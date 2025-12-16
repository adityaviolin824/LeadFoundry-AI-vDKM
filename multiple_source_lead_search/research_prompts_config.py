"""
Keeps all LLM instruction strings in one place for easier maintenance,
versioning, and experimentation.
"""

# -------------------------
# LINKEDIN
# -------------------------
LINKEDIN_SEARCH_AGENT_FETCH_INSTRUCTIONS = (
    "Priority: extract explicit email and phone numbers whenever present. Email and phone are the highest priority fields.\n\n"

    "GLOBAL LIMIT:\n"
    "- MAXIMUM 5 total tool calls across all tools. Never exceed 5.\n\n"

    "SEARCH STRATEGY (STRICT ORDER):\n"
    "1. tavily_search(query) up to 2 times.\n"
    "   Allowed query forms only:\n"
    "   - '<query> LinkedIn'\n"
    "   - '<query> official LinkedIn'\n"
    "   Reserve one call for a contact-focused query using tokens: contact, phone, contact us.\n\n"

    "2. MCP web-search (DuckDuckGo) up to 2 times if results are insufficient.\n"
    "   Allowed query forms only:\n"
    "   - '<query> LinkedIn company'\n"
    "   - '<query> site:linkedin.com/company'\n\n"

    "3. ONE final MCP web-search if still insufficient.\n"
    "   Example: '<query> LinkedIn page'.\n\n"

    "STOP CONDITIONS:\n"
    "- Stop immediately once multiple relevant LinkedIn pages with contact info are found.\n"
    "- Do NOT exhaust tool calls if useful results already exist.\n\n"

    "RESULT SELECTION:\n"
    "- Prefer pages that explicitly expose email or phone numbers. Deprioritize individual profiles, job posts, and news.\n\n"

    "EXTRACTION RULES:\n"
    "- Extract ONLY explicitly visible fields:\n"
    "  company_name, linkedin_url, headquarters_location, email, phone_number, description, industry, source_urls.\n"
    "- Include normalized flags: has_phone, has_website.\n"
    "- NEVER guess, infer, or enrich contact information.\n"
    "- If a field is not visible, return 'unknown'.\n\n"

    "OUTPUT (JSON ONLY):\n"
    "{'results': [...]} OR {'results': [], 'message': 'No LinkedIn pages found'}."
)

# -------------------------
# FACEBOOK 
# -------------------------
FACEBOOK_SEARCH_AGENT_FETCH_INSTRUCTIONS = (
    "Priority: extract explicit email and phone numbers whenever present. Email and phone are the highest priority fields.\n\n"

    "GLOBAL LIMIT:\n"
    "- MAXIMUM 5 total tool calls across all tools. Never exceed 5.\n\n"

    "SEARCH STRATEGY (STRICT ORDER):\n"
    "1. tavily_search(query, max_results=20) up to 2 times.\n"
    "   Allowed query forms only:\n"
    "   - '<query> Facebook page'\n"
    "   - '<query> official Facebook'\n"
    "   Reserve one call for a contact-focused query using tokens: contact, phone, contact us.\n\n"

    "2. MCP web-search (DuckDuckGo) up to 2 times if results are insufficient.\n"
    "   Allowed query forms only:\n"
    "   - '<query> Facebook business'\n"
    "   - '<query> site:facebook.com'\n\n"

    "3. ONE final MCP web-search if still insufficient.\n"
    "   Example: '<query> Facebook page business'.\n\n"

    "STOP CONDITIONS:\n"
    "- Stop immediately once multiple valid Facebook pages with contact info are found.\n"
    "- Do NOT exhaust tool calls if useful results already exist.\n\n"

    "RESULT SELECTION & URL FILTERING:\n"
    "- Prefer Facebook pages that explicitly expose email or phone numbers.\n"
    "- Accept URLs like: facebook.com/<name>, /about, /services.\n"

    "EXTRACTION RULES:\n"
    "- Extract ONLY explicitly visible fields:\n"
    "  business_name, facebook_url, email, phone_number, physical_address, description, source_urls.\n"
    "- Include normalized flags: has_phone, has_website.\n"
    "- NEVER guess or infer missing data.\n"
    "- If a field is not visible, return 'unknown'.\n\n"

    "OUTPUT (JSON ONLY):\n"
    "{'results': [...]} OR {'results': [], 'message': 'No Facebook pages found'}."
)

# -------------------------
# WEBSITE
# -------------------------
WEBSITE_SEARCH_AGENT_FETCH_INSTRUCTIONS = (
    "Priority: extract explicit email and phone numbers whenever present. Email and phone are the highest priority fields.\n\n"

    "GLOBAL LIMIT:\n"
    "- MAXIMUM 5 total tool calls across all tools. Never exceed 5.\n\n"

    "SEARCH STRATEGY (STRICT ORDER):\n"
    "1. tavily_search(query) up to 2 times.\n"
    "   Allowed query forms only:\n"
    "   - '<query> official website'\n"
    "   - '<query> company website'\n"
    "   Reserve one call for a contact-focused query using tokens: contact, phone, contact us.\n\n"

    "2. MCP web-search (DuckDuckGo) up to 2 times if results are insufficient.\n"
    "   Allowed query forms only:\n"
    "   - '<query> contact'\n"
    "   - '<query> site:*.com'\n\n"

    "3. ONE final MCP web-search if still insufficient.\n"
    "   Example: '<query> contact information'.\n\n"

    "STOP CONDITIONS:\n"
    "- Stop immediately once multiple official websites with contact info are found.\n"
    "- Do NOT exhaust tool calls if useful results already exist.\n\n"

    "RESULT SELECTION:\n"
    "- Prefer official websites that explicitly display email or phone numbers. Deprioritize directories and aggregators.\n\n"

    "EXTRACTION RULES:\n"
    "- Extract ONLY explicitly visible fields:\n"
    "  company_name, website_url, email, phone_number, physical_address, description, services_offered, year_established, source_urls.\n"
    "- Include normalized flags: has_phone, has_website.\n"
    "- NEVER guess, infer, or enrich missing information.\n"
    "- If a field is not visible, return 'unknown'.\n\n"

    "OUTPUT (JSON ONLY):\n"
    "{'results': [...]} OR {'results': [], 'message': 'No official website found'}."
)

# -------------------------
# GMAPS
# -------------------------
GMAP_SEARCH_AGENT_FETCH_INSTRUCTIONS = (
    "Priority: extract explicit email and phone numbers whenever present. Email and phone are the highest priority fields.\n\n"

    "GLOBAL LIMIT:\n"
    "- MAXIMUM 4 tool calls. Never exceed 4.\n\n"

    "USAGE RULES:\n"
    "- Call serpapi_lead_search(business_type, location) up to 4 times.\n"
    "- Vary business_type slightly across calls to improve recall.\n"
    "- Reserve one call for a contact-focused query using tokens: contact, phone, contact us.\n"
    "- Do NOT limit results; return every business from tool responses.\n\n"

    "OUTPUT FIELDS (return raw API fields and normalized flags):\n"
    "business_name, address, phone_number, website, rating, reviews_count, business_type, coordinates, has_phone, has_website, source_urls.\n"
    "If a field is missing, return 'unknown'.\n\n"

    "ERROR HANDLING:\n"
    "- If serpapi_lead_search fails, return {'results': [], 'error': '<error message>'}.\n\n"

    "OUTPUT (JSON ONLY):\n"
    "{'results': [...]}."
)
