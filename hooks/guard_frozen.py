"""The guard's frozen family: a write to the settings, the hooks or the global CLAUDE.md.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import os
import re

import guard_core
from guard_core import (
    REDIRECT, _expanded, _resolved, _split_heredocs, _strip_heredoc_bodies_unconditionally, _walk_heredocs,
    basename, dir_before_segment, is_powershell, norm, resolve_command, segment_tokens, split_segments,
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


def _perl_in_place(words) -> bool:
    """True when a perl command's switches hold `-i` (an in-place edit, as `sed -i`), alone or in a
    cluster (`-pi`, `-i.bak`, `-pie`). A switch that takes the rest of its word as an argument ends the
    cluster; a word that is no switch ends the switches, so `-i` after a script file is the script's."""
    words = iter(words)
    for word in words:
        if word == "--" or not re.match(r"-[A-Za-z0-9]", word):
            return False
        for at, char in enumerate(word[1:], 1):
            if char == "i":
                return True
            if char in "eE" and at == len(word) - 1:
                next(words, None)   # `-e` at the end of its word: the script is the next word
            if char in "eEFIMmVdDCx":
                break
    return False


def _perl_edits(path: str, cmd: str) -> bool:
    """True when a perl command in CMD edits in place (`_perl_in_place`) and names PATH. CMD is one
    segment of `_shell_write_hit`, so a `;` in a quoted script ends nothing."""
    return any(_perl_in_place(match.group(1).split()) and re.search(re.escape(path), match.group(1))
               for match in re.finditer(r"\bperl(?:\.exe)?\b([^\n]*)", cmd))


def _script_mutates(script: str) -> bool:
    """True when a `sh -c` script may change files through a command of its own. No script found, or one
    with a substitution or group in it, counts as a write, as it always did."""
    if not script or _SCRIPT_RUNS_HIDDEN.search(script):
        return True
    for segment in split_segments(script):
        command, rest = _segment_command([_unquoted(word) for word in _quoted_words(segment, True)])
        # `sed -i` is no mutating word: `writes_to` reads it by its own pattern, so it must get that far.
        if _mutates_as_command(command, rest) or (
                command == "sed" and any(re.match(r"-[a-z]*i\b|--in-place", word) for word in rest)) or (
                command == "perl" and _perl_in_place(rest)):
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
        return (command == "sed" and bool(re.search(r"\bsed\b[^\n;|&]*-i\b[^\n;|&]*" + target, cmd))
                ) or (command == "perl" and _perl_edits(path, cmd))
    if re.search(MUTATING_COMMAND + r"[^\n;|&]*" + target, cmd):
        return True
    if re.search(r"\bsed\b[^\n;|&]*-i\b[^\n;|&]*" + target, cmd):
        return True
    return _perl_edits(path, cmd)


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
# A DEST that is one quoted variable (`"$f"`) stays one word, so it cannot split into `-t dir`. Its
# value is unknown, but a DEST is only ever written, so the sources stay reads.
_QUOTED_VAR = re.compile(r'"\$(?:\w+|\{\w+\})"')


def _cp_start(raw) -> int:
    """The index of the `cp` command word of a segment, past assignments, a loop keyword (`do`, `then`,
    `else`, `{`) and a wrapper, by the one reader `resolve_command`; -1 when the segment runs no `cp`."""
    start = resolve_command(tuple(raw))
    return start if start is not None and _name(raw[start]) == "cp" else -1


def _copy_reads(raw, predicate, cwd):
    """The indexes of the words of a `cp` segment that are only read, else an empty set."""
    words = [_unquoted(word) for word in raw]
    start = _cp_start(raw)
    if start < 0:
        return set()
    operands, target, index, shown = [], None, start + 1, ""
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
            shown = raw[index - 1]
            continue
        if word.startswith("--target-directory="):
            target, shown = word.split("=", 1)[1], ""
        elif word.startswith("-t") and len(word) > 2 and word[1] != "-":
            target, shown = word[2:], ""
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
        shown = raw[operands[-1]]
        target = words[operands.pop()]
    if not operands or not target or (_CP_DEST_UNSAFE.search(target) and not _QUOTED_VAR.fullmatch(shown)):
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
    start = _cp_start(raw)
    if start < 0:
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
            elif index and re.fullmatch(_DESCRIPTOR, word) and _is_redirect(raw[index - 1]):
                # Never judged as a path. `dup` stays in the text so `2> PATH` is not read as `> PATH`.
                # The raw word is unquoted: a quoted "&1" is a file and is judged.
                shown.append("dup")
            else:
                pieces = _words_of(word) if "'" in word or '"' in word else [word]
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
# `ast` cannot parse is read by a literal path beside a write call. Node, perl and ruby are read by pattern.
_PY_HEADER = re.compile(r"(?<![\w.-])python[\d.]*(?:\.exe)?(?![\w.-])")
_NODE_HEADER = re.compile(r"(?<![\w.-])(?:node|nodejs|bun|deno)(?:\.exe)?(?![\w.-])")
_PERL_HEADER = re.compile(r"(?<![\w.-])perl(?:\.exe)?(?![\w.-])")
_RUBY_HEADER = re.compile(r"(?<![\w.-])ruby(?:\.exe)?(?![\w.-])")
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


# Names that let a python script hand text to a shell or run it as code. A script whose parse tree
# holds none of them cannot make a string in it a shell line. Judged by parsed names, never by words in a string.
_PY_RUNS_TEXT = frozenset((
    "os", "subprocess", "shutil", "importlib", "exec", "eval", "__import__", "compile", "pty", "ctypes",
    "runpy", "builtins", "getattr", "globals", "vars", "posix", "nt", "_os", "modules", "asyncio"))
_PY_PLAIN_DUNDERS = ("__name__", "__file__", "__doc__")
_PY_CODING = re.compile(r"^[ \t]*#.*coding[:=][ \t]*(?![ \t]|utf-?8\b)", re.IGNORECASE | re.MULTILINE)


# The subprocess calls that start a program from a list argv. `_py_list_argv_call` clears one of them.
_PY_ARGV_CALLS = frozenset(("run", "call", "check_call", "check_output", "Popen"))
# Shells and wrappers that take a command line as text: a list argv that starts with one is a shell run.
_PY_SHELL_NAMES = frozenset((
    "sh", "bash", "zsh", "dash", "ksh", "fish", "pwsh", "powershell", "cmd", "env", "csh", "tcsh", "ash",
    "busybox"))


def _py_list_argv_call(node) -> bool:
    """True when NODE is `subprocess.<run|call|check_call|check_output|Popen>(...)` that runs a program
    with no shell: the first argument is a list or tuple literal; its first element is a string that is
    not a shell name, or `sys.executable`; `shell=` is absent or the literal False; and there is no
    `**kwargs` and no `executable=`, which would swap the program the argv names."""
    import ast
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr in _PY_ARGV_CALLS
            and isinstance(func.value, ast.Name) and func.value.id == "subprocess"):
        return False
    if not node.args or not isinstance(node.args[0], (ast.List, ast.Tuple)) or not node.args[0].elts:
        return False
    first = node.args[0].elts[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        if os.path.splitext(basename(first.value))[0] in _PY_SHELL_NAMES or not first.value:
            return False
    elif not (isinstance(first, ast.Attribute) and first.attr == "executable"
              and isinstance(first.value, ast.Name) and first.value.id == "sys"):
        return False
    for keyword in node.keywords:
        if keyword.arg is None or keyword.arg == "executable":
            return False
        if keyword.arg == "shell" and not (
                isinstance(keyword.value, ast.Constant) and keyword.value.value is False):
            return False
    return True


def python_body_is_text(body: str) -> bool:
    """True when BODY parses with `ast` and its tree names none of _PY_RUNS_TEXT and no dunder but
    `__name__`, `__file__` and `__doc__`, in an import, a name or an attribute. A string, a comment and an
    f-string's text are never read as names. A body that does not parse, or declares a source encoding
    other than utf-8, is not text. One name is cleared: `subprocess` in `import subprocess`, or as the
    owner of a call `_py_list_argv_call` accepts. Any other use of it keeps the body out. What such a
    body writes to a file is `_py_hit`'s to judge."""
    import ast
    import textwrap
    if _PY_CODING.search("\n".join(body.split("\n")[:2])):
        return False
    try:
        tree = ast.parse(textwrap.dedent(body))
    except Exception:   # a syntax error, a null byte, a tree too deep to parse
        return False
    cleared = set()   # ids of the `subprocess` Name nodes, and of the plain `import subprocess` aliases
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _py_list_argv_call(node):
            cleared.add(id(node.func.value))
        elif isinstance(node, ast.Import):
            cleared.update(id(alias) for alias in node.names if alias.name == "subprocess" and not alias.asname)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name.split(".")[0] for alias in node.names if id(alias) not in cleared]
        elif isinstance(node, ast.ImportFrom):
            names = [(node.module or "").split(".")[0]] + [alias.name for alias in node.names]
        elif isinstance(node, (ast.Name, ast.Attribute)):
            if id(node) in cleared:
                continue
            names = [node.id if isinstance(node, ast.Name) else node.attr]
        else:
            continue
        for name in names:
            if name in _PY_RUNS_TEXT or (name.startswith("__") and name not in _PY_PLAIN_DUNDERS):
                return False
    return True


_PY_ARGUMENT = re.compile(r"-|-[BEIORSbdqsuv]+|<<-?[A-Za-z_]\w*")


def _python_header_alone(raw: str, header: str) -> bool:
    """True when RAW, with its heredoc bodies stripped, is the one line HEADER, and that line is one
    segment: a python that reads its program from the heredoc, with plain flags only. A pipe, a redirect,
    `;`, `&&`, `&`, `$(`, a backtick, `{`, `(`, a function, a loop or any other line fails, since a shell
    may run what the body prints."""
    if [line for line in _strip_heredoc_bodies_unconditionally(raw).split("\n") if line.strip()] != [header]:
        return False
    ends = []
    segments = split_segments(header, ends)
    tokens = segment_tokens(segments[0]) if len(segments) == 1 and ends == [""] else None
    return (bool(tokens) and bool(_PY_COMMAND.match(basename(tokens[0])))
            and all(_PY_ARGUMENT.fullmatch(word) for word in tokens[1:])
            and sum(word.startswith("<<") for word in tokens) == 1)


# The extensions of a file that holds text a shell does not run. A python body that writes any other name,
# a name with no extension, or a name it cannot read, stays in view: its strings may be a script's lines.
_PY_TEXT_EXTENSIONS = frozenset((".json", ".md", ".txt", ".csv"))


def _python_writes_text_files_only(body: str) -> bool:
    """True when every file the parsed BODY writes (`_py_written`) has a literal name that ends in one of
    `_PY_TEXT_EXTENSIONS`. A body that does not parse is not."""
    import ast
    import textwrap
    try:
        tree = ast.parse(textwrap.dedent(body))
        env_at = _py_env_at(tree)
        for call, expression in _py_written(tree, env_at):
            paths = _py_paths(expression, env_at(call))
            if not paths or any(
                    os.path.splitext(basename(path))[1].lower() not in _PY_TEXT_EXTENSIONS for path in paths):
                return False
    except Exception:
        return False   # unread: the body stays in view
    return True


def drop_text_python_bodies(raw: str) -> str:
    """RAW with the lines of a quoted python heredoc body dropped, for a rule that reads shell lines. It
    drops only when RAW is that one heredoc and nothing else (`_python_header_alone`), the body is text
    (`python_body_is_text`), it writes only text files (`_python_writes_text_files_only`), and all three
    readings of the walk (bash's, the contraction one, main's) give the same one body. Else RAW is kept."""
    if "<<" not in raw:
        return raw
    walks = []   # (span, body) of each reading
    for contractions, legacy in ((False, False), (True, False), (False, True)):
        spans = []
        _, bodies, unclosed = _walk_heredocs(raw, contractions, legacy, body_spans=spans)
        if unclosed or len(bodies) != 1:
            return raw
        walks.append((spans[0], bodies[0]))
    span, (quote, body, header) = walks[0]
    if (quote and all(walk == walks[0] for walk in walks)
            and _python_header_alone(raw, header) and python_body_is_text(body)
            and _python_writes_text_files_only(body)):
        return "\n".join(line for at, line in enumerate(raw.split("\n")) if not span[0] <= at < span[1])
    return raw


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


# A perl or ruby body is read by literal path, as node is: the written operand of a write call is a string,
# or a variable a plain assignment bound. Each pattern ends in the three groups of that operand (_RB_STR):
# single-quoted, double-quoted, a name.
_RB_STR = r"""(?:'([^'\n]*)'|"([^"\n]*)"|[\$@]?([A-Za-z_]\w*))"""
_PL_OPEN = r"""\bopen\s*\(?\s*(?:my\s+)?[\$\w]+\s*,\s*['"]\s*"""
_PL_RB_ASSIGN = re.compile(r"""(?<![\w$@])[\$@]?([A-Za-z_]\w*)\s*=\s*(?:'([^'\n]*)'|"([^"\n]*)")""")
_PL_RB_WRITE = (
    re.compile(_PL_OPEN + r"""(?:\+<|\+?>>?)[^'"]*['"]\s*,\s*""" + _RB_STR),              # perl 3-arg open
    re.compile(_PL_OPEN + r"""\+?>>?\s*()([^'"\s]+)['"]()"""),                            # perl 2-arg open
    re.compile(r"\b(?:rename|copy|move|FileUtils\s*\.\s*(?:cp|mv|cp_r|copy_file|install))(?:\s*\(\s*|\s+(?=['\"$]))"
               + _RB_STR + r"\s*,\s*" + _RB_STR),                                          # destination of a copy
    re.compile(r"\b(?:File|IO)\s*\.\s*(?:write|binwrite)\s*\(?\s*" + _RB_STR),
    re.compile(r"""\bFile\s*\.\s*open\s*\(?\s*""" + _RB_STR + r"""\s*,\s*['"][^'"]*[wa+][^'"]*['"]"""),
)


def _pl_rb_code(body: str) -> str:
    """BODY with each string's contents and each `#` comment blanked to spaces, so offsets stay aligned
    with BODY. A write call is a hit only where this copy still shows its first character; the path is
    read from BODY. Strings are '...' and "..." with backslash escapes and may span lines. A quote
    that finds no closer stays code, so a stray one hides nothing after it. `$#`, `$'` and `$"` are
    variables, not openers. Known limit: `#{...}` inside a ruby string and `%q()` strings are not
    read as code."""
    out = list(body)
    i, n = 0, len(body)
    while i < n:
        ch = body[i]
        if ch == "$":
            i += 2
        elif ch == "#":
            end = body.find("\n", i)
            end = n if end < 0 else end
            out[i:end] = " " * (end - i)
            i = end
        elif ch in "'\"":
            at = i + 1
            while at < n and body[at] != ch:
                at += 2 if body[at] == "\\" else 1
            if at >= n:
                i += 1
                continue
            for k in range(i + 1, at):
                if body[k] != "\n":
                    out[k] = " "
            i = at + 1
        else:
            i += 1
    return "".join(out)


def _pl_rb_hit(body: str, cwd: str, predicate) -> str:
    code = _pl_rb_code(body)

    def in_code(match):
        return code[match.start()] == body[match.start()]

    env = {}
    for match in _PL_RB_ASSIGN.finditer(body):
        if in_code(match):
            env.setdefault(match.group(1), []).append(
                match.group(2) if match.group(2) is not None else match.group(3))
    for pattern in _PL_RB_WRITE:
        at = 0
        while True:
            match = pattern.search(body, at)
            if not match:
                break
            at = match.start() + 1   # a match that starts in a string must not hide one that starts in code
            if not in_code(match):
                continue
            single, double, name = match.groups()[-3:]
            for path in [single or double] if single or double else env.get(name, ()):
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


def interpreter_may_write(raw: str) -> bool:
    """True when `raw` holds a heredoc or an inline flag and a write call an interpreter body could make:
    the cheap match that gates `interpreter_write_hit` for a caller that pays to learn its predicate."""
    return ("<<" in raw or any(flag in raw for flag in _INLINE_FLAG_WORDS)) and bool(
        _PY_WRITE_CALL.search(raw) or _JS_ONE.search(raw) or _JS_TWO.search(raw)
        or any(pattern.search(raw) for pattern in _PL_RB_WRITE))


def interpreter_write_hit(raw: str, cwd: str, predicate) -> str:
    """Return the path a python, node, perl or ruby script in `raw` writes that `predicate(path, cwd)`
    accepts, else ''. Read: the body of each heredoc fed to one of them, quoted or not, and each
    `python -c` and `node -e` script. A script that only reads a path, or names it in a string, hits nothing.
    A crash of the scan reads as no hit: it must never skip the rules after it."""
    try:
        return _interpreter_write_hit(raw, cwd, predicate)
    except Exception:
        return ""


def _header_dir(segments, ends, header: str, nth: int, cwd: str) -> str:
    """The folder the shell is in when the command that holds a heredoc's header runs: the NTH segment (the last, when
    fewer) of SEGMENTS that sits inside HEADER and holds `<<`, so a leading `cd` moves the body's relative paths as it
    moves a `python -c` script's. CWD when no such segment is found or the folder cannot be told."""
    holding = [at for at, segment in enumerate(segments) if "<<" in segment and segment.strip() in header]
    if not holding:
        return cwd
    try:
        return dir_before_segment(segments, holding[min(nth, len(holding) - 1)], cwd, ends) or cwd
    except Exception:
        return cwd


def _interpreter_write_hit(raw: str, cwd: str, predicate) -> str:
    if "<<" in raw:
        seen = set()
        ends = []
        segments = split_segments(_strip_heredoc_bodies_unconditionally(raw), ends)
        for reading in (False, True):   # bash's own walk, and the one where a contraction's `'` is text
            earlier = {}   # header line -> bodies seen on it so far in this reading
            for _quote, body, header in _split_heredocs(raw, reading)[1]:
                nth = earlier[header] = earlier.get(header, -1) + 1
                at = _header_dir(segments, ends, header, nth, cwd)
                if (header, body, at) in seen:
                    continue
                seen.add((header, body, at))
                if _PY_HEADER.search(header):
                    reader = _py_hit
                elif _NODE_HEADER.search(header):
                    reader = _js_hit
                elif _PERL_HEADER.search(header) or _RUBY_HEADER.search(header):
                    reader = _pl_rb_hit
                else:
                    continue
                hit = reader(body, at, predicate)
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
