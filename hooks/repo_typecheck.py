#!/usr/bin/env python3
"""The repo typecheck: runs a repo's declared check after an edit, and reports what it finds.

hooks/config_watch.py calls `run` on each PostToolUse payload. A repo declares its checks under
"typecheck" in its `.claude/layout-extras.json` (lint/layout.py `typecheck`): each entry holds globs, a
command and a timeout. After a Write, Edit or MultiEdit of a file that an entry's globs match, `run` starts
that entry's command from the repo root, with no shell, and returns the report as text. Entries that match
each run, and their reports join. The entries share one time budget, and the joined report has a length cap.

It speaks only when a command fails with output. A passing command, a missing program, a timeout, an
unreadable payload, a bad declaration and this module's own faults all return None: a check that reports on
its own malfunction, or on every edit, gets muted, and a muted check protects nothing. It cannot undo the
edit, because PostToolUse fires after the tool has run. The report tells the agent what the edit broke.

The extras path and the glob match come from lint/layout.py, the one home of both.
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
EDIT_TOOLS = ("Write", "Edit", "MultiEdit")
TOTAL_BUDGET = 90  # seconds that all matching entries of one edit share; the PostToolUse entry in settings.json must leave room
REPORT_CAP = 8000  # characters of report the block reason holds, so one noisy compiler cannot flood the turn


def _layout():
    lint = os.path.join(HERE, "..", "lint")
    if lint not in sys.path:
        sys.path.append(lint)
    import layout
    return layout


def _edited_file(payload):
    """The absolute path the tool wrote, or None when the payload names none."""
    if payload.get("tool_name") not in EDIT_TOOLS:
        return None
    tool_input = payload.get("tool_input")
    raw = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    if not isinstance(raw, str) or not raw:
        return None
    cwd = payload.get("cwd")
    return os.path.abspath(os.path.join(cwd, raw) if isinstance(cwd, str) and cwd else raw)


def _root_of(layout, edited):
    """The nearest folder above `edited` that holds the repo's extras file, or None. It walks the path as
    written, so a file reached through a symlinked root finds that root."""
    extras = layout.layout().get("extras")
    if not extras:
        return None
    here = os.path.dirname(edited)
    while True:
        if os.path.isfile(os.path.join(here, *extras.split("/"))):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent


def _command_report(root, entry, name, limit):
    """The failure report of one entry's command, run for at most `limit` seconds, or None when it passes,
    cannot run or says nothing."""
    argv = list(entry["command"])
    if ("/" in argv[0] or "\\" in argv[0]) and not os.path.isabs(argv[0]):
        argv[0] = os.path.join(root, argv[0])  # a relative program resolves against the root on every platform
    try:
        done = subprocess.run(argv, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=min(entry["timeout"], limit))
    except (OSError, subprocess.SubprocessError):
        return None
    output = ((done.stdout or "") + (done.stderr or "")).strip()
    if done.returncode == 0 or not output:
        return None
    return "typecheck failed after editing %s:\n%s" % (name, output)


def run(payload):
    """The report text for this PostToolUse payload, or None when there is nothing to say."""
    try:
        edited = _edited_file(payload)
        if edited is None:
            return None
        layout = _layout()
        root = _root_of(layout, edited)
        if root is None:
            return None
        rel = os.path.relpath(edited, root)
        reports, spent = [], 0.0
        for entry in layout.typecheck(root):
            if not layout.match_globs(rel, entry["globs"]):
                continue
            left = TOTAL_BUDGET - spent
            if left <= 0:
                break  # the budget is gone: the rest of the matching entries do not run
            started = time.monotonic()
            found = _command_report(root, entry, os.path.basename(edited), left)
            spent += time.monotonic() - started
            if found:
                reports.append(found)
        report = "\n\n".join(reports)
        if len(report) > REPORT_CAP:
            report = report[:REPORT_CAP] + "\n[typecheck report cut at %d characters]" % REPORT_CAP
        return report or None
    except Exception:  # a check never fails a turn on its own bug
        return None
