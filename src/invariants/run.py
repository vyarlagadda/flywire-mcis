"""CLI: compute directed-WL colors per connectome and build the cross-dataset candidate pool.

    python -m src.invariants.run [--dataset NAME | --all] [--out results/invariants]

For each dataset it writes ``<DATASET>_colors.csv`` (neuron_id,wl_color) and ``<DATASET>.json``
(diagnostics). Across datasets it writes ``candidate_pool.json`` — the WL color classes present in
>= invariants.min_datasets_per_color_class datasets (the Engine B/C pool) — plus ``summary.md`` and a
``config.snapshot.yaml``.

WL is NECESSARY-not-sufficient: a shared color is a *candidate*, never a confirmed match. Only the
verifier (``src/verify``) confirms. Optional GDV (``invariants.gdv_enabled``) is computed only when
the orca binary is present; otherwise it is skipped gracefully.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

import scipy

from src import config
from src.invariants.gdv import gdv_available, gdv_signatures
from src.invariants.pool import ColorClass, color_classes
from src.invariants.wl import WLResult, directed_wl
from src.io.loader import Dataset, load_dataset

_POOL_NOTE = (
    "WL is NECESSARY but NOT SUFFICIENT: nodes sharing a color are CANDIDATE correspondences only; "
    "different colors cannot correspond. No match here is confirmed — only src/verify confirms."
)


def _fmt_int(n: int) -> str:
    return f"{n:,}"


def _class_size_histogram(res: WLResult) -> dict[str, int]:
    """Histogram of color-class sizes (how many colors are shared by exactly k nodes)."""
    sizes = Counter(int(c) for c in res.colors)
    hist = Counter(sizes.values())
    return {str(k): int(v) for k, v in sorted(hist.items())}


def _dataset_record(ds: Dataset, res: WLResult, cfg: dict[str, Any], wall_s: float) -> dict[str, Any]:
    return {
        "name": ds.name,
        "seed": int(cfg.get("seed", 0)),
        "scipy_version": scipy.__version__,
        "num_nodes": ds.num_nodes,
        "num_edges": ds.num_edges,
        "wl": {
            "depth": res.depth,
            "rounds_run": res.rounds_run,
            "num_classes": res.num_classes,
            "stabilized_at_round": res.stabilized_at_round,
        },
        "class_size_histogram": _class_size_histogram(res),
        "wall_clock_s": float(wall_s),
    }


def write_colors_csv(ds: Dataset, res: WLResult, out_dir: Path) -> Path:
    """Write ``<name>_colors.csv``: one row per node, ``neuron_id,wl_color`` (color as hex)."""
    dest = out_dir / f"{ds.name}_colors.csv"
    lines = ["neuron_id,wl_color"]
    for i, sid in enumerate(ds.int_to_id):
        lines.append(f"{sid},{int(res.colors[i]):016x}")
    dest.write_text("\n".join(lines) + "\n")
    return dest


def _pool_to_dict(classes: list[ColorClass], min_datasets: int) -> dict[str, Any]:
    return {
        "note": _POOL_NOTE,
        "min_datasets_per_color_class": min_datasets,
        "num_classes": len(classes),
        "classes": [
            {
                "color": f"{cc.color:016x}",
                "num_datasets": cc.num_datasets,
                "sizes": cc.sizes,
                "members": cc.members,
            }
            for cc in classes
        ],
    }


def write_summary(records: list[dict[str, Any]], classes: list[ColorClass], out_dir: Path) -> Path:
    header = (
        "# WL invariants summary (generated)\n\n"
        "| dataset | nodes | edges | depth | WL classes | stabilized@ |\n"
        "|---|--:|--:|--:|--:|--:|\n"
    )
    rows = "\n".join(
        f"| {r['name']} | {_fmt_int(r['num_nodes'])} | {_fmt_int(r['num_edges'])} | "
        f"{r['wl']['depth']} | {_fmt_int(r['wl']['num_classes'])} | "
        f"{r['wl']['stabilized_at_round']} |"
        for r in records
    )
    pool_line = (
        f"\n\n**Candidate pool:** {_fmt_int(len(classes))} color classes present in "
        f">= the configured number of datasets. {_POOL_NOTE}\n"
    )
    dest = out_dir / "summary.md"
    dest.write_text(header + rows + pool_line)
    return dest


def main(argv: list[str] | None = None) -> None:
    cfg = config.get()
    all_names = list(cfg["data"]["datasets"])
    inv = cfg["invariants"]
    depth = int(inv["wl_max_iterations"])
    min_datasets = int(inv["min_datasets_per_color_class"])

    parser = argparse.ArgumentParser(description=__doc__)
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--dataset", choices=all_names, help="process a single dataset")
    grp.add_argument("--all", action="store_true", help="process every dataset (default)")
    parser.add_argument("--out", default=Path(cfg["paths"]["results_dir"]) / "invariants", type=Path)
    args = parser.parse_args(argv)

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    config.snapshot(out_dir)

    targets = [args.dataset] if args.dataset else all_names

    datasets: dict[str, Dataset] = {}
    results: dict[str, WLResult] = {}
    records: list[dict[str, Any]] = []

    if inv.get("gdv_enabled", False) and not gdv_available(cfg):
        print("[invariants] gdv_enabled but orca binary not found — GDV skipped (WL unaffected).",
              flush=True)

    for name in targets:
        t0 = time.perf_counter()
        print(f"[invariants] loading {name} ...", flush=True)
        ds = load_dataset(name, cfg)
        print(f"[invariants] {name}: {ds.num_nodes:,} nodes / {ds.num_edges:,} edges "
              f"(loaded in {time.perf_counter() - t0:.1f}s); running directed-WL depth {depth} ...",
              flush=True)
        tw = time.perf_counter()
        res = directed_wl(ds, max_iterations=depth)
        wall = time.perf_counter() - tw

        # Optional GDV (graceful no-op when disabled/missing).
        gdv_signatures(ds, cfg)

        write_colors_csv(ds, res, out_dir)
        rec = _dataset_record(ds, res, cfg, wall)
        (out_dir / f"{name}.json").write_text(json.dumps(rec, indent=2))
        records.append(rec)
        datasets[name] = ds
        results[name] = res
        print(f"[invariants] {name}: {res.num_classes:,} WL classes, "
              f"stabilized@{res.stabilized_at_round} (refine {wall:.1f}s)", flush=True)

    classes = color_classes(results, datasets, min_datasets)
    (out_dir / "candidate_pool.json").write_text(json.dumps(_pool_to_dict(classes, min_datasets), indent=2))
    summary = write_summary(records, classes, out_dir)
    print(f"[invariants] candidate pool: {len(classes):,} classes in >= {min_datasets} datasets; "
          f"wrote {summary}", flush=True)


if __name__ == "__main__":
    main()
