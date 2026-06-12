# tests/test_annotate.py
import pandas as pd
import pytest
from src.annotate import load_fafb_ids


def _make_cert(fafb_col: str, ids: list[int]) -> pd.DataFrame:
    return pd.DataFrame({fafb_col: ids, "OTHER1": range(len(ids)), "OTHER2": range(len(ids))})


def test_load_fafb_ids_basic():
    cert = _make_cert("FAFB", [720575940628908548, 720575940603022304])
    ids = load_fafb_ids(cert)
    assert list(ids) == [720575940628908548, 720575940603022304]
    assert ids.dtype == "int64"


def test_load_fafb_ids_single_row():
    cert = _make_cert("FAFB", [720575940628908548])
    ids = load_fafb_ids(cert)
    assert len(ids) == 1
