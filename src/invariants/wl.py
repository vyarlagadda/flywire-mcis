"""Directed 1-Weisfeiler–Leman (WL) color refinement on a scipy.sparse CSR substrate.

This is the cheap **necessary** filter that shrinks the matching search for Engines B and C:

    WL is NECESSARY, NOT SUFFICIENT.
      same stable color  ⇒  the two nodes *may* correspond (never confirmed here)
      different color     ⇒  the two nodes provably *cannot* correspond
    Only the verifier (``src/verify``) ever confirms a match.

We implement directed 1-WL **directly on CSR adjacency** (per CLAUDE.md), not via networkx's
graph-level WL hash. The module imports only numpy + scipy — no graph library — so it stays the
lightweight invariant it is meant to be.

Cross-dataset comparability without a shared relabeling table
-------------------------------------------------------------
Colors are **content hashes**. The depth-0 color of a node is ``blake2b8(in_deg, out_deg)`` — a
globally meaningful invariant. Each refinement round re-hashes ``(prev_color, sorted out-neighbor
colors, sorted in-neighbor colors)`` with the in- and out-multisets kept **separate** so edge
direction matters. Because every new color is a deterministic function of globally-meaningful
predecessor hashes, two nodes in *different* connectomes receive the same color iff their depth-d
directed-WL rooted trees coincide — so colors are directly comparable across datasets.

Equal depth is required for comparability
-----------------------------------------
A node whose neighborhood stabilizes at depth 2 still gets *different hash values* at depth 5
(each round re-wraps the partition). So two datasets are comparable only when refined to the **same**
number of rounds. ``directed_wl`` therefore always runs exactly ``max_iterations`` rounds and never
early-stops; the round at which the partition stopped refining is recorded as ``stabilized_at_round``
for diagnostics only. The orchestrator runs every dataset with the same ``max_iterations``.

64-bit digests: with ~10^6 total nodes the collision probability is ~5e-8 — negligible.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

import numpy as np
from scipy.sparse import csr_matrix

from src.io.loader import Dataset

_DIGEST_BYTES = 8  # 64-bit content hashes stored as uint64
_SEP = b"\x1e"  # record separator between the out- and in-neighbor multisets


@dataclass
class WLResult:
    """Stable directed-WL coloring of one dataset.

    ``colors[i]`` is the uint64 content-hash color of the node whose compact int id is ``i`` (aligned
    1:1 with ``Dataset.int_to_id`` and the verifier's adjacency). Colors are comparable across
    datasets refined to the same ``depth``.
    """

    colors: np.ndarray  # uint64, length == num_nodes
    num_classes: int
    stabilized_at_round: int | None  # first round the partition stopped refining; None if still refining at depth
    rounds_run: int
    depth: int


def build_csr(ds: Dataset) -> tuple[csr_matrix, csr_matrix]:
    """Return ``(out_csr, in_csr)`` for *ds*.

    ``out_csr`` row ``u`` lists the out-neighbors of ``u`` (targets of u->v edges); ``in_csr`` row
    ``v`` lists the in-neighbors of ``v`` (sources). Pure scipy/numpy; no graph library.
    """
    n = ds.num_nodes
    m = ds.num_edges
    rows = np.empty(m, dtype=np.int64)
    cols = np.empty(m, dtype=np.int64)
    for k, (u, v) in enumerate(ds.edges):
        rows[k] = u
        cols[k] = v
    data = np.ones(m, dtype=np.int8)
    out_csr = csr_matrix((data, (rows, cols)), shape=(n, n))
    in_csr = out_csr.T.tocsr()
    # Sort indices so neighbor slices are contiguous and deterministic.
    out_csr.sort_indices()
    in_csr.sort_indices()
    return out_csr, in_csr


def _init_colors(out_csr: csr_matrix, in_csr: csr_matrix) -> np.ndarray:
    """Depth-0 colors: ``blake2b8(in_degree, out_degree)`` per node."""
    out_deg = np.diff(out_csr.indptr)
    in_deg = np.diff(in_csr.indptr)
    n = len(out_deg)
    colors = np.empty(n, dtype=np.uint64)
    for i in range(n):
        h = hashlib.blake2b(struct.pack("<QQ", int(in_deg[i]), int(out_deg[i])), digest_size=_DIGEST_BYTES)
        colors[i] = int.from_bytes(h.digest(), "little")
    return colors


def _refine_once(
    colors: np.ndarray, out_csr: csr_matrix, in_csr: csr_matrix
) -> np.ndarray:
    """One WL round: new color = hash(prev, sorted out-neighbor colors, sorted in-neighbor colors)."""
    n = len(colors)
    out_ind, out_ptr = out_csr.indices, out_csr.indptr
    in_ind, in_ptr = in_csr.indices, in_csr.indptr
    new_colors = np.empty(n, dtype=np.uint64)
    for i in range(n):
        out_ms = np.sort(colors[out_ind[out_ptr[i]:out_ptr[i + 1]]])
        in_ms = np.sort(colors[in_ind[in_ptr[i]:in_ptr[i + 1]]])
        h = hashlib.blake2b(digest_size=_DIGEST_BYTES)
        h.update(struct.pack("<Q", int(colors[i])))
        h.update(struct.pack("<I", out_ms.size))
        h.update(out_ms.tobytes())
        h.update(_SEP)
        h.update(struct.pack("<I", in_ms.size))
        h.update(in_ms.tobytes())
        new_colors[i] = int.from_bytes(h.digest(), "little")
    return new_colors


def directed_wl(ds: Dataset, max_iterations: int) -> WLResult:
    """Run directed 1-WL on *ds* for exactly ``max_iterations`` rounds (no early stop).

    ``max_iterations == 0`` returns the pure depth-0 (in-degree, out-degree) coloring. The full
    budget is always run so colors stay comparable with other datasets refined to the same depth;
    ``stabilized_at_round`` records when the partition stopped refining (diagnostic only).
    """
    out_csr, in_csr = build_csr(ds)
    colors = _init_colors(out_csr, in_csr)

    counts = [int(np.unique(colors).size)]
    stabilized_at_round: int | None = None
    for r in range(1, max_iterations + 1):
        colors = _refine_once(colors, out_csr, in_csr)
        counts.append(int(np.unique(colors).size))
        if stabilized_at_round is None and counts[r] == counts[r - 1]:
            # Partition unchanged from round r-1 to r => it was fully refined at r-1.
            stabilized_at_round = r - 1

    return WLResult(
        colors=colors,
        num_classes=counts[-1],
        stabilized_at_round=stabilized_at_round,
        rounds_run=max_iterations,
        depth=max_iterations,
    )
