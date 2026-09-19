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

The allowlist-regression case (`claude-opus-4-sonnet-alias`) is the one that must
fail against the 8d30693 hook: that hook's `is_above_sonnet` was a substring test,
so an id merely containing "sonnet" passed with no justification, opus family or
not. Point GATE_UNDER_TEST at a copy of that old file to see it fail there and
pass here:

    GATE_UNDER_TEST=/path/to/old/model_gate.py python hooks/test_model_gate.py
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

# --------------------------------------------------------------------------- Change 1: is_above_sonnet allowlist

BELOW_BAR_IDS = [
    "sonnet",
    "haiku",
    "claude-sonnet-5",
    "claude-haiku-4-5-20251001",
    "claude-3-5-sonnet-20241022",
    "us.anthropic.claude-sonnet-5",
    "anthropic/claude-sonnet-5",
    "claude-sonnet-5[1m]",
]

ABOVE_BAR_IDS = [
    "claude-opus-5",
    "claude-fable-5-1",
    "claude-opus-4-sonnet-alias",
    "sonnet-opus",
    "gpt-5",
    "some-unknown-model",
    "claude-sonnet",  # no version: an unrecognised shape, not assumed cheap
]

for model_id in BELOW_BAR_IDS:
    add("allowlist: %r is below the bar -> allow, no marker needed" % model_id,
        agent(model=model_id, prompt="Do the task."),
        {"decision": "allow"})

for model_id in ABOVE_BAR_IDS:
    add("allowlist: %r is above the bar -> deny without a marker" % model_id,
        agent(model=model_id, prompt="Do the task."),
        {"decision": "deny", "reason_excludes": [model_id]})

# This is the case that must fail against the 8d30693 hook: its substring test let
# "sonnet" anywhere in the id pass, opus family or not. See the module docstring
# for how to run this file against a copy of the old hook.
add("allowlist regression: claude-opus-4-sonnet-alias denies although it contains 'sonnet'",
    agent(model="claude-opus-4-sonnet-alias", prompt="Do the task."),
    {"decision": "deny", "reason_excludes": ["claude-opus-4-sonnet-alias"]})

add("allowlist: above-bar id with a valid marker -> ask",
    agent(model="claude-opus-4-sonnet-alias", prompt="Do the task.\n" + GOOD_MARKER),
    {"decision": "ask", "reason_includes": ["needs deep multi-file refactor reasoning"]})

# --------------------------------------------------------------------------- Change 2: Workflow shape test

add("workflow shape: quoted literal below the bar -> allow",
    workflow(script='agent(prompt, { model: "%s" })' % SONNET),
    {"decision": "allow"})

add("workflow shape: quoted literal above the bar, no marker -> deny",
    workflow(script='agent(prompt, { model: "%s" })' % OPUS),
    {"decision": "deny", "reason_excludes": [OPUS]})

add("workflow shape: quoted literal above the bar, with marker -> ask",
    workflow(script='agent(prompt, { model: "%s" })\n// %s' % (OPUS, GOOD_MARKER)),
    {"decision": "ask", "reason_includes": ["needs deep multi-file refactor reasoning"]})

add("workflow shape: variable value, no marker -> deny (unprovable, not allowed by default)",
    workflow(script="const M = '%s'\nagent(prompt, { model: M })" % OPUS),
    {"decision": "deny"})

add("workflow shape: variable value, with marker -> ask",
    workflow(script=(
        "const M = '%s'\n"
        "// %s\n"
        "agent(prompt, { model: M })" % (OPUS, GOOD_MARKER)
    )),
    {"decision": "ask", "reason_includes": ["needs deep multi-file refactor reasoning"]})

add("workflow shape: template literal value -> deny (unprovable)",
    workflow(script="agent(prompt, { model: `claude-${tier}` })"),
    {"decision": "deny"})

add("workflow shape: a `//` commented line naming opus and nothing else -> allow",
    workflow(script='// agent(prompt, { model: "%s" })' % OPUS),
    {"decision": "allow"})

add("workflow shape: double-quoted key, no marker -> deny",
    workflow(script='const cfg = { "model": "%s" }; agent(prompt, cfg);' % OPUS),
    {"decision": "deny", "reason_excludes": [OPUS]})

add("workflow shape: double-quoted key, with marker -> ask",
    workflow(script=(
        'const cfg = { "model": "%s" }; agent(prompt, cfg);\n// %s'
        % (OPUS, GOOD_MARKER)
    )),
    {"decision": "ask", "reason_includes": ["needs deep multi-file refactor reasoning"]})

add("workflow shape: single-quoted key, no marker -> deny",
    workflow(script="const cfg = { 'model': '%s' }; agent(prompt, cfg);" % OPUS),
    {"decision": "deny", "reason_excludes": [OPUS]})

add("workflow shape: member assignment (opts.model = ...), no marker -> deny",
    workflow(script="opts.model = '%s';\nagent(prompt, opts);" % OPUS),
    {"decision": "deny", "reason_excludes": [OPUS]})

add("workflow shape: bracketed quoted-key member assignment (opts[\"model\"] = ...), no marker -> deny",
    workflow(script='opts["model"] = \'%s\';\nagent(prompt, opts);' % OPUS),
    {"decision": "deny", "reason_excludes": [OPUS]})

add("workflow shape: double-quoted key with a below-the-bar literal -> allow",
    workflow(script='const cfg = { "model": "%s" }; agent(prompt, cfg);' % SONNET),
    {"decision": "allow"})

add("workflow shape: fullwidth digit in the id reads as above the bar -> deny",
    workflow(script='agent(prompt, { model: "claude-sonnet-５" })'),
    {"decision": "deny"})

add("workflow shape: `//` line naming opus with a quoted key -> allow",
    workflow(script='// const cfg = { "model": "%s" };' % OPUS),
    {"decision": "allow"})

add("workflow shape: meta block's phase model override is not an agent option -> allow",
    workflow(script=(
        "export const meta = {\n"
        "  name: 'x',\n"
        "  description: 'y',\n"
        "  phases: [{ title: 'Scan', model: '%s' }],\n"
        "}\n"
        "agent('hi')" % OPUS
    )),
    {"decision": "allow"})

# --------------------------------------------------------------------------- third review pass: backtick key, restricted `=`

add("workflow shape: backtick-quoted key, above-bar literal, no marker -> deny",
    workflow(script='agent(p, { `model`: "%s" })' % OPUS),
    {"decision": "deny", "reason_excludes": [OPUS]})

add("workflow shape: backtick-quoted key, above-bar literal, with marker -> ask",
    workflow(script='agent(p, { `model`: "%s" })\n// %s' % (OPUS, GOOD_MARKER)),
    {"decision": "ask", "reason_includes": ["needs deep multi-file refactor reasoning"]})

add("workflow shape: backtick-quoted key, below-bar literal -> allow",
    workflow(script='agent(p, { `model`: "%s" })' % SONNET),
    {"decision": "allow"})

add("finding 2 regression: bare `model = ...` in a log line, no member/bracket key -> allow",
    workflow(script='console.log("Setting model = default for this run");'),
    {"decision": "allow"})

add("finding 2 regression: bare `model = someVariable` inside prose -> allow",
    workflow(script='const note = "Please set model = someVariable before running this.";'),
    {"decision": "allow"})

add("workflow shape: dot member assignment (opts.model = ...) still denies after narrowing `=`",
    workflow(script="opts.model = '%s';\nagent(prompt, opts);" % OPUS),
    {"decision": "deny", "reason_excludes": [OPUS]})

add("workflow shape: double-quoted bracketed key (opts[\"model\"] = ...) still denies after narrowing `=`",
    workflow(script='opts["model"] = \'%s\';\nagent(prompt, opts);' % OPUS),
    {"decision": "deny", "reason_excludes": [OPUS]})

add("workflow shape: single-quoted bracketed key (opts['model'] = ...) still denies after narrowing `=`",
    workflow(script="opts['model'] = '%s';\nagent(prompt, opts);" % OPUS),
    {"decision": "deny", "reason_excludes": [OPUS]})

add("workflow shape: member assignment with an unprovable value, no marker -> deny",
    workflow(script="opts.model = M;\nagent(prompt, opts);"),
    {"decision": "deny"})


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
