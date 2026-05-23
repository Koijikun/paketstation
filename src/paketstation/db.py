"""
db.py – PostgreSQL/PostGIS Verbindung und Schema-Management

Verantwortlichkeiten:
    - Engine / Verbindung aufbauen
    - Schema (Tabellen) erstellen
    - GeoDataFrames lesen und schreiben
    - Hilfsfunktionen für räumliche Abfragen
"""

import json
import logging
import os

import geopandas as gpd
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError

# .env (falls vorhanden) laden – ueberschreibt keine bereits gesetzten Umgebungsvariablen
load_dotenv()

logger = logging.getLogger(__name__)

# Tabellennamen können in SQL nicht als gebundene Parameter übergeben werden.
# Daher gegen eine feste Allowlist prüfen (Schutz gegen SQL-Injection über den
# Tabellen-Parameter). Werte (min_score, limit, n) werden gebunden übergeben.
ALLOWED_TABLES = frozenset(
    {
        "public_transport",
        "shops",
        "parcel_lockers",
        "quartiere",
        "scored_grid",
    }
)


def _validate_table(table: str) -> str:
    """Stellt sicher, dass ein Tabellenname in der Allowlist steht."""
    if table not in ALLOWED_TABLES:
        raise ValueError(f"Unzulässiger Tabellenname '{table}'. Erlaubt: {sorted(ALLOWED_TABLES)}")
    return table


# ---------------------------------------------------------------------------
# Verbindung
# ---------------------------------------------------------------------------


def get_engine(
    host: str | None = None,
    port: int | None = None,
    db: str | None = None,
    user: str | None = None,
    password: str | None = None,
) -> Engine:
    """
    Erstellt eine SQLAlchemy-Engine für PostgreSQL/PostGIS.

    Konfiguration erfolgt über Umgebungsvariablen (bzw. eine .env-Datei).
    Explizit übergebene Argumente haben Vorrang vor den Umgebungsvariablen:
        PG_HOST  (Standard: localhost)
        PG_PORT  (Standard: 5432)
        PG_DB    (Standard: paketstation)
        PG_USER  (Standard: postgres)
        PG_PASSWORD  (kein Standard – muss gesetzt werden, falls erforderlich)

    Es gibt bewusst KEIN hartkodiertes Standard-Passwort. Lege ein Passwort
    in der .env-Datei (PG_PASSWORD=…) oder als Umgebungsvariable ab.

    Returns
    -------
    sqlalchemy.Engine
    """
    host = host or os.getenv("PG_HOST", "localhost")
    port = int(port if port is not None else os.getenv("PG_PORT", "5432"))
    db = db or os.getenv("PG_DB", "paketstation")
    user = user or os.getenv("PG_USER", "postgres")
    password = password if password is not None else os.getenv("PG_PASSWORD")

    # URL.create kodiert Sonderzeichen in User/Passwort korrekt (z.B. @ : /)
    url = URL.create(
        drivername="postgresql+psycopg2",
        username=user or None,
        password=password or None,
        host=host,
        port=port,
        database=db,
    )
    engine = create_engine(url, pool_pre_ping=True)
    logger.info(f"DB-Engine erstellt: {host}:{port}/{db}")
    return engine


def test_connection(engine: Engine) -> bool:
    """Prüft ob die Datenbankverbindung funktioniert."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT PostGIS_Version();"))
        logger.info("PostGIS-Verbindung OK")
        return True
    except OperationalError as e:
        logger.error(f"Verbindung fehlgeschlagen: {e}")
        return False


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
-- PostGIS-Erweiterung (falls noch nicht aktiv)
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- ÖV-Haltestellen
CREATE TABLE IF NOT EXISTS public_transport (
    id          SERIAL PRIMARY KEY,
    osm_id      TEXT,
    lat         NUMERIC,
    lon         NUMERIC,
    name        TEXT,
    operator    TEXT,
    layer       TEXT,
    geometry    GEOMETRY(Point, 4326)
);

-- Supermärkte / Convenience
CREATE TABLE IF NOT EXISTS shops (
    id          SERIAL PRIMARY KEY,
    osm_id      TEXT,
    lat         NUMERIC,
    lon         NUMERIC,
    name        TEXT,
    operator    TEXT,
    layer       TEXT,
    geometry    GEOMETRY(Point, 4326)
);

-- Bestehende Paketstationen
CREATE TABLE IF NOT EXISTS parcel_lockers (
    id          SERIAL PRIMARY KEY,
    osm_id      TEXT,
    lat         NUMERIC,
    lon         NUMERIC,
    name        TEXT,
    operator    TEXT,
    layer       TEXT,
    geometry    GEOMETRY(Point, 4326)
);

-- BFS Quartiere (Centroids mit Bevölkerungsdaten)
CREATE TABLE IF NOT EXISTS quartiere (
    id              SERIAL PRIMARY KEY,
    quartier        TEXT NOT NULL,
    einwohner       INTEGER,
    flaeche_ha      NUMERIC,
    dichte_ew_ha    NUMERIC,
    geometry        GEOMETRY(Point, 4326)
);

-- Bewertetes Analysegitter
CREATE TABLE IF NOT EXISTS scored_grid (
    id                    SERIAL PRIMARY KEY,
    grid_id               INTEGER,
    lat                   NUMERIC,
    lon                   NUMERIC,
    score_total           NUMERIC,
    score_pop             NUMERIC,
    score_pt              NUMERIC,
    score_shops           NUMERIC,
    score_competition     NUMERIC,
    score_walkability     NUMERIC,
    nearest_quartier      TEXT,
    pt_count_400m         INTEGER,
    shop_count_600m       INTEGER,
    nearest_station_m     INTEGER,
    geometry              GEOMETRY(Point, 4326)
);

-- Räumliche Indizes für schnelle Abfragen
CREATE INDEX IF NOT EXISTS idx_pt_geom        ON public_transport  USING GIST(geometry);
CREATE INDEX IF NOT EXISTS idx_shops_geom     ON shops             USING GIST(geometry);
CREATE INDEX IF NOT EXISTS idx_lockers_geom   ON parcel_lockers    USING GIST(geometry);
CREATE INDEX IF NOT EXISTS idx_quartiere_geom ON quartiere         USING GIST(geometry);
CREATE INDEX IF NOT EXISTS idx_grid_geom      ON scored_grid       USING GIST(geometry);
CREATE INDEX IF NOT EXISTS idx_grid_score     ON scored_grid       (score_total DESC);
"""


def create_schema(engine: Engine) -> None:
    """Erstellt alle Tabellen und räumlichen Indizes (idempotent)."""
    with engine.begin() as conn:
        conn.execute(text(SCHEMA_SQL))
    logger.info("Datenbank-Schema erstellt / verifiziert")


# ---------------------------------------------------------------------------
# Schreiben
# ---------------------------------------------------------------------------


def save_layer(
    gdf: gpd.GeoDataFrame,
    table: str,
    engine: Engine,
    if_exists: str = "replace",
) -> None:
    """
    Schreibt ein GeoDataFrame in eine PostGIS-Tabelle.
    Bei 'replace' wird die Tabelle geleert (TRUNCATE), aber das Schema
    (Primary Keys, Indizes) bleibt erhalten.
    """
    table = _validate_table(table)
    if gdf is None or gdf.empty:
        logger.warning(f"  Layer '{table}' ist leer – wird übersprungen")
        return

    # Nur relevante Spalten + geometry behalten
    keep = [c for c in gdf.columns if c not in ["index", "id"]]
    gdf = gdf[keep].copy()

    if if_exists == "replace":
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))
        if_exists = "append"

    gdf.to_postgis(table, engine, if_exists=if_exists, index=False)
    logger.info(f"  → {len(gdf):>4} Zeilen in Tabelle '{table}' gespeichert")


def save_all_layers(layers: dict, engine: Engine) -> None:
    """Schreibt alle Datenlayer in die Datenbank."""
    logger.info("Schreibe Layer in PostGIS …")
    for name, gdf in layers.items():
        save_layer(gdf, name, engine)


def save_scored_grid(scored: gpd.GeoDataFrame, engine: Engine) -> None:
    """Schreibt das bewertete Grid in die Datenbank."""
    logger.info("Schreibe scored_grid in PostGIS …")
    save_layer(scored, "scored_grid", engine)


# ---------------------------------------------------------------------------
# Lesen
# ---------------------------------------------------------------------------


def load_layer(table: str, engine: Engine) -> gpd.GeoDataFrame:
    """
    Liest eine PostGIS-Tabelle (aus der Allowlist) als GeoDataFrame.

    Parameters
    ----------
    table  : Tabellenname (muss in ALLOWED_TABLES stehen)
    engine : SQLAlchemy-Engine
    """
    table = _validate_table(table)
    # Tabellenname über Allowlist abgesichert – sichere Interpolation.
    gdf = gpd.read_postgis(f"SELECT * FROM {table}", engine, geom_col="geometry")
    logger.info(f"  Gelesen: {len(gdf)} Zeilen aus '{table}'")
    return gdf


def load_top_candidates(engine: Engine, n: int = 10) -> gpd.GeoDataFrame:
    """Liest die Top-N Rasterpunkte nach score_total."""
    sql = text("""
        SELECT *, ROW_NUMBER() OVER (ORDER BY score_total DESC) AS rank
        FROM scored_grid
        ORDER BY score_total DESC
        LIMIT :n
    """)
    return gpd.read_postgis(sql, engine, geom_col="geometry", params={"n": int(n)})


def load_geojson_for_api(
    table: str,
    engine: Engine,
    min_score: float = 0,
    limit: int = 5000,
) -> str:
    """
    Gibt eine GeoJSON FeatureCollection als String zurück
    (direkt verwendbar in der Leaflet-Karte / FastAPI).
    """
    table = _validate_table(table)
    params = {"limit": int(limit)}
    # Score-Filter nur für Tabellen mit score_total-Spalte (gebundener Parameter)
    score_filter = ""
    if table == "scored_grid":
        score_filter = "AND score_total >= :min_score"
        params["min_score"] = float(min_score)

    sql = text(f"""
        SELECT json_build_object(
            'type', 'FeatureCollection',
            'features', json_agg(
                json_build_object(
                    'type', 'Feature',
                    'geometry', ST_AsGeoJSON(geometry)::json,
                    'properties', to_jsonb(t) - 'geometry'
                )
            )
        ) AS geojson
        FROM (
            SELECT * FROM {table}
            WHERE 1=1 {score_filter}
            ORDER BY id
            LIMIT :limit
        ) t
    """)
    with engine.connect() as conn:
        result = conn.execute(sql, params).fetchone()
        if result and result[0]:
            # Falls features null ist (0 Zeilen), leere Collection zurückgeben
            data = result[0]
            if data.get("features") is None:
                return '{"type":"FeatureCollection","features":[]}'
            return json.dumps(data)
        return '{"type":"FeatureCollection","features":[]}'


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def table_info(engine: Engine) -> pd.DataFrame:
    """Gibt eine Übersicht aller Tabellen mit Zeilenanzahl zurück."""
    sql = """
        SELECT
            t.table_name,
            s.n_live_tup AS rows,
            pg_size_pretty(pg_total_relation_size(quote_ident(t.table_name))) AS size
        FROM information_schema.tables t
        LEFT JOIN pg_stat_user_tables s ON s.relname = t.table_name
        WHERE t.table_schema = 'public'
        AND t.table_type = 'BASE TABLE'
        ORDER BY t.table_name;
    """
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    engine = get_engine()
    if test_connection(engine):
        create_schema(engine)
        print(table_info(engine).to_string(index=False))
