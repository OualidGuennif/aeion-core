# Spec: knowledge/components/axiom-toolkit.md
"""Strict JSON transport (AX-M-001, AX-I-001): every input is bounded and checked before any schema.

A failure is an InputError with a stable code; nothing is coerced, repaired or guessed."""
import json
import os
import stat

SAFE = 9007199254740991
MAX_BYTES = 1048576
MAX_DEPTH = 128


class InputError(ValueError):
    def __init__(self, code, message, pointer=""):
        super().__init__(f"{code}: {message}")
        self.code, self.message, self.pointer = code, message, pointer


def read_bytes(path, limit=MAX_BYTES):
    """At most limit bytes of one regular file, never through a final symlink; larger is an error."""
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as error:
        raise InputError("UNREADABLE", f"{path}: {error.strerror or error}") from None
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise InputError("NOT_A_FILE", f"{path} is not a regular file")
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise InputError("TOO_LARGE", f"{path} exceeds {limit} bytes")
    return raw


def loads(raw, limit=MAX_BYTES):
    """Parse UTF-8 JSON bytes strictly: no duplicate keys, floats, NaN, unsafe integers, BOM or trailing data."""
    # Bound the bytes before decoding anything.
    if len(raw) > limit:
        raise InputError("TOO_LARGE", f"input exceeds {limit} bytes")
    # Decode strictly; a BOM is not part of JSON text.
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise InputError("INVALID_UTF8", f"byte {error.start} is not UTF-8") from None
    if text.startswith("﻿"):
        raise InputError("BOM", "a byte order mark is not allowed")
    # Parse with hooks that refuse what JSON permits but the contract does not.
    try:
        value = json.loads(text, object_pairs_hook=_object, parse_float=_float,
                           parse_constant=_constant, parse_int=_integer)
    except InputError:
        raise
    except RecursionError:
        raise InputError("TOO_DEEP", "nesting exceeds the parser's depth") from None
    except json.JSONDecodeError as error:
        code = "TRAILING_DATA" if error.msg.startswith("Extra data") else "INVALID_JSON"
        raise InputError(code, f"{error.msg} at line {error.lineno} column {error.colno}") from None
    # Walk once for depth, keys and strings that the hooks cannot see.
    _walk(value)
    return value


def load(path, limit=MAX_BYTES):
    return loads(read_bytes(path, limit), limit)


def _object(pairs):
    result = {}
    for key, item in pairs:
        if key in result:
            raise InputError("DUPLICATE_KEY", f"duplicate key {key!r}")
        result[key] = item
    return result


def _float(text):
    raise InputError("NON_INTEGER_NUMBER", f"{text} is not an integer")


def _constant(text):
    raise InputError("NON_FINITE_NUMBER", f"{text} is not JSON")


def _integer(text):
    # 2**53 has 16 digits: anything longer is unsafe before int() (which refuses beyond 4300 digits) runs.
    if len(text.lstrip("-")) > 16:
        raise InputError("UNSAFE_INTEGER", f"{text[:20]}... is outside the safe integer range")
    number = int(text)
    if abs(number) > SAFE:
        raise InputError("UNSAFE_INTEGER", f"{text} is outside the safe integer range")
    return number


def _walk(value):
    # Iterative, so a deep valid document cannot exhaust Python's stack here.
    stack = [(value, "", 0)]
    while stack:
        item, pointer, depth = stack.pop()
        if depth > MAX_DEPTH:
            raise InputError("TOO_DEEP", f"nesting exceeds {MAX_DEPTH}", pointer)
        if isinstance(item, dict):
            for key, child in item.items():
                if not key.isascii():
                    raise InputError("NON_ASCII_KEY", f"key {key!r} is not ASCII", pointer)
                _check_string(key, pointer)
                stack.append((child, pointer + "/" + key.replace("~", "~0").replace("/", "~1"), depth + 1))
        elif isinstance(item, list):
            stack += [(child, f"{pointer}/{index}", depth + 1) for index, child in enumerate(item)]
        elif isinstance(item, str):
            _check_string(item, pointer)


def _check_string(text, pointer):
    if any(0xD800 <= ord(char) <= 0xDFFF for char in text):
        raise InputError("LONE_SURROGATE", "a string holds an unpaired surrogate", pointer)
