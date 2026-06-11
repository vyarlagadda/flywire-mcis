"""igraph representations built from a :class:`~src.io.loader.Dataset`.

This module imports igraph and is for the **engines only**. The verifier must never import it (and
``src.io.__init__`` deliberately does not re-export from here), preserving the verifier's
independence from any graph library.
"""
from __future__ import annotations

import igraph

from src.io.loader import Dataset


def to_igraph(ds: Dataset) -> igraph.Graph:
    """Directed igraph graph. Vertex index == the dataset's compact int id; original string IDs are
    stored in ``vs['name']`` (so they round-trip), keeping indices aligned with ``build_adjacency``.
    """
    g = igraph.Graph(n=ds.num_nodes, edges=list(ds.edges), directed=True)
    g.vs["name"] = ds.int_to_id
    return g


def to_reciprocal_igraph(ds: Dataset) -> igraph.Graph:
    """Undirected graph of mutual (reciprocal) edges only — for Engine A.

    An undirected edge {u,v} exists iff both u->v and v->u are present. The full node set is kept
    (``n = num_nodes``) so indices still align with the directed graph / adjacency; nodes with no
    reciprocal partner are simply isolated.
    """
    edge_set = ds.edges if isinstance(ds.edges, set) else set(ds.edges)
    mutual = {
        (u, v) if u < v else (v, u)
        for (u, v) in edge_set
        if u != v and (v, u) in edge_set
    }
    g = igraph.Graph(n=ds.num_nodes, edges=list(mutual), directed=False)
    g.vs["name"] = ds.int_to_id
    return g
