"""The guard's frozen family: a write to the settings, the hooks or the global CLAUDE.md.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import os
import re

import guard_core
from guard_core import (
    PS_DOUBLE_QUOTES, PS_SINGLE_QUOTES, PS_STRAIGHT_QUOTES, REDIRECT, PowerShellScript, _expanded, _resolved,
    _split_heredocs, _strip_heredoc_bodies_unconditionally, basename, dir_before_segment, is_powershell,
    nested_script, norm, resolve_command, segment_tokens, split_segments,
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
# `sc`, `ac`, `cpi` and `ni` are PowerShell aliases that are also ordinary words (`grep -n ac`, `diff ni`), so
# they count only as the segment's own command (`_ALIAS_COMMAND`), never as a word anywhere in it.
_ALIAS_COMMAND = r"(?i:sc|ac|cpi|ni)"
_MUTATING_ANYWHERE = (
    r"(?i:rm|mv|cp|chmod|truncate|tee|install|ln"
    r"|set-content|add-content|clear-content|out-file|new-item|remove-item|move-item|copy-item"
    r"|rename-item|set-itemproperty|ri|rd|rmdir|del|erase|move|copy|ren)"
)
# The full list, for a command already in command position and for a quick hint.
MUTATING_COMMAND = r"\b(?:" + _MUTATING_ANYWHERE + "|" + _ALIAS_COMMAND + r")\b"
_MUTATING_ANYWHERE_RE = r"\b" + _MUTATING_ANYWHERE + r"\b"
# Where an alias is a command: first in the segment, or the first word of a `{`, `(` or `$(` block, or after a
# dot-source (`.`) or call (`&`) word. In `grep -n ac F` or `diff ni F` it is only a word.
# An assignment (`$f = ni`), a cast (`[void] ni`), a closing paren (`param($p) ni`) and `return ni` leave it in
# command position. `_COMMAND_POSITION` is the text before such a command, for the alias and for `_lead_command`.
_COMMAND_POSITION = (r"(?:^\s*|[{()]\s*|\]\s*|(?:^|\s)[.&]\s+|(?i:\breturn)\s+"
                     r"|\$[\w:.]+(?:\[[^\]]*\])?\s*[-+*]?=\s*)")
_ALIAS_POSITION = _COMMAND_POSITION + _ALIAS_COMMAND + r"\b"


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
    if re.search(_MUTATING_ANYWHERE_RE + r"[^\n;|&]*" + target, cmd):
        return True
    # No command given: an alias writes only as the segment's own command (through a wrapper such as `env`
    # too) or where `_ALIAS_POSITION` reads it as one.
    name = _segment_command(cmd.split())[0]
    if re.search(_ALIAS_POSITION + r"[^\n;|&]*" + target, cmd) or (
            re.fullmatch(_ALIAS_COMMAND, name) and re.search(r"\b" + _ALIAS_COMMAND + r"\b[^\n;|&]*" + target, cmd)):
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
    """Read each `$VAR` or `${VAR}` as the value assigned earlier in the command. The text keeps its
    type, so a script that pwsh runs (PowerShellScript) is still read by PowerShell's rules after."""
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

    return type(cmd)(_VAR_TOKEN.sub(step, cmd))


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
# as a quote, even inside single quotes, so text with one is never data; a word that holds one is read
# with it as a quote, `_unquoted`): the shell may then read its quotes differently from the
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
_SMART_QUOTES = frozenset(PS_DOUBLE_QUOTES + PS_SINGLE_QUOTES)
_GROUP_MARK = re.compile(r"[&(){}]")
_STATEMENT_END = re.compile(r"[;|\n]")
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


def _typed(text: str, like: str) -> str:
    """`text` with the PowerShell type of `like`, so the reading follows a word to the next reader."""
    return PowerShellScript(text) if isinstance(like, PowerShellScript) else text


def _straight(word: str) -> str:
    """In PowerShell text, the word with each smart quote spelled as its ASCII twin. Bash text is as it is."""
    return _typed(word.translate(PS_STRAIGHT_QUOTES), word) if is_powershell(word) else word


def _has_quote(word: str) -> bool:
    """True when the word holds a quote mark: ASCII, or a smart quote in PowerShell text."""
    return "'" in word or '"' in word or (is_powershell(word) and any(c in _SMART_QUOTES for c in word))


def _unquoted(word: str) -> str:
    """The shell word after quote removal: `a/'b.py'` reads `a/b.py`. A quote inside the other
    kind of quote is text. The `$` of an unquoted `$'...'` or `$"..."` goes with the quote.
    In PowerShell text a smart quote is a quote too (`_straight`).
    RESIDUAL GAP: a backslash escape inside `$'...'` (hex or octal) is not decoded."""
    out, quote = [], ""
    word = _straight(word)
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
    word = _straight(word)
    inner = _typed(_unquoted(word), word)
    out = [inner] + [_unquoted(_typed(w, word)) for w in _quoted_words(inner)]   # a quoted script, read again
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


# The PowerShell twins of `cp` and of a write of text. `Copy-Item SRC DEST` writes only DEST. `Add-Content`
# and `Set-Content PATH TEXT...` write only PATH: a quoted word after it is the text written. Only the
# switches below and plain positional words are read; any other parameter (`-Destination`, `-Value`,
# `-Path`) or a redirect fails closed to a hit, as `-Destination` does for `cp`.
_PS_COPY = frozenset(("copy-item", "copy", "cpi", "cp"))
_PS_CONTENT = frozenset(("add-content", "set-content", "ac", "sc"))
# The parameters that take no value. Any parameter not known to take a value or none may take the next word.
_PS_SWITCH_FLAGS = ("recurse", "force", "container", "passthru", "verbose", "confirm", "whatif", "nonewline",
                    "append", "noclobber", "debug")
_PS_SWITCH = re.compile(r"-(?i:" + "|".join(_PS_SWITCH_FLAGS) + ")")


def _is_folder(target, cwd) -> bool:
    """True when a copy's destination is a folder: a trailing slash, or a folder that exists."""
    try:
        return target.endswith(("/", "\\")) or os.path.isdir(_expanded(target, cwd))
    except (OSError, ValueError):
        return False


def _only_read(operands, words, target, predicate, cwd, is_folder=False):
    """The copy operands (indexes into `words`) that are only read. A copy into a folder (`is_folder`, a
    trailing slash, or a folder that exists) writes `FOLDER/<each source's name>`, so a source whose
    name that folder path makes a hit is written, not read."""
    if not (is_folder or _is_folder(target, cwd)):
        return set(operands)
    head = target.rstrip("/\\")
    return {i for i in operands
            if not predicate(head + "/" + re.split(r"[/\\]", words[i].rstrip("/\\"))[-1], cwd)}


def _outside_quotes(word: str) -> str:
    """The word with each quoted span removed, so a comma inside quotes is text and one outside is syntax."""
    return re.sub(r"'[^']*'|\"[^\"]*\"", "", _straight(word))


def _comma_joined(words, raw, index, start) -> bool:
    """True when the word at `index` belongs to a comma list: it ends with a comma, starts with one, or
    follows a word that ends with one. Only a comma outside quotes joins (`"a.md", "b"` joins, `"a,b"`
    is one path)."""
    here = _outside_quotes(raw[index])
    return here.endswith(",") or (index > start + 1 and (
        here.startswith(",") or _outside_quotes(raw[index - 1]).endswith(",")))


def _ps_reads(name, raw, words, start, predicate, cwd, plain):
    """`_copy_reads` for a PowerShell `Copy-Item` (its sources) or `Add-Content` / `Set-Content` (the
    quoted text after the path): the indexes of the words that are only read or only text. A `;`, `|` or
    newline outside quotes means the segment holds a second statement the split missed: none is read."""
    if _GROUP_MARK.search(_FD_DUP.sub("", plain)) or _STATEMENT_END.search(plain):
        return set()
    operands = []
    for index in range(start + 1, len(words)):
        word = words[index]
        if ">" in word or "<" in word or (word.startswith("-") and not _PS_SWITCH.fullmatch(word)):
            return set()
        if not _PS_SWITCH.fullmatch(word):
            operands.append(index)
    if name in _PS_CONTENT:
        # A comma list is one argument: in a path slot it names several paths (`a.md, 'b'` writes both), so no
        # word is text; after the path slots it is the text written. A copy's comma list is judged below.
        arguments = []
        for at, index in enumerate(operands):
            if at and (_outside_quotes(raw[operands[at - 1]]).endswith(",") or raw[index].startswith(",")):
                arguments[-1].append(index)
            else:
                arguments.append([index])
        paths = _PATH_POSITIONS[name]
        if any(len(argument) > 1 for argument in arguments[:paths]):
            return set()
        return {i for argument in arguments[paths:] for i in argument if _has_quote(raw[i])}
    if len(operands) < 2:
        return set()
    target = words[operands[-1]]
    if "," in target or _comma_joined(words, raw, operands[-1], start):
        return set()
    if _CP_DEST_UNSAFE.search(target) or predicate(target, cwd) or predicate(target.rstrip("/\\") + "/_", cwd):
        return set()
    return _only_read(operands[:-1], words, target, predicate, cwd)


def _copy_reads(raw, predicate, cwd, plain=""):
    """The indexes of the words of a `cp` segment that are only read, else an empty set. `plain` is the
    segment's text outside quotes, for the PowerShell twins (`_ps_reads`)."""
    words = [_unquoted(word) for word in raw]
    start = next((i for i, word in enumerate(raw) if not _ASSIGNMENT.match(word)), len(raw))
    name = _name(raw[start] if start < len(raw) else "")
    # `cp` is read by the Bash parser below in both shells: its flags (`-t`, `-l`) are Bash's.
    if (name in _PS_COPY and name != "cp") or name in _PS_CONTENT:
        return _ps_reads(name, raw, words, start, predicate, cwd, plain)
    if name != "cp":
        return set()
    operands, target, index, is_folder = [], None, start + 1, False
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
            target, index, is_folder = (words[index + 1] if index + 1 < len(words) else None), index + 2, True
            if target is None:
                return set()
            continue
        if word.startswith("--target-directory="):
            target, is_folder = word.split("=", 1)[1], True
        elif word.startswith("-t") and len(word) > 2 and word[1] != "-":
            target, is_folder = word[2:], True
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
    return _only_read(operands, words, target, predicate, cwd, is_folder)


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
                     command_position=False, predicate_command=False, listed=None) -> str:
    """Return the path a shell command writes to that `predicate(path, cwd)` accepts, else ''.
    `holds(path, cwd)` tells a folder that holds such a path, for a linking `cp` (`_cp_link_source`).
    `follow_cd` hands `predicate` the folder a leading `cd` moved to (`dir_before_segment`), or `cwd`
    when that folder cannot be told. `predicate_command` also hands `predicate` the segment's command
    name as a third argument (`''` when none). `listed` holds the folders a listing piped into the text may
    be, so `$_` may name a file in one (`_pipe_variable_hit`)."""
    holds = holds or (lambda path, where: _holds(path, where, predicate))
    cmd = _resolve_vars(cmd)
    ends = []
    segments = split_segments(cmd, ends)
    scans = [_scan(segment) for segment in segments]
    parsed = [[_typed(word, segment) for word in _quoted_words(segment)] for segment in segments]
    # The same words with a quoted newline kept, for a `sh -c` script read at its command positions only:
    # the text the write patterns read keeps newlines as spaces, so a quoted newline never ends a command.
    scripts = ([[_typed(word, segment) for word in _quoted_words(segment, True)] for segment in segments]
               if command_position else parsed)
    closed = any(unsafe or _runs_stored_text(segment, words, plain)
                 for segment, words, (unsafe, plain) in zip(segments, parsed, scans))
    # A copy or a written text is read through PowerShell's own quotes: a smart quote is a quote there, so the
    # straightened text is what PowerShell sees. Only a printer's data stays closed by a smart quote.
    straight = [_scan(_straight(segment)) for segment in segments]
    reading_closed = any(unsafe or _runs_stored_text(segment, words, plain)
                         for segment, words, (unsafe, plain) in zip(segments, parsed, straight))
    # The reads come from the same straightened text, so a copy or a written text is cut where PowerShell cuts it.
    # An index into those words is an index into the segment's words only when they are the ones judged below.
    read_words = [[_typed(word, segment) for word in _quoted_words(_straight(segment))]
                  if is_powershell(segment) else words for segment, words in zip(segments, parsed)]
    read_scripts = ([[_typed(word, segment) for word in _quoted_words(_straight(segment), True)]
                     if is_powershell(segment) else words for segment, words in zip(segments, scripts)]
                    if command_position else read_words)
    kinds = ["" if closed else _kind(words, plain) for words, (_u, plain) in zip(parsed, scans)]
    quiet = all(kind in ("printer", "cd") or not words for kind, words in zip(kinds, parsed))
    carry, carry_depth = None, 0
    for number, raw in enumerate(parsed):
        linked = _cp_link_source(raw, holds, cwd)
        if linked:
            return linked
        data = set() if reading_closed else _copy_reads(read_words[number], predicate, cwd, straight[number][1])
        from_reads = bool(data)
        if from_reads:
            raw = read_words[number]
        powershell = is_powershell(segments[number])
        # A `( )` group outside the command's path slots is judged as a command of its own, below.
        groups = _ps_inner_groups(raw) if powershell else []
        grouped = {index: span[0] for span, _inner in groups for index in span}
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
            if index in grouped:
                if grouped[index] == index:   # the group is one argument of the outer command
                    words.append('""')
                    shown.append('""')
                    script.append('""')
            elif index in data:
                words.append('""')   # data, or a `cp` source: no redirect or `tee` in it runs
                shown.append('""')
                script.append('""')
            elif index and re.fullmatch(_DESCRIPTOR, word) and _is_redirect(raw[index - 1]):
                # Never judged as a path. `dup` stays in the text so `2> PATH` is not read as `> PATH`.
                # The raw word is unquoted: a quoted "&1" is a file and is judged.
                shown.append("dup")
            else:
                pieces = _words_of(word) if _has_quote(word) else [word]
                words.extend(pieces)
                shown.extend(pieces)
                kept = (read_scripts if from_reads else scripts)[number][index]
                script.extend(_words_of(kept) if _has_quote(kept) else [kept])
        text = " ".join(shown)
        at = (dir_before_segment(segments, number, cwd, ends) or cwd) if follow_cd else cwd
        verb = _segment_command(words)[0] if predicate_command else ""
        scripts_run = _powershell_scripts_of(segments[number])
        for nested in scripts_run:
            # a script pwsh, `cmd /c` or iex runs is PowerShell text: judge it by PowerShell's rules too
            hit = _shell_write_hit(nested, at, predicate, holds, follow_cd, command_position, predicate_command)
            if hit:
                return hit
        command_args = _segment_command(script) if command_position else ()
        if command_args and not _mutates_as_command(*command_args):
            command_args = _lead_command(segments[number]) or command_args
        if command_args and scripts_run and command_args[0] in _PS_SHELLS:
            # the script this shell runs was judged above by PowerShell's own rules; only a redirect on the shell is left
            command_args = ("", ())
        current = listed
        if command_position and powershell:
            # A command inside a scriptblock is a command of its own; `ls | % { Set-Content $_ x }` writes
            # each listed file, so a write whose target is `$_` is judged as the folder listed. A pipe inside
            # the block splits it into segments: the listing holds until the block's brace closes.
            blocks, delta = _ps_blocks(segments[number])
            here = _listed_folder(parsed, ends, number)
            current = here or (carry if carry_depth > 0 else None) or listed
            carry, carry_depth = (here, delta) if here else (carry, carry_depth + delta)
            for inner in blocks:
                hit = _shell_write_hit(inner, at, predicate, holds, follow_cd, command_position,
                                       predicate_command, current)
                if hit:
                    return hit
        for _span, inner in groups:
            hit = _shell_write_hit(_typed(inner, segments[number]), at, predicate, holds, follow_cd,
                                   command_position, predicate_command, current)
            if hit:
                return hit
        pipe_hit = _pipe_variable_hit(command_args, current, at, predicate, holds) if current is not None else ""
        if pipe_hit:
            return pipe_hit
        for word in words:
            if word.startswith("-") or REDIRECT.fullmatch(word):
                continue
            if not word or word in (">", ">>"):
                continue
            # A PowerShell comma joins paths into one argument: each piece is a path of its own.
            pieces = [word] + ([piece for piece in word.split(",") if piece] if powershell and "," in word else [])
            if powershell and word.endswith((")", "}")):
                pieces.append(word.rstrip(")}"))   # the paren or brace that closes the command's group
            for piece in pieces:
                if (predicate(piece, at, verb) if predicate_command else predicate(piece, at)) and \
                        writes_to(piece, text, *command_args):
                    return piece
    return ""


_LISTERS = frozenset(("ls", "dir", "gci", "get-childitem"))
# A stage between a listing and the block that passes each listed item on unchanged or in part.
_LIST_FILTERS = frozenset(("where-object", "where", "?", "select-object", "select", "sort-object", "sort"))
# `$_` or `$PSItem` as a path word: bare, with a member (`$_.FullName`), in parentheses, in a `$(...)`, or bound
# to a parameter by a colon (`-Path:$_`).
# A member may be called (`$_.FullName.ToString()`), and the variable may be braced (`${_}`).
_PIPE_VARIABLE = re.compile(
    r"(?:-\w+:)?\(*(?:\$\(+)?(?:\$(?:_|psitem)|\$\{(?:_|psitem)\})(?:\.\w+(?:\([^()]*\))?)*\)*", re.IGNORECASE)
# The common parameters that take a value, with their aliases. The word after one is its value, never a path.
_PS_COMMON_VALUE_FLAGS = ("erroraction", "warningaction", "informationaction", "errorvariable", "warningvariable",
                          "informationvariable", "outvariable", "outbuffer", "pipelinevariable", "progressaction",
                          "ea", "wa", "infa", "ev", "wv", "iv", "ov", "ob", "pv", "proga")
# What a `Get-ChildItem` parameter takes: a value that is the listed folder, a value that only filters it, or
# nothing. Matching is by prefix, as PowerShell does.
_LIST_PATH_FLAGS = ("path", "literalpath")
_LIST_FILTER_FLAGS = ("filter", "include", "exclude", "depth", "attributes")
_LIST_SWITCH_FLAGS = ("name", "directory", "file", "hidden", "readonly", "system", "followsymlink") + _PS_SWITCH_FLAGS


def _flag_is(name: str, full_names, shortest: int = 1) -> bool:
    """True when the parameter `name` (no dash) is a prefix of one of `full_names`, as PowerShell abbreviates."""
    return len(name) >= shortest and any(full.startswith(name) for full in full_names)


def _listed_folder(parsed, ends, number):
    """The folders a listing (`ls`, `dir`, `gci`, `Get-ChildItem`) may hand to segment `number` through a pipe
    (`_listed_path`), else None. A `Where-Object` or `Select-Object` stage between them passes the listing on."""
    stage = number - 1
    while stage >= 0 and ends[stage] == "|":
        words = [_unquoted(word) for word in parsed[stage]]
        command, rest = _segment_command(words)
        if command in _LISTERS:
            return _listed_path(rest)
        if command not in _LIST_FILTERS:
            return None
        stage -= 1
    return None


def _listed_path(rest) -> tuple:
    """The folders a listing's arguments may name: the `-Path` value, else the first plain word, else `.`. A
    filtering parameter's value (`-Filter *.py`) is no folder. The word after a parameter not known to take a
    value or none may be its value or the folder, so each reading gives a folder (`-New v hooks`: `v`, `hooks`)."""
    plain, index, sure, maybe = [], 0, False, False
    while index < len(rest):
        word = rest[index]
        if not word.startswith("-"):
            if not sure:
                plain.append(word)
                sure = not maybe
            maybe = False
        else:
            maybe = False
            name, colon, value = word[1:].partition(":")
            name = name.lower()
            if _flag_is(name, _LIST_PATH_FLAGS):
                if colon and value:
                    return (value,)
                if index + 1 < len(rest):
                    return (rest[index + 1],)
            elif not colon and _flag_is(name, _LIST_FILTER_FLAGS + _PS_COMMON_VALUE_FLAGS, 2):
                index += 1   # its value filters the listing; it is no folder
            elif not colon and not _flag_is(name, _LIST_SWITCH_FLAGS):
                maybe = True
        index += 1
    return tuple(plain) + (() if sure else (".",))


# What a mutating command's parameters take, for `_pipe_variable_hit`: the path it writes (or the destination
# of a copy), the path a copy reads, a value that is neither a path nor written (a filter, text), or nothing.
_PS_TARGET_FLAGS = ("path", "literalpath", "destination", "name", "newname", "target", "filepath", "pspath")
_PS_VALUE_FLAGS = ("include", "exclude", "filter", "inputobject", "value", "itemtype", "encoding", "stream",
                   "credential", "width", "depth", "attributes") + _PS_COMMON_VALUE_FLAGS
# How many plain words these take as paths. The words after them are text or a type: a content command's value,
# `Out-File`'s encoding, `New-Item`'s type or value (its second word is the Name, so it is a path). A command
# not listed takes every plain word as a path (`Remove-Item`).
_PATH_POSITIONS = {**dict.fromkeys(_PS_CONTENT | {"out-file"}, 1), "new-item": 2, "ni": 2}


def _ps_argument_slots(command, rest):
    """The `(role, word)` pairs of a PowerShell command's arguments. A role is `write` (a path the command
    writes), `source` (the path a copy reads) or `destination` (where a copy writes). A value of a filtering or
    text parameter has no role and is left out, and so is a switch. Where PowerShell would bind a word by
    position, the command's own order decides it. A parameter not known to take a value or none may take the
    plain word after it, or not: that word, and each word after it, gets every role some reading gives it, so
    a word may come twice."""
    copies = command in _PS_COPY
    # A path parameter given by name takes the place of a positional path, so the plain words that are left
    # are values (`Add-Content -Path docs/list.txt $_.Name` writes `$_.Name` into the file).
    named = sum(1 for word in rest if word.startswith("-") and len(word) > 1
                and _flag_is(word[1:].partition(":")[0].lower(), _PS_TARGET_FLAGS))
    limit = _PATH_POSITIONS.get(command)
    # `fewest` counts the plain words before this one that are positional in every reading, `most` those that
    # are in some reading. `maybe` marks a word an unknown parameter may take as its value.
    slots, fewest, most, index, maybe = [], 0, 0, 0, False
    while index < len(rest):
        word = rest[index]
        if word.startswith("-") and len(word) > 1:
            name, colon, value = word[1:].partition(":")
            name = name.lower()
            target = _flag_is(name, _PS_TARGET_FLAGS)
            takes_value = target or _flag_is(name, _PS_VALUE_FLAGS, 2)
            unknown = not takes_value and not _flag_is(name, _PS_SWITCH_FLAGS)
            if not colon and takes_value and index + 1 < len(rest):
                value = rest[index + 1]
                index += 1
            if value and target:
                if copies and _flag_is(name, ("path", "literalpath")):
                    role = "source"
                elif copies and _flag_is(name, ("destination",)):
                    role = "destination"
                else:
                    role = "write"
                slots.append((role, value))
            maybe = unknown and not colon
        else:
            if copies:
                taken = {role for role, _word in slots}
                if "source" not in taken and fewest == 0:
                    slots.append(("source", word))
                if "source" in taken or most > 0:
                    slots.append(("destination", word))
            elif limit is None or fewest + named < limit:
                slots.append(("write", word))
            fewest += 0 if maybe else 1
            most += 1
            maybe = False
        index += 1
    return slots


def _pipe_variable_hit(command_args, folders, at, predicate, holds) -> str:
    """The word that is the pipeline variable (`$_`, `$PSItem`) as a path the command writes into a place that
    `predicate` accepts, else ''. `folders` are the folders the listing the variable comes from may be
    (`_listed_path`): a write of `$_` lands on a path in one, so it counts when `holds(folder, at)` for any. A
    copy's source is only read; it is written when the destination is a folder, as `FOLDER/<listed name>`, so
    it counts when that path is accepted for any name a listing holds."""
    command, rest = command_args if command_args else ("", ())
    if not _mutates_as_command(command, rest):
        return ""
    slots = _ps_argument_slots(command, rest)
    for folder in folders:
        hit = _listed_hit(slots, folder, at, predicate, holds)
        if hit:
            return hit
    return ""


def _listed_hit(slots, folder, at, predicate, holds) -> str:
    """`_pipe_variable_hit` for one listed folder."""
    for role, word in slots:
        if role != "source" and _PIPE_VARIABLE.fullmatch(word) and holds(folder, at):
            return word
    sources = [word for role, word in slots if role == "source" and _PIPE_VARIABLE.fullmatch(word)]
    destinations = [word for role, word in slots if role == "destination"]
    if sources and destinations and _is_folder(destinations[0], at):
        try:
            names = os.listdir(_expanded(folder, at))
        except (OSError, ValueError):
            return sources[0] if holds(folder, at) else ""
        head = destinations[0].rstrip("/\\")
        if any(predicate(head + "/" + name, at) for name in names):
            return sources[0]
    return ""


# What may stand before a PowerShell command's name in its word: casts and the parens they open (`[void](`).
_PS_COMMAND_LEAD = re.compile(r"(?:\[[^\]]*\]|[$@]?\()*")
_PS_GROUP_OPEN = re.compile(r"[$@]?\(")


def _ps_inner_groups(raw):
    """The `( )` groups among a PowerShell segment's arguments that fill no path slot of its command, as
    (indexes into `raw`, the text inside the group). A path in such a group is read or written by the group's
    own commands, not by the outer one: `Set-Content docs/a.md (Get-Content hooks/test_x.py)` writes only
    docs/a.md. A group in a path slot (`Set-Content (Get-Item P) x`) names the target, so it is none of these.
    A shape this does not read (an unclosed group, a command name it does not know) gives none, so every word
    stays judged as part of the outer command."""
    plain = [_outside_quotes(word) for word in raw]
    start = 1 if plain and (plain[0].lower() == "return" or re.fullmatch(r"(?:\[[^\]]*\])+", plain[0])) else 0
    if start >= len(raw):
        return []
    lead = _PS_COMMAND_LEAD.match(plain[start]).group()
    name = plain[start][len(lead):]
    if not re.fullmatch(r"[A-Za-z][\w-]*", name):
        return []
    base = depth = lead.count("(")
    rest, spans, index = [], [], start + 1
    while index < len(raw):
        first = index
        opens = depth == base and _PS_GROUP_OPEN.match(plain[index])
        depth += plain[index].count("(") - plain[index].count(")")
        while opens and depth > base and index + 1 < len(raw):
            index += 1
            depth += plain[index].count("(") - plain[index].count(")")
        if depth != base and (opens or depth > base):
            return []   # an unclosed group, or a word that opens one mid-word
        if opens:
            spans.append(range(first, index + 1))
            rest.append("\0" + str(len(spans) - 1))
        else:
            rest.append(_unquoted(raw[index]))
        if depth < base:
            break   # the paren that closes the command's own group ends its arguments
        index += 1
    targets = {word for role, word in _ps_argument_slots(name.lower(), rest) if role != "source"}
    groups = []
    for number, span in enumerate(spans):
        if "\0" + str(number) in targets:
            continue
        text = _straight(" ".join(raw[i] for i in span))
        inner = text[_PS_GROUP_OPEN.match(text).end():]
        groups.append((span, inner[:-1] if inner.endswith(")") else inner))
    return groups


def _lead_command(segment):
    """(command, words after it) for the first mutating command a segment holds at a command position past its
    first word (`[void] New-Item x`, `[void](New-Item x)`, `return Set-Content x y`), else None. It reads the
    segment text: text inside quotes or a here-string holds no command. A position is the text
    `_COMMAND_POSITION` reads, so this and the alias rule share one idea of where a command starts."""
    text = _straight(segment)
    masked = re.sub(r"@(['\"])[ \t]*\r?\n.*?\r?\n[ \t]*\1@|'[^']*'|\"[^\"]*\"",
                    lambda quoted: "Q" * len(quoted.group()), text, flags=re.DOTALL)
    for match in re.finditer(r"[^\s(){}\[\];]+", masked):
        if not re.search(_COMMAND_POSITION + r"\Z", masked[:match.start()]):
            continue
        command, rest = _segment_command([_unquoted(word) for word in _quoted_words(text[match.start():])])
        if _mutates_as_command(command, rest):
            return command, rest
    return None


def _ps_blocks(segment: str):
    """(the text inside each top-level `{ ... }` of a PowerShell segment, its brace balance: opens less closes).
    Quoted text and here-strings are skipped, so a brace in a string is no block. An unclosed brace gives
    its rest."""
    text, out, depth, start, quote, index, balance = _straight(segment), [], 0, 0, "", 0, 0
    while index < len(text):
        char = text[index]
        if quote:
            if char == "`" and quote == '"':
                index += 1
            elif char == quote:
                quote = ""
        elif char == "@" and re.match(r"@['\"][ \t]*\r?\n", text[index:]):
            # a here-string body is text up to its closing `'@` or `"@` at a line start
            close = re.compile(r"\n[ \t]*" + text[index + 1] + "@").search(text, index)
            index = close.end() - 1 if close else len(text)
        elif char in "'\"":
            quote = char
        elif char == "{":
            balance += 1
            if depth == 0:
                start = index + 1
            depth += 1
        elif char == "}":
            balance -= 1
            if depth:
                depth -= 1
                if depth == 0:
                    out.append(text[start:index])
        index += 1
    if depth:
        out.append(text[start:])
    return out, balance


_PS_SHELLS = frozenset(("pwsh", "powershell", "cmd"))
_PS_LAUNCHER = re.compile(r"pwsh|powershell|cmd|iex|invoke-expression", re.IGNORECASE)


def _powershell_scripts_of(segment: str) -> list:
    """The PowerShell scripts a segment hands on (`pwsh -c`, `powershell -Command`, `cmd /c`, `iex`), else [].
    A shell the segment starts (`bash -c`, `sh -c`, `env -S`, `eval`) hands on text that is no PowerShell
    itself: its segments are read the same way, so a `pwsh -c` inside one is found. Each step cuts the
    text to the script the segment holds, so the walk ends."""
    if not _PS_LAUNCHER.search(segment):
        return []
    tokens = segment_tokens(segment)
    script = nested_script(tokens) if tokens else ""
    if not script:
        return []
    if isinstance(script, PowerShellScript):
        return [script]
    return [found for inner in split_segments(script, []) for found in _powershell_scripts_of(inner)]


def _segment_command(words):
    """(resolved command name, plain words after it) of a segment, for `writes_to`'s command position.
    `env -S STRING` runs STRING, with the words after it appended: that command is the one read."""
    inner = guard_core._env_split_string(tuple(words))
    tokens = segment_tokens(inner) if inner else None
    if tokens:
        return _segment_command(tokens)
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
