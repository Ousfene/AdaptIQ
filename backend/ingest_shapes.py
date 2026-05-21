"""
ingest_shapes.py
Step 3 of the geography shape pipeline.

Downloads Natural Earth 110m GeoJSON (once) and generates SVG silhouettes
for every geography row in visual_questions that has an iso2 code.

Run from adaptiq-backend/:
    python.exe ingest_shapes.py

Requirements:
    pip install psycopg2-binary requests
    (no extra geo libraries needed — pure Python coordinate math)
"""

import json
import math
import hashlib
import os
import sys
import psycopg2
import urllib.request

# ── Config ────────────────────────────────────────────────────────────────────

DB = dict(host="localhost", port=5432, dbname="adaptiq_db",
          user="adaptiq", password="adaptiq")

GEOJSON_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector"
    "/master/geojson/ne_110m_admin_0_countries.geojson"
)
GEOJSON_LOCAL = "ne_110m_countries.geojson"

SVG_WIDTH  = 200
SVG_HEIGHT = 150
PADDING    = 8       # px padding inside the viewBox
FILL_COLOR = "#4A90D9"
BG_COLOR   = "transparent"


# ── GeoJSON download ──────────────────────────────────────────────────────────

def ensure_geojson():
    if os.path.exists(GEOJSON_LOCAL) and os.path.getsize(GEOJSON_LOCAL) > 10_000:
        print(f"Using cached {GEOJSON_LOCAL}")
        return
    print(f"Downloading Natural Earth GeoJSON from GitHub...")
    headers = {"User-Agent": "AdaptIQ-PFE/1.0"}
    req = urllib.request.Request(GEOJSON_URL, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        with open(GEOJSON_LOCAL, "wb") as f:
            f.write(data)
        print(f"Downloaded {len(data):,} bytes → {GEOJSON_LOCAL}")
    except Exception as e:
        print(f"Download failed: {e}")
        print()
        print("Manual download:")
        print(f"  URL: {GEOJSON_URL}")
        print(f"  Save as: {GEOJSON_LOCAL} in your adaptiq-backend/ folder")
        sys.exit(1)


# ── GeoJSON → country lookup ──────────────────────────────────────────────────

def load_country_features(path: str) -> dict:
    """
    Returns dict: iso2_upper -> list of polygon coordinate rings.
    Each ring is a list of [lon, lat] pairs.
    Handles both Polygon and MultiPolygon geometry types.
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    lookup = {}
    for feature in data["features"]:
        props = feature.get("properties", {})
        # Natural Earth uses ISO_A2 — fall back to ADM0_A3 for edge cases
        iso2 = (
            props.get("ISO_A2") or
            props.get("iso_a2") or
            props.get("ADM0_A3", "")[:2]
        ).upper().strip()

        if not iso2 or iso2 in ("-1", ""):
            continue

        geom = feature.get("geometry", {})
        if not geom:
            continue

        rings = []  # list of coordinate rings (each ring = list of [lon, lat])

        if geom["type"] == "Polygon":
            # outer ring only (index 0), skip holes
            rings.append(geom["coordinates"][0])

        elif geom["type"] == "MultiPolygon":
            for polygon in geom["coordinates"]:
                rings.append(polygon[0])  # outer ring of each polygon

        if rings:
            lookup[iso2] = rings

    print(f"Loaded {len(lookup)} countries from GeoJSON")
    return lookup


# ── Coordinate projection → SVG path ─────────────────────────────────────────

def rings_to_svg(rings: list, width: int, height: int, padding: int) -> str:
    """
    Project geographic coordinate rings to a normalized SVG path string.

    Steps:
      1. Collect all points across all rings to find bounding box.
      2. Scale and translate to fit within (width x height) with padding.
      3. Emit one SVG <path> with all rings as subpaths (using M...Z per ring).
    """
    # 1. Collect all points
    all_lons = []
    all_lats = []
    for ring in rings:
        for lon, lat in ring:
            all_lons.append(lon)
            all_lats.append(lat)

    if not all_lons:
        return ""

    min_lon, max_lon = min(all_lons), max(all_lons)
    min_lat, max_lat = min(all_lats), max(all_lats)

    lon_span = max_lon - min_lon or 1
    lat_span = max_lat - min_lat or 1

    # 2. Scale to fit with padding, preserving aspect ratio
    draw_w = width  - 2 * padding
    draw_h = height - 2 * padding

    scale = min(draw_w / lon_span, draw_h / lat_span)

    # Center within the viewBox
    scaled_w = lon_span * scale
    scaled_h = lat_span * scale
    offset_x = padding + (draw_w - scaled_w) / 2
    offset_y = padding + (draw_h - scaled_h) / 2

    def project(lon, lat):
        x = (lon - min_lon) * scale + offset_x
        # Flip Y: SVG y=0 is top, latitude increases upward
        y = (max_lat - lat) * scale + offset_y
        return round(x, 2), round(y, 2)

    # 3. Build SVG path data — one subpath (M...Z) per ring
    path_parts = []
    for ring in rings:
        if len(ring) < 3:
            continue
        points = [project(lon, lat) for lon, lat in ring]
        coords = " ".join(f"{x},{y}" for x, y in points)
        path_parts.append(f"M {coords} Z")

    return " ".join(path_parts)


def make_svg(rings: list) -> str:
    """Wrap path data in a minimal SVG."""
    path_data = rings_to_svg(rings, SVG_WIDTH, SVG_HEIGHT, PADDING)
    if not path_data:
        return ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}" '
        f'width="{SVG_WIDTH}" height="{SVG_HEIGHT}">'
        f'<path d="{path_data}" fill="{FILL_COLOR}" stroke="white" stroke-width="0.5"/>'
        f'</svg>'
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ensure_geojson()
    country_features = load_country_features(GEOJSON_LOCAL)

    conn = psycopg2.connect(**DB)
    cur  = conn.cursor()

    # Fetch all geography rows that have iso2 but no shape yet
    cur.execute("""
        SELECT id, iso2
        FROM visual_questions
        WHERE topic = 'geography'
        AND iso2 IS NOT NULL
        AND shape_svg IS NULL
        ORDER BY iso2;
    """)
    rows = cur.fetchall()
    print(f"\nRows needing shapes: {len(rows)}")

    generated = 0
    skipped   = 0

    for row_id, iso2 in rows:
        rings = country_features.get(iso2)
        if not rings:
            # Try lowercase (some GeoJSON sources vary)
            rings = country_features.get(iso2.upper())

        if not rings:
            print(f"  SKIP {iso2} — not found in GeoJSON")
            skipped += 1
            continue

        svg = make_svg(rings)
        if not svg:
            print(f"  SKIP {iso2} — empty SVG generated")
            skipped += 1
            continue

        cur.execute(
            "UPDATE visual_questions SET shape_svg = %s WHERE id = %s",
            (svg, row_id)
        )
        generated += 1

    conn.commit()

    # Verify
    cur.execute("""
        SELECT COUNT(*) FROM visual_questions
        WHERE topic='geography' AND shape_svg IS NOT NULL;
    """)
    filled = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*) FROM visual_questions
        WHERE topic='geography' AND shape_svg IS NULL AND iso2 IS NOT NULL;
    """)
    still_missing = cur.fetchone()[0]

    conn.close()

    print(f"\nDone.")
    print(f"  Generated: {generated} SVGs")
    print(f"  Skipped:   {skipped}  (not in GeoJSON — safe to ignore)")
    print(f"  DB check  — shapes filled: {filled}, still missing: {still_missing}")


if __name__ == "__main__":
    main()
