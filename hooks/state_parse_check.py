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
  - Bash, PowerShell: the command split into words and operators (a quoted `>` is a word). A path counts
    only in a write position (a `sed -i` operand, a `>` or `>>` target, a `tee` argument), and only when it
    is a *.json or a *.md in the handoff folder. A read says nothing, even of a state file: it changes nothing, and an alarm on each read would
    repeat until the file is fixed. So `cat bad.json` says nothing.
  - The handoff folder is the folder of precompact_handoff.handoff_path, under CLAUDE_CONFIG_DIR.

No false alarm mid-edit: an Edit or MultiEdit rebuilds the before-state from old_string and new_string
(the after-state with new_string put back to old_string). A new_string that occurs more than once, or is
empty, gives one candidate before-state per place it could have been. The check stays silent only when
every candidate was already broken. It caps the work (candidates times file size) before it builds any
candidate, builds them one at a time, and stays silent past the cap or when new_string is not in the file.
A file that is gone says nothing: a delete is not a break. A Write or a shell write is judged as left.

Fence rules, one home (hooks/fence_rule.py, which feedback_guard.py also reads): an inbox uses
fence_rule.inbox_scan (parse()'s loop, so this check and the Stop check agree on the inbox); another handoff
.md uses fence_rule.fence_scan (unfenced()'s loop) with the indent capped at three spaces. A fence inside a
JSON string is text: the fence scan never runs on JSON.

Cost: every call in the matcher starts the settings.json filter's shell, with one cat and one grep. The
filter greps only tool_input and exits unless it names `.json` or the handoff folder, so a call that names
neither starts no Python. A call that names one starts one Python, which reads each file it judges, and
imports fence_rule when a .md is judged. It writes no file and starts no other process.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import precompact_handoff  # noqa: E402  the one home of the handoff path and the premises heading

SHELL_TOOLS = ("Bash", "PowerShell")
EDIT_TOOLS = ("Edit", "MultiEdit")
FILE_TOOLS = ("Write",) + EDIT_TOOLS
MAX_PATHS = 20           # files judged per call
MAX_CANDIDATES = 64      # places one new_string may occur in and still be tried
SHORT_TEXT = 2000        # a text this short is tried at every character for an Edit that only removed text
MAX_WORK = 60_000_000    # candidates times file size: a costlier rebuild is skipped, and the check is silent
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


OPERATOR = re.compile(r"&>>|&>|>>|>\||>&|<&|<<|\|\||&&|\|&|;;|[|;&()<>]")


def tokens(command, powershell):
    """[(text, is_operator)] for the command, in order. A quoted or escaped `>`, `;` or `#` is a word, never an
    operator or a comment. A newline outside quotes is a `;`. A command with an unclosed quote falls back to a
    whitespace split with no operators. PowerShell keeps a backslash as a path character."""
    out, word, quoted, i = [], "", False, 0

    def flush():
        nonlocal word, quoted
        if word or quoted:
            out.append((word, False))
        word, quoted = "", False

    try:
        while i < len(command):
            ch = command[i]
            if ch in "'\"":
                end = command.find(ch, i + 1)
                while ch == '"' and end > 0 and not powershell and command[end - 1] == "\\":
                    end = command.find(ch, end + 1)
                if end < 0:
                    raise ValueError("unclosed quote")
                word, quoted, i = word + command[i + 1:end], True, end + 1
            elif ch == "\\" and not powershell and i + 1 < len(command):
                word, i = word + command[i + 1], i + 2
            elif ch in " \t\r":
                flush()
                i += 1
            elif ch == "\n":
                flush()
                out.append((";", True))
                i += 1
            elif ch == "#" and not word and not quoted:
                end = command.find("\n", i)
                i = len(command) if end < 0 else end
            else:
                found = OPERATOR.match(command, i)
                if found:
                    if not (word.isdigit() and found.group().startswith((">", "&>"))):
                        flush()
                    else:
                        word = ""
                    out.append((found.group(), True))
                    i = found.end()
                else:
                    word, i = word + ch, i + 1
        flush()
    except ValueError:
        return [(w, False) for w in command.split()]
    return out


def shell_paths(command, powershell, cwd, hdir):
    """The files a shell command writes that this check may judge, in order: a redirect target, a `tee`
    argument, a `sed -i` operand."""
    found = {}

    def add(word):
        path = resolve(word, cwd)
        if path is not None:
            found[path] = True

    seg, redirect, segments = [], False, []
    for word, is_op in tokens(command, powershell) + [(";", True)]:
        if is_op and word in SEPARATORS:
            segments.append(seg)
            seg, redirect = [], False
        elif is_op and word in REDIRECTS:
            redirect = True
        elif is_op:
            continue
        elif redirect:
            add(word)
            redirect = False
        else:
            seg.append(word)
    for seg in segments:
        args = [w for w in seg if not re.fullmatch(r"\w+=.*", w)]
        while args and os.path.basename(args[0]) in SKIP_PROGRAMS:
            args = args[1:]
        program = os.path.basename(args[0]) if args else ""
        in_place = program == "sed" and any(SED_IN_PLACE.fullmatch(w) or w.startswith("-i")
                                            for w in args[1:] if w.startswith("-") and w != "--")
        if in_place or program == "tee":
            for word in args[1:]:
                if not word.startswith("-"):
                    add(word)
    return [p for p in found if kind_of(p, hdir)][:MAX_PATHS]


def read_text(path):
    """The file's text, or None when it is missing, too big, or not UTF-8: the check then says nothing."""
    try:
        if not os.path.isfile(path) or os.path.getsize(path) > MAX_BYTES:
            return None
        with open(path, "rb") as handle:
            return handle.read().decode("utf-8")
    except (OSError, ValueError):
        return None


def json_fault(text):
    """(line, column, why) when json.loads rejects the text, else None."""
    try:
        json.loads(text)
    except json.JSONDecodeError as error:
        return error.lineno, error.colno, error.msg
    except Exception:  # a RecursionError on deep nesting: not a verdict
        return None
    return None


def facts(kind, text, fences):
    """What the check reads from one state of a file: {"json": fault, "fence": line, "stamps": [...], "premises": bool}."""
    if kind == "json":
        return {"json": json_fault(text)}
    if kind == "inbox":
        blocks, open_line = fences.inbox_scan(text)
        return {"fence": open_line, "stamps": [b["stamp"] for b in blocks]}
    return {"fence": fences.fence_scan(text, 3)[1],
            "premises": precompact_handoff._premises_head().search(text) is not None}


class Unknown(Exception):
    """The before-state cannot be rebuilt, or costs more than MAX_WORK to try: the check says nothing."""


def places(text, edit):
    """The offsets where a before-state of `edit` differs from `text`, or raises Unknown. new_string
    occurs at each offset it is found at; an empty new_string could have been removed from any line start
    and the end, and from every offset when the text is short. Counts the places before anything is built."""
    new = edit["new_string"]
    if not new:
        count = len(text) + 1 if len(text) <= SHORT_TEXT else text.count("\n") + 2
        if count * len(text) > MAX_WORK:
            raise Unknown()
        short = len(text) <= SHORT_TEXT
        return [i for i in range(len(text) + 1) if short or i == 0 or i == len(text) or text[i - 1] == "\n"]
    if edit.get("replace_all"):
        found = [text.find(new)]
    else:
        found, start = [], text.find(new)
        while start >= 0 and len(found) <= MAX_CANDIDATES:
            found.append(start)
            start = text.find(new, start + 1)
    if found[0] < 0 or len(found) > MAX_CANDIDATES or len(found) * len(text) > MAX_WORK:
        raise Unknown()
    return found


def unapply(text, edit, spent):
    """The before-states of one edit, one at a time: `text` with new_string put back to old_string at
    each place it could have been. `spent` counts the characters built, and the work cap stops it."""
    old, new = edit["old_string"], edit["new_string"]
    if edit.get("replace_all") and new:
        spent[0] += len(text) + len(old)
        yield text.replace(new, old)
        return
    for i in places(text, edit):
        spent[0] += len(text) + len(old)
        if spent[0] > MAX_WORK:
            raise Unknown()
        yield text[:i] + old + text[i + len(new):]


class Candidates:
    """The candidate before-states of an Edit or MultiEdit, built one at a time on each pass."""

    def __init__(self, after, edits):
        self.after, self.edits = after, edits

    def __bool__(self):
        return True

    def __iter__(self):
        spent = [0]

        def walk(text, rest):
            if not rest:
                yield text
                return
            for back in unapply(text, rest[0], spent):
                yield from walk(back, rest[1:])

        return walk(self.after, self.edits[::-1])


def before_states(tool, tool_input, after):
    """(candidates, removal). candidates is None for a call judged as left, [] when an Edit's before-state
    cannot be rebuilt or costs more than the work cap, else a Candidates sequence. removal is True when an
    edit only removed text, so the place it was removed from is unknown."""
    if tool not in EDIT_TOOLS:
        return None, False
    edits = tool_input.get("edits") if tool == "MultiEdit" else [tool_input]
    if not isinstance(edits, list) or not edits or not all(
            isinstance(e, dict) and isinstance(e.get("old_string"), str) and isinstance(e.get("new_string"), str)
            for e in edits):
        return [], False
    try:
        places(after, edits[-1])  # the cap comes before any candidate is built
    except Unknown:
        return [], False
    return Candidates(after, edits), any(not e["new_string"] for e in edits)


def judge(path, kind, after, befores, fences):
    """The fault lines for one file. `befores` is None (judge as left), [] (silent), or the candidate
    before-states. A fault counts unless every candidate already had it."""
    if befores is not None and not befores:
        return []
    now = facts(kind, after, fences)
    fine = lost = None
    premises = False
    try:
        for text in befores or ():
            was = facts(kind, text, fences)
            if kind == "json":
                fine = fine or not was["json"]
            else:
                fine = fine or not was["fence"]
                if kind == "handoff":
                    premises = premises or was["premises"]
                else:
                    gone = list(was["stamps"])
                    for stamp in now["stamps"]:
                        if stamp in gone:
                            gone.remove(stamp)
                    lost = gone if lost is None else [s for s in lost if s in gone]
            if kind == "json" and fine:
                break
    except Unknown:
        return []
    if befores is None:
        fine = True
    lines = []
    if kind == "json":
        if now["json"] and fine:
            line, column, why = now["json"]
            lines.append("%s is not valid JSON: %s at line %d column %d" % (path, why, line, column))
        return lines
    if now["fence"] and fine:
        lines.append("%s has a code fence left open: the fence at line %d is never closed" % (path, now["fence"]))
    if lost:
        lines.append("%s lost %d block header(s): %s" % (path, len(lost), ", ".join(lost)))
    if kind == "handoff" and not now["premises"] and (befores is None or premises):
        lines.append("%s has no `## Working premises` heading" % path)
    return lines


def targets(payload, hdir):
    """[(path, kind)] of the files this call writes that the check may judge."""
    tool, tool_input = payload.get("tool_name"), payload.get("tool_input")
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else os.getcwd()
    if not isinstance(tool_input, dict):
        return []
    if tool in FILE_TOOLS:
        raw = tool_input.get("file_path")
        path = resolve(raw, cwd) if isinstance(raw, str) else None
        kind = kind_of(path, hdir) if path else None
        return [(path, kind)] if kind else []
    if tool in SHELL_TOOLS and isinstance(tool_input.get("command"), str):
        return [(p, kind_of(p, hdir)) for p in
                shell_paths(tool_input["command"], tool == "PowerShell", cwd, hdir)]
    return []


def check(payload):
    """The additionalContext text for the call, or "" when every file it names is fine."""
    hdir = handoff_dir()
    found = targets(payload, hdir)
    if not found:
        return ""
    fences = None
    if any(kind != "json" for _, kind in found):
        import fence_rule as fences  # noqa: E402  the one home of the fence loops
    lines = []
    for path, kind in found:
        after = read_text(path)
        if after is None:
            continue
        befores, _ = before_states(payload.get("tool_name"), payload.get("tool_input"), after)
        lines += judge(path, kind, after, befores, fences)
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
