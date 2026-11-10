# Spec: knowledge/components/aeion-engine.md
"""Shared test fixtures: settings on a temporary workspace, the mock agents, and a scripted
OpenAI-compatible upstream that records what it receives."""
import json
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from aeion import agents, config, llm  # noqa: E402
from aeion.store import Store  # noqa: E402


def settings(root, observability=None, url="http://127.0.0.1:9/v1/chat/completions"):
    return config.Settings(root=config.ROOT, data=Path(root) / "workspace",
                           observability=Path(observability or Path(root) / "no-observability"),
                           provider="mock", url=url, model="deepseek-v4.1-flash", host="127.0.0.1", port=0)


class Workspace:
    """A temporary workspace with a store, settings and mock agents; removed on close."""

    def __init__(self, observability=None):
        self.folder = Path(tempfile.mkdtemp(prefix="aeion-test-"))
        self.settings = settings(self.folder, observability)
        self.store = Store(self.settings.data)
        self.agents = agents.MockAgents(llm.Meter())

    def close(self):
        shutil.rmtree(self.folder, ignore_errors=True)


def events():
    """A recorder for job events."""
    seen = []
    return seen, seen.append


class Upstream:
    """A scripted chat-completions endpoint: each reply is a list of SSE `data` objects; requests are kept."""

    def __init__(self, replies, status=200):
        self.replies, self.requests, self.headers, self.status = list(replies), [], [], status
        upstream = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
                upstream.requests.append(body)
                upstream.headers.append(self.headers)  # case-insensitive lookups
                if upstream.status != 200:
                    data = json.dumps({"error": {"message": "scripted refusal"}}).encode()
                    self.send_response(upstream.status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                chunks = upstream.replies.pop(0) if upstream.replies else [text_chunk("(no script left)"), finish("stop")]
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for chunk in chunks:
                    self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                    self.wfile.flush()
                self.wfile.write(b"data: [DONE]\n\n")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1/chat/completions"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def _chunk(delta, finish_reason=None):
    return {"id": "chatcmpl-test", "object": "chat.completion.chunk", "created": 0, "model": "deepseek-v4.1-flash",
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}]}


def text_chunk(text):
    return _chunk({"role": "assistant", "content": text})


def tool_chunk(name, arguments, call_id="call_1"):
    return _chunk({"role": "assistant", "tool_calls": [{"index": 0, "id": call_id, "type": "function",
                                                        "function": {"name": name, "arguments": json.dumps(arguments)}}]})


def finish(reason, prompt=100, completion=20, cost=0.0001):
    chunk = _chunk({}, reason)
    chunk["usage"] = {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion,
                      "opencode": {"list_cost": cost}}
    return chunk
