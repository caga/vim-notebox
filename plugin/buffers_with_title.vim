vim9script

def GetYamlTitle(bufnr: number): string
    var filename = bufname(bufnr)
    if empty(filename) || !filereadable(filename)
        return ''
    endif

    try
        var lines = readfile(filename, '', 20)
        var in_frontmatter = false

        for line in lines
            if line == '---'
                in_frontmatter = !in_frontmatter
                continue
            endif

            if in_frontmatter && line =~ '^title:'
                var title = line[6 : ]
                title = trim(title)
                
                if len(title) >= 2
                    if title[0] == '"' && title[-1] == '"'
                        title = title[1 : -2]
                    elseif title[0] == "'" && title[-1] == "'"
                        title = title[1 : -2]
                    endif
                endif
                
                if len(title) > 40
                    title = title[ : 37] .. '...'
                endif
                return title
            endif
        endfor
    catch
        return ''
    endtry

    return ''
enddef

def ShowBuffersInQuickfix()
    var items: list<dict<any>> = []

    for bufnr in range(1, bufnr('$'))
        if !buflisted(bufnr)
            continue
        endif

        var bufname = bufname(bufnr)
        if empty(bufname) || bufname =~ '^$\|^term://'
            continue
        endif

        var title = GetYamlTitle(bufnr)
        var filename = fnamemodify(bufname, ':t')

        if empty(title)
            title = filename
        endif

        items->add({
            filename: bufname,
            lnum: 0,
            col: 0,
            text: title
        })
    endfor

    if empty(items)
        echo 'Buffer listesi boş'
        return
    endif

    setqflist([], 'r')
    setqflist(items, 'a')
    copen
enddef

def QfBufferOpen()
    var filename = ''
    try
        var line_text = getline('.')
        var pipe_pos = stridx(line_text, '|')

        if pipe_pos > 0
            filename = trim(line_text[ : pipe_pos - 1])
        else
            filename = trim(line_text)
        endif

        if empty(filename)
            echo 'Dosya adı bulunamadı'
            return
        endif

        var fullpath = findfile(filename, '.;')
        if !empty(fullpath)
            filename = fullpath
        endif

        if !filereadable(filename)
            echo 'Dosya okunamıyor: ' .. filename
            return
        endif

        wincmd p
        execute 'edit ' .. fnameescape(filename)
        cclose
        
    catch
        echo 'Hata: ' .. v:exception
        echo 'Dosya: ' .. filename
    endtry
enddef

def QfMappings()
    nnoremap <buffer> <CR> :call <SID>QfBufferOpen()<CR>
enddef

augroup QuickfixBufferOpen
    autocmd!
    autocmd FileType qf call QfMappings()
augroup END

command! BuffersQf ShowBuffersInQuickfix()
command! Bq ShowBuffersInQuickfix()
nnoremap <leader>lst :BuffersQf<CR>
