import json
import asyncio
from pathlib import Path
from optimize_and_evaluate_leads.enrichment_agent import enrich_leads_async, Lead
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

    # Convert to Lead objects
    leads = [Lead(**lead_dict) for lead_dict in input_data.get("leads", [])]
    
    if not leads:
        logger.warning("No leads to enrich")
        return

    logger.info(f"Starting enrichment for {len(leads)} leads with batching...")

    # Call async batching function
    enriched_leads = await enrich_leads_async(leads)

    # Convert back to dict format
    enriched_output = {
        "leads": [lead.model_dump() for lead in enriched_leads]
    }

    # Save enriched output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(
            enriched_output,
            f,
            indent=2,
            ensure_ascii=False,
        )

    logger.info(f"############## Enriched output saved to {output_path} ##################")


if __name__ == "__main__":
    asyncio.run(
        run_lead_enrichment(
            r"runs/run_20251217T125743_7bac9128/outputs/lead_list_deduped.json",
            r"runs/run_20251217T125743_7bac9128/outputs/lead_list_ENRICHED.json"
        )
    )
