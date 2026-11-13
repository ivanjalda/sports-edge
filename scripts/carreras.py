# -*- coding: utf-8 -*-
"""Sports Edge - Carreras: Formula 1 y MotoGP (solo libreria estandar).

Datos reales:
  - Formula 1: API publica Jolpica (continuacion de Ergast): resultados, clasificaciones y sprints desde 2014.
  - MotoGP: resultados oficiales publicos de motogp.com (carrera, sprint y clasificacion) desde 2016.
Motor propio: motor_carreras.py (fuerza de piloto y equipo + parrilla + abandonos, probado en carreras no vistas).

Salida:
  data/carreras_{serie}.json            proxima carrera con probabilidades, fuerzas y pruebas del motor
  data/carreras_{serie}_historial.json  predicciones guardadas ANTES de cada carrera (nunca se cambian) y su resultado
  data/carreras_{serie}_resultados.json cache de resultados reales
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import motor_carreras as MC

DATA = "data"
UA = "Mozilla/5.0 (compatible; sports-edge/1.0; +https://ivanjalda.github.io/sports-edge/)"
JOL = "https://api.jolpi.ca/ergast/f1/"
MGP = "https://api.motogp.pulselive.com/motogp/v1/results/"
LIMITE_SEG = 8 * 60          # tiempo maximo de descarga por serie en cada ejecucion
DIAS_PREVIA = 7              # la prediccion "previa" se guarda en los 7 dias antes de la carrera

SERIES = {
    "f1": {"nombre": "Fórmula 1", "desde": 2014},
    "motogp": {"nombre": "MotoGP", "desde": 2016},
}


# ------------------------------------------------------------------ utilidades
def leer_json(nombre, defecto):
    try:
        with open(os.path.join(DATA, nombre), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return defecto


def guardar_json(nombre, obj, compacto=False):
    with open(os.path.join(DATA, nombre), "w", encoding="utf-8") as f:
        if compacto:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(obj, f, ensure_ascii=False, indent=1)


def pedir(url, intentos=3, pausa=0.4):
    ult = None
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read().decode("utf-8"))
            time.sleep(pausa)
            return d
        except urllib.error.HTTPError as ex:
            ult = ex
            if ex.code == 429:
                time.sleep(8 * (i + 1))
            elif ex.code in (400, 404):
                break
            else:
                time.sleep(2 * (i + 1))
        except Exception as ex:
            ult = ex
            time.sleep(2 * (i + 1))
    raise RuntimeError("%s -> %s" % (url, ult))


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    s = str(s).replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        d = datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def a_int(x):
    try:
        v = int(str(x))
        return v if v > 0 else None
    except Exception:
        return None


# ------------------------------------------------------------------ Formula 1 (Jolpica)
def jol_paginas(ruta, lista):
    """Junta todas las paginas (100 filas cada una) en carreras por ronda."""
    carreras, off, total = {}, 0, None
    while total is None or off < total:
        d = pedir("%s%s?limit=100&offset=%d" % (JOL, ruta, off))
        mr = d.get("MRData", {})
        total = int(mr.get("total", 0))
        for rc in mr.get("RaceTable", {}).get("Races", []):
            r = int(rc["round"])
            if r not in carreras:
                carreras[r] = dict(rc)
                carreras[r][lista] = []
            carreras[r][lista].extend(rc.get(lista, []))
        off += 100
        if total == 0:
            break
    return carreras


def f1_hora(rc):
    return "%sT%s" % (rc["date"], rc.get("time") or "13:00:00Z")


def f1_filas(lista, parrilla):
    res = []
    for r in lista:
        pt = str(r.get("positionText", ""))
        if pt in ("W", "F"):        # no tomo la salida / no se clasifico
            continue
        did = r["Driver"]["driverId"]
        res.append({"id": did, "n": "%s %s" % (r["Driver"].get("givenName", ""), r["Driver"].get("familyName", "")),
                    "eq": r["Constructor"]["name"], "pos": a_int(r.get("position")) if pt.isdigit() else None,
                    "grid": parrilla.get(did)})
    return res


def f1_temporada(y):
    res = jol_paginas("%d/results.json" % y, "Results")
    qua = jol_paginas("%d/qualifying.json" % y, "QualifyingResults")
    spr = jol_paginas("%d/sprint.json" % y, "SprintResults") if y >= 2021 else {}
    out = []
    for rd, rc in res.items():
        q = {x["Driver"]["driverId"]: a_int(x.get("position")) for x in qua.get(rd, {}).get("QualifyingResults", [])}
        base = {"temporada": y, "ronda": rd, "nombre": rc["raceName"], "circuito": rc["Circuit"]["circuitName"],
                "pais": rc["Circuit"].get("Location", {}).get("country", "")}
        out.append(dict(base, id="f1-%d-%02d" % (y, rd), fecha=f1_hora(rc), sprint=False,
                        res=f1_filas(rc["Results"], q)))
        if rd in spr:
            sg = {x["Driver"]["driverId"]: a_int(x.get("grid")) for x in spr[rd]["SprintResults"]}
            out.append(dict(base, id="f1-%d-%02d-s" % (y, rd), fecha=f1_hora(spr[rd]), sprint=True,
                            res=f1_filas(spr[rd]["SprintResults"], sg)))
    return out


def f1_proxima(ahora, ultima_principal):
    """Proxima carrera del calendario oficial y, si ya hubo clasificacion, la parrilla."""
    for y in (ahora.year, ahora.year + 1):
        try:
            d = pedir("%s%d.json" % (JOL, y))
        except Exception as ex:
            print("Aviso: calendario %d no disponible (%s)" % (y, ex))
            continue
        for rc in d["MRData"]["RaceTable"]["Races"]:
            f = parse_iso(f1_hora(rc))
            if f > ahora - timedelta(hours=3):
                rd = int(rc["round"])
                prox = {"id": "f1-%d-%02d" % (y, rd), "temporada": y, "nombre": rc["raceName"],
                        "circuito": rc["Circuit"]["circuitName"], "pais": rc["Circuit"].get("Location", {}).get("country", ""),
                        "fecha": iso(f), "clasif": None, "sprint": "Sprint" in rc}
                if rc.get("Qualifying"):
                    prox["clasif"] = "%sT%s" % (rc["Qualifying"]["date"], rc["Qualifying"].get("time") or "15:00:00Z")
                pil = []
                try:
                    q = jol_paginas("%d/%d/qualifying.json" % (y, rd), "QualifyingResults").get(rd)
                except Exception:
                    q = None
                if q and q.get("QualifyingResults"):
                    for x in q["QualifyingResults"]:
                        pil.append({"id": x["Driver"]["driverId"],
                                    "n": "%s %s" % (x["Driver"].get("givenName", ""), x["Driver"].get("familyName", "")),
                                    "eq": x["Constructor"]["name"], "grid": a_int(x.get("position"))})
                    prox["parrilla"] = True
                else:
                    prox["parrilla"] = False
                    if ultima_principal and ultima_principal["temporada"] == y:
                        pil = [{"id": r["id"], "n": r["n"], "eq": r["eq"], "grid": None} for r in ultima_principal["res"]]
                if not pil and ultima_principal:
                    pil = [{"id": r["id"], "n": r["n"], "eq": r["eq"], "grid": None} for r in ultima_principal["res"]]
                prox["pilotos"] = pil
                return prox
    return None


def descargar_f1(cache, ahora):
    """Devuelve True si el historico quedo completo hasta hoy."""
    t0 = time.time()
    completo = True
    hechas = set(cache.get("temporadas_completas", []))
    for y in range(SERIES["f1"]["desde"], ahora.year + 1):
        if y in hechas:
            continue
        if time.time() - t0 > LIMITE_SEG:
            print("Aviso: descarga cortada por tiempo. Se continua en la proxima ejecucion.")
            completo = False
            break
        try:
            carreras = f1_temporada(y)
        except Exception as ex:
            print("Aviso: temporada %d de F1 no disponible (%s)" % (y, ex))
            completo = False
            continue
        for c in carreras:
            cache["carreras"][c["id"]] = c
        print("  F1 %d: %d carreras y sprints" % (y, len(carreras)))
        if y < ahora.year:
            hechas.add(y)
    cache["temporadas_completas"] = sorted(hechas)
    return completo


# ------------------------------------------------------------------ MotoGP (resultados oficiales)
def mgp_temporadas():
    return {int(s["year"]): s["id"] for s in pedir(MGP + "seasons", pausa=0.2)}


def mgp_categoria(season_id):
    for c in pedir(MGP + "categories?seasonUuid=" + season_id, pausa=0.2):
        if str(c.get("name", "")).startswith("MotoGP"):
            return c["id"]
    return None


def mgp_clasif(sesion_id):
    d = pedir(MGP + "session/%s/classification?test=false" % sesion_id, pausa=0.2)
    return d.get("classification") or []


def mgp_parrilla(sesiones):
    """Parrilla a partir de la clasificacion: Q2 da las posiciones 1-12; de Q1 pasan 2 a Q2, el resto sale del 13."""
    grid = {}
    q1 = [s for s in sesiones if s.get("type") == "Q" and str(s.get("number")) == "1" and s.get("status") == "FINISHED"]
    q2 = [s for s in sesiones if s.get("type") == "Q" and str(s.get("number")) == "2" and s.get("status") == "FINISHED"]
    if q2:
        for x in mgp_clasif(q2[0]["id"]):
            p = a_int(x.get("position"))
            if p:
                grid[x["rider"]["id"]] = p
    if q1:
        for x in mgp_clasif(q1[0]["id"]):
            p = a_int(x.get("position"))
            if p and p >= 3 and x["rider"]["id"] not in grid:
                grid[x["rider"]["id"]] = 10 + p
    return grid


def mgp_filas(clasif, grid):
    res = []
    for x in clasif:
        rid = x["rider"]["id"]
        res.append({"id": rid, "n": x["rider"].get("full_name", ""), "eq": (x.get("team") or {}).get("name", ""),
                    "pos": a_int(x.get("position")), "grid": grid.get(rid)})
    return res


def mgp_evento(y, ev, cat):
    ses = pedir(MGP + "sessions?eventUuid=%s&categoryUuid=%s" % (ev["id"], cat), pausa=0.2)
    grid = mgp_parrilla(ses)
    out = []
    base = {"temporada": y, "nombre": ev.get("name", "").title().replace(" Of ", " of "), "circuito": (ev.get("circuit") or {}).get("name", ""),
            "pais": (ev.get("country") or {}).get("name", "")}
    for s in ses:
        if s.get("type") not in ("RAC", "SPR") or s.get("status") != "FINISHED":
            continue
        cl = mgp_clasif(s["id"])
        if not cl:
            continue
        sp = s["type"] == "SPR"
        out.append(dict(base, id="mgp-%d-%s%s" % (y, ev.get("short_name", ev["id"][:6]), "-s" if sp else ""),
                        fecha=iso(parse_iso(s["date"])), sprint=sp, res=mgp_filas(cl, grid)))
    return out


def descargar_motogp(cache, ahora):
    """Devuelve True si el historico quedo completo hasta hoy."""
    t0 = time.time()
    completo = True
    hechos = set(cache.get("eventos_hechos", []))
    try:
        temps = mgp_temporadas()
    except Exception as ex:
        print("Aviso: no se pudo leer la lista de temporadas de MotoGP (%s)" % ex)
        return False
    cache["_temps"] = {str(k): v for k, v in temps.items()}
    for y in sorted(temps):
        if y < SERIES["motogp"]["desde"] or y > ahora.year:
            continue
        try:
            cat = mgp_categoria(temps[y])
            evs = pedir(MGP + "events?seasonUuid=%s&isFinished=true" % temps[y], pausa=0.2)
        except Exception as ex:
            print("Aviso: temporada %d de MotoGP no disponible (%s)" % (y, ex))
            completo = False
            continue
        cache.setdefault("_cat", {})[str(y)] = cat
        n = 0
        for ev in evs:
            if ev.get("test") or ev["id"] in hechos:
                continue
            if time.time() - t0 > LIMITE_SEG:
                print("Aviso: descarga cortada por tiempo. Se continua en la proxima ejecucion.")
                cache["eventos_hechos"] = sorted(hechos)
                return False
            try:
                for c in mgp_evento(y, ev, cat):
                    cache["carreras"][c["id"]] = c
                hechos.add(ev["id"])
                n += 1
            except Exception as ex:
                print("Aviso: evento %s no disponible (%s)" % (ev.get("short_name"), ex))
                completo = False
        if n:
            print("  MotoGP %d: %d grandes premios nuevos" % (y, n))
    cache["eventos_hechos"] = sorted(hechos)
    return completo


def motogp_proxima(cache, ahora, ultima_principal):
    temps = cache.get("_temps") or {}
    y = str(ahora.year)
    if y not in temps:
        return None
    try:
        evs = pedir(MGP + "events?seasonUuid=%s&isFinished=false" % temps[y], pausa=0.2)
        cat = (cache.get("_cat") or {}).get(y) or mgp_categoria(temps[y])
    except Exception as ex:
        print("Aviso: calendario de MotoGP no disponible (%s)" % ex)
        return None
    evs = sorted([e for e in evs if not e.get("test")], key=lambda e: e.get("date_start", ""))
    for ev in evs:
        try:
            ses = pedir(MGP + "sessions?eventUuid=%s&categoryUuid=%s" % (ev["id"], cat), pausa=0.2)
        except Exception:
            continue
        rac = [s for s in ses if s.get("type") == "RAC"]
        if not rac:
            continue
        f = parse_iso(rac[0]["date"])
        if f < ahora - timedelta(hours=3) or rac[0].get("status") == "FINISHED":
            continue
        q = [s for s in ses if s.get("type") == "Q"]
        prox = {"id": "mgp-%s-%s" % (y, ev.get("short_name", ev["id"][:6])), "temporada": int(y),
                "nombre": ev.get("name", "").title().replace(" Of ", " of "), "circuito": (ev.get("circuit") or {}).get("name", ""),
                "pais": (ev.get("country") or {}).get("name", ""), "fecha": iso(f),
                "clasif": iso(parse_iso(q[-1]["date"])) if q else None, "sprint": True}
        grid = mgp_parrilla(ses)
        base = ultima_principal["res"] if ultima_principal else []
        conocidos = {r["id"]: r for r in base}
        pil = []
        if grid:
            # nombres y equipos de la clasificacion
            for s in ses:
                if s.get("type") == "Q" and s.get("status") == "FINISHED":
                    for x in mgp_clasif(s["id"]):
                        rid = x["rider"]["id"]
                        if rid in grid and not any(p["id"] == rid for p in pil):
                            pil.append({"id": rid, "n": x["rider"].get("full_name", ""),
                                        "eq": (x.get("team") or {}).get("name", ""), "grid": grid[rid]})
        prox["parrilla"] = bool(pil)
        if not pil:
            pil = [{"id": r["id"], "n": r["n"], "eq": r["eq"], "grid": None} for r in conocidos.values()]
        prox["pilotos"] = pil
        return prox
    return None


# ------------------------------------------------------------------ prediccion, historial y salida
def pred_carrera(st, aj, prox, abandono):
    con = bool(prox.get("parrilla"))
    filas = [{"id": p["id"], "n": p["n"], "eq": p["eq"], "f": st.fuerza(p["id"], p["eq"]), "grid": p.get("grid")}
             for p in prox["pilotos"]]
    t = aj["t_grid"] if con else aj["t"]
    cg = aj["c_grid"] if con else 0.0
    sim = MC.simular(filas, t, cg, abandono)
    out = []
    for f, (pw, pp, p10) in zip(filas, sim):
        out.append({"id": f["id"], "n": f["n"], "eq": f["eq"], "grid": f.get("grid"), "fuerza": round(f["f"], 1),
                    "pw": round(pw, 4), "pp": round(pp, 4), "p10": round(p10, 4)})
    out.sort(key=lambda x: (-x["pw"], -x["pp"]))
    return out


def resolver(hist, carreras):
    por_id = {c["id"]: c for c in carreras}
    n = 0
    for p in hist["predicciones"]:
        if p.get("resultado") or p["id"] not in por_id:
            continue
        c = por_id[p["id"]]
        gan = [r for r in c["res"] if r.get("pos") == 1]
        if not gan:
            continue
        podio = [r["id"] for r in sorted([r for r in c["res"] if r.get("pos") in (1, 2, 3)], key=lambda r: r["pos"])]
        dado = {x["id"]: x for x in p["pilotos"]}
        nuestro_podio = [x["id"] for x in sorted(p["pilotos"], key=lambda x: -x["pp"])[:3]]
        p["resultado"] = {"ganador": gan[0]["id"], "ganador_n": gan[0]["n"],
                          "podio_n": [next(r["n"] for r in c["res"] if r["id"] == i) for i in podio],
                          "acierto": p["fav"]["id"] == gan[0]["id"],
                          "p_ganador": dado.get(gan[0]["id"], {}).get("pw"),
                          "podio_acertados": len(set(podio) & set(nuestro_podio))}
        n += 1
    return n


def estadisticas(hist):
    """Acierto en directo: se cuenta una prediccion por carrera (la ultima antes de empezar)."""
    por = {}
    for p in hist["predicciones"]:
        if not p.get("resultado"):
            continue
        if p["id"] not in por or p["tipo"] == "parrilla":
            por[p["id"]] = p
    ps = list(por.values())
    n = len(ps)
    if not n:
        return {"carreras": 0}
    return {"carreras": n, "favorito_gana": sum(1 for p in ps if p["resultado"]["acierto"]),
            "acierto": round(sum(1 for p in ps if p["resultado"]["acierto"]) / float(n), 4),
            "podio": round(sum(p["resultado"]["podio_acertados"] for p in ps) / (3.0 * n), 4)}


def procesar(clave, ahora, stamp):
    cfg = SERIES[clave]
    print("---- %s" % cfg["nombre"])
    cache = leer_json("carreras_%s_resultados.json" % clave, {"carreras": {}})
    cache.setdefault("carreras", {})
    if clave == "f1":
        completo = descargar_f1(cache, ahora)
    else:
        completo = descargar_motogp(cache, ahora)
    if not completo:
        print("AVISO: el historico aun no esta completo hasta hoy. No se publica ni se guarda ninguna prediccion.")
    carreras = sorted(cache["carreras"].values(), key=lambda c: (c["fecha"], 0 if c.get("sprint") else 1))
    carreras = [c for c in carreras if len(c["res"]) >= 10]
    print("Carreras con resultado real: %d (%d principales)" % (len(carreras), sum(1 for c in carreras if not c.get("sprint"))))
    guardar_json("carreras_%s_resultados.json" % clave, cache, compacto=True)
    if len(carreras) < 60:
        print("Todavia hay pocas carreras descargadas; se continua en la proxima ejecucion.")
        return
    aj = MC.ajustar(carreras)
    if not aj:
        print("No hay suficientes temporadas para probar el motor.")
        return
    a, b = aj["prueba_previa"] or {}, aj["prueba_parrilla"] or {}
    print("Motor propio %s: PRUEBA %s carreras no vistas (temporadas %s)" % (cfg["nombre"], a.get("carreras"), aj["temporadas_prueba"]))
    print("  Antes de la clasificacion: el favorito gana %.1f%% | podio %.1f%% | logloss %.3f (azar %.3f)" %
          (100 * (a.get("favorito_gana") or 0), 100 * (a.get("podio") or 0), a.get("logloss") or 0, aj["azar_logloss"]))
    print("  Con la parrilla: el favorito gana %.1f%% | podio %.1f%% | logloss %.3f | el que sale primero gana %.1f%%" %
          (100 * (b.get("favorito_gana") or 0), 100 * (b.get("podio") or 0), b.get("logloss") or 0, 100 * (b.get("pole_gana") or 0)))
    print("  Ajustes: K %s, peso equipo %s, temperatura %s / %s, peso parrilla %s" %
          (aj["k"], aj["w"], aj["t"], aj["t_grid"], aj["c_grid"]))

    st, _ = MC.recorrer(carreras, aj["k"], aj["w"])
    principales = [c for c in carreras if not c.get("sprint")]
    ultima = principales[-1] if principales else None
    abandono = MC.tasa_abandono(carreras)
    prox = f1_proxima(ahora, ultima) if clave == "f1" else motogp_proxima(cache, ahora, ultima)
    if prox and prox.get("temporada") != st.temp:
        st.nueva_temporada(prox["temporada"])

    hist = leer_json("carreras_%s_historial.json" % clave, {"predicciones": []})
    # Predicciones sin resolver hechas con el historico incompleto no son validas: se retiran
    antes = len(hist["predicciones"])
    hist["predicciones"] = [p for p in hist["predicciones"] if p.get("resultado") or p.get("datos_completos")]
    if len(hist["predicciones"]) < antes:
        print("Se retiran %d predicciones hechas con datos incompletos." % (antes - len(hist["predicciones"])))
    resueltas = resolver(hist, carreras)
    salida_prox = None
    if prox and prox.get("pilotos") and completo:
        pil = pred_carrera(st, aj, prox, abandono)
        tipo = "parrilla" if prox.get("parrilla") else "previa"
        salida_prox = {k: prox[k] for k in ("id", "nombre", "circuito", "pais", "fecha", "clasif", "sprint")}
        salida_prox.update({"tipo": tipo, "pilotos": pil})
        dias = (parse_iso(prox["fecha"]) - ahora).total_seconds() / 86400.0
        ya = any(p["id"] == prox["id"] and p["tipo"] == tipo for p in hist["predicciones"])
        if 0 < dias <= DIAS_PREVIA and not ya:
            hist["predicciones"].append({"id": prox["id"], "nombre": prox["nombre"], "fecha": prox["fecha"], "tipo": tipo,
                                         "creada": stamp, "fav": {"id": pil[0]["id"], "n": pil[0]["n"], "pw": pil[0]["pw"]},
                                         "pilotos": [{"id": x["id"], "n": x["n"], "pw": x["pw"], "pp": x["pp"]} for x in pil],
                                         "datos_completos": True, "resultado": None})
            print("Prediccion guardada (%s): %s -> favorito %s %.0f%%" % (tipo, prox["nombre"], pil[0]["n"], 100 * pil[0]["pw"]))
        print("Proxima: %s (%s) | %s | favorito %s %.0f%% | abandonos %.0f%%" %
              (prox["nombre"], prox["fecha"], "con parrilla" if prox.get("parrilla") else "antes de la clasificacion",
               pil[0]["n"], 100 * pil[0]["pw"], 100 * abandono))
    elif completo:
        print("No hay proxima carrera en el calendario (temporada terminada).")
    guardar_json("carreras_%s_historial.json" % clave, hist)

    # fuerza actual de pilotos y equipos de la ultima carrera
    fuerzas, equipos = [], {}
    if ultima:
        for r in ultima["res"]:
            fuerzas.append({"n": r["n"], "eq": r["eq"], "piloto": round(st.rp.get(r["id"], -10.0), 1),
                            "total": round(st.fuerza(r["id"], r["eq"]), 1)})
            equipos[r["eq"]] = round(st.re.get(r["eq"], 0.0), 1)
    fuerzas.sort(key=lambda x: -x["total"])
    recientes = []
    vistos = set()
    for p in sorted([p for p in hist["predicciones"] if p.get("resultado")], key=lambda p: (p["fecha"], p["tipo"] == "parrilla"), reverse=True):
        if p["id"] in vistos:
            continue
        vistos.add(p["id"])
        recientes.append({"nombre": p["nombre"], "fecha": p["fecha"], "tipo": p["tipo"], "fav": p["fav"], "resultado": p["resultado"]})
    ganadores = [{"nombre": c["nombre"], "fecha": c["fecha"],
                  "ganador": next((r["n"] for r in c["res"] if r.get("pos") == 1), ""),
                  "equipo": next((r["eq"] for r in c["res"] if r.get("pos") == 1), "")}
                 for c in principales[-8:]][::-1]
    salida = {"serie": clave, "nombre": cfg["nombre"], "actualizado": stamp, "proximo": salida_prox, "descargando": not completo,
              "abandono": round(abandono, 4), "motor": aj, "fuerzas": fuerzas,
              "equipos": sorted([{"eq": k, "f": v} for k, v in equipos.items()], key=lambda x: -x["f"]),
              "directo": estadisticas(hist), "recientes": recientes[:12], "ultimas": ganadores,
              "fuentes": "Jolpica (Ergast) · resultados oficiales F1" if clave == "f1" else "Resultados oficiales de motogp.com"}
    guardar_json("carreras_%s.json" % clave, salida)
    print("%s: %d predicciones resueltas ahora. Guardado." % (cfg["nombre"], resueltas))


def main():
    ahora = datetime.now(timezone.utc)
    stamp = ahora.strftime("%Y-%m-%d %H:%M UTC")
    for clave in SERIES:
        try:
            procesar(clave, ahora, stamp)
        except Exception as ex:
            print("ERROR en %s: %s" % (clave, ex))


if __name__ == "__main__":
    main()
