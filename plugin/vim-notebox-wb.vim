vim9script
# vim-notebox icin getData.py (WorldBank gosterge raporu) entegrasyonu.
# Aktif not kutusunda (g:notes_directory) bir ulkenin WB gosterge raporu
# notunu uretir, ulke gosterge indeksini gunceller ve indeksi acar.

var wbdir = expand('<sfile>:p:h') .. '/scripts'

if !exists('g:wb_python')
	g:wb_python = wbdir .. '/venv/bin/python3'
endif

if !exists('g:wb_script')
	g:wb_script = wbdir .. '/getData.py'
endif

def g:WbFetch(country: string)
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
		.. ' && ' .. shellescape(g:wb_python)
		.. ' ' .. shellescape(g:wb_script)
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

command -nargs=? Wbfetch call g:WbFetch(<q-args>)

nnoremap <unique> <Plug>Wbfetch; :Wbfetch<CR>
if !hasmapto('<Plug>Wbfetch;')
	nnoremap <unique> <Leader>wbr <Plug>Wbfetch;
endif
