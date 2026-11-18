# -*- coding: utf-8 -*-
"""SportEVLab - REVISOR AUTOMATICO DIARIO (solo libreria estandar).

Revisa toda la web cada dia, sin depender de nadie, y deja el informe en data/revision.json.
Si encuentra un ERROR, la tarea de GitHub termina en rojo y GitHub avisa por correo al dueno del repositorio.

Que revisa:
  1. Que todos los archivos de datos existen, se leen bien y estan al dia (el motor ha funcionado).
  2. Que las probabilidades tienen sentido (entre 0 y 1 y que sumen lo que deben sumar).
  3. Que no se muestran como "proximos" partidos que ya se jugaron hace tiempo.
  4. Que el historial publico NO se ha tocado: ninguna prediccion resuelta desaparece ni cambia
     (se guarda una huella de cada una y se compara con la del dia anterior).
  5. Que los partidos ya jugados reciben su resultado (si no, el registro publico estaria incompleto).
  6. Que el vigilante de Telegram sigue enviando (pronosticos de la manana y balance de la noche).
  7. Que cada pagina y cada archivo que usa la web existen, y que la web publicada responde.
  8. Que cada motor sigue acertando al menos como la regla mas sencilla en su prueba.
Los problemas leves quedan como AVISO; los graves como ERROR."""
import glob
import hashlib
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

DATA = "data"
WEB = "https://sportevlab.com/"
SALIDA = os.path.join(DATA, "revision.json")
HUELLAS = os.path.join(DATA, "revision_huellas.json")

errores, avisos, bien = [], [], []


def error(txt):
    errores.append(txt)
    print("ERROR: " + txt)


def aviso(txt):
    avisos.append(txt)
    print("AVISO: " + txt)


def ok(txt):
    bien.append(txt)


def leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def fecha(s):
    if s is None:
        return None
    s = str(s).strip().replace(" UTC", "").replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:len(datetime(2000, 1, 1).strftime(fmt))], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


AHORA = datetime.now(timezone.utc)


# ------------------------------------------------------------------ 1. archivos y frescura
# archivos que no se renuevan en cada ejecucion por diseno (se revisan por otro lado)
SIN_FRESCURA = {"telegram_directo.json", "cuotas.json", "laboratorio.json", "valor.json"}
PRINCIPALES = ["predicciones.json", "historial.json", "estadisticas.json", "motor_futbol.json", "tenis.json",
               "tenis_historial.json", "noticias.json", "carreras_f1.json", "carreras_motogp.json", "telegram_directo.json"]


def revisar_archivos():
    datos = {}
    for ruta in sorted(glob.glob(os.path.join(DATA, "*.json"))):
        nombre = os.path.basename(ruta)
        if nombre.startswith("revision"):
            continue
        try:
            datos[nombre] = leer(ruta)
        except Exception as ex:
            error("El archivo %s esta roto y la web no puede leerlo (%s)." % (nombre, ex))
    for n in PRINCIPALES:
        if n not in datos:
            error("Falta el archivo %s." % n)
    for n, d in datos.items():
        if not isinstance(d, dict) or "actualizado" not in d or n.endswith("_resultados.json") or n in SIN_FRESCURA:
            continue
        f = fecha(d["actualizado"])
        if f is None:
            continue
        horas = (AHORA - f).total_seconds() / 3600.0
        if horas > 72:
            error("%s lleva %d horas sin actualizarse: el motor no esta funcionando." % (n, horas))
        elif horas > 30:
            aviso("%s lleva %d horas sin actualizarse." % (n, horas))
    ok("%d archivos de datos leidos sin problemas" % len(datos))
    return datos


# ------------------------------------------------------------------ 2 y 3. probabilidades y fechas de los proximos
def comprobar_prob(nombre, ident, valores, suma=1.0, tol=0.02, maximo=None):
    for v in valores:
        if v is None or not (0.0 <= float(v) <= 1.0):
            error("%s: la prediccion %s tiene una probabilidad imposible (%s)." % (nombre, ident, v))
            return False
    s = sum(float(v) for v in valores)
    if maximo is not None:
        if s > maximo + tol:
            error("%s: las probabilidades de %s suman %.3f (como mucho %s)." % (nombre, ident, s, maximo))
            return False
    elif abs(s - suma) > tol:
        error("%s: las probabilidades de %s suman %.3f en vez de %s." % (nombre, ident, s, suma))
        return False
    return True


def proximo_pasado(nombre, ident, f, horas_margen):
    if f is None:
        error("%s: la prediccion %s no tiene una fecha valida." % (nombre, ident))
        return
    h = (AHORA - f).total_seconds() / 3600.0
    if h > horas_margen:
        aviso("%s: %s se muestra como proximo pero empezo hace %d horas." % (nombre, ident, h))


def revisar_predicciones(datos):
    n = 0
    for p in (datos.get("predicciones.json") or {}).get("predicciones", []):
        comprobar_prob("Futbol", "%s-%s" % (p.get("local"), p.get("visitante")), [p.get("p_local"), p.get("p_empate"), p.get("p_visitante")])
        n += 1
    for p in (datos.get("tenis.json") or {}).get("predicciones", []):
        comprobar_prob("Tenis", "%s-%s" % (p.get("j1"), p.get("j2")), [p.get("p1"), p.get("p2")])
        proximo_pasado("Tenis", "%s-%s" % (p.get("j1"), p.get("j2")), fecha(p.get("fecha")), 30)
        n += 1
    for nom, d in datos.items():
        if not re.match(r"equipos_[a-z0-9_]+\.json$", nom) or nom.endswith(("_backtest.json", "_historial.json", "_resultados.json")):
            continue
        for p in d.get("predicciones", []):
            ident = "%s-%s" % (p.get("local"), p.get("visitante"))
            comprobar_prob(d.get("liga", nom), ident, [p.get("pl"), p.get("pv")])
            proximo_pasado(d.get("liga", nom), ident, fecha(p.get("fecha")), 30)
            n += 1
    for s in ("f1", "motogp", "nascar"):
        d = datos.get("carreras_%s.json" % s) or {}
        pr = d.get("proximo")
        if pr:
            pil = pr.get("pilotos", [])
            comprobar_prob(d.get("nombre", s), pr.get("nombre"), [x.get("pw") for x in pil], maximo=1.0)
            comprobar_prob(d.get("nombre", s), pr.get("nombre") + " (podio)", [x.get("pp") for x in pil], maximo=3.0, tol=0.05)
            proximo_pasado(d.get("nombre", s), pr.get("nombre"), fecha(pr.get("fecha")), 6)
            n += len(pil)
    ok("%d probabilidades publicadas revisadas" % n)


# ------------------------------------------------------------------ 4 y 5. historial publico intacto y resultados anotados
def huella(p):
    clave = {k: p.get(k) for k in ("fecha", "p_local", "p_empate", "p_visitante", "pl", "pv", "p1", "p2", "resultado", "tipo")}
    if "fav" in p:
        clave["fav"] = p["fav"]
    return hashlib.sha1(json.dumps(clave, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:10]


def revisar_historial(datos):
    try:
        antes = leer(HUELLAS)
    except Exception:
        antes = {}
    nuevas = {}
    archivos = [n for n in datos if n.endswith("_historial.json") or n == "historial.json"]
    total = sin_resultado = 0
    for nom in sorted(archivos):
        lista = datos[nom].get("predicciones", [])
        ids = {}
        for p in lista:
            k = "%s|%s" % (p.get("id"), p.get("tipo", ""))
            if k in ids:
                error("%s: la prediccion %s aparece repetida en el historial." % (nom, p.get("id")))
            ids[k] = p
        h = {k: huella(p) for k, p in ids.items() if p.get("resultado")}
        nuevas[nom] = h
        viejo = antes.get(nom, {})
        perdidas = [k for k in viejo if k not in h]
        cambiadas = [k for k in viejo if k in h and h[k] != viejo[k]]
        if perdidas:
            error("%s: han desaparecido %d predicciones ya resueltas del historial publico (ej. %s)." % (nom, len(perdidas), perdidas[0]))
        if cambiadas:
            error("%s: se han modificado %d predicciones ya resueltas (ej. %s). El historial no se puede tocar." % (nom, len(cambiadas), cambiadas[0]))
        for k, p in ids.items():
            if p.get("resultado"):
                continue
            f = fecha(p.get("fecha"))
            if f is None:
                continue
            dias = (AHORA - f).total_seconds() / 86400.0
            nombre = "%s - %s" % (p.get("local") or p.get("j1") or p.get("nombre", ""), p.get("visitante") or p.get("j2") or "")
            if dias > 7:
                error("%s: %s se jugo hace %d dias y sigue sin resultado anotado." % (nom, nombre, dias))
                sin_resultado += 1
            elif dias > 3:
                aviso("%s: %s se jugo hace %d dias y aun no tiene resultado." % (nom, nombre, dias))
                sin_resultado += 1
        total += len(h)
    ok("%d predicciones resueltas del historial publico comprobadas (ninguna borrada ni cambiada)" % total
       if not any("historial" in e for e in errores) else "historial revisado")
    return nuevas


# ------------------------------------------------------------------ 6. vigilante de Telegram
def revisar_telegram(datos):
    t = datos.get("telegram_directo.json") or {}
    try:
        from zoneinfo import ZoneInfo
        loc = AHORA.astimezone(ZoneInfo("Europe/Madrid"))
    except Exception:
        loc = AHORA
    hoy = loc.strftime("%Y-%m-%d")
    ayer = (loc - timedelta(days=1)).strftime("%Y-%m-%d")
    if (loc.hour, loc.minute) >= (10, 30) and t.get("manana") != hoy:
        error("Telegram: hoy no se han enviado los pronosticos de la manana (ultimo: %s)." % t.get("manana"))
    if t.get("balance") not in (hoy, ayer):
        aviso("Telegram: el ultimo balance del dia enviado es del %s." % t.get("balance"))
    dias = set(v.get("dia") for v in (t.get("enviados") or {}).values())
    if not (dias & {hoy, ayer}):
        aviso("Telegram: no se ha avisado de ningun resultado ni hoy ni ayer.")
    ok("vigilante de Telegram revisado")


# ------------------------------------------------------------------ 7. paginas, enlaces y web publicada
def revisar_web():
    paginas = sorted(glob.glob("*.html"))
    nav = open("nav.js", encoding="utf-8").read() if os.path.exists("nav.js") else ""
    if not nav:
        error("Falta nav.js: ninguna pagina tendria menu.")
    for destino in set(re.findall(r'"([a-z_]+\.html)', nav)):
        if not os.path.exists(destino):
            error("El menu enlaza a %s, que no existe." % destino)
    usados = set()
    for pg in paginas:
        txt = open(pg, encoding="utf-8").read()
        for f in re.findall(r'data/([a-z0-9_]+\.json)', txt):
            usados.add(f)
            if not os.path.exists(os.path.join(DATA, f)):
                error("La pagina %s usa data/%s, que no existe." % (pg, f))
        if "nav.js" not in txt:
            aviso("La pagina %s no carga el menu (nav.js)." % pg)
        if "+18" not in txt and "18+" not in txt and "18 a" not in txt and pg != "guia.html":
            aviso("La pagina %s no muestra el aviso de mayores de 18 anos." % pg)
    caidas = []
    for pg in ["", "directo.html", "futbol.html", "equipos.html", "carreras.html", "data/predicciones.json"]:
        try:
            req = urllib.request.Request(WEB + pg, headers={"User-Agent": "sports-edge-revisor"})
            with urllib.request.urlopen(req, timeout=25) as r:
                if r.status != 200:
                    caidas.append("%s (%s)" % (pg or "inicio", r.status))
        except Exception as ex:
            caidas.append("%s (%s)" % (pg or "inicio", ex))
    if caidas:
        error("La web publicada no responde bien: %s." % ", ".join(caidas))
    else:
        ok("web publicada respondiendo")
    ok("%d paginas, el menu y los archivos que usan revisados" % len(paginas))


# ------------------------------------------------------------------ 8. motores
def revisar_motores(datos):
    for nom, d in datos.items():
        if not nom.endswith("_backtest.json") or not nom.startswith("equipos_"):
            continue
        tot = d.get("total") or {}
        base = d.get("base_local") or {}
        a, b = tot.get("acierto"), base.get("acierto") if isinstance(base, dict) else None
        if a is not None and b is not None and tot.get("n", 0) >= 100 and a + 0.005 < b:
            aviso("%s: en la prueba el motor acierta %.1f%%, menos que 'siempre gana el local' (%.1f%%)." %
                  (d.get("liga", nom), 100 * a, 100 * b))
    ok("pruebas de los motores revisadas")


def main():
    print("Revision automatica de SportEVLab · %s" % AHORA.strftime("%Y-%m-%d %H:%M UTC"))
    datos = revisar_archivos()
    revisar_predicciones(datos)
    nuevas = revisar_historial(datos)
    revisar_telegram(datos)
    revisar_web()
    revisar_motores(datos)
    estado = "error" if errores else ("aviso" if avisos else "ok")
    informe = {"fecha": AHORA.strftime("%Y-%m-%d %H:%M UTC"), "estado": estado,
               "errores": errores, "avisos": avisos, "bien": bien}
    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump(informe, f, ensure_ascii=False, indent=1)
    # las huellas solo se renuevan si el historial esta sano (si no, se conserva la referencia buena)
    if not any("historial" in e for e in errores):
        with open(HUELLAS, "w", encoding="utf-8") as f:
            json.dump(nuevas, f, separators=(",", ":"))
    print("\nRESUMEN: %d errores, %d avisos, %d comprobaciones correctas." % (len(errores), len(avisos), len(bien)))
    for b in bien:
        print("  OK  " + b)
    if errores:
        sys.exit(1)


if __name__ == "__main__":
    main()
