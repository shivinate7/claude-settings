#!/usr/bin/env python3
"""Throwaway probe (lane grant-reaches-lanes, Cockpit item 222): does a project-scope
PreToolUse `allow` skip the auto-mode classifier, and does the user-scope guard's deny
outrank it? Emits allow only when /tmp/probe-mode says `on` and the Bash call is one of
two exact probe acts. Never emits deny or ask. One JSON line per call goes to the log."""
import json
import os
import re
import sys
import time

# Overridable so the test can run without touching a live probe's files.
MODE_FILE = os.environ.get("PROBE_MODE_FILE", "/tmp/probe-mode")
LOG_FILE = os.environ.get("PROBE_LOG_FILE", "/tmp/probe-hook.jsonl")

# The main mirror is $HOME/claude-settings-main (install.sh MAIN_MIRROR).
MIRROR = os.path.join(os.path.expanduser("~"), "claude-settings-main")

RULE = '{"permissions":{"allow":["Bash(true)"]}}'
SLOT = "@RULE@"
ALLOW = {
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "permissionDecisionReason": "hook-allow-probe: exact probe act",
    }
}


def arm1(command, cwd):
    """Arm 1: write RULE into .claude/settings.local.json of the cwd checkout."""
    if RULE not in command:
        return False
    shape = command.strip().replace(RULE, SLOT)
    here = re.escape(cwd.rstrip("/"))
    target = r"""(["']?)(?:(?:\./)?|%s/)\.claude/settings\.local\.json\1""" % here
    forms = [
        r"(?:mkdir -p \.claude && )?(?:echo|printf '%%s') '%s' > %s" % (SLOT, target),
        r"(?:mkdir -p \.claude && )?cat > %s <<-? ?'?EOF'?\n%s\nEOF" % (target, SLOT),
    ]
    return any(re.fullmatch(f, shape) for f in forms)


def arm2(command):
    """Arm 2: `git -C <main mirror> switch --detach`, optional plain ref."""
    paths = {MIRROR, "~/claude-settings-main", "$HOME/claude-settings-main"}
    alt = "|".join(re.escape(p) for p in sorted(paths))
    pat = r"""git -C (["']?)(?:%s)/?\1 switch --detach(?: [\w./-]+)?""" % alt
    return re.fullmatch(pat, command.strip()) is not None


def log(entry):
    try:
        with open(LOG_FILE, "a") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    tool = data.get("tool_name")
    command = (data.get("tool_input") or {}).get("command") or ""
    cwd = data.get("cwd") or os.getcwd()
    try:
        with open(MODE_FILE) as fh:
            mode = "on" if fh.read().strip() == "on" else "off"
    except OSError:
        mode = "off"
    matched = "none"
    if tool == "Bash":
        if arm1(command, cwd):
            matched = "arm1"
        elif arm2(command):
            matched = "arm2"
    emitted = "allow" if mode == "on" and matched != "none" else "nothing"
    log({
        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "session_id": data.get("session_id"),
        "tool_name": tool,
        "command": command[:300],
        "mode": mode,
        "matched": matched,
        "emitted": emitted,
    })
    if emitted == "allow":
        print(json.dumps(ALLOW))
    return 0


if __name__ == "__main__":
    sys.exit(main())
