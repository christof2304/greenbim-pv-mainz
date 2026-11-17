# Schritt 6: PV-Module aufs Dach legen und Ertrag berechnen

Das IFC aus [Schritt 5](SCHRITT5.md) oder euer eigenes Revit-Modell bekommt eine konkrete **PV-Belegung**.
Jedes Modul wird ein echtes BIM-Bauteil (`IfcSolarDevice`) mit Leistung und Jahresertrag.

---

## 1. Aufruf

Im Ordner `python/`:

```bash
python module_layout.py ../data/mein_gebaeude.ifc ../data/mein_gebaeude_pv.ifc
```

| Teil | Bedeutung |
|---|---|
| `../data/mein_gebaeude.ifc` | Eingabe: das IFC aus Schritt 5 (oder euer eigenes Modell) |
| `../data/mein_gebaeude_pv.ifc` | Ausgabe: dasselbe Modell **mit Modulen** |

Beispielausgabe für das Gewerbegebäude `DERPLP200003IGOM`:

```
Dachfläche 1: 96 Module, 41.3 kWp, 977 kWh/kWp -> 40,349 kWh/a
Dachfläche 2: 624 Module, 268.3 kWp, 910 kWh/kWp -> 244,119 kWh/a
Summe: 720 Module, 309.6 kWp, 284,468 kWh/a, ≈ 108.1 t CO2/a (Validierung: 0 Meldungen)
```

Erst nur bewerten, ohne Module zu legen:

```bash
python ifc_roofs.py ../data/mein_gebaeude.ifc
```

## 2. Was das Skript macht

### a) Dachflächen finden

Dafür wird `ifc_roofs.py` verwendet. Das funktioniert mit jedem IFC, auch aus Revit oder Archicad.

- Es sammelt alle Dachbauteile: `IfcRoof` mit seinen Teilen, `IfcSlab` (ROOF) und `IfcCovering` (ROOFING).
- Es trianguliert die Geometrie mit dem IfcOpenShell-Geometriekern.
- Es fasst die Dreiecke zu **Ebenen** zusammen. Behalten werden nur Ebenen, die nach oben zeigen und mindestens 60 cm breit sind.
- Es dreht die Ausrichtung auf **geografisch Nord**, über `IfcMapConversion` oder `TrueNorth`. Das ist wichtig bei Revit-Modellen mit gedrehtem Projektnord.

### b) Belegung je Dachfläche

| | Geneigtes Dach (≥ 10°) | Flachdach (< 10°) |
|---|---|---|
| Verlegung | dachparallel | aufgeständert, 15° nach Süden |
| Randabstand | 40 cm | 1 m |
| Raster | Hoch- und Querformat in 16 Rasterlagen, das Beste gewinnt | Reihen von Ost nach West |
| Reihenabstand | 2 cm Fuge | keine Verschattung am 21.12. mittags (Sonnenhöhe 16,6°) |
| Abstand zur Dachhaut | 12 cm | 30 cm |

### c) Ertrag

- Der spezifische Ertrag (kWh/kWp) hängt von **Modulneigung und Modulausrichtung** ab. Er stammt aus `data/poa_lookup.json`, berechnet mit pvlib: PVGIS-Referenzjahr Mainz, Perez-Modell, Modultemperatur, 14 % Systemverluste.
- Dachflächen unter **800 kWh/kWp** werden nicht belegt.

### d) Ins IFC schreiben

- **Ein Modultyp** `IfcSolarDeviceType` (SOLARPANEL, 430 Wp, 1,722 × 1,134 m) mit einer Geometrie.
- **Jedes Modul** ist ein `IfcSolarDevice`, das auf diese Geometrie verweist. Die Datei bleibt dadurch klein.
- **Eigenschaften:**

| Pset | an | Inhalt |
|---|---|---|
| `PV_Modul` | Modultyp | Nennleistung, Maße, Technologie |
| `PV_Belegung` | jeder belegten Dachfläche | Anzahl Module, kWp, kWh/kWp, kWh/a, Modulneigung, Modulazimut, Art der Belegung |
| `PV_Anlage` | Gebäude | Summe Module, kWp, kWh/a, CO₂-Einsparung in t/a |

- Zum Schluss prüft `ifcopenshell.validate` das Modell, Ziel ist **0 Meldungen**.

## 3. In Bonsai ansehen

1. Blender starten → **File → Open IFC Project** → die `…_pv.ifc`-Datei.
2. Ein **Modul** anklicken: Klasse `IfcSolarDevice`, Typ „PV-Modul 430 Wp“, Pset `PV_Modul`.
3. Eine **Dachfläche** anklicken: Pset `PV_Belegung`.
4. Das **Gebäude** im Outliner anklicken: Pset `PV_Anlage` mit der Gesamtbilanz.

## 4. Annahmen anpassen

Die Annahmen stehen als Konstanten oben in `module_layout.py`:

| Konstante | Wert | Bedeutung |
|---|---|---|
| `MOD_L`, `MOD_W`, `MOD_WP` | 1,722 m, 1,134 m, 430 Wp | Modulmaße und -leistung |
| `SETBACK_PITCHED` | 0,40 m | Randabstand geneigtes Dach |
| `SETBACK_FLAT` | 1,00 m | Randabstand Flachdach |
| `RACK_TILT` | 15° | Aufständerung Flachdach |
| `WINTER_SUN` | 16,6° | Sonnenhöhe für den Reihenabstand |
| `MIN_YIELD` | 800 kWh/kWp | Mindestertrag für eine Belegung |
| `CO2_G_PER_KWH` | 380 g/kWh | Strommix-Annahme für die CO₂-Einsparung |

Diese Werte sind Annahmen. In der Hausarbeit solltet ihr sie begründen oder durch eigene Quellen ersetzen.

**Warum ist die kWp-Zahl hier anders als im Pset `PV_Potenzial` aus Schritt 5?**
Schritt 5 schätzt mit pauschal 70 % Belegung. Schritt 6 legt die Module tatsächlich aus.
Auf großen, einfach geschnittenen Dächern passen mehr Module als geschätzt, auf verwinkelten Dächern weniger.

## 5. Für die Hausarbeit: Ökobilanz

1. Euer Revit-Modell als **IFC 4** exportieren. Dabei müssen die Dächer als `IfcRoof` oder `IfcSlab` (ROOF) herauskommen und Projektnord bzw. Vermessungspunkt gesetzt sein.
2. Module legen:
   ```bash
   python module_layout.py mein_modell.ifc mein_modell_pv.ifc
   ```
3. Aus dem Pset `PV_Anlage` die **kWp** und die **CO₂-Einsparung pro Jahr** übernehmen.
4. In der **ÖKOBAUDAT** den Kennwert für die grauen Emissionen von PV-Modulen (kg CO₂e pro kWp) heraussuchen.
5. CO₂-Amortisationszeit berechnen:

   ```
   Amortisation [Jahre] = kWp × Kennwert [kg CO₂e/kWp] ÷ Einsparung [kg CO₂/a]
   ```

## Wenn etwas nicht klappt

| Meldung | Lösung |
|---|---|
| `Keine Dachflächen gefunden` (bei `ifc_roofs.py`) | Im Modell gibt es keine Dachbauteile mit Geometrie. Revit-Export prüfen: Dächer als `IfcRoof` bzw. `IfcSlab` (ROOF) exportieren. |
| `nicht belegt (spez. Ertrag … kWh/kWp)` | Die Dachfläche liegt unter 800 kWh/kWp, meist eine Nordseite. Das ist gewollt. |
| `nicht belegt (… 0 Module möglich)` | Die Fläche ist nach Abzug des Randabstands zu klein für ein Modul. |
| Azimute wirken um einen festen Winkel verdreht | Im Revit-Export fehlt die Georeferenz oder TrueNorth, die Richtung bezieht sich dann auf Projektnord. |

## Grenzen

- **Keine Verschattung** durch Nachbargebäude, Bäume, Gauben oder Haustechnik
- **Keine Elektroplanung:** Wechselrichter, Strings und Netzanschluss fehlen
- **Statik, Brandschutzabstände und Denkmalschutz** werden nicht geprüft
- Flachdächer werden immer nach Süden aufgeständert. Eine Ost-West-Variante wäre eine gute Erweiterung als Übung.
