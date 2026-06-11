# Phase Log

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
