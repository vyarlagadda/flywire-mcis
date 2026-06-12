"""Bounds analysis — collect lower/upper bounds and run ablation for Phase P7."""
from __future__ import annotations

import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def collect_lower_bounds(results_dir: Path) -> list[dict[str, Any]]:
    """Compile verified lower bounds from all three engines.

    Reads:
      - ``{results_dir}/engine_a/frontier.csv`` — verified rows only
      - ``{results_dir}/engine_c/best.json``    — if ok=True
      - ``{results_dir}/engine_b/summary.json`` — if verified=True

    Returns a list of dicts with keys:
      N (int), engine (str), family (str|None), triple (str), verified (bool), certificate (str|None)

    Gracefully skips any missing file.
    """
    bounds: list[dict[str, Any]] = []

    # --- Engine A: frontier.csv ---
    frontier_path = results_dir / "engine_a" / "frontier.csv"
    if frontier_path.exists():
        with frontier_path.open(newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                if row.get("ok", "").strip().lower() != "true":
                    continue
                try:
                    n = int(row.get("n", "0").strip())
                except ValueError:
                    continue
                cert = row.get("certificate", "").strip()
                bounds.append({
                    "N": n,
                    "engine": "engine_a",
                    "family": row.get("family", "").strip() or None,
                    "triple": row.get("triple", "").strip(),
                    "verified": True,
                    "certificate": str(results_dir / "engine_a" / cert) if cert else None,
                })

    # --- Engine C: best.json ---
    best_c_path = results_dir / "engine_c" / "best.json"
    if best_c_path.exists():
        best = json.loads(best_c_path.read_text())
        if best.get("ok") is True:
            cols = best.get("columns", [])
            triple = "|".join(cols)
            triple_dash = "-".join(cols)
            cert_rel = f"certificates/engine_c__{triple_dash}.csv"
            cert_full = results_dir / "engine_c" / cert_rel
            bounds.append({
                "N": int(best["n"]),
                "engine": "engine_c",
                "family": None,
                "triple": triple,
                "verified": True,
                "certificate": str(cert_full) if cert_full.exists() else None,
            })

    # --- Engine B: summary.json ---
    summary_b_path = results_dir / "engine_b" / "summary.json"
    if summary_b_path.exists():
        summary = json.loads(summary_b_path.read_text())
        if summary.get("verified") is True:
            bounds.append({
                "N": int(summary["best_N_found"]),
                "engine": "engine_b",
                "family": None,
                "triple": "BANC|FAFB|MCNS",
                "verified": True,
                "certificate": None,
            })

    return bounds


def collect_upper_bounds(
    results_dir: Path,
    cfg: dict[str, Any],
    triple: list[str] | None = None,
) -> dict[str, Any]:
    """Compile upper bounds from degeneracy analysis and WL color classes.

    Reads:
      - ``{results_dir}/engine_a/clique/{DATASET}.json`` for ``upper_bound`` per dataset
      - ``{results_dir}/invariants/candidate_pool.json`` for cross-dataset WL class capacity

    If *triple* is given, degeneracy bounds are restricted to those datasets only.
    This avoids mixing upper bounds across incompatible families/triples.

    Returns::

        {
          "degeneracy_clique": {"BANC": 50, "FAFB": 48, ...},
          "wl_class_capacity": {"max_class_size_per_dataset": {...}, "note": "..."},
        }

    Gracefully returns empty sub-dicts for any missing files.
    """
    degeneracy: dict[str, int] = {}
    clique_dir = results_dir / "engine_a" / "clique"
    dataset_names = triple if triple is not None else list(cfg.get("data", {}).get("datasets", {}))
    if clique_dir.exists():
        for dataset_name in dataset_names:
            p = clique_dir / f"{dataset_name}.json"
            if p.exists():
                data = json.loads(p.read_text())
                ub = data.get("upper_bound")
                if ub is not None:
                    degeneracy[dataset_name] = int(ub)

    wl_capacity: dict[str, Any] = {}
    pool_path = results_dir / "invariants" / "candidate_pool.json"
    if pool_path.exists():
        pool = json.loads(pool_path.read_text())
        classes_info: dict[str, Any] = {}
        for i, cls in enumerate(pool.get("classes", [])):
            classes_info[f"class_{i}"] = cls.get("sizes", {})
        wl_capacity = {
            "max_class_size_per_dataset": classes_info,
            "note": (
                "WL color classes are necessary-not-sufficient; "
                "a shared color is a candidate correspondence only. "
                "The candidate_pool.json classes span MAOL-based triples "
                "and do not constrain the BANC+FAFB+MCNS triple directly."
            ),
        }

    return {
        "degeneracy_clique": degeneracy,
        "wl_class_capacity": wl_capacity,
    }


def run_ablation(
    cfg: dict[str, Any],
    base_out_dir: Path,
    seeds: list[int],
    datasets: dict[str, Any],
    triple: list[str],
    clique_cert_path: Path | None = None,
) -> dict[int, dict[str, Any]]:
    """Run Engine C once per seed, writing to ``{base_out_dir}/ablation/seed_{seed}/``.

    For each seed:
      - Calls ``run_engine_c(...)`` with ``rng_seed=seed`` and ``snapshot=False``
      - Passes *clique_cert_path* as the warm-start (matches the normal engine_c invocation)
      - Reads N from the ``best_connected_n`` key of the returned summary dict
      - Resets ``config._seed_override`` to its prior value after each run

    Engine B is deterministic and not included in the ablation.

    Returns ``{seed: {"N": int, "wall_clock_s": float}, ...}``.
    """
    from src import config
    from src.engine_c.run import _DEFAULT_CAPS, run_engine_c

    ec = cfg.get("engine_c", {})
    caps = {k: int(ec.get(k, _DEFAULT_CAPS[k])) for k in _DEFAULT_CAPS}

    results: dict[int, dict[str, Any]] = {}
    original_override = config._seed_override
    for seed_val in seeds:
        config.set_seed(seed_val)
        seed_out = base_out_dir / "ablation" / f"seed_{seed_val}"
        seed_out.mkdir(parents=True, exist_ok=True)
        try:
            summary = run_engine_c(
                datasets, cfg, seed_out,
                triple=triple,
                num_seeds=int(ec.get("num_seeds", 100)),
                time_budget_s=float(ec.get("time_budget_s", 60.0)),
                enforce_conn=bool(ec.get("enforce_weak_connectivity", True)),
                caps=caps,
                rng_seed=seed_val,
                use_color_key=bool(ec.get("seed_color_key", True)),
                clique_cert_path=clique_cert_path,
                run_off_ablation=False,
                snapshot=False,
                verbose=False,
            )
            n = summary.get("best_connected_n", 0)
            wall = summary.get("wall_clock_s", 0.0)
            # Fallback: read best.json if summary key is absent
            if not n:
                best_path = seed_out / "best.json"
                if best_path.exists():
                    best = json.loads(best_path.read_text())
                    n = best.get("n", 0) if best.get("ok") else 0
            results[seed_val] = {"N": int(n), "wall_clock_s": float(wall)}
        finally:
            config._seed_override = original_override

    return results


def build_summary(
    lower_bounds: list[dict[str, Any]],
    upper_bounds: dict[str, Any],
    ablation: dict[int, dict[str, Any]],
    cfg_seed: int,
    primary_triple: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble the final bounds summary with gap analysis and OGP note.

    Parameters
    ----------
    lower_bounds:    output of :func:`collect_lower_bounds`
    upper_bounds:    output of :func:`collect_upper_bounds`
    ablation:        output of :func:`run_ablation` (may be {} when skipped)
    cfg_seed:        global RNG seed from config.yaml (recorded for reproducibility)
    primary_triple:  if given, ``best_lower_bound`` is the max N for bounds on this
                     triple only; the gap is then gap for the submitted solution.

    Returns a JSON-serializable dict ready to write as results/bounds/summary.json.
    """
    if primary_triple:
        triple_str = "|".join(primary_triple)
        primary_lb_list = [b for b in lower_bounds if b["triple"] == triple_str]
    else:
        primary_lb_list = lower_bounds
    best_lb = max((b["N"] for b in primary_lb_list), default=0)

    deg = upper_bounds.get("degeneracy_clique", {})
    tightest_ub: int | None = min(deg.values()) if deg else None
    gap: int | None = (tightest_ub - best_lb) if tightest_ub is not None else None

    abl_ns = [v["N"] for v in ablation.values()]
    abl_times = [v["wall_clock_s"] for v in ablation.values()]
    ablation_block: dict[str, Any] = {
        "seeds_tested": sorted(ablation.keys()),
        "results": {str(k): v for k, v in sorted(ablation.items())},
        "min_N": min(abl_ns) if abl_ns else None,
        "max_N": max(abl_ns) if abl_ns else None,
        "mean_wall_clock_s": (sum(abl_times) / len(abl_times)) if abl_times else None,
    }

    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "config_seed": cfg_seed,
        "lower_bounds": lower_bounds,
        "best_lower_bound": best_lb,
        "upper_bounds": upper_bounds,
        "tightest_upper_bound": tightest_ub,
        "gap": gap,
        "ablation": ablation_block,
        "note": (
            "MCIS is NP-hard; best_lower_bound is a verified certificate, "
            "not a proven global optimum. The computation-to-optimization gap "
            "(OGP) means no greedy algorithm can reliably exceed this N on "
            "this instance family without exponential branching."
        ),
    }
