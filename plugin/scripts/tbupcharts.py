#!/usr/bin/env python3
"""Chart reconstruction helpers for getTbupNotes.py.

The Trade Ministry country profiles draw their trade charts as images with the
labels as real PDF text.  pymupdf4llm therefore emits a single
``<!-- Start of picture text -->`` block per chart with the labels in raw
page order, which is unreadable.  This module rebuilds the data from the PDF
geometry:

* every chart is wrapped in a large stroked rectangle (the chart frame);
* every legend entry has a small (<=10 px) colour-swatch image;
* bars are small images, so each printed value can be matched to its bar.

Three chart families occur in the profiles:

* ``hbar``  – "Başlıca Ürün Grupları" (one bar per product group)
* ``vbar``  – "Dış Ticaret Göstergeleri" / "Türkiye ile Ticaret"
              (four bars per year: İhracat, İthalat, Hacim, Denge)
* ``pie``   – "Ülkelere Göre İhracat/İthalat"

The reconstructed data is rendered as a markdown table and as a mermaid
diagram.  EK-1…EK-6 tables are parsed as well; the country EK tables are the
authoritative source for the country pies (EK-3/EK-4), and the product EK
tables are used for cross-checks.  The "Detaylı tablo için tıklayınız" GOTO
links below the charts are used to resolve the matching EK table; when a PDF
has no such links (e.g. Mozambique), the chart title is used as a fallback.

All functions are intentionally dependency-free apart from PyMuPDF so the
module can be used by getTbupNotes.py both in plugin and standalone mode.
"""

from __future__ import annotations

import json
import math
import os
import re

import pymupdf


PICTURE_RE = re.compile(
    r"<!--\s*Start of picture text\s*-->.*?<!--\s*End of picture text\s*-->",
    re.S,
)
NUM_RE = re.compile(r"^-?\d[\d.,]*$")
YEAR_RE = re.compile(r"^(?:19|20)\d{2}$")
UNIT_RE = re.compile(r"\((?:[^()]*?)\b(milyar|milyon|bin|1000)\s*dolar", re.I)
EK_TITLE_RE = re.compile(r"\bEK-(\d+)\s*:\s*(.+)", re.I)
EK_LINK_TEXT_RE = re.compile(
    r"Detaylı\s+tablo\s+için\s+tıklayınız", re.I)
EK_LINK_PLACEHOLDER_RE = re.compile(r"\{\{tbup-ek-link:([^}]*)\}\}")
SERIES_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
BAR_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b",
    "#e377c2", "#7f7f7f", "#bcbd22", "#17becf", "#aec7e8", "#ffbb78",
]
BAR_TEXT_COLORS = [
    "#ffffff", "#000000", "#ffffff", "#ffffff", "#ffffff", "#ffffff",
    "#000000", "#ffffff", "#000000", "#000000", "#000000", "#000000",
]

TABLE_BLOCK_RE = re.compile(r"(?m)(?:^\|.*\|\s*$\n?)+")


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _norm(s):
    table = str.maketrans({
        "İ": "i", "I": "i", "ı": "i", "Ş": "s", "ş": "s",
        "Ğ": "g", "ğ": "g", "Ü": "u", "ü": "u",
        "Ö": "o", "ö": "o", "Ç": "c", "ç": "c",
    })
    return re.sub(r"[^a-z0-9]", "", (s or "").translate(table).lower())


def _clean(s):
    s = (s or "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


def _inside(frame, bbox):
    x0, y0, x1, y1 = bbox
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return frame.x0 <= cx <= frame.x1 and frame.y0 <= cy <= frame.y1


def _to_float(text):
    """Turkish/English number string -> float."""
    s = (text or "").strip().replace("\u2212", "-").replace("−", "-")
    s = s.replace(" ", "")
    if not s:
        return None
    has_dot, has_comma = "." in s, "," in s
    if has_dot and has_comma:
        s = s.replace(".", "").replace(",", ".")
    elif has_comma:
        if re.fullmatch(r"-?\d{1,3}(,\d{3})+", s):
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    elif has_dot and re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def _fmt_tr(v):
    if v is None:
        return ""
    if abs(v - round(v)) < 0.05:
        return f"{int(round(v)):,}".replace(",", ".")
    text = f"{v:.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _num_text(v):
    if abs(v - round(v)) < 1e-6:
        return str(int(round(v)))
    return f"{v:g}"


def _fmt_m(v):
    if v is None:
        return "0"
    text = f"{v:.4f}".rstrip("0").rstrip(".")
    return text or "0"


def _fmt_pct(v):
    if v is None:
        return ""
    if v >= 1:
        text = f"{v:.1f}"
    else:
        text = f"{v:.2f}"
    return text.rstrip("0").rstrip(".").replace(".", ",")


def _mq(s):
    """Quote a string for mermaid."""
    return (s or "").replace('"', "'").replace("\n", " ").strip()


def _alt(s):
    return (s or "").replace("[", "(").replace("]", ")").replace("\n", " ")


def _unit_from_title(title):
    m = UNIT_RE.search(title or "")
    if not m:
        return ""
    word = m.group(1).lower()
    if word == "1000":
        word = "bin"
    return f"{word} dolar"


def _unit_factor(unit):
    if unit.startswith("milyar"):
        return 1e9
    if unit.startswith("milyon"):
        return 1e6
    if unit.startswith("bin"):
        return 1e3
    return 1.0


def _ek_unit_factor(title):
    """Unit multiplier of an EK table, in dollars (EK tables use bin/1 000)."""
    text = _norm(title)
    if "milyar" in text:
        return 1e9
    if "milyon" in text:
        return 1e6
    if "bin" in text or "1000" in text:
        return 1e3
    return 1.0


def _convert_raw(value, unit):
    return value / _unit_factor(unit)


# ---------------------------------------------------------------------------
# geometry extraction
# ---------------------------------------------------------------------------

def chart_frames(page):
    """Outermost large rectangles that wrap a chart, top-to-bottom."""
    candidates = {}
    for drawing in page.get_drawings():
        rect = drawing["rect"]
        if (rect.width > 250 and rect.height > 100
                and rect.width * rect.height
                < page.rect.width * page.rect.height * 0.6):
            key = (round(rect.x0, 1), round(rect.y0, 1),
                   round(rect.x1, 1), round(rect.y1, 1))
            candidates[key] = rect
    rects = list(candidates.values())
    result = []
    for rect in rects:
        if any(other is not rect and other.contains(rect)
               and other.get_area() > rect.get_area() * 1.05
               for other in rects):
            continue
        result.append(rect)
    result.sort(key=lambda r: (r.y0, r.x0))
    return result


def _lines(page, frame):
    out = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            text = _clean(" ".join(span["text"] for span in line["spans"]))
            if not text:
                continue
            x0, y0, x1, y1 = line["bbox"]
            if not _inside(frame, (x0, y0, x1, y1)):
                continue
            out.append({
                "t": text, "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                "cx": (x0 + x1) / 2, "cy": (y0 + y1) / 2,
                "size": max(span["size"] for span in line["spans"]),
            })
    out.sort(key=lambda line: (round(line["y0"]), line["x0"]))
    return out


def _words(page, frame):
    out = []
    for word in page.get_text("words"):
        x0, y0, x1, y1, text = word[0], word[1], word[2], word[3], word[4]
        if not _inside(frame, (x0, y0, x1, y1)):
            continue
        out.append({
            "t": text, "x0": x0, "y0": y0, "x1": x1, "y1": y1,
            "cx": (x0 + x1) / 2, "cy": (y0 + y1) / 2,
        })
    return out


def _swatches(page, frame):
    out = []
    for info in page.get_image_info():
        x0, y0, x1, y1 = info["bbox"]
        if (x1 - x0) <= 10 and (y1 - y0) <= 10 and _inside(frame, info["bbox"]):
            out.append((x0, y0, x1, y1))
    return out


def _title_lines(lines, frame):
    top = [line for line in lines
           if line["cy"] < frame.y0 + frame.height * 0.30]
    if not top:
        return []
    biggest = max(line["size"] for line in top)
    candidates = [line for line in top if line["size"] >= biggest - 0.4]
    candidates.sort(key=lambda line: (line["y0"], line["x0"]))
    picked = [candidates[0]]
    for line in candidates[1:]:
        if line["y0"] - picked[-1]["y1"] < 18:
            picked.append(line)
        else:
            break
    return picked


def _year_row(words):
    rows = {}
    for word in words:
        if YEAR_RE.match(word["t"]):
            rows.setdefault(round(word["y0"]), []).append(word)
    if not rows:
        return []
    best = max(rows.values(), key=len)
    if len(best) < 3 or len({word["t"] for word in best}) < 3:
        return []
    return sorted(best, key=lambda word: word["x0"])


def _bar_geometry(page, frame):
    """Bar clusters with x-centre and top/bottom y (3-D bars have several
    overlapping images)."""
    swatch_keys = {
        (round(s[0], 1), round(s[1], 1), round(s[2], 1), round(s[3], 1))
        for s in _swatches(page, frame)
    }
    raw = []
    for info in page.get_image_info():
        x0, y0, x1, y1 = info["bbox"]
        width, height = x1 - x0, y1 - y0
        key = (round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1))
        if key in swatch_keys:
            continue
        if width >= 6 and height >= 4 and _inside(frame, info["bbox"]):
            raw.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1,
                        "cx": (x0 + x1) / 2})
    raw.sort(key=lambda bar: bar["cx"])
    clusters = []
    for bar in raw:
        if clusters and bar["cx"] - clusters[-1][-1]["cx"] <= 6:
            clusters[-1].append(bar)
        else:
            clusters.append([bar])
    result = []
    for cluster in clusters:
        result.append({
            "cx": sum(bar["cx"] for bar in cluster) / len(cluster),
            "top": min(bar["y0"] for bar in cluster),
            "bottom": max(bar["y1"] for bar in cluster),
        })
    return result


def _axis_scale(words, frame):
    """Fit value = a*y + b from the y-axis tick labels."""
    ticks = []
    for word in words:
        if word["x1"] < frame.x0 + 60 and NUM_RE.match(word["t"]):
            value = _to_float(word["t"])
            if value is not None:
                ticks.append((word["cy"], value))
    if len(ticks) < 2:
        return None
    n = len(ticks)
    sy = sum(y for y, _v in ticks)
    sv = sum(v for _y, v in ticks)
    syy = sum(y * y for y, _v in ticks)
    syv = sum(y * v for y, v in ticks)
    denominator = n * syy - sy * sy
    if abs(denominator) < 1e-9:
        return None
    a = (n * syv - sy * sv) / denominator
    b = (sv - a * sy) / n
    return a, b


def _numeric_spans(page, frame):
    out = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                text = _clean(span["text"])
                digits = text.replace(" ", "")
                if not digits or not re.fullmatch(r"\d[\d.,]*", digits):
                    continue
                x0, y0, x1, y1 = span["bbox"]
                if not _inside(frame, span["bbox"]):
                    continue
                out.append({"t": digits, "x0": x0, "y0": y0,
                            "x1": x1, "y1": y1})
    return out


def _split_value_string(digits, estimates):
    """Split a concatenated digit string across bars using bar heights."""
    count = len(estimates)
    length = len(digits)
    if count < 2 or length < count:
        return None
    inf = float("inf")
    dp = [[inf] * (count + 1) for _ in range(length + 1)]
    back = [[None] * (count + 1) for _ in range(length + 1)]
    dp[0][0] = 0.0
    for part in range(1, count + 1):
        for end in range(part, length - (count - part) + 1):
            for start in range(part - 1, end):
                if dp[start][part - 1] == inf:
                    continue
                chunk = digits[start:end]
                value = float(chunk)
                estimate = estimates[part - 1]
                cost = abs(value - estimate) / max(abs(estimate), 1.0)
                if cost > 0.6:
                    continue
                total = dp[start][part - 1] + cost
                if total < dp[end][part]:
                    dp[end][part] = total
                    back[end][part] = (start, chunk)
    if dp[length][count] == inf:
        return None
    chunks = []
    end, part = length, count
    while part > 0:
        start, chunk = back[end][part]
        chunks.append(chunk)
        end, part = start, part - 1
    return list(reversed(chunks))


def _values_with_spans(page, frame, bars, words, *, skip_y=None,
                       legend_y=None):
    values = _values_for_bars(words, bars, skip_y=skip_y,
                              legend_y=legend_y)
    scale = _axis_scale(words, frame)
    if not scale:
        return values
    a, b = scale
    for span in _numeric_spans(page, frame):
        if skip_y is not None and abs(span["y0"] - skip_y) <= 4:
            continue
        if legend_y is not None and span["y0"] >= legend_y - 4:
            continue
        covered = [i for i, bar in enumerate(bars)
                   if span["x0"] - 2 <= bar["cx"] <= span["x1"] + 2]
        if not covered:
            continue
        if len(covered) == 1:
            index = covered[0]
            if index not in values:
                values[index] = span["t"]
            continue
        digits = re.sub(r"[^\d]", "", span["t"])
        if len(digits) < len(covered):
            continue
        estimates = [max(0.0, a * bars[i]["top"] + b) for i in covered]
        chunks = _split_value_string(digits, estimates)
        if not chunks:
            continue
        for index, chunk in zip(covered, chunks):
            values[index] = chunk
    return values


def _legend_labels(words, swatches, vertical_column):
    ordered = sorted(swatches,
                     key=(lambda s: (s[1], s[0])) if vertical_column
                     else (lambda s: (s[0], s[1])))
    labels = []
    for i, swatch in enumerate(ordered):
        x0, y0, x1, y1 = swatch
        if vertical_column:
            y_lo = y0 - 3
            y_hi = (ordered[i + 1][1] - 3
                    if i + 1 < len(ordered) else y1 + 120)
            x_hi = None
        else:
            y_lo, y_hi = y0 - 4, y1 + 4
            x_hi = (ordered[i + 1][0] - 2
                    if i + 1 < len(ordered) else x1 + 220)
        picked = [word for word in words
                  if word["x0"] >= x1 - 1
                  and (x_hi is None or word["x0"] < x_hi)
                  and y_lo <= (word["y0"] + word["y1"]) / 2 <= y_hi]
        picked.sort(key=lambda word: (round(word["y0"]), word["x0"]))
        labels.append(_clean(" ".join(word["t"] for word in picked)))
    return labels


def _values_for_bars(words, bars, *, skip_y=None, legend_y=None):
    """Map bar index -> printed value using both x and y proximity.

    Value labels sit just above a bar (positive values) or just below it
    (negative values), and are occasionally shifted a few pixels sideways to
    avoid the neighbouring bar.  Matching only on x therefore picks the wrong
    bar in some charts.
    """
    found = {}
    for word in words:
        if not NUM_RE.match(word["t"]):
            continue
        if skip_y is not None and abs(word["y0"] - skip_y) <= 4:
            continue
        if legend_y is not None and word["y0"] >= legend_y - 4:
            continue
        best = None
        for index, bar in enumerate(bars):
            dx = abs(word["cx"] - bar["cx"])
            dy = min(abs(word["y1"] - bar["top"]),
                     abs(word["y0"] - bar["bottom"]))
            if dx > 14 or dy > 22:
                continue
            score = dx + 0.8 * dy
            if best is None or score < best[0]:
                best = (score, index)
        if best:
            index = best[1]
            if index not in found or best[0] < found[index][0]:
                found[index] = (best[0], word["t"])
    return {index: value for index, (_score, value) in found.items()}


def _chart_kind(lines, words, swatches, frame):
    if len(swatches) >= 8:
        xs = {round((s[0] + s[2]) / 2) for s in swatches}
        ys = {round((s[1] + s[3]) / 2) for s in swatches}
        if len(xs) >= 3 and len(ys) >= 3:
            return "pie"
        if len(ys) == 1:
            return "vbar"
        if len(xs) == 1:
            return "hbar"
    if _year_row(words):
        return "vbar"
    if any(word["t"].startswith("%") for word in words):
        return "pie"
    return "hbar"


# ---------------------------------------------------------------------------
# EK tables
# ---------------------------------------------------------------------------

def _cell(value):
    text = _clean(value or "")
    text = (text.replace("&lt;br&gt;", "<br>")
                .replace("&amp;#45;", "-")
                .replace("&#45;", "-")
                .replace("&amp;", "&")
                .replace("**", "")
                .replace("_", ""))
    text = text.replace("|", "\\|")
    return text


def _ek_title_above(page, bbox):
    top = bbox[1]
    matches = []
    for block in page.get_text("blocks"):
        text = block[4] or ""
        found = EK_TITLE_RE.search(text)
        if found and block[3] <= top + 2:
            matches.append((block[3], found.group(1), _clean(found.group(2))))
    if not matches:
        return None, None
    _bottom, number, title = max(matches, key=lambda item: item[0])
    return number, title


def _ek_key(title):
    text = _norm(title)
    if "ihracat" in text:
        direction = "export"
    elif "ithalat" in text:
        direction = "import"
    else:
        return None
    kind = "countries" if "ulkelere" in text else "products"
    prefix = "tr_" if "turkiye" in text else ""
    return f"{prefix}{kind}_{direction}"


def ek_key_for_title(title):
    """Return the EK table family key for an EK heading title."""
    return _ek_key(title)


def _expected_product_key(title):
    text = _norm(title)
    if "ihracat" in text:
        direction = "export"
    elif "ithalat" in text:
        direction = "import"
    else:
        return None
    prefix = "tr_" if "turkiye" in text else ""
    return f"{prefix}products_{direction}"


def _ek_rows(table):
    lines = [line for line in table.to_markdown(clean=True).splitlines()
             if line.startswith("|")]
    if len(lines) < 3:
        return None

    def cells(line):
        return [_cell(cell) for cell in line.split("|")[1:-1]]

    header = cells(lines[0])
    index_2025 = None
    index_name = None
    for i, text in enumerate(header):
        key = _norm(text)
        if key == "2025" or key.startswith("2025"):
            index_2025 = i
        if "ÜRÜNLER" in text.upper() or "ÜLKELER" in text.upper():
            index_name = i
    if index_2025 is None:
        return None
    if index_name is None:
        index_name = 1 if len(header) > 1 else 0

    data = []
    total = None
    extracted = table.extract() or []
    names_by_value = {}
    for raw_row in extracted[1:]:
        row = [_cell(cell) for cell in raw_row]
        if index_2025 >= len(row) or index_name >= len(row):
            continue
        value = _to_float(row[index_2025])
        name = row[index_name]
        if value is not None and name:
            names_by_value.setdefault(round(value, 2), name)
    for line in lines[2:]:
        row = cells(line)
        joined = " ".join(row[:2]).upper()
        if "TOPLAM" in joined:
            total = _to_float(row[index_2025]) if index_2025 < len(row) else 0
            continue
        name = row[index_name] if index_name < len(row) else ""
        value = _to_float(row[index_2025]) if index_2025 < len(row) else None
        if not name and value is not None:
            name = names_by_value.get(round(value, 2), "")
        if not name:
            name = row[0] if row else ""
        if name and value is not None:
            data.append((name.replace("<br>", " "), value))
    if not data:
        return None
    return {"header": header, "rows": data, "total": total or 0}


def parse_ek_tables(doc):
    """Return {'countries_export': {...}, ...} from the EK pages."""
    result = {}
    for page in doc:
        if not EK_TITLE_RE.search(page.get_text()):
            continue
        try:
            tables = page.find_tables(strategy="lines_strict").tables
        except Exception:
            continue
        for table in tables:
            _number, title = _ek_title_above(page, table.bbox)
            if not title:
                continue
            key = _ek_key(title)
            if not key:
                continue
            parsed = _ek_rows(table)
            if parsed:
                parsed["title"] = title
                parsed["unit_factor"] = _ek_unit_factor(title)
                parsed["page"] = page.number
                parsed["bbox"] = tuple(table.bbox)
                result[key] = parsed
    return result


def table_to_markdown(table):
    """Clean pipe table from a PyMuPDF table (fixes merged TOPLAM cells)."""
    raw = table.to_markdown(clean=True)
    try:
        extracted = table.extract() or []
    except Exception:
        extracted = []
    header = [_cell(cell) for cell in extracted[0]] if extracted else []
    out = []
    for index, line in enumerate(raw.splitlines()):
        if not line.startswith("|"):
            out.append(line)
            continue
        cells = line.split("|")[1:-1]
        if index == 0 and header and len(header) == len(cells):
            cells = header
        separator = all(re.fullmatch(r":?-+:?", cell.strip())
                        for cell in cells)
        first = _cell(cells[0]) if cells else ""
        if first and not separator:
            for i in range(1, len(cells)):
                if _cell(cells[i]) == first:
                    cells[i] = ""
        line = "|" + "|".join(cells) + "|"
        line = (line.replace("&lt;br&gt;", "<br>")
                    .replace("&amp;#45;", "-")
                    .replace("&#45;", "-")
                    .replace("&amp;", "&"))
        out.append(line)
    return "\n".join(out) + "\n"


def _promote_ek_headings(markdown):
    """Turn bold EK-4/EK-6 caption lines into real markdown headings."""
    out = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if (stripped and not stripped.startswith(("#", "|"))
                and re.search(r"EK-\d+\s*:", stripped, re.I)):
            title = re.sub(r"</?[^>]+>", "", stripped)
            title = _clean(title.replace("*", "").replace("_", ""))
            out.append("### " + title)
        else:
            out.append(line)
    return "\n".join(out)


def escape_dollars(markdown):
    """Escape currency dollars so Pandoc does not treat them as TeX math.

    The TBUP tables contain strings such as ``milyar$)``; unescaped dollar
    signs make Pandoc swallow the rest of the table as a math expression.
    Fenced mermaid blocks are left untouched.
    """
    out = []
    fenced = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fenced = not fenced
            out.append(line)
            continue
        if not fenced:
            line = re.sub(r"(?<!\\)\$", r"\\$", line)
        out.append(line)
    return "\n".join(out)


def chart_ek_link(page, frame):
    """Return (target_page_index, target_y) of the 'Detaylı tablo' GOTO link.

    The link annotation sits directly below the chart and points to the EK
    table page.  The target y coordinate distinguishes two EK tables that
    share one page (EK-3/EK-4, EK-5/EK-6, ...).
    """
    best = None
    for link in page.get_links():
        if link.get("kind") != 1 or link.get("page") is None:
            continue
        source = link.get("from")
        target = link.get("to")
        if source is None or target is None:
            continue
        if source.width <= 0 or source.height <= 0:
            continue
        gap = source.y0 - frame.y1
        if gap < -6 or gap > 130:
            continue
        if source.x1 <= frame.x0 or source.x0 >= frame.x1:
            continue
        if best is None or gap < best[0]:
            best = (gap, link["page"], target.y)
    if best is None:
        return None
    return best[1], best[2]


def resolve_ek_table(ek, target_page, target_y):
    """Pick the EK table on target_page at/nearest below target_y."""
    if not ek:
        return None, None
    best = None
    for key, data in ek.items():
        if data.get("page") != target_page:
            continue
        bbox = data.get("bbox")
        if not bbox:
            continue
        y0, y1 = bbox[1], bbox[3]
        if y0 <= target_y <= y1:
            score = 0.0
        elif target_y < y0:
            score = y0 - target_y
        else:
            score = (target_y - y1) + 1000.0
        if best is None or score < best[0]:
            best = (score, key, data)
    if best is None:
        return None, None
    return best[1], best[2]


def fix_ek_tables(page, markdown):
    """Replace pymupdf4llm's split EK tables with clean ones."""
    if not EK_TITLE_RE.search(page.get_text()):
        return markdown
    markdown = _promote_ek_headings(markdown)
    try:
        tables = page.find_tables(strategy="lines_strict").tables
    except Exception:
        return markdown
    if not tables:
        return markdown
    blocks = list(TABLE_BLOCK_RE.finditer(markdown))
    if len(blocks) != len(tables):
        return markdown
    out = []
    last = 0
    for block, table in zip(blocks, tables):
        replacement = table_to_markdown(table)
        number, title = _ek_title_above(page, table.bbox)
        tail = markdown[block.end():].lstrip()
        if title and not tail.startswith(":"):
            label = f"EK-{number}: {title}" if number else title
            replacement += f"\n: {_clean(label)}\n\n"
        out.append(markdown[last:block.start()])
        out.append(replacement)
        last = block.end()
    out.append(markdown[last:])
    return "".join(out)


# ---------------------------------------------------------------------------
# chart types
# ---------------------------------------------------------------------------

def _vbar_chart(page, frame, lines, words, swatches, title, unit,
                ek_key=None, ek_data=None, ek=None):
    years = _year_row(words)
    if len(years) < 3 or len(swatches) < 2:
        return None
    year_y = years[0]["y0"]
    series = _legend_labels(words, swatches, vertical_column=False)
    series_ys = [s[1] for s in swatches]
    legend_y = min(series_ys) if series_ys else None
    bars_geometry = _bar_geometry(page, frame)
    bars = [bar["cx"] for bar in bars_geometry]
    if len(bars) < len(years) * len(swatches):
        return None

    centers = [(word["x0"] + word["x1"]) / 2 for word in years]
    gaps = [centers[i + 1] - centers[i] for i in range(len(centers) - 1)]
    spacing = min(gaps) if gaps else 60

    groups = [[] for _ in years]
    for bar in bars:
        index = min(range(len(centers)),
                    key=lambda i: abs(centers[i] - bar))
        if abs(centers[index] - bar) < spacing * 0.55:
            groups[index].append(bar)

    values = _values_with_spans(page, frame, bars_geometry, words,
                                skip_y=year_y, legend_y=legend_y)
    bar_index = {round(bar, 2): i for i, bar in enumerate(bars)}

    rows = []
    for year, group in zip(years, groups):
        ordered = sorted(group)
        cells = []
        for bar in ordered:
            index = bar_index.get(round(bar, 2))
            cells.append(values.get(index, ""))
        rows.append([year["t"]] + cells)

    width = len(swatches)
    headers = ["Yıl"] + series
    column = {_norm(name): i + 1 for i, name in enumerate(series)}
    i_export = column.get("ihracat")
    i_import = column.get("ithalat")
    i_volume = column.get("hacim")
    i_balance = column.get("denge")

    def cell(row, index):
        if index is None or index >= len(row):
            return None
        return _to_float(row[index])

    # Very small bars are sometimes printed without a data label.  The
    # identity Hacim = İhracat + İthalat and Denge = İhracat - İthalat lets us
    # fill those cells safely.
    for row in rows:
        export = cell(row, i_export)
        imports = cell(row, i_import)
        if export is None or imports is None:
            continue
        if i_volume is not None and row[i_volume] == "":
            row[i_volume] = _num_text(export + imports)
        if i_balance is not None and row[i_balance] == "":
            row[i_balance] = _num_text(export - imports)

    if any(len(row) != width + 1 or any(value == "" for value in row[1:])
           for row in rows):
        return None

    for row in rows:
        export = cell(row, i_export)
        imports = cell(row, i_import)
        volume = cell(row, i_volume)
        balance = cell(row, i_balance)
        if None in (export, imports, volume, balance):
            continue
        tolerance = max(2.0, 0.01 * max(abs(volume), abs(export), 1))
        if (abs(volume - (export + imports)) > tolerance
                or abs(balance - (export - imports)) > tolerance):
            print(f"CHARTS-UYARI: tutarsız seri: {title}")
            return None

    if ek_data and ek_data.get("total") and "urunler" in _norm(
            ek_data.get("title", "")):
        last = next((row for row in rows if row[0] == "2025"), rows[-1])
        pairs = []
        if ek_key and ek_key.endswith("export"):
            pairs.append((i_export, "İhracat", ek_data))
            opposite = ek_key[:-len("export")] + "import"
            if ek and ek.get(opposite):
                pairs.append((i_import, "İthalat", ek[opposite]))
        elif ek_key and ek_key.endswith("import"):
            pairs.append((i_import, "İthalat", ek_data))
        for index, label, table in pairs:
            value = cell(last, index)
            if value is None or not table.get("total"):
                continue
            expected = _convert_raw(
                table["total"] * table.get("unit_factor", 1.0), unit)
            tolerance = max(1.0, 0.01 * max(abs(expected), 1.0))
            if abs(value - expected) > tolerance:
                print(f"CHARTS-UYARI: {title}: 2025 {label} grafik="
                      f"{_fmt_tr(value)} EK={_fmt_tr(expected)}")

    return {
        "kind": "vbar",
        "title": title,
        "unit": unit,
        "headers": headers,
        "rows": rows,
        "series": series,
    }


def _hbar_chart(page, frame, lines, words, swatches, title, unit,
                ek_key=None, ek_data=None):
    if len(swatches) < 2:
        return None
    labels = _legend_labels(words, swatches, vertical_column=True)
    bars_geometry = _bar_geometry(page, frame)
    bars = [bar["cx"] for bar in bars_geometry]
    values = _values_with_spans(page, frame, bars_geometry, words)

    # "Diğerleri" normally has a legend swatch but no bar.
    if len(labels) > len(bars):
        labels = [label for label in labels
                  if not _norm(label).startswith("digerleri")]
    if len(bars) == len(labels) + 1:
        # Some charts omit the legend entry for the trailing "Diğerleri"
        # bar.  The legend order always follows the bar order.
        labels = labels + ["Diğerleri"]
    if len(labels) != len(bars):
        return None
    rows = []
    for i, bar in enumerate(bars):
        value = values.get(i)
        if not value:
            return None
        rows.append([labels[i], value])

    if len(rows) > 1:
        numbers = [_to_float(row[1]) for row in rows]
        has_other = any(_norm(row[0]).startswith("digerleri") for row in rows)
        if not has_other and all(number is not None for number in numbers):
            for i in range(len(numbers) - 1):
                if numbers[i] + 1e-6 < numbers[i + 1]:
                    print(f"CHARTS-UYARI: sıralama beklenmedik: {title}")
                    break
        if has_other and ek_data and ek_data.get("total"):
            total = _convert_raw(
                ek_data["total"] * ek_data.get("unit_factor", 1.0), unit)
            chart_total = sum(number or 0 for number in numbers)
            tolerance = max(1.0, 0.015 * max(abs(total), 1.0))
            if abs(chart_total - total) > tolerance:
                print(f"CHARTS-UYARI: {title}: toplam grafik="
                      f"{_fmt_tr(chart_total)} EK={_fmt_tr(total)}")

    return {
        "kind": "hbar",
        "title": title,
        "unit": unit,
        "headers": ["Ürün grubu", f"Değer ({unit})" if unit else "Değer"],
        "rows": rows,
    }


def _pie_chart(page, frame, lines, words, swatches, title, unit, ek,
               ek_data=None):
    text = " ".join(word["t"] for word in words)
    pattern = re.compile(
        r"([A-ZÇĞİÖŞÜ][^0-9%$]*?)\s+(-?\d[\d.,]*)\s+"
        r"(milyar|milyon|miyar)\s*\$?")  # AUS PDF has "miyar" typo
    entries = []
    for match in pattern.finditer(text):
        value = _to_float(match.group(2))
        if value is None:
            continue
        entries.append((_clean(match.group(1)), value))
    entries = [entry for entry in entries if entry[0]]

    if len(entries) == len(swatches):
        merged = _merge_ek_pie(entries, title, unit, ek, ek_data)
        if merged:
            entries = merged
    elif entries:
        # Some labels may be missing/duplicated; the EK table still gives a
        # reliable country set for this chart family.
        fallback = _pie_from_ek(title, unit, len(swatches), ek, ek_data)
        if fallback:
            entries = fallback
    else:
        entries = _pie_from_ek(title, unit, len(swatches), ek, ek_data)

    if not entries:
        return None

    entries.sort(key=lambda item: item[1], reverse=True)
    total = sum(value for _name, value in entries)
    if total <= 0:
        return None
    rows = []
    for name, value in entries:
        share = 100.0 * value / total
        rows.append([name, value, share])
    return {
        "kind": "pie",
        "title": title,
        "unit": unit,
        "headers": ["Ülke", f"Değer ({unit})" if unit else "Değer", "Pay (%)"],
        "rows": rows,
    }


def _ek_country_data(title, ek):
    if not ek:
        return None
    text = _norm(title)
    if "ulkelere" not in text:
        return None
    if "ihracat" in text:
        key = "countries_export"
    elif "ithalat" in text:
        key = "countries_import"
    else:
        return None
    return ek.get(key)


def _ek_pie_data(title, ek, ek_data=None):
    if ek_data and "ulkelere" in _norm(ek_data.get("title", "")):
        return ek_data
    return _ek_country_data(title, ek)


def _merge_ek_pie(entries, title, unit, ek, ek_data=None):
    """Replace chart-text values with the more precise EK values per label.

    The printed chart values are rounded (and occasionally swapped, as in the
    İrlanda imports pie).  The EK tables are the authoritative source.  When a
    label is not present in EK, the chart value is kept.
    """
    data = _ek_pie_data(title, ek, ek_data)
    if not data or not data.get("rows"):
        return None
    factor = data.get("unit_factor", 1.0)
    by_name = {_norm(name): value for name, value in data["rows"]}
    merged = []
    displayed_sum = 0.0
    chart_other = None
    matched = 0

    for name, value in entries:
        if _norm(name).startswith("digerleri"):
            chart_other = value
            continue
        ek_value = by_name.get(_norm(name))
        if ek_value is not None:
            converted = _convert_raw(ek_value * factor, unit)
            tolerance = max(0.75, 0.001 * abs(converted))
            if abs(converted - value) > tolerance:
                print(f"CHARTS-UYARI: {title}: {name} grafik={_fmt_tr(value)} "
                      f"EK={_fmt_tr(converted)}")
            value = converted
            matched += 1
        merged.append((name, value))
        displayed_sum += value

    if matched == 0:
        return None

    total = data.get("total")
    if not total:
        return None
    total_chart = _convert_raw(total * factor, unit)
    computed_other = max(0.0, total_chart - displayed_sum)
    if chart_other is not None:
        tolerance = max(1.0, 0.02 * max(computed_other, 1.0))
        if abs(chart_other - computed_other) > tolerance:
            print(f"CHARTS-UYARI: {title}: Diğerleri grafik={_fmt_tr(chart_other)} "
                  f"EK={_fmt_tr(computed_other)}")
    merged.append(("Diğerleri", computed_other))
    return merged


def _pie_from_ek(title, unit, count, ek, ek_data=None):
    data = _ek_pie_data(title, ek, ek_data)
    if not data or not data.get("rows"):
        return None
    rows = data["rows"]
    total_raw = data.get("total")
    factor = data.get("unit_factor", 1.0)
    take = max(0, count - 1)
    if take > len(rows):
        return None
    chosen = rows[:take]
    selected = sum(value for _name, value in chosen)
    if not total_raw:
        total_raw = selected
    other_raw = max(0.0, total_raw - selected)
    entries = [(name, _convert_raw(value * factor, unit))
               for name, value in chosen]
    entries.append(("Diğerleri", _convert_raw(other_raw * factor, unit)))
    return entries


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def _init_directive(colors):
    palette = ",".join(colors)
    return ('%%{init: {"theme":"base","themeVariables":{"xyChart":'
            '{"plotColorPalette":"' + palette + '"}}}}%%')


def _render_table(chart):
    rows = chart["rows"]
    kind = chart["kind"]
    if kind == "hbar":
        headers = ["#", "Ürün grubu", chart["headers"][1]]
    else:
        headers = chart["headers"]
    out = ["| " + " | ".join(headers) + " |",
           "|" + "---|" * len(headers)]
    for i, row in enumerate(rows):
        if kind == "pie":
            cells = [_cell(row[0]), _fmt_tr(row[1]), _fmt_pct(row[2])]
        elif kind == "hbar":
            cells = [str(i + 1), _cell(row[0]), _cell(str(row[1]))]
        else:
            cells = [_cell(str(cell)) for cell in row]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def _legend_block(chart):
    rows = chart["rows"]
    lines = ["```mermaid", "block-beta", "  columns 2"]
    for i, row in enumerate(rows):
        label = _mq(f"{i + 1} {row[0]}").replace("]", ")")
        lines.append(f'  l{i + 1}["{label}"]')
    for i, _row in enumerate(rows):
        color = BAR_COLORS[i % len(BAR_COLORS)]
        text = BAR_TEXT_COLORS[i % len(BAR_TEXT_COLORS)]
        lines.append(
            f"  style l{i + 1} fill:{color},color:{text},stroke:{color}")
    lines.append("```")
    return "\n".join(lines)


def _render_mermaid(chart):
    kind = chart["kind"]
    unit = chart["unit"] or "değer"
    if kind == "pie":
        lines = ["```mermaid", "pie showData"]
        for row in chart["rows"]:
            lines.append(f'    "{_mq(row[0])}" : {_fmt_m(row[1])}')
        lines.append("```")
        return "\n".join(lines)

    if kind == "hbar":
        values = [_to_float(row[1]) or 0 for row in chart["rows"]]
        count = len(values)
        high = max(values) if values else 1
        high = max(1, math.ceil(high * 1.1))
        lines = [
            "```mermaid",
            _init_directive(BAR_COLORS),
            "xychart-beta",
            "    x-axis [" + ", ".join(
                json.dumps(str(i + 1), ensure_ascii=False)
                for i in range(count)) + "]",
            f'    y-axis "{_mq(unit)}" 0 --> {high}',
        ]
        for i, value in enumerate(values):
            data = [0.0] * count
            data[i] = value
            lines.append("    bar [" + ", ".join(
                _fmt_m(item) for item in data) + "]")
        lines.append("```")
        return "\n".join(lines) + "\n\n" + _legend_block(chart)

    # vbar: one line chart with four series (mermaid cannot group bars).
    years = [row[0] for row in chart["rows"]]
    series_count = len(chart["headers"]) - 1
    series_values = [[] for _ in range(series_count)]
    for row in chart["rows"]:
        for i in range(series_count):
            value = _to_float(row[i + 1]) if i + 1 < len(row) else None
            series_values[i].append(value or 0)
    flat = [value for series in series_values for value in series]
    low = min(0, min(flat)) if flat else 0
    high = max(flat) if flat else 1
    low = math.floor(low * 1.1) if low < 0 else 0
    high = max(1, math.ceil(high * 1.1))
    lines = ["```mermaid", _init_directive(SERIES_COLORS), "xychart-beta",
             "    x-axis [" + ", ".join(years) + "]",
             f'    y-axis "{_mq(unit)}" {low} --> {high}']
    for series in series_values:
        lines.append("    line [" + ", ".join(_fmt_m(v) for v in series) + "]")
    lines.append("```")
    return "\n".join(lines)


def _color_key(chart):
    names = chart.get("series") or []
    if len(names) < 4:
        return ""
    colors = ["Mavi", "Turuncu", "Yeşil", "Kırmızı"]
    return "*" + " · ".join(f"{color}: {name}" for color, name
                            in zip(colors, names[:4])) + "*"


def _image_block(page, frame, box, iso3, page_no, index, title,
                 save=True):
    folder = os.path.join(box, "imgs", "tbup")
    name = f"{iso3}-p{page_no + 1}-{index + 1}.png"
    if save:
        os.makedirs(folder, exist_ok=True)
        page.get_pixmap(clip=frame, dpi=150).save(os.path.join(folder, name))
    return f"![{_alt(title)}](imgs/tbup/{name}){{width=95%}}"


# ---------------------------------------------------------------------------
# public entry points
# ---------------------------------------------------------------------------

def reconstruct(page, frame, *, ek=None, box=".", iso3="tbup", mode="table+mermaid"):
    if mode in ("text", "image"):
        return None
    lines = _lines(page, frame)
    words = _words(page, frame)
    swatches = _swatches(page, frame)
    if len(lines) < 4 or len(words) < 4:
        return None
    title_lines = _title_lines(lines, frame)
    title = _clean(" ".join(line["t"] for line in title_lines))
    unit = _unit_from_title(title)
    kind = _chart_kind(lines, words, swatches, frame)
    ek_key = None
    ek_data = None
    link_key = None
    has_ek_link = False
    if ek:
        link = chart_ek_link(page, frame)
        has_ek_link = bool(link)
        if link:
            link_key, ek_data = resolve_ek_table(ek, link[0], link[1])
        ek_key = link_key
        if kind == "pie":
            ntitle = _norm(title)
            expected = ("countries_export" if "ihracat" in ntitle
                        else "countries_import" if "ithalat" in ntitle
                        else None)
            if expected and ek_key != expected:
                ek_key, ek_data = expected, ek.get(expected)
            if ek_key:
                link_key = ek_key
        elif kind == "hbar":
            expected = _expected_product_key(title)
            if expected and ek_key != expected:
                ek_key, ek_data = expected, ek.get(expected)
            if ek_key:
                link_key = ek_key
        elif kind == "vbar":
            # The links below the summary charts are often absent or point
            # to a country table; only product tables are useful here.
            if ek_data and "urunler" not in _norm(ek_data.get("title", "")):
                ek_key, ek_data = None, None
            if not ek_data:
                ntitle = _norm(title)
                if "turkiye" in ntitle:
                    ek_key, ek_data = "tr_products_export", \
                        ek.get("tr_products_export")
                else:
                    ek_key, ek_data = "products_export", \
                        ek.get("products_export")
            if not link_key:
                link_key = ek_key
    try:
        if kind == "vbar":
            chart = _vbar_chart(page, frame, lines, words, swatches, title,
                                unit, ek_key, ek_data, ek)
        elif kind == "pie":
            chart = _pie_chart(page, frame, lines, words, swatches, title,
                               unit, ek, ek_data)
        else:
            chart = _hbar_chart(page, frame, lines, words, swatches, title,
                                unit, ek_key, ek_data)
    except Exception as exc:  # keep the conversion running on odd pages
        print(f"CHARTS-UYARI: {title or 'grafik'}: {exc}")
        chart = None
    if not chart:
        return None
    chart["link_key"] = link_key
    chart["has_ek_link"] = has_ek_link
    return chart


def _frame_link_key(page, frame, ek):
    """Resolve the EK family key of a chart's GOTO annotation."""
    if not ek:
        return None
    link = chart_ek_link(page, frame)
    if not link:
        return None
    key, _data = resolve_ek_table(ek, link[0], link[1])
    return key


def _replace_ek_link_texts(markdown, keys):
    """Replace the generic source link text with EK-link placeholders.

    A page can contain more than one chart (for example the export and import
    pies), so the keys are assigned in chart order.  If the counts differ,
    the last key is reused and extra keys are ignored.
    """
    keys = list(keys)
    count = len(EK_LINK_TEXT_RE.findall(markdown))
    if not count:
        return markdown
    if not keys:
        keys = [None] * count
    elif len(keys) < count:
        keys.extend([keys[-1]] * (count - len(keys)))
    elif len(keys) > count:
        # A single picture-text block can contain several charts; pymupdf4llm
        # keeps only the last link line after such a block.
        keys = keys[-count:]

    index = 0

    def replace(_match):
        nonlocal index
        key = keys[index] if index < len(keys) else None
        index += 1
        return f"{{{{tbup-ek-link:{key or ''}}}}}"

    return EK_LINK_TEXT_RE.sub(replace, markdown)


def prepare_page(doc, page_no, markdown, ek, *, box=".", iso3="tbup",
                 mode="table+mermaid", dry_run=False):
    """Replace picture-text blocks on one page; return (markdown, titles).

    A single pymupdf4llm picture-text block can contain several charts (for
    example the export and import pies on one page), so the block is expanded
    into one table/diagram per chart frame.
    """
    if mode == "text":
        return markdown, []
    page = doc[page_no]
    blocks = list(PICTURE_RE.finditer(markdown))
    frames = chart_frames(page)
    if not blocks or not frames:
        return markdown, []

    word_list = page.get_text("words")
    scores = {}
    for bi, block in enumerate(blocks):
        tokens = {token for token in re.findall(r"[^\s<>/!-]+",
                                                block.group(0))
                  if len(token) > 1}
        for fi, frame in enumerate(frames):
            scores[(bi, fi)] = sum(
                1 for word in word_list
                if word[4] in tokens
                and _inside(frame, (word[0], word[1], word[2], word[3])))

    assign = {bi: [] for bi in range(len(blocks))}
    for fi in range(len(frames)):
        best = max(range(len(blocks)),
                   key=lambda bi: scores[(bi, fi)])
        if scores[(best, fi)] >= 2:
            assign[best].append(fi)
    assigned = {fi for indices in assign.values() for fi in indices}
    for fi in range(len(frames)):
        if fi in assigned:
            continue
        best = max(range(len(blocks)),
                   key=lambda bi: scores[(bi, fi)])
        assign[best].append(fi)
    assignments = [
        (block, [frames[fi] for fi in sorted(assign[bi],
                                             key=lambda i: frames[i].y0)])
        for bi, block in enumerate(blocks)
    ]

    out = []
    titles = []
    link_keys = []
    image_no = 0
    figure_no = 0
    last = 0
    for block, matched in assignments:
        out.append(markdown[last:block.start()])
        if not matched:
            out.append(block.group(0))
            last = block.end()
            continue
        pieces = []
        inside_count = min(len(matched), len(
            EK_LINK_TEXT_RE.findall(block.group(0))))
        for frame_index, frame in enumerate(matched):
            heading = _section_heading_above(page, frame)
            if heading and not _heading_before(markdown, block.start(),
                                               heading):
                pieces.append(f"### {heading}")
            chart = reconstruct(page, frame, ek=ek, box=box, iso3=iso3,
                                mode=mode)
            if chart:
                titles.append(_norm(chart["title"]))
                chart_link_key = chart.get("link_key")
                chart_inside = (chart.get("has_ek_link")
                                and chart_link_key
                                and frame_index < inside_count)
                if (chart.get("has_ek_link") and chart_link_key
                        and not chart_inside):
                    link_keys.append(chart_link_key)
                title_text = _clean(chart["title"])
                if mode in ("table", "table+mermaid"):
                    pieces.append(_render_table(chart))
                    if title_text:
                        pieces.append(f": {title_text}")
                if mode in ("mermaid", "table+mermaid"):
                    if chart["kind"] == "vbar":
                        color_key = _color_key(chart)
                        if color_key:
                            pieces.append(color_key)
                    if title_text:
                        fig_id = (f"fig:tbup-{iso3}-p{page_no + 1}-"
                                  f"{figure_no}")
                        caption = title_text.replace('"', "'")
                        pieces.append(
                            f'::: {{#{fig_id} caption="{caption}"}}')
                        pieces.append(_render_mermaid(chart))
                        pieces.append(":::")
                        figure_no += 1
                    else:
                        pieces.append(_render_mermaid(chart))
                if chart_inside:
                    pieces.append(
                        f"_<u>{{{{tbup-ek-link:{chart_link_key}}}}}</u>_")
            else:
                frame_link_key = _frame_link_key(page, frame, ek)
                frame_inside = bool(frame_link_key) and frame_index < inside_count
                if frame_link_key and not frame_inside:
                    link_keys.append(frame_link_key)
                lines = _lines(page, frame)
                title_lines = _title_lines(lines, frame)
                title = _clean(" ".join(line["t"] for line in title_lines))
                if mode != "image":
                    pieces.append(
                        "*Grafikteki bazı çubukların etiketi kaynak PDF'te "
                        "eksik olduğu için grafik görüntü olarak eklendi.*")
                pieces.append(_image_block(page, frame, box, iso3,
                                           page_no, image_no, title,
                                           save=not dry_run))
                if frame_inside:
                    pieces.append(
                        f"_<u>{{{{tbup-ek-link:{frame_link_key}}}}}</u>_")
                image_no += 1
        out.append("\n\n" + "\n\n".join(pieces) + "\n\n")
        last = block.end()
    out.append(markdown[last:])
    result = _replace_ek_link_texts("".join(out), link_keys)
    return re.sub(r"\n{3,}", "\n\n", result), titles


def _section_heading_above(page, frame):
    """Return a section heading directly above a frame.

    Besides the bare ``İhracat``/``İthalat`` subheadings, the profiles use
    product-section titles such as "Türkiye'nin … İthalatında Başlıca
    Ürünler".  Chart captions ("… Başlıca Ürün Grupları") must not be treated
    as headings.
    """
    candidates = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            text = _clean(" ".join(span["text"] for span in line["spans"]))
            if not text:
                continue
            y1 = line["bbox"][3]
            if y1 > frame.y0 + 2 or frame.y0 - y1 >= 110:
                continue
            ntext = _norm(text)
            if ntext in {"ihracat", "ithalat"}:
                candidates.append((y1, text))
            elif ("baslicaurunler" in ntext
                  and "baslicaurungruplari" not in ntext):
                candidates.append((y1, text))
    if not candidates:
        return ""
    return max(candidates, key=lambda item: item[0])[1]


def _heading_before(markdown, position, heading):
    heads = re.findall(r"(?m)^#{1,6}\s+(.*\S)\s*$", markdown[:position])
    target = _norm(heading)
    for head in heads[-6:]:
        clean = re.sub(r"<[^>]+>", "", head)
        clean = clean.replace("*", "").replace("_", "").strip()
        if _norm(clean) == target:
            return True
    return False
