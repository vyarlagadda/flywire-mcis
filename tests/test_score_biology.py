# tests/test_score_biology.py
import pandas as pd
import pytest

from src.score_biology import (
    score_identifiability,
    score_type_coherence,
    score_nt_coherence,
    score_anatomical_locality,
    count_reciprocal_pairs,
    score_circuit_richness,
    compute_scores,
)


def _ann(primary_types, nt_types) -> pd.DataFrame:
    n = len(primary_types)
    return pd.DataFrame({
        "root_id": list(range(1, n + 1)),
        "primary_type": primary_types,
        "nt_type": nt_types,
    })


def _conn(pre, post, syn=None) -> pd.DataFrame:
    n = len(pre)
    return pd.DataFrame({
        "pre_root_id": pre,
        "post_root_id": post,
        "neuropil": ["X"] * n,
        "syn_count": syn if syn is not None else [1] * n,
    })


# --- IDENTIFIABILITY ---

def test_identifiability_all_annotated():
    assert score_identifiability(_ann(["A", "B", "C"], ["ACH"] * 3)) == pytest.approx(20.0)


def test_identifiability_half():
    assert score_identifiability(_ann(["A", None, "C", None], ["ACH"] * 4)) == pytest.approx(10.0)


def test_identifiability_none_annotated():
    assert score_identifiability(_ann([None, None], ["ACH", "ACH"])) == pytest.approx(0.0)


# --- TYPE_COHERENCE ---

def test_type_coherence_all_same():
    assert score_type_coherence(_ann(["A"] * 4, ["ACH"] * 4)) == pytest.approx(20.0)


def test_type_coherence_all_distinct():
    # H = log2(4) = 2; log2(N) = log2(4) = 2 → score = 0
    assert score_type_coherence(_ann(["A", "B", "C", "D"], ["ACH"] * 4)) == pytest.approx(0.0, abs=1e-9)


def test_type_coherence_n1():
    assert score_type_coherence(_ann(["A"], ["ACH"])) == pytest.approx(20.0)


def test_type_coherence_all_null():
    assert score_type_coherence(_ann([None, None, None], ["ACH"] * 3)) == pytest.approx(0.0)


def test_type_coherence_bounded():
    score = score_type_coherence(_ann(["A", "B"], ["ACH"] * 2))
    assert 0.0 <= score <= 20.0


# --- NT_COHERENCE ---

def test_nt_coherence_all_same():
    assert score_nt_coherence(_ann(["A"] * 5, ["ACH"] * 5)) == pytest.approx(20.0)


def test_nt_coherence_half():
    # ACH:2, GABA:2 out of N=4 → 20*2/4 = 10.0
    assert score_nt_coherence(_ann(["A"] * 4, ["ACH", "ACH", "GABA", "GABA"])) == pytest.approx(10.0)


def test_nt_coherence_all_null():
    assert score_nt_coherence(_ann(["A", "B"], [None, None])) == pytest.approx(0.0)


# --- ANATOMICAL_LOCALITY ---

def test_anatomical_locality_all_in_top():
    stats = {"total_internal_synapses": 100, "top3_neuropils": [("AL_R", 100)]}
    assert score_anatomical_locality(stats) == pytest.approx(20.0)


def test_anatomical_locality_half():
    stats = {"total_internal_synapses": 100, "top3_neuropils": [("AL_R", 50), ("LH_R", 50)]}
    assert score_anatomical_locality(stats) == pytest.approx(10.0)


def test_anatomical_locality_zero_synapses():
    stats = {"total_internal_synapses": 0, "top3_neuropils": []}
    assert score_anatomical_locality(stats) == pytest.approx(0.0)


# --- COUNT_RECIPROCAL_PAIRS ---

def test_count_reciprocal_pairs_one_pair():
    # 1→2, 2→1 (reciprocal); 2→3 (no return)
    assert count_reciprocal_pairs({1, 2, 3}, _conn([1, 2, 2], [2, 1, 3])) == 1


def test_count_reciprocal_pairs_star_zero():
    # Hub 1 → leaves 2,3,4; no return edges
    assert count_reciprocal_pairs({1, 2, 3, 4}, _conn([1, 1, 1], [2, 3, 4])) == 0


def test_count_reciprocal_pairs_fully_reciprocal_4clique():
    # 4-node full reciprocal clique: 4*3/2 = 6 pairs
    fafb_set = {1, 2, 3, 4}
    edges = [(a, b) for a in fafb_set for b in fafb_set if a != b]
    assert count_reciprocal_pairs(fafb_set, _conn([e[0] for e in edges], [e[1] for e in edges])) == 6


# --- SCORE_CIRCUIT_RICHNESS ---

def test_circuit_richness_capped():
    # 703 pairs / 38 nodes → min(20, 370) = 20
    assert score_circuit_richness(703, 38) == pytest.approx(20.0)


def test_circuit_richness_zero():
    assert score_circuit_richness(0, 1877) == pytest.approx(0.0)


def test_circuit_richness_partial():
    # 5 pairs / N=20 → min(20, 5.0) = 5.0
    assert score_circuit_richness(5, 20) == pytest.approx(5.0)


# --- COMPUTE_SCORES (integration) ---

def test_compute_scores_structure_and_ranges():
    annotated = pd.DataFrame({
        "root_id": [1, 2, 3, 4],
        "primary_type": ["A", "A", "A", "A"],
        "nt_type": ["ACH", "ACH", "ACH", "ACH"],
    })
    # one reciprocal pair (1↔2), one one-way (2→3)
    conn = _conn([1, 2, 2], [2, 1, 3], syn=[10, 8, 5])

    result = compute_scores("test", annotated, conn)

    assert result["label"] == "test"
    assert result["N"] == 4
    assert set(result["components"].keys()) == {
        "IDENTIFIABILITY", "TYPE_COHERENCE", "NT_COHERENCE",
        "ANATOMICAL_LOCALITY", "CIRCUIT_RICHNESS",
    }
    assert result["total"] == pytest.approx(sum(result["components"].values()), rel=1e-4)
    assert all(0.0 <= v <= 20.0 for v in result["components"].values())
    assert 0.0 <= result["total"] <= 100.0
    assert result["dominant_nt"] == "ACH"
    assert result["reciprocal_pairs"] == 1
    assert result["components"]["IDENTIFIABILITY"] == pytest.approx(20.0)
    assert result["components"]["NT_COHERENCE"] == pytest.approx(20.0)
    assert result["components"]["CIRCUIT_RICHNESS"] == pytest.approx(5.0)  # min(20, 20*1/4)
