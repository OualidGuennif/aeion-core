# Spec: knowledge/components/axiom-toolkit.md
"""The canonical model and its design gates G01-G07 (AxiomSpec docs/03, 06; AX-M-*, AX-G-*).

Every check keeps its diagnostic; a phase is the worst of its required gates (error > fail >
unknown > pass). Declared links are claims: nothing here runs project code or calls a model."""
from collections import deque
from datetime import datetime

import bcir
from common import ROOT, SCHEMA_DIR, TOOL_VERSION, canonical_digest, relative_safe, sha256
from schema import SchemaError, Validator
from strict import InputError, load

RELATIONS = {
    "satisfies": ({"Requirement"}, {"Goal"}),
    "uses_term": ({"Requirement", "Constraint"}, {"Term"}),
    "formalizes": ({"Constraint"}, {"Requirement"}),
    "models": ({"StateModel"}, {"Requirement"}),
    "illustrates": ({"Scenario"}, {"Requirement"}),
    "verifies": ({"TestCase"}, {"Requirement"}),
    "checks": ({"TestCase"}, {"Constraint"}),
    "implements": ({"Component"}, {"Requirement"}),
    "depends_on": ({"Requirement"}, {"Requirement"}),
    "assumes": ({"Requirement", "Constraint"}, {"Assumption"}),
    "governs": ({"Decision"}, {"Goal", "Requirement", "Constraint", "StateModel"}),
    "threatens": ({"Risk"}, {"Goal", "Requirement"}),
    "mitigates": ({"Control"}, {"Risk"}),
    "realizes": ({"Requirement"}, {"Control"}),
}
PREFIXES = {"Goal": "GOAL", "Term": "TERM", "Requirement": "REQ", "Constraint": "CON", "StateModel": "MODEL",
            "Scenario": "SCN", "TestCase": "TEST", "Component": "COMP", "Decision": "DEC", "Assumption": "ASM",
            "Risk": "RISK", "Control": "CTRL"}
SECTIONS = {"actors": "ACTOR", "sources": "SRC", "environments": "ENV", "edges": "EDGE", "bindings": "BIND",
            "context_assets": "ASSET"}
DESIGN_GATES = ("G01", "G02", "G03", "G04", "G05", "G06", "G07")
SEVERITY = {"error": 3, "fail": 2, "unknown": 1, "pass": 0}
GATE_TITLES = {"G01": "strict parser and artifact schema", "G02": "IDs, references, typed relationships",
               "G03": "BCIR operators, scope, types, units, bounds", "G04": "authoring patterns, decisions, assumptions",
               "G05": "state-model topology", "G06": "reference scenarios and expected outcomes",
               "G07": "test plan, oracles and traceability", "G08": "context admission and rights",
               "G09": "bindings resolved", "G10": "tests actually executed", "G11": "evidence integrity and freshness",
               "G12": "policy-required authority", "G13": "runtime observations"}
CAPABILITIES = ["strict_json", "schema_validation_subset", "reference_checks", "bcir_static_analysis",
                "bcir_bounded_evaluation", "decision_gates", "state_topology", "verification_plan_checks",
                "graph_queries", "context_closure", "binding_resolution_lexical", "unittest_adapter",
                "receipt_freshness", "generated_views"]
UNSUPPORTED = ["authority_attestation", "trusted_policy", "context_rights_enforcement", "runtime_observation",
               "state_exploration", "solver_adapter", "type_resolved_call_graph"]
PATTERN_FIELDS = {  # pattern -> (conditions, trigger, feature) must be populated
    "ubiquitous": (False, False, False), "event": (False, True, False), "state": (True, False, False),
    "unwanted": (False, True, False), "optional": (False, False, True), "composite": (True, True, False)}


class Result:
    """Diagnostics of one validation run, grouped by gate."""

    def __init__(self):
        self.diagnostics = []
        self.notes = {}

    def add(self, gate, status, code, message, subject=None, pointer=""):
        self.diagnostics.append({"gate": gate, "status": status, "code": code, "subject_id": subject,
                                 "pointer": pointer, "message": message})

    def gate_status(self, gate):
        found = [d["status"] for d in self.diagnostics if d["gate"] == gate]
        return max(found, key=SEVERITY.get) if found else "pass"

    def phase(self, gates):
        return max((self.gate_status(g) for g in gates), key=SEVERITY.get)


def schema_validator(name="spec"):
    return Validator(load(ROOT / SCHEMA_DIR / f"{name}.schema.json"))


def load_spec(path, result):
    """G01: the strict transport and the closed schema; None when the document cannot be trusted further."""
    try:
        spec = load(path)
    except InputError as error:
        result.add("G01", "error", error.code, error.message, pointer=error.pointer)
        return None
    try:
        errors = schema_validator().errors(spec)
    except (InputError, SchemaError) as error:
        # The toolkit's own schema is missing or unreadable: nothing can be validated, so nothing passes.
        result.add("G01", "error", "SCHEMA_UNAVAILABLE", f"the AxiomSpec schema could not be loaded "
                   f"({getattr(error, 'message', error)}); restore {SCHEMA_DIR}/ (template-update carries it)")
        return None
    for pointer, message in errors[:50]:
        result.add("G01", "error", "SCHEMA", message, pointer=pointer)
    if len(errors) > 50:
        result.add("G01", "error", "SCHEMA", f"{len(errors) - 50} more schema errors not listed")
    return None if errors else spec


def validate(spec, phase="design", evaluated_at=None, result=None):
    """Run the design gates on a schema-valid spec; G06 needs the scenarios' observations only."""
    result = result or Result()
    model = Model(spec)
    check_references(model, result)
    check_constraints(model, result)
    check_authoring(model, result)
    check_states(model, result)
    check_scenarios(model, result, evaluated_at)
    check_test_plan(model, result)
    return model, result


class Model:
    """Indexes over one spec: nodes by ID, edges by endpoint, and the position of each record."""

    def __init__(self, spec):
        self.spec = spec
        self.nodes = {n["id"]: n for n in spec["nodes"]}
        self.where = {n["id"]: f"/nodes/{i}" for i, n in enumerate(spec["nodes"])}
        self.actors = {a["id"]: a for a in spec["actors"]}
        self.sources = {s["id"]: s for s in spec["sources"]}
        self.envs = {e["id"]: e for e in spec["environments"]}
        self.bindings = {b["id"]: b for b in spec["bindings"]}
        self.assets = {a["id"]: a for a in spec["context_assets"]}
        self.edges = spec["edges"]
        self.out, self.into = {}, {}
        for edge in self.edges:
            self.out.setdefault(edge["from"], []).append(edge)
            self.into.setdefault(edge["to"], []).append(edge)
        self.digest = canonical_digest(spec)

    def kind(self, node_id):
        return self.nodes.get(node_id, {}).get("kind")

    def active(self, kind=None):
        return [n for n in self.spec["nodes"] if n["status"] == "active" and (kind is None or n["kind"] == kind)]

    def linked(self, node_id, relation, direction="out"):
        edges = self.out.get(node_id, []) if direction == "out" else self.into.get(node_id, [])
        key = "to" if direction == "out" else "from"
        return [e[key] for e in edges if e["relation"] == relation]


def check_references(model, result):
    """G02: unique IDs with reserved prefixes, known actors and sources, typed edges, no dependency cycle."""
    spec = model.spec
    seen = {}
    records = [("/project/id", spec["project"]["id"])]
    for section in [*SECTIONS, "nodes"]:
        records += [(f"/{section}/{i}/id", record["id"]) for i, record in enumerate(spec[section])]
    for pointer, record_id in records:
        if record_id in seen:
            result.add("G02", "fail", "DUPLICATE_ID", f"{record_id} is also used at {seen[record_id]}", record_id, pointer)
        seen.setdefault(record_id, pointer)
    if not spec["project"]["id"].startswith("PROJECT-"):
        result.add("G02", "fail", "WRONG_PREFIX", "the project ID must start with PROJECT-", pointer="/project/id")
    for section, prefix in SECTIONS.items():
        for i, record in enumerate(spec[section]):
            if not record["id"].startswith(prefix + "-"):
                result.add("G02", "fail", "WRONG_PREFIX", f"{record['id']} in {section} must start with {prefix}-",
                           record["id"], f"/{section}/{i}/id")
    if spec["project"]["owner"] not in model.actors:
        result.add("G02", "fail", "UNKNOWN_OWNER", f"project owner {spec['project']['owner']} is not an actor",
                   pointer="/project/owner")
    for env_index, env in enumerate(spec["environments"]):
        for i, unit in enumerate(env["units"]):
            if model.kind(unit["term_id"]) != "Term":
                result.add("G02", "fail", "UNKNOWN_UNIT_TERM", f"unit {unit['term_id']} is not a Term", env["id"],
                           f"/environments/{env_index}/units/{i}/term_id")
    for node in spec["nodes"]:
        _check_node_references(model, node, result)
    for i, edge in enumerate(model.edges):
        _check_edge(model, edge, f"/edges/{i}", result)
    _check_cycles(model, result)
    _check_provenance(model, result)
    for i, binding in enumerate(spec["bindings"]):
        if binding["node_id"] not in model.nodes:
            result.add("G02", "fail", "UNKNOWN_BINDING_NODE", f"{binding['id']} binds unknown {binding['node_id']}",
                       binding["id"], f"/bindings/{i}/node_id")
        if not relative_safe(binding["path"]):
            result.add("G02", "fail", "UNSAFE_BINDING_PATH", f"{binding['path']!r} is not a safe relative path",
                       binding["id"], f"/bindings/{i}/path")
    for i, asset in enumerate(spec["context_assets"]):
        _check_asset(model, asset, f"/context_assets/{i}", result)
    if spec["project"]["mode"] == "product" and not (model.active("Goal") and model.active("Requirement")):
        result.add("G02", "fail", "EMPTY_BASELINE", "a product baseline needs at least one active goal and requirement")


def _check_node_references(model, node, result):
    pointer, node_id, data = model.where[node["id"]], node["id"], node["data"]
    if not node_id.startswith(PREFIXES[node["kind"]] + "-"):
        result.add("G02", "fail", "WRONG_PREFIX", f"a {node['kind']} ID starts with {PREFIXES[node['kind']]}-",
                   node_id, pointer + "/id")
    for field in ("owner", "created_by"):
        if node[field] not in model.actors:
            result.add("G02", "fail", "UNKNOWN_ACTOR", f"{field} {node[field]} is not a declared actor", node_id,
                       f"{pointer}/{field}")
    for source in node["source_ids"]:
        if source not in model.sources:
            result.add("G02", "fail", "UNKNOWN_SOURCE", f"source {source} is not declared", node_id,
                       pointer + "/source_ids")
    if data.get("environment_id") is not None and data["environment_id"] not in model.envs:
        result.add("G02", "fail", "UNKNOWN_ENVIRONMENT", f"environment {data['environment_id']} is not declared",
                   node_id, pointer + "/data/environment_id")
    if node["kind"] == "TestCase":
        for scenario in data["witness_scenario_ids"]:
            if model.kind(scenario) != "Scenario":
                result.add("G02", "fail", "UNKNOWN_SCENARIO", f"witness {scenario} is not a Scenario", node_id,
                           pointer + "/data/witness_scenario_ids")
    if node["kind"] == "Scenario":
        for i, expected in enumerate(data["constraint_expectations"]):
            if model.kind(expected["constraint_id"]) != "Constraint":
                result.add("G02", "fail", "UNKNOWN_CONSTRAINT", f"{expected['constraint_id']} is not a Constraint",
                           node_id, f"{pointer}/data/constraint_expectations/{i}")


def _check_edge(model, edge, pointer, result):
    a, b = model.nodes.get(edge["from"]), model.nodes.get(edge["to"])
    if a is None or b is None:
        missing = edge["from"] if a is None else edge["to"]
        result.add("G02", "fail", "UNKNOWN_TARGET", f"{edge['id']} names unknown {missing}", edge["id"], pointer)
        return
    allowed = RELATIONS.get(edge["relation"])
    if allowed is None or a["kind"] not in allowed[0] or b["kind"] not in allowed[1]:
        result.add("G02", "fail", "WRONG_EDGE_TYPE",
                   f"{edge['relation']} does not go from {a['kind']} to {b['kind']}", edge["id"], pointer)
        return
    if a["status"] == "active" and b["status"] == "retired":
        result.add("G02", "fail", "ACTIVE_TO_RETIRED", f"active {a['id']} links retired {b['id']}", edge["id"], pointer)


def _check_cycles(model, result):
    # Kahn's algorithm: iterative, so a long valid chain cannot exhaust the stack (AX-I-001).
    requirements = sorted(n["id"] for n in model.active("Requirement"))
    targets = {nid: [e["to"] for e in model.out.get(nid, []) if e["relation"] == "depends_on"
                     and model.nodes.get(e["to"], {}).get("status") == "active"] for nid in requirements}
    indegree = dict.fromkeys(requirements, 0)
    for listed in targets.values():
        for target in listed:
            if target in indegree:
                indegree[target] += 1
    ready = deque(nid for nid in requirements if indegree[nid] == 0)
    while ready:
        for target in targets[ready.popleft()]:
            if target in indegree:
                indegree[target] -= 1
                if indegree[target] == 0:
                    ready.append(target)
    for nid in sorted(n for n, count in indegree.items() if count > 0):
        result.add("G02", "fail", "DEPENDENCY_CYCLE", f"{nid} is on a depends_on cycle", nid, model.where[nid])


def _check_provenance(model, result):
    for node in model.active("Requirement"):
        goals = [g for g in model.linked(node["id"], "satisfies") if model.nodes.get(g, {}).get("status") == "active"]
        if not node["source_ids"]:
            result.add("G02", "fail", "REQUIREMENT_PROVENANCE", f"{node['id']} has no source", node["id"],
                       model.where[node["id"]])
        elif node["data"]["priority"] == "must" and not goals:
            result.add("G02", "fail", "REQUIREMENT_PROVENANCE", f"must requirement {node['id']} satisfies no active goal",
                       node["id"], model.where[node["id"]])
    for node in model.active("Constraint"):
        if not [r for r in model.linked(node["id"], "formalizes") if model.nodes.get(r, {}).get("status") == "active"]:
            result.add("G02", "fail", "UNLINKED_CONSTRAINT", f"{node['id']} formalizes no active requirement",
                       node["id"], model.where[node["id"]])


def _check_asset(model, asset, pointer, result):
    if not (set(asset["supports"]) <= set(model.nodes) and set(asset["source_ids"]) <= set(model.sources)
            and set(asset["allowed_roles"]) <= set(model.actors)):
        result.add("G02", "fail", "UNKNOWN_ASSET_REFERENCE", f"{asset['id']} names an unknown node, source or actor",
                   asset["id"], pointer)
    kinds = {"Goal", "Term", "Requirement", "Constraint", "StateModel", "Decision"}
    if any(model.kind(nid) not in kinds for nid in asset["supports"] if nid in model.nodes):
        result.add("G02", "fail", "WRONG_ASSET_TARGET_KIND", f"{asset['id']} supports a kind assets cannot support",
                   asset["id"], pointer + "/supports")
    if asset["binding_id"] is not None and asset["binding_id"] not in model.bindings:
        result.add("G02", "fail", "UNKNOWN_ASSET_BINDING", f"{asset['id']} names unknown {asset['binding_id']}",
                   asset["id"], pointer + "/binding_id")
    if asset["locator"].startswith("node:") and asset["locator"][5:] not in model.nodes:
        result.add("G02", "fail", "UNKNOWN_ASSET_LOCATOR", f"{asset['locator']} is not in the snapshot", asset["id"],
                   pointer + "/locator")


def check_constraints(model, result):
    """G03: environments are restricted schemas; every BCIR constraint is well-typed and unit-consistent."""
    terms = {n["id"] for n in model.spec["nodes"] if n["kind"] == "Term"}
    model.units, model.broken_envs = {}, set()
    for index, env in enumerate(model.spec["environments"]):
        try:
            problems = bcir.check_environment(env["schema"])
            table, unit_problems = bcir.unit_table(env, terms)
        except (bcir.AnalysisError, AttributeError, TypeError, KeyError, RecursionError) as error:
            # A schema the analyzer cannot even walk is an error of the environment, never a crash.
            result.add("G03", "error", "ENVIRONMENT_SCHEMA", f"the environment schema cannot be analyzed: "
                       f"{type(error).__name__}: {str(error)[:200]}", env["id"], f"/environments/{index}/schema")
            model.broken_envs.add(env["id"])
            model.units[env["id"]] = {}
            continue
        if problems or unit_problems:
            model.broken_envs.add(env["id"])
        for pointer, message in problems:
            result.add("G03", "error", "ENVIRONMENT_SCHEMA", message, env["id"], f"/environments/{index}/schema{pointer}")
        for pointer, message in unit_problems:
            result.add("G03", "error", "UNIT_ANNOTATION", message, env["id"], f"/environments/{index}{pointer}")
        model.units[env["id"]] = table
    for node in model.spec["nodes"]:
        if node["kind"] != "Constraint" or node["status"] == "retired":
            continue
        _check_constraint(model, node, result)


def _check_constraint(model, node, result):
    data, pointer, node_id = node["data"], model.where[node["id"]], node["id"]
    if data["predicate_role"] == "review":
        if data["representation"] != "review_protocol" or data["expression"] is not None or not data["review_protocol"]:
            result.add("G03", "error", "INCONSISTENT_REVIEW", "a review constraint has a protocol and no expression",
                       node_id, pointer + "/data")
    elif (data["representation"] != "bcir" or data["expression"] is None or data["environment_id"] is None
          or data["review_protocol"] is not None):
        result.add("G03", "error", "INCONSISTENT_BCIR", "a BCIR constraint has an expression, an environment and "
                   "no review protocol", node_id, pointer + "/data")
    binding = model.bindings.get(data["enforcement_binding_id"])
    if data["enforcement_binding_id"] is not None and (binding is None or binding["node_id"] != node_id
                                                       or binding["kind"] != "enforcement"):
        result.add("G02", "fail", "INVALID_ENFORCEMENT_BINDING", f"{data['enforcement_binding_id']} is not an "
                   f"enforcement binding of {node_id}", node_id, pointer + "/data/enforcement_binding_id")
    _check_window(data, node_id, pointer, result)
    env = model.envs.get(data["environment_id"])
    if data["representation"] != "bcir" or data["expression"] is None or env is None:
        return
    if env["id"] in getattr(model, "broken_envs", ()):
        result.add("G03", "unknown", "ENVIRONMENT_INVALID", f"{env['id']} failed G03, so {node_id} was not analyzed",
                   node_id, f"{pointer}/data/expression")
        return
    try:
        bcir.Analyzer(env, model.units.get(env["id"], {})).boolean_predicate(data["expression"])
    except bcir.AnalysisError as error:
        result.add("G03", "error", "BCIR_STATIC", str(error), node_id, f"{pointer}/data/expression{error.pointer}")
    except (AttributeError, TypeError, KeyError, RecursionError) as error:
        result.add("G03", "error", "BCIR_STATIC", f"cannot analyze against {env['id']}: {type(error).__name__}",
                   node_id, f"{pointer}/data/expression")


def utc_instant(value):
    """The datetime of an ISO 8601 instant in UTC (Z or +00:00); ValueError for anything else."""
    if not isinstance(value, str):
        raise ValueError(f"{value!r} is not a UTC instant")
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.utcoffset() is None or moment.utcoffset().total_seconds() != 0:
        raise ValueError(f"{value!r} is not a UTC instant")
    return moment


def _check_window(data, node_id, pointer, result):
    bounds = []
    for field in ("effective_from", "effective_until"):
        value = data[field]
        if value is None:
            bounds.append(None)
            continue
        try:
            bounds.append(utc_instant(value))
        except ValueError:
            result.add("G03", "error", "INVALID_WINDOW", f"{field} {value!r} is not a UTC instant", node_id,
                       f"{pointer}/data/{field}")
            return
    if bounds[0] and bounds[1] and bounds[0] >= bounds[1]:
        result.add("G03", "error", "INVALID_WINDOW", "effective_from must be before effective_until", node_id,
                   pointer + "/data")


def check_authoring(model, result):
    """G04: requirement patterns fill exactly their fields; blocking decisions answered, assumptions validated."""
    for node in model.spec["nodes"]:
        if node["kind"] != "Requirement" or node["status"] == "retired":
            continue
        data = node["data"]
        conditions, trigger, feature = PATTERN_FIELDS[data["pattern"]]
        populated = (bool(data["conditions"]), data["trigger"] is not None, data["feature"] is not None)
        if populated != (conditions, trigger, feature):
            result.add("G04", "fail", "PATTERN_FIELDS", f"pattern {data['pattern']} needs conditions={conditions}, "
                       f"trigger={trigger}, feature={feature}", node["id"], model.where[node["id"]] + "/data")
    for node in model.active("Decision"):
        if node["data"]["blocking"] and node["data"]["answer"] is None:
            result.add("G04", "fail", "OPEN_BLOCKING_DECISION", f"{node['id']} is unanswered: "
                       f"{node['data']['question']}", node["id"], model.where[node["id"]] + "/data/answer")
    for node in model.active("Assumption"):
        if node["data"]["blocking"] and node["data"]["state"] != "validated":
            result.add("G04", "fail", "UNVALIDATED_ASSUMPTION", f"{node['id']} is {node['data']['state']}: "
                       f"{node['data']['claim']}", node["id"], model.where[node["id"]] + "/data/state")


def check_states(model, result):
    """G05: initial state exists, names and transition IDs unique, endpoints known, guards compatible."""
    for node in model.spec["nodes"]:
        if node["kind"] != "StateModel" or node["status"] == "retired":
            continue
        data, pointer = node["data"], model.where[node["id"]]
        names = [s["name"] for s in data["states"]]
        if len(names) != len(set(names)) or data["initial"] not in names:
            result.add("G05", "fail", "INVALID_STATES", "state names must be unique and include the initial state",
                       node["id"], pointer + "/data/states")
        ids = [t["id"] for t in data["transitions"]]
        if len(ids) != len(set(ids)):
            result.add("G05", "fail", "DUPLICATE_TRANSITION", "transition IDs repeat", node["id"], pointer)
        for i, transition in enumerate(data["transitions"]):
            where = f"{pointer}/data/transitions/{i}"
            if transition["from"] not in names or transition["to"] not in names:
                result.add("G05", "fail", "UNKNOWN_STATE", f"{transition['id']} joins an undeclared state", node["id"],
                           where)
            guard = transition["guard_id"]
            if guard is None:
                continue
            if model.kind(guard) != "Constraint":
                result.add("G05", "fail", "UNKNOWN_GUARD", f"guard {guard} is not a Constraint", node["id"], where)
            elif (model.nodes[guard]["data"]["representation"] != "bcir"
                  or model.nodes[guard]["data"]["environment_id"] != data["environment_id"]):
                result.add("G05", "fail", "INCOMPATIBLE_GUARD", f"guard {guard} is not BCIR in "
                           f"{data['environment_id']}", node["id"], where)


def check_scenarios(model, result, evaluated_at=None):
    """G06: each scenario's given data fits its environment; each expectation holds on it."""
    validators = {}
    for node in model.active("Scenario"):
        data, pointer = node["data"], model.where[node["id"]]
        env = model.envs.get(data["environment_id"])
        if env is None:
            continue
        if env["id"] in getattr(model, "broken_envs", ()):
            # G03 rejected the environment: its scenarios cannot be checked, so they are unknown, not pass.
            result.add("G06", "unknown", "ENVIRONMENT_INVALID", f"{env['id']} failed G03; its scenarios were not "
                       "evaluated", node["id"], pointer + "/data/given")
            continue
        try:
            if env["id"] not in validators:
                validators[env["id"]] = bcir.environment_validator(env)
            validator = validators[env["id"]]
            problems = validator.errors(data["given"])
        except (bcir.AnalysisError, RecursionError, TypeError, AttributeError) as error:
            result.add("G06", "error", "ENVIRONMENT_SCHEMA", f"the environment schema cannot validate data: "
                       f"{type(error).__name__}: {str(error)[:200]}", node["id"], pointer + "/data/given")
            continue
        if problems:
            result.add("G06", "error", "INVALID_GIVEN", f"given data invalid at {problems[0][0] or '/'}: "
                       f"{problems[0][1]}", node["id"], pointer + "/data/given")
            continue
        for i, expectation in enumerate(data["constraint_expectations"]):
            outcome = expectation_outcome(model, node, expectation, validator, evaluated_at)
            if outcome:
                status, code, message = outcome
                result.add("G06", status, code, message, node["id"], f"{pointer}/data/constraint_expectations/{i}")


def expectation_outcome(model, scenario, expectation, validator, evaluated_at=None, given=None):
    """None when the expectation holds; otherwise (status, code, message)."""
    constraint = model.nodes.get(expectation["constraint_id"])
    if constraint is None:
        return None
    data = constraint["data"]
    if data["representation"] != "bcir" or data["environment_id"] != scenario["data"]["environment_id"]:
        return ("fail", "INCOMPATIBLE_EXPECTATION", f"{constraint['id']} is not BCIR in this scenario's environment")
    # Applicability first (docs/05): only an applicable hard invariant binds a witness.
    if data["effective_from"] or data["effective_until"]:
        # AX-C-013: applies when effective_from <= evaluated_at < effective_until; out of window is not pass.
        if evaluated_at is None:
            return ("unknown", "APPLICABILITY_UNKNOWN", f"{constraint['id']} has an effective window and no evaluation time")
        try:
            moment = utc_instant(evaluated_at)
            start = utc_instant(data["effective_from"]) if data["effective_from"] else None
            end = utc_instant(data["effective_until"]) if data["effective_until"] else None
        except ValueError:
            return ("unknown", "APPLICABILITY_UNKNOWN", f"{constraint['id']}: the evaluation time or the window is not "
                    "a UTC instant")
        if (start and moment < start) or (end and moment >= end):
            return ("unknown", "NOT_IN_EFFECT", f"{constraint['id']} is not in effect at {evaluated_at}")
    hard_invariant = data["predicate_role"] == "invariant" and data["classification"]["strength"] == "hard"
    if scenario["data"]["intent"] == "witness" and hard_invariant and expectation["expected"] is False:
        return ("fail", "WITNESS_VIOLATES_INVARIANT", f"a witness cannot expect hard invariant {constraint['id']} false")
    observed = bcir.evaluate(data["expression"], scenario["data"]["given"] if given is None else given, validator)
    if observed["result"] in ("unknown", "error"):
        return (observed["result"], "EVALUATION_" + observed["result"].upper(),
                f"{constraint['id']}: {observed['reason']}")
    if (observed["result"] == "pass") != expectation["expected"]:
        return ("fail", "EXPECTATION_MISMATCH", f"{constraint['id']} evaluated {observed['result']}, "
                f"expected {'true' if expectation['expected'] else 'false'}")
    return None


def check_test_plan(model, result):
    """G07: every active must requirement has an oracle; high/critical ones normal, negative and integration cases."""
    tests = {n["id"]: n for n in model.active("TestCase")}
    for node in model.active("Requirement"):
        verifying = [tests[t] for t in model.linked(node["id"], "verifies", "in") if t in tests]
        data, pointer = node["data"], model.where[node["id"]]
        if data["priority"] == "must" and not [t for t in verifying if t["data"]["oracle"].strip()]:
            result.add("G07", "fail", "MISSING_TEST", f"must requirement {node['id']} has no active test with an "
                       "oracle", node["id"], pointer)
        if data["risk"] in ("high", "critical") and verifying:
            if not [t for t in verifying if not t["data"]["negative"]]:
                result.add("G07", "fail", "MISSING_NORMAL_TEST", f"{data['risk']} {node['id']} has no normal case",
                           node["id"], pointer)
            if not [t for t in verifying if t["data"]["negative"]]:
                result.add("G07", "fail", "MISSING_NEGATIVE_TEST", f"{data['risk']} {node['id']} has no refusal case",
                           node["id"], pointer)
            if not [t for t in verifying if t["data"]["level"] in ("integration", "e2e")]:
                result.add("G07", "fail", "MISSING_INTEGRATION_TEST", f"{data['risk']} {node['id']} has no "
                           "integration or e2e case", node["id"], pointer)
    for test in tests.values():
        verified = set(model.linked(test["id"], "verifies"))
        for scenario in test["data"]["witness_scenario_ids"]:
            if scenario in model.nodes and not verified & set(model.linked(scenario, "illustrates")):
                result.add("G07", "fail", "SCENARIO_NOT_ILLUSTRATING", f"witness {scenario} illustrates none of the "
                           f"requirements {test['id']} verifies", test["id"], model.where[test["id"]])


def render_requirement(data):
    """AX-M-006: the English sentence of a structured requirement; connectives only, no added meaning."""
    conditions = " and ".join(data["conditions"])
    body = f"the {data['subject']} shall {data['response']}."
    pattern = data["pattern"]
    if pattern == "event":
        return f"When {data['trigger']}, {body}"
    if pattern == "state":
        return f"While {conditions}, {body}"
    if pattern == "unwanted":
        return f"If {data['trigger']}, then {body}"
    if pattern == "optional":
        return f"Where {data['feature']}, {body}"
    if pattern == "composite":
        return f"While {conditions}, when {data['trigger']}, {body}"
    return body[0].upper() + body[1:]


def toolchain_digest():
    """The toolkit's own bytes and the schemas it validates against: a change to either changes this digest."""
    files = sorted([*(ROOT / "tools/axiom").glob("*.py"), ROOT / "tools/axiom/axiom", *(ROOT / SCHEMA_DIR).glob("*.json")])
    return canonical_digest([[f.relative_to(ROOT).as_posix(), sha256(f.read_bytes())] for f in files if f.is_file()])


def report(result, phase_name, gates, spec_digest, evaluated_at, extra_limits=(), scope="baseline"):
    """The axiomspec-report/0.2 envelope: deterministic body, clock only in metadata. When G01 failed, the later
    gates never ran: each is reported unknown (NOT_RUN), never pass."""
    blocked = any(d["gate"] == "G01" and d["status"] == "error" for d in result.diagnostics)
    for gate in gates:
        if blocked and gate != "G01" and not any(d["gate"] == gate for d in result.diagnostics):
            result.add(gate, "unknown", "NOT_RUN", "not run: G01 rejected the document")
    checks = []
    for gate in gates:
        listed = [d for d in result.diagnostics if d["gate"] == gate]
        for index, d in enumerate(sorted(listed, key=lambda d: (d["code"], d["subject_id"] or "", d["pointer"]))):
            checks.append({"id": f"{gate}.{d['code']}.{index + 1}", "gate": gate, "status": d["status"],
                           "required": True, "subject_id": d["subject_id"], "pointer": d["pointer"],
                           "message": d["message"], "evidence": [], "limitations": []})
        if not listed:
            checks.append({"id": f"{gate}.ALL", "gate": gate, "status": "pass", "required": True, "subject_id": None,
                           "pointer": "", "message": f"{GATE_TITLES[gate]}: no diagnostic", "evidence": [],
                           "limitations": list(result.notes.get(gate, []))})
    status = result.phase(gates)
    return {"format": "axiomspec-report/0.2", "scope": scope, "status": status, "profile": "AX-CORE-0.1",
            "requested_phase": phase_name, "available_capabilities": CAPABILITIES,
            "unsupported_capabilities": UNSUPPORTED, "configuration": None,
            "subject": {"spec_sha256": spec_digest, "source_tree_sha256": None, "policy_sha256": None,
                        "toolchain_sha256": toolchain_digest(), "observations_sha256": None},
            "runner": {"name": "tools/axiom/axiom", "version": TOOL_VERSION, "trust": "untrusted_local"},
            "checks": checks,
            "bounds": {"max_input_bytes": 1048576, "max_expression_depth": bcir.MAX_DEPTH,
                       "max_expression_nodes": bcir.MAX_NODES, "max_steps": bcir.MAX_STEPS,
                       "max_collection_items": bcir.MAX_ITEMS},
            "metadata": {"evaluated_at": evaluated_at, "attempt": "local"},
            "limitations": ["Local untrusted runner: no identity attestation, trusted policy or production approval.",
                            "Declared links are claims; a passing gate does not establish business completeness.",
                            *extra_limits]}
