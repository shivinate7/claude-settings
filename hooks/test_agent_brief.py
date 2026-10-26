#!/usr/bin/env python3
"""Cases for hooks/agent_brief.py, a SubagentStart hook. Standard library only.

Run it from the repository root:

    python hooks/test_agent_brief.py

Contract (the hook's own docstring). On each agent start
the hook prints one JSON object on stdout and exits 0:
    {"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": "<text>"}}
- additionalContext holds the standing rules: a scope line that follows `agent_type` from the hook
  input (builder, test-author, reviewer, Explore, record-writer), the general scope line for any
  other or missing type, and fewer than 20 lines in all. Each scope line is pinned in full.
- The push line, the commit-trailer line and the record-path line appear for builder,
  test-author, record-writer and any other type; never for reviewer, Explore, Plan or
  claude-code-guide, which only read.
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
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.environ.get("AGENT_BRIEF_UNDER_TEST") or os.path.join(HERE, "agent_brief.py")

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
    "designer": "- Scope: designer. Edit files in the repo's design folder only. Report any other change needed.",
    "design-reviewer": "- Scope: design-reviewer. Never edit, write, stage, commit, or push. Read and render only.",
}
GENERAL_LINE = ("- Scope: do only what your brief names. A builder never edits tests; "
                "a test-author never edits product code; a reviewer and Explore never edit; "
                "a record-writer edits Markdown only.")
STASH_LINE = "- Never run git stash, git reset, git checkout <path>, or git restore."
# Non-scope lines in hook order. Builder, test-author, record-writer and any unknown type commit
# and push; reviewer, Explore, Plan and claude-code-guide do not, so they get the shorter set.
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


def line_set_check(expected):
    """Build a check: the non-scope lines equal `expected`, in order."""
    def check(text):
        rules = [line for line in text.split("\n") if not line.startswith("- Scope")]
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
    add("line set: %s gets the nine-line set" % _t, "context", payload(_t),
        line_set_check(WRITER_RULES))
add("line set: a general (unknown) type gets the nine-line set", "context",
    payload("some-new-agent"), line_set_check(WRITER_RULES))
add("line set: a missing agent type gets the nine-line set", "context", payload(),
    line_set_check(WRITER_RULES))
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
