"""Data IO layer.

Only the pure, library-agnostic loader symbols are re-exported here, so that ``import src.io`` (the
verifier's path) never pulls in igraph. The igraph builders live in :mod:`src.io.graphs` and are
imported explicitly by the engines: ``from src.io.graphs import to_igraph, to_reciprocal_igraph``.
"""
from src.io.loader import (
    Dataset,
    build_adjacency,
    load_all,
    load_dataset,
    load_edge_list,
)

__all__ = [
    "Dataset",
    "build_adjacency",
    "load_all",
    "load_dataset",
    "load_edge_list",
]
