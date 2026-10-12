#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bir ulke icin tum otomatik sayfalari uretir (dbwn, WB gostergeleri, tek
tarafli ticaret, ikili ticaret (TUR), harita) ve haritayi ulke hub sayfasinda
YAML basliginin hemen altina yerlestirir.

Alt surecler tek tek calistirilir; ciktilar canli olarak akar ve her biri icin
OK/HATA durumu raporlanir. Herhangi biri basarisiz olursa cikis kodu sifirdan
farkli olur.

Kullanim:
    python getCountry.py Nepal
    python getCountry.py NPL
    python getCountry.py Yeni Zelanda
"""

import os
import subprocess
import sys

import notebox as nb


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

GENERATORS = [
    ("getDbn.py", []),
    ("getData.py", []),
    ("getStmd.py", []),
    ("getTmd.py", []),
    ("getTbupNotes.py", ["--yes"]),
]
MAP_SCRIPT = "getMap.py"

NO_DATA_CODE = 2

MAP_HEIGHT = int(os.environ.get("NOTES_MAP_HEIGHT", "350"))


def _status_label(code):
    if code == 0:
        return "OK"
    if code == NO_DATA_CODE:
        return "VERİ YOK"
    return f"HATA (kod {code})"


def _extract(out, prefix):
    value = ""
    for line in (out or "").splitlines():
        if line.startswith(prefix):
            value = line[len(prefix):].strip()
    return value


def _run(script, args, env):
    """Alt sureci calistirir, ciktisini canli akitir. Donus: (cikti, kod)."""
    path = os.path.join(SCRIPT_DIR, script)
    print(f"=== {script} {' '.join(args)} ===", flush=True)
    try:
        proc = subprocess.Popen([sys.executable, path] + args, env=env,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True, bufsize=1)
    except OSError as exc:
        print(f"HATA {script} çalıştırılamadı: {exc}", flush=True)
        return "", 1
    chunks = []
    for line in proc.stdout:
        print(line, end="", flush=True)
        chunks.append(line)
    code = proc.wait()
    out = "".join(chunks)
    print(f"--- {script}: {_status_label(code)}", flush=True)
    return out, code


def _summary(statuses):
    """(sert hatalar, veri-yok adımları, etiketli özet satırları) döner."""
    hard = [(script, code) for script, code in statuses if code != 0
            and code != NO_DATA_CODE]
    nodata = [script for script, code in statuses if code == NO_DATA_CODE]
    lines = []
    for script, code in statuses:
        if code == 0:
            label = "[OK]"
        elif code == NO_DATA_CODE:
            label = "[VERİ YOK]"
        else:
            label = "[HATA]"
        lines.append(f"{label} {script} (kod {code})")
    return hard, nodata, lines


def run():
    arg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "TUR"
    iso3, display, country_field = nb.resolve_country(arg)
    if not iso3:
        print(f"HATA getCountry: Ülke ISO3 kodu çözülemedi: {arg}")
        return 1
    print(f"Ülke: {display} ({iso3})")

    notes = nb.notes_dir()
    env = dict(os.environ)
    env["NOTES_DIR"] = notes
    env.setdefault("NOTES_BIB_DIR", nb.bib_dir(notes))
    env["GMAP_NOTES_DIR"] = notes
    env["GMAP_MAPS_DIR"] = os.path.join(notes, "data", "img", "maps")
    env.setdefault("TBUP_PDF_DIR", os.path.join(notes, "tbupPdfs"))

    statuses = []
    indices = []
    for script, extra in GENERATORS:
        out, code = _run(script, [iso3] + extra, env)
        statuses.append((script, code))
        idx = _extract(out, "INDEX: ")
        if idx:
            indices.append(idx)

    map_out, map_code = _run(MAP_SCRIPT, [iso3], env)
    statuses.append((MAP_SCRIPT, map_code))
    map_path = _extract(map_out, "MAP: ")

    hub = nb.find_country_hub(iso3)
    if not hub and nb.autohub():
        hub = nb._create_country_hub(iso3, country_field, display)

    if hub and map_path and os.path.exists(map_path):
        rel = os.path.relpath(map_path, os.path.dirname(hub))
        nb.set_hub_map(hub, rel, MAP_HEIGHT)
    elif not hub:
        print("UYARI ülke hub'ı yok; harita yerleştirilmedi")

    hard, nodata, lines = _summary(statuses)

    print("=== Özet ===")
    for line in lines:
        print(line)
    if hub:
        print(f"HUB: {hub}")
    if indices:
        print(f"INDEX: {indices[-1]}")
    if hard:
        detail = "; ".join(f"{s} (kod {c})" for s, c in hard)
        print(f"FAILED: {detail}")
    if nodata:
        print(f"NODATA: {'; '.join(nodata)}")

    if hard or not (hub or indices):
        return 1
    return 0


def main():
    try:
        return run()
    except Exception as exc:
        print(f"HATA getCountry: {type(exc).__name__}: {exc}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
