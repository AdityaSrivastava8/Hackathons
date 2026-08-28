"""
agent/outreach.py
Autonomous B2B Lead Scraper (Playwright) + Cold Email Engine (yagmail)
"""

import asyncio
import json
import os
import subprocess
import sys
import time
from typing import List, Dict

def _ensure_playwright_browsers() -> None:
    """
    Silently install Chromium binaries if they are missing.
    Playwright raises an error mentioning 'Executable doesn't exist' or
    'please run playwright install' when the binary is absent — we catch
    that at launch time, but it's cheaper to pre-check here once per
    process by running `playwright install chromium --with-deps`.
    Only runs when the binary cache directory is absent or empty.
    """
    try:
        # Fast path: check if chromium is already available
        import playwright._impl._driver as _drv  # type: ignore
        cache_base = os.path.join(os.path.expanduser("~"), ".cache", "ms-playwright")
        has_chrome = any(
            "chromium" in d.lower()
            for d in os.listdir(cache_base)
        ) if os.path.isdir(cache_base) else False

        if not has_chrome:
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium", "--with-deps"],
                check=False,
                capture_output=True,
                timeout=180,
            )
    except Exception:
        # If the check itself fails, try installing unconditionally
        try:
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                check=False,
                capture_output=True,
                timeout=180,
            )
        except Exception:
            pass  # scraper will surface the real error on launch

# ── Constants ──────────────────────────────────────────────────────────────────
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
LEADS_FILE = os.path.join(DATA_DIR, "leads.json")

SENDER_EMAIL = "yeahboyadi@gmail.com"

COLD_EMAIL_SUBJECT = "25 Free AI Profiling Credits for {agency_name} — Detective Agentic AI"

COLD_EMAIL_BODY = """Hello {agency_name},

We noticed your agency operating in {location}. We are reaching out to introduce Detective Agentic AI—an automated criminal profiling and precedent matching system built for legal & investigative agencies.

You can test our platform immediately with 25 FREE Profiling Evaluations. Once your 25 free credits are completed, you can seamlessly select a plan (Starter, Pro, or Enterprise) and scan our UPI QR code to instantly top up your account quota.

Start your trial here: https://detective-ai.streamlit.app

Best regards,
Aditya Srivastava
Lead Developer & Founder"""


def _ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def load_leads() -> List[Dict]:
    """Load persisted leads from disk."""
    _ensure_data_dir()
    if not os.path.exists(LEADS_FILE):
        return []
    try:
        with open(LEADS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_leads(leads: List[Dict]) -> None:
    """Persist leads list to disk."""
    _ensure_data_dir()
    with open(LEADS_FILE, "w", encoding="utf-8") as f:
        json.dump(leads, f, indent=2, ensure_ascii=False)


# ── Playwright Scraper ─────────────────────────────────────────────────────────

async def _scrape_google_maps(keyword: str, location: str, max_results: int = 20) -> List[Dict]:
    """Scrape Google Maps business listings for the given keyword + location."""
    leads: List[Dict] = []
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return [{"error": "playwright not installed. Run: pip install playwright && playwright install chromium"}]

    query = f"{keyword} in {location}"
    url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"

    # ── Auto-install Chromium if missing ──────────────────────────────────
    _ensure_playwright_browsers()

    async with async_playwright() as p:
        # Try launch; if binary still missing, run installer and retry once
        try:
            browser = await p.chromium.launch(headless=True)
        except Exception as launch_err:
            err_str = str(launch_err).lower()
            if "executable" in err_str or "playwright install" in err_str:
                subprocess.run(
                    [sys.executable, "-m", "playwright", "install", "chromium", "--with-deps"],
                    check=False,
                    capture_output=True,
                    timeout=180,
                )
                browser = await p.chromium.launch(headless=True)
            else:
                raise

        page = await browser.new_page()
        try:
            await page.goto(url, timeout=30000)
            await page.wait_for_timeout(4000)

            # Scroll sidebar to load more listings
            for _ in range(5):
                await page.mouse.wheel(0, 2500)
                await page.wait_for_timeout(1500)

            listings = await page.locator('a[href*="/maps/place/"]').all()
            seen: set = set()

            for listing in listings[:max_results]:
                try:
                    name = await listing.get_attribute("aria-label")
                    href = await listing.get_attribute("href")
                    if not name or name in seen:
                        continue
                    seen.add(name)
                    sanitized = "".join(c for c in name.lower() if c.isalnum())
                    leads.append({
                        "agency_name": name,
                        "location": location,
                        "contact_email": f"info@{sanitized}.com",
                        "website": href or "",
                        "source": "Google Maps",
                        "status": "Prospect",
                    })
                except Exception:
                    continue
        finally:
            await browser.close()

    return leads


def scrape_leads_sync(keyword: str, location: str, max_results: int = 20) -> List[Dict]:
    """
    Synchronous wrapper around the async scraper.
    Streamlit's ScriptRunner thread has NO event loop, so we always
    spin up a dedicated thread and call asyncio.run() inside it.
    """
    import concurrent.futures

    def _run() -> List[Dict]:
        return asyncio.run(_scrape_google_maps(keyword, location, max_results))

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_run)
            new_leads = future.result(timeout=120)
    except Exception as e:
        return [{"error": str(e)}]

    if new_leads and "error" not in new_leads[0]:
        # Merge with existing leads (dedup by agency_name + location)
        existing = load_leads()
        existing_keys = {(l["agency_name"], l["location"]) for l in existing}
        merged = existing[:]
        for lead in new_leads:
            key = (lead["agency_name"], lead["location"])
            if key not in existing_keys:
                merged.append(lead)
                existing_keys.add(key)
        save_leads(merged)

    return new_leads


# ── Email Engine ───────────────────────────────────────────────────────────────

def send_cold_emails(
    leads: List[Dict],
    app_password: str,
    subject_template: str = COLD_EMAIL_SUBJECT,
    body_template: str = COLD_EMAIL_BODY,
    delay_seconds: int = 5,
    progress_callback=None,
) -> List[Dict]:
    """
    Send personalised cold emails to each lead.
    progress_callback(idx, total, agency_name, status) is called after each send.
    Returns a list of result dicts.
    """
    import yagmail

    results = []
    total = len(leads)

    try:
        yag = yagmail.SMTP(SENDER_EMAIL, app_password)
    except Exception as e:
        return [{"agency_name": "ALL", "status": "INIT_FAIL", "error": str(e)}]

    for idx, lead in enumerate(leads, 1):
        agency = lead.get("agency_name", "Agency")
        location = lead.get("location", "your region")
        recipient = lead.get("contact_email", "")

        if not recipient:
            results.append({"agency_name": agency, "status": "SKIPPED", "error": "No email"})
            continue

        subject = subject_template.format(agency_name=agency, location=location)
        body = body_template.format(agency_name=agency, location=location)

        try:
            yag.send(to=recipient, subject=subject, contents=body)
            status = "SENT"
            error = ""
        except Exception as e:
            status = "FAILED"
            error = str(e)

        results.append({"agency_name": agency, "recipient": recipient, "status": status, "error": error})

        if progress_callback:
            progress_callback(idx, total, agency, status)

        if idx < total:
            time.sleep(delay_seconds)

    return results
