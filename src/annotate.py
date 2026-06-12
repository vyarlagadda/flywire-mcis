"""Annotate FAFB neurons in certified subgraphs with Codex metadata."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

DATA_DIR = Path("data/fafb_annotations")
RESULTS_DIR = Path("results/biology")

CERTIFICATES = {
    "clique_38": Path("results/engine_a/certificates/reciprocal_clique__BANC-FAFB-MCNS.csv"),
    "star_1877": Path("results/engine_a/certificates/directed_star__FAFB-MAOL-MCNS.csv"),
    "nocolor_1292": Path("results/engine_c_nocolor/certificates/engine_c__BANC-FAFB-MCNS.csv"),
}


def load_fafb_ids(cert: pd.DataFrame) -> pd.Series:
    """Return the FAFB column of a certificate as int64 Series."""
    return cert["FAFB"].astype("int64").reset_index(drop=True)


def join_annotations(
    fafb_ids: pd.Series,
    cell_types: pd.DataFrame,
    classification: pd.DataFrame,
    neurons: pd.DataFrame,
) -> pd.DataFrame:
    """Left-join annotation tables onto fafb_ids; return one row per neuron.

    Output columns: root_id (str), primary_type, additional_types,
                    super_class, flow, side, nt_type, nt_type_score.
    Missing joins produce NaN — never raises.
    """
    base = pd.DataFrame({"root_id": fafb_ids.astype("int64")})

    ct = cell_types[["root_id", "primary_type", "additional_type(s)"]].rename(
        columns={"additional_type(s)": "additional_types"}
    ).drop_duplicates(subset=["root_id"], keep="first")
    cl = classification[["root_id", "super_class", "flow", "side"]].drop_duplicates(
        subset=["root_id"], keep="first"
    )
    ne = neurons[["root_id", "nt_type", "nt_type_score"]].drop_duplicates(
        subset=["root_id"], keep="first"
    )

    merged = (
        base.merge(ct, on="root_id", how="left")
            .merge(cl, on="root_id", how="left")
            .merge(ne, on="root_id", how="left")
    )
    merged["root_id"] = merged["root_id"].astype(object)
    return merged[[
        "root_id", "primary_type", "additional_types",
        "super_class", "flow", "side", "nt_type", "nt_type_score",
    ]]


def compute_synapse_stats(
    fafb_set: set[int],
    connections: pd.DataFrame,
) -> dict:
    """Compute internal synapse statistics for a FAFB neuron set.

    Returns dict with keys:
      total_internal_synapses (int)
      mean_syn_per_edge (float)
      top3_neuropils (list of (neuropil, count) tuples, descending)
    """
    mask = (
        connections["pre_root_id"].isin(fafb_set)
        & connections["post_root_id"].isin(fafb_set)
    )
    internal = connections[mask].copy()

    if internal.empty:
        return {"total_internal_synapses": 0, "mean_syn_per_edge": 0.0, "top3_neuropils": []}

    total = int(internal["syn_count"].sum())

    per_pair = (
        internal.groupby(["pre_root_id", "post_root_id"], sort=False)["syn_count"]
        .sum()
    )
    mean_per_edge = float(per_pair.mean()) if len(per_pair) else 0.0

    by_neuropil = (
        internal.groupby("neuropil", sort=False)["syn_count"]
        .sum()
        .sort_values(ascending=False)
    )
    top3 = [(str(neuropil_name), int(cnt)) for neuropil_name, cnt in by_neuropil.head(3).items()]

    return {
        "total_internal_synapses": total,
        "mean_syn_per_edge": mean_per_edge,
        "top3_neuropils": top3,
    }


def format_summary(label: str, annotated: pd.DataFrame, stats: dict) -> str:
    lines: list[str] = [f"=== {label} ===", f"N = {len(annotated)}"]

    annotated_mask = annotated["primary_type"].notna()
    frac = annotated_mask.sum() / len(annotated) if len(annotated) else 0.0
    lines.append(f"Annotated fraction (primary_type not null): {frac:.2%}")

    def _counts(col: str, top: int = 10) -> str:
        vc = annotated[col].value_counts(dropna=True)
        rows = "\n".join(f"  {k}: {v}" for k, v in vc.head(top).items())
        return f"{col} counts:\n{rows}" if rows else f"{col} counts: (none)"

    lines.append(_counts("primary_type", 10))
    lines.append(_counts("super_class"))
    lines.append(_counts("flow"))
    lines.append(_counts("side"))
    lines.append(_counts("nt_type"))

    lines.append(f"total_internal_synapses: {stats['total_internal_synapses']}")
    lines.append(f"mean_syn_per_edge: {stats['mean_syn_per_edge']:.2f}")

    if stats["top3_neuropils"]:
        np_lines = "\n".join(f"  {neuropil}: {cnt}" for neuropil, cnt in stats["top3_neuropils"])
        lines.append(f"Top 3 neuropils by internal synapse count:\n{np_lines}")
    else:
        lines.append("Top 3 neuropils: (no internal synapses)")

    unannotated = annotated.loc[~annotated_mask, "root_id"].tolist()
    if unannotated:
        lines.append(f"Unannotated root_ids ({len(unannotated)}):")
        lines.extend(f"  {rid}" for rid in unannotated)
    else:
        lines.append("Unannotated root_ids: none")

    return "\n".join(lines)


def _load_annotation_tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load all four Codex annotation tables from DATA_DIR."""
    cell_types = pd.read_csv(DATA_DIR / "consolidated_cell_types.csv.gz")
    classification = pd.read_csv(DATA_DIR / "classification.csv.gz")
    neurons = pd.read_csv(DATA_DIR / "neurons.csv.gz")
    connections = pd.read_csv(
        DATA_DIR / "connections_princeton.csv.gz",
        usecols=["pre_root_id", "post_root_id", "neuropil", "syn_count"],
    )
    return cell_types, classification, neurons, connections


def main() -> None:
    parser = argparse.ArgumentParser(description="Annotate FAFB neurons in certified subgraphs")
    parser.add_argument("--out-dir", default=str(RESULTS_DIR))
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cell_types, classification, neurons, connections = _load_annotation_tables()

    summary_parts: list[str] = []
    for label, cert_path in CERTIFICATES.items():
        cert = pd.read_csv(cert_path)
        fafb_ids = load_fafb_ids(cert)
        annotated = join_annotations(fafb_ids, cell_types, classification, neurons)
        fafb_set = set(fafb_ids.tolist())
        stats = compute_synapse_stats(fafb_set, connections)

        out_csv = out_dir / f"{label}_annotated.csv"
        annotated.to_csv(out_csv, index=False)
        print(f"Wrote {out_csv} ({len(annotated)} rows)")

        summary_parts.append(format_summary(label, annotated, stats))

    summary_path = out_dir / "annotation_summary.txt"
    summary_path.write_text("\n\n".join(summary_parts) + "\n")
    print(f"Wrote {summary_path}")


if __name__ == "__main__":
    main()
