"""Tests for Engine A — canonical, correct-by-construction families.

Toy in-memory Datasets (no file IO), mirroring tests/test_invariants.py. Each family is built so that
equal-size instances are automatically isomorphic; the frontier assembler aligns three per-dataset
instances and the *verifier* (src.verify) confirms induced isomorphism + weak connectivity.
"""
from __future__ import annotations

from src.engine_a.biclique import complete_bipartite
from src.engine_a.clique import reciprocal_clique
from src.engine_a.frontier import assemble_frontier
from src.engine_a.star import directed_star
from src.io.loader import Dataset
from src.verify.check import verify_candidate


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


def recip(nodes: list[str]) -> list[tuple[str, str]]:
    """All ordered pairs (both directions) — a reciprocal clique on *nodes*."""
    return [(u, v) for u in nodes for v in nodes if u != v]


def cfg(**ov) -> dict:
    c = {
        "seed": 7,
        "engine_a": {
            "clique": {"restarts": 10, "time_budget_s": 30},
            "star": {"min_hub_out_degree": 2},
            "biclique": {"enabled": True, "time_budget_s": 30},
        },
    }
    c["engine_a"].update(ov)
    return c


def edge(ds: Dataset, u: str, v: str) -> bool:
    return (ds.id_to_int[u], ds.id_to_int[v]) in ds.edges


# ---------------------------------------------------------------------------
# 1. Reciprocal clique
# ---------------------------------------------------------------------------

def test_reciprocal_clique_finds_k4():
    # reciprocal K4 on {a,b,c,d}, plus one-directional noise (not in the reciprocal graph)
    edges = recip(["a", "b", "c", "d"]) + [("a", "e"), ("e", "f")]
    ds = make_ds("D", edges)
    r = reciprocal_clique(ds, cfg())
    assert r["family"] == "reciprocal_clique"
    assert r["n"] == 4
    assert set(r["members"]) == {"a", "b", "c", "d"}
    assert r["upper_bound"] >= 4  # degeneracy+1 of the reciprocal graph
    # every ordered pair of members is reciprocal
    m = r["members"]
    assert all(edge(ds, u, v) and edge(ds, v, u) for u in m for v in m if u != v)


def test_reciprocal_clique_members_are_strings():
    ds = make_ds("D", recip(["100000000000000001", "100000000000000002", "100000000000000003"]))
    r = reciprocal_clique(ds, cfg())
    assert all(isinstance(x, str) for x in r["members"])
    assert r["n"] == 3


# ---------------------------------------------------------------------------
# 2. Directed star — both orientations
# ---------------------------------------------------------------------------

def test_directed_star_out_drops_dependent_leaf():
    # hub H -> {L1..L4}; an edge L1->L2 inside the leaves forces the IS to drop one leaf
    edges = [("H", "L1"), ("H", "L2"), ("H", "L3"), ("H", "L4"), ("L1", "L2")]
    ds = make_ds("D", edges)
    r = directed_star(ds, cfg())
    assert r["family"] == "directed_star"
    assert r["orientation"] == "out"
    assert r["hub"] == "H"
    assert r["n"] == 4  # hub + 3 independent leaves
    leaves = set(r["leaves"])
    assert len(leaves) == 3 and leaves <= {"L1", "L2", "L3", "L4"}
    # pure out-star: no leaf->hub, no leaf<->leaf
    assert all(not edge(ds, lf, "H") for lf in leaves)
    assert all(not edge(ds, a, b) for a in leaves for b in leaves if a != b)


def test_directed_star_picks_larger_in_orientation():
    # in-star: La..Le -> C, all leaves independent → in-star of size 6 beats any out-star
    edges = [(f"L{i}", "C") for i in "abcde"]
    ds = make_ds("Din", edges)
    r = directed_star(ds, cfg())
    assert r["orientation"] == "in"
    assert r["hub"] == "C"
    assert r["n"] == 6
    leaves = set(r["leaves"])
    assert leaves == {f"L{i}" for i in "abcde"}
    assert all(edge(ds, lf, "C") and not edge(ds, "C", lf) for lf in leaves)


# ---------------------------------------------------------------------------
# 3. Complete bipartite (gated)
# ---------------------------------------------------------------------------

def test_complete_bipartite_k23():
    A, B = ["a1", "a2"], ["b1", "b2", "b3"]
    edges = [(a, b) for a in A for b in B]
    ds = make_ds("Dbc", edges)
    r = complete_bipartite(ds, cfg())
    assert r["family"] == "complete_bipartite"
    assert r["n"] == 5
    assert {len(r["part_a"]), len(r["part_b"])} == {2, 3}
    pa, pb = set(r["part_a"]), set(r["part_b"])
    # all A->B present, no within-part, no B->A
    assert all(edge(ds, a, b) for a in pa for b in pb)
    assert all(not edge(ds, x, y) for x in pa for y in pa if x != y)
    assert all(not edge(ds, x, y) for x in pb for y in pb if x != y)
    assert all(not edge(ds, b, a) for b in pb for a in pa)


def test_complete_bipartite_disabled_is_skipped():
    ds = make_ds("Dbc", [("a1", "b1"), ("a1", "b2"), ("a2", "b1"), ("a2", "b2")])
    r = complete_bipartite(ds, cfg(biclique={"enabled": False, "time_budget_s": 30}))
    assert r["skipped"] is True
    assert r["n"] == 0


# ---------------------------------------------------------------------------
# 4. Frontier — assemble across a triple and confirm with the verifier
# ---------------------------------------------------------------------------

def _clique_instances(datasets: dict[str, Dataset]) -> dict:
    return {"reciprocal_clique": {n: reciprocal_clique(ds, cfg()) for n, ds in datasets.items()}}


def test_frontier_clique_triple_verifies():
    datasets = {
        "MANC": make_ds("MANC", recip(["x1", "x2", "x3", "x4"])),
        "MAOL": make_ds("MAOL", recip(["y1", "y2", "y3", "y4"])),
        "MCNS": make_ds("MCNS", recip(["z1", "z2", "z3", "z4"])),
    }
    rows = assemble_frontier(_clique_instances(datasets), datasets)
    clique_rows = [r for r in rows if r["family"] == "reciprocal_clique" and r["ok"]]
    assert len(clique_rows) == 1
    row = clique_rows[0]
    assert row["n"] == 4
    assert tuple(sorted(row["triple"])) == ("MANC", "MAOL", "MCNS")
    # independently re-verify via the oracle
    rep = verify_candidate(row["columns"], row["candidate_rows"], datasets)
    assert rep.ok and rep.n == 4 and rep.structure == "clique"


def test_frontier_truncates_to_min_size():
    datasets = {
        "MANC": make_ds("MANC", recip(["x1", "x2", "x3", "x4", "x5"])),  # K5
        "MAOL": make_ds("MAOL", recip(["y1", "y2", "y3", "y4"])),        # K4
        "MCNS": make_ds("MCNS", recip(["z1", "z2", "z3", "z4"])),        # K4
    }
    rows = assemble_frontier(_clique_instances(datasets), datasets)
    row = [r for r in rows if r["family"] == "reciprocal_clique" and r["ok"]][0]
    assert row["n"] == 4
    assert verify_candidate(row["columns"], row["candidate_rows"], datasets).ok


def test_frontier_star_triple_verifies():
    def star_ds(name: str, p: str) -> Dataset:
        return make_ds(name, [(f"{p}H", f"{p}L{i}") for i in range(4)])

    datasets = {
        "BANC": star_ds("BANC", "a"),
        "FAFB": star_ds("FAFB", "b"),
        "MCNS": star_ds("MCNS", "c"),
    }
    instances = {"directed_star": {n: directed_star(ds, cfg()) for n, ds in datasets.items()}}
    rows = assemble_frontier(instances, datasets)
    row = [r for r in rows if r["family"] == "directed_star" and r["ok"]][0]
    assert row["n"] == 5
    rep = verify_candidate(row["columns"], row["candidate_rows"], datasets)
    assert rep.ok and rep.structure == "star"


def test_frontier_biclique_triple_verifies():
    def bc_ds(name: str, p: str) -> Dataset:
        A, B = [f"{p}a1", f"{p}a2"], [f"{p}b1", f"{p}b2", f"{p}b3"]
        return make_ds(name, [(a, b) for a in A for b in B])

    datasets = {
        "BANC": bc_ds("BANC", "a"),
        "FAFB": bc_ds("FAFB", "b"),
        "MANC": bc_ds("MANC", "c"),
    }
    instances = {"complete_bipartite": {n: complete_bipartite(ds, cfg()) for n, ds in datasets.items()}}
    rows = assemble_frontier(instances, datasets)
    row = [r for r in rows if r["family"] == "complete_bipartite" and r["ok"]][0]
    assert row["n"] == 5
    rep = verify_candidate(row["columns"], row["candidate_rows"], datasets)
    assert rep.ok and rep.structure == "complete_bipartite"
