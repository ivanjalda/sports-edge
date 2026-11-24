"""Panel del administrador (solo lo ve el dueno en "Mi cuenta").

Hace dos cosas, todas automaticas:
1. data/panel.json  -> resumen de TODOS los motores, de las publicaciones automaticas del dia y de la
   revision diaria. Son datos que ya son publicos en la web (aciertos, pruebas...), solo que juntos.
2. Firebase (solo si existe el secreto FIREBASE_CUENTA) -> datos privados que solo puede leer el dueno:
   usuarios registrados, avisos activos, miembros de los canales de Telegram y correos que quedan hoy en Brevo.
   Se guardan dentro del propio documento del dueno (usuarios/<su uid>, campo "panel_privado"),
   que las reglas de seguridad ya protegen: nadie mas puede leerlo.
"""
import glob
import json
import os
import urllib.request
from datetime import datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Madrid")
except Exception:  # pragma: no cover
    TZ = timezone.utc

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
ADMIN = "community16jalda@gmail.com"
CANALES = {"es": "@sportevlab", "en": "@sportevlab_en"}

LG_DEP = {"nba": "baloncesto", "euroliga": "baloncesto", "eurocup": "baloncesto", "ncaab": "baloncesto", "wnba": "baloncesto",
          "nhl": "hockey", "ncaah": "hockey", "nfl": "americano", "ncaaf": "americano", "ufc": "mma", "mlb": "beisbol",
          "voley": "voleibol", "rug_6n": "rugby", "rug_prem": "rugby", "rug_top14": "rugby", "rug_urc": "rugby",
          "rug_cc": "rugby", "rug_super": "rugby", "lol": "esports"}
NOMBRES = {"ncaab": "NCAA · Baloncesto", "ncaaf": "NCAA · Fútbol americano", "ncaah": "NCAA · Hockey",
           "voley": "NCAA · Voleibol", "ufc": "UFC · MMA", "lol": "League of Legends"}
CARRERA_DEP = {"f1": "motor", "motogp": "motor", "nascar": "motor", "golf_pga": "golf", "golf_dp": "golf"}


def leer(nombre, defecto=None):
    try:
        with open(os.path.join(DATA, nombre), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return defecto


def fecha(x):
    if not x:
        return None
    s = str(x).strip()
    for fmt in ("%Y-%m-%d %H:%M UTC", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%MZ", "%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ") if d else None


def dias_desde(x, ahora):
    d = fecha(x)
    return None if d is None else round((ahora - d).total_seconds() / 86400.0, 1)


def estado_motor(dias, proximos):
    if dias is not None and dias > 21:
        return "temporada"      # sin partidos recientes: fuera de temporada
    if dias is not None and dias > 4:
        return "retraso"        # la fuente lleva dias sin datos nuevos
    return "activo" if proximos else "espera"


# ------------------------------------------------------------------ motores
def motores(ahora):
    out = []

    # Futbol (motor propio con cuotas reales de football-data.co.uk)
    mf = leer("motor_futbol.json", {}) or {}
    st = leer("estadisticas.json", {}) or {}
    pr = leer("predicciones.json", {}) or {}
    tot = ((mf.get("prueba") or {}).get("total") or {})
    proximos = sum(1 for p in pr.get("predicciones") or [] if not p.get("resultado") and (fecha(p.get("fecha")) or ahora) > ahora)
    out.append({"clave": "futbol", "dep": "futbol", "nombre": "Fútbol · %d ligas" % len(mf.get("ligas") or []),
                "prueba": {"n": (tot.get("motor") or {}).get("n"), "acierto": (tot.get("motor") or {}).get("acierto"),
                           "ref": "Cuotas de las casas", "ref_acierto": (tot.get("mercado") or {}).get("acierto")},
                "directo": {"resueltas": st.get("resueltas"), "acierto": st.get("acierto")},
                "proximos": proximos, "datos_hasta": pr.get("actualizado"), "actualizado": pr.get("actualizado"),
                "estado": estado_motor(dias_desde(pr.get("actualizado"), ahora), proximos)})

    # Tenis
    tb = leer("tenis_backtest.json", {}) or {}
    tn = leer("tenis.json", {}) or {}
    t = tb.get("total") or {}
    d = tn.get("directo") or {}
    out.append({"clave": "tenis", "dep": "tenis", "nombre": "Tenis · ATP y WTA",
                "prueba": {"n": t.get("n"), "acierto": t.get("acierto"), "ref": "Mejor ranking", "ref_acierto": t.get("mejor_ranking")},
                "directo": {"resueltas": d.get("resueltas"), "acierto": d.get("acierto"), "apuestas": d.get("apuestas"), "roi": d.get("roi")},
                "proximos": len(tn.get("predicciones") or []), "datos_hasta": tn.get("datos_hasta"), "actualizado": tn.get("actualizado"),
                "estado": estado_motor(tn.get("dias_desde_datos"), len(tn.get("predicciones") or []))})

    # Deportes de equipo
    for f in sorted(glob.glob(os.path.join(DATA, "equipos_*.json"))):
        clave = os.path.basename(f)[8:-5]
        if clave.endswith(("_historial", "_backtest", "_resultados")) or clave not in LG_DEP:
            continue
        e = leer("equipos_%s.json" % clave, {}) or {}
        b = leer("equipos_%s_backtest.json" % clave, {}) or {}
        bt = b.get("total") or {}
        m = b.get("motor") or {}
        d = e.get("directo") or {}
        n_prox = len(e.get("predicciones") or [])
        out.append({"clave": clave, "dep": LG_DEP[clave], "nombre": NOMBRES.get(clave) or e.get("liga") or b.get("liga") or clave,
                    "prueba": {"n": bt.get("n"), "acierto": bt.get("acierto"), "ref": "Elo básico",
                               "ref_acierto": (m.get("elo_basico") or {}).get("acierto")},
                    "directo": {"resueltas": d.get("resueltas"), "acierto": d.get("acierto"), "apuestas": d.get("apuestas"), "roi": d.get("roi")},
                    "proximos": n_prox, "datos_hasta": e.get("datos_hasta"), "actualizado": e.get("actualizado"),
                    "estado": estado_motor(e.get("dias_desde_datos"), n_prox)})

    # Carreras y golf
    for f in sorted(glob.glob(os.path.join(DATA, "carreras_*.json"))):
        clave = os.path.basename(f)[9:-5]
        if clave.endswith(("_historial", "_resultados")) or clave not in CARRERA_DEP:
            continue
        c = leer("carreras_%s.json" % clave, {}) or {}
        m = c.get("motor") or {}
        pp = m.get("prueba_parrilla") or m.get("prueba_previa") or {}
        prox = c.get("proximo") or {}
        d = c.get("directo") or {}
        dias_prox = None
        if prox.get("fecha"):
            dias_prox = (fecha(prox["fecha"]) - ahora).total_seconds() / 86400.0 if fecha(prox["fecha"]) else None
        est = "activo" if (dias_prox is not None and dias_prox <= 10) else ("espera" if prox else "temporada")
        out.append({"clave": clave, "dep": CARRERA_DEP[clave], "nombre": c.get("nombre") or clave,
                    "prueba": {"n": pp.get("carreras"), "acierto": pp.get("favorito_gana"), "ref": "Podio", "ref_acierto": pp.get("podio"),
                               "unidad": "carreras"},
                    "directo": {"resueltas": d.get("carreras"), "acierto": d.get("acierto")},
                    "proximos": 1 if prox else 0, "proximo": prox.get("nombre"), "proximo_fecha": prox.get("fecha"),
                    "datos_hasta": None, "actualizado": c.get("actualizado"), "estado": est})
    return out


# ------------------------------------------------------------------ publicaciones automaticas
def publicaciones(ahora):
    t = leer("telegram_directo.json", {}) or {}
    loc = ahora.astimezone(TZ)
    hoy = loc.strftime("%Y-%m-%d")
    ayer = (loc - timedelta(days=1)).strftime("%Y-%m-%d")
    env = (t.get("enviados") or {}).values()
    return {
        "hoy": hoy, "ayer": ayer,
        "telegram_manana": t.get("manana"), "balance": t.get("balance"), "correo": t.get("correo"),
        "resultados_hoy": sum(1 for v in env if isinstance(v, dict) and v.get("dia") == hoy),
        "resultados_ayer": sum(1 for v in env if isinstance(v, dict) and v.get("dia") == ayer),
        "motor": (leer("predicciones.json", {}) or {}).get("actualizado"),
        "noticias": (leer("noticias.json", {}) or {}).get("actualizado"),
        "asistente": (leer("asistente.json", {}) or {}).get("actualizado"),
        "cuotas": (leer("cuotas.json", {}) or {}).get("actualizado"),
        "records": (leer("records.json", {}) or {}).get("actualizado"),
    }


def rentabilidad():
    mf = leer("motor_futbol.json", {}) or {}
    p = mf.get("prueba") or {}
    v = leer("valor.json", {}) or {}
    return {"futbol_valor_prueba": p.get("valor"), "futbol_regla": p.get("regla_valor"), "valor_publico": v}


def publico(ahora):
    ms = motores(ahora)
    rev = leer("revision.json", {}) or {}
    return {
        "actualizado": ahora.strftime("%Y-%m-%d %H:%M UTC"),
        "motores": ms,
        "totales": {"motores": len(ms), "activos": sum(1 for m in ms if m["estado"] == "activo"),
                    "partidos_prueba": sum((m["prueba"].get("n") or 0) for m in ms if m["prueba"].get("unidad") != "carreras"),
                    "proximos": sum(m["proximos"] or 0 for m in ms if m["dep"] not in ("motor", "golf")),
                    "deportes": len(set(m["dep"] for m in ms)),
                    "archivos": len(glob.glob(os.path.join(DATA, "*.json")))},
        "publicaciones": publicaciones(ahora),
        "rentabilidad": rentabilidad(),
        "revision": {"fecha": rev.get("fecha"), "estado": rev.get("estado"), "errores": rev.get("errores") or [],
                     "avisos": rev.get("avisos") or [], "bien": rev.get("bien") or []},
    }


# ------------------------------------------------------------------ datos privados (Firebase)
def tg_miembros():
    tok = os.environ.get("TELEGRAM_TOKEN")
    out = {}
    if not tok:
        return out
    for lang, canal in CANALES.items():
        try:
            url = "https://api.telegram.org/bot%s/getChatMemberCount?chat_id=%s" % (tok, canal)
            with urllib.request.urlopen(url, timeout=20) as r:
                out[lang] = json.loads(r.read().decode()).get("result")
        except Exception as ex:
            print("Aviso: miembros de %s no disponibles (%s)" % (canal, ex.__class__.__name__))
    return out


def brevo_quedan():
    key = os.environ.get("BREVO_API_KEY")
    if not key:
        return None
    try:
        req = urllib.request.Request("https://api.brevo.com/v3/account", headers={
            "api-key": key, "accept": "application/json", "user-agent": "SportEVLab/1.0 (+https://sportevlab.com)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            c = json.loads(r.read().decode())
        vals = [p.get("credits") for p in c.get("plan", []) if p.get("creditsType") == "sendLimit"]
        vals = [v for v in vals if isinstance(v, (int, float))]
        return int(min(vals)) if vals else None
    except Exception as ex:
        print("Aviso: saldo de Brevo no disponible (%s)" % ex.__class__.__name__)
        return None


def privado(ahora):
    import firebase_admin
    from firebase_admin import credentials, firestore, auth
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(json.loads(os.environ["FIREBASE_CUENTA"])))
    db = firestore.client()
    verif = {}
    admin_uid = None
    pagina = auth.list_users()
    while pagina:
        for u in pagina.users:
            verif[u.uid] = bool(u.email_verified)
            if (u.email or "").lower() == ADMIN:
                admin_uid = u.uid
        pagina = pagina.get_next_page()
    if not admin_uid:
        print("Panel: el administrador aun no tiene cuenta en la web.")
        return
    c = {"total": 0, "verificados": 0, "correo": 0, "correo_es": 0, "correo_en": 0, "telegram_es": 0,
         "telegram_en": 0, "promo": 0, "nuevos_7d": 0, "nuevos_hoy": 0, "deportes": {}}
    hoy = ahora.astimezone(TZ).date()
    for d in db.collection("usuarios").stream():
        u = d.to_dict() or {}
        c["total"] += 1
        if verif.get(d.id):
            c["verificados"] += 1
        if u.get("email_diario") is True:
            c["correo"] += 1
            c["correo_en" if u.get("idioma") == "en" else "correo_es"] += 1
        if u.get("telegram") in ("es", "en"):
            c["telegram_" + u["telegram"]] += 1
        if u.get("promo") is True:
            c["promo"] += 1
        for dep in u.get("deportes") or []:
            c["deportes"][dep] = c["deportes"].get(dep, 0) + 1
        cr = u.get("creado")
        try:
            if cr is not None:
                cr = cr if isinstance(cr, datetime) else None
                if cr and (ahora - cr).days < 7:
                    c["nuevos_7d"] += 1
                if cr and cr.astimezone(TZ).date() == hoy:
                    c["nuevos_hoy"] += 1
        except Exception:
            pass
    datos = {"actualizado": ahora.strftime("%Y-%m-%d %H:%M UTC"), "usuarios": c,
             "telegram": tg_miembros(), "brevo_quedan_hoy": brevo_quedan()}
    db.collection("usuarios").document(admin_uid).set({"panel_privado": datos}, merge=True)
    print("Panel privado actualizado: %d usuarios, Telegram %s" % (c["total"], datos["telegram"]))


def main():
    ahora = datetime.now(timezone.utc)
    # en el vigilante de resultados (cada 10 min) basta con actualizarlo cada media hora
    if os.environ.get("PANEL_CADA_MIN"):
        viejo = leer("panel.json", {}) or {}
        f = fecha(viejo.get("actualizado"))
        if f and (ahora - f).total_seconds() < 60 * float(os.environ["PANEL_CADA_MIN"]):
            print("Panel: actualizado hace poco, no hace falta repetir.")
            return
    p = publico(ahora)
    with open(os.path.join(DATA, "panel.json"), "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, separators=(",", ":"))
    print("Panel: %d motores (%d activos)" % (p["totales"]["motores"], p["totales"]["activos"]))
    if os.environ.get("FIREBASE_CUENTA"):
        try:
            privado(ahora)
        except Exception as ex:
            print("Aviso: panel privado no actualizado (%s: %s)" % (ex.__class__.__name__, str(ex)[:200]))


if __name__ == "__main__":
    main()
