#!/usr/bin/env python3

import json
import re
from pathlib import Path
from difflib import SequenceMatcher
from typing import List, Tuple, Dict, Set, Optional

from utils.logger import logging          
from utils.exception import CustomException 

logger = logging.getLogger(__name__)

DEFAULT_SRC = Path("outputs/lead_list_consolidated.json")
DEFAULT_OUT_DEDUPE = Path("outputs/lead_list_deduped.json")
DEFAULT_OUT_CLUSTERS = Path("outputs/lead_clusters.json")
DEFAULT_SIMILARITY = 0.98


def norm_company(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    s = re.sub(r"[^\w\s]", "", str(name).strip().lower())
    for suf in (" inc", " inc.", " ltd", " ltd.", " llc", " corp", " co", " co."):
        if s.endswith(suf):
            s = s[:-len(suf)]
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def score_record(rec: dict) -> int:
    s = 0
    if rec.get("mail") and "@" in str(rec.get("mail")):
        s += 3
    if rec.get("phone_number"):
        s += 2
    if rec.get("website"):
        s += 1
    return s


def cluster_by_name(names: List[Optional[str]], threshold: float) -> List[Set[int]]:
    unvisited = set(range(len(names)))
    clusters: List[Set[int]] = []

    while unvisited:
        i = unvisited.pop()
        ni = names[i]
        if not ni:
            clusters.append({i})
            continue

        cluster = {i}
        for j in list(unvisited):
            nj = names[j]
            if not nj:
                continue

            if ni == nj:
                cluster.add(j)
                unvisited.discard(j)
                continue

            if SequenceMatcher(None, ni, nj).ratio() >= threshold:
                cluster.add(j)
                unvisited.discard(j)

        clusters.append(cluster)

    return clusters


def dedupe_company_name(
    input_path: Path = DEFAULT_SRC,
    out_dedupe: Path = DEFAULT_OUT_DEDUPE,
    out_clusters: Path = DEFAULT_OUT_CLUSTERS,
    similarity_threshold: float = DEFAULT_SIMILARITY,
) -> Tuple[int, int]:
    """
    Deduplicate leads by company name (exact or high-similarity).
    Returns: (num_input, num_output)
    """
    logger.info(f"Starting dedupe_company_name | input={input_path}")

    try:
        raw_text = input_path.read_text(encoding="utf8")
        data = json.loads(raw_text)

    except Exception as e:
        logger.exception("Failed to read or parse the input JSON file.")
        raise CustomException(e)

    try:
        leads = data.get("leads", data) if isinstance(data, dict) else data

        names = [norm_company(l.get("company") or l.get("name")) for l in leads]
        clusters = cluster_by_name(names, similarity_threshold)

        deduped = []
        cluster_info: Dict[int, Dict] = {}

        for idx, cluster in enumerate(clusters):
            best = max(cluster, key=lambda i: score_record(leads[i]))
            canon = dict(leads[best])

            # backfill missing fields
            for j in cluster:
                if j == best:
                    continue
                for k, v in leads[j].items():
                    if canon.get(k) in (None, "", "unknown") and v not in (None, "", "unknown"):
                        canon[k] = v

            deduped.append(canon)
            cluster_info[idx] = {"indices": sorted(list(cluster)), "chosen_index": int(best)}

        out_dedupe.parent.mkdir(parents=True, exist_ok=True)
        out_dedupe.write_text(json.dumps(deduped, indent=2, ensure_ascii=False), encoding="utf8")
        out_clusters.write_text(json.dumps(cluster_info, indent=2), encoding="utf8")

        logger.info(f"Dedupe completed successfully. {len(leads)} -> {len(deduped)}")

        return (len(leads), len(deduped))

    except Exception as e:
        logger.exception("Error occurred during deduplication.")
        raise CustomException(e)
