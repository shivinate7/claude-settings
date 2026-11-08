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
                   prints the scope line only and exits 0. `pin` prints a PASS verdict and exits 3.
  Verdict line     `ste-lint: PASS, ...` or `ste-lint: FAIL, ...` on stdout, as actions/ste-lint/run.sh prints it.
  Scope            the `paths`, `changed_paths` and `exclude` defaults of actions/ste-lint/action.yml, plus the
                   pushed checkout's .ste-lint-exclude.
  Record branch    the "record-branch" key of the checkout's extras file (lint/layout.py), else `roadmap`.
  CI pin           a `claude-settings/actions/ste-lint@<sha>` line in .github/workflows, or the checkout itself
                   holds actions/ste-lint/action.yml.
  Note             a line in <CLAUDE_CONFIG_DIR>/guard.log that holds `ste-push` and `unknown`.

LINT STARTS. The guard runs in a child process that records every process the guard starts. A lint start is
a recorded child whose argv names ste-changed, ste_lint.py, stale_cites.py or run.sh.

The fixture helpers are new, not copied: hooks/test_guard.py runs its whole suite when it is imported.
"""

import json
import os
import re
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


def make_pair(case_dir, main, topic, pin=True):
    """A bare origin, and a clone whose `main` is pushed to it. Branch `topic` then holds `topic`, committed
    on top of main, or no commit at all when `topic` is None."""
    origin = os.path.join(case_dir, "origin.git")
    clone = os.path.join(case_dir, "clone")
    git(case_dir, "init", "-q", "--bare", "-b", "main", origin)
    git(case_dir, "init", "-q", "-b", "main", clone)
    files = dict(main)
    if pin:
        files[".github/workflows/checks.yml"] = WORKFLOW
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


def require_range(clone, expected):
    """Fixture check: the push's net range holds exactly `expected`."""
    done = git(clone, "diff", "--name-only", "origin/main...topic")
    got = sorted(line for line in done.stdout.splitlines() if line)
    if got != sorted(expected):
        sys.exit("fixture error: the push's range holds %r, want %r" % (got, sorted(expected)))


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


def want_unknown_note(out, label):
    """Allowed, after one lint start, with a guard.log line for ste-push that says unknown."""
    if out.error:
        return out.error
    if out.decision != "allow":
        return "decision is %r, want allow: an unreadable lint never blocks (%s)" % (out.decision, label)
    if len(lint_starts(out)) != 1:
        return "%d lint starts, want exactly 1 (%s)" % (len(lint_starts(out)), label)
    if not any("unknown" in line.lower() for line in out.notes):
        return "no guard.log line names ste-push and unknown (%s)" % label
    if "unknown" not in (out.reason + out.stderr).lower():
        return "neither the reason nor stderr says unknown (%s)" % label
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
