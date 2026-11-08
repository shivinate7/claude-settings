#!/usr/bin/env python3
"""Every deny check on the shell path returns or refuses. None raises.

Decision guard-hooks-fail-closed (owner ruling, 2026-10-12): a guard that crashes lets the call
through. `main()` in hooks/guard.py catches an exception from `judge` and exits 0, so a raise in a
check is a call the guard let pass. Incident: a builder fix in hooks/guard_kill.py raised ValueError
on an unclosed `${`, and the guard failed open.

Run from the repository root:

    python3 hooks/test_checks_never_raise.py

Standard library only. The check list is read from the dispatch: the names that `judge_shell` and
`judge` call in hooks/guard.py, resolved to the guard modules (guard.py, guard_core.py and the
`_FAMILY_MODULES` tuple). A callee that the test neither fuzzes nor declares in OUTSIDE, with a
reason, fails the run. No check is skipped without a line saying so.

Each check gets COUNT seeded random command strings (one stream per check name, seed SEED), built
from shell and PowerShell characters and fragments, plus fixed edge inputs. Each direct check's other
parameters come from the real producers (`split_segments`, `segment_tokens`) or fixed harness values.
`judge` is fed whole Bash and PowerShell payloads. A refusal is `SystemExit`, because `refuse()` exits
by design; it is not a raise.

Isolation: CLAUDE_CONFIG_DIR is a run folder, so guard.log and the override state stay out of the real
config. PATH is an empty folder, so git and gh are absent and every read fails as on a machine without
them. The parsers of git and gh output are not fuzzed here.

The self-test feeds a check that raises, and one that refuses, through the same harness. The raising
check must be reported and the refusing one must not. A sweep case proves the shared run-folder sweep
(lint/_test_temp.py) removes an old sibling and keeps a new one.
"""

import ast
import builtins
import contextlib
import glob
import inspect
import io
import os
import random
import shutil
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lint"))
import _test_temp  # noqa: E402  the one home of the run folder (decision test-temp-standard)

SEED = "checks-never-raise"
COUNT = 2000   # random inputs per check, on top of the fixed edge inputs below
DISPATCH = ("judge_shell", "judge")

RUN = _test_temp.run_folder()
CONFIG = os.path.join(RUN, "config")        # guard.log and override state land here, not in the real config
NO_TOOLS = os.path.join(RUN, "no-tools")    # an empty PATH: git and gh are absent
CHECKOUT = os.path.join(RUN, "checkout")    # a plain folder, not a repository
TRANSCRIPT = os.path.join(RUN, "transcript.jsonl")
EMPTY_TRANSCRIPT = os.path.join(RUN, "empty.jsonl")
MISSING_TRANSCRIPT = os.path.join(RUN, "missing.jsonl")
for folder in (CONFIG, NO_TOOLS, CHECKOUT):
    os.makedirs(folder)
with open(TRANSCRIPT, "w", encoding="utf-8") as handle:
    handle.write('{"type": "user", "message": {"role": "user", "content": "hello"}}\n')
open(EMPTY_TRANSCRIPT, "w", encoding="utf-8").close()
os.environ["CLAUDE_CONFIG_DIR"] = CONFIG
os.environ["PATH"] = NO_TOOLS

import guard  # noqa: E402  the global PreToolUse guard (hooks/guard.py)
import guard_core  # noqa: E402  the shared code the guard and its families import

GUARD_MODULES = frozenset(("guard", "guard_core") + tuple(guard._FAMILY_MODULES))

# Dispatch callees the test does not fuzz, each with the reason and where it is reached.
OUTSIDE = {
    "is_worktree": "defined in hooks/git_reads.py, outside the files this test covers; judge_shell reaches it",
    "unread_handoff": "imported inside judge from hooks/reread_check.py, outside the files this test covers; judge reaches it",
}

CHARS = "${}()[]=;'\"`|&<> \n$-*?"
FRAGMENTS = (
    "git ", "env:GIT_DIR", "rm -rf", "wsl -e", "pwsh -Command", "sh -c", "<<EOF", "$(", "${",
    "${X:?", "git push --force", "git stash", "git worktree remove", "xargs kill", "pgrep x | ",
    "lsof -t", "gh pr merge", "cd ", "&& ", "| ", "'", '"', "`", "\\", "\n", "-Command ",
    "Remove-Item ", "$env:", "kill -9 ", "git -C ", "--force-with-lease", "node -e ",
)
WEIGHTED = ("${", "$(", "'", '"', "<<EOF", "${X", "`")   # the incident class, drawn more often
LONG = "sh -c \"git stash ${X:-$(pwd)} | rm -rf '\" <<EOF\n" * 80   # several KB, unclosed quotes and expansions
EDGE = ["", "${", "$(", "'", '"', "`", "<<EOF", "git ", "env:GIT_DIR", "rm -rf ${", "\n", "${X:?}",
        "$(rm -rf ", "pwsh -Command '", "sh -c \"", "wsl -e ", "\\", LONG]
SUBCOMMANDS = ("commit", "push", "stash", "checkout", "restore", "reset", "clean", "worktree", "branch",
               "rm", "add", "merge", "rebase", "fetch", "pull", "reflog", "status", "log", "show", "tag")
ROLES = ("", guard_core.BUILDER_ROLE, guard_core.AUTHOR_ROLE, guard_core.WRITER_ROLE, guard_core.DESIGNER_ROLE)
TOOLS = ("Bash", "Bash", "Bash", "PowerShell")
BOOL_NAMES = {"background", "agent", "subs_only", "heredoc", "bodies_kept", "failed_cd_stays",
              "shells_only", "legacy", "env_set", "has_agent", "command_position", "follow_cd",
              "predicate_command", "powershell"}
TOKEN_NAMES = {"tokens", "previous"}
PATH_NAMES = {"cwd", "shell_cwd", "root", "where", "folder", "repo", "target", "path"}
WRITE_NAMES = {"writes"}   # the item writes data_tool_judge reads back, as the dispatch passes them
DEFAULT_NAMES = {"watch", "overrides", "spawn_role", "remedies"}   # a shape the dispatch never varies: use the default


def _predicate(path, where, *rest):
    """A write-target predicate that takes the optional command name a predicate_command call adds."""
    return guard.is_settings_file(path, where)


CALLABLES = {"record_branch_of": guard.record_branch_of, "read_verb": guard.read_verb,
             "predicate": _predicate}


def draw_text(rng):
    """A random command string: mostly short, sometimes several hundred characters."""
    limit = rng.randint(0, 400) if rng.random() < 0.1 else rng.randint(0, 60)
    parts, size = [], 0
    while size < limit:
        roll = rng.random()
        if roll < 0.35:
            piece = rng.choice(CHARS)
        elif roll < 0.5:
            piece = rng.choice(WEIGHTED)
        else:
            piece = rng.choice(FRAGMENTS)
        parts.append(piece)
        size += len(piece)
    return "".join(parts)


class Env:
    """The per-call context that is not the command string: tool, folders, session, transcript, role."""

    def __init__(self, rng):
        self.tool = rng.choice(TOOLS)
        self.cwd = rng.choice((RUN, CHECKOUT, CHECKOUT))
        self.session = rng.choice(("", "sess-1"))
        self.transcript = rng.choice((TRANSCRIPT, EMPTY_TRANSCRIPT, MISSING_TRANSCRIPT, ""))
        self.role = rng.choice(ROLES)


def make_payload(rng, env, text, event="PreToolUse"):
    tool_input = {"command": text, "description": text, "file_path": text, "path": text, "content": text,
                  "new_string": text, "old_string": text, "prompt": text, "subagent_type": env.role or "builder",
                  "model": text, "name": text, "run_in_background": rng.random() < 0.5}
    return {"hook_event_name": event, "tool_name": env.tool, "tool_input": tool_input, "cwd": env.cwd,
            "session_id": env.session, "agent_id": rng.choice(("", "agent-1")),
            "agent_transcript_path": env.transcript, "transcript_path": env.transcript}


def tokens_of(text):
    """A segment's tokens, as segment_tokens returns them (the object the guard reads, with its attributes)."""
    found = guard.segment_tokens(text)
    return found if found is not None else guard.segment_tokens("echo")


def value_for(fn, name, param, rng, text, env, state):
    """One argument for a parameter, from its name and annotation. `state` builds shared inputs lazily."""
    annotation = "" if param.annotation is inspect.Parameter.empty else str(param.annotation)
    if fn.__name__ == "rm_var_reason" and name == "hits":
        return guard.rm_var_hits(text, env.cwd)
    if fn.__name__ == "rm_after_cd_reason" and name == "hits":
        return guard.rm_after_cd_hits(text)
    if name in CALLABLES:
        return CALLABLES[name]
    if name == "tool":
        return env.tool
    if name == "role":
        return env.role
    if name in ("session_id", "session"):
        return env.session
    if name == "transcript":
        return env.transcript
    if name == "subcommand":
        return rng.choice(SUBCOMMANDS)
    if name in WRITE_NAMES:
        return guard.data_tool_judge(state("payload")["tool_input"], env.cwd)[1]
    if name == "payload":
        return state("payload")
    if name == "tool_input":
        return state("payload")["tool_input"]
    if name in ("segments", "ends"):
        return state(name)
    if name == "number":
        return rng.randrange(len(state("segments")))
    if name == "before":
        return rng.randint(0, len(text))
    if name == "depth":
        return rng.randint(0, 2)
    if name in BOOL_NAMES or annotation == "bool":
        return rng.random() < 0.5
    if name == "all_tokens":
        return [tokens_of(segment) for segment in state("segments")]
    if name in TOKEN_NAMES:
        return tokens_of(text)
    if name in ("args", "words"):
        return text.split()
    if name in ("names", "writes", "parts"):
        return [text]
    if name in PATH_NAMES:
        return text if rng.random() < 0.3 else env.cwd
    if annotation == "int":
        return rng.randint(0, 3)
    if annotation == "dict":
        return state("payload")
    if annotation == "list":
        return [text]
    return text


def build_kwargs(fn, rng, text, env):
    """The keyword arguments for one call. A parameter with a default is passed half the time."""
    cache = {}

    def state(key):
        if key == "payload":
            if "payload" not in cache:
                cache["payload"] = make_payload(rng, env, text)
            return cache["payload"]
        # judge_shell splits the command once, and `ends` is the list that split fills: one separator per gap.
        if "segments" not in cache:
            ends = []
            segments = guard.split_segments(text, ends)
            if not segments:
                segments, ends = ["echo"], []
            cache["segments"], cache["ends"] = segments, ends
        return cache[key]

    kwargs = {}
    for name, param in inspect.signature(fn).parameters.items():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        if name in DEFAULT_NAMES and param.default is not inspect.Parameter.empty:
            continue
        if param.default is not inspect.Parameter.empty and rng.random() < 0.5:
            continue
        kwargs[name] = value_for(fn, name, param, rng, text, env, state)
    return kwargs


def describe(exc):
    """The exception type, its message, and the innermost frame that raised it."""
    frames = traceback.extract_tb(exc.__traceback__)
    where = " at %s:%d" % (os.path.basename(frames[-1].filename), frames[-1].lineno) if frames else ""
    return "%s: %s%s" % (type(exc).__name__, exc, where)


def run_checks(checks, count):
    """Feed each check its edge inputs and `count` seeded random inputs. Return one row per raising check.

    `checks` is a list of (name, function, mode). Mode "direct" calls the function with keyword
    arguments from build_kwargs; mode "judge" calls guard.judge with a whole payload.
    """
    failures = []
    for name, fn, mode in checks:
        rng = random.Random("%s:%s" % (SEED, name))
        inputs = EDGE + [draw_text(rng) for _ in range(count)]
        bad = []
        for text in inputs:
            env = Env(rng)
            guard_core.POWERSHELL_CALL[0] = env.tool == "PowerShell"
            try:
                if mode == "judge":
                    call = (guard.judge, (make_payload(rng, env, text, rng.choice(
                        ("PreToolUse",) * 9 + ("SubagentStop",))),), {})
                else:
                    call = (fn, (), build_kwargs(fn, rng, text, env))
            except Exception as exc:  # a harness defect, reported as such: never a silent pass
                bad.append((text, "input builder raised " + describe(exc)))
                continue
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    call[0](*call[1], **call[2])
            except SystemExit:
                pass  # a refusal: refuse() exits by design
            except Exception as exc:
                bad.append((text, describe(exc)))
        if bad:
            failures.append((name, len(bad), len(inputs), bad[0][0], bad[0][1]))
    return failures


def report(failures):
    for name, hits, total, first, error in failures:
        print("FAIL %s: %d of %d inputs raised. First input %r raised %s"
              % (name, hits, total, first, error))


def self_test():
    """A check that raises must be reported; a check that refuses must not. Return True when both hold."""
    def raises(text):
        raise ValueError("self-test: a check that raises")

    def refuses(text):
        sys.exit(0)   # the refuse() exit: a refusal, not a raise

    found = {row[0] for row in run_checks([("self-test raises", raises, "direct"),
                                           ("self-test refuses", refuses, "direct")], 20)}
    ok = found == {"self-test raises"}
    print("self-test: %s (a raising check %s, a refusing check %s)"
          % ("ok" if ok else "FAILED", "reported" if "self-test raises" in found else "NOT reported",
             "not reported" if "self-test refuses" not in found else "REPORTED"))
    return ok


def sweep_proof():
    """_test_temp.sweep removes a sibling run folder older than a day and keeps a new one and its own.

    The clock is passed in, so no wall-clock read decides the result.
    """
    temp_root = os.path.join(RUN, "sweep")
    now = 1800000000.0
    old = os.path.join(temp_root, "1-" + "a" * 32)
    new = os.path.join(temp_root, "2-" + "b" * 32)
    own = os.path.join(temp_root, "3-" + "c" * 32)
    for folder in (old, new, own):
        os.makedirs(folder)
    os.utime(old, (now - 2 * 24 * 60 * 60, now - 2 * 24 * 60 * 60))
    os.utime(new, (now, now))
    _test_temp.sweep(temp_root, own, now=now)
    ok = not os.path.exists(old) and os.path.exists(new) and os.path.exists(own)
    print("sweep: %s (an old sibling %s, a new sibling %s, the own folder %s)"
          % ("ok" if ok else "FAILED", "removed" if not os.path.exists(old) else "KEPT",
             "kept" if os.path.exists(new) else "REMOVED", "kept" if os.path.exists(own) else "REMOVED"))
    return ok


def dispatch_callees():
    """The names judge_shell and judge call, read from hooks/guard.py."""
    with open(os.path.join(HERE, "guard.py"), encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename="guard.py")
    bodies = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in DISPATCH}
    if set(bodies) != set(DISPATCH):
        raise SystemExit("hooks/guard.py has no %s: the dispatch moved, so update DISPATCH"
                         % ", ".join(sorted(set(DISPATCH) - set(bodies))))
    names = set()
    for node in bodies.values():
        for call in ast.walk(node):
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
                names.add(call.func.id)
    return names


def guard_function(name):
    """The function a name resolves to, when it is defined in one of the guard modules."""
    try:
        obj = getattr(guard, name)
    except AttributeError:
        return None
    if inspect.isfunction(obj) and obj.__module__ in GUARD_MODULES:
        return obj
    return None


def discover():
    """Return (direct checks by name, names declared outside, undeclared callees)."""
    direct, outside, undeclared = {}, [], []
    for name in sorted(dispatch_callees()):
        if name in OUTSIDE:
            outside.append(name)
            continue
        fn = guard_function(name)
        if fn is not None:
            direct[name] = fn
        elif not hasattr(builtins, name):
            undeclared.append(name)
    return direct, outside, undeclared


def family_list_is_whole():
    """True when every hooks/guard_*.py file other than guard_core is in guard's _FAMILY_MODULES."""
    files = {os.path.splitext(os.path.basename(path))[0] for path in glob.glob(os.path.join(HERE, "guard_*.py"))}
    return files - {"guard_core"} == set(guard._FAMILY_MODULES)


def main():
    started = time.monotonic()
    try:
        if not (self_test() and sweep_proof()):
            return 1
        if not family_list_is_whole():
            print("FAIL the guard_*.py files and guard._FAMILY_MODULES differ: a family module is not fuzzed")
            return 1
        direct, outside, undeclared = discover()
        if undeclared:
            for name in undeclared:
                print("FAIL undeclared dispatch callee %s: fuzz it or declare it in OUTSIDE with a reason" % name)
            return 1
        for required in ("judge_shell", "git_env_command_hit", "kill_hit", "rm_var_hits"):
            if required not in direct:
                print("FAIL %s is not among the discovered checks: the dispatch reading is broken" % required)
                return 1
        checks = [(name, direct[name], "direct") for name in sorted(direct)]
        checks.append(("judge (end to end)", guard.judge, "judge"))
        failures = run_checks(checks, COUNT)
        report(failures)
        elapsed = time.monotonic() - started
        print("checks-never-raise: %d direct checks and judge, %d inputs each (%d random + %d edge), "
              "%d raising, %.1f s"
              % (len(direct), COUNT + len(EDGE), COUNT, len(EDGE), len(failures), elapsed))
        print("not fuzzed directly: %s" % ", ".join("%s (%s)" % (name, OUTSIDE[name]) for name in outside))
        return 1 if failures else 0
    finally:
        shutil.rmtree(RUN, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
