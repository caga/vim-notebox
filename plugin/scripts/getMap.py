#!/home/osman/.vim/plugged/vim-notebox/plugin/scripts/venv/bin/python3
import os
import sys
import subprocess
import tempfile
import urllib.parse
from pathlib import Path

import requests
import cnlook as lu

BASE_URL = "https://www.harita.gov.tr/homedir-assets/ulke_adlari/ulke/"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

SOURCE_WIDTH = 3510
SOURCE_HEIGHT = 2482
CROP_WIDTH = 3386
CROP_HEIGHT = 2271
CROP_X = 62
CROP_Y = 44

# Haritalar aktif not kutusuna yazilir. GMAP_NOTES_DIR verilirse o kullanilir;
# GMAP_MAPS_DIR verilirse dogrudan o dizin kullanilir.
NOTES_DIR = os.environ.get("GMAP_NOTES_DIR") or os.getcwd()
MAPS_DIR = Path(
    os.environ.get("GMAP_MAPS_DIR")
    or (Path(NOTES_DIR) / "data" / "img" / "maps")
)

OVERRIDES = {
    "USA": "ABD",
    "GBR": "İngiltere",
    "CPV": "Cabo Verde",
    "KOR": "Kore Cumhuriyeti",
    "PRK": "Kore Demokratik Halk Cumhuriyeti",
    "BIH": "Bosna Hersek",
    "GNB": "Gine Bissau",
    "COM": "Komorlar Birliği",
    "LIE": "Lihtenştayn",
    "MHL": "Marşal Adaları",
    "MUS": "Morityus",
    "STP": "Sao Tome Ve Principe",
}

_TR_FOLD = str.maketrans({
    "İ": "i", "I": "i", "ı": "i",
    "Ş": "s", "ş": "s",
    "Ğ": "g", "ğ": "g",
    "Ü": "u", "ü": "u",
    "Ö": "o", "ö": "o",
    "Ç": "c", "ç": "c",
})


def _norm(value: str) -> str:
    return value.strip().translate(_TR_FOLD).lower()


ISO3_LOOKUP = {_norm(code): code.strip().upper() for code in lu.iso3 if code.strip()}
NAME_LOOKUP = {}
for _i, _name in enumerate(lu.countryNames):
    _code = lu.iso3[_i].strip().upper()
    if _code:
        NAME_LOOKUP.setdefault(_norm(_name), _code)
OVERRIDE_LOOKUP = {_norm(name): code for code, name in OVERRIDES.items()}


def filenameFor(iso3: str) -> str:
    return OVERRIDES.get(iso3, lu.iso3ToName(iso3))


def resolveCountry(country: str):
    key = _norm(country)
    if not key:
        return None
    iso3 = ISO3_LOOKUP.get(key) or NAME_LOOKUP.get(key) or OVERRIDE_LOOKUP.get(key)
    if not iso3:
        return None
    return iso3, filenameFor(iso3)


def downloadPdf(url: str, dest: Path) -> bool:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/pdf,*/*"}
    try:
        response = requests.get(url, headers=headers, timeout=90, allow_redirects=True)
    except requests.RequestException as exc:
        print(f"Download error: {exc}")
        return False
    content_type = response.headers.get("Content-Type", "").lower()
    if response.status_code != 200 or "pdf" not in content_type:
        print(f"No map available (HTTP {response.status_code}, {content_type or 'unknown'}).")
        return False
    dest.write_bytes(response.content)
    return True


def convertAndCrop(pdf: Path, out: Path) -> bool:
    command = [
        "magick",
        "-density", "300",
        "-colorspace", "RGB",
        str(pdf),
        "-resize", f"{SOURCE_WIDTH}x{SOURCE_HEIGHT}!",
        "-crop", f"{CROP_WIDTH}x{CROP_HEIGHT}+{CROP_X}+{CROP_Y}",
        "+repage",
        str(out),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ImageMagick failed:\n{result.stderr.strip()}")
        return False
    probe = subprocess.run(
        ["magick", "identify", "-format", "%wx%h", str(out)],
        capture_output=True, text=True,
    )
    size = probe.stdout.strip()
    expected = f"{CROP_WIDTH}x{CROP_HEIGHT}"
    if size != expected:
        print(f"Unexpected output size {size}, expected {expected}.")
        return False
    return True


def main():
    args = sys.argv[1:]
    force = "--force" in args
    path_only = "--path" in args or "--dry-run" in args
    positional = [a for a in args if not a.startswith("--")]
    country = " ".join(positional) if positional else "TUR"

    resolved = resolveCountry(country)
    if not resolved:
        print(f"Unknown country: {country}")
        sys.exit(1)

    iso3, filename = resolved
    out = MAPS_DIR / f"{iso3.lower()}.png"

    if path_only:
        print(f"MAP: {out}")
        return

    if out.exists() and not force:
        print(f"EXISTS: {out}")
        print(f"MAP: {out}")
        return

    url = BASE_URL + urllib.parse.quote(filename) + ".pdf"
    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {filename}.pdf for {iso3} ...")

    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / f"{iso3}.pdf"
        if not downloadPdf(url, pdf):
            sys.exit(1)
        if not convertAndCrop(pdf, out):
            out.unlink(missing_ok=True)
            sys.exit(1)

    print(f"Saved {out} ({CROP_WIDTH}x{CROP_HEIGHT})")
    print(f"MAP: {out}")


if __name__ == "__main__":
    main()
