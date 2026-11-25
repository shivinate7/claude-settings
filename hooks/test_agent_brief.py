#!/usr/bin/env python3
"""Cases for hooks/agent_brief.py, a SubagentStart hook. Standard library only, plus hooks/guard.py,
which reads the agent frontmatter.

Run it from the repository root:

    python hooks/test_agent_brief.py

Contract (the hook's own docstring). On each agent start
the hook prints one JSON object on stdout and exits 0:
    {"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": "<text>"}}
- additionalContext holds the standing rules: a scope line that follows `agent_type` from the hook
  input (builder, test-author, reviewer, Explore, record-writer, designer, design-reviewer, refuter), the general scope
  line for any other or missing type, and fewer than 20 lines in all. Each scope line is pinned in full.
  The two standing git lines are pinned in full, and they are the same for every type. One bans git stash, with no
  worktree condition. The other bans git reset with one of the discard flags in RESET_DISCARD_FLAGS (guard_shared_tree),
  git checkout of a path and git restore, only outside the agent's own worktree: a folder under .claude/worktrees
  (guard.agent_owned_worktree). The guard allows those discarding acts only in such a worktree, and refuses them in the
  main checkout and in a hand-made worktree (decision agent-worktree-discard-is-noted). A plain, soft or mixed reset is not named.
- The push line, the commit-trailer line and the record-path line appear for builder,
  test-author, record-writer, designer and any other type; never for reviewer, Explore, Plan,
  claude-code-guide, design-reviewer or refuter, which only read.
- The staged-diff line holds `git diff --cached --stat`. It appears once for each type that
  commits (builder, test-author, record-writer, designer and any other type) and never for a
  read-only type. Decision lanes-start-in-tool-worktrees.
- A plugin-namespaced type (`my-plugin:builder`) gets the scope of its bare name. The match ignores
  case: `Builder` and `explore` get the scope and the line set of their role.
- When the payload's cwd holds a .github/stamp.json whose cite.form is set, one brief line
  carries the form of every kind, in kind order. A cite.pattern with no cite.form adds no line.
- Each note rule that check_record_slugs.AGENT_FORM_RULES holds reaches every type's context, rendered
  with the note folder and the old notes file from lint/layout.py. The note form sits on one line, and the
  old notes file line says it takes deletes only. A changed or added rule in that list reaches the brief
  with no edit to the hook.
- Junk or empty stdin, or an internal error: no output on stdout, exit 0, and at most one stderr
  line that starts `agent_brief:`. The hook fails open.

Interface (Claude Code hooks reference, SubagentStart): stdin is one JSON object with
`hook_event_name` "SubagentStart", `agent_id`, and `agent_type`.

Override the module under test with the env var AGENT_BRIEF_UNDER_TEST.
"""
import json
import os
import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.environ.get("AGENT_BRIEF_UNDER_TEST") or os.path.join(HERE, "agent_brief.py")
sys.path.insert(0, HERE)
import guard  # noqa: E402  the one reader of agent frontmatter keys (guard.frontmatter_keys), not a copy of it here
import guard_core  # noqa: E402  the one home of the refuter role's name (REFUTER_ROLE), read below and never typed here
import guard_shared_tree  # noqa: E402  the one home of the discard flags (RESET_DISCARD_FLAGS), read below and never typed here
from tool_lists_test import tokens, unread_list  # noqa: E402  the one reader of tool lists (hooks/tool_lists_test.py)
sys.path.append(os.path.join(os.path.dirname(HERE), "lint"))  # appended: a module already in sys.modules wins
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)

CWD = "/tmp/agent-brief-test"
MISSING = object()  # payload() leaves agent_type out of the JSON when this is passed
# A guard_core with no REFUTER_ROLE reads as REFUTER_MISSING: each case that names the role then fails on the missing
# name, and refuter_name_check says so in words, never by a crash at import.
REFUTER_MISSING = "<no REFUTER_ROLE in guard_core>"
REFUTER = getattr(guard_core, "REFUTER_ROLE", REFUTER_MISSING)
TYPES = ["builder", "test-author", "reviewer", "Explore", "record-writer", "designer", "design-reviewer", REFUTER]

# Full scope line per type, pinned verbatim. Edit here only when the hook's text changes on purpose.
SCOPE_LINE = {
    "builder": "- Scope: builder. Never edit tests or test config. A mutant goes to a test-author. Report a test change you need.",
    "test-author": "- Scope: test-author. Edit tests and test config only. Never edit product code.",
    "reviewer": "- Scope: reviewer. Never edit, write, stage, commit, or push. Read and run checks only.",
    "Explore": "- Scope: Explore. Never edit. Read and search only.",
    "record-writer": "- Scope: record-writer. Edit Markdown (*.md) files only. Report any other change needed.",
    "designer": "- Scope: designer. Edit files in the repo's design folder only. Report any other change needed. "
                "Your brief names your designer kind: blind, informed or directed. In a blind designer, never read "
                "the current screen, its code, its screenshots, its mockups, or the repo's design spec and tokens.",
    "design-reviewer": "- Scope: design-reviewer. Never edit, write, stage, commit, or push. Read and render only.",
    REFUTER: "- Scope: %s. Never edit, write, stage, commit, or push. Read only." % REFUTER,
}
GENERAL_LINE = ("- Scope: do only what your brief names. A builder never edits tests; "
                "a test-author never edits product code; a reviewer and Explore never edit; "
                "a record-writer edits Markdown only.")


def standing_git_lines(flags):
    """The two standing git lines for the discard flags `flags`. The stash ban holds for every type. The reset ban,
    with a checkout of a path and a restore, holds only outside the agent's own worktree, a folder under .claude/worktrees."""
    return [
        "- Never run git stash.",
        "- Outside your own agent worktree (a folder under .claude/worktrees), never run git reset with one of the flags %s, git checkout of a path, or git restore." % "/".join(flags),
    ]


STASH_LINE, RESET_LINE = standing_git_lines(guard_shared_tree.RESET_DISCARD_FLAGS)  # the flags come from the constant, never typed here
STAGED_KEY = "git diff --cached --stat"  # the stable fragment of the staged-diff line; the wording may change
# Non-scope lines in hook order, after the scope line. Builder, test-author, record-writer, designer and any
# unknown type commit and push; reviewer, Explore, Plan, claude-code-guide and design-reviewer do not, so they
# get the shorter set. The staged-diff line is not in this list: line_set_check(staged=True) leaves it out.
WRITER_RULES = [
    "Standing rules for this agent:",
    STASH_LINE,
    RESET_LINE,
    "- Push only with: git push origin HEAD:<branch>.",
    "- Make no gh call unless your brief names it.",
    "- Report in 25 lines or fewer unless the brief sets a cap. Order: Done, Deviations, Input Needed, Next.",
    "- End each commit message with: Co-Authored-By: <model> <noreply@anthropic.com>",
    "- Name no record path in a commit message. The only exception is the Drops-lines: trailer.",
    "- Before you end, stop each server you started, by the $! from the same call or through the harness.",
]
READER_RULES = [
    "Standing rules for this agent:",
    STASH_LINE,
    RESET_LINE,
    "- Make no gh call unless your brief names it.",
    "- Report in 25 lines or fewer unless the brief sets a cap. Order: Done, Deviations, Input Needed, Next.",
]
PUSH_KEY = "Push only with"
TRAILER_KEY = "End each commit message with"
RECORD_KEY = "Name no record path"
INJECT_ERROR = (  # runs the hook with json.loads and json.dumps raising, to force an internal error
    "import json, runpy, sys\n"
    "def boom(*args, **kwargs):\n"
    "    raise RuntimeError('injected by test_agent_brief')\n"
    "json.loads = boom\n"
    "json.dumps = boom\n"
    "sys.argv = sys.argv[1:]\n"
    "runpy.run_path(sys.argv[0], run_name='__main__')\n"
)

CASES = []


def payload(agent_type=MISSING, cwd=CWD):
    """One SubagentStart payload, shaped as the docs: session_id, transcript_path, cwd,
    permission_mode, hook_event_name, agent_id, agent_type. `agent_type` MISSING drops the key."""
    body = {
        "session_id": "abc123",
        "transcript_path": cwd + "/transcript.jsonl",
        "cwd": cwd,
        "permission_mode": "default",
        "hook_event_name": "SubagentStart",
        "agent_id": "a1b2c3",
    }
    if agent_type is not MISSING:
        body["agent_type"] = agent_type
    return json.dumps(body)


def run(stdin_text):
    """Return (rc, stdout, stderr) for one run of the hook, or None when the hook file is absent."""
    if not os.path.exists(HOOK):
        return None
    result = subprocess.run([sys.executable, HOOK], input=stdin_text, capture_output=True,
                            encoding="utf-8", timeout=30)
    return result.returncode, result.stdout, result.stderr


def context_of(out):
    """Return (additionalContext, None) when stdout is the documented one-line object, else
    (None, problem)."""
    if len(out.strip().splitlines()) != 1:
        return None, "expected one line of JSON, got %d lines" % len(out.strip().splitlines())
    try:
        parsed = json.loads(out)
    except ValueError:
        return None, "expected one JSON object, got %r" % out[:120]
    if not isinstance(parsed, dict) or set(parsed) != {"hookSpecificOutput"}:
        return None, "top-level keys are %r, want only hookSpecificOutput" % (
            sorted(parsed) if isinstance(parsed, dict) else type(parsed).__name__)
    block = parsed["hookSpecificOutput"]
    if not isinstance(block, dict) or set(block) != {"hookEventName", "additionalContext"}:
        return None, "hookSpecificOutput keys are %r" % (
            sorted(block) if isinstance(block, dict) else type(block).__name__)
    if block["hookEventName"] != "SubagentStart":
        return None, "hookEventName is %r" % block["hookEventName"]
    text = block["additionalContext"]
    if not isinstance(text, str) or not text.strip():
        return None, "additionalContext is empty or not a string"
    return text, None


def context_for(stdin_text):
    """Run the hook and return (additionalContext, None), or (None, problem)."""
    got = run(stdin_text)
    if got is None:
        return None, "the hook file is missing: %s" % HOOK
    rc, out, err = got
    if rc != 0:
        return None, "exit %d: %s" % (rc, err.strip()[:120])
    return context_of(out)


RUN_FOLDER = None  # made on the first request of the run, so an import leaks no folder (test-temp-standard)


def repo_tree(extras=None, config=None):
    """A repo-shaped folder in this run's folder: its layout extras file when `extras` is text, its .github/stamp.json
    when `config` is a dict. The hook reads both through the payload's cwd. main() removes the run folder."""
    global RUN_FOLDER
    if RUN_FOLDER is None:
        RUN_FOLDER = _test_temp.run_folder()
    root = tempfile.mkdtemp(prefix="brief-tree-", dir=RUN_FOLDER)
    if extras is not None:
        write_under(root, ".claude/layout-extras.json", extras)
    if config is not None:
        write_under(root, ".github/stamp.json", json.dumps(config))
    return root


def write_under(root, rel, text):
    """Write `text` to `rel` under `root`, making its folders."""
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def brief_in(root, agent_type="builder"):
    """Run the hook with `root` as the payload's cwd. Return (additionalContext, None), or (None, problem)."""
    return context_for(payload(agent_type, cwd=root))


def has_line(text, *parts):
    """True when one line of text holds every part, in the order given."""
    for line in text.split("\n"):
        pos = 0
        for part in parts:
            pos = line.find(part, pos)
            if pos < 0:
                break
            pos += len(part)
        else:
            return True
    return False


def scope_lines(text):
    return [line for line in text.split("\n") if line.startswith("- Scope")]


def scope_check(expected):
    """Build a check: exactly one scope line, and it equals the pinned line for `expected`.
    Any key not in SCOPE_LINE (such as "general") pins GENERAL_LINE."""
    want = SCOPE_LINE.get(expected, GENERAL_LINE)

    def check(text):
        scopes = scope_lines(text)
        if len(scopes) != 1:
            return "want one scope line, got %d" % len(scopes)
        if scopes[0] != want:
            return "scope line is %r, want %r" % (scopes[0][:120], want[:120])
        return None
    return check


def builder_scope_check(*parts, lacks=()):
    """Build a check: exactly one scope line, and it holds every part and none of `lacks`, case-insensitively."""
    def check(text):
        scopes = scope_lines(text)
        if len(scopes) != 1:
            return "want one scope line, got %d" % len(scopes)
        low = scopes[0].lower()
        for part in parts:
            if part not in low:
                return "scope line lacks %r: %r" % (part, scopes[0][:120])
        for part in lacks:
            if part in low:
                return "scope line holds %r: %r" % (part, scopes[0][:120])
        return None
    return check


def brief_lines_check(present):
    """Build a check: the push, trailer and record-path lines are all there (present=True), or
    none of them is (present=False)."""
    def check(text):
        for key in (PUSH_KEY, TRAILER_KEY, RECORD_KEY):
            found = [line for line in text.split("\n") if key in line]
            if present and not found:
                return "no line holds %r" % key
            if not present and found:
                return "a line holds %r: %r" % (key, found[0][:90])
        return None
    return check


def rule_check(parts):
    def check(text):
        if has_line(text, *parts):
            return None
        return "no line of the context holds %r in order" % (parts,)
    return check


def add(name, kind, stdin=None, check=None, fn=None):
    CASES.append({"name": name, "kind": kind, "stdin": stdin, "check": check, "fn": fn})


def dispatch(case):
    """Return None when the case passes, else a note saying why not."""
    if case["kind"] == "custom":
        return case["fn"]()
    if case["kind"] == "bad":
        got = run(case["stdin"])
        if got is None:
            return "the hook file is missing: %s" % HOOK
        rc, out, err = got
        if rc != 0:
            return "exit %d: %s" % (rc, err.strip()[:120])
        if out.strip():
            return "expected no stdout, got %s" % out.strip()[:120]
        err_lines = err.strip().splitlines() if err.strip() else []
        if len(err_lines) > 1:
            return "want at most one stderr line, got %d" % len(err_lines)
        if err_lines and not err_lines[0].startswith("agent_brief:"):
            return "stderr line is %r, want it to start 'agent_brief:'" % err_lines[0][:120]
        return None
    text, problem = context_for(case["stdin"])
    if problem:
        return problem
    return case["check"](text)


# SHAPE: no case of its own. context_for() checks the one-line JSON shape on every "context"
# case. The scope rows (one per type) and the general row for a missing type cover the same inputs.

# RULES: each standing rule is in the context. The rule lines are the same for every type.
RULES = [
    ("rule: never git stash, with no worktree condition",
     ("Never run git stash.",)),
    ("rule: outside the agent's own worktree (a folder under .claude/worktrees), never git reset with a discard flag, git checkout of a path, or git restore",
     ("Outside your own agent worktree (a folder under .claude/worktrees), never run git reset with one of the flags",
      "/".join(guard_shared_tree.RESET_DISCARD_FLAGS), "git checkout of a path", "git restore")),
    ("rule: push only with git push origin HEAD:<branch>",
     ("Push only with", "git push origin HEAD:<branch>")),
    ("rule: no gh call unless the brief names it",
     ("Make no gh call", "unless your brief names it")),
    ("rule: report cap of 25 lines, then the label order Done, Deviations, Input Needed, Next",
     ("25 lines or fewer", "Done,", "Deviations,", "Input Needed,", "Next.")),
    ("rule: each commit message ends with the Co-Authored-By trailer",
     ("End each commit message with", "Co-Authored-By: <model> <noreply@anthropic.com>")),
    ("rule: no record path in a commit message, except the Drops-lines trailer",
     ("Name no record path in a commit message", "Drops-lines:")),
]
for _label, _parts in RULES:
    add(_label, "context", payload("builder"), rule_check(_parts))


def line_set_check(expected, staged=False):
    """Build a check: the non-scope lines equal `expected`, in order. With `staged`, the staged-diff line is
    left out first: its place in the brief is not pinned here, and staged_check pins that it appears once."""
    def check(text):
        rules = [line for line in text.split("\n") if not line.startswith("- Scope")]
        if staged:
            rules = [line for line in rules if STAGED_KEY not in line]
        noted = rendered_rules()  # the note rules have their own cases below, so a line that holds one is left out here
        rules = [line for line in rules if not any(rule in line for rule in noted)]
        if rules == expected:
            return None
        if len(rules) != len(expected):
            missing = [want for want in expected if want not in rules]  # names the first pinned line the context lacks
            named = "; no line is %r" % missing[0][:90] if missing else ""
            return "%d non-scope lines, want %d%s" % (len(rules), len(expected), named)
        for got, want in zip(rules, expected):
            if got != want:
                return "line is %r, want %r" % (got[:90], want[:90])
        return None
    return check


for _t in ["builder", "test-author", "record-writer", "designer"]:
    add("line set: %s gets the writer set" % _t, "context", payload(_t),
        line_set_check(WRITER_RULES, staged=True))
add("line set: a general (unknown) type gets the writer set", "context",
    payload("some-new-agent"), line_set_check(WRITER_RULES, staged=True))
add("line set: a missing agent type gets the writer set", "context", payload(),
    line_set_check(WRITER_RULES, staged=True))
for _t in ["reviewer", "Explore", "Plan", "claude-code-guide", "design-reviewer"]:
    add("line set: %s gets the six-line set" % _t, "context", payload(_t),
        line_set_check(READER_RULES))
# The refuter is read-only, so it gets the six-line set: no push, trailer, record-path or staged-diff line
# (decision plan-refuter). Failure class: a read-only role given the writer set.
add("line set: refuter gets the six-line set", "context", payload(REFUTER), line_set_check(READER_RULES))
# Plugin-prefixed read-only types take the reader set too (the prefix split must reach them).
for _t in ["my-plugin:reviewer", "ns:Explore"]:
    add("line set: plugin-prefixed %s gets the six-line set" % _t, "context", payload(_t),
        line_set_check(READER_RULES))


def git_line_check(want):
    """Build a check: the standing git line `want` is in the context exactly, for every agent type."""
    def check():
        for agent_type in TYPES + ["Plan", MISSING]:
            text, problem = context_for(payload(agent_type))
            if problem:
                return problem
            lines = text.split("\n")
            if want not in lines:
                held = [line[:90] for line in lines if "Never run" in line or "Outside your own agent worktree" in line]
                return "agent type %r holds %r, want %r" % (agent_type, held, want)
        return None
    return check


add("rules: the standing stash line is exactly %r for every agent type" % STASH_LINE, "custom",
    fn=git_line_check(STASH_LINE))
add("rules: the standing reset line is exactly %r for every agent type" % RESET_LINE, "custom",
    fn=git_line_check(RESET_LINE))


def stash_check():
    """No line of any agent type's context names git stash except the pinned stash line, so the stash ban has no
    worktree condition."""
    for agent_type in TYPES + ["Plan", MISSING]:
        text, problem = context_for(payload(agent_type))
        if problem:
            return problem
        for line in text.split("\n"):
            if "git stash" in line and line != STASH_LINE:
                return "agent type %r holds a git stash line other than %r: %r" % (agent_type, STASH_LINE, line[:90])
    return None


add("rules: the stash ban has no worktree condition: no other line names git stash", "custom", fn=stash_check)


RESET_VERB = re.compile(r"\breset\b", re.IGNORECASE)  # every use of the verb, bare or with a flag
RESET_SENTENCE = "- Outside your own agent worktree (a folder under .claude/worktrees),"  # the one sentence that may hold the reset verb


def discard_flag_after(line, pos):
    """The discard flag that appears in `line` after position `pos`, or None when none does."""
    for flag in guard_shared_tree.RESET_DISCARD_FLAGS:
        if re.search(re.escape(flag) + r"(?![\w-])", line[pos:]):
            return flag
    return None


def reset_check():
    """Every agent type's context holds the reset verb only in the sentence that starts with RESET_SENTENCE, and a
    discard flag follows it in that sentence. No line bans a bare reset."""
    for agent_type in TYPES + ["Plan", MISSING]:
        text, problem = context_for(payload(agent_type))
        if problem:
            return problem
        hits = [(line, hit) for line in text.split("\n") for hit in RESET_VERB.finditer(line)]
        if not hits:
            return "agent type %r holds no reset verb: the standing line %r is missing" % (agent_type, RESET_LINE)
        for line, hit in hits:
            if not line.startswith(RESET_SENTENCE):
                return "agent type %r holds the reset verb outside the sentence %r: %r" % (
                    agent_type, RESET_SENTENCE, line[:90])
            if discard_flag_after(line, hit.end()) is None:
                return "agent type %r holds a reset verb with no discard flag after it: %r" % (agent_type, line[:90])
    return None


add("rules: the reset verb holds only in the outside-worktree sentence, with a discard flag after it",
    "custom", fn=reset_check)

# A stand-in flag set. A context rebuilt with it must name it, which only holds when the hook reads the constant.
PATCHED_FLAGS = ("--patched-flag",)


def load_hook_fresh():
    """The hook module, loaded again from HOOK, so it reads RESET_DISCARD_FLAGS as it is now. Returns
    (module, None), or (None, problem) when the hook does not load."""
    try:
        spec = importlib.util.spec_from_file_location("agent_brief_fresh", HOOK)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod, None
    except (Exception, SystemExit) as e:
        return None, "the hook does not load: %s" % (e,)


def patched_flags_check():
    """With RESET_DISCARD_FLAGS patched, a context rebuilt for every agent type names the patched reset line, not the real one."""
    want = standing_git_lines(PATCHED_FLAGS)[1]
    saved = guard_shared_tree.RESET_DISCARD_FLAGS
    guard_shared_tree.RESET_DISCARD_FLAGS = PATCHED_FLAGS
    try:
        hook, problem = load_hook_fresh()
        if problem:
            return problem
        for agent_type in TYPES + ["Plan", None]:
            try:
                got = hook.build(agent_type)
            except Exception as e:
                return "building the context for agent type %r raised: %s" % (agent_type, e)
            lines = got.split("\n")
            if want not in lines:
                return "with the constant patched, agent type %r lacks the line %r" % (agent_type, want)
            if RESET_LINE in lines:
                return "with the constant patched, agent type %r still names the real line %r" % (agent_type, RESET_LINE)
        return None
    finally:
        guard_shared_tree.RESET_DISCARD_FLAGS = saved


add("rules: with RESET_DISCARD_FLAGS patched, a rebuilt context names the patched flags for every type",
    "custom", fn=patched_flags_check)


def length_check():
    for agent_type in TYPES + ["Plan", MISSING]:
        text, problem = context_for(payload(agent_type))
        if problem:
            return problem
        lines = len(text.split("\n"))
        if lines >= 20:
            return "agent type %r context is %d lines, want fewer than 20" % (agent_type, lines)
    return None


add("length: the context stays under 20 lines for every agent type", "custom", fn=length_check)

# SCOPE: each type gets its own full scope line, and only that one.
for _t in TYPES:
    add("scope: %s gets its own full scope line" % _t, "context", payload(_t), scope_check(_t))

# GENERAL: an unknown, odd, or missing type gets the full general scope line.
GENERAL_CASES = [
    ("an unknown agent type gets the general line", payload("Plan")),
    ("an empty agent type gets the general line", payload("")),
    ("an agent type with a trailing space gets the general line", payload("builder ")),
    ("a null agent type gets the general line", payload(None)),
    ("a number agent type gets the general line", payload(7)),
    ("a list agent type gets the general line", payload(["builder"])),
    ("a missing agent type gets the general line", payload()),
    ("a JSON array on stdin gets the general line", "[1, 2]"),
    ("a JSON string on stdin gets the general line", '"builder"'),
]
def general_rows_check():
    """One case for the general-line rows. A failing row names itself in the note."""
    check = scope_check("general")
    for name, stdin in GENERAL_CASES:
        note = dispatch({"kind": "context", "stdin": stdin, "check": check})
        if note is not None:
            return "general: %s: %s" % (name, note)
    return None


add("general: %d odd-input rows each get the general scope line" % len(GENERAL_CASES),
    "custom", fn=general_rows_check)

# CASE FOLD: an agent type in other case takes the scope and the line set of its role (decision
# agents-get-standing-rules, the scope line varies by agent type). `Builder` gets the builder scope. `explore` is a reader with the
# Explore scope, so it gets none of the push, trailer and record-path lines.
add("case: Builder gets the builder scope line", "context", payload("Builder"), scope_check("builder"))
add("case: explore gets the Explore scope line", "context", payload("explore"), scope_check("Explore"))
add("case: explore gets the six-line set", "context", payload("explore"), line_set_check(READER_RULES))

# The push, trailer and record-path lines are for the write-capable types and the general
# case, and never for reviewer or Explore.
for _t in ["builder", "test-author", "record-writer", "designer"]:
    add("brief lines: %s gets the push, trailer and record-path lines" % _t, "context",
        payload(_t), brief_lines_check(True))
add("brief lines: a missing agent type (general case) gets the push, trailer and record-path lines",
    "context", payload(), brief_lines_check(True))
for _t in ["reviewer", "Explore"]:
    add("brief lines: %s gets none of the push, trailer and record-path lines" % _t, "context",
        payload(_t), brief_lines_check(False))

# The builder never edits tests. A mutant is test content, so a builder never adds one, even when its brief
# asks: the scope line sends a mutant to a test-author.
add("builder scope: says never edit tests", "context", payload("builder"),
    builder_scope_check("never edit tests"))
add("builder scope: a mutant goes to a test-author", "context", payload("builder"),
    builder_scope_check("mutant", "test-author"))
add("builder scope: does not invite adding mutants when the brief asks", "context", payload("builder"),
    builder_scope_check("never edit tests", lacks=("add mutants", "brief asks")))

# PLUGIN NAMESPACE: `plugin:type` takes the scope of its bare type name.
add("namespace: my-plugin:builder gets the builder scope line", "context",
    payload("my-plugin:builder"), scope_check("builder"))


def internal_error_check():
    """An internal error prints nothing on stdout, one stderr line that starts `agent_brief:`,
    and exits 0."""
    if not os.path.exists(HOOK):
        return "the hook file is missing: %s" % HOOK
    result = subprocess.run([sys.executable, "-c", INJECT_ERROR, HOOK], input=payload("builder"),
                            capture_output=True, encoding="utf-8", timeout=30)
    if result.returncode != 0:
        return "exit %d: %s" % (result.returncode, result.stderr.strip()[:120])
    if result.stdout.strip():
        return "expected no stdout, got %s" % result.stdout.strip()[:120]
    err = result.stderr.strip().split("\n") if result.stderr.strip() else []
    if len(err) != 1:
        return "want one stderr line, got %d" % len(err)
    if not err[0].startswith("agent_brief:"):
        return "stderr line is %r, want it to start 'agent_brief:'" % err[0][:120]
    return None


add("error: an internal error gives no stdout, one agent_brief: stderr line, exit 0", "custom",
    fn=internal_error_check)

# GUARD_CORE FAILS ON IMPORT: the hook imports guard_core at module top, so this case runs the hook in a child whose
# guard_core raises on every attribute read, as a guard_core that fails at import does. `prelude` runs before the hook
# file, so the same child runner serves the red case (a broken guard_core) and its control (no prelude).
BROKEN_GUARD_CORE = (
    "import sys, types\n"
    "class _Broken(types.ModuleType):\n"
    "    def __getattr__(self, name):\n"
    "        raise RuntimeError('guard_core is broken')\n"
    "sys.modules['guard_core'] = _Broken('guard_core')\n"
)
HOOK_RUNNER = (
    "import runpy, sys\n"
    "sys.argv = sys.argv[1:]\n"
    "runpy.run_path(sys.argv[0], run_name='__main__')\n"
)


def run_hook_after(prelude, stdin_text):
    """Run the hook in a child that runs `prelude` first, then the hook file as __main__."""
    return subprocess.run([sys.executable, "-c", prelude + HOOK_RUNNER, HOOK], input=stdin_text,
                          capture_output=True, encoding="utf-8", timeout=30)


def last_stderr_line(result):
    lines = result.stderr.strip().splitlines()
    return lines[-1][:120] if lines else "no stderr"


def guard_core_fails_check():
    """A guard_core that fails on import: the hook fails open, as its docstring says. Exit 0, no traceback,
    no stdout, and one stderr line that starts `agent_brief:`."""
    if not os.path.exists(HOOK):
        return "the hook file is missing: %s" % HOOK
    result = run_hook_after(BROKEN_GUARD_CORE, payload("builder"))
    if result.returncode != 0:
        return "exit %d when guard_core fails on import, want 0: %s" % (result.returncode, last_stderr_line(result))
    if "Traceback" in result.stderr:
        return "stderr holds a traceback when guard_core fails on import, want one agent_brief: line"
    if result.stdout.strip():
        return "expected no stdout, got %s" % result.stdout.strip()[:120]
    err = result.stderr.strip().split("\n") if result.stderr.strip() else []
    if len(err) != 1:
        return "want one stderr line, got %d" % len(err)
    if not err[0].startswith("agent_brief:"):
        return "stderr line is %r, want it to start 'agent_brief:'" % err[0][:120]
    return None


add("error: a guard_core that fails on import gives no stdout, one agent_brief: stderr line, exit 0", "custom",
    fn=guard_core_fails_check)


def guard_core_control_check():
    """The control for the case above: with guard_core working, the same child runner gives the refuter the
    six-line read-only set. Green here and red above means the broken import is the cause, not the runner."""
    if not os.path.exists(HOOK):
        return "the hook file is missing: %s" % HOOK
    result = run_hook_after("", payload(REFUTER))
    if result.returncode != 0:
        return "exit %d with guard_core working, want 0: %s" % (result.returncode, last_stderr_line(result))
    text, problem = context_of(result.stdout)
    if problem:
        return problem
    return line_set_check(READER_RULES)(text)


add("control: with guard_core working, the refuter gets the six-line set through the same runner", "custom",
    fn=guard_core_control_check)

# SHARED-TREE FAILS ON IMPORT: the hook imports guard_shared_tree in its own try block, so a failed import drops only
# the reset line. A None entry in sys.modules makes the import raise ImportError, as a module that fails to load does.
BROKEN_SHARED_TREE = "import sys\nsys.modules['guard_shared_tree'] = None\n"


def shared_tree_fails_check():
    """A guard_shared_tree that fails on import: the hook still prints the scope line and every other standing line,
    the stash line included, and prints no reset line. Exit 0, one JSON object on stdout."""
    if not os.path.exists(HOOK):
        return "the hook file is missing: %s" % HOOK
    result = run_hook_after(BROKEN_SHARED_TREE, payload("builder"))
    if result.returncode != 0:
        return "exit %d when guard_shared_tree fails on import, want 0: %s" % (result.returncode, last_stderr_line(result))
    if not result.stdout.strip():
        return "with guard_shared_tree failing on import, the hook prints no context: every standing line is dropped"
    text, problem = context_of(result.stdout)
    if problem:
        return problem
    scope = scope_check("builder")(text)
    if scope:
        return "with guard_shared_tree failing on import, %s" % scope
    lines = text.split("\n")
    for want in WRITER_RULES:
        if want != RESET_LINE and want not in lines:
            return "with guard_shared_tree failing on import, no line is %r" % want[:90]
    for line in lines:
        if RESET_VERB.search(line):
            return "with guard_shared_tree failing on import, a line still names the reset verb: %r" % line[:90]
    return None


add("error: a guard_shared_tree that fails on import keeps the stash line and every other standing line, and no reset line",
    "custom", fn=shared_tree_fails_check)


def shared_tree_control_check():
    """The control for the case above: with guard_shared_tree working, the same child runner gives the builder the
    stash line and a reset line. Green here and red above means the broken import is the cause, not the runner.
    The reset line is found by its verb: its wording is pinned by the rules cases, not here."""
    if not os.path.exists(HOOK):
        return "the hook file is missing: %s" % HOOK
    result = run_hook_after("", payload("builder"))
    if result.returncode != 0:
        return "exit %d with guard_shared_tree working, want 0: %s" % (result.returncode, last_stderr_line(result))
    text, problem = context_of(result.stdout)
    if problem:
        return problem
    lines = text.split("\n")
    if STASH_LINE not in lines:
        return "with guard_shared_tree working, no line is %r" % STASH_LINE[:90]
    if not any(RESET_VERB.search(line) for line in lines):
        return "with guard_shared_tree working, no line names the reset verb"
    return None


add("control: with guard_shared_tree working, the builder gets the stash line and a reset line through the same runner",
    "custom", fn=shared_tree_control_check)

# SILENT: junk or empty stdin gives no stdout, exit 0, and at most one stderr line that starts
# `agent_brief:`.
BAD_CASES = [
    ("empty stdin", ""),
    ("whitespace-only stdin", "  \n"),
    ("junk stdin", "not json"),
    ("truncated JSON", '{"agent_type": "builder"'),
    ("non-text bytes on stdin", "\x00\x01 junk {"),
]
for _name, _stdin in BAD_CASES:
    add("bad input: %s gives no stdout, exit 0, at most one agent_brief: stderr line" % _name,
        "bad", _stdin)

# CITE FORM: the brief names the repo's record cite form. The hook reads `.github/stamp.json`
# under the payload's `cwd`, so the form comes from the repo, not from the hook's text. The
# fixture has three kinds (D, F, Q). The form is per kind: one brief line gives every kind's form,
# in kind order, because a single {prefix} filled from kinds[0] would name only D.
CITE_CONFIG = {
    "kinds": [
        {"id": "decision", "folder": "decisions", "prefix": "D", "idTemplate": "{prefix}{n}"},
        {"id": "finding", "folder": "findings", "prefix": "F", "idTemplate": "{prefix}{n}"},
        {"id": "question", "folder": "questions", "prefix": "Q", "idTemplate": "{prefix}{n}"},
    ],
    "cite": {"pattern": "([DFQ])‹([a-z0-9-]+)›", "prefixGroup": 1, "slugGroup": 2, "template": "{id}",
             "form": "{prefix}‹{slug}›"},  # cite.form is the one source for the brief line
}


def brief_for_config(config):
    """Run the hook in a repo whose .github/stamp.json holds `config`. Return (text, problem)."""
    return brief_in(repo_tree(config=config))


def cite_form_check():
    """A repo whose stamp.json carries cite.form gets one brief line that carries every kind's form."""
    text, problem = brief_for_config(CITE_CONFIG)
    if problem:
        return problem
    forms =["%s‹slug›" % letter for letter in ("D", "F", "Q")]  # spelled as escapes
    if not has_line(text, *forms):
        return "no one brief line carries the form of each kind (D, F, Q) from the repo's stamp.json"
    if len(text.split("\n")) >= 20:
        return "the context is %d lines, want fewer than 20" % len(text.split("\n"))
    return None


def cite_form_absent_check():
    """A stamp.json with cite.pattern and no cite.form adds no cite line: no form is derived."""
    config = json.loads(json.dumps(CITE_CONFIG))
    del config["cite"]["form"]
    text, problem = brief_for_config(config)
    if problem:
        return problem
    if "‹slug›" in text or "Cite a record in this repo" in text:
        return "a cite line was derived from cite.pattern; want none without cite.form"
    return None


add("cite form: a repo stamp.json with cite.form adds a brief line that carries it",
    "custom", fn=cite_form_check)
add("cite form: a repo stamp.json with cite.pattern and no cite.form adds no cite line",
    "custom", fn=cite_form_absent_check)


# STAGED: the staged-diff step has one home, agent_brief's COMMON (decision lanes-start-in-tool-worktrees). A
# committing type's brief holds it once, a read-only type's brief holds none, and no agent file keeps a copy.
AGENTS_DIR = os.path.join(os.path.dirname(HERE), "agents")
REPO_ROOT = os.path.dirname(HERE)


def load_read_only():
    """(lowercased READ_ONLY names, None) from the hook under test, or (None, problem) when it does not load.
    A missing or broken hook is a red case, never a crash at import."""
    try:
        spec = importlib.util.spec_from_file_location("agent_brief_under_test", HOOK)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return {name.lower() for name in module.READ_ONLY}, None
    except Exception as exc:  # the cases report it
        return None, "agent_brief's READ_ONLY set does not load: %s" % exc


WRITE_TOOLS = {"Edit", "Write"}


def write_names(raw):
    """The tool names in a frontmatter list value, comment stripped, each scope dropped: `Edit(src/**)` reads as Edit."""
    return {item.split("(", 1)[0] for item in tokens(raw.split("#", 1)[0])}


def can_write(keys):
    """True when an agent may write, read from its frontmatter keys alone: its `tools` allowlist, when it has one,
    lists Edit or Write, and its `disallowedTools` lists neither. Raises ValueError when a list sits below its key,
    which the shared reader does not read, so the answer is never a guess."""
    field = unread_list(keys)
    if field:
        raise ValueError("the %s list sits below its key, which the reader does not read" % field)
    if "tools" in keys and not WRITE_TOOLS & write_names(keys["tools"]):
        return False
    return not WRITE_TOOLS & write_names(keys.get("disallowedTools", ""))


# The write verdict of an agent's frontmatter, one case per form the lint reader reads: a comma list, a bracket list,
# quoted names, a scoped entry such as Edit(src/**), a comment, and an absent key. A list below its key fails loudly.
WRITE_FORMS = (
    ("a comma tools list that names Edit", {"tools": "Read, Edit"}, True),
    ("a comma tools list that names no write tool", {"tools": "Read, Grep"}, False),
    ("a comma disallowedTools list that names Edit", {"disallowedTools": "Edit, Bash"}, False),
    ("a bracket tools list that names Edit", {"tools": "[Read, Edit]"}, True),
    ("a bracket disallowedTools list that names Edit and Write", {"disallowedTools": "[Edit, Write]"}, False),
    ("a quoted tools list that names Edit", {"tools": "\"Read\", 'Edit'"}, True),
    ("a quoted disallowedTools list that names Write", {"disallowedTools": "\"Write\""}, False),
    ("a scoped tools entry Edit(src/**)", {"tools": "Read, Edit(src/**)"}, True),
    ("a scoped disallowedTools entry Write(**)", {"disallowedTools": "Write(**)"}, False),
    ("a tools list with a comment after it that names Edit", {"tools": "Read, Edit  # writes"}, True),
    ("no tools or disallowedTools key", {"name": "x"}, True),
)


def write_form_check(keys, want):
    """A case: can_write answers `want` for the frontmatter `keys`."""
    def check():
        got = can_write(keys)
        if got != want:
            return "can_write answers %s for %s; want %s" % (got, keys, want)
        return None
    return check


def unread_list_check(keys, field):
    """A case: can_write raises ValueError naming `field` when its list sits below the key, never a misjudged answer."""
    def check():
        try:
            got = can_write(keys)
        except ValueError as exc:
            if field in str(exc):
                return None
            return "can_write raised, but its message does not name %s: %s" % (field, exc)
        return "can_write answers %s for an empty %s key; want a loud failure" % (got, field)
    return check


for form_name, form_keys, form_want in WRITE_FORMS:
    add("can_write: %s" % form_name, "custom", fn=write_form_check(form_keys, form_want))
add("can_write: an empty tools key with its list on the lines below fails loudly, naming tools",
    "custom", fn=unread_list_check({"tools": ""}, "tools"))
add("can_write: an empty disallowedTools key with its list on the lines below fails loudly, naming disallowedTools",
    "custom", fn=unread_list_check({"disallowedTools": ""}, "disallowedTools"))


def agent_entries():
    """(entries, problem): one (name, can_write) pair per agents/*.md file, from guard.role_agent_keys, the one
    reader of agent frontmatter. The problem counts the files, so an agent file the reader skips cannot pass unseen."""
    try:
        files = [name for name in os.listdir(AGENTS_DIR) if name.endswith(".md")]
        keys = list(guard.role_agent_keys(REPO_ROOT))
    except OSError as exc:
        return [], "agents/ cannot be read: %s" % exc
    entries, unread = [], []
    for key in keys:
        name = key.get("name", "").split("#", 1)[0].strip().strip("'\"")
        try:
            entries.append((name, can_write(key)))
        except ValueError as exc:
            unread.append(str(exc))
    named = [(name, writes) for name, writes in entries if name]
    if unread:
        return named, "; ".join(unread)
    if not files or len(keys) != len(files) or len(named) != len(files):
        return named, ("want a name from each of the %d agent files; %d have frontmatter, %d have a name"
                       % (len(files), len(keys), len(named)))
    return named, None


READ_ONLY, READ_ONLY_PROBLEM = load_read_only()
AGENT_ENTRIES, NAMES_PROBLEM = agent_entries()
AGENT_NAMES = [name for name, _writes in AGENT_ENTRIES]


def staged_check(name, writes):
    """Build a check for one agent. A committing agent's brief holds exactly one staged-diff line; a read-only
    agent's brief holds none. `writes` is the agent's frontmatter verdict (can_write), not the hook's READ_ONLY set,
    so a writer filed into READ_ONLY still has to show its line."""
    def check():
        text, problem = context_for(payload(name))
        if problem:
            return problem
        hits = [line for line in text.split("\n") if STAGED_KEY in line]
        if not writes:
            if hits:
                return "a read-only type gets the staged-diff line: %r" % hits[0][:90]
            return None
        if len(hits) != 1:
            return "want one line that holds %r, got %d" % (STAGED_KEY, len(hits))
        return None
    return check


def agent_list_check():
    """The agent list is whole: every agent file names itself, and committing and read-only types are both present,
    so the per-agent cases cannot pass on an empty or partial list."""
    if NAMES_PROBLEM:
        return NAMES_PROBLEM
    if READ_ONLY_PROBLEM:
        return READ_ONLY_PROBLEM
    writers = [name for name in AGENT_NAMES if name.lower() not in READ_ONLY]
    readers = [name for name in AGENT_NAMES if name.lower() in READ_ONLY]
    if not writers or not readers:
        return "want committing and read-only agents, got %d and %d" % (len(writers), len(readers))
    return None


def copies_check():
    """No agent file carries its own copy of the staged-diff step."""
    copies = []
    try:
        for name in sorted(os.listdir(AGENTS_DIR)):
            if name.endswith(".md"):
                with open(os.path.join(AGENTS_DIR, name), encoding="utf-8") as handle:
                    if STAGED_KEY in handle.read():
                        copies.append("agents/" + name)
    except OSError as exc:
        return "agents/ cannot be read: %s" % exc
    if copies:
        return "own copy of %r in %s; the one home is agent_brief's COMMON" % (STAGED_KEY, ", ".join(copies))
    return None


add("staged-diff step: agents/ names every agent, with committing and read-only types both present",
    "custom", fn=agent_list_check)
for _name, _writes in AGENT_ENTRIES:
    add("staged-diff step, agent %s: one line if it commits, none if it is read-only" % _name,
        "custom", fn=staged_check(_name, _writes))
add("staged-diff step: no agents/*.md file carries its own copy of it", "custom", fn=copies_check)


def staged_once_check(agent_type):
    """Build a check: the brief for `agent_type` holds the staged-diff line exactly once. A general type and a
    missing type take the general scope line and the writer set, so each holds the line too."""
    def check():
        text, problem = context_for(payload(agent_type))
        if problem:
            return problem
        hits = [line for line in text.split("\n") if STAGED_KEY in line]
        if len(hits) != 1:
            return "want one line that holds %r, got %d" % (STAGED_KEY, len(hits))
        return None
    return check


add("staged-diff step: a general type (general-purpose) holds the staged-diff line exactly once", "custom",
    fn=staged_once_check("general-purpose"))
add("staged-diff step: a missing agent type holds the staged-diff line exactly once", "custom",
    fn=staged_once_check(MISSING))


def read_only_set_check():
    """agent_brief's READ_ONLY set names exactly the agents whose frontmatter says they cannot write. A failure names
    one agent and the way it disagrees."""
    if NAMES_PROBLEM:
        return NAMES_PROBLEM
    if READ_ONLY_PROBLEM:
        return READ_ONLY_PROBLEM
    for name, writes in AGENT_ENTRIES:
        listed = name.lower() in READ_ONLY
        if writes and listed:
            return "%s can write by its frontmatter, but agent_brief's READ_ONLY lists it" % name
        if not writes and not listed:
            return "%s cannot write by its frontmatter, but agent_brief's READ_ONLY does not list it" % name
    return None


add("staged-diff step: agent_brief's READ_ONLY set names exactly the agents whose frontmatter cannot write",
    "custom", fn=read_only_set_check)


def refuter_name_check():
    """guard_core names the refuter role in REFUTER_ROLE, a non-empty string. Every refuter case here reads that
    name from guard_core, so a guard_core without it fails this case and says so."""
    if REFUTER == REFUTER_MISSING:
        return "guard_core has no REFUTER_ROLE, the one home of the refuter role's name"
    if not isinstance(REFUTER, str) or not REFUTER.strip():
        return "guard_core.REFUTER_ROLE is %r, want a non-empty name" % (REFUTER,)
    return None


def refuter_read_only_check():
    """agent_brief's READ_ONLY set holds the refuter role, so the hook treats it as a read-only type."""
    if READ_ONLY_PROBLEM:
        return READ_ONLY_PROBLEM
    if REFUTER == REFUTER_MISSING:
        return "guard_core has no REFUTER_ROLE, so agent_brief's READ_ONLY set cannot name the refuter"
    if REFUTER.lower() not in READ_ONLY:
        return "agent_brief's READ_ONLY set does not hold %s, so the hook gives it the writer set" % REFUTER
    return None


add("refuter: guard_core.REFUTER_ROLE names the role, the one home the refuter cases read",
    "custom", fn=refuter_name_check)
add("refuter: agent_brief's READ_ONLY set holds the refuter role", "custom", fn=refuter_read_only_check)


# NOTE RULES: the brief gives every agent the rules that check_record_slugs.AGENT_FORM_RULES holds, one list that the
# check prints and the brief reads. An entry holds {folder} (the note folder, with its slash) and {old} (the old notes
# file). Both come from the layout of the payload's cwd, read as the hook reads it. NOTE_FORM and NOTE_FILE are the spec's own
# words, pinned here. The stand-in cases run the hook with a changed and an added list, so a rule that the list changes
# must reach the brief, and the note form that the list dropped must leave it.
LINT_DIR = os.path.join(REPO_ROOT, "lint")
NOTE_RULES_NAME = "AGENT_FORM_RULES"  # the list's name in check_record_slugs.py
NOTE_FORM = "- <slug>: <text>"  # the form a note line takes (decision notes-merge-union)
NOTE_FILE = "<slug>.md"  # a note file, named by its slug
CHANGED_RULE = "SENTINEL rule changed in the list: the note folder is {folder}"  # a stand-in value, not a note rule
EXTRA_RULE = "SENTINEL rule added to the list: the old notes file {old} takes deletes only"  # added, with no edit


def layout_paths(cwd):
    """(note folder with its slash, old notes file, None) from the layout of `cwd`, the repo the payload names, or
    (None, None, problem). The hook fills its rules from that same layout."""
    sys.path.append(LINT_DIR)
    try:
        import layout  # noqa: E402  the one home of where records live (lint/layout.py)
        return layout.path(cwd, "notes") + "/", layout.path(cwd, "debt-notes"), None
    except Exception as exc:  # a layout that does not read is a red case, never a crash at import
        return None, None, "lint/layout.py does not read: %s" % exc


def load_note_rules():
    """(the list's entries, None) from check_record_slugs, or (None, problem). A missing list is a red case."""
    sys.path.append(LINT_DIR)
    try:
        module = importlib.import_module("check_record_slugs")
    except Exception as exc:
        return None, "check_record_slugs does not load: %s" % exc
    rules = getattr(module, NOTE_RULES_NAME, None)
    if rules is None:
        return None, "check_record_slugs has no %s list, the one home of the note rules" % NOTE_RULES_NAME
    if not isinstance(rules, (tuple, list)) or not all(isinstance(r, str) and r.strip() for r in rules):
        return None, "%s is not a list of text entries" % NOTE_RULES_NAME
    return list(rules), None


FOLDER, OLD_NOTES, LAYOUT_PROBLEM = layout_paths(CWD)
NOTE_RULES, RULES_PROBLEM = load_note_rules()


def render(template):
    """A rule as the brief shows it: the note folder and the old notes file of the payload's cwd, filled in."""
    return template.replace("{folder}", FOLDER).replace("{old}", OLD_NOTES)


def rendered_rules():
    """The list's rules as the brief renders them, or none while the list or the layout does not read."""
    if LAYOUT_PROBLEM or RULES_PROBLEM:
        return []
    return [render(rule) for rule in NOTE_RULES]


def same_line(text, *parts):
    """True when one line of text holds every part, in any order."""
    return any(all(part in line for part in parts) for line in text.split("\n"))


def stand_in_prelude(rules):
    """Source that puts a stand-in check_record_slugs, whose list holds `rules`, in sys.modules before the hook runs."""
    return ("import sys, types\n"
            "_stand_in = types.ModuleType('check_record_slugs')\n"
            "_stand_in.%s = %r\n"
            "sys.modules['check_record_slugs'] = _stand_in\n" % (NOTE_RULES_NAME, tuple(rules)))


def stand_in_context(rules, agent_type="builder"):
    """(additionalContext, None) from the hook run with a stand-in check_record_slugs, or (None, problem)."""
    if not os.path.exists(HOOK):
        return None, "the hook file is missing: %s" % HOOK
    result = run_hook_after(stand_in_prelude(rules), payload(agent_type))
    if result.returncode != 0:
        return None, "exit %d with a stand-in check_record_slugs: %s" % (result.returncode, last_stderr_line(result))
    return context_of(result.stdout)


def note_form_check(agent_type):
    """Build a check: the brief for `agent_type` has its scope line, and one line holds the note file in the note
    folder and the note form."""
    def check():
        if LAYOUT_PROBLEM:
            return LAYOUT_PROBLEM
        text, problem = context_for(payload(agent_type))
        if problem:
            return problem
        scope = scope_check(agent_type if isinstance(agent_type, str) else "general")(text)  # scope before the subject
        if scope:
            return scope
        if not same_line(text, FOLDER + NOTE_FILE, NOTE_FORM):
            return "no line of the brief holds both %r and %r" % (FOLDER + NOTE_FILE, NOTE_FORM)
        return None
    return check


def old_notes_check():
    """The brief's old notes file line names the old notes file and says it takes deletes only, on one line."""
    if LAYOUT_PROBLEM:
        return LAYOUT_PROBLEM
    text, problem = context_for(payload("builder"))
    if problem:
        return problem
    if not same_line(text, OLD_NOTES, "deletes only"):
        return "no line of the brief holds both %r and 'deletes only'" % OLD_NOTES
    return None


def list_reaches_brief_check():
    """The builder's brief carries every rule that the list holds, rendered: the list is the source of the text."""
    if LAYOUT_PROBLEM:
        return LAYOUT_PROBLEM
    if RULES_PROBLEM:
        return RULES_PROBLEM
    text, problem = context_for(payload("builder"))
    if problem:
        return problem
    for rule in rendered_rules():
        if rule not in text:
            return "the brief lacks a rule the list holds: %r" % rule[:90]
    return None


def changed_rule_check():
    """A changed rule in the list reaches the brief, and the note form that the list dropped leaves it: the brief
    reads the list, and holds no copy of the text."""
    if LAYOUT_PROBLEM:
        return LAYOUT_PROBLEM
    text, problem = stand_in_context([CHANGED_RULE])
    if problem:
        return problem
    if render(CHANGED_RULE) not in text:
        return "the changed rule is not in the brief: the brief does not read check_record_slugs.%s" % NOTE_RULES_NAME
    if same_line(text, FOLDER + NOTE_FILE, NOTE_FORM):
        return "the brief still holds the note form after the list dropped it: the line is copied, not read"
    return None


def new_rule_check():
    """A rule added to the list reaches the brief with no edit to the hook."""
    if LAYOUT_PROBLEM:
        return LAYOUT_PROBLEM
    text, problem = stand_in_context([CHANGED_RULE, EXTRA_RULE])
    if problem:
        return problem
    for template in (CHANGED_RULE, EXTRA_RULE):
        if render(template) not in text:
            return "a rule of the list is not in the brief: %r" % render(template)[:90]
    return None


def empty_list_check():
    """Control, green on the old code: an empty list still gives the builder its scope line through the same runner."""
    text, problem = stand_in_context([])
    if problem:
        return problem
    return scope_check("builder")(text)


for _t in TYPES + ["Plan", MISSING]:
    add("note form: %s gets the note form on one line" % (_t if isinstance(_t, str) else "a missing type"),
        "custom", fn=note_form_check(_t))
add("note form: the old notes file line names its path and says it takes deletes only", "custom",
    fn=old_notes_check)
add("source: the builder's brief carries every rule that check_record_slugs.%s holds" % NOTE_RULES_NAME,
    "custom", fn=list_reaches_brief_check)
add("source: a changed rule in the list reaches the brief, and the note form it replaces is gone", "custom",
    fn=changed_rule_check)
add("source: a rule added to the list reaches the brief with no edit", "custom", fn=new_rule_check)
add("source control: an empty list keeps the builder's scope line through the same runner", "custom",
    fn=empty_list_check)


# CWD LAYOUT: the hook fills the note rules from the layout of the payload's cwd, not from this checkout. A cwd with
# no extras file gets the legacy old-notes path. A cwd whose layout does not read gets no note line at all.
NO_EXTRAS_OLD_NOTES = "debts/notes.md"  # the old notes file of a repo with no extras file (the legacy path)
CHECKOUT_OLD_NOTES = "docs/debts/notes.md"  # this checkout's old notes file: a cwd's brief never names it
UNREADABLE_EXTRAS = '{"rolled-out": true, "kinds": {"notes": {"path": "docs/elsewhere"}}}\n'  # moves a layout kind


def note_lines(text):
    """The lines of the brief that carry a note rule: the note form, the note file name, or the old-file rule."""
    return [line for line in text.split("\n") if NOTE_FORM in line or NOTE_FILE in line or "deletes only" in line]


def no_extras_old_file_check():
    """A cwd with no extras file: the brief names the old notes file at debts/notes.md, and never this checkout's
    docs/debts/notes.md."""
    text, problem = brief_in(repo_tree())
    if problem:
        return problem
    scope = scope_check("builder")(text)  # scope before the subject
    if scope:
        return scope
    if not same_line(text, "file " + NO_EXTRAS_OLD_NOTES + " takes", "deletes only"):
        return "no line of the brief holds 'file %s takes' and 'deletes only'" % NO_EXTRAS_OLD_NOTES
    if CHECKOUT_OLD_NOTES in text:
        return "the brief names %s, this checkout's old notes file, not the cwd's" % CHECKOUT_OLD_NOTES
    return None


def unreadable_layout_check():
    """A cwd whose extras file makes layout.kinds() raise: the brief gets no note line. The fixture is shown to make
    layout.kinds() raise first, so the case cannot pass on a fixture that reads fine."""
    root = repo_tree(extras=UNREADABLE_EXTRAS)
    sys.path.append(LINT_DIR)
    import layout  # noqa: E402  the one home of where records live (lint/layout.py)
    try:
        layout.kinds(root)
    except layout.LayoutError:
        pass
    else:
        return "the fixture does not make layout.kinds raise, so the case would prove nothing"
    text, problem = brief_in(root)
    if problem:
        return problem
    scope = scope_check("builder")(text)  # scope before the subject
    if scope:
        return scope
    lines = note_lines(text)
    if lines:
        return "a cwd whose layout does not read gets %d note line(s), want none: %r" % (len(lines), lines[0][:90])
    return None


add("cwd layout: a cwd with no extras file gets the legacy old notes path, not this checkout's", "custom",
    fn=no_extras_old_file_check)
add("cwd layout: a cwd whose layout does not read gets no note line", "custom", fn=unreadable_layout_check)


# NOTE RULES UNREAD: a check_record_slugs that will not import. The hook fails open for the note rules alone: the brief
# still goes out with its scope and no note line, and one stderr line says the rules were not read.
BROKEN_NOTE_LIST = "import sys\nsys.modules['check_record_slugs'] = None\n"  # an import of the name raises ImportError


def note_rules_unread_check():
    """A check_record_slugs that will not import: the hook exits 0, prints the brief with its scope and no note line,
    and its one stderr line starts `agent_brief: note rules not read`."""
    if not os.path.exists(HOOK):
        return "the hook file is missing: %s" % HOOK
    result = run_hook_after(BROKEN_NOTE_LIST, payload("builder"))
    if result.returncode != 0:
        return "exit %d when check_record_slugs will not import, want 0: %s" % (result.returncode,
                                                                                 last_stderr_line(result))
    text, problem = context_of(result.stdout)
    if problem:
        return "the brief did not go out when check_record_slugs will not import: %s" % problem
    scope = scope_check("builder")(text)  # scope before the subject
    if scope:
        return scope
    lines = note_lines(text)
    if lines:
        return "a brief whose note rules did not read holds %d note line(s), want none: %r" % (len(lines), lines[0][:90])
    err = result.stderr.strip().splitlines() if result.stderr.strip() else []
    if len(err) != 1:
        return "want one stderr line, got %d" % len(err)
    if not err[0].startswith("agent_brief: note rules not read"):
        return "stderr line is %r, want it to start 'agent_brief: note rules not read'" % err[0][:120]
    return None


add("note rules unread: a check_record_slugs that will not import leaves the brief out with no note line",
    "custom", fn=note_rules_unread_check)


def main():
    try:
        return run_cases()
    finally:
        if RUN_FOLDER is not None:
            shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def run_cases():
    failed = 0
    for case in CASES:
        note = dispatch(case)
        failed += 0 if note is None else 1
        print("%s  %s  %s" % ("PASS" if note is None else "FAIL", case["name"],
                              "" if note is None else "(%s)" % note))
    print()
    if failed:
        print("test_agent_brief FAIL: %d of %d cases wrong" % (failed, len(CASES)))
        return 1
    print("test_agent_brief PASS: %d of %d cases right" % (len(CASES), len(CASES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
