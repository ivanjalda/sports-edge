# -*- coding: utf-8 -*-
"""Sports Edge - Motor comun para deportes de equipo sin empate (solo libreria estandar).
Baloncesto: NBA, Euroliga, Eurocup, NCAA masculina, WNBA. Hockey: NHL, NCAA masculina.
Futbol americano: NFL y NCAA (FBS). Prediccion: motor propio (Elo + descanso + forma) de motor_equipos.py.
Para anadir otra liga basta con anadirla a LIGAS.

Datos de resultados y calendario: marcadores publicos de ESPN y API oficial de Euroleague.
Cuotas: The Odds API (opcional; sin cuotas se publican igualmente las probabilidades).
Modelo: Elo con ventaja de campo, margen de victoria y regresion a la media entre temporadas.
Los parametros se fijan de antemano (valores publicados por FiveThirtyEight) y no se ajustan
mirando los resultados."""
import json
import math
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import motor_equipos

DATA = "data"
KEY = os.environ.get("ODDS_API_KEY", "").strip()
LLAMAR = os.environ.get("ODDS_FETCH", "true").strip().lower() == "true"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/%s/scoreboard?%s%s"
# Formas de pedir los datos a ESPN, de la mas rapida a la mas lenta. Se usa la primera que funcione.
FORMAS = [("rango", "dates={a}-{b}&limit=1000"), ("rango", "dates={a}-{b}&limit=300"), ("rango", "dates={a}-{b}"),
          ("dia", "dates={a}&limit=300"), ("dia", "dates={a}")]
_forma = {}
ODDS = "https://api.the-odds-api.com/v4/sports"
UA = "Mozilla/5.0 (compatible; sports-edge/1.0; +https://ivanjalda.github.io/sports-edge/)"

MEDIA = 1505.0
UMBRAL_VALOR = 0.05
PROB_MIN = 0.10
DIF_MAX_MERCADO = 0.15   # si el modelo se aleja mas de 15 puntos del mercado, no se marca VALOR
VENTAJA_MIN_LIGA = 0.03  # la liga debe superar en 3 puntos a "siempre local" en el backtest
MIN_CREDITOS = 25
HORAS_PRED = 48        # se guardan predicciones de partidos que empiezan en las proximas 48 h

# fuente: "espn" (marcadores ESPN) o "euro" (API oficial de Euroleague Basketball)
# odds: clave de The Odds API, o None para no gastar creditos en esa liga
# min_eq: partidos minimos de un equipo para entrar (descarta partidos de exhibicion)
# max_dias: dias sin resultados nuevos a partir de los cuales no se guardan predicciones
BALONCESTO = {"k": 20.0, "hca": 100.0, "revertir": 0.75, "mov": "nba"}
HOCKEY = {"k": 6.0, "hca": 50.0, "revertir": 0.70, "mov": "nhl"}
AMERICANO = {"k": 20.0, "hca": 48.0, "revertir": 0.67, "mov": "nfl"}
LIGAS = {
    "nba": dict(BALONCESTO, nombre="NBA", fuente="espn", ruta="basketball/nba", extra="",
                odds="basketball_nba", inicio="20231001", eval="20241001", min_eq=20, max_dias=10,
                meses=(10, 11, 12, 1, 2, 3, 4, 5, 6)),
    "euroliga": dict(BALONCESTO, nombre="Euroliga", fuente="euro", comp="E",
                     odds="basketball_euroleague", inicio="2022", eval="20241001", min_eq=5, max_dias=21),
    "eurocup": dict(BALONCESTO, nombre="Eurocup", fuente="euro", comp="U",
                    odds=None, inicio="2022", eval="20241001", min_eq=5, max_dias=21),
    "ncaab": dict(BALONCESTO, nombre="NCAA", fuente="espn", ruta="basketball/mens-college-basketball",
                  extra="&groups=50", odds=None, inicio="20231101", eval="20241101", min_eq=10, max_dias=10,
                  meses=(11, 12, 1, 2, 3, 4)),
    "wnba": dict(BALONCESTO, nombre="WNBA", fuente="espn", ruta="basketball/wnba", extra="",
                 odds=None, inicio="20230501", eval="20240501", min_eq=20, max_dias=10,
                 meses=(5, 6, 7, 8, 9, 10)),
    "nhl": dict(HOCKEY, nombre="NHL", fuente="espn", ruta="hockey/nhl", extra="",
                odds="icehockey_nhl", inicio="20231001", eval="20241001", min_eq=20, max_dias=10,
                meses=(10, 11, 12, 1, 2, 3, 4, 5, 6)),
    "nfl": dict(AMERICANO, nombre="NFL", fuente="espn", ruta="football/nfl", extra="",
                odds="americanfootball_nfl", inicio="20230901", eval="20240901", min_eq=10, max_dias=12,
                meses=(9, 10, 11, 12, 1, 2)),
    "ncaaf": dict(AMERICANO, nombre="NCAA", fuente="espn", ruta="football/college-football", extra="&groups=80",
                  odds=None, inicio="20230825", eval="20240825", min_eq=8, max_dias=12,
                  meses=(8, 9, 10, 11, 12, 1)),
    "ncaah": dict(HOCKEY, nombre="NCAA", fuente="espn", ruta="hockey/mens-college-hockey", extra="",
                  odds=None, inicio="20231001", eval="20241001", min_eq=10, max_dias=12,
                  meses=(10, 11, 12, 1, 2, 3, 4)),
}
EURO = "https://api-live.euroleague.net/v2/competitions/%s/seasons/%s%d/games"
FASE_EURO = {"RS": 2, "PI": 5, "PO": 3, "FF": 3}


# ---------------------------------------------------------------- utilidades
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
    s = str(s).strip().replace("Z", "")
    if len(s) >= 19:
        return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    return datetime.strptime(s[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def get_json(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace")), r.headers


# ---------------------------------------------------------------- descarga de resultados
def leer_eventos(datos):
    """Convierte la respuesta de ESPN en una lista de partidos."""
    out = []
    for ev in (datos or {}).get("events", []) or []:
        try:
            comp = (ev.get("competitions") or [])[0]
            eq = {c.get("homeAway"): c for c in comp.get("competitors", [])}
            h, a = eq.get("home"), eq.get("away")
            if not h or not a:
                continue
            est = ((ev.get("status") or {}).get("type") or {})
            tipo = (ev.get("season") or {}).get("type")
            out.append({
                "id": str(ev.get("id")),
                "fecha": iso(parse_iso(ev.get("date"))),
                "temporada": (ev.get("season") or {}).get("year"),
                "tipo": tipo,
                "terminado": bool(est.get("completed")),
                "neutral": bool(comp.get("neutralSite")),
                "local": (h.get("team") or {}).get("displayName"),
                "visitante": (a.get("team") or {}).get("displayName"),
                "pl": int(float(h.get("score"))) if h.get("score") not in (None, "") else None,
                "pv": int(float(a.get("score"))) if a.get("score") not in (None, "") else None,
            })
        except Exception:
            continue
    return out


def _pedir(ruta, forma, d1, d2, extra, meses):
    tipo, patron = FORMAS[forma]
    if tipo == "rango":
        q = patron.format(a=d1.strftime("%Y%m%d"), b=d2.strftime("%Y%m%d"))
        datos, _ = get_json(ESPN % (ruta, q, extra), timeout=20)
        return leer_eventos(datos)
    out = []
    d = d1
    while d <= d2:
        if not meses or d.month in meses:
            datos, _ = get_json(ESPN % (ruta, patron.format(a=d.strftime("%Y%m%d")), extra), timeout=20)
            out.extend(leer_eventos(datos))
            time.sleep(0.1)
        d += timedelta(days=1)
    return out


def pedir_bloque(ruta, d1, d2, extra="", meses=None):
    """La primera vez prueba las distintas formas hasta encontrar una que ESPN acepte."""
    if ruta in _forma:
        return _pedir(ruta, _forma[ruta], d1, d2, extra, meses)
    ultimo = None
    for i in range(len(FORMAS)):
        try:
            res = _pedir(ruta, i, d1, d2, extra, meses)
            _forma[ruta] = i
            print("Forma de lectura de ESPN que funciona: %s (%s)" % (FORMAS[i][0], FORMAS[i][1]))
            return res
        except Exception as e:
            ultimo = e
            print("  forma %d no aceptada (%s)" % (i + 1, e))
    raise ultimo


def leer_euro(datos, anio):
    """Convierte la respuesta de la API oficial de Euroleague en una lista de partidos."""
    out = []
    for g in (datos or {}).get("data", []) or []:
        try:
            fase = ((g.get("phaseType") or {}).get("code") or "").upper()
            fecha = g.get("utcDate") or g.get("date")
            loc, vis = g.get("local") or {}, g.get("road") or {}
            sl, sv = loc.get("score"), vis.get("score")
            out.append({
                "id": str(g.get("identifier") or g.get("id")),
                "fecha": iso(parse_iso(fecha)),
                "temporada": anio + 1,
                "tipo": FASE_EURO.get(fase, 2),
                "terminado": bool(g.get("played")),
                "neutral": fase == "FF",
                "local": (loc.get("club") or {}).get("name"),
                "visitante": (vis.get("club") or {}).get("name"),
                "pl": int(sl) if sl not in (None, "") else None,
                "pv": int(sv) if sv not in (None, "") else None,
            })
        except Exception:
            continue
    return out


def descargar_euro(cfg, primera, ahora):
    """Temporadas desde cfg['inicio'] la primera vez; despues solo la temporada en curso."""
    actual = ahora.year if ahora.month >= 8 else ahora.year - 1
    anios = range(int(cfg["inicio"]), actual + 1) if primera else [actual]
    juegos, errores = [], 0
    for a in anios:
        try:
            datos, _ = get_json(EURO % (cfg["comp"], cfg["comp"], a), timeout=90)
            lista = leer_euro(datos, a)
            print("Temporada %d-%s: %d partidos" % (a, str(a + 1)[2:], len(lista)))
            juegos.extend(lista)
        except Exception as e:
            errores += 1
            print("Aviso: temporada %d no disponible (%s)" % (a, e))
        time.sleep(0.3)
    return juegos, errores


def descargar(ruta, desde, hasta, extra="", meses=None):
    """Descarga partidos entre dos fechas en bloques de 7 dias.
    Seguridad: si fallan 3 bloques seguidos o se superan 5 minutos, se para y sigue con lo que tenga."""
    juegos = {}
    errores = 0
    seguidos = 0
    llegado = None
    inicio = time.time()
    bloques = 0
    d = desde
    while d <= hasta:
        if time.time() - inicio > 300:
            print("Aviso: descarga cortada por tiempo (5 min). Se continua en la proxima ejecucion.")
            break
        fin = min(d + timedelta(days=6), hasta)
        try:
            lista = pedir_bloque(ruta, d, fin, extra, meses)
            for g in lista:
                juegos[g["id"]] = g
            seguidos = 0
            llegado = fin
        except Exception as e:
            errores += 1
            seguidos += 1
            if errores == 1:
                print("Aviso: fallo al leer %s - %s (%s)" % (d.strftime("%Y-%m-%d"), fin.strftime("%Y-%m-%d"), e))
            if seguidos >= 3:
                print("Aviso: 3 fallos seguidos. Se para la descarga de esta liga.")
                break
        bloques += 1
        if bloques % 26 == 0:
            print("  ... leido hasta %s (%d partidos, %d s)" % (fin.strftime("%Y-%m-%d"), len(juegos),
                                                              int(time.time() - inicio)))
        d = fin + timedelta(days=1)
        time.sleep(0.2)
    return list(juegos.values()), errores, llegado


# ---------------------------------------------------------------- modelo Elo
def mult_mov(tipo, mov, dr):
    """Multiplicador por margen de victoria (dr = Elo del ganador - Elo del perdedor)."""
    mov = max(1, abs(mov))
    if tipo == "nba":
        return ((mov + 3) ** 0.8) / (7.5 + 0.006 * dr)
    return (0.6686 * math.log(mov) + 0.8048) * (2.05 / (dr * 0.001 + 2.05))


class Elo(object):
    def __init__(self, cfg):
        self.cfg = cfg
        self.r = {}
        self.temp = None

    def get(self, e):
        return self.r.get(e, MEDIA)

    def nueva_temporada(self, t):
        if self.temp is not None and t != self.temp:
            a = self.cfg["revertir"]
            for e in self.r:
                self.r[e] = a * self.r[e] + (1 - a) * MEDIA
        self.temp = t

    def prob_local(self, l, v, neutral):
        dif = self.get(l) - self.get(v) + (0 if neutral else self.cfg["hca"])
        return 1.0 / (1.0 + 10 ** (-dif / 400.0))

    def actualizar(self, g):
        p = self.prob_local(g["local"], g["visitante"], g["neutral"])
        gana_l = g["pl"] > g["pv"]
        hca = 0 if g["neutral"] else self.cfg["hca"]
        dif = self.get(g["local"]) + hca - self.get(g["visitante"])
        dr = dif if gana_l else -dif
        k = self.cfg["k"] * mult_mov(self.cfg["mov"], g["pl"] - g["pv"], dr)
        cambio = k * ((1.0 if gana_l else 0.0) - p)
        self.r[g["local"]] = self.get(g["local"]) + cambio
        self.r[g["visitante"]] = self.get(g["visitante"]) - cambio


# ---------------------------------------------------------------- estadisticas
def resumen(items):
    """items: lista de (prob_local, gana_local)."""
    n = len(items)
    if n == 0:
        return None
    hit = sum(1 for p, w in items if (p > 0.5) == w)
    brier = sum((p - (1.0 if w else 0.0)) ** 2 for p, w in items) / n
    return {"n": n, "aciertos": hit, "acierto": round(hit / float(n), 4), "ic": wilson(hit, n),
            "brier": round(brier, 4)}


def tramos(items):
    out = []
    for th in (0.60, 0.70, 0.80):
        sub = [(p, w) for p, w in items if max(p, 1 - p) >= th]
        if not sub:
            out.append({"min": th, "n": 0, "conf": None, "acierto": None, "ic": None})
            continue
        h = sum(1 for p, w in sub if (p > 0.5) == w)
        out.append({"min": th, "n": len(sub), "conf": round(sum(max(p, 1 - p) for p, _ in sub) / len(sub), 4),
                    "acierto": round(h / float(len(sub)), 4), "ic": wilson(h, len(sub))})
    return out


def calibracion(items):
    out = []
    for b in range(5):
        lo = 0.5 + 0.1 * b
        hi = lo + 0.1
        sub = [(p, w) for p, w in items if max(p, 1 - p) >= lo and (max(p, 1 - p) < hi or b == 4)]
        if not sub:
            out.append({"desde": int(round(lo * 100)), "hasta": int(round(hi * 100)), "n": 0,
                        "prometido": None, "real": None})
            continue
        h = sum(1 for p, w in sub if (p > 0.5) == w)
        out.append({"desde": int(round(lo * 100)), "hasta": int(round(hi * 100)), "n": len(sub),
                    "prometido": round(sum(max(p, 1 - p) for p, _ in sub) / len(sub), 4),
                    "real": round(h / float(len(sub)), 4)})
    return out


def correr(juegos, cfg):
    """Recorre los partidos en orden. Devuelve (elo, evaluados, balances)."""
    elo = Elo(cfg)
    ev = []
    bal = {}
    temp_bal = None
    for g in juegos:
        elo.nueva_temporada(g["temporada"])
        if g["temporada"] != temp_bal:
            bal = {}
            temp_bal = g["temporada"]
        if g["fecha"][:10].replace("-", "") >= cfg["eval"]:
            p = elo.prob_local(g["local"], g["visitante"], g["neutral"])
            bl, bv = bal.get(g["local"], [0, 0]), bal.get(g["visitante"], [0, 0])
            ev.append({"g": g, "p": p, "w": g["pl"] > g["pv"], "bl": list(bl), "bv": list(bv)})
        elo.actualizar(g)
        gl = g["pl"] > g["pv"]
        bal.setdefault(g["local"], [0, 0])[0 if gl else 1] += 1
        bal.setdefault(g["visitante"], [0, 0])[1 if gl else 0] += 1
    return elo, ev, bal


def backtest(ev, cfg, stamp, hasta):
    items = [(e["p"], e["w"]) for e in ev]
    tot = resumen(items)
    # Comparacion 1: elegir siempre al local
    loc = sum(1 for e in ev if e["w"])
    # Comparacion 2: elegir al de mejor balance de la temporada (min. 5 partidos cada uno, distinto balance)
    nb = hb = ob = 0
    for e in ev:
        bl, bv = e["bl"], e["bv"]
        if sum(bl) < 5 or sum(bv) < 5:
            continue
        pl, pv = bl[0] / float(sum(bl)), bv[0] / float(sum(bv))
        if pl == pv:
            continue
        nb += 1
        hb += 1 if (pl > pv) == e["w"] else 0
        ob += 1 if (e["p"] > 0.5) == e["w"] else 0
    por_temp = {}
    for e in ev:
        por_temp.setdefault(str(e["g"]["temporada"]), []).append((e["p"], e["w"]))
    fases = {}
    for e in ev:
        fases.setdefault("playoff" if e["g"]["tipo"] == 3 else "regular", []).append((e["p"], e["w"]))
    elige = {"local": [], "visitante": []}
    for e in ev:
        elige["local" if e["p"] > 0.5 else "visitante"].append((e["p"], e["w"]))
    ejemplos = []
    for e in reversed(ev[-25:]):
        g = e["g"]
        fav_l = e["p"] > 0.5
        ejemplos.append({"fecha": g["fecha"], "local": g["local"], "visitante": g["visitante"],
                         "marcador": "%d-%d" % (g["pl"], g["pv"]),
                         "fav": g["local"] if fav_l else g["visitante"],
                         "pp": round(max(e["p"], 1 - e["p"]), 4), "ok": fav_l == e["w"]})
    return {"actualizado": stamp, "liga": cfg["nombre"], "desde": cfg["eval"], "datos_hasta": hasta,
            "total": tot,
            "base_local": {"n": len(ev), "acierto": round(loc / float(len(ev)), 4) if ev else None},
            "base_balance": {"n": nb, "acierto": round(hb / float(nb), 4) if nb else None,
                             "nuestro": round(ob / float(nb), 4) if nb else None},
            "tramos": tramos(items), "calibracion": calibracion(items),
            "temporadas": {k: resumen(v) for k, v in sorted(por_temp.items())},
            "fases": {k: resumen(v) for k, v in fases.items()},
            "elige": {k: resumen(v) for k, v in elige.items()},
            "ejemplos": ejemplos}


# ---------------------------------------------------------------- cuotas
def nombre_clave(nombre):
    t = norm(nombre)
    return " ".join(t), (t[-1] if t else "")


def cuotas_liga(cfg, restantes):
    """Pide las cuotas de la liga. Devuelve (lista de eventos, creditos restantes)."""
    url = "%s/%s/odds?apiKey=%s&regions=eu&markets=h2h&oddsFormat=decimal&dateFormat=iso" % (ODDS, cfg["odds"], KEY)
    datos, h = get_json(url, timeout=30)
    rest = h.get("x-requests-remaining")
    try:
        restantes = int(float(rest))
    except Exception:
        pass
    return (datos if isinstance(datos, list) else []), restantes


def emparejar(p, eventos):
    fl, ul = nombre_clave(p["local"])
    fv, uv = nombre_clave(p["visitante"])
    ini = parse_iso(p["fecha"])
    for ev in eventos:
        try:
            if abs((parse_iso(ev["commence_time"]) - ini).total_seconds()) > 6 * 3600:
                continue
        except Exception:
            continue
        hl, hu = nombre_clave(ev.get("home_team"))
        al, au = nombre_clave(ev.get("away_team"))
        if (hl == fl or hu == ul) and (al == fv or au == uv):
            return ev, False
        if (hl == fv or hu == uv) and (al == fl or au == ul):
            return ev, True
    return None, False


def procesar_cuotas(ev, invertido):
    """Mejor cuota y probabilidad de mercado para local ('L') y visitante ('V')."""
    nom = {"L": ev.get("away_team") if invertido else ev.get("home_team"),
           "V": ev.get("home_team") if invertido else ev.get("away_team")}
    mejor = {}
    cons = {"L": [], "V": []}
    casas = 0
    for b in ev.get("bookmakers", []):
        for m in b.get("markets", []):
            if m.get("key") != "h2h":
                continue
            pr = {}
            for o in m.get("outcomes", []):
                price = o.get("price")
                if not isinstance(price, (int, float)) or price <= 1:
                    continue
                k = "L" if o.get("name") == nom["L"] else ("V" if o.get("name") == nom["V"] else None)
                if not k:
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


def evaluar(probs, mejor, mercado, fiable=True):
    """VALOR solo si: ventaja >= 5 %, prob >= 10 %, prob > mercado, la diferencia con el mercado
    no pasa de 15 puntos (diferencias mayores suelen ser un error del modelo, no una oportunidad)
    y la liga es 'fiable' (en el backtest supera claramente a elegir siempre al local)."""
    ev = {}
    valor = []
    for k in ("L", "V"):
        ev[k] = round(probs[k] * mejor[k]["c"] - 1, 4)
        if (fiable and ev[k] >= UMBRAL_VALOR and probs[k] >= PROB_MIN and probs[k] > mercado[k]
                and probs[k] - mercado[k] <= DIF_MAX_MERCADO):
            valor.append(k)
    return ev, valor


# ---------------------------------------------------------------- record en directo
def stats_directo(lista):
    res = [p for p in lista if p.get("resultado")]
    n = len(res)
    hit = 0
    br = 0.0
    for p in res:
        w = p["resultado"] == "L"
        hit += 1 if (p["pl"] > 0.5) == w else 0
        br += (p["pl"] - (1.0 if w else 0.0)) ** 2
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
    return {"total": len(lista), "resueltas": n, "aciertos": hit,
            "acierto": round(hit / float(n), 4) if n else None, "ic": wilson(hit, n),
            "brier": round(br / n, 4) if n else None, "apuestas": ap, "ganadas": gan,
            "roi": round(ben / ap, 4) if ap else None}


# ---------------------------------------------------------------- una liga
def procesar(clave, cfg, ahora, stamp, restantes):
    print("---- %s" % cfg["nombre"])
    cache = leer_json("equipos_%s_resultados.json" % clave, {"juegos": {}})
    juegos = cache.get("juegos", {})
    if not juegos:
        print("Primera ejecucion: se descarga el historico desde %s" % cfg["inicio"])
    if cfg["fuente"] == "euro":
        nuevos, errores = descargar_euro(cfg, not juegos, ahora)
        origen = "Euroleague (oficial)"
    else:
        # Si la descarga historica quedo a medias, se continua desde donde se quedo
        hecho = cache.get("historico_hasta")
        if juegos and hecho and hecho >= (ahora - timedelta(days=12)).strftime("%Y-%m-%d"):
            desde = ahora - timedelta(days=12)
        elif juegos and hecho:
            desde = datetime.strptime(hecho, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
            print("Se continua la descarga historica desde %s" % desde.strftime("%Y-%m-%d"))
        elif juegos:
            desde = ahora - timedelta(days=12)
        else:
            desde = datetime.strptime(cfg["inicio"], "%Y%m%d").replace(tzinfo=timezone.utc)
        nuevos, errores, llegado = descargar(cfg["ruta"], desde, ahora + timedelta(days=3), cfg.get("extra", ""),
                                             cfg.get("meses"))
        if llegado:
            cache["historico_hasta"] = max(cache.get("historico_hasta") or "", llegado.strftime("%Y-%m-%d"))
        origen = "ESPN"
    print("Partidos leidos de %s: %d (bloques con error: %d)" % (origen, len(nuevos), errores))
    proximos = []
    for g in nuevos:
        if g["tipo"] not in (2, 3, 5):   # 2 regular, 3 playoff, 5 play-in
            continue
        if g["terminado"] and g["pl"] is not None and g["pv"] is not None and g["pl"] != g["pv"]:
            juegos[g["id"]] = g
        elif not g["terminado"]:
            proximos.append(g)
    if len(juegos) < 150:
        print("ERROR: solo hay %d partidos terminados. No se cambia nada en %s." % (len(juegos), cfg["nombre"]))
        return restantes
    with open(os.path.join(DATA, "equipos_%s_resultados.json" % clave), "w", encoding="utf-8") as f:
        json.dump({"actualizado": stamp, "historico_hasta": cache.get("historico_hasta"), "juegos": juegos}, f, ensure_ascii=False, separators=(",", ":"))

    cuenta = {}
    for g in juegos.values():
        cuenta[g["local"]] = cuenta.get(g["local"], 0) + 1
        cuenta[g["visitante"]] = cuenta.get(g["visitante"], 0) + 1
    validos = set(e for e, n in cuenta.items() if n >= cfg["min_eq"])
    lista_j = sorted([g for g in juegos.values() if g["local"] in validos and g["visitante"] in validos],
                     key=lambda g: g["fecha"])
    ultima = lista_j[-1]["fecha"]
    dias = (ahora - parse_iso(ultima)).days
    params, inf_motor = motor_equipos.ajustar(lista_j, cfg)
    elo, ev, bal = motor_equipos.recorrido_final(lista_j, cfg, params)
    mm, mb = inf_motor.get("motor") or {}, inf_motor.get("elo_basico") or {}
    print("Motor propio %s: PRUEBA %d partidos no vistos | motor %.1f%% (logloss %.4f) | Elo basico %.1f%% (logloss %.4f) -> %s" %
          (cfg["nombre"], mm.get("n", 0), 100 * (mm.get("acierto") or 0), mm.get("logloss") or 0,
           100 * (mb.get("acierto") or 0), mb.get("logloss") or 0,
           "SE USA el motor (descanso %s, forma %s)" % (params["c_desc"], params["c_forma"]) if inf_motor.get("activo")
           else "se usa el Elo basico"))
    if not ev:
        print("ERROR: no hay partidos para evaluar en %s." % cfg["nombre"])
        return restantes
    bt = backtest(ev, cfg, stamp, ultima)
    bt["desde"] = ev[0]["g"]["fecha"][:10].replace("-", "")
    bt["motor"] = inf_motor
    # VALOR solo se marca cuando se ha comprobado con cuotas historicas reales que gana dinero.
    # Para estos deportes aun no tenemos cuotas historicas, asi que no se recomienda ninguna apuesta.
    fiable = False
    bt["valor_activo"] = False
    guardar_json("equipos_%s_backtest.json" % clave, bt)
    print("Backtest %s: %d partidos, acierto %.1f%% (siempre local %.1f%%), Brier %.3f (azar 0.250). "
          "Ultimo resultado: %s (hace %d dias)" %
          (cfg["nombre"], bt["total"]["n"], bt["total"]["acierto"] * 100, bt["base_local"]["acierto"] * 100,
           bt["total"]["brier"], ultima[:10], dias))

    # Predicciones guardadas (nunca se modifican) y resultados
    hist = leer_json("equipos_%s_historial.json" % clave, {"predicciones": []})
    lista = hist.get("predicciones", [])
    por_id = {p["id"]: p for p in lista}
    nuevas = 0
    publicar = dias <= cfg["max_dias"]
    if not publicar and proximos:
        print("Aviso: el ultimo resultado tiene %d dias. No se guardan predicciones nuevas." % dias)
    for g in sorted(proximos, key=lambda x: x["fecha"]):
        if not publicar or g["id"] in por_id:
            continue
        ini = parse_iso(g["fecha"])
        if ini <= ahora or ini > ahora + timedelta(hours=HORAS_PRED):
            continue
        if g["local"] not in validos or g["visitante"] not in validos:
            continue
        if g["temporada"] != elo.temp:   # primer partido de una temporada nueva
            elo.nueva_temporada(g["temporada"])
        pl = round(elo.prob_partido(g["local"], g["visitante"], g["neutral"], parse_iso(g["fecha"])), 4)
        p = {"id": g["id"], "fecha": g["fecha"], "local": g["local"], "visitante": g["visitante"],
             "neutral": g["neutral"], "playoff": g["tipo"] == 3, "pl": pl, "pv": round(1 - pl, 4),
             "elo_l": round(elo.get(g["local"])), "elo_v": round(elo.get(g["visitante"])),
             "bal_l": bal.get(g["local"], [0, 0]), "bal_v": bal.get(g["visitante"], [0, 0]),
             "creada": stamp, "resultado": None, "marcador": None}
        lista.append(p)
        por_id[g["id"]] = p
        nuevas += 1

    # Cuotas solo si hay partidos pendientes en las proximas 48 h
    pend = [p for p in lista if p.get("resultado") is None and parse_iso(p["fecha"]) > ahora]
    if pend and LLAMAR and KEY and cfg["odds"]:
        if restantes is not None and restantes < MIN_CREDITOS:
            print("Aviso: quedan %d creditos. No se piden cuotas de %s." % (restantes, cfg["nombre"]))
        else:
            try:
                eventos, restantes = cuotas_liga(cfg, restantes)
                con = 0
                for p in pend:
                    evo, inv = emparejar(p, eventos)
                    if not evo:
                        continue
                    res = procesar_cuotas(evo, inv)
                    if not res:
                        continue
                    mejor, mercado, casas = res
                    evl, valor = evaluar({"L": p["pl"], "V": p["pv"]}, mejor, mercado, fiable)
                    p["cuota"] = {"mejor": mejor, "mercado": mercado, "casas": casas, "ev": evl,
                                  "valor": valor, "actualizado": stamp}
                    if "cuota_guardada" not in p:
                        p["cuota_guardada"] = {"fecha": stamp, "valor": valor,
                                               "L": mejor["L"]["c"], "V": mejor["V"]["c"]}
                    con += 1
                print("Cuotas %s: %d de %d partidos emparejados. Creditos restantes: %s" %
                      (cfg["nombre"], con, len(pend), restantes if restantes is not None else "?"))
            except Exception as e:
                print("Aviso: cuotas %s no disponibles (%s)" % (cfg["nombre"], e))

    liq = 0
    for p in lista:
        if p.get("resultado") is None and p["id"] in juegos:
            g = juegos[p["id"]]
            p["resultado"] = "L" if g["pl"] > g["pv"] else "V"
            p["marcador"] = "%d-%d" % (g["pl"], g["pv"])
            liq += 1
    hist["predicciones"] = lista
    hist["actualizado"] = stamp
    guardar_json("equipos_%s_historial.json" % clave, hist)

    futuros = sorted(g["fecha"] for g in proximos)
    proximo = futuros[0] if futuros else None
    visibles = sorted([p for p in lista if p.get("resultado") is None and
                       parse_iso(p["fecha"]) > ahora - timedelta(hours=4)], key=lambda x: x["fecha"])
    recientes = sorted([p for p in lista if p.get("resultado")], key=lambda x: x["fecha"], reverse=True)[:20]
    temp_actual = lista_j[-1]["temporada"]
    ranking = []
    for e in sorted(validos, key=lambda x: -elo.get(x)):
        b = bal.get(e, [0, 0]) if elo.temp == temp_actual else [0, 0]
        ranking.append({"equipo": e, "elo": round(elo.get(e)), "g": b[0], "p": b[1]})
    guardar_json("equipos_%s.json" % clave, {
        "actualizado": stamp, "liga": cfg["nombre"], "datos_hasta": ultima, "dias_desde_datos": dias,
        "fuente": ({"nombre": "Euroleague Basketball", "url": "https://www.euroleaguebasketball.net"}
                   if cfg["fuente"] == "euro" else {"nombre": "ESPN", "url": "https://www.espn.com"}),
        "con_cuotas": bool(cfg["odds"]), "proximo": proximo,
        "predicciones": visibles, "recientes": recientes, "directo": stats_directo(lista),
        "ranking": ranking})
    print("%s: %d predicciones nuevas, %d resultados anotados, %d proximos publicados" %
          (cfg["nombre"], nuevas, liq, len(visibles)))
    return restantes


def main():
    os.makedirs(DATA, exist_ok=True)
    ahora = datetime.now(timezone.utc)
    stamp = ahora.strftime("%Y-%m-%d %H:%M UTC")
    if not KEY:
        print("Aviso: falta ODDS_API_KEY. Se publican probabilidades sin cuotas.")
    restantes = None
    fallos = 0
    for clave, cfg in LIGAS.items():
        try:
            restantes = procesar(clave, cfg, ahora, stamp, restantes)
        except Exception as e:
            fallos += 1
            print("ERROR en %s: %s" % (cfg["nombre"], e))
    if fallos == len(LIGAS):
        sys.exit(1)


if __name__ == "__main__":
    main()
