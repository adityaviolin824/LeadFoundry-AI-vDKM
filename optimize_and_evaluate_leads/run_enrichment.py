import json
import asyncio
from pathlib import Path
from agents import Runner, trace
from optimize_and_evaluate_leads.enrichment_agent import create_enrichment_agent
from contextlib import AsyncExitStack
from utils.logger import logging
logger = logging.getLogger(__name__)


async def run_lead_enrichment(
    input_json_path: str,
    output_json_path: str,
) -> None:
    input_path = Path(input_json_path)
    output_path = Path(output_json_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input JSON not found: {input_path}")

    with input_path.open("r", encoding="utf-8") as f:
        input_data = json.load(f)

    agent = create_enrichment_agent()

    async with AsyncExitStack() as stack:
        if agent.mcp_servers:
            for server in agent.mcp_servers:
                await stack.enter_async_context(server)

        with trace("lead_enrichment_agent"):
            logger.info("Sending leads JSON to enrichment model...")
            input_message = json.dumps(input_data, indent=2)

            result = await Runner.run(
                agent,
                [{"role": "user", "content": input_message}],
            )

        enriched_output = result.final_output
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w", encoding="utf-8") as f:
            json.dump(
                enriched_output.model_dump(),
                f,
                indent=2,
                ensure_ascii=False,
            )

    logger.info(f"############## Enriched output saved to {output_path} ##################")

