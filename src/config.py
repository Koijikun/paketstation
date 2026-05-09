"""
config.py – Zentrale Konfiguration für die Paketstation-Standortanalyse Zürich
"""

# ---------------------------------------------------------------------------
# Untersuchungsgebiet
# ---------------------------------------------------------------------------
CITY_NAME = "Zürich, Switzerland"

# Bounding Box Zürich (lat_min, lat_max, lon_min, lon_max)
BBOX = (47.320, 47.435, 8.460, 8.625)

# Koordinaten-Referenzsystem (metrisch, für Distanzberechnungen)
CRS_METRIC = "EPSG:2056"   # CH1903+ / LV95 (Schweizer Landeskoordinaten)
CRS_WGS84  = "EPSG:4326"

# ---------------------------------------------------------------------------
# Analyse-Raster
# ---------------------------------------------------------------------------
GRID_RESOLUTION_M = 300   # Rasterpunkt-Abstand in Metern

# ---------------------------------------------------------------------------
# Scoring-Radien (Meter)
# ---------------------------------------------------------------------------
RADIUS_PT_M      = 400   # ÖV-Haltestellen
RADIUS_SHOP_M    = 600   # Supermärkte / Convenience
RADIUS_COMPETE_M = 500   # Bestehende Paketstationen (Konkurrenz)
RADIUS_WALK_M    = 300   # Fusswegnetz-Proxy (allg. POI-Dichte)

# ---------------------------------------------------------------------------
# Scoring-Gewichte (können später per CLI überschrieben werden)
# ---------------------------------------------------------------------------
DEFAULT_WEIGHTS = {
    "population":   3,   # Bevölkerungsdichte
    "public_transport": 3,   # ÖV-Erreichbarkeit
    "shops":        2,   # Nahversorgung
    "competition":  2,   # Konkurrenz (wird invertiert)
    "walkability":  2,   # Fusswegnetz
}

# ---------------------------------------------------------------------------
# OSM Overpass – Abfragen
# ---------------------------------------------------------------------------
OVERPASS_URL          = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT      = 60   # Sekunden
OVERPASS_USER_AGENT   = "PaketstationAnalyseZurich/1.0 (contact: user@example.com)" # Identifiziert die App bei OSM

# ---------------------------------------------------------------------------
# Lokale Daten (Post CH)
# ---------------------------------------------------------------------------
LOCAL_DATA_FILE       = "data/postoneweb-locations.json"
USE_LOCAL_DATA        = True  # Ersetzt OSM 'parcel_lockers' durch lokale JSON-Daten

OSM_QUERIES = {
    "public_transport": """
        [out:json][timeout:{timeout}];
        area["name"="Zürich"]["admin_level"="8"]->.a;
        (
            node["public_transport"="stop_position"](area.a);
            node["highway"="bus_stop"](area.a);
            node["railway"="tram_stop"](area.a);
        );
        out body;
    """,
    "shops": """
        [out:json][timeout:{timeout}];
        area["name"="Zürich"]["admin_level"="8"]->.a;
        (
            node["shop"="supermarket"](area.a);
            node["shop"="convenience"](area.a);
            node["shop"="department_store"](area.a);
            node["amenity"="marketplace"](area.a);
        );
        out body;
    """,
    "parcel_lockers": """
        [out:json][timeout:{timeout}];
        area["name"="Zürich"]["admin_level"="8"]->.a;
        node["amenity"="parcel_locker"](area.a);
        out body;
    """,
}

# ---------------------------------------------------------------------------
# BFS STATPOP 2022 – Bevölkerung nach Stadtquartier
# Quelle: Statistik Stadt Zürich, STATPOP 2022
# Felder: (Name, lat, lon, Einwohner, Fläche_ha)
# ---------------------------------------------------------------------------
BFS_QUARTIERE = [
    ("Rathaus",                47.3736, 8.5425,  1510,  21),
    ("Hochschulen",            47.3770, 8.5494,  1640,  35),
    ("Lindenhügel",            47.3694, 8.5452,  2180,  27),
    ("Hochstrasse",            47.3705, 8.5573,  2540,  32),
    ("Mühlebach",              47.3624, 8.5515,  8720,  48),
    ("Weinegg",                47.3585, 8.5615,  6340,  82),
    ("Fluntern",               47.3826, 8.5660,  6510, 185),
    ("Hottingen",              47.3760, 8.5698, 10730,  96),
    ("Hirslanden",             47.3684, 8.5784, 10420, 161),
    ("Witikon",                47.3628, 8.5983, 12540, 422),
    ("Seefeld",                47.3566, 8.5544, 12800,  98),
    ("Mühlebachquartier",      47.3574, 8.5466,  8950,  54),
    ("Enge",                   47.3617, 8.5305,  8350,  68),
    ("Wollishofen",            47.3427, 8.5348, 18920, 235),
    ("Leimbach",               47.3223, 8.5174,  5840, 262),
    ("Friesenberg",            47.3488, 8.5032, 12640, 273),
    ("Alt-Wiedikon",           47.3601, 8.5158, 15740, 160),
    ("Sihlfeld",               47.3672, 8.5135, 17820, 117),
    ("Langstrasse",            47.3763, 8.5250, 14950,  80),
    ("Werd",                   47.3718, 8.5262,  9840,  51),
    ("Gewerbeschule",          47.3790, 8.5340,  5650,  37),
    ("Hardau",                 47.3818, 8.5140, 10820, 122),
    ("Escher Wyss",            47.3894, 8.5163,  4350, 134),
    ("Wipkingen",              47.3906, 8.5280, 14460, 151),
    ("Unterstrass",            47.3908, 8.5421, 16740, 143),
    ("Oberstrass",             47.3946, 8.5487, 10580, 151),
    ("Höngg",                  47.4003, 8.4955, 18960, 473),
    ("Albisrieden",            47.3793, 8.4840, 17540, 224),
    ("Altstetten",             47.3903, 8.4816, 36820, 524),
    ("Schwamendingen-Mitte",   47.4110, 8.5567, 10840, 141),
    ("Hirzenbach",             47.4108, 8.5760,  9520, 168),
    ("Saatlen",                47.4059, 8.5720,  6840, 144),
    ("Milchbuck",              47.4000, 8.5503,  7620,  78),
    ("Seebach",                47.4249, 8.5334, 17840, 362),
    ("Affoltern",              47.4222, 8.5100, 16540, 350),
    ("Oerlikon",               47.4107, 8.5440, 14780, 142),
    ("Schwamendingerplatz",    47.4058, 8.5625,  5940,  67),
    ("Albisrieden-Nord",       47.3855, 8.4840,  8430, 120),
]

# ---------------------------------------------------------------------------
# Output-Pfade
# ---------------------------------------------------------------------------
OUTPUT_DIR         = "output"
OUTPUT_GEOJSON     = "output/scored_grid.geojson"
OUTPUT_CSV         = "output/scored_grid.csv"
OUTPUT_MAP_HTML    = "output/karte.html"
OUTPUT_TOP_CSV     = "output/top_standorte.csv"
