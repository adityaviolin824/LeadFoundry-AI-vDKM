from pydantic import BaseModel, Field, model_validator
from typing import List
from agents import Agent, AgentOutputSchema
from dotenv import load_dotenv

load_dotenv(override=True)

# ============================================================
# Configuration <<<NUMBER CAN SEVERLY AFFECT RUNTIME>>>>
# ============================================================
QUERY_COUNT = 3 
# ============================================================


instructions = f"""
You generate {QUERY_COUNT} simple, broad DuckDuckGo search queries from the provided JSON.

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
- Return {QUERY_COUNT} queries.
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

Query angles to mix:
1. entity_subtype + location
2. entity_subtype + industry + location
3. keyword + entity_subtype + location
4. role + entity_subtype + location (optional)
5. keyword + location

If some fields are missing, still generate at least 1 query using what is available.

Output Schema:
{{
  "queries": ["query1", "query2", ..., up to {QUERY_COUNT}]
}}
"""


class SearchQueryOutput(BaseModel):
    queries: List[str] = Field(
        ..., 
        description=f"A list of exactly {QUERY_COUNT} simple high-quality DuckDuckGo search queries."
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
