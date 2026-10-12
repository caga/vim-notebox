vim9script
# vim-notebox icin getCountry.py entegrasyonu (asenkron).
# Bir ulke icin tum otomatik sayfalari uretir (dbwn, WB gostergeleri, tek
# tarafli ticaret, ikili ticaret (TUR), harita), ciktilari canli akitir ve
# haritayi ulke hub sayfasinda YAML basliginin hemen altina yerlestirir.
# Islem arka planda calisir; vim donmaz. Bitince ulke hub'i acilir.
# g:country_async = 0 ile eski senkron davranisa donulur.

var cdir = expand('<sfile>:p:h') .. '/scripts'

if !exists('g:country_python')
	g:country_python = cdir .. '/venv/bin/python3'
endif

if !exists('g:country_script')
	g:country_script = cdir .. '/getCountry.py'
endif

if !exists('g:country_map_height')
	g:country_map_height = 350
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
		if line =~ '^HUB: '
			target = substitute(line, '^HUB: ', '', '')
		endif
	endfor
	if target == ''
		for line in s_lines
			if line =~ '^INDEX: '
				target = substitute(line, '^INDEX: ', '', '')
			endif
		endfor
	endif
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


def FailureSummary(): string
	# getCountry.py'nin ürettiği FAILED:/NODATA: satırlarını okunur özete çevirir.
	var parts: list<string> = []
	for line in s_lines
		if line =~ '^FAILED: '
			parts->add('HATA ' .. substitute(line, '^FAILED: ', '', ''))
		elseif line =~ '^NODATA: '
			parts->add('veri yok ' .. substitute(line, '^NODATA: ', '', ''))
		endif
	endfor
	return join(parts, ' | ')
enddef


def ExitCb(_j: job, status: number)
	s_running = false
	var target = TargetFromOutput()
	if status != 0
		# Günlüğü KAPATMA: hangi adımın düştüğü burada görünür.
		var summary = FailureSummary()
		if summary != ''
			echom 'Countryfetch: sorunlu adımlar — ' .. summary
		else
			echom 'Countryfetch: adımlardan biri başarısız — ayrıntı [Countryfetch] penceresinde'
		endif
		return
	endif
	if get(g:, 'country_keep_log', 0) == 0
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
		echom 'Countryfetch tamamlandı'
	else
		echom 'Countryfetch bitti ama hedef üretilemedi; günlük penceresine bakın'
	endif
enddef


def SetEnv(box: string)
	$NOTES_DIR = box
	$NOTES_BIB_DIR = box .. '/bibfiles'
	$NOTES_AUTOHUB = get(g:, 'notes_autohub', 1) ? '1' : '0'
	$NOTES_MAP_HEIGHT = string(g:country_map_height)
enddef


def SyncRun(box: string, name: string)
	var cmd = 'cd ' .. shellescape(box)
		.. ' && ' .. shellescape(expand(g:country_python))
		.. ' ' .. shellescape(expand(g:country_script))
		.. ' ' .. shellescape(name)
	var out = systemlist(cmd)
	echom join(out, "\n")
	var target = ''
	for line in out
		if line =~ '^HUB: '
			target = substitute(line, '^HUB: ', '', '')
		endif
	endfor
	if target == ''
		for line in out
			if line =~ '^INDEX: '
				target = substitute(line, '^INDEX: ', '', '')
			endif
		endfor
	endif
	checktime
	if target != '' && filereadable(target)
		execute 'edit ' .. fnameescape(target)
	endif
enddef


def g:CountryFetch(country: string)
	if s_running
		echom 'Countryfetch zaten çalışıyor'
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

	if get(g:, 'country_async', 1) == 0
		SyncRun(box, name)
		return
	endif

	s_lines = []
	s_partial = ''
	s_orig_win = win_getid()
	s_running = true

	execute 'botright new'
	setlocal buftype=nofile bufhidden=wipe noswapfile
	silent! file [Countryfetch]
	s_logbuf = bufnr('%')
	setlocal modifiable
	echom 'Countryfetch başladı (arka planda)...'

	var cmd: list<string> = [expand(g:country_python), expand(g:country_script), name]
	job_start(cmd, {out_cb: OutCb, err_cb: OutCb, exit_cb: ExitCb, cwd: box, mode: 'raw'})
enddef


command -nargs=? Countryfetch call g:CountryFetch(<q-args>)

nnoremap <unique> <Plug>Countryfetch; :Countryfetch<CR>
if !hasmapto('<Plug>Countryfetch;')
	nnoremap <unique> <Leader>cf <Plug>Countryfetch;
endif
