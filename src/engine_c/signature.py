"""Incremental connection-signature substrate for Engine C's greedy growth.

The crux of seed-and-extend across three graphs is deciding, in O(boundary) per step, whether a
candidate triple (a, b, c) can be appended while keeping the partial map an induced isomorphism.

Connection signature
---------------------
Relative to a mapping of K matched triples, a node ``x`` has a 2K-bit **signature**: for each
member row ``m``, bit ``2*m`` is set iff edge ``x -> member_m`` exists (an *out*-bit), and bit
``2*m+1`` is set iff ``member_m -> x`` exists (an *in*-bit). The signature is stored as a Python
big-int bitmask.

Why this is exactly the induced-iso growth test
-----------------------------------------------
Appending ``(a, b, c)`` at row index K creates only the new ordered pairs ``(K, m)`` and ``(m, K)``
for ``m < K``; all prior pairs are untouched. The map stays an induced isomorphism iff for every
prior ``m`` the in/out edge pattern of a, b, c to member ``m`` agrees across all three graphs
(all-or-none) — i.e. iff ``sig_BANC(a) == sig_FAFB(b) == sig_MCNS(c)`` as 2K-bit integers. This is
precisely the verifier's check-3 semantics, restricted to the new row.

Append-only incrementality
---------------------------
The greedy never backtracks within a seed, so members are only ever *appended*. A stored signature
therefore stays valid as K grows — we only set the two new bits for member ``m`` on the nodes
adjacent to the newly added member. ``add_member`` is O(deg(member)), independent of K. Nodes never
adjacent to any member keep an implicit all-zero signature and are never tracked (they are
disconnected from the mapping and so never admitted under weak connectivity).

This module is pure Python (dict/set adjacency from ``src.io``) — no graph library.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.io.loader import Dataset, build_adjacency


@dataclass
class GraphState:
    """Per-graph growth state: adjacency, the current mapped nodes (in row order), and the lazy
    boundary signatures.

    ``mapped[m]`` is the compact-int node chosen for row ``m``. ``sig[x]`` is the live 2K-bit
    signature of boundary node ``x``; only boundary nodes (those with >= 1 incident edge to a mapped
    node) are tracked. ``boundary`` is exactly ``sig``'s key set minus the mapped nodes.
    """

    ds: Dataset
    out: dict[int, set[int]]
    inn: dict[int, set[int]]
    mapped: list[int] = field(default_factory=list)
    mapped_set: set[int] = field(default_factory=set)
    sig: dict[int, int] = field(default_factory=dict)
    boundary: set[int] = field(default_factory=set)


def new_graph_state(ds: Dataset) -> GraphState:
    """Build a fresh :class:`GraphState` from *ds* (adjacency computed once, O(E))."""
    out, inn = build_adjacency(ds)
    return GraphState(ds=ds, out=out, inn=inn)


def fresh_state(ds: Dataset, out: dict[int, set[int]], inn: dict[int, set[int]]) -> GraphState:
    """A fresh empty-mapping :class:`GraphState` reusing precomputed adjacency.

    Adjacency is immutable across growth, so building it once per dataset and wrapping it in a fresh
    state per seed avoids re-running the O(E) ``build_adjacency`` for all ``num_seeds`` seeds.
    """
    return GraphState(ds=ds, out=out, inn=inn)


def add_member(gs: GraphState, w: int) -> None:
    """Append node ``w`` as the next mapped row and update boundary signatures in O(deg(w)).

    For new member index ``m``: every in-neighbor ``x`` of ``w`` (edge ``x -> w``) gains the out-bit
    ``2*m``; every out-neighbor ``x`` of ``w`` (edge ``w -> x``) gains the in-bit ``2*m+1``. Mapped
    nodes are skipped (self/intra-map edges are recorded by the verifier's K×K scan, not by the
    boundary). ``w`` is removed from the boundary as it is promoted to a member.
    """
    m = len(gs.mapped)
    gs.mapped.append(w)
    gs.mapped_set.add(w)
    out_bit = 1 << (2 * m)
    in_bit = 1 << (2 * m + 1)

    for x in gs.inn[w]:           # x -> w  => x has an out-edge to member m
        if x in gs.mapped_set:
            continue
        gs.sig[x] = gs.sig.get(x, 0) | out_bit
        gs.boundary.add(x)
    for x in gs.out[w]:           # w -> x  => member m -> x => x has an in-edge from member m
        if x in gs.mapped_set:
            continue
        gs.sig[x] = gs.sig.get(x, 0) | in_bit
        gs.boundary.add(x)

    gs.boundary.discard(w)
    gs.sig.pop(w, None)


def group_by_key(
    gs: GraphState, shallow_colors, boundary_cap: int | None = None, color_key: bool = True
) -> dict[tuple[int, int], list[int]]:
    """Group boundary nodes by their step key.

    With ``color_key=True`` the key is ``(signature, shallow_wl_color)``: it fuses the *sufficient*
    induced-iso constraint (identical signature) with the *necessary* shallow-WL color filter. The
    color filter is a strong pruner but, across three genuinely non-isomorphic connectomes, can block
    every cold-seed extension; with ``color_key=False`` the key is the signature alone — still
    correctness-preserving (signature equality is exactly the induced-iso growth condition) and far
    more permissive — and shallow color is demoted to an advisory tie-break in the score.

    ``boundary_cap`` bounds per-step work on hub-heavy graphs by keeping the smallest-id nodes.
    """
    nodes = gs.boundary
    if boundary_cap is not None and len(nodes) > boundary_cap:
        nodes = sorted(nodes)[:boundary_cap]
    groups: dict[tuple[int, int], list[int]] = {}
    for x in nodes:
        key = (gs.sig[x], int(shallow_colors[x]) if color_key else 0)
        groups.setdefault(key, []).append(x)
    return groups
