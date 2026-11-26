"""The guard's write family: a git write whose own output is silenced.

guard.py is the only entry point, and it calls these checks in its fixed order. The silent-write
rule refuses a discarding redirect, a pipe stage that drops lines, or a quiet flag on a git write
(commit, push, merge, tag, rebase, cherry-pick, pull) or on a `make merge` or `gh pr merge`.
Other files reach these names through `guard`.
"""
import re

from guard_core import (
    SILENT_WRITE_REDIRECT, basename, git_calls, is_powershell, resolve_command, segment_tokens, walk_quotes,
)
from guard_env import _substitutions


# ------------------------------------------------------------------ the silent write
#
# Rule 1c. CLAUDE.md (Git): "Never discard a command's output." A discarding REDIRECT is refused on
# every one of these six subcommands, whatever the subcommand does with its own output: the shell
# throws the stream away before git ever gets a say, so a hook's refusal and git's own proof of
# landing are both gone, together, always.
SILENT_WRITE_SUBCOMMANDS = ("commit", "push", "merge", "tag", "rebase", "cherry-pick", "pull")

# Gap roster. Each one moves a ref or lands a merge, so each is a write when its
# output is silenced: `pull` (a fetch plus a merge; its `-q` joins the quiet arm), a `fetch` that
# names a `src:dst` refspec (it moves a local ref; a bare `fetch` stays a read), `make merge`,
# `gh pr merge`, and a closed descriptor (`2>&-`, `>&-`), which silences like /dev/null.
# A pipe stage after the write that drops lines by pattern (`stage_drops_lines`) hides what the write
# printed the same way, so it counts too, whether or not it is the last stage. `tail` and `head` keep
# the lines they print, so they stay allowed.
# `--dry-run` moves nothing and stays allowed. Output sent to a FILE stays allowed: the owner held
# that until measured.

# git's OWN `-q`/`--quiet` flag is a narrower statement, and it does not read the same for every
# subcommand. MEASURED 2026-09-19 and 2026-09-20, in throwaway repos under this session's
# scratchpad, never in a shared checkout, `-q`/`--quiet` alone, no redirect, three states each: a
# write that succeeds, one a hook refuses (a `pre-commit`/`pre-receive` hook, or the conflict
# `merge`, `rebase`, and `cherry-pick` raise on their own), and a no-op (nothing staged or to
# push, an already-merged branch, nothing left to replay, a change already present).
#
#   git commit -q       success        exit 0, stdout '',                stderr ''
#                        hook refusal   exit 1, stdout '',                stderr the hook's own line
#                        no-op          exit 1, stdout "nothing to        stderr ''
#                                                commit ...",
#
#   git push --quiet    success        exit 0, stdout '',                stderr ''
#                        hook refusal   exit 1, stdout '',                stderr the full rejection
#                        no-op          exit 0, stdout '',                stderr ''
#
#   git merge -q         success        exit 0, stdout '',                stderr ''
#                        conflict       exit 1, stdout the full           stderr ''
#                                                CONFLICT message,
#                        no-op          exit 0, stdout '',                stderr ''
#
#   git rebase -q       success        exit 0, stdout '',                stderr ''
#                        conflict       exit 1, stdout the CONFLICT       stderr the apply error
#                                                message,                 and its hints,
#                        no-op          exit 0, stdout '',                stderr ''
#
#   git tag -q          every state    exit 129, stdout '',              stderr "error: unknown
#                                                                                switch `q'" plus
#                                                                                the full usage
#
#   git cherry-pick -q  every state    exit 129, stdout '',              stderr the full usage
#                                                                                ("-q" is not a
#                                                                                cherry-pick option)
#   git cherry-pick
#     --quiet            success        exit 0, stdout the full commit    stderr ''
#                                                summary line,
#                        conflict       exit 1, stdout the CONFLICT       stderr the apply error
#                                                message,                 and its hints,
#                        no-op          exit 1, stdout "nothing to        stderr "previous
#                                                commit ...",              cherry-pick is now
#                                                                          empty" and its hint
#
# `commit -q` hides nothing a session could not already read: a refusal keeps its own message on
# stderr, a no-op keeps its own message on stdout, and both keep a nonzero exit code, so silence
# at exit 0 is unambiguous proof of a landed commit. `commit` drops out of the quiet-flag arm.
#
# `push -q` and `merge -q` and `rebase -q` measure the same way as each other, and differently
# from `commit`. Each one's own refusal (a hook, or a real conflict) stays fully readable. But
# each one's success and its own no-op are BOTH silent and BOTH exit 0 (without `-q` they already
# differ: `push` prints "Everything up-to-date" against the `sha..sha  branch -> branch` summary,
# `merge` and `rebase` print their own "up to date"/"nothing to replay" line against a diffstat or
# a "Successfully rebased" line). `-q` erases the one line that told a real write from a no-op, so
# a session cannot read whether the write it just ran moved anything. All three keep the
# quiet-flag arm on this measurement, not on the flag's name.
#
# `tag` has NO `-q` and NO `--quiet` at all (git 2.39.3): both spellings exit 129 with "error:
# unknown switch" before git reads the tag name, the message, or the repository state. Every
# state measures identically, because the flag never gets past option parsing. `tag` therefore
# cannot use `-q`/`--quiet` to hide a success from a no-op or a refusal: the attempt is always a
# loud, immediate failure. `tag` drops out of the quiet-flag arm.
#
# `cherry-pick`'s short form, `-q`, is ALSO not a valid option (exit 129, the same shape as
# `tag`). Its long form, `--quiet`, IS valid, and measures as the least silent of the six: a
# success still prints the full one-line commit summary to stdout, a conflict prints its own
# CONFLICT message and hints in full, and a no-op (an already-applied change) prints "nothing to
# commit" and "previous cherry-pick is now empty" in full, at its own distinct nonzero exit. No
# state is silent, so nothing is lost by allowing either spelling. `cherry-pick` drops out of the
# quiet-flag arm.
QUIET_FLAG_SUBCOMMANDS = ("push", "merge", "rebase", "pull", "fetch")


def unquoted_at(text: str, index: int) -> bool:
    """True when `index` in `text` sits outside every quote, read off guard_core's quote walk (the
    one `split_segments` cuts with: an escaped quote, a `$'...'` string and a PowerShell backtick
    included). An unterminated quote runs to the end."""
    for at, _, quote in walk_quotes(text):
        if at >= index:
            return not quote
    return True


def discards_output(segment: str) -> bool:
    """True when the segment redirects stdout or stderr, on any descriptor, to a null device. A
    redirect named inside a quoted string (a commit message, an echo) is text, never a redirect.

    The walk reads a quote inside `$( )` or backticks as the outer string's own, so
    `-m "$(printf '"')" >/dev/null` hides the redirect. Each substitution is cut out first
    (`_substitutions`, the env layer's cut) and the text around it is read again. Too deep to cut
    is a redirect: this fails closed. ponytail: a bandaid; the cause, the quote walk's reading of
    a quote inside `$( )`, stays."""
    if any(unquoted_at(segment, m.start()) for m in SILENT_WRITE_REDIRECT.finditer(segment)):
        return True
    if "$(" not in segment and "`" not in segment or not SILENT_WRITE_REDIRECT.search(segment):
        return False
    texts, too_deep = _substitutions(segment, powershell=is_powershell(segment))
    if too_deep:
        return True
    outer = type(segment)(texts[-1][0])
    return any(unquoted_at(outer, m.start()) for m in SILENT_WRITE_REDIRECT.finditer(outer))


# A write whose output feeds a pipe is judged by that pipe's tail: silenced by a redirect, or a
# `grep -q`, which prints nothing by itself, or dropped by a filter that deletes lines by pattern
# (`stage_drops_lines`, any stage after the write). A printing tail (`| tail -5`, `| tee f`) is not.
# `bash -c '...'` stays unparsed, a known gap the owner left. A filter inside a script file the
# tail runs is out of reach.
def tail_discards(tail: str) -> bool:
    """True when a pipe's last segment prints nothing the session can read."""
    tail = tail.strip().lstrip("&").strip()   # `|&` leaves a leading `&`
    if discards_output(tail):
        return True
    tokens = segment_tokens(tail) or []
    index = resolve_command(tokens) if tokens else None
    return (index is not None and basename(tokens[index]) == "grep"
            and any(t in ("-q", "--quiet", "--silent") for t in tokens[index + 1:]))


# `grep` flags that take a value, as a separate word or as the rest of a short cluster.
GREP_VALUE_FLAGS = set("efmABCd")
GREP_LONG_VALUE_FLAGS = {"--regexp", "--file", "--max-count", "--after-context", "--before-context",
                         "--context", "--directories", "--include", "--exclude", "--exclude-dir",
                         "--label", "--binary-files", "--devices"}


def grep_inverts(args) -> bool:
    """True when a grep's argv carries an invert flag in any spelling: `-v`, a short cluster with
    `v` ahead of any value letter (`-vE`, `-Ev`), or `--invert-match` (or a prefix of it GNU grep
    still reads). A word read as a flag's value (`-e -v`) or after `--` is a pattern, never a flag."""
    skip = False
    for token in args:
        if skip:
            skip = False
        elif token == "--":
            return False
        elif token.startswith("--"):
            name = token.partition("=")[0]
            if len(name) > 3 and "--invert-match".startswith(name):
                return True
            if name in GREP_LONG_VALUE_FLAGS and "=" not in token:
                skip = True
        elif token.startswith("-") and len(token) > 1:
            for at, letter in enumerate(token[1:], 1):
                if letter == "v":
                    return True
                if letter in GREP_VALUE_FLAGS:
                    skip = at == len(token) - 1
                    break
    return False


SED_VALUE_FLAGS = set("efl")   # `-e script`, `-f file`, `-l N`: a letter that takes a value


def sed_scripts(args):
    """The inline sed scripts of an argv: each `-e` / `--expression` value, else the first plain
    word. A `-f file` script is not read (the file is out of reach), so it adds none."""
    scripts, plain, skip = [], [], None
    explicit = False
    for token in args:
        if skip:
            if skip == "e":
                scripts.append(token)
            skip = None
        elif token == "--":
            continue
        elif token.startswith("--"):
            name, eq, value = token.partition("=")
            if name == "--expression":
                explicit = True
                if eq:
                    scripts.append(value)
                else:
                    skip = "e"
            elif name == "--file":
                explicit = True
                skip = None if eq else "f"
        elif token.startswith("-") and len(token) > 1:
            for at, letter in enumerate(token[1:], 1):
                if letter in SED_VALUE_FLAGS:
                    explicit = explicit or letter != "l"
                    rest = token[at + 1:]
                    if rest:
                        if letter == "e":
                            scripts.append(rest)
                    else:
                        skip = letter
                    break
        else:
            plain.append(token)
    return scripts if explicit else plain[:1]


def sed_deletes(script: str) -> bool:
    """True when a sed script holds a delete command (`d`): `/re/d`, `5d`, `$d`, `/a/,/b/d`,
    `/x/{d}`. Read statement by statement, so a `d` inside a regex, an `s` replacement or the text
    of an `a`/`i`/`c` command is text, never a delete."""
    at, end = 0, len(script)

    def delimited(i, delimiter):
        """Index after a delimiter-closed section that starts at i, honouring a backslash."""
        while i < end and script[i] != delimiter:
            i += 2 if script[i] == "\\" else 1
        return i + 1

    while at < end:
        while at < end and script[at] in " \t\n;{}":
            at += 1
        # Addresses: a number, `$`, `first~step`, `/re/` or `\cREc`, joined by `,`, then `!`.
        while at < end:
            if script[at] == "/":
                at = delimited(at + 1, "/")
            elif script[at] == "\\" and at + 1 < end:
                at = delimited(at + 2, script[at + 1])
            elif script[at].isdigit() or script[at] in "$~+":
                at += 1
            else:
                break
            while at < end and script[at] in "IM":
                at += 1
            if at < end and script[at] == ",":
                at += 1
            else:
                break
        while at < end and script[at] in " \t!":
            at += 1
        if at >= end:
            return False
        command = script[at]
        at += 1
        if command in "dD":
            return True
        if command == "{":
            continue
        if command in "sy" and at < end:
            delimiter = script[at]
            at = delimited(delimited(at + 1, delimiter), delimiter)
        # Everything else runs to the next `;`, newline or `}`, except the text commands, which
        # run to the end of the line.
        if command in "aicrRwW":
            while at < end and script[at] != "\n":
                at += 1
        else:
            while at < end and script[at] not in ";\n}":
                at += 1
    return False


def stage_drops_lines(tail: str) -> bool:
    """True when a pipe stage drops lines by pattern: `grep`, `egrep` or `fgrep` with an invert flag,
    or a `sed` whose inline script holds a delete. `tail`, `head` and a plain `grep` print what they
    keep, so they pass. `--color` and `--colour` take a value only after `=`, so `grep --color -v`
    still inverts."""
    tail = tail.strip().lstrip("&").strip()
    tokens = segment_tokens(tail) or []
    index = resolve_command(tokens) if tokens else None
    if index is None:
        return False
    word, args = basename(tokens[index]), tokens[index + 1:]
    if word in ("grep", "egrep", "fgrep"):
        return grep_inverts(args)
    if word == "sed":
        return any(sed_deletes(script) for script in sed_scripts(args))
    return False


def quiet_write(args) -> bool:
    """True when a git call carries `-q` or `--quiet`."""
    return "-q" in args or "--quiet" in args


# A flag that takes the NEXT token as its value. Such a value is text, never a flag: `commit -m -h`
# and `commit -m "--dry-run"` are real commits. A miss here only keeps a deny, never lifts one.
VALUE_FLAGS = {"-m", "--message", "-F", "--file", "-c", "-C", "--reuse-message", "--reedit-message",
               "--author", "--date", "--fixup", "--squash", "-t", "--template", "--cleanup",
               "--trailer", "-o", "--push-option", "-X", "--onto", "--repo", "--strategy",
               "--strategy-option", "--exec", "--pathspec-from-file", "--receive-pack"}
# A letter whose value depends on the subcommand: `-s` is a merge's strategy but a commit's
# sign-off, `-x` a rebase's command but a cherry-pick's note, `-u` a tag's key but a push's upstream.
SUBCOMMAND_VALUE_FLAGS = {"merge": {"-s"}, "pull": {"-s"}, "rebase": {"-s", "-x"}, "tag": {"-u"}}


def takes_next(subcommand: str, token: str) -> bool:
    """True when `token` takes the next token as its value. In a short cluster the first value
    letter takes the rest of the cluster (`-mfoo`), or the next token when it is last (`-am`)."""
    flags = VALUE_FLAGS | SUBCOMMAND_VALUE_FLAGS.get(subcommand, set())
    if token in flags:
        return True
    if token[:1] != "-" or token[1:2] in ("-", ""):
        return False
    letters = {flag[1] for flag in flags if len(flag) == 2}
    for at, letter in enumerate(token[1:], 1):
        if letter in letters:
            return at == len(token) - 1
    return False
LISTING = re.compile(r"-[ln]+\d*")   # `tag -l`, `-n5`, `-ln1`
FETCH_VALUE_FLAGS = {"--depth", "-j", "--jobs", "--upload-pack", "--refmap", "-o", "--server-option",
                     "--deepen", "--shallow-since", "--shallow-exclude"}


def read_verb(subcommand: str, args) -> bool:
    """True when the call's own argv names a read: help, a dry run, a tag listing, a dry-run
    push. Argv tokens only, never the value of `-m` or `-F`, and nothing after `--`."""
    skip = False
    for token in args:
        if skip:
            skip = False
        elif token == "--":
            return False
        elif token in ("--help", "-h", "--dry-run") or (subcommand == "push" and token == "-n") or (
                subcommand == "tag" and (token == "--list" or LISTING.fullmatch(token))):
            return True
        elif takes_next(subcommand, token):
            skip = True
    return False


def fetch_moves_branch(args) -> bool:
    """True when a fetch's refspec writes a local branch: a `src:dst` whose dst is under
    refs/heads/ or refs/remotes/, or a short name (git resolves that to a branch). The first
    plain word is the repository, never a refspec."""
    plain, skip = [], False
    for token in args:
        if skip:
            skip = False
        elif token in FETCH_VALUE_FLAGS:
            skip = True
        elif not token.startswith("-"):
            plain.append(token)
    for spec in plain[1:]:
        dst = spec.lstrip("+").partition(":")[2]
        if dst and (not dst.startswith("refs/") or dst.startswith(("refs/heads/", "refs/remotes/"))):
            return True
    return False


def silent_write_hit(segment: str, tail: str = ""):
    """Return (matched text, mechanism, kind) for a write whose own trace is silenced, else
    ("", "", "").

    `mechanism` is `"redirect"`, `"filter"` (a pipe stage after the write that drops lines) or `"quiet"`, so the caller can print the reason that matches
    what actually fired; `kind` is the act's name (`push`, `commit`, `merge`). A redirect can hide
    a refusal AND a proof of landing on any of the subcommands, while the quiet flag is judged per
    subcommand against `QUIET_FLAG_SUBCOMMANDS`, the measured set. Only `SILENT_WRITE_SUBCOMMANDS`
    are judged at all. `fetch`, `rev-parse`, and every other read subcommand fall outside it,
    which is what keeps the test-by-exit-code shape `git rev-parse -q --verify <ref> >/dev/null
    2>&1` allowed. `merge --abort` is carved out inside the loop: it lands nothing, so it has no
    landing to prove. A call whose argv names a read (`read_verb`) is carved out the same way.
    `tail` is the pipe stage this segment feeds that judges it, if any: the first stage that drops lines,
    else the last (see `tail_discards`).
    """
    silenced = discards_output(segment) or (bool(tail) and tail_discards(tail))
    dropped = not silenced and bool(tail) and stage_drops_lines(tail)
    for subcommand, args in git_calls(segment):
        if subcommand == "fetch":
            # Only a fetch that moves a local branch (`src:dst`) is a write; a bare one is a read.
            if not fetch_moves_branch(args):
                continue
        elif subcommand not in SILENT_WRITE_SUBCOMMANDS:
            continue
        if subcommand == "merge" and "--abort" in args:
            continue
        if read_verb(subcommand, args):
            continue
        matched = ("git " + subcommand + " " + " ".join(args)).strip()
        if silenced:
            return matched, "redirect", subcommand
        if dropped:
            return matched, "filter", subcommand
        if subcommand in QUIET_FLAG_SUBCOMMANDS and quiet_write(args):
            return matched, "quiet", subcommand
    if silenced or dropped:
        mechanism = "redirect" if silenced else "filter"
        tokens = segment_tokens(segment)
        index = resolve_command(tokens) if tokens else None
        if index is not None:
            word, rest = basename(tokens[index]), tokens[index + 1:]
            if (word == "make" and "merge" in rest) or (
                    word in ("gh", "gh.exe") and rest[:2] == ["pr", "merge"]):
                return word + " " + " ".join(rest), mechanism, ("make merge" if word == "make" else "gh pr merge")
    return "", "", ""


SILENT_WRITE_REDIRECT_REASON = (
    "Rule (Git): command {command} of {total}, the {kind}: a redirect silences this write's own "
    "output (>/dev/null), so neither a refusal nor the line that proves it landed would reach "
    "the session. "
    "Remedy: run {program} again with its output kept, ending the line with `2>&1 | tail -1`, "
    "and read what it prints before you say it landed."
)
SILENT_WRITE_FILTER_REASON = (
    "Rule (Git): command {command} of {total}, the {kind}: a pipe stage after it drops lines "
    "(`grep -v` or a `sed` delete), so the line that says whether this write was refused or landed "
    "can vanish before it reaches the session. "
    "Remedy: run {program} again with its output kept, ending the line with `2>&1 | tail -1`, "
    "and read what it prints before you say it landed."
)
SILENT_WRITE_QUIET_REASON = (
    "Rule (Git): command {command} of {total}, the {kind}: its quiet flag (-q) drops the one line "
    "that told a real update apart from one that moved nothing, so the session cannot read "
    "which one just ran. "
    "Remedy: run {program} again without the quiet flag, ending the line with `2>&1 | tail -1`, "
    "and read what it prints before you say it landed."
)




# INSTALL_ID = "uninstalled"
