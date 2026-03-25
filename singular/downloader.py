import math
import requests
import os
import sys
import xml.etree.ElementTree as ET
from shapely.geometry import Polygon, box
import numpy as np
import time

# Google traffic map tile URL (subdomains mt0-mt3 for load spreading)
TILE_URL = "https://{s}.google.com/vt?lyrs=h@159000000,traffic|seconds_into_week:151200&style=3&x={x}&y={y}&z={z}"
TILE_SUBDOMAINS = ("mt0", "mt1", "mt2", "mt3")

def getTileBounds(x,y, zoom): #x: nro. de orden abcisas, y: nro. de orden ordenadas
    numTiles = 1 << zoom

    lon_deg = x/numTiles*360-180
    lat_rad = math.atan(math.sinh(math.pi*(1-2*y/numTiles)))
    lat_deg = math.degrees(lat_rad)

    north = lat_deg
    south = lat_deg - 360/numTiles
    west = lon_deg
    east = lon_deg + 360/numTiles

    return [north,south,west,east]

def getXY(lat,lng,zoom):
    tile_size = 256
    numTiles = 1 << zoom

    point_x = (tile_size/2 + lng*tile_size/360)*numTiles//tile_size
    sin_y = math.sin(lat*(math.pi / 180))
    point_y=((tile_size / 2) + 0.5 * math.log((1+sin_y)/(1-sin_y)) * -(tile_size / (2 * math.pi))) * numTiles // tile_size

    return (int(point_x),int(point_y))

def generateImage(x, y, zoom, count, path):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    os.makedirs(path, exist_ok=True)
    file_name = f"Foto-{count}.png"
    file_path = os.path.join(path, file_name)
    response = None
    for s in TILE_SUBDOMAINS:
        try_url = TILE_URL.format(s=s, x=x, y=y, z=zoom)
        response = requests.get(try_url, headers=headers, timeout=15)
        if response.status_code == 200 and len(response.content) > 100:
            with open(file_path, "wb") as f:
                f.write(response.content)
            print(f"Foto-{count} saved successfully (tile {x},{y} z={zoom})")
            return
        if response.status_code != 200:
            print(f"  {s}: status {response.status_code} for tile {x},{y}")

    print(f"Error: could not download tile {x},{y} (tried all subdomains). Last status: {response.status_code}")

def calculatePolygonBounds(coordinates):
    if not coordinates:
        return None, None, None, None
    
    x_min = x_max = coordinates[0][0]
    y_min = y_max = coordinates[0][1]

    for x,y in coordinates:
        if x<x_min:
            x_min = x
        elif x>x_max:
            x_max = x
        if y<y_min:
            y_min = y
        elif y>y_max:
            y_max = y
    
    return x_min, x_max, y_min, y_max

def tile_intersects_polygon(tile_x, tile_y, zoom, polygon):
    """Return True if the tile bounds intersect the given polygon (lat/lon)."""
    north, south, west, east = getTileBounds(tile_x, tile_y, zoom)
    tile_box = box(west, south, east, north)
    return polygon.intersects(tile_box)

def _find_coordinates(root):
    """Find coordinates element under any common KML namespace."""
    namespaces = (
        "{http://www.opengis.net/kml/2.2}",
        "{http://earth.google.com/kml/2.0}",
        "{http://www.opengis.net/kml/2.3}",
    )
    for ns in namespaces:
        el = root.find(f".//{ns}coordinates")
        if el is not None and el.text and el.text.strip():
            return el.text.strip()
    return None

def operator(path, zoom=20) -> None:
    _, name_kml = os.path.split(path)
    tree = ET.parse(path)
    root = tree.getroot()

    coordinates_text = _find_coordinates(root)
    if not coordinates_text:
        print("No se encontraron coordenadas en el KML. Revisa que el archivo tenga un polígono con <coordinates>.")
        return

    coordinates_list = [coord.strip().split(",")[:2] for coord in coordinates_text.split()]
    if not coordinates_list:
        print("Coordenadas vacías en el KML.")
        return
    # KML order is longitude,latitude; Shapely uses (x,y) = (lon, lat)
    polygon_coordinates = [(float(c[0]), float(c[1])) for c in coordinates_list if len(c) == 2]
    if len(polygon_coordinates) < 3:
        print("Se necesitan al menos 3 puntos para un polígono.")
        return
    polygon = Polygon(polygon_coordinates)
    vertices_polygon = list(polygon.exterior.coords)

    vertices = []
    for i in range(len(vertices_polygon)):
        lon_pt, lat_pt = vertices_polygon[i][0], vertices_polygon[i][1]
        vertices.append(getXY(lat_pt, lon_pt, zoom=zoom))

    min_x, max_x, min_y, max_y = calculatePolygonBounds(vertices)

    # Only count tiles that intersect the polygon
    tiles_to_download = [
        (i, j) for i in range(min_x, max_x + 1) for j in range(min_y, max_y + 1)
        if tile_intersects_polygon(i, j, zoom, polygon)
    ]
    total_images = len(tiles_to_download)

    photos_path = os.path.join("Output", f"{name_kml[:-4]}", "Fotografias")
    if not os.path.exists(photos_path):
        os.makedirs(photos_path)

    count = 0
    for i, j in tiles_to_download:
        generateImage(i, j, zoom, count, photos_path)
        if count % 20 == 0:
            time.sleep(1)
        count += 1

# Lima, Peru (center) - example for single-tile test
LIMA_LAT, LIMA_LON = -12.0464, -77.0428

def download_single_tile(lat: float, lon: float, zoom: int = 20, out_dir: str = "Output") -> None:
    """Download one map tile at the given lat/lon and zoom. Use this to test without a KML file."""
    tile_x, tile_y = getXY(lat, lon, zoom)
    path = os.path.join(out_dir, "single_tile")
    print(f"Downloading one tile for lat={lat}, lon={lon} -> tile x={tile_x}, y={tile_y}, zoom={zoom}")
    generateImage(tile_x, tile_y, zoom, 0, path)
    print(f"Saved to: {os.path.abspath(path)}")

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  KML mode:    python downloader.py <path_to.kml> [zoom_level]")
        print("  Single tile: python downloader.py --lat <latitude> --lon <longitude> [--zoom 20]")
        print("  Lima test:   python downloader.py --lima   # downloads one tile for Lima, Peru")
        print("  Downloads Google traffic map tiles. Without a KML, use --lat/--lon or --lima to test.")
        sys.exit(1)

    # Single-tile mode: --lima or --lat / --lon
    if sys.argv[1] == "--lima":
        zoom = 20
        if len(sys.argv) >= 3:
            try:
                zoom = int(sys.argv[2])
            except ValueError:
                pass
        download_single_tile(LIMA_LAT, LIMA_LON, zoom=zoom)
        print("Done.")
        return

    lat = lon = None
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--lat" and i + 1 < len(args):
            try:
                lat = float(args[i + 1])
            except ValueError:
                pass
        elif a == "--lon" and i + 1 < len(args):
            try:
                lon = float(args[i + 1])
            except ValueError:
                pass
    if lat is not None and lon is not None:
        zoom = 20
        for i, a in enumerate(args):
            if a == "--zoom" and i + 1 < len(args):
                try:
                    zoom = int(args[i + 1])
                    break
                except ValueError:
                    pass
        download_single_tile(lat, lon, zoom=zoom)
        print("Done.")
        return

    # KML mode
    path = os.path.abspath(sys.argv[1])
    if not os.path.isfile(path):
        print(f"Error: file not found: {path}")
        sys.exit(1)

    zoom = 20
    if len(sys.argv) >= 3:
        try:
            zoom = int(sys.argv[2])
        except ValueError:
            print("Warning: invalid zoom, using 20")

    name_kml = os.path.basename(path)
    if not (name_kml.lower().endswith(".kml") or name_kml.lower().endswith(".kmlw")):
        print("Warning: expected .kml or .kmlw file.")

    print(f"Processing: {path} (zoom={zoom})")
    operator(path, zoom=zoom)
    print("Done.")

if __name__ == '__main__':
    main()