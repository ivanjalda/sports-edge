"""SportEVLab Premium: sincroniza los pagos de Stripe con las cuentas de la web y los canales privados de Telegram.

Funciona solo, cada 10 minutos (lo lanza el vigilante de Telegram). Hace esto:
1. Telegram (bot Premium): encuentra los dos canales privados (ES y EN) en cuanto el bot es administrador,
   y apunta que persona de Telegram ha entrado con el enlace personal de cada usuario.
2. Stripe: mira quien tiene la suscripcion activa (pagada con nuestro enlace de pago).
3. Firebase: marca a cada usuario como Premium o no, con su fecha de renovacion, y le crea su enlace
   personal (de un solo uso) al canal privado de su idioma.
4. Si alguien deja de pagar: se le quita Premium, se anula su enlace y se le saca del canal privado.

Todo es opcional: si faltan las claves (STRIPE_KEY, TELEGRAM_PREMIUM_TOKEN, FIREBASE_CUENTA) no hace nada.
La configuracion publica (precio, enlace de pago, canales) esta en data/premium.json.
"""
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CFG = "premium.json"
ADMIN = "community16jalda@gmail.com"
STRIPE = os.environ.get("STRIPE_KEY", "").strip()
TGP = os.environ.get("TELEGRAM_PREMIUM_TOKEN", "").strip()
ACTIVOS = ("active", "trialing", "past_due")   # past_due: Stripe aun esta reintentando el cobro


def leer():
    try:
        with open(os.path.join(DATA, CFG), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def guardar(cfg):
    with open(os.path.join(DATA, CFG), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)


# ------------------------------------------------------------------ Telegram (bot Premium)
def tg(metodo, **params):
    url = "https://api.telegram.org/bot%s/%s" % (TGP, metodo)
    datos = urllib.parse.urlencode({k: (json.dumps(v) if isinstance(v, (list, dict, bool)) else v)
                                    for k, v in params.items()}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=datos), timeout=30) as r:
        res = json.loads(r.read().decode())
    if not res.get("ok"):
        raise RuntimeError(res.get("description"))
    return res["result"]


def leer_telegram(cfg, uniones):
    """Canales donde el bot es administrador y quien ha entrado con cada enlace personal."""
    try:
        ups = tg("getUpdates", offset=int(cfg.get("tg_offset", 0)) + 1, timeout=0,
                 allowed_updates=["my_chat_member", "chat_member"])
    except Exception as ex:
        print("Premium: Telegram no responde (%s)" % ex)
        return
    for u in ups:
        cfg["tg_offset"] = u["update_id"]
        m = u.get("my_chat_member")
        if m and m.get("chat", {}).get("type") == "channel":
            ch = m["chat"]
            if m.get("new_chat_member", {}).get("status") == "administrator":
                titulo = (ch.get("title") or "").lower()
                lang = "en" if (" en" in titulo + " " or "english" in titulo or "ingl" in titulo) and "es" not in titulo.split() else "es"
                cfg["canal_" + lang] = ch["id"]
                cfg["canal_" + lang + "_titulo"] = ch.get("title")
                print("Premium: canal %s encontrado (%s)" % (lang.upper(), ch.get("title")))
        c = u.get("chat_member")
        if c:
            link = (c.get("invite_link") or {}).get("name") or ""
            nuevo = c.get("new_chat_member", {})
            if link.startswith("u:") and nuevo.get("status") in ("member", "restricted"):
                uniones[link[2:]] = nuevo.get("user", {}).get("id")


def poner_logo(cfg):
    """Pone el logo de SportEVLab como foto de los canales privados (solo la primera vez)."""
    import uuid
    ruta = os.path.join(os.path.dirname(DATA), "img", "favicon-512.png")
    if not os.path.exists(ruta):
        return
    for lang in ("es", "en"):
        canal = cfg.get("canal_" + lang)
        if not canal or cfg.get("logo_" + lang):
            continue
        try:
            borde = uuid.uuid4().hex
            cuerpo = ("--%s\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n%s\r\n" % (borde, canal)).encode()
            cuerpo += ("--%s\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"logo.png\"\r\n"
                       "Content-Type: image/png\r\n\r\n" % borde).encode() + open(ruta, "rb").read() + ("\r\n--%s--\r\n" % borde).encode()
            req = urllib.request.Request("https://api.telegram.org/bot%s/setChatPhoto" % TGP, data=cuerpo,
                                         headers={"Content-Type": "multipart/form-data; boundary=" + borde})
            with urllib.request.urlopen(req, timeout=30) as r:
                if json.loads(r.read().decode()).get("ok"):
                    cfg["logo_" + lang] = True
                    print("Premium: logo puesto en el canal %s" % lang.upper())
        except Exception as ex:
            print("Premium: no se pudo poner el logo (%s)" % ex)


def sacar(canal, tg_id):
    try:
        tg("banChatMember", chat_id=canal, user_id=tg_id)
        tg("unbanChatMember", chat_id=canal, user_id=tg_id, only_if_banned=True)
    except Exception as ex:
        print("Premium: no se pudo sacar a un usuario del canal (%s)" % ex)


# ------------------------------------------------------------------ Stripe (solo lectura)
def stripe(ruta, **params):
    url = "https://api.stripe.com/v1/%s?%s" % (ruta, urllib.parse.urlencode(params))
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + STRIPE})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def todos(ruta, **params):
    out, desde = [], None
    for _ in range(50):
        p = dict(params, limit=100)
        if desde:
            p["starting_after"] = desde
        r = stripe(ruta, **p)
        out += r.get("data", [])
        if not r.get("has_more") or not r.get("data"):
            break
        desde = r["data"][-1]["id"]
    return out


def fin_periodo(s):
    f = s.get("current_period_end")
    if not f:
        items = (s.get("items") or {}).get("data") or []
        f = max([i.get("current_period_end") or 0 for i in items] or [0]) or None
    return f


def suscripciones(cfg):
    """{uid: {"estado", "hasta", "sub", "renueva"}} de quien pago con nuestro enlace de pago."""
    plink = cfg.get("plink")
    if not plink:
        return {}
    ses = todos("checkout/sessions", payment_link=plink, status="complete")
    subs = {s["id"]: s for s in todos("subscriptions", status="all")}
    out = {}
    for s in sorted(ses, key=lambda x: x.get("created", 0)):
        uid, sid = s.get("client_reference_id"), s.get("subscription")
        if not uid or not sid or sid not in subs:
            continue
        sub = subs[sid]
        previo = out.get(uid)
        if previo and previo["estado"] in ACTIVOS and sub["status"] not in ACTIVOS:
            continue   # si tiene una activa y otra antigua cancelada, manda la activa
        out[uid] = {"estado": sub["status"], "hasta": fin_periodo(sub), "sub": sid,
                    "renueva": not sub.get("cancel_at_period_end")}
    return out


# ------------------------------------------------------------------ todo junto
def main():
    cfg = leer()
    if not cfg:
        print("Premium: falta data/premium.json")
        return
    antes = json.dumps(cfg, sort_keys=True)
    uniones = {}
    if TGP:
        leer_telegram(cfg, uniones)
        poner_logo(cfg)
    if not os.environ.get("FIREBASE_CUENTA"):
        print("Premium: falta FIREBASE_CUENTA; solo se han revisado los canales.")
    else:
        import firebase_admin
        from firebase_admin import credentials, firestore, auth
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(json.loads(os.environ["FIREBASE_CUENTA"])))
        db = firestore.client()
        ref = db.collection("usuarios")
        for uid, tid in uniones.items():
            ref.document(uid).set({"tg_id_premium": tid}, merge=True)

        pagos = {}
        if STRIPE:
            try:
                pagos = suscripciones(cfg)
            except Exception as ex:
                print("Premium: Stripe no responde (%s). No se cambia nada este turno." % ex)
                pagos = None
        if pagos is not None:
            try:
                admin = auth.get_user_by_email(ADMIN).uid
            except Exception:
                admin = None
            premium = {uid for uid, p in pagos.items() if p["estado"] in ACTIVOS}
            if admin:
                premium.add(admin)   # el dueno siempre tiene todo
            ahora = datetime.now(timezone.utc)
            vistos = set()
            # quien ya era Premium
            for d in ref.where("premium", "==", True).stream():
                vistos.add(d.id)
                u = d.to_dict() or {}
                if d.id in premium:
                    continue
                # ha dejado de pagar: fuera Premium, fuera enlace y fuera del canal
                canal = u.get("tg_canal_premium")
                if TGP and canal and u.get("tg_link_premium"):
                    try:
                        tg("revokeChatInviteLink", chat_id=canal, invite_link=u["tg_link_premium"])
                    except Exception:
                        pass
                if TGP and canal and u.get("tg_id_premium"):
                    sacar(canal, u["tg_id_premium"])
                d.reference.set({"premium": False, "premium_estado": (pagos.get(d.id) or {}).get("estado", "cancelada"),
                                 "tg_link_premium": firestore.DELETE_FIELD, "tg_canal_premium": firestore.DELETE_FIELD,
                                 "premium_cambio": ahora}, merge=True)
                print("Premium: baja de un usuario")
            # quien es Premium ahora
            for uid in premium:
                d = ref.document(uid).get()
                u = d.to_dict() or {}
                p = pagos.get(uid) or {}
                datos = {"premium": True, "premium_estado": p.get("estado", "admin"),
                         "premium_renueva": p.get("renueva", True)}
                if p.get("hasta"):
                    datos["premium_hasta"] = datetime.fromtimestamp(p["hasta"], timezone.utc)
                if uid not in vistos:
                    datos["premium_cambio"] = ahora
                    print("Premium: alta de un usuario")
                lang = u.get("telegram") if u.get("telegram") in ("es", "en") else ("en" if u.get("idioma") == "en" else "es")
                canal = cfg.get("canal_" + lang)
                if TGP and canal and (not u.get("tg_link_premium") or u.get("tg_canal_premium") != canal):
                    try:
                        link = tg("createChatInviteLink", chat_id=canal, name="u:" + uid[:28], member_limit=1)
                        datos["tg_link_premium"] = link["invite_link"]
                        datos["tg_canal_premium"] = canal
                    except Exception as ex:
                        print("Premium: no se pudo crear el enlace de Telegram (%s)" % ex)
                ref.document(uid).set(datos, merge=True)
            cfg["socios"] = len(premium) - (1 if admin else 0)
    cfg["revisado"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if json.dumps({k: v for k, v in cfg.items() if k != "revisado"}, sort_keys=True) != \
            json.dumps({k: v for k, v in json.loads(antes).items() if k != "revisado"}, sort_keys=True):
        guardar(cfg)
        print("Premium: configuracion actualizada")


if __name__ == "__main__":
    t0 = time.time()
    try:
        main()
    except Exception as ex:
        print("Aviso Premium: %s: %s" % (ex.__class__.__name__, str(ex)[:300]))
    print("Premium revisado en %.1f s" % (time.time() - t0))
