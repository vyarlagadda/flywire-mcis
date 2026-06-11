"""CLI: compute structural fingerprints for the connectome datasets.

    python -m src.characterize.run [--dataset NAME | --all] [--out results/characterization]

Writes one ``<DATASET>.json`` per dataset, a ``config.snapshot.yaml``, and a ``summary.md`` table
that seeds the hand-written interpretation in ``docs/characterization.md``.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

from src import config
from src.characterize.metrics import characterize_dataset, compute_metrics
from src.io.loader import load_dataset


def _fmt_int(n: int) -> str:
    return f"{n:,}"


def _summary_row(m: dict[str, Any]) -> str:
    c = m["counts"]
    cor = m["coreness"]
    rec = m["reciprocity"]
    mot = m["motifs_size3"]
    # top connected isoclass by profile (index:fraction)
    prof = mot["profile"]
    best = max(
        (i for i, p in enumerate(prof) if p is not None),
        key=lambda i: prof[i],
        default=None,
    )
    top_motif = f"{best}:{prof[best]:.2f}" if best is not None else "-"
    return (
        f"| {m['name']} | {_fmt_int(c['num_nodes'])} | {_fmt_int(c['num_edges'])} | "
        f"{c['density']:.2e} | {rec['fraction']:.3f} | {_fmt_int(rec['dyad_census']['mutual'])} | "
        f"{cor['directed_degeneracy']} | {cor['reciprocal_degeneracy']} | "
        f"{cor['reciprocal_clique_upper_bound']} | {top_motif} | "
        f"{'yes' if mot['sampled'] else 'no'} |"
    )


def write_summary(metrics: list[dict[str, Any]], out_dir: Path) -> Path:
    header = (
        "# Characterization summary (generated)\n\n"
        "| dataset | nodes | edges | density | recip. frac | mutual dyads | "
        "dir. degeneracy | recip. degeneracy | recip-clique UB | top motif (iso:frac) | sampled |\n"
        "|---|--:|--:|--:|--:|--:|--:|--:|--:|---|---|\n"
    )
    body = "\n".join(_summary_row(m) for m in metrics)
    dest = out_dir / "summary.md"
    dest.write_text(header + body + "\n")
    return dest


def main(argv: list[str] | None = None) -> None:
    cfg = config.get()
    datasets = list(cfg["data"]["datasets"])

    parser = argparse.ArgumentParser(description=__doc__)
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--dataset", choices=datasets, help="characterize a single dataset")
    grp.add_argument("--all", action="store_true", help="characterize every dataset (default)")
    parser.add_argument(
        "--out", default=Path(cfg["paths"]["results_dir"]) / "characterization", type=Path
    )
    args = parser.parse_args(argv)

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    config.snapshot(out_dir)

    targets = [args.dataset] if args.dataset else datasets

    all_metrics: list[dict[str, Any]] = []
    for name in targets:
        t0 = time.perf_counter()
        print(f"[characterize] loading {name} ...", flush=True)
        ds = load_dataset(name, cfg)
        print(
            f"[characterize] {name}: {ds.num_nodes:,} nodes / {ds.num_edges:,} edges "
            f"(loaded in {time.perf_counter() - t0:.1f}s); computing metrics ...",
            flush=True,
        )
        metrics = compute_metrics(ds, cfg)
        characterize_dataset(ds, cfg, out_dir)  # writes <name>.json
        all_metrics.append(metrics)
        print(
            f"[characterize] {name}: done in {metrics['wall_clock_s']:.1f}s "
            f"(motif sampled={metrics['motifs_size3']['sampled']})",
            flush=True,
        )

    summary = write_summary(all_metrics, out_dir)
    print(f"[characterize] wrote {len(all_metrics)} json + {summary}", flush=True)


if __name__ == "__main__":
    main()
