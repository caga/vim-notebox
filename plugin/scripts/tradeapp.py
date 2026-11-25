# -*- coding: utf-8 -*-
"""Trade Map koprusu: tmapp paketi ile vim-notebox not uretimini birlestirir.

tmapp (~/calisma/tmapp) icindeki ``ulkeTrapor.py``, ``ikiliRapor.py`` ve
``tRwF.py`` modulleri dogrudan ice aktarilir; betiklerin urettigi markdown
govdesi degistirilmeden nota yazilir. tmapp kodu bu modulden asla degistirilmez;
paket yalnizca kendi JSON onbellegini (``outputs/json``) kullanir.

Ortam degiskenleri:
    TRADEAPP_DIR : tmapp kok dizini (varsayilan ~/calisma/tmapp)
"""

import datetime as dt
import json
import os
import sys
from pathlib import Path

import notebox as nb

DEFAULT_TRADEAPP_DIR = "~/calisma/tmapp"
MIN_YEAR = 2001

SINGLE_SUFFIX = "Dış Ticaret Rakamları"
FIGURE_SUFFIX = "Dış Ticaret Rakamları -Şekilli"
BILATERAL_SUFFIX = "İkili Ticaret Rakamları"

SOURCE_URL = "https://www.trademap.org/"
BIB_AUTHOR = "International Trade Centre (ITC)"
BIB_HOWPUBLISHED = "Trade Map"


# ----------------------------------------------------------------- tmapp erisimi

def tradeapp_dir() -> Path:
    """tmapp kok dizini ($TRADEAPP_DIR veya varsayilan)."""
    raw = os.environ.get("TRADEAPP_DIR") or DEFAULT_TRADEAPP_DIR
    return Path(raw).expanduser()


def _prepare() -> Path:
    """tmapp'i sys.path'e ekler ve dizinin gecerli oldugunu dogrular."""
    root = tradeapp_dir()
    if not (root / "reportModule.py").is_file():
        raise RuntimeError(
            f"tmapp bulunamadı: {root} (g:tradeapp_dir / $TRADEAPP_DIR)")
    path = str(root)
    if path not in sys.path:
        sys.path.insert(0, path)
    return root


def _countries() -> list[dict]:
    root = _prepare()
    path = root / "sdata" / "countries.tr.iso.json"
    if not path.is_file():
        raise RuntimeError(f"Ülke verisi bulunamadı: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def m49_for(iso3: str | None, query: str | None = None) -> str:
    """ISO3 (veya ulke adi) -> Trade Map/M49 ulke kodu.

    cnlook ile tmapp'in Turkce adlari 46 ulkede ayrisir; bu yuzden nota basligi
    cnlook'tan, sorgu ise ISO3 uzerinden M49 koduna cevrilir.
    """
    want = (iso3 or "").casefold()
    rows = _countries()
    if want:
        for row in rows:
            if (row.get("iso3") or "").casefold() == want:
                code = row.get("countryCd")
                if code:
                    return code
    if query:
        q = query.strip().casefold()
        for row in rows:
            names = ((row.get("label") or "").casefold(),
                     (row.get("labeltr") or "").casefold())
            if q in names:
                code = row.get("countryCd")
                if code:
                    return code
    raise LookupError(f"Ülke Trade Map koduna çevrilemedi: {query or iso3}")


def country_report(country: str, year: int) -> str:
    """ulkeTrapor.build_country_report (5 tablo)."""
    _prepare()
    from ulkeTrapor import build_country_report
    return build_country_report(country, year)


def country_figures(country: str, year: int) -> str:
    """tRwF.build_report (tablolar + mermaid grafikleri)."""
    _prepare()
    from tRwF import build_report
    return build_report(country, year)


def bilateral_report(partner: str, year: int) -> str:
    """ikiliRapor.build_bilateral_report (3 tablo)."""
    _prepare()
    from ikiliRapor import build_bilateral_report
    return build_bilateral_report(partner, year)


def latest_year(country: str, partner: str = "000",
                flows: tuple[str, ...] = ("E", "I")) -> int | None:
    """İki akış için de veri bulunan en yeni Trade Map yılını döndürür.

    Args:
        country: Reporter M49 kodu (ör. "036").
        partner: Partner M49 kodu; "000" (varsayılan) tüm dünya.
        flows: Kesit alınacak akışlar; varsayılan ("E", "I").

    Returns:
        En yeni ortak yıl, veri yoksa None.
    """
    _prepare()
    import fetchModule
    return fetchModule.latest_available_year(country, partner, flows=flows)


# ------------------------------------------------------------------ CLI yardimci

def parse_flags(argv: list[str]) -> tuple[set[str], list[str]]:
    flags, positional = set(), []
    for arg in argv:
        if arg.startswith("--"):
            flags.add(arg)
        else:
            positional.append(arg)
    return flags, positional


def parse_year(value) -> int:
    text = str(value or "").strip()
    if not text.isdigit():
        raise ValueError(f"Yıl gerekli (4 hane, ör. 2025): {value!r}")
    year = int(text)
    this_year = dt.date.today().year
    if year < MIN_YEAR or year > this_year:
        raise ValueError(f"Yıl {MIN_YEAR}-{this_year} aralığında olmalı: {year}")
    return year


def split_country_year(positional: list[str],
                       required: bool = True) -> tuple[str, int | None]:
    """Son 4 haneli arguman yil, kalani (bosluklu) ulke adidir."""
    if not positional:
        raise ValueError("Ülke gerekli")
    if not required:
        if (len(positional) > 1 and positional[-1].isdigit()
                and len(positional[-1]) == 4):
            return " ".join(positional[:-1]), parse_year(positional[-1])
        return " ".join(positional), None
    if len(positional) < 2 or not positional[-1].isdigit():
        raise ValueError("Yıl gerekli: <ülke> <yıl> (ör. Yeni Zelanda 2025)")
    return " ".join(positional[:-1]), parse_year(positional[-1])


# --------------------------------------------------------------- rapor/tazelik

def report_entry(country_field: str, display: str, title: str,
                 n_type: str):
    """(entry, gun, kaynak) - mevcut rapor notu (yoksa entry None)."""
    found, _ = nb.find_country_files(country_field, display, (n_type,))
    entry = found.get(nb.slugify(title))
    if not entry:
        return None, None, None
    days, source, _raw = nb.note_age(entry["path"])
    return entry, days, source


def report_age_text(title: str, days, source) -> str:
    if days is None:
        return f"{title} (tarih bilgisi yok)."
    verb = "güncellendi" if source == "modify" else "oluşturuldu"
    return f"{title} {nb.human_age(days)} {verb}."


def is_fresh(days) -> bool:
    return days is not None and days < nb.REPORT_MAX_AGE_DAYS


def body_has_year(path: str, year: int) -> bool:
    """Not govdesi istenen yil icin veri tasiyor mu?

    tmapp tablolari ``Table: ... (2025)``, eski getStmd notlari ise
    ``$(2025)`` bicimini kullanir; ``(2025)`` her ikisinde de bulunur.
    """
    try:
        with open(path, encoding="utf-8") as f:
            return f"({year})" in f.read()
    except OSError:
        return False


def emit_check(path: str, days, source, fresh: bool, text: str):
    print(f"REPORT_EXISTS: {path}")
    print(f"REPORT_AGE_DAYS: {'' if days is None else days}")
    print(f"REPORT_AGE_SOURCE: {source}")
    print(f"REPORT_FRESH: {1 if fresh else 0}")
    print(f"REPORT_AGE_TEXT: {text}")


# -------------------------------------------------------------------- not yazma

def emit_note(display: str, iso3: str | None, title: str, n_type: str,
              body: str, country_field: str, used: set,
              existing_ids: set):
    """Raporu id-kararli sekilde yazar; bib kaynagi Trade Map'tir."""
    return nb.emit_note(display, iso3, title, n_type, body, SOURCE_URL,
                        country_field, used, existing_ids,
                        bib_author=BIB_AUTHOR,
                        bib_howpublished=BIB_HOWPUBLISHED)
