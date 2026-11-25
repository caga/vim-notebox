vim9script

# Command-line messages for the data fetchers.
#
# Every wrapper calls one of the exported helpers so the command line shows
# which Python script is running and what it does:
#
#   getDbn.py — Dışişleri Bakanlığı ülke notları — Ülke (iso3/ad):
#   getDbn.py — Dışişleri Bakanlığı ülke notları — Nepal çalışıyor...
#
# g:notebox_fetch_desc can override or extend the descriptions; unknown
# scripts simply show their file name.  g:notebox_verbose = 0 suppresses the
# start/step/check messages (the prompts still include script and description).

const DEFAULT_DESC: dict<string> = {
	'getCountry.py': 'tüm otomatik ülke notları',
	'getDbn.py': 'Dışişleri Bakanlığı ülke notları',
	'getData.py': 'Dünya Bankası göstergeleri',
	'getLeaders.py': 'CIA World Leaders — liderler ve kabine',
	'getStmd.py': 'dış ticaret rakamları',
	'getTmd.py': 'ikili ticaret rakamları',
	'getUlkeTrapor.py': 'dış ticaret rakamları (tablo + şekil)',
	'getIkiliRapor.py': 'ikili ticaret rakamları',
	'getTbupNotes.py': 'Ticaret Bakanlığı ülke profili',
	'getTubitakNotes.py': 'TÜBİTAK bilgi notları',
	'getKosgebNotes.py': 'KOSGEB bilgi notları',
	'getTuysgmNotes.py': 'TÜYSGM bilgi notları',
	'getOtherBns.py': 'diğer kurum bilgi notları',
	'getMap.py': 'ülke haritası',
	'getTbupPdf.py': 'ülke profili PDF indirme',
	'generateCv.py': 'CV tablosu',
	'wbTable.py': 'WB gösterge tablosu',
	'exportObnHtml.py': 'OBN HTML dışa aktarımı',
}

g:notebox_fetch_desc = extend(copy(DEFAULT_DESC),
	get(g:, 'notebox_fetch_desc', {}))


def Verbose(): bool
	return get(g:, 'notebox_verbose', 1) != 0
enddef


export def Desc(script: string): string
	var desc = get(g:notebox_fetch_desc, script, '')
	return desc == '' ? script : desc
enddef


export def Label(script: string): string
	return printf('%s — %s', script, Desc(script))
enddef


export def Prompt(script: string, subject: string = 'Ülke (iso3/ad)'): string
	return Label(script) .. ' — ' .. subject .. ': '
enddef


export def DeletePrompt(script: string,
		subject: string = 'Ülke (iso3/ad)'): string
	return Label(script) .. ' siliniyor — ' .. subject .. ': '
enddef


# "Yeni Zelanda 2025" -> ["Yeni Zelanda", "2025"]; yil yoksa ikinci oge ''.
export def SplitYear(args: string): list<string>
	var parts = split(args)
	if !empty(parts) && parts[-1] =~ '^\d\{4}$'
		return [join(parts[0 : -2]), parts[-1]]
	endif
	return [args, '']
enddef


export def RequireYear(script: string, year: string): string
	if year != ''
		return year
	endif
	return trim(input(Prompt(script, 'Yıl (2025 gibi)')))
enddef


export def Busy(script: string, subject: string)
	if !Verbose()
		return
	endif
	echom Label(script) .. ' — ' .. subject .. ' çalışıyor...'
enddef


export def Checking(script: string)
	if !Verbose()
		return
	endif
	echom Label(script) .. ' — mevcut rapor kontrol ediliyor...'
enddef


export def Step(line: string)
	if !Verbose()
		return
	endif
	var m = matchlist(line, '^=== \(\S\+\.py\)')
	if !empty(m)
		echom Label(m[1])
		return
	endif
	m = matchlist(line, '^--- \(\S\+\.py\): \(.*\)$')
	if !empty(m)
		echom printf('%s — %s', m[1], m[2])
	endif
enddef


# WorldBank JSON önbelleği (data/<iso3>/wbdata/) hakkında bilgi.
#
# `getData.py --check` ağa çıkmaz ve hiçbir şey yazmaz; silme onaylarında
# klasörü ve dosya sayısını göstermek için kullanılır.  Vim tarafında ayrıca
# ISO3 çözümlemesi yok, ülke adını betik çözer.
export def WbCacheInfo(name: string, box: string): dict<any>
	var res = {dir: '', rel: '', files: 0, exists: false}
	if !exists('g:wb_script')
		return res
	endif
	var script = expand(g:wb_script)
	if script == '' || !filereadable(script)
		return res
	endif
	var python = expand(get(g:, 'wb_python', 'python3'))
	var out = systemlist([python, script, name, '--box', box, '--check'])
	for line in out
		if line =~ '^WB_DATA_DIR: '
			res.dir = substitute(line, '^WB_DATA_DIR: ', '', '')
		elseif line =~ '^WB_DATA_REL: '
			res.rel = substitute(line, '^WB_DATA_REL: ', '', '')
		elseif line =~ '^WB_DATA_FILES: '
			res.files = str2nr(split(
				substitute(line, '^WB_DATA_FILES: ', '', ''), '/')[0])
		elseif line =~ '^WB_DATA_EXISTS: '
			res.exists = str2nr(
				substitute(line, '^WB_DATA_EXISTS: ', '', '')) == 1
		endif
	endfor
	# `WB_DATA_FILES` yalnızca şablon göstergelerini sayar; onayda klasördeki
	# gerçek dosya sayısı gösterilsin (manifest.json dahil).
	if res.exists && res.dir != ''
		res.files = len(glob(res.dir .. '/**/*.json', true, true))
	endif
	return res
enddef
