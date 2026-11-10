# Spec: knowledge/components/axiom-toolkit.md
"""The knowledge graph snapshot (AX-K-001, AX-K-002, AX-K-008): spec, docs and code in one index.

Declared edges come from spec.json, frontmatter, `Spec:` headers and links; resolved edges locate a
binding's selector in a hashed file; static edges come from Python's ast or an ECMAScript lexical
scan. No model, embedding or learned relevance enters the graph. Rebuilt only when inputs change."""
import ast
import json
import os
import re
import shutil
import sys
from pathlib import Path, PurePosixPath

import spec as specs
from common import (GRAPH_DIR, TOOL_VERSION, canonical_digest, confined, export_ignored, inside, is_secret,
                    nested_projects, project_files, sha256, write_atomic)
from strict import InputError, load

FORMAT = "aeion-graph/0.1"
PYTHON = f"python-ast/{sys.version_info.major}.{sys.version_info.minor}"
ECMA = "ecmascript-lexical/1"
EXTRACTORS = {"python": PYTHON, "ecmascript": ECMA, "java": "java-lexical/1", "generic": "line-search/1",
              "headers": "spec-header/1", "markdown": "markdown/1"}
LANGUAGES = {".py": "python", ".ts": "ecmascript", ".tsx": "ecmascript", ".js": "ecmascript", ".jsx": "ecmascript",
             ".mjs": "ecmascript", ".cjs": "ecmascript", ".mts": "ecmascript", ".cts": "ecmascript", ".java": "java",
             ".go": "go", ".rs": "rust", ".kt": "kotlin", ".swift": "swift", ".rb": "ruby", ".php": "php",
             ".cs": "csharp", ".sh": "shell"}
CONFIG = {".json", ".toml", ".yaml", ".yml", ".ini", ".cfg"}
TEST_NAME = re.compile(r"(^test_.*\.py$|.*_test\.(py|ts|js|go)$|.*\.(test|spec)\.(ts|tsx|js|jsx|mjs)$)")
TEST_DIRS = {"tests", "test", "__tests__"}
SPEC_HEADER = re.compile(r"\bSpec:\s*(knowledge/[\w./-]+\.md)")
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
CANONICAL_ID = re.compile(r"\b((?:GOAL|TERM|REQ|CON|MODEL|SCN|TEST|COMP|DEC|ASM|RISK|CTRL)-[0-9]{3,6})\b")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
RESOURCE = re.compile(r'^\s*(?:-\s+)?resource:\s*"?([^"\n]+?)"?\s*$', re.MULTILINE)
MAX_READ = 1048576
# The vendored AxiomSpec package cites its own example's IDs, which are not this project's.
VENDORED = ("knowledge/axiomspec/",)
# The folders whose Markdown cites the canonical spec; a dangling ID there fails the check.
CITING = ("knowledge/", "docs/")


class GraphError(RuntimeError):
    pass


def snapshot(root, spec_path, force=False):
    """The current snapshot: loaded when its fingerprint matches the inputs, otherwise rebuilt and published."""
    root = Path(root)
    files = _files(root)
    fingerprint = _fingerprint(root, files, spec_path)
    folder = root / GRAPH_DIR
    if not force:
        try:
            manifest = load(folder / "manifest.json", 4 * MAX_READ)
            # Anything else in the folder (an older tool's graph, a partial write) is stale, never trusted.
            if (isinstance(manifest, dict) and manifest.get("format") == FORMAT
                    and manifest.get("fingerprint") == fingerprint and manifest.get("tool_version") == TOOL_VERSION):
                return {"manifest": manifest, "nodes": load(folder / "nodes.json", 64 * MAX_READ),
                        "edges": load(folder / "edges.json", 64 * MAX_READ),
                        "symbols": load(folder / "symbols.json", 64 * MAX_READ), "rebuilt": False}
        except InputError:
            pass
    built = build(root, spec_path, files)
    built["manifest"]["fingerprint"] = fingerprint
    _publish(folder, built)
    built["rebuilt"] = True
    return built


def _files(root):
    try:
        listed = project_files(root, untracked=True)
    except Exception as error:  # a broken repository is an error, never an empty project
        raise GraphError(f"cannot list project files: {error}") from None
    # Nested projects and folders releases leave out (a playground with its own spec) are not this project.
    nested = nested_projects(listed) | export_ignored(root)
    passive = (root / "skills/catalog.json").is_file()
    return [rel for rel in listed if not inside(rel, nested) and not is_secret(PurePosixPath(rel).name)
            and not rel.startswith(".aeion/") and not (passive and rel.startswith("skills/"))
            and (root / rel).is_file() and not (root / rel).is_symlink()]


def _fingerprint(root, files, spec_path):
    stats = []
    for rel in files:
        info = (root / rel).stat()
        stats.append([rel, info.st_size, info.st_mtime_ns])
    spec_stat = spec_path.stat() if spec_path.is_file() else None
    return canonical_digest([stats, str(spec_path), [spec_stat.st_size, spec_stat.st_mtime_ns] if spec_stat else None])


def build(root, spec_path, files=None):
    """Read every input once and return the snapshot records, sorted, with a content-derived snapshot ID."""
    files = _files(root) if files is None else files
    nodes, edges, symbols, limits = {}, [], {}, []
    present = set(files)
    contents = {}
    # Files first: every other layer points at them.
    for rel in files:
        raw = (root / rel).read_bytes()
        node = {"id": "file:" + rel, "type": "File", "path": rel, "sha256": sha256(raw), "role": _role(rel),
                "language": LANGUAGES.get(PurePosixPath(rel).suffix.lower(), "")}
        nodes[node["id"]] = node
        if len(raw) <= MAX_READ and b"\0" not in raw[:8192]:
            try:
                contents[rel] = raw.decode("utf-8")
            except UnicodeDecodeError:
                pass
    coverage = {"python": [0, 0], "ecmascript": [0, 0], "no_import_extractor": {}}
    dirs = {str(PurePosixPath(rel).parent) for rel in files}
    # Code: Spec headers, imports and symbols.
    for rel, text in sorted(contents.items()):
        node = nodes["file:" + rel]
        if node["role"] in ("code", "test"):
            _code_layer(rel, text, node, present, dirs, edges, symbols, coverage)
    # Tests that name a project path literally reach it even without importing it.
    for rel, text in sorted(contents.items()):
        if nodes["file:" + rel]["role"] == "test":
            for target in sorted(_named_paths(rel, text, present)):
                edges.append(_edge("file:" + rel, "names_file", "file:" + target, "static", extractor="literal-path/1"))
    # Documents: frontmatter, links and canonical ID mentions.
    mentions = {}
    for rel, text in sorted(contents.items()):
        if rel.endswith(".md"):
            _doc_layer(root, rel, text, nodes["file:" + rel], present, edges, mentions)
            if rel.startswith(VENDORED):
                mentions.pop(rel, None)
    # The canonical spec, its bindings and the docs that mention its IDs.
    spec_state = _spec_layer(root, spec_path, nodes, edges, symbols, contents, mentions, limits)
    for language, (parsed, failed) in (("python", coverage["python"]), ("ecmascript", coverage["ecmascript"])):
        if failed:
            limits.append(f"{failed} {language} file(s) could not be parsed; their imports are absent")
    for language, count in sorted(coverage["no_import_extractor"].items()):
        limits.append(f"{count} {language} file(s): no import extractor, so no dependency edges")
    limits.append("Imports only: calls, reflection, dynamic loading and configuration-driven wiring are not edges.")
    return _assemble(nodes, edges, symbols, spec_state, coverage, limits, files, root)


def _role(rel):
    path = PurePosixPath(rel)
    suffix = path.suffix.lower()
    if suffix in LANGUAGES and (TEST_NAME.match(path.name) or TEST_DIRS & set(path.parts[:-1])):
        return "test"
    if suffix in LANGUAGES:
        return "code"
    if suffix == ".md":
        return "doc"
    if suffix in CONFIG:
        return "config"
    if not suffix and path.parts[0] == "tools":
        return "code"
    return "other"


def _code_layer(rel, text, node, present, dirs, edges, symbols, coverage):
    head = "\n".join(text.splitlines()[:20])
    for doc in sorted(set(SPEC_HEADER.findall(head))):
        edges.append(_edge("file:" + rel, "specified_by", "file:" + doc, "declared", extractor=EXTRACTORS["headers"]))
    language = node["language"] or ("python" if text.startswith("#!") and "python" in text.split("\n", 1)[0] else "")
    if language == "python":
        found = _python(rel, text, present, dirs)
        coverage["python"][0 if found is not None else 1] += 1
        if found is not None:
            imports, defined = found
            edges += [_edge("file:" + rel, "imports", "file:" + t, "static", line=line, extractor=PYTHON)
                      for t, line in imports]
            symbols[rel] = defined
    elif language == "ecmascript":
        imports, defined = _ecmascript(rel, text, present)
        coverage["ecmascript"][0] += 1
        edges += [_edge("file:" + rel, "imports", "file:" + t, "static", line=line, extractor=ECMA)
                  for t, line in imports]
        symbols[rel] = defined
    elif language == "java":
        symbols[rel] = _java_symbols(text)
        coverage["no_import_extractor"]["java"] = coverage["no_import_extractor"].get("java", 0) + 1
    elif language:
        coverage["no_import_extractor"][language] = coverage["no_import_extractor"].get(language, 0) + 1


def _python(rel, text, present, dirs):
    """(imports, symbols) of one Python file, or None when it does not parse."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    here = PurePosixPath(rel).parent
    # Bases: each ancestor of the file up to the root, then folders the file adds to sys.path.
    bases = [("" if str(p) == "." else str(p)) for p in [here, *here.parents]] + _sys_path_folders(tree, dirs)
    imports = []
    for item in ast.walk(tree):
        if isinstance(item, ast.Import):
            for alias in item.names:
                target = _module(alias.name, bases, present)
                if target:
                    imports.append((target, item.lineno))
        elif isinstance(item, ast.ImportFrom):
            if item.level:
                base = here
                for _ in range(item.level - 1):
                    base = base.parent
                roots = ["" if str(base) == "." else str(base)]
            else:
                roots = bases
            for alias in item.names:
                dotted = ".".join(p for p in (item.module, alias.name) if p)
                target = _module(dotted, roots, present) or (_module(item.module, roots, present) if item.module else None)
                if target:
                    imports.append((target, item.lineno))
    defined = []
    for item in tree.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.append({"name": item.name, "kind": "class" if isinstance(item, ast.ClassDef) else "def",
                            "line": item.lineno})
            if isinstance(item, ast.ClassDef):
                defined += [{"name": f"{item.name}.{m.name}", "kind": "def", "line": m.lineno} for m in item.body
                            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
    return sorted(set(t for t in imports if t[0] != rel)), sorted(defined, key=lambda s: (s["line"], s["name"]))


def _sys_path_folders(tree, dirs):
    """Project folders named by string constants inside a sys.path.insert/append call."""
    found = set()
    for call in ast.walk(tree):
        func = getattr(call, "func", None)
        if (isinstance(call, ast.Call) and isinstance(func, ast.Attribute) and func.attr in ("insert", "append")
                and isinstance(func.value, ast.Attribute) and func.value.attr == "path"
                and isinstance(func.value.value, ast.Name) and func.value.value.id == "sys"):
            found |= {n.value.strip("/") for arg in call.args for n in ast.walk(arg)
                      if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.strip("/") in dirs}
    return sorted(found)


def _module(dotted, bases, present):
    if not dotted:
        return None
    path = dotted.replace(".", "/")
    for base in bases:
        prefix = f"{base}/" if base else ""
        for candidate in (f"{prefix}{path}.py", f"{prefix}{path}/__init__.py"):
            if candidate in present:
                return candidate
    return None


ECMA_IMPORT = re.compile(r"""(?:\bimport\s+(?:[\w*{}\s,$]+?\s+from\s+)?|\bexport\s+[\w*{}\s,$]+?\s+from\s+|"""
                         r"""\brequire\s*\(\s*|\bimport\s*\(\s*)["']([^"'\n]+)["']""")
ECMA_SYMBOL = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:declare\s+)?(?:abstract\s+)?(?:async\s+)?"
                         r"(function\s*\*?|class|interface|type|enum|const|let|var)\s+([A-Za-z_$][\w$]*)")
ECMA_METHOD = re.compile(r"^\s*(?:public\s+|private\s+|protected\s+|static\s+|async\s+|readonly\s+)*"
                         r"([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*(?::\s*[^{]+)?\{")
EXTENSIONS = ("", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", "/index.ts", "/index.tsx", "/index.js")


def _ecmascript(rel, text, present):
    """(imports, symbols) from a comment-stripped lexical scan; relative specifiers only."""
    code = _strip_comments(text)
    here = PurePosixPath(rel).parent
    imports = []
    for match in ECMA_IMPORT.finditer(code):
        spec = match.group(1)
        if not spec.startswith(("./", "../")):
            continue
        base = os.path.normpath(str(here / spec)).replace(os.sep, "/")
        for suffix in EXTENSIONS:
            if base + suffix in present:
                imports.append((base + suffix, code.count("\n", 0, match.start()) + 1))
                break
    defined, classes, depth = [], [], 0
    for number, line in enumerate(code.split("\n"), 1):
        found = ECMA_SYMBOL.match(line)
        if found:
            kind = found.group(1).split()[0].rstrip("*")
            defined.append({"name": found.group(2), "kind": kind, "line": number})
            if kind == "class":
                classes.append((found.group(2), depth))
        elif classes and depth == classes[-1][1] + 1:
            method = ECMA_METHOD.match(line)
            if method and method.group(1) not in ("if", "for", "while", "switch", "catch", "return", "constructor"):
                defined.append({"name": f"{classes[-1][0]}.{method.group(1)}", "kind": "method", "line": number})
        depth += line.count("{") - line.count("}")
        while classes and depth <= classes[-1][1]:
            classes.pop()
    return sorted(set(t for t in imports if t[0] != rel)), defined


def _strip_comments(text):
    # Blank out comments but keep strings and line numbers, so offsets still map to lines.
    out, i, n = [], 0, len(text)
    quote = None
    while i < n:
        char = text[i]
        if quote:
            out.append(char)
            if char == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if char == quote:
                quote = None
        elif char in "\"'`":
            quote = char
            out.append(char)
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end < 0 else end
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            block = text[i:n if end < 0 else end + 2]
            out.append("\n" * block.count("\n"))
            i = n if end < 0 else end + 2
            continue
        else:
            out.append(char)
        i += 1
    return "".join(out)


JAVA_SYMBOL = re.compile(r"^\s*(?:(?:public|private|protected|static|final|abstract|sealed|synchronized)\s+)*"
                         r"(class|interface|enum|record)\s+(\w+)")
JAVA_METHOD = re.compile(r"^\s*(?:(?:public|private|protected|static|final|abstract|synchronized)\s+)+[\w<>\[\],.\s]+?\s+"
                         r"(\w+)\s*\(")


def _java_symbols(text):
    defined, current = [], None
    for number, line in enumerate(text.split("\n"), 1):
        found = JAVA_SYMBOL.match(line)
        if found:
            current = found.group(2)
            defined.append({"name": current, "kind": found.group(1), "line": number})
            continue
        method = JAVA_METHOD.match(line)
        if method and current:
            defined.append({"name": f"{current}.{method.group(1)}", "kind": "method", "line": number})
    return defined


def _named_paths(rel, text, present):
    here = PurePosixPath(rel).parent
    found = set()
    for token in set(re.findall(r"[\w.][\w./-]*/[\w./-]+", text)):
        token = token.rstrip(".")
        for candidate in (token, os.path.normpath(str(here / token)).replace(os.sep, "/")):
            if candidate in present and candidate != rel:
                found.add(candidate)
    return found


def _doc_layer(root, rel, text, node, present, edges, mentions):
    match = FRONTMATTER.match(text)
    block = match.group(1) if match else ""
    title = re.search(r'^title:\s*"?([^"\n]+)"?\s*$', block, re.MULTILINE)
    heading = re.search(r"^#\s+(.+)$", text[match.end() if match else 0:], re.MULTILINE)
    node["title"] = (title.group(1) if title else heading.group(1) if heading else rel).strip()
    kind = re.search(r"^type:\s*\"?(\w+)", block, re.MULTILINE)
    node["doc_type"] = kind.group(1) if kind else ""
    here = PurePosixPath(rel).parent
    # Frontmatter sources: the files a document specifies (a folder covers what it holds).
    for resource in RESOURCE.findall(block):
        target = _local(here, resource)
        if target is None:
            continue
        if target in present:
            edges.append(_edge("file:" + rel, "specifies", "file:" + target, "declared", extractor="frontmatter/1"))
        else:
            for covered in sorted(p for p in present if p.startswith(target.rstrip("/") + "/")):
                edges.append(_edge("file:" + rel, "specifies", "file:" + covered, "declared", via=target,
                                   extractor="frontmatter/1"))
    listed = re.search(r"^spec_ids:\s*\[([^\]]*)\]", block, re.MULTILINE)
    ids = set(re.findall(r"[A-Z][A-Z0-9_]*-[0-9]{3,6}", listed.group(1))) if listed else set()
    # Body links between documents and to code.
    body = text[match.end():] if match else text
    for target in sorted({_local(here, link) for link in LINK.findall(body)} - {None}):
        if target in present and target != rel:
            edges.append(_edge("file:" + rel, "links_to", "file:" + target, "declared", extractor=EXTRACTORS["markdown"]))
    mentions[rel] = sorted(ids | set(CANONICAL_ID.findall(_without_code(body))))


def _without_code(markdown):
    # IDs inside code (fenced or inline) are illustrations, not references.
    return re.sub(r"`[^`\n]*`", "", re.sub(r"```.*?```", "", markdown, flags=re.DOTALL))


def _local(here, target):
    target = target.split("#", 1)[0].strip().strip("<>")
    if not target or "://" in target or target.startswith(("mailto:", "/")) or ":" in target.split("/")[0]:
        return None
    normal = os.path.normpath(str(here / target)).replace(os.sep, "/")
    return None if normal.startswith("..") else normal


def _spec_layer(root, spec_path, nodes, edges, symbols, contents, mentions, limits):
    """Canonical records and edges, binding resolution and doc mentions; the spec's state for the manifest."""
    if not spec_path.is_file():
        limits.append("No knowledge/spec/spec.json: the graph holds docs and code only.")
        return {"path": _rel(root, spec_path), "status": "missing", "sha256": None}
    result = specs.Result()
    spec = specs.load_spec(spec_path, result)
    if spec is None:
        first = result.diagnostics[0]
        limits.append(f"knowledge/spec/spec.json is not valid ({first['code']}): canonical nodes are absent.")
        return {"path": _rel(root, spec_path), "status": "invalid", "sha256": None}
    model = specs.Model(spec)
    nodes[spec["project"]["id"]] = {"id": spec["project"]["id"], "type": "Project", "label": spec["project"]["name"],
                                    "record": spec["project"]}
    for section, kind in (("actors", "Actor"), ("sources", "Source"), ("environments", "Environment"),
                          ("bindings", "Binding"), ("context_assets", "Asset")):
        for record in spec[section]:
            label = record.get("name") or record.get("title") or record.get("locator") or record["id"]
            nodes[record["id"]] = {"id": record["id"], "type": kind, "label": label, "record": record}
    for record in spec["nodes"]:
        nodes[record["id"]] = {"id": record["id"], "type": record["kind"], "label": record["title"],
                               "status": record["status"], "record": record}
        for source in record["source_ids"]:
            edges.append(_edge(record["id"], "supported_by", source, "declared"))
    for edge in spec["edges"]:
        edges.append(_edge(edge["from"], edge["relation"], edge["to"], "declared", id=edge["id"]))
    for asset in spec["context_assets"]:
        edges += [_edge(asset["id"], "supplies_context_for", target, "declared") for target in asset["supports"]]
    unresolved = 0
    for binding in spec["bindings"]:
        edges.append(_edge(binding["node_id"], "has_binding", binding["id"], "declared"))
        located = resolve_binding(root, binding, symbols, contents)
        nodes[binding["id"]]["resolution"] = located
        if located["status"] == "resolved":
            edges.append(_edge(binding["id"], "resolves_to", "file:" + binding["path"], "resolved",
                               line=located["line"], extractor=located["extractor"]))
        elif binding["expected_resolution"] == "must_resolve":
            unresolved += 1
    if unresolved:
        limits.append(f"{unresolved} must_resolve binding(s) did not resolve in this snapshot.")
    dangling = {}
    for rel, ids in mentions.items():
        for node_id in ids:
            if node_id in model.nodes:
                edges.append(_edge("file:" + rel, "mentions", node_id, "declared"))
            elif rel.startswith(CITING):
                # Only knowledge/ and docs/ cite the spec; elsewhere an ID-like word (a ticket key) is ordinary text.
                dangling.setdefault(rel, []).append(node_id)
    return {"path": _rel(root, spec_path), "status": "loaded", "sha256": model.digest, "dangling_mentions": dangling}


def resolve_binding(root, binding, symbols, contents):
    """Locate a binding's selector in the snapshot (AX-M-014). A symbol resolves by its definition; a binding
    without a symbol names the whole file, so it resolves to the file's first line when the file is present."""
    path, symbol = binding["path"], binding["symbol"]
    if confined(root, path) is None:
        return {"status": "unsafe", "detail": "path escapes the project or is not a safe relative path"}
    if path not in contents:
        return {"status": "missing", "detail": f"{path} is not in the snapshot"}
    if symbol is None:
        return {"status": "resolved", "line": 1, "extractor": "file-level/1"}
    extractor = EXTRACTORS.get(LANGUAGES.get(PurePosixPath(path).suffix.lower(), ""), EXTRACTORS["generic"])
    for item in symbols.get(path, []):
        if item["name"] == symbol:
            return {"status": "resolved", "line": item["line"], "extractor": extractor}
    if binding["language"] == "generic" or path not in symbols:
        last = symbol.split(".")[-1]
        for number, line in enumerate(contents[path].split("\n"), 1):
            if re.search(r"(?<![\w$])" + re.escape(last) + r"(?![\w$])", line):
                return {"status": "resolved", "line": number, "extractor": EXTRACTORS["generic"]}
    return {"status": "unresolved", "detail": f"symbol {symbol!r} not found in {path}"}


def _rel(root, path):
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return str(path)


def _edge(source, relation, target, origin, **extra):
    edge = {"from": source, "relation": relation, "to": target, "origin": origin}
    edge.update({k: v for k, v in extra.items() if v is not None})
    return edge


def _assemble(nodes, edges, symbols, spec_state, coverage, limits, files, root):
    ordered_nodes = [nodes[key] for key in sorted(nodes)]
    unique = {canonical_digest(e): e for e in edges}
    ordered_edges = sorted(unique.values(), key=lambda e: (e["from"], e["relation"], e["to"], e.get("id", ""),
                                                          e.get("line", 0)))
    ordered_symbols = {rel: symbols[rel] for rel in sorted(symbols)}
    inputs = canonical_digest([[n["path"], n["sha256"]] for n in ordered_nodes if n["type"] == "File"])
    body = {"nodes": ordered_nodes, "edges": ordered_edges, "symbols": ordered_symbols, "spec": spec_state,
            "inputs": inputs}
    counts = {"files": len(files), "nodes": len(ordered_nodes), "edges": len(ordered_edges),
              "spec_records": sum(1 for n in ordered_nodes if n["type"] != "File"),
              "python_files": coverage["python"][0], "ecmascript_files": coverage["ecmascript"][0]}
    manifest = {"format": FORMAT, "tool_version": TOOL_VERSION, "snapshot_id": canonical_digest(body),
                "inputs_sha256": inputs, "spec": spec_state, "extractors": EXTRACTORS, "counts": counts,
                "analysis_limits": sorted(set(limits))}
    return {"manifest": manifest, "nodes": ordered_nodes, "edges": ordered_edges, "symbols": ordered_symbols}


def _publish(folder, built):
    """Write a complete new snapshot beside the old one, then swap it in, so no reader mixes generations."""
    folder.parent.mkdir(parents=True, exist_ok=True)
    staging = folder.with_name(f"{folder.name}.new-{os.getpid()}")
    shutil.rmtree(staging, ignore_errors=True)
    for name in ("nodes", "edges", "symbols", "manifest"):
        write_atomic(staging / f"{name}.json", _compact(built[name]))
    retired = folder.with_name(f"{folder.name}.old-{os.getpid()}")
    if folder.exists():
        os.replace(folder, retired)
    os.replace(staging, folder)
    shutil.rmtree(retired, ignore_errors=True)


def _compact(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def summary(snapshot_value):
    manifest = snapshot_value["manifest"]
    return {"snapshot_id": manifest["snapshot_id"], "rebuilt": snapshot_value.get("rebuilt", False),
            "spec": {k: v for k, v in manifest["spec"].items() if k != "dangling_mentions"},
            "counts": manifest["counts"], "analysis_limits": manifest["analysis_limits"]}


def summary_text(value):
    counts, spec_state = value["counts"], value["spec"]
    lines = [f"graph {value['snapshot_id'][:12]} ({'rebuilt' if value['rebuilt'] else 'current'}): "
             f"{counts['files']} files, {counts['nodes']} nodes, {counts['edges']} edges",
             f"spec: {spec_state['status']} {spec_state.get('path', '')} "
             + (spec_state["sha256"][:12] if spec_state.get("sha256") else "")]
    lines += [f"limit: {limit}" for limit in value["analysis_limits"]]
    return "\n".join(lines)
