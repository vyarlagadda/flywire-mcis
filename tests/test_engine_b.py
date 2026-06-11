"""Tests for Engine B — k-core reduction and McSplit B&B."""
from __future__ import annotations

from src.io.loader import Dataset
from src.engine_b.reduce import kcore_reduce


def make_ds(name: str, edges: list[tuple[str, str]]) -> Dataset:
    int_to_id: list[str] = []
    id_to_int: dict[str, int] = {}

    def intern(s: str) -> int:
        if s not in id_to_int:
            id_to_int[s] = len(int_to_id)
            int_to_id.append(s)
        return id_to_int[s]

    eset = {(intern(u), intern(v)) for u, v in edges}
    return Dataset(name=name, int_to_id=int_to_id, id_to_int=id_to_int, edges=eset)


def recip(nodes: list[str]) -> list[tuple[str, str]]:
    return [(u, v) for u in nodes for v in nodes if u != v]


# ---------------------------------------------------------------------------
# k-core reduction tests
# ---------------------------------------------------------------------------

def test_kcore_removes_low_degree():
    # 4-node reciprocal clique (each node: total degree 6) + 1 pendant (degree 1)
    edges_a = recip(["a", "b", "c", "d"]) + [("d", "e")]
    edges_b = recip(["p", "q", "r", "s"]) + [("s", "t")]
    edges_c = recip(["x", "y", "z", "w"]) + [("w", "v")]
    ds_a = make_ds("A", edges_a)
    ds_b = make_ds("B", edges_b)
    ds_c = make_ds("C", edges_c)
    cert_ids = [["a", "p", "x"], ["b", "q", "y"], ["c", "r", "z"], ["d", "s", "w"], ["e", "t", "v"]]
    surviving_a, surviving_b, surviving_c = kcore_reduce(
        [ds_a, ds_b, ds_c],
        cert_ids,
        col_names=["A", "B", "C"],
        kcore_min=3,
    )
    assert "e" not in surviving_a
    assert "t" not in surviving_b
    assert "v" not in surviving_c
    assert {"a", "b", "c", "d"} <= set(surviving_a)


def test_kcore_removes_jointly():
    # Node fails threshold in ONE dataset → removed from ALL
    cert_ids = [["a", "p", "x"], ["b", "q", "y"], ["c", "r", "z"], ["d", "s", "w"], ["e", "t", "v"]]
    ds_a = make_ds("A", recip(["a", "b", "c", "d"]) + [("a", "e"), ("e", "a")])
    ds_b = make_ds("B", recip(["p", "q", "r", "s"]))  # t has no edges in cert
    ds_c = make_ds("C", recip(["x", "y", "z", "w"]))  # v has no edges in cert
    surviving_a, surviving_b, surviving_c = kcore_reduce(
        [ds_a, ds_b, ds_c],
        cert_ids,
        col_names=["A", "B", "C"],
        kcore_min=3,
    )
    assert "e" not in surviving_a
    assert "t" not in surviving_b
    assert "v" not in surviving_c


def test_kcore_stable_on_clique():
    # Reciprocal K4 has total degree 6 for every node → survives kcore_min <= 6
    cert_ids = [["a", "p", "x"], ["b", "q", "y"], ["c", "r", "z"], ["d", "s", "w"]]
    ds_a = make_ds("A", recip(["a", "b", "c", "d"]))
    ds_b = make_ds("B", recip(["p", "q", "r", "s"]))
    ds_c = make_ds("C", recip(["x", "y", "z", "w"]))
    sa, sb, sc = kcore_reduce([ds_a, ds_b, ds_c], cert_ids, ["A", "B", "C"], kcore_min=4)
    assert set(sa) == {"a", "b", "c", "d"}
    assert set(sb) == {"p", "q", "r", "s"}
    assert set(sc) == {"x", "y", "z", "w"}


# ---------------------------------------------------------------------------
# McSplit B&B tests
# ---------------------------------------------------------------------------

from src.engine_b.mcsplit import mcsplit_3graph
from src.io.loader import build_adjacency
from src.verify.check import verify_candidate


def _adj(ds: Dataset):
    return build_adjacency(ds)


def test_mcsplit_finds_k3_clique():
    ds_a = make_ds("A", recip(["a", "b", "c"]))
    ds_b = make_ds("B", recip(["p", "q", "r"]))
    ds_c = make_ds("C", recip(["x", "y", "z"]))
    out_a, in_a = _adj(ds_a)
    out_b, in_b = _adj(ds_b)
    out_c, in_c = _adj(ds_c)
    nodes_a = [ds_a.id_to_int[v] for v in ["a", "b", "c"]]
    nodes_b = [ds_b.id_to_int[v] for v in ["p", "q", "r"]]
    nodes_c = [ds_c.id_to_int[v] for v in ["x", "y", "z"]]
    mapping = mcsplit_3graph(
        out_a, in_a, out_b, in_b, out_c, in_c,
        nodes_a, nodes_b, nodes_c,
        best_known=2, connected=True, timeout_s=10.0,
    )
    assert mapping is not None
    assert len(mapping) == 3
    rows = [[ds_a.int_to_id[va], ds_b.int_to_id[vb], ds_c.int_to_id[vc]]
            for va, vb, vc in mapping]
    report = verify_candidate(["A", "B", "C"], rows, {"A": ds_a, "B": ds_b, "C": ds_c})
    assert report.ok


def test_mcsplit_connectivity_enforced():
    # Two disjoint K2 cliques; connected MCCS = 2, not 4
    def two_k2(name, p):
        return make_ds(name, [(f"{p}a1", f"{p}a2"), (f"{p}a2", f"{p}a1"),
                              (f"{p}b1", f"{p}b2"), (f"{p}b2", f"{p}b1")])

    ds_a = two_k2("A", "a")
    ds_b = two_k2("B", "b")
    ds_c = two_k2("C", "c")
    out_a, in_a = _adj(ds_a)
    out_b, in_b = _adj(ds_b)
    out_c, in_c = _adj(ds_c)
    nodes = lambda ds: list(range(ds.num_nodes))
    mapping = mcsplit_3graph(
        out_a, in_a, out_b, in_b, out_c, in_c,
        nodes(ds_a), nodes(ds_b), nodes(ds_c),
        best_known=1, connected=True, timeout_s=10.0,
    )
    assert mapping is not None
    assert len(mapping) == 2


def test_mcsplit_beats_best_known():
    ds_a = make_ds("A", recip(["a", "b", "c", "d"]))
    ds_b = make_ds("B", recip(["p", "q", "r", "s"]))
    ds_c = make_ds("C", recip(["x", "y", "z", "w"]))
    out_a, in_a = _adj(ds_a)
    out_b, in_b = _adj(ds_b)
    out_c, in_c = _adj(ds_c)
    nodes = lambda ds: list(range(ds.num_nodes))
    mapping = mcsplit_3graph(
        out_a, in_a, out_b, in_b, out_c, in_c,
        nodes(ds_a), nodes(ds_b), nodes(ds_c),
        best_known=3, connected=True, timeout_s=10.0,
    )
    assert mapping is not None and len(mapping) == 4


def test_mcsplit_returns_none_when_cannot_beat():
    ds_a = make_ds("A", recip(["a", "b", "c"]))
    ds_b = make_ds("B", recip(["p", "q", "r"]))
    ds_c = make_ds("C", recip(["x", "y", "z"]))
    out_a, in_a = _adj(ds_a)
    out_b, in_b = _adj(ds_b)
    out_c, in_c = _adj(ds_c)
    nodes = lambda ds: list(range(ds.num_nodes))
    mapping = mcsplit_3graph(
        out_a, in_a, out_b, in_b, out_c, in_c,
        nodes(ds_a), nodes(ds_b), nodes(ds_c),
        best_known=3, connected=True, timeout_s=10.0,
    )
    assert mapping is None
