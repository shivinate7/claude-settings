"""The guard's frozen family: a write to the settings, the hooks or the global CLAUDE.md.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import os
import re

import guard_core
from guard_core import (
    HEREDOC_HEADER, PS_DOUBLE_QUOTES, PS_SINGLE_QUOTES, PS_STRAIGHT_QUOTES, REDIRECT, SCRIPT_HEADERS,
    PowerShellScript, _expanded, _resolved, _split_heredocs, _strip_heredoc_bodies_unconditionally, basename,
    dir_before_segment, heredoc_delimiter, interpreter_bodies, is_powershell, nested_script, norm, resolve_command,
    segment_tokens, split_segments, strip_heredoc_bodies,
)
from guard_env import _quoted_words, _substitutions, script_spots


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


def writes_to(path: str, cmd: str, command=None, words=(), written=()) -> bool:
    """True when the command looks like it writes to the path, rather than merely naming it.

    Two ways to write a named file from a shell: redirect onto it, or hand it to a command that
    mutates its arguments. Everything else is a mention. `written` holds the words a parsed
    command writes (`_sed_operands`: the files of a `sed -i`), so a write the text match misses
    still counts.

    Reading the TARGET of the redirect is what separates
    `echo x > .claude/settings.json` from `cat .claude/settings.json 2>/dev/null`. The second
    redirects to the null device. It is also what stops a redirect elsewhere on the line from
    counting as a write to a path named in a comment.
    """
    if path in written:
        return True
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


# SED OPERANDS. `sed [OPTION]... [SCRIPT] [FILE]...`: the script is code, not a path, and each FILE
# is what an in-place sed writes. The script is each `-e`/`--expression` value and each `-f`/`--file`
# value (a file sed reads); with none of those it is the first operand. GNU sed reorders options
# after operands, `--` ends them, an `i` in a cluster takes the rest of it as a backup suffix
# (`-Ei`, `-ni`, `-i.bak`, but `-in` is suffix `n`), and a long name may be cut short.
# Read on the shell words of one segment (`_quoted_words`), so a `|`, `;`, `&`, `#` or line break
# inside a quoted script stays in it, and the files after it still count.
# Only a segment whose command word is `sed` is read. A wrapped or nested sed (`sudo sed`,
# `xargs sed`, `bash -c "sed ..."`) and an unquoted `$` word up to the script keep the text match.
# A script that holds a `w` or `W` command (it writes a file) or an `e` command (it runs one) is
# judged as text, as before, so the file or command in it still counts. The command letter follows
# a space, `;{}!$`, a digit, `=` (`--expression=`), `,` (an `s` flag after another delimiter), the
# flags of an `s/` or the `-e` or `-f` of a glued option (`-e'w f'`). A letter after any other
# character reads as text.
_SED_RUNS = re.compile(r"(?:^|[\s;{}!$0-9=,]|/[gpiImMe0-9]*|^-[A-Za-z]*[ef])[wWe](?:\s|$)")
_SED_LONG = ("expression", "file", "in-place", "line-length")
_SED_REDIRECT = re.compile(r"\d*>>?|<{1,3}")   # an operator word whose target is the next word
_UNQUOTED_EXPANSION = re.compile(r"""'[^']*'|"[^"]*"|([$`])""")


def _sed_operands(raw):
    """(script indexes, file indexes, in place?) of a `sed` segment's shell words, else None."""
    start = guard_core._skip_assignments_and_keywords(raw)
    if start >= len(raw) or _name(raw[start]) != "sed":
        return None
    scripts, operands, in_place, given, options = set(), [], False, False, True
    index = start + 1
    while index < len(raw):
        word = _unquoted(raw[index])
        operator = _SED_REDIRECT.fullmatch(raw[index])
        if operator or raw[index][0] in "<>&":   # a redirect: an operator word skips its target too
            index += 2 if operator else 1
            continue
        if options and word == "--":
            options = False
        elif options and word.startswith("--"):
            name, equals, _value = word[2:].partition("=")
            full = next((long for long in _SED_LONG if name and long.startswith(name)), "")
            in_place = in_place or full == "in-place"
            if full in ("expression", "file"):
                given = True
                scripts.add(index if equals else index + 1)
            if full in ("expression", "file", "line-length") and not equals:
                index += 1
        elif options and word.startswith("-") and len(word) > 1:
            for at, letter in enumerate(word[1:], 2):
                if letter == "i":
                    in_place = True
                    break
                if letter in "efl":
                    glued = at < len(word)
                    if letter != "l":
                        given = True
                        scripts.add(index if glued else index + 1)
                    index += 0 if glued else 1
                    break
        else:
            operands.append(index)
        index += 1
    if not given and operands:
        scripts.add(operands.pop(0))
    scripts = {i for i in scripts if i >= len(raw) or not _SED_RUNS.search(_unquoted(raw[i]))}
    last = max(scripts, default=start)
    if any(m.group(1) for word in raw[start:last + 1] for m in _UNQUOTED_EXPANSION.finditer(word)):
        return None   # an unquoted expansion may add or drop a word: the script cannot be placed
    return scripts, set(operands), in_place


# VARIABLE INDIRECTION. In `D=~/.claude/state/handoff/x.md; ...; cp "$S/handoff.md" "$D"` the parse
# sees only the word `$D`. `_resolve_vars` (called first by `_shell_write_hit`, which feeds the frozen
# and project-config checks) reads the command once, left to right, as the shell reads it: it splits
# the text into words and quoted spans, keeps a table of simple assignments, and reads each `$D` or
# `${D}` as the value current at that point. The table holds `D=v` at a command's start (a value is
# the whole shell word, so `WT="$BASE"/../lane` is one path), the arguments of `export`, `declare`,
# `typeset`, `local` and `readonly` (`export A=1 D=v`), and a PowerShell assignment: `$D = v` or `$D =v`
# anywhere, and `$D=v`, `$D='v'` or `$D= v` at a statement's start only, so a bash `echo $D=x` sets
# nothing. A backslash-newline joins two lines, so it reads as a blank. The text keeps its type: a
# PowerShell text (a `pwsh -c` script, `PowerShellScript`, or any text in a PowerShell call) comes back
# PowerShell, so a later reader judges it by the same rules. In PowerShell text a smart quote U+2018 to
# U+201E is a quote (`_straight`): the words are read as if it were its ASCII twin, and the result
# keeps the smart quote as written, so the scan for text that is no data still sees it. The last assignment
# wins, `unset D` clears it, a use before the assignment stays as written, and single quotes do not
# expand. An unassigned variable stays unresolved and allowed. `$HOME` reads as `~`:
# `os.path.expandvars` leaves it literal when HOME is unset (the Windows default), so a literal
# `$HOME/.claude/...` target was allowed.
# Text is not code, and code is not text. An assignment inside double quotes or after a `#` comment
# is text, and a lone apostrophe in double quotes opens no span, because quotes are read in pairs
# from the left. An unmated quote is one ordinary character, so the text after it is still read as
# code, the fail-closed side: a variable read as code resolves, one read as text stays as written.
# Every heredoc body is read alone, whatever its delimiter, so its quotes never pair with a quote
# after it and its assignments end with it. A header with no closer (its body was dropped before this
# read, or it runs to the end) is read on as code at the same level, so blocks in a row nest nothing;
# past `_NEST_LIMIT` a nested body is read inline as code too. The body of `$(...)` or backticks is a
# command even inside double quotes, and so is the argument of `eval "..."`. A prefix assignment
# (`S=x cmd "$S"`) sets the variable for that one command and the environment of the child it starts:
# the command's own words and all later text see the value from before it, and its heredoc body sees
# the new one. `env S=x cmd` gives the child the same. A verbatim body (`<<'EOF'`) is the child's text,
# so it sees each new value; the parent expands any other body, so it sees only names the table lacks.
# A subshell `( ... )`, `$( ... )` or backtick pair gives its assignments back where it ends.
# A redirect (`>/dev/null`, `2>f`, `<<'EOF'`) and the name after `function` leave the command's start
# as it was, so `D=x >/dev/null` still sets D. An unquoted `$D` whose value holds two words is an
# ambiguous redirect target that writes nothing, so it stays as written there (unless IFS is set).
# RESIDUAL GAP: a value from `$(...)`, backticks, `read`, `${D:-x}`, a loop variable (read only in the
# forms of LOOPS AND BRACES, below), `eval '...'`, or an interpreter (`python -c`) is not resolved, nor
# is a variable set in a different tool call. An assignment in a pipeline stage or a background job
# (`D=x | cat`, `D=x &`) is kept here, though the shell runs it in a subshell and keeps nothing, so a
# later `$D` can read a value the shell does not.
# An escaped `\$D` in an unquoted heredoc body reads the parent's value, not the child's.
# Fixing these needs a shell parser, not this one pass.
_WORD_STOP = frozenset(" \t\r\n;&|()`")
_ASSIGN_WORD = re.compile(r"([A-Za-z_]\w*)(\+?)=")
_VAR_USE = re.compile(r"\$(?:([A-Za-z_]\w*)|\{([A-Za-z_]\w*)\})")
_PS_NAME = re.compile(r"\$[A-Za-z_]\w*")
_PS_EQUALS = re.compile(r"[ \t]*=(?!=)[ \t]*")
_PS_ASSIGN = re.compile(r"\$([A-Za-z_]\w*)=(?!=)")
_BLANKS = re.compile(r"[ \t]*")
# `env` options whose next word is their argument, not the command or an assignment.
_ENV_ARGUMENT_OPTIONS = frozenset(("-u", "--unset", "-C", "--chdir", "-S", "--split-string"))
# A redirect operator at the start of a word (`>`, `>>`, `2>`, `>&`, `>|`, `<`, `<&`, `<>`).
_REDIRECT_OP = re.compile(r"\d*(?:>>|>&|>\||<&|<>|[<>])")
# Whitespace between two non-blank characters: the shell splits such a value into two words.
_TWO_WORDS = re.compile(r"[^ \t\n][ \t\n]+[^ \t\n]")
# Words after which the next word is still a command's start (`{ D=x; }`, `then D=x`, `eval D=x`).
_COMMAND_STARTERS = frozenset((
    "{", "!", "if", "then", "elif", "else", "do", "while", "until", "time", "eval", "function"))
_DECLARERS = frozenset(("export", "declare", "typeset", "local", "readonly"))
# Quotes nested in `$(...)` nested in quotes, or heredoc in heredoc; a deeper quoted body reads as plain
# text, a deeper heredoc body as code at the cap's level. It bounds the reader's recursion.
_NEST_LIMIT = 20


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


def _like(src: str, text: str) -> str:
    """`text` with the type of `src`, so a slice of PowerShell text is still read as PowerShell."""
    return text if type(src) is str else type(src)(text)


def _read_word(cmd: str, i: int, src=None):
    """(end, parts) of the shell word at `i`. `parts` are (kind, text, marks): kind `p` plain, `d` the
    inside of a double-quoted span, `s` the inside of a single-quoted span; `marks` is the span's opening
    and closing quote as written. Quotes are read in pairs; a quote with no mate is an ordinary character.
    `cmd` is the text the quotes are read in. `src` is the text the parts are cut from, the same text
    but for PowerShell's smart quotes (`_straight`): `cmd` has them as ASCII quotes, `src` as written."""
    src = cmd if src is None else src
    parts, plain, n = [], [], len(cmd)

    def flush():
        if plain:
            parts.append(("p", _like(src, "".join(plain)), ""))
            plain.clear()

    while i < n and cmd[i] not in _WORD_STOP:
        c = cmd[i]
        if c == "\\" and i + 1 < n:
            plain.append(src[i:i + 2])
            i += 2
            continue
        if c == "'":
            j = cmd.find("'", i + 1)
            if j >= 0:
                flush()
                parts.append(("s", _like(src, src[i + 1:j]), src[i] + src[j]))
                i = j + 1
                continue
        elif c == '"':
            j = _dq_end(cmd, i + 1)
            if j >= 0:
                flush()
                parts.append(("d", _like(src, src[i + 1:j]), src[i] + src[j]))
                i = j + 1
                continue
        elif c == "$" and cmd.startswith("{", i + 1):
            j = cmd.find("}", i + 2)
            if j >= 0:
                plain.append(src[i:j + 1])
                i = j + 1
                continue
        plain.append(src[i])
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
    scan = _straight(text)   # the quotes inside a `$(...)` are read as PowerShell reads them
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "$" and text.startswith("(", i + 1):
            end, skip = _subst_end(scan, i + 2, 0), 2
        elif c == "`":
            end, skip = text.find("`", i + 1), 1
        else:
            i += 1
            continue
        if end < 0:
            i += 1
            continue
        out.append(_expand(text[start:i], table))
        body = _like(text, text[i + skip:end])
        out.append(text[i:i + skip] + _resolve_into(body, dict(table), depth + 1)[0] + text[end])
        i = start = end + 1
    out.append(_expand(text[start:], table))
    return "".join(out)


def _rebuild(parts, table: dict, as_script: bool = False, depth: int = 0, as_target: bool = False):
    """(the word's text with each `$VAR` outside single quotes read as its value, the table after it).
    `as_script` reads a double-quoted span as a command that runs here (`eval "D=x"`). `as_target` is
    a redirect target word (see `_expand`)."""
    out = []
    for kind, text, marks in parts:
        if kind == "s":
            out.append(marks[0] + text + marks[1])
        elif kind == "d" and as_script and depth < _NEST_LIMIT:
            text, table = _resolve_into(text, table, depth + 1)
            out.append(marks[0] + text + marks[1])
        elif kind == "d":
            out.append(marks[0] + _dq_text(text, table, depth) + marks[1])
        else:
            out.append(_expand(text, table, as_target))
    return "".join(out), table


def _value_of(parts, table: dict) -> str:
    """The value a shell gives an assignment's word: quotes removed, `$VAR` read, escapes dropped. A
    backslash-newline outside single quotes joins two lines, so it adds nothing to the value."""
    pieces = []
    for kind, text, _marks in parts:
        if kind == "s":
            pieces.append(text)
        elif kind == "d":
            pieces.append(re.sub(r'\\(?:\n|(["\\$`]))', r"\1", _expand(text, table)))
        else:
            pieces.append(re.sub(r"\\(?:\n|(.))", r"\1", _expand(text, table), flags=re.S))
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
    for kind, text, _marks in parts:
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
    """Read each `$VAR` or `${VAR}` as the value assigned earlier in the command. The text keeps its
    type, so a script that pwsh runs (PowerShellScript) is still read by PowerShell's rules after."""
    return type(cmd)(_resolve_into(cmd, {"HOME": "~"})[0])


def _resolve_into(cmd: str, table: dict, depth: int = 0):
    """(`cmd` with each `$VAR` read, the table after it): `_resolve_vars` from a given table. In PowerShell
    text a smart quote is a quote (`_straight`): the words are read on the text with ASCII quotes, and
    every piece of the result is cut from the text as written, so the smart quotes stay in it."""
    src = cmd
    cmd = str(_straight(src))
    # stack: (table to restore where the group ends, glued to a `$`, closer, the outer command's child names)
    out, stack = [], []
    n, i = len(cmd), 0
    at_start, before, mode = True, None, ""   # before: the table from before this command's assignments
    operand = ""   # "target": the next word names a redirect's file; "name": a function's name
    # (delimiter, quoted?, the child's names) of the heredocs whose bodies start after the next newline
    heredocs = []
    child = {}   # names this command's prefix or `env NAME=v` words give its child: value, or None if unknown
    while i < n:
        c = cmd[i]
        if c in " \t\r":
            out.append(c)
            i += 1
        elif c == "\\" and cmd.startswith("\n", i + 1):   # a line join is a blank: the command goes on
            out.append("\\\n")
            i += 2
        elif c == "&" and (cmd[i - 1:i] in ("<", ">") or cmd.startswith(">", i + 1)):
            out.append(c)   # `>&1`, `<&-` and `&>f` are redirects, not a background job
            i += 1
        elif c in ";&|\n":
            out.append(c)
            i += 1
            at_start, before, mode, operand, child = True, None, "", "", {}
            while c == "\n" and heredocs:   # a body is read in itself: its quotes never pair outward
                delimiter, quoted, names = heredocs.pop(0)
                body_end, line_end = _heredoc_end(cmd, i, delimiter)
                if body_end == n:   # no closer: the rest is read on here as code, and nests nothing
                    heredocs.clear()
                    break
                scope = dict(table)
                for name, value in names.items():
                    if value is None and quoted:
                        scope.pop(name, None)
                    elif value is not None and (quoted or name not in table):
                        scope[name] = value   # the child expands a verbatim body; the parent, any other
                out.append(_resolve_into(_like(src, src[i:body_end]), scope, depth + 1)[0])
                out.append(src[body_end:line_end])
                i = line_end
                if heredocs and cmd.startswith("\n", i):
                    out.append("\n")
                    i += 1
        elif c == "(" or (c == "`" and not (stack and stack[-1][2] == "`")):
            stack.append((dict(table), c == "`" or cmd[i - 1:i] == "$", ")" if c == "(" else "`", child))
            out.append(c)
            i += 1
            at_start, before, mode, operand, child = True, None, "", "", {}
        elif c == ")" or c == "`":   # `)` ends the nearest `(`; a second backtick ends the open one
            glued, outer = False, {}
            for level in range(len(stack) - 1, -1, -1):
                if stack[level][2] == (")" if c == ")" else "`"):
                    table, glued, _closer, outer = stack[level]
                    del stack[level:]
                    break
            out.append(c)
            i += 1
            at_start, before, mode, operand = not glued, None, "", ""
            child = outer if glued else {}   # `$(...)` ends inside a word of the outer command
        elif c == "#":   # a comment: its text is read for uses and holds no assignment
            j = cmd.find("\n", i)
            j = n if j < 0 else j
            out.append(_expand(src[i:j], table))
            i = j
        else:
            end, parts = _read_word(cmd, i, src)
            word = src[i:end]
            if operand:   # a redirect's file or a function's name: a word, never a command or assignment
                text, table = _rebuild(parts, table, False, depth, operand == "target")
                out.append(text)
                operand = ""
                i = end
                continue
            at = _heredoc_at(parts)
            if at >= 0 and depth < _NEST_LIMIT:   # past the cap a body is read on here as code
                header = HEREDOC_HEADER.match(cmd, i + at)
                if header:   # any quote or backslash in the delimiter makes the body verbatim
                    heredocs.append((heredoc_delimiter(header.group(1))[1],
                                     any(mark in header.group(1) for mark in "'\"\\"), child))
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
                _assign(table, head.group(1), head.group(2), ([("p", rest, "")] if rest else []) + parts[1:],
                        cmd.startswith(("(", "`"), end))
                out.append(word)
                i = end
                continue
            if head and mode == "env":   # `env NAME=v cmd`: the value reaches the child only
                scope = dict(table)
                scope.update((name, value) for name, value in child.items() if value is not None)
                rest = parts[0][1][head.end():]
                _assign(scope, head.group(1), head.group(2), ([("p", rest, "")] if rest else []) + parts[1:],
                        cmd.startswith(("(", "`"), end))
                child[head.group(1)] = scope.get(head.group(1))
                out.append(word)
                i = end
                continue
            ps = _PS_ASSIGN.match(parts[0][1]) if at_start and parts and parts[0][0] == "p" else None
            if ps:   # PowerShell `$D=v`, `$D='v'` or `$D= v` at a statement's start
                rest = parts[0][1][ps.end():]
                vend, vparts = end, ([("p", rest, "")] if rest else []) + parts[1:]
                if not vparts:   # `$D= v`: the value is the next word
                    vend, vparts = _read_word(cmd, _BLANKS.match(cmd, end).end(), src)
                for held in [table] + [level[0] for level in stack]:
                    _assign(held, ps.group(1), "", vparts, cmd.startswith(("(", "`"), vend))
                out.append(src[i:vend])
                i = vend
                continue
            if head is None and len(parts) == 1 and parts[0][0] == "p" and _PS_NAME.fullmatch(parts[0][1]):
                eq = _PS_EQUALS.match(cmd, end)
                if eq:   # PowerShell `$D = v`. A paren is no scope there, so every level keeps it.
                    vend, vparts = _read_word(cmd, eq.end(), src)
                    for held in [table] + [level[0] for level in stack]:
                        _assign(held, parts[0][1][1:], "", vparts, cmd.startswith(("(", "`"), vend))
                    out.append(src[i:vend])
                    i = vend
                    continue
            if at_start:
                if word in _COMMAND_STARTERS:
                    mode = "eval" if word == "eval" else mode
                    operand = "name" if word == "function" else operand
                    out.append(word)
                    i = end
                    continue
                if before is not None:   # a prefix assignment reaches only its own command and its child
                    child.update((name, table.get(name)) for name in set(table) | set(before)
                                 if table.get(name) != before.get(name))
                    table, before = before, None
                at_start = False
                mode = ("declare" if word in _DECLARERS else "unset" if word == "unset"
                        else "env" if word.rsplit("/", 1)[-1] == "env" else mode if mode == "eval" else "")
            elif mode == "unset" and re.fullmatch(r"\w+", word):
                table.pop(word, None)
            elif mode == "env-argument":
                mode = "env"
            elif mode == "env":   # an option goes on; the first other word is the command
                mode = "env-argument" if word in _ENV_ARGUMENT_OPTIONS else "env" if word.startswith("-") else ""
            text, table = _rebuild(parts, table, mode == "eval", depth)
            out.append(text)
            i = end
    return "".join(out), table


# LOOPS AND BRACES. `for NAME in WORDS; do ... "$NAME" ...; done` names the words NAME takes, and a brace list
# `docs/{a,b}.md` names the words it expands to. `_resolve_loops` puts WORDS in place of each whole-word `$NAME`
# (`$f`, `${f}`, either in double quotes) in the body, and `_expand_braces` expands each unquoted comma brace of a parsed
# word, so the predicate judges the real paths. Both read shell words with `_quoted_words` and the segments of
# `split_segments`, never raw text. Each of these keeps today's literal reading (the word stays as written):
#  - a list word holds `$` or a backtick, or is a redirect;
#  - the body assigns NAME, uses `$NAME` as part of a word (`"$f.md"`, `$(cmd "$f")`), as the command word, or as a
#    redirect target; or a `for` loop nests inside it, or no `done` closes it, or the list is empty;
#    An inner `while` or `until` is not seen as a loop: the command start (guard_core `_skip_assignments_and_keywords`)
#    skips its keyword, so its `done` closes the outer `for`, and a `$NAME` after that `done` keeps the literal reading.
#  - a brace is a `{a..b}` range (the word is kept whole), or an expansion goes past 32 words.
# A PowerShell command is not read: its braces and `for` are another syntax.
_LOOP_OPENERS = frozenset(("for", "while", "until", "select"))
_LOOP_CAP = 32
_LOOP_NAME = re.compile(r"[A-Za-z_]\w*")


def _brace_groups(word):
    """(open index, close index, comma indexes) of each unquoted brace pair of a shell word. A `${...}` is a
    parameter expansion, not a brace list: its pair and the commas inside it are skipped."""
    groups, stack, quote, index = [], [], "", 0
    while index < len(word):
        char = word[index]
        if quote:
            if char == "\\" and quote == '"':
                index += 1
            elif char == quote:
                quote = ""
        elif char == "\\":
            index += 1
        elif char in "'\"":
            quote = char
        elif char == "{":
            stack.append([index, None if word[index - 1:index] == "$" else []])
        elif char == "," and stack and stack[-1][1] is not None:
            stack[-1][1].append(index)
        elif char == "}" and stack:
            start, commas = stack.pop()
            if commas is not None:
                groups.append((start, index, commas))
        index += 1
    return groups


def _brace_expand(word):
    """The words an unquoted comma brace list in a shell word stands for, else None when the word keeps its literal
    reading: it holds a `{a..b}` range, or the expansion goes past _LOOP_CAP words. A word with no comma brace is
    its own one-word list."""
    groups = _brace_groups(word)
    if any(not commas and ".." in word[start + 1:end] for start, end, commas in groups):
        return None
    lists = [group for group in groups if group[2]]
    if not lists:
        return [word]
    start, end, commas = min(lists)
    edges = [start, *commas, end]
    out = []
    for left, right in zip(edges, edges[1:]):
        more = _brace_expand(word[:start] + word[left + 1:right] + word[end + 1:])
        if more is None:
            return None
        out.extend(more)
        if len(out) > _LOOP_CAP:
            return None
    return out


def _expand_braces(words):
    """The shell words with each comma brace list expanded, in place. An empty alternative (`{path,}`) leaves no
    word, as in bash, so no caller reads the first character of an empty word."""
    out = []
    for word in words:
        expanded = _brace_expand(word) if "{" in word else None
        out.extend([part for part in expanded if part] if expanded is not None else [word])
    return out


def _loop_whole_use(word, name):
    """True when a shell word is exactly `$NAME` or `${NAME}`, bare or in double quotes."""
    return bool(re.fullmatch(r'(")?\$(?:%s|\{%s\})(?(1)")' % (name, name), word))


def _loop_part_use(word, name):
    """True when a shell word expands NAME inside more text, or in any way but a whole word. A word that is one
    single-quoted string expands nothing."""
    if len(word) > 1 and word[0] == word[-1] == "'" and "'" not in word[1:-1]:
        return False
    return bool(re.search(r"\$\{?%s(?!\w)" % name, word)) and not _loop_whole_use(word, name)


def _segment_spans(cmd, segments):
    """(start, end) of each segment in `cmd`, in order, or None when one is not found past the one before: a
    command with an unmated quote is read twice by `split_segments`, and its second reading is not a place in the text."""
    spans, at = [], 0
    for segment in segments:
        start = cmd.find(segment, at)
        if start < 0:
            return None
        at = start + len(segment)
        spans.append((start, at))
    return spans


def _loop_body(words, first):
    """(index of the `done` that closes the `for` segment at `first`, whether a loop nests in it), else None."""
    depth, nested = 0, False
    for index in range(first + 1, len(words)):
        start = guard_core._skip_assignments_and_keywords(words[index])
        head = words[index][start] if start < len(words[index]) else ""
        if head in _LOOP_OPENERS:
            depth, nested = depth + 1, True
        elif head == "done":
            if depth == 0:
                return index, nested
            depth -= 1
    return None


def _loop_items(listed):
    """The words a `for` list stands for, else None when any keeps its literal reading (see LOOPS AND BRACES)."""
    items, count = [], 0
    for word in listed:
        if "$" in word or "`" in word or _is_redirect(word) or word[0] in "<>&|();":
            return None
        expanded = _brace_expand(word)
        count += 1 if expanded is None else len(expanded)
        if count > _LOOP_CAP:
            return None
        # Each alternative is its own item, so a body writer is read once per path, never once over several.
        items.extend([part for part in expanded if part] if expanded is not None else [word])
    return items or None


def _spelled(item, quoted):
    """The text a list item takes in place of a `$NAME` use. A bare use of an item that holds white space is split by the
    shell into the words of its unquoted text, so it is spelled that way; a double-quoted use keeps the item as one word."""
    return item if quoted or not any(char.isspace() for char in _unquoted(item)) else _unquoted(item)


def _loop_rewrites(words, first, last, name, items):
    """{segment index: new text} for the body segments of one loop that use `$NAME` as a whole word, each read as one
    command per list item, else None when the loop keeps its literal reading: the body assigns NAME, uses it in part,
    as the command word or as a redirect target."""
    assigned = re.compile(r"%s\+?=" % name)
    out = {}
    for index in range(first + 1, last + 1):
        body, changed, made = words[index], False, []
        start = guard_core._skip_assignments_and_keywords(body)
        for place, word in enumerate(body):
            if word == name or assigned.match(_unquoted(word)) or _loop_part_use(word, name):
                return None
            if _loop_whole_use(word, name):
                if index == last or place == start or (place and _is_redirect(body[place - 1])):
                    return None
                made.append((word.startswith('"'),))   # a use, and whether it sits in double quotes
                changed = True
            else:
                made.append(word)
        if changed:
            # One command per list item, so a writer that judges only its last operand reads each item there: a
            # `cp SRC "$f"` over two items is a cp to each, never a cp with the first item as a source.
            out[index] = " ; ".join(
                " ".join(word if isinstance(word, str) else _spelled(item, word[0])
                         for word in (made if number == 0 else made[start:]))
                for number, item in enumerate(items))
    return out


def _resolve_loops(cmd):
    """`cmd` with each `for NAME in WORDS; ...; done` body read as its words: WORDS stand in each whole-word `$NAME`."""
    if "for" not in cmd or guard_core.is_powershell(cmd):
        return cmd
    segments = split_segments(cmd, [])
    spans = _segment_spans(cmd, segments)
    if spans is None:
        return cmd
    words = [_quoted_words(segment) for segment in segments]
    edits, index = {}, 0
    while index < len(words):
        start = guard_core._skip_assignments_and_keywords(words[index])
        head = words[index][start:start + 3]
        if len(head) < 3 or head[0] != "for" or head[2] != "in" or not _LOOP_NAME.fullmatch(head[1]):
            index += 1
            continue
        closed = _loop_body(words, index)
        if closed is None:
            index += 1
            continue
        last, nested = closed
        items = None if nested else _loop_items(words[index][start + 3:])
        edits.update((items and _loop_rewrites(words, index, last, head[1], items)) or {})
        index = last + 1
    for at in sorted(edits, reverse=True):
        # The segment's own edge white space stays: a same-line `# comment` after the last item keeps its space,
        # so the shell, and the scan, still read `#` as a comment and the item as its own word.
        left, right = spans[at]
        text = cmd[left:right]
        lead, trail = text[:len(text) - len(text.lstrip())], text[len(text.rstrip()):]
        cmd = cmd[:left] + lead + edits[at] + trail + cmd[right:]
    return cmd


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
# gh runs no shell over a comment or review body, so a `>` quoted in it is text (rule building-scanner-respects-strings).
_GH_MESSAGE_CALLS = frozenset((
    ("pr", "create"), ("pr", "edit"), ("issue", "create"), ("issue", "edit"),
    ("pr", "comment"), ("issue", "comment"), ("pr", "review")))
_UNSAFE_MARK = re.compile(r"""`|\\["']|\$['"(]|[<>]\(|<#""")
# PowerShell reads these as quote marks. They end or open a quote that the scanner does not see.
_SMART_QUOTES = frozenset(PS_DOUBLE_QUOTES + PS_SINGLE_QUOTES)
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
# A DEST that is one quoted variable (`"$f"`) stays one word, so it cannot split into `-t dir`. Its
# value is unknown, but a DEST is only ever written, so the sources stay reads.
_QUOTED_VAR = re.compile(r'"\$(?:\w+|\{\w+\})"')


def _cp_start(raw) -> int:
    """The index of the `cp` command word of a segment, past assignments, a loop keyword (`do`, `then`,
    `else`, `{`) and a wrapper, by the one reader `resolve_command`; -1 when the segment runs no `cp`."""
    start = resolve_command(tuple(raw))
    return start if start is not None and _name(raw[start]) == "cp" else -1


# Words that name no written path, for a caller that judges every word of a write command as a path
# (`_shell_write_hit(skip_non_targets=True)`): an input redirect or heredoc operator (`<`, `<<EOF`) and its operand,
# `chmod`'s mode word, `truncate`'s size word, `install`'s mode word and its source operands. `<>` opens for write
# and `<(` is a substitution, so neither is skipped. A glued `<file` is one word and a bare operator takes the next.
_INPUT_WORD = re.compile(r"\d*<(?![>(])")
_INPUT_OPERATOR = re.compile(r"\d*<{1,3}-?")
_REDIRECT_START = re.compile(r"[\d&]*[<>]")
_REDIRECT_OPERATOR = re.compile(r"[\d&]*[<>]+[&\d-]*|&")
_CHMOD_FLAGS = re.compile(r"-[Rfvch]+")
_TRUNCATE_SIZE = re.compile(r"-[co]*s|--size")
_NO_VALUED = re.compile(r"(?!)")
_INSTALL_VALUED = re.compile(r"-[mogSt]|--(?:mode|owner|group|suffix|target-directory)")
_INSTALL_DIRS = re.compile(r"-[^-]*[dt][^-]*|--(?:directory|target-directory)(?:=.*)?")


def _plain_operands(raw, start, valued):
    """The indexes of the words after `start` that are no option, no redirect and no option value (a word after an
    option `valued` matches). `--` ends the options."""
    operands, index, options = [], start, True
    while index < len(raw):
        word = _unquoted(raw[index])
        if _REDIRECT_OPERATOR.fullmatch(raw[index]):
            index += 1 if raw[index] == "&" else 2
            continue
        if _REDIRECT_START.match(raw[index]):
            index += 1
            continue
        if options and word == "--":
            options = False
        elif options and word.startswith("-") and len(word) > 1:
            index += 1 if valued.fullmatch(word) else 0
        else:
            operands.append(index)
        index += 1
    return operands


def _non_target_words(raw) -> set:
    """The indexes of the words of one segment that name no written path (see `_INPUT_WORD`)."""
    skip = set()
    for index, word in enumerate(raw):
        if _INPUT_WORD.match(word) and raw[index + 1:index + 2] not in ([">"], [">>"]):   # `<>` is split in two words
            skip.add(index)
            if _INPUT_OPERATOR.fullmatch(word):
                skip.add(index + 1)
    start = resolve_command(tuple(raw))
    if start is None:
        return skip
    verb = _name(raw[start])
    if verb == "chmod":
        words = [_unquoted(word) for word in raw]
        if not any(word.startswith("--reference") for word in words[start + 1:]):   # else every operand is a file
            for index in range(start + 1, len(raw)):
                if words[index].startswith("--") or _CHMOD_FLAGS.fullmatch(words[index]) or index in skip:
                    continue
                if _plain_operands(raw, index + 1, _NO_VALUED):   # the first other word is the mode, `-x` included
                    skip.add(index)   # with no file after it, the word may be the file
                break
    elif verb == "truncate":
        for index in range(start + 1, len(raw)):
            if _TRUNCATE_SIZE.fullmatch(_unquoted(raw[index])) and _plain_operands(raw, index + 2, _NO_VALUED):
                skip.add(index + 1)
    elif verb == "install":
        skip |= {index + 1 for index in range(start + 1, len(raw)) if _unquoted(raw[index]) in ("-m", "--mode")}
        operands = _plain_operands(raw, start + 1, _INSTALL_VALUED)
        # `-d` makes directories and `-t DIR` takes every operand as a source: neither has a lone destination
        if len(operands) > 1 and not any(_INSTALL_DIRS.fullmatch(_unquoted(word)) for word in raw[start + 1:]):
            skip |= set(operands[:-1])
    return skip


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
                     command_position=False, predicate_command=False, script_data=False, writes_first=False,
                     skip_non_targets=False) -> str:
    """Return the path a shell command writes to that `predicate(path, cwd)` accepts, else ''.
    `holds(path, cwd)` tells a folder that holds such a path, for a linking `cp` (`_cp_link_source`).
    `follow_cd` hands `predicate` the folder a leading `cd` moved to (`dir_before_segment`), or `cwd`
    when that folder cannot be told. `predicate_command` also hands `predicate` the segment's command
    name as a third argument (`''` when none). `script_data` reads the script of a `python -c` or a
    `node -e` as data, for a caller that reads its shell spots on its own (`shell_write_hit`). `skip_non_targets`
    leaves an input operand, a mode word and a size word unjudged (`_non_target_words`). `writes_first`
    asks `writes_to` before `predicate`, for a `predicate` that reads files: a word that is no write target never
    reaches it. The default keeps the cheap `predicate` first, because `writes_to` scans the whole text for each word
    and a command of thousands of words scales with the square of its length."""
    holds = holds or (lambda path, where: _holds(path, where, predicate))
    cmd = _resolve_vars(_resolve_loops(cmd))
    ends = []
    segments = split_segments(cmd, ends)
    scans = [_scan(segment) for segment in segments]
    # `_expand_braces` builds new strings, so each word is typed again after it: `parsed` and `scripts` keep the
    # same length, and the reading follows a word to the next reader.
    expand = _expand_braces if not is_powershell(cmd) else (lambda words: words)
    parsed = [[_typed(word, segment) for word in expand(_quoted_words(segment))] for segment in segments]
    # The same words with a quoted newline kept, for a `sh -c` script read at its command positions only:
    # the text the write patterns read keeps newlines as spaces, so a quoted newline never ends a command.
    scripts = ([[_typed(word, segment) for word in expand(_quoted_words(segment, True))] for segment in segments]
               if command_position else parsed)
    closed = any(unsafe or _runs_stored_text(segment, words, plain)
                 for segment, words, (unsafe, plain) in zip(segments, parsed, scans))
    kinds = ["" if closed else _kind(words, plain) for words, (_u, plain) in zip(parsed, scans)]
    quiet = all(kind in ("printer", "cd") or not words for kind, words in zip(kinds, parsed))
    inner = []
    for number, raw in enumerate(parsed):
        linked = _cp_link_source(raw, holds, cwd)
        if linked:
            return linked
        data = set() if closed else _copy_reads(raw, predicate, cwd)
        if skip_non_targets and not closed:
            data = data | _non_target_words(raw)
        sed = None if closed else _sed_operands(raw)
        files = set()
        if sed:
            data = data | sed[0]   # a sed script is code: it names no path
            files = sed[1] if sed[2] else set()
        found = None if closed or not script_data else _inline_script_at([_unquoted(word) for word in raw])
        if found:
            data.add(found[1])
            # the shell still runs a substitution in a double-quoted script word
            inner += [text for text, _ in _substitutions(raw[found[1]])[0][:-1]]
        if kinds[number] in ("printer", "message"):
            last = number
            while last + 1 < len(kinds) and ends[last] == "|":
                last += 1
            chain = range(number, last + 1)
            runs_nowhere = all(kinds[k] == "printer" for k in chain[1:])
            to_file = any(_writes_a_file(parsed[k]) for k in chain)
            if runs_nowhere and (quiet or not to_file):
                data = data | _data_words(kinds[number], raw)
        words, shown, script, stood_in, written = [], [], [], set(), set()
        command_at = guard_core._skip_assignments_and_keywords(raw)
        for index, word in enumerate(raw):
            if index < command_at and word in guard_core.LOOP_KEYWORDS:
                continue   # `do` before the command is shell syntax: as a path it matches `docs/...` as text
            if index in data:
                stood_in.add(len(words))
                words.append('""')   # data, a `cp` source or a sed script: no redirect or `tee` in it runs
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
                word = _typed(word.rstrip(")`") or word, word)   # keeps the PowerShell type of the word
                pieces = _words_of(word) if _has_quote(word) else [word]
                # `_words_of` cuts a quote's text at a paren but not at a backtick: a `bash -c` script that
                # holds a backtick substitution ends its path word with one.
                pieces = [_typed(piece.rstrip("`") or piece, piece) for piece in pieces]
                words.extend(pieces)
                shown.extend(pieces)
                if index in files:
                    written.add(_unquoted(word))
                kept = scripts[number][index]
                script.extend(_words_of(kept) if _has_quote(kept) else [kept])
        text = " ".join(shown)
        at = (dir_before_segment(segments, number, cwd, ends) or cwd) if follow_cd else cwd
        verb = _segment_command(words)[0] if predicate_command else ""
        for nested in _powershell_scripts_of(segments[number]):
            # a script pwsh, `cmd /c` or iex runs is PowerShell text: judge it by PowerShell's rules too
            hit = _shell_write_hit(nested, at, predicate, holds, follow_cd, command_position, predicate_command,
                                   writes_first=writes_first, skip_non_targets=skip_non_targets)
            if hit:
                return hit
        position = _segment_command(script) if command_position else (None, ())
        for place, word in enumerate(words):
            if word.startswith("-") or REDIRECT.fullmatch(word):
                continue
            if not word or word in (">", ">>") or place in stood_in:
                continue   # a stand-in names no path: judged, it would resolve to the cwd
            accepts = (lambda: predicate(word, at, verb)) if predicate_command else (lambda: predicate(word, at))
            if writes_first:
                if writes_to(word, text, *position, written) and accepts():
                    return word
            elif accepts() and writes_to(word, text, *position, written):
                return word
    for text in inner:
        hit = _shell_write_hit(text, cwd, predicate, holds, follow_cd, command_position,
                               skip_non_targets=skip_non_targets)
        if hit:
            return hit
    return ""


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
    """(resolved command name, plain words after it) of a segment, for `writes_to`'s command position."""
    index = resolve_command(tuple(words))
    if index is None:
        index = next((i for i, word in enumerate(words) if not _ASSIGNMENT.match(word)), len(words))
    command = _name(words[index]) if index < len(words) else ""
    return command, [word for word in words[index + 1:] if word]


def frozen_shell_hit(cmd: str, cwd: str) -> str:
    """Return the frozen (config-dir) path a shell command writes to, else ''."""
    return _shell_write_hit(cmd, cwd, is_frozen, _holds_frozen)


def shell_write_hit(raw: str, cwd: str, predicate, holds=None) -> str:
    """Return the path a whole shell command writes to that `predicate(path, cwd)` accepts, else ''.
    A shell reads the command with its heredoc bodies dropped, except a body a shell runs
    (`strip_heredoc_bodies`). The text a python, node, perl or ruby script holds is data: its heredoc body,
    a file written and then run by one, and the script of a `python -c` or `node -e` are read only at their
    shell spots (`script_spots`: os.system, subprocess, `%x`, a backtick in ruby). A crash of that reading
    falls back to reading every body, which refuses more and never less."""
    try:
        hit = _shell_write_hit(strip_heredoc_bodies(raw, shells_only=True, per_body=True), cwd, predicate, holds,
                           script_data=True)
        texts = []
        resolved = _resolve_vars(raw)   # each body and `-c` script reads `$F` as the command's own assignment
        for lang, body, quote in interpreter_bodies(resolved):
            texts += script_spots(body, lang)
            if not quote:
                texts += [text for text, _ in _substitutions(body, heredoc=True)[0][:-1]]   # bash runs these
        if _has_inline_flag(raw):
            for kind, script, *_ in _inline_scripts(resolved):
                texts += script_spots(script, kind)
        for text in texts:
            hit = hit or _shell_write_hit(text, cwd, predicate, holds)
        return hit
    except Exception:
        return _shell_write_hit(strip_heredoc_bodies(raw), cwd, predicate, holds)


def project_config_shell_hit(cmd: str, cwd: str) -> str:
    """Return the project config path a shell command writes to, else ''."""
    return _shell_write_hit(cmd, cwd, is_project_config)


# ------------------------------------------------------------------ an interpreter's own writes
#
# A python or node script, run from a heredoc body, from `-c` / `-e`, or from a file named on the
# command line, writes a file the shell never names, so `_shell_write_hit` cannot see it.
# `interpreter_write_hit` reads the script itself. A script file is read from disk (bounded), or, when
# the same command writes it with a heredoc first, from that heredoc body.
# A quoted `<<'EOF'` body is read too: the interpreter runs it. Python is read with `ast`, so a path
# in a printed string or a comment is text and a path held in a variable is still found. A body
# `ast` cannot parse is read by a literal path beside a write call. Node is read by pattern.
_PY_HEADER = SCRIPT_HEADERS["py"]
_NODE_HEADER = SCRIPT_HEADERS["js"]
_PY_COMMAND = re.compile(r"^python[\d.]*(?:\.exe)?$")
_NODE_COMMAND = re.compile(r"^(?:node|nodejs|bun|deno)(?:\.exe)?$")
_PY_C_FLAG = re.compile(r"^-[A-Za-z]*c$")
_NODE_EVAL_FLAG = re.compile(r"^(?:-[ep]{1,2}|--eval|--print)$")
_INLINE_FLAG_WORDS = ("-c", "-e", "-p", "--eval", "--print")
_INLINE_BUNDLE = re.compile(r"(?<![\w-])-[A-Za-z]+[cep](?![\w-])")   # a flag bundle that ends in one: `-Bc`


def _has_inline_flag(text: str) -> bool:
    return any(flag in text for flag in _INLINE_FLAG_WORDS) or bool(_INLINE_BUNDLE.search(text))
_PATH_CTORS = ("Path", "PurePath", "PosixPath", "WindowsPath", "PurePosixPath", "PureWindowsPath")
_PATH_PASS = ("resolve", "expanduser", "absolute")
_COPY_NAMES = ("copy", "copy2", "copyfile", "copytree", "move")
_PY_WRITE_CALL = re.compile(
    r"""open\s*\([^)]*['"][rwabt]*[wax+][rwabt+]*['"]|write_text|write_bytes|shutil\s*\.\s*(?:copy|move)"""
    r"""|os\s*\.\s*(?:replace|rename)""")
_STRING_LITERAL = re.compile(r"""'([^'\n]+)'|"([^"\n]+)\"""")


def _join_path(head: str, tail: str) -> str:
    return head.rstrip("/") + "/" + tail if head else tail


_PY_TEMP = "\0temp"   # a folder a python or node temp call made: no path of the repo, so nothing under it is judged
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


def _py_up(paths, steps: int):
    """Each path `steps` folders up. A temp folder stays a temp folder: nothing under it is judged."""
    out = []
    for path in paths:
        for _ in range(steps if path != _PY_TEMP else 0):
            path = os.path.dirname(path)
        out.append(path)
    return out


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
        if name in ("dirname", "abspath", "realpath", "normpath") and len(node.args) == 1:
            inner = _py_paths(node.args[0], env)
            return _py_up(inner, 1) if name == "dirname" else inner
    if isinstance(node, ast.Attribute) and node.attr == "parent":
        return _py_up(_py_paths(node.value, env), 1)
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) \
            and node.value.attr == "parents" and isinstance(node.slice, ast.Constant) \
            and isinstance(node.slice.value, int) and node.slice.value >= 0:
        return _py_up(_py_paths(node.value.value, env), node.slice.value + 1)
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


def _py_env_at(tree, script: str = ""):
    """A function `env_at(node)`: the path each `name = <path>` binding gave, as it stands where `node`
    begins. One pass in source order; a later top-level assignment replaces the value, one inside an
    `if`, loop, `try` or function adds to it, since either may not run. `script` is the file the body
    came from: `__file__` is that path, so `dirname(__file__)` is the script's own folder."""
    top = {id(statement) for statement in tree.body}
    events = _py_bindings(tree)

    def env_at(call):
        env = {"__file__": [script]} if script else {}
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


_PY_PREFIX_TRIES = 8   # parses of a cut script, at most; each is of no more than `_SCRIPT_READ_LIMIT` bytes


def _py_prefix_tree(body: str):
    """The tree of the longest run of whole lines from the start of a cut script that parses, else None.
    The last line may be partial, so it goes first. A parse error names the line its statement opens
    on (an open bracket or triple quote), so each try cuts there and the search ends in a few tries."""
    import ast
    lines = body.splitlines(keepends=True)[:-1]
    for _ in range(_PY_PREFIX_TRIES):
        if not lines:
            return None
        try:
            return ast.parse("".join(lines))
        except SyntaxError as error:
            line = error.lineno or len(lines)
            lines = lines[:min(line - 1, len(lines) - 1)]
        except ValueError:
            lines = lines[:-1]
    return None


def _py_hit(body: str, cwd: str, predicate, script: str = "", cut: bool = False) -> str:
    """`cut` is True for a script file read only up to `_SCRIPT_READ_LIMIT`: it is judged by the part
    that parses (`_py_prefix_tree`), never by the literal fallback, which would count every test-path
    string in the file beside any write call."""
    import ast
    import textwrap
    if cut:
        tree = _py_prefix_tree(body)
        if tree is None:
            return ""
    else:
        try:
            tree = ast.parse(textwrap.dedent(body))
        except (SyntaxError, ValueError):
            tree = None
    if tree is None:
        # Unparsable (a shell variable in an unquoted body, a Python 2 line): a literal path the
        # predicate accepts, beside a write call in the same body, counts.
        if _PY_WRITE_CALL.search(body):
            for match in _STRING_LITERAL.finditer(body):
                text = match.group(1) or match.group(2)
                if predicate(text, cwd):
                    return text
        return ""
    env_at = _py_env_at(tree, script)
    for call, expression in _py_written(tree, env_at):
        for path in _py_paths(expression, env_at(call)):
            if predicate(path, cwd):
                return path
    return ""


# A python script acts on files and processes only through the modules in `_PY_ACTING`. `py_spots` reads it with
# `ast`: each name an import binds to one of them must be the callee of a shell call of os or subprocess with
# literal arguments (an alias resolves: `import subprocess as sp`, `from os import system`), or a name that acts
# on nothing (`_py_inert`). Any other use (shutil.copy, os.chmod, a call held in a variable) cannot be told, so
# the script reads whole, as a shell reads it. A comment or a plain string is text.
_PY_ACTING = ("os", "subprocess", "shutil", "pty", "asyncio", "posix", "nt", "sys", "importlib", "ctypes",
              "multiprocessing", "pathlib", "builtins", "runpy", "_posixsubprocess")
_OS_SPOT = re.compile(r"system|popen|startfile|exec\w*|spawn\w*|posix_spawn\w*")
_SUBPROCESS_SPOTS = ("run", "call", "check_call", "check_output", "Popen", "getoutput", "getstatusoutput")
_PY_INERT = ("subprocess.PIPE", "subprocess.DEVNULL", "subprocess.STDOUT")
_PY_DYNAMIC = ("eval", "exec", "compile", "__import__", "__builtins__", "import_module", "globals", "locals",
               "vars")
# The keyword arguments of a shell call that set what runs: a variable there cannot be told.
_PY_SPOT_KEYWORDS = ("args", "executable")


def _py_spot_name(name: str) -> str:
    """The dotted `name` when that call hands its text to a shell (`os.system`, `subprocess.run`), else ''."""
    module, _, call = name.rpartition(".")
    if module == "os" and _OS_SPOT.fullmatch(call) or module == "subprocess" and call in _SUBPROCESS_SPOTS:
        return name
    return ""


def _py_inert(name: str) -> bool:
    """True for a dotted name of an acting module that names or reads things and acts on nothing: os.path, a
    subprocess constant, and every name of sys but sys.modules, which can swap a module for another."""
    return (name in _PY_INERT or name == "os.path" or name.startswith("os.path.")
            or name.startswith("sys.") and name.split(".")[1] != "modules")


def _py_literal(node) -> bool:
    import ast
    if isinstance(node, ast.Constant):
        return True
    return isinstance(node, (ast.List, ast.Tuple)) and all(_py_literal(each) for each in node.elts)


def _py_import_bindings(tree):
    """{name: dotted name} for each name an import binds to an acting module or a name of one: `import os.path`
    binds `os` to os, `import os.path as p` binds `p` to os.path, `from shutil import copy as c` binds `c` to
    shutil.copy. None for a `from` import of every name, which binds names that cannot be told."""
    import ast
    bound = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for each in node.names:
                top = each.name.split(".")[0]
                if top in _PY_ACTING:
                    bound[each.asname or top] = each.name if each.asname else top
        elif (isinstance(node, ast.ImportFrom) and node.module and not node.level
              and node.module.split(".")[0] in _PY_ACTING):
            for each in node.names:
                if each.name == "*":
                    return None
                bound[each.asname or each.name] = node.module + "." + each.name
    return bound


def py_spots(script: str):
    """The shell text of each call of a python script that hands a string to a shell, as `os.system('...')`,
    or None when the script cannot be told: it uses an acting module another way (`_PY_ACTING`), reaches code by
    another route (`eval`, `__import__`), or a shell call takes an argument that is no literal. The caller then
    reads the whole script as shell. A script that does not parse raises SyntaxError or ValueError: python
    runs none of it."""
    import ast
    import textwrap
    source = textwrap.dedent(script)
    tree = ast.parse(source)
    bound = _py_import_bindings(tree)
    if bound is None:
        return None
    calls, callee_names, parents = [], set(), {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
        if isinstance(node, ast.Name) and node.id in _PY_DYNAMIC:
            return None
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id in bound:
            spot, base = _py_spot_name(bound[func.value.id] + "." + func.attr), func.value
        elif isinstance(func, ast.Name) and func.id in bound:
            spot, base = _py_spot_name(bound[func.id]), func
        else:
            continue
        if spot:
            calls.append((node, spot))
            callee_names.add(id(base))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Name) or node.id not in bound or id(node) in callee_names:
            continue
        name, parent = bound[node.id], parents.get(id(node))
        if not (_py_inert(name) or isinstance(parent, ast.Attribute) and parent.value is node
                and _py_inert(name + "." + parent.attr)):
            return None
    out = []
    for node, spot in calls:
        args = list(node.args) + [kw.value for kw in node.keywords if kw.arg in _PY_SPOT_KEYWORDS]
        if (not args or not all(_py_literal(arg) for arg in args) or any(kw.arg is None for kw in node.keywords)
                or any(isinstance(arg, ast.Starred) for arg in node.args)):
            return None
        out.append(spot + "(" + ", ".join(ast.get_source_segment(source, arg) or "" for arg in args) + ")")
    return out


_JS_STR = (r"""(?:'([^'\n]*)'|"([^"\n]*)"|`([^`$]*)`|([A-Za-z_$][\w$]*)(?![\w$]|\s*[.(])"""
           r"""|path\s*\.\s*(?:join|resolve)\s*\(([^()]*)\))""")
_JS_ONE = re.compile(
    r"\b(?:writeFileSync|writeFile|appendFileSync|appendFile|createWriteStream)\s*\(\s*" + _JS_STR)
_JS_TWO = re.compile(
    r"(?:\b(?:copyFileSync|copyFile|renameSync|cpSync)|\bfs(?:\.promises)?\s*\.\s*(?:rename|cp))"
    r"\s*\(\s*" + _JS_STR + r"\s*,\s*" + _JS_STR)
_JS_BIND = re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*")
_JS_VALUE = re.compile(_JS_STR)
_JS_JOIN_PIECE = re.compile(r"""\s*(?:'([^']*)'|"([^"]*)"|`([^`$]*)`|([A-Za-z_$][\w$]*))\s*$""")
_JS_CWD = re.compile(r"process\s*\.\s*cwd\s*\(\s*\)")
_JS_TEMP_STEP = re.compile(
    r"\s*(?:await\s+)?(?:(?:[A-Za-z_$][\w$]*\s*\.\s*)*(tmpdir|mkdtempSync|mkdtemp)\s*\("
    r"|path\s*\.\s*(?:join|resolve)\s*\(|([A-Za-z_$][\w$]*)(?![\w$]|\s*[.(]))")


def _js_temp_head(body: str, at: int, env, depth: int = 0) -> bool:
    """True when the expression at `at` starts with a folder a temp call made: `os.tmpdir()`, a name bound
    to one, a `path.join` that starts with one, or `fs.mkdtempSync` given one. A mkdtemp prefix that starts
    anywhere else makes the folder there, maybe in the repo, as python's `dir=` does: no temp head."""
    match = _JS_TEMP_STEP.match(body, at)
    if not match or depth > 4:
        return False
    if match.group(2):
        return env.get(match.group(2)) == [_PY_TEMP]
    if match.group(1) == "tmpdir":
        return True
    return _js_temp_head(body, match.end(), env, depth + 1)


def _js_join(args: str, env) -> list:
    """The paths `path.join(...)` or `path.resolve(...)` can hold: each quoted piece, and each name bound
    to a path (`__dirname`, a `const`), joined in order. A later piece it cannot tell is left out, as for
    python. A first piece it cannot tell may be any folder, the repo's or not, so nothing under it is
    judged: empty. A temp folder stays a temp folder (`_PY_TEMP`)."""
    out = [""]
    for number, piece in enumerate(args.split(",")):
        match = _JS_JOIN_PIECE.match(piece)
        quoted = next((g for g in match.groups()[:3] if g is not None), None) if match else None
        options = [quoted] if quoted is not None else list(env.get(match.group(4), ())) if match else []
        if not options:
            if number == 0:
                return []
            continue
        out = [a if a == _PY_TEMP else _join_path(a, b.lstrip("/")) if a else b for a in out for b in options]
    return out if out != [""] else []


def _js_values(groups, env):
    """The path strings one `_JS_STR` match holds, from its five groups."""
    quoted = next((g for g in groups[:3] if g is not None), None)
    if quoted is not None:
        return [quoted]
    if groups[3]:
        return list(env.get(groups[3], ()))
    if groups[4] is not None:
        return _js_join(groups[4], env)
    return []


def _js_hit(body: str, cwd: str, predicate, script: str = "") -> str:
    """`script` is the file the body came from: `__filename` is that path and `__dirname` its folder."""
    env = {"__filename": [script], "__dirname": [os.path.dirname(script)]} if script else {}
    for match in _JS_BIND.finditer(body):
        if _js_temp_head(body, match.end(), env):
            values = [_PY_TEMP]
        elif _JS_CWD.match(body, match.end()):
            values = [""]   # the cwd itself, so a join from it reads repo-relative
        else:
            value = _JS_VALUE.match(body, match.end())
            values = _js_values(value.groups(), env) if value else []
        if values:
            known = env.setdefault(match.group(1), [])
            known.extend(v for v in values if v not in known)
    for match in _JS_ONE.finditer(body):
        for path in _js_values(match.groups(), env):
            if predicate(path, cwd):
                return path
    for match in _JS_TWO.finditer(body):
        for path in _js_values(match.groups()[5:], env):   # the second operand is the one written
            if predicate(path, cwd):
                return path
    return ""


def _inline_script_at(tokens):
    """(kind, index of the script word) for a `python -c SCRIPT` or `node -e SCRIPT` command, else None."""
    index = resolve_command(tokens) if tokens else None
    if index is None:
        return None
    name = basename(tokens[index])
    kind = "py" if _PY_COMMAND.match(name) else "js" if _NODE_COMMAND.match(name) else ""
    flag = _PY_C_FLAG if kind == "py" else _NODE_EVAL_FLAG
    for at in range(index + 1, len(tokens) - 1):
        if kind and flag.match(tokens[at]):
            return kind, at + 1
    return None


def _inline_scripts(command: str):
    """Yield (kind, script, segment number, segments, ends) for each `python -c` and `node -e` script."""
    ends = []
    segments = split_segments(_strip_heredoc_bodies_unconditionally(command), ends)
    for number, segment in enumerate(segments):
        if not _has_inline_flag(segment):
            continue
        tokens = segment_tokens(segment)
        found = _inline_script_at(tokens)
        if found:
            yield found[0], str(tokens[found[1]]), number, segments, ends


_SCRIPT_READ_LIMIT = 256 * 1024
_PY_VALUE_FLAGS = ("-W", "-X", "-Q", "--check-hash-based-pycs")
_NODE_VALUE_FLAGS = ("-r", "--require", "--import", "--loader", "--experimental-loader", "-C", "--conditions",
                     "--env-file", "--input-type", "--title")
_HEREDOC_TARGET = re.compile(
    r"""(?<![\d&<>])>>?(?![&>])\s*(?:'([^']+)'|"([^"]+)"|([^\s'"<>|;&()]+))"""
    r"""|\btee\s+(?:-\S+\s+)*(?:'([^']+)'|"([^"]+)"|([^\s'"<>|;&()-][^\s'"<>|;&()]*))""")


def _script_file_arg(tokens, index: int, kind: str):
    """The script file an interpreter command runs: its first argument that is no flag, else None.
    `-c` / `-e` / `-m` / `-` (a body, a module, stdin) name no file. A flag that takes a value is skipped
    with it; bun and deno name the file after `run`."""
    values = _PY_VALUE_FLAGS if kind == "py" else _NODE_VALUE_FLAGS
    at = index + 1
    while at < len(tokens):
        token = str(tokens[at])
        at += 1
        if token == "--":
            return str(tokens[at]) if at < len(tokens) else None
        if kind == "py" and (_PY_C_FLAG.match(token) or token.startswith("-m")):
            return None
        if kind == "js" and _NODE_EVAL_FLAG.match(token):
            return None
        if token.startswith("-"):
            if token == "-":
                return None
            if token in values:
                at += 1
            continue
        if kind == "js" and token == "run" and basename(str(tokens[index])).split(".")[0] in ("bun", "deno"):
            continue
        return token
    return None


def _script_path(name: str, where: str) -> str:
    """The absolute path a script argument names from folder `where`, else '' (it holds a variable or
    a command substitution, so it cannot be told)."""
    if not name or "$" in name or "`" in name:
        return ""
    name = os.path.expanduser(name)
    if not os.path.isabs(name):
        if not where:
            return ""
        name = os.path.join(where, name)
    return os.path.normpath(name)


def _read_script(path: str):
    """(text, cut): the first `_SCRIPT_READ_LIMIT` bytes of a script file, and True when the file runs past
    them. ('', False) for a folder, a missing or an unreadable file."""
    try:
        if not os.path.isfile(path):
            return "", False
        with open(path, "rb") as handle:
            data = handle.read(_SCRIPT_READ_LIMIT + 1)
    except OSError:
        return "", False
    return data[:_SCRIPT_READ_LIMIT].decode("utf-8", "replace"), len(data) > _SCRIPT_READ_LIMIT


def _heredoc_scripts(raw: str, segments, ends, cwd: str) -> dict:
    """{absolute path: [(segment number, body), ...]} of each file a heredoc in `raw` writes (`cat > f <<EOF`,
    `cat >> f <<EOF`, `tee [-a] f <<EOF`), in the order the bodies come: the script the run of that file
    executes, when it runs after the write. Every body counts: an append adds to the file, it never hides it."""
    written = {}
    for reading in (False, True):
        used = set()
        for _quote, body, header in _split_heredocs(raw, reading)[1]:
            for number, segment in enumerate(segments):
                if number in used or "<<" not in segment or segment.strip() not in header:
                    continue
                match = _HEREDOC_TARGET.search(segment)
                if not match:
                    continue
                used.add(number)
                target = next(group for group in match.groups() if group)
                at = dir_before_segment(segments, number, cwd, ends) or cwd
                path = _script_path(target, at)
                if path and (number, body) not in written.setdefault(path, []):
                    written[path].append((number, body))
                break
    return written


def _script_file_hit(raw: str, cwd: str, predicate) -> str:
    """The test path a script file run by `python3 f.py` or `node f.js` writes: the file as it stands on
    disk, and each heredoc body of the same command that writes it before the run. A folder, a missing or an
    unreadable file is no hit. `__file__` and `__dirname` are the script's own path and folder."""
    ends = []
    segments = split_segments(_strip_heredoc_bodies_unconditionally(raw), ends)
    written = None
    for number, segment in enumerate(segments):
        if not (_PY_HEADER.search(segment) or _NODE_HEADER.search(segment)):
            continue
        tokens = segment_tokens(segment)
        index = resolve_command(tokens) if tokens else None
        if index is None:
            continue
        name = basename(tokens[index])
        kind = "py" if _PY_COMMAND.match(name) else "js" if _NODE_COMMAND.match(name) else ""
        script = _script_file_arg(tokens, index, kind) if kind else None
        if script is None:
            continue
        at = dir_before_segment(segments, number, cwd, ends) or cwd
        path = _script_path(script, at)
        if not path:
            continue
        if written is None:
            written = _heredoc_scripts(raw, segments, ends, cwd) if "<<" in raw else {}
        bodies = [(body, False) for made, body in written.get(path, ()) if made < number]
        bodies.append(_read_script(path))
        for body, cut in bodies:
            if not body:
                continue
            hit = _py_hit(body, at, predicate, path, cut) if kind == "py" else _js_hit(body, at, predicate, path)
            if hit:
                return hit
    return ""


def interpreter_may_write(raw: str) -> bool:
    """True when `raw` holds a heredoc or an inline flag and a write call an interpreter body could make:
    the cheap match that gates `interpreter_write_hit` for a caller that pays to learn its predicate."""
    return ("<<" in raw or any(flag in raw for flag in _INLINE_FLAG_WORDS)) and bool(
        _PY_WRITE_CALL.search(raw) or _JS_ONE.search(raw) or _JS_TWO.search(raw))


def interpreter_write_hit(raw: str, cwd: str, predicate, script_files: bool = False) -> str:
    """Return the path a python or node script in `raw` writes that `predicate(path, cwd)` accepts, else ''.
    Read: the body of each heredoc fed to python or node, quoted or not, and each `python -c` and
    `node -e` script. With `script_files`, also each script file a python or node command runs by name
    (read from disk, and from each heredoc of the same command that writes it before the run). Only the
    builder-test check asks for that: it reads files, which no other caller pays for. A script that only
    reads a path, or names it in a string, hits nothing.
    A crash of the scan reads as no hit: it must never skip the rules after it."""
    try:
        return _interpreter_write_hit(raw, cwd, predicate, script_files)
    except Exception:
        return ""


def _interpreter_write_hit(raw: str, cwd: str, predicate, script_files: bool = False) -> str:
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
    return _script_file_hit(raw, cwd, predicate) if script_files else ""


# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
