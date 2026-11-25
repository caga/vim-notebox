#!/home/osman/.vim/plugged/vim-notebox/plugin/scripts/venv/bin/python3
# -*- coding: utf-8 -*-
"""Bir WorldBank gosterge notunun tablosunu sablon notundan yeniler.

Sablon notu `n_type` alaninda `şablon` gecen ve basligi
"Türkiye Son Ekonomik Gösterge Rakamları" olan nottur.  Her calismada yeniden
okunur; kullanici sablonu degistirdiginde tablo bir sonraki calistirmada
guncellenir.

Hedef not `obn indicatorReport` olmalidir.  Mevcut ulke degerleri tablodan
okunur; sablonun satirlari, Turkiye sutunu, basligi ve dipnotu uygulanir.
Ulke degerleri her zaman iki ondalik basamaga yuvarlanir.  Satirlar yil
yer tutucusundan bagimsiz (base label ile) eslesir; notta bulunan gercek
yil etiketleri korunur.  Yeni not olusturulmaz, yalnizca hedef notun
tablosu degistirilir.

Kullanim:
    ./wbTable.py 1792392619.md --box ~/countryNotes
    ./wbTable.py 1792392619 --box ~/countryNotes --stdout
    ./wbTable.py 1792392619 --template 1792067083

Secenekler:
    --box DIR       not kutusu (varsayilan: $NOTES_DIR veya cwd)
    --template ID   sablon notun id'si veya yolu
    --stdout        dosyaya yazmadan sonucu standart ciktiya bas
"""

import argparse
import datetime as dt
import os
import re
import sys
from decimal import Decimal, ROUND_HALF_UP

import _cli
import notebox as nb


TEMPLATE_TITLE = "Türkiye Son Ekonomik Gösterge Rakamları"
TEMPLATE_NTYPE = "şablon"


YEAR_PLACEHOLDER_RE = re.compile(r"\{year\d*\}", re.IGNORECASE)


def norm(value: str) -> str:
    """Normalise a table label for matching (Turkish-aware, punctuation-free)."""
    value = (value or "").replace("\\", "")
    value = value.replace("İ", "i").replace("I", "ı").lower()
    for source, target in (("ç", "c"), ("ğ", "g"), ("ı", "i"), ("ö", "o"),
                           ("ş", "s"), ("ü", "u"), ("â", "a"), ("î", "i"),
                           ("û", "u")):
        value = value.replace(source, target)
    return re.sub(r"[^a-z0-9]", "", value)


def base_label(label: str) -> str:
    """Row label without its trailing year placeholder or year.

    ``Nüfus ({year1})`` and ``Nüfus (2025)`` both become ``Nüfus``.
    Inner parentheticals such as ``GSYH (Kişi Başı $)`` are preserved.
    """
    value = YEAR_PLACEHOLDER_RE.sub("", label or "")
    value = re.sub(r"\s*\(\d{4}\)\s*$", "", value)
    value = re.sub(r"\s*\(\s*\)\s*$", "", value)
    return value.strip()


def split_frontmatter(text: str):
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return lines[1:i], lines[i + 1:]
    return None, lines


def cells(line: str):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_separator(line: str) -> bool:
    return "-" in line and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", line) is not None


def tables(lines):
    """Yield (start, end, headers, rows) for pipe tables in *lines*."""
    i = 0
    while i < len(lines) - 1:
        if lines[i].lstrip().startswith("|") and is_separator(lines[i + 1]):
            start = i
            headers = cells(lines[i])
            i += 2
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(cells(lines[i]))
                i += 1
            yield start, i, headers, rows
        else:
            i += 1


def find_template(box: str, template: str = ""):
    if template:
        path = os.path.abspath(os.path.expanduser(template))
        if not os.path.isfile(path):
            path = os.path.join(box, template if template.endswith(".md")
                                else f"{template}.md")
        if not os.path.isfile(path):
            return None
        return path

    best = None
    if os.path.isdir(box):
        for fname in sorted(os.listdir(box)):
            if not fname.lower().endswith(".md"):
                continue
            path = os.path.join(box, fname)
            info = nb.parse_front_matter(path)
            toks = [t.lower() for t in (info.get("n_type", "") or "").split()]
            if TEMPLATE_NTYPE.lower() not in toks:
                continue
            if norm(info.get("title", "")) != norm(TEMPLATE_TITLE):
                continue
            try:
                fid = int(info.get("id", "0"))
            except (TypeError, ValueError):
                fid = 0
            if best is None or fid > best[0]:
                best = (fid, path)
    return best[1] if best else None


def parse_template(path: str):
    text = open(path, encoding="utf-8").read()
    _, body_lines = split_frontmatter(text)
    body_text = "\n".join(body_lines)
    before, _ = nb.split_backrefs(body_text)
    lines = before

    found = None
    for start, end, headers, rows in tables(lines):
        if len(headers) < 3 or norm(headers[0]) != "gosterge":
            continue
        found = (start, end, headers, rows)
        break
    if not found:
        raise ValueError("şablon notunda gösterge tablosu bulunamadı")

    start, end, headers, rows = found
    template_rows = []
    for row in rows:
        if len(row) < 3:
            continue
        template_rows.append((row[0], row[2]))

    caption = ""
    footnotes = []
    i = end
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and lines[i].lstrip().startswith(":"):
        caption = lines[i].strip()
        i += 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    while i < len(lines) and lines[i].startswith("[^"):
        footnotes.append(lines[i].strip())
        i += 1

    return {
        "path": path,
        "headers": headers,
        "rows": template_rows,
        "caption": caption,
        "footnotes": footnotes,
    }


def find_indicator_table(body_lines):
    """Return the WB indicator table and its following caption/footnotes."""
    for start, end, headers, rows in tables(body_lines):
        if not headers or norm(headers[0]) != "gosterge":
            continue
        country = headers[1] if len(headers) >= 3 else ""
        values = {}
        for row in rows:
            if len(row) < 2:
                continue
            values[norm(base_label(row[0]))] = row[1]

        caption = ""
        footnotes = []
        i = end
        while i < len(body_lines) and not body_lines[i].strip():
            i += 1
        if i < len(body_lines) and body_lines[i].lstrip().startswith(":"):
            caption = body_lines[i].strip()
            i += 1
        while i < len(body_lines) and not body_lines[i].strip():
            i += 1
        while i < len(body_lines) and body_lines[i].startswith("[^"):
            footnotes.append(body_lines[i].strip())
            i += 1

        key_match = re.search(r"@([A-Za-z0-9][A-Za-z0-9_-]*)", caption)
        return {
            "start": start,
            "end": end,
            "tail_end": i,
            "headers": headers,
            "rows": rows,
            "country": country,
            "values": values,
            "caption": caption,
            "footnotes": footnotes,
            "key": key_match.group(1) if key_match else "",
        }
    return None


def format_value(_label: str, raw: str) -> str:
    """Round every numeric value to exactly two decimal places."""
    raw = (raw or "").strip()
    if not raw or raw == "veri yok":
        return raw or "veri yok"
    match = re.match(r"^(-?[0-9]+(?:\.[0-9]+)?)\s*([KMBT])?$", raw)
    if not match:
        return raw
    value = Decimal(match.group(1)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP)
    suffix = match.group(2) or ""
    return f"{value}{suffix}"


def build_comparison(template, country: str, values, key: str):
    headers = [template["headers"][0], country, template["headers"][2]]
    rows = []
    for label, turkey in template["rows"]:
        raw = values.get(norm(base_label(label)), "veri yok")
        rows.append([label, format_value(label, raw), turkey])

    widths = [len(cell) for cell in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def render(row):
        return "| " + " | ".join(
            row[i].ljust(widths[i]) for i in range(len(row))
        ) + " |"

    table = [render(headers),
             "| " + " | ".join("-" * widths[i] for i in range(len(headers))) + " |"]
    table.extend(render(row) for row in rows)

    caption = template["caption"]
    if key and caption:
        caption = re.sub(r"@[A-Za-z0-9][A-Za-z0-9_.-]*", f"@{key}",
                         caption, count=1)
    return table, caption, template["footnotes"]


def build_body(table, caption: str, footnotes):
    out = list(table)
    if caption:
        out.append(caption)
    if footnotes:
        out.append("")
        out.extend(footnotes)
    return "\n".join(out) + "\n"


def bib_key_from_info(info, box: str) -> str:
    value = (info.get("bibliography", "") or "").strip().strip('"\'')
    if not value:
        return ""
    path = value if os.path.isabs(value) else os.path.join(box, value)
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return ""
    match = re.search(r"@\w+\{([^,]+),", text)
    return match.group(1).strip() if match else ""


def set_modify(fm_lines, today: str):
    for i, line in enumerate(fm_lines):
        if re.match(r"^modify\s*:", line):
            fm_lines[i] = f"modify: {today}"
            return fm_lines
    fm_lines.append(f"modify: {today}")
    return fm_lines


def refresh(note_path: str, box: str, template_path: str, stdout=False) -> int:
    info = nb.parse_front_matter(note_path)
    tokens = [t.lower() for t in (info.get("n_type", "") or "").split()]
    if "obn" not in tokens or "indicatorreport" not in tokens:
        print("HATA wbTable: bu bir WorldBank gösterge notu değil")
        return 1

    text = open(note_path, encoding="utf-8").read()
    fm_lines, body_lines = split_frontmatter(text)
    body_text = "\n".join(body_lines)
    before, tail = nb.split_backrefs(body_text)
    before_lines = before

    parsed = find_indicator_table(before_lines)
    if not parsed:
        print("HATA wbTable: gösterge tablosu bulunamadı")
        return 1

    country = parsed["country"]
    if not country or country.startswith("{"):
        iso3, display, _ = nb.resolve_country(nb.clean(info.get("country", "")))
        country = display if iso3 else ""

    # The bibliography key is authoritative.  A caption previously generated
    # from the template may still carry the template's @wbApi.* token, so do
    # not prefer it over the note's own bib key.
    key = bib_key_from_info(info, box)
    if not key:
        match = re.search(r"(?m)^\s*@([A-Za-z0-9][A-Za-z0-9_-]*)\s*$",
                          body_text)
        key = match.group(1) if match else ""
    if not key:
        key = parsed["key"]
    template = parse_template(template_path)

    # Keep the year labels already present in the note.  A row newly added to
    # the şablon has no note label yet, so use its base label without the
    # {yearN} placeholder.  Wbtable never fetches, so it cannot invent a year.
    note_labels = {}
    for row in parsed.get("rows", []):
        if not row:
            continue
        row_label = row[0]
        row_key = norm(base_label(row_label))
        if not row_key:
            continue
        if YEAR_PLACEHOLDER_RE.search(row_label or ""):
            row_label = base_label(row_label)
        note_labels[row_key] = row_label

    display_rows = []
    for label, turkey in template["rows"]:
        row_key = norm(base_label(label))
        display_rows.append(
            (note_labels.get(row_key) or base_label(label), turkey))
    template = dict(template)
    template["rows"] = display_rows

    table, caption, footnotes = build_comparison(
        template, country, parsed["values"], key)

    new_before = before_lines[:parsed["start"]] + table
    if caption:
        new_before.append(caption)
    if footnotes:
        new_before.append("")
        new_before.extend(footnotes)

    suffix = before_lines[parsed["tail_end"]:]
    if suffix:
        if new_before and new_before[-1].strip() != "":
            new_before.append("")
        new_before.extend(suffix)

    today = dt.date.today().strftime("%d/%m/%y")
    if fm_lines is None:
        fm_lines = []
    fm_lines = set_modify(fm_lines, today)

    out = "---\n" + "\n".join(fm_lines) + "\n---\n\n"
    out += "\n".join(new_before).rstrip()
    if tail:
        out += "\n\n" + "\n".join(tail).strip("\n")
    out += "\n"

    if stdout:
        sys.stdout.write(out)
    else:
        nb.writeMdReport(note_path, out)

    print(f"WB: {note_path}")
    print(f"TEMPLATE: {template_path}")
    print(f"COUNTRY: {country}")
    return 0


def main(argv=None):
    box = _cli.init()
    box = os.path.abspath(os.path.expanduser(box))

    parser = argparse.ArgumentParser(
        description="WorldBank gösterge tablosunu şablon notundan yeniler")
    parser.add_argument("note", help="hedef .md yolu veya id")
    parser.add_argument("--template", default="",
                        help="şablon notun id'si veya yolu")
    parser.add_argument("--stdout", action="store_true",
                        help="dosyaya yazmadan sonucu yazdır")
    args = parser.parse_args(argv)

    note_path = os.path.abspath(os.path.expanduser(args.note))
    if not os.path.isfile(note_path):
        candidate = os.path.join(
            box, args.note if args.note.endswith(".md") else f"{args.note}.md")
        if os.path.isfile(candidate):
            note_path = candidate
    if not os.path.isfile(note_path):
        print(f"HATA wbTable: not bulunamadı: {args.note}")
        return 1

    template_path = find_template(box, args.template)
    if not template_path:
        print("HATA wbTable: şablon notu bulunamadı "
              f"({TEMPLATE_TITLE})")
        return 1

    return refresh(note_path, box, template_path, stdout=args.stdout)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        print(f"HATA wbTable: {type(exc).__name__}: {exc}")
        sys.exit(1)
