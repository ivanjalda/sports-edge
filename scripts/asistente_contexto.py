# -*- coding: utf-8 -*-
"""SportEVLab - Datos para el asistente virtual (solo libreria estandar).

Escribe data/asistente.json con un resumen en texto de TODO lo que la web sabe ahora mismo:
pronosticos de los proximos 3 dias, resultados recientes con acierto o fallo, record publico,
carreras y torneos, y las respuestas a las dudas frecuentes de la web.
El asistente (Cloudflare Worker + Gemini) solo puede contestar con esto: asi no se inventa nada.
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import telegram as tg  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DEP_ES = {"futbol": u"Fútbol", "tenis": "Tenis", "baloncesto": "Baloncesto", "hockey": "Hockey",
          "americano": u"Fútbol americano", "mma": "MMA", "beisbol": u"Béisbol", "voleibol": "Voleibol",
          "rugby": "Rugby", "esports": "Esports (League of Legends)", "motor": "Motor", "golf": "Golf"}
PAGINA = {"futbol": "futbol.html", "tenis": "tenis.html", "motor": "carreras.html", "golf": "carreras.html?grupo=golf"}

FAQ = u"""DUDAS FRECUENTES DE LA WEB (sportevlab.com)
- SportEVLab publica probabilidades calculadas por un motor propio con resultados reales. NO es una casa de apuestas: no acepta apuestas ni maneja dinero.
- Deportes: fútbol (Premier, LaLiga, Serie A, Bundesliga, Ligue 1, Portugal, Países Bajos, Championship, Brasil, Argentina, MLS), tenis (ATP y WTA), baloncesto (NBA, Euroliga, Eurocup, NCAA, WNBA), hockey (NHL, NCAA), fútbol americano (NFL, NCAA), MMA (UFC), béisbol (MLB), voleibol (NCAA femenina), rugby (Seis Naciones, Premiership, Top 14, URC, Champions Cup, Super Rugby), League of Legends, Fórmula 1, MotoGP, NASCAR y golf (PGA Tour, DP World Tour).
- Páginas: Inicio, En directo (directo.html, resultados en vivo), una página por deporte, Estadísticas (historial público de aciertos), Récords, Aprender (glosario, calculadora, gestión de banca y reglas de cada deporte) y Mi cuenta (cuenta.html).
- Cuenta gratis en Mi cuenta (cuenta.html) con Google o con correo y contraseña. Con cuenta se ven todos los pronósticos (sin cuenta solo los primeros de cada lista), se eligen deportes y equipos favoritos y se activan los avisos.
- Avisos (solo usuarios registrados, en Mi cuenta → Mis avisos): correo diario cada mañana (pronósticos, resultados de ayer y noticias) y canales de Telegram: español t.me/sportevlab, inglés t.me/sportevlab_en.
- Borrar la cuenta: Mi cuenta → Ajustes → «Borrar mi cuenta y todos mis datos». Darse de baja del correo: enlace al final de cada correo o Mi cuenta → Mis avisos.
- Contacto: contacto@sportevlab.com. Páginas legales: legal.html (privacidad, cookies, aviso legal, juego responsable).
- Juego responsable: solo mayores de 18 años. Ayuda gratuita: España FEJAR 900 200 225 (jugarbien.es), EE. UU. 1-800-GAMBLER, Reino Unido GamCare 0808 8020 133.
- Cómo funciona el motor: fuerza de cada equipo o jugador (Elo) según contra quién gana o pierde, ventaja de jugar en casa, descanso y forma reciente; en fútbol se calculan goles esperados; en carreras se simulan miles de carreras. Se valida con temporadas que el motor no ha visto.
- Probabilidad implícita = 1 / cuota. Valor esperado = probabilidad × cuota − 1. «Valor detectado» (experimental) = nuestra probabilidad × la mejor cuota supera lo apostado en un 5 % o más; aún no está demostrado que dé beneficio.
- Las horas son de Madrid."""


def leer(nombre, defecto):
    try:
        with open(os.path.join(DATA, nombre), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return defecto


DIAS = (u"lun", u"mar", u"mié", u"jue", u"vie", u"sáb", u"dom")


def loc(s):
    d = tg.fecha(s).astimezone(tg.TZ)
    return u"%s %s" % (DIAS[d.weekday()], d.strftime("%d/%m %H:%M"))


def recientes(ahora):
    """Pronosticos resueltos en las ultimas 48 h: linea con acierto o fallo."""
    desde = ahora - timedelta(hours=48)
    lin = []
    for p in leer("historial.json", {}).get("predicciones", []):
        try:
            if p.get("resultado") and desde <= tg.fecha(p["fecha"]) <= ahora:
                pr = {"1": p["p_local"], "X": p["p_empate"], "2": p["p_visitante"]}
                k = max(pr, key=pr.get)
                nom = {"1": p["local"], "X": "Empate", "2": p["visitante"]}
                lin.append((p["fecha"], u"Fútbol · %s · %s – %s · dijimos %s %s · salió %s · %s" % (
                    p.get("liga", ""), p["local"], p["visitante"], nom[k], tg.pc(pr[k]), nom.get(p["resultado"], p["resultado"]),
                    "ACIERTO" if k == p["resultado"] else "FALLO")))
        except Exception:
            continue
    for q in leer("tenis_historial.json", {}).get("predicciones", []):
        try:
            if q.get("resultado") and desde <= tg.fecha(q["fecha"]) <= ahora:
                k = "1" if q["p1"] >= q["p2"] else "2"
                lin.append((q["fecha"], u"Tenis · %s · %s – %s · dijimos %s %s · ganó %s · %s" % (
                    q.get("torneo", ""), q["j1"], q["j2"], q["j1"] if k == "1" else q["j2"], tg.pc(max(q["p1"], q["p2"])),
                    q["j1"] if q["resultado"] == "1" else q["j2"], "ACIERTO" if k == q["resultado"] else "FALLO")))
        except Exception:
            continue
    for dep, _ic, _n, ligas in tg.EQUIPOS:
        for clave, nombre in ligas:
            for r in leer("equipos_%s_historial.json" % clave, {}).get("predicciones", []):
                try:
                    if r.get("resultado") and desde <= tg.fecha(r["fecha"]) <= ahora:
                        k = "L" if r["pl"] >= r["pv"] else "V"
                        gan = r["local"] if r["resultado"] == "L" else r["visitante"] if r["resultado"] == "V" else "Empate"
                        lin.append((r["fecha"], u"%s · %s · %s – %s · dijimos %s %s · ganó %s · %s" % (
                            DEP_ES.get(dep, dep), nombre, r["local"], r["visitante"], r["local"] if k == "L" else r["visitante"],
                            tg.pc(max(r["pl"], r["pv"])), gan, "ACIERTO" if k == r["resultado"] else "FALLO")))
                except Exception:
                    continue
    lin.sort(key=lambda x: x[0], reverse=True)
    return [u"%s · %s" % (loc(f), t) for f, t in lin[:160]]


def carreras(ahora):
    out = []
    for serie, nombre_dep in (("f1", "Motor"), ("motogp", "Motor"), ("nascar", "Motor"), ("golf_pga", "Golf"), ("golf_dp", "Golf")):
        c = leer("carreras_%s.json" % serie, {})
        if not c:
            continue
        golf = serie.startswith("golf")
        pr = c.get("proximo") or {}
        if pr.get("pilotos"):
            lin = [u"%s · %s · PRÓXIMA: %s (%s)%s" % (nombre_dep, c.get("nombre", ""), pr.get("nombre", ""), loc(pr["fecha"]) if pr.get("fecha") else "",
                                                    " · en juego" if pr.get("en_juego") else "")]
            for i, x in enumerate(pr["pilotos"][:10]):
                if golf:
                    lin.append(u"  %d. %s · gana %s · top 10 %s" % (i + 1, x["n"], tg.pc(x["pw"]), tg.pc(x.get("p10") or 0)))
                else:
                    lin.append(u"  %d. %s (%s) · gana %s · podio %s" % (i + 1, x["n"], x.get("eq", ""), tg.pc(x["pw"]), tg.pc(x.get("pp") or 0)))
            out.append("\n".join(lin))
        else:
            out.append(u"%s · %s · ahora mismo no hay próxima carrera o torneo con lista de participantes (temporada terminada o sin publicar)." % (
                nombre_dep, c.get("nombre", "")))
        h = leer("carreras_%s_historial.json" % serie, {})
        res = [p for p in (h.get("predicciones") or []) if p.get("resultado")]
        if res:
            p = res[-1]
            r = p["resultado"]
            out.append(u"  Última resuelta: %s · ganó %s · nuestro favorito %s (%s) · %s" % (
                p.get("nombre", ""), r.get("ganador_n", ""), (p.get("fav") or {}).get("n", ""), tg.pc((p.get("fav") or {}).get("pw") or 0),
                "ACIERTO" if r.get("acierto") else "FALLO"))
    return out


def main():
    ahora = datetime.now(timezone.utc)
    tg.HORAS = 48
    px = sorted(tg.partidos(ahora), key=lambda x: x["fecha"])
    partes = [u"DATOS DE SPORTEVLAB · actualizado el %s %s (hora de Madrid)" % (DIAS[ahora.astimezone(tg.TZ).weekday()], ahora.astimezone(tg.TZ).strftime("%d/%m/%Y %H:%M")), FAQ]

    rc = tg.record()
    if rc:
        partes.append(u"RÉCORD PÚBLICO EN DIRECTO (predicciones publicadas antes de cada partido)\n" + "\n".join(
            u"- %s: %s de acierto en %d predicciones" % (DEP_ES.get(d, d), tg.pc(v[0]), v[1]) for d, v in rc.items() if v[0] is not None))
    ay = tg.resultados(ahora)
    if ay:
        a, n = sum(v[0] for v in ay.values()), sum(v[1] for v in ay.values())
        partes.append(u"ÚLTIMAS 36 HORAS: %d de %d acertados\n" % (a, n) + "\n".join(
            u"- %s: %d de %d" % (DEP_ES.get(d, d), v[0], v[1]) for d, v in ay.items()))

    lin = [u"PRONÓSTICOS DE LOS PRÓXIMAS 48 HORAS (%d partidos). Formato: deporte · competición · fecha · partido · pronóstico y probabilidad · detalle · cuota" % len(px)]
    for x in px[:450]:
        det = (x.get("det") or "") if x["dep"] == "futbol" else ""
        lin.append((u"- %s · %s · %s · %s – %s · %s %s · %s%s%s" % (
            DEP_ES.get(x["dep"], x["dep"]), x["comp"], loc(x["fecha"]), x["a"], x["b"], x["pick"], tg.pc(x["prob"]),
            det.replace("&amp;", "&"), (x.get("cuota") or "").replace("&amp;", "&"), u" · VALOR DETECTADO" if x.get("valor") else "")).replace(u" ·  · ", u" · ").rstrip(u" ·"))
    if len(px) > 450:
        lin.append(u"(y %d partidos más en la web)" % (len(px) - 450))
    if not px:
        lin.append(u"No hay partidos analizados en las próximas 48 horas.")
    partes.append("\n".join(lin))
    partes.append(u"CARRERAS Y TORNEOS\n" + "\n".join(carreras(ahora)))
    rec = recientes(ahora)
    partes.append(u"RESULTADOS RECIENTES (últimas 48 h)\n" + ("\n".join(rec) if rec else u"Sin resultados en las últimas 48 horas."))

    texto = "\n\n".join(partes)
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "asistente.json"), "w", encoding="utf-8") as f:
        json.dump({"actualizado": ahora.strftime("%Y-%m-%dT%H:%M:%SZ"), "texto": texto}, f, ensure_ascii=False)
    print("Asistente: contexto de %d caracteres (%d partidos, %d resultados recientes)" % (len(texto), len(px), len(rec)))


if __name__ == "__main__":
    main()
