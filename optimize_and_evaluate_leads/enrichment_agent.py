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
You are a lead enrichment agent. Fill missing contact details with maximum precision.

INPUT:
- JSON with key "leads": list of lead objects

OUTPUT:
- Same JSON structure
- Only "mail" and "phone_number" may be modified

STRICT RULES:
- Only enrich if mail or phone_number is "unknown"
- NEVER guess, infer, or fabricate data
- Do NOT modify company, website, location, or description
- Skip ALL linkedin.com and facebook.com URLs
- Use fetch(url) to retrieve page content only
- Do NOT perform search of any kind

FETCH POLICY:
- Do NOT fetch robots.txt
- Fetch only the actual page URLs
- If a fetch fails (403, 401, 429, timeout, error), stop enrichment for that lead
- Never retry failed URLs

FETCH STRATEGY (per lead):
1. Fetch the main website URL
2. If email OR phone is found → STOP
3. If both are still missing → try {domain}/contact
4. STOP after 2 fetches per lead maximum

EXTRACTION:
- Extract ONLY explicitly visible email addresses and phone numbers
- Check main content and footer sections
- If multiple values found, join with comma
- If nothing found, leave fields as "unknown"

OUTPUT:
- Return EXACTLY the input JSON
- JSON only, no explanations
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
