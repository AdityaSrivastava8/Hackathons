"""
agent/outreach.py
B2B Lead Scraper — Multi-engine fallback strategy (works on Streamlit Cloud)
+ Cold Email Engine (yagmail)

Engine priority:
  1. Overpass API (OpenStreetMap) — real business data, completely free, no auth
  2. Nominatim geocoding + local business lookup
  3. DuckDuckGo Instant Answer API — no auth, no captcha
  4. Wikipedia/DBpedia open-data search
  5. Smart seed generator — deterministic placeholder leads from keyword+location
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

We noticed your agency operating in {location}. We are reaching out to introduce Detective Agentic AI — an automated criminal profiling and precedent-matching system purpose-built for legal and investigative agencies like yours.

What we offer:
- Instant behavioural risk scoring against a database of historical criminal precedents
- AI-generated suspect profiles with downloadable PDF reports
- Secure, session-isolated processing — your case data stays with you
- Flexible pay-as-you-go plans starting at Rs. 500 (Starter / 100 evaluations)

Claim your 25 FREE Profiling Evaluations now — no credit card required:
https://detective-ai.streamlit.app

If you have any questions or would like a live walkthrough, simply reply to this email.

Best regards,

Aditya Srivastava          |  Akshat Verma
Lead Developer & Founder   |  Co-Founder
yeahboyadi@gmail.com       |  akshat.v2166@gmail.com

Detective Agentic AI — https://detective-ai.streamlit.app"""


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


# ── Shared HTTP session ────────────────────────────────────────────────────────

_STEALTH_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "application/json, text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
    "DNT":             "1",
    "Referer":         "https://www.google.com/",
}


def _get(url: str, params: dict = None, timeout: int = 15) -> "requests.Response":
    import requests
    return requests.get(url, params=params, headers=_STEALTH_HEADERS,
                        timeout=timeout, allow_redirects=True)


def _slug(text: str) -> str:
    """Clean text to alphanumeric slug for email generation."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


# ══════════════════════════════════════════════════════════════════════════════
# ENGINE 1 — Overpass API (OpenStreetMap)
# Free, no auth, no captcha, returns real POI business data
# ══════════════════════════════════════════════════════════════════════════════

# Map common keyword phrases → OSM amenity/shop tags
_OSM_TAG_MAP = {
    "detective":     [("office", "detective"), ("office", "investigator"), ("office", "lawyer")],
    "private":       [("office", "detective"), ("office", "investigator")],
    "investigat":    [("office", "detective"), ("office", "investigator")],
    "security":      [("office", "security"), ("shop", "security")],
    "legal":         [("office", "lawyer"), ("office", "advocate")],
    "advocate":      [("office", "lawyer"), ("office", "advocate")],
    "police":        [("amenity", "police")],
}

def _osm_tags_for_keyword(keyword: str) -> List[tuple]:
    kw = keyword.lower()
    for key, tags in _OSM_TAG_MAP.items():
        if key in kw:
            return tags
    # generic fallback: search by name
    return []


def _geocode_location(location: str):
    """Return (lat, lon, display_name) for a location string using Nominatim."""
    try:
        resp = _get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": location, "format": "json", "limit": 1},
            timeout=10,
        )
        data = resp.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"]), data[0].get("display_name", location)
    except Exception:
        pass
    return None, None, location


def _overpass_search(keyword: str, location: str, max_results: int) -> List[Dict]:
    """
    Query Overpass API for businesses matching keyword near location.
    Completely free, no authentication, works on any server IP.
    """
    lat, lon, _ = _geocode_location(location)
    if lat is None:
        return []

    leads: List[Dict] = []
    tags  = _osm_tags_for_keyword(keyword)

    # Build Overpass QL query — search 25km radius
    radius = 25000  # metres
    if tags:
        tag_queries = "\n  ".join(
            f'node["{k}"="{v}"](around:{radius},{lat},{lon});'
            f'\n  way["{k}"="{v}"](around:{radius},{lat},{lon});'
            for k, v in tags
        )
    else:
        # Name-based search when no tag mapping exists
        kw_clean = keyword.replace('"', "")
        tag_queries = (
            f'node["name"~"{kw_clean}",i](around:{radius},{lat},{lon});\n  '
            f'way["name"~"{kw_clean}",i](around:{radius},{lat},{lon});'
        )

    overpass_query = f"""
[out:json][timeout:25];
(
  {tag_queries}
);
out center {max_results * 3};
"""

    try:
        resp = _get(
            "https://overpass-api.de/api/interpreter",
            params={"data": overpass_query},
            timeout=30,
        )
        data = resp.json()
        seen: set = set()

        for element in data.get("elements", []):
            if len(leads) >= max_results:
                break
            tags_el = element.get("tags", {})

            name = tags_el.get("name") or tags_el.get("operator") or tags_el.get("brand")
            if not name or name in seen or len(name) < 3:
                continue
            seen.add(name)

            website = (
                tags_el.get("website") or
                tags_el.get("contact:website") or
                tags_el.get("url") or ""
            )
            phone = tags_el.get("phone") or tags_el.get("contact:phone") or ""
            addr_city = (
                tags_el.get("addr:city") or
                tags_el.get("addr:suburb") or
                location
            )

            # Derive email from website domain or name slug
            domain = re.sub(r"https?://", "", website).split("/")[0].strip()
            email  = (
                tags_el.get("contact:email") or
                tags_el.get("email") or
                (f"info@{domain}" if domain and "." in domain else f"info@{_slug(name)}.com")
            )

            leads.append({
                "agency_name":   name,
                "location":      addr_city,
                "contact_email": email,
                "website":       website,
                "phone":         phone,
                "source":        "OpenStreetMap",
                "status":        "Prospect",
            })

    except Exception:
        return []

    return leads


# ══════════════════════════════════════════════════════════════════════════════
# ENGINE 2 — DuckDuckGo Instant Answer API
# No auth, no captcha, returns structured JSON
# ══════════════════════════════════════════════════════════════════════════════

def _duckduckgo_search(keyword: str, location: str, max_results: int) -> List[Dict]:
    """
    Use DuckDuckGo's Instant Answer API to find related topics/topics.
    Returns partial leads enriched with name + website.
    """
    query = f"{keyword} agencies {location}"
    leads: List[Dict] = []

    try:
        resp = _get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
            timeout=15,
        )
        data  = resp.json()
        seen: set = set()

        # RelatedTopics contains real entity names
        topics = data.get("RelatedTopics", []) + data.get("Results", [])
        for item in topics:
            if len(leads) >= max_results:
                break
            if isinstance(item, dict) and "Topics" in item:
                # Nested topic group — flatten
                topics.extend(item["Topics"])
                continue

            text = item.get("Text", "") or item.get("Result", "")
            url  = item.get("FirstURL", "") or item.get("url", "")
            if not text or not url:
                continue

            # First sentence up to " - " is usually the entity name
            name = text.split(" - ")[0].split(". ")[0].strip()
            if not name or name in seen or len(name) < 4:
                continue
            seen.add(name)

            domain = re.sub(r"https?://", "", url).split("/")[0].strip()
            email  = f"info@{domain}" if domain and "." in domain else f"info@{_slug(name)}.com"

            leads.append({
                "agency_name":   name,
                "location":      location,
                "contact_email": email,
                "website":       url,
                "source":        "DuckDuckGo",
                "status":        "Prospect",
            })

    except Exception:
        return []

    return leads


# ══════════════════════════════════════════════════════════════════════════════
# ENGINE 3 — Wikipedia/DBpedia Open Search
# Returns known named entities (agencies, organisations)
# ══════════════════════════════════════════════════════════════════════════════

def _wikipedia_search(keyword: str, location: str, max_results: int) -> List[Dict]:
    """Search Wikipedia OpenSearch API for agency-related articles."""
    query = f"{keyword} {location}"
    leads: List[Dict] = []

    try:
        resp = _get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "opensearch",
                "search": query,
                "limit":  str(max_results * 2),
                "namespace": "0",
                "format": "json",
            },
            timeout=10,
        )
        data = resp.json()
        # data = [query, [titles], [descriptions], [urls]]
        if len(data) >= 4:
            titles = data[1]
            urls   = data[3]
            seen: set = set()

            for name, url in zip(titles, urls):
                if len(leads) >= max_results:
                    break
                if not name or name in seen:
                    continue
                # Filter to relevant entries
                kw_words = keyword.lower().split()
                if not any(w in name.lower() for w in kw_words + ["detective", "invest", "agency", "security"]):
                    continue
                seen.add(name)
                slug  = _slug(name)
                leads.append({
                    "agency_name":   name,
                    "location":      location,
                    "contact_email": f"info@{slug}.com",
                    "website":       url,
                    "source":        "Wikipedia",
                    "status":        "Prospect",
                })
    except Exception:
        return []

    return leads


# ══════════════════════════════════════════════════════════════════════════════
# ENGINE 4 — Smart Seed Generator (deterministic fallback)
# When all live sources are blocked, generate realistic placeholder leads
# that can be manually verified and email-corrected before dispatch.
# ══════════════════════════════════════════════════════════════════════════════

_AGENCY_SUFFIXES = [
    "Detective Agency", "Investigation Services", "Private Investigators",
    "Security Solutions", "Intellect Detectives", "Inquiry Bureau",
    "Surveillance Experts", "Probe Detective Services", "Field Investigations",
    "Eagle Eye Detectives", "Alpha Investigation", "Shield Detectives",
    "Nationwide Investigators", "Hawk Surveillance", "Trustworthy Detectives",
    "Guardian Investigation", "Precision Detectives", "City Probe Services",
    "Metro Investigation Bureau", "Pioneer Detective Agency",
]

def _seed_leads(keyword: str, location: str, max_results: int) -> List[Dict]:
    """
    Generate deterministic placeholder leads based on keyword + location.
    Names are realistic and consistent — same input always produces same output.
    Contact emails are in standard `info@` format ready for manual verification.
    """
    loc_clean   = location.replace(",", "").strip()
    loc_words   = loc_clean.split()
    loc_short   = loc_words[0] if loc_words else loc_clean

    leads: List[Dict] = []
    used: set = set()

    for i, suffix in enumerate(_AGENCY_SUFFIXES):
        if len(leads) >= max_results:
            break
        name = f"{loc_short} {suffix}"
        if name in used:
            continue
        used.add(name)
        slug  = _slug(name)
        leads.append({
            "agency_name":   name,
            "location":      location,
            "contact_email": f"info@{slug}.com",
            "website":       "",
            "source":        "Generated (Verify Manually)",
            "status":        "Prospect",
        })

    return leads


# ══════════════════════════════════════════════════════════════════════════════
# MAIN SCRAPER — 4-engine waterfall
# ══════════════════════════════════════════════════════════════════════════════

def scrape_leads_sync(keyword: str, location: str, max_results: int = 20) -> List[Dict]:
    """
    Multi-engine B2B lead scraper. Tries each engine in order until enough
    leads are collected. Always returns at least seed-generated leads so the
    admin can manually verify and update emails before dispatching.

    Engine order:
        1. Overpass API / OpenStreetMap  (real data, no auth, no captcha)
        2. DuckDuckGo Instant Answer API (no auth, no captcha)
        3. Wikipedia OpenSearch API      (named entities)
        4. Smart Seed Generator          (placeholder leads, always works)
    """
    collected: List[Dict] = []

    # ── Engine 1: Overpass / OSM ───────────────────────────────────────────
    try:
        osm = _overpass_search(keyword, location, max_results)
        collected.extend(osm)
    except Exception:
        pass

    # ── Engine 2: DuckDuckGo ───────────────────────────────────────────────
    if len(collected) < max_results:
        try:
            ddg = _duckduckgo_search(keyword, location, max_results - len(collected))
            collected.extend(ddg)
        except Exception:
            pass

    # ── Engine 3: Wikipedia ────────────────────────────────────────────────
    if len(collected) < max_results:
        try:
            wiki = _wikipedia_search(keyword, location, max_results - len(collected))
            collected.extend(wiki)
        except Exception:
            pass

    # ── Engine 4: Seed generator (always fills remaining quota) ───────────
    if len(collected) < max_results:
        seed = _seed_leads(keyword, location, max_results - len(collected))
        collected.extend(seed)

    # ── Dedup by name+location, cap at max_results ─────────────────────────
    seen_keys: set = set()
    unique: List[Dict] = []
    for lead in collected:
        key = (lead.get("agency_name", ""), lead.get("location", ""))
        if key not in seen_keys:
            seen_keys.add(key)
            unique.append(lead)
        if len(unique) >= max_results:
            break

    # ── Merge into leads.json ──────────────────────────────────────────────
    existing      = load_leads()
    existing_keys = {(l["agency_name"], l["location"]) for l in existing}
    merged        = existing[:]
    added: List[Dict] = []

    for lead in unique:
        key = (lead["agency_name"], lead["location"])
        if key not in existing_keys:
            merged.append(lead)
            added.append(lead)
            existing_keys.add(key)

    save_leads(merged)

    # Always return something — never show the "blocked" error again
    return added if added else unique


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
            progress_callback(idx, total, agency, result["status"], result.get("error", ""))

        if idx < total:
            time.sleep(delay_seconds)

    return results
