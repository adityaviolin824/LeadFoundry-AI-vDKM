#!/usr/bin/env python3
"""
Simple, sequential pipeline runner - per-run folders, cancellation, progress hooks,
pathlib consistency, and safe atomic writes.

This version intentionally removes parallel execution to keep behavior simple and
deterministic. Each query runs sequentially; retries happen inline.
"""
import asyncio
import json
import os
import time
import tempfile
import shutil
import random
import string
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from copy import deepcopy
import threading
from concurrent.futures import ThreadPoolExecutor

from utils.logger import logging
from utils.exception import CustomException

from lead_details_intake.user_intake_pipeline import run_user_intake_pipeline
from multiple_source_lead_search.leads_research_pipeline import run_all_agents_sync
from optimize_and_evaluate_leads.deduplication import dedupe_company_name
from optimize_and_evaluate_leads.prioritize_leads import sort_leads
from optimize_and_evaluate_leads.json_to_excel import leads_json_to_excel_preserve

logger = logging.getLogger(__name__)

PathOrStr = Union[str, Path]


@dataclass
class PipelineConfig:
    # NOTE: these are default templates. real paths will be redirected into run-specific folder at runtime.
    user_input_path: str = "inputs/user_input_2.json"
    suggested_queries_path: str = "outputs/suggested_queries.json"
    consolidated_path: str = "outputs/lead_list_consolidated.json"
    deduped_path: str = "outputs/lead_list_deduped.json"
    sorted_path: str = "outputs/lead_list_sorted.json"
    excel_out_path: str = "outputs/final_leads_list.xlsx"
    metrics_path: str = "outputs/pipeline_metrics.json"

    max_retries: int = 3
    retry_delay: int = 5
    query_timeout: int = 300

    # Run-folder options
    base_run_dir: str = "runs"
    run_name_prefix: str = "run_"
    cleanup_on_start: bool = True
    cleanup_age_hours: int = 3  # delete run folders older than this (hours)

    # Cancellation and progress hooks
    # cancellation_token: threading.Event that caller can set() to request graceful cancellation
    cancellation_token: Optional[threading.Event] = None
    # progress_callback signature: Callable[[str, dict], None]
    progress_callback: Optional[Callable[[str, dict], None]] = None


@dataclass
class PipelineMetrics:
    total_queries: int = 0
    successful_queries: int = 0
    failed_queries: int = 0
    total_leads_found: int = 0
    leads_after_dedup: int = 0
    leads_with_contact_info: int = 0
    execution_time_seconds: float = 0.0

    def to_dict(self) -> Dict:
        return asdict(self)

    def log_summary(self):
        dedup_rate = (self.leads_after_dedup / self.total_leads_found * 100) if self.total_leads_found else 0
        contact_rate = (self.leads_with_contact_info / self.leads_after_dedup * 100) if self.leads_after_dedup else 0

        logger.info("=" * 80)
        logger.info("PIPELINE EXECUTION SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total Queries: {self.total_queries} | Success: {self.successful_queries} | Failed: {self.failed_queries}")
        logger.info(f"Total Leads: {self.total_leads_found} -> Deduped: {self.leads_after_dedup} ({dedup_rate:.1f}% unique)")
        logger.info(f"With Contact Info: {self.leads_with_contact_info} ({contact_rate:.1f}%)")
        logger.info(f"Execution Time: {self.execution_time_seconds:.2f}s")
        logger.info("=" * 80)


# -----------------------
# Helpers
# -----------------------
def load_json(path: PathOrStr) -> Any:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json_atomic(data: Any, path: PathOrStr, make_backup: bool = True, sync: bool = True) -> None:
    """
    Atomically write JSON to path. Accepts Path or str.
    make_backup will attempt to create a hardlink backup, falling back to copy.
    sync controls whether to fsync the temp file before replacing.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    if make_backup and p.exists():
        try:
            backup_path = p.with_name(p.name + ".bak")
            if backup_path.exists():
                backup_path.unlink()
            try:
                os.link(str(p), str(backup_path))
            except OSError:
                shutil.copy2(str(p), str(backup_path))
            logger.debug("Backup created: %s", backup_path.name)
        except Exception:
            logger.debug("Backup failed for %s (continuing)", p, exc_info=True)

    fd, temp_name = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp_", suffix=".json")
    try:
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tf:
                json.dump(data, tf, indent=2, ensure_ascii=False)
                tf.flush()
                if sync:
                    try:
                        os.fsync(tf.fileno())
                    except Exception:
                        logger.debug("fsync failed or slow device, continuing", exc_info=True)
            Path(temp_name).replace(p)
            logger.debug("Atomically wrote: %s", p)
        except Exception:
            logger.exception("Failed to write temp file for %s", p)
            raise
    finally:
        try:
            tmp = Path(temp_name)
            if tmp.exists() and not (p.exists() and tmp.samefile(p)):
                tmp.unlink()
        except Exception:
            pass


def normalize_leads(loaded: Any) -> List[Dict]:
    if isinstance(loaded, dict):
        leads = loaded.get("leads", [])
        return leads if isinstance(leads, list) else []
    return loaded if isinstance(loaded, list) else []


def safe_load_leads(path: PathOrStr, default: Optional[List[Dict]] = None) -> List[Dict]:
    if default is None:
        default = []
    try:
        if not Path(path).exists():
            return default
        return normalize_leads(load_json(path))
    except Exception:
        logger.warning("Could not load leads from %s", path, exc_info=True)
        return default


def load_queries(path: PathOrStr) -> List[str]:
    """
    Load suggested queries file and return list of queries.
    Accepts either {"queries": [...]} or a plain list.
    """
    try:
        if not Path(path).exists():
            return []
        loaded = load_json(path)
        if isinstance(loaded, dict):
            q = loaded.get("queries", [])
            return q if isinstance(q, list) else []
        if isinstance(loaded, list):
            return loaded
        return []
    except Exception:
        logger.warning("Failed to load queries from %s", path, exc_info=True)
        return []


# -----------------------
# Async safety helper
# -----------------------
def run_async_safely(coro):
    """
    Runs a coroutine synchronously, safe to call from anywhere 
    (CLI, Web Server, or existing async context).
    """
    try:
        loop = asyncio.get_running_loop()
        # If we get here, there IS a running loop
        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        # No running loop, safe to use asyncio.run
        return asyncio.run(coro)


# -----------------------
# Cancellation and progress helpers
# -----------------------
def _check_cancel(config: PipelineConfig):
    if config.cancellation_token and config.cancellation_token.is_set():
        logger.info("Pipeline cancellation requested")
        if config.progress_callback:
            try:
                config.progress_callback("cancelled", {})
            except Exception:
                logger.debug("Progress callback raised during cancel notification", exc_info=True)
        raise CustomException("Pipeline cancelled by user")


def _maybe_progress(config: PipelineConfig, event: str, payload: Optional[dict] = None):
    if config and config.progress_callback:
        try:
            config.progress_callback(event, payload or {})
        except Exception:
            logger.debug("Progress callback raised for event %s", event, exc_info=True)


# -----------------------
# Retry helper (sequential)
# -----------------------
def execute_with_retry(func: Callable, *args, config: PipelineConfig, timeout: Optional[int] = None, **kwargs) -> bool:
    """
    Executes `func` with retries in the current thread.
    This is simple and deterministic. If func hangs forever, the caller must
    ensure func itself respects timeouts/cancellation.
    """
    timeout = timeout or config.query_timeout

    for attempt in range(1, config.max_retries + 1):
        _check_cancel(config)
        try:
            func(*args, **kwargs)
            return True
        except Exception as e:
            # If CustomException is known to be permanent, bail fast
            if isinstance(e, CustomException) and getattr(e, "is_retryable", None) is False:
                logger.error("Permanent CustomException, aborting retries: %s", e)
                return False
            logger.warning("Attempt %d/%d failed: %s", attempt, config.max_retries, e)
            if attempt == config.max_retries:
                logger.exception("Final attempt %d failed", attempt)
                return False
            # cancellation-aware wait
            if config.cancellation_token is not None:
                # Wait returns True if the event was set during the wait
                cancelled = config.cancellation_token.wait(config.retry_delay)
                if cancelled:
                    _check_cancel(config)
            else:
                time.sleep(config.retry_delay)

    return False


# -----------------------
# Run-folder cleanup
# -----------------------
def cleanup_old_runs(base_run_dir: str, run_prefix: str = "run_", max_age_hours: int = 3) -> None:
    base = Path(base_run_dir)
    if not base.exists() or not base.is_dir():
        return

    now_ts = time.time()
    age_seconds = max_age_hours * 3600

    for child in base.iterdir():
        try:
            if not child.is_dir():
                continue
            if not child.name.startswith(run_prefix):
                continue
            # skip active runs by sentinel lock
            lock_file = child / ".pipeline.lock"
            if lock_file.exists():
                logger.debug("Skipping active run (lock found): %s", child)
                continue
            mtime = child.stat().st_mtime
            if now_ts - mtime <= age_seconds:
                continue
            try:
                deleting = child / ".deleting"
                try:
                    deleting.touch(exist_ok=True)
                except Exception:
                    pass
                shutil.rmtree(child)
                logger.info("Removed old run folder: %s", child)
            except Exception as e:
                logger.exception("Failed to remove run folder %s: %s", child, e)
        except Exception:
            logger.exception("Error while evaluating run folder: %s", child)


# -----------------------
# Stage implementations
# -----------------------
def run_user_intake_stage(config: PipelineConfig, metrics: PipelineMetrics):
    _check_cancel(config)
    _maybe_progress(config, "stage_start", {
    "stage": 1,
    "name": "user_intake",
    "message": "Starting user intake and query generation"
})
    logger.info("Stage 1: User Intake -> Query Generation")
    if not Path(config.user_input_path).exists():
        raise CustomException(f"User input not found: {config.user_input_path}")

    user_input = load_json(config.user_input_path)
    # Use run_async_safely to avoid nested event loop errors when embedded in async servers
    run_async_safely(run_user_intake_pipeline(user_input, config.suggested_queries_path))

    queries = load_queries(config.suggested_queries_path)
    if not isinstance(queries, list):
        raise CustomException(f"Expected 'queries' list in {config.suggested_queries_path}")
    metrics.total_queries = len(queries)
    logger.info("✓ Stage 1 complete: %d queries generated", metrics.total_queries)
    _maybe_progress(config, "stage_complete", {
    "stage": 1,
    "name": "user_intake",
    "total_queries": metrics.total_queries,
    "message": f"Generated {metrics.total_queries} optimized search queries"
})


def _merge_consolidated_parts(parts_dir: Path, consolidated_path: Path) -> None:
    """
    Read all part files in parts_dir matching consolidated_part_*.json and merge 'leads' arrays.
    Write the merged object to consolidated_path.
    """
    combined: List[Dict] = []
    if not parts_dir.exists() or not parts_dir.is_dir():
        write_json_atomic({"leads": combined}, consolidated_path, make_backup=False)
        return

    parts = list(sorted(parts_dir.glob("consolidated_part_*.json")))
    failed_parts: List[str] = []
    total = len(parts)

    for part in parts:
        try:
            if not part.exists():
                continue
            data = load_json(part)
            leads = normalize_leads(data)
            combined.extend(leads)
            logger.debug("Merged %d leads from %s", len(leads), part.name)
        except Exception:
            logger.exception("Failed to read/merge part file %s", part)
            failed_parts.append(part.name)

    if failed_parts and total and (len(failed_parts) / total) > 0.1:
        raise CustomException(f"Too many failed part merges: {failed_parts}")

    write_json_atomic({"leads": combined}, consolidated_path, make_backup=False)
    logger.info("Merged %d leads into %s", len(combined), consolidated_path)


def run_research_from_queries(config: PipelineConfig, metrics: PipelineMetrics, run_dir: Path):
    _check_cancel(config)
    _maybe_progress(config, "stage_start", {
    "stage": 2,
    "name": "multi_query_research",
    "message": "Starting research across all search queries"
})
    logger.info("Stage 2: Multi-Query Research Pipeline (sequential)")

    queries = load_queries(config.suggested_queries_path)
    if not queries:
        logger.warning("No queries to process. Skipping Stage 2.")
        _maybe_progress(config, "stage_complete", {"stage": 2, "name": "multi_query_research"})
        return

    consolidated_parts_dir = run_dir / "consolidated_parts"
    consolidated_parts_dir.mkdir(parents=True, exist_ok=True)

    completed = 0
    for idx, query in enumerate(queries, start=1):
        _check_cancel(config)
        part_out = consolidated_parts_dir / f"consolidated_part_{idx}.json"
        logger.info("Processing query %d/%d -> %s", idx, len(queries), query)

        ok = execute_with_retry(run_all_agents_sync, query, str(part_out), config=config, timeout=config.query_timeout)
        if ok:
            metrics.successful_queries += 1
            logger.info("✓ Query %d succeeded", idx)
        else:
            metrics.failed_queries += 1
            logger.warning("✗ Query %d failed after retries", idx)

        completed += 1
        _maybe_progress(config, "query_progress", {
    "idx": idx,
    "completed": completed,
    "total": len(queries),
    "message": f"Completed research for query {idx} of {len(queries)}"
})
        _check_cancel(config)

    # merge parts
    consolidated_path = Path(config.consolidated_path)
    consolidated_path.parent.mkdir(parents=True, exist_ok=True)
    _merge_consolidated_parts(consolidated_parts_dir, consolidated_path)

    leads = safe_load_leads(consolidated_path)
    metrics.total_leads_found = len(leads)
    logger.info("✓ Stage 2 complete: %d leads found", metrics.total_leads_found)
    _maybe_progress(config, "stage_complete", {
    "stage": 2,
    "name": "multi_query_research",
    "total_leads": metrics.total_leads_found,
    "message": f"Research finished. Found {metrics.total_leads_found} raw leads"
})


def run_deduplication(config: PipelineConfig, metrics: PipelineMetrics):
    _check_cancel(config)
    _maybe_progress(config, "stage_start", {
    "stage": 3,
    "name": "deduplication",
    "message": "Starting deduplication of company leads"
})
    logger.info("Stage 3: Deduplication")
    try:
        dedupe_company_name(Path(config.consolidated_path), Path(config.deduped_path))
    except Exception as e:
        logger.exception("Deduplication raised exception, attempting fallback")
        if Path(config.consolidated_path).exists():
            raw = load_json(config.consolidated_path)
            write_json_atomic(raw, config.deduped_path, make_backup=False)
            logger.warning("Fallback applied: copied consolidated -> deduped")
        else:
            raise CustomException(f"Deduplication failed and no fallback available: {e}") from e

    deduped_leads = safe_load_leads(config.deduped_path)
    metrics.leads_after_dedup = len(deduped_leads)
    removed = max(0, metrics.total_leads_found - metrics.leads_after_dedup)
    logger.info("✓ Stage 3 complete: removed %d duplicates (%d -> %d)", removed, metrics.total_leads_found, metrics.leads_after_dedup)
    _maybe_progress(config, "stage_complete", {
    "stage": 3,
    "name": "deduplication",
    "deduped": metrics.leads_after_dedup,
    "message": f"Removed duplicates. {metrics.leads_after_dedup} unique leads remain"
})


def run_sorting(config: PipelineConfig, metrics: PipelineMetrics):
    _check_cancel(config)
    _maybe_progress(config, "stage_start", {
    "stage": 4,
    "name": "sorting",
    "message": "Sorting and prioritizing leads"
})
    logger.info("Stage 4: Lead Prioritization")
    leads = safe_load_leads(config.deduped_path)
    sorted_leads = sort_leads(leads)
    metrics.leads_with_contact_info = sum(
        1 for lead in sorted_leads
        if (lead.get("mail") and lead["mail"] != "unknown")
        or (lead.get("phone_number") and lead["phone_number"] != "unknown")
    )
    write_json_atomic({"leads": sorted_leads}, config.sorted_path)
    pct = (metrics.leads_with_contact_info / len(sorted_leads) * 100) if sorted_leads else 0
    logger.info("✓ Stage 4 complete: %d leads sorted, %.1f%% with contact", len(sorted_leads), pct)
    _maybe_progress(config, "stage_complete", {
    "stage": 4,
    "name": "sorting",
    "with_contact_pct": pct,
    "message": f"Lead prioritization complete. {pct:.1f}% have contact info"
})


def run_export_to_excel(config: PipelineConfig, metrics: PipelineMetrics):
    _check_cancel(config)
    _maybe_progress(config, "stage_start", {
    "stage": 5,
    "name": "export",
    "message": "Exporting final leads to Excel"
})
    logger.info("Stage 5: Export to Excel")
    if not Path(config.sorted_path).exists():
        raise CustomException(f"Sorted leads not found: {config.sorted_path}")
    leads_json_to_excel_preserve(input_path=str(config.sorted_path), excel_path=str(config.excel_out_path))
    if not Path(config.excel_out_path).exists():
        raise CustomException("Excel export failed - file not created")
    size_kb = Path(config.excel_out_path).stat().st_size / 1024
    logger.info("✓ Stage 5 complete: Excel saved (%0.1f KB)", size_kb)
    _maybe_progress(config, "stage_complete", {
    "stage": 5,
    "name": "export",
    "size_kb": size_kb,
    "message": "Excel export complete"
})


# -----------------------
# Orchestration
# -----------------------
def _make_run_folder(base_run_dir: str, prefix: str = "run_") -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    run_name = f"{prefix}{ts}_{rand}"
    run_dir = Path(base_run_dir) / run_name
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "outputs").mkdir(parents=True, exist_ok=True)
    logger.info("Created run folder: %s", run_dir)
    return run_dir


def run_full_pipeline(config: Optional[PipelineConfig] = None, user_input_dict: Optional[dict] = None):
    # avoid mutating caller's config
    config = deepcopy(config) if config is not None else PipelineConfig()
    metrics = PipelineMetrics()
    start = time.time()

    logger.info("=== FULL PIPELINE START ===")

    try:
        if config.cleanup_on_start:
            cleanup_old_runs(config.base_run_dir, run_prefix=config.run_name_prefix, max_age_hours=config.cleanup_age_hours)
    except Exception:
        logger.exception("Run-folder cleanup failed (continuing)")

    run_dir = _make_run_folder(config.base_run_dir, prefix=config.run_name_prefix)

    # -----------------------------
    # CREATE .pipeline.lock (new)
    # -----------------------------
    lock_path = run_dir / ".pipeline.lock"
    try:
        lock_path.write_text(str(os.getpid()))
    except Exception:
        logger.exception("Could not create pipeline lock file")
    # -----------------------------

    # 1. Capture the SOURCE path requested by the config
    source_input_path = Path(config.user_input_path)

    # 2. Define the DESTINATION path inside the run folder
    run_input_path = run_dir / "inputs" / "user_input.json"
    run_input_path.parent.mkdir(parents=True, exist_ok=True)

    # 3. Handle the transfer (Priority: Dict > ConfigFile > Failure)
    if user_input_dict is not None:
        write_json_atomic(user_input_dict, run_input_path, make_backup=False, sync=False)
        logger.info("Input: Used provided dictionary argument.")
    elif source_input_path.exists():
        try:
            shutil.copy2(source_input_path, run_input_path)
            logger.info("Input: Copied from config source: %s", source_input_path)
        except Exception:
            logger.exception("Failed to copy input file from %s", source_input_path)
            raise CustomException(f"Failed to copy input file from {source_input_path}")
    else:
        raise CustomException(f"No input provided: user_input_dict is None and config path {source_input_path} does not exist")

    # 4. Update config to point to the new run-isolated file and outputs
    config.user_input_path = str(run_input_path)
    config.suggested_queries_path = str(run_dir / "outputs" / "suggested_queries.json")
    config.consolidated_path = str(run_dir / "outputs" / "lead_list_consolidated.json")
    config.deduped_path = str(run_dir / "outputs" / "lead_list_deduped.json")
    config.sorted_path = str(run_dir / "outputs" / "lead_list_sorted.json")
    config.excel_out_path = str(run_dir / "outputs" / "final_leads_list.xlsx")
    config.metrics_path = str(run_dir / "outputs" / "pipeline_metrics.json")

    logger.info("Run-localized paths set under %s", run_dir)
    _maybe_progress(config, "run_started", {
        "run_dir": str(run_dir),
        "message": f"Pipeline started. Created run folder: {run_dir.name}"
    })

    try:
        run_user_intake_stage(config, metrics)
        run_research_from_queries(config, metrics, run_dir=run_dir)
        run_deduplication(config, metrics)
        run_sorting(config, metrics)
        run_export_to_excel(config, metrics)

        metrics.execution_time_seconds = time.time() - start
        metrics.log_summary()

        Path(config.metrics_path).parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(metrics.to_dict(), config.metrics_path, make_backup=False)
        logger.info("Metrics saved: %s", config.metrics_path)
        _maybe_progress(config, "run_complete", {
            "metrics_path": config.metrics_path,
            "excel_path": config.excel_out_path,
            "message": "Pipeline finished successfully"
        })
        logger.info("=== PIPELINE COMPLETE ===")

    except Exception as e:
        metrics.execution_time_seconds = time.time() - start
        logger.exception("PIPELINE FAILED after %.2fs: %s", metrics.execution_time_seconds, e)
        try:
            Path(config.metrics_path).parent.mkdir(parents=True, exist_ok=True)
            write_json_atomic(metrics.to_dict(), config.metrics_path, make_backup=False)
            logger.info("Failure metrics saved: %s", config.metrics_path)
            _maybe_progress(config, "run_failed", {
                "metrics_path": config.metrics_path,
                "error": str(e),
                "message": "Pipeline failed unexpectedly"
            })
        except Exception:
            logger.exception("Failed to write failure metrics to %s", config.metrics_path)
        raise

    finally:
        # -----------------------------
        # CLEAN UP .pipeline.lock (new)
        # -----------------------------
        try:
            if lock_path.exists():
                lock_path.unlink()
        except Exception:
            logger.exception("Failed to remove pipeline lock file")
        # -----------------------------



if __name__ == "__main__":
    try:
        run_full_pipeline()
    except Exception as exc:
        logger.exception("Fatal error: %s", exc)
        exit(1)