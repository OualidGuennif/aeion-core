# Spec: knowledge/components/aeion-engine.md
"""Settings from the environment, with safe local defaults. The API key is read from the process
environment or from one line of the project's .env, and is never printed, logged or returned."""
import ipaddress
import os
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/axiom"))
DEFAULT_URL = "https://opencode.ai/inference/go/openai/v1/chat/completions"
DEFAULT_MODEL = "deepseek-v4.1-flash"
# USD per million tokens for the default model (OpenCode Go list price, 2026-11).
PRICES = {"deepseek-v4.1-flash": (0.30, 1.20)}


@dataclass(frozen=True)
class Settings:
    root: Path
    data: Path
    observability: Path
    provider: str
    url: str
    model: str
    host: str
    port: int

    @property
    def price(self):
        return PRICES.get(self.model, (0.0, 0.0))


class ConfigError(ValueError):
    """A setting the server refuses to start with."""


def loopback(host):
    """True for localhost and loopback addresses (IPv4-mapped included); nothing is resolved."""
    if host.lower() == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return address.is_loopback or bool(getattr(address, "ipv4_mapped", None) and address.ipv4_mapped.is_loopback)


def load():
    """The effective settings; nothing here reads the key. The server answers this machine only."""
    env = os.environ
    host = env.get("AEION_HOST", "127.0.0.1")
    if not loopback(host):
        raise ConfigError(f"AEION_HOST={host} is not a loopback address: aeion-core serves this machine only "
                          "(use 127.0.0.1, ::1 or localhost)")
    return Settings(root=ROOT, data=Path(env.get("AEION_DATA", ROOT / "workspace")).resolve(),
                    observability=Path(env.get("AEION_OBSERVABILITY", ROOT.parent / "aeion-observability")).resolve(),
                    provider=env.get("AEION_LLM", "flue"), url=env.get("AEION_LLM_URL", DEFAULT_URL),
                    model=env.get("AEION_MODEL", DEFAULT_MODEL), host=host,
                    port=int(env.get("AEION_PORT", "8765")))


ENV_FILES = (Path(".env"), Path("app/aeion/.env"))


def api_key(root=ROOT):
    """OPENCODE_API_KEY from the environment, else from its own line in <root>/.env or app/aeion/.env."""
    value = os.environ.get("OPENCODE_API_KEY")
    if value:
        return value.strip()
    for relative in ENV_FILES:
        try:
            lines = (Path(root) / relative).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        # Only this one variable is read; every other line of the file is ignored.
        for line in lines:
            name, _, rest = line.strip().partition("=")
            if name.strip().removeprefix("export ").strip() == "OPENCODE_API_KEY":
                found = rest.strip().strip('"').strip("'")
                if found:
                    return found
    return None
