# app_fastapi.py (async-first version) - with high-priority fixes applied
import uuid
import logging
import json
import os
import asyncio
import inspect
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from fastapi import FastAPI, HTTPException
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Body
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import threading
from contextlib import asynccontextmanager
import shutil

logger = logging.getLogger("leadfoundry_api")
logging.basicConfig(level=logging.INFO)

# Async primitives for concurrency control and safe registry access
RUNS: Dict[str, Dict[str, Any]] = {}
_RUNS_LOCK = asyncio.Lock()
MAX_CONCURRENT_RUNS = 2
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
    _make_run_folder,  # if not exported, reimplement naming logic here
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
    # wrap sync function to run in thread
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
    # Delegate to thread-safe writer
    await asyncio.to_thread(_write_progress_sync, run_dir, stage, info)


# Create run metadata (sync parts are small and safe)
# NOTE: this function no longer writes the user_input to disk. create_run will write it via asyncio.to_thread
def _create_run_records(user_input_path: str, base_run_dir: Optional[str] = None) -> Dict[str, Any]:
    cfg = PipelineConfig()
    if base_run_dir:
        cfg.base_run_dir = base_run_dir

    run_dir = _make_run_folder(cfg.base_run_dir, prefix=cfg.run_name_prefix)

    # create simple lock sentinel
    lock_path = Path(run_dir) / ".pipeline.lock"
    try:
        lock_path.write_text(str(os.getpid()))
    except Exception:
        logger.exception("Could not write initial lock file")

    inputs_dir = Path(run_dir) / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    run_input_path = inputs_dir / user_input_path  # filename provided by caller

    # localize config paths
    cfg.user_input_path = str(run_input_path)
    cfg.suggested_queries_path = str(Path(run_dir) / "outputs" / "suggested_queries.json")
    cfg.consolidated_path = str(Path(run_dir) / "outputs" / "lead_list_consolidated.json")
    cfg.deduped_path = str(Path(run_dir) / "outputs" / "lead_list_deduped.json")
    cfg.sorted_path = str(Path(run_dir) / "outputs" / "lead_list_sorted.json")
    cfg.excel_out_path = str(Path(run_dir) / "outputs" / "final_leads_list.xlsx")
    cfg.metrics_path = str(Path(run_dir) / "outputs" / "pipeline_metrics.json")

    metrics = PipelineMetrics()
    # Keep threading.Event for pipeline compatibility
    cancel_event = _create_threading_cancel_event()

    meta = {
        "run_id": None,
        "run_dir": str(run_dir),
        "config": cfg,
        "metrics": metrics,
        "cancel_event": cancel_event,  # for compatibility with pipeline expecting threading.Event
        "task": None,                  # asyncio.Task for the currently running stage
        "status": "created",
        "error": None,
    }
    return meta


# Async stage runners that call pipeline code safely
async def _async_run_intake(run_id: str):
    meta = await _safe_get_run(run_id)
    if not meta:
        logger.error("Run missing in intake runner: %s", run_id)
        return

    cfg: PipelineConfig = meta["config"]
    metrics: PipelineMetrics = meta["metrics"]
    # pipeline expects a threading.Event; meta already contains it
    cfg.cancellation_token = meta["cancel_event"]

    await _safe_update_run(run_id, status="intake_running")
    await _write_progress(meta["run_dir"], "intake", {"status": "started"})
    try:
        await _maybe_awaitable_call(run_user_intake_stage, cfg, metrics)
        await _safe_update_run(run_id, status="intake_completed")
        await _write_progress(meta["run_dir"], "intake", {"status": "completed", "total_queries": metrics.total_queries})
    except asyncio.CancelledError:
        logger.info("Intake task cancelled for run %s", run_id)
        await _safe_update_run(run_id, status="cancelled")
        await _write_progress(meta["run_dir"], "intake", {"status": "cancelled"})
    except Exception as e:
        logger.exception("Intake failed for run %s", run_id)
        await _safe_update_run(run_id, status="intake_failed", error=str(e))
        await _write_progress(meta["run_dir"], "intake", {"status": "failed", "error": str(e)})


async def _async_run_research(run_id: str):
    meta = await _safe_get_run(run_id)
    if not meta:
        logger.error("Run missing in research runner: %s", run_id)
        return

    cfg: PipelineConfig = meta["config"]
    metrics: PipelineMetrics = meta["metrics"]
    cfg.cancellation_token = meta["cancel_event"]

    await _safe_update_run(run_id, status="research_running")
    await _write_progress(meta["run_dir"], "research", {"status": "started"})
    try:
        # Use the run_dir Path object just like the pipeline expects
        await _maybe_awaitable_call(run_research_from_queries, cfg, metrics, run_dir=Path(meta["run_dir"]))
        await _safe_update_run(run_id, status="research_completed")
        await _write_progress(meta["run_dir"], "research", {"status": "completed", "total_leads": metrics.total_leads_found})
    except asyncio.CancelledError:
        logger.info("Research task cancelled for run %s", run_id)
        await _safe_update_run(run_id, status="cancelled")
        await _write_progress(meta["run_dir"], "research", {"status": "cancelled"})
    except Exception as e:
        logger.exception("Research failed for run %s", run_id)
        await _safe_update_run(run_id, status="research_failed", error=str(e))
        await _write_progress(meta["run_dir"], "research", {"status": "failed", "error": str(e)})


async def _async_run_finalize(run_id: str):
    meta = await _safe_get_run(run_id)
    if not meta:
        logger.error("Run missing in finalize runner: %s", run_id)
        return

    cfg: PipelineConfig = meta["config"]
    metrics: PipelineMetrics = meta["metrics"]
    cfg.cancellation_token = meta["cancel_event"]

    await _safe_update_run(run_id, status="finalize_running")
    await _write_progress(meta["run_dir"], "finalize", {"status": "started"})
    try:
        # run dedupe, sort, export sequentially
        await _maybe_awaitable_call(run_deduplication, cfg, metrics)
        await _maybe_awaitable_call(run_sorting, cfg, metrics)
        await _maybe_awaitable_call(run_export_to_excel, cfg, metrics)
        await _safe_update_run(run_id, status="finalize_completed")
        await _write_progress(meta["run_dir"], "finalize", {"status": "completed"})
        # persist metrics to disk using thread
        await _safe_write_json_atomic(metrics.to_dict(), Path(cfg.metrics_path), make_backup=False)
    except asyncio.CancelledError:
        logger.info("Finalize task cancelled for run %s", run_id)
        await _safe_update_run(run_id, status="cancelled")
        await _write_progress(meta["run_dir"], "finalize", {"status": "cancelled"})
    except Exception as e:
        logger.exception("Finalize failed for run %s", run_id)
        await _safe_update_run(run_id, status="finalize_failed", error=str(e))
        await _write_progress(meta["run_dir"], "finalize", {"status": "failed", "error": str(e)})


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

    # write input
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

    logger.info("Created run %s and queued intake", run_id)
    return {"run_id": run_id, "status": "intake_queued", "run_dir": meta["run_dir"]}



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

# @app.post("/runs/{run_id}/research", status_code=202)
# async def start_research_dummy(run_id: str):
#     """
#     Dummy research stage for testing UI without running the actual pipeline.
#     It instantly completes research and produces empty JSON results.
#     """
#     meta = await _safe_get_run(run_id)
#     if not meta:
#         raise HTTPException(404, "run_id not found")

#     # Mark research as queued
#     await _safe_update_run(run_id, status="research_queued")

#     async def _wrapped():
#         async with _PIPELINE_SEMAPHORE:
#             # Simulate small delay
#             await asyncio.sleep(15)
#             # Mark research as completed with empty output
#             await _safe_update_run(run_id, status="research_completed")

#             # Write empty research output
#             out_dir = Path(meta["run_dir"]) / "outputs"
#             out_dir.mkdir(parents=True, exist_ok=True)
#             empty_json_path = out_dir / "dummy_research_output.json"
#             await asyncio.to_thread(write_json_atomic, {}, str(empty_json_path), False, False)

#             # Write progress log
#             await _write_progress(meta["run_dir"], "research", {"status": "completed", "dummy": True})

#     task = asyncio.create_task(_wrapped())
#     await _safe_update_run(run_id, task=task)

#     return {"run_id": run_id, "status": "research_queued", "dummy": True}





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
