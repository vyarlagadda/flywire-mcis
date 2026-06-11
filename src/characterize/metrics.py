"""Per-dataset structural metrics computed with igraph.

This is engine-side code, so importing igraph here is fine — only the *verifier* (``src/verify``)
must stay igraph-free. Everything is derived from a :class:`~src.io.loader.Dataset` so igraph vertex
indices align 1:1 with the compact ints the verifier's adjacency uses.

The output dict is JSON-serializable with ``allow_nan=False``: disconnected motif isoclasses (which
igraph returns as NaN) are stored as ``None``.
"""
from __future__ import annotations

import math
import random
import statistics
import time
from pathlib import Path
from typing import Any

import igraph

from src.io.graphs import to_igraph, to_reciprocal_igraph
from src.io.loader import Dataset

# Directed 3-node motif isoclasses that igraph leaves unclassified (disconnected / < 3 vertices).
# igraph returns NaN for these; we surface them as None and exclude them from the profile.


def _degree_summary(degs: list[int], quantiles: list[float]) -> dict[str, Any]:
    """Min/max/mean/median/std + requested quantiles for a degree sequence."""
    if not degs:
        return {"min": 0, "max": 0, "mean": 0.0, "median": 0.0, "std": 0.0, "quantiles": {}}
    s = sorted(degs)
    n = len(s)

    def q(p: float) -> float:
        # nearest-rank on the sorted sequence (deterministic, no interpolation surprises)
        if n == 1:
            return float(s[0])
        idx = min(n - 1, max(0, int(math.ceil(p * n)) - 1))
        return float(s[idx])

    return {
        "min": int(s[0]),
        "max": int(s[-1]),
        "mean": float(statistics.fmean(s)),
        "median": float(statistics.median(s)),
        "std": float(statistics.pstdev(s)) if n > 1 else 0.0,
        "quantiles": {f"p{int(round(p * 100))}": q(p) for p in quantiles},
    }


def _tails(degs: list[int], names: list[str], k: int) -> list[dict[str, Any]]:
    """Top-k nodes by degree, recorded with their original string id."""
    order = sorted(range(len(degs)), key=lambda i: degs[i], reverse=True)[:k]
    return [{"id": names[i], "degree": int(degs[i])} for i in order]


def _motif_census(
    g: igraph.Graph, *, size: int, sampled: bool, cut_prob: list[float] | None, seed: int
) -> dict[str, Any]:
    """Directed n-node motif census via ``motifs_randesu``.

    When ``sampled`` is True we pass ``cut_prob`` (probability a search-tree branch is skipped at
    each level) — the returned counts are then an *undercount of the sampled branches*, not a scaled
    total, so cross-dataset comparison must use the normalized ``profile`` rather than raw counts.
    NaN isoclasses (disconnected) become ``None``.
    """
    t0 = time.perf_counter()
    if sampled:
        # Seed igraph's RNG for reproducibility of the sampled census.
        igraph.set_random_number_generator(random)
        random.seed(seed)
        raw = g.motifs_randesu(size=size, cut_prob=cut_prob)
    else:
        raw = g.motifs_randesu(size=size)
    elapsed = time.perf_counter() - t0

    counts: list[int | None] = [None if (isinstance(c, float) and math.isnan(c)) else int(c) for c in raw]
    connected_total = sum(c for c in counts if c is not None)
    profile: list[float | None] = [
        None if c is None else (c / connected_total if connected_total else 0.0) for c in counts
    ]
    return {
        "sampled": sampled,
        "cut_prob": cut_prob if sampled else None,
        "seed": seed,
        "counts": counts,
        "profile": profile,
        "total_connected": int(g.motifs_randesu_no(size=size)),
        "total_connected_approx": sampled,
        "wall_clock_s": float(elapsed),
    }


def compute_metrics(ds: Dataset, cfg: dict[str, Any]) -> dict[str, Any]:
    """Compute the full structural fingerprint for one dataset.

    Builds the directed and reciprocal igraph graphs from *ds* and returns a JSON-serializable dict.
    Sampling of the motif census is triggered when ``num_edges >= dense_edge_threshold``.
    """
    t0 = time.perf_counter()
    ch = cfg["characterize"]
    seed = int(cfg.get("seed", 0))

    g = to_igraph(ds)
    recip = to_reciprocal_igraph(ds)
    names = g.vs["name"]

    # --- counts ---
    counts = {
        "num_nodes": g.vcount(),
        "num_edges": g.ecount(),
        "density": float(g.density(loops=False)),
    }

    # --- degree ---
    deg_in = g.degree(mode="in")
    deg_out = g.degree(mode="out")
    deg_total = g.degree(mode="all")
    quantiles = ch["degree_quantiles"]
    k = ch["degree_tail_k"]
    degree = {
        "in": _degree_summary(deg_in, quantiles),
        "out": _degree_summary(deg_out, quantiles),
        "total": _degree_summary(deg_total, quantiles),
        "tails": {
            "top_in": _tails(deg_in, names, k),
            "top_out": _tails(deg_out, names, k),
        },
    }

    # --- reciprocity ---
    mutual, asymmetric, null = g.dyad_census()
    reciprocity = {
        "fraction": float(g.reciprocity(mode="default")) if g.ecount() else 0.0,
        "dyad_census": {"mutual": int(mutual), "asymmetric": int(asymmetric), "null": int(null)},
    }

    # --- coreness / degeneracy ---
    directed_coreness = g.coreness(mode="all")
    recip_coreness = recip.coreness()
    recip_degeneracy = int(max(recip_coreness)) if recip_coreness else 0
    coreness = {
        "directed_degeneracy": int(max(directed_coreness)) if directed_coreness else 0,
        "reciprocal_degeneracy": recip_degeneracy,
        "reciprocal_clique_upper_bound": recip_degeneracy + 1,
        "reciprocal_edges": recip.ecount(),
        "reciprocal_nonisolated_nodes": int(sum(1 for d in recip.degree() if d > 0)),
    }

    # --- motif census ---
    sampled = counts["num_edges"] >= ch["dense_edge_threshold"]
    motifs = _motif_census(
        g,
        size=ch["motif_size"],
        sampled=sampled,
        cut_prob=list(ch["motif_cut_prob"]) if sampled else None,
        seed=seed,
    )

    return {
        "name": ds.name,
        "seed": seed,
        "igraph_version": igraph.__version__,
        "counts": counts,
        "degree": degree,
        "reciprocity": reciprocity,
        "coreness": coreness,
        "motifs_size3": motifs,
        "wall_clock_s": float(time.perf_counter() - t0),
    }


def characterize_dataset(ds: Dataset, cfg: dict[str, Any], out_dir: Path | str) -> Path:
    """Compute metrics for *ds* and write ``<out_dir>/<name>.json``; return the path."""
    import json

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics = compute_metrics(ds, cfg)
    dest = out_dir / f"{ds.name}.json"
    dest.write_text(json.dumps(metrics, indent=2, allow_nan=False))
    return dest
