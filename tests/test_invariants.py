"""Tests for src.invariants — directed 1-WL color refinement + cross-dataset pool.

Toy graphs with hand-computed answers; tmp output dir so nothing touches data/raw or results/.
Mirrors the style of tests/test_characterize.py.

WL is NECESSARY-not-sufficient: same color ⇒ *possible* match (never confirmed); different color ⇒
*impossible* match. Test 6 is the canonical witness that WL must not over-separate.
"""
from __future__ import annotations

import numpy as np

from src.invariants import WLResult, color_classes, directed_wl
from src.io.loader import Dataset


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ds(name: str, edges: list[tuple[str, str]]) -> Dataset:
    """Build a Dataset directly from string-id edge pairs (deduped, like the loader)."""
    int_to_id: list[str] = []
    id_to_int: dict[str, int] = {}

    def intern(s: str) -> int:
        i = id_to_int.get(s)
        if i is None:
            i = len(int_to_id)
            id_to_int[s] = i
            int_to_id.append(s)
        return i

    eset = {(intern(u), intern(v)) for u, v in edges}
    return Dataset(name=name, int_to_id=int_to_id, id_to_int=id_to_int, edges=eset)


def color_of(ds: Dataset, res: WLResult, sid: str) -> int:
    """Color (as a plain int) of the node with string id *sid*."""
    return int(res.colors[ds.id_to_int[sid]])


def cfg(**overrides) -> dict:
    c = {
        "seed": 123,
        "invariants": {
            "wl_max_iterations": 5,
            "min_datasets_per_color_class": 3,
            "gdv_enabled": False,
            "gdv_sample_fraction": 0.05,
        },
    }
    c["invariants"].update(overrides)
    return c


# ---------------------------------------------------------------------------
# 1. Depth-0 initialization = (in_degree, out_degree)
# ---------------------------------------------------------------------------

def test_init_color_is_in_out_degree():
    # A->C, B->C : A(0,1), B(0,1), C(2,0).  A and B share (in,out); C differs.
    ds = make_ds("init", [("A", "C"), ("B", "C")])
    res = directed_wl(ds, max_iterations=0)  # 0 rounds == pure depth-0 coloring
    assert color_of(ds, res, "A") == color_of(ds, res, "B")
    assert color_of(ds, res, "A") != color_of(ds, res, "C")
    assert res.depth == 0 and res.rounds_run == 0


def test_init_direction_matters():
    # A->B : A is a pure source (0,1), B a pure sink (1,0) — never conflated.
    ds = make_ds("dir", [("A", "B")])
    res = directed_wl(ds, max_iterations=0)
    assert color_of(ds, res, "A") != color_of(ds, res, "B")


# ---------------------------------------------------------------------------
# 2. Refinement separates nodes equal at depth 0 but differing by neighborhood
# ---------------------------------------------------------------------------

def test_refinement_separates_by_neighbor_color():
    # A->B, C->D, D->E.
    #   A(0,1), C(0,1) share depth-0 color; B(1,0), E(1,0) share depth-0 color.
    #   A's out-neighbor B is a sink (1,0); C's out-neighbor D is (1,1) -> A,C must separate at r>=1.
    ds = make_ds("refine", [("A", "B"), ("C", "D"), ("D", "E")])
    d0 = directed_wl(ds, max_iterations=0)
    assert color_of(ds, d0, "A") == color_of(ds, d0, "C")  # equal before refinement
    d1 = directed_wl(ds, max_iterations=1)
    assert color_of(ds, d1, "A") != color_of(ds, d1, "C")  # separated after one round


# ---------------------------------------------------------------------------
# 3. Convergence / stabilization diagnostics
# ---------------------------------------------------------------------------

def test_stabilization_round_recorded():
    # Path A->B->C->D. depth0: {A},{B,C},{D} = 3 classes; round1 splits B|C -> 4; then stable.
    ds = make_ds("path4", [("A", "B"), ("B", "C"), ("C", "D")])
    res = directed_wl(ds, max_iterations=5)
    assert res.num_classes == 4
    assert res.stabilized_at_round == 1
    assert res.rounds_run == 5 and res.depth == 5  # always runs the full budget (comparability)


def test_partition_stable_under_extra_iterations():
    # Reciprocal triangle: fully symmetric, all nodes one class, stable from round 0.
    edges = [("A", "B"), ("B", "A"), ("B", "C"), ("C", "B"), ("C", "A"), ("A", "C")]
    ds = make_ds("tri", edges)
    assert directed_wl(ds, max_iterations=2).num_classes == 1
    assert directed_wl(ds, max_iterations=20).num_classes == 1
    assert directed_wl(ds, max_iterations=5).stabilized_at_round == 0


# ---------------------------------------------------------------------------
# 4. Cross-dataset comparability (colors are content hashes, no shared table)
# ---------------------------------------------------------------------------

def test_isomorphic_graphs_in_two_datasets_share_colors():
    # Same structure, disjoint string ids -> identical multiset of color keys.
    a = make_ds("A", [("a1", "a2"), ("a2", "a3"), ("a3", "a1"), ("a1", "a3")])
    b = make_ds("B", [("b1", "b2"), ("b2", "b3"), ("b3", "b1"), ("b1", "b3")])
    ra = directed_wl(a, max_iterations=5)
    rb = directed_wl(b, max_iterations=5)
    assert sorted(int(x) for x in ra.colors) == sorted(int(x) for x in rb.colors)


def test_non_isomorphic_graphs_differ():
    # A directed triangle vs a 3-node feed-forward path: disjoint color sets.
    tri = make_ds("tri", [("x", "y"), ("y", "z"), ("z", "x")])
    path = make_ds("path", [("p", "q"), ("q", "r")])
    ct = {int(x) for x in directed_wl(tri, max_iterations=5).colors}
    cp = {int(x) for x in directed_wl(path, max_iterations=5).colors}
    assert ct.isdisjoint(cp)


# ---------------------------------------------------------------------------
# 5. NECESSARY-NOT-SUFFICIENT (the required witness)
# ---------------------------------------------------------------------------

def test_wl_does_not_separate_equivalent_but_non_isomorphic_vertices():
    """Directed 6-cycle vs two directed 3-cycles.

    Every vertex has in-degree 1 and out-degree 1, so 1-WL never refines — all vertices in both
    graphs collapse to a single color. A vertex of the 6-cycle and a vertex of a 3-cycle are NOT
    isomorphic as rooted structures of their whole graphs, yet WL gives them the *same* color.
    WL must not wrongly separate them: same color is necessary, never sufficient.
    """
    six = make_ds("six", [("c0", "c1"), ("c1", "c2"), ("c2", "c3"),
                          ("c3", "c4"), ("c4", "c5"), ("c5", "c0")])
    two3 = make_ds("two3", [("a", "b"), ("b", "c"), ("c", "a"),
                            ("d", "e"), ("e", "f"), ("f", "d")])
    r6 = directed_wl(six, max_iterations=5)
    r3 = directed_wl(two3, max_iterations=5)
    assert r6.num_classes == 1 and r3.num_classes == 1
    # The single color is identical across the two non-isomorphic graphs.
    assert color_of(six, r6, "c0") == color_of(two3, r3, "a")


# ---------------------------------------------------------------------------
# 6. Cross-dataset candidate pool
# ---------------------------------------------------------------------------

def _result_from_colors(colors: list[int]) -> WLResult:
    arr = np.array(colors, dtype=np.uint64)
    return WLResult(colors=arr, num_classes=len(set(colors)),
                    stabilized_at_round=0, rounds_run=0, depth=0)


def test_color_classes_keeps_only_multi_dataset_colors():
    # Three datasets; color 100 in all three, 200 in two, 300 in one.
    dA = Dataset(name="A", int_to_id=["A1", "A2"], id_to_int={"A1": 0, "A2": 1})
    dB = Dataset(name="B", int_to_id=["B1", "B2"], id_to_int={"B1": 0, "B2": 1})
    dC = Dataset(name="C", int_to_id=["C1"], id_to_int={"C1": 0})
    datasets = {"A": dA, "B": dB, "C": dC}
    results = {
        "A": _result_from_colors([100, 200]),
        "B": _result_from_colors([100, 200]),
        "C": _result_from_colors([100]),
    }
    # min_datasets = 3 -> only color 100 survives (present in A,B,C).
    classes = color_classes(results, datasets, min_datasets=3)
    assert len(classes) == 1
    cc = classes[0]
    assert cc.color == 100
    assert cc.num_datasets == 3
    assert cc.members["A"] == ["A1"] and cc.members["B"] == ["B1"] and cc.members["C"] == ["C1"]
    assert cc.sizes == {"A": 1, "B": 1, "C": 1}

    # min_datasets = 2 -> colors 100 (3 datasets) and 200 (A,B) both survive.
    classes2 = color_classes(results, datasets, min_datasets=2)
    colors2 = {c.color for c in classes2}
    assert colors2 == {100, 200}


# ---------------------------------------------------------------------------
# 7. Optional GDV guard (graceful skip; no orca binary required)
# ---------------------------------------------------------------------------

def test_gdv_skipped_when_disabled():
    from src.invariants import gdv

    ds = make_ds("g", [("A", "B"), ("B", "A")])
    assert gdv.gdv_signatures(ds, cfg(gdv_enabled=False)) is None


def test_gdv_missing_binary_returns_none(recwarn):
    from src.invariants import gdv

    ds = make_ds("g", [("A", "B"), ("B", "A")])
    c = cfg(gdv_enabled=True, orca_path="/nonexistent/orca-binary-xyz")
    assert gdv.gdv_available(c) is False
    # Enabled but missing binary: graceful skip (returns None, warns, never raises).
    assert gdv.gdv_signatures(ds, c) is None


# ---------------------------------------------------------------------------
# 8. The WL impl must not depend on a graph library (it's the cheap filter, scipy-only)
# ---------------------------------------------------------------------------

def test_wl_import_is_networkx_free():
    import subprocess
    import sys

    code = "import src.invariants.wl, sys; print('networkx' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
