# -*- coding: utf-8 -*-
"""Sports Edge - Noticias de deportes (solo libreria estandar).

Lee los titulares publicos (RSS) de medios deportivos y guarda solo: titular, enlace, medio y fecha.
No se copia el texto de las noticias: el usuario pulsa y lee la noticia en la web del medio.
Si un medio falla, se usan los demas. Si fallan todos, se conservan las noticias anteriores."""
import json
import os
import re
import sys
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

DATA = "data"
UA = "Mozilla/5.0 (compatible; sports-edge/1.0; +https://ivanjalda.github.io/sports-edge/)"
HORAS = 48
MAX_POR_IDIOMA = 60
MAX_POR_MEDIO = 15

FUENTES = {
    "es": [
        ("AS", ["https://as.com/rss/tags/ultimas_noticias.xml",
                "https://feeds.as.com/mrss-s/pages/as/site/as.com/portada"]),
        ("Marca", ["https://e00-marca.uecdn.es/rss/portada.xml"]),
        ("Mundo Deportivo", ["https://www.mundodeportivo.com/rss/home.xml"]),
    ],
    "en": [
        ("BBC Sport", ["https://feeds.bbci.co.uk/sport/rss.xml"]),
        ("Sky Sports", ["https://www.skysports.com/rss/12040"]),
    ],
}

# Palabras para clasificar cada titular por deporte (si no encaja, queda como "general")
CLAVES = {
    "tenis": ["tenis", "tennis", "atp", "wta", "alcaraz", "sinner", "djokovic", "nadal", "sabalenka", "swiatek",
              "gauff", "wimbledon", "roland garros", "us open", "open de australia", "australian open",
              "copa davis", "davis cup", "masters 1000", "zverev", "medvedev", "rybakina", "badosa"],
    "baloncesto": ["baloncesto", "basket", "nba", "acb", "euroliga", "euroleague", "eurocup", "wnba", "ncaa basketball",
                   "lakers", "celtics", "warriors", "knicks", "lebron", "curry", "doncic", "jokic", "wembanyama",
                   "giannis", "liga endesa", "pelicans", "mavericks", "nuggets", "76ers", "rockets", "bucks"],
    "hockey": ["hockey", "nhl", "stanley cup", "maple leafs", "canadiens", "oilers", "bruins", "rangers hockey",
               "mcdavid", "ovechkin", "crosby"],
    "futbol": ["futbol", "fútbol", "football", "soccer", "laliga", "la liga", "premier league", "champions",
               "real madrid", "barcelona", "barça", "atletico", "atlético", "sevilla", "betis", "valencia",
               "athletic", "villarreal", "liverpool", "arsenal", "chelsea", "manchester", "tottenham",
               "bayern", "juventus", "inter ", "milan", "napoli", "psg", "gol", "goal", "seleccion",
               "selección", "mundial", "world cup", "serie a", "bundesliga", "ligue 1", "eredivisie",
               "championship", "mbapp", "vinicius", "lamine", "haaland", "entrenador", "fichaje"],
}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii").lower()
    return " " + re.sub(r"\s+", " ", s) + " "


def clasificar(titulo):
    t = " " + re.sub(r"[^a-z0-9 ]", " ", norm(titulo)) + " "
    for dep in ("tenis", "baloncesto", "hockey", "futbol"):
        for c in CLAVES[dep]:
            k = re.sub(r"[^a-z0-9 ]", " ", norm(c)).strip()
            if k and (" " + k) in t:
                return dep
    return "general"


def limpiar(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
    return re.sub(r"\s+", " ", s).strip()


def fecha_item(txt):
    if not txt:
        return None
    txt = txt.strip()
    try:
        d = parsedate_to_datetime(txt)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(txt.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def leer_feed(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, text/xml"})
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read()
    root = ET.fromstring(raw)
    items = []
    for it in root.iter():
        tag = it.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        tit = enl = fec = img = None
        for ch in it.iter():
            n = ch.tag.split("}")[-1]
            if ch is it:
                continue
            if n == "title" and tit is None:
                tit = limpiar(ch.text)
            elif n == "link" and enl is None:
                enl = (ch.text or "").strip() or ch.attrib.get("href", "")
            elif n in ("pubDate", "published", "updated", "date"):
                fec = fec or ch.text
            elif n in ("content", "thumbnail") and ch.attrib.get("url") and not img:
                tipo = ch.attrib.get("type", "") + ch.attrib.get("medium", "")
                if n == "thumbnail" or "image" in tipo or re.search(r"\.(jpe?g|png|webp)", ch.attrib["url"], re.I):
                    img = ch.attrib["url"]
            elif n == "enclosure" and "image" in ch.attrib.get("type", "") and not img:
                img = ch.attrib.get("url")
            elif n in ("description", "encoded") and not img and ch.text:
                m = re.search(r'<img[^>]+src=["\']([^"\']+)', ch.text)
                if m:
                    img = m.group(1)
        if img and not img.startswith("https://"):
            img = None   # solo imagenes seguras (https)
        if tit and enl and enl.startswith(("http://", "https://")):
            items.append((tit, enl, fecha_item(fec), img))
    return items


def main():
    os.makedirs(DATA, exist_ok=True)
    ahora = datetime.now(timezone.utc)
    previo = {}
    try:
        with open(os.path.join(DATA, "noticias.json"), encoding="utf-8") as f:
            previo = json.load(f)
    except Exception:
        pass
    salida = {"actualizado": ahora.strftime("%Y-%m-%d %H:%M UTC"), "fuentes": {}}
    total = 0
    for idioma, medios in FUENTES.items():
        lista, vistos = [], set()
        usados = []
        for medio, urls in medios:
            items = None
            for u in urls:
                try:
                    items = leer_feed(u)
                    if items:
                        break
                except Exception as e:
                    print("Aviso: %s (%s) no disponible: %s" % (medio, u, e))
            if not items:
                continue
            n = 0
            for tit, enl, fec, img in items:
                if fec is None or fec < ahora - timedelta(hours=HORAS) or fec > ahora + timedelta(hours=2):
                    continue
                clave = norm(tit)[:80]
                if clave in vistos or enl in vistos:
                    continue
                vistos.add(clave)
                vistos.add(enl)
                lista.append({"t": tit, "url": enl, "fuente": medio, "fecha": fec.strftime("%Y-%m-%dT%H:%M:%SZ"),
                              "dep": clasificar(tit), "img": img})
                n += 1
                if n >= MAX_POR_MEDIO:
                    break
            if n:
                usados.append(medio)
            print("Noticias %s - %s: %d titulares" % (idioma.upper(), medio, n))
        lista.sort(key=lambda x: x["fecha"], reverse=True)
        if not lista and previo.get(idioma):
            print("Aviso: sin noticias nuevas en %s. Se conservan las anteriores." % idioma.upper())
            lista = previo[idioma]
            usados = previo.get("fuentes", {}).get(idioma, [])
        salida[idioma] = lista[:MAX_POR_IDIOMA]
        salida["fuentes"][idioma] = usados
        total += len(lista)
    if total == 0 and not previo:
        print("ERROR: no se pudo leer ningun medio.")
        sys.exit(1)
    with open(os.path.join(DATA, "noticias.json"), "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=1)
    print("Noticias guardadas: %d en espanol, %d en ingles" % (len(salida.get("es", [])), len(salida.get("en", []))))


if __name__ == "__main__":
    main()
