vim9script
import autoload 'notebox.vim'

# vim-notebox icin getDbn.py entegrasyonu.
# Aktif not kutusunda (g:notes_directory) bir ulkenin MFA notlarini uretir
# ve olusan "{Ulke} Dışişleri Bakanlığı Web Notları" indeks notunu acar.
# Bu dosya mevcut vim-notebox dosyalarini degistirmez; bagimsiz calisir.

var dbndir = expand('<sfile>:p:h') .. '/scripts'

if !exists('g:dbn_python')
	g:dbn_python = dbndir .. '/venv/bin/python3'
endif

if !exists('g:dbn_script')
	g:dbn_script = dbndir .. '/getDbn.py'
endif

def g:DbnFetch(country: string)
	var name = country
	if name == ''
		name = input(notebox.Prompt('getDbn.py'))
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

	$DBWN_NOTES_DIR = box
	$NOTES_AUTOHUB = get(g:, 'notes_autohub', 1) ? '1' : '0'
	var cmd = 'cd ' .. shellescape(box)
		.. ' && ' .. shellescape(g:dbn_python)
		.. ' ' .. shellescape(g:dbn_script)
		.. ' ' .. shellescape(name)
	notebox.Busy('getDbn.py', name)
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

def g:DbnDelete(country: string)
	var name = country
	if name == ''
		name = input(notebox.DeletePrompt('getDbn.py'))
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
	$DBWN_NOTES_DIR = box
	$NOTES_AUTOHUB = get(g:, 'notes_autohub', 1) ? '1' : '0'
	if confirm(name .. ' için oluşturulan Dışişleri Bakanlığı web notları silinsin mi?(E/H)',
		"&Evet\n&Hayır", 2) != 1
		echom 'Silme iptal edildi'
		return
	endif
	var cmd = 'cd ' .. shellescape(box)
		.. ' && ' .. shellescape(g:dbn_python)
		.. ' ' .. shellescape(g:dbn_script)
		.. ' ' .. shellescape(name) .. ' --delete'
	var out = systemlist(cmd)
	echom join(out, "\n")
	checktime
enddef


command -nargs=? Dbnfetch call g:DbnFetch(<q-args>)
command -nargs=? Dbndelete call g:DbnDelete(<q-args>)

nnoremap <unique> <Plug>Dbnfetch; :Dbnfetch<CR>
if !hasmapto('<Plug>Dbnfetch;')
	nnoremap <unique> <Leader>dbn <Plug>Dbnfetch;
endif

nnoremap <unique> <Plug>Dbndelete; :Dbndelete<CR>
if !hasmapto('<Plug>Dbndelete;')
	nnoremap <unique> <Leader>dbnd <Plug>Dbndelete;
endif
