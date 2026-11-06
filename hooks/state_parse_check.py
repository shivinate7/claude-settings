#!/usr/bin/env python3
"""After a Bash, PowerShell, Write, Edit or MultiEdit call, names a state file the call left unreadable: a *.json that does not parse, an inbox or handoff .md with a code fence left open, an inbox block header lost, or a handoff with no Working premises heading. It never blocks, and it says nothing about a file that was already broken or is gone (decision state-file-parse-check). Standard library only.

The mistake it stops: a Bash, PowerShell, Write, Edit or MultiEdit call that leaves a state file
broken: a *.json that json.loads rejects, an inbox (*.inbox.md) or handoff (*.md) in the handoff folder
with a code fence left open, an Edit that drops an inbox block header, a handoff with no `## Working
premises` heading. Later hooks and sessions read a broken file, and the break shows turns later.

It never blocks, never reverts and never writes a file. It prints a PostToolUse additionalContext that
names the file, the line and the fault, and exits 0 on every path.

What it reads: only the files the call names.
  - Write, Edit, MultiEdit: the call's file_path, when it is a *.json or a *.md in the handoff folder.
  - Bash, PowerShell: the command split by shlex. A path counts when it is in the handoff folder, a
    settings*.json, a roadmap/data/steps/*.json, or a *.json in a write position (a `sed -i` operand, a
    `>` or `>>` target, a `tee` argument). So `cat bad.json` says nothing.
  - The handoff folder is the folder of precompact_handoff.handoff_path, under CLAUDE_CONFIG_DIR.
  - A premises check on a handoff runs for a call that wrote it, not for a read of it.

No false alarm mid-edit: an Edit or MultiEdit rebuilds the before-state from old_string and new_string
(the after-state with new_string put back to old_string). When the before-state already had the fault,
or cannot be rebuilt (new_string empty, or not found in the file), it says nothing. A file that is gone
says nothing: a delete is not a break. A Write or a shell write is judged as left.

Fence rules, one home each: an inbox uses feedback_guard.scan (parse()'s loop, so this check and the Stop
check agree on the inbox); another handoff .md uses feedback_guard.fence_scan (unfenced()'s loop). A fence
inside a JSON string is text: the fence scan never runs on JSON.

Cost: one shell start for a call that names no state file (the settings.json filter greps only
tool_input and exits unless it names `.json` or the handoff folder). A call that names one: one Python
start, one read of each named file, and the import of feedback_guard when a .md is judged. It writes no
file and starts no other process.

STATE_PARSE_CHECK_UNDER_TEST names another copy of this file for hooks/test_state_parse_check.py.
"""
import fnmatch
import json
import os
import re
import shlex
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import precompact_handoff  # noqa: E402  the one home of the handoff path and the premises heading

SHELL_TOOLS = ("Bash", "PowerShell")
EDIT_TOOLS = ("Edit", "MultiEdit")
FILE_TOOLS = ("Write",) + EDIT_TOOLS
MAX_PATHS = 20           # files judged per call
MAX_CANDIDATES = 64      # before-states tried for one Edit whose new_string occurs more than once
MAX_BYTES = 8_000_000    # a state file larger than this is not read
SEPARATORS = {"|", "||", "&&", ";", "&", ";;", "|&", "(", ")"}
REDIRECTS = {">", ">>", ">|", "&>", "&>>"}
SKIP_PROGRAMS = {"sudo", "command", "env", "exec", "nohup", "time"}
SED_IN_PLACE = re.compile(r"-[A-Za-z]*i|--in-place")


def handoff_dir():
    return os.path.dirname(precompact_handoff.handoff_path("x"))


def norm(path):
    return os.path.normcase(os.path.normpath(path.replace("\\", "/")))


def resolve(path, cwd):
    path = os.path.expandvars(os.path.expanduser(path))
    if "$" in path:
        return None
    return path if os.path.isabs(path) or re.match(r"[A-Za-z]:[\\/]", path) else os.path.join(cwd, path)


def kind_of(path, hdir):
    """"json", "inbox", "handoff", or None for a file this check does not judge."""
    name = os.path.basename(path.replace("\\", "/"))
    if name.endswith(".json"):
        return "json"
    if name.endswith(".md") and norm(os.path.dirname(path)) == norm(hdir):
        return "inbox" if name.endswith(".inbox.md") else "handoff"
    return None


def is_state_path(path, hdir):
    """A path that counts in any position of a shell command."""
    flat = path.replace("\\", "/")
    name = os.path.basename(flat)
    if fnmatch.fnmatch(name, "settings*.json"):
        return True
    if name.endswith(".json") and "/roadmap/data/steps/" in "/" + flat.lstrip("/"):
        return True
    return kind_of(path, hdir) in ("inbox", "handoff") or (
        name.endswith(".json") and norm(os.path.dirname(path)) == norm(hdir))


def tokens(command, powershell):
    """The command's words and punctuation. A command shlex cannot read falls back to a whitespace split."""
    try:
        lexer = shlex.shlex(command, posix=not powershell, punctuation_chars=True)
        lexer.whitespace_split = True
        words = list(lexer)
    except ValueError:
        words = command.split()
    return [w[1:-1] if len(w) > 1 and w[0] == w[-1] and w[0] in "'\"" else w for w in words]


def shell_paths(command, powershell, cwd, hdir):
    """[(path, written)] of the files a shell command names that this check may judge, in order."""
    found = {}

    def add(word, written):
        path = resolve(word, cwd)
        if path is None:
            return
        found[path] = found.get(path, False) or written

    words, seg, redirect = tokens(command, powershell), [], False
    segments = []
    for word in words + [";"]:
        if word in SEPARATORS:
            segments.append(seg)
            seg, redirect = [], False
        elif word in REDIRECTS:
            redirect = True
        elif redirect:
            add(word, True)
            redirect = False
        elif not set(word) <= set("<>&|();"):
            seg.append(word)
    for seg in segments:
        args = [w for w in seg if not re.fullmatch(r"\w+=.*", w)]
        while args and os.path.basename(args[0]) in SKIP_PROGRAMS:
            args = args[1:]
        program = os.path.basename(args[0]) if args else ""
        in_place = program == "sed" and any(SED_IN_PLACE.fullmatch(w) or w.startswith("-i")
                                            for w in args[1:] if w.startswith("-") and w != "--")
        for word in args[1:]:
            written = (in_place and word.endswith(".json")) or (program == "tee" and not word.startswith("-"))
            probe = resolve(word, cwd)
            if probe is not None and not word.startswith("-") and (written or is_state_path(probe, hdir)):
                add(word, bool(written))
    return list(found.items())[:MAX_PATHS]


def read_text(path):
    """The file's text, or None when it is missing, too big, or not UTF-8: the check then says nothing."""
    try:
        if not os.path.isfile(path) or os.path.getsize(path) > MAX_BYTES:
            return None
        with open(path, "rb") as handle:
            return handle.read().decode("utf-8")
    except (OSError, ValueError):
        return None


def position(text, index):
    return text.count("\n", 0, index) + 1, index - (text.rfind("\n", 0, index) + 1) + 1


def json_fault(text):
    """(line, column, why) when json.loads rejects the text, else None. A trailing comma is named at the
    comma, as Python 3.13 does, so the verdict does not depend on the Python version."""
    try:
        json.loads(text)
    except json.JSONDecodeError as error:
        index, why = error.pos, error.msg
        if why.startswith("Expecting") and text[index:index + 1] in ("}", "]"):
            before = text[:index].rstrip()
            if before.endswith(","):
                index, why = len(before) - 1, "trailing comma"
        line, column = position(text, index)
        return line, column, why
    except Exception:  # a RecursionError on deep nesting: not a verdict
        return None
    return None


def facts(kind, text, guard):
    """What the check reads from one state of a file: {"json": fault, "fence": line, "stamps": [...], "premises": bool}."""
    if kind == "json":
        return {"json": json_fault(text)}
    if kind == "inbox":
        blocks, open_line = guard.scan(text)
        return {"fence": open_line, "stamps": [b["stamp"] for b in blocks]}
    return {"fence": guard.fence_scan(text)[1],
            "premises": precompact_handoff._PREMISES_HEAD.search(text) is not None}


def unapply(text, edit):
    """The before-states of one edit: `text` with new_string put back to old_string, one per place
    new_string occurs, or None when that cannot be done."""
    old, new = edit.get("old_string"), edit.get("new_string")
    if not isinstance(old, str) or not isinstance(new, str) or not new:
        return None
    if edit.get("replace_all"):
        return [text.replace(new, old)] if new in text else None
    states, start = [], text.find(new)
    while start >= 0 and len(states) <= MAX_CANDIDATES:
        states.append(text[:start] + old + text[start + len(new):])
        start = text.find(new, start + 1)
    return states if 0 < len(states) <= MAX_CANDIDATES else None


def before_states(tool, tool_input, after):
    """None for a call judged as left; [] when an Edit's before-state cannot be rebuilt; else the candidates."""
    if tool not in EDIT_TOOLS:
        return None
    edits = tool_input.get("edits") if tool == "MultiEdit" else [tool_input]
    if not isinstance(edits, list):
        return []
    states = [after]
    for edit in reversed(edits):
        if not isinstance(edit, dict):
            return []
        nxt = []
        for state in states:
            back = unapply(state, edit)
            if back is None:
                return []
            nxt += back
        states = nxt[:MAX_CANDIDATES]
    return states


def judge(path, kind, after, befores, written, guard):
    """The fault lines for one file. `befores` is None (judge as left), [] (silent), or the candidate
    before-states: a fault counts only when no candidate already had it."""
    if befores is not None and not befores:
        return []
    now = facts(kind, after, guard)
    was = [facts(kind, text, guard) for text in befores or []]
    name, lines = path, []
    if kind == "json":
        if now["json"] and not any(w["json"] for w in was):
            line, column, why = now["json"]
            lines.append("%s is not valid JSON: %s at line %d column %d" % (name, why, line, column))
        return lines
    if now["fence"] and not any(w["fence"] for w in was):
        lines.append("%s has a code fence left open: the fence at line %d is never closed" % (name, now["fence"]))
    if kind == "inbox" and was:
        lost = None
        for w in was:
            gone = list(w["stamps"])
            for stamp in now["stamps"]:
                if stamp in gone:
                    gone.remove(stamp)
            lost = gone if lost is None else [s for s in lost if s in gone]
        if lost:
            lines.append("%s lost %d block header(s): %s" % (name, len(lost), ", ".join(lost)))
    if kind == "handoff" and written and not now["premises"] and (not was or any(w["premises"] for w in was)):
        lines.append("%s has no `## Working premises` heading" % name)
    return lines


def targets(payload, hdir):
    """[(path, kind, written)] of the files this call names that the check may judge."""
    tool, tool_input = payload.get("tool_name"), payload.get("tool_input")
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else os.getcwd()
    if not isinstance(tool_input, dict):
        return []
    if tool in FILE_TOOLS:
        raw = tool_input.get("file_path")
        path = resolve(raw, cwd) if isinstance(raw, str) else None
        kind = kind_of(path, hdir) if path else None
        return [(path, kind, True)] if kind else []
    if tool in SHELL_TOOLS and isinstance(tool_input.get("command"), str):
        return [(p, kind_of(p, hdir), written) for p, written in
                shell_paths(tool_input["command"], tool == "PowerShell", cwd, hdir) if kind_of(p, hdir)]
    return []


def check(payload):
    """The additionalContext text for the call, or "" when every file it names is fine."""
    hdir = handoff_dir()
    found = targets(payload, hdir)
    if not found:
        return ""
    guard = None
    if any(kind != "json" for _, kind, _ in found):
        import feedback_guard as guard  # noqa: E402  the one home of the fence loops
    lines = []
    for path, kind, written in found:
        after = read_text(path)
        if after is None:
            continue
        befores = before_states(payload.get("tool_name"), payload.get("tool_input"), after)
        lines += judge(path, kind, after, befores, written, guard)
    if not lines:
        return ""
    return "state_parse_check: a state file this call touched no longer parses.\n- " + "\n- ".join(lines)


def main():
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
        text = check(payload) if isinstance(payload, dict) else ""
        if text:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}))
    except Exception as error:  # advisory hook: fail open, one stderr line shows in --debug
        print("state_parse_check: %s" % error, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
