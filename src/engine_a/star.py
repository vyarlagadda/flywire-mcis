"""Engine A — directed-star family (correct-by-construction, both orientations).

A pure **out-star** is one hub h plus leaves L with edges h→l only: the induced subgraph must contain
*nothing else*, so the leaves form an independent set (no edge in either direction between any two)
and no leaf points back to the hub. The **in-star** is the mirror (l→h only). Equal-size stars of the
same orientation are isomorphic, and a star is connected — so truncation across a triple is a valid
common induced subgraph. The verifier confirms.

Per dataset we search hubs with relevant degree ≥ ``star.min_hub_out_degree`` (out-degree for out-
stars, in-degree for in-stars), build the largest independent set among the hub's *pure* neighbors
(greedy by ascending degree + a (2,1)-swap local search), and keep the best (hub, orientation). Hubs
are examined in descending degree so the search stops once ``degree + 1`` can no longer beat the best
star found (a star's size is bounded by its hub degree + 1). Params from ``config.yaml
engine_a.star``; RNG seeded from ``config.seed`` (used only to break ties deterministically).
"""
from __future__ import annotations

import time
from typing import Any

from src.io.loader import Dataset

_SWAP_ROUNDS = 50  # cap on (2,1)-swap improvement rounds (each is O(E) over the leaf graph)


def _directed_adjacency(ds: Dataset) -> tuple[list[set[int]], list[set[int]]]:
    out: list[set[int]] = [set() for _ in range(ds.num_nodes)]
    inn: list[set[int]] = [set() for _ in range(ds.num_nodes)]
    for u, v in ds.edges:
        out[u].add(v)
        inn[v].add(u)
    return out, inn


def _independent_set(adj: dict[int, set[int]], swap_max_nodes: int) -> set[int]:
    """Large independent set over the leaf subgraph: greedy (ascending degree) + bounded (2,1)-swaps.

    The greedy alone is near-optimal when the leaf set is large and sparse (the dominant star case),
    so the swap is skipped above ``swap_max_nodes`` leaves. When it runs, each round computes the
    1-tight outside vertices in a single O(E) pass (no per-vertex intersection scan) and is capped at
    ``_SWAP_ROUNDS`` rounds, keeping it bounded on dense leaf neighborhoods.
    """
    order = sorted(adj, key=lambda v: len(adj[v]))
    chosen: set[int] = set()
    blocked: set[int] = set()
    for v in order:
        if v in blocked:
            continue
        chosen.add(v)
        blocked.add(v)
        blocked |= adj[v]

    if len(adj) > swap_max_nodes:
        return chosen

    # (2,1)-swap: drop one chosen x, add two mutually-non-adjacent outsiders whose ONLY chosen
    # neighbor is x → net +1. Repeat to a local optimum (bounded).
    for _ in range(_SWAP_ROUNDS):
        cnt: dict[int, int] = {}
        attach: dict[int, int] = {}
        for c in chosen:
            for w in adj[c]:
                if w in chosen:
                    continue
                cnt[w] = cnt.get(w, 0) + 1
                attach[w] = c
        by_x: dict[int, list[int]] = {}
        for w, k in cnt.items():
            if k == 1:
                by_x.setdefault(attach[w], []).append(w)

        improved = False
        for x, tight in by_x.items():
            for i in range(len(tight)):
                a = tight[i]
                for b in tight[i + 1:]:
                    if b not in adj[a]:
                        chosen.discard(x)
                        chosen.add(a)
                        chosen.add(b)
                        improved = True
                        break
                if improved:
                    break
            if improved:
                break
        if not improved:
            break
    return chosen


def _leaf_subgraph(cand: set[int], out: list[set[int]], inn: list[set[int]]) -> dict[int, set[int]]:
    """Undirected adjacency among candidate leaves (edge iff either direction present)."""
    adj: dict[int, set[int]] = {v: set() for v in cand}
    for v in cand:
        nb = (out[v] | inn[v]) & cand
        nb.discard(v)
        adj[v] = nb
    return adj


def _best_star_for_orientation(
    hubs: list[int],
    primary: list[set[int]],
    secondary: list[set[int]],
    swap_max_nodes: int,
    deadline: float,
) -> tuple[int, list[int]] | None:
    """Best (hub, leaves) for one orientation. ``primary`` is the hub→leaf direction, ``secondary``
    the reverse (a pure edge means leaf is in primary[hub] but not secondary[hub]). Hubs given in
    descending |primary| order; stop once the degree bound can't beat the best (or the deadline)."""
    best_hub = -1
    best_leaves: list[int] = []
    for h in hubs:
        if 1 + len(primary[h]) <= 1 + len(best_leaves):
            break  # degree bound: no remaining hub can beat the best star
        if time.perf_counter() > deadline:
            break
        cand = primary[h] - secondary[h]  # pure edges only (no reciprocal leaf)
        if not cand:
            continue
        adj = _leaf_subgraph(cand, primary, secondary)
        iset = _independent_set(adj, swap_max_nodes)
        if len(iset) > len(best_leaves):
            best_hub, best_leaves = h, sorted(iset)
    if best_hub < 0:
        return None
    return best_hub, best_leaves


def directed_star(ds: Dataset, cfg: dict[str, Any]) -> dict[str, Any]:
    t0 = time.perf_counter()
    star_cfg = cfg["engine_a"]["star"]
    min_deg = int(star_cfg["min_hub_out_degree"])
    swap_max_nodes = int(star_cfg.get("swap_max_nodes", 2000))
    budget = float(star_cfg.get("time_budget_s", 300))
    seed = int(cfg.get("seed", 0))
    out, inn = _directed_adjacency(ds)

    max_out = max((len(s) for s in out), default=0)
    max_in = max((len(s) for s in inn), default=0)
    ub = 1 + max(max_out, max_in)

    out_hubs = sorted(
        (v for v in range(ds.num_nodes) if len(out[v]) >= min_deg),
        key=lambda v: len(out[v]), reverse=True,
    )
    in_hubs = sorted(
        (v for v in range(ds.num_nodes) if len(inn[v]) >= min_deg),
        key=lambda v: len(inn[v]), reverse=True,
    )

    # split the budget across the two orientations
    half = budget / 2.0
    best = None  # (orientation, hub, leaves)
    out_res = _best_star_for_orientation(out_hubs, out, inn, swap_max_nodes, t0 + half)
    if out_res:
        best = ("out", out_res[0], out_res[1])
    in_res = _best_star_for_orientation(in_hubs, inn, out, swap_max_nodes, time.perf_counter() + half)
    if in_res and (best is None or len(in_res[1]) > len(best[2])):
        best = ("in", in_res[0], in_res[1])

    if best is None:
        return {
            "family": "directed_star", "dataset": ds.name, "n": 0, "hub": None,
            "orientation": None, "leaves": [], "upper_bound": int(ub),
            "min_hub_out_degree": min_deg, "seed": seed,
            "wall_clock_s": time.perf_counter() - t0,
        }

    orientation, hub_idx, leaf_idx = best
    return {
        "family": "directed_star",
        "dataset": ds.name,
        "n": 1 + len(leaf_idx),
        "hub": ds.int_to_id[hub_idx],
        "orientation": orientation,
        "leaves": [ds.int_to_id[i] for i in leaf_idx],
        "upper_bound": int(ub),
        "min_hub_out_degree": min_deg,
        "seed": seed,
        "wall_clock_s": time.perf_counter() - t0,
    }
