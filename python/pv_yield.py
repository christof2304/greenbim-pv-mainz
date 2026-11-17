"""Jährliche Einstrahlung und PV-Ertrag je Dachfläche mit pvlib.

Ablauf
  1. Wetterdaten: typisches Referenzjahr (TMY) von PVGIS (EU JRC) für Mainz,
     zwischengespeichert in data/tmy_mainz.csv (danach offline nutzbar).
  2. Für ein Raster aus Neigung (0..90°) x Azimut (0..355°) wird die jährliche
     Einstrahlung auf die geneigte Fläche (POA, Perez-Modell) und der spezifische
     Ertrag in kWh/kWp berechnet (PVWatts-Ansatz inkl. Modultemperatur).
     -> data/poa_lookup.json  (wird auch von Sandcastle für die Jahresansicht genutzt)
  3. Jede Dachfläche aus campus_roofs.geojson bekommt per Interpolation:
        irr_kwh_m2   Jahreseinstrahlung auf die Fläche [kWh/m²a]
        yield_kwh_kwp spezifischer Ertrag [kWh/kWp a]
        kwp          installierbare Leistung (Belegungsgrad * Fläche * Wp/m²)
        kwh_a        Jahresertrag [kWh/a]
        class        Eignungsklasse (sehr gut / gut / bedingt / ungeeignet)

Beispiel:
    python pv_yield.py ../data/campus_roofs.geojson ../data/campus_roofs_pv.geojson
"""
import argparse
import sys
import json
import os

import numpy as np
import pandas as pd
import pvlib

LAT, LON, ALT = 49.9884, 8.2274, 150  # Campus HS Mainz
HERE = os.path.dirname(os.path.abspath(__file__))
TMY_CSV = os.path.join(HERE, "..", "data", "tmy_mainz.csv")
LOOKUP_JSON = os.path.join(HERE, "..", "data", "poa_lookup.json")

# Annahmen (bewusst einfach gehalten, im Vortrag diskutieren!)
WP_PER_M2 = 210          # Modulleistung je m² Modulfläche (≈ 430 Wp / 2,0 m²)
GAMMA = -0.0035          # Temperaturkoeffizient Leistung [1/K]
SYSTEM_LOSSES = 0.14     # Kabel, Wechselrichter, Verschmutzung, Mismatch
COVER_PITCHED = 0.70     # Belegungsgrad geneigter Dächer (Ränder, Gauben, Fenster)
COVER_FLAT = 0.45        # Flachdach mit aufgeständerten Modulen (Reihenabstand)
FLAT_RACK_TILT = 15      # Aufständerung auf Flachdächern
FLAT_LIMIT = 10          # Dächer < 10° gelten als Flachdach


def load_tmy():
    if os.path.exists(TMY_CSV):
        df = pd.read_csv(TMY_CSV, index_col=0, parse_dates=True)
    else:
        res = pvlib.iotools.get_pvgis_tmy(LAT, LON, map_variables=True)
        df = res[0]
        df = df[["ghi", "dni", "dhi", "temp_air", "wind_speed"]]
        df.to_csv(TMY_CSV)
    # PVGIS-TMY besteht aus Monaten verschiedener Jahre -> auf ein Jahr normieren
    df.index = pd.date_range("2025-01-01 00:00", periods=len(df), freq="h", tz="UTC") + pd.Timedelta(minutes=30)
    return df


def lookup_table(tmy):
    sp = pvlib.solarposition.get_solarposition(tmy.index, LAT, LON, ALT)
    dni_extra = pvlib.irradiance.get_extra_radiation(tmy.index)
    airmass = pvlib.atmosphere.get_relative_airmass(sp["apparent_zenith"])
    tilts = list(range(0, 91, 5))
    azis = list(range(0, 360, 10))
    irr = np.zeros((len(tilts), len(azis)))
    yld = np.zeros_like(irr)
    params = pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"]["close_mount_glass_glass"]
    for i, t in enumerate(tilts):
        for j, a in enumerate(azis):
            poa = pvlib.irradiance.get_total_irradiance(
                t, a, sp["apparent_zenith"], sp["azimuth"], tmy["dni"], tmy["ghi"], tmy["dhi"],
                dni_extra=dni_extra, airmass=airmass, model="perez", albedo=0.2,
            )["poa_global"].fillna(0).clip(lower=0)
            tc = pvlib.temperature.sapm_cell(poa, tmy["temp_air"], tmy["wind_speed"], **params)
            p_dc = poa / 1000 * (1 + GAMMA * (tc - 25))          # kW je kWp
            irr[i, j] = poa.sum() / 1000                          # kWh/m²a
            yld[i, j] = p_dc.sum() * (1 - SYSTEM_LOSSES)          # kWh/kWp a
    return {"tilts": tilts, "azimuths": azis, "irr_kwh_m2": irr.round(1).tolist(),
            "yield_kwh_kwp": yld.round(1).tolist(), "lat": LAT, "lon": LON, "source": "PVGIS TMY, pvlib Perez"}


def interp(table, key, tilt, az):
    """Bilineare Interpolation im Neigung/Azimut-Raster (Azimut zyklisch)."""
    T, A = table["tilts"], table["azimuths"]
    v = np.array(table[key])
    ti = np.clip(tilt / 5, 0, len(T) - 1.0001)
    i0, ft = int(ti), ti - int(ti)
    aj = (az % 360) / 10
    j0, fa = int(aj) % len(A), aj - int(aj)
    j1 = (j0 + 1) % len(A)
    return ((1 - ft) * ((1 - fa) * v[i0, j0] + fa * v[i0, j1])
            + ft * ((1 - fa) * v[i0 + 1, j0] + fa * v[i0 + 1, j1]))


def classify(spec):
    if spec >= 950:
        return "sehr gut"
    if spec >= 850:
        return "gut"
    if spec >= 700:
        return "bedingt"
    return "ungeeignet"


def evaluate_roof(table, tilt, az, area):
    if tilt < FLAT_LIMIT:
        # Flachdach: Module nach Süden aufgeständert, Grundfläche * Belegungsgrad
        t_eff, a_eff, cover = FLAT_RACK_TILT, 180, COVER_FLAT
    else:
        t_eff, a_eff, cover = tilt, az, COVER_PITCHED
    irr = interp(table, "irr_kwh_m2", t_eff, a_eff)
    spec = interp(table, "yield_kwh_kwp", t_eff, a_eff)
    kwp = area * cover * WP_PER_M2 / 1000
    if spec < 700:
        kwp = 0.0
    return dict(irr_kwh_m2=round(irr), yield_kwh_kwp=round(spec), kwp=round(kwp, 1),
                kwh_a=round(kwp * spec), **{"class": classify(spec)})


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help="GeoJSON aus citygml_roofs.py")
    ap.add_argument("dst")
    a = ap.parse_args()

    tmy = load_tmy()
    print(f"TMY: GHI {tmy['ghi'].sum()/1000:.0f} kWh/m²a, mittlere Temperatur {tmy['temp_air'].mean():.1f} °C")
    table = lookup_table(tmy)
    with open(LOOKUP_JSON, "w", encoding="utf-8") as f:
        json.dump(table, f, separators=(",", ":"))
    best = np.unravel_index(np.argmax(table["yield_kwh_kwp"]), np.array(table["yield_kwh_kwp"]).shape)
    print(f"Optimum: Neigung {table['tilts'][best[0]]}°, Azimut {table['azimuths'][best[1]]}° -> "
          f"{table['yield_kwh_kwp'][best[0]][best[1]]:.0f} kWh/kWp a")

    gj = json.load(open(a.src, encoding="utf-8"))
    for ft in gj["features"]:
        p = ft["properties"]
        p.update(evaluate_roof(table, p["tilt"], p["azimuth"], p["area"]))
    json.dump(gj, open(a.dst, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

    df = pd.DataFrame([f["properties"] for f in gj["features"]])
    df.to_csv(os.path.splitext(a.dst)[0] + ".csv", index=False, sep=";", decimal=",")
    print(df.groupby("class")[["area", "kwp", "kwh_a"]].sum().round(0))
    print(f"Summe: {df.kwp.sum():,.0f} kWp, {df.kwh_a.sum()/1e6:,.2f} GWh/a "
          f"(≈ {df.kwh_a.sum()/3500:,.0f} Haushalte à 3500 kWh)")


if __name__ == "__main__":
    main()
