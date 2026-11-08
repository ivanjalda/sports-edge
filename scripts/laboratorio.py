# -*- coding: utf-8 -*-
"""Sports Edge - Laboratorio del modelo (solo libreria estandar).
Prueba variantes SIN tocar las predicciones en directo.
Elige con el 60% mas antiguo y confirma con el 40% mas reciente."""
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine
import backtest

HALF = [None, 60, 120]     # vida media (dias) del peso de cada partido; None = todos pesan igual
PRIORS = [2, 4, 8]         # suavizado hacia la media de la liga
RHOS = [0.0, -0.1]         # correccion Dixon-Coles para marcadores bajos
BASE = (None, 4, 0.0)      # el modelo que usamos hoy
MIN_P = engine.MIN_PARTIDOS


def fuerzas(prev, ref, half, prior):
    sw = sh = sa = 0.0
    filas = []
    for f, h, a, gh, ga in prev:
        d = (ref - f).total_seconds() / 86400.0
        w = 1.0 if half is None else 0.5 ** (max(d, 0.0) / half)
        filas.append((w, h, a, gh, ga))
        sw += w
        sh += w * gh
        sa += w * ga
    if sw <= 0:
        return None
    mh = sh / sw
    ma = sa / sw
    media = (mh + ma) / 2
    if media <= 0:
        return None
    eq = {}
    for w, h, a, gh, ga in filas:
        for tid, fv, cv in ((h, gh, ga), (a, ga, gh)):
            e = eq.setdefault(tid, [0, 0.0, 0.0, 0.0])
            e[0] += 1
            e[1] += w
            e[2] += w * fv
            e[3] += w * cv
    res = {}
    for tid, (pj, ws, f, c) in eq.items():
        res[tid] = ((f + prior * media) / (ws + prior) / media,
                    (c + prior * media) / (ws + prior) / media, pj)
    return mh, ma, res


def probs(fz, h, a, rho):
    mh, ma, eq = fz
    if h not in eq or a not in eq:
        return None
    if eq[h][2] < MIN_P or eq[a][2] < MIN_P:
        return None
    lh = mh * eq[h][0] * eq[a][1]
    la = ma * eq[a][0] * eq[h][1]
    g = engine.rejilla(lh, la)
    if rho != 0.0:
        g[0][0] *= max(1 - lh * la * rho, 0.0)
        g[0][1] *= max(1 + lh * rho, 0.0)
        g[1][0] *= max(1 + la * rho, 0.0)
        g[1][1] *= max(1 - rho, 0.0)
    ph = pe = pa = 0.0
    for i in range(engine.MAX_GOLES + 1):
        for j in range(engine.MAX_GOLES + 1):
            if i > j:
                ph += g[i][j]
            elif i == j:
                pe += g[i][j]
            else:
                pa += g[i][j]
    s = ph + pe + pa
    return {"1": ph / s, "X": pe / s, "2": pa / s}


def evaluar_liga(ms, out):
    for i, m in enumerate(ms):
        prev = [(x["f"], x["h"], x["a"], x["gh"], x["ga"]) for x in ms[:i] if x["f"] < m["f"]]
        if not prev:
            continue
        real = engine.signo(m["gh"], m["ga"])
        for half in HALF:
            for prior in PRIORS:
                fz = fuerzas(prev, m["f"], half, prior)
                if fz is None:
                    continue
                for rho in RHOS:
                    p = probs(fz, m["h"], m["a"], rho)
                    if p is None:
                        continue
                    brier = sum((p[k] - (1.0 if k == real else 0.0)) ** 2 for k in p)
                    hit = 1 if max(p, key=p.get) == real else 0
                    out.setdefault((half, prior, rho), []).append((m["iso"], brier, hit))


def medir(filas):
    n = len(filas)
    if n == 0:
        return None, None
    return (round(sum(f[1] for f in filas) / n, 4), round(sum(f[2] for f in filas) / float(n), 4))


def nombre(k):
    return "peso reciente=%s dias, suavizado=%d, bajos=%s" % (
        "no" if k[0] is None else k[0], k[1], "si" if k[2] != 0.0 else "no")


def main():
    if not engine.KEY:
        print("ERROR: falta FOOTBALL_DATA_KEY")
        sys.exit(1)
    os.makedirs(engine.DATA, exist_ok=True)
    time.sleep(10)
    out = {}
    errores = 0
    for i, (codigo, nombre_liga) in enumerate(engine.LIGAS.items()):
        if i > 0:
            time.sleep(7)
        try:
            ms = backtest.cargar(codigo)
        except Exception as e:
            print("Aviso: no se pudo leer %s (%s)" % (codigo, e))
            errores += 1
            continue
        evaluar_liga(ms, out)
    if errores == len(engine.LIGAS) or BASE not in out:
        print("ERROR: sin datos suficientes. No se cambia nada.")
        sys.exit(1)

    resultados = []
    for k, filas in out.items():
        filas.sort(key=lambda x: x[0])
        corte = int(len(filas) * 0.6)
        tb, ta = medir(filas[:corte])
        vb, va = medir(filas[corte:])
        resultados.append({"clave": k, "nombre": nombre(k), "n": len(filas), "n_train": corte,
                           "train_brier": tb, "train_acierto": ta,
                           "valid_brier": vb, "valid_acierto": va})
    resultados.sort(key=lambda r: r["train_brier"])

    base = [r for r in resultados if r["clave"] == BASE][0]
    mejor = resultados[0]
    print("Partidos comparados: %d (entrenamiento %d, validacion %d)" %
          (base["n"], base["n_train"], base["n"] - base["n_train"]))
    print("--- Top 5 (elegidos con entrenamiento) ---")
    for r in resultados[:5]:
        print("%s | train Brier %.4f acierto %.1f%% | valid Brier %.4f acierto %.1f%%" %
              (r["nombre"], r["train_brier"], r["train_acierto"] * 100, r["valid_brier"], r["valid_acierto"] * 100))
    print("--- Modelo actual ---")
    print("%s | train Brier %.4f acierto %.1f%% | valid Brier %.4f acierto %.1f%%" %
          (base["nombre"], base["train_brier"], base["train_acierto"] * 100, base["valid_brier"], base["valid_acierto"] * 100))
    mejora = base["valid_brier"] - mejor["valid_brier"]
    print("RESULTADO: el mejor elegido %s el actual en validacion (diferencia de Brier %.4f)" %
          ("MEJORA a" if mejora > 0 else "NO mejora a", mejora))

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    for r in resultados:
        r["clave"] = list(r["clave"])
    engine.guardar_json("laboratorio.json", {"actualizado": stamp, "variantes": resultados,
                                             "base": list(BASE), "mejor": mejor["nombre"]})


if __name__ == "__main__":
    main()
