# Assumptions Ledger — FlyWire Maximum Common Induced Subgraph Challenge

*Phase P0. This page is self-contained and graded. It restates the problem precisely and records
every assumption the brief leaves open, with the decision we take and one sentence of justification
for each. Sources: `docs/brief/Qualification Challenge.pdf` (original, 2026-06-02) and
`docs/brief/Qualification Challenge Extension.pdf` (clarifications, 2026-06-08).*

---

## 1. Problem restatement (precise)

We are given five connectomic datasets — **BANC**, **FAFB**, **MANC**, **MAOL**, **MCNS** — each
supplied as a directed edge list (`source neuron id,target neuron id`) over its own neurons.

**Goal.** Find the largest integer **N** and a set of **N** neurons in **each of three** of the five
datasets, together with a row-by-row correspondence between the three sets, such that:

1. **Induced.** In each dataset we take the subgraph *induced* on its N chosen neurons — i.e. we
   keep every edge of that dataset whose endpoints are both chosen, and only those edges.
2. **Mutually isomorphic under the given alignment.** The correspondence aligns the three induced
   subgraphs vertex-for-vertex (row *r* names one neuron per dataset). For every ordered pair of
   rows *(i, j)*, the directed edge *i → j* is present in **all three** induced subgraphs or in
   **none** of them. Equivalently, the three induced subgraphs are identical as directed graphs once
   relabeled by the correspondence.
3. **Weakly connected.** The shared structure (identical across all three) is weakly connected:
   its underlying *undirected* graph — obtained by ignoring edge direction — is connected.

**Objective.** Maximize **N**, subject to (1)–(3). The grading note in the brief explicitly states
that *methodological rigor and clarity may be prioritized over the size of the circuit*; we therefore
treat N as a **verified lower bound with a certificate**, and we deliberately prefer a smaller,
biologically meaningful, non-degenerate circuit over a larger degenerate one (see `README.md`).

**Deliverable format.** `network.csv`: exactly **3 columns** (the chosen datasets, named in the
header) and **N rows**; cell *(r, d)* holds the identifier of the neuron in dataset *d* that plays
role *r* in the correspondence. The rows *are* the isomorphism — the verifier does not search for a
mapping, it checks edge-consistency under this fixed row alignment.

---

## 2. Assumptions ledger

Each entry: **what the brief says or leaves open → our decision → why.**

### Graph model

| # | Topic | Decision | Justification |
|---|-------|----------|---------------|
| A1 | **Directedness** | Treat every dataset as a **directed** graph; *i → j* and *j → i* are distinct edges, both subject to matching. | The brief defines a circuit as a *directed* induced subgraph and states "edge directionality must be preserved." |
| A2 | **Edge weights** | **Ignore** synapse-count weights; analyze the unweighted graph. | The brief: "for simplicity edge weights should be ignored… performed on the corresponding unweighted directed graphs." |
| A3 | **Self-loops** | **Remove** all self-loops (edges *i → i*) before analysis. | Self-loops carry no inter-neuron circuit structure and would corrupt induced-subgraph and isomorphism bookkeeping; a "circuit" is relational between distinct neurons. |
| A4 | **Parallel edges** | **Collapse** multiple *i → j* rows into a single directed edge (simple directed graph). | We use the unweighted graph (A2); multiplicity only re-encodes synapse count, which we ignore, so repeated rows are redundant. |
| A5 | **Edge list completeness / node presence** | A neuron is considered **present in a dataset iff it appears as the source or target of at least one (post-cleanup) edge** in that dataset. | Only edge lists are provided; isolated neurons (degree 0) are unrepresentable and, being disconnected, could never belong to a weakly connected shared circuit anyway (A9), so excluding them is lossless. |
| A6 | **Malformed / blank rows** | Drop rows that are empty, lack two fields, or duplicate the header; trim surrounding whitespace on IDs. | Defensive parsing keeps the structural graph faithful without inventing edges; documented so the verifier and loaders agree exactly. |

### Identifiers and matching

| # | Topic | Decision | Justification |
|---|-------|----------|---------------|
| A7 | **ID type** | Handle **all** neuron IDs as **strings**, never as int64. | BANC and FAFB use 18-digit root IDs that overflow signed 64-bit integers; string handling is uniform and lossless across all five datasets. |
| A8 | **Cross-dataset identity** | IDs are **not shared** across datasets; a neuron in one dataset has no a-priori counterpart in another. Matching is **purely structural** (topology only). | The brief's extension confirms metadata such as brain region was not provided and is not required for matching; the correspondence is established by graph structure, not by ID equality or annotation. |

### Correspondence semantics

| # | Topic | Decision | Justification |
|---|-------|----------|---------------|
| A9 | **"Identical" induced subgraphs** | Interpret as **directed-graph isomorphism under the row alignment**: for matched rows *(i, j)*, edge *i → j* exists in all three induced subgraphs or in none; likewise for *j → i*. | This is the brief's literal statement — "if an edge exists between two matched neurons in one dataset, the corresponding edge must exist in the others" — and it makes the CSV row order the explicit vertex bijection. |
| A10 | **Weak connectivity** | The shared structure must be **weakly connected**: its underlying undirected graph is connected (one weak component). | Added explicitly by the 2026-06-08 extension ("the discovered isomorphic structures must be weakly connected"); we check it on the undirected projection because "weak" connectivity is defined by ignoring direction. |
| A11 | **Number of datasets** | Target **exactly three** datasets (the best-scoring triple of the five), not all five. | The brief requires a circuit shared across "at least three" and fixes the solution file at exactly three columns; a single 3-column correspondence cannot encode a 4- or 5-way match, so we choose the strongest triple. |
| A12 | **Brain region / cell type** | Matched neurons need **not** share brain region, cell type, or any annotation across datasets. | The extension states explicitly there is no same-region requirement, "as this information was not provided in the data." |

### Degeneracy and minimum size

| # | Topic | Decision | Justification |
|---|-------|----------|---------------|
| A13 | **Trivial / degenerate matches** | Require **N ≥ 2** with the structure weakly connected, and prefer biologically meaningful, non-degenerate circuits over large degenerate ones. | A single vertex (N = 1) or an edgeless vertex set is a vacuous "circuit"; weak connectivity (A10) already forbids the edgeless case for N ≥ 2, and the brief warns that superficial results are scored unfavorably. |
| A14 | **No claim of global optimality** | Report achieved **N as a verified lower bound** plus a certificate; report any upper bounds (e.g. degeneracy + 1 for cliques) separately, never as the answer. | The problem is the NP-hard maximum common induced connected subgraph; claiming a proven maximum would be unsupportable, so we are explicit about what is certified versus conjectured. |

### Verification

| # | Topic | Decision | Justification |
|---|-------|----------|---------------|
| A15 | **Ground truth** | A candidate is trusted only once the independent **verifier** (`src/verify`) confirms it: it loads the raw data, applies A3–A6, and checks A9–A10 under the row alignment using plain dict/set adjacency, with **no** graph library and **no** dependency on any engine. | Mirroring FlyWire's grading with a deliberately independent oracle prevents an engine's own assumptions from certifying its own output. |

---

## 3. Out-of-scope / explicitly not assumed

- We do **not** assume IDs, ordering, or counts align across datasets in any way other than the
  explicit correspondence we construct (follows from A8).
- We do **not** assume the five graphs are comparable in size or density; the chosen triple (A11) is
  selected from data, not fixed in advance.
- We do **not** treat reciprocal connectivity (*i → j* and *j → i*) as a single undirected edge for
  matching purposes — both directions are matched independently (follows from A1/A9); direction is
  collapsed **only** for the weak-connectivity test (A10).
- We make **no** biological claim at this stage; biological interpretation is the separate research
  component (`science.md`) performed on one chosen dataset after the structural match is verified.
