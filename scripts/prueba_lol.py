# -*- coding: utf-8 -*-
"""SportEVLab - Prueba de la fuente de datos de League of Legends (solo libreria estandar).

Antes de construir el motor de LoL comprobamos, desde GitHub, que Leaguepedia (lol.fandom.com, la
enciclopedia abierta de LoL con su API publica "cargo") responde y trae partidos reales con resultado.
No hace predicciones: solo guarda data/lol_prueba.json con lo que ha encontrado.
"""
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

UA = "SportEVLab/1.0 (https://sportevlab.com; contacto@sportevlab.com)"
API = "https://lol.fandom.com/api.php"


def cargo(where, limite=50):
    q = {"action": "cargoquery", "format": "json", "tables": "MatchSchedule",
         "fields": "Team1,Team2,Winner,Team1Score,Team2Score,BestOf,DateTime_UTC,OverviewPage",
         "where": where, "order_by": "DateTime_UTC DESC", "limit": str(limite)}
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(q), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    out = {"comprobado": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "pruebas": []}
    for nombre, where in (("LCK 2025", "OverviewPage LIKE 'LCK/2025%'"),
                          ("LEC 2025", "OverviewPage LIKE 'LEC/2025%'"),
                          ("Worlds 2025", "OverviewPage LIKE '2025 Season World Championship%'")):
        r = {"liga": nombre}
        try:
            d = cargo(where)
            filas = [x.get("title", {}) for x in d.get("cargoquery", [])]
            r["ok"] = True
            r["partidos"] = len(filas)
            r["con_resultado"] = sum(1 for f in filas if f.get("Winner"))
            r["ejemplo"] = filas[:3]
            if "error" in d:
                r["ok"] = False
                r["error"] = d["error"]
        except Exception as ex:
            r["ok"] = False
            r["error"] = str(ex)[:300]
        out["pruebas"].append(r)
        print(nombre, "->", "OK %s partidos (%s con resultado)" % (r.get("partidos"), r.get("con_resultado")) if r["ok"] else "ERROR " + r.get("error", ""))
    os.makedirs("data", exist_ok=True)
    with open("data/lol_prueba.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
