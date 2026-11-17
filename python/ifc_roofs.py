"""Dachebenen aus einem beliebigen IFC-Modell lesen und das PV-Potenzial bewerten.

Damit könnt ihr euer eigenes Hausarbeitsmodell (z. B. als IFC aus Revit exportiert)
auswerten, ohne dass Revit dafür nötig ist:
    python ifc_roofs.py mein_modell.ifc

Vorgehen
  1. Alle Dachbauteile einsammeln: IfcRoof (und alles, was es aggregiert),
     IfcSlab.ROOF und IfcCovering.ROOFING.
  2. Die Geometrie mit dem IfcOpenShell-Geometriekern triangulieren
     (Weltkoordinaten = Projektkoordinaten).
  3. Dreiecke nach Ebene clustern (gleiche Normale, gleicher Abstand). Behalten
     werden nur Ebenen, die nach oben zeigen (Neigung < 80°) und mindestens
     0,6 m breit sind. Stirnflächen von Dachplatten fallen dadurch heraus.
  4. Die Ausrichtung wird auf geografisch Nord bezogen. Grundlage ist
     IfcMapConversion (XAxisAbscissa/Ordinate) oder, falls nicht vorhanden,
     TrueNorth des Kontexts.
  5. Bewertung mit dem Neigung/Azimut-Raster aus pv_yield.py (data/poa_lookup.json).
"""
import argparse
import csv
import json
import math
import sys

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element as ue

from pv_yield import LOOKUP_JSON, evaluate_roof

ANGLE_TOL = math.radians(3)
DIST_TOL = 0.10
MIN_WIDTH = 0.6
MIN_AREA = 1.0


def roof_elements(f):
    els = set(f.by_type("IfcRoof"))
    for r in list(els):
        els.update(ue.get_decomposition(r))
    for s in f.by_type("IfcSlab"):
        if ue.get_predefined_type(s) == "ROOF":
            els.add(s)
    for c in f.by_type("IfcCovering"):
        if ue.get_predefined_type(c) == "ROOFING":
            els.add(c)
    return [e for e in els if e.Representation]


def north_rotation(f):
    """Winkel (rad, gegen den Uhrzeigersinn), um den Modellvektoren in Karten-/Nordsystem gedreht werden."""
    for mc in f.by_type("IfcMapConversion"):
        a, o = mc.XAxisAbscissa, mc.XAxisOrdinate
        if a is not None and o is not None:
            return math.atan2(o, a)
    for ctx in f.by_type("IfcGeometricRepresentationContext"):
        tn = getattr(ctx, "TrueNorth", None)
        if tn is not None:
            x, y = tn.DirectionRatios[:2]
            # TrueNorth = Richtung von Nord im Modell -> Drehung, die sie auf +Y bringt
            return math.atan2(x, y)
    return 0.0


def plane_frame(n):
    z = np.array([0.0, 0.0, 1.0])
    u = np.cross(z, n)  # horizontal, entlang der Traufe
    if np.linalg.norm(u) < 1e-6:
        u = np.array([1.0, 0.0, 0.0])
    u /= np.linalg.norm(u)
    v = np.cross(n, u)  # in der Ebene, hangaufwärts
    return u, v


def cluster_planes(verts, faces):
    tri = verts[faces]
    nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    area2 = np.linalg.norm(nrm, axis=1)
    keep = area2 > 1e-8
    tri, nrm, area2 = tri[keep], nrm[keep], area2[keep]
    nrm = nrm / area2[:, None]
    planes = []
    for t, n, a in zip(tri, nrm, area2):
        if n[2] < math.cos(math.radians(80)):
            continue
        d = float(np.dot(n, t[0]))
        for p in planes:
            if math.acos(min(1.0, float(np.dot(p["n"], n)))) < ANGLE_TOL and abs(p["d"] - d) < DIST_TOL:
                p["tris"].append(t)
                p["area"] += a / 2
                break
        else:
            planes.append({"n": n, "d": d, "tris": [t], "area": a / 2})
    return planes


def roof_planes(f):
    """Liste der Dachebenen: Element, Normale, Ebenen-Rahmen, 2D-Polygon, Neigung, Azimut, Fläche."""
    rot = north_rotation(f)
    st = ifcopenshell.geom.settings()
    st.set("use-world-coords", True)
    result = []
    for el in roof_elements(f):
        try:
            shape = ifcopenshell.geom.create_shape(st, el)
        except RuntimeError:
            continue
        g = shape.geometry
        verts = np.array(g.verts).reshape(-1, 3)
        faces = np.array(g.faces).reshape(-1, 3)
        if len(faces) == 0:
            continue
        for p in cluster_planes(verts, faces):
            n = p["n"]
            u, v = plane_frame(n)
            o = p["tris"][0][0]
            polys = [Polygon([(float(np.dot(q - o, u)), float(np.dot(q - o, v))) for q in t]) for t in p["tris"]]
            poly = unary_union([q.buffer(0.001) for q in polys if q.area > 0]).buffer(-0.001)
            if poly.is_empty or poly.area < MIN_AREA:
                continue
            mrr = poly.minimum_rotated_rectangle
            xs, ys = mrr.exterior.coords.xy
            sides = [math.dist((xs[i], ys[i]), (xs[i + 1], ys[i + 1])) for i in range(2)]
            if min(sides) < MIN_WIDTH:
                continue
            tilt = math.degrees(math.acos(max(-1.0, min(1.0, n[2]))))
            # Normale ins Kartensystem drehen, dann Azimut (0° = Nord, im Uhrzeigersinn)
            e_ = n[0] * math.cos(rot) - n[1] * math.sin(rot)
            n_ = n[0] * math.sin(rot) + n[1] * math.cos(rot)
            az = (math.degrees(math.atan2(e_, n_)) + 360) % 360 if tilt > 0.5 else 180.0
            result.append({"element": el, "n": n, "origin": o, "u": u, "v": v, "polygon": poly,
                           "tilt": tilt, "azimuth": az, "area": poly.area, "north_rotation": rot})
    return result


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ifc")
    ap.add_argument("--csv", help="Ergebnis zusätzlich als CSV speichern")
    a = ap.parse_args()
    f = ifcopenshell.open(a.ifc)
    lookup = json.load(open(LOOKUP_JSON, encoding="utf-8"))
    rows = []
    for p in roof_planes(f):
        r = evaluate_roof(lookup, p["tilt"], p["azimuth"], p["area"])
        rows.append({"GlobalId": p["element"].GlobalId, "Bauteil": p["element"].is_a(),
                     "Name": p["element"].Name, "Neigung": round(p["tilt"], 1),
                     "Azimut": round(p["azimuth"], 1), "Flaeche_m2": round(p["area"], 1), **r})
    if not rows:
        sys.exit("Keine Dachflächen gefunden (IfcRoof / IfcSlab.ROOF / IfcCovering.ROOFING mit Geometrie?)")
    w = max(len(str(r["Name"])) for r in rows)
    print(f"{'Bauteil':<{w}}  Neigung  Azimut   Fläche  kWh/m²a  kWh/kWp    kWp    kWh/a  Eignung")
    for r in rows:
        print(f"{str(r['Name']):<{w}}  {r['Neigung']:6.1f}°  {r['Azimut']:5.0f}°  {r['Flaeche_m2']:6.1f}  "
              f"{r['irr_kwh_m2']:7d}  {r['yield_kwh_kwp']:7d}  {r['kwp']:5.1f}  {r['kwh_a']:7d}  {r['class']}")
    print(f"Summe: {sum(r['kwp'] for r in rows):.1f} kWp, {sum(r['kwh_a'] for r in rows):,} kWh/a")
    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8") as fh:
            wr = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter=";")
            wr.writeheader()
            wr.writerows(rows)


if __name__ == "__main__":
    main()
