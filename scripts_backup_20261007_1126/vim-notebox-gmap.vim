vim9script
# vim-notebox icin getMap.py entegrasyonu.
# Aktif not kutusunda (g:notes_directory) bir ulkenin haritasini indirir,
# data/img/maps/{iso3}.png olarak kaydeder ve imlece markdown resim linki ekler.
# Harita daha once indirilmisse yeniden indirmek icin sorar.
# Bu dosya mevcut vim-notebox dosyalarini degistirmez; bagimsiz calisir.

var gmapdir = expand('<sfile>:p:h') .. '/scripts'

if !exists('g:gmap_python')
	g:gmap_python = gmapdir .. '/venv/bin/python3'
endif

if !exists('g:gmap_script')
	g:gmap_script = gmapdir .. '/getMap.py'
endif

if !exists('g:gmap_height')
	g:gmap_height = 350
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

def RunGmap(name: string, extra: string): list<string>
	var cmd = 'cd ' .. shellescape(expand(g:notes_directory))
		.. ' && ' .. shellescape(g:gmap_python)
		.. ' ' .. shellescape(g:gmap_script)
		.. ' ' .. shellescape(name)
	if extra != ''
		cmd = cmd .. ' ' .. extra
	endif
	return systemlist(cmd)
enddef

def ParseMap(out: list<string>): string
	for line in out
		if line =~ '^MAP: '
			return substitute(line, '^MAP: ', '', '')
		endif
	endfor
	return ''
enddef

def g:GmapFetch(country: string)
	var name = country
	if name == ''
		name = input('Ülke (iso3/ad): ')
	endif
	if name == ''
		return
	endif

	var box = NotesBox()
	$KUNYE_NOTES_DIR = box
	$KUNYE_MAPS_DIR = box .. '/data/img/maps'

	# 1) Indirmeden hedef yolu coz.
	var map = ParseMap(RunGmap(name, '--path'))
	if map == ''
		echom 'Harita yolu bulunamadi (ulke cozulemedi?).'
		return
	endif

	# 2) Dosya varsa yeniden indirmek icin sor.
	if filereadable(map)
		var choice = confirm('Harita zaten var. Yeniden indirilsin mi?', "&Evet\n&Hayır", 2)
		if choice == 1
			var out = RunGmap(name, '--force')
			map = ParseMap(out)
			echom join(out, "\n")
		endif
	else
		var out = RunGmap(name, '')
		map = ParseMap(out)
		echom join(out, "\n")
	endif

	if map == '' || !filereadable(map)
		return
	endif

	# 3) Imlece markdown resim linki ekle.
	var link = '![](data/img/maps/' .. fnamemodify(map, ':t')
		.. '){ height=' .. g:gmap_height .. 'px }'
	execute 'normal! a' .. link .. "\<Esc>"
enddef

command -nargs=? Gmapfetch call g:GmapFetch(<q-args>)

nnoremap <unique> <Plug>Gmapfetch; :Gmapfetch<CR>
if !hasmapto('<Plug>Gmapfetch;')
	nnoremap <unique> <Leader>gm <Plug>Gmapfetch;
endif
