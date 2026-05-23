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
| Bevölkerung | Einwohnerdichte je Stadtquartier (→ Ziel: Grenzen aus OSM) | OpenStreetMap (Overpass) |
| Mobilität (ÖV) | Haltestellen (Tram/Bus/Bahn) | OpenStreetMap (Overpass) |
| Points of Interest | Detailhandel / Supermärkte / Convenience | OpenStreetMap (Overpass) |
| Bestehendes Netz | Paketstationen & Filialen | Post „postoneweb" + OSM |

*Sprechnotiz:* Datenbasis bewusst auf OpenStreetMap vereinheitlicht — einheitlich, reproduzierbar.

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

**Logik der Paarvergleiche:** ÖV dominiert (H2); Konkurrenz/Gap und Bevölkerung gleichauf
(Standortziel „Nachfrage **und** unterversorgt"); Shops und Fusswegnetz nachrangig.

**Resultierende Gewichte (Consistency Ratio = 0.007 < 0.10 ✓ konsistent):**

| Faktor | Gewicht |
|---|---|
| ÖV-Erreichbarkeit (Frequenz) | **37.5 %** |
| Konkurrenz / Gap (unterversorgt) | **21.5 %** |
| Bevölkerungsdichte | **21.5 %** |
| Nahversorgung (POI) | **12.1 %** |
| Fusswegnetz | **7.3 %** |

*Sprechnotiz:* Der Gap-Faktor wurde bewusst hochgewichtet (gleichauf mit Bevölkerung), weil das
Ziel **neue, unterversorgte** Standorte sind. CR = 0.007 belegt widerspruchsfreie Vergleiche.

---

## 8 · Scoring & Konsistenz

- **Gesamtscore = Σ(Teilscore × Gewicht)** — ein **absoluter** Wert (0–100), zwischen Läufen vergleichbar.
- Keine künstliche Re-Normalisierung auf das Maximum → ehrliche, interpretierbare Werte.
- **Gap-Faktor kalibriert:** Distanz zur nächsten Station kontinuierlich bis **1500 m**
  (zuvor 500 m → 77 % aller Punkte am Maximum, dadurch wirkungslos).
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
- **Top-Kandidaten:** *Werd*, *Langstrasse*, *Mühlebach* (Score ~84–85) — dichte, ÖV-starke
  Lagen, die ~390–540 m von der nächsten bestehenden Station entfernt sind.
- Interaktive Potenzial-Karte: Heatmap des Eignungsscores + Top-Standorte + Rohdaten-Layer
  + Live-Gewichtungs-Slider.

| Rang | Quartier | Score | ÖV | Bev. | Gap | nächste Station |
|---|---|---|---|---|---|---|
| 1 | Werd | 85 | 100 | 96 | 33 | 498 m |
| 2 | Langstrasse | 85 | 100 | 93 | 36 | 537 m |
| 4 | Mühlebach | 84 | 100 | 91 | 33 | 488 m |

*Sprechnotiz:* Live-Demo unter `http://localhost:8000`. Slider erlauben „Was-wäre-wenn"-Gewichtung.

---

## 11 · Schlüssel-Erkenntnisse

- **Datenqualität schlägt Modell:** Der Gap-Faktor war anfangs durch eine zu kleine
  Sättigungsdistanz (500 m) **wirkungslos** — 77 % der Stadt erreichten den Maximalwert.
  Erst die Kalibrierung auf 1500 m machte „unterversorgt" sichtbar.
- **AHP bringt Nachvollziehbarkeit:** Gewichte sind hergeleitet (CR = 0.007), nicht geraten;
  die Hypothesen (H1–H3) sind direkt in den Paarvergleichen abgebildet.
- **Nachfrage dominiert die Spitze:** Selbst bei hohem Gap-Gewicht (21.5 %) führen die
  nachfragestärksten Quartiere — weil deren ÖV-/Bevölkerungswerte überragend sind. Reine
  Umgewichtung surft die „größten Lücken" nicht automatisch nach oben.
- **Konsequenz:** „Eignungspotenzial" und „unterversorgte Lücke" sind **zwei Fragen**;
  letztere braucht eine eigene Gap-Auswertung (harter Ausschluss-Puffer), nicht nur Gewichte.

*Sprechnotiz:* Das ist die wichtigste methodische Lehre — sie rechtfertigt die nächsten Ausbaustufen.

---

## 12 · Qualitätssicherung & Reproduzierbarkeit

- Sauberes Python-Package (src-Layout), Konfiguration über `.env` (keine Secrets im Code).
- Abgesicherte API (SQL-Parametrisierung, Tabellen-Allowlist, lokale Bindung).
- Automatisierte Tests (pytest) + Linting/Formatierung (ruff); Lockfile für reproduzierbare Umgebung.

*Sprechnotiz:* Wissenschaftliche Nachvollziehbarkeit + technische Solidität.

---

## 13 · Limitationen & Ausblick

**Aktuelle Limitationen:**
- Bevölkerung noch als Quartier-Näherung (38 Werte), nicht feinräumig.
- ÖV als Halte-*Anzahl* im Luftlinienradius (noch keine Typgewichtung/Gehzeit).
- Nachfrage dominiert die Spitze → „größte Lücken" noch nicht als eigene Sicht.

**Ausblick (geplante Ausbaustufen — alle aus OpenStreetMap):**
- **Bevölkerung aus OSM** (Quartier-/Stadtkreis-Grenzen statt hartkodierter Punkte) + räumlicher Join.
- **ÖV-Typgewichtung** aus OSM (Tram/Bahn > Bus), optional Fußweg-Isochronen.
- **Explizite Gap-Analyse** (Nachfrage **und** unterversorgt) + Hypothesen-Validierung (H1–H3).

---

## 14 · Datenquellen & Lizenzen

| Datensatz | Quelle | Lizenz |
|---|---|---|
| ÖV-Haltestellen | OpenStreetMap (Overpass) | ODbL |
| Supermärkte / POI | OpenStreetMap (Overpass) | ODbL |
| Bevölkerung (geplant: Grenzen) | OpenStreetMap (Overpass) | ODbL |
| Paketstationen / Filialen | Post „postoneweb" + OSM | ODbL / OGD |

*Sprechnotiz:* Datenbasis bewusst auf **OpenStreetMap** vereinheitlicht (reproduzierbar via Overpass);
Verarbeitung in CH1903+/LV95 (EPSG:2056).
