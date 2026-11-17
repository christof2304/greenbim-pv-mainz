"""Schneidet eine CityGML-LoD2-Kachel (RLP, 2x2 km) auf ein Rechteck zu.

Behalten werden alle Gebäude, deren Grundriss-Schwerpunkt (Mittel aller Koordinaten)
im Rechteck liegt. Optional wird srsName auf EPSG-Codes umgeschrieben, damit
Cesium ion & Co. das Koordinatensystem erkennen.

Beispiel (Campus HS Mainz + Bretzenheim, 1,1 km x 1,0 km):
    python clip_citygml.py LoD2_32_444_5536_2_RP.gml ../data/campus_lod2.gml \
        --bbox 444300 5536900 445400 5537900 --epsg
"""
import argparse
import sys
from lxml import etree

NS = {
    "core": "http://www.opengis.net/citygml/1.0",
    "bldg": "http://www.opengis.net/citygml/building/1.0",
    "gml": "http://www.opengis.net/gml",
}
# ETRS89 / UTM32N + DHHN2016-Normalhöhe
EPSG_SRS = "urn:ogc:def:crs,crs:EPSG::25832,crs:EPSG::7837"


def centroid(building):
    xs, ys = [], []
    for pl in building.iterfind(".//gml:posList", NS):
        v = [float(t) for t in pl.text.split()]
        xs += v[0::3]
        ys += v[1::3]
    for p in building.iterfind(".//gml:pos", NS):
        v = [float(t) for t in p.text.split()]
        xs.append(v[0])
        ys.append(v[1])
    if not xs:
        return None
    return sum(xs) / len(xs), sum(ys) / len(ys)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--bbox", nargs=4, type=float, metavar=("XMIN", "YMIN", "XMAX", "YMAX"), required=True)
    ap.add_argument("--epsg", action="store_true", help="srsName auf EPSG:25832+7837 umschreiben")
    a = ap.parse_args()
    xmin, ymin, xmax, ymax = a.bbox

    tree = etree.parse(a.src, etree.XMLParser(huge_tree=True, remove_blank_text=True))
    root = tree.getroot()
    kept = removed = 0
    for m in root.findall("core:cityObjectMember", NS):
        b = m.find("bldg:Building", NS)
        c = centroid(b) if b is not None else None
        if c and xmin <= c[0] <= xmax and ymin <= c[1] <= ymax:
            kept += 1
        else:
            root.remove(m)
            removed += 1

    env = root.find("gml:boundedBy/gml:Envelope", NS)
    if env is not None:
        lo, hi = env.find("gml:lowerCorner", NS), env.find("gml:upperCorner", NS)
        zlo, zhi = lo.text.split()[2], hi.text.split()[2]
        lo.text, hi.text = f"{xmin} {ymin} {zlo}", f"{xmax} {ymax} {zhi}"

    if a.epsg:
        for el in root.iter():
            if "srsName" in el.attrib:
                el.attrib["srsName"] = EPSG_SRS

    tree.write(a.dst, xml_declaration=True, encoding="UTF-8", pretty_print=True)
    print(f"{kept} Gebäude behalten, {removed} entfernt -> {a.dst}")


if __name__ == "__main__":
    main()
