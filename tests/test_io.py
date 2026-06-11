"""Tests for src.io — the data IO layer.

Toy CSVs are written into tmp_path so the tests are self-contained and never touch data/raw.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from src.io import Dataset, build_adjacency, load_edge_list

HEADER = "source neuron id,target neuron id\n"


def _write(tmp_path: Path, rows: str, name: str = "toy.csv") -> Path:
    p = tmp_path / name
    p.write_text(HEADER + textwrap.dedent(rows).lstrip("\n"))
    return p


# ---------------------------------------------------------------------------
# Core loader
# ---------------------------------------------------------------------------

def test_header_skipped_and_basic_counts(tmp_path):
    p = _write(tmp_path, """
        10,20
        20,30
    """)
    ds = load_edge_list(p, name="toy")
    assert isinstance(ds, Dataset)
    assert ds.name == "toy"
    assert ds.num_nodes == 3            # 10, 20, 30
    assert ds.num_edges == 2
    # header text must never become a node
    assert "source neuron id" not in ds.id_to_int


def test_self_loop_dropped_by_default(tmp_path):
    p = _write(tmp_path, """
        1,1
        1,2
    """)
    ds = load_edge_list(p)
    assert ds.num_edges == 1
    u, v = next(iter(ds.edges))
    assert ds.int_to_id[u] == "1" and ds.int_to_id[v] == "2"


def test_self_loop_retained_when_disabled(tmp_path):
    p = _write(tmp_path, """
        1,1
        1,2
    """)
    ds = load_edge_list(p, drop_self_loops=False)
    assert ds.num_edges == 2


def test_parallel_edges_collapsed_by_default(tmp_path):
    p = _write(tmp_path, """
        5,6
        5,6
        5,6
    """)
    ds = load_edge_list(p)
    assert ds.num_edges == 1


def test_parallel_edges_retained_when_disabled(tmp_path):
    p = _write(tmp_path, """
        5,6
        5,6
        5,6
    """)
    ds = load_edge_list(p, collapse_parallel_edges=False)
    assert ds.num_edges == 3


def test_string_ids_preserved_18_digit(tmp_path):
    big_a = "720575940621234567"   # 18-digit root id, > 2**53 and > int64-safe handling
    big_b = "720575940629876543"
    p = _write(tmp_path, f"""
        {big_a},{big_b}
    """)
    ds = load_edge_list(p)
    # round-trips exactly as a string; never coerced to int
    assert big_a in ds.id_to_int
    assert big_b in ds.id_to_int
    assert all(isinstance(x, str) for x in ds.int_to_id)
    u = ds.id_to_int[big_a]
    assert ds.int_to_id[u] == big_a    # exact, full-precision round-trip


def test_node_set_is_endpoints_only(tmp_path):
    # every mapped node must be an endpoint of some edge — no degree-0 vertices
    p = _write(tmp_path, """
        1,2
        2,3
        3,1
    """)
    ds = load_edge_list(p)
    out, inn = build_adjacency(ds)
    for i in range(ds.num_nodes):
        assert out[i] or inn[i]


def test_blank_lines_ignored(tmp_path):
    p = tmp_path / "blanks.csv"
    p.write_text(HEADER + "1,2\n\n2,3\n\n")
    ds = load_edge_list(p)
    assert ds.num_edges == 2


# ---------------------------------------------------------------------------
# Adjacency (verifier representation)
# ---------------------------------------------------------------------------

def test_adjacency_distinguishes_direction(tmp_path):
    p = _write(tmp_path, """
        a,b
    """, name="dir.csv")
    # ids are strings regardless of being non-numeric
    ds = load_edge_list(p)
    out, inn = build_adjacency(ds)
    a = ds.id_to_int["a"]
    b = ds.id_to_int["b"]
    assert out[a] == {b}
    assert inn[b] == {a}
    assert out[b] == set()
    assert inn[a] == set()


def test_adjacency_covers_all_nodes(tmp_path):
    p = _write(tmp_path, """
        1,2
        2,3
    """)
    ds = load_edge_list(p)
    out, inn = build_adjacency(ds)
    assert set(out.keys()) == set(range(ds.num_nodes))
    assert set(inn.keys()) == set(range(ds.num_nodes))


# ---------------------------------------------------------------------------
# igraph builders (engine representation) — live in src.io.graphs
# ---------------------------------------------------------------------------

def test_to_igraph_directed_with_names(tmp_path):
    from src.io.graphs import to_igraph
    p = _write(tmp_path, """
        1,2
        2,3
    """)
    ds = load_edge_list(p)
    g = to_igraph(ds)
    assert g.is_directed()
    assert g.vcount() == ds.num_nodes
    assert g.ecount() == ds.num_edges
    assert list(g.vs["name"]) == ds.int_to_id


def test_reciprocal_igraph_mutual_edges_only(tmp_path):
    from src.io.graphs import to_reciprocal_igraph
    # 1<->2 mutual; 2->3 one-way; 3,3 self-loop (dropped at load)
    p = _write(tmp_path, """
        1,2
        2,1
        2,3
    """)
    ds = load_edge_list(p)
    g = to_reciprocal_igraph(ds)
    assert not g.is_directed()
    assert g.vcount() == ds.num_nodes        # node set preserved (3 is isolated here)
    assert g.ecount() == 1                    # only the 1<->2 pair
    n1, n2 = ds.id_to_int["1"], ds.id_to_int["2"]
    src, tgt = g.es[0].tuple
    assert {ds.int_to_id[src], ds.int_to_id[tgt]} == {"1", "2"}
    n3 = ds.id_to_int["3"]
    assert g.degree(n3) == 0


# ---------------------------------------------------------------------------
# Hard rule: the verifier path must import src.io without pulling in igraph
# ---------------------------------------------------------------------------

def test_importing_src_io_does_not_import_igraph():
    code = (
        "import sys; import src.io; "
        "from src.io import load_edge_list, build_adjacency, Dataset; "
        "assert 'igraph' not in sys.modules, 'src.io must not import igraph'; "
        "print('OK')"
    )
    repo_root = Path(__file__).resolve().parent.parent
    res = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root, capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    assert "OK" in res.stdout
