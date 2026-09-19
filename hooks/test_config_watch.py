#!/usr/bin/env python3
"""Cases for hooks/config_watch.py. Standard library only, and no test runner.

Run it from the repository root:

    python hooks/test_config_watch.py

EVERY CASE IS AN ACT, NEVER A STRING. Each case builds a real project directory, runs a real shell
command or a real tool payload that writes the cap into `.claude/settings.local.json`, then runs
the PreToolUse guard and the PostToolUse watch exactly as Claude Code runs them, and reads the FILE
back. A case that only asked the guard what it thought would prove nothing about `cp`, because the
whole point of `cp` is that the guard cannot see what it carries.

THE GUARD MUST GO RED BEFORE IT GOES GREEN. `--baseline` runs every case with the watch turned off,
which is the state of `main`. The shapes the design brief measured as ALLOWED must all report a
LIFTED cap there. Without that number the green run proves nothing.

    python hooks/test_config_watch.py --baseline    # main: the bypasses land
    python hooks/test_config_watch.py               # here: the bypasses are undone
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "guard.py")
# WATCH_UNDER_TEST points the suite at another copy of the watch, such as a copy carrying one
# mutation, the same contract GUARD_UNDER_TEST holds for the guard. A mutation test then needs no
# second copy of this file, so the cases cannot drift from the cases that pass.
WATCH = os.environ.get("WATCH_UNDER_TEST") or os.path.join(HERE, "config_watch.py")

# Assembled from parts, so this file never holds the cap variable whole and cannot trip the guard
# that reads it.
KEY = "CLAUDE_CODE_" + "SUBAGENT_MODEL"
KEY_FORCE = KEY + "_FORCE"
LIFT = json.dumps({"env": {KEY: "opus", KEY_FORCE: "1"}})
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

    def post(self, tool, tool_input) -> str:
        """Run the PostToolUse watch and return its systemMessage, or ''."""
        if BASELINE:
            return ""  # `main` has no watch: this is the red run
        out = run(WATCH, self.payload(tool, tool_input), self.env())
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
    subprocess.run(["bash", "-c", command], cwd=project.proj, capture_output=True, text=True)


# --------------------------------------------------------------------------- the bypass shapes
#
# One case per row of the table the design brief measured. Each one WRITES the cap lift for real
# and then reads the file back. The five rows the brief measured as ALLOWED must lift the cap on
# `main` and must be undone here.


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
       lambda p: "cp /tmp/lift_case.json .claude/settings.local.json")
bypass("mv from another file",
       lambda p: "mv /tmp/lift_case2.json .claude/settings.local.json")
bypass("sed -i in place",
       lambda p: "sed -i '' s/sonnet/opus/ .claude/settings.local.json")
bypass("python3 -c writes the path",
       lambda p: "python3 -c \"open('.claude/settings.local.json','w')"
                 ".write(open('/tmp/lift_case3.json').read())\"")
bypass("python3 runs a script file",
       lambda p: "python3 gen.py")
bypass("bash runs a script file",
       lambda p: "bash gen.sh")

# The two indirection shapes the brief's table does not cover. Neither names the path in the
# command, so no shell reading can reach them, and both must be caught by the hash.
bypass("a path held in a shell variable",
       lambda p: "f=.claude/settings.local.json; cp /tmp/lift_case4.json \"$f\"")
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
    command = "cp /tmp/lift_case5.json .claude/settings.local.json"
    decision = project.pre("Bash", {"command": command})
    shell(project, command)
    message = project.post("Bash", {"command": command})
    return {"pre": decision, "lifted": project.lifted(), "message": message,
            "settings": project.content()}


@case("a failed write is caught at turn end", "stop")
def stop_backstop(project):
    project.settle()
    # No PostToolUse fires for a FAILED tool call, so the watch never sees the write. The Stop
    # sweep is what closes that hole.
    shell(project, "cp /tmp/lift_case6.json .claude/settings.local.json")
    message = project.stop()
    return {"pre": "n/a", "lifted": project.lifted(), "message": message}


# --------------------------------------------------------------------------- the run

BASELINE = "--baseline" in sys.argv


def expectation(entry, result):
    """Return (ok, note) for one finished case."""
    group = entry["group"]
    lifted = result["lifted"]
    message = result["message"]
    if group in ("bypass", "stop"):
        if BASELINE:
            # The red run. A bypass that does not lift the cap on `main` proves nothing, so the
            # case itself is wrong and says so.
            return (lifted, "cap LIFTED on main" if lifted
                    else "the case never lifted the cap: the fixture is wrong")
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
    if BASELINE:
        return (lifted, "landed on main")
    return (lifted and not message,
            "passed through untouched" if lifted else "an APPROVED write was reverted")


def main() -> int:
    print("config_watch cases, %d in all%s" % (len(CASES), "  [BASELINE: no watch]" if BASELINE
                                               else ""))
    print()
    failed = 0
    for entry in CASES:
        root = tempfile.mkdtemp(prefix="config_watch_")
        try:
            # The files the indirection cases read. They sit OUTSIDE the project and outside the
            # measured command, which is the whole point: the cap value must never reach the
            # command line, or the case measures a shape the guard already reads. They are rebuilt
            # for each case because `mv` consumes its source.
            for name in ("lift_case.json", "lift_case2.json", "lift_case3.json",
                         "lift_case4.json", "lift_case6.json"):
                write(os.path.join("/tmp", name), LIFT)
            write("/tmp/lift_case5.json", UNRELATED)
            project = Project(root, start=SONNET)
            write(os.path.join(project.proj, "gen.py"),
                  "open('.claude/settings.local.json','w').write(open('/tmp/lift_case.json')"
                  ".read())\n")
            write(os.path.join(project.proj, "gen.sh"),
                  "cp /tmp/lift_case.json .claude/settings.local.json\n")
            write(os.path.join(project.proj, "write.sh"),
                  "t=.claude/settings.local.json\ncp /tmp/lift_case.json \"$t\"\n")
            result = entry["run"](project)
            ok, note = expectation(entry, result)
        finally:
            shutil.rmtree(root, ignore_errors=True)
        failed += 0 if ok else 1
        print("%s  %-9s pre=%-5s  %s  (%s)" % (
            "PASS" if ok else "FAIL", "[" + entry["group"] + "]",
            result["pre"], entry["name"], note))
    print()
    if failed:
        print("test_config_watch FAIL: %d of %d cases wrong" % (failed, len(CASES)))
        return 1
    print("test_config_watch PASS: %d of %d cases right" % (len(CASES), len(CASES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
