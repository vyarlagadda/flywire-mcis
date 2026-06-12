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
