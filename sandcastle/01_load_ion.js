// =====================================================================
//  Green BIM – HS Mainz | Schritt 2: Eigenes CityGML-Asset aus Cesium ion laden
//  In https://sandcastle.cesium.com einfügen und "Run" klicken.
// =====================================================================

import * as Cesium from "cesium";

// Euer Token: https://ion.cesium.com/tokens
// Cesium.Ion.defaultAccessToken = "HIER_EUREN_TOKEN_EINFÜGEN";
const ION_ASSET_ID = 6169981; // <- eure Asset-ID (ion -> My Assets -> CityGML-Upload)

const viewer = new Cesium.Viewer("cesiumContainer", {
  terrain: Cesium.Terrain.fromWorldTerrain(),
});

const tileset = await Cesium.Cesium3DTileset.fromIonAssetId(ION_ASSET_ID);
viewer.scene.primitives.add(tileset);
await viewer.zoomTo(tileset);

// Klick auf ein Gebäude -> alle CityGML-Attribute in der Konsole
const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
handler.setInputAction((click) => {
  const feature = viewer.scene.pick(click.position);
  if (!(feature instanceof Cesium.Cesium3DTileFeature)) return;
  const props = {};
  for (const name of feature.getPropertyIds()) props[name] = feature.getProperty(name);
  console.log(props);
}, Cesium.ScreenSpaceEventType.LEFT_CLICK);

// Aufgabe: Färbt die Gebäude nach Höhe ein, z. B. mit
// tileset.style = new Cesium.Cesium3DTileStyle({
//   color: { conditions: [["${Height} > 15", "color('red')"], ["true", "color('white')"]] },
// });
// (Welche Attribute es gibt, seht ihr in der Konsole nach einem Klick.)
