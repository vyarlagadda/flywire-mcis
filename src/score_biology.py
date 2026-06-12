"""Compute five-component biological significance scores for certified FAFB subgraphs."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from src.annotate import compute_synapse_stats

DATA_DIR = Path("data/fafb_annotations")
RESULTS_DIR = Path("results/biology")

SUBGRAPHS = {
    "clique_38": RESULTS_DIR / "clique_38_annotated.csv",
    "star_1877": RESULTS_DIR / "star_1877_annotated.csv",
    "nocolor_1292": RESULTS_DIR / "nocolor_1292_annotated.csv",
}

_COMPONENTS = [
    "IDENTIFIABILITY",
    "TYPE_COHERENCE",
    "NT_COHERENCE",
    "ANATOMICAL_LOCALITY",
    "CIRCUIT_RICHNESS",
]


def score_identifiability(annotated: pd.DataFrame) -> float:
    N = len(annotated)
    if N == 0:
        return 0.0
    return 20.0 * annotated["primary_type"].notna().sum() / N


def score_type_coherence(annotated: pd.DataFrame) -> float:
    N = len(annotated)
    if N <= 1:
        return 20.0
    counts = annotated["primary_type"].dropna().value_counts()
    if counts.empty:
        return 0.0
    probs = counts / counts.sum()
    H = -sum(p * math.log2(p) for p in probs if p > 0)
    return 20.0 * max(0.0, 1.0 - H / math.log2(N))


def score_nt_coherence(annotated: pd.DataFrame) -> float:
    N = len(annotated)
    if N == 0:
        return 0.0
    counts = annotated["nt_type"].value_counts()
    if counts.empty:
        return 0.0
    return 20.0 * counts.iloc[0] / N


def score_anatomical_locality(stats: dict) -> float:
    total = stats["total_internal_synapses"]
    if total == 0:
        return 0.0
    top_count = stats["top3_neuropils"][0][1] if stats["top3_neuropils"] else 0
    return 20.0 * top_count / total


def count_reciprocal_pairs(fafb_set: set[int], connections: pd.DataFrame) -> int:
    mask = (
        connections["pre_root_id"].isin(fafb_set)
        & connections["post_root_id"].isin(fafb_set)
    )
    internal = connections[mask]
    directed = set(zip(internal["pre_root_id"].tolist(), internal["post_root_id"].tolist()))
    return sum(1 for (a, b) in directed if b > a and (b, a) in directed)


def score_circuit_richness(reciprocal_count: int, N: int) -> float:
    if N == 0:
        return 0.0
    return min(20.0, 20.0 * reciprocal_count / N)


def compute_scores(label: str, annotated: pd.DataFrame, connections: pd.DataFrame) -> dict:
    fafb_set = set(annotated["root_id"].astype("int64").tolist())
    N = len(annotated)
    stats = compute_synapse_stats(fafb_set, connections)
    rec_pairs = count_reciprocal_pairs(fafb_set, connections)

    components = {
        "IDENTIFIABILITY": score_identifiability(annotated),
        "TYPE_COHERENCE": score_type_coherence(annotated),
        "NT_COHERENCE": score_nt_coherence(annotated),
        "ANATOMICAL_LOCALITY": score_anatomical_locality(stats),
        "CIRCUIT_RICHNESS": score_circuit_richness(rec_pairs, N),
    }
    total = sum(components.values())

    nt_counts = annotated["nt_type"].value_counts()
    return {
        "label": label,
        "N": N,
        "components": {k: round(v, 4) for k, v in components.items()},
        "total": round(total, 4),
        "top_5_primary_types": {str(k): int(v) for k, v in annotated["primary_type"].value_counts().head(5).items()},
        "dominant_nt": str(nt_counts.index[0]) if not nt_counts.empty else None,
        "top_neuropil": stats["top3_neuropils"][0][0] if stats["top3_neuropils"] else None,
        "reciprocal_pairs": rec_pairs,
        "total_internal_synapses": stats["total_internal_synapses"],
    }


def print_table(results: list[dict]) -> None:
    labels = [r["label"] for r in results]
    col_w = 15
    header = f"{'Component':<22}" + "".join(f"{l:>{col_w}}" for l in labels)
    sep = "-" * len(header)
    print(header)
    print(sep)
    for comp in _COMPONENTS:
        row = f"{comp:<22}" + "".join(f"{r['components'][comp]:>{col_w}.2f}" for r in results)
        print(row)
    print(sep)
    print(f"{'TOTAL':<22}" + "".join(f"{r['total']:>{col_w}.2f}" for r in results))


def main() -> None:
    connections = pd.read_csv(
        DATA_DIR / "connections_princeton.csv.gz",
        usecols=["pre_root_id", "post_root_id", "neuropil", "syn_count"],
    )
    results = []
    for label, path in SUBGRAPHS.items():
        annotated = pd.read_csv(path)
        result = compute_scores(label, annotated, connections)
        results.append(result)

    print_table(results)

    out_path = RESULTS_DIR / "scores.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
