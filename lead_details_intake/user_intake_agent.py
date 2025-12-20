from pydantic import BaseModel, Field, model_validator
from typing import List
from agents import Agent, AgentOutputSchema
from dotenv import load_dotenv

load_dotenv(override=True)

# ============================================================
# Configuration <<<NUMBER CAN SEVERELY AFFECT RUNTIME>>>
# ============================================================
QUERY_COUNT = 3
# ============================================================


instructions = f"""
You will produce exactly {QUERY_COUNT} short web/search queries derived from the provided JSON input.

Input JSON fields you may use:
- entity_subtype
- locations
- industries
- keywords
- personas.roles  (optional, use for one query only)

Constraints (strict):
- Output exactly one JSON object and nothing else.
- Return exactly {QUERY_COUNT} queries.
- Each query must be 2 to 7 words long.
- Use plain words only: lowercase, no quotes, no punctuation, no boolean operators, no special symbols.
- Avoid stopwords like "the", "and", "of".
- Prefer terms that work in both general web search and maps (city or region names, entity type, short industry keywords).
- Do not invent locations, roles, or industries not present in input.
- Do not include brand names or emails.

Query construction priority (use top ones first):
1. entity_subtype + location
2. keyword + location
3. entity_subtype + location
4. keyword + entity_subtype + location

Diversify results:
- If you need multiple queries with similar fields, vary the wording using synonyms or reorder words (example: "technical university delhi" vs "delhi technical university").
- For map-style queries prefer explicit place tokens (city, state, region). Example formats: "entitytype city" or "keyword city".

If insufficient fields exist, repeat the best available query with a small, sensible variation until you produce exactly {QUERY_COUNT} queries.

Output schema (strict JSON):
{{
  "queries": ["query1", "query2", ...]
}}

Example input (for reference only):
{{
  "project": "workshop outreach",
  "entity_type": "Academic Institution",
  "targets": {{
    "entity_subtype": "technical university",
    "locations": ["delhi", "gurgaon"],
    "industries": ["education"],
    "keywords": ["engineering workshop", "technical training"]
  }},
  "personas": {{
    "roles": ["principal", "dean"]
  }}
}}

Example valid output:
{{
  "queries": [
    "engineering university delhi",
    "techical workshop mumbai"
  ]
}}
"""




class SearchQueryOutput(BaseModel):
    queries: List[str] = Field(
        ..., 
        description=f"A list of exactly {QUERY_COUNT} simple high-quality web search queries."
    )

    @model_validator(mode="after")
    def ensure_correct_query_count(self):
        if len(self.queries) != QUERY_COUNT:
            raise ValueError(f"Must return exactly {QUERY_COUNT} queries.")
        return self


def create_lead_query_agent() -> Agent:
    return Agent(
        name="lead_query_agent",
        model="gpt-4.1-mini",
        instructions=instructions,
        output_type=AgentOutputSchema(
            output_type=SearchQueryOutput,
            strict_json_schema=True,
        ),
    )
