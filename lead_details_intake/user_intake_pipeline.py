import asyncio
import json
import os
import traceback
from typing import Dict, Any

from agents import Runner, trace
from lead_details_intake.user_intake_agent import create_lead_query_agent
from dotenv import load_dotenv

from utils.logger import logging
from utils.exception import CustomException

load_dotenv(override=True)

logger = logging.getLogger(__name__)


def _ensure_dir_for_path(path: str) -> None:
    dirpath = os.path.dirname(path)
    if dirpath and not os.path.exists(dirpath):
        os.makedirs(dirpath, exist_ok=True)


async def run_user_intake_pipeline(
    user_input: Dict,
    output_path: str = "outputs/suggested_queries.json"
) -> None:
    agent = create_lead_query_agent()

    logger.info("Starting user intake pipeline.")
    logger.info("Output will be saved to: %s", output_path)

    try:
        with trace("lead_query_generator"):
            logger.info("Sending user JSON to model...")
            input_message = json.dumps(user_input, indent=2)
            result = await Runner.run(agent, [{"role": "user", "content": input_message}])

        logger.info("Model returned response successfully.")
        logger.debug("RAW MODEL OUTPUT:\n%s", result)

        _ensure_dir_for_path(output_path)

        actual_model = result.final_output

        if hasattr(actual_model, "model_dump"):
            data_to_save = actual_model.model_dump()
        elif hasattr(actual_model, "dict"):
            data_to_save = actual_model.dict()
        else:
            data_to_save = actual_model

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, indent=2, ensure_ascii=False)

        logger.info("Success. Suggested queries saved to %s", output_path)

    except Exception as exc:
        logger.exception("Error occurred in user intake pipeline: %s", exc)

        err_payload: Dict[str, Any] = {
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "traceback": traceback.format_exc()
        }

        _ensure_dir_for_path(output_path)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(err_payload, f, indent=2, ensure_ascii=False)

        logger.error("Error details written to %s", output_path)

        raise CustomException(f"User intake pipeline failed: {exc}") from exc
