"""The guard's stream family: a stream that never ends, a waiter loop, a background server with no end
note, a waiter loop over a pattern and two ported shell traps.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import os
import re

from guard_core import (
    DURATION, PLAYWRIGHT_PS_SHELLS, PowerShellScript, _absolute, _pwsh_script, _skip_assignments_and_keywords, basename,
    bare_words, command_indexes, inline_script, inner_commands, resolve_command, segment_tokens,
    split_segments,
)


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
    "wait for its completion notice."
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


def narrating_stage(segment: str) -> str:
    """The command word when one segment is a long, narrating `--confirm` run, else ''."""
    tokens = segment_tokens(segment)
    if not tokens or "--confirm" not in tokens:
        return ""
    index = resolve_command(tokens)
    if index is None:
        return ""
    word = basename(tokens[index])
    if word in NARRATING_COMMANDS:
        return word
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
# carried run_in_background (named hole).
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
# Named holes (decision background-needs-end-note): `node <file>` is not in the roster, the note
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
    "Remedy: wait on one pid this session started, such as `kill -0 $PID`. To wait for CI, wait "
    "for the CI-wake notice that follows gh pr ready."
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
