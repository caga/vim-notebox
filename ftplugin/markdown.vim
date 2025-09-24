vim9script noclear

#var pdfdir = $"{g:notes_directory}/pdfs"
#var pdfdir = $"{g:notes_directory}"
var plugindir = expand('<sfile>:p:h:h')
var pdfdir = $"{g:pdfdir}"
var docdir = $"{g:docdir}"
if exists("b:did_ftplugin")
	finish
endif

b:did_ftplugin = 1

# if !exists("g:pdf_directory")
# 	 g:pdf_directory = "~/notespdf"
# endif


def CheckPdfDirectory(): string
	var res = trim(system($"[ -d {pdfdir} ] && echo 'yes' || echo 'no'"))
	return res
enddef

def CheckDocDirectory(): string
	var res = trim(system($"[ -d {docdir} ] && echo 'yes' || echo 'no'"))
	return res
enddef

def CreatePdfDirectory(): string
	if CheckPdfDirectory() == "no"
		system($"mkdir {g:notes_directory}/pdfs -p")
		echo $"'pdfs' directory created: {g:notes_directory}/pdfs"
	return $"pdf directory created: {g:notes_directory}/pdfs"
	endif
	return $"pdf directory is under {g:notes_directory}/pdfs"
enddef

def CreateDocDirectory(): string
	if CheckDocDirectory() == "no"
		system($"mkdir {g:notes_directory}/docs -p")
		echo $"'docs' directory created: {g:notes_directory}/docs"
	return $"docs directory created: {g:notes_directory}/docs"
	endif
	return $"doc directory is under {g:notes_directory}/docs"
enddef

def IsNewerFile(file1: string, file2: string): number
	var res = trim(system($"[ {file1} -nt {file2} ] && echo 'yes' || echo 'no'"))
	if res == "yes"
		return 1 
	endif
	if res == "no"
		return 0
	endif
	return 2
enddef

def Convert2Pdf(mdfile: string, pdffile: string): string

	CreatePdfDirectory()

	if IsNewerFile(mdfile, pdffile) == 1
		var res = system($"pandoc -f markdown -t pdf {mdfile} -o {pdffile} --filter mermaid-filter --filter $HOME/.bin/pandoc-crossref --citeproc")
		
		echom "Doing the convertion"
		echom res
		return res
	endif
	#if filereadable(file2)
	echom "Convertion is not needed"
	return "Convertion is not needed"
enddef

def Convert2Doc(mdfile: string, docfile: string): string
	CreateDocDirectory()
	if IsNewerFile(mdfile, docfile) == 1
#		var res = system($"pandoc -f markdown+implicit_figures -t docx {mdfile} -o {docfile} --filter mermaid-filter --filter $HOME/.bin/pandoc-crossref --citeproc --reference-doc={plugindir}/ftplugin/pandocOrjRef.docx")
		var res = system($"pandoc -f markdown+implicit_figures+table_captions -t odt {mdfile} -o {docfile} --filter mermaid-filter --filter $HOME/.bin/pandoc-crossref --citeproc --reference-doc={plugindir}/ftplugin/referenceOdt.odt")
		echom "Doing the convertion"
		echom res
		return res
	endif
	echom "Convertion is not needed"
	return "Convertion is not needed"
enddef

def ViewPdf(mdfile: string)
	var trimmedFilename = fnamemodify(mdfile, ":t:r")
	var pdfFilename = trimmedFilename .. ".pdf"
	var pdfFullPath = $"{pdfdir}/{pdfFilename}"
	var pdffile = pdfFullPath

	Convert2Pdf(mdfile, pdffile)
  	var res = system($"zathura {pdffile} & disown")
enddef



def ViewDoc(mdfile: string)
	
	var trimmedFilename = fnamemodify(mdfile, ":t:r")
#	var docFilename = trimmedFilename .. ".docx"
	var docFilename = trimmedFilename .. ".odt"
	var docFullPath = $"{docdir}/{docFilename}"
	var docfile = docFullPath
	Convert2Doc(mdfile, docfile)
 	var res = system($"libreoffice {docfile} & disown")
enddef

#def ViewDoc(mdfile: string)
	
#	var trimmedFilename = fnamemodify(mdfile, ":t:r")
#	var docFilename = trimmedFilename .. ".odt"
#	var docFullPath = $"{docdir}/{docFilename}"
#	#var pdfFullPath = $"{docdir}{docFilename}"
#	var docfile = docFullPath
#	Convert2Doc(mdfile, docfile)
#  	var res = system($"libreoffice {docfile} & disown")
#enddef

def SaveAsAndView(mdfile: string): string
	var filetype = str2nr(input("Please select filetype, 1-pdf or 2-doc \n choicenumber?:"))
	var OutputFileName = input($"please input the filename including full directory:")

	if filetype == 1
		
		var pdfFullPath = $"{pdfdir}/{OutputFileName}"
		var pdffile = pdfFullPath
		Convert2Pdf(mdfile, pdffile)
		echom $"Document is saved as {pdffile}"
		var res = system($"zathura {pdffile} & disown")
		return $"\nDocument is saved as {pdffile}"
	endif

	if filetype == 2
		var docFullPath = $"{docdir}/{OutputFileName}"
		var docfile = docFullPath
		Convert2Doc(mdfile, docfile)
		echom $"Document is saved as {docfile}"
		var res = system($"libreoffice {docfile} & disown")
		return $"\nDocument is saved as {docfile}"
	endif
	if filetype != 1 && filetype != 2
		echom "\nNo Valid Choice is made"
		return "No Valid Choice is made"
	endif
	return "Bye From SaveAndView"
enddef

def AreYouSure(action: string): number
	var res = input($"Are you sure to {action}? (y/n): ")
	if res == "y"
		#echo " -> Done!"
		return 1
	endif
	if res == "n"
		#echo " -> Not Done!"
		return 0
	endif
	if res != "y" && res != "n"
		#echo " -> Not Understood"
		return -1
	endif
	return -2
enddef

def DeleteCurrentNote()
	var sure = AreYouSure("delete current note")
	if sure == 1
		delete(expand('%')) | bdelete!
		echo " -> Current Note Deleted"
	else
		echo " -> Note not deleted"
	endif
enddef

command -buffer -nargs=0 Viewpdf :call ViewPdf(expand("%"))
command -buffer -nargs=0 Viewdoc :call ViewDoc(expand("%"))
command -buffer -nargs=0 Saveas :call SaveAsAndView(expand("%"))

if !hasmapto('<Plug>Viewpdf;')
	map <buffer> <unique> <Leader>v <Plug>Viewpdf
endif

if !hasmapto('<Plug>Viewdoc;')
	map <buffer> <unique> <Leader>vd <Plug>Viewdoc
endif

if !hasmapto('<Plug>DeleteNote;')
	map <buffer> <unique> <Leader>dn <Plug>Deletenote
endif

if !hasmapto('<Plug>Saveas;')
	map <buffer> <unique> <Leader>sa <Plug>Saveas
endif

nnoremap <buffer> <Plug>Viewpdf :call <SID>ViewPdf(expand("%"))<CR>
nnoremap <buffer> <Plug>Viewdoc :call <SID>ViewDoc(expand("%"))<CR>
nnoremap <buffer> <Plug>Deletenote :call <SID>DeleteCurrentNote()<CR>
nnoremap <buffer> <Plug>Saveas :call <SID>SaveAsAndView(expand("%"))<CR>
