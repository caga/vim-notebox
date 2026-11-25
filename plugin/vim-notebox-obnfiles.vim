vim9script
import autoload 'notebox.vim'

# vim-notebox icin getObnFiles.py entegrasyonu.
# Bir ulkenin "Dokumanlari" sayfasini (n_type: obn files) uretir ve ulke
# hub'ina "## Obn Files" basligi altinda baglar.
# --delete yalnizca bu betigin urettigi sayfayi ve hub linkini kaldirir;
# baska notlara, hub'a veya belgelere dokunmaz.

var cdir = expand('<sfile>:p:h') .. '/scripts'

if !exists('g:obnfiles_python')
	g:obnfiles_python = cdir .. '/venv/bin/python3'
endif

if !exists('g:obnfiles_script')
	g:obnfiles_script = cdir .. '/getObnFiles.py'
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
	$NOTES_AUTOHUB = get(g:, 'notes_autohub', 1) ? '1' : '0'
	$TBUP_PDF_DIR = get(g:, 'tbup_pdfdir', box .. '/tbupPdfs')
enddef


def RunScript(name: string, extra: string): list<string>
	var cmd = 'cd ' .. shellescape(NotesBox())
		.. ' && ' .. shellescape(expand(g:obnfiles_python))
		.. ' ' .. shellescape(expand(g:obnfiles_script))
		.. ' ' .. shellescape(name)
	if extra != ''
		cmd = cmd .. ' ' .. extra
	endif
	return systemlist(cmd)
enddef


def ParseTarget(out: list<string>): string
	var fallback = ''
	for line in out
		if line =~ '^FILES: '
			return substitute(line, '^FILES: ', '', '')
		elseif line =~ '^INDEX: '
			fallback = substitute(line, '^INDEX: ', '', '')
		endif
	endfor
	return fallback
enddef


def OpenTarget(target: string)
	if target == '' || !filereadable(target)
		return
	endif
	checktime
	execute 'edit ' .. fnameescape(target)
enddef


def g:CountryFiles(country: string)
	var name = country
	if name == ''
		name = input(notebox.Prompt('getObnFiles.py'))
	endif
	if name == ''
		return
	endif

	SetEnv(NotesBox())
	notebox.Busy('getObnFiles.py', name)
	var out = RunScript(name, '')
	echom join(out, "\n")
	OpenTarget(ParseTarget(out))
enddef


def g:CountryFilesDelete(country: string)
	var name = country
	if name == ''
		name = input(notebox.DeletePrompt('getObnFiles.py'))
	endif
	if name == ''
		return
	endif

	if confirm(notebox.Label('getObnFiles.py') .. "\n"
		.. name .. ' için oluşturulan Dokümanlar sayfası ve hub linki silinsin mi?',
		"&Evet\n&Hayır", 2) != 1
		echom 'Silme iptal edildi'
		return
	endif

	SetEnv(NotesBox())
	notebox.Busy('getObnFiles.py', name)
	var out = RunScript(name, '--delete')
	echom join(out, "\n")
	checktime
enddef


command -nargs=? CountryFiles call g:CountryFiles(<q-args>)
command -nargs=? CountryFilesDelete call g:CountryFilesDelete(<q-args>)

nnoremap <unique> <Plug>CountryFiles; :CountryFiles<CR>
if !hasmapto('<Plug>CountryFiles;')
	nnoremap <unique> <Leader>cF <Plug>CountryFiles;
endif

nnoremap <unique> <Plug>CountryFilesDelete; :CountryFilesDelete<CR>
