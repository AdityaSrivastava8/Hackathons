"""
agent/outreach.py

B2B Lead Scraper + Gmail Cold Email Engine.

Lead sources:
    1. OpenStreetMap / Overpass
    2. DuckDuckGo Instant Answer API
    3. Wikipedia OpenSearch
    4. Generated leads (manual verification only)

Email:
    Gmail SMTP over SSL using a Gmail App Password.

IMPORTANT:
Generated/placeholder leads are NEVER automatically emailed.
Only leads with a real, verified-looking email address can be sent.
"""

import json
import os
import re
import time
import smtplib
import ssl
import urllib.parse
from email.message import EmailMessage
from typing import List, Dict


# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

DATA_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data")
)

LEADS_FILE = os.path.join(DATA_DIR, "leads.json")

SENDER_EMAIL = "yeahboyadi@gmail.com"

APP_URL = (
    "https://ibmhackathon2026-uzj9dxbwnxgkcdffvztpfa.streamlit.app/"
)

COLD_EMAIL_SUBJECT = (
    "25 Free AI Profiling Credits for {agency_name} "
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

{app_url}

If you have any questions or would like a live walkthrough, simply reply to this email.

Best regards,

Aditya Srivastava          |  Akshat Verma
Lead Developer & Founder   |  Co-Founder
yeahboyadi@gmail.com       |  akshat.v2166@gmail.com

Detective Agentic AI
{app_url}
"""


# ══════════════════════════════════════════════════════════════════════════════
# PERSISTENCE
# ══════════════════════════════════════════════════════════════════════════════

def _ensure_data_dir() -> None:
    """Create the data directory when necessary."""
    os.makedirs(DATA_DIR, exist_ok=True)


def load_leads() -> List[Dict]:
    """Load persisted leads from leads.json."""
    _ensure_data_dir()

    if not os.path.exists(LEADS_FILE):
        return []

    try:
        with open(
            LEADS_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            data = json.load(f)

        return data if isinstance(data, list) else []

    except (OSError, json.JSONDecodeError):
        return []


def save_leads(leads: List[Dict]) -> None:
    """Persist leads to leads.json."""
    _ensure_data_dir()

    with open(
        LEADS_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            leads,
            f,
            indent=2,
            ensure_ascii=False
        )


# ══════════════════════════════════════════════════════════════════════════════
# HTTP
# ══════════════════════════════════════════════════════════════════════════════

_STEALTH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "application/json, text/html, "
        "application/xhtml+xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
}


def _get(
    url: str,
    params: dict = None,
    timeout: int = 15
):
    """Perform a GET request with safe defaults."""
    import requests

    return requests.get(
        url,
        params=params,
        headers=_STEALTH_HEADERS,
        timeout=timeout,
        allow_redirects=True,
    )


def _slug(text: str) -> str:
    """Create a simple alphanumeric slug."""
    return re.sub(
        r"[^a-z0-9]",
        "",
        text.lower()
    )


# ══════════════════════════════════════════════════════════════════════════════
# EMAIL VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

_EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$"
)


def _is_valid_email(email: str) -> bool:
    """
    Basic email validation.

    This checks formatting only. It does NOT guarantee that
    the mailbox actually exists.
    """
    if not email:
        return False

    email = email.strip()

    if len(email) > 254:
        return False

    return bool(
        _EMAIL_PATTERN.fullmatch(email)
    )


def _is_generated_lead(lead: Dict) -> bool:
    """
    Generated leads are placeholders and must never be
    automatically emailed.
    """
    source = str(
        lead.get("source", "")
    ).lower()

    return (
        "generated" in source
        or "verify manually" in source
    )


# ══════════════════════════════════════════════════════════════════════════════
# ENGINE 1 — OPENSTREETMAP / OVERPASS
# ══════════════════════════════════════════════════════════════════════════════

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
) -> List[tuple]:
    """Return OSM tag filters for a keyword."""
    kw = keyword.lower()

    for key, tags in _OSM_TAG_MAP.items():
        if key in kw:
            return tags

    return []


def _geocode_location(location: str):
    """Return latitude, longitude and display name."""
    try:
        response = _get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": location,
                "format": "json",
                "limit": 1,
            },
            timeout=10,
        )

        response.raise_for_status()

        data = response.json()

        if data:
            return (
                float(data[0]["lat"]),
                float(data[0]["lon"]),
                data[0].get(
                    "display_name",
                    location
                ),
            )

    except Exception:
        pass

    return None, None, location


def _overpass_search(
    keyword: str,
    location: str,
    max_results: int
) -> List[Dict]:

    """Search OpenStreetMap businesses around a location."""

    lat, lon, _ = _geocode_location(location)

    if lat is None or lon is None:
        return []

    leads = []
    tags = _osm_tags_for_keyword(keyword)

    radius = 25000

    if tags:

        tag_queries = "\n  ".join(
            (
                f'node["{key}"="{value}"]'
                f'(around:{radius},{lat},{lon});\n'
                f'  way["{key}"="{value}"]'
                f'(around:{radius},{lat},{lon});'
            )
            for key, value in tags
        )

    else:

        kw_clean = re.sub(
            r'["\\]',
            "",
            keyword
        )

        # Escape regex-special characters.
        kw_clean = re.escape(kw_clean)

        tag_queries = (
            f'node["name"~"{kw_clean}",i]'
            f'(around:{radius},{lat},{lon});\n'
            f'  way["name"~"{kw_clean}",i]'
            f'(around:{radius},{lat},{lon});'
        )

    overpass_query = f"""
[out:json][timeout:25];
(
  {tag_queries}
);
out center {max_results * 3};
"""

    try:

        response = _get(
            "https://overpass-api.de/api/interpreter",
            params={
                "data": overpass_query
            },
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()

        seen = set()

        for element in data.get(
            "elements",
            []
        ):

            if len(leads) >= max_results:
                break

            tags_el = element.get(
                "tags",
                {}
            )

            name = (
                tags_el.get("name")
                or tags_el.get("operator")
                or tags_el.get("brand")
            )

            if (
                not name
                or name in seen
                or len(name) < 3
            ):
                continue

            seen.add(name)

            website = (
                tags_el.get("website")
                or tags_el.get("contact:website")
                or tags_el.get("url")
                or ""
            )

            phone = (
                tags_el.get("phone")
                or tags_el.get("contact:phone")
                or ""
            )

            city = (
                tags_el.get("addr:city")
                or tags_el.get("addr:suburb")
                or location
            )

            contact_email = (
                tags_el.get("contact:email")
                or tags_el.get("email")
                or ""
            )

            leads.append({
                "agency_name": name,
                "location": city,
                "contact_email": contact_email,
                "website": website,
                "phone": phone,
                "source": "OpenStreetMap",
                "status": "Prospect",
            })

    except Exception:
        return []

    return leads


# ══════════════════════════════════════════════════════════════════════════════
# ENGINE 2 — DUCKDUCKGO
# ══════════════════════════════════════════════════════════════════════════════

def _duckduckgo_search(
    keyword: str,
    location: str,
    max_results: int
) -> List[Dict]:

    """Search DuckDuckGo Instant Answer API."""

    query = f"{keyword} agencies {location}"

    leads = []

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

        topics = list(
            data.get(
                "RelatedTopics",
                []
            )
        )

        topics.extend(
            data.get(
                "Results",
                []
            )
        )

        seen = set()
        index = 0

        while index < len(topics):

            if len(leads) >= max_results:
                break

            item = topics[index]
            index += 1

            if not isinstance(item, dict):
                continue

            nested = item.get("Topics")

            if isinstance(
                nested,
                list
            ):
                topics.extend(nested)
                continue

            text = (
                item.get("Text", "")
                or item.get("Result", "")
            )

            url = (
                item.get("FirstURL", "")
                or item.get("url", "")
            )

            if not text or not url:
                continue

            name = (
                text
                .split(" - ")[0]
                .split(". ")[0]
                .strip()
            )

            if (
                not name
                or name in seen
                or len(name) < 4
            ):
                continue

            seen.add(name)

            leads.append({
                "agency_name": name,
                "location": location,
                "contact_email": "",
                "website": url,
                "source": "DuckDuckGo",
                "status": "Prospect",
            })

    except Exception:
        return []

    return leads


# ══════════════════════════════════════════════════════════════════════════════
# ENGINE 3 — WIKIPEDIA
# ══════════════════════════════════════════════════════════════════════════════

def _wikipedia_search(
    keyword: str,
    location: str,
    max_results: int
) -> List[Dict]:

    """Search Wikipedia OpenSearch for relevant entities."""

    query = f"{keyword} {location}"

    leads = []

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

        if len(data) < 4:
            return []

        titles = data[1]
        urls = data[3]

        seen = set()

        for name, url in zip(
            titles,
            urls
        ):

            if len(leads) >= max_results:
                break

            if (
                not name
                or name in seen
            ):
                continue

            kw_words = (
                keyword.lower().split()
            )

            relevant = any(
                word in name.lower()
                for word in (
                    kw_words
                    + [
                        "detective",
                        "invest",
                        "agency",
                        "security",
                    ]
                )
            )

            if not relevant:
                continue

            seen.add(name)

            leads.append({
                "agency_name": name,
                "location": location,
                "contact_email": "",
                "website": url,
                "source": "Wikipedia",
                "status": "Prospect",
            })

    except Exception:
        return []

    return leads


# ══════════════════════════════════════════════════════════════════════════════
# ENGINE 4 — GENERATED FALLBACK
# ══════════════════════════════════════════════════════════════════════════════

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

    """
    Generate placeholder leads.

    IMPORTANT:
    These leads deliberately have NO email address.
    They require manual verification before outreach.
    """

    loc_clean = location.replace(
        ",",
        ""
    ).strip()

    loc_words = loc_clean.split()

    loc_short = (
        loc_words[0]
        if loc_words
        else "Local"
    )

    leads = []
    used = set()

    for suffix in _AGENCY_SUFFIXES:

        if len(leads) >= max_results:
            break

        name = (
            f"{loc_short} {suffix}"
        )

        if name in used:
            continue

        used.add(name)

        leads.append({
            "agency_name": name,
            "location": location,
            "contact_email": "",
            "website": "",
            "source": "Generated (Verify Manually)",
            "status": "Needs Verification",
        })

    return leads


# ══════════════════════════════════════════════════════════════════════════════
# MAIN SCRAPER
# ══════════════════════════════════════════════════════════════════════════════

def scrape_leads_sync(
    keyword: str,
    location: str,
    max_results: int = 20
) -> List[Dict]:

    """
    Multi-source B2B lead scraper.

    Real sources are tried first. Generated leads are only
    placeholders for manual verification.

    Returns newly-added leads when possible.
    """

    keyword = str(keyword or "").strip()
    location = str(location or "").strip()

    if not keyword or not location:
        return []

    try:
        max_results = max(
            1,
            int(max_results)
        )
    except (TypeError, ValueError):
        max_results = 20

    collected = []

    # ── Engine 1: OpenStreetMap ────────────────────────────────────────────

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

    # ── Engine 2: DuckDuckGo ───────────────────────────────────────────────

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

    # ── Engine 3: Wikipedia ────────────────────────────────────────────────

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

    # ── Engine 4: Manual-verification placeholders ─────────────────────────

    if len(collected) < max_results:

        collected.extend(
            _seed_leads(
                keyword,
                location,
                max_results - len(collected)
            )
        )

    # ── Deduplicate ────────────────────────────────────────────────────────

    seen_keys = set()
    unique = []

    for lead in collected:

        key = (
            str(
                lead.get(
                    "agency_name",
                    ""
                )
            ).strip().lower(),

            str(
                lead.get(
                    "location",
                    ""
                )
            ).strip().lower(),
        )

        if key in seen_keys:
            continue

        seen_keys.add(key)
        unique.append(lead)

        if len(unique) >= max_results:
            break

    # ── Merge into persistent storage ──────────────────────────────────────

    existing = load_leads()

    existing_keys = {
        (
            str(
                lead.get(
                    "agency_name",
                    ""
                )
            ).strip().lower(),

            str(
                lead.get(
                    "location",
                    ""
                )
            ).strip().lower(),
        )
        for lead in existing
    }

    merged = existing[:]
    added = []

    for lead in unique:

        key = (
            str(
                lead.get(
                    "agency_name",
                    ""
                )
            ).strip().lower(),

            str(
                lead.get(
                    "location",
                    ""
                )
            ).strip().lower(),
        )

        if key not in existing_keys:

            merged.append(lead)
            added.append(lead)

            existing_keys.add(key)

    save_leads(merged)

    return added if added else unique


# ════════════════════════════════════ 
