#!/usr/bin/env python3

import json
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from utils.logger import logging
from utils.exception import CustomException

logger = logging.getLogger(__name__)

DEFAULT_SRC = Path("outputs/lead_list_consolidated.json")
DEFAULT_OUT_DEDUPE = Path("outputs/lead_list_deduped.json")


# =========================
# Normalization helpers
# =========================
def norm_company(name: Optional[str]) -> Optional[str]:
    """
    Normalize company name for exact-match deduplication.
    """
    if not name:
        return None

    s = re.sub(r"[^\w\s]", "", str(name).strip().lower())
    for suf in (" inc", " inc.", " ltd", " ltd.", " llc", " corp", " co", " co."):
        if s.endswith(suf):
            s = s[:-len(suf)]

    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def score_record(rec: dict) -> int:
    """
    Score a lead by quality.
    Higher score = better canonical record.
    """
    score = 0
    if rec.get("mail") and "@" in str(rec.get("mail")):
        score += 3
    if rec.get("phone_number"):
        score += 2
    if rec.get("website"):
        score += 1
    return score


# =========================
# Deduplication logic
# =========================
def dedupe_company_name(
    input_path: Path = DEFAULT_SRC,
    out_dedupe: Path = DEFAULT_OUT_DEDUPE,
) -> Tuple[int, int]:
    """
    Deduplicate leads by normalized company name.

    Strategy:
    - Group by normalized company name
    - Pick the highest-quality record per group
    - Backfill missing fields from weaker duplicates

    Returns:
        (num_input_leads, num_output_leads)
    """
    logger.info("########## DEDUPLICATION START ##########")
    logger.info("Input path: %s", input_path)

    try:
        raw_text = input_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
        leads: List[Dict] = data.get("leads", data) if isinstance(data, dict) else data

    except Exception as e:
        logger.exception("Failed to read or parse consolidated leads JSON")
        raise CustomException(e)

    try:
        buckets: Dict[str, List[Dict]] = {}

        for lead in leads:
            key = norm_company(lead.get("company") or lead.get("name"))
            key = key or "__unknown__"
            buckets.setdefault(key, []).append(lead)

        deduped: List[Dict] = []

        for key, group in buckets.items():
            # Choose best canonical record
            best = max(group, key=score_record)
            canon = dict(best)

            for rec in group:
                if rec is best:
                    continue
                for field, value in rec.items():
                    if canon.get(field) in (None, "", "unknown") and value not in (None, "", "unknown"):
                        canon[field] = value

            deduped.append(canon)

        out_dedupe.parent.mkdir(parents=True, exist_ok=True)
        out_dedupe.write_text(
            json.dumps({"leads": deduped}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        logger.info("Leads before: %d | Leads after: %d", len(leads), len(deduped))

        return len(leads), len(deduped)

    except Exception as e:
        logger.exception("Deduplication failed")
        raise CustomException(e)
