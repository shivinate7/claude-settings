"""Arms per-case timing when env CASE_TIMES=1 (decision per-case-times).

Python imports this file at startup when its folder is on PYTHONPATH, so a job sets the path and the env once
and every process it starts is covered. Unarmed, this file only runs the next sitecustomize on sys.path.

Armed (CASE_TIMES=1 and RUNNER_TEMP set), it latches the job file in case_times.arm() and puts one import hook
on sys.meta_path. When unittest.result first loads, the hook removes CASE_TIMES from the env, so the children a
suite starts stay unarmed, and it patches TestResult so each test method is recorded. A process that never
imports unittest records nothing and writes no file.
"""
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
OWN = os.path.realpath(__file__)
TARGET = "unittest.result"  # unittest/__init__ loads it on every `import unittest`, so the hook fires there


class _UnittestHook(object):
    """A meta path finder that lets the real loader run, then patches TestResult and drops CASE_TIMES."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname != TARGET:
            return None
        import importlib.machinery
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.loader is None:
            return None
        load = spec.loader.exec_module

        def exec_module(module):
            load(module)
            os.environ.pop("CASE_TIMES", None)
            import case_times
            case_times.patch_result(module.TestResult)

        spec.loader.exec_module = exec_module
        return spec


def _arm():
    if os.environ.get("CASE_TIMES") != "1":
        return
    folder = os.environ.get("RUNNER_TEMP")
    if not folder:
        return
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import case_times
    case_times.arm(os.path.join(folder, "case-times", (os.environ.get("GITHUB_JOB") or "local") + ".jsonl"))
    sys.meta_path.insert(0, _UnittestHook())


def _chain():
    """Run the next sitecustomize.py on sys.path, the one Python would have run without this file."""
    for entry in sys.path:
        candidate = os.path.join(entry or os.curdir, "sitecustomize.py")
        if os.path.isfile(candidate) and os.path.realpath(candidate) != OWN:
            with open(candidate, "rb") as f:
                code = compile(f.read(), candidate, "exec")
            exec(code, {"__name__": "sitecustomize", "__file__": candidate})
            return


try:
    _arm()
except Exception as error:  # a broken arm must never break a Python start: the process runs unarmed
    sys.stderr.write("case_times: not armed: %s\n" % error)
_chain()
