"""
agent/outreach.py

B2B Lead Scraper + Cold Email Engine.

Scraper priority:
    1. OpenStreetMap / Overpass API
    2. DuckDuckGo Instant Answer API
    3. Wikipedia OpenSearch API
    4. Deterministic seed fallback

The module is intentionally dependency-light so that it can run
on Streamlit Cloud.

Exports used by frontend/app.py:
    - scrape_leads_sync
    - send_cold_emails
    - load_leads
    - save_leads
    - COLD_EMAIL_SUBJECT
    - COLD_EMAIL_BODY
"""

import json
import os
import re
import time
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import quote, urlparse


# =============================================================================
# PATHS AND CONSTANTS
# =============================================================================

BASE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)

DATA_DIR = os.path.join(BASE_DIR, "data")
LEADS_FILE = os.path.join(DATA_DIR, "leads.json")

SENDER_EMAIL = "yeahboyadi@gmail.com"

COLD_EMAIL_SUBJECT = (
    "25 Free AI Profiling Credits for {agency_name} in {location} "
    "— Detective Agentic AI"
)

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
yeahboyadi@gmail.com        |  akshat.v2166@gmail.com

Detective Agentic AI — https://detective-ai.streamlit.app
"""


# =============================================================================
# PERSISTENCE
# =============================================================================

def _ensure_data_dir() -> None:
    """Create the data directory if necessary."""
    os.makedirs(DATA_DIR, exist_ok=True)


def load_leads() -> List[Dict]:
    """
    Load persisted leads from data/leads.json.

    Returns an empty list if the file does not exist or contains
    invalid JSON.
    """
    _ensure_data_dir()

    if not os.path.exists(LEADS_FILE):
        return []

    try:
        with open(LEADS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, list):
            return data

        return []

    except (OSError, json.JSONDecodeError, TypeError):
        return []


def save_leads(leads: List[Dict]) -> None:
    """Persist leads to data/leads.json."""
    _ensure_data_dir()

    with open(
        LEADS_FILE,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            leads,
            file,
            indent=2,
            ensure_ascii=False
        )


# =============================================================================
# HTTP HELPER
# =============================================================================

_HEADERS = {
    "User-Agent": (
        "DetectiveAgenticAI/1.0 "
        "(B2B lead discovery application)"
    ),
    "Accept": (
        "application/json, text/html, "
        "application/xhtml+xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}


def _get(
    url: str,
    params: Optional[dict] = None,
    timeout: int = 15
):
    """
    Perform an HTTP GET request.

    requests is imported lazily so importing this module itself
    does not fail if the package is temporarily unavailable.
    """
    import requests

    return requests.get(
        url,
        params=params,
        headers=_HEADERS,
        timeout=timeout,
        allow_redirects=True,
    )


# =============================================================================
# TEXT HELPERS
# =============================================================================

def _slug(text: str) -> str:
    """Convert text into a simple alphanumeric slug."""
    return re.sub(
        r"[^a-z0-9]",
        "",
        str(text).lower()
    )


def _normalise_key(value: str) -> str:
    """Create a stable comparison key."""
    return re.sub(
        r"\s+",
        " ",
        str(value or "").strip().lower()
    )


def _safe_email(value: str) -> str:
    """
    Return a cleaned email address.

    This does not verify whether the mailbox actually exists.
    """
    return str(value or "").strip()


def _domain_from_url(url: str) -> str:
    """Extract a hostname from a website URL."""
    if not url:
        return ""

    try:
        parsed = urlparse(url)

        hostname = parsed.netloc

        if not hostname:
            return ""

        return hostname.lower().removeprefix("www.")

    except Exception:
        return ""


def _generated_email(name: str) -> str:
    """
    Generate a placeholder email for leads that do not expose
    an actual contact address.

    These generated addresses should be manually verified before
    sending outreach emails.
    """
    slug = _slug(name)

    if not slug:
        return ""

    return f"info@{slug}.com"


# =============================================================================
# ENGINE 1 — OPENSTREETMAP / OVERPASS
# =============================================================================

_OSM_TAG_MAP = {
    "detective": [
        ("office", "detective"),
        ("office", "investigator"),
        ("office", "lawyer"),
    ],
    "private": [
        ("office", "detective"),
        ("office", "investigator"),
    ],
    "investigat": [
        ("office", "detective"),
        ("office", "investigator"),
    ],
    "security": [
        ("office", "security"),
        ("shop", "security"),
    ],
    "legal": [
        ("office", "lawyer"),
        ("office", "advocate"),
    ],
    "advocate": [
        ("office", "lawyer"),
        ("office", "advocate"),
    ],
    "police": [
        ("amenity", "police"),
    ],
}


def _osm_tags_for_keyword(
    keyword: str
) -> List[Tuple[str, str]]:
    """Return OSM tags relevant to the supplied keyword."""
    keyword_lower = str(keyword or "").lower()

    for key, tags in _OSM_TAG_MAP.items():
        if key in keyword_lower:
            return tags

    return []


def _geocode_location(
    location: str
) -> Tuple[Optional[float], Optional[float], str]:
    """
    Convert a human-readable location into latitude/longitude
    using Nominatim.
    """
    if not location or not location.strip():
        return None, None, ""

    try:
        response = _get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": location.strip(),
                "format": "json",
                "limit": 1,
            },
            timeout=10,
        )

        response.raise_for_status()

        data = response.json()

        if not isinstance(data, list) or not data:
            return None, None, location

        item = data[0]

        return (
            float(item["lat"]),
            float(item["lon"]),
            item.get("display_name", location),
        )

    except Exception:
        return None, None, location


def _overpass_search(
    keyword: str,
    location: str,
    max_results: int
) -> List[Dict]:
    """Search OpenStreetMap businesses/organisations around a location."""
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
            query_parts.append(
                f'node["{key}"="{value}"]'
                f'(around:{radius},{lat},{lon});'
            )
            query_parts.append(
                f'way["{key}"="{value}"]'
                f'(around:{radius},{lat},{lon});'
            )
    else:
        keyword_clean = re.sub(
            r'["\\]',
            "",
            keyword.strip()
        )

        if not keyword_clean:
            return []

        keyword_clean = keyword_clean[:80]

        query_parts.append(
            f'node["name"~"{keyword_clean}",i]'
            f'(around:{radius},{lat},{lon});'
        )
        query_parts.append(
            f'way["name"~"{keyword_clean}",i]'
            f'(around:{radius},{lat},{lon});'
        )

    overpass_query = (
        "[out:json][timeout:25];\n"
        "(\n"
        + "\n".join(query_parts)
        + "\n);\n"
        f"out center {max_results * 3};"
    )

    try:
        response = _get(
            "https://overpass-api.de/api/interpreter",
            params={"data": overpass_query},
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()

    except Exception:
        return []

    leads: List[Dict] = []
    seen = set()

    for element in data.get("elements", []):
        if len(leads) >= max_results:
            break

        element_tags = element.get("tags", {})

        name = (
            element_tags.get("name")
            or element_tags.get("operator")
            or element_tags.get("brand")
        )

        name = str(name or "").strip()

        if len(name) < 3:
            continue

        key = _normalise_key(name)

        if key in seen:
            continue

        seen.add(key)

        website = (
            element_tags.get("website")
            or element_tags.get("contact:website")
            or element_tags.get("url")
            or ""
        )

        phone = (
            element_tags.get("phone")
            or element_tags.get("contact:phone")
            or ""
        )

        email = (
            element_tags.get("contact:email")
            or element_tags.get("email")
            or ""
        )

        city = (
            element_tags.get("addr:city")
            or element_tags.get("addr:town")
            or element_tags.get("addr:suburb")
            or location
        )

        domain = _domain_from_url(website)

        if not email:
            if domain:
                email = f"info@{domain}"
            else:
                email = _generated_email(name)

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


# =============================================================================
# ENGINE 2 — DUCKDUCKGO
# =============================================================================

def _duckduckgo_search(
    keyword: str,
    location: str,
    max_results: int
) -> List[Dict]:
    """Search DuckDuckGo Instant Answer API."""
    if max_results <= 0:
        return []

    query = (
        f"{str(keyword).strip()} "
        f"agencies {str(location).strip()}"
    )

    try:
        response = _get(
            "https://api.duckduckgo.com/",
            params={
                "q": query,
                "format": "json",
                "no_html": "1",
                "skip_disambig": "1",
            },
            timeout=15,
        )

        response.raise_for_status()

        data = response.json()

    except Exception:
        return []

    leads: List[Dict] = []
    seen = set()

    topics = list(data.get("RelatedTopics", []))
    topics.extend(data.get("Results", []))

    index = 0

    while index < len(topics) and len(leads) < max_results:
        item = topics[index]
        index += 1

        if not isinstance(item, dict):
            continue

        nested_topics = item.get("Topics")

        if isinstance(nested_topics, list):
            topics.extend(nested_topics)
            continue

        text = (
            item.get("Text", "")
            or item.get("Result", "")
        )

        url = (
            item.get("FirstURL", "")
            or item.get("url", "")
        )

        text = str(text).strip()
        url = str(url).strip()

        if not text or not url:
            continue

        name = (
            text.split(" - ", 1)[0]
            .split(". ", 1)[0]
            .strip()
        )

        if len(name) < 4:
            continue

        key = _normalise_key(name)

        if key in seen:
            continue

        seen.add(key)

        domain = _domain_from_url(url)

        email = (
            f"info@{domain}"
            if domain
            else _generated_email(name)
        )

        leads.append({
            "agency_name": name,
            "location": location,
            "contact_email": email,
            "website": url,
            "phone": "",
            "source": "DuckDuckGo",
            "status": "Prospect",
        })

    return leads


# =============================================================================
# ENGINE 3 — WIKIPEDIA
# =============================================================================

def _wikipedia_search(
    keyword: str,
    location: str,
    max_results: int
) -> List[Dict]:
    """Search Wikipedia's OpenSearch API."""
    if max_results <= 0:
        return []

    query = (
        f"{str(keyword).strip()} "
        f"{str(location).strip()}"
    )

    try:
        response = _get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "opensearch",
                "search": query,
                "limit": str(max_results * 2),
                "namespace": "0",
                "format": "json",
            },
            timeout=10,
        )

        response.raise_for_status()

        data = response.json()

    except Exception:
        return []

    if not isinstance(data, list) or len(data) < 4:
        return []

    titles = data[1]
    urls = data[3]

    leads: List[Dict] = []
    seen = set()

    keyword_words = [
        word
        for word in str(keyword).lower().split()
        if word
    ]

    relevance_words = keyword_words + [
        "detective",
        "invest",
        "agency",
        "security",
        "legal",
    ]

    for name, url in zip(titles, urls):
        if len(leads) >= max_results:
            break

        name = str(name or "").strip()
        url = str(url or "").strip()

        if not name or not url:
            continue

        name_lower = name.lower()

        if not any(
            word in name_lower
            for word in relevance_words
        ):
            continue

        key = _normalise_key(name)

        if key in seen:
            continue

        seen.add(key)

        leads.append({
            "agency_name": name,
            "location": location,
            "contact_email": _generated_email(name),
            "website": url,
            "phone": "",
            "source": "Wikipedia",
            "status": "Prospect",
        })

    return leads


# =============================================================================
# ENGINE 4 — DETERMINISTIC FALLBACK
# =============================================================================

_AGENCY_SUFFIXES = [
    "Detective Agency",
    "Investigation Services",
    "Private Investigators",
    "Security Solutions",
    "Intellect Detectives",
    "Inquiry Bureau",
    "Surveillance Experts",
    "Probe Detective Services",
    "Field Investigations",
    "Eagle Eye Detectives",
    "Alpha Investigation",
    "Shield Detectives",
    "Nationwide Investigators",
    "Hawk Surveillance",
    "Trustworthy Detectives",
    "Guardian Investigation",
    "Precision Detectives",
    "City Probe Services",
    "Metro Investigation Bureau",
    "Pioneer Detective Agency",
]


def _seed_leads(
    keyword: str,
    location: str,
    max_results: int
) -> List[Dict]:
    """Generate deterministic fallback leads."""
    if max_results <= 0:
        return []

    location_clean = str(location or "").replace(
        ",",
        " "
    ).strip()

    location_words = location_clean.split()

    location_short = (
        location_words[0]
        if location_words
        else "Local"
    )

    leads: List[Dict] = []
    used = set()

    for suffix in _AGENCY_SUFFIXES:
        if len(leads) >= max_results:
            break

        name = f"{location_short} {suffix}"

        key = _normalise_key(name)

        if key in used:
            continue

        used.add(key)

        leads.append({
            "agency_name": name,
            "location": location,
            "contact_email": _generated_email(name),
            "website": "",
            "phone": "",
            "source": "Generated (Verify Manually)",
            "status": "Prospect",
        })

    return leads


# =============================================================================
# MAIN SCRAPER
# =============================================================================

def scrape_leads_sync(
    keyword: str,
    location: str,
    max_results: int = 20
) -> List[Dict]:
    """Run the lead-discovery waterfall."""
    try:
        max_results = int(max_results)
    except (TypeError, ValueError):
        max_results = 20

    max_results = max(1, min(max_results, 100))

    keyword = str(keyword or "").strip()
    location = str(location or "").strip()

    if not keyword or not location:
        return []

    collected: List[Dict] = []

    # Engine 1: OpenStreetMap / Overpass
    try:
        collected.extend(
            _overpass_search(
                keyword,
                location,
                max_results
            )
        )
    except Exception:
        pass

    # Engine 2: DuckDuckGo
    if len(collected) < max_results:
        try:
            collected.extend(
                _duckduckgo_search(
                    keyword,
                    location,
                    max_results - len(collected)
                )
            )
        except Exception:
            pass

    # Engine 3: Wikipedia
    if len(collected) < max_results:
        try:
            collected.extend(
                _wikipedia_search(
                    keyword,
                    location,
                    max_results - len(collected)
                )
            )
        except Exception:
            pass

    # Engine 4: deterministic fallback
    if len(collected) < max_results:
        try:
            collected.extend(
                _seed_leads(
                    keyword,
                    location,
                    max_results - len(collected)
                )
            )
        except Exception:
            pass

    # Deduplicate
    unique: List[Dict] = []
    seen_keys = set()

    for lead in collected:
        agency_name = str(
            lead.get("agency_name", "")
        ).strip()

        lead_location = str(
            lead.get("location", location)
        ).strip()

        key = (
            _normalise_key(agency_name),
            _normalise_key(lead_location),
        )

        if not agency_name or key in seen_keys:
            continue

        seen_keys.add(key)

        cleaned_lead = {
            "agency_name": agency_name,
            "location": lead_location,
            "contact_email": _safe_email(
                lead.get("contact_email", "")
            ),
            "website": str(
                lead.get("website", "")
            ).strip(),
            "phone": str(
                lead.get("phone", "")
            ).strip(),
            "source": str(
                lead.get("source", "Unknown")
            ).strip(),
            "status": str(
                lead.get("status", "Prospect")
            ).strip(),
        }

        unique.append(cleaned_lead)

        if len(unique) >= max_results:
            break

    # Merge with persistent leads
    existing = load_leads()

    valid_existing = []

    for lead in existing:
        if not isinstance(lead, dict):
            continue

        if not str(
            lead.get("agency_name", "")
        ).strip():
            continue

        valid_existing.append(lead)

    existing_keys = {
        (
            _normalise_key(
                lead.get("agency_name", "")
            ),
            _normalise_key(
                lead.get("location", "")
            ),
        )
        for lead in valid_existing
    }

    merged = list(valid_existing)
    added: List[Dict] = []

    for lead in unique:
        key = (
            _normalise_key(
                lead.get("agency_name", "")
            ),
            _normalise_key(
                lead.get("location", "")
            ),
        )

        if key not in existing_keys:
            merged.append(lead)
            added.append(lead)
            existing_keys.add(key)

    try:
        save_leads(merged)
    except Exception:
        pass

    return added if added else unique


# =============================================================================
# COLD EMAIL ENGINE
# =============================================================================

def send_cold_emails(
    leads: List[Dict],
    app_password: str,
    subject_template: str = COLD_EMAIL_SUBJECT,
    body_template: str = COLD_EMAIL_BODY,
    delay_seconds: int = 5,
    progress_callback: Optional[
        Callable[[int, int, str, str, str], None]
    ] = None,
) -> List[Dict]:
    """Send personalised cold emails using yagmail/Gmail SMTP."""
    results: List[Dict] = []

    if not isinstance(leads, list) or not leads:
        return results

    if not app_password or not str(app_password).strip():
        return [{
            "agency_name": "ALL",
            "status": "INIT_FAIL",
            "error": "Gmail App Password is missing.",
        }]

    try:
        import yagmail
    except ImportError:
        return [{
            "agency_name": "ALL",
            "status": "INIT_FAIL",
            "error": (
                "yagmail is not installed. "
                "Add 'yagmail' to requirements.txt."
            ),
        }]

    try:
        yag = yagmail.SMTP(
            SENDER_EMAIL,
            str(app_password).strip()
        )
    except Exception as exc:
        return [{
            "agency_name": "ALL",
            "status": "INIT_FAIL",
            "error": str(exc),
        }]

    total = len(leads)

    try:
        for index, lead in enumerate(leads, start=1):
            if not isinstance(lead, dict):
                lead = {}

            agency = str(
                lead.get(
                    "agency_name",
                    "Agency"
                )
            ).strip() or "Agency"

            location = str(
                lead.get(
                    "location",
                    "your region"
                )
            ).strip() or "your region"

            recipient = _safe_email(
                lead.get(
                    "contact_email",
                    ""
                )
            )

            # Validate recipient
            if (
                not recipient
                or "@" not in recipient
                or "." not in recipient.rsplit("@", 1)[-1]
            ):
                result = {
                    "agency_name": agency,
                    "recipient": recipient,
                    "status": "SKIPPED",
                    "error": "No valid email address.",
                }
            else:
                try:
                    try:
                        subject = subject_template.format(
                            agency_name=agency,
                            location=location,
                        )
                    except KeyError:
                        subject = subject_template.format(agency_name=agency)

                    try:
                        body = body_template.format(
                            agency_name=agency,
                            location=location,
                        )
                    except KeyError:
                        body = body_template.format(agency_name=agency)

                    yag.send(
                        to=recipient,
                        subject=subject,
                        contents=body,
                    )

                    result = {
                        "agency_name": agency,
                        "recipient": recipient,
                        "status": "SENT",
                        "error": "",
                    }

                except Exception as exc:
                    result = {
                        "agency_name": agency,
                        "recipient": recipient,
                        "status": "FAILED",
                        "error": str(exc),
                    }

            results.append(result)

            # Progress callback
            if progress_callback:
                try:
                    progress_callback(
                        index,
                        total,
                        agency,
                        result["status"],
                        result.get("error", ""),
                    )
                except TypeError:
                    try:
                        progress_callback(
                            index,
                            total,
                            agency,
                            result["status"],
                        )
                    except Exception:
                        pass
                except Exception:
                    pass

            # Delay between emails
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


# =============================================================================
# EXPLICIT PUBLIC API
# =============================================================================

__all__ = [
    "scrape_leads_sync",
    "send_cold_emails",
    "load_leads",
    "save_leads",
    "COLD_EMAIL_SUBJECT",
    "COLD_EMAIL_BODY",
] 
