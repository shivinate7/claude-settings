"""A test stand-in for hooks/guard_load.py, copied as hooks/guard_load.py beside a copy of a tool under test
(lint/test_sim_lease.py and lint/test_sim_test.sh). Every name of the real module is the real one, load_verdict and
the limits included. Only read_load is replaced: it returns the reading the test wrote as JSON to the file named by
FAKE_LOAD_READING, and it appends one line to FAKE_LOAD_LOG per read. FAKE_LOAD_REAL is the path of the real
module. Test-only seam: no production code reads these names.
"""
import importlib.util
import json
import os

_real_spec = importlib.util.spec_from_file_location("guard_load_real", os.environ["FAKE_LOAD_REAL"])
_real = importlib.util.module_from_spec(_real_spec)
_real_spec.loader.exec_module(_real)
for _name, _value in vars(_real).items():
    if not _name.startswith("__"):
        globals()[_name] = _value


def read_load():
    log = os.environ.get("FAKE_LOAD_LOG")
    if log:
        with open(log, "a") as f:
            f.write("read\n")
    with open(os.environ["FAKE_LOAD_READING"]) as f:
        return json.load(f)
