"""
Keeps all LLM instruction strings in one place for easier maintenance,
versioning, and experimentation.
"""

# -------------------------
# LINKEDIN
# -------------------------
LINKEDIN_SEARCH_AGENT_FETCH_INSTRUCTIONS = """
MAX_CALLS=5
Priority: emails and phone numbers are highest priority. Extract explicit contact fields whenever present.

TASK:
- Use up to MAX_CALLS total tool calls. Count every tool call against the budget.
- Search sequence (strict order):
  1) tavily_search(query) up to 2 calls. Allowed forms: "<query> LinkedIn", "<query> official LinkedIn".
     One tavily call must be contact-focused: add tokens "contact phone email contact us".
  2) If needed, use MCP web-search (DuckDuckGo) up to 1 call using "<query> site:linkedin.com/company" or "<query> company LinkedIn".
- Stop when you find 3 distinct organization-level LinkedIn pages that contain explicit email or phone.

EXTRACTION:
- Return ONLY explicitly visible fields, never infer:
  company_name, linkedin_url, headquarters_location, email, phone_number, description, industry, source_urls
- Also return flags: has_email (true/false), has_phone (true/false).
- If a field is missing, return "unknown".

ERRORS:
- If a tool call fails, retry with a different allowed query form until MAX_CALLS exhausted.
- If still no results, return {"results": [], "message":"No LinkedIn pages found"}.

OUTPUT: JSON only
{"results":[{...}]}
"""

# -------------------------
# FACEBOOK 
# -------------------------
FACEBOOK_SEARCH_AGENT_FETCH_INSTRUCTIONS = """
MAX_CALLS=5
Priority: emails and phone numbers are highest priority. Extract explicit contact fields whenever present.

TASK:
- Use up to MAX_CALLS tool calls.
- Search sequence:
  1) tavily_search(query, max_results=25) up to 2 calls. Allowed forms: "<query> Facebook page", "<query> official Facebook".
     One call must be contact-focused: add "contact phone email contact us".
  2) If needed, MCP web-search (DuckDuckGo) up to 1 call: "<query> site:facebook.com" or "<query> Facebook business".
- Stop when you find 3 valid Facebook business pages with explicit email or phone.

EXTRACTION:
- Return ONLY explicitly visible fields:
  business_name, facebook_url, email, phone_number, physical_address, description, source_urls
- Flags: has_email, has_phone
- Missing -> "unknown"

ERRORS:
- On tool failure, retry with alternate allowed query form until MAX_CALLS used.
- If none found, return {"results": [], "message":"No Facebook pages found"}.

OUTPUT: JSON only
{"results":[{...}]}
"""

# -------------------------
# WEBSITE
# -------------------------
WEBSITE_SEARCH_AGENT_FETCH_INSTRUCTIONS = """
MAX_CALLS=5
Priority: emails and phone numbers are highest priority. Extract explicit contact fields whenever present.

TASK:
- Use up to MAX_CALLS tool calls.
- Search sequence:
  1) tavily_search(query) up to 2 calls. Allowed forms: "<query> official website", "<query> company website".
     Reserve one call to include "contact", "contact us", or "phone" tokens.
  2) If needed, MCP web-search (DuckDuckGo) up to 1 call: "<query> contact" or "<query> site:example.com".
- Stop when you have 3 distinct official sites with explicit email or phone.

EXTRACTION:
- Return ONLY explicitly visible fields:
  company_name, website_url, email, phone_number, physical_address, description, services_offered, year_established, source_urls
- Flags: has_email, has_phone, has_website
- Missing -> "unknown"

ERRORS:
- If a tool fails, retry with allowed variation until MAX_CALLS exhausted.
- If none found, return {"results": [], "message":"No official website found"}.

OUTPUT: JSON only
{"results":[{...}]}
"""

# -------------------------
# GMAPS
# -------------------------
GMAP_SEARCH_AGENT_FETCH_INSTRUCTIONS = """
MAX_CALLS=4
Priority: emails and phone numbers are highest priority. Extract explicit contact fields whenever present.

TASK:
- Call serpapi_lead_search(business_type, location) up to MAX_CALLS times. Vary business_type slightly; one call must include tokens "contact phone email".
- Do not artificially limit results returned by the tool.

EXTRACTION:
- Return raw-normalized fields:
  business_name, address, phone_number, website, rating, reviews_count, business_type, coordinates, has_phone, has_website, source_urls
- Missing -> "unknown"

ERRORS:
- If serpapi_lead_search fails, return {"results": [], "error":"<error message>"} and stop.
- If partial results returned, include them and continue other calls until MAX_CALLS used.

OUTPUT: JSON only
{"results":[{...}]}
"""