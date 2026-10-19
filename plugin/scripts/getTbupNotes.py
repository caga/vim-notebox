#!/home/osman/.vim/plugged/vim-notebox/plugin/scripts/venv/bin/python3
"""
getTbupNotes.py

Convert a (born-digital) PDF country profile into a set of separate Markdown
notes, one note per heading that has its own text, plus a per-country hub note
and a general index hub.

The source may be either an existing PDF path, or a country given by Turkish
name or ISO3 code. When a country is given, its "Ülke Profili" PDF is fetched
from ticaret.gov.tr via getTbupPdf.py and then converted.

Rules:
  * Every heading that has non-blank text directly beneath it (before the next
    heading) becomes its own note, titled with the short heading name.
  * Headings that only contain sub-headings (no own text) produce no note.
  * The "EKLER" chapter and its subtree are skipped entirely.
  * The per-country hub note links the notes (flat list + nested outline).
  * Section notes are reused across runs via their `tbup_key` field.

Output notes use the vault's standard YAML header with:
    n_type: obn tbup        (section/content notes)
    n_type: obn dizin tbup  (the per-country tbup index)
    n_type: hub obn genel   (the global OBN hub, file obn-hub.md)

Two modes (auto-detected):
  * plugin: when `notebox` is importable (vim-notebox), notes go to
    nb.notes_dir(), and the per-country hub is linked into the country hub
    (`n_type: hub {iso3}`) and the general index via notebox helpers.
  * standalone: otherwise notes go to the repository root and a simple general
    index is maintained here.

Usage:
    getTbupNotes.py <pdf|country|iso3> [iso3] [--headings] [--dir DIR]
                    [--refresh] [--download-only] [--yes] [--no-prune]
                    [--check] [--force]

    <pdf|country|iso3>  a PDF path, a Turkish country name, or an ISO3 code
    iso3                optional ISO-3166 alpha-3 code (e.g. nzl)
    --headings          dry run: print the outline and the planned
                        new/updated/orphan notes, without writing anything
    --dir DIR           PDF download folder (default: tbupPdfs, or TBUP_PDF_DIR)
    --refresh           re-scrape the ticaret.gov.tr region/country map
    --download-only     download the PDF for a country and stop
    --yes               auto-confirm deletion of orphan section notes
    --no-prune          never delete orphan section notes
    --check             only report the existing profile's age (no download,
                        no writes); prints REPORT_* lines
    --force             ignore the freshness gate and regenerate

Freshness gate: if the per-country profile index exists and is newer than
NOTES_TBUP_REPORT_MAX_AGE_DAYS (default 30) days, regeneration is skipped
(no PDF download). --headings and --download-only always bypass the gate.
"""

import os
import re
import sys
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pymupdf
import pymupdf4llm

import cnlook as lu
import getTbupPdf

# --- notebox shim: present inside the vim-notebox plugin, absent standalone --
try:
    import notebox as nb
    PLUGIN = True
except Exception:
    nb = None
    PLUGIN = False

if not PLUGIN:
    from helperFunctions import IdGenerator as _standalone_id

# ---------------------------------------------------------------------------
# Configuration / paths
# ---------------------------------------------------------------------------

STANDALONE_OUT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

AUTHOR = os.path.splitext(os.path.basename(sys.argv[0] or ""))[0] or "getTbupNotes"
N_TYPE_NOTE = "obn tbup"           # section (content) notes
N_TYPE_COUNTRY = "obn dizin tbup"  # per-country tbup index
N_TYPE_GLOBAL = "hub obn genel"    # global OBN hub (obn-hub.md)
CITATION_STYLE = "csl/ieee-with-url.csl"

INDEX_FILE = "obn-hub.md"
INDEX_TITLE = "Otomatik Bilgi Notları Dizini"
COUNTRY_H2 = "Ticaret Bakanlığı Ülke Profil Notları"

PUBLISHER = "T.C. Ticaret Bakanlığı"
HOWPUBLISHED = "ticaret.gov.tr, T.C. Ticaret Bakanlığı"

TOC_TITLES = {"icindekiler", "tableofcontents", "contents", "index",
              "listoffigures", "listoftables"}
EXCLUDED_CHAPTER_PREFIX = "ekler"


def notes_dir():
    return nb.notes_dir() if PLUGIN else STANDALONE_OUT


def bib_dir():
    return nb.bib_dir() if PLUGIN else os.path.join(STANDALONE_OUT, "bibfiles")


def gen_id():
    return nb.IdGenerator() if PLUGIN else _standalone_id()


OUT_DIR = notes_dir()
BIB_DIR = bib_dir()


# ---------------------------------------------------------------------------
# Small text helpers
# ---------------------------------------------------------------------------

def norm(s: str) -> str:
    """Aggressively normalise text for comparisons (Turkish-aware)."""
    table = str.maketrans({
        "İ": "i", "I": "i", "ı": "i",
        "Ş": "s", "ş": "s",
        "Ğ": "g", "ğ": "g",
        "Ü": "u", "ü": "u",
        "Ö": "o", "ö": "o",
        "Ç": "c", "ç": "c",
    })
    s = s.translate(table).lower()
    return re.sub(r"[^a-z0-9]", "", s)


def slug(s: str) -> str:
    """Turkish-aware slug (lowercase words joined by '-')."""
    table = str.maketrans({
        "İ": "i", "I": "i", "ı": "i",
        "Ş": "s", "ş": "s",
        "Ğ": "g", "ğ": "g",
        "Ü": "u", "ü": "u",
        "Ö": "o", "ö": "o",
        "Ç": "c", "ç": "c",
    })
    s = clean_heading(s).translate(table).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def clean_heading(text: str) -> str:
    """Clean a raw markdown heading line into a plain short title."""
    text = re.sub(r"<[^>]+>", "", text)      # drop tags like <u>
    text = text.replace("*", "").replace("_", "").replace("\\", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def strip_enum(title: str) -> str:
    """Drop a leading enumerator such as '1. ' or '2) ' from a heading."""
    return re.sub(r"^\s*\d+\s*[\.\)]\s*", "", title).strip()


def yaml_title(title: str) -> str:
    """Render a title as a safely quoted YAML scalar."""
    safe = title.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{safe}"'


# ---------------------------------------------------------------------------
# Markdown structure
# ---------------------------------------------------------------------------

def page_markdown(doc):
    """Return the list of per-page markdown blocks produced by pymupdf4llm."""
    chunks = pymupdf4llm.to_markdown(
        doc,
        page_chunks=True,
        header=False,
        footer=False,
        show_progress=False,
    )
    return [c["text"] for c in chunks]


def flatten_pages(pages_md):
    """Flatten per-page markdown into a single list of {page, text} lines."""
    lines = []
    for pno, md in enumerate(pages_md):
        for text in md.split("\n"):
            lines.append({"page": pno, "text": text})
    return lines


def collect_headings(flat_lines):
    """Return content headings as a tree (dicts) with own-text.

    A heading is {level, title, page, line, own, children, parent}.
    """
    raw = []
    for idx, ln in enumerate(flat_lines):
        match = re.match(r"^(#{1,6})\s+(.*\S)\s*$", ln["text"])
        if not match:
            continue
        title = strip_enum(clean_heading(match.group(2)))
        if not title or norm(title) in TOC_TITLES:
            continue
        raw.append({"level": len(match.group(1)), "title": title,
                    "page": ln["page"], "line": idx})

    if not raw:
        return [], None

    # Drop a lone shallowest heading at the very top (the cover title).
    min_level = min(h["level"] for h in raw)
    if (raw[0]["level"] == min_level
            and sum(1 for h in raw if h["level"] == min_level) == 1):
        raw = raw[1:]
    if not raw:
        return [], None
    chapter_level = min(h["level"] for h in raw)

    roots = []
    stack = []
    for h in raw:
        node = {"level": h["level"], "title": h["title"], "page": h["page"],
                "line": h["line"], "own": [], "children": [], "parent": None}
        while stack and stack[-1]["level"] >= node["level"]:
            stack.pop()
        if stack:
            stack[-1]["children"].append(node)
            node["parent"] = stack[-1]
        else:
            roots.append(node)
        stack.append(node)

    ordered = []
    for root in roots:
        ordered.extend(preorder(root))
    for i, node in enumerate(ordered):
        start = node["line"] + 1
        end = ordered[i + 1]["line"] if i + 1 < len(ordered) else len(flat_lines)
        node["own"] = [ln["text"] for ln in flat_lines[start:end]
                       if ln["text"].strip()]
    return roots, chapter_level


def preorder(node):
    yield node
    for child in node["children"]:
        yield from preorder(child)


def heading_key(node):
    """Stable key for a heading = slug of its chapter+ancestor+title chain."""
    chain = []
    cur = node
    while cur is not None:
        chain.append(cur["title"])
        cur = cur["parent"]
    chain.reverse()
    return "/".join(slug(part) for part in chain)


def chapter_excluded(node):
    root = node
    while root["parent"] is not None:
        root = root["parent"]
    return norm(root["title"]).startswith(EXCLUDED_CHAPTER_PREFIX)


# ---------------------------------------------------------------------------
# YAML headers
# ---------------------------------------------------------------------------

def build_note_header(nid, title, country, bibfile="", tbup_key="", date=None,
                      modify=""):
    date = date or dt.datetime.now().strftime("%d/%m/%Y")
    return (
        "---\n"
        f"id: {nid}\n"
        f"author: {AUTHOR}\n"
        f"title: {yaml_title(title)}\n"
        f"date: {date}\n"
        f"modify: {modify or ''}\n"
        f"country: {country}\n"
        "institude:\n"
        f"n_type: {N_TYPE_NOTE}\n"
        f"tbup_key: {tbup_key}\n"
        "keywords:\n"
        f"bibliography: {bibfile}\n"
        f"citation-style: {CITATION_STYLE}\n"
        'toc-title: "İçindekiler"\n'
        'tableTitle: "Tablo"\n'
        'lotTitle: "Tablolar"\n'
        'reference-section-title: "Kaynakça"\n'
        'figureTitle: "Şekil"\n'
        "colorlinks: true\n"
        "---\n"
    )


def build_country_header(nid, title, country, bibfile="", date=None,
                         modify=""):
    date = date or dt.datetime.now().strftime("%d/%m/%Y")
    return (
        "---\n"
        f"id: {nid}\n"
        f"author: {AUTHOR}\n"
        f"title: {yaml_title(title)}\n"
        f"date: {date}\n"
        f"modify: {modify or ''}\n"
        f"country: {country}\n"
        "institude:\n"
        f"n_type: {N_TYPE_COUNTRY}\n"
        "keywords:\n"
        f"bibliography: {bibfile}\n"
        f"citation-style: {CITATION_STYLE}\n"
        'toc-title: "İçindekiler"\n'
        'tableTitle: "Tablo"\n'
        'lotTitle: "Tablolar"\n'
        'reference-section-title: "Kaynakça"\n'
        'figureTitle: "Şekil"\n'
        "colorlinks: true\n"
        "---\n"
    )


def build_global_header(nid, title, date=None, modify=""):
    date = date or dt.datetime.now().strftime("%d/%m/%Y")
    return (
        "---\n"
        f"id: {nid}\n"
        f"author: {AUTHOR}\n"
        f"title: {yaml_title(title)}\n"
        f"date: {date}\n"
        f"modify: {modify or ''}\n"
        "country:\n"
        "institude:\n"
        f"n_type: {N_TYPE_GLOBAL}\n"
        "keywords:\n"
        "bibliography:\n"
        f"citation-style: {CITATION_STYLE}\n"
        'toc-title: "İçindekiler"\n'
        'tableTitle: "Tablo"\n'
        'lotTitle: "Tablolar"\n'
        'reference-section-title: "Kaynakça"\n'
        'figureTitle: "Şekil"\n'
        "colorlinks: true\n"
        "---\n"
    )


# ---------------------------------------------------------------------------
# Bibliography
# ---------------------------------------------------------------------------

def tr_today():
    months = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
              "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
    now = dt.datetime.now()
    return f"{now.day} {months[now.month - 1]} {now.year}"


def bib_year(*names):
    """Year from a filename/name (last 20xx match), else the current year."""
    for name in names:
        if not name:
            continue
        years = re.findall(r"(20\d{2})", name)
        if years:
            return years[-1]
    return str(dt.datetime.now().year)


def bib_key(iso3, year):
    return f"ticaret-{iso3}-ulkeprofili-{year}"


def bib_entry(key, title, url, year):
    lines = [
        f"@misc{{{key},",
        f"  author = {{{{{PUBLISHER}}}}},",
        f"  title = {{{title}}},",
        f"  howpublished = {{{HOWPUBLISHED}}},",
        f"  year = {{{year}}},",
    ]
    if url:
        lines.append(f"  url = {{{url}}},")
    lines.append(f"  note = {{Erişim tarihi: {tr_today()}}}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def existing_bib_url(path):
    """Return the url already stored in a bibfile, or None."""
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                match = re.search(r"\burl\s*=\s*\{(.*)\}", line)
                if match:
                    return match.group(1).strip()
    except OSError:
        pass
    return None


def write_file(path, content):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def infer_iso3(pdf_path):
    """Best-effort ISO-3 inference from the PDF file name."""
    stem = norm(os.path.splitext(os.path.basename(pdf_path))[0])
    for name, code in zip(lu.countryNames, lu.iso3):
        if len(name) >= 4 and norm(name) in stem:
            return code.lower()
    return None


# ---------------------------------------------------------------------------
# Discovery of previously generated notes (for idempotent re-runs)
# ---------------------------------------------------------------------------

def parse_front_matter(path):
    """Read the leading '---' YAML block into a {key: value} dict."""
    info = {}
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
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


def n_type_tokens(info):
    return [t.lower() for t in (info.get("n_type", "") or "").split()]


def _iter_notes():
    if not os.path.isdir(OUT_DIR):
        return
    for name in os.listdir(OUT_DIR):
        if name.lower().endswith(".md"):
            path = os.path.join(OUT_DIR, name)
            yield path, parse_front_matter(path)


def _int_id(info):
    try:
        return int(info.get("id", "0"))
    except (TypeError, ValueError):
        return 0


def _is_country_tbup(info):
    """A per-country tbup index: n_type has both 'tbup' and 'dizin'."""
    toks = n_type_tokens(info)
    if "tbup" not in toks or "dizin" not in toks:
        return False
    if not (info.get("country", "") or "").strip():
        return False
    return not (info.get("tbup_key", "") or "").strip()


def find_country_tbup(iso3):
    """Return {id, id_int, path, date} of the country's tbup hub, or None."""
    iso = (iso3 or "").lower()
    best = None
    for path, info in _iter_notes():
        if not _is_country_tbup(info):
            continue
        if (info.get("country", "") or "").strip().lower() != iso:
            continue
        idno = _int_id(info)
        if best is None or idno > best["id_int"]:
            best = {"id": info.get("id", ""), "id_int": idno, "path": path,
                    "date": info.get("date", "")}
    return best


def find_section_notes(iso3):
    """Return (by_key, legacy): section notes for the country.

    by_key maps tbup_key -> {id, id_int, path, date} (highest id wins);
    legacy lists older notes without a tbup_key (treated as orphans).
    """
    iso = (iso3 or "").lower()
    by_key = {}
    legacy = []
    for path, info in _iter_notes():
        toks = n_type_tokens(info)
        if "tbup" not in toks:
            continue
        if "dizin" in toks or "hub" in toks:
            continue
        if (info.get("country", "") or "").strip().lower() != iso:
            continue
        rec = {"id": info.get("id", ""), "id_int": _int_id(info), "path": path,
               "date": info.get("date", "")}
        key = (info.get("tbup_key", "") or "").strip()
        if not key:
            legacy.append(rec)
        elif key not in by_key or rec["id_int"] > by_key[key]["id_int"]:
            by_key[key] = rec
    return by_key, legacy


# --- standalone-only general index helpers ---------------------------------

def find_global_index():
    """Return {id, id_int, path, date} of the general tbup index, or None."""
    best = None
    for path, info in _iter_notes():
        toks = n_type_tokens(info)
        is_index = ("hub" in toks and "obn" in toks) \
            or os.path.basename(path) == INDEX_FILE
        if not is_index:
            continue
        idno = _int_id(info)
        if best is None or idno > best["id_int"]:
            best = {"id": info.get("id", ""), "id_int": idno, "path": path,
                    "date": info.get("date", "")}
    return best


def find_country_tbup_all():
    """Return [(title, path)] for every country's tbup hub (standalone)."""
    hubs = []
    for path, info in _iter_notes():
        if not _is_country_tbup(info):
            continue
        title = (info.get("title", "") or "").strip().strip('"')
        if title:
            hubs.append((title, path))
    hubs.sort(key=lambda item: item[0])
    return hubs


# ---------------------------------------------------------------------------
# Argument handling
# ---------------------------------------------------------------------------

def parse_args(argv):
    opts = {"headings": False, "download_only": False, "refresh": False,
            "dir": None, "yes": False, "no_prune": False,
            "check": False, "force": False, "delete": False}
    positional = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--headings":
            opts["headings"] = True
        elif arg == "--download-only":
            opts["download_only"] = True
        elif arg == "--refresh":
            opts["refresh"] = True
        elif arg == "--yes":
            opts["yes"] = True
        elif arg == "--no-prune":
            opts["no_prune"] = True
        elif arg == "--check":
            opts["check"] = True
        elif arg == "--force":
            opts["force"] = True
        elif arg == "--delete":
            opts["delete"] = True
        elif arg == "--dir":
            i += 1
            opts["dir"] = argv[i] if i < len(argv) else None
        elif arg.startswith("--dir="):
            opts["dir"] = arg.split("=", 1)[1]
        elif arg.startswith("--"):
            print(f"Bilinmeyen seçenek: {arg}")
        else:
            positional.append(arg)
        i += 1
    return opts, positional


def resolve_source(source, iso3_arg, opts):
    """Return (pdf_path, iso3, pdf_url, filename).

    Downloads the PDF when a country is given; a local PDF has no URL.
    """
    is_pdf = os.path.isfile(source) and source.lower().endswith(".pdf")
    if is_pdf:
        iso3 = (iso3_arg or infer_iso3(source))
        return source, (iso3.lower() if iso3 else None), None, \
            os.path.basename(source)

    iso3, display, _ = getTbupPdf.resolve_country(source)
    iso3 = (iso3_arg or iso3)
    info = getTbupPdf.download_tbup_pdf_info(source, dest_dir=opts["dir"],
                                             refresh=opts["refresh"])
    if not info:
        return None, (iso3.lower() if iso3 else None), None, None
    return info["path"], (iso3.lower() if iso3 else None), \
        info["url"], info["filename"]


# ---------------------------------------------------------------------------
# Finalize: link the country hub into the vault
# ---------------------------------------------------------------------------

def finalize_plugin(iso3, display, country_field, hub_path, hub_title):
    """Link the per-country tbup index into the country OBN page/vault."""
    nb.update_country_hub(iso3, "tbup", hub_path, hub_title,
                          display=display, country_field=country_field)


def finalize_standalone(hub_path, today, alloc_id):
    """Maintain a simple general index (standalone mode)."""
    rec = find_global_index()
    if rec:
        index_id = rec["id"]
        index_path = rec["path"]
        index_date = rec["date"] or today
        index_modify = today
    else:
        index_id = alloc_id()
        index_path = os.path.join(OUT_DIR, INDEX_FILE)
        index_date = today
        index_modify = ""

    links = [f"- [{title}]({os.path.basename(path)})"
             for title, path in find_country_tbup_all()]
    content = (
        build_global_header(index_id, INDEX_TITLE, index_date, index_modify)
        + "\n"
        + "\n".join(links)
        + "\n"
    )
    write_file(index_path, content)
    print(f"Index hub: {os.path.basename(index_path)} ({len(links)} ülke)")
    return index_path


def prune_orphans(orphans, opts):
    """Report orphan notes and delete them after confirmation."""
    if not orphans:
        return
    print(f"\nKullanılmayan (artık bir başlığa karşılık gelmeyen) notlar: "
          f"{len(orphans)}")
    for rec in orphans:
        print(f"  - {os.path.basename(rec['path'])}")

    if opts.get("no_prune"):
        print("Atlandı (--no-prune).")
        return
    if opts.get("yes"):
        proceed = True
    elif sys.stdin.isatty():
        try:
            ans = input("Bu notlar silinsin mi? [y/N] ").strip().lower()
        except EOFError:
            ans = ""
        proceed = ans in ("y", "yes", "e", "evet")
    else:
        print("Atlandı (onay alınamadı; silmek için --yes kullanın).")
        return

    if not proceed:
        print("Silme iptal edildi.")
        return
    deleted = 0
    for rec in orphans:
        try:
            os.remove(rec["path"])
            deleted += 1
        except OSError as exc:
            print(f"UYARI silinemedi: {rec['path']} ({exc})")
    print(f"{deleted} not silindi.")


# ---------------------------------------------------------------------------
# Outline rendering
# ---------------------------------------------------------------------------

def print_outline(node, depth=1):
    mark = "  " * (depth - 1)
    tag = " *" if node["own"] else ""
    print(f"  {mark}{'#' * depth} {node['title']}{tag}")
    for child in node["children"]:
        print_outline(child, depth + 1)


def render_outline(node, note_id, out, depth=1):
    """Append this node's header (+ note link) then recurse, top-down."""
    lines = [f"{'#' * depth} {node['title']}"]
    nid = note_id.get(id(node))
    if nid is not None:
        lines.append(f"- [{node['title']}]({nid}.md)")
    out.append("\n".join(lines))
    for child in node["children"]:
        render_outline(child, note_id, out, depth + 1)


# ---------------------------------------------------------------------------
# Rapor yas kontrolu (getStmd/getTmd ile ayni mantik, ayri esik)
# ---------------------------------------------------------------------------

TBUP_AGE_ENV = "NOTES_TBUP_REPORT_MAX_AGE_DAYS"


def _tbup_max_age_days():
    try:
        return int(os.environ.get(TBUP_AGE_ENV, "30"))
    except ValueError:
        return 30


def resolve_iso3_offline(source, iso3_arg):
    """Ulke adi/pdf'ten indirme yapmadan iso3 cozer (offline)."""
    is_pdf = os.path.isfile(source) and source.lower().endswith(".pdf")
    if is_pdf:
        iso3 = iso3_arg or infer_iso3(source)
    else:
        iso3, _display, _key = getTbupPdf.resolve_country(source)
        iso3 = iso3_arg or iso3
    return iso3.lower() if iso3 else None


def _age_text(title, days, source):
    if days is None:
        return f"{title} (tarih bilgisi yok)."
    verb = "güncellendi" if source == "modify" else "oluşturuldu"
    human = "bugün" if days <= 0 else f"{days} gün önce"
    return f"{title} {human} {verb}."


def tbup_report_status(source, iso3_arg):
    """(hub, days, source, title) - mevcut per-country tbup index notu."""
    iso3 = resolve_iso3_offline(source, iso3_arg)
    if not iso3:
        return None, None, None, ""
    hub = find_country_tbup(iso3)
    if not hub:
        return None, None, None, ""
    info = parse_front_matter(hub["path"])
    title = re.sub(r"\s+", " ", (info.get("title") or "")
                   .replace("\xa0", " ")).strip().strip('"')
    if not title:
        name = lu.iso3ToName(iso3.upper())
        title = f"{name if name != 1 else iso3.upper()} Ülke Profili"
    raw_mod = (info.get("modify", "") or "").strip()
    raw_date = (info.get("date", "") or "").strip()
    if raw_mod:
        src, raw = "modify", raw_mod
    elif raw_date:
        src, raw = "date", raw_date
    else:
        return hub, None, "none", title
    d = None
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            d = dt.datetime.strptime(raw, fmt).date()
            break
        except ValueError:
            continue
    if d is None:
        return hub, None, "none", title
    return hub, (dt.date.today() - d).days, src, title


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv):
    opts, positional = parse_args(argv)
    if not positional:
        print(__doc__)
        return 1

    iso3_arg = positional[1] if len(positional) > 1 else None
    max_age = _tbup_max_age_days()

    if opts["delete"]:
        if not PLUGIN:
            print("--delete yalnızca eklenti (plugin) modunda desteklenir.")
            return 1
        iso3 = resolve_iso3_offline(positional[0], iso3_arg)
        if not iso3:
            print("ISO-3 kodu çözülemedi.")
            return 1
        name = lu.iso3ToName(iso3.upper())
        return nb.delete_country_type(
            iso3, "obn tbup", "tbup", iso3.lower(),
            name if name != 1 else iso3.upper())

    if opts["check"]:
        hub, days, source, title = tbup_report_status(positional[0], iso3_arg)
        if hub:
            fresh = 1 if (days is not None and days < max_age) else 0
            print(f"REPORT_EXISTS: {hub['path']}")
            print(f"REPORT_AGE_DAYS: {'' if days is None else days}")
            print(f"REPORT_AGE_SOURCE: {source}")
            print(f"REPORT_FRESH: {fresh}")
            print(f"REPORT_AGE_TEXT: {_age_text(title, days, source)}")
        return 0

    if not opts["force"] and not opts["download_only"] and not opts["headings"]:
        hub, days, source, title = tbup_report_status(positional[0], iso3_arg)
        if hub and days is not None and days < max_age:
            print(f"ATLANDI: {_age_text(title, days, source)} "
                  f"({max_age} günden yeni; yenilenmedi)")
            return 0

    pdf_path, iso3, pdf_url, pdf_filename = resolve_source(
        positional[0],
        iso3_arg,
        opts)

    if opts["download_only"]:
        if pdf_path:
            print(f"PDF: {pdf_path}")
            return 0
        return 1

    if not pdf_path:
        print(f"PDF bulunamadı veya indirilemedi: {positional[0]}")
        return 1

    if not iso3:
        print("ISO-3 kodu çözülemedi; açıkça verin: "
              "getTbupNotes.py <pdf|ülke> <iso3>")
        return 1
    country_name = lu.iso3ToName(iso3.upper())
    if country_name == 1:
        print(f"Bilinmeyen ISO-3 kodu: {iso3}")
        return 1
    country_field = iso3.lower()

    doc = pymupdf.open(pdf_path)
    flat_lines = flatten_pages(page_markdown(doc))
    roots, chapter_level = collect_headings(flat_lines)

    if not roots:
        print("Belgede başlık bulunamadı (pymupdf4llm başlık üretmedi).")
        return 1

    print(f"Document : {os.path.basename(pdf_path)}")
    print(f"Country  : {country_name} ({iso3})")
    print(f"Mode     : {'plugin (notebox)' if PLUGIN else 'standalone'}")

    notes = []
    for root in roots:
        if chapter_excluded(root):
            continue
        for node in preorder(root):
            if node["own"]:
                notes.append(node)

    if not notes:
        print("Not üretilecek metin bulunamadı.")
        return 1

    hub_title = f"{country_name} Ülke Profili"
    today = dt.datetime.now().strftime("%d/%m/%Y")

    year = bib_year(pdf_filename, pdf_path)
    key = bib_key(iso3, year)
    bib_title = f"{country_name} Ülke Profili {year}"

    # --- reuse previously generated notes for this country ---------------
    existing_hub = find_country_tbup(iso3)
    by_key, legacy = find_section_notes(iso3)

    used_ids = {rec["id_int"] for rec in list(by_key.values()) + legacy
                if rec["id_int"]}
    counter = [gen_id()]

    def alloc_id():
        nid = counter[0]
        while nid in used_ids or os.path.exists(
                os.path.join(OUT_DIR, f"{nid}.md")):
            nid += 1
        counter[0] = nid + 1
        used_ids.add(nid)
        return nid

    if existing_hub:
        hub_id = existing_hub["id"]
        hub_path = existing_hub["path"]
        hub_date = existing_hub["date"] or today
        hub_modify = today
        used_ids.add(existing_hub["id_int"])
    else:
        hub_id = alloc_id()
        hub_path = os.path.join(OUT_DIR, f"{hub_id}.md")
        hub_date = today
        hub_modify = ""
    bibfile_rel = f"bibfiles/{hub_id}.bib"

    plan = []
    for node in notes:
        nkey = heading_key(node)
        rec = by_key.get(nkey)
        if rec:
            plan.append({"node": node, "key": nkey, "id": rec["id"],
                         "path": rec["path"], "date": rec["date"] or today,
                         "modify": today, "reused": True})
        else:
            nid = alloc_id()
            plan.append({"node": node, "key": nkey, "id": nid,
                         "path": os.path.join(OUT_DIR, f"{nid}.md"),
                         "date": today, "modify": "", "reused": False})

    generated_keys = {p["key"] for p in plan}
    orphans = [rec for k, rec in by_key.items() if k not in generated_keys]
    orphans.extend(legacy)

    # --- dry run ---------------------------------------------------------
    if opts["headings"]:
        print(f"\nOutline ({len(notes)} note(s)):")
        for root in roots:
            if chapter_excluded(root):
                continue
            print_outline(root)
        new_n = sum(1 for p in plan if not p["reused"])
        print(f"\nNotes   : {len(plan)} ({new_n} yeni, "
              f"{len(plan) - new_n} güncellenecek)")
        print(f"Hub     : {'mevcut (id ' + str(hub_id) + ')' if existing_hub else 'yeni'}")
        print(f"Bibfile : {bibfile_rel}")
        if orphans:
            print(f"Orphans : {len(orphans)} (silinebilir)")
            for rec in orphans:
                print(f"  - {os.path.basename(rec['path'])}")
        return 0

    # --- write bibliography ---------------------------------------------
    os.makedirs(BIB_DIR, exist_ok=True)
    bib_path = os.path.join(BIB_DIR, f"{hub_id}.bib")
    write_file(bib_path,
               bib_entry(key, bib_title, pdf_url or existing_bib_url(bib_path),
                         year))

    # --- write section notes --------------------------------------------
    for p in plan:
        node = p["node"]
        content = (
            build_note_header(p["id"], node["title"], country_field,
                              bibfile=bibfile_rel, tbup_key=p["key"],
                              date=p["date"], modify=p["modify"])
            + "\n"
            + "\n".join(node["own"]).strip()
            + f"\n\n@{key}\n"
            + f"\n#BackReferences:\n1- [{hub_title}]({hub_id}.md)\n"
        )
        write_file(p["path"], content)

    # --- write the per-country hub --------------------------------------
    note_id = {id(p["node"]): p["id"] for p in plan}
    hub_body = []
    for root in roots:
        if chapter_excluded(root):
            continue
        render_outline(root, note_id, hub_body)
    note_links = "\n".join(
        f"- [{p['node']['title']}]({os.path.basename(p['path'])})"
        for p in plan)
    hub_content = (
        build_country_header(hub_id, hub_title, country_field,
                             bibfile=bibfile_rel, date=hub_date,
                             modify=hub_modify)
        + "\n"
        + f"# {country_name} Ülke Profil Notları\n\n"
        + note_links
        + "\n\n"
        + "\n\n".join(hub_body).strip()
        + f"\n\n@{key}\n"
        + f"\n#BackReferences:\n1- [{INDEX_TITLE}]({INDEX_FILE})\n"
    )
    write_file(hub_path, hub_content)

    # --- link into the vault --------------------------------------------
    if PLUGIN:
        finalize_plugin(iso3, country_name, country_field, hub_path, hub_title)
    else:
        finalize_standalone(hub_path, today, alloc_id)

    prune_orphans(orphans, opts)

    new_n = sum(1 for p in plan if not p["reused"])
    print(f"\nBibliography: {bibfile_rel}")
    print(f"Hub note : {os.path.basename(hub_path)}  ({hub_title})")
    print(f"Section notes: {len(plan)} ({new_n} yeni, "
          f"{len(plan) - new_n} güncellendi)")
    print(f"INDEX: {hub_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
