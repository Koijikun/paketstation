"""Tests für das AHP-Modul und die abgeleiteten Default-Gewichte."""

import numpy as np
import pytest

from paketstation.ahp import (
    build_matrix,
    consistency_ratio,
    derive_weights,
    priority_vector,
)
from paketstation.config import (
    AHP_CONSISTENCY_RATIO,
    AHP_FACTORS,
    AHP_JUDGMENTS,
    DEFAULT_WEIGHTS,
)


def test_build_matrix_reciprocal_and_diagonal():
    m = build_matrix(["a", "b", "c"], {("a", "b"): 3, ("a", "c"): 5, ("b", "c"): 2})
    assert np.allclose(np.diag(m), 1.0)
    assert m[0, 1] == 3 and m[1, 0] == pytest.approx(1 / 3)
    assert m[2, 0] == pytest.approx(1 / 5)


def test_build_matrix_requires_all_pairs():
    with pytest.raises(ValueError):
        build_matrix(["a", "b", "c"], {("a", "b"): 3})  # fehlende Vergleiche


def test_priority_vector_sums_to_one():
    w = priority_vector(
        build_matrix(["a", "b", "c"], {("a", "b"): 3, ("a", "c"): 5, ("b", "c"): 2})
    )
    assert w.sum() == pytest.approx(1.0)


def test_perfectly_consistent_matrix_has_zero_cr():
    # Aus einem Verhältnisvektor gebaute Matrix ist perfekt konsistent -> CR ~ 0
    v = np.array([0.5, 0.3, 0.2])
    m = np.outer(v, 1.0 / v)
    assert consistency_ratio(m) == pytest.approx(0.0, abs=1e-9)
    assert np.allclose(priority_vector(m), v)


def test_derive_weights_consistent():
    weights, cr = derive_weights(AHP_FACTORS, AHP_JUDGMENTS)
    assert sum(weights.values()) == pytest.approx(1.0)
    assert cr < 0.10
    # ÖV (Frequenz) ist laut H2 der dominante Faktor
    assert weights["public_transport"] == max(weights.values())


def test_config_default_weights():
    assert set(DEFAULT_WEIGHTS) == {
        "population",
        "public_transport",
        "shops",
        "competition",
        "walkability",
    }
    assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)
    assert AHP_CONSISTENCY_RATIO < 0.10
    # ÖV dominant; Gap (competition) gleichauf mit Bevölkerung (Standortziel)
    assert DEFAULT_WEIGHTS["public_transport"] == pytest.approx(0.375, abs=0.02)
    assert DEFAULT_WEIGHTS["competition"] == pytest.approx(0.215, abs=0.02)
    assert DEFAULT_WEIGHTS["competition"] == pytest.approx(DEFAULT_WEIGHTS["population"], abs=0.01)
