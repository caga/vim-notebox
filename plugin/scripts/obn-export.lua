-- obn-export.lua -- pandoc filter for exportObnHtml.py
--
-- Rewrites links AFTER pandoc has parsed the Markdown.  This is important for
-- pandoc grid tables (notably the CV notes): changing a path before parsing
-- would shift the fixed column widths and break the table.
--
-- Configuration is passed by exportObnHtml.py through the environment:
--   OBN_PAGE_MAP   lines of "<note.md>\t<note.html>"
--   OBN_ASSET_MAP  lines of "<original target>\t<new target>"
--
-- Page links to exported notes become .html; links to excluded notes become
-- plain text.  Local images/documents use the exact mapping computed by the
-- exporter.  Remote URLs and anchors are left alone.

local page_map = {}
local asset_map = {}

local function load_map(name)
  local result = {}
  local raw = os.getenv(name) or ""
  for line in raw:gmatch("[^\n]+") do
    local key, value = line:match("^(.-)\t(.*)$")
    if key and key ~= "" then
      result[key] = value
    end
  end
  return result
end

page_map = load_map("OBN_PAGE_MAP")
asset_map = load_map("OBN_ASSET_MAP")

local function basename(path)
  local normalized = path:gsub("\\", "/")
  return normalized:match("([^/]+)$") or normalized
end

local function split_fragment(target)
  local path, fragment = target:match("^([^#]*)(#.*)$")
  if path then
    return path, fragment
  end
  return target, ""
end

local function is_remote(target)
  return target:match("^%a[%w+.-]*:") ~= nil or target:match("^//") ~= nil
end

local function lookup(map, target)
  local value = map[target]
  if value then
    return value
  end
  -- pandoc percent-encodes spaces in AST targets
  local decoded = target:gsub("%%20", " ")
  return map[decoded]
end

local function rewrite_target(target)
  local path, fragment = split_fragment(target)
  local mapped = lookup(asset_map, path)
  if mapped then
    return mapped .. fragment
  end
  return target
end

function Image(el)
  el.src = rewrite_target(el.src)
  return el
end

function Link(el)
  local path, fragment = split_fragment(el.target)

  if path:match("%.md$") then
    local html = page_map[basename(path)]
    if html then
      el.target = html .. fragment
      return el
    end
    -- Link to a note that is not part of this export: keep only its text.
    return el.content
  end

  el.target = rewrite_target(el.target)
  return el
end

local function rewrite_html_src(text)
  return (text:gsub('(src%s*=%s*")([^"]+)(")',
    function(prefix, src, suffix)
      local mapped = lookup(asset_map, src)
      if mapped then
        return prefix .. mapped .. suffix
      end
      return prefix .. src .. suffix
    end))
end

function RawInline(el)
  if el.format:match("html") then
    el.text = rewrite_html_src(el.text)
  end
  return el
end

function RawBlock(el)
  if el.format:match("html") then
    el.text = rewrite_html_src(el.text)
  end
  return el
end
