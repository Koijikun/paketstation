"""
api.py – FastAPI-Backend: liefert Geodaten aus PostGIS als GeoJSON

Endpoints:
    GET /api/layers          → Verfügbare Layer und Zeilenanzahl
    GET /api/grid            → Bewertetes Raster (gefiltert nach min_score)
    GET /api/top             → Top-N Kandidaten
    GET /api/pt              → ÖV-Haltestellen
    GET /api/shops           → Supermärkte
    GET /api/lockers         → Bestehende Paketstationen
    GET /api/quartiere       → BFS-Quartiere

Starten:
    uvicorn paketstation.api:app --reload --port 8000
"""

import json
import logging
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from paketstation.config import AHP_CONSISTENCY_RATIO, DEFAULT_WEIGHTS
from paketstation.db import (
    get_engine,
    load_geojson_for_api,
    load_top_candidates,
    table_info,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Paketstation Standort-API",
    description="Geodaten-API für die Paketstation-Standortanalyse Zürich",
    version="1.0",
)

# CORS – die ausgelieferte Leaflet-Karte läuft same-origin (relative Pfade) und
# braucht eigentlich kein CORS. Erlaubte Origins daher restriktiv und über die
# Umgebungsvariable CORS_ALLOW_ORIGINS (kommagetrennt) konfigurierbar.
_default_origins = "http://localhost:8000,http://127.0.0.1:8000"
_allow_origins = [
    o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", _default_origins).split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Globale Engine (einmal erstellt beim Start)
engine = get_engine()


# ---------------------------------------------------------------------------
# Health / Info
# ---------------------------------------------------------------------------


@app.get("/api/layers", summary="Übersicht aller Tabellen")
def get_layers():
    """Gibt alle verfügbaren Tabellen mit Zeilenanzahl und Speichergrösse zurück."""
    try:
        df = table_info(engine)
        return df.to_dict(orient="records")
    except Exception:
        logger.exception("Fehler bei API-Anfrage")
        raise HTTPException(status_code=500, detail="Interner Serverfehler") from None


@app.get("/api/weights", summary="AHP-Standardgewichte")
def get_weights():
    """
    Gibt die per AHP hergeleiteten Standardgewichte (Summe = 1) und die
    Consistency Ratio zurück. Das Frontend initialisiert damit die Slider, sodass
    die Default-Ansicht der Karte exakt dem gespeicherten Score (CSV/DB) entspricht.
    """
    return {
        "weights": DEFAULT_WEIGHTS,
        "consistency_ratio": round(AHP_CONSISTENCY_RATIO, 4),
    }


# ---------------------------------------------------------------------------
# Raster / Scoring
# ---------------------------------------------------------------------------


@app.get("/api/grid", summary="Bewertetes Analysegitter")
def get_grid(
    min_score: float = Query(
        default=30.0, ge=0, le=100, description="Minimaler Score-Schwellwert (0–100)"
    ),
    limit: int = Query(
        default=3000, ge=1, le=10000, description="Maximale Anzahl zurückgegebener Punkte"
    ),
):
    """
    Gibt alle Rasterpunkte mit score_total >= min_score als GeoJSON zurück.
    Niedrige min_score-Werte erzeugen grosse Responses — für die Karte
    empfiehlt sich min_score >= 30.
    """
    try:
        geojson_str = load_geojson_for_api("scored_grid", engine, min_score=min_score, limit=limit)
        return JSONResponse(content=json.loads(geojson_str))
    except Exception:
        logger.exception("Fehler bei API-Anfrage")
        raise HTTPException(status_code=500, detail="Interner Serverfehler") from None


@app.get("/api/top", summary="Top-N Standortkandidaten")
def get_top(
    n: int = Query(default=10, ge=1, le=50, description="Anzahl Top-Kandidaten"),
):
    """Gibt die n besten Rasterpunkte nach score_total zurück."""
    try:
        gdf = load_top_candidates(engine, n=n)
        return JSONResponse(content=json.loads(gdf.to_json()))
    except Exception:
        logger.exception("Fehler bei API-Anfrage")
        raise HTTPException(status_code=500, detail="Interner Serverfehler") from None


# ---------------------------------------------------------------------------
# OSM-Layer
# ---------------------------------------------------------------------------


@app.get("/api/pt", summary="ÖV-Haltestellen")
def get_public_transport():
    """Gibt alle ÖV-Haltestellen als GeoJSON zurück."""
    try:
        geojson_str = load_geojson_for_api("public_transport", engine)
        return JSONResponse(content=json.loads(geojson_str))
    except Exception:
        logger.exception("Fehler bei API-Anfrage")
        raise HTTPException(status_code=500, detail="Interner Serverfehler") from None


@app.get("/api/shops", summary="Supermärkte und Convenience-Shops")
def get_shops():
    """Gibt alle Supermärkte / Convenience-Shops als GeoJSON zurück."""
    try:
        geojson_str = load_geojson_for_api("shops", engine)
        return JSONResponse(content=json.loads(geojson_str))
    except Exception:
        logger.exception("Fehler bei API-Anfrage")
        raise HTTPException(status_code=500, detail="Interner Serverfehler") from None


@app.get("/api/lockers", summary="Bestehende Paketstationen")
def get_lockers():
    """Gibt alle bekannten Paketstationen als GeoJSON zurück."""
    try:
        geojson_str = load_geojson_for_api("parcel_lockers", engine)
        return JSONResponse(content=json.loads(geojson_str))
    except Exception:
        logger.exception("Fehler bei API-Anfrage")
        raise HTTPException(status_code=500, detail="Interner Serverfehler") from None


@app.get("/api/quartiere", summary="BFS Stadtquartiere")
def get_quartiere():
    """Gibt alle BFS-Quartiere mit Bevölkerungsdaten als GeoJSON zurück."""
    try:
        geojson_str = load_geojson_for_api("quartiere", engine)
        return JSONResponse(content=json.loads(geojson_str))
    except Exception:
        logger.exception("Fehler bei API-Anfrage")
        raise HTTPException(status_code=500, detail="Interner Serverfehler") from None


# ---------------------------------------------------------------------------
# Interaktive Karte (direkt vom API-Server ausgeliefert)
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse, summary="Interaktive Karte")
def get_map():
    """Liefert die Leaflet-Karte, die Daten live vom API bezieht."""
    html = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Paketstation Standort-Analyse Zürich</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"/>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: monospace; background: #0f1117; color: #e8e4d9; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }
  header { padding: 10px 18px; background: #0f1117; border-bottom: 1px solid #2a2d35; display: flex; align-items: center; gap: 16px; flex-shrink: 0; }
  header h1 { font-size: 13px; font-weight: normal; letter-spacing: 0.08em; color: #c8c2b0; }
  .badge { font-size: 10px; padding: 2px 8px; border-radius: 2px; letter-spacing: 0.05em; }
  .badge-ok { background: #1a2e1a; color: #5cb85c; border: 1px solid #2d4d2d; }
  .badge-loading { background: #2a1e0a; color: #e6a830; border: 1px solid #4d3a1a; }
  .main { display: flex; flex: 1; overflow: hidden; }
  .sidebar { width: 320px; flex-shrink: 0; background: #13161e; border-right: 1px solid #2a2d35; display: flex; flex-direction: column; overflow-y: auto; }
  .s-section { padding: 18px; border-bottom: 1px solid #1e2128; }
  .s-section h3 { font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase; color: #555; margin-bottom: 14px; display: flex; align-items: center; justify-content: space-between; }
  .layer-row { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; cursor: pointer; }
  .layer-row label { font-size: 12px; color: #9a9080; cursor: pointer; }
  .dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
  input[type=checkbox] { accent-color: #c8a96e; transform: scale(1.1); }
  .weight-row { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
  .weight-label { font-size: 11px; color: #777; width: 120px; flex-shrink: 0; }
  input[type=range] { flex: 1; accent-color: #c8a96e; height: 4px; cursor: pointer; }
  .weight-val { font-size: 11px; color: #c8a96e; width: 20px; text-align: right; font-weight: bold; }
  
  /* Tooltip styling */
  .help-icon { width: 16px; height: 16px; border: 1px solid #444; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: 10px; color: #777; cursor: help; margin-left: 8px; transition: all 0.2s; }
  .help-icon:hover { border-color: #c8a96e; color: #c8a96e; background: rgba(200, 169, 110, 0.1); }
  .tooltip { position: relative; display: inline-block; }
  .tooltip .tooltiptext { 
    visibility: hidden; 
    width: 280px; 
    background-color: #1a1d25; 
    color: #c8c2b0; 
    text-align: left; 
    border: 1px solid #c8a96e; 
    border-radius: 4px; 
    padding: 16px; 
    position: absolute; 
    z-index: 10000; 
    right: 0; 
    top: 25px; 
    opacity: 0; 
    transition: opacity 0.2s, transform 0.2s; 
    transform: translateY(-5px);
    font-size: 11px; 
    line-height: 1.5; 
    text-transform: none; 
    letter-spacing: normal; 
    box-shadow: 0 15px 40px rgba(0,0,0,0.8); 
    pointer-events: none; 
  }
  .tooltip:hover .tooltiptext { visibility: visible; opacity: 1; transform: translateY(0); }

  .stat-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .stat { background: #0f1117; border: 1px solid #2a2d35; border-radius: 4px; padding: 10px; }
  .stat-v { font-size: 20px; color: #c8a96e; line-height: 1; font-weight: bold; }
  .stat-l { font-size: 9px; color: #555; margin-top: 4px; letter-spacing: 0.05em; }
  .cand { padding: 9px 14px; border-bottom: 1px solid #1e2128; cursor: pointer; }
  .cand:hover { background: #1a1d25; }
  .cand-name { font-size: 11px; color: #c8c2b0; }
  .cand-bar { height: 2px; background: #2a2d35; border-radius: 1px; margin: 4px 0 3px; }
  .cand-fill { height: 100%; border-radius: 1px; }
  .cand-meta { font-size: 9px; color: #555; }
  #map { flex: 1; }
  .leaflet-popup-content-wrapper { background: #13161e; color: #c8c2b0; border: 1px solid #2a2d35; border-radius: 4px; box-shadow: 0 4px 20px rgba(0,0,0,.6); }
  .leaflet-popup-tip { background: #13161e; }
  .leaflet-popup-content { font-family: monospace; font-size: 11px; margin: 12px; min-width: 200px; }
  .p-score { font-size: 26px; color: #c8a96e; text-align: center; }
  .p-label { font-size: 9px; color: #555; text-align: center; letter-spacing: .1em; margin-bottom: 10px; }
  .p-row { display: flex; justify-content: space-between; gap: 16px; margin-bottom: 4px; }
  .p-row span:first-child { color: #666; }
  .p-bar { height: 4px; background: #1e2128; border-radius: 2px; margin: 2px 0 6px; }
  .p-bfill { height: 100%; border-radius: 2px; background: #c8a96e; }
  .legend { position: fixed; bottom: 20px; right: 10px; z-index: 9999; background: #13161e; border: 1px solid #2a2d35; border-radius: 5px; padding: 12px; font-family: monospace; min-width: 180px; }
  .leg-title { font-size: 9px; color: #444; letter-spacing: .1em; text-transform: uppercase; margin-bottom: 8px; }
  .leg-bar { display: flex; height: 7px; border-radius: 2px; overflow: hidden; margin-bottom: 4px; }
  .leg-labels { display: flex; justify-content: space-between; font-size: 9px; color: #444; }
</style>
</head>
<body>
<header>
  <h1>PAKETSTATION STANDORT-ANALYSE · ZÜRICH</h1>
  <span class="badge badge-loading" id="badge">LADEN…</span>
  <span style="font-size:10px;color:#444">API: <span id="api-status">verbinde…</span></span>
</header>
<div class="main">
  <div class="sidebar">
    <div class="s-section">
      <h3>
        Gewichtung (live)
        <div class="tooltip">
          <span class="help-icon">?</span>
          <span class="tooltiptext">
            <b>Bevölkerung:</b> Einwohnerdichte pro Hektar im jeweiligen Quartier.<br><br>
            <b>ÖV-Halt.:</b> Anzahl Haltestellen in 400m Gehdistanz.<br><br>
            <b>Supermärkte:</b> Nahversorgung in 600m Radius.<br><br>
            <b>Konkurrenz:</b> Distanz zur nächsten Paketstation. Je weiter weg, desto höher der Score.<br><br>
            <b>Fusswegnetz:</b> POI-Dichte als Proxy für Passantenfrequenz.
          </span>
        </div>
      </h3>
      <div class="weight-row"><span class="weight-label">Bevölkerung</span><input type="range" id="w-pop" min="0" max="50" step="0.1" value="21.5"><span class="weight-val" id="wv-pop">22%</span></div>
      <div class="weight-row"><span class="weight-label">ÖV-Haltestellen</span><input type="range" id="w-pt" min="0" max="50" step="0.1" value="37.5"><span class="weight-val" id="wv-pt">38%</span></div>
      <div class="weight-row"><span class="weight-label">Supermärkte</span><input type="range" id="w-shop" min="0" max="50" step="0.1" value="12.1"><span class="weight-val" id="wv-shop">12%</span></div>
      <div class="weight-row"><span class="weight-label">Konkurrenz (neg.)</span><input type="range" id="w-comp" min="0" max="50" step="0.1" value="21.5"><span class="weight-val" id="wv-comp">22%</span></div>
      <div class="weight-row"><span class="weight-label">Fusswegnetz</span><input type="range" id="w-walk" min="0" max="50" step="0.1" value="7.3"><span class="weight-val" id="wv-walk">7%</span></div>
    </div>
    <div class="s-section">
      <h3>
        Layer
        <div class="tooltip">
          <span class="help-icon">?</span>
          <span class="tooltiptext">
            <b>Score-Heatmap:</b> Visualisiert die berechnete Standortqualität.<br><br>
            <b>ÖV / Shops:</b> Zeigt die Rohdaten (Haltestellen & Läden) aus OpenStreetMap.<br><br>
            <b>Stationen:</b> Bestehende Standorte der Post und My Post 24.
          </span>
        </div>
      </h3>
      <div class="layer-row"><input type="checkbox" id="l-heat" checked><div class="dot" style="background:#c8a96e;opacity:.7"></div><label for="l-heat">Score-Heatmap</label></div>
      <div class="layer-row"><input type="checkbox" id="l-pt" checked><div class="dot" style="background:#5b9bd5"></div><label for="l-pt">ÖV-Haltestellen</label></div>
      <div class="layer-row"><input type="checkbox" id="l-shop" checked><div class="dot" style="background:#5cb85c"></div><label for="l-shop">Supermärkte</label></div>
      <div class="layer-row"><input type="checkbox" id="l-lock"><div class="dot" style="background:#e74c3c"></div><label for="l-lock">Bestehende Stationen</label></div>
      <div class="layer-row"><input type="checkbox" id="l-top" checked><div class="dot" style="background:#c8a96e"></div><label for="l-top">Top-Kandidaten</label></div>
    </div>
    <div class="s-section">
      <h3>Statistiken</h3>
      <div class="stat-grid">
        <div class="stat"><div class="stat-v" id="s-pt">–</div><div class="stat-l">ÖV-HALT.</div></div>
        <div class="stat"><div class="stat-v" id="s-shop">–</div><div class="stat-l">SUPERMÄRKTE</div></div>
        <div class="stat"><div class="stat-v" id="s-grid">–</div><div class="stat-l">RASTERPUNKTE</div></div>
        <div class="stat"><div class="stat-v" id="s-lock">–</div><div class="stat-l">STATIONEN</div></div>
      </div>
    </div>
    <div class="s-section" style="padding-bottom:4px">
      <h3>
        Top-Kandidaten
        <div class="tooltip">
          <span class="help-icon">?</span>
          <span class="tooltiptext">
            <b>Ranking:</b> Die 10 besten Standorte basierend auf deiner Gewichtung.<br><br>
            <b>Mindestabstand:</b> Um Cluster zu vermeiden, wird zwischen den Top-Kandidaten ein Abstand von 500m eingehalten.<br><br>
            <b>Score:</b> Ein Wert von 100 markiert den aktuell besten Punkt im Stadtgebiet.
          </span>
        </div>
      </h3>
    </div>
    <div id="cand-list"></div>
  </div>
  <div id="map"></div>
</div>

<div class="legend">
  <div class="leg-title">Score</div>
  <div class="leg-bar">
    <div style="flex:1;background:#1a3a2a"></div>
    <div style="flex:1;background:#4a7c59"></div>
    <div style="flex:1;background:#c8a96e"></div>
    <div style="flex:1;background:#d4713a"></div>
    <div style="flex:1;background:#c0392b"></div>
  </div>
  <div class="leg-labels"><span>0</span><span>50</span><span>100</span></div>
</div>

<script>
const API = '';  // Leer = gleicher Host (relativer Pfad)

const map = L.map('map', { center: [47.376, 8.548], zoom: 13, preferCanvas: true });
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
  attribution: '© OpenStreetMap, © CARTO', subdomains: 'abcd', maxZoom: 19
}).addTo(map);

const gHeat  = L.layerGroup().addTo(map);
const gPT    = L.layerGroup().addTo(map);
const gShop  = L.layerGroup().addTo(map);
const gLock  = L.layerGroup();
const gTop   = L.layerGroup().addTo(map);

let rawGridData = null;

// Weight sliders logic
const weights = {
  pop: document.getElementById('w-pop'),
  pt: document.getElementById('w-pt'),
  shop: document.getElementById('w-shop'),
  comp: document.getElementById('w-comp'),
  walk: document.getElementById('w-walk')
};

// Präzise Gewichtswerte (in %). Werden beim Start aus /api/weights (AHP)
// gesetzt, damit die Default-Karte exakt dem gespeicherten Score entspricht.
const weightValues = { pop: 21.5, pt: 37.5, shop: 12.1, comp: 21.5, walk: 7.3 };

// Mapping API-Faktor -> Slider-Key
const API_TO_SLIDER = {
  population: 'pop', public_transport: 'pt', shops: 'shop',
  competition: 'comp', walkability: 'walk'
};

function setWeightLabel(k) {
  document.getElementById('wv-'+k).textContent = Math.round(weightValues[k]) + '%';
}

async function loadWeights() {
  try {
    const res = await fetch(`${API}/api/weights`);
    const data = await res.json();
    for (const [factor, w] of Object.entries(data.weights || {})) {
      const k = API_TO_SLIDER[factor];
      if (!k) continue;
      weightValues[k] = w * 100;          // präzise (z.B. 41.74)
      weights[k].value = (w * 100).toFixed(1);
    }
  } catch (e) { /* Default-Werte beibehalten */ }
  Object.keys(weights).forEach(setWeightLabel);
}

Object.keys(weights).forEach(k => {
  weights[k].addEventListener('input', e => {
    weightValues[k] = parseFloat(e.target.value);  // Live-What-if (überschreibt AHP)
    setWeightLabel(k);
    updateAnalysis();
  });
});

// Layer toggles
['heat','pt','shop','lock','top'].forEach(k => {
  document.getElementById('l-'+k).addEventListener('change', e => {
    const g = {heat:gHeat,pt:gPT,shop:gShop,lock:gLock,top:gTop}[k];
    e.target.checked ? g.addTo(map) : map.removeLayer(g);
  });
});

function scoreColor(s) {
  const stops = [[0,'#1a3a2a'],[25,'#4a7c59'],[50,'#c8a96e'],[75,'#d4713a'],[100,'#c0392b']];
  for (let i=0;i<stops.length-1;i++) {
    const [s0,c0]=stops[i], [s1,c1]=stops[i+1];
    if (s>=s0&&s<=s1) {
      const t=(s-s0)/(s1-s0);
      const h=(c,o)=>parseInt(c.slice(o,o+2),16);
      const r=Math.round(h(c0,1)+t*(h(c1,1)-h(c0,1)));
      const g=Math.round(h(c0,3)+t*(h(c1,3)-h(c0,3)));
      const b=Math.round(h(c0,5)+t*(h(c1,5)-h(c0,5)));
      return `#${r.toString(16).padStart(2,'0')}${g.toString(16).padStart(2,'0')}${b.toString(16).padStart(2,'0')}`;
    }
  }
  return '#c0392b';
}

function popupHTML(p) {
  const bar = (v,label) => `
    <div style="color:#666;font-size:10px">${label}</div>
    <div class="p-bar"><div class="p-bfill" style="width:${v}%"></div></div>`;
  return `
    <div class="p-score">${Math.round(p.score_total)}</div>
    <div class="p-label">GESAMT-SCORE</div>
    <div style="border-top:1px solid #2a2d35;padding-top:8px">
      <div class="p-row"><span>Quartier</span><span>${p.nearest_quartier||'–'}</span></div>
      ${bar(p.score_pop,'Bevölkerung')}
      ${bar(p.score_pt,'ÖV-Erreichbarkeit')}
      ${bar(p.score_shops,'Nahversorgung')}
      ${bar(p.score_competition,'Konkurrenz-Abstand')}
      ${bar(p.score_walkability,'Fusswegnetz')}
      <div style="color:#444;font-size:9px;margin-top:6px">Nächste Station: ${p.nearest_station_m >= 0 ? p.nearest_station_m+'m' : 'keine'}</div>
    </div>`;
}

function updateAnalysis() {
  if (!rawGridData) return;
  
  // Präzise Gewichte (in %). Der Score ist ein gewichteter Mittelwert, daher
  // ist die Einheit (% oder Anteil) irrelevant – nur die Verhältnisse zählen.
  const w = {
    pop:  weightValues.pop,
    pt:   weightValues.pt,
    shop: weightValues.shop,
    comp: weightValues.comp,
    walk: weightValues.walk
  };
  const totalW = w.pop + w.pt + w.shop + w.comp + w.walk;
  
  // Recalculate all scores
  const features = rawGridData.features.map(f => {
    const p = f.properties;
    let score = 0;
    if (totalW > 0) {
      score = (p.score_pop * w.pop + p.score_pt * w.pt + p.score_shops * w.shop + 
               p.score_competition * w.comp + p.score_walkability * w.walk) / totalW;
    }
    return { ...f, properties: { ...p, score_total: score } };
  });

  // 1. Update Heatmap
  gHeat.clearLayers();
  features.forEach(f => {
    if (f.properties.score_total < 25) return;
    const s = f.properties.score_total;
    const c = scoreColor(s);
    L.circle([f.geometry.coordinates[1], f.geometry.coordinates[0]], {
      radius: 170, color:'transparent', fillColor:c,
      fillOpacity: 0.3 + (s/100)*0.45, weight:0
    }).bindPopup(popupHTML(f.properties), {maxWidth:260}).addTo(gHeat);
  });

  // 2. Update Top Candidates
  const top10 = [...features]
    .sort((a,b) => b.properties.score_total - a.properties.score_total)
    .slice(0, 10);
    
  gTop.clearLayers();
  const list = document.getElementById('cand-list');
  list.innerHTML = '';
  
  top10.forEach((f, i) => {
    const p = f.properties;
    const rank = i+1;
    const color = rank<=3 ? '#c8a96e' : rank<=6 ? '#8ab87a' : '#5b9bd5';
    const coords = [f.geometry.coordinates[1], f.geometry.coordinates[0]];
    
    const icon = L.divIcon({
      html:`<div style="width:24px;height:24px;border-radius:50%;background:${color};
        display:flex;align-items:center;justify-content:center;font-size:11px;
        font-weight:bold;color:#0f1117;box-shadow:0 2px 8px rgba(0,0,0,.6)">${rank}</div>`,
      iconSize:[24,24], className:''
    });
    
    L.marker(coords, {icon}).bindPopup(popupHTML(p), {maxWidth:280}).addTo(gTop);
    
    const el = document.createElement('div');
    el.className='cand';
    el.innerHTML=`
      <div class="cand-name">#${rank} ${p.nearest_quartier||'–'}</div>
      <div class="cand-bar"><div class="cand-fill" style="width:${p.score_total}%;background:${color}"></div></div>
      <div class="cand-meta">Score ${Math.round(p.score_total)} · ÖV ${Math.round(p.score_pt)} · Bev. ${Math.round(p.score_pop)}</div>`;
    el.onclick = () => map.setView(coords, 15);
    list.appendChild(el);
  });
}

async function loadGrid() {
  const res = await fetch(`${API}/api/grid?min_score=0&limit=5000`);
  rawGridData = await res.json();
  document.getElementById('s-grid').textContent = rawGridData.features?.length || 0;
  updateAnalysis();
}

async function loadPT() {
  const res = await fetch(`${API}/api/pt`);
  const fc  = await res.json();
  gPT.clearLayers();
  document.getElementById('s-pt').textContent = fc.features?.length || 0;
  (fc.features||[]).forEach(f => {
    L.circleMarker([f.geometry.coordinates[1], f.geometry.coordinates[0]], {
      radius:3, color:'#5b9bd5', fillColor:'#5b9bd5', fillOpacity:.6, weight:.5
    }).bindTooltip(f.properties.name||'ÖV-Haltestelle').addTo(gPT);
  });
}

async function loadShops() {
  const res = await fetch(`${API}/api/shops`);
  const fc  = await res.json();
  gShop.clearLayers();
  document.getElementById('s-shop').textContent = fc.features?.length || 0;
  (fc.features||[]).forEach(f => {
    L.circleMarker([f.geometry.coordinates[1], f.geometry.coordinates[0]], {
      radius:4, color:'#5cb85c', fillColor:'#5cb85c', fillOpacity:.65, weight:.5
    }).bindTooltip(f.properties.name||'Shop').addTo(gShop);
  });
}

async function loadLockers() {
  const res = await fetch(`${API}/api/lockers`);
  const fc  = await res.json();
  gLock.clearLayers();
  document.getElementById('s-lock').textContent = fc.features?.length || 0;
  (fc.features||[]).forEach(f => {
    L.circleMarker([f.geometry.coordinates[1], f.geometry.coordinates[0]], {
      radius:7, color:'#e74c3c', fillColor:'#e74c3c', fillOpacity:.3,
      weight:2, dashArray:'5,4'
    }).bindPopup(`<b>Paketstation</b><br>Betreiber: ${f.properties.operator||'–'}`).addTo(gLock);
  });
}

async function init() {
  try {
    const res = await fetch(`${API}/api/layers`);
    if (!res.ok) throw new Error('API nicht erreichbar');
    document.getElementById('api-status').textContent = 'verbunden';
    document.getElementById('badge').textContent = 'LIVE';
    document.getElementById('badge').className = 'badge badge-ok';

    await loadWeights();   // AHP-Gewichte VOR dem ersten Scoring laden
    await Promise.all([loadGrid(), loadPT(), loadShops(), loadLockers()]);
  } catch(e) {
    document.getElementById('api-status').textContent = 'FEHLER: ' + e.message;
    document.getElementById('badge').textContent = 'API OFFLINE';
  }
}

init();
</script>
</body>
</html>
"""
    return HTMLResponse(content=html)
