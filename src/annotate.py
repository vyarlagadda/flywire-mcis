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
