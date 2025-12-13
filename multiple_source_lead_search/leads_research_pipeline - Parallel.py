# final_run_linkedin.py
import asyncio
import json
from contextlib import AsyncExitStack
from pathlib import Path
from typing import List, Dict, Any
import tempfile
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


# ---------------------------------------------------------------------
# Core agent runner (research + structuring)
# ---------------------------------------------------------------------
async def common_research_agent_runner(
    agent: Agent,
    query: str,
    trace_name: str,
) -> Dict[str, Any]:
    """
    Runs:
    - research agent (with MCP servers)
    - structuring agent (post-processing)

    Returns a structured dict or raises CustomException on fatal failure.
    """
    try:
        async with AsyncExitStack() as stack:
            # connect MCP servers for this agent instance
            connected = [await stack.enter_async_context(s) for s in agent.mcp_servers]
            agent.mcp_servers = connected

            # run research agent
            with trace(trace_name):
                research_result = await Runner.run(agent, query)

        # run structuring agent (no MCP/tools)
        struct_agent = create_structuring_agent()
        with trace(f"{trace_name}_structurer"):
            struct_run = await Runner.run(
                struct_agent,
                research_result.final_output,
            )

        if hasattr(struct_run, "final_output") and struct_run.final_output is not None:
            return struct_run.final_output.model_dump()

        logger.warning(
            "Structuring agent returned unexpected shape for trace=%s",
            trace_name,
        )
        return {
            "agent": trace_name,
            "error": "structuring_agent_unexpected_shape",
            "leads": [],
        }

    except Exception as e:
        logger.exception(
            "Error in common_research_agent_runner trace=%s: %s",
            trace_name,
            e,
        )
        raise CustomException(
            f"Research run failed for trace={trace_name}: {e}"
        ) from e


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _extract_leads_from_chunk(chunk: Any) -> List[Dict[str, Any]]:
    """
    Normalize a single agent output into a list of leads.
    """
    if not chunk:
        return []

    if isinstance(chunk, dict):
        if isinstance(chunk.get("leads"), list):
            return chunk["leads"]
        if isinstance(chunk.get("results"), list):
            return chunk["results"]

    if isinstance(chunk, list):
        return chunk

    logger.debug("Skipping unexpected lead chunk shape: %s", type(chunk))
    return []


def consolidate_and_save(
    all_leads: List[Dict[str, Any]],
    json_path: str,
    *,
    make_backup: bool = True,
) -> None:
    """
    Append new leads to existing JSON atomically.
    """
    path = Path(json_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # extract new leads
    new_leads: List[Dict[str, Any]] = []
    for chunk in all_leads:
        new_leads.extend(_extract_leads_from_chunk(chunk))

    # load existing leads
    existing_leads: List[Dict[str, Any]] = []
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("leads"), list):
                existing_leads = data["leads"]
        except Exception as e:
            logger.warning(
                "Could not parse existing JSON at %s: %s. Starting fresh.",
                path,
                e,
            )

    combined = {"leads": existing_leads + new_leads}

    # optional backup
    if make_backup and path.exists():
        try:
            shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        except Exception:
            logger.debug("Backup failed for %s", path, exc_info=True)

    # atomic write
    with tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        dir=str(path.parent),
        encoding="utf-8",
    ) as tf:
        json.dump(combined, tf, indent=2, ensure_ascii=False)
        temp_file = tf.name

    Path(temp_file).replace(path)

    logger.info(
        "Saved consolidated leads: %s (existing=%d new=%d total=%d)",
        path,
        len(existing_leads),
        len(new_leads),
        len(combined["leads"]),
    )


# ---------------------------------------------------------------------
# Public entrypoints
# ---------------------------------------------------------------------
def run_all_agents_sync(query: str, json_path: str) -> None:
    asyncio.run(run_all_agents(query, json_path))


async def run_all_agents(query: str, json_path: str) -> None:
    """
    For ONE query:
    - runs all agents in parallel
    - waits for all to finish
    - consolidates results
    """
    agent_creators = [
        ("linkedin", create_linkedin_search_agent),
        ("facebook", create_facebook_search_agent),
        ("website", create_company_website_search_agent),
        ("gmap", create_serpapi_search_agent),
    ]

    # launch all agents in parallel
    tasks: List[tuple[str, asyncio.Task]] = []
    for name, factory in agent_creators:
        agent = factory()
        trace_name = f"run_{name}_agent"
        task = asyncio.create_task(
            common_research_agent_runner(agent, query, trace_name)
        )
        tasks.append((name, task))

    # wait for all agents
    results = await asyncio.gather(
        *(task for _, task in tasks),
        return_exceptions=True,
    )

    # collect results
    all_leads: List[Dict[str, Any]] = []
    for (name, _), result in zip(tasks, results):
        if isinstance(result, Exception):
            logger.error("Agent %s failed: %s", name, result)
            all_leads.append(
                {"agent": name, "error": str(result), "leads": []}
            )
        else:
            logger.info(
                "Agent %s completed: collected %d leads",
                name,
                len(result.get("leads", [])) if isinstance(result, dict) else 0,
            )
            all_leads.append(result)

    consolidate_and_save(all_leads, json_path)
