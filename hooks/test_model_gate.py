#!/usr/bin/env python3
"""Cases for hooks/model_gate.py. Standard library only, and no test runner.

Run it from the repository root:

    python hooks/test_model_gate.py

Each case drives the gate as Claude Code drives it: one JSON object on stdin, and
the decision read back off stdout. An empty stdout is an allow. Anything else is
parsed for permissionDecision.

The masking-regression case is the one that must fail against the OLD grep hook:
a prompt that quotes `"model": "sonnet"` while `tool_input.model` is an opus id.
The old hook greps the payload text and reads the quoted decoy. This gate parses
JSON and reads `tool_input.model` by key, so it must still deny.
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.environ.get("GATE_UNDER_TEST") or os.path.join(HERE, "model_gate.py")

OPUS = "claude-opus-4-1-20250805"
SONNET = "claude-sonnet-5"
GOOD_MARKER = "MODEL-JUSTIFICATION: needs deep multi-file refactor reasoning"
SHORT_MARKER = "MODEL-JUSTIFICATION: short"

CASES = []


def add(name, payload, expect):
    CASES.append({"name": name, "payload": payload, "expect": expect})


def agent(model=None, prompt="", subagent_type=None, **extra):
    tool_input = dict(extra)
    if model is not None:
        tool_input["model"] = model
    if subagent_type is not None:
        tool_input["subagent_type"] = subagent_type
    tool_input["prompt"] = prompt
    return {"tool_name": "Agent", "tool_input": tool_input}


def workflow(script=None, script_path=None):
    tool_input = {}
    if script is not None:
        tool_input["script"] = script
    if script_path is not None:
        tool_input["scriptPath"] = script_path
    return {"tool_name": "Workflow", "tool_input": tool_input}


# --------------------------------------------------------------------------- rule 1: Agent + model

add("agent opus, no marker -> deny, no model name in reason",
    agent(model=OPUS, prompt="Do the refactor."),
    {"decision": "deny", "reason_excludes": [OPUS]})

add("agent opus, valid marker -> ask, reason carries the justification",
    agent(model=OPUS, prompt="Do the refactor.\n" + GOOD_MARKER),
    {"decision": "ask", "reason_includes": ["needs deep multi-file refactor reasoning"]})

add("agent opus, marker under twelve characters -> deny",
    agent(model=OPUS, prompt="Do the refactor.\n" + SHORT_MARKER),
    {"decision": "deny"})

add("agent sonnet -> allow, no output",
    agent(model=SONNET, prompt="Do the refactor."),
    {"decision": "allow"})

add("agent with no model key -> allow",
    agent(prompt="Do the refactor."),
    {"decision": "allow"})

# --------------------------------------------------------------------------- rule 2: fork

add("agent fork, no marker -> deny",
    agent(subagent_type="fork", prompt="Continue the session."),
    {"decision": "deny"})

add("agent fork, valid marker -> ask",
    agent(subagent_type="fork", prompt="Continue the session.\n" + GOOD_MARKER),
    {"decision": "ask", "reason_includes": ["needs deep multi-file refactor reasoning"]})

# --------------------------------------------------------------------------- the masking regression

add("masking regression: decoy model in prompt text, real model is opus -> still deny",
    agent(model=OPUS, prompt='Some note says "model": "sonnet" but ignore that.'),
    {"decision": "deny", "reason_excludes": [OPUS]})

# --------------------------------------------------------------------------- rule 3: Workflow

add("workflow script names opus, no marker -> deny",
    workflow(script='const cfg = { agentType: "builder", model: "%s" };' % OPUS),
    {"decision": "deny"})

add("workflow script names opus, with marker in a comment -> ask",
    workflow(script=(
        '// %s\n'
        'const cfg = { agentType: "builder", model: "%s" };' % (GOOD_MARKER, OPUS)
    )),
    {"decision": "ask", "reason_includes": ["needs deep multi-file refactor reasoning"]})

add("workflow script names sonnet only -> allow",
    workflow(script='const cfg = { model: "%s" };' % SONNET),
    {"decision": "allow"})


def _workflow_scriptpath_cases():
    tmp = tempfile.mkdtemp(prefix="model_gate_cases_")
    no_marker = os.path.join(tmp, "wf_no_marker.js")
    with open(no_marker, "w", encoding="utf-8") as handle:
        handle.write('const cfg = { model: "%s" };' % OPUS)
    add("workflow scriptPath names opus, no marker -> deny",
        workflow(script_path=no_marker),
        {"decision": "deny"})

    with_marker = os.path.join(tmp, "wf_marker.js")
    with open(with_marker, "w", encoding="utf-8") as handle:
        handle.write('// %s\nconst cfg = { model: "%s" };' % (GOOD_MARKER, OPUS))
    add("workflow scriptPath names opus, with marker -> ask",
        workflow(script_path=with_marker),
        {"decision": "ask", "reason_includes": ["needs deep multi-file refactor reasoning"]})


_workflow_scriptpath_cases()

# --------------------------------------------------------------------------- fail open

add("malformed stdin (not JSON) -> allow",
    None,
    {"decision": "allow", "raw": "{not json"})

add("empty stdin -> allow",
    None,
    {"decision": "allow", "raw": ""})

add("non-object JSON (a bare list) -> allow",
    None,
    {"decision": "allow", "raw": "[1, 2, 3]"})

add("missing tool_name -> allow",
    {"tool_input": {"model": OPUS, "prompt": ""}},
    {"decision": "allow"})

add("tool_name not Agent or Workflow -> allow",
    {"tool_name": "Bash", "tool_input": {"model": OPUS, "prompt": ""}},
    {"decision": "allow"})


# --------------------------------------------------------------------------- the runner

def run_case(case):
    raw = case["expect"].get("raw")
    if raw is None:
        raw = json.dumps(case["payload"])
    result = subprocess.run(
        [sys.executable, GATE],
        input=raw,
        capture_output=True,
        text=True,
        timeout=15,
    )
    stdout = result.stdout.strip()
    expect = case["expect"]

    if expect["decision"] == "allow":
        if stdout:
            return "expected allow (empty stdout), got: %r" % stdout
        return ""

    if not stdout:
        return "expected %s, got empty stdout (allow)" % expect["decision"]
    try:
        parsed = json.loads(stdout)
    except Exception as exc:
        return "stdout is not valid JSON: %s (%r)" % (exc, stdout)

    hso = parsed.get("hookSpecificOutput", {})
    decision = hso.get("permissionDecision")
    reason = hso.get("permissionDecisionReason", "")

    if decision != expect["decision"]:
        return "expected decision %s, got %s" % (expect["decision"], decision)

    for needle in expect.get("reason_includes", []):
        if needle not in reason:
            return "reason missing %r: %r" % (needle, reason)
    for needle in expect.get("reason_excludes", []):
        if needle in reason:
            return "reason must not name the refused model, found %r in: %r" % (needle, reason)
    return ""


def main() -> int:
    failures = 0
    for case in CASES:
        error = run_case(case)
        if error:
            failures += 1
            print("FAIL: %s\n      %s" % (case["name"], error))
        else:
            print("PASS: %s" % case["name"])
    total = len(CASES)
    print("\n%d/%d passed" % (total - failures, total))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
