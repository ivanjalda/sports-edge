# -*- coding: utf-8 -*-
"""Sports Edge - Backtest honesto (solo libreria estandar).
Para cada partido terminado, predice usando SOLO partidos anteriores y compara con la realidad."""
import math
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine  # reutiliza exactamente el mismo modelo que las predicciones en directo


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / float(n)
    d = 1 + z * z / n
    c = p + z * z / (2.0 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4.0 * n * n))
    return [round((c - m) / d, 4), round((c + m) / d, 4)]


def cargar(codigo):
    datos = engine.pedir("/competitions/%s/matches" % codigo)
    out = []
    for m in datos.get("matches", []):
        if m.get("status") != "FINISHED":
            continue
        sc = m.get("score") or {}
        ft = sc.get("fullTime") or {}
        ht = sc.get("halfTime") or {}
        if ft.get("home") is None or ft.get("away") is None:
            continue
        try:
            f = engine.parse_fecha(m["utcDate"])
        except Exception:
            continue
        out.append({"f": f, "iso": m["utcDate"],
                    "h": m["homeTeam"]["id"], "a": m["awayTeam"]["id"],
                    "hn": m["homeTeam"].get("name"), "an": m["awayTeam"].get("name"),
                    "gh": ft["home"], "ga": ft["away"],
                    "hh": ht.get("home"), "ha": ht.get("away")})
    out.sort(key=lambda x: x["f"])
    return out


def recorrer(liga, ms):
    res = []
    for i, m in enumerate(ms):
        previos = [(x["h"], x["a"], x["gh"], x["ga"], x["hh"], x["ha"])
                   for x in ms[:i] if x["f"] < m["f"]]
        fz = engine.calcular_fuerzas(previos)
        if fz is None:
            continue
        pred = engine.predecir(fz, m["h"], m["a"])
        if pred is None:
            continue
        mk = pred["mercados"]
        res.append({
            "liga": liga, "fecha": m["iso"], "local": m["hn"], "visitante": m["an"],
            "marcador": "%d-%d" % (m["gh"], m["ga"]),
            "res": engine.signo(m["gh"], m["ga"]),
            "p1": pred["p_local"], "px": pred["p_empate"], "p2": pred["p_visitante"],
            "o25": mk["over25"], "bt": mk["btts"],
            "ro": (m["gh"] + m["ga"]) >= 3,
            "rb": (m["gh"] > 0 and m["ga"] > 0),
        })
    return res


def mejor(r):
    probs = {"1": r["p1"], "X": r["px"], "2": r["p2"]}
    k = max(probs, key=probs.get)
    return k, probs[k]


def resumen(rs):
    n = len(rs)
    if n == 0:
        return None
    hit = 0
    brier = 0.0
    for r in rs:
        k, _ = mejor(r)
        if k == r["res"]:
            hit += 1
        probs = {"1": r["p1"], "X": r["px"], "2": r["p2"]}
        brier += sum((probs[x] - (1.0 if x == r["res"] else 0.0)) ** 2 for x in probs)
    local = sum(1 for r in rs if r["res"] == "1")
    o_ok = sum(1 for r in rs if (r["o25"] >= 0.5) == r["ro"])
    b_ok = sum(1 for r in rs if (r["bt"] >= 0.5) == r["rb"])
    return {"n": n, "aciertos": hit, "acierto": round(hit / float(n), 4),
            "ic": wilson(hit, n), "brier": round(brier / n, 4),
            "brier_azar": 0.6667, "siempre_local": round(local / float(n), 4),
            "over25": round(o_ok / float(n), 4), "btts": round(b_ok / float(n), 4)}


def tramos(rs):
    out = []
    for th in (0.45, 0.55, 0.65):
        sub = [r for r in rs if mejor(r)[1] >= th]
        if not sub:
            out.append({"min": th, "n": 0, "conf": None, "acierto": None, "ic": None})
            continue
        h = sum(1 for r in sub if mejor(r)[0] == r["res"])
        conf = sum(mejor(r)[1] for r in sub) / len(sub)
        out.append({"min": th, "n": len(sub), "conf": round(conf, 4),
                    "acierto": round(h / float(len(sub)), 4), "ic": wilson(h, len(sub))})
    return out


def calibracion(rs):
    bins = [[0, 0.0, 0] for _ in range(10)]  # n, suma_prob, aciertos
    for r in rs:
        for key, k in (("p1", "1"), ("px", "X"), ("p2", "2")):
            p = r[key]
            b = min(int(p * 10), 9)
            bins[b][0] += 1
            bins[b][1] += p
            bins[b][2] += 1 if r["res"] == k else 0
    out = []
    for i, (n, sp, h) in enumerate(bins):
        out.append({"desde": i * 10, "hasta": i * 10 + 10, "n": n,
                    "prometido": round(sp / n, 4) if n else None,
                    "real": round(h / float(n), 4) if n else None})
    return out


def main():
    if not engine.KEY:
        print("ERROR: falta FOOTBALL_DATA_KEY")
        sys.exit(1)
    os.makedirs(engine.DATA, exist_ok=True)
    time.sleep(10)  # respeta el limite gratuito tras el paso anterior
    todos = []
    por_liga = {}
    errores = 0
    for i, (codigo, nombre) in enumerate(engine.LIGAS.items()):
        if i > 0:
            time.sleep(7)
        try:
            ms = cargar(codigo)
        except Exception as e:
            print("Aviso: no se pudo leer %s (%s)" % (codigo, e))
            errores += 1
            continue
        rs = recorrer(nombre, ms)
        por_liga[nombre] = resumen(rs)
        todos.extend(rs)
        print("%s: %d partidos terminados, %d evaluados" % (nombre, len(ms), len(rs)))

    if errores == len(engine.LIGAS) or not todos:
        print("ERROR: sin datos suficientes. No se cambia nada.")
        sys.exit(1)

    todos.sort(key=lambda r: r["fecha"])
    ej = []
    for r in reversed(todos[-25:]):
        k, p = mejor(r)
        ej.append({"liga": r["liga"], "fecha": r["fecha"], "local": r["local"],
                   "visitante": r["visitante"], "marcador": r["marcador"],
                   "pick": k, "pp": round(p, 4), "res": r["res"]})

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    engine.guardar_json("backtest.json", {
        "actualizado": stamp, "total": resumen(todos), "ligas": por_liga,
        "tramos": tramos(todos), "calibracion": calibracion(todos), "ejemplos": ej})
    t = resumen(todos)
    print("OK backtest: %d partidos, acierto %.1f%%, Brier %.3f" % (t["n"], t["acierto"] * 100, t["brier"]))


if __name__ == "__main__":
    main()
