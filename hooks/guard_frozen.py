"""The guard's frozen family: a write to the settings, the hooks or the global CLAUDE.md.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import os
import re

import guard_core
from guard_core import (
    HEREDOC_HEADER, REDIRECT, _expanded, _resolved, _split_heredocs, _strip_heredoc_bodies_unconditionally,
    basename, dir_before_segment, heredoc_delimiter, is_powershell, norm, resolve_command, segment_tokens,
    split_segments,
)
from guard_env import _quoted_words


# ------------------------------------------------------------------ the frozen paths
#
# The harness configuration is the owner's. A session that edits its own settings, its own hooks or
# its own CLAUDE.md can grant itself anything, so those files change through a pull request on the
# clone of claude-settings and in no other way.
#
# THE CLONE ITSELF IS NOT FROZEN. `<clone>/settings.json` is the source that the install script
# copies into the config directory, so it must stay editable. The test is that a path is frozen only
# when it sits under the config directory. A file at the root of the clone does not.
#
# A PROJECT'S OWN `.claude/settings.json`, `.claude/settings.local.json`, and `.claude/hooks/*` are
# a SEPARATE, UNFROZEN set (Decision 7: "allow and report"). They decide only that one project's
# session, the owner is often away from the desk, and the edit is not sensitive enough for a hard
# wall. `is_project_config` answers that question; `is_frozen` never does.
CONFIG_FROZEN_FILES = (
    os.path.normcase("settings.json"),
    os.path.normcase("CLAUDE.md"),
)
# This tuple is a literal on purpose, not a read of landed-dirs.txt at the repo root (the
# manifest install.sh and install.ps1 both read). A frozen-path list read from a file shrinks
# to nothing when the file is missing or unreadable, which turns a missing file into a silent
# weakening of a security control. This list must not be shrinkable, so it stays hardcoded here.
# lint/check_landed_dirs.py checks by hand that this set and the manifest agree, `state` (below)
# excepted as a documented guard-only extra.
CONFIG_FROZEN_DIRS = (
    os.path.normcase("hooks"),
    os.path.normcase("lint"),
    os.path.normcase("agents"),
    # janitor/sweep.py deletes branches and worktrees. A session must not rewrite a program that
    # deletes things, same reasoning as hooks/lint/agents, so it lands here too (decision
    # the-janitor-is-one-machine-wide-sweep, the janitor is one machine-wide sweep).
    os.path.normcase("janitor"),
    # bin/ holds the merge shim that every merge runs. Same reasoning as janitor.
    os.path.normcase("bin"),
    # output-styles/ holds the rules for the main session's replies. A session that could rewrite
    # its own style could loosen those rules, same reasoning as agents/.
    os.path.normcase("output-styles"),
    # docs/design/ holds the house rules builders and reviewers read (decision ux-house-rules). A
    # session that could rewrite them could loosen its own review bar, same reasoning as
    # output-styles/. It is two levels deep, so is_frozen matches an entry as a path prefix.
    os.path.normcase("docs/design"),
    # `state` holds the baseline `hooks/config_watch.py` restores a reverted file from. A session
    # that could rewrite the baseline could launder a cap lift into it, so the store is frozen on
    # the same terms as the hooks themselves. Rule 7 needs only the PATH, never the value, so this
    # covers every shape rule 8 misses for want of a readable value: `cp`, `mv` and `sed -i`
    # included. The two shapes that hide the path from PreToolUse, `python3 -c` and a script file,
    # are not covered here and `config_watch.py` reports a lost baseline as unknown, never clear.
    os.path.normcase("state"),
)
# skills/ is NOT frozen whole: a person's own skills under ~/.claude/skills stay writable.
# Only the skills this repo ships are frozen, one name per entry, because a skill's frontmatter
# `allowed-tools` can grant tools without a prompt, so a session that could edit a landed skill
# could grant itself tools the same way it could through a rewritten hook. lint/check_landed_dirs.py
# checks by hand that this set matches the repo's own skills/*/ subdirectories.
CONFIG_FROZEN_SKILLS = (
    os.path.normcase("ci-hygiene"),
    os.path.normcase("compliance-check"),
    os.path.normcase("fresh-prose"),
    os.path.normcase("design-review"),
    os.path.normcase("design-explore"),
    os.path.normcase("impeccable"),
    os.path.normcase("ios-apps"),
    os.path.normcase("plain-english-map"),
    os.path.normcase("project-ops"),
    os.path.normcase("roadmap"),
    os.path.normcase("waiting-page"),
)
# THE LIVE PINNED CHECKOUT IS FROZEN (decision merge-reinstalls-from-main, ruling 1: no work runs in
# the pinned checkout). The links in the config directory load
# from it, so a write there changes what every session runs. The pin is `<clone>-live`, and each
# move leaves a stamped worktree `<clone>-live-<12 hex>`. This suffix is the one copy in Python.
# merge/install_from_main.sh builds the same name (`pin="$clone-live"`) and must stay equal to it.
# A folder counts as a pin only when the clone beside it holds the install script that makes the
# pin, so an unrelated `something-live` folder stays editable.
# A stamped worktree is frozen only while the pin link resolves to it: the install tells a person
# to move an older one aside, and prunes them, so those stay writable.
LIVE_PIN_SUFFIX = "-live"
_LIVE_PIN = re.compile(r"(?P<clone>.+)" + re.escape(LIVE_PIN_SUFFIX) + r"(?P<stamp>-[0-9a-f]{12})?")
_CLONE_MARKER = os.path.join("merge", "install_from_main.sh")
from shared_names import PROJECT_FROZEN_FILES  # noqa: E402  the one home, shared with the config watch
PROJECT_FROZEN_DIR = "/.claude/hooks/"
# THE MAIN MIRROR IS FROZEN TOO. A cloud install whose session checkout is on a branch takes its files from a mirror of
# main at `$HOME/claude-settings-main`, and the CLAUDE.md pointer names it, so a write there changes what every session
# runs. install.sh's MAIN_MIRROR builds the same name and must stay equal to this one.
MAIN_MIRROR_NAME = "claude-settings-main"

FROZEN_REASON = (
    "Rule (configuration): this file decides what a session is allowed to do, so a session "
    "does not change it. "
    "Remedy: edit the clone of claude-settings and open a pull request. "
    "Run the install script after the merge."
)


def _literal_resolved(path: str, cwd: str) -> str:
    """Same reading as `_resolved`, but stops short of following a symlink: `..`, a trailing
    slash and case are normalized, the path's own leaf is not.

    `install.sh` lands every frozen file under the config directory as a symlink INTO the clone
    (`~/.claude/hooks/guard.py -> <clone>/hooks/guard.py`). `_resolved`'s realpath follows that
    link and reports a path that has already left the config directory, which is the live-path
    gap `is_frozen` closes by also checking this literal reading.
    """
    return os.path.normcase(os.path.normpath(_expanded(path, cwd)))


def _in_live_pin(target: str) -> bool:
    """True when the path is the pinned checkout, or sits inside it or inside the stamped worktree
    the pin link points at now."""
    while True:
        parent, name = os.path.split(target)
        found = _LIVE_PIN.fullmatch(name)
        if found:
            clone = os.path.join(parent, found["clone"])
            if os.path.isfile(os.path.join(clone, _CLONE_MARKER)):
                if not found["stamp"]:
                    return True
                pin = os.path.realpath(clone + LIVE_PIN_SUFFIX)
                if os.path.normcase(pin) == os.path.normcase(os.path.realpath(target)):
                    return True
        if not name or parent == target:
            return False
        target = parent


def _in_main_mirror(target: str) -> bool:
    """True when the path is the main mirror folder directly under the home directory, or inside it."""
    root = os.path.normcase(os.path.normpath(os.path.join(os.path.expanduser("~"), MAIN_MIRROR_NAME)))
    return target == root or target.startswith(root + os.sep)


def is_frozen(path: str, cwd: str) -> bool:
    """True when the path is part of the harness configuration under the config directory, or is
    the live pinned checkout (`_in_live_pin`), or the main mirror (`_in_main_mirror`).

    A path is frozen when EITHER its literal spelling (no symlink followed) OR its fully
    resolved spelling (every symlink followed) sits under the config directory. The literal
    reading catches the LIVE path itself, which `install.sh` lands as a symlink into the clone:
    realpath alone follows that link back out and misses it. The resolved reading keeps
    catching a symlink a session creates ELSEWHERE that points INTO the config directory -- a
    symlink is a spelling of the file it points at, same as rule 8's alias case. Case and a
    trailing slash read the same either way, so a `~`, a forward slash and a backslash all
    still read the same on Windows. A skill under `skills/<name>` freezes the same way: a whole
    shipped skill directory lands as one directory symlink, so the literal reading is what
    keeps it frozen too, while a user's own unlisted skill directory stays unfrozen. A
    project's own `.claude` files are a separate, unfrozen set: see `is_project_config`.
    """
    if not path:
        return False
    try:
        literal = _literal_resolved(path, cwd)
        resolved = _resolved(path, cwd)
        literal_root = os.path.normcase(os.path.normpath(guard_core.config_dir()))
        resolved_root = os.path.normcase(os.path.realpath(guard_core.config_dir()))
    except Exception:
        return False
    if _in_live_pin(literal) or _in_live_pin(resolved):
        return True
    if _in_main_mirror(literal) or _in_main_mirror(resolved):
        return True
    for target, root in ((literal, literal_root), (resolved, resolved_root)):
        if not target.startswith(root + os.sep):
            continue
        rel = target[len(root) + 1:]
        parts = rel.split(os.sep)
        if len(parts) == 1 and parts[0] in CONFIG_FROZEN_FILES:
            return True
        if any(rel.startswith(d + os.sep) for d in CONFIG_FROZEN_DIRS):
            return True
        if len(parts) > 1 and parts[0] == os.path.normcase("skills") and parts[1] in CONFIG_FROZEN_SKILLS:
            return True
    return False


def is_project_config(path: str, cwd: str) -> bool:
    """True when the path is a project's own `.claude/settings*.json` or `.claude/hooks/*`.

    Decision 7: allowed in any checkout, never refused. The caller logs the edit as `noted` under
    rule `config-edit` instead of refusing it.
    """
    if not path:
        return False
    try:
        target = _resolved(path, cwd)
    except Exception:
        return False
    posix = norm(target)
    if any(posix.endswith(name) for name in PROJECT_FROZEN_FILES):
        return True
    return PROJECT_FROZEN_DIR in posix


# Commands that change a file named in their arguments. `mv` stays on the list even when the frozen
# path is its source, because guessing wrong on `mv` loses the file. `cp` FROM a frozen path to a
# path outside the frozen set only reads it, and is allowed (`_copy_reads`). Deliberate over-blocking elsewhere, narrow in scope.
#
# The list holds the PowerShell cmdlets (`Set-Content`, `Out-File`, `Add-Content`, `Remove-Item`) as
# well as the POSIX commands. Matching folds case, as PowerShell does.
MUTATING_COMMAND = (
    r"\b(?i:rm|mv|cp|chmod|truncate|tee|install|ln"
    r"|set-content|add-content|clear-content|out-file|new-item|remove-item|move-item|copy-item"
    r"|rename-item|set-itemproperty|ri|rd|rmdir|del|erase|move|copy|ren)\b"
)


# A command that hands its arguments to another program, so a mutating word in them may run.
_RUNS_ITS_ARGUMENTS = {"find", "eval", "exec", "pwsh", "powershell", "cmd"}


def _mutates_as_command(command: str, words) -> bool:
    """True when the segment's own command (`command`, its resolved name) changes the files it names:
    a word of MUTATING_COMMAND or a `mv` or `rm` of the version control tool. A command that runs its
    arguments counts too, as it always did, so `find -exec rm` stays seen. A shell `-c` script is read at
    its own command positions, so `bash -c "pytest -k install t.py"` reads and `bash -c "rm x"` writes."""
    if command in guard_core.INLINE_SCRIPT_SHELLS:
        return _script_mutates(guard_core.inline_script([command, *words]))
    if command in _RUNS_ITS_ARGUMENTS:
        return True
    if command == "git":
        rest = [word for word in words if not word.startswith("-")]
        return any(word in ("mv", "rm") for word in rest[:2])
    return bool(re.fullmatch(MUTATING_COMMAND, command))


# A character that lets a script run text the segment split cannot see: a substitution, a group, a brace,
# or a backslash (an escaped quote or separator the split would read wrongly).
_SCRIPT_RUNS_HIDDEN = re.compile(r"[$`(){}\\]")


def _script_mutates(script: str) -> bool:
    """True when a `sh -c` script may change files through a command of its own. No script found, or one
    with a substitution or group in it, counts as a write, as it always did."""
    if not script or _SCRIPT_RUNS_HIDDEN.search(script):
        return True
    for segment in split_segments(script):
        command, rest = _segment_command([_unquoted(word) for word in _quoted_words(segment, True)])
        # `sed -i` is no mutating word: `writes_to` reads it by its own pattern, so it must get that far.
        if _mutates_as_command(command, rest) or (
                command == "sed" and any(re.match(r"-[a-z]*i\b|--in-place", word) for word in rest)):
            return True
    return False


def writes_to(path: str, cmd: str, command=None, words=()) -> bool:
    """True when the command looks like it writes to the path, rather than merely naming it.

    Two ways to write a named file from a shell: redirect onto it, or hand it to a command that
    mutates its arguments. Everything else is a mention.

    Reading the TARGET of the redirect is what separates
    `echo x > .claude/settings.json` from `cat .claude/settings.json 2>/dev/null`. The second
    redirects to the null device. It is also what stops a redirect elsewhere on the line from
    counting as a write to a path named in a comment.
    """
    target = re.escape(path)
    if re.search(r"\d?>>?\s*['\"]?" + target, cmd):
        return True
    # `command` is the segment's resolved command name, given by a caller that reads a mutating
    # word only in command position (`grep -n install tests/x.py` reads, never writes).
    if command is not None and not _mutates_as_command(command, words):
        return command == "sed" and bool(re.search(r"\bsed\b[^\n;|&]*-i\b[^\n;|&]*" + target, cmd))
    if re.search(MUTATING_COMMAND + r"[^\n;|&]*" + target, cmd):
        return True
    if re.search(r"\bsed\b[^\n;|&]*-i\b[^\n;|&]*" + target, cmd):
        return True
    return False


# VARIABLE INDIRECTION. In `D=~/.claude/state/handoff/x.md; ...; cp "$S/handoff.md" "$D"` the parse
# sees only the word `$D`. `_resolve_vars` (called first by `_shell_write_hit`, which feeds the frozen
# and project-config checks) reads the command once, left to right, as the shell reads it: it splits
# the text into words and quoted spans, keeps a table of simple assignments, and reads each `$D` or
# `${D}` as the value current at that point. The table holds `D=v` at a command's start (a value is
# the whole shell word, so `WT="$BASE"/../lane` is one path), the arguments of `export`, `declare`,
# `typeset`, `local` and `readonly` (`export A=1 D=v`), and a PowerShell `$D = v`. The last assignment
# wins, `unset D` clears it, a use before the assignment stays as written, and single quotes do not
# expand. An unassigned variable stays unresolved and allowed. `$HOME` reads as `~`:
# `os.path.expandvars` leaves it literal when HOME is unset (the Windows default), so a literal
# `$HOME/.claude/...` target was allowed.
# Text is not code, and code is not text. An assignment inside double quotes or after a `#` comment
# is text, and a lone apostrophe in double quotes opens no span, because quotes are read in pairs
# from the left. An unmated quote is one ordinary character, so the text after it is still read as
# code, the fail-closed side: a variable read as code resolves, one read as text stays as written.
# The body of a heredoc with a quoted delimiter is text to the shell, so its quotes are read in the
# body alone and never pair with a quote after it. The body of `$(...)` or backticks is a command
# even inside double quotes, and so is the argument of `eval "..."`. A prefix assignment
# (`S=x cmd "$S"`) sets the variable for that one command: the command's own words and all later
# text see the value from before it. A subshell `( ... )`, `$( ... )` or backtick pair gives its
# assignments back where it ends.
# A redirect (`>/dev/null`, `2>f`, `<<'EOF'`) and the name after `function` leave the command's start
# as it was, so `D=x >/dev/null` still sets D. An unquoted `$D` whose value holds two words is an
# ambiguous redirect target that writes nothing, so it stays as written there (unless IFS is set).
# RESIDUAL GAP: a value from `$(...)`, backticks, `read`, `${D:-x}`, a loop variable, `eval '...'`, or
# an interpreter (`python -c`) is not resolved, nor is a variable set in a different tool call. An
# assignment in a pipeline stage or a background job (`D=x | cat`, `D=x &`) is kept here, though the
# shell runs it in a subshell and keeps nothing, so a later `$D` can read a value the shell does not.
# Fixing these needs a shell parser, not this one pass.
_WORD_STOP = frozenset(" \t\r\n;&|()`")
_ASSIGN_WORD = re.compile(r"([A-Za-z_]\w*)(\+?)=")
_VAR_USE = re.compile(r"\$(?:([A-Za-z_]\w*)|\{([A-Za-z_]\w*)\})")
_PS_NAME = re.compile(r"\$[A-Za-z_]\w*")
_PS_EQUALS = re.compile(r"[ \t]*=(?!=)[ \t]*")
# A redirect operator at the start of a word (`>`, `>>`, `2>`, `>&`, `>|`, `<`, `<&`, `<>`).
_REDIRECT_OP = re.compile(r"\d*(?:>>|>&|>\||<&|<>|[<>])")
# Whitespace between two non-blank characters: the shell splits such a value into two words.
_TWO_WORDS = re.compile(r"[^ \t\n][ \t\n]+[^ \t\n]")
# Words after which the next word is still a command's start (`{ D=x; }`, `then D=x`, `eval D=x`).
_COMMAND_STARTERS = frozenset((
    "{", "!", "if", "then", "elif", "else", "do", "while", "until", "time", "eval", "function"))
_DECLARERS = frozenset(("export", "declare", "typeset", "local", "readonly"))
_NEST_LIMIT = 20   # quotes nested in `$(...)` nested in quotes; deeper reads as plain text


def _subst_end(text: str, j: int, depth: int) -> int:
    """Index of the `)` that ends the `$(` body starting at `j`, or -1 when it has no mate."""
    if depth > _NEST_LIMIT:
        return -1
    level, n = 1, len(text)
    while j < n:
        c = text[j]
        if c == "\\":
            j += 2
            continue
        if c == "'":
            j = text.find("'", j + 1)
            if j < 0:
                return -1
        elif c == '"':
            j = _dq_end(text, j + 1, depth + 1)
            if j < 0:
                return -1
        elif c == "(":
            level += 1
        elif c == ")":
            level -= 1
            if level == 0:
                return j
        j += 1
    return -1


def _dq_end(text: str, j: int, depth: int = 0) -> int:
    """Index of the `"` that closes a double-quoted span whose text starts at `j`, or -1."""
    n = len(text)
    while j < n and text[j] != '"':
        if text[j] == "\\":
            j += 2
        elif text[j] == "$" and text.startswith("(", j + 1):
            j = _subst_end(text, j + 2, depth)   # no mate for the body: no mate for the quote either
            if j < 0:
                return -1
            j += 1
        else:
            j += 1
    return j if j < n else -1


def _read_word(cmd: str, i: int):
    """(end, parts) of the shell word at `i`. `parts` are (kind, text): kind `p` plain, `d` the inside
    of a double-quoted span, `s` the inside of a single-quoted span. Quotes are read in pairs; a quote
    with no mate is an ordinary character."""
    parts, plain, n = [], [], len(cmd)

    def flush():
        if plain:
            parts.append(("p", "".join(plain)))
            plain.clear()

    while i < n and cmd[i] not in _WORD_STOP:
        c = cmd[i]
        if c == "\\" and i + 1 < n:
            plain.append(cmd[i:i + 2])
            i += 2
            continue
        if c == "'":
            j = cmd.find("'", i + 1)
            if j >= 0:
                flush()
                parts.append(("s", cmd[i + 1:j]))
                i = j + 1
                continue
        elif c == '"':
            j = _dq_end(cmd, i + 1)
            if j >= 0:
                flush()
                parts.append(("d", cmd[i + 1:j]))
                i = j + 1
                continue
        elif c == "$" and cmd.startswith("{", i + 1):
            j = cmd.find("}", i + 2)
            if j >= 0:
                plain.append(cmd[i:j + 1])
                i = j + 1
                continue
        plain.append(c)
        i += 1
    flush()
    return i, parts


def _expand(text: str, table: dict, as_target: bool = False) -> str:
    """`text` with each `$VAR` read. `as_target` is an unquoted redirect target: a value of two words
    is an ambiguous redirect that writes nothing, so its variable stays as written (fail closed when
    IFS is set, which can change where the shell splits)."""
    splits = as_target and "IFS" not in table

    def read(use):
        value = table.get(use.group(1) or use.group(2))
        return use.group(0) if value is None or (splits and _TWO_WORDS.search(value)) else value
    return _VAR_USE.sub(read, text)


def _dq_text(text: str, table: dict, depth: int = 0) -> str:
    """Double-quoted text with each `$VAR` read. A `$(...)` or backtick body is a command, read on a copy
    of the table so its assignments end with it. Past `_NEST_LIMIT` levels a body is plain text."""
    if depth >= _NEST_LIMIT:
        return _expand(text, table)
    out, i, start, n = [], 0, 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "$" and text.startswith("(", i + 1):
            end, skip = _subst_end(text, i + 2, 0), 2
        elif c == "`":
            end, skip = text.find("`", i + 1), 1
        else:
            i += 1
            continue
        if end < 0:
            i += 1
            continue
        out.append(_expand(text[start:i], table))
        out.append(text[i:i + skip] + _resolve_into(text[i + skip:end], dict(table), depth + 1)[0] + text[end])
        i = start = end + 1
    out.append(_expand(text[start:], table))
    return "".join(out)


def _rebuild(parts, table: dict, as_script: bool = False, depth: int = 0, as_target: bool = False):
    """(the word's text with each `$VAR` outside single quotes read as its value, the table after it).
    `as_script` reads a double-quoted span as a command that runs here (`eval "D=x"`). `as_target` is
    a redirect target word (see `_expand`)."""
    out = []
    for kind, text in parts:
        if kind == "s":
            out.append("'" + text + "'")
        elif kind == "d" and as_script and depth < _NEST_LIMIT:
            text, table = _resolve_into(text, table, depth + 1)
            out.append('"' + text + '"')
        elif kind == "d":
            out.append('"' + _dq_text(text, table, depth) + '"')
        else:
            out.append(_expand(text, table, as_target))
    return "".join(out), table


def _value_of(parts, table: dict) -> str:
    """The value a shell gives an assignment's word: quotes removed, `$VAR` read, escapes dropped."""
    pieces = []
    for kind, text in parts:
        if kind == "s":
            pieces.append(text)
        elif kind == "d":
            pieces.append(re.sub(r'\\(["\\$`])', r"\1", _expand(text, table)))
        else:
            pieces.append(re.sub(r"\\(.)", r"\1", _expand(text, table), flags=re.S))
    return "".join(pieces)


def _assign(table: dict, name: str, plus: str, parts, opens_group: bool) -> None:
    """Set `name` in `table` to the value `parts` read as. A value that holds `$` or a backtick, or that is
    cut by a `(` or backtick (an array, `$(...)`), is not known: the name forgets its old value too."""
    value = _value_of(parts, table)
    if "$" in value or "`" in value or opens_group:
        table.pop(name, None)
    elif plus:
        if name in table:
            table[name] += value
    else:
        table[name] = value


def _heredoc_at(parts) -> int:
    """Offset in the word of an unquoted `<<` that opens a heredoc (not `<<<`), or -1."""
    offset = 0
    for kind, text in parts:
        if kind != "p":
            offset += len(text) + 2   # the quotes around the span
            continue
        found = re.search(r"(?<!<)<<(?!<)", text)
        if found:
            return offset + found.start()
        offset += len(text)
    return -1


def _heredoc_end(cmd: str, start: int, delimiter: str):
    """(index where the delimiter line starts, index where its text ends) for a heredoc body that
    starts at `start`; both are the end of `cmd` when the delimiter never comes."""
    n, pos = len(cmd), start
    while pos < n:
        eol = cmd.find("\n", pos)
        eol = n if eol < 0 else eol
        if cmd[pos:eol].strip() == delimiter:
            return pos, eol
        pos = eol + 1
    return n, n


def _resolve_vars(cmd: str) -> str:
    """Read each `$VAR` or `${VAR}` as the value assigned earlier in the command."""
    return _resolve_into(cmd, {"HOME": "~"})[0]


def _resolve_into(cmd: str, table: dict, depth: int = 0):
    """(`cmd` with each `$VAR` read, the table after it): `_resolve_vars` from a given table."""
    out, stack = [], []   # stack: (table to restore where the group ends, glued to a `$`, closer)
    n, i = len(cmd), 0
    at_start, before, mode = True, None, ""   # before: the table from before this command's assignments
    operand = ""   # "target": the next word names a redirect's file; "name": a function's name
    heredocs = []   # delimiters of the heredocs whose bodies start after the next newline
    while i < n:
        c = cmd[i]
        if c in " \t\r":
            out.append(c)
            i += 1
        elif c == "&" and (cmd[i - 1:i] in ("<", ">") or cmd.startswith(">", i + 1)):
            out.append(c)   # `>&1`, `<&-` and `&>f` are redirects, not a background job
            i += 1
        elif c in ";&|\n":
            out.append(c)
            i += 1
            at_start, before, mode, operand = True, None, "", ""
            while c == "\n" and heredocs:   # a body is text, read in itself: its quotes never pair outward
                body_end, line_end = _heredoc_end(cmd, i, heredocs.pop(0))
                body = cmd[i:body_end]
                out.append(_expand(body, table) if depth >= _NEST_LIMIT
                           else _resolve_into(body, dict(table), depth + 1)[0])
                out.append(cmd[body_end:line_end])
                i = line_end
                if heredocs and cmd.startswith("\n", i):
                    out.append("\n")
                    i += 1
        elif c == "(" or (c == "`" and not (stack and stack[-1][2] == "`")):
            stack.append((dict(table), c == "`" or cmd[i - 1:i] == "$", ")" if c == "(" else "`"))
            out.append(c)
            i += 1
            at_start, before, mode, operand = True, None, "", ""
        elif c == ")" or c == "`":   # `)` ends the nearest `(`; a second backtick ends the open one
            glued = False
            for level in range(len(stack) - 1, -1, -1):
                if stack[level][2] == (")" if c == ")" else "`"):
                    table, glued, _closer = stack[level]
                    del stack[level:]
                    break
            out.append(c)
            i += 1
            at_start, before, mode, operand = not glued, None, "", ""
        elif c == "#":   # a comment: its text is read for uses and holds no assignment
            j = cmd.find("\n", i)
            j = n if j < 0 else j
            out.append(_expand(cmd[i:j], table))
            i = j
        else:
            end, parts = _read_word(cmd, i)
            word = cmd[i:end]
            if operand:   # a redirect's file or a function's name: a word, never a command or assignment
                text, table = _rebuild(parts, table, False, depth, operand == "target")
                out.append(text)
                operand = ""
                i = end
                continue
            at = _heredoc_at(parts)
            if at >= 0:
                header = HEREDOC_HEADER.match(cmd, i + at)
                if header:
                    heredocs.append(heredoc_delimiter(header.group(1))[1])
            redirect = _REDIRECT_OP.match(word)
            if redirect:   # a redirect is no command: it leaves the command's start as it was
                text, table = _rebuild(parts, table, False, depth, True)
                out.append(text)
                if redirect.end() == len(word) or re.fullmatch(r"\d*<<<?-?", word):
                    operand = "target"
                i = end
                continue
            head = _ASSIGN_WORD.match(parts[0][1]) if parts and parts[0][0] == "p" else None
            if head and (at_start or mode == "declare"):
                if at_start and before is None:
                    before = dict(table)
                rest = parts[0][1][head.end():]
                _assign(table, head.group(1), head.group(2), ([("p", rest)] if rest else []) + parts[1:],
                        cmd.startswith(("(", "`"), end))
                out.append(word)
                i = end
                continue
            if head is None and len(parts) == 1 and parts[0][0] == "p" and _PS_NAME.fullmatch(parts[0][1]):
                eq = _PS_EQUALS.match(cmd, end)
                if eq:   # PowerShell `$D = v`. A paren is no scope there, so every level keeps it.
                    vend, vparts = _read_word(cmd, eq.end())
                    for held in [table] + [saved for saved, _glued, _closer in stack]:
                        _assign(held, parts[0][1][1:], "", vparts, cmd.startswith(("(", "`"), vend))
                    out.append(cmd[i:vend])
                    i = vend
                    continue
            if at_start:
                if word in _COMMAND_STARTERS:
                    mode = "eval" if word == "eval" else mode
                    operand = "name" if word == "function" else operand
                    out.append(word)
                    i = end
                    continue
                if before is not None:
                    table, before = before, None   # a prefix assignment reaches only its own command
                at_start = False
                mode = ("declare" if word in _DECLARERS else "unset" if word == "unset"
                        else mode if mode == "eval" else "")
            elif mode == "unset" and re.fullmatch(r"\w+", word):
                table.pop(word, None)
            text, table = _rebuild(parts, table, mode == "eval", depth)
            out.append(text)
            i = end
    return "".join(out), table


# DATA IS NOT A WRITE. A command that only names the cap key or a frozen path as text is not asked
# about, and no real write passes. A list of "reader" commands does not converge (git, gh, rg, sort
# and python run text they are given), so quoted text is data in TWO places only (review option A):
#  (a) the value of a named message flag: `git [-C dir] commit` -m, --message or -F, and
#      `gh pr|issue create|edit` --title, --body, -t or -b;
#  (b) a quoted argument of a pure printer (`echo`, `printf`, `cat`, `grep`, `wc`, `jq`).
# Either is data only when its output runs nowhere: a pipe only into a printer (an interpreter as a
# pipe target fails closed, as on main: it may run the text, and `python run.py` may read it), and
# a write to a file only when every segment of the command is a printer or
# a `cd`. A redirect target is never data. All other text stays in view. Each segment is judged
# alone, so a leading `cd dir &&` or `Set-Location dir;` does not change the answer.
# FAIL CLOSED. No text is data when the command holds, outside single quotes, a backtick, `$(`,
# `$'`, `$"`, `<(`, `>(`, a backslash before a quote, an unmated quote, a `<#` (a PowerShell block
# comment, which hides its quotes), or anywhere a smart quote U+2018 to U+201E (PowerShell reads it
# as a quote, even inside single quotes): the shell may then read its quotes differently from the
# scanner. Bash text is read by bash's own rules: inside double quotes `\"` and `\\` are literal, and
# a smart quote is an ordinary character. A newline and a `#` inside quotes are text. A backtick and
# `$(` inside double quotes stay live and stay closed. PowerShell text keeps every mark above. A segment with an unquoted `&`, `(`, `)`, `{` or `}`
# holds no data: a background job, a call operator, a PowerShell group such as `(iex "...")`.
# A word in view that holds a quote is read in whole: the text of each quote is its own words, so
# `system("sh", "-c", "tee P")` shows its `tee P`.
# RESIDUAL GAPS: a write made by a program's own code;
# `cat <<EOF | sh`, an eval of a heredoc, a subshell `( ... > P)` and `"$( ... )"`; `sort -o P`,
# `git diff --output=P`, `git config --file P`, `>| P` and a quoted redirect target with a space.
# Main missed these too.
_PRINTERS = frozenset(("echo", "printf", "cat", "grep", "wc", "jq"))
_QUIET = _PRINTERS | {"cd", "set-location"}
_MESSAGE_FLAGS = {"git": ("-m", "--message", "-F"), "gh": ("--title", "--body", "-t", "-b")}
_GH_MESSAGE_CALLS = frozenset((
    ("pr", "create"), ("pr", "edit"), ("issue", "create"), ("issue", "edit")))
_UNSAFE_MARK = re.compile(r"""`|\\["']|\$['"(]|[<>]\(|<#""")
# PowerShell reads these as quote marks. They end or open a quote that the scanner does not see.
_SMART_QUOTES = frozenset("\u2018\u2019\u201a\u201b\u201c\u201d\u201e")
_GROUP_MARK = re.compile(r"[&(){}]")
_FD_DUP = re.compile(r"\d*>&\d*|&>")
_COMMAND_WORD_HOLDS = re.compile(r"""['"$`(){}\[\]!&]""")
# A command that can run stored text, or rename what a printer is, makes no text data (review r2
# H2, H3): `eval`, `printf -v`, a command word built from a variable (`$D`, `"${D}"`), a `${F@P}`
# operator (even inside double quotes), and a function, an alias or a PATH change, which can make
# `cat` or `echo` run its input. Read on the text outside quotes, so a message may name them.
_RENAMES_A_COMMAND = re.compile(
    r"\b(?:eval|function|alias|set-alias|new-alias|sal|nal|hash)\b|\(\s*\)|(?<![-\w])path\s*\+?=",
    re.IGNORECASE)
_PARAM_OPERATOR = re.compile(r"\$\{[^}]*@")
_ASSIGNMENT = re.compile(r"[A-Za-z_]\w*\+?=")
_REDIRECT_CHARS = frozenset("0123456789<>&|")
_NULL_TARGETS = ("/dev/null", "nul", "$null")
# A descriptor dup or close after a redirect (`&1`, `&2-`, `&-`) names a descriptor, not a file.
# Digits only: `>&name` writes the file `name`.
_DESCRIPTOR = r"&(?:\d+-?|-)"


def _scan(segment: str):
    """(fail closed?, the segment's text outside quotes). Single-quoted text is skipped whole, so a
    `\\"` in a JSON sample there is plain text. In bash text, inside double quotes, `\\"` and `\\\\` are
    one literal character each and a smart quote is an ordinary one; a backtick and `$(` there are
    live code, so they still fail closed. PowerShell text keeps every smart quote and backslash mark
    as a fail-closed form."""
    plain, quote = [], ""
    bash = not is_powershell(segment)
    index, length = 0, len(segment)
    while index < length:
        char = segment[index]
        if char in _SMART_QUOTES and not bash:   # PowerShell ends a string at one, even in '...'
            return True, ""
        if quote == "'":
            quote = "" if char == "'" else quote
        elif bash and quote == '"' and char == "\\" and segment[index + 1:index + 2] in ('"', "\\"):
            index += 2   # an escaped pair is text and neither opens nor closes a quote
            continue
        elif _UNSAFE_MARK.match(segment, index):
            return True, ""
        elif char in "'\"":
            quote = "" if quote == char else (quote or char)
        elif not quote:
            plain.append(char)
        index += 1
    return bool(quote), "".join(plain)   # a quote with no mate: fail closed


def _name(word: str) -> str:
    """The command name of a word, or '' when the word is quoted or built from a variable."""
    if _COMMAND_WORD_HOLDS.search(word):
        return ""
    return word.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower().removesuffix(".exe")


def _is_redirect(word: str) -> bool:
    return bool(word) and set(word) <= _REDIRECT_CHARS


def _kind(words, plain: str) -> str:
    """'printer', 'message', 'cd' or '' for one segment."""
    if not words or _GROUP_MARK.search(_FD_DUP.sub("", plain)):
        return ""
    name = _name(words[0])
    if name in _PRINTERS and re.search(r"[/\\]", words[0]):
        return ""   # `./cat` or `b/echo` is a local program, not the printer (review r2 H3)
    if name in _QUIET:
        return "cd" if name not in _PRINTERS else "printer"
    if name == "git":
        index = 1
        while words[index:index + 1] == ["-C"]:
            index += 2
        return "message" if words[index:index + 1] == ["commit"] else ""
    if name == "gh" and tuple(words[1:3]) in _GH_MESSAGE_CALLS:
        return "message"
    return ""


def _writes_a_file(words) -> bool:
    """True when the segment redirects output onto a file, not a null device or a descriptor."""
    for index, word in enumerate(words):
        if ">" in word and _is_redirect(word) and not word.endswith("&"):
            target = words[index + 1].strip("'\"").lower() if index + 1 < len(words) else ""
            if target not in _NULL_TARGETS and not re.fullmatch(_DESCRIPTOR, target):
                return True
    return False


def _data_words(kind: str, words):
    """The indexes of the words that are data in a printer or message segment."""
    data = set()
    if kind == "printer":
        for index in range(1, len(words)):
            if ("'" in words[index] or '"' in words[index]) and not _is_redirect(words[index - 1]):
                data.add(index)
        return data
    name = _name(words[0])
    flags = _MESSAGE_FLAGS[name]
    for index, word in enumerate(words):
        if word in flags or (name == "git" and re.fullmatch(r"-[A-Za-z]*m", word)):
            if index + 1 < len(words) and not _is_redirect(words[index + 1]):
                data.add(index + 1)
        elif any(word.startswith(flag + "=") if flag.startswith("--")
                 else word.startswith(flag) and len(word) > 2 for flag in flags):
            data.add(index)   # a glued value: --body=..., -m"..."
    return data


def _unquoted(word: str) -> str:
    """The shell word after quote removal: `a/'b.py'` reads `a/b.py`. A quote inside the other
    kind of quote is text. The `$` of an unquoted `$'...'` or `$"..."` goes with the quote.
    RESIDUAL GAP: a backslash escape inside `$'...'` (hex or octal) is not decoded."""
    out, quote = [], ""
    for index, char in enumerate(word):
        if char == quote:
            quote = ""
        elif not quote and char in "'\"":
            quote = char
        elif not (not quote and char == "$" and word[index + 1:index + 2] in ("'", '"')):
            out.append(char)
    return "".join(out)


def _words_of(word: str):
    """The words a word stands for with its quotes read: the word itself after quote removal, that
    text split as the shell splits it (a `bash -c` script), and each quote's text as its own words
    (cut at a paren too, so `'$(echo 1 > P)'` shows `P`)."""
    inner = _unquoted(word)
    out = [inner] + [_unquoted(w) for w in _quoted_words(inner)]   # a quoted script, read again
    for piece in re.split(r"""['"()]""", word):
        out.extend(REDIRECT.sub(r" \1 ", piece).split())
    return out


def _runs_stored_text(segment: str, words, plain: str) -> bool:
    """True when the segment can run text it holds or stores, or rename a printer."""
    if _RENAMES_A_COMMAND.search(plain) or _PARAM_OPERATOR.search(segment):
        return True
    command = next((word for word in words if not _ASSIGNMENT.match(word)), "")
    if "$" in command:
        return True
    return _name(command) == "printf" and any(word.startswith("-v") for word in words)


# COPY-OUT. `cp SRC... DEST` writes only DEST. Only plain POSIX flags are read (a PowerShell
# `-Destination` fails closed to a deny), and a DEST built from a variable, a glob or a brace fails
# closed too. DEST also counts as hit when it is a directory the predicate hits (`DEST/_`), so a
# frozen file copied into a frozen folder stays refused.
# `l` and `s` (and the long `--link`, `--symbolic-link`, even cut short) make a link, not a copy: a
# later write to the new name writes the frozen file, so those flags are never read as a copy.
_CP_FLAGS = re.compile(r"-[RrfiaHLPpnvuxTS]+|--[a-z][a-z-]*(?:=.*)?|--")
_CP_TARGET = re.compile(r"-[RrfiaHLPpnvuxTS]*t|--target-directory")
_CP_LINK_LONG = ("link", "symbolic-link")
# A redirect to the null device or onto another descriptor writes no file.
_NULL_REDIRECT = re.compile(r"(?:\d*|&)>>?(?:/dev/null|nul|\$null)|\d*>" + _DESCRIPTOR, re.IGNORECASE)
_OPEN_REDIRECT = re.compile(r"\d*>>?|&>>?")
_CP_DEST_UNSAFE = re.compile(r"[$`*?\[{<>]")


def _copy_reads(raw, predicate, cwd):
    """The indexes of the words of a `cp` segment that are only read, else an empty set."""
    words = [_unquoted(word) for word in raw]
    start = next((i for i, word in enumerate(raw) if not _ASSIGNMENT.match(word)), len(raw))
    if _name(raw[start] if start < len(raw) else "") != "cp":
        return set()
    operands, target, index = [], None, start + 1
    while index < len(words):
        word = words[index]
        if _NULL_REDIRECT.fullmatch(word):
            index += 1
            continue
        if words[index:index + 2] in (["&", ">"], ["&", ">>"], [">", "&"]):
            # `&>`, `&>>` and `>&` are one redirect: its `&` is no source, and a file it opens is no destination
            # unless it is unsafe or the predicate hits it. Any other redirect leaves the segment judged.
            out = words[index + 2:index + 3]
            if out and (out[0].lower() in _NULL_TARGETS or re.fullmatch(_DESCRIPTOR, out[0]) or not (
                    _CP_DEST_UNSAFE.search(out[0]) or predicate(out[0], cwd)
                    or predicate(out[0].rstrip("/\\") + "/_", cwd))):
                index += 3
                continue
            return set()
        if _OPEN_REDIRECT.fullmatch(word) and words[index + 1:index + 2] and \
                (words[index + 1].lower() in _NULL_TARGETS or re.fullmatch(_DESCRIPTOR, words[index + 1])):
            index += 2
            continue
        if word != "--" and word.startswith("--") and any(
                name.startswith(word[2:].split("=")[0]) for name in _CP_LINK_LONG):
            return set()
        if _CP_TARGET.fullmatch(word):
            target, index = (words[index + 1] if index + 1 < len(words) else None), index + 2
            if target is None:
                return set()
            continue
        if word.startswith("--target-directory="):
            target = word.split("=", 1)[1]
        elif word.startswith("-t") and len(word) > 2 and word[1] != "-":
            target = word[2:]
        elif _CP_FLAGS.fullmatch(word):
            pass
        elif word.startswith("-") or ">" in word or "<" in word:
            return set()
        else:
            operands.append(index)
        index += 1
    if target is None:
        if len(operands) < 2:
            return set()
        target = words[operands.pop()]
    if not operands or not target or _CP_DEST_UNSAFE.search(target):
        return set()
    if predicate(target, cwd) or predicate(target.rstrip("/\\") + "/_", cwd):
        return set()
    return set(operands)


def _cp_link_source(raw, holds, cwd) -> str:
    """The word of a linking `cp` (`-l`, `-s`, `--link`, `--symbolic-link`, in any cluster) that
    `holds(word, cwd)` accepts, else ''. A link to a frozen file, or to a folder of them, gives the
    new name the frozen file itself, so a later write there writes it. Every operand but a plain
    DEST is judged; with `-t` every operand is, which fails closed."""
    words = [_unquoted(word) for word in raw]
    start = next((i for i, word in enumerate(raw) if not _ASSIGNMENT.match(word)), len(raw))
    if _name(raw[start] if start < len(raw) else "") != "cp":
        return ""
    link = target = False
    operands = []
    for word in words[start + 1:]:
        if word.startswith("--"):
            name = word[2:].split("=")[0]
            link = link or bool(name) and any(full.startswith(name) for full in _CP_LINK_LONG)
            target = target or bool(name) and "target-directory".startswith(name)
        elif word.startswith("-") and len(word) > 1:
            flags, cut, _dir = word[1:].partition("t")
            link = link or bool({"l", "s"} & set(flags))
            target = target or bool(cut)
        elif ">" not in word and "<" not in word:
            operands.append(word)
    if not link:
        return ""
    return next((word for word in (operands if target else operands[:-1]) if holds(word, cwd)), "")


def _holds(path: str, cwd: str, predicate) -> bool:
    """True when `predicate` accepts the path, a path inside it, or a path one level below it."""
    base = path.rstrip("/\\") or path
    if predicate(path, cwd) or predicate(base + "/_", cwd):
        return True
    try:
        children = os.listdir(_expanded(path, cwd))
    except (OSError, ValueError):
        return False
    return any(predicate(os.path.join(base, child), cwd) or
               predicate(os.path.join(base, child, "_"), cwd) for child in children)


def _holds_frozen(path: str, cwd: str) -> bool:
    """`_holds` for the frozen set, plus a folder that holds the config directory at any depth.
    ponytail: a live pin more than one level below the folder is missed (`cp -al /opt` with the
    pin at /opt/a/clone-live); a walk of the tree closes it, at the cost of a slow hook."""
    if _holds(path, cwd, is_frozen):
        return True
    try:
        readings = ((_literal_resolved(path, cwd), os.path.normpath(guard_core.config_dir())),
                    (_resolved(path, cwd), os.path.realpath(guard_core.config_dir())))
    except Exception:
        return False
    return any(os.path.normcase(root) == target or
               os.path.normcase(root).startswith(target.rstrip(os.sep) + os.sep)
               for target, root in readings)


def _shell_write_hit(cmd: str, cwd: str, predicate, holds=None, follow_cd=False,
                     command_position=False, predicate_command=False) -> str:
    """Return the path a shell command writes to that `predicate(path, cwd)` accepts, else ''.
    `holds(path, cwd)` tells a folder that holds such a path, for a linking `cp` (`_cp_link_source`).
    `follow_cd` hands `predicate` the folder a leading `cd` moved to (`dir_before_segment`), or `cwd`
    when that folder cannot be told. `predicate_command` also hands `predicate` the segment's command
    name as a third argument (`''` when none)."""
    holds = holds or (lambda path, where: _holds(path, where, predicate))
    cmd = _resolve_vars(cmd)
    ends = []
    segments = split_segments(cmd, ends)
    scans = [_scan(segment) for segment in segments]
    parsed = [_quoted_words(segment) for segment in segments]
    # The same words with a quoted newline kept, for a `sh -c` script read at its command positions only:
    # the text the write patterns read keeps newlines as spaces, so a quoted newline never ends a command.
    scripts = [_quoted_words(segment, True) for segment in segments] if command_position else parsed
    closed = any(unsafe or _runs_stored_text(segment, words, plain)
                 for segment, words, (unsafe, plain) in zip(segments, parsed, scans))
    kinds = ["" if closed else _kind(words, plain) for words, (_u, plain) in zip(parsed, scans)]
    quiet = all(kind in ("printer", "cd") or not words for kind, words in zip(kinds, parsed))
    for number, raw in enumerate(parsed):
        linked = _cp_link_source(raw, holds, cwd)
        if linked:
            return linked
        data = set() if closed else _copy_reads(raw, predicate, cwd)
        if kinds[number] in ("printer", "message"):
            last = number
            while last + 1 < len(kinds) and ends[last] == "|":
                last += 1
            chain = range(number, last + 1)
            runs_nowhere = all(kinds[k] == "printer" for k in chain[1:])
            to_file = any(_writes_a_file(parsed[k]) for k in chain)
            if runs_nowhere and (quiet or not to_file):
                data = data | _data_words(kinds[number], raw)
        words, shown, script = [], [], []
        for index, word in enumerate(raw):
            if index in data:
                words.append('""')   # data, or a `cp` source: no redirect or `tee` in it runs
                shown.append('""')
                script.append('""')
            elif word == "&" and (raw[index + 1:index + 2] in ([">"], [">>"]) or raw[index - 1:index] == [">"]):
                continue   # the `&` of `&>` or `>&` ends no command, so the text reads `> PATH` whole
            elif index and re.fullmatch(_DESCRIPTOR, word) and _is_redirect(raw[index - 1]):
                # Never judged as a path. `dup` stays in the text so `2> PATH` is not read as `> PATH`.
                # The raw word is unquoted: a quoted "&1" is a file and is judged.
                shown.append("dup")
            else:
                # An unquoted `)` or backtick glued to the path (`( echo > F)`, `$(... > F)`) is not
                # part of it. A quoted word ends in its quote, so it is never cut here.
                word = word.rstrip(")`") or word
                pieces = _words_of(word) if "'" in word or '"' in word else [word]
                # `_words_of` cuts a quote's text at a paren but not at a backtick: a `bash -c` script that
                # holds a backtick substitution ends its path word with one.
                pieces = [piece.rstrip("`") or piece for piece in pieces]
                words.extend(pieces)
                shown.extend(pieces)
                kept = scripts[number][index]
                script.extend(_words_of(kept) if "'" in kept or '"' in kept else [kept])
        text = " ".join(shown)
        at = (dir_before_segment(segments, number, cwd, ends) or cwd) if follow_cd else cwd
        verb = _segment_command(words)[0] if predicate_command else ""
        for word in words:
            if word.startswith("-") or REDIRECT.fullmatch(word):
                continue
            if not word or word in (">", ">>"):
                continue
            if (predicate(word, at, verb) if predicate_command else predicate(word, at)) and writes_to(word, text, *(_segment_command(script) if command_position else ())):
                return word
    return ""


def _segment_command(words):
    """(resolved command name, plain words after it) of a segment, for `writes_to`'s command position."""
    index = resolve_command(tuple(words))
    if index is None:
        index = next((i for i, word in enumerate(words) if not _ASSIGNMENT.match(word)), len(words))
    command = _name(words[index]) if index < len(words) else ""
    return command, [word for word in words[index + 1:] if word]


def frozen_shell_hit(cmd: str, cwd: str) -> str:
    """Return the frozen (config-dir) path a shell command writes to, else ''."""
    return _shell_write_hit(cmd, cwd, is_frozen, _holds_frozen)


def project_config_shell_hit(cmd: str, cwd: str) -> str:
    """Return the project config path a shell command writes to, else ''."""
    return _shell_write_hit(cmd, cwd, is_project_config)


# ------------------------------------------------------------------ an interpreter's own writes
#
# A python or node script, run from a heredoc body or from `-c` / `-e`, writes a file the shell
# never names, so `_shell_write_hit` cannot see it. `interpreter_write_hit` reads the script itself.
# A quoted `<<'EOF'` body is read too: the interpreter runs it. Python is read with `ast`, so a path
# in a printed string or a comment is text and a path held in a variable is still found. A body
# `ast` cannot parse is read by a literal path beside a write call. Node is read by pattern.
_PY_HEADER = re.compile(r"(?<![\w.-])python[\d.]*(?:\.exe)?(?![\w.-])")
_NODE_HEADER = re.compile(r"(?<![\w.-])(?:node|nodejs|bun|deno)(?:\.exe)?(?![\w.-])")
_PY_COMMAND = re.compile(r"^python[\d.]*(?:\.exe)?$")
_NODE_COMMAND = re.compile(r"^(?:node|nodejs|bun|deno)(?:\.exe)?$")
_PY_C_FLAG = re.compile(r"^-[A-Za-z]*c$")
_NODE_EVAL_FLAG = re.compile(r"^(?:-[ep]{1,2}|--eval|--print)$")
_INLINE_FLAG_WORDS = ("-c", "-e", "-p", "--eval", "--print")
_PATH_CTORS = ("Path", "PurePath", "PosixPath", "WindowsPath", "PurePosixPath", "PureWindowsPath")
_PATH_PASS = ("resolve", "expanduser", "absolute")
_COPY_NAMES = ("copy", "copy2", "copyfile", "copytree", "move")
_PY_WRITE_CALL = re.compile(
    r"""open\s*\([^)]*['"][rwabt]*[wax+][rwabt+]*['"]|write_text|write_bytes|shutil\s*\.\s*(?:copy|move)"""
    r"""|os\s*\.\s*(?:replace|rename)""")
_STRING_LITERAL = re.compile(r"""'([^'\n]+)'|"([^"\n]+)\"""")


def _join_path(head: str, tail: str) -> str:
    return head.rstrip("/") + "/" + tail if head else tail


_PY_TEMP = "\0temp"   # stands for a folder a temp call made: no path of the repo, so nothing under it is judged
_PY_TEMP_CALLS = ("mkdtemp", "mkstemp", "gettempdir", "TemporaryDirectory")


def _py_call_name(node):
    import ast
    func = node.func
    return func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""


def _py_temp_head(node, env):
    """True when the first piece of a path expression is a folder a temp call made: the call itself, a
    name bound to one, its `.name`, or a join or `/` that starts with one. Any other head, such as
    `sys.argv[1]` or `Path(__file__).parents[1]`, may name a folder of the repo, so it is no temp head.
    A temp call given a folder (`dir=`, a third argument, `*args` or `**kwargs`) may make it in the repo."""
    import ast
    if isinstance(node, ast.Name):
        return env.get(node.id) == [_PY_TEMP]
    if isinstance(node, ast.Attribute) and node.attr == "name":   # `TemporaryDirectory().name`
        return _py_temp_head(node.value, env)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _py_temp_head(node.left, env)
    if isinstance(node, ast.Call):
        name = _py_call_name(node)
        if name in _PY_TEMP_CALLS:
            return len(node.args) < 3 and not any(isinstance(arg, ast.Starred) for arg in node.args) \
                and not any(keyword.arg in ("dir", None) for keyword in node.keywords)
        if name in _PATH_CTORS or name == "join":
            return bool(node.args) and _py_temp_head(node.args[0], env)
        if name in _PATH_PASS and isinstance(node.func, ast.Attribute):
            return _py_temp_head(node.func.value, env)
    return False


def _py_paths(node, env):
    """The path strings an expression can hold: a string, `Path(...)`, `a / b`, `os.path.join`, a
    name bound to one of those, or a chain of path calls. A part it cannot tell (`Path.cwd()`,
    `os.getcwd()`, `__file__`) is left out, so the literal pieces still join: `Path.cwd() / 'tests'`
    reads `tests`. A join that starts with a temp folder (`_py_temp_head`) holds only that folder.
    Empty when no piece is known."""
    import ast
    if isinstance(node, ast.Constant):
        return [node.value] if isinstance(node.value, str) else []
    if isinstance(node, ast.Name):
        return list(env.get(node.id, ()))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        if _py_temp_head(node.left, env):
            return [_PY_TEMP]
        left, right = _py_paths(node.left, env), _py_paths(node.right, env)
        if not right:
            return left
        return [_join_path(a, b) for a in (left or [""]) for b in right]
    if isinstance(node, ast.Call):
        func = node.func
        name = _py_call_name(node)
        if _py_temp_head(node, env):
            return [_PY_TEMP]
        if name in _PATH_CTORS or name == "join":
            out = [""]
            for options in (_py_paths(arg, env) for arg in node.args):
                if options:
                    out = [_join_path(a, b) for a in out for b in options]
            return out if out != [""] else []
        if isinstance(func, ast.Attribute) and func.attr in _PATH_PASS:
            return _py_paths(func.value, env)
    return []


def _py_bindings(tree):
    """(end position, name, value expression, statement) of each name a script binds to a path: a simple
    `name = <path>`, and a name taken from a temp call by a tuple (`fd, tmp = mkstemp()`) or by
    `with TemporaryDirectory() as tmp`. In source order."""
    import ast
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            end = (node.end_lineno, node.end_col_offset)
            if isinstance(target, ast.Name):
                out.append((end, target.id, node.value, node))
            elif isinstance(target, ast.Tuple) and isinstance(node.value, ast.Call) \
                    and _py_call_name(node.value) in _PY_TEMP_CALLS:
                out.extend((end, name.id, node.value, node) for name in target.elts if isinstance(name, ast.Name))
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if isinstance(item.optional_vars, ast.Name) and isinstance(item.context_expr, ast.Call) \
                        and _py_call_name(item.context_expr) in _PY_TEMP_CALLS:
                    end = (item.context_expr.end_lineno, item.context_expr.end_col_offset)
                    out.append((end, item.optional_vars.id, item.context_expr, node))
    return sorted(out, key=lambda event: event[0])


def _py_env_at(tree):
    """A function `env_at(node)`: the path each `name = <path>` binding gave, as it stands where `node`
    begins. One pass in source order; a later top-level assignment replaces the value, one inside an
    `if`, loop, `try` or function adds to it, since either may not run."""
    top = {id(statement) for statement in tree.body}
    events = _py_bindings(tree)

    def env_at(call):
        env = {}
        for end, name, value, node in events:
            if end > (call.lineno, call.col_offset):
                break
            values = _py_paths(value, env)
            if id(node) in top:
                env[name] = values
            else:
                env[name] = env.get(name, []) + [v for v in values if v not in env.get(name, [])]
        return env
    return env_at


def _py_mode_writes(mode) -> bool:
    import ast
    return isinstance(mode, ast.Constant) and isinstance(mode.value, str) and any(c in mode.value for c in "wax+")


def _py_arg(call, index, keyword):
    if len(call.args) > index:
        return call.args[index]
    return next((kw.value for kw in call.keywords if kw.arg == keyword), None)


def _py_written(tree, env_at):
    """(call, path expression) of each write call of a script: `open` with a writing mode, `write_text`,
    `write_bytes`, the destination of a copy, a move or a rename."""
    import ast
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            if func.id == "open" and _py_mode_writes(_py_arg(node, 1, "mode")):
                out.append((node, _py_arg(node, 0, "file")))
            elif func.id in _COPY_NAMES and len(node.args) >= 2:
                out.append((node, node.args[1]))
        elif isinstance(func, ast.Attribute):
            attr, owner = func.attr, func.value
            module = isinstance(owner, ast.Name) and owner.id in ("os", "shutil", "io", "codecs", "gzip", "bz2")
            if attr in ("write_text", "write_bytes"):
                out.append((node, owner))
            elif attr == "open" and module and _py_mode_writes(_py_arg(node, 1, "mode")):
                out.append((node, _py_arg(node, 0, "file")))
            elif attr == "open" and not module and _py_mode_writes(_py_arg(node, 0, "mode")):
                out.append((node, owner))
            elif attr in _COPY_NAMES and isinstance(owner, ast.Name) and owner.id == "shutil" and len(node.args) >= 2:
                out.append((node, node.args[1]))
            elif attr in ("replace", "rename") and isinstance(owner, ast.Name) and owner.id == "os" \
                    and len(node.args) >= 2:
                out.append((node, node.args[1]))
            elif attr in ("replace", "rename") and not module and len(node.args) == 1 \
                    and _py_paths(owner, env_at(node)):
                out.append((node, node.args[0]))   # Path.rename(target) writes the target
    return [(call, expression) for call, expression in out if expression is not None]


def _py_hit(body: str, cwd: str, predicate) -> str:
    import ast
    import textwrap
    try:
        tree = ast.parse(textwrap.dedent(body))
    except (SyntaxError, ValueError):
        # Unparsable (a shell variable in an unquoted body, a Python 2 line): a literal path the
        # predicate accepts, beside a write call in the same body, counts.
        if _PY_WRITE_CALL.search(body):
            for match in _STRING_LITERAL.finditer(body):
                text = match.group(1) or match.group(2)
                if predicate(text, cwd):
                    return text
        return ""
    env_at = _py_env_at(tree)
    for call, expression in _py_written(tree, env_at):
        for path in _py_paths(expression, env_at(call)):
            if predicate(path, cwd):
                return path
    return ""


_JS_STR = r"""(?:'([^'\n]*)'|"([^"\n]*)"|`([^`$]*)`|([A-Za-z_$][\w$]*)|path\s*\.\s*(?:join|resolve)\s*\(([^()]*)\))"""
_JS_ONE = re.compile(
    r"\b(?:writeFileSync|writeFile|appendFileSync|appendFile|createWriteStream)\s*\(\s*" + _JS_STR)
_JS_TWO = re.compile(
    r"(?:\b(?:copyFileSync|copyFile|renameSync|cpSync)|\bfs(?:\.promises)?\s*\.\s*(?:rename|cp))"
    r"\s*\(\s*" + _JS_STR + r"\s*,\s*" + _JS_STR)
_JS_ASSIGN = re.compile(
    r"""\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:'([^'\n]*)'|"([^"\n]*)"|`([^`$]*)`)""")


def _js_values(groups, env):
    """The path strings one `_JS_STR` match holds, from its five groups."""
    quoted = next((g for g in groups[:3] if g is not None), None)
    if quoted is not None:
        return [quoted]
    if groups[3]:
        return list(env.get(groups[3], ()))
    if groups[4] is not None:
        pieces = re.findall(r"""['"]([^'"]*)['"]""", groups[4])
        return ["/".join(piece.strip("/") for piece in pieces)] if pieces else []
    return []


def _js_hit(body: str, cwd: str, predicate) -> str:
    env = {}
    for match in _JS_ASSIGN.finditer(body):
        env.setdefault(match.group(1), []).append(next(g for g in match.groups()[1:] if g is not None))
    for match in _JS_ONE.finditer(body):
        for path in _js_values(match.groups(), env):
            if predicate(path, cwd):
                return path
    for match in _JS_TWO.finditer(body):
        for path in _js_values(match.groups()[5:], env):   # the second operand is the one written
            if predicate(path, cwd):
                return path
    return ""


def _inline_scripts(command: str):
    """Yield (kind, script, segment number, segments, ends) for each `python -c` and `node -e` script."""
    ends = []
    segments = split_segments(_strip_heredoc_bodies_unconditionally(command), ends)
    for number, segment in enumerate(segments):
        if not any(flag in segment for flag in _INLINE_FLAG_WORDS):
            continue
        tokens = segment_tokens(segment)
        index = resolve_command(tokens) if tokens else None
        if index is None:
            continue
        name = basename(tokens[index])
        kind = "py" if _PY_COMMAND.match(name) else "js" if _NODE_COMMAND.match(name) else ""
        flag = _PY_C_FLAG if kind == "py" else _NODE_EVAL_FLAG
        for at in range(index + 1, len(tokens) - 1):
            if kind and flag.match(tokens[at]):
                yield kind, str(tokens[at + 1]), number, segments, ends
                break


def interpreter_write_hit(raw: str, cwd: str, predicate) -> str:
    """Return the path a python or node script in `raw` writes that `predicate(path, cwd)` accepts, else ''.
    Read: the body of each heredoc fed to python or node, quoted or not, and each `python -c` and
    `node -e` script. A script that only reads a path, or names it in a string, hits nothing.
    A crash of the scan reads as no hit: it must never skip the rules after it."""
    try:
        return _interpreter_write_hit(raw, cwd, predicate)
    except Exception:
        return ""


def _interpreter_write_hit(raw: str, cwd: str, predicate) -> str:
    if "<<" in raw:
        seen = set()
        for reading in (False, True):   # bash's own walk, and the one where a contraction's `'` is text
            for _quote, body, header in _split_heredocs(raw, reading)[1]:
                if (header, body) in seen:
                    continue
                seen.add((header, body))
                if _PY_HEADER.search(header):
                    hit = _py_hit(body, cwd, predicate)
                elif _NODE_HEADER.search(header):
                    hit = _js_hit(body, cwd, predicate)
                else:
                    continue
                if hit:
                    return hit
    if any(flag in raw for flag in _INLINE_FLAG_WORDS):
        for kind, script, number, segments, ends in _inline_scripts(raw):
            at = dir_before_segment(segments, number, cwd, ends) or cwd
            hit = (_py_hit if kind == "py" else _js_hit)(script, at, predicate)
            if hit:
                return hit
    return ""


# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
