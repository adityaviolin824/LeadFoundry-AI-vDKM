from pydantic import BaseModel, model_validator
from typing import List, Optional, Tuple
from agents import Agent, AgentOutputSchema, Runner, trace
from multiple_source_lead_search.research_tools import researcher_mcp_stdio_servers
from dotenv import load_dotenv
from contextlib import AsyncExitStack
import json

load_dotenv(override=True)


# =========================
# Enrichment Instructions
# =========================

ENRICHMENT_AGENT_INSTRUCTIONS = """
You are a lead enrichment agent. Fill missing contact details with maximum precision.

INPUT: JSON with "leads" array of lead objects
OUTPUT: Same JSON structure with enriched mail and phone_number fields only

STRICT RULES:
- Only enrich if mail or phone_number is "unknown"
- NEVER guess, infer, or fabricate data
- Do NOT modify company, website, location, or description
- Skip ALL linkedin.com and facebook.com URLs entirely
- Use fetch(url) to retrieve page content only - NEVER search

FETCH STRATEGY (per lead):
1. Fetch the main website URL first
2. Extract email and phone from page content
3. If email OR phone found → STOP, move to next lead
4. If both still missing → try {domain}/contact
5. STOP after 2 fetches per lead maximum

EXTRACTION:
- Extract ONLY explicitly visible contact info from fetched HTML
- Look for emails (name@domain.com) and phones (digits + separators)
- Check main content and footer sections
- If multiple values found, join with comma
- If nothing found after 2 fetches, leave as "unknown"

FETCH LIMITS:
- Each URL fetched only ONCE per lead
- Failed fetches (errors, timeouts) still count toward limit
- Never retry failed URLs

OUTPUT:
- Return EXACTLY the input JSON structure
- Only mail and phone_number may change
- JSON only, no explanations or commentary
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


# =========================
# Helper Functions
# =========================

def preprocess_leads(leads: List[Lead]) -> Tuple[List[Lead], List[Lead], List[int]]:
    """
    Separate fetchable vs unfetchable leads.
    
    Returns:
        fetchable: Leads with valid non-social-media websites
        skipped: Leads with LinkedIn/Facebook/unknown websites
        skip_indices: Original indices of skipped leads for order restoration
    """
    fetchable = []
    skipped = []
    skip_indices = []
    
    for idx, lead in enumerate(leads):
        website = lead.website.lower() if lead.website else "unknown"
        
        if lead.website == "unknown":
            skipped.append(lead)
            skip_indices.append(idx)
        elif "linkedin.com" in website or "facebook.com" in website:
            skipped.append(lead)
            skip_indices.append(idx)
        else:
            fetchable.append(lead)
    
    return fetchable, skipped, skip_indices


async def enrich_leads_async(leads: List[Lead], batch_size: int = 10) -> List[Lead]:
    """
    Main async enrichment function with preprocessing and batching.
    Uses Runner.run() with proper MCP server management.
    
    Input: List of Lead objects
    Output: List of Lead objects (same order as input)
    
    Skipped leads (LinkedIn/Facebook/unknown) are returned unchanged.
    """
    if not leads:
        return []
    
    # Separate fetchable from unfetchable leads
    fetchable, skipped, skip_indices = preprocess_leads(leads)
    
    enriched_fetchable = []
    
    # Enrich fetchable leads in batches
    if fetchable:
        agent = create_enrichment_agent()
        
        async with AsyncExitStack() as stack:
            # Initialize MCP servers once for all batches
            if agent.mcp_servers:
                for server in agent.mcp_servers:
                    await stack.enter_async_context(server)
            
            # Process in batches with trace
            with trace("lead_enrichment_batched"):
                for i in range(0, len(fetchable), batch_size):
                    batch = fetchable[i:i + batch_size]
                    
                    # Prepare input message
                    input_data = {"leads": [lead.model_dump() for lead in batch]}
                    input_message = json.dumps(input_data, indent=2)
                    
                    # Use Runner.run() with connected MCP servers
                    result = await Runner.run(
                        agent,
                        [{"role": "user", "content": input_message}],
                        max_turns=100
                    )
                    
                    # Extract enriched leads from result
                    enriched_fetchable.extend(result.final_output.leads)
    
    # Restore original order using index tracking
    result = [None] * len(leads)
    
    # Place skipped leads back in their original positions
    for idx, lead in zip(skip_indices, skipped):
        result[idx] = lead
    
    # Place enriched leads in their original positions
    enriched_idx = 0
    for i in range(len(result)):
        if result[i] is None:
            result[i] = enriched_fetchable[enriched_idx]
            enriched_idx += 1
    
    return result
