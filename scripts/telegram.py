# -*- coding: utf-8 -*-
"""Sports Edge - Resumen diario a Telegram con TODOS los deportes (solo libreria estandar).
Lee los mismos archivos que la web: nada se inventa. Si un deporte no tiene partidos hoy, no aparece."""
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
CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
WEB = "https://ivanjalda.github.io/sports-edge/"
HORAS = 24
LIGAS_FUT = ["Premier League", "LaLiga", "Serie A", "Bundesliga", "Ligue 1",
             "Primeira Liga", "Eredivisie", "Championship", "Brasileirão", "Liga Profesional", "MLS"]
EQUIPOS = [("baloncesto", u"\U0001F3C0", "Baloncesto", [("nba", "NBA"), ("euroliga", "Euroliga"), ("eurocup", "Eurocup"),
                                                     ("ncaab", "NCAA"), ("wnba", "WNBA")]),
           ("hockey", u"\U0001F3D2", "Hockey", [("nhl", "NHL"), ("ncaah", "NCAA")]),
           ("americano", u"\U0001F3C8", u"F\u00fatbol americano", [("nfl", "NFL"), ("ncaaf", "NCAA")]),
           ("mma", u"\U0001F94B", "MMA", [("ufc", "UFC")]),
           ("beisbol", u"\u26be", u"B\u00e9isbol", [("mlb", "MLB")]),
           ("voleibol", u"\U0001F3D0", "Voleibol", [("voley", "NCAA femenina")])]
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


def cuota_txt(c, k):
    if not c or not c.get("mejor") or not c["mejor"].get(k):
        return ""
    m = c["mejor"][k]
    return u" · cuota %s (%s)" % (("%.2f" % m["c"]).replace(".", ","), e(m.get("casa", "")))


def enviar(texto):
    url = "https://api.telegram.org/bot%s/sendMessage" % TOKEN
    datos = urllib.parse.urlencode({"chat_id": CHAT, "text": texto, "parse_mode": "HTML",
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
        out.append({"dep": "futbol", "ic": u"⚽", "comp": p["liga"], "fecha": p["fecha"], "a": p["local"],
                    "b": p["visitante"], "pick": {"1": p["local"], "X": "Empate", "2": p["visitante"]}[k],
                    "prob": pr[k], "cuota": cuota_txt(c, k), "valor": c.get("valor") if c else None,
                    "nom": {"1": p["local"], "X": "Empate", "2": p["visitante"]}, "pr": pr, "c": c, "det": det})
    for q in leer("tenis.json", {}).get("predicciones", []):
        f = fecha(q["fecha"])
        if not (ahora <= f <= lim):
            continue
        k = "1" if q["p1"] >= q["p2"] else "2"
        c = q.get("cuota")
        out.append({"dep": "tenis", "ic": u"\U0001F3BE", "comp": q.get("torneo", ""), "fecha": q["fecha"],
                    "a": q["j1"], "b": q["j2"], "pick": q["j1"] if k == "1" else q["j2"], "prob": max(q["p1"], q["p2"]),
                    "cuota": cuota_txt(c, k), "valor": c.get("valor") if c else None,
                    "nom": {"1": q["j1"], "2": q["j2"]}, "pr": {"1": q["p1"], "2": q["p2"]}, "c": c,
                    "det": u"%s %s · %s %s" % (e(q["j1"]), pc(q["p1"]), e(q["j2"]), pc(q["p2"]))})
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
                            "prob": max(r["pl"], r["pv"]), "cuota": cuota_txt(c, k),
                            "valor": c.get("valor") if c else None,
                            "nom": {"L": r["local"], "V": r["visitante"]}, "pr": {"L": r["pl"], "V": r["pv"]}, "c": c,
                            "det": u"Local %s · Visitante %s" % (pc(r["pl"]), pc(r["pv"]))})
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
           "hockey": u"\U0001F3D2 Hockey", "americano": u"\U0001F3C8 F\u00fatbol americano", "mma": u"\U0001F94B MMA", "beisbol": u"\u26be B\u00e9isbol", "voleibol": u"\U0001F3D0 Voleibol"}


def main():
    if not TOKEN or not CHAT:
        print("Telegram no configurado (faltan TELEGRAM_TOKEN o TELEGRAM_CHAT_ID). No se envia nada.")
        return
    ahora = datetime.now(timezone.utc)
    px = partidos(ahora)
    bloques = [u"\U0001F3AF <b>PRONÓSTICOS DEL DÍA</b> · %s\nSports Edge · próximas 24 horas, calculados con resultados reales." %
               ahora.astimezone(TZ).strftime("%d/%m/%Y")]

    if not px:
        bloques.append(u"Hoy no hay partidos analizados en las próximas 24 horas en ningún deporte.")
    else:
        cuenta = {}
        for x in px:
            cuenta[x["dep"]] = cuenta.get(x["dep"], 0) + 1
        bloques.append(u"\U0001F4C5 <b>Hoy analizamos %d partidos</b>\n%s" % (
            len(px), "\n".join(u"%s: %d" % (NOMBRES[d], n) for d, n in cuenta.items())))

        # Favoritos mas claros: maximo 3 por deporte
        top, porDep = [], {}
        for x in sorted(px, key=lambda y: -y["prob"]):
            porDep[x["dep"]] = porDep.get(x["dep"], 0) + 1
            if porDep[x["dep"]] <= 3:
                top.append(x)
        lin = [u"⭐ <b>Favoritos más claros</b>"]
        for x in top[:10]:
            lin.append(u"%s %s %s · %s – %s\n   ➡ <b>%s</b> %s%s" % (
                x["ic"], hora(x["fecha"]), e(x["comp"]), e(x["a"]), e(x["b"]), e(x["pick"]), pc(x["prob"]), x["cuota"]))
        bloques.append("\n".join(lin))

        # Valor detectado (experimental)
        val = [x for x in px if x.get("valor")]
        if val:
            lin = [u"\U0001F48E <b>Valor detectado</b> (experimental)"]
            for x in sorted(val, key=lambda y: y["fecha"])[:6]:
                k = x["valor"][0]
                lin.append(u"%s %s %s – %s\n   ➡ <b>%s</b> %s%s" % (
                    x["ic"], hora(x["fecha"]), e(x["a"]), e(x["b"]), e(x["nom"].get(k, "")), pc(x["pr"].get(k)),
                    cuota_txt(x["c"], k)))
            lin.append(u"Nuestra probabilidad × la mejor cuota supera lo apostado en un 5 % o más. Aún no está demostrado que dé beneficio.")
            bloques.append("\n".join(lin))

        # Detalle por deporte y competicion
        for dep in ("futbol", "tenis", "baloncesto", "hockey", "americano", "mma", "beisbol", "voleibol"):
            ps = [x for x in px if x["dep"] == dep]
            if not ps:
                continue
            comps = []
            for x in sorted(ps, key=lambda y: y["fecha"]):
                if x["comp"] not in comps:
                    comps.append(x["comp"])
            lin = [u"<b>%s</b>" % NOMBRES[dep]]
            for cmp in comps:
                cs = sorted([x for x in ps if x["comp"] == cmp], key=lambda y: -y["prob"])
                lin.append(u"<i>%s</i>" % e(cmp))
                for x in sorted(cs[:MAX_POR_LIGA], key=lambda y: y["fecha"]):
                    if x["prob"] < 0.55 and dep != "futbol":
                        lin.append(u"%s %s – %s · ⚖ igualado (%s – %s)" % (
                            hora(x["fecha"]), e(x["a"]), e(x["b"]), pc(x["prob"]), pc(1 - x["prob"])))
                    else:
                        lin.append(u"%s %s – %s · <b>%s %s</b>%s" % (
                            hora(x["fecha"]), e(x["a"]), e(x["b"]), e(x["pick"]), pc(x["prob"]), x["cuota"]))
                    if dep == "futbol":
                        lin.append(u"   " + x["det"])
                if len(cs) > MAX_POR_LIGA:
                    lin.append(u"   … y %d partidos más en la web" % (len(cs) - MAX_POR_LIGA))
            bloques.append("\n".join(lin))

    rc = record()
    if rc:
        lin = [u"\U0001F3C6 <b>Récord público en directo</b>"]
        for dep in ("futbol", "tenis", "baloncesto", "hockey", "americano", "mma", "beisbol", "voleibol"):
            if dep in rc:
                lin.append(u"%s: %s de acierto en %d predicciones" % (NOMBRES[dep], pc(rc[dep][0]), rc[dep][1]))
        bloques.append("\n".join(lin))

    bloques.append(u"\U0001F534 Durante el día: resultados de cada partido aquí y en directo en %sdirecto.html" % WEB)
    bloques.append(u"\U0001F310 Todo el análisis: %s\n⚠ Probabilidades estadísticas, no garantizan resultados. Solo +18. Juega con responsabilidad." % WEB)

    mensajes, actual = [], ""
    for b in bloques:
        if len(actual) + len(b) + 2 > 3800:
            mensajes.append(actual)
            actual = ""
        actual += (("\n\n" if actual else "") + b)
    if actual:
        mensajes.append(actual)
    if os.environ.get("TELEGRAM_PRUEBA"):
        print("\n\n=====\n".join(mensajes))
        return
    try:
        for m in mensajes:
            enviar(m)
        print("Telegram: %d mensaje(s) enviado(s) con %d partidos" % (len(mensajes), len(px)))
    except Exception as ex:
        print("ERROR enviando a Telegram: %s" % ex)
        sys.exit(1)


if __name__ == "__main__":
    main()
