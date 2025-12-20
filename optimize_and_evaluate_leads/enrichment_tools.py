import os
import json
import random
import re
from typing import Dict, Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from agents import function_tool
from dotenv import load_dotenv

load_dotenv(override=True)

# --------------------------------------------------
# Block detection (HARD blockers only)
# --------------------------------------------------

HARD_BLOCK_KEYWORDS = [
    "cloudflare",
    "attention required",
    "verify you are human",
    "enable javascript",
    "captcha",
    "access denied",
    "temporarily unavailable",
]

COOKIE_SIGNALS = [
    "we use cookies",
    "cookie preferences",
    "manage consent",
    "accept all cookies",
    "cookie settings",
]

# --------------------------------------------------
# Regex patterns (refined)
# --------------------------------------------------
# Keep a permissive email regex then filter obvious false positives.
EMAIL_RE = re.compile(
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}\b'
)
PHONE_RE = re.compile(r"\+?[0-9][0-9\-\s().]{6,}[0-9]")

# --------------------------------------------------
# User agent pool (small randomization)
# --------------------------------------------------
UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# --------------------------------------------------
# Internal fetcher (NOT exposed to agent)
# --------------------------------------------------
def _fetch_html_raw(url: str, timeout: int = 15) -> dict:
    headers = {
        "User-Agent": random.choice(UA_POOL),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "close",
    }

    try:
        r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)

        if r.status_code in {403, 429, 503}:
            return {"ok": False, "reason": f"blocked_status_{r.status_code}"}

        # try to use the best encoding available
        r.encoding = r.apparent_encoding or r.encoding

        content_type = r.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type:
            return {"ok": False, "reason": "not_html"}

        html = (r.text or "").strip()
        # relaxed minimum size threshold
        if len(html) < 500:
            return {"ok": False, "reason": "html_too_small"}

        return {"ok": True, "html": html, "final_url": r.url}

    except requests.exceptions.Timeout:
        return {"ok": False, "reason": "timeout"}

    except Exception as e:
        return {"ok": False, "reason": f"error:{e}"}


# --------------------------------------------------
# Helper validators/normalizers
# --------------------------------------------------
def _filter_emails(raw_emails):
    filtered = set()
    for e in raw_emails:
        e = e.strip()
        # drop obvious image filenames or assets
        if re.search(r'\.(png|jpg|jpeg|svg|gif|webp)$', e, re.I):
            continue
        # drop localhost or single-label domains
        domain = e.split("@")[-1]
        if domain.lower().startswith("localhost") or "." not in domain:
            continue
        filtered.add(e)
    return sorted(filtered)


def _filter_phones(raw_phones):
    norm = set()
    for p in raw_phones:
        digits = re.sub(r"\D", "", p)
        # ignore too short or improbable too long numbers
        if 8 <= len(digits) <= 15:
            # canonicalize: +<country?> if present otherwise digits
            if p.strip().startswith("+"):
                norm.add("+" + digits)
            else:
                norm.add(digits)
    return sorted(norm)


# --------------------------------------------------
# Function tool (agent-facing)
# --------------------------------------------------
@function_tool
def enrich_website_contacts(url: str) -> dict:
    """
    Deterministic website enrichment tool.
    Fetches once, extracts emails, phones, important links, and a short text snippet.

    HARD RULES preserved:
    - Called at most once per URL
    - No retries
    - No raw HTML returned
    - If blocked, returns explicit reason
    """
    fetch_result = _fetch_html_raw(url)
    if not fetch_result.get("ok"):
        return {
            "ok": False,
            "reason": fetch_result.get("reason"),
            "source_url": url,
        }

    html = fetch_result["html"]
    final_url = fetch_result["final_url"]
    html_lower = html.lower()

    # extract raw candidates first
    raw_emails = set(EMAIL_RE.findall(html))
    raw_phones = set(PHONE_RE.findall(html))

    # hard block detection: only treat as hard block if no contacts found
    for kw in HARD_BLOCK_KEYWORDS:
        if kw in html_lower and not (raw_emails or raw_phones):
            return {"ok": False, "reason": f"blocked_keyword:{kw}", "source_url": final_url}

    # cookie wall detection (soft)
    cookie_hits = sum(1 for s in COOKIE_SIGNALS if s in html_lower)
    if cookie_hits >= 2 and not (raw_emails or raw_phones):
        return {"ok": False, "reason": "cookie_wall", "source_url": final_url}

    # parse visible content, prefer main/article if present
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    main_content = soup.find(["main", "article"]) or soup
    text = " ".join(main_content.stripped_strings)
    text = re.sub(r"\s+", " ", text).strip()
    text_snippet = text[:800] if text else "unknown"

    # important internal links expanded
    link_keywords = [
        "contact", "contact-us", "about", "impressum",
        "team", "leadership", "press", "media", "career", "careers", "privacy", "terms"
    ]
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        href_l = href.lower()
        if any(k in href_l for k in link_keywords):
            try:
                links.add(urljoin(final_url, href))
            except Exception:
                continue

    # filter and normalize contacts
    emails = _filter_emails(raw_emails)
    phones = _filter_phones(raw_phones)

    return {
        "ok": True,
        "source_url": final_url,
        "emails": emails,            # empty list if none
        "phones": phones,            # empty list if none
        "email_count": len(emails),
        "phone_count": len(phones),
        "important_links": sorted(links),
        "text_snippet": text_snippet,
        "has_email": bool(emails),
        "has_phone": bool(phones),
    }





# RAPIDAPI_API_KEY = os.getenv("RAPIDAPI_KEY")
# DOES NOT WORK ANYMORE

# @function_tool
# def linkedin_profile_fetch(profile_url: str) -> Dict[str, Any]:
#     """
#     Fetch public LinkedIn profile data using RapidAPI.
#     """
#     if not RAPIDAPI_API_KEY:
#         return {
#             "success": False,
#             "error": "RAPIDAPI_API_KEY not configured"
#         }
#     if not profile_url:
#         return {
#             "success": False,
#             "error": "profile_url is required"
#         }
#     try:
#         conn = http.client.HTTPSConnection("linkedin-data-api.p.rapidapi.com")

#         headers = {
#             "x-rapidapi-key": RAPIDAPI_API_KEY,
#             "x-rapidapi-host": "linkedin-data-api.p.rapidapi.com",
#         }
#         encoded_url = profile_url.replace(":", "%3A").replace("/", "%2F")
#         endpoint = f"/get-profile-data-by-url?url={encoded_url}"
#         conn.request("GET", endpoint, headers=headers)
#         res = conn.getresponse()
#         raw_data = res.read().decode("utf-8")
#         try:
#             data = json.loads(raw_data)
#         except json.JSONDecodeError:
#             return {
#                 "success": False,
#                 "error": "Invalid JSON response from RapidAPI",
#                 "raw_response": raw_data,
#             }
#         return {
#             "success": True,
#             "source": "rapidapi_linkedin",
#             "data": data,
#         }
#     except Exception as e:
#         return {
#             "success": False,
#             "error": str(e),
#         }
