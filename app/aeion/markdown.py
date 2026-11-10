# Spec: knowledge/components/aeion-engine.md
"""Markdown to HTML for the documentation hub, safe by construction: every text run is escaped, raw HTML
is shown as text, and a link is kept only when its target is a relative path, an anchor or http(s).
Supports the subset the project's documents use: headings, paragraphs, lists, quotes, code, tables,
images, links, emphasis and the `<a id>` anchors of the generated cockpit."""
import html
import re

ANCHOR = re.compile(r'^<a id="([a-z0-9][a-z0-9_-]{0,80})"></a>$')
INLINE = re.compile(r"(\\[\\`*_\[\]<>|#!-])|(`+)(.+?)\2|!\[([^\]]*)\]\(([^)\s]+)\)|\[([^\]]+)\]\(([^)\s]+)\)"
                    r"|\*\*(.+?)\*\*|(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])|(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])")


def heading_id(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:80] or "section"


def safe_url(url):
    if url is None:
        return None
    url = url.strip()
    lowered = url.lower()
    if lowered.startswith(("http://", "https://", "#", "mailto:")):
        return url
    if ":" in url.split("/")[0] or lowered.startswith(("//", "\\")):
        return None
    return url


def inline(text, link=None):
    """One line of inline Markdown; link(url) may rewrite a relative target (or drop it with None)."""
    out, position = [], 0
    for match in INLINE.finditer(text):
        out.append(html.escape(text[position:match.start()]))
        position = match.end()
        escaped, ticks, code, alt, src, label, href, strong, em, em2 = match.groups()
        if escaped:
            out.append(html.escape(escaped[1]))
        elif ticks:
            out.append(f"<code>{html.escape(code)}</code>")
        elif src is not None:
            # Check the author's target first, then let the page rewrite it: a scheme never survives.
            target = safe_url(src) and safe_url(link(src) if link else src)
            out.append(f'<img src="{html.escape(target)}" alt="{html.escape(alt)}" loading="lazy">' if target
                       else html.escape(alt))
        elif href is not None:
            target = safe_url(href) and safe_url(link(href) if link else href)
            body = inline(label, link)
            out.append(f'<a href="{html.escape(target)}"' + (' target="_blank" rel="noopener"'
                       if target.startswith("http") else "") + f">{body}</a>" if target else body)
        elif strong is not None:
            out.append(f"<strong>{inline(strong, link)}</strong>")
        else:
            out.append(f"<em>{inline(em if em is not None else em2, link)}</em>")
    out.append(html.escape(text[position:]))
    return "".join(out)


def render(markdown, link=None):
    """(HTML, outline) where outline is [(level, id, text)] for the page's table of contents."""
    lines = markdown.replace("\r\n", "\n").split("\n")
    if lines and lines[0].strip() == "---" and "---" in [l.strip() for l in lines[1:40]]:
        lines = lines[[l.strip() for l in lines[1:40]].index("---") + 2:]
    out, outline, i, seen = [], [], 0, {}
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or (stripped.startswith("<!--") and stripped.endswith("-->")):
            i += 1
            continue
        if stripped.startswith("```"):
            language = re.sub(r"[^a-z0-9+-]", "", stripped[3:].strip().lower())
            block = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1
            out.append(f'<pre><code class="language-{language or "text"}">{html.escape(chr(10).join(block))}</code></pre>')
            continue
        heading = re.match(r"(#{1,6})\s+(.*?)\s*#*$", stripped)
        if heading:
            level, text = len(heading.group(1)), heading.group(2)
            base = heading_id(re.sub(r"[`*_\\]", "", text))
            seen[base] = seen.get(base, 0) + 1
            anchor = base if seen[base] == 1 else f"{base}-{seen[base]}"
            outline.append((level, anchor, re.sub(r"[`*_\\]", "", text)))
            out.append(f'<h{level} id="{anchor}">{inline(text, link)}</h{level}>')
            i += 1
            continue
        if ANCHOR.match(stripped):
            out.append(f'<a id="{ANCHOR.match(stripped).group(1)}"></a>')
            i += 1
            continue
        if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", stripped):
            out.append("<hr>")
            i += 1
            continue
        if stripped.startswith("|") and i + 1 < len(lines) and re.fullmatch(r"\|?\s*:?-{2,}.*", lines[i + 1].strip()):
            i = _table(lines, i, out, link)
            continue
        if stripped.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].lstrip())
                i += 1
            inner, _ = render("\n".join(quote), link)
            out.append(f"<blockquote>{inner}</blockquote>")
            continue
        if re.match(r"\s*([-*+]|\d+[.)])\s+", line):
            i = _list(lines, i, out, link)
            continue
        paragraph = []
        while i < len(lines) and lines[i].strip() and not re.match(r"\s*(#{1,6}\s|```|>|\||([-*+]|\d+[.)])\s)", lines[i]):
            paragraph.append(lines[i].strip())
            i += 1
        if not paragraph:
            paragraph, i = [stripped], i + 1
        out.append("<p>" + "<br>".join(inline(p.rstrip(), link) for p in _join_breaks(paragraph)) + "</p>")
    return "\n".join(out), outline


def _join_breaks(lines):
    # A line ending in two spaces or a backslash is a hard break; others join with a space.
    joined, current = [], ""
    for line in lines:
        current = f"{current} {line}".strip() if current else line
        if line.endswith("\\"):
            joined.append(current[:-1])
            current = ""
    return joined + ([current] if current else [])


def _cells(row):
    row = row.strip().strip("|")
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", row)]


def _table(lines, i, out, link):
    head = _cells(lines[i])
    i += 2
    rows = []
    while i < len(lines) and lines[i].strip().startswith("|"):
        rows.append(_cells(lines[i]))
        i += 1
    body = "".join("<tr>" + "".join(f"<td>{_cell(c, link)}</td>" for c in row) + "</tr>" for row in rows)
    out.append('<div class="table"><table><thead><tr>' + "".join(f"<th>{inline(c, link)}</th>" for c in head)
               + f"</tr></thead><tbody>{body}</tbody></table></div>")
    return i


def _cell(text, link):
    anchor = re.match(r'<a id="([a-z0-9][a-z0-9_-]{0,80})"></a>(.*)', text)
    if anchor:
        return f'<a id="{anchor.group(1)}"></a>' + inline(anchor.group(2), link)
    return inline(text, link)


def _list(lines, i, out, link):
    ordered = bool(re.match(r"\s*\d+[.)]\s", lines[i]))
    base = len(lines[i]) - len(lines[i].lstrip())
    items = []
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            if i + 1 < len(lines) and re.match(r"\s*([-*+]|\d+[.)])\s+", lines[i + 1]) and \
                    len(lines[i + 1]) - len(lines[i + 1].lstrip()) >= base:
                i += 1
                continue
            break
        indent = len(line) - len(line.lstrip())
        marker = re.match(r"\s*([-*+]|\d+[.)])\s+(.*)", line)
        if marker and indent == base:
            items.append([marker.group(2)])
        elif indent > base and items:
            items[-1].append(line[base + 2:] if len(line) > base + 2 else line.strip())
        else:
            break
        i += 1
    rendered = []
    for item in items:
        first, rest = item[0], item[1:]
        check = re.match(r"\[( |x|X)\]\s+(.*)", first)
        head = (f'<input type="checkbox" disabled{" checked" if check.group(1) != " " else ""}> {inline(check.group(2), link)}'
                if check else inline(first, link))
        nested = render("\n".join(rest), link)[0] if rest else ""
        rendered.append(f"<li>{head}{nested}</li>")
    tag = "ol" if ordered else "ul"
    out.append(f"<{tag}>{''.join(rendered)}</{tag}>")
    return i
