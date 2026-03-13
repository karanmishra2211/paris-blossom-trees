#!/usr/bin/env python3
"""Create a static PNG map of Paris blossom trees with pink leaf markers."""

from __future__ import annotations

import csv
import math
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance


INPUT_CSV = Path("output/paris_cerisier_a_fleurs_points.csv")
OUT_PNG = Path("output/paris_cerisier_leaf_map.png")
WIDTH, HEIGHT = 1500, 980
PADDING = 70


def lon_to_world_x(lon: float, zoom: int) -> float:
    world = 256 * (2**zoom)
    return (lon + 180.0) / 360.0 * world


def lat_to_world_y(lat: float, zoom: int) -> float:
    world = 256 * (2**zoom)
    lat_rad = math.radians(lat)
    merc_n = math.log(math.tan(math.pi / 4 + lat_rad / 2))
    return (1 - merc_n / math.pi) / 2 * world


def world_x_to_lon(x: float, zoom: int) -> float:
    world = 256 * (2**zoom)
    return x / world * 360.0 - 180.0


def world_y_to_lat(y: float, zoom: int) -> float:
    world = 256 * (2**zoom)
    n = math.pi - 2 * math.pi * y / world
    return math.degrees(math.atan(math.sinh(n)))


def pick_zoom(bounds: tuple[float, float, float, float]) -> int:
    min_lon, min_lat, max_lon, max_lat = bounds
    for z in range(17, 0, -1):
        dx = lon_to_world_x(max_lon, z) - lon_to_world_x(min_lon, z)
        dy = lat_to_world_y(min_lat, z) - lat_to_world_y(max_lat, z)
        if dx <= (WIDTH - 2 * PADDING) and dy <= (HEIGHT - 2 * PADDING):
            return z
    return 10


def load_points() -> list[tuple[float, float]]:
    if not INPUT_CSV.exists():
        raise FileNotFoundError(f"Missing {INPUT_CSV}. Run paris_leaf_blossom_map.py first.")
    points: list[tuple[float, float]] = []
    with INPUT_CSV.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            points.append((float(row["latitude"]), float(row["longitude"])))
    return points


def percentile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("Empty list")
    vals = sorted(values)
    if len(vals) == 1:
        return vals[0]
    pos = (len(vals) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return vals[lo]
    frac = pos - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac


def fetch_basemap(center_lat: float, center_lon: float, zoom: int) -> Image.Image:
    cx = lon_to_world_x(center_lon, zoom)
    cy = lat_to_world_y(center_lat, zoom)
    left = cx - WIDTH / 2
    top = cy - HEIGHT / 2
    right = cx + WIDTH / 2
    bottom = cy + HEIGHT / 2

    tile_size = 256
    n = 2**zoom
    min_tx = int(math.floor(left / tile_size))
    max_tx = int(math.floor(right / tile_size))
    min_ty = int(math.floor(top / tile_size))
    max_ty = int(math.floor(bottom / tile_size))

    canvas = Image.new("RGBA", (WIDTH, HEIGHT), (245, 245, 245, 255))
    for ty in range(min_ty, max_ty + 1):
        if ty < 0 or ty >= n:
            continue
        for tx in range(min_tx, max_tx + 1):
            tx_wrapped = tx % n
            url = f"https://a.basemaps.cartocdn.com/light_all/{zoom}/{tx_wrapped}/{ty}.png"
            try:
                with urllib.request.urlopen(url, timeout=30) as resp:
                    tile = Image.open(resp).convert("RGBA")
            except Exception:
                continue
            px = int(tx * tile_size - left)
            py = int(ty * tile_size - top)
            canvas.alpha_composite(tile, (px, py))

    return canvas


def make_leaf_icon(angle: float) -> Image.Image:
    base = Image.new("RGBA", (24, 24), (0, 0, 0, 0))
    draw = ImageDraw.Draw(base)
    # Star-like bloom marker to match requested style.
    star = [
        (12, 1), (14, 8), (22, 8), (16, 12), (18, 20),
        (12, 15), (6, 20), (8, 12), (2, 8), (10, 8),
    ]
    draw.polygon(star, fill=(255, 48, 160, 225), outline=(160, 0, 85, 240))
    return base.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)


def render_png(points: list[tuple[float, float]]) -> None:
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    # Focus on central Paris by trimming distant outliers.
    min_lat = percentile(lats, 0.03)
    max_lat = percentile(lats, 0.97)
    min_lon = percentile(lons, 0.03)
    max_lon = percentile(lons, 0.97)
    bounds = (min_lon, min_lat, max_lon, max_lat)
    zoom = pick_zoom(bounds)

    min_x0 = lon_to_world_x(bounds[0], 0)
    max_x0 = lon_to_world_x(bounds[2], 0)
    min_y0 = lat_to_world_y(bounds[3], 0)
    max_y0 = lat_to_world_y(bounds[1], 0)
    center_x0 = (min_x0 + max_x0) / 2
    center_y0 = (min_y0 + max_y0) / 2
    center_lon = world_x_to_lon(center_x0, 0)
    center_lat = world_y_to_lat(center_y0, 0)

    base = fetch_basemap(center_lat, center_lon, zoom)
    # Slight fade to mimic a cleaner background style.
    base = ImageEnhance.Brightness(base).enhance(1.08)
    base = ImageEnhance.Color(base).enhance(0.78)

    cx = lon_to_world_x(center_lon, zoom)
    cy = lat_to_world_y(center_lat, zoom)

    leaf_cache = {
        -22: make_leaf_icon(-22),
        -10: make_leaf_icon(-10),
        0: make_leaf_icon(0),
        12: make_leaf_icon(12),
    }
    angles = tuple(leaf_cache.keys())

    for i, (lat, lon) in enumerate(points):
        px = int(lon_to_world_x(lon, zoom) - cx + WIDTH / 2)
        py = int(lat_to_world_y(lat, zoom) - cy + HEIGHT / 2)
        if px < -20 or py < -20 or px > WIDTH + 20 or py > HEIGHT + 20:
            continue
        icon = leaf_cache[angles[i % len(angles)]]
        base.alpha_composite(icon, (px - icon.width // 2, py - icon.height // 2))

    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    base.convert("RGB").save(OUT_PNG, optimize=True, quality=95)
    print(f"[ok] Wrote {OUT_PNG} ({len(points):,} leaf markers, zoom={zoom})")


def main() -> None:
    points = load_points()
    render_png(points)


if __name__ == "__main__":
    main()
