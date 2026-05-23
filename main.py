"""
main.py – Einstiegspunkt der Paketstation-Standortanalyse

Verwendung:
    python main.py                        # OSM live laden, Folium-HTML ausgeben
    python main.py --cache                # GeoJSON-Cache verwenden
    python main.py --db                   # Daten in PostGIS speichern + API starten
    python main.py --db --from-db         # Daten aus PostGIS lesen (nach erstem --db Lauf)
    python main.py --resolution 200       # Feineres Raster
    python main.py --weights pop=4,pt=5   # Gewichte anpassen
    python main.py --top 15               # 15 Top-Kandidaten
"""

import argparse
import logging
import os
import sys
import time

from config import DEFAULT_WEIGHTS, OUTPUT_DIR
from data_loader import load_all, summarize
from scoring import score_grid, top_candidates


def parse_args():
    parser = argparse.ArgumentParser(description="Paketstation Standort-Analyse Zürich")
    parser.add_argument("--cache", action="store_true")
    parser.add_argument("--db", action="store_true", help="In PostGIS speichern")
    parser.add_argument("--from-db", action="store_true", help="Aus PostGIS lesen")
    parser.add_argument("--serve", action="store_true", help="FastAPI starten")
    parser.add_argument("--resolution", type=int, default=300)
    parser.add_argument("--weights", type=str, default=None)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--min-dist", type=float, default=500)
    parser.add_argument("--no-map", action="store_true")
    parser.add_argument("--output-dir", type=str, default=OUTPUT_DIR)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def parse_weights(s):
    weights = DEFAULT_WEIGHTS.copy()
    if not s:
        return weights
    key_map = {
        "pop": "population",
        "population": "population",
        "pt": "public_transport",
        "transport": "public_transport",
        "shops": "shops",
        "shop": "shops",
        "comp": "competition",
        "competition": "competition",
        "walk": "walkability",
        "walkability": "walkability",
    }
    for item in s.split(","):
        if "=" not in item:
            continue
        k, v = item.strip().split("=", 1)
        canonical = key_map.get(k.strip().lower())
        if canonical:
            try:
                weights[canonical] = float(v)
            except ValueError:
                pass
    return weights


def _force_utf8_console():
    """
    Stellt stdout/stderr auf UTF-8 um. Die Windows-Konsole nutzt sonst cp1252
    und wirft bei Unicode-Zeichen (→, …) einen UnicodeEncodeError.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main():
    _force_utf8_console()
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs("data", exist_ok=True)
    weights = parse_weights(args.weights)

    print("\n" + "=" * 52)
    print("  Paketstation Standort-Analyse Zürich")
    print("=" * 52)
    print(f"  Rasterauflösung : {args.resolution} m")
    print(f"  Gewichte        : {weights}")
    print(f"  PostGIS         : {'ja' if args.db else 'nein'}")
    source = "PostGIS" if args.from_db else ("Cache" if args.cache else "Overpass live")
    print(f"  Quelle          : {source}\n")

    t0 = time.time()

    # DB-Engine
    engine = None
    if args.db or args.from_db:
        from db import create_schema, get_engine, test_connection

        engine = get_engine()
        if not test_connection(engine):
            print("\n✗ PostGIS-Verbindung fehlgeschlagen.")
            print("  Stelle sicher, dass PostgreSQL läuft und die Datenbank existiert.")
            sys.exit(1)
        create_schema(engine)

    # 1. Daten laden
    print("Schritt 1/3: Daten laden …")
    layers = load_all(use_cache=args.cache, use_db=args.from_db, engine=engine)
    summarize(layers)

    if args.db and not args.from_db:
        from db import save_all_layers

        print("  → Speichere Layer in PostGIS …")
        save_all_layers(layers, engine)

    # 2. Scoring
    print("Schritt 2/3: Scoring berechnen …")
    scored = score_grid(layers, resolution_m=args.resolution, weights=weights)
    top = top_candidates(scored, n=args.top, min_distance_m=args.min_dist)

    if args.db:
        from db import save_scored_grid

        print("  → Speichere scored_grid in PostGIS …")
        save_scored_grid(scored, engine)

    # 3. Ausgaben
    print("Schritt 3/3: Ausgaben speichern …")

    top_path = os.path.join(args.output_dir, "top_standorte.csv")
    top[
        [
            "rank",
            "nearest_quartier",
            "lat",
            "lon",
            "score_total",
            "score_pop",
            "score_pt",
            "score_shops",
            "score_competition",
            "score_walkability",
            "nearest_station_m",
        ]
    ].to_csv(top_path, index=False)
    print(f"  CSV:     {top_path}")

    if not args.no_map:
        from visualizer import build_map

        map_path = os.path.join(args.output_dir, "karte.html")
        build_map(scored, layers, top, output_path=map_path)
        print(f"  Karte:   {map_path}")

    geo_path = os.path.join(args.output_dir, "scored_grid.geojson")
    scored.to_file(geo_path, driver="GeoJSON")
    print(f"  GeoJSON: {geo_path}")

    elapsed = time.time() - t0
    print(f"\nDone. Fertig in {elapsed:.1f}s\n")

    print("-- Top 10 Standorte ---------------------------------")
    print(
        top[["rank", "nearest_quartier", "score_total", "score_pop", "score_pt", "score_shops"]]
        .head(10)
        .to_string(index=False, float_format=lambda x: f"{x:.1f}")
    )
    print()

    if args.serve or args.db:
        print("> Starte FastAPI-Server auf http://localhost:8000")
        print("  Karte: http://localhost:8000/")
        print("  Docs:  http://localhost:8000/docs\n")
        import uvicorn

        uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
