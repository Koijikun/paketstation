# Paketstation Standort-Analyse Zürich

Datenbasiertes Scoring-Modell zur Identifikation optimaler Paketstation-Standorte
in der Stadt Zürich. Kombination aus BFS STATPOP 2022 und OpenStreetMap,
mit PostGIS-Backend und FastAPI-basierter Live-Karte.

---

## Projektstruktur

```
paketstation/
├── main.py                      # Einstiegspunkt (CLI)
├── pyproject.toml               # Package-Definition, Abhängigkeiten, Tooling
├── .env.example                 # Vorlage für DB-Zugangsdaten (→ .env kopieren)
├── src/
│   └── paketstation/            # Python-Package (src-Layout)
│       ├── config.py            # Konstanten, Gewichte, BFS-Daten, OSM-Queries
│       ├── data_loader.py       # Overpass API + BFS + PostGIS-Lesezugriff
│       ├── scoring.py           # Rastergenerierung + ScoringEngine (cKDTree)
│       ├── visualizer.py        # Folium-Karte (statische HTML-Ausgabe)
│       ├── db.py                # PostGIS: Verbindung, Schema, Lesen/Schreiben
│       └── api.py               # FastAPI: GeoJSON-Endpoints + Live-Karte
├── data/                        # Eingabedaten + GeoJSON-Cache (Cache auto-generiert)
└── output/                      # Ausgaben (auto-generiert, nicht versioniert)
    ├── karte.html
    ├── scored_grid.geojson
    └── top_standorte.csv
```

---

## Setup-Anleitung

### 1. PostgreSQL installieren

**macOS (Homebrew):**

> **Wichtig:** Homebrew's PostGIS-Formel (3.6.x) wird aktuell gegen PostgreSQL 17 gebaut.
> PostgreSQL 16 funktioniert auf macOS daher **nicht** mit `brew install postgis`.
> Bitte exakt Version 17 verwenden.

```bash
brew install postgresql@17
brew services start postgresql@17
echo 'export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
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

**macOS:** Homebrew PostgreSQL erstellt keinen `postgres`-Superuser automatisch. Diesen zuerst anlegen:

```bash
createuser -s postgres
createdb paketstation
psql -d paketstation -c "CREATE EXTENSION postgis;"
psql -d paketstation -c "CREATE EXTENSION postgis_topology;"
```

**Linux:**
```bash
sudo -u postgres createdb paketstation
sudo -u postgres psql -d paketstation -c "CREATE EXTENSION postgis;"
sudo -u postgres psql -d paketstation -c "CREATE EXTENSION postgis_topology;"
```

**Windows:** "SQL Shell (psql)" im Startmenü suchen. Bei den Verbindungsprompts jeweils Enter drücken (Defaults übernehmen), nur beim Port die eigene Portnummer eingeben. Erst wenn `postgres=#` erscheint:

```sql
CREATE DATABASE paketstation;
\c paketstation
CREATE EXTENSION postgis;
CREATE EXTENSION postgis_topology;
\q
```

Verbindung testen:
```bash
psql -U postgres -d paketstation -c "SELECT PostGIS_Version();"
# Erwartete Ausgabe: z.B. "3.4 USE_GEOS=1 ..."
```

---

### 4. Python-Version setzen (pyenv)

Das Projekt benötigt Python 3.11 oder neuer. Falls pyenv verwendet wird:

```bash
pyenv install 3.11.9   # kompiliert aus dem Quellcode, dauert ca. 3–5 Minuten
cd pfad/zu/paketstation
pyenv local 3.11.9
```

> Alternativ kann eine bereits installierte Version wie `3.11.4` verwendet werden:
> `echo "3.11.4" > .python-version`

---

### 5. Virtual Environment erstellen

> **Wichtig:** Das `venv/`-Verzeichnis ist **nicht** Teil des Repositories (siehe `.gitignore`).
> Es ist plattform- und maschinenspezifisch und muss auf **jeder Workstation lokal neu
> erstellt** werden. Niemals einchecken.

**macOS / Linux:**
```bash
cd pfad/zu/paketstation
python -m venv venv
source venv/bin/activate
pip install -e .
```

**Windows (PowerShell):**
```powershell
cd pfad\zu\paketstation
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -e .
```

**Windows (CMD):**
```cmd
cd pfad\zu\paketstation
python -m venv venv
venv\Scripts\activate
pip install -e .
```

Das Projekt nutzt ein **src-Layout** (Package unter `src/paketstation/`). Der editierbare
Install (`pip install -e .`) macht das Package importierbar – ohne ihn findet `python main.py`
das Modul `paketstation` nicht. Abhängigkeiten und Tooling sind in `pyproject.toml` definiert;
Dev-Werkzeuge (pytest, ruff) optional via `pip install -e ".[dev]"`.

Das `(venv)` am Zeilenanfang zeigt an, dass das venv aktiv ist.
Bei jeder neuen Sitzung muss das venv erneut aktiviert werden (`source venv/bin/activate`
bzw. `venv\Scripts\activate`).

---

### 6. Umgebungsvariablen setzen (.env)

Die DB-Zugangsdaten werden über eine `.env`-Datei konfiguriert (nicht im Code hartkodiert
und durch `.gitignore` vom Versionieren ausgeschlossen). Vorlage kopieren und anpassen:

**macOS / Linux:**
```bash
cp .env.example .env
```

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
```

Anschliessend `.env` öffnen und mindestens `PG_PASSWORD` setzen:

```
PG_HOST=localhost
PG_PORT=5432
PG_DB=paketstation
PG_USER=postgres
PG_PASSWORD=DEIN_PASSWORT
```

Alle Variablen können auch direkt als Umgebungsvariablen gesetzt werden
(`PG_HOST`, `PG_PORT`, `PG_DB`, `PG_USER`, `PG_PASSWORD`); diese haben Vorrang vor `.env`.
Es gibt bewusst kein Standard-Passwort im Quellcode.

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

> **Hinweis:** Falls beim ersten Lauf die OSM-Layer `public_transport` oder `shops` leer bleiben
> (406-Fehler von der Overpass API), kann in `src/paketstation/config.py` der Mirror gewechselt werden:
> `OVERPASS_URL = "https://overpass.kumi.systems/api/interpreter"`

---

## Entwicklung & Tests

Dev-Werkzeuge installieren und ausführen:

```bash
pip install -e ".[dev]"

pytest          # Tests (in tests/, ohne DB/Netzwerk)
ruff check .    # Linting
ruff format .   # Formatierung
```

**Reproduzierbare Umgebung (Lockfile):** `pyproject.toml` definiert die Abhängigkeiten
mit Mindestversionen; `requirements.lock` enthält die exakt getesteten Versionen
(Python 3.11). Für eine reproduzierbare Installation:

```bash
pip install -r requirements.lock
pip install -e . --no-deps      # nur das Package selbst (editierbar)
```

Lock nach Dependency-Änderungen neu erzeugen:

```bash
pip freeze --exclude-editable > requirements.lock
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
| `GET /api/weights` | AHP-Standardgewichte + Consistency Ratio |
| `GET /api/pt` | ÖV-Haltestellen |
| `GET /api/shops` | Supermärkte |
| `GET /api/lockers` | Bestehende Paketstationen |
| `GET /api/quartiere` | BFS-Quartiere |
| `GET /api/layers` | Tabellenübersicht |
| `GET /docs` | Interaktive API-Dokumentation (Swagger) |

---

## Scoring-Modell

Der Gesamtscore ist ein gewichteter Mittelwert von fünf Teilscores (jeweils 0–100).
Die Gewichte werden über das **AHP-Verfahren** (Analytic Hierarchy Process, Saaty) aus
paarweisen Vergleichen hergeleitet und auf Konsistenz geprüft (**CR ≈ 0.015 < 0.10**).
Per CLI (`--weights`) bzw. über die Slider in der Karte sind sie überschreibbar.

| Faktor | Methode | Radius | AHP-Gewicht |
|---|---|---|---|
| ÖV-Erreichbarkeit | Haltestellen im Radius | 400 m | **41.7 %** |
| Bevölkerungsdichte | EW/ha des nächsten BFS-Quartiers | — | **26.3 %** |
| Nahversorgung | Supermärkte im Radius | 600 m | **16.0 %** |
| Konkurrenz (neg.) | Distanz zur nächsten Paketstation | — | **9.7 %** |
| Fusswegnetz-Proxy | POI-Dichte im Radius | 300 m | **6.2 %** |

Der `score_total` ist **absolut** (0–100, zwischen Läufen vergleichbar), keine
Re-Normalisierung auf das Maximum. Alle Distanzen in CH1903+/LV95 (EPSG:2056).
Die AHP-Herleitung (Paarvergleichsmatrix) steht in `src/paketstation/config.py`,
die Berechnung in `src/paketstation/ahp.py`.

---

## Datenquellen

| Datensatz | Quelle | Lizenz |
|---|---|---|
| Bevölkerung nach Quartier | BFS STATPOP 2022 | CC BY |
| ÖV-Haltestellen | OpenStreetMap (Overpass) | ODbL |
| Supermärkte | OpenStreetMap | ODbL |
| Paketstationen | OpenStreetMap + manuell | ODbL |
