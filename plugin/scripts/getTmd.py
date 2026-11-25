#!/home/osman/.vim/plugged/vim-notebox/plugin/scripts/venv/bin/python3
# -*- coding: utf-8 -*-
"""Iki ulke arasindaki ikili ticaret raporunu (Trade Map) uretir ve not
kutusuna standart not olarak yazar. Ortak ulke verilmezse varsayilan TUR'dur.

Kullanim:
    ./getTmd.py Nepal
    ./getTmd.py Nepal --box ~/countryNotes
    ./getTmd.py Nepal --force
    ./getTmd.py Nepal --check

Secenekler:
    --box DIR   not kutusu (varsayilan: $NOTES_DIR veya cwd)
    --check     yalnizca mevcut raporun yasini bildir (ag erisimi yok)
    --force     tazelik esigini yok say ve yeniden uret
    --delete    ulkenin ikili ticaret notlarini sil
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
PARTNER_SELECT_RE = re.compile(
    r'<select[^>]*DropDownList_Partner"[^>]*>.*?'
    r'<option selected="selected" value="(\d+)"', re.S)
TRADE_TYPE_RE = re.compile(
    r'<select[^>]*DropDownList_TradeType"[^>]*>.*?'
    r'<option selected="selected" value="([EIB])"', re.S)
FORM_ACTION_RE = re.compile(r'localtheForm\.action\s*=\s*"([^"]+)"')
PARTNER_EVENT_TARGET = 'ctl00$NavigationControl$DropDownList_Partner'
VIEW_RETRY_ATTEMPTS = 3
VIEW_RETRY_PAUSE = 0.2


def trade_map_session():
    """Trade Map icin cerez isitmali yeni oturum.

    Site cerezsiz istegi `AspxAutoDetectCookieSupport=1` ile Index.aspx'e
    yonlendiriyor ve veri sayfasi bos donuyor; isitma bunu onler.
    """
    return nb.http_session(headers=TRADE_MAP_HEADERS, warmup=TRADE_MAP_HOME)


def _view_state(html):
    """(ulke, partner, ticaret yonu) - sayfada secili olan degerler."""
    country = COUNTRY_SELECT_RE.search(html)
    partner = PARTNER_SELECT_RE.search(html)
    flow = TRADE_TYPE_RE.search(html)
    return (int(country.group(1)) if country else None,
            int(partner.group(1)) if partner else None,
            flow.group(1) if flow else None)


def _view_ok(html, country_code, partner_code, impex):
    got_code, got_partner, got_flow = _view_state(html)
    return (got_code == int(country_code)
            and got_partner == int(partner_code)
            and got_flow == TRADE_TYPE[impex])


def check_view(html, country_code, partner_code, impex):
    """Sayfa istenen ulke, partner ve ticaret yonunu mu gosteriyor?

    Trade Map anonim oturumda `nvpm` parametrelerini yok sayiyor: oturum
    hangi gorunumle acildiysa (varsayilan Turkiye/ithalat) onu donduruyor.
    Yanlis veriyi istenen ulkenin notuna yazmamak icin gorunum burada
    dogrulanir; uymuyorsa islem durur.
    """
    if _view_ok(html, country_code, partner_code, impex):
        return
    got_code, got_partner, got_flow = _view_state(html)
    want_flow = TRADE_TYPE[impex]
    raise RuntimeError(
        f"Trade Map istenen görünümü vermedi (istenen ülke {country_code}, "
        f"partner {partner_code}, ticaret yönü {want_flow}; gelen ülke "
        f"{got_code}, partner {got_partner}, yön {got_flow}) — site nvpm "
        "parametrelerini yok sayıp oturumdaki görünümü "
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


def select_view(session, response, country_code, partner_code, impex,
                attempts=VIEW_RETRY_ATTEMPTS):
    """Ulke/partner secimini ASP.NET postback'i ile yapar.

    Legacy Trade Map `nvpm` ile secim yapmayi anonim oturumda yok sayar;
    secim ancak form postback'i ile yapilir.  Ilk POST oturumu Index.aspx'e
    yonlendirir, ayni POST'un tekrari istenen gorunumu dondurur.
    """
    if _view_ok(response.text, country_code, partner_code, impex):
        return response
    soup = BeautifulSoup(response.text, 'html.parser')
    form = soup.find('form', {'name': 'aspnetForm'})
    if form is None:
        raise RuntimeError("Trade Map ülke/partner seçim formu bulunamadı")
    action = _form_action(response, form)
    data = _form_payload(form)
    data['__EVENTTARGET'] = PARTNER_EVENT_TARGET
    data['__EVENTARGUMENT'] = ''
    data['ctl00$NavigationControl$DropDownList_Country'] = country_code
    data['ctl00$NavigationControl$Country_Selection'] = 'RadioButton_Country'
    data['ctl00$NavigationControl$DropDownList_Partner'] = partner_code
    data['ctl00$NavigationControl$DropDownList_TradeType'] = TRADE_TYPE[impex]
    data['ctl00$NavigationControl$DropDownList_Product'] = 'TOTAL'

    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            response = session.post(action, data=data, timeout=60)
        except requests.RequestException as exc:
            last_error = exc
        else:
            if _view_ok(response.text, country_code, partner_code, impex):
                return response
            last_error = None
        if attempt < attempts:
            time.sleep(VIEW_RETRY_PAUSE * attempt)
    if last_error is not None:
        raise last_error
    check_view(response.text, country_code, partner_code, impex)
    return response


async def _translate(s, dest='tr'):
    async with Translator() as translator:
        return await translator.translate(s, dest=dest)


def translate_text(s):
    try:
        return asyncio.run(_translate(s)).text
    except Exception:
        return s


def connectAndGetSoup(country='TUR', partner='AUS', impex='1'):
    headers = TRADE_MAP_HEADERS
    countryIso3166Code = lu.iso3ToNumeric(country)
    partnerIso3166Code = lu.iso3ToNumeric(partner)
    if countryIso3166Code == 1:
        print("Country not Found")
        return 1
    if partnerIso3166Code == 1:
        print("Partner Country not Found")
        return 1
    if impex not in ('1', '2'):
        print("Wrong impex value! Should be 1 or 2 as string")
        return 1
    urlimport = (f"https://legacy.trademap.org/Bilateral_TS.aspx?"
                 f"nvpm=1%7c{countryIso3166Code}%7c%7c{partnerIso3166Code}%7c%7cTOTAL"
                 f"%7c%7c%7c2%7c1%7c1%7c{impex}%7c2%7c1%7c1%7c1%7c%7c1")
    print("Connecting to trademap.org")
    session = trade_map_session()
    response = nb.http_get(urlimport, headers=headers, timeout=60,
                           session=session)
    response = select_view(session, response, countryIso3166Code,
                           partnerIso3166Code, impex)
    soup = BeautifulSoup(response.text, 'html.parser')
    return soup


def extractDataFromSoup(soup: BeautifulSoup):
    data = []
    itemd = {}
    table = soup.find('table', id="ctl00_PageContent_MyGridView1")
    if table is None:
        return 'No Data'
    figures = table.find_all('td', title='Direct Data')
    if not figures:
        return 'No Data'
    tableHeaders = table.find_all('th')
    th1 = tableHeaders[1].text
    th2 = tableHeaders[2].text
    th3 = tableHeaders[3].text
    th4 = tableHeaders[4].text
    th5 = tableHeaders[5].text

    rvalues = [figures[i] for i in range(len(figures)) if i % 3 == 2]
    mvalues = [figures[i] for i in range(len(figures)) if i % 3 == 1]
    lvalues = [figures[i] for i in range(len(figures)) if i % 3 == 0]

    codesAndLabels = table.find_all('td', align='left')
    codes, labels = zip(*[(cl.text, codesAndLabels[i + 1].text)
                          for i, cl in enumerate(codesAndLabels) if i % 2 == 0])

    flag = 2
    finalValues = rvalues
    th_data = th5

    if rvalues[0].text == '\xa0':
        if mvalues[0].text != '\xa0':
            flag = 1
            th_data = th4
            finalValues = mvalues
        if mvalues[0].text == '\xa0':
            flag = 0
            th_data = th3
            finalValues = lvalues
    if finalValues[0].text == '\xa0' or not finalValues[0].text.strip():
        return 'No Data'

    for i in range(len(codes)):
        itemd[th1] = codes[i].replace('\n', '')
        itemd[th2] = labels[i]
        itemd[th_data] = int(finalValues[i].text.replace(',', '')) * 1000
        data.append(itemd.copy())
    return data


def extractAndSeperateDataForNproducts(soup, n: int):
    data = extractDataFromSoup(soup)
    if data == 'No Data' or not data:
        return None, None
    main = data[0]
    products = [product for product in data[1:n + 1]]
    k1, k2, k3 = products[0].keys()
    for product in products:
        product[k2] = translate_text(product[k2])
    return main, products


def allReportData(impsoup, expsoup, n: int):
    impTotal, impProducts = extractAndSeperateDataForNproducts(impsoup, n)
    expTotal, expProducts = extractAndSeperateDataForNproducts(expsoup, n)
    if impTotal is None or expTotal is None:
        return None, None, None, None
    return impTotal, expTotal, impProducts, expProducts


def mainTableMd(country: str, partner: str, impTotal: dict, expTotal: dict):
    lastkey = list(impTotal.keys())[-1]
    year = lastkey.split()[-1]
    impValue = impTotal[f"{lastkey}"]
    expValue = expTotal[f"{lastkey}"]
    tradeVolume = impValue + expValue

    impValue = nb.human_format(impValue)
    expValue = nb.human_format(expValue)
    tradeVolume = nb.human_format(tradeVolume)

    countryName = lu.iso3ToName(country)
    partnerName = lu.iso3ToName(partner)
    mainDict = {'İthalat $': impValue, 'İhracat $': expValue, 'Hacim $': tradeVolume}
    mainList = [mainDict]

    widths = [20, 50, 30]
    tableBody = tabulate(mainList, headers="keys", tablefmt="grid",
                         numalign="left", maxcolwidths=widths)
    tableCaption = f"\n:{countryName} - {partnerName} Dış Ticaret Rakamları $({year}) \n\n\n"
    return "\n" + tableBody + tableCaption


def rename_keys(d, key_mapping):
    new_dic = {}
    for old_key, value in d.items():
        new_key = key_mapping.get(old_key)
        new_dic[new_key] = value
    return new_dic


def thirdKeyHumanReadable(Products: list):
    k1, k2, k3, k4 = Products[0].keys()
    for product in Products:
        product[k3] = nb.human_format(product[k3])
    return Products


def tableHeadersTranslate(Data: list):
    k1, k2, k3 = Data[0].keys()
    year = k3.split()[-1]
    key_mapping = {k1: 'HS Kodu', k2: 'Ürün Tanımı', k3: f"Değer $({year})"}
    rData = []
    for data in Data:
        data = rename_keys(data, key_mapping)
        rData.append(data)
    return rData


def productTableMd(country: str, partner: str, Products: list, impex='1', totalValue=1):
    impexpString = "ithal" if impex == '1' else "ihraç"
    k1, k2, k3 = Products[0].keys()
    countryName = lu.iso3ToName(country)
    partnerName = lu.iso3ToName(partner)
    Products = tableHeadersTranslate(Products)
    k1, k2, k3 = Products[0].keys()
    k4 = '% Oran'
    for product in Products:
        share = (product[k3] / totalValue * 100) if totalValue else 0.0
        product[k4] = f"{share:.1f}"
    Products = thirdKeyHumanReadable(Products)

    widths = [20, 50, 30]
    tableBody = tabulate(Products, headers="keys", tablefmt="grid",
                         numalign="left", maxcolwidths=widths)
    tableCaption = f"\n:{countryName} - {partnerName} {impexpString} edilen ilk 5 ürün\n\n\n"
    return tableBody + tableCaption


def build_body(country: str, partner: str, impsoup, expsoup, n=5):
    impTotal, expTotal, impProducts, expProducts = allReportData(impsoup, expsoup, n)
    if impTotal is None or expTotal is None:
        return None
    k1, k2, k3 = impTotal.keys()
    N_impTotal = impTotal[k3]
    N_expTotal = expTotal[k3]
    mdReportString = mainTableMd(country, partner, impTotal, expTotal)
    for impexpFlag in range(2):
        impex = '1' if impexpFlag == 0 else '2'
        Products = impProducts if impexpFlag == 0 else expProducts
        totalImpExpValue = N_impTotal if impexpFlag == 0 else N_expTotal
        mdReportString = mdReportString + productTableMd(
            country, partner, Products, impex, totalImpExpValue)
    kaynak = "\n\n Kaynak: Trademap \n"
    return mdReportString + kaynak


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


def getArguments():
    """Ikili ticaret: ulke daima TUR, tek arguman ortak (partner) ulkedir."""
    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    return "TUR", (positional[0] if positional else "AUS")


def main(country="TUR", partner="AUS"):
    flags = set()
    if __name__ == "__main__":
        flags, positional = _parse_flags(sys.argv[1:])
        country = "TUR"
        partner = positional[0] if positional else "AUS"

    country_iso, country_display, country_field = nb.resolve_country(country)
    partner_iso, partner_display, partner_field = nb.resolve_country(partner)
    if not country_iso:
        print(f"Ülke ISO3 kodu çözülemedi: {country}")
        return 1
    if not partner_iso:
        print(f"Ortak ülke ISO3 kodu çözülemedi: {partner}")
        return 1
    if "--delete" in flags:
        return nb.delete_country_type(partner_iso, "obn bilateraltrade", "ticaret",
                                      partner_field, partner_display)
    title = f"{country_display} - {partner_display} İkili Ticaret Rakamları"
    entry, days, source = _report(partner_field, partner_display, title,
                                  "obn bilateraltrade")

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

    print(f"Ülke: {country_display} ({country_iso}) - Ortak: "
          f"{partner_display} ({partner_iso})")

    try:
        impsoup = connectAndGetSoup(country_iso, partner_iso, '1')
        expsoup = connectAndGetSoup(country_iso, partner_iso, '2')
        body = build_body(country_iso, partner_iso, impsoup, expsoup, 5)
    except Exception as exc:
        print(f"HATA getTmd: {exc}")
        return 1
    if body is None:
        print(f"İkili ticaret verisi bulunamadı ({country_display} - {partner_display}); "
              "ülke Trade Map'e doğrudan veri bildirmiyor olabilir.")
        return 2

    source_url = "https://www.trademap.org/"
    used = set()
    existing_ids = set()
    try:
        nb.emit_note(partner_display, partner_iso, title, "obn bilateraltrade", body,
                     source_url, partner_field, used, existing_ids,
                     bib_author="International Trade Centre (ITC)",
                     bib_howpublished="Trade Map")
        idx_path, _ = nb.write_country_index(partner_display, partner_iso, "ticaret",
                                             partner_field, used, existing_ids)
    except Exception as exc:
        print(f"HATA getTmd: {exc}")
        return 1
    print(f"INDEX: {idx_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
