# WL invariants — interpretation (Phase P3)

Directed 1-Weisfeiler–Leman (WL) color refinement is our cheap **necessary** filter for matching.

> **WL is NECESSARY, NOT SUFFICIENT.** Two nodes with the same stable color *may* correspond — never
> confirmed here. Two nodes with different colors provably *cannot* correspond. Only the verifier
> (`src/verify`) confirms a match.

Implementation: `src/invariants/wl.py` runs directed 1-WL directly on a scipy.sparse CSR substrate
(no graph library). Depth-0 color = `blake2b8(in_degree, out_degree)`; each round re-hashes
`(prev_color, sorted out-neighbor colors, sorted in-neighbor colors)`, in- and out-multisets kept
separate so direction matters. Colors are **content hashes**, so they are directly comparable across
datasets refined to the **same depth** — no shared relabeling table.

## Headline finding: the candidate pool is strongly depth-sensitive

The cross-dataset candidate pool = WL color classes present in ≥ `min_datasets_per_color_class` (=3)
datasets. Its size depends sharply on the refinement depth, because deeper rooted-tree signatures are
nearly unique fingerprints:

| WL depth | classes in ≥3 datasets | per-dataset #classes (BANC/FAFB/MANC/MAOL/MCNS) |
|---:|---:|---|
| 0 (in/out degree only) | **11,211** | 13,061 / 14,056 / 20,676 / 25,791 / 21,280 |
| 1 | 16 | 112,107 / 135,208 / 23,640 / 51,517 / 164,288 |
| 2 | 2 | 112,574 / 135,313 / 23,640 / 51,546 / 164,332 |
| 3 | 2 | 112,574 / 135,318 / 23,640 / 51,549 / 164,332 |
| 5 (configured `wl_max_iterations`) | 2 | 112,574 / 135,318 / 23,640 / 51,549 / 164,332 |

At depth ≥2 essentially every node is its own class (~99.7% singletons; BANC class-size histogram:
112,411 singletons of 112,885 nodes), and the ≥3-dataset pool collapses to **2 classes** — both
spanning (BANC, FAFB, MAOL), not even the chosen triple (BANC, FAFB, MCNS). Refinement has stabilized
by depth 2–3 on every dataset (`stabilized_at_round` 1–3).

### Why, and what it means downstream

A node's depth-d color encodes its entire directed neighborhood tree out to radius d. In graphs this
large and irregular, those trees are almost always unique, so **deep WL is a near-perfect separator**
— excellent as a *pairwise rejection* test (different deep colors ⇒ no match), but useless as a
*seed generator* (exact deep-color equality across datasets almost never holds).

The committed `candidate_pool.json` is the faithful depth-5 (`wl_max_iterations`) intersection — a
strict, certified-impossible-pruned pool. For **seeding Engine C** the useful signal lives at shallow
depth: depth-0 (degree buckets) yields ~11k cross-triple classes; depth-1 already collapses to 16.

**Recommendation (for the Engine C phase, not applied now):** seed from shallow WL — degree buckets
(depth 0) or depth-1 colors — and use the deep-WL color only as the inline *necessary* pruning test
when extending a candidate match. Consider exposing the seeding depth separately from the
rejection-filter depth rather than a single `wl_max_iterations`.

## Optional GDV

`src/invariants/gdv.py` is flag-gated on `invariants.gdv_enabled` (now `false`, matching "off by
default — no orca binary installed"). When disabled it is a no-op; when enabled but the orca binary is
absent it warns and returns `None` — never crashes the WL pipeline. GDV is deferred until an engine
actually needs richer seeds.

## Artifacts (`results/invariants/`)

- `<DATASET>_colors.csv` — `neuron_id,wl_color` (16-hex), one row per node, indices aligned with the
  loader's compact ints.
- `<DATASET>.json` — counts, WL depth/rounds/classes/`stabilized_at_round`, class-size histogram.
- `candidate_pool.json` — kept color classes (depth-5) with per-dataset member ids + the
  necessary-not-sufficient `note`.
- `summary.md`, `config.snapshot.yaml`.
