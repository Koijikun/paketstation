"""
visualizer.py – Interaktive Folium-Karte der Standortanalyse

Erzeugt eine HTML-Karte mit:
    - Choropleth-ähnlicher Heatmap (Score-Kreise je Rasterpunkt)
    - ÖV-Haltestellen, Supermärkte, bestehende Paketstationen als Layer
    - Top-Kandidaten mit Ranking-Markers und Detail-Popups
    - Layer-Control zum Ein-/Ausblenden
    - Legende und Info-Panel
"""

import logging

import folium
import geopandas as gpd
import numpy as np
import pandas as pd
from folium.plugins import MarkerCluster, MiniMap

from paketstation.config import OUTPUT_MAP_HTML

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Farbskalierung
# ---------------------------------------------------------------------------


def _score_to_color(score: float) -> str:
    """Gibt einen Hex-Farbwert für einen Score (0–100) zurück."""
    # Grün (niedrig) → Gelb (mittel) → Rot (hoch)
    stops = [
        (0, "#1a3a2a"),
        (25, "#4a7c59"),
        (50, "#c8a96e"),
        (75, "#d4713a"),
        (100, "#c0392b"),
    ]
    for i in range(len(stops) - 1):
        s0, c0 = stops[i]
        s1, c1 = stops[i + 1]
        if s0 <= score <= s1:
            t = (score - s0) / (s1 - s0)
            r = int(int(c0[1:3], 16) + t * (int(c1[1:3], 16) - int(c0[1:3], 16)))
            g = int(int(c0[3:5], 16) + t * (int(c1[3:5], 16) - int(c0[3:5], 16)))
            b = int(int(c0[5:7], 16) + t * (int(c1[5:7], 16) - int(c0[5:7], 16)))
            return f"#{r:02x}{g:02x}{b:02x}"
    return stops[-1][1]


def _rank_color(rank: int) -> str:
    if rank <= 3:
        return "#c8a96e"
    if rank <= 6:
        return "#8ab87a"
    return "#5b9bd5"


# ---------------------------------------------------------------------------
# Haupt-Visualisierungsfunktion
# ---------------------------------------------------------------------------


def build_map(
    scored: gpd.GeoDataFrame,
    layers: dict,
    top: gpd.GeoDataFrame,
    output_path: str = OUTPUT_MAP_HTML,
    score_percentile_min: float = 20.0,
) -> folium.Map:
    """
    Erstellt die interaktive Folium-Karte.

    Parameters
    ----------
    scored : GeoDataFrame
        Vollständig gescotertes Grid (Output von scoring.score_grid)
    layers : dict
        Rohdaten-Layer (public_transport, shops, parcel_lockers, quartiere)
    top : GeoDataFrame
        Top-Kandidaten (Output von scoring.top_candidates)
    output_path : str
        Speicherpfad der HTML-Datei
    score_percentile_min : float
        Untere Schwelle (Perzentil) – Rasterpunkte darunter werden nicht
        dargestellt (reduziert Datenmenge und verbessert Lesbarkeit)

    Returns
    -------
    folium.Map
    """
    # Karte initialisieren
    m = folium.Map(
        location=[47.376, 8.548],
        zoom_start=13,
        tiles="CartoDB dark_matter",
        prefer_canvas=True,
    )

    # Mini-Übersichtskarte
    MiniMap(tile_layer="CartoDB dark_matter", toggle_display=True).add_to(m)

    # ── Score-Heatmap ────────────────────────────────────────────────────
    heatmap_group = folium.FeatureGroup(name="Score-Heatmap", show=True)

    threshold = np.percentile(scored["score_total"], score_percentile_min)
    visible = scored[scored["score_total"] >= threshold]

    for _, row in visible.iterrows():
        score = row["score_total"]
        color = _score_to_color(score)
        opacity = 0.35 + (score / 100) * 0.40

        popup_html = _grid_popup(row)

        folium.Circle(
            location=[row["lat"], row["lon"]],
            radius=180,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=opacity,
            weight=0,
            popup=folium.Popup(popup_html, max_width=280),
            tooltip=f"Score: {score:.0f}",
        ).add_to(heatmap_group)

    heatmap_group.add_to(m)

    # ── ÖV-Haltestellen ──────────────────────────────────────────────────
    pt_group = folium.FeatureGroup(name="ÖV-Haltestellen", show=True)
    pt_cluster = MarkerCluster(
        options={"maxClusterRadius": 40, "disableClusteringAtZoom": 15}
    ).add_to(pt_group)

    pt_data = layers.get("public_transport", gpd.GeoDataFrame())
    for _, row in pt_data.iterrows():
        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=3,
            color="#5b9bd5",
            fill=True,
            fill_color="#5b9bd5",
            fill_opacity=0.7,
            weight=0.5,
            tooltip=row.get("name") or "ÖV-Haltestelle",
        ).add_to(pt_cluster)

    pt_group.add_to(m)

    # ── Supermärkte ──────────────────────────────────────────────────────
    shop_group = folium.FeatureGroup(name="Supermärkte / Convenience", show=True)

    shop_data = layers.get("shops", gpd.GeoDataFrame())
    for _, row in shop_data.iterrows():
        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=5,
            color="#5cb85c",
            fill=True,
            fill_color="#5cb85c",
            fill_opacity=0.7,
            weight=0.8,
            tooltip=row.get("name") or "Shop",
        ).add_to(shop_group)

    shop_group.add_to(m)

    # ── Bestehende Paketstationen ────────────────────────────────────────
    exist_group = folium.FeatureGroup(name="Bestehende Paketstationen", show=False)

    exist_data = layers.get("parcel_lockers", gpd.GeoDataFrame())
    for _, row in exist_data.iterrows():
        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=8,
            color="#e74c3c",
            fill=True,
            fill_color="#e74c3c",
            fill_opacity=0.3,
            weight=2,
            dash_array="6,4",
            tooltip=f"Paketstation ({row.get('operator') or 'Unbekannt'})",
            popup=folium.Popup(
                f"<b>Bestehende Paketstation</b><br>Betreiber: {row.get('operator') or '–'}",
                max_width=200,
            ),
        ).add_to(exist_group)

    exist_group.add_to(m)

    # ── Top-Kandidaten ───────────────────────────────────────────────────
    top_group = folium.FeatureGroup(name="Top-Kandidaten", show=True)

    for _, row in top.iterrows():
        rank = int(row["rank"])
        color = _rank_color(rank)

        icon_html = f"""
        <div style="
            width:28px; height:28px; border-radius:50%;
            background:{color};
            border:2px solid {color}cc;
            display:flex; align-items:center; justify-content:center;
            font-family:monospace; font-size:12px; font-weight:bold;
            color:#0f1117;
            box-shadow:0 2px 10px rgba(0,0,0,0.7);
        ">{rank}</div>
        """

        folium.Marker(
            location=[row["lat"], row["lon"]],
            icon=folium.DivIcon(html=icon_html, icon_size=(28, 28), icon_anchor=(14, 14)),
            popup=folium.Popup(_top_popup(row), max_width=300),
            tooltip=f"#{rank} {row.get('nearest_quartier', '')} — Score {row['score_total']:.0f}",
        ).add_to(top_group)

    top_group.add_to(m)

    # ── Legende ──────────────────────────────────────────────────────────
    legend_html = _legend_html(top)
    m.get_root().html.add_child(folium.Element(legend_html))

    # ── Layer-Control ────────────────────────────────────────────────────
    folium.LayerControl(collapsed=False).add_to(m)

    # Speichern
    m.save(output_path)
    logger.info(f"Karte gespeichert: {output_path}")
    return m


# ---------------------------------------------------------------------------
# Popup-Templates
# ---------------------------------------------------------------------------


def _grid_popup(row: pd.Series) -> str:
    def bar(val):
        w = int(val)
        color = _score_to_color(val)
        return (
            f'<div style="background:#1e2128;border-radius:2px;height:6px;margin:2px 0 6px">'
            f'<div style="width:{w}%;height:100%;background:{color};border-radius:2px"></div>'
            f"</div>"
        )

    return f"""
    <div style="font-family:monospace;font-size:11px;color:#c8c2b0;background:#13161e;
                padding:12px;border-radius:4px;min-width:220px">
        <div style="font-size:22px;color:#c8a96e;text-align:center;margin-bottom:4px">
            {row["score_total"]:.0f}
        </div>
        <div style="font-size:9px;color:#555;text-align:center;margin-bottom:10px;
                    letter-spacing:0.1em">GESAMT-SCORE</div>
        <div style="color:#666;margin-bottom:6px">{row.get("nearest_quartier", "")}</div>
        <div style="color:#666;font-size:10px">Bevölkerung</div>
        {bar(row["score_pop"])}
        <div style="color:#666;font-size:10px">ÖV-Erreichbarkeit</div>
        {bar(row["score_pt"])}
        <div style="color:#666;font-size:10px">Nahversorgung</div>
        {bar(row["score_shops"])}
        <div style="color:#666;font-size:10px">Konkurrenz-Abstand</div>
        {bar(row["score_competition"])}
        <div style="color:#666;font-size:10px">Fusswegnetz</div>
        {bar(row["score_walkability"])}
        <div style="color:#444;font-size:9px;margin-top:6px">
            Nächste Station: {row.get("nearest_station_m", "–")} m
        </div>
    </div>
    """


def _top_popup(row: pd.Series) -> str:
    rank = int(row["rank"])
    score = row["score_total"]
    color = _rank_color(rank)

    factors = [
        ("Bevölkerung", row["score_pop"]),
        ("ÖV-Haltestellen", row["score_pt"]),
        ("Nahversorgung", row["score_shops"]),
        ("Konkurrenz-Abst.", row["score_competition"]),
        ("Fusswegnetz", row["score_walkability"]),
    ]
    rows_html = "".join(
        f'<tr><td style="color:#666;padding:2px 8px 2px 0">{k}</td>'
        f'<td style="color:#c8c2b0">{v:.0f}/100</td></tr>'
        for k, v in factors
    )

    return f"""
    <div style="font-family:monospace;font-size:11px;color:#c8c2b0;background:#13161e;
                padding:14px;border-radius:4px;min-width:250px">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
            <div style="width:32px;height:32px;border-radius:50%;background:{color};
                        display:flex;align-items:center;justify-content:center;
                        font-weight:bold;color:#0f1117;font-size:14px">#{rank}</div>
            <div>
                <div style="color:#c8a96e;font-size:13px">
                    {row.get("nearest_quartier", "Zürich")}
                </div>
                <div style="color:#555;font-size:9px">Score: {score:.0f}/100</div>
            </div>
        </div>
        <table style="border-collapse:collapse;width:100%">{rows_html}</table>
        <div style="color:#444;font-size:9px;margin-top:8px;border-top:1px solid #2a2d35;
                    padding-top:6px">
            Koordinaten: {row["lat"]:.4f}°N, {row["lon"]:.4f}°E<br>
            Nächste Paketstation: {row.get("nearest_station_m", "–")} m
        </div>
    </div>
    """


# ---------------------------------------------------------------------------
# Legende
# ---------------------------------------------------------------------------


def _legend_html(top: gpd.GeoDataFrame) -> str:
    top_rows = ""
    for _, row in top.head(5).iterrows():
        rank = int(row["rank"])
        color = _rank_color(rank)
        top_rows += (
            f'<div style="display:flex;justify-content:space-between;'
            f'margin-bottom:4px;font-size:10px">'
            f'<span style="color:{color}">#{rank} {row.get("nearest_quartier", "")[:20]}</span>'
            f'<span style="color:#c8a96e">{row["score_total"]:.0f}</span>'
            f"</div>"
        )

    return f"""
    <div style="
        position:fixed; bottom:30px; right:10px; z-index:9999;
        background:#13161e; border:1px solid #2a2d35; border-radius:6px;
        padding:14px; font-family:monospace; min-width:200px;
        box-shadow:0 4px 20px rgba(0,0,0,0.6);
    ">
        <div style="font-size:9px;letter-spacing:0.1em;color:#555;margin-bottom:10px;
                    text-transform:uppercase">Score-Legende</div>
        <div style="display:flex;height:8px;border-radius:2px;overflow:hidden;margin-bottom:4px">
            <div style="flex:1;background:#1a3a2a"></div>
            <div style="flex:1;background:#4a7c59"></div>
            <div style="flex:1;background:#8ab87a"></div>
            <div style="flex:1;background:#c8a96e"></div>
            <div style="flex:1;background:#d4713a"></div>
            <div style="flex:1;background:#c0392b"></div>
        </div>
        <div style="display:flex;justify-content:space-between;
                    font-size:9px;color:#444;margin-bottom:12px">
            <span>0 — niedrig</span><span>100 — hoch</span>
        </div>

        <div style="font-size:9px;letter-spacing:0.1em;color:#555;margin-bottom:8px;
                    text-transform:uppercase">Top 5 Standorte</div>
        {top_rows}

        <div style="font-size:9px;color:#333;margin-top:10px;border-top:1px solid #1e2128;
                    padding-top:8px">
            Daten: BFS STATPOP 2022 + OSM
        </div>
    </div>
    """


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    import os

    from paketstation.data_loader import load_all
    from paketstation.scoring import score_grid, top_candidates

    os.makedirs("output", exist_ok=True)
    layers = load_all(use_cache=True)
    scored = score_grid(layers)
    top = top_candidates(scored, n=10)
    build_map(scored, layers, top)
    print("→ Karte: output/karte.html")
