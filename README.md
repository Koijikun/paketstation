# Paketstation Standort-Analyse Zürich

Datenbasiertes Scoring-Modell zur Identifikation optimaler Paketstation-Standorte
in der Stadt Zürich. Kombination aus BFS STATPOP 2022 und OpenStreetMap,
mit PostGIS-Backend und FastAPI-basierter Live-Karte.

---

## Projektstruktur

```
paketstation/
├── main.py                  # Einstiegspunkt (CLI)
├── requirements.txt
├── src/
│   ├── config.py            # Konstanten, Gewichte, BFS-Daten, OSM-Queries
│   ├── data_loader.py       # Overpass API + BFS + PostGIS-Lesezugriff
│   ├── scoring.py           # Rastergenerierung + ScoringEngine (cKDTree)
│   ├── visualizer.py        # Folium-Karte (statische HTML-Ausgabe)
│   ├── db.py                # PostGIS: Verbindung, Schema, Lesen/Schreiben
│   └── api.py               # FastAPI: GeoJSON-Endpoints + Live-Karte
├── data/                    # GeoJSON-Cache (auto-generiert)
└── output/                  # Ausgaben (auto-generiert)
    ├── karte.html
    ├── scored_grid.geojson
    └── top_standorte.csv
```

---

## Setup-Anleitung

### 1. PostgreSQL installieren

**macOS (Homebrew):**
```bash
brew install postgresql@16
brew services start postgresql@16
```

**Ubuntu / Debian:**
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

**Windows:**
Installer von https://www.postgresql.org/download/windows/ herunterladen.
PostgreSQL 16 auswählen. Den Port während der Installation notieren (Standard: 5432).

---

### 2. PostGIS installieren

**macOS:**
```bash
brew install postgis
```

**Ubuntu / Debian:**
```bash
sudo apt install postgis postgresql-16-postgis-3
```

**Windows:**
Nach der PostgreSQL-Installation öffnet sich Stack Builder automatisch.
Navigiere zu **Spatial Extensions** → **PostGIS** (Version muss zur PostgreSQL-Version passen) → installieren.

> Falls Stack Builder PostGIS nicht findet: Direktdownload unter https://postgis.net/windows_downloads

---

### 3. Datenbank erstellen

**psql-Shell öffnen:**

- Windows: "SQL Shell (psql)" im Startmenü suchen. Bei den Verbindungsprompts jeweils Enter drücken (Defaults übernehmen), nur beim Port die eigene Portnummer eingeben. Erst wenn `postgres=#` erscheint, Befehle eingeben.
- macOS / Linux: `psql -U postgres` im Terminal

**In der psql-Shell:**
```sql
CREATE DATABASE paketstation;
\c paketstation
CREATE EXTENSION postgis;
CREATE EXTENSION postgis_topology;
\q
```

Verbindung testen:
```bash
psql -U postgres -p DEIN_PORT -d paketstation -c "SELECT PostGIS_Version();"
# Erwartete Ausgabe: z.B. "3.4 USE_GEOS=1 ..."
```

---

### 4. Python-Version setzen (pyenv)

Das Projekt benötigt Python 3.11 oder neuer. Falls pyenv verwendet wird:

```bash
pyenv install 3.11.9
cd pfad/zu/paketstation
pyenv local 3.11.9
```

---

### 5. Virtual Environment erstellen

**macOS / Linux:**
```bash
cd pfad/zu/paketstation
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Windows (CMD):**
```cmd
cd pfad\zu\paketstation
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Das `(venv)` am Zeilenanfang zeigt an, dass das venv aktiv ist.
Bei jeder neuen Sitzung muss das venv erneut aktiviert werden (`venv\Scripts\activate`).

---

### 6. Umgebungsvariablen setzen

Standardmässig verbindet sich die App mit Port `5432`. Bei abweichendem Port:

**macOS / Linux:**
```bash
export PG_PORT=DEIN_PORT
export PG_PASSWORD=DEIN_PASSWORT
```

**Windows (CMD):**
```cmd
set PG_PORT=DEIN_PORT
set PG_PASSWORD=DEIN_PASSWORT
```

Alle verfügbaren Variablen: `PG_HOST`, `PG_PORT`, `PG_DB`, `PG_USER`, `PG_PASSWORD`

Alternativ: Standardwerte direkt in `src/db.py` in der Funktion `get_engine()` anpassen.

---

### 7. Erster Lauf

```bash
python main.py --db
```

Lädt OSM-Daten live von Overpass, berechnet das Scoring, schreibt alles in PostGIS
und startet den API-Server.

- Karte: **http://localhost:8000**
- API-Dokumentation: **http://localhost:8000/docs**

**Folgeläufe** (liest aus PostGIS, kein Overpass-Request):
```bash
python main.py --from-db --serve
```

---

## CLI-Referenz

| Flag | Beschreibung |
|---|---|
| `--db` | Ergebnisse in PostGIS speichern + API starten |
| `--from-db` | Daten aus PostGIS laden (statt Overpass) |
| `--cache` | GeoJSON-Datei-Cache verwenden |
| `--serve` | FastAPI-Server starten (ohne --db) |
| `--resolution 200` | Rasterauflösung in Metern (Standard: 300) |
| `--weights pop=4,pt=5` | Scoring-Gewichte anpassen |
| `--top 15` | Anzahl Top-Kandidaten |
| `--min-dist 400` | Mindestabstand zwischen Kandidaten (m) |
| `--no-map` | Keine Folium-HTML-Karte erzeugen |

---

## API-Endpoints

| Endpoint | Beschreibung |
|---|---|
| `GET /` | Interaktive Leaflet-Karte |
| `GET /api/grid?min_score=30` | Bewertetes Raster als GeoJSON |
| `GET /api/top?n=10` | Top-N Kandidaten |
| `GET /api/pt` | ÖV-Haltestellen |
| `GET /api/shops` | Supermärkte |
| `GET /api/lockers` | Bestehende Paketstationen |
| `GET /api/quartiere` | BFS-Quartiere |
| `GET /api/layers` | Tabellenübersicht |
| `GET /docs` | Interaktive API-Dokumentation (Swagger) |

---

## Scoring-Modell

| Faktor | Methode | Radius | Std.-Gewicht |
|---|---|---|---|
| Bevölkerungsdichte | EW/ha des nächsten BFS-Quartiers | — | 3 |
| ÖV-Erreichbarkeit | Haltestellen im Radius | 400 m | 3 |
| Nahversorgung | Supermärkte im Radius | 600 m | 2 |
| Konkurrenz (neg.) | Distanz zur nächsten Paketstation | — | 2 |
| Fusswegnetz-Proxy | POI-Dichte im Radius | 300 m | 2 |

Alle Distanzen in CH1903+/LV95 (EPSG:2056).

---

## Datenquellen

| Datensatz | Quelle | Lizenz |
|---|---|---|
| Bevölkerung nach Quartier | BFS STATPOP 2022 | CC BY |
| ÖV-Haltestellen | OpenStreetMap (Overpass) | ODbL |
| Supermärkte | OpenStreetMap | ODbL |
| Paketstationen | OpenStreetMap + manuell | ODbL |
