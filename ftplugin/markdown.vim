vim9script noclear

if exists("b:did_ftplugin")
	finish
endif
b:did_ftpugin = 1

def g:Convert2Pdf(file: string): string
	var trimmedFilename = fnamemodify(file, ":t:r")
	var res = system($"pandoc -f markdown -t pdf {file} -o ~/notespdf/{trimmedFilename}.pdf --lua-filter=$HOME/.bin/pandocFilters/links-to-pdf.lua --filter mermaid-filter --filter pandoc-crossref --citeproc")
	return res
enddef
