# Spec: knowledge/components/aeion-agents.md
"""Model work runs as Flue agents (app/flue/src/agents), one `flue run` per turn, each a disposable
conversation. This module is the server side of that contract:

- the gateway, a loopback HTTP server, relays the agents' chat requests to OpenCode with the key, the
  User-Agent and a stable session header the provider requires, meters the usage the stream reports,
  and serves the agents' tools (search, graph, typed submissions) from this process;
- the launcher writes one input file, starts the CLI with the turn's message bound to --message, reads
  the agent's event file as it streams and returns the final reply and any accepted submission.

The message and the input file never carry the same text: duplicated payloads cost tokens and confuse
the model. The key never reaches the agent process; it only holds a per-run token for the gateway."""
import collections
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import VERSION, config
from .llm import LLMError, Meter, tls_context
from schema import Validator  # noqa: E402  (config put the template's tools/axiom on the import path)

FLUE = Path(__file__).resolve().parents[1] / "flue"
UPSTREAM = Path(__file__).resolve().parent / "goldfish" / "upstream"
AGENTS = ("elephant", "goldfish", "synthesizer", "consolidator", "drafter", "reconciler", "resolver", "analyst",
          "patcher", "discussant", "illustrator", "librarian")
MODELS = {"deepseek-v4.1-flash": {"id": "deepseek-v4.1-flash", "name": "DeepSeek V4.1 Flash", "context": 1_000_000,
                                  "input": 0.30, "output": 1.20, "cacheRead": 0.006}}
MAX_BODY = 16 * 1024 * 1024
TOOL_CALLS = 12  # per server tool and run: enough for research, a stop for loops


class ToolRefused(Exception):
    """A tool call the model must correct: the message goes back to it as the tool's error."""


@dataclass
class Submit:
    """A typed result: schema-valid, then the deterministic checks; up to `attempts` corrections. An amending
    submit (`target` set) carries only the parts that change: `combine(current, amendment)` folds it into the
    target's last recorded value, which is then validated and checked as a whole, so a fix costs a few items."""
    name: str
    schema: dict
    check: object = None  # value -> list of problems the model can fix; empty when clean
    attempts: int = 4
    target: str = None
    combine: object = None


@dataclass
class Run:
    token: str
    agent: str
    session: str
    tools: dict = field(default_factory=dict)
    submits: dict = field(default_factory=dict)
    record: bool = False
    submissions: dict = field(default_factory=dict)
    state: dict = field(default_factory=dict)
    requests: list = field(default_factory=list)
    usage: dict = field(default_factory=lambda: {"calls": 0, "input": 0, "output": 0, "reasoning": 0, "cost": 0.0})
    finishes: list = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def call(self, name, data):
        """One tool call from the agent: a typed submission or a server tool. Returns (output, terminate)."""
        if not isinstance(data, dict):
            raise ToolRefused("the tool input must be a JSON object")
        if name in self.submits:
            return self._submit(self.submits[name], data)
        if name not in self.tools:
            raise ToolRefused(f"{name} is not available to this agent")
        with self.lock:
            used = self.state.setdefault(f"{name}:calls", 0) + 1
            self.state[f"{name}:calls"] = used
        if used > TOOL_CALLS:
            raise ToolRefused(f"{name} was already called {TOOL_CALLS} times in this run: use what it returned")
        output = self.tools[name](data, self)
        return (output, False) if not isinstance(output, tuple) else output

    def _submit(self, spec, data):
        # Steps: strict schema; an amendment folded into the recorded value; the checks; a clean value ends the turn.
        errors = Validator(spec.schema).errors(data)
        if errors:
            listed = "; ".join(f"{p or '/'}: {m}" for p, m in errors[:8])
            raise ToolRefused(f"refused, the value does not match the shape: {listed}")
        if spec.target:
            whole = self.submits[spec.target]
            current = self.submissions.get(spec.target)
            if current is None:
                raise ToolRefused(f"nothing to amend yet: call {spec.target} with the complete value first")
            data = spec.combine(current, data)
            errors = Validator(whole.schema).errors(data)
            if errors:
                listed = "; ".join(f"{p or '/'}: {m}" for p, m in errors[:8])
                raise ToolRefused(f"refused, the amended value does not match the shape: {listed}")
            spec = whole
        with self.lock:
            tries = self.state.setdefault(f"{spec.name}:tries", 0) + 1
            self.state[f"{spec.name}:tries"] = tries
        problems = list(spec.check(data)) if spec.check else []
        with self.lock:
            self.submissions[spec.name] = data
            self.state[f"{spec.name}:problems"] = problems
        if not problems:
            return "Accepted.", True
        if tries >= spec.attempts:
            return f"Recorded with {len(problems)} open problem(s); the owner will see them. Stop now.", True
        listed = "\n".join(f"- {p}" for p in problems[:12])
        amend = next((s.name for s in self.submits.values() if s.target == spec.name), None)
        how = (f"call {amend} with only the items that change (same keys replace, new keys add, `remove` drops keys)"
               if amend else f"call {spec.name} again with the complete value")
        return (f"Recorded, but these deterministic checks fail:\n{listed}\nFix them: {how} "
                f"({spec.attempts - tries} attempt(s) left). Problems only the owner can settle "
                f"(open decisions, unvalidated assumptions) are not listed."), False


@dataclass
class Result:
    text: str
    submissions: dict
    state: dict
    usage: dict
    requests: list
    seconds: float


class Gateway:
    """The loopback endpoint for every agent run: /v1/chat/completions (relay) and /bridge/tool (tools)."""

    def __init__(self, url, key, model, meter, user_agent=None):
        self.upstream, self._key, self.model, self.meter = url, key, model, meter
        self.user_agent = user_agent or f"aeion-core/{VERSION}"
        self.runs, self.lock, self.server = {}, threading.Lock(), None

    def start(self):
        with self.lock:
            if self.server is None:
                gateway = self

                class Handler(_GatewayHandler):
                    owner = gateway
                self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
                self.server.daemon_threads = True
                threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None

    def register(self, run):
        with self.lock:
            self.runs[run.token] = run

    def unregister(self, run):
        with self.lock:
            self.runs.pop(run.token, None)

    def find(self, header):
        token = (header or "").removeprefix("Bearer ").strip()
        with self.lock:
            return self.runs.get(token) if token else None

    def forward(self, run, body, write):
        """Relay one chat request; returns after the stream ends. LLMError for a refusal or failure upstream."""
        request = urllib.request.Request(self.upstream, data=json.dumps(body).encode("utf-8"), method="POST", headers={
            "Content-Type": "application/json", "Accept": "text/event-stream", "User-Agent": self.user_agent,
            "x-opencode-session": run.session, "Authorization": f"Bearer {self._key}"})
        usage, finish = {}, None
        with urllib.request.urlopen(request, timeout=900, context=tls_context()) as response:
            for raw in response:
                write(raw)
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:") or line[5:].strip() == "[DONE]":
                    continue
                try:
                    event = json.loads(line[5:])
                except ValueError:
                    continue
                usage = event.get("usage") or usage
                for choice in event.get("choices") or []:
                    finish = choice.get("finish_reason") or finish
        self.meter.add(usage)
        details = usage.get("completion_tokens_details") or {}
        cost = (usage.get("opencode") or {}).get("list_cost")
        with run.lock:
            run.usage["calls"] += 1
            run.usage["input"] += int(usage.get("prompt_tokens") or 0)
            run.usage["output"] += int(usage.get("completion_tokens") or 0)
            run.usage["reasoning"] += int(details.get("reasoning_tokens") or 0)
            run.usage["cost"] += float(cost) if isinstance(cost, (int, float)) else 0.0
            run.finishes.append(finish)


class _GatewayHandler(BaseHTTPRequestHandler):
    owner = None
    protocol_version = "HTTP/1.0"

    def log_message(self, form, *args):
        pass

    def _json(self, status, value):
        data = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        # Steps: the caller's run by its token, a bounded JSON body, then the relay or the bridge.
        run = self.owner.find(self.headers.get("Authorization"))
        if run is None:
            return self._json(401, {"error": {"message": "unknown run token"}})
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self._json(413, {"error": {"message": "request too large"}})
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json(400, {"error": {"message": "the body is not JSON"}})
        if self.path == "/v1/chat/completions":
            return self._relay(run, body)
        if self.path == "/bridge/tool":
            return self._tool(run, body)
        return self._json(404, {"error": {"message": "no such route"}})

    def _relay(self, run, body):
        if body.get("model") != self.owner.model:
            return self._json(400, {"error": {"message": f"this gateway serves {self.owner.model} only"}})
        if run.record:
            with run.lock:
                run.requests.append(json.loads(json.dumps(body)))
        started = []

        def write(raw):
            if not started:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                started.append(True)
            self.wfile.write(raw)
            self.wfile.flush()
        try:
            self.owner.forward(run, body, write)
        except urllib.error.HTTPError as error:
            message = _provider_message(error)
            if not started:
                return self._json(error.code, {"error": {"message": message}})
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            if not started:
                return self._json(502, {"error": {"message": f"upstream unreachable: {str(getattr(error, 'reason', error))[:160]}"}})

    def _tool(self, run, body):
        name = str(body.get("name", ""))
        try:
            output, terminate = run.call(name, body.get("input"))
        except ToolRefused as error:
            # The refusal goes back to the model; one line in the server log says why (no content beyond it).
            print(f"[agent {run.agent}] {name} refused: {str(error)[:300]}", flush=True)
            return self._json(200, {"error": str(error)[:4000]})
        except Exception:  # a server bug reaches the model as a plain refusal, details stay in the log
            import traceback
            traceback.print_exc()
            return self._json(200, {"error": f"{name} failed inside the server"})
        return self._json(200, {"output": output, "terminate": bool(terminate)})


def _provider_message(error):
    try:
        detail = json.loads(error.read().decode("utf-8", errors="replace"))
        return str((detail.get("error") or {}).get("message") or detail)[:300]
    except (ValueError, OSError, AttributeError):
        return str(error.reason)[:300]


class Agents:
    """Starts Flue agents for the sections. `ready` is false without a key, Node or the installed harness."""

    def __init__(self, settings, meter):
        self.settings, self.meter = settings, meter
        self._key = config.api_key(settings.root)
        self.gateway = Gateway(settings.url, self._key, settings.model, meter)
        self.flue = FLUE / "node_modules" / ".bin" / "flue"

    @property
    def ready(self):
        return bool(self._key) and self.flue.exists() and shutil.which("node") is not None

    @property
    def problem(self):
        if not self._key:
            return "no OPENCODE_API_KEY: add it to aeion-core/.env (or app/aeion/.env), then restart"
        if shutil.which("node") is None:
            return "Node.js 22.19 or newer is required for the agents"
        if not self.flue.exists():
            return "the agent harness is not installed: run `npm ci` in app/flue"
        return None

    def run(self, agent, message, *, blocks=(), tools=None, submits=(), require=None, session=None, persona=None,
            on_text=None, on_event=None, max_output=32768, timeout=900, record=False):
        """One agent turn. Returns a Result; LLMError when the agent fails, is cut off or skips a required result."""
        if agent not in AGENTS:
            raise ValueError(f"unknown agent {agent!r}")
        if not self.ready:
            raise LLMError("not_ready", self.problem)
        if not message.strip():
            raise ValueError("an agent run needs a message")
        single_payload(message, blocks)
        base = self.gateway.start()
        run = Run(token=secrets.token_urlsafe(24), agent=agent, session=_session(session or agent), tools=dict(tools or {}),
                  submits={s.name: s for s in submits}, record=record)
        scratch = Path(tempfile.mkdtemp(prefix="aeion-agent-"))
        started = time.monotonic()
        try:
            # Steps: one input file (never the message), the event file, an empty .env, then the CLI.
            input_file, events, empty = scratch / "input.json", scratch / "events.ndjson", scratch / "empty.env"
            # Each submit tool's schema travels once, as the tool's parameter schema; never also as prose.
            input_file.write_text(json.dumps({"blocks": list(blocks), "persona": persona,
                                              "schemas": {s.name: s.schema for s in submits}}, ensure_ascii=False))
            events.touch(mode=0o600)
            empty.touch(mode=0o600)
            meta = dict(MODELS.get(self.settings.model) or {**MODELS["deepseek-v4.1-flash"], "id": self.settings.model},
                        maxOutputTokens=max_output)
            env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(scratch), "TMPDIR": str(scratch),
                   "LANG": "C.UTF-8", "NODE_NO_WARNINGS": "1", "AEION_RELAY_URL": f"{base}/v1",
                   "AEION_BRIDGE_URL": f"{base}/bridge", "AEION_RELAY_TOKEN": run.token, "AEION_INPUT": str(input_file),
                   "AEION_EVENTS_FILE": str(events), "AEION_MODEL_JSON": json.dumps(meta), "AEION_UPSTREAM": str(UPSTREAM)}
            self.gateway.register(run)
            # The message is bound to the option, so a message that starts with '-' or '---' is never a flag.
            argv = [str(self.flue), "run", f"src/agents/{agent}.ts", f"--message={message}", "--id",
                    f"{agent}-{secrets.token_hex(6)}", "--new", "--json", "--env", str(empty)]
            process = subprocess.Popen(argv, cwd=FLUE, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, start_new_session=True)
            tail = collections.deque(maxlen=40)
            out = []
            readers = [threading.Thread(target=lambda: tail.extend(l.decode("utf-8", "replace").rstrip() for l in process.stderr), daemon=True),
                       threading.Thread(target=lambda: out.append(process.stdout.read()), daemon=True)]
            for reader in readers:
                reader.start()
            last_turn_text = _follow(events, process, started + timeout, on_text, on_event)
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise LLMError("timeout", f"the {agent} agent did not finish within {timeout} s")
            for reader in readers:
                reader.join(timeout=5)
            envelope = _envelope(b"".join(out))
        finally:
            self.gateway.unregister(run)
            shutil.rmtree(scratch, ignore_errors=True)
        if "length" in run.finishes:
            raise LLMError("truncated", f"the {agent} agent reached its output limit before finishing")
        if envelope.get("outcome") != "completed":
            error = envelope.get("error") or {}
            detail = error.get("message") or (tail[-1] if tail else "no detail")
            raise LLMError("agent", f"the {agent} agent {envelope.get('outcome', 'failed')}: {str(detail)[:300]}")
        if require and require not in run.submissions:
            raise LLMError("contract", f"the {agent} agent finished without an accepted {require}")
        # The envelope joins the text of every model turn; the answer is the last turn's text.
        text = (last_turn_text or str(envelope.get("message") or "")).strip()
        return Result(text=text, submissions=run.submissions, state=run.state,
                      usage=run.usage, requests=run.requests, seconds=round(time.monotonic() - started, 1))


def single_payload(message, blocks):
    """Refuse a run that would send the same text twice: once as the message and again in a block. A
    conversation block may quote an earlier, identical owner message; any other block may not contain a long
    message, and no block may equal it."""
    text = message.strip()
    for block in blocks:
        body = str(block.get("body", "")).strip()
        if body == text or (len(text) >= 200 and block.get("tag") != "conversation" and text in body):
            raise ValueError(f"the message is repeated in the '{block.get('tag')}' block: send it once")


def _session(value):
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]", "-", str(value))[:80]
    return f"aeion-core-{cleaned}"


def _follow(path, process, deadline, on_text, on_event):
    """Read the agent's event file until the process exits (then drain it) or the deadline passes. Text from a
    later model turn replaces what an earlier turn streamed, so a 'restart' event comes first."""
    buffer, text_turn, final = b"", None, []
    with path.open("rb") as stream:
        while True:
            block = stream.read(65536)
            if not block:
                if process.poll() is not None:
                    block = stream.read(65536)
                    if not block:
                        return "".join(final)
                elif time.monotonic() >= deadline:
                    return "".join(final)
                else:
                    time.sleep(0.05)
                    continue
            buffer += block
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if record.get("type") == "text" and record.get("text"):
                    if text_turn is not None and record.get("turn") != text_turn and on_event:
                        on_event({"type": "restart"})
                    if record.get("turn") != text_turn:
                        final.clear()
                    text_turn = record.get("turn")
                    final.append(record["text"])
                    if on_text:
                        on_text(record["text"])
                elif on_event:
                    on_event(record)


def _envelope(stdout):
    for line in reversed(stdout.decode("utf-8", "replace").strip().splitlines()):
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict) and "outcome" in value:
            return value
    return {"outcome": "error", "error": {"message": "the agent printed no result envelope"}}


class MockAgents:
    """Deterministic agents for tests: scripted replies per agent, with their tool calls and submissions
    going through the same Run.call path (schema, deterministic checks) as a real run."""

    ready, problem = True, None

    def __init__(self, meter=None):
        self.meter = meter or Meter()
        self.queue = collections.defaultdict(list)
        self.calls = []
        self.last_outputs = []
        self.lock = threading.Lock()

    def script(self, agent, *replies):
        self.queue[agent].extend(replies)

    def run(self, agent, message, *, blocks=(), tools=None, submits=(), require=None, session=None, persona=None,
            on_text=None, on_event=None, max_output=32768, timeout=900, record=False):
        if agent not in AGENTS:
            raise ValueError(f"unknown agent {agent!r}")
        single_payload(message, blocks)
        run = Run(token="mock", agent=agent, session=_session(session or agent), tools=dict(tools or {}),
                  submits={s.name: s for s in submits})
        with self.lock:
            self.calls.append({"agent": agent, "message": message, "blocks": list(blocks), "persona": persona,
                               "session": session})
            reply = self.queue[agent].pop(0) if self.queue[agent] else {"text": f"Mock {agent} reply."}
        if callable(reply):
            reply = reply(message, list(blocks))
        if isinstance(reply, Exception):
            raise reply
        outputs = []
        for name, data in reply.get("calls", []):
            try:
                outputs.append(run.call(name, data)[0])
            except ToolRefused as error:
                outputs.append(f"ERROR: {error}")
        run.state["outputs"] = outputs
        self.last_outputs = outputs
        text = reply.get("text", "")
        if on_text:
            for start in range(0, len(text), 40):
                on_text(text[start:start + 40])
        self.meter.add({"prompt_tokens": len(message) // 4, "completion_tokens": len(text) // 4})
        if require and require not in run.submissions:
            raise LLMError("contract", f"the {agent} agent finished without an accepted {require}")
        return Result(text=text.strip(), submissions=run.submissions, state=run.state, usage=run.usage, requests=[],
                      seconds=0.0)


def streaming(emit, kind="token"):
    """Callbacks that forward an agent's stream to a job: text chunks, restarts, reasoning progress, tool use."""
    thinking = {"chars": 0, "sent": 0}

    def on_text(chunk):
        emit({"type": kind, "text": chunk})

    def on_event(record):
        if record.get("type") == "restart":
            emit({"type": "restart", "stream": kind})
        elif record.get("type") == "thinking":
            thinking["chars"] += int(record.get("chars") or 0)
            if thinking["chars"] - thinking["sent"] >= 400:
                thinking["sent"] = thinking["chars"]
                emit({"type": "thinking", "chars": thinking["chars"]})
        elif record.get("type") == "tool_start" and record.get("name") not in (None, "other"):
            emit({"type": "agent_tool", "name": record["name"]})
    return {"on_text": on_text, "on_event": on_event}


def client(settings, meter):
    """The configured agents: the mock when AEION_LLM=mock, otherwise Flue."""
    return MockAgents(meter) if settings.provider == "mock" else Agents(settings, meter)
