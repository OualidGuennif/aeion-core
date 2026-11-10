# Spec: knowledge/components/aeion-agents.md
"""The agent contract: typed submissions, the gateway relay and bridge, and one real `flue run` against a
scripted upstream proving that each piece of input reaches the model exactly once, at maximum reasoning."""
import json
import shutil
import unittest
import urllib.error
import urllib.request

from support import Upstream, finish, text_chunk, tool_chunk  # noqa: F401  (support sets the import path)
from aeion import agents, config, llm

SCHEMA = {"type": "object", "required": ["items"], "additionalProperties": False,
          "properties": {"items": {"type": "array", "maxItems": 3, "items": {"type": "string", "maxLength": 20}}}}


def post(url, body, token):
    request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


class SubmitTests(unittest.TestCase):
    def run_with(self, check=None, attempts=4):
        return agents.Run(token="t", agent="analyst", session="s", submits={"submit": agents.Submit("submit", SCHEMA, check, attempts)})

    def test_schema_refusal_names_the_field_and_records_nothing(self):
        run = self.run_with()
        with self.assertRaises(agents.ToolRefused) as caught:
            run.call("submit", {"items": ["x" * 30]})
        self.assertIn("/items/0", str(caught.exception))
        self.assertEqual(run.submissions, {})

    def test_clean_value_is_accepted_and_ends_the_turn(self):
        output, terminate = self.run_with(check=lambda v: []).call("submit", {"items": ["a"]})
        self.assertEqual((output, terminate), ("Accepted.", True))

    def test_failing_checks_are_returned_until_the_attempts_run_out(self):
        run = self.run_with(check=lambda v: ["G07 MISSING_TEST on r1"], attempts=2)
        output, terminate = run.call("submit", {"items": ["a"]})
        self.assertFalse(terminate)
        self.assertIn("G07 MISSING_TEST on r1", output)
        output, terminate = run.call("submit", {"items": ["b"]})
        self.assertTrue(terminate)
        self.assertEqual(run.submissions["submit"], {"items": ["b"]})
        self.assertEqual(run.state["submit:problems"], ["G07 MISSING_TEST on r1"])

    def test_a_block_that_repeats_the_message_is_refused(self):
        message = "Review this feature concept. " * 10
        with self.assertRaises(ValueError):
            agents.single_payload(message, [{"tag": "feature_concept", "body": "Header\n" + message}])
        with self.assertRaises(ValueError):
            agents.single_payload("yes", [{"tag": "note", "body": "yes"}])
        agents.single_payload(message, [{"tag": "conversation", "body": "Owner: " + message}])
        mock = agents.MockAgents()
        with self.assertRaises(ValueError):
            mock.run("goldfish", "same text", blocks=[{"tag": "document", "body": "same text"}])
        self.assertEqual(mock.calls, [])

    def test_an_undeclared_tool_is_refused(self):
        with self.assertRaises(agents.ToolRefused):
            self.run_with().call("delete_everything", {})


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.upstream = Upstream([[text_chunk("hello"), finish("stop", 120, 30, 0.0002)]])
        self.meter = llm.Meter()
        self.gateway = agents.Gateway(self.upstream.url, "secret-key", "deepseek-v4.1-flash", self.meter, user_agent="aeion-core/test")
        self.base = self.gateway.start()
        self.run = agents.Run(token="run-token", agent="goldfish", session="aeion-core-s1",
                              tools={"echo": lambda data, run: {"echo": data["word"]}})
        self.gateway.register(self.run)

    def tearDown(self):
        self.gateway.stop()
        self.upstream.close()

    def test_relay_adds_the_key_and_provider_headers_and_meters_usage(self):
        status, body = post(f"{self.base}/v1/chat/completions", {"model": "deepseek-v4.1-flash", "messages": [], "stream": True}, "run-token")
        self.assertEqual(status, 200)
        self.assertIn(b"hello", body)
        headers = self.upstream.headers[0]
        self.assertEqual(headers["Authorization"], "Bearer secret-key")
        self.assertEqual(headers["x-opencode-session"], "aeion-core-s1")
        self.assertEqual(headers["User-Agent"], "aeion-core/test")
        self.assertEqual(self.run.usage["input"], 120)
        self.assertEqual(self.meter.snapshot()["estimated_usd"], 0.0002)

    def test_unknown_token_and_other_model_are_refused_before_the_upstream(self):
        self.assertEqual(post(f"{self.base}/v1/chat/completions", {"model": "deepseek-v4.1-flash"}, "nope")[0], 401)
        self.assertEqual(post(f"{self.base}/v1/chat/completions", {"model": "other-model"}, "run-token")[0], 400)
        self.assertEqual(self.upstream.requests, [])

    def test_bridge_runs_a_registered_tool_and_reports_refusals(self):
        status, body = post(f"{self.base}/bridge/tool", {"name": "echo", "input": {"word": "hi"}}, "run-token")
        self.assertEqual((status, json.loads(body)["output"]), (200, {"echo": "hi"}))
        status, body = post(f"{self.base}/bridge/tool", {"name": "missing", "input": {}}, "run-token")
        self.assertIn("not available", json.loads(body)["error"])

    def test_the_key_never_appears_in_a_refusal(self):
        failing = Upstream([], status=403)
        gateway = agents.Gateway(failing.url, "secret-key", "deepseek-v4.1-flash", llm.Meter())
        base = gateway.start()
        gateway.register(self.run)
        try:
            status, body = post(f"{base}/v1/chat/completions", {"model": "deepseek-v4.1-flash"}, "run-token")
            self.assertEqual(status, 403)
            self.assertNotIn(b"secret-key", body)
        finally:
            gateway.stop()
            failing.close()


HARNESS = (agents.FLUE / "node_modules" / ".bin" / "flue").exists() and shutil.which("node")


@unittest.skipUnless(HARNESS, "the Flue harness is not installed (npm ci in app/flue)")
class FlueRunTests(unittest.TestCase):
    """The real CLI and runtime, a scripted upstream: one consolidator run that submits findings."""

    def test_each_input_reaches_the_model_once_and_the_submission_is_validated(self):
        findings = {"findings": [{"title": "No refusal path", "severity": "Major", "reviewer": "egm-design",
                                  "scope": "lines 1-4", "description": "Nothing says what fails.", "recommendation": "Add one."}]}
        upstream = Upstream([[tool_chunk("submit_findings", findings), finish("tool_calls")]])
        root = config.ROOT
        settings = config.Settings(root=root, data=root / "workspace", observability=root, provider="flue", url=upstream.url,
                                   model="deepseek-v4.1-flash", host="127.0.0.1", port=0)
        runner = agents.Agents(settings, llm.Meter())
        runner._key = "test-key"
        runner.gateway = agents.Gateway(upstream.url, "test-key", settings.model, runner.meter)
        from aeion import goldfish
        report = "UNIQUE-REPORT-MARKER: the design never says what happens on failure."
        message = "Consolidate the attached Goldfish reports of this stage into findings."
        try:
            result = runner.run("consolidator", message,
                                blocks=[{"tag": "goldfish_reports", "body": report}],
                                submits=[agents.Submit("submit_findings", goldfish.FINDINGS)], require="submit_findings",
                                record=True, timeout=180)
        finally:
            runner.gateway.stop()
            upstream.close()
        self.assertEqual(result.submissions["submit_findings"], findings)
        first = json.dumps(upstream.requests[0])
        self.assertEqual(first.count("UNIQUE-REPORT-MARKER"), 1)
        self.assertEqual(first.count(message), 1)
        self.assertEqual(upstream.requests[0]["reasoning_effort"], "max")
        self.assertEqual(upstream.requests[0]["thinking"], {"type": "enabled"})
        tool = next(t["function"] for t in upstream.requests[0]["tools"] if t["function"]["name"] == "submit_findings")
        # Typed parameters, not a free object: nested fields are arrays and enums, never JSON-encoded strings.
        findings_schema = tool["parameters"]["properties"]["findings"]
        self.assertEqual(findings_schema["type"], "array")
        self.assertEqual(findings_schema["items"]["properties"]["severity"]["enum"], ["Blocker", "Major", "Nit"])
        self.assertNotIn('"title"', tool["description"])  # the schema is sent once, as parameters
        # An accepted submission ends the turn: no further model call.
        self.assertEqual(len(upstream.requests), 1)
        self.assertEqual(result.text, "")


if __name__ == "__main__":
    unittest.main()
