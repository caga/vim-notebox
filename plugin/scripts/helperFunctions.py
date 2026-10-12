# -*- coding: utf-8 -*-
"""Geriye donuk uyumluluk modulu.

Yeni kod ortak islevler icin `notebox` modulunu kullanmalidir. Buradaki
isimler eski cagrilar icin korunmustur.
"""

import notebox as nb

human_format = nb.human_format
IdGenerator = nb.IdGenerator
writeMdReport = nb.writeMdReport
write_note_file = nb.write_note_file
split_backrefs = nb.split_backrefs


def FileHeader(title: str, author: str, country=' ', institude=' '):
    idno = nb.IdGenerator()
    return nb.build_header(idno, title, country, modify=None,
                           n_type="tmtd", author=author) \
        .replace("institude: \n", f"institude: {institude}\n")


def getArgument(country: str = 'TUR'):
    import sys
    return sys.argv[1] if len(sys.argv) > 1 else country
