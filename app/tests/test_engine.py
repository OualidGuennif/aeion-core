# Spec: knowledge/components/aeion-engine.md
"""The engine's boundaries: names never become paths unchecked, Markdown never emits unsafe HTML, the
server answers this machine only, refuses foreign hosts, cross-site writes and unbounded bodies, and
nothing it returns carries the key."""
import http.client
import json
import os
import secrets
import socket
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

from support import Workspace
from aeion import agents, config, llm, markdown, server
from aeion.store import StoreError


def start(app, setup=None):
    """The app's server on a free loopback port; `setup` may rewrite each request's peer address."""
    members = {"app": app} | ({"setup": setup} if setup else {})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), type("TestHandler", (server.Handler,), members))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def raw_status(port, head):
    """Send raw request bytes and return the status code, for headers http.client would correct."""
    with socket.create_connection(("127.0.0.1", port), timeout=10) as connection:
        connection.sendall(head)
        return int(connection.recv(65536).split(b" ", 2)[1])


def write_head(port, length, body=b"{}"):
    return (f"POST /api/features HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nX-Aeion: 1\r\nContent-Type: application/json\r\n"
            f"Content-Length: {length}\r\n\r\n").encode() + body


class ConfigTests(unittest.TestCase):
    def test_the_server_refuses_a_host_off_loopback(self):
        for host in ("0.0.0.0", "192.168.1.29", "::", "example.com", ""):
            with mock.patch.dict(os.environ, {"AEION_HOST": host}), self.assertRaises(config.ConfigError, msg=host):
                config.load()
        for host in ("127.0.0.1", "127.0.0.2", "::1", "localhost"):
            with mock.patch.dict(os.environ, {"AEION_HOST": host}):
                self.assertEqual(config.load().host, host)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.ws = Workspace()

    def tearDown(self):
        self.ws.close()

    def test_names_that_could_leave_the_workspace_are_refused(self):
        for name in ("../x", "a/b", "A", "", "x" * 81, ".hidden", "a\x00b"):
            with self.assertRaises(StoreError, msg=name):
                self.ws.store.path("sessions", name, ".json")

    def test_a_saved_feature_reads_back_with_its_metadata(self):
        meta = self.ws.store.save_feature("Digest", "# Digest\n", "brief", "test")
        read, text = self.ws.store.feature(meta["id"])
        self.assertEqual((read["title"], text, read["bytes"]), ("Digest", "# Digest\n", 9))
        with self.assertRaises(StoreError):
            self.ws.store.save_feature("x", "y", "unknown-kind", "test")


class MarkdownTests(unittest.TestCase):
    def test_html_is_escaped_and_unsafe_links_are_dropped(self):
        html, _ = markdown.render("<script>alert(1)</script>\n\n[x](javascript:alert(1)) [y](https://example.com)")
        self.assertNotIn("<script>", html)
        self.assertNotIn("javascript:", html)
        self.assertIn('href="https://example.com"', html)

    def test_a_rewritten_link_is_checked_before_rewriting(self):
        html, _ = markdown.render("[x](javascript:alert(1))", link=lambda href: "#/docs/safe")
        self.assertNotIn("#/docs/safe", html)


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ws = Workspace()
        cls.app = server.App(cls.ws.settings, client=cls.ws.agents)
        cls.httpd, cls.port = start(cls.app)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.ws.close()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        connection.request(method, path, body=body, headers={"Host": f"127.0.0.1:{self.port}", **(headers or {})})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()

    def test_a_foreign_host_is_refused(self):
        status, _, _ = self.request("GET", "/api/status", headers={"Host": "evil.example"})
        self.assertEqual(status, 403)

    def test_a_write_without_the_custom_header_is_refused(self):
        status, _, _ = self.request("POST", "/api/brainstorms", json.dumps({"idea": "x"}), {"Content-Type": "application/json"})
        self.assertEqual(status, 403)
        status, _, _ = self.request("POST", "/api/brainstorms", "idea=x", {"X-Aeion": "1", "Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(status, 403)

    def test_the_page_carries_a_strict_content_security_policy(self):
        status, headers, _ = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Frame-Options"], "DENY")

    def test_status_reports_readiness_without_secrets(self):
        status, _, body = self.request("GET", "/api/status")
        value = json.loads(body)
        self.assertEqual((status, value["ready"], value["reasoning"]), (200, True, "max"))
        self.assertNotIn("OPENCODE_API_KEY=", body.decode())

    def test_an_unknown_session_is_not_found(self):
        status, _, body = self.request("GET", "/api/sessions/does-not-exist")
        self.assertEqual(status, 404)
        self.assertNotIn("Traceback", body.decode())

    def test_a_peer_on_another_machine_is_refused(self):
        def setup(handler):
            server.Handler.setup(handler)
            handler.client_address = ("192.168.1.29", 50000)
        httpd, port = start(self.app, setup)
        try:
            self.assertEqual(raw_status(port, f"GET /api/status HTTP/1.1\r\nHost: localhost\r\n\r\n".encode()), 403)
            feature = b'{"markdown": "# From the network"}'
            self.assertEqual(raw_status(port, write_head(port, len(feature), feature)), 403)
        finally:
            httpd.shutdown()
            httpd.server_close()
        self.assertEqual(self.ws.store.features(), [])

    def test_a_body_length_that_is_not_a_bounded_number_is_refused(self):
        self.assertEqual(raw_status(self.port, write_head(self.port, -1)), 400)
        self.assertEqual(raw_status(self.port, write_head(self.port, "abc")), 400)
        self.assertEqual(raw_status(self.port, write_head(self.port, 3 * 1024 * 1024)), 413)
        self.assertEqual(self.ws.store.features(), [])


class KeyTests(unittest.TestCase):
    def test_no_response_carries_the_key(self):
        sentinel = "sk-sentinel-" + secrets.token_hex(12)
        ws = Workspace()
        with mock.patch.dict(os.environ, {"OPENCODE_API_KEY": sentinel}):
            client = agents.Agents(ws.settings, llm.Meter())
        self.assertEqual(client._key, sentinel)  # the real client holds the key, so its absence below means something
        httpd, port = start(server.App(ws.settings, client=client))
        try:
            seen = []
            for path in ("/", "/static/app.js", "/api/status", "/api/sessions", "/api/sessions/nope", "/api/features",
                         "/api/features/nope", "/api/catalog", "/api/studio", "/api/studio/nope", "/api/docs/tree",
                         "/api/docs/search?q=key", "/api/docs/page?root=x&path=y", "/api/nope"):
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                connection.request("GET", path, headers={"Host": f"127.0.0.1:{port}"})
                response = connection.getresponse()
                seen.append((path, response.status, str(response.getheaders()) + response.read().decode()))
            for path, body in (("/api/docs/ask", {}), ("/api/features", {"title": "x"}), ("/api/nope", {})):
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                connection.request("POST", path, body=json.dumps(body), headers={"Host": f"127.0.0.1:{port}", "X-Aeion": "1",
                                                                                 "Content-Type": "application/json"})
                response = connection.getresponse()
                seen.append((path, response.status, str(response.getheaders()) + response.read().decode()))
        finally:
            httpd.shutdown()
            httpd.server_close()
            ws.close()
        self.assertEqual(len(seen), 17)
        for path, status, text in seen:
            self.assertNotIn(sentinel, text, f"{path} ({status})")


if __name__ == "__main__":
    unittest.main()
