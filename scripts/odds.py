# -*- coding: utf-8 -*-
"""Sports Edge - Cuotas reales y analisis de valor (solo libreria estandar)."""
import difflib
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

KEY = os.environ.get("ODDS_API_KEY", "").strip()
LLAMAR = os.environ.get("ODDS_FETCH", "true").strip().lower() == "true"
API = "https://api.the-odds-api.com/v4/sports/%s/odds"
DATA = "data"

DEPORTES = {
    "Premier League": "soccer_epl",
    "LaLiga": "soccer_spain_la_liga",
    "Serie A": "soccer_italy_serie_a",
    "Bundesliga": "soccer_germany_bundesliga",
    "Ligue 1": "soccer_france_ligue_one",
    "Primeira Liga": "soccer_portugal_primeira_liga",
    "Eredivisie": "soccer_netherlands_eredivisie",
    "Championship": "soccer_efl_champ",
    "Brasileirão": "soccer_brazil_campeonato",
    "Liga Profesional": "soccer_argentina_primera_division",
    "MLS": "soccer_usa_mls",
}
HORAS_CUOTAS = 48     # solo se piden cuotas de ligas con partidos en las proximas 48 h (ahorra creditos)
REGION = "eu"
UMBRAL_VALOR = 0.05   # ventaja minima para marcar valor
PROB_MIN = 0.10       # no se marcan apuestas muy improbables
MIN_CREDITOS = 25     # si quedan menos creditos, se detienen las consultas
VENTANA_H = 12        # diferencia maxima de hora entre nuestro partido y el de la casa

STOP = set(["fc", "afc", "cf", "ac", "as", "sc", "sv", "fsv", "vfb", "vfl", "rb", "ss", "us",
            "ud", "rc", "rcd", "ca", "cd", "club", "de", "del", "la", "le", "les", "the",
            "calcio", "stade", "olympique"])
ALIAS = {"munchen": "munich", "internazionale": "inter", "milano": "milan",
         "brestois": "brest", "lyonnais": "lyon", "rennais": "rennes"}


def leer_json(nombre, defecto):
    try:
        with open(os.path.join(DATA, nombre), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return defecto


def guardar_json(nombre, obj):
    with open(os.path.join(DATA, nombre), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def parse(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def toks(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode("ascii").lower()
    s = s.replace("&", " and ")
    out = []
    for w in re.findall(r"[a-z0-9]+", s):
        if w.isdigit() or w in STOP:
            continue
        out.append(ALIAS.get(w, w))
    return out


def sim(a, b):
    ta = toks(a)
    tb = toks(b)
    if not ta or not tb:
        return 0.0
    if set(ta) == set(tb):
        return 1.0
    if set(ta) <= set(tb) or set(tb) <= set(ta):
        return 0.9
    r = difflib.SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio()
    return r if r >= 0.85 else 0.0


def pedir(dep):
    q = urllib.parse.urlencode({"apiKey": KEY, "regions": REGION, "markets": "h2h",
                                "oddsFormat": "decimal", "dateFormat": "iso"})
    req = urllib.request.Request((API % dep) + "?" + q, headers={"User-Agent": "sports-edge"})
    with urllib.request.urlopen(req, timeout=30) as r:
        rest = r.headers.get("x-requests-remaining")
        datos = json.load(r)
    return datos, rest


def eventos(datos):
    out = []
    for ev in datos if isinstance(datos, list) else []:
        try:
            out.append({"home": ev["home_team"], "away": ev["away_team"],
                        "t": parse(ev["commence_time"]), "raw": ev})
        except Exception:
            continue
    return out


def buscar(evs, p):
    try:
        fecha = parse(p["fecha"])
    except Exception:
        return None
    mejor = None
    ms = 0.0
    for e in evs:
        if abs((e["t"] - fecha).total_seconds()) > VENTANA_H * 3600:
            continue
        a = sim(p["local"], e["home"])
        b = sim(p["visitante"], e["away"])
        if a > 0 and b > 0 and a + b > ms:
            mejor = e
            ms = a + b
    return mejor


def procesar(ev):
    mejor = {}
    cons = {"1": [], "X": [], "2": []}
    casas = 0
    for b in ev.get("bookmakers", []):
        for m in b.get("markets", []):
            if m.get("key") != "h2h":
                continue
            precios = {}
            for o in m.get("outcomes", []):
                nm = o.get("name")
                pr = o.get("price")
                if not isinstance(pr, (int, float)) or pr <= 1:
                    continue
                if nm == ev.get("home_team"):
                    k = "1"
                elif nm == ev.get("away_team"):
                    k = "2"
                elif nm == "Draw":
                    k = "X"
                else:
                    continue
                precios[k] = pr
                if k not in mejor or pr > mejor[k]["c"]:
                    mejor[k] = {"c": round(pr, 2), "casa": b.get("title") or b.get("key")}
            if len(precios) == 3:
                casas += 1
                s = sum(1.0 / v for v in precios.values())
                for k, v in precios.items():
                    cons[k].append((1.0 / v) / s)
    if len(mejor) < 3 or casas == 0:
        return None
    mercado = {k: round(sum(v) / len(v), 4) for k, v in cons.items()}
    return mejor, mercado, casas


def valor_permitido():
    """VALOR solo se marca si la simulacion con cuotas reales del motor propio dio beneficio.
    Si dio perdidas, se muestran las cuotas y la ventaja, pero no se recomienda nada."""
    try:
        with open(os.path.join("data", "motor_futbol.json"), encoding="utf-8") as f:
            v = (json.load(f).get("prueba") or {}).get("valor") or {}
        return v.get("roi") is not None and v["roi"] >= 0
    except Exception:
        return False


VALOR_OK = None


def evaluar(p, mejor, mercado):
    global VALOR_OK
    if VALOR_OK is None:
        VALOR_OK = valor_permitido()
        if not VALOR_OK:
            print("Aviso: la simulacion con cuotas reales del motor dio perdidas. En futbol no se marca VALOR.")
    probs = {"1": p["p_local"], "X": p["p_empate"], "2": p["p_visitante"]}
    ev = {}
    valor = []
    for k in ("1", "X", "2"):
        ev[k] = round(probs[k] * mejor[k]["c"] - 1, 4)
        if VALOR_OK and ev[k] >= UMBRAL_VALOR and probs[k] >= PROB_MIN and probs[k] > mercado[k] \
                and probs[k] - mercado[k] <= 0.15:
            valor.append(k)
    return ev, valor


def stats_valor(lista):
    n = 0
    gan = 0
    ben = 0.0
    for p in lista:
        cg = p.get("cuota_guardada")
        r = p.get("resultado")
        if not cg or r is None:
            continue
        for k in cg.get("valor", []):
            c = cg.get(k)
            if not c:
                continue
            n += 1
            if r == k:
                gan += 1
                ben += c - 1
            else:
                ben -= 1
    return {"apuestas": n, "ganadas": gan, "beneficio": round(ben, 2),
            "roi": round(ben / n, 4) if n else None}


def main():
    os.makedirs(DATA, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    hist = leer_json("historial.json", {"predicciones": []})
    lista = hist.get("predicciones", [])
    preds = leer_json("predicciones.json", {}).get("predicciones", [])
    llamar = LLAMAR
    fallo = False

    if llamar and not KEY:
        print("Aviso: falta ODDS_API_KEY. No se consultan cuotas.")
        llamar = False

    if llamar:
        viejo = leer_json("cuotas.json", {}).get("partidos", {})
        nuevo = {}
        restantes = None
        casados = 0
        sin_casar = []
        leidas = 0
        pedidas = 0
        for liga, dep in DEPORTES.items():
            ps = [p for p in preds if p.get("liga") == liga]
            pronto = [p for p in ps if (parse(p["fecha"]) - datetime.now(timezone.utc)).total_seconds() < HORAS_CUOTAS * 3600]
            if not pronto:
                for p in ps:   # se conservan las cuotas que ya teniamos de esa liga
                    if str(p.get("id")) in viejo:
                        nuevo[str(p["id"])] = viejo[str(p["id"])]
                continue
            pedidas += 1
            datos = None
            if restantes is not None and restantes < MIN_CREDITOS:
                print("Aviso: quedan %d creditos. Se detienen las consultas." % restantes)
            else:
                try:
                    datos, rest = pedir(dep)
                    leidas += 1
                    if rest is not None:
                        try:
                            restantes = int(float(rest))
                        except Exception:
                            pass
                except urllib.error.HTTPError as e:
                    print("Aviso: %s -> error HTTP %s" % (liga, e.code))
                except Exception as e:
                    print("Aviso: %s -> %s" % (liga, e))
            if datos is None:
                for p in ps:
                    if str(p["id"]) in viejo:
                        nuevo[str(p["id"])] = viejo[str(p["id"])]
                continue
            evs = eventos(datos)
            for p in ps:
                ev = buscar(evs, p)
                res = procesar(ev["raw"]) if ev else None
                if res is None:
                    sin_casar.append("%s: %s - %s" % (liga, p["local"], p["visitante"]))
                    continue
                mejor, mercado, casas = res
                evl, valor = evaluar(p, mejor, mercado)
                nuevo[str(p["id"])] = {"mejor": mejor, "mercado": mercado, "casas": casas,
                                       "ev": evl, "valor": valor, "actualizado": stamp}
                casados += 1

        print("Cuotas: %d partidos con cuotas, %d sin emparejar. Creditos restantes: %s" %
              (casados, len(sin_casar), restantes if restantes is not None else "?"))
        for s in sin_casar:
            print("  Sin emparejar -> " + s)

        if leidas > 0:
            guardar_json("cuotas.json", {"actualizado": stamp, "partidos": nuevo})
            cambios = 0
            for p in lista:
                if p.get("resultado") is not None or "cuota_guardada" in p:
                    continue
                c = nuevo.get(str(p["id"]))
                if not c:
                    continue
                cg = {"fecha": stamp, "valor": c["valor"]}
                for k in ("1", "X", "2"):
                    cg[k] = c["mejor"][k]["c"]
                p["cuota_guardada"] = cg
                cambios += 1
            if cambios:
                hist["predicciones"] = lista
                guardar_json("historial.json", hist)
                print("Cuotas guardadas en el historial: %d" % cambios)
        elif pedidas > 0:
            fallo = True

    sv = stats_valor(lista)
    sv["actualizado"] = stamp
    guardar_json("valor.json", sv)
    print("Valor simulado: %d apuestas, ROI %s" % (sv["apuestas"], sv["roi"]))
    if fallo:
        sys.exit(1)


if __name__ == "__main__":
    main()
