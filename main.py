import uuid
import logging
import asyncio
import re
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import shutil
import time

# =========================
# Logging
# =========================
logger = logging.getLogger("leadfoundry_api")
logging.basicConfig(level=logging.INFO)

# =========================
# Engine imports (authoritative state & execution)
# =========================
from pipeline_execution.pipeline_parallel_execution import (
    RUNS,
    _RUNS_LOCK,
    _PIPELINE_SEMAPHORE,
    create_run_records,
    async_run_intake,
    async_run_research,
    async_run_finalize,
    safe_update_run,
)

from pipeline_execution.full_pipeline import write_json_atomic

# =========================
# API-only helpers
# =========================
def is_valid_email(email: str) -> bool:
    """Lightweight email format check (not RFC-perfect, intentionally)"""
    return bool(re.match(r"^[^@]+@[^@]+\.[^@]+$", email))


# =========================
# FastAPI lifecycle
# =========================
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("LeadFoundry API starting up")
    yield
    logger.info("LeadFoundry API shutting down")

    async with _RUNS_LOCK:
        for meta in RUNS.values():
            try:
                lock = Path(meta["run_dir"]) / ".pipeline.lock"
                if lock.exists():
                    lock.unlink()
            except Exception:
                logger.exception("Shutdown cleanup failed")

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


async def cleanup_stale_runs(
    base_dir: str = "runs",
    min_age_seconds: int = 1 * 3600,  # 1 hour
):
    """
    Delete run folders that:
    - do NOT have a .pipeline.lock
    - are NOT present in RUNS
    - are older than min_age_seconds
    """
    base = Path(base_dir)
    if not base.exists():
        return
    
    now = time.time()
    
    for folder in base.iterdir():
        if not folder.is_dir():
            continue
        
        lock = folder / ".pipeline.lock"
        if lock.exists():
            continue
        
        try:
            if now - folder.stat().st_mtime < min_age_seconds:
                continue
        except Exception:
            continue
        
        async with _RUNS_LOCK:
            is_active = any(
                meta.get("run_dir") == str(folder)
                for meta in RUNS.values()
            )
        
        if is_active:
            continue
        
        try:
            await asyncio.to_thread(shutil.rmtree, folder, ignore_errors=True)
            logger.info("Deleted stale run folder: %s", folder)
        except Exception:
            logger.exception("Failed to delete folder %s", folder)


# =========================
# API endpoints
# =========================

@app.post("/runs/full", status_code=201)
async def create_and_start_run(payload: Dict):
    """
    Create a run and immediately queue intake.
    Presence of email switches execution_mode to 'email'.
    """
    try:
        await cleanup_stale_runs()  
    except Exception:
        logger.exception("Stale run cleanup failed")


    run_id = uuid.uuid4().hex

    meta = create_run_records("user_input.json")
    meta["run_id"] = run_id

    email = payload.get("email")
    if email:
        if not is_valid_email(email):
            raise HTTPException(400, "Invalid email format")
        meta["email"] = email
        meta["execution_mode"] = "email"
    else:
        meta["execution_mode"] = "manual"

    await asyncio.to_thread(
        write_json_atomic,
        payload,
        meta["config"].user_input_path,
        False,  
    )

    async with _RUNS_LOCK:
        RUNS[run_id] = meta

    async def _wrapped():
        async with _PIPELINE_SEMAPHORE:
            await async_run_intake(run_id)

    task = asyncio.create_task(_wrapped())
    await safe_update_run(run_id, task=task, status="intake_queued")

    return {
        "run_id": run_id,
        "status": "intake_queued",
        "run_dir": meta["run_dir"],
        "email_delivery": bool(email),
    }


@app.post("/runs/{run_id}/research", status_code=202)
async def start_research(run_id: str):
    """
    Explicitly start research.
    Required only for manual (non-email) runs.
    """
    async with _RUNS_LOCK:
        meta = RUNS.get(run_id)
        if not meta:
            raise HTTPException(404, "run_id not found")

        if meta["status"] not in ("intake_completed", "research_failed"):
            raise HTTPException(409, "Research cannot be started in current state")

    async def _wrapped():
        async with _PIPELINE_SEMAPHORE:
            await async_run_research(run_id)

    task = asyncio.create_task(_wrapped())
    await safe_update_run(run_id, task=task, status="research_queued")

    return {"run_id": run_id, "status": "research_queued"}


@app.post("/runs/{run_id}/finalize_full", status_code=202)
async def finalize_full(run_id: str):
    """
    Idempotent finalize endpoint.
    Safe to call multiple times.
    """
    async with _RUNS_LOCK:
        meta = RUNS.get(run_id)
        if not meta:
            raise HTTPException(404, "run_id not found")

        if meta.get("phase") == "done":
            outputs = Path(meta["run_dir"]) / "outputs"
            return {
                "run_id": run_id,
                "status": meta["status"],
                "outputs": [
                    str(p.relative_to(meta["run_dir"]))
                    for p in outputs.rglob("*") if p.is_file()
                ],
                "excel_available": (outputs / "final_leads_list.xlsx").exists(),
            }

        if meta.get("phase") == "finalize":
            return {"run_id": run_id, "status": meta["status"]}

        run_dir = meta["run_dir"]

    async def _wrapped():
        async with _PIPELINE_SEMAPHORE:
            await async_run_finalize(run_id)

    task = asyncio.create_task(_wrapped())
    await safe_update_run(run_id, task=task, status="finalize_queued")

    await task

    async with _RUNS_LOCK:
        meta = RUNS[run_id]

    outputs = Path(run_dir) / "outputs"

    return {
        "run_id": run_id,
        "status": meta["status"],
        "outputs": [
            str(p.relative_to(run_dir))
            for p in outputs.rglob("*") if p.is_file()
        ],
        "excel_available": (outputs / "final_leads_list.xlsx").exists(),
    }


@app.get("/runs/{run_id}/finalize_full/download_excel")
async def download_excel(run_id: str):
    """
    Download final Excel output.
    """
    async with _RUNS_LOCK:
        meta = RUNS.get(run_id)

    if not meta:
        raise HTTPException(404, "run_id not found")

    excel = Path(meta["run_dir"]) / "outputs" / "final_leads_list.xlsx"
    if not excel.exists():
        raise HTTPException(404, "excel not found")

    return FileResponse(
        str(excel),
        filename=excel.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/runs/{run_id}/status")
async def get_status(run_id: str):
    """
    Canonical status endpoint.
    Returns engine-owned truth.
    """
    async with _RUNS_LOCK:
        meta = RUNS.get(run_id)

    if not meta:
        raise HTTPException(404, "run_id not found")

    task = meta.get("task")

    return JSONResponse({
        "run_id": run_id,
        "run_dir": meta["run_dir"],
        "status": meta["status"],
        "phase": meta.get("phase"),
        "execution_mode": meta.get("execution_mode"),
        "error": meta.get("error"),
        "has_task": bool(task),
        "task_done": task.done() if task else None,
        "email_sent": meta.get("email_sent"),
        "email_sent_to": meta.get("email_sent_to"),
        "email_error": meta.get("email_error"),
    })


@app.delete("/runs/{run_id}")
async def cancel_run(run_id: str):
    """
    Signal cancellation to engine and cancel async task.
    """
    async with _RUNS_LOCK:
        meta = RUNS.get(run_id)

    if not meta:
        raise HTTPException(404, "run_id not found")

    meta["cancel_event"].set()

    task = meta.get("task")
    if task:
        task.cancel()

    await safe_update_run(run_id, status="cancelling")

    return {"run_id": run_id, "status": "cancelling"}
