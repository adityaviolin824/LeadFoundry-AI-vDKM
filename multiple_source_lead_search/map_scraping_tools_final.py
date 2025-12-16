from __future__ import annotations

import sys
import os
import requests
from typing import Any, Dict, List

from dotenv import load_dotenv
from utils.logger import logging
from utils.exception import CustomException

from agents import function_tool

logger = logging.getLogger(__name__)
load_dotenv(override=True)

# -------------------------------------------------------------------------
# ENV VARIABLES
# -------------------------------------------------------------------------

GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
GMAP_API_KEY = os.getenv("GMAP_API_KEY")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

TIMEOUT = 120

# -------------------------------------------------------------------------
# GEOAPIFY GEOCODER
# -------------------------------------------------------------------------

def _geocode(location: str) -> Dict[str, Any]:
    if not GEOAPIFY_API_KEY:
        return {}

    url = "https://api.geoapify.com/v1/geocode/search"
    params = {"text": location, "apiKey": GEOAPIFY_API_KEY, "limit": 1}

    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()

        feats = r.json().get("features", [])
        if not feats:
            return {}

        p = feats[0]["properties"]
        return {
            "lat": p.get("lat"),
            "lon": p.get("lon"),
            "formatted_address": p.get("formatted")
        }

    except Exception as e:
        logger.error("Geocoding failed for location='%s': %s", location, str(e))
        return {}



# -------------------------------------------------------------------------
# SERPAPI LEAD SEARCH (PRIMARY TOOL)
# -------------------------------------------------------------------------

@function_tool
def serpapi_lead_search(
    business_type: str,
    location: str,
    max_results: int = 20
) -> Dict[str, Any]:
    """
    Lead search using SerpAPI Google Maps.
    Optimized for first-pass discovery with contact bias.
    Safe, deterministic, and backward-compatible.
    """

    if not business_type or not location:
        return {"success": False, "error": "business_type and location required"}

    if not SERPAPI_API_KEY:
        return {"success": False, "error": "SERPAPI_API_KEY not configured"}

    # ------------------------------
    # 1. Best-effort geocoding
    # ------------------------------
    geo = _geocode(location)

    # ------------------------------
    # 2. Adaptive zoom (safe heuristic)
    # ------------------------------
    zoom = "11z"  # default city-level
    if geo:
        formatted = (geo.get("formatted_address") or "").lower()
        if any(x in formatted for x in ["india", "state", "province", "region"]):
            zoom = "7z"
        elif any(x in formatted for x in ["district", "county"]):
            zoom = "9z"

    # ------------------------------
    # 3. Entity-biased query framing
    # ------------------------------
    query = business_type.strip().lower()

    params = {
        "engine": "google_maps",
        "q": query,
        "api_key": SERPAPI_API_KEY,
    }

    # Only add ll if geocoding succeeded
    if geo and geo.get("lat") and geo.get("lon"):
        params["ll"] = f"@{geo['lat']},{geo['lon']},{zoom}"

    logger.info(
        "Calling SerpAPI Maps for query='%s' location='%s' zoom='%s'",
        query,
        location,
        zoom,
    )

    try:
        r = requests.get(
            "https://serpapi.com/search.json",
            params=params,
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.error("SerpAPI request failed: %s", str(e))
        return {"success": False, "error": str(e)}

    raw = data.get("local_results") or data.get("place_results") or []
    leads = []

    for p in raw[:max_results]:
        coords = p.get("gps_coordinates", {}) or {}

        phone = p.get("phone")
        website = p.get("website")

        leads.append({
            "name": p.get("title") or p.get("name"),
            "address": p.get("address"),
            "phone": phone,
            "website": website,
            "rating": p.get("rating"),
            "reviews": p.get("reviews"),
            "type": p.get("type"),
            "latitude": coords.get("latitude"),
            "longitude": coords.get("longitude"),

            "has_phone": bool(phone),
            "has_website": bool(website),

            "raw": p,
        })

    if not leads:
        return {"success": False, "error": "No leads found"}

    return {
        "success": True,
        "source": "serpapi",
        "query": query,
        "location_info": geo or {"input_location": location},
        "leads": leads,
        "count": len(leads),
    }







# -------------------------------------------------------------------------
# GMAPS EXTRACTOR LEAD SEARCH (OPTIONAL)
# -------------------------------------------------------------------------

@function_tool
def gmaps_extractor_lead_search(
    business_type: str,
    location: str,
    zoom: int = 11,
    page: int = 1,
    max_results: int = 20
) -> Dict[str, Any]:

    if not business_type or not location:
        return {"success": False, "error": "business_type and location required"}

    if not GMAP_API_KEY:
        return {"success": False, "error": "GMAP_API_KEY not configured"}

    geo = _geocode(location)
    if not geo:
        return {"success": False, "error": f"Could not geocode: {location}"}

    payload = {
        "q": business_type,
        "page": page,
        "ll": f"@{geo['lat']},{geo['lon']},{zoom}z",
        "hl": "en",
        "gl": "in",
        "extra": False,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GMAP_API_KEY}",
    }

    logger.info("Calling GMaps Extractor for '%s' near '%s'", business_type, location)

    try:
        r = requests.post(
            "https://cloud.gmapsextractor.com/api/v2/search",
            headers=headers,
            json=payload,
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.error("GMaps Extractor request failed: %s", str(e))
        return {"success": False, "error": str(e)}

    raw = data.get("data") or data.get("results") or []
    leads = []

    for biz in raw[:max_results]:
        loc = biz.get("geometry", {}).get("location", {})
        leads.append({
            "name": biz.get("name"),
            "address": biz.get("address") or biz.get("formatted_address"),
            "phone": biz.get("phone") or biz.get("phone_number"),
            "website": biz.get("website"),
            "email": biz.get("email"),
            "social_links": biz.get("social_links") or biz.get("social"),
            "place_id": biz.get("place_id"),
            "latitude": loc.get("lat"),
            "longitude": loc.get("lng"),
            "raw": biz,
        })

    if not leads:
        return {"success": False, "error": "No leads found"}

    return {
        "success": True,
        "source": "gmaps_extractor",
        "location_info": geo,
        "leads": leads,
        "count": len(leads),
        "page": page,
    }

# -------------------------------------------------------------------------
# RAPIDAPI BACKUP (LOW PRIORITY)
# -------------------------------------------------------------------------

def _search_rapidapi(query: str, lat: float, lon: float, radius_m: int, max_results: int):
    if not RAPIDAPI_KEY:
        return []

    url = "https://google-maps-extractor2.p.rapidapi.com/search_nearby"
    params = {
        "query": query,
        "lat": lat,
        "lng": lon,
        "language": "en",
        "country": "in",
        "radius": radius_m,
    }

    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "google-maps-extractor2.p.rapidapi.com",
    }

    try:
        r = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.error("RapidAPI request failed: %s", str(e))
        return []

    raw = data.get("data") or data.get("results") or []
    results = []

    for biz in raw[:max_results]:
        loc = biz.get("geometry", {}).get("location", {})
        results.append({
            "name": biz.get("name"),
            "address": biz.get("address") or biz.get("formatted_address"),
            "phone": biz.get("phone") or biz.get("phone_number"),
            "website": biz.get("website"),
            "rating": biz.get("rating"),
            "reviews": biz.get("user_ratings_total") or biz.get("reviews_count"),
            "types": biz.get("types"),
            "place_id": biz.get("place_id"),
            "latitude": loc.get("lat"),
            "longitude": loc.get("lng"),
            "raw": biz,
        })

    return results

@function_tool
def rapidapi_backup_lead_search(
    business_type: str,
    location: str,
    radius_m: int = 5000,
    max_results: int = 20
) -> Dict[str, Any]:

    if not business_type or not location:
        return {"success": False, "error": "business_type and location required"}

    geo = _geocode(location)
    if not geo:
        return {"success": False, "error": f"Could not geocode: {location}"}

    if not RAPIDAPI_KEY:
        return {"success": False, "error": "RAPIDAPI_KEY not configured"}

    logger.info("Calling RapidAPI backup for '%s' near '%s'", business_type, location)

    leads = _search_rapidapi(
        business_type,
        geo["lat"],
        geo["lon"],
        radius_m,
        max_results,
    )

    if not leads:
        return {"success": False, "error": "No leads found"}

    return {
        "success": True,
        "source": "rapidapi_backup",
        "location_info": geo,
        "leads": leads,
        "count": len(leads),
        "radius_m": radius_m,
    }
