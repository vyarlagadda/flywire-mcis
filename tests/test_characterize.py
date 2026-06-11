"""Tests for src.characterize — per-dataset structural fingerprint.

Toy graphs with hand-computed answers; tmp output dir so nothing touches data/raw or results/.
Mirrors the style of tests/test_io.py.
"""
from __future__ import annotations

import json
import math

from src.characterize import characterize_dataset, compute_metrics
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


def cfg(**overrides) -> dict:
    c = {
        "seed": 123,
        "characterize": {
            "degree_tail_k": 5,
            "degree_quantiles": [0.5, 0.9, 0.99],
            "motif_size": 3,
            "dense_edge_threshold": 1_000_000,
            "motif_cut_prob": [0.0, 0.0, 0.9],
        },
    }
    c["characterize"].update(overrides)
    return c


# ---------------------------------------------------------------------------
# Counts / degree / reciprocity
# ---------------------------------------------------------------------------

def test_counts_and_density():
    # A->B, B->A, B->C : 3 nodes, 3 edges, density = 3/(3*2) = 0.5
    ds = make_ds("toy", [("A", "B"), ("B", "A"), ("B", "C")])
    m = compute_metrics(ds, cfg())
    assert m["name"] == "toy"
    assert m["counts"]["num_nodes"] == 3
    assert m["counts"]["num_edges"] == 3
    assert math.isclose(m["counts"]["density"], 0.5)


def test_degree_summaries_and_tails():
    ds = make_ds("toy", [("A", "B"), ("B", "A"), ("B", "C")])
    m = compute_metrics(ds, cfg())
    d = m["degree"]
    # out-degrees: A=1, B=2, C=0 ; in-degrees all 1 ; total: A=2,B=3,C=1
    assert d["out"]["max"] == 2 and d["out"]["min"] == 0
    assert math.isclose(d["out"]["mean"], 1.0)
    assert d["in"]["min"] == 1 and d["in"]["max"] == 1
    assert d["total"]["max"] == 3 and d["total"]["min"] == 1
    # tail: highest out-degree node is B, recorded by string id
    top_out = d["tails"]["top_out"]
    assert top_out[0]["id"] == "B" and top_out[0]["degree"] == 2
    assert all(isinstance(e["id"], str) for e in top_out)


def test_reciprocity_and_dyad_census():
    ds = make_ds("toy", [("A", "B"), ("B", "A"), ("B", "C")])
    m = compute_metrics(ds, cfg())
    r = m["reciprocity"]
    assert math.isclose(r["fraction"], 2 / 3)
    # mutual {A,B}=1, asymmetric {B,C}=1, null {A,C}=1
    assert r["dyad_census"] == {"mutual": 1, "asymmetric": 1, "null": 1}


# ---------------------------------------------------------------------------
# Coreness / degeneracy (Engine A headline)
# ---------------------------------------------------------------------------

def test_reciprocal_triangle_degeneracy():
    # Three mutual edges => reciprocal undirected graph is a triangle: degeneracy 2, clique UB 3.
    edges = [("A", "B"), ("B", "A"), ("B", "C"), ("C", "B"), ("C", "A"), ("A", "C")]
    ds = make_ds("tri", edges)
    m = compute_metrics(ds, cfg())
    c = m["coreness"]
    assert c["reciprocal_degeneracy"] == 2
    assert c["reciprocal_clique_upper_bound"] == 3
    assert c["reciprocal_edges"] == 3
    assert c["reciprocal_nonisolated_nodes"] == 3


def test_no_reciprocal_edges_gives_degeneracy_zero():
    # purely asymmetric path: no mutual edges
    ds = make_ds("path", [("A", "B"), ("B", "C")])
    m = compute_metrics(ds, cfg())
    c = m["coreness"]
    assert c["reciprocal_edges"] == 0
    assert c["reciprocal_degeneracy"] == 0
    assert c["reciprocal_clique_upper_bound"] == 1


# ---------------------------------------------------------------------------
# Directed 3-node motif census
# ---------------------------------------------------------------------------

def test_motif_three_cycle_isoclass():
    # directed 3-cycle => isoclass 11
    ds = make_ds("cycle", [("A", "B"), ("B", "C"), ("C", "A")])
    m = compute_metrics(ds, cfg())
    mot = m["motifs_size3"]
    assert mot["sampled"] is False
    assert mot["cut_prob"] is None
    assert mot["counts"][11] == 1
    # disconnected isoclasses are null, not 0
    assert mot["counts"][0] is None
    # all other connected classes are zero
    assert sum(c for c in mot["counts"] if c) == 1
    assert math.isclose(mot["profile"][11], 1.0)


def test_motif_feedforward_path_isoclass():
    # feed-forward path A->B->C => isoclass 4
    ds = make_ds("path", [("A", "B"), ("B", "C")])
    m = compute_metrics(ds, cfg())
    assert m["motifs_size3"]["counts"][4] == 1


def test_motif_sampling_flag_on_dense():
    ds = make_ds("cycle", [("A", "B"), ("B", "C"), ("C", "A")])
    # force the dense path by lowering the threshold below this graph's edge count
    m = compute_metrics(ds, cfg(dense_edge_threshold=1))
    mot = m["motifs_size3"]
    assert mot["sampled"] is True
    assert mot["cut_prob"] == [0.0, 0.0, 0.9]


# ---------------------------------------------------------------------------
# Provenance + serialization
# ---------------------------------------------------------------------------

def test_provenance_and_json_roundtrip():
    ds = make_ds("toy", [("A", "B"), ("B", "A"), ("B", "C")])
    m = compute_metrics(ds, cfg())
    assert m["seed"] == 123
    assert isinstance(m["igraph_version"], str)
    assert isinstance(m["wall_clock_s"], float)
    # JSON must be valid (NaN -> null), no bare NaN tokens
    s = json.dumps(m, allow_nan=False)
    assert "NaN" not in s


def test_characterize_dataset_writes_json(tmp_path):
    ds = make_ds("toy", [("A", "B"), ("B", "A"), ("B", "C")])
    out = characterize_dataset(ds, cfg(), tmp_path)
    assert out.exists() and out.name == "toy.json"
    loaded = json.loads(out.read_text())
    assert loaded["name"] == "toy"
    assert loaded["counts"]["num_edges"] == 3
