vim9script

# Quickfix penceresini toggle et
def ToggleQuickfix()
    var qf_win = getqflist({winid: 0}).winid
    if qf_win > 0
        cclose
    else
        copen
    endif
enddef

# Komut ve kısayol
command! QfToggle ToggleQuickfix()
nnoremap <leader>q :QfToggle<CR>
