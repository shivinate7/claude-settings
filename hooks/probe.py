#!/usr/bin/env python3
"""Guard probe: print the verdict hooks/guard.py gives one tool call, without running the call.

A reviewer agent has no Write tool, so it cannot save a probe script. This helper takes the call as
flags or as a JSON payload on stdin and prints one line: `allow`, or `<decision> <rule>: <reason>`.

    python3 hooks/probe.py --tool Bash --command '<text>' [--cwd <dir>]
    python3 hooks/probe.py --tool Bash --command-file <path> [--cwd <dir>]
    python3 hooks/probe.py < payload.json     # {"tool_name", "tool_input", "cwd"}

Run `hooks/probe.py` in a claude-settings worktree to judge that branch's guard. Once the probe is
installed, run `~/.claude/hooks/probe.py` in any other repo to judge the installed guard.

The verdict is for a call with no session id and no agent id. The probe drops agent_id, agent_type and
session_id from a stdin payload, and writes one stderr note that names each field it drops. So
no check that needs agent_id is judged. Some of them are builder-test-edit, test-author-scope,
the commit and push diff checks, worktree-home and the red-run folder exemption. This list may
not be complete. With no session id, the guard's own-scratchpad exemption does not apply: a
`--cwd` in a session's scratchpad reads like a folder outside any checkout.

A `noted` verdict allows the call and writes a log line. The probe prints it as plain `allow`.

`--cwd` sets the folder the call runs in. The probe makes a relative `--cwd` absolute. With no
`--cwd`, the folder is the one you run the probe from. In a reviewer's own worktree, `git reset --hard origin/main` reads allow. In a
folder outside any checkout, it reads deny shared-tree.

With `--command` or `--command-file`, the tool must be one of the guard's shell tools
(guard_core.SHELL_TOOLS). Any other tool exits 1 with a message on stderr and no verdict.

The guard runs as a subprocess, with the payload on its stdin. CLAUDE_CONFIG_DIR is a fresh temp
dir, so guard.log and the other config writes land there. The probe deletes that dir before it
exits. The temp dir moves the guard's config reads too. So frozen-path, override state and the
guard's other config reads are not judged as live. When the call's folder is inside the real
config dir, the probe writes one stderr line that starts `probe: note:` and says so.

The probed command is text for the guard to judge, and it never runs. The probe writes its config
files only to its temp dir. The guard's own `git status` may refresh .git/index. During a merge
in progress, the guard's merge-tree check writes git objects. Bad input exits 2 or 1, with a
message on stderr and no verdict.

If the guard refuses the probe call itself, the guard's deny line is the verdict. Report it, and
do not encode the command another way. A harness refusal ("too complex", worktree isolation) is
not a verdict. Report it as a need, and do not re-encode the call.
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
sys.dont_write_bytecode = True  # the import below must not write __pycache__ beside hooks/
if HERE not in sys.path:
    sys.path.insert(0, HERE)
try:
    import _nowindow  # the one home of a no-window child start (hooks/_nowindow.py)
except ImportError:  # the probe never dies for a missing helper, as in a copy of the probe beside a stub guard
    _nowindow = subprocess
TIMEOUT_SECONDS = 120
# The payload fields that tie a call to a session or an agent. The verdict is for a main-session call.
SESSION_FIELDS = ("agent_id", "agent_type", "session_id")
# The outer session's ids. guard_shared_tree.session_id_of reads the first when the payload has no
# session_id. override.py reads the second for the Opus spawn step.
SESSION_ENV = ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE_SESSION_ID")


class BadInput(Exception):
    pass


def hooks_module(name):
    """The hooks module `name`, imported from beside this file. None when that file is absent, as in a
    copy of the probe beside a stub guard; a real guard cannot run without its modules."""
    if not os.path.exists(os.path.join(HERE, name + ".py")):
        return None
    sys.dont_write_bytecode = True  # the import must not write __pycache__ beside hooks/
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    return __import__(name)


def shell_tools():
    """The guard's SHELL_TOOLS, read from guard_core.py beside this file, or None without it."""
    guard_core = hooks_module("guard_core")
    return None if guard_core is None else guard_core.SHELL_TOOLS


def config_overlap_note(folder):
    """A `probe: note:` line when `folder` lies inside the real config dir, else None. The guard reads
    its config from the probe's temp dir, so its config reads for such a folder are not live."""
    shared_names = hooks_module("shared_names")
    if shared_names is None:
        return None
    real_config = os.path.realpath(shared_names.config_dir())
    real_folder = os.path.realpath(folder)
    try:
        inside = os.path.commonpath([real_config, real_folder]) == real_config
    except ValueError:  # different drives on Windows
        inside = False
    if not inside:
        return None
    return ("probe: note: the folder %s is inside the real config dir %s; frozen-path and override state "
            "are not judged for this folder, since the guard reads its config from the probe's temp dir"
            % (folder, real_config))


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
    if not lines:
        return None
    # lint/guard_log_report.py is the one reader of guard.log lines. Without it a crash would read as an
    # allow, so a failed import ends the probe with verdict unknown.
    sys.dont_write_bytecode = True  # the import must not write __pycache__ beside lint/
    lint_dir = os.path.join(HERE, "..", "lint")
    if lint_dir not in sys.path:
        sys.path.insert(0, lint_dir)
    try:
        import guard_log_report
    except Exception as exc:
        raise BadInput("cannot read the guard log (%s), verdict unknown" % exc)
    for line in lines:
        row = guard_log_report.parse_line(line)
        if row is not None and row.rule == "guard-crash":
            return row.matched
    return None


def remove_dir(path):
    shutil.rmtree(path, ignore_errors=True)
    if os.path.exists(path):
        print("probe: could not remove its temp dir %s" % path, file=sys.stderr)


def probe(payload):
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd:
        # The guard reads cwd as given, so a relative path would name a folder under the guard's own cwd.
        cwd = os.path.abspath(cwd)
        payload = dict(payload, cwd=cwd)
    # With no cwd, the guard judges the folder it runs in, which is this process's own.
    note = config_overlap_note(cwd if isinstance(cwd, str) and cwd else os.getcwd())
    if note is not None:
        print(note, file=sys.stderr)
    run_cwd = cwd if isinstance(cwd, str) and os.path.isdir(cwd) else None
    config_dir = tempfile.mkdtemp(prefix="probe-guard-")
    try:
        env = dict(os.environ)
        env["CLAUDE_CONFIG_DIR"] = config_dir
        env["PYTHONDONTWRITEBYTECODE"] = "1"  # the guard's imports must not write __pycache__ beside hooks/
        # The outer session must not change the verdict. session_id_of falls back to CLAUDE_CODE_SESSION_ID,
        # and override.py reads CLAUDE_CODE_REMOTE_SESSION_ID for the Opus spawn step. Drop both.
        for name in SESSION_ENV:
            env.pop(name, None)
        try:
            result = _nowindow.run([sys.executable, GUARD], input=json.dumps(payload), capture_output=True,
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
