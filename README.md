# FlyWire Qualification Challenge — README

**Final Result:** 38 matched neurons across BANC, FAFB, and MCNS  
**Structure:** Fully Reciprocal Clique (all 703 possible bidirectional pairs present)  
**Verified:** Passed 4 Different Verifications

---

## The Problem

My task was to find the largest set of N neurons that appears in at least three of the five connectome datasets ( BANC (female brain and nerve cord), FAFB (female adult fly brain), MANC (male adult nerve cord), MAOL (male adult optic lobe), and MCNS (male whole CNS) ) such that the connections between those neurons are identical across all three datasets and the neurons form a single connected structure.

We also had certain constraints to clarify "Identical connections": pick N neurons in dataset A, N in dataset B, and N in dataset C, and line them up row by row. For every pair of rows, if neuron in row 2 connects to neuron in row 5 in dataset A, it must do the same in datasets B and C. If there is no connection in dataset A, there must be no connection in B or C either. This has to hold for every pair in both directions. That is just directed graph isomorphism under the row alignment, and it is what the verifier checks.

Since this type of problem is NP-hard, there is no efficient shortcut as the search space grows exponentially with N. So instead, the following results I report is a verified lower bound: a solution I found and verified.

---

## Choosing the Right Three Datasets

Before searching, I needed to pick which three datasets to focus further on. If I was to do this blindly, mixing very different datasets, it would make finding a large common subgraph harder because the local circuit statistics might look very different.

So instead, to measure similarity, I computed the distribution of all possible 3-neuron connection patterns (3-node directed motif profile) of each dataset and measured the L1 distance between profiles for every possible triple. Following this, **BANC + FAFB + MCNS had the lowest total distance (0.389)**, which simply means their local connectivity patterns are more similar to each other than any other combination of datasets. This was the best choice by a large margin, as the next-best triple was 0.609.

I also confirmed my choice against the upper bound for the reciprocal clique search for the other data sets as well. From this, I found that any triple containing MAOL would be capped at N=12 because the MAOL dataset's dense reciprocal core is small despite having the most total edges. Finally, the BANC + FAFB + MCNS tripley also has a theoretical ceiling of N=48, which made it the clear triple for me to work with.

---

## Graph Cleanup

Before searching, every dataset I planned to use was cleaned up the same way:

- **Self-loops Removed:** A neuron connecting to itself would carry no circuit information and would instead negatively affect the isomorphism check, so they were removed.
- **Parallel Edges Collapsed:** Here, multiple rows for the same directed pair were merged into one edge, since we are ignoring the weights of any edges in this analysis.
- **Neuron IDs:** — BANC and FAFB have 18-digit root IDs, so instead of treating them as numbers, I simply converted them to strings.

---

## Technical Strategy

Simply put, my total search used three independent "engines", with each approaching this same problem differently. Subsequently, every result from every engine was checked by the same independent verifier before being recorded and solidified.

### The Verifier

Before writing any search code, I wrote a simply verification script `src/verify/check.py` which runs four checks in order:

1. **Structural:** Correct number of columns, no duplicate IDs, at least 2 rows.
2. **Existence:** Check if every neuron ID actually appears in its respective dataset.
3. **Induced Isomorphism:** I check that for every pair of rows, the edge pattern identical and agrees across all three datasets.
4. **Weak Connectivity** The matched neurons form one connected structure.

My verifier script uses no graph library and only plain Python sets and a union-find algorithm. I deliverately did this so that my verifier is kept fully independent of the search engines so any sort of bugs or errors cannot affect other runs or serches.

### Engine A — Simple Canonical Structure Search

To officially start this problem, my first "engine" explicitly searches for three specific families of structures where isomorphism is guaranteed by construction, alongside any subgraphs of it. I started simply like this since if you build the same structure in each dataset, they are automatically isomorphic and no matching is needed:

**Reciprocal clique:** A structure where every neuron connects to every other neuron in both directions. In our problem, to find the largest one in each dataset, I used igraph's k-core decomposition to narrow down the search region since only neurons with high enough connectivity can be in a large clique, then ran exact clique search within that reduced region. Following that, here were the per-dataset results that I was left with:

| Dataset | Clique found | Upper bound |
|---------|:---:|:---:|
| BANC | 38 | 50 |
| FAFB | 38 | 48 |
| MANC | 28 | 65 |
| MAOL | 12 | 29 |
| MCNS | 41 | 51 |

From the data above, The triple minimum gives N=38 for BANC+FAFB+MCNS. Note that my exact search finished in roughly under 6 seconds seconds on every dataset.

**Directed star:** A structure with one hub neuron connected to many leaves, with no connections between leaves. This kind of search produced N=1,877 on FAFB+MAOL+MCNS. The exact rationaled for why I declined this structure is further below.

**Complete Bipartite** A structure with two groups of neurons where every neuron in group A connects to every neuron in group B. This search produced N=15 on BANC+FAFB+MCNS which is smaller than the clique found earlier.

All 24 verified certificates from each test run with Engine A can be found in `results/engine_a/certificates/`.

### Engine B — WL Filtering and McSplit

Then, for another kind of search, before running exact branch-and-bound search later, I researched and used Weisfeiler-Leman (WL) color refinement to filter the candidate space. Here, WL assigns each neuron a "color" based on its neighborhood structure so two neurons with different colors cannot possibly be matched. Alongside this, by using content-hash colors (a hash of the actual degree values), these colors are directly comparable across different datasets without any kind of shared lookup table.

At depth 5, WL reduced the candidate pool from 11,211 shared color classes at depth 0 down to just 2 which means deep WL was a near perfect separator across these three connectomes. Because of that, this ruled out almost every neuron as a possible match partner before any expensive search began.

I also then applied k-core peeling to the large candidate structure found by Engine C (described below) which iteratively removes any neuron with fewer than 3 connections to other surviving neurons in any of the three datasets. At both thresholds tested (k=3 and k=10), this converged to exactly 38 neurons, which were the the same 38 neurons from Engine A. This further confirmed that confirmed that the large structure (found in Engine C) was just the original 38-clique with thousands of weakly-attached leaf neurons hanging off it, and NOT a larger coherent circuit.

### Engine C — Greedy Seed and Extend

This third "engine" directly started from the verified 38-clique and tried to grow it by adding one neuron triplet at a time. At each step it checked the isomorphism condition incrementally. Specifically, instead of rechecking all prior pairs, it computed a "connection signature" for each candidate, which is a compact encoding of how it connects to every already-matched neuron. From this. two candidates from different datasets can only be matched if their signatures are identical.

I also continued this, and by running with a strict color filter (requiring WL color agreement on top of signature agreement), the greedy search could not find a 39th consistent triplet which is another independent confirmation of N=38 as the local cap. This same process was run five times with different random seeds, and all five converged to N=38 in about 19 seconds each.

Running without the color filter, the greedy search grew to N=1,292 before the time limit I gave for the search ran out. A further structure analysis revealed that 1,254 of those neurons were degree-1 leaves each connected to the 38-clique core by a single edge but not connected to each other. This is the same degeneracy structure as the directed star.

---

## Results

| Candidate | Datasets | N | Density | Reciprocal pairs | Disposition |
|-----------|----------|:-:|:-------:|:----------------:|-------------|
| Directed star | FAFB+MAOL+MCNS | 1,877 | ~0.001 | 0 | Declined — degenerate |
| Nocolor extension | BANC+FAFB+MCNS | 1,292 | ~0.002 | 712 | Declined — degenerate |
| **Reciprocal clique** | **BANC+FAFB+MCNS** | **38** | **1.000** | **703** | **Submitted** |
| Complete bipartite | BANC+FAFB+MCNS | 15 | — | 0 | Smaller than clique |

Followind my analysis, I reached a verified lower bound N=38, and a theoretical ceiling N=48 (FAFB reciprocal degeneracy), so this shows that true optimum might be somewhere in [38, 48] neurons.

---

## Why N=38 and Not N=1,877 or N=1,292

After a simple structural analysis, I found that the two larger results were perfectly valid according to the challenge guidelines, but they were structurally degenerate.

The **directed star (N=1,877)** is one CT1-type hub neuron connected outward to 1,876 T4/T5 optic lobe leaves. The leaves have zero connections to each other. There is no recurrent structure, no internal connectivity between the leaf neurons, it is a hub with leaves, and was not a circuit according to the assumptions and constraints I made for myself when wanting to find clear biological significance.

The **nocolor extension (N=1,292)** was the same problem. The k-core peeling revealed that 1,254 of the 1,292 neurons had degree 1 or 2 in the joint subgraph, which shows that they are also just leaves hanging off the 38-clique core. By removing them, you are left with exactly the 38-neurons clique.

Apart from this, to score all three candidates against any biological criteria, I joined each subgraph's FAFB neuron IDs against the Codex annotation files (cell types, classification hierarchy, neurotransmitter predictions, and internal synapse counts) and "graded" each structure across 5 components.

| Component | Clique 38 | Star 1,877 | Nocolor 1,292 |
|-----------|:---------:|:----------:|:-------------:|
| Identifiability | 20.00 | 20.00 | 19.91 |
| Type coherence | 8.59 | 14.66 | 1.28 |
| NT coherence | 4.74 | 16.16 | 11.36 |
| Anatomical locality | 20.00 | 15.73 | 17.74 |
| Circuit richness | 20.00 | 0.00 | 11.02 |
| **Total** | **73.32** | **66.55** | **61.31** |

The clique wins on the three most important components for the circuit to me (identifiability, locality, and richness). To explain where this structure lacked, its lower type and NT coherence scores were annotation artifacts as the dominant cell type (lLN1_bc) falls below the FlyWire NT classifier's confidence threshold for 23 of 38 neurons, a documented limitation of serotonin prediction for this cell class. At the Codex class level, 36 of 38 clique neurons are ALLN (Antennal Lobe Local Neurons) from the same ALl1_dorsal hemilineage — a type coherence of approximately 18/20.

Apart from this, the star's higher type and NT coherence scores are structural artifacts as all internal edges flow from the single CT1 hub to disconnected leaves, so the "coherence" reflects the hub's properties replicated across 1,876 neurons that share no connections with each other. With its circuit richness at 0, the star cannot be a functional circuit regardless of its other coherence scores.

With these and other criteria I set for myself to rigorously find a useful and verifiable circuit, I selected the 38-neuron reciprocal clique which is a dense, fully bidirectional recurrent network of antennal lobe local interneurons, localized almost entirely to the right antennal lobe (99.98% of 86,275 internal synapses in AL_R), and conserved across a female brain, a female whole-CNS, and a male whole-CNS datasets.

---

## Reproducing the Results

**Requirements:** Python ≥ 3.10, raw edge-list CSVs in `data/raw/`, FAFB annotation files in `data/fafb_annotations/`.

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Full pipeline
python scripts/run_all --config config.yaml

# Verify the submitted result
python -m src.verify.check --candidate network.csv
```

Expected verifier output:
```
[1] structural ................ PASS
[2] existence ................. PASS
[3] induced isomorphism ....... PASS
[4] weak connectivity ......... PASS
structure: clique
RESULT: PASS  (exit 0)
```

Individual steps can be run separately — see `scripts/run_all` for the full sequence. Key parameters (time budgets, dataset paths, search depths) are all in `config.yaml`. The global seed is `20260610`; results are deterministic given the same seed and input data.

**Data files needed:**

| File | Location |
|------|----------|
| BANC v626 edge list | `data/raw/banc_626_edge_list.csv` |
| FAFB v783 edge list | `data/raw/fafb_783_edge_list.csv` |
| MANC v1.2.1 edge list | `data/raw/manc_1_2_1_edge_list.csv` |
| MAOL v1.1 edge list | `data/raw/maol_1_1_edge_list.csv` |
| MCNS v0.9 edge list | `data/raw/mcns_0_9_edge_list.csv` |
| FAFB cell types | `data/fafb_annotations/consolidated_cell_types.csv.gz` |
| FAFB classification | `data/fafb_annotations/classification.csv.gz` |
| FAFB neurotransmitters | `data/fafb_annotations/neurons.csv.gz` |
| FAFB connections | `data/fafb_annotations/connections_princeton.csv.gz` |
