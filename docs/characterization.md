# Dataset Characterization (Phase P1b)

Structural fingerprint of the five connectomes, computed with igraph from the cleaned simple
directed graphs (self-loops removed, parallel edges collapsed). Raw per-dataset numbers live in
`results/characterization/<DATASET>.json`; the machine-generated table is
`results/characterization/summary.md`. This document interprets them for the two open decisions:
**Engine A family/feasibility** and the **Engine C/B triple choice**.

> Reproducibility: seed `20260610`, igraph 1.0.0. The directed 3-node motif census was **sampled**
> on every dataset (all exceed the 1 M-edge dense threshold) via `motifs_randesu(size=3,
> cut_prob=[0.0, 0.0, 0.9])`. Sampled counts are an undercount of the explored branches, **not** a
> scaled total — so cross-dataset comparison uses the normalized `profile`, never the raw `counts`.

## Summary

| dataset | nodes | edges | density | recip. frac | mutual dyads | dir. degeneracy | recip. degeneracy | **recip-clique UB** | out-deg max / p99 | sampled |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|
| BANC | 112,885 | 2,676,592 | 2.1e-04 | 0.143 | 191,712 | 109 | 49 | **50** | 1,858 / 188 | yes |
| FAFB | 138,584 | 3,732,460 | 1.9e-04 | 0.166 | 310,090 | 107 | 47 | **48** | 6,523 / 170 | yes |
| MANC | 23,641 | 5,305,602 | 9.5e-03 | 0.304 | 806,074 | 335 | 64 | **65** | 4,752 / 1,060 | yes |
| MAOL | 51,668 | 6,484,673 | 2.4e-03 | 0.282 | 913,256 | 177 | 28 | **29** | 11,215 / 693 | yes |
| MCNS | 165,820 | 6,239,094 | 2.3e-04 | 0.157 | 488,924 | 130 | 50 | **51** | 7,570 / 227 | yes |

Two structural regimes are immediately visible:

- **Whole-CNS, sparse (BANC, FAFB, MCNS):** density ~2e-4, reciprocity 0.14–0.17, mean out-degree
  24–38. Edges scale with a large node count (113k–166k).
- **Region-scale, dense (MANC, MAOL):** density 10–40× higher, reciprocity ~0.3, mean out-degree
  125–224 on far fewer nodes (24k–52k). MANC (the VNC) is the densest by node.

All five have heavy-tailed degree distributions with strong hubs (out-degree max 1.8k–11k vs p99 of
170–1,060), so a **directed-star** circuit is structurally supported everywhere.

## Directed 3-node motif profile

Normalized over the 13 connected isoclasses. The dominant shapes (isoclass → shape):
`4` = 2-path `a→b→c`, `2` = converging `a→c←b`, `6` = diverging `a←b→c`, `9` = mutual-dyad+pendant
`a↔b, b→c`, `5` = mutual-dyad+pendant-in, `10` = reciprocal 2-path `a↔b↔c`, `11` = 3-cycle,
`15` = fully reciprocal triangle.

| dataset | 4 (chain) | 2 (conv) | 6 (div) | 9 (mut+out) | 5 (mut+in) | 10 (recip-path) | recip-heavy (10+15) |
|---|--:|--:|--:|--:|--:|--:|--:|
| BANC | 0.341 | 0.254 | 0.215 | 0.071 | 0.070 | 0.020 | 0.021 |
| FAFB | 0.294 | 0.251 | 0.183 | 0.096 | 0.099 | 0.059 | 0.060 |
| MANC | 0.267 | 0.173 | 0.191 | 0.141 | 0.125 | 0.033 | 0.035 |
| MAOL | 0.245 | 0.191 | 0.220 | 0.147 | 0.117 | 0.051 | 0.052 |
| MCNS | 0.318 | 0.263 | 0.185 | 0.083 | 0.086 | 0.043 | 0.044 |

Every dataset is **feed-forward-dominated**: the three acyclic triads (chain + converging +
diverging) account for ~73–81% of connected triads, and directed cycles (iso 11) are negligible
(<0.3%) everywhere. The denser VNC datasets (MANC, MAOL) shift mass toward the reciprocity-bearing
triads (iso 5, 9), consistent with their higher reciprocity fraction.

## Decision 1 — Engine A feasibility

Engine A solves each dataset independently and truncates to the min across the triple. The
`reciprocal_clique` family is bounded above by `reciprocal_degeneracy + 1` per dataset (a vertex of a
k-clique has reciprocal-coreness ≥ k−1):

- **CNS trio (BANC, FAFB, MCNS):** reciprocal-clique UBs 50 / 48 / 51 → ceiling **48** (FAFB).
- **Tentative trio (MANC, MAOL, MCNS):** UBs 65 / 29 / 51 → ceiling **29** (MAOL is the binding
  constraint — its reciprocal structure is the thinnest of all five despite high overall density).

So the CNS trio offers a materially higher reciprocal-clique ceiling (48 vs 29). These are upper
bounds, not achieved cliques — Engine A will report the actual max reciprocal clique per dataset —
but they set the feasible envelope. The large mutual-dyad counts (192k–913k) and strong hubs also
make **directed-star** and **complete-bipartite** families viable; given the universally
feed-forward profile, a star/biclique may yield a larger *and* more biologically natural recurrent
motif than a clique. Engine A should enumerate all three families and let the certified floor decide.

## Decision 2 — Engine C/B triple choice

The triple should maximize structural similarity (similar profiles ⇒ a large mutual induced
isomorphism is plausible). Ranking all 10 triples by total pairwise L1 distance between motif
profiles (lower = more similar):

| rank | triple | total L1 |
|---|---|--:|
| **1** | **(BANC, FAFB, MCNS)** | **0.389** |
| 2 | (FAFB, MAOL, MCNS) | 0.609 |
| 3 | (FAFB, MANC, MAOL) | 0.636 |
| … | … | … |
| 5 | (MANC, MAOL, MCNS) ← *tentative* | 0.734 |

**(BANC, FAFB, MCNS) is the clear winner** — its intra-triple distance (0.389) is far below the next
best (0.609), and the three pairwise distances are the smallest in the whole matrix (BANC–MCNS 0.121,
FAFB–MCNS 0.084, BANC–FAFB 0.185). They share the same regime: sparse whole-CNS graphs, near-equal
density (~2e-4), reciprocity (0.14–0.17), and feed-forward-dominated profiles. This is also the more
biologically coherent grouping (three whole-CNS reconstructions vs. mixing in the VNC-scale MANC/MAOL).

It also dominates on the Engine A axis (recip-clique ceiling 48 vs 29), so the two decisions agree.

### Recommendation

Revise the tentative `engine_c.chosen_triple` from **[MANC, MAOL, MCNS]** to **[BANC, FAFB, MCNS]**.
Per the build-order discipline this is left as an explicit, separate config change (not auto-applied
here) — to be confirmed against the Engine A frontier before Engine C runs. Open caveat: BANC and
FAFB are the two 18-digit string-ID datasets and the two largest by edge count, so Engine C's pools
and the exact induced-isomorphism check must stay string-ID-safe and memory-aware on them.
