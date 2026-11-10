# Spec: knowledge/components/aeion-agents.md
"""What the model layer shares: its error type, the cost meter, TLS trust for the gateway's upstream
calls. Model work itself runs as Flue agents (agents.py); every value an agent
returns is data, validated against these schemas before anything uses it."""
import functools
import os
import ssl
import threading
from dataclasses import dataclass, field

# System CA bundles, for a Python build that ships without one (python.org on macOS). Verification stays on.
CA_BUNDLES = ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt")


@functools.lru_cache(maxsize=1)
def tls_context():
    """Python's default trust store when it has one, otherwise the first system bundle found."""
    paths = ssl.get_default_verify_paths()
    configured = any(os.path.exists(p) for p in (paths.cafile, paths.capath) if p)
    if configured or os.environ.get("SSL_CERT_FILE") or os.environ.get("SSL_CERT_DIR"):
        return ssl.create_default_context()
    for bundle in CA_BUNDLES:
        if os.path.exists(bundle):
            return ssl.create_default_context(cafile=bundle)
    return ssl.create_default_context()


class LLMError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(f"{code}: {message}")
        self.code, self.message = code, message


@dataclass
class Meter:
    """Calls, tokens and cost since the server started; shared across threads. OpenCode reports each
    call's list cost; the estimate from the price table is used only when a call did not report one."""
    price: tuple = (0.0, 0.0)
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    reported_usd: float = 0.0
    reported_calls: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self, usage):
        with self.lock:
            self.calls += 1
            self.input_tokens += int(usage.get("prompt_tokens") or 0)
            self.output_tokens += int(usage.get("completion_tokens") or 0)
            reported = (usage.get("opencode") or {}).get("list_cost")
            if isinstance(reported, (int, float)):
                self.reported_usd += float(reported)
                self.reported_calls += 1

    def snapshot(self):
        with self.lock:
            cost = (self.input_tokens * self.price[0] + self.output_tokens * self.price[1]) / 1_000_000
            if self.calls and self.reported_calls == self.calls:
                cost = self.reported_usd
            return {"calls": self.calls, "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                    "estimated_usd": round(cost, 4)}
