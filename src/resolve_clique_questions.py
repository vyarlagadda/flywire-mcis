"""Resolve open annotation questions for the clique_38 subgraph before writing science.md."""
from __future__ import annotations

import math
from io import StringIO
from pathlib import Path

import pandas as pd

ANNOTATED = Path("results/biology/clique_38_annotated.csv")
DATA_DIR = Path("data/fafb_annotations")
OUT = Path("results/biology/clique_resolution.txt")


def _entropy_score(series: pd.Series, N: int) -> float:
    counts = series.dropna().value_counts()
    if counts.empty or N <= 1:
        return 20.0 if N <= 1 else 0.0
    probs = counts / counts.sum()
    H = -sum(p * math.log2(p) for p in probs if p > 0)
    return round(20.0 * max(0.0, 1.0 - H / math.log2(N)), 4)


def _df_to_block(df: pd.DataFrame) -> str:
    buf = StringIO()
    df.to_string(buf, index=False)
    return buf.getvalue()


def main() -> None:
    lines: list[str] = []

    def section(title: str) -> None:
        lines.append("")
        lines.append("=" * 70)
        lines.append(title)
        lines.append("=" * 70)

    def sub(title: str) -> None:
        lines.append("")
        lines.append(f"--- {title} ---")

    def out(*args: object) -> None:
        lines.append(" ".join(str(a) for a in args))

    # Load base annotated CSV
    ann = pd.read_csv(ANNOTATED)
    root_ids = ann["root_id"].astype("int64")
    id_set = set(root_ids.tolist())
    N = len(ann)

    # Load annotation tables (filtered to clique root_ids)
    neurons = pd.read_csv(DATA_DIR / "neurons.csv.gz")
    neurons_clique = neurons[neurons["root_id"].isin(id_set)].copy()

    cell_types = pd.read_csv(DATA_DIR / "consolidated_cell_types.csv.gz")
    cell_types_clique = cell_types[cell_types["root_id"].isin(id_set)].copy()

    classification = pd.read_csv(DATA_DIR / "classification.csv.gz")
    class_clique = classification[classification["root_id"].isin(id_set)].copy()

    # =========================================================
    section("QUESTION 1 — NT COHERENCE SUPPRESSED BY MISSING ANNOTATIONS")
    # =========================================================

    sub("1a. NT type coverage (null vs non-null)")
    null_mask = ann["nt_type"].isna()
    n_null = null_mask.sum()
    n_annotated = (~null_mask).sum()
    out(f"Total neurons       : {N}")
    out(f"nt_type non-null    : {n_annotated}  ({100*n_annotated/N:.1f}%)")
    out(f"nt_type null        : {n_null}  ({100*n_null/N:.1f}%)")

    sub("1b. NT type distribution among annotated neurons")
    nt_counts = ann["nt_type"].value_counts(dropna=True)
    for nt, cnt in nt_counts.items():
        out(f"  {nt}: {cnt}  ({100*cnt/N:.1f}% of all 38;  {100*cnt/n_annotated:.1f}% of annotated)")

    sub("1c. All columns available in neurons.csv.gz for the 38 clique root_ids")
    out("Column list in neurons.csv.gz:")
    for col in neurons.columns:
        out(f"  {col}")
    out("")
    out("Full neurons.csv.gz rows for the 38 clique neurons (sorted by root_id):")
    display_cols = [c for c in neurons_clique.columns]
    out(_df_to_block(neurons_clique.sort_values("root_id").reset_index(drop=True)[display_cols]))

    sub("1d. nt_type_score for neurons with null nt_type label")
    null_neurons = neurons_clique[neurons_clique["nt_type"].isna()].copy()
    # Show all per-NT probability columns if they exist
    prob_cols = [c for c in neurons_clique.columns if c not in ("root_id", "nt_type", "nt_type_score", "group")]
    out(f"Neurons with null nt_type: {len(null_neurons)}")
    if "nt_type_score" in null_neurons.columns:
        score_null = null_neurons["nt_type_score"].isna().sum()
        score_zero = (null_neurons["nt_type_score"] == 0.0).sum()
        score_nonzero = (~null_neurons["nt_type_score"].isna() & (null_neurons["nt_type_score"] != 0.0)).sum()
        out(f"  nt_type_score null  : {score_null}")
        out(f"  nt_type_score = 0.0 : {score_zero}")
        out(f"  nt_type_score > 0   : {score_nonzero}")
    if prob_cols:
        out("")
        out(f"Per-NT probability columns: {prob_cols}")
        out("Values for null-nt_type neurons:")
        show_cols = ["root_id", "nt_type", "nt_type_score"] + prob_cols
        show_cols = [c for c in show_cols if c in null_neurons.columns]
        out(_df_to_block(null_neurons[show_cols].sort_values("root_id").reset_index(drop=True)))
    else:
        out("(no per-NT probability columns found)")

    sub("1e. NT distribution grouped by primary_type")
    merged = ann[["root_id", "primary_type", "nt_type"]].copy()
    out("primary_type | n_total | nt_null | nt_annotated | nt distribution")
    for pt, grp in merged.groupby("primary_type", dropna=False):
        label = str(pt) if pd.notna(pt) else "(null)"
        n_tot = len(grp)
        n_na = grp["nt_type"].isna().sum()
        n_ann = n_tot - n_na
        dist = grp["nt_type"].value_counts(dropna=True).to_dict()
        dist_str = ", ".join(f"{k}:{v}" for k, v in dist.items()) if dist else "—"
        out(f"  {label:<14} | {n_tot:>7} | {n_na:>7} | {n_ann:>12} | {dist_str}")

    # =========================================================
    section("QUESTION 2 — TYPE_COHERENCE WITH COLLAPSED PARENT TYPES")
    # =========================================================

    sub("2a. Full primary_type distribution (all 38 neurons)")
    pt_counts = ann["primary_type"].value_counts(dropna=False)
    for pt, cnt in pt_counts.items():
        label = str(pt) if pd.notna(pt) else "(null)"
        out(f"  {label:<20} : {cnt}")

    sub("2b. parent_type mapping and distribution (lLN1_x → lLN1, lLN2_x → lLN2)")
    def _parent_type(s: str | float) -> str:
        if pd.isna(s):
            return "(null)"
        if s.startswith("lLN1"):
            return "lLN1"
        if s.startswith("lLN2"):
            return "lLN2"
        if s.startswith("lLN"):
            return "lLN"
        return s

    ann["parent_type"] = ann["primary_type"].apply(_parent_type)
    parent_counts = ann["parent_type"].value_counts()
    for pt, cnt in parent_counts.items():
        out(f"  {pt:<20} : {cnt}")

    sub("2c. collapsed_type distribution (all lLN variants → 'lLN')")
    def _collapsed_type(s: str | float) -> str:
        if pd.isna(s):
            return "(null)"
        if s.startswith("lLN"):
            return "lLN"
        return s

    ann["collapsed_type"] = ann["primary_type"].apply(_collapsed_type)
    collapsed_counts = ann["collapsed_type"].value_counts()
    for ct, cnt in collapsed_counts.items():
        out(f"  {ct:<20} : {cnt}")

    sub("2d. TYPE_COHERENCE scores at each level of resolution")
    score_raw = _entropy_score(ann["primary_type"], N)
    score_parent = _entropy_score(ann["parent_type"], N)
    score_collapsed = _entropy_score(ann["collapsed_type"], N)
    out(f"  primary_type  (original, ~10 types): TYPE_COHERENCE = {score_raw:.2f}/20")
    out(f"  parent_type   (lLN1 vs lLN2 level) : TYPE_COHERENCE = {score_parent:.2f}/20")
    out(f"  collapsed_type (all lLN as one)     : TYPE_COHERENCE = {score_collapsed:.2f}/20")

    out("")
    out("Entropy details:")
    for label, col in [("primary_type", "primary_type"), ("parent_type", "parent_type"), ("collapsed_type", "collapsed_type")]:
        counts = ann[col].dropna().value_counts()
        probs = counts / counts.sum()
        H = -sum(p * math.log2(p) for p in probs if p > 0)
        out(f"  {label:<20}: H={H:.4f} bits, log2(N)={math.log2(N):.4f}, H/log2(N)={H/math.log2(N):.4f}")

    sub("2e. Classification hierarchy for the 38 neurons (from classification.csv.gz)")
    out("Columns available in classification.csv.gz:")
    for col in classification.columns:
        out(f"  {col}")
    out("")
    out("Classification rows for the 38 clique neurons:")
    out(_df_to_block(class_clique.sort_values("root_id").reset_index(drop=True)))

    out("")
    out("Value counts per classification column:")
    for col in class_clique.columns:
        if col == "root_id":
            continue
        vc = class_clique[col].value_counts(dropna=False)
        if len(vc) <= 10:
            out(f"  {col}:")
            for val, cnt in vc.items():
                out(f"    {str(val):<30}: {cnt}")

    # =========================================================
    section("SUMMARY FOR SCIENCE.MD")
    # =========================================================
    out("")
    out("NT COHERENCE:")
    out(f"  {n_annotated}/38 neurons have nt_type annotation ({100*n_annotated/N:.1f}%)")
    out(f"  Of these: {dict(nt_counts)}")
    if n_null > 0:
        out(f"  {n_null} unannotated neurons — check 1d for whether per-NT probability columns exist")

    out("")
    out("TYPE_COHERENCE at three resolutions:")
    out(f"  Raw primary_type : {score_raw:.2f}/20")
    out(f"  Parent type      : {score_parent:.2f}/20")
    out(f"  Collapsed lLN    : {score_collapsed:.2f}/20")
    out(f"  Collapsed composition: {collapsed_counts.to_dict()}")

    # Write output
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n")
    print(f"Wrote {OUT}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
