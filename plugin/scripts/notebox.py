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

import cnlook as lu

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CITATION_STYLE = os.path.join(SCRIPT_DIR, "ieee-with-url.csl")

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
                 n_type="note", keywords=None, bibfile=None, author="dbscript"):
    date = date or dt.datetime.now().strftime("%d/%m/%y")
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
               author="dbscript", bib_author=None, bib_howpublished=None):
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
              used, existing_ids, author="dbscript",
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
        n_types=("indicatorReport",),
        index_n_type="index gosterge",
        hub_file="gosterge-index.md",
        hub_title="Gösterge Raporları Dizini",
        hub_n_type="hub gosterge",
        hub_keywords="gosterge hub",
        hub_h2="World Bank Gösterge Raporu",
    ),
    "ticaret": dict(
        index_suffix="Ticaret Raporları",
        n_types=("singletrade", "bilateraltrade"),
        index_n_type="index ticaret",
        hub_file="ticaret-index.md",
        hub_title="Ticaret Raporları Dizini",
        hub_n_type="hub ticaret",
        hub_keywords="ticaret hub",
        hub_h2="Trademap Ticaret Raporları",
    ),
    "dbwn": dict(
        index_suffix="Dışişleri Bakanlığı Web Notları",
        n_types=("dbwn",),
        index_n_type="dbwn",
        hub_file="dbwn-index.md",
        hub_title="Dışişleri Bakanlığı Web Notları",
        hub_n_type="hub dbwn",
        hub_keywords="dbwn hub",
        hub_h2="Dışişleri Bakanlığı Web Notları",
    ),
    "tbup": dict(
        index_suffix="Ticaret Bakanlığı Ülke Profil Notları",
        n_types=("tbup",),
        index_n_type="index tbup",
        hub_file="tbup-index.md",
        hub_title="Ticaret Bakanlığı Ülke Profilleri",
        hub_n_type="hub tbup",
        hub_keywords="tbup hub",
        hub_h2="Ticaret Bakanlığı Ülke Profil Notları",
    ),
}


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
    """Ulke bazli rapor indeksini yazar/gunceller ve global hub'a ekler.
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
    update_hub(cfg["hub_file"], cfg["hub_title"], title, path,
               n_type=cfg["hub_n_type"], keywords=cfg["hub_keywords"])
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
        if "hub" not in toks:
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
                          n_type=f"hub {iso3.lower()}", author="dbscript")
    writeMdReport(path, header + "\n")
    print(f"Yazıldı (hub oluşturuldu): {path}")
    add_to_general_hub(path, title)
    return path


def update_country_hub(iso3, kind, index_path, index_title,
                       display=None, country_field=None):
    """Ulke hub'indaki (# Otomatik Bilgi Notları > ## <h2>) linki gunceller.
    Hub yoksa (ISO3 varsa ve NOTES_AUTOHUB kapali degilse) minimal hub olusturur.
    Mevcut icerik korunur; yalnizca ilgili alt bolum ve modify: degisir."""
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
    cfg = KIND[kind]
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
    target_rel = os.path.relpath(index_path, os.path.dirname(hub))
    body_before = _upsert_subsection(body_before, "Otomatik Bilgi Notları",
                                     cfg["hub_h2"], index_title, target_rel)
    if body_after and body_before and body_before[-1].strip() != "":
        body_before = body_before + [""]
    out = head + body_before + body_after
    writeMdReport(hub, "\n".join(out).rstrip("\n") + "\n")
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
