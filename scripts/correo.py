# -*- coding: utf-8 -*-
"""SportEVLab - Correo diario a los usuarios registrados que lo han activado en "Mis avisos".

- Solo se envia a quien marco "Si, quiero recibir el correo diario" y tiene el correo confirmado.
- Cada persona lo recibe en su idioma (espanol o ingles) y con sus deportes y equipos favoritos primero.
- Contenido real, el mismo que la web: pronosticos de hoy, como nos fue ayer, carreras, noticias
  y (solo si lo acepto) novedades de nuestras otras webs.
- Cada usuario lo recibe como mucho una vez al dia (se apunta en su ficha de Firebase).
- Antes de enviar mira cuantos correos quedan hoy en Brevo y no se pasa del limite.

Llaves (secretos de GitHub): BREVO_API_KEY y FIREBASE_CUENTA.
Pruebas: CORREO_PRUEBA=direccion@ejemplo.com manda un ejemplo solo a esa direccion.
         CORREO_VER=1 guarda el ejemplo en correo_ejemplo_es.html / _en.html sin enviar nada.
"""
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import telegram as tg  # noqa: E402  (reutilizamos la lectura de pronosticos del resumen de Telegram)

WEB = "https://sportevlab.com/"
REMITENTE = {"name": "SportEVLab", "email": "pronosticos@sportevlab.com"}
BREVO = os.environ.get("BREVO_API_KEY", "").strip()
PRUEBA = os.environ.get("CORREO_PRUEBA", "").strip()
VER = os.environ.get("CORREO_VER", "").strip()
MAX_PICKS = 24

VERDE, OSCURO, GRIS, FONDO, LINEA = "#16a34a", "#0b0f17", "#6b7280", "#f3f4f6", "#e5e7eb"

DEP = {
    "futbol": (u"⚽", u"Fútbol", "Football"), "tenis": (u"\U0001F3BE", "Tenis", "Tennis"),
    "baloncesto": (u"\U0001F3C0", "Baloncesto", "Basketball"), "hockey": (u"\U0001F3D2", "Hockey", "Hockey"),
    "americano": (u"\U0001F3C8", u"Fútbol americano", "American football"), "mma": (u"\U0001F94B", "MMA", "MMA"),
    "beisbol": (u"⚾", u"Béisbol", "Baseball"), "voleibol": (u"\U0001F3D0", "Voleibol", "Volleyball"),
    "rugby": (u"\U0001F3C9", "Rugby", "Rugby"), "esports": (u"\U0001F3AE", "Esports", "Esports"), "motor": (u"\U0001F3C1", "Motor", "Motorsport"), "golf": (u"⛳", "Golf", "Golf")}

WEBS = [
    ("https://equityintrinsic.com/", WEB + "img/equity-intrinsic.jpg", u"\U0001F4C8 Equity Intrinsic",
     u"Análisis de acciones de bolsa y su valor intrínseco.", "Stock analysis and intrinsic value."),
    ("https://nexusterminalalerts.com/", "https://nexusterminalalerts.com/og-image.jpg", u"\U0001F4CA Nexus Terminal Alerts",
     u"Análisis y señales de trading en tiempo real.", "Real-time trading analysis and signals."),
    ("https://dazpremiumfit.com/", "https://dazpremiumfit.com/cdn/shop/files/f8bc49e2-f715-4a8d-aab8-6fbea8d7f3d4_91f710a0-5d71-463a-b4b0-843f4b06fbf4.jpg?v=1740522264&width=800",
     u"\U0001F455 DAZ Premium Fit", u"Ropa deportiva de calidad, marca registrada en EE. UU.", "Quality sportswear, US registered brand."),
    ("https://www.valmontco.com/", "https://www.valmontco.com/cdn/shop/files/Gemini_Generated_Image_rn5qnprn5qnprn5q_332c8c1b-d38f-49f7-b964-fe5d442752d6.png?v=1783524650&width=800",
     u"\U0001F393 Valmont & Co.", u"Academia de inversión: libros, guías y cursos.", "Investing academy: books, guides and courses."),
    ("https://dazmond.com/", "https://dazmond.com/cdn/shop/files/Gemini_Generated_Image_d07g62d07g62d07g.png?v=1785778922&width=800",
     u"\U0001F48E DAZMOND", u"Ropa y complementos de lujo a precio de saldo.", "Luxury clothing and accessories at outlet prices.")]

TX = {
    "es": {"asunto": u"\U0001F3AF Pronósticos de hoy · %s", "hola": "Hola", "intro": u"Tu resumen de hoy: pronósticos calculados con resultados reales, cómo nos fue ayer y lo más importante del día.",
           "k_hoy": u"Partidos analizados hoy", "k_deps": u"Deportes con pronóstico", "k_ayer": u"Acierto de ayer", "k_rec": u"Récord en directo", "k_pred": u"predicciones",
           "pick": u"⭐ Pick del día", "pick_s": u"El pronóstico más claro de hoy", "tus": u"\U0001F3AF Tus pronósticos de hoy", "top": u"\U0001F3AF Los pronósticos más claros de hoy",
           "nofav": u"Hoy no hay partidos de tus favoritos. Te dejamos los más claros de todos los deportes.",
           "elige": u"⭐ Elige tus deportes y equipos favoritos y te los pondremos primero cada mañana.", "elige_b": u"Elegir favoritos",
           "ninguno": u"Hoy no hay partidos analizados en las próximas 24 horas.", "ayer": u"\U0001F4CA Cómo nos fue ayer", "acierto": u"acertados",
           "carreras": u"\U0001F3C1 Carreras y torneos", "gana": "gana", "podio": "podio", "top10": "top 10", "noticias": u"\U0001F4F0 Noticias del día",
           "leer": u"Leer →", "webs": u"\U0001F310 Nuestras otras webs", "visitar": u"Visitar →", "boton": u"Ver todos los pronósticos", "directo": u"Resultados en directo",
           "empate": "Empate", "cuota": "cuota", "hoy": "Hoy", "man": u"Mañana", "rec": u"\U0001F3C6 Récord del día", "rec_b": u"Ver todos los récords →",
           "aprende": u"\U0001F393 Aprende en 1 minuto", "aprende_b": u"Más en Aprender →",
           "aviso": u"Probabilidades estadísticas: no garantizan resultados. Solo mayores de 18 años. Juega con responsabilidad.",
           "porque": u"Recibes este correo porque activaste el correo diario en tu cuenta de SportEVLab.",
           "baja": u"Dejar de recibirlo o cambiar el idioma", "espacio": u"Mi espacio"},
    "en": {"asunto": u"\U0001F3AF Today's predictions · %s", "hola": "Hi", "intro": u"Your daily summary: predictions calculated from real results, how we did yesterday and the day's highlights.",
           "k_hoy": u"Games analysed today", "k_deps": u"Sports with predictions", "k_ayer": u"Yesterday's accuracy", "k_rec": u"Live record", "k_pred": u"predictions",
           "pick": u"⭐ Pick of the day", "pick_s": u"Today's clearest prediction", "tus": u"\U0001F3AF Your predictions for today", "top": u"\U0001F3AF Today's clearest predictions",
           "nofav": u"There are no games for your favourites today. Here are the clearest picks from every sport.",
           "elige": u"⭐ Choose your favourite sports and teams and we'll put them first every morning.", "elige_b": u"Choose favourites",
           "ninguno": u"There are no analysed games in the next 24 hours.", "ayer": u"\U0001F4CA How we did yesterday", "acierto": u"correct",
           "carreras": u"\U0001F3C1 Races and tournaments", "gana": "win", "podio": "podium", "top10": "top 10", "noticias": u"\U0001F4F0 Today's news",
           "leer": u"Read →", "webs": u"\U0001F310 Our other websites", "visitar": u"Visit →", "boton": u"See all predictions", "directo": u"Live results",
           "empate": "Draw", "cuota": "odds", "hoy": "Today", "man": "Tomorrow", "rec": u"\U0001F3C6 Record of the day", "rec_b": u"See all records →",
           "aprende": u"\U0001F393 Learn in 1 minute", "aprende_b": u"More in Learn →",
           "aviso": u"Statistical probabilities: results are not guaranteed. 18+ only. Please gamble responsibly.",
           "porque": u"You get this email because you turned on the daily email in your SportEVLab account.",
           "baja": u"Unsubscribe or change language", "espacio": u"My space"}}

# Un concepto distinto cada dia (rota solo)
APRENDE = [
    (u"Probabilidad implícita", u"Es la probabilidad que esconde una cuota: 1 ÷ cuota. Una cuota de 2,00 equivale al 50 %. Si nuestra probabilidad es mayor, la cuota paga más de lo que debería.",
     u"Implied probability", u"The probability hidden in the odds: 1 ÷ odds. Odds of 2.00 mean 50%. If our probability is higher, the odds pay more than they should."),
    (u"Valor esperado (EV)", u"Probabilidad × cuota − 1. Si sale positivo, a la larga esa apuesta gana dinero; si sale negativo, lo pierde. Es la idea que da nombre a SportEVLab.",
     u"Expected value (EV)", u"Probability × odds − 1. If it is positive, the bet wins money in the long run; if negative, it loses. It's the idea behind the name SportEVLab."),
    (u"Gestión de banca", u"Decide un dinero solo para apostar y no arriesgues más del 1–2 % en cada apuesta. Así una mala racha no te deja sin nada.",
     u"Bankroll management", u"Set aside money only for betting and never risk more than 1–2% on a single bet. That way a bad run won't wipe you out."),
    (u"Margen de la casa", u"Si sumas las probabilidades implícitas de todas las opciones, pasan del 100 %. Ese exceso es lo que gana la casa. Por eso conviene comparar casas.",
     u"Bookmaker margin", u"Add up the implied probabilities of every outcome and they exceed 100%. That extra is the bookmaker's cut. That's why comparing bookmakers matters."),
    (u"Criterio de Kelly", u"Fórmula que dice cuánto apostar según tu ventaja. Es muy agresiva, así que se suele usar ¼ de Kelly. Pruébala en nuestra calculadora.",
     u"Kelly criterion", u"A formula that says how much to stake based on your edge. It is very aggressive, so a quarter Kelly is usually used. Try it in our calculator."),
    (u"Puntuación Elo", u"Cada equipo tiene una puntuación que sube al ganar y baja al perder, más o menos según la fuerza del rival. Es una de las bases de nuestro motor.",
     u"Elo rating", u"Every team has a rating that goes up when it wins and down when it loses, more or less depending on the opponent. It's one of the foundations of our engine."),
    (u"Rachas y varianza", u"Un 70 % de acierto también falla 3 de cada 10. Las rachas malas son normales: lo que cuenta son cientos de apuestas, no un día.",
     u"Streaks and variance", u"A 70% pick still fails 3 times out of 10. Bad runs are normal: what counts is hundreds of bets, not a single day."),
    (u"Comparar cuotas", u"La misma apuesta puede pagar 1,80 en una casa y 1,95 en otra. A la larga esa diferencia es enorme: busca siempre la mejor cuota.",
     u"Shopping for odds", u"The same bet can pay 1.80 at one bookmaker and 1.95 at another. Over time that gap is huge: always look for the best odds.")]


def e(s):
    return tg.e(s)


def pc(x):
    return tg.pc(x)


# ------------------------------------------------------------- contenido comun (igual para todos)
def carreras(ahora):
    out = []
    for serie, dep in (("f1", "motor"), ("motogp", "motor"), ("nascar", "motor"), ("golf_pga", "golf"), ("golf_dp", "golf")):
        c = tg.leer("carreras_%s.json" % serie, {})
        pr = c.get("proximo") or {}
        try:
            f = tg.fecha(pr["fecha"])
        except Exception:
            continue
        if not pr.get("pilotos") or pr.get("en_juego") or not (ahora < f <= ahora + timedelta(hours=72)):
            continue
        out.append({"serie": serie, "dep": dep, "comp": c.get("nombre", ""), "nombre": pr.get("nombre", ""), "fecha": pr["fecha"],
                    "pilotos": pr["pilotos"][:3], "golf": serie.startswith("golf")})
    return out


def record_dia(dia_n):
    """Un record real calculado con nuestros datos, distinto cada dia."""
    comps = [c for c in tg.leer("records.json", {}).get("competiciones", []) if c.get("dep") in DEP]
    if not comps:
        return None
    c = comps[dia_n % len(comps)]
    tipo = (dia_n // len(comps)) % 3
    for t in (tipo, (tipo + 1) % 3, (tipo + 2) % 3):
        if t == 0 and c.get("racha"):
            r = c["racha"]
            return c, (u"Racha más larga: <b>%s</b>, %d victorias seguidas" % (e(r["quien"]), r["n"]),
                       u"Longest winning streak: <b>%s</b>, %d wins in a row" % (e(r["quien"]), r["n"]))
        if t == 1 and c.get("mayor_victoria"):
            r = c["mayor_victoria"]
            return c, (u"Mayor victoria: <b>%s</b> %s a %s (%s)" % (e(r["quien"]), e(r["marcador"]), e(r["rival"]), e(r["fecha"][:10])),
                       u"Biggest win: <b>%s</b> %s against %s (%s)" % (e(r["quien"]), e(r["marcador"]), e(r["rival"]), e(r["fecha"][:10])))
        if t == 2 and c.get("mejor_temporada") and c["mejor_temporada"].get("v") is not None:
            r = c["mejor_temporada"]
            return c, (u"Mejor temporada: <b>%s</b> en %s, %d–%d" % (e(r["quien"]), e(r["temporada"]), r["v"], r.get("d", 0)),
                       u"Best season: <b>%s</b> in %s, %d–%d" % (e(r["quien"]), e(r["temporada"]), r["v"], r.get("d", 0)))
    return None


def contenido(ahora):
    dia_n = ahora.astimezone(tg.TZ).timetuple().tm_yday
    rc = tg.record()
    h = sum((a or 0) * n for a, n in rc.values())
    n = sum(n for _a, n in rc.values())
    return {"picks": tg.partidos(ahora), "ayer": tg.resultados(ahora), "carreras": carreras(ahora),
            "noticias": tg.leer("noticias.json", {}), "record": (h / float(n), n) if n else None,
            "rec_dia": record_dia(dia_n), "aprende": APRENDE[dia_n % len(APRENDE)]}


# ------------------------------------------------------------- correo de cada usuario
def elegir(picks, deportes, equipos):
    eq = set(equipos or [])

    def sigue(x):
        return x["a"] in eq or x["b"] in eq or x["pick"] in eq

    favs = [x for x in picks if x["dep"] in (deportes or []) or sigue(x)]
    base, son_favs = (favs, True) if favs else (picks, False)
    base = sorted(base, key=lambda x: (0 if sigue(x) else 1, -x["prob"]))
    # reparto entre deportes para que no se lo coma uno solo (los equipos que sigue siempre entran)
    tope = 4 if not son_favs else max(3, -(-MAX_PICKS // max(1, len(set(x["dep"] for x in base)))))
    sel, n = [], {}
    for x in base:
        n[x["dep"]] = n.get(x["dep"], 0) + 1
        if sigue(x) or n[x["dep"]] <= tope:
            sel.append(x)
    return sel[:MAX_PICKS], son_favs


def seccion(t):
    return (u'<div style="padding:28px 6px 10px;font:800 15px Arial,sans-serif;letter-spacing:.6px;text-transform:uppercase;color:%s;'
            u'border-top:1px solid %s;margin-top:18px">%s</div>' % (OSCURO, LINEA, t))


def caja(pct, dentro, movil=100):
    """Bloque que ocupa un porcentaje del ancho (toda la pantalla entre todos); en el movil se pone debajo."""
    return (u'<div class="m%d" style="display:inline-block;vertical-align:top;width:%.4f%%;font-size:14px">'
            u'<div style="margin:6px;text-align:left">%s</div></div>' % (movil, pct, dentro))


def reparto(n, maximo):
    """Porcentaje de cada bloque para llenar la fila: n bloques, como mucho 'maximo' por fila."""
    return 100.0 / max(1, min(n, maximo))


def fila(cajas):
    return u'<div style="font-size:0;text-align:left">%s</div>' % "".join(cajas)


def cuando(f, T, hoy):
    d = tg.fecha(f).astimezone(tg.TZ)
    return (T["hoy"] if d.date() == hoy else T["man"] if d.date() == hoy + timedelta(days=1) else d.strftime("%d/%m")) + " " + d.strftime("%H:%M")


def cuota_de(x, T):
    c = x.get("cuota_en") if T is TX["en"] else x.get("cuota")
    return c.lstrip(u" ·") if c else ""


def html_correo(u, C, ahora, lang):
    T = TX[lang]
    sel, son_favs = elegir(C["picks"], u.get("deportes"), u.get("equipos"))
    eq = set(u.get("equipos") or [])
    hoy = ahora.astimezone(tg.TZ).date()
    F = []
    nombre = (u.get("nombre") or "").split(" ")[0]
    F.append(u'<div style="padding:4px 6px 14px"><div style="font:700 22px Arial,sans-serif;color:%s">%s%s \U0001F44B</div>'
             u'<div style="font:15px Arial,sans-serif;color:%s;line-height:1.5;margin-top:4px">%s</div></div>'
             % (OSCURO, T["hola"], (" " + e(nombre)) if nombre else "", GRIS, T["intro"]))

    # Cifras del dia
    ay = C["ayer"]
    ta, tn = sum(v[0] for v in ay.values()), sum(v[1] for v in ay.values())
    kp = [(str(len(C["picks"])), T["k_hoy"]),
          (str(len(set(x["dep"] for x in C["picks"]))), T["k_deps"]),
          (pc(ta / float(tn)) if tn else u"—", T["k_ayer"] + (u" · %d/%d" % (ta, tn) if tn else "")),
          (pc(C["record"][0]) if C["record"] else u"—", T["k_rec"] + (u" · %d %s" % (C["record"][1], T["k_pred"]) if C["record"] else ""))]
    F.append(fila([caja(25, u'<div style="background:%s;border-radius:12px;padding:16px 10px;text-align:center">'
                             u'<div style="font:800 28px Arial,sans-serif;color:%s">%s</div><div style="font:12px Arial,sans-serif;color:%s;margin-top:2px">%s</div></div>'
                             % (FONDO, VERDE, v, GRIS, k), 50) for v, k in kp]))

    # Pick del dia + record + aprende (lado a lado en pantallas anchas)
    arriba = []
    if sel:
        con_c = [x for x in sel if x.get("cuota")]
        p = max(con_c or sel, key=lambda x: x["prob"])
        pk = T["empate"] if p["pick"] == "Empate" else p["pick"]
        arriba.append(caja(40, u'<div style="background:%s;border-radius:14px;padding:18px 20px;min-height:130px">'
                       u'<table width="100%%" cellpadding="0" cellspacing="0"><tr><td valign="top">'
                       u'<div style="font:800 13px Arial,sans-serif;letter-spacing:.6px;text-transform:uppercase;color:#eab308">%s</div>'
                       u'<div style="font:12px Arial,sans-serif;color:#9ca3af;margin-top:2px">%s · %s %s · %s</div>'
                       u'<div style="font:16px Arial,sans-serif;color:#fff;margin-top:10px">%s – %s</div>'
                       u'<div style="font:800 22px Arial,sans-serif;color:#22c55e;margin-top:4px">\U0001F3AF %s</div>'
                       u'<div style="font:13px Arial,sans-serif;color:#d1d5db;margin-top:4px">%s</div></td>'
                       u'<td align="right" valign="middle" style="padding-left:10px"><div style="font:800 40px Arial,sans-serif;color:#22c55e">%s</div></td></tr></table></div>'
                       % (OSCURO, T["pick"], T["pick_s"], DEP.get(p["dep"], ("",))[0], e(p["comp"]), cuando(p["fecha"], T, hoy),
                          e(p["a"]), e(p["b"]), e(pk), cuota_de(p, T), pc(p["prob"]))))
    if C.get("rec_dia"):
        c, txt = C["rec_dia"]
        arriba.append(caja(30, u'<div style="background:%s;border-radius:14px;padding:18px;min-height:130px">'
                      u'<div style="font:800 13px Arial,sans-serif;letter-spacing:.6px;text-transform:uppercase;color:%s">%s</div>'
                      u'<div style="font:12px Arial,sans-serif;color:%s;margin-top:6px">%s %s</div><div style="font:14px Arial,sans-serif;color:#111;margin-top:4px;line-height:1.45">%s</div>'
                      u'<a href="%srecords.html" style="display:inline-block;margin-top:8px;font:700 13px Arial,sans-serif;color:%s;text-decoration:none">%s</a></div>'
                      % (FONDO, OSCURO, T["rec"], GRIS, DEP.get(c["dep"], ("",))[0], e(c.get("nombre")), txt[0] if lang == "es" else txt[1], WEB, VERDE, T["rec_b"])))
    ap = C["aprende"]
    arriba.append(caja(30, u'<div style="background:%s;border-radius:14px;padding:18px;min-height:130px">'
                  u'<div style="font:800 13px Arial,sans-serif;letter-spacing:.6px;text-transform:uppercase;color:%s">%s</div>'
                  u'<div style="font:700 14px Arial,sans-serif;color:#111;margin-top:6px">%s</div><div style="font:13px Arial,sans-serif;color:#374151;margin-top:4px;line-height:1.45">%s</div>'
                  u'<a href="%saprender.html" style="display:inline-block;margin-top:8px;font:700 13px Arial,sans-serif;color:%s;text-decoration:none">%s</a></div>'
                  % (FONDO, OSCURO, T["aprende"], ap[0] if lang == "es" else ap[2], ap[1] if lang == "es" else ap[3], WEB, VERDE, T["aprende_b"])))
    F.append(fila(arriba))

    # Pronosticos: un bloque por deporte, varios bloques por fila en pantallas anchas
    F.append(seccion(T["tus"] if son_favs else T["top"]))
    if (u.get("deportes") or u.get("equipos")) and not son_favs and sel:
        F.append(u'<div style="padding:0 6px 8px;font:13px Arial,sans-serif;color:%s">%s</div>' % (GRIS, T["nofav"]))
    if not sel:
        F.append(u'<div style="padding:0 6px;font:14px Arial,sans-serif;color:%s">%s</div>' % (GRIS, T["ninguno"]))
    orden = []
    for x in sel:
        if x["dep"] not in orden:
            orden.append(x["dep"])
    bloques = []
    for d in orden:
        ic, es_, en_ = DEP.get(d, ("", d, d))
        filas = []
        for x in [y for y in sel if y["dep"] == d]:
            pk = T["empate"] if x["pick"] == "Empate" else x["pick"]
            sig = x["a"] in eq or x["b"] in eq or x["pick"] in eq
            cu = cuota_de(x, T)
            filas.append(u'<tr style="background:%s"><td width="58" valign="top" style="padding:10px 6px 10px 12px;font:12px Arial,sans-serif;color:%s;border-top:1px solid %s">%s</td>'
                         u'<td valign="top" style="padding:10px 6px;font:14px Arial,sans-serif;color:#111;border-top:1px solid %s">'
                         u'<div style="font-size:11px;color:%s">%s%s</div>%s – %s<br><b style="color:%s">\U0001F3AF %s</b>%s</td>'
                         u'<td width="56" align="right" valign="middle" style="padding:10px 12px;font:800 18px Arial,sans-serif;color:%s;border-top:1px solid %s">%s</td></tr>'
                         % ("#f0fdf4" if sig else "#ffffff", GRIS, LINEA, cuando(x["fecha"], T, hoy).replace(" ", "<br>"), LINEA, GRIS, e(x["comp"]), u" · ⭐" if sig else "",
                            e(x["a"]), e(x["b"]), VERDE, e(pk), (u'<span style="font-size:12px;color:%s"> · %s</span>' % (GRIS, cu)) if cu else "", VERDE, LINEA, pc(x["prob"])))
        bloques.append(caja(reparto(len(orden), 3), u'<div style="border:1px solid %s;border-radius:12px;overflow:hidden">'
                                 u'<div style="background:%s;padding:10px 12px;font:700 14px Arial,sans-serif;color:%s">%s %s</div>'
                                 u'<table width="100%%" cellpadding="0" cellspacing="0">%s</table></div>'
                                 % (LINEA, FONDO, OSCURO, ic, es_ if lang == "es" else en_, "".join(filas))))
    F.append(fila(bloques))
    if not (u.get("deportes") or u.get("equipos")):
        F.append(u'<div style="margin:12px 6px 0;background:#fefce8;border:1px solid #fde68a;border-radius:12px;padding:12px 14px;font:13px Arial,sans-serif;color:#713f12">'
                 u'%s <a href="%scuenta.html#favoritos" style="color:%s;font-weight:700">%s →</a></div>' % (T["elige"], WEB, VERDE, T["elige_b"]))
    F.append(u'<div style="text-align:center;padding:20px 6px 4px"><a href="%s" style="display:inline-block;background:%s;color:#fff;text-decoration:none;'
             u'font:700 15px Arial,sans-serif;padding:14px 30px;border-radius:10px;margin:4px">%s</a>'
             u'<a href="%sdirecto.html" style="display:inline-block;border:2px solid %s;color:%s;text-decoration:none;font:700 15px Arial,sans-serif;padding:12px 22px;border-radius:10px;margin:4px">\U0001F534 %s</a></div>'
             % (WEB, VERDE, T["boton"], WEB, VERDE, VERDE, T["directo"]))

    # Carreras y ayer
    cs = [c for c in C["carreras"] if not u.get("deportes") or c["dep"] in u["deportes"]]
    if cs:
        F.append(seccion(T["carreras"]))
        bl = []
        for c in cs:
            lin = []
            for i, p in enumerate(c["pilotos"]):
                extra = (u"%s %s" % (T["top10"], pc(p.get("p10") or 0))) if c["golf"] else (u"%s %s" % (T["podio"], pc(p.get("pp"))))
                lin.append(u"%s <b>%s</b> · %s %s · %s" % ([u"\U0001F947", u"\U0001F948", u"\U0001F949"][i], e(p["n"]), T["gana"], pc(p["pw"]), extra))
            bl.append(caja(reparto(len(cs), 4), u'<div style="border:1px solid %s;border-radius:12px;padding:14px;font:14px Arial,sans-serif;color:#111;line-height:1.7">'
                                u'<b>%s %s · %s</b><br><span style="color:%s;font-size:12px">%s</span><br>%s</div>'
                                % (LINEA, DEP[c["dep"]][0], e(c["comp"]), e(c["nombre"]), GRIS, cuando(c["fecha"], T, hoy), "<br>".join(lin))))
        F.append(fila(bl))
    if ay:
        F.append(seccion(T["ayer"]))
        bl = []
        for d, (a, n) in sorted(ay.items(), key=lambda z: -z[1][1]):
            ic, es_, en_ = DEP.get(d, ("", d, d))
            bl.append(caja(reparto(len(ay), 8), u'<div style="border:1px solid %s;border-radius:10px;padding:12px;text-align:center;font:12px Arial,sans-serif;color:%s">'
                                u'%s %s<div style="font:800 20px Arial,sans-serif;color:%s;margin-top:3px">%d/%d</div></div>'
                                % (LINEA, GRIS, ic, es_ if lang == "es" else en_, OSCURO, a, n), 50))
        F.append(fila(bl))

    # Noticias con foto
    nots = (C["noticias"].get(lang) or [])[:8]
    if nots:
        F.append(seccion(T["noticias"]))
        bl = []
        for n in nots:
            img = (u'<img src="%s" width="290" alt="" style="width:100%%;height:190px;object-fit:cover;border-radius:10px;display:block;background:%s">'
                   % (e(n["img"]), FONDO)) if n.get("img") else ""
            bl.append(caja(25, u'<a href="%s" style="text-decoration:none;color:#111">%s'
                                u'<div style="font:700 14px Arial,sans-serif;line-height:1.35;margin-top:8px">%s</div>'
                                u'<div style="font:12px Arial,sans-serif;color:%s;margin-top:4px">%s · <span style="color:%s;font-weight:700">%s</span></div></a>'
                                % (e(n.get("url")), img, e(n.get("t")), GRIS, e(n.get("fuente")), VERDE, T["leer"])))
        F.append(fila(bl))

    # Otras webs (solo si lo acepto)
    if u.get("promo"):
        F.append(seccion(T["webs"]))
        bl = []
        for url, img, nom, des, den in WEBS:
            bl.append(caja(reparto(len(WEBS), 5), u'<a href="%s" style="text-decoration:none;color:#111">'
                                u'<img src="%s" width="290" alt="%s" style="width:100%%;height:170px;object-fit:cover;border-radius:10px;display:block;background:%s">'
                                u'<div style="font:700 14px Arial,sans-serif;margin-top:8px">%s</div><div style="font:12px Arial,sans-serif;color:%s">%s</div>'
                                u'<div style="font:700 12px Arial,sans-serif;color:%s;margin-top:3px">%s</div></a>'
                                % (url, e(img), e(nom), FONDO, e(nom), GRIS, des if lang == "es" else den, VERDE, T["visitar"]), 50))
        F.append(fila(bl))

    pie = (u'<div style="padding:26px 16px;font:12px Arial,sans-serif;color:%s;line-height:1.7;text-align:center;background:%s">'
           u'<a href="%s" style="color:%s;font-weight:700;text-decoration:none">sportevlab.com</a> · <a href="%scuenta.html#espacio" style="color:%s;text-decoration:none">%s</a><br>'
           u'\U0001F51E %s<br>%s<br><a href="%scuenta.html#avisos" style="color:%s">%s</a><br>SportEVLab · Community16 LLC · 500 4th St NW, Suite 102 #1327, Albuquerque, NM 87102, USA<br><a href="%slegal.html#privacidad" style="color:#6b7280">Privacidad / Privacy</a></div>'
           % (GRIS, FONDO, WEB, VERDE, WEB, VERDE, T["espacio"], T["aviso"], T["porque"], WEB, VERDE, T["baja"], WEB))
    cab = (u'<div style="background:%s;padding:26px 16px 22px;text-align:center">'
           u'<a href="%s" style="display:inline-block"><img src="%simg/correo-logo.png" width="320" alt="SportEVLab" '
           u'style="width:320px;max-width:80%%;height:auto;display:block;margin:0 auto;border:0;color:#ffffff;font:800 30px Arial,sans-serif"></a>'
           u'<div style="font:13px Arial,sans-serif;color:#9ca3af;margin-top:10px;letter-spacing:.5px">%s</div></div>'
           % (OSCURO, WEB, WEB, ahora.astimezone(tg.TZ).strftime("%d/%m/%Y")))
    return (u'<!DOCTYPE html><html lang="%s"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            u'<meta name="color-scheme" content="light"><style>@media only screen and (max-width:760px){.m100{width:100%%!important}.m50{width:50%%!important}}</style></head><body style="margin:0;padding:0;background:#ffffff">'
            u'<div style="width:100%%;background:#ffffff">%s<div style="padding:16px 10px 10px">%s</div>%s</div></body></html>'
            % (lang, cab, "".join(F), pie))


# ------------------------------------------------------------- Brevo
def brevo(metodo, ruta, datos=None):
    req = urllib.request.Request("https://api.brevo.com/v3" + ruta, method=metodo,
                                 data=json.dumps(datos).encode() if datos is not None else None,
                                 headers={"api-key": BREVO, "accept": "application/json", "content-type": "application/json",
                                          "user-agent": "SportEVLab/1.0 (+https://sportevlab.com)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            t = r.read().decode() or "{}"
            return json.loads(t)
    except urllib.error.HTTPError as ex:
        # mostramos lo que dice Brevo para saber exactamente que falla
        cuerpo = ex.read().decode("utf-8", "replace")[:400]
        raise RuntimeError("Brevo respondio %s en %s: %s" % (ex.code, ruta, cuerpo))


def quedan_hoy():
    """Correos que quedan hoy en el plan de Brevo (None si no se sabe)."""
    try:
        cuenta = brevo("GET", "/account")
        vals = [p.get("credits") for p in cuenta.get("plan", []) if p.get("creditsType") == "sendLimit" and isinstance(p.get("credits"), (int, float))]
        return int(min(vals)) if vals else None
    except Exception as ex:
        print("No se pudo consultar el saldo de Brevo: %s" % ex)
        return None


def enviar(para, nombre, asunto, html, lang):
    brevo("POST", "/smtp/email", {
        "sender": REMITENTE, "to": [{"email": para, "name": nombre or para}], "subject": asunto, "htmlContent": html,
        "headers": {"List-Unsubscribe": "<%scuenta.html#avisos>" % WEB}, "tags": ["diario", "diario-" + lang]})


# ------------------------------------------------------------- usuarios (Firebase)
def usuarios():
    import firebase_admin
    from firebase_admin import credentials, firestore, auth
    firebase_admin.initialize_app(credentials.Certificate(json.loads(os.environ["FIREBASE_CUENTA"])))
    db = firestore.client()
    out = []
    for d in db.collection("usuarios").where("email_diario", "==", True).stream():
        u = d.to_dict()
        u["_ref"] = d.reference
        try:
            cu = auth.get_user(d.id)
        except Exception:
            continue
        if not cu.email or not cu.email_verified or cu.disabled:
            continue
        u["email"] = cu.email
        out.append(u)
    return out


def main():
    ahora = datetime.now(timezone.utc)
    dia = ahora.astimezone(tg.TZ).strftime("%Y-%m-%d")
    C = contenido(ahora)
    fecha_txt = ahora.astimezone(tg.TZ).strftime("%d/%m")

    if VER:
        for lang in ("es", "en"):
            u = {"nombre": "Prueba", "deportes": ["futbol", "baloncesto"], "equipos": [], "promo": True}
            with open("correo_ejemplo_%s.html" % lang, "w", encoding="utf-8") as f:
                f.write(html_correo(u, C, ahora, lang))
        print("Ejemplos guardados (no se envia nada).")
        return
    if not BREVO:
        print("Falta BREVO_API_KEY: no se envia nada.")
        return
    if PRUEBA:
        for lang in ("es", "en"):
            u = {"nombre": "", "deportes": [], "equipos": [], "promo": True}
            enviar(PRUEBA, "", TX[lang]["asunto"] % fecha_txt + (" (prueba)" if lang == "es" else " (test)"), html_correo(u, C, ahora, lang), lang)
        print("Correos de prueba (español e inglés) enviados a %s" % PRUEBA)
        return
    if not os.environ.get("FIREBASE_CUENTA"):
        print("Falta FIREBASE_CUENTA: no se envia nada.")
        return

    lista = [u for u in usuarios() if u.get("ultimo_correo") != dia]
    print("Suscriptores pendientes hoy: %d" % len(lista))
    if not lista:
        return
    quedan = quedan_hoy()
    if quedan is not None and quedan < len(lista):
        print("AVISO: hoy solo quedan %d correos en Brevo para %d suscriptores. Hay que ampliar el plan." % (quedan, len(lista)))
        lista = lista[:max(0, quedan)]
    ok = mal = 0
    for u in lista:
        lang = "en" if u.get("idioma") == "en" else "es"
        try:
            enviar(u["email"], u.get("nombre"), TX[lang]["asunto"] % fecha_txt, html_correo(u, C, ahora, lang), lang)
            u["_ref"].update({"ultimo_correo": dia})
            ok += 1
        except Exception as ex:
            mal += 1
            print("Error enviando a un suscriptor: %s" % ex)
    print("Correo diario: %d enviados, %d con error" % (ok, mal))
    if mal and not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
