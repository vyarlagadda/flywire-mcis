# Phase Log

---

## Phase P0 — Assumptions ledger (2026-06-10)

### What this phase did
Read both challenge briefs (`docs/brief/Qualification Challenge.pdf`, 2026-06-02; and
`docs/brief/Qualification Challenge Extension.pdf`, 2026-06-08) and wrote a self-contained, graded
assumptions ledger at `docs/assumptions.md`: a precise restatement of the problem plus an explicit
table of every assumption the brief leaves open, each with the decision taken and one sentence of
justification.

### Key decisions
- **Graph model (A1–A6):** directed, unweighted (weights ignored per brief), simple — self-loops
  removed, parallel edges collapsed. A neuron is "present" in a dataset iff it is an endpoint of ≥1
  post-cleanup edge (only edge lists are provided; degree-0 nodes can't be in a weakly connected
  circuit anyway, so the exclusion is lossless).
- **Identifiers (A7–A8):** all IDs handled as strings (BANC/FAFB 18-digit root IDs overflow int64);
  IDs are not shared across datasets → matching is purely structural.
- **Correspondence (A9–A12):** "identical" = directed-graph isomorphism under the row alignment (the
  CSV rows *are* the vertex bijection); weak connectivity checked on the undirected projection (per
  the 2026-06-08 extension); target exactly the best **triple** of datasets (3-column format can't
  encode a 4-/5-way match); no shared brain region required (extension).
- **Degeneracy / optimality (A13–A14):** require N ≥ 2 non-degenerate; report N as a verified lower
  bound + certificate, never a proven global optimum (problem is NP-hard).
- **Verification (A15):** the independent verifier (`src/verify`) is the sole ground truth.

### Outputs produced
- `docs/assumptions.md` (15-entry ledger + problem restatement + out-of-scope section)

### Open questions
- A11: `config.yaml`'s `chosen_triple: [MANC, MAOL, MCNS]` is still tentative — confirm from the
  Engine A frontier.
- A5: node-presence-via-edge-endpoint assumes no isolated-node semantics are needed downstream;
  revisit if any phase expects degree-0 neurons.
- Next phase: build the verifier test-first (`src/verify/check.py`) before any engine emits a
  candidate — currently `network.csv` is an empty stub and `src.verify.check` does not yet exist.

---

## Phase S0 — Scaffolding (2026-06-10)

### What this phase did
Set up the complete project skeleton so every subsequent phase can write code rather than infrastructure.

- Created `requirements.txt` with all declared deps: `python-igraph`, `scipy`, `numpy`, `pandas`, `pyyaml`, `rustworkx`, `networkx`, `pytest`.
- Provisioned `.venv` and verified all packages import cleanly.
- Created `config.yaml` at repo root with full parameter block: global seed, data paths, invariant knobs (WL/GDV), and per-engine budgets/options for engines A, B, and C.
- Created `src/config.py`: `yaml.safe_load`-based loader with `get()`, `seed()`, `set_seed()` runtime override, and `snapshot(result_dir)` helper that copies `config.yaml` → `result_dir/config.snapshot.yaml`.
- Added empty `__init__.py` stubs in all nine `src/` subpackages: `src`, `io`, `verify`, `engine_a`, `engine_b`, `engine_c`, `invariants`, `bounds`, `characterize`.
- Created placeholder deliverables: `README.md`, `science.md`, `network.csv`, `docs/assumptions.md`, `docs/methodology.md`.
- Added `.claude/` command stubs (`phase-wrap`, `recap`, `verify`) and `.gitignore`.
- Placed raw edge-list CSVs in `data/raw/` (gitignored) and result subdirs under `results/`.

### Key decisions
- Neuron IDs stored as **strings** throughout (BANC/FAFB use 18-digit root IDs that overflow int64).
- `data/raw/` is gitignored — large binary CSVs stay local; each developer re-downloads.
- All tunable parameters live in `config.yaml`; nothing is hard-coded in source.
- `src/config.py` caches after first load; `set_seed()` allows per-run override without touching the file.

### Outputs produced
- `requirements.txt`
- `config.yaml`
- `src/config.py`
- `src/*/___init__.py` × 9
- `docs/phase-log.md` (this file)
- Placeholder: `README.md`, `science.md`, `network.csv`, `docs/assumptions.md`, `docs/methodology.md`

### Open questions
- Engine A: which family (reciprocal clique vs. directed star vs. complete bipartite) will yield the largest certified floor? — answered in Phase 1.
- `chosen_triple` in `config.yaml` is tentative (`[MANC, MAOL, MCNS]`); will be set after reviewing Engine A frontier.
- ORCA/GDV integration: confirm binary availability on target machine before enabling `gdv_enabled`.

---

## Phase P1 — Data IO (`src/io`) (2026-06-10)

### What this phase did
Built the streaming data-IO layer that loads each connectome edge list once and exposes two
representations from the **same** load: a pure dict/set adjacency for the verifier and igraph graphs
for the engines. Test-first: 13 tests written red, then implemented to green.

### Key decisions (and why)
- **Dependency split enforces the hard rule.** `src/io/loader.py` is pure Python (no igraph) and
  holds the `Dataset` core + `build_adjacency`; `src/io/graphs.py` holds the igraph builders.
  `src/io/__init__.py` re-exports **only** loader symbols, so `import src.io` (the verifier's path)
  never imports igraph — guarded by a subprocess test. Engines import the builders explicitly via
  `from src.io.graphs import ...` (chosen over a lazy `__getattr__` for an obvious, magic-free
  boundary).
- **`Dataset` is the single library-agnostic core**: `int_to_id` (reverse map), `id_to_int`,
  `edges` (cleaned directed). Both representations derive from it, so igraph vertex indices align
  1:1 with the compact ints used by the verifier's adjacency.
- **IDs are strings throughout**, interned to compact ints; 18-digit root IDs round-trip exactly
  (test asserts no int coercion).
- **Streaming via `csv.reader` over the file handle** — never `read()`/`readlines()` — so 100 MB
  inputs stay cheap. Header line skipped; blank lines ignored.
- **Cleaning honored from config flags**: `drop_self_loops` (skip u==v), `collapse_parallel_edges`
  (set dedup when True; list keeps multiplicity when False — a safety valve, default stays True).
- **Reciprocal graph** (Engine A): undirected mutual-edges-only graph keeping the full node set so
  indices still align; non-reciprocal nodes are simply isolated.
- **Node set == edge endpoints** (assumption A5) — no degree-0 vertices by construction.

### Outputs produced
- `src/io/loader.py` — `Dataset`, `load_edge_list`, `build_adjacency`, `load_dataset`, `load_all`
- `src/io/graphs.py` — `to_igraph`, `to_reciprocal_igraph`
- `src/io/__init__.py` — pure re-exports
- `tests/test_io.py` (13 tests) + `tests/__init__.py`

### Open questions
- Real-data sanity-load **confirmed** (2026-06-11): `load_dataset("MAOL")` → 51,668 nodes /
  6,484,673 edges in 2.6 s; reciprocal graph 913,256 mutual edges; IDs round-trip as strings;
  `import src.io` stays igraph-free. Resolved.
- `load_dataset`/`load_all` resolve `data.dir` relative to CWD; if invoked from outside repo root,
  paths may need to be anchored to repo root — revisit if any engine runs from a result dir.

---

## Phase P1b — Characterization (`src/characterize`) (2026-06-11)

### What this phase did
Built the igraph-based structural-fingerprint layer and ran it on all five connectomes, turning the
tentative triple/family choices into evidence-based ones. Test-first: 10 tests written red, then
implemented to green (full suite 23 passing).

- `src/characterize/metrics.py` — `compute_metrics(ds, cfg)` returns a JSON-serializable dict:
  node/edge counts + density; in/out/total degree summaries (min/max/mean/median/std + p50/p90/p99)
  with top-k degree tails recorded by **string** id; reciprocity fraction + dyad census; directed
  total-degree degeneracy and the **reciprocal-graph degeneracy** with `reciprocal_clique_upper_bound`
  (= degeneracy+1, the Engine A headline); and a directed 3-node motif census via `motifs_randesu`.
- `src/characterize/run.py` — CLI (`python -m src.characterize.run [--dataset NAME | --all]
  [--out ...]`); writes `<DATASET>.json` ×5, `config.snapshot.yaml`, and a generated `summary.md`.
- Added a `characterize:` block to `config.yaml` (tail-k, quantiles, motif size, dense threshold,
  cut_prob) — no tunables hard-coded.

### Key decisions (and why)
- **Motif census sampled on every dataset** (all > 1 M edges): `motifs_randesu(size=3,
  cut_prob=[0.0, 0.0, 0.9])`, igraph RNG seeded from config. Sampled counts are an undercount of the
  explored branches, **not** a scaled total — so cross-dataset comparison uses the normalized
  `profile`, not raw `counts`. The `sampled` flag + `cut_prob` are recorded in each JSON.
- **NaN isoclasses → `null`**; JSON written with `allow_nan=False` so output is strict-valid.
- **Reciprocal degeneracy is the Engine A feasibility lever** — computed on `to_reciprocal_igraph`,
  not the directed graph.

### Outputs produced
- `src/characterize/{metrics.py, run.py, __init__.py}`, `tests/test_characterize.py` (10 tests)
- `results/characterization/{BANC,FAFB,MANC,MAOL,MCNS}.json` + `summary.md` + `config.snapshot.yaml`
- `docs/characterization.md` (interpretation), `characterize:` block in `config.yaml`

### Findings → decisions
- **Two regimes:** sparse whole-CNS (BANC/FAFB/MCNS, density ~2e-4, reciprocity 0.14–0.17) vs dense
  region-scale (MANC/MAOL, density 10–40×, reciprocity ~0.3). All are feed-forward-dominated
  (acyclic triads ~73–81%; directed 3-cycles <0.3%). Strong hubs everywhere (out-deg max 1.8k–11k).
- **Engine A:** reciprocal-clique ceiling (min UB over triple) = **48** for (BANC,FAFB,MCNS) vs only
  **29** for the tentative (MANC,MAOL,MCNS) — MAOL's reciprocal structure is the binding constraint.
  Star/biclique families also viable (large mutual-dyad counts + hubs) and may beat a clique.
- **Triple choice (resolves A11):** by motif-profile L1 similarity, **(BANC, FAFB, MCNS)** is the
  clear winner (total intra-distance 0.389 vs next-best 0.609; tentative triple ranks 5th at 0.734).
  Both axes agree. **Recommend revising `engine_c.chosen_triple` → [BANC, FAFB, MCNS]**.

### Open questions
- `engine_c.chosen_triple` revision to `[BANC, FAFB, MCNS]` is **recommended but not yet applied** —
  left as an explicit decision to confirm against the Engine A frontier before Engine C runs.
- BANC/FAFB are the two 18-digit string-ID datasets and the two largest by edges; Engine C pools and
  the exact induced-iso check must stay string-safe and memory-aware on them.
- Motif `cut_prob` chosen lightly ([0,0,0.9]); MANC/MAOL motif census ran 3–6 min. Acceptable for a
  one-off characterization; revisit if re-run cost matters.

---

## Phase P2 — Verifier / oracle (`src/verify`) (2026-06-11)

### What this phase did
Built the independent grading oracle — the ground truth (A15) every candidate must pass before it is
trusted. It mirrors FlyWire's grading: directed induced isomorphism under the row alignment plus weak
connectivity, using plain dict/set adjacency and **no graph library**. Test-first: 18 tests written
red, then implemented to green (full suite now 41 passing). Tagged `v0.1-verifier`.

- `src/verify/check.py` — `verify_candidate(columns, rows, datasets) -> Report` (pure engine),
  `read_candidate(path)`, `verify_file(path, cfg)` (header → config resolution → load via `src.io`),
  and a `main()` CLI (`python -m src.verify.check --candidate … [--config …] [--json]`,
  exit 0=PASS / 1=FAIL / 2=usage). `Report`/`CheckResult` are frozen dataclasses with `.format()`
  (human) and `.to_dict()` (JSON).
- Four checks, run **in order, short-circuiting at the first failure**, each with a precise reason:
  (1) structural — exactly 3 distinct known datasets, **N ≥ 2** rows, 3 non-empty cells/row, no
  duplicate id within a column; (2) existence — every id is a node in its dataset; (3) induced
  isomorphism — for every ordered row pair (i,j), edge i→j present in all three or none (fail-fast,
  names the offending pair + which datasets disagree); (4) weak connectivity — hand-rolled union-find
  over the undirected projection, names the components on failure. A structure label
  (clique / star / complete_bipartite / general) is detected once check 3 passes (informational only).

### Key decisions (and why)
- **No graph library — enforced, not just intended.** `check.py` imports only stdlib + `src.io`
  (loader symbols, which never pull igraph). A subprocess test asserts neither `igraph` nor
  `networkx` is in `sys.modules` after `import src.verify.check` (mirrors the P1 io guard). This is
  the hard rule that keeps the oracle independent of every engine.
- **Edge-presence primitive = `(u, v) in ds.edges` set membership** (coerce a list to a set once),
  not per-node adjacency. O(1) lookups with zero per-node allocation, so the O(N²) pairwise checks
  stay cheap on the 6 M-edge BANC/FAFB graphs (building full `build_adjacency` dicts there would be
  O(E) memory for no benefit, since we only ever probe the N matched nodes).
- **Row floor = N ≥ 2 as a hard check-1 failure** (A13), confirmed this session — chosen over the
  spec's looser "≥1 row". A single neuron / edgeless set is a vacuous circuit; rejecting it
  structurally (rather than flagging it) keeps the verifier faithful to the "no degenerate results"
  grading intent. Weak connectivity then guarantees ≥1 edge for any N ≥ 2.
- **Iso-check fail-fast.** The first offending ordered pair is reported (the brief/skill ask for "the
  offending pair"); enumerating all violations is a trivial future flag, deliberately deferred.
- **`verify_file` never loads the big graphs on a malformed header.** Datasets are loaded only after
  the header passes a cheap "3 distinct names" gate; unknown/extra/duplicate headers are reported by
  check 1 without touching `data/raw`.
- **CLI smoke confirms the placeholder is rejected:** `python -m src.verify.check` on the empty
  `network.csv` stub exits 1 with `expected 3 columns, got 0` — the oracle refuses the stub, as it
  must until an engine emits a real candidate.

### Outputs produced
- `src/verify/check.py` (verifier + CLI)
- `tests/test_verify.py` (18 tests: the 5 spec'd cases + boundary/ordering/structure/CLI/import-guard)
- `docs/phase-log.md` (this entry); git tag `v0.1-verifier`

### Open questions
- `verify_file` / `load_dataset` resolve `data.dir` relative to CWD (inherited P1 caveat); the CLI is
  expected to run from repo root. Revisit if any engine invokes the verifier from a result dir.
- Real-data end-to-end (loading the actual ~6 M-edge graphs through `verify_file`) is exercised only
  via toy datasets so far; the first genuine engine candidate will be the real load test.
- Structure detection treats N==2 (a lone directed/reciprocal edge) as `general`; not exercised and
  immaterial to pass/fail, but worth a note if a 2-node match is ever reported.

---

## Phase P3 — WL pruning + optional GDV (`src/invariants`) (2026-06-11)

### What this phase did
Built the cheap **necessary** match filter: directed 1-Weisfeiler–Leman color refinement implemented
directly on a scipy.sparse CSR substrate (no graph library — *not* networkx's graph-level WL hash),
plus a cross-dataset candidate-pool builder and a flag-gated optional ORCA/GDV wrapper. Ran WL on all
five connectomes and committed the artifacts. Test-first: 12 tests written red, then to green (full
suite now 53 passing).

- `src/invariants/wl.py` — `build_csr(ds)` (out/in CSR from `Dataset.edges`), `directed_wl(ds,
  max_iterations) -> WLResult`. Depth-0 color = `blake2b8(in_deg, out_deg)`; each round re-hashes
  `(prev_color, sorted out-neighbor colors, sorted in-neighbor colors)` — in/out multisets kept
  **separate** so direction matters. Colors are 64-bit **content hashes**.
- `src/invariants/pool.py` — `color_classes(results, datasets, min_datasets) -> [ColorClass]`: group
  nodes by color, keep classes present in ≥ `min_datasets_per_color_class` datasets, map compact ints
  back to original **string** ids.
- `src/invariants/gdv.py` — `gdv_available` / `gdv_signatures`, behind `invariants.gdv_enabled`;
  graceful skip (warn + `None`, never crash) when the orca binary is absent. Clearly optional.
- `src/invariants/run.py` — CLI mirroring `characterize/run.py`; writes per-dataset colors CSV +
  JSON, `candidate_pool.json`, `summary.md`, `config.snapshot.yaml`.

### Key decisions (and why)
- **Content-hash colors → cross-dataset comparability with no shared relabeling table.** Because each
  color is a deterministic hash of globally-meaningful predecessor hashes (rooted in `(in_deg,
  out_deg)`), two nodes in *different* connectomes get the same color iff their depth-d directed-WL
  rooted trees coincide. Local integer compression would not be comparable across datasets.
- **Equal depth is required for comparability, so `directed_wl` always runs the full
  `max_iterations` rounds — no early stop.** A node stable at depth 2 still hashes to *different
  values* at depth 5 (each round re-wraps the partition); comparing two datasets demands the same
  depth. The "or until stable" intent is honored as a recorded diagnostic, `stabilized_at_round`
  (first round the class count stopped growing), not as an early cutoff.
- **scipy CSR substrate, no graph library** (per CLAUDE.md): a subprocess test asserts
  `import src.invariants.wl` pulls in no networkx. WL stays the lightweight invariant it is meant to be.
- **64-bit digests:** collision probability across ~10⁶ total nodes ≈ 5e-8 — negligible; noted in code.
- **NECESSARY-not-sufficient** stated in module docstrings, the `candidate_pool.json` `note`, and the
  required toy test: a directed 6-cycle vs two directed 3-cycles — every vertex is in-deg/out-deg 1, so
  WL never refines; a vertex from each lands in the **same** color (WL must not wrongly separate
  WL-equivalent-but-non-isomorphic vertices).
- **GDV scoped as a guarded graceful-skip wrapper** (resolved with user): no orca binary installed, so
  `gdv_enabled` flipped `true → false` in config (matches its own "off by default" comment). Real GDV
  computation deferred until an engine consumes it.

### Outputs produced
- `src/invariants/{wl.py, pool.py, gdv.py, run.py, __init__.py}`; `tests/test_invariants.py` (12 tests)
- `results/invariants/{BANC,FAFB,MANC,MAOL,MCNS}_colors.csv` + `*.json`, `candidate_pool.json`,
  `summary.md`, `config.snapshot.yaml`
- `docs/invariants.md` (interpretation + depth-sweep table); `config.yaml` `gdv_enabled → false`

### Findings → decisions
- **The candidate pool is strongly depth-sensitive.** Pool size (classes in ≥3 datasets): depth 0 =
  **11,211**; depth 1 = 16; depth ≥2 = **2**. Deep WL is a near-perfect *separator* (~99.7% singleton
  classes by depth 2; BANC: 112,411 singletons / 112,885 nodes), so exact deep-color equality across
  datasets almost never holds. The committed depth-5 `candidate_pool.json` therefore has just 2 classes
  (both spanning BANC/FAFB/MAOL, not the chosen triple).
- **Implication for Engine C seeding:** deep WL = a great inline *pairwise rejection* test, a poor
  *seed generator*. Seed from **shallow** WL (degree buckets at depth 0, or depth-1 colors) and use
  deep-WL color only as the necessary pruning check during extension.

### Open questions
- **Recommended (not applied): split the seeding depth from the rejection-filter depth** rather than a
  single `invariants.wl_max_iterations`. The depth-5 pool is faithful but near-empty for seeding; Engine
  C should consume shallow-depth (0–1) color classes for seeds. Decide when Engine C is built.
- WL refinement is a Python per-node loop (numpy slice + sort + blake2b); ~2–4 s/dataset at depth 5 here
  (largest: MCNS 6.2 M edges, 165 k nodes). Fine for one-off; revisit if depth or re-runs grow.
- ORCA/GDV remains unimplemented behind the flag; wire it only if Engine C needs richer-than-WL seeds.

---

## Phase P4 — Engine A canonical (`src/engine_a`) (2026-06-11)

### What this phase did
Built Engine A — the **certified FLOOR** — and produced the first verified candidates. Three
correct-by-construction families (equal-size instances are automatically isomorphic) solved per
dataset, then a frontier assembled every (family × triple) and confirmed each through the verifier.
Test-first: 10 tests written red, then to green (full suite now **63 passing**). The headline
submission `network.csv` is now a **verified reciprocal 38-clique**. Tagged `v1.0-engineA-frontier`.

- `src/engine_a/clique.py` — reciprocal clique on `to_reciprocal_igraph`: degeneracy+1 UB from
  `coreness`; seeded randomized-greedy floor; exact `largest_cliques` on the coreness≥floor k-core in
  a `spawn` worker bounded by `clique.time_budget_s`.
- `src/engine_a/star.py` — pure out-/in-star (both orientations); leaves = an independent set of the
  hub's *pure* neighbours via greedy + bounded O(E) (2,1)-swap; per-orientation time budget; hubs
  scanned by descending degree with a `degree+1 ≤ best` break.
- `src/engine_a/biclique.py` — pure directed K_{a,b} (gated on `biclique.enabled`); A-candidates =
  `(∩_{b∈B} in[b]) − (∪_{b∈B} out[b])`; heuristic LB, time-budgeted.
- `src/engine_a/frontier.py` — aligns three instances at the common size (clique: first N; star:
  hub+leaves, shared orientation; biclique: min (a,b)), calls `verify_candidate`, keeps only PASS.
- `src/engine_a/run.py` — CLI; per-dataset JSON, `summary.md`, `frontier.csv`, `certificates/`.

### Key decisions (and why)
- **Correct-by-construction + verifier-confirmed.** Each family guarantees induced isomorphism and
  weak connectivity by shape; truncation to the min size stays in-family; every emitted certificate is
  still independently checked by `src.verify`. N is a verified LOWER bound; the clique degeneracy+1 is
  reported as a separate UPPER bound, never claimed as achieved.
- **Greedy clique uses a precomputed static (coreness) key**, not a per-step `len(nbrs[v] & cand)`
  rescan — the latter was O(seeds·k·|cand|·deg) and spun for >6 min on dense MANC; the fix makes each
  step O(|cand|) and the whole clique pass ≤ 5.4 s on every dataset.
- **Exact clique in a `spawn` worker joined with the time budget** (terminated on overrun → greedy
  floor) — a hard wall-clock bound around igraph's C call without threading hazards.
- **Pure-orientation stars/bicliques** so equal-size instances are *directed*-isomorphic (out- and
  in-stars are NOT isomorphic to each other); the frontier therefore requires a shared orientation.
- **Bounded (2,1)-swap** for the star IS: single O(E) tight-vertex pass per round, capped rounds,
  skipped above `star.swap_max_nodes` (greedy is near-optimal on large sparse leaf sets). Star went
  from a >7-min hang to ≤ 102 s/dataset.
- **config:** `clique`/`biclique` `time_budget_s` 3600 → **300** (exact is a bonus over the greedy
  floor); added `star.time_budget_s` and `star.swap_max_nodes`. All budgets stay in config.

### Outputs produced
- `src/engine_a/{clique,star,biclique,frontier,run}.py`; `tests/test_engine_a.py` (10 tests)
- `results/engine_a/{clique,star,biclique}/*.json`, `frontier.csv`, `summary.md`,
  `config.snapshot.yaml`, `certificates/*.csv` (**24 verifier-PASS** certificates)
- `network.csv` ← reciprocal **38-clique** on (BANC, FAFB, MCNS), CLI-verified PASS
- `config.yaml` engine_a budgets; git tag `v1.0-engineA-frontier`

### Findings → results (best VERIFIED N per family)
- **reciprocal_clique: N = 38** on **BANC+FAFB+MCNS** (10/10 triples pass). Per-dataset cliques (UB):
  BANC 38 (50), FAFB 38 (48), MANC 28 (65), MAOL 12 (29), MCNS 41 (51) — all exact, ≤ 5.4 s. MAOL's
  12 is the binding outlier (why MAOL triples cap at 12).
- **directed_star: N = 1877** on FAFB+MAOL+MCNS (only **4/10** — BANC's best is an in-star while the
  others are out-stars → 6 orientation-mismatch skips). Per-dataset: BANC 1107 (in), FAFB 2062, MANC
  314, MAOL 1877, MCNS 2480. **Large but DEGENERATE** (a hub + thousands of mutually-disconnected
  leaves) → not the submission.
- **complete_bipartite: N = 15** on BANC+FAFB+MCNS (10/10). Per-dataset: BANC 15, FAFB 112, MANC 23,
  MAOL 14, MCNS 77.
- **Submission = the 38-clique** (a dense, biologically meaningful recurrent circuit) per the
  weight-meaningful-over-degenerate rule; the star=1877 is recorded in the frontier, not submitted.

### Most promising triples for Engine C / B
- **BANC + FAFB + MCNS** — clique floor **38**, min clique UB **48** (headroom of 10), the three
  whole-CNS sparse graphs, and the P1b motif-similarity winner. Engine C should seed-and-extend from
  the verified 38-clique toward a larger *non-degenerate connected* circuit; Engine B can attempt
  exact MCS on WL+k-core-reduced BANC/FAFB/MCNS around it. This empirically confirms the P1b
  recommendation to set `engine_c.chosen_triple → [BANC, FAFB, MCNS]` (still not applied).

### Open questions
- **Star frontier coverage 4/10**: report BOTH orientations per dataset so the frontier can pick the
  best COMMON orientation (recovers the 6 BANC in/out mismatches). Deferred — star is degenerate and
  not the headline.
- Clique exact never hit the 300 s budget (≤ 5.4 s everywhere); `restarts`/budget could rise if
  pushing N, but the degeneracy gap (38 vs UB 48) suggests Engine C/B, not more clique search.
- Biclique UB is left at 0 (no cheap non-trivial bound for max biclique); LB only, as intended.

---

## Phase P5 — Engine C greedy seed-and-extend (`src/engine_c`) (2026-06-11)

### What this phase did
Built Engine C — the **workhorse**: a connectivity-constrained greedy seed-and-extend on the chosen
triple **BANC + FAFB + MCNS**, with the EXACT induced-directed-isomorphism check inline at every
expansion step. Test-first: failing tests first, then to green (full suite now **76 passing**). Tagged
`v1.5-engineC`.

- `src/engine_c/signature.py` — the incremental **connection-signature** substrate. A node's signature
  vs a K-row mapping is a 2K-bit big-int (bit `2m` = node→member_m, bit `2m+1` = member_m→node);
  `add_member` sets the two new bits only on the added member's neighbors (O(deg), append-only). A
  candidate triple is induced-iso-admissible iff `sig_BANC(a) == sig_FAFB(b) == sig_MCNS(c)`. Guarded
  by `test_incremental_equals_full` (incremental ≡ brute-force 2K-bit recompute).
- `src/engine_c/seeds.py` — `resolve_seed_source` (gdv→wl graceful fallback, no orca binary),
  `compute_wl_colors` (shallow depth-1 seeds + deep depth-5 advisory filter), `generate_seeds`
  (deterministic triples from shallow color classes), and `clique_seed` (loads Engine A's verified
  38-clique certificate as a full warm-start mapping).
- `src/engine_c/grow.py` — `grow_from_seed`: rebuilds boundary groups each step (they mutate on every
  admission), admits the single best triple by a deterministic lexicographic `score` (deep-match,
  shallow-match, −degree-spread, min future-boundary, smallest-id), one admission per step.
- `src/engine_c/run.py` — CLI orchestrator mirroring Engine A: WL + adjacency once, clique warm-start
  prepended to WL seeds, ON + connectivity-OFF tracks, every kept result re-verified by `src.verify`,
  artifacts under `results/engine_c/`.

### Key decisions (and why)
- **Correctness backbone — incremental admission is exact.** Appending a row creates only new ordered
  pairs vs prior rows, so checking the new row's all-or-none agreement (the signature equality) is
  necessary AND sufficient to keep the partial map an induced isomorphism — exactly the verifier's
  check-3 semantics. No K×K rescan; per-step work is O(boundary).
- **Adjacency built once, fresh state per seed** (`fresh_state`) — sharing the immutable O(E)
  adjacency across all seeds instead of rebuilding it `num_seeds` times.
- **GDV requested but unavailable** → recorded `seed_source_requested=gdv` /
  `seed_source_effective=wl`, never crashes.
- **Warm-start from the 38-clique** (user decision) guarantees the connected best never regresses below
  the certified floor.
- **The step key is the pivotal knob — added `seed_color_key` (default true).** With shallow-WL color
  in the *hard* key, the necessary filter is correct but, across three genuinely non-isomorphic
  connectomes, blocks **every** cold-seed extension (all 17 cold seeds grew to N=1). Demoting color to
  an *advisory score term* (`--no-color-key`) keeps the signature check — which alone guarantees
  induced-iso, the verifier remains the authority — but is far more permissive.

### Findings → results (every N independently re-verified by `src.verify`)
- **Color-keyed (principled default) — N = 38, corroboration.** `python -m src.engine_c.run` →
  best connected **38** (the clique warm-start; greedy could not add a 39th globally-consistent triple),
  disconnected ceiling **43**. Cold WL seeds all stall at N=1 — empirical proof of how discriminating
  cross-connectome WL is (the P3 "great separator"). Engine C **independently corroborates** Engine A's
  38-clique floor. `results/engine_c/`.
- **Signature-only ablation — N ≥ 1292 but DEGENERATE.** `--no-color-key` from the clique warm-start
  grew to a verified connected **N=1292** (still growing when the 600 s budget hit). Structure analysis:
  density **0.0016**, **median total degree = 1**, min 1, mean 4.1, max 76, 712 reciprocal pairs —
  i.e. a small dense core of ~degree-76 hubs surrounded by hundreds of degree-1 pendant leaves. This is
  the hub-and-spoke **degeneracy** CLAUDE.md weights AGAINST (cf. Engine A's star=1877). Recorded as a
  ceiling, NOT submitted. `results/engine_c_nocolor/`.
- **Submission unchanged:** `network.csv` stays Engine A's dense, meaningful **38-clique** (every node
  degree 37, fully reciprocal) per the deliberate "smaller meaningful over larger degenerate" rule. The
  1292-vs-38 split is a clean empirical demonstration of the computation-to-optimization / meaningful-
  vs-degenerate gap that the README/science track foregrounds.

### Outputs produced
- `src/engine_c/{signature,seeds,grow,run}.py`; `tests/test_engine_c.py` (13 tests)
- `results/engine_c/` (color-keyed, N=38, ceiling 43) and `results/engine_c_nocolor/` (signature-only,
  N=1292 degenerate ceiling) — each with `best.json`, `best_disconnected.json`, `certificates/`,
  `frontier.csv`, `summary.md`, `seeds.json`, `config.snapshot.yaml`
- `config.yaml` engine_c: `seed_color_key`, `candidate_cap`, `boundary_cap`, `off_pool_cap`; git tag
  `v1.5-engineC`

### Open questions
- **Extract a meaningful dense sub-core from the 1292** (it contains a real recurrent core under the
  pendant leaves) — this is Engine B territory (exact MCS on a k-core/WL-reduced instance around the
  hub set), the natural next push past 38 toward a larger *non-degenerate* circuit.
- The color-keyed greedy can't grow the 38-clique to 39; whether a **non-clique** connected induced
  subgraph of size 39–48 (within the clique UB headroom) exists is open — Engine B should target it.
- The OFF/ceiling slice is time-boxed at 0.15·budget; under signature-only its connected run already
  dominates, so the disconnected ceiling is not separately informative there.

---

## Phase P6 — Engine B reduction + McSplit scaffolding (`src/engine_b`) (2026-06-11)

### What this phase did
Built Engine B — the exact-MCS corroboration arm — comprising a Python McSplit branch-and-bound
solver for the maximum common CONNECTED induced subgraph across three directed graphs, a k-core
reduction stage that narrows the 1292-node Engine C no-color certificate to a dense candidate pool,
and a three-step gated CLI (`--step 1/2/3`). Test-first: 7 tests written red, then to green (full
suite now **83 passing**). Tagged `v1.8-engineB`.

- `src/engine_b/reduce.py` — `kcore_reduce(datasets, cert_rows, col_names, kcore_min)`: iterative
  k-core peeling on plain dict/set adjacency (no igraph). A row is removed when its total degree
  (in + out, edges to other surviving rows only) falls below `kcore_min` in ANY of the three
  datasets simultaneously. Returns surviving string-ID lists.
- `src/engine_b/mcsplit.py` — `mcsplit_3graph(...)`: McSplit label-class B&B extended to 3 directed
  graphs. Label classes `(S_A, S_B, S_C)` of mutually-admissible unmatched vertices; upper bound =
  `|mapping| + Σ_classes min(|A|,|B|,|C|)`; prune when UB ≤ best; branch on each vertex in the
  smallest list of the largest class; refine ALL classes (including the current class's remaining
  vertices) by consistent directed-edge-type (4-type: none/x→u/u→x/both) to the newly added triple;
  connectivity via `out_adj ∪ in_adj` intersection with the mapped set; hard wall-clock deadline.
  Initial label classes partitioned by `(out_deg, in_deg)` signature.
- `src/engine_b/run.py` — `--step 1` reduces + reports count + writes `candidates/`; `--step 2`
  runs McSplit + writes `solutions/best.json`; `--step 3` verifies + writes certificate +
  `network.csv` + `summary.json`.

### Key decisions (and why)
- **Step-gated CLI** — user reviews each step's output before proceeding; fits the "stop and show
  me the count" workflow and makes the search/verify boundary explicit.
- **all_remaining includes the current class's residual vertices** — the critical McSplit correctness
  fix: passing only `rest` (classes minus the current class) to `_refine` discards the remaining
  vertices of the branching class, making every single-class instance return None. Fixed by building
  `all_remaining` from ALL current classes with the selected triple removed before calling `_refine`.
- **`kcore_min` lowered from 10 → 3** in config after kcore_min=10 converged to 38 (same as
  kcore_min=3); both produce the same result, confirming the structural observation below.

### Key structural finding (from Step 1 output)
**k-core peeling at ALL tested thresholds (3, 10) converges to exactly 38 surviving nodes**, all
members of the 38-clique. The Engine C no-color certificate's 1254 non-clique nodes each have total
degree < 3 in the joint induced subgraph across all three connectomes simultaneously — the structure
is a dense reciprocal 38-clique core surrounded by degree-1/2 pendant chains. The McSplit search on
this certificate would only ever find the 38-clique; Step 2 was therefore skipped and Step 3 run as
a corroboration record.

### Outputs produced
- `src/engine_b/{reduce,mcsplit,run}.py`; `tests/test_engine_b.py` (7 tests)
- `results/engine_b/candidates/{BANC,FAFB,MCNS}_candidates.txt` (38 nodes each),
  `step1_meta.json`, `config.snapshot.yaml`
- `results/engine_b/summary.json` — corroboration record: `core_size=38`, `best_N_found=38`,
  `verified=true`, `beats_clique=false`
- `config.yaml` `engine_b.reduce.kcore_min` 10 → 3; git tag `v1.8-engineB`

### Open questions
- **Engine B's McSplit is correct on toy graphs but untested on real data** — Step 2 was skipped
  because the candidate pool collapsed to the 38-clique. To exercise McSplit at scale, a different
  source pool is needed (e.g., WL-degree-pooled candidates from the full graphs, not filtered through
  the degenerate no-color certificate).
- **The 38-clique structural ceiling**: is there any connected non-clique induced subgraph of size
  39–48 in (BANC, FAFB, MCNS)? Engine B's McSplit is the right tool to answer this — but requires
  a richer candidate pool sourced directly from WL color classes on the full datasets (not post-hoc
  from Engine C's ceiling artifact).
- `network.csv` remains the Engine A **38-clique** (verified, meaningful, non-degenerate) — the
  correct submission at this stage.

---

## Phase P7 — Bounds & reproducibility (2026-06-11)

### What this phase did
Added `src/bounds/` (collect + ablation + summary), `scripts/run_all` pipeline, and
`FLYWIRE_CONFIG` env-var support to `src/config.py`. Produces `results/bounds/summary.json`
documenting the honest bound-vs-result gap and a 5-seed Engine C ablation.

### Key decisions
- **`FLYWIRE_CONFIG` env var** added to `src/config.py` (`load()` priority: explicit path >
  env var > default). `snapshot()` now copies whichever config was last loaded, not always the
  repo-root default. This lets `scripts/run_all --config <path>` propagate a custom config to
  every subprocess step without modifying any module.
- **Upper bounds scoped to chosen triple**: `collect_upper_bounds` accepts an optional `triple`
  parameter; when given, degeneracy bounds are computed only for those datasets. This avoids the
  misleading negative gap that results from mixing the MAOL degeneracy (29) with the BANC+FAFB+MCNS
  star lower bound (1877) — two incompatible structure families.
- **`best_lower_bound` scoped to chosen triple** via `primary_triple` param in `build_summary`:
  reports the max verified N for the submitted triple (BANC+FAFB+MCNS = 38), not the global max
  across all families (1877 for the directed-star triple FAFB+MAOL+MCNS).
- **Ablation uses clique warm-start**: `run_ablation` passes the Engine A certificate to
  `run_engine_c` as `clique_cert_path`, matching the normal invocation. Without this the greedy
  finds N=0 from cold WL seeds — not because it's fragile, but because the 38-clique is only
  reachable from the warm-start on these datasets.
- **OGP / computation-to-optimization gap** noted verbatim in `summary.json["note"]`: problem is
  NP-hard; best_lower_bound is a certificate, not a proven optimum.

### Outputs produced
- `src/config.py` — `FLYWIRE_CONFIG` env var + `_active_config_path` tracking
- `src/bounds/compute.py` — `collect_lower_bounds`, `collect_upper_bounds`, `run_ablation`,
  `build_summary` (243 lines)
- `src/bounds/run.py` — CLI: `python -m src.bounds.run [--skip-ablation] [--results-dir]`
- `scripts/run_all` — pipeline orchestrator; chains 10 steps; `--config` sets `FLYWIRE_CONFIG`
- `tests/test_bounds.py` — 27 new tests (110 total, all passing)
- `results/bounds/summary.json` — `best_lower_bound=38`, `tightest_upper_bound=48`, `gap=10`,
  `ablation.min_N=38`, `ablation.max_N=38` (seeds 1–5, mean 19.4 s/seed)
- `results/bounds/config.snapshot.yaml`

### Key finding
**N=38 is stable across all 5 ablation seeds** — every seed converges to the same 38-clique in
~19 s, confirming it is a robust attractor for the greedy given the clique warm-start. The
degeneracy+1 upper bound for the BANC+FAFB+MCNS triple is **48** (FAFB degeneracy = 47, so
degeneracy+1 = 48), leaving an honest gap of **10**: the true optimum for the connected MCIS on
this triple lies in [38, 48].

### Open questions
- **Gap [38, 48]**: a non-clique connected induced subgraph of size 39–48 may exist in
  (BANC, FAFB, MCNS). Engine B's McSplit on a WL-seeded candidate pool (not the degenerate
  Engine C certificate) is the correct tool to narrow this gap.
- **`scripts/run_all` engine_c_nocolor step** uses `--no-color-key` and `--no-off-ablation`
  flags; these are defined in `engine_c/run.py` argparse and confirmed working.

---

## Phase P8a — Ingest & Annotate FAFB Neurons (2026-06-12)

### What this phase did
Added `src/annotate.py` — a pure-pandas script that joins the three certified subgraph
certificates against the Codex FAFB annotation files (consolidated_cell_types, classification,
neurons, connections_princeton) to produce per-neuron annotation tables and internal synapse
statistics for each subgraph.

### Key decisions
- **Pure-pandas, no graph library:** the annotation step is a table join, not a graph computation;
  keeping it library-agnostic mirrors the verifier's design philosophy and makes it trivially
  portable.
- **`additional_type(s)` rename:** the Codex file uses a column name with literal parentheses
  (`additional_type(s)`); this is renamed to `additional_types` in output to avoid downstream
  quoting issues.
- **usecols for connections:** `connections_princeton.csv.gz` is 68 MB; loading only the four
  required columns (`pre_root_id`, `post_root_id`, `neuropil`, `syn_count`) halves peak memory.
- **Left-join strategy:** all annotation tables are left-joined onto the FAFB ID set so that
  unannotated neurons still appear in the output with NaN fields; the script never crashes on
  missing matches.
- **mean_syn_per_edge defined per directed pair:** synapse rows are first grouped by
  (pre_root_id, post_root_id) and summed before taking the mean, so multi-neuropil connections
  between the same pair are treated as one edge.
- **Annotation tables loaded once and shared across all three certificates** to avoid 3× I/O on
  the large connections file.

### Outputs produced
- `src/annotate.py` — annotation script (load_fafb_ids, join_annotations, compute_synapse_stats,
  format_summary, _load_annotation_tables, main CLI)
- `tests/test_annotate.py` — 7 unit tests using in-memory fixtures; all pass
- `results/biology/clique_38_annotated.csv` — 38 rows; 100% annotated
- `results/biology/star_1877_annotated.csv` — 1877 rows; 100% annotated
- `results/biology/nocolor_1292_annotated.csv` — 1292 rows; 99.54% annotated (6 unannotated)
- `results/biology/annotation_summary.txt` — per-subgraph summary with type counts, synapse stats

### Key findings
- **clique_38 (BANC+FAFB+MCNS):** 38 neurons, 100% annotated; all central, intrinsic, right-side;
  AL_R neuropil dominates internal synapses (86,258 / 86,275 total); mean 61.4 syn/edge — a dense
  antennal-lobe recurrent circuit.
- **star_1877 (FAFB+MAOL+MCNS):** 1877 neurons, 100% annotated; 1876/1877 are optic neurons
  (T4/T5 family), mostly left side; mean 16.9 syn/edge — a large motion-detection circuit.
- **nocolor_1292 (BANC+FAFB+MCNS, Engine C):** 1292 neurons, 99.54% annotated; heterogeneous
  (central + optic + visual_projection); mean 36.5 syn/edge; 6 FAFB root_ids absent from all
  annotation tables.

### Open questions
- The 6 unannotated FAFB neurons in nocolor_1292 may be neurons added after the Codex snapshot;
  worth cross-checking against a newer FAFB proofreading export.
- science.md biological interpretation section should discuss which of the three subgraphs is most
  biologically parsimonious as the final submission candidate.
