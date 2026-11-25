vim9script
import autoload 'notebox.vim'

# vim-notebox icin getData.py (WorldBank gosterge raporu) entegrasyonu.
# Aktif not kutusunda (g:notes_directory) bir ulkenin WB gosterge raporu
# notunu uretir, ulke gosterge indeksini gunceller ve indeksi acar.
#
# Islem varsayilan olarak arka planda calisir; her gosterge icin tanilama
# satiri canli akitilir ve [Wbfetch] penceresinde toplanir.  g:wb_async = 0
# ile eski senkron davranisa donulur.

var wbdir = expand('<sfile>:p:h') .. '/scripts'

if !exists('g:wb_python')
	g:wb_python = wbdir .. '/venv/bin/python3'
endif

if !exists('g:wb_script')
	g:wb_script = wbdir .. '/getData.py'
endif

var s_lines: list<string> = []
var s_partial = ''
var s_logbuf = -1
var s_orig_win = 0
var s_running = false
var s_cancelled = false
var s_start = reltime()


def LogLine(line: string)
	s_lines->add(line)
	if s_logbuf > 0 && bufexists(s_logbuf)
		appendbufline(s_logbuf, '$', line)
	else
		# Tampon kapatildiysa (bwipeout) ayrinti kaybolmasin: sessizce ac.
		EnsureLogBuf(false)
		appendbufline(s_logbuf, '$', line)
	endif
enddef


def EnsureLogBuf(open: bool = true)
	if s_logbuf > 0 && bufexists(s_logbuf)
		return
	endif
	var buf = bufadd('[Wbfetch]')
	setbufvar(buf, '&buftype', 'nofile')
	setbufvar(buf, '&bufhidden', 'hide')
	setbufvar(buf, '&swapfile', 0)
	s_logbuf = buf
	if open
		execute 'botright sbuffer ' .. buf
	endif
enddef


def OpenLog()
	if s_logbuf > 0 && bufexists(s_logbuf)
		setbufvar(s_logbuf, '&bufhidden', 'hide')
		execute 'botright sbuffer ' .. s_logbuf
		silent! :%delete _
		return
	endif
	s_logbuf = -1
	EnsureLogBuf()
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


def SummaryLine(): string
	var summary = ''
	for line in s_lines
		if line =~ '^--- getData\.py: ÖZET'
			summary = substitute(line, '^--- getData\.py: ', '', '')
		endif
	endfor
	return summary
enddef


def ErrorLine(): string
	var error = ''
	for line in s_lines
		if line =~ '^HATA getData'
			error = substitute(line, '^HATA getData:\s*', '', '')
		endif
	endfor
	if strchars(error) > 120
		error = strcharpart(error, 0, 117) .. '...'
	endif
	return error
enddef


def Elapsed(): string
	return printf('%.1f sn', reltimefloat(reltime(s_start)))
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
	var cancelled = s_cancelled
	s_cancelled = false
	var target = TargetFromOutput()
	var summary = SummaryLine()
	var error = ErrorLine()
	if status != 0
		if cancelled
			echom notebox.Label('getData.py') .. ' — iptal edildi'
		elseif summary != ''
			# Gunlugu kapatma: hangi gostergenin dustugu burada gorunur.
			echom notebox.Label('getData.py') .. ' — ' .. summary
		elseif error != ''
			echom notebox.Label('getData.py') .. ' — ' .. error
		else
			echom notebox.Label('getData.py')
				.. ' — adımlardan biri başarısız; ayrıntı [Wbfetch] penceresinde'
		endif
		if s_logbuf > 0 && bufexists(s_logbuf) && bufwinid(s_logbuf) == -1
			execute 'botright sbuffer ' .. s_logbuf
		endif
		return
	endif
	if get(g:, 'wb_keep_log', 0) == 0
		var target_ok = target != '' && filereadable(target)
		if target_ok
			CloseLog()
		endif
	endif
	if target != '' && filereadable(target)
		if s_orig_win != 0 && win_id2win(s_orig_win) > 0
			win_gotoid(s_orig_win)
		endif
		execute 'edit ' .. fnameescape(target)
		if summary != ''
			echom notebox.Label('getData.py') .. ' — ' .. summary
				.. ' (' .. Elapsed() .. ')'
		else
			echom notebox.Label('getData.py') .. ' — tamamlandı ('
				.. Elapsed() .. ')'
		endif
	else
		echom notebox.Label('getData.py')
			.. ' — bitti ama INDEX üretilemedi; [Wbfetch] penceresine bakın'
	endif
enddef


def SetEnv(box: string)
	$NOTES_DIR = box
	$NOTES_BIB_DIR = box .. '/bibfiles'
	$NOTES_AUTOHUB = get(g:, 'notes_autohub', 1) ? '1' : '0'
	$NOTES_WB_REPORT_MAX_AGE_DAYS =
		string(get(g:, 'wb_report_max_age_days', 7))
enddef


def SyncRun(box: string, name: string)
	var cmd = 'cd ' .. shellescape(box)
		.. ' && ' .. shellescape(expand(g:wb_python))
		.. ' ' .. shellescape(expand(g:wb_script))
		.. ' ' .. shellescape(name)
	notebox.Busy('getData.py', name)
	var out = systemlist(cmd)
	for line in out
		notebox.Step(line)
	endfor
	var target = ''
	var summary = ''
	for line in out
		if line =~ '^INDEX: '
			target = substitute(line, '^INDEX: ', '', '')
		elseif line =~ '^--- getData\.py: ÖZET'
			summary = substitute(line, '^--- getData\.py: ', '', '')
		endif
	endfor
	checktime
	if target != '' && filereadable(target)
		execute 'edit ' .. fnameescape(target)
	endif
	if summary != ''
		echom notebox.Label('getData.py') .. ' — ' .. summary
	else
		echom notebox.Label('getData.py') .. ' — tamamlandı'
	endif
enddef


def g:WbFetch(country: string)
	if s_running
		echom notebox.Label('getData.py') .. ' — zaten çalışıyor'
		return
	endif

	var name = country
	if name == ''
		name = input(notebox.Prompt('getData.py'))
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

	if get(g:, 'wb_async', 1) == 0
		SyncRun(box, name)
		return
	endif

	s_lines = []
	s_partial = ''
	s_orig_win = win_getid()
	s_running = true
	s_cancelled = false
	s_start = reltime()

	OpenLog()

	var cmd: list<string> = [expand(g:wb_python), '-u',
		expand(g:wb_script), name]
	notebox.Busy('getData.py', name)
	var job = job_start(cmd, {out_cb: OutCb, err_cb: OutCb, exit_cb: ExitCb,
		cwd: box, mode: 'raw'})
	setbufvar(s_logbuf, 'wb_job', job)
enddef

def g:WbCancel()
	if s_logbuf <= 0 || !bufexists(s_logbuf)
		echom notebox.Label('getData.py') .. ' — çalışan iş yok'
		return
	endif
	var j = getbufvar(s_logbuf, 'wb_job', 0)
	if type(j) != v:t_job || job_status(j) != 'run'
		echom notebox.Label('getData.py') .. ' — çalışan iş yok'
		return
	endif
	job_stop(j)
	s_cancelled = true
enddef


def g:WbDelete(country: string)
	var name = country
	if name == ''
		name = input(notebox.DeletePrompt('getData.py'))
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
	if confirm(name .. ' için oluşturulan WorldBank gösterge notları silinsin mi?(E/H)',
		"&Evet\n&Hayır", 2) != 1
		echom 'Silme iptal edildi'
		return
	endif
	# JSON önbelleği ayrı sorulur ve varsayılan olarak korunur: bir sonraki
	# çalıştırma ağa çıkmadan aynı değerleri yeniden üretebilir.
	var extra = ''
	var cache = notebox.WbCacheInfo(name, box)
	if cache.exists && cache.files > 0
		if confirm(printf('%s için JSON önbelleği de silinsin mi? (%s — %d dosya)',
				name, cache.rel != '' ? cache.rel : cache.dir,
				cache.files), "&Evet\n&Hayır", 2) == 1
			extra = ' --delete-data'
		endif
	endif
	var cmd = 'cd ' .. shellescape(box)
		.. ' && ' .. shellescape(expand(g:wb_python))
		.. ' ' .. shellescape(expand(g:wb_script))
		.. ' ' .. shellescape(name) .. ' --delete' .. extra
	var out = systemlist(cmd)
	echom join(out, "\n")
	checktime
enddef


command -nargs=? Wbfetch call g:WbFetch(<q-args>)
command -nargs=? Wbdelete call g:WbDelete(<q-args>)
command -nargs=0 Wbcancel call g:WbCancel()

nnoremap <unique> <Plug>Wbfetch; :Wbfetch<CR>
if !hasmapto('<Plug>Wbfetch;')
	nnoremap <unique> <Leader>wbr <Plug>Wbfetch;
endif

nnoremap <unique> <Plug>Wbdelete; :Wbdelete<CR>
if !hasmapto('<Plug>Wbdelete;')
	nnoremap <unique> <Leader>wbd <Plug>Wbdelete;
endif

nnoremap <unique> <Plug>Wbcancel; :Wbcancel<CR>
if !hasmapto('<Plug>Wbcancel;')
	nnoremap <unique> <Leader>wbc <Plug>Wbcancel;
endif
