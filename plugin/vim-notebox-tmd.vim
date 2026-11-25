vim9script
import autoload 'notebox.vim'

# vim-notebox icin getIkiliRapor.py (ikili ticaret raporu) entegrasyonu.
# Ulke daima TUR'dur; tek arguman diger (ortak) ulkedir. Ornegin
# :Tmdfetch Nepal 2025 -> "Turkiye - Nepal Ikili Ticaret Rakamlari" notunu
# uretir; not, Nepal'in sayfalarina/indeksine yazilir (country: npl).
# Yil istege baglidir: :Tmdfetch Nepal
# Yil verilmezse iki akista da veri bulunan en yeni yil kullanilir.
# Rapor tazelik kontrolu: g:country_report_check / ask / max_age_days.

var tmddir = expand('<sfile>:p:h') .. '/scripts'

if !exists('g:tmd_python')
	g:tmd_python = tmddir .. '/venv/bin/python3'
endif

if !exists('g:tmd_script')
	g:tmd_script = tmddir .. '/getIkiliRapor.py'
endif

if !exists('g:tradeapp_dir')
	g:tradeapp_dir = '~/calisma/tmapp'
endif


def ParseReport(out: list<string>): dict<any>
	var res = {exists: '', fresh: 0, text: ''}
	for line in out
		if line =~ '^REPORT_EXISTS: '
			res.exists = substitute(line, '^REPORT_EXISTS: ', '', '')
		elseif line =~ '^REPORT_FRESH: '
			res.fresh = str2nr(substitute(line, '^REPORT_FRESH: ', '', ''))
		elseif line =~ '^REPORT_AGE_TEXT: '
			res.text = substitute(line, '^REPORT_AGE_TEXT: ', '', '')
		endif
	endfor
	return res
enddef


# "Nepal 2025" -> ["Nepal", "2025"]; yil yoksa ikinci oge ''.
def SplitYear(args: string): list<string>
	return notebox.SplitYear(args)
enddef


def g:TmdFetch(country: string)
	var parsed = SplitYear(country)
	var name = parsed[0]
	var year = parsed[1]
	if name == ''
		name = input(notebox.Prompt('getIkiliRapor.py', 'Ortak ülke'))
	endif
	if name == ''
		return
	endif
	if year != '' && year !~ '^\d\{4}$'
		echom notebox.Label('getIkiliRapor.py')
			.. ' — yıl 4 haneli olmalı (ör. 2025): ' .. year
		return
	endif
	var year_arg = year == '' ? '' : ' ' .. shellescape(year)

	if !exists('g:notes_directory') || g:notes_directory == ''
		g:notes_directory = '~/notes'
	endif
	var box = expand(g:notes_directory)
	if box == ''
		box = expand('~/notes')
	endif

	$NOTES_DIR = box
	$NOTES_BIB_DIR = box .. '/bibfiles'
	$NOTES_AUTOHUB = get(g:, 'notes_autohub', 1) ? '1' : '0'
	$NOTES_REPORT_MAX_AGE_DAYS = string(get(g:, 'country_report_max_age_days', 7))
	$TRADEAPP_DIR = expand(g:tradeapp_dir)

	if get(g:, 'country_report_check', 1) != 0
		notebox.Checking('getIkiliRapor.py')
		var chk = systemlist('cd ' .. shellescape(box)
			.. ' && ' .. shellescape(g:tmd_python)
			.. ' ' .. shellescape(g:tmd_script)
			.. ' ' .. shellescape(name) .. year_arg
			.. ' --check')
		var r = ParseReport(chk)
		if r.exists != ''
			if r.fresh == 1
				echom notebox.Label('getIkiliRapor.py')
					.. ' — taze rapor, yenilenmedi: ' .. r.text
				execute 'edit ' .. fnameescape(r.exists)
				return
			endif
			if get(g:, 'country_report_ask', 1) != 0
				if confirm(notebox.Label('getIkiliRapor.py') .. "\n" .. r.text
					.. "\nYeni rapor oluşturulsun mu?",
					"&Evet\n&Hayır", 2) != 1
					echom notebox.Label('getIkiliRapor.py')
						.. ' — rapor yenilenmedi: ' .. r.text
					execute 'edit ' .. fnameescape(r.exists)
					return
				endif
			endif
		endif
	endif

	var cmd = 'cd ' .. shellescape(box)
		.. ' && ' .. shellescape(g:tmd_python)
		.. ' ' .. shellescape(g:tmd_script)
		.. ' ' .. shellescape(name) .. year_arg .. ' --force'
	var subject = year == '' ? name : name .. ' (' .. year .. ')'
	notebox.Busy('getIkiliRapor.py', subject)
	var out = systemlist(cmd)
	echom join(out, "\n")

	var idx = ''
	for line in out
		if line =~ '^INDEX: '
			idx = substitute(line, '^INDEX: ', '', '')
		endif
	endfor

	checktime
	if idx != '' && filereadable(idx)
		execute 'edit ' .. fnameescape(idx)
	endif
enddef

def g:TmdDelete(country: string)
	var name = country
	if name == ''
		name = input(notebox.DeletePrompt('getIkiliRapor.py', 'Ortak ülke'))
	endif
	if name == ''
		return
	endif
	if !exists('g:notes_directory') || g:notes_directory == ''
		g:notes_directory = '~/notes'
	endif
	var box = expand(g:notes_directory)
	if box == ''
		box = expand('~/notes')
	endif
	$NOTES_DIR = box
	$NOTES_BIB_DIR = box .. '/bibfiles'
	$NOTES_AUTOHUB = get(g:, 'notes_autohub', 1) ? '1' : '0'
	$TRADEAPP_DIR = expand(g:tradeapp_dir)
	if confirm(name .. ' için oluşturulan ikili ticaret notları silinsin mi?(E/H)',
		"&Evet\n&Hayır", 2) != 1
		echom 'Silme iptal edildi'
		return
	endif
	var cmd = 'cd ' .. shellescape(box)
		.. ' && ' .. shellescape(g:tmd_python)
		.. ' ' .. shellescape(g:tmd_script)
		.. ' ' .. shellescape(name) .. ' --delete'
	var out = systemlist(cmd)
	echom join(out, "\n")
	checktime
enddef


command -nargs=? Tmdfetch call g:TmdFetch(<q-args>)
command -nargs=? Tmddelete call g:TmdDelete(<q-args>)

nnoremap <unique> <Plug>Tmdfetch; :Tmdfetch<CR>
if !hasmapto('<Plug>Tmdfetch;')
	nnoremap <unique> <Leader>tmd <Plug>Tmdfetch;
endif

nnoremap <unique> <Plug>Tmddelete; :Tmddelete<CR>
if !hasmapto('<Plug>Tmddelete;')
	nnoremap <unique> <Leader>tmdd <Plug>Tmddelete;
endif
