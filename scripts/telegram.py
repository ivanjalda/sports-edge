# -*- coding: utf-8 -*-
"""Sports Edge - Envio diario a Telegram (solo libreria estandar)."""
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
LIGAS = ["Premier League", "LaLiga", "Serie A", "Bundesliga", "Ligue 1"]


def leer(nombre, defecto):
    try:
        with open(os.path.join("data", nombre), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return defecto


def e(s):
    return html.escape(str(s if s is not None else ""))


def pc(x):
    return ("%d%%" % round(x * 100)) if isinstance(x, (int, float)) else "Sin datos"


def fecha(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def enviar(texto):
    url = "https://api.telegram.org/bot%s/sendMessage" % TOKEN
    datos = urllib.parse.urlencode({"chat_id": CHAT, "text": texto, "parse_mode": "HTML",
                                    "disable_web_page_preview": "true"}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=datos), timeout=30) as r:
        r.read()


def mejor(p):
    m = {"1": p["p_local"], "X": p["p_empate"], "2": p["p_visitante"]}
    k = max(m, key=m.get)
    return k, (p["local"] if k == "1" else (p["visitante"] if k == "2" else "Empate"))


def bloque_partido(p):
    hora = fecha(p["fecha"]).astimezone(TZ).strftime("%H:%M")
    _, nombre = mejor(p)
    m = p.get("mercados") or {}
    l = [u"\U0001F552 %s <b>%s</b> - <b>%s</b>" % (hora, e(p["local"]), e(p["visitante"])),
         u"   1: %s \u00b7 X: %s \u00b7 2: %s" % (pc(p["p_local"]), pc(p["p_empate"]), pc(p["p_visitante"])),
         u"   \u27a1 M\u00e1s probable: %s" % e(nombre),
         u"   \u26bd +2,5: %s \u00b7 Ambos marcan: %s \u00b7 Gol 1\u00aa parte: %s" %
         (pc(m.get("over25")), pc(m.get("btts")), pc(m.get("ht_gol")))]
    g = p.get("goleadores")
    if g:
        todos = g.get("local", []) + g.get("visitante", [])
        todos.sort(key=lambda x: -x["p"])
        if todos:
            l.append(u"   \U0001F3AF Gol: " + ", ".join("%s (%s)" % (e(x["n"]), pc(x["p"])) for x in todos[:3]))
        else:
            l.append(u"   \U0001F3AF Gol: Sin datos")
    return "\n".join(l)


def main():
    if not TOKEN or not CHAT:
        print("Telegram no configurado (faltan TELEGRAM_TOKEN o TELEGRAM_CHAT_ID). No se envia nada.")
        return
    ahora = datetime.now(timezone.utc)
    preds = leer("predicciones.json", {}).get("predicciones", [])
    hist = leer("historial.json", {}).get("predicciones", [])
    stats = leer("estadisticas.json", {})

    proximos = [p for p in preds if ahora <= fecha(p["fecha"]) <= ahora + timedelta(hours=24)]
    bloques = [u"\U0001F4CA <b>SPORTS EDGE</b> \u00b7 " + ahora.astimezone(TZ).strftime("%d/%m/%Y")]

    if proximos:
        for liga in LIGAS:
            ps = sorted([p for p in proximos if p["liga"] == liga], key=lambda x: x["fecha"])
            if not ps:
                continue
            bloques.append(u"\u26bd <b>%s</b>" % e(liga))
            for p in ps:
                bloques.append(bloque_partido(p))
    else:
        bloques.append("Hoy no hay partidos analizados en las pr\u00f3ximas 24 horas.")

    ayer = [p for p in hist if p.get("resultado") and ahora - timedelta(hours=36) <= fecha(p["fecha"]) <= ahora]
    if ayer:
        ayer.sort(key=lambda x: x["fecha"])
        lineas = [u"\U0001F4C8 <b>Resultados recientes</b>"]
        ok = 0
        for p in ayer:
            k, _ = mejor(p)
            bien = (k == p["resultado"])
            ok += 1 if bien else 0
            lineas.append(u"%s %s %s %s" % (u"\u2705" if bien else u"\u274C", e(p["local"]), e(p["marcador"]), e(p["visitante"])))
        lineas.append("Aciertos: %d de %d" % (ok, len(ayer)))
        bloques.append("\n".join(lineas))

    if stats.get("acierto") is not None:
        bloques.append("Acierto global: %s (%d predicciones resueltas)" % (pc(stats["acierto"]), stats.get("resueltas", 0)))
    bloques.append(u"\u26a0 Probabilidades estad\u00edsticas, no garantizan resultados. Solo +18.")

    mensajes = []
    actual = ""
    for b in bloques:
        if len(actual) + len(b) + 2 > 3800:
            mensajes.append(actual)
            actual = ""
        actual += (("\n\n" if actual else "") + b)
    if actual:
        mensajes.append(actual)

    try:
        for m in mensajes:
            enviar(m)
        print("Telegram: %d mensaje(s) enviado(s)" % len(mensajes))
    except Exception as ex:
        print("ERROR enviando a Telegram: %s" % ex)
        sys.exit(1)


if __name__ == "__main__":
    main()
