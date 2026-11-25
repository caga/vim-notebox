vim9script

# Açık buffer'ları YAML başlıklarıyla quickfix penceresinde listele.
# Quickfix içinde:
#   dd / x  -> satırı listeden çıkar (buffer açık kalır)
#   D       -> satırı çıkar ve buffer'ı sil (bwipeout)
#   h       -> buffer'ı bu oturum için gizle
#   u       -> son çıkarma/gizlemeyi geri al
#   R       -> gizlenenleri temizle ve listeyi yenile
#   g?      -> kısayol yardımı

const QF_TITLE = 'Buffers'

# Yalnızca bu Vim oturumu için gizlenen buffer'lar: mutlak yol -> true
var hidden: dict<bool> = {}

# Geri alma yığını: {idx, item, kind, path?}
var undo_stack: list<dict<any>> = []

def InLoclistWindow(): bool
    var info = getwininfo(win_getid())
    return !empty(info) && get(info[0], 'loclist', 0) == 1
enddef

def IsOurQf(): bool
    return !InLoclistWindow() && getqflist({'title': 0}).title == QF_TITLE
enddef

def SetQf(items: list<dict<any>>, idx: number = 1)
    setqflist([], 'r', {
        items: items,
        title: QF_TITLE,
        idx: empty(items) ? 0 : min([idx, len(items)]),
    })
enddef

def GetYamlTitle(b: number): string
    var filename = bufname(b)
    if empty(filename)
        return ''
    endif

    var loaded = bufloaded(b)
    if !loaded && !filereadable(filename)
        return ''
    endif

    try
        var lines: list<string> = loaded
            ? getbufline(b, 1, 20)
            : readfile(filename, '', 20)
        if empty(lines)
            return ''
        endif

        # Frontmatter ilk boş olmayan satırda '---' ile başlamalı.
        var start = -1
        for i in range(len(lines))
            if trim(lines[i]) != ''
                start = i
                break
            endif
        endfor
        if start < 0 || substitute(lines[start], '\r$', '', '') != '---'
            return ''
        endif

        for raw in lines[start + 1 :]
            var line = substitute(raw, '\r$', '', '')
            if line == '---'
                break
            endif

            if line =~ '^\s*title:'
                var title = trim(matchstr(line, '^\s*title:\s*\zs.*'))

                if len(title) >= 2
                    var q = title[0]
                    if (q == '"' || q == "'") && title[-1] == q
                        title = title[1 : -2]
                    endif
                endif

                if strchars(title) > 40
                    title = strcharpart(title, 0, 37) .. '...'
                endif
                return title
            endif
        endfor
    catch
        return ''
    endtry

    return ''
enddef

def ShowBuffersInQuickfix(show_hidden: bool = false)
    var items: list<dict<any>> = []

    for b in range(1, bufnr('$'))
        if !buflisted(b)
            continue
        endif

        var name = bufname(b)
        if empty(name) || name =~ '^term://'
            continue
        endif

        var path = fnamemodify(name, ':p')
        if !show_hidden && has_key(hidden, path)
            continue
        endif

        var title = GetYamlTitle(b)
        if empty(title)
            title = fnamemodify(name, ':t')
        endif

        items->add({bufnr: b, lnum: 0, col: 0, text: title})
    endfor

    undo_stack = []
    SetQf(items, 1)
    copen

    if empty(items)
        echo 'Buffer listesi boş'
    endif
enddef

def QfEnter()
    if InLoclistWindow()
        if !empty(getloclist(0))
            execute 'll ' .. line('.')
        endif
        return
    endif

    if !IsOurQf()
        # Başka bir quickfix listesi (grep, LSP, ...): yerleşik davranış.
        if !empty(getqflist())
            execute 'cc ' .. line('.')
        endif
        return
    endif

    if empty(getqflist())
        return
    endif

    try
        execute 'cc ' .. line('.')
        cclose
    catch
        echo 'Hata: ' .. v:exception
    endtry
enddef

def QfRemoveRange(l1: number, l2: number, record_undo: bool = true)
    if !IsOurQf()
        return
    endif

    var items = getqflist()
    var n = len(items)
    var first = min([l1, l2])
    var last = max([l1, l2])
    if n == 0 || first < 1 || first > n
        return
    endif

    var lo = first - 1
    var hi = min([last, n]) - 1

    for i in range(hi, lo, -1)
        if record_undo
            undo_stack->add({idx: i, item: items[i], kind: 'remove'})
        endif
        remove(items, i)
    endfor

    SetQf(items, empty(items) ? 0 : min([lo + 1, len(items)]))
enddef

def QfUndo()
    if !IsOurQf() || empty(undo_stack)
        return
    endif

    var entry = undo_stack[-1]
    undo_stack->remove(-1)

    var items = getqflist()
    var idx = min([entry.idx, len(items)])
    insert(items, entry.item, idx)

    if get(entry, 'kind', '') == 'hide'
        var path = get(entry, 'path', '')
        if !empty(path) && has_key(hidden, path)
            remove(hidden, path)
        endif
    endif

    SetQf(items, idx + 1)
enddef

def QfHide(l: number)
    if !IsOurQf()
        return
    endif

    var items = getqflist()
    if l < 1 || l > len(items)
        return
    endif

    var item = items[l - 1]
    if item.bufnr <= 0
        return
    endif

    var path = fnamemodify(bufname(item.bufnr), ':p')
    if empty(path)
        return
    endif

    hidden[path] = true
    undo_stack->add({idx: l - 1, item: item, kind: 'hide', path: path})
    QfRemoveRange(l, l, false)
enddef

def QfWipe(l: number)
    if !IsOurQf()
        return
    endif

    var items = getqflist()
    if l < 1 || l > len(items)
        return
    endif

    var item = items[l - 1]
    var b = item.bufnr

    if b > 0 && bufexists(b)
        execute 'confirm bwipeout ' .. b
    endif

    if b <= 0 || !bufexists(b)
        # Silinen buffer'ın quickfix satırı burada bufnr=0 olarak kalır.
        var after = getqflist()
        if l <= len(after) && after[l - 1].bufnr == 0
            if after[l - 1].text == item.text
                QfRemoveRange(l, l, false)
            endif
        endif
    endif
enddef

def ResetHidden()
    hidden = {}
    undo_stack = []
    ShowBuffersInQuickfix()
enddef

def QfReset()
    if !IsOurQf()
        return
    endif
    ResetHidden()
enddef

def QfHelp()
    if !IsOurQf()
        return
    endif
    echo '<CR> aç | dd/x listeden çıkar | D buffer sil | h gizle | u geri al | R sıfırla'
enddef

def QfMappings()
    nnoremap <buffer> <silent> <CR> <ScriptCmd>QfEnter()<CR>
    nnoremap <buffer> <silent> dd <ScriptCmd>QfRemoveRange(line('.'), line('.') + v:count1 - 1)<CR>
    nnoremap <buffer> <silent> x  <ScriptCmd>QfRemoveRange(line('.'), line('.'))<CR>
    xnoremap <buffer> <silent> d  :<C-U>call <SID>QfRemoveRange(line("'<"), line("'>"))<CR>
    xnoremap <buffer> <silent> x  :<C-U>call <SID>QfRemoveRange(line("'<"), line("'>"))<CR>
    nnoremap <buffer> <silent> D  <ScriptCmd>QfWipe(line('.'))<CR>
    nnoremap <buffer> <silent> h  <ScriptCmd>QfHide(line('.'))<CR>
    nnoremap <buffer> <silent> u  <ScriptCmd>QfUndo()<CR>
    nnoremap <buffer> <silent> R  <ScriptCmd>QfReset()<CR>
    nnoremap <buffer> <silent> g? <ScriptCmd>QfHelp()<CR>
enddef

augroup QuickfixBufferOpen
    autocmd!
    autocmd FileType qf QfMappings()
augroup END

command! -bar BuffersQf ShowBuffersInQuickfix()
command! -bar Bq ShowBuffersInQuickfix()
command! -bar BuffersQfAll ShowBuffersInQuickfix(true)
command! -bar BuffersQfReset ResetHidden()
nnoremap <silent> <leader>lst :BuffersQf<CR>
