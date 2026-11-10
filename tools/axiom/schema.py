# Spec: knowledge/components/axiom-toolkit.md
"""A JSON Schema Draft 2020-12 validator for the keyword subset the AxiomSpec schemas use.

A schema using any other keyword is refused when loaded (fail closed). `format` is an annotation,
as in 2020-12. Only local `#/$defs/...` references resolve; nothing is fetched."""
import re

ASSERTIONS = {"type", "properties", "required", "additionalProperties", "items", "minItems", "maxItems",
              "uniqueItems", "minLength", "maxLength", "minimum", "maximum", "enum", "const", "pattern",
              "anyOf", "oneOf", "allOf", "$ref"}
ANNOTATIONS = {"$schema", "$id", "$defs", "title", "description", "format", "examples", "default", "$comment"}
TYPES = {"object", "array", "string", "integer", "number", "boolean", "null"}


class SchemaError(ValueError):
    """The schema itself uses something this validator does not implement."""


class Validator:
    def __init__(self, schema):
        self.root = schema
        self.patterns = {}
        self._check(schema, "#")

    def errors(self, instance):
        """Every (instance pointer, message) the instance violates; an empty list means valid."""
        found = []
        self._validate(self.root, instance, "", found)
        return found

    def _check(self, schema, where):
        # Walk the schema once: unknown keywords and bad references fail before any instance is read.
        if isinstance(schema, bool):
            return
        if not isinstance(schema, dict):
            raise SchemaError(f"{where}: a schema is an object or a boolean")
        unknown = set(schema) - ASSERTIONS - ANNOTATIONS
        if unknown:
            raise SchemaError(f"{where}: unsupported keyword(s) {sorted(unknown)}")
        for key in ("properties", "$defs"):
            for name, child in schema.get(key, {}).items():
                self._check(child, f"{where}/{key}/{name}")
        for key in ("items", "additionalProperties"):
            if isinstance(schema.get(key), dict):
                self._check(schema[key], f"{where}/{key}")
        for key in ("anyOf", "oneOf", "allOf"):
            for index, child in enumerate(schema.get(key, [])):
                self._check(child, f"{where}/{key}/{index}")
        if "$ref" in schema:
            self._resolve(schema["$ref"])
        types = schema.get("type")
        if types is not None and not set(types if isinstance(types, list) else [types]) <= TYPES:
            raise SchemaError(f"{where}: unknown type {types}")
        if "pattern" in schema:
            self.patterns[schema["pattern"]] = _ecma(schema["pattern"])

    def _resolve(self, ref):
        if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
            raise SchemaError(f"only local #/$defs references are supported: {ref!r}")
        target = self.root.get("$defs", {}).get(ref[len("#/$defs/"):])
        if target is None:
            raise SchemaError(f"unresolved reference {ref}")
        return target

    def _validate(self, schema, value, pointer, found):
        if schema is True:
            return
        if schema is False:
            found.append((pointer, "no value is allowed here"))
            return
        if "$ref" in schema:
            self._validate(self._resolve(schema["$ref"]), value, pointer, found)
        if "type" in schema and not _has_type(value, schema["type"]):
            found.append((pointer, f"expected {schema['type']}, found {_kind(value)}"))
            return
        if "const" in schema and not same(value, schema["const"]):
            found.append((pointer, f"must equal {schema['const']!r}"))
        if "enum" in schema and not any(same(value, option) for option in schema["enum"]):
            found.append((pointer, f"{_short(value)} is not one of {schema['enum']}"))
        self._combinators(schema, value, pointer, found)
        if isinstance(value, dict):
            self._object(schema, value, pointer, found)
        elif isinstance(value, list):
            self._array(schema, value, pointer, found)
        elif isinstance(value, str):
            self._string(schema, value, pointer, found)
        elif type(value) is int:
            if "minimum" in schema and value < schema["minimum"]:
                found.append((pointer, f"{value} is below the minimum {schema['minimum']}"))
            if "maximum" in schema and value > schema["maximum"]:
                found.append((pointer, f"{value} is above the maximum {schema['maximum']}"))

    def _combinators(self, schema, value, pointer, found):
        for child in schema.get("allOf", []):
            self._validate(child, value, pointer, found)
        for key in ("anyOf", "oneOf"):
            if key not in schema:
                continue
            outcomes = []
            for child in schema[key]:
                errors = []
                self._validate(child, value, pointer, errors)
                outcomes.append(errors)
            matches = sum(1 for errors in outcomes if not errors)
            if matches == 0:
                # The closest branch explains the failure better than a bare "no match".
                closest = min(outcomes, key=len)
                found.append((pointer, f"matches none of the {len(outcomes)} {key} alternatives"))
                found.extend(closest[:5])
            elif key == "oneOf" and matches > 1:
                found.append((pointer, f"matches {matches} oneOf alternatives, exactly one is allowed"))

    def _object(self, schema, value, pointer, found):
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                found.append((pointer, f"missing required field '{name}'"))
        extra = schema.get("additionalProperties", True)
        for name, child in value.items():
            where = pointer + "/" + name.replace("~", "~0").replace("/", "~1")
            if name in properties:
                self._validate(properties[name], child, where, found)
            elif extra is False:
                found.append((where, f"unknown field '{name}'"))
            elif isinstance(extra, dict):
                self._validate(extra, child, where, found)

    def _array(self, schema, value, pointer, found):
        if "minItems" in schema and len(value) < schema["minItems"]:
            found.append((pointer, f"{len(value)} items, at least {schema['minItems']} required"))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            found.append((pointer, f"{len(value)} items, at most {schema['maxItems']} allowed"))
        if schema.get("uniqueItems"):
            for index, item in enumerate(value):
                if any(same(item, earlier) for earlier in value[:index]):
                    found.append((f"{pointer}/{index}", "duplicate item in a unique array"))
        if "items" in schema:
            for index, item in enumerate(value):
                self._validate(schema["items"], item, f"{pointer}/{index}", found)

    def _string(self, schema, value, pointer, found):
        if "minLength" in schema and len(value) < schema["minLength"]:
            found.append((pointer, f"shorter than {schema['minLength']} characters"))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            found.append((pointer, f"longer than {schema['maxLength']} characters"))
        if "pattern" in schema and not self.patterns[schema["pattern"]].search(value):
            found.append((pointer, f"{_short(value)} does not match {schema['pattern']}"))


def same(a, b):
    """JSON equality: true is not 1, 1 is not "1", object key order does not matter."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(same(a[key], b[key]) for key in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def _ecma(pattern):
    # ECMA-262 `$` matches only at the very end; Python's also matches before a final newline.
    if pattern.endswith("$") and not pattern.endswith("\\$"):
        pattern = pattern[:-1] + r"\Z"
    try:
        return re.compile(pattern, re.ASCII)
    except re.error as error:
        raise SchemaError(f"pattern {pattern!r}: {error}") from None


def _has_type(value, expected):
    return any(_is(value, name) for name in (expected if isinstance(expected, list) else [expected]))


def _is(value, name):
    if name == "integer":
        return type(value) is int
    if name == "number":
        return type(value) is int or type(value) is float
    return {"object": dict, "array": list, "string": str, "boolean": bool}.get(name, type(None)) is type(value)


def _kind(value):
    return {dict: "object", list: "array", str: "string", bool: "boolean", int: "integer",
            type(None): "null"}.get(type(value), type(value).__name__)


def _short(value):
    text = repr(value)
    return text if len(text) <= 60 else text[:57] + "..."
