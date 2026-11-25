-- Convert fenced divs with a caption attribute into real Pandoc Figure nodes.
--
-- tbupcharts.py emits charts as:
--
--   ::: {#fig:tbup-aus-p11-0 caption="AVUSTRALYA'nın ..."}
--   ```mermaid
--   ...
--   ```
--   :::
--
-- This makes `--lof` / List of Figures work and gives HTML <figure>/<figcaption>
-- without using Pandoc's table-caption colon notation for figures.

function Div(el)
  if not el.attributes["caption"] then
    return nil
  end
  if not el.identifier:match("^fig:") then
    return nil
  end
  local caption = el.attributes["caption"]
  el.attributes["caption"] = nil
  local id = el.identifier
  el.identifier = ""
  return pandoc.Figure(
    el.content,
    pandoc.Caption({ pandoc.Plain({ pandoc.Str(caption) }) }),
    pandoc.Attr(id, {}, {})
  )
end
