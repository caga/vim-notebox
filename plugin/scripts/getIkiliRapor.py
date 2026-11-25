#!/home/osman/.vim/plugged/vim-notebox/plugin/scripts/venv/bin/python3
# -*- coding: utf-8 -*-
"""Turkiye ile bir ortak ulke arasindaki ikili ticaret raporunu (Trade Map)
uretir ve not kutusuna standart not olarak yazar. Ulke daima TUR'dur; tek
arguman diger (ortak) ulkedir.

Kullanim:
    ./getIkiliRapor.py Nepal
    ./getIkiliRapor.py Nepal 2024 --box ~/countryNotes
    ./getIkiliRapor.py Nepal 2024 --force
    ./getIkiliRapor.py Nepal 2024 --check
    ./getIkiliRapor.py Nepal --delete

Secenekler:
    --box DIR   not kutusu (varsayilan: $NOTES_DIR veya cwd)
    --check     mevcut raporun yasini bildir; yil verilmezse en yeni
                yili kisa bir ag sorgusuyla dogrular (ag yoksa yalnizca yas)
    --force     tazelik esigini yok say ve yeniden uret
    --delete    ulkenin ikili ticaret notlarini sil

Yil istege baglidir. Verilmezse hem ithalat hem ihracat icin veri bulunan
en yeni yil kullanilir (--check bunu kisa bir ag sorgusuyla dogrular; ag
yoksa yalnizca yas kontrolu yapar).
"""

import sys

import _cli

_cli.init()

import notebox as nb
import tradeapp as ta

N_TYPE = "obn bilateraltrade"
KIND = "ticaret"
REPORTER = "TUR"


def _check(title, partner_field, partner_display, year):
    entry, days, source = ta.report_entry(partner_field, partner_display,
                                          title, N_TYPE)
    if not entry:
        return 0
    if year is None:
        year_ok = True
    else:
        year_ok = ta.body_has_year(entry["path"], year)
    fresh = ta.is_fresh(days) and year_ok
    text = ta.report_age_text(title, days, source)
    if year is None:
        text += " En yeni veri yılı sorgulanamadı; yalnızca yaş kontrol edildi."
    elif not year_ok:
        text += f" İstenen yıl ({year}) için veri yok."
    ta.emit_check(entry["path"], days, source, fresh, text)
    return 0


def main():
    flags, positional = ta.parse_flags(sys.argv[1:])
    try:
        partner_arg, year = ta.split_country_year(positional, required=False)
    except ValueError as exc:
        print(f"HATA getIkiliRapor: {exc}")
        return 1

    country_iso, country_display, _country_field = nb.resolve_country(REPORTER)
    partner_iso, partner_display, partner_field = nb.resolve_country(partner_arg)
    title = f"{country_display} - {partner_display} {ta.BILATERAL_SUFFIX}"

    if "--delete" in flags:
        return nb.delete_country_type(partner_iso, N_TYPE, KIND,
                                      partner_field, partner_display)

    try:
        m49 = ta.m49_for(partner_iso, partner_display)
    except (LookupError, RuntimeError) as exc:
        print(f"HATA getIkiliRapor: {exc}")
        return 1

    resolved = False
    if year is None:
        try:
            reporter_m49 = ta.m49_for(country_iso, country_display)
            year = ta.latest_year(reporter_m49, m49)
        except Exception as exc:
            if "--check" in flags:
                print(f"UYARI getIkiliRapor: en yeni veri yılı "
                      f"sorgulanamadı: {exc}")
            else:
                print(f"HATA getIkiliRapor: en yeni veri yılı "
                      f"sorgulanamadı: {exc}")
                return 1
        else:
            if year is None:
                if "--check" in flags:
                    print("UYARI getIkiliRapor: en yeni veri yılı "
                          "bulunamadı; yalnızca yaş kontrol edildi")
                else:
                    print(f"HATA getIkiliRapor: en yeni veri yılı "
                          f"bulunamadı ({country_display} - "
                          f"{partner_display})")
                    return 2
            else:
                resolved = True

    if "--check" in flags:
        return _check(title, partner_field, partner_display, year)

    entry, days, source = ta.report_entry(partner_field, partner_display,
                                          title, N_TYPE)
    if (entry and ta.is_fresh(days)
            and ta.body_has_year(entry["path"], year)
            and "--force" not in flags):
        print(f"ATLANDI: {title} {nb.human_age(days)} güncellendi "
              f"({nb.REPORT_MAX_AGE_DAYS} günden yeni; yenilenmedi)")
        return 0

    print(f"Ülke: {country_display} ({country_iso}) - Ortak: "
          f"{partner_display} ({partner_iso or partner_field})")
    if resolved:
        print(f"Veri yılı: {year} (en yeni veri)")
    else:
        print(f"Veri yılı: {year}")

    try:
        body = ta.bilateral_report(m49, year)
    except Exception as exc:
        print(f"HATA getIkiliRapor: {exc}")
        return 1
    if not body or not body.strip():
        print(f"HATA getIkiliRapor: ikili ticaret verisi bulunamadı "
              f"({country_display} - {partner_display})")
        return 2

    used = set()
    existing_ids = set()
    try:
        ta.emit_note(partner_display, partner_iso, title, N_TYPE, body,
                     partner_field, used, existing_ids)
        idx_path, _ = nb.write_country_index(partner_display, partner_iso,
                                             KIND, partner_field, used,
                                             existing_ids)
    except Exception as exc:
        print(f"HATA getIkiliRapor: {exc}")
        return 1
    print(f"INDEX: {idx_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
