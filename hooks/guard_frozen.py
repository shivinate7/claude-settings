"""The guard's frozen family: a write to the settings, the hooks or the global CLAUDE.md.

guard.py is the only entry point, and it runs these checks in its fixed order (decision
guard-split-by-family). Other files reach these names through `guard`.
"""
import os
import re

import guard_core
from guard_core import (
    REDIRECT, _drop_heredoc_bodies, _expanded, _resolved, norm, split_segments,
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
    # deletes things, same reasoning as hooks/lint/agents, so it lands here too (plan:
    # janitor-build-plan.md, "The code lands in a new janitor/ directory").
    os.path.normcase("janitor"),
    # bin/ holds the merge shim that every merge runs. Same reasoning as janitor.
    os.path.normcase("bin"),
    # output-styles/ holds the rules for the main session's replies. A session that could rewrite
    # its own style could loosen those rules, same reasoning as agents/.
    os.path.normcase("output-styles"),
    # ux/ holds the house rules builders and reviewers read (decision ux-house-rules). A session
    # that could rewrite them could loosen its own review bar, same reasoning as output-styles/.
    os.path.normcase("ux"),
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
    os.path.normcase("impeccable"),
)
PROJECT_FROZEN_FILES = ("/.claude/settings.json", "/.claude/settings.local.json")
PROJECT_FROZEN_DIR = "/.claude/hooks/"

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


def is_frozen(path: str, cwd: str) -> bool:
    """True when the path is part of the harness configuration under the config directory.

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
    for target, root in ((literal, literal_root), (resolved, resolved_root)):
        if not target.startswith(root + os.sep):
            continue
        parts = target[len(root) + 1:].split(os.sep)
        if len(parts) == 1 and parts[0] in CONFIG_FROZEN_FILES:
            return True
        if len(parts) > 1 and parts[0] in CONFIG_FROZEN_DIRS:
            return True
        if len(parts) > 1 and parts[0] == os.path.normcase("skills") and parts[1] in CONFIG_FROZEN_SKILLS:
            return True
    return False


def is_project_config(path: str, cwd: str) -> bool:
    """True when the path is a project's own `.claude/settings*.json` or `.claude/hooks/*`.

    Decision 7: allowed in any checkout, never denied. The caller logs the edit as `noted` under
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


# Commands that change a file named in their arguments. `cp` and `mv` stay on the list even when the
# frozen path is their source rather than their target, because guessing wrong on `mv` loses the
# file. Deliberate over-blocking, narrow in scope.
#
# MEASURED in q_max on 2026-09-09 with a POSIX-only list: `Set-Content`, `Out-File`, `Add-Content`
# and `Remove-Item` each wrote a frozen path unrefused. Matching folds case, as PowerShell does.
MUTATING_COMMAND = (
    r"\b(?i:rm|mv|cp|chmod|truncate|tee|install|ln"
    r"|set-content|add-content|clear-content|out-file|new-item|remove-item|move-item|copy-item"
    r"|rename-item|set-itemproperty|ri|rd|rmdir|del|erase|move|copy|ren)\b"
)


def writes_to(path: str, cmd: str) -> bool:
    """True when the command looks like it writes to the path, rather than merely naming it.

    Two ways to write a named file from a shell: redirect onto it, or hand it to a command that
    mutates its arguments. Everything else is a mention.

    MEASURED in q_max on 2026-08-20: reading the TARGET of the redirect is what separates
    `echo x > .claude/settings.json` from `cat .claude/settings.json 2>/dev/null`. The second
    redirects to the null device. It is also what stops a redirect elsewhere on the line from
    counting as a write to a path named in a comment.
    """
    target = re.escape(path)
    if re.search(r"\d?>>?\s*['\"]?" + target, cmd):
        return True
    if re.search(MUTATING_COMMAND + r"[^\n;|&]*" + target, cmd):
        return True
    if re.search(r"\bsed\b[^\n;|&]*-i\b[^\n;|&]*" + target, cmd):
        return True
    return False


# VARIABLE INDIRECTION. Incident 2026-10-07, q_max session 56ca874f:
# `D=~/.claude/state/handoff/x.md; ...; cp "$S/handoff.md" "$D"` was allowed, because the parse saw
# only the word `$D`. One left-to-right pass in `_shell_write_hit` (it feeds the frozen and
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


# DATA IS NOT A WRITE. Incident 2026-10-14: a reviewer's probe piped a JSON sample that held a cap
# write into `python hooks/guard.py`, and the owner was asked to approve a call that wrote nothing.
# A quoted string that holds a space or an operator, and a heredoc body fed to a program that is not a
# shell, are text for that program: no redirect or `tee` inside them runs. Two cases keep the text
# in view. A shell reads it (`bash -c "..."`, `echo "..." | sh`, `eval`, `iex`, `pwsh -c`, a heredoc
# fed to `sh`: any segment of the command that names a shell), and a double-quoted string holds `$(`
# or a backtick, which the shell runs.
# RESIDUAL GAP: a program that writes from its own code (`python -c`, a python heredoc) is not seen
# here; debt cap-write-by-python-unseen.
_SHELL_RUNNERS = frozenset((
    "bash", "sh", "zsh", "dash", "ksh", "eval", "pwsh", "powershell", "cmd", "wsl", "su",
    "iex", "invoke-expression"))
_SHELL_HEREDOC = re.compile(r"\b(?:bash|sh|zsh|dash|ksh)\b[^\n]*<<")
_DATA_WORD = re.compile(r"[\s<>|;&]")


def _text_words(word: str, shell_runs_it: bool):
    """The words a segment's quoted word stands for: itself when it is no text, one blank when it is
    data, else the words inside it (a shell runs them: it reads the quote as code)."""
    if word[:1] not in ("'", '"') or not _DATA_WORD.search(word):
        return [word]
    if shell_runs_it or (word[0] == '"' and ("$(" in word or "`" in word)):
        return REDIRECT.sub(r" \1 ", word).split()
    return ['""']


def _runs_text(words) -> bool:
    """True when a command word is a shell, so a quoted argument or piped text is code."""
    for word in words:
        if word[:1] not in ("'", '"'):
            name = word.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
            if name.removesuffix(".exe") in _SHELL_RUNNERS:
                return True
    return False


def _shell_write_hit(cmd: str, cwd: str, predicate) -> str:
    """Return the path a shell command writes to that `predicate(path, cwd)` accepts, else ''."""
    cmd = _resolve_vars(cmd)
    if not _SHELL_HEREDOC.search(cmd):
        cmd = _drop_heredoc_bodies(cmd)
    segments = [(seg, _quoted_words(seg)) for seg in split_segments(cmd) if seg.strip()]
    shell_runs_it = any(_runs_text(words) for _, words in segments)   # `echo "..." | sh` too
    for segment, words in segments:
        words = [part for word in words for part in _text_words(word, shell_runs_it)]
        text = " ".join(words)
        for word in words:
            if word.startswith("-") or REDIRECT.fullmatch(word):
                continue
            bare = word.strip("'\"")
            if not bare or bare in (">", ">>"):
                continue
            if predicate(bare, cwd) and writes_to(word, text):
                return bare
    return ""


def frozen_shell_hit(cmd: str, cwd: str) -> str:
    """Return the frozen (config-dir) path a shell command writes to, else ''."""
    return _shell_write_hit(cmd, cwd, is_frozen)


def project_config_shell_hit(cmd: str, cwd: str) -> str:
    """Return the project config path a shell command writes to, else ''."""
    return _shell_write_hit(cmd, cwd, is_project_config)

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
