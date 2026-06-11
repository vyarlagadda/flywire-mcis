"""CLI: Engine C — connectivity-constrained greedy seed-and-extend on the chosen triple.

    python -m src.engine_c.run [--seeds N] [--time-budget S] [--out results/engine_c] [--no-off-ablation]

Loads the three chosen datasets (``engine_c.chosen_triple``), computes shallow/deep directed-WL
colors once, generates seeds (Engine A's verified clique warm-start prepended to shallow-WL
color-class seeds), and greedily grows each seed under a single wall-clock budget. Every kept result
is confirmed by the independent verifier (``src.verify``) before a certificate is written.

Two tracks are recorded:
  - **connected best** (``best.json`` + certificate, the submission candidate) — a verified LOWER
    bound on the largest weakly-connected common induced directed subgraph;
  - **disconnected ceiling** (``best_disconnected.json``) — the connectivity-OFF reference, which by
    design fails only the verifier's weak-connectivity check (checks 1-3 still pass); for the
    frontier discussion, never the submission.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import time
from pathlib import Path
from typing import Any

from src import config
from src.engine_c.grow import grow_from_seed
from src.engine_c.seeds import clique_seed, compute_wl_colors, generate_seeds, resolve_seed_source
from src.engine_c.signature import fresh_state
from src.io.loader import Dataset, build_adjacency, load_dataset
from src.verify.check import verify_candidate

_DEFAULT_CAPS = {"candidate_cap": 50000, "boundary_cap": 200000, "off_pool_cap": 20000}


def _rows_str(datasets: dict[str, Dataset], triple: list[str], rows_int) -> list[list[str]]:
    return [[datasets[c].int_to_id[node] for c, node in zip(triple, row)] for row in rows_int]


def _states(datasets, triple, adj):
    return tuple(fresh_state(datasets[c], adj[c][0], adj[c][1]) for c in triple)


def run_engine_c(
    datasets: dict[str, Dataset],
    cfg: dict[str, Any],
    out_dir: Path,
    *,
    triple: list[str],
    num_seeds: int,
    time_budget_s: float,
    enforce_conn: bool,
    caps: dict[str, int],
    rng_seed: int,
    use_color_key: bool = True,
    clique_cert_path: Path | None = None,
    run_off_ablation: bool = True,
    snapshot: bool = True,
    verbose: bool = True,
) -> dict[str, Any]:
    """Run Engine C end-to-end on already-loaded *datasets* and write all artifacts under *out_dir*.

    Returns a summary dict (also the basis for ``summary.md``). Pure orchestration; the algorithm is
    in ``grow``/``seeds``/``signature`` and the oracle is ``src.verify``.
    """
    t_start = time.perf_counter()
    out_dir.mkdir(parents=True, exist_ok=True)
    if snapshot:
        config.snapshot(out_dir)

    inv = cfg.get("invariants", {})
    seed_depth = int(inv.get("wl_seed_depth", 1))
    filter_depth = int(inv.get("wl_filter_depth", 5))

    def log(msg: str) -> None:
        if verbose:
            print(msg, flush=True)

    # --- WL colors (once) + adjacency (once per dataset, reused across all seeds) ---
    log(f"[engine_c] WL colors: shallow depth {seed_depth}, deep depth {filter_depth} ...")
    shallow, deep = compute_wl_colors(datasets, seed_depth, filter_depth)
    shallow_cols = [shallow[c].colors for c in triple]
    deep_cols = [deep[c].colors for c in triple]
    adj = {c: build_adjacency(datasets[c]) for c in triple}

    # --- seeds: clique warm-start (full mapping) prepended to shallow-WL color-class seeds ---
    seed_source_effective = resolve_seed_source(cfg)
    wl_seeds = generate_seeds(shallow, datasets, triple, num_seeds, random.Random(rng_seed))
    clique_mapping = clique_seed(clique_cert_path, datasets, triple) if clique_cert_path else None

    jobs: list[tuple[str, list[tuple[int, int, int]]]] = []
    if clique_mapping:
        jobs.append(("clique_warmstart", clique_mapping))
        log(f"[engine_c] clique warm-start: {len(clique_mapping)} rows (floor to beat)")
    jobs += [("wl", [s]) for s in wl_seeds]
    log(f"[engine_c] {len(jobs)} seed jobs ({len(wl_seeds)} WL + "
        f"{1 if clique_mapping else 0} clique), source={seed_source_effective}")

    # --- connected (ON) growth over all seeds under the wall-clock budget ---
    on_deadline = time.monotonic() + time_budget_s * (0.85 if run_off_ablation else 1.0)
    best: dict[str, Any] | None = None
    per_seed: list[dict[str, Any]] = []
    for idx, (kind, init_mapping) in enumerate(jobs):
        if time.monotonic() >= on_deadline:
            log(f"[engine_c] budget reached after {idx} seeds; stopping ON phase")
            break
        tw = time.perf_counter()
        states = _states(datasets, triple, adj)
        res = grow_from_seed(
            init_mapping, states, shallow_cols, deep_cols,
            enforce_conn=enforce_conn, candidate_cap=caps["candidate_cap"],
            boundary_cap=caps["boundary_cap"], jump_pool=None,
            use_color_key=use_color_key, deadline=on_deadline,
        )
        rows_str = _rows_str(datasets, triple, res["rows_int"])
        rep = verify_candidate(triple, rows_str, datasets)
        rec = {
            "seed_index": idx, "kind": kind, "n": res["n"], "ok": rep.ok,
            "structure": rep.structure, "failed_check": rep.failed_check,
            "stopped_reason": res["stopped_reason"], "wall_clock_s": time.perf_counter() - tw,
        }
        per_seed.append(rec)
        if rep.ok and (best is None or res["n"] > best["n"]):
            best = {**rec, "columns": triple, "rows": rows_str, "verify": rep.to_dict()}
            log(f"[engine_c] new best connected N={res['n']} ({kind}, {rep.structure}) seed {idx}")

    # --- disconnected (OFF) ceiling: relax connectivity, allow components, from the strongest start ---
    best_disconnected: dict[str, Any] | None = None
    if run_off_ablation:
        jump_pool = generate_seeds(shallow, datasets, triple, caps["off_pool_cap"], random.Random(rng_seed))
        off_init = clique_mapping if clique_mapping else (wl_seeds[:1] if wl_seeds else [])
        if off_init:
            states = _states(datasets, triple, adj)
            off = grow_from_seed(
                off_init, states, shallow_cols, deep_cols,
                enforce_conn=False, candidate_cap=caps["candidate_cap"],
                boundary_cap=caps["boundary_cap"], jump_pool=jump_pool,
                use_color_key=use_color_key, deadline=time.monotonic() + time_budget_s * 0.15,
            )
            rows_str = _rows_str(datasets, triple, off["rows_int"])
            rep = verify_candidate(triple, rows_str, datasets)
            best_disconnected = {
                "n": off["n"], "columns": triple, "rows": rows_str,
                "stopped_reason": off["stopped_reason"], "verify": rep.to_dict(),
                "note": "connectivity-OFF N-ceiling; expected to fail only weak connectivity (check 4)",
            }
            log(f"[engine_c] disconnected ceiling N={off['n']} "
                f"(verify ok={rep.ok}, failed_check={rep.failed_check})")

    wall = time.perf_counter() - t_start
    summary = {
        "engine": "engine_c", "triple": triple, "config_seed": rng_seed,
        "seed_source_requested": cfg.get("engine_c", {}).get("seed_source"),
        "seed_source_effective": seed_source_effective,
        "num_seeds_requested": num_seeds, "num_seed_jobs": len(jobs),
        "enforce_weak_connectivity": enforce_conn, "use_color_key": use_color_key, "caps": caps,
        "time_budget_s": time_budget_s, "wall_clock_s": wall,
        "best_connected_n": best["n"] if best else 0,
        "best_disconnected_n": best_disconnected["n"] if best_disconnected else 0,
        "clique_warmstart_rows": len(clique_mapping) if clique_mapping else 0,
    }

    # --- write artifacts (mirror Engine A conventions) ---
    _write_artifacts(out_dir, triple, summary, best, best_disconnected, per_seed,
                     wl_seeds, seed_source_effective, rng_seed, datasets)
    log(f"[engine_c] best connected N = {summary['best_connected_n']}, "
        f"ceiling N = {summary['best_disconnected_n']} ({wall:.1f}s) -> {out_dir}")
    return summary


def _write_artifacts(out_dir, triple, summary, best, best_disconnected, per_seed,
                     wl_seeds, seed_source_effective, rng_seed, datasets) -> None:
    (out_dir / "seeds.json").write_text(json.dumps({
        "seed_source_requested": summary["seed_source_requested"],
        "seed_source_effective": seed_source_effective,
        "config_seed": rng_seed, "num_wl_seeds": len(wl_seeds),
        "wl_seeds_strids": [
            [datasets[c].int_to_id[node] for c, node in zip(triple, s)] for s in wl_seeds[:200]
        ],
    }, indent=2))

    if best:
        (out_dir / "best.json").write_text(json.dumps(best, indent=2))
    if best_disconnected:
        (out_dir / "best_disconnected.json").write_text(json.dumps(best_disconnected, indent=2))

    ps_dir = out_dir / "per_seed"
    ps_dir.mkdir(parents=True, exist_ok=True)
    for rec in sorted(per_seed, key=lambda r: r["n"], reverse=True)[:50]:
        (ps_dir / f"{rec['seed_index']:05d}.json").write_text(json.dumps(rec, indent=2))

    # certificate only when the connected best PASSES the verifier
    cert_rel = ""
    if best and best["ok"]:
        cert_dir = out_dir / "certificates"
        cert_dir.mkdir(parents=True, exist_ok=True)
        cert_rel = f"certificates/engine_c__{'-'.join(triple)}.csv"
        with (out_dir / cert_rel).open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(triple)
            w.writerows(best["rows"])

    with (out_dir / "frontier.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["engine", "triple", "n", "structure", "ok", "reason", "certificate", "connectivity"])
        if best:
            w.writerow(["engine_c", "|".join(triple), best["n"], best["structure"],
                        best["ok"], "", cert_rel, "weakly_connected"])
        if best_disconnected:
            v = best_disconnected["verify"]
            w.writerow(["engine_c", "|".join(triple), best_disconnected["n"], v.get("structure", ""),
                        v["ok"], v.get("reason", ""), "", "disconnected_ceiling"])

    lines = ["# Engine C — greedy seed-and-extend (generated)\n",
             f"- triple: **{' + '.join(triple)}**",
             f"- seed source: requested `{summary['seed_source_requested']}`, "
             f"effective `{seed_source_effective}`",
             f"- seed jobs: {summary['num_seed_jobs']} "
             f"(clique warm-start rows: {summary['clique_warmstart_rows']})",
             f"- caps: {summary['caps']}",
             f"- **best connected N: {summary['best_connected_n']}**"
             + (f" ({best['structure']})" if best else ""),
             f"- disconnected ceiling N: {summary['best_disconnected_n']} "
             f"(connectivity-OFF reference; fails only weak connectivity)",
             f"- wall-clock: {summary['wall_clock_s']:.1f}s (budget {summary['time_budget_s']}s)",
             f"- config seed: {summary['config_seed']}"]
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> None:
    cfg = config.get()
    ec = cfg["engine_c"]
    triple = list(ec["chosen_triple"])

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=int(ec["num_seeds"]))
    parser.add_argument("--time-budget", type=float, default=float(ec["time_budget_s"]))
    parser.add_argument("--out", default=Path(cfg["paths"]["results_dir"]) / "engine_c", type=Path)
    parser.add_argument("--no-off-ablation", action="store_true", help="skip the connectivity-OFF ceiling")
    parser.add_argument("--no-color-key", action="store_true",
                        help="demote shallow-WL color from the hard step key to an advisory score term")
    args = parser.parse_args(argv)

    caps = {k: int(ec.get(k, _DEFAULT_CAPS[k])) for k in _DEFAULT_CAPS}
    use_color_key = bool(ec.get("seed_color_key", True)) and not args.no_color_key

    print(f"[engine_c] loading triple {triple} ...", flush=True)
    datasets: dict[str, Dataset] = {}
    for name in triple:
        t0 = time.perf_counter()
        datasets[name] = load_dataset(name, cfg)
        ds = datasets[name]
        print(f"[engine_c] {name}: {ds.num_nodes:,} nodes / {ds.num_edges:,} edges "
              f"({time.perf_counter() - t0:.1f}s)", flush=True)

    cert_dir = Path(cfg["paths"]["results_dir"]) / "engine_a" / "certificates"
    clique_cert = cert_dir / f"reciprocal_clique__{'-'.join(sorted(triple))}.csv"

    run_engine_c(
        datasets, cfg, args.out,
        triple=triple, num_seeds=args.seeds, time_budget_s=args.time_budget,
        enforce_conn=bool(ec["enforce_weak_connectivity"]), caps=caps,
        rng_seed=config.seed(), use_color_key=use_color_key,
        clique_cert_path=clique_cert if clique_cert.exists() else None,
        run_off_ablation=not args.no_off_ablation,
    )


if __name__ == "__main__":
    main()
