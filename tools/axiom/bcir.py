# Spec: knowledge/components/axiom-toolkit.md
"""BCIR 0.1: static analysis, then bounded pure evaluation (AxiomSpec docs/05, AX-C-001..013).

Analysis checks every path, scope, operator, arity, type and unit before anything runs. Evaluation
follows the reference traversal: eager, left to right, no short-circuit, one step per node visit
and per collection item. Missing data or an exhausted budget is unknown, never pass."""
import re

from schema import Validator, SchemaError

SAFE = 9007199254740991
MAX_DEPTH, MAX_NODES, MAX_STEPS, MAX_ITEMS = 24, 2000, 1000000, 10000
ENV_KEYWORDS = {"type", "properties", "required", "additionalProperties", "items", "enum", "minimum", "maximum",
                "minItems", "maxItems", "minLength", "maxLength", "description"}
VARIABLE = re.compile(r"[a-z][a-z0-9_]*\Z")
ZERO = "zero"  # the unit of a literal 0, which takes whatever unit is expected


class AnalysisError(ValueError):
    def __init__(self, message, pointer=""):
        super().__init__(message)
        self.pointer = pointer


class Unknown(Exception):
    """Missing data or an exhausted budget: the result is unknown, never a Boolean."""


def check_environment(schema, pointer=""):
    """AX-C-002: closed objects, every property required, bounded arrays, strings and integers."""
    problems = []
    if not isinstance(schema, dict):
        return [(pointer, "an environment schema is an object")]
    extra = set(schema) - ENV_KEYWORDS
    if extra:
        problems.append((pointer, f"keyword(s) not allowed in an environment: {sorted(extra)}"))
    kind = schema.get("type")
    if kind == "object":
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is not False:
            problems.append((pointer, "an environment object must be closed (additionalProperties: false)"))
        if set(schema.get("required", [])) != set(properties):
            problems.append((pointer, "every declared property must be required"))
        for name, child in properties.items():
            problems += check_environment(child, f"{pointer}/properties/{name}")
    elif kind == "array":
        if type(schema.get("maxItems")) is not int or not 0 <= schema["maxItems"] <= MAX_ITEMS:
            problems.append((pointer, f"an environment array needs maxItems between 0 and {MAX_ITEMS}"))
        problems += check_environment(schema.get("items"), pointer + "/items")
    elif kind == "integer":
        low, high = schema.get("minimum"), schema.get("maximum")
        if type(low) is not int or type(high) is not int or not -SAFE <= low <= high <= SAFE:
            problems.append((pointer, "an environment integer needs safe minimum <= maximum"))
    elif kind == "string":
        if type(schema.get("maxLength")) is not int or schema["maxLength"] < 0:
            problems.append((pointer, "an environment string needs maxLength"))
    elif kind != "boolean":
        problems.append((pointer, f"environment type must be object, array, integer, boolean or string, not {kind!r}"))
    return problems


def unit_table(environment, terms):
    """Annotation pointer -> Term ID; `*` stands for one array-element level and must reach an integer."""
    table, problems = {}, []
    for index, annotation in enumerate(environment.get("units", [])):
        where = f"/units/{index}"
        pattern, term = annotation["pointer"], annotation["term_id"]
        if term not in terms:
            problems.append((where, f"unit {term} is not a Term"))
        node = _schema_at(environment["schema"], pattern)
        if node is None or node.get("type") != "integer":
            problems.append((where, f"{pattern} does not resolve to an integer leaf"))
        if table.get(pattern, term) != term:
            problems.append((where, f"{pattern} has conflicting unit annotations"))
        table[pattern] = term
    return table, problems


def _schema_at(schema, pattern):
    node = schema
    for token in _tokens(pattern):
        if token == "*" and node.get("type") == "array":
            node = node.get("items", {})
        elif node.get("type") == "object" and token in node.get("properties", {}):
            node = node["properties"][token]
        else:
            return None
    return node


def _tokens(pointer):
    if pointer == "":
        return []
    if not pointer.startswith("/") or re.search(r"~(?![01])", pointer):
        raise AnalysisError(f"invalid JSON Pointer {pointer!r}")
    # Decode ~1 then ~0, exactly once (RFC 6901 order).
    return [token.replace("~1", "/").replace("~0", "~") for token in pointer.split("/")[1:]]


class Analyzer:
    """Static types and units of one expression in one environment: run before any evaluation."""

    def __init__(self, environment, units):
        self.schema = environment["schema"]
        self.units = units
        self.count = 0

    def boolean_predicate(self, expression):
        found = self.visit(expression, {"env": (self.schema, "")}, 0, "")
        if found["t"] != "boolean":
            raise AnalysisError(f"a constraint must be Boolean, this one is {found['t']}", "")
        return found

    def visit(self, e, scope, depth, where):
        self.count += 1
        if depth > MAX_DEPTH or self.count > MAX_NODES:
            raise AnalysisError(f"expression exceeds depth {MAX_DEPTH} or {MAX_NODES} nodes", where)
        if not isinstance(e, dict) or "kind" not in e:
            raise AnalysisError("an expression is an object with a kind", where)
        kind = e["kind"]
        if kind == "literal":
            return self._literal(e.get("value"), where)
        if kind == "path":
            return self._path(e, scope, where)
        if kind == "apply":
            args = [self.visit(a, scope, depth + 1, f"{where}/arguments/{i}") for i, a in enumerate(e["arguments"])]
            return self._apply(e["operator"], args, where)
        if kind in ("aggregate", "quantifier"):
            return self._collection(e, scope, depth, where)
        raise AnalysisError(f"unknown expression kind {kind!r}", where)

    def _literal(self, value, where):
        if type(value) is bool:
            return {"t": "boolean"}
        if type(value) is int:
            if abs(value) > SAFE:
                raise AnalysisError("literal outside the safe integer range", where)
            return {"t": "integer", "unit": ZERO if value == 0 else None}
        if isinstance(value, str):
            return {"t": "string"}
        if isinstance(value, list):
            kinds = {type(item) for item in value}
            if len(kinds) > 1 or kinds - {bool, int, str}:
                raise AnalysisError("a literal array is homogeneous and holds scalars only", where)
            element = {bool: "boolean", int: "integer", str: "string"}.get(next(iter(kinds), None))
            unit = ZERO if element == "integer" and all(item == 0 for item in value) else None
            return {"t": "array", "item": {"t": element, "unit": unit} if element else None}
        raise AnalysisError(f"unsupported literal {type(value).__name__}", where)

    def _path(self, e, scope, where):
        if e.get("root") not in scope:
            raise AnalysisError(f"unbound root {e.get('root')!r}", where)
        node, apath = scope[e["root"]]
        for token in _tokens(e.get("pointer", "")):
            if node.get("type") != "object" or token not in node.get("properties", {}):
                raise AnalysisError(f"path {e['pointer']!r} is not declared in the environment", where)
            node, apath = node["properties"][token], f"{apath}/{token.replace('~', '~0').replace('/', '~1')}"
        return self._type_of(node, apath)

    def _type_of(self, node, apath):
        kind = node.get("type")
        if kind == "array":
            return {"t": "array", "item": self._type_of(node["items"], apath + "/*"), "schema": node["items"],
                    "apath": apath + "/*"}
        if kind == "integer":
            return {"t": "integer", "unit": self.units.get(apath)}
        return {"t": kind}

    def _apply(self, op, args, where):
        arity = {"not": (1, 1), "and": (2, None), "or": (2, None)}.get(op, (2, 2))
        if len(args) < arity[0] or (arity[1] and len(args) > arity[1]):
            raise AnalysisError(f"{op} takes {arity[0]}{'+' if not arity[1] else ''} arguments, got {len(args)}", where)
        if op in ("and", "or", "not", "implies"):
            if any(a["t"] != "boolean" for a in args):
                raise AnalysisError(f"{op} takes Booleans only (no coercion)", where)
            return {"t": "boolean"}
        a, b = args
        if op in ("eq", "ne"):
            if a["t"] != b["t"] or a["t"] not in ("integer", "string", "boolean"):
                raise AnalysisError(f"{op} compares two scalars of one type, got {a['t']} and {b['t']}", where)
            if a["t"] == "integer":
                _same_unit(a, b, op, where)
            return {"t": "boolean"}
        if op == "in":
            if a["t"] not in ("integer", "string", "boolean") or b["t"] != "array":
                raise AnalysisError("in takes a scalar and an array", where)
            item = b["item"] or {"t": a["t"], "unit": ZERO}
            if item["t"] != a["t"]:
                raise AnalysisError(f"in: a {a['t']} cannot be found in an array of {item['t']}", where)
            if a["t"] == "integer":
                _same_unit(a, item, op, where)
            return {"t": "boolean"}
        if a["t"] != "integer" or b["t"] != "integer":
            raise AnalysisError(f"{op} takes integers, got {a['t']} and {b['t']}", where)
        if op in ("lt", "le", "gt", "ge"):
            _same_unit(a, b, op, where)
            return {"t": "boolean"}
        if op in ("add", "sub"):
            return {"t": "integer", "unit": _same_unit(a, b, op, where)}
        if op == "mul":
            if a["unit"] not in (None, ZERO) and b["unit"] not in (None, ZERO):
                raise AnalysisError("mul needs at least one dimensionless operand", where)
            return {"t": "integer", "unit": b["unit"] if a["unit"] in (None, ZERO) else a["unit"]}
        raise AnalysisError(f"unknown operator {op!r}", where)

    def _collection(self, e, scope, depth, where):
        bind = e.get("bind")
        if not isinstance(bind, str) or not VARIABLE.match(bind) or bind == "env" or bind in scope:
            raise AnalysisError(f"variable {bind!r} is not a fresh lowercase name", where)
        collection = self.visit(e["collection"], scope, depth + 1, where + "/collection")
        if collection["t"] != "array" or "schema" not in collection:
            raise AnalysisError("a collection is an environment array, never a literal", where)
        inner = dict(scope, **{bind: (collection["schema"], collection["apath"])})
        if e["kind"] == "quantifier":
            if e.get("operator") not in ("all", "exists"):
                raise AnalysisError(f"unknown quantifier {e.get('operator')!r}", where)
            if self.visit(e["predicate"], inner, depth + 1, where + "/predicate")["t"] != "boolean":
                raise AnalysisError("a quantifier predicate is Boolean", where)
            return {"t": "boolean"}
        if e.get("operator") not in ("sum", "count"):
            raise AnalysisError(f"unknown aggregate {e.get('operator')!r}", where)
        if self.visit(e["filter"], inner, depth + 1, where + "/filter")["t"] != "boolean":
            raise AnalysisError("an aggregate filter is Boolean", where)
        projection = self.visit(e["projection"], inner, depth + 1, where + "/projection")
        if projection["t"] != "integer":
            raise AnalysisError("an aggregate projects integers", where)
        if e["operator"] == "count":
            literal = e["projection"]
            if literal.get("kind") != "literal" or type(literal.get("value")) is not int or literal["value"] != 1:
                raise AnalysisError("count requires the projection to be the literal integer 1", where)
            return {"t": "integer", "unit": None}
        return {"t": "integer", "unit": projection["unit"]}


def _same_unit(a, b, op, where):
    left, right = a.get("unit"), b.get("unit")
    if ZERO in (left, right):
        return right if left == ZERO else left
    if left != right:
        raise AnalysisError(f"{op}: unit {left or 'dimensionless'} is not compatible with {right or 'dimensionless'}",
                            where)
    return left


class Evaluator:
    """Eager reference traversal with a step budget; reads only its arguments."""

    def __init__(self, max_steps=MAX_STEPS):
        self.max_steps = max_steps
        self.steps = 0

    def run(self, expression, environment):
        self.steps = 0
        return self.visit(expression, {"env": environment})

    def tick(self):
        self.steps += 1
        if self.steps > self.max_steps:
            raise Unknown(f"work budget of {self.max_steps} steps exhausted")

    def visit(self, e, scope):
        self.tick()
        kind = e["kind"]
        if kind == "literal":
            return e["value"]
        if kind == "path":
            value = scope[e["root"]]
            for token in _tokens(e["pointer"]):
                if not isinstance(value, dict) or token not in value:
                    raise Unknown(f"observation has no value at {e['pointer']}")
                value = value[token]
            return value
        if kind == "apply":
            return _operate(e["operator"], [self.visit(a, scope) for a in e["arguments"]])
        items = self.visit(e["collection"], scope)
        if not isinstance(items, list) or len(items) > MAX_ITEMS:
            raise Unknown("collection missing or above the item bound")
        results = []
        for item in items:
            self.tick()
            inner = dict(scope, **{e["bind"]: item})
            if kind == "quantifier":
                results.append(_boolean(self.visit(e["predicate"], inner)))
            elif _boolean(self.visit(e["filter"], inner)):
                results.append(_integer(self.visit(e["projection"], inner)))
        if kind == "quantifier":
            return all(results) if e["operator"] == "all" else any(results)
        if e["operator"] == "count":
            return len(results)
        total = 0
        for value in results:
            total = _integer(total + value)
        return total


def _operate(op, args):
    if op in ("and", "or", "not", "implies"):
        values = [_boolean(a) for a in args]
        if op == "and":
            return all(values)
        if op == "or":
            return any(values)
        return (not values[0]) if op == "not" else (not values[0] or values[1])
    a, b = args
    if op == "eq":
        return a == b and type(a) is type(b)
    if op == "ne":
        return not (a == b and type(a) is type(b))
    if op == "in":
        return any(type(item) is type(a) and item == a for item in b)
    a, b = _integer(a), _integer(b)
    return {"lt": lambda: a < b, "le": lambda: a <= b, "gt": lambda: a > b, "ge": lambda: a >= b,
            "add": lambda: _integer(a + b), "sub": lambda: _integer(a - b), "mul": lambda: _integer(a * b)}[op]()


def _boolean(value):
    if type(value) is not bool:
        raise TypeError("expected a Boolean")
    return value


def _integer(value):
    if type(value) is not int:
        raise TypeError("expected an integer")
    if abs(value) > SAFE:
        raise OverflowError("integer outside the safe range")
    return value


def evaluate(expression, environment, schema_validator, max_steps=MAX_STEPS):
    """One constraint on one observation: pass, fail, unknown or error, with a reason and the steps used."""
    errors = schema_validator.errors(environment)
    # Absent data is unknown (never an empty collection); present but malformed data is an error.
    if errors and all(message.startswith("missing required field") for _, message in errors):
        pointer, message = errors[0]
        return {"result": "unknown", "reason": f"observation lacks data at {pointer or '/'}: {message}", "steps": 0}
    if errors:
        pointer, message = errors[0]
        return {"result": "error", "reason": f"observation invalid at {pointer or '/'}: {message}", "steps": 0}
    evaluator = Evaluator(max_steps)
    try:
        value = evaluator.run(expression, environment)
    except Unknown as reason:
        return {"result": "unknown", "reason": str(reason), "steps": evaluator.steps}
    except (TypeError, OverflowError, KeyError, AnalysisError) as reason:
        return {"result": "error", "reason": str(reason), "steps": evaluator.steps}
    if type(value) is not bool:
        return {"result": "error", "reason": "the constraint did not produce a Boolean", "steps": evaluator.steps}
    return {"result": "pass" if value else "fail", "reason": "", "steps": evaluator.steps}


def environment_validator(environment):
    try:
        return Validator(environment["schema"])
    except SchemaError as error:
        raise AnalysisError(str(error)) from None
