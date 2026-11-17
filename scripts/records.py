# -*- coding: utf-8 -*-
"""Sports Edge - Records calculados con NUESTROS datos reales (solo libreria estandar).

Lee los resultados reales que ya descarga el motor y calcula, para cada competicion:
  - Equipos: mejor balance de una temporada, racha de victorias mas larga, mayor victoria, mas victorias en total.
  - Carreras y golf: mas victorias, mas podios / top 3 y mas victorias en una temporada.
Siempre se indica el periodo que cubren nuestros datos (no es el historico completo del deporte).
Salida: data/records.json (la pagina records.html lo junta con el palmares historico verificado)."""
import glob
import json
import os
from collections import defaultdict
from datetime import datetime, timezone

DATA = "data"
DEP = {"nba": "baloncesto", "euroliga": "baloncesto", "eurocup": "baloncesto", "ncaab": "baloncesto", "wnba": "baloncesto",
       "nhl": "hockey", "ncaah": "hockey", "nfl": "americano", "ncaaf": "americano", "ufc": "mma", "mlb": "beisbol",
       "voley": "voleibol", "rug_6n": "rugby", "rug_prem": "rugby", "rug_top14": "rugby", "rug_urc": "rugby",
       "rug_cc": "rugby", "rug_super": "rugby"}
NOMBRE = {"nba": "NBA", "euroliga": "Euroliga", "eurocup": "Eurocup", "ncaab": "NCAA baloncesto", "wnba": "WNBA",
          "nhl": "NHL", "ncaah": "NCAA hockey", "nfl": "NFL", "ncaaf": "NCAA fútbol americano", "ufc": "UFC", "mlb": "MLB",
          "voley": "NCAA voleibol femenino", "rug_6n": "Seis Naciones", "rug_prem": "Premiership", "rug_top14": "Top 14",
          "rug_urc": "United Rugby Championship", "rug_cc": "Champions Cup", "rug_super": "Super Rugby"}
SERIES = {"f1": ("motor", "Fórmula 1", "podios"), "motogp": ("motor", "MotoGP", "podios"),
          "golf_pga": ("golf", "PGA Tour", "top 3"), "golf_dp": ("golf", "DP World Tour", "top 3")}


def leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def equipos(clave, juegos):
    js = sorted([g for g in juegos.values() if g.get("terminado") and g.get("pl") is not None and g.get("pv") is not None
                 and g["pl"] != g["pv"] and (clave.startswith("rug_") or g.get("tipo") in (2, 3, 5))],
                key=lambda g: g["fecha"])
    if len(js) < 50:
        return None
    temp = defaultdict(lambda: [0, 0])
    total = defaultdict(int)
    racha, mejor_racha = defaultdict(int), {}
    mayor = None
    for g in js:
        gana, pierde = (g["local"], g["visitante"]) if g["pl"] > g["pv"] else (g["visitante"], g["local"])
        if clave.startswith("rug_") or clave == "ufc" or g.get("tipo") == 2:   # balance: solo fase regular
            temp[(gana, g["temporada"])][0] += 1
            temp[(pierde, g["temporada"])][1] += 1
        total[gana] += 1
        racha[gana] += 1
        racha[pierde] = 0
        if racha[gana] > mejor_racha.get("n", 0):
            mejor_racha = {"n": racha[gana], "quien": gana, "hasta": g["fecha"][:10]}
        dif = abs(g["pl"] - g["pv"])
        if clave != "ufc" and (mayor is None or dif > mayor["dif"]):
            mayor = {"dif": dif, "quien": gana, "rival": pierde, "marcador": "%d-%d" % (max(g["pl"], g["pv"]), min(g["pl"], g["pv"])),
                     "fecha": g["fecha"][:10]}
    # la temporada en curso no cuenta para "mejor temporada" (aun no ha terminado)
    ult = js[-1]["temporada"]
    en_curso = (datetime.now(timezone.utc) - datetime.strptime(js[-1]["fecha"][:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)).days < 30
    bal = [(k, v) for k, v in temp.items() if v[0] + v[1] >= 10 and not (en_curso and k[1] == ult)]
    mejor_temp = max(bal, key=lambda kv: (kv[1][0] / float(kv[1][0] + kv[1][1]), kv[1][0])) if bal else None
    top = sorted(total.items(), key=lambda kv: -kv[1])[:5]
    out = {"clave": clave, "dep": DEP.get(clave), "nombre": NOMBRE.get(clave, clave),
           "desde": js[0]["fecha"][:10], "hasta": js[-1]["fecha"][:10], "partidos": len(js),
           "mas_victorias": [{"quien": q, "n": n} for q, n in top], "racha": mejor_racha}
    if mejor_temp:
        (q, t), (w, l) = mejor_temp
        out["mejor_temporada"] = {"quien": q, "temporada": t, "v": w, "d": l}
    if mayor:
        out["mayor_victoria"] = mayor
    return out


def carreras(clave, cache):
    cs = [c for c in cache.get("carreras", {}).values() if not c.get("sprint") and len(c.get("res", [])) >= 10]
    if len(cs) < 20:
        return None
    cs.sort(key=lambda c: c["fecha"])
    wins, pods, por_temp, nombres = defaultdict(int), defaultdict(int), defaultdict(int), {}
    for c in cs:
        for r in c["res"]:
            nombres[r["id"]] = r["n"]
            if r.get("pos") == 1:
                wins[r["id"]] += 1
                por_temp[(r["id"], c["temporada"])] += 1
            if r.get("pos") in (1, 2, 3):
                pods[r["id"]] += 1
    dep, nom, etq = SERIES[clave]
    mt = max(por_temp.items(), key=lambda kv: kv[1]) if por_temp else None
    return {"clave": clave, "dep": dep, "nombre": nom, "desde": cs[0]["fecha"][:10], "hasta": cs[-1]["fecha"][:10],
            "partidos": len(cs), "etiqueta_podio": etq,
            "mas_victorias": [{"quien": nombres[i], "n": n} for i, n in sorted(wins.items(), key=lambda kv: -kv[1])[:5]],
            "mas_podios": [{"quien": nombres[i], "n": n} for i, n in sorted(pods.items(), key=lambda kv: -kv[1])[:5]],
            "mejor_temporada": {"quien": nombres[mt[0][0]], "temporada": mt[0][1], "v": mt[1]} if mt else None}


def main():
    out = []
    for ruta in sorted(glob.glob(os.path.join(DATA, "equipos_*_resultados.json"))):
        clave = os.path.basename(ruta)[len("equipos_"):-len("_resultados.json")]
        try:
            r = equipos(clave, leer(ruta).get("juegos", {}))
            if r:
                out.append(r)
        except Exception as ex:
            print("Aviso: %s (%s)" % (clave, ex))
    for clave in SERIES:
        ruta = os.path.join(DATA, "carreras_%s_resultados.json" % clave)
        if not os.path.exists(ruta):
            continue
        try:
            r = carreras(clave, leer(ruta))
            if r:
                out.append(r)
        except Exception as ex:
            print("Aviso: %s (%s)" % (clave, ex))
    salida = {"actualizado": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "competiciones": out}
    with open(os.path.join(DATA, "records.json"), "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=1)
    print("Records calculados para %d competiciones." % len(out))


if __name__ == "__main__":
    main()
