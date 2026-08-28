"""
agent/outreach.py
B2B Lead Scraper (requests + BeautifulSoup, no browser required)
+ Cold Email Engine (yagmail)

Uses HTTP scraping against Google Search / JustDial instead of Playwright,
so it works on Streamlit Cloud with zero binary dependencies.
"""

import json
import os
import re
import time
import urllib.parse
from typing import List, Dict

# ── Constants ──────────────────────────────────────────────────────────────────
DATA_DIR   = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
LEADS_FILE = os.path.join(DATA_DIR, "leads.json")

SENDER_EMAIL = "yeahboyadi@gmail.com"

COLD_EMAIL_SUBJECT = "25 Free AI Profiling Credits for {agency_name} — Detective Agentic AI"

COLD_EMAIL_BODY = """Hello {agency_name},

We noticed your agency operating in {location}. We are reaching out to introduce Detective Agentic AI — an automated criminal profiling and precedent matching system built for legal & investigative agencies.

You can test our platform immediately with 25 FREE Profiling Evaluations. Once your 25 free credits are completed, you can seamlessly select a plan (Starter, Pro, or Enterprise) and scan our UPI QR code to instantly top up your account quota.

Start your trial here: https://detective-ai.streamlit.app

Best regards,
Aditya Srivastava
Lead Developer & Founder"""


# ── Persistence helpers ────────────────────────────────────────────────────────

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


# ── HTTP Scraper ───────────────────────────────────────────────────────────────

# Rotate User-Agents to reduce bot-detection blocks
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]

_HEADERS = {
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
    "DNT":             "1",
}


def _get_headers(idx: int = 0) -> dict:
    h = dict(_HEADERS)
    h["User-Agent"] = _USER_AGENTS[idx % len(_USER_AGENTS)]
    return h


def _scrape_google_search(keyword: str, location: str, max_results: int) -> List[Dict]:
    """
    Scrape Google Search results for 'keyword location' to find agency names,
    websites, and derive placeholder contact emails.
    """
    import requests
    from bs4 import BeautifulSoup

    query   = f"{keyword} {location} contact email"
    url     = f"https://www.google.com/search?q={urllib.parse.quote(query)}&num=50"
    leads: List[Dict] = []
    seen: set = set()

    try:
        resp = requests.get(url, headers=_get_headers(0), timeout=15, allow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # ── Extract result blocks ──────────────────────────────────────────
        for block in soup.select("div.g, div[data-hveid]"):
            if len(leads) >= max_results:
                break
            try:
                # Agency name — from heading
                h3 = block.find("h3")
                if not h3:
                    continue
                name = h3.get_text(strip=True)
                if not name or name in seen or len(name) < 4:
                    continue
                # Skip generic result types
                if any(skip in name.lower() for skip in ["wikipedia", "youtube", "facebook", "linkedin"]):
                    continue

                seen.add(name)

                # Website URL — from the green breadcrumb span
                site_span = block.select_one("cite, span.iUh30, div.UPmit")
                raw_site  = site_span.get_text(strip=True) if site_span else ""
                website   = raw_site.split(" ")[0] if raw_site else ""

                # Derive a candidate email from the domain
                domain    = re.sub(r"https?://", "", website).split("/")[0].strip()
                email     = f"info@{domain}" if domain and "." in domain else ""

                leads.append({
                    "agency_name":   name,
                    "location":      location,
                    "contact_email": email,
                    "website":       f"https://{domain}" if domain else "",
                    "source":        "Google Search",
                    "status":        "Prospect",
                })
            except Exception:
                continue

    except Exception as e:
        return [{"error": f"Google Search scrape failed: {e}"}]

    return leads


def _scrape_justdial(keyword: str, location: str, max_results: int) -> List[Dict]:
    """
    Scrape JustDial search results — richer contact data for Indian agencies.
    """
    import requests
    from bs4 import BeautifulSoup

    # JustDial URL format: /keyword-in-location
    kw_slug   = keyword.lower().replace(" ", "-")
    loc_slug  = location.lower().replace(" ", "-").replace(",", "")
    url       = f"https://www.justdial.com/{loc_slug}/{kw_slug}"
    leads: List[Dict] = []
    seen: set = set()

    try:
        resp = requests.get(url, headers=_get_headers(1), timeout=15, allow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for card in soup.select("li.cntanr, div.resultbox_title_anchor, li[class*='store-card']"):
            if len(leads) >= max_results:
                break
            try:
                # Name
                name_tag = card.select_one(
                    "span.lng_cont_name, a.store-name, h2.jdnm, span.jdnm"
                )
                if not name_tag:
                    continue
                name = name_tag.get_text(strip=True)
                if not name or name in seen:
                    continue
                seen.add(name)

                # Phone / email — JustDial hides these; derive from name slug
                sanitized = re.sub(r"[^a-z0-9]", "", name.lower())
                email     = f"info@{sanitized}.com"

                # Location text
                loc_tag   = card.select_one("span.cont_fl_addr, span.jdnm_add")
                loc_text  = loc_tag.get_text(strip=True) if loc_tag else location

                leads.append({
                    "agency_name":   name,
                    "location":      loc_text or location,
                    "contact_email": email,
                    "website":       "",
                    "source":        "JustDial",
                    "status":        "Prospect",
                })
            except Exception:
                continue

    except Exception as e:
        # JustDial may return 403/captcha; don't crash — return empty
        return []

    return leads


def scrape_leads_sync(keyword: str, location: str, max_results: int = 20) -> List[Dict]:
    """
    Scrape B2B leads using HTTP (no browser needed).
    Tries JustDial first (best for Indian agencies), then Google Search as fallback.
    Merges results with existing leads.json (deduplicates by name+location).
    """
    new_leads: List[Dict] = []

    # ── 1. JustDial (primary — richer Indian business data) ────────────────
    jd_leads = _scrape_justdial(keyword, location, max_results)
    new_leads.extend(jd_leads)

    # ── 2. Google Search (fills up remaining quota) ─────────────────────────
    remaining = max_results - len(new_leads)
    if remaining > 0:
        gs_leads = _scrape_google_search(keyword, location, remaining)
        if gs_leads and "error" in gs_leads[0]:
            if not new_leads:            # only surface error if we have nothing
                return gs_leads
        else:
            new_leads.extend(gs_leads)

    if not new_leads:
        return [{"error": (
            "No leads found. Google may have blocked the request. "
            "Try a different keyword or add leads manually."
        )}]

    # ── Dedup & merge into leads.json ──────────────────────────────────────
    existing      = load_leads()
    existing_keys = {(l["agency_name"], l["location"]) for l in existing}
    merged        = existing[:]
    added         = []

    for lead in new_leads:
        key = (lead["agency_name"], lead["location"])
        if key not in existing_keys:
            merged.append(lead)
            added.append(lead)
            existing_keys.add(key)

    save_leads(merged)
    return added if added else new_leads


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
    Send personalised cold emails to each lead via yagmail (Gmail SMTP).
    progress_callback(idx, total, agency_name, status) is called after each send.
    Returns a list of result dicts.
    """
    import yagmail

    results: List[Dict] = []
    total = len(leads)

    try:
        yag = yagmail.SMTP(SENDER_EMAIL, app_password)
    except Exception as e:
        return [{"agency_name": "ALL", "status": "INIT_FAIL", "error": str(e)}]

    for idx, lead in enumerate(leads, 1):
        agency    = lead.get("agency_name", "Agency")
        location  = lead.get("location", "your region")
        recipient = lead.get("contact_email", "")

        if not recipient or "@" not in recipient:
            result = {"agency_name": agency, "status": "SKIPPED", "error": "No valid email"}
        else:
            subject = subject_template.format(agency_name=agency, location=location)
            body    = body_template.format(agency_name=agency, location=location)
            try:
                yag.send(to=recipient, subject=subject, contents=body)
                result = {"agency_name": agency, "recipient": recipient, "status": "SENT",   "error": ""}
            except Exception as e:
                result = {"agency_name": agency, "recipient": recipient, "status": "FAILED", "error": str(e)}

        results.append(result)

        if progress_callback:
            progress_callback(idx, total, agency, result["status"])

        if idx < total:
            time.sleep(delay_seconds)

    return results
