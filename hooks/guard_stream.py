"""The guard's stream family: a stream that never ends, a waiter loop, a background server with no end
note, a waiter loop over a pattern and two ported shell traps.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import os
import re

from guard_core import (
    DURATION, PLAYWRIGHT_PS_SHELLS, PowerShellScript, _absolute, _pwsh_script, _skip_assignments_and_keywords, basename,
    bare_words, command_indexes, dir_before_segment, inline_script, inner_commands, is_powershell,
    resolve_command, git_calls, segment_tokens, split_segments,
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
    "wait for its completion notice. To wait on a pid, use `wait-pid PID [--timeout SECS]`."
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


# A CHECK piped into `tail` or `head` (decision background-check-through-verdict). A filter that keeps
# one end holds every byte until the command exits, then prints a few lines, so the one useful line, the
# verdict, can be cut off or never read. `verdict <cmd>` keeps the whole log and prints the verdict
# itself. Only named checks count, one entry per incident, because refusing every `| tail` is the
# cry-wolf guard (docs/decisions/guard-that-cries-wolf-is-spent.md). The merge tool's verdict calls
# (`--lane-lint`, `--review-record`) are refused in the foreground too. They count as `merge`,
# `merge.cmd`, or `merge/merge.py` or `merge/launch.py` run by `python`, a `python3.N`, `pythonw` or
# `py`, behind a wrapper or `uv run`. A call through `verdict` is verdict-pipe's, never read here.
# `merge --confirm` is narrated_tail_hit's, so it is left out here and never refused twice.
# `ci-job` is refused in the background only.
CHECK_COMMANDS = ("ci-job", "ci-job.cmd")
CHECK_FLAGS = ("--lane-lint", "--review-record")
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
    """True when a token is the merge tool's option `flag` or an argparse prefix that names it alone.
    argparse takes an exact name first, else a prefix that matches one option (`--lane` is `--lane-lint`).
    A prefix that matches two or more is an error and runs nothing, so it is no flag (`--l`). The option
    names are MERGE_OPTIONS, the list the merge parser is checked against. argparse splits `--name=value`
    at the first `=` before it matches, so `--lane=7` names --lane-lint as `--lane 7` does."""
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
    only in the background."""
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
    """The segments of `pipelines` in order, and the `ends` that dir_before_segment reads. Only a pipe
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
    for number, segment in enumerate(segments):
        if in_lint and SUBSTITUTION_SLOT.search(segment):
            return True, dir_before_segment(segments, number, cwd, ends)
        in_lint = _enters_lint_dir(segment, in_lint)
    return False, None


def _pipeline_hit(stages, background: bool, stage_of=check_stage, any_later: bool = False) -> str:
    """The matched text when a stage that `stage_of` names, in one pipeline's stages, reaches
    `tail`/`head`. A `tee` between them does not end the reach, since the filter after it still cuts
    what the agent reads. A `tee` with no `tail` or `head` after it is not a hit. With `any_later`, any
    later command counts: a pipeline's exit is its last stage's, so `grep`, `tee` and `wc` mask the
    exit of the stage before them as `tail` does (the lint-then-commit gate reads the exit, not the cut)."""
    for first, segment in enumerate(stages):
        stage = stage_of(segment, background)
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
            if any_later or word in TRUNCATING_FILTERS:
                return stage + " | " + word
    return ""


def _commits_or_pushes(segment: str) -> bool:
    """True when one segment runs a commit or a push, read by the one reader of git calls."""
    return any(verb in ("commit", "push") for verb, _args in git_calls(segment))


def _pipelines(text: str):
    """One command text as its pipelines, each a list of stage segments. A pipeline ends at any
    separator other than `|`."""
    ends = []
    segments = split_segments(text, ends)
    pipelines = []
    stages = []
    for segment, end in zip(segments, ends):
        stages.append(segment)
        if end != "|":
            pipelines.append(stages)
            stages = []
    pipelines.append(stages)
    return pipelines


def check_tail_hit(stripped: str, background: bool, cwd: str = "") -> str:
    """The matched text when a call pipes a named check into `tail`/`head`, directly or through other
    filters. Each command substitution is its own text, read through the one reader in guard_env as
    `verdict_pipe_hit` reads it, so a pipe inside `$(...)` counts. A lint script piped into any later
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
    texts = [_pipelines(text) for text, _in_message in texts]
    for pipelines in texts:
        for stages in pipelines:
            hit = _pipeline_hit(stages, background)
            if hit:
                return hit
    inherited, slot_folder = _inherited_in_lint(texts[-1], cwd) if len(texts) > 1 else (False, None)
    for number, pipelines in enumerate(texts):
        inner = number < len(texts) - 1
        in_lint = inherited and inner
        segments, ends = _flat(pipelines)
        start = slot_folder if inner else cwd
        first = 0
        for at, stages in enumerate(pipelines):
            folder = dir_before_segment(segments, first, start, ends) if stages else None
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
    "this check's output goes into a filter that keeps one end, so the filter holds everything "
    "until the check exits and the verdict can be lost "
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


def waiter_verdict(segments, background: bool) -> str:
    """Return the matched text when a command waits by looping, else ''.

    Refused: a loop around a sleep, two or more sleeps, one sleep of SLEEP_LIMIT seconds or
    more, `timeout /t`, `gh run watch` (foreground or background), and a foreground
    `gh pr checks --watch`. Allowed: one short sleep, and `gh pr checks --watch` with
    run_in_background."""
    sleeps, loop, watcher, run_watch = [], False, "", ""
    for segment in segments:
        # Braces get their own token, so a compact `while(1){Start-Sleep 1}` reads like a spaced one.
        tokens = segment_tokens(re.sub(r"([{}])", r" \1 ", segment))
        if not tokens:
            continue
        loop = loop or re.match(r"[\w%-]*", tokens[0]).group().lower() in LOOP_WORDS
        index = resolve_command(tokens)
        if index is None:
            continue
        word = basename(tokens[index]).lower()
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
    if sleeps and loop:
        return sleeps[0][0]
    if len(sleeps) > 1 or any(seconds >= SLEEP_LIMIT for _, seconds in sleeps):
        return sleeps[0][0]
    return run_watch or ("" if background else watcher)


WAITER_REASON = (
    "a pause between polls turns waiting into a loop of turns that each print a word. "
    "Remedy: wait for the CI-wake notice that follows gh pr ready. "
    "To wait for another condition, use the Monitor tool once, or run the long command in the background and wait for its completion notice. "
    "To wait on one pid, use `wait-pid PID [--timeout SECS]`. "
    "A single pause under 25 seconds is allowed. Avoid "
    "gh pr checks --watch in the foreground, which serves a cached status. For a server warm-up, use a "
    "readiness check such as curl --retry."
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
    "Remedy: wait on one pid with `wait-pid PID [--timeout SECS]`, which also takes a job a stall "
    "left behind. To wait for CI, wait for the CI-wake notice that follows gh pr ready."
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
