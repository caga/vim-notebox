vim9script
import autoload 'notebox.vim'

# vim-notebox icin exportObnHtml.py entegrasyonu.
# Bir ulkenin otomatik bilgi notlarini (OBN) HTML olarak disa aktarir.
# Cikti: <not kutusu>/htmlExports/<Ulke>Notlari/
#   index.html  -> ulkenin OBN hub sayfasi (ana sayfa)
#   <id>.html   -> ulkeye ait diger OBN notlari
# `obn files` sayfasi, global OBN dizini ve ulke paneli disarida kalir.

var cdir = expand('<sfile>:p:h') .. '/scripts'

if !exists('g:htmlexport_python')
	g:htmlexport_python = cdir .. '/venv/bin/python3'
endif

if !exists('g:htmlexport_script')
	g:htmlexport_script = cdir .. '/exportObnHtml.py'
endif

if !exists('g:htmlexport_dir')
	g:htmlexport_dir = 'htmlExports'
endif

if !exists('g:htmlexport_open')
	g:htmlexport_open = 1
endif

if !exists('g:htmlexport_opener')
	g:htmlexport_opener = 'xdg-open'
endif

if !exists('g:htmlexport_map')
	g:htmlexport_map = '<Leader>ohe'
endif


def NotesBox(): string
	if !exists('g:notes_directory') || g:notes_directory == ''
		g:notes_directory = '~/notes'
	endif
	var box = expand(g:notes_directory)
	if box == ''
		box = expand('~/notes')
	endif
	return box
enddef


def SetEnv(box: string)
	$NOTES_DIR = box
	$NOTES_BIB_DIR = box .. '/bibfiles'
enddef


def RunScript(name: string): list<string>
	var cmd = 'cd ' .. shellescape(NotesBox())
		.. ' && ' .. shellescape(expand(g:htmlexport_python))
		.. ' ' .. shellescape(expand(g:htmlexport_script))
		.. ' ' .. shellescape(name)
		.. ' --root ' .. shellescape(expand(g:htmlexport_dir))
	return systemlist(cmd)
enddef


def ParseTarget(out: list<string>): string
	for line in out
		if line =~ '^INDEX: '
			return substitute(line, '^INDEX: ', '', '')
		endif
	endfor
	return ''
enddef


def OpenTarget(target: string)
	if target == '' || !filereadable(target)
		return
	endif
	if !get(g:, 'htmlexport_open', 1)
		return
	endif
	var opener = get(g:, 'htmlexport_opener', 'xdg-open')
	try
		job_start([opener, target])
	catch
		echom 'Tarayıcı açılamadı: ' .. target
	endtry
enddef


def g:ObnHtmlExport(country: string)
	var name = country
	if name == ''
		name = input(notebox.Prompt('exportObnHtml.py'))
	endif
	if name == ''
		return
	endif

	var box = NotesBox()
	SetEnv(box)
	notebox.Busy('exportObnHtml.py', name)
	var out = RunScript(name)
	echom join(out, "\n")
	OpenTarget(ParseTarget(out))
enddef


command -nargs=? ObnHtmlExport call g:ObnHtmlExport(<q-args>)

nnoremap <unique> <Plug>ObnHtmlExport; :ObnHtmlExport<CR>
if !hasmapto('<Plug>ObnHtmlExport;')
	execute 'nnoremap <unique> ' .. g:htmlexport_map
		.. ' <Plug>ObnHtmlExport;'
endif
