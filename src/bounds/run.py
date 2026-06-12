"""CLI: compute and write bounds summary for Phase P7.

    python -m src.bounds.run [--out results/bounds] [--skip-ablation] [--results-dir results]

Loads per-engine result files, compiles lower and upper bounds, optionally runs a multi-seed
Engine C ablation, and writes ``{out}/summary.json`` + ``{out}/config.snapshot.yaml``.

Does not load data/raw — reads only already-written JSON/CSV result files.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from src import config
from src.bounds.compute import (
    build_summary,
    collect_lower_bounds,
    collect_upper_bounds,
    run_ablation,
)


def main(argv: list[str] | None = None) -> int:
    cfg = config.get()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=Path(cfg["paths"]["results_dir"]) / "bounds",
        type=Path,
        help="Directory to write summary.json and config.snapshot.yaml into.",
    )
    parser.add_argument(
        "--skip-ablation",
        action="store_true",
        help="Skip the multi-seed Engine C ablation (faster; use during development).",
    )
    parser.add_argument(
        "--results-dir",
        default=Path(cfg["paths"]["results_dir"]),
        type=Path,
        help="Root results directory containing engine_a/, engine_c/, engine_b/, invariants/.",
    )
    args = parser.parse_args(argv)

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    config.snapshot(out_dir)

    results_dir: Path = args.results_dir
    print(f"[bounds] collecting lower bounds from {results_dir} ...", flush=True)
    lower_bounds = collect_lower_bounds(results_dir)
    print(f"[bounds] found {len(lower_bounds)} verified lower bound(s)", flush=True)

    print("[bounds] collecting upper bounds ...", flush=True)
    upper_bounds = collect_upper_bounds(results_dir, cfg)
    deg = upper_bounds.get("degeneracy_clique", {})
    if deg:
        print(f"[bounds] degeneracy upper bounds: {deg}", flush=True)

    ablation: dict[int, Any] = {}
    if not args.skip_ablation:
        bounds_cfg = cfg.get("bounds", {})
        seeds: list[int] = [int(s) for s in bounds_cfg.get("ablation_seeds", [1, 2, 3, 4, 5])]
        triple = list(cfg["engine_c"]["chosen_triple"])
        print(f"[bounds] running Engine C ablation over seeds={seeds} triple={triple} ...",
              flush=True)

        from src.io.loader import load_dataset
        datasets = {}
        for name in triple:
            datasets[name] = load_dataset(name, cfg)
            print(f"[bounds] loaded {name}", flush=True)

        ablation = run_ablation(cfg, out_dir, seeds=seeds, datasets=datasets, triple=triple)
        print(f"[bounds] ablation results: {ablation}", flush=True)
    else:
        print("[bounds] skipping ablation (--skip-ablation)", flush=True)

    summary = build_summary(
        lower_bounds=lower_bounds,
        upper_bounds=upper_bounds,
        ablation=ablation,
        cfg_seed=config.seed(),
    )

    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"[bounds] wrote {summary_path}", flush=True)
    print(
        f"[bounds] best_lower_bound={summary['best_lower_bound']}, "
        f"tightest_upper_bound={summary['tightest_upper_bound']}, "
        f"gap={summary['gap']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
