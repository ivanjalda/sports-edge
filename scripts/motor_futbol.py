# -*- coding: utf-8 -*-
"""Sports Edge - MOTOR PROPIO DE FUTBOL (solo libreria estandar).

Datos: resultados reales de varias temporadas de football-data.co.uk (goles, tiros a puerta y cuotas reales).
El motor combina tres piezas:
  A) Goles: fuerza de ataque y defensa de cada equipo, dando mas peso a los partidos recientes.
  B) Tiros a puerta: la calidad de las ocasiones que crea y concede cada equipo (menos dependiente de la suerte).
  C) Elo: fuerza acumulada de cada equipo teniendo en cuenta contra quien jugo y por cuanto gano.
Como se elige todo (sin trampas):
  - Temporada mas antigua: solo para calentar. No se mide.
  - Temporadas intermedias (ENTRENAMIENTO): se eligen los ajustes y el peso de cada pieza.
  - Temporadas mas recientes (PRUEBA): se mide con partidos que el ajuste no ha visto.
  - Cada partido se predice solo con los partidos anteriores a su fecha.
En la PRUEBA se compara con el modelo anterior, con "siempre local" y con las casas de apuestas,
y se simula la regla de VALOR con las cuotas reales que habia antes de cada partido.
El motor solo se usa en directo si en la PRUEBA acierta mejor que el modelo anterior."""
import csv
import io
import json
import math
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

DATA = "data"
UA = "sports-edge/1.0 (+https://ivanjalda.github.io/sports-edge/)"
BASE_URL = "https://www.football-data.co.uk/"
MAX_G = 8
ARCHIVO = "motor_futbol.json"
DIAS_REAJUSTE = 7

# clave interna -> datos de la liga
LIGAS = {
    "E0": {"nombre": "Premier League", "tipo": "main", "api": "PL"},
    "SP1": {"nombre": "LaLiga", "tipo": "main", "api": "PD"},
    "I1": {"nombre": "Serie A", "tipo": "main", "api": "SA"},
    "D1": {"nombre": "Bundesliga", "tipo": "main", "api": "BL1"},
    "F1": {"nombre": "Ligue 1", "tipo": "main", "api": "FL1"},
    "P1": {"nombre": "Primeira Liga", "tipo": "main", "api": "PPL"},
    "N1": {"nombre": "Eredivisie", "tipo": "main", "api": "DED"},
    "E1": {"nombre": "Championship", "tipo": "main", "api": "ELC"},
    "BRA": {"nombre": "Brasileirão", "tipo": "extra", "api": "BSA"},
    "ARG": {"nombre": "Liga Profesional", "tipo": "extra", "espn": "soccer/arg.1"},
    "USA": {"nombre": "MLS", "tipo": "extra", "espn": "soccer/usa.1"},
}
TEMPORADAS_MAIN = 5        # temporadas europeas (agosto-mayo) que se descargan
ANIOS_EXTRA = 5            # temporadas de calendario (Brasil, Argentina, MLS)

# Ajustes que se prueban (se eligen con ENTRENAMIENTO)
VIDAS = [90, 180, 365, 730]         # dias para que un partido pese la mitad
PESOS_ELO = [0.002, 0.003, 0.004, 0.005, 0.006, 0.007, 0.008]
RHOS = [0.0, -0.05, -0.1]           # correccion de empates con pocos goles
PRIOR = 4.0
ELO_K = 20.0
ELO_HFA = 65.0
ELO_REVERTIR = 0.8
MIN_PJ = 5
# Reglas de VALOR (las mismas que en la web)
UMBRAL_VALOR = 0.05
PROB_MIN = 0.10
DIF_MAX = 0.15


# ------------------------------------------------------------------ utilidades
def log(*a):
    print(*a)
    sys.stdout.flush()


def bajar(url, intentos=2):
    ult = None
    for _ in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8-sig", "replace")
        except Exception as e:
            ult = e
            time.sleep(1)
    raise ult


def num(x):
    try:
        v = float(str(x).strip())
        return v if v == v else None
    except Exception:
        return None


def fecha_csv(d, t):
    d = (d or "").strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            f = datetime.strptime(d, fmt)
            break
        except Exception:
            f = None
    if f is None:
        return None
    hh, mm = 15, 0
    try:
        hh, mm = [int(x) for x in (t or "15:00").strip().split(":")[:2]]
    except Exception:
        pass
    return f.replace(hour=hh, minute=mm, tzinfo=timezone.utc)


def trio(row, pref):
    v = [num(row.get(pref + s)) for s in ("H", "D", "A")]
    return v if all(x and x > 1 for x in v) else None


def implicitas(o):
    if not o:
        return None
    s = sum(1.0 / x for x in o)
    return [(1.0 / x) / s for x in o]


# ------------------------------------------------------------------ descarga
def temporadas_main(ahora):
    ini = ahora.year if ahora.month >= 7 else ahora.year - 1
    return ["%02d%02d" % ((y) % 100, (y + 1) % 100) for y in range(ini - TEMPORADAS_MAIN + 1, ini + 1)]


def cargar_liga(clave, ahora):
    cfg = LIGAS[clave]
    out = []
    if cfg["tipo"] == "main":
        for tcode in temporadas_main(ahora):
            try:
                txt = bajar(BASE_URL + "mmz4281/%s/%s.csv" % (tcode, clave))
            except Exception as e:
                log("  Aviso: %s %s no disponible (%s)" % (clave, tcode, e))
                continue
            for row in csv.DictReader(io.StringIO(txt)):
                m = fila_main(row, tcode)
                if m:
                    out.append(m)
    else:
        try:
            txt = bajar(BASE_URL + "new/%s.csv" % clave)
        except Exception as e:
            log("  Aviso: %s no disponible (%s)" % (clave, e))
            return []
        anio_min = ahora.year - ANIOS_EXTRA + 1
        for row in csv.DictReader(io.StringIO(txt)):
            m = fila_extra(row, anio_min)
            if m:
                out.append(m)
    out.sort(key=lambda x: x["f"])
    return out


def fila_main(row, tcode):
    h, a = (row.get("HomeTeam") or "").strip(), (row.get("AwayTeam") or "").strip()
    gh, ga = num(row.get("FTHG")), num(row.get("FTAG"))
    f = fecha_csv(row.get("Date"), row.get("Time"))
    if not h or not a or f is None or gh is None or ga is None:
        return None
    return {"f": f, "temp": tcode, "h": h, "a": a, "gh": int(gh), "ga": int(ga),
            "hst": num(row.get("HST")), "ast": num(row.get("AST")),
            "hhg": num(row.get("HTHG")), "hag": num(row.get("HTAG")),
            "o_pre_max": trio(row, "Max") or trio(row, "BbMx"),
            "o_pre_avg": trio(row, "Avg") or trio(row, "BbAv"),
            "o_close": trio(row, "AvgC") or trio(row, "PSC")}


def fila_extra(row, anio_min):
    temp = (row.get("Season") or "").strip()
    try:
        y = int(temp[:4])
    except Exception:
        return None
    if y < anio_min:
        return None
    h, a = (row.get("Home") or "").strip(), (row.get("Away") or "").strip()
    gh, ga = num(row.get("HG")), num(row.get("AG"))
    f = fecha_csv(row.get("Date"), row.get("Time"))
    if not h or not a or f is None or gh is None or ga is None:
        return None
    close = trio(row, "AvgC") or trio(row, "PSC")
    return {"f": f, "temp": temp, "h": h, "a": a, "gh": int(gh), "ga": int(ga),
            "hst": None, "ast": None, "hhg": None, "hag": None,
            "o_pre_max": trio(row, "MaxC"), "o_pre_avg": close, "o_close": close}


# ------------------------------------------------------------------ probabilidades
def pmf(lam):
    p = [math.exp(-lam)]
    for k in range(1, MAX_G + 1):
        p.append(p[-1] * lam / k)
    return p


def prob_1x2(lh, la, rho):
    ph, pa = pmf(lh), pmf(la)
    p1 = px = p2 = 0.0
    for i in range(MAX_G + 1):
        for j in range(MAX_G + 1):
            v = ph[i] * pa[j]
            if rho and i <= 1 and j <= 1:
                if i == 0 and j == 0:
                    v *= max(1 - lh * la * rho, 0.0)
                elif i == 0 and j == 1:
                    v *= max(1 + lh * rho, 0.0)
                elif i == 1 and j == 0:
                    v *= max(1 + la * rho, 0.0)
                else:
                    v *= max(1 - rho, 0.0)
            if i > j:
                p1 += v
            elif i == j:
                px += v
            else:
                p2 += v
    s = p1 + px + p2
    return [p1 / s, px / s, p2 / s]


def mercados(lh, la, rho, frac):
    ph, pa = pmf(lh), pmf(la)
    tot = o15 = o25 = o35 = btts = 0.0
    mejor = (0, 0, 0.0)
    for i in range(MAX_G + 1):
        for j in range(MAX_G + 1):
            v = ph[i] * pa[j]
            if rho and i <= 1 and j <= 1:
                v *= max({(0, 0): 1 - lh * la * rho, (0, 1): 1 + lh * rho, (1, 0): 1 + la * rho,
                          (1, 1): 1 - rho}[(i, j)], 0.0)
            tot += v
            if i + j >= 2:
                o15 += v
            if i + j >= 3:
                o25 += v
            if i + j >= 4:
                o35 += v
            if i > 0 and j > 0:
                btts += v
            if v > mejor[2]:
                mejor = (i, j, v)
    m = {"over15": round(o15 / tot, 4), "over25": round(o25 / tot, 4), "over35": round(o35 / tot, 4),
         "btts": round(btts / tot, 4), "marcador": "%d-%d" % (mejor[0], mejor[1]),
         "p_marcador": round(mejor[2] / tot, 4),
         "ht_local": None, "ht_empate": None, "ht_visitante": None, "ht_gol": None}
    if frac:
        p = prob_1x2(lh * frac, la * frac, 0.0)
        m["ht_local"], m["ht_empate"], m["ht_visitante"] = [round(x, 4) for x in p]
        m["ht_gol"] = round(1 - math.exp(-(lh + la) * frac), 4)
    return m


def logloss(p, k):
    return -math.log(max(p[k], 1e-6))


def brier(p, k):
    return sum((p[i] - (1.0 if i == k else 0.0)) ** 2 for i in range(3))


def res_idx(gh, ga):
    return 0 if gh > ga else (1 if gh == ga else 2)


# ------------------------------------------------------------------ piezas del motor
class Decaido(object):
    """Sumas que pierden peso con el tiempo (vida media en dias). vida=None: no pierden peso."""
    __slots__ = ("vida", "t", "v")

    def __init__(self, vida, n):
        self.vida = vida
        self.t = None
        self.v = [0.0] * n

    def llevar(self, t):
        if self.t is not None and self.vida is not None and t > self.t:
            fct = 0.5 ** ((t - self.t).total_seconds() / 86400.0 / self.vida)
            self.v = [x * fct for x in self.v]
        self.t = t if self.t is None or t > self.t else self.t

    def sumar(self, t, vals):
        self.llevar(t)
        for i, x in enumerate(vals):
            self.v[i] += x


class Piezas(object):
    """Recorre los partidos de UNA liga en orden y da, antes de cada partido, lo que predice cada pieza."""

    def __init__(self, vida_a, vida_b, reset_temporada=False):
        self.va, self.vb = vida_a, vida_b
        self.reset = reset_temporada
        self.temp = None
        self.nuevo()
        self.elo = {}
        self.pj = {}
        self.vistos_temp = {}

    def nuevo(self):
        self.lg = Decaido(self.va, 4)      # goles local, goles visit, partidos, -
        self.eq = {}                        # equipo -> Decaido(gf, gc, pj)
        self.ls = Decaido(self.vb, 5)       # tiros local, tiros visit, goles local (con tiros), goles visit, partidos
        self.es = {}                        # equipo -> Decaido(tf, tc, pj)
        self.ht = Decaido(self.va, 2)       # goles al descanso, goles totales

    def cambio_temporada(self, temp):
        if self.temp is None:
            self.temp = temp
            return
        if temp == self.temp:
            return
        media = (sum(self.elo.values()) / len(self.elo)) if self.elo else 1500.0
        for k in self.elo:
            self.elo[k] = ELO_REVERTIR * self.elo[k] + (1 - ELO_REVERTIR) * media
        if self.reset:
            self.nuevo()
        self.temp = temp

    def elo_de(self, e):
        if e not in self.elo:
            media = (sum(self.elo.values()) / len(self.elo)) if self.elo else 1500.0
            self.elo[e] = media - (50.0 if self.elo else 0.0)   # recien ascendido: algo por debajo de la media
        return self.elo[e]

    def antes(self, m):
        """Lo que dice cada pieza ANTES del partido m (sin mirar su resultado)."""
        t, h, a = m["f"], m["h"], m["a"]
        self.cambio_temporada(m["temp"])
        out = {"ok": self.pj.get(h, 0) >= MIN_PJ and self.pj.get(a, 0) >= MIN_PJ}
        self.lg.llevar(t)
        gh, ga, n = self.lg.v[0], self.lg.v[1], self.lg.v[2]
        if n < 20:
            out["ok"] = False
            return out
        mh, ma = gh / n, ga / n
        mu = (mh + ma) / 2
        eh, ea = self.eq.get(h), self.eq.get(a)
        for e in (eh, ea):
            if e:
                e.llevar(t)

        def fz(e):
            if not e:
                return 1.0, 1.0
            return ((e.v[0] + PRIOR * mu) / (e.v[2] + PRIOR) / mu, (e.v[1] + PRIOR * mu) / (e.v[2] + PRIOR) / mu)
        ah, dh = fz(eh)
        aa, da = fz(ea)
        out["A"] = (max(mh * ah * da, 0.1), max(ma * aa * dh, 0.1))
        # B: tiros a puerta
        self.ls.llevar(t)
        sh, sa, g2h, g2a, ns = self.ls.v
        if ns >= 20 and sh > 0 and sa > 0:
            smh, sma = sh / ns, sa / ns
            smu = (smh + sma) / 2
            sh_, sa_ = self.es.get(h), self.es.get(a)
            for e in (sh_, sa_):
                if e:
                    e.llevar(t)

            def fs(e):
                if not e or e.v[2] < 1:
                    return None
                return ((e.v[0] + PRIOR * smu) / (e.v[2] + PRIOR) / smu, (e.v[1] + PRIOR * smu) / (e.v[2] + PRIOR) / smu)
            x, y = fs(sh_), fs(sa_)
            if x and y:
                out["B"] = (max(smh * x[0] * y[1] * (g2h / sh), 0.1), max(sma * y[0] * x[1] * (g2a / sa), 0.1))
        # C: Elo
        out["dr"] = self.elo_de(h) + ELO_HFA - self.elo_de(a)
        self.ht.llevar(t)
        out["frac"] = (self.ht.v[0] / self.ht.v[1]) if self.ht.v[1] > 30 else None
        return out

    def despues(self, m):
        t, h, a, gh, ga = m["f"], m["h"], m["a"], m["gh"], m["ga"]
        self.lg.sumar(t, [gh, ga, 1, 0])
        for e, f, c in ((h, gh, ga), (a, ga, gh)):
            self.eq.setdefault(e, Decaido(self.va, 3)).sumar(t, [f, c, 1])
            self.pj[e] = self.pj.get(e, 0) + 1
        if m.get("hst") is not None and m.get("ast") is not None:
            self.ls.sumar(t, [m["hst"], m["ast"], gh, ga, 1])
            for e, f, c in ((h, m["hst"], m["ast"]), (a, m["ast"], m["hst"])):
                self.es.setdefault(e, Decaido(self.vb, 3)).sumar(t, [f, c, 1])
        if m.get("hhg") is not None and m.get("hag") is not None:
            self.ht.sumar(t, [m["hhg"] + m["hag"], gh + ga])
        # Elo
        dr = self.elo_de(h) + ELO_HFA - self.elo_de(a)
        we = 1.0 / (1.0 + 10 ** (-dr / 400.0))
        w = 1.0 if gh > ga else (0.5 if gh == ga else 0.0)
        d = abs(gh - ga)
        g = 1.0 if d <= 1 else (1.5 if d == 2 else (11.0 + d) / 8.0)
        cambio = ELO_K * g * (w - we)
        self.elo[h] += cambio
        self.elo[a] -= cambio


def lambdas(pz, params):
    """Combina las piezas con los pesos elegidos."""
    wa, wb, wc, k = params["wa"], params["wb"], params["wc"], params["k_elo"]
    A = pz.get("A")
    if not A:
        return None
    T = A[0] + A[1]
    s = k * pz["dr"]
    C = (max((T + s) / 2, 0.1), max((T - s) / 2, 0.1))
    B = pz.get("B")
    if not B:
        wa, wb = wa + wb, 0.0
    tot = wa + wb + wc
    lh = (wa * A[0] + wb * (B[0] if B else 0) + wc * C[0]) / tot
    la = (wa * A[1] + wb * (B[1] if B else 0) + wc * C[1]) / tot
    return lh, la


# ------------------------------------------------------------------ laboratorio
def fases(ms, tipo):
    """Divide las temporadas: la 1a calienta, las intermedias entrenan, las 2 ultimas son PRUEBA."""
    temps = sorted(set(m["temp"] for m in ms))
    if len(temps) < 4:
        return {}
    out = {temps[0]: "calentar"}
    for t in temps[1:-2]:
        out[t] = "entrena"
    for t in temps[-2:]:
        out[t] = "prueba"
    return out


def recorrer(ms, vida_a, vida_b, reset=False):
    pz = Piezas(vida_a, vida_b, reset)
    filas = []
    for m in ms:
        p = pz.antes(m)
        filas.append(p)
        pz.despues(m)
    return filas


def ajustar(hist, ahora):
    t0 = time.time()
    datos = {c: ms for c, ms in hist.items() if len(ms) > 200}
    fase = {c: fases(ms, LIGAS[c]["tipo"]) for c, ms in datos.items()}
    # Paso 1: vida media de goles (A) y de tiros (B), cada una sola
    pasadas = {}
    for v in VIDAS:
        pasadas[v] = {c: recorrer(ms, v, v) for c, ms in datos.items()}

    def err(fn):
        s = n = 0
        for c, ms in datos.items():
            for m, p in zip(ms, pasadas_sel[c]):
                if fase[c].get(m["temp"]) != "entrena" or not p.get("ok"):
                    continue
                r = fn(p)
                if r is None:
                    continue
                s += logloss(prob_1x2(r[0], r[1], 0.0), res_idx(m["gh"], m["ga"]))
                n += 1
        return s / n if n else 9e9
    mejor_a = mejor_b = None
    for v in VIDAS:
        pasadas_sel = pasadas[v]
        ea = err(lambda p: p.get("A"))
        eb = err(lambda p: p.get("B"))
        log("  vida %d dias: goles %.4f | tiros a puerta %.4f" % (v, ea, eb))
        if mejor_a is None or ea < mejor_a[1]:
            mejor_a = (v, ea)
        if mejor_b is None or eb < mejor_b[1]:
            mejor_b = (v, eb)
    va, vb = mejor_a[0], mejor_b[0]
    # una pasada con la vida de A para A y la de B para B
    sel = {c: recorrer(ms, va, vb) for c, ms in datos.items()}
    pasadas_sel = sel
    # Paso 2: peso del Elo
    mejor_k = None
    for k in PESOS_ELO:
        e = err(lambda p: lambdas(p, {"wa": 0, "wb": 0, "wc": 1, "k_elo": k}))
        if mejor_k is None or e < mejor_k[1]:
            mejor_k = (k, e)
    log("  Elo: mejor peso %.3f (%.4f)" % mejor_k)
    # Paso 3: mezcla de las tres piezas y correccion de empates
    cand = []
    pasos = [i / 4.0 for i in range(5)]
    for wa in pasos:
        for wb in pasos:
            wc = 1.0 - wa - wb
            if wc < -1e-9:
                continue
            for rho in RHOS:
                cand.append({"wa": wa, "wb": wb, "wc": max(wc, 0.0), "k_elo": mejor_k[0], "rho": rho,
                             "vida_a": va, "vida_b": vb})
    mejor = None
    for pr in cand:
        if pr["wa"] + pr["wb"] + pr["wc"] <= 0:
            continue
        s = n = 0
        for c, ms in datos.items():
            for m, p in zip(ms, sel[c]):
                if fase[c].get(m["temp"]) != "entrena" or not p.get("ok"):
                    continue
                l = lambdas(p, pr)
                if not l:
                    continue
                s += logloss(prob_1x2(l[0], l[1], pr["rho"]), res_idx(m["gh"], m["ga"]))
                n += 1
        e = s / n if n else 9e9
        if mejor is None or e < mejor[1]:
            mejor = (pr, e)
    params = mejor[0]
    log("  Mezcla elegida: goles %.2f, tiros %.2f, Elo %.2f, empates %.2f (entrenamiento %.4f)" %
        (params["wa"], params["wb"], params["wc"], params["rho"], mejor[1]))
    # PRUEBA con partidos no vistos
    viejo = {c: recorrer(ms, None, None, reset=True) for c, ms in datos.items()}
    informe = medir_prueba(datos, fase, sel, viejo, params)
    informe["segundos"] = int(time.time() - t0)
    return params, informe


def medir_prueba(datos, fase, sel, viejo, params):
    tot = {"motor": [], "anterior": [], "mercado": [], "local": []}
    por_liga = {}
    apuestas = []
    for c, ms in datos.items():
        L = {"motor": [], "anterior": [], "mercado": [], "local": []}
        for m, p, q in zip(ms, sel[c], viejo[c]):
            if fase[c].get(m["temp"]) != "prueba" or not p.get("ok") or not q.get("ok"):
                continue
            l = lambdas(p, params)
            if not l or not q.get("A"):
                continue
            k = res_idx(m["gh"], m["ga"])
            pm = prob_1x2(l[0], l[1], params["rho"])
            pv = prob_1x2(q["A"][0], q["A"][1], 0.0)
            mk = implicitas(m.get("o_close") or m.get("o_pre_avg"))
            for nom, pp in (("motor", pm), ("anterior", pv), ("mercado", mk), ("local", [1.0, 0.0, 0.0])):
                if pp is None:
                    continue
                fila = (1 if max(range(3), key=lambda i: pp[i]) == k else 0, brier(pp, k), logloss(pp, k) if nom != "local" else None)
                L[nom].append(fila)
                tot[nom].append(fila)
            # simulacion de VALOR con las cuotas que habia antes del partido
            omax, oavg = m.get("o_pre_max"), m.get("o_pre_avg")
            if omax and oavg:
                imp = implicitas(oavg)
                for i in range(3):
                    ev = pm[i] * omax[i] - 1
                    if ev >= UMBRAL_VALOR and pm[i] >= PROB_MIN and pm[i] > imp[i] and pm[i] - imp[i] <= DIF_MAX:
                        apuestas.append((c, omax[i] - 1 if i == k else -1.0))
        por_liga[LIGAS[c]["nombre"]] = {n: resumen(v) for n, v in L.items()}
    ganancia = sum(a[1] for a in apuestas)
    return {"total": {n: resumen(v) for n, v in tot.items()}, "ligas": por_liga,
            "valor": {"apuestas": len(apuestas), "ganadas": sum(1 for a in apuestas if a[1] > 0),
                      "roi": round(ganancia / len(apuestas), 4) if apuestas else None,
                      "ic_roi": ic_roi([a[1] for a in apuestas])}}


def resumen(filas):
    n = len(filas)
    if not n:
        return None
    ll = [f[2] for f in filas if f[2] is not None]
    return {"n": n, "acierto": round(sum(f[0] for f in filas) / float(n), 4),
            "brier": round(sum(f[1] for f in filas) / n, 4),
            "logloss": round(sum(ll) / len(ll), 4) if ll else None}


def ic_roi(r):
    n = len(r)
    if n < 30:
        return None
    m = sum(r) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in r) / (n - 1))
    return [round(m - 1.96 * sd / math.sqrt(n), 4), round(m + 1.96 * sd / math.sqrt(n), 4)]


# ------------------------------------------------------------------ uso en directo
class Motor(object):
    def __init__(self):
        self.hist = {}
        self.params = None
        self.activo = False
        self.estado = {}
        self.frac = {}

    def predecir(self, clave, h, a):
        """Prediccion con el estado de la liga despues del ultimo partido jugado."""
        pz = self.estado.get(clave)
        if not pz or not self.params:
            return None
        m = {"f": datetime.now(timezone.utc), "temp": pz.temp, "h": h, "a": a}
        p = pz.antes(m)
        if not p.get("ok"):
            return None
        l = lambdas(p, self.params)
        if not l:
            return None
        pr = prob_1x2(l[0], l[1], self.params["rho"])
        return {"p_local": round(pr[0], 4), "p_empate": round(pr[1], 4), "p_visitante": round(pr[2], 4),
                "xg_local": round(l[0], 2), "xg_visitante": round(l[1], 2),
                "n_partidos": min(pz.pj.get(h, 0), pz.pj.get(a, 0)),
                "mercados": mercados(l[0], l[1], self.params["rho"], p.get("frac")), "modelo": "SE"}

    def equipos(self, clave, temporada_actual=True):
        ms = self.hist.get(clave, [])
        if not ms:
            return set()
        ult = ms[-1]["temp"]
        return set(x for m in ms if (not temporada_actual or m["temp"] == ult) for x in (m["h"], m["a"]))

    def mapear(self, clave, jugados):
        """Empareja nombres de otra fuente con los de la nuestra usando partidos ya jugados:
        mismo dia (+-1) y mismo marcador. jugados: lista de (fecha, nombre_local, nombre_visit, gl, gv)."""
        ms = self.hist.get(clave, [])
        votos = {}
        for f, hn, an, gh, ga in jugados:
            cand = [m for m in ms if abs((m["f"].date() - f.date()).days) <= 1 and m["gh"] == gh and m["ga"] == ga]
            if len(cand) != 1:
                continue
            c = cand[0]
            votos.setdefault(hn, {}).setdefault(c["h"], 0)
            votos[hn][c["h"]] += 1
            votos.setdefault(an, {}).setdefault(c["a"], 0)
            votos[an][c["a"]] += 1
        out, usados = {}, set()
        for nom, v in sorted(votos.items(), key=lambda x: -max(x[1].values())):
            mejor = max(v.items(), key=lambda x: x[1])
            if mejor[1] >= 2 and mejor[0] not in usados:
                out[nom] = mejor[0]
                usados.add(mejor[0])
        return out


def preparar(ahora=None, forzar=False):
    """Descarga el historico, ajusta el motor si toca y deja el estado listo para predecir."""
    ahora = ahora or datetime.now(timezone.utc)
    os.makedirs(DATA, exist_ok=True)
    M = Motor()
    log("Motor propio: descargando historico de football-data.co.uk ...")
    for c in LIGAS:
        ms = cargar_liga(c, ahora)
        M.hist[c] = ms
        if ms:
            log("  %s: %d partidos (%s a %s)" % (LIGAS[c]["nombre"], len(ms), ms[0]["f"].strftime("%Y-%m-%d"),
                                                 ms[-1]["f"].strftime("%Y-%m-%d")))
    if sum(len(v) for v in M.hist.values()) < 2000:
        log("ERROR motor propio: muy pocos datos. Se usa el modelo anterior.")
        return None
    previo = {}
    try:
        with open(os.path.join(DATA, ARCHIVO), encoding="utf-8") as f:
            previo = json.load(f)
    except Exception:
        pass
    viejo = True
    try:
        viejo = (ahora - datetime.strptime(previo.get("ajustado", ""), "%Y-%m-%d %H:%M UTC").replace(
            tzinfo=timezone.utc)).days >= DIAS_REAJUSTE
    except Exception:
        pass
    if forzar or viejo or not previo.get("params"):
        log("Motor propio: ajustando con temporadas de entrenamiento y midiendo con las de prueba ...")
        params, informe = ajustar(M.hist, ahora)
        t = informe["total"]
        activo = bool(t.get("motor") and t.get("anterior") and t["motor"]["logloss"] < t["anterior"]["logloss"])
        previo = {"ajustado": ahora.strftime("%Y-%m-%d %H:%M UTC"), "params": params, "activo": activo,
                  "prueba": informe, "ligas": [LIGAS[c]["nombre"] for c in LIGAS]}
        mm, mv, mk = t.get("motor") or {}, t.get("anterior") or {}, t.get("mercado") or {}
        log("PRUEBA (%d partidos no vistos): motor %.1f%% Brier %.4f | anterior %.1f%% Brier %.4f | casas %.1f%% Brier %.4f" %
            (mm.get("n", 0), 100 * (mm.get("acierto") or 0), mm.get("brier") or 0, 100 * (mv.get("acierto") or 0),
             mv.get("brier") or 0, 100 * (mk.get("acierto") or 0), mk.get("brier") or 0))
        v = informe["valor"]
        log("VALOR simulado con cuotas reales: %d apuestas, ROI %s" % (v["apuestas"], v["roi"]))
        log("El motor propio %s en directo." % ("SE USA" if activo else "NO se usa (no mejora al anterior)"))
    M.params = previo["params"]
    M.activo = previo.get("activo", False)
    previo["actualizado"] = ahora.strftime("%Y-%m-%d %H:%M UTC")
    with open(os.path.join(DATA, ARCHIVO), "w", encoding="utf-8") as f:
        json.dump(previo, f, ensure_ascii=False, indent=1)
    # estado de cada liga despues del ultimo partido
    for c, ms in M.hist.items():
        if not ms:
            continue
        pz = Piezas(M.params["vida_a"], M.params["vida_b"])
        for m in ms:
            pz.antes(m)
            pz.despues(m)
        M.estado[c] = pz
    return M


if __name__ == "__main__":
    preparar(forzar="--ajustar" in sys.argv)
