// =====================================================================
//  Green BIM – HS Mainz | Schritt 4 · Stufe 2 von 3: Dachnormale
//  Gelöst bis TODO 2. Weiter mit stufe3_einfallswinkel.js
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
  // TODO 3: Kosinus des Einfallswinkels zwischen Dachnormale n und Sonnenrichtung sun
  //   Tipp: Beide sind Einheitsvektoren → Skalarprodukt (Cesium.Cartesian3.dot)
  const cosTheta = 1;
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
