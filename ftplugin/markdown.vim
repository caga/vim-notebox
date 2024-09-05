vim9script noclear

var pdfdir = $"{g:notes_directory}/pdfs"

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

def CreatePdfDirectory(): string
	if CheckPdfDirectory() == "no"
		system($"mkdir {g:notes_directory}/pdfs -p")
		echo $"'pdfs' directory created: {g:notes_directory}/pdfs"
	return $"pdf directory created: {g:notes_directory}/pdfs"
	endif
	return $"pdf directory is under {g:notes_directory}/pdfs"
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

def Convert2Pdf(file: string): string
	var trimmedFilename = fnamemodify(file, ":t:r")
	var pdfFilename = trimmedFilename .. ".pdf"
	var pdfFullPath = $"{pdfdir}/{pdfFilename}"
 	var file2 = pdfFullPath
	CreatePdfDirectory()
	# var fileden = expand("%.")
	if IsNewerFile(file, file2) == 1
		var res = system($"pandoc -f markdown -t pdf {file} -o {file2} --lua-filter=$HOME/.bin/pandocFilters/links-to-pdf.lua --filter mermaid-filter --filter pandoc-crossref --citeproc")
		echom "Doing the convertion"
		return res
	endif
	echom "Convertion is not needed"
	return "Convertion is not needed"
enddef


def ViewPdf(file: string)
	
	var trimmedFilename = fnamemodify(file, ":t:r")
	var pdfFilename = trimmedFilename .. ".pdf"
	var pdfFullPath = $"{pdfdir}/{pdfFilename}"
	echom pdfFullPath
	Convert2Pdf(file)
  	var res = system($"zathura {pdfFullPath} & disown")
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

if !hasmapto('<Plug>Viewpdf;')
	map <buffer> <unique> <Leader>v <Plug>Viewpdf;
endif

if !hasmapto('<Plug>DeleteNote;')
	map <buffer> <unique> <Leader>dn <Plug>Deletenote
endif

nnoremap <buffer> <Plug>Viewpdf :call <SID>ViewPdf(expand("%"))<CR>
nnoremap <buffer> <Plug>Deletenote :call <SID>DeleteCurrentNote()<CR>
