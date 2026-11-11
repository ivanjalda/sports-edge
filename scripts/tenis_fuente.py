# -*- coding: utf-8 -*-
"""Sports Edge - Fuente de datos de tenis (solo libreria estandar).

Fuente principal: TennisMyLife (stats.tennismylife.org), ATP y WTA, actualizada a diario.
  Uso permitido: personal, educativo y de investigacion NO comercial. No se guardan ni se
  redistribuyen los CSV: solo se leen durante la ejecucion.
Respaldo: espejo de Jeff Sackmann en GitHub (datos hasta mayo-junio 2026, desactualizado).

Regla importante: cada circuito (ATP o WTA) usa UNA sola fuente para todos los anios, porque
cada fuente identifica a los jugadores con codigos distintos y mezclarlas romperia el Elo."""
import csv
import io
import json
import os
import re
import urllib.error
import urllib.request

TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
UA = "Mozilla/5.0 (compatible; sports-edge/1.0; +https://ivanjalda.github.io/sports-edge/)"

TML = {"atp": "https://stats.tennismylife.org/data/%d.csv",
       "wta": "https://stats.tennismylife.org/data/%d_wta.csv"}
ESPEJO_REPO = "Aneeshers/tennis-sackmann-archive"

FUENTES_INFO = {
    "tml": {"nombre": "TennisMyLife", "url": "https://stats.tennismylife.org",
            "licencia": "uso no comercial / non-commercial use"},
    "espejo": {"nombre": "Jeff Sackmann / Tennis Abstract (copia de archivo)",
               "url": "https://github.com/" + ESPEJO_REPO, "licencia": "CC BY-NC-SA 4.0"},
}


def _get(url, api=False):
    h = {"User-Agent": UA}
    if api:
        h["Accept"] = "application/vnd.github+json"
        if TOKEN:
            h["Authorization"] = "Bearer " + TOKEN
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def _csv_valido(txt):
    """Comprueba que lo descargado es un CSV de partidos y no una pagina de error."""
    if not txt:
        return False
    cab = txt.lstrip("﻿").split("\n", 1)[0]
    return "tourney_date" in cab and "winner_name" in cab and "loser_name" in cab


def _ultima_fecha(txt):
    vals = []
    for f in csv.DictReader(io.StringIO(txt)):
        x = (f.get("tourney_date") or "").strip()
        if x.isdigit() and len(x) == 8:
            vals.append(int(x))
    return max(vals) if vals else None


def _desde_tml(tour, anios):
    textos = {}
    for a in anios:
        url = TML[tour] % a
        try:
            txt = _get(url).decode("utf-8-sig", "replace")
            if _csv_valido(txt):
                textos[a] = txt
            else:
                print("Aviso: TennisMyLife %s %d no devolvio un CSV valido" % (tour.upper(), a))
        except urllib.error.HTTPError as e:
            print("Aviso: TennisMyLife %s %d -> HTTP %s" % (tour.upper(), a, e.code))
        except Exception as e:
            print("Aviso: TennisMyLife %s %d -> %s" % (tour.upper(), a, e))
    return textos


def _desde_espejo(tour, anios):
    textos = {}
    try:
        d = json.loads(_get("https://api.github.com/repos/%s/contents/%s" % (ESPEJO_REPO, tour),
                            api=True).decode("utf-8", "replace"))
    except Exception as e:
        print("Aviso: espejo %s no accesible (%s)" % (tour.upper(), e))
        return textos
    enlaces = {}
    for f in d if isinstance(d, list) else []:
        m = re.match(r"^%s_matches_(\d{4})\.csv$" % tour, str(f.get("name", "")))
        if m and f.get("download_url"):
            enlaces[int(m.group(1))] = f["download_url"]
    for a in anios:
        if a not in enlaces:
            continue
        try:
            txt = _get(enlaces[a]).decode("utf-8-sig", "replace")
            if _csv_valido(txt):
                textos[a] = txt
        except Exception as e:
            print("Aviso: espejo %s %d -> %s" % (tour.upper(), a, e))
    return textos


def _suficiente(textos, anios):
    """La fuente vale si tiene el anio actual o el anterior, y al menos el 80 % de los anios."""
    if not textos:
        return False
    recientes = anios[-1] in textos or anios[-2] in textos
    return recientes and len(textos) >= 0.8 * len(anios)


def cargar(tour, anios):
    """Devuelve (lista de textos CSV, clave de la fuente usada) para un circuito."""
    textos = _desde_tml(tour, anios)
    if _suficiente(textos, anios):
        clave = "tml"
    else:
        print("Aviso: TennisMyLife no sirve para %s (%d de %d anios). Se prueba el espejo." %
              (tour.upper(), len(textos), len(anios)))
        textos = _desde_espejo(tour, anios)
        clave = "espejo" if textos else None
    if not clave:
        print("ERROR: %s sin datos en ninguna fuente" % tour.upper())
        return [], None
    ultimas = [u for u in (_ultima_fecha(t) for t in textos.values()) if u]
    print("Fuente usada para %s: %s | anios: %d | ultimo torneo con datos: %s" %
          (tour.upper(), FUENTES_INFO[clave]["nombre"], len(textos), max(ultimas) if ultimas else "?"))
    return [textos[a] for a in sorted(textos)], clave
