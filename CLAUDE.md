# FlyWire Qualification Challenge — Maximum Common Induced Subgraph (≥3 of 5 connectomes)

## Goal
Find the largest set of N neurons present in ≥3 of the 5 connectome datasets whose INDUCED,
DIRECTED subgraphs are mutually isomorphic AND weakly connected. Maximize N, subject to the
structure being a clear, biologically meaningful recurrent circuit (we weight a smaller meaningful
circuit OVER a larger degenerate one — this is a deliberate, theory-backed choice; see README).

## Final deliverables (repo root — submitted)
- network.csv : matched-neuron table — 3 columns (chosen datasets) × N rows (neuron IDs). MUST pass the verifier.
- README.md   : technical approach — the chain of thought, methods, and why.
- science.md  : one-page scientific summary (research component; after the technical track).

## Datasets (directed, unweighted edge lists in data/raw/; header `source neuron id,target neuron id`)
banc_626, fafb_783, manc_1_2_1, maol_1_1, mcns_0_9
- BANC and FAFB use 18-digit root IDs → ALWAYS handle neuron IDs as STRINGS, never int64.
- IDs are NOT shared across datasets. Matching is purely STRUCTURAL.
- Simple directed graphs: remove self-loops, collapse parallel edges.

## Architecture — THREE engines + one verifier. Results stored separately under results/<stage>/.
- ENGINE A (engine_a) — canonical, correct-by-construction: restrict the shared shape to families
  (reciprocal clique, directed star, complete bipartite) where equal-size instances are
  automatically isomorphic. Solve each dataset independently (igraph), N = min across the 3.
  Truncation valid; weak connectivity automatic. This is the CERTIFIED FLOOR.
- ENGINE C (engine_c) — connectivity-constrained greedy seed-and-extend: the polynomial LCIS
  greedy fused with GRAAL-style seed-and-extend, adapted to directed + 3-graph + weak-connectivity,
  with the EXACT induced-isomorphism check inline at every expansion step. Seeds from WL signatures
  (cheap) or optional sampled GDV/ORCA fingerprints. Runs on full graphs / pruned pools. LIKELY
  WORKHORSE for the largest MEANINGFUL N.
- ENGINE B (engine_b) — exact MCS on REDUCED instances (stretch): McSplit-family / modular-product
  branch-and-bound for the maximum common CONNECTED induced subgraph, on small WL-pruned + k-core
  candidate subgraphs, with vertex-equivalence pruning and smallest-first ordering. Corroborates
  or pushes N; never claimed as a global optimum.
- WL pruning is NECESSARY-not-sufficient: it removes impossible matches and shrinks the search;
  it NEVER confirms a match. Only the verifier confirms.

## Hard rules (do not violate)
- The VERIFIER (src/verify) is the ground-truth oracle and mirrors FlyWire's grading. It uses plain
  dict/set adjacency — NO graph library — and may use src/io to load, but MUST NOT depend on any
  engine code (engine_a/b/c, invariants). Every candidate is checked by it before being trusted or committed.
- "Identical induced subgraphs" = directed-graph isomorphism under the row alignment: for every
  matched pair (i,j), edge i→j is present in ALL three datasets or in NONE; same for j→i.
- Never claim a global optimum. The problem is NP-hard, worst-case inapproximable, and exhibits a
  computation-to-optimization gap (overlap gap property) — report achieved N as a verified LOWER
  BOUND + certificate; report upper bounds (e.g. degeneracy+1 for cliques) separately.
- No superficial filler. Every method choice must be explainable from first principles in README.md.

## Stack
- igraph (C core) for ALL heavy ops: largest_cliques, k_core/coreness, weak components,
  motifs_randesu (directed), bipartite_projection. scipy.sparse (CSR) is the adjacency substrate
  for custom routines, the directed WL impl, and Engine C. rustworkx optional (Rust, pip, VF2
  cross-check). NetworkX ONLY for small-graph viz + toy tests — never on full graphs. Engine B =
  compiled McSplit / Glasgow Subgraph Solver. ORCA optional for GDV. graph-tool/networkit = escalation only.
- All tunable params live in config.yaml, read via src/config.py. Never hard-code seeds, budgets,
  thresholds, or the chosen triple. Snapshot config.yaml into each result dir as config.snapshot.yaml.

## Build order (de-risks the deadline)
Engine A (certified floor) → Engine C (workhorse, largest meaningful N) → Engine B (exact corroboration, stretch).
Engine A alone is already a complete, certified submission.

## Workflow conventions
- Plan first for algorithmic phases (plan mode); do NOT write code until I approve the plan.
- Test-first for the verifier and engines: failing tests, then implement to green.
- One phase = one git branch = one focused session. Commit at phase end; update docs/phase-log.md
  with what was done, key decisions and why, outputs produced, open questions.
- Reproducibility: seed all RNG from config; record seeds + wall-clock in each result JSON.

## Commands
- Setup : python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
- Tests : pytest -q
- Verify: python -m src.verify.check --candidate <path/to/network.csv>
  (Run the verifier after ANY change that could affect a solution.)