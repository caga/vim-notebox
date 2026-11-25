" markdown_combiner.vim
" Bu script, bir markdown taslak dosyasındaki başlıkların altına
" '- [açıklama](dosya.md)' formatındaki markdown linklerini takip ederek
" dosyaları birleştirir.

" =============================================================================
" 1. YARDIMCI FONKSİYONLAR
" =============================================================================

if !exists("g:citation_style")
	 g:citation_style = $"{plugindir}/plugin/ieee-with-url.csl"
endif

function! s:GenerateId()
    return localtime()
endfunction

function! s:GetYamlValue(source_file, field)
    " YAML frontmatter'dan belirtilen alanın değerini al
    if !filereadable(a:source_file)
        return ''
    endif
    
    let lines = readfile(a:source_file)
    let i = 0
    
    if len(lines) > 0 && lines[0] =~ '^---$'
        let i = 1
        while i < len(lines) && lines[i] !~ '^---$'
            if lines[i] =~ '^' . a:field . ':'
                let value = substitute(lines[i], '^' . a:field . ':\s*', '', '')
                let value = substitute(value, '^"', '', '')
                let value = substitute(value, '"$', '', '')
                let value = substitute(value, "^'", '', '')
                let value = substitute(value, "'$", '', '')
                let value = substitute(value, '^\s*', '', '')
                let value = substitute(value, '\s*$', '', '')
                return value
            endif
            let i += 1
        endwhile
    endif
    
    return ''
endfunction

function! s:GetTitleFromYaml(source_file)
    let title = s:GetYamlValue(a:source_file, 'title')
    if title != ''
        return title
    endif
    
    " YAML'da title yoksa ilk başlığı bul
    if !filereadable(a:source_file)
        return fnamemodify(a:source_file, ':t:r')
    endif
    
    let lines = readfile(a:source_file)
    let i = 0
    
    " YAML frontmatter'ı atla
    if len(lines) > 0 && lines[0] =~ '^---$'
        let i = 1
        while i < len(lines) && lines[i] !~ '^---$'
            let i += 1
        endwhile
        let i += 1
    endif
    
    while i < len(lines)
        if lines[i] =~ '^#\+ '
            let title = substitute(lines[i], '^#\+ ', '', '')
            let title = substitute(title, '^\s*', '', '')
            let title = substitute(title, '\s*$', '', '')
            return title
        endif
        let i += 1
    endwhile
    
    return fnamemodify(a:source_file, ':t:r')
endfunction

function! s:GetNType(source_file)
    " Ana dosyanın n_type değerini al
    let n_type = s:GetYamlValue(a:source_file, 'n_type')
    return n_type
endfunction

function! s:IsValidNType(n_type)
    " n_type geçerli mi kontrol et
    let valid_types = ['yöt', 'taslak', 'plan','hbn']
    for type in valid_types
        if a:n_type ==? type
            return 1
        endif
    endfor
    return 0
endfunction

" =============================================================================
" 2. TABLO TESPİTİ
" =============================================================================

function! s:IsTableLine(line)
    let line = a:line
    if line =~ '^\s*$'
        return 0
    endif
    
    " Grid table separator (+---+---)
    if line =~ '^[ \t]*+'
        return 1
    endif
    
    " Pipe table (| başlık |)
    if line =~ '|'
        return 1
    endif
    
    return 0
endfunction

" =============================================================================
" 3. BIBTEX TOPLAMA VE TEMİZLEME
" =============================================================================

function! s:GetCorrespondingBibFile(file)
    " Dosyaya karşılık gelen .bib dosyasını bul
    let file_base = fnamemodify(a:file, ':t:r')
    
    " bibfiles/ klasöründeki .bib dosyası
    let bib_file = 'bibfiles/' . file_base . '.bib'
    if filereadable(bib_file)
        return bib_file
    endif
    
    " Aynı dizindeki .bib dosyası (alternatif)
    let file_dir = fnamemodify(a:file, ':h')
    let bib_file2 = file_dir . '/' . file_base . '.bib'
    if filereadable(bib_file2)
        return bib_file2
    endif
    
    return ''
endfunction

function! s:ExtractBibEntries(content)
    " Dosya içeriğinden BibTeX kayıtlarını çıkar (@ ile başlayan)
    let entries = []
    let i = 0
    let current_entry = []
    let brace_count = 0
    
    while i < len(a:content)
        let line = a:content[i]
        " Boş satırları atla
        if line =~ '^\s*$'
            let i += 1
            continue
        endif
        
        let trimmed = substitute(line, '^\s*', '', '')
        
        " @ ile başlayan yeni bir kayıt
        if trimmed =~ '^@'
            " Önceki kayıt varsa ekle
            if !empty(current_entry)
                let entry_text = join(current_entry, "\n")
                let entry_text = substitute(entry_text, '\n\s*\n', "\n", 'g')
                let entry_text = substitute(entry_text, '^\s*', '', '')
                let entry_text = substitute(entry_text, '\s*$', '', '')
                if entry_text != ''
                    call add(entries, entry_text)
                endif
                let current_entry = []
            endif
            let current_entry = [line]
            let brace_count = 0
            let brace_count += count(line, '{')
            let brace_count -= count(line, '}')
            let i += 1
            
            if brace_count == 0 && line =~ '}\s*$'
                let entry_text = join(current_entry, "\n")
                let entry_text = substitute(entry_text, '\n\s*\n', "\n", 'g')
                let entry_text = substitute(entry_text, '^\s*', '', '')
                let entry_text = substitute(entry_text, '\s*$', '', '')
                if entry_text != ''
                    call add(entries, entry_text)
                endif
                let current_entry = []
            endif
            continue
        endif
        
        " Kayıt içindeyiz
        if !empty(current_entry)
            call add(current_entry, line)
            let brace_count += count(line, '{')
            let brace_count -= count(line, '}')
            
            if brace_count == 0
                let entry_text = join(current_entry, "\n")
                let entry_text = substitute(entry_text, '\n\s*\n', "\n", 'g')
                let entry_text = substitute(entry_text, '^\s*', '', '')
                let entry_text = substitute(entry_text, '\s*$', '', '')
                if entry_text != ''
                    call add(entries, entry_text)
                endif
                let current_entry = []
            endif
        endif
        let i += 1
    endwhile
    
    if !empty(current_entry)
        let entry_text = join(current_entry, "\n")
        let entry_text = substitute(entry_text, '\n\s*\n', "\n", 'g')
        let entry_text = substitute(entry_text, '^\s*', '', '')
        let entry_text = substitute(entry_text, '\s*$', '', '')
        if entry_text != ''
            call add(entries, entry_text)
        endif
    endif
    
    return entries
endfunction

function! s:CleanBibEntries(entries)
    let unique = {}
    let result = []
    
    for entry in a:entries
        let clean_entry = substitute(entry, '[^[:print:]\t\n\r]', '', 'g')
        let clean_entry = substitute(clean_entry, '\n\s*\n', "\n", 'g')
        let clean_entry = substitute(clean_entry, '^\s*', '', '')
        let clean_entry = substitute(clean_entry, '\s*$', '', '')
        
        if clean_entry == ''
            continue
        endif
        
        let key_match = matchlist(clean_entry, '@[a-zA-Z]\+{\s*\([^,]*\)')
        if !empty(key_match)
            let key = key_match[1]
            let key = substitute(key, '^\s*', '', '')
            let key = substitute(key, '\s*$', '', '')
            if key != '' && !has_key(unique, key)
                let unique[key] = clean_entry
                call add(result, clean_entry)
            endif
        else
            call add(result, clean_entry)
        endif
    endfor
    
    return result
endfunction

function! s:CollectBibEntriesFromFiles(file_list)
    let all_entries = []
    
    for file in a:file_list
        let bib_file = s:GetCorrespondingBibFile(file)
        if bib_file != '' && filereadable(bib_file)
            let content = readfile(bib_file)
            let entries = s:ExtractBibEntries(content)
            if !empty(entries)
                call extend(all_entries, entries)
            endif
        endif
    endfor
    
    let unique_entries = s:CleanBibEntries(all_entries)
    return unique_entries
endfunction

function! s:CleanTextLine(line, keep_refs)
    " Normal metin satırlarını temizle
    let line = a:line
    
    " @ ile başlayan BibTeX satırlarını kontrol et
    if line =~ '^\s*@'
        if a:keep_refs
            return line
        else
            return ''
        endif
    endif
    
    if a:keep_refs
        let cleaned = line
        let cleaned = substitute(cleaned, '^\s*', '', '')
        let cleaned = substitute(cleaned, '\s*$', '', '')
        return cleaned
    else
        let cleaned = substitute(line, '@[a-zA-Z0-9._\-]\+', '', 'g')
        let cleaned = substitute(cleaned, '  \+', ' ', 'g')
        "let cleaned = substitute(cleaned, '\. ', ' ', 'g')
        "let cleaned = substitute(cleaned, ' \.', ' ', 'g')
        let cleaned = substitute(cleaned, '^\s*', '', '')
        let cleaned = substitute(cleaned, '\s*$', '', '')
        return cleaned
    endif
endfunction

function! s:StripBackReferences(content)
    " #BackReferences: etiketinden sonra gelen tüm içeriği temizle
    let result = []
    let i = 0
    let found_backrefs = 0
    
    while i < len(a:content)
        let line = a:content[i]
        
        " #BackReferences: etiketini bul
        if line =~ '^\s*#BackReferences:'
            " Etiketi bulduk, bu satırdan sonrasını tamamen atla
            let found_backrefs = 1
            break
        endif
        
        " Etiket bulunana kadar satırları ekle
        call add(result, line)
        let i += 1
    endwhile
    
    return result
endfunction

function! s:CleanContent(content, keep_refs)
    let content = a:content
    let start_idx = 0
    
    if len(content) > 0 && content[0] =~ '^---$'
        let start_idx = 1
        while start_idx < len(content) && content[start_idx] !~ '^---$'
            let start_idx += 1
        endwhile
        let start_idx += 1
    endif
    
    let i = start_idx
    while i < len(content) && content[i] =~ '^\s*$'
        let i += 1
    endwhile
    
    if i < len(content) && content[i] =~ '^#\+ '
        let i += 1
        while i < len(content) && content[i] =~ '^\s*$'
            let i += 1
        endwhile
    endif
    
    " #BackReferences: ve sonrasını temizle
    let content_without_backrefs = s:StripBackReferences(content[i:])
    
    let result = []
    for line in content_without_backrefs
        " Tablo satırlarını olduğu gibi ekle
        if s:IsTableLine(line)
            call add(result, line)
        else
            let cleaned = s:CleanTextLine(line, a:keep_refs)
            if cleaned != '' || line =~ '^\s*$'
                call add(result, cleaned)
            endif
        endif
    endfor
    
    return result
endfunction

" =============================================================================
" 4. YAML HEADER OLUŞTURMA
" =============================================================================

function! s:CreateYamlHeader(source_file, output_file, file_count, file_list, id, keywords, bibliography)
    let date_string = strftime('%d/%m/%y', localtime())
    let source_name = fnamemodify(a:source_file, ':t')
    let output_name = fnamemodify(a:output_file, ':t')
    let main_title = s:GetTitleFromYaml(a:source_file)
    "let combined_title = main_title . '_combined'
    let combined_title = main_title 
    
    let header = []
    call add(header, '---')
    call add(header, 'id: ' . a:id)
    let author_name = exists('g:notes_author') && g:notes_author !~ '^\s*$'
                \ ? g:notes_author : 'Çağatay Çakır'
    call add(header, 'author: ' . author_name)
    call add(header, 'title: "' . combined_title . '"')
    call add(header, 'date: ' . date_string)
    call add(header, 'n_type: output')
    
    " bibliography
    if a:bibliography != ''
        call add(header, 'bibliography: ' . a:bibliography)
    else
        call add(header, 'bibliography: []')
    endif
    
    " citation-style
    call add(header, $"citation-style: {g:citation_style}")
    
    if a:keywords != ''
        call add(header, 'keywords: ' . a:keywords)
    else
        call add(header, 'keywords: []')
    endif
    
    call add(header, 'toc: true')
    call add(header, 'toc-depth: "1"')
    call add(header, 'toc-title: "İçindekiler"')
    call add(header, 'tableTitle: "Tablolar"')
    call add(header, 'reference-section-title: "Kaynakça"')
    call add(header, 'figureTitle: "Şekil"')
    call add(header, 'numbersections: true')
    call add(header, 'source_file: "' . source_name . '"')
    call add(header, 'output_file: "' . output_name . '"')
    call add(header, 'file_count: ' . a:file_count)
    
    if !empty(a:file_list)
        call add(header, 'combined_files:')
        for file in a:file_list
            call add(header, '  - "' . file . '"')
        endfor
    else
        call add(header, 'combined_files: []')
    endif
    
    call add(header, '---')
    call add(header, '')
    
    return header
endfunction

" =============================================================================
" 5. ANA BİRLEŞTİRME FONKSİYONU
" =============================================================================

function! MarkdownCombine(source_file, keep_refs)
    let lines = readfile(a:source_file)
    let result = []
    let total_files = 0
    let combined_files_list = []
    let id = s:GenerateId()
    let keywords = s:GetYamlValue(a:source_file, 'keywords')
    
    " YAML frontmatter'ı atla
    let start_idx = 0
    if len(lines) > 0 && lines[0] =~ '^---$'
        let start_idx = 1
        while start_idx < len(lines) && lines[start_idx] !~ '^---$'
            let start_idx += 1
        endwhile
        let start_idx += 1
    endif
    
    let source_content = lines[start_idx:]
    
    " Dosya listesini topla
    let i = 0
    while i < len(source_content)
        if source_content[i] =~ '^#\+ '
            let j = i + 1
            while j < len(source_content) && (source_content[j] =~ '^- ' || source_content[j] =~ '^\s*- ')
                let file_line = source_content[j]
                let file_match = matchlist(file_line, '(\zs[^)]\+\ze)')
                if !empty(file_match)
                    let file_name = file_match[0]
                    let file_name = substitute(file_name, '\s*$', '', '')
                    if filereadable(file_name)
                        let total_files += 1
                        call add(combined_files_list, file_name)
                    endif
                else
                    let file_name = substitute(file_line, '^- ', '', '')
                    let file_name = substitute(file_name, '\s*$', '', '')
                    if file_name != '' && filereadable(file_name)
                        let total_files += 1
                        call add(combined_files_list, file_name)
                    endif
                endif
                let j += 1
            endwhile
            let i = j - 1
        endif
        let i += 1
    endwhile
    
    " BibTeX kayıtlarını topla (e seçeneği için)
    let bib_entries = []
    let bibliography = ''
    if a:keep_refs
        let bib_entries = s:CollectBibEntriesFromFiles(combined_files_list)
        if !empty(bib_entries)
            let bib_dir = 'bibfiles'
            if !isdirectory(bib_dir)
                call mkdir(bib_dir)
            endif
            
            let bib_filename = bib_dir . '/' . id . '.bib'
            
            let bib_content = []
            for entry in bib_entries
                let lines = split(entry, "\n")
                if !empty(lines)
                    call add(bib_content, lines[0])
                    for idx in range(1, len(lines) - 1)
                        let line = lines[idx]
                        if line =~ '^\s*$'
                            continue
                        endif
                        let indent_line = '  ' . substitute(line, '^\s*', '', '')
                        call add(bib_content, indent_line)
                    endfor
                    if lines[-1] !~ '}\s*$'
                        call add(bib_content, '}')
                    endif
                    call add(bib_content, '')
                endif
            endfor
            
            call writefile(bib_content, bib_filename, 'b')
            let bibliography = bib_filename
            echo "BibTeX dosyası oluşturuldu: " . bib_filename
            echo "Toplam " . len(bib_entries) . " benzersiz kaynak bulundu."
        else
            echo "Uyarı: bibfiles/ klasöründe .bib dosyalarında kayıt bulunamadı!"
            let bib_dir = 'bibfiles'
            if !isdirectory(bib_dir)
                call mkdir(bib_dir)
            endif
            let bib_filename = bib_dir . '/' . id . '.bib'
            call writefile(['% BibTeX dosyası - kayıt bulunamadı'], bib_filename, 'b')
            let bibliography = bib_filename
        endif
    endif
    
    " Çıktı dosyası adı - ID.md
    let output_filename = id . '.md'
    
    " YAML header'ı oluştur
    let yaml_header = s:CreateYamlHeader(a:source_file, output_filename, total_files, combined_files_list, id, keywords, bibliography)
    call extend(result, yaml_header)
    
    " Ana içeriği birleştir
    let i = 0
    while i < len(source_content)
        let current_line = source_content[i]
        
        " #BackReferences: satırlarını atla (ana dosyadan)
        if current_line !~ '^\s*#BackReferences:'
            " Tablo satırlarını olduğu gibi ekle
            if s:IsTableLine(current_line)
                call add(result, current_line)
            else
                let cleaned = s:CleanTextLine(current_line, a:keep_refs)
                if cleaned != '' || current_line =~ '^\s*$'
                    call add(result, cleaned)
                endif
            endif
        endif
        
        " Dosya listesini işle
        if current_line =~ '^#\+ '
            let j = i + 1
            let found_files = []
            let found_titles = []
            
            while j < len(source_content) && (source_content[j] =~ '^- ' || source_content[j] =~ '^\s*- ')
                let file_line = source_content[j]
                let file_match = matchlist(file_line, '(\zs[^)]\+\ze)')
                if !empty(file_match)
                    let file_name = file_match[0]
                    let file_name = substitute(file_name, '\s*$', '', '')
                    let title_match = matchlist(file_line, '-\s*\[\zs[^\]]\+\ze\]')
                    if !empty(title_match)
                        let title = title_match[0]
                    else
                        let title = fnamemodify(file_name, ':t:r')
                    endif
                    call add(found_files, file_name)
                    call add(found_titles, title)
                else
                    let file_name = substitute(file_line, '^- ', '', '')
                    let file_name = substitute(file_name, '\s*$', '', '')
                    if file_name != ''
                        call add(found_files, file_name)
                        call add(found_titles, fnamemodify(file_name, ':t:r'))
                    endif
                endif
                let j += 1
            endwhile
            
            if !empty(found_files)
                call add(result, '')
                for idx in range(len(found_files))
                    let file_name = found_files[idx]
                    if filereadable(file_name)
                        let file_content = readfile(file_name)
                        let clean_content = s:CleanContent(file_content, a:keep_refs)
                        if !empty(clean_content)
                            call extend(result, clean_content)
                            call add(result, '')
                        endif
                    else
                        call add(result, '')
                        call add(result, '> **HATA:** `' . file_name . '` dosyası bulunamadı!')
                        call add(result, '')
                    endif
                endfor
                let i = j - 1
            endif
        endif
        
        let i += 1
    endwhile
    
    " Çıktıyı yaz
    call writefile(result, output_filename)
    
    " Mesajlar
    echo "Birleştirme tamamlandı! Çıktı: " . output_filename
    echo "ID: " . id
    echo "Toplam " . total_files . " dosya birleştirildi."
    echo "Başlık: " . s:GetTitleFromYaml(a:source_file) . "_combined"
    if keywords != ''
        echo "Keywords: " . keywords
    endif
    if a:keep_refs && !empty(bib_entries)
        echo "Kaynaklar korundu ve " . len(bib_entries) . " benzersiz kayıt " . bib_filename . " dosyasına yazıldı."
    elseif a:keep_refs
        echo "Kaynaklar korundu ancak bibfiles/ klasöründe .bib dosyalarında kayıt bulunamadı."
    else
        echo "Kaynaklar temizlendi."
    endif
    
    " Yeni tab'da aç
    execute "tabnew " . output_filename
endfunction

" =============================================================================
" 6. KULLANICI ARAYÜZÜ - İNTERAKTİF SEÇENEK
" =============================================================================

function! s:MarkdownCombineInteractive(...)
    if a:0 == 0
        echo "Kullanım: :MarkdownCombine kaynak_dosya"
        echo "Veya: call MarkdownCombine('kaynak.md')"
        echo "Kısayol: <leader>bt"
        return
    endif
    
    let source = a:1
    if !filereadable(source)
        echo "Hata: " . source . " dosyası okunamıyor!"
        return
    endif
    
    " n_type kontrolü
    let n_type = s:GetNType(source)
    if !s:IsValidNType(n_type)
        echo "Yanlış n_type: '" . n_type . "', yöt/taslak veya plan olmalı!"
        echo "İşlem iptal edildi."
        return
    endif
    
    " Kullanıcıya seçenek sun
    echo "Kaynaklar (BibTeX) korunsun mu? (e/h)"
    let choice = input("e (koru) / h (temizle): ")
    
    if choice ==? 'e'
        call MarkdownCombine(source, 1)
    elseif choice ==? 'h'
        call MarkdownCombine(source, 0)
    else
        echo "Geçersiz seçenek! Varsayılan olarak 'h' (temizle) seçildi."
        call MarkdownCombine(source, 0)
    endif
endfunction

" =============================================================================
" 7. KULLANICI KOMUTLARI VE KISAYOLLAR
" =============================================================================

command! -nargs=* MarkdownCombine call s:MarkdownCombineInteractive(<f-args>)

" Kısayol: <leader>bt - interaktif seçenek ile
nnoremap <leader>bt :call <SID>MarkdownCombineInteractive(expand('%:p'))<CR>

" Hızlı kısayol: kaynakları koru (e)
nnoremap <leader>bte :call MarkdownCombine(expand('%:p'), 1)<CR>

" Hızlı kısayol: kaynakları temizle (h)
nnoremap <leader>bth :call MarkdownCombine(expand('%:p'), 0)<CR>

" Yardım
command! MarkdownCombineHelp call s:MarkdownCombineHelp()

function! s:MarkdownCombineHelp()
    echo "===== Markdown Combine Script ====="
    echo ""
    echo "Kullanım:"
    echo "  :MarkdownCombine kaynak.md"
    echo "  <leader>bt   - Mevcut dosya, interaktif seçenek"
    echo "  <leader>bte  - Mevcut dosya, kaynakları koru (e)"
    echo "  <leader>bth  - Mevcut dosya, kaynakları temizle (h)"
    echo ""
    echo "Geçerli n_type değerleri:"
    echo "  - yöt"
    echo "  - taslak"
    echo "  - plan"
    echo ""
    echo "Seçenekler:"
    echo "  e - Kaynakları koru, .bib dosyası oluştur"
    echo "  h - Kaynakları temizle (varsayılan)"
    echo ""
    echo "Temizleme Özellikleri:"
    echo "  - #BackReferences: etiketi ve sonrasındaki TÜM içerik TEMİZLENİR"
    echo "  - Tablo satırları KESİNLİKLE DEĞİŞTİRİLMEZ (olduğu gibi eklenir)"
    echo "  - Sadece normal metin satırlarındaki @referanslar temizlenir"
    echo ""
    echo "BibTeX Toplama:"
    echo "  - Birleştirilen her dosya için bibfiles/klasöründe aynı isimli .bib dosyası taranır"
    echo "  - Örnek: bd1.md için bibfiles/bd1.bib dosyası kontrol edilir"
    echo "  - Mükerrer kayıtlar otomatik temizlenir"
    echo "  - Pretty format ile kaydedilir (indentli)"
    echo "  - Çıktı: bibfiles/ID.bib (ID ile aynı)"
    echo ""
    echo "YAML Header Alanları:"
    echo "  - author: g:notes_author (varsayılan: Çağatay Çakır)"
    echo "  - bibliography: bibfiles/ID.bib (e seçeneğinde)"
    echo "  - citation-style: style/ieee-with-url.csl"
    echo ""
    echo "Özellikler:"
    echo "  - Çıktı: ID.md (ID = timestamp)"
    echo "  - BibTeX çıktısı: bibfiles/ID.bib (ID ile aynı)"
    echo "  - e seçeneği: @referanslar korunur, bibfiles/ID.bib oluşturulur"
    echo "  - h seçeneği: @referanslar temizlenir"
    echo "  - Grid/Pipe tabloları KESİNLİKLE KORUNUR"
    echo "  - Boşluklar ve satır yapısı korunur"
    echo "  - Çıktı yeni tab'da açılır"
endfunction
