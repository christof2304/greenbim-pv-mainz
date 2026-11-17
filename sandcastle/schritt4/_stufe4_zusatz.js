
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
