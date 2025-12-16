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
- JSON with key "leads": list of lead objects.

Goal:
Fill missing contact details with maximum accuracy.

ABSOLUTE RULES:
- Only update fields: mail, phone_number.
- If a field is not explicitly found, keep it as "unknown".
- NEVER guess, infer, or fabricate data.
- Do NOT add, remove, or rename fields.
- JSON output only. No explanations.

WHEN TO ENRICH:
- Attempt enrichment ONLY if mail or phone_number is "unknown".

METHOD:
- Use fetch(url) only. NEVER perform search.
- Fetch static HTML only. Do NOT execute JavaScript.

ROBOTS HANDLING:
- robots.txt fetch is a pre-flight permission check.
- It does NOT count toward the "one fetch per path" limit.
- If robots.txt is unreachable or errors, IGNORE it and proceed.
- If robots.txt is reachable and explicitly disallows crawling, SKIP enrichment for that lead.

FETCH ORDER (stop immediately once data is found):
1. Lead website URL (exact).
2. Same domain paths, one request each:
   /contact
   /contact-us
   /about
   /about-us
   /footer
   /support

LIMITS:
- One fetch per path.
- Do NOT follow links.
- Do NOT retry failures.
- LinkedIn URLs: allow at most ONE LinkedIn fetch, otherwise skip.

EXTRACTION:
- Extract ONLY explicitly visible emails and phone numbers.
- Simple pattern matching only.
- If multiple values found, deduplicate and join with commas.

FAILSAFE:
- If nothing is found, leave the lead unchanged.

OUTPUT:
- Return the exact same JSON structure as input.

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
