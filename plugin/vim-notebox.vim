vim9script
import '/home/osman/.vim/plugged/bibtexcite.vim/autoload/bibtexcite.vim'

var plugindir = expand('<sfile>:p:h:h')

#if !exists("b:bibtexcite_bibfile")
#	 b:bibtexcite#getbibfile() = "notes.bib"
#endif

if !exists("g:notes_directory")
	 g:notes_directory = "~/notes"
endif

if !exists("g:notes_author")
	 g:notes_author = " "
endif

if !exists("g:citation_style")
	 g:citation_style = $"{plugindir}/plugin/ieee-with-url.csl"
endif

if !exists("g:boxes")
	g:boxes = ["~/notes", "~/notes2"]
endif

if !exists("g:bibfiles_directory")
	 g:bibfiles_directory = "bibfiles"
endif

if !exists("g:bibfile")
	 g:bibfile = $"{plugindir}/plugin/notes.bib"
endif

#if !exists("g:bibfile")
#	 g:bibfile = $"{plugindir}/plugin/notes.bib"
#endif

if !exists("g:pdfdir")
	#g:pdfdir = $"{g:notes_directory}/pdfs"
	g:pdfdir = "pdfs"
endif
#execute $"cd {g:notes_directory}"

if !exists("g:docdir")
	#g:docdir = $"{g:notes_directory}/docs"
	g:docdir = "docs"
endif

# Rapor tazelik kontrolu (getStmd / getTmd)
if !exists("g:country_report_check")
	g:country_report_check = 1
endif
if !exists("g:country_report_ask")
	g:country_report_ask = 1
endif
if !exists("g:country_report_max_age_days")
	g:country_report_max_age_days = 7
endif

# Rapor tazelik kontrolu (getTbupNotes) - ayri esik
if !exists("g:tbup_report_check")
	g:tbup_report_check = 1
endif
if !exists("g:tbup_report_ask")
	g:tbup_report_ask = 1
endif
if !exists("g:tbup_report_max_age_days")
	g:tbup_report_max_age_days = 30
endif

# Rapor tazelik kontrolu (getTubitakNotes) - ayri esik
if !exists("g:tubitak_report_check")
	g:tubitak_report_check = 1
endif
if !exists("g:tubitak_report_ask")
	g:tubitak_report_ask = 1
endif
if !exists("g:tubitak_report_max_age_days")
	g:tubitak_report_max_age_days = 30
endif

# Rapor tazelik kontrolu (getKosgebNotes) - ayri esik
if !exists("g:kosgeb_report_check")
	g:kosgeb_report_check = 1
endif
if !exists("g:kosgeb_report_ask")
	g:kosgeb_report_ask = 1
endif
if !exists("g:kosgeb_report_max_age_days")
	g:kosgeb_report_max_age_days = 30
endif

# TUBITAK esleme tuslari (varsayilan: <Leader>tu / <Leader>tud)
if !exists("g:tubitak_fetch_map")
	g:tubitak_fetch_map = '<Leader>tu'
endif
if !exists("g:tubitak_delete_map")
	g:tubitak_delete_map = '<Leader>tud'
endif

# KOSGEB esleme tuslari (varsayilan: <Leader>tk / <Leader>tkd)
if !exists("g:kosgeb_fetch_map")
	g:kosgeb_fetch_map = '<Leader>tk'
endif
if !exists("g:kosgeb_delete_map")
	g:kosgeb_delete_map = '<Leader>tkd'
endif

# Rapor tazelik kontrolu (getTuysgmNotes) - ayri esik
if !exists("g:tuysgm_report_check")
	g:tuysgm_report_check = 1
endif
if !exists("g:tuysgm_report_ask")
	g:tuysgm_report_ask = 1
endif
if !exists("g:tuysgm_report_max_age_days")
	g:tuysgm_report_max_age_days = 30
endif

# TUYSGM esleme tuslari (varsayilan: <Leader>ty / <Leader>tyd)
if !exists("g:tuysgm_fetch_map")
	g:tuysgm_fetch_map = '<Leader>ty'
endif
if !exists("g:tuysgm_delete_map")
	g:tuysgm_delete_map = '<Leader>tyd'
endif

# Rapor tazelik kontrolu (getOtherBns) - ayri esik
if !exists("g:otherbn_report_check")
	g:otherbn_report_check = 1
endif
if !exists("g:otherbn_report_ask")
	g:otherbn_report_ask = 1
endif
if !exists("g:otherbn_report_max_age_days")
	g:otherbn_report_max_age_days = 30
endif

# Diger kurum BN esleme tuslari (varsayilan: <Leader>bn / <Leader>bnd)
if !exists("g:otherbn_fetch_map")
	g:otherbn_fetch_map = '<Leader>bn'
endif
if !exists("g:otherbn_delete_map")
	g:otherbn_delete_map = '<Leader>bnd'
endif

# obn -> kalici (permanent) not: MakePermNote
if !exists("g:permnote_type")
	g:permnote_type = 'perm'
endif
if !exists("g:permnote_split")
	g:permnote_split = 1
endif
if !exists("g:permnote_map")
	g:permnote_map = '<Leader>pn'
endif


def ListBoxes()
	var i = 1
	for box in g:boxes
		echo $"{i} - {g:boxes[i - 1]}"
		i = i + 1
	endfor
enddef

def ChooseBox(): string
	ListBoxes()
	var box = input($"Please choose box:")
	if box == ""
		var cbox = g:boxes[0]
		g:notes_directory = cbox
#		g:pdfdir = cbox #becareful with that line - you may want to delete it in the future
		echo "\n" .. "Current Note Box: " .. g:notes_directory
		return cbox
	endif
	var cbox = g:boxes[str2nr(box) - 1]
	g:notes_directory = cbox
	#g:pdfdir = $"{g:notes_directory}/pdfs"
	#g:docdir = $"{g:notes_directory}/docs"
	g:pdfdir = "pdfs"
	g:docdir = "docs"
	g:bibfiles_directory = "bibfiles"
	execute $"cd {g:notes_directory}"
	echo "\n" .. "Current Note Box and pwd: " .. g:notes_directory
	return cbox
enddef


def ChooseBoxSilent(): string
	ListBoxes()
	var box = input($"Please choose box:")
	if box == ""
		var cbox = g:boxes[0]
		g:notes_directory = cbox
		return cbox
	endif
	var cbox = g:boxes[str2nr(box) - 1]
	g:notes_directory = cbox
	return cbox
enddef

def WhichBox(): string
	echo "Current Note Box: " .. g:notes_directory
	return g:notes_directory
enddef


def EditNoteId(id: number)
	search("id")
	execute $"normal 0f:d$A: {id}"
enddef

def EditAuthor(auth: string)
	search("author")
	execute $"normal 0f:d$A: {auth}"
enddef

def EditTitle(exp: string)
	search('^title:')
	execute $"normal 0f:d$A: {exp} "
enddef

def EditDate(dat: string)
	search("date:")
	execute $"normal 0f:d$A: {dat}"

enddef

def ModifyDate()
	var date = strftime("%d/%m/%y")
	search("modify:")
	execute $"normal 0f:d$A: {date}"
enddef

def EditCitationStyle()
	search("citation-style:")
	execute $"normal 0f:d$A: {g:citation_style}"
enddef

def EditBibFilePlace(bibfile: string ="bibfiles/notes.bib")
	search("bibliography:")
	execute $"normal 0f:d$A: {bibfile}"
enddef

# Bu EditBibFilePlace2 bibtexcite ile aynı bibfile kullanmak için yazıldı:
def EditBibFilePlace2()
	var bibfile2 = bibtexcite#get_bibfile()
	search("bibliography:")
	execute $"normal 0f:d$A: {bibfile2}"
enddef

#def EditBibFilePlace3(id)
#	bibtexcite#bibtexcite_bibfile = 
	#var bibfile = ()
	#search("bibliography:")
	#execute $"normal 0f:d$A: {bibfile2}"
#enddef

def CapitalizeAndUnite(phrase: string = ""): string
	var prefix = phrase
	var dummy = split(prefix)
	var capitalAndUnite = ""
	for word in dummy
		capitalAndUnite = capitalAndUnite .. toupper(word[0]) .. word[1 : ]
	endfor
	return capitalAndUnite
enddef

def NewNote(phrase: string = "" )

	var id = localtime()
	var filename = CapitalizeAndUnite(phrase)
#	var note = $"{g:notes_directory}/{filename .. "_Id" .. id}.md"
	var note = $"{id}" .. ".md"
	var date = strftime("%d/%m/%y")
	var bibfile = $"{id}" .. ".bib"
	exe $"new {note}"
	exe $":0r {plugindir}/plugin/zettelskeleton.zet"
	EditNoteId(id)
	EditAuthor(g:notes_author)
	EditDate(date)
	EditCitationStyle()
	EditBibFilePlace()
	EditTitle(phrase)
enddef

def CheckFileExist(file: string): string
	var res = trim(system($"[ -f {file} ] && echo 'yes' || echo 'no'"))
	return res
enddef

def CreateBibFileForNote(file: string): string
	var id = GetNoteId(file)
	var bibfileName = id .. '.bib'
	var bibfileFullPath = $"{g:bibfiles_directory}/{bibfileName}"
	var existence = CheckFileExist($"{bibfileFullPath}")
	if  existence == 'yes'
		echom "Specific Note-Bibfile already exists, quiting"
	endif
	if existence == 'no'
		var res = system($"touch {bibfileFullPath}")
		if res == ''
			echom $"Specific Note-Bibfile created as: {bibfileFullPath}"
		endif
		if res != ''
			echom $"Bibfile is not created. maybe there is no bibfiles directory under {g:notes_directory}"
			bibfileFullPath = 'error'
		endif
		echom res
	endif
	return bibfileFullPath
enddef

def CreateAndWriteNoteBibFile(file: string)
	var res = CreateBibFileForNote(file)
	if res != 'error'
		EditBibFilePlace(res)
		echom "Bibfile fullpath is written in note metadata"
	endif
	if res == 'error'
		echom "Bibfile can't be written"
	endif
enddef
		



#def GetNoteBibFile(file: string): string
#	var soup = readfile(file)
#	var bibfile = ""
#	bibfile = split(soup[6])[1]
#	return bibfile
#enddef

def GetNoteBibFile(file: string): string
	var bibfile = GetYamlField(file, 'bibliography')
	return bibfile
enddef

def OpenNoteBibFile(note: string)
	var bibfile = GetNoteBibFile(note)
	if !filereadable(bibfile)
		echom $"Current bib file for note, {bibfile} is not readable"
	endif

	if filereadable(bibfile)
		exe $"new {bibfile}"
	endif
enddef



#def NoteFilename(id: number): string
#	var file = $"{g:notes_directory}/{id}.md"
#	if !filereadable(expand(file)) 
#		throw $"No Readable File for {file}"
#	endif
#	return file
#enddef

#def OpenNoteById(id: number)
#	var file = NoteFilename(id)
#		execute $"edit {file}"
#enddef

def LastNote(): string 
	var cmd = $"ls {g:notes_directory}/*.md -lt | head -n 1 | tail -n 1 | rev | cut -d' ' -f1 | rev"
	var lnote = system(cmd)
	var checkvar = join(split(lnote)[0 : 2])
	if checkvar == "ls: cannot access"
		throw $"No Readabe File for Last Note {lnote}"
	endif
	return lnote
enddef

def LastNotes(snlf: string)
	var nlf = str2nr(snlf)
	var cmd = $"ls *.md -t|head -n {nlf}"
	var lnotes = systemlist(cmd)
	cgetexpr lnotes
	copen
enddef

def OpenLastNote()
	var file = LastNote()
	execute $"edit {file}"
enddef

# def GetCurrentNoteId(): number
# 	var save_yank = @0
# 	var save_cursor = getcurpos()
# 	execute "normal! gg"
# 	if search("id:") != 0
# 		execute "normal 0f:wyw"
# 		var id = str2nr(@0)
# 		@0 = save_yank
# 		setpos('.', save_cursor)
# 		return id
# 	endif
# 	throw "GetCurrentNoteId: There is no 'id' section found in the file"
# enddef

# def YankCurrentNoteId()
# 	var id = GetCurrentNoteId()
# 	@0 = id
# enddef

# def GetCurrentNoteFilename(): string
# 	var id = GetCurrentNoteId()
# 	var file = id .. ".md"
# 	return file
# enddef

# def YankCurrentNoteFilename(): string
# 	filename = GetCurrentNoteFilename()
# 	@0 = file
# enddef


# def GetCurrentNoteExplanation(): string
# 	var save_yank = @0
# 	var save_cursor = getcurpos()
# 	search("n_explanation:")
# 	execute "normal 0f:w"
# 	var a = getcurpos()[2]
# 	if a <= 15
# 		echo "explanation needed"
# 		return "explanation needed "
# 	endif
# 	execute "normal! y$"
# 	var exp = @0
# 	@0 = save_yank
# 	setpos('.', save_cursor)
# 	return exp
# enddef

# def YankCurrentNoteExplanation(): string
# 	var exp = GetCurrentNoteExplanation()
# 	@0 = exp
# enddef
# def GetCurrentNoteMarkdownLink(): string
# 	var filename = GetCurrentNoteFilename()
# 	var explanation = GetCurrentNoteExplanation()
# 	var link = "[[" .. explanation .. "]" .. "(" .. filename .. ")]"
# 	return link
# enddef

# def YankCurrentNoteMarkdownLink()
# 	var link = GetCurrentNoteMarkdownLink()
# 	@0 = link
# 	echom "Link Copied"
# enddef

# def GetNoteId(file: string = " "): number
# 	try
# 	execute ":new temporary.md"
# 	execute $":read {file}"
# 	catch /E484/
# 		echo "No such file"
# 		execute ":q!"
# 		return 0
# 	endtry
# 	normal! gg
# 	var a = search("id")
# 	if a == 0
# 		echom "no id found"
# 		execute ":q!"
# 		return -1 
# 	endif
# 	normal! f:wy$
# 	var id = @0
# 	execute ":q!"
# 	var file_id = fnamemodify(file, ":t:r")
# 	if id == file_id
# 		echo str2nr(id)
# 		return str2nr(id)
# 	else
# 		echom "note id and id in filename does not match, maybe a different document"
# 		return 0
# 	endif
# enddef

# Simple function to get YAML field from a file
def GetYamlField(file: string, field: string): string
    # Read the file
    var lines = readfile(file)
    
    # Check if it has a YAML header
    if len(lines) == 0 || lines[0] !~ '^---$'
        return ''
    endif
    
    # Find the end of header
    var end_line = 0
    for i in range(1, len(lines) - 1)
        if lines[i] =~ '^---$'
            end_line = i
            break
        endif
    endfor
    
    if end_line == 0
        return ''
    endif
    
    # Search for the field between line 1 and end_line-1
    var pattern = '^' .. field .. '\s*:\s*'
    for i in range(1, end_line - 1)
        if lines[i] =~ pattern
            var value = matchstr(lines[i], pattern .. '\zs.*')
            value = trim(value)
            # Remove quotes if present
            value = substitute(value, '^"\(.*\)"$', '\1', '')
            value = substitute(value, "^'\(.*\)'$", '\1', '')
            return value
        endif
    endfor
    
    return ''
enddef

def GetNoteId(file: string): number
	var id = GetYamlField(file, 'id')
	var nid = str2nr(id)
	return nid
enddef

#def GetNoteId(file: string): number
#	var soup = readfile(file)
#	var id = 0
#	try
#	id = str2nr(split(soup[1])[1])
#	catch
#		id = 0
#		return 0
#	endtry
#	return id
#enddef


def IsNote(file: string): number
	var id = GetNoteId(file)
	return id
enddef

#def GetNoteExplanation(file: string): string
#	var soup = readfile(file)
#	var exp = join(split(soup[4])[1 : ])
#	return exp
#enddef

def GetNoteExplanation(file: string): string
	var exp = GetYamlField(file, 'title')
	return exp
enddef

def CreateNoteLink(file: string): string
	var link = $"[{GetNoteExplanation(file)}]({file})"
	return link
enddef

def YankNoteLink(file: string)
	var link = CreateNoteLink(file)
	echom link
	@@ = link
enddef
	
#def BackReferencesOld(id: number): list<string>
#	var files = split(system($"grep -lid skip {id} {g:notes_directory}/*"))
#	var referees = []
#	for file in files
#		if GetNoteId(file) != id && GetNoteId(file) > 0
#			add(referees, file)
#		endif
#	endfor
#	return sort(referees)
#enddef

#First Line Number Function
def FLN(st: string, file: string): number
	var raw_number = systemlist($"grep -n '{st}' {file}|cut -d':' -f1")
	var first_number = -2
	try
	first_number = str2nr(raw_number[0])
	catch
		return -1
	endtry
	return first_number
enddef



# Last Line Number Function
def LLN(st: string, file: string): number
	var raw_number = systemlist($"grep -n '{st}' {file}|cut -d':' -f1")
	var last_number = -2
	try
	last_number = str2nr(raw_number[-1])
	catch
		return -1
	endtry
	return last_number
enddef


def BackReferences(id: number, thefile: string): list<string>
	var brl: number 
	var rfl: number 
	var referees: list<string>
	#var files = split(system($"grep -lid skip {id} {g:notes_directory}/*"))
	var files = split(system($"grep -lid skip {thefile} {g:notes_directory}/*"))
	# backreferences altındaki isimleri de dahil etmesin diye bu FLN ve
	# LLN fonksyonlarını kullanıp çile çekiyoruz.
	var filename: string # bu da yeni
	for file in files
		brl = LLN("#BackReferences", file)
		if brl == -1 
			brl = 1000000
		endif
		#rfl = FLN($"{id}", file)
		rfl = FLN(thefile, file)
		if GetNoteId(file) != id && GetNoteId(file) > 0 && (rfl > 0) && (rfl < brl) 
			filename = fnamemodify(file, ':t') #yeni satır
			add(referees, filename) # buda yeni
			#add(referees, file)
		endif
	endfor
	return sort(referees)
enddef

def ParseYamlField(lines: list<string>, field: string): string
	if len(lines) == 0 || lines[0] !~ '^---$'
		return ''
	endif
	var end_line = 0
	for i in range(1, len(lines) - 1)
		if lines[i] =~ '^---$'
			end_line = i
			break
		endif
	endfor
	if end_line == 0
		return ''
	endif
	var pattern = '^' .. field .. '\s*:\s*'
	for i in range(1, end_line - 1)
		if lines[i] =~ pattern
			var value = matchstr(lines[i], pattern .. '\zs.*')
			value = trim(value)
			value = substitute(value, '^"\(.*\)"$', '\1', '')
			value = substitute(value, "^'\(.*\)'$", '\1', '')
			return value
		endif
	endfor
	return ''
enddef

# Tek geçişte, tüm notları belleğe okuyup geri referansları hesaplar.
# Eski sürüm her not için ayrı ayrı grep/readfile çalıştırıyordu (O(N^2)).
def OrphanNotes(): list<string>
	var dir = expand(g:notes_directory)
	var paths = filter(glob(dir .. '/*', true, true), (_, p) => filereadable(p))
	var data: dict<list<string>> = {}
	var ids: dict<number> = {}
	for p in paths
		var lines = readfile(p)
		var name = fnamemodify(p, ':t')
		data[name] = lines
		ids[name] = str2nr(ParseYamlField(lines, 'id'))
	endfor

	var name_set: dict<bool> = {}
	var refs: dict<number> = {}
	for name in keys(data)
		refs[name] = 0
		if ids[name] > 0
			name_set[name] = true
		endif
	endfor

	for b in keys(data)
		if ids[b] <= 0
			continue
		endif
		var lines = data[b]
		var hdr = -1
		for i in range(len(lines) - 1, 0, -1)
			if lines[i] =~ '#BackReferences'
				hdr = i
				break
			endif
		endfor
		var last = hdr < 0 ? len(lines) : hdr
		var seen: dict<bool> = {}
		for i in range(0, last - 1)
			var pos = 0
			while true
				var m = matchstrpos(lines[i], '\f\+', pos)
				if m[1] < 0
					break
				endif
				pos = m[2]
				var refname = m[0]
				if refname != b && has_key(name_set, refname)
					seen[refname] = true
				endif
			endwhile
		endfor
		for r in keys(seen)
			refs[r] = refs[r] + 1
		endfor
	endfor

	var orphans: list<string> = []
	for name in keys(data)
		if ids[name] > 0 && refs[name] == 0
			orphans->add(name)
		endif
	endfor
	return sort(orphans)
enddef

def WriteOrphanNotes()
	var orphans = OrphanNotes()
	# Satırları bellekte kurup tampona tek seferde yazıyoruz. Eski sürüm
	# her satır için ayrı bir normal! komutu çalıştırdığı için yavaştı.
	var lines: list<string> = ['', 'OrphanNotes:']
	var i = 0
	for orphan in orphans
		i = i + 1
		lines->add($"{i}- " .. CreateNoteLink(orphan))
		lines->add('')
	endfor
	exe $"new {g:notes_directory}/OrphanNotes.md"
	silent! deletebufline(bufnr(), 1, '$')
	silent noautocmd setline(1, lines)
enddef
def g:Deneme()
	echom "Merhaba"
enddef
	
def WriteBackReferences()
	var file = expand("%:t")
	var id = GetNoteId(file)
	var backrefs = BackReferences(id, file)
	cursor(line('$'), 100)
	var backrefHeaderLine = search('#BackReferences', 'b')
	if backrefHeaderLine == 0
		execute "normal! Go\<esc>o#BackReferences "
		backrefHeaderLine = getcurpos()[1]
	endif
	setpos('.', [0, backrefHeaderLine, 0])
	execute "normal! dGo#BackReferences:\<esc>o"
	var i = 0
	for ref in backrefs
		i = i + 1
		execute $"normal! o{i}- {CreateNoteLink(ref)}\<esc>o"
	endfor
enddef

def OpenNoteBox()
	execute $"e {g:notes_directory}"
enddef

def GetNoteTitle(file: string): string
    var title = GetYamlField(file, 'title')
    if title == ''
        title = fnamemodify(file, ':t:r')
    endif
    return title
enddef

def SingleTermSearch(keyword: string): list<string>
    var results = systemlist($"grep -l '{keyword}' {g:notes_directory}/*.md")
    if empty(results)
        echom $"SingleTermSearch: keyword: '{keyword}' returns no result"
        return []
    endif
    return results
enddef

def SingleTermSearchForFiles(keyword: string, files: string): list<string>
    if files == ""
        return []
    endif
    var searchSentence = $"grep -l '{keyword}' {files}"
    var results = systemlist(searchSentence)
    return results
enddef

def NoteSearch(keywords: string)
    set efm=%f
    setqflist([])
    var Keywords = split(keywords, '\;')

    if len(Keywords) == 0
        echom "No keyword is given"
        return
    endif

    var result_files: list<string> = []
    
    if len(Keywords) == 1 
        result_files = SingleTermSearch(Keywords[0])
        if empty(result_files)
            echom "NoteSearch: Exiting Search"
            return
        endif
    else
        var files = ""
        var i = 0
        for keyword in Keywords
            if i == 0
                var first_result = SingleTermSearch(keyword)
                if empty(first_result)
                    echom "NoteSearch: First Keyword Returns No Results. Exiting Search"
                    return
                endif
                files = join(first_result, ' ')
                i = i + 1
                continue
            endif
            var next_result = SingleTermSearchForFiles(keyword, files)
            if empty(next_result)
                echom "NoteSearch: No results for keyword: " .. keyword
                return
            endif
            files = join(next_result, ' ')
            i = i + 1
        endfor
        if files != ""
            result_files = split(files)
        endif
    endif
    
    if empty(result_files)
        echo "NoteSearch: There is no search result"
        setqflist([])
    else
        var qf_list: list<dict<any>> = []
        for file in result_files
            var title = GetNoteTitle(file)
            var dict = {
                filename: file,
                text: title,
                lnr: 1,
                col: 1,
                module: fnamemodify(file, ':t')
            }
            add(qf_list, dict)
        endfor
        setqflist(qf_list)
        copen
    endif
enddef

def NoteSearchInBox(keywords: string)
	var cbox = WhichBox()
	ChooseBoxSilent()
	NoteSearch(keywords)
	g:notes_directory = cbox
enddef


def WordSearch(keyword: string)
	NoteSearch(keyword)
enddef

def LoadBibFile(file: string)
	var isNote = IsNote(expand("%"))
	if isNote != 0
		g:bibtexcite_bibfile = GetNoteBibFile(expand("%"))
		echom $"Loaded bibfile is : {g:bibtexcite_bibfile}" 
	endif
	if isNote == 0
		echom "Can't load bibfile! This is not a standart note!"
	endif
enddef

augroup SettingBibFileSpecificToNoteForBibtexcite
	au!
	autocmd BufEnter *.md {
		LoadBibFile(expand("%"))
	}  
augroup END


command -nargs=* Newnote :call NewNote(<q-args>)
command -nargs=0 Writeback :call WriteBackReferences()
command -nargs=1 Getnoteid :call GetNoteId(expand(<q-args>))
command -nargs=0 Openlastnote :call OpenLastNote()
command -nargs=0 Openbox :call OpenNoteBox()
command -nargs=0 Choosebox :call ChooseBox()
command -nargs=* Notesearch :call NoteSearch(<q-args>)
command -nargs=* NoteSearchInbox :call NoteSearchInBox(<q-args>)
command -nargs=0 Whichbox :call WhichBox()
command -nargs=0 Orphans :call WriteOrphanNotes()
command -nargs=1 Lastnotes :call LastNotes(<q-args>)
command -nargs=0 Modifydate :call ModifyDate()


if !hasmapto('<Plug>Newnote;')
	map <unique> <Leader>nn <Plug>Newnote;
endif

if !hasmapto('<Plug>Yanknotelink;')
	map <unique> <Leader>yn <Plug>Yanknotelink;
endif

if !hasmapto('<Plug>Opennotebox;')
 	map <unique> <Leader>ob <Plug>Openbox;
endif

if !hasmapto('<Plug>Openlastnote;')
 	map <unique> <Leader>ln <Plug>Openlastnote;
endif

if !hasmapto('<Plug>Selectbox;')
 	map <unique> <Leader>sb <Plug>Selectbox;
endif

if !hasmapto('<Plug>Searchword;')
 	map <unique> <Leader>s <Plug>Searchword;
endif

if !hasmapto('<Plug>Notesearch;')
 	map <unique> <Leader>ns <Plug>Notesearch;
endif

if !hasmapto('<Plug>Whichbox;')
 	map <unique> <Leader>wb <Plug>Whichbox;
endif

if !hasmapto('<Plug>WriteBacklinks;')
 	map <unique> <Leader>bl <Plug>WriteBacklinks;
endif

if !hasmapto('<Plug>NoteSearchInbox;')
 	map <unique> <Leader>nsb <Plug>NoteSearchInbox;
endif

if !hasmapto('<Plug>Modifydate;')
 	map <unique> <Leader>md <Plug>Modifydate;
endif

if !hasmapto('<Plug>CreateAndWriteNoteBibFile;')
 	map <unique> <Leader>cbf <Plug>Createandwritenotebibfile;
endif

if !hasmapto('<Plug>OpenNoteBibFile;')
 	map <unique> <Leader>obf <Plug>Opennotebibfile;
endif

if !hasmapto('<Plug>OpenNoteBibFile;')
 	map <unique> <Leader>lbf <Plug>Loadbibfile;
endif

noremap <unique> <script> <Plug>Selectbox; <SID>Selectbox
noremap <SID>Selectbox :call <SID>ChooseBox()<CR>

noremap <unique> <script> <Plug>Newnote; <SID>Newnote
#noremap <SID>Newnote :call <SID>NewNote()<CR>
noremap <SID>Newnote :Newnote 

noremap <unique> <script> <Plug>Yanknotelink; <SID>Yanknotelink
#noremap <SID>Yanknotelink :call <SID>YankNoteLink(expand("%"))<CR>
noremap <SID>Yanknotelink :call <SID>YankNoteLink(expand("%:t"))<CR>

noremap <unique> <script> <Plug>Openbox; <SID>Openbox
noremap <SID>Openbox :call <SID>OpenNoteBox()<CR>

noremap <unique> <script> <Plug>Openlastnote; <SID>Openlastnote
noremap <SID>Openlastnote :call <SID>OpenLastNote()<CR>

noremap <unique> <script> <Plug>Searchword; <SID>Searchword
noremap <SID>Searchword :call <SID>WordSearch(expand("<cword>"))<CR>

noremap <unique> <script> <Plug>Notesearch; <SID>Notesearch
noremap <SID>Notesearch :Notesearch 

noremap <unique> <script> <Plug>Whichbox; <SID>Whichbox
noremap <SID>Whichbox :call <SID>WhichBox()<CR>

noremap <unique> <script> <Plug>WriteBacklinks; <SID>WriteBacklinks
noremap <SID>WriteBacklinks :call <SID>WriteBackReferences()<CR>

noremap <unique> <script> <Plug>NoteSearchInbox; <SID>NoteSearchInbox
noremap <SID>NoteSearchInbox :NoteSearchInbox 

noremap <unique> <script> <Plug>Modifydate; <SID>Modifydate
noremap <SID>Modifydate :call <SID>ModifyDate()<CR>

noremap <unique> <script> <Plug>Createandwritenotebibfile; <SID>Createandwritenotebibfile
noremap <SID>Createandwritenotebibfile :call <SID>CreateAndWriteNoteBibFile(expand("%"))<CR>

noremap <unique> <script> <Plug>Opennotebibfile; <SID>Opennotebibfile
noremap <SID>Opennotebibfile :call <SID>OpenNoteBibFile(expand("%"))<CR>

noremap <unique> <script> <Plug>Loadbibfile; <SID>Loadbibfile
noremap <SID>Loadbibfile :call <SID>LoadBibFile(expand("%"))<CR>
