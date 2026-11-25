#!/home/osman/.vim/plugged/vim-notebox/plugin/scripts/venv/bin/python3
"""
getTuysgmNotes.py

Convert local TUYSGM (Teşvik Uygulama ve Yabancı Sermaye Genel Müdürlüğü)
"Bilgi Notu" documents, sent for a country, into a set of separate Markdown
notes: one note per section heading that has its own text, plus a per-country
hub note linking them and the source file(s).

Source documents are read from the vault (note box) folder:

    data/{iso3}/gbn/tuysgm/*.doc   (legacy binary Word)
    data/{iso3}/gbn/tuysgm/*.docx

Because these are legacy .doc files (and PyMuPDF/pandoc cannot read them), each
source is converted to HTML with LibreOffice headless and then parsed with
BeautifulSoup:
  * section headings are fully-bold, short paragraphs (skipping the ministry
    cover page and table captions);
  * list paragraphs become Markdown bullets;
  * data tables become Markdown pipe tables (the outer LibreOffice layout
    table is descended into, not rendered).

Output notes use the vault's standard YAML header with:
    n_type: obn tuysgm        (section/content notes)
    n_type: obn dizin tuysgm  (the per-country tuysgm index)
    n_type: hub obn genel     (the global OBN hub, file obn-hub.md)

Two modes (auto-detected):
  * plugin: when `notebox` is importable (vim-notebox), notes go to
    nb.notes_dir(), and the per-country hub is linked into the country hub
    (`n_type: hub {iso3}`) and the general index via notebox helpers.
  * standalone: otherwise notes go to the repository root and a simple general
    index is maintained here.

Usage:
    ./getTuysgmNotes.py <iso3|country> [--dir DIR] [--box DIR] [--headings]
                        [--yes] [--no-prune] [--check] [--force] [--delete]

    <iso3|country>  an ISO-3166 alpha-3 code (folder name) or a country name
    --box DIR       note box (default: $NOTES_DIR or cwd)
    --dir DIR       read documents from DIR instead of data/{iso3}/gbn/tuysgm
    --headings      dry run: print the outline and the planned new/updated/
                    orphan notes, without writing anything
    --yes           auto-confirm deletion of orphan section notes
    --no-prune      never delete orphan section notes
    --check         only report the existing profile's age (no writes);
                    prints REPORT_* lines
    --force         ignore the freshness gate and regenerate
    --delete        delete all generated notes for the country (plugin only)

Freshness gate: if the per-country hub exists and is newer than
NOTES_TUYSGM_REPORT_MAX_AGE_DAYS (default 30) days, regeneration is skipped.
--headings always bypasses the gate.

Requires LibreOffice (`soffice`) on PATH for the .doc -> HTML conversion.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import datetime as dt

import _cli

_cli.init()

from bs4 import BeautifulSoup, NavigableString

import cnlook as lu

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

AUTHOR = os.path.splitext(os.path.basename(sys.argv[0] or ""))[0] or "getTuysgmNotes"
INSTITUDE = "tuysgm"
N_TYPE_NOTE = "obn tuysgm"            # section (content) notes
N_TYPE_COUNTRY = "obn dizin tuysgm"   # per-country tuysgm index
N_TYPE_GLOBAL = "hub obn genel"       # global OBN hub (obn-hub.md)
CITATION_STYLE = "csl/ieee-with-url.csl"

INDEX_FILE = "obn-hub.md"
INDEX_TITLE = "Otomatik Bilgi Notları Dizini"

PUBLISHER = "T.C. Sanayi ve Teknoloji Bakanlığı, Teşvik Uygulama ve Yabancı Sermaye Genel Müdürlüğü"
HOWPUBLISHED = "TÜYSGM Bilgi Notu"
BIB_LABEL = "tuysgm"

NO_DATA_CODE = 2
MAX_HEADING_LEN = 100
SOFFICE = os.environ.get("SOFFICE_BIN", "soffice")

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

_TR_MONTHS = ("ocak", "subat", "mart", "nisan", "mayis", "haziran",
              "temmuz", "agustos", "eylul", "ekim", "kasim", "aralik")

_TR_FOLD = str.maketrans({
    "İ": "i", "I": "i", "ı": "i",
    "Ş": "s", "ş": "s",
    "Ğ": "g", "ğ": "g",
    "Ü": "u", "ü": "u",
    "Ö": "o", "ö": "o",
    "Ç": "c", "ç": "c",
})


def notes_dir():
    return nb.notes_dir() if PLUGIN else STANDALONE_OUT


def bib_dir():
    return nb.bib_dir() if PLUGIN else os.path.join(STANDALONE_OUT, "bibfiles")


def gen_id():
    return nb.IdGenerator() if PLUGIN else _standalone_id()


OUT_DIR = notes_dir()
BIB_DIR = bib_dir()


def data_subdir(iso3, override=None):
    """Document folder for a country: data/{iso3}/gbn/tuysgm (or override)."""
    if override:
        return override
    return os.path.join(OUT_DIR, "data", iso3.lower(), "gbn", "tuysgm")


# ---------------------------------------------------------------------------
# Small text helpers
# ---------------------------------------------------------------------------

def clean(text):
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def norm(s):
    """Aggressively normalise text for comparisons (Turkish-aware)."""
    return re.sub(r"[^a-z0-9]", "", (s or "").translate(_TR_FOLD).lower())


def norm_name(s):
    return norm(s)


def slug(s):
    """Turkish-aware slug (lowercase words joined by '-')."""
    s = clean(s).translate(_TR_FOLD).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def yaml_title(title):
    safe = title.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{safe}"'


# ---------------------------------------------------------------------------
# Country resolution
# ---------------------------------------------------------------------------

def resolve_country(arg):
    """Resolve user input to (iso3_lower or None, display name)."""
    arg = clean(arg)
    if not arg:
        return None, ""
    up = arg.upper()
    if up in lu.iso3:
        return up.lower(), lu.iso3ToName(up)
    if arg in lu.countryNames:
        iso3 = lu.name2Iso3(arg)
        if iso3 != 1:
            return iso3.lower(), arg
    na = norm_name(arg)
    for key, code in ALIASES.items():
        if norm_name(key) == na and code in lu.iso3:
            return code.lower(), lu.iso3ToName(code)
    if re.fullmatch(r"[A-Za-z]{3}", arg):
        name = lu.iso3ToName(arg.upper())
        if name != 1:
            return arg.lower(), name
    return None, arg


# ---------------------------------------------------------------------------
# LibreOffice conversion + HTML parsing
# ---------------------------------------------------------------------------

def convert_to_html(path, workdir):
    """Convert a .doc/.docx to HTML with LibreOffice. Return path or None."""
    profile = os.path.join(workdir, "lo-profile")
    cmd = [
        SOFFICE, "--headless", "--norestore",
        f"-env:UserInstallation=file://{profile}",
        "--convert-to", "html", "--outdir", workdir, path,
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=180, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"UYARI dönüştürülemedi: {os.path.basename(path)} ({exc})")
        return None
    html_path = os.path.join(
        workdir, os.path.splitext(os.path.basename(path))[0] + ".html")
    return html_path if os.path.exists(html_path) else None


def _is_doc_title(text):
    stripped = (text or "").strip()
    n = norm(stripped)
    return (stripped == stripped.upper()
            and "yatirim" in n and "iliskileri" in n)


def _is_cover(text):
    n = norm(text)
    if not n:
        return False
    if n in {"tc", "konu", "bilginotu"}:
        return True
    if "sanayiveteknoloji" in n or "tesvikuygulama" in n \
            or "genelmudurlugu" in n:
        return True
    if _is_doc_title(text):
        return True
    for month in _TR_MONTHS:
        if re.fullmatch(month + r"20\d{2}", n):
            return True
    return False


def strip_enum(title):
    """Drop a leading bullet or enumerator ('1. ', '2) ', 'a. ') from a heading."""
    title = re.sub(r"^\s*[•·▪◦\-\u2013\u2014]\s*", "", title)
    return re.sub(r"^\s*(?:\d+|[a-zA-ZçğıöşüÇĞİÖŞÜ])\s*[\.\)]\s*", "",
                  title).strip()


def _is_caption(text):
    n = norm(text)
    return n.startswith(("tablo", "sekil", "grafik"))


def _anc_bold(node, stop):
    for anc in node.parents:
        if anc is stop:
            break
        if anc.name in ("b", "strong"):
            return True
        style = (anc.get("style") or "").replace(" ", "").lower()
        if anc.name in ("font", "span") and "font-weight" in style \
                and "normal" not in style:
            return True
    return False


def _par_all_bold(par):
    total = 0
    bold = 0
    for node in par.descendants:
        if isinstance(node, NavigableString):
            text = str(node)
            if not text.strip():
                continue
            total += len(text)
            if _anc_bold(node, par):
                bold += len(text)
    return total > 0 and bold == total


def _is_data_table(tbl):
    rows = tbl.find_all("tr", recursive=False) or tbl.find_all("tr")
    if len(rows) < 2:
        return False
    cols = [len(tr.find_all(["td", "th"], recursive=False)) for tr in rows]
    if (max(cols) if cols else 0) < 2:
        return False
    cells = tbl.find_all(["td", "th"])
    if not cells:
        return False
    avg = sum(len(clean(c.get_text(" ", strip=True))) for c in cells) / len(cells)
    return avg <= 60


def _render_table(tbl):
    rows = []
    for tr in tbl.find_all("tr", recursive=False):
        cells = [clean(td.get_text(" ", strip=True)).replace("|", "\\|")
                 for td in tr.find_all(["td", "th"], recursive=False)]
        if cells:
            rows.append(cells)
    if not rows:
        return ""
    ncols = max(len(r) for r in rows)
    rows = [r + [""] * (ncols - len(r)) for r in rows]
    head = "| " + " | ".join(rows[0]) + " |"
    sep = "| " + " | ".join(["---"] * ncols) + " |"
    body = ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join([head, sep] + body)


def read_html(path):
    """Return a list of blocks {kind:'p'|'table', text, bold, list}."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        soup = BeautifulSoup(fh.read(), "html.parser")
    blocks = []

    def walk(el, in_list=False):
        for child in el.children:
            name = getattr(child, "name", None)
            if name is None:
                continue
            if name == "table":
                if _is_data_table(child):
                    blocks.append({"kind": "table",
                                   "text": _render_table(child)})
                else:
                    walk(child, in_list)
            elif name in ("p", "h1", "h2", "h3", "h4", "h5", "h6"):
                text = clean(child.get_text(" ", strip=True))
                if text:
                    blocks.append({"kind": "p", "text": text,
                                   "bold": _par_all_bold(child),
                                   "list": in_list})
            elif name in ("ol", "ul"):
                walk(child, True)
            elif name == "li":
                walk(child, True)
            else:
                walk(child, in_list)

    walk(soup.body or soup)
    return blocks


def _heading_candidates(blocks):
    idx = []
    for i, b in enumerate(blocks):
        if b["kind"] != "p" or not b["bold"]:
            continue
        text = b["text"]
        if len(text) > MAX_HEADING_LEN:
            continue
        if _is_cover(text) or _is_caption(text):
            continue
        idx.append(i)
    return idx


def collect_sections(blocks):
    """Return (subject, sections).

    sections : list of {title, blocks(list)} where blocks are the body blocks.
    Duplicate headings coming from the cover outline are dropped when an
    identical heading with its own text appears later.
    """
    hidx = _heading_candidates(blocks)
    if not hidx:
        return _subject(blocks), []

    def own_empty(pos):
        j = hidx.index(pos)
        end = hidx[j + 1] if j + 1 < len(hidx) else len(blocks)
        return not blocks[pos + 1:end]

    titles = [norm(blocks[i]["text"]) for i in hidx]
    keep = []
    for j, pos in enumerate(hidx):
        if own_empty(pos) and titles[j] in titles[j + 1:]:
            continue
        keep.append(pos)

    sections = []
    for j, pos in enumerate(keep):
        end = keep[j + 1] if j + 1 < len(keep) else len(blocks)
        sections.append({"title": strip_enum(clean(blocks[pos]["text"])),
                         "blocks": blocks[pos + 1:end]})
    return _subject(blocks), sections


def _subject(blocks):
    for b in blocks:
        if b["kind"] == "p" and b["bold"] and _is_doc_title(b["text"]):
            return clean(b["text"])
    return ""


def render_body(blocks):
    """Render body blocks as Markdown (bullets + pipe tables)."""
    out = []
    bullets = []
    for b in blocks:
        if b["kind"] == "table":
            if bullets:
                out.append("\n".join(bullets))
                bullets = []
            if b["text"]:
                out.append(b["text"])
        else:
            text = clean(b["text"])
            if not text:
                continue
            if b.get("list") and not b.get("bold"):
                bullets.append("- " + text)
            else:
                if bullets:
                    out.append("\n".join(bullets))
                    bullets = []
                out.append(text)
    if bullets:
        out.append("\n".join(bullets))
    return "\n\n".join(out)


# ---------------------------------------------------------------------------
# YAML headers
# ---------------------------------------------------------------------------

def _fallback_header(nid, title, country, date, modify, n_type,
                     bibfile="", extra=(), lof=False, compact_empty=False,
                     institude=None):
    """Header renderer for standalone installs without notebox.py."""
    date = date or dt.datetime.now().strftime("%d/%m/%Y")
    inst_line = f"institude: {institude}" if institude else "institude:"
    lines = [
        "---",
        f"id: {nid}",
        f"author: {AUTHOR}",
        f"title: {yaml_title(title)}",
        f"date: {date}",
        f"modify: {modify or ''}",
        "country:" if (compact_empty and not country) else f"country: {country}",
        inst_line,
        f"n_type: {n_type}",
    ]
    for key, value in extra:
        lines.append(f"{key}: {value}")
    lines.append("keywords:")
    lines.append("bibliography:" if (compact_empty and not bibfile)
                 else f"bibliography: {bibfile}")
    lines.append(f"citation-style: {CITATION_STYLE}")
    lines += ['toc-title: "İçindekiler"', 'tableTitle: "Tablo"',
              'lotTitle: "Tablolar"']
    if lof:
        lines.append('lofTitle: "Şekiller"')
    lines += ['reference-section-title: "Kaynakça"', 'figureTitle: "Şekil"',
              "colorlinks: true", "---"]
    return "\n".join(lines) + "\n"


def build_note_header(nid, title, country, bibfile="", tuysgm_key="", date=None,
                      modify=""):
    if PLUGIN:
        return nb.build_header(
            nid, yaml_title(title), country, date, modify,
            n_type=N_TYPE_NOTE, bibfile=bibfile, author=AUTHOR,
            date_fmt="%d/%m/%Y", citation_style=CITATION_STYLE,
            institude=INSTITUDE, extra_fields=(("tuysgm_key", tuysgm_key),),
        )
    return _fallback_header(nid, title, country, date, modify, N_TYPE_NOTE,
                            bibfile=bibfile,
                            extra=(("tuysgm_key", tuysgm_key),),
                            institude=INSTITUDE)


def build_country_header(nid, title, country, bibfile="", date=None,
                         modify=""):
    if PLUGIN:
        return nb.build_header(
            nid, yaml_title(title), country, date, modify,
            n_type=N_TYPE_COUNTRY, bibfile=bibfile, author=AUTHOR,
            date_fmt="%d/%m/%Y", citation_style=CITATION_STYLE,
            institude=INSTITUDE,
        )
    return _fallback_header(nid, title, country, date, modify, N_TYPE_COUNTRY,
                            bibfile=bibfile, institude=INSTITUDE)


def build_global_header(nid, title, date=None, modify=""):
    if PLUGIN:
        return nb.build_header(
            nid, yaml_title(title), "", date, modify,
            n_type=N_TYPE_GLOBAL, author=AUTHOR,
            date_fmt="%d/%m/%Y", citation_style=CITATION_STYLE,
            institude="", compact_empty=True,
        )
    return _fallback_header(nid, title, "", date, modify, N_TYPE_GLOBAL,
                            compact_empty=True, institude="")


# ---------------------------------------------------------------------------
# Bibliography
# ---------------------------------------------------------------------------

def bib_year(*names):
    for name in names:
        if not name:
            continue
        years = re.findall(r"(20\d{2})", name)
        if years:
            return years[-1]
    return str(dt.datetime.now().year)


def tr_today():
    months = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
              "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
    now = dt.datetime.now()
    return f"{now.day} {months[now.month - 1]} {now.year}"


def bib_key(iso3, doc_slug, year):
    return f"{BIB_LABEL}-{iso3}-{doc_slug}-{year}"


def bib_entry(key, title, rel_path, year):
    lines = [
        f"@misc{{{key},",
        f"  author = {{{{{PUBLISHER}}}}},",
        f"  title = {{{title}}},",
        f"  howpublished = {{{HOWPUBLISHED}}},",
        f"  year = {{{year}}},",
        f"  note = {{local file: {rel_path}; Erişim tarihi: {tr_today()}}}",
        "}",
    ]
    return "\n".join(lines) + "\n"


def write_file(path, content):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


# ---------------------------------------------------------------------------
# Discovery of previously generated notes (for idempotent re-runs)
# ---------------------------------------------------------------------------

def parse_front_matter(path):
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


def _is_country_tuysgm(info):
    toks = n_type_tokens(info)
    if "tuysgm" not in toks or "dizin" not in toks:
        return False
    if not (info.get("country", "") or "").strip():
        return False
    return not (info.get("tuysgm_key", "") or "").strip()


def find_country_tuysgm(iso3):
    iso = (iso3 or "").lower()
    best = None
    for path, info in _iter_notes():
        if not _is_country_tuysgm(info):
            continue
        if (info.get("country", "") or "").strip().lower() != iso:
            continue
        idno = _int_id(info)
        if best is None or idno > best["id_int"]:
            best = {"id": info.get("id", ""), "id_int": idno, "path": path,
                    "date": info.get("date", "")}
    return best


def find_section_notes(iso3):
    iso = (iso3 or "").lower()
    by_key = {}
    legacy = []
    for path, info in _iter_notes():
        toks = n_type_tokens(info)
        if "tuysgm" not in toks:
            continue
        if "dizin" in toks or "hub" in toks:
            continue
        if (info.get("country", "") or "").strip().lower() != iso:
            continue
        rec = {"id": info.get("id", ""), "id_int": _int_id(info), "path": path,
               "date": info.get("date", "")}
        key = (info.get("tuysgm_key", "") or "").strip()
        if not key:
            legacy.append(rec)
        elif key not in by_key or rec["id_int"] > by_key[key]["id_int"]:
            by_key[key] = rec
    return by_key, legacy


def find_global_index():
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


def find_country_tuysgm_all():
    hubs = []
    for path, info in _iter_notes():
        if not _is_country_tuysgm(info):
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
    opts = {"headings": False, "dir": None, "yes": False, "no_prune": False,
            "check": False, "force": False, "delete": False}
    positional = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--headings":
            opts["headings"] = True
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


# ---------------------------------------------------------------------------
# Source discovery
# ---------------------------------------------------------------------------

def discover_docs(iso3, override=None):
    """Return the sorted list of .doc/.docx paths under data/{iso3}/gbn/tuysgm."""
    folder = data_subdir(iso3, override)
    if not os.path.isdir(folder):
        return folder, []
    files = sorted(
        os.path.join(folder, name)
        for name in os.listdir(folder)
        if name.lower().endswith((".doc", ".docx"))
        and os.path.isfile(os.path.join(folder, name))
        and not name.startswith("~$"))
    return folder, files


# ---------------------------------------------------------------------------
# Finalize: link the country hub into the vault
# ---------------------------------------------------------------------------

def finalize_plugin(iso3, display, country_field, hub_path, hub_title):
    nb.update_country_hub(iso3, "tuysgm", hub_path, hub_title,
                          display=display, country_field=country_field)


def finalize_standalone(hub_path, today, alloc_id):
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
             for title, path in find_country_tuysgm_all()]
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
# Freshness gate (same idea as getTubitakNotes, separate threshold)
# ---------------------------------------------------------------------------

TUYSGM_AGE_ENV = "NOTES_TUYSGM_REPORT_MAX_AGE_DAYS"


def _tuysgm_max_age_days():
    try:
        return int(os.environ.get(TUYSGM_AGE_ENV, "30"))
    except ValueError:
        return 30


def _age_text(title, days, source):
    if days is None:
        return f"{title} (tarih bilgisi yok)."
    verb = "güncellendi" if source == "modify" else "oluşturuldu"
    human = "bugün" if days <= 0 else f"{days} gün önce"
    return f"{title} {human} {verb}."


def tuysgm_report_status(source):
    iso3, _display = resolve_country(source)
    if not iso3:
        return None, None, None, ""
    hub = find_country_tuysgm(iso3)
    if not hub:
        return None, None, None, ""
    info = parse_front_matter(hub["path"])
    title = re.sub(r"\s+", " ", (info.get("title") or "")
                   .replace("\xa0", " ")).strip().strip('"')
    if not title:
        name = lu.iso3ToName(iso3.upper())
        title = f"{name if name != 1 else iso3.upper()} TÜYSGM Bilgi Notları"
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

    max_age = _tuysgm_max_age_days()
    source = positional[0]
    iso3, display = resolve_country(source)

    if opts["delete"]:
        if not PLUGIN:
            print("--delete yalnızca eklenti (plugin) modunda desteklenir.")
            return 1
        if not iso3:
            print("ISO-3 kodu çözülemedi.")
            return 1
        name = lu.iso3ToName(iso3.upper())
        return nb.delete_country_type(
            iso3, "obn tuysgm", "tuysgm", iso3.lower(),
            name if name != 1 else iso3.upper())

    if opts["check"]:
        hub, days, src, title = tuysgm_report_status(source)
        if hub:
            fresh = 1 if (days is not None and days < max_age) else 0
            print(f"REPORT_EXISTS: {hub['path']}")
            print(f"REPORT_AGE_DAYS: {'' if days is None else days}")
            print(f"REPORT_AGE_SOURCE: {src}")
            print(f"REPORT_FRESH: {fresh}")
            print(f"REPORT_AGE_TEXT: {_age_text(title, days, src)}")
        return 0

    if not opts["force"] and not opts["headings"]:
        hub, days, src, title = tuysgm_report_status(source)
        if hub and days is not None and days < max_age:
            print(f"ATLANDI: {_age_text(title, days, src)} "
                  f"({max_age} günden yeni; yenilenmedi)")
            return 0

    if not iso3:
        print(f"ISO-3 kodu çözülemedi: {source}. Açıkça bir ISO3 kodu verin "
              "(örn. data/<iso3>/gbn/tuysgm).")
        return 1
    country_field = iso3.lower()
    country_name = display or (lu.iso3ToName(iso3.upper())
                              if lu.iso3ToName(iso3.upper()) != 1
                              else iso3.upper())

    folder, docs = discover_docs(iso3, opts["dir"])
    if not docs:
        print(f"Belge bulunamadı: {folder}")
        print("Beklenen konum: data/{iso3}/gbn/tuysgm/*.doc "
              "(--dir ile değiştirilebilir)")
        return NO_DATA_CODE

    print(f"Country  : {country_name} ({iso3})")
    print(f"Folder   : {folder}")
    print(f"DOC(s)   : {len(docs)}")
    for path in docs:
        print(f"  - {os.path.basename(path)}")
    print(f"Mode     : {'plugin (notebox)' if PLUGIN else 'standalone'}")

    # --- convert + parse every document ---------------------------------
    reports = []
    workdir = tempfile.mkdtemp(prefix="tuysgm-")
    try:
        for path in docs:
            html_path = convert_to_html(path, workdir)
            if not html_path:
                continue
            try:
                blocks = read_html(html_path)
            except Exception as exc:
                print(f"UYARI ayrıştırılamadı: {os.path.basename(path)} ({exc})")
                continue
            subject, sections = collect_sections(blocks)
            for sec in sections:
                sec["body"] = render_body(sec["blocks"])
            doc_slug = slug(os.path.splitext(os.path.basename(path))[0]) or "rapor"
            year = bib_year(subject, os.path.basename(path))
            title = subject or os.path.splitext(os.path.basename(path))[0]
            reports.append({
                "path": path,
                "rel": os.path.relpath(path, OUT_DIR),
                "slug": doc_slug,
                "subject": subject,
                "title": title,
                "year": year,
                "key": bib_key(iso3, doc_slug, year),
                "sections": sections,
            })
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    # --- collect notes, namespacing keys per report ----------------------
    notes = []
    seen_keys = {}
    for rpt in reports:
        for sec in rpt["sections"]:
            if not sec["body"]:
                continue
            base = f"{rpt['slug']}/{slug(sec['title'])}"
            count = seen_keys.get(base, 0) + 1
            seen_keys[base] = count
            key = base if count == 1 else f"{base}#{count}"
            notes.append({"section": sec, "key": key, "report": rpt})

    if not notes:
        print("Not üretilecek metin bulunamadı (başlık/metin yok).")
        return 1

    hub_title = f"{country_name} TÜYSGM Bilgi Notları"
    today = dt.datetime.now().strftime("%d/%m/%Y")

    existing_hub = find_country_tuysgm(iso3)
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
    for note in notes:
        nkey = note["key"]
        rec = by_key.get(nkey)
        if rec:
            plan.append({"note": note, "key": nkey, "id": rec["id"],
                         "path": rec["path"], "date": rec["date"] or today,
                         "modify": today, "reused": True})
        else:
            nid = alloc_id()
            plan.append({"note": note, "key": nkey, "id": nid,
                         "path": os.path.join(OUT_DIR, f"{nid}.md"),
                         "date": today, "modify": "", "reused": False})

    generated_keys = {p["key"] for p in plan}
    orphans = [rec for k, rec in by_key.items() if k not in generated_keys]
    orphans.extend(legacy)

    if opts["headings"]:
        for rpt in reports:
            print(f"\n== {os.path.basename(rpt['path'])} "
                  f"({len(rpt['sections'])} başlık)")
            if rpt["subject"]:
                print(f"   Konu: {rpt['subject']}")
            for sec in rpt["sections"]:
                tag = " *" if sec["body"] else ""
                print(f"  # {sec['title']}{tag}")
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
    write_file(bib_path, "".join(
        bib_entry(r["key"], r["title"], r["rel"], r["year"]) + "\n"
        for r in reports))

    # --- write section notes --------------------------------------------
    for p in plan:
        sec = p["note"]["section"]
        key = p["note"]["report"]["key"]
        content = (
            build_note_header(p["id"], sec["title"], country_field,
                              bibfile=bibfile_rel, tuysgm_key=p["key"],
                              date=p["date"], modify=p["modify"])
            + "\n"
            + sec["body"].strip()
            + f"\n\n@{key}\n"
            + f"\n#BackReferences:\n1- [{hub_title}]({hub_id}.md)\n"
        )
        write_file(p["path"], content)

    # --- write the per-country hub --------------------------------------
    note_id = {id(p["note"]["section"]): p["id"] for p in plan}
    hub_body = []
    for rpt in reports:
        for sec in rpt["sections"]:
            lines = [f"# {sec['title']}"]
            nid = note_id.get(id(sec))
            if nid is not None:
                lines.append(f"- [{sec['title']}]({nid}.md)")
            hub_body.append("\n".join(lines))
    note_links = "\n".join(
        f"- [{p['note']['section']['title']}]({os.path.basename(p['path'])})"
        for p in plan)
    doc_links = "\n".join(
        f"- [{os.path.basename(r['path'])}]({r['rel'].replace(os.sep, '/')})"
        for r in reports)
    cite_keys = " ".join(f"@{r['key']}" for r in reports)
    hub_content = (
        build_country_header(hub_id, hub_title, country_field,
                             bibfile=bibfile_rel, date=hub_date,
                             modify=hub_modify)
        + "\n"
        + f"# {country_name} TÜYSGM Bilgi Notları\n\n"
        + "## Kaynak Belge(ler)\n\n"
        + doc_links
        + "\n\n## Notlar\n\n"
        + note_links
        + "\n\n## İçerik\n\n"
        + "\n\n".join(hub_body).strip()
        + f"\n\n{cite_keys}\n"
        + f"\n#BackReferences:\n1- [{INDEX_TITLE}]({INDEX_FILE})\n"
    )
    write_file(hub_path, hub_content)

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
