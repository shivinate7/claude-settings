"""The guard's stream family: a stream that never ends, a waiter loop, a background server with no end
note, a waiter loop over a pattern and two ported shell traps.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import os
import re
import shlex

from guard_core import (
    DURATION, PLAYWRIGHT_PS_SHELLS, PowerShellScript, _absolute, _pwsh_script, _segment_cd_move,
    _skip_assignments_and_keywords, backgrounding_amp, basename, bare_words, command_indexes, git_calls,
    inline_script, inner_commands, is_powershell, resolve_command, segment_tokens, split_segments,
    CD_UNKNOWN,
)
from guard_env import _substitutions


# ------------------------------------------------------------------ a stream that never ends
#
# Guard rule live-stream. A follow flag turns `tail` or `Get-Content` into a command that never
# exits on its own, so it outlives the turn and the agent that started it. A `tail` at any bare
# (unquoted) word counts, so a runner no reader names still shows it (bare_words). Quoted text, a
# commit message or a search command's pattern never matches. A script inside one quoted word
# (`sh -c`, `ssh`, `docker exec` and the like) is read as a nested command (inner_commands).
#
# The short-flag test reads the WHOLE TOKEN for an `f` or an `F`, the same shape as
# `clean_deletes_files` and `push_is_forced` above, so `-fn 20` and `-nf` both match a combined
# flag. `-F` is `tail`'s own retry-on-rotate form of follow, so it counts too.
LIVE_STREAM_TAIL_TOOL = "tail"
LIVE_STREAM_GETCONTENT_TOOLS = ("get-content", "gc")


def _follow_hit(token: str, args) -> str:
    """The matched text when the command `token` with arguments `args` follows a stream, else ''."""
    tool = basename(token)
    for arg in args:
        if tool == LIVE_STREAM_TAIL_TOOL:
            if arg == "--follow" or arg.startswith("--follow="):
                return token + " " + arg
            if arg.startswith("-") and not arg.startswith("--") and ("f" in arg or "F" in arg):
                return token + " " + arg
        elif tool in LIVE_STREAM_GETCONTENT_TOOLS and arg.lower() == "-wait":
            return token + " " + arg
    return ""


def live_stream_hit(segment: str) -> str:
    """Return the matched text when one segment follows a stream and never ends, else ''.

    A segment shlex cannot parse is read word by word, every word as a command word, so an
    unmatched quote elsewhere in the line does not hide a follow."""
    tokens = segment_tokens(segment)
    if tokens is None:
        words = segment.split()
        return next((h for i, w in enumerate(words) if (h := _follow_hit(w, words[i + 1:]))), "")
    for start in command_indexes(tokens):
        hit = _follow_hit(tokens[start], tokens[start + 1:])
        if hit:
            return hit
    words, bare = bare_words(segment)
    hit = next((h for i in sorted(bare) if (h := _follow_hit(words[i], words[i + 1:]))), "")
    if hit:
        return hit
    return next((h for text in inner_commands(tokens) for part in split_segments(text)
                 if (h := live_stream_hit(part))), "")


LIVE_STREAM_REASON = (
    "this command follows a stream and never ends on its own, so it outlives the turn "
    "and the agent that started it. "
    "Remedy: run the command in the foreground with a timeout, or in the background and "
    "wait for its completion notice. To wait on a pid, use `bin/wait-pid PID [--timeout SECS]`. "
    "To wait until a clock time, use `bin/wait-until TIME [--timeout SECS]`."
)


# A COMMAND THAT NARRATES WHILE IT WAITS, piped into `tail` or `head`. The merge tool waits minutes for
# a claim commit's checks and prints a line a minute. A pipe block-buffers that heartbeat and the
# filter keeps one end of it, so a working wait reads as a hang. The roster is NAMED, one entry per
# incident, because "does this command narrate for minutes" cannot be resolved from the system, and
# refusing every `| tail` is the cry-wolf guard (docs/decisions/guard-that-cries-wolf-is-spent.md). `tee`
# keeps every byte, so it is not refused. Only `--confirm` reaches the wait: a bare `merge <pr>` is a
# preview that returns in seconds, so piping it is allowed.
NARRATING_COMMANDS = ("merge", "merge.cmd")
NARRATING_SCRIPT_TAILS = ("merge/merge.py", "merge/launch.py")
TRUNCATING_FILTERS = ("tail", "head")
# The lone writer stage the check rule lets through: `tee`, `tee.exe`, `Tee-Object` and `Out-File`. No filter
# cuts what it keeps. `tee` and `Tee-Object -FilePath` print the whole stream and write it to a file the agent
# reads back. `Tee-Object -Variable` writes no file but prints the stream in full. `Out-File` prints nothing, so
# its file is the only copy of the stream, as with `> file`. Compared on `basename` with `.exe` stripped.
FILE_WRITER_STAGES = ("tee", "tee-object", "out-file")
SCRIPT_INTERPRETER = re.compile(r"(?:python[\d.]*w?|py)$")


def narrating_stage(segment: str) -> str:
    """The command word when one segment is a long, narrating `--confirm` run, else ''."""
    tokens = segment_tokens(segment)
    if not tokens or "--confirm" not in tokens:
        return ""
    index = resolve_command(tokens)
    if index is None:
        return ""
    return _roster_word(tokens, index)


# The interpreter flags that take the next word as their value, so `python -W ignore run.py` skips `ignore`.
INTERPRETER_VALUE_FLAGS = ("-W", "-X")


def _flag_module(tokens, at: int):
    """What the interpreter flag at `at` (`-m`, `-Im`, `-Wignore`, `-uc`) does with the rest of its word.
    Returns (module, next_at): module is the `-m` operand, "" for `-c` (code, no script), None for a flag
    that names neither. A value flag (-W, -X) takes the rest of its word, else the next word."""
    flag = tokens[at]
    if flag.startswith("--"):
        return None, at + 1
    for pos, char in enumerate(flag[1:], 1):
        rest = flag[pos + 1:]
        if char == "c":
            return "", at + 1
        if char == "m":
            if rest:
                return rest, at + 1
            return (tokens[at + 1] if at + 1 < len(tokens) else ""), at + 2
        if "-" + char in INTERPRETER_VALUE_FLAGS:
            return None, at + (1 if rest else 2)
    return None, at + 1


def _script_operand(tokens, index: int) -> str:
    """The script an interpreter at `index` runs: its first word that is no flag. `-m <module>` runs the
    module's file, so `-m lint.ste_lint` reads as `lint/ste_lint.py` and the roster and lint tails judge it as
    they judge the path. '' for `-c <code>`, which runs no script."""
    at = index + 1
    while at < len(tokens) and tokens[at].startswith("-"):
        module, at = _flag_module(tokens, at)
        if module is not None:
            return module.replace(".", "/") + ".py" if module else ""
    return _whole_word(tokens, at) if at < len(tokens) else ""


def _script_run(tokens, index: int) -> str:
    """The script the command at `index` runs, else ''. An interpreter runs its script operand
    (`_script_operand`). A `.py` command word is the script itself, which is how `uv run lint/x.py` runs
    it. The one reader of both spellings, for `_roster_word`, `check_stage` and `lint_stage`."""
    word = basename(tokens[index])
    script = _script_operand(tokens, index) if SCRIPT_INTERPRETER.match(word.removesuffix(".exe")) else ""
    if not script and word.endswith(".py"):
        script = tokens[index]
    return script


def _whole_word(tokens, at: int) -> str:
    """The word at `at`, joined across the tokens an unquoted substitution split. A `$(` or a backtick
    opens a substitution that reads as several tokens, so the word reads on to the token that closes it
    and the roster tail is judged on the joined word. A quoted substitution is one token and joins nothing."""
    word = tokens[at]
    depth = word.count("$(") - word.count(")")
    ticks = word.count("`") % 2
    while (depth > 0 or ticks) and at + 1 < len(tokens):
        at += 1
        word += " " + tokens[at]
        depth += tokens[at].count("$(") - tokens[at].count(")")
        ticks = (ticks + tokens[at].count("`")) % 2
    return word


def _roster_word(tokens, index: int, interpreter_only: bool = False) -> str:
    """The roster spelling the command at `index` runs (`merge`, `merge.cmd`, or a script run through
    a runner, `python merge.py`), else ''. The one reader of NARRATING_COMMANDS and
    NARRATING_SCRIPT_TAILS. A word carrying a script path counts, so `python3.11` and `uv run python`
    both match. `interpreter_only` keeps the word to an interpreter (SCRIPT_INTERPRETER) and the path
    to its script operand: the check rule needs it, so `grep -n x merge/merge.py` and
    `python3 -m pytest -k merge/merge.py` are no run of the script."""
    word = basename(tokens[index])
    if word in NARRATING_COMMANDS:
        return word
    if interpreter_only:
        script = _script_run(tokens, index)
        if script.replace("\\", "/").endswith(NARRATING_SCRIPT_TAILS):
            return word + " " + basename(script)
        return ""
    for token in tokens[index:]:
        if token.replace("\\", "/").endswith(NARRATING_SCRIPT_TAILS):
            return word + " " + basename(token)
    return ""


def narrated_tail_hit(stripped: str) -> str:
    """Return the matched text when a narrating stage is piped straight into `tail`/`head`."""
    ends = []
    segments = split_segments(stripped, ends)
    for index in range(len(segments) - 1):
        if ends[index] != "|":
            continue
        stage = narrating_stage(segments[index])
        if not stage:
            continue
        tokens = segment_tokens(segments[index + 1])
        if not tokens:
            continue
        at = resolve_command(tokens)
        if at is not None and basename(tokens[at]) in TRUNCATING_FILTERS:
            return stage + " | " + basename(tokens[at])
    return ""


NARRATED_TAIL_REASON = (
    "this command waits for minutes and prints a line as it goes, and a pipe into a filter "
    "that keeps one end of the stream hides that line until the end, so a working wait looks "
    "like a hang. "
    "Remedy: run the command with nothing after it and read its output as it arrives, or "
    "redirect to a file you read back afterwards, or use tee to keep a full copy."
)


# A CHECK piped into a filter (decision background-check-through-verdict). A filter after the run can cut
# or hide the one useful line, the verdict, so it can be lost or never read. `verdict <cmd>` keeps the whole
# log and prints the verdict itself. Only named checks count, one entry per incident, because refusing every
# `| tail` is the cry-wolf guard (docs/decisions/guard-that-cries-wolf-is-spent.md). The merge tool's verdict
# calls (`--lane-lint`, `--review-record`, `--release-check`) are refused in the foreground too. They count as
# `merge`, `merge.cmd`, or `merge/merge.py` or `merge/launch.py` run by `python`, a `python3.N`, `pythonw` or
# `py` (also as `-m merge.merge`), behind a wrapper or `uv run`. A call through `verdict` is verdict-pipe's,
# never read here. `merge --confirm` is narrated_tail_hit's, so it is left out here and never refused twice.
# `ci-job` is refused in the background only, and a job `&` is the background.
# Which filter counts depends on the check: `--lane-lint`, `--review-record` and `ci-job` reach every
# later stage but a lone file writer (FILE_WRITER_STAGES), and `--release-check` reaches `tail` and `head` only.
CHECK_COMMANDS = ("ci-job", "ci-job.cmd")
CHECK_FLAGS = ("--lane-lint", "--review-record", "--release-check")
ANY_FILTER_FLAGS = ("--lane-lint", "--review-record")
CHECK_SCRIPT_TAIL = "bin/ci-job"
# The `uv` and `uv run` flags that take the next word as their value (`uv run --help`, uv 0.11), so
# `uv run -w pytest python x.py` skips `pytest`. The global flags that sit before `run` are in this list too.
UV_VALUE_FLAGS = frozenset((
    "--allow-insecure-host", "--cache-dir", "--color", "--config-file", "--config-setting",
    "--config-settings-package", "--default-index", "--directory", "--env-file", "--exclude-newer",
    "--exclude-newer-package", "--extra", "--extra-index-url", "--find-links", "--fork-strategy",
    "--group", "--index", "--index-strategy", "--index-url", "--keyring-provider", "--link-mode",
    "--no-binary-package", "--no-build-isolation-package", "--no-build-package",
    "--no-editable-package", "--no-extra", "--no-group", "--no-sources-package", "--only-group",
    "--package", "--prerelease", "--project", "--python", "--python-platform",
    "--refresh-package", "--reinstall-package", "--resolution", "--upgrade-group",
    "--upgrade-package", "--with", "--with-editable", "--with-requirements",
    "-C", "-P", "-f", "-i", "-p", "-w",
))


def _skip_uv_run(tokens, index: int) -> int:
    """The index of the command `uv [flags] run [flags] ...` starts, read through `resolve_command`
    again, else `index`. `uv` is no entry of COMMAND_WRAPPERS: adding it would move every rule that
    reads the command word, and only the check rule needs it."""
    while index < len(tokens) and basename(tokens[index]) == "uv":
        run = index + 1
        while run < len(tokens) and tokens[run].startswith("-"):
            run += 2 if tokens[run] in UV_VALUE_FLAGS else 1
        if tokens[run:run + 1] != ["run"]:
            break
        start = run + 1
        while start < len(tokens) and tokens[start].startswith("-"):
            start += 2 if tokens[start] in UV_VALUE_FLAGS else 1
        at = resolve_command(tokens[start:])
        if at is None:
            break
        index = start + at
    return index


def _merge_flag(tokens, flag: str) -> bool:
    """True when a token is the merge tool's option `flag`, bare or as `flag=value`. The tool's parser takes no
    prefix of an option (allow_abbrev is off, decision merge-confirm-repo), so `--lane` runs no check and is
    no flag here."""
    return any(token == flag or token.startswith(flag + "=") for token in tokens)


def check_stage(segment: str, background: bool):
    """(command word, any_filter) when one segment runs a named check, else ("", False). `ci-job` counts
    only in the background. `any_filter` says every later stage but a lone file writer reaches the check, not
    `tail` and `head` alone."""
    tokens = segment_tokens(segment)
    if not tokens:
        return "", False
    index = resolve_command(tokens)
    if index is None:
        return "", False
    index = _skip_uv_run(tokens, index)
    if basename(tokens[index]) in CHECK_COMMANDS:
        return (basename(tokens[index]), True) if background else ("", False)
    if _script_run(tokens, index).replace("\\", "/").endswith(CHECK_SCRIPT_TAIL):
        return (CHECK_COMMANDS[0], True) if background else ("", False)
    if "--confirm" in tokens or not any(_merge_flag(tokens, flag) for flag in CHECK_FLAGS):
        return "", False
    return (_roster_word(tokens, index, interpreter_only=True),
            any(_merge_flag(tokens, flag) for flag in ANY_FILTER_FLAGS))


LINT_SCRIPT = re.compile(r"(?:^|/)lint/[^/]+\.py$")


def _enters_lint_dir(segment: str, in_lint: bool) -> bool:
    """Whether the working directory is `lint/` after `segment`, given `in_lint` before it. A `cd` to a
    path that ends in `lint` enters it; a `cd` anywhere else leaves it; any other segment keeps it. The
    move is read by `_segment_cd_move`, the one reader of `cd`, `pushd` and `Set-Location`."""
    tokens = segment_tokens(segment)
    move = _segment_cd_move(tokens) if tokens else None
    if move is None:
        return in_lint
    if move is CD_UNKNOWN or move == "-":
        return False
    return basename(move.replace("\\", "/").rstrip("/")) == "lint"


def lint_stage(segment: str, in_lint: bool = False):
    """("lint", True) when one segment runs a script under `lint/`, through an interpreter, as
    `-m lint.<name>`, or as the `.py` command word (`uv run lint/x.py`), else ("", False). With `in_lint`
    (an earlier `cd lint` in the same command), a script named by its basename is under `lint/` too
    (`./ste_lint.py`). Only a word that is itself a token counts: `-m pytest` reads as `pytest.py`, which is
    no word of the call, so it is no lint script. The second value is the any_filter flag of check_stage."""
    tokens = segment_tokens(segment)
    index = resolve_command(tokens) if tokens else None
    if index is None:
        return "", False
    index = _skip_uv_run(tokens, index)
    script = _script_run(tokens, index).replace("\\", "/")
    bare = script.removeprefix("./")
    if in_lint and "/" not in bare and script in [token.replace("\\", "/") for token in tokens]:
        script = "lint/" + bare
    return ("lint", True) if LINT_SCRIPT.search(script) else ("", False)


def _ends_in_ampersand(stages, first: int) -> bool:
    """Whether the pipeline is backgrounded by a `&` in the stage at `first` or a later one, spaced or
    glued to the last word (`backgrounding_amp`, the one reader detached-launch shares). split_segments
    leaves the `&` of `|&` at the head of the next stage; that one is a pipe, not a job, and
    `backgrounding_amp` reads it as none."""
    for segment in stages[first:]:
        tokens = segment_tokens(segment)
        if tokens and backgrounding_amp(segment, tokens):
            return True
    return False


def _list_ends_in_ampersand(segments, ends, after: int) -> bool:
    """Whether the `&&` or `||` list that a pipeline closes, which goes on from segment `after`, is
    ended by a job `&`: `ci-job x | tail && echo done & echo $!` backgrounds the whole list. The
    list runs on through `|`, `&&` and `||` and stops at `;` or a newline, or at the first `&`."""
    for segment, end in zip(segments[after:], ends[after:]):
        tokens = segment_tokens(segment)
        if tokens and backgrounding_amp(segment, tokens):
            return True
        if end not in ("|", "&&", "||"):
            return False
    return False


def _pipeline_hit(stages, background: bool, stage_of=check_stage, any_later: bool = False,
                  list_amp: bool = False) -> str:
    """The matched text when a stage that `stage_of(segment, backgrounded)` names, in one pipeline's
    stages, is followed by a filter that cuts what the agent reads. `backgrounded` is the call's
    `background`, a job `&` that ends the stage's list (`list_amp`), or a job `&` in this stage or a later
    one. The stage's any_filter widens the reach from `tail` and `head` to every later stage but a lone file
    writer (FILE_WRITER_STAGES), since `sed -n`, `grep -m1` and `awk` cut what the agent reads as `tail`
    does; a `tee` between the check and a filter does not end the reach. With `any_later`, any later command
    counts: a pipeline's exit is its last stage's, so `grep`, `tee` and `wc` mask the exit of the stage
    before them as `tail` does (the lint-then-commit gate reads the exit, not the cut)."""
    for first, segment in enumerate(stages):
        stage, any_filter = stage_of(segment, background or list_amp or _ends_in_ampersand(stages, first))
        if not stage:
            continue
        for later in stages[first + 1:]:
            tokens = segment_tokens(later)
            at = resolve_command(tokens) if tokens else None
            if at is None:
                continue
            word = basename(tokens[at])
            if any_later or word in TRUNCATING_FILTERS or (
                    any_filter and word.removesuffix(".exe") not in FILE_WRITER_STAGES):
                return stage + " | " + word
    return ""


def _commits_or_pushes(segment: str) -> bool:
    """True when one segment runs a commit or a push, read by the one reader of git calls."""
    return any(verb in ("commit", "push") for verb, _args in git_calls(segment))


def check_tail_hit(stripped: str, background: bool) -> str:
    """The matched text when a call pipes a named check into a filter that cuts what the agent reads (see
    `_pipeline_hit`), directly or through other filters. A pipeline ends at any separator other than `|`.
    A lint script piped into any later command counts only when a later pipeline of the call runs a commit
    or a push: the pipeline's exit is the last stage's, so a red lint hides, and the commit or push runs on
    it. A commit before the lint is no follow-up."""
    ends = []
    segments = split_segments(stripped, ends)
    pipelines, stages = [], []
    for number, (segment, end) in enumerate(zip(segments, ends)):
        stages.append(segment)
        if end != "|":
            list_amp = end in ("&&", "||") and _list_ends_in_ampersand(segments, ends, number + 1)
            hit = _pipeline_hit(stages, background, list_amp=list_amp)
            if hit:
                return hit
            pipelines.append(stages)
            stages = []
    hit = _pipeline_hit(stages, background)
    if hit:
        return hit
    pipelines.append(stages)
    in_lint = False
    for at, stages in enumerate(pipelines):
        hit = _pipeline_hit(stages, background,
                            lambda segment, bg: lint_stage(segment, in_lint), any_later=True)
        for segment in stages:
            in_lint = _enters_lint_dir(segment, in_lint)
        if hit and any(_commits_or_pushes(segment) for later in pipelines[at + 1:] for segment in later):
            return hit + " then a commit or push"
    return ""


CHECK_TAIL_REASON = (
    "this check's output goes into a filter after the run, and the filter can cut or hide the "
    "verdict line "
    "(decision background-check-through-verdict). "
    "Remedy: run the check through verdict, as `verdict <cmd>` with nothing after it. It keeps the "
    "full log and prints the verdict itself."
)


# A PIPE OUT OF `verdict`. A pipeline's exit is its last stage's, so `verdict CMD | tail` returns
# tail's exit and a red run reads 0. verdict prints its `FAIL ... rc=` line first, and a filter
# that keeps the end of the stream (or anything that selects lines) can cut it. Every command after
# the pipe counts, not only TRUNCATING_FILTERS: grep, tee and cat all return their own exit.
# `verdict` is a COMMAND_WRAPPERS entry, so `resolve_command` skips it and names the program it
# runs; the verdict word is read from the tokens up to that program (`timeout 600 verdict x`,
# `python bin/verdict x`, `VAR=1 verdict x`). A verdict that closes a segment on something other
# than `|` (`&&`, `;`, a redirect target, the last stage) has no pipe out of it.
VERDICT_WORDS = ("verdict", "verdict.cmd")


def _is_lookup(tokens) -> bool:
    """True for `command -v NAME` / `command -V NAME`: the shell names a program and runs none."""
    at = _skip_assignments_and_keywords(tokens)
    return (at < len(tokens) and basename(tokens[at]) == "command"
            and any(token in ("-v", "-V") for token in tokens[at + 1:]))


def _verdict_pipe_in(text: str) -> str:
    """One command text, no substitution left in it (they are read apart): the `verdict |` match, else ''."""
    ends = []
    segments = split_segments(text, ends)
    for index, segment in enumerate(segments):
        # A pipe at a line end (`verdict x |` then a newline) still pipes into the next line.
        if ends[index] != "|":
            continue
        tokens = segment_tokens(segment)
        if not tokens:
            continue
        at = resolve_command(tokens)
        if at is None and _is_lookup(tokens):
            continue
        # `uv` is no wrapper, so `uv run verdict x` names `uv`; _skip_uv_run reads on to the program.
        reach = tokens if at is None else tokens[:_skip_uv_run(tokens, at) + 1]
        if any(basename(token.lstrip("(")) in VERDICT_WORDS for token in reach):
            return "verdict |"
    # A shell's script (`bash -c '...'`) is its own command text, read the way the live-stream rule reads it.
    for segment in segments:
        tokens = segment_tokens(segment)
        hit = tokens and next((h for inner in inner_commands(tokens)
                               if (h := verdict_pipe_hit(inner))), "")
        if hit:
            return hit
    return ""


def verdict_pipe_hit(stripped: str) -> str:
    """Return the matched text when a `verdict` stage is piped into another command, else ''.
    Each command substitution (`$(...)`, backticks, in double quotes too) is its own text, read
    through the one reader in guard_env, as the draft-pr rule reads it."""
    texts, too_deep = _substitutions(stripped, powershell=is_powershell(stripped))
    if too_deep:   # the env layer refuses a nest this deep; read the command as it stands
        texts = [(stripped, False)]
    return next((hit for text, _in_message in texts if (hit := _verdict_pipe_in(text))), "")


VERDICT_PIPE_REASON = (
    "a pipe out of verdict hides its result: the pipeline returns the last command's exit, so a "
    "failed run reads as exit 0, and verdict prints its FAIL line first, which a filter can cut. "
    "Remedy: run `verdict <cmd>` with nothing after it. Its output is already short. "
    "(rule tokens-run-through-verdict, verdict keeps the full output in a log)"
)


# ------------------------------------------------------------------ a waiter loop
#
# Rule 9, approved by the owner: a shell segment whose command word is a sleep-and-poll turns
# waiting into a loop of turns that each print a word. Placed beside the live-stream rule, because
# both are about a command that should not be how a session waits.
#
# THE COMMAND WORD is read through `resolve_command`, wrappers and leading loop keywords skipped,
# not the segment's raw first token: `split_segments` cuts a loop's `while COND; do sleep 1;
# done` into `do sleep 1` as its own segment, and the command inside that block is `sleep`, not
# `do`. A segment `shlex` cannot parse fails open, this file's standing rule. The Windows
# `timeout /t` form is the one case where the wait is the SECOND word after the command, so it is
# read apart: `timeout /t 5` waits, `timeout /help` (no `/t`) does not.
WAITER_COMMANDS = ("sleep", "start-sleep")


SLEEP_LIMIT = 25   # one sleep under 25 s is allowed
LOOP_WORDS = {"while", "until", "for", "foreach", "do", "%", "foreach-object"}


def sleep_seconds(tokens, index) -> float:
    """Seconds of one `sleep N` / `Start-Sleep [-Seconds] N`; infinity when unreadable."""
    scale = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    unit = 1.0
    for token in tokens[index + 1:]:
        if token.lower() in ("-milliseconds", "-m"):
            unit = 0.001
        if DURATION.match(token):
            return float(token.rstrip("smhd")) * scale.get(token[-1], 1) * unit
    return float("inf")


def waiter_hit(segment: str) -> str:
    """Return the matched text for a `timeout /t` wait, else ''. Sleeps and watchers are
    judged over the whole command by `waiter_verdict`."""
    tokens = segment_tokens(segment)
    if not tokens:
        return ""
    index = resolve_command(tokens)
    if index is None:
        return ""
    # `timeout /t` is read at the first word (`timeout 5 /t 5` waits, and the unwrap would hide
    # it) and at the resolved word (`sudo timeout /t 5`, `verdict timeout /t 5`).
    for at in (_skip_assignments_and_keywords(tokens), index):
        if (at < len(tokens) and basename(tokens[at]) == "timeout"
                and any(t.lower() == "/t" for t in tokens[at + 1:])):
            return tokens[at] + " /t"
    return ""


def gh_watches(rest) -> str:
    """"run" for `gh run watch`, "checks" for `gh pr checks` with --watch or --watch=...; else ''.

    The global `-R`/`--repo` flag may sit between the group and the verb. `-w` on `gh pr checks`
    is `--web`, and `--watch` has no short form."""
    words, i = [], 0
    while i < len(rest) and len(words) < 2:
        t = rest[i]
        i += 2 if t in ("-R", "--repo") else 1
        if not (t in ("-R", "--repo") or t.startswith(("--repo=", "-R"))):
            words.append(t)
    if words == ["run", "watch"]:
        return "run"
    return "checks" if words == ["pr", "checks"] and watch_flag(rest[i:]) else ""


def watch_flag(args) -> bool:
    """True for `--watch` or `--watch=<v>`; not when the value is `false` or `0`, in either spelling
    (`--watch=false`, `--watch 0`), as test runners take it."""
    for i, a in enumerate(args):
        if a == "--watch":
            if args[i + 1:i + 2] and args[i + 1].lower() in ("false", "0"):
                continue
            return True
        if a.startswith("--watch=") and a[8:].lower() not in ("false", "0"):
            return True
    return False


# A loop ends at a clock time only when its one test orders a `date` read against a literal time of the same
# kind, in the direction that turns the test at that time. Two shapes do: a `+%s` read ordered with -gt, -ge,
# -lt or -le against an epoch number, and an ISO date-time read ordered with `>` or `<` against a full ISO
# date-time. `until` takes the later-than operators and `while` the earlier-than ones. Any other pairing never
# turns: a numeric order of a text read is an error, and a text order of epoch digits never meets an ISO time.
# The read is the clock only with no flag but -u: `-d` and `-r` read a fixed time, and a format outside
# CLOCK_FORMATS is not ordered like the ISO literal.
CLOCK_LITERAL = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?$|\d{9,}$")
CLOCK_READ = re.compile(r"\$\(date(?:\s[^;&|<>$`()]*)?\)$|`date(?:\s[^;&|<>$`()]*)?`$")
TEST_CLOSER = {"[": "]", "[[": "]]", "test": None}   # the only commands a clock loop's test may use
LATER_THAN = {">", "-gt", "-ge"}     # ends an `until` loop once the clock is past the literal
EARLIER_THAN = {"<", "-lt", "-le"}   # ends a `while` loop when the clock reaches the literal
CLOCK_FLAGS = ("-u", "--utc")        # the only flags a clock read may carry
# The formats a clock read may use: the epoch, and the ISO date-time with or without its `Z`.
CLOCK_FORMATS = ("+%s", "+%Y-%m-%dT%H:%M:%S", "+%Y-%m-%dT%H:%M:%SZ", "+%FT%T", "+%FT%TZ")


def clock_test(head) -> bool:
    """True when the loop header `head` (tokens, `while` or `until` first) is one `[ ]`, `[[ ]]` or `test`
    whose operands are exactly a `date` read, an ordering that ends the loop, and a literal time, with the
    read's format, the ordering and the literal all of one kind (epoch or ISO date-time)."""
    opener = head[1] if len(head) > 1 else ""
    if opener not in TEST_CLOSER:
        return False
    rest, closer = head[2:], TEST_CLOSER[opener]
    if closer:
        if not rest or rest[-1] != closer:
            return False
        rest = rest[:-1]
    # An unquoted `$(date -u +%s)` is split on its spaces: take the words up to the one that closes it.
    cut = next((n for n in range(1, len(rest) + 1) if CLOCK_READ.match(" ".join(rest[:n]))), 0)
    if not cut:
        return False
    form = date_format(" ".join(rest[:cut]))
    rest = rest[cut:]
    ends_loop = LATER_THAN if head[0].lower() == "until" else EARLIER_THAN
    if not (len(rest) == 2 and rest[0] in ends_loop and bool(CLOCK_LITERAL.match(rest[1]))):
        return False
    # CLOCK_LITERAL has matched, so a `:` marks the ISO form and all digits the epoch form.
    if rest[0].startswith("-"):
        return form == "+%s" and ":" not in rest[1]
    return form is not None and "%s" not in form and not rest[1].isdigit()


def date_format(read: str):
    """The `+FORMAT` argument of a `$(date ...)` or backtick `date` read, unquoted, when it is one of
    CLOCK_FORMATS and every other argument is one of CLOCK_FLAGS; else None, as for a read that cannot be split."""
    inner = read[2:-1] if read.startswith("$(") else read[1:-1]
    try:
        words = shlex.split(inner)
    except ValueError:
        return None
    forms = [word for word in words[1:] if word.startswith("+")]
    flags = [word for word in words[1:] if not word.startswith("+")]
    if len(forms) != 1 or forms[0] not in CLOCK_FORMATS or any(flag not in CLOCK_FLAGS for flag in flags):
        return None
    return forms[0]


def clock_loop(token_rows) -> bool:
    """True when the command's one loop is a `while`/`until` whose own test (no `&&` or `||` clause after
    it) is a `clock_test`, and no other loop. A quoted word is one token, so `grep -q "date"` names no clock."""
    words = [re.match(r"[\w%-]*", row[0]).group().lower() for row in token_rows]
    heads = [i for i, word in enumerate(words) if word in ("while", "until")]
    if len(heads) != 1 or any(w in LOOP_WORDS and w not in ("while", "until", "do") for w in words):
        return False
    return words[heads[0] + 1:heads[0] + 2] == ["do"] and clock_test(token_rows[heads[0]])


def waiter_verdict(segments, background: bool) -> str:
    """Return the matched text when a command waits by looping, else ''.

    Refused: a loop around a sleep, two or more sleeps, one sleep of SLEEP_LIMIT seconds or
    more, `timeout /t`, `gh run watch` (foreground or background), and a foreground
    `gh pr checks --watch`. Allowed: one short sleep, `gh pr checks --watch` with
    run_in_background, and, with run_in_background, one sleep of any length followed by a command
    and a `clock_loop`: a `+%s` read ordered against an epoch, or an ISO read ordered against an ISO time."""
    sleeps, loop, watcher, run_watch, followed = [], False, "", "", False
    token_rows = []
    for segment in segments:
        # Braces get their own token, so a compact `while(1){Start-Sleep 1}` reads like a spaced one.
        tokens = segment_tokens(re.sub(r"([{}])", r" \1 ", segment))
        if not tokens:
            continue
        token_rows.append(tokens)
        loop = loop or re.match(r"[\w%-]*", tokens[0]).group().lower() in LOOP_WORDS
        index = resolve_command(tokens)
        if index is None:
            continue
        word = basename(tokens[index]).lower()
        followed = followed or bool(sleeps) and word not in WAITER_COMMANDS
        # A PowerShell loop keeps its sleep in a `{ ... }` block inside the same segment.
        for at in sorted({index, *(i + 1 for i, t in enumerate(tokens[:-1]) if t == "{")}):
            if basename(tokens[at]).lower() in WAITER_COMMANDS:
                sleeps.append((tokens[at], sleep_seconds(tokens, at)))
        if word in WAITER_COMMANDS:
            pass
        elif word in ("gh", "gh.exe") and gh_watches(tokens[index + 1:]):
            found = "gh " + " ".join(tokens[index + 1:index + 3])
            watcher = watcher or found
            if gh_watches(tokens[index + 1:]) == "run":
                run_watch = run_watch or found
        elif waiter_hit(segment):
            return waiter_hit(segment)
    if background and clock_loop(token_rows):
        # A `+%s` read ordered against an epoch, or an ISO read ordered against an ISO time, ends the loop at
        # that time, so only its pauses are judged.
        loop = False
    if sleeps and loop:
        return sleeps[0][0]
    long_ok = background and followed
    if len(sleeps) > 1 or (any(seconds >= SLEEP_LIMIT for _, seconds in sleeps) and not long_ok):
        return sleeps[0][0]
    return run_watch or ("" if background else watcher)


WAITER_REASON = (
    "a pause between polls turns waiting into a loop of turns that each print a word. "
    "Remedy: wait for the CI-wake notice that follows gh pr ready. "
    "To wait until a clock time, use `bin/wait-until TIME [--timeout SECS]`, with TIME an ISO-8601 instant "
    "that has a zone. To wait on one pid, use `bin/wait-pid PID [--timeout SECS]`. "
    "To wait for another condition, run the long command in the background and wait for its completion "
    "notice. In the background, one pause of any length followed by a command is allowed, and so is a "
    "loop whose test orders the date output against a literal time of the same kind: date +%s against an "
    "epoch with -gt or -ge, or an ISO date-time read against an ISO time with \\>. "
    "A single pause under 25 seconds is allowed in the foreground. Avoid gh pr checks --watch in the "
    "foreground, which serves a cached status. For a server warm-up, use a "
    "readiness check such as `curl --retry 5 --retry-connrefused http://localhost:3000`."
)


# ------------------------------------------------------------------ a background end condition
#
# A server or watcher that runs in the background has no end of its own. The call must say when it
# ends: an `until: <condition>` note in the tool's `description`. The note
# belongs to the call, not the command text. stall_watch.py --stop shows the note per quiet job, and
# reads it through `until_note` below, the one parser.
#
# The roster is NAMED: "does this command ever end" cannot be resolved from the system, and a rule
# for every background call would refuse the builds and test runs that end by themselves. A foreground
# server that the harness timeout later moves to the background is NOT covered: its call never
# carried run_in_background (named safety hole).
UNTIL_NOTE = re.compile(r"\buntil:[ \t]*(\S[^\r\n]*)", re.I)
SCRIPT_RUNNERS = ("npm", "pnpm", "yarn", "bun", "npx", "pnpx", "bunx")
SCRIPT_MANAGERS = ("npm", "pnpm", "yarn", "bun")
RUNNER_VERBS = ("run", "run-script", "exec", "dlx", "x")
# A runner flag that takes its value as the next token, so the value is not the script name.
RUNNER_VALUE_FLAGS = ("--prefix", "-w", "--workspace", "-C", "--dir", "--filter", "-F", "--cwd",
                      "-p", "--package")
SERVER_SCRIPTS = ("dev", "serve", "start", "watch", "preview")
SERVER_PROGRAMS = ("serve", "http-server", "live-server", "nodemon", "uvicorn", "http.server")
# A program that serves when its first positional word is one of these verbs.
SERVER_VERBS = {"next": ("dev", "start"), "deno": ("serve",), "jupyter": ("lab", "notebook"),
                "webpack": ("serve",), "astro": ("dev",), "rails": ("s", "server"),
                "streamlit": ("run",)}
SHELL_EXTENSION = re.compile(r"\.(exe|cmd|bat|ps1)$")
# Named safety holes (decision background-needs-end-note): `node <file>` is not in the roster, the note
# is checked for presence only, and some wrappers and forms are not read (debt notes).


def until_note(description) -> str:
    """The end condition after `until:` in a tool description, to the end of its line, else ''."""
    found = UNTIL_NOTE.search(description) if isinstance(description, str) else None
    return found.group(1).strip() if found else ""


def program_name(token: str) -> str:
    """A command word or package name without its path, `@version` or `.exe`/`.cmd` suffix."""
    return SHELL_EXTENSION.sub("", basename(token)).split("@", 1)[0]


def server_script(name: str) -> bool:
    """True for a script name with a part, split on `:` and `-`, that serves or watches."""
    return any(part in SERVER_SCRIPTS for part in re.split(r"[:-]", name))


def server_program(word: str, args) -> bool:
    """True for a program (with its args) that serves or watches and never ends by itself.
    The `--watch` flag is read by the caller, on the whole command tail."""
    if word in SERVER_PROGRAMS:
        return True
    if re.fullmatch(r"python[\d.]*|py", word):
        for i, a in enumerate(args):  # options (`-u`, `-3`) may come before -m
            if a == "-m":  # the module is read as the program: `-m flask run`, `-m http.server`
                return i + 1 < len(args) and server_program(args[i + 1], args[i + 2:])
            if not a.startswith("-"):
                return False
        return False
    if word == "vite":
        return "build" not in args
    positional = [a for a in args if not a.startswith("-")]
    if word == "deno" and positional[:1] == ["task"]:
        return len(positional) > 1 and server_script(positional[1])
    if word in SERVER_VERBS:
        return positional[:1] != [] and positional[0] in SERVER_VERBS[word]
    if word == "flask":  # `flask --app hello run` puts an option value before the verb
        return "run" in positional
    if word == "tsc":
        return "-w" in args
    return False


def _inner_scripts(tokens, at: int):
    """The script text a wrapper at `tokens[at]` runs: `sh -c`, `pwsh -Command`, `cmd /c`, else ''."""
    script = inline_script(tokens)
    if script:
        return script
    word = basename(tokens[at])
    if word in PLAYWRIGHT_PS_SHELLS:
        return _pwsh_script(tokens)
    if word in ("cmd", "cmd.exe") and at + 1 < len(tokens) and tokens[at + 1].lower() in ("/c", "/k"):
        return PowerShellScript(" ".join(tokens[at + 2:]))
    return ""


def _tokens_hit(tokens) -> str:
    tokens = [t for t in ([tokens[0].lstrip("(")] + tokens[1:-1] + [tokens[-1].rstrip(")")]
                          if len(tokens) > 1 else [tokens[0].strip("()")]) if t]  # a subshell `(...)`
    at = resolve_command(tokens) if tokens else None
    if at is None:
        return ""
    if tokens[at] == "&":  # PowerShell's call operator
        return _tokens_hit(tokens[at + 1:]) if at + 1 < len(tokens) else ""
    script = _inner_scripts(tokens, at)
    if script:
        return next((hit for hit in map(server_hit, split_segments(script)) if hit), "")
    word, args = program_name(tokens[at]), tokens[at + 1:]
    tail, runner, script = args, word, word in SCRIPT_MANAGERS
    if word in SCRIPT_RUNNERS:
        # The flag skip below drops `--watch` and `--hot`, so both are read on `tail`, the whole args.
        while args and (args[0].startswith("-") or args[0] in RUNNER_VERBS):
            script = script and args[0] not in ("exec", "dlx", "x")  # a package binary, not a script
            args = args[2:] if args[0] in RUNNER_VALUE_FLAGS else args[1:]
        if not args:
            return ""
        name, rest = program_name(args[0]), args[1:]
        if script and server_script(name):
            return word + " " + name
        word, args = name, rest
    if word != "gh" and (watch_flag(tail) or runner == "bun" and "--hot" in tail):
        return word  # `gh ... --watch` ends when the run ends, so it is out of the roster
    return word if server_program(word, args) else ""


def server_hit(segment: str) -> str:
    """The matched text when one segment starts a server or watcher, else ''. Wrappers (`cmd /c`,
    `bash -c`, `pwsh -Command`, `&`, a subshell) are read through by guard_core's own resolvers."""
    tokens = segment_tokens(segment)
    return _tokens_hit(tokens) if tokens else ""


def background_end_hit(segments, background: bool, description) -> str:
    """The matched text when a background call starts a server or watcher with no until note."""
    if not background or until_note(description):
        return ""
    return next((hit for hit in map(server_hit, segments) if hit), "")


BACKGROUND_END_REASON = (
    "this command starts a server or watcher that never ends on its own, and nothing says when it "
    "should stop, so it can run unnoticed for a day. "
    "Remedy: put an end condition in this tool call's description, as `until: <condition>`, such "
    "as `until: round 1 bids are served`. The Stop check shows that note beside the job."
)


# ------------------------------------------------------------------ a waiter loop over a pattern
#
# THE CONDITION IS READ WHOLE, not only in command position: a negation (`while ! pgrep ...`) or
# a subshell can sit ahead of the poller, the same reason `live_stream_hit` below reads every
# token of its segment rather than only the first.
PATTERN_POLLERS = {"pgrep", "pkill", "lsof"}


def loop_condition_polls_a_pattern(segment: str) -> str:
    """Return the matched tool when a `while`/`until` segment's condition polls a pattern."""
    tokens = segment.split()
    if not tokens or tokens[0] not in ("while", "until"):
        return ""
    for token in tokens[1:]:
        if basename(token) in PATTERN_POLLERS:
            return token
    return ""


PATTERN_POLLER_REASON = (
    "the loop's own condition polls for a process by name or by pattern. That pattern can match "
    "every process whose command line names it, including this session's own wrapper for the "
    "same wait, so the condition can stay true long after the work is done. "
    "Remedy: wait on one pid with `bin/wait-pid PID [--timeout SECS]`, which also takes a job a stall "
    "left behind. To wait until a clock time, use `bin/wait-until TIME [--timeout SECS]`. "
    "To wait for CI, wait for the CI-wake notice that follows gh pr ready."
)


# ------------------------------------------------------------------ one shell trap

# `ln -s` where the link name is a directory that is already there. ln does not fail: it creates the
# link INSIDE that directory (`images/images`), the original is still in place, and the call exits 0.
# A real directory always
# descends, whatever flags. A symlink to a directory descends unless `-n`/`-h`, so `-sf` over one is
# the trap and `-sfn` is the answer. Nothing else is refused: a file or a link to a file either
# fails loudly or, with `-f`, is replaced as asked, and neither loses anything silently. A trailing
# slash, `-t`, and `-T` each say the destination is, or is not, a directory, so each is allowed.
# `-sf` over a link to a file is therefore allowed: it replaces the link, which is what `-f` means.
def ln_descends_hit(segment: str, where: str) -> str:
    """Return the matched text when `ln -s` would create a link inside an existing directory."""
    tokens = segment_tokens(segment)
    if not tokens:
        return ""
    at = resolve_command(tokens)
    if at is None or basename(tokens[at]) != "ln":
        return ""
    symbolic = no_deref = False
    operands = []
    index = at + 1
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if token == "--":
            operands.extend(tokens[index:])
            break
        if token in ("-t", "--target-directory", "--no-target-directory") or token.startswith(
                "--target-directory="):
            return ""
        if token.startswith("--"):
            symbolic = symbolic or token == "--symbolic"
            no_deref = no_deref or token == "--no-dereference"
        elif token.startswith("-") and len(token) > 1:
            if "T" in token[1:] or "t" in token[1:]:
                return ""
            symbolic = symbolic or "s" in token[1:]
            no_deref = no_deref or "n" in token[1:] or "h" in token[1:]
        else:
            operands.append(token)
    if not symbolic or len(operands) != 2:
        return ""
    dest = operands[1]
    if dest.endswith(("/", "\\")) or "$" in dest or "*" in dest:
        return ""
    full = _absolute(os.path.expanduser(dest), where or os.getcwd())
    if not os.path.isdir(full):
        return ""
    if os.path.islink(full) and no_deref:
        return ""
    return "ln -s over an existing directory"


LN_DESCENDS_REASON = (
    "the link name is a directory that already exists, so ln does not replace it: it creates the "
    "link inside it and exits 0, leaving the original where it was. "
    "Remedy: add -n beside -f to replace a link to a directory, check that the path is free first "
    "with a test such as [ -e path ], or end the destination with a slash when you mean a link "
    "inside the directory."
)

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
