vim9script
# vim-notebox icin getStmd.py (tek ulke dis ticaret raporu) entegrasyonu.
# Aktif not kutusunda (g:notes_directory) bir ulkenin Trade Map dis ticaret
# raporu notunu uretir, ulke ticaret indeksini gunceller ve indeksi acar.
# Rapor tazelik kontrolu: g:country_report_check / ask / max_age_days.

var stmddir = expand('<sfile>:p:h') .. '/scripts'

if !exists('g:stmd_python')
	g:stmd_python = stmddir .. '/venv/bin/python3'
endif

if !exists('g:stmd_script')
	g:stmd_script = stmddir .. '/getStmd.py'
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


def g:StmdFetch(country: string)
	var name = country
	if name == ''
		name = input('Ülke (iso3/ad): ')
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
			.. ' && ' .. shellescape(g:stmd_python)
			.. ' ' .. shellescape(g:stmd_script)
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
		.. ' && ' .. shellescape(g:stmd_python)
		.. ' ' .. shellescape(g:stmd_script)
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

def g:StmdDelete(country: string)
	var name = country
	if name == ''
		name = input('Ülke (iso3/ad): ')
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
	if confirm(name .. ' için oluşturulan dış ticaret notları silinsin mi?(E/H)',
		"&Evet\n&Hayır", 2) != 1
		echom 'Silme iptal edildi'
		return
	endif
	var cmd = 'cd ' .. shellescape(box)
		.. ' && ' .. shellescape(g:stmd_python)
		.. ' ' .. shellescape(g:stmd_script)
		.. ' ' .. shellescape(name) .. ' --delete'
	var out = systemlist(cmd)
	echom join(out, "\n")
	checktime
enddef


command -nargs=? Stmdfetch call g:StmdFetch(<q-args>)
command -nargs=? Stmddelete call g:StmdDelete(<q-args>)

nnoremap <unique> <Plug>Stmdfetch; :Stmdfetch<CR>
if !hasmapto('<Plug>Stmdfetch;')
	nnoremap <unique> <Leader>stmd <Plug>Stmdfetch;
endif

nnoremap <unique> <Plug>Stmddelete; :Stmddelete<CR>
if !hasmapto('<Plug>Stmddelete;')
	nnoremap <unique> <Leader>stmdd <Plug>Stmddelete;
endif
