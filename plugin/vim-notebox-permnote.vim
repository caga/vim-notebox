vim9script
# vim-notebox: obn notundan kalici (permanent) not uretir.
#
# Gecerli not (n_type: obn ...) uzerinde calisir; yeni bir "perm" notu icin
# yeni id ve <id>.md adiyla, YAML basligi guncellenmis yeni bir tampon acar.
# Tampon KAYDEDILMEZ; yalnizca bibfile diske yazilir.
#
#   :MakePermNote [n_type]        (varsayilan: g:permnote_type = 'perm')
#   <Leader>pn

if !exists('g:permnote_type')
	g:permnote_type = 'perm'
endif
if !exists('g:permnote_split')
	g:permnote_split = 1
endif
if !exists('g:permnote_map')
	g:permnote_map = '<Leader>pn'
endif


def FieldRange(lines: list<string>): list<number>
	# YAML basligindaki alan satirlarinin 0-tabanli [ilk, son] araligi.
	if len(lines) == 0 || lines[0] !~ '^---\s*$'
		return []
	endif
	for i in range(1, len(lines) - 1)
		if lines[i] =~ '^---\s*$'
			return [1, i - 1]
		endif
	endfor
	return []
enddef


def YamlGet(lines: list<string>, field: string): string
	var r = FieldRange(lines)
	if empty(r) || r[0] > r[1]
		return ''
	endif
	var pat = '^' .. field .. '\s*:\s*'
	for idx in range(r[0], r[1])
		if lines[idx] =~ pat
			var v = trim(matchstr(lines[idx], pat .. '\zs.*'))
			v = substitute(v, '^"\(.*\)"$', '\1', '')
			v = substitute(v, "^'\(.*\)'$", '\1', '')
			return v
		endif
	endfor
	return ''
enddef


def YamlSet(lines: list<string>, field: string, value: string)
	var r = FieldRange(lines)
	if empty(r)
		return
	endif
	var pat = '^' .. field .. '\s*:'
	for idx in range(r[0], r[1])
		if lines[idx] =~ pat
			lines[idx] = field .. ': ' .. value
			return
		endif
	endfor
	insert(lines, field .. ': ' .. value, r[1] + 1)
enddef


def QuoteYaml(value: string): string
	return '"' .. substitute(value, '"', '\\"', 'g') .. '"'
enddef


def ClearBackReferences(lines: list<string>): list<string>
	var out = copy(lines)
	var br = -1
	for i in range(0, len(out) - 1)
		if out[i] =~ '^#BackReferences:'
			br = i
			break
		endif
	endfor
	if br >= 0
		out = br == 0 ? [] : out[0 : br - 1]
	endif
	while len(out) > 0 && trim(out[-1]) == ''
		remove(out, -1)
	endwhile
	add(out, '')
	add(out, '#BackReferences:')
	return out
enddef


def YamlDelPattern(lines: list<string>, pattern: string): list<string>
	# YAML basligi icindeki desene uyan alan satirlarini kaldirir.
	var r = FieldRange(lines)
	var out = []
	for i in range(0, len(lines) - 1)
		if !empty(r) && i >= r[0] && i <= r[1] && lines[i] =~ pattern
			continue
		endif
		add(out, lines[i])
	endfor
	return out
enddef


def NewId(notes_dir: string): number
	var id = localtime()
	while filereadable(notes_dir .. '/' .. id .. '.md')
		id += 1
	endwhile
	return id
enddef


def CloneBib(old_lines: list<string>, notes_dir: string, newid: number)
	var old_field = YamlGet(old_lines, 'bibliography')
	var new_abs = notes_dir .. '/' .. g:bibfiles_directory .. '/' .. newid .. '.bib'
	var bibdir = notes_dir .. '/' .. g:bibfiles_directory
	if !isdirectory(bibdir)
		mkdir(bibdir, 'p')
	endif
	var old_abs = old_field
	if old_abs != '' && old_abs !~ '^/'
		old_abs = notes_dir .. '/' .. old_abs
	endif
	if old_abs != '' && filereadable(old_abs)
		writefile(readfile(old_abs), new_abs)
		echom 'Bibfile olusturuldu: ' .. fnamemodify(new_abs, ':t')
	else
		writefile([], new_abs)
		echom 'UYARI: eski bibfile bulunamadi; bos bibfile olusturuldu'
	endif
enddef


def g:MakePermNote(n_type: string = '')
	# 1) Gecerli bir obn notu mu?
	if &buftype != '' || !filereadable(expand('%'))
		echom 'MakePermNote: kaydedilmis bir not tamponunda calistirin'
		return
	endif
	var old_lines = getline(1, '$')
	var old_type = YamlGet(old_lines, 'n_type')
	var toks = split(tolower(old_type))
	if index(toks, 'obn') < 0
		echom 'MakePermNote: bu not obn tipinde degil (' .. old_type .. ')'
		return
	endif
	if index(toks, 'dizin') >= 0 || index(toks, 'hub') >= 0
		echom 'MakePermNote: dizin/hub notlari desteklenmiyor'
		return
	endif

	# 2) Yeni id ve satirlar
	var notes_dir = expand(g:notes_directory)
	var newid = NewId(notes_dir)
	var new_type = n_type != '' ? n_type : g:permnote_type
	var lines = copy(old_lines)

	YamlSet(lines, 'id', string(newid))
	YamlSet(lines, 'date', strftime('%d/%m/%y'))
	YamlSet(lines, 'modify', '')
	YamlSet(lines, 'author', g:notes_author)
	YamlSet(lines, 'n_type', new_type)
	YamlSet(lines, 'bibliography', g:bibfiles_directory .. '/' .. newid .. '.bib')

	var title = YamlGet(old_lines, 'title')
	if title != ''
		var stripped = substitute(title, '\s*-\s*\S\+\s\+BN$', '', '')
		YamlSet(lines, 'title', QuoteYaml(stripped))
	endif

	lines = YamlDelPattern(lines, '^[A-Za-z0-9_]\+_key\s*:')
	lines = ClearBackReferences(lines)

	# 3) Yeni tampon (kaydedilmez)
	if get(g:, 'permnote_split', 1)
		execute 'new'
	else
		execute 'enew'
	endif
	setline(1, lines)
	setlocal filetype=markdown
	execute 'silent! file ' .. fnameescape(newid .. '.md')

	# 4) Bibfile'i kopyala
	CloneBib(old_lines, notes_dir, newid)

	echom 'MakePermNote: ' .. newid .. '.md (' .. new_type
		.. ') olusturuldu - KAYDEDILMEDI'
enddef


command -nargs=? MakePermNote call g:MakePermNote('<args>')

nnoremap <unique> <Plug>MakePermNote; :MakePermNote<CR>
if !hasmapto('<Plug>MakePermNote;')
	execute 'nnoremap <unique> ' .. g:permnote_map .. ' <Plug>MakePermNote;'
endif
