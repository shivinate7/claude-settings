#!/usr/bin/env python3
"""Every deny check on the shell path returns or refuses. None raises.

Decision guard-hooks-fail-closed: a guard that crashes lets the call through. `main()` in
hooks/guard.py catches an exception from `judge` and exits 0, so a raise in a check is a call the
guard let pass.

Run from the repository root:

    python3 hooks/test_checks_never_raise.py

Standard library only. The checks are read from the dispatch in hooks/guard.py: each call that
`judge_shell` and `judge` make, and each hook-module function that those callees call through an
attribute (`question_form.page_item_hit`, for one). A call that resolves to no hook function fails
the run. The tools are the names that `judge` and the functions it reaches compare a tool against.

Each check gets COUNT seeded random command strings per env shape (one stream per check and shape, seed
SEED), built from shell and PowerShell characters, digits and fragments, plus fixed edge inputs. Fragments hold
CONFIG_TOKEN where the config dir's settings path goes, and run_checks swaps in the run folder when it hands an
input to a check, so the drawn text is the same on every run. A share of the inputs opens with a kill of one
pid (`kill <pid>` or `kill -9 <pid>`, the pid 0, 1, -1 or random digits), the act that reaches pid_is_owned. A share
of the payloads holds a well-formed decision item in `data`, and another share holds a workflow step (continue-on-error)
ahead of the text in `content` and `new_string`, with `old_string` empty: the step rides on every tool, not only a Write
or an Edit. Each input carries one tool: two of every three are Bash or PowerShell, the others go round the rest.
A payload carries the keys of every tool's shape, filled with random strings, with typed values where a string reaches
nothing. `judge` gets whole payloads. A refusal is a SystemExit after refuse() prints a
permissionDecision on stdout. Any other exit, and any raise, is a failure.

Isolation: CLAUDE_CONFIG_DIR is a run folder, so guard.log and the override state stay out of the
real config. PATH is an empty folder, so git, gh and ps are absent and every read fails as on a machine
without them. CLAUDE_GUARD_ROOT_PID pins the session root, so a kill reaches its pid read. The checks that
reach the session root (session_root_pid) run a second pass with the pin unset: the walk finds no root, so
foreign_pid_kill takes its no-root return.

Not fuzzed: the parsers of git, gh and ps output. The parent walk of pid_is_owned past its first read
(ps never answers, so it returns at once). The parent walk of session_root_pid past its first read (ps never
answers, so the walk returns 0 at once and its loop over each parent's name never runs). The rest of
in_own_agent_worktree past its first line (ps never answers, so it returns False at once, and its cwd read and
transcript-folder check never run). The rest of foreign_pid_kill past pid_is_owned: _under_init, holds_session_tag
and the refusal after them (pid_is_owned never says False with ps absent). The git-backed commit reads:
own_changes returns None without git, so diff_violation stops before role_offences, and no input here reaches
role_offences.

Env shapes: every check runs twice, under two shapes that the host never sets: both remote variables
unset, and CLAUDE_CODE_REMOTE=true with a session id. The branches that read them (is_cloud,
remote_session_id, and the trust-card check under a session id) run only under the shape that reaches them.
Each shape also runs the session-root checks once more with the root pin unset.

Fixtures: CHECKOUT is a plain folder. PAGE_CHECKOUT is a repository root (a .git folder) whose extras file
names a waiting page, so the item checks and the workflow check run on a real path. CONFIG is also the
pointer checkout: its CLAUDE.md names it, and it holds the role table and an agents folder with one role
file, so the role checks read real files. fixture_proof asserts
that each fixture reaches its check, so a moved key or path fails by name instead of leaving the fuzz blind.

The self-test feeds a raising check, a silent exit and a real refusal through the same harness. A
sweep case proves the shared run-folder sweep (lint/_test_temp.py) removes an old sibling and keeps
a new one.
"""

import ast
import builtins
import contextlib
import glob
import importlib
import inspect
import io
import json
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
COUNT = 1000   # random inputs per check and env shape, on top of the fixed edge inputs below
GUARD = "guard"
DISPATCH = ("judge_shell", "judge")      # the two entry points the guard's PreToolUse hook runs
TOOL_VARIABLES = ("tool", "tool_name")   # the names judge's branches compare a tool by
UNLISTED_TOOL = "mcp__fuzz__unlisted_tool"   # a name no branch lists: the default shape
REQUIRED_CHECKS = ("judge_shell", "git_env_command_hit", "kill_hit", "rm_var_hits", "opus_spawn_hit",
                   "page_item_hit", "is_worktree", "data_tool_judge", "role_write_hit", "shared_tree_match",
                   "trust_card_hit")
REQUIRED_TOOLS = ("Agent", "Task", "Workflow", "Bash", "PowerShell", "Edit", "Write", "ArtifactData",
                  "Artifact", "ArtifactComments", "mcp__github__merge_pull_request",
                  "mcp__claude-code-remote__confirm_repository_trust")
# Hook functions reached by a call but not fuzzed directly, each with the reason. The rest are fuzzed.
OUTSIDE = {
    ("own_session", "own_session_read"): "raises OSError on a transcript that is missing, by design; every caller in "
                                         "guard.py and guard_merge.py reads it inside a try that fails closed, and the "
                                         "direct callers are fuzzed, so a caller that lets the error out is still found",
    ("own_session", "created_sessions"): "raises OSError on a transcript that is missing, by design; its one caller, "
                                         "step_dup_hit, reads it inside a try that fails closed, and that caller is fuzzed",
    ("own_session", "list_sessions_read"): "raises OSError on a transcript that is missing, by design; its one caller, "
                                           "step_dup_hit, reads it inside a try that fails closed, and that caller is fuzzed",
}

RUN = _test_temp.run_folder()
CONFIG = os.path.join(RUN, "config")        # guard.log and override state land here, not in the real config
NO_TOOLS = os.path.join(RUN, "no-tools")    # an empty PATH: git and gh are absent
CHECKOUT = os.path.join(RUN, "checkout")    # a plain folder, not a repository
PAGE_CHECKOUT = os.path.join(RUN, "page-checkout")   # a repository root whose waiting page is PAGE_URL
PAGE_URL = "https://claude.ai/artifact/fuzzpage"
WORKFLOW_TARGET = ".github/workflows/ci.yml"    # a workflow file: guard.workflow_builder_refused judges its edits
WORKFLOW_STEP = ("      - name: test\n"          # a step that runs a test and passes anyway: a builder may not add it
                 "        run: pytest\n"
                 "        continue-on-error: true\n")
REMOTE_ID = "cse_fuzz01"   # the lane id a cloud session names in CLAUDE_CODE_REMOTE_SESSION_ID (override.LANE_ENV)
ROOT_PID = "9999"          # the session root the kill checks read (guard_kill.session_root_pid, the test hook)
ROOT_ENV = "CLAUDE_GUARD_ROOT_PID"   # the env var that pins that root
ROOT_READER = ("guard_kill", "session_root_pid")   # the one read of the root; checks that reach it also run unpinned
TRANSCRIPT = os.path.join(RUN, "transcript.jsonl")
EMPTY_TRANSCRIPT = os.path.join(RUN, "empty.jsonl")
MISSING_TRANSCRIPT = os.path.join(RUN, "missing.jsonl")
SETTINGS_PATH = os.path.join(CONFIG, "settings.json")   # a settings file in the config dir: guard_frozen judges writes to it
for folder in (CONFIG, NO_TOOLS, CHECKOUT, os.path.join(PAGE_CHECKOUT, ".git")):
    os.makedirs(folder)
import layout  # noqa: E402  the one home of the layout and of the waiting-page key (lint/layout.py)
EXTRAS = os.path.join(PAGE_CHECKOUT, *layout.layout()["extras"].split("/"))   # the extras file the page key lives in
os.makedirs(os.path.dirname(EXTRAS))
with open(EXTRAS, "w", encoding="utf-8") as handle:
    json.dump({"kinds": {}, layout.WAITING_PAGE: PAGE_URL}, handle)
with open(TRANSCRIPT, "w", encoding="utf-8") as handle:
    handle.write('{"type": "user", "message": {"role": "user", "content": "hello"}}\n')
open(EMPTY_TRANSCRIPT, "w", encoding="utf-8").close()
os.environ["CLAUDE_CONFIG_DIR"] = CONFIG
os.environ["PATH"] = NO_TOOLS
os.environ[ROOT_ENV] = ROOT_PID

import guard  # noqa: E402  the global PreToolUse guard (hooks/guard.py)
import guard_core  # noqa: E402  the shared code the guard and its families import
import guard_kill  # noqa: E402  the kill checks and the session root (hooks/guard_kill.py)
import guard_shared_tree  # noqa: E402  the shared-tree verbs (hooks/guard_shared_tree.py)
import override  # noqa: E402  the lane id a session env names (hooks/override.py)
import question_form  # noqa: E402  the ArtifactData item shape (hooks/question_form.py)
import shared_names  # noqa: E402  the one home of the markers a spawn shape carries

# The pointer checkout is the config dir: its CLAUDE.md names it (guard_pointer.POINTER_LINE), and it holds the role
# table in the decisions folder and an agents folder with one role file, so role_model_table, role_name and
# role_agent_keys read real files (decision agent-model-cap).
ROLE_TABLE = ("| Role | Model | Effort |\n| --- | --- | --- |\n| builder | opus | high |\n"
              "| reviewer | sonnet | high |\n| Explore | haiku | xhigh |\n")
DECISIONS = os.path.join(CONFIG, *layout.layout()["kinds"]["decisions"]["path"].split("/"))
os.makedirs(os.path.join(CONFIG, "agents"))
os.makedirs(DECISIONS)
with open(os.path.join(CONFIG, "CLAUDE.md"), "w", encoding="utf-8") as handle:
    handle.write("@%s/CLAUDE.md\n" % CONFIG.replace(os.sep, "/"))
with open(os.path.join(DECISIONS, guard.ROLE_TABLE_FILE), "w", encoding="utf-8") as handle:
    handle.write(ROLE_TABLE)
with open(os.path.join(CONFIG, "agents", "builder.md"), "w", encoding="utf-8") as handle:
    handle.write("---\nname: builder\nmodel: opus\n---\n\nThe builder role.\n")

HOOK_MODULES = frozenset(os.path.splitext(name)[0] for name in os.listdir(HERE) if name.endswith(".py"))

CHARS = "${}()[]=;'\"`|&<> \n$-*?0123456789"
CONFIG_TOKEN = "{config}"   # where the config dir's path goes in a drawn fragment; run_checks swaps in CONFIG
SETTINGS_FRAGMENT = CONFIG_TOKEN + os.sep + "settings.json"   # SETTINGS_PATH with the run folder held back
KILL_SHARE = 0.25   # the share of inputs that open with a kill of one pid: the act that reaches pid_is_owned
FRAGMENTS = (
    "git ", "env:GIT_DIR", "rm -rf", "wsl -e", "pwsh -Command", "sh -c", "<<EOF", "$(", "${",
    "${X:?", "git push --force", "git stash", "git worktree remove", "xargs kill", "pgrep x | ",
    "lsof -t", "gh pr merge", "cd ", "&& ", "| ", "'", '"', "`", "\\", "\n", "-Command ",
    "Remove-Item ", "$env:", "kill -9 ", "git -C ", "--force-with-lease", "node -e ",
    "git reset --hard", "git clean -fd", "git checkout -- x", "git restore", "git switch", WORKFLOW_TARGET,
    SETTINGS_FRAGMENT, "> " + SETTINGS_FRAGMENT,
)
WEIGHTED = ("${", "$(", "'", '"', "<<EOF", "${X", "`")   # the incident class, drawn more often
LONG = "sh -c \"git stash ${X:-$(pwd)} | rm -rf '\" <<EOF\n" * 80   # several KB, unclosed quotes and expansions
EDGE = ["", "${", "$(", "'", '"', "`", "<<EOF", "git ", "env:GIT_DIR", "rm -rf ${", "\n", "${X:?}",
        "$(rm -rf ", "pwsh -Command '", "sh -c \"", "wsl -e ", "\\", LONG]
SUBCOMMANDS = ("commit", "push", "stash", "checkout", "restore", "reset", "clean", "worktree", "branch",
               "rm", "add", "merge", "rebase", "fetch", "pull", "reflog", "status", "log", "show", "tag")
ROLES = ("", guard_core.BUILDER_ROLE, guard_core.AUTHOR_ROLE, guard_core.WRITER_ROLE, guard_core.DESIGNER_ROLE)
SPAWN_ROLES = ROLES + ("Explore", "Plan", "design-reviewer", "general-purpose")
SPAWN_MODELS = ("opus", "sonnet", "haiku", "claude-opus-5-5")
GENERIC_ACTIONS = ("publish", "read", "list", "get", "query", "delete", "launch", "set", "update",
                   "str_replace", "batch")
WORKFLOW_SCRIPTS = (   # `@@` takes the random text: an agent call with a model and a role, or the text alone
    'agent("@@", { model: "opus", agentType: "builder" });',
    'agent(`@@`, { model: "sonnet", agentType: "reviewer" });',
    "@@",
)
SHELL_TOOLS = guard_core.SHELL_TOOLS
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


def kill_fragment(rng):
    """`kill <pid>` or `kill -9 <pid>`: a kill of one pid. The pid is 0, 1 or -1, which foreign_pid_kill returns at once
    (-1 reads as a pid only after a signal flag, so `kill -9 -1`), or a random pid that pid_is_owned judges once the
    session root is read. Everything comes from rng, so the draw is the same on every run."""
    pid = rng.choice((0, 1, -1, rng.randint(2, 99999)))
    return rng.choice(("kill ", "kill -9 ")) + str(pid) + rng.choice((" ", "; "))


def draw_text(rng):
    """A random command string: mostly short, sometimes several hundred characters. A share opens with a kill of one pid."""
    limit = rng.randint(0, 400) if rng.random() < 0.1 else rng.randint(0, 60)
    parts, size = [], 0
    if rng.random() < KILL_SHARE:
        parts.append(kill_fragment(rng))
        size = len(parts[0])
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


def decision_item(text):
    """A well-formed decision item whose Goal holds `text`. Its form lines and option effects pass, so each check
    reaches the Departs from line (question_form.departs_hit), whose change side holds no `;`."""
    goal = " ".join(text.split()) or "x"
    return {"kind": "decision",
            "context": "Goal: %s\nProblem (goal): why the owner judges it\nBased on (read): one premise\n"
                       "Departs from: main — adds a check" % goal,
            "options": [{"label": "a", "gain": "saves time", "lose": "one more check"}]}


class Env:
    """The per-call context that is not the command string: tool, folders, session, transcript, role. `template` is
    the drawn text before run_checks swaps the run folder in, so a bound drawn from it does not move with the path."""

    def __init__(self, rng, tool, template):
        self.tool = tool
        self.template = template
        self.cwd = rng.choice((RUN, CHECKOUT, CHECKOUT, PAGE_CHECKOUT, PAGE_CHECKOUT))
        self.session = rng.choice(("", "sess-1"))
        self.transcript = rng.choice((TRANSCRIPT, EMPTY_TRANSCRIPT, MISSING_TRANSCRIPT, ""))
        self.role = rng.choice(ROLES)


def tool_input_for(tool, rng, text, env):
    """The tool_input of one call. It holds the keys every tool's shape reads, each a random string, and the typed
    values a check needs to reach its body: an action, a count, a flag, a list. A tool's own values go on top."""
    tool_input = {
        "command": text, "description": text, "file_path": text, "path": text, "notebook_path": text,
        "content": text, "old_string": text, "new_string": text, "prompt": text, "name": text, "url": text,
        "skill": text, "args": text, "session_id": text, "message": text, "doc_id": text, "device": text,
        "udid": text, "owner": text, "repo": text, "model": text, "collection": text,
        "subagent_type": env.role or "builder", "data": {"question": text, "options": [text]},
        "action": rng.choice(GENERIC_ACTIONS), "script": rng.choice(WORKFLOW_SCRIPTS).replace("@@", text),
        "run_in_background": rng.random() < 0.5, "asset": rng.random() < 0.3, "draft": rng.random() < 0.5,
        "pullNumber": rng.randint(0, 3),
        "writes": [{"op": rng.choice(question_form.ITEM_OPS), "collection": question_form.WAITING_ITEMS,
                    "doc_id": text, "data": {"question": text}}],
    }
    if tool == guard.DATA_TOOL:
        tool_input["action"] = rng.choice(question_form.ITEM_OPS + ("batch",))
        tool_input["collection"] = question_form.WAITING_ITEMS if rng.random() < 0.8 else text
    if tool in guard.SPAWN_TOOLS:
        tool_input["model"] = rng.choice(SPAWN_MODELS + (text,))
        tool_input["subagent_type"] = rng.choice(SPAWN_ROLES + (text,))
        tool_input["prompt"] = rng.choice((text, shared_names.EXPLORE_AUDIT_MARKER + "\n" + text))
    # Typed values for the waiting-page item checks: the page's link, the item collection and op, an option list.
    tool_input["url"] = rng.choice((text, PAGE_URL))
    if rng.random() < 0.5:
        tool_input["collection"] = question_form.WAITING_ITEMS
        tool_input["action"] = rng.choice(question_form.ITEM_OPS)
    if rng.random() < 0.5:
        tool_input["data"] = {"question": text, "options": [{"key": rng.choice(("a", "b", "none")), "label": text}]}
    if rng.random() < 0.3:   # a well-formed decision item: the form passes, so the checks past the form run
        tool_input["data"] = decision_item(text)
    if rng.random() < 0.3:   # a Write or an Edit that adds a workflow step: the old text is empty, the new holds it
        tool_input["old_string"] = ""
        tool_input["content"] = tool_input["new_string"] = WORKFLOW_STEP + text
    return tool_input


def make_payload(rng, env, text, event="PreToolUse"):
    return {"hook_event_name": event, "tool_name": env.tool, "tool_input": tool_input_for(env.tool, rng, text, env),
            "cwd": env.cwd, "session_id": env.session, "agent_id": rng.choice(("", "agent-1")),
            "agent_type": env.role, "agent_transcript_path": env.transcript, "transcript_path": env.transcript}


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
    if fn.__name__ == "role_write_hit" and name == "target":   # a builder's workflow edit reaches the workflow check
        return rng.choice((WORKFLOW_TARGET, text, env.cwd))
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
        return rng.randint(0, len(env.template))
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


def refusal_printed(stdout):
    """True when stdout holds a refusal: a JSON line whose hookSpecificOutput carries permissionDecision,
    which refuse() prints (hooks/guard_core.py)."""
    for line in stdout.splitlines():
        try:
            found = json.loads(line)
        except ValueError:
            continue
        hook = found.get("hookSpecificOutput") if isinstance(found, dict) else None
        if isinstance(hook, dict) and "permissionDecision" in hook:
            return True
    return False


def tool_for(index, shells, others):
    """The tool an input carries. Two of every three inputs carry a shell tool, the incident class; the third goes
    round the other tools, so each of them still gets inputs in every check."""
    if index % 3 != 2:
        return shells[index % len(shells)]
    return others[(index // 3) % len(others)]


def run_checks(checks, count, tools, shape=""):
    """Feed each check its edge inputs and `count` seeded random inputs. Return one row per failing check.

    `checks` is a list of (label, function, mode). Mode "direct" calls the function with keyword arguments from
    build_kwargs; mode "judge" calls guard.judge with a whole payload. A row is (label, failed, total, tools
    that failed, (first input, its tool, its error)). The caller pins the env shape `shape` names; the streams
    differ per shape, so each shape reads its own inputs.
    """
    shells = [tool for tool in tools if tool in SHELL_TOOLS]
    others = [tool for tool in tools if tool not in SHELL_TOOLS]
    failures = []
    for label, fn, mode in checks:
        rng = random.Random("%s:%s:%s" % (SEED, shape, label))
        inputs = EDGE + [draw_text(rng) for _ in range(count)]
        bad = []
        for index, drawn in enumerate(inputs):
            text = drawn.replace(CONFIG_TOKEN, CONFIG)   # the run folder enters here only, so the draws match on every run
            tool = tool_for(index, shells, others)
            env = Env(rng, tool, drawn)
            guard_core.POWERSHELL_CALL[0] = tool == "PowerShell"
            try:
                if mode == "judge":
                    call = (guard.judge, (make_payload(rng, env, text, rng.choice(
                        ("PreToolUse",) * 9 + ("SubagentStop",))),), {})
                else:
                    call = (fn, (), build_kwargs(fn, rng, text, env))
            except Exception as exc:  # a harness defect, reported as such: never a silent pass
                bad.append((drawn, tool, "input builder raised " + describe(exc)))
                continue
            out = io.StringIO()
            try:
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                    call[0](*call[1], **call[2])
            except SystemExit as exc:
                if not refusal_printed(out.getvalue()):
                    bad.append((drawn, tool, "exit %r with no refusal on stdout" % (exc.code,)))
            except Exception as exc:
                bad.append((drawn, tool, describe(exc)))
        if bad:
            failures.append((label, len(bad), len(inputs), sorted({row[1] for row in bad}), bad[0]))
    return failures


def report(failures, shape):
    for label, hits, total, tools, (first, first_tool, error) in failures:
        print("FAIL [%s] %s: %d of %d inputs failed, tools %s. First input %r with tool %s: %s"
              % (shape, label, hits, total, ", ".join(tools), first[:80], first_tool, error))


def self_test():
    """A raising check and a silent exit must be reported; a real refusal must not. Return True when all hold."""
    def raises(text):
        raise ValueError("self-test: a check that raises")

    def exits_silently(text):
        sys.exit(0)

    def refuses(text):
        guard_core.refuse("Bash", "deny", "self-test", "a refusal the self-test makes", "self-test")

    found = {row[0] for row in run_checks([("self-test raises", raises, "direct"),
                                           ("self-test exits silently", exits_silently, "direct"),
                                           ("self-test refuses", refuses, "direct")], 20, ["Bash", "Agent"])}
    ok = found == {"self-test raises", "self-test exits silently"}
    print("self-test: %s (a raising check %s, a silent exit %s, a real refusal %s)"
          % ("ok" if ok else "FAILED", "reported" if "self-test raises" in found else "NOT reported",
             "reported" if "self-test exits silently" in found else "NOT reported",
             "reported" if "self-test refuses" in found else "not reported"))
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


# ------------------------------------------------------------------ the env shapes and the fixtures

REMOTE_VARS = ("CLAUDE_CODE_REMOTE", "CLAUDE_CODE_REMOTE_SESSION_ID")   # read by is_cloud and remote_session_id
SHAPES = (   # (name, values of REMOTE_VARS; a variable not listed is unset)
    ("remote unset", {}),
    ("remote set with a session id", {"CLAUDE_CODE_REMOTE": "true", "CLAUDE_CODE_REMOTE_SESSION_ID": REMOTE_ID}),
)


@contextlib.contextmanager
def pinned_env(values):
    """Set REMOTE_VARS to `values`, unset the rest, and restore the prior values on exit, so no host value reaches a check."""
    before = {name: os.environ.get(name) for name in REMOTE_VARS}
    for name in REMOTE_VARS:
        if name in values:
            os.environ[name] = values[name]
        else:
            os.environ.pop(name, None)
    try:
        yield
    finally:
        for name, value in before.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


@contextlib.contextmanager
def root_unpinned():
    """Unset ROOT_ENV, so session_root_pid walks the process tree. With ps absent the walk finds no root and reads 0."""
    before = os.environ.pop(ROOT_ENV, None)
    try:
        yield
    finally:
        if before is not None:
            os.environ[ROOT_ENV] = before


def calls_pid_is_owned(run):
    """True when `run()` calls guard_kill.pid_is_owned. The real function still answers, and the wrap is undone on exit."""
    calls, real = [], guard_kill.pid_is_owned

    def recording(pid, root):
        calls.append(pid)
        return real(pid, root)

    guard_kill.pid_is_owned = recording
    try:
        run()
    finally:
        guard_kill.pid_is_owned = real
    return bool(calls)


def _probe(problems, cause, probe):
    """Run one reach probe. A False result or a raise is a problem named by `cause`: a raise is the check failing, so
    it is reported here and the fuzz still runs."""
    try:
        if not probe():
            problems.append(cause)
    except Exception as exc:
        problems.append("%s; the probe raised %s" % (cause, describe(exc)))


def fixture_proof():
    """[problem] for each fixture that fails to reach the check it exists for. Each problem names its cause, so a
    moved key, path or env read fails here rather than leaving the fuzz green and blind."""
    problems = []
    _probe(problems, "PAGE_CHECKOUT is not its repository's waiting page (the .git folder or the extras key moved)",
           lambda: question_form.is_waiting_page({"url": PAGE_URL}, PAGE_CHECKOUT))
    _probe(problems, "WORKFLOW_TARGET under PAGE_CHECKOUT is no workflow path (the repo root or WORKFLOW_REL moved)",
           lambda: guard.is_workflow_rel(guard.repo_rel(WORKFLOW_TARGET, PAGE_CHECKOUT) or ""))
    _probe(problems, "'git reset --hard' no longer reads as a discarding call (the shared-tree reading moved)",
           lambda: bool(guard_shared_tree.shared_tree_match("git reset --hard")))
    expected = override.LANE_PREFIX + REMOTE_ID[len(override.LANE_ENV_PREFIX):]
    with pinned_env(SHAPES[0][1]):
        _probe(problems, "remote unset, yet remote_session_id() names a session (the session env read moved)",
               lambda: override.remote_session_id() is None)
        _probe(problems, "remote unset, yet is_cloud() is true (the CLAUDE_CODE_REMOTE read moved)",
               lambda: not guard_core.is_cloud())
    with pinned_env(SHAPES[1][1]):
        _probe(problems, "remote set, yet remote_session_id() names no session (the session env read moved)",
               lambda: override.remote_session_id() == expected)
        _probe(problems, "CLAUDE_CODE_REMOTE=true, yet is_cloud() is false (the CLAUDE_CODE_REMOTE read moved)",
               guard_core.is_cloud)
    _probe(problems, "CLAUDE_GUARD_ROOT_PID is pinned, yet session_root_pid() reads no root (the root hook moved)",
           lambda: guard_kill.session_root_pid() == int(ROOT_PID))
    with root_unpinned():
        _probe(problems, "CLAUDE_GUARD_ROOT_PID is unset, yet session_root_pid() reads a root with ps absent (the walk "
                         "moved): the no-root return of foreign_pid_kill is not reached",
               lambda: guard_kill.session_root_pid() == 0)
    _probe(problems, "a kill of one pid under the pinned root does not reach pid_is_owned (the kill path of "
                     "foreign_pid_kill moved, or the root read did)",
           lambda: calls_pid_is_owned(lambda: guard_kill.foreign_pid_kill(tokens_of("kill 4242"))))
    _probe(problems, "a drawn fragment holds the run folder's name, so the drawn inputs differ on each run "
                     "(CONFIG_TOKEN moved, or a fragment takes RUN)",
           lambda: not any(os.path.basename(RUN) in piece for piece in [*FRAGMENTS, *CHARS, *WEIGHTED, *EDGE]))
    _probe(problems, "CONFIG's CLAUDE.md names no pointer checkout (POINTER_LINE or the config dir moved)",
           lambda: guard.pointer_checkout() == os.path.normcase(os.path.realpath(CONFIG)))
    _probe(problems, "CONFIG's decisions folder holds no builder row (the layout decisions path or ROLE_TABLE_FILE moved)",
           lambda: (guard.role_model_table(CONFIG) or {}).get("builder") == "opus")
    _probe(problems, "CONFIG's agents folder yields no builder role (role_agent_keys or the agents folder moved)",
           lambda: any(keys.get("name") == "builder" for keys in guard.role_agent_keys(CONFIG)))
    _probe(problems, "the decision item's form lines refuse it, so the Departs from check never runs (the form moved)",
           lambda: question_form._lines_hit(decision_item("x")["context"]) == question_form.PASS)
    _probe(problems, "WORKFLOW_STEP's continue-on-error line is no disabling step (WORKFLOW_DISABLE_STEP moved)",
           lambda: guard.workflow_step_disables("        continue-on-error: true"))
    _probe(problems, "SETTINGS_PATH is no settings file (the settings basenames moved)",
           lambda: guard.is_settings_file(SETTINGS_PATH, CONFIG))
    return problems


# ------------------------------------------------------------------ the dispatch, read from the AST

_TREES, _SYMBOLS = {}, {}


def _tree(module):
    if module not in _TREES:
        with open(os.path.join(HERE, module + ".py"), encoding="utf-8") as handle:
            _TREES[module] = ast.parse(handle.read(), filename=module + ".py")
    return _TREES[module]


def _top_level(statements):
    """Each statement that runs at module level. The body of an if, try, while or with counts; a def or class does not."""
    for statement in statements:
        yield statement
        if isinstance(statement, (ast.FunctionDef, ast.ClassDef)):
            continue
        for field in ("body", "orelse", "finalbody"):
            yield from _top_level(getattr(statement, field, None) or [])
        for handler in getattr(statement, "handlers", None) or []:
            yield from _top_level(handler.body)


def _symbols(module):
    """(defined, imported) for a hook module. `defined` maps each module-level def or assigned name to its node.
    `imported` maps each name a hook-module import binds to (module, name), or (module, None) for a module.
    Imports inside a function count too, as the dispatch reads the whole file."""
    if module not in _SYMBOLS:
        tree = _tree(module)
        defined, imported = {}, {}
        for node in _top_level(tree.body):
            if isinstance(node, ast.FunctionDef):
                defined[node.name] = node
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        defined[target.id] = node
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                defined[node.target.id] = node
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module in HOOK_MODULES:
                for alias in node.names:
                    imported[alias.asname or alias.name] = (node.module, alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in HOOK_MODULES:
                        imported[alias.asname or alias.name] = (alias.name, None)
        _SYMBOLS[module] = (defined, imported)
    return _SYMBOLS[module]


def _locate(module, name, depth=0):
    """(module, name) where a hook module defines `name`, following imports between hook modules. None when it defines none."""
    defined, imported = _symbols(module)
    if name in defined:
        return module, name
    if name in imported and imported[name][1] is not None and depth < 8:
        source, source_name = imported[name]
        return _locate(source, source_name, depth + 1)
    return None


def _function_node(module, name):
    """The FunctionDef a hook module defines under `name`, or None."""
    node = _symbols(module)[0].get(name)
    return node if isinstance(node, ast.FunctionDef) else None


def _resolved(module, name):
    """(module, name) of the hook function `name` names in `module`, or None."""
    hit = _locate(module, name)
    return hit if hit and _function_node(*hit) is not None else None


def _edges(module, node, attributes_only=False):
    """(found, missing): the hook functions a body calls, as (module, name), and the calls that resolve to none.

    A Name call resolves through the module's defs and imports. It is skipped when it is a builtin or a def the body
    nests. An attribute call resolves only when its base is an imported hook module. `attributes_only` keeps the
    Name calls out."""
    imported = _symbols(module)[1]
    nested = {n.name for n in ast.walk(node) if isinstance(n, ast.FunctionDef) and n is not node}
    found, missing = [], []
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        if isinstance(func, ast.Name) and not attributes_only:
            if func.id in nested or hasattr(builtins, func.id):
                continue
            hit = _resolved(module, func.id)
            if hit:
                found.append(hit)
            else:
                missing.append(func.id)
        elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            source = imported.get(func.value.id, (None, None))
            if source[0] is not None and source[1] is None:
                hit = _resolved(source[0], func.attr)
                if hit:
                    found.append(hit)
                else:
                    missing.append(source[0] + "." + func.attr)
    return found, missing


def dispatch():
    """(direct, reads, missing, outside), read from hooks/guard.py.

    direct: the (module, name) keys the fuzz runs directly. They are judge_shell, each call judge and judge_shell
    make, and each hook-module function those callees call through an attribute. judge itself is the end-to-end check.
    reads: every hook function judge and judge_shell reach, read only, for the tool names.
    missing: each call in direct or in the reads that resolves to nothing hook-side.
    outside: the direct keys OUTSIDE declares, with the reason.
    """
    judge_key, shell_key = (GUARD, "judge"), (GUARD, "judge_shell")
    direct, missing = {shell_key: _function_node(*shell_key)}, []
    for key in (judge_key, shell_key):
        found, gone = _edges(key[0], _function_node(*key))
        missing.extend(gone)
        for callee in found:
            direct.setdefault(callee, _function_node(*callee))
    for key in list(direct):
        found, gone = _edges(key[0], direct[key], attributes_only=True)
        missing.extend(gone)
        for hook in found:
            direct.setdefault(hook, _function_node(*hook))
    direct.pop(judge_key, None)
    outside = {key: OUTSIDE[key] for key in OUTSIDE if key in direct}
    for key in outside:
        del direct[key]
    reads, queue = set(), [judge_key, shell_key]
    while queue:
        key = queue.pop()
        if key not in reads:
            reads.add(key)
            queue.extend(_edges(key[0], _function_node(*key))[0])
    return set(direct), reads, missing, outside


def reaches(key, target):
    """True when the hook function `key` calls `target`, directly or through the hook functions it calls."""
    queue, seen = [key], set()
    while queue:
        node = queue.pop()
        if node == target:
            return True
        if node not in seen:
            seen.add(node)
            queue.extend(_edges(node[0], _function_node(*node))[0])
    return False


def _callable(key):
    module, name = key
    return getattr(importlib.import_module(module), name)


def _strings_of(value):
    if isinstance(value, str):
        return {value} if value else set()
    if isinstance(value, (tuple, list, set, frozenset)):
        return {item for item in value if isinstance(item, str) and item}
    return set()


def _tool_strings(module, node):
    """The tool names one side of a comparison names: a string literal, a tuple of them, or a constant that holds them."""
    if isinstance(node, ast.Constant):
        return _strings_of(node.value)
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        names = set()
        for element in node.elts:
            names |= _tool_strings(module, element)
        return names
    if isinstance(node, ast.Name) and node.id not in TOOL_VARIABLES:
        hit = _locate(module, node.id)
        if hit:
            return _strings_of(getattr(importlib.import_module(hit[0]), hit[1], None))
    return set()


def _is_tool_name(name):
    """Claude Code tool names are capitalized (Bash, ArtifactData) or mcp__ names. A lowercase word that a comparison
    to a tool variable names is a shell program or a stream verb (npm, tail), not a tool."""
    return name[:1].isupper() or name.startswith("mcp__")


def tool_names(reads):
    """Every tool name a comparison against a tool variable names, in the functions judge reaches."""
    names = set()
    for module, name in reads:
        for node in ast.walk(_function_node(module, name)):
            if isinstance(node, ast.Compare):
                sides = [node.left, *node.comparators]
                if any(isinstance(side, ast.Name) and side.id in TOOL_VARIABLES for side in sides):
                    for side in sides:
                        names |= {tool for tool in _tool_strings(module, side) if _is_tool_name(tool)}
    return names


def family_list_is_whole():
    """True when every hooks/guard_*.py file other than guard_core is in guard's _FAMILY_MODULES."""
    files = {os.path.splitext(os.path.basename(path))[0] for path in glob.glob(os.path.join(HERE, "guard_*.py"))}
    return files - {"guard_core"} == set(guard._FAMILY_MODULES)


def main():
    started = time.monotonic()
    try:
        with pinned_env(SHAPES[0][1]):
            if not (self_test() and sweep_proof()):
                return 1
        problems = fixture_proof()
        for problem in problems:
            print("FAIL fixture: %s" % problem)   # the fuzz still runs, so each family's own rows show too
        if not family_list_is_whole():
            print("FAIL the guard_*.py files and guard._FAMILY_MODULES differ: a family module is not fuzzed")
            return 1
        direct, reads, missing, outside = dispatch()
        for name in missing:
            print("FAIL undeclared dispatch callee %s: it resolves to no hook function. Fix the dispatch reading or the "
                  "hook it names." % name)
        if missing:
            return 1
        names = {name for _, name in direct}
        for required in REQUIRED_CHECKS:
            if required not in names:
                print("FAIL %s is not among the discovered checks: the dispatch reading is broken" % required)
                return 1
        tools = sorted(tool_names(reads) | {UNLISTED_TOOL})
        for required in REQUIRED_TOOLS:
            if required not in tools:
                print("FAIL tool %s is not among the discovered tools: the branch reading is broken" % required)
                return 1
        keyed = [(key, "%s.%s" % key, _callable(key), "direct") for key in sorted(direct)]
        keyed.append(((GUARD, "judge"), "judge (end to end)", guard.judge, "judge"))
        checks = [check[1:] for check in keyed]
        root_checks = [check[1:] for check in keyed if reaches(check[0], ROOT_READER)]
        if not root_checks:
            print("FAIL no check reaches %s.%s: the root reading is broken" % ROOT_READER)
            return 1
        failing = 0
        for shape, values in SHAPES:
            with pinned_env(values):
                failures = run_checks(checks, COUNT, tools, shape)
                report(failures, shape)
                failing += len(failures)
                with root_unpinned():
                    unpinned = shape + ", root unpinned"
                    failures = run_checks(root_checks, COUNT, tools, unpinned)
                report(failures, unpinned)
                failing += len(failures)
        elapsed = time.monotonic() - started
        print("checks-never-raise: %d direct checks and judge, %d tools, %d env shapes, %d root-reading checks also run "
              "with the root unpinned, %d inputs each per pass (%d random + %d edge), %d failing rows, %.1f s"
              % (len(direct), len(tools), len(SHAPES), len(root_checks), COUNT + len(EDGE), COUNT, len(EDGE),
                 failing, elapsed))
        print("not fuzzed directly: %s" % ", ".join("%s.%s (%s)" % (key[0], key[1], why)
                                                  for key, why in sorted(outside.items())))
        return 1 if failing or problems else 0
    finally:
        shutil.rmtree(RUN, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
