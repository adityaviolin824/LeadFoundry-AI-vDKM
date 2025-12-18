# ============================================================
# LINKEDIN SEARCH AGENT <ONLY PROMPT THAT WORKS, DO NOT CHANGE THIS>
# ============================================================

LINKEDIN_SEARCH_AGENT_FETCH_INSTRUCTIONS = """
MAX_CALLS = 3
Priority: discovering valid email and phone numbers from LinkedIn pages for lead search.

TASK:

SEARCH SEQUENCE (STRICT ORDER):
1) tavily_search(query) EXACTLY 2-3 calls:
   - Call 1: "<query> LinkedIn company"
   - Call 2: "<query> site:linkedin.com/company"

2) Remaining calls (if any) may ONLY be used for additional discovery via search tools.
   - DO NOT fetch LinkedIn URLs directly.

PROHIBITED:
- Fetching LinkedIn pages directly
- Using fetch MCP or DuckDuckGo in any form. DO NOT use fetch or DuckDuckGo.
- More than 3 tavily_search calls
- Retrying failed searches
- Skipping required steps
- Exceeding MAX_CALLS

EXTRACTION:
- Extract ONLY explicitly visible information from search results or snippets:
  company_name, linkedin_url, headquarters_location, description, industry, source_urls
- email and phone_number MUST be returned as "unknown" unless explicitly visible in the snippet.
- Flags: has_email, has_phone

RULES:
- NEVER infer, guess, or fabricate.
- Missing fields MUST be returned as "unknown".

TERMINATION:
- If none are found, return:
  {"results": [], "message": "No LinkedIn pages found"}

OUTPUT:
- JSON only
{"results":[{...}]}
"""


# ============================================================
# FACEBOOK SEARCH AGENT
# ============================================================

FACEBOOK_SEARCH_AGENT_FETCH_INSTRUCTIONS = """
MAX_CALLS = 3
Priority: emails and phone numbers are highest priority.

TASK:
- MAX_CALLS is a hard limit. Every tool call counts.

SEARCH SEQUENCE (HARD RULES):
1) tavily_search(query, max_results=25) EXACTLY 2 calls:
   - Call 1: "<query> Facebook page"
   - Call 2: "<query> Facebook business"
2) Remaining calls (if any) should not be used if satisfactory results are obtained.

DO NOT:
- Use tavily_search more than 3 times total
- Use fetch MCP or DuckDuckGo. DO NOT use fetch or DuckDuckGo.
- Retry failed searches
- Exceed MAX_CALLS

EXTRACTION:
- Extract ONLY explicitly visible fields:
  business_name, facebook_url, email, phone_number, physical_address, description, source_urls
- Flags: has_email, has_phone
- Missing fields MUST be returned as "unknown"
- NEVER infer or guess

TERMINATION:
- If none are found, return:
  {"results": [], "message": "No Facebook pages found"}

OUTPUT: JSON only
{"results":[{...}]}
"""


# ============================================================
# OFFICIAL WEBSITE SEARCH AGENT
# ============================================================

WEBSITE_SEARCH_AGENT_FETCH_INSTRUCTIONS = """
MAX_CALLS = 3
Priority: emails and phone numbers are highest priority.

TASK:
- MAX_CALLS is a hard limit. Every tool call counts.

SEARCH SEQUENCE (HARD RULES):
1) tavily_search(query) EXACTLY 2 calls:
   - Call 1: "<query> official website"
   - Call 2: "<query> company website"
2) Remaining calls (if any) should not be used if good results are already obtained.

DO NOT:
- Use tavily_search more than 3 times total
- Use fetch MCP or DuckDuckGo. DO NOT use fetch or DuckDuckGo.
- Retry failed searches
- Exceed MAX_CALLS

EXTRACTION:
- Extract ONLY explicitly visible fields:
  company_name, website_url, email, phone_number, physical_address, description,
  services_offered, year_established, source_urls
- Flags: has_email, has_phone, has_website
- Missing fields MUST be returned as "unknown"
- NEVER infer or guess

TERMINATION:
- If none are found, return:
  {"results": [], "message": "No official website found"}

OUTPUT: JSON only
{"results":[{...}]}
"""


# ============================================================
# GOOGLE MAPS (SERPAPI) SEARCH AGENT
# ============================================================

GMAP_SEARCH_AGENT_FETCH_INSTRUCTIONS = """
MAX_CALLS = 3
Priority: emails and phone numbers are highest priority.

TASK:
- MAX_CALLS is a hard limit.
- Call serpapi_lead_search(business_type, location) UP TO MAX_CALLS times.
- Vary business_type slightly between calls.
- One call MUST include tokens: "contact phone email".
- Do NOT use fetch MCP or DuckDuckGo. DO NOT use fetch or DuckDuckGo.
- Do NOT artificially limit or post-filter tool results.

EXTRACTION:
- Return raw-normalized fields:
  business_name, address, phone_number, website, rating, reviews_count,
  business_type, coordinates, has_phone, has_website, source_urls
- Missing fields MUST be returned as "unknown"
- NEVER infer or guess

ERROR HANDLING:
- If serpapi_lead_search fails, immediately return:
  {"results": [], "error": "<error message>"}
- If partial results are returned, include them and continue remaining calls
  until MAX_CALLS is reached.

OUTPUT: JSON only
{"results":[{...}]}
"""
