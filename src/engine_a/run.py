"""CLI: run Engine A families per dataset, then assemble + verify the frontier.

    python -m src.engine_a.run [--dataset NAME | --all] [--families F ...] [--out results/engine_a]

For each enabled family × dataset it writes ``<out>/<family>/<dataset>.json`` (the per-dataset
instance: size, members, upper bound, method, wall-clock, seed). It then aligns every (family ×
triple) and runs it through the verifier (``src.verify``), writing ``<out>/frontier.csv`` (all rows)
and ``<out>/certificates/<family>__<D1>-<D2>-<D3>.csv`` for every verifier-PASS candidate. A
``config.snapshot.yaml`` and per-family ``summary.md`` are written too.

Engine A is the certified FLOOR: every emitted N is a verified LOWER bound + certificate; the
reciprocal-clique ``upper_bound`` (degeneracy+1) is reported separately and never claimed as achieved.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Any, Callable

from src import config
from src.engine_a.biclique import complete_bipartite
from src.engine_a.clique import reciprocal_clique
from src.engine_a.frontier import assemble_frontier
from src.engine_a.star import directed_star
from src.io.loader import Dataset, load_dataset

# family name -> (solver, output subdir)
_FAMILIES: dict[str, tuple[Callable[[Dataset, dict], dict], str]] = {
    "reciprocal_clique": (reciprocal_clique, "clique"),
    "directed_star": (directed_star, "star"),
    "complete_bipartite": (complete_bipartite, "biclique"),
}


def _write_summary(instances: dict[str, dict[str, dict]], out_dir: Path) -> None:
    lines = ["# Engine A — per-dataset family sizes (generated)\n"]
    for family, inst in instances.items():
        lines.append(f"\n## {family}\n")
        lines.append("| dataset | n (LB) | upper_bound | detail |")
        lines.append("|---|--:|--:|---|")
        for d, r in inst.items():
            extra = r.get("method") or r.get("orientation") or ("skipped" if r.get("skipped") else "")
            lines.append(f"| {d} | {r['n']} | {r.get('upper_bound', 0)} | {extra} |")
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n")


def _write_certificate(path: Path, columns: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(columns)
        w.writerows(rows)


def _write_frontier(frontier: list[dict], out_dir: Path) -> list[dict]:
    cert_dir = out_dir / "certificates"
    rows_sorted = sorted(frontier, key=lambda r: (r["ok"], r["n"]), reverse=True)
    csv_path = out_dir / "frontier.csv"
    with csv_path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["family", "triple", "n", "structure", "ok", "reason", "certificate"])
        for r in rows_sorted:
            cert = ""
            if r["ok"]:
                tri = "-".join(r["triple"])
                cert = f"certificates/{r['family']}__{tri}.csv"
                _write_certificate(cert_dir / f"{r['family']}__{tri}.csv", r["columns"], r["candidate_rows"])
            w.writerow([r["family"], "|".join(r["triple"]), r["n"], r["structure"],
                        r["ok"], r["reason"], cert])
    return rows_sorted


def main(argv: list[str] | None = None) -> None:
    cfg = config.get()
    all_names = list(cfg["data"]["datasets"])
    cfg_families = list(cfg["engine_a"]["families"])

    parser = argparse.ArgumentParser(description=__doc__)
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--dataset", choices=all_names, help="process a single dataset")
    grp.add_argument("--all", action="store_true", help="process every dataset (default)")
    parser.add_argument("--families", nargs="+", choices=list(_FAMILIES), default=cfg_families)
    parser.add_argument("--out", default=Path(cfg["paths"]["results_dir"]) / "engine_a", type=Path)
    args = parser.parse_args(argv)

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    config.snapshot(out_dir)

    targets = [args.dataset] if args.dataset else all_names
    families = [f for f in args.families if f in _FAMILIES]

    print(f"[engine_a] loading {len(targets)} dataset(s) ...", flush=True)
    datasets: dict[str, Dataset] = {}
    for name in targets:
        t0 = time.perf_counter()
        datasets[name] = load_dataset(name, cfg)
        ds = datasets[name]
        print(f"[engine_a] {name}: {ds.num_nodes:,} nodes / {ds.num_edges:,} edges "
              f"({time.perf_counter() - t0:.1f}s)", flush=True)

    instances: dict[str, dict[str, dict]] = {f: {} for f in families}
    for family in families:
        solver, subdir = _FAMILIES[family]
        fdir = out_dir / subdir
        fdir.mkdir(parents=True, exist_ok=True)
        for name, ds in datasets.items():
            tw = time.perf_counter()
            res = solver(ds, cfg)
            (fdir / f"{name}.json").write_text(json.dumps(res, indent=2))
            instances[family][name] = res
            print(f"[engine_a] {family} / {name}: n={res['n']} "
                  f"(ub={res.get('upper_bound', 0)}, {time.perf_counter() - tw:.1f}s)", flush=True)

    _write_summary(instances, out_dir)

    frontier = assemble_frontier(instances, datasets)
    rows_sorted = _write_frontier(frontier, out_dir)

    # Report: best verified N per family + the top verified triples.
    print("\n[engine_a] === verified frontier (lower bounds) ===", flush=True)
    for family in families:
        ok_rows = [r for r in frontier if r["family"] == family and r["ok"]]
        if ok_rows:
            best = max(ok_rows, key=lambda r: r["n"])
            print(f"[engine_a] {family}: best verified N = {best['n']} "
                  f"on {'+'.join(best['triple'])} ({len(ok_rows)} passing triples)", flush=True)
        else:
            print(f"[engine_a] {family}: no verified triple", flush=True)

    top = [r for r in rows_sorted if r["ok"]][:5]
    if top:
        print("[engine_a] top verified triples:", flush=True)
        for r in top:
            print(f"    N={r['n']:>4}  {r['family']:<19} {'+'.join(r['triple'])}", flush=True)
    print(f"[engine_a] wrote {out_dir/'frontier.csv'}", flush=True)


if __name__ == "__main__":
    main()
