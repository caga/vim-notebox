vim9script
import autoload 'notebox.vim'

# vim-notebox icin getLeaders.py (CIA World Leaders) entegrasyonu.
# Bir ulkenin lider ve kabine uyelerini CIA World Leaders sayfasindan alir,
# "<Ulke> Liderler ve Kabine Uyeleri" icerik notunu uretir; notu ulke OBN
# sayfasindaki "## Liderler ve Kabine" bolumune dogrudan baglar ve kuresel
# "Liderler ve Kabine Dizini" notuna ekler.
# Rapor tazelik kontrolu: g:leaders_report_check / ask / max_age_days.

var ldir = expand('<sfile>:p:h') .. '/scripts'

if !exists('g:leaders_python')
	g:leaders_python = ldir .. '/venv/bin/python3'
endif

if !exists('g:leaders_script')
	g:leaders_script = ldir .. '/getLeaders.py'
endif

if !exists('g:leaders_fetch_map')
	g:leaders_fetch_map = '<Leader>wl'
endif

if !exists('g:leaders_delete_map')
	g:leaders_delete_map = '<Leader>wld'
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
	$NOTES_LEADERS_REPORT_MAX_AGE_DAYS =
		string(get(g:, 'leaders_report_max_age_days', 30))
enddef


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


def ParseTarget(out: list<string>): string
	var fallback = ''
	for line in out
		if line =~ '^NOTE: '
			return substitute(line, '^NOTE: ', '', '')
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


def SyncLinks(box: string, name: string)
	var out = systemlist('cd ' .. shellescape(box)
		.. ' && ' .. shellescape(expand(g:leaders_python))
		.. ' ' .. shellescape(expand(g:leaders_script))
		.. ' ' .. shellescape(name) .. ' --link-only')
	echom join(out, "\n")
enddef


def g:LeadersFetch(country: string)
	var name = country
	if name == ''
		name = input(notebox.Prompt('getLeaders.py'))
	endif
	if name == ''
		return
	endif

	var box = NotesBox()
	SetEnv(box)

	if get(g:, 'leaders_report_check', 1) != 0
		notebox.Checking('getLeaders.py')
		var chk = systemlist('cd ' .. shellescape(box)
			.. ' && ' .. shellescape(expand(g:leaders_python))
			.. ' ' .. shellescape(expand(g:leaders_script))
			.. ' ' .. shellescape(name) .. ' --check')
		var r = ParseReport(chk)
		if r.exists != ''
			if r.fresh == 1
				echom notebox.Label('getLeaders.py')
					.. ' — taze rapor, yenilenmedi: ' .. r.text
				SyncLinks(box, name)
				OpenTarget(r.exists)
				return
			endif
			if get(g:, 'leaders_report_ask', 1) != 0
				if confirm(notebox.Label('getLeaders.py') .. "\n" .. r.text
					.. "\nYeni rapor oluşturulsun mu?",
					"&Evet\n&Hayır", 2) != 1
					echom notebox.Label('getLeaders.py')
						.. ' — rapor yenilenmedi: ' .. r.text
					SyncLinks(box, name)
					OpenTarget(r.exists)
					return
				endif
			endif
		endif
	endif

	var cmd = 'cd ' .. shellescape(box)
		.. ' && ' .. shellescape(expand(g:leaders_python))
		.. ' ' .. shellescape(expand(g:leaders_script))
		.. ' ' .. shellescape(name) .. ' --force'
	notebox.Busy('getLeaders.py', name)
	var out = systemlist(cmd)
	echom join(out, "\n")
	OpenTarget(ParseTarget(out))
enddef


def g:LeadersDelete(country: string)
	var name = country
	if name == ''
		name = input(notebox.DeletePrompt('getLeaders.py'))
	endif
	if name == ''
		return
	endif

	if confirm(notebox.Label('getLeaders.py') .. "\n"
		.. name .. ' için oluşturulan liderler ve kabine notları silinsin mi?',
		"&Evet\n&Hayır", 2) != 1
		echom 'Silme iptal edildi'
		return
	endif

	var box = NotesBox()
	SetEnv(box)
	notebox.Busy('getLeaders.py', name)
	var out = systemlist('cd ' .. shellescape(box)
		.. ' && ' .. shellescape(expand(g:leaders_python))
		.. ' ' .. shellescape(expand(g:leaders_script))
		.. ' ' .. shellescape(name) .. ' --delete')
	echom join(out, "\n")
	checktime
enddef


command -nargs=? Leadersfetch call g:LeadersFetch(<q-args>)
command -nargs=? Leadersdelete call g:LeadersDelete(<q-args>)

nnoremap <unique> <Plug>Leadersfetch; :Leadersfetch<CR>
if !hasmapto('<Plug>Leadersfetch;')
	execute 'nnoremap <unique> ' .. g:leaders_fetch_map
		.. ' <Plug>Leadersfetch;'
endif

nnoremap <unique> <Plug>Leadersdelete; :Leadersdelete<CR>
if !hasmapto('<Plug>Leadersdelete;')
	execute 'nnoremap <unique> ' .. g:leaders_delete_map
		.. ' <Plug>Leadersdelete;'
endif
