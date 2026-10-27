#!/usr/bin/env python3
"""Cases for hooks/config_watch.py. Standard library only, and no test runner.

Run it from the repository root:

    python hooks/test_config_watch.py

EVERY CASE IS AN ACT, NEVER A STRING. Each case builds a real project directory, runs a real shell
command or a real tool payload that writes the cap into `.claude/settings.local.json`, then runs
the PreToolUse guard and the PostToolUse watch exactly as Claude Code runs them, and reads the FILE
back. A case that only asked the guard what it thought would prove nothing about `cp`, because the
whole point of `cp` is that the guard cannot see what it carries.
"""

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "guard.py")


def _find_git_bash():
    """Resolve the real Git-for-Windows bash by full path. Never hand subprocess a bare "bash".

    Both this machine and the CI runner list `C:\\Windows\\System32` ahead of Git's
    own `bin` folder on PATH. `System32\\bash.exe` is a WSL launcher stub, not Git
    Bash. It mounts drives at "/mnt/c", never at "/c". `to_bash_path` below builds
    the "/c" form. A path handed to that stub never resolves. `shutil.which("bash")`
    does not help. It is a plain PATH scan. On this PATH order it returns the same
    stub.

    A bare "bash" prints "/mnt/c/Users/..." (the WSL stub). The full path to
    Git's own bash.exe prints "C:/Users/..." (the real MINGW64 mount). The
    `shell: bash` steps of `.github\\workflows\\gates.yml` already use that path.
    """
    if os.name != "nt":
        return shutil.which("bash") or "bash"
    for var in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        base = os.environ.get(var)
        if base:
            candidate = os.path.join(base, "Git", "bin", "bash.exe")
            if os.path.isfile(candidate):
                return candidate
    # Fall back to a PATH scan that skips the System32 stub, in case Git sits
    # somewhere else. Whatever PATH still finds beats a bare "bash".
    system_root = os.path.normcase(os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"), "System32"))
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        if os.path.normcase(folder).startswith(system_root):
            continue
        candidate = os.path.join(folder, "bash.exe")
        if os.path.isfile(candidate):
            return candidate
    return shutil.which("bash") or "bash"


BASH = _find_git_bash()

# FIXTURE_TMP is where the indirection fixtures below live: `tempfile.gettempdir()`, never a
# literal "/tmp". On Windows, Python resolves "/tmp" to "C:\tmp". Bash (MSYS) resolves the
# same literal to a different directory instead, such as "C:\Users\x\AppData\Local\Temp".
# A fixture Python writes at the literal path then never lands where the command under
# test, run through bash, reads it. `gettempdir()` gives Python's own real answer.
# `to_bash_path` below converts that answer to the POSIX form bash needs, wherever a
# command string names it.
FIXTURE_TMP = os.path.join(tempfile.gettempdir(), "config_watch_fixtures")


def to_bash_path(path):
    """Convert a native path to the POSIX/MSYS form bash expects inside a command string.

    On POSIX, a path is already in that form, so this is a no-op. On Windows, bash
    (MSYS/Git Bash) never resolves a drive-letter path like "C:\\Users\\x\\y". It wants
    "/c/Users/x/y" instead. Only a path PASSED INTO a bash command or script needs this.
    A path Python itself opens (json.load, open()) must stay in its native form.
    """
    if os.name != "nt":
        return path
    drive, rest = os.path.splitdrive(path)
    if not drive:
        return path.replace("\\", "/")
    return "/" + drive[0].lower() + rest.replace("\\", "/")


def to_python_literal_path(path):
    """Convert a native path for a Python literal a bash string carries first.

    The "python3 -c writes the path" case builds a Python `open(...)` call. It then
    embeds that call inside a bash double-quoted string. A native Windows path there
    crosses two escapers in a row.

    Bash's own double-quote rule turns `\\\\` into one `\\`. The surviving single
    backslash then starts a Python string escape, such as `\\U`. `\\U` demands eight
    hex digits next. "Users" fails that check. The inner python3 then raised a
    SyntaxError and wrote nothing, so the case tested a fixture that never ran.

    `to_bash_path`'s MSYS form, "/c/Users/...", fixes the bash side. The inner
    python3 is native Windows Python. It has no "/c" drive. Forward slashes are the
    one form both readers accept. Bash passes a plain `/` through untouched. Windows
    Python opens a drive-letter path with forward slashes the same as with
    backslashes. On POSIX this is already a no-op.
    """
    return path.replace("\\", "/")


# WATCH_UNDER_TEST points the suite at another copy of the watch, such as a copy carrying one
# mutation, the same contract GUARD_UNDER_TEST holds for the guard. A mutation test then needs no
# second copy of this file, so the cases cannot drift from the cases that pass.
WATCH = os.environ.get("WATCH_UNDER_TEST") or os.path.join(HERE, "config_watch.py")

# Assembled from parts, so this file never holds the cap variable whole and cannot trip the guard
# that reads it.
KEY = "CLAUDE_CODE_" + "SUBAGENT_MODEL"
KEY_FORCE = KEY + "_FORCE"
EXPIRY_FIELD = "_agentCapUntil"


def _iso(hours_from_now: float) -> str:
    when = datetime.now(timezone.utc) + timedelta(hours=hours_from_now)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


VALID_UNTIL = _iso(1)     # one hour ahead: current
PASSED_UNTIL = _iso(-1)   # one hour ago: expired
TOO_FAR_UNTIL = _iso(48)  # two days ahead: over the 24-hour ceiling

# TEST_CLOCK_ENV must match `config_watch.TEST_CLOCK_ENV`. It is the only way a fixture can put
# `_agentCapUntil` EXACTLY on the 24-hour boundary: `datetime.now()` called once to build the
# fixture and once more, later, inside `expiry_problem`, are never the same instant on their own,
# so the watch under test must read a clock the fixture also controls.
TEST_CLOCK_ENV = "CONFIG_WATCH_TEST_CLOCK"

# One fixed instant, seconds only (no microseconds, so formatting and re-parsing round-trips
# exactly), that every boundary case below both builds its `_agentCapUntil` from and pins as
# the watch's own clock. Same reference on both sides: the boundary is exact, not approximate.
REFERENCE_NOW = datetime.now(timezone.utc).replace(microsecond=0)


def _fmt(when: datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


CLOCK_AT_REFERENCE = _fmt(REFERENCE_NOW)
BOUNDARY_24H_UNTIL = _fmt(REFERENCE_NOW + timedelta(hours=24))           # ahead == 86400s: accepted
BOUNDARY_INSIDE_UNTIL = _fmt(REFERENCE_NOW + timedelta(seconds=86399))   # ahead == 86399s: accepted
BOUNDARY_OUTSIDE_UNTIL = _fmt(REFERENCE_NOW + timedelta(seconds=86401))  # ahead == 86401s: revoked
BOUNDARY_AT_DEADLINE_UNTIL = _fmt(REFERENCE_NOW)                         # ahead == 0s: accepted
BOUNDARY_PAST_UNTIL = _fmt(REFERENCE_NOW - timedelta(seconds=1))         # ahead == -1s: revoked


def cap_json(model=None, force=None, until=None, extra=None):
    """Build one settings.local.json body. `until`, when given, sits OUTSIDE `env` on purpose:
    that is the whole point of the field under test."""
    body = {}
    env = {}
    if model is not None:
        env[KEY] = model
    if force is not None:
        env[KEY_FORCE] = force
    if env:
        body["env"] = env
    if until is not None:
        body[EXPIRY_FIELD] = until
    if extra:
        body.update(extra)
    return json.dumps(body)


def cap_json_until_in_env(model, force, until):
    """Build one settings.local.json body with `_agentCapUntil` mis-typed INSIDE `env`.

    The mistake this tests: an owner reaching for `_agentCapUntil` types it next to the
    keys it is meant to bound. The message must say where it belongs, not read it as absent.
    """
    return json.dumps({"env": {KEY: model, KEY_FORCE: force, EXPIRY_FIELD: until}})


# LIFT carries a valid, current expiry: a lift with none is what the "bad expiry" cases below
# test. The bypass cases reuse LIFT and are reverted for being UNASKED, a check that runs
# before the expiry rule.
LIFT = cap_json(model="opus", force="1", until=VALID_UNTIL)
SONNET = json.dumps({"env": {KEY: "sonnet", KEY_FORCE: "1"}})
UNRELATED = json.dumps({"env": {KEY: "sonnet", KEY_FORCE: "1"}, "theme": "light"})

CASES = []


def case(name, group, **kw):
    def register(fn):
        CASES.append(dict(name=name, group=group, run=fn, **kw))
        return fn
    return register


# --------------------------------------------------------------------------- the fixture


class Project(object):
    """One temporary project with its own config directory, so no case reaches the real one."""

    def __init__(self, root, start=None):
        self.root = root
        self.cfg = os.path.join(root, "cfg")
        self.proj = os.path.join(root, "proj")
        self.dot = os.path.join(self.proj, ".claude")
        self.settings = os.path.join(self.dot, "settings.local.json")
        self.other = os.path.join(self.proj, "notes.txt")
        os.makedirs(self.dot)
        os.makedirs(self.cfg)
        if start is not None:
            write(self.settings, start)
        write(self.other, "untouched\n")

    def env(self):
        env = dict(os.environ)
        env["CLAUDE_CONFIG_DIR"] = self.cfg
        # The watch under test imports the REAL guard. A mutation of the watch must be killed by
        # the watch's own cases, never by a guard that moved with it.
        env.pop("GUARD_UNDER_TEST", None)
        return env

    def payload(self, tool, tool_input):
        return {"tool_name": tool, "tool_input": tool_input, "cwd": self.proj,
                "session_id": "case"}

    def content(self):
        try:
            with open(self.settings, "r", encoding="utf-8") as handle:
                return handle.read()
        except Exception:
            return None

    def lifted(self) -> bool:
        """True when the file on disk now carries a model above the cap."""
        text = self.content()
        return bool(text) and "opus" in text

    def pre(self, tool, tool_input) -> str:
        """Run the PreToolUse guard and return its decision: allow, ask or deny."""
        out = run(GUARD, self.payload(tool, tool_input), self.env())
        if not out.strip():
            return "allow"
        try:
            return json.loads(out)["hookSpecificOutput"]["permissionDecision"]
        except Exception:
            return "allow"

    def post(self, tool, tool_input, clock=None) -> str:
        """Run the PostToolUse watch and return its systemMessage, or ''.

        `clock`, an ISO-8601 string, pins the expiry rule's "now" through `TEST_CLOCK_ENV`. It
        is unset in every case that does not name it, so those cases read the real clock, the
        same as production.
        """
        env = self.env()
        if clock is not None:
            env[TEST_CLOCK_ENV] = clock
        out = run(WATCH, self.payload(tool, tool_input), env)
        if not out.strip():
            return ""
        try:
            return json.loads(out).get("systemMessage", "")
        except Exception:
            return ""

    def settle(self, tool="", tool_input=None):
        """Record the baseline for the file as it stands, as a turn with no cap change would."""
        self.post(tool, tool_input or {})

    def stop(self) -> str:
        """Run the watch at turn end, with no tool call to explain anything."""
        return self.post("", {})


def write(path, text):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def run(script, payload, env) -> str:
    done = subprocess.run([sys.executable, script], input=json.dumps(payload),
                          capture_output=True, text=True, env=env)
    return done.stdout


def shell(project, command):
    """Run one shell command inside the project, as the Bash tool would."""
    subprocess.run([BASH, "-c", command], cwd=project.proj, capture_output=True, text=True)


# --------------------------------------------------------------------------- the bypass shapes
#
# One case per row of the bypass table. Each one WRITES the cap lift for real and then reads the
# file back. The five rows the guard ALLOWS lift the cap, and the watch must undo them.


def bypass(name, build):
    """Register one shell bypass: the guard is asked, the command runs, the watch judges."""
    @case(name, "bypass")
    def run_case(project):
        project.settle()
        command = build(project)
        decision = project.pre("Bash", {"command": command})
        shell(project, command)
        message = project.post("Bash", {"command": command})
        return {"pre": decision, "lifted": project.lifted(), "message": message}
    return run_case


# THE SOURCE FILE IS PREPARED OUT OF BAND, by `main` before the case runs. Building it inside the
# measured command would put the cap value ON the command line, and rule 8 reads the whole line, so
# the case would measure the heredoc shape under a `cp` name and report a pass that is not there.
bypass("cp from another file",
       lambda p: "cp %s .claude/settings.local.json"
                 % to_bash_path(os.path.join(FIXTURE_TMP, "lift_case.json")))
bypass("mv from another file",
       lambda p: "mv %s .claude/settings.local.json"
                 % to_bash_path(os.path.join(FIXTURE_TMP, "lift_case2.json")))
bypass("sed -i in place",
       # `sed -i ''` is BSD syntax: GNU sed's `-i` takes its suffix only ATTACHED, so a
       # SEPARATE `''` is read as the script and `s/sonnet/opus/` as a missing filename (an
       # error, not a write); the target is edited with an EMPTY script and no byte changes.
       # `-i.bak` attaches a REAL suffix, which BSD and GNU parse the same way, so this edits in
       # place identically on both.
       lambda p: "sed -i.bak -e s/sonnet/opus/ .claude/settings.local.json "
                 "&& rm -f .claude/settings.local.json.bak")
bypass("python3 -c writes the path",
       lambda p: "python3 -c \"open('.claude/settings.local.json','w')"
                 ".write(open(%r).read())\"" % to_python_literal_path(
                     os.path.join(FIXTURE_TMP, "lift_case3.json")))
bypass("python3 runs a script file",
       lambda p: "python3 gen.py")
bypass("bash runs a script file",
       lambda p: "bash gen.sh")

# The two indirection shapes the table above does not cover. Neither names the path in the
# command, so no shell reading can reach them, and both must be caught by the hash.
bypass("a path held in a shell variable",
       lambda p: "f=.claude/settings.local.json; cp %s \"$f\""
                 % to_bash_path(os.path.join(FIXTURE_TMP, "lift_case4.json")))
bypass("a script file that never names the path in the command",
       lambda p: "sh write.sh")



# --------------------------------------------------------------------------- the green cases


@case("an approved Write passes through and is NOT reverted", "pass")
def approved_write(project):
    project.settle()
    decision = project.pre("Write", {"file_path": project.settings, "content": LIFT})
    write(project.settings, LIFT)
    message = project.post("Write", {"file_path": project.settings, "content": LIFT})
    return {"pre": decision, "lifted": project.lifted(), "message": message}


@case("an approved heredoc passes through and is NOT reverted", "pass")
def approved_heredoc(project):
    project.settle()
    command = ("cat > .claude/settings.local.json <<'JSON'\n" + LIFT + "\nJSON\n")
    decision = project.pre("Bash", {"command": command})
    shell(project, command)
    message = project.post("Bash", {"command": command})
    return {"pre": decision, "lifted": project.lifted(), "message": message}


@case("a write to an unrelated file triggers nothing", "pass")
def unrelated_file(project):
    project.settle()
    command = "echo changed > notes.txt"
    decision = project.pre("Bash", {"command": command})
    shell(project, command)
    message = project.post("Bash", {"command": command})
    return {"pre": decision, "lifted": project.lifted(), "message": message,
            "settings": project.content()}


@case("an ordinary project config edit is allowed and not reverted", "pass")
def ordinary_edit(project):
    project.settle()
    command = "cp %s .claude/settings.local.json" % to_bash_path(
        os.path.join(FIXTURE_TMP, "lift_case5.json"))
    decision = project.pre("Bash", {"command": command})
    shell(project, command)
    message = project.post("Bash", {"command": command})
    return {"pre": decision, "lifted": project.lifted(), "message": message,
            "settings": project.content()}


@case("a failed write is caught at turn end", "stop")
def stop_backstop(project):
    project.settle()
    # No PostToolUse fires for a FAILED tool call, so the watch never sees the write. The Stop
    # sweep is what closes that safety hole.
    shell(project, "cp %s .claude/settings.local.json" % to_bash_path(
        os.path.join(FIXTURE_TMP, "lift_case6.json")))
    message = project.stop()
    return {"pre": "n/a", "lifted": project.lifted(), "message": message}


# ------------------------------------------------------------------ absent, never merely empty
#
# `digest()`'s docstring draws a line between a file that is ABSENT and one that is merely
# EMPTY: "a cap lift that CREATES settings.local.json must read as a change and its restore must
# remove the file again." Every other case above starts from `start=SONNET` and never deletes the
# file, so a `digest()` that hashed an absent file the same as an empty one would pass them all.
#
# ONE MORE STEP THAN IT LOOKS LIKE IT NEEDS, and each one is load-bearing. `load_baseline`
# recomputes `"digest": ""` by hand whenever a stored baseline's content is `None` (a genuinely
# absent file), rather than trusting the stored digest. So a baseline that goes straight from
# "no baseline yet" to "absent" never asks `digest(None)` an interesting question. The defect only
# shows through a baseline that starts REAL AND EMPTY (`digest()` is trusted and verified there),
# and is THEN deleted by an ordinary, non-cap event. A `digest()` confusing absent with empty
# makes that deletion invisible to the watch's own baseline, so a later cap lift reverts to an
# EMPTY file instead of removing it -- the file's true last-known-good state.


@case("a file goes from empty to absent before a lift, so the revert removes it, not empties it",
      "absent")
def empty_then_absent(project):
    # This one case starts from a real, empty file, though `main` below hands every case one that
    # already carries SONNET.
    write(project.settings, "")
    project.settle()
    # It disappears through no cap-bearing call at all -- an ordinary event, and the watch must
    # fold it into its own baseline exactly as Decision 7 asks of any project edit.
    os.remove(project.settings)
    project.settle()
    command = "cp %s .claude/settings.local.json" % to_bash_path(
        os.path.join(FIXTURE_TMP, "lift_case.json"))
    decision = project.pre("Bash", {"command": command})
    shell(project, command)
    message = project.post("Bash", {"command": command})
    return {"pre": decision, "lifted": project.lifted(), "message": message,
            "settings": project.content()}


# --------------------------------------------------------------------------- the expiry
#
# `_agentCapUntil` only matters once a lift is APPROVED: an unasked write is reverted for being
# unasked, before the expiry rule ever runs. So every case here goes through the approved-Write
# path, the same shape `approved_write` above uses, and differs only in what `_agentCapUntil`
# says.


def approved_case(name, content, kind, clock=None):
    @case(name, "expiry", kind=kind)
    def run_case(project):
        project.settle()
        decision = project.pre("Write", {"file_path": project.settings, "content": content})
        write(project.settings, content)
        message = project.post(
            "Write", {"file_path": project.settings, "content": content}, clock)
        return {"pre": decision, "lifted": project.lifted(), "message": message}
    return run_case


def chain_case(name):
    """Two approved lifts in a row, then a third write that is not: `next_prior` must carry
    the ORIGINAL pre-lift content forward through the second lift, never the first lift's own
    lifted bytes, or the eventual revert restores an override instead of the true baseline."""
    @case(name, "expiry", kind="bad")
    def run_case(project):
        project.settle()  # baseline: SONNET
        first = cap_json(model="opus", force="1", until=VALID_UNTIL)
        project.pre("Write", {"file_path": project.settings, "content": first})
        write(project.settings, first)
        project.post("Write", {"file_path": project.settings, "content": first})

        second = cap_json(model="opus", force="1", until=_iso(2))
        project.pre("Write", {"file_path": project.settings, "content": second})
        write(project.settings, second)
        project.post("Write", {"file_path": project.settings, "content": second})

        bad = cap_json(model="opus", force="1")  # missing expiry: must be reverted
        decision = project.pre("Write", {"file_path": project.settings, "content": bad})
        write(project.settings, bad)
        message = project.post("Write", {"file_path": project.settings, "content": bad})
        return {"pre": decision, "lifted": project.lifted(), "message": message}
    return run_case


approved_case("an approved lift with a missing _agentCapUntil is revoked",
              cap_json(model="opus", force="1"), "bad")
approved_case("an approved lift with an unparseable _agentCapUntil is revoked",
              cap_json(model="opus", force="1", until="not-a-time"), "bad")
approved_case("an approved lift with _agentCapUntil more than 24h ahead is revoked",
              cap_json(model="opus", force="1", until=TOO_FAR_UNTIL), "bad")
approved_case("an approved lift with _agentCapUntil already passed is revoked",
              cap_json(model="opus", force="1", until=PASSED_UNTIL), "bad")
approved_case("an approved lift with a valid, current _agentCapUntil is NOT reverted, "
              "and stays silent", cap_json(model="opus", force="1", until=VALID_UNTIL), "valid")
approved_case("a file with no lift above Sonnet and a stray _agentCapUntil does nothing",
              cap_json(model="sonnet", force="1", until=VALID_UNTIL), "nocap")
approved_case("an approved lift with _agentCapUntil misplaced inside env is revoked, "
              "and says where it belongs",
              cap_json_until_in_env("opus", "1", VALID_UNTIL), "wrong_place")
# The field's old name is read until its end day, so a deadline written before the rename counts.
approved_case("an approved lift with a valid, current _subagentCapUntil (the old name) is NOT "
              "reverted", cap_json(model="opus", force="1", extra={"_subagentCapUntil": VALID_UNTIL}),
              "valid")

chain_case("a second approved lift keeps the ORIGINAL pre-lift content as prior, so a later "
           "revert never installs the first lift's own content")

# The 24-hour boundary, pinned exactly with TEST_CLOCK_ENV (see REFERENCE_NOW above). The code
# accepts a deadline AT the ceiling and AT the deadline instant itself: both `ahead > 24h` and
# `ahead < 0` are strict, so `ahead == 86400` and `ahead == 0` both read as "no problem".
approved_case("an approved lift with _agentCapUntil exactly 24 hours ahead is accepted "
              "(the ceiling is inclusive)",
              cap_json(model="opus", force="1", until=BOUNDARY_24H_UNTIL), "valid",
              clock=CLOCK_AT_REFERENCE)
approved_case("an approved lift with _agentCapUntil one second inside the 24h bound is "
              "accepted",
              cap_json(model="opus", force="1", until=BOUNDARY_INSIDE_UNTIL), "valid",
              clock=CLOCK_AT_REFERENCE)
approved_case("an approved lift with _agentCapUntil one second outside the 24h bound is "
              "revoked",
              cap_json(model="opus", force="1", until=BOUNDARY_OUTSIDE_UNTIL), "bad",
              clock=CLOCK_AT_REFERENCE)
approved_case("an approved lift with _agentCapUntil exactly at the deadline instant is "
              "accepted (not yet passed)",
              cap_json(model="opus", force="1", until=BOUNDARY_AT_DEADLINE_UNTIL), "valid",
              clock=CLOCK_AT_REFERENCE)
approved_case("an approved lift with _agentCapUntil one second past the deadline is revoked",
              cap_json(model="opus", force="1", until=BOUNDARY_PAST_UNTIL), "bad",
              clock=CLOCK_AT_REFERENCE)


# --------------------------------------------------------------------------- the old shape


@case("a baseline entry in the old on-disk shape (no 'prior' key) still works", "compat")
def old_shape_baseline(project):
    # Seed the store with a baseline entry that has no "prior" key. load_baseline must read it
    # without crashing, and the unasked lift below must still be caught and reverted from it.
    store_dir = os.path.join(project.cfg, "state", "config-watch")
    os.makedirs(store_dir, exist_ok=True)
    content = SONNET.encode("utf-8")
    key = hashlib.sha256(project.settings.encode("utf-8", "replace")).hexdigest() + ".json"
    entry = {
        "path": project.settings,
        "digest": hashlib.sha256(content).hexdigest(),
        "content": base64.b64encode(content).decode("ascii"),
    }
    with open(os.path.join(store_dir, key), "w", encoding="utf-8") as handle:
        json.dump(entry, handle)
    command = "cp %s .claude/settings.local.json" % to_bash_path(
        os.path.join(FIXTURE_TMP, "lift_case.json"))
    decision = project.pre("Bash", {"command": command})
    shell(project, command)
    message = project.post("Bash", {"command": command})
    return {"pre": decision, "lifted": project.lifted(), "message": message}


# --------------------------------------------------------------------------- the run

def expectation(entry, result):
    """Return (ok, note) for one finished case."""
    group = entry["group"]
    lifted = result["lifted"]
    message = result["message"]
    if group in ("bypass", "stop"):
        if lifted:
            return (False, "cap STILL LIFTED: the watch missed it")
        if not message:
            return (False, "reverted but said nothing")
        return (True, "reverted and reported")
    if entry["name"].startswith("a write to an unrelated file"):
        return ((not lifted) and not message and result["settings"] == SONNET,
                "untouched and silent" if not message else "spoke about an unrelated file")
    if entry["name"].startswith("an ordinary project config edit"):
        return ((not lifted) and not message and result["settings"] == UNRELATED,
                "kept and silent" if not message else "reverted an ordinary edit")
    if group == "expiry":
        kind = entry["kind"]
        if kind == "bad":
            if lifted:
                return (False, "cap STILL LIFTED past a bad deadline: the expiry rule missed it")
            if not message:
                return (False, "reverted but said nothing")
            return (True, "reverted for a bad expiry, and reported")
        if kind == "valid":
            return (lifted and not message,
                    "stayed lifted and silent, as a valid deadline should" if lifted and not
                    message else "a valid, current deadline was mishandled")
        if kind == "nocap":
            return ((not lifted) and not message,
                    "untouched and silent" if (not lifted and not message)
                    else "a stray field with no lift above Sonnet should never speak")
        if kind == "wrong_place":
            if lifted:
                return (False, "cap STILL LIFTED with a misplaced expiry: the watch missed it")
            if "env" not in message:
                return (False, "reverted, but the message never says the field is in env: "
                        "it reads as plain 'missing' instead -- got: %r" % message)
            return (True, "reverted, and the message names the env block")
    if group == "compat":
        if lifted:
            return (False, "cap STILL LIFTED: the watch missed it")
        if not message:
            return (False, "reverted but said nothing")
        return (True, "reverted and reported, even from an old-shape baseline entry")
    if group == "absent":
        if lifted:
            return (False, "cap STILL LIFTED: the watch missed it")
        if not message:
            return (False, "reverted but said nothing")
        settings = result["settings"]
        if settings == "":
            return (False, "reverted to EMPTY: the file's last known-good state was absent")
        if settings is not None:
            return (False, "reverted but did not land on absent")
        return (True, "reverted to its own last known-good state, absent, not merely empty")
    return (lifted and not message,
            "passed through untouched" if lifted else "an APPROVED write was reverted")


# --------------------------------------------------------------------------- the session column
#
# A revert writes one guard.log line through guard.record. Its last field must be the hook's
# session_id, and "-" when the hook sends none. The check runs IN THIS PROCESS through sweep, so a
# test can patch guard_core.set_log_session. A patch to a no-op is the mutant of deleting the call in
# config_watch.sweep: the watch then never sets the session, and the placeholder stays.

SWEEP_SESSION = "sess-config-watch-0001"
SWEEP_ABSENT = object()  # the hook sends no session_id key


def _load_watch():
    import importlib.util
    spec = importlib.util.spec_from_file_location("config_watch_sweep_under_test", WATCH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _unexplained_revert(session):
    """Run one cap lift through sweep, in this process. The lift arrives as a Bash call the guard
    cannot read, so the watch reverts it and writes one `reverted` line. Return the guard.log lines
    of that folder, split on tabs, and sweep's messages. The module's session is reset to the
    placeholder directly, not through set_log_session, so a watch that never sets it leaves '-'.
    """
    watch = _load_watch()
    core = sys.modules["guard_core"]  # the module the writer reads its session from
    core._log_session = "-"
    root = tempfile.mkdtemp(prefix="config_watch_sweep_")
    saved = os.environ.get("CLAUDE_CONFIG_DIR")
    try:
        proj = os.path.join(root, "proj")
        cfg = os.path.join(root, "cfg")
        settings = os.path.join(proj, ".claude", "settings.local.json")
        write(settings, SONNET)  # the baseline: the file as it stands
        os.environ["CLAUDE_CONFIG_DIR"] = cfg
        payload = {"tool_name": "Bash", "tool_input": {"command": "true"}, "cwd": proj}
        if session is not SWEEP_ABSENT:
            payload["session_id"] = session
        watch.sweep(dict(payload))
        write(settings, LIFT)  # a lift the guard never explained
        messages = watch.sweep(dict(payload))
        path = os.path.join(cfg, "guard.log")
        if not os.path.exists(path):
            return [], messages
        with open(path, encoding="utf-8") as handle:
            rows = [line.split("\t") for line in handle.read().splitlines() if line.strip()]
        return rows, messages
    finally:
        if saved is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = saved
        shutil.rmtree(root, ignore_errors=True)


def _reverted_rows(rows):
    return [fields for fields in rows if len(fields) > 2 and fields[2] == "reverted"]


def sweep_session_check():
    """config_watch names the session in its revert line: the last field is the hook's session_id,
    and '-' when the hook sends none. Returns (ok, note).
    """
    rows, messages = _unexplained_revert(SWEEP_SESSION)
    if not messages:
        return False, "the watch judged nothing: the lift was not reverted"
    reverted = _reverted_rows(rows)
    if len(reverted) != 1:
        return False, "expected one reverted line, found %d" % len(reverted)
    if len(reverted[0]) != 6 or reverted[0][5] != SWEEP_SESSION:
        return False, "the revert line ends in %r, want the hook's session_id" % (
            reverted[0][-1])
    rows, messages = _unexplained_revert(SWEEP_ABSENT)
    reverted = _reverted_rows(rows)
    if len(reverted) != 1 or len(reverted[0]) != 6 or reverted[0][5] != "-":
        return False, "with no session_id the revert line must end in '-', got %r" % (
            reverted[0][-1] if reverted else rows)
    return True, "the revert line ends in the session_id, and in '-' with none"


def main() -> int:
    print("config_watch cases, %d in all" % len(CASES))
    print()
    failed = 0
    only = os.environ.get("MUTATE_ONLY")  # first stage of hooks/mutate_shared.py: named cases only
    for entry in CASES:
        if only and only not in entry["name"]:
            continue
        root = tempfile.mkdtemp(prefix="config_watch_")
        try:
            # The files the indirection cases read. They sit OUTSIDE the project and outside the
            # measured command, which is the whole point: the cap value must never reach the
            # command line, or the case measures a shape the guard already reads. They are rebuilt
            # for each case because `mv` consumes its source.
            for name in ("lift_case.json", "lift_case2.json", "lift_case3.json",
                         "lift_case4.json", "lift_case6.json"):
                write(os.path.join(FIXTURE_TMP, name), LIFT)
            write(os.path.join(FIXTURE_TMP, "lift_case5.json"), UNRELATED)
            project = Project(root, start=SONNET)
            # gen.py is run as `python3 gen.py`: the path inside it is read by PYTHON's own
            # open(), so it stays in native form, never bash-converted.
            write(os.path.join(project.proj, "gen.py"),
                  "open('.claude/settings.local.json','w').write(open(%r).read())\n"
                  % os.path.join(FIXTURE_TMP, "lift_case.json"))
            # gen.sh and write.sh are run as `bash gen.sh` / `sh write.sh`: the path inside them
            # is read by BASH, so it must be in POSIX/MSYS form.
            write(os.path.join(project.proj, "gen.sh"),
                  "cp %s .claude/settings.local.json\n"
                  % to_bash_path(os.path.join(FIXTURE_TMP, "lift_case.json")))
            write(os.path.join(project.proj, "write.sh"),
                  "t=.claude/settings.local.json\ncp %s \"$t\"\n"
                  % to_bash_path(os.path.join(FIXTURE_TMP, "lift_case.json")))
            result = entry["run"](project)
            ok, note = expectation(entry, result)
        finally:
            shutil.rmtree(root, ignore_errors=True)
        failed += 0 if ok else 1
        print("%s  %-9s pre=%-5s  %s  (%s)" % (
            "PASS" if ok else "FAIL", "[" + entry["group"] + "]",
            result["pre"], entry["name"], note))
    if not only:
        sweep_ok, sweep_note = sweep_session_check()
        failed += 0 if sweep_ok else 1
        print("%s  [sweep]  config_watch names the session in its revert line  (%s)" % (
            "PASS" if sweep_ok else "FAIL", sweep_note))
    print()
    if failed:
        print("test_config_watch FAIL: %d of %d cases wrong" % (failed, len(CASES)))
        return 1
    print("test_config_watch PASS: %d of %d cases right" % (len(CASES), len(CASES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
