# Spec: knowledge/components/axiom-toolkit.md
"""What every axiom command shares: the project layout, the AxiomSpec digest and atomic writes.

Nothing here reads the clock, the network or a model; paths are always project-relative."""
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

TOOL_VERSION = "3.0.0"
ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = Path("knowledge/axiomspec/AxiomSpec/schemas")
SPEC_PATH = Path("knowledge/spec/spec.json")
VIEW_CATALOG = Path("docs/view-catalog.json")
FEATURE_CATALOG = Path("docs/feature-catalog.json")
GENERATED = Path("docs/generated")
COCKPIT = Path("docs/README.md")
EVIDENCE_DIR = Path("knowledge/spec/evidence")
GRAPH_DIR = Path(".aeion/graph")
ID_PATTERN = r"^[A-Z][A-Z0-9_]*-[0-9]{3,6}$"
CANONICAL_PREFIXES = ("GOAL", "TERM", "REQ", "CON", "MODEL", "SCN", "TEST", "COMP", "DEC", "ASM", "RISK", "CTRL")

sys.path.insert(0, str(ROOT / ".claude/hooks"))
from project_files import SKIPPED_FILES, export_ignored, inside, nested_projects, project_files  # noqa: E402,F401
from secret_names import is_secret  # noqa: E402,F401


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical_bytes(value):
    """AX-G-008: sorted ASCII keys, array order kept, minimal integers, short escapes, raw UTF-8 otherwise.

    Depth is bounded by the strict loader (128), so recursion cannot exhaust the stack."""
    return _canonical(value).encode("utf-8")


def _canonical(item):
    if isinstance(item, dict):
        return "{" + ",".join(_string(key) + ":" + _canonical(item[key]) for key in sorted(item)) + "}"
    if isinstance(item, list):
        return "[" + ",".join(_canonical(element) for element in item) + "]"
    return _scalar(item)


SHORT = {"\b": "\\b", "\t": "\\t", "\n": "\\n", "\f": "\\f", "\r": "\\r", '"': '\\"', "\\": "\\\\"}


def _string(text):
    # Other controls take lowercase \u00xx; every other scalar, including / and U+2028/2029, stays raw.
    escaped = "".join(SHORT.get(c) or (f"\\u{ord(c):04x}" if ord(c) < 0x20 else c) for c in text)
    return '"' + escaped + '"'


def _scalar(item):
    if item is True:
        return "true"
    if item is False:
        return "false"
    if item is None:
        return "null"
    if type(item) is int:
        return str(item)
    if isinstance(item, str):
        return _string(item)
    raise ValueError(f"not canonical JSON: {type(item).__name__}")


def canonical_digest(value):
    return sha256(canonical_bytes(value))


def pretty(value):
    """Stable human-readable JSON for files an author or a reviewer reads; never the hashed form."""
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


# write_atomic's temporary files; a leftover from an interrupted write is the toolkit's own.
TEMP_PREFIX = ".axiom-"

def write_atomic(path, data):
    """Replace one file in a single rename, so a reader never sees half of it; refuses a symlink target."""
    path = Path(path)
    if path.is_symlink():
        raise OSError(f"refusing to write through a symlink: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = data.encode("utf-8") if isinstance(data, str) else data
    # mkstemp creates 0600; the file keeps its old mode, or gets what the umask gives a new file.
    try:
        mode = path.stat().st_mode & 0o7777
    except FileNotFoundError:
        mask = os.umask(0)
        os.umask(mask)
        mode = 0o666 & ~mask
    handle, name = tempfile.mkstemp(dir=path.parent, prefix=TEMP_PREFIX)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(raw)
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def relative_safe(path):
    """AX-S-001 spelling rules for a repository-relative path: no absolute, `..`, NUL, backslash or scheme."""
    return (isinstance(path, str) and path != "" and not path.startswith("/") and "\\" not in path
            and "\0" not in path and ":" not in path and ".." not in path.split("/"))


def confined(root, rel):
    """The real file for a relative path, or None when it escapes the root through a link or is unsafe."""
    if not relative_safe(rel):
        return None
    real = (Path(root) / rel).resolve()
    return real if real.is_relative_to(Path(root).resolve()) else None
