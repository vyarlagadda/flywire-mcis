"""Tests for Engine C — connectivity-constrained greedy seed-and-extend.

Toy in-memory Datasets (no file IO), mirroring tests/test_engine_a.py. The growth invariant
(a row only creates new ordered pairs against prior rows, so per-step all-or-none agreement is
necessary AND sufficient) is the load-bearing claim; ``test_incremental_equals_full`` guards the
incremental signature implementation against a brute-force reference, and every growth test ends in
the independent verifier (src.verify).
"""
from __future__ import annotations

import random
import time

from src.io.loader import Dataset
from src.verify.check import verify_candidate


# ---------------------------------------------------------------------------
# Helpers (mirror tests/test_engine_a.py)
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


def relabel(edges: list[tuple[str, str]], prefix: str) -> list[tuple[str, str]]:
    """Re-prefix node ids so three datasets share structure but not ids (structural matching)."""
    return [(prefix + u, prefix + v) for u, v in edges]


# ---------------------------------------------------------------------------
# signature.py — the incremental connection-signature data structure
# ---------------------------------------------------------------------------

def _full_signature(ds: Dataset, mapped: list[int], x: int) -> int:
    """Brute-force reference: 2K-bit signature of x against the mapping, read straight from edges."""
    sig = 0
    for m, w in enumerate(mapped):
        if (x, w) in ds.edges:          # x -> member_m  => out-bit
            sig |= 1 << (2 * m)
        if (w, x) in ds.edges:          # member_m -> x  => in-bit
            sig |= 1 << (2 * m + 1)
    return sig


def test_add_member_sets_expected_bits():
    from src.engine_c.signature import new_graph_state, add_member

    # a -> b, b -> a (reciprocal), a -> c (one-way out of a)
    ds = make_ds("T", [("a", "b"), ("b", "a"), ("a", "c")])
    gs = new_graph_state(ds)
    a = ds.id_to_int["a"]
    b = ds.id_to_int["b"]
    c = ds.id_to_int["c"]

    add_member(gs, a)  # member index 0 == a
    # b is reciprocal with a: b->a (out-bit 0) and a->b (in-bit 1) => bits 0 and 1 set => 0b11
    assert gs.sig[b] == 0b11
    # c only has a->c: member0 -> c => in-bit (bit 1) only => 0b10
    assert gs.sig[c] == 0b10
    assert b in gs.boundary and c in gs.boundary
    assert a not in gs.boundary


def test_boundary_excludes_mapped():
    from src.engine_c.signature import new_graph_state, add_member

    ds = make_ds("T", recip(["a", "b", "c"]))
    gs = new_graph_state(ds)
    a, b = ds.id_to_int["a"], ds.id_to_int["b"]
    add_member(gs, a)
    add_member(gs, b)
    assert a not in gs.boundary and b not in gs.boundary
    assert a not in gs.sig and b not in gs.sig  # popped when promoted to mapped


def test_incremental_equals_full():
    """The O(boundary) incremental add_member must equal the brute-force 2K-bit recompute."""
    from src.engine_c.signature import new_graph_state, add_member

    rng = random.Random(123)
    nodes = [f"n{i}" for i in range(12)]
    edges = []
    for u in nodes:
        for v in nodes:
            if u != v and rng.random() < 0.35:
                edges.append((u, v))
    ds = make_ds("T", edges)
    gs = new_graph_state(ds)

    mapped: list[int] = []
    order = list(range(ds.num_nodes))
    rng.shuffle(order)
    for w in order[:6]:
        add_member(gs, w)
        mapped.append(w)
        # every boundary node's incremental signature must match the brute-force reference
        for x in gs.boundary:
            assert gs.sig[x] == _full_signature(ds, mapped, x), f"mismatch at node {x}, K={len(mapped)}"


# ---------------------------------------------------------------------------
# seeds.py — WL color-class seeds + clique warm-start
# ---------------------------------------------------------------------------

def _cfg_c(**ov) -> dict:
    c = {
        "seed": 7,
        "invariants": {"gdv_enabled": False, "min_datasets_per_color_class": 3},
        "engine_c": {"seed_source": "gdv", "num_seeds": 50},
    }
    c["engine_c"].update(ov)
    return c


def test_resolve_seed_source_gdv_falls_back_to_wl(recwarn):
    from src.engine_c.seeds import resolve_seed_source

    # seed_source=gdv but no orca binary installed => must fall back to wl (never crash)
    assert resolve_seed_source(_cfg_c(seed_source="gdv")) == "wl"
    assert resolve_seed_source(_cfg_c(seed_source="wl")) == "wl"


def test_generate_seeds_share_color_and_deterministic():
    from src.engine_c.seeds import compute_wl_colors, generate_seeds

    triple = ["BANC", "FAFB", "MCNS"]
    datasets = {
        "BANC": make_ds("BANC", relabel(recip(["1", "2", "3", "4"]), "a")),
        "FAFB": make_ds("FAFB", relabel(recip(["1", "2", "3", "4"]), "b")),
        "MCNS": make_ds("MCNS", relabel(recip(["1", "2", "3", "4"]), "c")),
    }
    shallow, _deep = compute_wl_colors(datasets, seed_depth=1, filter_depth=2)

    s1 = generate_seeds(shallow, datasets, triple, num_seeds=10, rng=random.Random(7))
    s2 = generate_seeds(shallow, datasets, triple, num_seeds=10, rng=random.Random(7))
    assert s1 == s2 and len(s1) > 0                      # deterministic, non-empty
    for a, b, c in s1:                                   # each seed triple shares one shallow color
        ca = int(shallow["BANC"].colors[a])
        cb = int(shallow["FAFB"].colors[b])
        cc = int(shallow["MCNS"].colors[c])
        assert ca == cb == cc


def test_clique_seed_loads_full_mapping(tmp_path):
    from src.engine_c.seeds import clique_seed

    triple = ["BANC", "FAFB", "MCNS"]
    datasets = {
        "BANC": make_ds("BANC", relabel(recip(["1", "2", "3"]), "a")),
        "FAFB": make_ds("FAFB", relabel(recip(["1", "2", "3"]), "b")),
        "MCNS": make_ds("MCNS", relabel(recip(["1", "2", "3"]), "c")),
    }
    # certificate header in a PERMUTED order vs the triple; clique_seed must reorder to triple order
    cert = tmp_path / "clique.csv"
    cert.write_text("FAFB,MCNS,BANC\nb1,c1,a1\nb2,c2,a2\nb3,c3,a3\n")
    mapping = clique_seed(cert, datasets, triple)
    assert mapping is not None and len(mapping) == 3
    # first row should map to (BANC a1, FAFB b1, MCNS c1) in triple order, as compact ints
    a1, b1, c1 = datasets["BANC"].id_to_int["a1"], datasets["FAFB"].id_to_int["b1"], datasets["MCNS"].id_to_int["c1"]
    assert mapping[0] == (a1, b1, c1)
    assert clique_seed(tmp_path / "missing.csv", datasets, triple) is None


# ---------------------------------------------------------------------------
# grow.py — the greedy seed-and-extend loop (every test ends in the verifier)
# ---------------------------------------------------------------------------

def _grow(datasets, triple, init_mapping, enforce_conn, jump_pool=None, deadline_offset=30.0):
    from src.engine_c.grow import grow_from_seed
    from src.engine_c.seeds import compute_wl_colors
    from src.engine_c.signature import new_graph_state

    shallow, deep = compute_wl_colors(datasets, seed_depth=1, filter_depth=3)
    states = tuple(new_graph_state(datasets[c]) for c in triple)
    shallow_cols = [shallow[c].colors for c in triple]
    deep_cols = [deep[c].colors for c in triple]
    return grow_from_seed(
        init_mapping, states, shallow_cols, deep_cols,
        enforce_conn=enforce_conn, candidate_cap=100000, boundary_cap=100000,
        jump_pool=jump_pool, deadline=time.monotonic() + deadline_offset,
    )


def _rows_str(datasets, triple, rows_int):
    return [[datasets[c].int_to_id[node] for c, node in zip(triple, row)] for row in rows_int]


def _seed(datasets, triple, suffix):
    """Compact-int triple for the structurally-corresponding nodes a<suffix>/b<suffix>/c<suffix>."""
    prefixes = {"BANC": "a", "FAFB": "b", "MCNS": "c"}
    return tuple(datasets[c].id_to_int[prefixes[c] + suffix] for c in triple)


def test_grow_recovers_reciprocal_k4():
    triple = ["BANC", "FAFB", "MCNS"]
    datasets = {
        "BANC": make_ds("BANC", relabel(recip(["1", "2", "3", "4"]), "a")),
        "FAFB": make_ds("FAFB", relabel(recip(["1", "2", "3", "4"]), "b")),
        "MCNS": make_ds("MCNS", relabel(recip(["1", "2", "3", "4"]), "c")),
    }
    res = _grow(datasets, triple, [_seed(datasets, triple, "1")], enforce_conn=True)
    assert res["n"] == 4
    rep = verify_candidate(triple, _rows_str(datasets, triple, res["rows_int"]), datasets)
    assert rep.ok and rep.structure == "clique"


def test_grow_directed_path():
    triple = ["BANC", "FAFB", "MCNS"]
    path = [("1", "2"), ("2", "3"), ("3", "4")]
    datasets = {
        "BANC": make_ds("BANC", relabel(path, "a")),
        "FAFB": make_ds("FAFB", relabel(path, "b")),
        "MCNS": make_ds("MCNS", relabel(path, "c")),
    }
    res = _grow(datasets, triple, [_seed(datasets, triple, "1")], enforce_conn=True)
    assert res["n"] == 4
    rep = verify_candidate(triple, _rows_str(datasets, triple, res["rows_int"]), datasets)
    assert rep.ok and rep.structure == "general"


def test_grow_recovers_core_ignores_divergent_gadget():
    """Growth recovers the shared connected core and the verifier confirms it; incompatible
    extra material (here a disconnected gadget that differs across the three graphs) is never
    admitted under weak connectivity, so the result stays exactly the verified core."""
    triple = ["BANC", "FAFB", "MCNS"]
    core = recip(["1", "2", "3"])  # identical, untouched reciprocal triangle in all three
    datasets = {
        # divergent, DISCONNECTED gadget on {7,8,9}: reciprocal edge vs reciprocal edge vs 3-cycle
        "BANC": make_ds("BANC", relabel(core + recip(["7", "8"]), "a")),
        "FAFB": make_ds("FAFB", relabel(core + recip(["7", "8"]), "b")),
        "MCNS": make_ds("MCNS", relabel(core + [("7", "8"), ("8", "9"), ("9", "7")], "c")),
    }
    res = _grow(datasets, triple, [_seed(datasets, triple, "1")], enforce_conn=True)
    assert res["n"] == 3  # exactly the shared triangle; the divergent gadget is not pulled in
    rep = verify_candidate(triple, _rows_str(datasets, triple, res["rows_int"]), datasets)
    assert rep.ok and rep.structure == "clique"


def test_grow_connectivity_off_extends_further():
    """Two disjoint isomorphic triangles: ON yields one (connected, verifies); OFF yields both
    (disconnected -> verifier fails ONLY check 4, checks 1-3 pass)."""
    triple = ["BANC", "FAFB", "MCNS"]
    two = recip(["1", "2", "3"]) + recip(["4", "5", "6"])  # no edges between the components
    datasets = {
        "BANC": make_ds("BANC", relabel(two, "a")),
        "FAFB": make_ds("FAFB", relabel(two, "b")),
        "MCNS": make_ds("MCNS", relabel(two, "c")),
    }
    seed = _seed(datasets, triple, "1")
    on = _grow(datasets, triple, [seed], enforce_conn=True)
    assert on["n"] == 3
    rep_on = verify_candidate(triple, _rows_str(datasets, triple, on["rows_int"]), datasets)
    assert rep_on.ok

    jump_pool = [_seed(datasets, triple, str(k)) for k in range(1, 7)]
    off = _grow(datasets, triple, [seed], enforce_conn=False, jump_pool=jump_pool)
    assert off["n"] == 6
    rep_off = verify_candidate(triple, _rows_str(datasets, triple, off["rows_int"]), datasets)
    assert not rep_off.ok and rep_off.failed_check == 4
    assert all(c.passed for c in rep_off.checks if c.index in (1, 2, 3))


def test_grow_deterministic():
    triple = ["BANC", "FAFB", "MCNS"]
    datasets = {
        "BANC": make_ds("BANC", relabel(recip(["1", "2", "3", "4", "5"]), "a")),
        "FAFB": make_ds("FAFB", relabel(recip(["1", "2", "3", "4", "5"]), "b")),
        "MCNS": make_ds("MCNS", relabel(recip(["1", "2", "3", "4", "5"]), "c")),
    }
    r1 = _grow(datasets, triple, [_seed(datasets, triple, "1")], enforce_conn=True)
    r2 = _grow(datasets, triple, [_seed(datasets, triple, "1")], enforce_conn=True)
    assert r1["rows_int"] == r2["rows_int"]


def test_grow_deadline_returns_verifying_prefix():
    triple = ["BANC", "FAFB", "MCNS"]
    datasets = {
        "BANC": make_ds("BANC", relabel(recip(["1", "2", "3"]), "a")),
        "FAFB": make_ds("FAFB", relabel(recip(["1", "2", "3"]), "b")),
        "MCNS": make_ds("MCNS", relabel(recip(["1", "2", "3"]), "c")),
    }
    init = [_seed(datasets, triple, "1"), _seed(datasets, triple, "2")]  # valid reciprocal edge
    res = _grow(datasets, triple, init, enforce_conn=True, deadline_offset=-1.0)  # already expired
    assert res["stopped_reason"] == "deadline" and res["n"] == 2
    rep = verify_candidate(triple, _rows_str(datasets, triple, res["rows_int"]), datasets)
    assert rep.ok


# ---------------------------------------------------------------------------
# run.py — orchestrator smoke test (writes only to pytest tmp_path)
# ---------------------------------------------------------------------------

def test_run_engine_c_smoke(tmp_path):
    import json

    from src import config
    from src.engine_c.run import run_engine_c

    triple = ["BANC", "FAFB", "MCNS"]
    datasets = {
        "BANC": make_ds("BANC", relabel(recip(["1", "2", "3", "4", "5"]), "a")),
        "FAFB": make_ds("FAFB", relabel(recip(["1", "2", "3", "4", "5"]), "b")),
        "MCNS": make_ds("MCNS", relabel(recip(["1", "2", "3", "4", "5"]), "c")),
    }
    cfg = config.get()  # real config provides invariants depths + engine_c.seed_source
    summary = run_engine_c(
        datasets, cfg, tmp_path,
        triple=triple, num_seeds=10, time_budget_s=10.0,
        enforce_conn=True, caps={"candidate_cap": 10000, "boundary_cap": 10000, "off_pool_cap": 100},
        rng_seed=7, clique_cert_path=None, run_off_ablation=True, snapshot=False, verbose=False,
    )
    assert summary["best_connected_n"] == 5  # recovers the full reciprocal K5

    for fname in ("best.json", "frontier.csv", "summary.md", "seeds.json"):
        assert (tmp_path / fname).exists()
    cert = tmp_path / "certificates" / "engine_c__BANC-FAFB-MCNS.csv"
    assert cert.exists()

    best = json.loads((tmp_path / "best.json").read_text())
    assert best["ok"] and best["verify"]["ok"]  # the written best is verifier-confirmed
    # the certificate independently re-verifies through the oracle
    from src.verify.check import read_candidate
    header, rows = read_candidate(cert)
    rep = verify_candidate(header, rows, datasets)
    assert rep.ok and rep.n == 5
