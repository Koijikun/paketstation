"""Tests für das Scoring (synthetische Layer, kein Netzwerk/DB)."""

import numpy as np

from data_loader import _empty_geodataframe, load_bfs_quartiere
from scoring import make_grid, score_grid, top_candidates

SCORE_COLS = [
    "score_pop",
    "score_pt",
    "score_shops",
    "score_competition",
    "score_walkability",
    "score_total",
]


def _minimal_layers():
    """Layer-Dict mit echten Quartieren, aber leeren OSM-Layern."""
    return {
        "public_transport": _empty_geodataframe(),
        "shops": _empty_geodataframe(),
        "parcel_lockers": _empty_geodataframe(),
        "quartiere": load_bfs_quartiere(),
    }


def test_make_grid_basic():
    grid = make_grid(resolution_m=2000)
    assert len(grid) > 0
    assert grid.crs.to_epsg() == 4326
    assert {"grid_id", "lat", "lon", "geometry"}.issubset(grid.columns)


def test_score_grid_columns_and_range():
    scored = score_grid(_minimal_layers(), resolution_m=2000)
    for col in SCORE_COLS:
        assert col in scored.columns
        assert scored[col].between(0, 100).all()


def test_score_total_is_absolute_not_forced_to_100():
    """Absoluter Score: ohne ÖV/Shops darf das Maximum < 100 bleiben."""
    scored = score_grid(_minimal_layers(), resolution_m=2000)
    # Bei leeren pt/shops sind score_pt/score_shops/walkability = 0,
    # daher kann score_total nicht künstlich auf 100 hochskaliert sein.
    assert scored["score_total"].max() < 100
    assert (scored["score_pt"] == 0).all()


def test_top_candidates_rank_and_min_distance():
    scored = score_grid(_minimal_layers(), resolution_m=2000)
    top = top_candidates(scored, n=5, min_distance_m=2000)
    assert len(top) <= 5
    assert list(top["rank"]) == list(range(1, len(top) + 1))
    # absteigend sortiert nach score_total
    assert (np.diff(top["score_total"].to_numpy()) <= 0).all()
