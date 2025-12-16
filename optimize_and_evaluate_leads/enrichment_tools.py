import os
import json
import http.client
from typing import Dict, Any
from agents import function_tool
from dotenv import load_dotenv

load_dotenv(override=True)

RAPIDAPI_API_KEY = os.getenv("RAPIDAPI_KEY")

# DOES NOT WORK ANYMORE

@function_tool
def linkedin_profile_fetch(profile_url: str) -> Dict[str, Any]:
    """
    Fetch public LinkedIn profile data using RapidAPI.
    """

    if not RAPIDAPI_API_KEY:
        return {
            "success": False,
            "error": "RAPIDAPI_API_KEY not configured"
        }

    if not profile_url:
        return {
            "success": False,
            "error": "profile_url is required"
        }

    try:
        conn = http.client.HTTPSConnection("linkedin-data-api.p.rapidapi.com")

        headers = {
            "x-rapidapi-key": RAPIDAPI_API_KEY,
            "x-rapidapi-host": "linkedin-data-api.p.rapidapi.com",
        }

        encoded_url = profile_url.replace(":", "%3A").replace("/", "%2F")
        endpoint = f"/get-profile-data-by-url?url={encoded_url}"

        conn.request("GET", endpoint, headers=headers)

        res = conn.getresponse()
        raw_data = res.read().decode("utf-8")

        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError:
            return {
                "success": False,
                "error": "Invalid JSON response from RapidAPI",
                "raw_response": raw_data,
            }

        return {
            "success": True,
            "source": "rapidapi_linkedin",
            "data": data,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
