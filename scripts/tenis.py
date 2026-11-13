# -*- coding: utf-8 -*-
"""Sports Edge - Motor de tenis (solo libreria estandar).
Elo general + Elo por superficie con resultados reales (TennisMyLife; respaldo: archivo de Jeff Sackmann).
Partidos proximos y cuotas: The Odds API."""
import csv
import io
import json
import math
import os
import re
import sys
import unicodedata
import tenis_fuente
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

DATA = "data"
KEY = os.environ.get("ODDS_API_KEY", "").strip()
LLAMAR = os.environ.get("ODDS_FETCH", "true").strip().lower() == "true"
RAW = "https://raw.githubusercontent.com/JeffSackmann/tennis_%s/master/%s_matches_%d.csv"
ODDS = "https://api.the-odds-api.com/v4/sports"

ANIO = datetime.now(timezone.utc).year
ANIOS = list(range(2018, ANIO + 1))
EVAL_DESDE = (ANIO - 1) * 10000 + 101   # el backtest evalua desde el 1 de enero del anio pasado
MIN_N = 10            # minimo de partidos de cada jugador para predecir
MIN_SUP = 10          # minimo de partidos en la superficie para usar su Elo
PESO_SUP = 0.5        # peso del Elo de superficie frente al general
MAX_TORNEOS = 6       # maximo de torneos que se consultan por ejecucion
MIN_CREDITOS = 25     # si quedan menos creditos, no se consulta
UMBRAL_VALOR = 0.05
PROB_MIN = 0.10
VENTANA_DIAS = 16
SUPERFICIES = ("Hard", "Clay", "Grass")
ORDEN = {"R128": 1, "R64": 2, "R32": 3, "R16": 4, "QF": 5, "SF": 6, "F": 7, "RR": 3, "BR": 7}

# Superficie por torneo (solo los que conocemos con seguridad; el resto usa Elo general)
SUP_TORNEO = [("aus_open", "Hard"), ("french_open", "Clay"), ("wimbledon", "Grass"), ("us_open", "Hard"),
              ("cincinnati", "Hard"), ("dubai", "Hard"), ("hamburg", "Clay"), ("indian_wells", "Hard"),
              ("italian", "Clay"), ("madrid", "Clay"), ("miami", "Hard"), ("monte_carlo", "Clay"),
              ("munich", "Clay"), ("paris", "Hard"), ("qatar", "Hard"), ("shanghai", "Hard"),
              ("canadian", "Hard"), ("wuhan", "Hard"), ("beijing", "Hard"), ("china_open", "Hard"),
              ("atp_finals", "Hard"), ("wta_finals", "Hard")]


def leer_json(nombre, defecto):
    try:
        with open(os.path.join(DATA, nombre), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return defecto


def guardar_json(nombre, obj):
    with open(os.path.join(DATA, nombre), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode("ascii").lower()
    return re.findall(r"[a-z0-9]+", s)


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / float(n)
    d = 1 + z * z / n
    c = p + z * z / (2.0 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4.0 * n * n))
    return [round((c - m) / d, 4), round((c + m) / d, 4)]


def parse_iso(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def a_int(dt):
    return int(dt.strftime("%Y%m%d"))


# ---------------------------------------------------------------- datos historicos
def descargar(tour, anio):
    url = RAW % (tour, tour, anio)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "sports-edge"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        print("Aviso: %s %d no disponible (HTTP %s)" % (tour.upper(), anio, e.code))
    except Exception as e:
        print("Aviso: %s %d no se pudo leer (%s)" % (tour.upper(), anio, e))
    return None


def rank(x):
    try:
        v = int(float(x))
        return v if v > 0 else None
    except Exception:
        return None


def parsear(texto, tour):
    out = []
    for f in csv.DictReader(io.StringIO(texto)):
        try:
            fecha = int(f.get("tourney_date") or 0)
        except Exception:
            continue
        wid = (f.get("winner_id") or "").strip()
        lid = (f.get("loser_id") or "").strip()
        wn = (f.get("winner_name") or "").strip()
        ln = (f.get("loser_name") or "").strip()
        if not (fecha and wid and lid and wn and ln):
            continue
        sc = (f.get("score") or "").strip()
        if "W/O" in sc.upper() or "DEF" in sc.upper():
            continue
        try:
            mn = int(f.get("match_num") or 0)
        except Exception:
            mn = 0
        out.append({"d": fecha, "o": (ORDEN.get((f.get("round") or "").strip(), 3), mn), "tour": tour,
                    "sup": (f.get("surface") or "").strip() or None,
                    "torneo": (f.get("tourney_name") or "").strip(),
                    "w": tour + ":" + wid, "l": tour + ":" + lid, "wn": wn, "ln": ln, "sc": sc,
                    "wr": rank(f.get("winner_rank")), "lr": rank(f.get("loser_rank"))})
    return out


# ---------------------------------------------------------------- modelo Elo
class Elo(object):
    def __init__(self):
        self.g = {}
        self.s = {}
        self.nombres = {}

    def n(self, i):
        return self.g.get(i, [1500.0, 0])[1]

    def rg(self, i):
        return self.g.get(i, [1500.0, 0])[0]

    def rating(self, i, sup):
        if sup:
            rs = self.s.get((i, sup))
            if rs and rs[1] >= MIN_SUP:
                return PESO_SUP * rs[0] + (1 - PESO_SUP) * self.rg(i), True
        return self.rg(i), False

    def prob(self, a, b, sup):
        ra, ua = self.rating(a, sup)
        rb, ub = self.rating(b, sup)
        if ua != ub:   # solo se usa la superficie si los dos tienen suficientes partidos
            ra, rb = self.rg(a), self.rg(b)
        return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))

    @staticmethod
    def _mover(tabla, kw, kl, w, l):
        rw = tabla.setdefault(kw, [1500.0, 0])
        rl = tabla.setdefault(kl, [1500.0, 0])
        sorpresa = 1.0 - 1.0 / (1.0 + 10 ** ((rl[0] - rw[0]) / 400.0))
        kw_ = 250.0 / ((rw[1] + 5) ** 0.4)
        kl_ = 250.0 / ((rl[1] + 5) ** 0.4)
        rw[0] += kw_ * sorpresa
        rl[0] -= kl_ * sorpresa
        rw[1] += 1
        rl[1] += 1

    def actualizar(self, w, l, sup, wn, ln, fecha):
        self._mover(self.g, w, l, w, l)
        if sup:
            self._mover(self.s, (w, sup), (l, sup), w, l)
        self.nombres[w] = (wn, fecha)
        self.nombres[l] = (ln, fecha)


def correr(rows, elo, eval_desde):
    ev = []
    for r in sorted(rows, key=lambda x: (x["d"], x["o"])):
        sup = r["sup"] if r["sup"] in SUPERFICIES else None
        if r["d"] >= eval_desde and elo.n(r["w"]) >= MIN_N and elo.n(r["l"]) >= MIN_N:
            ev.append((r, sup, elo.prob(r["w"], r["l"], sup)))
        elo.actualizar(r["w"], r["l"], sup, r["wn"], r["ln"], r["d"])
    return ev


# ---------------------------------------------------------------- backtest
def resumen(ev):
    n = len(ev)
    if n == 0:
        return None
    hit = sum(1 for _, _, p in ev if p > 0.5)
    brier = sum((1 - p) ** 2 for _, _, p in ev) / n
    nr = hr = kr = 0
    for r, _, p in ev:
        if r["wr"] and r["lr"] and r["wr"] != r["lr"]:
            nr += 1
            hr += 1 if p > 0.5 else 0
            kr += 1 if r["wr"] < r["lr"] else 0
    return {"n": n, "aciertos": hit, "acierto": round(hit / float(n), 4), "ic": wilson(hit, n),
            "brier": round(brier, 4), "brier_azar": 0.25, "n_ranking": nr,
            "acierto_mismo_grupo": round(hr / float(nr), 4) if nr else None,
            "mejor_ranking": round(kr / float(nr), 4) if nr else None}


def tramos(ev):
    out = []
    for th in (0.60, 0.70, 0.80):
        sub = [p for _, _, p in ev if max(p, 1 - p) >= th]
        if not sub:
            out.append({"min": th, "n": 0, "conf": None, "acierto": None, "ic": None})
            continue
        h = sum(1 for p in sub if p > 0.5)
        conf = sum(max(p, 1 - p) for p in sub) / len(sub)
        out.append({"min": th, "n": len(sub), "conf": round(conf, 4),
                    "acierto": round(h / float(len(sub)), 4), "ic": wilson(h, len(sub))})
    return out


def calibracion(ev):
    out = []
    for b in range(5):
        lo = 0.5 + 0.1 * b
        hi = lo + 0.1
        sub = [p for _, _, p in ev if (max(p, 1 - p) >= lo and (max(p, 1 - p) < hi or b == 4))]
        if not sub:
            out.append({"desde": int(round(lo * 100)), "hasta": int(round(hi * 100)), "n": 0,
                        "prometido": None, "real": None})
            continue
        h = sum(1 for p in sub if p > 0.5)
        out.append({"desde": int(round(lo * 100)), "hasta": int(round(hi * 100)), "n": len(sub),
                    "prometido": round(sum(max(p, 1 - p) for p in sub) / len(sub), 4),
                    "real": round(h / float(len(sub)), 4)})
    return out


def agrupar(ev, f):
    g = {}
    for item in ev:
        k = f(item)
        if k:
            g.setdefault(k, []).append(item)
    return {k: resumen(v) for k, v in g.items()}


def ejemplos(ev):
    out = []
    for r, sup, p in reversed(ev[-25:]):
        out.append({"fecha": r["d"], "tour": r["tour"].upper(), "torneo": r["torneo"], "sup": sup,
                    "ganador": r["wn"], "perdedor": r["ln"], "marcador": r["sc"],
                    "fav": r["wn"] if p > 0.5 else r["ln"], "pp": round(max(p, 1 - p), 4), "ok": p > 0.5})
    return out


# ---------------------------------------------------------------- nombres
def indexar(elo):
    full = {}
    corto = {}
    for pid, (nom, _) in elo.nombres.items():
        toks = norm(nom)
        if not toks:
            continue
        tour = pid.split(":")[0]
        full.setdefault((tour, " ".join(toks)), []).append(pid)
        corto.setdefault((tour, toks[-1], toks[0][0]), []).append(pid)
    return full, corto


def encontrar(idx, tour, nombre):
    full, corto = idx
    toks = norm(nombre)
    if not toks:
        return None
    c = full.get((tour, " ".join(toks)), [])
    if len(c) == 1:
        return c[0]
    if len(c) > 1:
        return None
    c = corto.get((tour, toks[-1], toks[0][0]), [])
    return c[0] if len(c) == 1 else None


# ---------------------------------------------------------------- cuotas y partidos proximos
def pedir(url):
    req = urllib.request.Request(url, headers={"User-Agent": "sports-edge"})
    with urllib.request.urlopen(req, timeout=30) as r:
        rest = r.headers.get("x-requests-remaining")
        return json.load(r), rest


def superficie_torneo(clave):
    for sub, sup in SUP_TORNEO:
        if sub in clave:
            return sup
    return None


def procesar_evento(ev):
    mejor = {}
    cons = {"1": [], "2": []}
    casas = 0
    for b in ev.get("bookmakers", []):
        for m in b.get("markets", []):
            if m.get("key") != "h2h":
                continue
            pr = {}
            for o in m.get("outcomes", []):
                price = o.get("price")
                nm = o.get("name")
                if not isinstance(price, (int, float)) or price <= 1:
                    continue
                if nm == ev.get("home_team"):
                    k = "1"
                elif nm == ev.get("away_team"):
                    k = "2"
                else:
                    continue
                pr[k] = price
                if k not in mejor or price > mejor[k]["c"]:
                    mejor[k] = {"c": round(price, 2), "casa": b.get("title") or b.get("key")}
            if len(pr) == 2:
                casas += 1
                s = sum(1.0 / v for v in pr.values())
                for k, v in pr.items():
                    cons[k].append((1.0 / v) / s)
    if len(mejor) < 2 or casas == 0:
        return None
    return mejor, {k: round(sum(v) / len(v), 4) for k, v in cons.items()}, casas


VALOR_VERIFICADO = False


def evaluar(p1, p2, mejor, mercado):
    probs = {"1": p1, "2": p2}
    ev = {}
    valor = []
    for k in ("1", "2"):
        ev[k] = round(probs[k] * mejor[k]["c"] - 1, 4)
        # VALOR desactivado: aun no se ha comprobado con cuotas historicas reales que gane dinero.
        if VALOR_VERIFICADO and ev[k] >= UMBRAL_VALOR and probs[k] >= PROB_MIN and probs[k] > mercado[k]:
            valor.append(k)
    return ev, valor


def captar(elo, idx, lista, ahora, stamp):
    """Devuelve (sin_datos, torneos_activos, ok_consulta)."""
    if not LLAMAR:
        return [], None, False
    if not KEY:
        print("Aviso: falta ODDS_API_KEY. No se consultan partidos proximos.")
        return [], None, False
    try:
        sports, _ = pedir(ODDS + "/?apiKey=" + KEY)
    except Exception as e:
        print("Aviso: no se pudo leer la lista de torneos (%s)" % e)
        return [], None, False
    activos = [s for s in sports if isinstance(s, dict) and s.get("group") == "Tennis"
               and str(s.get("key", "")).startswith(("tennis_atp", "tennis_wta"))
               and s.get("active") and not s.get("has_outrights")]
    print("Torneos de tenis activos con cuotas: %d" % len(activos))
    por_id = {p["id"]: p for p in lista}
    sin_datos = []
    nombres = []
    restantes = None
    nuevas = 0
    for s in activos[:MAX_TORNEOS]:
        if restantes is not None and restantes < MIN_CREDITOS:
            print("Aviso: quedan %d creditos. Se detienen las consultas." % restantes)
            break
        clave = s["key"]
        tour = "atp" if clave.startswith("tennis_atp") else "wta"
        sup = superficie_torneo(clave)
        try:
            datos, rest = pedir("%s/%s/odds?apiKey=%s&regions=eu&markets=h2h&oddsFormat=decimal&dateFormat=iso"
                                % (ODDS, clave, KEY))
            if rest is not None:
                try:
                    restantes = int(float(rest))
                except Exception:
                    pass
        except Exception as e:
            print("Aviso: %s -> %s" % (clave, e))
            continue
        nombres.append(s.get("title") or clave)
        for ev in datos if isinstance(datos, list) else []:
            try:
                fecha = parse_iso(ev["commence_time"])
                n1, n2, eid = ev["home_team"], ev["away_team"], ev["id"]
            except Exception:
                continue
            if fecha <= ahora or fecha > ahora + timedelta(days=7):
                continue
            i1, i2 = encontrar(idx, tour, n1), encontrar(idx, tour, n2)
            if not i1 or not i2 or i1 == i2:
                sin_datos.append("%s - %s (jugador no identificado)" % (n1, n2))
                continue
            if elo.n(i1) < MIN_N or elo.n(i2) < MIN_N:
                sin_datos.append("%s - %s (pocos partidos previos)" % (n1, n2))
                continue
            res = procesar_evento(ev)
            p = por_id.get(eid)
            if p is None:
                p1 = round(elo.prob(i1, i2, sup), 4)
                p = {"id": eid, "torneo": s.get("title") or clave, "tour": tour.upper(), "sup": sup,
                     "fecha": ev["commence_time"], "j1": n1, "j2": n2, "id1": i1, "id2": i2,
                     "p1": p1, "p2": round(1 - p1, 4), "n1": elo.n(i1), "n2": elo.n(i2),
                     "creada": stamp, "resultado": None, "marcador": None}
                lista.append(p)
                por_id[eid] = p
                nuevas += 1
            if res is not None and p.get("resultado") is None:
                mejor, mercado, casas = res
                evl, valor = evaluar(p["p1"], p["p2"], mejor, mercado)
                p["cuota"] = {"mejor": mejor, "mercado": mercado, "casas": casas, "ev": evl,
                              "valor": valor, "actualizado": stamp}
                if "cuota_guardada" not in p:   # la primera cuota se guarda y no se cambia
                    p["cuota_guardada"] = {"fecha": stamp, "valor": valor, "1": mejor["1"]["c"], "2": mejor["2"]["c"]}
    print("Partidos nuevos guardados: %d. Sin datos suficientes: %d. Creditos restantes: %s" %
          (nuevas, len(sin_datos), restantes if restantes is not None else "?"))
    return sin_datos, nombres, True


def liquidar(lista, rows, ahora):
    idx = {}
    for r in rows:
        idx.setdefault(frozenset((r["w"], r["l"])), []).append(r)
    n = 0
    for p in lista:
        if p.get("resultado") is not None:
            continue
        f = parse_iso(p["fecha"])
        if f > ahora:
            continue
        lo = a_int(f - timedelta(days=VENTANA_DIAS))
        hi = a_int(f + timedelta(days=1))
        c = [r for r in idx.get(frozenset((p["id1"], p["id2"])), []) if lo <= r["d"] <= hi]
        if c:
            r = max(c, key=lambda x: x["d"])
            p["resultado"] = "1" if r["w"] == p["id1"] else "2"
            p["marcador"] = r["sc"]
            n += 1
    return n


def stats_directo(lista):
    res = [p for p in lista if p.get("resultado")]
    n = len(res)
    hit = 0
    br = 0.0
    for p in res:
        pw = p["p1"] if p["resultado"] == "1" else p["p2"]
        hit += 1 if pw > 0.5 else 0
        br += (1 - pw) ** 2
    ap = gan = 0
    ben = 0.0
    for p in res:
        cg = p.get("cuota_guardada")
        if not cg:
            continue
        for k in cg.get("valor", []):
            c = cg.get(k)
            if not c:
                continue
            ap += 1
            if p["resultado"] == k:
                gan += 1
                ben += c - 1
            else:
                ben -= 1
    return {"total": len(lista), "resueltas": n, "acierto": round(hit / float(n), 4) if n else None,
            "brier": round(br / n, 4) if n else None, "apuestas": ap,
            "roi": round(ben / ap, 4) if ap else None}


def main():
    os.makedirs(DATA, exist_ok=True)
    ahora = datetime.now(timezone.utc)
    stamp = ahora.strftime("%Y-%m-%d %H:%M UTC")
    rows = []
    fuentes = {}
    for tour in ("atp", "wta"):
        textos, clave = tenis_fuente.cargar(tour, ANIOS)
        for txt in textos:
            rows.extend(parsear(txt, tour))
        if clave:
            fuentes[tour.upper()] = tenis_fuente.FUENTES_INFO[clave]
    print("Partidos de tenis cargados: %d" % len(rows))
    if len(rows) < 1000:
        print("ERROR: datos insuficientes. No se cambia nada.")
        sys.exit(1)

    elo = Elo()
    ev = correr(rows, elo, EVAL_DESDE)
    if not ev:
        print("ERROR: no hay partidos para evaluar. No se cambia nada.")
        sys.exit(1)
    ultima = max(r["d"] for r in rows)
    ultima_dt = datetime.strptime(str(ultima), "%Y%m%d").replace(tzinfo=timezone.utc)
    dias = (ahora - ultima_dt).days
    tot = resumen(ev)
    guardar_json("tenis_backtest.json", {
        "actualizado": stamp, "desde": EVAL_DESDE, "datos_hasta": ultima, "dias_desde_datos": dias,
        "fuentes": fuentes, "total": tot, "tramos": tramos(ev), "calibracion": calibracion(ev),
        "superficies": agrupar(ev, lambda x: x[1]),
        "circuitos": agrupar(ev, lambda x: x[0]["tour"].upper()),
        "ejemplos": ejemplos(ev)})
    print("OK backtest tenis: %d partidos, acierto %.1f%%, Brier %.3f (azar 0.250). Ultimo dato: %s (hace %d dias)" %
          (tot["n"], tot["acierto"] * 100, tot["brier"], ultima, dias))

    hist = leer_json("tenis_historial.json", {"predicciones": []})
    lista = hist.get("predicciones", [])
    idx = indexar(elo)
    if dias > 60:
        print("Aviso: los resultados llevan %d dias sin actualizarse. No se publican predicciones nuevas." % dias)
        sin_datos, torneos, consultado = [], None, False
    else:
        sin_datos, torneos, consultado = captar(elo, idx, lista, ahora, stamp)
    liq = liquidar(lista, rows, ahora)
    if liq:
        print("Resultados de tenis anotados: %d" % liq)
    hist["predicciones"] = lista
    hist["actualizado"] = stamp
    guardar_json("tenis_historial.json", hist)

    previo = leer_json("tenis.json", {})
    visibles = []
    for p in lista:
        if p.get("resultado") is not None:
            continue
        try:
            if parse_iso(p["fecha"]) < ahora - timedelta(hours=4):
                continue
        except Exception:
            continue
        visibles.append(p)
    visibles.sort(key=lambda x: x["fecha"])
    guardar_json("tenis.json", {
        "actualizado": stamp, "datos_hasta": ultima, "dias_desde_datos": dias, "fuentes": fuentes,
        "torneos": torneos if consultado else previo.get("torneos", []),
        "sin_datos": sin_datos if consultado else previo.get("sin_datos", []),
        "predicciones": visibles, "directo": stats_directo(lista)})
    print("Tenis: %d partidos proximos publicados" % len(visibles))


if __name__ == "__main__":
    main()
