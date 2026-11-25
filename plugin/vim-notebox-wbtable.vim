vim9script
import autoload 'notebox.vim'

# WorldBank gosterge notunun tablosunu sablon notundan yeniler.
# Yalnizca n_type: obn indicatorReport notlarinda calisir; notu yerinde
# gunceller, yeni not veya baglanti olusturmaz.

var wbdir = expand('<sfile>:p:h') .. '/scripts'

if !exists('g:wb_table_python')
	g:wb_table_python = wbdir .. '/venv/bin/python3'
endif

if !exists('g:wb_table_script')
	g:wb_table_script = wbdir .. '/wbTable.py'
endif

if !exists('g:wb_table_map')
	g:wb_table_map = '<Leader>wt'
endif


def YamlField(file: string, field: string): string
	var lines = readfile(file, '', 40)
	if empty(lines) || lines[0] !~ '^---\s*$'
		return ''
	endif
	var pat = '^' .. field .. '\s*:\s*'
	for i in range(1, len(lines) - 1)
		if lines[i] =~ '^---\s*$'
			break
		endif
		if lines[i] =~ pat
			var value = trim(matchstr(lines[i], pat .. '\zs.*'))
			value = substitute(value, '^"\(.*\)"$', '\1', '')
			value = substitute(value, "^'\(.*\)'$", '\1', '')
			return value
		endif
	endfor
	return ''
enddef


def g:WbTable()
	if &buftype != '' || !filereadable(expand('%'))
		echom 'Wbtable: kaydedilmiş bir not tamponunda çalıştırın'
		return
	endif
	if &modified
		echom 'Wbtable: önce notu kaydedin (:w)'
		return
	endif

	var file = expand('%:p')
	var ntype = YamlField(file, 'n_type')
	var tokens = split(tolower(ntype))
	if index(tokens, 'obn') < 0 || index(tokens, 'indicatorreport') < 0
		echom 'Wbtable: bu bir WorldBank gösterge notu değil'
		return
	endif

	var box = fnamemodify(file, ':h')
	var title = YamlField(file, 'title')
	if title == ''
		title = fnamemodify(file, ':t:r')
	endif

	notebox.Busy('wbTable.py', title)

	var cmd = 'cd ' .. shellescape(box)
		.. ' && ' .. shellescape(expand(g:wb_table_python))
		.. ' ' .. shellescape(expand(g:wb_table_script))
		.. ' ' .. shellescape(file)
		.. ' --box ' .. shellescape(box)
	var out = systemlist(cmd)
	echom join(out, "\n")

	checktime
	execute 'edit ' .. fnameescape(file)
enddef


command -nargs=0 Wbtable call g:WbTable()

nnoremap <unique> <Plug>Wbtable; :Wbtable<CR>
if !hasmapto('<Plug>Wbtable;')
	execute 'nnoremap <unique> ' .. g:wb_table_map .. ' <Plug>Wbtable;'
endif
