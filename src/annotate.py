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
