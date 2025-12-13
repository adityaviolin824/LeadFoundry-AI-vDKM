from pydantic import BaseModel, Field, model_validator
from typing import List
from agents import Agent, AgentOutputSchema
from dotenv import load_dotenv

load_dotenv(override=True)

# ============================================================
# Configuration <<<NUMBER CAN SEVERELY AFFECT RUNTIME>>>
# ============================================================
QUERY_COUNT = 2
# ============================================================


instructions = f"""
You generate {QUERY_COUNT} simple, broad web search queries from the provided JSON.

Input JSON structure:
- project
- entity_type
- targets: entity_subtype, locations, industries, company_sizes, keywords
- personas: roles, seniority
- constraints
- verification
- seeds

Goal:
Produce concise search queries that collect many potential leads without becoming too specific.

Core rules:
- Output exactly one JSON object matching the schema below and nothing else.
- Return exactly {QUERY_COUNT} queries.
- Never generate more than {QUERY_COUNT} queries.
- Each query must be 3 to 8 meaningful keywords.
- Use plain words only. No quotes, boolean operators, punctuation, or special symbols.
- Prefer lowercase keywords.
- Avoid stopwords like "the", "and", "of".
- Build queries using only these fields:
  - entity_subtype
  - locations
  - industries
  - keywords
  - personas.roles (optional, for one query)
- Keep queries broad enough to generate large search result sets.

Query angle priority (use top ones if QUERY_COUNT is small):
1. entity_subtype + location
2. keyword + location
3. entity_subtype + industry + location
4. role + entity_subtype + location (optional)
5. keyword + entity_subtype + location

If insufficient fields exist, repeat the best available query with slight wording variation
until exactly {QUERY_COUNT} queries are produced.

Output Schema:
{{
  "queries": ["query1", "query2"]
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
