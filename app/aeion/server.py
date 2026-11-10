# Spec: knowledge/components/aeion-engine.md
"""The local web server: a JSON API, background jobs streamed as server-sent events, and the static page.
It listens on a loopback address only, answers loopback peers only, refuses a foreign Host header (DNS
rebinding) and any write without its custom header (cross-site requests), bounds every body, and never
returns the API key or a stack trace."""
import json
import re
import secrets
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import VERSION, agents, brainstorm, config, design, docshub, llm, markdown, specstudio
from .store import Store, StoreError

WEB = Path(__file__).resolve().parents[1] / "web"
STATIC = {"app.css": "text/css; charset=utf-8", "app.js": "text/javascript; charset=utf-8",
          "icon.svg": "image/svg+xml"}
PAGE_POLICY = ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; "
               "font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
MAX_BODY = 2 * 1024 * 1024


class Jobs:
    """Background work whose events a page reads as a server-sent stream, replayed from the start."""

    def __init__(self):
        self.jobs, self.lock = {}, threading.Lock()

    def start(self, work):
        job = {"id": secrets.token_hex(8), "events": [], "done": False, "condition": threading.Condition(),
               "started": time.time()}
        with self.lock:
            self.jobs = {k: v for k, v in self.jobs.items() if time.time() - v["started"] < 3600}
            self.jobs[job["id"]] = job

        def emit(event):
            with job["condition"]:
                job["events"].append(event)
                job["condition"].notify_all()

        def run():
            try:
                emit({"type": "done", "result": work(emit)})
            except (StoreError, llm.LLMError) as error:
                emit({"type": "error", "message": getattr(error, "message", None) or str(error)})
            except Exception:  # an unexpected failure is logged server-side and reported without details
                traceback.print_exc()
                emit({"type": "error", "message": "unexpected server error (see the server log)"})
            finally:
                with job["condition"]:
                    job["done"] = True
                    job["condition"].notify_all()
        threading.Thread(target=run, daemon=True).start()
        return job["id"]

    def get(self, name):
        with self.lock:
            return self.jobs.get(name)


class App:
    """Everything a request may touch: settings, store, model client, corpus and jobs."""

    def __init__(self, settings=None, client=None):
        self.settings = settings or config.load()
        self.store = Store(self.settings.data)
        self.meter = llm.Meter(self.settings.price)
        self.client = client or agents.client(self.settings, self.meter)
        if isinstance(self.client, agents.MockAgents):
            self.meter = self.client.meter
        self.corpus = docshub.Corpus(self.settings, self.store)
        self.assistant = docshub.Assistant(self.corpus, self.client, self.settings, self.store)
        self.jobs = Jobs()

    def need_model(self):
        if not self.client.ready:
            raise StoreError(self.client.problem or "the agents are not ready")

    def status(self):
        known = specstudio.catalog(self.settings)
        return {"version": VERSION, "model": self.settings.model, "provider": self.settings.provider,
                "harness": "flue", "reasoning": "max", "ready": bool(self.client.ready), "problem": self.client.problem,
                "meter": self.meter.snapshot(), "products": self.store.products(),
                "observability": {"available": known["available"], "features": len(known["features"])}}


ROUTES = []


def route(method, pattern):
    def register(function):
        ROUTES.append((method, re.compile(f"^{pattern}$"), function))
        return function
    return register


def job(app, work):
    app.need_model()
    return {"job": app.jobs.start(work)}


@route("GET", "/api/status")
def _status(app, body, query):
    return app.status()


@route("GET", "/api/sessions")
def _sessions(app, body, query):
    return {"sessions": app.store.sessions(), "studio": app.store.sessions("studio")}


@route("GET", r"/api/sessions/(?P<name>[a-z0-9-]+)")
def _session(app, body, query, name):
    return app.store.session(name)


@route("POST", "/api/brainstorms")
def _brainstorm_new(app, body, query):
    session = brainstorm.create(app.store, body.get("title", ""), body.get("idea", ""), body.get("author", "owner"))
    return {"session": session, **job(app, lambda emit: brainstorm.turn(app.store, app.client, session["id"], "", emit))}


@route("POST", r"/api/brainstorms/(?P<name>[a-z0-9-]+)/message")
def _brainstorm_message(app, body, query, name):
    text = str(body.get("text", ""))
    if not text.strip():
        raise StoreError("write a message")
    return job(app, lambda emit: brainstorm.turn(app.store, app.client, name, text, emit))


@route("POST", r"/api/brainstorms/(?P<name>[a-z0-9-]+)/review")
def _brainstorm_review(app, body, query, name):
    return job(app, lambda emit: brainstorm.review(app.store, app.client, name, emit))


@route("PUT", r"/api/brainstorms/(?P<name>[a-z0-9-]+)/brief")
def _brainstorm_brief(app, body, query, name):
    return brainstorm.edit_brief(app.store, name, str(body.get("markdown", "")))


@route("POST", r"/api/brainstorms/(?P<name>[a-z0-9-]+)/save")
def _brainstorm_save(app, body, query, name):
    return brainstorm.save(app.store, name)


@route("POST", r"/api/brainstorms/(?P<name>[a-z0-9-]+)/reopen")
def _brainstorm_reopen(app, body, query, name):
    return brainstorm.reopen(app.store, name)


@route("POST", "/api/drafts")
def _draft_new(app, body, query):
    return design.create_draft(app.store, body.get("feature"), body.get("title"), body.get("notes", ""))


@route("POST", r"/api/drafts/(?P<name>[a-z0-9-]+)/section")
def _draft_section(app, body, query, name):
    return job(app, lambda emit: design.draft_section(app.store, app.client, name, str(body.get("instruction", "")), emit))


@route("POST", r"/api/drafts/(?P<name>[a-z0-9-]+)/approve")
def _draft_approve(app, body, query, name):
    return design.approve_section(app.store, name)


@route("POST", r"/api/drafts/(?P<name>[a-z0-9-]+)/reconcile")
def _draft_reconcile(app, body, query, name):
    return job(app, lambda emit: design.reconcile(app.store, app.client, name))


@route("POST", r"/api/drafts/(?P<name>[a-z0-9-]+)/save")
def _draft_save(app, body, query, name):
    return design.save_draft(app.store, name)


@route("POST", "/api/reviews")
def _review_new(app, body, query):
    return design.create_review(app.store, body.get("feature"), body.get("preset", "interactive"))


@route("POST", r"/api/reviews/(?P<name>[a-z0-9-]+)/run")
def _review_run(app, body, query, name):
    return job(app, lambda emit: design.run_stage(app.store, app.client, name, emit))


@route("POST", r"/api/reviews/(?P<name>[a-z0-9-]+)/gate")
def _review_gate(app, body, query, name):
    return design.gate(app.store, name, str(body.get("action", "")))


@route("POST", r"/api/reviews/(?P<name>[a-z0-9-]+)/resolve")
def _review_resolve(app, body, query, name):
    return job(app, lambda emit: design.resolve(app.store, app.client, name, int(body.get("stage", 0))))


@route("POST", r"/api/reviews/(?P<name>[a-z0-9-]+)/apply")
def _review_apply(app, body, query, name):
    accepted = [int(i) for i in body.get("accepted", []) if str(i).isdigit()]
    return design.apply(app.store, name, int(body.get("stage", 0)), accepted)


@route("GET", "/api/features")
def _features(app, body, query):
    return {"features": app.store.features()}


@route("GET", r"/api/features/(?P<name>[a-z0-9-]+)")
def _feature(app, body, query, name):
    meta, text = app.store.feature(name)
    return {"meta": meta, "markdown": text, "html": markdown.render(text)[0]}


@route("POST", "/api/features")
def _feature_import(app, body, query):
    text = str(body.get("markdown", ""))
    if not text.strip() or len(text.encode("utf-8")) > 500_000:
        raise StoreError("a feature document is non-empty Markdown of at most 500 KB")
    title = str(body.get("title") or (re.search(r"^#\s+(.+)$", text, re.MULTILINE) or [None, "Imported feature"])[1])
    return app.store.save_feature(title, text, "imported", "dropped by the owner")


@route("GET", "/api/catalog")
def _catalog(app, body, query):
    known = specstudio.catalog(app.settings)
    return {**known, "target": specstudio.target()}


@route("GET", "/api/studio")
def _studio_list(app, body, query):
    return {"studio": app.store.sessions("studio"), "products": app.store.products()}


@route("POST", "/api/studio")
def _studio_new(app, body, query):
    product = str(body.get("product") or "aeion-autonomous-forum")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", product):
        raise StoreError("a product name is lowercase letters, digits and dashes")
    session = specstudio.create(app.store, body.get("feature"), product, body.get("title"))
    return {"session": session, **job(app, lambda emit: specstudio.draft(app.store, app.client, app.settings, session["id"], emit))}


@route("GET", r"/api/studio/(?P<name>[a-z0-9-]+)")
def _studio_get(app, body, query, name):
    session = app.store.session(name, "studio")
    preview = (session.get("checks") or {}).get("preview") or ""
    return {"session": session, "preview_html": markdown.render(preview)[0] if preview else ""}


@route("POST", r"/api/studio/(?P<name>[a-z0-9-]+)/draft")
def _studio_draft(app, body, query, name):
    return job(app, lambda emit: specstudio.draft(app.store, app.client, app.settings, name, emit))


@route("POST", r"/api/studio/(?P<name>[a-z0-9-]+)/check")
def _studio_check(app, body, query, name):
    return specstudio.check(app.store, app.settings, name)


@route("POST", r"/api/studio/(?P<name>[a-z0-9-]+)/answer")
def _studio_answer(app, body, query, name):
    return job(app, lambda emit: specstudio.answer(app.store, app.client, app.settings, name, str(body.get("question", "")),
                                                   body.get("choice"), str(body.get("text", "")), emit))


@route("POST", r"/api/studio/(?P<name>[a-z0-9-]+)/entry")
def _studio_entry(app, body, query, name):
    return specstudio.set_entry(app.store, app.settings, name, body.get("fields") or {})


@route("POST", r"/api/studio/(?P<name>[a-z0-9-]+)/discuss")
def _studio_discuss(app, body, query, name):
    text = str(body.get("text", ""))
    if not text.strip():
        raise StoreError("write a message")
    return job(app, lambda emit: specstudio.discuss(app.store, app.client, app.settings, name, text, emit))


@route("POST", r"/api/studio/(?P<name>[a-z0-9-]+)/change")
def _studio_change(app, body, query, name):
    return job(app, lambda emit: specstudio.change(app.store, app.client, app.settings, name, str(body.get("instruction", "")), emit))


@route("POST", r"/api/studio/(?P<name>[a-z0-9-]+)/approve")
def _studio_approve(app, body, query, name):
    return job(app, lambda emit: specstudio.approve(app.store, app.client, app.settings, name, emit))


@route("GET", "/api/docs/tree")
def _docs_tree(app, body, query):
    return {"tree": app.corpus.tree()}


@route("GET", "/api/docs/page")
def _docs_page(app, body, query):
    try:
        return app.corpus.page(query.get("id", [""])[0])
    except KeyError:
        raise StoreError("not found") from None


@route("GET", "/api/docs/search")
def _docs_search(app, body, query):
    return {"results": app.corpus.search(query.get("q", [""])[0])}


@route("POST", "/api/docs/ask")
def _docs_ask(app, body, query):
    question = str(body.get("question", "")).strip()
    if not question:
        raise StoreError("ask a question")
    history = [m for m in body.get("history", []) if isinstance(m, dict) and m.get("role") in ("user", "assistant")]
    conversation = str(body.get("conversation") or "docs")
    return job(app, lambda emit: app.assistant.ask(question, history, emit, session=f"docs-{conversation[:40]}"))


class Handler(BaseHTTPRequestHandler):
    app = None
    server_version = f"aeion-core/{VERSION}"

    def log_message(self, form, *args):
        pass

    def _host_ok(self):
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        return host in ("127.0.0.1", "localhost", "::1") or host == self.app.settings.host

    def _send(self, status, body, content_type="application/json; charset=utf-8", extra=()):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        for name, value in extra:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status, code, message):
        self._send(status, {"error": code, "message": message})

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def _dispatch(self, method):
        # This machine only: the peer must be a loopback address, whatever the bound host, and the Host header
        # must name this machine (DNS rebinding).
        if not config.loopback(self.client_address[0]):
            return self._error(403, "peer", "this server answers this machine only")
        if not self._host_ok():
            return self._error(403, "host", "requests must name this machine")
        url = urlparse(self.path)
        if method == "GET" and not url.path.startswith("/api/"):
            return self._static(url.path)
        if method == "GET" and (found := re.fullmatch(r"/api/jobs/([0-9a-f]{16})/events", url.path)):
            return self._events(found.group(1))
        if method == "GET" and url.path == "/api/docs/asset":
            return self._asset(parse_qs(url.query))
        body = {}
        if method in ("POST", "PUT"):
            # A custom header and a JSON body: a cross-site form or a simple request cannot carry both.
            if self.headers.get("X-Aeion") != "1" or "application/json" not in (self.headers.get("Content-Type") or ""):
                return self._error(403, "csrf", "writes need the X-Aeion header and a JSON body")
            length, refused = agents.content_length(self.headers, MAX_BODY)
            if refused:
                return self._error(refused, "length", "the body needs a Content-Length of at most 2 MB")
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return self._error(400, "json", "the body is not JSON")
            if not isinstance(body, dict):
                return self._error(400, "json", "the body is not a JSON object")
        for verb, pattern, function in ROUTES:
            found = pattern.match(url.path)
            if verb == method and found:
                try:
                    return self._send(200, function(self.app, body, parse_qs(url.query), **found.groupdict()))
                except StoreError as error:
                    return self._error(404 if str(error) == "not found" else 400, "refused", str(error))
                except llm.LLMError as error:
                    return self._error(502, error.code, error.message)
                except Exception:  # logged server-side, never sent to the page
                    traceback.print_exc()
                    return self._error(500, "server", "unexpected server error (see the server log)")
        return self._error(404, "not_found", "no such route")

    def _static(self, path):
        if path in ("/", "/index.html"):
            return self._send(200, (WEB / "index.html").read_bytes(), "text/html; charset=utf-8",
                              [("Content-Security-Policy", PAGE_POLICY), ("X-Frame-Options", "DENY")])
        name = path.removeprefix("/static/")
        if name in STATIC:
            return self._send(200, (WEB / name).read_bytes(), STATIC[name])
        return self._error(404, "not_found", "no such file")

    def _asset(self, query):
        try:
            data = self.app.corpus.asset(query.get("root", [""])[0], query.get("path", [""])[0])
        except KeyError:
            return self._error(404, "not_found", "no such diagram")
        self._send(200, data, "image/svg+xml", [("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'")])

    def _events(self, name):
        work = self.app.jobs.get(name)
        if work is None:
            return self._error(404, "not_found", "no such job")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        sent = 0
        try:
            while True:
                with work["condition"]:
                    while sent == len(work["events"]) and not work["done"]:
                        if not work["condition"].wait(timeout=15):
                            break
                    events, finished = work["events"][sent:], work["done"]
                if not events and not finished:
                    self.wfile.write(b": keep-alive\n\n")
                for event in events:
                    self.wfile.write(f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8"))
                sent += len(events)
                self.wfile.flush()
                if finished and sent == len(work["events"]):
                    return
        except (BrokenPipeError, ConnectionResetError):
            return


def serve(settings=None):
    try:
        app = App(settings)
    except config.ConfigError as error:
        raise SystemExit(f"aeion-core: {error}") from None
    if not config.loopback(app.settings.host):
        raise SystemExit(f"aeion-core: {app.settings.host} is not a loopback address; aeion-core serves this machine only")
    Handler.app = app
    server = ThreadingHTTPServer((app.settings.host, app.settings.port), Handler)
    server.daemon_threads = True
    state = "ready, Flue agents, reasoning max" if app.client.ready else f"NOT READY: {app.client.problem}"
    print(f"aeion-core {VERSION}: http://{app.settings.host}:{app.settings.port}  model {app.settings.model} ({state}); "
          f"workspace {app.settings.data}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
