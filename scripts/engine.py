# -*- coding: utf-8 -*-
"""Sports Edge - Motor de futbol (solo libreria estandar)."""
import json
import math
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import motor_futbol
except Exception as _e:   # si falta el motor propio se sigue con el modelo anterior
    motor_futbol = None
    print("Aviso: motor propio no disponible (%s)" % _e)

API = "https://api.football-data.org/v4"
KEY = os.environ.get("FOOTBALL_DATA_KEY", "").strip()
DATA = "data"

LIGAS = {
    "PL": "Premier League",
    "PD": "LaLiga",
    "SA": "Serie A",
    "BL1": "Bundesliga",
    "FL1": "Ligue 1",
    "PPL": "Primeira Liga",
    "DED": "Eredivisie",
    "ELC": "Championship",
    "BSA": "Brasileirão",
}
# Ligas que no estan en football-data.org: calendario y resultados desde ESPN, prediccion con el motor propio
LIGAS_ESPN = {"ARG": ("Liga Profesional", "soccer/arg.1"), "USA": ("MLS", "soccer/usa.1")}
API_A_CSV = {"PL": "E0", "PD": "SP1", "SA": "I1", "BL1": "D1", "FL1": "F1", "PPL": "P1", "DED": "N1",
             "ELC": "E1", "BSA": "BRA"}

MIN_PARTIDOS = 5          # minimo de partidos por equipo para predecir
PRIOR = 4                 # suaviza equipos con pocos partidos hacia la media
MAX_GOLES = 10            # rejilla de goles del modelo Poisson
DIAS = 7                  # dias hacia delante que se predicen
MIN_GOLES_JUGADOR = 2     # minimo de goles para mostrar a un jugador
MIN_PARTIDOS_1T = 30      # minimo de partidos con dato de descanso


def ahora():
    return datetime.now(timezone.utc)


def parse_fecha(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def parse_iso(s):
    s = str(s).replace("Z", "")
    fmt = "%Y-%m-%dT%H:%M:%S" if len(s) >= 19 else "%Y-%m-%dT%H:%M"
    return datetime.strptime(s[:19] if len(s) >= 19 else s[:16], fmt).replace(tzinfo=timezone.utc)


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


def rejilla(lh, la):
    return [[poisson(i, lh) * poisson(j, la) for j in range(MAX_GOLES + 1)]
            for i in range(MAX_GOLES + 1)]


def calcular_fuerzas(terminados):
    """terminados: (id_local, id_visit, gol_local, gol_visit, desc_local, desc_visit)."""
    n = len(terminados)
    if n == 0:
        return None
    media_h = sum(t[2] for t in terminados) / n
    media_a = sum(t[3] for t in terminados) / n
    media = (media_h + media_a) / 2
    if media <= 0:
        return None
    eq = {}
    g1 = 0
    gt = 0
    n1 = 0
    for h, a, gh, ga, hh, ha in terminados:
        if hh is not None and ha is not None:
            g1 += hh + ha
            gt += gh + ga
            n1 += 1
        for tid, f, c in ((h, gh, ga), (a, ga, gh)):
            e = eq.setdefault(tid, {"pj": 0, "f": 0, "c": 0})
            e["pj"] += 1
            e["f"] += f
            e["c"] += c
    res = {}
    for tid, e in eq.items():
        ataque = (e["f"] + PRIOR * media) / (e["pj"] + PRIOR) / media
        defensa = (e["c"] + PRIOR * media) / (e["pj"] + PRIOR) / media
        res[tid] = (ataque, defensa, e["pj"], e["f"])
    frac = (g1 / gt) if (n1 >= MIN_PARTIDOS_1T and gt > 0) else None
    return media_h, media_a, res, frac


def mercados(lh, la, frac):
    g = rejilla(lh, la)
    tot = sum(sum(f) for f in g)
    o15 = o25 = o35 = btts = 0.0
    mejor = (0, 0, 0.0)
    for i in range(MAX_GOLES + 1):
        for j in range(MAX_GOLES + 1):
            p = g[i][j] / tot
            if i + j >= 2:
                o15 += p
            if i + j >= 3:
                o25 += p
            if i + j >= 4:
                o35 += p
            if i > 0 and j > 0:
                btts += p
            if p > mejor[2]:
                mejor = (i, j, p)
    m = {"over15": round(o15, 4), "over25": round(o25, 4), "over35": round(o35, 4),
         "btts": round(btts, 4), "marcador": "%d-%d" % (mejor[0], mejor[1]),
         "p_marcador": round(mejor[2], 4),
         "ht_local": None, "ht_empate": None, "ht_visitante": None, "ht_gol": None}
    if frac is not None:
        l1h = lh * frac
        l1a = la * frac
        g1 = rejilla(l1h, l1a)
        t1 = sum(sum(f) for f in g1)
        a = b = c = 0.0
        for i in range(MAX_GOLES + 1):
            for j in range(MAX_GOLES + 1):
                p = g1[i][j] / t1
                if i > j:
                    a += p
                elif i == j:
                    b += p
                else:
                    c += p
        m["ht_local"] = round(a, 4)
        m["ht_empate"] = round(b, 4)
        m["ht_visitante"] = round(c, 4)
        m["ht_gol"] = round(1 - math.exp(-(l1h + l1a)), 4)
    return m


def predecir(fz, h, a):
    media_h, media_a, eq, frac = fz
    if h not in eq or a not in eq:
        return None
    if eq[h][2] < MIN_PARTIDOS or eq[a][2] < MIN_PARTIDOS:
        return None
    lh = media_h * eq[h][0] * eq[a][1]
    la = media_a * eq[a][0] * eq[h][1]
    g = rejilla(lh, la)
    ph = pe = pa = 0.0
    for i in range(MAX_GOLES + 1):
        for j in range(MAX_GOLES + 1):
            p = g[i][j]
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
        "mercados": mercados(lh, la, frac),
    }


def goleadores_equipo(scorers, tid, goles_equipo, lam):
    out = []
    if not goles_equipo or goles_equipo <= 0:
        return out
    for s in scorers.get(tid, []):
        if s["g"] < MIN_GOLES_JUGADOR:
            continue
        share = min(s["g"] / float(goles_equipo), 1.0)
        out.append({"n": s["n"], "g": s["g"], "p": round(1 - math.exp(-share * lam), 4)})
    out.sort(key=lambda x: -x["p"])
    return out[:3]


def anadir_goleadores(reg, fz, scorers, h, a):
    eq = fz[2]
    gh = eq[h][3] if h in eq else None
    ga = eq[a][3] if a in eq else None
    reg["goleadores"] = {
        "local": goleadores_equipo(scorers, h, gh, reg["xg_local"]),
        "visitante": goleadores_equipo(scorers, a, ga, reg["xg_visitante"]),
    }


def signo(gh, ga):
    if gh > ga:
        return "1"
    if gh == ga:
        return "X"
    return "2"


def metricas(res):
    if not res:
        return None, None
    aciertos = 0
    brier = 0.0
    for p in res:
        probs = {"1": p["p_local"], "X": p["p_empate"], "2": p["p_visitante"]}
        if max(probs, key=probs.get) == p["resultado"]:
            aciertos += 1
        brier += sum((probs[k] - (1.0 if k == p["resultado"] else 0.0)) ** 2 for k in probs)
    return round(aciertos / len(res), 4), round(brier / len(res), 4)


def main():
    if not KEY:
        print("ERROR: falta el secret FOOTBALL_DATA_KEY")
        sys.exit(1)
    os.makedirs(DATA, exist_ok=True)

    MOT = None
    if motor_futbol is not None:
        try:
            MOT = motor_futbol.preparar()
        except Exception as e:
            print("Aviso: el motor propio fallo (%s). Se usa el modelo anterior." % e)
            MOT = None
    usar_motor = bool(MOT and MOT.activo)
    n_motor = n_base = 0

    hist = leer_json("historial.json", {"predicciones": []})
    lista = hist.get("predicciones", [])
    por_id = {p["id"]: p for p in lista}
    t_ahora = ahora()
    limite = t_ahora + timedelta(days=DIAS)
    proximos = []
    errores = 0
    nuevas = 0
    resueltas = 0
    ampliadas = 0

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
                sc = m.get("score") or {}
                ft = sc.get("fullTime") or {}
                ht = sc.get("halfTime") or {}
                if ft.get("home") is not None and ft.get("away") is not None:
                    terminados.append((m["homeTeam"]["id"], m["awayTeam"]["id"],
                                       ft["home"], ft["away"], ht.get("home"), ht.get("away")))
                    p = por_id.get(m["id"])
                    if p is not None and p.get("resultado") is None:
                        p["resultado"] = signo(ft["home"], ft["away"])
                        p["marcador"] = "%d-%d" % (ft["home"], ft["away"])
                        resueltas += 1

        fz = calcular_fuerzas(terminados)
        nombres = {}
        clave_csv = API_A_CSV.get(codigo)
        if usar_motor and clave_csv:
            jugados = []
            for m in ms:
                ft = ((m.get("score") or {}).get("fullTime") or {})
                if m.get("status") == "FINISHED" and ft.get("home") is not None:
                    try:
                        jugados.append((parse_fecha(m["utcDate"]), m["homeTeam"].get("name"), m["awayTeam"].get("name"),
                                        ft["home"], ft["away"]))
                    except Exception:
                        pass
            nombres = MOT.mapear(clave_csv, jugados)
            print("%s: %d equipos emparejados con el historico del motor" % (nombre, len(nombres)))

        # Goleadores de la liga
        time.sleep(7)
        scorers = {}
        sc_ok = False
        try:
            sd = pedir("/competitions/%s/scorers?limit=60" % codigo)
            for s in sd.get("scorers", []):
                tid = (s.get("team") or {}).get("id")
                nom = (s.get("player") or {}).get("name")
                g = s.get("goals") or 0
                if tid is None or not nom:
                    continue
                scorers.setdefault(tid, []).append({"n": nom, "g": g})
            sc_ok = True
        except Exception as e:
            print("Aviso: sin goleadores de %s (%s)" % (codigo, e))

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
            p = por_id.get(m["id"])
            if fz is None and not (p is None and nombres):
                continue
            if p is None:
                pred = None
                if nombres.get(h.get("name")) and nombres.get(a.get("name")):
                    pred = MOT.predecir(clave_csv, nombres[h["name"]], nombres[a["name"]])
                if pred is None and fz is not None:
                    pred = predecir(fz, h["id"], a["id"])
                    if pred is not None:
                        pred["modelo"] = "base"
                if pred is None:
                    continue  # Sin datos suficientes: no se inventa nada
                if pred.get("modelo") == "SE":
                    n_motor += 1
                else:
                    n_base += 1
                reg = {"id": m["id"], "liga": nombre, "fecha": m["utcDate"],
                       "local": h.get("name"), "visitante": a.get("name"),
                       "creada": t_ahora.strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "resultado": None, "marcador": None}
                reg.update(pred)
                if sc_ok and fz is not None:
                    anadir_goleadores(reg, fz, scorers, h["id"], a["id"])
                lista.append(reg)
                por_id[m["id"]] = reg
                nuevas += 1
            elif p.get("resultado") is None:
                # Partido aun no jugado: se completan mercados nuevos sin tocar el 1X2 guardado
                if "mercados" not in p and fz is not None:
                    p["mercados"] = mercados(p["xg_local"], p["xg_visitante"], fz[3])
                    ampliadas += 1
                if sc_ok and "goleadores" not in p and fz is not None:
                    anadir_goleadores(p, fz, scorers, h["id"], a["id"])

    # ---- Ligas desde ESPN (Argentina y MLS): solo con el motor propio
    if usar_motor:
        try:
            import equipos as _eq
            for clave, (nombre, ruta) in LIGAS_ESPN.items():
                try:
                    evs = _eq.pedir_bloque(ruta, t_ahora - timedelta(days=45), t_ahora + timedelta(days=DIAS))
                except Exception as e:
                    print("Aviso: %s no disponible en ESPN (%s)" % (nombre, e))
                    continue
                jugados = []
                for g in evs:
                    if g["terminado"] and g["pl"] is not None and g["pv"] is not None:
                        jugados.append((parse_iso(g["fecha"]), g["local"], g["visitante"], g["pl"], g["pv"]))
                        p = por_id.get("espn-" + g["id"])
                        if p is not None and p.get("resultado") is None:
                            p["resultado"] = signo(g["pl"], g["pv"])
                            p["marcador"] = "%d-%d" % (g["pl"], g["pv"])
                            resueltas += 1
                nombres = MOT.mapear(clave, jugados)
                print("%s: %d partidos leidos de ESPN, %d equipos emparejados" % (nombre, len(evs), len(nombres)))
                for g in evs:
                    if g["terminado"]:
                        continue
                    fecha = parse_iso(g["fecha"])
                    if fecha <= t_ahora or fecha > limite:
                        continue
                    fiso = fecha.strftime("%Y-%m-%dT%H:%M:%SZ")
                    proximos.append({"id": "espn-" + g["id"], "liga": nombre, "fecha": fiso,
                                     "local": g["local"], "visitante": g["visitante"]})
                    if ("espn-" + g["id"]) in por_id:
                        continue
                    hn, an = nombres.get(g["local"]), nombres.get(g["visitante"])
                    pred = MOT.predecir(clave, hn, an) if hn and an else None
                    if pred is None:
                        continue
                    reg = {"id": "espn-" + g["id"], "liga": nombre, "fecha": fiso, "local": g["local"],
                           "visitante": g["visitante"], "creada": t_ahora.strftime("%Y-%m-%dT%H:%M:%SZ"),
                           "resultado": None, "marcador": None}
                    reg.update(pred)
                    lista.append(reg)
                    por_id[reg["id"]] = reg
                    nuevas += 1
                    n_motor += 1
        except Exception as e:
            print("Aviso: ligas de ESPN no procesadas (%s)" % e)
    print("Predicciones nuevas: %d con el motor propio, %d con el modelo anterior" % (n_motor, n_base))

    if errores == len(LIGAS):
        print("ERROR: no se pudo leer ninguna liga. No se cambia nada.")
        sys.exit(1)

    stamp = t_ahora.strftime("%Y-%m-%d %H:%M UTC")

    hist["predicciones"] = lista
    hist["actualizado"] = stamp
    guardar_json("historial.json", hist)

    visibles = []
    for p in lista:
        if p.get("resultado") is not None:
            continue
        if parse_fecha(p["fecha"]) < t_ahora - timedelta(hours=3):
            continue
        q = dict(p)
        if p.get("modelo") == "SE":
            q["razon_es"] = ("Goles esperados: %.2f - %.2f. Motor propio Sports Edge: combina la fuerza en goles de cada "
                             "equipo (con mas peso a lo reciente), la calidad de sus ocasiones (tiros a puerta) y su "
                             "rating Elo, ajustado con temporadas pasadas y comprobado con partidos que no habia visto." %
                             (p["xg_local"], p["xg_visitante"]))
            q["razon_en"] = ("Expected goals: %.2f - %.2f. Sports Edge's own engine: it blends each team's goal strength "
                             "(weighted towards recent games), the quality of its chances (shots on target) and its Elo "
                             "rating, tuned on past seasons and checked on games it had not seen." %
                             (p["xg_local"], p["xg_visitante"]))
            visibles.append(q)
            continue
        q["razon_es"] = ("Goles esperados: %.2f - %.2f. Modelo de Poisson con los resultados reales de liga "
                         "de esta temporada (%d partidos por equipo como minimo). Probabilidad de gol de "
                         "cada jugador: su porcentaje de goles del equipo por los goles esperados del partido." %
                         (p["xg_local"], p["xg_visitante"], p["n_partidos"]))
        q["razon_en"] = ("Expected goals: %.2f - %.2f. Poisson model built from real league results "
                         "this season (at least %d matches per team). Player scoring probability: his share "
                         "of the team's goals times the match's expected goals." %
                         (p["xg_local"], p["xg_visitante"], p["n_partidos"]))
        visibles.append(q)
    visibles.sort(key=lambda x: x["fecha"])
    guardar_json("predicciones.json", {"actualizado": stamp, "predicciones": visibles})

    guardar_json("partidos.json", {"actualizado": stamp,
                                   "partidos": sorted(proximos, key=lambda x: x["fecha"])})

    res = [p for p in lista if p.get("resultado") is not None]
    acierto, brier = metricas(res)
    ligas_st = {}
    for nombre in list(LIGAS.values()) + [v[0] for v in LIGAS_ESPN.values()]:
        rs = [p for p in res if p["liga"] == nombre]
        ac, br = metricas(rs)
        ligas_st[nombre] = {"total": len([p for p in lista if p["liga"] == nombre]),
                            "resueltas": len(rs), "acierto": ac}
    guardar_json("estadisticas.json", {"actualizado": stamp, "total": len(lista),
                                       "resueltas": len(res), "acierto": acierto,
                                       "brier": brier, "ligas": ligas_st})

    print("OK: %d nuevas, %d ampliadas, %d resultados anotados, %d en historial" %
          (nuevas, ampliadas, resueltas, len(lista)))


if __name__ == "__main__":
    main()
