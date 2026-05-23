# Präsentation: Datengestützte Paketstation-Standortanalyse Zürich

> Arbeitsgrundlage für die PowerPoint. Eine Überschrift (`##`) = eine Folie.
> Bullet-Points = Folieninhalt; *Sprechnotiz:* = Notizen für den Vortrag.
> Stand: Methodik wie aktuell **implementiert** (AHP, PostGIS, FastAPI).

---

## 1 · Titel

**Datengestützte Standortanalyse für Paketstationen in der Stadt Zürich**
Identifikation des räumlichen Nachfragepotenzials aus Bevölkerungs- und Mobilitätsdaten

- Standortanalyse · Zürich · 2026
- Methode: Geodaten-Scoring mit AHP-Gewichtung · PostGIS · interaktive Karte

---

## 2 · Einleitung & Problemstellung

**Leitfrage:** „Wo erzeugt eine Paketstation den höchsten Nutzen – für Anbieter und Kunden?"

- **Der Boom:** Wachsende Paketvolumina erhöhen den Druck auf die Zustellung.
- **Das Problem:** Die „letzte Meile" ist der teuerste und ineffizienteste Abschnitt der Lieferkette.
- **Die Lösung:** Paketstationen – flexibel, rund um die Uhr, gebündelte Zustellung.

*Sprechnotiz:* Standortwahl bisher reaktiv (Immobilienverfügbarkeit). Ziel: proaktiv & datenbasiert.

---

## 3 · Forschungsfrage & Hypothesen

**Hauptforschungsfrage:** Welche Standorte in der Stadt Zürich weisen das höchste
Eignungspotenzial für Paketstationen auf?

- **H1 – Wohndichte = Basispotenzial:** Hohe Bevölkerungs-/Geschossflächendichte korreliert mit Bedarf.
- **H2 – Knotenpunkte > Wohnortnähe:** Nähe zu Bahnhöfen/Tram-/Busknoten dominiert reine Wohnortnähe.
- **H3 – Periphere Lücken:** Unterversorgte Wohngebiete mit hohem Bedarf, aber großer Distanz zur nächsten Station.

*Sprechnotiz:* Die Hypothesen begründen direkt die AHP-Gewichtung (Folie 7).

---

## 4 · Zielsetzung

- **Parameter-Definition:** Identifikation der relevantesten Standortfaktoren.
- **Modellentwicklung:** Gewichtetes, nachvollziehbares Scoring-Modell über ein Stadtraster.
- **Gap-Analyse:** Abgleich mit dem bestehenden Netz (Post/My Post 24).

Ziel: **proaktive, datengestützte Standortwahl** statt reaktiver Immobilienverfügbarkeit.

---

## 5 · Datengrundlage (4 Layer)

Ausschließlich öffentlich verfügbare Geodaten.

| Layer | Inhalt | Quelle |
|---|---|---|
| Bevölkerung | Einwohnerdichte je Stadtquartier (→ Ziel: STATPOP-Hektarraster) | BFS / Stadt Zürich |
| Mobilität (ÖV) | Haltestellen (Tram/Bus/Bahn) | OpenStreetMap (Overpass) |
| Points of Interest | Detailhandel / Supermärkte / Convenience | OpenStreetMap |
| Bestehendes Netz | Paketstationen & Filialen | Post „postoneweb" + OSM |

*Sprechnotiz:* Aktuell 1712 ÖV-Halte, 363 Shops, 73 bestehende Standorte, 38 Quartiere.

---

## 6 · Methodik

1. **Analyseraster:** gleichmäßiges Punktgitter über die Stadt (Standard 300 m), aufgebaut in
   metrischen Schweizer Landeskoordinaten (CH1903+/LV95, EPSG:2056).
2. **Fünf Teilscores je Rasterpunkt (0–100):**
   - Bevölkerungsdichte (nächstes Quartier)
   - ÖV-Erreichbarkeit (Halte im 400-m-Radius)
   - Nahversorgung (Shops im 600-m-Radius)
   - Konkurrenz/Gap (Distanz zur nächsten Station, invertiert)
   - Fusswegnetz-Proxy (POI-Dichte im 300-m-Radius)
3. **Räumliche Effizienz:** Nachbarschaftsabfragen via cKDTree.
4. **Gewichtung:** AHP (Folie 7). **Gesamtscore** = gewichteter Mittelwert.

*Sprechnotiz:* Alle Distanzen metrisch (LV95), Ausgabe in WGS84 für die Karte.

---

## 7 · AHP-Gewichtung (Analytic Hierarchy Process) — Kernstück

Gewichte werden **nicht frei gesetzt**, sondern aus paarweisen Vergleichen (Saaty-Skala 1–9)
hergeleitet und auf Konsistenz geprüft.

**Paarvergleichsmatrix (Auszug der Logik):**
- ÖV wichtiger als Bevölkerung (H2), Bevölkerung wichtiger als Shops (H1), usw.

**Resultierende Gewichte (Consistency Ratio = 0.015 < 0.10 ✓ konsistent):**

| Faktor | Gewicht |
|---|---|
| ÖV-Erreichbarkeit (Frequenz) | **41.7 %** |
| Bevölkerungsdichte | **26.3 %** |
| Nahversorgung (POI) | **16.0 %** |
| Konkurrenz / Gap (H3) | **9.7 %** |
| Fusswegnetz | **6.2 %** |

*Sprechnotiz:* Trifft das Zielprofil „40 % Frequenz / 30 % Bevölkerung / 30 % POI". CR < 0.10 belegt,
dass die Vergleiche widerspruchsfrei sind.

---

## 8 · Scoring & Konsistenz

- **Gesamtscore = Σ(Teilscore × Gewicht)** — ein **absoluter** Wert (0–100), zwischen Läufen vergleichbar.
- Keine künstliche Re-Normalisierung auf das Maximum → ehrliche, interpretierbare Werte.
- **Top-Standorte:** Sortierung nach Score mit Mindestabstand (500 m), um Cluster zu vermeiden.

*Sprechnotiz:* Karte, CSV und Datenbank zeigen denselben Score (durchgängige Konsistenz).

---

## 9 · Architektur & Tech-Stack

- **Datenbeschaffung:** Overpass-API (OSM) + lokale Post-Daten + BFS-Quartiere.
- **Datenhaltung:** PostgreSQL 17 + **PostGIS** (räumliche Tabellen & Indizes).
- **Analyse:** Python (GeoPandas, SciPy/cKDTree, NumPy).
- **API:** FastAPI – liefert GeoJSON-Endpoints (`/api/grid`, `/api/top`, `/api/weights` …).
- **Visualisierung:** interaktive Leaflet-Karte (Heatmap, Layer, Live-Gewichtungs-Slider).

*Sprechnotiz:* Reproduzierbar (pyproject.toml + Lockfile), getestet (pytest), gelintet (ruff).

---

## 10 · Ergebnisse

- **1804 bewertete Rasterpunkte** (300 m) über das Stadtgebiet.
- **Top-Kandidaten (AHP):** u. a. *Werd*, *Langstrasse*, *Mühlebach* — dichte, ÖV-starke Lagen.
- Interaktive Potenzial-Karte: Heatmap des Eignungsscores + Top-Standorte + Rohdaten-Layer.

*Sprechnotiz:* Live-Demo unter `http://localhost:8000`. Slider erlauben „Was-wäre-wenn"-Gewichtung.

---

## 11 · Qualitätssicherung & Reproduzierbarkeit

- Sauberes Python-Package (src-Layout), Konfiguration über `.env` (keine Secrets im Code).
- Abgesicherte API (SQL-Parametrisierung, Tabellen-Allowlist, lokale Bindung).
- Automatisierte Tests (pytest) + Linting/Formatierung (ruff); Lockfile für reproduzierbare Umgebung.

*Sprechnotiz:* Wissenschaftliche Nachvollziehbarkeit + technische Solidität.

---

## 12 · Limitationen & Ausblick

**Aktuelle Limitationen:**
- Bevölkerung als Quartier-Centroid-Näherung (noch kein echtes Hektarraster).
- ÖV als Halte-Anzahl im Luftlinienradius (noch keine Gehzeit-Isochronen/Fahrplanfrequenz).

**Ausblick (geplante Ausbaustufen):**
- **STATPOP-Hektarraster** statt Quartier-Centroids (feinere Bevölkerungsauflösung).
- **OSMnx-Isochronen** + Fahrplanfrequenz (ZVV/SBB) für realistische Erreichbarkeit.
- **Hypothesen-Validierung** (H1–H3 statistisch) und explizite Gap-Analyse.

---

## 13 · Datenquellen & Lizenzen

| Datensatz | Quelle | Lizenz |
|---|---|---|
| Bevölkerung (Quartier / STATPOP) | BFS / Statistik Stadt Zürich | OGD / CC BY |
| ÖV-Haltestellen | OpenStreetMap (Overpass) | ODbL |
| Supermärkte / POI | OpenStreetMap | ODbL |
| Paketstationen / Filialen | Post „postoneweb" + OSM | ODbL / OGD |

*Sprechnotiz:* Alle Daten öffentlich und frei nutzbar; Verarbeitung in CH1903+/LV95 (EPSG:2056).
