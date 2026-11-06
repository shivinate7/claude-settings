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
- --changed BASE names every judge when the committed diff changes the claude-code pin line in
  .github/workflows/checks.yml. The pin cases set judge_replay.REPO to a two-commit temp repo, since --changed reads git there.
- --probe: one call. Exit 1 with the secret's name and waiting page item 283 when the call fails, else exit 0.

The fake answers (None, "no auth"), the pair decision_watch.invoke_model returns for a failed call, so no case needs the
network or the claude binary. A missing runner fails each case by name, never with a traceback. The one temp folder is this
run's folder from lint/_test_temp.py (test-temp-standard), made in main() and removed at its end. The git read of
--changed HEAD is the committed diff of HEAD against itself, which is empty whatever the working tree holds.
"""
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "lint"))
os.chdir(REPO)  # the runner reads git and the scope paths from the repository root

import decision_watch  # noqa: E402  the one model seam; the runner looks invoke_model up here at call time
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py), for the pin repos' commits
import _test_temp  # noqa: E402  test-temp-standard: this run's folder (lint/_test_temp.py)

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
    (["hooks/shared_names.py"], "all"),
    (["hooks/guard.py"], "all"),
)
NO_AUTH = (None, "no auth")
# lint/test_ci_scope.py pins the CI scope's judge_replay flag, so it names the runner by that flag. It wires nothing.
SELF_FILES = ("hooks/judge_replay.py", "hooks/test_judge_replay.py", "lint/test_ci_scope.py")
NAMED = re.compile(rb"judge[_-]replay")
RUN = None  # this run's folder, made in main()
WINDOW = 27  # the adapter's copy of the wording prompt, "Judge this SendMessage call", is this long
PIN_BEFORE = "steps:\n  - run: npm install --global @anthropic-ai/claude-code@2.1.319\n  - run: echo lint\n"
PIN_MOVED = "steps:\n  - run: npm install --global @anthropic-ai/claude-code@2.1.320\n  - run: echo lint\n"
OTHER_STEP = "steps:\n  - run: npm install --global @anthropic-ai/claude-code@2.1.319\n  - run: echo lint again\n"
RESWORDED = 'Weigh this peer message against the rule: %s\nAnswer {"ok": true} or {"ok": false, "reason": "..."}. Reply JSON only.'


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


@contextlib.contextmanager
def faked_calls(fake):
    """decision_watch.invoke_model replaced by `fake`, a function of each call's arguments. The real one is restored after."""
    real = decision_watch.invoke_model
    decision_watch.invoke_model = fake
    try:
        yield
    finally:
        decision_watch.invoke_model = real


@contextlib.contextmanager
def adapter_swapped(name, adapter):
    """JUDGES[name] with its adapter replaced, so replay(name) drives `adapter` over the corpus's cases. Restored after."""
    row = judge_replay.JUDGES[name]
    judge_replay.JUDGES[name] = dict(row, adapter=adapter)
    try:
        yield
    finally:
        judge_replay.JUDGES[name] = row


def git_in(repo, *args):
    subprocess.run(["git", "-C", repo, "-c", "user.name=test", "-c", "user.email=test@example.invalid", *args],
                   check=True, capture_output=True)


def pin_repo(name, before, after):
    """A repo under RUN whose .github/workflows/checks.yml is `before` in one commit and `after` in the next."""
    repo = os.path.join(RUN, name)
    path = os.path.join(repo, ".github", "workflows", "checks.yml")
    os.makedirs(os.path.dirname(path))
    git_in(repo, "init", "-q")
    for text, message in ((before, "before"), (after, "after")):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        git_in(repo, "add", "-A")
        git_in(repo, "commit", "-q", "-m", message)
    return repo


def changed_run(repo, base):
    """`--changed base` run in `repo` with replay stubbed to record the judges it asks for. -> (asked, output, model calls)."""
    asked = []

    def record(name, runs=1):
        asked.append(name)
        return []

    saved = judge_replay.REPO, judge_replay.replay
    judge_replay.REPO, judge_replay.replay = repo, record
    try:
        with faked_model(NO_AUTH) as calls, contextlib.redirect_stdout(io.StringIO()) as out:
            run_main(["--changed", base])
    finally:
        judge_replay.REPO, judge_replay.replay = saved
    return asked, out.getvalue(), calls


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


def case_feedback_bad_entry_reads_unknown():
    label = "feedback_guard: a bad entry"
    judges = judges_or_fail(label)
    if judges is None:
        return
    cases, problem = load_corpus("feedback_guard")
    if cases is None:
        check(label, False, problem)
        return
    # The model names an id and a ref that are no candidate: judge() returns a `why`, and every row must read UNKNOWN.
    bad = {"repeats": [{"id": "fb-9-1", "ref": "inbox:no-such-home@2026-01-01 00:00"}]}
    with faked_model((bad, None)) as calls:
        rows = judge_replay.replay("feedback_guard")
    check("%s: one model call per case" % label, len(calls) == len(cases),
          "%d calls for %d cases" % (len(calls), len(cases)))
    wrong = [r for r in rows if r["verdict"] != "UNKNOWN"]
    check("%s: every row reads UNKNOWN" % label, not wrong,
          "row %s read %s" % (wrong[0]["id"], wrong[0]["verdict"]) if wrong else "")


def case_feedback_clean_answer_reads_no_unknown():
    label = "feedback_guard: a clean answer (control)"
    judges = judges_or_fail(label)
    if judges is None:
        return
    cases, problem = load_corpus("feedback_guard")
    if cases is None:
        check(label, False, problem)
        return
    clean = ((judges.get("feedback_guard") or {}).get("answers") or {}).get("allow")
    if clean is None:
        check(label, False, "JUDGES['feedback_guard'] has no clean allow answer")
        return
    with faked_model((clean, None)) as calls:
        rows = judge_replay.replay("feedback_guard")
    check("%s: one model call per case" % label, len(calls) == len(cases),
          "%d calls for %d cases" % (len(calls), len(cases)))
    unknown = [r["id"] for r in rows if r["verdict"] == "UNKNOWN"]
    check("%s: no row reads UNKNOWN" % label, not unknown, "UNKNOWN rows: %s" % ", ".join(unknown))


def case_sendmessage_errored_call_reads_unknown():
    label = "sendmessage_state: an errored call"
    if need_runner(label) is None:
        return
    # A stand-in entry that makes two seam calls in order, the first errors and the second answers. The row must read
    # UNKNOWN: any errored call is unknown, whatever the last call said. Deterministic: no threads, no prompt text.
    script = []

    def fake(*args, **kwargs):
        script.append(args)
        return (None, "no auth") if len(script) == 1 else ({"ok": True}, None)

    def two_calls(case_input, calls):
        del script[:]
        decision_watch.invoke_model("first call")
        decision_watch.invoke_model("second call")
        return "allow"

    with faked_calls(fake), adapter_swapped("sendmessage_state", two_calls):
        rows = judge_replay.replay("sendmessage_state")
    wrong = [r for r in rows if r["verdict"] != "UNKNOWN"]
    check("%s: every row reads UNKNOWN" % label, not wrong,
          "row %s read %s" % (wrong[0]["id"], wrong[0]["verdict"]) if wrong else "")


def case_sendmessage_one_seam_call_per_case_whatever_the_wording():
    label = "sendmessage_state: one seam call per case"
    if need_runner(label) is None:
        return
    import sendmessage_state
    cases, problem = load_corpus("sendmessage_state")
    if cases is None:
        check(label, False, problem)
        return
    # The wording judge's text is changed, and the adapter must still read its one call without knowing the text.
    saved = sendmessage_state.WORDING_PROMPT
    sendmessage_state.WORDING_PROMPT = RESWORDED
    try:
        with faked_model(NO_AUTH) as calls:
            judge_replay.replay("sendmessage_state")
    finally:
        sendmessage_state.WORDING_PROMPT = saved
    check(label, len(calls) == len(cases),
          "%d seam calls for %d cases: the adapter depends on the wording prompt's text" % (len(calls), len(cases)))


def case_wording_prompt_text_is_not_copied():
    label = "sendmessage_state: wording prompt not copied"
    if need_runner(label) is None:
        return
    import sendmessage_state
    with open(os.path.join(HERE, "judge_replay.py"), encoding="utf-8") as f:
        source = f.read()
    prompts = sorted(name for name in dir(sendmessage_state)
                     if name.endswith("PROMPT") and isinstance(getattr(sendmessage_state, name), str))
    check("%s: the module has a PROMPT string" % label, bool(prompts), "no *PROMPT str constant")
    for name in prompts:
        window = getattr(sendmessage_state, name)[:WINDOW]
        check("%s: judge_replay.py holds no %d characters of %s" % (label, WINDOW, name), window not in source,
              "copied: %r" % window)


def case_pin_change_names_every_judge():
    label = "--changed on the claude-code pin"
    if need_runner(label) is None:
        return
    every = sorted(judge_replay.JUDGES)
    asked, out, calls = changed_run(pin_repo("pin-moved", PIN_BEFORE, PIN_MOVED), "HEAD~1")
    check("%s: the diff reads" % label, "UNKNOWN: git diff" not in out, out[-200:])
    check("%s: asks every judge" % label, sorted(asked) == every, "asked %r, want every judge" % (asked,))
    check("%s: makes no model call" % label, not calls, "%d model calls" % len(calls))
    # Control: a checks.yml change that leaves the pin line alone asks no judge.
    asked, out, calls = changed_run(pin_repo("other-step", PIN_BEFORE, OTHER_STEP), "HEAD~1")
    check("--changed on a checks.yml change that leaves the pin (control): the diff reads",
          "UNKNOWN: git diff" not in out, out[-200:])
    check("--changed on a checks.yml change that leaves the pin (control): asks no judge", not asked,
          "asked %r" % (asked,))


def case_probe_names_the_secret_and_the_item():
    label = "--probe"
    if need_runner(label) is None:
        return
    with ci_env(None), faked_model(NO_AUTH), contextlib.redirect_stdout(io.StringIO()) as out:
        code = run_main(["--probe"])
    text = out.getvalue()
    check("--probe with no sign-in exits 1 (control)", code == 1, "exit %r" % (code,))
    check("--probe with no sign-in names the secret (control)", "CLAUDE_CODE_OAUTH_TOKEN" in text, text[-200:])
    check("--probe with no sign-in names waiting page item 283 (control)", "283" in text, text[-200:])
    with ci_env(None), faked_model(({"ok": True}, None)), contextlib.redirect_stdout(io.StringIO()):
        code = run_main(["--probe"])
    check("--probe with an answer exits 0 (control)", code == 0, "exit %r" % (code,))


CASES = (case_seam_control, case_corpora, case_scopes, case_touched, case_no_auth_rows,
         case_cli_exit_follows_ci, case_cli_changed_head, case_runner_named_nowhere_else,
         case_feedback_bad_entry_reads_unknown, case_feedback_clean_answer_reads_no_unknown,
         case_sendmessage_errored_call_reads_unknown, case_sendmessage_one_seam_call_per_case_whatever_the_wording,
         case_wording_prompt_text_is_not_copied, case_pin_change_names_every_judge,
         case_probe_names_the_secret_and_the_item)


def main():
    global RUN
    RUN = _test_temp.run_folder()
    try:
        for case in CASES:
            try:
                case()
            except Exception as error:
                check(case.__name__, False, "raised %s: %s" % (type(error).__name__, error))
    finally:
        shutil.rmtree(RUN, ignore_errors=True)
    print("FAIL: %d failed" % len(FAILED) if FAILED else "all checks passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
