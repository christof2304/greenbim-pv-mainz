# Schritt 5: Ein Gebäude aus dem Stadtmodell als IFC

Aus einem LoD2-Gebäude (CityGML) entsteht ein georeferenziertes **IFC-4-Modell**.
Das könnt ihr in Bonsai, Revit oder jedem IFC-Viewer öffnen und in Schritt 6 mit PV-Modulen belegen.

Ihr braucht: Python ≥ 3.11 mit den Paketen aus `requirements.txt` und, zum Ansehen, Blender + Bonsai.

---

## 1. Gebäude in Sandcastle auswählen

1. In Sandcastle auf das **Dach** des gewünschten Gebäudes klicken.
2. In der Info-Box rechts die Zeile **`building_id`** suchen und den Wert kopieren, z. B. `DERPLP200003IGOM`.

Die ID ist die `gml:id` des Gebäudes im amtlichen Stadtmodell.

**Abkürzung:** In [`sandcastle/schritt4/stufe4_gebaeude.js`](../sandcastle/schritt4/stufe4_gebaeude.js) aufs Dach klicken und dann den Button **„Befehl Schritt 5+6“** drücken. Er zeigt beide Python-Befehle schon mit der richtigen ID. Mit **„Module legen“** seht ihr die Belegung vorab im 3D-Modell.

## 2. Einmalig: Python-Pakete installieren

Terminal öffnen (Windows: PowerShell, Mac/Linux: Terminal) und in den Ordner `python/` des Repos wechseln:

```bash
cd greenbim-pv-mainz/python
pip install -r requirements.txt
```

## 3. Konvertierung starten

Die ID wird **nicht in eine Datei geschrieben**, sondern beim Aufruf als zweites Argument übergeben:

```bash
python citygml_to_ifc.py ../data/campus_lod2.gml DERPLP200003IGOM ../data/mein_gebaeude.ifc
```

| Teil | Bedeutung |
|---|---|
| `../data/campus_lod2.gml` | das Stadtmodell (450 Gebäude rund um den Campus) |
| `DERPLP200003IGOM` | **eure** `building_id` aus Sandcastle |
| `../data/mein_gebaeude.ifc` | Name der neuen IFC-Datei (frei wählbar) |

Wenn alles klappt, erscheint eine Zeile wie diese:

```
../data/mein_gebaeude.ifc: 2 Dachflächen, 6 Wände, 1 Bodenplatten;
Ursprung E=444788 N=5537545 H=128.06; Validierung: 0 Meldungen
```

**„Validierung: 0 Meldungen“** heißt, das IFC ist formal korrekt.

## 4. Was das Skript macht

1. **Gebäude lesen:** Es sucht das Gebäude mit eurer ID und sammelt alle Dach-, Wand- und Bodenflächen. Virtuelle Abschlussflächen (`ClosureSurface`) werden ignoriert.
2. **Lokaler Ursprung:** Der Modellursprung liegt an der Südwest-Ecke des Gebäudes auf Geländehöhe. So bleiben die Koordinaten im IFC klein.
3. **Georeferenzierung:** `IfcMapConversion` auf **EPSG:25832** (ETRS89 / UTM 32N) mit Höhen in **DHHN2016**. Damit weiß das Modell, wo es auf der Erde liegt.
4. **Aus Flächen werden Bauteile:** LoD2-Flächen haben keine Dicke. Jede Fläche wird deshalb nach innen extrudiert:

   | CityGML | IFC | Dicke |
   |---|---|---|
   | RoofSurface | `IfcSlab` (ROOF) in einem `IfcRoof` | 25 cm |
   | WallSurface | `IfcWall` | 30 cm |
   | GroundSurface | `IfcSlab` (BASESLAB) | 30 cm |

5. **Eigenschaften (Psets):**
   - `CityGML_Herkunft` am Gebäude und an jedem Bauteil: gml:id, Quelle, Funktion, Dachform, Höhe
   - `PV_Potenzial` an jeder Dachfläche: Neigung, Azimut, Fläche, Einstrahlung, spezifischer Ertrag, kWp, kWh/a, Eignung
6. **Prüfen:** Am Ende prüft `ifcopenshell.validate` das Modell gegen das IFC-Schema.

## 5. In Bonsai ansehen

1. Blender starten → **File → Open IFC Project** → eure `.ifc`-Datei.
2. **Outliner:** Site → Building → Storey „LoD2 Hülle“ → Dach, Wände, Bodenplatte.
3. **Georeferenz:** *Project Setup → Georeferencing* zeigt EPSG:25832, Eastings und Northings.
4. **PV-Werte:** eine Dachfläche anklicken → *Object Properties → Property Sets → PV_Potenzial*.

Dass das Modell in Blender nahe am Nullpunkt liegt, ist richtig so. Die echte Lage steht in der Georeferenzierung.

## 6. Weiter mit Schritt 6

```bash
python module_layout.py ../data/mein_gebaeude.ifc ../data/mein_gebaeude_pv.ifc
```

Damit werden PV-Module als `IfcSolarDevice` auf alle geeigneten Dachflächen gelegt. Details: [SCHRITT6.md](SCHRITT6.md)

## Wenn etwas nicht klappt

| Meldung | Lösung |
|---|---|
| `can't open file '…\citygml_to_ifc.py': No such file or directory` | Ihr steht im falschen Ordner (z. B. `C:\WINDOWS\system32`). Zuerst `cd` in den Ordner `python` des Repos, z. B. `cd C:\Users\<name>\Downloads\greenbim-pv-mainz\python`. |
| `Gebäude … nicht gefunden` | ID falsch kopiert (Groß-/Kleinschreibung beachten). In Sandcastle erneut klicken. |
| `ModuleNotFoundError` | `pip install -r requirements.txt` im Ordner `python/` ausführen. |
| `python` wird nicht gefunden | Python installieren, unter Windows evtl. `py` statt `python` verwenden. |
| `No such file` bei `campus_lod2.gml` | Ihr steht nicht im Ordner `python/`. Mit `cd` hineinwechseln. |

## Grenzen

- **Nur die Hülle:** LoD2 kennt keine Fenster, Türen, Geschosse oder Innenwände.
- **Generalisiert:** Gauben, Schornsteine und Dachfenster fehlen.
- **Bauteildicken sind Annahmen**, nicht gemessen.
- An Rücksprüngen oder Doppelhaus-Fugen können einzelne Wandscheiben überstehen.

Für die PV-Planung reicht das. Für eine Ökobilanz braucht ihr euer eigenes, detailliertes Modell. Dafür gibt es `ifc_roofs.py`, siehe Haupt-README.
