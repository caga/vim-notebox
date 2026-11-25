#!/home/osman/.vim/plugged/vim-notebox/plugin/scripts/venv/bin/python3
# -*- coding: utf-8 -*-
"""Bir ulke icin tum otomatik sayfalari uretir (dbwn, WB gostergeleri, tek
tarafli ticaret, ikili ticaret (TUR), harita) ve haritayi ulke hub sayfasinda
YAML basliginin hemen altina yerlestirir.  Tubitak/KOSGEB/TUYSGM/diger kurum
bilgi notlari ve ulkenin `perm cvb` profillerinden CV tablolari da uretilir.

Alt surecler tek tek calistirilir; ciktilar canli olarak akar ve her biri icin
OK/HATA durumu raporlanir. Herhangi biri basarisiz olursa cikis kodu sifirdan
farkli olur.

Kullanim:
    ./getCountry.py Nepal
    ./getCountry.py NPL --force
    ./getCountry.py Yeni Zelanda 2025 --box ~/countryNotes
    ./getCountry.py Nepal --skip-tbup --skip-tubitak

Secenekler:
    --box DIR   not kutusu (varsayilan: $NOTES_DIR veya cwd)
    --trade-year YYYY  ticaret raporlari icin yil
                (varsayilan: en yeni veri yili)
    --force     tazelik esigini yok say; tum raporlari ve haritayi yenile
    --delete    ulkenin tum otomatik notlarini ve OBN sayfasini sil
    --delete-data  --delete ile birlikte ulkenin JSON onbellegini
                (data/<iso3>/wbdata) de sil; varsayilan: koru
    --skip-*    ilgili ureticiyi atla (--skip-cv dahil)
"""

import datetime as dt
import os
import subprocess
import sys

import _cli

_cli.init()

import notebox as nb


SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

TRADE_SCRIPTS = ("getUlkeTrapor.py", "getIkiliRapor.py")

GENERATORS = [
    ("getDbn.py", []),
    ("getData.py", []),
    ("getLeaders.py", []),
    ("getUlkeTrapor.py", []),
    ("getIkiliRapor.py", []),
    ("getTbupNotes.py", ["--yes"]),
    ("getTubitakNotes.py", ["--yes"]),
    ("getKosgebNotes.py", ["--yes"]),
    ("getTuysgmNotes.py", ["--yes"]),
    ("getOtherBns.py", ["--yes"]),
    ("generateCv.py", ["--all"]),
    ("getObnFiles.py", []),
]
MAP_SCRIPT = "getMap.py"

NO_DATA_CODE = 2

MAP_HEIGHT = int(os.environ.get("NOTES_MAP_HEIGHT", "350"))

# vim tarafindan gonderilen atlama bayraklari -> script adi
SKIP_FLAGS = {"--skip-leaders": "getLeaders.py",
              "--skip-stmd": "getUlkeTrapor.py",
              "--skip-tmd": "getIkiliRapor.py",
              "--skip-tbup": "getTbupNotes.py",
              "--skip-tubitak": "getTubitakNotes.py",
              "--skip-kosgeb": "getKosgebNotes.py",
              "--skip-tuysgm": "getTuysgmNotes.py",
              "--skip-otherbn": "getOtherBns.py",
              "--skip-cv": "generateCv.py",
              "--skip-obnfiles": "getObnFiles.py"}

# --force verildiginde tazelik esigini yok sayan betikler. getDbn esik
# kullanmaz; getData kendi not modify yasina gore artimli/tam calisir ve
# --force ile tum gostergeleri yeniler. getMap --force ile yeniden indirir.
FORCE_FLAGS = {"getData.py", "getLeaders.py", *TRADE_SCRIPTS,
               "getTbupNotes.py", "getTubitakNotes.py", "getKosgebNotes.py",
               "getTuysgmNotes.py", "getOtherBns.py", MAP_SCRIPT}


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


def _summary(statuses, skipped=()):
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
    for script in skipped:
        lines.append(f"[ATLANDI] {script}")
    return hard, nodata, lines


def _parse_trade_year(argv):
    """--trade-year YYYY / --trade-year=YYYY; verilmezse None."""
    year, rest = None, []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--trade-year":
            if i + 1 >= len(argv):
                raise ValueError("--trade-year bir yıl gerektirir")
            year = argv[i + 1]
            i += 2
            continue
        if arg.startswith("--trade-year="):
            year = arg.split("=", 1)[1]
            i += 1
            continue
        rest.append(arg)
        i += 1
    return year, rest


def _validate_year(year):
    try:
        year = int(year)
    except (TypeError, ValueError):
        raise ValueError(f"Geçersiz ticaret yılı: {year}")
    this_year = dt.date.today().year
    if year < 2001 or year > this_year:
        raise ValueError(f"Ticaret yılı 2001-{this_year} aralığında olmalı: {year}")
    return year


def run():
    try:
        trade_year, argv = _parse_trade_year(sys.argv[1:])
    except ValueError as exc:
        print(f"HATA getCountry: {exc}")
        return 1
    flags, positional = set(), []
    for a in argv:
        if a.startswith("--"):
            flags.add(a)
        else:
            positional.append(a)
    # Yil bayraksiz da verilebilir: "./getCountry.py Nepal 2025"
    if (trade_year is None and len(positional) > 1
            and positional[-1].isdigit() and len(positional[-1]) == 4):
        trade_year, positional = positional[-1], positional[:-1]
    try:
        if trade_year is not None:
            trade_year = _validate_year(trade_year)
    except ValueError as exc:
        print(f"HATA getCountry: {exc}")
        return 1
    arg = " ".join(positional) if positional else "TUR"
    skip = {SKIP_FLAGS[f] for f in flags if f in SKIP_FLAGS}
    force = "--force" in flags
    iso3, display, country_field = nb.resolve_country(arg)
    if not iso3:
        print(f"HATA getCountry: Ülke ISO3 kodu çözülemedi: {arg}")
        return 1
    if "--delete" in flags:
        try:
            import getObnFiles
            getObnFiles.delete_country_files(iso3, country_field, display)
        except Exception as exc:
            print(f"UYARI obn files sayfası silinemedi: {exc}")
        rc = nb.delete_country_obn(iso3, country_field, display,
                                   delete_data="--delete-data" in flags)
        leaders_hub = nb.find_hub_by_type("hub leaders")
        if leaders_hub:
            nb.prune_hub_links(leaders_hub)
        return rc
    trade_year_text = ("en yeni veri" if trade_year is None
                       else str(trade_year))
    print(f"Ülke: {display} ({iso3}) — ticaret yılı: {trade_year_text}")

    notes = nb.notes_dir()
    env = dict(os.environ)
    # Alt betiklerin tanilama satirlari tamponda beklemeden aksin.
    env["PYTHONUNBUFFERED"] = "1"
    env["NOTES_DIR"] = notes
    env.setdefault("NOTES_BIB_DIR", nb.bib_dir(notes))
    env["GMAP_NOTES_DIR"] = notes
    env["GMAP_MAPS_DIR"] = os.path.join(notes, "data", "img", "maps")
    env.setdefault("TBUP_PDF_DIR", os.path.join(notes, "tbupPdfs"))

    statuses = []
    skipped = []
    indices = []
    for script, extra in GENERATORS:
        if script in skip:
            print(f"=== {script} (ATLANDI) ===", flush=True)
            skipped.append(script)
            continue
        args = [iso3] + list(extra)
        if script in TRADE_SCRIPTS and trade_year is not None:
            args.append(str(trade_year))
        if force and script in FORCE_FLAGS:
            args.append("--force")
        out, code = _run(script, args, env)
        statuses.append((script, code))
        idx = _extract(out, "INDEX: ")
        if idx:
            indices.append(idx)

    map_args = [iso3] + (["--force"] if force else [])
    map_out, map_code = _run(MAP_SCRIPT, map_args, env)
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

    hard, nodata, lines = _summary(statuses, skipped)

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
