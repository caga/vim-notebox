vim9script
# vim-notebox icin getStmd.py (tek ulke dis ticaret raporu) entegrasyonu.
# Aktif not kutusunda (g:notes_directory) bir ulkenin Trade Map dis ticaret
# raporu notunu uretir, ulke ticaret indeksini gunceller ve indeksi acar.

var stmddir = expand('<sfile>:p:h') .. '/scripts'

if !exists('g:stmd_python')
	g:stmd_python = stmddir .. '/venv/bin/python3'
endif

if !exists('g:stmd_script')
	g:stmd_script = stmddir .. '/getStmd.py'
endif

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
	var cmd = 'cd ' .. shellescape(box)
		.. ' && ' .. shellescape(g:stmd_python)
		.. ' ' .. shellescape(g:stmd_script)
		.. ' ' .. shellescape(name)
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

command -nargs=? Stmdfetch call g:StmdFetch(<q-args>)

nnoremap <unique> <Plug>Stmdfetch; :Stmdfetch<CR>
if !hasmapto('<Plug>Stmdfetch;')
	nnoremap <unique> <Leader>stmd <Plug>Stmdfetch;
endif
