#!/usr/bin/env python3
"""Cases for hooks/agent_brief.py, a SubagentStart hook. Standard library only.

Run it from the repository root:

    python hooks/test_agent_brief.py

Contract, from the owner ruling of 2026-10-12 (the hook's own docstring). On each subagent start
the hook prints one JSON object on stdout and exits 0:
    {"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": "<text>"}}
- additionalContext holds the standing rules: a scope line that follows `agent_type` from the hook
  input (builder, test-author, reviewer, Explore, record-writer), the general scope line for any
  other or missing type, and fewer than 20 lines in all.
- Junk or empty stdin: no output on stdout, no stderr, exit 0. The hook fails open.

Interface (Claude Code hooks reference, SubagentStart): stdin is one JSON object with
`hook_event_name` "SubagentStart", `agent_id`, and `agent_type`.

Override the module under test with the env var AGENT_BRIEF_UNDER_TEST.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.environ.get("AGENT_BRIEF_UNDER_TEST") or os.path.join(HERE, "agent_brief.py")

CWD = "/tmp/agent-brief-test"
MISSING = object()  # payload() leaves agent_type out of the JSON when this is passed
TYPES = ["builder", "test-author", "reviewer", "Explore", "record-writer"]
SCOPE_PREFIX = {
    "builder": "Scope: builder.",
    "test-author": "Scope: test-author.",
    "reviewer": "Scope: reviewer.",
    "Explore": "Scope: Explore.",
    "record-writer": "Scope: record-writer.",
}
GENERAL_PREFIX = "Scope: do only what your brief names"

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


def scope_check(expected):
    """Build a check: exactly one scope line, and it starts with the expected scope text."""
    want = SCOPE_PREFIX.get(expected, GENERAL_PREFIX)

    def check(text):
        scopes = [line for line in text.split("\n") if line.startswith("- Scope")]
        if len(scopes) != 1:
            return "want one scope line, got %d" % len(scopes)
        if not scopes[0].startswith("- " + want):
            return "scope line is %r" % scopes[0][:90]
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
    if case["kind"] == "silent":
        got = run(case["stdin"])
        if got is None:
            return "the hook file is missing: %s" % HOOK
        rc, out, err = got
        if rc != 0:
            return "exit %d: %s" % (rc, err.strip()[:120])
        if out.strip():
            return "expected no output, got %s" % out.strip()[:120]
        if err.strip():
            return "expected no stderr, got %s" % err.strip()[:120]
        return None
    text, problem = context_for(case["stdin"])
    if problem:
        return problem
    return case["check"](text)


# SHAPE: every type, and the general case, print one JSON object of the documented shape.
for _t in TYPES:
    add("shape: %s output is one JSON object with the documented shape" % _t, "context",
        payload(_t), lambda text: None)
add("shape: a missing agent type output is one JSON object with the documented shape",
    "context", payload(), lambda text: None)

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


def common_rules_check():
    base = None
    for agent_type in TYPES + ["Plan", MISSING]:
        text, problem = context_for(payload(agent_type))
        if problem:
            return problem
        rules = [line for line in text.split("\n") if not line.startswith("- Scope")]
        if base is None:
            base = rules
        elif rules != base:
            return "the non-scope lines differ for agent type %r" % (agent_type,)
    return None


add("rules: the non-scope lines are identical for every agent type", "custom",
    fn=common_rules_check)


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

# SCOPE: each of the five types gets its own scope line, and only that one.
for _t in TYPES:
    add("scope: %s gets its own scope line" % _t, "context", payload(_t), scope_check(_t))

# GENERAL: an unknown, odd, or missing type gets the general scope line.
GENERAL_CASES = [
    ("an unknown agent type gets the general line", payload("Plan")),
    ("an empty agent type gets the general line", payload("")),
    ("an agent type in other case gets the general line", payload("Builder")),
    ("an agent type with a trailing space gets the general line", payload("builder ")),
    ("a null agent type gets the general line", payload(None)),
    ("a number agent type gets the general line", payload(7)),
    ("a list agent type gets the general line", payload(["builder"])),
    ("a missing agent type gets the general line", payload()),
    ("a JSON array on stdin gets the general line", "[1, 2]"),
    ("a JSON string on stdin gets the general line", '"builder"'),
]
for _name, _stdin in GENERAL_CASES:
    add("general: " + _name, "context", _stdin, scope_check("general"))

# SILENT: junk or empty stdin gives no output, no stderr, exit 0.
SILENT_CASES = [
    ("empty stdin gives no output", ""),
    ("whitespace-only stdin gives no output", "  \n"),
    ("junk stdin gives no output", "not json"),
    ("truncated JSON gives no output", '{"agent_type": "builder"'),
    ("non-text bytes on stdin give no output", "\x00\x01 junk {"),
]
for _name, _stdin in SILENT_CASES:
    add("silent: " + _name, "silent", _stdin)


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
