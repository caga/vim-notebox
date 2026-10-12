import datetime as dt
import cnlook as lu
import os
import sys

def human_format(num):
    magnitude = 0
    while abs(num) >= 1000:
        magnitude += 1
        num /= 1000.0
    # add more suffixes if you need them
    return '%.3f%s' % (num, ['', 'K', 'M', 'B', 'T', 'P'][magnitude])

def IdGenerator(): 
    time = dt.datetime.now()
    timestamp = time.timestamp()
    idno = int(timestamp)
    return idno

def FileHeader(title:str, author:str, country = ' ', institude = ' '):
    time = dt.datetime.now()
    timestamp = time.timestamp()
    idno = IdGenerator()
    date = time.strftime('%d/%m/%Y')
    #bibfile = "reports/bibfiles/country.replace(' ','')+'.bib'"
    #bibfile = ""
    #title = f"Automatic Trade Report Between {country} and {partner}"
    headerString=f"""---
id: {idno}
date: {date}
author: {author}
title: {title}  
n_type: tmtd
institude: {institude}
country: {country}
citation-style: ieee-with-url.csl
colorlinks: true
keywords:
modify:
--- \n"""
    return headerString

def writeMdReport(file:str,reportString:str):
    with open (f"{file}",'w') as f:
        f.write(reportString)
    f.close()
    result=f"Report File saved as {file}"
    return result

def convertMdAndOpenDoc(mdfile:str,docDirectory):
    docFile=f"{docDirectory}/{mdfile.split('/')[-1].split('.')[0]+'.docx'}"
    print(f"hedef dosyaismi: {docFile}")
    print(f"md dosyaismi: {mdfile}")
    #os.system(f"pandoc -f markdown -t odt {mdpath} -o {docFile}")
    os.system(f"pandoc -f markdown -t docx --lua-filter $HOME/.bin/table-border.lua {mdpath} -o {docFile} --reference-doc=yeni-reference.docx")

    #os.system(f"pandoc -f markdown-tex_math_dollars -t odt -o {docxFile} {filepath} --filter $HOME/.bin/pandoc-crossref --citeproc --reference-doc=referenceOdt.odt")
    #os.system(f"pandoc -f markdown-tex_math_dollars -t docx -o {docxFile} {filepath} --filter $HOME/.bin/pandoc-crossref --citeproc")
    os.system(f"libreoffice {docFile}")
    return 0

def writeOdtReport(mdfile:str,odtfile:str):
    print(f"hedef dosya: {odtfile}")
    print(f"md dosya: {mdfile}")
    os.system(f"pandoc -f markdown -t odt {mdfile} -o {odtfile}")
    return 0
def writeDocReport(mdfile:str,docfile:str):
    print(f"hedef dosya: {docfile}")
    print(f"md dosya: {mdfile}")
    os.system(f"pandoc -f markdown -t docx --lua-filter $HOME/.bin/table-border.lua --reference-doc=yeni-reference.docx {mdfile} -o {docfile}")
    return 0

def openOdtReport(odtfile:str):
    os.system(f"libreoffice {odtfile}")
    return 0

def openDocReport(docfile:str):
    os.system(f"libreoffice {docfile}")
    return 0
#Function to get argument from shell:
def getArgument(country:str = 'TUR'):
    try: 
       rv_country = sys.argv[1] #returned value:rv
    except:
        pass
    else:
       country=rv_country
    return country
