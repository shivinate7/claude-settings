"""The guard's cite family: the cite rules, with lane-by-slug and scratchpad-commit-msg-owner.

guard.py is the only entry point, and it calls these checks in its fixed order (`judge`, at the
commit and PR message check). Other files reach these names through `guard`.

Rule index:

  cite-by-id          deny. A commit message or PR body that cites a record by its path.
  lane-by-slug         deny. A commit message or PR text that names a lane by a session number.
                       (lane-by-slug)
  scratchpad-commit-msg-owner  deny. A commit from an agent's call whose -F message file resolves
                       into any session's scratchpad. `-F -`, `-m`, an orchestrator's call and a file
                       elsewhere pass. (scratchpad-commit-msg-owner)
"""
import itertools
import json
import os
import re

from guard_core import (
    _absolute, _segment_git_c_target, dir_before_segment, heredoc_heads, norm, own_heredoc_bodies, record, segment_tokens,
    shell_abs,
)
from guard_shared_tree import in_any_session_scratchpad
from guard_merge import gh_call_of, git_call_of, settings_roots
from guard_env import is_env
from guard_rm_var import _rm_values


def _unexpanded(path) -> bool:
    """True when a path holds a variable or a substitution: the shell's value is not this hook's."""
    return any(mark in path for mark in "$%`")


# ---- a message that cites a record by path
RECORD_LAYOUT_FILE = os.path.join("lint", "layout.json")   # lint/check_layout.py: equals lint/layout.py LAYOUT_FILE
_RECORD_PATTERN = []


def record_folders(text):
    """The record folders a cite may not name, from the text of lint/layout.json: each kind marked
    `"record": true`, at its layout path and, when the layout keeps one, its legacy path too (a repo
    may sit on either). Raises when the text is not a layout, and the caller reads that as unread."""
    data = json.loads(text)
    legacy = data.get("legacy") or {}
    found = []
    for kind in data["kinds"].values():
        if isinstance(kind, dict) and kind.get("record") is True and isinstance(kind.get("path"), str):
            for folder in (kind["path"], legacy.get(kind["path"], kind["path"])):
                folder = folder.strip("/")
                if (folder and folder not in found
                        and re.fullmatch(r"[\w.-]+(?:/[\w.-]+)*", folder)):
                    found.append(folder)
    return found


def record_path_pattern():
    """The pattern for a repo-root record path, or None when the record folders cannot be read.

    The folders are the record kinds of lint/layout.json, read from the file. A path counts only at
    the START of a word: after a space, quote, bracket, `=` or `*` (markdown bold), with an
    optional `./`. A URL and
    `lint/decisions/x.md` have a `/` or a word before the folder, so they are not repo-root record
    paths and stay allowed. A layout path such as `docs/decisions/0001.md` is a record path.
    """
    if _RECORD_PATTERN:
        return _RECORD_PATTERN[0]
    for root in settings_roots():
        try:
            with open(os.path.join(root, RECORD_LAYOUT_FILE), encoding="utf-8") as handle:
                names = record_folders(handle.read(MESSAGE_FILE_MAX))
        except Exception:
            continue
        if names:
            pattern = re.compile(
                r"(?:^|(?<=[\s\"'`(\[<,;=@*]))(?:\./)?(?:" + "|".join(map(re.escape, names))
                + r")/[\w.-]+\.md\b")
            _RECORD_PATTERN.append(pattern)
            return pattern
    return None
DROPS_LINES_PATH = re.compile(r"(?im)^(drops-lines[ \t]*:[ \t]*)(\S+)(?=[ \t]+--[ \t]+\S)")
MESSAGE_VALUE_FLAGS = {"--message", "--body"}
MESSAGE_FILE_FLAGS = {"--file", "--body-file"}
TITLE_FLAGS = {"--title", "--subject"}
MESSAGE_FILE_MAX = 64 * 1024

CITE_REASON = (
    "Rule (Git): this message cites a record by its path. A record is cited by its id, with a "
    "short gloss, like \"D12, short titles for records\". "
    "Remedy: write the id the record carries, or its slug while the number is unclaimed, "
    "and leave the folder and the file extension out. Only a commit's last-paragraph trailer "
    "`Drops-lines: <path> -- <reason>` may name a path. "
    "(rule git-cite-by-id, cite a record by its id, never by its path)"
)


# The short flags of each act, from `git commit -h` and `gh pr <act> --help`. "text" and "file"
# carry the message, "title" a gh title or squash subject. "value" takes a value that is no message,
# glued or the next argument (`-Bmain`, `-B main`), and "glued" takes only a glued one (`-uno`). A
# letter not named takes no value, so the walk over a cluster goes on past it (`-am x`, `-db x`).
# In gh, `-m` is a milestone, or a merge with no value: never a message.
SHORT_FLAGS = {
    "commit": dict(m="text", F="file", C="value", c="value", t="value", u="glued", S="glued"),
    "create": dict(b="text", F="file", t="title", a="value", B="value", H="value", l="value",
                   m="value", p="value", r="value", R="value", T="value"),
    "edit": dict(b="text", F="file", t="title", B="value", m="value", R="value"),
    "merge": dict(b="text", F="file", t="title", A="value", R="value"),
}


def message_sources(args, act, titles=False):
    """Return (texts, files, stdin) the message flags of a commit or PR call carry.

    `texts` are the inline values, `files` the named files, `stdin` True for `-F -`. Reads a long
    flag (`--message x`, `--message=x`) or any unique prefix of one of at least four characters
    (git takes `--mess=x`), and a short cluster such as `-am x`, `-amx`, `-mx`, `-m=x`, `-bx`,
    `-Fx`: the walk reads each letter of `act`'s SHORT_FLAGS until one takes a value, and what
    follows it is the value. A letter whose value is no message ends the walk, so `-BmN20` (base
    `mN20`) holds no message. `titles` also reads `--title`, `--subject` and `-t`, which are a gh call's title or squash
    subject (a commit's `-t` is a template file, so a commit never passes it).
    """
    texts, files, stdin = [], [], False
    names = MESSAGE_VALUE_FLAGS | MESSAGE_FILE_FLAGS | (TITLE_FLAGS if titles else set())
    index = 0
    while index < len(args):
        arg = args[index]
        index += 1
        name = value = None
        if arg.startswith("--"):
            flag, equals, glued = arg.partition("=")
            hits = [n for n in names if n == flag] or \
                [n for n in names if len(flag) >= 4 and n.startswith(flag)]
            if len(hits) != 1:
                continue
            name = hits[0]
            value = glued if equals else None
        elif re.match(r"^-[A-Za-z]", arg):
            for pos, letter in enumerate(arg[1:], 1):
                role = SHORT_FLAGS[act].get(letter)
                if role == "title":
                    role = "text" if titles else "value"
                if role is None:
                    continue
                rest = arg[pos + 1:]
                if role in ("text", "file"):
                    name = "--file" if role == "file" else letter
                    value = (rest[1:] if rest.startswith("=") else rest) if rest else None
                elif role == "value" and not rest:
                    index += 1   # its value is the next argument, never a flag
                break
        if name is None:
            continue
        if value is None:
            value = args[index] if index < len(args) else ""
            index += 1
        if name not in MESSAGE_FILE_FLAGS:
            texts.append(value)
        elif value == "-":
            stdin = True
        else:
            files.append(value)
    return texts, files, stdin


UNREAD_MARK = "\0unread:"
UNREAD_REASON = (
    "Rule (Git): the message file could not be read, so the guard cannot tell whether it cites a "
    "record by its path. "
    "Remedy: pass the message inline, or name a file this directory can read. "
    "(decision cite-by-id-refuses-unread-file, an unread message file is refused, not passed)"
)


SCRATCH_MSG_REASON = (
    "Rule (Git): this commit takes its message from a file in a folder that every agent of the session "
    "shares, so the file may hold another agent's message and the commit would carry it. "
    "Remedy: pass your own message with `-F -` and a heredoc, or with `-m`. "
    "(decision scratchpad-commit-msg-owner, an agent commits the message it wrote itself)"
)


_SCRATCH_EXPANSION = re.compile(r"\$(?:\{(\w+)\}|(\w+))")


def scratchpad_commit_file(segments, number: int, cwd: str, ends, scope: str) -> str:
    """Return the first message file of this commit segment that resolves into any session's
    scratchpad, else ''. The path alone decides, never the file's text, and a link is judged by the
    file it resolves to. A relative path is read from the directory the shell is in when the segment
    runs (`dir_before_segment`, then the call's own `-C`); a name `scope` binds to literals is
    expanded (`_rm_values`), and any other variable stays as the environment gives it. When that
    directory cannot be told, only an absolute path is judged."""
    segment = segments[number]
    call = git_call_of(segment)
    if call is None or call[0] != "commit":
        return ""
    where = dir_before_segment(segments, number, cwd, ends)
    tokens = segment_tokens(segment)
    named = _segment_git_c_target(tokens) if tokens else None
    if named is not None:
        where = None if _unexpanded(named) else shell_abs(named, where)
    values = _rm_values(scope)
    for name in message_sources(call[1], "commit")[1]:
        names = sorted({a or b for a, b in _SCRATCH_EXPANSION.findall(name) if values.get(a or b)})
        picks = list(itertools.product(*(values[n] for n in names)))[:64]
        for pick in picks or [()]:
            mapping = dict(zip(names, pick))
            path = _SCRATCH_EXPANSION.sub(lambda m: mapping.get(m.group(1) or m.group(2), m.group(0)), name)
            absolute = _absolute(path, where)
            if os.path.isabs(absolute) and in_any_session_scratchpad(os.path.normpath(absolute)):
                return name
    return ""


def heredoc_offsets(segments, ends, bodies_kept=True):
    """Return, for each segment, the count of heredoc headers ahead of it (own_heredoc_bodies's
    `before`). A line inside a body is no header: `x = 1 << y` in `python3 - <<'EOF'` would shift the
    count and make the commit after it read the wrong body. A body runs from the line after its
    header, to a segment that is its delimiter.
    `bodies_kept` is false when the segments come from a command whose bodies were stripped: no body is in them to skip."""
    offsets, heads, queue, reading = [], 0, [], False
    for segment, end in zip(segments, ends):
        offsets.append(heads)
        if reading:
            if segment.strip() == queue[0]:
                queue.pop(0)
                reading = bool(queue)
        else:
            found = [delimiter for _, delimiter in heredoc_heads(segment)[0]]
            heads += len(found)
            # a body that opens and closes inside one quoted segment (`-m "$(cat <<EOF ... EOF`) is whole
            queue += [d for d in found if not any(line.strip() == d for line in segment.split("\n")[1:])]
            reading = bodies_kept and bool(queue) and end == "\n"
    return offsets


def message_texts(segment: str, raw: str, where: str, before: int, titles: bool = False):
    """Return (is_commit, texts, unread) for a `git commit` or `gh pr create|edit` segment, or None
    when the segment is neither. `titles` also takes `gh pr merge`, whose squash subject and body
    become a commit on main. `unread` is the name of a message file that could not be read, else
    ''. An unread message is not a clean one.

    A heredoc body belongs to the act only when the segment itself carries the `<<` header, so a
    heredoc that writes a record file never counts. `before` is the count of heredoc headers in the
    segments ahead of this one (own_heredoc_bodies).
    """
    call = git_call_of(segment)
    if call is not None:
        if call[0] != "commit":
            return None
        args = call[1]
    else:
        rest = gh_call_of(segment)
        acts = (["create"], ["edit"]) + ((["merge"],) if titles else ())
        if rest is None or rest[:1] != ["pr"] or rest[1:2] not in acts:
            return None
        args = rest[2:]
    act = "commit" if call is not None else rest[1]
    texts, files, stdin = message_sources(args, act, titles=titles and call is None)
    for name in files:
        if is_env(name):
            continue   # never opened here: the environment-file rule judges it, and refuses
        try:
            with open(os.path.normpath(_absolute(name, where)), encoding="utf-8",
                      errors="replace") as handle:
                texts.append(handle.read(MESSAGE_FILE_MAX))
        except Exception:
            return call is not None, texts, name   # unknown, never a pass
    if "<<" in segment:
        texts.extend(own_heredoc_bodies(segment, raw, before))
    return call is not None, texts, ""


def cited_record_path(segment: str, raw: str, where: str, before: int) -> str:
    """Return the first record path a commit message or PR body cites, else ''. A message file
    that cannot be read returns UNREAD_MARK + its name.

    Acts: `git commit` and `gh pr create|edit`.
    """
    read = message_texts(segment, raw, where, before)
    if read is None:
        return ""
    is_commit, texts, unread = read
    if unread:
        return UNREAD_MARK + unread
    pattern = record_path_pattern()
    if pattern is None:
        # An unread folder list is logged, as every unread subject is, and the rule stands down.
        record("Bash", "noted", "subject-unread", "cite-by-id: record folders unread")
        return ""
    if is_commit:
        # Owner ruling 2026-10-12: a commit's trailer `Drops-lines: <path> -- <reason>`, the shape
        # lint/check_silent_undo.py reads, may name its path. Git joins -m values as paragraphs and
        # reads trailers from the last one only, never from a lone subject. Only a token that is one
        # whole record path is blanked: `a.md,b.md` stays judged, as the lint keys on the token.
        paras = re.split(r"\n\s*\n", "\n\n".join(texts).strip())
        if len(paras) > 1:
            paras[-1] = DROPS_LINES_PATH.sub(
                lambda m: m.group(1) if pattern.fullmatch(m.group(2)) else m.group(0), paras[-1])
        texts = ["\n\n".join(paras)]
    for text in texts:
        found = pattern.search(norm(text))
        if found:
            return found.group(0)
    return ""


# ---- a message that names a lane by its session number
LANE_NUMBER = re.compile(r"\bN\d{1,3}b?\b")
LANE_QUOTED = re.compile(
    r"^[ \t]*(```|~~~).*?^[ \t]*\1|(?<!`)(`+)(?!`)[^\n]*?(?<!`)\2(?!`)", re.MULTILINE | re.DOTALL)
LANE_REASON = (
    "Rule (Git): this message names a lane by a session number. That number is handed out in one "
    "chat and means nothing outside it. "
    "Remedy: name the lane by its branch slug, like \"lane-number-cite\". A number inside a "
    "backtick code span or a fenced block is quoted text and stays allowed. "
    "(decision lane-by-slug, a lane is named by its branch slug, never by a session number)"
)


def lane_number_named(segment: str, raw: str, where: str, before: int) -> str:
    """Return the first session-number lane name (`N20`) in a commit message, PR body or title, or
    `gh pr merge` subject or body, else ''. Fenced blocks and backtick spans are quoted text and
    skipped. Same text extraction as cite-by-id. An unread message file returns UNREAD_MARK + its
    name: cite-by-id refuses an unread create or edit file first, so this covers merge.
    """
    read = message_texts(segment, raw, where, before, titles=True)
    if read is None:
        return ""
    if read[2]:
        return UNREAD_MARK + read[2]
    for text in read[1]:
        found = LANE_NUMBER.search(LANE_QUOTED.sub(" ", text))
        if found:
            return found.group(0)
    return ""


# INSTALL_ID = "uninstalled"
