# Spec: knowledge/components/aeion-engine.md
"""The workspace on disk: sessions, saved feature documents and product specifications. Every write is
atomic and every identifier is checked before it becomes a path, so a request cannot leave the workspace."""
import contextlib
import io
import json
import os
import re
import secrets
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,79}\Z")
KINDS = ("brief", "design", "review", "imported")


class StoreError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slug(text, fallback="item"):
    value = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60].strip("-")
    return value or fallback


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.lock = threading.RLock()
        for folder in ("sessions", "features", "products", "studio"):
            (self.root / folder).mkdir(parents=True, exist_ok=True)

    def path(self, folder, name, suffix):
        """The file for a checked name; StoreError for anything that is not a plain lowercase name."""
        if not isinstance(name, str) or not NAME.match(name):
            raise StoreError(f"invalid name {name!r}")
        return self.root / folder / f"{name}{suffix}"

    def new_name(self, folder, title):
        base = slug(title)[:48].strip("-") or "item"
        return f"{base}-{secrets.token_hex(3)}"

    def write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(data if isinstance(data, str) else json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def read_json(self, path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise StoreError("not found") from None

    # Sessions: one JSON document per brainstorm, draft, review or studio conversation.
    def save_session(self, session, folder="sessions"):
        with self.lock:
            session["updated"] = now()
            self.write(self.path(folder, session["id"], ".json"), session)
        return session

    def session(self, name, folder="sessions"):
        return self.read_json(self.path(folder, name, ".json"))

    def sessions(self, folder="sessions"):
        found = []
        for path in sorted((self.root / folder).glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                continue
            found.append({k: value.get(k) for k in ("id", "title", "kind", "state", "updated", "feature")})
        return sorted(found, key=lambda s: s.get("updated") or "", reverse=True)

    # Feature documents: the Markdown a brainstorm, draft or review saves, or a file the owner drops.
    def save_feature(self, title, markdown, kind, origin, name=None):
        if kind not in KINDS:
            raise StoreError(f"unknown kind {kind!r}")
        with self.lock:
            name = name or self.new_name("features", title)
            self.write(self.path("features", name, ".md"), markdown)
            meta = {"id": name, "title": title.strip()[:200] or name, "kind": kind, "origin": origin,
                    "bytes": len(markdown.encode("utf-8")), "saved": now()}
            self.write(self.path("features", name, ".json"), meta)
        return meta

    def feature(self, name):
        meta = self.read_json(self.path("features", name, ".json"))
        return meta, self.path("features", name, ".md").read_text(encoding="utf-8")

    def features(self):
        found = []
        for path in sorted((self.root / "features").glob("*.json")):
            try:
                found.append(json.loads(path.read_text(encoding="utf-8")))
            except ValueError:
                continue
        return sorted(found, key=lambda f: f.get("saved") or "", reverse=True)

    # Products: one AxiomSpec project folder each (knowledge/spec/spec.json, docs/), created once.
    def product(self, name, title=None):
        folder = self.path("products", name, "")
        if not (folder / "knowledge/spec/spec.json").is_file():
            import docs as axiom_docs
            with self.lock, contextlib.redirect_stdout(io.StringIO()):
                axiom_docs.init(folder, folder / "knowledge/spec/spec.json", title or name, "Product owner")
        return folder

    def products(self):
        return sorted(p.name for p in (self.root / "products").iterdir()
                      if (p / "knowledge/spec/spec.json").is_file())
