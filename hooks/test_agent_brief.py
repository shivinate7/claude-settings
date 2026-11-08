#!/usr/bin/env python3
"""Cases for hooks/agent_brief.py, a SubagentStart hook. Standard library only, plus hooks/guard.py,
which reads the agent frontmatter.

Run it from the repository root:

    python hooks/test_agent_brief.py

Contract (the hook's own docstring). On each agent start
the hook prints one JSON object on stdout and exits 0:
    {"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": "<text>"}}
- additionalContext holds the standing rules: a scope line that follows `agent_type` from the hook
  input (builder, test-author, reviewer, Explore, record-writer, designer, design-reviewer), the general scope line for any
  other or missing type, and fewer than 20 lines in all. Each scope line is pinned in full.
- The push line, the commit-trailer line and the record-path line appear for builder,
  test-author, record-writer, designer and any other type; never for reviewer, Explore, Plan,
  claude-code-guide or design-reviewer, which only read.
- The staged-diff line holds `git diff --cached --stat`. It appears once for each type that
  commits (builder, test-author, record-writer, designer and any other type) and never for a
  read-only type. Decision lanes-start-in-tool-worktrees.
- The refusal line holds the words refus, final and base64: a refusal from the harness or a guard is final,
  so report it and never re-send the command in another form. It appears once for every type, reviewer and
  Explore included. Its place in the brief is not pinned; its words are.
- A plugin-namespaced type (`my-plugin:builder`) gets the scope of its bare name. The match ignores
  case: `Builder` and `explore` get the scope and the line set of their role.
- When the payload's cwd holds a .github/stamp.json whose cite.form is set, one brief line
  carries the form of every kind, in kind order. A cite.pattern with no cite.form adds no line.
- Junk or empty stdin, or an internal error: no output on stdout, exit 0, and at most one stderr
  line that starts `agent_brief:`. The hook fails open.

Interface (Claude Code hooks reference, SubagentStart): stdin is one JSON object with
`hook_event_name` "SubagentStart", `agent_id`, and `agent_type`.

Override the module under test with the env var AGENT_BRIEF_UNDER_TEST.
"""
import json
import os
import importlib.util
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.environ.get("AGENT_BRIEF_UNDER_TEST") or os.path.join(HERE, "agent_brief.py")
sys.path.insert(0, HERE)
import guard  # noqa: E402  the one reader of agent frontmatter keys (guard.frontmatter_keys), not a copy of it here
from tool_lists_test import tokens, unread_list  # noqa: E402  the one reader of tool lists (hooks/tool_lists_test.py)

CWD = "/tmp/agent-brief-test"
MISSING = object()  # payload() leaves agent_type out of the JSON when this is passed
TYPES = ["builder", "test-author", "reviewer", "Explore", "record-writer", "designer", "design-reviewer"]

# Full scope line per type, pinned verbatim. Edit here only when the hook's text changes on purpose.
SCOPE_LINE = {
    "builder": "- Scope: builder. Never edit tests or test config. Add mutants to hooks/mutate_guard.py when the brief asks. Report a test change you need.",
    "test-author": "- Scope: test-author. Edit tests and test config only. Never edit product code.",
    "reviewer": "- Scope: reviewer. Never edit, write, stage, commit, or push. Read and run checks only.",
    "Explore": "- Scope: Explore. Never edit. Read and search only.",
    "record-writer": "- Scope: record-writer. Edit Markdown (*.md) files only. Report any other change needed.",
    "designer": "- Scope: designer. Edit files in the repo's design folder only. Report any other change needed. "
                "Your brief names your designer kind: blind, informed or directed. In a blind designer, never read "
                "the current screen, its code, its screenshots, its mockups, or the repo's design spec and tokens.",
    "design-reviewer": "- Scope: design-reviewer. Never edit, write, stage, commit, or push. Read and render only.",
}
GENERAL_LINE = ("- Scope: do only what your brief names. A builder never edits tests; "
                "a test-author never edits product code; a reviewer and Explore never edit; "
                "a record-writer edits Markdown only.")
STASH_LINE = "- Never run git stash, git reset, git checkout <path>, or git restore."
STAGED_KEY = "git diff --cached --stat"  # the stable fragment of the staged-diff line; the wording may change
REFUSAL_WORDS = ("refus", "final", "base64")  # the stable words of the refusal line; its wording may change


def is_refusal_line(line):
    """True when a line holds every refusal word, case-insensitively."""
    low = line.lower()
    return all(word in low for word in REFUSAL_WORDS)
# Non-scope lines in hook order, after the scope line. Builder, test-author, record-writer, designer and any
# unknown type commit and push; reviewer, Explore, Plan, claude-code-guide and design-reviewer do not, so they
# get the shorter set. The staged-diff line is not in this list: line_set_check(staged=True) leaves it out.
WRITER_RULES = [
    "Standing rules for this agent:",
    STASH_LINE,
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


def payload(agent_type=MISSING):
    """One SubagentStart payload, shaped as the docs: session_id, transcript_path, cwd,
    permission_mode, hook_event_name, agent_id, agent_type. `agent_type` MISSING drops the key."""
    body = {
        "session_id": "abc123",
        "transcript_path": CWD + "/transcript.jsonl",
        "cwd": CWD,
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


def builder_scope_check(*parts):
    """Build a check: exactly one scope line, and it holds every part, case-insensitively."""
    def check(text):
        scopes = scope_lines(text)
        if len(scopes) != 1:
            return "want one scope line, got %d" % len(scopes)
        low = scopes[0].lower()
        for part in parts:
            if part not in low:
                return "scope line lacks %r: %r" % (part, scopes[0][:120])
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
    ("rule: no git stash, git reset, git checkout <path>, or git restore",
     ("Never run", "git stash", "git reset", "git checkout <path>", "git restore")),
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
        rules = [line for line in rules if not is_refusal_line(line)]  # refusal_line_check pins it, once per type
        if staged:
            rules = [line for line in rules if STAGED_KEY not in line]
        if rules == expected:
            return None
        if len(rules) != len(expected):
            return "%d non-scope lines, want %d" % (len(rules), len(expected))
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
    add("line set: %s gets the five-line set" % _t, "context", payload(_t),
        line_set_check(READER_RULES))
# Plugin-prefixed read-only types take the reader set too (the prefix split must reach them).
for _t in ["my-plugin:reviewer", "ns:Explore"]:
    add("line set: plugin-prefixed %s gets the five-line set" % _t, "context", payload(_t),
        line_set_check(READER_RULES))


def stash_check():
    """The stash line is exact, for every agent type."""
    for agent_type in TYPES + ["Plan", MISSING]:
        text, problem = context_for(payload(agent_type))
        if problem:
            return problem
        if STASH_LINE not in text.split("\n"):
            return "agent type %r lacks the exact stash line" % (agent_type,)
    return None


add("rules: the stash line is exactly 'Never run git stash, git reset, git checkout <path>, "
    "or git restore' for every agent type", "custom", fn=stash_check)


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

# SCOPE: each of the five types gets its own full scope line, and only that one.
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
add("case: explore gets the five-line set", "context", payload("explore"), line_set_check(READER_RULES))

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

# The builder never edits tests, and may add mutants to hooks/mutate_guard.py only when the brief asks.
add("builder scope: says never edit tests", "context", payload("builder"),
    builder_scope_check("never edit tests"))
add("builder scope: allows adding mutants to hooks/mutate_guard.py when the brief asks",
    "context", payload("builder"),
    builder_scope_check("mutant", "hooks/mutate_guard.py", "brief asks"))

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
CITE_STAMP = {
    "kinds": [
        {"id": "decision", "folder": "decisions", "prefix": "D", "idTemplate": "{prefix}{n}"},
        {"id": "finding", "folder": "findings", "prefix": "F", "idTemplate": "{prefix}{n}"},
        {"id": "question", "folder": "questions", "prefix": "Q", "idTemplate": "{prefix}{n}"},
    ],
    "cite": {"pattern": "([DFQ])‹([a-z0-9-]+)›", "prefixGroup": 1, "slugGroup": 2, "template": "{id}",
             "form": "{prefix}‹{slug}›"},  # cite.form is the one source for the brief line
}


def brief_for_stamp(stamp):
    """Run the hook in a repo whose .github/stamp.json holds `stamp`. Return (text, problem)."""
    root = tempfile.mkdtemp(prefix="agent-brief-cite-")
    try:
        os.makedirs(os.path.join(root, ".github"))
        with open(os.path.join(root, ".github", "stamp.json"), "w", encoding="utf-8") as fh:
            json.dump(stamp, fh)
        body = json.loads(payload("builder"))
        body["cwd"] = root
        return context_for(json.dumps(body))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def cite_form_check():
    """A repo whose stamp.json carries cite.form gets one brief line that carries every kind's form."""
    text, problem = brief_for_stamp(CITE_STAMP)
    if problem:
        return problem
    forms = ["%s‹slug›" % letter for letter in ("D", "F", "Q")]  # spelled as escapes
    if not has_line(text, *forms):
        return "no one brief line carries the form of each kind (D, F, Q) from the repo's stamp.json"
    if len(text.split("\n")) >= 20:
        return "the context is %d lines, want fewer than 20" % len(text.split("\n"))
    return None


def cite_form_absent_check():
    """A stamp.json with cite.pattern and no cite.form adds no cite line: no form is derived."""
    stamp = json.loads(json.dumps(CITE_STAMP))
    del stamp["cite"]["form"]
    text, problem = brief_for_stamp(stamp)
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


def agent_files_with(holds):
    """The agents/*.md files with one line that `holds` accepts, as (names, None), or (None, problem) when the
    folder cannot be read. The one walk of agents/ that the copies checks share."""
    names = []
    try:
        for name in sorted(os.listdir(AGENTS_DIR)):
            if name.endswith(".md"):
                with open(os.path.join(AGENTS_DIR, name), encoding="utf-8") as handle:
                    if any(holds(line) for line in handle.read().split("\n")):
                        names.append("agents/" + name)
    except OSError as exc:
        return None, "agents/ cannot be read: %s" % exc
    return names, None


def copies_check():
    """No agent file carries its own copy of the staged-diff step."""
    copies, problem = agent_files_with(lambda line: STAGED_KEY in line)
    if problem:
        return problem
    if copies:
        return "own copy of %r in %s; the one home is agent_brief's COMMON" % (STAGED_KEY, ", ".join(copies))
    return None


def refusal_copies_check():
    """No agent file carries its own copy of the refusal line: one line holding refus and base64. The one home is
    agent_brief's COMMON, so a brief and an agent file cannot disagree about the refusal rule."""
    copies, problem = agent_files_with(lambda line: "refus" in line.lower() and "base64" in line.lower())
    if problem:
        return problem
    if copies:
        return "own copy of the refusal line in %s; the one home is agent_brief's COMMON" % ", ".join(copies)
    return None


add("staged-diff step: agents/ names every agent, with committing and read-only types both present",
    "custom", fn=agent_list_check)
for _name, _writes in AGENT_ENTRIES:
    add("staged-diff step, agent %s: one line if it commits, none if it is read-only" % _name,
        "custom", fn=staged_check(_name, _writes))
add("staged-diff step: no agents/*.md file carries its own copy of it", "custom", fn=copies_check)
add("refusal line: no agents/*.md file carries its own copy of it", "custom", fn=refusal_copies_check)


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


# REFUSAL LINE. Every type, reviewer and Explore included, gets one line that says a refusal is final: report it,
# never re-send the command in another form. The words are pinned, not the wording. Each type is one case, so a
# red names the type that lacks the line.
REFUSAL_TYPES = TYPES + ["Plan", "claude-code-guide", "my-plugin:reviewer", "ns:Explore", "some-new-agent", MISSING]


def refusal_line_check(agent_type):
    """Build a check: the brief for `agent_type` holds exactly one line that holds every refusal word."""
    def check():
        text, problem = context_for(payload(agent_type))
        if problem:
            return problem
        hits = [line for line in text.split("\n") if is_refusal_line(line)]
        if len(hits) != 1:
            return "want one line that holds %s, got %d" % (" and ".join(REFUSAL_WORDS), len(hits))
        return None
    return check


for _t in REFUSAL_TYPES:
    add("refusal line, %s: one line says a refusal is final" % ("a missing agent type" if _t is MISSING else _t),
        "custom", fn=refusal_line_check(_t))


def main():
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
