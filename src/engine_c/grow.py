"""Engine C — the connectivity-constrained greedy seed-and-extend loop.

From an initial mapping (a single WL seed triple, or Engine A's full clique warm-start), grow the
three-way correspondence one matched triple at a time. A new triple ``(a, b, c)`` is admissible iff
its connection signatures match across all three graphs (see ``signature.py``) — which is exactly the
condition that keeps the partial map an induced directed isomorphism. Each step rebuilds the boundary
groups (they mutate on every admission) and admits the single best candidate by a deterministic
secondary score, so dead-ends are avoided without a stale priority queue.

Connectivity:
  - ``enforce_weak_connectivity = True`` (default): only boundary nodes carry signatures and a
    formable triple shares a *non-zero* common signature, so the new row attaches identically in all
    three graphs — weak connectivity is automatic.
  - ``False`` (N-ceiling reference): when no connected extension exists, *jump* to a shallow-color
    matched triple of fully-disconnected (all-zero signature) unmapped nodes, letting separate
    components form. Still induced-iso (all-or-none "none"), but no longer weakly connected — for the
    frontier discussion only, never the submission.

The greedy never backtracks within a seed, so signatures are append-only (O(deg) per admission).
Pure Python; the verifier remains the sole authority on every kept result.
"""
from __future__ import annotations

import time
from itertools import product
from typing import Any

from src.engine_c.signature import GraphState, add_member, group_by_key

States = tuple[GraphState, GraphState, GraphState]


def _score(a: int, b: int, c: int, states: States, shallow_colors, deep_colors) -> tuple:
    """Deterministic secondary score (higher wins) for picking among admissible triples.

    Lexicographic: (1) deep-WL colors all equal (strongest structural agreement); (2) shallow-WL
    colors all equal (advisory when shallow color is not in the hard key — keeps growth biased toward
    color-consistent, biologically comparable matches); (3) small in/out degree spread across the
    three candidates (a hub matched to a leaf dead-ends); (4) large minimum future-boundary
    contribution across graphs (the bottleneck graph governs future growth); (5) smallest
    ``(a, b, c)`` for a total, reproducible tie-break.
    """
    gb, gf, gm = states
    deep_match = int(int(deep_colors[0][a]) == int(deep_colors[1][b]) == int(deep_colors[2][c]))
    shallow_match = int(int(shallow_colors[0][a]) == int(shallow_colors[1][b]) == int(shallow_colors[2][c]))
    indeg = (len(gb.inn[a]), len(gf.inn[b]), len(gm.inn[c]))
    outdeg = (len(gb.out[a]), len(gf.out[b]), len(gm.out[c]))
    spread = (max(indeg) - min(indeg)) + (max(outdeg) - min(outdeg))
    fb_a = len((gb.out[a] | gb.inn[a]) - gb.mapped_set)
    fb_b = len((gf.out[b] | gf.inn[b]) - gf.mapped_set)
    fb_c = len((gm.out[c] | gm.inn[c]) - gm.mapped_set)
    min_future = min(fb_a, fb_b, fb_c)
    return (deep_match, shallow_match, -spread, min_future, -a, -b, -c)


def _best_candidate(
    common_keys, groups_b, groups_f, groups_m, states: States, shallow_colors, deep_colors, candidate_cap: int
) -> tuple[int, int, int] | None:
    """Best admissible triple this step: argmax of ``_score`` over candidates sharing a common step
    key in all three graphs, bounded by ``candidate_cap`` examined."""
    best: tuple[int, int, int] | None = None
    best_score = None
    budget = 0
    for key in sorted(common_keys):
        la, lb, lc = sorted(groups_b[key]), sorted(groups_f[key]), sorted(groups_m[key])
        for a, b, c in product(la, lb, lc):
            budget += 1
            if budget > candidate_cap:
                return best
            sc = _score(a, b, c, states, shallow_colors, deep_colors)
            if best_score is None or sc > best_score:
                best_score = sc
                best = (a, b, c)
    return best


def _next_jump(jump_pool, states: States) -> tuple[int, int, int] | None:
    """First pool triple whose three nodes are unmapped AND fully disconnected from the current
    mapping (all-zero signature in every graph) — a valid new-component addition under OFF mode."""
    gb, gf, gm = states
    for a, b, c in jump_pool:
        if a in gb.mapped_set or b in gf.mapped_set or c in gm.mapped_set:
            continue
        if a in gb.boundary or b in gf.boundary or c in gm.boundary:
            continue  # non-zero signature => would need the iso check; skip to keep jumps trivially valid
        return (a, b, c)
    return None


def grow_from_seed(
    init_mapping: list[tuple[int, int, int]],
    states: States,
    shallow_colors,
    deep_colors,
    *,
    enforce_conn: bool,
    candidate_cap: int,
    boundary_cap: int,
    jump_pool: list[tuple[int, int, int]] | None = None,
    use_color_key: bool = True,
    deadline: float,
) -> dict[str, Any]:
    """Grow a mapping from ``init_mapping`` and return ``{n, rows_int, stopped_reason}``.

    ``states`` must be FRESH (empty-mapping) GraphStates for the three chosen datasets, in the same
    order as ``shallow_colors``/``deep_colors`` (each a length-3 list of per-node color arrays).
    ``use_color_key`` puts shallow-WL color in the hard step key (stricter pruning) when True, or
    demotes it to an advisory score term when False (more permissive; signature equality alone still
    guarantees induced isomorphism). ``stopped_reason`` is ``"no_extension"`` (local optimum) or
    ``"deadline"`` (wall-clock budget).
    """
    gb, gf, gm = states
    rows: list[tuple[int, int, int]] = []
    for a, b, c in init_mapping:
        add_member(gb, a)
        add_member(gf, b)
        add_member(gm, c)
        rows.append((a, b, c))

    stopped = "no_extension"
    while time.monotonic() < deadline:
        groups_b = group_by_key(gb, shallow_colors[0], boundary_cap, use_color_key)
        groups_f = group_by_key(gf, shallow_colors[1], boundary_cap, use_color_key)
        groups_m = group_by_key(gm, shallow_colors[2], boundary_cap, use_color_key)
        common = set(groups_b) & set(groups_f) & set(groups_m)

        choice = None
        if common:
            choice = _best_candidate(common, groups_b, groups_f, groups_m, states, shallow_colors, deep_colors, candidate_cap)
        if choice is None and not enforce_conn and jump_pool:
            choice = _next_jump(jump_pool, states)
        if choice is None:
            stopped = "no_extension"
            break

        a, b, c = choice
        add_member(gb, a)
        add_member(gf, b)
        add_member(gm, c)
        rows.append((a, b, c))
    else:
        stopped = "deadline"

    return {"n": len(rows), "rows_int": rows, "stopped_reason": stopped}
