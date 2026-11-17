"""Belegt die geeigneten Dachflächen eines IFC-Modells mit PV-Modulen (IfcSolarDevice).

Das Skript funktioniert mit jedem IFC, das Dachbauteile enthält: mit dem Modell
aus citygml_to_ifc.py ebenso wie mit dem eigenen Revit-Export.

  geneigtes Dach (≥ 10°): Module liegen parallel zur Dachfläche in einem Raster.
                          Zur Traufe/zum Ortgang bleibt ein Randabstand.
                          Hoch- und Querformat werden verglichen, das bessere gewinnt.
  Flachdach (< 10°):      Module werden auf 15° aufgeständert, nach Süden.
                          Den Reihenabstand bestimmt die Sonne zur Wintersonnenwende
                          mittags (Mainz: 90° − 50° − 23,4° ≈ 16,6°): Die vordere
                          Reihe soll die hintere dann gerade nicht verschatten.

Ergebnis: neue IFC-Datei mit
  IfcSolarDeviceType (SOLARPANEL) + n x IfcSolarDevice (gemappte Geometrie)
  Pset "PV_Modul" am Typ, Pset "PV_Belegung" an jeder belegten Dachfläche,
  Pset "PV_Anlage" am Gebäude (Summe kWp, kWh/a, CO2-Einsparung)

Beispiel:
    python module_layout.py ../data/haus_bretzenheim.ifc ../data/haus_bretzenheim_pv.ifc
"""
import argparse
import json
import math
import sys

import numpy as np
from shapely.geometry import box
from shapely import affinity

import ifcopenshell
import ifcopenshell.api.geometry
import ifcopenshell.api.material
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.style
import ifcopenshell.api.type
import ifcopenshell.util.element as ue
import ifcopenshell.validate

from ifc_roofs import roof_planes
from pv_yield import LOOKUP_JSON, interp

# Modul: generisches 430-Wp-Glas-Glas-Modul
MOD_L, MOD_W, MOD_T, MOD_WP = 1.722, 1.134, 0.035, 430
GAP = 0.02                 # Fuge zwischen Modulen
SETBACK_PITCHED = 0.40     # Randabstand geneigtes Dach
SETBACK_FLAT = 1.00        # Randabstand Flachdach (Attika, Wartungsweg)
RACK_TILT = 15.0
WINTER_SUN = 16.6          # Sonnenhöhe 21.12. mittags in Mainz
MIN_YIELD = 800            # kWh/kWp a – darunter nicht belegen
CO2_G_PER_KWH = 380        # Strommix DE (UBA, ca. 2024) – im Vortrag diskutieren
MOUNT_GAP = 0.12           # Abstand Modul–Dachhaut (Schienen)


def pack(poly, cell_u, cell_v, pitch_v, phases=4):
    """Rechteck-Raster in Polygon packen; mehrere Phasenlagen probieren, beste zurückgeben."""
    minx, miny, maxx, maxy = poly.bounds
    best = []
    for pu in range(phases):
        for pv in range(phases):
            x0 = minx + pu * cell_u / phases
            y0 = miny + pv * pitch_v / phases
            cells = []
            y = y0
            while y + cell_v <= maxy + 1e-9:
                x = x0
                while x + cell_u <= maxx + 1e-9:
                    if poly.contains(box(x, y, x + cell_u, y + cell_v)):
                        cells.append((x, y))
                    x += cell_u + GAP
                y += pitch_v
            if len(cells) > len(best):
                best = cells
    return best


def layout_plane(p):
    """Gibt Liste von 4x4-Matrizen (Modul-Ursprung = Ecke, x = Modullänge, y = Modulbreite, z = Normale)."""
    o, u, v, n = p["origin"], p["u"], p["v"], p["n"]
    mats = []
    if p["tilt"] >= 10:
        poly = p["polygon"].buffer(-SETBACK_PITCHED, join_style=2)
        if poly.is_empty:
            return [], p["tilt"], p["azimuth"]
        variants = [(MOD_L, MOD_W), (MOD_W, MOD_L)]  # quer / hoch
        res = max(((cu, cv, pack(poly, cu, cv, cv + GAP)) for cu, cv in variants), key=lambda r: len(r[2]))
        cu, cv, cells = res
        for x, y in cells:
            origin = o + u * x + v * y + n * MOUNT_GAP
            if cu == MOD_L:
                ax, ay = u, v
            else:
                ax, ay = v, -u
                origin = origin + u * cu  # Ecke so wählen, dass das Modul in der Zelle liegt
            mats.append(np.column_stack([np.append(ax, 0), np.append(ay, 0), np.append(n, 0), np.append(origin, 1)]))
        return mats, p["tilt"], p["azimuth"]

    # Flachdach: Rahmen auf Süd (Karte) drehen
    rot = p["north_rotation"]
    north = np.array([-math.sin(rot), math.cos(rot), 0.0])  # Kartennord im Modellsystem
    east = np.array([math.cos(rot), math.sin(rot), 0.0])
    # Polygon aus (u,v)-Ebenenkoordinaten in (Ost,Nord)-Koordinaten umrechnen
    def to_en(x, y):
        q = u * x + v * y
        return float(np.dot(q, east)), float(np.dot(q, north))
    poly_en = affinity.affine_transform(p["polygon"], [float(np.dot(u, east)), float(np.dot(v, east)),
                                                        float(np.dot(u, north)), float(np.dot(v, north)), 0, 0])
    poly_en = poly_en.buffer(-SETBACK_FLAT, join_style=2)
    if poly_en.is_empty:
        return [], RACK_TILT, 180.0
    t = math.radians(RACK_TILT)
    depth = MOD_W * math.cos(t)
    pitch = depth + MOD_W * math.sin(t) / math.tan(math.radians(WINTER_SUN))
    cells = pack(poly_en, MOD_L, depth, pitch)
    up_slope = north * math.cos(t) + np.array([0, 0, 1.0]) * math.sin(t)   # Modul steigt nach Norden an
    normal = np.cross(east, up_slope)
    for x, y in cells:
        d = east * x + north * y
        # Höhe der (evtl. leicht geneigten) Dachebene an dieser Stelle: n · (p − o) = 0
        dz = -(n[0] * d[0] + n[1] * d[1]) / n[2]
        origin = o + d + np.array([0, 0, dz + 0.30])  # Unterkonstruktion 30 cm
        mats.append(np.column_stack([np.append(east, 0), np.append(up_slope, 0), np.append(normal, 0), np.append(origin, 1)]))
    return mats, RACK_TILT, 180.0


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("dst")
    a = ap.parse_args()

    f = ifcopenshell.open(a.src)
    api = ifcopenshell.api
    lookup = json.load(open(LOOKUP_JSON, encoding="utf-8"))
    body = next(c for c in f.by_type("IfcGeometricRepresentationSubContext") if c.ContextIdentifier == "Body") \
        if f.by_type("IfcGeometricRepresentationSubContext") else f.by_type("IfcGeometricRepresentationContext")[0]

    # Modultyp mit Geometrie (wird für jedes Modul nur referenziert)
    mtype = api.root.create_entity(f, ifc_class="IfcSolarDeviceType", predefined_type="SOLARPANEL",
                                   name=f"PV-Modul {MOD_WP} Wp")
    prof = f.createIfcRectangleProfileDef("AREA", None,
                                          f.createIfcAxis2Placement2D(f.createIfcCartesianPoint((MOD_L / 2, MOD_W / 2))),
                                          MOD_L, MOD_W)
    solid = f.createIfcExtrudedAreaSolid(prof, f.createIfcAxis2Placement3D(f.createIfcCartesianPoint((0.0, 0.0, 0.0))),
                                         f.createIfcDirection((0.0, 0.0, 1.0)), MOD_T)
    api.geometry.assign_representation(f, product=mtype, representation=f.createIfcShapeRepresentation(
        body, "Body", "SweptSolid", [solid]))
    mat = api.material.add_material(f, name="PV-Modul Glas-Glas")
    st = api.style.add_style(f, name="PV-Modul")
    api.style.add_surface_style(f, style=st, ifc_class="IfcSurfaceStyleShading",
                                attributes={"SurfaceColour": {"Name": None, "Red": 0.05, "Green": 0.10, "Blue": 0.30}})
    api.style.assign_material_style(f, material=mat, style=st, context=body)
    api.material.assign_material(f, products=[mtype], material=mat)
    ps = api.pset.add_pset(f, product=mtype, name="PV_Modul")
    api.pset.edit_pset(f, pset=ps, properties={"Nennleistung_Wp": float(MOD_WP), "Laenge": MOD_L,
                                               "Breite": MOD_W, "Dicke": MOD_T, "Technologie": "Mono-Si, Glas-Glas"})

    total_n = total_kwp = total_kwh = 0
    for p in roof_planes(f):
        mats, t_eff, a_eff = layout_plane(p)
        spec = float(interp(lookup, "yield_kwh_kwp", t_eff, a_eff))
        el = p["element"]
        if spec < MIN_YIELD or not mats:
            print(f"{el.Name}: nicht belegt (spez. Ertrag {spec:.0f} kWh/kWp, {len(mats)} Module möglich)")
            continue
        container = ue.get_container(el) or ue.get_container(ue.get_aggregate(el))
        modules = []
        for i, m in enumerate(mats):
            d = api.root.create_entity(f, ifc_class="IfcSolarDevice", predefined_type="SOLARPANEL",
                                       name=f"PV {el.Name} #{i + 1}")
            api.geometry.edit_object_placement(f, product=d, matrix=m)
            modules.append(d)
        api.type.assign_type(f, related_objects=modules, relating_type=mtype)
        api.spatial.assign_container(f, relating_structure=container, products=modules)
        kwp = len(mats) * MOD_WP / 1000
        kwh = kwp * spec
        ps = api.pset.add_pset(f, product=el, name="PV_Belegung")
        api.pset.edit_pset(f, pset=ps, properties={
            "Anzahl_Module": len(mats), "Leistung_kWp": round(kwp, 2), "SpezErtrag_kWh_kWp": round(spec),
            "Ertrag_kWh_a": round(kwh), "Modulneigung": round(t_eff, 1), "Modulazimut": round(a_eff, 1),
            "Belegung": "aufgeständert Süd" if p["tilt"] < 10 else "dachparallel"})
        print(f"{el.Name}: {len(mats)} Module, {kwp:.1f} kWp, {spec:.0f} kWh/kWp -> {kwh:,.0f} kWh/a")
        total_n += len(mats)
        total_kwp += kwp
        total_kwh += kwh

    bld = (f.by_type("IfcBuilding") or [None])[0]
    if bld is not None and total_n:
        ps = api.pset.add_pset(f, product=bld, name="PV_Anlage")
        api.pset.edit_pset(f, pset=ps, properties={
            "Anzahl_Module": total_n, "Leistung_kWp": round(total_kwp, 2), "Ertrag_kWh_a": round(total_kwh),
            "CO2_Einsparung_t_a": round(total_kwh * CO2_G_PER_KWH / 1e6, 1)})
    f.write(a.dst)
    log = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(f, log, express_rules=True)
    print(f"Summe: {total_n} Module, {total_kwp:.1f} kWp, {total_kwh:,.0f} kWh/a, "
          f"≈ {total_kwh * CO2_G_PER_KWH / 1e6:.1f} t CO2/a -> {a.dst} (Validierung: {len(log.statements)} Meldungen)")
    for s in log.statements[:5]:
        print("  ", s.get("message", s))


if __name__ == "__main__":
    main()
