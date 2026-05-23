"""
scoring.py – Rastergenerierung und Scoring-Modell

Pipeline:
    1. make_grid()         → Analysegitter über Zürich
    2. ScoringEngine       → berechnet 5 Teilscores + Gesamtscore pro Rasterpunkt
    3. score_grid()        → verknüpft Grid mit allen Layern → scored GeoDataFrame
    4. top_candidates()    → filtert und sortiert Top-Standorte
"""

import logging

import geopandas as gpd
import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import Point

from paketstation.config import (
    BBOX,
    CRS_METRIC,
    CRS_WGS84,
    DEFAULT_WEIGHTS,
    GRID_RESOLUTION_M,
    RADIUS_COMPETE_M,
    RADIUS_PT_M,
    RADIUS_SHOP_M,
    RADIUS_WALK_M,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Analysegitter erzeugen
# ---------------------------------------------------------------------------


def make_grid(resolution_m: int = GRID_RESOLUTION_M) -> gpd.GeoDataFrame:
    """
    Erzeugt ein gleichmässiges Punktgitter über das Untersuchungsgebiet.

    Das Gitter wird in metrischen Koordinaten (CH1903+ LV95) aufgebaut,
    damit der Abstand in Metern korrekt ist, und dann zurück nach WGS84
    transformiert.

    Parameters
    ----------
    resolution_m : int
        Abstand zwischen Rasterpunkten in Metern

    Returns
    -------
    GeoDataFrame (CRS: WGS84) mit Spalten: grid_id, geometry
    """
    lat_min, lat_max, lon_min, lon_max = BBOX

    # Eckpunkte der Bounding Box nach metrisch projizieren
    corners = gpd.GeoDataFrame(
        geometry=[
            Point(lon_min, lat_min),
            Point(lon_max, lat_max),
        ],
        crs=CRS_WGS84,
    ).to_crs(CRS_METRIC)

    x_min, y_min = corners.geometry[0].x, corners.geometry[0].y
    x_max, y_max = corners.geometry[1].x, corners.geometry[1].y

    xs = np.arange(x_min, x_max, resolution_m)
    ys = np.arange(y_min, y_max, resolution_m)

    points = [Point(x, y) for x in xs for y in ys]

    grid_metric = gpd.GeoDataFrame(
        {"grid_id": range(len(points)), "geometry": points},
        crs=CRS_METRIC,
    )
    grid_wgs84 = grid_metric.to_crs(CRS_WGS84)
    grid_wgs84["lat"] = grid_wgs84.geometry.y
    grid_wgs84["lon"] = grid_wgs84.geometry.x

    logger.info(f"Analysegitter: {len(grid_wgs84)} Punkte ({resolution_m}m Auflösung)")
    return grid_wgs84


# ---------------------------------------------------------------------------
# 2. Scoring Engine
# ---------------------------------------------------------------------------


class ScoringEngine:
    """
    Berechnet Standortscores auf Basis räumlicher Nachbarschaftsanalysen.

    Alle Distanzberechnungen erfolgen im metrischen CRS (CH1903+/LV95),
    um Verzerrungen durch Längen-/Breitengradkoordinaten zu vermeiden.

    Attributes
    ----------
    weights : dict
        Gewichtung der fünf Faktoren (Werte 0–5)
    """

    def __init__(self, weights: dict = None):
        self.weights = weights or DEFAULT_WEIGHTS.copy()
        self._trees = {}  # cKDTree pro Layer (lazy gebaut)

    def _get_coords(self, gdf: gpd.GeoDataFrame) -> np.ndarray:
        """Gibt (x, y)-Koordinaten im metrischen CRS zurück."""
        projected = gdf.to_crs(CRS_METRIC)
        return np.column_stack([projected.geometry.x, projected.geometry.y])

    def _build_tree(self, name: str, gdf: gpd.GeoDataFrame) -> cKDTree | None:
        """Baut einen KD-Baum für schnelle Nachbarschaftsabfragen."""
        if gdf is None or gdf.empty:
            logger.warning(f"Layer '{name}' ist leer – dieser Faktor wird auf 0 gesetzt.")
            return None
        coords = self._get_coords(gdf)
        return cKDTree(coords)

    def fit(self, layers: dict) -> None:
        """
        Bereitet die Scoring-Engine mit allen Layern vor.
        Baut KD-Bäume für schnelle räumliche Abfragen.

        Parameters
        ----------
        layers : dict
            Enthält GeoDataFrames für 'public_transport', 'shops',
            'parcel_lockers', 'quartiere'
        """
        self._layers = layers
        self._trees["pt"] = self._build_tree("public_transport", layers.get("public_transport"))
        self._trees["shops"] = self._build_tree("shops", layers.get("shops"))
        self._trees["compete"] = self._build_tree("parcel_lockers", layers.get("parcel_lockers"))

        # Bevölkerungsdichte: KD-Baum der Quartier-Centroids + Dichte-Array
        q = layers["quartiere"].to_crs(CRS_METRIC)
        self._q_coords = np.column_stack([q.geometry.x, q.geometry.y])
        self._q_density = q["dichte_ew_ha"].values
        self._q_names = q["quartier"].values
        logger.info("ScoringEngine bereit.")

    def _count_in_radius(self, tree: cKDTree | None, xy: np.ndarray, radius_m: float) -> np.ndarray:
        """Zählt Punkte im gegebenen Radius für alle Grid-Punkte (vektorisiert)."""
        if tree is None:
            return np.zeros(len(xy), dtype=int)
        indices = tree.query_ball_point(xy, r=radius_m)
        return np.array([len(ix) for ix in indices])

    def _min_dist(self, tree: cKDTree | None, xy: np.ndarray) -> np.ndarray:
        """Berechnet Distanz zum nächsten Nachbarn für alle Grid-Punkte."""
        if tree is None:
            return np.full(len(xy), np.inf)
        dists, _ = tree.query(xy, k=1)
        return dists

    def _nearest_quartier(self, xy: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Gibt Bevölkerungsdichte und Namen des nächsten Quartiers zurück."""
        q_tree = cKDTree(self._q_coords)
        _, idx = q_tree.query(xy, k=1)
        return self._q_density[idx], self._q_names[idx]

    def _normalize(self, arr: np.ndarray, max_val: float) -> np.ndarray:
        """Normalisiert ein Array auf [0, 100]."""
        return np.clip(arr / max_val, 0, 1) * 100

    def transform(self, grid: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """
        Berechnet alle Teilscores und den Gesamtscore für jeden Rasterpunkt.

        Parameters
        ----------
        grid : GeoDataFrame
            Output von make_grid()

        Returns
        -------
        GeoDataFrame mit zusätzlichen Spalten:
            score_pop, score_pt, score_shops, score_competition,
            score_walkability, score_total (alle 0–100),
            nearest_quartier
        """
        logger.info(f"Berechne Scores für {len(grid)} Rasterpunkte …")

        # Alle Grid-Punkte metrisch projizieren
        grid_m = grid.to_crs(CRS_METRIC)
        xy = np.column_stack([grid_m.geometry.x, grid_m.geometry.y])

        result = grid.copy()

        # ── 1. Bevölkerungsdichte ────────────────────────────────────────
        density, q_names = self._nearest_quartier(xy)
        # Max. Dichte in Zürich ≈ 200 EW/ha (Innenstadt)
        result["score_pop"] = self._normalize(density, max_val=200)
        result["nearest_quartier"] = q_names

        # ── 2. ÖV-Erreichbarkeit ────────────────────────────────────────
        pt_count = self._count_in_radius(self._trees["pt"], xy, RADIUS_PT_M)
        # Ab 20 Haltestellen in 400m → maximaler Score
        result["score_pt"] = self._normalize(pt_count, max_val=20)
        result["pt_count_400m"] = pt_count

        # ── 3. Nahversorgung / Supermärkte ──────────────────────────────
        shop_count = self._count_in_radius(self._trees["shops"], xy, RADIUS_SHOP_M)
        result["score_shops"] = self._normalize(shop_count, max_val=6)
        result["shop_count_600m"] = shop_count

        # ── 4. Konkurrenz (invertiert) ──────────────────────────────────
        # Grosse Distanz zu bestehender Station = hoher Score (positiv)
        compete_dist = self._min_dist(self._trees["compete"], xy)
        # Distanz ≥ RADIUS_COMPETE_M → voller Score; direkte Nachbarschaft → 0
        compete_dist_clipped = np.clip(compete_dist, 0, RADIUS_COMPETE_M)
        result["score_competition"] = self._normalize(
            compete_dist_clipped, max_val=RADIUS_COMPETE_M
        )
        # inf (kein Konkurrent vorhanden) → -1 als Sentinel
        finite_dist = np.where(np.isinf(compete_dist), -1, np.round(compete_dist))
        result["nearest_station_m"] = finite_dist.astype(int)

        # ── 5. Fusswegnetz-Proxy ─────────────────────────────────────────
        # Kombination: ÖV + Shops in engem Radius als Proxy für Fussgängerfrequenz
        all_poi = [
            self._trees["pt"],
            self._trees["shops"],
        ]
        poi_count = sum(
            self._count_in_radius(t, xy, RADIUS_WALK_M) for t in all_poi if t is not None
        )
        result["score_walkability"] = self._normalize(poi_count, max_val=15)

        # ── Gesamtscore (gewichteter Mittelwert) ─────────────────────────
        # ABSOLUTER Score: gewichteter Mittel der Teilscores (jeweils 0–100),
        # daher selbst direkt in [0, 100]. Bewusst KEINE Re-Normalisierung auf
        # das eigene Maximum – so sind Werte zwischen Läufen/Gewichtungen
        # vergleichbar und identisch zur Berechnung im Frontend (api.py) sowie
        # in den CSV-/GeoJSON-Ausgaben (Konsistenz Karte = CSV = DB).
        w = self.weights
        total_weight = sum(w.values())

        if total_weight == 0:
            result["score_total"] = 0.0
        else:
            result["score_total"] = (
                result["score_pop"] * w["population"]
                + result["score_pt"] * w["public_transport"]
                + result["score_shops"] * w["shops"]
                + result["score_competition"] * w["competition"]
                + result["score_walkability"] * w["walkability"]
            ) / total_weight
            result["score_total"] = result["score_total"].round(1)

        logger.info(
            f"Scoring abgeschlossen. "
            f"Max: {result['score_total'].max():.1f} | "
            f"Median: {result['score_total'].median():.1f}"
        )
        return result


# ---------------------------------------------------------------------------
# 3. Hauptfunktion: Grid + Scoring
# ---------------------------------------------------------------------------


def score_grid(
    layers: dict,
    resolution_m: int = GRID_RESOLUTION_M,
    weights: dict = None,
) -> gpd.GeoDataFrame:
    """
    Erstellt das Analysegitter und berechnet alle Scores.

    Parameters
    ----------
    layers : dict
        Output von data_loader.load_all()
    resolution_m : int
        Rasterauflösung in Metern
    weights : dict, optional
        Gewichtung der Faktoren (überschreibt DEFAULT_WEIGHTS)

    Returns
    -------
    Vollständig gescotertes GeoDataFrame
    """
    grid = make_grid(resolution_m)
    engine = ScoringEngine(weights=weights)
    engine.fit(layers)
    return engine.transform(grid)


# ---------------------------------------------------------------------------
# 4. Top-Kandidaten
# ---------------------------------------------------------------------------


def top_candidates(
    scored: gpd.GeoDataFrame,
    n: int = 10,
    min_distance_m: float = 500,
) -> gpd.GeoDataFrame:
    """
    Extrahiert die n besten Standorte mit Mindestabstand zwischen Kandidaten
    (vermeidet Cluster von sehr nahe beieinanderliegenden Top-Punkten).

    Parameters
    ----------
    scored : GeoDataFrame
        Output von score_grid()
    n : int
        Anzahl gewünschter Top-Kandidaten
    min_distance_m : float
        Mindestabstand zwischen zwei Kandidaten in Metern

    Returns
    -------
    GeoDataFrame mit den n besten Standorten, sortiert nach score_total
    """
    sorted_gdf = scored.sort_values("score_total", ascending=False).reset_index(drop=True)
    sorted_metric = sorted_gdf.to_crs(CRS_METRIC)

    selected = []
    selected_coords = []

    for idx, row in sorted_metric.iterrows():
        pt = np.array([row.geometry.x, row.geometry.y])

        # Mindestabstand zu allen bereits gewählten Kandidaten prüfen
        too_close = False
        for prev in selected_coords:
            if np.linalg.norm(pt - prev) < min_distance_m:
                too_close = True
                break

        if not too_close:
            selected.append(idx)
            selected_coords.append(pt)

        if len(selected) >= n:
            break

    top = sorted_gdf.loc[selected].reset_index(drop=True)
    top.insert(0, "rank", range(1, len(top) + 1))
    logger.info(f"Top {len(top)} Kandidaten selektiert (min. {min_distance_m}m Abstand)")
    return top


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    from paketstation.data_loader import load_all, summarize

    layers = load_all(use_cache=True)
    summarize(layers)

    scored = score_grid(layers)
    top = top_candidates(scored, n=10)

    print("\n── Top 10 Standorte ─────────────────────────────")
    print(
        top[
            [
                "rank",
                "nearest_quartier",
                "score_total",
                "score_pop",
                "score_pt",
                "score_shops",
                "score_competition",
                "score_walkability",
                "nearest_station_m",
            ]
        ].to_string(index=False)
    )
