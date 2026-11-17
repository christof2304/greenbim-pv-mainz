// =====================================================================
//  Green BIM – HS Mainz | Schritt 4 · Stufe 4: Vom Stadtmodell zum Gebäude
//  Lösung + Dach anklicken → Module legen, Python-Befehl für Schritt 5+6
//  Komplett in https://sandcastle.cesium.com einfügen und "Run" klicken.
//  Alle Stufen: github.com/christof2304/greenbim-pv-mainz/tree/main/sandcastle/schritt4
// =====================================================================

import * as Cesium from "cesium";
import Sandcastle from "Sandcastle";

// ---- 1) Eigene Daten ------------------------------------------------
// Euer Token: https://ion.cesium.com/tokens  (Sandcastle hat auch einen Default-Token)
// Cesium.Ion.defaultAccessToken = "HIER_EUREN_TOKEN_EINFÜGEN";
const ION_ASSET_ID = 6169981; // <- eure Asset-ID aus Cesium ion (CityGML-Upload)
const ROOFS_URL =
  "https://raw.githubusercontent.com/christof2304/greenbim-pv-mainz/main/data/campus_roofs_pv.geojson";
const CAMPUS = Cesium.Cartesian3.fromDegrees(8.2274, 49.9884, 150);

// ---- 2) Viewer mit Gelände, Schatten und Zeitleiste ---------------------
const viewer = new Cesium.Viewer("cesiumContainer", {
  terrain: Cesium.Terrain.fromWorldTerrain(),
  shadows: true,
  infoBox: true,
});
viewer.scene.globe.enableLighting = true;
viewer.shadowMap.softShadows = true;
viewer.shadowMap.maximumDistance = 3000;

// Sommersonnenwende, Zeitraffer 1 h pro Sekunde
const start = Cesium.JulianDate.fromIso8601("2026-06-21T03:00:00Z");
const stop = Cesium.JulianDate.fromIso8601("2026-06-21T20:00:00Z");
viewer.clock.startTime = start.clone();
viewer.clock.stopTime = stop.clone();
viewer.clock.currentTime = Cesium.JulianDate.fromIso8601("2026-06-21T10:00:00Z");
viewer.clock.clockRange = Cesium.ClockRange.UNBOUNDED; // Datumssprünge per Button erlauben
viewer.clock.multiplier = 3600;
viewer.clock.shouldAnimate = false;
viewer.timeline.zoomTo(start, stop);

// ---- 3) LoD2-Gebäude aus Cesium ion ----------------------------------
let tileset;
try {
  tileset = await Cesium.Cesium3DTileset.fromIonAssetId(ION_ASSET_ID);
  tileset.style = new Cesium.Cesium3DTileStyle({ color: "color('#d9d9d9')" });
  viewer.scene.primitives.add(tileset);
} catch (e) {
  console.log("Tileset konnte nicht geladen werden (Asset-ID/Token prüfen):", e);
}

// ---- 4) Dachflächen (GeoJSON mit tilt/azimuth/area aus Python) ---------
const roofs = await Cesium.GeoJsonDataSource.load(ROOFS_URL);
viewer.dataSources.add(roofs);
const roofEntities = roofs.entities.values;
for (const e of roofEntities) {
  e.polygon.perPositionHeight = true; // echte 3D-Dachneigung statt auf Boden geklemmt
  e.polygon.outline = false;
  e.polygon.shadows = Cesium.ShadowMode.RECEIVE_ONLY;
}

viewer.camera.flyTo({
  destination: Cesium.Cartesian3.fromDegrees(8.2335, 49.9775, 900),
  orientation: { heading: Cesium.Math.toRadians(-20), pitch: Cesium.Math.toRadians(-35) },
  duration: 0,
});

// ---- 5) Sonnenstand: Richtungsvektor im lokalen Ost-Nord-Oben-System ---
const enuToFixed = Cesium.Transforms.eastNorthUpToFixedFrame(CAMPUS);
const fixedToEnu = Cesium.Matrix4.inverse(enuToFixed, new Cesium.Matrix4());

function sunDirectionENU(time) {
  // Sonnenposition im Inertialsystem -> erdfestes System (ECEF)
  const sunInertial = Cesium.Simon1994PlanetaryPositions.computeSunPositionInEarthInertialFrame(time);
  const icrfToFixed =
    Cesium.Transforms.computeIcrfToFixedMatrix(time) ??
    Cesium.Transforms.computeTemeToPseudoFixedMatrix(time);
  const sunFixed = Cesium.Matrix3.multiplyByVector(icrfToFixed, sunInertial, new Cesium.Cartesian3());
  // Richtung vom Campus zur Sonne, in ENU (x=Ost, y=Nord, z=Oben)
  const dirFixed = Cesium.Cartesian3.normalize(
    Cesium.Cartesian3.subtract(sunFixed, CAMPUS, new Cesium.Cartesian3()),
    new Cesium.Cartesian3()
  );
  return Cesium.Matrix4.multiplyByPointAsVector(fixedToEnu, dirFixed, new Cesium.Cartesian3());
}

// ---- 6) Einstrahlung auf eine geneigte Fläche (Clear-Sky-Modell) -------
function surfaceNormalENU(tiltDeg, azimuthDeg) {
  const t = Cesium.Math.toRadians(tiltDeg);
  const a = Cesium.Math.toRadians(azimuthDeg); // 0° = Nord, 90° = Ost, 180° = Süd
  // ✔ TODO 2 gelöst: Neigung t kippt den Pfeil, Azimut a dreht ihn in die Himmelsrichtung
  return new Cesium.Cartesian3(Math.sin(t) * Math.sin(a), Math.sin(t) * Math.cos(a), Math.cos(t));
}

function irradiance(sun, tiltDeg, azimuthDeg) {
  const cosZenith = sun.z; // Sonnenhöhe: sin(h) = cos(Zenitwinkel)
  if (cosZenith <= 0.01) return 0; // Nacht
  const airMass = 1 / cosZenith;
  const DNI = 1361 * Math.pow(0.7, Math.pow(airMass, 0.678)); // Meinel & Meinel 1976
  const DHI = 0.1 * DNI; // grobe Annahme für klaren Himmel
  const n = surfaceNormalENU(tiltDeg, azimuthDeg);
  // ✔ TODO 3 gelöst: Skalarprodukt zweier Einheitsvektoren = Kosinus des Winkels
  const cosTheta = Cesium.Cartesian3.dot(n, sun);
  const tilt = Cesium.Math.toRadians(tiltDeg);
  return DNI * Math.max(0, cosTheta) + DHI * (1 + Math.cos(tilt)) / 2; // W/m²
}

// Prüft, ob TODO 2 und 3 gelöst sind. Vorher wäre die Leistungssumme Unsinn.
function todosSolved() {
  const n = surfaceNormalENU(90, 180); // Südfassade, richtig wäre (0, -1, 0)
  if (n.y > -0.99) return false;
  const sunFromNorth = Cesium.Cartesian3.normalize(new Cesium.Cartesian3(0, 1, 0.5), new Cesium.Cartesian3());
  // Sonne im Norden: Die Südfassade bekommt dann keine Direktstrahlung, ein Flachdach schon
  return irradiance(sunFromNorth, 90, 180) < 0.5 * irradiance(sunFromNorth, 0, 0);
}

// ---- 7) Einfärben --------------------------------------------------------
const ramp = (v, min, max) =>
  Cesium.Color.fromHsl(0.66 * (1 - Cesium.Math.clamp((v - min) / (max - min), 0, 1)), 1.0, 0.5, 0.9);

let mode = "Momentan (W/m²)";
const legend = document.createElement("div");
legend.style.cssText =
  "position:absolute;bottom:40px;right:10px;background:rgba(40,40,40,.85);color:#fff;" +
  "padding:8px 12px;font:13px sans-serif;border-radius:6px;min-width:220px";
document.getElementById("cesiumContainer").appendChild(legend);

function updateColors() {
  const time = viewer.clock.currentTime;
  const sun = sunDirectionENU(time);
  const elev = Cesium.Math.toDegrees(Math.asin(sun.z));
  const azim = (Cesium.Math.toDegrees(Math.atan2(sun.x, sun.y)) + 360) % 360;
  let sum = 0;
  for (const e of roofEntities) {
    const p = e.properties;
    const tilt = p.tilt.getValue(), az = p.azimuth.getValue(), area = p.area.getValue();
    let color;
    if (mode.startsWith("Momentan")) {
      const E = irradiance(sun, tilt, az);
      sum += (E * area) / 1000;
      // ✔ TODO 1 gelöst: Farbe aus der Einstrahlung (0 W/m² = blau, 1000 W/m² = rot)
      color = ramp(E, 0, 1000);
    } else {
      color = ramp(p.irr_kwh_m2.getValue(), 700, 1300);
    }
    e.polygon.material = color;
  }
  const local = Cesium.JulianDate.toDate(time).toLocaleString("de-DE", { timeZone: "Europe/Berlin" });
  legend.innerHTML = mode.startsWith("Momentan")
    ? `<b>${local}</b><br>Sonnenhöhe ${elev.toFixed(1)}°, Azimut ${azim.toFixed(0)}°<br>` +
      (todosSolved()
        ? `Leistung auf allen Dächern: <b>${(sum / 1000).toFixed(1)} MW</b> (Strahlung, ohne Wirkungsgrad)<br>`
        : `Leistung auf allen Dächern: <b>—</b> (erst nach TODO 2 + 3)<br>`) +
      `<span style="color:#66f">■</span> 0 &nbsp;→&nbsp; <span style="color:#f44">■</span> 1000 W/m²`
    : `<b>Jahressumme (PVGIS-TMY, pvlib)</b><br>` +
      `<span style="color:#66f">■</span> 700 &nbsp;→&nbsp; <span style="color:#f44">■</span> 1300 kWh/m²a`;
}

// Nur neu einfärben, wenn sich die Zeit um > 5 min geändert hat
let last;
viewer.clock.onTick.addEventListener((clock) => {
  if (!last || Math.abs(Cesium.JulianDate.secondsDifference(clock.currentTime, last)) > 300) {
    last = clock.currentTime.clone();
    updateColors();
  }
});

Sandcastle.addToolbarMenu(
  ["Momentan (W/m²)", "Jahressumme (kWh/m²a)"].map((text) => ({
    text,
    onselect: () => { mode = text; updateColors(); },
  }))
);
// Springt zu einem Tag und stellt die Zeitleiste auf diesen Tag (04:00–22:00 Ortszeit)
function gotoDay(date, hourUTC) {
  const d = date.toISOString().slice(0, 10);
  const t0 = Cesium.JulianDate.fromIso8601(`${d}T03:00:00Z`);
  const t1 = Cesium.JulianDate.fromIso8601(`${d}T21:00:00Z`);
  viewer.clock.startTime = t0;
  viewer.clock.stopTime = t1;
  viewer.clock.currentTime = hourUTC === undefined
    ? Cesium.JulianDate.fromDate(date)
    : Cesium.JulianDate.fromIso8601(`${d}T${String(hourUTC).padStart(2, "0")}:00:00Z`);
  viewer.timeline.zoomTo(t0, t1);
}
Sandcastle.addToolbarButton("21. Juni", () => gotoDay(new Date("2026-06-21T12:00:00Z"), 10));
Sandcastle.addToolbarButton("21. Dezember", () => gotoDay(new Date("2026-12-21T12:00:00Z"), 11));
Sandcastle.addToolbarButton("Jetzt", () => gotoDay(new Date()));
updateColors();

// =====================================================================
//  STUFE 4: Vom Stadtmodell zum Gebäude (Brücke zu Schritt 5 und 6)
//  1. Auf ein Dach klicken → das Gebäude ist ausgewählt
//  2. „Module legen“      → PV-Module wie in module_layout.py, direkt im 3D-Modell
//  3. „Befehl Schritt 5+6“ → fertiger Python-Befehl mit der Gebäude-ID
// =====================================================================

const LOOKUP_URL =
  "https://raw.githubusercontent.com/christof2304/greenbim-pv-mainz/main/data/poa_lookup.json";
const lookup = await (await fetch(LOOKUP_URL)).json(); // Ertragstabelle aus pvlib (Neigung × Azimut)

// Dieselben Annahmen wie in python/module_layout.py
const MOD_L = 1.722, MOD_W = 1.134, MOD_WP = 430, GAP = 0.02;
const SETBACK_PITCHED = 0.4, SETBACK_FLAT = 1.0, RACK_TILT = 15, WINTER_SUN = 16.6;
const MIN_YIELD = 800, CO2_G_PER_KWH = 380, FLAT_LIMIT = 10;

// Spezifischer Ertrag [kWh/kWp] per bilinearer Interpolation (wie interp() in pv_yield.py)
function specYield(tilt, az) {
  const v = lookup.yield_kwh_kwp, nT = lookup.tilts.length, nA = lookup.azimuths.length;
  const ti = Math.min(Math.max(tilt / 5, 0), nT - 1.0001), i0 = Math.floor(ti), ft = ti - i0;
  const aj = (((az % 360) + 360) % 360) / 10, j0 = Math.floor(aj) % nA, fa = aj - Math.floor(aj), j1 = (j0 + 1) % nA;
  return (1 - ft) * ((1 - fa) * v[i0][j0] + fa * v[i0][j1]) + ft * ((1 - fa) * v[i0 + 1][j0] + fa * v[i0 + 1][j1]);
}

// ---- Kleine 2D-Geometrie: Punkt im Polygon, Strecken-Schnitt -------------
function inside(pt, poly) {
  let c = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if ((yi > pt[1]) !== (yj > pt[1]) && pt[0] < ((xj - xi) * (pt[1] - yi)) / (yj - yi) + xi) c = !c;
  }
  return c;
}
function segX(a, b, c, d) {
  const cr = (p, q, r) => (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]);
  return cr(a, b, c) * cr(a, b, d) < 0 && cr(c, d, a) * cr(c, d, b) < 0;
}
// Abstand Punkt–Strecke
function distPtSeg(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy;
  const t = l2 ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2)) : 0;
  return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy);
}
// Liegt ein Rechteck vollständig im Dachpolygon, mit mindestens s Abstand zu jeder Dachkante?
// (entspricht poly.buffer(-s).contains(box) in Python, auch bei schräg liegenden Kanten)
function fits(x, y, w, h, s, poly) {
  const r = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];
  if (!r.every((p) => inside(p, poly))) return false;
  if (poly.some((p) => p[0] > x && p[0] < x + w && p[1] > y && p[1] < y + h)) return false;
  const nP = poly.length;
  for (let k = 0; k < nP; k++) {
    const a = poly[k], b = poly[(k + 1) % nP];
    for (let i = 0; i < 4; i++) {
      if (segX(r[i], r[(i + 1) % 4], a, b)) return false;
      if (distPtSeg(r[i], a, b) < s) return false;            // Rechteckecke zu nah an der Dachkante
      if (distPtSeg(a, r[i], r[(i + 1) % 4]) < s) return false; // Dachecke zu nah an der Modulkante
    }
  }
  return true;
}
// Raster in mehreren Lagen probieren, die Lage mit den meisten Modulen gewinnt (wie pack() in Python)
function pack(poly, cu, cv, pitchV, s) {
  const xs = poly.map((p) => p[0]), ys = poly.map((p) => p[1]);
  const minx = Math.min(...xs) + s, maxx = Math.max(...xs) - s, miny = Math.min(...ys) + s, maxy = Math.max(...ys) - s;
  let best = [];
  for (let pu = 0; pu < 4; pu++)
    for (let pv = 0; pv < 4; pv++) {
      const cells = [];
      for (let y = miny + (pv * pitchV) / 4; y + cv <= maxy + 1e-9; y += pitchV)
        for (let x = minx + (pu * cu) / 4; x + cu <= maxx + 1e-9; x += cu + GAP)
          if (fits(x, y, cu, cv, s, poly)) cells.push([x, y]);
      if (cells.length > best.length) best = cells;
    }
  return best;
}

// ---- Module für eine Dachfläche berechnen ------------------------------------
const C3 = Cesium.Cartesian3;
function layoutRoof(entity, time) {
  const P = entity.properties;
  const tilt = P.tilt.getValue(), az = P.azimuth.getValue();
  let pts = entity.polygon.hierarchy.getValue(time).positions;
  if (pts.length > 3 && C3.equalsEpsilon(pts[0], pts[pts.length - 1], 0, 1e-3)) pts = pts.slice(0, -1); // Schlusspunkt nur einmal
  const enu = Cesium.Transforms.eastNorthUpToFixedFrame(pts[0]);
  const inv = Cesium.Matrix4.inverse(enu, new Cesium.Matrix4());
  const L = pts.map((p) => Cesium.Matrix4.multiplyByPoint(inv, p, new C3())); // lokal: x=Ost, y=Nord, z=Oben
  // Dachnormale (Newell), nach oben gerichtet
  const n = new C3();
  for (let i = 0; i < L.length; i++) {
    const a = L[i], b = L[(i + 1) % L.length];
    n.x += (a.y - b.y) * (a.z + b.z); n.y += (a.z - b.z) * (a.x + b.x); n.z += (a.x - b.x) * (a.y + b.y);
  }
  C3.normalize(n, n); if (n.z < 0) C3.negate(n, n);
  const toWorld = (x, y, z) => Cesium.Matrix4.multiplyByPoint(enu, new C3(x, y, z), new C3());
  const quads = [];
  let mTilt, mAz;

  if (tilt >= FLAT_LIMIT) {
    // Geneigtes Dach: dachparallel. u = waagerecht entlang der Traufe, v = hangaufwärts
    const u = C3.normalize(C3.cross(new C3(0, 0, 1), n, new C3()), new C3());
    const v = C3.cross(n, u, new C3());
    const poly = L.map((p) => [C3.dot(p, u), C3.dot(p, v)]);
    const variants = [[MOD_L, MOD_W], [MOD_W, MOD_L]].map(([cu, cv]) => [cu, cv, pack(poly, cu, cv, cv + GAP, SETBACK_PITCHED)]);
    const [cu, cv, cells] = variants[0][2].length >= variants[1][2].length ? variants[0] : variants[1];
    const pt = (x, y) => { const q = C3.add(C3.multiplyByScalar(u, x, new C3()), C3.multiplyByScalar(v, y, new C3()), new C3());
      C3.add(q, C3.multiplyByScalar(n, 0.12, new C3()), q); return toWorld(q.x, q.y, q.z); };
    for (const [x, y] of cells) quads.push([pt(x, y), pt(x + cu, y), pt(x + cu, y + cv), pt(x, y + cv)]);
    mTilt = tilt; mAz = az;
  } else {
    // Flachdach: 15° nach Süden aufgeständert, Reihenabstand für 16,6° Wintersonne
    const t = Cesium.Math.toRadians(RACK_TILT);
    const depth = MOD_W * Math.cos(t);
    const pitch = depth + (MOD_W * Math.sin(t)) / Math.tan(Cesium.Math.toRadians(WINTER_SUN));
    const poly = L.map((p) => [p.x, p.y]);
    const cells = pack(poly, MOD_L, depth, pitch, SETBACK_FLAT);
    const zRoof = (x, y) => -(n.x * x + n.y * y) / n.z; // Höhe der Dachebene an (x, y)
    for (const [x, y] of cells) {
      const z0 = zRoof(x, y) + 0.3, rise = MOD_W * Math.sin(t);
      quads.push([toWorld(x, y, z0), toWorld(x + MOD_L, y, z0), toWorld(x + MOD_L, y + depth, z0 + rise), toWorld(x, y + depth, z0 + rise)]);
    }
    mTilt = RACK_TILT; mAz = 180;
  }
  const spec = specYield(mTilt, mAz);
  return { quads: spec >= MIN_YIELD ? quads : [], possible: quads.length, spec, mTilt, mAz, flat: tilt < FLAT_LIMIT };
}

// ---- Auswahl, Anzeige, Buttons --------------------------------------------------
const modules = new Cesium.CustomDataSource("PV-Module");
viewer.dataSources.add(modules);
let selectedId = null;

const panel = document.createElement("div");
panel.style.cssText =
  "position:absolute;top:50px;left:10px;width:340px;background:rgba(40,40,40,.9);color:#fff;" +
  "padding:10px 12px;font:13px sans-serif;border-radius:6px;user-select:text";
document.getElementById("cesiumContainer").appendChild(panel);
const showPanel = (html) => { panel.innerHTML = html; };
showPanel("<b>Stufe 4</b><br>Auf ein <b>Dach</b> klicken, um ein Gebäude auszuwählen.");

viewer.selectedEntityChanged.addEventListener((e) => {
  const id = e?.properties?.building_id?.getValue();
  if (!id) return;
  selectedId = id;
  const n = roofEntities.filter((r) => r.properties.building_id.getValue() === id).length;
  showPanel(`<b>Ausgewählt:</b> ${id}<br>${n} Dachfläche(n)<br><br>→ <b>Module legen</b> oder <b>Befehl Schritt 5+6</b>`);
});

Sandcastle.addToolbarButton("Module legen", () => {
  if (!selectedId) return showPanel("Bitte zuerst auf ein <b>Dach</b> klicken.");
  modules.entities.removeAll();
  const time = viewer.clock.currentTime;
  let rows = "", nSum = 0, kwhSum = 0;
  roofEntities.filter((r) => r.properties.building_id.getValue() === selectedId).forEach((r, i) => {
    const res = layoutRoof(r, time);
    for (const q of res.quads)
      modules.entities.add({ polygon: { hierarchy: q, perPositionHeight: true, material: Cesium.Color.fromCssColorString("#13235a"),
        outline: true, outlineColor: Cesium.Color.fromCssColorString("#9db3ff") } });
    const kwp = (res.quads.length * MOD_WP) / 1000, kwh = kwp * res.spec;
    nSum += res.quads.length; kwhSum += kwh;
    rows += `Dach ${i + 1}: ` + (res.quads.length
      ? `<b>${res.quads.length}</b> Module, ${kwp.toFixed(1)} kWp, ${Math.round(res.spec)} kWh/kWp${res.flat ? " (aufgeständert)" : ""}<br>`
      : `nicht belegt (${Math.round(res.spec)} kWh/kWp${res.possible ? "" : ", zu klein"})<br>`);
  });
  const kwpSum = (nSum * MOD_WP) / 1000;
  showPanel(`<b>${selectedId}</b><br>${rows}<hr style="border-color:#666">` +
    `<b>${nSum} Module · ${kwpSum.toFixed(1)} kWp · ${Math.round(kwhSum).toLocaleString("de-DE")} kWh/a</b><br>` +
    `≈ ${((kwhSum * CO2_G_PER_KWH) / 1e6).toFixed(1)} t CO₂/a (${CO2_G_PER_KWH} g/kWh)<br>` +
    `<span style="color:#aaa">Ohne Verschattung. Das IFC dazu erzeugt Schritt 5+6 in Python.</span>`);
});

Sandcastle.addToolbarButton("Module entfernen", () => modules.entities.removeAll());

Sandcastle.addToolbarButton("Befehl Schritt 5+6", async () => {
  if (!selectedId) return showPanel("Bitte zuerst auf ein <b>Dach</b> klicken.");
  const cmd =
    `cd PFAD\\ZUM\\REPO\\greenbim-pv-mainz\\python\n` +
    `python citygml_to_ifc.py ../data/campus_lod2.gml ${selectedId} ../data/${selectedId}.ifc\n` +
    `python module_layout.py ../data/${selectedId}.ifc ../data/${selectedId}_pv.ifc`;
  let copied = false;
  try { await navigator.clipboard.writeText(cmd); copied = true; } catch (e) { /* Sandcastle erlaubt die Zwischenablage evtl. nicht */ }
  showPanel(`<b>Schritt 5+6 für ${selectedId}</b><br>Im Terminal ausführen. <b>Erste Zeile anpassen:</b> ` +
    `Pfad zu eurem Repo-Ordner <code>python</code> (sonst „No such file“):` +
    `<pre style="white-space:pre-wrap;background:#111;padding:6px;border-radius:4px;font-size:12px">${cmd}</pre>` +
    (copied ? "✔ In die Zwischenablage kopiert." : "Text markieren und mit Strg+C kopieren."));
});
