#!/home/osman/.vim/plugged/vim-notebox/plugin/scripts/venv/bin/python3
# -*- coding: utf-8 -*-
"""Bir ulkenin Trade Map dis ticaret raporunu iki not olarak uretir:

    "<Ulke> Dis Ticaret Rakamlari"          -> 5 tablo (ulkeTrapor.py)
    "<Ulke> Dis Ticaret Rakamlari -Sekilli" -> tablolar + mermaid grafikleri (tRwF.py)

Kullanim:
    ./getUlkeTrapor.py Yeni Zelanda
    ./getUlkeTrapor.py NPL 2025 --box ~/countryNotes
    ./getUlkeTrapor.py Türkiye 2024 --force
    ./getUlkeTrapor.py Türkiye 2024 --check
    ./getUlkeTrapor.py Nepal --delete

Secenekler:
    --box DIR   not kutusu (varsayilan: $NOTES_DIR veya cwd)
    --check     mevcut raporlarin yasini bildir; yil verilmezse en yeni
                yili kisa bir ag sorgusuyla dogrular (ag yoksa yalnizca yas)
    --force     tazelik esigini yok say ve yeniden uret
    --delete    ulkenin dis ticaret notlarini (tablo + sekilli) sil

Yil istege baglidir. Verilmezse hem ithalat hem ihracat icin veri bulunan
en yeni yil kullanilir (--check bunu kisa bir ag sorgusuyla dogrular; ag
yoksa yalnizca yas kontrolu yapar).
"""

import sys

import _cli

_cli.init()

import notebox as nb
import tradeapp as ta

N_TYPE = "obn singletrade"
KIND = "ticaret"


def _titles(display):
    return (f"{display} {ta.SINGLE_SUFFIX}",
            f"{display} {ta.FIGURE_SUFFIX}")


def _check(display, country_field, year):
    table_title, figure_title = _titles(display)
    table_entry, table_days, table_source = ta.report_entry(
        country_field, display, table_title, N_TYPE)
    figure_entry, figure_days, figure_source = ta.report_entry(
        country_field, display, figure_title, N_TYPE)
    if not table_entry:
        return 0

    if year is None:
        table_year_ok = True
        figure_year_ok = True
    else:
        table_year_ok = ta.body_has_year(table_entry["path"], year)
        figure_year_ok = (figure_entry is not None
                          and ta.body_has_year(figure_entry["path"], year))
    fresh = (ta.is_fresh(table_days) and figure_entry is not None
             and ta.is_fresh(figure_days) and table_year_ok
             and figure_year_ok)

    parts = [ta.report_age_text(table_title, table_days, table_source)]
    if figure_entry is None:
        parts.append("Şekilli not yok.")
    else:
        parts.append(ta.report_age_text(figure_title, figure_days,
                                        figure_source))
    if year is None:
        parts.append("En yeni veri yılı sorgulanamadı; yalnızca yaş "
                     "kontrol edildi.")
    else:
        missing = []
        if not table_year_ok:
            missing.append("tablo notu")
        if figure_entry is not None and not figure_year_ok:
            missing.append("şekilli not")
        if missing:
            parts.append(f"İstenen yıl ({year}) için veri yok: "
                         f"{' ve '.join(missing)}.")

    ta.emit_check(table_entry["path"], table_days, table_source, fresh,
                  " ".join(parts))
    return 0


def main():
    flags, positional = ta.parse_flags(sys.argv[1:])
    try:
        arg, year = ta.split_country_year(positional, required=False)
    except ValueError as exc:
        print(f"HATA getUlkeTrapor: {exc}")
        return 1

    iso3, display, country_field = nb.resolve_country(arg)
    table_title, figure_title = _titles(display)

    if "--delete" in flags:
        return nb.delete_country_type(iso3, N_TYPE, KIND,
                                      country_field, display)

    try:
        m49 = ta.m49_for(iso3, display)
    except (LookupError, RuntimeError) as exc:
        print(f"HATA getUlkeTrapor: {exc}")
        return 1

    resolved = False
    if year is None:
        try:
            year = ta.latest_year(m49)
        except Exception as exc:
            if "--check" in flags:
                print(f"UYARI getUlkeTrapor: en yeni veri yılı "
                      f"sorgulanamadı: {exc}")
            else:
                print(f"HATA getUlkeTrapor: en yeni veri yılı "
                      f"sorgulanamadı: {exc}")
                return 1
        else:
            if year is None:
                if "--check" in flags:
                    print("UYARI getUlkeTrapor: en yeni veri yılı "
                          "bulunamadı; yalnızca yaş kontrol edildi")
                else:
                    print(f"HATA getUlkeTrapor: en yeni veri yılı "
                          f"bulunamadı ({display})")
                    return 2
            else:
                resolved = True

    if "--check" in flags:
        return _check(display, country_field, year)

    table_entry, table_days, table_source = ta.report_entry(
        country_field, display, table_title, N_TYPE)
    figure_entry, figure_days, _figure_source = ta.report_entry(
        country_field, display, figure_title, N_TYPE)
    if (table_entry and ta.is_fresh(table_days) and figure_entry
            and ta.is_fresh(figure_days)
            and ta.body_has_year(table_entry["path"], year)
            and ta.body_has_year(figure_entry["path"], year)
            and "--force" not in flags):
        print(f"ATLANDI: {table_title} {nb.human_age(table_days)} "
              f"güncellendi ({nb.REPORT_MAX_AGE_DAYS} günden yeni; "
              "yenilenmedi)")
        return 0

    print(f"Ülke: {display} ({iso3 or country_field})")
    if resolved:
        print(f"Veri yılı: {year} (en yeni veri)")
    else:
        print(f"Veri yılı: {year}")

    try:
        body = ta.country_report(m49, year)
    except Exception as exc:
        print(f"HATA getUlkeTrapor: {exc}")
        return 1
    if not body or not body.strip():
        print(f"HATA getUlkeTrapor: ticaret verisi bulunamadı ({display})")
        return 2

    figures = ""
    try:
        figures = ta.country_figures(m49, year)
    except Exception as exc:
        print(f"UYARI getUlkeTrapor: şekilli rapor üretilemedi: {exc}")
    if not figures or not figures.strip():
        print("UYARI getUlkeTrapor: şekilli rapor verisi bulunamadı")
        figures = ""

    used = set()
    existing_ids = set()
    try:
        ta.emit_note(display, iso3, table_title, N_TYPE, body,
                     country_field, used, existing_ids)
        if figures:
            ta.emit_note(display, iso3, figure_title, N_TYPE, figures,
                         country_field, used, existing_ids)
        idx_path, _ = nb.write_country_index(display, iso3, KIND,
                                             country_field, used, existing_ids)
    except Exception as exc:
        print(f"HATA getUlkeTrapor: {exc}")
        return 1
    print(f"INDEX: {idx_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
