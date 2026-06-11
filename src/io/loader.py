"""Streaming edge-list loader and the library-agnostic graph core.

This module is **pure Python** and must never import igraph: the verifier (``src/verify``) depends
on it, and the hard rule is that the verifier never depends on a graph library. The igraph
representations live in ``src.io.graphs`` and are built from the same :class:`Dataset`.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Dataset:
    """One connectome loaded into a compact, library-agnostic core.

    Neuron IDs are kept as strings (BANC/FAFB use 18-digit root IDs that overflow int64) and
    interned to compact ints. ``int_to_id`` is the reverse map (list index == compact int);
    ``edges`` is the cleaned directed edge collection. Node set == endpoints of post-cleanup edges,
    so there are no degree-0 vertices by construction.
    """

    name: str
    int_to_id: list[str] = field(default_factory=list)
    id_to_int: dict[str, int] = field(default_factory=dict)
    edges: Any = field(default_factory=set)  # set[tuple[int,int]] or list[tuple[int,int]]

    @property
    def num_nodes(self) -> int:
        return len(self.int_to_id)

    @property
    def num_edges(self) -> int:
        return len(self.edges)


def load_edge_list(
    path: Path | str,
    *,
    name: str = "",
    drop_self_loops: bool = True,
    collapse_parallel_edges: bool = True,
) -> Dataset:
    """Stream an edge-list CSV into a :class:`Dataset`.

    The file is iterated row-by-row (never read whole) so 100 MB inputs stay cheap. The header line
    (``source neuron id,target neuron id``) is skipped. IDs are interned as strings.

    - ``drop_self_loops``: skip rows where source == target.
    - ``collapse_parallel_edges``: dedup edges via a ``set`` (the simple-directed-graph default);
      when False, edges are accumulated into a ``list`` and multiplicity is preserved.
    """
    id_to_int: dict[str, int] = {}
    int_to_id: list[str] = []

    def intern(s: str) -> int:
        i = id_to_int.get(s)
        if i is None:
            i = len(int_to_id)
            id_to_int[s] = i
            int_to_id.append(s)
        return i

    edges: set[tuple[int, int]] | list[tuple[int, int]]
    edges = set() if collapse_parallel_edges else []

    with open(path, newline="") as fh:
        reader = csv.reader(fh)
        next(reader, None)  # discard header
        for row in reader:
            if not row:
                continue
            src = row[0].strip()
            tgt = row[1].strip()
            if not src and not tgt:
                continue
            if drop_self_loops and src == tgt:
                continue
            u = intern(src)
            v = intern(tgt)
            if collapse_parallel_edges:
                edges.add((u, v))  # type: ignore[union-attr]
            else:
                edges.append((u, v))  # type: ignore[union-attr]

    return Dataset(name=name, int_to_id=int_to_id, id_to_int=id_to_int, edges=edges)


def build_adjacency(ds: Dataset) -> tuple[dict[int, set[int]], dict[int, set[int]]]:
    """Pure dict/set adjacency for the verifier.

    Returns ``(out_neighbors, in_neighbors)``: for edge u->v, ``v in out[u]`` and ``u in in[v]``.
    Every node in ``range(num_nodes)`` is a key, even if its set is empty.
    """
    out: dict[int, set[int]] = {i: set() for i in range(ds.num_nodes)}
    inn: dict[int, set[int]] = {i: set() for i in range(ds.num_nodes)}
    for u, v in ds.edges:
        out[u].add(v)
        inn[v].add(u)
    return out, inn


def load_dataset(name: str, cfg: dict[str, Any] | None = None) -> Dataset:
    """Load a dataset named in config (resolves path + cleaning flags from ``config.yaml``)."""
    if cfg is None:
        from src import config

        cfg = config.get()
    data = cfg["data"]
    path = Path(data["dir"]) / data["datasets"][name]
    return load_edge_list(
        path,
        name=name,
        drop_self_loops=data.get("drop_self_loops", True),
        collapse_parallel_edges=data.get("collapse_parallel_edges", True),
    )


def load_all(cfg: dict[str, Any] | None = None) -> dict[str, Dataset]:
    """Load every dataset declared in ``config['data']['datasets']``."""
    if cfg is None:
        from src import config

        cfg = config.get()
    return {name: load_dataset(name, cfg) for name in cfg["data"]["datasets"]}
