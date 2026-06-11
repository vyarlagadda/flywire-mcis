"""Engine A — reciprocal-clique family (correct-by-construction).

A clique in the reciprocal-edge graph (``to_reciprocal_igraph``) is a set of neurons mutually joined
by reciprocal (both-direction) edges — i.e. a *directed reciprocal clique*. Any two equal-size
reciprocal cliques are isomorphic (the complete directed graph on k nodes) and weakly connected, so
truncation to the min size across a triple is automatically a valid common induced subgraph. The
verifier (``src.verify``) still confirms every candidate.

We report two numbers per dataset:
  - ``n``           : the size of a clique we actually found — a certified LOWER bound.
  - ``upper_bound`` : degeneracy+1 of the reciprocal graph (= max coreness + 1) — an UPPER bound on
                      any clique. Reported separately; never claimed as achieved.

The lower bound is obtained by a seeded randomized greedy (``clique.restarts`` restarts), then an
exact ``largest_cliques`` attempt on the relevant k-core, run in a worker process bounded by
``clique.time_budget_s`` (terminated on timeout, falling back to the greedy clique). All params come
from ``config.yaml engine_a.clique``; RNG is seeded from ``config.seed``.
"""
from __future__ import annotations

import multiprocessing as mp
import random
import time
from typing import Any

from src.io.graphs import to_reciprocal_igraph
from src.io.loader import Dataset


def _adjacency_sets(g) -> list[set[int]]:
    """Undirected neighbor sets indexed by vertex id."""
    nbrs: list[set[int]] = [set() for _ in range(g.vcount())]
    for e in g.es:
        a, b = e.source, e.target
        nbrs[a].add(b)
        nbrs[b].add(a)
    return nbrs


def _greedy_clique(nbrs: list[set[int]], seeds: list[int], key: list[int]) -> list[int]:
    """Best clique over several greedy expansions, each seeded at one vertex.

    From a seed, repeatedly add the candidate maximizing the static ``key`` (coreness — vertices that
    can belong to a large clique), then intersect the candidate pool with its neighborhood. Using a
    *precomputed* key keeps each step O(|cand|) (no per-step intersection scan), which matters on the
    dense reciprocal graphs. Always yields a valid clique.
    """
    best: list[int] = []
    for seed in seeds:
        clique = [seed]
        cand = set(nbrs[seed])
        while cand:
            pick = max(cand, key=key.__getitem__)
            clique.append(pick)
            cand &= nbrs[pick]
        if len(clique) > len(best):
            best = clique
    return best


def _exact_worker(n: int, edges: list[tuple[int, int]], q) -> None:
    """Child process: largest clique of the (relabeled) undirected subgraph → vertex list on the queue."""
    import igraph

    g = igraph.Graph(n=n, edges=edges, directed=False)
    cliques = g.largest_cliques()
    q.put(list(cliques[0]) if cliques else [])


def _kcore_subgraph(g, nbrs: list[set[int]], coreness: list[int], floor: int):
    """Vertices with coreness >= floor (any clique strictly larger than ``floor`` lives here), as a
    compact relabeled edge list plus the map back to original vertex ids.
    """
    keep = [v for v in range(g.vcount()) if coreness[v] >= floor]
    relabel = {v: i for i, v in enumerate(keep)}
    edges = [
        (relabel[u], relabel[v])
        for u in keep
        for v in nbrs[u]
        if u < v and v in relabel
    ]
    return keep, edges


def reciprocal_clique(ds: Dataset, cfg: dict[str, Any]) -> dict[str, Any]:
    t0 = time.perf_counter()
    params = cfg["engine_a"]["clique"]
    restarts = int(params["restarts"])
    budget = float(params["time_budget_s"])
    seed = int(cfg.get("seed", 0))

    g = to_reciprocal_igraph(ds)
    nbrs = _adjacency_sets(g)
    coreness = g.coreness()
    ub = (max(coreness) + 1) if g.vcount() else 0

    # Lower-bound floor: seeded randomized greedy over `restarts` start vertices (prefer high-core).
    rng = random.Random(seed)
    nonisolated = [v for v in range(g.vcount()) if nbrs[v]]
    method = "greedy"
    members_idx: list[int] = []
    if nonisolated:
        ranked = sorted(nonisolated, key=lambda v: coreness[v], reverse=True)
        seeds = ranked[: min(len(ranked), max(1, restarts))]
        # mix in random seeds for diversity (deterministic from config seed)
        seeds = list(dict.fromkeys(seeds + [rng.choice(nonisolated) for _ in range(restarts)]))
        members_idx = _greedy_clique(nbrs, seeds, coreness)

    # Exact attempt on the k-core above the greedy floor, bounded by the time budget.
    floor = len(members_idx)
    if floor < ub:  # only worth it if a larger clique is still possible
        keep, edges = _kcore_subgraph(g, nbrs, coreness, floor)
        if keep:
            ctx = mp.get_context("spawn")
            q = ctx.Queue()
            proc = ctx.Process(target=_exact_worker, args=(len(keep), edges, q))
            proc.start()
            proc.join(budget)
            if proc.is_alive():
                proc.terminate()
                proc.join()
            else:
                try:
                    exact_local = q.get_nowait()
                except Exception:
                    exact_local = []
                if len(exact_local) > len(members_idx):
                    members_idx = [keep[i] for i in exact_local]
                    method = "exact"

    members = [g.vs[i]["name"] for i in members_idx]
    return {
        "family": "reciprocal_clique",
        "dataset": ds.name,
        "n": len(members),
        "members": members,
        "upper_bound": int(ub),
        "method": method,
        "restarts": restarts,
        "time_budget_s": budget,
        "seed": seed,
        "wall_clock_s": time.perf_counter() - t0,
    }
