# Spec: knowledge/components/docs-hub.md
"""Section 3, the documentation hub: every document of aeion-core, its products and saved features in one
navigable tree, each page with the diagrams that concern it, and an assistant that answers from the
documents and the AxiomSpec graph with citations it cannot invent (each one is checked to exist)."""
import json
import math
import re
import threading
import unicodedata
from pathlib import Path

import graph as axgraph
import query as axquery
from . import markdown
from .agents import streaming

WORD = re.compile(r"[a-z0-9]+(?:-[0-9]{3,6})?")
STOP = set("the a an and or of to in on for is are be by with as at it this that from not no can its into than then "
           "le la les de des du un une et ou en est pour par sur dans que qui".split())
MAX_PAGE = 400_000


class Corpus:
    """Pages from the configured roots, chunked by heading, with a BM25 index; rebuilt when files change."""

    def __init__(self, settings, store):
        self.settings, self.store = settings, store
        self.lock = threading.Lock()
        self.signature = None
        self.pages, self.chunks, self.index, self.lengths = {}, [], {}, []

    def roots(self):
        """(key, title, folder, include) for each source of pages; product folders are discovered."""
        root, data = self.settings.root, self.settings.data
        roots = [("core", "aeion-core", root, ["README.md", "docs/README.md", "docs/generated", "knowledge"]),
                 ("egm", "Elephant-Goldfish Model", root / "app/aeion/goldfish/upstream", ["skills", "resources", "NOTICE.md"]),
                 ("features", "Feature documents", data / "features", ["."])]
        for name in self.store.products():
            roots.append((f"product/{name}", name, data / "products" / name, ["docs/README.md", "docs/generated", "exports"]))
        return roots

    def _files(self):
        found = []
        for key, title, folder, include in self.roots():
            for item in include:
                base = folder / item
                paths = [base] if base.is_file() else sorted(base.rglob("*.md")) if base.is_dir() else []
                for path in paths:
                    if path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_PAGE:
                        found.append((key, title, folder, path))
        return found

    def refresh(self):
        """Rebuild only when a page was added, removed or changed (size and modification time)."""
        files = self._files()
        signature = tuple((str(p), p.stat().st_size, p.stat().st_mtime_ns) for _, _, _, p in files)
        with self.lock:
            if signature == self.signature:
                return
            pages, chunks = {}, []
            for key, group, folder, path in files:
                rel = path.relative_to(folder).as_posix()
                page_id = f"{key}:{rel}"
                text = path.read_text(encoding="utf-8", errors="replace")
                heading = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
                pages[page_id] = {"id": page_id, "root": key, "group": group, "path": rel, "folder": str(folder),
                                  "title": _plain(heading.group(1)) if heading else rel}
                chunks += [dict(c, page=page_id) for c in _chunks(text, pages[page_id]["title"])]
            index, lengths = {}, []
            for number, chunk in enumerate(chunks):
                words = _words(chunk["title"] + " " + chunk["text"])
                lengths.append(len(words))
                for word in set(words):
                    index.setdefault(word, []).append((number, words.count(word)))
            self.pages, self.chunks, self.index, self.lengths, self.signature = pages, chunks, index, lengths, signature

    def tree(self):
        """The navigation: groups in a fixed order, pages sorted with index pages first."""
        self.refresh()
        groups = {}
        for page in self.pages.values():
            groups.setdefault((page["root"], page["group"]), []).append(page)
        order = lambda key: (0 if key[0].startswith("product/") else 1 if key[0] == "features" else 2 if key[0] == "core" else 3, key[1])  # noqa: E731
        result = []
        for key in sorted(groups, key=order):
            pages = sorted(groups[key], key=lambda p: (not p["path"].endswith(("README.md", "index.md")), p["path"]))
            result.append({"root": key[0], "title": key[1], "pages": [{"id": p["id"], "title": p["title"], "path": p["path"]}
                                                                       for p in pages]})
        return result

    def search(self, text, limit=8):
        """BM25 over heading chunks; returns the best chunk per page."""
        self.refresh()
        words = [w for w in _words(text) if w not in STOP]
        if not words or not self.chunks:
            return []
        average = sum(self.lengths) / len(self.lengths)
        scores = {}
        for word in set(words):
            postings = self.index.get(word, [])
            idf = math.log(1 + (len(self.chunks) - len(postings) + 0.5) / (len(postings) + 0.5))
            for number, frequency in postings:
                length = self.lengths[number]
                scores[number] = scores.get(number, 0) + idf * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * length / average))
        best = {}
        for number, score in sorted(scores.items(), key=lambda kv: -kv[1]):
            page = self.chunks[number]["page"]
            if page not in best:
                best[page] = (score, number)
            if len(best) >= limit:
                break
        return [{"page": page, "title": self.pages[page]["title"], "section": self.chunks[n]["title"],
                 "anchor": self.chunks[n]["anchor"], "score": round(s, 3), "snippet": _snippet(self.chunks[n]["text"], words)}
                for page, (s, n) in best.items()]

    def page(self, page_id):
        self.refresh()
        page = self.pages.get(page_id)
        if page is None:
            raise KeyError(page_id)
        path = Path(page["folder"]) / page["path"]
        text = path.read_text(encoding="utf-8", errors="replace")
        html, outline = markdown.render(text, link=lambda target: self._link(page, target))
        ids = sorted(set(re.findall(r"\b(?:GOAL|TERM|REQ|CON|MODEL|SCN|TEST|COMP|DEC|ASM|RISK|CTRL)-[0-9]{3,6}\b", text)))
        return {"id": page_id, "title": page["title"], "group": page["group"], "path": page["path"], "html": html,
                "outline": outline, "markdown": text, "diagrams": self.diagrams(page, ids, text), "ids": ids}

    def _link(self, page, target):
        """A relative link becomes a hub route (#/docs/...) or a diagram URL; anything else is kept as is."""
        if re.match(r"^[a-z]+:", target) or target.startswith("#"):
            return target
        clean, _, fragment = target.partition("#")
        resolved = (Path(page["path"]).parent / clean).as_posix()
        parts = []
        for part in resolved.split("/"):
            if part == "..":
                if not parts:
                    return None
                parts.pop()
            elif part not in ("", "."):
                parts.append(part)
        rel = "/".join(parts)
        if rel.endswith(".svg"):
            return f"/api/docs/asset?root={page['root']}&path={rel}"
        if rel.endswith(".md"):
            return f"#/docs/{page['root']}:{rel}" + (f"::{fragment}" if fragment else "")
        return None

    def diagrams(self, page, ids, text):
        """The rendered views of this page's product whose canonical IDs appear in it (none for a view page itself)."""
        if not page["root"].startswith(("product/", "core")) or "diagrams/" in text:
            return []
        folder = Path(page["folder"])
        try:
            catalog = json.loads((folder / "docs/view-catalog.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        wanted = set(ids)
        found = []
        for view in catalog.get("views", []):
            if wanted & set(view.get("canonical_ids", [])) and (folder / f"docs/generated/diagrams/{view['id']}.svg").is_file():
                found.append({"id": view["id"], "title": view["title"], "question": view["question"], "claim": view["claim"],
                              "src": f"/api/docs/asset?root={page['root']}&path=docs/generated/diagrams/{view['id']}.svg"})
        return found[:4]

    def asset(self, root, rel):
        """A generated SVG diagram of a known root; nothing else is served."""
        self.refresh()
        folders = {key: folder for key, _, folder, _ in self.roots()}
        folder = folders.get(root)
        if folder is None or not re.fullmatch(r"docs/generated/diagrams/[A-Za-z0-9-]+\.svg", rel or ""):
            raise KeyError(rel)
        path = (Path(folder) / rel).resolve()
        if not path.is_relative_to(Path(folder).resolve()) or not path.is_file():
            raise KeyError(rel)
        return path.read_bytes()


def _plain(text):
    return re.sub(r"[`*_\\]", "", text).strip()


def _fold(text):
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def _words(text):
    return WORD.findall(_fold(text))


def _chunks(text, page_title):
    """Sections of at most ~1,500 characters, each under its nearest heading."""
    text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.DOTALL)
    parts, title, anchor, current = [], page_title, "", []
    for line in text.split("\n"):
        heading = re.match(r"#{1,3}\s+(.+)", line)
        if heading:
            if "".join(current).strip():
                parts.append({"title": title, "anchor": anchor, "text": "\n".join(current).strip()})
            title = f"{page_title} › {_plain(heading.group(1))}"
            anchor, current = markdown.heading_id(_plain(heading.group(1))), []
        else:
            current.append(line)
    if "".join(current).strip():
        parts.append({"title": title, "anchor": anchor, "text": "\n".join(current).strip()})
    chunks = []
    for part in parts:
        body = part["text"]
        for start in range(0, len(body), 1500):
            chunks.append(dict(part, text=body[start:start + 1500]))
    return chunks


def _snippet(text, words, size=280):
    folded = _fold(text)
    positions = [folded.find(w) for w in words if folded.find(w) >= 0]
    start = max(0, min(positions) - 60) if positions else 0
    return re.sub(r"\s+", " ", text[start:start + size]).strip()


PAGE_LIMIT = 9000


def sections(text):
    """[(level, title, anchor, start offset)] of a Markdown page's headings, outside code fences."""
    found, fenced, offset = [], False, 0
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            fenced = not fenced
        heading = None if fenced else re.match(r"^(#{1,6})\s+(.+?)\s*#*$", line)
        if heading:
            title = _plain(heading.group(2))
            found.append((len(heading.group(1)), title, markdown.heading_id(title), offset))
        offset += len(line) + 1
    return found


def section_text(text, anchor):
    """The section under the heading with this anchor, down to the next heading of the same or a higher level."""
    heads = sections(text)
    for index, (level, title, slug, start) in enumerate(heads):
        if slug == anchor:
            end = next((s for lvl, _, _, s in heads[index + 1:] if lvl <= level), len(text))
            return title, text[start:end]
    return None, None


class Assistant:
    """The librarian agent with three server tools; every result is numbered evidence the answer cites."""

    def __init__(self, corpus, client, settings, store):
        self.corpus, self.client, self.settings, self.store = corpus, client, settings, store

    def graph(self, node_id, product):
        """A bounded node query on the core's or a product's graph snapshot."""
        if product in (None, "", "core"):
            root = self.settings.root
        else:
            if product not in self.store.products():
                return {"error": f"unknown product {product!r}; known: {', '.join(self.store.products()) or 'none'}"}
            root = self.settings.data / "products" / product
        snapshot = axgraph.snapshot(root, root / "knowledge/spec/spec.json")
        kind = "requirement" if node_id.startswith("REQ-") else "node"
        response, code = axquery.run(snapshot, kind, [node_id])
        return {"code": code, "text": axquery.text(response, cap=30)}

    def tools(self, evidence, emit):
        lock = threading.Lock()

        def cite(item):
            with lock:
                evidence.append(item)
                return len(evidence)

        def search(data, _run):
            emit({"type": "tool", "action": "search", "detail": data["query"]})
            hits = self.corpus.search(data["query"])[:6]
            if not hits:
                return "No section matches; try other words."
            return [{"evidence": cite({"kind": "page", "page": h["page"], "title": h["section"], "anchor": h["anchor"],
                                       "text": h["snippet"]}), "page": h["page"], "section": h["anchor"],
                     "title": h["section"], "snippet": h["snippet"]} for h in hits]

        def open_page(data, _run):
            emit({"type": "tool", "action": "open", "detail": data["page"] + (f" § {data['section']}" if data.get("section") else "")})
            try:
                page = self.corpus.page(data["page"])
            except KeyError:
                return "No such page id; use one from a search result."
            text, title, anchor = page["markdown"], page["title"], None
            if data.get("section"):
                found_title, found = section_text(text, data["section"])
                if found is None:
                    return {"error": "no such section", "outline": [{"section": a, "title": t} for _, t, a, _ in sections(text)][:80]}
                text, title, anchor = found, f"{page['title']} › {found_title}", data["section"]
            elif len(text) > PAGE_LIMIT:
                return {"page": page["id"], "title": page["title"], "note": "This page is long: open one section.",
                        "outline": [{"section": a, "title": t, "level": lvl} for lvl, t, a, _ in sections(text)][:120]}
            number = cite({"kind": "page", "page": page["id"], "title": title, "anchor": anchor, "text": text[:PAGE_LIMIT]})
            return {"evidence": number, "page": page["id"], "title": title, "text": text[:PAGE_LIMIT]}

        def graph(data, _run):
            emit({"type": "tool", "action": "graph", "detail": data["id"]})
            found = self.graph(data["id"], data.get("product"))
            if "error" in found:
                return found["error"]
            number = cite({"kind": "graph", "node": data["id"],
                           "title": f"Graph: {data['id']} ({data.get('product') or 'core'})", "text": found["text"]})
            return {"evidence": number, "text": found["text"]}
        return {"search_docs": search, "open_page": open_page, "graph_query": graph}

    def ask(self, question, history=(), emit=lambda e: None, session=None):
        """Agentic retrieval and a streamed, cited answer; citations are checked against the evidence."""
        evidence, blocks = [], []
        earlier = [m for m in list(history)[-6:] if m.get("content")]
        if earlier:
            blocks.append({"tag": "conversation", "body": "\n\n".join(
                f"{'Question' if m['role'] == 'user' else 'Answer'}: {m['content'][:2000]}" for m in earlier)})
        result = self.client.run("librarian", question, blocks=blocks, tools=self.tools(evidence, emit),
                                 session=session, **streaming(emit))
        answer = result.text
        cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer) if 1 <= int(n) <= len(evidence)})
        sources = [dict(number=n, **{k: evidence[n - 1].get(k) for k in ("kind", "page", "title", "anchor", "node")})
                   for n in cited]
        emit({"type": "answer", "markdown": answer, "sources": sources})
        return {"answer": answer, "sources": sources}
