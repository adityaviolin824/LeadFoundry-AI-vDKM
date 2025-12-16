#!/usr/bin/env python3
"""
Pipeline execution engine.

Responsibilities:
- Execute pipeline stages deterministically
- Respect cancellation
- Emit progress callbacks
- Perform atomic IO
- No orchestration, no API logic, no lifecycle policy
"""

import asyncio
import json
import os
import time
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, asdict
import threading
from concurrent.futures import ThreadPoolExecutor

from utils.logger import logging
from utils.exception import CustomException

from lead_details_intake.user_intake_pipeline import run_user_intake_pipeline
from multiple_source_lead_search.leads_research_pipeline import run_all_agents_sync
from optimize_and_evaluate_leads.deduplication import dedupe_company_name
from optimize_and_evaluate_leads.prioritize_leads import sort_leads
from optimize_and_evaluate_leads.json_to_excel import leads_json_to_excel_preserve
from optimize_and_evaluate_leads.run_enrichment import run_lead_enrichment


logger = logging.getLogger(__name__)

PathOrStr = Union[str, Path]

# ---------------------------------------------------------------------
# Config and metrics
# ---------------------------------------------------------------------

@dataclass
class PipelineConfig:
    user_input_path: str
    suggested_queries_path: str
    consolidated_path: str
    deduped_path: str
    enriched_path: str        
    sorted_path: str
    excel_out_path: str
    metrics_path: str


    max_retries: int = 3
    retry_delay: int = 5
    query_timeout: int = 300

    cancellation_token: Optional[threading.Event] = None
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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

# ---------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------

def load_json(path: PathOrStr) -> Any:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json_atomic(data: Any, path: PathOrStr, make_backup: bool = True) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    if make_backup and p.exists():
        try:
            backup = p.with_suffix(p.suffix + ".bak")
            if backup.exists():
                backup.unlink()
            try:
                os.link(p, backup)
            except OSError:
                shutil.copy2(p, backup)
        except Exception:
            logger.debug("Backup failed for %s", p, exc_info=True)

    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        Path(tmp).replace(p)
    finally:
        try:
            Path(tmp).unlink(missing_ok=True)
        except Exception:
            pass


def normalize_leads(obj: Any) -> List[Dict]:
    if isinstance(obj, dict):
        return obj.get("leads", []) if isinstance(obj.get("leads"), list) else []
    return obj if isinstance(obj, list) else []


def safe_load_leads(path: PathOrStr) -> List[Dict]:
    try:
        if not Path(path).exists():
            return []
        return normalize_leads(load_json(path))
    except Exception:
        logger.warning("Failed to load leads from %s", path, exc_info=True)
        return []


def load_queries(path: PathOrStr) -> List[str]:
    try:
        if not Path(path).exists():
            return []
        data = load_json(path)
        if isinstance(data, dict):
            return data.get("queries", []) if isinstance(data.get("queries"), list) else []
        return data if isinstance(data, list) else []
    except Exception:
        logger.warning("Failed to load queries from %s", path, exc_info=True)
        return []

# ---------------------------------------------------------------------
# Cancellation & progress
# ---------------------------------------------------------------------

def _check_cancel(cfg: PipelineConfig):
    if cfg.cancellation_token and cfg.cancellation_token.is_set():
        if cfg.progress_callback:
            try:
                cfg.progress_callback("cancelled", {})
            except Exception:
                pass
        raise CustomException("Pipeline cancelled")


def _progress(cfg: PipelineConfig, event: str, payload: Optional[dict] = None):
    if cfg.progress_callback:
        try:
            cfg.progress_callback(event, payload or {})
        except Exception:
            pass

# ---------------------------------------------------------------------
# Async intake safety
# ---------------------------------------------------------------------

_async_executor = ThreadPoolExecutor(max_workers=2)

def run_async_safely(coro):
    if not asyncio.iscoroutine(coro):
        raise TypeError("Expected coroutine")
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        return _async_executor.submit(asyncio.run, coro).result()

# ---------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------

def execute_with_retry(func: Callable, *args, cfg: PipelineConfig, **kwargs) -> bool:
    for attempt in range(1, cfg.max_retries + 1):
        _check_cancel(cfg)
        try:
            func(*args, **kwargs)
            return True
        except Exception as e:
            if isinstance(e, CustomException) and getattr(e, "is_retryable", True) is False:
                return False
            if attempt == cfg.max_retries:
                return False
            if cfg.cancellation_token:
                if cfg.cancellation_token.wait(cfg.retry_delay):
                    _check_cancel(cfg)
            else:
                time.sleep(cfg.retry_delay)
    return False

# ---------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------

def run_user_intake_stage(cfg: PipelineConfig, metrics: PipelineMetrics):
    _check_cancel(cfg)

    logger.info("########## INTAKE STAGE STARTED ##########")
    _progress(cfg, "stage_start", {"stage": "intake"})

    user_input = load_json(cfg.user_input_path)
    run_async_safely(run_user_intake_pipeline(user_input, cfg.suggested_queries_path))

    queries = load_queries(cfg.suggested_queries_path)
    metrics.total_queries = len(queries)

    logger.info(
        "########## INTAKE STAGE COMPLETED ########## | queries_generated=%d",
        metrics.total_queries
    )

    _progress(cfg, "stage_complete", {
        "stage": "intake",
        "queries": metrics.total_queries
    })



def run_research_from_queries(cfg: PipelineConfig, metrics: PipelineMetrics, run_dir: Path):
    _check_cancel(cfg)

    logger.info("########## RESEARCH STAGE STARTED ##########")
    _progress(cfg, "stage_start", {"stage": "research"})

    queries = load_queries(cfg.suggested_queries_path)
    total_queries = len(queries)

    if not queries:
        logger.warning("########## NO QUERIES FOUND ##########")
        _progress(cfg, "stage_complete", {"stage": "research", "leads": 0})
        return

    logger.info(
        "########## RESEARCH QUERIES COUNT ########## | total=%d",
        total_queries
    )

    parts_dir = run_dir / "consolidated_parts"
    parts_dir.mkdir(parents=True, exist_ok=True)

    for idx, query in enumerate(queries, start=1):
        _check_cancel(cfg)

        logger.info(
            "########## QUERY START ########## | %d/%d | query=%s",
            idx, total_queries, query
        )

        out = parts_dir / f"consolidated_part_{idx}.json"
        start_ts = time.time()

        ok = execute_with_retry(
            run_all_agents_sync,
            query,
            str(out),
            cfg=cfg
        )

        duration = round(time.time() - start_ts, 2)

        if ok:
            metrics.successful_queries += 1
            logger.info(
                "########## QUERY SUCCESS ########## | %d/%d | time=%.2fs",
                idx, total_queries, duration
            )
        else:
            metrics.failed_queries += 1
            logger.error(
                "########## QUERY FAILED ########## | %d/%d | time=%.2fs",
                idx, total_queries, duration
            )

        _progress(cfg, "query_done", {
            "idx": idx,
            "total": total_queries,
            "success": ok,
            "duration_sec": duration
        })

    # Merge results
    logger.info("########## MERGING QUERY RESULTS ##########")

    leads: List[Dict] = []
    for part in sorted(parts_dir.glob("consolidated_part_*.json")):
        leads.extend(normalize_leads(load_json(part)))

    write_json_atomic({"leads": leads}, cfg.consolidated_path, make_backup=False)
    metrics.total_leads_found = len(leads)

    logger.info(
        "########## RESEARCH STAGE COMPLETED ########## | "
        "queries_total=%d | success=%d | failed=%d | leads=%d",
        total_queries,
        metrics.successful_queries,
        metrics.failed_queries,
        metrics.total_leads_found,
    )

    _progress(cfg, "stage_complete", {
        "stage": "research",
        "leads": metrics.total_leads_found
    })



def run_deduplication(cfg: PipelineConfig, metrics: PipelineMetrics):
    _check_cancel(cfg)

    logger.info("########## DEDUPLICATION STARTED ##########")
    _progress(cfg, "stage_start", {"stage": "deduplication"})

    dedupe_company_name(Path(cfg.consolidated_path), Path(cfg.deduped_path))
    deduped = safe_load_leads(cfg.deduped_path)
    metrics.leads_after_dedup = len(deduped)

    logger.info(
        "########## DEDUPLICATION COMPLETED ########## | remaining=%d",
        metrics.leads_after_dedup
    )

    _progress(cfg, "stage_complete", {
        "stage": "deduplication",
        "remaining": metrics.leads_after_dedup
    })


def run_enrichment_stage(cfg: PipelineConfig, metrics: PipelineMetrics):
    _check_cancel(cfg)

    logger.info("########## ENRICHMENT STARTED ##########")
    _progress(cfg, "stage_start", {"stage": "enrichment"})

    run_async_safely(
        run_lead_enrichment(
            input_json_path=cfg.deduped_path,
            output_json_path=cfg.enriched_path,
        )
    )

    enriched = safe_load_leads(cfg.enriched_path)

    metrics.leads_with_contact_info = sum(
        1 for l in enriched
        if l.get("mail") not in (None, "unknown")
        or l.get("phone_number") not in (None, "unknown")
    )

    logger.info(
        "########## ENRICHMENT COMPLETED ########## | leads=%d | with_contact_info=%d",
        len(enriched),
        metrics.leads_with_contact_info,
    )

    _progress(cfg, "stage_complete", {
        "stage": "enrichment",
        "leads": len(enriched),
        "with_contact_info": metrics.leads_with_contact_info,
    })


def run_sorting(cfg: PipelineConfig, metrics: PipelineMetrics):
    _check_cancel(cfg)

    logger.info("########## SORTING STARTED ##########")
    _progress(cfg, "stage_start", {"stage": "sorting"})

    leads = safe_load_leads(cfg.enriched_path)
    sorted_leads = sort_leads(leads)


    write_json_atomic({"leads": sorted_leads}, cfg.sorted_path)

    logger.info(
        "########## SORTING COMPLETED ########## | total_leads=%d",
        len(sorted_leads)  # Just log the count, don't recalculate contact info
    )

    _progress(cfg, "stage_complete", {"stage": "sorting"})


def run_export_to_excel(cfg: PipelineConfig, metrics: PipelineMetrics):
    _check_cancel(cfg)

    logger.info("########## EXCEL EXPORT STARTED ##########")
    _progress(cfg, "stage_start", {"stage": "export"})

    leads_json_to_excel_preserve(cfg.sorted_path, cfg.excel_out_path)

    if not Path(cfg.excel_out_path).exists():
        logger.error("########## EXCEL EXPORT FAILED ##########")
        raise CustomException("Excel export failed")

    logger.info("########## EXCEL EXPORT COMPLETED ##########")

    _progress(cfg, "stage_complete", {"stage": "export"})
