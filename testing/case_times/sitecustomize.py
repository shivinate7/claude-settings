"""Arms per-case timing when env CASE_TIMES=1 (decision per-case-times).

Python imports this file at startup when its folder is on PYTHONPATH, so a job sets the path and the env once
and every process it starts is covered. Unarmed, this file only runs the next sitecustomize on sys.path.

Armed (CASE_TIMES=1 and RUNNER_TEMP set), it latches the job file in case_times.arm() and puts one import hook
on sys.meta_path. When unittest.result first loads, the hook removes CASE_TIMES from the env, so the children a
suite starts stay unarmed, and it patches TestResult and TestCase's fixture calls so each test method is recorded.
When unittest.async_case loads (only when a case uses IsolatedAsyncioTestCase), it patches that class's fixture
calls. A process that never imports unittest records nothing and writes no file.
"""
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
OWN = os.path.realpath(__file__)
# unittest/__init__ loads unittest.result on every `import unittest`. unittest.async_case loads only when a case uses
# IsolatedAsyncioTestCase, so the second target never imports asyncio.
TARGETS = ("unittest.result", "unittest.async_case")


class _UnittestHook(object):
    """A meta path finder that lets the real loader run, then patches the unittest module it loaded."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname not in TARGETS:
            return None
        import importlib.machinery
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.loader is None:
            return None
        load = spec.loader.exec_module

        def exec_module(module):
            load(module)
            import case_times
            if fullname == "unittest.result":
                os.environ.pop("CASE_TIMES", None)  # the children this process starts stay unarmed
                case_times.patch_result(module.TestResult)
                case_times.patch_case()  # guards its own reads: a Python without TestCase._callSetUp runs unwrapped
                return
            try:  # a broken async patch must never break the import: the module loads unpatched
                case_times.patch_async_case(module)
            except Exception as error:
                sys.stderr.write("case_times: not armed for %s: %s\n" % (fullname, error))

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


def _is_home(path):
    """True for this home's own file and for a copy of it: a sitecustomize.py that sits beside a case_times.py.
    A copy that the chain ran would chain back to this one, so no copy is ever run from here."""
    real = os.path.realpath(path)
    return real == OWN or os.path.isfile(os.path.join(os.path.dirname(real), "case_times.py"))


def _chain():
    """Run the next sitecustomize.py on sys.path, the one Python would have run without this file."""
    for entry in sys.path:
        candidate = os.path.join(entry or os.curdir, "sitecustomize.py")
        if os.path.isfile(candidate) and not _is_home(candidate):
            with open(candidate, "rb") as f:
                code = compile(f.read(), candidate, "exec")
            exec(code, {"__name__": "sitecustomize", "__file__": candidate})
            return


try:
    _arm()
except Exception as error:  # a broken arm must never break a Python start: the process runs unarmed
    sys.stderr.write("case_times: not armed: %s\n" % error)
_chain()
