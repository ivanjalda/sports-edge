# -*- coding: utf-8 -*-
"""Sports Edge - Telegram: resultados finalizados (cada 30 min) y balance del dia (por la noche).

Solo libreria estandar. Nada se inventa:
- Los marcadores finales salen del marcador publico de ESPN.
- El pronostico es el que guardamos ANTES del partido (data/historial.json y data/equipos_*_historial.json).
- Solo se avisa de partidos que pronosticamos. Cada partido se avisa una sola vez
  (se apunta en data/telegram_directo.json).

MODO=resultados (por defecto): envia los partidos terminados desde el ultimo aviso. Si no hay ninguno, no envia nada.
MODO=balance: hace lo mismo y despues envia el balance del dia (hora de Madrid).
TELEGRAM_PRUEBA=1: escribe los mensajes en pantalla en vez de enviarlos y no guarda nada.
"""
import html
import json
import os
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Madrid")
except Exception:
    TZ = timezone.utc

TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
PRUEBA = bool(os.environ.get("TELEGRAM_PRUEBA"))
MODO = os.environ.get("MODO", "resultados").strip().lower()
WEB = "https://ivanjalda.github.io/sports-edge/"
DATA = "data"
ESTADO = "telegram_directo.json"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/"
MAX_POR_LIGA = 8

# (deporte, icono, liga, ruta ESPN, extra, archivo de predicciones)
FUENTES = [
    ("futbol", u"⚽", "LaLiga", "soccer/esp.1", "", "futbol"),
    ("futbol", u"⚽", "Premier League", "soccer/eng.1", "", "futbol"),
    ("futbol", u"⚽", "Serie A", "soccer/ita.1", "", "futbol"),
    ("futbol", u"⚽", "Bundesliga", "soccer/ger.1", "", "futbol"),
    ("futbol", u"⚽", "Ligue 1", "soccer/fra.1", "", "futbol"),
    ("futbol", u"⚽", "Primeira Liga", "soccer/por.1", "", "futbol"),
    ("futbol", u"⚽", "Eredivisie", "soccer/ned.1", "", "futbol"),
    ("futbol", u"⚽", "Championship", "soccer/eng.2", "", "futbol"),
    ("futbol", u"⚽", u"Brasileirão", "soccer/bra.1", "", "futbol"),
    ("futbol", u"⚽", "Liga Profesional", "soccer/arg.1", "", "futbol"),
    ("futbol", u"⚽", "MLS", "soccer/usa.1", "", "futbol"),
    ("baloncesto", u"\U0001F3C0", "NBA", "basketball/nba", "", "nba"),
    ("baloncesto", u"\U0001F3C0", "WNBA", "basketball/wnba", "", "wnba"),
    ("baloncesto", u"\U0001F3C0", "NCAA", "basketball/mens-college-basketball", "&groups=50", "ncaab"),
    ("hockey", u"\U0001F3D2", "NHL", "hockey/nhl", "", "nhl"),
    ("americano", u"\U0001F3C8", "NFL", "football/nfl", "", "nfl"),
    ("americano", u"\U0001F3C8", "NCAA", "football/college-football", "&groups=80", "ncaaf"),
    ("beisbol", u"⚾", "MLB", "baseball/mlb", "", "mlb"),
    ("voleibol", u"\U0001F3D0", "NCAA femenina", "volleyball/womens-college-volleyball", "", "voley"),
]
NOMBRES = {"futbol": u"⚽ Fútbol", "tenis": u"\U0001F3BE Tenis", "baloncesto": u"\U0001F3C0 Baloncesto",
           "hockey": u"\U0001F3D2 Hockey", "americano": u"\U0001F3C8 Fútbol americano", "mma": u"\U0001F94B MMA",
           "beisbol": u"⚾ Béisbol", "voleibol": u"\U0001F3D0 Voleibol"}
ORDEN = ["futbol", "tenis", "baloncesto", "hockey", "americano", "mma", "beisbol", "voleibol"]


def leer(nombre, defecto):
    try:
        with open(os.path.join(DATA, nombre), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return defecto


def guardar(nombre, obj):
    with open(os.path.join(DATA, nombre), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def e(s):
    return html.escape(str(s if s is not None else ""))


def pc(x):
    return "%d%%" % round(x * 100)


def fecha(s):
    s = str(s).replace("Z", "")[:19]
    if len(s) == 16:
        s += ":00"
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


def palabras(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    fuera = {"fc", "cf", "sc", "ac", "cd", "rc", "ud", "club", "de", "the", "afc"}
    return [w for w in s.split() if w and w not in fuera]


def parecido(a, b):
    x, y = palabras(a), palabras(b)
    if not x or not y:
        return False
    if x == y:
        return True
    c = sum(1 for w in x if len(w) > 2 and w in y)
    return c >= 1 and (c >= min(len(x), len(y)) or c >= 2)


def pedir(url):
    req = urllib.request.Request(url, headers={"User-Agent": "SportsEdge/1.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))


def enviar(texto):
    url = "https://api.telegram.org/bot%s/sendMessage" % TOKEN
    datos = urllib.parse.urlencode({"chat_id": CHAT, "text": texto, "parse_mode": "HTML",
                                    "disable_web_page_preview": "true"}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=datos), timeout=30) as r:
        r.read()


def trocear(bloques):
    mensajes, actual = [], ""
    for b in bloques:
        if actual and len(actual) + len(b) + 2 > 3800:
            mensajes.append(actual)
            actual = ""
        actual += (("\n\n" if actual else "") + b)
    if actual:
        mensajes.append(actual)
    return mensajes


# ------------------------------------------------------------- predicciones guardadas
def cargar_predicciones():
    pred = {"futbol": leer("historial.json", {}).get("predicciones", [])}
    for f in FUENTES:
        if f[5] != "futbol":
            pred[f[5]] = leer("equipos_%s_historial.json" % f[5], {}).get("predicciones", [])
    return pred


def buscar(pred, clave, ev_id, local, visit, cuando):
    lista = pred.get(clave) or []
    for p in lista:
        if str(p.get("id")) in (str(ev_id), "espn-" + str(ev_id)):
            return p
    for p in lista:
        try:
            cerca = abs((fecha(p["fecha"]) - cuando).total_seconds()) < 36 * 3600
        except Exception:
            cerca = False
        if cerca and parecido(p.get("local"), local) and parecido(p.get("visitante"), visit):
            return p
    return None


def eleccion(clave, p, local, visit):
    """(clave elegida 1/X/2, nombre, probabilidad)"""
    if clave == "futbol":
        pr = {"1": p["p_local"], "X": p["p_empate"], "2": p["p_visitante"]}
        k = max(pr, key=pr.get)
        return k, {"1": local, "X": "Empate", "2": visit}[k], pr[k]
    k = "1" if p["pl"] >= p["pv"] else "2"
    return k, (local if k == "1" else visit), max(p["pl"], p["pv"])


# ------------------------------------------------------------- partidos terminados en ESPN
def terminados(ahora):
    """Partidos terminados hoy y ayer (hora de EE. UU.) en las ligas que pronosticamos."""
    et = ahora - timedelta(hours=5)
    dias = [(et - timedelta(days=1)).strftime("%Y%m%d"), et.strftime("%Y%m%d")]
    out, fallos = [], 0
    for dep, ic, liga, ruta, extra, clave in FUENTES:
        for d in dias:
            try:
                j = pedir("%s%s/scoreboard?dates=%s&limit=300%s" % (ESPN, ruta, d, extra))
            except Exception:
                fallos += 1
                continue
            for ev in j.get("events") or []:
                comp = (ev.get("competitions") or [{}])[0]
                st = ((ev.get("status") or comp.get("status") or {}).get("type") or {})
                if st.get("state") != "post" or not st.get("completed", True):
                    continue
                if re.search(r"POSTPONED|CANCELED|SUSPENDED|FORFEIT", st.get("name", "")):
                    continue
                h = a = None
                for c in comp.get("competitors") or []:
                    if c.get("homeAway") == "home":
                        h = c
                    elif c.get("homeAway") == "away":
                        a = c
                if not h or not a:
                    continue
                try:
                    gl, gv = float(h.get("score")), float(a.get("score"))
                except Exception:
                    continue
                out.append({"dep": dep, "ic": ic, "liga": liga, "clave": clave, "id": str(ev.get("id")),
                            "fecha": ev.get("date"), "local": (h.get("team") or {}).get("displayName"),
                            "visit": (a.get("team") or {}).get("displayName"), "gl": int(gl), "gv": int(gv)})
    vistos, unicos = set(), []
    for x in out:
        k = x["clave"] + ":" + x["id"]
        if k not in vistos:
            vistos.add(k)
            unicos.append(x)
    return unicos, fallos


# ------------------------------------------------------------- mensajes
def bloque_resultados(nuevos):
    lin = [u"\U0001F3C1 <b>RESULTADOS FINALIZADOS</b>"]
    grupos = {}
    for x in nuevos:
        grupos.setdefault((x["ic"], x["liga"]), []).append(x)
    for (ic, liga), xs in grupos.items():
        lin.append(u"\n%s <b>%s</b>" % (ic, e(liga)))
        for x in xs[:MAX_POR_LIGA]:
            lin.append(u"%s %s <b>%d – %d</b> %s\n     Dijimos: %s %s" % (
                u"✅" if x["ok"] else u"❌", e(x["local"]), x["gl"], x["gv"], e(x["visit"]), e(x["pick"]), pc(x["prob"])))
        if len(xs) > MAX_POR_LIGA:
            ok = sum(1 for x in xs[MAX_POR_LIGA:] if x["ok"])
            lin.append(u"… y %d más (%d acertados). Todos en la web." % (len(xs) - MAX_POR_LIGA, ok))
    return "\n".join(lin)


def resumen_dia(estado, dia):
    porDep = {}
    for v in estado["enviados"].values():
        if v.get("dia") == dia:
            a = porDep.setdefault(v["dep"], [0, 0])
            a[0] += 1 if v["ok"] else 0
            a[1] += 1
    return porDep


def main():
    if not PRUEBA and (not TOKEN or not CHAT):
        print("Telegram no configurado (faltan TELEGRAM_TOKEN o TELEGRAM_CHAT_ID). No se envia nada.")
        return
    ahora = datetime.now(timezone.utc)
    dia = ahora.astimezone(TZ).strftime("%Y-%m-%d")
    estado = leer(ESTADO, {})
    estado.setdefault("enviados", {})
    primera = not estado["enviados"] and not estado.get("inicio")

    pred = cargar_predicciones()
    lista, fallos = terminados(ahora)
    nuevos = []
    for x in lista:
        k = x["clave"] + ":" + x["id"]
        if k in estado["enviados"]:
            continue
        try:
            cuando = fecha(x["fecha"])
        except Exception:
            continue
        p = buscar(pred, x["clave"], x["id"], x["local"], x["visit"], cuando)
        if not p:
            continue
        kk, nom, prob = eleccion(x["clave"], p, x["local"], x["visit"])
        real = "1" if x["gl"] > x["gv"] else ("2" if x["gl"] < x["gv"] else "X")
        x.update({"k": k, "pick": nom, "prob": prob, "ok": real == kk})
        nuevos.append(x)
    print("Partidos terminados leidos: %d (fallos de lectura: %d). Con pronostico y sin avisar: %d" %
          (len(lista), fallos, len(nuevos)))

    bloques = []
    if nuevos:
        if primera:
            # Primera vez: solo se apuntan, para no enviar de golpe todo lo de ayer
            print("Primera ejecucion: se apuntan %d partidos ya terminados sin enviarlos." % len(nuevos))
        else:
            bloques.append(bloque_resultados(nuevos))
        for x in nuevos:
            estado["enviados"][x["k"]] = {"dia": dia, "dep": x["dep"], "ok": x["ok"]}
    estado["inicio"] = estado.get("inicio") or ahora.strftime("%Y-%m-%d %H:%M UTC")

    hoy = resumen_dia(estado, dia)
    if bloques:
        a = sum(v[0] for v in hoy.values())
        n = sum(v[1] for v in hoy.values())
        bloques.append(u"\U0001F4C8 Hoy llevamos <b>%d de %d</b> acertados (%s)\n\U0001F534 Partidos en directo: %sdirecto.html" %
                       (a, n, pc(a / float(n)) if n else "-", WEB))

    if MODO == "balance" and estado.get("balance") != dia:
        fechatxt = ahora.astimezone(TZ).strftime("%d/%m/%Y")
        if hoy:
            a = sum(v[0] for v in hoy.values())
            n = sum(v[1] for v in hoy.values())
            lin = [u"\U0001F4CA <b>BALANCE DEL DÍA</b> · %s" % fechatxt,
                   u"Hoy acertamos <b>%d de %d</b> pronósticos (%s)\n" % (a, n, pc(a / float(n)))]
            for d in ORDEN:
                if d in hoy:
                    lin.append(u"%s: %d de %d (%s)" % (NOMBRES[d], hoy[d][0], hoy[d][1], pc(hoy[d][0] / float(hoy[d][1]))))
            lin.append(u"\nTodos los pronósticos se publican antes de cada partido y no se cambian nunca.")
            lin.append(u"\U0001F3AF Mañana por la mañana, los nuevos pronósticos.\n\U0001F310 %s" % WEB)
            lin.append(u"⚠ Solo +18. Juega con responsabilidad.")
            bloques.append("\n".join(lin))
        estado["balance"] = dia

    # limpieza: solo se guardan los ultimos 4 dias
    limite = (ahora - timedelta(days=4)).astimezone(TZ).strftime("%Y-%m-%d")
    estado["enviados"] = {k: v for k, v in estado["enviados"].items() if v.get("dia", "") >= limite}
    estado["actualizado"] = ahora.strftime("%Y-%m-%d %H:%M UTC")

    mensajes = trocear(bloques)
    if PRUEBA:
        print("\n\n=====\n".join(mensajes) if mensajes else "(no hay nada que enviar)")
        return
    try:
        for m in mensajes:
            enviar(m)
    except Exception as ex:
        print("ERROR enviando a Telegram: %s" % ex)
        sys.exit(1)
    guardar(ESTADO, estado)
    print("Telegram: %d mensaje(s) enviado(s)." % len(mensajes))


if __name__ == "__main__":
    main()
