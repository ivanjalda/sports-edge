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
MAX_PICKS = 12

VERDE, OSCURO, GRIS, FONDO, LINEA = "#16a34a", "#0b0f17", "#6b7280", "#f3f4f6", "#e5e7eb"

DEP = {
    "futbol": (u"⚽", u"Fútbol", "Football"), "tenis": (u"\U0001F3BE", "Tenis", "Tennis"),
    "baloncesto": (u"\U0001F3C0", "Baloncesto", "Basketball"), "hockey": (u"\U0001F3D2", "Hockey", "Hockey"),
    "americano": (u"\U0001F3C8", u"Fútbol americano", "American football"), "mma": (u"\U0001F94B", "MMA", "MMA"),
    "beisbol": (u"⚾", u"Béisbol", "Baseball"), "voleibol": (u"\U0001F3D0", "Voleibol", "Volleyball"),
    "rugby": (u"\U0001F3C9", "Rugby", "Rugby"), "motor": (u"\U0001F3C1", "Motor", "Motorsport"), "golf": (u"⛳", "Golf", "Golf")}

WEBS = [
    ("https://equityintrinsic.com/", WEB + "img/equity-intrinsic.jpg", u"\U0001F4C8 Equity Intrinsic",
     u"Análisis de acciones de bolsa y su valor intrínseco.", "Stock analysis and intrinsic value."),
    ("https://nexusterminalalerts.com/", "https://nexusterminalalerts.com/og-image.jpg", u"\U0001F4CA Nexus Terminal Alerts",
     u"Análisis y señales de trading en tiempo real.", "Real-time trading analysis and signals."),
    ("https://dazpremiumfit.com/", "https://dazpremiumfit.com/cdn/shop/files/f8bc49e2-f715-4a8d-aab8-6fbea8d7f3d4_91f710a0-5d71-463a-b4b0-843f4b06fbf4.jpg?v=1740522264&width=800",
     u"\U0001F455 DAZ Premium Fit", u"Ropa deportiva de calidad, marca registrada en EE. UU.", "Quality sportswear, US registered brand."),
    ("https://www.valmontco.com/", "https://www.valmontco.com/cdn/shop/files/Gemini_Generated_Image_rn5qnprn5qnprn5q_332c8c1b-d38f-49f7-b964-fe5d442752d6.png?v=1783524650&width=800",
     u"\U0001F393 Valmont & Co.", u"Academia de inversión: libros, guías y cursos.", "Investing academy: books, guides and courses.")]

TX = {
    "es": {"asunto": u"\U0001F3AF Pronósticos de hoy · %s", "hola": "Hola", "intro": u"Estos son los pronósticos de hoy, calculados con resultados reales.",
           "tus": u"Tus pronósticos de hoy", "top": u"Los más claros de hoy", "nofav": u"Hoy no hay partidos de tus favoritos. Te dejamos los más claros de todos los deportes.",
           "ninguno": u"Hoy no hay partidos analizados en las próximas 24 horas.", "ayer": u"Cómo nos fue ayer", "acierto": u"acertados",
           "carreras": u"Carreras y torneos", "gana": "gana", "podio": "podio", "top10": "top 10", "noticias": u"Noticias del día",
           "webs": u"Nuestras otras webs", "visitar": u"Visitar →", "boton": u"Ver todos los pronósticos", "directo": u"Resultados en directo",
           "empate": "Empate", "cuota": "cuota", "aviso": u"Probabilidades estadísticas: no garantizan resultados. Solo mayores de 18 años. Juega con responsabilidad.",
           "porque": u"Recibes este correo porque activaste el correo diario en tu cuenta de SportEVLab.",
           "baja": u"Dejar de recibirlo o cambiar el idioma", "hoy": "hoy", "favs": u"Tus favoritos"},
    "en": {"asunto": u"\U0001F3AF Today's predictions · %s", "hola": "Hi", "intro": u"Here are today's predictions, calculated from real results.",
           "tus": u"Your predictions for today", "top": u"Today's clearest picks", "nofav": u"There are no games for your favourites today. Here are the clearest picks from every sport.",
           "ninguno": u"There are no analysed games in the next 24 hours.", "ayer": u"How we did yesterday", "acierto": u"correct",
           "carreras": u"Races and tournaments", "gana": "win", "podio": "podium", "top10": "top 10", "noticias": u"Today's news",
           "webs": u"Our other websites", "visitar": u"Visit →", "boton": u"See all predictions", "directo": u"Live results",
           "empate": "Draw", "cuota": "odds", "aviso": u"Statistical probabilities: results are not guaranteed. 18+ only. Please gamble responsibly.",
           "porque": u"You get this email because you turned on the daily email in your SportEVLab account.",
           "baja": u"Unsubscribe or change language", "hoy": "today", "favs": u"Your favourites"}}


def e(s):
    return tg.e(s)


def pc(x):
    return tg.pc(x)


# ------------------------------------------------------------- contenido comun (igual para todos)
def carreras(ahora):
    out = []
    for serie, dep in (("f1", "motor"), ("motogp", "motor"), ("golf_pga", "golf"), ("golf_dp", "golf")):
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


def contenido(ahora):
    return {"picks": tg.partidos(ahora), "ayer": tg.resultados(ahora), "carreras": carreras(ahora),
            "noticias": tg.leer("noticias.json", {})}


# ------------------------------------------------------------- correo de cada usuario
def elegir(picks, deportes, equipos):
    eq = set(equipos or [])

    def sigue(x):
        return x["a"] in eq or x["b"] in eq or x["pick"] in eq

    favs = [x for x in picks if x["dep"] in (deportes or []) or sigue(x)]
    if favs:
        # primero los equipos que sigue; luego reparto entre sus deportes para que no se lo coma uno solo
        favs.sort(key=lambda x: (0 if sigue(x) else 1, -x["prob"]))
        tope = max(3, -(-MAX_PICKS // max(1, len(set(x["dep"] for x in favs)))))
        sel, n = [], {}
        for x in favs:
            n[x["dep"]] = n.get(x["dep"], 0) + 1
            if sigue(x) or n[x["dep"]] <= tope:
                sel.append(x)
        return sel[:MAX_PICKS], True
    top, n = [], {}
    for x in sorted(picks, key=lambda y: -y["prob"]):
        n[x["dep"]] = n.get(x["dep"], 0) + 1
        if n[x["dep"]] <= 3:
            top.append(x)
    return top[:MAX_PICKS], False


def titulo(t):
    return (u'<tr><td style="padding:22px 24px 8px;font:700 13px Arial,sans-serif;letter-spacing:1px;text-transform:uppercase;color:%s">%s</td></tr>'
            % (VERDE, t))


def html_correo(u, C, ahora, lang):
    T = TX[lang]
    sel, son_favs = elegir(C["picks"], u.get("deportes"), u.get("equipos"))
    eq = set(u.get("equipos") or [])
    f_loc = ahora.astimezone(tg.TZ)
    filas = []
    # Cabecera
    filas.append(u'<tr><td style="background:%s;padding:20px 24px"><a href="%s" style="text-decoration:none;font:800 24px Arial,sans-serif;color:#fff">'
                 u'Sport<span style="color:#22c55e">EV</span><span style="color:#eab308">Lab</span></a>'
                 u'<div style="font:13px Arial,sans-serif;color:#9ca3af;margin-top:4px">%s</div></td></tr>'
                 % (OSCURO, WEB, f_loc.strftime("%d/%m/%Y")))
    nombre = (u.get("nombre") or "").split(" ")[0]
    filas.append(u'<tr><td style="padding:22px 24px 0;font:16px Arial,sans-serif;color:#111">%s%s,<br><span style="color:%s;font-size:14px">%s</span></td></tr>'
                 % (T["hola"], (" " + e(nombre)) if nombre else "", GRIS, T["intro"]))
    # Pronosticos
    filas.append(titulo(T["tus"] if son_favs else T["top"]))
    if (u.get("deportes") or u.get("equipos")) and not son_favs and sel:
        filas.append(u'<tr><td style="padding:0 24px 6px;font:13px Arial,sans-serif;color:%s">%s</td></tr>' % (GRIS, T["nofav"]))
    if not sel:
        filas.append(u'<tr><td style="padding:0 24px;font:14px Arial,sans-serif;color:%s">%s</td></tr>' % (GRIS, T["ninguno"]))
    for x in sel:
        pick = T["empate"] if x["pick"] == "Empate" else x["pick"]
        sigue = x["a"] in eq or x["b"] in eq or x["pick"] in eq
        cuota = x["cuota"].replace(u"cuota", T["cuota"]).lstrip(u" ·") if x["cuota"] else ""
        filas.append(
            u'<tr><td style="padding:4px 24px"><table width="100%%" cellpadding="0" cellspacing="0" style="border:1px solid %s;border-radius:10px;background:%s">'
            u'<tr><td style="padding:10px 12px;font:12px Arial,sans-serif;color:%s">%s %s · %s %s%s</td>'
            u'<td rowspan="2" align="right" style="padding:10px 12px;font:800 20px Arial,sans-serif;color:%s;white-space:nowrap">%s</td></tr>'
            u'<tr><td style="padding:0 12px 10px;font:14px Arial,sans-serif;color:#111">%s – %s<br>\U0001F3AF <b style="color:%s">%s</b>'
            u'<span style="color:%s;font-size:12px">%s</span></td></tr></table></td></tr>'
            % (LINEA, "#f0fdf4" if sigue else "#fff", GRIS, DEP.get(x["dep"], ("", "", ""))[0], e(x["comp"]), T["hoy"] if tg.fecha(x["fecha"]).astimezone(tg.TZ).date() == f_loc.date() else "",
               tg.hora(x["fecha"]), u" · ⭐" if sigue else "", VERDE, pc(x["prob"]), e(x["a"]), e(x["b"]), VERDE, e(pick), GRIS,
               (u"<br>" + cuota) if cuota else ""))
    # Carreras
    cs = [c for c in C["carreras"] if not u.get("deportes") or c["dep"] in u["deportes"]]
    if cs:
        filas.append(titulo(T["carreras"]))
        for c in cs:
            lin = []
            for i, p in enumerate(c["pilotos"]):
                extra = (u"%s %s" % (T["top10"], pc(p.get("p10") or 0))) if c["golf"] else (u"%s %s" % (T["podio"], pc(p.get("pp"))))
                lin.append(u"%d. <b>%s</b> · %s %s · %s" % (i + 1, e(p["n"]), T["gana"], pc(p["pw"]), extra))
            dia = tg.fecha(c["fecha"]).astimezone(tg.TZ)
            filas.append(u'<tr><td style="padding:4px 24px;font:14px Arial,sans-serif;color:#111">%s <b>%s · %s</b> <span style="color:%s;font-size:12px">%s</span><br>%s</td></tr>'
                         % (DEP[c["dep"]][0], e(c["comp"]), e(c["nombre"]), GRIS, dia.strftime("%d/%m %H:%M"), "<br>".join(lin)))
    # Ayer
    if C["ayer"]:
        filas.append(titulo(T["ayer"]))
        tot_a = sum(v[0] for v in C["ayer"].values())
        tot_n = sum(v[1] for v in C["ayer"].values())
        lin = [u"<b style='font-size:18px;color:%s'>%d / %d</b> %s (%s)" % (VERDE, tot_a, tot_n, T["acierto"], pc(tot_a / float(tot_n)) if tot_n else "")]
        for d, (a, n) in sorted(C["ayer"].items(), key=lambda z: -z[1][1]):
            ic, es, en = DEP.get(d, ("", d, d))
            lin.append(u"%s %s: %d / %d" % (ic, es if lang == "es" else en, a, n))
        filas.append(u'<tr><td style="padding:0 24px;font:14px Arial,sans-serif;color:#111;line-height:1.6">%s</td></tr>' % "<br>".join(lin))
    # Boton
    filas.append(u'<tr><td align="center" style="padding:22px 24px 6px"><a href="%s" style="display:inline-block;background:%s;color:#fff;text-decoration:none;'
                 u'font:700 15px Arial,sans-serif;padding:13px 26px;border-radius:10px">%s</a>'
                 u'<div style="margin-top:10px"><a href="%sdirecto.html" style="font:13px Arial,sans-serif;color:%s">\U0001F534 %s</a></div></td></tr>'
                 % (WEB, VERDE, T["boton"], WEB, VERDE, T["directo"]))
    # Noticias
    nots = (C["noticias"].get(lang) or [])[:5]
    if nots:
        filas.append(titulo(T["noticias"]))
        for n in nots:
            filas.append(u'<tr><td style="padding:3px 24px;font:14px Arial,sans-serif"><a href="%s" style="color:#111;text-decoration:none">• %s</a> '
                         u'<span style="color:%s;font-size:12px">%s</span></td></tr>' % (e(n.get("url")), e(n.get("t")), GRIS, e(n.get("fuente"))))
    # Otras webs (solo si lo acepto)
    if u.get("promo"):
        filas.append(titulo(T["webs"]))
        celdas = []
        for url, img, nom, des, den in WEBS:
            celdas.append(u'<td width="50%%" valign="top" style="padding:6px"><a href="%s" style="text-decoration:none;color:#111">'
                          u'<img src="%s" width="250" alt="" style="width:100%%;max-width:250px;height:130px;object-fit:cover;border-radius:10px;display:block;background:%s">'
                          u'<div style="font:700 14px Arial,sans-serif;margin-top:6px">%s</div><div style="font:12px Arial,sans-serif;color:%s">%s</div>'
                          u'<div style="font:700 12px Arial,sans-serif;color:%s;margin-top:3px">%s</div></a></td>'
                          % (url, img, LINEA, e(nom), GRIS, des if lang == "es" else den, VERDE, T["visitar"]))
        filas.append(u'<tr><td style="padding:0 18px"><table width="100%%" cellpadding="0" cellspacing="0"><tr>%s</tr><tr>%s</tr></table></td></tr>'
                     % ("".join(celdas[:2]), "".join(celdas[2:])))
    # Pie
    filas.append(u'<tr><td style="padding:24px;font:12px Arial,sans-serif;color:%s;line-height:1.6;border-top:1px solid %s">\U0001F51E %s<br>%s<br>'
                 u'<a href="%scuenta.html#avisos" style="color:%s">%s</a><br>SportEVLab · Community16 LLC · New Mexico, USA</td></tr>'
                 % (GRIS, LINEA, T["aviso"], T["porque"], WEB, VERDE, T["baja"]))
    cuerpo = u"".join(filas)
    return (u'<!DOCTYPE html><html lang="%s"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>'
            u'<body style="margin:0;background:%s"><table width="100%%" cellpadding="0" cellspacing="0" style="background:%s"><tr><td align="center" style="padding:16px 8px">'
            u'<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%%;background:#fff;border-radius:14px;overflow:hidden">%s</table>'
            u'</td></tr></table></body></html>' % (lang, FONDO, FONDO, cuerpo))


# ------------------------------------------------------------- Brevo
def brevo(metodo, ruta, datos=None):
    req = urllib.request.Request("https://api.brevo.com/v3" + ruta, method=metodo,
                                 data=json.dumps(datos).encode() if datos is not None else None,
                                 headers={"api-key": BREVO, "accept": "application/json", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        t = r.read().decode() or "{}"
        return json.loads(t)


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
        except urllib.error.HTTPError as ex:
            mal += 1
            print("Error enviando a un suscriptor: %s %s" % (ex.code, ex.read()[:200]))
        except Exception as ex:
            mal += 1
            print("Error enviando a un suscriptor: %s" % ex)
    print("Correo diario: %d enviados, %d con error" % (ok, mal))
    if mal and not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
