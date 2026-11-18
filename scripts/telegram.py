# -*- coding: utf-8 -*-
"""SportEVLab - Resumen diario a Telegram con TODOS los deportes (solo libreria estandar).
Lee los mismos archivos que la web: nada se inventa. Si un deporte no tiene partidos hoy, no aparece.
Se envia en espanol al canal @sportevlab y en ingles al canal @sportevlab_en."""
import html
import json
import os
import sys
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
WEB = "https://sportevlab.com/"
HORAS = 24
LIGAS_FUT = ["Premier League", "LaLiga", "Serie A", "Bundesliga", "Ligue 1",
             "Primeira Liga", "Eredivisie", "Championship", "Brasileirão", "Liga Profesional", "MLS"]
EQUIPOS = [("baloncesto", u"\U0001F3C0", "Baloncesto", [("nba", "NBA"), ("euroliga", "Euroliga"), ("eurocup", "Eurocup"),
                                                     ("ncaab", "NCAA"), ("wnba", "WNBA")]),
           ("hockey", u"\U0001F3D2", "Hockey", [("nhl", "NHL"), ("ncaah", "NCAA")]),
           ("americano", u"\U0001F3C8", u"F\u00fatbol americano", [("nfl", "NFL"), ("ncaaf", "NCAA")]),
           ("mma", u"\U0001F94B", "MMA", [("ufc", "UFC")]),
           ("beisbol", u"\u26be", u"B\u00e9isbol", [("mlb", "MLB")]),
           ("voleibol", u"\U0001F3D0", "Voleibol", [("voley", "NCAA femenina")]),
           ("rugby", u"\U0001F3C9", "Rugby", [("rug_6n", "Seis Naciones"), ("rug_prem", "Premiership"), ("rug_top14", "Top 14"),
                                              ("rug_urc", "United Rugby Championship"), ("rug_cc", "Champions Cup"),
                                              ("rug_super", "Super Rugby")])]
MAX_POR_LIGA = 6   # para que el mensaje no sea interminable (la lista completa esta en la web)


def leer(nombre, defecto):
    try:
        with open(os.path.join("data", nombre), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return defecto


def e(s):
    return html.escape(str(s if s is not None else ""))


def pc(x):
    return ("%d%%" % round(x * 100)) if isinstance(x, (int, float)) else "s/d"


def fecha(s):
    s = str(s).replace("Z", "")[:19]
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


def hora(s):
    return fecha(s).astimezone(TZ).strftime("%H:%M")


def cuota_txt(c, k, lang="es"):
    if not c or not c.get("mejor") or not c["mejor"].get(k):
        return ""
    m = c["mejor"][k]
    if lang == "en":
        return u" · odds %.2f (%s)" % (m["c"], e(m.get("casa", "")))
    return u" · cuota %s (%s)" % (("%.2f" % m["c"]).replace(".", ","), e(m.get("casa", "")))


# Nombres en ingles (lo que no esta aqui se deja igual)
COMP_EN = {"Seis Naciones": "Six Nations", "NCAA femenina": "NCAA Women"}


def comp(nombre, lang):
    return COMP_EN.get(nombre, nombre) if lang == "en" else nombre


def pick(nombre, lang):
    return "Draw" if (lang == "en" and nombre == "Empate") else nombre


def enviar(texto, chat):
    url = "https://api.telegram.org/bot%s/sendMessage" % TOKEN
    datos = urllib.parse.urlencode({"chat_id": chat, "text": texto, "parse_mode": "HTML",
                                    "disable_web_page_preview": "true"}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=datos), timeout=30) as r:
        r.read()


# ------------------------------------------------------------- lectura comun de cada deporte
def partidos(ahora):
    """Lista comun: dep, ic, comp, fecha, a, b, pick, prob, cuota, valor, linea_detalle."""
    out = []
    lim = ahora + timedelta(hours=HORAS)
    cu = leer("cuotas.json", {}).get("partidos", {})
    for p in leer("predicciones.json", {}).get("predicciones", []):
        f = fecha(p["fecha"])
        if not (ahora <= f <= lim):
            continue
        pr = {"1": p["p_local"], "X": p["p_empate"], "2": p["p_visitante"]}
        k = max(pr, key=pr.get)
        c = cu.get(str(p["id"]))
        m = p.get("mercados") or {}
        det = u"1: %s · X: %s · 2: %s · +2,5: %s · Ambos: %s" % (
            pc(pr["1"]), pc(pr["X"]), pc(pr["2"]), pc(m.get("over25")), pc(m.get("btts")))
        det_en = u"1: %s · X: %s · 2: %s · Over 2.5: %s · BTTS: %s" % (
            pc(pr["1"]), pc(pr["X"]), pc(pr["2"]), pc(m.get("over25")), pc(m.get("btts")))
        out.append({"dep": "futbol", "ic": u"⚽", "comp": p["liga"], "fecha": p["fecha"], "a": p["local"],
                    "b": p["visitante"], "pick": {"1": p["local"], "X": "Empate", "2": p["visitante"]}[k],
                    "prob": pr[k], "cuota": cuota_txt(c, k), "cuota_en": cuota_txt(c, k, "en"), "valor": c.get("valor") if c else None,
                    "nom": {"1": p["local"], "X": "Empate", "2": p["visitante"]}, "pr": pr, "c": c, "det": det, "det_en": det_en})
    for q in leer("tenis.json", {}).get("predicciones", []):
        f = fecha(q["fecha"])
        if not (ahora <= f <= lim):
            continue
        k = "1" if q["p1"] >= q["p2"] else "2"
        c = q.get("cuota")
        out.append({"dep": "tenis", "ic": u"\U0001F3BE", "comp": q.get("torneo", ""), "fecha": q["fecha"],
                    "a": q["j1"], "b": q["j2"], "pick": q["j1"] if k == "1" else q["j2"], "prob": max(q["p1"], q["p2"]),
                    "cuota": cuota_txt(c, k), "cuota_en": cuota_txt(c, k, "en"), "valor": c.get("valor") if c else None,
                    "nom": {"1": q["j1"], "2": q["j2"]}, "pr": {"1": q["p1"], "2": q["p2"]}, "c": c,
                    "det": u"%s %s · %s %s" % (e(q["j1"]), pc(q["p1"]), e(q["j2"]), pc(q["p2"])),
                    "det_en": u"%s %s · %s %s" % (e(q["j1"]), pc(q["p1"]), e(q["j2"]), pc(q["p2"]))})
    for dep, ic, _, ligas in EQUIPOS:
        for clave, nombre in ligas:
            for r in leer("equipos_%s.json" % clave, {}).get("predicciones", []):
                f = fecha(r["fecha"])
                if not (ahora <= f <= lim):
                    continue
                k = "L" if r["pl"] >= r["pv"] else "V"
                c = r.get("cuota")
                out.append({"dep": dep, "ic": ic, "comp": nombre, "fecha": r["fecha"], "a": r["local"],
                            "b": r["visitante"], "pick": r["local"] if k == "L" else r["visitante"],
                            "prob": max(r["pl"], r["pv"]), "cuota": cuota_txt(c, k), "cuota_en": cuota_txt(c, k, "en"),
                            "valor": c.get("valor") if c else None,
                            "nom": {"L": r["local"], "V": r["visitante"]}, "pr": {"L": r["pl"], "V": r["pv"]}, "c": c,
                            "det": u"Local %s · Visitante %s" % (pc(r["pl"]), pc(r["pv"])),
                            "det_en": u"Home %s · Away %s" % (pc(r["pl"]), pc(r["pv"]))})
    return out


def resultados(ahora):
    """Predicciones resueltas en las ultimas 36 h, por deporte: (aciertos, total)."""
    desde = ahora - timedelta(hours=36)
    res = {}

    def sumar(dep, ok):
        a = res.setdefault(dep, [0, 0])
        a[0] += 1 if ok else 0
        a[1] += 1

    for p in leer("historial.json", {}).get("predicciones", []):
        if p.get("resultado") and desde <= fecha(p["fecha"]) <= ahora:
            pr = {"1": p["p_local"], "X": p["p_empate"], "2": p["p_visitante"]}
            sumar("futbol", max(pr, key=pr.get) == p["resultado"])
    for q in leer("tenis_historial.json", {}).get("predicciones", []):
        if q.get("resultado") and desde <= fecha(q["fecha"]) <= ahora:
            sumar("tenis", ("1" if q["p1"] >= q["p2"] else "2") == q["resultado"])
    for dep, _, _, ligas in EQUIPOS:
        for clave, _n in ligas:
            for r in leer("equipos_%s_historial.json" % clave, {}).get("predicciones", []):
                if r.get("resultado") and desde <= fecha(r["fecha"]) <= ahora:
                    sumar(dep, ("L" if r["pl"] >= r["pv"] else "V") == r["resultado"])
    return res


def record():
    """Acierto en directo acumulado de cada deporte (predicciones guardadas antes del partido)."""
    out = {}
    s = leer("estadisticas.json", {})
    if s.get("resueltas"):
        out["futbol"] = (s.get("acierto"), s["resueltas"])
    d = leer("tenis.json", {}).get("directo") or {}
    if d.get("resueltas"):
        out["tenis"] = (d.get("acierto"), d["resueltas"])
    for dep, _, _, ligas in EQUIPOS:
        h = n = 0
        for clave, _n in ligas:
            dd = leer("equipos_%s.json" % clave, {}).get("directo") or {}
            h += dd.get("aciertos") or 0
            n += dd.get("resueltas") or 0
        if n:
            out[dep] = (h / float(n), n)
    return out


NOMBRES = {"futbol": u"⚽ Fútbol", "tenis": u"\U0001F3BE Tenis", "baloncesto": u"\U0001F3C0 Baloncesto",
           "hockey": u"\U0001F3D2 Hockey", "americano": u"\U0001F3C8 Fútbol americano", "mma": u"\U0001F94B MMA", "beisbol": u"⚾ Béisbol", "voleibol": u"\U0001F3D0 Voleibol", "rugby": u"\U0001F3C9 Rugby"}
NOMBRES_EN = {"futbol": u"⚽ Football", "tenis": u"\U0001F3BE Tennis", "baloncesto": u"\U0001F3C0 Basketball",
              "hockey": u"\U0001F3D2 Hockey", "americano": u"\U0001F3C8 American football", "mma": u"\U0001F94B MMA", "beisbol": u"⚾ Baseball", "voleibol": u"\U0001F3D0 Volleyball", "rugby": u"\U0001F3C9 Rugby"}
ORDEN_DEP = ("futbol", "tenis", "baloncesto", "hockey", "americano", "mma", "beisbol", "voleibol", "rugby")

TX = {
    "es": {"titulo": u"\U0001F3AF <b>PRONÓSTICOS DEL DÍA</b> · %s\nSportEVLab · próximas 24 horas, calculados con resultados reales. Horas de Madrid.",
           "nada": u"Hoy no hay partidos analizados en las próximas 24 horas en ningún deporte.",
           "analizamos": u"\U0001F4C5 <b>Hoy analizamos %d partidos</b>", "favs": u"⭐ <b>Favoritos más claros</b>",
           "valor": u"\U0001F48E <b>Valor detectado</b> (experimental)",
           "valor_n": u"Nuestra probabilidad × la mejor cuota supera lo apostado en un 5 % o más. Aún no está demostrado que dé beneficio.",
           "igualado": u"⚖ igualado", "mas": u"   … y %d partidos más en la web",
           "dias": [u"lun", u"mar", u"mié", u"jue", u"vie", u"sáb", u"dom"],
           "antes_torneo": u"Antes del torneo", "parrilla": u"Con la parrilla de salida", "antes_clasif": u"Antes de la clasificación",
           "gana": "gana", "podio": "podio", "record": u"\U0001F3C6 <b>Récord público en directo</b>",
           "record_l": u"%s: %s de acierto en %d predicciones",
           "directo": u"\U0001F534 Durante el día: resultados de cada partido aquí y en directo en %sdirecto.html",
           "fin": u"\U0001F310 Todo el análisis: %s\n⚠ Probabilidades estadísticas, no garantizan resultados. Solo +18. Juega con responsabilidad."},
    "en": {"titulo": u"\U0001F3AF <b>TODAY'S PREDICTIONS</b> · %s\nSportEVLab · next 24 hours, calculated from real results. Madrid time (CET).",
           "nada": u"There are no analysed games in the next 24 hours in any sport.",
           "analizamos": u"\U0001F4C5 <b>Today we analyse %d games</b>", "favs": u"⭐ <b>Clearest favourites</b>",
           "valor": u"\U0001F48E <b>Value detected</b> (experimental)",
           "valor_n": u"Our probability × the best odds beats the stake by 5% or more. Not yet proven to be profitable.",
           "igualado": u"⚖ close call", "mas": u"   … and %d more games on the website",
           "dias": [u"Mon", u"Tue", u"Wed", u"Thu", u"Fri", u"Sat", u"Sun"],
           "antes_torneo": u"Before the tournament", "parrilla": u"With the starting grid", "antes_clasif": u"Before qualifying",
           "gana": "win", "podio": "podium", "record": u"\U0001F3C6 <b>Live public record</b>",
           "record_l": u"%s: %s accuracy over %d predictions",
           "directo": u"\U0001F534 During the day: every result here and live at %sdirecto.html",
           "fin": u"\U0001F310 Full analysis: %s\n⚠ Statistical probabilities, results are not guaranteed. 18+ only. Please gamble responsibly."}}


def construir(px, ahora, lang):
    """Mensajes del resumen de la manana en un idioma."""
    T = TX[lang]
    NOM = NOMBRES if lang == "es" else NOMBRES_EN
    cuota = (lambda x: x["cuota"]) if lang == "es" else (lambda x: x.get("cuota_en", ""))
    bloques = [T["titulo"] % ahora.astimezone(TZ).strftime("%d/%m/%Y")]

    if not px:
        bloques.append(T["nada"])
    else:
        cuenta = {}
        for x in px:
            cuenta[x["dep"]] = cuenta.get(x["dep"], 0) + 1
        bloques.append(T["analizamos"] % len(px) + "\n" + "\n".join(u"%s: %d" % (NOM[d], n) for d, n in cuenta.items()))

        # Favoritos mas claros: maximo 3 por deporte
        top, porDep = [], {}
        for x in sorted(px, key=lambda y: -y["prob"]):
            porDep[x["dep"]] = porDep.get(x["dep"], 0) + 1
            if porDep[x["dep"]] <= 3:
                top.append(x)
        lin = [T["favs"]]
        for x in top[:10]:
            lin.append(u"%s %s %s · %s – %s\n   ➡ <b>%s</b> %s%s" % (
                x["ic"], hora(x["fecha"]), e(comp(x["comp"], lang)), e(x["a"]), e(x["b"]), e(pick(x["pick"], lang)), pc(x["prob"]), cuota(x)))
        bloques.append("\n".join(lin))

        # Valor detectado (experimental)
        val = [x for x in px if x.get("valor")]
        if val:
            lin = [T["valor"]]
            for x in sorted(val, key=lambda y: y["fecha"])[:6]:
                k = x["valor"][0]
                lin.append(u"%s %s %s – %s\n   ➡ <b>%s</b> %s%s" % (
                    x["ic"], hora(x["fecha"]), e(x["a"]), e(x["b"]), e(pick(x["nom"].get(k, ""), lang)), pc(x["pr"].get(k)),
                    cuota_txt(x["c"], k, lang)))
            lin.append(T["valor_n"])
            bloques.append("\n".join(lin))

        # Detalle por deporte y competicion
        for dep in ORDEN_DEP:
            ps = [x for x in px if x["dep"] == dep]
            if not ps:
                continue
            comps = []
            for x in sorted(ps, key=lambda y: y["fecha"]):
                if x["comp"] not in comps:
                    comps.append(x["comp"])
            lin = [u"<b>%s</b>" % NOM[dep]]
            for cmp in comps:
                cs = sorted([x for x in ps if x["comp"] == cmp], key=lambda y: -y["prob"])
                lin.append(u"<i>%s</i>" % e(comp(cmp, lang)))
                for x in sorted(cs[:MAX_POR_LIGA], key=lambda y: y["fecha"]):
                    if x["prob"] < 0.55 and dep != "futbol":
                        lin.append(u"%s %s – %s · %s (%s – %s)" % (
                            hora(x["fecha"]), e(x["a"]), e(x["b"]), T["igualado"], pc(x["prob"]), pc(1 - x["prob"])))
                    else:
                        lin.append(u"%s %s – %s · <b>%s %s</b>%s" % (
                            hora(x["fecha"]), e(x["a"]), e(x["b"]), e(pick(x["pick"], lang)), pc(x["prob"]), cuota(x)))
                    if dep == "futbol":
                        lin.append(u"   " + (x["det"] if lang == "es" else x.get("det_en", x["det"])))
                if len(cs) > MAX_POR_LIGA:
                    lin.append(T["mas"] % (len(cs) - MAX_POR_LIGA))
            bloques.append("\n".join(lin))

    # Carreras (F1, MotoGP y golf) en las proximas 72 horas
    for serie, ic in (("f1", u"\U0001F3CE"), ("motogp", u"\U0001F3CD"), ("nascar", u"\U0001F3C1"), ("golf_pga", u"⛳"), ("golf_dp", u"⛳")):
        c = leer("carreras_%s.json" % serie, {})
        pr = c.get("proximo") or {}
        try:
            horas = (fecha(pr["fecha"]) - ahora).total_seconds() / 3600.0
        except Exception:
            continue
        if not pr.get("pilotos") or not (0 < horas <= 72) or pr.get("en_juego"):
            continue
        dia = fecha(pr["fecha"]).astimezone(TZ)
        lin = [u"%s <b>%s · %s</b> (%s %s)" % (ic, e(c.get("nombre", "")), e(pr.get("nombre", "")), T["dias"][dia.weekday()], dia.strftime("%H:%M")),
               u"<i>%s</i>" % (T["antes_torneo"] if serie.startswith("golf") else T["parrilla"] if pr.get("tipo") == "parrilla" else T["antes_clasif"])]
        for i, x in enumerate(pr["pilotos"][:5]):
            if serie.startswith("golf"):
                lin.append(u"%d. <b>%s</b> · %s %s · top 10 %s" % (i + 1, e(x["n"]), T["gana"], pc(x["pw"]), pc(x.get("p10") or 0)))
            else:
                lin.append(u"%d. <b>%s</b> (%s) · %s %s · %s %s" % (i + 1, e(x["n"]), e(x["eq"]), T["gana"], pc(x["pw"]), T["podio"], pc(x["pp"])))
        bloques.append("\n".join(lin))

    rc = record()
    if rc:
        lin = [T["record"]]
        for dep in ORDEN_DEP:
            if dep in rc:
                lin.append(T["record_l"] % (NOM[dep], pc(rc[dep][0]), rc[dep][1]))
        bloques.append("\n".join(lin))

    bloques.append(T["directo"] % WEB)
    bloques.append(T["fin"] % WEB)

    mensajes, actual = [], ""
    for b in bloques:
        if actual and len(actual) + len(b) + 2 > 3800:
            mensajes.append(actual)
            actual = ""
        actual += (("\n\n" if actual else "") + b)
    if actual:
        mensajes.append(actual)
    return mensajes


def main():
    if not TOKEN and not os.environ.get("TELEGRAM_PRUEBA"):
        print("Telegram no configurado (falta TELEGRAM_TOKEN). No se envia nada.")
        return
    ahora = datetime.now(timezone.utc)
    px = partidos(ahora)
    enviados = fallos = 0
    for lang in ("es", "en"):
        mensajes = construir(px, ahora, lang)
        if os.environ.get("TELEGRAM_PRUEBA"):
            print(("\n\n===== %s =====\n" % lang) + "\n\n-----\n".join(mensajes))
            continue
        try:
            for m in mensajes:
                enviar(m, CANALES[lang])
            enviados += 1
            print("Telegram %s (%s): %d mensaje(s) con %d partidos" % (lang, CANALES[lang], len(mensajes), len(px)))
        except Exception as ex:
            fallos += 1
            print("ERROR enviando a Telegram %s (%s): %s" % (lang, CANALES[lang], ex))
    if fallos and not enviados:
        sys.exit(1)


if __name__ == "__main__":
    main()
