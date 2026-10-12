#!/home/osman/.vim/plugged/vim-notebox/plugin/scripts/venv/bin/python3
# -*- coding: utf-8 -*-
"""getTbupPdf.py

Download the T.C. Ticaret Bakanligi "Ulke Profili" PDF for a country.

Given a Turkish country name or an ISO3 code, this module resolves the
country's region and slug on ticaret.gov.tr/yurtdisi-teskilati, locates the
country-profile PDF link, and downloads it.

Site flow:
    ticaret.gov.tr/yurtdisi-teskilati                 (12 regions)
      /{region}                                        (lists countries)
        /{country}                                      (country page)
          /{country}/ulke-profili                       (profile tab)
            <a href=".../data/.../XXX Ulke Profili_2026.pdf">

Configuration (environment variables):
    TBUP_PDF_DIR   download folder (default: tbupPdfs, relative to CWD)
    TBUP_CACHE     region/country map cache JSON
                   (default: <scriptdir>/scriptData/tbupNotes/regions.json)

Usage:
    getTbupPdf.py <country|iso3> [--dir DIR] [--refresh]
"""

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
from urllib.parse import quote, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cnlook as lu  # noqa: E402

BASE = "https://ticaret.gov.tr"
ROOT = BASE + "/yurtdisi-teskilati"
BASE_HOST = "ticaret.gov.tr"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
TIMEOUT = 45

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CACHE = os.path.join(SCRIPT_DIR, "scriptData", "tbupNotes", "regions.json")
DEFAULT_PDF_DIR = os.environ.get("TBUP_PDF_DIR", "tbupPdfs")

# Region slugs, in the order they appear on the main page.
REGIONS = [
    "afrika",
    "avrupa",
    "avustralya",
    "dogu-asya",
    "guney-amerika",
    "guney-asya",
    "guney-dogu-asya",
    "karayipler",
    "kuzey-amerika",
    "orta-amerika",
    "orta-asya",
    "orta-dogu-ve-korfez",
]

# PDF file-name fragments that are never the country profile.
PDF_BLACKLIST = ("ekonomikgorunum", "serbestbolge", "cerez")

_STOPWORDS = {"federal", "cumhuriyeti", "halk", "demokratik", "devleti",
              "kralligi", "birlesik", "ve"}

ALIASES = {
    "ABD": "USA",
    "Amerika": "USA",
    "Amerika Birleşik Devletleri": "USA",
    "İngiltere": "GBR",
    "Britanya": "GBR",
    "Birleşik Krallık": "GBR",
    "BAE": "ARE",
    "Güney Kore": "KOR",
    "Kuzey Kore": "PRK",
    "Türkiye": "TUR",
    "turkiye": "TUR",
    "Çekya": "CZE",
}


# --------------------------------------------------------------------- helpers

def clean(s):
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def ascii_fold(s):
    """Fold to plain ascii, lowercase, drop every non-alphanumeric char."""
    s = clean(s)
    for a, b in (("İ", "i"), ("I", "i"), ("ı", "i"), ("Ş", "s"), ("ş", "s"),
                 ("Ğ", "g"), ("ğ", "g"), ("Ü", "u"), ("ü", "u"), ("Ö", "o"),
                 ("ö", "o"), ("Ç", "c"), ("ç", "c")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]", "", s.lower())


def norm_name(s):
    """Normalise a country name for map lookups (Turkish-aware)."""
    return re.sub(r"[^a-z0-9]", "", ascii_fold(s))


def cache_path():
    return os.environ.get("TBUP_CACHE", DEFAULT_CACHE)


def _get(url):
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def _abs_url(href):
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return BASE + href
    return href


def _encode_url(url):
    """Percent-encode the path (spaces, non-ascii) while keeping host/query."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc,
                       quote(parts.path, safe="/%"), parts.query,
                       parts.fragment))


# ------------------------------------------------------------- country map

def build_country_map(refresh=False):
    """Return {norm_country_name: {region, slug, display}}, cached to JSON."""
    path = cache_path()
    if not refresh and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("countries"):
                return data["countries"]
        except (OSError, ValueError):
            pass

    countries = {}
    for region in REGIONS:
        try:
            soup = BeautifulSoup(_get(f"{ROOT}/{region}"), "html.parser")
        except requests.RequestException as exc:
            print(f"UYARI {region} bölgesi alınamadı: {exc}")
            continue
        pattern = re.compile(
            rf"^/yurtdisi-teskilati/{re.escape(region)}/([a-z0-9-]+)/?$")
        for a in soup.find_all("a", href=True):
            match = pattern.match(a["href"])
            if not match:
                continue
            slug = match.group(1)
            display = clean(a.get_text())
            key = norm_name(display)
            if not key or key in countries or slug == region:
                continue
            countries[key] = {"region": region, "slug": slug,
                              "display": display}

    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {"generated": dt.datetime.now().isoformat(timespec="seconds"),
               "regions": REGIONS, "countries": countries}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    return countries


def resolve_country(arg):
    """Resolve user input to (iso3 or None, canonical name, norm key)."""
    arg = clean(arg)
    if not arg:
        return None, "", ""
    up = arg.upper()
    if up in lu.iso3:
        return up, lu.iso3ToName(up), norm_name(lu.iso3ToName(up))
    if arg in lu.countryNames:
        iso3 = lu.name2Iso3(arg)
        return (iso3, arg, norm_name(arg)) if iso3 != 1 else (None, arg, norm_name(arg))
    alias = ALIASES.get(arg)
    if alias is None:
        na = norm_name(arg)
        for k, v in ALIASES.items():
            if norm_name(k) == na:
                alias = v
                break
    if alias and alias in lu.iso3:
        name = lu.iso3ToName(alias)
        return alias, name, norm_name(name)
    return None, arg, norm_name(arg)


def find_country(country, refresh=False):
    """Return the map entry {region, slug, display} for a country, or None."""
    iso3, display, key = resolve_country(country)
    countries = build_country_map(refresh)
    entry = countries.get(key) or countries.get(norm_name(display))
    if entry is None:
        for cand in countries.values():
            if cand["slug"] == clean(country).lower():
                entry = cand
                break
    if entry is None and not refresh:
        countries = build_country_map(refresh=True)
        entry = countries.get(key) or countries.get(norm_name(display))
    return entry


# ------------------------------------------------------------- profile lookup

def find_profile_url(country, refresh=False):
    """Return (pdf_url, filename) for the country profile, or None."""
    entry = find_country(country, refresh)
    if not entry:
        return None
    page_url = f"{ROOT}/{entry['region']}/{entry['slug']}/ulke-profili"
    soup = BeautifulSoup(_get(page_url), "html.parser")

    candidates = []
    for a in soup.find_all("a", href=True):
        href = _abs_url(a["href"])
        if ".pdf" not in href.lower() or not href.startswith("http"):
            continue
        filename = html.unescape(urlsplit(href).path.rsplit("/", 1)[-1])
        candidates.append((href, filename))

    def is_blacklisted(name):
        folded = ascii_fold(name)
        return any(frag in folded for frag in PDF_BLACKLIST)

    # 1) filename contains "ulkeprofil" (UlkeProfili / Ülke Profili).
    for href, name in candidates:
        if "ulkeprofil" in ascii_fold(name):
            return href, name
    # 2) filename contains the country name.
    key = norm_name(entry["display"])
    for href, name in candidates:
        if key and key in ascii_fold(name):
            return href, name
    # 3) exactly one non-blacklisted pdf.
    rest = [c for c in candidates if not is_blacklisted(c[1])]
    if len(rest) == 1:
        return rest[0]
    return None


def safe_filename(name):
    name = html.unescape(name).replace("\xa0", " ").strip()
    name = re.sub(r"[\\/]+", "-", name)
    return name or "ulke-profili.pdf"


def find_local_pdf(country, dest_dir=None):
    """Return a previously downloaded PDF for the country, or None."""
    dest_dir = dest_dir or DEFAULT_PDF_DIR
    if not os.path.isdir(dest_dir):
        return None
    _, display, _ = resolve_country(country)
    key = norm_name(display) if display else norm_name(country)
    fallback = None
    for name in sorted(os.listdir(dest_dir)):
        if not name.lower().endswith(".pdf"):
            continue
        folded = ascii_fold(name)
        if "ulkeprofil" in folded and (not key or key in folded):
            return os.path.join(dest_dir, name)
        if key and key in folded and fallback is None:
            fallback = os.path.join(dest_dir, name)
    return fallback


def download_tbup_pdf_info(country, dest_dir=None, refresh=False):
    """Download the country profile PDF.

    Returns {"path", "url", "filename"} on success, or None. If the site is
    unreachable but a local copy exists, the local copy is used (url=None).
    """
    dest_dir = dest_dir or DEFAULT_PDF_DIR
    try:
        found = find_profile_url(country, refresh)
    except requests.RequestException as exc:
        print(f"UYARI ülke profili sayfasına ulaşılamadı: {exc}")
        found = None
    if not found:
        local = find_local_pdf(country, dest_dir)
        if local:
            print(f"Yerel PDF kullanılıyor: {local}")
            return {"path": local, "url": None,
                    "filename": os.path.basename(local)}
        print(f"Ülke profili PDF'i bulunamadı: {country}")
        return None
    url, filename = found
    filename = safe_filename(filename)
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, filename)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        print(f"Zaten mevcut: {path}")
        return {"path": path, "url": url, "filename": filename}
    try:
        response = requests.get(_encode_url(url), headers=HEADERS, stream=True,
                                timeout=TIMEOUT)
        response.raise_for_status()
        with open(path, "wb") as fh:
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    fh.write(chunk)
    except requests.RequestException as exc:
        print(f"UYARI PDF indirilemedi: {exc}")
        local = find_local_pdf(country, dest_dir)
        if local and os.path.getsize(local) > 0:
            print(f"Yerel PDF kullanılıyor: {local}")
            return {"path": local, "url": None,
                    "filename": os.path.basename(local)}
        return None
    print(f"İndirildi: {path}")
    return {"path": path, "url": url, "filename": filename}


def download_tbup_pdf(country, dest_dir=None, refresh=False):
    """Download the country profile PDF. Returns the local path, or None."""
    info = download_tbup_pdf_info(country, dest_dir=dest_dir, refresh=refresh)
    return info["path"] if info else None


# ------------------------------------------------------------------- CLI

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Ticaret Bakanlığı Ülke Profili PDF indirici")
    parser.add_argument("country", help="ülke adı (TR) veya ISO3 kodu")
    parser.add_argument("--dir", dest="dest_dir", default=None,
                        help=f"indirme klasörü (varsayılan: {DEFAULT_PDF_DIR})")
    parser.add_argument("--refresh", action="store_true",
                        help="bölge/ülke haritasını yeniden tarayıp önbelleği tazele")
    args = parser.parse_args(argv)

    path = download_tbup_pdf(args.country, dest_dir=args.dest_dir,
                             refresh=args.refresh)
    if not path:
        return 1
    print(f"PDF: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
