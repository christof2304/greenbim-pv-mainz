"""CityGML LoD2 -> Dachflächen mit Neigung, Ausrichtung und Fläche (GeoJSON, WGS84).

Für jede bldg:RoofSurface werden berechnet:
  - Normale (Newell-Verfahren) -> Neigung (tilt, 0° = flach) und Azimut
    (0° = Nord, 90° = Ost, 180° = Süd, 270° = West)
  - wahre (geneigte) Fläche in m²
Die Koordinaten werden nach WGS84 (lon, lat) umgerechnet. Als Höhe wird die
ellipsoidische Höhe ausgegeben (Normalhöhe + Geoidundulation), damit die Flächen
in Cesium mit Cesium World Terrain an der richtigen Stelle liegen.

Beispiel:
    python citygml_roofs.py ../data/campus_lod2.gml ../data/campus_roofs.geojson
"""
import argparse
import sys
import json
import math

import numpy as np
from lxml import etree
from pyproj import Transformer

NS = {
    "core": "http://www.opengis.net/citygml/1.0",
    "bldg": "http://www.opengis.net/citygml/building/1.0",
    "gml": "http://www.opengis.net/gml",
    "gen": "http://www.opengis.net/citygml/generics/1.0",
}
# Geoidundulation GCG2016 im Raum Mainz (Quasigeoid über GRS80). Für eine
# Visualisierung reicht ein konstanter Wert; Abweichung im Stadtgebiet < 0,1 m.
UNDULATION_MAINZ = 48.2
# Dachflächen leicht anheben, damit sie in Cesium nicht mit den Gebäude-Tiles
# flackern (z-fighting). Nur Darstellung - z_min/z_max bleiben unverändert.
OVERLAY_OFFSET = 0.3

TO_WGS84 = Transformer.from_crs(25832, 4326, always_xy=True)


def ring_coords(polygon):
    """Außenring eines gml:Polygon als (n,3)-Array ohne doppelten Endpunkt."""
    ext = polygon.find("gml:exterior//gml:posList", NS)
    if ext is not None:
        v = np.array(ext.text.split(), dtype=float).reshape(-1, 3)
    else:
        v = np.array([p.text.split() for p in polygon.iterfind("gml:exterior//gml:pos", NS)], dtype=float)
    if len(v) > 1 and np.allclose(v[0], v[-1]):
        v = v[:-1]
    return v


def newell(v):
    """Flächennormale * 2*Fläche nach Newell (robust für nicht-planare Ringe)."""
    n = np.zeros(3)
    for i in range(len(v)):
        a, b = v[i], v[(i + 1) % len(v)]
        n += [(a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]), (a[0] - b[0]) * (a[1] + b[1])]
    return n


def orientation(v):
    n = newell(v)
    area = np.linalg.norm(n) / 2
    if area < 1e-6:
        return None
    n /= np.linalg.norm(n)
    if n[2] < 0:  # Dachnormale soll nach oben zeigen
        n = -n
    tilt = math.degrees(math.acos(max(-1.0, min(1.0, n[2]))))
    # UTM-Gitter-Nord weicht in Mainz um < 1° von geografisch Nord ab -> vernachlässigt
    azimuth = (math.degrees(math.atan2(n[0], n[1])) + 360) % 360
    return tilt, azimuth, area


def gen_attr(building, name):
    el = building.find(f"gen:stringAttribute[@name='{name}']/gen:value", NS)
    return el.text if el is not None else None


def extract(path):
    tree = etree.parse(path, etree.XMLParser(huge_tree=True))
    features = []
    for b in tree.getroot().iterfind(".//bldg:Building", NS):
        bid = b.get("{http://www.opengis.net/gml}id")
        func = b.findtext("bldg:function", namespaces=NS)
        roof_type = b.findtext("bldg:roofType", namespaces=NS)
        for rs in b.iterfind(".//bldg:RoofSurface", NS):
            for poly in rs.iterfind(".//gml:Polygon", NS):
                v = ring_coords(poly)
                if len(v) < 3:
                    continue
                o = orientation(v)
                if o is None:
                    continue
                tilt, az, area = o
                lon, lat = TO_WGS84.transform(v[:, 0], v[:, 1])
                h = v[:, 2] + UNDULATION_MAINZ + OVERLAY_OFFSET
                ring = [[round(x, 8), round(y, 8), round(z, 2)] for x, y, z in zip(lon, lat, h)]
                ring.append(ring[0])
                features.append({
                    "type": "Feature",
                    "properties": {
                        "building_id": bid,
                        "surface_id": poly.get("{http://www.opengis.net/gml}id"),
                        "function": func,
                        "roofType": roof_type,
                        "tilt": round(tilt, 1),
                        "azimuth": round(az, 1),
                        "area": round(area, 2),
                        "z_min": round(float(v[:, 2].min()), 2),
                        "z_max": round(float(v[:, 2].max()), 2),
                    },
                    "geometry": {"type": "Polygon", "coordinates": [ring]},
                })
    return features


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("dst")
    a = ap.parse_args()
    feats = extract(a.src)
    with open(a.dst, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f, ensure_ascii=False, separators=(",", ":"))
    total = sum(ft["properties"]["area"] for ft in feats)
    nb = len({ft["properties"]["building_id"] for ft in feats})
    print(f"{len(feats)} Dachflächen von {nb} Gebäuden, {total:,.0f} m² Dachfläche -> {a.dst}")


if __name__ == "__main__":
    main()
