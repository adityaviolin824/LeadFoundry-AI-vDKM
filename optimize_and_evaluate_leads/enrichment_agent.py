from pydantic import BaseModel, model_validator
from typing import List, Optional
from agents import Agent, AgentOutputSchema
from multiple_source_lead_search.research_tools import researcher_mcp_stdio_servers
# from optimize_and_evaluate_leads.enrichment_tools import linkedin_profile_fetch # discontinued tool (kept for future ideas)
from optimize_and_evaluate_leads.enrichment_tools import enrich_website_contacts
from dotenv import load_dotenv

load_dotenv(override=True)


# =========================
# Enrichment Instructions
# =========================

ENRICHMENT_AGENT_INSTRUCTIONS = """
You are a lead enrichment agent.

Goal:
Fill missing contact details with high precision and low cost.

Input:
- JSON object with key "leads" containing a list of lead objects

Output:
- Return the exact same JSON structure
- You may modify ONLY:
  - mail
  - phone_number

Rules:
- Enrich only if mail or phone_number is "unknown"
- Never guess, infer, or fabricate
- Never modify company, website, location, description, or any other fields
- Skip all linkedin.com and facebook.com URLs
- Never perform search
- Never retry failed steps
- Never loop or branch

Primary method:
- Use the tool enrich_website_contacts(url)
- This is the default and preferred method
- Call the tool at most once per lead
- Do not request HTML or raw page content

Tool handling:
- If the tool returns ok == true:
  - Use only the returned emails and phones
- If the tool returns ok == false:
  - Stop enrichment for that lead immediately

Fetch MCP (emergency only):
- Use fetch ONLY if the tool cannot be used
- Fetch only the main website URL
- At most one fetch per lead
- Do not fetch subpages
- If fetch fails for any reason, stop enrichment

Extraction:
- Extract only explicitly visible email addresses and phone numbers
- If multiple values exist, join with a comma
- If nothing valid is found, leave fields as "unknown"

Stop immediately if:
- Website is LinkedIn or Facebook
- Tool fails
- Fetch fails
- Both mail and phone_number are already present

Final output:
- Return exactly the input JSON
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
        tools=[enrich_website_contacts]
    )
