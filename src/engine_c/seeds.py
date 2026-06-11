"""Seed generation for Engine C — shallow-WL color classes + the Engine A clique warm-start.

A *seed* is one matched node-triple ``(a, b, c)`` (compact ints, one per chosen dataset) whose three
nodes share a shallow directed-WL color — a necessary-not-sufficient signal that they may correspond.
Engine C grows the mapping greedily from each seed.

Two seed sources:
  - **WL** (the active path): shallow colors (``invariants.wl_seed_depth``) partition each dataset;
    cross-dataset color classes populated in all three chosen datasets yield candidate triples. Deep
    WL (``wl_filter_depth``) is a near-perfect *separator* — great as an inline rejection filter
    during growth, poor as a seed generator — so seeds use the *shallow* coloring.
  - **GDV** (requested in config but unavailable here): no orca binary, so ``resolve_seed_source``
    gracefully falls back to WL and records the substitution. WL stays the active filter.

Plus a **clique warm-start**: Engine A's verified reciprocal 38-clique is loaded as a full
ready-made mapping so the greedy can try to *extend* it — guaranteeing Engine C's overall best can
never regress below the certified floor.
"""
from __future__ import annotations

import random
import warnings
from pathlib import Path
from typing import Any

from src.invariants.gdv import gdv_available
from src.invariants.pool import color_classes
from src.invariants.wl import WLResult, directed_wl
from src.io.loader import Dataset


def resolve_seed_source(cfg: dict[str, Any]) -> str:
    """Resolve the *effective* seed source, falling back to WL whenever GDV can't be honored.

    GDV computation is not wired up (and no orca binary is installed), so a ``gdv`` request always
    degrades to ``wl`` with a ``RuntimeWarning`` — never a crash. Unknown sources also default to WL.
    """
    requested = cfg.get("engine_c", {}).get("seed_source", "wl")
    if requested == "wl":
        return "wl"
    if requested == "gdv":
        reason = (
            "the orca binary is absent"
            if not gdv_available(cfg)
            else "GDV seed computation is not wired up (WL is the active filter)"
        )
        warnings.warn(
            f"engine_c.seed_source=gdv requested but {reason}; falling back to WL seeds.",
            RuntimeWarning,
            stacklevel=2,
        )
        return "wl"
    warnings.warn(
        f"unknown engine_c.seed_source {requested!r}; using WL seeds.", RuntimeWarning, stacklevel=2
    )
    return "wl"


def compute_wl_colors(
    datasets: dict[str, Dataset], seed_depth: int, filter_depth: int
) -> tuple[dict[str, WLResult], dict[str, WLResult]]:
    """Compute ``(shallow, deep)`` directed-WL colorings per dataset.

    ``shallow`` (depth ``seed_depth``) drives seed generation; ``deep`` (depth ``filter_depth``) is
    the advisory rejection/tie-break filter consumed during growth. Computed once and reused across
    all seeds.
    """
    shallow = {name: directed_wl(ds, seed_depth) for name, ds in datasets.items()}
    deep = {name: directed_wl(ds, filter_depth) for name, ds in datasets.items()}
    return shallow, deep


def generate_seeds(
    shallow: dict[str, WLResult],
    datasets: dict[str, Dataset],
    triple: list[str],
    num_seeds: int,
    rng: random.Random,
) -> list[tuple[int, int, int]]:
    """Generate up to ``num_seeds`` compact-int seed triples from shallow color classes.

    Classes present in all three chosen datasets are formed; within a class, triples are drawn by the
    sorted-rank diagonal first (a deterministic alignment) then RNG-sampled combinations for larger
    classes. Seeds are emitted round-robin across classes (rarest/smallest class first) so the budget
    spreads across distinct colors rather than exhausting one. Fully deterministic given ``rng``.
    """
    cols = list(triple)
    sub_shallow = {c: shallow[c] for c in cols}
    sub_ds = {c: datasets[c] for c in cols}
    classes = color_classes(sub_shallow, sub_ds, min_datasets=3)
    # Prefer small (rarer, sharper) classes first; color breaks ties deterministically.
    classes.sort(key=lambda cc: (min(cc.sizes[c] for c in cols), cc.color))

    class_triples: list[list[tuple[int, int, int]]] = []
    for cc in classes:
        lists = [[sub_ds[c].id_to_int[s] for s in cc.members[c]] for c in cols]
        m = min(len(lst) for lst in lists)
        trips = [(lists[0][t], lists[1][t], lists[2][t]) for t in range(m)]
        # Extra sampled combinations for larger classes, capped so no single class hogs the budget.
        extra = min(max(len(lst) for lst in lists), num_seeds)
        for _ in range(extra):
            trips.append((
                lists[0][rng.randrange(len(lists[0]))],
                lists[1][rng.randrange(len(lists[1]))],
                lists[2][rng.randrange(len(lists[2]))],
            ))
        class_triples.append(trips)

    seeds: list[tuple[int, int, int]] = []
    seen: set[tuple[int, int, int]] = set()
    idx = 0
    while len(seeds) < num_seeds and any(idx < len(ct) for ct in class_triples):
        for ct in class_triples:
            if idx < len(ct):
                tr = ct[idx]
                if tr not in seen:
                    seen.add(tr)
                    seeds.append(tr)
                    if len(seeds) >= num_seeds:
                        break
        idx += 1
    return seeds


def clique_seed(
    path: Path | str, datasets: dict[str, Dataset], triple: list[str]
) -> list[tuple[int, int, int]] | None:
    """Load Engine A's verified clique certificate as a full warm-start mapping (compact-int triples).

    The certificate header may order the three datasets differently from ``triple``; rows are
    reordered into ``triple`` column order. Returns ``None`` if the file is missing or its header is
    not exactly the chosen triple (so a stale/foreign certificate is ignored, not misused).
    """
    p = Path(path)
    if not p.exists():
        return None
    from src.verify.check import read_candidate  # parser only; no graph dependency

    header, rows = read_candidate(p)
    if sorted(header) != sorted(triple):
        return None
    pos = {name: header.index(name) for name in triple}
    mapping: list[tuple[int, int, int]] = []
    for row in rows:
        mapping.append(tuple(datasets[c].id_to_int[row[pos[c]]] for c in triple))  # type: ignore[arg-type]
    return mapping
