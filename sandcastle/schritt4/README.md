# Schritt 4: Einstrahlung auf jede Dachfläche

Zwei Wege, ihr könnt jederzeit wechseln:

- **Selbst tippen:** `stufe0_start.js` in Sandcastle einfügen, dann die drei Zeilen unten der Reihe nach ersetzen.
- **Aufholen:** Die Datei der nächsten Stufe komplett einfügen (Datei öffnen → Button *Copy raw file*) und **Run** klicken.

Token: In der Zeile `// Cesium.Ion.defaultAccessToken = "HIER_EUREN_TOKEN_EINFÜGEN";` (Abschnitt 1, ganz oben) die `//` entfernen und den Token aus dem Zoom-Chat einsetzen.

| Stufe | Datei | Was man sieht |
|---|---|---|
| 0 | [stufe0_start.js](stufe0_start.js) | Dächer weiß |
| 1 | [stufe1_farbe.js](stufe1_farbe.js) | Dächer farbig, aber alle gleich |
| 2 | [stufe2_normale.js](stufe2_normale.js) | fast unverändert, nur kleine Unterschiede nach Neigung |
| 3 | [stufe3_einfallswinkel.js](stufe3_einfallswinkel.js) | Sonnenseiten rot, Schattenseiten blau = Lösung |
| 4 | [stufe4_gebaeude.js](stufe4_gebaeude.js) | Lösung + Gebäude anklicken, Module legen, Python-Befehl |

## TODO 1: Farbe

Wo: in der Funktion updateColors(), Abschnitt 7. Diese Zeile suchen (Strg+F):

```js
color = Cesium.Color.WHITE;
```

ersetzen durch:

```js
color = ramp(E, 0, 1000);
```

Ergebnis: Die Dächer werden farbig, aber alle gleich: Noch gilt jedes Dach als flach und steht senkrecht zur Sonne.

Nicht geklappt? Ganze Datei nehmen: [stufe1_farbe.js](stufe1_farbe.js)

## TODO 2: Dachnormale

Wo: in der Funktion surfaceNormalENU(), Abschnitt 6. Diese Zeile suchen (Strg+F):

```js
return new Cesium.Cartesian3(0, 0, 1);
```

ersetzen durch:

```js
return new Cesium.Cartesian3(Math.sin(t) * Math.sin(a), Math.sin(t) * Math.cos(a), Math.cos(t));
```

Ergebnis: Jedes Dach kennt jetzt seine Neigung und Richtung. Sichtbar ist das erst nach TODO 3, denn bisher wird die Richtung noch nicht mit der Sonne verglichen.

Nicht geklappt? Ganze Datei nehmen: [stufe2_normale.js](stufe2_normale.js)

## TODO 3: Einfallswinkel

Wo: in der Funktion irradiance(), Abschnitt 6. Diese Zeile suchen (Strg+F):

```js
const cosTheta = 1;
```

ersetzen durch:

```js
const cosTheta = Cesium.Cartesian3.dot(n, sun);
```

Ergebnis: Fertig: Sonnenseiten werden rot, abgewandte Seiten blau, und alles wandert mit der Uhrzeit. Die Legende zeigt jetzt die Gesamtleistung.

Nicht geklappt? Ganze Datei nehmen: [stufe3_einfallswinkel.js](stufe3_einfallswinkel.js)

## Stufe 4: Vom Stadtmodell zum Gebäude

[stufe4_gebaeude.js](stufe4_gebaeude.js) ist die Lösung plus drei Buttons oben links:

1. Auf ein **Dach** klicken: Das Gebäude ist ausgewählt (Anzeige oben rechts).
2. **Module legen**: PV-Module wie in `python/module_layout.py` direkt im 3D-Modell, mit Anzahl, kWp, kWh/a und CO₂.
3. **Module entfernen**: räumt wieder auf.
4. **Befehl Schritt 5+6**: zeigt den fertigen Python-Befehl mit der Gebäude-ID und kopiert ihn, wenn der Browser es erlaubt.

Das IFC selbst entsteht weiterhin in Python, siehe [`python/SCHRITT5.md`](../../python/SCHRITT5.md) und [`python/SCHRITT6.md`](../../python/SCHRITT6.md).
Sandcastle zeigt die Belegung nur an. Für Planung und Ökobilanz braucht ihr die IFC-Datei.
