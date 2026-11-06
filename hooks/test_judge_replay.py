#!/usr/bin/env python3
"""Cases for hooks/judge_replay.py, the replay runner of the model judges' known allow and deny corpora.
Standard library only, and no test runner.

    python3 hooks/test_judge_replay.py

The runner, as the builder writes it. This file is its interface.

- JUDGES: name -> {"corpus": "hooks/judge_corpus/<name>.json", "scope": [repo-relative paths]}, for each name in NAMES.
  Each scope holds hooks/decision_watch.py, the one model seam, and the judge's own module file.
- A corpus is a JSON list of cases {"id": str, "expect": "allow" or "deny", "source": str, "input": object}, with an
  optional "agreement": str. Ids are unique in a file, and a corpus holds an allow case and a deny case.
- touched(paths): the sorted names whose scope holds a path, whose corpus is a path, or, for hooks/judge_replay.py, all.
- replay(name, runs=1): one row per case, {"id", "expect", "got", "verdict"}. got is allow, deny or unknown. Each model
  call goes through decision_watch.invoke_model, looked up at call time, so this file replaces it. Every judge makes one
  call per case, feedback_guard included, even where its prompt could batch.
- main(argv) returns the exit code. --changed BASE, --judge NAME and --all. An UNKNOWN exits 1 when env CI is set, else 0.

The fake answers (None, "no auth"), the pair decision_watch.invoke_model returns for a failed call, so no case needs the
network or the claude binary. A missing runner fails each case by name, never with a traceback. The suite writes no temp
files. Its one git read is the committed diff of HEAD against itself, which is empty whatever the working tree holds.
"""
import contextlib
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
os.chdir(REPO)  # the runner reads git and the scope paths from the repository root

import decision_watch  # noqa: E402  the one model seam; the runner looks invoke_model up here at call time

try:
    import judge_replay  # noqa: E402
    IMPORT_FAULT = ""
except Exception as error:  # the missing runner is the red; each case names it
    judge_replay = None
    IMPORT_FAULT = "%s: %s" % (type(error).__name__, error)

FAILED = []
NAMES = ("call_judge.spawn", "call_judge.question", "call_judge.page", "call_judge.opus_ask", "call_judge.opus_scope",
         "prose_judge", "reply_judge", "feedback_guard", "report_guard.past_ruling", "sendmessage_state",
         "decision_watch")
SEAM = "hooks/decision_watch.py"
OWN_FILES = {
    "call_judge.spawn": ("hooks/call_judge.py",),
    "call_judge.question": ("hooks/call_judge.py",),
    "call_judge.page": ("hooks/call_judge.py",),
    "call_judge.opus_ask": ("hooks/call_judge.py",),
    "call_judge.opus_scope": ("hooks/call_judge.py",),
    "prose_judge": ("hooks/prose_judge.py",),
    "reply_judge": ("hooks/reply_judge.py",),
    "feedback_guard": ("hooks/feedback_guard.py",),
    "report_guard.past_ruling": ("lint/report_guard.py", "hooks/call_judge.py"),
    "sendmessage_state": ("hooks/sendmessage_state.py",),
    "decision_watch": ("hooks/decision_watch.py",),
}
TOUCH = (
    ([], []),
    (["README.md"], []),
    (["hooks/decision_watch.py"], "all"),
    (["hooks/judge_replay.py"], "all"),
    (["hooks/prose_judge.py"], ["prose_judge"]),
    (["hooks/judge_corpus/reply_judge.json"], ["reply_judge"]),
)
NO_AUTH = (None, "no auth")
SELF_FILES = ("hooks/judge_replay.py", "hooks/test_judge_replay.py")
NAMED = re.compile(rb"judge[_-]replay")


def check(name, ok, detail=""):
    if ok:
        print("ok   " + name)
    else:
        FAILED.append(name)
        print("FAIL " + name + (" :: " + str(detail) if detail else ""))


def need_runner(label):
    """The runner module, or None after a named failure of `label`."""
    if judge_replay is None:
        check(label, False, "hooks/judge_replay.py does not import: " + IMPORT_FAULT)
    return judge_replay


def judges_or_fail(label):
    """The runner's JUDGES dict, or None after a named failure of `label`."""
    if need_runner(label) is None:
        return None
    judges = getattr(judge_replay, "JUDGES", None)
    if not isinstance(judges, dict):
        check(label, False, "hooks/judge_replay.py has no JUDGES dict")
        return None
    return judges


@contextlib.contextmanager
def faked_model(answer):
    """decision_watch.invoke_model replaced by a fake that returns `answer` and records each call. The real one is restored after."""
    real = decision_watch.invoke_model
    calls = []

    def fake(*args, **kwargs):
        calls.append((args, kwargs))
        return answer

    decision_watch.invoke_model = fake
    try:
        yield calls
    finally:
        decision_watch.invoke_model = real


@contextlib.contextmanager
def ci_env(value):
    """Env CI set to `value`, or unset for None. The value it had is put back after."""
    saved = os.environ.pop("CI", None)
    if value is not None:
        os.environ["CI"] = value
    try:
        yield
    finally:
        os.environ.pop("CI", None)
        if saved is not None:
            os.environ["CI"] = saved


def load_corpus(name):
    """(cases, "") for hooks/judge_corpus/<name>.json, or (None, reason) when it is missing or does not parse."""
    rel = "hooks/judge_corpus/%s.json" % name
    try:
        with open(os.path.join(REPO, rel), encoding="utf-8") as f:
            return json.load(f), ""
    except OSError:
        return None, "%s is missing or unreadable" % rel
    except ValueError as error:
        return None, "%s does not parse: %s" % (rel, error)


def shape_problem(cases):
    """The first way a corpus's cases break the shape, or "" when every case has it."""
    if not isinstance(cases, list) or not cases:
        return "not a non-empty JSON list"
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            return "case %d is not an object" % index
        cid = case.get("id")
        if not isinstance(cid, str) or not cid.strip():
            return "case %d has no id" % index
        if case.get("expect") not in ("allow", "deny"):
            return "case %r has expect %r, not allow or deny" % (cid, case.get("expect"))
        source = case.get("source")
        if not isinstance(source, str) or not source.strip():
            return "case %r has no source" % cid
        if not isinstance(case.get("input"), dict):
            return "case %r has no input object" % cid
        if "agreement" in case and not isinstance(case["agreement"], str):
            return "case %r has a non-string agreement" % cid
    return ""


def run_main(argv):
    """main(argv), its exit code. A SystemExit reads as the code it carries."""
    try:
        return judge_replay.main(argv)
    except SystemExit as error:
        return error.code


def case_seam_control():
    """Green on main: the seam the fake replaces is real, and the fake is undone when its block ends."""
    real = decision_watch.invoke_model
    check("seam: decision_watch.invoke_model is a function", callable(real), "decision_watch has no invoke_model")
    with faked_model(NO_AUTH):
        pass
    check("seam: faked_model restores the real invoke_model", decision_watch.invoke_model is real,
          "the fake outlived its block")


def case_corpora():
    judges = judges_or_fail("corpora: JUDGES is readable")
    if judges is None:
        return
    for name in NAMES:
        check("JUDGES has %s" % name, name in judges, "JUDGES has no %r" % name)
        if name not in judges:
            continue
        entry = judges[name] if isinstance(judges[name], dict) else {}
        rel = "hooks/judge_corpus/%s.json" % name
        check("corpus path is %s: %s" % (rel, name), entry.get("corpus") == rel,
              "corpus is %r" % (entry.get("corpus"),))
        cases, problem = load_corpus(name)
        check("corpus reads: %s" % name, cases is not None, problem)
        if cases is None:
            continue
        shape = shape_problem(cases)
        check("corpus cases well formed: %s" % name, not shape, shape)
        ids = [repr(case.get("id")) for case in cases if isinstance(case, dict)]
        repeated = sorted({i for i in ids if ids.count(i) > 1})
        check("corpus ids unique: %s" % name, not repeated, "repeated ids: %s" % ", ".join(repeated))
        expects = [case.get("expect") for case in cases if isinstance(case, dict)]
        check("corpus has an allow case: %s" % name, "allow" in expects, "no case expects allow")
        check("corpus has a deny case: %s" % name, "deny" in expects, "no case expects deny")


def case_scopes():
    judges = judges_or_fail("scopes: JUDGES is readable")
    if judges is None:
        return
    for name in NAMES:
        entry = judges.get(name) if isinstance(judges.get(name), dict) else {}
        scope = entry.get("scope")
        if not isinstance(scope, list) or not all(isinstance(p, str) for p in scope):
            check("scope is a list of paths: %s" % name, False, "no scope list in JUDGES[%r]" % name)
            continue
        need = [SEAM] + list(OWN_FILES[name])
        lacks = [p for p in need if p not in scope]
        check("scope holds the seam and its module: %s" % name, not lacks, "scope lacks %s" % ", ".join(lacks))
        gone = [p for p in scope
                if os.path.isabs(p) or ".." in p.split("/") or not os.path.exists(os.path.join(REPO, p))]
        check("scope paths exist: %s" % name, not gone, "no such path: %s" % ", ".join(gone))


def case_touched():
    judges = judges_or_fail("touched: JUDGES is readable")
    if judges is None:
        return
    everything = sorted(judges)
    with faked_model(NO_AUTH) as calls:
        for paths, want in TOUCH:
            label = "touched %s" % (paths,)
            try:
                got = judge_replay.touched(paths)
            except Exception as error:
                check(label, False, "raised %s: %s" % (type(error).__name__, error))
                continue
            expected = everything if want == "all" else want
            check(label, got == expected, "got %r, want %r" % (got, expected))
    check("touched makes no model call", not calls, "%d model calls" % len(calls))


def case_no_auth_rows():
    judges = judges_or_fail("no-auth: JUDGES is readable")
    if judges is None:
        return
    for name in NAMES:
        cases, problem = load_corpus(name)
        if cases is None:
            check("no-auth rows: %s" % name, False, problem)
            continue
        with faked_model(NO_AUTH) as calls:
            try:
                rows = judge_replay.replay(name)
            except Exception as error:
                rows = None
                failure = "replay raised %s: %s" % (type(error).__name__, error)
        if rows is None:
            check("no-auth rows: %s" % name, False, failure)
            continue
        if not isinstance(rows, list) or not rows:
            check("no-auth rows: %s" % name, False, "replay gave no row list")
            continue
        wrong = [r for r in rows if not (isinstance(r, dict) and r.get("got") == "unknown"
                                         and r.get("verdict") == "UNKNOWN")]
        check("no-auth rows read UNKNOWN: %s" % name, not wrong, "row %r" % (wrong[0],) if wrong else "")
        check("no-auth one model call per case: %s" % name, len(calls) == len(cases),
              "%d calls for %d cases" % (len(calls), len(cases)))
        got_pairs = sorted(repr((r.get("id"), r.get("expect"))) for r in rows if isinstance(r, dict))
        want_pairs = sorted(repr((c.get("id"), c.get("expect"))) for c in cases if isinstance(c, dict))
        check("no-auth one row per case: %s" % name, got_pairs == want_pairs,
              "rows %s, cases %s" % (len(got_pairs), len(want_pairs)))


def case_cli_exit_follows_ci():
    label = "--judge exit under CI"
    if need_runner(label) is None:
        return
    for value, want in (("1", 1), (None, 0)):
        tag = "CI=%s" % value if value is not None else "CI unset"
        error = None
        with ci_env(value), faked_model(NO_AUTH) as calls, contextlib.redirect_stdout(io.StringIO()) as out:
            try:
                code = run_main(["--judge", "prose_judge"])
            except Exception as exc:
                error = exc
        if error is not None:
            check("%s, %s" % (label, tag), False, "raised %s: %s" % (type(error).__name__, error))
            continue
        check("--judge prose_judge reaches the model, %s" % tag, bool(calls), "no model call")
        check("--judge prose_judge prints UNKNOWN, %s" % tag, "UNKNOWN" in out.getvalue(), out.getvalue()[-200:])
        check("--judge prose_judge exits %d, %s" % (want, tag), code == want, "exit %r" % (code,))


def case_cli_changed_head():
    label = "--changed HEAD"
    if need_runner(label) is None:
        return
    error = None
    with faked_model(NO_AUTH) as calls, contextlib.redirect_stdout(io.StringIO()) as out:
        try:
            code = run_main(["--changed", "HEAD"])
        except Exception as exc:
            error = exc
    if error is not None:
        check(label, False, "raised %s: %s" % (type(error).__name__, error))
        return
    check("%s prints no judge touched" % label, "no judge touched" in out.getvalue(), out.getvalue()[-200:])
    check("%s exits 0" % label, code == 0, "exit %r" % (code,))
    check("%s makes no model call" % label, not calls, "%d model calls" % len(calls))


def case_runner_named_nowhere_else():
    scanned = 0
    named = []
    for top in ("hooks", "lint"):
        for root, dirs, files in os.walk(os.path.join(REPO, top)):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in files:
                rel = os.path.relpath(os.path.join(root, name), REPO).replace(os.sep, "/")
                if rel in SELF_FILES:
                    continue
                scanned += 1
                with open(os.path.join(root, name), "rb") as f:
                    if NAMED.search(f.read()):
                        named.append(rel)
    check("scan reached files under hooks/ and lint/", scanned > 0, "no files scanned")
    with open(os.path.join(REPO, "settings.json"), "rb") as f:
        if NAMED.search(f.read()):
            named.append("settings.json")
    check("no file under hooks/ or lint/, and settings.json, names the runner", not named,
          "names it: %s" % ", ".join(named[:5]))


CASES = (case_seam_control, case_corpora, case_scopes, case_touched, case_no_auth_rows,
         case_cli_exit_follows_ci, case_cli_changed_head, case_runner_named_nowhere_else)


def main():
    for case in CASES:
        try:
            case()
        except Exception as error:
            check(case.__name__, False, "raised %s: %s" % (type(error).__name__, error))
    print("FAIL: %d failed" % len(FAILED) if FAILED else "all checks passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
