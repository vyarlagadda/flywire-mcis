"""CLI: Engine B — k-core reduction + Python McSplit for directed 3-graph MCCS.

Three gated steps (run each separately and review output before proceeding):
  python -m src.engine_b.run --step 1   # k-core reduce + report surviving count
  python -m src.engine_b.run --step 2   # McSplit B&B search on reduced graphs
  python -m src.engine_b.run --step 3   # verify + finalize + copy to network.csv

State is threaded through files under --out (default: results/engine_b/).
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

from src import config
from src.engine_b.mcsplit import mcsplit_3graph
from src.engine_b.reduce import kcore_reduce
from src.io.loader import Dataset, build_adjacency, load_dataset
from src.verify.check import verify_candidate

_TRIPLE = ["BANC", "FAFB", "MCNS"]
_CLIQUE_CERT = "results/engine_a/certificates/reciprocal_clique__BANC-FAFB-MCNS.csv"


def _load_cert(path: str) -> tuple[list[str], list[list[str]]]:
    with open(path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = [row for row in reader if row]
    return header, rows


def step1(cfg: dict, out_dir: Path) -> None:
    print("[engine_b/step1] loading datasets ...", flush=True)
    datasets = {n: load_dataset(n, cfg) for n in _TRIPLE}

    cert_path = cfg["engine_b"]["source_certificate"]
    _, cert_rows = _load_cert(cert_path)
    print(f"[engine_b/step1] source certificate: {len(cert_rows)} nodes  ({cert_path})", flush=True)

    kcore_min = cfg["engine_b"]["reduce"]["kcore_min"]
    print(f"[engine_b/step1] k-core peeling (kcore_min={kcore_min}) ...", flush=True)

    ds_list = [datasets[n] for n in _TRIPLE]
    surviving = kcore_reduce(ds_list, cert_rows, _TRIPLE, kcore_min)
    n_surviving = len(surviving[0])
    print(f"[engine_b/step1] surviving nodes after peeling: {n_surviving}", flush=True)

    _, clique_rows = _load_cert(_CLIQUE_CERT)
    surviving_sets = [set(s) for s in surviving]
    missing = sum(
        1 for row in clique_rows
        if any(row[i] not in surviving_sets[i] for i in range(3))
    )
    status = "ALL PRESENT" if missing == 0 else f"SOME MISSING ({missing}) — check kcore_min"
    print(f"[engine_b/step1] clique members missing after reduction: {missing} ({status})", flush=True)

    cand_dir = out_dir / "candidates"
    cand_dir.mkdir(parents=True, exist_ok=True)
    for i, name in enumerate(_TRIPLE):
        (cand_dir / f"{name}_candidates.txt").write_text("\n".join(surviving[i]))
    config.snapshot(out_dir)

    meta = {
        "n_source": len(cert_rows),
        "n_surviving": n_surviving,
        "kcore_min": kcore_min,
        "clique_members_missing": missing,
    }
    (out_dir / "step1_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"[engine_b/step1] wrote candidates → {cand_dir}", flush=True)
    print(f"[engine_b/step1] DONE — surviving={n_surviving}, clique_missing={missing}", flush=True)


def step2(cfg: dict, out_dir: Path) -> None:
    cand_dir = out_dir / "candidates"
    surviving = [
        (cand_dir / f"{name}_candidates.txt").read_text().splitlines()
        for name in _TRIPLE
    ]
    n_red = len(surviving[0])
    print(f"[engine_b/step2] reduced instance: {n_red} nodes per graph", flush=True)

    datasets = {n: load_dataset(n, cfg) for n in _TRIPLE}
    adjs = [build_adjacency(datasets[name]) for name in _TRIPLE]

    nodes_int: list[list[int]] = [
        [datasets[_TRIPLE[i]].id_to_int[s] for s in surviving[i]]
        for i in range(3)
    ]

    solver_cfg = cfg["engine_b"]["solver"]
    timeout_s = float(solver_cfg["time_budget_s"])
    connected = bool(solver_cfg["connected"])

    print(
        f"[engine_b/step2] McSplit B&B (timeout={timeout_s}s, connected={connected}, "
        f"best_known=38) ...",
        flush=True,
    )
    t0 = time.perf_counter()
    mapping = mcsplit_3graph(
        adjs[0][0], adjs[0][1],
        adjs[1][0], adjs[1][1],
        adjs[2][0], adjs[2][1],
        nodes_int[0], nodes_int[1], nodes_int[2],
        best_known=38,
        connected=connected,
        timeout_s=timeout_s,
    )
    elapsed = time.perf_counter() - t0

    if mapping is None:
        print(f"[engine_b/step2] no improvement over 38 found  ({elapsed:.1f}s)", flush=True)
        result = {"best_n": 38, "beats_clique": False, "elapsed_s": elapsed, "mapping": None}
    else:
        best_n = len(mapping)
        rows_str = [
            [datasets[_TRIPLE[i]].int_to_id[t[i]] for i in range(3)]
            for t in mapping
        ]
        print(f"[engine_b/step2] best found: N={best_n}  ({elapsed:.1f}s)", flush=True)
        result = {
            "best_n": best_n,
            "beats_clique": best_n > 38,
            "elapsed_s": elapsed,
            "mapping": rows_str,
        }

    sol_dir = out_dir / "solutions"
    sol_dir.mkdir(parents=True, exist_ok=True)
    (sol_dir / "best.json").write_text(json.dumps(result, indent=2))
    print(f"[engine_b/step2] wrote {sol_dir / 'best.json'}", flush=True)
    print(f"[engine_b/step2] DONE — best_N={result['best_n']}", flush=True)


def step3(cfg: dict, out_dir: Path) -> None:
    result = json.loads((out_dir / "solutions" / "best.json").read_text())
    best_n = result["best_n"]
    print(f"[engine_b/step3] best N from step2: {best_n}", flush=True)

    datasets = {n: load_dataset(n, cfg) for n in _TRIPLE}
    verified = False
    report_dict: dict = {}

    if result["mapping"] is not None:
        rows_str: list[list[str]] = result["mapping"]
        report = verify_candidate(_TRIPLE, rows_str, datasets)
        verified = report.ok
        report_dict = report.to_dict()
        print(
            f"[engine_b/step3] verifier: ok={report.ok}, n={report.n}, "
            f"structure={report.structure}",
            flush=True,
        )
        if report.ok and report.n > 38:
            cert_dir = out_dir / "certificates"
            cert_dir.mkdir(parents=True, exist_ok=True)
            cert_path = cert_dir / f"engine_b__{'_'.join(_TRIPLE)}.csv"
            with cert_path.open("w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(_TRIPLE)
                w.writerows(rows_str)
            print(f"[engine_b/step3] certificate → {cert_path}", flush=True)

            root_csv = Path("network.csv")
            with root_csv.open("w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(_TRIPLE)
                w.writerows(rows_str)
            root_report = verify_candidate(_TRIPLE, rows_str, datasets)
            print(
                f"[engine_b/step3] network.csv verifier: ok={root_report.ok}, n={root_report.n}",
                flush=True,
            )
    else:
        print("[engine_b/step3] no mapping in step2; Engine A 38-clique remains submission", flush=True)

    meta = json.loads((out_dir / "step1_meta.json").read_text())
    summary = {
        "source_certificate": cfg["engine_b"]["source_certificate"],
        "kcore_min_used": cfg["engine_b"]["reduce"]["kcore_min"],
        "core_size": meta["n_surviving"],
        "best_N_found": best_n,
        "verified": verified,
        "beats_clique": verified and best_n > 38,
        "verifier_report": report_dict,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"[engine_b/step3] wrote {out_dir / 'summary.json'}", flush=True)
    print(
        f"[engine_b/step3] DONE — verified={verified}, beats_clique={summary['beats_clique']}",
        flush=True,
    )


def main(argv: list[str] | None = None) -> None:
    cfg = config.get()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--step", type=int, choices=[1, 2, 3], required=True,
        help="Step to run: 1=reduce  2=mcsplit  3=verify+finalize",
    )
    parser.add_argument(
        "--out", default=Path(cfg["paths"]["results_dir"]) / "engine_b", type=Path,
    )
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    if args.step == 1:
        step1(cfg, args.out)
    elif args.step == 2:
        step2(cfg, args.out)
    elif args.step == 3:
        step3(cfg, args.out)


if __name__ == "__main__":
    main()
