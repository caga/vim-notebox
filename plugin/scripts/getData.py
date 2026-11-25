#!/home/osman/.vim/plugged/vim-notebox/plugin/scripts/venv/bin/python3
# -*- coding: utf-8 -*-
"""WorldBank gostergelerinden iki not uretir.

Birinci not `<Ulke> Ilk Bakis` basligiyla genel ulke tablosunu, ikinci not
`<Ulke> Temel Ekonomik Gostergeler` basligiyla sablon notundan uretilen
karsilastirma tablosunu icerir.  Ikisi de `n_type: obn indicatorReport` olur
ve ulke gosterge indeksinde listelenir.

Veriler not kutusunun icinde JSON olarak onbelleklenir:

    data/<iso3>/wbdata/general.json             ulke kunyesi (ham yanit)
    data/<iso3>/wbdata/indicators/<KOD>.json    gosterge basina ham yanit
    data/<iso3>/wbdata/manifest.json            cozulen degerler ve ceviriler

Ornek: `Yeni Zelanda` icin `data/nzl/wbdata/`.  Klasor yoksa kurulur.

Indirme `curl` ile yapilir.  Bu agda TLS el sikismasi duzenli olarak
kesiliyor ve ayni istek ikinci denemede geciyor; bu yuzden curl
`--retry-all-errors` ile cagrilir.  Yanit once `.part` dosyasina yazilir,
JSON olarak dogrulanir, sonra `os.replace` ile atomik olarak yerine konur:
yarim ya da bozuk indirme onbellegi asla ezmez.

Tazeleme karari **dosya tarihine** baglidir, notun `modify:` alanina degil.
Bir dosya `NOTES_WB_REPORT_MAX_AGE_DAYS` (varsayilan 7) gunden yeniyse aga
cikilmaz.  Suresi dolmus dosyalar tek tek yenilenir, yani tek bir calisma
hem onbellekten hem endpoint'ten beslenebilir.  `--force` yas sinirini yok
sayar, `--rebuild` hic indirmez (yalnizca onbellekten uretir).  Indirme
duserse elde bayat dosya varsa o kullanilir; notun eski degeri ancak o da
yoksa korunur.  Tasima hatasi "veri yok" sayilmaz ve `modify:` bugune
cekilmez, boylece sonraki calisma eksikleri yeniden dener.

Her gosterge `mrnev=1` ile istenir: en son *dolu* gozlem, tek satir.  Bu
parametre cok gostergeli istekte API hatasi verdigi icin istekler tek tek
yapilir.  Sablon satirlarindaki `{yearN}` yer tutuculari, o satirin endpoint
yiliyla doldurulur.  Sablon yili yalnizca etikettir; endpoint yili farkli
diye deger reddedilmez.  Yil yoksa yer tutucu ve bos parantez kaldirilir.

Kullanim:
    ./getData.py Nepal
    ./getData.py NPL --box ~/countryNotes
    ./getData.py Türkiye --force
    ./getData.py Nepal --check
    ./getData.py Nepal --rebuild
    ./getData.py Nepal --delete
    ./getData.py Nepal --delete --delete-data
    ./getData.py Nepal --ping

Secenekler:
    --box DIR        not kutusu (varsayilan: $NOTES_DIR veya cwd)
    --check          onbellek yasini ve calisma modunu bildirir, not yazmaz
    --force          dosya yasindan bagimsiz olarak tumunu yeniler
    --rebuild        aga cikmadan yalnizca onbellekten notlari uretir
    --clear-cache    data/<iso3>/wbdata/ klasorunu siler, sonra normal akis
    --delete         ulkenin gosterge notlarini siler (JSON onbellek kalir)
    --delete-data    --delete ile birlikte JSON onbellegini de siler
    --ping           not yazmadan, onbellege dokunmadan endpoint'i dener

Ortam degiskenleri:
    NOTES_WB_REPORT_MAX_AGE_DAYS   onbellek yas siniri (varsayilan 7)
    NOTES_WB_HTTP_RETRIES          curl --retry sayisi (varsayilan 4)
    NOTES_WB_CURL                  curl yolu (varsayilan: PATH'teki curl)
"""

import asyncio
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import _cli

_cli.init()

from googletrans import Translator
from py_markdown_table.markdown_table import markdown_table as md_table

import notebox as nb
import wbTable as wbt


indicatorCodesWB = {
        'Nüfus': 'SP.POP.TOTL',
        'GSYH ($)': 'NY.GDP.MKTP.CD',
        'GSYH (Kişi Başı $)': 'NY.GDP.PCAP.CD',
        'GSYH % Büyüme': 'NY.GDP.MKTP.KD.ZG',
        'GSYH % Sanayi Payı': 'NV.IND.TOTL.ZS',
        'GSYH % Hizmet Payı': 'NV.SRV.TOTL.ZS',
        'GSYH % Tarım Payı': 'NV.AGR.TOTL.ZS',
        'Enflasyon %': 'FP.CPI.TOTL.ZG',
        'İşsizlik %': 'SL.UEM.TOTL.ZS',
        'İhracatda Yük. Tek. Payı %': 'TX.VAL.TECH.MF.ZS',
        'İhracat ($)': 'BX.GSR.MRCH.CD',
        'İthalat ($)': 'BM.GSR.MRCH.CD',
        'Arge/GSYH % Oranı': 'GB.XPD.RSDV.GD.ZS',
}

DEFAULT_MAX_AGE_DAYS = 7
GENERAL_KEYS = ("Ülke", "Bölge", "Gelir Seviyesi", "Başkent")

# Sablon satirindaki son yil yer tutucusu/eki atilir; "GSYH (Kişi Başı $)"
# gibi etiketlerin ic parantezleri korunur.
_INDICATOR_BY_BASE = {wbt.norm(k): (k, v) for k, v in indicatorCodesWB.items()}
YEAR_PLACEHOLDER_RE = re.compile(r"\{year\d*\}", re.IGNORECASE)

# --- WorldBank HTTP katmani -------------------------------------------------
# Istekler tek gostergelidir: `mrnev=1` (en son dolu deger) cok gostergeli
# istekte "The provided parameter value is not valid" hatasi verir.  Tek tek
# istekler kenar onbelleginde tutuldugu icin ayrica daha hizlidir.
WB_API = "https://api.worldbank.org/v2"
WB_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
WB_CURL_CONNECT_TIMEOUT = 5
WB_CURL_MAX_TIME = 12
DEFAULT_HTTP_RETRIES = 4
# Yeniden denenecek HTTP kodlari (diger 4xx kalici sayilir).
RETRY_STATUS = (429, 500, 502, 503, 504)
# Ag tamamen dustuyse her gosterge icin yeniden denemek anlamsiz: bu kadar
# istek ust uste duserse kalanlar istenmeden isaretlenir.
WB_MAX_CONSECUTIVE_ERRORS = 3

# --- Onbellek duzeni --------------------------------------------------------
WB_DATA_SUBDIR = "wbdata"
WB_GENERAL_FILE = "general.json"
WB_INDICATORS_SUBDIR = "indicators"
WB_MANIFEST_FILE = "manifest.json"


def http_retries():
    raw = (os.environ.get("NOTES_WB_HTTP_RETRIES") or "").strip()
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_HTTP_RETRIES


def curl_bin():
    return (os.environ.get("NOTES_WB_CURL") or "curl").strip() or "curl"


def _short_error(exc):
    """Uzun istisnalari tek satira indirger."""
    text = f"{type(exc).__name__}: {exc}".split(" (Caused by")[0]
    text = " ".join(text.split())
    if len(text) > 110:
        text = text[:107].rstrip() + "..."
    return text


def _ensure_dir(path):
    if path:
        os.makedirs(path, exist_ok=True)


def _unlink(path):
    if not path:
        return
    try:
        os.unlink(path)
    except OSError:
        pass


def _read_json(path):
    """Dosyayi JSON olarak okur; yoksa/bozuksa None."""
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _mtime(path):
    try:
        return int(os.path.getmtime(path))
    except OSError:
        return 0


def cache_key(iso3, country_field=""):
    """`data/` altindaki klasor adi: TUR -> tur, Yeni Zelanda -> nzl."""
    return nb.wb_cache_key(iso3, country_field)


def wb_data_dir(key):
    return os.path.join(nb.notes_dir(), "data", key, WB_DATA_SUBDIR)


def general_cache_path(data_dir):
    return os.path.join(data_dir, WB_GENERAL_FILE)


def indicator_cache_path(data_dir, code):
    return os.path.join(data_dir, WB_INDICATORS_SUBDIR, f"{code}.json")


def manifest_path(data_dir):
    return os.path.join(data_dir, WB_MANIFEST_FILE)


def cache_age_days(path):
    """Dosya yasi (gun).  Dosya yoksa None."""
    try:
        return max(0.0, (time.time() - os.path.getmtime(path)) / 86400.0)
    except OSError:
        return None


def curl_json(url, dest=None, retries=None):
    """JSON indirir, dogrular ve (dest verildiyse) atomik olarak yazar.

    Yeniden deneme Python tarafinda yapilir: `curl --retry` denemeleri
    gecikmesiz arka arkaya yapiyor (olctuk: 5 deneme 21 ms'de bitiyor) ve
    hepsi ayni kesinti penceresine dusuyor.  Bu agda TLS el sikismasi
    kesintisi ~0.1 sn surdugu icin denemeler arasina gercek bir bekleme
    konur; yeni baglanti ikinci denemede geciyor.

    Donus: (payload, info); hata halinde payload None ve info['error']
    doludur.  `dest` verilmezse gecici bir dosya kullanilir ve silinir
    (ping).
    """
    limit = WB_CURL_MAX_TIME
    attempts = http_retries() if retries is None else max(1, retries)
    info = {'http': None, 'elapsed': 0.0, 'attempts': 1, 'bytes': 0,
            'cached': False, 'error': None}
    ephemeral = False
    if dest:
        _ensure_dir(os.path.dirname(dest))
    else:
        fd, dest = tempfile.mkstemp(prefix="wb-json-", suffix=".json")
        os.close(fd)
        ephemeral = True
    tmp = f"{dest}.part"
    try:
        for attempt in range(1, attempts + 1):
            info['attempts'] = attempt
            payload, once, retryable = _curl_attempt(url, tmp, limit)
            for field in ('http', 'elapsed', 'bytes'):
                if once.get(field) is not None:
                    info[field] = once[field]
            if payload is not None:
                info['error'] = None
                try:
                    os.replace(tmp, dest)
                except OSError as exc:
                    info['error'] = _short_error(exc)
                    return None, info
                return payload, info
            info['error'] = once.get('error')
            if not retryable or attempt == attempts:
                break
            # Kesinti penceresi cok kisa (olcum: ~0.1 sn): 0.2 sn yeter,
            # agir durumda artar.
            time.sleep(min(1.5, 0.2 * attempt))
        return None, info
    finally:
        _unlink(tmp)
        if ephemeral:
            _unlink(dest)


def _curl_attempt(url, tmp, limit):
    """Tek curl denemesi.  Donus: (payload, info, yeniden_denenebilir)."""
    info = {'http': None, 'elapsed': 0.0, 'bytes': 0, 'error': None}
    cmd = [
        curl_bin(), "-sS", "--fail", "--location",
        "--connect-timeout", str(WB_CURL_CONNECT_TIMEOUT),
        "--max-time", str(limit),
        "-A", WB_USER_AGENT,
        "-H", "Accept: application/json",
        "-H", "Accept-Language: en-US,en;q=0.9",
        "-o", tmp,
        "-w", "%{http_code} %{time_total} %{size_download}",
        url,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=limit + 10)
    except (OSError, subprocess.SubprocessError) as exc:
        info['error'] = _short_error(exc)
        return None, info, True

    fields = (proc.stdout or "").split()
    if len(fields) >= 2:
        try:
            info['http'] = int(fields[0]) or None
            info['elapsed'] = float(fields[1])
            if len(fields) > 2:
                info['bytes'] = int(float(fields[2]))
        except ValueError:
            pass

    if proc.returncode != 0:
        lines = [ln for ln in (proc.stderr or "").strip().splitlines() if ln]
        reason = lines[-1] if lines else f"curl çıkış kodu {proc.returncode}"
        retryable = True
        if info['http']:
            reason = f"HTTP {info['http']}"
            retryable = info['http'] in RETRY_STATUS
        info['error'] = " ".join(reason.split())[:110]
        return None, info, retryable

    try:
        with open(tmp, encoding="utf-8") as fh:
            head = fh.read(64).lstrip()
        if head.startswith("<"):
            # API hatalari HTTP 200 ile XML govde dondurur; tekrar denemek
            # ayni sonucu verir.
            info['error'] = "API hata yanıtı (JSON değil)"
            return None, info, False
        payload = _read_json(tmp)
    except OSError as exc:
        info['error'] = _short_error(exc)
        return None, info, True
    if payload is None:
        info['error'] = "bozuk JSON"
        return None, info, False
    return payload, info, False


def _payload_rows(payload):
    """Yaniti (meta, rows, hata) olarak ayirir."""
    if not isinstance(payload, list) or not payload:
        return {}, [], "geçersiz API yanıtı"
    meta = payload[0] if isinstance(payload[0], dict) else {}
    if "message" in meta and len(payload) == 1:
        messages = meta.get("message") or []
        text = (messages[0].get("value")
                if messages and isinstance(messages[0], dict) else "")
        return meta, [], f"API hatası: {text or 'bilinmeyen hata'}"
    rows = (payload[1]
            if len(payload) > 1 and isinstance(payload[1], list) else [])
    return meta, rows, None


def diag(msg):
    """Vim tarafinda `--- getData.py:` satirlari adim olarak gosterilir."""
    print(f"--- getData.py: {msg}", flush=True)


def detail(msg):
    """Yalnizca [Wbfetch]/[Countryfetch] tamponunda gorunen ayrinti."""
    print(f"... getData.py: {msg}", flush=True)


def max_age_days():
    raw = (os.environ.get("NOTES_WB_REPORT_MAX_AGE_DAYS")
           or os.environ.get("NOTES_REPORT_MAX_AGE_DAYS") or "").strip()
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_MAX_AGE_DAYS


def _indicator_code_for(label):
    match = _INDICATOR_BY_BASE.get(wbt.norm(wbt.base_label(label)))
    return match[1] if match else None


def _row_year(label):
    match = re.search(r"\((\d{4})\)\s*$", label or "")
    return match.group(1) if match else ""


def _fill_year(label, year):
    """Replace {yearN} in a row label with *year*.

    With no year, drop the placeholder (and an empty trailing parenthesis)
    instead of leaving a literal {yearN} in the note.
    """
    label = label or ""
    if year:
        return YEAR_PLACEHOLDER_RE.sub(str(year), label)
    value = YEAR_PLACEHOLDER_RE.sub("", label)
    value = re.sub(r"\s*\(\s*\)\s*$", "", value)
    return value.strip()


def _missing(value):
    return (value is None or not str(value).strip()
            or wbt.norm(str(value)) == "veriyok")


def _meta(res):
    """Yanitin kisa tanilama eki (kaynak etiketi ayri yazilir)."""
    parts = []
    if res.get('http') is not None and not res.get('cached'):
        parts.append(f"HTTP {res['http']}")
    if res.get('lastupdated'):
        parts.append(f"WB {res['lastupdated']}")
    if res.get('elapsed') and not res.get('cached'):
        parts.append(f"{res['elapsed']:.2f} sn")
    if (res.get('attempts') or 1) > 1:
        parts.append(f"{res['attempts']} deneme")
    return " | ".join(parts)


def source_label(res):
    """`endpoint` ya da `önbellek (0.3 gün)` biciminde kaynak etiketi."""
    if not res.get('cached'):
        return "endpoint"
    label = "eski önbellek" if res.get('stale') else "önbellek"
    age = res.get('age')
    return f"{label} ({age:.1f} gün)" if age is not None else label


def _write_existing(path, idno, title, body, country_field, date, bib_abs,
                    author, keywords, modify):
    rel = os.path.relpath(bib_abs, nb.notes_dir())
    header = nb.build_header(idno, title, country_field, date, modify,
                             n_type="obn indicatorReport",
                             keywords=keywords or None,
                             bibfile=rel, author=author)
    nb.write_note_file(path, header + "\n" + body)
    print(f"Güncellendi: {path}", flush=True)


async def _translate(s, dest='tr'):
    async with Translator() as translator:
        return await translator.translate(s, dest=dest)


def translate_text(s):
    try:
        return asyncio.run(_translate(s)).text
    except Exception as exc:
        diag(f"UYARI çeviri başarısız, özgün metin kullanıldı: {exc}")
        return s


# --- Ulke kunyesi -----------------------------------------------------------
def _general_from_payload(payload, country, memo=None):
    """Ham ulke yanitindan tablo sozlugunu ve ceviri notunu uretir."""
    memo = dict(memo or {})
    if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
        return None, memo
    data = payload[1][0] if isinstance(payload[1], list) else {}
    if not isinstance(data, dict) or not data:
        return None, memo
    raw = {
        'Ülke': data.get('name') or country,
        'Bölge': ((data.get('region') or {}).get('value') or '—'),
        'Gelir Seviyesi': ((data.get('incomeLevel') or {}).get('value')
                           or '—'),
    }
    result = {}
    for key in GENERAL_KEYS:
        if key not in raw:
            result[key] = data.get('capitalCity') or '—'
            continue
        source = str(raw[key])
        known = memo.get(key) or {}
        if known.get('src') == source and known.get('text'):
            result[key] = known['text']
            continue
        text = translate_text(source)
        result[key] = text
        memo[key] = {'src': source, 'text': text}
    return result, memo


def fetch_general(country, data_dir, force=False, offline=False, memo=None):
    """Kunye: taze onbellekten, degilse curl ile.  Donus (data, info).

    `memo` onceki cevirilerdir (manifest.json); kaynak metin degismediyse
    Google'a yeniden gidilmez.
    """
    path = general_cache_path(data_dir)
    age = cache_age_days(path)
    limit = max_age_days()
    info = {'cached': False, 'age': age, 'http': None, 'elapsed': 0.0,
            'attempts': 1, 'lastupdated': '', 'error': None, 'memo': {}}

    if not force and age is not None and age < limit:
        data, memo = _general_from_payload(_read_json(path), country, memo)
        if data:
            info.update(cached=True, memo=memo)
            return data, info

    if offline:
        data, memo = _general_from_payload(_read_json(path), country, memo)
        if data:
            info.update(cached=True, stale=True, memo=memo)
            return data, info
        info['error'] = "önbellek yok (çevrimdışı)"
        return None, info

    payload, net = curl_json(f"{WB_API}/country/{country}?format=json", path)
    info.update(net)
    if payload is None:
        # Indirme dustu: elde bayat dosya varsa onu kullan.
        data, memo = _general_from_payload(_read_json(path), country, memo)
        if data:
            info.update(cached=True, stale=True, memo=memo)
            return data, info
        return None, info

    data, memo = _general_from_payload(payload, country, memo)
    if not data:
        info['error'] = "ülke künyesi boş"
        return None, info
    info.update(age=cache_age_days(path), memo=memo)
    return data, info


# --- Gostergeler ------------------------------------------------------------
def indicator_url(country, code):
    """Tek gosterge, en son dolu gozlem.  `mrnev` cok kodla calismaz."""
    return (f"{WB_API}/country/{country}/indicator/{code}"
            f"?format=json&mrnev=1")


def _indicator_from_payload(payload, code):
    """Ham gosterge yanitini tek sonuca indirger."""
    meta, rows, error = _payload_rows(payload)
    if error:
        return None
    result = {
        'indicator': code,
        'code': code,
        'value': None,
        'year': None,
        'status': 'missing',
        'lastupdated': meta.get('lastupdated') or '',
        'observations': len(rows),
        'mrnev': True,
        'error': None,
    }
    if not rows:
        return result
    result['indicator'] = ((rows[0].get('indicator') or {}).get('value')
                           or code)
    for item in rows:
        if item.get('value') is None:
            continue
        try:
            result['value'] = nb.human_format(float(item['value']))
            result['year'] = f"{item.get('date', '')}"
            result['status'] = 'ok'
        except (TypeError, ValueError):
            result['status'] = 'error'
            result['error'] = f"sayı çözümlenemedi: {item.get('value')!r}"
        break
    return result


def _error_result(code, info, note='bilinmeyen hata'):
    return {
        'indicator': code, 'code': code, 'value': None, 'year': None,
        'status': 'error', 'http': info.get('http'),
        'lastupdated': '', 'elapsed': info.get('elapsed') or 0.0,
        'observations': 0, 'attempts': info.get('attempts') or 1,
        'mrnev': True, 'cached': False, 'age': None,
        'error': info.get('error') or note,
    }


def fetch_indicator(country, code, data_dir, force=False, offline=False):
    """Tek gosterge: taze dosyadan, degilse curl ile.  Donus: sonuc sozlugu.

    Dosya yasi sinirin altindaysa aga hic cikilmaz.  Indirme duserse elde
    bayat dosya varsa o kullanilir (status 'ok', `stale` isaretli), boylece
    gecici bir kesinti tabloyu "veri yok"a dusurmez.
    """
    path = indicator_cache_path(data_dir, code)
    age = cache_age_days(path)
    limit = max_age_days()

    if not force and age is not None and age < limit:
        res = _indicator_from_payload(_read_json(path), code)
        if res is not None:
            res.update(http=None, elapsed=0.0, attempts=1,
                       cached=True, age=age)
            return res

    if offline:
        res = _indicator_from_payload(_read_json(path), code)
        if res is not None:
            res.update(http=None, elapsed=0.0, attempts=1,
                       cached=True, stale=True, age=age)
            return res
        return _error_result(code, {'error': 'önbellek yok (çevrimdışı)'})

    payload, info = curl_json(indicator_url(country, code), path)
    res = _indicator_from_payload(payload, code)
    if res is not None:
        res.update(http=info['http'], elapsed=info['elapsed'],
                   attempts=info['attempts'], cached=False,
                   age=cache_age_days(path))
        return res

    res = _indicator_from_payload(_read_json(path), code)
    if res is not None:
        res.update(http=info.get('http'), elapsed=info.get('elapsed') or 0.0,
                   attempts=info.get('attempts') or 1,
                   cached=True, stale=True, age=age)
        return res
    return _error_result(code, info)


def read_indicator_values(path):
    """Mevcut gosterge notunun tablosundaki degerleri ve yillari okur.

    Donus: {base_label_norm: {"value": ..., "year": "YYYY" veya ""}}.
    Yil anahtari etiketten okunur; eski notlarda bu sembolik sablon yili
    olabilir, yeni notlarda endpoint yilidir.
    """
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return {}
    _, body_lines = wbt.split_frontmatter(text)
    before, _ = nb.split_backrefs("\n".join(body_lines))
    parsed = wbt.find_indicator_table(before)
    if not parsed:
        return {}
    data = {}
    for row in parsed.get("rows", []):
        if len(row) < 2:
            continue
        label = row[0]
        key = wbt.norm(wbt.base_label(label))
        if not key:
            continue
        data[key] = {"value": row[1], "year": _row_year(label)}
    return data


def read_general_data(path):
    """<Ulke> Ilk Bakis notundaki genel ulke tablosunu okur."""
    if not path:
        return None
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return None
    _, body_lines = wbt.split_frontmatter(text)
    before, _ = nb.split_backrefs("\n".join(body_lines))
    for _start, _end, headers, rows in wbt.tables(before):
        if len(headers) < 4 or wbt.norm(headers[0]) != "ulke" or not rows:
            continue
        row = rows[0]
        if len(row) < 4:
            continue
        data = dict(zip(headers, row))
        if all((data.get(k) or "").strip() for k in GENERAL_KEYS):
            return {k: data[k] for k in GENERAL_KEYS}
    return None


def collect_indicators(country, data_dir, template, existing, incremental,
                       offline=False):
    """Sablon satirlarina karsilik gelen gostergeleri dondurur.

    Her gosterge kendi dosyasindan beslenir: dosya taze ise aga cikilmaz,
    suresi dolmussa yalnizca o dosya yenilenir.  Tam modda (--force) yas
    siniri yok sayilir, `offline` modda hic indirilmez.  Yillar endpoint'ten
    gelir; sablon yili yalnizca etikettir ve dogrulama yapilmaz.

    Donus: (degerler, yillar, istatistikler, kod -> satir ozeti).
    """
    total = len(indicatorCodesWB)
    rows = []
    row_by_code = {}
    for label, _turkey in template["rows"]:
        code = _indicator_code_for(label)
        row = {'label': label, 'code': code,
               'key': wbt.norm(wbt.base_label(label))}
        rows.append(row)
        if code:
            row_by_code.setdefault(code, row)
    chosen_keys = {row['key'] for row in row_by_code.values()}

    values = {}
    years = {}
    per_code = {}
    stats = {'cached': 0, 'fetched': 0, 'stale': 0, 'missing': 0,
             'error': 0, 'skipped': 0, 'unmatched': 0, 'retried': 0}

    consecutive = 0
    net_down = False
    for idx, (label, code) in enumerate(indicatorCodesWB.items(), 1):
        row = row_by_code.get(code)
        if row is None:
            diag(f"[{idx:2d}/{total}] {label} ({code}) — "
                 "şablonda satır yok (atlandı)")
            stats['skipped'] += 1
            continue

        key = row['key']
        old = existing.get(key) or {}
        old_value = old.get('value')
        old_year = old.get('year') or ''

        if net_down:
            res = _error_result(
                code, {'error': 'ağ erişilemiyor (üst üste düşen istekler)'})
        else:
            detail(f"[{idx:2d}/{total}] {label} ({code}) — istek gönderildi")
            res = fetch_indicator(country, code, data_dir,
                                  force=not incremental, offline=offline)
            if res['status'] == 'error':
                consecutive += 1
                if consecutive >= WB_MAX_CONSECUTIVE_ERRORS:
                    net_down = True
                    detail(f"ağ erişilemiyor: {consecutive} gösterge üst üste "
                           "düştü; kalanlar istenmeden işaretlenecek")
            else:
                consecutive = 0

        suffix = _meta(res)
        meta = f" | {suffix}" if suffix else ""
        stats['retried'] += max(0, (res.get('attempts') or 1) - 1)

        if res['status'] == 'ok':
            value = wbt.format_value(row['label'], res['value'])
            values[key] = value
            if res['year']:
                years[key] = res['year']
            if res.get('cached'):
                stats['cached'] += 1
                if res.get('stale'):
                    stats['stale'] += 1
            else:
                stats['fetched'] += 1
            per_code[code] = {
                'label': label, 'value': res['value'], 'year': res['year'],
                'cell': value, 'source': source_label(res),
                'wb_lastupdated': res.get('lastupdated') or '',
            }
            diag(f"[{idx:2d}/{total}] {label} ({code}) — "
                 f"{source_label(res)}: {value} "
                 f"({res['year']}){meta}")
            continue

        if res['status'] == 'missing':
            stats['missing'] += 1
            reason = "veri yok"
        else:
            stats['error'] += 1
            reason = f"HATA: {res.get('error') or 'bilinmeyen hata'}"

        if not _missing(old_value):
            values[key] = old_value
            if old_year:
                years[key] = old_year
            diag(f"[{idx:2d}/{total}] {label} ({code}) — {reason}{meta}; "
                 "eski değer korundu")
        else:
            values[key] = 'veri yok'
            if old_year:
                years[key] = old_year
            diag(f"[{idx:2d}/{total}] {label} ({code}) — {reason}{meta}")

    # Sablonda olup indicatorCodesWB ile eslesmeyen satirlar (ve yinelenen
    # kodlar) endpoint'e gitmez; mevcut deger varsa korunur.
    for row in rows:
        if row['key'] in chosen_keys:
            continue
        key = row['key']
        old = existing.get(key) or {}
        old_value = old.get('value')
        old_year = old.get('year') or ''
        if not _missing(old_value):
            values[key] = old_value
            if old_year:
                years[key] = old_year
            diag(f"    {row['label']} — eşleşen gösterge kodu yok; "
                 f"nottan: {old_value}")
        elif row['code'] and row['code'] in row_by_code:
            primary_key = row_by_code[row['code']]['key']
            values[key] = values.get(primary_key, 'veri yok')
            if years.get(primary_key):
                years[key] = years[primary_key]
            diag(f"    {row['label']} — yinelenen gösterge satırı; "
                 "birincil satırdan kullanıldı")
        else:
            values[key] = 'veri yok'
            if old_year:
                years[key] = old_year
            diag(f"    {row['label']} — eşleşen gösterge kodu yok; veri yok")
        stats['unmatched'] += 1

    return values, years, stats, per_code


# --- Manifest ---------------------------------------------------------------
def read_manifest(data_dir):
    data = _read_json(manifest_path(data_dir))
    return data if isinstance(data, dict) else {}


def write_manifest(data_dir, data):
    path = manifest_path(data_dir)
    _ensure_dir(os.path.dirname(path))
    tmp = f"{path}.{os.getpid()}.part"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except OSError as exc:
        _unlink(tmp)
        diag(f"UYARI manifest yazılamadı: {_short_error(exc)}")


def cache_state(data_dir, codes):
    """Onbellek ozeti: kac dosya var, kaci bayat, en eski/yeni yas.

    Yalnizca sablonun kullandigi kodlar sayilir; sablonda satiri olmayan
    gosterge hic indirilmedigi icin "eksik" sayilmamali.
    """
    limit = max_age_days()
    paths = [general_cache_path(data_dir)]
    paths += [indicator_cache_path(data_dir, code) for code in codes]
    ages = []
    for path in paths:
        age = cache_age_days(path)
        if age is not None:
            ages.append(age)
    stale = sum(1 for age in ages if age >= limit) + (len(paths) - len(ages))
    return {'total': len(paths), 'files': len(ages), 'stale': stale,
            'oldest': max(ages) if ages else None,
            'newest': min(ages) if ages else None}


def general_body(gdata):
    table = md_table([gdata]).set_params(row_sep='markdown').get_markdown()
    table = table.replace('```', '').strip()
    return table + "\n\n## Kaynaklar:\n\n    Dünya Bankası Verileri"


def _entry(found, title):
    return found.get(nb.slugify(title))


def _bib_abs(info, idno, box):
    value = (info.get("bibliography", "") or "").strip().strip('"\'')
    if value:
        return (value if os.path.isabs(value)
                else os.path.abspath(os.path.join(box, value)))
    return nb.bib_path(idno)


def _bib_key(path):
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return ""
    match = re.search(r"@\w+\{([^,]+),", text)
    return match.group(1).strip() if match else ""


def ping(country):
    """Endpoint erisimini dener; ne not ne onbellek yazar."""
    print(f"Deneme: {http_retries()} (NOTES_WB_HTTP_RETRIES)", flush=True)
    print(f"curl: {curl_bin()}", flush=True)

    payload, info = curl_json(f"{WB_API}/country/{country}?format=json")
    if payload is None:
        print(f"API: ERİŞİLEMEDİ — {info.get('error')}", flush=True)
        return 1
    retry = info['attempts'] - 1
    print(f"API: OK — HTTP {info['http']} | {info['elapsed']:.2f} sn"
          + (f" | {retry + 1} deneme" if retry else ""), flush=True)

    failed = 0
    for label, code in indicatorCodesWB.items():
        payload, info = curl_json(indicator_url(country, code))
        res = _indicator_from_payload(payload, code)
        retry = f" | {info['attempts']} deneme" if info['attempts'] > 1 else ""
        if res is None:
            failed += 1
            print(f"  {label} ({code}) — HATA: "
                  f"{info.get('error')}{retry}", flush=True)
        elif res['status'] == 'ok':
            print(f"  {label} ({code}) — {res['year']} | "
                  f"{wbt.format_value(label, res['value'])}{retry}",
                  flush=True)
        else:
            failed += 1
            print(f"  {label} ({code}) — {res['status']}{retry}", flush=True)
    return 1 if failed else 0


def main():
    flags, positional = set(), []
    for a in sys.argv[1:]:
        if a.startswith("--"):
            flags.add(a)
        else:
            positional.append(a)
    arg = " ".join(positional) if positional else "TUR"
    iso3, display, country_field = nb.resolve_country(arg)
    data_dir = wb_data_dir(cache_key(iso3, country_field))

    if "--delete" in flags:
        code = nb.delete_country_type(iso3, "obn indicatorReport", "gosterge",
                                      country_field, display)
        if "--delete-data" in flags:
            removed, files, size = nb.remove_wb_cache(iso3, country_field)
            if removed:
                print(f"Silindi: {data_dir} "
                      f"({files} JSON, {nb.human_size(size)})", flush=True)
        elif os.path.isdir(data_dir):
            files, size = nb.wb_cache_stats(data_dir)
            print(f"Korundu: {data_dir} "
                  f"({files} JSON, {nb.human_size(size)})", flush=True)
        return code

    api_country = iso3 if iso3 else country_field.upper()
    print(f"Ülke: {display}" + (f" ({iso3})" if iso3 else ""), flush=True)

    force = "--force" in flags
    offline = "--rebuild" in flags
    if "--clear-cache" in flags and nb.remove_wb_cache(iso3, country_field)[0]:
        diag(f"Önbellek silindi: {os.path.relpath(data_dir, nb.notes_dir())}")

    if "--ping" in flags:
        return ping(api_country)

    box = nb.notes_dir()
    max_age = max_age_days()

    # Sablon once yuklenir: onbellek sayimi yalnizca sablonun kullandigi
    # gostergeleri kapsar (sablonda satiri olmayan kod hic indirilmez).
    template_path = wbt.find_template(box)
    template = wbt.parse_template(template_path) if template_path else None
    template_codes = []
    if template:
        for label, _turkey in template["rows"]:
            code = _indicator_code_for(label)
            if code and code not in template_codes:
                template_codes.append(code)
    else:
        template_codes = list(dict.fromkeys(indicatorCodesWB.values()))

    state = cache_state(data_dir, template_codes)
    if force:
        mode, reason = "full", "--force"
    elif offline:
        mode, reason = "rebuild", "--rebuild: yalnızca önbellek"
    elif state['files'] == 0:
        mode, reason = "full", "önbellek yok"
    elif state['stale']:
        mode, reason = "incremental", \
            f"{state['stale']}/{state['total']} dosya {max_age} günden eski"
    else:
        mode, reason = "incremental", "önbellek taze"
    incremental = mode != "full"

    title_first = f"{display} İlk Bakış"
    title_legacy = f"{display} WorldBank Göstergeleri"
    title_second = f"{display} Temel Ekonomik Göstergeler"

    found, _ = nb.find_country_files(country_field, display,
                                     ("obn indicatorReport",))
    entry_first = _entry(found, title_first)
    entry_legacy = _entry(found, title_legacy)
    entry_second = _entry(found, title_second)
    chosen_first = entry_first or entry_legacy

    if "--check" in flags:
        fresh = (state['stale'] == 0 and state['files'] == state['total'])
        print(f"WB_DATA_DIR: {data_dir}")
        print(f"WB_DATA_REL: {os.path.relpath(data_dir, box)}")
        print(f"WB_DATA_EXISTS: {1 if os.path.isdir(data_dir) else 0}")
        print(f"WB_DATA_FILES: {state['files']}/{state['total']}")
        print("WB_DATA_AGE_DAYS: "
              + ("" if state['oldest'] is None
                 else f"{state['oldest']:.1f}"))
        print("WB_DATA_NEWEST_DAYS: "
              + ("" if state['newest'] is None
                 else f"{state['newest']:.1f}"))
        print(f"WB_STALE: {state['stale']}/{state['total']}")
        print(f"WB_MAX_AGE_DAYS: {max_age}")
        print(f"WB_MODE: {mode}")
        print(f"REPORT_EXISTS: {entry_second['path'] if entry_second else ''}")
        print(f"REPORT_FRESH: {1 if fresh else 0}")
        if fresh:
            text = f"{title_second} önbelleği taze."
        elif state['files'] == 0:
            text = f"{title_second} için önbellek yok."
        else:
            text = (f"{title_second}: {state['stale']}/{state['total']} "
                    "gösterge dosyası yenilenecek.")
        print(f"REPORT_AGE_TEXT: {text}")
        return 0

    rel_data = os.path.relpath(data_dir, box)
    if entry_second:
        diag(f"Not: {entry_second['path']} — veri: {rel_data}")
    else:
        diag(f"Gösterge notu yok — veri: {rel_data}")
    diag(f"Mod: {mode} — {reason}")

    try:
        if not template_path:
            print("HATA getData: şablon notu bulunamadı "
                  f"({wbt.TEMPLATE_TITLE})", flush=True)
            return 1

        manifest = read_manifest(data_dir)
        gtext = (manifest.get('general') or {}).get('text') or {}
        gdata = None
        ginfo = {}
        try:
            gdata, ginfo = fetch_general(api_country, data_dir, force=force,
                                         offline=offline, memo=gtext)
        except Exception as exc:
            ginfo = {'error': _short_error(exc), 'cached': False}

        general_error = 0
        if gdata:
            gtext = ginfo.get('memo') or gtext
            suffix = _meta(ginfo)
            diag(f"Genel künye — {source_label(ginfo)}: "
                 + " / ".join(gdata[k] for k in GENERAL_KEYS)
                 + (f" | {suffix}" if suffix else ""))
        else:
            if chosen_first:
                gdata = read_general_data(chosen_first["path"])
            if not gdata:
                print("HATA getData: ülke künyesi alınamadı — "
                      f"{ginfo.get('error') or 'bilinmeyen hata'}", flush=True)
                return 1
            general_error = 1
            diag("Genel künye — endpoint'e ulaşılamadı "
                 f"({ginfo.get('error')}); nottan kullanıldı")

        existing = read_indicator_values(entry_second["path"]) \
            if entry_second else {}
        values, years, stats, per_code = collect_indicators(
            api_country, data_dir, template, existing,
            incremental=incremental, offline=offline)
        errors = stats['error'] + general_error

        write_manifest(data_dir, {
            'iso3': iso3 or '',
            'country': api_country,
            'data_dir': rel_data,
            'updated': dt.datetime.now().isoformat(timespec="seconds"),
            'max_age_days': max_age,
            'mode': mode,
            'general': {
                'file': WB_GENERAL_FILE,
                'mtime': _mtime(general_cache_path(data_dir)),
                'cached': bool(ginfo.get('cached')),
                'wb_lastupdated': ginfo.get('lastupdated') or '',
                'values': gdata,
                'text': gtext,
            },
            'indicators': {
                code: dict(
                    file=os.path.join(WB_INDICATORS_SUBDIR, f"{code}.json"),
                    mtime=_mtime(indicator_cache_path(data_dir, code)),
                    **info)
                for code, info in per_code.items()
            },
        })

        #source_url = "https://data.worldbank.org"
        source_url = "https://api.worldbank.org/v2"
        today = dt.date.today().strftime("%d/%m/%y")
        used = set()
        existing_ids = set()

        body_first = general_body(gdata)

        if chosen_first:
            info1 = nb.parse_front_matter(chosen_first["path"])
            id1 = chosen_first["id"]
            path1 = chosen_first["path"]
            date1 = chosen_first["date"] or today
            bib1 = _bib_abs(info1, id1, box)
            key1 = _bib_key(bib1) or nb.bib_key(title_first, display, iso3)
            if not os.path.exists(bib1):
                os.makedirs(os.path.dirname(bib1), exist_ok=True)
                with open(bib1, "w", encoding="utf-8") as fh:
                    fh.write(nb.bib_entry(
                        key1, title_first, source_url, "Dünya Bankası",
                        "World Bank Open Data"))
            if errors:
                # Hata varsa modify hic ilerlemez (bos kalabilir): sonraki
                # calisma eksikleri yas beklemeden yeniden dener.
                modify1 = info1.get("modify") or ""
            else:
                modify1 = today
            _write_existing(path1, id1, title_first,
                            body_first + f"\n\n@{key1}\n", country_field,
                            date1, bib1, info1.get("author") or "getData",
                            info1.get("keywords", ""), modify1)
            if entry_first and entry_legacy:
                diag("UYARI eski başlıklı not da duruyor: "
                     f"{entry_legacy['path']}")
        else:
            path1, _ = nb.emit_note(
                display, iso3, title_first, "obn indicatorReport",
                body_first, source_url, country_field, used, existing_ids,
                bib_author="Dünya Bankası",
                bib_howpublished="World Bank Open Data")
            info1 = nb.parse_front_matter(path1)
            id1 = info1.get("id") or \
                os.path.splitext(os.path.basename(path1))[0]
            bib1 = _bib_abs(info1, id1, box)
            key1 = _bib_key(bib1) or nb.bib_key(title_first, display, iso3)

        try:
            used.add(int(id1))
        except (TypeError, ValueError):
            pass

        # Karsilastirma tablosunun atif anahtarini birinci notun anahtariyla
        # eslestir.  Sablon satirlarindaki {yearN} yer tutuculari endpoint
        # yiliyla doldurulur; degerler base label ile eslesir.
        display_rows = []
        for label, turkey in template["rows"]:
            row_key = wbt.norm(wbt.base_label(label))
            display_rows.append((_fill_year(label, years.get(row_key)),
                                 turkey))
        table_template = dict(template)
        table_template["rows"] = display_rows
        table, caption, footnotes = wbt.build_comparison(
            table_template, display, values, key1)
        body_second = wbt.build_body(table, caption, footnotes)

        if entry_second:
            info2 = nb.parse_front_matter(entry_second["path"])
            id2 = entry_second["id"]
            path2 = entry_second["path"]
            date2 = entry_second["date"] or today
            bib2 = _bib_abs(info2, id2, box)
            os.makedirs(os.path.dirname(bib2), exist_ok=True)
            if os.path.abspath(bib1) != os.path.abspath(bib2):
                shutil.copyfile(bib1, bib2)
            if errors:
                modify2 = info2.get("modify") or ""
            else:
                modify2 = today
            _write_existing(path2, id2, title_second, body_second,
                            country_field, date2, bib2,
                            info2.get("author") or "getData",
                            info2.get("keywords", ""), modify2)
        else:
            id2 = str(nb.unique_id(used, existing_ids))
            path2 = os.path.join(box, f"{id2}.md")
            bib2 = nb.bib_path(id2)
            os.makedirs(os.path.dirname(bib2), exist_ok=True)
            shutil.copyfile(bib1, bib2)
            rel2 = os.path.relpath(bib2, box)
            # Hatali ilk uretimde modify bos kalir: sonraki calisma tam
            # yenileme yapar (emit_note de yeni notta boyle davranir).
            modify2 = today if not errors else ""
            header = nb.build_header(
                id2, title_second, country_field, None, modify2 or None,
                n_type="obn indicatorReport", bibfile=rel2, author="getData")
            nb.write_note_file(path2, header + "\n" + body_second)
            print(f"Yazıldı: {path2}", flush=True)

        mode_text = {"full": "tam yenileme", "rebuild": "önbellekten",
                     "incremental": "artımlı"}[mode]
        extra = ""
        if stats['unmatched']:
            extra = f"; {stats['unmatched']} eşleşmeyen satır"
        if stats['stale']:
            extra += f"; {stats['stale']} eski önbellek"
        if stats['retried']:
            extra += f"; {stats['retried']} yeniden deneme"
        if errors and not offline:
            extra += "; modify korundu (sonraki çalışma yeniden dener)"
        diag(f"ÖZET ({mode_text}): {len(indicatorCodesWB)} gösterge — "
             f"{stats['cached']} önbellek, {stats['fetched']} endpoint, "
             f"{stats['missing']} veri yok, {stats['error']} hata, "
             f"{stats['skipped']} atlandı{extra}; modify {modify2 or 'yok'}; "
             f"veri {rel_data}")

        idx_path, _ = nb.write_country_index(display, iso3, "gosterge",
                                             country_field, used, existing_ids)
    except Exception as exc:
        print(f"HATA getData: {_short_error(exc)}", flush=True)
        return 1
    print(f"INDEX: {idx_path}", flush=True)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
