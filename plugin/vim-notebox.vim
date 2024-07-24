vim9script

var plugindir = expand('<sfile>:p:h:h')

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

if !exists("g:bibfile")
	 g:bibfile = $"{plugindir}/plugin/notes.bib"
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
		echo "\n" .. "Current Note Box: " .. g:notes_directory
		return cbox
	endif
	var cbox = g:boxes[str2nr(box) - 1]
	g:notes_directory = cbox
# 	execute $"cd {g:notes_directory}"
	echo "\n" .. "Current Note Box: " .. g:notes_directory
	return cbox
enddef

def WhichBox(): string
	echo "\n" .. "Current Note Box: " .. g:notes_directory
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
	search("title:")
	execute $"normal 0f:d$A: {exp} "
enddef


def EditDate(dat: string)
	search("date:")
	execute $"normal 0f:d$A: {dat}"

enddef

def EditCitationStyle()
	search("citation-style:")
	execute $"normal 0f:d$A: {g:citation_style}"
enddef

def EditBibFilePlace()
	search("bibliography:")
	execute $"normal 0f:d$A: {g:bibfile}"
enddef

def NewNote(phrase: string = "" )
	var id = localtime()
	var note = $"{g:notes_directory}/{id}.md"
	var date = strftime("%d/%m/%y")
	exe $"new {note}"
	exe $":0r {plugindir}/plugin/zettelskeleton.zet"
	EditNoteId(id)
	EditAuthor(g:notes_author)
	EditDate(date)
	EditCitationStyle()
	EditBibFilePlace()
	EditTitle(phrase)
enddef

def NoteFilename(id: number): string
	var file = $"{g:notes_directory}/{id}.md"
	if !filereadable(expand(file)) 
		throw $"No Readable File for {file}"
	endif
	return file
enddef

def OpenNoteById(id: number)
	var file = NoteFilename(id)
		execute $"edit {file}"
enddef

def LastNote(): string 
	var cmd = $"ls {g:notes_directory}/*.md -lt | head -n 1 | tail -n 1 | rev | cut -d' ' -f1 | rev"
	var lnote = system(cmd)
	var checkvar = join(split(lnote)[0 : 2])
	if checkvar == "ls: cannot access"
		throw $"No Readabe File for Last Note {lnote}"
	endif
	return lnote
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

def GetNoteId(file: string): number
	var soup = readfile(file)
	var id = str2nr(split(soup[1])[1])
	return id
enddef

def GetNoteExplanation(file: string): string
	var soup = readfile(file)
	var exp = join(split(soup[4])[1 : ])
	return exp
enddef

def CreateNoteLink(file: string): string
	var link = $"[{GetNoteExplanation(file)}]({file})"
	return link
enddef

def YankNoteLink(file: string)
	var link = CreateNoteLink(file)
	@0 = ""
	@0 = link
enddef
	
def BackReferences(id: number): list<string>
	var files = split(system($"grep -lid skip {id} {g:notes_directory}/*"))
	var referees = []
	for file in files
		if GetNoteId(file) != id && GetNoteId(file) > 0
			add(referees, file)
		endif
	endfor
	return sort(referees)
enddef

def WriteBackReferences()
	var file = expand("%:p")
	var id = GetNoteId(file)
	var backrefs = BackReferences(id)
	cursor(line('$'), 100)
	var backrefHeaderLine = search('#BackReferences', 'b')
	if backrefHeaderLine < 0
		execute "normal! Go#BackReferences "
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
def SingleTermSearchInBox(keyword: string): string
 		var results = join(systemlist($"grep -lid recurse {keyword} {g:notes_directory}/*.md"), ' ')
		return results
enddef

def SingleTermSearchForFiles(keyword: string, files: string): string
	var searchSentence = $"grep -lid recurse {keyword} {files}"
	var results = join(systemlist(searchSentence), ' ')
	return results
enddef

def NoteSearch(keywords: string): string
	set efm=%f
	var Keywords =  split(keywords)

	if len(Keywords) == 0
		echom "No keyword is given"
		return "No keyword"
	endif

	if len(Keywords) == 1 
		var files = SingleTermSearchInBox(Keywords[0])
		cgetexpr split(files)
		copen
		return files
	endif

	var files = ""
	var i = 0

	for keyword in Keywords
		if i == 0
			files = SingleTermSearchInBox(keyword)
			i = i + 1
			continue
		endif
		files = SingleTermSearchForFiles(keyword, files)
		i = i + 1
	endfor
# 	return files
	  	if empty(files)
	  		echo "NoteSearch: There is no search result"
			cexpr []
	  	else
	  	cgetexpr split(files)
	  	copen
	  	endif
		return files
enddef

def WordSearch(keyword: string)
		NoteSearch(keyword)
enddef


command -nargs=* Newnote :call NewNote(<q-args>)
command -nargs=0 Writeback :call WriteBackReferences()
command -nargs=1 Getnoteid :call GetNoteId(expand(<q-args>))
command -nargs=0 Openlastnote :call OpenLastNote()
command -nargs=0 Openbox :call OpenNoteBox()
command -nargs=0 Choosebox :call ChooseBox()
command -nargs=* Notesearch :call NoteSearch(<q-args>)
command -nargs=0 Whichbox :call WhichBox()

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

noremap <unique> <script> <Plug>Selectbox; <SID>Selectbox
noremap <SID>Selectbox :call <SID>ChooseBox()<CR>

noremap <unique> <script> <Plug>Newnote; <SID>Newnote
noremap <SID>Newnote :call <SID>NewNote()<CR>

noremap <unique> <script> <Plug>Yanknotelink; <SID>Yanknotelink
noremap <SID>Yanknotelink :call <SID>YankNoteLink(expand("%"))<CR>

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
