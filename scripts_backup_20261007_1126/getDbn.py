#!/home/osman/.vim/plugged/vim-notebox/plugin/scripts/venv/bin/python3
# -*- coding: utf-8 -*-
"""MFA (Disisleri Bakanligi) Ulke Kunyesi sayfasindan veri cekip
standart not formatinda markdown dosyalari uretir.

Kullanim:
    python getDbn.py NZL
    python getDbn.py "Yeni Zelanda"
    python getDbn.py Yeni Zelanda
    python getDbn.py Almanya
"""

import datetime as dt
import json
import os
import re
import sys

import requests
from bs4 import BeautifulSoup, NavigableString

import cnlook as lu
from helperFunctions import IdGenerator, writeMdReport


BASE = "https://www.mfa.gov.tr"
BOLGELER_URL = "/sub.tr.mfa?03af1e06-bd93-40cb-ae4f-2c4ac27672e7"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
CACHE_DIR = os.path.join(SCRIPT_DIR, "scriptData", "mfaNotes")
CACHE_FILE = os.path.join(CACHE_DIR, "regions.json")

# ==== CIKTI KONUMU ====
# Notlar ve indeks, aktif not kutusuna (g:notes_directory / calisma klasoru)
# yazilir. KUNYE_NOTES_DIR ortam degiskeni verilirse o kullanilir.
BIB_SUBDIR = "bibfiles"
NOTES_DIR = os.environ.get("KUNYE_NOTES_DIR") or os.getcwd()
OUT_DIR = NOTES_DIR
BIB_DIR = os.environ.get("KUNYE_BIB_DIR") or os.path.join(OUT_DIR, BIB_SUBDIR)
HUB_FILE = os.path.join(OUT_DIR, "dbwn-index.md")
HUB_TITLE = "Dışişleri Bakanlığı Web Notları"
NOTE_TYPE = "dbwn"
CITATION_STYLE = os.path.join(SCRIPT_DIR, "ieee-with-url.csl")

BIB_AUTHOR = "T.C. Dışişleri Bakanlığı"
BIB_HOWPUBLISHED = "mfa.gov.tr, T.C. Dışişleri Bakanlığı"
TR_MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
             "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

ALIASES = {
    "Güney Kore": "Kore Cumhuriyeti",
    "Kuzey Kore": "Kore Demokratik Halk Cumhuriyeti",
    "Birleşik Arap Emirlikleri": "BAE",
    "Yeşil Burun Adaları": "Cabo Verde",
    "Ekvador": "Ekvator Cumhuriyeti",
    "Liechtenstein": "Lihtenştayn",
    "Marshall Adaları": "Marşal Adaları",
    "Mauritius": "Morityus",
    "Esvatini": "Esvatini Krallığı",
    "Komorlar": "Komorlar Birliği",
    "Brunei": "Brunei Darusselam",
    "Çekya": "Çek Cumhuriyeti",
    "Samoa": "Bağımsız Samoa Devleti",
    "Kongo": "Kongo Cumhuriyeti",
    "Nijerya": "Nijerya Federal Cumhuriyeti",
    "Rusya": "Rusya Federasyonu",
    "Fiji": "Fiji Cumhuriyeti",
    "Tonga": "Tonga Krallığı",
    "Gine-Bissau": "Gine Bissau",
    "Demokratik Kongo Cumhuriyeti": "Kongo Demokratik Cumhuriyeti",
}

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
}


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


COUNTRY_NAME_INDEX = {}
for _name in lu.countryNames:
    COUNTRY_NAME_INDEX.setdefault(norm_name(_name), []).append(_name)


def clean(s):
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def slugify(s):
    s = clean(s).replace("İ", "i").replace("I", "ı").lower()
    for a, b in (("ı", "i"), ("ş", "s"), ("ğ", "g"), ("ü", "u"), ("ö", "o"),
                 ("ç", "c"), ("â", "a"), ("î", "i"), ("û", "u")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def strip_parentheses(s):
    """Basliklardaki yuvarlak parantez isaretlerini kaldirir, icerigi korur."""
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


def fetch_soup(session, url):
    if not url.startswith("http"):
        url = BASE + url
    resp = session.get(url, headers=HEADERS, timeout=45)
    return BeautifulSoup(resp.text, "html.parser")


def grid_items(soup):
    table = soup.find("table", id="sb_grd")
    items = []
    if not table:
        return items
    for a in table.find_all("a", href=True):
        text = a.get_text(strip=True)
        if not text or re.fullmatch(r"\d+", text):
            continue
        items.append((text, a["href"]))
    return items


def next_page_number(soup, current):
    nxt = 0
    for a in soup.find_all("a", href=True):
        if "__doPostBack" in a["href"] and re.fullmatch(r"\d+", a.get_text(strip=True)):
            nxt = max(nxt, int(a.get_text(strip=True)))
    return nxt if nxt > current else None


def region_page_items(session, region_href):
    soup = fetch_soup(session, region_href)
    items = []
    page = 1
    while True:
        items.extend(grid_items(soup))
        nxt = next_page_number(soup, page)
        if not nxt:
            break
        data = {}
        for inp in soup.find_all("input"):
            name = inp.get("name")
            if name:
                data[name] = inp.get("value", "")
        data["__EVENTTARGET"] = "sb$grd"
        data["__EVENTARGUMENT"] = f"Page${nxt}"
        resp = session.post(BASE + region_href, headers=HEADERS, data=data, timeout=45)
        soup = BeautifulSoup(resp.text, "html.parser")
        page = nxt
    return items


def crawl_country_map(session):
    root = fetch_soup(session, BOLGELER_URL)
    regions = grid_items(root)
    countries = {}
    region_list = []
    for region_name, region_href in regions:
        region_list.append({"name": region_name, "href": region_href})
        for name, href in region_page_items(session, region_href):
            countries.setdefault(name, href)
    data = {
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "regions": region_list,
        "countries": countries,
    }
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return countries


def load_country_map(session):
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("countries"):
                return data["countries"]
        except (ValueError, OSError):
            pass
    return crawl_country_map(session)


def match_country(name, countries):
    if name in ALIASES and ALIASES[name] in countries:
        return ALIASES[name]
    key = norm_name(name)
    for k in countries:
        if norm_name(k) == key:
            return k
    keys = list(countries)
    prefix = [k for k in keys if key and (norm_name(k).startswith(key) or key.startswith(norm_name(k)))]
    if len(prefix) == 1:
        return prefix[0]
    scored = []
    token = set(key.split())
    for k in keys:
        nk = norm_name(k)
        overlap = len(token & set(nk.split()))
        if overlap:
            scored.append((overlap, len(nk.split()), nk, k))
    scored.sort(key=lambda x: (-x[0], x[1]))
    if scored:
        best = scored[0]
        unique = len(scored) == 1 or scored[1][0] < best[0]
        if unique and key:
            return best[3]
    return None


def resolve_country(arg):
    """Kullanici girdisini (ISO3 kodu veya Turkce ulke adi) cozumler.
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
        if len(cand) > 1:
            print(f"UYARI birden çok eşleşme: {cand}; en kısası seçildi")
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


def find_kunye_url(session, sub_href):
    soup = fetch_soup(session, sub_href)
    for a in soup.find_all("a", href=True):
        text = clean(a.get_text(strip=True))
        if text.endswith("Ülke Künyesi") or "kunyesi.tr.mfa" in a["href"]:
            href = a["href"]
            return href if href.startswith("http") else BASE + href
    return None


def mechanical_kunye_url(name):
    return f"{BASE}/{slugify(name)}-kunyesi.tr.mfa"


def mechanical_relations_url(name):
    return f"{BASE}/turkiye-{slugify(name)}-siyasi-iliskileri.tr.mfa"


def fetch_page(session, url):
    if not url.startswith("http"):
        url = BASE + url
    resp = session.get(url, headers=HEADERS, timeout=45)
    return BeautifulSoup(resp.text, "html.parser"), resp.url


def find_relations_url(session, sub_href, name=None):
    """Ulke alt sayfasindan Turkiye ile iliskiler sayfasinin linkini bulur.
    Siyasi iliskiler sayfasi tercih edilir; yoksa birlesik iliskiler sayfasi.
    Slug'inda ulke adi gecen linklere oncelik verilir."""
    soup = fetch_soup(session, sub_href)
    slug = slugify(name) if name else ""
    candidates = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "tr.mfa" not in href:
            continue
        low = href.lower()
        if any(x in low for x in ("terminoloji", "ekonomik", "commercial",
                                  "ticari", "kuruluslar", "sub.tr.mfa")):
            continue
        text = clean(a.get_text(" ", strip=True))
        if "siyasi-iliskileri" in low:
            score = 3
        elif low.endswith("iliskileri.tr.mfa"):
            score = 2
        elif "ilişkileri" in text or "iliskileri" in low:
            score = 1
        else:
            continue
        if slug and slug in low:
            score += 1
        candidates.append((score, href))
    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])
    href = candidates[0][1]
    return href if href.startswith("http") else BASE + href


def strip_enumeration(s):
    """Bolum basliklarindaki 'a.', 'b.' veya '1.' gibi on ekleri kaldirir."""
    return clean(re.sub(r"^[0-9A-Za-zÇĞİÖŞÜçğıöşü]+[\).]\s*", "", s or ""))


def html_table_md(table):
    """HTML tablosunu markdown pipe tablosuna cevirir."""
    rows = []
    for tr in table.find_all("tr"):
        cells = [clean(td.get_text(" ", strip=True))
                 for td in tr.find_all(["td", "th"])]
        if any(cells):
            rows.append(cells)
    if not rows:
        return ""
    ncol = max(len(r) for r in rows)
    rows = [r + [""] * (ncol - len(r)) for r in rows]
    header, body = rows[0], rows[1:]
    lines = ["| " + " | ".join(escape_cell(c) for c in header) + " |",
             "| " + " | ".join("---" for _ in header) + " |"]
    for r in body:
        lines.append("| " + " | ".join(escape_cell(c) for c in r) + " |")
    return "\n".join(lines)


def render_node(node):
    if getattr(node, "name", None) == "table":
        return html_table_md(node)
    inner = node.find("table") if hasattr(node, "find") else None
    if inner is not None:
        return html_table_md(inner)
    return clean(node.get_text(" ", strip=True))


def _heading_title(el):
    if getattr(el, "name", None) not in ("p", "h1", "h2", "h3", "h4", "h5", "h6"):
        return None
    strong = el.find("strong")
    if not strong:
        return None
    text = clean(el.get_text(" ", strip=True))
    stext = clean(strong.get_text(" ", strip=True))
    if not text or not stext or norm_name(text) != norm_name(stext):
        return None
    if len(text) > 120 or text.endswith("."):
        return None
    title = strip_enumeration(stext)
    return title or None


def extract_sections(soup, fallback_title):
    """Bir icerik sayfasini baslikli bolumlere ayirir. Baslik yoksa tum
    icerik fallback_title altinda tek bolum olur. Donus: [(baslik, govde), ...]"""
    box = soup.find("span", class_="mfa-content-text") or \
        soup.find("div", class_="mfa-content-text")
    if not box:
        return []
    sections = []
    cur_title = None
    cur_nodes = []
    for node in box.children:
        if getattr(node, "name", None) is None:
            continue
        title = _heading_title(node)
        if title is not None:
            sections.append((cur_title, cur_nodes))
            cur_title = title
            cur_nodes = []
        else:
            cur_nodes.append(node)
    sections.append((cur_title, cur_nodes))

    out = []
    preamble = []
    for title, nodes in sections:
        body = "\n\n".join(filter(None, (render_node(n) for n in nodes))).strip()
        if title is None:
            if body:
                preamble.append(body)
            continue
        if body:
            out.append((title, body))
    if preamble:
        out.insert(0, (fallback_title, "\n\n".join(preamble)))
    return out


def _page_title(soup):
    """Sayfa <title> metnini dondurur (bos ise '')."""
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    return clean(title)


def country_in_title(title, names):
    """Sayfa basligi verilen ulke adlarindan birini iceriyorsa True.
    Baslik bos ise dogrulanamadigi icin None doner."""
    nt = norm_name(title)
    if not nt:
        return None
    for name in names or ():
        nn = norm_name(name)
        if nn and nn in nt:
            return True
    return False


def _download_sections(session, url, fallback_title, label):
    """url'yi indirip (bolumler, final_url, sayfa_basligi) doner. Ag hatasinda
    (None, None, None) (durum bilinmiyor, silme yapilmamali); sayfa yoksa
    ([], final_url, baslik)."""
    try:
        soup, final = fetch_page(session, url)
    except requests.RequestException as exc:
        print(f"UYARI {label} sayfası indirilemedi: {url} ({exc})")
        return None, None, None
    page_title = _page_title(soup)
    if "default." in final.lower() or not soup.find(class_="mfa-content-text"):
        print(f"{label} sayfası yok: {url}")
        return [], final, page_title
    sections = extract_sections(soup, fallback_title)
    if not sections:
        print(f"{label} sayfasında bölüm bulunamadı: {final}")
        return [], final, page_title
    merged = {}
    order = []
    for title, body in sections:
        if title in merged:
            merged[title] = merged[title] + "\n\n" + body
        else:
            merged[title] = body
            order.append(title)
    print(f"{label} sayfası: {final} ({len(order)} bölüm)")
    return [(t, merged[t]) for t in order], final, page_title


def parse_relations(session, name, sub_href=None):
    """Turkiye ile iliskiler sayfasini indirip
    (bolumler, final_url, sayfa_basligi) doner."""
    rel_url = None
    if sub_href:
        rel_url = find_relations_url(session, sub_href, name)
    if not rel_url:
        rel_url = mechanical_relations_url(name)
    return _download_sections(session, rel_url, "Siyasi İlişkiler", "İlişkiler")


def _find_siyasi_gorunum_url(session, sub_href, name=None):
    soup = fetch_soup(session, sub_href)
    slug = slugify(name) if name else ""
    candidates = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "tr.mfa" not in href or "sub.tr.mfa" in href:
            continue
        low = href.lower()
        text = clean(a.get_text(" ", strip=True))
        if "siyasi-gorunumu" in low:
            score = 3
        elif "siyasi görünümü" in text.lower() or "siyasi gorunumu" in low:
            score = 2
        else:
            continue
        if slug and slug in low:
            score += 1
        candidates.append((score, href))
    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])
    href = candidates[0][1]
    return href if href.startswith("http") else BASE + href


def mechanical_siyasi_gorunum_url(name):
    return f"{BASE}/{slugify(name)}-siyasi-gorunumu.tr.mfa"


def parse_siyasi_gorunum(session, name, sub_href=None):
    """Ulkenin siyasi gorunumu sayfasini indirip
    (bolumler, final_url, sayfa_basligi) doner."""
    url = None
    if sub_href:
        url = _find_siyasi_gorunum_url(session, sub_href, name)
    if not url:
        url = mechanical_siyasi_gorunum_url(name)
    return _download_sections(session, url, "Siyasi Görünümü", "Siyasi Görünüm")


def parse_cell(td):
    """Bir td icindeki <strong> etiketlerini kesif noktasi kabul edip
    her etiketin degerini, bir sonraki etikete kadar toplar. Ardisik
    <strong> parcalari (aralarinda deger yoksa) tek etikette birlestirilir."""
    pairs = []
    label_parts = []
    buf = []

    def flush():
        if label_parts:
            pairs.append((" ".join(label_parts).strip(), " ".join(buf).strip()))

    for node in td.descendants:
        name = getattr(node, "name", None)
        if name == "strong":
            text = clean(node.get_text(" ", strip=True)).rstrip(":").strip()
            if not text:
                continue
            if buf and label_parts:
                flush()
                label_parts = []
                buf = []
            label_parts.append(text)
            continue
        if isinstance(node, NavigableString):
            if getattr(node.parent, "name", None) == "strong":
                continue
            text = clean(str(node))
            if text and label_parts:
                buf.append(text)
    flush()
    return pairs


def parse_kunye(soup):
    box = soup.find("span", class_="mfa-content-text") or soup.find("div", class_="mfa-content-text")
    table = box.find("table") if box else None
    official = None
    data = {}
    if not table:
        return official, data
    for td in table.find_all("td"):
        for label, value in parse_cell(td):
            if not label:
                continue
            if official is None:
                official = label
            value = value.lstrip(":").strip()
            if label not in data or (not data[label] and value):
                data[label] = value
    return official, data


def find_value(data, *keys):
    for key in keys:
        nk = norm_name(key)
        for label, value in data.items():
            if nk and nk in norm_name(label):
                return value
    return ""


DYNAMIC_SKIP_ROWS = 4


def extract_dynamic_fields(soup, skip_rows=DYNAMIC_SKIP_ROWS):
    """Kunye tablosunun ilk 'skip_rows' satirini atlayip kalan
    hucrelerdeki <strong> etiketli alanlari (etiket, deger) olarak doner."""
    box = soup.find("span", class_="mfa-content-text") or soup.find("div", class_="mfa-content-text")
    table = box.find("table") if box else None
    fields = []
    seen = set()
    if not table:
        return fields
    for index, tr in enumerate(table.find_all("tr")):
        if index < skip_rows:
            continue
        for td in tr.find_all("td"):
            for label, value in parse_cell(td):
                label = clean(label).rstrip(":").strip()
                value = clean(value).lstrip(":").strip()
                if not label or not value:
                    continue
                if not re.search(r"[0-9A-Za-zÇĞİÖŞÜçğıöşü]", label):
                    continue
                key = norm_name(label)
                if key in seen:
                    continue
                seen.add(key)
                fields.append((label, value))
    return fields


def escape_cell(value):
    return clean(value).replace("|", "\\|")


def md_table(rows, caption):
    labels = [r[0] for r in rows]
    values = [r[1] for r in rows]
    w1 = max([len("Resmi İsmi:")] + [len(x) for x in labels]) + 2
    w2 = max([len(v) for v in values] + [10])
    lines = [
        f"| {' ' * w1} | {' ' * w2} |",
        f"| {'-' * w1} | {'-' * w2} |",
    ]
    for label, value in rows:
        lines.append(f"| {label:<{w1}} | {escape_cell(value):<{w2}} |")
    lines.append(caption)
    return "\n".join(lines)


def date_from_id(idno):
    try:
        return dt.datetime.fromtimestamp(int(idno)).strftime("%d/%m/%y")
    except (TypeError, ValueError):
        return dt.datetime.now().strftime("%d/%m/%y")


def bib_key(title, display, iso3):
    """Not basligindan benzersiz bib anahtari uretir: <slug>-<iso3>."""
    base = clean(title)
    prefix = clean(display) + " " if display else ""
    if prefix and base.startswith(prefix):
        base = base[len(prefix):]
    slug = slugify(base).replace("-", "")
    if not slug:
        slug = "kaynak"
    code = (iso3 or "").lower()
    return f"{slug}-{code}" if code else slug


def tr_today():
    now = dt.datetime.now()
    return f"{now.day} {TR_MONTHS[now.month - 1]} {now.year}"


def bib_path(idno):
    return os.path.join(BIB_DIR, f"{idno}.bib")


def bib_entry(key, title, url):
    lines = [
        f"@misc{{{key},",
        f"  author = {{{{{BIB_AUTHOR}}}}},",
        f"  title = {{{title}}},",
        f"  howpublished = {{{BIB_HOWPUBLISHED}}},",
        f"  year = {{{dt.datetime.now().year}}},",
    ]
    if url:
        lines.append(f"  url = {{{url}}},")
    lines.append(f"  note = {{Erişim tarihi: {tr_today()}}}")
    lines.append("}")
    return "\n".join(lines) + "\n"


BACKREF_RE = re.compile(r"^\s*#BackReferences\b")


def split_backrefs(text):
    """Metni (govde_satirlari, backref_satirlari) olarak ayirir.
    #BackReferences isareti yoksa ikinci liste bostur."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if BACKREF_RE.match(line):
            return lines[:i], lines[i:]
    return lines, []


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


def write_note(path, idno, title, body, country_field, source_url,
               display, iso3, date=None, modify=None):
    """Notu yazar; ayni id ile bibfiles/{id}.bib uretir ve not sonuna
    @key atfini ekler."""
    key = bib_key(title, display, iso3)
    os.makedirs(BIB_DIR, exist_ok=True)
    with open(bib_path(idno), "w", encoding="utf-8") as f:
        f.write(bib_entry(key, title, source_url))
    rel_bib = os.path.relpath(bib_path(idno), os.path.dirname(path) or OUT_DIR)
    body = body.rstrip() + f"\n\n@{key}\n"
    write_note_file(path, build_header(idno, title, country_field, date, modify,
                                       bibfile=rel_bib) + "\n" + body)
    return key


def remove_note(path):
    """Notu ve varsa ayni id'li bib dosyasini siler."""
    idno = os.path.splitext(os.path.basename(path))[0]
    for target in (path, bib_path(idno)):
        try:
            if os.path.exists(target):
                os.remove(target)
        except OSError as exc:
            print(f"UYARI silinemedi: {target} ({exc})")


def build_header(idno, title, country_field, date=None, modify=None,
                 n_type=None, keywords=None, bibfile=None):
    n_type = n_type or NOTE_TYPE
    date = date or dt.datetime.now().strftime("%d/%m/%y")
    keywords_line = f"keywords: {keywords}\n" if keywords else "keywords:\n"
    return (
        "---\n"
        f"id: {idno}\n"
        "author: dbscript\n"
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


INDEX_SUFFIX = "Dışişleri Bakanlığı Web Notları"
LEGACY_INDEX_SUFFIX = "Kunye"


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


def _id_int(entry):
    try:
        return int(entry["id"])
    except (TypeError, ValueError):
        return 0


def find_country_files(country_field, display_name, n_types=None):
    """Yalnizca dbKunye/ klasorunde, verilen n_type degerlerine ve ulkeye ait
    dosyalari bulur. Varsayilan olarak eski dbk notlarini da kapsar; boylece
    onlar dbwn olarak yerinde guncellenir. Donus: {key: {"path","id","date","title"}}"""
    if n_types is None:
        n_types = (NOTE_TYPE, "dbk")
    elif isinstance(n_types, str):
        n_types = (n_types,)
    found = {}
    duplicates = set()
    if not os.path.isdir(OUT_DIR):
        return found, duplicates
    for fname in os.listdir(OUT_DIR):
        if not fname.lower().endswith(".md"):
            continue
        path = os.path.join(OUT_DIR, fname)
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
            print(f"UYARI birden çok '{title}' dosyası: "
                  f"{os.path.basename(prev['path'])} ve {os.path.basename(path)}; "
                  "en yenisi güncellenecek")
            if _id_int(entry) > _id_int(prev):
                duplicates.add(prev["path"])
                found[key] = entry
            else:
                duplicates.add(path)
    return found, duplicates


def target_directory(found):
    index_key = next((k for k in found if k.endswith(slugify(INDEX_SUFFIX))), None)
    if not index_key:
        index_key = next((k for k in found
                          if k.endswith(slugify(LEGACY_INDEX_SUFFIX))), None)
    if index_key:
        return os.path.dirname(found[index_key]["path"])
    for entry in found.values():
        return os.path.dirname(entry["path"])
    return OUT_DIR


def unique_id(used, existing_ids, target_dir):
    idno = IdGenerator()
    while idno in used or idno in existing_ids or os.path.exists(os.path.join(target_dir, f"{idno}.md")):
        idno += 1
    used.add(idno)
    return idno


def update_hub(index_title, index_path):
    """dbKunye/dbwn-index.md dosyasini olusturur/gunceller ve ilgili
    ulke indeks dosyasinin linkini ekler."""
    os.makedirs(OUT_DIR, exist_ok=True)
    legacy_hub = os.path.join(OUT_DIR, "kunyeindex.md")
    if not os.path.exists(HUB_FILE) and os.path.exists(legacy_hub):
        try:
            os.replace(legacy_hub, HUB_FILE)
            print(f"Yeniden adlandırıldı: {legacy_hub} -> {HUB_FILE}")
        except OSError as exc:
            print(f"UYARI {legacy_hub} yeniden adlandırılamadı: {exc}")
    rel = os.path.relpath(index_path, os.path.dirname(HUB_FILE))
    target = f"- [{index_title}]({rel})"
    existing = []
    if os.path.exists(HUB_FILE):
        info = parse_front_matter(HUB_FILE)
        idno = info.get("id") or str(IdGenerator())
        date = info.get("date") or None
        with open(HUB_FILE, encoding="utf-8") as f:
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
        idno = str(IdGenerator())
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
    modify = None if create else dt.datetime.now().strftime("%d/%m/%y")
    header = build_header(idno, HUB_TITLE, "", date, modify,
                          keywords="kunye hub")
    write_note_file(HUB_FILE, header + "\n" + "\n".join(existing) + "\n")
    print(f"{'Yazıldı' if create else 'Güncellendi'}: {HUB_FILE}")


def run(iso3, name=None, country_field=None):
    session = requests.Session()
    if not name:
        name = lu.iso3ToName(iso3) if iso3 in lu.iso3 else iso3
    if not country_field:
        country_field = iso3.lower() if iso3 else slugify(name)
    print(f"Ülke: {name}" + (f" ({iso3})" if iso3 else ""))

    countries = load_country_map(session)
    matched = match_country(name, countries)
    kunye_url = None
    if matched:
        print(f"MFA eşleşmesi: {matched}")
        kunye_url = find_kunye_url(session, countries[matched])
    if not kunye_url:
        kunye_url = mechanical_kunye_url(name)
        print(f"Keşif başarısız, mekanik URL deneniyor: {kunye_url}")

    soup = fetch_soup(session, kunye_url)
    official, data = parse_kunye(soup)
    if not data:
        print(f"Künye verisi ayrıştırılamadı: {kunye_url}")
        return 2
    official = smart_title(official or name)
    display = name

    resmi = official
    baskent = find_value(data, "Başkent")
    yuzolcumu = find_value(data, "Yüzölçümü", "Yuzolcumu")
    para = find_value(data, "Para Birimi")
    devlet = find_value(data, "Devlet Başkanı", "Cumhurbaşkanı", "Genel Vali")
    basbakan = find_value(data, "Başbakan")

    dynamic = extract_dynamic_fields(soup)

    missing = [n for n, v in (("Başkent", baskent), ("Yüzölçümü", yuzolcumu),
                              ("Para Birimi", para), ("Devlet Başkanı", devlet),
                              ("Başbakan", basbakan)) if not v]
    if missing:
        print("UYARI eksik alanlar:", ", ".join(missing))

    os.makedirs(OUT_DIR, exist_ok=True)
    found, duplicate_paths = find_country_files(country_field, display)
    if found:
        print(f"Mevcut dosyalar: "
              f"{', '.join(sorted(e['title'] for e in found.values()))}")
    for dup in sorted(duplicate_paths):
        remove_note(dup)
        print(f"Silindi (yinelenen): {dup}")

    sub_href = countries.get(matched) if matched else None
    candidate_names = [display, official, ALIASES.get(display),
                       lu.iso3ToName(iso3) if iso3 in lu.iso3 else None]
    candidate_names = [n for n in candidate_names if n]
    rel_sections, rel_url, rel_title = parse_relations(session, name, sub_href)
    gorum_sections, gorum_url, gorum_title = parse_siyasi_gorunum(session, name, sub_href)
    mismatch = False
    rel_ok = True
    gorum_ok = True
    if rel_sections and country_in_title(rel_title, candidate_names) is False:
        print(f"UYARI İlişkiler sayfası ülkeye uymuyor "
              f"(başlık: {rel_title!r}); kaynak atlanıyor")
        rel_ok = False
        mismatch = True
    if gorum_sections and country_in_title(gorum_title, candidate_names) is False:
        print(f"UYARI Siyasi Görünüm sayfası ülkeye uymuyor "
              f"(başlık: {gorum_title!r}); kaynak atlanıyor")
        gorum_ok = False
        mismatch = True
    sources_ok = (rel_sections is not None and gorum_sections is not None
                  and not mismatch)
    extra_sections = []
    if rel_ok:
        for title, body in (rel_sections or []):
            extra_sections.append((title, body, rel_url))
    if gorum_ok:
        for title, body in (gorum_sections or []):
            extra_sections.append((title, body, gorum_url))
    if not sources_ok:
        print("Bazı sayfalar alınamadı veya ülkeyle uyuşmadı; mevcut notlar korunacak")

    target = target_directory(found)
    os.makedirs(target, exist_ok=True)
    modify_date = dt.datetime.now().strftime("%d/%m/%y")
    existing_ids = {int(e["id"]) for e in found.values() if str(e["id"]).strip().isdigit()}
    used = set()

    t1 = strip_parentheses(f"{display} Genel Siyasi Bilgiler Tablosu")
    body1 = md_table([("Resmi İsmi:", resmi), ("Başkent:", baskent),
                      ("Yüzölçümü:", yuzolcumu), ("Para Birimi:", para)],
                     ":Genel Siyasi Bilgiler") + "\n"
    t2 = strip_parentheses(f"{display} Makam Bilgileri Tablosu")
    body2 = md_table([("Devlet Başkanı/Vali", devlet), ("Başbakan", basbakan)],
                     ": Makam Bilgileri") + "\n"

    notes = [(t1, body1, kunye_url), (t2, body2, kunye_url)]
    for label, value in dynamic:
        notes.append((strip_parentheses(f"{display} {label}"),
                      clean(value) + "\n", kunye_url))

    written = []

    def emit(title, body, source_url):
        entry = found.get(slugify(title))
        if entry:
            idno = entry["id"]
            path = entry["path"]
            date = entry.get("date") or date_from_id(idno)
            modify = modify_date
        else:
            idno = str(unique_id(used, existing_ids, target))
            path = os.path.join(target, f"{idno}.md")
            date = None
            modify = None
        write_note(path, idno, title, body, country_field, source_url,
                   display, iso3, date, modify)
        print(f"{'Güncellendi' if entry else 'Yazıldı'}: {path}")
        written.append((path, title))

    for title, body, source_url in notes:
        emit(title, body, source_url)

    for section, body, source_url in extra_sections:
        emit(strip_parentheses(f"{display} {section}"), body, source_url)

    t5 = strip_parentheses(f"{display} {INDEX_SUFFIX}")
    legacy_t5 = strip_parentheses(f"{display} {LEGACY_INDEX_SUFFIX}")
    idx_entry = found.get(slugify(t5)) or found.get(slugify(legacy_t5))
    if idx_entry:
        idx_id = idx_entry["id"]
        idx_path = idx_entry["path"]
        idx_date = idx_entry.get("date") or date_from_id(idx_id)
        idx_modify = modify_date
    else:
        idx_id = str(unique_id(used, existing_ids, target))
        idx_path = os.path.join(target, f"{idx_id}.md")
        idx_date = None
        idx_modify = None
    idx_dir = os.path.dirname(idx_path)
    links = "\n".join(f"- [{title}]({os.path.relpath(path, idx_dir)})"
                      for path, title in written)
    body5 = f"{links}\n"
    write_note_file(idx_path, build_header(idx_id, t5, country_field, idx_date, idx_modify) + "\n" + body5)
    print(f"{'Güncellendi' if idx_entry else 'Yazıldı'}: {idx_path}")

    update_hub(t5, idx_path)

    current_titles = ({slugify(title) for _, title in written}
                      | {slugify(t5), slugify(legacy_t5)})
    if sources_ok:
        for key, entry in found.items():
            if key not in current_titles and os.path.exists(entry["path"]):
                remove_note(entry["path"])
                print(f"Silindi (artık üretilmiyor): {entry['path']}")

    print(f"INDEX: {idx_path}")

    return 0


def main():
    arg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "TUR"
    iso3, name, country_field = resolve_country(arg)
    return run(iso3, name, country_field)


if __name__ == "__main__":
    sys.exit(main())
