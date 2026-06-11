"""Tests for src.verify — the independent verifier / grading oracle.

The verifier mirrors FlyWire's grading: directed induced isomorphism under the row alignment plus
weak connectivity, using plain dict/set adjacency and NO graph library. These tests target the pure
engine ``verify_candidate(columns, rows, datasets)`` directly with toy graphs built by the real
loader; the file/CLI path and the no-graph-library hard rule are covered via subprocess.

Checks, in order: (1) structural, (2) existence, (3) induced isomorphism, (4) weak connectivity.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from src.io import load_edge_list
from src.verify.check import Report, verify_candidate, verify_file

HEADER = "source neuron id,target neuron id\n"

# 18-digit root ids (BANC/FAFB style) — must round-trip as strings, never int64.
B1 = "720575940600000001"
B2 = "720575940600000002"
B3 = "720575940600000003"
B4 = "720575940600000004"


def _write(tmp_path: Path, rows: str, name: str) -> Path:
    p = tmp_path / name
    p.write_text(HEADER + textwrap.dedent(rows).lstrip("\n"))
    return p


def _ds(tmp_path: Path, name: str, rows: str):
    """Build a Dataset from a toy edge list (one file per dataset name)."""
    return load_edge_list(_write(tmp_path, rows, f"{name}.csv"), name=name)


# ---------------------------------------------------------------------------
# Toy-graph builders: the SAME induced shape across three differently-labelled graphs.
# Each graph also carries extra nodes/edges so the match is genuinely *induced*,
# not the whole graph.
# ---------------------------------------------------------------------------

def _triangle_datasets(tmp_path):
    """Reciprocal triangle on the three chosen nodes, embedded with extra structure."""
    g1 = _ds(tmp_path, "G1", """
        1,2
        2,1
        2,3
        3,2
        1,3
        3,1
        1,9
        9,1
    """)
    g2 = _ds(tmp_path, "G2", """
        a,b
        b,a
        b,c
        c,b
        a,c
        c,a
        a,z
    """)
    g3 = _ds(tmp_path, "G3", f"""
        {B1},{B2}
        {B2},{B1}
        {B2},{B3}
        {B3},{B2}
        {B1},{B3}
        {B3},{B1}
        {B1},720575940600000099
    """)
    datasets = {"G1": g1, "G2": g2, "G3": g3}
    rows = [["1", "a", B1], ["2", "b", B2], ["3", "c", B3]]
    return datasets, rows


# ---------------------------------------------------------------------------
# The five spec'd tests
# ---------------------------------------------------------------------------

def test_positive_clique_passes(tmp_path):
    datasets, rows = _triangle_datasets(tmp_path)
    rep = verify_candidate(["G1", "G2", "G3"], rows, datasets)
    assert isinstance(rep, Report)
    assert rep.ok
    assert rep.failed_check is None
    assert rep.n == 3
    assert rep.datasets == ("G1", "G2", "G3")
    assert rep.structure == "clique"
    # all four checks executed and passed
    assert len(rep.checks) == 4
    assert all(c.passed for c in rep.checks)


def test_one_differing_edge_fails_check3_names_pair(tmp_path):
    datasets, rows = _triangle_datasets(tmp_path)
    # In G3, drop the 1->3 (row0 -> row2) edge while keeping the reverse; G1/G2 still have it.
    datasets["G3"] = _ds(tmp_path, "G3", f"""
        {B1},{B2}
        {B2},{B1}
        {B2},{B3}
        {B3},{B2}
        {B3},{B1}
        {B1},720575940600000099
    """)
    rep = verify_candidate(["G1", "G2", "G3"], rows, datasets)
    assert not rep.ok
    assert rep.failed_check == 3
    assert "row 0" in rep.reason and "row 2" in rep.reason
    assert "G3" in rep.reason  # names the dataset that disagrees


def test_isomorphic_but_disconnected_fails_check4(tmp_path):
    # Two disjoint reciprocal edges {0,1} and {2,3}, identical across all three datasets.
    g1 = _ds(tmp_path, "G1", """
        1,2
        2,1
        3,4
        4,3
    """)
    g2 = _ds(tmp_path, "G2", """
        p,q
        q,p
        r,s
        s,r
    """)
    g3 = _ds(tmp_path, "G3", f"""
        {B1},{B2}
        {B2},{B1}
        {B3},{B4}
        {B4},{B3}
    """)
    datasets = {"G1": g1, "G2": g2, "G3": g3}
    rows = [["1", "p", B1], ["2", "q", B2], ["3", "r", B3], ["4", "s", B4]]
    rep = verify_candidate(["G1", "G2", "G3"], rows, datasets)
    assert not rep.ok
    assert rep.failed_check == 4
    assert "2 components" in rep.reason
    # check 3 (iso) must have passed before we reached connectivity
    assert rep.checks[2].index == 3 and rep.checks[2].passed


def test_nonexistent_id_fails_check2(tmp_path):
    datasets, rows = _triangle_datasets(tmp_path)
    rows[1][1] = "nonexistent"  # row 1, column G2
    rep = verify_candidate(["G1", "G2", "G3"], rows, datasets)
    assert not rep.ok
    assert rep.failed_check == 2
    assert "nonexistent" in rep.reason
    assert "G2" in rep.reason


def test_duplicate_id_in_column_fails_check1(tmp_path):
    datasets, rows = _triangle_datasets(tmp_path)
    rows[2][0] = "1"  # column G1 now has "1" in rows 0 and 2
    rep = verify_candidate(["G1", "G2", "G3"], rows, datasets)
    assert not rep.ok
    assert rep.failed_check == 1
    assert "duplicate" in rep.reason.lower()
    assert "G1" in rep.reason


# ---------------------------------------------------------------------------
# Structural boundaries (check 1) and ordering
# ---------------------------------------------------------------------------

def test_wrong_column_count_fails_check1(tmp_path):
    datasets, _ = _triangle_datasets(tmp_path)
    rep2 = verify_candidate(["G1", "G2"], [["1", "a"], ["2", "b"]], datasets)
    assert rep2.failed_check == 1 and "3 column" in rep2.reason
    rep4 = verify_candidate(
        ["G1", "G2", "G3", "G4"],
        [["1", "a", B1, "x"], ["2", "b", B2, "y"]],
        datasets,
    )
    assert rep4.failed_check == 1 and "3 column" in rep4.reason


def test_empty_candidate_fails_check1(tmp_path):
    datasets, _ = _triangle_datasets(tmp_path)
    rep = verify_candidate(["G1", "G2", "G3"], [], datasets)
    assert rep.failed_check == 1
    assert "at least 2" in rep.reason


def test_single_row_fails_check1(tmp_path):
    # N == 1 is degenerate (A13): a single neuron is a vacuous circuit -> hard fail.
    datasets, _ = _triangle_datasets(tmp_path)
    rep = verify_candidate(["G1", "G2", "G3"], [["1", "a", B1]], datasets)
    assert rep.failed_check == 1
    assert "at least 2" in rep.reason


def test_missing_cell_fails_check1(tmp_path):
    datasets, _ = _triangle_datasets(tmp_path)
    rows = [["1", "a", B1], ["2", "", B2]]  # row 1, column G2 empty
    rep = verify_candidate(["G1", "G2", "G3"], rows, datasets)
    assert rep.failed_check == 1
    assert "row 1" in rep.reason


def test_checks_short_circuit_in_order(tmp_path):
    # Candidate violates BOTH check 1 (duplicate id in G1) and check 2 (bad id in G2).
    # The earliest failing check (1) must be the one reported.
    datasets, _ = _triangle_datasets(tmp_path)
    rows = [["1", "nonexistent", B1], ["1", "b", B2]]
    rep = verify_candidate(["G1", "G2", "G3"], rows, datasets)
    assert rep.failed_check == 1


# ---------------------------------------------------------------------------
# Structure detection (informational; never affects pass/fail)
# ---------------------------------------------------------------------------

def test_star_structure_detected(tmp_path):
    # Out-star: one center -> three leaves, identical across datasets.
    g1 = _ds(tmp_path, "G1", "1,2\n1,3\n1,4\n")
    g2 = _ds(tmp_path, "G2", "p,q\np,r\np,s\n")
    g3 = _ds(tmp_path, "G3", f"{B1},{B2}\n{B1},{B3}\n{B1},{B4}\n")
    datasets = {"G1": g1, "G2": g2, "G3": g3}
    rows = [["1", "p", B1], ["2", "q", B2], ["3", "r", B3], ["4", "s", B4]]
    rep = verify_candidate(["G1", "G2", "G3"], rows, datasets)
    assert rep.ok
    assert rep.n == 4
    assert rep.structure == "star"


def test_complete_bipartite_detected(tmp_path):
    # K_{2,2}: parts {row0,row1} -> {row2,row3}, all cross edges, identical across datasets.
    g1 = _ds(tmp_path, "G1", "1,3\n1,4\n2,3\n2,4\n")
    g2 = _ds(tmp_path, "G2", "p,r\np,s\nq,r\nq,s\n")
    g3 = _ds(tmp_path, "G3", f"{B1},{B3}\n{B1},{B4}\n{B2},{B3}\n{B2},{B4}\n")
    datasets = {"G1": g1, "G2": g2, "G3": g3}
    rows = [["1", "p", B1], ["2", "q", B2], ["3", "r", B3], ["4", "s", B4]]
    rep = verify_candidate(["G1", "G2", "G3"], rows, datasets)
    assert rep.ok
    assert rep.structure == "complete_bipartite"


# ---------------------------------------------------------------------------
# File / config path (verify_file) and the no-graph-library hard rule (CLI)
# ---------------------------------------------------------------------------

def _toy_config(tmp_path, datasets_map):
    """Write toy dataset CSVs + a tmp config.yaml (absolute data.dir). Returns config path."""
    for name, rows in datasets_map.items():
        _write(tmp_path, rows, f"{name.lower()}.csv")
    lines = [
        "seed: 1",
        "data:",
        f"  dir: {tmp_path}",
        "  datasets:",
    ]
    for name in datasets_map:
        lines.append(f"    {name}: {name.lower()}.csv")
    lines += ["  drop_self_loops: true", "  collapse_parallel_edges: true"]
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("\n".join(lines) + "\n")
    return cfg_path


_TRIANGLE_MAP = {
    "G1": "1,2\n2,1\n2,3\n3,2\n1,3\n3,1\n",
    "G2": "a,b\nb,a\nb,c\nc,b\na,c\nc,a\n",
    "G3": f"{B1},{B2}\n{B2},{B1}\n{B2},{B3}\n{B3},{B2}\n{B1},{B3}\n{B3},{B1}\n",
}


def test_unknown_dataset_header_fails_check1(tmp_path):
    import src.config as config

    cfg = config.load(_toy_config(tmp_path, _TRIANGLE_MAP))
    cand = tmp_path / "cand.csv"
    cand.write_text(f"G1,G2,NOPE\n1,a,{B1}\n2,b,{B2}\n3,c,{B3}\n")
    rep = verify_file(cand, cfg=cfg)
    assert rep.failed_check == 1
    assert "NOPE" in rep.reason


def test_verify_file_positive(tmp_path):
    import src.config as config

    cfg = config.load(_toy_config(tmp_path, _TRIANGLE_MAP))
    cand = tmp_path / "cand.csv"
    cand.write_text(f"G1,G2,G3\n1,a,{B1}\n2,b,{B2}\n3,c,{B3}\n")
    rep = verify_file(cand, cfg=cfg)
    assert rep.ok and rep.n == 3 and rep.structure == "clique"


def _run_cli(repo_root, *args):
    return subprocess.run(
        [sys.executable, "-m", "src.verify.check", *args],
        cwd=repo_root, capture_output=True, text=True,
    )


def test_cli_pass_exit_zero(tmp_path):
    repo_root = Path(__file__).resolve().parent.parent
    cfg_path = _toy_config(tmp_path, _TRIANGLE_MAP)
    cand = tmp_path / "cand.csv"
    cand.write_text(f"G1,G2,G3\n1,a,{B1}\n2,b,{B2}\n3,c,{B3}\n")
    res = _run_cli(repo_root, "--candidate", str(cand), "--config", str(cfg_path))
    assert res.returncode == 0, res.stderr + res.stdout
    assert "PASS" in res.stdout


def test_cli_fail_exit_nonzero(tmp_path):
    repo_root = Path(__file__).resolve().parent.parent
    cfg_path = _toy_config(tmp_path, _TRIANGLE_MAP)
    cand = tmp_path / "cand.csv"
    # duplicate id "1" in column G1 -> check 1 failure
    cand.write_text(f"G1,G2,G3\n1,a,{B1}\n1,b,{B2}\n3,c,{B3}\n")
    res = _run_cli(repo_root, "--candidate", str(cand), "--config", str(cfg_path))
    assert res.returncode == 1, res.stderr + res.stdout
    assert "FAIL" in res.stdout


def test_cli_json_output(tmp_path):
    import json

    repo_root = Path(__file__).resolve().parent.parent
    cfg_path = _toy_config(tmp_path, _TRIANGLE_MAP)
    cand = tmp_path / "cand.csv"
    cand.write_text(f"G1,G2,G3\n1,a,{B1}\n2,b,{B2}\n3,c,{B3}\n")
    res = _run_cli(repo_root, "--candidate", str(cand), "--config", str(cfg_path), "--json")
    assert res.returncode == 0, res.stderr + res.stdout
    payload = json.loads(res.stdout)
    assert payload["ok"] is True
    assert payload["n"] == 3
    assert payload["structure"] == "clique"
    assert payload["datasets"] == ["G1", "G2", "G3"]
    assert [c["index"] for c in payload["checks"]] == [1, 2, 3, 4]


def test_verifier_imports_no_graph_library():
    code = (
        "import sys; import src.verify.check; "
        "assert 'igraph' not in sys.modules, 'verifier must not import igraph'; "
        "assert 'networkx' not in sys.modules, 'verifier must not import networkx'; "
        "print('OK')"
    )
    repo_root = Path(__file__).resolve().parent.parent
    res = subprocess.run(
        [sys.executable, "-c", code], cwd=repo_root, capture_output=True, text=True
    )
    assert res.returncode == 0, res.stderr
    assert "OK" in res.stdout
