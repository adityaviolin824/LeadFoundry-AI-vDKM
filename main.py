# app_fastapi.py (async-first version) - with email logic fixes
import uuid
import logging
import json
import os
import asyncio
import inspect
import re
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from fastapi import FastAPI, HTTPException
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Body
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import threading
from contextlib import asynccontextmanager
import shutil
from utils.send_excel_on_email import send_lead_notification

logger = logging.getLogger("leadfoundry_api")
logging.basicConfig(level=logging.INFO)

# Async primitives for concurrency control and safe registry access
RUNS: Dict[str, Dict[str, Any]] = {}
_RUNS_LOCK = asyncio.Lock()
MAX_CONCURRENT_RUNS = 5
_PIPELINE_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_RUNS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # runs before the app starts
    logger.info("🚀 LeadFoundry API starting up")
    yield
    # runs after the app stops - shutdown cleanup for run locks
    logger.info("🛑 LeadFoundry API shutting down - cleaning run locks")
    async with _RUNS_LOCK:
        for run_id, meta in RUNS.items():
            try:
                lock = Path(meta["run_dir"]) / ".pipeline.lock"
                if lock.exists():
                    lock.unlink()
                    logger.info("Removed lock for run %s", run_id)
            except Exception:
                logger.exception("Failed to cleanup lock for run %s", run_id)


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


# Import pipeline utilities and stages (no modification to pipeline required)
from full_pipeline import (  # noqa: E402
    PipelineConfig,
    PipelineMetrics,
    _make_run_folder,
    run_user_intake_stage,
    run_research_from_queries,
    run_deduplication,
    run_sorting,
    run_export_to_excel,
    write_json_atomic,
)


# Delete all run folders without a .pipeline.lock
def _cleanup_unlocked_run_folders(base_dir: str = "runs"):
    base = Path(base_dir)
    if not base.exists():
        return

    for folder in base.iterdir():
        if not folder.is_dir():
            continue

        lock = folder / ".pipeline.lock"
        if lock.exists():
            continue

        try:
            shutil.rmtree(folder, ignore_errors=True)
            logger.info("Deleted unlocked run folder: %s", folder)
        except Exception:
            logger.exception("Failed to delete folder %s", folder)


# Utilities
def is_valid_email(email: str) -> bool:
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


async def _safe_write_json_atomic(data: Any, path: Path, **kw):
    """Run write_json_atomic in a thread to avoid blocking event loop."""
    await asyncio.to_thread(write_json_atomic, data, str(path), **kw)


async def _safe_update_run(run_id: str, **kwargs) -> None:
    async with _RUNS_LOCK:
        if run_id in RUNS:
            RUNS[run_id].update(kwargs)


async def _safe_get_run(run_id: str) -> Optional[Dict[str, Any]]:
    async with _RUNS_LOCK:
        return dict(RUNS.get(run_id)) if run_id in RUNS else None


def _create_threading_cancel_event() -> threading.Event:
    return threading.Event()


def _is_coro(fn: Callable) -> bool:
    return inspect.iscoroutinefunction(fn)


def _maybe_awaitable_call(fn: Callable, /, *args, **kwargs):
    """
    If fn is async, return awaitable. If not, run in thread and return awaitable.
    This returns a coroutine object suitable for 'await'.
    """
    if _is_coro(fn):
        return fn(*args, **kwargs)
    return asyncio.to_thread(fn, *args, **kwargs)


def _write_progress_sync(run_dir: str, stage: str, info: dict):
    out_dir = Path(run_dir) / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"progress_{stage}.json"
    try:
        write_json_atomic({"stage": stage, "info": info}, str(p), make_backup=False)
    except Exception:
        logger.exception("Failed to write progress for %s", stage)


async def _write_progress(run_dir: str, stage: str, info: dict):
    await asyncio.to_thread(_write_progress_sync, run_dir, stage, info)


# Create run metadata
def _create_run_records(user_input_path: str, base_run_dir: Optional[str] = None) -> Dict[str, Any]:
    cfg = PipelineConfig()
    if base_run_dir:
        cfg.base_run_dir = base_run_dir

    run_dir = _make_run_folder(cfg.base_run_dir, prefix=cfg.run_name_prefix)

    lock_path = Path(run_dir) / ".pipeline.lock"
    try:
        lock_path.write_text(str(os.getpid()))
    except Exception:
        logger.exception("Could not write initial lock file")

    inputs_dir = Path(run_dir) / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    run_input_path = inputs_dir / user_input_path

    cfg.user_input_path = str(run_input_path)
    cfg.suggested_queries_path = str(Path(run_dir) / "outputs" / "suggested_queries.json")
    cfg.consolidated_path = str(Path(run_dir) / "outputs" / "lead_list_consolidated.json")
    cfg.deduped_path = str(Path(run_dir) / "outputs" / "lead_list_deduped.json")
    cfg.sorted_path = str(Path(run_dir) / "outputs" / "lead_list_sorted.json")
    cfg.excel_out_path = str(Path(run_dir) / "outputs" / "final_leads_list.xlsx")
    cfg.metrics_path = str(Path(run_dir) / "outputs" / "pipeline_metrics.json")

    metrics = PipelineMetrics()
    cancel_event = _create_threading_cancel_event()

    return {
        "run_id": None,
        "run_dir": str(run_dir),
        "config": cfg,
        "metrics": metrics,
        "cancel_event": cancel_event,
        "task": None,
        "status": "created",
        "error": None,
    }


# Async stage runners
async def _async_run_intake(run_id: str):
    meta = await _safe_get_run(run_id)
    if not meta:
        return

    cfg = meta["config"]
    metrics = meta["metrics"]
    cfg.cancellation_token = meta["cancel_event"]

    await _safe_update_run(run_id, status="intake_running")
    await _write_progress(meta["run_dir"], "intake", {"status": "started"})

    try:
        await _maybe_awaitable_call(run_user_intake_stage, cfg, metrics)
        await _safe_update_run(run_id, status="intake_completed")
        await _write_progress(meta["run_dir"], "intake", {"status": "completed"})
    except Exception as e:
        await _safe_update_run(run_id, status="intake_failed", error=str(e))
        logger.exception("Intake failed for run %s", run_id)


async def _async_run_research(run_id: str):
    meta = await _safe_get_run(run_id)
    if not meta:
        return

    cfg = meta["config"]
    metrics = meta["metrics"]
    cfg.cancellation_token = meta["cancel_event"]

    await _safe_update_run(run_id, status="research_running")
    await _write_progress(meta["run_dir"], "research", {"status": "started"})

    # Run research stage
    try:
        await _maybe_awaitable_call(run_research_from_queries, cfg, metrics, run_dir=Path(meta["run_dir"]))
    except Exception as e:
        await _safe_update_run(run_id, status="research_failed", error=str(e))
        logger.exception("Research failed for run %s", run_id)
        return  # Don't proceed to auto-finalization if research failed

    # Research completed successfully
    email = meta.get("email")
    
    if not email:
        # No email - just complete research and stop
        await _safe_update_run(run_id, status="research_completed")
        await _write_progress(meta["run_dir"], "research", {"status": "completed"})
        logger.info("Research completed for run %s (no email provided)", run_id)
        return
    
    # Email is present - mark research complete then continue to finalization
    await _safe_update_run(run_id, status="research_completed")
    await _write_progress(meta["run_dir"], "research", {"status": "completed"})
    logger.info("Research completed for run %s, starting auto-finalization for email delivery to %s", run_id, email)
    
    # Auto-finalize (email will be sent inside finalize stage)
    try:
        async with _PIPELINE_SEMAPHORE:
            await _async_run_finalize(run_id)
    except Exception as finalize_error:
        logger.exception("Auto-finalization failed for run %s", run_id)
        await _safe_update_run(
            run_id, 
            email_sent=False, 
            email_error=f"Finalization error: {str(finalize_error)}"
        )


async def _async_run_finalize(run_id: str):
    meta = await _safe_get_run(run_id)
    if not meta:
        return

    cfg = meta["config"]
    metrics = meta["metrics"]
    cfg.cancellation_token = meta["cancel_event"]

    await _safe_update_run(run_id, status="finalize_running")
    await _write_progress(meta["run_dir"], "finalize", {"status": "started"})

    try:
        # Run finalization pipeline
        await _maybe_awaitable_call(run_deduplication, cfg, metrics)
        await _maybe_awaitable_call(run_sorting, cfg, metrics)
        await _maybe_awaitable_call(run_export_to_excel, cfg, metrics)
        
        await _safe_update_run(run_id, status="finalize_completed")
        await _write_progress(meta["run_dir"], "finalize", {"status": "completed"})
        logger.info("Finalization completed for run %s", run_id)
        
        # ========================================================
        # EMAIL SENDING - MOVED INTO FINALIZE STAGE
        # ========================================================
        email = meta.get("email")
        if email:
            # Check if email already sent (idempotency for duplicate calls)
            if meta.get("email_sent"):
                logger.info("Email already sent for run %s, skipping", run_id)
                return
            
            logger.info("📧 Preparing to send email to %s for run %s", email, run_id)
            
            # Check if Excel file exists
            excel_path = Path(cfg.excel_out_path)
            if not excel_path.exists():
                logger.error("Excel file not found at %s for run %s", excel_path, run_id)
                await _safe_update_run(run_id, email_sent=False, email_error="Excel file not generated")
                return
            
            # Send email
            try:
                logger.info("📧 Sending email to %s with attachment %s", email, excel_path)
                await asyncio.to_thread(
                    send_lead_notification,
                    email,
                    "Your LeadFoundry AI Results",
                    "<p>Your leads are ready. Please find the Excel attached.</p>",
                    str(excel_path),
                )
                logger.info("=" * 70)
                logger.info("✅ Email sent successfully to %s for run %s", email, run_id)
                logger.info("=" * 70)
                await _safe_update_run(run_id, email_sent=True, email_sent_to=email)
                
            except Exception as email_error:
                logger.exception("❌ Failed to send email for run %s to %s", run_id, email)
                await _safe_update_run(
                    run_id, 
                    email_sent=False, 
                    email_error=f"Email delivery failed: {str(email_error)}"
                )
        
    except Exception as e:
        await _safe_update_run(run_id, status="finalize_failed", error=str(e))
        logger.exception("Finalization failed for run %s", run_id)


# API endpoints (async, non-blocking)

@app.post("/runs/full", status_code=201)
async def create_and_start_run(payload: Dict):
    """
    Create a new run, write user_input, clean old runs,
    and automatically start intake.
    """
    run_id = uuid.uuid4().hex
    user_input_filename = "user_input.json"
    meta = _create_run_records(user_input_filename)
    meta["run_id"] = run_id

    # Validate and store email if provided
    email = payload.get("email")
    if email:
        if not is_valid_email(email):
            raise HTTPException(400, "Invalid email format")
        meta["email"] = email
        logger.info("Run %s will send results to email: %s", run_id, email)

    # write input (payload already contains email if provided)
    try:
        await asyncio.to_thread(
            write_json_atomic,
            payload,
            meta["config"].user_input_path,
            False,
            False
        )
    except Exception as e:
        logger.exception("Failed to write user_input for run %s: %s", run_id, e)
        raise HTTPException(500, f"Failed to create run input: {e}")

    # store in memory
    async with _RUNS_LOCK:
        RUNS[run_id] = meta

    # cleanup old runs
    await asyncio.to_thread(_cleanup_unlocked_run_folders)

    # schedule intake
    async def _wrapped():
        async with _PIPELINE_SEMAPHORE:
            await _async_run_intake(run_id)

    task = asyncio.create_task(_wrapped())
    await _safe_update_run(run_id, task=task, status="intake_queued")

    logger.info(
        "Created run %s and queued intake (email=%s)",
        run_id,
        email or "none"
    )

    return {
        "run_id": run_id,
        "status": "intake_queued",
        "run_dir": meta["run_dir"],
        "email_delivery": bool(email),
    }


@app.post("/runs/{run_id}/research", status_code=202)
async def start_research(run_id: str):
    """
    Start the research stage for an existing run.
    """
    meta = await _safe_get_run(run_id)
    if not meta:
        raise HTTPException(404, "run_id not found")

    # optional guard: require intake_completed
    if meta["status"] not in ("intake_completed", "research_failed", "research_queued", "created"):
        logger.info("Starting research from status: %s", meta["status"])

    async def _wrapped():
        async with _PIPELINE_SEMAPHORE:
            await _async_run_research(run_id)

    task = asyncio.create_task(_wrapped())
    await _safe_update_run(run_id, task=task, status="research_queued")
    return {"run_id": run_id, "status": "research_queued"}


@app.get("/runs/{run_id}/status")
async def get_status(run_id: str):
    meta = await _safe_get_run(run_id)
    if not meta:
        raise HTTPException(404, "run_id not found")
    t = meta.get("task")
    info = {
        "run_id": run_id,
        "run_dir": meta["run_dir"],
        "status": meta["status"],
        "error": meta.get("error"),
        # indicate if a task is present and running
        "has_task": bool(t),
        "task_done": t.done() if t else None,
        "task_cancelled": t.cancelled() if t else None,
        # email info
        "email_delivery_enabled": bool(meta.get("email")),
        "email_sent": meta.get("email_sent"),
        "email_sent_to": meta.get("email_sent_to"),
        "email_error": meta.get("email_error"),
    }
    outputs = Path(meta["run_dir"]) / "outputs"
    if outputs.exists():
        info["progress_files"] = [str(p.name) for p in outputs.glob("progress_*.json")]
    return JSONResponse(info)


@app.post("/runs/{run_id}/finalize_full", status_code=202)
async def finalize_full(run_id: str):
    """
    Combined endpoint:
    1. Runs dedupe, sorting, export (finalize stage)
    2. Returns list of output files
    3. Returns Excel file if generated
    """
    meta = await _safe_get_run(run_id)
    if not meta:
        raise HTTPException(404, "run_id not found")

    async def _wrapped():
        async with _PIPELINE_SEMAPHORE:
            await _async_run_finalize(run_id)

    # schedule finalize
    task = asyncio.create_task(_wrapped())
    await _safe_update_run(run_id, task=task, status="finalize_queued")

    # await completion
    try:
        await task
    except asyncio.CancelledError:
        raise HTTPException(500, "finalize cancelled")

    # refresh metadata
    meta = await _safe_get_run(run_id)

    # collect outputs
    outputs_dir = Path(meta["run_dir"]) / "outputs"
    output_files = []
    if outputs_dir.exists():
        output_files = [
            str(p.relative_to(meta["run_dir"]))
            for p in outputs_dir.rglob("*") if p.is_file()
        ]

    # check excel
    excel_path = outputs_dir / "final_leads_list.xlsx"
    excel_available = excel_path.exists()

    return {
        "run_id": run_id,
        "status": meta["status"],
        "error": meta.get("error"),
        "outputs": output_files,
        "excel_available": excel_available,
    }


@app.get("/runs/{run_id}/finalize_full/download_excel")
async def finalize_full_download_excel(run_id: str):
    """
    Companion endpoint for downloading Excel after finalize_full response indicates availability.
    """
    meta = await _safe_get_run(run_id)
    if not meta:
        raise HTTPException(404, "run_id not found")

    excel = Path(meta["run_dir"]) / "outputs" / "final_leads_list.xlsx"
    if not excel.exists():
        raise HTTPException(404, "excel not found")

    return FileResponse(
        str(excel),
        filename=excel.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@app.delete("/runs/{run_id}")
async def cancel_run(run_id: str):
    """
    Signal cancellation for the run via threading.Event for pipeline compatibility,
    and cancel the asyncio.Task so async code stops quickly.
    """
    meta = await _safe_get_run(run_id)
    if not meta:
        raise HTTPException(404, "run_id not found")

    # set threading event so pipeline code that checks it stops
    try:
        cancel_event = meta.get("cancel_event")
        if cancel_event:
            cancel_event.set()
    except Exception:
        logger.exception("Failed to set cancel_event for run %s", run_id)

    # cancel asyncio task if present
    task = meta.get("task")
    if task and isinstance(task, asyncio.Task):
        task.cancel()
        await _safe_update_run(run_id, status="cancelling")
        return {"run_id": run_id, "status": "cancelling"}

    await _safe_update_run(run_id, status="cancelling")
    return {"run_id": run_id, "status": "cancelling"}