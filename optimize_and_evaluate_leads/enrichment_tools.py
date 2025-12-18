import os
import json
import http.client
from typing import Dict, Any
from agents import function_tool
from dotenv import load_dotenv

load_dotenv(override=True)

import requests
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup

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
# Regex patterns
# --------------------------------------------------

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")

# --------------------------------------------------
# Internal fetcher (NOT exposed to agent)
# --------------------------------------------------

def _fetch_html_raw(url: str, timeout: int = 15) -> dict:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "close",
    }

    try:
        r = requests.get(
            url,
            headers=headers,
            timeout=timeout,
            allow_redirects=True,
        )

        if r.status_code in {403, 429, 503}:
            return {"ok": False, "reason": f"blocked_status_{r.status_code}"}

        content_type = r.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type:
            return {"ok": False, "reason": "not_html"}

        html = r.text.strip()
        if len(html) < 1500:
            return {"ok": False, "reason": "html_too_small"}

        return {
            "ok": True,
            "html": html,
            "final_url": r.url,
        }

    except requests.exceptions.Timeout:
        return {"ok": False, "reason": "timeout"}

    except Exception as e:
        return {"ok": False, "reason": f"error:{e}"}

# --------------------------------------------------
# Function tool (agent-facing)
# --------------------------------------------------

@function_tool
def enrich_website_contacts(
    url: str,
) -> dict:
    """
    Deterministic website enrichment tool.
    Fetches a website once, extracts emails, phone numbers,
    important links, and a short text snippet.

    HARD RULES:
    - Called at most once per URL
    - No retries
    - No HTML returned
    - If blocked, returns explicit reason

    Args:
        url: Official company website URL

    Returns:
        dict with extracted contact signals or failure reason
    """

    fetch_result = _fetch_html_raw(url)

    if not fetch_result["ok"]:
        return {
            "ok": False,
            "reason": fetch_result["reason"],
            "source_url": url,
        }

    html = fetch_result["html"]
    final_url = fetch_result["final_url"]
    html_lower = html.lower()

    # -------------------------
    # Extract contacts FIRST
    # -------------------------

    emails = sorted(set(EMAIL_RE.findall(html)))
    phones = sorted(set(PHONE_RE.findall(html)))

    # -------------------------
    # Hard block detection
    # -------------------------

    for kw in HARD_BLOCK_KEYWORDS:
        if kw in html_lower:
            if not (emails or phones):
                return {
                    "ok": False,
                    "reason": f"blocked_keyword:{kw}",
                    "source_url": final_url,
                }

    # -------------------------
    # Cookie wall detection (soft)
    # -------------------------

    cookie_hits = sum(1 for s in COOKIE_SIGNALS if s in html_lower)
    if cookie_hits >= 2 and not (emails or phones):
        return {
            "ok": False,
            "reason": "cookie_wall",
            "source_url": final_url,
        }

    # -------------------------
    # Parse visible content
    # -------------------------

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = " ".join(soup.stripped_strings)
    text = re.sub(r"\s+", " ", text)
    text_snippet = text[:800] if text else "unknown"

    # -------------------------
    # Important internal links
    # -------------------------

    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if any(k in href.lower() for k in ["contact", "about", "impressum"]):
            links.add(urljoin(final_url, href))

    return {
        "ok": True,
        "source_url": final_url,
        "emails": emails or ["unknown"],
        "phones": phones or ["unknown"],
        "important_links": sorted(links) or ["unknown"],
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
