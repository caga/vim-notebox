vim9script
import autoload 'notebox.vim'

# vim-notebox icin CV tablosu uretimi.
# Gecerli notun (n_type: cvb veya perm cvb) basliklarindan yeni bir
# n_type: cv notu uretir ve acar. Kaynak not degistirilmez.
# Islem senkron calisir; script hizlidir (ag erisimi yok).

var cvdir = expand('<sfile>:p:h') .. '/scripts'

if !exists('g:cv_python')
	g:cv_python = cvdir .. '/venv/bin/python3'
endif

if !exists('g:cv_script')
	g:cv_script = cvdir .. '/generateCv.py'
endif

if !exists('g:cv_generate_map')
	g:cv_generate_map = '<Leader>cv'
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


def g:CvGenerate()
	if &buftype != '' || !filereadable(expand('%'))
		echom 'Cvgenerate: kaydedilmiş bir not tamponunda çalıştırın'
		return
	endif
	if &modified
		echom 'Cvgenerate: önce notu kaydedin (:w)'
		return
	endif

	var file = expand('%:p')
	var ntype = YamlField(file, 'n_type')
	if index(split(tolower(ntype)), 'cvb') < 0
		echom 'Cvgenerate: bu standart bir cv bilgi sayfası değil'
		return
	endif

	var box = fnamemodify(file, ':h')
	var title = YamlField(file, 'title')
	if title == ''
		title = fnamemodify(file, ':t:r')
	endif

	notebox.Busy('generateCv.py', title)

	var cmd = 'cd ' .. shellescape(box)
		.. ' && ' .. shellescape(expand(g:cv_python))
		.. ' ' .. shellescape(expand(g:cv_script))
		.. ' ' .. shellescape(file)
		.. ' --box ' .. shellescape(box)
	var out = systemlist(cmd)
	echom join(out, "\n")

	var target = ''
	for line in out
		if line =~ '^CV: '
			target = substitute(line, '^CV: ', '', '')
		endif
	endfor

	checktime
	if target != '' && filereadable(target)
		execute 'edit ' .. fnameescape(target)
	endif
enddef


command -nargs=0 Cvgenerate call g:CvGenerate()

nnoremap <unique> <Plug>Cvgenerate; :Cvgenerate<CR>
if !hasmapto('<Plug>Cvgenerate;')
	execute 'nnoremap <unique> ' .. g:cv_generate_map .. ' <Plug>Cvgenerate;'
endif
