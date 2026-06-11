"""Cross-dataset WL color classes — the Engine B/C candidate pool.

Group every node by its stable directed-WL color (comparable across datasets, see ``wl.py``) and
keep the classes populated in at least ``min_datasets`` distinct datasets. That intersection is the
pruned pool of plausible correspondences.

WL is NECESSARY-not-sufficient: a shared color means the nodes *may* correspond; it is never a
confirmed match. Only the verifier (``src/verify``) confirms.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.invariants.wl import WLResult
from src.io.loader import Dataset


@dataclass
class ColorClass:
    """One WL color present in >= min_datasets datasets, with its per-dataset member string ids."""

    color: int
    num_datasets: int
    members: dict[str, list[str]]  # dataset name -> sorted string ids carrying this color
    sizes: dict[str, int]


def color_classes(
    results: dict[str, WLResult],
    datasets: dict[str, Dataset],
    min_datasets: int,
) -> list[ColorClass]:
    """Build the candidate pool: color classes present in >= ``min_datasets`` datasets.

    ``results`` and ``datasets`` are keyed by dataset name; node ids are mapped back to their original
    strings via ``Dataset.int_to_id``. Returned classes are sorted by descending dataset count then by
    color, and member id lists are sorted for determinism.
    """
    # color -> {dataset name -> [string ids]}
    by_color: dict[int, dict[str, list[str]]] = {}
    for name, res in results.items():
        int_to_id = datasets[name].int_to_id
        for i, c in enumerate(res.colors):
            key = int(c)
            by_color.setdefault(key, {}).setdefault(name, []).append(int_to_id[i])

    classes: list[ColorClass] = []
    for color, per_ds in by_color.items():
        if len(per_ds) < min_datasets:
            continue
        members = {name: sorted(ids) for name, ids in per_ds.items()}
        sizes = {name: len(ids) for name, ids in members.items()}
        classes.append(
            ColorClass(color=color, num_datasets=len(members), members=members, sizes=sizes)
        )

    classes.sort(key=lambda cc: (-cc.num_datasets, cc.color))
    return classes
