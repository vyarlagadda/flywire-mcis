"""Tests for Phase P7 — Bounds & Reproducibility."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Task 1: src/config.py — FLYWIRE_CONFIG env var + active path snapshot
# ---------------------------------------------------------------------------

def test_load_uses_flywire_config_env_var(tmp_path, monkeypatch):
    """FLYWIRE_CONFIG env var must take precedence over the default config path."""
    import src.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "_cfg", None)
    monkeypatch.setattr(cfg_mod, "_active_config_path", None)

    alt_config = tmp_path / "alt_config.yaml"
    alt_config.write_text("seed: 9999\ndata:\n  dir: data/raw\n  datasets: {}\n")

    monkeypatch.setenv("FLYWIRE_CONFIG", str(alt_config))
    result = cfg_mod.load()
    assert result["seed"] == 9999


def test_load_default_when_no_env_var(tmp_path, monkeypatch):
    """Without FLYWIRE_CONFIG, load() must use the repo-root config.yaml."""
    import src.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "_cfg", None)
    monkeypatch.setattr(cfg_mod, "_active_config_path", None)
    monkeypatch.delenv("FLYWIRE_CONFIG", raising=False)

    result = cfg_mod.load()
    assert result["seed"] == 20260610


def test_snapshot_copies_active_config_path(tmp_path, monkeypatch):
    """snapshot() must copy whichever config was last loaded, not always _DEFAULT_CONFIG."""
    import src.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "_cfg", None)
    monkeypatch.setattr(cfg_mod, "_active_config_path", None)

    alt_config = tmp_path / "special_config.yaml"
    alt_config.write_text("seed: 7777\ndata:\n  dir: data/raw\n  datasets: {}\n")

    monkeypatch.setenv("FLYWIRE_CONFIG", str(alt_config))
    cfg_mod.load()

    dest_dir = tmp_path / "result"
    dest_dir.mkdir()
    snap = cfg_mod.snapshot(dest_dir)
    assert snap.exists()
    import yaml
    content = yaml.safe_load(snap.read_text())
    assert content["seed"] == 7777


def test_load_explicit_path_overrides_env_var(tmp_path, monkeypatch):
    """An explicit path= argument to load() takes highest precedence."""
    import src.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "_cfg", None)
    monkeypatch.setattr(cfg_mod, "_active_config_path", None)

    env_config = tmp_path / "env_config.yaml"
    env_config.write_text("seed: 1111\ndata:\n  dir: data/raw\n  datasets: {}\n")
    explicit_config = tmp_path / "explicit_config.yaml"
    explicit_config.write_text("seed: 2222\ndata:\n  dir: data/raw\n  datasets: {}\n")

    monkeypatch.setenv("FLYWIRE_CONFIG", str(env_config))
    result = cfg_mod.load(path=explicit_config)
    assert result["seed"] == 2222


# ---------------------------------------------------------------------------
# Task 2a: collect_lower_bounds
# ---------------------------------------------------------------------------

def _write_frontier_csv(path: Path, rows: list[list[str]]) -> None:
    import csv
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["family", "triple", "n", "structure", "ok", "reason", "certificate"])
        for row in rows:
            w.writerow(row)


def test_collect_lower_bounds_reads_engine_a_frontier(tmp_path):
    """collect_lower_bounds reads verified rows from engine_a/frontier.csv."""
    from src.bounds.compute import collect_lower_bounds

    ea_dir = tmp_path / "engine_a"
    ea_dir.mkdir(parents=True)
    _write_frontier_csv(
        ea_dir / "frontier.csv",
        [
            ["reciprocal_clique", "BANC|FAFB|MCNS", "38", "clique", "True", "",
             "certificates/reciprocal_clique__BANC-FAFB-MCNS.csv"],
            ["directed_star", "FAFB|MAOL|MCNS", "1877", "star", "True", "",
             "certificates/directed_star__FAFB-MAOL-MCNS.csv"],
            ["reciprocal_clique", "BANC|FAFB|MANC", "0", "", "False", "orientation mismatch", ""],
        ],
    )

    bounds = collect_lower_bounds(tmp_path)
    engine_a_bounds = [b for b in bounds if b["engine"] == "engine_a"]
    assert len(engine_a_bounds) == 2   # only verified rows
    clique_row = next(b for b in engine_a_bounds if b["triple"] == "BANC|FAFB|MCNS")
    assert clique_row["N"] == 38
    assert clique_row["verified"] is True
    assert clique_row["family"] == "reciprocal_clique"
    assert "reciprocal_clique__BANC-FAFB-MCNS.csv" in clique_row["certificate"]


def test_collect_lower_bounds_reads_engine_c_best(tmp_path):
    """collect_lower_bounds reads N and verified from engine_c/best.json."""
    from src.bounds.compute import collect_lower_bounds

    ec_dir = tmp_path / "engine_c"
    ec_dir.mkdir(parents=True)
    cert_dir = ec_dir / "certificates"
    cert_dir.mkdir()
    best = {
        "n": 38, "ok": True, "columns": ["BANC", "FAFB", "MCNS"],
        "verify": {"ok": True},
    }
    (ec_dir / "best.json").write_text(json.dumps(best))
    (cert_dir / "engine_c__BANC-FAFB-MCNS.csv").write_text("BANC,FAFB,MCNS\n")

    bounds = collect_lower_bounds(tmp_path)
    ec_bounds = [b for b in bounds if b["engine"] == "engine_c"]
    assert len(ec_bounds) == 1
    assert ec_bounds[0]["N"] == 38
    assert ec_bounds[0]["verified"] is True
    assert ec_bounds[0]["triple"] == "BANC|FAFB|MCNS"


def test_collect_lower_bounds_reads_engine_b_summary(tmp_path):
    """collect_lower_bounds reads best_N_found and verified from engine_b/summary.json."""
    from src.bounds.compute import collect_lower_bounds

    eb_dir = tmp_path / "engine_b"
    eb_dir.mkdir(parents=True)
    summary = {
        "best_N_found": 38, "verified": True, "beats_clique": False,
        "source_certificate": "results/engine_c_nocolor/certificates/engine_c__BANC-FAFB-MCNS.csv",
        "note": "k-core converges to the 38-clique",
    }
    (eb_dir / "summary.json").write_text(json.dumps(summary))

    bounds = collect_lower_bounds(tmp_path)
    eb_bounds = [b for b in bounds if b["engine"] == "engine_b"]
    assert len(eb_bounds) == 1
    assert eb_bounds[0]["N"] == 38
    assert eb_bounds[0]["verified"] is True


def test_collect_lower_bounds_graceful_missing_files(tmp_path):
    """collect_lower_bounds returns an empty list when result files are absent."""
    from src.bounds.compute import collect_lower_bounds

    bounds = collect_lower_bounds(tmp_path)
    assert isinstance(bounds, list)
    assert len(bounds) == 0


def test_collect_lower_bounds_skips_unverified_engine_c(tmp_path):
    """collect_lower_bounds omits engine_c entry when best.json has ok=False."""
    from src.bounds.compute import collect_lower_bounds

    ec_dir = tmp_path / "engine_c"
    ec_dir.mkdir(parents=True)
    best = {"n": 10, "ok": False, "columns": ["BANC", "FAFB", "MCNS"], "verify": {"ok": False}}
    (ec_dir / "best.json").write_text(json.dumps(best))

    bounds = collect_lower_bounds(tmp_path)
    ec_bounds = [b for b in bounds if b["engine"] == "engine_c"]
    assert len(ec_bounds) == 0


# ---------------------------------------------------------------------------
# Task 2b: collect_upper_bounds
# ---------------------------------------------------------------------------

def _write_clique_json(path: Path, dataset: str, n: int, upper_bound: int) -> None:
    path.write_text(json.dumps({
        "family": "reciprocal_clique",
        "dataset": dataset,
        "n": n,
        "upper_bound": upper_bound,
        "members": [],
        "method": "greedy",
    }))


def test_collect_upper_bounds_degeneracy_from_clique_jsons(tmp_path):
    """collect_upper_bounds reads upper_bound from engine_a/clique/{DATASET}.json."""
    from src.bounds.compute import collect_upper_bounds

    clique_dir = tmp_path / "engine_a" / "clique"
    clique_dir.mkdir(parents=True)
    _write_clique_json(clique_dir / "BANC.json", "BANC", 38, 50)
    _write_clique_json(clique_dir / "FAFB.json", "FAFB", 38, 48)
    _write_clique_json(clique_dir / "MCNS.json", "MCNS", 41, 51)

    cfg = {"data": {"datasets": {"BANC": "x", "FAFB": "y", "MCNS": "z"}}}
    result = collect_upper_bounds(tmp_path, cfg)

    deg = result["degeneracy_clique"]
    assert deg["BANC"] == 50
    assert deg["FAFB"] == 48
    assert deg["MCNS"] == 51


def test_collect_upper_bounds_wl_class_capacity(tmp_path):
    """collect_upper_bounds reads class sizes from invariants/candidate_pool.json."""
    from src.bounds.compute import collect_upper_bounds

    inv_dir = tmp_path / "invariants"
    inv_dir.mkdir(parents=True)
    pool = {
        "num_classes": 2,
        "classes": [
            {"color": "aabbcc", "num_datasets": 3,
             "sizes": {"BANC": 4, "FAFB": 10, "MAOL": 16}},
            {"color": "ddeeff", "num_datasets": 3,
             "sizes": {"BANC": 4, "FAFB": 10, "MAOL": 16}},
        ],
    }
    (inv_dir / "candidate_pool.json").write_text(json.dumps(pool))

    cfg = {"data": {"datasets": {"BANC": "x", "FAFB": "y", "MCNS": "z"}}}
    result = collect_upper_bounds(tmp_path, cfg)

    wl = result["wl_class_capacity"]
    assert "max_class_size_per_dataset" in wl
    assert "note" in wl
    assert wl["max_class_size_per_dataset"]["class_0"]["BANC"] == 4


def test_collect_upper_bounds_graceful_missing_clique_files(tmp_path):
    """collect_upper_bounds returns empty degeneracy_clique when directory is absent."""
    from src.bounds.compute import collect_upper_bounds

    cfg = {"data": {"datasets": {"BANC": "x", "FAFB": "y"}}}
    result = collect_upper_bounds(tmp_path, cfg)
    assert result["degeneracy_clique"] == {}


def test_collect_upper_bounds_graceful_missing_pool(tmp_path):
    """collect_upper_bounds returns empty wl_class_capacity when candidate_pool.json is absent."""
    from src.bounds.compute import collect_upper_bounds

    cfg = {"data": {"datasets": {"BANC": "x"}}}
    result = collect_upper_bounds(tmp_path, cfg)
    assert result["wl_class_capacity"] == {}


# ---------------------------------------------------------------------------
# Task 2c: run_ablation
# ---------------------------------------------------------------------------

def _make_toy_datasets():
    """Minimal three-dataset dict for smoke-testing run_ablation."""
    from src.io.loader import Dataset

    def make_ds(name, edges):
        int_to_id: list[str] = []
        id_to_int: dict[str, int] = {}

        def intern(s):
            if s not in id_to_int:
                id_to_int[s] = len(int_to_id)
                int_to_id.append(s)
            return id_to_int[s]

        eset = {(intern(u), intern(v)) for u, v in edges}
        return Dataset(name=name, int_to_id=int_to_id, id_to_int=id_to_int, edges=eset)

    def recip(nodes, prefix):
        return [(prefix + u, prefix + v) for u in nodes for v in nodes if u != v]

    nodes = ["1", "2", "3"]
    return {
        "BANC": make_ds("BANC", recip(nodes, "a")),
        "FAFB": make_ds("FAFB", recip(nodes, "b")),
        "MCNS": make_ds("MCNS", recip(nodes, "c")),
    }


def test_run_ablation_returns_per_seed_dict(tmp_path):
    """run_ablation returns a dict with one entry per seed."""
    from src.bounds.compute import run_ablation

    cfg = {
        "seed": 42,
        "invariants": {"wl_seed_depth": 1, "wl_filter_depth": 2, "gdv_enabled": False,
                       "min_datasets_per_color_class": 3},
        "engine_c": {
            "seed_source": "wl", "num_seeds": 3,
            "enforce_weak_connectivity": True, "seed_color_key": True,
            "candidate_cap": 1000, "boundary_cap": 1000, "off_pool_cap": 100,
            "time_budget_s": 5.0,
        },
        "paths": {"results_dir": str(tmp_path)},
    }
    datasets = _make_toy_datasets()
    triple = ["BANC", "FAFB", "MCNS"]

    result = run_ablation(cfg, tmp_path, seeds=[1, 2], datasets=datasets, triple=triple)

    assert isinstance(result, dict)
    assert set(result.keys()) == {1, 2}
    for seed_val, rec in result.items():
        assert "N" in rec
        assert "wall_clock_s" in rec
        assert isinstance(rec["N"], int)
        assert rec["N"] >= 0


def test_run_ablation_writes_subdirectories(tmp_path):
    """run_ablation writes {base_out_dir}/ablation/seed_{seed}/ for each seed."""
    from src.bounds.compute import run_ablation

    cfg = {
        "seed": 42,
        "invariants": {"wl_seed_depth": 1, "wl_filter_depth": 2, "gdv_enabled": False,
                       "min_datasets_per_color_class": 3},
        "engine_c": {
            "seed_source": "wl", "num_seeds": 3,
            "enforce_weak_connectivity": True, "seed_color_key": True,
            "candidate_cap": 1000, "boundary_cap": 1000, "off_pool_cap": 100,
            "time_budget_s": 5.0,
        },
        "paths": {"results_dir": str(tmp_path)},
    }
    datasets = _make_toy_datasets()
    triple = ["BANC", "FAFB", "MCNS"]

    run_ablation(cfg, tmp_path, seeds=[3], datasets=datasets, triple=triple)

    assert (tmp_path / "ablation" / "seed_3").exists()


def test_run_ablation_different_seeds_produce_independent_runs(tmp_path):
    """run_ablation with two seeds runs engine_c twice with those exact seeds."""
    from src.bounds.compute import run_ablation

    cfg = {
        "seed": 99,
        "invariants": {"wl_seed_depth": 1, "wl_filter_depth": 2, "gdv_enabled": False,
                       "min_datasets_per_color_class": 3},
        "engine_c": {
            "seed_source": "wl", "num_seeds": 3,
            "enforce_weak_connectivity": True, "seed_color_key": True,
            "candidate_cap": 1000, "boundary_cap": 1000, "off_pool_cap": 100,
            "time_budget_s": 5.0,
        },
        "paths": {"results_dir": str(tmp_path)},
    }
    datasets = _make_toy_datasets()
    triple = ["BANC", "FAFB", "MCNS"]

    result = run_ablation(cfg, tmp_path, seeds=[10, 20], datasets=datasets, triple=triple)

    for s in [10, 20]:
        assert s in result
        assert (tmp_path / "ablation" / f"seed_{s}").exists()


# ---------------------------------------------------------------------------
# Task 2d: build_summary
# ---------------------------------------------------------------------------

def test_build_summary_structure_and_gap(tmp_path):
    """build_summary assembles the canonical summary dict with correct gap."""
    from src.bounds.compute import build_summary

    lower_bounds = [
        {"N": 38, "engine": "engine_a", "family": "reciprocal_clique",
         "triple": "BANC|FAFB|MCNS", "verified": True,
         "certificate": "results/engine_a/certificates/reciprocal_clique__BANC-FAFB-MCNS.csv"},
        {"N": 38, "engine": "engine_c", "family": None,
         "triple": "BANC|FAFB|MCNS", "verified": True,
         "certificate": "results/engine_c/certificates/engine_c__BANC-FAFB-MCNS.csv"},
    ]
    upper_bounds = {
        "degeneracy_clique": {"BANC": 50, "FAFB": 48, "MCNS": 51},
        "wl_class_capacity": {},
    }
    ablation = {
        1: {"N": 38, "wall_clock_s": 20.0},
        2: {"N": 38, "wall_clock_s": 21.0},
    }

    summary = build_summary(lower_bounds, upper_bounds, ablation, cfg_seed=20260610)

    assert summary["best_lower_bound"] == 38
    assert summary["tightest_upper_bound"] == 48   # min(50, 48, 51)
    assert summary["gap"] == 10                     # 48 - 38
    assert summary["config_seed"] == 20260610
    assert "lower_bounds" in summary
    assert "upper_bounds" in summary
    assert "ablation" in summary
    assert "note" in summary
    assert "OGP" in summary["note"] or "NP-hard" in summary["note"]


def test_build_summary_ablation_statistics(tmp_path):
    """build_summary populates ablation.min_N, max_N, mean_wall_clock_s."""
    from src.bounds.compute import build_summary

    ablation = {
        1: {"N": 36, "wall_clock_s": 20.0},
        2: {"N": 38, "wall_clock_s": 22.0},
        3: {"N": 37, "wall_clock_s": 24.0},
    }
    summary = build_summary([], {"degeneracy_clique": {}, "wl_class_capacity": {}},
                            ablation, cfg_seed=7)

    abl = summary["ablation"]
    assert abl["min_N"] == 36
    assert abl["max_N"] == 38
    assert abs(abl["mean_wall_clock_s"] - 22.0) < 0.01
    assert set(abl["seeds_tested"]) == {1, 2, 3}


def test_build_summary_no_lower_bounds_gives_zero(tmp_path):
    """build_summary returns best_lower_bound=0 when lower_bounds is empty."""
    from src.bounds.compute import build_summary

    summary = build_summary([], {"degeneracy_clique": {}, "wl_class_capacity": {}},
                            {}, cfg_seed=0)
    assert summary["best_lower_bound"] == 0


def test_build_summary_no_upper_bounds_gives_none(tmp_path):
    """build_summary returns tightest_upper_bound=None when degeneracy_clique is empty."""
    from src.bounds.compute import build_summary

    lower_bounds = [{"N": 38, "engine": "engine_a", "family": "reciprocal_clique",
                     "triple": "BANC|FAFB|MCNS", "verified": True, "certificate": None}]
    summary = build_summary(lower_bounds, {"degeneracy_clique": {}, "wl_class_capacity": {}},
                            {}, cfg_seed=0)
    assert summary["tightest_upper_bound"] is None
    assert summary["gap"] is None


def test_build_summary_includes_generated_at_timestamp(tmp_path):
    """build_summary includes a generated_at ISO timestamp."""
    from src.bounds.compute import build_summary
    from datetime import datetime

    summary = build_summary([], {"degeneracy_clique": {}, "wl_class_capacity": {}},
                            {}, cfg_seed=0)
    assert "generated_at" in summary
    datetime.fromisoformat(summary["generated_at"])


# ---------------------------------------------------------------------------
# Task 3: src/bounds/run.py — CLI smoke tests
# ---------------------------------------------------------------------------

def test_bounds_run_writes_summary_json(tmp_path, monkeypatch):
    """The bounds CLI writes summary.json when given pre-populated result dirs."""
    import src.config as cfg_mod
    from src.bounds import run as bounds_run_mod

    monkeypatch.setattr(cfg_mod, "_cfg", None)
    monkeypatch.setattr(cfg_mod, "_active_config_path", None)
    monkeypatch.delenv("FLYWIRE_CONFIG", raising=False)

    # Build a minimal fake results tree
    ea_dir = tmp_path / "engine_a"
    clique_dir = ea_dir / "clique"
    clique_dir.mkdir(parents=True)
    _write_frontier_csv(
        ea_dir / "frontier.csv",
        [["reciprocal_clique", "BANC|FAFB|MCNS", "38", "clique", "True", "",
          "certificates/reciprocal_clique__BANC-FAFB-MCNS.csv"]],
    )
    _write_clique_json(clique_dir / "BANC.json", "BANC", 38, 50)
    _write_clique_json(clique_dir / "FAFB.json", "FAFB", 38, 48)
    _write_clique_json(clique_dir / "MCNS.json", "MCNS", 41, 51)

    bounds_run_mod.main(
        argv=["--out", str(tmp_path / "bounds"), "--skip-ablation",
              "--results-dir", str(tmp_path)],
    )

    out_dir = tmp_path / "bounds"
    assert (out_dir / "summary.json").exists()
    summary = json.loads((out_dir / "summary.json").read_text())
    assert summary["best_lower_bound"] == 38
    assert summary["tightest_upper_bound"] == 48
    assert summary["gap"] == 10


def test_bounds_run_writes_config_snapshot(tmp_path, monkeypatch):
    """The bounds CLI writes config.snapshot.yaml alongside summary.json."""
    import src.config as cfg_mod
    from src.bounds import run as bounds_run_mod

    monkeypatch.setattr(cfg_mod, "_cfg", None)
    monkeypatch.setattr(cfg_mod, "_active_config_path", None)
    monkeypatch.delenv("FLYWIRE_CONFIG", raising=False)

    ea_dir = tmp_path / "engine_a"
    ea_dir.mkdir(parents=True)
    _write_frontier_csv(ea_dir / "frontier.csv", [])

    bounds_run_mod.main(
        argv=["--out", str(tmp_path / "bounds"), "--skip-ablation",
              "--results-dir", str(tmp_path)],
    )

    assert (tmp_path / "bounds" / "config.snapshot.yaml").exists()


# ---------------------------------------------------------------------------
# Task 4: scripts/run_all — pipeline orchestrator
# ---------------------------------------------------------------------------

_RUN_ALL = Path("/Users/vikasyarlagadda/Projects/flywire-mcis/scripts/run_all")
_CONFIG = Path("/Users/vikasyarlagadda/Projects/flywire-mcis/config.yaml")
_CWD = "/Users/vikasyarlagadda/Projects/flywire-mcis"


def test_run_all_exists():
    """scripts/run_all must exist."""
    assert _RUN_ALL.exists(), "scripts/run_all not found"


def test_run_all_help_exits_cleanly():
    """scripts/run_all --help must print usage and exit 0."""
    import subprocess
    result = subprocess.run(
        ["python", str(_RUN_ALL), "--help"],
        capture_output=True, text=True, cwd=_CWD,
    )
    assert result.returncode == 0
    assert "usage" in result.stdout.lower() or "usage" in result.stderr.lower()


def test_run_all_skip_all_exits_zero():
    """Skipping all steps must not crash and must exit 0."""
    import subprocess

    all_steps = (
        "characterize,invariants,engine_a,engine_c,engine_c_nocolor,"
        "engine_b_step1,engine_b_step2,engine_b_step3,verify,bounds"
    )
    result = subprocess.run(
        ["python", str(_RUN_ALL), "--config", str(_CONFIG), "--skip", all_steps],
        capture_output=True, text=True, cwd=_CWD,
    )
    assert result.returncode == 0


def test_run_all_unknown_skip_step_still_exits_zero():
    """An unknown --skip step name is ignored; script exits 0 when all known steps are skipped."""
    import subprocess

    all_plus_unknown = (
        "characterize,invariants,engine_a,engine_c,engine_c_nocolor,"
        "engine_b_step1,engine_b_step2,engine_b_step3,verify,bounds,nonexistent_step"
    )
    result = subprocess.run(
        ["python", str(_RUN_ALL), "--config", str(_CONFIG), "--skip", all_plus_unknown],
        capture_output=True, text=True, cwd=_CWD,
    )
    assert result.returncode == 0
