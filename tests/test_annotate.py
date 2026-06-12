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


def _make_cell_types(root_ids: list[int]) -> pd.DataFrame:
    return pd.DataFrame({
        "root_id": root_ids,
        "primary_type": ["T4b", "T5b"],
        "additional_type(s)": [None, "T5c"],
    })


def _make_classification(root_ids: list[int]) -> pd.DataFrame:
    return pd.DataFrame({
        "root_id": root_ids,
        "flow": ["intrinsic", "efferent"],
        "super_class": ["optic", "optic"],
        "class": ["T4/T5", "T4/T5"],
        "sub_class": [None, None],
        "hemilineage": [None, None],
        "side": ["left", "right"],
        "nerve": [None, None],
    })


def _make_neurons(root_ids: list[int]) -> pd.DataFrame:
    return pd.DataFrame({
        "root_id": root_ids,
        "group": [None, None],
        "nt_type": ["GABA", "ACH"],
        "nt_type_score": [0.95, 0.88],
        "da_avg": [0.01, 0.02],
        "ser_avg": [0.01, 0.01],
        "gaba_avg": [0.90, 0.05],
        "glut_avg": [0.02, 0.03],
        "ach_avg": [0.03, 0.80],
        "oct_avg": [0.01, 0.01],
    })


def test_join_annotations_all_present():
    from src.annotate import join_annotations

    ids = pd.Series([720575940628908548, 720575940603022304], dtype="int64")
    ct = _make_cell_types(list(ids))
    cl = _make_classification(list(ids))
    ne = _make_neurons(list(ids))
    result = join_annotations(ids, ct, cl, ne)

    assert list(result.columns) == [
        "root_id", "primary_type", "additional_types",
        "super_class", "flow", "side", "nt_type", "nt_type_score",
    ]
    assert result["root_id"].dtype == object  # strings in output
    assert result.loc[0, "primary_type"] == "T4b"
    assert result.loc[1, "side"] == "right"
    assert result.loc[0, "nt_type"] == "GABA"
    assert len(result) == 2


def test_join_annotations_missing_graceful():
    from src.annotate import join_annotations

    ids = pd.Series([720575940628908548, 999999999999999999], dtype="int64")
    ct = _make_cell_types([720575940628908548, 720575940628908548])  # second ID missing
    cl = _make_classification([720575940628908548, 720575940628908548])
    ne = _make_neurons([720575940628908548, 720575940628908548])
    result = join_annotations(ids, ct, cl, ne)

    # Still has 2 rows; missing neuron gets NaN for all annotation cols
    assert len(result) == 2
    assert pd.isna(result.loc[1, "primary_type"])


from src.annotate import compute_synapse_stats


def _make_connections() -> pd.DataFrame:
    return pd.DataFrame({
        "pre_root_id":  [720575940628908548, 720575940628908548, 720575940603022304],
        "post_root_id": [720575940603022304, 720575940603022304, 720575940628908548],
        "neuropil": ["ME_L", "ME_R", "ME_L"],
        "syn_count": [12, 3, 7],
        "nt_type": ["GABA", "GABA", "ACH"],
    })


def test_compute_synapse_stats_basic():
    fafb_set = {720575940628908548, 720575940603022304}
    conn = _make_connections()
    stats = compute_synapse_stats(fafb_set, conn)

    # 12+3+7 = 22 total; 3 rows collapse to 2 directed pairs after sum
    assert stats["total_internal_synapses"] == 22
    # 2 unique directed pairs: 22/2 = 11.0
    assert stats["mean_syn_per_edge"] == pytest.approx(11.0)
    # top 3 neuropils: ME_L has 12+7=19, ME_R has 3
    assert stats["top3_neuropils"][0] == ("ME_L", 19)
    assert stats["top3_neuropils"][1] == ("ME_R", 3)


def test_compute_synapse_stats_empty():
    fafb_set = {720575940628908548}
    conn = _make_connections()
    stats = compute_synapse_stats(fafb_set, conn)
    # Only 1 neuron — no internal edges
    assert stats["total_internal_synapses"] == 0
    assert stats["mean_syn_per_edge"] == 0.0
    assert stats["top3_neuropils"] == []


from src.annotate import format_summary


def test_format_summary_contains_required_sections():
    annotated = pd.DataFrame({
        "root_id": ["720575940628908548", "720575940603022304", "999"],
        "primary_type": ["T4b", "T5b", None],
        "additional_types": [None, "T5c", None],
        "super_class": ["optic", "optic", None],
        "flow": ["intrinsic", "efferent", None],
        "side": ["left", "right", None],
        "nt_type": ["GABA", "ACH", None],
        "nt_type_score": [0.95, 0.88, None],
    })
    stats = {
        "total_internal_synapses": 22,
        "mean_syn_per_edge": 11.0,
        "top3_neuropils": [("ME_L", 19), ("ME_R", 3)],
    }
    text = format_summary("test_subgraph", annotated, stats)

    assert "N = 3" in text
    assert "Annotated fraction" in text
    assert "primary_type" in text
    assert "super_class" in text
    assert "flow" in text
    assert "side" in text
    assert "nt_type" in text
    assert "total_internal_synapses" in text
    assert "mean_syn_per_edge" in text
    assert "ME_L" in text
    assert "unannotated" in text.lower()
    assert "999" in text
