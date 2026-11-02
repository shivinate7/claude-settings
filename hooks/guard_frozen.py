"""The guard's frozen family: a write to the settings, the hooks or the global CLAUDE.md.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import ast
import os
import re
import warnings

import guard_core
from guard_core import (
    REDIRECT, _expanded, _resolved, dir_before_segment, inline_script, norm, segment_tokens, split_segments,
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


# `precise` is the opt-in of a rule that judges what Claude writes by mistake (builder-test-edit): a
# mutating word counts only in command position (its segment's start, or after `git`, `xargs`,
# `sudo`, `-exec` and the like), so `pip install -r tests/requirements.txt` and `pytest -k copy
# tests/x.py` write nothing; and `perl -pi` rewrites a file in place.
_COMMAND_POSITION = (
    r"(?:^\s*(?:\w+=\S*\s+)*|\b(?:git|xargs|sudo|command|exec|time|env|nohup|do|then|else"
    r"|-exec|-execdir)\s+)"
)


_SED_WRAPPERS = frozenset((
    "git", "xargs", "sudo", "command", "exec", "time", "env", "nohup", "do", "then", "else", "-exec", "-execdir"))


def _sed_flags_edit_in_place(tokens) -> bool:
    """True when the words after `sed` hold the in-place flag, read as flags: `-i`, `-i.bak`, a short
    cluster that holds `i` (`-Ei`, `-ni`) or `--in-place[=SUFFIX]`. The argument of `-e`, `-f` and `-l`
    is not a flag, and a script such as `/-i/p` is not one."""
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            break
        if token.startswith("--"):
            if token == "--in-place" or token.startswith("--in-place="):
                return True
        elif len(token) > 1 and token[0] == "-" and token[1].isalpha():
            for place, letter in enumerate(token[1:]):
                if letter == "i":
                    return True
                if letter in "efl":
                    index += place == len(token) - 2   # the argument is the next word
                    break
        index += 1
    return False


def _sed_in_place_on(path: str, cmd: str) -> bool:
    """True when `cmd` runs `sed` in command position with the in-place flag on `path` (`precise`)."""
    words = cmd.split()
    for index, word in enumerate(words):
        if word.rsplit("/", 1)[-1] != "sed":
            continue
        start = index == 0 or all(re.fullmatch(r"\w+=\S*", w) for w in words[:index]) \
            or words[index - 1] in _SED_WRAPPERS
        if start and path in words[index + 1:] and _sed_flags_edit_in_place(words[index + 1:]):
            return True
    return False


def writes_to(path: str, cmd: str, precise: bool = False) -> bool:
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
    if re.search((_COMMAND_POSITION if precise else "") + MUTATING_COMMAND + r"[^\n;|&]*" + target, cmd):
        return True
    if precise:
        if _sed_in_place_on(path, cmd):
            return True
    elif re.search(r"\bsed\b[^\n;|&]*-i\b[^\n;|&]*" + target, cmd):
        return True
    if precise and re.search(r"\bperl\b[^\n;|&]*\s-[pnlasw]*i\b[^\n;|&]*" + target, cmd):
        return True
    return False


# VARIABLE INDIRECTION. In `D=~/.claude/state/handoff/x.md; ...; cp "$S/handoff.md" "$D"` the parse
# sees only the word `$D`. One left-to-right pass in `_shell_write_hit` (it feeds the frozen and
# project-config checks) keeps a table of simple assignments (`D=v`, `export A=1 D=v`, `declare`,
# a PowerShell `$D = v`), and reads each `$D` or `${D}` as the value current at that point: the
# last assignment wins, `unset D` clears it, a use before the assignment stays as written, and
# single quotes do not expand. An unassigned variable stays unresolved and allowed. `$HOME` reads
# as `~`: `os.path.expandvars` leaves it literal when HOME is unset (the Windows default), so a
# literal `$HOME/.claude/...` target was allowed.
# RESIDUAL GAP: a value from `$(...)`, backticks, `read`, `${D:-x}`, a loop variable, `eval`, or an
# interpreter (`python -c`) is not resolved, nor is a variable set in a different tool call.
# Fixing that needs a shell parser, not a regex.
_VAR_TOKEN = re.compile(
    r"""'[^']*'"""                                                    # single quotes: no expansion
    r"""|(?<![\w$.\-/:])(?P<n>[A-Za-z_]\w*)=(?!=)(?P<v>"[^"]*"|'[^']*'|[^\s;&|"'`)}]*)"""
    r"""|\$(?P<pn>[A-Za-z_]\w*)[ \t]*=(?!=)[ \t]*(?P<pv>"[^"]*"|'[^']*'|[^\s;&|"'`)}]*)"""
    r"""|\bunset\s+(?P<u>\w+)"""
    r"""|\$(?:(?P<x>[A-Za-z_]\w*)|\{(?P<y>[A-Za-z_]\w*)\})""")


def _resolve_vars(cmd: str) -> str:
    """Read each `$VAR` or `${VAR}` as the value assigned earlier in the command."""
    table = {"HOME": "~"}

    def use(m):
        return table.get(m.group("x") or m.group("y"), m.group(0))

    def step(m):
        if m.group("u"):
            table.pop(m.group("u"), None)
        name, raw = (m.group("n"), m.group("v")) if m.group("n") else (m.group("pn"), m.group("pv"))
        if name:
            value = raw if raw.startswith("'") else _VAR_TOKEN.sub(step, raw)
            value = value.strip("'\"")
            if "$" in value or "`" in value:
                table.pop(name, None)  # not resolvable: forget any older value too
            else:
                table[name] = value
            return m.group(0)
        return use(m) if (m.group("x") or m.group("y")) else m.group(0)

    return _VAR_TOKEN.sub(step, cmd)


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
# scanner. A segment with an unquoted `&`, `(`, `)`, `{` or `}`
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
    `\\"` in a JSON sample there is plain text."""
    plain, quote = [], ""
    for index, char in enumerate(segment):
        if char in _SMART_QUOTES:   # also inside single quotes: PowerShell ends a string at one
            return True, ""
        if quote == "'":
            quote = "" if char == "'" else quote
        elif _UNSAFE_MARK.match(segment, index):
            return True, ""
        elif char in "'\"":
            quote = "" if quote == char else (quote or char)
        elif not quote:
            plain.append(char)
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


def _shell_write_hit(cmd: str, cwd: str, predicate, holds=None, follow_cd=False, precise=False) -> str:
    """Return the path a shell command writes to that `predicate(path, cwd)` accepts, else ''.
    `holds(path, cwd)` tells a folder that holds such a path, for a linking `cp` (`_cp_link_source`).
    `follow_cd` hands `predicate` the folder a leading `cd` moved to (`dir_before_segment`), or `cwd`
    when that folder cannot be told. `precise` is the opt-in read of `writes_to`."""
    holds = holds or (lambda path, where: _holds(path, where, predicate))
    cmd = _resolve_vars(cmd)
    ends = []
    segments = split_segments(cmd, ends)
    scans = [_scan(segment) for segment in segments]
    parsed = [_quoted_words(segment) for segment in segments]
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
        words, shown = [], []
        for index, word in enumerate(raw):
            if index in data:
                words.append('""')   # data, or a `cp` source: no redirect or `tee` in it runs
                shown.append('""')
            elif index and re.fullmatch(_DESCRIPTOR, word) and _is_redirect(raw[index - 1]):
                # Never judged as a path. `dup` stays in the text so `2> PATH` is not read as `> PATH`.
                # The raw word is unquoted: a quoted "&1" is a file and is judged.
                shown.append("dup")
            else:
                pieces = _words_of(word) if "'" in word or '"' in word else [word]
                words.extend(pieces)
                shown.extend(pieces)
        text = " ".join(shown)
        at = (dir_before_segment(segments, number, cwd, ends) or cwd) if follow_cd else cwd
        for word in words:
            if word.startswith("-") or REDIRECT.fullmatch(word):
                continue
            if not word or word in (">", ">>"):
                continue
            if predicate(word, at) and writes_to(word, text, precise):
                return word
    return ""


# INTERPRETER WRITES. An opt-in read (`interpreter_write_hit`; no frozen, config or settings rule calls
# it): the script a command hands to `python` or `node` is read as that language's own text, never
# split as shell words (`#` and a lone quote are not shell syntax in a script). Python is parsed with
# `ast`: `open(P, mode)` with `w`, `a`, `x` or `+` in the mode, `Path(P).open(mode)`, `.write_text`,
# `.write_bytes`, the destination of `shutil.copy*`/`shutil.move`/`os.replace`/`os.rename`. A name is
# read through a plain `name = "lit"` or `name = Path("lit")` assignment. Node is a string- and
# comment-aware scan for `writeFileSync`, `writeFile`, `appendFileSync` or `appendFile` with a literal
# first argument. A script that does not parse, or a path that is not a literal, is allowed.
# RESIDUAL GAPS (a mistake does not make these): `python3 script.py` and `node script.js`, where the
# program's own code writes; a path built by an f-string, a call, an argument or an environment
# variable; a Node path held in a variable; `ruby`, `perl -e` and `perl` heredocs; a script an
# interpreter reads from a pipe that no heredoc feeds (`echo "..." | python3`).
_PY_WRITE_MODE = frozenset("wax+")
_PY_PATH_CLASSES = ("Path", "PurePath", "PosixPath", "PurePosixPath", "WindowsPath", "PureWindowsPath")
_JS_WRITERS = frozenset(("writeFileSync", "writeFile", "appendFileSync", "appendFile"))
_SCRIPT_RUNNER = re.compile(r"python[\d.]*w?|nodejs|node")
_PY_FLAG_C = re.compile(r"-[BEIOPRSsuvVWXxq]*c")
_NODE_FLAG_E = re.compile(r"--eval|--print|-[a-zA-Z]*[ep]")
_INTERPRETER_WORD = re.compile(
    r"(?<![\w./-])(?:[^\s|;&<>()]*[/\\])?(python[\d.]*w?|nodejs|node)(?:\.exe)?(?![\w.-])")
_SCRIPT_FILE = re.compile(r"[^\s]*\.(?:py|pyw|js|mjs|cjs)$")


def _py_str(node, env, depth=0):
    """The literal text an expression stands for (a string, a name read through `env`, a `Path(...)`
    or `a / "b"` or `.joinpath` or `os.path.join` of literals), else None."""
    if depth > 8:
        return None
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.Name):
        return env.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left, right = _py_str(node.left, env, depth + 1), _py_str(node.right, env, depth + 1)
        return None if left is None or right is None else left.rstrip("/") + "/" + right
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
    parts = [_py_str(arg, env, depth + 1) for arg in node.args]
    if name in _PY_PATH_CLASSES or (name == "join" and isinstance(func, ast.Attribute)
                                    and isinstance(func.value, (ast.Attribute, ast.Name))
                                    and getattr(func.value, "attr", getattr(func.value, "id", "")) in ("path", "posixpath")):
        return "/".join(parts) if parts and None not in parts else None
    if isinstance(func, ast.Attribute) and name in ("resolve", "absolute", "expanduser", "joinpath"):
        base = _py_str(func.value, env, depth + 1)
        return None if base is None or None in parts else "/".join([base] + parts)
    return None


def _py_write_paths(script: str):
    """The literal paths a Python script writes, in the forms listed above. [] when it does not parse."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = ast.parse(script)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return []
    env = {}
    for node in sorted((n for n in ast.walk(tree) if isinstance(n, (ast.Assign, ast.AnnAssign))),
                       key=lambda n: (n.lineno, n.col_offset)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value = _py_str(node.value, env) if node.value is not None else None
        for target in targets:
            if isinstance(target, ast.Name):
                if value is None:
                    env.pop(target.id, None)
                else:
                    env[target.id] = value
    found = []

    def write_mode(node):
        mode = _py_str(node, env) if node is not None else None
        return isinstance(mode, str) and bool(_PY_WRITE_MODE & set(mode))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func, args = node.func, node.args
        kw = {k.arg: k.value for k in node.keywords if k.arg}
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
        owner = func.value.id if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) else ""
        path = None
        if name == "open" and (isinstance(func, ast.Name) or owner in ("io", "codecs")):
            if write_mode(args[1] if len(args) > 1 else kw.get("mode")):
                path = _py_str(args[0] if args else kw.get("file"), env)
        elif name == "open" and isinstance(func, ast.Attribute):
            if write_mode(args[0] if args else kw.get("mode")):
                path = _py_str(func.value, env)
        elif name in ("write_text", "write_bytes") and isinstance(func, ast.Attribute):
            path = _py_str(func.value, env)
        elif owner == "shutil" and name in ("copy", "copy2", "copyfile", "copytree", "move") or (
                owner == "os" and name in ("replace", "rename")):
            path = _py_str(args[1] if len(args) > 1 else kw.get("dst"), env)
        if path:
            found.append(path)
    return found


def _js_write_paths(text: str):
    """The literal first arguments of `writeFileSync`, `writeFile`, `appendFileSync` and `appendFile`
    calls in code. A string, a template literal (any line count) and a comment are skipped whole, so
    a `//` or a `/*` inside a string opens no comment and a quote inside a template ends nothing."""
    found, at, size = [], 0, len(text)

    def string_end(start):
        quote, at = text[start], start + 1
        while at < size and text[at] != quote:
            at += 2 if text[at] == "\\" else 1
        return min(at, size)

    while at < size:
        char = text[at]
        if text.startswith("//", at):
            at = text.find("\n", at)
            at = size if at < 0 else at
        elif text.startswith("/*", at):
            at = text.find("*/", at + 2)
            at = size if at < 0 else at + 2
        elif char in "'\"`":
            at = string_end(at) + 1
        elif char.isalpha() or char in "_$":
            end = at
            while end < size and (text[end].isalnum() or text[end] in "_$"):
                end += 1
            word, at = text[at:end], end
            if word in _JS_WRITERS:
                rest = re.compile(r"\s*\(\s*(['\"`])").match(text, at)
                if rest:
                    start = rest.end() - 1
                    found.append(text[start + 1:string_end(start)])
        else:
            at += 1
    return found


def _script_write_paths(language: str, script: str):
    return _py_write_paths(script) if language == "python" else _js_write_paths(script)


def _inline_scripts(tokens):
    """[(language, script)] a segment's `python -c`, `node -e` and `node -p` hand over."""
    found = []
    for index, token in enumerate(tokens[:6]):
        name = token.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower().removesuffix(".exe")
        if not _SCRIPT_RUNNER.fullmatch(name):
            continue
        python = name.startswith("python")
        flag = _PY_FLAG_C if python else _NODE_FLAG_E
        for at in range(index + 1, len(tokens) - 1):
            if flag.fullmatch(tokens[at]):
                found.append(("python" if python else "node", tokens[at + 1]))
                break
            if not tokens[at].startswith("-"):
                break   # a script file or a module: the program's own code writes (residual gap)
        break
    return found


def interpreter_write_hit(cmd: str, cwd: str, predicate, follow_cd=True, depth=0) -> str:
    """The path a `python`/`node` script in the command writes that `predicate(path, cwd)` accepts,
    else ''. Reads `-c`, `-e` and `-p` scripts, scripts of `sh -c`, and the body of each heredoc fed
    to the interpreter (`python3 - <<'EOF'`, `cat <<'EOF' | python3 -`). `follow_cd` hands `predicate`
    the folder a leading `cd` moved to."""
    bare = guard_core._strip_heredoc_bodies_unconditionally(cmd)
    ends = []
    segments = split_segments(bare, ends)
    heads = []   # the segment number of each heredoc header, in order
    for number, segment in enumerate(segments):
        tokens = segment_tokens(segment)
        if not tokens:
            continue
        at = (dir_before_segment(segments, number, cwd, ends) or cwd) if follow_cd else cwd
        for language, script in _inline_scripts(tokens):
            for path in _script_write_paths(language, script):
                if predicate(path, at):
                    return path
        nested = inline_script(tokens)
        if nested and depth < 3:
            hit = interpreter_write_hit(nested, at, predicate, False, depth + 1)
            if hit:
                return hit
        heads.extend([number] * sum(1 for t in tokens if t.startswith("<<") and not t.startswith("<<<")))
    if "<<" not in cmd:
        return ""
    bodies = guard_core._walk_heredocs(cmd)[1]
    for index, (_quote, body, header) in enumerate(bodies):
        found = _INTERPRETER_WORD.search(header)
        if not found:
            continue
        rest = re.split(r"<<|[|;&]", header[found.end():], 1)[0].split()
        if any(_SCRIPT_FILE.fullmatch(word) for word in rest if not word.startswith("-")):
            continue   # `python3 run.py <<EOF`: the body is the script's input
        language = "python" if found.group(1).startswith("python") else "node"
        number = heads[index] if index < len(heads) and len(heads) == len(bodies) else None
        at = cwd if number is None or not follow_cd else (dir_before_segment(segments, number, cwd, ends) or cwd)
        for path in _script_write_paths(language, body):
            if predicate(path, at):
                return path
    return ""


def frozen_shell_hit(cmd: str, cwd: str) -> str:
    """Return the frozen (config-dir) path a shell command writes to, else ''."""
    return _shell_write_hit(cmd, cwd, is_frozen, _holds_frozen)


def project_config_shell_hit(cmd: str, cwd: str) -> str:
    """Return the project config path a shell command writes to, else ''."""
    return _shell_write_hit(cmd, cwd, is_project_config)

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
