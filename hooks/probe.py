#!/usr/bin/env python3
"""Guard probe: print the verdict hooks/guard.py gives one tool call, without running the call.

A reviewer agent has no Write tool, so it cannot save a probe script. This helper takes the call as
flags or as a JSON payload on stdin and prints one line: `allow`, or `<decision> <rule>: <reason>`.

    python3 hooks/probe.py --tool Bash --command '<text>' [--cwd <dir>]
    python3 hooks/probe.py --tool Bash --command-file <path> [--cwd <dir>]
    python3 hooks/probe.py < payload.json     # {"tool_name", "tool_input", "cwd"}

Read-only. The guard runs as a subprocess of this interpreter, with the payload on its stdin and
CLAUDE_CONFIG_DIR set to a fresh temp dir, so guard.log and every other write land there. The probe
deletes that dir before it exits. The probed command is text for the guard to judge and never runs.
Bad input exits 2 or 1 with a message on stderr and prints no verdict. Standard library only.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

GUARD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guard.py")
TIMEOUT_SECONDS = 120


class BadInput(Exception):
    pass


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
    return payload


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
        # The session ids pick the guard's override and log context, so the verdict must not depend on them.
        payload = {k: v for k, v in payload.items() if k not in ("session_id", "agent_id")}
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
