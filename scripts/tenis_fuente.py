# -*- coding: utf-8 -*-
"""Sports Edge - Fuente de datos de tenis con respaldo y diagnostico (solo libreria estandar).
Primero prueba la ruta directa de Sackmann. Si falla, pregunta a GitHub que archivos existen.
Si el repositorio original no esta disponible, usa un archivo espejo (puede estar desactualizado)."""
import json
import os
import re
import urllib.error
import urllib.request

TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
RAW = "https://raw.githubusercontent.com/JeffSackmann/tennis_%s/master/%s_matches_%d.csv"
ORIGENES = [
    {"nombre": "Sackmann", "repo": "JeffSackmann/tennis_%s", "carpeta": "", "directo": True},
    {"nombre": "Espejo (puede estar desactualizado)", "repo": "Aneeshers/tennis-sackmann-archive",
     "carpeta": "%s", "directo": False},
]
_listas = {}
_info = set()
_usadas = set()


def _get(url, api=False):
    h = {"User-Agent": "sports-edge"}
    if api:
        h["Accept"] = "application/vnd.github+json"
        if TOKEN:
            h["Authorization"] = "Bearer " + TOKEN
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def _info_repo(repo):
    if repo in _info:
        return
    _info.add(repo)
    try:
        d = json.loads(_get("https://api.github.com/repos/" + repo, api=True).decode("utf-8", "replace"))
        print("Repositorio %s: rama=%s, ultimo cambio=%s, archivado=%s" %
              (repo, d.get("default_branch"), d.get("pushed_at"), d.get("archived")))
    except urllib.error.HTTPError as e:
        print("Repositorio %s: no accesible (HTTP %s)" % (repo, e.code))
    except Exception as e:
        print("Repositorio %s: no se pudo consultar (%s)" % (repo, e))


def _listar(o, tour):
    clave = (o["nombre"], tour)
    if clave in _listas:
        return _listas[clave]
    repo = o["repo"] % tour if "%s" in o["repo"] else o["repo"]
    carpeta = o["carpeta"] % tour if "%s" in o["carpeta"] else o["carpeta"]
    _info_repo(repo)
    res = {}
    try:
        datos = json.loads(_get("https://api.github.com/repos/%s/contents/%s" % (repo, carpeta),
                                api=True).decode("utf-8", "replace"))
        for f in datos if isinstance(datos, list) else []:
            m = re.match(r"^%s_matches_(\d{4})\.csv$" % tour, str(f.get("name", "")))
            if m and f.get("download_url"):
                res[int(m.group(1))] = f["download_url"]
        print("Fuente %s (%s): %d archivos anuales encontrados" % (o["nombre"], tour.upper(), len(res)))
    except urllib.error.HTTPError as e:
        print("Aviso: fuente %s (%s) no accesible (HTTP %s)" % (o["nombre"], tour.upper(), e.code))
    except Exception as e:
        print("Aviso: fuente %s (%s) no se pudo consultar (%s)" % (o["nombre"], tour.upper(), e))
    _listas[clave] = res
    return res


def descargar(tour, anio):
    for o in ORIGENES:
        urls = []
        if o["directo"]:
            urls.append(RAW % (tour, tour, anio))
        for u in urls:
            try:
                txt = _get(u).decode("utf-8", "replace")
                if (o["nombre"], tour) not in _usadas:
                    _usadas.add((o["nombre"], tour))
                    print("Fuente usada para %s: %s (ruta directa)" % (tour.upper(), o["nombre"]))
                return txt
            except Exception:
                pass
        u = _listar(o, tour).get(anio)
        if u:
            try:
                txt = _get(u).decode("utf-8", "replace")
                if (o["nombre"], tour) not in _usadas:
                    _usadas.add((o["nombre"], tour))
                    print("Fuente usada para %s: %s" % (tour.upper(), o["nombre"]))
                return txt
            except Exception as e:
                print("Aviso: %s %d desde %s fallo (%s)" % (tour.upper(), anio, o["nombre"], e))
    print("Aviso: %s %d no disponible en ninguna fuente" % (tour.upper(), anio))
    return None
