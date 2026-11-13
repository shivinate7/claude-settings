#!/usr/bin/env python3
"""After a Bash, PowerShell, Write, Edit or MultiEdit call, names a state file the call left unreadable: a *.json that does not parse, an inbox or handoff .md with a code fence left open, an inbox block header lost, or a handoff with no Working premises heading. It never blocks. After an Edit or MultiEdit it says nothing about a file that was already broken, and it says nothing about a file that is gone (decision state-file-parse-check). Standard library only.

The mistake it stops: a Bash, PowerShell, Write, Edit or MultiEdit call that leaves a state file
broken: a *.json that json.loads rejects, an inbox (*.inbox.md) or handoff (*.md) in the handoff folder
with a code fence left open, an Edit that drops an inbox block header, a handoff with no `## Working
premises` heading. Later hooks and sessions read a broken file, and the break shows turns later.

It never blocks, never reverts and never writes a file. It prints a PostToolUse additionalContext that
names the file, the line and the fault, and exits 0 on every path.

What it reads: only the files the call names.
  - Write, Edit, MultiEdit: the call's file_path, when it is a *.json or a *.md in the handoff folder.
  - Bash, PowerShell: the command is read with the repo's one shell walk (guard_core: heredoc bodies dropped,
    quotes and comments read, `cd` followed, a lone `&` a cut). A path counts only in a write position: a
    redirect target, a `tee` argument, a `sed -i` or `perl -i` operand, the last word of `mv` and `cp`, a
    `truncate` operand, the target of Set-Content, Add-Content, Out-File. It counts only when it is a *.json
    or a *.md in the handoff folder. A read says nothing, even of a state file: it changes nothing, and an
    alarm on each read would repeat until the file is fixed. So `cat bad.json` says nothing. A redirect under
    a background `&` whose file is still empty says nothing: the job has not written yet.
  - The handoff folder is the folder of precompact_handoff.handoff_path, under CLAUDE_CONFIG_DIR.

No false alarm mid-edit: an Edit or MultiEdit rebuilds the before-state from old_string and new_string
(the after-state with new_string put back to old_string). A new_string that occurs more than once, or is
empty, gives one candidate before-state per place it could have been. The check stays silent only when
every candidate was already broken. That silence is for an Edit or MultiEdit alone: a Write or a shell
write is judged as left, so it names a broken file even when the file was broken before. It caps the work (candidates times file size) before it builds any
candidate, builds them one at a time, and stays silent past the cap or when new_string is not in the file.
A file that is gone says nothing: a delete is not a break. A Write or a shell write is judged as left.

Fence rules, one home (hooks/fence_rule.py, which feedback_guard.py also reads): an inbox uses
fence_rule.inbox_scan (parse()'s loop, so this check and the Stop check agree on the inbox); another handoff
.md uses fence_rule.fence_scan (unfenced()'s loop) with the indent capped at three spaces. A fence inside a
JSON string is text: the fence scan never runs on JSON. A *.json whose only fault is a `//` or `/* */` comment,
or a UTF-8 byte order mark, is fine.

Cost: every call in the matcher starts the settings.json filter's shell, with one cat and one grep. The
filter greps only tool_input and exits unless it names `.json` or the handoff folder, so a call that names
neither starts no Python. A call that names one starts one Python, which reads each file it judges, and
imports fence_rule when a .md is judged, and guard_core and guard when a shell call is judged. It reads
the premises prompt at most once and each file it judges once. It writes no file and starts no other process.
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
SED_IN_PLACE = re.compile(r"-[A-Za-z]*i|--in-place")
PERL_IN_PLACE = re.compile(r"-[A-Za-z]*i|--in-place")
# Each PowerShell writer: the flags that name its target, and the flags whose next word is a value, not a path.
POWERSHELL_WRITERS = {"set-content", "add-content", "out-file", "clear-content", "new-item"}
POWERSHELL_PATH_FLAGS = ("-path", "-filepath", "-literalpath", "-pspath")
POWERSHELL_VALUE_FLAGS = ("-value", "-encoding", "-inputobject", "-width", "-stream", "-itemtype", "-name")


def handoff_dir():
    return os.path.dirname(precompact_handoff.handoff_path("x"))


PREMISES = []   # the premises heading matcher, read once per process: _premises_head() opens the prompt file


def premises_head():
    if not PREMISES:
        PREMISES.append(precompact_handoff._premises_head())
    return PREMISES[0]


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


def lone_ampersands(segment):
    """[(text, backgrounded)] for one split_segments segment cut at each lone unquoted `&`, the shell's background
    operator. The `&` of `&>`, `>&`, `2>&1` and `&&` is no cut. A part before a lone `&` runs in the background."""
    import guard_core
    marks = []
    for at, char, quote in guard_core.walk_quotes(segment):
        if char == "&" and not quote:
            before, after = segment[at - 1:at], segment[at + 1:at + 2]
            if before not in (">", "<", "&", "|") and after not in (">", "&"):
                marks.append(at)
    parts, start = [], 0
    for at in marks:
        parts.append((segment[start:at], True))
        start = at + 1
    parts.append((segment[start:], False))
    return parts


def powershell_target(args):
    """The path a PowerShell writer cmdlet names: the value of -Path, -FilePath or -LiteralPath, else its first
    word that is no flag and no flag's value."""
    skip = False
    for at, word in enumerate(args):
        low = word.lower()
        if low in POWERSHELL_PATH_FLAGS:
            return args[at + 1] if at + 1 < len(args) else None
        if skip:
            skip = False
        elif low.startswith("-"):
            skip = low in POWERSHELL_VALUE_FLAGS
        else:
            return word
    return None


def verb_writes(verb, args):
    """The words of `args` that name a file the command `verb` writes. A word that is no state file is dropped
    later by kind_of, so a script word among them does no harm."""
    if verb == "tee" or (verb == "sed" and any(SED_IN_PLACE.fullmatch(w) for w in args if w.startswith("-"))):
        return [w for w in args if not w.startswith("-")]
    if verb == "perl" and any(PERL_IN_PLACE.fullmatch(w.split("=")[0]) for w in args if w.startswith("-")):
        return [w for w in args if not w.startswith("-")]
    if verb in ("mv", "cp"):
        words = [w for w in args if not w.startswith("-")]
        return words[-1:]
    if verb == "truncate":
        out, skip = [], False
        for word in args:
            if skip:
                skip = False
            elif word in ("-s", "--size", "-r", "--reference"):
                skip = True
            elif not word.startswith("-"):
                out.append(word)
        return out
    if verb in POWERSHELL_WRITERS:
        found = powershell_target(args)
        return [found] if found else []
    return []


def shell_paths(command, powershell, cwd, hdir):
    """[(path, backgrounded)] for each file a shell command writes that this check may judge, in order: a redirect
    target, a `tee` argument, a `sed -i` or `perl -i` operand, the last word of `mv` and `cp`, a `truncate`
    operand, and the target of Set-Content, Add-Content, Out-File and the like. The walk is the repo's: heredoc
    bodies are dropped, quotes and comments are read by split_segments, a redirect by guard._redirect_targets, and
    a `cd` is followed by dir_before_segment, so a relative path resolves where the shell was."""
    import guard
    import guard_core
    guard_core.POWERSHELL_CALL[0] = powershell
    text = guard_core.strip_heredoc_bodies(command)
    ends = []
    segments = guard_core.split_segments(text, ends)
    found = {}
    for number, segment in enumerate(segments):
        if not segment.strip():
            continue
        where = guard_core.dir_before_segment(segments, number, cwd, ends) or cwd
        for part, background in lone_ampersands(segment):
            words = list(guard._redirect_targets(part))
            tokens = guard_core.segment_tokens(guard_core.strip_redirections(part)) or []
            for at in guard_core.command_indexes(tokens):
                words += verb_writes(os.path.basename(tokens[at]).lower(), tokens[at + 1:])
            for word in words:
                path = resolve(word, where)
                if path is not None and kind_of(path, hdir):
                    found[path] = found.get(path, True) and background
    return list(found.items())[:MAX_PATHS]


def read_text(path):
    """The file's text, or None when it is missing, too big, or not UTF-8: the check then says nothing."""
    try:
        if not os.path.isfile(path) or os.path.getsize(path) > MAX_BYTES:
            return None
        with open(path, "rb") as handle:
            return handle.read().decode("utf-8-sig")  # a UTF-8 byte order mark is no break
    except (OSError, ValueError):
        return None


def blank_comments(text):
    """`text` with each `//` and `/* */` comment outside a string replaced by spaces, newlines kept, so a position in
    the result is a position in the text."""
    out, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
            i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("".join(c if c == "\n" else " " for c in text[i:j]))
            i = j
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def json_fault(text):
    """(line, column, why) when json.loads rejects the text, else None. A file whose only fault is a `//` or
    `/* */` comment (a tsconfig.json) is fine: the reader that wrote it takes comments."""
    try:
        json.loads(text)
        return None
    except json.JSONDecodeError:
        pass
    except Exception:  # a RecursionError on deep nesting: not a verdict
        return None
    try:
        json.loads(blank_comments(text))
    except json.JSONDecodeError as error:
        return error.lineno, error.colno, error.msg
    except Exception:
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
            "premises": premises_head().search(text) is not None}


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
    """[(path, kind, backgrounded)] of the files this call writes that the check may judge."""
    tool, tool_input = payload.get("tool_name"), payload.get("tool_input")
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else os.getcwd()
    if not isinstance(tool_input, dict):
        return []
    if tool in FILE_TOOLS:
        raw = tool_input.get("file_path")
        path = resolve(raw, cwd) if isinstance(raw, str) else None
        kind = kind_of(path, hdir) if path else None
        return [(path, kind, False)] if kind else []
    if tool in SHELL_TOOLS and isinstance(tool_input.get("command"), str):
        try:
            return [(p, kind_of(p, hdir), background) for p, background in
                    shell_paths(tool_input["command"], tool == "PowerShell", cwd, hdir)]
        except ImportError:
            return []
    return []


def check(payload):
    """The additionalContext text for the call, or "" when every file it names is fine."""
    hdir = handoff_dir()
    found = targets(payload, hdir)
    if not found:
        return ""
    fences = None
    if any(kind != "json" for _, kind, _ in found):
        import fence_rule as fences  # noqa: E402  the one home of the fence loops
    lines = []
    for path, kind, background in found:
        after = read_text(path)
        if after is None or (background and not after.strip()):  # a background job's redirect may not have written yet
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
