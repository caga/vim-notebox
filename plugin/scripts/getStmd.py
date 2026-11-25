#!/home/osman/.vim/plugged/vim-notebox/plugin/scripts/venv/bin/python3
# -*- coding: utf-8 -*-
"""Bir ulkenin tek tarafli dis ticaret raporunu (Trade Map) uretir ve not
kutusuna standart not olarak yazar.

Kullanim:
    ./getStmd.py Nepal
    ./getStmd.py NPL --box ~/countryNotes
    ./getStmd.py Türkiye --force
    ./getStmd.py Türkiye --check

Secenekler:
    --box DIR   not kutusu (varsayilan: $NOTES_DIR veya cwd)
    --check     yalnizca mevcut raporun yasini bildir (ag erisimi yok)
    --force     tazelik esigini yok say ve yeniden uret
    --delete    ulkenin dis ticaret notlarini sil
"""

import asyncio
import re
import sys
import time
from urllib.parse import urljoin

import _cli

_cli.init()

import requests
from bs4 import BeautifulSoup
from googletrans import Translator
from tabulate import tabulate

import cnlook as lu
import notebox as nb

TRADE_MAP_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (X11; Linux x86_64) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/131.0.0.0 Safari/537.36'),
}
TRADE_MAP_HOME = "https://legacy.trademap.org/Index.aspx"
TRADE_TYPE = {"1": "I", "2": "E"}
COUNTRY_SELECT_RE = re.compile(
    r'<select[^>]*DropDownList_Country"[^>]*>.*?'
    r'<option selected="selected" value="(\d+)"', re.S)
TRADE_TYPE_RE = re.compile(
    r'<select[^>]*DropDownList_TradeType"[^>]*>.*?'
    r'<option selected="selected" value="([EIB])"', re.S)
FORM_ACTION_RE = re.compile(r'localtheForm\.action\s*=\s*"([^"]+)"')
COUNTRY_EVENT_TARGET = 'ctl00$NavigationControl$DropDownList_Country'
VIEW_RETRY_ATTEMPTS = 3
VIEW_RETRY_PAUSE = 0.2


def trade_map_session():
    """Trade Map icin cerez isitmali yeni oturum.

    Site cerezsiz istegi `AspxAutoDetectCookieSupport=1` ile Index.aspx'e
    yonlendiriyor ve veri sayfasi bos donuyor; isitma bunu onler.
    """
    return nb.http_session(headers=TRADE_MAP_HEADERS, warmup=TRADE_MAP_HOME)


def _view_state(html):
    """(ulke kodu, ticaret yonu) - sayfada secili olan degerler."""
    country = COUNTRY_SELECT_RE.search(html)
    flow = TRADE_TYPE_RE.search(html)
    return (int(country.group(1)) if country else None,
            flow.group(1) if flow else None)


def _view_ok(html, country_code, impex):
    got_code, got_flow = _view_state(html)
    return got_code == int(country_code) and got_flow == TRADE_TYPE[impex]


def check_view(html, country_code, impex):
    """Sayfa istenen ulkeyi ve ticaret yonunu mu gosteriyor?

    Trade Map anonim oturumda `nvpm` parametrelerini yok sayiyor: oturum
    hangi gorunumle acildiysa (varsayilan Turkiye/ithalat) onu donduruyor.
    Yanlis veriyi istenen ulkenin notuna yazmamak icin gorunum burada
    dogrulanir; uymuyorsa islem durur.
    """
    if _view_ok(html, country_code, impex):
        return
    got_code, got_flow = _view_state(html)
    want_flow = TRADE_TYPE[impex]
    raise RuntimeError(
        f"Trade Map istenen görünümü vermedi (istenen ülke {country_code}, "
        f"ticaret yönü {want_flow}; gelen ülke {got_code}, yön {got_flow})"
        " — site nvpm parametrelerini yok sayıp oturumdaki görünümü "
        "döndürüyor")


def _form_payload(form):
    """ASP.NET formunun mevcut degerlerini POST verisine cevirir."""
    data = {}
    for inp in form.find_all('input'):
        name = inp.get('name')
        if not name:
            continue
        kind = (inp.get('type') or 'text').lower()
        if kind in ('submit', 'button', 'image', 'reset', 'file'):
            continue
        if kind in ('radio', 'checkbox'):
            if inp.has_attr('checked'):
                data[name] = inp.get('value', 'on')
        else:
            data[name] = inp.get('value', '')
    for select in form.find_all('select'):
        name = select.get('name')
        if not name:
            continue
        options = select.find_all('option')
        selected = next((o.get('value') for o in options
                         if o.has_attr('selected')), None)
        if selected is None and options:
            selected = options[0].get('value', '')
        data[name] = selected if selected is not None else ''
    return data


def _form_action(response, form):
    """Formun gercek POST adresi (sayfadaki localtheForm.action)."""
    match = FORM_ACTION_RE.search(response.text)
    action = match.group(1) if match else (form.get('action') or response.url)
    return urljoin(response.url, action)


def select_view(session, response, country_code, impex,
                attempts=VIEW_RETRY_ATTEMPTS):
    """Ulkeyi ASP.NET postback'i ile secer ve dogrulanmis yaniti dondurur.

    Legacy Trade Map `nvpm` ile ulke degistirmeyi anonim oturumda yok sayar;
    secim ancak form postback'i ile yapilir.  Ilk POST oturumu Index.aspx'e
    yonlendirir, ayni POST'un tekrari istenen gorunumu dondurur.
    """
    if _view_ok(response.text, country_code, impex):
        return response
    soup = BeautifulSoup(response.text, 'html.parser')
    form = soup.find('form', {'name': 'aspnetForm'})
    if form is None:
        raise RuntimeError("Trade Map ülke seçim formu bulunamadı")
    action = _form_action(response, form)
    data = _form_payload(form)
    data['__EVENTTARGET'] = COUNTRY_EVENT_TARGET
    data['__EVENTARGUMENT'] = ''
    data['ctl00$NavigationControl$DropDownList_Country'] = country_code
    data['ctl00$NavigationControl$Country_Selection'] = 'RadioButton_Country'
    data['ctl00$NavigationControl$DropDownList_TradeType'] = TRADE_TYPE[impex]
    data['ctl00$NavigationControl$DropDownList_Product'] = 'TOTAL'

    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            response = session.post(action, data=data, timeout=60)
        except requests.RequestException as exc:
            last_error = exc
        else:
            if _view_ok(response.text, country_code, impex):
                return response
            last_error = None
        if attempt < attempts:
            time.sleep(VIEW_RETRY_PAUSE * attempt)
    if last_error is not None:
        raise last_error
    check_view(response.text, country_code, impex)
    return response


async def _translate(s, src='en', dest='tr'):
    async with Translator() as translator:
        return await translator.translate(s, dest=dest)


def translate_text(s):
    try:
        return asyncio.run(_translate(s)).text
    except Exception:
        return s


def getProductSoup(country='TUR', impex='1'):
    headers = TRADE_MAP_HEADERS
    countryIso3166Code = lu.iso3ToNumeric(country)
    if countryIso3166Code == 1:
        print("Country not Found")
        return 1
    if impex not in ('1', '2'):
        print("Wrong impex value! Should be 1 or 2 as string")
        return 1
    url = (f"https://legacy.trademap.org/Product_SelCountry_TS.aspx?"
           f"nvpm=1%7c{countryIso3166Code}%7c%7c%7c%7cTOTAL%7c%7c%7c2%7c1%7c1%7c{impex}"
           "%7c2%7c1%7c1%7c1%7c%7c1")
    print("Connecting to trademap.org")
    session = trade_map_session()
    response = nb.http_get(url, headers=headers, timeout=60, session=session)
    response = select_view(session, response, countryIso3166Code, impex)
    soup = BeautifulSoup(response.text, 'html.parser')
    return soup


def extractProductData(soup: BeautifulSoup):
    dataSoup = soup.find_all('td', class_='tabContent')
    headers = [th.text for th in dataSoup[0].find_all('th')]
    year = headers[-1].split()[-1]
    th1 = "HS Kodu"
    th2 = "Ürün"
    th3 = f"Değer $({year})"
    th4 = "% Oran"
    rows = dataSoup[0].find_all('tr')
    rows = rows[3:]
    rowCol = rows[0].find_all('td')
    total = int(rowCol[7].text.split()[0].replace(',', '')) * 1000
    rows = rows[1:6]
    itemd = {}
    data = []
    for row in rows:
        rowCol = row.find_all('td')
        itemd[th1] = rowCol[1].text.split()[0]
        itemd[th2] = translate_text(rowCol[2].text)
        itemd[th3] = int(rowCol[7].text.split()[0].replace(',', '')) * 1000
        itemd[th4] = f"{round(itemd[th3] / total * 100, 1) if total else 0.0:.1f}"
        itemd[th3] = nb.human_format(itemd[th3])
        data.append(itemd.copy())
    total = nb.human_format(total)
    return total, year, data


def getCountrySoup(country='TUR', impex='1'):
    headers = TRADE_MAP_HEADERS
    countryIso3166Code = lu.iso3ToNumeric(country)
    if countryIso3166Code == 1:
        print("Country not Found")
        return 1
    if impex not in ('1', '2'):
        print("Wrong impex value! Should be 1 or 2 as string")
        return 1
    url = (f"https://legacy.trademap.org/Country_SelProductCountry_TS.aspx?"
           f"nvpm=1%7c{countryIso3166Code}%7c%7c%7c%7cTOTAL%7c%7c%7c2%7c1%7c1%7c{impex}"
           "%7c2%7c1%7c2%7c1%7c1%7c1")
    print("Connecting to trademap.org")
    session = trade_map_session()
    response = nb.http_get(url, headers=headers, timeout=60, session=session)
    response = select_view(session, response, countryIso3166Code, impex)
    soup = BeautifulSoup(response.text, 'html.parser')
    return soup


def extractCountryData(soup: BeautifulSoup):
    dataSoup = soup.find_all('table', id='ctl00_PageContent_MyGridView1')
    headers = [th.text for th in dataSoup[0].find_all('th')]
    year = headers[-1].split()[-1]
    th1 = "Ülke"
    th2 = f"Değer $({year})"
    th3 = "% Oran"
    rows = dataSoup[0].find_all('tr')
    rows = rows[3:]
    rowCol = rows[0].find_all('td')
    total = int(rowCol[-1].text.split()[0].replace(',', '')) * 1000
    rows = rows[1:6]
    itemd = {}
    data = []
    for row in rows:
        rowCol = row.find_all('td')
        itemd[th1] = translate_text(rowCol[1].text.replace('\n', ''))
        itemd[th2] = int(rowCol[6].text.split()[0].replace(',', '')) * 1000
        itemd[th3] = f"{round(itemd[th2] / total * 100, 1) if total else 0.0:.1f}"
        itemd[th2] = nb.human_format(itemd[th2])
        data.append(itemd.copy())
    total = nb.human_format(total)
    return total, year, data


def Table2(caption: str, data: list):
    widths = [20, 50, 30]
    tableCaption = f"\n:{caption}"
    tableBody = tabulate(data, headers="keys", tablefmt="grid",
                         numalign="left", maxcolwidths=widths)
    return tableBody + tableCaption


def getAllData(country: str):
    pimsoup = getProductSoup(f"{country}", '1')
    pimtotal, pimyear, pimdata = extractProductData(pimsoup)
    pexsoup = getProductSoup(f"{country}", '2')
    pextotal, pexyear, pexdata = extractProductData(pexsoup)
    cexsoup = getCountrySoup(f"{country}", '2')
    cextotal, cexyear, cexdata = extractCountryData(cexsoup)
    cimsoup = getCountrySoup(f"{country}", '1')
    cimtotal, cimyear, cimdata = extractCountryData(cimsoup)
    year = cimyear
    importVal = pimtotal
    exportVal = pextotal
    importPartners = cimdata
    exportPartners = cexdata
    importProducts = pimdata
    exportProducts = pexdata
    country = lu.iso3ToName(country)
    imEx = [{f"İthalat $({cimyear})": importVal, f"İhracat $({cexyear})": exportVal}]
    return country, imEx, importPartners, exportPartners, importProducts, exportProducts


def build_body(country):
    _, impEx, importPartners, exportPartners, importProducts, exportProducts = getAllData(country)
    imExTable = Table2("Toplam İthalat ve İhracat $", impEx)
    imPartTable = Table2("İlk Beş İthalat Ortakları", importPartners)
    exPartTable = Table2("İlk Beş İhracat Ortakları", exportPartners)
    imProTable = Table2("İlk Beş İthal Ürünleri", importProducts)
    exProTable = Table2("İlk Beş İhraç Ürünleri", exportProducts)
    Sep = "\n\n"
    #kaynak = "\n\n Kaynak: Trademap \n"
    return Sep.join([imExTable, imPartTable, exPartTable, imProTable, exProTable])


def _parse_flags(argv):
    flags, positional = set(), []
    for a in argv:
        if a.startswith("--"):
            flags.add(a)
        else:
            positional.append(a)
    return flags, positional


def _report_age_text(title, days, source):
    if days is None:
        return f"{title} (tarih bilgisi yok)."
    verb = "güncellendi" if source == "modify" else "oluşturuldu"
    return f"{title} {nb.human_age(days)} {verb}."


def _report(country_field, display, title, n_type):
    """(entry, days, source) - mevcut rapor notu (yoksa entry None)."""
    found, _ = nb.find_country_files(country_field, display, (n_type,))
    entry = found.get(nb.slugify(title))
    if not entry:
        return None, None, None
    days, source, _raw = nb.note_age(entry["path"])
    return entry, days, source


def main():
    flags, positional = _parse_flags(sys.argv[1:])
    arg = " ".join(positional) if positional else "TUR"
    iso3, display, country_field = nb.resolve_country(arg)
    if not iso3:
        print(f"Ülke ISO3 kodu çözülemedi: {arg}")
        return 1
    if "--delete" in flags:
        return nb.delete_country_type(iso3, "obn singletrade", "ticaret",
                                      country_field, display)
    title = f"{display} Dış Ticaret Rakamları"
    entry, days, source = _report(country_field, display, title, "obn singletrade")

    if "--check" in flags:
        if entry:
            fresh = days is not None and days < nb.REPORT_MAX_AGE_DAYS
            print(f"REPORT_EXISTS: {entry['path']}")
            print(f"REPORT_AGE_DAYS: {'' if days is None else days}")
            print(f"REPORT_AGE_SOURCE: {source}")
            print(f"REPORT_FRESH: {1 if fresh else 0}")
            print(f"REPORT_AGE_TEXT: {_report_age_text(title, days, source)}")
        return 0

    if (entry and days is not None and days < nb.REPORT_MAX_AGE_DAYS
            and "--force" not in flags):
        print(f"ATLANDI: {_report_age_text(title, days, source)} "
              f"({nb.REPORT_MAX_AGE_DAYS} günden yeni; yenilenmedi)")
        return 0

    print(f"Ülke: {display} ({iso3})")
    try:
        body = build_body(iso3)
    except Exception as exc:
        print(f"HATA getStmd: {exc}")
        return 1
    if not body:
        print(f"HATA getStmd: ticaret verisi bulunamadı ({display})")
        return 2

    source_url = "https://www.trademap.org/"
    used = set()
    existing_ids = set()
    try:
        nb.emit_note(display, iso3, title, "obn singletrade", body, source_url,
                     country_field, used, existing_ids,
                     bib_author="International Trade Centre (ITC)",
                     bib_howpublished="Trade Map")
        idx_path, _ = nb.write_country_index(display, iso3, "ticaret",
                                             country_field, used, existing_ids)
    except Exception as exc:
        print(f"HATA getStmd: {exc}")
        return 1
    print(f"INDEX: {idx_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
