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
- The real-data end-to-end sanity-load (`load_dataset("MAOL")`) is **unverified**: `data/raw/**` is
  deny-listed for all tools, so it can't be run here. Toy-CSV unit tests cover correctness, but a
  real-file run (counts, wall-clock) should be confirmed manually by the user.
- `load_dataset`/`load_all` resolve `data.dir` relative to CWD; if invoked from outside repo root,
  paths may need to be anchored to repo root — revisit if any engine runs from a result dir.
