#!/usr/bin/env python3
"""Paris pink-blossom tree map with leaf-shaped markers."""

from __future__ import annotations

import csv
import urllib.request
from pathlib import Path

import folium
from folium import Element
from folium.plugins import FastMarkerCluster


PARIS_CSV_URL = (
    "https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/les-arbres/exports/csv"
    "?lang=en&timezone=Europe%2FParis&use_labels=true&delimiter=%2C"
)

RAW_CSV_PATH = Path("paris_trees.csv")
OUT_DIR = Path("output")
FILTERED_CSV_PATH = OUT_DIR / "paris_cerisier_a_fleurs_points.csv"
HTML_MAP_PATH = OUT_DIR / "paris_cerisier_leaf_map.html"

TARGET_LABEL = "Cerisier à fleurs"


def download_source_csv() -> None:
    if RAW_CSV_PATH.exists() and RAW_CSV_PATH.stat().st_size > 0:
        print(f"[ok] Using existing {RAW_CSV_PATH}")
        return
    print("[download] Fetching Paris trees CSV export...")
    with urllib.request.urlopen(PARIS_CSV_URL, timeout=180) as resp:
        data = resp.read()
    RAW_CSV_PATH.write_bytes(data)
    print(f"[ok] Saved {RAW_CSV_PATH} ({len(data) / 1024 / 1024:.2f} MB)")


def parse_points() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with RAW_CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("LIBELLE FRANCAIS") or "").strip() != TARGET_LABEL:
                continue
            geo = (row.get("geo_point_2d") or "").strip().strip('"')
            if not geo or "," not in geo:
                continue
            lat_s, lon_s = [x.strip() for x in geo.split(",", 1)]
            try:
                lat = float(lat_s)
                lon = float(lon_s)
            except ValueError:
                continue
            rows.append(
                {
                    "idbase": (row.get("IDBASE") or "").strip(),
                    "arrondissement": (row.get("ARRONDISSEMENT") or "").strip(),
                    "adresse": (row.get("LIEU / ADRESSE") or "").strip(),
                    "genre": (row.get("GENRE") or "").strip(),
                    "espece": (row.get("ESPECE") or "").strip(),
                    "latitude": f"{lat:.7f}",
                    "longitude": f"{lon:.7f}",
                }
            )
    return rows


def write_filtered_csv(rows: list[dict[str, str]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    headers = ["idbase", "arrondissement", "adresse", "genre", "espece", "latitude", "longitude"]
    with FILTERED_CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    print(f"[ok] Wrote {FILTERED_CSV_PATH} ({len(rows)} rows)")


def build_leaf_map(rows: list[dict[str, str]]) -> None:
    points = [[float(r["latitude"]), float(r["longitude"])] for r in rows]
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]

    m = folium.Map(
        location=[48.8566, 2.3522],
        zoom_start=12,
        tiles=None,
        control_scale=True,
        prefer_canvas=True,
    )
    folium.TileLayer("CartoDB positron", name="Clean Streets", overlay=False).add_to(m)

    leaf_css = """
    <style>
      .leaf-dot {
        width: 12px;
        height: 12px;
        background: #ff4da6;
        border: 1px solid #a8005b;
        border-radius: 0 80% 0 80%;
        transform: rotate(-45deg);
        box-shadow: 0 0 1px rgba(90, 0, 40, 0.25);
        opacity: 0.82;
      }
      .leaf-legend {
        position: fixed;
        bottom: 18px;
        left: 18px;
        z-index: 9999;
        background: rgba(255,255,255,0.94);
        border: 1px solid #e0e0e0;
        border-radius: 10px;
        padding: 10px 12px;
        font-family: Arial, sans-serif;
        font-size: 13px;
        line-height: 1.3;
      }
      .leaf-swatch {
        display: inline-block;
        width: 10px;
        height: 10px;
        background: #ff4da6;
        border: 1px solid #a8005b;
        border-radius: 0 80% 0 80%;
        transform: rotate(-45deg);
        margin-right: 8px;
      }
    </style>
    """
    m.get_root().header.add_child(Element(leaf_css))

    callback = """
    function (row) {
      const icon = L.divIcon({
        className: '',
        html: '<div class="leaf-dot"></div>',
        iconSize: [12, 12],
        iconAnchor: [6, 6]
      });
      return L.marker(new L.LatLng(row[0], row[1]), {icon: icon});
    };
    """
    FastMarkerCluster(data=points, callback=callback, name=TARGET_LABEL).add_to(m)

    legend_html = (
        "<div class='leaf-legend'>"
        "<div><b>Paris Blossom Trees</b></div>"
        f"<div style='margin-top:4px;'><span class='leaf-swatch'></span>{TARGET_LABEL}: <b>{len(rows):,}</b></div>"
        "</div>"
    )
    m.get_root().html.add_child(Element(legend_html))

    if points:
        m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])
    folium.LayerControl(collapsed=False).add_to(m)
    m.save(str(HTML_MAP_PATH))
    print(f"[ok] Wrote {HTML_MAP_PATH}")


def main() -> None:
    download_source_csv()
    rows = parse_points()
    write_filtered_csv(rows)
    build_leaf_map(rows)
    print(f"[summary] {TARGET_LABEL}: {len(rows):,} trees in Paris dataset")


if __name__ == "__main__":
    main()
