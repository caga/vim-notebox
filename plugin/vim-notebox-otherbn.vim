vim9script
import autoload 'notebox.vim'

# vim-notebox icin getOtherBns.py entegrasyonu (asenkron).
# Bir ulke icin "diger" kurum bilgi notu belgelerini
# (data/gbns) tarar, ulkeye iliskin bolumleri ayirir, kurum bazli
# hub'lara baglar ve ilk hub notunu acar. Islem arka planda calisir.
# g:otherbn_async = 0 ile senkron davranisa donulur.

var cdir = expand('<sfile>:p:h') .. '/scripts'

if !exists('g:otherbn_python')
	g:otherbn_python = cdir .. '/venv/bin/python3'
endif

if !exists('g:otherbn_script')
	g:otherbn_script = cdir .. '/getOtherBns.py'
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
		notebox.Step(line)
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
			echom notebox.Label('getOtherBns.py')
				.. ' — tamamlandı (bazı adımlar HATA verdi; çıktıya bakın)'
		else
			echom notebox.Label('getOtherBns.py') .. ' — tamamlandı'
		endif
	else
		echom notebox.Label('getOtherBns.py')
			.. ' — bitti ama hedef üretilemedi; günlük penceresine bakın'
	endif
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


def GateOtherbn(box: string, name: string): dict<any>
	# {run: bool, target: path}
	if get(g:, 'otherbn_report_check', 1) == 0
		return {run: true, target: ''}
	endif
	var cmd = 'cd ' .. shellescape(box)
		.. ' && ' .. shellescape(expand(g:otherbn_python))
		.. ' ' .. shellescape(expand(g:otherbn_script))
		.. ' ' .. shellescape(name) .. ' --check'
	notebox.Checking('getOtherBns.py')
	var r = ParseReport(systemlist(cmd))
	if r.exists == ''
		return {run: true, target: ''}
	endif
	if r.fresh == 1
		echom notebox.Label('getOtherBns.py') .. ' atlandı: ' .. r.text .. ' ('
			.. get(g:, 'otherbn_report_max_age_days', 30) .. ' günden yeni)'
		return {run: false, target: r.exists}
	endif
	if get(g:, 'otherbn_report_ask', 1) != 0
		if confirm(notebox.Label('getOtherBns.py') .. "\n" .. r.text
			.. "\nYeni rapor oluşturulsun mu?",
			"&Evet\n&Hayır", 2) != 1
			echom notebox.Label('getOtherBns.py') .. ' atlandı: ' .. r.text
			return {run: false, target: r.exists}
		endif
	endif
	return {run: true, target: ''}
enddef


def OpenTarget(target: string)
	checktime
	if target != '' && filereadable(target)
		execute 'edit ' .. fnameescape(target)
	endif
enddef


def SetEnv(box: string)
	$NOTES_DIR = box
	$NOTES_BIB_DIR = box .. '/bibfiles'
	$NOTES_AUTOHUB = get(g:, 'notes_autohub', 1) ? '1' : '0'
	$NOTES_OTHERBN_REPORT_MAX_AGE_DAYS = string(get(g:, 'otherbn_report_max_age_days', 30))
enddef


def SyncRun(box: string, name: string)
	var gate = GateOtherbn(box, name)
	if !gate.run
		OpenTarget(gate.target)
		return
	endif
	var cmd = 'cd ' .. shellescape(box)
		.. ' && ' .. shellescape(expand(g:otherbn_python))
		.. ' ' .. shellescape(expand(g:otherbn_script))
		.. ' --yes --force ' .. shellescape(name)
	notebox.Busy('getOtherBns.py', name)
	var out = systemlist(cmd)
	echom join(out, "\n")
	var target = ''
	for line in out
		if line =~ '^INDEX: '
			target = substitute(line, '^INDEX: ', '', '')
		endif
	endfor
	OpenTarget(target)
enddef


def g:OtherbnFetch(country: string)
	if s_running
		echom notebox.Label('getOtherBns.py') .. ' zaten çalışıyor'
		return
	endif

	var name = country
	if name == ''
		name = input(notebox.Prompt('getOtherBns.py'))
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

	if get(g:, 'otherbn_async', 1) == 0
		SyncRun(box, name)
		return
	endif

	var gate = GateOtherbn(box, name)
	if !gate.run
		OpenTarget(gate.target)
		return
	endif

	s_lines = []
	s_partial = ''
	s_orig_win = win_getid()
	s_running = true

	execute 'botright new'
	setlocal buftype=nofile bufhidden=wipe noswapfile
	silent! file [Otherbnfetch]
	s_logbuf = bufnr('%')
	setlocal modifiable
	notebox.Busy('getOtherBns.py', name)

	var cmd: list<string> = [expand(g:otherbn_python), expand(g:otherbn_script),
		'--yes', '--force', name]
	job_start(cmd, {out_cb: OutCb, err_cb: OutCb, exit_cb: ExitCb, cwd: box,
		mode: 'raw'})
enddef


def g:OtherbnDelete(country: string)
	var name = country
	if name == ''
		name = input(notebox.DeletePrompt('getOtherBns.py'))
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
	if confirm(name .. ' için oluşturulan diğer kurum bilgi notları silinsin mi?(E/H)',
		"&Evet\n&Hayır", 2) != 1
		echom 'Silme iptal edildi'
		return
	endif
	var cmd = 'cd ' .. shellescape(box)
		.. ' && ' .. shellescape(expand(g:otherbn_python))
		.. ' ' .. shellescape(expand(g:otherbn_script))
		.. ' ' .. shellescape(name) .. ' --delete'
	var out = systemlist(cmd)
	echom join(out, "\n")
	checktime
enddef


command -nargs=? Otherbnfetch call g:OtherbnFetch(<q-args>)
command -nargs=? Otherbndelete call g:OtherbnDelete(<q-args>)

nnoremap <unique> <Plug>Otherbnfetch; :Otherbnfetch<CR>
if !hasmapto('<Plug>Otherbnfetch;')
	execute 'nnoremap <unique> ' .. get(g:, 'otherbn_fetch_map', '<Leader>bn')
		.. ' <Plug>Otherbnfetch;'
endif

nnoremap <unique> <Plug>Otherbndelete; :Otherbndelete<CR>
if !hasmapto('<Plug>Otherbndelete;')
	execute 'nnoremap <unique> ' .. get(g:, 'otherbn_delete_map', '<Leader>bnd')
		.. ' <Plug>Otherbndelete;'
endif
