#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WorldBank gosterge raporu uretir ve not kutusuna standart not olarak yazar.

Kullanim:
    python getData.py Nepal
    python getData.py NPL
    python getData.py Türkiye
"""

import asyncio
import sys

import requests
from googletrans import Translator
from py_markdown_table.markdown_table import markdown_table as md_table

import notebox as nb


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


async def _translate(s, dest='tr'):
    async with Translator() as translator:
        return await translator.translate(s, dest=dest)


def translate_text(s):
    try:
        return asyncio.run(_translate(s)).text
    except Exception:
        return s


def GetGeneralDataFromWB(country='TUR'):
    api_url = f"https://api.worldbank.org/v2/countries/{country}?format=json"
    response = requests.get(api_url, timeout=30)
    data = response.json()[1][0]
    countryFullName = translate_text(data['name'])
    region = translate_text(data['region']['value'])
    incomeLevel = translate_text(data['incomeLevel']['value'])
    generalData = {
        'Ülke': countryFullName,
        'Bölge': region,
        'Gelir Seviyesi': incomeLevel,
        'Başkent': data['capitalCity'],
    }
    return generalData


def GetIndicatorValueFromWB(country, indicator):
    api_url = f"https://api.worldbank.org/v2/countries/{country}/indicator/{indicator}?format=json"
    try:
        response = requests.get(api_url, timeout=30)
        data = response.json()[1]
    except Exception as exc:
        print(f"UYARI gösterge alınamadı: {indicator} ({exc})")
        return {'indicator': indicator, 'value': None, 'year': None}
    if not data:
        print(f"UYARI gösterge verisi yok: {indicator}")
        return {'indicator': indicator, 'value': None, 'year': None}
    indicatorValue = None
    indicatorYear = None
    for data_item in data:
        if data_item.get('value') is not None:
            indicatorValue = nb.human_format(float(data_item['value']))
            indicatorYear = f"{data_item['date']}"
            break
    return {
        'indicator': (data[0].get('indicator') or {}).get('value', indicator),
        'value': indicatorValue,
        'year': indicatorYear,
    }


def GetIndicatorsFromWB(country):
    data = []
    for indicator in indicatorCodesWB:
        dataItemWB = GetIndicatorValueFromWB(country, indicatorCodesWB[indicator])
        year = dataItemWB['year']
        value = dataItemWB['value']
        label = indicator + (f" ({year})" if year else "")
        data.append({
            'Gösterge': label,
            'Değer': value if value is not None else 'veri yok',
        })
    return data


def build_body(countryName, gdata, data):
    gDataTable = md_table([gdata]).set_params(row_sep='markdown').get_markdown().replace('```', '')
    dataTable = md_table(data).set_params(row_sep='markdown').get_markdown().replace('```', '')
    return f"""
# {countryName} Otomatik Rapor Tabloları


{gDataTable}


{dataTable}


## Kaynaklar:

    Dünya Bankası Verileri
"""


def main():
    arg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "TUR"
    iso3, display, country_field = nb.resolve_country(arg)
    api_country = iso3 if iso3 else country_field.upper()
    print(f"Ülke: {display}" + (f" ({iso3})" if iso3 else ""))

    try:
        data = GetIndicatorsFromWB(api_country)
        gdata = GetGeneralDataFromWB(api_country)
        countryName = gdata['Ülke']
        title = f"{display} WorldBank Göstergeleri"
        body = build_body(countryName, gdata, data)

        source_url = f"https://data.worldbank.org/country/{iso3 or country_field}"
        used = set()
        existing_ids = set()
        nb.emit_note(display, iso3, title, "indicatorReport", body, source_url,
                     country_field, used, existing_ids,
                     bib_author="Dünya Bankası",
                     bib_howpublished="World Bank Open Data")

        idx_path, _ = nb.write_country_index(display, iso3, "gosterge",
                                             country_field, used, existing_ids)
    except Exception as exc:
        print(f"HATA getData: {exc}")
        return 1
    print(f"INDEX: {idx_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
