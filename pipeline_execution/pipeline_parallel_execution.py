import uuid
import logging
import os
import asyncio
import inspect
import time
from pathlib import Path
from typing import Dict, Any, Optional, Callable
import threading

from utils.send_excel_on_email import send_lead_notification

# =========================
# Engine imports (pipeline primitives)
# =========================
from pipeline_execution.full_pipeline import (
    PipelineConfig,
    PipelineMetrics,
    run_user_intake_stage,
    run_research_from_queries,
    run_deduplication,
    run_sorting,
    run_export_to_excel,
    write_json_atomic,
    run_enrichment_stage
)

# =========================
# Logging
# =========================
logger = logging.getLogger("leadfoundry_api")
logging.basicConfig(level=logging.INFO)

# =========================
# Global shared state
# =========================
RUNS: Dict[str, Dict[str, Any]] = {}
_RUNS_LOCK = asyncio.Lock()

MAX_CONCURRENT_RUNS = 5
_PIPELINE_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_RUNS)

# =========================
# Helpers (internal)
# =========================
def _make_run_folder(base_dir: str = "runs", prefix: str = "run_") -> Path:
    ts = time.strftime("%Y%m%dT%H%M%S")
    rid = uuid.uuid4().hex[:8]
    run_dir = Path(base_dir) / f"{prefix}{ts}_{rid}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "inputs").mkdir(parents=True, exist_ok=True)
    (run_dir / "outputs").mkdir(parents=True, exist_ok=True)
    return run_dir


def _create_cancel_event() -> threading.Event:
    return threading.Event()


def _is_coro(fn: Callable) -> bool:
    return inspect.iscoroutinefunction(fn)


def _maybe_awaitable_call(fn: Callable, /, *args, **kwargs):
    if _is_coro(fn):
        return fn(*args, **kwargs)
    return asyncio.to_thread(fn, *args, **kwargs)


async def _safe_get_run(run_id: str) -> Optional[Dict[str, Any]]:
    async with _RUNS_LOCK:
        return dict(RUNS.get(run_id)) if run_id in RUNS else None


async def safe_update_run(run_id: str, **kwargs) -> None:
    async with _RUNS_LOCK:
        if run_id in RUNS:
            RUNS[run_id].update(kwargs)

# =========================
# Progress writer
# =========================
def _write_progress_sync(run_dir: str, stage: str, info: dict) -> None:
    out = Path(run_dir) / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    write_json_atomic(
        {"stage": stage, "info": info},
        out / f"progress_{stage}.json",
        make_backup=False,
    )


async def _write_progress(run_dir: str, stage: str, info: dict) -> None:
    await asyncio.to_thread(_write_progress_sync, run_dir, stage, info)

# =========================
# Run creation
# =========================
def create_run_records(user_input_filename: str) -> Dict[str, Any]:
    run_dir = _make_run_folder()
    (Path(run_dir) / ".pipeline.lock").write_text(str(os.getpid()))

    cfg = PipelineConfig(
        user_input_path=str(run_dir / "inputs" / user_input_filename),
        suggested_queries_path=str(run_dir / "outputs" / "suggested_queries.json"),
        consolidated_path=str(run_dir / "outputs" / "lead_list_consolidated.json"),
        deduped_path=str(run_dir / "outputs" / "lead_list_deduped.json"),
        enriched_path=str(run_dir / "outputs" / "lead_list_enriched.json"),
        sorted_path=str(run_dir / "outputs" / "lead_list_sorted.json"),
        excel_out_path=str(run_dir / "outputs" / "final_leads_list.xlsx"),
        metrics_path=str(run_dir / "outputs" / "pipeline_metrics.json"),
    )

    logger.info("########## RUN CREATED ##########")
    logger.info("Run directory: %s", run_dir)
    logger.info("#################################")

    return {
        "run_id": None,
        "run_dir": str(run_dir),
        "config": cfg,
        "metrics": PipelineMetrics(),
        "cancel_event": _create_cancel_event(),
        "task": None,

        "status": "created",
        "phase": "intake",
        "execution_mode": None,

        "error": None,
        "email_sent": False,
        "email_sent_to": None,
        "email_error": None,
    }

# =========================
# Async stage runners
# =========================
async def async_run_intake(run_id: str) -> None:
    meta = await _safe_get_run(run_id)
    if not meta:
        return

    logger.info("########## INTAKE STARTED ########## [run=%s]", run_id)

    cfg = meta["config"]
    cfg.cancellation_token = meta["cancel_event"]

    await safe_update_run(run_id, status="intake_running", phase="intake")
    await _write_progress(meta["run_dir"], "intake", {"status": "started"})

    try:
        await _maybe_awaitable_call(run_user_intake_stage, cfg, meta["metrics"])

        await safe_update_run(run_id, status="intake_completed", phase="research")
        await _write_progress(meta["run_dir"], "intake", {"status": "completed"})

        logger.info("########## INTAKE COMPLETED ########## [run=%s]", run_id)

    except Exception as e:
        await safe_update_run(run_id, status="intake_failed", error=str(e))
        logger.exception("########## INTAKE FAILED ########## [run=%s]", run_id)


async def async_run_research(run_id: str) -> None:
    meta = await _safe_get_run(run_id)
    if not meta:
        return

    logger.info("########## RESEARCH STARTED ########## [run=%s]", run_id)

    cfg = meta["config"]
    cfg.cancellation_token = meta["cancel_event"]

    await safe_update_run(run_id, status="research_running", phase="research")
    await _write_progress(meta["run_dir"], "research", {"status": "started"})

    try:
        await _maybe_awaitable_call(
            run_research_from_queries,
            cfg,
            meta["metrics"],
            run_dir=Path(meta["run_dir"]),
        )

        await safe_update_run(run_id, status="research_completed", phase="research_done")
        await _write_progress(meta["run_dir"], "research", {"status": "completed"})

        logger.info("########## RESEARCH COMPLETED ########## [run=%s]", run_id)

    except Exception as e:
        await safe_update_run(run_id, status="research_failed", error=str(e))
        logger.exception("########## RESEARCH FAILED ########## [run=%s]", run_id)
        return

    if meta.get("execution_mode") == "email":
        logger.info("########## AUTO-FINALIZE TRIGGERED ########## [run=%s]", run_id)
        async with _PIPELINE_SEMAPHORE:
            await async_run_finalize(run_id)


async def async_run_finalize(run_id: str) -> None:
    async with _RUNS_LOCK:
        meta = RUNS.get(run_id)
        if not meta:
            return
        if meta.get("phase") == "done":
            logger.info("Finalize already done [run=%s]", run_id)
            return
        if meta.get("phase") == "finalize":
            logger.info("Finalize already running [run=%s]", run_id)
            return
        RUNS[run_id]["phase"] = "finalize"
        RUNS[run_id]["status"] = "finalize_running"
    
    async with _RUNS_LOCK:
        meta = RUNS[run_id]
    
    logger.info("########## FINALIZE STARTED ########## [run=%s]", run_id)
    cfg = meta["config"]
    cfg.cancellation_token = meta["cancel_event"]
    await _write_progress(meta["run_dir"], "finalize", {"status": "started"})
    
    try:
        if meta["cancel_event"].is_set():
            raise Exception("Run cancelled")
        
        await _maybe_awaitable_call(run_deduplication, cfg, meta["metrics"])
        
        await _maybe_awaitable_call(run_enrichment_stage, cfg, meta["metrics"])
        
        await _maybe_awaitable_call(run_sorting, cfg, meta["metrics"])
        
        await _maybe_awaitable_call(run_export_to_excel, cfg, meta["metrics"])
        
        email = meta.get("email")
        if email and not meta.get("email_sent"):
            excel = Path(cfg.excel_out_path)
            if excel.exists():
                try:
                    logger.info("########## EMAIL SENDING ########## [run=%s]", run_id)
                    await asyncio.to_thread(
                        send_lead_notification,
                        email,
                        str(excel),
                    )
                    await safe_update_run(run_id, email_sent=True, email_sent_to=email)
                    logger.info("########## EMAIL SENT ########## [run=%s]", run_id)
                except Exception as email_error:
                    logger.exception("########## EMAIL FAILED ########## [run=%s]", run_id)
                    await safe_update_run(run_id, email_error=str(email_error))
        
        await safe_update_run(run_id, status="finalize_completed", phase="done")
        await _write_progress(meta["run_dir"], "finalize", {"status": "completed"})
        logger.info("########## FINALIZE COMPLETED ########## [run=%s]", run_id)
        
    except Exception as e:
        await safe_update_run(run_id, status="finalize_failed", error=str(e))
        logger.exception("########## FINALIZE FAILED ########## [run=%s]", run_id)