# Spec: knowledge/components/axiom-toolkit.md
"""The fixed unittest runner behind `axiom evidence run`: imports one test file as its own script would, runs
one test name, prints one JSON line. Standard library only, and started with -P (evidence.adapter_command): no
toolkit module may sit where the project's tests import theirs, while PYTHONPATH still applies."""
import io
import json
import sys
import unittest
from pathlib import Path, PurePosixPath


class _Recorder(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.outcomes = {}

    def addSuccess(self, test):
        self.outcomes[test.id()] = "pass"

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.outcomes[test.id()] = "fail"

    def addError(self, test, err):
        super().addError(test, err)
        self.outcomes[test.id()] = "error"

    def addSkip(self, test, reason):
        self.outcomes[test.id()] = "skip"

    def addExpectedFailure(self, test, err):
        self.outcomes[test.id()] = "fail"

    def addUnexpectedSuccess(self, test):
        self.outcomes[test.id()] = "fail"


def _adapter(path, symbol):
    """Adapter mode: import one test file as its own script would, run one name, print one JSON line."""
    import importlib.util
    folder = str(Path(path).resolve().parent)
    sys.path.insert(0, folder)
    name = "axiom_bound_" + PurePosixPath(path).stem
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    output = io.StringIO()
    try:
        spec.loader.exec_module(module)
        suite = unittest.defaultTestLoader.loadTestsFromName(symbol, module)
    except Exception as error:  # an import or lookup failure is a reported error, not a crash
        print(json.dumps({"results": {}, "error": f"{type(error).__name__}: {error}"}))
        return
    recorder = _Recorder()
    stream, sys.stdout = sys.stdout, output
    try:
        suite.run(recorder)
    finally:
        sys.stdout = stream
    results = {test_id.replace(name + ".", "", 1): outcome for test_id, outcome in recorder.outcomes.items()}
    sys.stderr.write(output.getvalue())
    for _, trace in recorder.failures + recorder.errors:
        sys.stderr.write(trace)
    print(json.dumps({"results": results}))


if __name__ == "__main__" and len(sys.argv) == 3:
    _adapter(sys.argv[1], sys.argv[2])
