# Spec: knowledge/components/aeion-engine.md
"""The engine's boundaries: names never become paths unchecked, Markdown never emits unsafe HTML, the
server refuses foreign hosts and cross-site writes, and nothing it returns carries the key."""
import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from support import Workspace
from aeion import markdown, server
from aeion.store import StoreError


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
        app = server.App(cls.ws.settings, client=cls.ws.agents)
        handler = type("TestHandler", (server.Handler,), {"app": app})
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.port = cls.httpd.server_address[1]

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


if __name__ == "__main__":
    unittest.main()
