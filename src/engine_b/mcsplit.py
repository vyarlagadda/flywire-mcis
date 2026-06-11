"""McSplit branch-and-bound for maximum common CONNECTED induced subgraph on 3 directed graphs.

Label-class B&B extended to 3 graphs:
  - label classes (S_A, S_B, S_C) of mutually admissible unmatched vertices
  - upper bound = |mapping| + sum_classes min(|S_A|, |S_B|, |S_C|)
  - branching: pick the largest class (by min-size), branch on each vertex in the smallest list
  - vertex-equivalence pruning: initial classes partitioned by (out_deg, in_deg) signature
  - directed-edge consistency: 4-type labelling per matched node (none/x->u/u->x/both)
  - connectivity: only admit a triple if all 3 vertices are weakly adjacent to the mapped set
  - timeout: hard wall-clock deadline
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

LabelClass = tuple[list[int], list[int], list[int]]


def _edge_type(out_adj: dict[int, set[int]], x: int, u: int) -> int:
    """Directed edge type from x's perspective relative to u: 0=none, 1=x->u, 2=u->x, 3=both."""
    return (1 if u in out_adj.get(x, ()) else 0) + (2 if x in out_adj.get(u, ()) else 0)


def _initial_classes(
    out_a: dict[int, set[int]], in_a: dict[int, set[int]],
    out_b: dict[int, set[int]], in_b: dict[int, set[int]],
    out_c: dict[int, set[int]], in_c: dict[int, set[int]],
    nodes_a: list[int], nodes_b: list[int], nodes_c: list[int],
) -> list[LabelClass]:
    """Build initial label classes by (out_deg, in_deg) signature on the candidate node sets."""
    def sig(v, out_adj, in_adj):
        return (len(out_adj.get(v, ())), len(in_adj.get(v, ())))

    by_a: dict[tuple, list[int]] = defaultdict(list)
    by_b: dict[tuple, list[int]] = defaultdict(list)
    by_c: dict[tuple, list[int]] = defaultdict(list)
    for v in nodes_a:
        by_a[sig(v, out_a, in_a)].append(v)
    for v in nodes_b:
        by_b[sig(v, out_b, in_b)].append(v)
    for v in nodes_c:
        by_c[sig(v, out_c, in_c)].append(v)

    return [
        (by_a[s][:], by_b[s][:], by_c[s][:])
        for s in by_a
        if s in by_b and s in by_c
    ]


def _refine(
    classes: list[LabelClass],
    va: int, vb: int, vc: int,
    out_a: dict[int, set[int]],
    out_b: dict[int, set[int]],
    out_c: dict[int, set[int]],
) -> list[LabelClass]:
    """Split each class by consistent directed-edge type to (va, vb, vc); discard mismatches."""
    new_classes: list[LabelClass] = []
    for sa, sb, sc in classes:
        bta: dict[int, list[int]] = defaultdict(list)
        btb: dict[int, list[int]] = defaultdict(list)
        btc: dict[int, list[int]] = defaultdict(list)
        for x in sa:
            bta[_edge_type(out_a, x, va)].append(x)
        for x in sb:
            btb[_edge_type(out_b, x, vb)].append(x)
        for x in sc:
            btc[_edge_type(out_c, x, vc)].append(x)
        for t in set(bta) & set(btb) & set(btc):
            na, nb, nc = bta[t], btb[t], btc[t]
            if na and nb and nc:
                new_classes.append((na, nb, nc))
    return new_classes


def _upper_bound(current_size: int, classes: list[LabelClass]) -> int:
    return current_size + sum(min(len(a), len(b), len(c)) for a, b, c in classes)


def mcsplit_3graph(
    out_a: dict[int, set[int]], in_a: dict[int, set[int]],
    out_b: dict[int, set[int]], in_b: dict[int, set[int]],
    out_c: dict[int, set[int]], in_c: dict[int, set[int]],
    nodes_a: list[int], nodes_b: list[int], nodes_c: list[int],
    *,
    best_known: int = 0,
    connected: bool = True,
    timeout_s: float = 300.0,
) -> list[tuple[int, int, int]] | None:
    """Return best mapping (list of (va,vb,vc)) that strictly beats best_known, or None."""

    deadline = time.perf_counter() + timeout_s
    state: dict[str, Any] = {"best": best_known, "best_mapping": None}

    initial_classes = _initial_classes(
        out_a, in_a, out_b, in_b, out_c, in_c, nodes_a, nodes_b, nodes_c
    )

    def search(
        mapping: list[tuple[int, int, int]],
        classes: list[LabelClass],
        mapped_a: set[int],
        mapped_b: set[int],
        mapped_c: set[int],
    ) -> None:
        if time.perf_counter() > deadline:
            return
        if _upper_bound(len(mapping), classes) <= state["best"]:
            return

        if not classes:
            if len(mapping) > state["best"]:
                state["best"] = len(mapping)
                state["best_mapping"] = mapping[:]
            return

        # Pick class with largest min-size (best upper-bound contribution)
        cls_idx = max(
            range(len(classes)),
            key=lambda i: min(len(classes[i][0]), len(classes[i][1]), len(classes[i][2])),
        )
        sa, sb, sc = classes[cls_idx]

        # Branch on each vertex in the smallest list of this class
        sizes = (len(sa), len(sb), len(sc))
        min_idx = sizes.index(min(sizes))
        branch_list = (sa, sb, sc)[min_idx]

        for v_fixed in branch_list:
            if time.perf_counter() > deadline:
                return
            if min_idx == 0:
                pool1, pool2 = sb, sc
            elif min_idx == 1:
                pool1, pool2 = sa, sc
            else:
                pool1, pool2 = sa, sb

            for vp1 in pool1:
                for vp2 in pool2:
                    if time.perf_counter() > deadline:
                        return

                    if min_idx == 0:
                        va, vb, vc = v_fixed, vp1, vp2
                    elif min_idx == 1:
                        va, vb, vc = vp1, v_fixed, vp2
                    else:
                        va, vb, vc = vp1, vp2, v_fixed

                    # Connectivity: skip if no graph has an edge to already-mapped nodes
                    if connected and mapping:
                        def adj(out, inn, x, mp):
                            return bool(out.get(x, set()) & mp or inn.get(x, set()) & mp)
                        if not (adj(out_a, in_a, va, mapped_a) and
                                adj(out_b, in_b, vb, mapped_b) and
                                adj(out_c, in_c, vc, mapped_c)):
                            continue

                    # Build all_remaining: ALL current classes with va/vb/vc removed
                    all_remaining: list[LabelClass] = []
                    for cls_a, cls_b, cls_c in classes:
                        new_a = [x for x in cls_a if x != va]
                        new_b = [x for x in cls_b if x != vb]
                        new_c = [x for x in cls_c if x != vc]
                        if new_a and new_b and new_c:
                            all_remaining.append((new_a, new_b, new_c))

                    new_classes = _refine(all_remaining, va, vb, vc, out_a, out_b, out_c)
                    mapping.append((va, vb, vc))
                    mapped_a.add(va)
                    mapped_b.add(vb)
                    mapped_c.add(vc)
                    search(mapping, new_classes, mapped_a, mapped_b, mapped_c)
                    mapping.pop()
                    mapped_a.discard(va)
                    mapped_b.discard(vb)
                    mapped_c.discard(vc)

        # Skip this class entirely (no vertex from it matched in this branch)
        rest = classes[:cls_idx] + classes[cls_idx + 1:]
        search(mapping, rest, mapped_a, mapped_b, mapped_c)

    search([], initial_classes, set(), set(), set())
    return state["best_mapping"]
