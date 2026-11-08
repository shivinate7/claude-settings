#!/usr/bin/env python3
"""Cases for the `ste-push` rule in hooks/guard.py, a PreToolUse Bash hook. Standard library only, and no
test runner. Run it from the repository root:

    python3 hooks/test_guard_ste_push.py

GUARD_UNDER_TEST points the run at another copy of the guard, as in hooks/test_guard.py.

WHAT IT PROVES. A `git push` whose net range changes a file in the ste-lint scope is linted once, from the
pushed checkout, and is refused when the lint fails. A lint that cannot be read is allowed, with a note. A
push that changes nothing in scope, or that is never linted, starts no lint.

THE SEAMS THE GUARD HONORS.
  STE_CHANGED_BIN  The program the guard runs for the lint, as `<program> <base>`, with the pushed checkout as
                   its working folder (the child's cwd). Unset, it is the repo's own bin/ste-changed. This file
                   sets it to a stub that reads STE_STUB_MODE. `real` execs bin/ste-changed of this clone, so
                   its output and exit code pass through. `unexpected` exits 7 with a traceback. `no-verdict`
                   prints the scope line only and exits 0. `pin` prints a PASS verdict and exits 3. `pin-fail`
                   prints a FAIL verdict and exits 3, the pin drift that comes with a failing lint.
  Verdict line     `ste-lint: PASS, ...` or `ste-lint: FAIL, ...` on stdout, as actions/ste-lint/run.sh prints it.
  Scope            the `paths`, `changed_paths` and `exclude` defaults of actions/ste-lint/action.yml, plus the
                   pushed checkout's .ste-lint-exclude.
  Chain            a commit that the same call makes before its push (commit, merge, cherry-pick, am, revert) is not in
                   the push's range, so a push after such a commit is refused when the commit would send in-scope
                   prose, and it is told to push in a call of its own.
  Lint base        origin's default branch, as CI's base is: a lane that merged main is judged on its own changes.
  Pinned inputs    the `with:` block under the pinned step: fail and exclude are applied as CI applies them, scope:
                   changed (the action's unquoted default) is applied, and an input the guard cannot apply (scope:
                   all) is noted unknown. A step the guard cannot parse is noted unknown.
  Record branch    the "record-branch" key of the checkout's extras file (lint/layout.py), else `roadmap`.
  CI pin           a `claude-settings/actions/ste-lint@<sha>` line in .github/workflows, or the checkout itself
                   holds actions/ste-lint/action.yml.
  Pin drift        the real bin/ste-changed, run on a clone whose pinned commit's lint files differ from its own
                   (drift_case). A FAIL with drift is allowed, noted unknown. This file fixes no text for the drift line.
  Note             a line in <CLAUDE_CONFIG_DIR>/guard.log that holds `ste-push` and `unknown`.

LINT STARTS. The guard runs in a child process that records every process the guard starts. A lint start is
a recorded child whose argv names ste-changed, ste_lint.py, stale_cites.py or run.sh.

The fixture helpers are new, not copied: hooks/test_guard.py runs its whole suite when it is imported.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
GUARD = os.environ.get("GUARD_UNDER_TEST") or os.path.join(HERE, "guard.py")
LINTER = os.path.join(REPO, "lint", "ste_lint.py")
REAL_STE_CHANGED = os.path.join(REPO, "bin", "ste-changed")
sys.path.insert(0, os.path.join(REPO, "lint"))
import _test_git  # noqa: E402,F401  the one home of the test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  the one home of the run folder and its sweep (lint/_test_temp.py)

RUN = _test_temp.run_folder()
STUB = os.path.join(RUN, "stub", "bin", "ste-changed")
GIT = ["git", "-c", "user.name=ste-push test", "-c", "user.email=ste-push-test@example.invalid"]
LINT_TOKEN = re.compile(r"ste-changed|ste_lint|stale_cites|run\.sh")

# A sentence of 38 plain words (STE001 says 30 at most), and a short clean one.
BAD = ("When the build passes on the branch, the reviewer checks each changed note against the style guide "
       "before the team merges the branch into the main line of daily work, so that no reader sees an unchecked page.")
CLEAN = "Open the note. Check each step. Run the build before you merge."


def note(text):
    return "# Note\n\n%s\n" % text


BLOAT_NOTES = {"docs/notes/a.md": note(CLEAN), "docs/notes/b.md": note(CLEAN),
               "docs/notes/c.md": note(BAD), "docs/notes/d.md": note(CLEAN)}   # the bad note is third, not first
BLOAT_FLAGGED = ["docs/notes/c.md"]
BLOAT_CLEAN = ["docs/notes/a.md", "docs/notes/b.md", "docs/notes/d.md"]
CLEAN_NOTES = {path: note(CLEAN) for path in BLOAT_NOTES}
MAIN = {"README.md": "# Repo\n"}
PIN_SHA = "1" * 40
WORKFLOW = ("name: checks\non: [pull_request]\njobs:\n  lint:\n    runs-on: ubuntu-latest\n    steps:\n"
            "      - uses: example/claude-settings/actions/ste-lint@%s\n" % PIN_SHA)
EXTRAS = {".claude/layout-extras.json": '{"kinds": {}, "record-branch": "records-test"}\n'}

# The stub at the STE_CHANGED_BIN seam. It is an executable Python script, so the guard can run it either way.
STUB_SOURCE = '''#!/usr/bin/env python3
# A stand-in for bin/ste-changed at the STE_CHANGED_BIN seam (hooks/test_guard_ste_push.py). Not the product.
import os
import sys

REAL = %r
mode = os.environ.get("STE_STUB_MODE", "real")
if mode == "real":
    os.execv(sys.executable, [sys.executable, REAL] + sys.argv[1:])
if mode == "unexpected":
    sys.stderr.write("Traceback (most recent call last):\\nRuntimeError: stub crash\\n")
    sys.exit(7)
if mode == "no-verdict":
    print("ste-lint: 1 file(s) in scope, 0 excluded")
    sys.exit(0)
if mode == "pin":
    print("ste-lint: PASS, 0 error(s), 0 warning(s) on changed lines")
    sys.stderr.write("ste-changed: CI pins ste-lint at 1111111 (stub)\\n")
    sys.exit(3)
if mode == "pin-fail":
    print("::error file=docs/notes/c.md,line=3::STE001 sentence has 38 words, the limit is 30")
    print("ste-lint: FAIL, 1 error(s), 0 warning(s) on changed lines")
    sys.stderr.write("ste-changed: CI pins ste-lint at 1111111 (stub)\\n")
    sys.exit(3)
sys.exit(9)
'''

# Runs the guard in a child that records each process the guard starts, then runs the guard as __main__.
PROBE = r"""
import json, runpy, subprocess, sys
guard, log = sys.argv[1], sys.argv[2]
starts = []
real_popen = subprocess.Popen


class RecordingPopen(real_popen):
    def __init__(self, args, *rest, **kwargs):
        argv = args if isinstance(args, (list, tuple)) else [args]
        starts.append({"argv": [str(a) for a in argv], "cwd": str(kwargs.get("cwd") or "")})
        super().__init__(args, *rest, **kwargs)


subprocess.Popen = RecordingPopen
sys.argv = [guard]
try:
    runpy.run_path(guard, run_name="__main__")
finally:
    with open(log, "w", encoding="utf-8") as handle:
        json.dump(starts, handle)
"""


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def git(where, *args):
    done = subprocess.run(GIT + list(args), cwd=where, capture_output=True, text=True)
    if done.returncode != 0:
        sys.exit("fixture setup failed: git %s in %r: %s" % (" ".join(args), where, done.stderr.strip()))
    return done


def make_pair(case_dir, main, topic, pin=True, workflow=WORKFLOW):
    """A bare origin, and a clone whose `main` is pushed to it. Branch `topic` then holds `topic`, committed
    on top of main, or no commit at all when `topic` is None. `workflow` is the checks file when `pin` is set."""
    origin = os.path.join(case_dir, "origin.git")
    clone = os.path.join(case_dir, "clone")
    git(case_dir, "init", "-q", "--bare", "-b", "main", origin)
    git(case_dir, "init", "-q", "-b", "main", clone)
    files = dict(main)
    if pin:
        files[".github/workflows/checks.yml"] = workflow
    for rel, text in files.items():
        write(os.path.join(clone, rel), text)
    git(clone, "add", "-A")
    git(clone, "commit", "-q", "-m", "main")
    git(clone, "remote", "add", "origin", origin)
    git(clone, "push", "-q", "origin", "main")
    git(clone, "checkout", "-q", "-b", "topic")
    if topic is not None:
        for rel, text in topic.items():
            write(os.path.join(clone, rel), text)
        git(clone, "add", "-A")
        git(clone, "commit", "-q", "-m", "topic")
    return clone


def require_range(clone, expected, base="origin/main"):
    """Fixture check: the net range of `topic` from `base` holds exactly `expected`."""
    done = git(clone, "diff", "--name-only", base + "...topic")
    got = sorted(line for line in done.stdout.splitlines() if line)
    if got != sorted(expected):
        sys.exit("fixture error: the range %s...topic holds %r, want %r" % (base, got, sorted(expected)))


def require_lint(clone, flagged, clean):
    """Fixture check: the real linter flags exactly `flagged` with STE001 errors, and no error in `clean`."""
    done = subprocess.run([sys.executable, LINTER, "--no-color", "--format", "json", "--fail-on", "never",
                           *flagged, *clean], cwd=clone, capture_output=True, text=True)
    if done.returncode != 0:
        sys.exit("fixture error: lint/ste_lint.py exited %d: %s" % (done.returncode, done.stderr.strip()[:300]))
    found = {f["path"] for f in json.loads(done.stdout)["findings"]
             if f["code"] == "STE001" and f["severity"] == "error"}
    if found != set(flagged):
        sys.exit("fixture error: STE001 flagged %r, want %r" % (sorted(found), sorted(flagged)))


def require_bloat(clone):
    require_range(clone, list(BLOAT_NOTES))
    require_lint(clone, BLOAT_FLAGGED, BLOAT_CLEAN)


class Outcome:
    def __init__(self, decision="", reason="", stderr="", starts=(), notes=(), error=""):
        self.decision, self.reason, self.stderr = decision, reason, stderr
        self.starts, self.notes, self.error = list(starts), list(notes), error


def read_decision(stdout):
    out = stdout.strip()
    if not out:
        return "allow", ""
    try:
        block = json.loads(out)["hookSpecificOutput"]
        return block["permissionDecision"], block.get("permissionDecisionReason", "")
    except (ValueError, KeyError, TypeError):
        return "unparsed", out[:200]


def guard_run(clone, command, case_dir, env=None, transcript=None):
    """Judge one Bash call from the pushed checkout, under the guard under test. `transcript` is the session
    transcript the hook call names (transcript_path), when a case needs the session's own record."""
    cfg = os.path.join(case_dir, "cfg")
    os.makedirs(cfg, exist_ok=True)
    spawn_log = os.path.join(case_dir, "spawns.json")
    body = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": clone}
    if transcript:
        body["transcript_path"] = transcript
    payload = json.dumps(body)
    environ = dict(os.environ)
    for name in ("TMPDIR", "TEMP", "TMP"):
        environ[name] = case_dir
    for name in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_CODE_REMOTE",
                 "CLAUDE_PROJECT_DIR", "STE_STUB_MODE"):
        environ.pop(name, None)
    environ.update({"CLAUDE_CONFIG_DIR": cfg, "CLAUDE_GUARD_ROOT_PID": str(os.getpid()),
                    "STE_CHANGED_BIN": STUB})
    environ.update(env or {})
    done = subprocess.run([sys.executable, "-c", PROBE, GUARD, spawn_log], input=payload,
                          capture_output=True, text=True, env=environ, timeout=300)
    if done.returncode != 0:
        return Outcome(error="the guard exited %d: %s" % (done.returncode, done.stderr.strip()[-300:]))
    decision, reason = read_decision(done.stdout)
    starts = []
    if os.path.exists(spawn_log):
        with open(spawn_log, encoding="utf-8") as handle:
            starts = json.load(handle)
    log = os.path.join(cfg, "guard.log")
    lines = []
    if os.path.exists(log):
        with open(log, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    return Outcome(decision, reason, done.stderr, starts, [line for line in lines if "ste-push" in line])


def lint_starts(out):
    return [s for s in out.starts if any(LINT_TOKEN.search(part) for part in s["argv"])]


def want_quiet(out, label):
    """Allowed, and no lint start: a push that lints nothing."""
    if out.error:
        return out.error
    if out.decision != "allow":
        return "decision is %r, want allow (%s)" % (out.decision, label)
    if lint_starts(out):
        return "%d lint start(s), want none (%s)" % (len(lint_starts(out)), label)
    return None


def want_denied(out, label):
    """Denied by ste-push, after exactly one lint start."""
    if out.error:
        return out.error
    if out.decision != "deny":
        return "decision is %r, want deny (%s)" % (out.decision, label)
    if "ste-push" not in out.reason:
        return "the deny reason does not name rule ste-push (%s)" % label
    if len(lint_starts(out)) != 1:
        return "%d lint starts, want exactly 1 (%s)" % (len(lint_starts(out)), label)
    return None


def want_unknown_note(out, label, lints=1):
    """Allowed, with a guard.log line for ste-push that says unknown. `lints` is the lint starts wanted, or None
    when the case does not say whether the guard lints."""
    if out.error:
        return out.error
    if out.decision != "allow":
        return "decision is %r, want allow: an unreadable lint never blocks (%s; %s)" % (
            out.decision, label, out.reason[:160])
    if lints is not None and len(lint_starts(out)) != lints:
        return "%d lint starts, want exactly %d (%s)" % (len(lint_starts(out)), lints, label)
    if not any("unknown" in line.lower() for line in out.notes):
        return "no guard.log line names ste-push and unknown (%s)" % label
    if "unknown" not in (out.reason + out.stderr).lower():
        return "neither the reason nor stderr says unknown (%s)" % label
    return None


def want_allowed_no_note(out, label):
    """Allowed, and no note says unknown: the pinned input was applied, so nothing was left unread."""
    if out.error:
        return out.error
    if out.decision != "allow":
        return "decision is %r, want allow (%s; %s)" % (out.decision, label, out.reason[:160])
    if any("unknown" in line.lower() for line in out.notes):
        return "a guard.log line says unknown, want none: the input is applied (%s)" % label
    if "unknown" in (out.reason + out.stderr).lower():
        return "the reason or stderr says unknown, want none (%s)" % label
    return None


def want_chain_denied(out, label):
    """Denied by ste-push, for a commit in the same call that the push cannot judge. The lint may not start."""
    if out.error:
        return out.error
    if out.decision != "deny":
        return "decision is %r, want deny (%s)" % (out.decision, label)
    if "ste-push" not in out.reason:
        return "the deny reason does not name rule ste-push (%s)" % label
    if "call of its own" not in out.reason:
        return "the deny reason does not say to push in a call of its own (%s)" % label
    return None


# ---- the cases

def case_bloated_note_denied(case_dir):
    clone = make_pair(case_dir, MAIN, BLOAT_NOTES)
    require_bloat(clone)
    out = guard_run(clone, "git push origin topic", case_dir)
    cause = want_denied(out, "a pushed note with a sentence over 30 words")
    if cause:
        return cause
    if "docs/notes/c.md" not in out.reason:
        return "the deny reason does not name the failing file docs/notes/c.md"
    if "fix the sentence" not in out.reason:
        return "the deny reason does not say to fix the sentence"
    if "ste_lint.py --fix" not in out.reason:
        return "the deny reason does not name ste_lint.py --fix"
    if "bloat" not in out.reason:
        return "the deny reason does not say that --fix covers bloat only"
    return None


def case_clean_prose_allowed(case_dir):
    clone = make_pair(case_dir, MAIN, CLEAN_NOTES)
    require_range(clone, list(CLEAN_NOTES))
    require_lint(clone, [], list(CLEAN_NOTES))
    out = guard_run(clone, "git push origin topic", case_dir)
    if out.error:
        return out.error
    if out.decision != "allow":
        return "decision is %r, want allow for clean prose" % out.decision
    starts = lint_starts(out)
    if len(starts) != 1:
        return "%d lint starts, want exactly 1 (the push is in scope)" % len(starts)
    if not starts[0]["cwd"] or os.path.realpath(starts[0]["cwd"]) != os.path.realpath(clone):
        return "the lint ran in %r, want the pushed checkout" % starts[0]["cwd"]
    if "main" not in [arg.replace("origin/", "") for arg in starts[0]["argv"]]:
        return "the lint was not given base main: argv %r" % (starts[0]["argv"],)
    return None


def case_code_only_starts_no_lint(case_dir):
    clone = make_pair(case_dir, MAIN, {"src/notes.py": '"""%s"""\n' % BAD})
    require_range(clone, ["src/notes.py"])
    out = guard_run(clone, "git push origin topic", case_dir)
    return want_quiet(out, "a push that changes no Markdown")


def case_nothing_new_starts_no_lint(case_dir):
    clone = make_pair(case_dir, dict(MAIN, **{"docs/old.md": note(BAD)}), None)
    git(clone, "update-ref", "refs/remotes/origin/topic", "HEAD")
    require_range(clone, [])
    require_lint(clone, ["docs/old.md"], [])
    out = guard_run(clone, "git push origin topic", case_dir)
    return want_quiet(out, "a push with nothing new")


def case_excluded_path_starts_no_lint(case_dir):
    clone = make_pair(case_dir, dict(MAIN, **{".ste-lint-exclude": "vendor/**\n"}),
                      {"vendor/notes/x.md": note(BAD)})
    require_range(clone, ["vendor/notes/x.md"])
    require_lint(clone, ["vendor/notes/x.md"], [])
    out = guard_run(clone, "git push origin topic", case_dir)
    return want_quiet(out, "a change only under a .ste-lint-exclude path")


def case_unreadable_lint(mode):
    def check(case_dir):
        clone = make_pair(case_dir, MAIN, BLOAT_NOTES)
        require_bloat(clone)
        out = guard_run(clone, "git push origin topic", case_dir, {"STE_STUB_MODE": mode})
        return want_unknown_note(out, "the lint stub mode %s" % mode)
    return check


def case_pin_drift_allowed(case_dir):
    clone = make_pair(case_dir, MAIN, CLEAN_NOTES)
    require_range(clone, list(CLEAN_NOTES))
    require_lint(clone, [], list(CLEAN_NOTES))
    out = guard_run(clone, "git push origin topic", case_dir, {"STE_STUB_MODE": "pin"})
    if out.error:
        return out.error
    if out.decision != "allow":
        return "decision is %r, want allow: exit 3 is pin drift, and the lint passed" % out.decision
    if len(lint_starts(out)) != 1:
        return "%d lint starts, want exactly 1" % len(lint_starts(out))
    return None


def skip_case(command, main=None, prepare=None, pin=True):
    """A push the lint never sees. The fixture's range holds the bad note, so a lint would deny it."""
    def check(case_dir):
        clone = make_pair(case_dir, dict(MAIN, **(main or {})), BLOAT_NOTES, pin=pin)
        require_bloat(clone)
        if prepare:
            prepare(clone)
        out = guard_run(clone, command, case_dir)
        return want_quiet(out, command)
    return check


def case_other_ref_not_linted(case_dir):
    clone = make_pair(case_dir, dict(MAIN, **{"docs/notes/a.md": note(CLEAN)}), {"docs/notes/c.md": note(BAD)})
    git(clone, "branch", "other", "origin/main")
    require_range(clone, ["docs/notes/c.md"])
    out = guard_run(clone, "git push origin other", case_dir)
    if out.error:
        return out.error
    if out.decision != "allow":
        return "decision is %r, want allow: the pushed ref is not HEAD" % out.decision
    if lint_starts(out):
        return "%d lint start(s), want none: ste-changed lints HEAD only" % len(lint_starts(out))
    if not any("unknown" in line.lower() for line in out.notes):
        return "no guard.log line names ste-push and unknown for a ref that is not HEAD"
    if "unknown" not in (out.reason + out.stderr).lower():
        return "neither the reason nor stderr says unknown for a ref that is not HEAD"
    return None


def case_claude_settings_itself_linted(case_dir):
    clone = make_pair(case_dir, dict(MAIN, **{"actions/ste-lint/action.yml": "name: STE lint\n"}),
                      BLOAT_NOTES, pin=False)
    require_bloat(clone)
    out = guard_run(clone, "git push origin topic", case_dir)
    return want_denied(out, "a checkout that is claude-settings itself")


def record_branch_case(command, main=None):
    """A push to the record branch. ste-push starts no lint there. The record's own rule (roadmap-one-writer)
    decides such a push, so the case asserts only that ste-push neither lints it nor judges it."""
    def check(case_dir):
        clone = make_pair(case_dir, dict(MAIN, **(main or {})), BLOAT_NOTES)
        require_bloat(clone)
        out = guard_run(clone, command, case_dir)
        if out.error:
            return out.error
        if lint_starts(out):
            return "%d lint start(s), want none: a record branch push is never linted (%s)" % (
                len(lint_starts(out)), command)
        if "ste-push" in out.reason:
            return "the decision names ste-push, which must not judge a record branch push (%s)" % command
        return None
    return check


# The triage proof roadmap-one-writer reads (hooks/guard_merge.py _own_tier_proved): the session's own newest
# get_session record carries cs-build:triage. The transcript is written here, in the shape hooks/own_session.py
# reads. hooks/test_guard.py is not imported for it, since that file runs its whole suite on import.
OWN_TAIL = "7" * 20
TRIAGE_ENV = {"CLAUDE_CODE_REMOTE_SESSION_ID": "cse_" + OWN_TAIL}


def triage_transcript(case_dir):
    """A transcript whose newest get_session record for this session carries cs-build:triage."""
    record = json.dumps({"ccr": {"id": "session_" + OWN_TAIL, "title": "triage", "tags": ["cs-build:triage"]}})
    lines = [
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "g1", "name": "mcp__claude-code-remote__get_session", "input": {}}]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "g1", "content": record}]}},
    ]
    path = os.path.join(case_dir, "triage.jsonl")
    write(path, "".join(json.dumps(line) + "\n" for line in lines))
    return path


def record_branch_triage_case(command, main=None):
    """A push to the record branch that roadmap-one-writer allows, because the own record proves the triage
    tier. The push reaches ste-push, which skips a record branch: the decision is allow and no lint starts. The
    decision is checked first, so a refusal by an earlier rule cannot pass this case."""
    def check(case_dir):
        clone = make_pair(case_dir, dict(MAIN, **(main or {})), BLOAT_NOTES)
        require_bloat(clone)
        out = guard_run(clone, command, case_dir, env=TRIAGE_ENV, transcript=triage_transcript(case_dir))
        if out.error:
            return out.error
        if out.decision != "allow":
            return "decision is %r, want allow: the triage record proves the tier (%s; %s)" % (
                out.decision, command, out.reason[:120])
        if lint_starts(out):
            return "%d lint start(s), want none: ste-push never lints a record branch push (%s)" % (
                len(lint_starts(out)), command)
        return None
    return check


def triage_control_case(command):
    """The same triage proof and the same bloated prose, pushed to a branch that is not the record branch. The
    proof does not switch the lint off: ste-push lints once and denies."""
    def check(case_dir):
        clone = make_pair(case_dir, MAIN, BLOAT_NOTES)
        require_bloat(clone)
        out = guard_run(clone, command, case_dir, env=TRIAGE_ENV, transcript=triage_transcript(case_dir))
        return want_denied(out, command)
    return check


def case_run_folder_sweep(case_dir):
    root = os.path.join(case_dir, "sweep")
    old = os.path.join(root, "111-" + "a" * 32)
    new = os.path.join(root, "222-" + "b" * 32)
    os.makedirs(old)
    os.makedirs(new)
    now = time.time()
    os.utime(old, (now - 2 * 86400, now - 2 * 86400))   # over a day old: swept
    os.utime(new, (now, now))                            # newer: kept
    own = _test_temp.run_folder(root)
    if os.path.exists(old):
        return "the sweep kept an old sibling run folder"
    if not os.path.isdir(new):
        return "the sweep removed a new sibling run folder"
    if not os.path.isdir(own):
        return "run_folder did not create this run's folder"
    return None


# ---- a commit that the same call makes before its push: the push's range does not hold it

CHAIN_ADD = "git add -A && git commit -m x && git push origin topic"
CHAIN_AM = "git commit -am x && git push origin topic"
CHAIN_STAGED = "git commit -m x && git push origin topic"
TRACKED_C = {"docs/notes/c.md": note(CLEAN)}   # main holds the note clean, so an edit to it is a tracked change


def write_c_bad(clone):
    write(os.path.join(clone, "docs/notes/c.md"), note(BAD))


def stage_c_bad(clone):
    write_c_bad(clone)
    git(clone, "add", "docs/notes/c.md")


def write_src_bad(clone):
    write(os.path.join(clone, "src/notes.py"), '"""%s"""\n' % BAD)


def chain_case(command, dirty, main=None, flagged=(), want=want_chain_denied):
    """A commit then a push in one call. The push's range holds nothing new, so the prose the commit adds is in no
    range the guard reads. `want(out, label)` judges the decision the call gets."""
    def check(case_dir):
        clone = make_pair(case_dir, dict(MAIN, **(main or {})), None)
        dirty(clone)
        require_range(clone, [])
        if flagged:
            require_lint(clone, list(flagged), [])
        return want(guard_run(clone, command, case_dir), command)
    return check


# ---- the lint base: origin's default branch, as CI's base is, never the push's own destination

def case_merged_main_allowed(case_dir, command="git push origin topic"):
    """Main gains a bad note after the lane pushed its branch, and the lane merges main and pushes again. CI's base
    is origin's default branch, so the bad note is outside the push's range: the lane's own note is the one linted,
    against main, and the push is allowed. `command` may name the merge too: the same call must still be allowed."""
    clone = make_pair(case_dir, MAIN, {"docs/notes/a.md": note(CLEAN)})
    git(clone, "push", "-q", "origin", "topic")   # origin/topic exists before main moves, as a lane's does
    git(clone, "checkout", "-q", "main")
    write(os.path.join(clone, "docs/notes/c.md"), note(BAD))
    git(clone, "add", "-A")
    git(clone, "commit", "-q", "-m", "bad note on main")
    git(clone, "push", "-q", "origin", "main")
    git(clone, "checkout", "-q", "topic")
    git(clone, "merge", "-q", "--no-edit", "origin/main")
    require_range(clone, ["docs/notes/a.md"], base="origin/main")
    require_range(clone, ["docs/notes/c.md"], base="origin/topic")
    require_lint(clone, ["docs/notes/c.md"], ["docs/notes/a.md"])
    out = guard_run(clone, command, case_dir)
    if out.error:
        return out.error
    if out.decision != "allow":
        return "decision is %r, want allow: the bad note came from main, not from this push (%s)" % (
            out.decision, out.reason[:160])
    if any("unknown" in line.lower() for line in out.notes):
        return "a guard.log line says unknown, want none: the base is known"
    starts = lint_starts(out)
    if len(starts) != 1:
        return "%d lint starts, want exactly 1: the lane's own note is in scope" % len(starts)
    if "main" not in [arg.replace("origin/", "") for arg in starts[0]["argv"]]:
        return "the lint base is not main: argv %r" % (starts[0]["argv"],)
    return None


# ---- a verb that makes a commit in the same call (merge, cherry-pick, am, revert): not in the push's range

MERGE_PUSH = "git merge other && git push origin topic"
CHERRY_PUSH = "git cherry-pick other && git push origin topic"
AM_PUSH = "git am ../bad.patch && git push origin topic"
REVERT_PUSH = "git revert --no-edit HEAD && git push origin topic"


def bad_note_on_other(clone):
    """Branch `other` holds one commit that adds the bad note. The clone is back on topic, which holds no commit."""
    git(clone, "checkout", "-q", "-b", "other")
    write(os.path.join(clone, "docs/notes/c.md"), note(BAD))
    git(clone, "add", "-A")
    git(clone, "commit", "-q", "-m", "bad note on other")
    require_lint(clone, ["docs/notes/c.md"], [])
    git(clone, "checkout", "-q", "topic")


def bad_note_patch_on_other(clone):
    """As bad_note_on_other, and that commit as a patch beside the clone, for `git am ../bad.patch`."""
    bad_note_on_other(clone)
    patch = git(clone, "format-patch", "-1", "--stdout", "other").stdout
    write(os.path.join(os.path.dirname(clone), "bad.patch"), patch)


def bad_note_then_removed(clone):
    """Topic adds the bad note in one commit and removes it in the next, so the push's range holds nothing. A revert
    of the removal brings the note back."""
    write(os.path.join(clone, "docs/notes/c.md"), note(BAD))
    git(clone, "add", "-A")
    git(clone, "commit", "-q", "-m", "bad note")
    require_lint(clone, ["docs/notes/c.md"], [])
    git(clone, "rm", "-q", "docs/notes/c.md")
    git(clone, "commit", "-q", "-m", "remove the note")


def want_chain_denied_unlinted(out, label):
    """want_chain_denied, and no lint start: the push cannot judge a commit this call makes."""
    cause = want_chain_denied(out, label)
    if cause:
        return cause
    if lint_starts(out):
        return "%d lint start(s), want none: the push cannot lint a commit this call makes (%s)" % (
            len(lint_starts(out)), label)
    return None


def verb_case(command, prepare):
    """A call that makes a commit with the bad note (`prepare`), then pushes. The push's range holds nothing, so the
    guard sees an in-scope file only when it reads what the call's own verb brings in."""
    def check(case_dir):
        clone = make_pair(case_dir, MAIN, None)
        prepare(clone)
        require_range(clone, [])
        return want_chain_denied_unlinted(guard_run(clone, command, case_dir), command)
    return check


# ---- a `cd` or a `git -C` that names the folder a commit runs in: the commit is judged in that folder

MAIN_C = dict(MAIN, **TRACKED_C)   # main holds docs/notes/c.md clean, so an edit to it is a tracked change


def other_checkout(case_dir):
    """A second checkout of make_pair's origin, on main, beside its `clone`: the folder a `git -C` names."""
    other = os.path.join(case_dir, "other")
    git(case_dir, "clone", "-q", os.path.join(case_dir, "origin.git"), other)
    return other


def folder_chain_case(template, dirty, start, want=want_chain_denied_unlinted):
    """The call `template` makes. %(a)s is the checkout `other` and %(b)s the clone `clone`. The in-scope note is dirty
    in each folder the tuple `dirty` names ("a", "b"), and the call starts in the folder `start` names. `want(out, label)`
    judges the decision. The push's range holds nothing, so no lint judges a commit the call makes."""
    def check(case_dir):
        clone = make_pair(case_dir, MAIN_C, None)
        other = other_checkout(case_dir)
        folders = {"a": other, "b": clone}
        for name in dirty:
            write_c_bad(folders[name])
            require_lint(folders[name], ["docs/notes/c.md"], [])
        require_range(clone, [])
        command = template % {"a": shlex.quote(other), "b": shlex.quote(clone)}
        return want(guard_run(folders[start], command, case_dir), command)
    return check


# ---- a push read in the folder it runs in: a heredoc commit's body does not hide the push, a repeated push is read
# where it runs, a `mkdir` makes the folder a later `cd` enters, and a folder the guard cannot read is noted

BAD_TOPIC = {"docs/notes/c.md": note(BAD)}   # the topic commit holds the bad note, so a push from it is refused


def bad_clone(case_dir):
    """The clone, on topic, one commit past main with the bad note: a push from it sends prose the lint refuses."""
    clone = make_pair(case_dir, MAIN_C, BAD_TOPIC)
    require_range(clone, ["docs/notes/c.md"])
    require_lint(clone, ["docs/notes/c.md"], [])
    return clone


def bad_checkout(case_dir):
    """A second checkout of make_pair's origin, on topic, with the bad note committed. The clone the shell starts in
    stays clean, so a push read in the wrong folder is allowed."""
    other = os.path.join(case_dir, "other")
    git(case_dir, "clone", "-q", os.path.join(case_dir, "origin.git"), other)
    git(other, "checkout", "-q", "-b", "topic")
    write_c_bad(other)
    git(other, "add", "-A")
    git(other, "commit", "-q", "-m", "bad note")
    require_range(other, ["docs/notes/c.md"], base="origin/main")
    require_lint(other, ["docs/notes/c.md"], [])
    return other


def want_denied_in(out, label, folder):
    """want_denied, and the one lint ran in `folder`, the checkout the push runs in."""
    cause = want_denied(out, label)
    if cause:
        return cause
    ran = lint_starts(out)[0]["cwd"]
    if os.path.realpath(ran) != os.path.realpath(folder):
        return "the lint ran in %r, want %r (%s)" % (ran, folder, label)
    return None


HEREDOC_PUSH = "git commit -F - <<'EOF'\nmsg\nEOF\ngit push origin topic"
COMMIT_M_PUSH = "git commit -m msg\ngit push origin topic"


def case_heredoc_commit_then_push(case_dir):
    clone = bad_clone(case_dir)
    return want_denied_in(guard_run(clone, HEREDOC_PUSH, case_dir), "a push after a heredoc commit", clone)


def case_commit_m_then_push_control(case_dir):
    clone = bad_clone(case_dir)
    return want_denied_in(guard_run(clone, COMMIT_M_PUSH, case_dir), "the control: a push after git commit -m", clone)


def case_cd_heredoc_commit_then_push(case_dir):
    clone = make_pair(case_dir, MAIN_C, None)
    other = bad_checkout(case_dir)
    command = "cd %s && git commit -F - <<'EOF'\nmsg\nEOF\ngit push origin topic" % shlex.quote(other)
    return want_denied_in(guard_run(clone, command, case_dir), "a cd, a heredoc commit, then a push", other)


def two_pushes_case(template, label):
    """`template` names the clone B (%(b)s) and the bad checkout A (%(a)s). B's push sends nothing. The second push,
    from A after the commit, sends the bad note, so it is read in A."""
    def check(case_dir):
        clone = make_pair(case_dir, MAIN_C, None)
        other = bad_checkout(case_dir)
        command = template % {"a": shlex.quote(other), "b": shlex.quote(clone)}
        return want_denied_in(guard_run(clone, command, case_dir), label, other)
    return check


def case_mkdir_cd_push(case_dir):
    """`mkdir -p` a folder inside A, `cd` into it, then push. The folder exists before the push runs, so the push is
    A's: git walks up from the new folder to A's repo. The shell starts in B, which has nothing to send."""
    clone = make_pair(case_dir, MAIN_C, None)
    other = bad_checkout(case_dir)
    fresh = shlex.quote(os.path.join(other, "fresh"))
    command = "mkdir -p %s; cd %s; git push origin topic" % (fresh, fresh)
    return want_denied_in(guard_run(clone, command, case_dir), "mkdir, cd into a new folder of A, then a push", other)


def case_cd_then_push_control(case_dir):
    clone = make_pair(case_dir, MAIN_C, None)
    other = bad_checkout(case_dir)
    command = "cd %s; git push origin topic" % shlex.quote(other)
    return want_denied_in(guard_run(clone, command, case_dir), "the control: cd into A, then a push", other)


def want_unread_ask(out, label):
    """Asked alone under rule push-unread-folder, no lint start, and a guard.log line that names ste-push and unknown.
    The ask is not a refusal by ste-push."""
    if out.error:
        return out.error
    if out.decision != "ask":
        return "decision is %r, want ask (%s; %s)" % (out.decision, label, out.reason[:160])
    if "push-unread-folder" not in out.reason:
        return "the ask does not name rule push-unread-folder (%s)" % label
    if lint_starts(out):
        return "%d lint start(s), want none (%s)" % (len(lint_starts(out)), label)
    if not any("unknown" in line.lower() for line in out.notes):
        return "no guard.log line names ste-push and unknown under the ask (%s)" % label
    return None


def want_chained_unread_ask(out, label):
    """Denied as the chained ask of rule push-unread-folder, with no lint start. Not a refusal by ste-push."""
    if out.error:
        return out.error
    if out.decision != "deny":
        return "decision is %r, want deny: a chained ask (%s; %s)" % (out.decision, label, out.reason[:160])
    if "ask-alone" not in out.reason or "push-unread-folder" not in out.reason:
        return "the deny is not the chained ask of push-unread-folder (%s; %s)" % (label, out.reason[:160])
    if "ste-push" in out.reason:
        return "refused by rule ste-push, want the chained ask (%s)" % label
    if lint_starts(out):
        return "%d lint start(s), want none (%s)" % (len(lint_starts(out)), label)
    return None


# Owner ruling 413 a (2026-11-08 06:11 CST) and coordinator ruling under item 410 a (2026-11-08 06:22 CST): a push
# whose folder cannot be read asks, as the forced push does. A `cd "$(...)"` is a second command, so its ask chains
# with the push and denies; a `cd` to a folder that is not there is one command and asks alone.
def unread_folder_push(template, chained):
    """A bare push after a `cd` the guard cannot read. `%(a)s` is the bad checkout the push would send the bad note
    from, if its folder were read."""
    def check(case_dir):
        clone = make_pair(case_dir, MAIN_C, None)
        other = bad_checkout(case_dir)
        command = template % {"a": shlex.quote(other)}
        out = guard_run(clone, command, case_dir)
        if chained:
            return want_chained_unread_ask(out, command)
        return want_unread_ask(out, command)
    return check


def case_cd_bare_push_control(case_dir):
    clone = make_pair(case_dir, MAIN_C, None)
    other = bad_checkout(case_dir)
    command = "cd %s && git push" % shlex.quote(other)
    return want_denied_in(guard_run(clone, command, case_dir), "the control: cd into A, then a bare push", other)


# ---- the pin compare: the real bin/ste-changed, run on a clone whose pinned commit's lint files differ

DRIFT_FILE = "hooks/route_match.py"   # a lint file in bin/ste-changed's LINT_FILES: a change to it is drift


def pinning(sha):
    """WORKFLOW with its pinned ste-lint commit replaced by `sha`."""
    return WORKFLOW.replace(PIN_SHA, sha)


def drift_checkout(case_dir, drift):
    """A clone of this checkout's HEAD, with bin/ste-changed and hooks/guard_ste.py as they stand in this checkout, so
    an edit to them is what runs. With `drift`, one commit more, which changes DRIFT_FILE: then HEAD~1 is a pin whose
    lint files differ from the clone's."""
    cs = os.path.join(case_dir, "cs")
    done = subprocess.run(["git", "clone", "-q", "--depth", "2", "file://" + REPO, cs], capture_output=True, text=True)
    if done.returncode != 0:
        sys.exit("fixture error: cannot clone %r: %s" % (REPO, done.stderr.strip()))
    for rel in ("bin/ste-changed", "hooks/guard_ste.py"):
        shutil.copy2(os.path.join(REPO, rel), os.path.join(cs, rel))
    if drift:
        with open(os.path.join(cs, DRIFT_FILE), "a", encoding="utf-8", newline="\n") as handle:
            handle.write("# A comment. It changes a lint file, so the pin compare reads drift.\n")
        git(cs, "add", DRIFT_FILE)
        git(cs, "commit", "-q", "-m", "drift")
    return cs


def drift_case(drift):
    """The real bin/ste-changed lints the bad note. The workflow pins HEAD~1 of the clone (drift), or its HEAD."""
    def check(case_dir):
        cs = drift_checkout(case_dir, drift)
        pinned = git(cs, "rev-parse", "HEAD~1" if drift else "HEAD").stdout.strip()
        clone = make_pair(case_dir, MAIN, BLOAT_NOTES, workflow=pinning(pinned))
        require_bloat(clone)
        tool = {"STE_CHANGED_BIN": os.path.join(cs, "bin", "ste-changed")}
        out = guard_run(clone, "git push origin topic", case_dir, tool)
        if drift:
            return want_unknown_note(out, "the real lint, pinned to a commit whose lint files differ")
        return want_denied(out, "the real lint, pinned to this checkout's own lint files (the control)")
    return check


# ---- the workflow layouts the pinned-step reader meets

def want_allowed(out, label):
    """Allowed. The pinned step's inputs can make a push allowed, never refused, so this only needs the allow."""
    if out.error:
        return out.error
    if out.decision != "allow":
        return "decision is %r, want allow (%s; %s)" % (out.decision, label, out.reason[:160])
    return None


def steps_workflow(steps):
    """The checks file with `steps` as its job's steps, each line at the indent the case writes."""
    return "name: checks\non: [pull_request]\njobs:\n  lint:\n    runs-on: ubuntu-latest\n    steps:\n" + steps


FOUR_STEP = "    - uses: example/claude-settings/actions/ste-lint@%s\n" % PIN_SHA
FOUR_FAIL_FALSE = steps_workflow(FOUR_STEP + '      with:\n        fail: "false"\n')
FOUR_NO_WITH = steps_workflow(FOUR_STEP)
FLOW_FAIL_FALSE = steps_workflow(
    '    - {uses: example/claude-settings/actions/ste-lint@%s, with: {fail: "false"}}\n' % PIN_SHA)


# ---- the pinned step's `with:` inputs

def pinned_with(*lines):
    """WORKFLOW with a `with:` block under its ste-lint step, one `key: value` line for each argument."""
    return WORKFLOW + "        with:\n" + "".join("          %s\n" % line for line in lines)


def with_case(label, workflow, want):
    """Push the bad note with the pinned step as `workflow` says. `want(out, label)` judges the decision."""
    def check(case_dir):
        clone = make_pair(case_dir, MAIN, BLOAT_NOTES, workflow=workflow)
        require_bloat(clone)
        return want(guard_run(clone, "git push origin topic", case_dir), label)
    return check


def write_stub():
    write(STUB, STUB_SOURCE % REAL_STE_CHANGED)
    os.chmod(STUB, 0o755)


def want_denied_case(case_dir, command, main=None):
    clone = make_pair(case_dir, dict(MAIN, **(main or {})), BLOAT_NOTES)
    require_bloat(clone)
    return want_denied(guard_run(clone, command, case_dir), command)


CASES = [
    ("ste-push: a sentence over 30 words in a pushed note is denied, naming the file and the remedy",
     case_bloated_note_denied),
    ("ste-push: clean prose is allowed, after one lint of the pushed checkout against main", case_clean_prose_allowed),
    ("ste-push: a push that changes no Markdown starts no lint", case_code_only_starts_no_lint),
    ("ste-push: a push with nothing new starts no lint", case_nothing_new_starts_no_lint),
    ("ste-push: a change only under a .ste-lint-exclude path starts no lint", case_excluded_path_starts_no_lint),
    ("ste-push: a lint that exits with an unexpected code is allowed, noted unknown", case_unreadable_lint("unexpected")),
    ("ste-push: a lint with no verdict line is allowed, noted unknown", case_unreadable_lint("no-verdict")),
    ("ste-push: exit 3 (pin drift only) is allowed after the lint passed", case_pin_drift_allowed),
    ("ste-push: a delete push starts no lint", skip_case("git push origin --delete old")),
    ("ste-push: a tag-only push starts no lint", skip_case("git push origin v1",
                                                          prepare=lambda clone: git(clone, "tag", "v1"))),
    ("ste-push: a push to archive/* starts no lint", skip_case("git push origin HEAD:archive/topic")),
    ("ste-push: a push to the default record branch roadmap starts no lint",
     record_branch_case("git push origin HEAD:roadmap")),
    ("ste-push: a push to the record branch the extras file names starts no lint",
     record_branch_case("git push origin HEAD:records-test", main=EXTRAS)),
    ("ste-push: a triage session's push of bloated prose to roadmap is allowed, with no lint",
     record_branch_triage_case("git push origin HEAD:roadmap")),
    ("ste-push: a triage session's push of bloated prose to the extras record branch is allowed, with no lint",
     record_branch_triage_case("git push origin HEAD:records-test", main=EXTRAS)),
    ("ste-push: a triage session's push of the same prose to feature-x is denied after one lint",
     triage_control_case("git push origin HEAD:feature-x")),
    ("ste-push: a push to a branch that is not the record branch is linted when the extras file names one",
     lambda case_dir: want_denied_case(case_dir, "git push origin HEAD:feature-x", EXTRAS)),
    ("ste-push: --dry-run starts no lint", skip_case("git push --dry-run origin topic")),
    ("ste-push: -n starts no lint", skip_case("git push -n origin topic")),
    ("ste-push: a quoted --dry-run after the push does not skip the push",
     lambda case_dir: want_denied_case(case_dir, 'git push origin topic && echo "--dry-run"')),
    ("ste-push: a pushed ref that is not HEAD is allowed, noted unknown, and not linted", case_other_ref_not_linted),
    ("ste-push: a repo whose CI runs no ste-lint step starts no lint", skip_case("git push origin topic", pin=False)),
    ("ste-push: a checkout that is claude-settings itself is linted", case_claude_settings_itself_linted),
    ("ste-push: a commit the same call pushes, with an in-scope note added by git add -A, is denied to push in "
     "its own call", chain_case(CHAIN_ADD, write_c_bad, flagged=["docs/notes/c.md"])),
    ("ste-push: commit -am then push, with an in-scope tracked note edited, is denied to push in its own call",
     chain_case(CHAIN_AM, write_c_bad, main=TRACKED_C, flagged=["docs/notes/c.md"])),
    ("ste-push: a staged in-scope note committed and pushed in one call is denied to push in its own call",
     chain_case(CHAIN_STAGED, stage_c_bad, flagged=["docs/notes/c.md"])),
    ("ste-push: the same add-commit-push chain with only a code file dirty is allowed, with no lint",
     chain_case(CHAIN_ADD, write_src_bad, want=want_quiet)),
    ("ste-push: a lane that merged origin/main is linted against main, not its own destination, and allowed",
     case_merged_main_allowed),
    ("ste-push: a merge of origin/main the same call makes is allowed, judged on the lane's own note "
     "(the verb control)",
     lambda case_dir: case_merged_main_allowed(case_dir, "git merge origin/main && git push origin topic")),
    ("ste-push: a merge the same call makes, bringing an in-scope bad note, is denied to push in its own call",
     verb_case(MERGE_PUSH, bad_note_on_other)),
    ("ste-push: a cherry-pick the same call makes, bringing an in-scope bad note, is denied to push in its own call",
     verb_case(CHERRY_PUSH, bad_note_on_other)),
    ("ste-push: a git am the same call makes, bringing an in-scope bad note, is denied to push in its own call",
     verb_case(AM_PUSH, bad_note_patch_on_other)),
    ("ste-push: a git revert the same call makes, restoring an in-scope bad note, is denied to push in its own call",
     verb_case(REVERT_PUSH, bad_note_then_removed)),
    ("ste-push: `git -C <A> status && cd <B> && git commit -am m && git push`, with B's in-scope note dirty, is denied "
     "to push in its own call (the commit runs in B, after the cd)",
     folder_chain_case("git -C %(a)s status && cd %(b)s && git commit -am m && git push origin topic", ("b",), "a")),
    ("ste-push: `cd <B> && git -C <A> commit -am m && git push` from B, with only A's in-scope note dirty, is allowed: "
     "the push from B sends no A commit, and B's range holds nothing in scope, so no lint",
     folder_chain_case("cd %(b)s && git -C %(a)s commit -am m && git push origin topic", ("a",), "b", want_quiet)),
    ("ste-push: the mirror control, the same chain with B's own in-scope note dirty and no commit in B, is allowed "
     "with no lint (a push folder with a dirty note is not refused)",
     folder_chain_case("cd %(b)s && git -C %(a)s commit -am m && git push origin topic", ("a", "b"), "b", want_quiet)),
    ("ste-push: the control, all in one tree: `git -C <B> status && cd <B> && git commit -am m && git push` with B's "
     "note dirty is denied to push in its own call",
     folder_chain_case("git -C %(b)s status && cd %(b)s && git commit -am m && git push origin topic", ("b",), "b")),
    ("ste-push: the control, all in one tree: `cd <B> && git -C <B> commit -am m && git push` with B's note dirty "
     "is denied to push in its own call",
     folder_chain_case("cd %(b)s && git -C %(b)s commit -am m && git push origin topic", ("b",), "b")),
    # A commit's folder is the shell's folder when it runs: a subshell's cd, or a pushd and popd pair, does not move it.
    ("ste-push: `pushd <A> && popd && git commit -am m && git push` from B, with B's note dirty, is denied to push in "
     "its own call (popd returns the shell to B, where the commit runs)",
     folder_chain_case("pushd %(a)s && popd && git commit -am m && git push origin topic", ("b",), "b")),
    ("ste-push: `(cd <A>) && git commit -am m && git push` from B, with B's note dirty, is denied to push in its own "
     "call (the subshell's cd ends with the parenthesis, so the commit runs in B)",
     folder_chain_case("(cd %(a)s) && git commit -am m && git push origin topic", ("b",), "b")),
    # After `&&` a failed cd ends the chain, so the commit never runs. The `;` then runs the push in the original
    # folder, which holds no new commit, so the push has nothing to lint.
    ("ste-push: `cd /nonexistent && git commit -am m; git push` from B, with B's note dirty, is allowed with no lint",
     folder_chain_case("cd /nonexistent && git commit -am m; git push origin topic", ("b",), "b", want_quiet)),
    ("ste-push: the control, `cd /nonexistent; git commit -am m && git push` from B, with B's note dirty, is denied "
     "to push in its own call (after `;` the commit runs in B)",
     folder_chain_case("cd /nonexistent; git commit -am m && git push origin topic", ("b",), "b")),
    # `--work-tree` names the files a commit reads, not the repo it lands in. Real git: `git --work-tree=A commit -am m`
    # run in B committed A's note on B's branch, so the push from B sends it.
    ("ste-push: `git --work-tree=<A> commit -am m && git push` from B, with A's note dirty and B clean, is denied "
     "to push in its own call (the commit lands in B with A's prose)",
     folder_chain_case("git --work-tree=%(a)s commit -am m && git push origin topic", ("a",), "b")),
    ("ste-push: `git --work-tree=<A> commit -am m && git push` from B, with B's note dirty and A clean, is allowed "
     "with no lint (B's dirty note is not in the commit)",
     folder_chain_case("git --work-tree=%(a)s commit -am m && git push origin topic", ("b",), "b", want_quiet)),
    ("ste-push: the control, `git --work-tree=<B> commit -am m && git push` from B, with B's note dirty, is denied "
     "to push in its own call",
     folder_chain_case("git --work-tree=%(b)s commit -am m && git push origin topic", ("b",), "b")),
    # `git -C "$X"` names no folder the guard can read, so the commit may land in B, the pushed tree, where B's
    # in-scope note is dirty. The push is denied to run in its own call, as a commit of unknown folder would be.
    ("ste-push: `git -C \"$X\" commit -am m && git push` from B, with B's note dirty, is denied to push in its own "
     "call (an unreadable commit folder counts in the pushed tree)",
     folder_chain_case('git -C "$X" commit -am m && git push origin topic', ("b",), "b")),
    # A push is read in the folder it runs in. A heredoc commit's body must not hide the push, a repeated push is read
    # where it runs, a `mkdir` makes the folder a later `cd` enters, and a folder the guard cannot read is noted.
    ("ste-push: a push after a `git commit -F -` heredoc is denied in its own checkout, whose topic holds the bad note",
     case_heredoc_commit_then_push),
    ("ste-push: the control, the same push after `git commit -m` is denied in the same checkout",
     case_commit_m_then_push_control),
    ("ste-push: `cd <A> && git commit -F - <<EOF` then a push is denied in A, the folder the push runs in",
     case_cd_heredoc_commit_then_push),
    ("ste-push: a second push after a heredoc commit is read in its own folder A, not the first push's folder B",
     two_pushes_case("cd %(b)s\ngit push origin topic\ncd %(a)s\n"
                     "git commit -F - <<'EOF'\nmsg\nEOF\ngit push origin topic",
                     "a second push after a heredoc commit")),
    ("ste-push: the control, the same second push after `git commit -m` is denied in A",
     two_pushes_case("cd %(b)s\ngit push origin topic\ncd %(a)s\ngit commit -m msg\ngit push origin topic",
                     "the control: a second push after git commit -m")),
    ("ste-push: `mkdir -p <A>/fresh; cd <A>/fresh; git push` is denied in A, the repo the new folder sits in",
     case_mkdir_cd_push),
    ("ste-push: the control, `cd <A>; git push` with a known folder is denied in A",
     case_cd_then_push_control),
    ("ste-push: a bare push after `cd \"$(...)\"` is a chained ask, denied in its own call, with no lint",
     unread_folder_push('cd "$(echo %(a)s)" && git push', chained=True)),
    ("ste-push: a bare push after `cd $HOME/x` asks, noted unknown, with no lint, since its folder cannot be read",
     unread_folder_push("cd $HOME/x && git push", chained=False)),
    ("ste-push: the control, a bare push after `cd <A>` with a known folder is denied in A",
     case_cd_bare_push_control),
    ("ste-push: a pinned fail: false (report only) is allowed with no unknown note",
     with_case("with: fail: false", pinned_with('fail: "false"'), want_allowed_no_note)),
    ("ste-push: a pinned exclude naming the bad note is allowed with no unknown note",
     with_case("with: exclude: docs/notes/c.md", pinned_with('exclude: "docs/notes/c.md"'), want_allowed_no_note)),
    ("ste-push: a pinned fail: true still denies the bad note",
     with_case("with: fail: true", pinned_with('fail: "true"'), want_denied)),
    ("ste-push: a pinned exclude that names another file still denies the bad note",
     with_case("with: exclude: docs/notes/d.md", pinned_with('exclude: "docs/notes/d.md"'), want_denied)),
    ("ste-push: a commented-out fail: false in the pinned step is ignored, and the bad note is denied",
     with_case("with: # fail: false", pinned_with('# fail: "false"'), want_denied)),
    ("ste-push: a pinned input the guard cannot apply (scope: all) is allowed, noted unknown",
     with_case("with: scope: all", pinned_with('scope: "all"'),
               lambda out, label: want_unknown_note(out, label, lints=None))),
    ("ste-push: exit 3 with a FAIL verdict (pin drift with a failing lint) is allowed, noted unknown",
     case_unreadable_lint("pin-fail")),
    ("ste-push: a FAIL from the real bin/ste-changed, pinned to a commit whose lint files differ, is allowed, "
     "noted unknown", drift_case(True)),
    ("ste-push: a FAIL from the real bin/ste-changed, pinned to this checkout's own lint files, is denied "
     "(the control)", drift_case(False)),
    ("ste-push: a pinned scope: changed (the action's unquoted default) is linted like no input, and the bad "
     "note is denied", with_case("with: scope: changed", pinned_with("scope: changed"), want_denied)),
    ("ste-push: a 4-space step with fail: false is allowed, never denied",
     with_case("4-space steps, with: fail: false", FOUR_FAIL_FALSE, want_allowed)),
    ("ste-push: a 4-space step with no with: is linted, and the bad note denied (the control)",
     with_case("4-space steps, no with:", FOUR_NO_WITH, want_denied)),
    ("ste-push: a pinned step the guard cannot parse (a flow mapping with fail: false) is allowed, noted unknown",
     with_case("flow-mapping step, with: fail: false", FLOW_FAIL_FALSE,
               lambda out, label: want_unknown_note(out, label, lints=None))),
    ("test-temp: the run-folder sweep removes an old sibling and keeps a new one", case_run_folder_sweep),
]


def main():
    failed = 0
    try:
        write_stub()
        for index, (name, check) in enumerate(CASES, 1):
            case_dir = os.path.join(RUN, "case-%02d" % index)
            os.makedirs(case_dir)
            cause = check(case_dir)
            if cause:
                failed += 1
                print("FAIL  %s: %s" % (name, cause))
            else:
                print("PASS  %s" % name)
    finally:
        shutil.rmtree(RUN, ignore_errors=True)
    total = len(CASES)
    if failed:
        print("test_guard_ste_push FAIL: %d of %d cases wrong" % (failed, total))
        return 1
    print("test_guard_ste_push PASS: %d of %d cases right" % (total, total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
