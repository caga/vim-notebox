vim9script
# vim-notebox icin getTbupNotes.py entegrasyonu (asenkron).
# Bir ulkenin T.C. Ticaret Bakanligi "Ulke Profili" PDF'ini indirip notlara
# cevirir, notlari ulke tbup hub'ina baglar ve o hub notunu acar.
# Islem arka planda calisir; vim donmaz.
# g:tbup_async = 0 ile eski senkron davranisa donulur.

var cdir = expand('<sfile>:p:h') .. '/scripts'

if !exists('g:tbup_python')
	g:tbup_python = cdir .. '/venv/bin/python3'
endif

if !exists('g:tbup_script')
	g:tbup_script = cdir .. '/getTbupNotes.py'
endif

var s_lines: list<string> = []
var s_partial = ''
var s_logbuf = -1
var s_orig_win = 0
var s_running = false


def LogLine(line: string)
	s_lines->add(line)
	if s_logbuf > 0 && bufexists(s_logbuf)
		appendbufline(s_logbuf, '$', line)
	endif
enddef


def OutCb(_ch: channel, msg: string)
	s_partial = s_partial .. msg
	while true
		var nl = stridx(s_partial, "\n")
		if nl < 0
			break
		endif
		var line = strpart(s_partial, 0, nl)
		s_partial = strpart(s_partial, nl + 1)
		LogLine(line)
	endwhile
enddef


def TargetFromOutput(): string
	if s_partial != ''
		LogLine(s_partial)
		s_partial = ''
	endif
	var target = ''
	for line in s_lines
		if line =~ '^INDEX: '
			target = substitute(line, '^INDEX: ', '', '')
		endif
	endfor
	return target
enddef


def CloseLog()
	if s_logbuf > 0 && bufexists(s_logbuf)
		var wi = bufwinid(s_logbuf)
		if wi != -1
			win_execute(wi, 'close')
		endif
	endif
enddef


def ExitCb(_j: job, status: number)
	s_running = false
	var target = TargetFromOutput()
	if target != '' && filereadable(target)
		CloseLog()
		if s_orig_win != 0 && win_id2win(s_orig_win) > 0
			win_gotoid(s_orig_win)
		endif
		execute 'edit ' .. fnameescape(target)
		if status != 0
			echom 'Tbupfetch tamamlandı (bazı adımlar HATA verdi; çıktıya bakın)'
		else
			echom 'Tbupfetch tamamlandı'
		endif
	else
		echom 'Tbupfetch bitti ama hedef üretilemedi; günlük penceresine bakın'
	endif
enddef


def SetEnv(box: string)
	$NOTES_DIR = box
	$NOTES_BIB_DIR = box .. '/bibfiles'
	$NOTES_AUTOHUB = get(g:, 'notes_autohub', 1) ? '1' : '0'
	$TBUP_PDF_DIR = get(g:, 'tbup_pdfdir', box .. '/tbupPdfs')
enddef


def SyncRun(box: string, name: string)
	var cmd = 'cd ' .. shellescape(box)
		.. ' && ' .. shellescape(expand(g:tbup_python))
		.. ' ' .. shellescape(expand(g:tbup_script))
		.. ' --yes ' .. shellescape(name)
	var out = systemlist(cmd)
	echom join(out, "\n")
	var target = ''
	for line in out
		if line =~ '^INDEX: '
			target = substitute(line, '^INDEX: ', '', '')
		endif
	endfor
	checktime
	if target != '' && filereadable(target)
		execute 'edit ' .. fnameescape(target)
	endif
enddef


def g:TbupFetch(country: string)
	if s_running
		echom 'Tbupfetch zaten çalışıyor'
		return
	endif

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

	SetEnv(box)

	if get(g:, 'tbup_async', 1) == 0
		SyncRun(box, name)
		return
	endif

	s_lines = []
	s_partial = ''
	s_orig_win = win_getid()
	s_running = true

	execute 'botright new'
	setlocal buftype=nofile bufhidden=wipe noswapfile
	silent! file [Tbupfetch]
	s_logbuf = bufnr('%')
	setlocal modifiable
	echom 'Tbupfetch başladı (arka planda)...'

	var cmd: list<string> = [expand(g:tbup_python), expand(g:tbup_script),
		'--yes', name]
	job_start(cmd, {out_cb: OutCb, err_cb: OutCb, exit_cb: ExitCb, cwd: box,
		mode: 'raw'})
enddef


command -nargs=? Tbupfetch call g:TbupFetch(<q-args>)

nnoremap <unique> <Plug>Tbupfetch; :Tbupfetch<CR>
if !hasmapto('<Plug>Tbupfetch;')
	nnoremap <unique> <Leader>tb <Plug>Tbupfetch;
endif
