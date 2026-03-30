import cv2
import numpy as np
import sqlite3
import os
import sys
import re
import glob

TRAFFIC_COLORS = {
    "dark_red": (169, 39, 39),
    "red":      (242, 78, 66),
    "yellow":   (255, 207, 67),
    "green":    (22, 224, 152),
}

DEFAULT_THRESHOLD = 30


def count_color_pixels(image_bgr, color_rgb, threshold):
    """Count pixels matching a specific RGB color within a BGR image."""
    color_bgr = np.array([color_rgb[2], color_rgb[1], color_rgb[0]], dtype=np.uint8)
    lower = np.clip(color_bgr.astype(int) - threshold, 0, 255).astype(np.uint8)
    upper = np.clip(color_bgr.astype(int) + threshold, 0, 255).astype(np.uint8)
    mask = cv2.inRange(image_bgr, lower, upper)
    return int(np.count_nonzero(mask))


def analyze_tile(image_path, threshold=DEFAULT_THRESHOLD):
    """Return pixel counts per traffic color for a single tile image."""
    image = cv2.imread(image_path)
    if image is None:
        print(f"  Warning: could not read {image_path}")
        return None

    results = {}
    for name, rgb in TRAFFIC_COLORS.items():
        results[name] = count_color_pixels(image, rgb, threshold)
    results["total"] = sum(results.values())
    return results


_TILE_RE = re.compile(r"Tile_(\d+)_(\d+)\.png$")

def parse_tile_filename(filename):
    """Extract (tile_x, tile_y) from a filename like Tile_12345_67890.png."""
    m = _TILE_RE.search(filename)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def init_database(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tile_analysis (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            tile_x          INTEGER NOT NULL,
            tile_y          INTEGER NOT NULL,
            zoom            INTEGER NOT NULL,
            dark_red_pixels INTEGER NOT NULL,
            red_pixels      INTEGER NOT NULL,
            yellow_pixels   INTEGER NOT NULL,
            green_pixels    INTEGER NOT NULL,
            total_pixels    INTEGER NOT NULL,
            analyzed_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def process_tiles(tiles_dir, zoom, db_path, threshold=DEFAULT_THRESHOLD):
    """Analyze every Tile_*_*.png in *tiles_dir* and write results to SQLite."""
    tile_files = sorted(glob.glob(os.path.join(tiles_dir, "Tile_*_*.png")))
    if not tile_files:
        print(f"No tile images found in {tiles_dir}")
        return

    conn = init_database(db_path)
    cur = conn.cursor()

    print(f"Analyzing {len(tile_files)} tiles (threshold={threshold}) ...")

    for i, filepath in enumerate(tile_files):
        tile_x, tile_y = parse_tile_filename(os.path.basename(filepath))
        if tile_x is None:
            print(f"  Skipping {filepath}: could not parse coordinates")
            continue

        r = analyze_tile(filepath, threshold)
        if r is None:
            continue

        cur.execute(
            "INSERT INTO tile_analysis "
            "(tile_x, tile_y, zoom, dark_red_pixels, red_pixels, yellow_pixels, green_pixels, total_pixels) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (tile_x, tile_y, zoom, r["dark_red"], r["red"], r["yellow"], r["green"], r["total"]),
        )

        if (i + 1) % 100 == 0:
            conn.commit()
            print(f"  {i + 1}/{len(tile_files)} tiles processed ...")

    conn.commit()

    row = cur.execute(
        "SELECT COUNT(*), "
        "COALESCE(SUM(dark_red_pixels),0), "
        "COALESCE(SUM(red_pixels),0), "
        "COALESCE(SUM(yellow_pixels),0), "
        "COALESCE(SUM(green_pixels),0), "
        "COALESCE(SUM(total_pixels),0) "
        "FROM tile_analysis"
    ).fetchone()

    print(f"\n--- Analysis complete ---")
    print(f"Tiles analyzed : {row[0]}")
    print(f"Dark red pixels: {row[1]}")
    print(f"Red pixels     : {row[2]}")
    print(f"Yellow pixels  : {row[3]}")
    print(f"Green pixels   : {row[4]}")
    print(f"Total traffic  : {row[5]}")
    print(f"Database       : {os.path.abspath(db_path)}")

    conn.close()


def run_pipeline(kml_path, zoom=20, threshold=DEFAULT_THRESHOLD, db_path=None):
    """Single entry-point: KML in -> SQLite database out.

    1. Downloads all traffic tiles that intersect the KML polygon.
    2. Applies the 4 color filters to every tile.
    3. Stores per-tile pixel counts in an SQLite database.

    Returns the absolute path to the generated database, or None on error.
    """
    kml_path = os.path.abspath(kml_path)
    if not os.path.isfile(kml_path):
        print(f"Error: file not found: {kml_path}")
        return None

    from downloader import operator as download_tiles

    print(f"=== Downloading tiles from {kml_path} (zoom={zoom}) ===")
    photos_dir = download_tiles(kml_path, zoom=zoom)
    if photos_dir is None:
        print("Download failed — aborting analysis.")
        return None

    if db_path is None:
        db_path = os.path.join(photos_dir, "..", "traffic_analysis.db")
    db_path = os.path.abspath(db_path)

    print(f"\n=== Analyzing tiles in {photos_dir} ===")
    process_tiles(photos_dir, zoom, db_path, threshold)
    return db_path


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python analyzer.py <path_to.kml> [--zoom 20] [--threshold 0] [--db results.db]")
        print()
        print("Example:")
        print("  python analyzer.py data/mi_area.kml --zoom 20 --threshold 0")
        sys.exit(1)

    target = sys.argv[1]

    zoom = 20
    threshold = DEFAULT_THRESHOLD
    db_path = None

    args = sys.argv[2:]
    for idx, arg in enumerate(args):
        if arg == "--zoom" and idx + 1 < len(args):
            try:
                zoom = int(args[idx + 1])
            except ValueError:
                pass
        elif arg == "--threshold" and idx + 1 < len(args):
            try:
                threshold = int(args[idx + 1])
            except ValueError:
                pass
        elif arg == "--db" and idx + 1 < len(args):
            db_path = args[idx + 1]

    if target.lower().endswith((".kml", ".kmlw")):
        run_pipeline(target, zoom=zoom, threshold=threshold, db_path=db_path)
    elif os.path.isdir(target):
        if db_path is None:
            db_path = os.path.join(target, "..", "traffic_analysis.db")
        db_path = os.path.abspath(db_path)
        process_tiles(target, zoom, db_path, threshold)
    else:
        print(f"Error: {target} is not a .kml file or a directory of tiles.")
        sys.exit(1)


if __name__ == "__main__":
    main()
