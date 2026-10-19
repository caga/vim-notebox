# -*- coding: utf-8 -*-
"""vim-notebox ortak modulu.

Standart not (flat <id>.md) uretimi, basliklar, bibfiles girdileri, ulke/rapor
indeksleri ve ulke hub'larinin (n_type: hub {iso3}) linklenmesi burada toplanir.
getDbn.py, getData.py, getStmd.py ve getTmd.py bu modulu kullanir.

Ortam degiskenleri:
    NOTES_DIR / DBWN_NOTES_DIR : not kutusu (yoksa calisma dizini)
    NOTES_BIB_DIR / DBWN_BIB_DIR : bibfiles dizini (yoksa <notes>/bibfiles)
"""

import datetime as dt
import json
import os
import re
import sys

import cnlook as lu

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CITATION_STYLE = os.path.join(SCRIPT_DIR, "ieee-with-url.csl")

# Rapor tazelik esigi (gun). g:country_report_max_age_days vim'de bu env'e yazilir.
REPORT_MAX_AGE_DAYS = int(os.environ.get("NOTES_REPORT_MAX_AGE_DAYS", "7"))

TR_MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
             "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

STOPWORDS = {
    "federal", "cumhuriyeti", "halk", "demokratik", "devleti", "kralligi",
    "birlesik", "ve",
}

NAME_ALIASES = {
    "ABD": "USA",
    "Amerika": "USA",
    "Amerika Birleşik Devletleri": "USA",
    "İngiltere": "GBR",
    "Britanya": "GBR",
    "Birleşik Krallık": "GBR",
    "BAE": "ARE",
    "Birleşik Arap Emirlikleri": "ARE",
    "Güney Kore": "KOR",
    "Kuzey Kore": "PRK",
    "Türkiye": "TUR",
    "turkiye": "TUR",
    "tur": "TUR",
}


def notes_dir():
    for var in ("NOTES_DIR", "DBWN_NOTES_DIR"):
        val = os.environ.get(var)
        if val:
            return val
    return os.getcwd()


def bib_dir(notes=None):
    notes = notes or notes_dir()
    for var in ("NOTES_BIB_DIR", "DBWN_BIB_DIR"):
        val = os.environ.get(var)
        if val:
            return val
    return os.path.join(notes, "bibfiles")


def today_str():
    return dt.datetime.now().strftime("%d/%m/%y")


def script_name():
    """Ureten betigin adi (uzantisiz). Orn. getDbn.py -> getDbn"""
    return os.path.splitext(os.path.basename(sys.argv[0] or ""))[0] or "notebox"


def autohub():
    """Ulke hub'i yoksa otomatik olusturulsun mu? (NOTES_AUTOHUB=0 ile kapatilir)"""
    return os.environ.get("NOTES_AUTOHUB", "1") != "0"


# ---------------------------------------------------------------- isim/yardimci

def norm_name(s):
    if not s:
        return ""
    s = s.replace("İ", "i").replace("I", "ı").lower()
    for a, b in (("ı", "i"), ("ş", "s"), ("ğ", "g"), ("ü", "u"), ("ö", "o"),
                 ("ç", "c"), ("â", "a"), ("î", "i"), ("û", "u")):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    words = [w for w in s.split() if w not in STOPWORDS]
    return re.sub(r"\s+", " ", " ".join(words)).strip()


def clean(s):
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def slugify(s):
    s = clean(s).replace("İ", "i").replace("I", "ı").lower()
    for a, b in (("ı", "i"), ("ş", "s"), ("ğ", "g"), ("ü", "u"), ("ö", "o"),
                 ("ç", "c"), ("â", "a"), ("î", "i"), ("û", "u")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def strip_parentheses(s):
    return clean(re.sub(r"[()]", " ", s or ""))


def _tr_cap(word):
    first = "İ" if word[:1] == "i" else word[:1].upper()
    return first + word[1:]


def smart_title(s):
    s = clean(s)
    if not s:
        return s
    letters = re.sub(r"[^A-Za-zÇĞİÖŞÜçğıöşü]", "", s)
    if letters and letters.isupper():
        lower = s.replace("İ", "i").replace("I", "ı").lower()
        return " ".join(_tr_cap(w) for w in lower.split())
    return s


def human_format(num):
    magnitude = 0
    while abs(num) >= 1000:
        magnitude += 1
        num /= 1000.0
    return '%.3f%s' % (num, ['', 'K', 'M', 'B', 'T', 'P'][magnitude])


COUNTRY_NAME_INDEX = {}
for _name in lu.countryNames:
    COUNTRY_NAME_INDEX.setdefault(norm_name(_name), []).append(_name)


def resolve_country(arg):
    """Kullanici girdisini (ISO3 veya Turkce ulke adi) cozumler.
    Donus: (iso3 veya None, kanonik isim, YAML country alani)"""
    arg = clean(arg)
    if not arg:
        arg = "TUR"
    up = arg.upper()
    if up in lu.iso3:
        return up, lu.iso3ToName(up), up.lower()
    if arg in lu.countryNames:
        iso3 = lu.name2Iso3(arg)
        if iso3 != 1:
            return iso3, arg, iso3.lower()
        return None, arg, slugify(arg)
    alias = NAME_ALIASES.get(arg)
    if alias is None:
        na = norm_name(arg)
        for k, v in NAME_ALIASES.items():
            if norm_name(k) == na:
                alias = v
                break
    if alias and alias in lu.iso3:
        return alias, lu.iso3ToName(alias), alias.lower()
    na = norm_name(arg)
    cand = COUNTRY_NAME_INDEX.get(na)
    if cand:
        name = min(cand, key=len)
        iso3 = lu.name2Iso3(name)
        if iso3 != 1:
            return iso3, name, iso3.lower()
        return None, name, slugify(name)
    matches = [n for n in lu.countryNames
               if na and (norm_name(n).startswith(na) or na.startswith(norm_name(n)))]
    if len(matches) == 1:
        name = matches[0]
        iso3 = lu.name2Iso3(name)
        if iso3 != 1:
            return iso3, name, iso3.lower()
        return None, name, slugify(name)
    print(f"UYARI cnlook'ta bulunamadı: {arg}; isim doğrudan kullanılacak")
    return None, arg, slugify(arg)


# ------------------------------------------------------------------- id/bib/not

def IdGenerator():
    return int(dt.datetime.now().timestamp())


def date_from_id(idno):
    try:
        return dt.datetime.fromtimestamp(int(idno)).strftime("%d/%m/%y")
    except (TypeError, ValueError):
        return dt.datetime.now().strftime("%d/%m/%y")


def tr_today():
    now = dt.datetime.now()
    return f"{now.day} {TR_MONTHS[now.month - 1]} {now.year}"


def parse_note_date(raw):
    """Not tarihini (%d/%m/%y veya %d/%m/%Y) datetime.date'e cevirir."""
    raw = (raw or "").strip().strip('"')
    for fmt in ("%d/%m/%y", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def note_age(path):
    """(gun, kaynak, tarih_str). modify varsa modify, yoksa date kullanilir.
    Tarih yok/cozulemezse (None, 'none', '')."""
    info = parse_front_matter(path)
    raw_mod = (info.get("modify", "") or "").strip()
    raw_date = (info.get("date", "") or "").strip()
    if raw_mod:
        source, raw = "modify", raw_mod
    elif raw_date:
        source, raw = "date", raw_date
    else:
        return None, "none", ""
    d = parse_note_date(raw)
    if d is None:
        return None, "none", raw
    return (dt.date.today() - d).days, source, raw


def human_age(days):
    if days is None:
        return ""
    if days <= 0:
        return "bugün"
    return f"{days} gün önce"


def bib_path(idno, bibdir=None):
    return os.path.join(bibdir or bib_dir(), f"{idno}.bib")


def bib_key(title, display, iso3):
    base = clean(title)
    prefix = clean(display) + " " if display else ""
    if prefix and base.startswith(prefix):
        base = base[len(prefix):]
    slug = slugify(base).replace("-", "")
    if not slug:
        slug = "kaynak"
    code = (iso3 or "").lower()
    return f"{slug}-{code}" if code else slug


def bib_entry(key, title, url, author, howpublished):
    lines = [
        f"@misc{{{key},",
        f"  author = {{{{{author}}}}},",
        f"  title = {{{title}}},",
        f"  howpublished = {{{howpublished}}},",
        f"  year = {{{dt.datetime.now().year}}},",
    ]
    if url:
        lines.append(f"  url = {{{url}}},")
    lines.append(f"  note = {{Erişim tarihi: {tr_today()}}}")
    lines.append("}")
    return "\n".join(lines) + "\n"


BACKREF_RE = re.compile(r"^\s*#BackReferences\b")


def parse_front_matter(path):
    info = {}
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return info
    if not lines or lines[0].strip() != "---":
        return info
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            key, value = line.split(":", 1)
            info[key.strip()] = value.strip()
    return info


def _front_matter_end(lines):
    if not lines or lines[0].strip() != "---":
        return -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return i
    return -1


def split_backrefs(text):
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if BACKREF_RE.match(line):
            return lines[:i], lines[i:]
    return lines, []


def writeMdReport(file, reportString):
    with open(file, "w", encoding="utf-8") as f:
        f.write(reportString)
    return f"Report File saved as {file}"


def write_note_file(path, content):
    """content'i yazar; mevcut dosyadaki #BackReferences bolumunu ve altini
    koruyup yeni icerigin altina ekler."""
    tail = []
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                _, tail = split_backrefs(f.read())
        except OSError:
            tail = []
    out = content.rstrip("\n")
    if tail:
        out = out + "\n\n" + "\n".join(tail).strip("\n")
    writeMdReport(path, out + "\n")


def build_header(idno, title, country_field, date=None, modify=None,
                 n_type="note", keywords=None, bibfile=None, author=None):
    date = date or dt.datetime.now().strftime("%d/%m/%y")
    author = script_name() if author is None else author
    keywords_line = f"keywords: {keywords}\n" if keywords else "keywords:\n"
    return (
        "---\n"
        f"id: {idno}\n"
        f"author: {author}\n"
        f"title: {title}\n"
        f"date: {date}\n"
        f"modify: {modify or ''}\n"
        f"country: {country_field}\n"
        "institude: \n"
        f"n_type: {n_type}\n"
        + keywords_line +
        f"bibliography: {bibfile or ''}\n"
        f"citation-style: {CITATION_STYLE}\n"
        'toc-title: "İçindekiler"\n'
        'tableTitle: "Tablo"\n'
        'lotTitle: "Tablolar"\n'
        'reference-section-title: "Kaynakça"\n'
        'figureTitle: "Şekil"\n'
        "colorlinks: true\n"
        "---\n"
    )


def write_note(path, idno, title, body, country_field, source_url,
               display, iso3, date=None, modify=None, n_type="note",
               author=None, bib_author=None, bib_howpublished=None):
    """Notu yazar; ayni id ile bibfiles/{id}.bib uretir ve not sonuna
    @key atfini ekler."""
    key = bib_key(title, display, iso3)
    bibdir = bib_dir()
    os.makedirs(bibdir, exist_ok=True)
    with open(bib_path(idno, bibdir), "w", encoding="utf-8") as f:
        f.write(bib_entry(key, title, source_url,
                          bib_author or display or author,
                          bib_howpublished or "vim-notebox"))
    rel_bib = os.path.relpath(bib_path(idno, bibdir),
                              os.path.dirname(path) or notes_dir())
    body = body.rstrip() + f"\n\n@{key}\n"
    write_note_file(path, build_header(idno, title, country_field, date, modify,
                                       n_type=n_type, bibfile=rel_bib,
                                       author=author) + "\n" + body)
    return key


def remove_note(path):
    idno = os.path.splitext(os.path.basename(path))[0]
    for target in (path, bib_path(idno)):
        try:
            if os.path.exists(target):
                os.remove(target)
        except OSError as exc:
            print(f"UYARI silinemedi: {target} ({exc})")


# ------------------------------------------------------------------- kesif

def _id_int(entry):
    try:
        return int(entry["id"])
    except (TypeError, ValueError):
        return 0


def _n_type_tokens(info):
    return [t.lower() for t in (info.get("n_type", "") or "").split()]


def _country_matches(info, country_field, display_name):
    country = info.get("country", "").strip()
    if country:
        if norm_name(country) == norm_name(country_field):
            return True
        if slugify(country) == slugify(country_field):
            return True
        if display_name and slugify(country) == slugify(display_name):
            return True
        return False
    title = info.get("title", "")
    return bool(display_name) and slugify(title).startswith(slugify(display_name))


def find_country_files(country_field, display_name, n_types):
    """Verilen n_type degerlerine ve ulkeye ait .md dosyalarini not kutusu
    kokunde bulur. Donus: ({slug: {"path","id","date","title"}}, duplicates)"""
    if isinstance(n_types, str):
        n_types = (n_types,)
    found = {}
    duplicates = set()
    out = notes_dir()
    if not os.path.isdir(out):
        return found, duplicates
    for fname in os.listdir(out):
        if not fname.lower().endswith(".md"):
            continue
        path = os.path.join(out, fname)
        info = parse_front_matter(path)
        if info.get("n_type") not in n_types:
            continue
        if not _country_matches(info, country_field, display_name):
            continue
        title = clean(info.get("title", ""))
        if not title:
            continue
        entry = {"path": path, "id": info.get("id", ""),
                 "date": info.get("date", ""), "title": title}
        key = slugify(title)
        prev = found.get(key)
        if prev is None:
            found[key] = entry
        else:
            if _id_int(entry) > _id_int(prev):
                duplicates.add(prev["path"])
                found[key] = entry
            else:
                duplicates.add(path)
    return found, duplicates


def country_note_paths(country_field, display_name, n_types):
    """n_type ve ulkeye uyan TUM .md dosyalarinin yollarini doner
    (find_country_files'dan farkli olarak basliga gore tekillemez)."""
    if isinstance(n_types, str):
        n_types = (n_types,)
    out = notes_dir()
    paths = []
    if not os.path.isdir(out):
        return paths
    for fname in os.listdir(out):
        if not fname.lower().endswith(".md"):
            continue
        path = os.path.join(out, fname)
        info = parse_front_matter(path)
        if info.get("n_type") not in n_types:
            continue
        if not _country_matches(info, country_field, display_name):
            continue
        paths.append(path)
    return paths


def unique_id(used, existing_ids, target_dir=None):
    target_dir = target_dir or notes_dir()
    idno = IdGenerator()
    while (idno in used or idno in existing_ids
           or os.path.exists(os.path.join(target_dir, f"{idno}.md"))):
        idno += 1
    used.add(idno)
    return idno


def fresh_id(existing_ids=None):
    """Not kutusu kokunde <id>.md ile cakismayan yeni bir id uretir."""
    used = set(existing_ids or ())
    out = notes_dir()
    idno = IdGenerator()
    while idno in used or os.path.exists(os.path.join(out, f"{idno}.md")):
        idno += 1
    return idno


# ------------------------------------------------------------- not/indeks yazma

def emit_note(display, iso3, title, n_type, body, source_url, country_field,
              used, existing_ids, author=None,
              bib_author=None, bib_howpublished=None):
    """Tek bir rapor notunu id-kararli sekilde yazar/gunceller.
    Donus: (path, title)"""
    found, _ = find_country_files(country_field, display, (n_type,))
    key = slugify(title)
    entry = found.get(key)
    if entry:
        idno = entry["id"]
        path = entry["path"]
        date = entry.get("date") or date_from_id(idno)
        modify = today_str()
    else:
        idno = str(unique_id(used, existing_ids))
        path = os.path.join(notes_dir(), f"{idno}.md")
        date = None
        modify = None
    write_note(path, idno, title, body, country_field, source_url,
               display, iso3, date, modify, n_type=n_type, author=author,
               bib_author=bib_author, bib_howpublished=bib_howpublished)
    print(f"{'Güncellendi' if entry else 'Yazıldı'}: {path}")
    return path, title


KIND = {
    "gosterge": dict(
        index_suffix="Gösterge Raporları",
        n_types=("obn indicatorReport",),
        index_n_type="obn dizin gosterge",
        hub_h2="World Bank Gösterge Raporu",
    ),
    "ticaret": dict(
        index_suffix="Ticaret Raporları",
        n_types=("obn singletrade", "obn bilateraltrade"),
        index_n_type="obn dizin ticaret",
        hub_h2="Trademap Ticaret Raporları",
    ),
    "dbwn": dict(
        index_suffix="Dışişleri Bakanlığı Web Notları",
        n_types=("obn dbwn",),
        index_n_type="obn dizin dbwn",
        hub_h2="Dışişleri Bakanlığı Web Notları",
    ),
    "tbup": dict(
        index_suffix="Ticaret Bakanlığı Ülke Profil Notları",
        n_types=("obn tbup",),
        index_n_type="obn dizin tbup",
        hub_h2="Ticaret Bakanlığı Ülke Profil Notları",
    ),
    "tubitak": dict(
        index_suffix="TÜBİTAK Bilgi Notları",
        n_types=("obn tubitak",),
        index_n_type="obn dizin tubitak",
        hub_h2="TÜBİTAK Bilgi Notları",
    ),
    "kosgeb": dict(
        index_suffix="KOSGEB Bilgi Notları",
        n_types=("obn kosgeb",),
        index_n_type="obn dizin kosgeb",
        hub_h2="KOSGEB Bilgi Notları",
    ),
    "tuysgm": dict(
        index_suffix="TÜYSGM Bilgi Notları",
        n_types=("obn tuysgm",),
        index_n_type="obn dizin tuysgm",
        hub_h2="Teşvik ve Yabancı Sermaye Bilgi Notları",
    ),
    "turkpatent": dict(
        index_suffix="Türk Patent Bilgi Notları",
        n_types=("obn turkpatent",),
        index_n_type="obn dizin turkpatent",
        hub_h2="Türk Patent Bilgi Notları",
    ),
    "tse": dict(
        index_suffix="TSE Bilgi Notları",
        n_types=("obn tse",),
        index_n_type="obn dizin tse",
        hub_h2="Türk Standartları Enstitüsü Bilgi Notları",
    ),
    "mtgm": dict(
        index_suffix="MTGM Bilgi Notları",
        n_types=("obn mtgm",),
        index_n_type="obn dizin mtgm",
        hub_h2="Milli Teknoloji ve Yapay Zeka Genel Müdürlüğü Bilgi Notları",
    ),
    "db": dict(
        index_suffix="Dışişleri Bakanlığı Bilgi Notları",
        n_types=("obn db",),
        index_n_type="obn dizin db",
        hub_h2="Dışişleri Bakanlığı Bilgi Notları",
    ),
    "tb": dict(
        index_suffix="Ticaret Bakanlığı Bilgi Notları",
        n_types=("obn tb",),
        index_n_type="obn dizin tb",
        hub_h2="Ticaret Bakanlığı Bilgi Notları",
    ),
    "tua": dict(
        index_suffix="TUA Bilgi Notları",
        n_types=("obn tua",),
        index_n_type="obn dizin tua",
        hub_h2="Türkiye Uzay Ajansı Bilgi Notları",
    ),
    "tuba": dict(
        index_suffix="TÜBA Bilgi Notları",
        n_types=("obn tuba",),
        index_n_type="obn dizin tuba",
        hub_h2="Türkiye Bilimler Akademisi Bilgi Notları",
    ),
    "sgm": dict(
        index_suffix="Sanayi GM Bilgi Notları",
        n_types=("obn sgm",),
        index_n_type="obn dizin sgm",
        hub_h2="Sanayi Genel Müdürlüğü Bilgi Notları",
    ),
    "sbgm": dict(
        index_suffix="Sanayi Bölgeleri GM Bilgi Notları",
        n_types=("obn sbgm",),
        index_n_type="obn dizin sbgm",
        hub_h2="Sanayi Bölgeleri Genel Müdürlüğü Bilgi Notları",
    ),
    "savgm": dict(
        index_suffix="SAVGM Bilgi Notları",
        n_types=("obn savgm",),
        index_n_type="obn dizin savgm",
        hub_h2="Stratejik Araştırmalar ve Verimlilik Genel Müdürlüğü Bilgi Notları",
    ),
    "atgm": dict(
        index_suffix="ATGM Bilgi Notları",
        n_types=("obn atgm",),
        index_n_type="obn dizin atgm",
        hub_h2="Ar-Ge Teşvikleri Genel Müdürlüğü Bilgi Notları",
    ),
    "kagm": dict(
        index_suffix="KAGM Bilgi Notları",
        n_types=("obn kagm",),
        index_n_type="obn dizin kagm",
        hub_h2="Kalkınma Ajansları Genel Müdürlüğü Bilgi Notları",
    ),
}

# Tum otomatik notlari listeleyen global hub (per-country OBN sayfalarina linkler).
OBN_HUB_FILE = "obn-hub.md"
OBN_HUB_TITLE = "Otomatik Bilgi Notları Dizini"
OBN_HUB_N_TYPE = "hub obn genel"
OBN_SECTION = "Otomatik Bilgi Notları"


def update_hub(hub_file, hub_title, index_title, index_path,
               n_type="hub", keywords=None):
    """Global indeks dosyasini olusturur/gunceller ve ulke indeksinin linkini
    ekler. id/date korunur, modify guncellenir."""
    hub_file = os.path.join(notes_dir(), hub_file)
    rel = os.path.relpath(index_path, os.path.dirname(hub_file))
    target = f"- [{index_title}]({rel})"
    existing = []
    if os.path.exists(hub_file):
        info = parse_front_matter(hub_file)
        idno = info.get("id") or str(fresh_id())
        date = info.get("date") or None
        with open(hub_file, encoding="utf-8") as f:
            lines = f.read().splitlines()
        separators = 0
        for i, line in enumerate(lines):
            if line.strip() == "---":
                separators += 1
                if separators == 2:
                    body_lines = lines[i + 1:]
                    for j, ln in enumerate(body_lines):
                        if BACKREF_RE.match(ln):
                            body_lines = body_lines[:j]
                            break
                    existing = [ln for ln in body_lines if ln.strip()]
                    break
        create = False
    else:
        idno = str(fresh_id())
        date = None
        create = True
    refreshed = []
    replaced = False
    for line in existing:
        match = re.search(r"\]\(([^)]+)\)", line)
        if match and match.group(1) == rel:
            if not replaced:
                refreshed.append(target)
                replaced = True
        else:
            refreshed.append(line)
    if not replaced:
        refreshed.append(target)
    existing = refreshed
    modify = None if create else today_str()
    header = build_header(idno, hub_title, "", date, modify,
                          n_type=n_type, keywords=keywords)
    write_note_file(hub_file, header + "\n" + "\n".join(existing) + "\n")
    print(f"{'Yazıldı' if create else 'Güncellendi'}: {hub_file}")
    return hub_file


def write_country_index(display, iso3, kind, country_field=None,
                        used=None, existing_ids=None):
    """Ulke bazli rapor indeksini yazar/gunceller ve OBN sayfasina baglar.
    Donus: (index_path, index_title)"""
    cfg = KIND[kind]
    country_field = country_field or (iso3.lower() if iso3 else slugify(display))
    used = used if used is not None else set()
    title = f"{display} {cfg['index_suffix']}"
    found, _ = find_country_files(country_field, display, cfg["n_types"])
    links = "\n".join(
        f"- [{e['title']}]({os.path.relpath(e['path'], notes_dir())})"
        for _, e in sorted(found.items(), key=lambda kv: kv[1]["title"])
    )
    idx_found, _ = find_country_files(country_field, display,
                                      (cfg["index_n_type"],))
    entry = idx_found.get(slugify(title))
    if entry:
        idno = entry["id"]
        path = entry["path"]
        date = entry.get("date") or date_from_id(idno)
        modify = today_str()
    else:
        existing_ids = existing_ids or set()
        idno = str(unique_id(used, existing_ids))
        path = os.path.join(notes_dir(), f"{idno}.md")
        date = None
        modify = None
    body = (links + "\n") if links else "\n"
    write_note_file(path, build_header(idno, title, country_field, date, modify,
                                       n_type=cfg["index_n_type"]) + "\n" + body)
    print(f"{'Güncellendi' if entry else 'Yazıldı'}: {path}")
    update_country_hub(iso3, kind, path, title,
                       display=display, country_field=country_field)
    return path, title


def existing_ids_from(found):
    return {int(e["id"]) for e in found.values()
            if str(e["id"]).strip().isdigit()}


# ------------------------------------------------------------- ulke hub linkleri

def find_country_hub(iso3):
    iso = (iso3 or "").lower()
    if not iso:
        return None
    out = notes_dir()
    if not os.path.isdir(out):
        return None
    cands = []
    for fname in os.listdir(out):
        if not fname.lower().endswith(".md"):
            continue
        path = os.path.join(out, fname)
        info = parse_front_matter(path)
        toks = _n_type_tokens(info)
        if "hub" not in toks or "obn" in toks:
            continue
        country = (info.get("country", "") or "").strip().lower()
        if country == iso or iso in toks:
            try:
                idno = int(info.get("id", "0"))
            except (TypeError, ValueError):
                idno = 0
            cands.append((idno, path))
    if not cands:
        return None
    cands.sort(key=lambda x: x[0], reverse=True)
    return cands[0][1]


def find_obn_hub(iso3):
    """Ulkenin 'Otomatik Bilgi Notlari' (n_type: hub obn {iso3}) notunu bulur."""
    iso = (iso3 or "").lower()
    if not iso:
        return None
    out = notes_dir()
    if not os.path.isdir(out):
        return None
    cands = []
    for fname in os.listdir(out):
        if not fname.lower().endswith(".md"):
            continue
        path = os.path.join(out, fname)
        info = parse_front_matter(path)
        toks = _n_type_tokens(info)
        if "obn" not in toks or "hub" not in toks:
            continue
        country = (info.get("country", "") or "").strip().lower()
        if country == iso or iso in toks:
            try:
                idno = int(info.get("id", "0"))
            except (TypeError, ValueError):
                idno = 0
            cands.append((idno, path))
    if not cands:
        return None
    cands.sort(key=lambda x: x[0], reverse=True)
    return cands[0][1]


def find_obn_global_hub():
    """Global OBN hub'ini (n_type: hub obn genel / obn-hub.md) bulur."""
    out = notes_dir()
    if not os.path.isdir(out):
        return None
    for fname in os.listdir(out):
        if not fname.lower().endswith(".md"):
            continue
        if fname == OBN_HUB_FILE:
            return os.path.join(out, fname)
        info = parse_front_matter(os.path.join(out, fname))
        toks = _n_type_tokens(info)
        if "genel" in toks and "hub" in toks and "obn" in toks:
            return os.path.join(out, fname)
    return None


def _is_h1(line):
    return re.match(r"^#(?!#)\s", line) is not None


def _is_h2(line):
    return re.match(r"^##(?!#)\s", line) is not None


def _set_fm_modify(lines, date_str):
    fm_end = _front_matter_end(lines)
    if fm_end < 0:
        return lines
    for i in range(1, fm_end):
        if re.match(r"^modify\s*:", lines[i]):
            lines[i] = f"modify: {date_str}"
            return lines
    insert_at = fm_end
    for i in range(1, fm_end):
        if re.match(r"^date\s*:", lines[i]):
            insert_at = i + 1
            break
    lines.insert(insert_at, f"modify: {date_str}")
    return lines


def _upsert_subsection(before, wrapper_title, sub_title, link_text, target_rel):
    """before (backrefs oncesi satirlar) icinde wrapper > subsection yapisini
    kurar ve tek linki idempotent sekilde yerlestirir."""
    wrapper_re = r"^#(?!#)\s*" + re.escape(wrapper_title) + r"\s*$"
    wrapper_idx = -1
    for i, ln in enumerate(before):
        if re.match(wrapper_re, ln):
            wrapper_idx = i
            break
    if wrapper_idx < 0:
        if before and before[-1].strip() != "":
            before.append("")
        before.append(f"# {wrapper_title}")
        before.append("")
        wrapper_idx = len(before) - 2

    wrapper_end = len(before)
    for i in range(wrapper_idx + 1, len(before)):
        if _is_h1(before[i]):
            wrapper_end = i
            break

    sub_re = r"^##(?!#)\s*" + re.escape(sub_title) + r"\s*$"
    sub_idx = -1
    for i in range(wrapper_idx + 1, wrapper_end):
        if re.match(sub_re, before[i]):
            sub_idx = i
            break

    link_line = f"- [{link_text}]({target_rel})"
    if sub_idx < 0:
        block = []
        if before and before[-1].strip() != "":
            block.append("")
        block += [f"## {sub_title}", "", link_line]
        before[wrapper_end:wrapper_end] = block
        return before

    sub_end = wrapper_end
    for i in range(sub_idx + 1, wrapper_end):
        if _is_h2(before[i]) or _is_h1(before[i]):
            sub_end = i
            break

    block = before[sub_idx + 1:sub_end]
    repl = -1
    for j, ln in enumerate(block):
        m = re.search(r"\]\(([^)]+)\)", ln)
        if m and os.path.basename(m.group(1)) == os.path.basename(target_rel):
            repl = j
            break
    if repl >= 0:
        block[repl] = link_line
    else:
        insert_at = 0
        while insert_at < len(block) and block[insert_at].strip() == "":
            insert_at += 1
        block.insert(insert_at, link_line)
    before[sub_idx + 1:sub_end] = block
    return before


def _note_title(path):
    info = parse_front_matter(path)
    return clean(info.get("title", "")).strip('"')


def _upsert_wrapper_link(before, wrapper_title, link_text, target_rel):
    """before icinde '# wrapper_title' basligini bulur/olusturur ve altina
    tek bir link satiri yerlestirir (varsa diger alt satirlari temizler)."""
    wrapper_re = r"^#(?!#)\s*" + re.escape(wrapper_title) + r"\s*$"
    wrapper_idx = -1
    for i, ln in enumerate(before):
        if re.match(wrapper_re, ln):
            wrapper_idx = i
            break
    if wrapper_idx < 0:
        if before and before[-1].strip() != "":
            before.append("")
        before += [f"# {wrapper_title}", ""]
        wrapper_idx = len(before) - 2
    wrapper_end = len(before)
    for i in range(wrapper_idx + 1, len(before)):
        if _is_h1(before[i]):
            wrapper_end = i
            break
    link_line = f"- [{link_text}]({target_rel})"
    before[wrapper_idx + 1:wrapper_end] = ["", link_line, ""]
    return before


def _upsert_link_under(before, wrapper_title, link_text, target_rel):
    """'# wrapper_title' basligini bulur/olusturur ve altina TEK bir linki
    (varsa diger linkleri koruyarak) idempotent sekilde yerlestirir."""
    wrapper_re = r"^#(?!#)\s*" + re.escape(wrapper_title) + r"\s*$"
    wrapper_idx = -1
    for i, ln in enumerate(before):
        if re.match(wrapper_re, ln):
            wrapper_idx = i
            break
    if wrapper_idx < 0:
        if before and before[-1].strip() != "":
            before.append("")
        before += [f"# {wrapper_title}", ""]
        wrapper_idx = len(before) - 2
    wrapper_end = len(before)
    for i in range(wrapper_idx + 1, len(before)):
        if _is_h1(before[i]):
            wrapper_end = i
            break
    link_line = f"- [{link_text}]({target_rel})"
    base = os.path.basename(target_rel)
    section = before[wrapper_idx + 1:wrapper_end]
    replaced = False
    for j, ln in enumerate(section):
        m = re.search(r"\]\(([^)]+)\)", ln)
        if m and os.path.basename(m.group(1)) == base:
            section[j] = link_line
            replaced = True
            break
    if not replaced:
        while section and section[-1].strip() == "":
            section.pop()
        if not section:
            section = [""]
        section += [link_line, ""]
    before[wrapper_idx + 1:wrapper_end] = section
    return before


def find_general_hub():
    """Genel ulke hub'ini (n_type: ugh / title: Ülkeler Genel Hub) bulur."""
    out = notes_dir()
    if not os.path.isdir(out):
        return None
    for fname in os.listdir(out):
        if not fname.lower().endswith(".md"):
            continue
        path = os.path.join(out, fname)
        info = parse_front_matter(path)
        toks = _n_type_tokens(info)
        if "ugh" in toks or clean(info.get("title", "")) == "Ülkeler Genel Hub":
            return path
    return None


def add_to_general_hub(hub_path, hub_title):
    """Yeni olusturulan ulke hub'ini genel hub'da '# Ülkeler' altindaki
    '## Sorumlu Oldugum Ülkeler' listesine ekler. Mevcut icerik silinmez."""
    general = find_general_hub()
    if not general:
        print("UYARI genel hub (n_type: ugh) bulunamadı; "
              "ülke hub'ı genel hub'a eklenmedi")
        return None
    with open(general, encoding="utf-8") as f:
        lines = f.read().splitlines()
    lines = _set_fm_modify(lines, today_str())
    fm_end = _front_matter_end(lines)
    head = lines[:fm_end + 1]
    rest = lines[fm_end + 1:]
    body_before, body_after = [], []
    for i, ln in enumerate(rest):
        if BACKREF_RE.match(ln):
            body_before = rest[:i]
            body_after = rest[i:]
            break
    else:
        body_before = rest[:]

    target_rel = os.path.relpath(hub_path, os.path.dirname(general))
    link = f"- [{hub_title}]({target_rel})"
    base = os.path.basename(hub_path)

    for ln in body_before:
        m = re.search(r"\]\(([^)]+)\)", ln)
        if m and os.path.basename(m.group(1)) == base:
            return general

    wrap_re = r"^#(?!#)\s*Ülkeler\s*$"
    w = -1
    for i, ln in enumerate(body_before):
        if re.match(wrap_re, ln):
            w = i
            break
    if w < 0:
        print("UYARI genel hub'da '# Ülkeler' başlığı bulunamadı; link eklenmedi")
        return general
    w_end = len(body_before)
    for i in range(w + 1, len(body_before)):
        if _is_h1(body_before[i]):
            w_end = i
            break

    sub_re = r"^##(?!#)\s*Sorumlu Olduğum Ülkeler\s*$"
    s = -1
    for i in range(w + 1, w_end):
        if re.match(sub_re, body_before[i]):
            s = i
            break
    if s < 0:
        insert_at = w_end
    else:
        insert_at = w_end
        for i in range(s + 1, w_end):
            if _is_h2(body_before[i]) or _is_h1(body_before[i]):
                insert_at = i
                break
    while insert_at - 1 > w and body_before[insert_at - 1].strip() == "":
        insert_at -= 1
    body_before.insert(insert_at, link)

    if body_after and body_before and body_before[-1].strip() != "":
        body_before = body_before + [""]
    out = head + body_before + body_after
    writeMdReport(general, "\n".join(out).rstrip("\n") + "\n")
    print(f"Güncellendi (genel hub): {general}")
    return general


def _create_country_hub(iso3, country_field, display):
    """Ulke hub'i yoksa minimal bir tane olusturur. Donus: path."""
    out = notes_dir()
    os.makedirs(out, exist_ok=True)
    country_field = country_field or iso3.lower()
    title = display or (lu.iso3ToName(iso3) if iso3 in lu.iso3 else iso3)
    idno = str(fresh_id())
    path = os.path.join(out, f"{idno}.md")
    header = build_header(idno, title, country_field, date=None, modify=None,
                          n_type=f"hub {iso3.lower()}", author="")
    writeMdReport(path, header + "\n")
    print(f"Yazıldı (hub oluşturuldu): {path}")
    add_to_general_hub(path, title)
    return path


def _build_note_backrefs(note_path, dashboard_path):
    """OBN notu icin dashboard + global OBN hub geri referanslarini uretir."""
    entries = []
    if dashboard_path and os.path.exists(dashboard_path):
        rel = os.path.relpath(dashboard_path, os.path.dirname(note_path))
        entries.append((_note_title(dashboard_path) or "Dashboard", rel))
    entries.append((OBN_HUB_TITLE, OBN_HUB_FILE))
    if not entries:
        return ""
    lines = ["#BackReferences:", ""]
    for i, (title, rel) in enumerate(entries, 1):
        lines.append(f"{i}- [{title}]({rel})")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _create_obn_hub(iso3, country_field, display, dashboard_path, author=None):
    """Ulke icin ayri 'Otomatik Bilgi Notlari' (obn) sayfasi olusturur."""
    out = notes_dir()
    os.makedirs(out, exist_ok=True)
    country_field = country_field or iso3.lower()
    name = (display or (lu.iso3ToName(iso3) if iso3 in lu.iso3 else iso3)
            or iso3).strip()
    title = f"{name} Otomatik Bilgi Notları"
    idno = str(fresh_id())
    path = os.path.join(out, f"{idno}.md")
    header = build_header(idno, title, country_field, date=None, modify=None,
                          n_type=f"hub obn {iso3.lower()}", author=author)
    content = header + "\n# " + OBN_SECTION + "\n"
    backrefs = _build_note_backrefs(path, dashboard_path)
    if backrefs:
        content = content.rstrip("\n") + "\n\n" + backrefs
    writeMdReport(path, content.rstrip("\n") + "\n")
    print(f"Yazıldı (obn oluşturuldu): {path}")
    return path


def _link_index_to_obn_hub():
    """index.md (genel hub) icine '# Otomatik Bilgi Notları' altinda
    obn-hub.md linkini idempotent sekilde yerlestirir."""
    general = find_general_hub()
    if not general:
        print("UYARI genel hub (index.md) bulunamadı; obn-hub linki eklenmedi")
        return None
    with open(general, encoding="utf-8") as f:
        lines = f.read().splitlines()
    lines = _set_fm_modify(lines, today_str())
    fm_end = _front_matter_end(lines)
    head = lines[:fm_end + 1]
    rest = lines[fm_end + 1:]
    body_before, body_after = [], []
    for i, ln in enumerate(rest):
        if BACKREF_RE.match(ln):
            body_before = rest[:i]
            body_after = rest[i:]
            break
    else:
        body_before = rest[:]
    rel = os.path.relpath(os.path.join(notes_dir(), OBN_HUB_FILE),
                          os.path.dirname(general))
    body_before = _upsert_link_under(body_before, OBN_SECTION, OBN_HUB_TITLE, rel)
    if body_after and body_before and body_before[-1].strip() != "":
        body_before = body_before + [""]
    writeMdReport(general, "\n".join(head + body_before + body_after).rstrip("\n") + "\n")
    print(f"Güncellendi (index): {general}")
    return general


def update_country_hub(iso3, kind, index_path, index_title,
                       display=None, country_field=None):
    """Otomatik bilgi notu linkini ulke hub'indan ayri bir OBN notunda
    (n_type: hub obn {iso3}) gunceller; ulke hub'ina yalnizca OBN linki eklenir.
    Hub/OBN yoksa (ISO3 varsa ve NOTES_AUTOHUB kapali degilse) olusturur."""
    display = display or (lu.iso3ToName(iso3) if (iso3 and iso3 in lu.iso3) else iso3)
    country_field = country_field or ((iso3 or "").lower() or slugify(display or ""))
    ident = iso3 or country_field
    hub = find_country_hub(ident)
    if not hub:
        if not iso3:
            print(f"UYARI {display or ident} için ISO3 yok; "
                  "ülke hub'ı oluşturulmadı/bağlanmadı")
            return None
        if not autohub():
            print(f"UYARI {iso3} için ülke hub'ı bulunamadı; hub linki atlandı")
            return None
        hub = _create_country_hub(iso3, country_field, display)

    obn = find_obn_hub(ident)
    if not obn:
        obn = _create_obn_hub(iso3, country_field, display, hub)

    # OBN sayfasini global OBN hub'ina (obn-hub.md) ve index.md'ye kaydet
    obn_title = (_note_title(obn)
                 or f"{clean(display or ident)} Otomatik Bilgi Notları")
    update_hub(OBN_HUB_FILE, OBN_HUB_TITLE, obn_title, obn,
               n_type=OBN_HUB_N_TYPE, keywords="obn hub")
    _link_index_to_obn_hub()

    cfg = KIND[kind]

    # 1) ilgili alt bolumu OBN notuna yaz
    with open(obn, encoding="utf-8") as f:
        lines = f.read().splitlines()
    lines = _set_fm_modify(lines, today_str())
    fm_end = _front_matter_end(lines)
    head = lines[:fm_end + 1]
    rest = lines[fm_end + 1:]
    body_before, body_after = [], []
    for i, ln in enumerate(rest):
        if BACKREF_RE.match(ln):
            body_before = rest[:i]
            body_after = rest[i:]
            break
    else:
        body_before = rest[:]
    target_rel = os.path.relpath(index_path, os.path.dirname(obn))
    body_before = _upsert_subsection(body_before, OBN_SECTION,
                                     cfg["hub_h2"], index_title, target_rel)
    if body_after and body_before and body_before[-1].strip() != "":
        body_before = body_before + [""]
    writeMdReport(obn, "\n".join(head + body_before + body_after).rstrip("\n") + "\n")
    print(f"Güncellendi (obn): {obn}")

    # 2) ulke hub'ina yalnizca OBN linkini yerlestir
    with open(hub, encoding="utf-8") as f:
        lines = f.read().splitlines()
    lines = _set_fm_modify(lines, today_str())
    fm_end = _front_matter_end(lines)
    head = lines[:fm_end + 1]
    rest = lines[fm_end + 1:]
    body_before, body_after = [], []
    for i, ln in enumerate(rest):
        if BACKREF_RE.match(ln):
            body_before = rest[:i]
            body_after = rest[i:]
            break
    else:
        body_before = rest[:]
    obn_rel = os.path.relpath(obn, os.path.dirname(hub))
    link_text = f"{clean(display or ident)} Otomatik Bilgi Notları"
    body_before = _upsert_wrapper_link(body_before, OBN_SECTION,
                                       link_text, obn_rel)
    if body_after and body_before and body_before[-1].strip() != "":
        body_before = body_before + [""]
    writeMdReport(hub, "\n".join(head + body_before + body_after).rstrip("\n") + "\n")
    print(f"Güncellendi (hub): {hub}")
    return hub


MAP_IMG_RE = re.compile(r"^\s*!\[[^\]]*\]\([^)]*data/img/maps/[^)]*\)")


def set_hub_map(hub_path, map_rel, height=350):
    """Ulke hub'inda harita resmini YAML basligindan hemen sonra yerlestirir.
    Varsa eski harita satirini degistirir; diger icerige dokunmaz."""
    with open(hub_path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    fm_end = _front_matter_end(lines)
    if fm_end < 0:
        head, body = [], lines[:]
    else:
        head, body = lines[:fm_end + 1], lines[fm_end + 1:]

    body = [ln for ln in body if not MAP_IMG_RE.match(ln)]
    while body and body[0].strip() == "":
        body.pop(0)
    img = f"![]({map_rel}){{ height={height}px }}"
    body = ["", img, ""] + body
    out = head + body
    writeMdReport(hub_path, "\n".join(out).rstrip("\n") + "\n")
    print(f"Guncellendi (harita): {hub_path}")
    return hub_path


# ------------------------------------------------------------- silme (delete)

def _split_front_back(lines):
    """(head, body_before, body_after). modify bugun olarak guncellenir."""
    lines = _set_fm_modify(lines, today_str())
    fm_end = _front_matter_end(lines)
    head = lines[:fm_end + 1]
    rest = lines[fm_end + 1:]
    body_before, body_after = [], []
    for i, ln in enumerate(rest):
        if BACKREF_RE.match(ln):
            body_before = rest[:i]
            body_after = rest[i:]
            break
    else:
        body_before = rest[:]
    return head, body_before, body_after


def _write_back(path, head, body_before, body_after):
    if body_after and body_before and body_before[-1].strip() != "":
        body_before = body_before + [""]
    writeMdReport(path, "\n".join(head + body_before + body_after).rstrip("\n") + "\n")


def _remove_subsection(before, wrapper_title, sub_title):
    """wrapper altindaki '## sub_title' blogunu kaldirir (upsert tersi)."""
    wrapper_re = r"^#(?!#)\s*" + re.escape(wrapper_title) + r"\s*$"
    wrapper_idx = -1
    for i, ln in enumerate(before):
        if re.match(wrapper_re, ln):
            wrapper_idx = i
            break
    if wrapper_idx < 0:
        return before
    wrapper_end = len(before)
    for i in range(wrapper_idx + 1, len(before)):
        if _is_h1(before[i]):
            wrapper_end = i
            break
    sub_re = r"^##(?!#)\s*" + re.escape(sub_title) + r"\s*$"
    sub_idx = -1
    for i in range(wrapper_idx + 1, wrapper_end):
        if re.match(sub_re, before[i]):
            sub_idx = i
            break
    if sub_idx < 0:
        return before
    sub_end = wrapper_end
    for i in range(sub_idx + 1, wrapper_end):
        if _is_h2(before[i]) or _is_h1(before[i]):
            sub_end = i
            break
    start = sub_idx
    if start > 0 and before[start - 1].strip() == "":
        start -= 1
    del before[start:sub_end]
    return before


def _remove_link_under(before, wrapper_title, target_base):
    """wrapper altindaki, hedef dosyaya isaret eden linki kaldirir."""
    wrapper_re = r"^#(?!#)\s*" + re.escape(wrapper_title) + r"\s*$"
    wrapper_idx = -1
    for i, ln in enumerate(before):
        if re.match(wrapper_re, ln):
            wrapper_idx = i
            break
    if wrapper_idx < 0:
        return before
    wrapper_end = len(before)
    for i in range(wrapper_idx + 1, len(before)):
        if _is_h1(before[i]):
            wrapper_end = i
            break
    out = []
    for i, ln in enumerate(before):
        if wrapper_idx < i < wrapper_end:
            m = re.search(r"\]\(([^)]+)\)", ln)
            if m and os.path.basename(m.group(1)) == target_base:
                continue
        out.append(ln)
    return out


def _remove_index_link(target_base):
    general = find_general_hub()
    if not general:
        return
    with open(general, encoding="utf-8") as f:
        lines = f.read().splitlines()
    head, body_before, body_after = _split_front_back(lines)
    body_before = _remove_link_under(body_before, OBN_SECTION, target_base)
    _write_back(general, head, body_before, body_after)
    print(f"Güncellendi (index): {general}")


def remove_hub_entry(hub_file, target_path):
    """hub dosyasindan target_path linkini kaldirir; hub bos kalirsa siler."""
    hub_path = os.path.join(notes_dir(), hub_file)
    if not os.path.exists(hub_path):
        return None
    with open(hub_path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    head, body_before, body_after = _split_front_back(lines)
    base = os.path.basename(target_path)
    kept = []
    for ln in body_before:
        m = re.search(r"\]\(([^)]+)\)", ln)
        if m and os.path.basename(m.group(1)) == base:
            continue
        kept.append(ln)
    if not any(re.search(r"\]\(([^)]+)\)", ln) for ln in kept):
        remove_note(hub_path)
        print(f"Silindi (boş hub): {hub_path}")
        if hub_file == OBN_HUB_FILE:
            _remove_index_link(os.path.basename(hub_path))
        return None
    _write_back(hub_path, head, kept, body_after)
    print(f"Güncellendi (hub): {hub_path}")
    return hub_path


def _remove_obn_subsection(iso3, kind, country_field, display):
    ident = iso3 or country_field
    obn = find_obn_hub(ident)
    if not obn:
        return
    with open(obn, encoding="utf-8") as f:
        lines = f.read().splitlines()
    head, body_before, body_after = _split_front_back(lines)
    body_before = _remove_subsection(body_before, OBN_SECTION, KIND[kind]["hub_h2"])
    _write_back(obn, head, body_before, body_after)
    print(f"Güncellendi (obn): {obn}")


def _maybe_delete_obn(iso3, country_field, display):
    """OBN sayfasinda hic '##' bolum kalmadiysa sayfayi ve linklerini siler."""
    ident = iso3 or country_field
    obn = find_obn_hub(ident)
    if not obn:
        return
    with open(obn, encoding="utf-8") as f:
        lines = f.read().splitlines()
    _, body_before, _ = _split_front_back(lines)
    if any(_is_h2(ln) for ln in body_before):
        return
    remove_note(obn)
    print(f"Silindi (obn): {obn}")
    remove_hub_entry(OBN_HUB_FILE, obn)
    hub = find_country_hub(ident)
    if hub:
        with open(hub, encoding="utf-8") as f:
            hlines = f.read().splitlines()
        hhead, hbefore, hafter = _split_front_back(hlines)
        hbefore = _remove_link_under(hbefore, OBN_SECTION, os.path.basename(obn))
        _write_back(hub, hhead, hbefore, hafter)
        print(f"Güncellendi (hub): {hub}")


def delete_country_type(iso3, n_type, kind, country_field=None, display=None):
    """Bir betigin urettigi notlari (icerik + indeks + OBN alt bolumu) siler."""
    display = display or (lu.iso3ToName(iso3) if iso3 in lu.iso3 else iso3)
    country_field = country_field or (iso3.lower() if iso3 else slugify(display))
    cfg = KIND[kind]
    for path in country_note_paths(country_field, display, (n_type,)):
        remove_note(path)
        print(f"Silindi: {path}")
    idx_paths = country_note_paths(country_field, display, (cfg["index_n_type"],))
    if idx_paths:
        remaining = country_note_paths(country_field, display, cfg["n_types"])
        if remaining:
            ids = set()
            for p in remaining:
                info = parse_front_matter(p)
                if str(info.get("id", "")).strip().isdigit():
                    ids.add(int(info["id"]))
            write_country_index(display, iso3, kind, country_field, set(), ids)
        else:
            for path in idx_paths:
                remove_note(path)
                print(f"Silindi: {path}")
            _remove_obn_subsection(iso3, kind, country_field, display)
            _maybe_delete_obn(iso3, country_field, display)
    else:
        _maybe_delete_obn(iso3, country_field, display)
    return 0


def delete_country_obn(iso3, country_field=None, display=None):
    """Ulkenin tum otomatik bilgi notlarini ve OBN sayfasini siler.
    Ulke hub'i (dashboard), index.md ve harita korunur."""
    display = display or (lu.iso3ToName(iso3) if iso3 in lu.iso3 else iso3)
    country_field = country_field or (iso3.lower() if iso3 else slugify(display))
    for kind, cfg in KIND.items():
        for path in country_note_paths(country_field, display, cfg["n_types"]):
            remove_note(path)
            print(f"Silindi: {path}")
        for path in country_note_paths(country_field, display,
                                       (cfg["index_n_type"],)):
            remove_note(path)
            print(f"Silindi: {path}")
    ident = iso3 or country_field
    obn = find_obn_hub(ident)
    if obn:
        remove_note(obn)
        print(f"Silindi (obn): {obn}")
        remove_hub_entry(OBN_HUB_FILE, obn)
        hub = find_country_hub(ident)
        if hub:
            with open(hub, encoding="utf-8") as f:
                hlines = f.read().splitlines()
            hhead, hbefore, hafter = _split_front_back(hlines)
            hbefore = _remove_link_under(hbefore, OBN_SECTION, os.path.basename(obn))
            _write_back(hub, hhead, hbefore, hafter)
            print(f"Güncellendi (hub): {hub}")
    return 0
