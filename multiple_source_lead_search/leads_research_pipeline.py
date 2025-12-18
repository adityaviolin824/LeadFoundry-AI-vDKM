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


AGENT_TIMEOUT_SECONDS = 240   # 3 minutes

async def run_with_timeout(agent, input_json):
    """
    Runs an agent with a hard timeout.
    If the agent takes more than AGENT_TIMEOUT_SECONDS,
    it is cancelled and a timeout JSON is returned.
    """
    try:
        return await asyncio.wait_for(
            agent.run(input_json),
            timeout=AGENT_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        return {
            "agent": agent.name,
            "status": "timeout",
            "message": f"{agent.name} exceeded {AGENT_TIMEOUT_SECONDS} seconds"
        }



async def common_research_agent_runner(agent: Agent, query: str, trace_name: str) -> Dict[str, Any]:
    try:
        async with AsyncExitStack() as stack:
            connected = [await stack.enter_async_context(s) for s in agent.mcp_servers]
            agent.mcp_servers = connected

            # Apply 3 minute timeout here
            with trace(trace_name):
                research_result = await asyncio.wait_for(
                    Runner.run(agent, query),
                    timeout=AGENT_TIMEOUT_SECONDS
                )

        struct_agent = create_structuring_agent()
        with trace(f"{trace_name}_structurer"):
            struct_run = await Runner.run(struct_agent, research_result.final_output)

        if hasattr(struct_run, "final_output") and struct_run.final_output is not None:
            return struct_run.final_output.model_dump()
        else:
            logger.warning("Structuring agent returned unexpected shape for trace=%s", trace_name)
            return {"error": "structuring_agent_unexpected_shape", "raw": str(struct_run)}

    except asyncio.TimeoutError:
        logger.error("Timeout: %s exceeded %s seconds", trace_name, AGENT_TIMEOUT_SECONDS)
        return {
            "agent": trace_name,
            "status": "timeout",
            "message": f"{trace_name} exceeded {AGENT_TIMEOUT_SECONDS} seconds"
        }

    except Exception as e:
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

####################################################################
async def run_all_agents(query: str, json_path: str) -> None:


    agent_creators = [
        ("linkedin", create_linkedin_search_agent), ################### EXPERIMENTATION
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

    ################## DUMMY FOR EXPERIMENTATION ########################
    # shutil.copy2("dummy/lead_list_consolidated.json", json_path) 
#########################################################################




if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO)


    TEST_QUERY = "drone inspection maharashtra"
    OUTPUT_JSON = "dummy/lead_list_consolidated_experimental.json"

    Path(OUTPUT_JSON).parent.mkdir(parents=True, exist_ok=True)

    logger.info("Starting local LeadFoundry agent run")
    logger.info("Query: %s", TEST_QUERY)
    logger.info("Output: %s", OUTPUT_JSON)

    try:
        run_all_agents_sync(
            query=TEST_QUERY,
            json_path=OUTPUT_JSON,
        )
        logger.info("Local agent run completed successfully")
    except Exception as e:
        logger.exception("Local agent run failed: %s", e)
