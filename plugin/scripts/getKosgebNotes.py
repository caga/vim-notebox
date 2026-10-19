#!/home/osman/.vim/plugged/vim-notebox/plugin/scripts/venv/bin/python3
"""
getKosgebNotes.py

Convert local KOSGEB "Bilgi Notu" DOCX file(s), sent for a country, into a set
of separate Markdown notes: one note per section heading that has its own text,
plus a per-country hub note linking them and the source DOCX(s).

Source documents are read from the vault (note box) folder:

    data/{iso3}/gbn/kosgeb/*.docx

There may be several DOCX files in that folder; every file is parsed and
referenced. A single DOCX may cover several countries; notes are attributed to
the folder's ISO3 only.

The DOCX body is wrapped in a Word table and its section headings are fully
bold paragraphs (same font size as the body), so they are located with a small
stdlib parser rather than a PDF/markdown converter:
  * A heading is a paragraph whose runs are all bold, that is not a list item
    (no numPr) and is short; the cover page (before "KONU:") is skipped.
  * List paragraphs (numPr) are rendered as Markdown bullets.
  * Headings that only contain sub-headings (no own text) produce no note but
    still appear in the hub outline.

Output notes use the vault's standard YAML header with:
    n_type: obn kosgeb        (section/content notes)
    n_type: obn dizin kosgeb  (the per-country kosgeb index)
    n_type: hub obn genel     (the global OBN hub, file obn-hub.md)

Two modes (auto-detected):
  * plugin: when `notebox` is importable (vim-notebox), notes go to
    nb.notes_dir(), and the per-country hub is linked into the country hub
    (`n_type: hub {iso3}`) and the general index via notebox helpers.
  * standalone: otherwise notes go to the repository root and a simple general
    index is maintained here.

Usage:
    getKosgebNotes.py <iso3|country> [--dir DIR] [--headings] [--yes]
                      [--no-prune] [--check] [--force] [--delete]

    <iso3|country>  an ISO-3166 alpha-3 code (folder name) or a country name
    --dir DIR       read DOCX files from DIR instead of data/{iso3}/gbn/kosgeb
    --headings      dry run: print the outline and the planned new/updated/
                    orphan notes, without writing anything
    --yes           auto-confirm deletion of orphan section notes
    --no-prune      never delete orphan section notes
    --check         only report the existing profile's age (no writes);
                    prints REPORT_* lines
    --force         ignore the freshness gate and regenerate
    --delete        delete all generated notes for the country (plugin only)

Freshness gate: if the per-country hub exists and is newer than
NOTES_KOSGEB_REPORT_MAX_AGE_DAYS (default 30) days, regeneration is skipped.
--headings always bypasses the gate.
"""

import os
import re
import sys
import zipfile
import datetime as dt
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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

AUTHOR = os.path.splitext(os.path.basename(sys.argv[0] or ""))[0] or "getKosgebNotes"
INSTITUDE = "kosgeb"
N_TYPE_NOTE = "obn kosgeb"            # section (content) notes
N_TYPE_COUNTRY = "obn dizin kosgeb"   # per-country kosgeb index
N_TYPE_GLOBAL = "hub obn genel"       # global OBN hub (obn-hub.md)
CITATION_STYLE = "csl/ieee-with-url.csl"

INDEX_FILE = "obn-hub.md"
INDEX_TITLE = "Otomatik Bilgi Notları Dizini"

PUBLISHER = "KOSGEB"
HOWPUBLISHED = "KOSGEB Bilgi Notu"
BIB_LABEL = "kosgeb"

NO_DATA_CODE = 2

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# Maximum length of a bold paragraph to be accepted as a heading.
MAX_HEADING_LEN = 100

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


def notes_dir():
    return nb.notes_dir() if PLUGIN else STANDALONE_OUT


def bib_dir():
    return nb.bib_dir() if PLUGIN else os.path.join(STANDALONE_OUT, "bibfiles")


def gen_id():
    return nb.IdGenerator() if PLUGIN else _standalone_id()


OUT_DIR = notes_dir()
BIB_DIR = bib_dir()


def data_subdir(iso3, override=None):
    """DOCX folder for a country: data/{iso3}/gbn/kosgeb (or an override)."""
    if override:
        return override
    return os.path.join(OUT_DIR, "data", iso3.lower(), "gbn", "kosgeb")


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


def norm_name(s: str) -> str:
    return norm(s)


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
    """Collapse whitespace and drop soft-hyphen/word-joiner artefacts."""
    text = re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()
    return text


def strip_punct(title: str) -> str:
    """Drop wrapping quotes and a trailing colon from a heading."""
    title = title.strip().strip('"').strip("\u201c\u201d").strip()
    return title.rstrip(":").strip()


def yaml_title(title: str) -> str:
    """Render a title as a safely quoted YAML scalar."""
    safe = title.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{safe}"'


# ---------------------------------------------------------------------------
# Country resolution
# ---------------------------------------------------------------------------

def resolve_country(arg):
    """Resolve user input to (iso3_lower or None, display name)."""
    arg = re.sub(r"\s+", " ", (arg or "").replace("\xa0", " ")).strip()
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
# DOCX parsing (stdlib)
# ---------------------------------------------------------------------------

def _run_is_bold(run):
    rpr = run.find(W + "rPr")
    if rpr is None:
        return False
    b = rpr.find(W + "b")
    if b is None:
        return False
    val = b.get(W + "val")
    return val not in ("0", "false", "off")


def _par_text(par):
    parts = []
    for node in par.iter():
        if node.tag == W + "t":
            parts.append(node.text or "")
        elif node.tag == W + "tab":
            parts.append(" ")
    return "".join(parts)


def _par_bold(par):
    has_text = False
    all_bold = True
    for run in par.iter(W + "r"):
        if (run.find(W + "t") is None) and ("".join(
                t.text or "" for t in run.iter(W + "t")) == ""):
            continue
        has_text = True
        if not _run_is_bold(run):
            all_bold = False
    return has_text and all_bold


def _par_is_list(par):
    ppr = par.find(W + "pPr")
    return ppr is not None and ppr.find(W + "numPr") is not None


def _walk_paragraphs(element):
    """Yield w:p elements in document order, descending into tables."""
    for child in element:
        if child.tag == W + "p":
            yield child
        elif child.tag == W + "tbl":
            for tr in child.findall(W + "tr"):
                for tc in tr.findall(W + "tc"):
                    yield from _walk_paragraphs(tc)


def read_docx(path):
    """Return a list of paragraph dicts {text, bold, list} in document order."""
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml")
    body = ET.fromstring(xml).find(W + "body")
    paras = []
    for par in _walk_paragraphs(body):
        text = clean_heading(_par_text(par))
        paras.append({"text": text, "bold": _par_bold(par),
                      "list": _par_is_list(par)})
    return paras


def _is_cover_text(text):
    n = norm(text)
    if not n:
        return False
    if n in {"tc", "konu", "bilginotu"}:
        return True
    if "kucukveortaolcekli" in n:
        return True
    for month in _TR_MONTHS:
        if re.fullmatch(month + r"20\d{2}", n):
            return True
    return False


def is_heading(text, bold, is_list):
    if not bold or is_list:
        return False
    t = (text or "").strip()
    if not t or len(t) > MAX_HEADING_LEN:
        return False
    if t[:1] in ("\u201c", "\u201d", '"'):
        return False
    return not _is_cover_text(t)


def _konu_index(paras):
    for i, p in enumerate(paras):
        if norm(p["text"]) == "konu":
            return i
    return -1


def collect_sections(paras):
    """Return (subject, sections).

    subject  : preamble text between the cover and the first heading
    sections : list of {title, body(str), paras(list)}
    """
    start = _konu_index(paras)
    if start >= 0:
        tail = paras[start + 1:]
    else:
        tail = [p for p in paras if not _is_cover_text(p["text"])]

    subject_paras = []
    sections = []
    current = None
    for p in tail:
        if is_heading(p["text"], p["bold"], p["list"]):
            current = {"title": strip_punct(p["text"]), "paras": []}
            sections.append(current)
        elif current is None:
            subject_paras.append(p)
        else:
            current["paras"].append(p)

    for sec in sections:
        sec["body"] = render_body(sec["paras"])
    return render_body(subject_paras), sections


def render_body(paras):
    """Render paragraphs as Markdown (list paragraphs become bullets)."""
    blocks = []
    bullets = []
    for p in paras:
        text = (p["text"] or "").strip()
        if not text:
            continue
        if p["list"]:
            bullets.append("- " + text)
        else:
            if bullets:
                blocks.append("\n".join(bullets))
                bullets = []
            blocks.append(text)
    if bullets:
        blocks.append("\n".join(bullets))
    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# YAML headers
# ---------------------------------------------------------------------------

_HEADER_TAIL = (
    'toc-title: "İçindekiler"\n'
    'tableTitle: "Tablo"\n'
    'lotTitle: "Tablolar"\n'
    'reference-section-title: "Kaynakça"\n'
    'figureTitle: "Şekil"\n'
    "colorlinks: true\n"
    "---\n"
)


def build_note_header(nid, title, country, bibfile="", kosgeb_key="", date=None,
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
        f"institude: {INSTITUDE}\n"
        f"n_type: {N_TYPE_NOTE}\n"
        f"kosgeb_key: {kosgeb_key}\n"
        "keywords:\n"
        f"bibliography: {bibfile}\n"
        f"citation-style: {CITATION_STYLE}\n"
        + _HEADER_TAIL
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
        f"institude: {INSTITUDE}\n"
        f"n_type: {N_TYPE_COUNTRY}\n"
        "keywords:\n"
        f"bibliography: {bibfile}\n"
        f"citation-style: {CITATION_STYLE}\n"
        + _HEADER_TAIL
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
        + _HEADER_TAIL
    )


# ---------------------------------------------------------------------------
# Bibliography
# ---------------------------------------------------------------------------

def bib_year(*names):
    """Year from a name (last 20xx match), else the current year."""
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


def bib_key(iso3, docx_slug, year):
    return f"{BIB_LABEL}-{iso3}-{docx_slug}-{year}"


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


def _is_country_kosgeb(info):
    """A per-country kosgeb index: n_type has both 'kosgeb' and 'dizin'."""
    toks = n_type_tokens(info)
    if "kosgeb" not in toks or "dizin" not in toks:
        return False
    if not (info.get("country", "") or "").strip():
        return False
    return not (info.get("kosgeb_key", "") or "").strip()


def find_country_kosgeb(iso3):
    """Return {id, id_int, path, date} of the country's kosgeb hub, or None."""
    iso = (iso3 or "").lower()
    best = None
    for path, info in _iter_notes():
        if not _is_country_kosgeb(info):
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

    by_key maps kosgeb_key -> {id, id_int, path, date} (highest id wins);
    legacy lists older notes without a kosgeb_key (treated as orphans).
    """
    iso = (iso3 or "").lower()
    by_key = {}
    legacy = []
    for path, info in _iter_notes():
        toks = n_type_tokens(info)
        if "kosgeb" not in toks:
            continue
        if "dizin" in toks or "hub" in toks:
            continue
        if (info.get("country", "") or "").strip().lower() != iso:
            continue
        rec = {"id": info.get("id", ""), "id_int": _int_id(info), "path": path,
               "date": info.get("date", "")}
        key = (info.get("kosgeb_key", "") or "").strip()
        if not key:
            legacy.append(rec)
        elif key not in by_key or rec["id_int"] > by_key[key]["id_int"]:
            by_key[key] = rec
    return by_key, legacy


# --- standalone-only general index helpers ---------------------------------

def find_global_index():
    """Return {id, id_int, path, date} of the general OBN index, or None."""
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


def find_country_kosgeb_all():
    """Return [(title, path)] for every country's kosgeb hub (standalone)."""
    hubs = []
    for path, info in _iter_notes():
        if not _is_country_kosgeb(info):
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
# Source DOCX discovery
# ---------------------------------------------------------------------------

def discover_docx(iso3, override=None):
    """Return the sorted list of DOCX paths under data/{iso3}/gbn/kosgeb."""
    folder = data_subdir(iso3, override)
    if not os.path.isdir(folder):
        return folder, []
    files = sorted(
        os.path.join(folder, name)
        for name in os.listdir(folder)
        if name.lower().endswith(".docx")
        and os.path.isfile(os.path.join(folder, name))
        and not name.startswith("~$"))
    return folder, files


# ---------------------------------------------------------------------------
# Finalize: link the country hub into the vault
# ---------------------------------------------------------------------------

def finalize_plugin(iso3, display, country_field, hub_path, hub_title):
    """Link the per-country kosgeb index into the country OBN page/vault."""
    nb.update_country_hub(iso3, "kosgeb", hub_path, hub_title,
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
             for title, path in find_country_kosgeb_all()]
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
# Freshness gate (same idea as getTubitakNotes, separate threshold)
# ---------------------------------------------------------------------------

KOSGEB_AGE_ENV = "NOTES_KOSGEB_REPORT_MAX_AGE_DAYS"


def _kosgeb_max_age_days():
    try:
        return int(os.environ.get(KOSGEB_AGE_ENV, "30"))
    except ValueError:
        return 30


def _age_text(title, days, source):
    if days is None:
        return f"{title} (tarih bilgisi yok)."
    verb = "güncellendi" if source == "modify" else "oluşturuldu"
    human = "bugün" if days <= 0 else f"{days} gün önce"
    return f"{title} {human} {verb}."


def kosgeb_report_status(source):
    """(hub, days, source, title) - existing per-country kosgeb index note."""
    iso3, _display = resolve_country(source)
    if not iso3:
        return None, None, None, ""
    hub = find_country_kosgeb(iso3)
    if not hub:
        return None, None, None, ""
    info = parse_front_matter(hub["path"])
    title = re.sub(r"\s+", " ", (info.get("title") or "")
                   .replace("\xa0", " ")).strip().strip('"')
    if not title:
        name = lu.iso3ToName(iso3.upper())
        title = f"{name if name != 1 else iso3.upper()} KOSGEB Bilgi Notları"
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

    max_age = _kosgeb_max_age_days()
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
            iso3, "obn kosgeb", "kosgeb", iso3.lower(),
            name if name != 1 else iso3.upper())

    if opts["check"]:
        hub, days, src, title = kosgeb_report_status(source)
        if hub:
            fresh = 1 if (days is not None and days < max_age) else 0
            print(f"REPORT_EXISTS: {hub['path']}")
            print(f"REPORT_AGE_DAYS: {'' if days is None else days}")
            print(f"REPORT_AGE_SOURCE: {src}")
            print(f"REPORT_FRESH: {fresh}")
            print(f"REPORT_AGE_TEXT: {_age_text(title, days, src)}")
        return 0

    if not opts["force"] and not opts["headings"]:
        hub, days, src, title = kosgeb_report_status(source)
        if hub and days is not None and days < max_age:
            print(f"ATLANDI: {_age_text(title, days, src)} "
                  f"({max_age} günden yeni; yenilenmedi)")
            return 0

    if not iso3:
        print(f"ISO-3 kodu çözülemedi: {source}. Açıkça bir ISO3 kodu verin "
              "(örn. data/<iso3>/gbn/kosgeb).")
        return 1
    country_field = iso3.lower()
    country_name = display or (lu.iso3ToName(iso3.upper())
                              if lu.iso3ToName(iso3.upper()) != 1
                              else iso3.upper())

    folder, docx_files = discover_docx(iso3, opts["dir"])
    if not docx_files:
        print(f"DOCX bulunamadı: {folder}")
        print("Beklenen konum: data/{iso3}/gbn/kosgeb/*.docx "
              "(--dir ile değiştirilebilir)")
        return NO_DATA_CODE

    print(f"Country  : {country_name} ({iso3})")
    print(f"Folder   : {folder}")
    print(f"DOCX(s)  : {len(docx_files)}")
    for path in docx_files:
        print(f"  - {os.path.basename(path)}")
    print(f"Mode     : {'plugin (notebox)' if PLUGIN else 'standalone'}")

    # --- parse every DOCX into (subject, sections, report info) ----------
    reports = []
    for path in docx_files:
        try:
            paras = read_docx(path)
        except Exception as exc:
            print(f"UYARI okunamadı: {os.path.basename(path)} ({exc})")
            continue
        subject, sections = collect_sections(paras)
        docx_slug = slug(os.path.splitext(os.path.basename(path))[0]) or "rapor"
        year = bib_year(subject, os.path.basename(path))
        title = subject.split("\n", 1)[0].strip() \
            or os.path.splitext(os.path.basename(path))[0]
        reports.append({
            "path": path,
            "rel": os.path.relpath(path, OUT_DIR),
            "slug": docx_slug,
            "subject": subject,
            "title": title,
            "year": year,
            "key": bib_key(iso3, docx_slug, year),
            "sections": sections,
        })

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

    hub_title = f"{country_name} KOSGEB Bilgi Notları"
    today = dt.datetime.now().strftime("%d/%m/%Y")

    # --- reuse previously generated notes for this country ---------------
    existing_hub = find_country_kosgeb(iso3)
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

    # --- dry run ---------------------------------------------------------
    if opts["headings"]:
        for rpt in reports:
            print(f"\n== {os.path.basename(rpt['path'])} "
                  f"({len(rpt['sections'])} başlık)")
            if rpt["subject"]:
                print(f"   Konu: {rpt['subject'].splitlines()[0]}")
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

    # --- write bibliography (one entry per DOCX) -------------------------
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
                              bibfile=bibfile_rel, kosgeb_key=p["key"],
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
    docx_links = "\n".join(
        f"- [{os.path.basename(r['path'])}]({r['rel'].replace(os.sep, '/')})"
        for r in reports)
    cite_keys = " ".join(f"@{r['key']}" for r in reports)
    hub_content = (
        build_country_header(hub_id, hub_title, country_field,
                             bibfile=bibfile_rel, date=hub_date,
                             modify=hub_modify)
        + "\n"
        + f"# {country_name} KOSGEB Bilgi Notları\n\n"
        + "## Kaynak DOCX\n\n"
        + docx_links
        + "\n\n## Notlar\n\n"
        + note_links
        + "\n\n## İçerik\n\n"
        + "\n\n".join(hub_body).strip()
        + f"\n\n{cite_keys}\n"
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
