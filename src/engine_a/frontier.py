"""Engine A — frontier assembler.

Given per-dataset family instances (from ``clique``/``star``/``biclique``) and the loaded datasets,
build a candidate for every (family × triple) by aligning the three instances at the common size,
then run it through the **verifier** (``src.verify``). Only verifier-PASS rows are trusted; each
carries the exact candidate rows so a certificate CSV can be written.

Alignment per family (all correct-by-construction, so equal-size aligned instances are isomorphic):
  - reciprocal_clique: N = min clique size; rows = first N members of each (order is arbitrary —
    the directed clique is complete).
  - directed_star: all three must share an orientation; N = min size; row 0 = hub, rows 1..N-1 =
    first N-1 leaves.
  - complete_bipartite: a' = min |part_a|, b' = min |part_b| (both ≥ 2); rows = first a' of each
    part_a then first b' of each part_b (same a_to_b orientation).
"""
from __future__ import annotations

from itertools import combinations
from typing import Any

from src.io.loader import Dataset
from src.verify.check import verify_candidate

Instances = dict[str, dict[str, dict[str, Any]]]


def _clique_candidate(triple, inst):
    sizes = [len(inst[d]["members"]) for d in triple]
    n = min(sizes)
    if n < 2:
        return None, f"min clique size {n} < 2"
    rows = [[inst[d]["members"][i] for d in triple] for i in range(n)]
    return rows, ""


def _star_candidate(triple, inst):
    orients = {inst[d]["orientation"] for d in triple}
    if len(orients) != 1 or None in orients:
        return None, f"orientation mismatch {sorted(str(o) for o in orients)}"
    sizes = [inst[d]["n"] for d in triple]
    n = min(sizes)
    if n < 2:
        return None, f"min star size {n} < 2"
    rows = [[inst[d]["hub"] for d in triple]]
    for i in range(n - 1):
        rows.append([inst[d]["leaves"][i] for d in triple])
    return rows, ""


def _biclique_candidate(triple, inst):
    a = min(len(inst[d]["part_a"]) for d in triple)
    b = min(len(inst[d]["part_b"]) for d in triple)
    if a < 2 or b < 2:
        return None, f"min parts (a={a}, b={b}) not both >= 2"
    rows = [[inst[d]["part_a"][i] for d in triple] for i in range(a)]
    rows += [[inst[d]["part_b"][i] for d in triple] for i in range(b)]
    return rows, ""


_BUILDERS = {
    "reciprocal_clique": _clique_candidate,
    "directed_star": _star_candidate,
    "complete_bipartite": _biclique_candidate,
}


def assemble_frontier(
    instances: Instances,
    datasets: dict[str, Dataset],
    triples: list[tuple[str, ...]] | None = None,
) -> list[dict[str, Any]]:
    names = sorted(datasets)
    triples = triples or list(combinations(names, 3))
    out: list[dict[str, Any]] = []

    for family, inst in instances.items():
        builder = _BUILDERS[family]
        for triple in triples:
            if any(d not in inst for d in triple):
                continue
            rows, reason = builder(triple, inst)
            columns = list(triple)
            if rows is None:
                out.append({
                    "family": family, "triple": tuple(triple), "n": 0, "structure": "",
                    "ok": False, "reason": reason, "columns": columns, "candidate_rows": [],
                })
                continue
            rep = verify_candidate(columns, rows, {d: datasets[d] for d in triple})
            out.append({
                "family": family,
                "triple": tuple(triple),
                "n": rep.n,
                "structure": rep.structure,
                "ok": rep.ok,
                "reason": rep.reason,
                "columns": columns,
                "candidate_rows": rows,
            })
    return out
