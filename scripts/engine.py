# -*- coding: utf-8 -*-
"""Sports Edge - Motor de futbol (solo libreria estandar)."""
import json
import math
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

API = "https://api.football-data.org/v4"
KEY = os.environ.get("FOOTBALL_DATA_KEY", "").strip()
DATA = "data"

LIGAS = {
    "PL": "Premier League",
    "PD": "LaLiga",
    "SA": "Serie A",
    "BL1": "Bundesliga",
    "FL1": "Ligue 1",
}

MIN_PARTIDOS = 5   # minimo de partidos por equipo para predecir
PRIOR = 4          # suaviza equipos con pocos partidos hacia la media
MAX_GOLES = 10     # rejilla de goles del modelo Poisson
DIAS = 7           # dias hacia delante que se predicen


def ahora():
    return datetime.now(timezone.utc)


def parse_fecha(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def leer_json(nombre, defecto):
    try:
        with open(os.path.join(DATA, nombre), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return defecto


def guardar_json(nombre, obj):
    with open(os.path.join(DATA, nombre), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def pedir(ruta):
    req = urllib.request.Request(API + ruta, headers={"X-Auth-Token": KEY})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def poisson(k, lam):
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def calcular_fuerzas(terminados):
    """terminados: lista de (id_local, id_visit, goles_local, goles_visit)."""
    n = len(terminados)
    if n == 0:
        return None
    media_h = sum(t[2] for t in terminados) / n
    media_a = sum(t[3] for t in terminados) / n
    media = (media_h + media_a) / 2
    if media <= 0:
        return None
    eq = {}
    for h, a, gh, ga in terminados:
        for tid, f, c in ((h, gh, ga), (a, ga, gh)):
            e = eq.setdefault(tid, {"pj": 0, "f": 0, "c": 0})
            e["pj"] += 1
            e["f"] += f
            e["c"] += c
    res = {}
    for tid, e in eq.items():
        ataque = (e["f"] + PRIOR * media) / (e["pj"] + PRIOR) / media
        defensa = (e["c"] + PRIOR * media) / (e["pj"] + PRIOR) / media
        res[tid] = (ataque, defensa, e["pj"])
    return media_h, media_a, res


def predecir(fz, h, a):
    media_h, media_a, eq = fz
    if h not in eq or a not in eq:
        return None
    if eq[h][2] < MIN_PARTIDOS or eq[a][2] < MIN_PARTIDOS:
        return None
    lh = media_h * eq[h][0] * eq[a][1]
    la = media_a * eq[a][0] * eq[h][1]
    ph = pe = pa = 0.0
    for i in range(MAX_GOLES + 1):
        pi = poisson(i, lh)
        for j in range(MAX_GOLES + 1):
            p = pi * poisson(j, la)
            if i > j:
                ph += p
            elif i == j:
                pe += p
            else:
                pa += p
    s = ph + pe + pa
    return {
        "p_local": round(ph / s, 4),
        "p_empate": round(pe / s, 4),
        "p_visitante": round(pa / s, 4),
        "xg_local": round(lh, 2),
        "xg_visitante": round(la, 2),
        "n_partidos": min(eq[h][2], eq[a][2]),
    }


def signo(gh, ga):
    if gh > ga:
        return "1"
    if gh == ga:
        return "X"
    return "2"


def main():
    if not KEY:
        print("ERROR: falta el secret FOOTBALL_DATA_KEY")
        sys.exit(1)
    os.makedirs(DATA, exist_ok=True)

    hist = leer_json("historial.json", {"predicciones": []})
    lista = hist.get("predicciones", [])
    por_id = {p["id"]: p for p in lista}
    t_ahora = ahora()
    limite = t_ahora + timedelta(days=DIAS)
    proximos = []
    errores = 0
    nuevas = 0
    resueltas = 0

    for i, (codigo, nombre) in enumerate(LIGAS.items()):
        if i > 0:
            time.sleep(7)  # limite gratuito: 10 llamadas por minuto
        try:
            datos = pedir("/competitions/%s/matches" % codigo)
        except Exception as e:
            print("Aviso: no se pudo leer %s (%s)" % (codigo, e))
            errores += 1
            continue

        ms = datos.get("matches", [])
        terminados = []
        for m in ms:
            if m.get("status") == "FINISHED":
                ft = (m.get("score") or {}).get("fullTime") or {}
                if ft.get("home") is not None and ft.get("away") is not None:
                    terminados.append((m["homeTeam"]["id"], m["awayTeam"]["id"], ft["home"], ft["away"]))
                    p = por_id.get(m["id"])
                    if p is not None and p.get("resultado") is None:
                        p["resultado"] = signo(ft["home"], ft["away"])
                        p["marcador"] = "%d-%d" % (ft["home"], ft["away"])
                        resueltas += 1

        fz = calcular_fuerzas(terminados)

        for m in ms:
            if m.get("status") not in ("SCHEDULED", "TIMED"):
                continue
            try:
                fecha = parse_fecha(m["utcDate"])
            except Exception:
                continue
            if fecha <= t_ahora or fecha > limite:
                continue
            h = m["homeTeam"]
            a = m["awayTeam"]
            if h.get("id") is None or a.get("id") is None:
                continue
            proximos.append({"id": m["id"], "liga": nombre, "fecha": m["utcDate"],
                             "local": h.get("name"), "visitante": a.get("name")})
            if m["id"] in por_id or fz is None:
                continue
            pred = predecir(fz, h["id"], a["id"])
            if pred is None:
                continue  # Sin datos suficientes: no se inventa nada
            reg = {"id": m["id"], "liga": nombre, "fecha": m["utcDate"],
                   "local": h.get("name"), "visitante": a.get("name"),
                   "creada": t_ahora.strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "resultado": None, "marcador": None}
            reg.update(pred)
            lista.append(reg)
            por_id[m["id"]] = reg
            nuevas += 1

    if errores == len(LIGAS):
        print("ERROR: no se pudo leer ninguna liga. No se cambia nada.")
        sys.exit(1)

    stamp = t_ahora.strftime("%Y-%m-%d %H:%M UTC")

    # Historial (las predicciones antiguas nunca se modifican)
    hist["predicciones"] = lista
    hist["actualizado"] = stamp
    guardar_json("historial.json", hist)

    # Predicciones visibles en la web: partidos pendientes
    visibles = []
    for p in lista:
        if p.get("resultado") is not None:
            continue
        if parse_fecha(p["fecha"]) < t_ahora - timedelta(hours=3):
            continue
        q = dict(p)
        q["razon_es"] = ("Goles esperados: %.2f - %.2f. Modelo de Poisson con los resultados reales de liga "
                         "de esta temporada (%d partidos por equipo como minimo)." %
                         (p["xg_local"], p["xg_visitante"], p["n_partidos"]))
        q["razon_en"] = ("Expected goals: %.2f - %.2f. Poisson model built from real league results "
                         "this season (at least %d matches per team)." %
                         (p["xg_local"], p["xg_visitante"], p["n_partidos"]))
        visibles.append(q)
    visibles.sort(key=lambda x: x["fecha"])
    guardar_json("predicciones.json", {"actualizado": stamp, "predicciones": visibles})

    guardar_json("partidos.json", {"actualizado": stamp,
                                   "partidos": sorted(proximos, key=lambda x: x["fecha"])})

    # Estadisticas del historial
    res = [p for p in lista if p.get("resultado") is not None]
    if res:
        aciertos = 0
        brier = 0.0
        for p in res:
            probs = {"1": p["p_local"], "X": p["p_empate"], "2": p["p_visitante"]}
            if max(probs, key=probs.get) == p["resultado"]:
                aciertos += 1
            brier += sum((probs[k] - (1.0 if k == p["resultado"] else 0.0)) ** 2 for k in probs)
        acierto = round(aciertos / len(res), 4)
        brier = round(brier / len(res), 4)
    else:
        acierto = None
        brier = None
    guardar_json("estadisticas.json", {"actualizado": stamp, "total": len(lista),
                                       "resueltas": len(res), "acierto": acierto, "brier": brier})

    print("OK: %d nuevas predicciones, %d resultados anotados, %d en historial" %
          (nuevas, resueltas, len(lista)))


if __name__ == "__main__":
    main()
