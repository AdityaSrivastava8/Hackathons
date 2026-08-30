"""
agent/outreach.py
B2B Lead Scraper + Cold Email Engine.
"""

import json
import os
import re
import time
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")
LEADS_FILE = os.path.join(DATA_DIR, "leads.json")

SENDER_EMAIL = "yeahboyadi@gmail.com"
PLATFORM_URL = "https://ibmhackathon2026-uzj9dxbwnxgkcdffvztpfa.streamlit.app/on2026-uzj9dxbwnxgkcdffvztpfa.streamlit.app/"

COLD_EMAIL_SUBJECT = "25 Free AI Profiling Credits for {agency_name} — Detective Agentic AI"

COLD_EMAIL_BODY = """Hello {agency_name},

We noticed your agency operating in {location}. We are reaching out to introduce Detective Agentic AI — an automated criminal profiling and precedent-matching system purpose-built for legal and investigative agencies like yours.

What we offer:

- Instant behavioural risk scoring against a database of historical criminal precedents
- AI-generated suspect profiles with downloadable PDF reports
- Secure, session-isolated processing — your case data stays with you
- Flexible pay-as-you-go plans starting at Rs. 500 (Starter / 100 evaluations)

Claim your 25 FREE Profiling Evaluations now — no credit card required:
{platform_url}

If you have any questions or would like a live walkthrough, simply reply to this email.

Best regards,
Aditya Srivastava          |  Akshat Verma
Lead Developer & Founder   |  Co-Founder
yeahboyadi@gmail.com        |  akshat.v2166@gmail.com
Detective Agentic AI — {platform_url}
"""

def _ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)

def load_leads() -> List[Dict]:
    _ensure_data_dir()
    if not os.path.exists(LEADS_FILE):
        return []
    try:
        with open(LEADS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError, TypeError):
        return []

def save_leads(leads: List[Dict]) -> None:
    _ensure_data_dir()
    with open(LEADS_FILE, "w", encoding="utf-8") as file:
        json.dump(leads, file, indent=2, ensure_ascii=False)

_HEADERS = {
    "User-Agent": "DetectiveAgenticAI/1.0 (B2B lead discovery application)",
    "Accept": "application/json, text/html, application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}

def _get(url: str, params: Optional[dict] = None, timeout: int = 15):
    import requests
    return requests.get(url, params=params, headers=_HEADERS, timeout=timeout, allow_redirects=True)

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text).lower())

def _normalise_key(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())

def _safe_email(value: str) -> str:
    return str(value or "").strip()

def _domain_from_url(url: str) -> str:
    if not url:
        return ""
    try:
        hostname = urlparse(url).netloc
        return hostname.lower().removeprefix("www.") if hostname else ""
    except Exception:
        return ""

def _generated_email(name: str) -> str:
    slug = _slug(name)
    return f"info@{slug}.com" if slug else ""

_OSM_TAG_MAP = {
    "detective": [("office", "detective"), ("office", "investigator"), ("office", "lawyer")],
    "private": [("office", "detective"), ("office", "investigator")],
    "investigat": [("office", "detective"), ("office", "investigator")],
    "security": [("office", "security"), ("shop", "security")],
    "legal": [("office", "lawyer"), ("office", "advocate")],
    "advocate": [("office", "lawyer"), ("office", "advocate")],
    "police": [("amenity", "police")],
}

def _osm_tags_for_keyword(keyword: str) -> List[Tuple[str, str]]:
    keyword_lower = str(keyword or "").lower()
    for key, tags in _OSM_TAG_MAP.items():
        if key in keyword_lower:
            return tags
    return []

def _geocode_location(location: str) -> Tuple[Optional[float], Optional[float], str]:
    if not location or not location.strip():
        return None, None, ""
    try:
        response = _get("https://nominatim.openstreetmap.org/search",
                        params={"q": location.strip(), "format": "json", "limit": 1},
                        timeout=10)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list) or not data:
            return None, None, location
        item = data[0]
        return float(item["lat"]), float(item["lon"]), item.get("display_name", location)
    except Exception:
        return None, None, location

def _overpass_search(keyword: str, location: str, max_results: int) -> List[Dict]:
    if max_results <= 0:
        return []
    lat, lon, _ = _geocode_location(location)
    if lat is None or lon is None:
        return []

    tags = _osm_tags_for_keyword(keyword)
    radius = 25000
    query_parts = []

    if tags:
        for key, value in tags:
            query_parts.append(f'node["{key}"="{value}"](around:{radius},{lat},{lon});')
            query_parts.append(f'way["{key}"="{value}"](around:{radius},{lat},{lon});')
    else:
        keyword_clean = re.sub(r'["\\]', "", keyword.strip())[:80]
        if not keyword_clean:
            return []
        query_parts.append(f'node["name"~"{keyword_clean}",i](around:{radius},{lat},{lon});')
        query_parts.append(f'way["name"~"{keyword_clean}",i](around:{radius},{lat},{lon});')

    overpass_query = "[out:json][timeout:25];\n(\n" + "\n".join(query_parts) + f"\n);\nout center {max_results * 3};"

    try:
        response = _get("https://overpass-api.de/api/interpreter",
                        params={"data": overpass_query}, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return []

    leads, seen = [], set()
    for element in data.get("elements", []):
        if len(leads) >= max_results:
            break
        tags = element.get("tags", {})
        name = str(tags.get("name") or tags.get("operator") or tags.get("brand") or "").strip()
        if len(name) < 3:
            continue
        key = _normalise_key(name)
        if key in seen:
            continue
        seen.add(key)

        website = tags.get("website") or tags.get("contact:website") or tags.get("url") or ""
        phone = tags.get("phone") or tags.get("contact:phone") or ""
        email = tags.get("contact:email") or tags.get("email") or ""
        city = tags.get("addr:city") or tags.get("addr:town") or tags.get("addr:suburb") or location
        domain = _domain_from_url(website)
        if not email:
            email = f"info@{domain}" if domain else _generated_email(name)

        leads.append({
            "agency_name": name,
            "location": str(city),
            "contact_email": _safe_email(email),
            "website": str(website or ""),
            "phone": str(phone or ""),
            "source": "OpenStreetMap",
            "status": "Prospect",
        })
    return leads

def _duckduckgo_search(keyword: str, location: str, max_results: int) -> List[Dict]:
    if max_results <= 0:
        return []
    query = f"{str(keyword).strip()} agencies {str(location).strip()}"
    try:
        response = _get("https://api.duckduckgo.com/",
                        params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
                        timeout=15)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return []

    leads, seen = [], set()
    topics = list(data.get("RelatedTopics", []))
    topics.extend(data.get("Results", []))
    index = 0
    while index < len(topics) and len(leads) < max_results:
        item = topics[index]
        index += 1
        if not isinstance(item, dict):
            continue
        nested = item.get("Topics")
        if isinstance(nested, list):
            topics.extend(nested)
            continue
        text = str(item.get("Text", "") or item.get("Result", "")).strip()
        url = str(item.get("FirstURL", "") or item.get("url", "")).strip()
        if not text or not url:
            continue
        name = text.split(" - ", 1)[0].split(". ", 1)[0].strip()
        if len(name) < 4:
            continue
        key = _normalise_key(name)
        if key in seen:
            continue
        seen.add(key)
        domain = _domain_from_url(url)
        leads.append({
            "agency_name": name,
            "location": location,
            "contact_email": f"info@{domain}" if domain else _generated_email(name),
            "website": url,
            "phone": "",
            "source": "DuckDuckGo",
            "status": "Prospect",
        })
    return leads

def _wikipedia_search(keyword: str, location: str, max_results: int) -> List[Dict]:
    if max_results <= 0:
        return []
    query = f"{str(keyword).strip()} {str(location).strip()}"
    try:
        response = _get("https://en.wikipedia.org/w/api.php",
                        params={"action": "opensearch", "search": query, "limit": str(max_results * 2),
                                "namespace": "0", "format": "json"}, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return []
    if not isinstance(data, list) or len(data) < 4:
        return []

    leads, seen = [], set()
    relevance_words = [w for w in str(keyword).lower().split() if w] + ["detective", "invest", "agency", "security", "legal"]
    for name, url in zip(data[1], data[3]):
        if len(leads) >= max_results:
            break
        name, url = str(name or "").strip(), str(url or "").strip()
        if not name or not url or not any(word in name.lower() for word in relevance_words):
            continue
        key = _normalise_key(name)
        if key in seen:
            continue
        seen.add(key)
        leads.append({
            "agency_name": name, "location": location,
            "contact_email": _generated_email(name), "website": url,
            "phone": "", "source": "Wikipedia", "status": "Prospect",
        })
    return leads

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
    if max_results <= 0:
        return []
    location_words = str(location or "").replace(",", " ").strip().split()
    location_short = location_words[0] if location_words else "Local"
    leads, used = [], set()
    for suffix in _AGENCY_SUFFIXES:
        if len(leads) >= max_results:
            break
        name = f"{location_short} {suffix}"
        key = _normalise_key(name)
        if key in used:
            continue
        used.add(key)
        leads.append({
            "agency_name": name, "location": location,
            "contact_email": _generated_email(name), "website": "",
            "phone": "", "source": "Generated (Verify Manually)", "status": "Prospect",
        })
    return leads

def scrape_leads_sync(keyword: str, location: str, max_results: int = 20) -> List[Dict]:
    try:
        max_results = int(max_results)
    except (TypeError, ValueError):
        max_results = 20
    max_results = max(1, min(max_results, 100))
    keyword, location = str(keyword or "").strip(), str(location or "").strip()
    if not keyword or not location:
        return []

    collected = []
    for engine in (
        _overpass_search,
        _duckduckgo_search,
        _wikipedia_search,
    ):
        if len(collected) >= max_results:
            break
        try:
            collected.extend(engine(keyword, location, max_results - len(collected)))
        except Exception:
            pass

    if len(collected) < max_results:
        try:
            collected.extend(_seed_leads(keyword, location, max_results - len(collected)))
        except Exception:
            pass

    unique, seen_keys = [], set()
    for lead in collected:
        agency_name = str(lead.get("agency_name", "")).strip()
        lead_location = str(lead.get("location", location)).strip()
        key = (_normalise_key(agency_name), _normalise_key(lead_location))
        if not agency_name or key in seen_keys:
            continue
        seen_keys.add(key)
        unique.append({
            "agency_name": agency_name,
            "location": lead_location,
            "contact_email": _safe_email(lead.get("contact_email", "")),
            "website": str(lead.get("website", "")).strip(),
            "phone": str(lead.get("phone", "")).strip(),
            "source": str(lead.get("source", "Unknown")).strip(),
            "status": str(lead.get("status", "Prospect")).strip(),
        })
        if len(unique) >= max_results:
            break

    existing = load_leads()
    valid_existing = [
        lead for lead in existing
        if isinstance(lead, dict) and str(lead.get("agency_name", "")).strip()
    ]
    existing_keys = {
        (_normalise_key(lead.get("agency_name", "")), _normalise_key(lead.get("location", "")))
        for lead in valid_existing
    }
    merged = list(valid_existing)
    added = []
    for lead in unique:
        key = (_normalise_key(lead["agency_name"]), _normalise_key(lead["location"]))
        if key not in existing_keys:
            merged.append(lead)
            added.append(lead)
            existing_keys.add(key)
    try:
        save_leads(merged)
    except Exception:
        pass
    return added if added else unique

def send_cold_emails(
    leads: List[Dict],
    app_password: str,
    subject_template: str = COLD_EMAIL_SUBJECT,
    body_template: str = COLD_EMAIL_BODY,
    delay_seconds: int = 5,
    progress_callback: Optional[Callable[[int, int, str, str, str], None]] = None,
) -> List[Dict]:
    """Send personalised cold emails using Gmail SMTP via yagmail."""
    results = []
    if not isinstance(leads, list) or not leads:
        return results
    if not app_password or not str(app_password).strip():
        return [{"agency_name": "ALL", "status": "INIT_FAIL", "error": "Gmail App Password is missing."}]

    try:
        import yagmail
    except ImportError:
        return [{"agency_name": "ALL", "status": "INIT_FAIL", "error": "yagmail is not installed. Add 'yagmail' to requirements.txt."}]

    try:
        yag = yagmail.SMTP(SENDER_EMAIL, str(app_password).strip())
    except Exception as exc:
        return [{"agency_name": "ALL", "status": "INIT_FAIL", "error": str(exc)}]

    total = len(leads)
    try:
        for index, lead in enumerate(leads, start=1):
            lead = lead if isinstance(lead, dict) else {}
            agency = str(lead.get("agency_name") or lead.get("company_name") or lead.get("company") or lead.get("name") or "Agency").strip()
            location = str(lead.get("location") or "your region").strip()
            recipient = _safe_email(
                lead.get("contact_email") or lead.get("email") or lead.get("email_address") or ""
            )

            if not recipient or "@" not in recipient or "." not in recipient.rsplit("@", 1)[-1]:
                result = {"agency_name": agency, "recipient": recipient, "status": "SKIPPED", "error": "No valid email address."}
            else:
                try:
                    format_values = {
                        "agency_name": agency,
                        "company_name": agency,
                        "company": agency,
                        "business_name": agency,
                        "recipient": agency,
                        "name": agency,
                        "email": recipient,
                        "location": location,
                        "platform_url": PLATFORM_URL,
                    }
                    subject = subject_template.format(**format_values)
                    body = body_template.format(**format_values)
                    yag.send(to=recipient, subject=subject, contents=body)
                    result = {"agency_name": agency, "recipient": recipient, "status": "SENT", "error": ""}
                except Exception as exc:
                    result = {"agency_name": agency, "recipient": recipient, "status": "FAILED", "error": str(exc)}

            results.append(result)
            if progress_callback:
                try:
                    progress_callback(index, total, agency, result["status"], result.get("error", ""))
                except Exception:
                    pass

            if index < total:
                try:
                    delay = float(delay_seconds)
                except (TypeError, ValueError):
                    delay = 5.0
                if delay > 0:
                    time.sleep(delay)
    finally:
        try:
            yag.close()
        except Exception:
            pass
    return results

__all__ = [
    "scrape_leads_sync",
    "send_cold_emails",
    "load_leads",
    "save_leads",
    "COLD_EMAIL_SUBJECT",
    "COLD_EMAIL_BODY",
]
