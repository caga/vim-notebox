vim9script
import autoload 'notebox.vim'

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

if !exists('g:tradeapp_dir')
	g:tradeapp_dir = '~/calisma/tmapp'
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
			echom notebox.Label('getCountry.py') .. ' — sorunlu adımlar — ' .. summary
		else
			echom notebox.Label('getCountry.py')
				.. ' — adımlardan biri başarısız; ayrıntı [Countryfetch] penceresinde'
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
		echom notebox.Label('getCountry.py') .. ' — tamamlandı'
	else
		echom notebox.Label('getCountry.py')
			.. ' — bitti ama hedef üretilemedi; günlük penceresine bakın'
	endif
enddef


def ReportField(out: list<string>, prefix: string): string
	for line in out
		if line =~ '^' .. prefix .. ': '
			return substitute(line, '^' .. prefix .. ': ', '', '')
		endif
	endfor
	return ''
enddef


def GateReport(box: string, name: string, script: string, label: string,
		prefix: string, year: string = ''): number
	# 1 = rapor uret, 0 = atla (taze veya kullanici hayir dedi)
	if get(g:, prefix .. '_report_check', 1) == 0
		return 1
	endif
	var cmd = 'cd ' .. shellescape(box)
		.. ' && ' .. shellescape(expand(g:country_python))
		.. ' ' .. shellescape(cdir .. '/' .. script)
		.. ' ' .. shellescape(name)
	if year != ''
		cmd ..= ' ' .. shellescape(year)
	endif
	cmd ..= ' --check'
	notebox.Checking(script)
	var out = systemlist(cmd)
	var exists = ReportField(out, 'REPORT_EXISTS')
	if exists == ''
		return 1
	endif
	var fresh = str2nr(ReportField(out, 'REPORT_FRESH'))
	var text = ReportField(out, 'REPORT_AGE_TEXT')
	var max_age = get(g:, prefix .. '_report_max_age_days', 7)
	if fresh == 1
		echom notebox.Label(script) .. ' atlandı: ' .. text
			.. ' (' .. max_age .. ' günden yeni)'
		return 0
	endif
	if get(g:, prefix .. '_report_ask', 1) != 0
		if confirm(notebox.Label(script) .. "\n" .. text
			.. "\nYeni rapor oluşturulsun mu?", "&Evet\n&Hayır", 2) != 1
			echom notebox.Label(script) .. ' atlandı: ' .. text
			return 0
		endif
	endif
	return 1
enddef


def SetEnv(box: string)
	$NOTES_DIR = box
	$NOTES_BIB_DIR = box .. '/bibfiles'
	$NOTES_AUTOHUB = get(g:, 'notes_autohub', 1) ? '1' : '0'
	$NOTES_MAP_HEIGHT = string(g:country_map_height)
	$NOTES_REPORT_MAX_AGE_DAYS = string(get(g:, 'country_report_max_age_days', 7))
	$TRADEAPP_DIR = expand(g:tradeapp_dir)
	$NOTES_LEADERS_REPORT_MAX_AGE_DAYS = string(get(g:, 'leaders_report_max_age_days', 30))
	$NOTES_WB_REPORT_MAX_AGE_DAYS = string(get(g:, 'wb_report_max_age_days', 7))
	$NOTES_TBUP_REPORT_MAX_AGE_DAYS = string(get(g:, 'tbup_report_max_age_days', 30))
	$NOTES_TUBITAK_REPORT_MAX_AGE_DAYS = string(get(g:, 'tubitak_report_max_age_days', 30))
	$NOTES_KOSGEB_REPORT_MAX_AGE_DAYS = string(get(g:, 'kosgeb_report_max_age_days', 30))
	$NOTES_TUYSGM_REPORT_MAX_AGE_DAYS = string(get(g:, 'tuysgm_report_max_age_days', 30))
	$NOTES_OTHERBN_REPORT_MAX_AGE_DAYS = string(get(g:, 'otherbn_report_max_age_days', 30))
enddef


def SyncRun(box: string, name: string, year: string)
	var extra = ''
	if GateReport(box, name, 'getLeaders.py', 'leaders', 'leaders') == 0
		extra = extra .. ' --skip-leaders'
	endif
	if GateReport(box, name, 'getUlkeTrapor.py', 'stmd', 'country', year) == 0
		extra = extra .. ' --skip-stmd'
	endif
	if GateReport(box, name, 'getIkiliRapor.py', 'tmd', 'country', year) == 0
		extra = extra .. ' --skip-tmd'
	endif
	if GateReport(box, name, 'getTbupNotes.py', 'tbup', 'tbup') == 0
		extra = extra .. ' --skip-tbup'
	endif
	if GateReport(box, name, 'getTubitakNotes.py', 'tubitak', 'tubitak') == 0
		extra = extra .. ' --skip-tubitak'
	endif
	if GateReport(box, name, 'getKosgebNotes.py', 'kosgeb', 'kosgeb') == 0
		extra = extra .. ' --skip-kosgeb'
	endif
	if GateReport(box, name, 'getTuysgmNotes.py', 'tuysgm', 'tuysgm') == 0
		extra = extra .. ' --skip-tuysgm'
	endif
	if GateReport(box, name, 'getOtherBns.py', 'otherbn', 'otherbn') == 0
		extra = extra .. ' --skip-otherbn'
	endif
	var year_arg = year == '' ? '' : ' --trade-year ' .. shellescape(year)
	var cmd = 'cd ' .. shellescape(box)
		.. ' && ' .. shellescape(expand(g:country_python))
		.. ' ' .. shellescape(expand(g:country_script))
		.. ' ' .. shellescape(name) .. year_arg
		.. extra
	notebox.Busy('getCountry.py', name)
	var out = systemlist(cmd)
	for line in out
		notebox.Step(line)
	endfor
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
		echom notebox.Label('getCountry.py') .. ' — zaten çalışıyor'
		return
	endif

	var parsed = notebox.SplitYear(country)
	var name = parsed[0]
	var year = parsed[1]
	if name == ''
		name = input(notebox.Prompt('getCountry.py'))
	endif
	if name == ''
		return
	endif
	if year != '' && year !~ '^\d\{4}$'
		echom notebox.Label('getCountry.py')
			.. ' — yıl 4 haneli olmalı (ör. 2025): ' .. year
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
		SyncRun(box, name, year)
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

	var cmd: list<string> = [expand(g:country_python), expand(g:country_script),
		name]
	if year != ''
		cmd->add('--trade-year')
		cmd->add(year)
	endif
	if GateReport(box, name, 'getLeaders.py', 'leaders', 'leaders') == 0
		cmd->add('--skip-leaders')
	endif
	if GateReport(box, name, 'getUlkeTrapor.py', 'stmd', 'country', year) == 0
		cmd->add('--skip-stmd')
	endif
	if GateReport(box, name, 'getIkiliRapor.py', 'tmd', 'country', year) == 0
		cmd->add('--skip-tmd')
	endif
	if GateReport(box, name, 'getTbupNotes.py', 'tbup', 'tbup') == 0
		cmd->add('--skip-tbup')
	endif
	if GateReport(box, name, 'getTubitakNotes.py', 'tubitak', 'tubitak') == 0
		cmd->add('--skip-tubitak')
	endif
	if GateReport(box, name, 'getKosgebNotes.py', 'kosgeb', 'kosgeb') == 0
		cmd->add('--skip-kosgeb')
	endif
	if GateReport(box, name, 'getTuysgmNotes.py', 'tuysgm', 'tuysgm') == 0
		cmd->add('--skip-tuysgm')
	endif
	if GateReport(box, name, 'getOtherBns.py', 'otherbn', 'otherbn') == 0
		cmd->add('--skip-otherbn')
	endif
	var subject = year == '' ? name : name .. ' (' .. year .. ')'
	notebox.Busy('getCountry.py', subject)
	job_start(cmd, {out_cb: OutCb, err_cb: OutCb, exit_cb: ExitCb, cwd: box, mode: 'raw'})
enddef


def g:CountryDelete(country: string)
	var name = notebox.SplitYear(country)[0]
	if name == ''
		name = input(notebox.DeletePrompt('getCountry.py'))
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
	if confirm(name .. ' için oluşturulan tüm otomatik bilgi notları silinsin mi?(E/H)',
		"&Evet\n&Hayır", 2) != 1
		echom 'Silme iptal edildi'
		return
	endif
	# JSON önbelleği (data/<iso3>/wbdata) ayrı sorulur; varsayılan koru.
	# Klasördeki Raporlar/, ciktilar/, eski/ gibi belgeler hiç etkilenmez.
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
		.. ' && ' .. shellescape(expand(g:country_python))
		.. ' ' .. shellescape(expand(g:country_script))
		.. ' ' .. shellescape(name) .. ' --delete' .. extra
	var out = systemlist(cmd)
	echom join(out, "\n")
	checktime
enddef


command -nargs=? Countryfetch call g:CountryFetch(<q-args>)
command -nargs=? Countrydelete call g:CountryDelete(<q-args>)

nnoremap <unique> <Plug>Countryfetch; :Countryfetch<CR>
if !hasmapto('<Plug>Countryfetch;')
	nnoremap <unique> <Leader>cf <Plug>Countryfetch;
endif

nnoremap <unique> <Plug>Countrydelete; :Countrydelete<CR>
if !hasmapto('<Plug>Countrydelete;')
	nnoremap <unique> <Leader>cD <Plug>Countrydelete;
endif
