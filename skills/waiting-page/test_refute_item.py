"""Cases for skills/waiting-page/refute_item.py, the blind refuter. It writes `against`, the best case against
the recommended pick, onto one waiting-page decision. Run: python3 skills/waiting-page/test_refute_item.py

REFUTE_ITEM_UNDER_TEST names the script to load (default: refute_item.py beside this file).

The contract the script must match:
- main(argv, model_call=None) -> int. argv is [<item.json>]. It prints one verdict line and returns the exit code.
- model_call, when given, is called as model_call(prompt, model=REFUTER_MODEL, shape=REFUTER_SHAPE,
  effort=REFUTER_EFFORT) in place of decision_watch.invoke_model. When it is None, the script looks up
  decision_watch.invoke_model at call time, so a patch of that module attribute takes effect.
- Module constants: REFUTER_MODEL == "sonnet", REFUTER_SHAPE == {"verdict": ("AGAINST",)}, REFUTER_EFFORT.
- In scope: kind "decision", status not "closed", options a non-empty list, and a pick: a str, or a non-empty
  list when multi. Each in-scope item makes exactly one call. The prompt holds the context, each option's
  label, how, gain and lose, and the pick key or keys. It never holds the why text.
- Out of scope: no call, the file is not written, exit 0.
- A written case: the model's "case" text, stripped, is the item's `against`. Every other key is kept. Exit 0.
- Unknown (the call returns (None, err), or "case" is missing, empty or not a string): `against` is
  "unknown (<reason>)". The verdict line says unknown and never ok. Exit 0, or 1 when env CI is set.

No case calls a real model. The stub answers each call, PATH is emptied, and the credential read is patched out,
so a call that reaches the real invoke_model fails before any model or credential is touched.
"""
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.realpath(os.path.join(HERE, "..", "..", "hooks"))
LINT = os.path.realpath(os.path.join(HERE, "..", "..", "lint"))
sys.path.insert(0, HOOKS)
sys.path.insert(0, LINT)
import decision_watch  # noqa: E402  the one home of invoke_model
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)

CMD = os.environ.get("REFUTE_ITEM_UNDER_TEST") or os.path.join(HERE, "refute_item.py")
RUN_FOLDER = None
SAVED_PATH = None
CREDENTIAL_GUARD = None

# Markers the blindness case looks for. Each is unique, so a prompt that holds one holds that text.
WHY = "WHY-MARK-91c2: the owner's ruling says otherwise."
CONTEXT = "Goal: CTX-MARK-7f3a the batch runner merges alone."
OPT_A = {"key": "a", "label": "LABEL-A-Keep", "how": "HOW-A-runs-the-check", "gain": "GAIN-A-quiet",
         "lose": "LOSE-A-slow"}
OPT_B = {"key": "b", "label": "LABEL-B-Switch", "how": "HOW-B-merges-alone", "gain": "GAIN-B-fast",
         "lose": "LOSE-B-extra-form"}
OPTION_MARKERS = ("LABEL-A-Keep", "HOW-A-runs-the-check", "GAIN-A-quiet", "LOSE-A-slow",
                  "LABEL-B-Switch", "HOW-B-merges-alone", "GAIN-B-fast", "LOSE-B-extra-form")
CASE_REPLY = ({"verdict": "AGAINST", "case": "The case."}, None)
WRITE_REPLY = ({"verdict": "AGAINST", "case": "A case that must not be written unless the item is in scope."}, None)


def item(**over):
    """An in-scope decision: open, two options, pick b, and the why text the prompt must not hold."""
    found = {"id": "wrote-q", "n": 40, "kind": "decision", "status": "open", "title": "Let the runner merge alone?",
             "context": CONTEXT, "options": [OPT_A, OPT_B], "pick": "b", "why": WHY}
    found.update(over)
    return found


def without(data, key):
    data = dict(data)
    data.pop(key)
    return data


OUT_OF_SCOPE = {
    "a task": lambda: dict(item(), kind="task", steps=["Plug in the Mac"]),
    "a closed decision": lambda: item(status="closed"),
    "a decision with no pick": lambda: without(item(), "pick"),
    "a decision with an empty pick": lambda: item(pick=""),
    "a decision with no options": lambda: item(options=[]),
    "a list pick that is not multi": lambda: item(pick=["b"]),
}

UNKNOWN_REPLIES = {
    "the model call failed": (None, "model subprocess timed out"),
    "the case is missing": ({"verdict": "AGAINST"}, None),
    "the case is empty": ({"verdict": "AGAINST", "case": "   "}, None),
    "the case is not a string": ({"verdict": "AGAINST", "case": 7}, None),
    "the case is a list": ({"verdict": "AGAINST", "case": ["a case"]}, None),
}


class Stub:
    """A model_call stand-in: records each call, and answers `reply`."""

    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.reply


def setUpModule():
    global RUN_FOLDER, SAVED_PATH, CREDENTIAL_GUARD
    RUN_FOLDER = _test_temp.run_folder()
    empty_bin = os.path.join(RUN_FOLDER, "no-bin")
    os.makedirs(empty_bin)
    SAVED_PATH = os.environ.get("PATH")
    os.environ["PATH"] = empty_bin  # no `claude` on the path: a call that reaches the real model cannot start
    # A call that reaches the real invoke_model reads no credential file: the isolation step refuses at once.
    CREDENTIAL_GUARD = mock.patch.object(decision_watch, "_judge_isolation", side_effect=decision_watch.TokenUnreadable)
    CREDENTIAL_GUARD.start()


def tearDownModule():
    CREDENTIAL_GUARD.stop()
    if SAVED_PATH is not None:
        os.environ["PATH"] = SAVED_PATH
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def load_refute():
    """The script under test, loaded fresh. A checkout without the script fails each case by name."""
    if not os.path.exists(CMD):
        raise AssertionError("refute_item.py is not on this checkout (%s)" % CMD)
    spec = importlib.util.spec_from_file_location("refute_item_under_test", CMD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_item(name, data):
    path = os.path.join(RUN_FOLDER, name + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_main(refute, path, **kwargs):
    """main([path], **kwargs) with stdout and stderr captured: (exit code, the printed text)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = refute.main([path], **kwargs)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue() + err.getvalue()


def prompt_for(refute, **over):
    """The prompt the script sends for an in-scope item with `over`, from a stub that is called once."""
    path = write_item("probe", item(**over))
    stub = Stub(CASE_REPLY)
    run_main(refute, path, model_call=stub)
    return stub.calls[0][0][0] if stub.calls else None


class RefuteItem(unittest.TestCase):

    def test_the_refuter_constants_are_pinned(self):
        refute = load_refute()
        self.assertEqual(getattr(refute, "REFUTER_MODEL", None), "sonnet", "REFUTER_MODEL is not sonnet")
        self.assertEqual(getattr(refute, "REFUTER_SHAPE", None), {"verdict": ("AGAINST",)},
                         "REFUTER_SHAPE is not the AGAINST verdict shape")
        self.assertTrue(hasattr(refute, "REFUTER_EFFORT"), "REFUTER_EFFORT is not a module constant")

    def test_an_in_scope_decision_makes_one_call_and_writes_its_case(self):
        refute = load_refute()
        path = write_item("in-scope", item())
        stub = Stub(CASE_REPLY)
        code, _ = run_main(refute, path, model_call=stub)
        self.assertEqual(len(stub.calls), 1, "an in-scope decision makes %d model calls, want 1" % len(stub.calls))
        args, kwargs = stub.calls[0]
        self.assertEqual(len(args), 1, "the prompt is not the one positional argument of the model call")
        self.assertEqual(set(kwargs), {"model", "shape", "effort"},
                         "the model call is passed %s, want model, shape and effort" % sorted(kwargs))
        self.assertEqual(kwargs["model"], "sonnet", "the call's model is not REFUTER_MODEL")
        self.assertEqual(kwargs["shape"], {"verdict": ("AGAINST",)}, "the call's shape is not REFUTER_SHAPE")
        self.assertEqual(kwargs["effort"], getattr(refute, "REFUTER_EFFORT", "<missing>"),
                         "the call's effort is not REFUTER_EFFORT")
        self.assertEqual(code, 0, "a written case exits %r, want 0" % (code,))
        self.assertEqual(read_json(path), dict(item(), against="The case."),
                         "the file is not the item with against written and every other key kept")

    def test_with_no_model_call_the_module_attribute_is_called(self):
        refute = load_refute()
        path = write_item("default", item())
        with mock.patch.object(decision_watch, "invoke_model", return_value=CASE_REPLY) as call:
            run_main(refute, path)
        self.assertEqual(call.call_count, 1,
                         "with no model_call, decision_watch.invoke_model is called %d times, want 1; "
                         "the default is bound before the patch" % call.call_count)
        self.assertEqual(set(call.call_args[1]), {"model", "shape", "effort"},
                         "the default call is passed %s, want model, shape and effort" % sorted(call.call_args[1]))
        self.assertEqual(read_json(path)["against"], "The case.", "the default call's case was not written")

    def test_the_case_text_is_stripped_before_it_is_written(self):
        refute = load_refute()
        path = write_item("stripped", item())
        run_main(refute, path, model_call=Stub(({"verdict": "AGAINST", "case": "  The case.  \n"}, None)))
        self.assertEqual(read_json(path)["against"], "The case.", "against is not the case text, stripped")

    def test_the_prompt_holds_the_item_and_never_the_why_text(self):
        refute = load_refute()
        path = write_item("blind", item())
        stub = Stub(CASE_REPLY)
        run_main(refute, path, model_call=stub)
        self.assertEqual(len(stub.calls), 1, "the blindness case did not reach the model call")
        prompt = stub.calls[0][0][0]
        self.assertNotIn("WHY-MARK-91c2", prompt, "the prompt holds the why text, so the refuter is not blind")
        self.assertIn("CTX-MARK-7f3a", prompt, "the prompt lacks the context")
        for marker in OPTION_MARKERS:
            self.assertIn(marker, prompt, "the prompt lacks option text %s" % marker)

    def test_the_pick_key_reaches_the_prompt(self):
        refute = load_refute()
        pick_a, pick_b = prompt_for(refute, pick="a"), prompt_for(refute, pick="b")
        self.assertIsNotNone(pick_a, "a pick of a made no model call")
        self.assertIsNotNone(pick_b, "a pick of b made no model call")
        self.assertNotEqual(pick_a, pick_b, "the prompt is the same for pick a and pick b, so the pick is not in it")

    def test_every_key_of_a_multi_pick_reaches_the_prompt(self):
        refute = load_refute()
        both = prompt_for(refute, multi=True, pick=["a", "b"])
        only_a = prompt_for(refute, multi=True, pick=["a"])
        only_b = prompt_for(refute, multi=True, pick=["b"])
        self.assertIsNotNone(both, "a multi pick of a and b made no model call")
        self.assertNotEqual(both, only_a, "the prompt for [a, b] is the prompt for [a]: key b is not in it")
        self.assertNotEqual(both, only_b, "the prompt for [a, b] is the prompt for [b]: key a is not in it")

    def test_out_of_scope_items_make_no_call_and_are_not_written(self):
        refute = load_refute()
        for name, make in OUT_OF_SCOPE.items():
            with self.subTest(item=name):
                path = write_item("out-" + re.sub(r"\W+", "-", name), make())
                before = read_bytes(path)
                stub = Stub(WRITE_REPLY)
                code, _ = run_main(refute, path, model_call=stub)
                self.assertEqual(len(stub.calls), 0, "%s makes a model call, want none" % name)
                self.assertEqual(read_bytes(path), before, "%s is written, want the file unchanged" % name)
                self.assertEqual(code, 0, "%s exits %r, want 0" % (name, code))

    def test_a_multi_decision_with_a_pick_list_is_in_scope(self):
        refute = load_refute()
        path = write_item("multi", item(multi=True, pick=["b"]))
        stub = Stub(CASE_REPLY)
        run_main(refute, path, model_call=stub)
        self.assertEqual(len(stub.calls), 1,
                         "a multi decision with a pick list makes %d calls, want 1" % len(stub.calls))
        self.assertEqual(read_json(path)["against"], "The case.", "a multi decision was not written")

    def test_a_failed_call_writes_its_reason_as_unknown(self):
        refute = load_refute()
        path = write_item("failed", item())
        run_main(refute, path, model_call=Stub((None, "model subprocess timed out")))
        self.assertEqual(read_json(path)["against"], "unknown (model subprocess timed out)",
                         "a failed call did not write against as unknown with its reason")

    def test_an_unknown_case_is_written_as_unknown_and_says_so(self):
        refute = load_refute()
        for name, reply in UNKNOWN_REPLIES.items():
            with self.subTest(reply=name):
                path = write_item("unk-" + re.sub(r"\W+", "-", name), item())
                code, text = run_main(refute, path, model_call=Stub(reply))
                written = read_json(path)
                against = written.get("against")
                self.assertTrue(isinstance(against, str) and against.startswith("unknown (")
                                and against.endswith(")"),
                                "%s: against is %r, want unknown (<reason>)" % (name, against))
                self.assertEqual(written, dict(item(), against=against),
                                 "%s: the file lost a key other than against" % name)
                self.assertRegex(text, r"(?i)\bunknown\b", "%s: the verdict line does not say unknown" % name)
                self.assertNotRegex(text, r"(?i)\bok\b", "%s: the verdict line says ok on an unknown" % name)
                self.assertEqual(code, 0, "%s: exit %r with CI unset, want 0" % (name, code))

    def test_a_written_case_says_ok_on_the_verdict_line(self):
        refute = load_refute()
        path = write_item("ok-line", item())
        _, text = run_main(refute, path, model_call=Stub(CASE_REPLY))
        self.assertRegex(text, r"(?i)\bok\b", "the verdict line of a written case does not say ok")
        self.assertNotRegex(text, r"(?i)\bunknown\b", "the verdict line of a written case says unknown")

    def test_unknown_exits_zero_without_ci_and_one_with_ci(self):
        refute = load_refute()
        failed = (None, "model subprocess timed out")
        path = write_item("ci-unset", item())
        with mock.patch.dict(os.environ):
            os.environ.pop("CI", None)
            code_unset, _ = run_main(refute, path, model_call=Stub(failed))
        path = write_item("ci-set", item())
        with mock.patch.dict(os.environ, {"CI": "1"}):
            code_set, _ = run_main(refute, path, model_call=Stub(failed))
        self.assertEqual(code_unset, 0, "unknown exits %r with CI unset, want 0" % (code_unset,))
        self.assertEqual(code_set, 1, "unknown exits %r with CI set, want 1" % (code_set,))

    def test_a_written_case_exits_zero_with_ci_set(self):
        refute = load_refute()
        path = write_item("ci-ok", item())
        with mock.patch.dict(os.environ, {"CI": "1"}):
            code, _ = run_main(refute, path, model_call=Stub(CASE_REPLY))
        self.assertEqual(code, 0, "a written case exits %r with CI set, want 0" % (code,))

    def test_the_command_line_leaves_an_out_of_scope_item_unchanged(self):
        if not os.path.exists(CMD):
            raise AssertionError("refute_item.py is not on this checkout (%s)" % CMD)
        path = write_item("cli-task", dict(item(), kind="task"))
        before = read_bytes(path)
        env = {k: v for k, v in os.environ.items() if k != "CI"}
        proc = subprocess.run([sys.executable, CMD, path], capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(proc.returncode, 0,
                         "python3 refute_item.py exits %d on an out-of-scope item: %s" % (proc.returncode,
                                                                                          proc.stderr[-300:]))
        self.assertEqual(read_bytes(path), before, "the command line wrote an out-of-scope item")


if __name__ == "__main__":
    unittest.main()
