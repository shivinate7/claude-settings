"""The guard's stream family: a stream that never ends, a waiter loop, a background server with no end
note, a waiter loop over a pattern and two ported shell traps.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import importlib
import os
import re
import shlex

from guard_core import (
    DURATION, PLAYWRIGHT_PS_SHELLS, PowerShellScript, _absolute, _pwsh_script, _skip_assignments_and_keywords,
    _wrapper_flags, backgrounding_amp, basename, bare_words, command_indexes, inline_script, inner_commands,
    is_powershell, resolve_command, git_calls, segment_dirs, segment_tokens, split_segments,
)
from guard_env import _substitutions
from merge_options import MERGE_OPTIONS


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
# refusing every `| tail` is the cry-wolf guard (docs/decisions/guard-that-cries-wolf-is-spent.md). A `tee`
# with nothing after it keeps every byte and is not refused; a `tee` followed by `tail` or `head` is
# refused, since the filter still cuts what the agent reads. Only `--confirm` reaches the wait: a bare
# `merge <pr>` is a preview that returns in seconds, so piping it is allowed.
NARRATING_COMMANDS = ("merge", "merge.cmd")
NARRATING_SCRIPT_TAILS = ("merge/merge.py", "merge/launch.py")
TRUNCATING_FILTERS = ("tail", "head")
# The lone writer stage the check rule lets through: `tee`, `tee.exe`, `Tee-Object` and `Out-File`. No filter
# cuts what it keeps. `tee` and `Tee-Object -FilePath` print the whole stream and write it to a file the agent
# reads back. `Tee-Object -Variable` writes no file but prints the stream in full. `Out-File` prints nothing, so
# its file is the only copy of the stream, as with `> file`.
# Compared on the word `basename` gives, with `.exe` stripped as in `_roster_word`.
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
# A redirect word the shell strips before the interpreter runs: `2>&1`, `2>/dev/null`, `>file`, `>>file`,
# `<file`, `&>file`. Group 1 is what follows the operator, empty for a bare `>` or `2>`, whose target is
# the next word.
REDIRECT_WORD = re.compile(r"^(?:\d*|&)(?:>>|<<<|<<|>&|<&|>|<|&>)(.*)$")


def _redirect_width(tokens, at: int) -> int:
    """How many words the redirect at `at` takes (1 for `2>&1`, 2 for a bare `>` and its target), 0 when
    the word at `at` is no redirect."""
    redirect = REDIRECT_WORD.match(tokens[at])
    if not redirect:
        return 0
    return 1 if redirect.group(1) else 2


def _skip_redirects(tokens, at: int) -> int:
    """The index of the first word from `at` on that is no redirect word. A redirect before the command
    (`2>/dev/null python3 lint/x.py`) is stripped by the shell, so the command is the word after it."""
    while at < len(tokens) and (width := _redirect_width(tokens, at)):
        at += width
    return at


def _flag_module(tokens, at: int):
    """What the interpreter flag at `at` (`-m`, `-Im`, `-Wignore`, `-uc`) does with the rest of the word.
    Returns (module, next_at): module is the `-m` operand, `""` for `-c` (code, no script), None for a
    flag that names neither. A value flag (-W, -X) takes the rest of its word, else the next word."""
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
    """The script an interpreter at `index` runs: its first word that is no flag and no redirect. A
    `-m <module>` runs the module's file, so `-m lint.ste_lint` reads as `lint/ste_lint.py` and the
    roster and lint tails judge it as they judge the path. '' for `-c <code>`, which runs no script."""
    at = index + 1
    while at < len(tokens):
        width = _redirect_width(tokens, at)
        if width:
            at += width
        elif tokens[at].startswith("-"):
            module, at = _flag_module(tokens, at)
            if module is not None:
                return module.replace(".", "/") + ".py" if module else ""
        else:
            return _whole_word(tokens, at)
    return ""


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
    both match. `interpreter_only` keeps the word to a command that runs a script (`_script_run`) and the
    path to that script: the check rule needs it, so `grep -n x merge/merge.py` and
    `python3 -m pytest -k merge/merge.py` are no run of the script."""
    word = basename(tokens[index])
    if word in NARRATING_COMMANDS:
        return word
    if interpreter_only:
        script = _script_run(tokens, index)
        if script.replace("\\", "/").endswith(NARRATING_SCRIPT_TAILS):
            return word if script == tokens[index] else word + " " + basename(script)
        return ""
    for token in tokens[index:]:
        if token.replace("\\", "/").endswith(NARRATING_SCRIPT_TAILS):
            return word + " " + basename(token)
    return ""


def narrated_tail_hit(stripped: str) -> str:
    """Return the matched text when a narrating stage reaches `tail`/`head`, directly or through a
    `tee` or other filters. Same pipeline walk as `check_tail_hit`, one stage reader apart."""
    flags = []
    pipelines = _pipelines(stripped, flags)
    for stages, list_amp in zip(pipelines, flags):
        hit = _pipeline_hit(stages, False, lambda segment, _background: narrating_stage(segment), list_amp=list_amp)
        if hit:
            return hit
    return ""


NARRATED_TAIL_REASON = (
    "this command waits for minutes and prints a line as it goes, and a pipe into a filter "
    "that keeps one end of the stream hides that line until the end, so a working wait looks "
    "like a hang. "
    "Remedy: run the command through `verdict <cmd>`, or with nothing after it, or through a "
    "`tee` with nothing after it, and read its output as it arrives, or redirect to a file you "
    "read back afterwards."
)


# A CHECK piped into any filter but a lone `tee`, `tee.exe`, `Tee-Object` or `Out-File` (decision
# background-check-through-verdict). A filter
# after the run can cut or hide the verdict line, the one useful line, so it can be lost or never read. `verdict <cmd>` keeps the whole log and prints the
# verdict itself. Only named checks count, one entry per incident, because refusing every `| tail` is the
# cry-wolf guard (docs/decisions/guard-that-cries-wolf-is-spent.md). The merge tool's verdict calls
# (`--lane-lint`, `--review-record`, `--release-check`) are refused in the foreground too. They count as `merge`,
# `merge.cmd`, or `merge/merge.py` or `merge/launch.py` run by `python`, a `python3.N`, `pythonw` or
# `py`, behind a wrapper or `uv run`. A call through `verdict` is verdict-pipe's, never read here.
# `merge --confirm` is narrated_tail_hit's, so it is left out here and never refused twice.
# `ci-job` is refused in the background only, and a trailing `&` is the background.
CHECK_COMMANDS = ("ci-job", "ci-job.cmd")
CHECK_FLAGS = ("--lane-lint", "--review-record", "--release-check")
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
    index = _skip_redirects(tokens, index)
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
        index = _skip_redirects(tokens, start + at)
    return index


def _merge_flag(tokens, flag: str) -> bool:
    """True when a token is the merge tool's option `flag`, or a prefix that names it alone. The merge parser sets
    allow_abbrev off, so a prefix runs no check (`--lane` is an error, not `--lane-lint`). The guard still reads a
    unique prefix as the flag: a tail after it is refused, which costs nothing, because the command fails anyway.
    A prefix that matches two or more options is no flag (`--l`). The option names are MERGE_OPTIONS, the list
    the merge parser is checked against. `--name=value` is split at the first `=`, so `--lane=7` reads as `--lane 7`.
    `check_timeout_hit` takes the exact token only."""
    for token in tokens:
        if token.startswith("--"):
            token = token.split("=", 1)[0]
        if len(token) > 2 and token.startswith("--") and token not in MERGE_OPTIONS:
            named = [name for name in MERGE_OPTIONS if name.startswith(token)]
            if named == [flag]:
                return True
        elif token == flag:
            return True
    return False


def check_stage(segment: str, background: bool) -> str:
    """The command word when one segment runs a named check, else ''. `ci-job` counts
    only in the background, which a trailing `&` makes it (the caller passes that in `background`)."""
    tokens = segment_tokens(segment)
    if not tokens:
        return ""
    index = resolve_command(tokens)
    if index is None:
        return ""
    index = _skip_uv_run(tokens, index)
    if index >= len(tokens):   # a redirect-only segment (`> out.txt`) leaves no command word
        return ""
    if basename(tokens[index]) in CHECK_COMMANDS:
        return basename(tokens[index]) if background else ""
    if _script_run(tokens, index).replace("\\", "/").endswith(CHECK_SCRIPT_TAIL):
        return CHECK_COMMANDS[0] if background else ""
    if "--confirm" in tokens or not any(_merge_flag(tokens, flag) for flag in CHECK_FLAGS):
        return ""
    return _roster_word(tokens, index, interpreter_only=True)


LINT_SCRIPT = re.compile(r"(?:^|/)lint/[^/]+\.py$")


CD_COMMANDS = ("cd", "pushd", "chdir", "set-location", "sl")


def _enters_lint_dir(segment: str, in_lint: bool) -> bool:
    """Whether the working directory is `lint/` after `segment`, given `in_lint` before it. A `cd` to a
    path that ends in `lint` enters it; a `cd` anywhere else leaves it; any other segment keeps it."""
    tokens = segment_tokens(segment)
    index = resolve_command(tokens) if tokens else None
    if index is None or basename(tokens[index]).lower() not in CD_COMMANDS:
        return in_lint
    targets = [word for word in tokens[index + 1:] if not word.startswith("-")]
    path = targets[0].replace("\\", "/").rstrip("/") if targets else ""
    return basename(path) == "lint"


LINT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "lint")


def _is_lint_file(name: str, folder=None) -> bool:
    """Whether `name` is a file in the lint folder the call has entered. `folder` is that folder, read
    from the call's own cwd and its `cd`. A copy install has no lint/ beside its guard, and another repo
    has its own lint scripts. So the guard's own folder is wrong for both. LINT_DIR, the lint/ of the
    checkout this guard runs from, is read only when `folder` is None: the cwd is unknown, or a `cd`
    went to a folder that does not exist. No list of lint scripts exists (LINT_SCRIPT is a path
    pattern), so the folder is the one home. Under `cd lint`, a bare name that is no file there
    (`-m pytest` reads as `pytest.py`) runs no lint script."""
    return os.path.isfile(os.path.join(folder or LINT_DIR, name))


def lint_stage(segment: str, background: bool, in_lint: bool = False, folder=None) -> str:
    """`lint` when one segment runs a script under `lint/`, through an interpreter, as `-m lint.<name>`,
    or as the `.py` command word (`uv run lint/x.py`), else ''. With `in_lint` (an earlier `cd lint` in
    the same command), a script named by its basename is under `lint/` too (`./ste_lint.py`) when it is
    a file in `folder`, the folder the segment runs in (see _is_lint_file). The `background` argument
    keeps the signature of check_stage, the other stage reader."""
    tokens = segment_tokens(segment)
    index = resolve_command(tokens) if tokens else None
    if index is None:
        return ""
    index = _skip_uv_run(tokens, index)
    if index >= len(tokens):   # a redirect-only segment (`> out.txt`) leaves no command word
        return ""
    script = _script_run(tokens, index).replace("\\", "/").lstrip("(")   # `(./x.py` opens a subshell
    if in_lint and script and "/" not in script.removeprefix("./") and _is_lint_file(
            script.removeprefix("./"), folder):
        script = "lint/" + script.removeprefix("./")
    if LINT_SCRIPT.search(script):
        return "lint"
    return ""


SUBSTITUTION_SLOT = re.compile(r"(?<![\w.-])x(?![\w.-])|`x`")


def _flat(pipelines):
    """The segments of `pipelines` in order, and the `ends` that segment_dirs reads. Only a pipe
    end matters to it here (a pipe part's `cd` moves nothing), so each pipeline ends in `;`."""
    segments, ends = [], []
    for stages in pipelines:
        for place, segment in enumerate(stages):
            segments.append(segment)
            ends.append("|" if place < len(stages) - 1 else ";")
    return segments, ends


def _inherited_in_lint(pipelines, cwd: str = ""):
    """Whether a command substitution inside the outer text `pipelines` runs with `lint/` as its working
    directory, and the folder it runs in (None when unknown). `_substitutions` leaves each substitution's
    place in the outer text as `x`, so a segment holding that slot, reached after a `cd lint`, hands
    `lint/` to every substitution. Which slot a text fills is not tracked, so one slot after `cd lint`
    counts for all (the reading that refuses more)."""
    segments, ends = _flat(pipelines)
    in_lint = False
    for segment, folder in zip(segments, segment_dirs(segments, cwd, ends)):
        if in_lint and SUBSTITUTION_SLOT.search(segment):
            return True, folder
        in_lint = _enters_lint_dir(segment, in_lint)
    return False, None


def _ends_in_ampersand(stages, first: int) -> bool:
    """Whether the pipeline is backgrounded by a `&` in the stage at `first` or a later one, spaced
    or glued to the last word (`backgrounding_amp`, the one reader detached-launch shares)."""
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


def _pipeline_hit(stages, background: bool, stage_of=check_stage, any_filter: bool = False,
                  any_later: bool = False, list_amp: bool = False) -> str:
    """The matched text when a stage that `stage_of(segment, backgrounded)` names, in one pipeline's
    stages, reaches `tail`/`head`. A `tee` between them does not end the reach, since the filter after it
    still cuts what the agent reads. A `tee` with no `tail` or `head` after it is not a hit. The one walk
    for the narrated rule and the check rule. `backgrounded` is the call's `background`, or a lone `&` word
    in this stage or a later one, or a job `&` that ends the `&&` or `||` list this pipeline closes
    (`list_amp`). `any_filter` (the check rule, decision `background-check-through-verdict`)
    widens the reach to every later stage but a file writer (`tee`, `tee.exe`, `Tee-Object`, `Out-File`),
    since `sed -n`, `grep -m1` and `awk` cut what the agent reads as `tail` does. With `any_later`, any
    later command counts: a pipeline's exit is its last stage's, so `grep`, `tee` and `wc` mask the
    exit of the stage before them as `tail` does (the lint-then-commit gate reads the exit, not the cut)."""
    for first, segment in enumerate(stages):
        stage = stage_of(segment, background or list_amp or _ends_in_ampersand(stages, first))
        if not stage:
            continue
        for later in stages[first + 1:]:
            tokens = segment_tokens(later)
            at = resolve_command(tokens) if tokens else None
            if at is None:
                continue
            at = _skip_redirects(tokens, at)
            if at >= len(tokens):
                continue
            word = basename(tokens[at])
            if any_later or ((word.removesuffix(".exe") not in FILE_WRITER_STAGES) if any_filter
                             else (word in TRUNCATING_FILTERS)):
                return stage + " | " + word
    return ""


def _commits_or_pushes(segment: str) -> bool:
    """True when one segment runs a commit or a push, read by the one reader of git calls."""
    return any(verb in ("commit", "push") for verb, _args in git_calls(segment))


def _pipelines(text: str, list_amps=None):
    """One command text as its pipelines, each a list of stage segments. A pipeline ends at any
    separator other than `|`. With `list_amps` (a list), it gets one flag per pipeline: whether the `&&`
    or `||` list that pipeline closes is ended by a job `&` (`_list_ends_in_ampersand`)."""
    ends = []
    segments = split_segments(text, ends)
    pipelines = []
    stages = []
    for number, (segment, end) in enumerate(zip(segments, ends)):
        stages.append(segment)
        if end != "|":
            pipelines.append(stages)
            if list_amps is not None:
                list_amps.append(end in ("&&", "||") and _list_ends_in_ampersand(segments, ends, number + 1))
            stages = []
    pipelines.append(stages)
    if list_amps is not None:
        list_amps.append(False)
    return pipelines


def check_tail_hit(stripped: str, background: bool, cwd: str = "") -> str:
    """The matched text when a call pipes a named check into any filter but a lone `tee`, `tee.exe`,
    `Tee-Object` or `Out-File`, directly or through other filters. Each command substitution is its own
    text, read through the one reader in guard_env as `verdict_pipe_hit` reads it, so a pipe inside `$(...)` counts. A lint script piped into any later
    command counts only when a later segment of the call runs a commit or a push: the pipeline's exit is
    the last stage's, so a red lint hides, and the commit or push runs on it (incident, lane
    windows-tests-for-touched-files). Order across texts is not tracked: a lint inside a substitution
    counts when any other text of the call runs a commit or a push, and so does an outer lint when a
    substitution after it runs one (`lint | tail -2 && out=$(git commit ...)`). Under `cd lint`, a bare
    script name is looked up in the folder its pipeline runs in. That folder is read from `cwd`, the
    call's own, and each `cd` before it. A pipe part's `cd` moves nothing, so all stages of a pipeline
    share the folder of its first stage. With no cwd, the guard's own lint/ is read (see _is_lint_file)."""
    texts, too_deep = _substitutions(stripped, powershell=is_powershell(stripped))
    if too_deep:   # the env layer refuses a nest this deep; read the command as it stands
        texts = [(stripped, False)]
    amps = [[] for _ in texts]
    texts = [_pipelines(text, flags) for (text, _in_message), flags in zip(texts, amps)]
    for pipelines, flags in zip(texts, amps):
        for stages, list_amp in zip(pipelines, flags):
            hit = _pipeline_hit(stages, background, any_filter=True, list_amp=list_amp)
            if hit:
                return hit
    inherited, slot_folder = _inherited_in_lint(texts[-1], cwd) if len(texts) > 1 else (False, None)
    for number, pipelines in enumerate(texts):
        inner = number < len(texts) - 1
        in_lint = inherited and inner
        segments, ends = _flat(pipelines)
        folders = list(segment_dirs(segments, slot_folder if inner else cwd, ends))
        first = 0
        for at, stages in enumerate(pipelines):
            folder = folders[first] if stages else None
            first += len(stages)
            hit = _pipeline_hit(stages, background,
                                lambda segment, bg: lint_stage(segment, bg, in_lint, folder), any_later=True)
            for segment in stages:
                in_lint = _enters_lint_dir(segment, in_lint)
            if not hit:
                continue
            others = texts[:number] + texts[number + 1:]
            after = list(pipelines[at + 1:]) + [stages for text in others for stages in text]
            if any(_commits_or_pushes(segment) for later in after for segment in later):
                return hit + " then a commit or push"
    return ""


CHECK_TAIL_REASON = (
    "this check's output goes into a filter after the run, and the filter can cut or hide the "
    "verdict line "
    "(decision background-check-through-verdict). "
    "Remedy: run the check through verdict, as `verdict <cmd>` with nothing after it. It keeps the "
    "full log and prints the verdict itself. "
    "Start a lane lint in the background. Give it a time limit above its bound, "
    "LINT_SECONDS plus PUSHED_HEAD_WAIT_MINUTES times 60, times 1000 ms (rule check-timeout gives the figure). "
    "A shorter limit ends it before the verdict."
)


# A BACKGROUND LANE LINT'S TIME LIMIT (rule check-timeout). `merge --lane-lint` waits for its pushed head. Then it
# runs one ci-job under the merge tool's lint bound. A call whose `timeout` is shorter ends before the verdict.
# The bound is read from the merge tool, never copied. The tool caps a foreground limit below the bound,
# so a foreground lane lint that sets a limit is refused at any limit. A call that sets no `timeout` is not
# judged: no limit means no bound to compare. An unloadable merge tool gives an unknown bound: nothing is refused.


def check_timeout_bound_ms():
    """The least limit in ms a lane lint can finish under, or None."""
    import guard_merge  # Lazy: only a lane lint pays to load the merge tool.
    tool = guard_merge.merge_module()
    if tool is None:
        return None
    try:
        return (tool.LINT_SECONDS + tool.PUSHED_HEAD_WAIT_MINUTES * 60) * 1000
    except (AttributeError, TypeError):
        return None


def check_timeout_hit(stripped: str, background: bool, timeout_ms=None) -> str:
    """The matched text when a call runs `merge --lane-lint` with too little time, else ''.
    A call that sets no limit is not judged. A foreground call that sets one has too little at any limit.
    A background call has too little under the bound. `timeout_ms` is the `timeout` of the call, None when unset."""
    hit = ""
    for segment in split_segments(stripped):
        word = check_stage(segment, False)  # False: ci-job is no lane lint
        tokens = segment_tokens(segment) if word else None
        if word and tokens and "--lane-lint" in tokens:
            hit = word + " --lane-lint"
            break
    if not hit or isinstance(timeout_ms, bool) or not isinstance(timeout_ms, (int, float)):
        return ""
    bound = check_timeout_bound_ms()
    if bound is None:
        return ""
    if not background:
        return hit
    return hit if timeout_ms < bound else ""


CHECK_TIMEOUT_TEMPLATE = (
    "a lane lint with a time limit shorter than its own bound ends before it prints a verdict "
    "(decision background-check-through-verdict). "
    "A run in the foreground is capped below that bound. "
    "Remedy: start it in the background, as `verdict <cmd>`, with a time limit of %s. "
    "That is LINT_SECONDS plus PUSHED_HEAD_WAIT_MINUTES times 60, times 1000. "
    "Read the verdict when the run ends."
)


def check_timeout_limit_text() -> str:
    """The limit the refusal names, read from the merge tool when it loads."""
    bound = check_timeout_bound_ms()
    return "at least %d ms" % bound if bound is not None else "above the bound"


def _check_timeout_reason() -> str:
    """The text of CHECK_TIMEOUT_REASON, with the bound read from the merge tool."""
    return CHECK_TIMEOUT_TEMPLATE % check_timeout_limit_text()


def __getattr__(name):
    """CHECK_TIMEOUT_REASON, built on first read: it holds the bound, and reading the bound loads the merge tool."""
    if name == "CHECK_TIMEOUT_REASON":
        return _check_timeout_reason()
    raise AttributeError(name)


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
    "Remedy: to wait, then run a command, use `bin/wait-until TIME [--timeout SECS]`, with TIME an ISO-8601 "
    "instant that has a zone, then run the command. To wait for CI, wait for the CI-wake notice that "
    "follows gh pr ready. To wait on one pid, use `bin/wait-pid PID [--timeout SECS]`. "
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


# ------------------------------------------------------------------ a long foreground call while background work runs
#
# Guard rule fg-bash-while-bg (decision fg-bash-while-bg). It refuses only a call that can
# run long: a test, lint, merge, build or install, or a time limit over 60 s. Quick reads stay in the foreground.
# A foreground call that runs long holds the session still while its agents and background commands run, so nothing
# can read their notices until it ends. The call is refused only while this session has background work: a
# background command or a background agent with no terminal notice and no TaskStop (stall_watch.scan_jobs, the
# one reader of that state). A call from an agent is not judged: the transcript is its parent's, and an agent's
# own wait freezes no session. A missing or unreadable transcript, or a failed import, allows.
# THE LONG FORMS are read by shape, per command word, and never by substring, so `grep test notes.txt` and
# `git status` stay quick. Wrappers (`verdict`, `timeout`, `sudo`, `uv run`) and `bash -c` text are read through.
# A call that runs nothing stays quick: a version or help flag, a dry run (`make -n`) and a `command -v` lookup.
FG_LIMIT_MS = 60000
FG_PROGRAMS = frozenset((
    "pytest", "py.test", "tox", "nox", "jest", "vitest", "mocha", "playwright", "eslint", "pylint", "flake8", "mypy",
    "pyright", "shellcheck", "markdownlint", "make", "gmake", "cmake", "ninja", "xcodebuild", "gradle", "gradlew",
    "mvn", "bazel", "ci-job", "sim-test", "ruff", "black", "rspec", "invoke-pester",
))
FG_PYTHON_MODULES = frozenset((
    "pytest", "unittest", "tox", "nox", "mypy", "pylint", "flake8", "ruff", "black", "build", "pip", "playwright",
))
FG_INSTALLERS = {  # the install verbs of each installer
    "pip": ("install",), "pip3": ("install",), "pipx": ("install", "upgrade"), "poetry": ("install", "add", "update"),
    "uv": ("sync", "add", "install", "pip", "tool"), "brew": ("install", "upgrade", "reinstall"),
    "apt": ("install", "upgrade"), "apt-get": ("install", "upgrade"), "gem": ("install",), "bundle": ("install",),
    "composer": ("install", "update"), "conda": ("install", "create"), "dotnet": ("build", "test", "restore"),
    "swift": ("build", "test"), "cargo": ("build", "test", "check", "clippy", "install"),
    "go": ("build", "test", "install", "vet"),
}
FG_VERBS = {  # a program that runs long only for some verbs: the verbs, read after the program's own flags
    "pre-commit": ("run", "run-hooks", "autoupdate", "install-hooks"),
    "deno": ("test", "lint", "check", "bench", "compile", "install"),
    "docker": ("build", "buildx", "compose"),
    "git": ("clone",),
}
FG_VERB_FLAGS = {  # the flags of a FG_VERBS program that take a value
    "git": ("-C", "-c", "--git-dir", "--work-tree", "--namespace"),
    "docker": ("-H", "--host", "-c", "--context"),
}
FG_PACKAGE_MANAGERS = ("npm", "pnpm", "yarn", "bun")
FG_PACKAGE_VERBS = frozenset(("test", "t", "tst", "install", "i", "ci", "add", "build", "lint"))
FG_SCRIPT_NAME = re.compile(r"test|lint|build|check|install|verify|compile|e2e|ci$")
FG_INTERPRETERS = frozenset(("node", "bash", "sh", "zsh", "ruby", "deno", "pwsh", "powershell"))
FG_TEST_FILE = re.compile(r"(?:^tests?\.\w+$|^test[_-]|[_-]tests?\.\w+$|\.(?:test|spec)\.\w+$|^run[_-]?tests?\.\w+$)")
FG_TEST_DIR = re.compile(r"(?:^|/)tests?/")  # a script kept in a test folder, such as tests/run.sh
# The programs whose lone `-v` prints the version. For pytest, flake8, mypy, pip and most others `-v` is verbose,
# and `pytest -v` runs the tests.
FG_VERSION_V = frozenset((
    "tsc", "node", "npm", "npx", "pnpm", "yarn", "bun", "make", "gmake", "gradle", "gradlew", "mvn", "rspec",
    "eslint", "jest", "vitest", "docker", "ruby", "gem",
))
FG_QUICK_FLAGS = {  # per program, the flags that run nothing: an info read or a dry run
    "xcodebuild": ("-version", "-showsdks", "-help", "-usage"),
    "make": ("-n", "--dry-run", "--just-print", "--recon"),
    "gmake": ("-n", "--dry-run", "--just-print", "--recon"),
}
# RUNNER_VALUE_FLAGS is the one list of a package manager's flags that take a value. These managers read one of
# its flags as taking no value: pnpm `-w` is --workspace-root and npm `-p` is --parseable.
FG_PACKAGE_BOOL_FLAGS = {"pnpm": ("-w",), "npm": ("-p",)}


def _fg_verb_hit(word: str, args) -> str:
    """The matched text when `word` (a FG_VERBS program) runs one of its long verbs, else ''. `docker buildx` and
    `docker compose` count for their `build` verb only. A flag that takes a value is skipped with it."""
    at = 0
    while at < len(args) and args[at].startswith("-"):
        at += 2 if args[at] in FG_VERB_FLAGS.get(word, ()) else 1
    verb = args[at] if at < len(args) else ""
    if verb not in FG_VERBS[word]:
        return ""
    if verb in ("buildx", "compose") and args[at + 1:at + 2] != ["build"]:
        return ""
    return word + " " + verb


def _fg_info_read(word: str, args) -> bool:
    """True for a call that runs nothing. `--version`, `--help` and `-h` print and exit, so they count anywhere.
    A lone `-v` counts only for a FG_VERSION_V program, since `pytest -v` runs the tests. A FG_QUICK_FLAGS flag
    counts for its own program only, so `make -n` is quick and `pytest -n 4` is not."""
    if "--version" in args or "--help" in args or "-h" in args:
        return True
    if word in FG_VERSION_V and list(args) == ["-v"]:
        return True
    return any(arg in FG_QUICK_FLAGS.get(word, ()) for arg in args)


def _fg_lookup(tokens, at: int) -> bool:
    """True when `tokens[at]` follows `command -v` or `command -V`, which prints where the word is and runs
    nothing. `command` is a COMMAND_WRAPPERS entry, so the resolver has already stepped past it and its flags."""
    start = at
    while start > 0 and tokens[start - 1].startswith("-"):
        start -= 1
    if start == 0 or basename(tokens[start - 1].lstrip("$(")) != "command":
        return False
    return any(not flag.startswith("--") and ("v" in flag or "V" in flag) for flag in tokens[start:at])


class _FgTokens(list):
    quoted = frozenset()


def _fg_clean(tokens):
    """The tokens with the `)` that closes a group cut off each unquoted word, so `(npm test)` reads as
    `npm test`. A word that is only `)` stays. `quoted` is kept for command_indexes."""
    quoted = getattr(tokens, "quoted", frozenset())
    cleaned = _FgTokens(token.rstrip(")") if i not in quoted and token.rstrip(")") else token
                        for i, token in enumerate(tokens))
    cleaned.quoted = quoted
    return cleaned


def _fg_skip_ionice(tokens, index: int) -> int:
    """The index of the command `ionice [flags] ...` runs, read through `resolve_command` again, else `index`.
    `ionice` is no entry of COMMAND_WRAPPERS, which would move every rule that reads the command word."""
    while index < len(tokens) and basename(tokens[index]) == "ionice":
        start = _wrapper_flags("ionice", tokens, index + 1)[0]
        at = resolve_command(tokens[start:])
        if at is None:
            break
        index = start + at
    return index


def _fg_positional(args):
    return [arg for arg in args if not arg.startswith("-")]


def _fg_package_positional(word: str, args):
    """The positional words of a package manager's args. A RUNNER_VALUE_FLAGS flag's value is skipped with it,
    so `npm --prefix web test` reads `test`, unless FG_PACKAGE_BOOL_FLAGS names that flag for this manager."""
    found, at = [], 0
    while at < len(args):
        arg = args[at]
        at += 1
        if not arg.startswith("-"):
            found.append(arg)
        elif arg in RUNNER_VALUE_FLAGS and arg not in FG_PACKAGE_BOOL_FLAGS.get(word, ()):
            at += 1
    return found


def _fg_test_file(path: str) -> bool:
    """True for a file named as a test, or kept in a `test` or `tests` folder."""
    return bool(FG_TEST_FILE.search(basename(path)) or FG_TEST_DIR.search(path))


def _fg_script_long(word: str, args) -> str:
    """The script an interpreter runs when it is a test file, else ''. `-m <module>` names the module instead.
    `node --test` runs node's own test runner."""
    at = 0
    while at < len(args) and args[at].startswith("-"):
        flag = args[at]
        if word == "node" and flag == "--test":
            return flag
        if flag == "-m":
            module = args[at + 1] if at + 1 < len(args) else ""
            return "-m " + module if module in FG_PYTHON_MODULES and (
                module != "pip" or "install" in args[at + 2:]) else ""
        if flag == "-c":
            return ""
        at += 2 if flag in INTERPRETER_VALUE_FLAGS else 1
    script = args[at] if at < len(args) else ""
    return script if script and _fg_test_file(script) else ""


def _fg_package_hit(word: str, positional) -> str:
    """The matched text when an npm, pnpm, yarn or bun call installs, tests, lints or builds, else ''.
    `run <script>` reads the script's name. The other managers also run a script by its bare name."""
    verb = positional[0] if positional else ""
    runs = verb in ("run", "run-script")
    script = positional[1] if runs and len(positional) > 1 else verb
    if verb in FG_PACKAGE_VERBS or (runs or word != "npm") and FG_SCRIPT_NAME.search(script):
        return word + " " + script
    return ""


def _fg_word_hit(tokens, at: int) -> str:
    """The matched text when the command at `tokens[at]` can run long, else ''."""
    word, args = program_name(tokens[at]), tokens[at + 1:]
    positional = _fg_positional(args)
    if _fg_info_read(word, args) or _fg_lookup(tokens, at):
        return ""
    if any(basename(token) in VERDICT_WORDS for token in tokens[:at]):
        return "verdict " + word
    if word in FG_PROGRAMS:
        return word
    if word in FG_VERBS:
        return _fg_verb_hit(word, args)
    if _roster_word(tokens, at, interpreter_only=True):
        return "merge"
    if word in FG_PACKAGE_MANAGERS:
        return _fg_package_hit(word, _fg_package_positional(word, args))
    if word == "npx" and positional[:1] and (positional[0] in FG_PROGRAMS or positional[0] == "tsc"):
        return word + " " + positional[0]
    if word in FG_INSTALLERS:
        verb = positional[0] if positional else ""
        if verb in FG_INSTALLERS[word] and (word != "uv" or verb != "tool" and (
                verb != "pip" or positional[1:2] == ["install"])):
            return word + " " + verb
        return ""
    if word == "tsc":
        return "" if "-w" in args or "--watch" in args else word
    if _fg_test_file(tokens[at]):  # a test file run directly
        return word
    if SCRIPT_INTERPRETER.match(word) or word in FG_INTERPRETERS:
        script = _fg_script_long(word, args)
        return word + " " + script if script else ""
    return ""


def _fg_tokens_hit(tokens, depth: int) -> str:
    """The matched text when the one segment `tokens` runs a command that can run long, else ''. A shell's
    `-c` text, `cmd /c` and `pwsh -Command` are read as segments of their own."""
    tokens = _fg_clean(tokens)
    for start in command_indexes(tokens):
        at = _fg_skip_ionice(tokens, _skip_uv_run(tokens, start))
        hit = _fg_word_hit(tokens, at)
        if hit:
            return hit
    script = _inner_scripts(tokens, resolve_command(tokens)) if depth < 3 and resolve_command(tokens) is not None else ""
    return next((hit for seg in split_segments(script) if (hit := fg_long_segment(seg, depth + 1))), "") if script else ""


def fg_long_segment(segment: str, depth: int = 0) -> str:
    """The matched text when one segment can run long, else ''."""
    tokens = segment_tokens(segment)
    return _fg_tokens_hit(tokens, depth) if tokens else ""


def fg_long_hit(segments, timeout_ms=None) -> str:
    """The matched text when a foreground call can run long, else ''. A `timeout` over FG_LIMIT_MS is long too."""
    if isinstance(timeout_ms, (int, float)) and not isinstance(timeout_ms, bool) and timeout_ms > FG_LIMIT_MS:
        return "timeout %d ms" % timeout_ms
    return next((hit for hit in map(fg_long_segment, segments) if hit), "")


def background_work_running(transcript) -> bool:
    """True when the session's transcript shows a background command or agent with no terminal notice and no
    TaskStop. False for no transcript, an unreadable one, or a failed import: the rule fails open."""
    if not isinstance(transcript, str) or not transcript:
        return False
    try:
        # Loaded by name, and only for a call that can run long. The darwin-arm scan of test_guard reads import
        # statements, and scan_jobs reads one file and never reaches the process-table arms of stall_watch.
        jobs, _stop = importlib.import_module("stall_watch").scan_jobs(transcript)
        return bool(jobs)
    except Exception:
        return False


FG_BACKGROUND_REASON = (
    "refused in the foreground while background work runs: this call can run long, and this session has a "
    "background command or agent that is still running. A long foreground call holds the session still, so no "
    "notice from that work can be read until it ends (decision fg-bash-while-bg, owner, 2026-11-16 13:47 CST). "
    "Remedy: rerun it with run_in_background and it is allowed. Read its result when its notice arrives. "
    "A quick read stays in the foreground."
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
