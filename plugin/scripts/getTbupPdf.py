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

The profile link is read from the country page instead of being constructed:
the site sometimes uses a different region segment there (for Australia the
listing region is "avustralya" but the profile link is under "avusturalya").

Configuration (environment variables):
    TBUP_PDF_DIR   download folder (default: <notes>/tbupPdfs)
    NOTES_DIR      note box used to derive the default download folder
    TBUP_CACHE     region/country map cache JSON
                   (default: <scriptdir>/scriptData/tbupNotes/regions.json)

Usage:
    ./getTbupPdf.py <country|iso3> [--dir DIR] [--box DIR] [--refresh]
"""

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import time
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import _cli

if __name__ == "__main__":
    _cli.init(help=False)

import requests
from bs4 import BeautifulSoup

import cnlook as lu
import notebox as nb

BASE = "https://ticaret.gov.tr"
ROOT = BASE + "/yurtdisi-teskilati"
BASE_HOST = "ticaret.gov.tr"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
TIMEOUT = 45

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
DEFAULT_CACHE = os.path.join(SCRIPT_DIR, "scriptData", "tbupNotes", "regions.json")
CACHE_VERSION = 2


def default_pdf_dir():
    """Default download folder: $TBUP_PDF_DIR or <notes box>/tbupPdfs.

    NOTES_DIR is set by --box in the entry scripts, by the Vim wrappers, or
    comes from the environment; the cwd is the last-resort fallback.
    """
    explicit = os.environ.get("TBUP_PDF_DIR")
    if explicit:
        return explicit
    notes = os.environ.get("NOTES_DIR") or os.getcwd()
    return os.path.join(notes, "tbupPdfs")

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

# The TBUP site sometimes uses a different display name from cnlook.  These
# normalized aliases map the user/cnlook key to the key stored in
# regions.json.  Without them, e.g. "Çin" or "Ekvador" is in the cache but
# cannot be reached by its ISO3 code or standard Turkish name.
SITE_ALIASES = {
    "amerikabirlesikdevletleri": "abd",
    "abd": "abd",
    "usa": "abd",
    "cin": "cinhalkcumhuriyeti",
    "chn": "cinhalkcumhuriyeti",
    "ekvador": "ekvator",
    "ecu": "ekvator",
    "guneyafrika": "guneyafrikacumhuriyeti",
    "zaf": "guneyafrikacumhuriyeti",
    "guneykore": "guneykorecumhuriyeti",
    "korecumhuriyeti": "guneykorecumhuriyeti",
    "kor": "guneykorecumhuriyeti",
    "liechtenstein": "lihtenstayn",
    "lie": "lihtenstayn",
    "mauritius": "morityus",
    "mus": "morityus",
    "kktc": "kuzeykibristc",
    "kuzeykibris": "kuzeykibristc",
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
    response = nb.http_get(url, headers=HEADERS, timeout=TIMEOUT)
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
    existing_countries = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            existing_countries = data.get("countries") or {}
            if (not refresh and data.get("version") == CACHE_VERSION
                    and existing_countries):
                return existing_countries
        except (OSError, ValueError):
            existing_countries = {}

    countries = {}
    failed = []
    for region in REGIONS:
        soup = None
        last_exc = None
        for attempt in range(2):
            try:
                soup = BeautifulSoup(_get(f"{ROOT}/{region}"), "html.parser")
                break
            except requests.RequestException as exc:
                last_exc = exc
                if attempt == 0:
                    time.sleep(1)
        if soup is None:
            print(f"UYARI {region} bölgesi alınamadı: {last_exc}")
            failed.append(region)
            continue

        # Slugs are not always lowercase/ASCII: Sri Lanka is "sri-Lanka",
        # Kenya is "Kenya", KKTC is "KKTC", Karadağ is "karadağ", Sırbistan
        # is "sırbistan".  Keep the original slug because the site URLs are
        # case-sensitive; decode percent-encoded Turkish characters.
        pattern = re.compile(
            rf"^/yurtdisi-teskilati/{re.escape(region)}/([^/?#]+)/?$",
            re.IGNORECASE)
        for a in soup.find_all("a", href=True):
            href_path = urlsplit(_abs_url(a["href"])).path
            match = pattern.match(href_path)
            if not match:
                continue
            slug = unquote(match.group(1))
            display = clean(a.get_text())
            key = norm_name(display)
            # Do not skip slug == region: Australia's country page is
            # /yurtdisi-teskilati/avustralya/avustralya.  The region root
            # link (without a slug segment) does not match `pattern` anyway.
            if not key or key in countries:
                continue
            countries[key] = {"region": region, "slug": slug,
                              "display": display}

    if not countries:
        print("UYARI ülke haritası boş; önbellek yazılmadı")
        return existing_countries

    if failed:
        # Do not replace a usable cache with a partial map when a region
        # request fails.  Keep previously known countries for failed regions
        # in the returned map, and retry the download on the next call.
        print(f"UYARI {len(failed)} bölge alınamadı; önbellek yazılmadı: "
              f"{', '.join(failed)}")
        merged = dict(existing_countries)
        merged.update(countries)
        return merged

    cache_dir = os.path.dirname(path)
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
    payload = {"version": CACHE_VERSION,
               "generated": dt.datetime.now().isoformat(timespec="seconds"),
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


def _lookup_country(countries, display, key, raw):
    """Look up a country by name key, site alias, or slug."""
    entry = countries.get(key) or countries.get(norm_name(display))
    wanted = norm_name(raw)
    if entry is None and wanted:
        alias = SITE_ALIASES.get(wanted)
        if alias:
            entry = countries.get(alias)
    if entry is None and wanted:
        for cand in countries.values():
            if norm_name(cand["slug"]) == wanted:
                return cand
    return entry


def find_country(country, refresh=False):
    """Return the map entry {region, slug, display} for a country, or None."""
    _iso3, display, key = resolve_country(country)
    countries = build_country_map(refresh)
    entry = _lookup_country(countries, display, key, country)
    if entry is None and not refresh:
        countries = build_country_map(refresh=True)
        entry = _lookup_country(countries, display, key, country)
    return entry


# ------------------------------------------------------------- profile lookup

def find_profile_url(country, refresh=False):
    """Return (pdf_url, filename) for the country profile, or None."""
    entry = find_country(country, refresh)
    if not entry:
        return None

    # Follow the site's own "Ülke Profili" link.  The region segment in that
    # link is not always the same as the listing region: for Australia the
    # country page is /avustralya/avustralya but the profile link is
    # /avusturalya/avustralya/ulke-profili.
    country_url = f"{ROOT}/{entry['region']}/{entry['slug']}"
    soup = BeautifulSoup(_get(country_url), "html.parser")
    profile_url = None
    for a in soup.find_all("a", href=True):
        href = _abs_url(a["href"])
        if "ulke-profili" in href:
            profile_url = href
            break
    if not profile_url:
        profile_url = f"{ROOT}/{entry['region']}/{entry['slug']}/ulke-profili"
    soup = BeautifulSoup(_get(profile_url), "html.parser")

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
    dest_dir = dest_dir or default_pdf_dir()
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
    dest_dir = dest_dir or default_pdf_dir()
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
    ok, exc, _tries = nb.http_download(_encode_url(url), path,
                                       headers=HEADERS, timeout=TIMEOUT)
    if not ok:
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
                        help=f"indirme klasörü (varsayılan: {default_pdf_dir()})")
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
