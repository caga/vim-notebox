#!/home/osman/.vim/plugged/vim-notebox/plugin/scripts/venv/bin/python3
# -*- coding: utf-8 -*-
"""Bir cvb / perm cvb notundan pandoc grid tablo CV notu uretir.

Kaynak not, vim-notebox not kutusundaki bir `<id>.md` dosyasidir ve
`n_type` alaninda `cvb` gecmelidir (`cvb` veya `perm cvb`).  Uretilen not
`n_type: obn cv` ile ayni kutunun kokune yazilir; `cv_source` alani kaynak
notun dosya adini tutar (orn. `1790086521.md`).  Kaynak nota dokunulmaz ve
uretilen notta ne `#BackReferences` bolumu ne de metin icinde kaynak
baglantisi olusturulmaz.

Ayni kaynak icin daha once uretilmis bir CV varsa yeni dosya acilmaz: mevcut
`obn cv` guncellenir, eski `cv` notu `obn cv` olarak devralinir.  CV notu
ulkenin OBN sayfasinda `## CV Notları` altina baglanir.

Kullanim:
    ./generateCv.py 1790086521.md --box ~/countryNotes
    ./generateCv.py 1790086521 --box ~/countryNotes
    ./generateCv.py "Enrico Palermo" --box ~/countryNotes
    ./generateCv.py NPL --all --box ~/countryNotes
    ./generateCv.py 1790086521 --box ~/countryNotes --stdout
    ./generateCv.py 1790086521 --image '![](data/img/x.png){ height=250px }'

Secenekler:
    --box DIR     not kutusu (varsayilan: $NOTES_DIR veya cwd)
    --output FILE cikti dosyasi (varsayilan: <box>/<yeni-id>.md)
    --id ID       cikti id'si (varsayilan: yeni zaman damgasi)
    --image LINE  fotograf hucresinin icerigi (kaynak nottaki satiri ezer)
    --stdout      dosyaya yazmadan tam notu standart ciktiya bas
    --force       var olan cikti dosyasinin uzerine yaz
    --no-update   iliskili CV varsa yalnizca yolunu bildir, yazma
    --all         verilen ulkenin tum perm cvb profillerini isle
"""

import argparse
import datetime as dt
import os
import re
import sys
import time
from collections import OrderedDict

import _cli

# --box/--notes-dir'i notebox import edilmeden once isle.
_BOX_EXPLICIT = any(
    a in ("--box", "--notes-dir")
    or a.startswith("--box=")
    or a.startswith("--notes-dir=")
    for a in sys.argv[1:]
)
BOX = _cli.init()

import notebox as nb  # noqa: E402


REF_RE = re.compile(r"\s*@[A-Za-z0-9][A-Za-z0-9_\-]*")
NAME_RE = re.compile(r"^#\s+(.*\S)\s*$")
IMAGE_RE = re.compile(r"^\s*!\[[^\]]*\]\(([^)]+)\)(?:\{[^}]*\})?\s*$")
BACKREF_RE = re.compile(r"^\s*#BackReferences\b")
HISTORY_HINTS = ("profesyonel", "geçmiş", "gecmis")
SUBTITLE_KEY = "__subtitle__"
TEXT_IMAGE = "Fotoğraf mevcut değil"

PREFERRED_FACT_ORDER = [
    "Göreve Başlama Tarihi",
    "Doğum Tarihi",
    "Medeni Durum",
    "Eğitim",
]

C1, C2, C3 = 52, 28, 29


def strip_refs(text: str) -> str:
    return REF_RE.sub("", text).strip()


def split_frontmatter(text: str):
    """(frontmatter_lines, body_lines); no frontmatter -> (None, all lines)."""
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return lines[1:i], lines[i + 1:]
    return None, lines


def strip_backrefs(lines):
    for i, line in enumerate(lines):
        if BACKREF_RE.match(line):
            return lines[:i]
    return lines


def field(lines, key: str) -> str:
    for line in lines or ():
        stripped = line.lstrip()
        if stripped.startswith(f"{key}:"):
            return stripped[len(key) + 1:].strip()
    return ""


def set_field(lines, key: str, value: str):
    """Replace a top-level ``key:`` line, or insert it at the top."""
    out, replaced = [], False
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith(f"{key}:"):
            indent = line[: len(line) - len(stripped)]
            out.append(f"{indent}{key}:" if value == ""
                       else f"{indent}{key}: {value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        insert_at = 0
        if key == "cv_source":
            for i, line in enumerate(out):
                if line.lstrip().startswith("n_type:"):
                    insert_at = i + 1
                    break
        out.insert(insert_at, f"{key}: {value}")
    return out


def _title_value(name: str) -> str:
    """Quote a title once; keep an already-quoted value untouched."""
    name = (name or "").strip()
    if len(name) >= 2 and name[0] == '"' and name[-1] == '"':
        return name
    return nb.yaml_title(name)


def render_frontmatter(lines) -> str:
    return "---\n" + "\n".join(lines) + "\n---\n\n"


def heading_name(lines) -> str:
    for line in lines:
        match = NAME_RE.match(line)
        if match:
            return strip_refs(match.group(1))
    return ""


def note_name(path: str) -> str:
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return ""
    _, body = split_frontmatter(text)
    return heading_name(body)


def resolve_source(arg: str, box: str):
    """Return (path, warning) or (None, error_message)."""
    path = os.path.abspath(os.path.expanduser(arg))
    if os.path.isfile(path):
        return path, ""
    # A bare file name can refer to a note inside --box even when the CLI is
    # run from another directory.
    if not os.path.isabs(arg):
        candidate = os.path.join(box, arg)
        if os.path.isfile(candidate):
            return candidate, ""

    if arg.isdigit():
        path = os.path.join(box, f"{arg}.md")
        if os.path.isfile(path):
            return path, ""
        return None, f"id bulunamadı: {arg}"

    want = nb.norm_name(arg)
    matches = []
    if os.path.isdir(box):
        for name in sorted(os.listdir(box)):
            if not name.lower().endswith(".md"):
                continue
            path = os.path.join(box, name)
            info = nb.parse_front_matter(path)
            tokens = [t.lower() for t in (info.get("n_type", "") or "").split()]
            if "cvb" not in tokens:
                continue
            heading = note_name(path)
            title = nb.clean(info.get("title", ""))
            nhead = nb.norm_name(heading)
            ntitle = nb.norm_name(title)
            if not want:
                continue
            if (want == nhead or want == ntitle
                    or (len(want) >= 3 and (want in nhead or nhead in want))):
                matches.append((path, heading, title))

    if not matches:
        return None, f"cvb/perm cvb notu bulunamadı: {arg}"
    if len(matches) > 1:
        print(f"UYARI birden fazla aday var ({arg}):")
        for path, heading, title in matches:
            print(f"  {os.path.basename(path)}  {heading or title}")
        return None, "adaylardan birini dosya yolu veya id ile belirtin"
    return matches[0][0], ""


def extract_image(body_lines, image_override: str, box: str):
    """Return (cell_text, warning)."""
    if image_override:
        return image_override, ""

    name_seen = False
    for line in body_lines:
        if not name_seen:
            if NAME_RE.match(line):
                name_seen = True
            continue
        if line.startswith("#"):
            break
        match = IMAGE_RE.match(line)
        if not match:
            continue
        target = match.group(1)
        local = target if os.path.isabs(target) else os.path.join(box, target)
        if os.path.isfile(local):
            return line.strip(), ""
        return TEXT_IMAGE, f"portre bulunamadı: {target}"

    return TEXT_IMAGE, "portre satırı bulunamadı"


def parse_profile(text: str):
    """Return (name, subtitle, facts, history_heading, history_items)."""
    name = ""
    sections: "OrderedDict[str, list[tuple[str, str]]]" = OrderedDict()
    current = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("### "):
            current = line[4:].strip()
            sections[current] = []
        elif line.startswith("## "):
            current = SUBTITLE_KEY
            sections[current] = []
        elif line.startswith("# "):
            name = strip_refs(line[2:])
        else:
            if current is None:
                continue
            if line.startswith("- "):
                sections[current].append(("bullet", strip_refs(line[2:])))
            else:
                sections[current].append(("text", strip_refs(line)))

    subtitle_items = sections.pop(SUBTITLE_KEY, [])
    subtitle = " ".join(v for _, v in subtitle_items if v).strip()

    history_heading = None
    for heading in sections:
        low = heading.lower()
        if any(hint in low for hint in HISTORY_HINTS):
            history_heading = heading
            break
    if history_heading is None and sections:
        history_heading = list(sections)[-1]

    history_items = []
    if history_heading:
        history_items = [v for _, v in sections.pop(history_heading) if v]

    def rank(heading: str) -> int:
        return (PREFERRED_FACT_ORDER.index(heading)
                if heading in PREFERRED_FACT_ORDER
                else len(PREFERRED_FACT_ORDER))

    facts = OrderedDict((h, sections[h]) for h in sorted(sections, key=rank))
    return name, subtitle, facts, history_heading, history_items


def wrap(text: str, width: int):
    words = text.split()
    if not words:
        return [""]
    lines, cur = [], ""
    for word in words:
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = word if not cur else f"{cur} {word}"
    if cur:
        lines.append(cur)
    return lines


class Grid:
    def __init__(self, c1: int, c2: int, c3: int):
        self.c1, self.c2, self.c3 = c1, c2, c3
        self.inner = c1 + c2 + c3 + 2

    def _pad(self, text: str, width: int) -> str:
        text = text[: max(width - 2, 0)]
        return " " + text + " " * max(width - 1 - len(text), 0)

    def row3(self, a: str, b: str, c: str) -> str:
        return ("|" + self._pad(a, self.c1) + "|" + self._pad(b, self.c2)
                + "|" + self._pad(c, self.c3) + "|")

    def row23(self, a: str, text: str) -> str:
        return ("|" + self._pad(a, self.c1) + "|"
                + self._pad(text, self.c2 + 1 + self.c3) + "|")

    def span(self, text: str) -> str:
        return "|" + self._pad(text, self.inner) + "|"

    def empty(self) -> str:
        return "|" + " " * self.inner + "|"

    def border(self, ch: str = "-") -> str:
        return "+" + ch * self.c1 + "+" + ch * self.c2 + "+" + ch * self.c3 + "+"

    def border_cont(self) -> str:
        return ("+" + " " * self.c1 + "+" + "-" * self.c2
                + "+" + "-" * self.c3 + "+")


def build_table(name, subtitle, facts, history_heading, history_items, image):
    c1 = max(C1, len(image) + 4)
    labels = [f"**{h}**" for h in facts
              if not any(kind == "bullet" for kind, _ in facts[h])]
    c2 = max(C2, max((len(x) for x in labels), default=0) + 2)
    c3 = C3
    grid = Grid(c1, c2, c3)

    out = [grid.border()]
    out.append(grid.span(name))
    for line in wrap(subtitle, grid.inner - 2):
        out.append(grid.span(line))
    out.append(grid.border("="))

    first = True
    for heading, items in facts.items():
        is_list = any(kind == "bullet" for kind, _ in items)
        if is_list:
            if not first:
                out.append(grid.border_cont())
            out.append(grid.row23("", f"**{heading}**"))
            out.append(grid.border_cont())
            for _, value in items:
                # Continuation lines get a two-space hanging indent; reserve
                # room for it so _pad() never truncates the last word.
                lines = wrap("- " + value, grid.c2 + 1 + grid.c3 - 4)
                out.append(grid.row23("", lines[0]))
                for extra in lines[1:]:
                    out.append(grid.row23("", "  " + extra))
        else:
            value = " ".join(v for _, v in items if v)
            value_lines = wrap(value, c3 - 2)
            if first:
                out.append(grid.row3(image, f"**{heading}**", value_lines[0]))
            else:
                out.append(grid.border_cont())
                out.append(grid.row3("", f"**{heading}**", value_lines[0]))
            for extra in value_lines[1:]:
                out.append(grid.row3("", "", extra))
        first = False

    out.append(grid.border())
    heading = history_heading or "Profesyonel Geçmiş:"
    out.append(grid.span(f"#### {heading}"))
    out.append(grid.empty())
    for item in history_items:
        lines = wrap("- " + item, grid.inner - 4)
        out.append(grid.span(lines[0]))
        for extra in lines[1:]:
            out.append(grid.span("  " + extra))
        out.append(grid.empty())
    if out[-1] == grid.empty():
        out.pop()
    out.append(grid.border())
    return "\n".join(out) + "\n"


def next_id(box: str) -> str:
    nid = int(time.time())
    while os.path.exists(os.path.join(box, f"{nid}.md")):
        nid += 1
    return str(nid)


def source_key(source: str) -> str:
    """Stable source reference stored in YAML: the source file name."""
    return os.path.basename(source)


def _abs_bib(box: str, value: str) -> str:
    value = (value or "").strip().strip('"\'')
    if not value:
        return ""
    path = value if os.path.isabs(value) else os.path.join(box, value)
    return os.path.realpath(path)


def _has_source_backref(path: str, source: str) -> bool:
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return False
    _, tail = nb.split_backrefs(text)
    base = os.path.basename(source)
    return any(base in line for line in tail)


def find_existing_cv(box: str, source: str, info, name: str):
    """Return (path, kind) for a related CV, or None.

    kind == "auto"   -> n_type: obn cv with cv_source
    kind == "legacy" -> n_type: cv matched by bibliography/title/backrefs
    """
    sid = source_key(source)
    sid_stem = os.path.splitext(sid)[0]
    src_bib = _abs_bib(box, nb.clean(info.get("bibliography", "")))
    want = nb.norm_name(name)
    candidates = []

    for fname in sorted(os.listdir(box)):
        if not fname.lower().endswith(".md"):
            continue
        path = os.path.join(box, fname)
        if os.path.abspath(path) == os.path.abspath(source):
            continue
        finfo = nb.parse_front_matter(path)
        tokens = [t.lower() for t in (finfo.get("n_type", "") or "").split()]
        if "cv" not in tokens or "cvb" in tokens:
            continue
        if "hub" in tokens or "dizin" in tokens:
            continue

        try:
            fid = int(finfo.get("id", "0"))
        except (TypeError, ValueError):
            fid = 0

        cand_sid = (finfo.get("cv_source", "") or "").strip().strip('"\'')
        # Accept both the current filename form and the old id-only form.
        if cand_sid in (sid, sid_stem):
            candidates.append((fid, path, "auto"))
            continue
        if cand_sid:
            continue

        signals = 0
        cand_bib = _abs_bib(box, finfo.get("bibliography", ""))
        if src_bib and cand_bib == src_bib:
            signals += 1
        cand_title = nb.norm_name(nb.clean(finfo.get("title", "")))
        if want and cand_title and (want == cand_title
                                    or want in cand_title
                                    or cand_title in want):
            signals += 1
        if _has_source_backref(path, source):
            signals += 1
        if signals >= 2:
            candidates.append((fid, path, "legacy"))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    auto = [item for item in candidates if item[2] == "auto"]
    chosen = auto[0] if auto else candidates[0]
    if len(auto) > 1:
        print(f"UYARI birden fazla otomatik CV var; en yenisi kullanılıyor: "
              f"{os.path.basename(chosen[1])}")
    elif not auto and len(candidates) > 1:
        print(f"UYARI birden fazla eski CV adayı var; en yenisi kullanılıyor: "
              f"{os.path.basename(chosen[1])}")
    return chosen[1], chosen[2]


def generate_one(source: str, box: str, image_override: str = "",
                 new_id: str = "", output: str = "", stdout: bool = False,
                 force: bool = False, no_update: bool = False) -> int:
    warnings = []
    info = nb.parse_front_matter(source)
    tokens = [t.lower() for t in (info.get("n_type", "") or "").split()]
    if "cvb" not in tokens:
        print("HATA generateCv: bu standart bir cv bilgi sayfası değil")
        print(f"  kaynak: {source}")
        return 1

    try:
        text = open(source, encoding="utf-8").read()
    except OSError as exc:
        print(f"HATA generateCv: kaynak okunamadı: {exc}")
        return 1

    fm_lines, body_lines = split_frontmatter(text)
    body_lines = strip_backrefs(body_lines)

    name, subtitle, facts, history_heading, history_items = \
        parse_profile("\n".join(body_lines))
    if not name:
        name = re.sub(r"\s+CV\s+Bilgiler\s*$", "",
                      nb.clean(info.get("title", "")), flags=re.I).strip()
    if not name:
        name = os.path.splitext(os.path.basename(source))[0]

    image, image_warning = extract_image(body_lines, image_override, box)
    if image_warning:
        warnings.append(image_warning)

    sid = source_key(source)
    existing = find_existing_cv(box, source, info, name)
    today = dt.date.today().strftime("%d/%m/%y")

    if existing:
        out_path, kind = existing
        old_fm, _ = split_frontmatter(open(out_path, encoding="utf-8").read())
        old_id = field(old_fm, "id").strip('"\'') or \
            os.path.splitext(os.path.basename(out_path))[0]
        old_date = field(old_fm, "date").strip('"\'') or today
        if no_update:
            print(f"CV: {out_path}")
            print(f"ID: {old_id}")
            print(f"SOURCE: {source}")
            print(f"STATUS: MEVCUT ({kind})")
            return 0
        if new_id or output:
            print(f"HATA generateCv: ilişkili CV zaten var: {out_path}")
            print("      Güncellemek için --id/--output vermeyin; "
                  "açmak için --no-update kullanın.")
            return 1
        new_id_value = old_id
        date = old_date
        modify = today
        status = "ADOPTED" if kind == "legacy" else "UPDATED"
        if kind == "legacy":
            print(f"ADOPT: {out_path} (n_type: cv -> obn cv)")
    else:
        new_id_value = str(new_id) if new_id else next_id(box)
        out_path = output or os.path.join(box, f"{new_id_value}.md")
        out_path = os.path.abspath(os.path.expanduser(out_path))
        if os.path.exists(out_path) and not force:
            print(f"HATA generateCv: çıktı zaten var: {out_path} (--force)")
            return 1
        date = today
        modify = ""
        status = "CREATED"

    if fm_lines is None:
        author = nb.clean(info.get("author", "")) or "generateCv"
        bib = nb.clean(info.get("bibliography", ""))
        fm_lines = [
            f"id: {new_id_value}",
            f"author: {author}",
            f"title: {_title_value(name)}",
            f"date: {date}",
            f"modify: {modify}" if modify else "modify:",
            f"country: {nb.clean(info.get('country', ''))}",
            "institude: ",
            "n_type: obn cv",
            f"cv_source: {sid}",
            "keywords:",
            f"bibliography: {bib}",
            f"citation-style: {nb.CITATION_STYLE}",
            'toc-title: "İçindekiler"',
            'tableTitle: "Tablo"',
            'lotTitle: "Tablolar"',
            'reference-section-title: "Kaynakça"',
            'figureTitle: "Şekil"',
            "colorlinks: true",
        ]
    else:
        fm_lines = set_field(fm_lines, "id", new_id_value)
        fm_lines = set_field(fm_lines, "title", _title_value(name))
        fm_lines = set_field(fm_lines, "date", date)
        fm_lines = set_field(fm_lines, "modify", modify)
        fm_lines = set_field(fm_lines, "n_type", "obn cv")
        fm_lines = set_field(fm_lines, "cv_source", sid)

    bib_value = field(fm_lines, "bibliography")
    if bib_value:
        bib_abs = (bib_value if os.path.isabs(bib_value)
                   else os.path.join(box, bib_value))
        if not os.path.isfile(bib_abs):
            warnings.append(f"bibliyografya bulunamadı: {bib_value}")
    else:
        warnings.append("bibliyografya alanı boş")

    table = build_table(name, subtitle, facts, history_heading, history_items,
                        image)
    # No #BackReferences and no visible source link: the only provenance is
    # cv_source in the YAML header.  :Writeback can add real backrefs later.
    content = render_frontmatter(fm_lines) + table

    if stdout:
        for warning in warnings:
            print(f"UYARI: {warning}", file=sys.stderr)
        sys.stdout.write(content)
        return 0

    try:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(content)
    except OSError as exc:
        print(f"HATA generateCv: çıktı yazılamadı: {exc}")
        return 1

    country = nb.clean(info.get("country", "")).strip('"\'')
    out_dir = os.path.dirname(out_path) or box
    if country:
        if os.path.abspath(out_dir) != os.path.abspath(box):
            warnings.append("OBN bağlantısı atlandı: çıktı kutu dışında")
        else:
            iso3, display, country_field = nb.resolve_country(country)
            if iso3:
                nb.update_country_hub(iso3, "cv", out_path, name,
                                      display=display,
                                      country_field=country_field)
            else:
                warnings.append("OBN bağlantısı atlandı: ülke çözülemedi")
    else:
        warnings.append("OBN bağlantısı atlandı: country alanı boş")

    for warning in warnings:
        print(f"UYARI: {warning}")
    print(f"CV: {out_path}")
    print(f"ID: {new_id_value}")
    print(f"SOURCE: {source}")
    print(f"STATUS: {status}")
    return 0


def generate_all(country: str, box: str, args) -> int:
    iso3, display, country_field = nb.resolve_country(country)
    paths = nb.country_note_paths(country_field, display, ("perm cvb", "cvb"))
    if not paths:
        print(f"ATLANDI: {country} için perm cvb profili yok")
        return 0

    rc = 0
    count = 0
    for source in sorted(paths):
        print(f"=== CV kaynağı: {os.path.basename(source)} ===")
        code = generate_one(source, box, image_override=args.image,
                            no_update=args.no_update)
        if code == 0:
            count += 1
        else:
            rc = 1
    print(f"CV_COUNT: {count}")
    return rc


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="cvb/perm cvb notundan grid tablo CV notu uretir")
    parser.add_argument("source", nargs="?",
                        help="kaynak .md yolu, id, kişi adı veya --all ile ülke")
    parser.add_argument("--output", help="çıktı dosyası")
    parser.add_argument("--id", dest="new_id", help="çıktı id'si")
    parser.add_argument("--image", default="",
                        help="fotoğraf hücresi içeriği (kaynak satırı ezer)")
    parser.add_argument("--stdout", action="store_true",
                        help="dosyaya yazmadan tam notu yazdır")
    parser.add_argument("--force", action="store_true",
                        help="var olan çıktı dosyasının üzerine yaz")
    parser.add_argument("--no-update", action="store_true",
                        help="ilişkili CV varsa yalnızca yolunu bildir")
    parser.add_argument("--all", action="store_true",
                        help="verilen ülkenin tüm perm cvb profillerini işle")
    args = parser.parse_args(argv)

    if not args.source:
        print("HATA generateCv: kaynak not veya ülke belirtilmedi")
        return 1

    base_box = os.path.abspath(os.path.expanduser(BOX))
    if not os.path.isdir(base_box):
        print(f"HATA generateCv: not kutusu bulunamadı: {base_box}")
        return 1
    os.environ["NOTES_DIR"] = base_box

    if args.all:
        if args.output or args.new_id or args.stdout:
            print("HATA generateCv: --all ile --output/--id/--stdout kullanılamaz")
            return 1
        return generate_all(args.source, base_box, args)

    try:
        source, err = resolve_source(args.source, base_box)
    except Exception as exc:
        print(f"HATA generateCv: {exc}")
        return 1
    if not source:
        print(f"HATA generateCv: {err}")
        return 1

    box = os.path.dirname(source) if not _BOX_EXPLICIT else base_box
    if not os.path.isdir(box):
        print(f"HATA generateCv: not kutusu bulunamadı: {box}")
        return 1
    os.environ["NOTES_DIR"] = box

    return generate_one(source, box, image_override=args.image,
                        new_id=args.new_id or "", output=args.output or "",
                        stdout=args.stdout, force=args.force,
                        no_update=args.no_update)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        print(f"HATA generateCv: {type(exc).__name__}: {exc}")
        sys.exit(1)
