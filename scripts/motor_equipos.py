# -*- coding: utf-8 -*-
"""Sports Edge - MOTOR PROPIO para deportes de equipo sin empate (baloncesto, hockey, futbol americano).

Piezas:
  1) Elo: fuerza de cada equipo segun contra quien jugo y por cuanto gano (con ventaja de campo).
  2) Descanso: dias desde el ultimo partido de cada equipo (jugar dos dias seguidos cansa).
  3) Forma a varias escalas (la idea "fractal": mirar el mismo rendimiento con distintas lupas):
     - temporada completa -> el Elo;  ultimos 10 partidos -> forma;  ultimos 3 -> racha corta;
     - como juega el local EN CASA (ultimos 5) frente a como juega el visitante FUERA (ultimos 5).
     Cada escala solo entra si mejora la prediccion en partidos de ENTRENAMIENTO, y el motor entero
     solo se usa si en la PRUEBA (partidos no vistos) mejora al Elo basico.
Como se elige (sin trampas), igual que en futbol:
  - 1a temporada: calentar.  Temporadas intermedias: ENTRENAMIENTO (se eligen los ajustes).
  - 2 temporadas mas recientes: PRUEBA con partidos no vistos.
  - Cada partido se predice solo con lo anterior a su fecha.
El motor solo se usa si en la PRUEBA acierta mejor que el Elo basico. Si no, se usa el Elo basico."""
import math
from collections import deque
from datetime import datetime, timezone

MEDIA = 1505.0
K_MUL = [0.7, 1.0, 1.4]
H_MUL = [0.6, 1.0, 1.4]
C_DESCANSO = [0.0, 10.0, 20.0, 35.0]   # puntos Elo por cada dia de descanso de diferencia (max 3)
C_FORMA = [0.0, 15.0, 30.0, 60.0]      # puntos Elo por cada unidad de forma (margen normalizado)
C_MICRO = [0.0, 15.0, 30.0, 60.0]      # puntos Elo por unidad de racha corta (ultimos 3)
C_SEDE = [0.0, 15.0, 30.0, 60.0]       # puntos Elo por unidad de forma en casa / fuera (ultimos 5)
BASE = {"kmul": 1.0, "hmul": 1.0, "c_desc": 0.0, "c_forma": 0.0, "c_micro": 0.0, "c_sede": 0.0}
VENTANA_FORMA = 10
VENTANA_MICRO = 3
VENTANA_SEDE = 5
MEJORA_MINIMA = 0.001   # mejora minima de logloss en validacion para aceptar una escala nueva


def fecha(s):
    s = str(s).replace("Z", "")[:19]
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


def mult_mov(tipo, mov, dr):
    mov = max(1, abs(mov))
    if tipo == "nba":
        return ((mov + 3) ** 0.8) / (7.5 + 0.006 * dr)
    if tipo == "nfl":
        return math.log(mov + 1) * (2.2 / (dr * 0.001 + 2.2))
    return (0.6686 * math.log(mov) + 0.8048) * (2.05 / (dr * 0.001 + 2.05))


class Estado(object):
    def __init__(self, cfg, params, sd):
        self.cfg = cfg
        self.p = params
        self.k = cfg["k"] * params["kmul"]
        self.hca = cfg["hca"] * params["hmul"]
        self.sd = sd or 1.0
        self.r = {}
        self.temp = None
        self.ultimo = {}
        self.forma = {}
        self.corto = {}
        self.casa = {}
        self.fuera = {}

    def get(self, e):
        return self.r.get(e, MEDIA)

    def nueva_temporada(self, t):
        if self.temp is not None and t != self.temp:
            a = self.cfg["revertir"]
            for e in self.r:
                self.r[e] = a * self.r[e] + (1 - a) * MEDIA
            self.forma, self.corto, self.casa, self.fuera = {}, {}, {}, {}
        self.temp = t

    def rasgos(self, local, visit, neutral, f):
        def desc(e):
            u = self.ultimo.get(e)
            if u is None:
                return 3.0
            return float(min(max((f.date() - u.date()).days, 0), 3))

        def fm(dic, e):
            q = dic.get(e)
            return (sum(q) / len(q)) if q else 0.0
        return {"dr0": self.get(local) - self.get(visit), "hca": 0.0 if neutral else self.hca,
                "d": desc(local) - desc(visit), "fo": fm(self.forma, local) - fm(self.forma, visit),
                "f3": fm(self.corto, local) - fm(self.corto, visit),
                "se": 0.0 if neutral else fm(self.casa, local) - fm(self.fuera, visit)}

    def prob(self, x, p=None):
        p = p or self.p
        dif = (x["dr0"] + x["hca"] + p["c_desc"] * x["d"] + p["c_forma"] * x["fo"]
               + p.get("c_micro", 0.0) * x["f3"] + p.get("c_sede", 0.0) * x["se"])
        return 1.0 / (1.0 + 10 ** (-dif / 400.0))

    def prob_partido(self, local, visit, neutral, f):
        return self.prob(self.rasgos(local, visit, neutral, f))

    def actualizar(self, g):
        f = fecha(g["fecha"])
        l, v = g["local"], g["visitante"]
        x = self.rasgos(l, v, g["neutral"], f)
        p = 1.0 / (1.0 + 10 ** (-(x["dr0"] + x["hca"]) / 400.0))
        gana = g["pl"] > g["pv"]
        dr = (x["dr0"] + x["hca"]) * (1 if gana else -1)
        k = self.k * mult_mov(self.cfg["mov"], g["pl"] - g["pv"], dr)
        c = k * ((1.0 if gana else 0.0) - p)
        self.r[l] = self.get(l) + c
        self.r[v] = self.get(v) - c
        self.ultimo[l] = f
        self.ultimo[v] = f
        m = (g["pl"] - g["pv"]) / self.sd
        self.forma.setdefault(l, deque(maxlen=VENTANA_FORMA)).append(m)
        self.forma.setdefault(v, deque(maxlen=VENTANA_FORMA)).append(-m)
        self.corto.setdefault(l, deque(maxlen=VENTANA_MICRO)).append(m)
        self.corto.setdefault(v, deque(maxlen=VENTANA_MICRO)).append(-m)
        if not g["neutral"]:
            self.casa.setdefault(l, deque(maxlen=VENTANA_SEDE)).append(m)
            self.fuera.setdefault(v, deque(maxlen=VENTANA_SEDE)).append(-m)


def fases(juegos):
    temps = sorted(set(g["temporada"] for g in juegos))
    if len(temps) < 3:
        return {t: "prueba" for t in temps[1:]}
    out = {temps[0]: "calentar"}
    for t in temps[1:-2]:
        out[t] = "entrena"
    for t in temps[-2:]:
        out[t] = "prueba"
    if len(temps) == 3:
        out[temps[1]] = "entrena"
    return out


def desviacion(juegos):
    m = [g["pl"] - g["pv"] for g in juegos]
    if len(m) < 2:
        return 1.0
    mu = sum(m) / len(m)
    return math.sqrt(sum((x - mu) ** 2 for x in m) / (len(m) - 1)) or 1.0


def pasada(juegos, cfg, params, sd):
    """Recorre los partidos: rasgos ANTES de cada partido y luego actualiza."""
    st = Estado(cfg, params, sd)
    filas = []
    for g in juegos:
        st.nueva_temporada(g["temporada"])
        filas.append(st.rasgos(g["local"], g["visitante"], g["neutral"], fecha(g["fecha"])))
        st.actualizar(g)
    return st, filas


def ll(p, w):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -math.log(p if w else 1 - p)


def medir(items):
    n = len(items)
    if not n:
        return None
    return {"n": n, "acierto": round(sum(1 for p, w in items if (p > 0.5) == w) / float(n), 4),
            "brier": round(sum((p - (1.0 if w else 0.0)) ** 2 for p, w in items) / n, 4),
            "logloss": round(sum(ll(p, w) for p, w in items) / n, 4)}


def ajustar(juegos, cfg):
    """Elige los ajustes con ENTRENAMIENTO y mide con PRUEBA. Devuelve (params, informe)."""
    fs = fases(juegos)
    sd = desviacion(juegos)
    res = [g["pl"] > g["pv"] for g in juegos]
    fase = [fs.get(g["temporada"]) for g in juegos]
    mejor = None
    base_filas = None
    for km in K_MUL:
        for hm in H_MUL:
            pr0 = {"kmul": km, "hmul": hm, "c_desc": 0.0, "c_forma": 0.0, "c_micro": 0.0, "c_sede": 0.0}
            st, filas = pasada(juegos, cfg, pr0, sd)
            if km == 1.0 and hm == 1.0:
                base_filas = filas
            for cd in C_DESCANSO:
                for cf in C_FORMA:
                    pr = {"kmul": km, "hmul": hm, "c_desc": cd, "c_forma": cf, "c_micro": 0.0, "c_sede": 0.0}
                    s = n = 0
                    for x, w, f in zip(filas, res, fase):
                        if f != "entrena":
                            continue
                        s += ll(st.prob(x, pr), w)
                        n += 1
                    if n and (mejor is None or s / n < mejor[1]):
                        mejor = (pr, s / n, filas)
    if mejor is None:
        return dict(BASE), {"activo": False, "motivo": "sin temporadas de entrenamiento"}
    pr, mej_ll, filas = mejor
    # Escalas cortas (racha de 3 y casa/fuera): se deciden con la ULTIMA temporada de entrenamiento
    # (validacion) y solo entran si mejoran claramente; asi no se "aprende de memoria" el pasado.
    t_ent = sorted(t for t, v in fs.items() if v == "entrena")
    val = t_ent[-1] if t_ent else None
    st_e = Estado(cfg, BASE, sd)

    def ll_val(pp):
        s = n = 0
        for x, w, g in zip(filas, res, juegos):
            if g["temporada"] != val:
                continue
            s += ll(st_e.prob(x, pp), w)
            n += 1
        return s / n if n else None
    ref = ll_val(pr)
    if ref is not None:
        mejor_e = (dict(pr), ref)
        for cm in C_MICRO:
            for cs in C_SEDE:
                if cm == 0 and cs == 0:
                    continue
                pr2 = dict(pr, c_micro=cm, c_sede=cs)
                v = ll_val(pr2)
                if v is not None and v < mejor_e[1]:
                    mejor_e = (pr2, v)
        if mejor_e[1] < ref - MEJORA_MINIMA:
            pr = mejor_e[0]
    st_b = Estado(cfg, BASE, sd)
    prueba_m, prueba_b, prueba_l = [], [], []
    for x, xb, w, f in zip(filas, base_filas, res, fase):
        if f != "prueba":
            continue
        prueba_m.append((st_b.prob(x, pr), w))
        prueba_b.append((st_b.prob(xb, BASE), w))
        prueba_l.append((1.0, w))
    mm, mb = medir(prueba_m), medir(prueba_b)
    activo = bool(mm and mb and mm["logloss"] < mb["logloss"])
    if not activo and (pr["c_micro"] or pr["c_sede"]):
        # si con las escalas cortas no supera al Elo basico, se prueba el motor sin ellas
        pr_sin = dict(pr, c_micro=0.0, c_sede=0.0)
        m2 = medir([(st_b.prob(x, pr_sin), w) for x, w, f in zip(filas, res, fase) if f == "prueba"])
        if m2 and mb and m2["logloss"] < mb["logloss"]:
            pr, mm, activo = pr_sin, m2, True
    inf = {"activo": activo, "params": pr, "sd": round(sd, 3), "motor": mm, "elo_basico": mb,
           "escalas": {"temporada": True, "ultimos10": pr["c_forma"] > 0, "ultimos3": pr["c_micro"] > 0,
                       "casa_fuera": pr["c_sede"] > 0, "descanso": pr["c_desc"] > 0},
           "local": {"n": len(prueba_l), "acierto": round(sum(1 for _, w in prueba_l if w) / float(len(prueba_l)), 4)}
           if prueba_l else None,
           "temporadas_prueba": sorted(t for t, v in fs.items() if v == "prueba")}
    return (pr if activo else dict(BASE)), inf


def recorrido_final(juegos, cfg, params):
    """Recorre todo con los ajustes elegidos. Devuelve (estado, evaluados de PRUEBA, balances)."""
    fs = fases(juegos)
    sd = desviacion(juegos)
    st = Estado(cfg, params, sd)
    ev, bal, temp_bal = [], {}, None
    for g in juegos:
        st.nueva_temporada(g["temporada"])
        if g["temporada"] != temp_bal:
            bal, temp_bal = {}, g["temporada"]
        if fs.get(g["temporada"]) == "prueba":
            p = st.prob_partido(g["local"], g["visitante"], g["neutral"], fecha(g["fecha"]))
            ev.append({"g": g, "p": p, "w": g["pl"] > g["pv"], "bl": list(bal.get(g["local"], [0, 0])),
                       "bv": list(bal.get(g["visitante"], [0, 0]))})
        st.actualizar(g)
        gl = g["pl"] > g["pv"]
        bal.setdefault(g["local"], [0, 0])[0 if gl else 1] += 1
        bal.setdefault(g["visitante"], [0, 0])[1 if gl else 0] += 1
    return st, ev, bal
