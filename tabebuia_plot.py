#!/usr/bin/env python3
"""Download Bengaluru tree census KMZ and plot Tabebuia rosea distribution."""

from __future__ import annotations

import csv
import os
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

# Keep matplotlib/font caches in the project directory for sandbox-safe runs.
os.environ.setdefault("MPLCONFIGDIR", str(Path(".mpl-cache").resolve()))
os.environ.setdefault("XDG_CACHE_HOME", str(Path(".cache").resolve()))

import folium
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from folium.plugins import FastMarkerCluster


KMZ_URL = (
    "https://data.opencity.in/dataset/9151032e-4423-4697-81a2-e29018a4facd/"
    "resource/44623cd8-b167-4c02-bff1-5120e37beabc/download/"
    "8128cdd5-579d-428a-a464-d4578069f296.kmz"
)
KMZ_PATH = Path("bengaluru_trees.kmz")
OUT_DIR = Path("output")
CSV_PATH = OUT_DIR / "tabebuia_rosea_points.csv"
MAP_PATH = OUT_DIR / "tabebuia_rosea_map.png"
HEXBIN_PATH = OUT_DIR / "tabebuia_rosea_density.png"
HTML_MAP_PATH = OUT_DIR / "tabebuia_rosea_google_like.html"

KML_NS = "{http://www.opengis.net/kml/2.2}"
TREE_FIELD = "TreeName"
TARGET_SPECIES = "tabebuia rosea"


def download_kmz() -> None:
    if KMZ_PATH.exists() and KMZ_PATH.stat().st_size > 0:
        print(f"[ok] Using existing {KMZ_PATH}")
        return
    print(f"[download] Fetching {KMZ_URL}")
    with urllib.request.urlopen(KMZ_URL) as resp:
        data = resp.read()
    KMZ_PATH.write_bytes(data)
    print(f"[ok] Saved {KMZ_PATH} ({len(data) / 1024 / 1024:.2f} MB)")


def parse_points() -> tuple[dict[str, int], list[tuple[float, float]], list[dict[str, str]], list[float]]:
    counts: dict[str, int] = {}
    all_points: list[tuple[float, float]] = []
    tabebuia_rows: list[dict[str, str]] = []
    bbox = [999.0, 999.0, -999.0, -999.0]  # min_lon, min_lat, max_lon, max_lat

    with zipfile.ZipFile(KMZ_PATH) as zf:
        kml_files = [n for n in zf.namelist() if n.lower().endswith(".kml")]
        if not kml_files:
            raise RuntimeError("No KML file found in KMZ")
        with zf.open(kml_files[0]) as kmlf:
            context = ET.iterparse(kmlf, events=("end",))
            for _, elem in context:
                if elem.tag != KML_NS + "Placemark":
                    continue

                fields: dict[str, str] = {}
                for sd in elem.findall(".//" + KML_NS + "SimpleData"):
                    fields[sd.attrib.get("name", "")] = (sd.text or "").strip()

                tree_name = fields.get(TREE_FIELD, "").strip()
                if tree_name:
                    counts[tree_name] = counts.get(tree_name, 0) + 1

                coord_el = elem.find(".//" + KML_NS + "coordinates")
                if coord_el is None or not coord_el.text:
                    elem.clear()
                    continue
                parts = coord_el.text.strip().split()[0].split(",")
                if len(parts) < 2:
                    elem.clear()
                    continue

                lon = float(parts[0])
                lat = float(parts[1])
                all_points.append((lon, lat))
                bbox[0] = min(bbox[0], lon)
                bbox[1] = min(bbox[1], lat)
                bbox[2] = max(bbox[2], lon)
                bbox[3] = max(bbox[3], lat)

                if TARGET_SPECIES in tree_name.lower():
                    tabebuia_rows.append(
                        {
                            "OBJECTID": fields.get("OBJECTID", ""),
                            "TreeName": tree_name,
                            "KGISTreeID": fields.get("KGISTreeID", ""),
                            "WardNumber": fields.get("WardNumber", ""),
                            "DepartmentCode": fields.get("DepartmentCode", ""),
                            "longitude": f"{lon:.7f}",
                            "latitude": f"{lat:.7f}",
                        }
                    )

                elem.clear()

    return counts, all_points, tabebuia_rows, bbox


def write_csv(rows: list[dict[str, str]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "OBJECTID",
        "TreeName",
        "KGISTreeID",
        "WardNumber",
        "DepartmentCode",
        "longitude",
        "latitude",
    ]
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"[ok] Wrote {CSV_PATH} ({len(rows)} rows)")


def plot_maps(all_points: list[tuple[float, float]], tabebuia_rows: list[dict[str, str]], bbox: list[float]) -> None:
    tab_lon = [float(r["longitude"]) for r in tabebuia_rows]
    tab_lat = [float(r["latitude"]) for r in tabebuia_rows]
    all_lon = [p[0] for p in all_points]
    all_lat = [p[1] for p in all_points]

    # Style tuned for the "pink bloom" visual emphasis.
    fig, ax = plt.subplots(figsize=(12, 10), dpi=180)
    fig.patch.set_facecolor("#f5f5f5")
    ax.set_facecolor("#fbfbfb")
    ax.scatter(all_lon, all_lat, s=0.08, c="#a6a6a6", alpha=0.22, linewidths=0)
    ax.scatter(
        tab_lon,
        tab_lat,
        s=15,
        marker="*",
        c="#ff1493",
        alpha=0.80,
        linewidths=0.25,
        edgecolors="#b3006b",
    )
    ax.set_xlim(bbox[0], bbox[2])
    ax.set_ylim(bbox[1], bbox[3])
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(
        f"Tabebuia Rosea in Bengaluru (n={len(tabebuia_rows):,})\n"
        "BBMP Tree Census (July 2025 resource)",
        fontsize=14,
        weight="bold",
    )
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(color="#dcdcdc", linestyle="--", linewidth=0.4, alpha=0.7)
    fig.tight_layout()
    fig.savefig(MAP_PATH, bbox_inches="tight")
    plt.close(fig)
    print(f"[ok] Wrote {MAP_PATH}")

    fig2, ax2 = plt.subplots(figsize=(11, 9), dpi=180)
    fig2.patch.set_facecolor("#faf7fa")
    ax2.set_facecolor("#fffafc")
    hb = ax2.hexbin(
        tab_lon,
        tab_lat,
        gridsize=120,
        cmap="RdPu",
        mincnt=1,
        linewidths=0.0,
    )
    cbar = fig2.colorbar(hb, ax=ax2, shrink=0.85)
    cbar.set_label("Tabebuia Rosea count per hex", rotation=90)
    ax2.set_xlim(bbox[0], bbox[2])
    ax2.set_ylim(bbox[1], bbox[3])
    ax2.set_aspect("equal", adjustable="box")
    ax2.set_title("Tabebuia Rosea Density Hotspots in Bengaluru", fontsize=14, weight="bold")
    ax2.set_xlabel("Longitude")
    ax2.set_ylabel("Latitude")
    ax2.grid(color="#ead8e5", linestyle=":", linewidth=0.5, alpha=0.6)
    fig2.tight_layout()
    fig2.savefig(HEXBIN_PATH, bbox_inches="tight")
    plt.close(fig2)
    print(f"[ok] Wrote {HEXBIN_PATH}")


def plot_interactive_map(tabebuia_rows: list[dict[str, str]], bbox: list[float]) -> None:
    center_lat = (bbox[1] + bbox[3]) / 2
    center_lon = (bbox[0] + bbox[2]) / 2
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=11,
        tiles=None,
        control_scale=True,
        prefer_canvas=True,
    )

    # Light, uncluttered basemap to mimic a clean Google-style road map.
    folium.TileLayer("CartoDB positron", name="Clean Streets", overlay=False).add_to(m)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap", overlay=False).add_to(m)

    points = [[float(r["latitude"]), float(r["longitude"])] for r in tabebuia_rows]
    callback = """
        function (row) {
            return L.circleMarker(new L.LatLng(row[0], row[1]), {
                radius: 3,
                color: '#ff1493',
                weight: 0.5,
                fillColor: '#ff1493',
                fillOpacity: 0.65
            });
        };
    """
    FastMarkerCluster(data=points, callback=callback, name="Tabebuia Rosea").add_to(m)

    m.fit_bounds([[bbox[1], bbox[0]], [bbox[3], bbox[2]]])
    folium.LayerControl(collapsed=False).add_to(m)
    m.save(str(HTML_MAP_PATH))
    print(f"[ok] Wrote {HTML_MAP_PATH}")


def print_summary(counts: dict[str, int], tabebuia_count: int) -> None:
    top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:10]
    print("\nTop 10 tree names in the dataset:")
    for name, count in top:
        print(f"  {count:>7,}  {name}")
    print(f"\nTabebuia Rosea count: {tabebuia_count:,}")


def main() -> None:
    download_kmz()
    counts, all_points, tabebuia_rows, bbox = parse_points()
    write_csv(tabebuia_rows)
    plot_maps(all_points, tabebuia_rows, bbox)
    plot_interactive_map(tabebuia_rows, bbox)
    print_summary(counts, len(tabebuia_rows))
    print("\nDone.")


if __name__ == "__main__":
    main()
