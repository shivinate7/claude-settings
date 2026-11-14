#!/usr/bin/env python3
"""Cases for hooks/guard.py. Standard library only, and no test runner.

Run it from the repository root:

    python hooks/test_guard.py

GUARD_TESTS=windows-slice runs only the cases tagged for Windows (see WINDOWS_SHAPE below);
GUARD_TESTS=macos-slice runs only the cases that reach a darwin arm (see MACOS_REACH); unset
runs every case. Any other value stops the run before a case runs.

GUARD_FAMILY=<name> runs only one family of cases (FAMILIES, at the top of this file). An unknown
name, or a filter that matches no case, fails the run. GUARD_TIMING=1 prints what each fixture
block cost.

GUARD_HEARTBEAT=<seconds> sets the quiet time after which the run prints a progress line to stderr,
and appends it to STALL_WATCH_BEAT when that is set (default 60; a number above 0). A run that prints
nothing for minutes is cut by the stall watch. A malformed value stops the run before a case runs.

GUARD_SHARD=<i>/<n> or GUARD_SHARD=<i>-<n> runs every n-th selected case, starting at the i-th
(1-based), after the other filters. The n shards of one selection are disjoint and together hold
every case, so CI can split the suite across jobs and drop none. A malformed value stops the run
before a case runs.

GUARD_SECTION_DIR=<folder> reads the section files from that folder instead of tests/guard/. A folder with no
section file, or with two that share a `# section <n>` number, stops the run before any case.

Each case drives the guard as Claude Code drives it: one JSON object on stdin, and the decision read
back off stdout. An empty stdout is an allow. Anything else is parsed for permissionDecision.

BOTH DIRECTIONS ARE PINNED. A guard is exactly the wrong thing to change untested. Too loose and a
protected file is lost. Too tight and every session routes around it, which is the failure that
actually happened in both of the repositories this guard is ported from. So each GREEN case here is
as load-bearing as each RED one.

The cases come from two working guards and their own test suites:

  job-cost-reporting  harness/test_guard.py        the shared-tree cases
  q_max               harness/tests/guard.test.mjs the environment and frozen-path cases

Two literals are assembled from parts, so that this file cannot trip the guard it tests.
"""

import ast  # noqa: F401  the section files use it
import contextlib  # noqa: F401  the section files use it
import hashlib  # noqa: F401  the section files use it
import io  # noqa: F401  the section files use it
import json  # noqa: F401  the section files use it
import math
import os
import re
import shutil
import signal
import stat  # noqa: F401  the section files use it
import subprocess  # noqa: F401  the section files use it
import sys
import tempfile  # noqa: F401  the section files use it
import threading  # noqa: F401  the section files use it
import time
import uuid  # noqa: F401  the section files use it
from collections import namedtuple  # noqa: F401  the section files use it
from datetime import datetime, timedelta, timezone  # noqa: F401  the section files use it
from html.parser import HTMLParser  # noqa: F401  the section files use it
from unittest import mock  # noqa: F401  the section files use it

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
# GUARD_UNDER_TEST points the suite at another copy of the guard, such as a `.bak` copy carrying
# one mutation. A mutation test then needs no copy of this file, so the cases cannot drift from the
# cases that pass.
GUARD = os.environ.get("GUARD_UNDER_TEST") or os.path.join(HERE, "guard.py")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
from precompact_handoff import PREMISE_KINDS  # noqa: E402,F401  the one home of the premise kinds
import precompact_handoff as ph  # noqa: E402,F401  the one home of the handoff and flag paths
import local_time  # noqa: E402,F401  the one home of the inbox paths
import mutate_shared  # noqa: E402,F401  module_files: every module a copied guard may import

# Assembled, so this file never holds the token whole.
ENV = "." + "env"
VCS = "g" + "it"
# The settings file sets the agent model to sonnet (decision agent-model-cap), and every guard run in
# this suite inherits that. A case that tests the unset or empty default names its own `env`.
os.environ["CLAUDE_CODE_SUBAGENT_MODEL"] = "sonnet"

CASES = []

# GUARD_TESTS=windows-slice keeps only the cases tagged "windows": the ones that reach Windows-only
# guard code. GUARD_TESTS=macos-slice keeps only the cases tagged "macos": the ones that reach a darwin
# arm (MACOS_REACH). Unset or empty keeps every case. Any other value stops the run before a case runs.
GUARD_TESTS_MODES = ("", "windows-slice", "macos-slice")
# The tag each slice keeps. The windows slice also keeps the log checks in WINDOWS_CHECKERS. The macOS
# slice also keeps each log check whose family reaches a darwin arm. A log check has no session, so only
# a case reaches the session row.
SLICE_TAG = {"windows-slice": "windows", "macos-slice": "macos"}

# GUARD_FAMILY=<name> keeps only the cases of one family, so a change to one rule runs in that
# family's time. A case takes the family of the nearest FAMILY line above it (one per section),
# except a case named "rm-var", which is its own family wherever it sits. An unknown name stops the
# run before any fixture is built, and the message lists these names.
FAMILIES = {
    "shared-tree": "stash, reset, restore, checkout and the subject read",
    "branch-worktree": "branch delete and worktree remove/prune",
    "two-worktrees-one-branch": "a checkout, switch or worktree add that would take a branch another worktree of the clone holds is refused; the forms that take no such branch, and the holder's own checkout, pass",
    "worktree-home": "rule 0: an agent's shell call outside its recorded home, and the path forms it reads",
    "pointer-edit": "the pointer checkout's own files: a Write, Edit, MultiEdit or NotebookEdit into them is refused, naming EnterWorktree; its .git, a linked worktree, a target outside it, a stood-down pointer and the read tools pass",
    "session-home": "rule session-home: a session whose worktree is gone is refused a write into the primary checkout; its record and its cost",
    "scratchpad-owner": "rule scratchpad-owner: an agent that runs a script another agent of its session wrote into the shared scratchpad is refused; the write-time record, the run forms, the passes, the reads and the cost",
    "pointer": "the pointer HEAD checkout",
    "hand-made-worktree": "a worktree made by hand outside the agent home folder",
    "kill": "machine-wide kills and detached launches",
    "stream": "live streams, narrating commands, ln -s, waiter loops and background end conditions",
    "write": "the silent write",
    "readonly-shell-write": "a read-only agent's shell write: a redirect, tee, touch or mktemp, in the shell or inside an ssh command, is refused; its own scratchpad, the null devices, the reads, a writing role and a call with no agent pass",
    "push-delete": "push and delete",
    "linked-node-modules": "a dependency install or a recursive delete through a node_modules that is a link",
    "env": "environment files",
    "argv": "process arguments: a ps, pgrep or /proc form that prints other processes' full arguments is refused; pid-and-name forms, quoted or heredoc text and the guard's own readers pass",
    "git-env": "a command that sets GIT_DIR, GIT_WORK_TREE or GIT_INDEX_FILE",
    "hook-bypass": "a git commit, merge or push that skips the git hooks: core.hooksPath on the command or in the environment, --no-verify, and -n on commit; the mutation tool's own exemption",
    "merge": "merge into main, draft pull requests and the merge guard",
    "lane-closes-after-records": "archive_session of a lane: refused while the lane's repo has an open pull request on its step slug, while a branch of the lane is ahead of its repo's default branch with no pull request, or when the lane's record cannot be read",
    "lane-one-topic": "one lane, one topic: a send_message brief whose Topic differs from the lane's cs-topic, or names none, is refused; an older lane with no cs-topic is judged by its cs-step tags; a message without the marker passes unread",
    "brief-ids-in-roster": "a lane start (a create_session that tags a lane, whatever its prompt opens with) or a send_message with a Grant or Lane brief line anywhere in it (after a markdown lead) is refused when it names a bare session id, roster id or not, since a brief names a slug or a role and the lane looks the id up; an id with a backtick or a double quote on both sides passes. The check reads no roster, so a repo with none is judged the same",
    "message-time-matches-clock": "a send_message whose first non-blank line opens with a header stamp (a label of 1 to 4 words, then a comma, a colon or a spaced dash, then H:MM or HH:MM with optional seconds, then CST or CDT in any case) is refused when the stamp is wrong for the clock: a CST or CDT label that is not the clock's zone, a dated stamp more than 1 minute ahead, or an undated stamp 2 to 60 minutes ahead; an undated stamp more than 60 minutes ahead, or behind the clock, passes; a stamp later in the message, mid-line, on a status line, or on another tool passes. A dated ISO instant with an offset more than 1 minute ahead is refused too in `added` of an ArtifactData write to collection items (a whole instant, or a time fragment such as T20:24:00Z), `updatedAt` of a Write to a roadmap step file, each instant an Edit or MultiEdit writes to a roadmap step file (with or without a key), and the last literal `updatedAt` key in a Bash command (bare, quoted, or followed by `]`; then `:`, `=` or jq's `|=`; then a single- or double-quoted value); a time in prose, another field or collection, or a value with no offset passes",
    "sendmessage-session-id": "SendMessage whose to starts session_: refused, since a session_ id is not an agent name and delivery to one is unmeasured; mcp__claude-code-remote__send_message takes the session_id. Any other to, and that tool, pass this rule",
    "records-page": "a lane commit of the generated records page: refused unless the page is the base's",
    "records-page-ready": "a ready pull request whose head holds a stale records page is refused, on the MCP draft:false call and on gh pr ready in each form; a current, non-default, claim-holding, behind-the-base, empty, undo, draft, title-only or non-merge-tool call is allowed; a read that cannot run, or an ancestry unknown in a shallow clone, is refused unknown, and the unknown reason names no --confirm",
    "conflict-markers": "a git commit or --continue judged on the index and the files its adds or paths name, and a git push judged on the net change it sends: all three markers in one file's added lines are refused; a blind step before a commit, with a push after it, is refused only when the commit covers a triplet already in the tree; a chain that makes a conflict is refused, and a clean, whitespace-only, unstaged or half-marked file is allowed",
    "octopus-push": "a git push whose range adds a merge commit of more than two parents is refused, with a two-parent remedy; a push that writes main keeps its push-main ask",
    "cite": "cite by id",
    "scratchpad-message": "a git commit whose -F message file sits in a session scratchpad: an agent's call is refused in every flag form, through a link into the scratchpad, and an orchestrator's call, a heredoc, -m and a gh body file pass",
    "frozen": "frozen paths",
    "model-cap": "the agent model cap",
    "ask-alone": "an ask command chained with other commands denies, except a leading cd, export or an output tail; a lone ask command still asks",
    "paths": "path rules, builders and the test-author",
    "diff": "the diff judged at commit, push and stop",
    "builder-refuse": "a builder's diff refused at commit and push and blocked at the first stop, the deny names no path, and a test-author's diff still allowed",
    "impeccable": "impeccable is review-only",
    "port-question": "the page writer: a port question carries a Departs from line and holds nothing",
    "page-stale": "the waiting page: a publish of a page behind main's page.html is refused, a republish of main's page with empty designData and roadmap blocks is refused, a page with its own title and empty blocks is allowed, and an allowed publish of a page with live data writes the stamp",
    "uniform-pick": "the page writer: a pick never names an option that widens a shared tool",
    "press-link": "the page writer: a press in a web app carries a link to the exact page",
    "command-in-item": "the page writer: a task step never sends the owner to a file for a command",
    "gh-login-switch": "the page writer: a gh command in a task switches login first, shivinate7 by default and ssemwal-cdc only for a repo shivinate7 cannot reach",
    "task-names-check": "the page writer: a task carries a Why yours line naming the check that showed only the owner can do it",
    "owner-judge": "the page writer: a decision states the question form (Goal, Problem with its stake, one to three Based on lines, gain and lose in each option), or is a closed decision or a task",
    "question-departs": "the page writer: a decision says how it departs from main in a Departs from line, not a restatement of main",
    "option-letter-keys": "the page writer: an open decision's option keys are the lowercase letter of their position, unique, never none, its text names no option by a letter-and-digit key, and an option label that opens with a letter tag (B: x, Option B x) names the key's letter; a closed item is not judged; the page's letters are read from its own source",
    "rework-off-page": "the page writer: an item whose text says being reworked is not written unless its status is closed, and a str_replace that adds the phrase is refused",
    "item-field-rendered": "the page writer: a write names only item fields the page renders (the itemFields block of page.html)",
    "page-item-design": "the page writer: a design picture that misses its focus, its state or its height is refused at write, and an allowed publish of the waiting page records the published file",
    "rule9": "rule 9, the agent model floor",
    "role-model": "agent-role-model: a spawn's model against its role's row in the decision table, the missing-model default, and the fail-open read",
    "mask-script": "mask_script lexemes",
    "simulator": "the simulator boot and hold rules",
    "rm-var": "every case named rm-var, wherever it sits",
    "session-log": "the session id column of guard.log",
    "fail-closed": "a missing sibling module refuses the call, and never allows it",
    "reload-stamp": "a hook file broken, missing or mis-stamped: the guard waits and reloads, then refuses, never allows",
    "override": "the owner override: one act or a timed override, one session, the exclusions it never lifts",
    "handoff-unread": "after compaction, the guard refuses each call it judges until the session reads its handoff: the refusals, the allows, the cost, the fail-open copy, and the override",
    "handoff-sections": "a write that leaves a session's handoff without a section the prompt's marker names is refused, naming the sections; the marker is the one list; the fail-open copies; and the cost",
    "handoff-checked-stamp": "a write to a session handoff that restamps a premise's Checked value is refused without evidence in the session's transcript after its last compact boundary: the incident, the evidence forms, the boundary, the agent and handoff reads, the fail-open copies, the non-handoff files, and the cost",
    "wsl": "the WSL launch allow list, the refused WSL forms, and quoted or commented text",
    "load-brake": "the machine-load brake: busy and full on start calls, full on an agent's or a lane session's shell or file write (a lane session's own record tags cs-build:lane), the reader seam, no child process, no per-call read, no CPU read or wait, the cloud skip (CLAUDE_CODE_REMOTE=true reads nothing), the neutral load every other family's lane call meets",
    "agent-remote-tools": "an agent's call to an outward claude-code-remote tool is refused; the session's own call, an agent_type with no agent_id, and the read tools keep their verdict",
    "workflow-args": "a Workflow call whose args is, or holds as an array or object value, a placeholder (an all-caps word with an underscore, or __X__) is refused, naming it and the fix; an absent, empty or real args passes, and so does a short all-caps word or a sentence with an env var name",
    "sections": "the section files: a set the loader refuses (no section file, two files with one number, a log check appended after the LOG_CHECKS_EXTRA join) stops a run before any case",
    "misc": "anything outside a tagged section",
}
GUARD_FAMILY = os.environ.get("GUARD_FAMILY", "")
if GUARD_FAMILY and GUARD_FAMILY not in FAMILIES:
    sys.exit("GUARD_FAMILY=%r is not a family. Want one of: %s"
             % (GUARD_FAMILY, ", ".join(sorted(FAMILIES))))


# The progress beat (decision stall-watch: a quiet tool owes a line at least every 120 s). The quiet clock
# restarts at each line that `say` prints and at each beat. `beat` costs one clock read when the output is
# not quiet, and needs no thread or timer.
def parse_heartbeat(value):
    if not value:
        return 60.0
    try:
        secs = float(value)
    except ValueError:
        secs = math.nan
    if not (math.isfinite(secs) and secs > 0):
        sys.exit("GUARD_HEARTBEAT=%r is not a number of seconds above 0. Want a float, or unset for 60."
                 % value)
    return secs


GUARD_HEARTBEAT = parse_heartbeat(os.environ.get("GUARD_HEARTBEAT", ""))
BEAT_FILE = os.environ.get("STALL_WATCH_BEAT", "")  # the stall watch reads this file (hooks/stall_watch.py)
QUIET_SINCE = [time.monotonic()]  # the import counts as quiet time, so a slow import is a stretch too


def say(line):
    """Print one line, flushed, and restart the quiet clock. Piped output is block-buffered: without the
    flush a case line reaches a `| tail` or a file only at exit."""
    print(line, flush=True)
    QUIET_SINCE[0] = time.monotonic()


def beat(where):
    """Print a progress line to stderr, and append it to STALL_WATCH_BEAT, when the output has been quiet
    for GUARD_HEARTBEAT seconds. A caller marks a point where the run may spend that long. The line never
    starts with PASS, FAIL or ok: mutate_guard.py and test_wrappers.py read those as case lines."""
    now = time.monotonic()
    quiet = now - QUIET_SINCE[0]
    if quiet < GUARD_HEARTBEAT:
        return
    QUIET_SINCE[0] = now
    line = "test_guard: still running, %.0fs quiet, %s" % (quiet, where)
    print(line, file=sys.stderr, flush=True)
    if BEAT_FILE:
        try:
            with open(BEAT_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass


def parse_shard(value):
    """(i, n) from GUARD_SHARD's "<i>-<n>" or "<i>/<n>", 1 <= i <= n; (1, 1) when unset.
    Anything else stops the run. Builders use "<i>-<n>" because the harness refuses `VAR=i/n cmd`
    in a worktree (bandaid); CI keeps "<i>/<n>"."""
    if not value:
        return 1, 1
    m = re.fullmatch(r"([1-9][0-9]*)[/-]([1-9][0-9]*)", value)
    if not m or int(m.group(1)) > int(m.group(2)):
        sys.exit("GUARD_SHARD=%r: want <i>-<n> (builders; the harness refuses VAR=i/n cmd in a worktree) "
                 "or <i>/<n> (CI), with 1 <= i <= n. Nothing ran." % value)
    return int(m.group(1)), int(m.group(2))


def shard_of(items, shard):
    """The items of one shard: every n-th item, starting at index i-1."""
    i, n = shard
    return items[i - 1::n]


GUARD_SHARD = parse_shard(os.environ.get("GUARD_SHARD", ""))
FAMILY = "misc"  # set at each section header below
# TEMP_DIR is the temp folder the guard reads for the cases added while it is set, or None for the
# system temp. add() records it, and decide() puts it in TMPDIR, TEMP and TMP for that guard run.
# The silent-write section sets it to ROOT/tmp, so its throwaway cases sit under it while every
# other fixture (ROOT/nogit, ROOT/repo) stays outside it. Left None, a case keeps the system temp,
# which holds ROOT, so a case that sets nothing is judged as it always was.
TEMP_DIR = None


def _family(name):
    """The family a case or a log check takes: session-log and argv by prefix, rm-var by name, else FAMILY."""
    if name.startswith("session-log:"):
        return "session-log"
    if name.startswith("argv:"):
        return "argv"
    return "rm-var" if "rm-var" in name else FAMILY


LOG_FAMILY = {}  # log check label -> family, filled as each log check is registered


class _TaggedLogs(list):
    """LOG_CHECKS_EXTRA: each (label, check) appended takes the family in force at that line."""

    def append(self, item):
        LOG_FAMILY[item[0]] = _family(item[0])
        list.append(self, item)


# A case this platform does not run is a SKIP row with its reason: never a PASS, never a silent drop.
# skip_case records it here, and the rows join LOG_CHECKS with the other log checks, further down.
SKIP_ROWS = []
# A log check in this set builds its own folders and reads none of the lazy fixtures, so a run that
# selects only such checks (GUARD_FAMILY=load-brake) skips the fixture build, which takes minutes.
FIXTURELESS_CHECKS = set()
NO_PS = "Windows has no ps, so ownership reads unknown and this case does not run here"
NO_STAND_IN = "a POSIX stand-in git does not reach CreateProcess, so this case does not run here"
NO_ORPHAN = "needs a PPID-1 orphan from ps, which this host does not give"
NO_SIMULATOR = "the simulator fakes are POSIX shell scripts, and Windows has no xcrun or ps to fake"
NO_EXEC_BIT = "Windows git ignores the exec bit (core.filemode is false), so a chmod makes no mode change here"


def skip_case(label, reason):
    """Register a case that cannot run on this platform. It prints as SKIP with its reason, and
    run_cases counts it. The family is the one in force at this line, as for a log check."""
    LOG_FAMILY[label] = _family(label)
    SKIP_ROWS.append((label, lambda: (SKIP, reason)))


# GUARD_TIMING=1 prints, once at the end, the seconds each fixture block took: the eager blocks at
# import, and each lazy block the first time a case needs it. Unset, a run prints nothing extra.
GUARD_TIMING = os.environ.get("GUARD_TIMING") == "1"
TIMINGS = []
_TIMED_LAST = [time.perf_counter()]


def _mark(label):
    """GUARD_TIMING only: the seconds since the previous mark, recorded under `label`."""
    if GUARD_TIMING:
        now = time.perf_counter()
        TIMINGS.append((label, now - _TIMED_LAST[0]))
        _TIMED_LAST[0] = now


_TIMED_INNER = []  # one running total per nested _timed call: the seconds its inner builders took


def _timed(label, build):
    """GUARD_TIMING only: run `build`, recording its own seconds under `label`, not the seconds of a
    builder it runs inside (a push destination builds the branch repos first)."""
    start = time.perf_counter()
    _TIMED_INNER.append(0.0)
    build()
    took = time.perf_counter() - start
    inner = _TIMED_INNER.pop()
    if _TIMED_INNER:
        _TIMED_INNER[-1] += took
    if GUARD_TIMING:
        TIMINGS.append((label, took - inner))


def _timing_report():
    if GUARD_TIMING:
        totals = {}  # a label can repeat (every diff repo is one `build`): sum them
        for label, secs in TIMINGS:
            totals[label] = totals.get(label, 0.0) + secs
        print("fixture timing, seconds (net of any builder a block runs):")
        for label, secs in totals.items():
            print("  %8.2f  %s" % (secs, label))
        print("  %8.2f  total" % sum(totals.values()))

# A case's input carries a Windows-only shape: a backslash, a drive letter, .exe/.cmd/.ps1 names, NUL or
# $null, cmd /c, or PowerShell with its verbs and taskkill.
WINDOWS_SHAPE = re.compile(
    r"\\|(?<![A-Za-z])[A-Za-z]:[\\/]|\.(?:exe|cmd|ps1)\b|\bnul\b|\$null\b|\bcmd(?:\.exe)?\s+/c\b"
    r"|(?<![\w./-])/[A-Za-z](?=/|[\s;\"']|$)"
    r"|\b(?:Start-Job|Start-Process|Stop-Process|Remove-Item|taskkill|powershell|pwsh)\b|PowerShell",
    re.I)


def windows_shaped(*parts):
    """True when a case's literal input, or a path under the fixture root, carries a Windows shape.

    A fixture path is built with os.path.join, so on Windows it carries backslashes and a drive
    letter that Linux never sees. Both spellings of ROOT, and the path that follows it, read as
    forward slashes first, so the tag does not depend on the platform the suite runs on.
    """
    text = " ".join(str(p) for p in parts if p is not None)
    for root in {ROOT, slash(ROOT)}:
        text = re.sub(re.escape(root) + r"[^\s\"'`;|&]*",
                      lambda m: "<fixture>" + m.group(0)[len(root):].replace("\\", "/"), text)
    return WINDOWS_SHAPE.search(text) is not None


# GUARD_TESTS=macos-slice keeps only the cases tagged "macos": the ones that reach a darwin arm. Each row
# names an arm by file and function, with the cases that reach it. macos_arm_problems() holds the rows to
# the arms the ast scan finds in hooks/, so an arm with no row fails the run before any case runs.
# The macOS-only arms, by kind: a sys.platform test that holds on darwin, the else of one that does not,
# and a ps, lsof or launchctl argument list. Each arm is read in a hooks module the guard suite reaches.
MACOS_COMMANDS = ("ps", "lsof", "launchctl")
MACOS_REACH = {
    ("hooks/guard.py", "_read_memory"): lambda family, session: family == "load-brake",
    ("hooks/guard_rm_var.py", "_rm_real"): lambda family, session: family == "rm-var",
    ("hooks/proc_env.py", "_entries"): lambda family, session: session is not None,
    ("hooks/git_reads.py", "_process_start_ms"): lambda family, session: family in ("kill", "branch-worktree"),
    ("hooks/guard_kill.py", "_process_parents"): lambda family, session: family == "kill",
    ("hooks/guard_kill.py", "_pid_cwd"): lambda family, session: family == "kill",
    ("hooks/guard_kill.py", "_ps_ppid"): lambda family, session: family == "kill",
    ("hooks/guard_kill.py", "session_root_pid"): lambda family, session: family == "kill",
}


def macos_reached(family, session):
    return any(reach(family, session) for reach in MACOS_REACH.values())


def _mentions_sys_platform(node):
    return any(isinstance(n, ast.Attribute) and n.attr == "platform"
               and isinstance(n.value, ast.Name) and n.value.id == "sys" for n in ast.walk(node))


def _platform_truth(test):
    """What a sys.platform test says when sys.platform is darwin: True or False, or None when the test reads
    a name other than sys, which this scan does not evaluate."""
    if {n.id for n in ast.walk(test) if isinstance(n, ast.Name)} - {"sys"}:
        return None

    class DarwinSys:
        platform = "darwin"

    expr = ast.fix_missing_locations(ast.Expression(body=test))
    try:
        return bool(eval(compile(expr, "<platform test>", "eval"), {"sys": DarwinSys}, {}))
    except Exception:
        return None


def _product_reach():
    """The hooks modules the guard suite reaches: guard.py and every hooks module it imports, read with the ast.
    Test files are not product code, so they are left out."""
    hooks = os.path.dirname(os.path.abspath(__file__))
    modules = {n[:-3] for n in os.listdir(hooks) if n.endswith(".py") and not n.startswith("test_")}
    reach, todo = set(), ["guard"]
    while todo:
        module = todo.pop()
        if module in reach:
            continue
        reach.add(module)
        with open(os.path.join(hooks, module + ".py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = {node.module.split(".")[0]}
            else:
                continue
            todo.extend((names & modules) - reach)
    return reach


def darwin_arms():
    """(file, function) of each macOS-only arm in a hooks module the guard reaches. The ast reads the code, so a
    string or a comment that names darwin, ps or lsof is not an arm."""
    found = set()
    hooks = os.path.dirname(os.path.abspath(__file__))
    for module in sorted(_product_reach()):
        name = module + ".py"
        path = os.path.join(hooks, name)
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=path)
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}

        def owner(node):
            while node in parents and not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                node = parents[node]
            return getattr(node, "name", "<module>")

        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.IfExp)) and _mentions_sys_platform(node.test):
                truth = _platform_truth(node.test)
                if truth or (truth is False and node.orelse):
                    found.add(("hooks/" + name, owner(node)))
            if isinstance(node, (ast.List, ast.Tuple)) and node.elts \
                    and isinstance(node.elts[0], ast.Constant) and node.elts[0].value in MACOS_COMMANDS:
                found.add(("hooks/" + name, owner(node)))
    return found


def macos_arm_problems():
    """What is wrong with MACOS_REACH against the darwin arms in hooks/: an arm with no row, a row that names
    no arm, and a row that reaches no case."""
    arms = darwin_arms()
    rows = set(MACOS_REACH)
    problems = ["untagged darwin arm %s::%s: add a row to MACOS_REACH" % arm for arm in sorted(arms - rows)]
    problems += ["MACOS_REACH row %s::%s names no darwin arm in hooks/" % row for row in sorted(rows - arms)]
    units = [(c["family"], c["session"]) for c in CASES] + [(LOG_FAMILY.get(label), None) for label, _ in LOG_CHECKS]
    problems += ["MACOS_REACH row %s::%s reaches no case or log check" % row for row in sorted(rows)
                 if not any(MACOS_REACH[row](family, session) for family, session in units)]
    return problems


def add(name, expected, rule=None, raw=None, tool="Bash", cwd=None, env_path=None,
        session=None, carries=(), lacks=(), config=None, agent_id=None, no_root=False, silent=False,
        agent_type=None, event=None, stop_active=False, windows=False, transcript=None,
        max_seconds=None, env=None, guard=None, **tool_input):
    """Register one case.

    `guard` is the path of a copy of hooks/guard.py to run in place of this repository's, for the
    cases that need a checkout whose origin/main they control (see the page-stale section). None runs
    this repository's guard.

    `env` is the environment the guard run gets on top of the runner's own, for the cases that name a
    session id (see decide, which drops the runner's id first).

    `carries` names fragments the printed reason MUST hold, which is how a case pins what an
    approver reads, not only the decision. A tuple inside `carries` is any-of: the reason holds
    one of its fragments. `lacks` names fragments the printed reason MUST NOT hold.

    A case NEVER opts out of the generic-reason check. Which fragments a reason may name is read
    from the case's RULE, through `REASON_MAY_NAME` below, so the exemption belongs to one rule and
    no case can widen it by itself.

    `agent_id`, when given, rides on the payload the same way the harness sends it for a
    agent's own tool call: alongside `tool_name` and `tool_input`, never inside either.
    """
    CASES.append({
        "name": name,
        "expected": expected,
        "rule": rule,
        "raw": raw,
        "tool": tool,
        "cwd": cwd,
        "env_path": env_path,
        "session": session,
        "carries": (carries,) if isinstance(carries, str) else tuple(carries),
        "lacks": (lacks,) if isinstance(lacks, str) else tuple(lacks),
        # The config directory the case runs against. It decides where the global rules file is
        # read from, so a pointer case names its own and every other case keeps the default.
        "config": config,
        # The payload's `transcript_path`, when a case names one: the agents of the session
        # are the folder beside it, `<session>/subagents/agent-<id>.jsonl`.
        "transcript": transcript,
        "agent_id": agent_id,
        "agent_type": agent_type,
        "event": event,
        "stop_active": stop_active,
        "no_root": no_root,
        # A case that must be judged within this many seconds. A slower verdict fails the case.
        "max_seconds": max_seconds,
        # Variables this case sets on the guard's environment. A None value unsets one (see decide).
        "env": env,
        # The guard copy this case runs (see add), or None for this repository's guard.
        "guard": guard,
        # An allow that must print NOTHING, not even context. Only a case that says so is held to it.
        "silent": silent,
        # The temp folder this case's guard run reads as its own (see TEMP_DIR above).
        "temp": TEMP_DIR,
        "tool_input": tool_input,
        # Tagged for GUARD_TESTS=windows-slice. A session case reads a live process's start time,
        # which on Windows is the ctypes arm of _process_start_ms (guard.py L1837-1905).
        "family": _family(name),
        "windows": bool(windows or session is not None or windows_shaped(
            tool, raw, cwd, env_path, config, *tool_input.values())),
        # Tagged for GUARD_TESTS=macos-slice: the case reaches a darwin arm (MACOS_REACH).
        "macos": macos_reached(_family(name), session),
    })


def sh(name, command, expected, rule=None, tool="Bash", cwd=None, env_path=None, session=None,
       carries=(), lacks=(), config=None, agent_id=None, no_root=False, silent=False,
       agent_type=None, transcript=None, env=None):
    add(name, expected, rule=rule, tool=tool, cwd=cwd, env_path=env_path, session=session,
        agent_id=agent_id, agent_type=agent_type, no_root=no_root, silent=silent,
        carries=carries, lacks=lacks, config=config, transcript=transcript, env=env, command=command)


# ASK ALONE. A shell call that holds a command
# the guard would ASK on, chained with other commands by `&&`, `||`, `;`, `|` or a newline, is DENIED to
# the agent, and the remedy says to run that command alone or drop it. A lone ask command still asks, and a
# deny anywhere in the call still wins. Decision ask-commands-run-alone: a
# leading `cd X &&`, `Set-Location X;` or `export NAME=value &&`, and an output tail (`| tail -N`,
# `| head -N`, `| Out-Null`, `&& echo done`, `; Write-Host done`), are no second command, so that call
# asks once. Any other chained command still denies. CHAIN_ASK is the rule id the deny prints (the lane slug;
# the cases below pin it, so one edit re-points them all). ALONE is the one word the remedy must
# carry. Each ask rule's own id is NOT in REASON_MAY_NAME for this rule, so a reason that names an
# ask command must still avoid every FORBIDDEN_IN_A_REASON fragment.
CHAIN_ASK = "ask-alone"
ALONE = "alone"


def chained_ask(name, command, **kw):
    """One case: `command` holds an ask command chained with other commands, so it denies, never asks."""
    more = kw.pop("carries", ())
    carries = (ALONE,) + ((more,) if isinstance(more, str) else tuple(more))
    sh(name, command, "deny", CHAIN_ASK, carries=carries, **kw)


# The cases after the helpers above are section files in tests/guard/. A section file's first line is
# `# section <n>`, where n orders them. n need not be a FAMILY line: a section with no FAMILY statement, such as s00442, keeps the module's default family, misc.
# They run here, in this module's globals, in n order: the case and log-check order is the one-file order.
SECTION_DIR = os.path.join(HERE, "..", "tests", "guard")


def load_sections(section_dir):
    """Run each section file of section_dir here, in n order. No file, or two files with one n, stops the run."""
    found = []
    for name in (sorted(os.listdir(section_dir)) if os.path.isdir(section_dir) else []):
        if not name.endswith(".py"):
            continue
        path = os.path.join(section_dir, name)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        head = re.match(r"# section (\d+)\n", text)
        if not head:
            sys.exit("fixture setup failed: %s has no `# section <n>` first line" % path)
        found.append((int(head.group(1)), path, text))
    if not found:
        sys.exit("fixture setup failed: no section file in %s, so the run would hold no case" % section_dir)
    numbers = [n for n, _, _ in found]
    for n in sorted(set(numbers)):
        if numbers.count(n) > 1:
            sys.exit("fixture setup failed: section number %d is on %d section files" % (n, numbers.count(n)))
    for _, path, text in sorted(found):
        exec(compile(text, path, "exec"), globals())


load_sections(os.environ.get("GUARD_SECTION_DIR") or SECTION_DIR)
# A log check appended to LOG_CHECKS_EXTRA after its join is in no run. Refuse that, rather than drop it.
UNJOINED = [label for label, check in LOG_CHECKS_EXTRA if (label, check) not in LOG_CHECKS]
if UNJOINED:
    sys.exit("fixture setup failed: %d log check(s) were appended to LOG_CHECKS_EXTRA after its join and "
             "never run, first: %s" % (len(UNJOINED), UNJOINED[0]))

# A section set the loader refuses must stop a run before any case. A refusal that reads as a pass would hide
# every case the set holds, so each check below runs a child run of this runner on such a set and reads the stop.
# The child runs the family that builds no fixture, so each check costs one import. The checks join LOG_CHECKS
# directly: LOG_CHECKS_EXTRA has joined already, and an append to it here would be the loss this check refuses.
NO_SYMLINK = "a symlink needs a privilege this Windows run does not hold, so this check does not run here"
EMPTY_SECTIONS_LABEL = "sections: a run with no section file stops before any case"
DUPLICATE_SECTIONS_LABEL = "sections: two section files with one number stop the run before any case"
LATE_APPEND_LABEL = "sections: a log check appended after the join stops the run before any case"


def section_child_run(folder):
    """This runner, in a child process, on the section files of `folder`, under the family that builds no fixture.
    -> (rc, output), rc None when it does not end in 300 s. The child leads its own process group: a sleep that
    its import starts (OWNED) would hold a pipe open, so the output goes to a file, and the group ends with the child."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GUARD_", "MUTATE_ONLY"))}
    env.update(GUARD_FAMILY="load-brake", GUARD_SECTION_DIR=folder)
    posix = os.name != "nt"
    log = os.path.join(folder, "child-output.txt")
    with open(log, "w", encoding="utf-8") as out:
        child = subprocess.Popen([sys.executable, os.path.join(HERE, "test_guard.py")], env=env, stdout=out,
                                 stderr=subprocess.STDOUT, **({"start_new_session": True} if posix else {}))
        try:
            rc = child.wait(timeout=300)
        except subprocess.TimeoutExpired:
            rc = None
            child.kill()
        finally:
            if posix:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except OSError:
                    pass  # the group has already ended
    with open(log, encoding="utf-8", errors="replace") as f:
        return rc, f.read()


def section_refusal_check(build, want):
    """A check: the child run on the folder that `build` fills must stop nonzero, and its output must hold `want`."""
    def check():
        folder = tempfile.mkdtemp(dir=ROOT)
        build(folder)
        rc, out = section_child_run(folder)
        if rc is None:
            return False, "the run did not end within 300 s on a section set it must refuse"
        if rc == 0:
            return False, "the run passed with rc 0 on a section set it must refuse"
        if want not in out:
            return False, "the run stopped, but not on the refusal: %s" % ((out.strip().splitlines() or [""])[-1][:100])
        return True, "the run stops before any case, rc %d" % rc
    return check


def build_empty(folder):
    """A folder with no section file in it."""


def build_two_with_one_number(folder):
    """Every real section file, copied in, and one more file that claims the number of the first section."""
    # A copy, not a link: a symlink needs a privilege the Windows run does not hold.
    for name in os.listdir(SECTION_DIR):
        if name.endswith(".py"):
            shutil.copyfile(os.path.join(SECTION_DIR, name), os.path.join(folder, name))
    with open(os.path.join(folder, "s00442-second.py"), "w", encoding="utf-8") as f:
        f.write("# section 442\n")


def build_late_append(folder):
    """Every real section file, linked in, and one more that appends to LOG_CHECKS_EXTRA after the join."""
    for name in os.listdir(SECTION_DIR):
        if name.endswith(".py"):
            os.symlink(os.path.join(SECTION_DIR, name), os.path.join(folder, name))
    with open(os.path.join(folder, "s99999-late.py"), "w", encoding="utf-8") as f:
        f.write('# section 99999\nLOG_CHECKS_EXTRA.append(("sections: a late append", lambda: (True, "")))\n')


for _label, _check in (
        (EMPTY_SECTIONS_LABEL, section_refusal_check(build_empty, "no section file in")),
        (DUPLICATE_SECTIONS_LABEL, section_refusal_check(build_two_with_one_number,
                                                         "section number 442 is on 2 section files")),
):
    LOG_FAMILY[_label] = "sections"
    LOG_CHECKS = LOG_CHECKS + ((_label, _check),)
    FIXTURELESS_CHECKS.add(_check)
if os.name != "nt":
    _late_check = section_refusal_check(build_late_append, "were appended to LOG_CHECKS_EXTRA after its join")
    LOG_FAMILY[LATE_APPEND_LABEL] = "sections"
    LOG_CHECKS = LOG_CHECKS + ((LATE_APPEND_LABEL, _late_check),)
    FIXTURELESS_CHECKS.add(_late_check)
else:
    skip_case(LATE_APPEND_LABEL, NO_SYMLINK)

# The SKIP rows join last, so a skip_case anywhere above, the simulator one too, prints its row.
LOG_CHECKS = LOG_CHECKS + tuple(SKIP_ROWS)

# Log checks in the literal and the appended extras are tagged by section above. These prefixes give
# each one its rule's family instead, so GUARD_FAMILY=<rule> runs its log checks too. A prefix that
# matches no label, or more than one, stops the run: a typo must not leave a log check untagged.
LOG_RULE_FAMILY = (
    ("log: one line per refusal", "frozen"),
    ("log: the refused file is named", "frozen"),
    ("log: a project config edit", "frozen"),
    ("log: a cap lift is asked", "model-cap"),
    ("log: a cap lift under a deep path", "model-cap"),
    ("cap: the printed reason is bounded", "model-cap"),
    ("trim: a guard crash fails open", "paths"),
    ("merge-checks: a merge tool that cannot load", "merge"),
    ("merge-checks: a merge tool that exits at import", "merge"),
    ("merge-checks: a gh that never answers", "merge"),
    ("powershell: a backslash path survives", "paths"),
    ("wsl: a PowerShell script tag keeps its backslashes", "wsl"),
    ("wsl: a split segment keeps the PowerShell tag", "wsl"),
    ("log: an unreadable subject", "shared-tree"),
    ("log: a hard reset in an agent-owned", "shared-tree"),
    ("log: checkout -- in an agent-owned", "shared-tree"),
    ("log: an unforced worktree remove", "branch-worktree"),
    ("log: a forced worktree remove", "branch-worktree"),
    ("log: a quoted or abbreviated force", "branch-worktree"),
    ("per-file kill: log: a quoted or abbreviated force", "branch-worktree"),
    ("log: a branch delete with no resolvable base", "branch-worktree"),
    ("stack: the refusal never names", "shared-tree"),
    ("playwright: the refusal names the stale", "env"),
    ("split_segments: a comment starting a word", "paths"),
    ("liveness: process_start_ms splits", "kill"),
    ("liveness: windows arm splits", "kill"),
    ("liveness: session_is_live carries", "branch-worktree"),
    ("liveness: worktree_live_session answers None on an unreadable", "branch-worktree"),
    ("liveness: worktree_live_session matches two", "branch-worktree"),
    ("liveness: worktree_live_session answers None when", "branch-worktree"),
    ("liveness: session_is_live reads an implied", "branch-worktree"),
    ("liveness: process_start_ms reads a repeated-hour start (01:30 CDT)", "kill"),
    ("liveness: process_start_ms reads a repeated-hour start (01:30 CST)", "kill"),
    ("liveness: session_is_live says True for a repeated-hour start (01:30 CDT)", "branch-worktree"),
    ("liveness: session_is_live says True for a repeated-hour start (01:30 CST)", "branch-worktree"),
    ("worktree-home: orchestrator", "worktree-home"),
    ("worktree-home: any session's write into another checkout of its clone", "worktree-home"),
    ("worktree-home: any session's write into another checkout is refused after a cd", "worktree-home"),
    ("worktree-home: an absolute cd into another checkout is refused after an untracked move", "worktree-home"),
    ("worktree-home: pushd into another checkout", "worktree-home"),
    ("worktree-home: a write into a worktree in the session's own scratchpad", "worktree-home"),
    ("worktree-home: an owner override lifts the cross-checkout", "worktree-home"),
    ("worktree-home: the cross-checkout read costs", "worktree-home"),
    ("worktree-home: a cd into another checkout of the clone is refused", "worktree-home"),
    ("worktree-home: the other-checkout refusal names the EnterWorktree call", "worktree-home"),
    ("worktree-home: a cd into another checkout is refused when it is a relative climb", "worktree-home"),
    ("worktree-home: an agent's cd into a sibling agent tree", "worktree-home"),
    ("worktree-home: a cd to a checkout's own root", "worktree-home"),
    ("worktree-home: the cd exemptions pass", "worktree-home"),
    ("worktree-home: an agent's write into its own red-run folder", "worktree-home"),
    ("worktree-home: the own red-run folder's root", "worktree-home"),
    ("worktree-home: a red-run folder nested under another linked worktree", "worktree-home"),
    ("worktree-home: a write into the own red-run folder spelled", "worktree-home"),
    ("worktree-home: a cd in a comment, in quotes", "worktree-home"),
    ("worktree-home: an owner override lifts a bare cd", "worktree-home"),
    ("worktree-home: a later path field", "worktree-home"),
    ("worktree-home: a lone cd or Set-Location", "worktree-home"),
    ("worktree-home: a cd or Set-Location into the home chained", "worktree-home"),
    ("worktree-home: a /c/ cwd inside", "worktree-home"),
    ("worktree-home: a cd or Set-Location outside the home", "worktree-home"),
    ("worktree-home: a lone move with a separator", "worktree-home"),
    ("worktree-home: sl, chdir and set-location", "worktree-home"),
    ("worktree-home: the merge rule reads", "worktree-home"),
    ("worktree-home: the shared-tree rule reads", "worktree-home"),
    ("worktree-home: the builder test-edit rule reads", "worktree-home"),
    ("worktree-home: the frozen-path rule reads", "worktree-home"),
    ("worktree-home: the config-edit rule reads", "worktree-home"),
    ("worktree-home: the agent cap rule reads", "worktree-home"),
    ("worktree-home: a builder write to a test file from a /c/ cwd", "worktree-home"),
    ("worktree-home: a builder write to product code from a /c/ cwd", "worktree-home"),
    ("worktree-home: a builder write to a path in no repository from a /c/ cwd", "worktree-home"),
    ("cite-by-id: a -F file that cannot be read", "cite"),
    ("env: heredoc-allow-strip", "env"),
    ("roadmap-one-writer: a push starts one rev-parse", "push-delete"),
)
for _prefix, _family_name in LOG_RULE_FAMILY:
    _hits = [label for label in LOG_FAMILY if label.startswith(_prefix)]
    if len(_hits) != 1:
        sys.exit("fixture setup failed: log family prefix %r matches %d log checks, want 1"
                 % (_prefix, len(_hits)))
    LOG_FAMILY[_hits[0]] = _family_name

# A case or log check with a family that FAMILIES does not name would hide from GUARD_FAMILY.
_UNNAMED = sorted({c["family"] for c in CASES} - set(FAMILIES))
_BAD_LOG = [(label, LOG_FAMILY.get(label)) for label, _ in LOG_CHECKS
            if LOG_FAMILY.get(label) not in FAMILIES]
if _UNNAMED or _BAD_LOG:
    sys.exit("fixture setup failed: families not in FAMILIES: cases %s, log checks %s"
             % (_UNNAMED, _BAD_LOG))


# Debt: build-disk-guard (decision build-dirs-reaped-at-agent-end, Part 2), until a threshold is measured.


# A log check returns (SKIP, note) when it cannot run on this platform. run_cases prints a SKIP line for
# it and counts it in the summary. It is never printed as PASS, and it is never a failure.
SKIP = "skip"


def run_cases():
    mode = os.environ.get("GUARD_TESTS", "")
    if mode not in GUARD_TESTS_MODES:
        say("GUARD_TESTS=%r: want unset, 'windows-slice' or 'macos-slice'. Nothing ran." % mode)
        return 2
    problems = macos_arm_problems()
    if problems:
        for problem in problems:
            say("macos arm check FAIL: " + problem)
        return 1
    tag = SLICE_TAG.get(mode)
    fam = GUARD_FAMILY
    cases = [c for c in CASES if (not tag or c[tag]) and (not fam or c["family"] == fam)]
    logs = [(label, check) for label, check in LOG_CHECKS
            if (not mode or (tag == "windows" and check in WINDOWS_CHECKERS)
                or (tag == "macos" and check not in WINDOWS_CHECKERS
                    and macos_reached(LOG_FAMILY.get(label), None)))
            and (not fam or LOG_FAMILY.get(label) == fam)]
    total = len(cases) + len(logs)
    if mode and not total:
        say("GUARD_TESTS=%s: no case is tagged. Nothing ran." % mode)
        return 2
    # One list, so a shard takes its share of the log checks too, and the shards stay disjoint.
    picked = shard_of(cases + logs, GUARD_SHARD)
    cases = [c for c in picked if isinstance(c, dict)]
    logs = [c for c in picked if not isinstance(c, dict)]
    say("guard cases, %d in all" % (len(CASES) + len(LOG_CHECKS)))
    say("GUARD_TESTS=%s GUARD_FAMILY=%s: %d cases selected to run"
        % (mode or "(unset)", fam or "(unset)", total))
    say("GUARD_SHARD=%d/%d: %d of those cases run in this shard" % (GUARD_SHARD + (len(picked),)))
    say("fixtures under " + ROOT)
    say("")
    failed = 0
    ran = 0
    skipped = 0
    # MUTATE_ONLY: set by hooks/mutate_shared.py's first stage, run only the named cases.
    only = os.environ.get("MUTATE_ONLY")
    for case in cases:
        if only and only not in case["name"]:
            continue
        ran += 1
        beat("case %d of %d, before it runs" % (ran, len(cases)))
        got, reason = decide(case)
        beat("case %d of %d, after it ran" % (ran, len(cases)))
        ok = got == case["expected"]
        note = ""
        if ok and case.get("silent") and reason:
            ok = False
            note = "  (an allow that must be silent printed: %s)" % reason[:90]
        elif ok and case["rule"] and case["rule"] not in reason:
            ok = False
            note = "  (the reason does not name rule %r: %s)" % (case["rule"], reason[:90])
        elif ok and case["carries"] and [f for f in case["carries"] if not carried(f, reason)]:
            ok = False
            note = "  (the reason does not carry %r: %s)" % (
                [f for f in case["carries"] if not carried(f, reason)][0], reason[:90])
        elif ok and case["lacks"] and [f for f in case["lacks"] if f in reason]:
            ok = False
            note = "  (the reason carries %r, which it must not: %s)" % (
                [f for f in case["lacks"] if f in reason][0], reason[:90])
        elif ok and got != "allow" and names_the_target(reason, case["rule"]):
            ok = False
            note = "  (the reason names the forbidden target %r)" % names_the_target(
                reason, case["rule"])
        elif not ok:
            note = "  (%s)" % reason[:110] if reason else ""
        failed += 0 if ok else 1
        say("%s  %-6s(want %-6s)  [%-11s] %s%s" % (
            "PASS" if ok else "FAIL", got, case["expected"], case["tool"], case["name"], note))
    if any((not only or only in label) and check not in FIXTURELESS_CHECKS for label, check in logs):
        materialize_all()  # a log check names its fixtures in its own code, not in a case's fields
    for label, checker in logs:
        if only and only not in label:
            continue
        beat("log check, before it runs")
        ok, note = checker()
        beat("log check, after it ran")
        if ok == SKIP:  # cannot run on this platform: shown and counted, never a PASS, never a failure
            skipped += 1
            say("SKIP  %s  (%s)" % (label, note))
            continue
        ran += 1
        failed += 0 if ok else 1
        say("%s  %-6s(want %-6s)  [%-11s] %s  (%s)" % (
            "PASS" if ok else "FAIL", "logged" if ok else "wrong", "logged", "Bash", label, note))
    say("")
    shutil.rmtree(ROOT, ignore_errors=True)
    OWNED.kill()
    for orphan in ORPHAN_PIDS:   # the sleeps this file started, by their own pids
        try:
            os.kill(orphan, signal.SIGTERM)
        except OSError:
            pass
    if (mode or fam or only or GUARD_SHARD != (1, 1)) and not ran:
        say("test_guard FAIL: ran 0 cases (GUARD_TESTS=%s, GUARD_FAMILY=%s, MUTATE_ONLY=%s, "
            "GUARD_SHARD=%d/%d matched none, or matched only skips: %d skipped)" % (
                mode or "(unset)", fam or "(unset)", only or "(unset)", GUARD_SHARD[0], GUARD_SHARD[1],
                skipped))
        return 1
    if failed:
        say("test_guard FAIL: %d of %d cases wrong, %d skipped" % (failed, ran, skipped))
        return 1
    say("test_guard PASS: %d of %d cases right, %d skipped" % (ran, ran, skipped))
    return 0


def main():
    _mark("case registration (module code after the fixtures)")
    rc = run_cases()
    _timing_report()
    return rc


if __name__ == "__main__":
    sys.exit(main())
