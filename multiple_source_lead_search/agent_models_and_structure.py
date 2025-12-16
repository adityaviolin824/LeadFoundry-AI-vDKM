"""
Lead search utilities and agent factories.

Organized:
 - imports and env
 - logging
 - constants
 - helpers (url validation, normalization, sanitization)
 - pydantic models
 - research tool defaults (MCP servers + tool groups)
 - OpenAI client + model
 - agent factory functions
 - structuring agent (LLM normalizer)
 - mapping: agent output -> LeadList (no dedupe)
"""
from __future__ import annotations

import os
import re
from typing import Any, List, Dict
from urllib.parse import urlparse, urlunparse

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

from openai import AsyncOpenAI
from agents import Agent, OpenAIChatCompletionsModel, AgentOutputSchema

from multiple_source_lead_search.map_scraping_tools_final import serpapi_lead_search
from multiple_source_lead_search.research_prompts_config import (
    LINKEDIN_SEARCH_AGENT_FETCH_INSTRUCTIONS,
    FACEBOOK_SEARCH_AGENT_FETCH_INSTRUCTIONS,
    WEBSITE_SEARCH_AGENT_FETCH_INSTRUCTIONS,
    GMAP_SEARCH_AGENT_FETCH_INSTRUCTIONS,
)
from multiple_source_lead_search.research_tools import tavily_search, researcher_mcp_stdio_servers

from utils.logger import logging
from utils.exception import CustomException


# ---------------------------------------------------------------------
# Load environment and logger
# ---------------------------------------------------------------------
load_dotenv(override=False)
logger = logging.getLogger(__name__)

UNKNOWN = "unknown"

_DOMAIN_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def url_validator(value: Any) -> str:
    try:
        if not value:
            return UNKNOWN

        s = str(value).strip()
        if not s or s.lower() == UNKNOWN:
            return UNKNOWN

        if not s.lower().startswith(("http://", "https://")):
            s = "https://" + s

        parsed = urlparse(s)
        hostname = parsed.hostname
        if not hostname:
            return UNKNOWN
        if " " in hostname:
            return UNKNOWN
        if "." not in hostname:
            return UNKNOWN
        if not _DOMAIN_RE.match(hostname):
            return UNKNOWN

        cleaned = urlunparse(parsed)
        return cleaned.rstrip("/")

    except Exception:
        logger.exception("url_validator failed for value=%r", value)
        return UNKNOWN


def normalize_field(v: Any) -> str:
    if v is None:
        return UNKNOWN
    s = str(v).strip()
    return s if s else UNKNOWN


def sanitize_source_urls(srcs: Any) -> List[str]:
    if not srcs:
        return []
    if isinstance(srcs, str):
        srcs = [srcs]
    out = []
    for s in srcs:
        cleaned = url_validator(s)
        if cleaned != UNKNOWN:
            out.append(cleaned)
    return out


# ---------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------
class Lead(BaseModel):
    company: str
    website: str
    mail: str
    phone_number: str
    location: str
    description: str

    @field_validator("website")
    @classmethod
    def ensure_protocol(cls, v: str) -> str:
        return url_validator(v)


class LeadList(BaseModel):
    leads: List[Lead] = Field(default_factory=list)


# ---------------------------------------------------------------------
# Research tool defaults
# ---------------------------------------------------------------------
try:
    DEFAULT_MCP_SERVERS = researcher_mcp_stdio_servers(
        client_session_timeout_seconds=90 ####
    )
except Exception:
    logger.exception("Failed to initialize MCP servers")
    DEFAULT_MCP_SERVERS = []

LINKEDIN_TOOLS = [tavily_search]
FACEBOOK_TOOLS = [tavily_search]
WEBSITE_TOOLS = [tavily_search]
SERPAPI_TOOLS = [serpapi_lead_search, tavily_search]


# ---------------------------------------------------------------------
# OpenAI model client
# ---------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY")

try:
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    model = OpenAIChatCompletionsModel(
        model="gpt-4.1-mini",
        openai_client=openai_client,
    )
except Exception:
    logger.exception("Failed initializing OpenAI model")
    raise


# ---------------------------------------------------------------------
# Agent factories
# ---------------------------------------------------------------------
def create_linkedin_search_agent() -> Agent:
    return Agent(
        name="linkedin_research_agent",
        instructions=LINKEDIN_SEARCH_AGENT_FETCH_INSTRUCTIONS,
        model=model,
        mcp_servers=DEFAULT_MCP_SERVERS,
        tools=LINKEDIN_TOOLS,
    )


def create_facebook_search_agent() -> Agent:
    return Agent(
        name="facebook_research_agent",
        instructions=FACEBOOK_SEARCH_AGENT_FETCH_INSTRUCTIONS,
        model=model,
        mcp_servers=DEFAULT_MCP_SERVERS,
        tools=FACEBOOK_TOOLS,
    )


def create_company_website_search_agent() -> Agent:
    return Agent(
        name="company_website_research_agent",
        instructions=WEBSITE_SEARCH_AGENT_FETCH_INSTRUCTIONS,
        model=model,
        mcp_servers=DEFAULT_MCP_SERVERS,
        tools=WEBSITE_TOOLS,
    )


def create_serpapi_search_agent() -> Agent:
    return Agent(
        name="serpapi_lead_agent",
        instructions=GMAP_SEARCH_AGENT_FETCH_INSTRUCTIONS,
        model=model,
        mcp_servers=DEFAULT_MCP_SERVERS,
        tools=SERPAPI_TOOLS,
    )


# ---------------------------------------------------------------------
# Structuring agent (LLM normalizer)
# ---------------------------------------------------------------------
def create_structuring_agent() -> Agent:
    return Agent(
        name="lead_structuring_agent",
        model="gpt-4.1-mini",
        mcp_servers=[],     # no MCP for normalizer
        tools=[],           # no external tools
        instructions="""
Normalize raw lead data into LeadList JSON.

Rules:
- Extract every distinct COMPANY explicitly present.
- Ignore ads, UI labels, navigation text, or generic directories.
- Extract email and phone aggressively, but ONLY if explicitly shown.
- Never guess or infer values.
- Missing values → "unknown".
- If no website exists, LinkedIn URL may be used as website.
- Collect all referenced links in source_urls.
- One object per company.

Output:
- Return ONLY valid JSON.
- Must match LeadList schema exactly.
- No markdown, no text outside JSON.

Schema:
{
  "leads": [
    {
      "company": "...",
      "website": "...",
      "mail": "...",
      "phone_number": "...",
      "location": "...",
      "description": "...",
      "source_urls": []
    }
  ]
}

""",
        output_type=AgentOutputSchema(
            LeadList,
            strict_json_schema=False,
        ),
    )
