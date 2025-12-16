from pydantic import BaseModel, model_validator
from typing import List, Optional
from agents import Agent, AgentOutputSchema
from multiple_source_lead_search.research_tools import researcher_mcp_stdio_servers
# from optimize_and_evaluate_leads.enrichment_tools import linkedin_profile_fetch # discontinued tool (kept for future ideas)
from dotenv import load_dotenv

load_dotenv(override=True)


# =========================
# Enrichment Instructions
# =========================

ENRICHMENT_AGENT_INSTRUCTIONS = """
You are a lead enrichment agent.

Input:
- JSON with key "leads": a list of lead objects.

Goal:
Fill missing contact details with maximum precision and minimum actions.

Strict rules:
- If mail or phone_number is "unknown", attempt enrichment.
- NEVER guess, infer, or fabricate data.
- Modify ONLY mail and phone_number.
- Do NOT add, remove, or rename any fields.

Primary method:
- Use fetch(url) to retrieve page content.
- NEVER perform search of any kind.

Fetch strategy (strict order):
1. If the website is NOT a LinkedIn URL:
   a. Fetch the lead's website URL.
   b. If missing data remains, try these paths on the same domain (if valid):
      - /contact
      - /contact-us
      - /about
      - /about-us
      - /footer
      - /support
   c. Stop immediately once missing data is found.

2. If the website IS a LinkedIn URL OR website fetch fails:
   - Call linkedin_profile_fetch(profile_url) exactly once.
   - Extract ONLY explicitly returned email or phone_number fields.
   - If none are present, leave fields unchanged.

Extraction rules:
- Extract ONLY explicitly visible or explicitly returned email addresses and phone numbers.
- Use simple pattern matching (emails like name@domain, phone numbers with digits and separators).
- If multiple values are found, deduplicate and join with comma.
- If no valid data is found, keep values as "unknown".

Safety:
- If all allowed methods fail, leave the lead unchanged.
- Do NOT retry failed methods.
- Do NOT exceed one LinkedIn API call per lead.

Output:
- Return EXACTLY the same JSON structure as input.
- JSON only. No explanations.
"""




# =========================
# Models
# =========================

class Lead(BaseModel):
    company: str
    website: Optional[str] = "unknown"
    mail: Optional[str] = "unknown"
    phone_number: Optional[str] = "unknown"
    location: Optional[str] = "unknown"
    description: Optional[str] = "unknown"


class EnrichmentOutput(BaseModel):
    leads: List[Lead]

    @model_validator(mode="after")
    def validate_leads(self):
        if not isinstance(self.leads, list):
            raise ValueError("leads must be a list")
        return self


# =========================
# MCP servers (FETCH ONLY)
# =========================

ALL_MCP_SERVERS = researcher_mcp_stdio_servers()

FETCH_ONLY_MCP_SERVERS = [
    server for server in ALL_MCP_SERVERS
    if server.name == "fetch_mcp"
]


# =========================
# Agent factory
# =========================

def create_enrichment_agent() -> Agent:
    return Agent(
        name="lead_enrichment_agent",
        model="gpt-4.1-mini",
        instructions=ENRICHMENT_AGENT_INSTRUCTIONS,
        output_type=AgentOutputSchema(
            output_type=EnrichmentOutput,
            strict_json_schema=True,
        ),
        mcp_servers=FETCH_ONLY_MCP_SERVERS,
    )
