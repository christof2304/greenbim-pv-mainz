"""Erzeugt die vier Code-Stufen für Schritt 4 aus einer Vorlage.

    python make_stufen.py

Vorlage:  schritt4/_vorlage.js  (alle drei TODOs offen, Platzhalter {{KOPF}})
Ausgabe:  schritt4/stufe0_start.js … stufe3_einfallswinkel.js
          schritt4/README.md  (Snippets mit Kopier-Button auf GitHub)

Jede Stufe ist eine vollständige, lauffähige Datei: einfach komplett in
Sandcastle einfügen und "Run" klicken.
"""
import os

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schritt4")

TODOS = [
    {
        "nr": 1,
        "titel": "Farbe",
        "datei": "stufe1_farbe.js",
        "sicht": "Dächer farbig, aber alle gleich",
        "offen": (
            "      // TODO 1: Farbe aus der Einstrahlung E berechnen (0 W/m² = blau, 1000 W/m² = rot)\n"
            "      //   Tipp: Es gibt oben eine Funktion ramp(wert, min, max)\n"
            "      color = Cesium.Color.WHITE;\n"
        ),
        "geloest": (
            "      // ✔ TODO 1 gelöst: Farbe aus der Einstrahlung (0 W/m² = blau, 1000 W/m² = rot)\n"
            "      color = ramp(E, 0, 1000);\n"
        ),
        "vorher": "color = Cesium.Color.WHITE;",
        "nachher": "color = ramp(E, 0, 1000);",
        "wo": "in der Funktion updateColors(), Abschnitt 7",
        "effekt": "Die Dächer werden farbig, aber alle gleich: Noch gilt jedes Dach als flach und steht senkrecht zur Sonne.",
    },
    {
        "nr": 2,
        "titel": "Dachnormale",
        "datei": "stufe2_normale.js",
        "sicht": "fast unverändert, nur kleine Unterschiede nach Neigung",
        "offen": (
            "  // TODO 2: Normalenvektor der Dachfläche in ENU (x = Ost, y = Nord, z = Oben)\n"
            "  //   Flachdach (t = 0°) → (0, 0, 1); senkrecht nach Süden (t = 90°, a = 180°) → (0, −1, 0)\n"
            "  //   Tipp: Der waagerechte Anteil ist sin(t), aufgeteilt mit sin(a) nach Ost und cos(a) nach Nord\n"
            "  return new Cesium.Cartesian3(0, 0, 1);\n"
        ),
        "geloest": (
            "  // ✔ TODO 2 gelöst: Neigung t kippt den Pfeil, Azimut a dreht ihn in die Himmelsrichtung\n"
            "  return new Cesium.Cartesian3(Math.sin(t) * Math.sin(a), Math.sin(t) * Math.cos(a), Math.cos(t));\n"
        ),
        "vorher": "return new Cesium.Cartesian3(0, 0, 1);",
        "nachher": "return new Cesium.Cartesian3(Math.sin(t) * Math.sin(a), Math.sin(t) * Math.cos(a), Math.cos(t));",
        "wo": "in der Funktion surfaceNormalENU(), Abschnitt 6",
        "effekt": "Jedes Dach kennt jetzt seine Neigung und Richtung. Sichtbar ist das erst nach TODO 3, denn bisher wird die Richtung noch nicht mit der Sonne verglichen.",
    },
    {
        "nr": 3,
        "titel": "Einfallswinkel",
        "datei": "stufe3_einfallswinkel.js",
        "sicht": "Sonnenseiten rot, Schattenseiten blau = Lösung",
        "offen": (
            "  // TODO 3: Kosinus des Einfallswinkels zwischen Dachnormale n und Sonnenrichtung sun\n"
            "  //   Tipp: Beide sind Einheitsvektoren → Skalarprodukt (Cesium.Cartesian3.dot)\n"
            "  const cosTheta = 1;\n"
        ),
        "geloest": (
            "  // ✔ TODO 3 gelöst: Skalarprodukt zweier Einheitsvektoren = Kosinus des Winkels\n"
            "  const cosTheta = Cesium.Cartesian3.dot(n, sun);\n"
        ),
        "vorher": "const cosTheta = 1;",
        "nachher": "const cosTheta = Cesium.Cartesian3.dot(n, sun);",
        "wo": "in der Funktion irradiance(), Abschnitt 6",
        "effekt": "Fertig: Sonnenseiten werden rot, abgewandte Seiten blau, und alles wandert mit der Uhrzeit. Die Legende zeigt jetzt die Gesamtleistung.",
    },
]

KOPF = """// =====================================================================
//  Green BIM – HS Mainz | Schritt 4 · {stufe}
//  {beschreibung}
//  Komplett in https://sandcastle.cesium.com einfügen und "Run" klicken.
//  Alle Stufen: github.com/christof2304/greenbim-pv-mainz/tree/main/sandcastle/schritt4
// =====================================================================
"""


def main():
    vorlage = open(os.path.join(HERE, "_vorlage.js"), encoding="utf-8").read()
    for t in TODOS:
        assert t["offen"] in vorlage, f"TODO {t['nr']} nicht in der Vorlage gefunden"

    stufen = [("stufe0_start.js", "Stufe 0 von 3: Start",
               "Drei Lücken (TODO 1–3). Die Dächer sind noch weiß. Weiter mit stufe1_farbe.js")]
    for t in TODOS:
        naechste = f"Weiter mit {TODOS[t['nr']]['datei']}" if t["nr"] < 3 else "Das ist die fertige Lösung."
        stufen.append((t["datei"], f"Stufe {t['nr']} von 3: {t['titel']}",
                       f"Gelöst bis TODO {t['nr']}. {naechste}"))

    code = vorlage
    for i, (datei, stufe, beschreibung) in enumerate(stufen):
        if i > 0:
            t = TODOS[i - 1]
            code = code.replace(t["offen"], t["geloest"])
        text = code.replace("{{KOPF}}\n", KOPF.format(stufe=stufe, beschreibung=beschreibung))
        with open(os.path.join(HERE, datei), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("geschrieben:", datei)

    # Stufe 4: Lösung + Gebäudeauswahl, Modulbelegung und Python-Befehl (Brücke zu Schritt 5/6)
    zusatz = open(os.path.join(HERE, "_stufe4_zusatz.js"), encoding="utf-8").read()
    text = code.replace("{{KOPF}}\n", KOPF.format(
        stufe="Stufe 4: Vom Stadtmodell zum Gebäude",
        beschreibung="Lösung + Dach anklicken → Module legen, Python-Befehl für Schritt 5+6")) + zusatz
    with open(os.path.join(HERE, "stufe4_gebaeude.js"), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("geschrieben: stufe4_gebaeude.js")

    # README mit kopierbaren Snippets
    raw = "https://raw.githubusercontent.com/christof2304/greenbim-pv-mainz/main/sandcastle/schritt4"
    md = [
        "# Schritt 4: Einstrahlung auf jede Dachfläche",
        "",
        "Zwei Wege, ihr könnt jederzeit wechseln:",
        "",
        "- **Selbst tippen:** `stufe0_start.js` in Sandcastle einfügen, dann die drei Zeilen unten der Reihe nach ersetzen.",
        "- **Aufholen:** Die Datei der nächsten Stufe komplett einfügen (Datei öffnen → Button *Copy raw file*) und **Run** klicken.",
        "",
        "Token: In der Zeile `// Cesium.Ion.defaultAccessToken = \"HIER_EUREN_TOKEN_EINFÜGEN\";` (Abschnitt 1, ganz oben) die `//` entfernen und den Token aus dem Zoom-Chat einsetzen.",
        "",
        "| Stufe | Datei | Was man sieht |",
        "|---|---|---|",
        f"| 0 | [stufe0_start.js](stufe0_start.js) | Dächer weiß |",
    ]
    for t in TODOS:
        md.append(f"| {t['nr']} | [{t['datei']}]({t['datei']}) | {t['sicht']} |")
    md.append("| 4 | [stufe4_gebaeude.js](stufe4_gebaeude.js) | Lösung + Gebäude anklicken, Module legen, Python-Befehl |")
    for t in TODOS:
        md += [
            "",
            f"## TODO {t['nr']}: {t['titel']}",
            "",
            f"Wo: {t['wo']}. Diese Zeile suchen (Strg+F):",
            "",
            "```js",
            t["vorher"],
            "```",
            "",
            "ersetzen durch:",
            "",
            "```js",
            t["nachher"],
            "```",
            "",
            f"Ergebnis: {t['effekt']}",
            "",
            f"Nicht geklappt? Ganze Datei nehmen: [{t['datei']}]({t['datei']})",
        ]
    md += [
        "",
        "## Stufe 4: Vom Stadtmodell zum Gebäude",
        "",
        "[stufe4_gebaeude.js](stufe4_gebaeude.js) ist die Lösung plus drei Buttons oben links:",
        "",
        "1. Auf ein **Dach** klicken: Das Gebäude ist ausgewählt (Anzeige oben rechts).",
        "2. **Module legen**: PV-Module wie in `python/module_layout.py` direkt im 3D-Modell, mit Anzahl, kWp, kWh/a und CO₂.",
        "3. **Module entfernen**: räumt wieder auf.",
        "4. **Befehl Schritt 5+6**: zeigt den fertigen Python-Befehl mit der Gebäude-ID und kopiert ihn, wenn der Browser es erlaubt.",
        "",
        "Das IFC selbst entsteht weiterhin in Python, siehe [`python/SCHRITT5.md`](../../python/SCHRITT5.md) und [`python/SCHRITT6.md`](../../python/SCHRITT6.md).",
        "Sandcastle zeigt die Belegung nur an. Für Planung und Ökobilanz braucht ihr die IFC-Datei.",
    ]
    with open(os.path.join(HERE, "README.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(md) + "\n")
    print("geschrieben: README.md")


if __name__ == "__main__":
    main()
