"""The guard's frozen family: a write to the settings, the hooks or the global CLAUDE.md.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import fnmatch
import os
import re

import guard_core
from guard_core import (
    LOOP_KEYWORDS, REDIRECT, _expanded, _resolved, _split_heredocs, _strip_heredoc_bodies_unconditionally,
    _walk_wrappers, basename, checkout_root_by_stat, dir_before_segment, is_powershell, norm,
    path_is_inside, resolve_command, segment_tokens, split_segments,
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


# An in-place editor on the segment. `sed` (or `gsed`, GNU sed on macOS) takes `-i` (alone or with a
# suffix) or `--in-place`; `perl` takes `-i` as the last letter of a cluster of flags that take no value
# (`-pi`, `-0777pi.bak`). A flag starts a word (`(?<!\S)`), so `--in-place` inside a quoted pattern is text.
# A cluster is `-Ei`, `-ni`, `-ie`: letters that take no value, then `i`, and what follows is the backup
# suffix. `e`, `f` and `l` take a value, so `-ei` is a script, not `-i`. `_SED_IN_PLACE_FLAG` is the one
# home of the flag; a `sed` word and a `sed` segment are both read by it.
_SED_NAMES = ("sed", "gsed")
_SED_IN_PLACE_FLAG = r"(?<!\S)(?:-[A-Za-dg-km-z]*i|--in-place)"
_SED_IN_PLACE = r"\b(?:g?sed)\b[^\n;|&]*" + _SED_IN_PLACE_FLAG + r"[^\n;|&]*"
# `writes_to` reads one segment, whose quoted words the shell scan has already unquoted, so a `;`, `|` or `&`
# left in it is script text (`-e 's/a/b/;s/c/d/'`) and must not end the match before the path.
_PERL_IN_PLACE_FLAG = r"(?<!\S)-[0-9aCcFlnpsStTuUvwW]*i"
_PERL_IN_PLACE = r"\bperl\b[^\n]*" + _PERL_IN_PLACE_FLAG + r"[^\n]*"


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
                command in _SED_NAMES and any(re.match(_SED_IN_PLACE_FLAG, word) for word in rest)):
            return True
    return False


def writes_to(path: str, cmd: str, command=None, words=(), runs=None) -> bool:
    """True when the command looks like it writes to the path, rather than merely naming it.

    Two ways to write a named file from a shell: redirect onto it, or hand it to a command that
    mutates its arguments. Everything else is a mention.

    Reading the TARGET of the redirect is what separates
    `echo x > .claude/settings.json` from `cat .claude/settings.json 2>/dev/null`. The second
    redirects to the null device. It is also what stops a redirect elsewhere on the line from
    counting as a write to a path named in a comment. A caller that gives `runs` (the command name that
    runs in the segment, `_commands_run`) has `sed -i` and `perl -i` count only when that command runs, so
    `grep sed -i P` and `echo perl -i P` name an in-place edit and make none.
    """
    target = re.escape(path)
    if re.search(r"\d?>>?\s*&?\s*['\"]?" + target, cmd):   # `>` and `>&` redirect onto the path, with or without a space; `>&1` names no file
        return True
    # `command` is the segment's resolved command name, given by a caller that reads a mutating
    # word only in command position (`grep -n install tests/x.py` reads, never writes).
    if command is not None and not _mutates_as_command(command, words):
        in_place = {"sed": _SED_IN_PLACE, "gsed": _SED_IN_PLACE, "perl": _PERL_IN_PLACE}.get(command)
        return bool(in_place) and bool(re.search(in_place + target, cmd))
    if re.search(MUTATING_COMMAND + r"[^\n;|&]*" + target, cmd):
        return True
    if (runs is None or runs.intersection(_SED_NAMES)) and re.search(_SED_IN_PLACE + target, cmd):
        return True
    if (runs is None or "perl" in runs) and re.search(_PERL_IN_PLACE + target, cmd):
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
# `cat <<EOF | sh`, an eval of a heredoc, a subshell `( ... > P)` and `"$( ... )"`; `git config --file P`, `>| P` and a quoted redirect target with a space.
# Main missed these too. `sort -o`, `less -o` and `git diff --output` are read (`_output_targets`).
_PRINTERS = frozenset(("echo", "printf", "cat", "grep", "wc", "jq"))
_QUIET = _PRINTERS | {"cd", "set-location"}
# Read-only tools beside the printers, for a sed `e` command (`_sed_command_words`). Not part of `_PRINTERS`:
# that set also makes a segment quiet (`_kind`), and `sort -o P` or `uniq in P` write. `_command_reads` drops
# the forms of each tool that write.
_READ_ONLY_TOOLS = frozenset(("head", "tail", "ls", "less", "sort", "uniq", "diff", "stat", "file", "find"))
_FIND_WRITERS = frozenset(("-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprint0", "-fprintf", "-fls"))


# Per command, the short flags that write a file (`_OUTPUT_SHORTS`), the short flags that take a value
# (`_VALUE_SHORTS`: what follows one in its cluster is its value, never a flag), and the long flags that
# write a file, each with the fewest letters a command reads for it (`_OUTPUT_LONGS`). `git diff`, `git log`
# and `git show` are the command names `_output_targets` gives a `git` call with that subcommand.
_OUTPUT_SHORTS = {"sort": "o", "less": "oO", "curl": "oDc", "wget": "Ooa"}
_VALUE_SHORTS = {"sort": "kStT", "less": "bhjkPpTtxyzD#", "curl": "AbCcDdEeFHKmPQrTtUuwXxYyz",
                 "wget": "oaeiBtTwQPlARDIXU"}
_GIT_OUTPUT = (("output", 6),)   # git reads no shorter form: it is a prefix of other flags
_OUTPUT_LONGS = {"sort": (("output", 1),), "less": (("log-file", 3),),
                 "curl": (("output", 3), ("dump-header", 2), ("cookie-jar", 7)),
                 "wget": (("output-document", 9), ("output-file", 8), ("append-output", 2)),
                 "git diff": _GIT_OUTPUT, "git log": _GIT_OUTPUT, "git show": _GIT_OUTPUT}
_GIT_OUTPUT_SUBCOMMANDS = ("diff", "log", "show")


def _output_flag_value(command: str, word: str):
    """The one home of the flags that name the file a command writes. None when `word` is no such flag of
    `command`; else the file glued to it (`-ofile`, `--output=file`), or '' when the next word is the file
    (`-o file`, `--output file`). `sort`: `-o` in a short cluster, `--output` or a prefix of it (`--o`, `--out`).
    `less`: `-o` and `-O`, `--log-file` or a prefix of it from `--log`, in any case. `git diff`, `git log` and
    `git show`: `--output` only, as git reads no shorter form (it is a prefix of other flags). `curl`: `-o`,
    `-D` and `-c`, `--output` or a prefix from `--out`, `--dump-header` or a prefix from `--du`, `--cookie-jar`
    or a prefix from `--cookie-`. `wget`: `-O`, `-o` and `-a`, `--output-document` or a prefix from `--output-do`,
    `--output-file` or a prefix from `--output-f`, `--append-output` or a prefix from `--ap`."""
    if command not in _OUTPUT_LONGS or not word.startswith("-") or word == "-":
        return None
    if word.startswith("--"):
        flag, equals, value = word.partition("=")
        typed = flag[2:].lower() if command == "less" else flag[2:]
        if not any(len(typed) >= least and name.startswith(typed) for name, least in _OUTPUT_LONGS[command]):
            return None
        return value if equals else ""
    for place, letter in enumerate(word[1:], 1):
        if letter in _OUTPUT_SHORTS.get(command, ""):
            return word[place + 1:]
        if letter in _VALUE_SHORTS.get(command, ""):
            return None
    return None


def _output_targets(words):
    """The files that the output flags in one segment's unquoted `words` name (`_output_flag_value`)."""
    command, rest = _segment_command(words)
    if command == "git":
        subcommand = next((name for name in [word for word in rest if not word.startswith("-")][:2]
                           if name in _GIT_OUTPUT_SUBCOMMANDS), "")
        if subcommand:
            command = "git " + subcommand
    targets = []
    for at, word in enumerate(rest):
        value = _output_flag_value(command, word)
        if value:
            targets.append(value)
        elif value == "" and at + 1 < len(rest):
            targets.append(rest[at + 1])
    return targets


def _split_background(segment):
    """`segment` cut at each lone, unquoted `&` (a background job ends there, so the next word starts a
    command, as after `;`). `&&`, `|&`, `>&`, `<&` and `&>` hold an `&` that is no break. A quoted or escaped
    `&` is text. `split_segments` keeps a lone `&` inside its segment, for callers that read a job as one."""
    parts, start = [], 0
    for at, char, quote in guard_core.walk_quotes(segment):
        if char != "&" or quote:
            continue
        if (segment[at - 1:at] if at else "") in ("&", "|", ">", "<") or segment[at + 1:at + 2] in ("&", ">"):
            continue
        parts.append(segment[start:at])
        start = at + 1
    parts.append(segment[start:])
    return [type(segment)(part) for part in parts]


def _command_reads(command: str, args) -> bool:
    """True when `command` with `args` only reads: a printer, or a read-only tool (`_READ_ONLY_TOOLS`) with no
    form that writes or runs a program. `find` with `-exec` or `-delete`, `sort` with an output, compress or
    temp-folder option (any short flag cluster that holds `o` or `T`), `uniq` with a second operand (its output
    file), `less` with a log file, and `file -C` (writes a compiled magic file) are not reads."""
    if command in _PRINTERS:
        return True
    if command not in _READ_ONLY_TOOLS:
        return False
    shorts = [word[1:] for word in args if re.fullmatch(r"-[^-].*", word)]
    longs = [word for word in args if word.startswith("--")]
    if command == "find":
        return not _FIND_WRITERS.intersection(args)
    if command == "sort":
        return not any("T" in word for word in shorts) and not any(
            _output_flag_value("sort", word) is not None for word in args) and not any(
            word.startswith(("--c", "--t")) for word in longs)
    if command == "uniq":
        return sum(1 for word in args if not word.startswith("-")) <= 1
    if command == "less":
        return not any(_output_flag_value("less", word) is not None for word in args) and not any(
            "log" in word.lower() for word in longs)
    if command == "file":
        return not any("C" in word for word in shorts) and "--compile" not in longs
    return True
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


def _fixed_prefix_outside(prefix: str, stop: str, predicate, cwd) -> bool:
    """True when a `cp` destination, cut at its first `$`, backtick, glob or brace character (`stop`),
    has a literal prefix in a fixed directory that `predicate` does not accept. Whatever the rest of
    the word expands to is read as one name in that directory. A redirect character, a prefix with no
    directory (`bak_$x`, `$x`) and one inside a test root (`tests/$x`, `tests/bak_$x`) are not."""
    if stop in "<>" or "/" not in prefix.replace("\\", "/"):
        return False
    return not (predicate(prefix + "x", cwd) or predicate(prefix.rstrip("/\\") + "/_", cwd))


def _cp_start(raw, keywords=False):
    """The index of the `cp` word of a segment, past its `VAR=value` words (and past `do`, `then` and
    the other loop keywords when `keywords`), else None when the command is not `cp`."""
    start = 0
    while start < len(raw) and (_ASSIGNMENT.match(raw[start]) or keywords and raw[start] in LOOP_KEYWORDS):
        start += 1
    return start if _name(raw[start] if start < len(raw) else "") == "cp" else None


def _copy_reads(raw, predicate, cwd, keywords=False, prefix=False):
    """The indexes of the words of a `cp` segment that are only read, else an empty set. With `prefix`, a
    destination that holds a `$`, a glob or a brace is read by its literal prefix (`_fixed_prefix_outside`)."""
    words = [_unquoted(word) for word in raw]
    start = _cp_start(raw, keywords)
    if start is None:
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
    if not operands or not target:
        return set()
    unsafe = _CP_DEST_UNSAFE.search(target)
    if unsafe:
        return set(operands) if prefix and _fixed_prefix_outside(
            target[:unsafe.start()], unsafe.group(), predicate, cwd) else set()
    if predicate(target, cwd) or predicate(target.rstrip("/\\") + "/_", cwd):
        return set()
    return set(operands)


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
# ponytail: a `while read` loop, `find -delete`, a `$(...)` whose body holds a quoted paren, and a
# root fed through a variable that a loop or an xargs itself assigns are not read.
_MARK = "\0"
_MARK_AT = re.compile("`\0`|\0")
_WORD_MARK = "\x04"   # the mark as `_copy_outer` splits words: `_quoted_words` keeps it, not NUL; no other mark shares its byte
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


def _roots(words) -> list:
    """The words of a segment that name where its command reads: for `find`, the words before the
    first `-`, `(` or `!` (`.` when there are none); for grep and rg, the words after the pattern;
    for any other command, its words that are not a flag, a redirect or a redirect's target."""
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
    if name == "git":
        listed = _git_listing_roots(args)
        if listed is not None:
            return listed
    grep = name in _GREP_COMMANDS
    roots, skip, flags_over, has_pattern = [], False, False, False
    for word in args:
        if skip:
            skip = False
        elif (">" in word or "<" in word) and _is_redirect(word):
            skip = True
        elif word == "&":
            continue   # the `&` of `&>`: `_quoted_words` splits it from the `>` that skips the target
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
    return roots[1:] if grep and not has_pattern else roots


_GLOB_MARK = "\x02"   # starts a glob pathspec root: MARK folder MARK glob
_SEGMENT_GLOB = "\x03"   # first char of a glob that a shell expands: `*` stays inside one path segment
_GIT_LIST_FLAGS = frozenset(("--files-with-matches", "--name-only", "--files-without-match"))
_GIT_LIST_PATTERN_FLAGS = frozenset(("-x", "--exclude"))   # `git ls-files` flags whose next word is a pattern


def _glob_root(folder: str, word: str, shell: bool = False) -> str:
    """A pathspec word as a root: the word, or, for a glob (`'*.py'`), a marked root that `_dot_roots`
    reads as the tests under `folder` that the glob matches. A glob pathspec names tracked paths at
    any depth, so it cannot be judged as the one path its spelling shows. A leading `./` is dropped.
    Pathspec magic (`:(glob)`, `:!`, `:^`) and a backslash escape are not read: they give the whole
    of `folder`, which refuses when it holds any test (conservative). `shell` reads a glob that the
    shell expands, whose `*` does not cross a `/` (`sed -i ... hooks/*.py`), and has no magic."""
    text = _unquoted(word)
    if not shell and (text.startswith(":") or "\\" in text):
        return _GLOB_MARK + folder + _GLOB_MARK
    while text.startswith("./"):
        text = text[2:]
    if not re.search(r"[*?\[]", text):
        return word
    return _GLOB_MARK + folder + _GLOB_MARK + (_SEGMENT_GLOB if shell else "") + text


def _pathspec_roots(folder: str, word: str) -> list:
    """The roots one pathspec word stands for. A glob or magic word is one marked root (`_glob_root`).
    Any other relative word is itself and, as a folder, `<word>/*`: the tests under it, which
    `_dot_roots` reads from disk. A word that is a file matches nothing under it."""
    root = _glob_root(folder, word)
    text = _unquoted(word)
    if root != word or text in ("", ".", "./") or text.startswith(("/", "~", "$")):
        return [root]
    return [word, _glob_root(folder, text.rstrip("/") + "/*")]


def _excluded_pathspec(word: str) -> str:
    """The path an exclusion pathspec drops (`:!tests`, `:^tests`, `:(exclude)tests`), else ''. A value
    that starts with more magic or holds `$`, a backtick, a quote, a brace, a bracket or a backslash is
    not read: it gives '', and the word stays a root (`_glob_root`), which keeps the guard strict."""
    text = _unquoted(word)
    for magic in (":!", ":^", ":(exclude)"):
        if text.startswith(magic):
            value = text[len(magic):]
            if value and not value.startswith((":", "(", "/", "!", "^")) and not re.search(r"[$`'\"{}\[\\]", value):
                return value
    return ""


def _walks_from_git_folder(word: str) -> bool:
    """True for an include pathspec that `_dot_roots` walks from the git folder, so a path it reaches is
    spelled under that folder, as an exclusion pathspec is: `.` and a glob. A folder pathspec (`hooks`) is
    walked from itself, where `:!tests` would drop `hooks/tests` that git still lists, so it is not."""
    text = _unquoted(word)
    return text in (".", "./") or bool(re.search(r"[*?\[]", text))


def _git_listing_roots(args):
    """The roots of a `git ls-files` or `git grep -l` segment, which print tracked paths: its pathspecs
    (for `grep`, the words after the pattern), else `.`, the whole checkout, read as a `.` root is
    (`_dot_roots`). A redirect and its target are not pathspecs, as in `_roots`, and nor is the value
    of `-x` or `--exclude`; a glob pathspec is a marked root, and a folder pathspec is read as the
    tests under it (`_pathspec_roots`). An exclusion pathspec (`_excluded_pathspec`) is no root:
    `_name_filters` reads it. A `-C DIR` before the command is its folder. None for any other `git`
    command, and for a `git grep` that prints matching lines, not paths."""
    listed = _git_listing_pathspecs(args)
    if listed is None:
        return None
    folder, words = listed
    roots = [root for word in words if not _excluded_pathspec(word) for root in _pathspec_roots(folder, word)]
    return roots or [folder]


def _git_listing_pathspecs(args):
    """(folder, pathspec words) of a `git ls-files` or `git grep -l` segment (`_git_listing_roots`), else
    None."""
    folder, at = ".", 0
    while at < len(args) and args[at].startswith("-"):
        if args[at] in ("-C", "-c") and at + 1 < len(args):
            folder = args[at + 1] if args[at] == "-C" else folder
            at += 1
        at += 1
    if at >= len(args) or args[at] not in ("ls-files", "grep"):
        return None
    rest = args[at + 1:]
    if args[at] == "ls-files":
        roots, skip, flags_over = [], False, False
        for word in rest:
            if skip:
                skip = False
            elif (">" in word or "<" in word) and _is_redirect(word):
                skip = True
            elif word == "&":
                continue   # the `&` of `&>`, as in `_roots`
            elif not flags_over and word == "--":
                flags_over = True
            elif not flags_over and word in _GIT_LIST_PATTERN_FLAGS:
                skip = True
            elif flags_over or not word.startswith("-"):
                roots.append(word)
    else:
        if not any(word in _GIT_LIST_FLAGS or re.fullmatch(r"-[A-Za-z0-9]*[lL][A-Za-z0-9]*", word)
                   for word in rest):
            return None
        roots = _roots(["grep"] + rest)
    return folder, roots


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


def _text_roots(text: str, cwd: str = "", predicate=None) -> list:
    """The roots of every pipeline of a command text, in order, each once. A pipeline that ends in a
    count (`_prints_a_count`) gives none. `cwd` and `predicate` read a `.` root (`_dot_roots`)."""
    ends = []
    segments = split_segments(text, ends)
    segments, ends, _changed = _fed_segments(segments, ends, cwd, predicate)
    parsed = [_quoted_words(segment) for segment in segments]
    fed_by = [_piped_into(ends, parsed, at) for at in range(len(parsed))]
    roots = []
    for at, words in enumerate(parsed):
        if not words or at in fed_by or _prints_a_count(words):
            continue   # empty, not the last of its pipeline, or a count
        chain, stage = [], at
        while stage is not None:
            chain = _dot_roots(_roots(parsed[stage]), cwd, predicate, _name_filters(parsed[stage])) + chain
            stage = fed_by[stage]
        roots.extend(word for word in chain if word not in roots)
    return roots


def _fed_substitutions(cmd: str, cwd: str = "", predicate=None) -> str:
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
        stack.append(_text_roots(text, cwd, predicate))
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
                filled.extend(variable.sub(lambda _m, item=item: item, word) for item in items)
        words = filled
    return words


def _put_roots(words, mark, roots):
    """The commands that `words` stands for with `mark` put as one copy of the word per root. A mark
    glued to other text (`{}.bak`) names a file inside a root that is a folder, so a second command
    reads it as `ROOT/x.bak`; the first reads it as `ROOT.bak`, for a root that is a file."""
    plain = [part for word in words
             for part in ([word.replace(mark, root) for root in roots] if mark in word else [word])]
    inside = [part for word in words
              for part in ([word.replace(mark, root if word == mark else root.rstrip("/") + "/x")
                            for root in roots] if mark in word else [word])]
    return [plain] if inside == plain else [plain, inside]


_TREE_SKIP = frozenset(("node_modules", "__pycache__", "venv"))
_TREE_LIMIT = 20000   # files read before the walk gives up


def _first_test_under(where: str, predicate, glob: str = "", only=(), top=None) -> str:
    """The first path under the folder `where` (relative to it) that `predicate` accepts, else ''.
    With `glob`, only a path whose relative spelling matches it (a pathspec glob: `*` crosses `/`; a
    glob that starts with `_SEGMENT_GLOB`, one the shell expands: `*` stays in one segment). With
    `only` (`_name_filters`), only a file whose own name and path pass them (`_name_passes`); `top` is the
    root word a `find` printed the path under. Both are tested before `predicate` runs. Read from disk, top down,
    skipping hidden folders, `node_modules`, `venv` and `__pycache__`.
    ponytail: a tree of more than `_TREE_LIMIT` files with no test found early reads as holding none."""
    segmented = glob.startswith(_SEGMENT_GLOB)
    glob = glob.removeprefix(_SEGMENT_GLOB)
    seen = 0
    for folder, names, files in os.walk(where):
        names[:] = sorted(name for name in names if not name.startswith(".") and name not in _TREE_SKIP)
        prefix = os.path.relpath(folder, where).replace(os.sep, "/")
        prefix = "" if prefix == "." else prefix + "/"
        for name in sorted(files):
            seen += 1
            if only and not _name_passes(name, only, prefix + name, top):
                continue
            if glob:
                rel = prefix + name
                if (segmented and rel.count("/") != glob.count("/")) or not fnmatch.fnmatchcase(rel, glob):
                    continue
            full = os.path.join(folder, name)
            if predicate(full, where):
                return os.path.relpath(full, where)
        if seen > _TREE_LIMIT:
            break
    return ""


def _folder_root(root: str, cwd: str) -> str:
    """The folder a root names when it is a plain path to a folder that exists on disk and sits inside
    the checkout that holds `cwd` (`hooks`, `./hooks/`, `../hooks` after a `cd`, an absolute path), else
    ''. A relative path that stays inside `cwd` needs no checkout. A word with a quote, `$`, `~`, a glob
    character or a backslash, a leading `-`, and a path outside the checkout are not read."""
    text = _unquoted(root)
    if text in ("", ".", "./") or re.search(r"[$`~*?\[\\]", text) or text.startswith(("-", ":")):
        return ""
    full = os.path.normpath(os.path.join(cwd, text))
    if not os.path.isdir(full):
        return ""
    if os.path.isabs(text) or path_is_inside(full, cwd) is not True:
        top = checkout_root_by_stat(os.path.realpath(cwd))
        if not top or path_is_inside(os.path.realpath(full), top) is not True:
            return ""
    return text


_NAME_EXCLUDE = "\x05"   # marks an excluded glob in the tuple `_name_filters` returns
_PATH_EXCLUDE = "\x06"   # marks a `find -not -path` glob: matched against the path find prints
_SPEC_EXCLUDE = "\x07"   # marks a git exclusion pathspec: matched against the path under the git folder
_DIR_EXCLUDE = "\x08"   # marks a `grep --exclude-dir` glob: matched against each folder name above the file
_EXCLUDES = (_NAME_EXCLUDE, _PATH_EXCLUDE, _SPEC_EXCLUDE, _DIR_EXCLUDE)


def _name_passes(name: str, filters, rel=None, top=None) -> bool:
    """Whether a file named `name` is reached by `filters` (`_name_filters`): it matches one of the wanted
    globs, when there are any, and none of the excluded ones, as `find -name`, `-not -name`, `grep
    --include` and `--exclude` read. `rel` is the file's path under the walked folder. A `-not -path`
    glob drops a file whose path as find prints it (`top/rel`) matches it; a git exclusion pathspec drops
    `rel` when it is that path, under it, or matches it as a glob. With no `rel` or `top` to read, an
    exclusion drops nothing, which keeps the guard strict."""
    wanted = [glob for glob in filters if not glob.startswith(_EXCLUDES)]
    if wanted and not any(fnmatch.fnmatchcase(name, glob) for glob in wanted):
        return False
    for glob in filters:
        mark, value = glob[:1], glob[1:]
        if mark == _NAME_EXCLUDE and fnmatch.fnmatchcase(name, value):
            return False
        if mark == _PATH_EXCLUDE and rel is not None and top is not None and fnmatch.fnmatchcase(
                top.rstrip("/") + "/" + rel, value):
            return False
        if mark == _DIR_EXCLUDE and rel is not None and any(
                fnmatch.fnmatchcase(part, value) for part in rel.split("/")[:-1]):
            return False
        if mark == _SPEC_EXCLUDE and rel is not None and (
                rel == value.rstrip("/") or rel.startswith(value.rstrip("/") + "/") or fnmatch.fnmatchcase(rel, value)):
            return False
    return True


def _name_filters(words) -> tuple:
    """The file-name globs that limit what a `find`, `grep` or git listing segment reads: the values of
    `-name` or `--include`, and the excluded ones, each marked: `-not -name`, `! -name` or `--exclude`
    (`_NAME_EXCLUDE`), `-not -path` or `! -path` (`_PATH_EXCLUDE`), and a git listing's exclusion pathspecs
    when each other pathspec is `.` or a glob (`_SPEC_EXCLUDE`, `_excluded_pathspec`,
    `_walks_from_git_folder`), and a `grep --exclude-dir` (`_DIR_EXCLUDE`), so a walk of its folder roots
    counts only the files it reaches (`_name_passes`). () when there is none, and for a `find` that holds
    `-o`, a group, or a `-not` or `!` that does not lead straight into `-name VALUE` or `-path VALUE`,
    which can widen or invert what `-name` picks, and for a value that holds `$` or a backtick, a brace
    sequence (`{a..b}`, which `_brace_split` reads as text), a backslash left after one unescape pass
    (`\\\\`), or a brace list of `_BRACE_LIMIT` words or more. A wanted value's brace list is several
    filters (`_brace_words`), and a backslash escape reads as its literal character, so a walk counts a
    file that any of them matches. An excluded value with a brace, a bracket or a backslash is not read,
    and drops nothing. () counts every file, so a form not read keeps the guard strict. A `find` stops
    at its first `-exec`."""
    index = resolve_command(tuple(words))
    if index is None:
        return ()
    name, args = _name(words[index]), list(words[index + 1:])
    values = []
    if name == "find":
        at = 0
        while at < len(args):
            word = args[at]
            if word in _FIND_EXEC:
                break
            if word in ("-o", "-or", "(", "\\("):
                return ()
            if word in ("-not", "!", "\\!"):
                test = args[at + 1:at + 2]
                if test not in (["-name"], ["-path"]) or at + 2 >= len(args):
                    return ()
                values.append((_NAME_EXCLUDE if test == ["-name"] else _PATH_EXCLUDE, args[at + 2]))
                at += 3
                continue
            if word == "-name" and at + 1 < len(args):
                values.append(("", args[at + 1]))
            at += 1
    elif name in _GREP_COMMANDS and name != "rg":
        for at, word in enumerate(args):
            if word == "--":
                break
            for flag, mark in (("--include", ""), ("--exclude", _NAME_EXCLUDE), ("--exclude-dir", _DIR_EXCLUDE)):
                if word.startswith(flag + "="):
                    values.append((mark, word.partition("=")[2]))
                elif word == flag and at + 1 < len(args):
                    values.append((mark, args[at + 1]))
    elif name == "git":
        listed = _git_listing_pathspecs(args)
        pathspecs = listed[1] if listed else []
        if all(_excluded_pathspec(word) or _walks_from_git_folder(word) for word in pathspecs):
            values = [(_SPEC_EXCLUDE, _excluded_pathspec(word)) for word in pathspecs if _excluded_pathspec(word)]
    values = [(mark, _unquoted(value)) for mark, value in values]
    if any(re.search(r"[$`]", value) for _mark, value in values):
        return ()
    filters = []
    for mark, value in values:
        if mark:
            if not re.search(r"[{}\[\\]", value):
                filters.append(mark + value)
            continue
        variants = _brace_words(value)
        if len(variants) >= _BRACE_LIMIT:
            return ()
        for variant in variants:
            if re.search(r"\{[^{},]*\.\.[^{},]*\}", variant):
                return ()
            unescaped = re.sub(r"\\(.)", r"\1", variant)
            if "\\" in unescaped:
                return ()
            filters.append(unescaped)
    return tuple(filters)


def _dot_roots(roots, cwd: str, predicate, names=()) -> list:
    """`roots` with each `.` or `./` put as the first test path under it, so a writer fed from the whole
    checkout is judged by a test it can reach. A `.` root that holds no test stays as it is, and so
    does one when `cwd` or `predicate` is not given. A folder root (`_folder_root`) is read the same
    way, from disk, under that folder; a brace list of them (`{docs,hooks}`) is read one folder at a
    time (`_brace_words`). `names` (`_name_filters`) limit the walk to the files the segment reaches. A
    glob pathspec root (`_glob_root`) is put the same way, as the first test path under its folder
    that the glob matches. When none matches, or `cwd` or `predicate` is not given, it names nothing
    that is judged and is dropped."""
    reading = bool(cwd) and predicate is not None
    out = []
    for root in roots:
        variants = [] if root.startswith(_GLOB_MARK) or not reading else _brace_words(root)
        if len(variants) > 1:
            out.extend(_dot_roots(variants, cwd, predicate, names))
        elif root.startswith(_GLOB_MARK):
            folder, _mark, glob = root[len(_GLOB_MARK):].partition(_GLOB_MARK)
            only = tuple(name for name in names if name.startswith(_SPEC_EXCLUDE))
            found = _first_test_under(os.path.join(cwd, folder), predicate, glob, only) if reading else ""
            if found:
                out.append(os.path.join(folder, found) if folder != "." else "./" + found)
        elif reading and root in (".", "./"):
            found = _first_test_under(cwd, predicate, only=names, top=root)
            out.append("./" + found if found else root)
        elif reading and _folder_root(root, cwd) and not predicate(root, cwd):
            # a folder that is itself a test path (`tests`) stays as it is: it is judged as it stands
            folder = _folder_root(root, cwd)
            found = _first_test_under(os.path.join(cwd, folder), predicate, only=names, top=folder)
            out.append(os.path.join(folder, found) if found else root)
        else:
            out.append(_named_test(root, cwd, predicate, names) if reading else root)
    return out


def _named_test(root: str, cwd: str, predicate, names) -> str:
    """`root`, or the path `root/<name>` when a folder root that is not on disk is searched for a name
    (`_name_filters`) that is a test file: `find hooks -name 'test_*.py'` writes tests wherever `hooks` is,
    since its walk cannot be read. A root with a quote, `$`, a backtick, `~` or a brace, and a folder that
    exists (its walk is read from disk), stay as they are. An excluded glob names no file."""
    text = _unquoted(root)
    names = [name for name in names if not name.startswith(_EXCLUDES)]
    if (not names or re.search(r"[$`~{}\\]", text) or text.startswith(("-", ":", "/"))
            or os.path.exists(os.path.join(cwd, text))):
        return root
    return next((joined for joined in (os.path.join(text, name) for name in names)
                 if predicate(joined, cwd)), root)


def _fed_segments(segments, ends, cwd: str = "", predicate=None):
    """(segments, ends, changed): the segments with each `for` variable, xargs and `find -exec` put as
    the plain command the shell runs. An xargs command takes the roots of the segments piped into it,
    in the `-I` string's place, else as last words. A `find -exec` segment becomes its commands, with
    `{}` put as the find roots. `_walk_wrappers` already reads the xargs flags. `cwd` and `predicate`
    read a `.` root (`_dot_roots`) in the folder the segment runs in."""
    out, out_ends, out_words, loops, changed = [], [], [], [], False
    for number, segment in enumerate(segments):
        words = original = _quoted_words(segment)
        lead = 0
        while lead < len(words) and words[lead] in LOOP_KEYWORDS:
            lead += 1
        head = words[lead] if lead < len(words) else ""
        if head == "for" and words[lead + 2:lead + 3] == ["in"]:
            loops.append((words[lead + 1], words[lead + 3:]))
        elif head in ("while", "until", "select"):
            loops.append(("", []))
        elif head == "done" and loops:
            loops.pop()
        words = _fill_loop_variables(words, loops)
        rewritten = [words]

        def dot_roots(roots, names=()):
            where = (dir_before_segment(out + [segment], len(out), cwd, out_ends) or cwd) if cwd else ""
            return _dot_roots(roots, where, predicate, names)

        index, chain = _walk_wrappers(tuple(words))
        xargs = next((flags for word, flags in chain if word == "xargs"), None)
        if index is not None and xargs is not None:
            roots, back = [], _piped_into(out_ends, out_words, len(out))
            if back is not None and _prints_a_count(out_words[back]):
                back = None
            while back is not None:
                roots = dot_roots(_roots(out_words[back]), _name_filters(out_words[back])) + roots
                back = _piped_into(out_ends, out_words, back)
            replace = None
            for flag, value in xargs:
                if flag == "-I":
                    replace = value
                elif flag in ("-i", "--replace"):
                    replace = value or "{}"
            if roots:
                command = words[index:]
                rewritten = [command + roots] if not replace else _put_roots(command, replace, roots)
        elif index is not None and _name(words[index]) == "find":
            roots, commands, at = dot_roots(_roots(words), _name_filters(words)), [], index + 1
            while at < len(words):
                if words[at] in _FIND_EXEC:
                    stop = at + 1
                    while stop < len(words) and words[stop] not in _FIND_END:
                        stop += 1
                    commands.extend(_put_roots(words[at + 1:stop], "{}", roots))
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


def _fed_command(cmd: str, cwd: str = "", predicate=None):
    """(text, segments, ends) of `cmd` as the shell runs it with the fed roots put in place, else
    None when it holds no fed form or reads as PowerShell."""
    if is_powershell(cmd):
        return None
    text = _fed_substitutions(cmd, cwd, predicate)
    plain = _resolve_vars(text)
    ends = []
    segments = split_segments(plain, ends)
    segments, ends, changed = _fed_segments(segments, ends, cwd, predicate)
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
    def scan(text, fed=None, copy_outer=False):
        return _shell_write_scan(text, cwd, predicate, holds, follow_cd, command_position,
                                 predicate_command, fed, copy_outer)

    if not read_fed:
        return scan(cmd)
    texts, too_deep = _substitutions(cmd, powershell=is_powershell(cmd))
    hit = scan(cmd, copy_outer=True)
    for text, _in_message in ([] if too_deep else texts[:-1]):
        hit = hit or scan(text)
    if hit:
        return hit
    fed = _fed_command(cmd, cwd, predicate)
    return scan(fed[0], fed[1:]) if fed else ""


def _copy_outer(segment):
    """A `cp` segment whose substitutions are each a whole source word (`$(...)`, a backtick pair,
    quoted or not) or sit in the destination after a fixed directory (`/tmp/$(...)`, `tests/$(...)`),
    as the text around them with an `x` in each one's place, else the segment. Any other substitution
    leaves the segment as main reads it: one in a flag, glued to a flag (`-t$(...)`,
    `--target-directory=$(...)`), after a flag that takes the target directory, in a word that is
    neither a source nor the destination, or in a destination with no directory before it (`$(...)`,
    `bak_$(...)`). The `x` then lets the predicate judge the destination by its directory."""
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
        if word in (_WORD_MARK, "`%s`" % _WORD_MARK) and at < len(outer) - 1 and not _takes_target(outer[at - 1]):
            continue   # a whole source word
        # The destination (the last word, not after a target flag) with a fixed directory before its first
        # substitution: the substitution reads as one name in that directory, so the `cp` is judged by it.
        prefix = re.split("[`%s]" % _WORD_MARK, word, 1)[0]
        if at < len(outer) - 1 or "/" not in prefix or _takes_target(outer[at - 1]):
            return segment
    return type(segment)(_MARK_AT.sub("x", texts[-1][0]))


def _takes_target(word) -> bool:
    """True when a `cp` word takes the next word as its target directory: a short cluster that ends in
    `t`, or `--target-directory` or a long flag it starts with."""
    if word.startswith("--"):
        return len(word) > 2 and "=" not in word and "target-directory".startswith(word[2:])
    return word.startswith("-") and word.endswith("t")


def _shell_write_scan(cmd, cwd, predicate, holds, follow_cd, command_position, predicate_command,
                      fed=None, copy_outer=False):
    """`_shell_write_hit` for one text. `fed` is the (segments, ends) that `_fed_command` made of it."""
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
    for number, raw in enumerate(parsed):
        linked = _cp_link_source(raw, holds, cwd, bool(fed))
        if linked:
            return linked
        data = set() if closed else _copy_reads(raw, predicate, cwd, bool(fed), command_position)
        sed_targets = {}
        if command_position:
            sed_targets = _sed_script_words(scripts[number])   # the builder test check only: a script names no file but w, W, e, with or without -i; read with its newlines
            if not closed:
                data = data | set(sed_targets)   # a closed segment keeps its script words as words, and still reads the targets
        if not closed:
            # A sed with no in-place option reads its script as text: an in-place flag spelled inside it is no flag.
            data = data | {at for at in _sed_script_words(parsed[number])
                           if re.search(_SED_IN_PLACE_FLAG, _unquoted(raw[at]))}
            # A perl script (the word after `-e`) that spells an in-place flag is text, as a sed script is.
            data = data | _perl_script_words(raw)
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
                glued = index and word.startswith("&") and raw[index - 1].endswith(">")
                if glued:   # `>&FILE` splits as `>` and `&FILE`: the `&` is part of the operator, FILE is the target
                    word = word[1:]
                pieces = _words_of(word) if "'" in word or '"' in word else [word]
                words.extend(pieces)
                shown.extend(pieces)
                kept = scripts[number][index]
                if glued:
                    kept = kept[1:]
                script.extend(_words_of(kept) if "'" in kept or '"' in kept else [kept])
            files, commands = sed_targets.get(index, ((), ()))
            # a sed script's w or W names a file, and its e runs a command: the words that command writes
            for target in [*files, *(word for command in commands for word in _sed_command_words(command))]:
                # `>` marks the target as written, as a redirect would: a sed with no -i has no other write mark.
                words.extend((">", target))
                shown.extend((">", target))
                script.extend((">", target))
        for target in _output_targets([_unquoted(word) for word in raw]):   # the file an output flag names is written
            words.extend((">", target))
            shown.extend((">", target))
            script.extend((">", target))
        text = " ".join(shown)
        at = (dir_before_segment(segments, number, cwd, ends) or cwd) if follow_cd else cwd
        for _files, commands in sed_targets.values():
            for command in commands:   # a sed `e` runs a shell command in the sed's folder: its redirects are read too
                hit = _shell_write_scan(command, at, predicate, holds, follow_cd, command_position,
                                        predicate_command)
                if hit:
                    return _from_cwd(hit, at, cwd) if follow_cd else hit
        runs = _commands_run(raw)
        verb = _segment_command(words)[0] if predicate_command else ""
        for word in words:
            if word.startswith("-") or REDIRECT.fullmatch(word):
                continue
            if not word or word in (">", ">>"):
                continue
            if follow_cd and word == '""':
                continue   # the data placeholder is no path, though `cd tests` makes it one in that folder
            if (predicate(word, at, verb) if predicate_command else predicate(word, at)) and writes_to(word, text, *(_segment_command(script) if command_position else ()), runs=runs):
                return _from_cwd(word, at, cwd) if follow_cd else word
    return ""


_BRACE_LIMIT = 256   # words one word's brace groups give before the expansion stops


def _brace_split(word: str):
    """(head, parts, tail) for the first unquoted `{a,b}` group of `word` that has a top-level comma,
    else None. `${...}` is no group, a quoted or escaped brace is text, and a `{x}` with no comma is
    text, as in bash."""
    quote, depth, start, cuts, skip = "", 0, -1, [], False
    for at, char in enumerate(word):
        if skip:
            skip = False
        elif quote:
            if char == quote:
                quote = ""
            elif char == "\\" and quote == '"':
                skip = True
        elif char == "\\":
            skip = True
        elif char in "'\"":
            quote = char
        elif char == "{" and word[at - 1:at] != "$":
            if depth == 0:
                start, cuts = at, []
            depth += 1
        elif char == "," and depth == 1:
            cuts.append(at)
        elif char == "}" and depth:
            depth -= 1
            if depth == 0 and cuts:
                bounds = [start] + cuts + [at]
                return (word[:start], [word[bounds[i] + 1:bounds[i + 1]] for i in range(len(bounds) - 1)],
                        word[at + 1:])
    return None


def _brace_words(word: str) -> list:
    """The words a shell makes of `word` by brace expansion (`hooks/{a,b}.py` gives `hooks/a.py` and
    `hooks/b.py`), else `[word]`. Stops at `_BRACE_LIMIT` words.
    ponytail: a sequence (`{1..3}`) is not expanded, and a word past the limit is cut short."""
    split = _brace_split(word)
    if split is None:
        return [word]
    head, parts, tail = split
    out = []
    for part in parts:
        for rest in _brace_words(part + tail):
            out.append(head + rest)
            if len(out) >= _BRACE_LIMIT:
                return out
    return out


def _from_cwd(word, at, cwd):
    """`word` as a path from `cwd` when the segment ran in a folder `at` that a `cd` moved to, so the
    matched path a refusal logs names its test folder (`tests/test_a.py`, not `./test_a.py`)."""
    if at == cwd or not cwd or os.path.isabs(word) or word.startswith(("~", "$")):
        return word
    full = os.path.normpath(os.path.join(at, word))
    inside = os.path.normpath(cwd)
    return os.path.relpath(full, inside).replace(os.sep, "/") if full.startswith(inside + os.sep) else full


_SED_TAKES_VALUE = "efl"   # the sed short flags that take a value: a script, a script file, a width


def _sed_past(script, at, delimiter, parts):
    """The index after `parts` closing `delimiter`s in `script` from `at`; a backslash escapes the next
    character. The regex and the replacement of `s` are two parts, the sets of `y` are two."""
    while at < len(script) and parts:
        if script[at] == "\\":
            at += 1
        elif script[at] == delimiter:
            parts -= 1
        at += 1
    return at


def _sed_script_targets(script):
    """(files, commands): what one sed script word names for writing or running. Files: the rest of the
    line after a `w` or `W` command, and after the `w` flag of `s`. Commands: the rest of the line after
    an `e` command, a shell command judged as one. Every other word of a script is text. Walks the script
    as sed reads it: an address (`3`, `$`, `/re/`, a regex in other delimiters) is skipped, so are the
    regex and replacement of `s` and the sets of `y`. The file of `r` and `R` runs to the line's end. The
    text of `a`, `i` and `c` runs to the end of the first line that does not end in a backslash, so
    `1a\\` and its next line are one text. A label (`:`, `b`, `t`, `T`) ends at `;` or the line's end."""
    targets, commands, at, size = [], [], 0, len(script)

    def line_end(start):
        end = script.find("\n", start)
        return size if end < 0 else end

    def text_end(start):
        # the text of `a`, `i` or `c` goes on past each line end that an odd run of backslashes escapes
        end = line_end(start)
        while end < size:
            back = end
            while back > start and script[back - 1] == "\\":
                back -= 1
            if (end - back) % 2 == 0:
                break
            end = line_end(end + 1)
        return end

    def label_end(start):
        # a label (`:`, `b`, `t`, `T`) ends at `;` or the line's end, whichever comes first
        end = start
        while end < size and script[end] not in ";\n":
            end += 1
        return end

    while at < size:
        char = script[at]
        if char in " \t\n;{}!0123456789$,~+IM":
            at += 1
        elif char == "#":
            at = line_end(at)
        elif char in "/\\":
            delimiter = script[at + 1:at + 2] if char == "\\" else char
            at = _sed_past(script, at + (2 if char == "\\" else 1), delimiter, 1)
        elif char in "wWe":
            end = line_end(at + 1)
            target = script[at + 1:end].strip()
            if target:
                (commands if char == "e" else targets).append(target)   # `e` runs a shell command
            at = end
        elif char in "sy":
            delimiter = script[at + 1:at + 2]
            if not delimiter or delimiter in "\n\\":
                break
            at = _sed_past(script, at + 2, delimiter, 2)
            while char == "s" and at < size and script[at] not in ";\n}":
                if script[at] == "w":
                    end = line_end(at + 1)
                    target = script[at + 1:end].strip()
                    if target:
                        targets.append(target)
                    at = end
                    break
                at += 1
        elif char in "aic":
            at = text_end(at + 1)
        elif char in "rR":
            at = line_end(at)
        elif char in ":btT":
            at = label_end(at)
        else:
            at += 1
    return targets, commands


def _commands_run(raw):
    """The command name that runs in one segment's `raw` words, after any `sudo`, `env` or `xargs`
    (`_segment_command`), as a set. None when a quoted word holds a space: it may be a script the shell runs
    (`sh -c 'sed -i s/a/b/ P'`, or JSON piped to an interpreter), so no command name is read from the segment."""
    if any(word[:1] in ("'", '"') and re.search(r"\s", _unquoted(word)) for word in raw):
        return None
    return {_segment_command([_unquoted(word) for word in raw])[0]}


def _perl_script_words(raw):
    """The indexes of the words of a `perl` segment that are a `-e` or `-E` script holding an in-place flag
    spelling (a word of it, as `_words_of` splits it): text, not a flag. `-pe` ends in `e`, so its next word is
    its script; `-ie` is an in-place flag with the suffix `e`, so its next word is not."""
    command, _rest = _segment_command([_unquoted(word) for word in raw])
    if command != "perl":
        return set()
    return {at for at in range(1, len(raw))
            if re.fullmatch(r"-[0-9aCcFlnpsStTuUvwW]*[eE]", _unquoted(raw[at - 1]))
            and any(re.match(_PERL_IN_PLACE_FLAG, piece) for piece in _words_of(raw[at]))}


def _sed_command_words(command):
    """The words of a sed `e` command that count as written: none when each command in it only reads
    (`_command_reads`: a printer or a read-only tool), else every word, since a printer can feed a writer (`e echo tests/x | xargs rm`). So
    `e cat tests/x` reads and `e touch tests/x` writes. A lone `&` ends a command as `;` does
    (`_split_background`), so `e head a & tee tests/x` writes. The file an output flag names (`sort -otests/x`)
    counts as written beside the words (`_output_targets`). A command with text the segment split cannot see
    (`_SCRIPT_RUNS_HIDDEN`) counts every word. Its redirects are read apart, by the shell scan of the
    whole command (`_shell_write_scan`)."""
    commands = [[_unquoted(word) for word in _quoted_words(part, True)]
                for segment in split_segments(command) for part in _split_background(segment)]
    if not _SCRIPT_RUNS_HIDDEN.search(command):
        if all(_command_reads(*_segment_command(words)) for words in commands if words):
            return []
    return [*command.split(), *(target for words in commands for target in _output_targets(words))]


def _sed_script_words(raw):
    """{index: (files, commands)} for the words of a `sed` segment that are not files it writes: its
    script (the first operand, or the value of each `-e` and `--expression`) and the value of `-f`,
    `--file` and `-l`. A script is text, so `s/N/tests\\/a.py/` names no test. `files` and `commands`
    are what the script's `w`, `W`, `s///w` and `e` name (`_sed_script_targets`): `sed -i 'w tests/a.py'
    src/app.py` and `sed -n 'w tests/a.py' src/x.py` both write tests/a.py, since `w` writes with or
    without an in-place option. A redirect and its target are no sed words, wherever they stand
    (`sed > out p src`), as in `_roots`. A value flag with no word after it has no value. Empty when the
    segment is no sed."""
    index = resolve_command(tuple(raw))
    if index is None or _name(raw[index]) not in _SED_NAMES:
        return {}
    places, target = [], False
    for at in range(index + 1, len(raw)):
        if target:
            target = False
        elif (">" in raw[at] or "<" in raw[at]) and _is_redirect(raw[at]):
            target = True
        elif raw[at] != "&":   # the `&` of `&>`, as in `_roots`
            places.append(at)
    skip, scripts, scripted, operands, flags_over = set(), {}, False, [], False
    step = 0
    while step < len(places):
        at = places[step]
        after = places[step + 1] if step + 1 < len(places) else None
        word = _unquoted(raw[at])
        if flags_over or not word.startswith("-") or word == "-":
            operands.append(at)
        elif word == "--":
            flags_over = True
        elif word.startswith("--"):
            flag, glued, value = word.partition("=")
            if flag in ("--expression", "--file", "--line-length"):
                scripted = scripted or flag != "--line-length"
                where = at if glued else after
                if where is not None:
                    skip.add(where)
                    if flag == "--expression":
                        scripts[where] = value if glued else _unquoted(raw[where])
                step += 0 if glued else 1
        else:
            for place, letter in enumerate(word[1:], 1):
                if letter == "i":
                    break   # the rest of the cluster is the backup suffix
                if letter in _SED_TAKES_VALUE:
                    scripted = scripted or letter != "l"
                    glued = place < len(word) - 1
                    where = at if glued else after
                    if where is not None:
                        skip.add(where)
                        if letter == "e":
                            scripts[where] = word[place + 1:] if glued else _unquoted(raw[where])
                    step += 0 if glued else 1
                    break
        step += 1
    if not scripted and operands:
        skip.add(operands[0])
        scripts[operands[0]] = _unquoted(raw[operands[0]])
    return {where: _sed_script_targets(scripts.get(where, "")) for where in skip}


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
