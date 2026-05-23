"""
data_loader.py – Datenbeschaffung von OSM (Overpass API) und BFS

Funktionen:
    fetch_osm(layer)        → GeoDataFrame mit OSM-Punkten
    load_bfs_quartiere()    → GeoDataFrame mit Quartieren + Bevölkerungsdichte
    load_all()              → dict aller Layer
"""

import logging
import time

import geopandas as gpd
import requests
from shapely.geometry import Point

from paketstation.config import (
    BBOX,
    BFS_QUARTIERE,
    CRS_WGS84,
    LOCAL_DATA_FILE,
    OSM_QUERIES,
    OVERPASS_TIMEOUT,
    OVERPASS_URL,
    OVERPASS_USER_AGENT,
    USE_LOCAL_DATA,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# OSM / Overpass
# ---------------------------------------------------------------------------


def fetch_osm(layer: str, retries: int = 3, backoff: float = 5.0) -> gpd.GeoDataFrame:
    """
    Lädt einen OSM-Layer via Overpass API.

    Parameters
    ----------
    layer : str
        Schlüssel aus OSM_QUERIES (z.B. 'public_transport', 'shops', 'parcel_lockers')
    retries : int
        Anzahl Wiederholversuche bei Netzwerkfehlern
    backoff : float
        Wartezeit (Sek.) zwischen Versuchen, wird nach jedem Fehlversuch verdoppelt

    Returns
    -------
    GeoDataFrame (CRS: WGS84) mit Spalten: geometry, osm_id, name, tags…
    """
    if layer not in OSM_QUERIES:
        raise ValueError(f"Unbekannter Layer '{layer}'. Verfügbar: {list(OSM_QUERIES)}")

    query = OSM_QUERIES[layer].format(timeout=OVERPASS_TIMEOUT)
    logger.info(f"Lade OSM-Layer '{layer}' von Overpass API …")

    attempt = 0
    while attempt < retries:
        try:
            resp = requests.post(
                OVERPASS_URL,
                data={"data": query},
                headers={"User-Agent": OVERPASS_USER_AGENT},
                timeout=OVERPASS_TIMEOUT + 10,
            )
            resp.raise_for_status()
            elements = resp.json().get("elements", [])
            logger.info(f"  → {len(elements)} Elemente für '{layer}' erhalten")
            return _elements_to_geodataframe(elements, layer)

        except requests.exceptions.RequestException as e:
            attempt += 1
            logger.warning(f"  Versuch {attempt}/{retries} fehlgeschlagen: {e}")
            if attempt < retries:
                time.sleep(backoff)
                backoff *= 2

    logger.error(f"Overpass API nicht erreichbar für Layer '{layer}'. Gebe leeres GDF zurück.")
    return _empty_geodataframe()


def _elements_to_geodataframe(elements: list, layer: str) -> gpd.GeoDataFrame:
    """Konvertiert Overpass-JSON-Elemente in ein GeoDataFrame."""
    records = []
    for el in elements:
        if el.get("type") != "node":
            continue
        tags = el.get("tags", {})
        records.append(
            {
                "osm_id": el["id"],
                "lat": el["lat"],
                "lon": el["lon"],
                "name": tags.get("name", ""),
                "operator": tags.get("operator", ""),
                "layer": layer,
                "geometry": Point(el["lon"], el["lat"]),
            }
        )

    if not records:
        return _empty_geodataframe()

    gdf = gpd.GeoDataFrame(records, crs=CRS_WGS84)
    return gdf


def _empty_geodataframe() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        columns=["osm_id", "lat", "lon", "name", "operator", "layer", "geometry"],
        geometry="geometry",
        crs=CRS_WGS84,
    )


def load_local_post_data(file_path: str) -> gpd.GeoDataFrame:
    """
    Lädt Paketstationen und Filialen aus der lokalen JSON-Datei.
    Filtert auf 'My Post 24' und 'Post Filiale' innerhalb der BBOX.
    """
    import json
    import os

    if not os.path.exists(file_path):
        logger.error(f"Lokale Datei nicht gefunden: {file_path}")
        return _empty_geodataframe()

    logger.info(f"Lade lokale Post-Daten aus {file_path} ...")
    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Fehler beim Laden der JSON-Datei: {e}")
        return _empty_geodataframe()

    lat_min, lat_max, lon_min, lon_max = BBOX
    records = []

    for item in data:
        name = item.get("name_de", "")
        # Filter: My Post 24 (Automaten) ODER Post Filiale (Filialen)
        if not (name.startswith("My Post 24") or name.startswith("Post Filiale")):
            continue

        coords = item.get("geoCoordinates", {})
        lat = coords.get("latitude")
        lon = coords.get("longitude")

        if lat is None or lon is None:
            continue

        # Geografischer Filter (Zürich BBOX)
        if not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
            continue

        records.append(
            {
                "osm_id": item.get("id", ""),
                "lat": lat,
                "lon": lon,
                "name": name,
                "operator": "Die Post",
                "layer": "parcel_lockers",
                "geometry": Point(lon, lat),
            }
        )

    if not records:
        logger.warning("Keine passenden lokalen Post-Daten im Gebiet gefunden.")
        return _empty_geodataframe()

    gdf = gpd.GeoDataFrame(records, crs=CRS_WGS84)
    logger.info(f"  → {len(gdf)} lokale Post-Standorte geladen.")
    return gdf


# ---------------------------------------------------------------------------
# BFS Quartiere
# ---------------------------------------------------------------------------


def load_bfs_quartiere() -> gpd.GeoDataFrame:
    """
    Erstellt ein GeoDataFrame aus den BFS STATPOP 2022 Quartierdaten.

    Returns
    -------
    GeoDataFrame mit Spalten:
        quartier, einwohner, flaeche_ha, dichte_ew_ha, geometry (Centroid)
    """
    records = []
    for name, lat, lon, einwohner, flaeche_ha in BFS_QUARTIERE:
        records.append(
            {
                "quartier": name,
                "einwohner": einwohner,
                "flaeche_ha": flaeche_ha,
                "dichte_ew_ha": round(einwohner / flaeche_ha, 2),
                "geometry": Point(lon, lat),
            }
        )

    gdf = gpd.GeoDataFrame(records, crs=CRS_WGS84)
    logger.info(f"BFS Quartiere geladen: {len(gdf)} Quartiere")
    return gdf


# ---------------------------------------------------------------------------
# Alle Layer auf einmal laden
# ---------------------------------------------------------------------------


def load_all(
    use_cache: bool = False, use_db: bool = False, engine=None
) -> dict[str, gpd.GeoDataFrame]:
    """
    Lädt alle Datenlayer.

    Parameters
    ----------
    use_cache : bool  – GeoJSON-Cache aus data/ verwenden
    use_db    : bool  – Daten aus PostGIS laden (benötigt engine)
    engine           – SQLAlchemy-Engine (nur bei use_db=True)
    """
    import os

    if use_db and engine is not None:
        from paketstation.db import load_layer

        logger.info("Lade Layer aus PostGIS …")
        layers = {layer: load_layer(layer, engine) for layer in OSM_QUERIES}
        layers["quartiere"] = load_layer("quartiere", engine)
        return layers

    layers = {}
    for layer in OSM_QUERIES:
        # Sonderfall: Lokale Daten für Paketstationen verwenden
        if layer == "parcel_lockers" and USE_LOCAL_DATA:
            layers[layer] = load_local_post_data(LOCAL_DATA_FILE)
            continue

        cache_path = f"data/{layer}.geojson"
        if use_cache and os.path.exists(cache_path):
            logger.info(f"Lade '{layer}' aus Cache: {cache_path}")
            layers[layer] = gpd.read_file(cache_path)
        else:
            layers[layer] = fetch_osm(layer)
            if not layers[layer].empty:
                os.makedirs("data", exist_ok=True)
                layers[layer].to_file(cache_path, driver="GeoJSON")
                logger.info(f"  → Cache gespeichert: {cache_path}")

    layers["quartiere"] = load_bfs_quartiere()
    return layers


# ---------------------------------------------------------------------------
# Hilfsfunktion: Zusammenfassung
# ---------------------------------------------------------------------------


def summarize(layers: dict) -> None:
    """Gibt eine kurze Übersicht der geladenen Layer auf der Konsole aus."""
    print("\n-- Geladene Datenlayer --------------------------")
    for name, gdf in layers.items():
        n = len(gdf)
        crs = gdf.crs.to_epsg() if gdf.crs else "?"
        print(f"  {name:<25} {n:>4} Eintraege  (EPSG:{crs})")
    print("-------------------------------------------------\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    data = load_all(use_cache=False)
    summarize(data)
