// =====================================================================
//  Green BIM – HS Mainz | Schritt 3: Wo steht die Sonne?
//  Sonnenhöhe und -azimut über dem Campus für die aktuelle Zeit der Zeitleiste.
// =====================================================================

import * as Cesium from "cesium";

const CAMPUS = Cesium.Cartesian3.fromDegrees(8.2274, 49.9884, 150);

const viewer = new Cesium.Viewer("cesiumContainer", {
  terrain: Cesium.Terrain.fromWorldTerrain(),
  shadows: true,
});
viewer.scene.globe.enableLighting = true;
viewer.scene.primitives.add(await Cesium.createOsmBuildingsAsync());
viewer.camera.flyTo({ destination: Cesium.Cartesian3.fromDegrees(8.2274, 49.982, 700),
  orientation: { pitch: Cesium.Math.toRadians(-35) }, duration: 0 });

// Lokales Koordinatensystem am Campus: x = Ost, y = Nord, z = Oben (ENU)
const fixedToEnu = Cesium.Matrix4.inverse(
  Cesium.Transforms.eastNorthUpToFixedFrame(CAMPUS), new Cesium.Matrix4());

function sunDirectionENU(time) {
  const sunInertial = Cesium.Simon1994PlanetaryPositions.computeSunPositionInEarthInertialFrame(time);
  const icrfToFixed = Cesium.Transforms.computeIcrfToFixedMatrix(time) ??
    Cesium.Transforms.computeTemeToPseudoFixedMatrix(time);
  const sunFixed = Cesium.Matrix3.multiplyByVector(icrfToFixed, sunInertial, new Cesium.Cartesian3());
  const dir = Cesium.Cartesian3.normalize(
    Cesium.Cartesian3.subtract(sunFixed, CAMPUS, new Cesium.Cartesian3()), new Cesium.Cartesian3());
  return Cesium.Matrix4.multiplyByPointAsVector(fixedToEnu, dir, new Cesium.Cartesian3());
}

// Anzeige oben links
const box = document.createElement("div");
box.style.cssText = "position:absolute;top:10px;left:10px;background:rgba(40,40,40,.85);" +
  "color:#fff;padding:8px 12px;font:14px sans-serif;border-radius:6px";
document.getElementById("cesiumContainer").appendChild(box);

viewer.clock.onTick.addEventListener((clock) => {
  const s = sunDirectionENU(clock.currentTime);
  const hoehe = Cesium.Math.toDegrees(Math.asin(s.z));
  const azimut = (Cesium.Math.toDegrees(Math.atan2(s.x, s.y)) + 360) % 360; // 0° = Nord
  const t = Cesium.JulianDate.toDate(clock.currentTime)
    .toLocaleString("de-DE", { timeZone: "Europe/Berlin" });
  box.innerHTML = `${t}<br>Sonnenhöhe: <b>${hoehe.toFixed(1)}°</b><br>Azimut: <b>${azimut.toFixed(1)}°</b>`;
});

// Kontrollfrage: Mittags am 21. Juni sollte die Sonnenhöhe in Mainz ca. 90° − 50° + 23,4° ≈ 63,4° sein.
viewer.clock.currentTime = Cesium.JulianDate.fromIso8601("2026-06-21T11:20:00Z");
viewer.clock.multiplier = 1800;
