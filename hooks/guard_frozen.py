"""The guard's frozen family: a write to the settings, the hooks or the global CLAUDE.md.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import fnmatch
import glob
import itertools
import os
import re

import guard_core
from guard_core import (
    LOOP_KEYWORDS, REDIRECT, _expanded, _resolved, _split_heredocs, _strip_heredoc_bodies_unconditionally,
    _walk_wrappers, basename, dir_before_segment, is_powershell, norm, resolve_command, segment_tokens,
    split_segments,
)
from guard_env import _quoted_words, _substitutions


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
# sees only the word `$D`. One left-to-right pass in `_shell_write_hit` (it feeds the frozen and
# project-config checks) keeps a table of simple assignments (`D=v`, `export A=1 D=v`, `declare`,
# a PowerShell `$D = v`), and reads each `$D` or `${D}` as the value current at that point: the
# last assignment wins, `unset D` clears it, a use before the assignment stays as written, and
# single quotes do not expand. An unassigned variable stays unresolved and allowed. `$HOME` reads
# as `~`: `os.path.expandvars` leaves it literal when HOME is unset (the Windows default), so a
# literal `$HOME/.claude/...` target was allowed.
# RESIDUAL GAP: a value from `read`, `${D:-x}`, `eval`, or an interpreter (`python -c`) is not
# resolved, nor is a variable set in a different tool call. Fixing that needs a shell parser, not a
# regex. The frozen, project-config and settings checks also leave a value from `$(...)`, backticks
# and a loop variable unresolved. The builder test check reads those (`read_fed`, `_fed_command`).
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


def _cp_start(raw, keywords=False, names=("cp",)):
    """The index of the command word of a segment, past its `VAR=value` words (and past `do`, `then` and
    the other loop keywords when `keywords`), else None when the command is not one of `names`."""
    start = 0
    while start < len(raw) and (_ASSIGNMENT.match(raw[start]) or keywords and raw[start] in LOOP_KEYWORDS):
        start += 1
    word = raw[start].lstrip("(") if start < len(raw) else ""   # a subshell paren glued to the command: `(cp a b)`
    return start if _name(word) in names else None


def _copy_parts(raw, keywords=False, names=("cp",)):
    """(source indexes, target index) of a `cp` segment, or of a command in `names`, as indexes into `raw`: the
    target is the word `-t` takes (a glued `-tDIR` is its own word), else the last operand. None when the segment
    is not one, or holds a flag or redirect that is not read."""
    words = [_unquoted(word) for word in raw]
    start = _cp_start(raw, keywords, names)
    if start is None:
        return None
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
            return None
        if _CP_TARGET.fullmatch(word):
            if index + 1 >= len(words):
                return None
            target, index = index + 1, index + 2
            continue
        if word.startswith("--target-directory=") or word.startswith("-t") and len(word) > 2 and word[1] != "-":
            target = index
        elif _CP_FLAGS.fullmatch(word):
            pass
        elif word.startswith("-") or ">" in word or "<" in word:
            return None
        else:
            operands.append(index)
        index += 1
    if target is None:
        if len(operands) < 2:
            return None
        target = operands.pop()
    return operands, target


def _copy_target(word) -> str:
    """The directory a `_copy_parts` target word names: a glued `-tDIR` or `--target-directory=DIR` gives DIR."""
    glued = _glued_cp_target(word)
    value = glued[1] if glued else _unquoted(word)
    # An unquoted `)` or backtick glued to the word (`(cp a docs/)`) ends the subshell, not the path.
    return value if word.endswith(("'", '"')) else value.rstrip(")`") or value


def _copy_reads(raw, predicate, cwd, keywords=False):
    """The indexes of the words of a `cp` segment that are only read, else an empty set."""
    parts = _copy_parts(raw, keywords)
    if parts is None:
        return set()
    operands, at = parts
    target = _copy_target(raw[at])
    if not operands or not target or _CP_DEST_UNSAFE.search(target):
        return set()
    if predicate(target, cwd) or predicate(target.rstrip("/\\") + "/_", cwd):
        return set()
    return set(operands)


_TARGET_COMMANDS = ("cp", "mv", "install")   # the commands that take `-tDIR`, glued, as `cp` does
_CP_GLUED_TARGET = re.compile(r"-[RrfiaHLPpnvuxTSD]*t(.+)")   # D is `install`'s flag
_WALK_SKIP = frozenset((".git", "node_modules", ".venv", "venv", "__pycache__"))
_WALK_LIMIT = 5000
_LIST_LIMIT = 10 * _WALK_LIMIT   # entries listed, judged or not: a filtered walk of a whole disk stops here


def _glued_cp_target(word):
    """(flag, value) of a `cp`, `mv` or `install` word that glues the target directory to its flag (`-ttests`,
    `--target-directory=tests`), else None. `_copy_parts` reads the same two forms."""
    plain = _unquoted(word)
    if plain.startswith("--"):
        name, equals, value = plain[2:].partition("=")
        if equals and value and name and "target-directory".startswith(name):
            return "--target-directory", value
        return None
    found = _CP_GLUED_TARGET.fullmatch(plain)
    return ("-t", found.group(1)) if found else None


_TOO_LARGE = "\0too-large"   # `_first_test_under`'s answer for a folder it could not finish
_TOO_LARGE_FILTERED = "\0too-large-filtered"   # the same, for a walk that a find's name filter already narrows
_TOO_LARGE_NOTE = " (the folder is too large to check for a test; name a narrower path)"
# The hit's note when the walk had a name filter: the refusal's remedy then names no `-name` filter.
_TOO_LARGE_FILTERED_NOTE = " (the folder is too large to check for a test even through the find's name filter; name a narrower path)"


_TOO_LARGE_NOTES = {_TOO_LARGE: _TOO_LARGE_NOTE, _TOO_LARGE_FILTERED: _TOO_LARGE_FILTERED_NOTE}


def _brace_words(word):
    """The words bash makes of `word` by brace expansion, lazily: `{a,b}` by its commas, `{1..3}` and
    `{a..c}` by their range. A brace in quotes, after `$`, or with neither a comma nor a range is text.
    A range with a step, or one that is not a whole number or one letter, is left as text."""
    depth, quote, start, commas = 0, "", -1, []
    for at, char in enumerate(word):
        if quote:
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char == "{" and not (depth == 0 and word[at - 1:at] == "$"):
            if depth == 0:
                start, commas = at, []
            depth += 1
        elif char == "," and depth == 1:
            commas.append(at)
        elif char == "}" and depth:
            depth -= 1
            if depth:
                continue
            inner = word[start + 1:at]
            if commas:
                cuts = [start] + commas + [at]
                parts = [word[cuts[n] + 1:cuts[n + 1]] for n in range(len(cuts) - 1)]
            else:
                parts = _brace_range(inner)
            if parts is not None:
                for part in parts:
                    yield from _brace_words(word[:start] + part + word[at + 1:])
                return
    yield word


def _brace_range(inner):
    """The words of a brace range `1..3` or `a..e` (down as well as up), else None."""
    found = re.fullmatch(r"(-?\d+)\.\.(-?\d+)|([A-Za-z])\.\.([A-Za-z])", inner)
    if not found:
        return None
    if found.group(1) is not None:
        low, high, shape = int(found.group(1)), int(found.group(2)), str
    else:
        low, high, shape = ord(found.group(3)), ord(found.group(4)), chr
    step = 1 if high >= low else -1
    if abs(high - low) > _WALK_LIMIT:
        return None
    return [shape(number) for number in range(low, high + step, step)]


def _glob_pattern(word):
    """(pattern, has a glob) of a raw word: its quoted `*`, `?` and `[` are text, so they are bracketed."""
    out, quote, magic = [], "", False
    for at, char in enumerate(word):
        if char == quote:
            quote = ""
        elif not quote and char in "'\"":
            quote = char
        elif not quote and char == "$" and word[at + 1:at + 2] in ("'", '"'):
            continue
        elif char in "*?[":
            out.append("[%s]" % char if quote else char)
            magic = magic or not quote
        else:
            out.append(char)
    return "".join(out), magic


def _written_sources(word, cwd):
    """(paths, capped) the source word `word` of a `cp` names once the shell has expanded its braces and
    globs against `cwd`. A glob that matches nothing stays its text, as in the shell. `capped` is True when
    the expansion passed `_WALK_LIMIT` paths: the rest are not listed."""
    paths = []
    for each in _brace_words(word):
        pattern, magic = _glob_pattern(each)
        if magic:
            matched = list(itertools.islice(glob.iglob(_expanded(pattern, cwd)), _WALK_LIMIT + 1 - len(paths)))
            paths.extend(matched or [_unquoted(each)])
        else:
            paths.append(_unquoted(each))
        if len(paths) > _WALK_LIMIT:
            return paths[:_WALK_LIMIT], True
    return paths, False


def _copy_written_hit(raw, cwd, predicate, fed, filters, made=frozenset()) -> str:
    """The path a `cp` segment writes that `predicate(path, cwd)` accepts, else ''. The sources are the
    words with their braces and globs expanded against `cwd`. DEST is a folder when it ends in a slash,
    is an existing folder, is a folder `made` holds (absolute folders an earlier `mkdir` of the same command makes), is `-t`'s word, is
    fed, or there is more than one source: the copy then writes
    `DEST/<basename of each source>`, so a test-named source copied into any folder writes a test there.
    With `--parents` DEST is always a folder and the copy writes `DEST/<each source as named>`.
    Otherwise it writes DEST itself. A source folder is walked (`cp -r SRC DEST/` writes
    `DEST/<SRC name>/<path under SRC>` for each file) as far as the caps allow; a fed source that is a folder is a
    find root (`_fed_segments`): it is walked, as `filters` narrows it, and each file under it is judged
    as `DEST/<its name>`. A DEST that holds a glob or a variable is not judged (it stays a root, which fails closed)."""
    parts = _copy_parts(raw, fed)
    if parts is None:
        return ""
    operands, at = parts
    dest = _copy_target(raw[at])
    if not operands or not dest or _CP_DEST_UNSAFE.search(dest):
        return ""
    sources, capped = [], False
    for index in operands:
        found, more = _written_sources(raw[index], cwd)
        sources.extend((raw[index], path) for path in found)
        capped = capped or more
    flagged = _glued_cp_target(raw[at]) is not None or at > 0 and _CP_TARGET.fullmatch(_unquoted(raw[at - 1]))
    parents = _cp_keeps_parents(raw)
    into = bool(fed or flagged or parents or dest.endswith(("/", "\\")) or len(sources) > 1
                or os.path.normpath(_expanded(dest, cwd)) in made or os.path.isdir(_expanded(dest, cwd)))
    if capped and _may_hold_a_test(dest, cwd, predicate):
        return _unquoted(raw[operands[0]]) + _TOO_LARGE_NOTE
    for word, source in sources:
        base = re.split(r"[/\\]", source.rstrip("/\\"))[-1]
        written = os.path.join(dest, source.lstrip("/\\") if parents else base) if into else dest
        if base and predicate(written, cwd):
            return written
        if fed and _may_hold_a_test(dest, cwd, predicate):
            walked = _first_test_under(source, cwd, predicate, (filters or {}).get(source), dest)
        elif not fed and base and os.path.isdir(_expanded(source, cwd)) and _may_hold_a_test(dest, cwd, predicate):
            walked = _first_test_under(source, cwd, predicate, None, written, True)
        else:
            continue
        if walked:
            return source + _TOO_LARGE_NOTES[walked] if walked in _TOO_LARGE_NOTES else walked
    return ""


def _cp_keeps_parents(raw) -> bool:
    """True when a `cp` segment has `--parents`, which GNU `cp` also takes cut short to `--pa`."""
    start = _cp_start(raw, True)
    for word in ([_unquoted(word) for word in raw[start + 1:]] if start is not None else []):
        if word == "--":
            return False
        if word.startswith("--pa") and "parents".startswith(word[2:]):
            return True
    return False


def _made_folders(raw, cwd) -> set:
    """The folders a `mkdir` segment run in `cwd` makes, each with the folders above it that do not exist yet,
    as absolute `os.path.normpath` paths. A flag's value (`-m MODE`) is not one. A brace in quotes is text."""
    start = _cp_start(raw, True, ("mkdir",))
    made, skip = set(), False
    for word in (raw[start + 1:] if start is not None else []):
        plain = _unquoted(word)
        if skip:
            skip = False
        elif plain in ("-m", "--mode"):
            skip = True
        elif not plain.startswith("-"):
            for each in _brace_words(word):
                folder = os.path.normpath(_expanded(_unquoted(each), cwd))
                while folder not in made and not os.path.isdir(folder) and folder != os.path.dirname(folder):
                    made.add(folder)
                    folder = os.path.dirname(folder)
    return made


def _name_matches(names, base: str) -> bool:
    """True when a `find` name filter (`_find_name_filter`) accepts the file name `base`: some branch
    has an include that matches it and no exclude that matches it."""
    def hit(patterns):
        return any(fnmatch.fnmatchcase(base.lower(), pattern.lower()) if fold else fnmatch.fnmatchcase(base, pattern)
                   for fold, pattern in patterns)
    return any(hit(includes) and not hit(excludes) for includes, excludes in names)


def _may_hold_a_test(top: str, cwd: str, predicate) -> bool:
    """True when a test could sit under the folder `top`: `predicate` accepts a test-folder path in it,
    or `top` holds the working folder, and so its checkout. A tree outside every checkout gives False."""
    if predicate(os.path.join(top, "tests", "_"), cwd):
        return True
    try:
        here, root = os.path.realpath(_expanded(".", cwd)), os.path.realpath(top)
        return os.path.commonpath([here, root]) == root
    except (OSError, ValueError):
        return True


def _first_test_under(path: str, cwd: str, predicate, names=None, dest=None, tree=False) -> str:
    """The first path under the folder `path`, at any depth, that `predicate` accepts, else ''. A
    folder that `predicate` accepts as `DIR/_` counts. `.git`, `node_modules` and the virtualenv and
    bytecode folders are not entered. An empty path names no folder.
    `names` is the name filter of the `find` that feeds the path (`_find_name_filter`): only a file whose
    name it accepts is judged, and a folder whose name it accepts is walked whole, as the writer takes
    it whole. A root the filter accepts is walked whole too.
    The cap counts the entries judged and the folders entered: past `_WALK_LIMIT` of them, or past
    `_LIST_LIMIT` entries listed, with folders left to enter, the answer is `_TOO_LARGE` (`_TOO_LARGE_FILTERED`
    when a name filter was in effect), as a walk that
    stops there would let a test past it through. A tree where no test can sit (`_may_hold_a_test`) gives
    '' there instead: nothing past the cap is a test.
    `dest` is the folder a copy writes into: each file is then judged as `dest/<its name>`, the path the copy
    writes, and that path is the answer. A folder entry is not judged.
    `tree` (with `dest`, and no `names`) makes `dest` the folder that `path` itself becomes, as in `cp -r`:
    each file is then judged as `dest/<its path under path>`.
    ponytail: a checkout nested in a tree outside every checkout, past the cap, is not read.
    ponytail: the walk costs one pass over the tree, once per fed writer word that is a folder."""
    if not _unquoted(path).strip():
        return ""
    try:
        top = _expanded(path, cwd)
        if not os.path.isdir(top):
            return ""
    except (OSError, ValueError):
        return ""
    if names and _name_matches(names, os.path.basename(os.path.normpath(_unquoted(path)))
                               or _unquoted(path)):
        names = None
    judged = listed = 0
    walk = os.walk(top)
    for folder, folders, files in walk:
        folders[:] = [name for name in folders if name not in _WALK_SKIP]
        if names is None:
            found_in = [] if dest else [os.path.join(folder, "_")]
            found_in += [os.path.join(folder, name) for name in files]
        else:
            found_in = [os.path.join(folder, name) for name in files if _name_matches(names, name)]
            for name in folders:
                if _name_matches(names, name):
                    whole = _first_test_under(os.path.join(folder, name), cwd, predicate, None, dest)
                    if whole:
                        return _TOO_LARGE_FILTERED if whole == _TOO_LARGE else whole
        for found in found_in:
            written = os.path.join(dest, os.path.relpath(found, top) if tree else os.path.basename(found)) \
                if dest else found
            if predicate(written, cwd):
                return written
        judged += len(folders) + len(found_in)
        listed += len(folders) + len(files)
        if (judged > _WALK_LIMIT or listed > _LIST_LIMIT) and next(walk, None) is not None:
            if not _may_hold_a_test(top, cwd, predicate):
                return ""
            return _TOO_LARGE_FILTERED if names else _TOO_LARGE
    return ""


def _cp_link_source(raw, holds, cwd, keywords=False) -> str:
    """The word of a linking `cp` (`-l`, `-s`, `--link`, `--symbolic-link`, in any cluster) that
    `holds(word, cwd)` accepts, else ''. A link to a frozen file, or to a folder of them, gives the
    new name the frozen file itself, so a later write there writes it. Every operand but a plain
    DEST is judged; with `-t` every operand is, which fails closed."""
    words = [_unquoted(word) for word in raw]
    start = _cp_start(raw, keywords)
    if start is None:
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


# FED PATHS. A writer can take its paths from another command: `find tests | xargs sed -i ...`,
# `find tests -exec sed -i ... {} +`, `for f in tests/*.py; do sed -i ... $f; done`, and
# `sed -i ... $(grep -rl a tests)`. The word the writer shows is `{}`, `$f`, nothing, or a word with a
# paren glued on, so no path in it can be judged. `_fed_command` rewrites each of those forms into the
# plain command the shell would run, with the fed roots put in place, and `_shell_write_hit` judges
# that with the same loop and predicate (`read_fed`). A root is a word that names where a command
# reads, never a word that selects: a `-name` or `-path` value, a grep pattern. Roots are never
# listed from disk (`_holds` does that), so a path that is not there yet is still a root.
# A `while read V` loop that a pipe feeds reads `$V` as the pipe's roots, as a `for` list does.
# ponytail: a `while read` loop fed by redirect (`done < FILE`) or by a substitution, `find -delete`, a
# `$(...)` whose body holds a quoted paren, and a root fed through a variable that a loop or an xargs
# itself assigns are not read.
_MARK = "\0"
_MARK_AT = re.compile("`\0`|\0")
_WORD_MARK = "\x02"   # the mark as `_copy_outer` splits words: `_quoted_words` keeps it, not NUL (\x01 is its newline stand-in)
_FIND_EXEC = ("-exec", "-execdir", "-ok", "-okdir")
_FIND_END = (";", "\\;", "+")
_FIND_TEST_STARTS = ("(", "\\(", "!", "\\!")
_GREP_COMMANDS = frozenset(("grep", "egrep", "fgrep", "rg", "ag", "ack"))
_GREP_PATTERN_LETTERS = "ef"
_GREP_VALUE_LETTERS = "efmABCdDgtTj"
_GREP_PATTERN_FLAGS = frozenset(("--regexp", "--file"))
_GREP_VALUE_FLAGS = _GREP_PATTERN_FLAGS | frozenset((
    "--include", "--exclude", "--exclude-dir", "--include-dir", "--max-count", "--glob", "--iglob",
    "--type", "--type-not", "--context", "--after-context", "--before-context", "--label",
    "--max-depth", "--threads", "--replace", "--devices", "--directories", "--binary-files"))


def _recursive_search(name, args) -> bool:
    """True when a grep-like command with no path searches the working folder: `rg`, `ag` and `ack` always
    do, `grep` with `-r`, `-R` or a long form of them."""
    if name in ("rg", "ag", "ack"):
        return True
    for word in args:
        if word.startswith("--"):
            if word.split("=")[0] in ("--recursive", "--dereference-recursive"):
                return True
        elif word.startswith("-") and len(word) > 1:
            for letter in word[1:]:
                if letter in "rR":
                    return True
                if letter in _GREP_VALUE_LETTERS:
                    break
    return False


def _roots(words, search_cwd=False) -> list:
    """The words of a segment that name where its command reads: for `find`, the words before the
    first `-`, `(` or `!` (`.` when there are none); for grep and rg, the words after the pattern;
    for any other command, its words that are not a flag, a redirect or a redirect's target.
    `search_cwd` reads a recursive grep or rg with no path as `.`: it searches the working folder when
    nothing is piped into it."""
    index = resolve_command(tuple(words))
    if index is None:
        return []
    name, args = _name(words[index]), list(words[index + 1:])
    if name == "find":
        while args and (args[0] in ("-H", "-L", "-P") or re.fullmatch(r"-O\d", args[0])):
            args.pop(0)
        roots = []
        for word in args:
            if word.startswith("-") or word in _FIND_TEST_STARTS:
                break
            roots.append(word)
        return roots or ["."]
    grep = name in _GREP_COMMANDS
    roots, skip, flags_over, has_pattern = [], False, False, False
    for word in args:
        if skip:
            skip = False
        elif (">" in word or "<" in word) and _is_redirect(word):
            skip = True
        elif not flags_over and word == "--":
            flags_over = True
        elif not flags_over and word.startswith("-") and len(word) > 1:
            if grep and word.startswith("--"):
                flag, glued, _value = word.partition("=")
                has_pattern = has_pattern or flag in _GREP_PATTERN_FLAGS
                skip = flag in _GREP_VALUE_FLAGS and not glued
            elif grep:
                for at, letter in enumerate(word[1:], 1):
                    if letter in _GREP_VALUE_LETTERS:
                        has_pattern = has_pattern or letter in _GREP_PATTERN_LETTERS
                        skip = at == len(word) - 1
                        break
        else:
            roots.append(word)
    roots = roots[1:] if grep and not has_pattern else roots
    return roots or (["."] if search_cwd and grep and _recursive_search(name, args) else [])


# The primaries that only narrow what a find lists, by arity. Each is skipped when the name filter is read: the
# names alone then give a superset of the list. An action that prints other text (`-printf`, `-ls`), writes a file
# (`-fprint`) or deletes (`-delete`) is not here, so it leaves the walk plain. `-path` and `-regex` only narrow
# the names a find lists, as `-mtime` does, so they are here.
_FIND_PLAIN = ("-print", "-print0", "-depth", "-xdev", "-mount", "-a", "-and", "-noleaf", "-prune", "-empty",
               "-executable", "-readable", "-writable", "-nouser", "-nogroup", "-true", "-false", "-daystart",
               "-ignore_readdir_race", "-noignore_readdir_race")
_FIND_VALUED = ("-type", "-xtype", "-maxdepth", "-mindepth", "-mtime", "-mmin", "-atime", "-amin", "-ctime", "-cmin",
                "-used", "-size", "-newer", "-anewer", "-cnewer", "-perm", "-user", "-group", "-uid", "-gid", "-links",
                "-inum", "-samefile", "-fstype", "-path", "-ipath", "-regex", "-iregex")
_FIND_NOT = ("!", "\\!", "-not")
_FIND_OR = ("-o", "-or")
# fnmatch reads `[^x]` as a set that holds `^`, and has no `[:class:]`, `[=e=]` or `[.c.]`, where find's glob negates
# or names a class. A pattern that holds one of them is not read: the walk stays plain.
_FNMATCH_UNLIKE_FIND = re.compile(r"[$`\\/]|\[\^|\[[:=.]")


def _find_name_filter(words):
    """The name filter of a `find` segment as a tuple of OR branches, each (includes, excludes), every
    pattern an (ignore case, pattern) pair, else None. A name in a branch is `-name` or `-iname`; one
    after `!` or `-not` is an exclude. Several includes in one branch are read as any of them, a superset
    of the files the find lists. A narrowing primary (`_FIND_PLAIN`, `_FIND_VALUED`, an `-exec` command)
    is skipped, negated or not. Any other word (`(`, `,`, `-delete`, a pattern that
    `_FNMATCH_UNLIKE_FIND` matches), or a branch with no include, leaves the walk plain, which fails closed."""
    index = resolve_command(tuple(words))
    if index is None or _name(words[index]) != "find":
        return None
    args = list(words[index + 1:])
    while args and (args[0] in ("-H", "-L", "-P") or re.fullmatch(r"-O\d", args[0])):
        args.pop(0)
    at = 0
    while at < len(args) and not (args[at].startswith("-") or args[at] in _FIND_TEST_STARTS):
        at += 1
    branches, includes, excludes, negated = [], [], [], False
    while at < len(args):
        word = _unquoted(args[at])
        if word in _FIND_NOT:
            negated = not negated
            at += 1
            continue
        if word in ("-name", "-iname"):
            pattern = _unquoted(args[at + 1]) if at + 1 < len(args) else ""
            if not pattern or _FNMATCH_UNLIKE_FIND.search(pattern):
                return None
            (excludes if negated else includes).append((word == "-iname", pattern))
            at += 2
        elif word in _FIND_OR and not negated:
            branches.append((tuple(includes), tuple(excludes)))
            includes, excludes = [], []
            at += 1
        elif word in _FIND_VALUED:
            at += 2
        elif word in _FIND_PLAIN:
            at += 1
        elif word in _FIND_EXEC:
            at += 1
            while at < len(args) and _unquoted(args[at]) not in _FIND_END:
                at += 1
            if at >= len(args):
                return None
            at += 1
        else:
            return None
        negated = False
    if negated:
        return None
    branches.append((tuple(includes), tuple(excludes)))
    if not all(branch_includes for branch_includes, _excludes in branches):
        return None
    return tuple(branches)


def _walk_filters(texts) -> dict:
    """{root word: name filter} for the roots that a name filter may narrow the walk of. A word has a
    filter only when every place the command text uses it is the root of a `find` that has one (the
    union of their filters); any other use of the word, such as a root of another command, a loop item or
    a word of an `-exec` command, leaves it out, so its walk stays plain."""
    table = {}

    def note(word, names):
        word = _unquoted(word)
        if word in table and table[word] is None or names is None:
            table[word] = None
        else:
            table[word] = tuple(dict.fromkeys(table.get(word, ()) + names))

    for text in texts:
        segments = split_segments(_resolve_vars(text), [])
        for segment in segments:
            words = _quoted_words(segment)
            index = resolve_command(tuple(words))
            if index is not None and _name(words[index]) == "find":
                names = _find_name_filter(words)
                roots = _roots(words)
                for word in roots:
                    note(word, names)
                for word in words[index + 1 + len(roots):]:
                    if word != "{}":
                        note(word, None)
            else:
                for word in [*_roots(words, True), *words]:
                    note(word, None)
    return {word: names for word, names in table.items() if names}


def _piped_into(ends, parsed, at):
    """The index of the segment whose output pipes into segment `at`, else None. A pipe at a line's
    end leaves an empty segment cut at the newline before the next command; it is passed over."""
    back = at - 1
    while back >= 0 and not parsed[back] and ends[back] == "\n":
        back -= 1
    return back if back >= 0 and ends[back] == "|" else None


def _prints_a_count(words) -> bool:
    """True when the segment prints a count of what is piped in, not paths: `wc`, or a grep that
    counts (`-c`, `--count`), with no root of its own. The roots of a pipeline that ends in one are
    not fed on. Narrow on purpose: `grep -l` and `-rl` print paths, and `wc FILE` prints FILE."""
    index = resolve_command(tuple(words))
    if index is None or _roots(words):
        return False
    name = _name(words[index])
    return name == "wc" or name in _GREP_COMMANDS and any(
        word in ("-c", "--count") for word in words[index + 1:])


def _text_roots(text: str) -> list:
    """The roots of every pipeline of a command text, in order, each once. A pipeline that ends in a
    count (`_prints_a_count`) gives none."""
    ends = []
    segments = split_segments(text, ends)
    segments, ends, _changed = _fed_segments(segments, ends)
    parsed = [_quoted_words(segment) for segment in segments]
    fed_by = [_piped_into(ends, parsed, at) for at in range(len(parsed))]
    roots = []
    for at, words in enumerate(parsed):
        if not words or at in fed_by or _prints_a_count(words):
            continue   # empty, not the last of its pipeline, or a count
        chain, stage = [], at
        while stage is not None:
            chain = _roots(parsed[stage], fed_by[stage] is None) + chain
            stage = fed_by[stage]
        roots.extend(word for word in chain if word not in roots)
    return roots


def _fed_substitutions(cmd: str) -> str:
    """`cmd` with each `$(...)`, backtick pair and process substitution read as the roots of its inner
    command. `_substitutions` lists the texts children first, siblings left to right, each parent
    holding one mark per child, so a stack gives each mark its child."""
    texts, too_deep = _substitutions(cmd, mark=_MARK)
    if too_deep or len(texts) < 2:
        return cmd
    stack = []
    for number, (text, _in_message) in enumerate(texts):
        marks = len(_MARK_AT.findall(text))
        if marks > len(stack):
            return cmd
        children = iter(stack[len(stack) - marks:])
        del stack[len(stack) - marks:]
        text = _MARK_AT.sub(lambda _mark: " ".join(next(children)), text)
        if number == len(texts) - 1:
            return text
        stack.append(_text_roots(text))
    return cmd


def _fill_loop_variables(words, loops):
    """`words` with each `$v` and `${v}` of an open `for v in LIST` loop put as one copy of the word
    per list word. A single-quoted word is text."""
    for name, items in loops:
        if not name or not items:
            continue
        variable = re.compile(r"\$\{%s\}|\$%s(?!\w)" % (re.escape(name), re.escape(name)))
        filled = []
        for word in words:
            if word.startswith("'") or not variable.search(word):
                filled.append(word)
            else:
                filled.extend(_put_loop_item(variable, word, item) for item in items)
        words = filled
    return words


_LIST_MAGIC = re.compile(r"[*?\[{]")


def _put_loop_item(variable, word, item) -> str:
    """`word` with each match of `variable` put as `item`. A loop list's glob or brace is expanded when the
    loop starts, so the variable holds its matches: an `item` that holds one, put inside double quotes
    (`"$f"`), leaves those quotes, so the glob is still read as a glob."""
    def put(found):
        if not _LIST_MAGIC.search(item) or word[:found.start()].count('"') % 2 == 0:
            return item
        return '"%s"' % item
    return variable.sub(put, word)


def _put_roots(words, mark, roots):
    """`words` with `mark` in a word put as one copy of the word per root."""
    return [part for word in words
            for part in ([word.replace(mark, root) for root in roots] if mark in word else [word])]


def _piped_roots(ends, parsed, at) -> list:
    """The roots of the pipeline stages that feed segment `at`, first stage first. A pipeline that
    ends in a count (`_prints_a_count`) gives none."""
    roots, back = [], _piped_into(ends, parsed, at)
    if back is not None and _prints_a_count(parsed[back]):
        back = None
    while back is not None:
        before = _piped_into(ends, parsed, back)
        roots = _roots(parsed[back], before is None) + roots
        back = before
    return roots


_READ_VALUE_LETTERS = "dnNptua"


def _read_loop(words, roots):
    """The (variable, list) entry of a `while` or `until` loop whose condition is `words`: `read V`
    over the roots a pipe feeds it, so `$V` in the body reads as each of them. Any other condition
    binds nothing. The first variable of `read A B` takes the first word of each line; `REPLY` is
    the name when `read` has none."""
    at = 0
    while at < len(words) and _ASSIGNMENT.match(words[at]):
        at += 1
    if not roots or words[at:at + 1] != ["read"]:
        return ("", [])
    skip = False
    for word in words[at + 1:]:
        if skip:
            skip = False
        elif word.startswith("-") and len(word) > 1:
            skip = word[-1] in _READ_VALUE_LETTERS
        else:
            return (word, roots)
    return ("REPLY", roots)


def _fed_segments(segments, ends):
    """(segments, ends, changed): the segments with each `for` variable, xargs and `find -exec` put as
    the plain command the shell runs. An xargs command takes the roots of the segments piped into it,
    in the `-I` string's place, else as last words. A `find -exec` segment becomes its commands, with
    `{}` put as the find roots. `_walk_wrappers` already reads the xargs flags."""
    out, out_ends, out_words, loops, changed = [], [], [], [], False
    for number, segment in enumerate(segments):
        words = original = _quoted_words(segment)
        lead = 0
        while lead < len(words) and words[lead] in LOOP_KEYWORDS:
            lead += 1
        head = words[lead] if lead < len(words) else ""
        if head == "for" and words[lead + 2:lead + 3] == ["in"]:
            loops.append((words[lead + 1], words[lead + 3:]))
        elif head == "select" or any(word in ("while", "until") for word in words[:lead]):
            loops.append(_read_loop(words[lead:], _piped_roots(out_ends, out_words, len(out))))
        elif head == "done" and loops:
            loops.pop()
        words = _fill_loop_variables(words, loops)
        rewritten = [words]
        index, chain = _walk_wrappers(tuple(words))
        xargs = next((flags for word, flags in chain if word == "xargs"), None)
        if index is not None and xargs is not None:
            roots = _piped_roots(out_ends, out_words, len(out))
            replace = None
            for flag, value in xargs:
                if flag == "-I":
                    replace = value
                elif flag in ("-i", "--replace"):
                    replace = value or "{}"
            if roots:
                command = words[index:]
                rewritten = [command + roots if not replace else _put_roots(command, replace, roots)]
        elif index is not None and _name(words[index]) == "find":
            roots, commands, at = _roots(words), [], index + 1
            while at < len(words):
                if words[at] in _FIND_EXEC:
                    stop = at + 1
                    while stop < len(words) and words[stop] not in _FIND_END:
                        stop += 1
                    commands.append(_put_roots(words[at + 1:stop], "{}", roots))
                    at = stop
                at += 1
            rewritten = commands or rewritten
        for part, part_words in enumerate(rewritten):
            made = part_words != original or len(rewritten) > 1
            changed = changed or made
            out.append(type(segment)(" ".join(part_words)) if made else segment)
            out_ends.append(ends[number] if part == len(rewritten) - 1 else ";")
            out_words.append(words)   # a later xargs reads roots here: the stage's own words, so a
            # chain of xargs stages, each fed the stages before it, grows by a sum and not a product
    return out, out_ends, changed


def _fed_command(cmd: str):
    """(text, segments, ends) of `cmd` as the shell runs it with the fed roots put in place, else
    None when it holds no fed form or reads as PowerShell."""
    if is_powershell(cmd):
        return None
    text = _fed_substitutions(cmd)
    plain = _resolve_vars(text)
    ends = []
    segments = split_segments(plain, ends)
    segments, ends, changed = _fed_segments(segments, ends)
    return (plain, segments, ends) if changed or text != cmd else None


def _shell_write_hit(cmd: str, cwd: str, predicate, holds=None, follow_cd=False,
                     command_position=False, predicate_command=False, read_fed=False) -> str:
    """Return the path a shell command writes to that `predicate(path, cwd)` accepts, else ''.
    `holds(path, cwd)` tells a folder that holds such a path, for a linking `cp` (`_cp_link_source`).
    `follow_cd` hands `predicate` the folder a leading `cd` moved to (`dir_before_segment`), or `cwd`
    when that folder cannot be told. `predicate_command` also hands `predicate` the segment's command
    name as a third argument (`''` when none).
    `read_fed` reads what main reads, and more: a path that `find`, `xargs`, a `for` list or a
    substitution feeds to a writer. It judges the command as it stands (`_copy_outer` aside), then
    each substitution's inner command as a command of its own, then the command once more as
    `_fed_command` rewrites it. It only adds refusals, except for a `cp` source that is a whole
    substitution (`cp $(find tests -name x) /tmp/`): that is a read (`_copy_outer`). The builder test
    check asks for it, from rule 7c and from `never_lifted` (both call `builder_shell_test_hit`), so
    no other caller's verdict moves."""
    def scan(text, fed=None, copy_outer=False, filters=None):
        return _shell_write_scan(text, cwd, predicate, holds, follow_cd, command_position,
                                 predicate_command, fed, copy_outer, filters, read_fed)

    if not read_fed:
        return scan(cmd)
    texts, too_deep = _substitutions(cmd, powershell=is_powershell(cmd))
    hit = scan(cmd, copy_outer=True)
    for text, _in_message in ([] if too_deep else texts[:-1]):
        hit = hit or scan(text)
    if hit:
        return hit
    fed = _fed_command(cmd)
    return scan(fed[0], fed[1:], filters=_walk_filters([text for text, _in_message in texts] or [cmd])) \
        if fed else ""


def _copy_outer(segment):
    """A `cp` segment whose substitutions are each a whole source word (`$(...)`, a backtick pair,
    quoted or not), as the text around them with an `x` in each one's place, else the segment. Any
    other substitution leaves the segment as main reads it: one in the last word, in a flag, glued to
    a flag (`-t$(...)`, `--target-directory=$(...)`), after a flag that takes the target directory,
    or glued to other text in any word (`tests/$(...)`, `/tmp/$(...)`)."""
    words = _quoted_words(segment)
    index = resolve_command(tuple(words))
    if index is None or _name(words[index]) != "cp" or is_powershell(segment):
        return segment
    texts, too_deep = _substitutions(segment, mark=_MARK)
    if too_deep or len(texts) < 2:
        return segment
    # `_quoted_words` reads NUL as a space, so the mark goes in as a byte it keeps.
    outer = [_unquoted(word) for word in _quoted_words(texts[-1][0].replace(_MARK, _WORD_MARK))]
    for at, word in enumerate(outer):
        if _WORD_MARK not in word:
            continue
        if word not in (_WORD_MARK, "`%s`" % _WORD_MARK) or at == len(outer) - 1 or _takes_target(outer[at - 1]):
            return segment
    return type(segment)(_MARK_AT.sub("x", texts[-1][0]))


def _takes_target(word) -> bool:
    """True when a `cp` word takes the next word as its target directory: a short cluster that ends in
    `t`, or `--target-directory` or a long flag it starts with."""
    if word.startswith("--"):
        return len(word) > 2 and "=" not in word and "target-directory".startswith(word[2:])
    return word.startswith("-") and word.endswith("t")


def _shell_write_scan(cmd, cwd, predicate, holds, follow_cd, command_position, predicate_command,
                      fed=None, copy_outer=False, filters=None, written=False):
    """`_shell_write_hit` for one text. `fed` is the (segments, ends) that `_fed_command` made of it.
    `filters` is `_walk_filters` of the command: the name filter of each fed root's find.
    `written` also judges the path each `cp` writes (`_copy_written_hit`)."""
    holds = holds or (lambda path, where: _holds(path, where, predicate))
    if fed:
        segments, ends = fed
    else:
        cmd = _resolve_vars(cmd)
        ends = []
        segments = split_segments(cmd, ends)
        if copy_outer:
            segments = [_copy_outer(segment) for segment in segments]
    scans = [_scan(segment) for segment in segments]
    parsed = [_quoted_words(segment) for segment in segments]
    # The same words with a quoted newline kept, for a `sh -c` script read at its command positions only:
    # the text the write patterns read keeps newlines as spaces, so a quoted newline never ends a command.
    scripts = [_quoted_words(segment, True) for segment in segments] if command_position else parsed
    closed = any(unsafe or _runs_stored_text(segment, words, plain)
                 for segment, words, (unsafe, plain) in zip(segments, parsed, scans))
    kinds = ["" if closed else _kind(words, plain) for words, (_u, plain) in zip(parsed, scans)]
    quiet = all(kind in ("printer", "cd") or not words for kind, words in zip(kinds, parsed))
    made = set()   # the folders an earlier `mkdir` of this command makes
    for number, raw in enumerate(parsed):
        linked = _cp_link_source(raw, holds, cwd, bool(fed))
        if linked:
            return linked
        data = set() if closed else _copy_reads(raw, predicate, cwd, bool(fed))
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
        cp_at = _cp_start(raw, bool(fed), _TARGET_COMMANDS)
        # A fed `cp` or `mv` writes only its destination, so that word is judged as one, as the direct check does,
        # and is never a walk root. A destination that holds a glob or a variable stays a root, which fails closed.
        dest_at = None
        copy = _copy_parts(raw, True, ("cp", "mv")) if fed else None
        if copy and copy[0] and not _CP_DEST_UNSAFE.search(_copy_target(raw[copy[1]])):
            dest_at = copy[1]
        dest_words = set()
        for index, word in enumerate(raw):
            before = len(words)
            glued = _glued_cp_target(word) if cp_at is not None and index > cp_at else None
            if glued and index not in data:
                # The glued target judged as the spaced `-t DIR` is, by the same text.
                words.extend(glued)
                shown.extend(glued)
                script.extend(glued)
            elif index in data:
                words.append('""')   # data, or a `cp` source: no redirect or `tee` in it runs
                shown.append('""')
                script.append('""')
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
            if index == dest_at:
                dest_words.update(range(before, len(words)))
        text = " ".join(shown)
        at = (dir_before_segment(segments, number, cwd, ends, made=made) or cwd) if follow_cd else cwd
        verb = _segment_command(words)[0] if predicate_command else ""
        for position, word in enumerate(words):
            if word.startswith("-") or REDIRECT.fullmatch(word):
                continue
            if not word or word in (">", ">>"):
                continue
            # A fed writer's word that is a folder writes each test under it: `find . | xargs sed -i`.
            # A data word's `""` stand-in names no folder.
            walked = ""
            if predicate_command:
                hit = predicate(word, at, verb)
            else:
                hit = predicate(word, at)
                if not hit and fed and word != '""' and position not in dest_words:
                    walked = _first_test_under(word, at, predicate, (filters or {}).get(_unquoted(word)))
                    hit = bool(walked)
            if hit and writes_to(word, text, *(_segment_command(script) if command_position else ())):
                return word + _TOO_LARGE_NOTES.get(walked, "")
        if written and not closed and not predicate_command:
            wrote = _copy_written_hit(raw, at, predicate, bool(fed), filters, made)
            if wrote:
                return wrote
            made |= _made_folders(raw, at)
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


def _py_paths(node, env):
    """The path strings an expression can hold: a string, `Path(...)`, `a / b`, `os.path.join`, a
    name bound to one of those, or a chain of path calls. A part it cannot tell (`Path.cwd()`,
    `os.getcwd()`, `__file__`) is left out, so the literal pieces still join: `Path.cwd() / 'tests'`
    reads `tests`. Empty when no piece is known."""
    import ast
    if isinstance(node, ast.Constant):
        return [node.value] if isinstance(node.value, str) else []
    if isinstance(node, ast.Name):
        return list(env.get(node.id, ()))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left, right = _py_paths(node.left, env), _py_paths(node.right, env)
        if not right:
            return left
        return [_join_path(a, b) for a in (left or [""]) for b in right]
    if isinstance(node, ast.Call):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
        if name in _PATH_CTORS or name == "join":
            out = [""]
            for options in (_py_paths(arg, env) for arg in node.args):
                if options:
                    out = [_join_path(a, b) for a in out for b in options]
            return out if out != [""] else []
        if isinstance(func, ast.Attribute) and func.attr in _PATH_PASS:
            return _py_paths(func.value, env)
    return []


def _py_env_at(tree):
    """A function `env_at(node)`: the path each simple `name = <path>` assignment bound, as it stands
    where `node` begins. One pass in source order; a later top-level assignment replaces the value, one
    inside an `if`, loop, `try` or function adds to it, since either may not run."""
    import ast
    top = {id(statement) for statement in tree.body}
    events = sorted(
        (node for node in ast.walk(tree)
         if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)),
        key=lambda node: (node.end_lineno, node.end_col_offset))

    def env_at(call):
        env = {}
        for node in events:
            if (node.end_lineno, node.end_col_offset) > (call.lineno, call.col_offset):
                break
            name, values = node.targets[0].id, _py_paths(node.value, env)
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
