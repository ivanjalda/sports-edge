# -*- coding: utf-8 -*-
"""SportEVLab - Telegram: resultados finalizados (cada 30 min) y balance del dia (por la noche).
Se envia en espanol al canal @sportevlab y en ingles al canal @sportevlab_en.

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
import time
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
CANALES = {"es": os.environ.get("TELEGRAM_CANAL_ES", "").strip() or "@sportevlab",
           "en": os.environ.get("TELEGRAM_CANAL_EN", "").strip() or "@sportevlab_en"}
PRUEBA = bool(os.environ.get("TELEGRAM_PRUEBA"))
MODO = os.environ.get("MODO", "resultados").strip().lower()
WEB = "https://sportevlab.com/"
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
    ("rugby", u"\U0001F3C9", "Seis Naciones", "rugby/180659", "", "rug_6n"),
    ("rugby", u"\U0001F3C9", "Premiership", "rugby/267979", "", "rug_prem"),
    ("rugby", u"\U0001F3C9", "Top 14", "rugby/270559", "", "rug_top14"),
    ("rugby", u"\U0001F3C9", "United Rugby Championship", "rugby/270557", "", "rug_urc"),
    ("rugby", u"\U0001F3C9", "Champions Cup", "rugby/271937", "", "rug_cc"),
    ("rugby", u"\U0001F3C9", "Super Rugby", "rugby/242041", "", "rug_super"),
]
NOMBRES = {"futbol": u"⚽ Fútbol", "tenis": u"\U0001F3BE Tenis", "baloncesto": u"\U0001F3C0 Baloncesto",
           "hockey": u"\U0001F3D2 Hockey", "americano": u"\U0001F3C8 Fútbol americano", "mma": u"\U0001F94B MMA",
           "beisbol": u"⚾ Béisbol", "voleibol": u"\U0001F3D0 Voleibol",
           "rugby": u"\U0001F3C9 Rugby", "esports": u"\U0001F3AE Esports", "motor": u"\U0001F3C1 Motor"}
NOMBRES_EN = {"futbol": u"⚽ Football", "tenis": u"\U0001F3BE Tennis", "baloncesto": u"\U0001F3C0 Basketball",
              "hockey": u"\U0001F3D2 Hockey", "americano": u"\U0001F3C8 American football", "mma": u"\U0001F94B MMA",
              "beisbol": u"⚾ Baseball", "voleibol": u"\U0001F3D0 Volleyball",
              "rugby": u"\U0001F3C9 Rugby", "esports": u"\U0001F3AE Esports", "motor": u"\U0001F3C1 Motorsport"}
LIGA_EN = {"Seis Naciones": "Six Nations", "NCAA femenina": "NCAA Women"}
ORDEN = ["futbol", "tenis", "baloncesto", "hockey", "americano", "mma", "beisbol", "voleibol", "rugby", "esports", "motor"]


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


def premium_cfg():
    """Canales privados Premium (solo si la suscripcion esta activada en data/premium.json)."""
    c = leer("premium.json", {}) or {}
    tok = os.environ.get("TELEGRAM_PREMIUM_TOKEN", "").strip()
    if c.get("activo") and tok and c.get("canal_es") and c.get("canal_en"):
        return {"token": tok, "es": c["canal_es"], "en": c["canal_en"]}
    return None


def enviar(texto, chat, token=None):
    url = "https://api.telegram.org/bot%s/sendMessage" % (token or TOKEN)
    datos = urllib.parse.urlencode({"chat_id": chat, "text": texto, "parse_mode": "HTML",
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
    pred["lol"] = leer("equipos_lol_historial.json", {}).get("predicciones", [])
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
    # League of Legends: no esta en ESPN; los resultados los trae el motor desde Leaguepedia
    for g in (leer("equipos_lol_resultados.json", {}).get("juegos") or {}).values():
        try:
            if g.get("pl") is None or g.get("pv") is None or fecha(g["fecha"]) < ahora - timedelta(hours=48):
                continue
        except Exception:
            continue
        out.append({"dep": "esports", "ic": u"\U0001F3AE", "liga": "League of Legends", "clave": "lol", "id": str(g["id"]),
                    "fecha": g["fecha"], "local": g["local"], "visit": g["visitante"], "gl": int(g["pl"]), "gv": int(g["pv"])})
    vistos, unicos = set(), []
    for x in out:
        k = x["clave"] + ":" + x["id"]
        if k not in vistos:
            vistos.add(k)
            unicos.append(x)
    return unicos, fallos


# ------------------------------------------------------------- mensajes
def bloque_resultados(nuevos, lang):
    en = lang == "en"
    lin = [u"\U0001F3C1 <b>%s</b>" % ("FINAL RESULTS" if en else "RESULTADOS FINALIZADOS")]
    grupos = {}
    for x in nuevos:
        grupos.setdefault((x["ic"], x["liga"]), []).append(x)
    for (ic, liga), xs in grupos.items():
        lin.append(u"\n%s <b>%s</b>" % (ic, e(LIGA_EN.get(liga, liga) if en else liga)))
        for x in xs[:MAX_POR_LIGA]:
            pk = "Draw" if (en and x["pick"] == "Empate") else x["pick"]
            lin.append(u"%s %s <b>%d – %d</b> %s\n     %s: %s %s" % (
                u"✅" if x["ok"] else u"❌", e(x["local"]), x["gl"], x["gv"], e(x["visit"]),
                "Our pick" if en else "Dijimos", e(pk), pc(x["prob"])))
        if len(xs) > MAX_POR_LIGA:
            ok = sum(1 for x in xs[MAX_POR_LIGA:] if x["ok"])
            lin.append((u"… and %d more (%d correct). All on the website." if en else
                        u"… y %d más (%d acertados). Todos en la web.") % (len(xs) - MAX_POR_LIGA, ok))
    return "\n".join(lin)


def resumen_dia(estado, dia):
    porDep = {}
    for v in estado["enviados"].values():
        if v.get("dia") == dia:
            a = porDep.setdefault(v["dep"], [0, 0])
            a[0] += 1 if v["ok"] else 0
            a[1] += 1
    return porDep


def ciclo(estado, ahora, balance):
    """Una pasada: resultados nuevos (y balance si toca). Devuelve la lista de mensajes."""
    dia = ahora.astimezone(TZ).strftime("%Y-%m-%d")
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
    print("[%s] Partidos terminados leidos: %d (fallos de lectura: %d). Con pronostico y sin avisar: %d" %
          (ahora.astimezone(TZ).strftime("%H:%M"), len(lista), fallos, len(nuevos)))

    bloques = {"es": [], "en": []}
    publico = {"es": [], "en": []}   # lo que va al canal gratis cuando Premium esta activado (el balance)
    # Carreras (F1 y MotoGP): resultado de la ultima carrera frente a nuestro favorito
    for serie, ic, nomb in (("f1", u"\U0001F3CE", u"Fórmula 1"), ("motogp", u"\U0001F3CD", u"MotoGP"), ("nascar", u"\U0001F3C1", u"NASCAR"),
                            ("golf_pga", u"\u26f3", u"PGA Tour"), ("golf_dp", u"\u26f3", u"DP World Tour")):
        hist = leer("carreras_%s_historial.json" % serie, {}).get("predicciones", [])
        por = {}
        for p in hist:
            if p.get("resultado") and (p["id"] not in por or p["tipo"] == "parrilla"):
                por[p["id"]] = p
        for p in por.values():
            k = "car:" + p["id"]
            if k in estado["enviados"]:
                continue
            try:
                reciente = (ahora - fecha(p["fecha"])).total_seconds() < 3 * 86400
            except Exception:
                reciente = False
            r = p["resultado"]
            estado["enviados"][k] = {"dia": dia, "dep": "motor", "ok": bool(r["acierto"])}
            if not reciente or primera:
                continue
            golf = serie.startswith("golf")
            podio = ", ".join(e(x) for x in r.get("podio_n", [])[1:])
            bloques["es"].append(u"%s <b>%s · %s</b>\n\U0001F3C6 Ganó <b>%s</b>%s\n%s Nuestro favorito: %s (%s de ganar)%s" % (
                ic, nomb, e(p["nombre"]), e(r["ganador_n"]),
                ((u" · top 3: " if golf else u" · podio: ") + podio) if r.get("podio_n") else "",
                u"✅" if r["acierto"] else u"❌", e(p["fav"]["n"]), pc(p["fav"]["pw"]),
                u"" if r["acierto"] else u" · al ganador le dábamos %s" % pc(r.get("p_ganador") or 0)))
            bloques["en"].append(u"%s <b>%s · %s</b>\n\U0001F3C6 Winner: <b>%s</b>%s\n%s Our favourite: %s (%s to win)%s" % (
                ic, nomb.replace(u"Fórmula 1", "Formula 1"), e(p["nombre"]), e(r["ganador_n"]),
                ((u" · top 3: " if golf else u" · podium: ") + podio) if r.get("podio_n") else "",
                u"✅" if r["acierto"] else u"❌", e(p["fav"]["n"]), pc(p["fav"]["pw"]),
                u"" if r["acierto"] else u" · we gave the winner %s" % pc(r.get("p_ganador") or 0)))
    if nuevos:
        if primera:
            print("Primera ejecucion: se apuntan %d partidos ya terminados sin enviarlos." % len(nuevos))
        else:
            for lang in ("es", "en"):
                bloques[lang].append(bloque_resultados(nuevos, lang))
        for x in nuevos:
            estado["enviados"][x["k"]] = {"dia": dia, "dep": x["dep"], "ok": x["ok"]}
    estado["inicio"] = estado.get("inicio") or ahora.strftime("%Y-%m-%d %H:%M UTC")

    hoy = resumen_dia(estado, dia)
    if bloques["es"]:
        a = sum(v[0] for v in hoy.values())
        n = sum(v[1] for v in hoy.values())
        bloques["es"].append(u"\U0001F4C8 Hoy llevamos <b>%d de %d</b> acertados (%s)\n\U0001F534 Partidos en directo: %sdirecto.html" %
                             (a, n, pc(a / float(n)) if n else "-", WEB))
        bloques["en"].append(u"\U0001F4C8 Today so far: <b>%d of %d</b> correct (%s)\n\U0001F534 Live games: %sdirecto.html" %
                             (a, n, pc(a / float(n)) if n else "-", WEB))

    if balance and estado.get("balance") != dia:
        fechatxt = ahora.astimezone(TZ).strftime("%d/%m/%Y")
        if hoy:
            a = sum(v[0] for v in hoy.values())
            n = sum(v[1] for v in hoy.values())
            lin = [u"\U0001F4CA <b>BALANCE DEL DÍA</b> · %s" % fechatxt,
                   u"Hoy acertamos <b>%d de %d</b> pronósticos (%s)\n" % (a, n, pc(a / float(n)))]
            len_ = [u"\U0001F4CA <b>DAILY BALANCE</b> · %s" % fechatxt,
                    u"Today we got <b>%d of %d</b> predictions right (%s)\n" % (a, n, pc(a / float(n)))]
            for d in ORDEN:
                if d in hoy:
                    lin.append(u"%s: %d de %d (%s)" % (NOMBRES[d], hoy[d][0], hoy[d][1], pc(hoy[d][0] / float(hoy[d][1]))))
                    len_.append(u"%s: %d of %d (%s)" % (NOMBRES_EN[d], hoy[d][0], hoy[d][1], pc(hoy[d][0] / float(hoy[d][1]))))
            lin.append(u"\nTodos los pronósticos se publican antes de cada partido y no se cambian nunca.")
            lin.append(u"\U0001F3AF Mañana por la mañana, los nuevos pronósticos.\n\U0001F310 %s" % WEB)
            lin.append(u"⚠ Solo +18. Juega con responsabilidad.")
            len_.append(u"\nEvery prediction is published before the game and never changed.")
            len_.append(u"\U0001F3AF New predictions tomorrow morning.\n\U0001F310 %s" % WEB)
            len_.append(u"⚠ 18+ only. Please gamble responsibly.")
            bloques["es"].append("\n".join(lin))
            bloques["en"].append("\n".join(len_))
            publico["es"].append("\n".join(lin) + u"\n\U0001F48E Resultados en directo y todos los pronósticos en Premium: %spremium.html" % WEB)
            publico["en"].append("\n".join(len_) + u"\n\U0001F48E Live results and every prediction with Premium: %spremium.html" % WEB)
        estado["balance"] = dia

    limite = (ahora - timedelta(days=4)).astimezone(TZ).strftime("%Y-%m-%d")
    estado["enviados"] = {k: v for k, v in estado["enviados"].items() if v.get("dia", "") >= limite}
    out = {lang: trocear(b) for lang, b in bloques.items()}
    out["publico"] = {lang: trocear(b) for lang, b in publico.items()}
    return out


def mandar(mensajes):
    """mensajes = {"es": [...], "en": [...]}. Devuelve False solo si no se pudo enviar a ningun canal."""
    prem = premium_cfg()
    publico = mensajes.get("publico") or {}
    envios = []   # (idioma, mensajes, canal, token)
    for lang in ("es", "en"):
        ms = mensajes.get(lang) or []
        if prem:
            # Premium activado: todo al canal privado; al canal gratis solo el balance de la noche
            envios.append((lang, ms, prem[lang], prem["token"]))
            envios.append((lang, publico.get(lang) or [], CANALES[lang], None))
        else:
            envios.append((lang, ms, CANALES[lang], None))
    if PRUEBA:
        for lang, ms, canal, _ in envios:
            print(("\n===== %s -> %s =====\n" % (lang, canal)) + ("\n\n-----\n".join(ms) if ms else "(no hay nada que enviar)"))
        return True
    hay = enviados = 0
    for lang, ms, canal, tok in envios:
        if not ms:
            continue
        hay += 1
        try:
            for m in ms:
                enviar(m, canal, tok)
            enviados += 1
            print("Telegram %s (%s): %d mensaje(s) enviado(s)." % (lang, canal, len(ms)))
        except Exception as ex:
            print("ERROR enviando a Telegram %s (%s): %s" % (lang, canal, ex))
    return enviados > 0 or hay == 0


def main():
    if not PRUEBA and not TOKEN:
        print("Telegram no configurado (falta TELEGRAM_TOKEN). No se envia nada.")
        return
    ahora = datetime.now(timezone.utc)
    estado = leer(ESTADO, {})
    mensajes = ciclo(estado, ahora, MODO == "balance")
    if not mandar(mensajes):
        sys.exit(1)
    if not PRUEBA:
        estado["actualizado"] = ahora.strftime("%Y-%m-%d %H:%M UTC")
        guardar(ESTADO, estado)


# ------------------------------------------------------------- modo vigilante (bucle)
HORA_MANANA = (9, 30)    # pronosticos del dia (hora de Madrid)
HORA_BALANCE = (23, 40)  # balance del dia (hora de Madrid)


def git(*args):
    import subprocess
    r = subprocess.run(["git"] + list(args), capture_output=True, text=True)
    if r.returncode != 0:
        print("git %s -> %s" % (" ".join(args), (r.stderr or r.stdout).strip()[:300]))
    return r.returncode == 0


def subir(msg):
    # el asistente virtual se actualiza a la vez que los resultados
    try:
        import subprocess
        subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "asistente_contexto.py")], timeout=120)
        git("add", os.path.join(DATA, "asistente.json"))
    except Exception as ex:
        print("Aviso: asistente no actualizado: %s" % ex)
    # panel privado del administrador ("Mi cuenta"): como mucho cada 30 minutos
    try:
        import subprocess
        subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "panel_admin.py")],
                       timeout=180, env=dict(os.environ, PANEL_CADA_MIN="30"))
        git("add", os.path.join(DATA, "panel.json"))
        git("add", os.path.join(DATA, "premium.json"))
    except Exception as ex:
        print("Aviso: panel no actualizado: %s" % ex)
    git("add", os.path.join(DATA, ESTADO))
    if git("diff", "--cached", "--quiet"):
        return
    git("commit", "-q", "-m", msg)
    for _ in range(3):
        # si otra tarea ha cambiado los mismos archivos generados, gana la version recien calculada
        if git("pull", "-q", "--rebase", "-X", "theirs") and git("push", "-q"):
            return
        git("rebase", "--abort")
        time.sleep(15)


def bucle():
    """Vigila durante DURACION minutos: cada 10 minutos mira resultados; a las 9:30 manda los pronosticos
    del dia y a las 23:40 el balance (hora de Madrid). Asi no dependemos de que GitHub lance a tiempo
    las tareas programadas, que a veces se retrasan horas."""
    import subprocess
    fin = time.time() + 60 * float(os.environ.get("DURACION", "330"))
    while True:
        git("pull", "-q", "--rebase")
        estado = leer(ESTADO, {})
        ahora = datetime.now(timezone.utc)
        loc = ahora.astimezone(TZ)
        dia = loc.strftime("%Y-%m-%d")
        if "manana" not in estado:
            estado["manana"] = dia   # primera vez: hoy ya se enviaron los pronosticos con el sistema anterior
        antes = json.dumps(estado, sort_keys=True)
        try:
            # 1) pronosticos del dia
            if (loc.hour, loc.minute) >= HORA_MANANA and estado.get("manana") != dia:
                r = subprocess.run([sys.executable, "-u", os.path.join("scripts", "telegram.py")])
                if r.returncode == 0:
                    estado["manana"] = dia
            # 1b) correo diario a los registrados que lo activaron (cada uno lo recibe una sola vez al dia)
            if (loc.hour, loc.minute) >= HORA_MANANA and estado.get("correo") != dia and os.environ.get("BREVO_API_KEY"):
                intentos = estado.get("correo_intentos", {})
                intentos = {dia: intentos.get(dia, 0) + 1}
                estado["correo_intentos"] = intentos
                r = subprocess.run([sys.executable, "-u", os.path.join("scripts", "correo.py")])
                if r.returncode == 0 or intentos[dia] >= 3:
                    estado["correo"] = dia
            # 0) Premium: pagos de Stripe -> cuentas y canales privados (cada 10 minutos)
            if os.environ.get("STRIPE_KEY") or os.environ.get("TELEGRAM_PREMIUM_TOKEN"):
                subprocess.run([sys.executable, "-u", os.path.join("scripts", "premium.py")], timeout=240)
                cambio = subprocess.run(["git", "status", "--porcelain", os.path.join(DATA, "premium.json")],
                                        capture_output=True, text=True).stdout.strip()
                if cambio and not PRUEBA:
                    subir("Premium: suscripciones revisadas")
            # 2) resultados y 3) balance
            balance = (loc.hour, loc.minute) >= HORA_BALANCE
            mensajes = ciclo(estado, ahora, balance)
            if not mandar(mensajes):
                estado = json.loads(antes)   # no se apunta nada si no se pudo enviar
        except Exception as ex:
            print("Aviso en el ciclo: %s" % ex)
            estado = json.loads(antes)
        if json.dumps(estado, sort_keys=True) != antes and not PRUEBA:
            guardar(ESTADO, estado)
            subir("Telegram: resultados enviados")
        if time.time() + 600 > fin:
            break
        time.sleep(600)
    print("Fin del turno de vigilancia.")


if __name__ == "__main__":
    if not PRUEBA and not TOKEN:
        print("Telegram no configurado (falta TELEGRAM_TOKEN). No se envia nada.")
    elif MODO == "bucle":
        bucle()
    else:
        main()
