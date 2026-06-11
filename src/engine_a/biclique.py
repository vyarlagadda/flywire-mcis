"""Engine A — complete-bipartite family (gated, correct-by-construction).

Target a **pure directed biclique** K_{a,b}: parts A and B with *every* A→B edge present, *no* B→A
edge, and *no* edge within A or within B. As an induced subgraph this is exactly the complete
bipartite shape, and two instances of the same (a, b) and orientation are isomorphic and connected —
so a common (a', b') = (min a, min b) across a triple is a valid common induced subgraph. The
verifier confirms.

This family is the hardest (maximum biclique is NP-hard); we compute a heuristic **lower bound**,
time-budgeted by ``biclique.time_budget_s`` and gated by ``biclique.enabled``. For a seed hub h we
take B = an independent subset of h's *pure* out-neighbors (h→b, no b→h), then grow A from the
A-candidates — vertices x with the whole of B in their pure out-neighbourhood, computed efficiently as
``(∩_{b∈B} in[b]) − (∪_{b∈B} out[b])`` — keeping A an independent set. Best a·b (a,b ≥ 2) wins.
Params from ``config.yaml engine_a.{star,biclique}``; RNG seeded from ``config.seed``.
"""
from __future__ import annotations

import time
from typing import Any

from src.io.loader import Dataset


def _directed_adjacency(ds: Dataset) -> tuple[list[set[int]], list[set[int]]]:
    out: list[set[int]] = [set() for _ in range(ds.num_nodes)]
    inn: list[set[int]] = [set() for _ in range(ds.num_nodes)]
    for u, v in ds.edges:
        out[u].add(v)
        inn[v].add(u)
    return out, inn


def _greedy_is(verts: list[int], adj: dict[int, set[int]], forced: int | None = None) -> list[int]:
    """Greedy independent set (ascending degree), optionally forcing one vertex into the set first."""
    chosen: set[int] = set()
    blocked: set[int] = set()
    if forced is not None:
        chosen.add(forced)
        blocked.add(forced)
        blocked |= adj.get(forced, set())
    for v in sorted(verts, key=lambda v: len(adj[v])):
        if v in blocked:
            continue
        chosen.add(v)
        blocked.add(v)
        blocked |= adj[v]
    return sorted(chosen)


def complete_bipartite(ds: Dataset, cfg: dict[str, Any]) -> dict[str, Any]:
    t0 = time.perf_counter()
    bc = cfg["engine_a"]["biclique"]
    seed = int(cfg.get("seed", 0))
    if not bc.get("enabled", True):
        return {
            "family": "complete_bipartite", "dataset": ds.name, "n": 0, "skipped": True,
            "part_a": [], "part_b": [], "orientation": "a_to_b", "upper_bound": 0,
            "seed": seed, "wall_clock_s": time.perf_counter() - t0,
        }

    budget = float(bc["time_budget_s"])
    min_deg = int(cfg["engine_a"]["star"]["min_hub_out_degree"])
    out, inn = _directed_adjacency(ds)

    def pure_out(v: int) -> set[int]:
        return out[v] - inn[v]

    seeds = sorted(
        (v for v in range(ds.num_nodes) if len(pure_out(v)) >= min_deg),
        key=lambda v: len(pure_out(v)), reverse=True,
    )

    best_a: list[int] = []
    best_b: list[int] = []
    best_prod = 0
    for h in seeds:
        if time.perf_counter() - t0 > budget:
            break
        b_cand = pure_out(h)
        if len(b_cand) < 2:
            continue
        # make B an independent set (no within-B edges)
        b_adj = {b: (out[b] | inn[b]) & b_cand for b in b_cand}
        for b in b_adj:
            b_adj[b].discard(b)
        B = _greedy_is(list(b_cand), b_adj)
        if len(B) < 2:
            continue
        Bs = set(B)

        # A-candidates: vertices whose pure-out neighbourhood ⊇ B.
        #   x→b for all b  ⇔  x ∈ ∩_b in[b];   b→x for no b  ⇔  x ∉ ∪_b out[b].
        common_in: set[int] = set(inn[B[0]])
        for b in B[1:]:
            common_in &= inn[b]
            if not common_in:
                break
        forbid: set[int] = set()
        for b in B:
            forbid |= out[b]
        a_cand = (common_in - forbid) - Bs
        a_cand.add(h)
        if len(a_cand) < 2:
            continue
        a_adj = {x: (out[x] | inn[x]) & a_cand for x in a_cand}
        for x in a_adj:
            a_adj[x].discard(x)
        A = _greedy_is(list(a_cand), a_adj, forced=h)
        if len(A) < 2:
            continue

        prod = len(A) * len(B)
        if prod > best_prod:
            best_prod, best_a, best_b = prod, A, B

    return {
        "family": "complete_bipartite",
        "dataset": ds.name,
        "n": len(best_a) + len(best_b),
        "part_a": [ds.int_to_id[i] for i in best_a],
        "part_b": [ds.int_to_id[i] for i in best_b],
        "orientation": "a_to_b",
        "upper_bound": 0,  # no cheap non-trivial UB for max biclique; LB only
        "seed": seed,
        "wall_clock_s": time.perf_counter() - t0,
    }
