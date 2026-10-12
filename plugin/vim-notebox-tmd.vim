vim9script
# vim-notebox icin getTmd.py (ikili ticaret raporu) entegrasyonu.
# Ulke daima TUR'dur; tek arguman diger (ortak) ulkedir. Ornegin
# :Tmdfetch Nepal -> "Turkiye - Nepal Ikili Ticaret Rakamlari" notunu uretir;
# not, Nepal'in sayfalarina/indeksine yazilir (country: npl).

var tmddir = expand('<sfile>:p:h') .. '/scripts'

if !exists('g:tmd_python')
	g:tmd_python = tmddir .. '/venv/bin/python3'
endif

if !exists('g:tmd_script')
	g:tmd_script = tmddir .. '/getTmd.py'
endif

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
	var cmd = 'cd ' .. shellescape(box)
		.. ' && ' .. shellescape(g:tmd_python)
		.. ' ' .. shellescape(g:tmd_script)
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

command -nargs=? Tmdfetch call g:TmdFetch(<q-args>)

nnoremap <unique> <Plug>Tmdfetch; :Tmdfetch<CR>
if !hasmapto('<Plug>Tmdfetch;')
	nnoremap <unique> <Leader>tmd <Plug>Tmdfetch;
endif
