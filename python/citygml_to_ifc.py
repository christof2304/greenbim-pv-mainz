"""Ein CityGML-LoD2-Gebäude -> georeferenziertes IFC4-Modell (offen, ohne Kaufsoftware).

Abbildung CityGML -> IFC
  bldg:RoofSurface    -> IfcSlab (ROOF), zusammengefasst in einem IfcRoof
  bldg:WallSurface    -> IfcWall
  bldg:GroundSurface  -> IfcSlab (BASESLAB)
  (ClosureSurface wird ignoriert, sie ist nur eine virtuelle Abschlussfläche)
LoD2-Flächen haben keine Dicke. Jede Fläche wird deshalb um eine Bauteildicke
nach innen extrudiert (IfcExtrudedAreaSolid). So entstehen echte Volumenkörper,
die sich in Bonsai, Revit usw. sauber öffnen lassen.

Georeferenz: IfcMapConversion auf EPSG:25832 (ETRS89/UTM32) und DHHN2016. Der
Modellursprung liegt an der Südwestecke des Gebäudes auf Geländehöhe.
Für jede Dachfläche wird zusätzlich das Pset "PV_Potenzial" geschrieben
(Neigung, Azimut, Fläche und Ertrag aus data/poa_lookup.json).

Beispiel:
    python citygml_to_ifc.py ../data/campus_lod2.gml DERPLP150000jSeO ../data/haus_bretzenheim.ifc
    python citygml_to_ifc.py ../data/campus_lod2.gml DERPLP150000jVVf ../data/hs_mainz_gebaeude.ifc
"""
import argparse
import json
import math
import os
import sys

import numpy as np
from lxml import etree

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.georeference
import ifcopenshell.api.geometry
import ifcopenshell.api.material
import ifcopenshell.api.project
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.style
import ifcopenshell.api.unit
import ifcopenshell.validate

from citygml_roofs import NS, newell, orientation, ring_coords
from pv_yield import LOOKUP_JSON, evaluate_roof

THICKNESS = {"RoofSurface": 0.25, "WallSurface": 0.30, "GroundSurface": 0.30}
GML_ID = "{http://www.opengis.net/gml}id"


def read_building(path, gml_id):
    tree = etree.parse(path, etree.XMLParser(huge_tree=True))
    b = tree.getroot().find(f".//bldg:Building[@gml:id='{gml_id}']", NS)
    if b is None:
        sys.exit(f"Gebäude {gml_id} nicht gefunden")
    surfaces = []
    for kind in THICKNESS:
        for s in b.iterfind(f".//bldg:{kind}", NS):
            for poly in s.iterfind(".//gml:Polygon", NS):
                v = ring_coords(poly)
                if len(v) >= 3 and np.linalg.norm(newell(v)) > 1e-4:
                    surfaces.append({"kind": kind, "id": poly.get(GML_ID), "v": v})
    meta = {
        "function": b.findtext("bldg:function", namespaces=NS),
        "roofType": b.findtext("bldg:roofType", namespaces=NS),
        "measuredHeight": b.findtext("bldg:measuredHeight", namespaces=NS),
    }
    return surfaces, meta


def plane_frame(v):
    """Lokales Koordinatensystem einer Fläche: Ursprung, x-Achse (1. Kante), Normale (außen)."""
    n = newell(v)
    n /= np.linalg.norm(n)
    x = v[1] - v[0]
    x -= n * np.dot(x, n)
    x /= np.linalg.norm(x)
    y = np.cross(n, x)
    return v[0], x, y, n


def make_solid(f, v, thickness):
    o, x, y, n = plane_frame(v)
    pts2d = [(float(np.dot(p - o, x)), float(np.dot(p - o, y))) for p in v]
    pts2d.append(pts2d[0])
    poly = f.createIfcPolyline([f.createIfcCartesianPoint(p) for p in pts2d])
    profile = f.createIfcArbitraryClosedProfileDef("AREA", None, poly)
    pos = f.createIfcAxis2Placement3D(
        f.createIfcCartesianPoint([float(c) for c in o]),
        f.createIfcDirection([float(c) for c in n]),
        f.createIfcDirection([float(c) for c in x]),
    )
    # Extrusion entgegen der Außennormalen = ins Gebäudeinnere
    return f.createIfcExtrudedAreaSolid(profile, pos, f.createIfcDirection([0.0, 0.0, -1.0]), thickness)


def build_ifc(surfaces, meta, gml_id, out):
    allv = np.vstack([s["v"] for s in surfaces])
    origin = np.array([math.floor(allv[:, 0].min()), math.floor(allv[:, 1].min()), round(allv[:, 2].min(), 2)])

    f = ifcopenshell.api.project.create_file(version="IFC4")
    api = ifcopenshell.api
    project = api.root.create_entity(f, ifc_class="IfcProject", name="Green BIM – PV-Potenzial HS Mainz")
    api.unit.assign_unit(f, units=[api.unit.add_si_unit(f, unit_type=t)
                                   for t in ("LENGTHUNIT", "AREAUNIT", "VOLUMEUNIT", "PLANEANGLEUNIT")])
    model = api.context.add_context(f, context_type="Model")
    body = api.context.add_context(f, context_type="Model", context_identifier="Body",
                                   target_view="MODEL_VIEW", parent=model)

    api.georeference.add_georeferencing(f, name="EPSG:25832")
    api.georeference.edit_georeferencing(
        f,
        projected_crs={"Name": "EPSG:25832", "Description": "ETRS89 / UTM zone 32N",
                       "GeodeticDatum": "ETRS89", "VerticalDatum": "DHHN2016"},
        coordinate_operation={"Eastings": float(origin[0]), "Northings": float(origin[1]),
                              "OrthogonalHeight": float(origin[2]),
                              "XAxisAbscissa": 1.0, "XAxisOrdinate": 0.0, "Scale": 1.0},
    )

    site = api.root.create_entity(f, ifc_class="IfcSite", name="Mainz")
    building = api.root.create_entity(f, ifc_class="IfcBuilding", name=gml_id)
    storey = api.root.create_entity(f, ifc_class="IfcBuildingStorey", name="LoD2 Hülle")
    api.aggregate.assign_object(f, relating_object=project, products=[site])
    api.aggregate.assign_object(f, relating_object=site, products=[building])
    api.aggregate.assign_object(f, relating_object=building, products=[storey])
    for el in (site, building, storey):
        api.geometry.edit_object_placement(f, product=el)
    pset = api.pset.add_pset(f, product=building, name="CityGML_Herkunft")
    api.pset.edit_pset(f, pset=pset, properties={
        "gml_id": gml_id, "Quelle": "GeoBasis-DE / LVermGeoRP, dl-de/by-2-0",
        "Gebaeudefunktion": meta["function"] or "", "Dachform": meta["roofType"] or "",
        "Hoehe_gemessen": float(meta["measuredHeight"] or 0),
    })

    # Materialien mit Farbe (für die Ansicht in Bonsai)
    mats = {}
    for name, rgb in {"Dach": (0.62, 0.25, 0.20), "Wand": (0.90, 0.88, 0.82), "Bodenplatte": (0.5, 0.5, 0.5)}.items():
        m = api.material.add_material(f, name=name)
        st = api.style.add_style(f, name=name)
        api.style.add_surface_style(f, style=st, ifc_class="IfcSurfaceStyleShading",
                                    attributes={"SurfaceColour": {"Name": None, "Red": rgb[0], "Green": rgb[1], "Blue": rgb[2]}})
        api.style.assign_material_style(f, material=m, style=st, context=body)
        mats[name] = m

    lookup = json.load(open(LOOKUP_JSON, encoding="utf-8")) if os.path.exists(LOOKUP_JSON) else None
    roof = api.root.create_entity(f, ifc_class="IfcRoof", name="Dach")
    api.geometry.edit_object_placement(f, product=roof)
    api.spatial.assign_container(f, relating_structure=storey, products=[roof])

    counts = {"RoofSurface": 0, "WallSurface": 0, "GroundSurface": 0}
    roof_slabs, others = [], []
    for s in surfaces:
        v = s["v"] - origin
        k = s["kind"]
        counts[k] += 1
        if k == "RoofSurface":
            el = api.root.create_entity(f, ifc_class="IfcSlab", predefined_type="ROOF", name=f"Dachfläche {counts[k]}")
            mat = mats["Dach"]
            roof_slabs.append(el)
        elif k == "WallSurface":
            el = api.root.create_entity(f, ifc_class="IfcWall", predefined_type="SOLIDWALL", name=f"Wand {counts[k]}")
            mat = mats["Wand"]
            others.append(el)
        else:
            el = api.root.create_entity(f, ifc_class="IfcSlab", predefined_type="BASESLAB", name=f"Bodenplatte {counts[k]}")
            mat = mats["Bodenplatte"]
            others.append(el)
        api.geometry.edit_object_placement(f, product=el)
        rep = f.createIfcShapeRepresentation(body, "Body", "SweptSolid", [make_solid(f, v, THICKNESS[k])])
        api.geometry.assign_representation(f, product=el, representation=rep)
        api.material.assign_material(f, products=[el], material=mat)
        p = api.pset.add_pset(f, product=el, name="CityGML_Herkunft")
        api.pset.edit_pset(f, pset=p, properties={"gml_id": s["id"] or "", "Flaechentyp": k})
        if k == "RoofSurface":
            tilt, az, area = orientation(s["v"])
            props = {"Neigung": round(tilt, 1), "Azimut": round(az, 1), "Flaeche": round(area, 2)}
            if lookup:
                r = evaluate_roof(lookup, tilt, az, area)
                props.update({"Einstrahlung_kWh_m2a": float(r["irr_kwh_m2"]),
                              "SpezErtrag_kWh_kWp": float(r["yield_kwh_kwp"]),
                              "Potenzial_kWp": float(r["kwp"]), "Potenzial_kWh_a": float(r["kwh_a"]),
                              "Eignung": r["class"]})
            p = api.pset.add_pset(f, product=el, name="PV_Potenzial")
            api.pset.edit_pset(f, pset=p, properties=props)

    api.aggregate.assign_object(f, relating_object=roof, products=roof_slabs)
    api.spatial.assign_container(f, relating_structure=storey, products=others)
    f.write(out)

    log = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(f, log, express_rules=True)
    print(f"{out}: {counts['RoofSurface']} Dachflächen, {counts['WallSurface']} Wände, "
          f"{counts['GroundSurface']} Bodenplatten; Ursprung E={origin[0]:.0f} N={origin[1]:.0f} H={origin[2]:.2f}; "
          f"Validierung: {len(log.statements)} Meldungen")
    for st in log.statements[:10]:
        print("  ", st.get("message", st))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("citygml")
    ap.add_argument("gml_id", help="gml:id des Gebäudes (z. B. per Klick in Cesium ermittelt)")
    ap.add_argument("out")
    a = ap.parse_args()
    surfaces, meta = read_building(a.citygml, a.gml_id)
    build_ifc(surfaces, meta, a.gml_id, a.out)


if __name__ == "__main__":
    main()
