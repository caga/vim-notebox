vim9script noclear

if exists("b:did_ftplugin")
	finish
endif
b:did_ftpugin = 1

# if !exists("g:pdf_directory")
# 	 g:pdf_directory = "~/notespdf"
# endif

var pdfdir = $"{g:notes_directory}/pdfs"

def CheckPdfDirectory(): string
	var res = trim(system($"[ -d {pdfdir} ] && echo 'yes' || echo 'no'"))
	return res
enddef

def g:CreatePdfDirectory()
	if CheckPdfDirectory() == "no"
		system($"mkdir {g:notes_directory}/pdfs -p")
	endif
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
# 	var file2 = $"pdfs/{pdfFilename}"
	var fileden = expand("%.")
	if IsNewerFile(file, file2) == 1
		var res = system($"pandoc -f markdown -t pdf {file} -o {file2} --lua-filter=$HOME/.bin/pandocFilters/links-to-pdf.lua --filter mermaid-filter --filter pandoc-crossref --citeproc")
		echom res
		echo res
		return res
	endif
# 	var res = system($"pandoc -f markdown -t pdf {file} -o pdfs/{trimmedFilename}.pdf --lua-filter=$HOME/.bin/pandocFilters/links-to-pdf.lua --filter mermaid-filter --filter pandoc-crossref --citeproc")
	return "Convertion is not needed"
enddef


def ViewPdf(file: string)
	
	var trimmedFilename = fnamemodify(file, ":t:r")
	var pdfFilename = trimmedFilename .. ".pdf"
	var pdfFullPath = $"{pdfdir}/{pdfFilename}"
	Convert2Pdf(file)
#  	var res = system($"zathura {pdfdir}/{pdfFilename} & disown")
  	var res = system($"zathura {pdfFullPath} & disown")
enddef


command -buffer -nargs=0 Viewpdf :call ViewPdf(expand("%"))

if !hasmapto('<Plug>Viewpdf;')
	map <buffer> <unique> <Leader>v <Plug>Viewpdf;
endif

nnoremap <buffer> <Plug>Viewpdf :call <SID>ViewPdf(expand("%"))<CR>

# def g:Deneme(file1: string, file2: string): string
# 	var res = IsNewerFile(file1, file2)
# 	return res
# enddef
