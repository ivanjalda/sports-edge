# -*- coding: utf-8 -*-
"""Sports Edge - MOTOR PROPIO para carreras (Formula 1 y MotoGP). Solo libreria estandar.

Que mide:
  - Fuerza de cada PILOTO y de cada EQUIPO (coche/moto). Se actualiza despues de cada carrera
    comparando a cada piloto con todos los que acabaron detras o delante (como un Elo por parejas).
    Las carreras al sprint cuentan la mitad. Entre temporadas la fuerza se acerca a la media
    (el piloto conserva mas que el coche, porque el coche cambia mucho de un ano a otro).
  - Posicion de salida (parrilla), cuando ya se conoce la clasificacion.
  - Abandonos: cada piloto puede no acabar, con la tasa real de abandonos de las temporadas anteriores.
Con todo eso se simulan miles de carreras y se cuenta cuantas veces gana cada piloto, sube al podio
o entra en los puntos.

Como se elige (sin trampas): 1a temporada para calentar, las intermedias para ENTRENAR (elegir ajustes)
y las 2 mas recientes de PRUEBA (carreras no vistas). Cada carrera se predice solo con lo anterior."""
import math
import random

K_OPC = [4.0, 8.0, 16.0]          # cuanto se mueve la fuerza tras cada carrera
W_EQUIPO = [0.5, 1.0, 2.0]        # peso del equipo frente al piloto
T_OPC = [20.0, 30.0, 50.0, 80.0, 120.0, 180.0, 260.0]  # "temperatura": cuanto se parecen las probabilidades al reparto igualado
G_OPC = [0.0, 20.0, 40.0, 70.0, 110.0, 160.0, 230.0]  # peso de la posicion de salida
ESCALA = 50.0                     # escala fija de la comparacion por parejas al actualizar
REV_PILOTO = 0.85                 # parte de la fuerza del piloto que se conserva al cambiar de temporada
REV_EQUIPO = 0.55                 # parte de la fuerza del equipo que se conserva al cambiar de temporada
SIMULACIONES = 6000


def sig(x):
    if x < -60:
        return 0.0
    if x > 60:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


class Estado(object):
    def __init__(self, k, w):
        self.k, self.w = k, w
        self.rp, self.re = {}, {}
        self.temp = None

    def nueva_temporada(self, t):
        if self.temp is not None and t != self.temp:
            for d in self.rp:
                self.rp[d] *= REV_PILOTO
            for e in self.re:
                self.re[e] *= REV_EQUIPO
        self.temp = t

    def fuerza(self, piloto, equipo):
        return self.rp.get(piloto, -10.0) + self.w * self.re.get(equipo, 0.0)

    def actualizar(self, carrera):
        """Comparacion por parejas entre los que terminaron (los abandonos no cuentan: suelen ser averias)."""
        acab = sorted([r for r in carrera["res"] if r.get("pos")], key=lambda r: r["pos"])
        n = len(acab)
        if n < 2:
            return
        f = [self.fuerza(r["id"], r["eq"]) for r in acab]
        k = self.k * (0.5 if carrera.get("sprint") else 1.0)
        delta = [0.0] * n
        for i in range(n):
            for j in range(i + 1, n):
                e = sig((f[i] - f[j]) / ESCALA)
                c = k * (1.0 - e)
                delta[i] += c
                delta[j] -= c
        por_eq = {}
        for r, d in zip(acab, delta):
            d = d / (n - 1) * 10.0
            self.rp[r["id"]] = self.rp.get(r["id"], -10.0) + d
            por_eq.setdefault(r["eq"], []).append(d)
        for e, ds in por_eq.items():
            self.re[e] = self.re.get(e, 0.0) + sum(ds) / len(ds)


def rasgo_parrilla(g):
    return -math.log(g) if g and g > 0 else None


def prob_ganador(filas, t, cg):
    """Probabilidad de ganar (reparto tipo Plackett-Luce) a partir de la fuerza y la parrilla."""
    xs = []
    for f in filas:
        s = f["f"]
        pg = rasgo_parrilla(f.get("grid"))
        if cg and pg is not None:
            s += cg * pg
        elif cg:
            s += cg * -math.log(22)   # sin parrilla conocida (salida desde el pit lane): como el ultimo
        xs.append(s / t)
    m = max(xs)
    ex = [math.exp(x - m) for x in xs]
    tot = sum(ex)
    return [e / tot for e in ex]


def fases(carreras):
    temps = sorted(set(c["temporada"] for c in carreras))
    if len(temps) < 4:
        return {}
    out = {temps[0]: "calentar"}
    for t in temps[1:-2]:
        out[t] = "entrena"
    for t in temps[-2:]:
        out[t] = "prueba"
    return out


def recorrer(carreras, k, w):
    """Recorre todas las carreras; antes de cada carrera principal guarda la fuerza de cada participante."""
    st = Estado(k, w)
    previas = []
    for c in carreras:
        st.nueva_temporada(c["temporada"])
        if not c.get("sprint"):
            filas = [{"id": r["id"], "eq": r["eq"], "f": st.fuerza(r["id"], r["eq"]), "grid": r.get("grid"),
                      "pos": r.get("pos")} for r in c["res"]]
            previas.append((c, filas))
        st.actualizar(c)
    return st, previas


def ganador(filas):
    for i, f in enumerate(filas):
        if f.get("pos") == 1:
            return i
    return None


def medir(previas, fs, fase, t, cg):
    s = n = 0
    for c, filas in previas:
        if fs.get(c["temporada"]) != fase:
            continue
        gi = ganador(filas)
        if gi is None:
            continue
        if cg and not any(f.get("grid") for f in filas):
            continue
        p = prob_ganador(filas, t, cg)
        s += -math.log(max(p[gi], 1e-9))
        n += 1
    return (s / n, n) if n else (None, 0)


def informe(previas, fs, t, cg, con_parrilla):
    """Acierto en la PRUEBA: el favorito gana, podio, y probabilidad media que dimos al ganador real."""
    n = gana = podio_ok = 0
    ll = 0.0
    pole = pole_n = 0
    for c, filas in previas:
        if fs.get(c["temporada"]) != "prueba":
            continue
        gi = ganador(filas)
        if gi is None:
            continue
        tiene_grid = any(f.get("grid") for f in filas)
        if con_parrilla and not tiene_grid:
            continue
        p = prob_ganador(filas, t, cg if con_parrilla else 0.0)
        orden = sorted(range(len(filas)), key=lambda i: -p[i])
        n += 1
        gana += 1 if orden[0] == gi else 0
        ll += -math.log(max(p[gi], 1e-9))
        real_podio = set(i for i, f in enumerate(filas) if f.get("pos") in (1, 2, 3))
        podio_ok += len(real_podio & set(orden[:3]))
        if tiene_grid:
            pole_n += 1
            pole += 1 if filas[gi].get("grid") == 1 else 0
    if not n:
        return None
    return {"carreras": n, "favorito_gana": round(gana / float(n), 4), "logloss": round(ll / n, 4),
            "podio": round(podio_ok / (3.0 * n), 4),
            "pole_gana": round(pole / float(pole_n), 4) if pole_n else None}


def ajustar(carreras):
    """Elige K, peso del equipo, temperatura y peso de la parrilla con ENTRENAMIENTO. Mide en PRUEBA."""
    fs = fases(carreras)
    if not fs:
        return None
    mejor = None
    for k in K_OPC:
        for w in W_EQUIPO:
            st, previas = recorrer(carreras, k, w)
            for t in T_OPC:
                v, n = medir(previas, fs, "entrena", t, 0.0)
                if v is not None and (mejor is None or v < mejor[0]):
                    mejor = (v, k, w, t, previas)
    if mejor is None:
        return None
    _, k, w, t, previas = mejor
    mejor_g = None
    for t2 in T_OPC:
        for cg in G_OPC:
            v, n = medir(previas, fs, "entrena", t2, cg)
            if v is not None and (mejor_g is None or v < mejor_g[0]):
                mejor_g = (v, t2, cg)
    t_g, cg = (mejor_g[1], mejor_g[2]) if mejor_g else (t, 0.0)
    n_pil = [len(f) for c, f in previas if fs.get(c["temporada"]) == "prueba"]
    media_pil = sum(n_pil) / float(len(n_pil)) if n_pil else 20.0
    return {"k": k, "w": w, "t": t, "t_grid": t_g, "c_grid": cg,
            "prueba_previa": informe(previas, fs, t, 0.0, False),
            "prueba_parrilla": informe(previas, fs, t_g, cg, True),
            "azar_logloss": round(math.log(media_pil), 4),
            "temporadas_prueba": sorted(x for x, v in fs.items() if v == "prueba")}


def tasa_abandono(carreras, ultimas=60):
    princ = [c for c in carreras if not c.get("sprint")][-ultimas:]
    tot = sum(len(c["res"]) for c in princ)
    ab = sum(1 for c in princ for r in c["res"] if not r.get("pos"))
    return (ab / float(tot)) if tot else 0.1


def simular(filas, t, cg, abandono, n=SIMULACIONES, semilla=7):
    """Simula la carrera n veces (ruido de Gumbel = reparto Plackett-Luce, mas abandonos al azar).
    Devuelve por piloto: P(ganar), P(podio), P(puntos = top 10)."""
    rnd = random.Random(semilla)
    base = []
    for f in filas:
        s = f["f"]
        pg = rasgo_parrilla(f.get("grid"))
        if cg:
            s += cg * (pg if pg is not None else -math.log(22))
        base.append(s / t)
    m = len(filas)
    gana, podio, puntos = [0] * m, [0] * m, [0] * m
    for _ in range(n):
        val = []
        for i in range(m):
            u = rnd.random()
            g = -math.log(-math.log(u)) if 0 < u < 1 else 0.0
            v = base[i] + g
            if rnd.random() < abandono:
                v -= 1e6   # no termina
            val.append((v, i))
        val.sort(reverse=True)
        for pos, (v, i) in enumerate(val):
            if v < -1e5:
                break
            if pos == 0:
                gana[i] += 1
            if pos < 3:
                podio[i] += 1
            if pos < 10:
                puntos[i] += 1
    return [(gana[i] / float(n), podio[i] / float(n), puntos[i] / float(n)) for i in range(m)]
