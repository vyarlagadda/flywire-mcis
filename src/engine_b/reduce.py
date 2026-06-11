"""K-core peeling on the 3-graph candidate pool derived from a source certificate.

Pure dict/set adjacency — no igraph. Nodes are removed jointly: if any one of the three
datasets drops a node below the degree threshold, it is removed from all three simultaneously.
"""
from __future__ import annotations

from src.io.loader import Dataset


def kcore_reduce(
    datasets: list[Dataset],
    cert_rows: list[list[str]],
    col_names: list[str],
    kcore_min: int,
) -> tuple[list[str], list[str], list[str]]:
    """Return surviving string-ID lists for each dataset after iterative k-core peeling.

    A row is removed when its total degree (in + out, counting only edges to other surviving
    rows) falls below *kcore_min* in ANY of the three datasets.
    """
    assert len(datasets) == 3 and len(col_names) == 3

    cert_str: list[list[str]] = [[row[i] for row in cert_rows] for i in range(3)]
    alive = set(range(len(cert_rows)))

    def _build_adj(ds: Dataset, col_idx: int):
        id2row: dict[str, int] = {row[col_idx]: r for r, row in enumerate(cert_rows)}
        out_adj: dict[int, set[int]] = {r: set() for r in range(len(cert_rows))}
        in_adj: dict[int, set[int]] = {r: set() for r in range(len(cert_rows))}
        for u, v in ds.edges:
            u_str, v_str = ds.int_to_id[u], ds.int_to_id[v]
            if u_str in id2row and v_str in id2row:
                ur, vr = id2row[u_str], id2row[v_str]
                out_adj[ur].add(vr)
                in_adj[vr].add(ur)
        return out_adj, in_adj

    adjs = [_build_adj(ds, i) for i, ds in enumerate(datasets)]

    changed = True
    while changed:
        changed = False
        to_remove: set[int] = set()
        for r in alive:
            for out_adj, in_adj in adjs:
                deg = len(out_adj[r] & alive) + len(in_adj[r] & alive)
                if deg < kcore_min:
                    to_remove.add(r)
                    break
        if to_remove:
            alive -= to_remove
            changed = True

    return (
        [cert_str[0][r] for r in sorted(alive)],
        [cert_str[1][r] for r in sorted(alive)],
        [cert_str[2][r] for r in sorted(alive)],
    )
