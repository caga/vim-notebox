#!/home/osman/.vim/plugged/vim-notebox/plugin/scripts/venv/bin/python3
"""
getOtherBns.py

Convert "other" institution information notes (multi-country documents) into
per-country Markdown notes. A single document may contain information for many
countries; the script extracts only the sections related to the requested
country.

Documents live under:

    data/gbns/{inst}/*.doc | *.docx | *.pdf

Only that folder tree is searched (override with --dir; restrict to one
institute folder with --inst). The institute is inferred from the folder name,
else from the document content/title; if it cannot be inferred the script asks.
`tubitak`, `kosgeb` and `tuysgm` are handled by their own dedicated scripts
(they read `data/{iso3}/gbn/...`) and are excluded here.

Formats:
  * .pdf          -> PyMuPDF4LLM markdown
  * .doc / .docx  -> LibreOffice headless -> HTML -> BeautifulSoup

Documents in the same folder that are the same (byte-identical, same extracted
text, or >= --dedup-threshold similar) are reduced to a single file (the newest
one); the others are recorded as aliases in the hub's source list.

For every institute found, notes are produced exactly like the dedicated
TUBITAK/TUYSGM scripts: one section note per matched heading and one
per-country hub, linked into the country OBN page. Output YAML headers use:
    n_type: obn <inst>        (section/content notes)
    n_type: obn dizin <inst>  (the per-country index of that institute)
    n_type: hub obn genel      (global OBN hub, obn-hub.md)
There is no generic note type: every note carries a real institute slug.

Usage:
    ./getOtherBns.py <iso3|country> [--dir DIR] [--box DIR] [--inst FOLDER]
                     [--headings] [--yes] [--no-prune] [--check] [--force]
                     [--delete] [--no-dedup] [--dedup-threshold R]

    <iso3|country>  an ISO-3166 alpha-3 code or a country name
    --box DIR       note box (default: $NOTES_DIR or cwd)
    --dir DIR       search root (default: <box>/data/gbns)
    --inst FOLDER   only process this institute folder
    --headings      dry run: print the outline and planned notes/writes
    --yes           auto-confirm orphan deletion
    --no-prune      never delete orphan section notes
    --check         report the existing hub's age (prints REPORT_* lines)
    --force         ignore the freshness gate and regenerate
    --delete        delete all generated notes for the country (plugin only)
    --no-dedup      disable the document de-duplication pass
    --dedup-threshold R   near-duplicate similarity threshold (default 0.90)

Freshness gate: if the country's newest hub (among the managed institutes)
exists and is newer than NOTES_OTHERBN_REPORT_MAX_AGE_DAYS (default 30) days,
regeneration is skipped.

Requires LibreOffice (`soffice`) for Word documents.
"""

import os
import re
import sys
import shutil
import hashlib
import subprocess
import tempfile
import datetime as dt

import _cli

_cli.init()

import pymupdf
import pymupdf4llm
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

AUTHOR = os.path.splitext(os.path.basename(sys.argv[0] or ""))[0] or "getOtherBns"
N_TYPE_GLOBAL = "hub obn genel"       # global OBN hub (obn-hub.md)
CITATION_STYLE = "csl/ieee-with-url.csl"

INDEX_FILE = "obn-hub.md"
INDEX_TITLE = "Otomatik Bilgi Notları Dizini"

DEFAULT_SEARCH = "data/gbns"
NO_DATA_CODE = 2
SOFFICE = os.environ.get("SOFFICE_BIN", "soffice")
MAX_HEADING_LEN = 100
MIN_BODY_WORDS = 12
WORD_RE = re.compile(r"\S+")

# dedicated per-country scripts own these kinds; never touch them here
EXCLUDED_INSTITUTES = {"tubitak", "kosgeb", "tuysgm"}

# folder name (and aliases) -> canonical institute slug
INST_FOLDER_SLUG = {
    "tubitak": "tubitak",
    "kosgeb": "kosgeb",
    "tuysgm": "tuysgm",
    "tp": "turkpatent", "turkpatent": "turkpatent", "tpe": "turkpatent",
    "tse": "tse",
    "mtgm": "mtgm", "mtyzgm": "mtgm", "mtzygm": "mtgm",
    "db": "db",
    "tb": "tb",
    "tua": "tua",
    "tuba": "tuba",
    "sgm": "sgm",
    "sbgm": "sbgm",
    "savgm": "savgm",
    "atgm": "atgm",
    "kagm": "kagm",
}

INST_SHORT = {
    "tubitak": "TÜBİTAK", "kosgeb": "KOSGEB", "turkpatent": "Türk Patent",
    "tse": "TSE", "tuysgm": "TÜYSGM", "mtgm": "MTGM", "db": "DB", "tb": "TB",
    "tua": "TUA", "tuba": "TÜBA", "sgm": "SGM", "sbgm": "SBGM",
    "savgm": "SAVGM", "atgm": "ATGM", "kagm": "KAGM",
}

INST_NAME = {
    "tubitak": "TÜBİTAK", "kosgeb": "KOSGEB", "turkpatent": "Türk Patent",
    "tse": "Türk Standartları Enstitüsü",
    "tuysgm": "Teşvik Uygulama ve Yabancı Sermaye Genel Müdürlüğü",
    "mtgm": "Milli Teknoloji ve Yapay Zeka Genel Müdürlüğü",
    "db": "Dışişleri Bakanlığı", "tb": "Ticaret Bakanlığı",
    "tua": "Türkiye Uzay Ajansı", "tuba": "Türkiye Bilimler Akademisi",
    "sgm": "Sanayi Genel Müdürlüğü",
    "sbgm": "Sanayi Bölgeleri Genel Müdürlüğü",
    "savgm": "Stratejik Araştırmalar ve Verimlilik Genel Müdürlüğü",
    "atgm": "Ar-Ge Teşvikleri Genel Müdürlüğü",
    "kagm": "Kalkınma Ajansları Genel Müdürlüğü",
}

# content fingerprints -> canonical slug (checked in order, most specific first)
INST_PATTERNS = [
    ("turkpatent", "turkpatent"),
    ("turkiyeuzayajansi", "tua"),
    ("turkiyebilimlerakademisi", "tuba"),
    ("turkstandardlarienstitusu", "tse"),
    ("milliteknolojiveyapayzeka", "mtgm"),
    ("tesvikuygulamaveyabancisermaye", "tuysgm"),
    ("stratejikarastirmalarsav", "savgm"),
    ("sanayibolgeleri", "sbgm"),
    ("argetesvikleri", "atgm"),
    ("kalkinmaajanslari", "kagm"),
    ("sanayigenelmudurlugu", "sgm"),
    ("tubitak", "tubitak"),
    ("kosgeb", "kosgeb"),
    ("disisleribakanligi", "db"),
    ("ticaretbakanligi", "tb"),
]

# ISO3 -> Turkish heading substrings (already folded) to match a country
COUNTRY_TOKENS = {
    "aus": ["avustralya"],
    "nzl": ["yenizelanda", "zelanda"],
    "lka": ["srilanka", "lanka"],
    "phl": ["filipin"],
    "brn": ["brunei", "bruney", "bruneidarusselam"],
    "lao": ["laos"],
    "npl": ["nepal"],
    "mdv": ["maldiv"],
    "afg": ["afganistan"],
    "tls": ["dogutimor", "timorleste", "timor"],
    "mmr": ["myanmar", "burma"],
    "fin": ["finlandiya"],
    "vut": ["vanuatu"],
    "fji": ["fiji"],
    "slb": ["solomon"],
    "ind": ["hindistan"],
    "sgp": ["singapur"],
    "tha": ["tayland"],
    "pak": ["pakistan"],
    "bgd": ["banglades"],
    "jpn": ["japonya"],
    "khm": ["kambocya"],
}

ALL_COUNTRY_TOKENS = sorted({t for toks in COUNTRY_TOKENS.values() for t in toks})

ALIASES = {
    "ABD": "USA", "Amerika": "USA", "Amerika Birleşik Devletleri": "USA",
    "İngiltere": "GBR", "Britanya": "GBR", "Birleşik Krallık": "GBR",
    "BAE": "ARE", "Güney Kore": "KOR", "Kuzey Kore": "PRK",
    "Türkiye": "TUR", "turkiye": "TUR", "Çekya": "CZE",
}

_TR_FOLD = str.maketrans({
    "İ": "i", "I": "i", "ı": "i", "Ş": "s", "ş": "s", "Ğ": "g", "ğ": "g",
    "Ü": "u", "ü": "u", "Ö": "o", "ö": "o", "Ç": "c", "ç": "c",
})

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def notes_dir():
    return nb.notes_dir() if PLUGIN else STANDALONE_OUT


def bib_dir():
    return nb.bib_dir() if PLUGIN else os.path.join(STANDALONE_OUT, "bibfiles")


def gen_id():
    return nb.IdGenerator() if PLUGIN else _standalone_id


OUT_DIR = notes_dir()
BIB_DIR = bib_dir()

# ids reserved during this run (so institutes don't collide even in dry-run)
_RESERVED = set()


def n_type_note(inst):
    """Section/content note type for an institute."""
    return f"obn {inst}"


def n_type_country(inst):
    """Per-country index note type for an institute."""
    return f"obn dizin {inst}"


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


def clean_heading(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    text = text.replace("*", "").replace("_", "").replace("\\", "")
    return re.sub(r"\s+", " ", text).strip()


def strip_enum(title):
    """Drop a leading bullet or enumerator ('1. ', '2) ', 'a. ') from a heading."""
    title = re.sub(r"^\s*[•·▪◦\-\u2013\u2014]\s*", "", title)
    return re.sub(r"^\s*(?:\d+|[a-zA-ZçğıöşüÇĞİÖŞÜ])\s*[\.\)]\s*", "",
                  title).strip()


def yaml_title(title):
    safe = title.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{safe}"'


def words_of(text):
    """Folded lowercase word list (for shingle similarity)."""
    return re.sub(r"[^a-z0-9]+", " ",
                  (text or "").translate(_TR_FOLD).lower()).split()


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


def country_tokens(iso3):
    if iso3 in COUNTRY_TOKENS:
        return COUNTRY_TOKENS[iso3]
    name = lu.iso3ToName(iso3.upper()) if iso3 else None
    if name and name != 1:
        return [norm(name)]
    return [norm(iso3 or "")]


# ---------------------------------------------------------------------------
# Document parsing (pdf / doc / docx)
#   block = {"kind": "heading"|"para"|"table", "level": int, "text": str}
# ---------------------------------------------------------------------------

def markdown_blocks(md):
    blocks = []
    table = []

    def flush_table():
        if table:
            blocks.append({"kind": "table", "level": 0,
                           "text": "\n".join(table)})
            table.clear()

    for line in md.split("\n"):
        s = line.rstrip()
        if s.strip().startswith("|"):
            table.append(s.strip())
            continue
        flush_table()
        match = re.match(r"^(#{1,6})\s+(.*\S)\s*$", s)
        if match:
            txt = clean_heading(match.group(2))
            if txt:
                blocks.append({"kind": "heading", "level": len(match.group(1)),
                               "text": txt})
            continue
        txt = clean_heading(s)
        if txt:
            blocks.append({"kind": "para", "level": 0, "text": txt})
    flush_table()
    return blocks


def read_pdf(path):
    doc = pymupdf.open(path)
    md = pymupdf4llm.to_markdown(doc, header=False, footer=False,
                                 show_progress=False)
    doc.close()
    return markdown_blocks(md)


def convert_to_html(path, workdir):
    """Convert a .doc/.docx to HTML with LibreOffice. Return path or None."""
    profile = os.path.join(workdir, "lo-profile")
    cmd = [SOFFICE, "--headless", "--norestore",
           f"-env:UserInstallation=file://{profile}",
           "--convert-to", "html", "--outdir", workdir, path]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=180, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    html_path = os.path.join(
        workdir, os.path.splitext(os.path.basename(path))[0] + ".html")
    return html_path if os.path.exists(html_path) else None


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
    total = bold = 0
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
    with open(path, encoding="utf-8", errors="replace") as fh:
        soup = BeautifulSoup(fh.read(), "html.parser")
    blocks = []

    def walk(el):
        for child in el.children:
            name = getattr(child, "name", None)
            if name is None:
                continue
            if name == "table":
                if _is_data_table(child):
                    blocks.append({"kind": "table", "level": 0,
                                   "text": _render_table(child)})
                else:
                    walk(child)
            elif name in ("p", "h1", "h2", "h3", "h4", "h5", "h6"):
                text = clean(child.get_text(" ", strip=True))
                if not text:
                    continue
                if _par_all_bold(child) and len(text) <= MAX_HEADING_LEN \
                        and not _is_caption(text):
                    blocks.append({"kind": "heading", "level": 1, "text": text})
                else:
                    blocks.append({"kind": "para", "level": 0, "text": text})
            elif name in ("ol", "ul", "li"):
                walk(child)
            else:
                walk(child)

    walk(soup.body or soup)
    return blocks


def read_doc(path, workdir):
    """Dispatch by extension; return the block list for one document."""
    if path.lower().endswith(".pdf"):
        return read_pdf(path)
    html_path = convert_to_html(path, workdir)
    if not html_path:
        raise RuntimeError("dönüştürülemedi")
    return read_html(html_path)


# ---------------------------------------------------------------------------
# Document de-duplication
# ---------------------------------------------------------------------------

def _shingles(words, k=6):
    return {tuple(words[i:i + k]) for i in range(max(0, len(words) - k + 1))}


def _jaccard(a, b):
    A = _shingles(a)
    B = _shingles(b)
    return len(A & B) / len(A | B) if A | B else 0.0


def dedup_documents(entries, threshold, enabled=True):
    """Reduce same-information files to one (newest).

    entries: list of dicts with path, mtime, bytes_hash, text_hash, words.
    A skipped entry gets 'duplicate_of' set to the canonical path.
    """
    ordered = sorted(entries, key=lambda e: e["mtime"], reverse=True)
    canonicals = []
    skipped = []
    for entry in ordered:
        dup = None
        for canon in canonicals:
            if entry["bytes_hash"] == canon["bytes_hash"]:
                dup = canon
                break
            if entry["text_hash"] == canon["text_hash"]:
                dup = canon
                break
            if enabled and len(entry["words"]) >= 150 \
                    and len(canon["words"]) >= 150 \
                    and _jaccard(entry["words"], canon["words"]) >= threshold:
                dup = canon
                break
        if dup is not None:
            entry["duplicate_of"] = dup["path"]
            skipped.append(entry)
        else:
            canonicals.append(entry)
    return canonicals, skipped


# ---------------------------------------------------------------------------
# Country section extraction
# ---------------------------------------------------------------------------

def _heading_positions(blocks):
    return [i for i, b in enumerate(blocks) if b["kind"] == "heading"]


def _any_country(text):
    n = norm(text)
    return any(tok in n for tok in ALL_COUNTRY_TOKENS)


def _target_country(text, tokens):
    n = norm(text)
    return any(tok in n for tok in tokens)


def render_body(blocks):
    out = []
    for b in blocks:
        if b["kind"] == "heading":
            out.append(f"### {clean(b['text'])}")
        elif b["kind"] == "table":
            if b["text"]:
                out.append(b["text"])
        else:
            out.append(b["text"])
    return "\n\n".join(x for x in out if x.strip())


def collect_country_sections(blocks, tokens):
    """Return [{title, body}] for sections whose heading matches the country."""
    hidx = _heading_positions(blocks)
    sections = []
    for pos, i in enumerate(hidx):
        if not _target_country(blocks[i]["text"], tokens):
            continue
        end = len(blocks)
        for j in hidx[pos + 1:]:
            if _any_country(blocks[j]["text"]):
                end = j
                break
        body = render_body(blocks[i + 1:end])
        if len(WORD_RE.findall(body)) < MIN_BODY_WORDS:
            continue
        sections.append({"title": strip_enum(clean(blocks[i]["text"])),
                         "body": body})
    # section-level dedupe: same title -> keep the longest body
    best = {}
    for sec in sections:
        k = norm(sec["title"])
        if k not in best or len(sec["body"]) > len(best[k]["body"]):
            best[k] = sec
    return list(best.values())


# ---------------------------------------------------------------------------
# Institute inference
# ---------------------------------------------------------------------------

def infer_institute(folder_name, all_text, opts_inst):
    if opts_inst:
        return INST_FOLDER_SLUG.get(opts_inst.lower(), opts_inst.lower())
    if folder_name and folder_name.lower() in INST_FOLDER_SLUG:
        return INST_FOLDER_SLUG[folder_name.lower()]
    n = norm(all_text[:200000])
    for pattern, inst in INST_PATTERNS:
        if pattern in n:
            return inst
    return None


def ask_institute(folder_name):
    known = ", ".join(sorted(set(INST_SHORT.values())))
    if sys.stdin.isatty():
        print(f"Kurum tespit edilemedi ({folder_name}). Bilinen kurumlar: {known}")
        try:
            ans = input("Kurum (kısa ad): ").strip()
        except EOFError:
            ans = ""
        if ans:
            key = ans.lower()
            return INST_FOLDER_SLUG.get(key, key)
    print(f"HATA kurum tespit edilemedi: {folder_name}. "
          "--inst ile belirtin.")
    return None


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


def build_note_header(nid, title, country, inst, bibfile="", bn_key="",
                      date=None, modify=""):
    if PLUGIN:
        return nb.build_header(
            nid, yaml_title(title), country, date, modify,
            n_type=n_type_note(inst), bibfile=bibfile, author=AUTHOR,
            date_fmt="%d/%m/%Y", citation_style=CITATION_STYLE,
            institude=inst, extra_fields=(("bn_key", bn_key),),
        )
    return _fallback_header(nid, title, country, date, modify,
                            n_type_note(inst), bibfile=bibfile,
                            extra=(("bn_key", bn_key),), institude=inst)


def build_country_header(nid, title, country, inst, bibfile="", date=None,
                         modify=""):
    if PLUGIN:
        return nb.build_header(
            nid, yaml_title(title), country, date, modify,
            n_type=n_type_country(inst), bibfile=bibfile, author=AUTHOR,
            date_fmt="%d/%m/%Y", citation_style=CITATION_STYLE,
            institude=inst,
        )
    return _fallback_header(nid, title, country, date, modify,
                            n_type_country(inst), bibfile=bibfile,
                            institude=inst)


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


def bib_key(inst, iso3, doc_slug, year):
    return f"{inst}-{iso3}-{doc_slug}-{year}"


def bib_entry(key, title, rel_path, year):
    inst = key.split("-", 1)[0]
    name = INST_NAME.get(inst, INST_SHORT.get(inst, inst.upper()))
    return "\n".join([
        f"@misc{{{key},",
        f"  author = {{{{{name}}}}},",
        f"  title = {{{title}}},",
        f"  howpublished = {{Bilgi Notu}},",
        f"  year = {{{year}}},",
        f"  note = {{local file: {rel_path}; Erişim tarihi: {tr_today()}}}",
        "}",
    ]) + "\n"


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


def _country_ok(info, iso3):
    return (info.get("country", "") or "").strip().lower() == (iso3 or "").lower()


def _index_inst(info):
    """Return the institute slug if info is a per-country index note."""
    toks = n_type_tokens(info)
    if len(toks) >= 3 and toks[0] == "obn" and toks[1] == "dizin":
        return toks[2]
    return None


def _is_country_index(info, inst):
    return _index_inst(info) == inst


def find_country_index(iso3, inst):
    """Return the newest hub {id, id_int, path, date} for (country, institute)."""
    best = None
    for path, info in _iter_notes():
        if not _is_country_index(info, inst):
            continue
        if not _country_ok(info, iso3):
            continue
        idno = _int_id(info)
        if best is None or idno > best["id_int"]:
            best = {"id": info.get("id", ""), "id_int": idno, "path": path,
                    "date": info.get("date", "")}
    return best


def find_country_indexes(iso3, insts=None):
    """Return all {inst, id, id_int, path, date} hubs, newest first.

    When `insts` is given only those institutes are considered (managed set).
    """
    hubs = []
    for path, info in _iter_notes():
        inst = _index_inst(info)
        if inst is None:
            continue
        if insts is not None and inst not in insts:
            continue
        if not _country_ok(info, iso3):
            continue
        hubs.append({"inst": inst, "id": info.get("id", ""),
                     "id_int": _int_id(info), "path": path,
                     "date": info.get("date", "")})
    hubs.sort(key=lambda h: h["id_int"], reverse=True)
    return hubs


def find_section_notes(iso3, inst):
    """Return (by_key, legacy) section notes for the country/institute."""
    by_key = {}
    legacy = []
    for path, info in _iter_notes():
        if info.get("n_type", "") != n_type_note(inst):
            continue
        if not _country_ok(info, iso3):
            continue
        rec = {"id": info.get("id", ""), "id_int": _int_id(info), "path": path,
               "date": info.get("date", "")}
        key = (info.get("bn_key", "") or "").strip()
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


# ---------------------------------------------------------------------------
# KIND registration
# ---------------------------------------------------------------------------

def ensure_kind(inst):
    """Make sure notebox knows this institute (index/hub helpers rely on it)."""
    if not PLUGIN or inst in nb.KIND:
        return
    name = INST_NAME.get(inst, inst.upper())
    nb.KIND[inst] = dict(
        index_suffix=f"{INST_SHORT.get(inst, inst.upper())} Bilgi Notları",
        n_types=(n_type_note(inst),),
        index_n_type=n_type_country(inst),
        hub_h2=f"{name} Bilgi Notları",
    )


# ---------------------------------------------------------------------------
# Argument handling
# ---------------------------------------------------------------------------

def parse_args(argv):
    opts = {"headings": False, "dir": None, "inst": None, "yes": False,
            "no_prune": False, "check": False, "force": False, "delete": False,
            "dedup": True, "threshold": 0.90}
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
        elif arg == "--no-dedup":
            opts["dedup"] = False
        elif arg == "--dedup-threshold":
            i += 1
            if i < len(argv):
                try:
                    opts["threshold"] = float(argv[i])
                except ValueError:
                    pass
        elif arg == "--dir":
            i += 1
            opts["dir"] = argv[i] if i < len(argv) else None
        elif arg.startswith("--dir="):
            opts["dir"] = arg.split("=", 1)[1]
        elif arg == "--inst":
            i += 1
            opts["inst"] = argv[i] if i < len(argv) else None
        elif arg.startswith("--inst="):
            opts["inst"] = arg.split("=", 1)[1]
        elif arg.startswith("--"):
            print(f"Bilinmeyen seçenek: {arg}")
        else:
            positional.append(arg)
        i += 1
    return opts, positional


# ---------------------------------------------------------------------------
# Source discovery
# ---------------------------------------------------------------------------

def search_root(override):
    return override or os.path.join(OUT_DIR, DEFAULT_SEARCH)


def _folder_slug(name):
    return INST_FOLDER_SLUG.get(name.lower(), name.lower())


def institute_folders(root, only=None):
    """Return (name, path) institute folders, excluding dedicated kinds."""
    if not os.path.isdir(root):
        return []
    folders = []
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if not os.path.isdir(path):
            continue
        if only and name.lower() != only.lower():
            continue
        if _folder_slug(name) in EXCLUDED_INSTITUTES:
            continue
        folders.append((name, path))
    return folders


def managed_institutes(folders):
    return {_folder_slug(name) for name, _ in folders}


def documents_in(folder):
    exts = (".pdf", ".doc", ".docx")
    files = []
    for name in sorted(os.listdir(folder)):
        if name.startswith("~$"):
            continue
        if name.lower().endswith(exts):
            files.append(os.path.join(folder, name))
    return files


# ---------------------------------------------------------------------------
# Finalize: link the country hub into the vault
# ---------------------------------------------------------------------------

def finalize_plugin(iso3, display, country_field, inst, hub_path, hub_title):
    nb.update_country_hub(iso3, inst, hub_path, hub_title,
                          display=display, country_field=country_field)


def finalize_standalone(hub_path, today, alloc_id):
    rec = find_global_index()
    if rec:
        index_id, index_path = rec["id"], rec["path"]
    else:
        index_id = alloc_id()
        index_path = os.path.join(OUT_DIR, INDEX_FILE)
    links = []
    seen = set()
    for path, info in _iter_notes():
        if _index_inst(info) is None:
            continue
        title = clean(info.get("title", "")).strip('"')
        if title and title not in seen:
            seen.add(title)
            links.append(f"- [{title}]({os.path.basename(path)})")
    content = (build_global_header(index_id, INDEX_TITLE, today, today) + "\n"
               + "\n".join(sorted(links)) + "\n")
    write_file(index_path, content)


def prune_orphans(orphans, opts):
    if not orphans:
        return
    print(f"\nKullanılmayan notlar: {len(orphans)}")
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
        print("Atlandı (onay alınamadı; silmek için --yes).")
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

OTHERBN_AGE_ENV = "NOTES_OTHERBN_REPORT_MAX_AGE_DAYS"


def _otherbn_max_age_days():
    try:
        return int(os.environ.get(OTHERBN_AGE_ENV, "30"))
    except ValueError:
        return 30


def _age_text(title, days, source):
    if days is None:
        return f"{title} (tarih bilgisi yok)."
    verb = "güncellendi" if source == "modify" else "oluşturuldu"
    human = "bugün" if days <= 0 else f"{days} gün önce"
    return f"{title} {human} {verb}."


def otherbn_report_status(source, managed):
    iso3, _display = resolve_country(source)
    if not iso3:
        return None, None, None, ""
    hubs = find_country_indexes(iso3, managed or None)
    if not hubs:
        return None, None, None, ""
    hub = hubs[0]
    info = parse_front_matter(hub["path"])
    title = clean(info.get("title", "")).strip('"') or \
        f"{iso3.upper()} Bilgi Notları"
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

def run_institute(iso3, display, inst, sections, sources, aliases, opts,
                  summary):
    country_field = iso3.lower()
    short = INST_SHORT.get(inst, inst.upper())
    hub_title = f"{display} {short} Bilgi Notları"
    title_suffix = f" - {inst} BN"

    existing_hub = find_country_index(iso3, inst)
    by_key, legacy = find_section_notes(iso3, inst)
    used_ids = {r["id_int"] for r in list(by_key.values()) + legacy if r["id_int"]}
    counter = [gen_id()]

    def alloc_id():
        nid = counter[0]
        while nid in used_ids or nid in _RESERVED or os.path.exists(
                os.path.join(OUT_DIR, f"{nid}.md")):
            nid += 1
        counter[0] = nid + 1
        used_ids.add(nid)
        _RESERVED.add(nid)
        return nid

    today = dt.datetime.now().strftime("%d/%m/%Y")
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
    for sec in sections:
        key = f"{sec['doc_slug']}/{slug(sec['title'])}"
        rec = by_key.get(key)
        if rec:
            plan.append({"sec": sec, "key": key, "id": rec["id"],
                         "path": rec["path"], "date": rec["date"] or today,
                         "modify": today, "reused": True})
        else:
            nid = alloc_id()
            plan.append({"sec": sec, "key": key, "id": nid,
                         "path": os.path.join(OUT_DIR, f"{nid}.md"),
                         "date": today, "modify": "", "reused": False})

    generated = {p["key"] for p in plan}
    orphans = [r for k, r in by_key.items() if k not in generated]
    orphans.extend(legacy)

    if opts["headings"]:
        summary.append((inst, len(plan), sum(1 for p in plan if not p["reused"]),
                        hub_path, len(orphans)))
        return

    # bibliography (one entry per canonical source)
    os.makedirs(BIB_DIR, exist_ok=True)
    bib_path = os.path.join(BIB_DIR, f"{hub_id}.bib")
    write_file(bib_path, "".join(
        bib_entry(src["bibkey"], src["title"], src["rel"], src["year"]) + "\n"
        for src in sources))

    # section notes
    for p in plan:
        sec = p["sec"]
        content = (
            build_note_header(p["id"], f"{sec['title']}{title_suffix}",
                              country_field, inst,
                              bibfile=bibfile_rel, bn_key=p["key"],
                              date=p["date"], modify=p["modify"])
            + "\n"
            + sec["body"].strip()
            + f"\n\n@{sec['bibkey']}\n"
            + f"\n#BackReferences:\n1- [{hub_title}]({hub_id}.md)\n"
        )
        write_file(p["path"], content)

    # hub
    note_links = "\n".join(
        f"- [{p['sec']['title']}{title_suffix}]({os.path.basename(p['path'])})"
        for p in plan)
    src_links = []
    for src in sources:
        src_links.append(
            f"- [{os.path.basename(src['path'])}]("
            f"{src['rel'].replace(os.sep, '/')})")
    for al in aliases:
        if isinstance(al, dict):
            src_links.append(
                f"- {al['name']}  _(kopya: {os.path.basename(al['dup_of'])})_")
        else:
            src_links.append(f"- {al}")
    cite = " ".join(f"@{src['bibkey']}" for src in sources)
    body = [
        f"# {hub_title}",
        "## Kaynak Belge(ler)",
        "\n".join(src_links) if src_links else "-",
        "## Notlar",
        note_links if note_links else "-",
        "## İçerik",
    ]
    for p in plan:
        body.append(f"### {p['sec']['title']}{title_suffix}")
        body.append(f"- [{p['sec']['title']}{title_suffix}]"
                    f"({os.path.basename(p['path'])})")
    hub_content = (
        build_country_header(hub_id, hub_title, country_field, inst,
                             bibfile=bibfile_rel, date=hub_date,
                             modify=hub_modify)
        + "\n" + "\n\n".join(body).strip() + f"\n\n{cite}\n"
        + f"\n#BackReferences:\n1- [{INDEX_TITLE}]({INDEX_FILE})\n"
    )
    write_file(hub_path, hub_content)

    ensure_kind(inst)
    if PLUGIN:
        finalize_plugin(iso3, display, country_field, inst, hub_path, hub_title)
    else:
        finalize_standalone(hub_path, today, alloc_id)

    prune_orphans(orphans, opts)
    summary.append((inst, len(plan), sum(1 for p in plan if not p["reused"]),
                    hub_path, len(orphans)))


def main(argv):
    opts, positional = parse_args(argv)
    if not positional:
        print(__doc__)
        return 1

    source = positional[0]
    iso3, display = resolve_country(source)

    root = search_root(opts["dir"])
    folders = institute_folders(root, opts["inst"])
    managed = managed_institutes(folders)
    max_age = _otherbn_max_age_days()

    if opts["delete"]:
        if not PLUGIN:
            print("--delete yalnızca eklenti (plugin) modunda desteklenir.")
            return 1
        if not iso3:
            print("ISO-3 kodu çözülemedi.")
            return 1
        name = lu.iso3ToName(iso3.upper())
        for inst in sorted(managed):
            ensure_kind(inst)
            nb.delete_country_type(iso3, n_type_note(inst), inst, iso3.lower(),
                                   name if name != 1 else iso3.upper())
        return 0

    if opts["check"]:
        hub, days, src, title = otherbn_report_status(source, managed)
        if hub:
            fresh = 1 if (days is not None and days < max_age) else 0
            print(f"REPORT_EXISTS: {hub['path']}")
            print(f"REPORT_AGE_DAYS: {'' if days is None else days}")
            print(f"REPORT_AGE_SOURCE: {src}")
            print(f"REPORT_FRESH: {fresh}")
            print(f"REPORT_AGE_TEXT: {_age_text(title, days, src)}")
        return 0

    if not opts["force"] and not opts["headings"]:
        hub, days, src, title = otherbn_report_status(source, managed)
        if hub and days is not None and days < max_age:
            print(f"ATLANDI: {_age_text(title, days, src)} "
                  f"({max_age} günden yeni; yenilenmedi)")
            return 0

    if not iso3:
        print(f"ISO-3 kodu çözülemedi: {source}.")
        return 1
    country_name = display or (lu.iso3ToName(iso3.upper())
                              if lu.iso3ToName(iso3.upper()) != 1
                              else iso3.upper())
    tokens = country_tokens(iso3)

    if not folders:
        print(f"Klasör bulunamadı: {root}")
        return NO_DATA_CODE

    print(f"Country  : {country_name} ({iso3})")
    print(f"Root     : {root}")
    print(f"Mode     : {'plugin (notebox)' if PLUGIN else 'standalone'}")

    summary = []
    workdir = tempfile.mkdtemp(prefix="otherbn-")
    try:
        for folder_name, folder_path in folders:
            docs = documents_in(folder_path)
            if not docs:
                continue
            entries = []
            for path in docs:
                try:
                    blocks = read_doc(path, workdir)
                except Exception as exc:
                    print(f"UYARI okunamadı: {os.path.basename(path)} ({exc})")
                    continue
                text = " ".join(b["text"] for b in blocks)
                entries.append({
                    "path": path, "blocks": blocks,
                    "mtime": os.path.getmtime(path),
                    "bytes_hash": hashlib.sha256(
                        open(path, "rb").read()).hexdigest(),
                    "text_hash": hashlib.sha256(norm(text).encode()).hexdigest(),
                    "words": words_of(text), "text": text,
                })
            if not entries:
                continue
            canonicals, skipped = dedup_documents(
                entries, opts["threshold"], opts["dedup"])

            all_text = " ".join(e["text"] for e in canonicals)
            inst = infer_institute(folder_name, all_text, opts["inst"])
            if not inst:
                inst = ask_institute(folder_name)
            if not inst or inst in EXCLUDED_INSTITUTES:
                continue
            print(f"\n== {folder_name} -> {inst} "
                  f"({len(canonicals)} belge, {len(skipped)} kopya)")
            for sk in skipped:
                print(f"   (kopya atlandı) {os.path.basename(sk['path'])}")

            sections = []
            sources = []
            aliases = []
            kept_paths = set()
            for e in canonicals:
                secs = collect_country_sections(e["blocks"], tokens)
                if not secs:
                    continue
                kept_paths.add(e["path"])
                doc_slug = slug(os.path.splitext(
                    os.path.basename(e["path"]))[0]) or "doc"
                year = bib_year(os.path.basename(e["path"]))
                key = bib_key(inst, iso3, doc_slug, year)
                for sec in secs:
                    sections.append({"title": sec["title"], "body": sec["body"],
                                     "doc_slug": doc_slug, "bibkey": key})
                sources.append({"path": e["path"], "slug": doc_slug,
                                "rel": os.path.relpath(e["path"], OUT_DIR),
                                "title": f"{country_name} - "
                                         f"{INST_SHORT.get(inst, inst)}",
                                "year": year, "bibkey": key})
            for sk in skipped:
                if sk.get("duplicate_of") in kept_paths:
                    aliases.append({"name": os.path.basename(sk["path"]),
                                    "dup_of": sk["duplicate_of"]})

            # global section dedupe by title
            best = {}
            for sec in sections:
                k = norm(sec["title"])
                if k not in best or len(sec["body"]) > len(best[k]["body"]):
                    best[k] = sec
            sections = list(best.values())

            if not sections:
                print("   (bu ülke için ilgili bölüm yok)")
                continue
            for sec in sections:
                print(f"   # {sec['title']}")
            run_institute(iso3, country_name, inst, sections, sources,
                          aliases, opts, summary)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    if not summary:
        print("\nBu ülke için ilgili bilgi notu bulunamadı.")
        return NO_DATA_CODE

    print("\n=== Özet ===")
    for inst, total, new, hub_path, orph in summary:
        print(f"[OK] {inst}: {total} not ({new} yeni) "
              f"hub={os.path.basename(hub_path)}")
    if opts["headings"]:
        return 0
    print(f"INDEX: {summary[0][3]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
