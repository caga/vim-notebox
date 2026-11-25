#!/home/osman/.vim/plugged/vim-notebox/plugin/scripts/venv/bin/python3
# -*- coding: utf-8 -*-
"""Ulke icin "<Ulke> Dokumanlari" sayfasi uretir.

Sayfa:
    <Ulke> Dokumanlari
    n_type: obn files

Icerik:
    ## OBN Notlarinda Kullanilan Dokumanlar
                                     (OBN notlarinda kaynak olarak kullanilan
                                     dokumanlar + data/<iso3>/gbn + TBUP PDF)
    ## Ulke Klasoru (data/<iso3>)    (eski/ ve resim klasorleri haric)
    ## Diger Dokumanlar              (data/documents icindeki ulke dokumanlari)

Sayfa ulke hub'ina (n_type: hub <iso3>) "# Otomatik Bilgi Notlari" basligi
altinda, son alt baslik olarak baglanir:

    ## Ulke Dokumanlari
    - [<Ulke> Dokumanlari](<id>.md)

Kullanim:
    ./getObnFiles.py Nepal
    ./getObnFiles.py NPL --box ~/countryNotes
    ./getObnFiles.py Nepal --delete
    ./getObnFiles.py Nepal --delete --dry-run

Secenekler:
    --box DIR     not kutusu (varsayilan: $NOTES_DIR veya cwd)
    --delete      yalnizca bu betigin urettigi obn files sayfalarini ve onlarin
                  hub linkini siler; baska notlara/ Dosyalara dokunmaz
    --dry-run     hicbir sey yazmaz/silmez, yalnizca plani gosterir
    --no-link     sayfayi yazar, ulke hub'ini degistirmez

Guvenlik:
    * Uretim sirasinda hicbir dosya/not silinmez.
    * Ulke hub'inda yalnizca kendi "## Ulke Dokumanlari" blogu eklenir/guncellenir;
      mevcut satirlar korunur.
    * Silme yalnizca --delete ile ve yalnizca author: getObnFiles olan
      obn files sayfalari icin yapilir.
"""

import os
import re
import sys
import tempfile

import _cli

_cli.init()

import notebox as nb

try:
    import getTbupPdf
except Exception:  # pragma: no cover - requests/bs4 yoksa TBUP icin fallback
    getTbupPdf = None


SCRIPT_NAME = "getObnFiles"
N_TYPE = "obn files"
TITLE_SUFFIX = "Dokümanları"
SECTION_USED = "OBN Notlarında Kullanılan Dokümanlar"
SECTION_COUNTRY = "Ülke Klasörü"
SECTION_OTHER = "Diğer Dokümanlar"
SECTION_HUB = "Ülke Dokümanları"
LEGACY_SECTION_HUBS = ("OBN Dokümanları", "Obn Files")

DOC_EXTS = {".doc", ".docx", ".odt", ".rtf"}
PDF_EXTS = {".pdf"}
ALL_EXTS = DOC_EXTS | PDF_EXTS

SKIP_DIRS = {"eski", "img", "imgs", "maps", "sablonlar", ".git", "__pycache__"}

USED_ORDER = ["KOSGEB", "TÜBİTAK", "TÜYSGM", "Diğer Kurumlar", "TBUP"]

LINK_RE = re.compile(r"\[[^\]]*\]\(((?:[^()\n]|\([^()\n]*\))*)\)")
BIB_URL_RE = re.compile(r"^\s*(?:url|file)\s*=\s*\{(.*)\}\s*,?\s*$",
                        re.MULTILINE)
BIB_LOCAL_RE = re.compile(r"local file:\s*([^;\n}]+)")

INST_LABELS = {
    "kosgeb": "KOSGEB",
    "tubitak": "TÜBİTAK",
    "tuysgm": "TÜYSGM",
}


# --------------------------------------------------------------------- helpers

def _notes_root():
    return nb.notes_dir()


def _is_doc(path):
    return os.path.splitext(path)[1].lower() in ALL_EXTS


def _real(path):
    return os.path.realpath(os.path.abspath(path))


def _rel(path):
    return os.path.relpath(path, _notes_root()).replace(os.sep, "/")


def _skip_name(name):
    low = name.lower()
    return (name.startswith("~$") or low.startswith(".~lock")
            or name.endswith("#") or low.endswith(".tmp"))


def _compact(s):
    return re.sub(r"[^a-z0-9]+", "", nb.norm_name(s or ""))


def _yaml_title(s):
    return nb.yaml_title(s or "")


def _md_target(rel):
    if ")" in rel or "<" in rel or ">" in rel:
        return "<" + rel + ">"
    return rel


def _link_line(item):
    return f"- [{item['name']}]({_md_target(item['rel'])})"


def _sort_key(item):
    return (item["name"].lower(), item["rel"].lower())


def _atomic_write(path, content):
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".obnfiles-", suffix=".tmp",
                               dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _split_lines(lines):
    """(head, body_before_backrefs, backrefs) - modify'ye dokunmaz."""
    fm_end = nb._front_matter_end(lines)
    if fm_end < 0:
        head, rest = [], list(lines)
    else:
        head, rest = list(lines[:fm_end + 1]), list(lines[fm_end + 1:])
    for i, line in enumerate(rest):
        if nb.BACKREF_RE.match(line):
            return head, rest[:i], rest[i:]
    return head, rest, []


def _tokens(info):
    return [t.lower() for t in (info.get("n_type", "") or "").split()]


def _country_notes(country_field, display):
    """Ulkeye ait gorunen tum notlar: (path, frontmatter)."""
    root = _notes_root()
    if not os.path.isdir(root):
        return []
    found = []
    for name in sorted(os.listdir(root)):
        if not name.lower().endswith(".md"):
            continue
        path = os.path.join(root, name)
        info = nb.parse_front_matter(path)
        if not info:
            continue
        if nb._country_matches(info, country_field, display):
            found.append((path, info))
    return found


def _generated_pages(country_field, display, quiet=False):
    """Yalnizca bu betigin urettigi obn files sayfalari."""
    pages = []
    for path, info in _country_notes(country_field, display):
        if (info.get("n_type", "") or "").strip() != N_TYPE:
            continue
        author = (info.get("author", "") or "").strip()
        if author not in (SCRIPT_NAME, SCRIPT_NAME + ".py"):
            if not quiet:
                print(f"Atlandı (author: {author or '-'}): {path}")
            continue
        pages.append((path, info))
    pages.sort(key=lambda item: _id_int(item[1].get("id", "0")), reverse=True)
    return pages


def _id_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _resolve_local(target, base):
    target = (target or "").strip()
    if not target:
        return None
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    target = target.split("#", 1)[0].strip()
    if not target:
        return None
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target):
        return None
    if target.startswith("file://"):
        target = target[7:]
    if not os.path.isabs(target):
        target = os.path.join(base, target)
    return os.path.normpath(target)


def _category_for(path, linked=False):
    rel = _rel(path)
    parts = rel.split("/")
    if rel.startswith("data/") and len(parts) >= 4 and parts[2] == "gbn":
        inst = parts[3].lower()
        return INST_LABELS.get(inst, "Diğer Kurumlar")
    if rel.startswith("data/gbns/"):
        return "Diğer Kurumlar"
    if rel.startswith("tbupPdfs/"):
        return "TBUP"
    if linked:
        return "Diğer Kaynaklar"
    return "Ülke Klasörü"


def _add(items, path, section, category, group):
    if not path or not os.path.isfile(path) or not _is_doc(path):
        return
    real = _real(path)
    rel = _rel(real)
    # docs/pdfs are Vim-side exports, not country-source documents.
    if rel.startswith("docs/") or rel.startswith("pdfs/"):
        return
    item = {
        "path": real,
        "rel": rel,
        "name": os.path.basename(real),
        "ext": os.path.splitext(real)[1].lower(),
        "section": section,
        "category": category,
        "group": group,
    }
    item["kind"] = "Word" if item["ext"] in DOC_EXTS else "PDF"
    previous = items.get(real)
    if previous is None:
        items[real] = item
        return
    # A used (kaynak) kaydi, ülke klasörü kaydindan daha degerlidir.
    if section == "used" and previous["section"] != "used":
        previous.update(section="used", category=category, group=group)


# ----------------------------------------------------------------- collectors

def _collect_linked(items, notes):
    root = _notes_root()
    for note_path, info in notes:
        if (info.get("n_type", "") or "").strip() == N_TYPE:
            continue
        toks = set(_tokens(info))
        if not ({"obn", "hub"} & toks):
            continue
        try:
            with open(note_path, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        for target in LINK_RE.findall(text):
            path = _resolve_local(target, root)
            if path and os.path.isfile(path) and _is_doc(path):
                category = _category_for(path, linked=True)
                _add(items, path, "used", category, category)

        bib = (info.get("bibliography", "") or "").strip().strip('"').strip("'")
        if not bib:
            continue
        bib_path = _resolve_local(bib, root)
        if not bib_path or not os.path.isfile(bib_path):
            continue
        try:
            with open(bib_path, encoding="utf-8") as f:
                bib_text = f.read()
        except OSError:
            continue
        for match in BIB_URL_RE.finditer(bib_text):
            value = match.group(1).strip().strip('"').strip("'")
            path = _resolve_local(value, root)
            if path and os.path.isfile(path) and _is_doc(path):
                category = _category_for(path, linked=True)
                _add(items, path, "used", category, category)
        for match in BIB_LOCAL_RE.finditer(bib_text):
            path = _resolve_local(match.group(1).strip(), root)
            if path and os.path.isfile(path) and _is_doc(path):
                category = _category_for(path, linked=True)
                _add(items, path, "used", category, category)


def _collect_country_gbn(items, country_dir):
    gbn = os.path.join(country_dir, "gbn")
    if not os.path.isdir(gbn):
        return
    for root, dirs, files in os.walk(gbn):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if _skip_name(name):
                continue
            path = os.path.join(root, name)
            if _is_doc(path):
                category = _category_for(path, linked=True)
                _add(items, path, "used", category, category)


def _collect_tbup(items, notes, display):
    tbup_dir = os.path.join(_notes_root(), "tbupPdfs")
    if not os.path.isdir(tbup_dir):
        return

    # 1) TBUP hub'inin bib'indeki URL'nin dosya adi ile yerel PDF'i bul.
    for note_path, info in notes:
        if "tbup" not in {t.lower() for t in (info.get("n_type", "") or "").split()}:
            continue
        bib = (info.get("bibliography", "") or "").strip().strip('"').strip("'")
        if not bib:
            continue
        bib_path = _resolve_local(bib, _notes_root())
        if not bib_path or not os.path.isfile(bib_path):
            continue
        try:
            with open(bib_path, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        for match in BIB_URL_RE.finditer(text):
            value = match.group(1).strip().strip('"').strip("'")
            name = os.path.basename(value)
            path = os.path.join(tbup_dir, name)
            if os.path.isfile(path) and _is_doc(path):
                _add(items, path, "used", "TBUP", "TBUP")

    # 2) getTbupPdf'nin bilinen eslestirmesi.
    if getTbupPdf is not None:
        try:
            path = getTbupPdf.find_local_pdf(display, tbup_dir)
        except Exception:
            path = None
        if path and os.path.isfile(path) and _is_doc(path):
            _add(items, path, "used", "TBUP", "TBUP")


def _collect_documents_dir(items, display, iso3):
    docdir = os.path.join(_notes_root(), "data", "documents")
    if not os.path.isdir(docdir):
        return
    keys = {_compact(display)}
    if iso3:
        keys.add((iso3 or "").lower())
    keys.discard("")
    for root, dirs, files in os.walk(docdir):
        dirs[:] = [d for d in dirs if d.lower() != "sablonlar"]
        for name in files:
            path = os.path.join(root, name)
            if _skip_name(name) or not _is_doc(path):
                continue
            compact = _compact(name)
            if any(key in compact for key in keys):
                _add(items, path, "other", SECTION_OTHER, SECTION_OTHER)


def _collect_country_dir(items, country_dir, used):
    if not os.path.isdir(country_dir):
        return
    for root, dirs, files in os.walk(country_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if _skip_name(name):
                continue
            path = os.path.join(root, name)
            if not _is_doc(path):
                continue
            if _real(path) in used:
                continue
            rel_under = os.path.relpath(path, country_dir)
            parts = rel_under.split(os.sep)
            group = parts[0] if len(parts) > 1 else "(kök)"
            _add(items, path, "country", "Ülke Klasörü", group)


# ---------------------------------------------------------------- page writing

def _build_body(display, country_field, items):
    values = list(items.values())
    total = len(values)
    word = sum(1 for item in values if item["ext"] in DOC_EXTS)
    pdf = sum(1 for item in values if item["ext"] in PDF_EXTS)

    lines = [f"# {display} {TITLE_SUFFIX}", ""]
    if total:
        lines += [f"Toplam **{total}** doküman: {word} Word, {pdf} PDF.", ""]
    else:
        lines += ["Doküman bulunamadı.", ""]

    # --- OBN kaynaklari -------------------------------------------------
    lines += [f"## {SECTION_USED}", ""]
    used = [item for item in values if item["section"] == "used"]
    if used:
        lines += ["Bu bölüm, ülkenin OBN notlarında kaynak olarak kullanılan "
                  "dokümanları listeler.", ""]
        for category in USED_ORDER:
            group = sorted([item for item in used
                            if item["category"] == category], key=_sort_key)
            if not group:
                continue
            lines += [f"### {category}", ""]
            lines += [_link_line(item) for item in group]
            lines.append("")
        known = set(USED_ORDER)
        rest = sorted([item for item in used if item["category"] not in known],
                      key=_sort_key)
        if rest:
            lines += ["### Diğer Kaynaklar", ""]
            lines += [_link_line(item) for item in rest]
            lines.append("")
    else:
        lines += ["- Doküman bulunamadı.", ""]

    # --- ulke klasoru ---------------------------------------------------
    country_rel = f"data/{country_field}"
    lines += [f"## {SECTION_COUNTRY} ({country_rel})", ""]
    country = [item for item in values if item["section"] == "country"]
    has_gbn = any(item["rel"].startswith(country_rel + "/gbn/")
                  for item in values if item["section"] == "used")
    if has_gbn:
        lines += ["> `gbn/` kaynakları yukarıdaki bölümde listelendiği için "
                  "burada tekrarlanmaz.", ""]
    if country:
        groups = {}
        for item in country:
            groups.setdefault(item["group"], []).append(item)
        for group_name in sorted(groups,
                                 key=lambda g: (g != "(kök)", g.lower())):
            lines += [f"### {group_name}", ""]
            lines += [_link_line(item) for item in
                      sorted(groups[group_name], key=_sort_key)]
            lines.append("")
    else:
        lines += ["- Doküman bulunamadı.", ""]
    lines += ["> `eski/` arşivi taranmaz.", ""]

    # --- diger dokumanlar -----------------------------------------------
    lines += [f"## {SECTION_OTHER}", ""]
    other = [item for item in values if item["section"] == "other"]
    if other:
        lines += [_link_line(item) for item in sorted(other, key=_sort_key)]
        lines.append("")
    else:
        lines += ["- Doküman bulunamadı.", ""]

    return "\n".join(lines).rstrip() + "\n"


def _backref_tail(page_path, hub, display):
    tail = []
    if os.path.exists(page_path):
        try:
            with open(page_path, encoding="utf-8") as f:
                _, tail = nb.split_backrefs(f.read())
        except OSError:
            tail = []
    if tail:
        return tail
    if not hub:
        return []
    info = nb.parse_front_matter(hub)
    hub_title = nb.clean(info.get("title", "")) or display
    hub_rel = os.path.relpath(hub, os.path.dirname(page_path)).replace(os.sep, "/")
    return ["#BackReferences:", "", f"1- [{hub_title}]({hub_rel})"]


def _write_page(page_path, display, country_field, idno, date, hub):
    items = _collect_all(display, country_field)
    title = f"{display} {TITLE_SUFFIX}"
    modify = nb.today_str() if os.path.exists(page_path) else None
    header = nb.build_header(idno, _yaml_title(title), country_field,
                             date, modify, n_type=N_TYPE, author=SCRIPT_NAME)
    body = _build_body(display, country_field, items)
    tail = _backref_tail(page_path, hub, display)
    content = header + "\n" + body.rstrip("\n") + "\n"
    if tail:
        content += "\n" + "\n".join(tail).strip("\n") + "\n"
    return items, content


def _collect_all(display, country_field):
    items = {}
    notes = _country_notes(country_field, display)
    country_dir = os.path.join(_notes_root(), "data", country_field)

    _collect_linked(items, notes)
    _collect_country_gbn(items, country_dir)
    _collect_tbup(items, notes, display)
    _collect_documents_dir(items, display, country_field)

    used = {path for path, item in items.items() if item["section"] == "used"}
    _collect_country_dir(items, country_dir, used)
    return items


# ---------------------------------------------------------------- hub editing

def _find_hub(iso3, country_field, display):
    if iso3:
        hub = nb.find_country_hub(iso3)
        if hub:
            return hub
    for path, info in _country_notes(country_field, display):
        toks = set(_tokens(info))
        if "hub" in toks and "obn" not in toks:
            return path
    return None


def _find_subsection(before, wrapper_title, sub_title):
    wrapper_re = r"^#(?!#)\s*" + re.escape(wrapper_title) + r"\s*$"
    wrapper_idx = -1
    for i, line in enumerate(before):
        if re.match(wrapper_re, line):
            wrapper_idx = i
            break
    if wrapper_idx < 0:
        return -1, -1, -1
    wrapper_end = len(before)
    for i in range(wrapper_idx + 1, len(before)):
        if nb._is_h1(before[i]):
            wrapper_end = i
            break
    sub_re = r"^##(?!#)\s*" + re.escape(sub_title) + r"\s*$"
    sub_idx = -1
    for i in range(wrapper_idx + 1, wrapper_end):
        if re.match(sub_re, before[i]):
            sub_idx = i
            break
    if sub_idx < 0:
        return wrapper_idx, -1, wrapper_end
    sub_end = wrapper_end
    for i in range(sub_idx + 1, wrapper_end):
        if nb._is_h2(before[i]) or nb._is_h1(before[i]):
            sub_end = i
            break
    return wrapper_idx, sub_idx, sub_end


def _move_subsection_last(before, wrapper_title, sub_title):
    wrapper_idx, sub_idx, sub_end = _find_subsection(before, wrapper_title,
                                                     sub_title)
    if sub_idx < 0 or wrapper_idx < 0:
        return before
    wrapper_end = len(before)
    for i in range(wrapper_idx + 1, len(before)):
        if nb._is_h1(before[i]):
            wrapper_end = i
            break
    if sub_end >= wrapper_end:
        return before

    block = list(before[sub_idx:sub_end])
    del before[sub_idx:sub_end]

    wrapper_end = len(before)
    for i in range(wrapper_idx + 1, len(before)):
        if nb._is_h1(before[i]):
            wrapper_end = i
            break

    while block and block[-1].strip() == "":
        block.pop()
    if wrapper_end > 0 and before[wrapper_end - 1].strip() != "":
        block = [""] + block
    block.append("")
    before[wrapper_end:wrapper_end] = block
    return before


def _tidy_subsection(before, wrapper_title, sub_title):
    """Alt bolumun cevresindeki fazla bos satirlari tek bosluga indirir.
    Bolumun kendi icerigine dokunmaz."""
    _, sub_idx, sub_end = _find_subsection(before, wrapper_title, sub_title)
    if sub_idx < 0:
        return before

    start = sub_idx
    while start > 0 and before[start - 1].strip() == "":
        start -= 1

    prefix = list(before[:start])
    block = list(before[sub_idx:sub_end])
    suffix = list(before[sub_end:])

    while block and block[-1].strip() == "":
        block.pop()
    if prefix:
        prefix.append("")
    block.append("")

    return prefix + block + suffix


def _normalize_block(block):
    """## basligi ile icerik arasinda ve blok sonunda tek bos satir birakir."""
    if not block:
        return block
    content = list(block[1:])
    while content and content[0].strip() == "":
        content.pop(0)
    while content and content[-1].strip() == "":
        content.pop()
    if not content:
        return [block[0], ""]
    return [block[0], ""] + content + [""]


def _migrate_hub_heading(before):
    """Eski hub basliklarini '## Ülke Dokümanları' olarak yeniden adlandirir."""
    wrapper = "Otomatik Bilgi Notları"
    _, new_idx, _ = _find_subsection(before, wrapper, SECTION_HUB)
    if new_idx >= 0:
        return before
    for legacy in LEGACY_SECTION_HUBS:
        _, old_idx, _ = _find_subsection(before, wrapper, legacy)
        if old_idx >= 0:
            before[old_idx] = f"## {SECTION_HUB}"
            break
    return before


def _move_link_last(before, wrapper_title, sub_title, link_basename):
    """Uretilen linki ## Ülke Dokümanları icindeki linklerin sonuncusu yapar."""
    _, sub_idx, sub_end = _find_subsection(before, wrapper_title, sub_title)
    if sub_idx < 0:
        return before

    block = list(before[sub_idx:sub_end])
    target_line = None
    rest = []
    for line in block:
        match = re.search(r"\]\(([^)]+)\)", line)
        if (match
                and os.path.basename(match.group(1).strip().strip("<>"))
                == link_basename):
            target_line = line
        else:
            rest.append(line)
    if target_line is None:
        return before

    insert_at = None
    for i, line in enumerate(rest):
        if re.search(r"\]\(([^)]+)\)", line):
            insert_at = i + 1
    if insert_at is None:
        insert_at = len(rest)
        while insert_at > 0 and rest[insert_at - 1].strip() == "":
            insert_at -= 1
    rest.insert(insert_at, target_line)
    return before[:sub_idx] + _normalize_block(rest) + before[sub_end:]


def _link_hub(hub, page_path, page_title, dry_run=False):
    if not hub:
        print("UYARI: ülke hub'ı yok; sayfa hub'a bağlanmadı")
        return False
    try:
        with open(hub, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError as exc:
        print(f"UYARI: hub okunamadı: {hub} ({exc})")
        return False

    head, before, after = _split_lines(lines)
    original = list(before)
    before = _migrate_hub_heading(before)
    page_rel = os.path.relpath(page_path, os.path.dirname(hub)).replace(os.sep, "/")
    updated = nb._upsert_subsection(list(before), "Otomatik Bilgi Notları",
                                    SECTION_HUB, page_title, page_rel)
    updated = _move_subsection_last(updated, "Otomatik Bilgi Notları",
                                    SECTION_HUB)
    updated = _tidy_subsection(updated, "Otomatik Bilgi Notları", SECTION_HUB)
    updated = _move_link_last(updated, "Otomatik Bilgi Notları", SECTION_HUB,
                              os.path.basename(page_path))
    if updated == original:
        print(f"Değişmedi (hub): {hub}")
        return False

    if after and updated and updated[-1].strip() != "":
        updated = updated + [""]
    if head:
        head = nb._set_fm_modify(head, nb.today_str())
    if not dry_run:
        _atomic_write(hub, "\n".join(head + updated + after).rstrip("\n") + "\n")
        print(f"Güncellendi (hub): {hub}")
    else:
        print(f"Güncellenecek (hub): {hub}")
    return True


def _unlink_hub(hub, removed_paths, dry_run=False):
    if not hub or not removed_paths:
        return False
    try:
        with open(hub, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return False

    head, before, after = _split_lines(lines)
    sub_idx, sub_end = -1, -1
    old_heading = False
    for heading in (SECTION_HUB,) + LEGACY_SECTION_HUBS:
        _, sub_idx, sub_end = _find_subsection(before,
                                               "Otomatik Bilgi Notları",
                                               heading)
        if sub_idx >= 0:
            old_heading = heading != SECTION_HUB
            break
    if sub_idx < 0:
        return False

    removed = {os.path.basename(path) for path in removed_paths}
    block = before[sub_idx:sub_end]
    kept = []
    changed = False
    for line in block:
        match = re.search(r"\]\(([^)]+)\)", line)
        if match:
            target = match.group(1).strip().strip("<>")
            if os.path.basename(target) in removed:
                changed = True
                continue
        kept.append(line)
    if not changed:
        return False

    body = [line for line in kept[1:] if line.strip()]
    if not body:
        before = before[:sub_idx] + before[sub_end:]
    else:
        if old_heading:
            kept[0] = f"## {SECTION_HUB}"
        before = before[:sub_idx] + kept + before[sub_end:]

    if after and before and before[-1].strip() != "":
        before = before + [""]
    if head:
        head = nb._set_fm_modify(head, nb.today_str())
    if not dry_run:
        _atomic_write(hub, "\n".join(head + before + after).rstrip("\n") + "\n")
        print(f"Güncellendi (hub): {hub}")
    else:
        print(f"Güncellenecek (hub): {hub}")
    return True


# ---------------------------------------------------------------------- delete

def delete_country_files(iso3, country_field, display, dry_run=False):
    pages = _generated_pages(country_field, display)
    hub = _find_hub(iso3, country_field, display)

    if not pages:
        print("Silinecek obn files sayfası bulunamadı.")
        return 0

    removed = []
    for path, _info in pages:
        if dry_run:
            print(f"Silinecek: {path}")
        else:
            try:
                os.remove(path)
                print(f"Silindi: {path}")
            except OSError as exc:
                print(f"UYARI silinemedi: {path} ({exc})")
                continue
        removed.append(path)

    if hub and removed:
        _unlink_hub(hub, removed, dry_run)
    return 0


# ------------------------------------------------------------------------ main

def run():
    flags = {arg for arg in sys.argv[1:] if arg.startswith("--")}
    positional = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    arg = " ".join(positional).strip()
    if not arg:
        print("HATA getObnFiles: ülke adı veya ISO3 gerekli")
        return 2

    dry_run = "--dry-run" in flags
    delete = "--delete" in flags
    no_link = "--no-link" in flags

    iso3, display, country_field = nb.resolve_country(arg)
    display = nb.clean(display) or arg
    print(f"Ülke: {display} ({iso3 or '-'})")

    if delete:
        return delete_country_files(iso3, country_field, display, dry_run)

    notes = _notes_root()
    hub = _find_hub(iso3, country_field, display)
    if not hub and not no_link and iso3 and nb.autohub():
        if dry_run:
            print("Oluşturulacak (hub): ülke hub'ı yok")
        else:
            hub = nb._create_country_hub(iso3, country_field, display)
    if not hub:
        print("UYARI: ülke hub'ı bulunamadı; sayfa hub'a bağlanmayacak")

    page_path, info = None, {}
    pages = _generated_pages(country_field, display, quiet=True)
    if pages:
        page_path, info = pages[0]
    if page_path:
        idno = str(info.get("id") or nb.fresh_id())
        date = info.get("date") or None
    else:
        idno = str(nb.fresh_id())
        date = None
        page_path = os.path.join(notes, f"{idno}.md")

    items, content = _write_page(page_path, display, country_field, idno, date,
                                 hub)
    total = len(items)
    word = sum(1 for item in items.values() if item["ext"] in DOC_EXTS)
    pdf = sum(1 for item in items.values() if item["ext"] in PDF_EXTS)
    print(f"Doküman: {total} ({word} Word, {pdf} PDF)")

    if dry_run:
        print(f"Yazılacak: {page_path}")
    else:
        _atomic_write(page_path, content)
        print(f"{'Güncellendi' if info else 'Yazıldı'}: {page_path}")

    if not no_link and hub:
        _link_hub(hub, page_path, f"{display} {TITLE_SUFFIX}", dry_run)

    print(f"FILES: {page_path}")
    if hub:
        print(f"HUB: {hub}")
    return 0


def main():
    try:
        return run()
    except Exception as exc:
        print(f"HATA getObnFiles: {type(exc).__name__}: {exc}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
