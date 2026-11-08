#!/usr/bin/env python3
"""Guard probe: print the verdict hooks/guard.py gives one tool call, without running the call.

A reviewer agent has no Write tool, so it cannot save a probe script. This helper takes the call as
flags or as a JSON payload on stdin and prints one line: `allow`, or `<decision> <rule>: <reason>`.

    python3 hooks/probe.py --tool Bash --command '<text>' [--cwd <dir>]
    python3 hooks/probe.py --tool Bash --command-file <path> [--cwd <dir>]
    python3 hooks/probe.py < payload.json     # {"tool_name", "tool_input", "cwd"}

Run `hooks/probe.py` in a claude-settings worktree to judge that branch's guard. Run
`~/.claude/hooks/probe.py` elsewhere to judge the installed guard.

The verdict is for a call from the main session. The probe drops agent_id, agent_type and
session_id from a stdin payload, and writes one stderr note that names each field it drops. So
builder-test-edit, test-author-scope and the commit and push diff checks are not judged. They
need agent_id.

`--cwd` sets the folder the call runs in. With no `--cwd`, the folder is the one you run the
probe from. In a reviewer's own worktree, `git reset --hard origin/main` reads allow. In a
folder outside any checkout, it reads deny shared-tree.

With `--command` or `--command-file`, the tool must be one of the guard's shell tools
(guard_core.SHELL_TOOLS). Any other tool exits 1 with a message on stderr and no verdict.

The guard runs as a subprocess, with the payload on its stdin. CLAUDE_CONFIG_DIR is a fresh temp
dir, so guard.log and the other config writes land there. The probe deletes that dir before it
exits. The probed command is text for the guard to judge, and it never runs. The probe writes
only its temp dir. One exception: during a merge in progress, the guard's merge-tree check
writes git objects. Bad input exits 2 or 1, with a message on stderr and no verdict.

If the guard refuses the probe call itself, that refusal is the verdict. Report it, and do not
encode the command another way.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "guard.py")
TIMEOUT_SECONDS = 120
# The payload fields that tie a call to a session or an agent. The verdict is for a main-session call.
SESSION_FIELDS = ("agent_id", "agent_type", "session_id")
# session_id_of in guard_shared_tree.py falls back to these when the payload has no session_id.
SESSION_ENV = ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE_SESSION_ID")


class BadInput(Exception):
    pass


def shell_tools():
    """The guard's SHELL_TOOLS, read from guard_core.py beside this file. None when that file is absent,
    as in a copy of the probe beside a stub guard; a real guard cannot run without guard_core.py."""
    if not os.path.exists(os.path.join(HERE, "guard_core.py")):
        return None
    sys.dont_write_bytecode = True  # the import must not write __pycache__ beside hooks/
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import guard_core
    return guard_core.SHELL_TOOLS


def read_payload(args):
    """The payload dict the guard receives, from flags, or from stdin when no flag was given."""
    if args.command is not None and args.command_file is not None:
        raise BadInput("give --command or --command-file, not both")
    if args.command_file is not None:
        try:
            with open(args.command_file, "rb") as handle:
                command = handle.read().decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise BadInput("cannot read --command-file %s: %s" % (args.command_file, exc))
    else:
        command = args.command
    if command is not None:
        tools = shell_tools()
        if tools is not None and args.tool not in tools:
            raise BadInput("--tool %s is not a shell tool the guard judges (%s)" % (args.tool, ", ".join(tools)))
        payload = {"tool_name": args.tool, "tool_input": {"command": command}}
        if args.cwd is not None:
            payload["cwd"] = args.cwd
        return payload
    if args.cwd is not None or args.tool != "Bash":
        raise BadInput("--command or --command-file is required with --tool or --cwd")
    if sys.stdin is None or sys.stdin.isatty():
        raise BadInput("give --command, --command-file, or a JSON payload on stdin")
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise BadInput("stdin is not a JSON payload: %s" % exc)
    if not isinstance(payload, dict):
        raise BadInput("the JSON payload must be an object")
    if not isinstance(payload.get("tool_name"), str) or not isinstance(payload.get("tool_input"), dict):
        raise BadInput('the JSON payload needs a string "tool_name" and an object "tool_input"')
    dropped = [field for field in SESSION_FIELDS if field in payload]
    if dropped:
        print("probe: dropped %s from the payload; the verdict is for a main-session call" % ", ".join(dropped),
              file=sys.stderr)
    return {k: v for k, v in payload.items() if k not in SESSION_FIELDS}


def verdict_line(guard_stdout):
    """`allow` for no output, else `<decision> <reason>` from the guard's permissionDecision."""
    if not guard_stdout.strip():
        return "allow"
    try:
        out = json.loads(guard_stdout)["hookSpecificOutput"]
        decision, reason = out["permissionDecision"], out["permissionDecisionReason"]
    except (ValueError, KeyError, TypeError):
        raise BadInput("the guard printed output this probe does not read: %r" % guard_stdout[:200])
    return " ".join(("%s %s" % (decision, reason)).split())


def crash_reason(config_dir):
    """The reason of a guard-crash line in this run's guard.log, else None. The guard fails open on a
    crash (exit 0, no output), so only its log tells a crash from an allow. The dir is fresh, so any
    such line is this run's."""
    try:
        with open(os.path.join(config_dir, "guard.log"), encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return None
    for line in lines:
        fields = line.split("\t")
        if len(fields) >= 5 and fields[3] == "guard-crash":
            return fields[4]
    return None


def remove_dir(path):
    shutil.rmtree(path, ignore_errors=True)
    if os.path.exists(path):
        print("probe: could not remove its temp dir %s" % path, file=sys.stderr)


def probe(payload):
    config_dir = tempfile.mkdtemp(prefix="probe-guard-")
    try:
        env = dict(os.environ)
        env["CLAUDE_CONFIG_DIR"] = config_dir
        env["PYTHONDONTWRITEBYTECODE"] = "1"  # the guard's imports must not write __pycache__ beside hooks/
        # The guard reads the session id from the payload, else from these env vars, and the id changes
        # verdicts such as a call from the session's own scratchpad. Drop both, so the outer session cannot.
        for name in SESSION_ENV:
            env.pop(name, None)
        cwd = payload.get("cwd")
        run_cwd = cwd if isinstance(cwd, str) and os.path.isdir(cwd) else None
        try:
            result = subprocess.run([sys.executable, GUARD], input=json.dumps(payload), capture_output=True,
                                    text=True, encoding="utf-8", env=env, cwd=run_cwd,
                                    timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            raise BadInput("the guard did not answer in %d seconds" % TIMEOUT_SECONDS)
        if result.returncode != 0:
            raise BadInput("the guard exited %d: %s" % (result.returncode, result.stderr.strip()[-200:]))
        crashed = crash_reason(config_dir)
        if crashed is not None:
            raise BadInput("guard crashed (%s), verdict unknown" % " ".join(crashed.split()))
        return verdict_line(result.stdout)
    finally:
        remove_dir(config_dir)


def main():
    parser = argparse.ArgumentParser(description="Print the guard's verdict for one tool call; never run it.")
    parser.add_argument("--tool", default="Bash", help="tool name, default Bash")
    parser.add_argument("--command", help="the command text to judge")
    parser.add_argument("--command-file", help="a file holding the command text to judge")
    parser.add_argument("--cwd", help="the working folder the call would run in")
    args = parser.parse_args()
    try:
        line = probe(read_payload(args))
    except BadInput as exc:
        print("probe: %s" % exc, file=sys.stderr)
        return 1
    sys.stdout.write(line + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
