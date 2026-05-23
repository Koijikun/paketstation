"""Tests für data_loader (ohne Netzwerk/DB)."""

from paketstation.data_loader import _empty_geodataframe, load_bfs_quartiere


def test_empty_geodataframe_has_expected_columns():
    gdf = _empty_geodataframe()
    assert gdf.empty
    for col in ["osm_id", "lat", "lon", "name", "operator", "layer", "geometry"]:
        assert col in gdf.columns


def test_bfs_quartiere_density_and_crs():
    gdf = load_bfs_quartiere()
    assert len(gdf) > 0
    assert gdf.crs.to_epsg() == 4326
    # Dichte = Einwohner / Fläche (gerundet)
    row = gdf.iloc[0]
    expected = round(row["einwohner"] / row["flaeche_ha"], 2)
    assert row["dichte_ew_ha"] == expected
    # alle Dichten positiv
    assert (gdf["dichte_ew_ha"] > 0).all()
