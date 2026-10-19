vim9script
# vim-notebox icin getTmd.py (ikili ticaret raporu) entegrasyonu.
# Ulke daima TUR'dur; tek arguman diger (ortak) ulkedir. Ornegin
# :Tmdfetch Nepal -> "Turkiye - Nepal Ikili Ticaret Rakamlari" notunu uretir;
# not, Nepal'in sayfalarina/indeksine yazilir (country: npl).
# Rapor tazelik kontrolu: g:country_report_check / ask / max_age_days.

var tmddir = expand('<sfile>:p:h') .. '/scripts'

if !exists('g:tmd_python')
	g:tmd_python = tmddir .. '/venv/bin/python3'
endif

if !exists('g:tmd_script')
	g:tmd_script = tmddir .. '/getTmd.py'
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


def g:TmdFetch(country: string)
	var name = country
	if name == ''
		name = input('Diğer ülke (varsayılan ülke TUR): ')
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
	$NOTES_REPORT_MAX_AGE_DAYS = string(get(g:, 'country_report_max_age_days', 7))

	if get(g:, 'country_report_check', 1) != 0
		var chk = systemlist('cd ' .. shellescape(box)
			.. ' && ' .. shellescape(g:tmd_python)
			.. ' ' .. shellescape(g:tmd_script)
			.. ' ' .. shellescape(name) .. ' --check')
		var r = ParseReport(chk)
		if r.exists != ''
			if r.fresh == 1
				echom 'Taze rapor, yenilenmedi: ' .. r.text
				execute 'edit ' .. fnameescape(r.exists)
				return
			endif
			if get(g:, 'country_report_ask', 1) != 0
				if confirm(r.text .. "\nYeni rapor oluşturulsun mu?",
					"&Evet\n&Hayır", 2) != 1
					echom 'Rapor yenilenmedi: ' .. r.text
					execute 'edit ' .. fnameescape(r.exists)
					return
				endif
			endif
		endif
	endif

	var cmd = 'cd ' .. shellescape(box)
		.. ' && ' .. shellescape(g:tmd_python)
		.. ' ' .. shellescape(g:tmd_script)
		.. ' ' .. shellescape(name) .. ' --force'
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
		name = input('Diğer ülke (varsayılan ülke TUR): ')
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
