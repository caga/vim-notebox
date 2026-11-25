#!/home/osman/.vim/plugged/vim-notebox/plugin/scripts/venv/bin/python3
# -*- coding: utf-8 -*-
"""CIA World Leaders sayfasindan bir ulkenin lider ve kabine uyelerini alir
ve not kutusuna standart bir OBN notu olarak yazar.

Not:
    <Ulke> Liderler ve Kabine Uyeleri     (n_type: obn leaders)
    Liderler ve Kabine Dizini             (n_type: hub leaders, kuresel)

Icerik notu ulke OBN sayfasindaki "## Liderler ve Kabine" bolumune dogrudan
baglanir; ulke bazli ayri bir indeks notu uretilmez. Kuresel dizin butun
ulkelerin lider notlarini listeler ve obn-hub.md'den baglanir.

Icerik CIA World Leaders sayfasindaki ozgun Ingilizce gorev unvanlariyla
yazilir; not basligi, tablo basliklari ve OBN bolumu Turkcedir.

Kullanim:
    ./getLeaders.py Nepal
    ./getLeaders.py Mozambik --box ~/countryNotes
    ./getLeaders.py Almanya --force
    ./getLeaders.py Yeni Zelanda --check
    ./getLeaders.py Nepal --link-only

Secenekler:
    --box DIR   not kutusu (varsayilan: $NOTES_DIR veya cwd)
    --check     yalnizca mevcut notun yasini bildir (ag erisimi yok)
    --force     tazelik esigini yok say ve yeniden uret
    --delete    bu betigin ulke icin urettigi notlari sil
    --link-only yalnizca OBN/kuresel dizin baglantilarini yenile (ag yok)
    --slug S    CIA sayfa adini (slug) elle belirt
"""

import contextlib
import datetime as dt
import io
import os
import re
import sys
import unicodedata

import _cli

_cli.init()

import requests

from tabulate import tabulate

import cnlook as lu
import notebox as nb


SCRIPT_NAME = "getLeaders"
N_TYPE = "obn leaders"
KIND_KEY = "leaders"
TITLE_SUFFIX = "Liderler ve Kabine Üyeleri"
SECTION_TITLE = "Liderler ve Kabine"
GLOBAL_N_TYPE = "hub leaders"
GLOBAL_TITLE = "Liderler ve Kabine Dizini"

BASE = "https://www.cia.gov/resources/world-leaders"
PAGE_DATA = BASE + "/page-data/foreign-governments/{slug}/page-data.json"
SOURCE = BASE + "/foreign-governments/{slug}"
TIMEOUT = 45
HEADERS = {
    "User-Agent": "vim-notebox/getLeaders (+https://www.cia.gov/resources/world-leaders/)",
}

REPORT_MAX_AGE_DAYS = int(
    os.environ.get(
        "NOTES_LEADERS_REPORT_MAX_AGE_DAYS",
        os.environ.get("NOTES_REPORT_MAX_AGE_DAYS", "30"),
    )
)

GROUPS = (
    ("leaders_label", "leaders"),
    ("leaders_2_label", "leaders_2"),
    ("leaders_3_label", "leaders_3"),
)

# ISO3 -> CIA World Leaders Ingilizce ulke adi. 199 CIA kaydinda bulunan
# ulke ve XKX (Kosovo) icin tamamlanmistir. CIA yalnizca yabanci hukumetleri
# yayinladigi icin ABD (USA) bu tabloda yoktur.
CIA_COUNTRIES = {
    "ABW": 'Aruba',
    "AFG": 'Afghanistan',
    "AGO": 'Angola',
    "ALB": 'Albania',
    "AND": 'Andorra',
    "ARE": 'United Arab Emirates',
    "ARG": 'Argentina',
    "ARM": 'Armenia',
    "ATG": 'Antigua and Barbuda',
    "AUS": 'Australia',
    "AUT": 'Austria',
    "AZE": 'Azerbaijan',
    "BDI": 'Burundi',
    "BEL": 'Belgium',
    "BEN": 'Benin',
    "BFA": 'Burkina Faso',
    "BGD": 'Bangladesh',
    "BGR": 'Bulgaria',
    "BHR": 'Bahrain',
    "BHS": 'Bahamas, The',
    "BIH": 'Bosnia and Herzegovina',
    "BLR": 'Belarus',
    "BLZ": 'Belize',
    "BMU": 'Bermuda',
    "BOL": 'Bolivia',
    "BRA": 'Brazil',
    "BRB": 'Barbados',
    "BRN": 'Brunei',
    "BTN": 'Bhutan',
    "BWA": 'Botswana',
    "CAF": 'Central African Republic',
    "CAN": 'Canada',
    "CHE": 'Switzerland',
    "CHL": 'Chile',
    "CHN": 'China',
    "CIV": "Cote d'Ivoire",
    "CMR": 'Cameroon',
    "COD": 'Congo, Democratic Republic of the',
    "COG": 'Congo, Republic of the',
    "COK": 'Cook Islands',
    "COL": 'Colombia',
    "COM": 'Comoros',
    "CPV": 'Cabo Verde',
    "CRI": 'Costa Rica',
    "CUB": 'Cuba',
    "CYP": 'Cyprus',
    "CZE": 'Czechia',
    "DEU": 'Germany',
    "DJI": 'Djibouti',
    "DMA": 'Dominica',
    "DNK": 'Denmark',
    "DOM": 'Dominican Republic',
    "DZA": 'Algeria',
    "ECU": 'Ecuador',
    "EGY": 'Egypt',
    "ERI": 'Eritrea',
    "ESP": 'Spain',
    "EST": 'Estonia',
    "ETH": 'Ethiopia',
    "FIN": 'Finland',
    "FJI": 'Fiji',
    "FRA": 'France',
    "FSM": 'Micronesia, Federated States of',
    "GAB": 'Gabon',
    "GBR": 'United Kingdom',
    "GEO": 'Georgia',
    "GHA": 'Ghana',
    "GIN": 'Guinea',
    "GMB": 'Gambia, The',
    "GNB": 'Guinea-Bissau',
    "GNQ": 'Equatorial Guinea',
    "GRC": 'Greece',
    "GRD": 'Grenada',
    "GTM": 'Guatemala',
    "GUY": 'Guyana',
    "HND": 'Honduras',
    "HRV": 'Croatia',
    "HTI": 'Haiti',
    "HUN": 'Hungary',
    "IDN": 'Indonesia',
    "IND": 'India',
    "IRL": 'Ireland',
    "IRN": 'Iran',
    "IRQ": 'Iraq',
    "ISL": 'Iceland',
    "ISR": 'Israel',
    "ITA": 'Italy',
    "JAM": 'Jamaica',
    "JOR": 'Jordan',
    "JPN": 'Japan',
    "KAZ": 'Kazakhstan',
    "KEN": 'Kenya',
    "KGZ": 'Kyrgyzstan',
    "KHM": 'Cambodia',
    "KIR": 'Kiribati',
    "KNA": 'Saint Kitts and Nevis',
    "KOR": 'Korea, South',
    "KWT": 'Kuwait',
    "LAO": 'Laos',
    "LBN": 'Lebanon',
    "LBR": 'Liberia',
    "LBY": 'Libya',
    "LCA": 'Saint Lucia',
    "LIE": 'Liechtenstein',
    "LKA": 'Sri Lanka',
    "LSO": 'Lesotho',
    "LTU": 'Lithuania',
    "LUX": 'Luxembourg',
    "LVA": 'Latvia',
    "MAR": 'Morocco',
    "MCO": 'Monaco',
    "MDA": 'Moldova',
    "MDG": 'Madagascar',
    "MDV": 'Maldives',
    "MEX": 'Mexico',
    "MHL": 'Marshall Islands',
    "MKD": 'North Macedonia',
    "MLI": 'Mali',
    "MLT": 'Malta',
    "MMR": 'Burma',
    "MNE": 'Montenegro',
    "MNG": 'Mongolia',
    "MOZ": 'Mozambique',
    "MRT": 'Mauritania',
    "MUS": 'Mauritius',
    "MWI": 'Malawi',
    "MYS": 'Malaysia',
    "NAM": 'Namibia',
    "NER": 'Niger',
    "NGA": 'Nigeria',
    "NIC": 'Nicaragua',
    "NIU": 'Niue',
    "NLD": 'Netherlands',
    "NOR": 'Norway',
    "NPL": 'Nepal',
    "NRU": 'Nauru',
    "NZL": 'New Zealand',
    "OMN": 'Oman',
    "PAK": 'Pakistan',
    "PAN": 'Panama',
    "PER": 'Peru',
    "PHL": 'Philippines',
    "PLW": 'Palau',
    "PNG": 'Papua New Guinea',
    "POL": 'Poland',
    "PRK": 'Korea, North',
    "PRT": 'Portugal',
    "PRY": 'Paraguay',
    "QAT": 'Qatar',
    "ROU": 'Romania',
    "RUS": 'Russia',
    "RWA": 'Rwanda',
    "SAU": 'Saudi Arabia',
    "SDN": 'Sudan',
    "SEN": 'Senegal',
    "SGP": 'Singapore',
    "SLB": 'Solomon Islands',
    "SLE": 'Sierra Leone',
    "SLV": 'El Salvador',
    "SMR": 'San Marino',
    "SOM": 'Somalia',
    "SRB": 'Serbia',
    "SSD": 'South Sudan',
    "STP": 'Sao Tome and Principe',
    "SUR": 'Suriname',
    "SVK": 'Slovakia',
    "SVN": 'Slovenia',
    "SWE": 'Sweden',
    "SWZ": 'Eswatini',
    "SYC": 'Seychelles',
    "SYR": 'Syria',
    "TCD": 'Chad',
    "TGO": 'Togo',
    "THA": 'Thailand',
    "TJK": 'Tajikistan',
    "TKM": 'Turkmenistan',
    "TLS": 'Timor-Leste',
    "TON": 'Tonga',
    "TTO": 'Trinidad and Tobago',
    "TUN": 'Tunisia',
    "TUR": 'Turkey',
    "TUV": 'Tuvalu',
    "TWN": 'Taiwan',
    "TZA": 'Tanzania',
    "UGA": 'Uganda',
    "UKR": 'Ukraine',
    "URY": 'Uruguay',
    "UZB": 'Uzbekistan',
    "VAT": 'Holy See (Vatican City)',
    "VCT": 'Saint Vincent and the Grenadines',
    "VEN": 'Venezuela',
    "VNM": 'Vietnam',
    "VUT": 'Vanuatu',
    "WSM": 'Samoa',
    "XKX": 'Kosovo',
    "YEM": 'Yemen',
    "ZAF": 'South Africa',
    "ZMB": 'Zambia',
    "ZWE": 'Zimbabwe',
}

def norm_ascii(value):
    """Ingilizce ulke adlarini karsilastirmak icin sadelesmis anahtar."""
    s = unicodedata.normalize("NFKD", value or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("İ", "i").replace("I", "i").replace("ı", "i")
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


CIA_BY_NAME = {norm_ascii(name): code for code, name in CIA_COUNTRIES.items()}
CIA_NAME_ALIASES = {
    "kosova": "XKX",
    "kosovo": "XKX",
    "south korea": "KOR",
    "north korea": "PRK",
    "ivory coast": "CIV",
    "cape verde": "CPV",
    "east timor": "TLS",
    "vatican": "VAT",
    "vatican city": "VAT",
    "uae": "ARE",
    "czech republic": "CZE",
    "swaziland": "SWZ",
    "macedonia": "MKD",
    "drc": "COD",
}
DISPLAY_OVERRIDES = {"XKX": "Kosova"}


def cia_slug(name):
    """CIA sayfa adi: kucuk harf, kesme isareti atilir, digerleri '-'."""
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def parse_args(argv):
    flags = set()
    positional = []
    slug = None
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--slug":
            if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                raise ValueError("--slug bir değer gerektirir")
            slug = argv[i + 1]
            i += 2
            continue
        if arg.startswith("--slug="):
            slug = arg.split("=", 1)[1]
            if not slug:
                raise ValueError("--slug bir değer gerektirir")
            i += 1
            continue
        if arg.startswith("--"):
            flags.add(arg)
        else:
            positional.append(arg)
        i += 1
    return flags, positional, slug


def resolve_country(arg):
    """Kullanici girdisini (Turkce ad, ISO3 veya CIA Ingilizce adi) cozer."""
    with contextlib.redirect_stdout(io.StringIO()):
        iso3, display, country_field = nb.resolve_country(arg)

    if not iso3:
        key = norm_ascii(arg)
        iso3 = CIA_BY_NAME.get(key) or CIA_NAME_ALIASES.get(key)
        if not iso3 and arg.upper() in CIA_COUNTRIES:
            iso3 = arg.upper()
        if iso3:
            display = DISPLAY_OVERRIDES.get(iso3)
            if not display:
                tr_name = lu.iso3ToName(iso3)
                display = tr_name if tr_name != 1 else CIA_COUNTRIES.get(iso3, arg)
            country_field = iso3.lower()

    if not iso3:
        return None
    return iso3, display, country_field


def format_updated(raw):
    raw = (raw or "").strip()
    try:
        return dt.datetime.strptime(raw[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return raw


def fetch_page(slug):
    url = PAGE_DATA.format(slug=slug)
    try:
        response = nb.http_get(url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as exc:
        return None, f"HATA getLeaders: {exc}"

    if response.status_code == 404:
        return None, f"NODATA: CIA World Leaders sayfası yok ({slug})"
    if response.status_code != 200:
        return None, f"HATA getLeaders: HTTP {response.status_code}"

    try:
        page = response.json()["result"]["data"]["page"]
    except (ValueError, KeyError, TypeError):
        return None, "HATA getLeaders: CIA yanıtı çözümlenemedi"

    return page, None


def leader_groups(page):
    groups = []
    for label_key, rows_key in GROUPS:
        rows = page.get(rows_key) or []
        if not rows:
            continue
        groups.append((nb.clean(page.get(label_key, "")), rows))
    return groups


def group_leaders(rows):
    """Ayni kisinin birden cok gorevini tek satirda toplar.
    Ilk gorulme sirasini korur; unvanlari CIA sirasinda biriktirir."""
    grouped = {}
    order = []
    for row in rows:
        name = nb.clean(row.get("name", ""))
        if not name:
            continue
        key = name.casefold()
        if key not in grouped:
            grouped[key] = {
                "name": name,
                "honorific": nb.clean(row.get("honorific", "")),
                "titles": [],
            }
            order.append(key)
        entry = grouped[key]
        if not entry["honorific"]:
            entry["honorific"] = nb.clean(row.get("honorific", ""))
        title = nb.clean(row.get("title", ""))
        if title and title not in entry["titles"]:
            entry["titles"].append(title)
    return [grouped[key] for key in order]


def leader_table(grouped):
    data = []
    for entry in grouped:
        name = entry["name"]
        if entry["honorific"]:
            name = f"{entry['honorific']} {name}"
        titles = "<br>".join(entry["titles"])
        data.append([titles.replace("|", "/"), name.replace("|", "/")])
    if not data:
        return ""
    return tabulate(
        data,
        headers=["Görev", "Ad Soyad"],
        tablefmt="grid",
        colalign=("left", "left"),
        disable_numparse=True,
        maxcolwidths=[50, 32],
    )


def build_body(page, slug, fallback_name):
    groups = []
    for label, rows in leader_groups(page):
        grouped = group_leaders(rows)
        if grouped:
            groups.append((label, grouped))
    if not groups:
        return None

    country_name = nb.clean(page.get("country", "")) or fallback_name
    source = (f"**Kaynak:** [CIA World Leaders — {country_name}]"
              f"({SOURCE.format(slug=slug)})")
    updated = format_updated(page.get("date_updated"))
    if updated:
        source += f" — **Kaynak güncelleme:** {updated}"
    lines = [
        source,
        "",
        "Görev unvanları CIA kaynağındaki özgün İngilizce biçimindedir.",
        "Aynı kişinin birden çok görevi tek satırda gruplanmıştır.",
        "",
    ]
    if page.get("caveat"):
        lines.append(f"> **Kaynak notu:** {nb.clean(page['caveat'])}")
        lines.append("")

    for label, grouped in groups:
        if label:
            lines.append(f"## {label}")
            lines.append("")
        elif len(groups) > 1:
            lines.append("## Merkezi Hükümet")
            lines.append("")
        lines.append(leader_table(grouped))
        lines.append("")

    return "\n".join(lines).strip()


def _used_note_ids():
    """Not kutusundaki tum YAML id'lerini toplar (sabit adli hub'lar dahil)."""
    used = set()
    out = nb.notes_dir()
    if not os.path.isdir(out):
        return used
    for fname in os.listdir(out):
        if not fname.lower().endswith(".md"):
            continue
        info = nb.parse_front_matter(os.path.join(out, fname))
        raw = str(info.get("id", "")).strip()
        if raw.isdigit():
            used.add(int(raw))
    return used


def ensure_global_leaders_page():
    """Kuresel 'Liderler ve Kabine Dizini' notunu bulur, yoksa olusturur."""
    path = nb.find_hub_by_type(GLOBAL_N_TYPE)
    if path:
        return path
    idno = str(nb.fresh_id(_used_note_ids()))
    path = os.path.join(nb.notes_dir(), f"{idno}.md")
    header = nb.build_header(idno, GLOBAL_TITLE, "", date=None, modify=None,
                             n_type=GLOBAL_N_TYPE, keywords="leaders")
    nb.write_note_file(path, header + "\n# Liderler ve Kabine\n")
    print(f"Yazıldı (küresel dizin): {path}")
    return path


def cleanup_legacy_indexes(iso3, country_field, display):
    """Onceki surumun ulke bazli obn dizin leaders sayfalarini kaldirir."""
    obn = nb.find_obn_hub(iso3 or country_field)
    for path in nb.country_note_paths(country_field, display,
                                      ("obn dizin leaders",)):
        if obn:
            nb.remove_link_from_section(obn, SECTION_TITLE, path)
        nb.remove_note(path)
        print(f"Silindi (eski dizin): {path}")


def sync_links(iso3, country_field, display, note_path):
    """Icerik notunu OBN sayfasina ve kuresel lider dizinine baglar."""
    link_title = f"{display} {TITLE_SUFFIX}"
    nb.link_note_to_obn(
        iso3, country_field, display, note_path,
        SECTION_TITLE, link_title,
    )
    global_path = ensure_global_leaders_page()
    nb.update_hub(
        os.path.basename(global_path), GLOBAL_TITLE, link_title,
        note_path, n_type=GLOBAL_N_TYPE, keywords="leaders",
    )
    nb.update_hub(
        nb.OBN_HUB_FILE, nb.OBN_HUB_TITLE, GLOBAL_TITLE, global_path,
        n_type=nb.OBN_HUB_N_TYPE, keywords="obn hub",
    )
    cleanup_legacy_indexes(iso3, country_field, display)
    return global_path


def report_entry(country_field, display):
    found, _ = nb.find_country_files(country_field, display, (N_TYPE,))
    entry = found.get(nb.slugify(f"{display} {TITLE_SUFFIX}"))
    if not entry:
        return None, None, None
    days, source, _raw = nb.note_age(entry["path"])
    return entry, days, source


def report_age_text(title, days, source):
    if days is None:
        return f"{title} (tarih bilgisi yok)."
    verb = "güncellendi" if source == "modify" else "oluşturuldu"
    return f"{title} {nb.human_age(days)} {verb}."


def run():
    flags, positional, slug_override = parse_args(sys.argv[1:])
    arg = " ".join(positional) if positional else "TUR"
    resolved = resolve_country(arg)
    if not resolved:
        print(f"HATA getLeaders: Ülke çözülemedi: {arg}")
        return 1
    iso3, display, country_field = resolved

    if "--delete" in flags:
        rc = nb.delete_country_type(iso3, N_TYPE, KIND_KEY,
                                    country_field, display)
        hub = nb.find_hub_by_type(GLOBAL_N_TYPE)
        if hub:
            nb.prune_hub_links(hub)
        return rc

    title = f"{display} {TITLE_SUFFIX}"
    entry, days, source = report_entry(country_field, display)

    if "--check" in flags:
        if entry:
            fresh = days is not None and days < REPORT_MAX_AGE_DAYS
            print(f"REPORT_EXISTS: {entry['path']}")
            print(f"REPORT_AGE_DAYS: {'' if days is None else days}")
            print(f"REPORT_AGE_SOURCE: {source}")
            print(f"REPORT_FRESH: {1 if fresh else 0}")
            print(f"REPORT_AGE_TEXT: {report_age_text(title, days, source)}")
        return 0

    if "--link-only" in flags:
        if not entry:
            print(f"NODATA: {title} notu yok")
            return 2
        try:
            global_path = sync_links(iso3, country_field, display,
                                     entry["path"])
        except Exception as exc:
            print(f"HATA getLeaders: {type(exc).__name__}: {exc}")
            return 1
        print(f"NOTE: {entry['path']}")
        print(f"GLOBAL: {global_path}")
        return 0

    if (entry and days is not None and days < REPORT_MAX_AGE_DAYS
            and "--force" not in flags):
        print(f"ATLANDI: {report_age_text(title, days, source)} "
              f"({REPORT_MAX_AGE_DAYS} günden yeni; yenilenmedi)")
        try:
            global_path = sync_links(iso3, country_field, display,
                                     entry["path"])
        except Exception as exc:
            print(f"HATA getLeaders: {type(exc).__name__}: {exc}")
            return 1
        print(f"NOTE: {entry['path']}")
        print(f"GLOBAL: {global_path}")
        return 0

    if iso3 not in CIA_COUNTRIES:
        print(f"NODATA: CIA World Leaders bu ülkeyi kapsamıyor: "
              f"{display} ({iso3})")
        return 2

    slug = slug_override or cia_slug(CIA_COUNTRIES[iso3])
    print(f"Ülke: {display} ({iso3}) — CIA: {CIA_COUNTRIES[iso3]} ({slug})")

    page, error = fetch_page(slug)
    if error:
        print(error)
        return 2 if error.startswith("NODATA:") else 1

    body = build_body(page, slug, CIA_COUNTRIES[iso3])
    if not body:
        print(f"NODATA: CIA sayfasında lider listesi yok: {slug}")
        return 2

    source_url = SOURCE.format(slug=slug)
    used = set()
    existing_ids = set()
    try:
        note_path, _ = nb.emit_note(
            display, iso3, title, N_TYPE, body, source_url, country_field,
            used, existing_ids,
            author=SCRIPT_NAME,
            bib_author="Central Intelligence Agency (CIA)",
            bib_howpublished="World Leaders",
        )
        global_path = sync_links(iso3, country_field, display, note_path)
    except Exception as exc:
        print(f"HATA getLeaders: {type(exc).__name__}: {exc}")
        return 1

    print(f"NOTE: {note_path}")
    print(f"GLOBAL: {global_path}")
    return 0


def main():
    try:
        return run()
    except ValueError as exc:
        print(f"HATA getLeaders: {exc}")
        return 1
    except Exception as exc:
        print(f"HATA getLeaders: {type(exc).__name__}: {exc}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
