#!/usr/bin/env python3
"""Cases for hooks/judge_replay.py, the replay runner of the model judges' known allow and deny corpora.
Standard library only, and no test runner.

    python3 hooks/test_judge_replay.py

The runner, as the builder writes it. This file is its interface.

- JUDGES: name -> {"corpus": ".github/judge-replay/corpus/<name>.json", "scope": [repo-relative paths], "answers":
  {"allow": ..., "deny": ...}}, for each name in NAMES. Each scope holds hooks/decision_watch.py, the one model seam, and
  the judge's own module file. Each answer is one model answer, in the judge's own shape, that reads every case as allow
  or as deny.
- A corpus is a JSON list of cases {"id": str, "expect": "allow" or "deny", "source": str, "input": object,
  "agreement": str such as "3/3"}. Ids are unique in a file, and a corpus holds an allow case and a deny case. Each case
  carries its recorded verdict: its expect, and its agreement from a recorded run.
- The page judge has no corpus file while step judge-replay-page-cases is pending. Its row runs zero cases and reads
  "no cases yet" with the pending step. Only a judge that PENDING_STEPS names may run zero cases. Any other judge whose
  corpus file is missing, holds [], or does not parse as a list of cases exits 1, and a detail line names the judge and
  its file.
- touched(paths): the sorted names whose scope holds a path, whose corpus is a path, or, for hooks/judge_replay.py, all.
- replay(name, runs=1): one row per case, {"id", "expect", "got", "verdict"}. got is allow, deny or unknown. Each model
  call goes through decision_watch.invoke_model, looked up at call time, so this file replaces it. Every judge makes one
  call per case, feedback_guard included, even where its prompt could batch.
- main(argv) returns the exit code. --changed BASE, --judge NAME and --all. An UNKNOWN exits 1 when env CI is set, else 0.
- --changed BASE names every judge when the committed diff moves the claude-code pin: a change to
  .github/judge-replay/package.json or its lock file, or a pin line added or removed in .github/workflows/checks.yml.
  The pin cases set judge_replay.REPO to a two-commit temp repo, since --changed reads git there.
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
import tempfile

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
# The page judge has no corpus file until step judge-replay-page-cases adds its cases after a CI dispatch. Its row runs
# zero cases and says so, while the other judges keep their corpora. These are the pinned numbers while that step is pending.
PENDING_JUDGE = "call_judge.page"
PENDING_TEXT = "pending step judge-replay-page-cases"
NO_CASES = "no cases yet"
JUDGE_COUNT = 11  # every JUDGES row, the pending judge's included
CORPUS_JUDGES = 10  # the judges with a corpus file while the page judge is pending
CORPUS_CASES = 53  # their cases: 7 + 4 + 6 + 7 + 4 + 4 + 5 + 6 + 4 + 6
FEEDS_CALL_JUDGE = ("call_judge.opus_ask", "call_judge.opus_scope", "call_judge.page", "call_judge.question",
                    "call_judge.spawn", "report_guard.past_ruling")  # the judges whose scope holds hooks/call_judge.py
PROBE_JUDGE = "no_corpus_probe"  # a judge row added for one case, whose corpus path has no file
ROW = re.compile(r"^  (PASS|MISS|UNKNOWN)\s")
HEADER = re.compile(r"^(\S+) \(\d+ cases?, ")
TOUCH = (
    ([], []),
    (["README.md"], []),
    (["hooks/decision_watch.py"], "all"),
    (["hooks/judge_replay.py"], "all"),
    (["hooks/prose_judge.py"], ["prose_judge"]),
    ([".github/judge-replay/corpus/reply_judge.json"], ["reply_judge"]),
    (["hooks/shared_names.py"], "all"),
    (["hooks/guard.py"], "all"),
    (["hooks/_nowindow.py"], "all"),  # every judge's model call starts in it (decision_watch.run calls _nowindow.run)
    (["hooks/call_judge.py"], list(FEEDS_CALL_JUDGE)),  # the page judge's module, with the judges it feeds
    (["hooks/guard_pointer.py"], "all"),  # a guard family module: guard.py loads it, so every judge's scope holds it
    (["hooks/git_reads.py"], "all"),  # the other guard family file that guard.py loads
    ([".github/judge-replay/package.json"], "all"),  # the claude CLI pin: a change to it replays every judge
    ([".github/judge-replay/package-lock.json"], "all"),
)
NO_AUTH = (None, "no auth")
# lint/test_ci_scope.py pins the CI scope's judge_replay flag, so it names the runner by that flag. It wires nothing.
SELF_FILES = ("hooks/judge_replay.py", "hooks/test_judge_replay.py", "lint/test_ci_scope.py")
NAMED = re.compile(rb"judge[_-]replay")
CORPUS_DIR = ".github/judge-replay/corpus"  # out of hooks/: the installer lands hooks/ but not its subfolders
RUN = None  # this run's folder, made in main()
WINDOW = 27  # the adapter's copy of the wording prompt, "Judge this SendMessage call", is this long
PIN_BEFORE = "steps:\n  - run: npm install --global @anthropic-ai/claude-code@2.1.319\n  - run: echo lint\n"
PIN_MOVED = "steps:\n  - run: npm install --global @anthropic-ai/claude-code@2.1.320\n  - run: echo lint\n"
OTHER_STEP = "steps:\n  - run: npm install --global @anthropic-ai/claude-code@2.1.319\n  - run: echo lint again\n"
CHECKS_REL = ".github/workflows/checks.yml"
PKG_REL = ".github/judge-replay/package.json"  # the one home of the claude CLI pin, installed by npm ci
PKG_BEFORE = '{\n  "dependencies": {\n    "@anthropic-ai/claude-code": "2.1.319"\n  }\n}\n'
PKG_MOVED = PKG_BEFORE.replace("2.1.319", "2.1.320")
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


def pin_repo(name, before, after, rel=CHECKS_REL, steady=()):
    """A repo under RUN whose file `rel` is `before` in one commit and `after` in the next. Each (path, text) in `steady`
    is committed with the first commit and left as it is."""
    repo = os.path.join(RUN, name)
    os.makedirs(repo)
    git_in(repo, "init", "-q")
    for path, text in steady:
        write_text(repo, path, text)
    for text, message in ((before, "before"), (after, "after")):
        write_text(repo, rel, text)
        git_in(repo, "add", "-A")
        git_in(repo, "commit", "-q", "-m", message)
    return repo


def write_text(repo, rel, text):
    path = os.path.join(repo, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


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
    """(cases, "") for CORPUS_DIR/<name>.json, or (None, reason) when it is missing or does not parse."""
    rel = "%s/%s.json" % (CORPUS_DIR, name)
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
    """Control: the seam the fake replaces is real, and the fake is undone when its block ends."""
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
        rel = corpus_rel(name)
        check("corpus path is %s: %s" % (rel, name), entry.get("corpus") == rel,
              "corpus is %r" % (entry.get("corpus"),))
        if name == PENDING_JUDGE:
            check("corpus file absent while pending: %s" % name, not corpus_present(name),
                  "%s exists; its cases are the pending step's to add" % rel)
            continue
        cases, problem = load_corpus(name)
        check("corpus reads: %s" % name, cases is not None, problem)
        if cases is None:
            continue
        shape = shape_problem(cases)
        check("corpus cases well formed: %s" % name, not shape, shape)
        recorded = recorded_problem(cases)
        check("corpus cases carry a recorded verdict: %s" % name, not recorded, recorded)
        ids = [repr(case.get("id")) for case in cases if isinstance(case, dict)]
        repeated = sorted({i for i in ids if ids.count(i) > 1})
        check("corpus ids unique: %s" % name, not repeated, "repeated ids: %s" % ", ".join(repeated))
        expects = [case.get("expect") for case in cases if isinstance(case, dict)]
        check("corpus has an allow case: %s" % name, "allow" in expects, "no case expects allow")
        check("corpus has a deny case: %s" % name, "deny" in expects, "no case expects deny")


def tracked_under(repo, prefix):
    """The tracked paths of `repo` that start with `prefix`, or None when git cannot list them."""
    try:
        listed = subprocess.run(["git", "-C", repo, "ls-files", "-z"], capture_output=True)
    except OSError:
        return None
    if listed.returncode != 0:
        return None
    return [p for p in listed.stdout.decode("utf-8", "replace").split("\0") if p.startswith(prefix)]


def case_corpus_not_under_hooks():
    """The installer lands hooks/ but not its subfolders, so no tracked file may sit under hooks/judge_corpus/.
    The scope control: git lists the runner at this commit, so an empty listing below is a real empty listing."""
    label = "corpus: no tracked file under hooks/judge_corpus/"
    runner = tracked_under(REPO, "hooks/judge_replay.py")
    if runner is None or "hooks/judge_replay.py" not in runner:
        check("%s (scope control: git lists hooks/judge_replay.py)" % label, False,
              "git ls-files gave %r" % (runner,))
        return
    check("%s (scope control: git lists hooks/judge_replay.py)" % label, True)
    stray = tracked_under(REPO, "hooks/judge_corpus/")
    if stray is None:
        check(label, False, "git ls-files failed in %s" % REPO)
        return
    check(label, not stray, "%d tracked under hooks/judge_corpus/, first %s" % (len(stray), stray[0] if stray else ""))


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
        # The pending judge's corpus file is the step's to add, so its path may not exist yet. The path stays in its scope,
        # so the file, once added, touches the judge.
        absent_ok = corpus_rel(name) if name == PENDING_JUDGE else None
        gone = [p for p in scope if p != absent_ok
                and (os.path.isabs(p) or ".." in p.split("/") or not os.path.exists(os.path.join(REPO, p)))]
        check("scope paths exist: %s" % name, not gone, "no such path: %s" % ", ".join(gone))
        if name == PENDING_JUDGE:
            check("scope holds the pending corpus path: %s" % name, absent_ok in scope,
                  "scope lacks %s" % absent_ok)


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
        if name == PENDING_JUDGE:
            continue  # its zero-case row is pinned by case_pending_judge_reads_no_cases
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


def case_pin_change_checks_yml_names_every_judge():
    """The checks.yml form of the pin, which pin_changed still reads."""
    label = "--changed on the claude-code pin line in checks.yml"
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


def case_pin_change_package_names_every_judge():
    label = "--changed on the claude-code pin in .github/judge-replay/package.json"
    if need_runner(label) is None:
        return
    every = sorted(judge_replay.JUDGES)
    asked, out, calls = changed_run(pin_repo("pin-cli-moved", PKG_BEFORE, PKG_MOVED, PKG_REL), "HEAD~1")
    check("%s: the diff reads" % label, "UNKNOWN: git diff" not in out, out[-200:])
    check("%s: asks every judge" % label, sorted(asked) == every, "asked %r, want every judge" % (asked,))
    check("%s: makes no model call" % label, not calls, "%d model calls" % len(calls))
    # Control: the pin file is present and unmoved in both commits, and only a README changes. Asks no judge.
    steady = ((PKG_REL, PKG_BEFORE),)
    asked, out, calls = changed_run(pin_repo("cli-unrelated", "one\n", "two\n", "README.md", steady), "HEAD~1")
    check("%s (control): the diff reads" % label, "UNKNOWN: git diff" not in out, out[-200:])
    check("%s (control): asks no judge" % label, not asked, "asked %r" % (asked,))


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


def answer_problem(rows, cases, key):
    """The first way the rows of an answer `key` miss the expected verdicts, or "" when they hold. The row count and
    both verdicts come first, so an empty or one-sided run cannot pass the row check."""
    if len(rows) != len(cases):
        return "%d rows for %d cases" % (len(rows), len(cases))
    verdicts = sorted({r["verdict"] for r in rows})
    if verdicts != ["MISS", "PASS"]:
        return "rows read %s, want PASS and MISS" % ", ".join(verdicts)
    for r in rows:
        want = "PASS" if r["expect"] == key else "MISS"
        if r["verdict"] != want:
            return "row %s read %s, want %s" % (r["id"], r["verdict"], want)
    return ""


def case_each_judge_answer_reads_as_its_own_verdict():
    """Each judge's own answers, given for every call. The allow answer reads each case as allow, so its expect-allow
    rows PASS and its expect-deny rows MISS, and the deny answer is the mirror. A MISS exits 1. sendmessage_state makes
    two calls on a busy receiver, but its adapter answers the wording call itself with the same {"ok": bool} shape, so
    one answer per run serves both calls."""
    judges = judges_or_fail("answer shapes: JUDGES is readable")
    if judges is None:
        return
    for name in sorted(judges):
        if name == PENDING_JUDGE:
            continue  # its zero-case rows are pinned by case_pending_judge_reads_no_cases
        row = judges[name] if isinstance(judges[name], dict) else {}
        answers = row.get("answers") if isinstance(row.get("answers"), dict) else {}
        cases, problem = load_corpus(name)
        for key in ("allow", "deny"):
            rows_label = "%s: the %s answer reads each row as its verdict" % (name, key)
            exit_label = "%s: --judge exits 1 under the %s answer" % (name, key)
            if key not in answers:
                check(rows_label, False, "JUDGES[%r] has no %r answer" % (name, key))
                continue
            if cases is None:
                check(rows_label, False, problem)
                continue
            # A copy, so the judge that reads the answer cannot change the table.
            model_answer = json.loads(json.dumps(answers[key]))
            try:
                with faked_model((model_answer, None)):
                    rows = judge_replay.replay(name)
            except Exception as error:
                check(rows_label, False, "replay raised %s: %s" % (type(error).__name__, error))
                continue
            wrong = answer_problem(rows, cases, key)
            check(rows_label, not wrong, wrong)
            try:
                with faked_model((model_answer, None)), contextlib.redirect_stdout(io.StringIO()):
                    code = run_main(["--judge", name])
            except Exception as error:
                check(exit_label, False, "raised %s: %s" % (type(error).__name__, error))
                continue
            check(exit_label, code == 1, "exit %r" % (code,))


MAJORITY_FIXTURES = (
    ("one run, allow", ["allow"], 1, "allow"),
    ("one run, model error", ["unknown"], 1, "unknown"),
    ("2 runs, one allow and one deny", ["allow", "deny"], 2, "unknown"),
    ("3 of 3 allow", ["allow", "allow", "allow"], 3, "allow"),
    ("2 of 3 allow", ["allow", "deny", "allow"], 3, "allow"),
    ("2 of 3 deny", ["deny", "allow", "deny"], 3, "deny"),
    ("2 allow and a model error", ["allow", "unknown", "allow"], 3, "allow"),
    ("1 allow, 1 deny and a model error", ["allow", "deny", "unknown"], 3, "unknown"),
    ("1 allow and 2 model errors", ["allow", "unknown", "unknown"], 3, "unknown"),
    ("3 model errors", ["unknown", "unknown", "unknown"], 3, "unknown"),
)


def case_majority_takes_the_verdict_of_the_runs():
    """A case's verdict is the answer that a strict majority of its runs give: 3 of 3 and 2 of 3 agree, and a split with no
    majority is unknown. A model error is no answer for its run, so it is never counted as agreeing with an answer or with
    another error. The agreement string counts answered runs only."""
    label = "majority of runs"
    if need_runner(label) is None:
        return
    settle = getattr(judge_replay, "settle", None)
    if not callable(settle):
        check(label, False, "hooks/judge_replay.py has no settle(answers, runs)")
        return
    for name, answers, runs, want in MAJORITY_FIXTURES:
        got, agreement = settle(list(answers), runs)
        check("%s: %s" % (label, name), got == want, "got %r, want %r" % (got, want))
        # Named failure: the agreement string counts model-error runs as agreeing with each other.
        answered = max(answers.count("allow"), answers.count("deny"))
        counted = int(agreement.split("/")[0])
        check("%s: agreement counts answered runs only, %s" % (label, name), counted <= answered,
              "agreement %r reads %d runs agreeing with %d answered" % (agreement, counted, answered))


def scripted_judge(outcomes):
    """An adapter whose runs read `outcomes` in order. Each run makes one model call, which fails on "error"."""
    queue = list(outcomes)

    def adapter(case_input, calls):
        outcome = queue.pop(0)
        decision_watch.invoke_model("fixture prompt", fail=outcome == "error")
        return "deny" if outcome == "deny" else "allow"
    return adapter


def failing_on_request(*args, fail=False, **kwargs):
    """decision_watch.invoke_model's fake for scripted_judge: the no-auth pair on a failed call, else an answer."""
    return NO_AUTH if fail else ({"ok": True}, None)


def case_replay_model_error_is_no_answer_for_its_run():
    """replay() of one case over three runs: a run whose model call fails answers nothing. Two allows and an error read as
    allow. One allow and two errors read as unknown."""
    label = "replay: a model error in one run"
    if need_runner(label) is None:
        return
    case = {"id": "fixture-case", "expect": "allow", "source": "fixture", "input": {}}
    saved_load = judge_replay.load_corpus
    judge_replay.load_corpus = lambda name: [case]
    try:
        for outcomes, want_got, want_verdict in (
            (["allow", "allow", "error"], "allow", "PASS"),
            (["allow", "error", "error"], "unknown", "UNKNOWN"),
        ):
            with adapter_swapped("prose_judge", scripted_judge(outcomes)), faked_calls(failing_on_request):
                rows = judge_replay.replay("prose_judge", runs=3)
            check("%s %s: one row" % (label, outcomes), len(rows) == 1, "%d rows" % len(rows))
            if rows:
                row = rows[0]
                check("%s %s: got %s" % (label, outcomes, want_got), row["got"] == want_got,
                      "got %r, want %r" % (row["got"], want_got))
                check("%s %s: verdict %s" % (label, outcomes, want_verdict), row["verdict"] == want_verdict,
                      "verdict %r, want %r" % (row["verdict"], want_verdict))
    finally:
        judge_replay.load_corpus = saved_load


def corpus_rel(name):
    return "%s/%s.json" % (CORPUS_DIR, name)


def corpus_present(name):
    return os.path.isfile(os.path.join(REPO, *corpus_rel(name).split("/")))


def recorded_problem(cases):
    """The first case with no recorded verdict, or "" when every case has one: an expect of allow or deny, and an agreement
    such as "3/3" from its recorded run."""
    if not isinstance(cases, list):
        return "not a list"
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            return "case %d is not an object" % index
        agreement = case.get("agreement")
        if case.get("expect") in ("allow", "deny") and isinstance(agreement, str) and re.fullmatch(r"\d+/\d+", agreement):
            continue
        return "case %r has no recorded verdict" % (case.get("id"),)
    return ""


def runner_output(argv, answer=NO_AUTH):
    """(exit code, output, model calls, error) of run_main(argv), with CI unset and the model faked as `answer`. error is the
    text of an exception the runner raised, or None."""
    code, error = None, None
    with ci_env(None), faked_model(answer) as calls, contextlib.redirect_stdout(io.StringIO()) as out:
        try:
            code = run_main(argv)
        except Exception as exc:  # a raise is a failed check, named by the caller
            error = "raised %s: %s" % (type(exc).__name__, " ".join(str(exc).split()))
    return code, out.getvalue(), calls, error


def judge_block(text, name):
    """The output lines of judge `name`: its header line, then the indented lines under it, up to the next header."""
    block, inside = [], False
    for line in text.splitlines():
        if line.startswith(name + " ("):
            block, inside = [line], True
        elif inside and line.startswith(" "):
            block.append(line)
        else:
            inside = False
    return block


def judges_headed(text):
    """The sorted names of the judges whose header lines the runner printed."""
    return sorted(m.group(1) for m in map(HEADER.match, text.splitlines()) if m)


def check_pending_block(label, text):
    """The page judge's row in runner output `text`: it runs zero cases, has no case rows, reads NO_CASES, and names the
    pending step."""
    block = judge_block(text, PENDING_JUDGE)
    joined = "\n".join(block)
    check("%s: the page row runs zero cases" % label, bool(block) and block[0].startswith(PENDING_JUDGE + " (0 cases,"),
          joined or text[-200:])
    rows = [line for line in block if ROW.match(line)]
    check("%s: the page row has no case rows" % label, not rows, "%d case rows" % len(rows))
    check("%s: the page row reads %r" % (label, NO_CASES), NO_CASES in joined, joined or text[-200:])
    check("%s: the page row names %r" % (label, PENDING_TEXT), PENDING_TEXT in joined, joined or text[-200:])


@contextlib.contextmanager
def judge_row_added(name, row):
    """JUDGES[name] = row for one case, removed after."""
    judge_replay.JUDGES[name] = row
    try:
        yield
    finally:
        judge_replay.JUDGES.pop(name, None)


def case_pending_judge_reads_no_cases():
    """The page judge's corpus is the pending step's to add. Under either answer its row runs zero cases, names the step,
    makes no model call, and exits 0: zero cases is no MISS and no UNKNOWN."""
    label = "--judge %s" % PENDING_JUDGE
    judges = judges_or_fail(label)
    if judges is None:
        return
    answers = (judges.get(PENDING_JUDGE) or {}).get("answers") or {}
    for key in ("allow", "deny"):
        tag = "under the %s answer" % key
        if key not in answers:
            check("%s: JUDGES holds the %s answer" % (label, key), False, "no %r answer" % key)
            continue
        model_answer = json.loads(json.dumps(answers[key]))  # a copy, so the judge cannot change the table
        code, text, calls, error = runner_output(["--judge", PENDING_JUDGE], answer=(model_answer, None))
        check("%s: does not raise %s" % (label, tag), error is None, error or "")
        check_pending_block("%s %s" % (label, tag), text)
        check("%s: makes no model call %s" % (label, tag), not calls, "%d model calls" % len(calls))
        check("%s: exits 0 %s" % (label, tag), code == 0, "exit %r" % (code,))


def case_corpus_counts_while_page_pending():
    """Ten judges hold a corpus file, with 53 cases between them. The runner's --all total reads 53 cases, lists all eleven
    judges, and lists the page judge as pending."""
    label = "corpus counts while %s is pending" % PENDING_JUDGE
    if need_runner(label) is None:
        return
    have = [name for name in NAMES if corpus_present(name)]
    check("%s: %d judges have a corpus file" % (label, CORPUS_JUDGES), len(have) == CORPUS_JUDGES,
          "%d have one: %s" % (len(have), ", ".join(have)))
    total = 0
    for name in have:
        cases, _ = load_corpus(name)
        total += len(cases or [])
    check("%s: the corpora hold %d cases" % (label, CORPUS_CASES), total == CORPUS_CASES, "%d cases" % total)
    _, text, _, error = runner_output(["--all"])
    check("--all: the runner does not raise", error is None, error or "")
    found = re.search(r"^\d+ cases:.*$", text, re.MULTILINE)
    check("--all totals %d cases" % CORPUS_CASES, bool(found) and found.group(0).startswith("%d cases:" % CORPUS_CASES),
          found.group(0) if found else text[-200:])
    listed = judges_headed(text)
    check("--all lists %d judges" % JUDGE_COUNT, len(listed) == JUDGE_COUNT, "%d judges listed" % len(listed))
    check_pending_block("--all", text)


def case_judge_without_corpus_fails_the_run():
    """Rewritten under the coordinator's ruling (08:35 CST Nov 12): a judge whose corpus file is missing, and that the pending
    table does not name, fails the run. The runner does not raise, exits 1, names the judge and its file on one detail
    line, and makes no model call. The scope check still names it."""
    label = "a judge with no corpus file"
    judges = judges_or_fail(label)
    if judges is None:
        return
    row = {"corpus": corpus_rel(PROBE_JUDGE), "scope": [SEAM], "adapter": judges["prose_judge"]["adapter"], "answers": {}}
    check("%s: the probe's corpus file is absent (fixture)" % label, not corpus_present(PROBE_JUDGE),
          "%s exists" % row["corpus"])
    with judge_row_added(PROBE_JUDGE, row):
        code, text, calls, error = runner_output(["--judge", PROBE_JUDGE])
        scoped = judge_replay.touched([SEAM])
    check("%s: the scope check names it" % label, PROBE_JUDGE in scoped, "touched gave %s" % ", ".join(scoped))
    check_judges_without_corpus(label, {PROBE_JUDGE: (code, text, calls, error)})


CONTROL_CASE = {"id": "control-allow", "expect": "allow", "source": "fixture", "input": {}}
OK_ANSWER = ({"ok": True}, None)  # the answer of a model call that succeeded, for the cases whose adapter makes one
FIXTURE_PENDING = "pending step fixture-table-row"
CAUSES = ("raises", "exit is not 1", "no detail line names the judge and its corpus file", "prints pending text",
          "makes a model call")


def page_case(expect):
    return {"id": "page-fixture-%s" % expect, "expect": expect, "source": "fixture", "input": {}}


@contextlib.contextmanager
def runner_repo(corpora):
    """judge_replay.REPO set to a folder under RUN whose corpus files hold `corpora`, {judge name: file text}. A judge not in
    `corpora` has no file there. The runner reads its corpora from REPO, so the real loader reads these files."""
    root = tempfile.mkdtemp(dir=RUN)
    for name, text in corpora.items():
        write_text(root, corpus_rel(name), text)
    saved = judge_replay.REPO
    judge_replay.REPO = root
    try:
        yield root
    finally:
        judge_replay.REPO = saved


def check_judges_without_corpus(label, runs):
    """`runs` maps each judge with no usable corpus file to its (code, text, calls, error). One check per cause in CAUSES,
    each listing the judges that miss it, so each failure names one cause."""
    missed = {cause: [] for cause in CAUSES}
    for name, (code, text, calls, error) in runs.items():
        block = judge_block(text, name)
        if error is not None:
            missed["raises"].append(name)
        if code != 1:
            missed["exit is not 1"].append(name)
        if not any(name in line and corpus_rel(name) in line for line in block[1:]):
            missed["no detail line names the judge and its corpus file"].append(name)
        if PENDING_TEXT in "\n".join(block):
            missed["prints pending text"].append(name)
        if calls:
            missed["makes a model call"].append(name)
    for cause in CAUSES:
        check("%s: %s" % (label, cause), not missed[cause], ", ".join(missed[cause]))


def case_judge_other_than_page_without_corpus_file_fails_the_run():
    """A judge other than the page judge with no corpus file exits 1, and a detail line names the judge and its file. The
    control runs first: a one-case file in a temp folder is read and run there, so the zero-case runs after it are about
    absence and not about a swap that did not reach the runner."""
    label = "a judge other than the page judge, no corpus file"
    if need_runner(label) is None:
        return
    with runner_repo({"prose_judge": json.dumps([CONTROL_CASE])}), \
            adapter_swapped("prose_judge", scripted_judge(["allow"])):
        code, text, _, _ = runner_output(["--judge", "prose_judge"], answer=OK_ANSWER)
    head = judge_block(text, "prose_judge")[:1]
    check("%s: control: the runner reads the one case in its file" % label,
          bool(head) and head[0].startswith("prose_judge (1 cases,"), head[0] if head else text[-200:])
    check("%s: control: the run exits 0" % label, code == 0, "exit %r" % (code,))
    others = [name for name in NAMES if name != PENDING_JUDGE]
    with runner_repo({}):
        runs = {name: runner_output(["--judge", name]) for name in others}
    check_judges_without_corpus(label, runs)


def case_judge_other_than_page_with_empty_corpus_fails_the_run():
    """A judge other than the page judge whose corpus file holds [] exits 1, and a detail line names the judge and its file.
    The same rule as a missing file: an empty corpus is no cases, and only the pending table exempts a judge from that."""
    label = "a judge other than the page judge, corpus []"
    if need_runner(label) is None:
        return
    others = [name for name in NAMES if name != PENDING_JUDGE]
    with runner_repo({name: "[]\n" for name in others}):
        runs = {name: runner_output(["--judge", name]) for name in others}
    check_judges_without_corpus(label, runs)


def case_pending_judge_missing_or_empty_corpus_reads_no_cases():
    """The page judge may have no cases yet: with no file, or with a file that holds [], its row runs zero cases, reads
    NO_CASES and names the pending step, makes no model call, and exits 0."""
    label = "--judge %s" % PENDING_JUDGE
    if need_runner(label) is None:
        return
    for tag, corpora in (("no file", {}), ("file holds []", {PENDING_JUDGE: "[]\n"})):
        with runner_repo(corpora):
            code, text, calls, error = runner_output(["--judge", PENDING_JUDGE])
        check("%s, %s: does not raise" % (label, tag), error is None, error or "")
        check_pending_block("%s, %s" % (label, tag), text)
        check("%s, %s: makes no model call" % (label, tag), not calls, "%d model calls" % len(calls))
        check("%s, %s: exits 0" % (label, tag), code == 0, "exit %r" % (code,))


def run_page_with_cases(cases, outcomes):
    """(code, text, error) of --judge on the page judge, its file holding `cases` and its adapter scripted to `outcomes`."""
    with runner_repo({PENDING_JUDGE: json.dumps(cases)}), adapter_swapped(PENDING_JUDGE, scripted_judge(outcomes)):
        code, text, _, error = runner_output(["--judge", PENDING_JUDGE], answer=OK_ANSWER)
    return code, text, error


def case_pending_judge_with_cases_runs_its_rows():
    """The pending exemption keys on the pending table, not on a missing file. With cases in its file the page judge's rows
    run as any judge's do: no NO_CASES line, no pending text, and the exit follows the rows. A MISS exits 1."""
    label = "--judge %s with cases in its file" % PENDING_JUDGE
    if need_runner(label) is None:
        return
    for cases, outcomes, want_rows, want_code in (
        ([page_case("allow"), page_case("deny")], ["allow", "allow"], ["MISS", "PASS"], 1),
        ([page_case("allow")], ["allow"], ["PASS"], 0),
    ):
        tag = "%d case%s" % (len(cases), "" if len(cases) == 1 else "s")
        code, text, error = run_page_with_cases(cases, outcomes)
        check("%s, %s: does not raise" % (label, tag), error is None, error or "")
        block = judge_block(text, PENDING_JUDGE)
        joined = "\n".join(block)
        check("%s, %s: the header counts its cases" % (label, tag),
              bool(block) and block[0].startswith("%s (%d cases," % (PENDING_JUDGE, len(cases))),
              joined or text[-200:])
        check("%s, %s: no %s line" % (label, tag, NO_CASES), NO_CASES not in joined, joined)
        check("%s, %s: no pending text" % (label, tag), PENDING_TEXT not in joined, joined)
        rows = sorted(ROW.match(line).group(1) for line in block if ROW.match(line))
        check("%s, %s: its rows read %s" % (label, tag, " and ".join(want_rows)), rows == sorted(want_rows),
              "rows read %s" % (", ".join(rows) or "none"))
        check("%s, %s: exits %d" % (label, tag, want_code), code == want_code, "exit %r" % (code,))


def case_pending_exemption_follows_the_pending_table():
    """The exemption keys on a judge named in PENDING_STEPS: with prose_judge named there and no corpus file, its row reads
    NO_CASES and the table's text, and it exits 0. A judge the table does not name fails (the cases above)."""
    label = "pending exemption follows PENDING_STEPS"
    if need_runner(label) is None:
        return
    table = getattr(judge_replay, "PENDING_STEPS", None)
    if not isinstance(table, dict):
        check(label, False, "hooks/judge_replay.py has no PENDING_STEPS dict")
        return
    judge_replay.PENDING_STEPS = dict(table, prose_judge=FIXTURE_PENDING)
    try:
        with runner_repo({}):
            code, text, _, error = runner_output(["--judge", "prose_judge"])
    finally:
        judge_replay.PENDING_STEPS = table
    check("%s: does not raise" % label, error is None, error or "")
    block = judge_block(text, "prose_judge")
    joined = "\n".join(block)
    check("%s: prose_judge's row reads %r" % (label, NO_CASES), NO_CASES in joined, joined or text[-200:])
    check("%s: prose_judge's row names the table's text" % label, FIXTURE_PENDING in joined, joined or text[-200:])
    check("%s: exits 0" % label, code == 0, "exit %r" % (code,))


def case_changed_page_judge_file_runs_no_page_cases():
    """A change to hooks/call_judge.py replays the judges whose scope holds it. The page judge is one of them, and its row
    runs zero cases and says so."""
    label = "--changed on hooks/call_judge.py"
    if need_runner(label) is None:
        return
    saved = judge_replay.changed_paths, judge_replay.pin_changed
    judge_replay.changed_paths = lambda base: ["hooks/call_judge.py"]
    judge_replay.pin_changed = lambda base: False  # the diff moves no pin, so the judges come from the scope lists
    try:
        _, text, _, error = runner_output(["--changed", "HEAD~1"])
    finally:
        judge_replay.changed_paths, judge_replay.pin_changed = saved
    check("%s: the runner does not raise" % label, error is None, error or "")
    fed = judges_headed(text)
    check("%s: replays the judges whose scope holds it" % label, fed == sorted(FEEDS_CALL_JUDGE),
          "replayed %s" % ", ".join(fed))
    check_pending_block(label, text)


FIRST_REF = "inbox:replay00@2026-11-01 10:00"  # the first older message of the feedback corpus's cases
SECOND_REF = "inbox:replay00@2026-11-01 10:01"  # the second older message, a candidate in every feedback case
HELPER_TOUCH = (
    ("hooks/route_match.py", ("reply_judge",)),  # reply_judge's prompt carries the route rows route_match reads
    ("lint/report_guard.py", ("reply_judge", "report_guard.past_ruling")),  # the route block reads its hand-off lines
    ("lint/_transcript.py", ("decision_watch",)),  # decision_watch's chat text starts after the record is_last_human picks
)
MALFORMED_CORPORA = (
    ("not JSON", "[{\"id\": \"x\", "),
    ("a JSON object, not a list", json.dumps({"cases": []})),
    ("a list of a non-object", json.dumps([1])),
    ("a case with no expect", json.dumps([{"id": "x"}])),
)


def case_feedback_hit_on_any_candidate_reads_refuse():
    """feedback_guard: a repeat is a hit on any candidate, not only on the older message the case names. The controls run
    first: a hit on the first older message reads deny on every row, and an empty list reads every allow row allow. Then
    a hit on the second older message must read deny on every row, since each feedback case has that candidate."""
    label = "feedback_guard: a hit on any candidate"
    if need_runner(label) is None:
        return
    cases, problem = load_corpus("feedback_guard")
    if cases is None:
        check(label, False, problem)
        return

    def rows_under(answer):
        with faked_model((answer, None)):
            return judge_replay.replay("feedback_guard")

    def hit(ref):
        return {"repeats": [{"id": "fb-9-1", "ref": ref}]}

    first = rows_under(hit(FIRST_REF))
    misses = [r["id"] for r in first if r["got"] != "deny"]
    check("%s: control: a hit on the first older message reads deny on every row" % label, not misses,
          "read allow: %s" % ", ".join(misses))
    empty = rows_under({"repeats": []})
    misses = [r["id"] for r in empty if r["expect"] == "allow" and r["got"] != "allow"]
    check("%s: control: an empty repeats list reads every allow row allow" % label, not misses,
          "read deny: %s" % ", ".join(misses))
    second = rows_under(hit(SECOND_REF))
    unknown = [r["id"] for r in second if r["got"] == "unknown"]
    check("%s: scope: the second older message's ref is a candidate, so no row reads unknown" % label, not unknown,
          "read unknown: %s" % ", ".join(unknown))
    misses = [r["id"] for r in second if r["got"] != "deny"]
    check("%s: a hit on the second older message reads deny on every row" % label, not misses,
          "read allow: %s" % ", ".join(misses))


def case_opus_scope_fail_open_answer_reads_no_verdict():
    """call_judge.opus_scope returns None both for a refusal ({"ok": false}) and for a fail-open answer ({"ok": true} with
    no roles), so the adapter must read the model's answer to tell them apart. The controls run first: a refusal reads deny
    on every row and a role list reads allow on every row. Then the fail-open answer: no row may read a verdict."""
    label = "call_judge.opus_scope: a fail-open answer"
    if need_runner(label) is None:
        return
    cases, problem = load_corpus("call_judge.opus_scope")
    if cases is None:
        check(label, False, problem)
        return

    def rows_under(answer):
        with faked_model((answer, None)) as calls:
            rows = judge_replay.replay("call_judge.opus_scope")
        return rows, calls

    refused, _ = rows_under({"ok": False})
    misses = [r["id"] for r in refused if r["got"] != "deny"]
    check("%s: control: a refusal reads deny on every row" % label, not misses, "read allow: %s" % ", ".join(misses))
    granted, _ = rows_under({"ok": True, "roles": ["reviewer"]})
    misses = [r["id"] for r in granted if r["got"] != "allow"]
    check("%s: control: a role list reads allow on every row" % label, not misses, "read deny: %s" % ", ".join(misses))
    failed_open, calls = rows_under({"ok": True})
    check("%s: scope: one model call per case" % label, len(calls) == len(cases),
          "%d calls for %d cases" % (len(calls), len(cases)))
    verdicts = ["%s read %s" % (r["id"], r["verdict"]) for r in failed_open if r["verdict"] != "UNKNOWN"]
    check("%s: reads UNKNOWN on every row, not a verdict" % label, not verdicts, "; ".join(verdicts))


def case_scope_helpers_touch_the_judges_they_feed():
    """A module that a judge's prompt comes from touches that judge: the scope rule of the judge replay decision, which
    names any module its prompt or model comes from. A subset check, since the rule requires each judge named here and
    does not forbid others."""
    label = "touched: a module a judge's prompt comes from"
    if need_runner(label) is None:
        return
    for path, judges in HELPER_TOUCH:
        got = judge_replay.touched([path])
        missing = [name for name in judges if name not in got]
        check("%s: %s names %s" % (label, path, ", ".join(judges)), not missing,
              "touched gave %s, missing %s" % (", ".join(got) or "none", ", ".join(missing)))


def case_malformed_corpus_exits_1_and_names_judge_and_path():
    """A corpus that does not parse, or parses to the wrong shape, exits 1 with one detail line that names the judge and its
    file, and makes no model call. The control: a well-formed file of one case reads that case and exits 0 with CI unset."""
    label = "--judge prose_judge, a malformed corpus"
    if need_runner(label) is None:
        return
    with runner_repo({"prose_judge": json.dumps([CONTROL_CASE])}):
        code, text, _, error = runner_output(["--judge", "prose_judge"])
    check("%s: control: a well-formed file reads its one case" % label,
          error is None and "prose_judge (1 cases," in text, error or text[-200:])
    check("%s: control: exits 0 with CI unset" % label, code == 0, "exit %r" % (code,))
    for tag, text in MALFORMED_CORPORA:
        with runner_repo({"prose_judge": text}):
            runs = {"prose_judge": runner_output(["--judge", "prose_judge"])}
        check_judges_without_corpus("%s (%s)" % (label, tag), runs)


CASES = (case_seam_control, case_corpora, case_corpus_not_under_hooks, case_scopes, case_touched, case_no_auth_rows,
         case_cli_exit_follows_ci, case_cli_changed_head, case_runner_named_nowhere_else,
         case_feedback_bad_entry_reads_unknown, case_feedback_clean_answer_reads_no_unknown,
         case_sendmessage_errored_call_reads_unknown, case_sendmessage_one_seam_call_per_case_whatever_the_wording,
         case_wording_prompt_text_is_not_copied, case_pin_change_checks_yml_names_every_judge,
         case_pin_change_package_names_every_judge, case_probe_names_the_secret_and_the_item,
         case_each_judge_answer_reads_as_its_own_verdict, case_majority_takes_the_verdict_of_the_runs,
         case_replay_model_error_is_no_answer_for_its_run, case_pending_judge_reads_no_cases,
         case_corpus_counts_while_page_pending, case_judge_without_corpus_fails_the_run,
         case_judge_other_than_page_without_corpus_file_fails_the_run,
         case_judge_other_than_page_with_empty_corpus_fails_the_run,
         case_pending_judge_missing_or_empty_corpus_reads_no_cases,
         case_pending_judge_with_cases_runs_its_rows, case_pending_exemption_follows_the_pending_table,
         case_changed_page_judge_file_runs_no_page_cases,
         case_feedback_hit_on_any_candidate_reads_refuse, case_opus_scope_fail_open_answer_reads_no_verdict,
         case_scope_helpers_touch_the_judges_they_feed, case_malformed_corpus_exits_1_and_names_judge_and_path)


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
