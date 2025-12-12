# final_run_linkedin.py
import asyncio
import json
import tempfile
from contextlib import AsyncExitStack
from pathlib import Path
from typing import List, Dict, Any, Optional
import shutil

from agents import Agent, Runner, trace
from utils.logger import logging
from utils.exception import CustomException

from multiple_source_lead_search.agent_models_and_structure import (
    create_linkedin_search_agent,
    create_facebook_search_agent,
    create_company_website_search_agent,
    create_serpapi_search_agent,
    create_structuring_agent,
)

logger = logging.getLogger(__name__)


async def common_research_agent_runner(agent: Agent, query: str, trace_name: str) -> Dict[str, Any]:
    """
    Run a research agent (with MCP servers connected), then normalize its output
    using the structuring agent. Returns a dict (LeadList.model_dump()).
    Raises CustomException on fatal internal errors.
    """
    try:
        # connect MCP servers
        async with AsyncExitStack() as stack:
            connected = [await stack.enter_async_context(s) for s in agent.mcp_servers]
            agent.mcp_servers = connected

            # run research agent with a named trace
            with trace(trace_name):
                research_result = await Runner.run(agent, query)

        # run structuring agent (no MCP/tools) with its own trace name
        struct_agent = create_structuring_agent()
        with trace(f"{trace_name}_structurer"):
            struct_run = await Runner.run(struct_agent, research_result.final_output)

        # structured final_output should be a parsed LeadList
        if hasattr(struct_run, "final_output") and struct_run.final_output is not None:
            return struct_run.final_output.model_dump()
        else:
            # unexpected shape from structuring agent: return raw wrapper for debugging
            logger.warning("Structuring agent returned unexpected shape for trace=%s", trace_name)
            return {"error": "structuring_agent_unexpected_shape", "raw": str(struct_run)}

    except Exception as e:
        # Wrap and re-raise as CustomException so caller can decide to continue
        logger.exception("Error in common_research_agent_runner trace=%s: %s", trace_name, e)
        raise CustomException(f"Research run failed for trace={trace_name}: {e}") from e


def _extract_leads_from_chunk(chunk: Any) -> List[Dict[str, Any]]:
    """
    Normalize a single chunk returned by an agent into a list of lead dicts.
    Accepted shapes:
    - {"leads": [...]}
    - {"results": [...]}
    - [ {...}, {...} ]
    If the chunk is unexpected, returns an empty list and logs debug info.
    """
    leads: List[Dict[str, Any]] = []
    if not chunk:
        return leads
    if isinstance(chunk, dict):
        if "leads" in chunk and isinstance(chunk["leads"], list):
            leads.extend(chunk["leads"])
            return leads
        if "results" in chunk and isinstance(chunk["results"], list):
            leads.extend(chunk["results"])
            return leads
    if isinstance(chunk, list):
        leads.extend(chunk)
        return leads

    logger.debug("Skipping unexpected lead chunk shape: %s", type(chunk))
    return leads


def consolidate_and_save(all_leads: List[Dict[str, Any]], json_path: str, *, make_backup: bool = True) -> None:
    """
    Merge newly collected lead chunks with existing leads, then save atomically.
    Preserves all existing leads and appends new ones.
    """
    import tempfile
    import shutil

    path = Path(json_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Extract new leads from agent responses
    new_leads: List[Dict[str, Any]] = []
    for chunk in all_leads:
        new_leads.extend(_extract_leads_from_chunk(chunk))

    # Load existing leads if present
    existing_leads: List[Dict[str, Any]] = []
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("leads"), list):
                existing_leads = data["leads"]
            else:
                logger.warning("Existing file %s missing 'leads' list. Ignored.", path)
        except Exception as e:
            logger.warning("Could not parse existing JSON at %s: %s. Starting fresh.", path, e)

    total_existing = len(existing_leads)
    total_new = len(new_leads)
    combined = {"leads": existing_leads + new_leads}

    # Optional backup
    if make_backup and path.exists():
        try:
            backup_path = path.with_suffix(path.suffix + ".bak")
            shutil.copy2(path, backup_path)
            logger.debug("Backup created: %s", backup_path)
        except Exception:
            logger.debug("Backup failed for %s (continuing without backup)", path, exc_info=True)

    # Atomic write
    try:
        with tempfile.NamedTemporaryFile("w", delete=False, dir=str(path.parent), encoding="utf-8") as tf:
            json.dump(combined, tf, indent=2, ensure_ascii=False)
            temp_file = tf.name
        Path(temp_file).replace(path)
        logger.info(
            "Saved consolidated leads: %s (existing=%d new=%d total=%d)",
            path, total_existing, total_new, len(combined["leads"])
        )
    except Exception as e:
        logger.exception("Write failed for %s: %s", path, e)
        raise



def run_all_agents_sync(query: str, json_path: str) -> None:
    asyncio.run(run_all_agents(query, json_path))


async def run_all_agents(query: str, json_path: str) -> None:
    agent_creators = [
        ("linkedin", create_linkedin_search_agent),
        ("facebook", create_facebook_search_agent),
        ("website", create_company_website_search_agent),
        ("gmap", create_serpapi_search_agent),
    ]

    all_leads: List[Dict[str, Any]] = []

    for name, factory in agent_creators:
        trace_name = f"run_{name}_agent"
        try:
            agent = factory()
            structured = await common_research_agent_runner(agent, query, trace_name)
            all_leads.append(structured)
            logger.info(
                "Agent %s completed: collected %d leads",
                name,
                len(structured.get("leads", [])) if isinstance(structured, dict) else 0,
            )
        except CustomException as ce:
            logger.error("Agent %s failed with CustomException: %s", name, ce)
            all_leads.append({"agent": name, "error": str(ce)})
        except Exception as e:
            logger.exception("Agent %s unexpected error: %s", name, e)
            all_leads.append({"agent": name, "error": str(e)})

    consolidate_and_save(all_leads, json_path)
