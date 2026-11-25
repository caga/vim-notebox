#!/home/osman/.vim/plugged/vim-notebox/plugin/scripts/venv/bin/python3
# -*- coding: utf-8 -*-
"""Bir ulkenin otomatik bilgi notlarini (OBN) HTML olarak disa aktarir.

Ulkenin "Otomatik Bilgi Notlari" sayfasi (n_type: hub obn {iso3}) ana sayfa
(index.html) olur.  Ulkeye ait butun OBN notlari <id>.html olarak yazilir.
Yalnizca istenen ulkenin OBN notlari alinir; `obn files` sayfasi, global
`obn-hub.md`, ulke paneli (hub {iso3}) ve diger ulkeler disarida kalir.
Notlarda gecen yerel resimler cikti dizinine (ozgun goreli yollari korunarak)
kopyalanir; PDF/DOCX belgeler kopyalanmaz.  Link degistirme islemi pandoc
AST filtresiyle (obn-export.lua) yapilir; boylece CV grid tablolari bozulmaz.

Kullanim:
    ./exportObnHtml.py YeniZelanda
    ./exportObnHtml.py NZL --box ~/countryNotes
    ./exportObnHtml.py Avustralya --out /tmp/aus-html

Secenekler:
    --box DIR    not kutusu (varsayilan: $NOTES_DIR veya cwd)
    --root DIR   disa aktarim kok dizini, kutuya gore (varsayilan: htmlExports)
    --out DIR    tam cikti dizini (--root yerine)
    --no-map     ulke haritasini kopyalama/ana sayfaya ekleme
    --no-clean   var olan cikti dizinini silme, uzerine yaz
    --dry-run    hicbir dosya yazmadan ne yapilacagini yazdir
"""

import html
import os
import re
import shutil
import subprocess
import sys

import _cli

_cli.init()

import notebox as nb


MAP_SUBDIR = ("data", "img", "maps")
EXPORT_ROOT = "htmlExports"
DEFAULT_TOC_TITLE = "İçindekiler"
DEFAULT_REF_TITLE = "Kaynakça"
PANDOC = "pandoc"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LUA_FILTER = os.path.join(SCRIPT_DIR, "obn-export.lua")
MERMAID_FIGURE_FILTER = os.path.join(SCRIPT_DIR, "mermaid-figures.lua")
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp",
              ".tif", ".tiff", ".avif", ".ico"}
MARKDOWN_REF_RE = re.compile(r"(!?)\[([^\]]*)\]\(([^)]+)\)")
HTML_IMG_RE = re.compile(r'<img\b[^>]*\bsrc\s*=\s*"([^"]+)"', re.IGNORECASE)

CSS = """\
:root {
  color-scheme: light;
}

* {
  box-sizing: border-box;
}

body {
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue",
    Arial, sans-serif;
  max-width: 1100px;
  margin: 0 auto;
  padding: 1.5rem 2rem 4rem;
  line-height: 1.6;
  color: #1f2328;
  background: #fff;
}

h1, h2, h3, h4 {
  line-height: 1.25;
  margin-top: 1.6em;
  margin-bottom: 0.5em;
}

h1.title, header#title-block-header h1 {
  margin-top: 0.2em;
}

a {
  color: #0969da;
}

a:hover {
  text-decoration: underline;
}

.country-map-wrap {
  text-align: center;
  margin: 1rem 0 2rem;
}

.country-map {
  max-width: 100%;
  max-height: 350px;
  width: auto;
  height: auto;
  border: 1px solid #d0d7de;
  border-radius: 6px;
  padding: 4px;
  background: #fff;
}

.site-nav {
  font-size: 0.9rem;
  margin: 0 0 1.25rem;
}

.site-nav a {
  text-decoration: none;
  color: #57606a;
}

.site-nav a:hover {
  color: #0969da;
  text-decoration: underline;
}

nav#TOC {
  background: #f6f8fa;
  border: 1px solid #d0d7de;
  border-radius: 6px;
  padding: 1rem 1.5rem;
  margin: 1.5rem 0;
  font-size: 0.95rem;
}

nav#TOC > ul {
  margin: 0.25rem 0;
  padding-left: 1.25rem;
}

table {
  border-collapse: collapse;
  width: 100%;
  margin: 1rem 0;
  display: block;
  overflow-x: auto;
}

th, td {
  border: 1px solid #d0d7de;
  padding: 0.35rem 0.5rem;
  vertical-align: top;
  text-align: left;
}

thead th {
  background: #f6f8fa;
}

tr:nth-child(even) td {
  background: #fbfbfc;
}

figure {
  margin: 1.5rem 0;
  text-align: center;
}

figcaption, caption {
  color: #57606a;
  font-size: 0.9rem;
}

img {
  max-width: 100%;
  height: auto;
}

code {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas,
    "Liberation Mono", monospace;
  font-size: 0.9em;
  background: #f6f8fa;
  padding: 0.1em 0.3em;
  border-radius: 4px;
}

pre {
  background: #f6f8fa;
  border: 1px solid #d0d7de;
  border-radius: 6px;
  padding: 1rem;
  overflow-x: auto;
}

pre code {
  background: transparent;
  padding: 0;
}

blockquote {
  margin: 1rem 0;
  padding: 0.25rem 1rem;
  color: #57606a;
  border-left: 4px solid #d0d7de;
}

hr {
  border: 0;
  border-top: 1px solid #d0d7de;
  margin: 2rem 0;
}

@media print {
  body {
    max-width: none;
    padding: 0;
  }

  .site-nav {
    display: none;
  }

  table {
    display: table;
  }

  a {
    color: inherit;
    text-decoration: none;
  }
}
"""


def clean_value(value):
    """YAML on-ekindeki tirnaklari temizler."""
    value = (value or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value.strip()


def n_type_tokens(info):
    return (info.get("n_type") or "").lower().split()


def note_country(info):
    return clean_value(info.get("country"))


def note_title(info):
    return clean_value(info.get("title"))


def front_matter_end(lines):
    if not lines or lines[0].strip() != "---":
        return -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return i
    return -1


def split_note(path):
    """Notu (info, govde) olarak dondurur; YAML ve #BackReferences cikarilir."""
    info = nb.parse_front_matter(path)
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return info, ""

    end = front_matter_end(lines)
    body = lines[end + 1:] if end >= 0 else lines

    for i, line in enumerate(body):
        if nb.BACKREF_RE.match(line):
            body = body[:i]
            break

    return info, "\n".join(body).strip("\n")


def country_matches(info, iso3, country_field, display):
    country = note_country(info)
    if country:
        if nb.norm_name(country) == nb.norm_name(country_field):
            return True
        if nb.slugify(country) == nb.slugify(country_field):
            return True
        if display and nb.norm_name(country) == nb.norm_name(display):
            return True
        return False

    tokens = n_type_tokens(info)
    if iso3.lower() in tokens:
        return True

    title = note_title(info)
    return bool(display) and nb.slugify(title).startswith(nb.slugify(display))


def collect_country_notes(box, iso3, country_field, display):
    """Ulkeye ait OBN notlarini (obn files haric) dondurur.

    Donus: ([(path, info, out_name)], hub_path veya None, excluded listesi)
    """
    hub = nb.find_obn_hub(iso3)
    hub_abs = os.path.abspath(hub) if hub else None

    found = []
    excluded = []
    for fname in sorted(os.listdir(box)):
        if not fname.lower().endswith(".md"):
            continue
        path = os.path.join(box, fname)
        info = nb.parse_front_matter(path)
        tokens = n_type_tokens(info)
        if "obn" not in tokens:
            continue
        if "files" in tokens:
            if country_matches(info, iso3, country_field, display):
                excluded.append((path, "obn files"))
            continue
        if not country_matches(info, iso3, country_field, display):
            continue
        found.append((os.path.abspath(path), info, os.path.splitext(fname)[0]))

    if hub_abs:
        found = [item for item in found if item[0] != hub_abs]
        hub_info = nb.parse_front_matter(hub_abs)
        found.insert(0, (hub_abs, hub_info, os.path.splitext(hub)[0]))

    return found, hub_abs, excluded


def export_folder_name(display, iso3):
    name = re.sub(r"\s+", "", (display or "").strip())
    name = name.replace("/", "-").replace("\\", "-")
    if not name:
        name = iso3.upper()
    return name + "Notları"


def safe_output_dir(box, opts, display, iso3):
    if opts["out"]:
        outdir = os.path.expanduser(opts["out"])
        if not os.path.isabs(outdir):
            outdir = os.path.join(box, outdir)
    else:
        root = os.path.expanduser(opts["root"])
        if not os.path.isabs(root):
            root = os.path.join(box, root)
        outdir = os.path.join(root, export_folder_name(display, iso3))
    return os.path.abspath(outdir)


def check_clean_target(outdir, box):
    """Yanlislikla kutu kokunu veya ana dizini silmeyi engeller."""
    target = os.path.abspath(outdir)
    dangerous = {
        os.path.abspath(os.sep),
        os.path.abspath(os.path.expanduser("~")),
        os.path.abspath(box),
    }
    if target in dangerous or len(target.rstrip(os.sep)) <= 3:
        return False
    return True


def _split_link_target(raw):
    """'path "title"' / '<path>' bicimini (path, title) olarak ayirir."""
    raw = raw.strip()
    if raw.startswith("<") and ">" in raw:
        end = raw.index(">")
        return raw[1:end], raw[end + 1:].strip()
    match = re.match(r'^(\S+)(\s+"[^"]*")?$', raw)
    if match:
        return match.group(1), (match.group(2) or "").strip()
    # Yol bosluk icerebilir; sonundaki tirnakli basligi ayir.
    match = re.match(r'^(.*?)(\s+"[^"]*")$', raw)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return raw, ""


def is_remote_target(target):
    return (not target or target.startswith("#")
            or target.startswith("//")
            or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target) is not None)


def rel_inside(path, box):
    """path kutu icindeyse kutuya gore goreli yolu dondurur."""
    try:
        rel = os.path.relpath(path, box)
    except ValueError:
        return None
    if rel == os.pardir or rel.startswith(os.pardir + os.sep):
        return None
    return rel.replace(os.sep, "/")


def unique_dest(dest, local_abs, used):
    if dest not in used or used[dest] == local_abs:
        return dest
    stem, ext = os.path.splitext(dest)
    n = 2
    while f"{stem}-{n}{ext}" in used:
        n += 1
    return f"{stem}-{n}{ext}"


def add_asset_map(asset_map, target, dest):
    variants = {
        target,
        target.replace(" ", "%20"),
        target.replace("%20", " "),
        os.path.normpath(target),
    }
    for variant in variants:
        asset_map[variant] = dest


def collect_assets(body, box, outdir, copied, used, asset_map, warnings):
    """Govdedeki yerel resim/belge hedeflerini toplar.

    Resimler cikti dizinine kopyalanir; belgeler kopyalanmaz, yalnizca
    cikti dizininden kutuya gore yeniden yollanir.  Linklerin kendisi burada
    degistirilmez; pandoc AST filtresi (obn-export.lua) uygular.  Boylece
    sabit genislikli grid tablolari bozulmaz.
    """

    def process(raw_target, is_image):
        target, _title = _split_link_target(raw_target)
        if not target or is_remote_target(target):
            return
        path = target.split("#", 1)[0]
        if not path:
            return
        local_abs = (path if os.path.isabs(path)
                     else os.path.abspath(os.path.join(box, path)))
        if not os.path.isfile(local_abs):
            if is_image:
                warnings.append(f"görsel bulunamadı: {path}")
            return

        ext = os.path.splitext(local_abs)[1].lower()
        if is_image or ext in IMAGE_EXTS:
            if local_abs in copied:
                dest = copied[local_abs]
            else:
                rel = rel_inside(local_abs, box)
                dest = rel if rel else os.path.join(
                    "assets", os.path.basename(local_abs))
                dest = unique_dest(dest.replace(os.sep, "/"), local_abs, used)
                used[dest] = local_abs
                copied[local_abs] = dest
                dest_abs = os.path.join(outdir, dest)
                os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
                shutil.copy2(local_abs, dest_abs)
            add_asset_map(asset_map, path, dest)
            return

        if ext == ".md":
            return
        add_asset_map(asset_map, path,
                      os.path.relpath(local_abs, outdir).replace(os.sep, "/"))

    for match in MARKDOWN_REF_RE.finditer(body):
        process(match.group(3), bool(match.group(1)))

    for match in HTML_IMG_RE.finditer(body):
        process(match.group(1), True)



def heading_count(body):
    count = 0
    in_fence = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if re.match(r"^#{1,3}\s", line):
            count += 1
    return count


def resolve_bib(info, box):
    raw = clean_value(info.get("bibliography"))
    if raw in ("", "[]"):
        return None
    if raw.startswith("[") and raw.endswith("]"):
        return None
    path = raw if os.path.isabs(raw) else os.path.join(box, raw)
    if os.path.isfile(path) and os.path.getsize(path) > 0:
        return os.path.abspath(path)
    return None


def resolve_csl(info, box):
    raw = clean_value(info.get("citation-style"))
    if raw:
        path = raw if os.path.isabs(raw) else os.path.join(box, raw)
        if os.path.isfile(path):
            return os.path.abspath(path)
    if os.path.isfile(nb.CITATION_STYLE):
        return os.path.abspath(nb.CITATION_STYLE)
    return None


def find_mermaid_js():
    """Locate mermaid.min.js (env override, ~/.bin, node_modules)."""
    candidates = []
    for env_name in ("OBN_MERMAID_JS", "MERMAID_JS"):
        value = os.environ.get(env_name)
        if value:
            candidates.append(os.path.expanduser(value))
    candidates.append(os.path.expanduser("~/.bin/mermaid.min.js"))
    candidates.append(os.path.expanduser(
        "~/node_modules/mermaid/dist/mermaid.min.js"))
    for tool in ("mmdc", "mermaid-filter"):
        path = shutil.which(tool)
        if not path:
            continue
        parent = os.path.dirname(os.path.realpath(path))
        while True:
            candidates.append(os.path.join(
                parent, "node_modules", "mermaid", "dist", "mermaid.min.js"))
            nxt = os.path.dirname(parent)
            if nxt == parent:
                break
            parent = nxt
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def write_mermaid_header(outdir):
    """Copy mermaid.min.js (or use CDN) and write the init snippet."""
    local = find_mermaid_js()
    if local:
        shutil.copy2(local, os.path.join(outdir, "mermaid.min.js"))
        src = "mermaid.min.js"
        print("MERMAID: yerel mermaid.min.js kullanılıyor")
    else:
        src = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"
        print("UYARI exportObnHtml: yerel mermaid.min.js bulunamadı; CDN kullanılacak")
    header = os.path.join(outdir, "mermaid-init.html")
    content = (
        f'<script src="{src}"></script>\n'
        "<script>\n"
        '  mermaid.initialize({ startOnLoad: false, securityLevel: "loose" });\n'
        '  window.addEventListener("DOMContentLoaded", function () {\n'
        '    document.querySelectorAll("pre.mermaid > code").forEach(function (code) {\n'
        "      code.parentElement.textContent = code.textContent;\n"
        "    });\n"
        '    mermaid.run({ nodes: document.querySelectorAll(".mermaid") }).catch(function (e) {\n'
        '      console.error(e);\n'
        '    });\n'
        "  });\n"
        "</script>\n"
    )
    with open(header, "w", encoding="utf-8") as fh:
        fh.write(content)
    return header


def pandoc_args(box, title, info, toc, output, header=None):
    args = [
        PANDOC,
        "--from", "markdown+implicit_figures+table_captions",
        "--to", "html5",
        "--standalone",
        "--table-caption-position", "below",
        "--figure-caption-position", "below",
        "--lua-filter", LUA_FILTER,
        "--lua-filter", MERMAID_FIGURE_FILTER,
        "--metadata", f"title={title}",
        "--metadata", "lang=tr",
        "--metadata", f"toc-title={clean_value(info.get('toc-title')) or DEFAULT_TOC_TITLE}",
        "--metadata", ("reference-section-title="
                       + (clean_value(info.get("reference-section-title"))
                          or DEFAULT_REF_TITLE)),
        "--css", "style.css",
        "--output", output,
    ]
    if header:
        args += ["--include-in-header", header]
    if toc:
        args += ["--toc", "--toc-depth=2"]

    bib = resolve_bib(info, box)
    csl = resolve_csl(info, box)
    if bib:
        args += ["--citeproc", "--bibliography", bib]
        if csl:
            args += ["--csl", csl]

    return args


def filter_env(page_map, asset_map):
    env = dict(os.environ)
    env["OBN_PAGE_MAP"] = "\n".join(
        f"{key}\t{value}" for key, value in page_map.items())
    env["OBN_ASSET_MAP"] = "\n".join(
        f"{key}\t{value}" for key, value in asset_map.items())
    return env


def run_pandoc(args, markdown, box, env):
    try:
        proc = subprocess.run(
            args, input=markdown, text=True, cwd=box, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        return 1, str(exc)
    message = (proc.stderr or "").strip()
    return proc.returncode, message


def parse_args(argv):
    opts = {
        "root": EXPORT_ROOT,
        "out": None,
        "no_map": False,
        "no_clean": False,
        "dry": False,
    }
    positional = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--root", "--out"):
            if i + 1 >= len(argv):
                raise SystemExit(f"HATA {arg} bir dizin gerektirir")
            opts[arg[2:]] = argv[i + 1]
            i += 2
            continue
        if arg.startswith("--root="):
            opts["root"] = arg.split("=", 1)[1]
        elif arg.startswith("--out="):
            opts["out"] = arg.split("=", 1)[1]
        elif arg == "--no-map":
            opts["no_map"] = True
        elif arg == "--no-clean":
            opts["no_clean"] = True
        elif arg == "--dry-run":
            opts["dry"] = True
        elif arg.startswith("--"):
            raise SystemExit(f"HATA bilinmeyen seçenek: {arg}")
        else:
            positional.append(arg)
        i += 1
    return opts, positional


def run():
    opts, positional = parse_args(sys.argv[1:])
    arg = " ".join(positional) if positional else "TUR"
    iso3, display, country_field = nb.resolve_country(arg)
    if not iso3:
        print(f"HATA exportObnHtml: Ülke ISO3 kodu çözülemedi: {arg}")
        return 1

    box = os.path.abspath(nb.notes_dir())
    if not os.path.isdir(box):
        print(f"HATA exportObnHtml: Not kutusu bulunamadı: {box}")
        return 1

    hub = nb.find_obn_hub(iso3)
    if not hub:
        print(f"HATA exportObnHtml: {display} ({iso3}) için OBN hub sayfası yok")
        return 1

    notes, hub_abs, excluded = collect_country_notes(
        box, iso3, country_field, display)
    if not notes:
        print(f"HATA exportObnHtml: {display} ({iso3}) için OBN notu bulunamadı")
        return 1

    outdir = safe_output_dir(box, opts, display, iso3)

    page_map = {}
    for path, _info, stem in notes:
        page_map[os.path.basename(path)] = (
            "index.html" if os.path.abspath(path) == hub_abs else stem + ".html")

    print(f"Ülke: {display} ({iso3})")
    print(f"HTML_EXPORT: {outdir}")
    print(f"PAGES: {len(notes)}")
    if excluded:
        print("HARIÇ: " + "; ".join(
            os.path.basename(path) + " (" + reason + ")"
            for path, reason in excluded))

    if opts["dry"]:
        for path, info, stem in notes:
            name = page_map[os.path.basename(path)]
            print(f"  {os.path.basename(path)} -> {name}  [{info.get('n_type', '')}]")
        return 0

    if not shutil.which(PANDOC):
        print("HATA exportObnHtml: pandoc bulunamadı (PATH)")
        return 1

    if os.path.isdir(outdir):
        if not opts["no_clean"]:
            if not check_clean_target(outdir, box):
                print(f"HATA exportObnHtml: güvenli olmayan çıktı dizini: {outdir}")
                return 1
            shutil.rmtree(outdir)
        else:
            print(f"UYARI exportObnHtml: mevcut dizin korunuyor: {outdir}")
    os.makedirs(outdir, exist_ok=True)

    with open(os.path.join(outdir, "style.css"), "w", encoding="utf-8") as fh:
        fh.write(CSS)

    mermaid_header = write_mermaid_header(outdir)

    map_note = ""
    if not opts["no_map"]:
        map_src = os.path.join(box, *MAP_SUBDIR, f"{iso3.lower()}.png")
        if os.path.isfile(map_src):
            shutil.copy2(map_src, os.path.join(outdir, "map.png"))
            map_note = "map.png"
        else:
            print(f"UYARI exportObnHtml: ülke haritası yok: {map_src}")

    if not os.path.isfile(LUA_FILTER) or not os.path.isfile(
            MERMAID_FIGURE_FILTER):
        print("HATA exportObnHtml: Lua filtresi bulunamadı: "
              f"{LUA_FILTER} / {MERMAID_FIGURE_FILTER}")
        return 1

    copied = {}
    used = {}
    asset_map = {}
    warnings = []
    pages = []
    for path, info, stem in notes:
        body = split_note(path)[1]
        collect_assets(body, box, outdir, copied, used, asset_map, warnings)
        pages.append((path, info, stem, body))

    for warning in dict.fromkeys(warnings):
        print(f"UYARI exportObnHtml: {warning}")
    if copied:
        print(f"GÖRSEL: {len(copied)} dosya kopyalandı")

    env = filter_env(page_map, asset_map)
    failures = []
    for path, info, stem, body in pages:
        fname = os.path.basename(path)
        out_name = page_map[fname]
        output = os.path.join(outdir, out_name)
        title = note_title(info) or stem

        is_home = os.path.abspath(path) == hub_abs
        if is_home and map_note:
            alt = html.escape(f"{display} haritası")
            body = (f'<p class="country-map-wrap">'
                    f'<img class="country-map" src="map.png" alt="{alt}">'
                    f'</p>\n\n' + body)
        elif not is_home:
            body = ('<nav class="site-nav"><a href="index.html">'
                    '← Ana sayfa</a></nav>\n\n' + body)

        toc = heading_count(body) >= 3
        args = pandoc_args(box, title, info, toc, output,
                           header=mermaid_header)
        code, message = run_pandoc(args, body, box, env)
        if code != 0:
            failures.append((fname, message or f"pandoc kodu {code}"))
            print(f"HATA {fname}: {message or 'pandoc başarısız'}")
        else:
            print(f"Yazıldı: {out_name}  [{info.get('n_type', '')}]")

    index_path = os.path.join(outdir, "index.html")
    print(f"INDEX: {index_path}")
    if failures:
        print(f"FAILED: {len(failures)} sayfa")
        return 1
    return 0


def main():
    try:
        return run()
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
            return 2
        raise
    except Exception as exc:
        print(f"HATA exportObnHtml: {type(exc).__name__}: {exc}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
