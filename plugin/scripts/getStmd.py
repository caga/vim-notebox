#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bir ulkenin tek tarafli dis ticaret raporunu (Trade Map) uretir ve not
kutusuna standart not olarak yazar.

Kullanim:
    python getStmd.py Nepal
    python getStmd.py NPL
    python getStmd.py Türkiye
"""

import asyncio
import sys

import requests
from bs4 import BeautifulSoup
from googletrans import Translator
from tabulate import tabulate

import cnlook as lu
import notebox as nb


async def _translate(s, src='en', dest='tr'):
    async with Translator() as translator:
        return await translator.translate(s, dest=dest)


def translate_text(s):
    try:
        return asyncio.run(_translate(s)).text
    except Exception:
        return s


def getProductSoup(country='TUR', impex='1'):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
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
    response = requests.get(url, headers=headers, timeout=60)
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
        itemd[th4] = f"{round(itemd[th3] / total * 100, 1):.1f}"
        itemd[th3] = nb.human_format(itemd[th3])
        data.append(itemd.copy())
    total = nb.human_format(total)
    return total, year, data


def getCountrySoup(country='TUR', impex='1'):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
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
    response = requests.get(url, headers=headers, timeout=60)
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
        itemd[th3] = f"{round(itemd[th2] / total * 100, 1):.1f}"
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
    kaynak = "\n\n Kaynak: Trademap \n"
    return Sep.join([imExTable, imPartTable, exPartTable, imProTable, exProTable]) + kaynak


def main():
    arg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "TUR"
    iso3, display, country_field = nb.resolve_country(arg)
    if not iso3:
        print(f"Ülke ISO3 kodu çözülemedi: {arg}")
        return 1
    print(f"Ülke: {display} ({iso3})")

    try:
        body = build_body(iso3)
    except Exception as exc:
        print(f"HATA getStmd: {exc}")
        return 1
    if not body:
        print(f"HATA getStmd: ticaret verisi bulunamadı ({display})")
        return 2
    title = f"{display} Dış Ticaret Rakamları"

    source_url = "https://www.trademap.org/"
    used = set()
    existing_ids = set()
    try:
        nb.emit_note(display, iso3, title, "singletrade", body, source_url,
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
