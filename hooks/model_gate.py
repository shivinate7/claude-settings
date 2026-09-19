#!/usr/bin/env python3
"""The subagent model justification gate.

Claude Code runs this script before an `Agent` or `Workflow` call. It reads one JSON
object on stdin and answers on stdout, the same contract as `guard.py`:

  stdin  : {"tool_name": str, "tool_input": {...}, ...}
  allow  : print nothing, exit 0
  refuse : print one hookSpecificOutput object with "deny" or "ask", exit 0

Fail open. Unreadable input, a payload that is not an object, a missing key, or a
tool this gate does not judge, all allow the call. A gate bug must never brick a
session.

CLAUDE.md: "Justify a model above Sonnet in one line." and "Once set up, turn each
rule below into a hook or check." This gate is that check for the subagent-model
rule. It replaces an inline shell hook that grepped the whole payload for the first
`"model"` string. A grep reads prompt text the same as the real field, so a prompt
that quotes a model name masks the field it should read. This gate parses the
payload with `json.loads` and reads `tool_input.model` by key, never by pattern.

Rules, first match wins. See decisions/subagent-model-justification.md for the
design and the gaps this closes.

  1 Agent, tool_input.model set and above Sonnet
      -> needs a `MODEL-JUSTIFICATION: <text>` line in tool_input.prompt,
         at least twelve characters of text after the colon.
      no marker or a marker too short  -> deny
      marker present                   -> ask, with the justification text as the
                                           reason, so an approver decides against a
                                           stated case
  2 Agent, tool_input.subagent_type == "fork"
      -> same rule as 1. A fork carries no `model` field of its own and inherits
         the parent session model, which this hook cannot read from its stdin
         payload. It is treated as always above Sonnet, so every fork needs the
         marker. See the deviation note in the decision entry: the approved
         option asked for a session-model test, which this hook cannot make
         without guessing.
  3 Workflow, tool_input.script or tool_input.scriptPath names a model above
    Sonnet
      -> same rule as 1, checked against the script text. The marker may sit
         anywhere in the script, including a comment.
  4 anything else                        -> allow

A refusal never names the model it refused. CLAUDE.md: "A refusal's printed remedy
never names the forbidden target." The requested model reaches the log line style
only through the "ask" reason, where it is the approver's own read, chosen with the
justification text, not a bare denial.
"""

import json
import os
import re
import sys


MARKER_RE = re.compile(r"MODEL-JUSTIFICATION:\s*(.+)")
MIN_JUSTIFICATION_CHARS = 12

DENY_REASON = (
    "A subagent model above the Sonnet default needs a one-line justification "
    "in the brief. Add a line `MODEL-JUSTIFICATION: <why this model>` with at "
    "least twelve characters of reason, then retry."
)


def _force_utf8_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


_VENDOR_PREFIX_RE = re.compile(r"^(?:us|eu|apac)\.anthropic\.")
_VENDOR_SLASH_RE = re.compile(r"^anthropic/")
_CONTEXT_SUFFIX_RE = re.compile(r"\[[^\]]*\]$")

# A model id is below the bar only when it matches one of these recognised Sonnet or
# Haiku shapes, once `_normalize_model_id` has stripped an optional vendor prefix and
# an optional trailing context-window suffix. An id that matches none of these shapes
# is unrecognised, not assumed cheap: it needs the marker like any above-bar id.
_BELOW_BAR_RE = re.compile(
    r"""^(?:
        (?:sonnet|haiku)                                   # bare family name
        |claude-(?:sonnet|haiku)-\d+(?:-\d+)*(?:-\d{8})?    # claude-sonnet-<version>[-<date>]
        |claude-\d+(?:-\d+)*-(?:sonnet|haiku)(?:-\d{8})?    # claude-<version>-sonnet[-<date>]
    )$""",
    re.VERBOSE,
)

# A second family token anywhere in the id overrides a shape match. An alias or a
# fine-tuned name can still contain "sonnet" while naming a different family underneath,
# for example `claude-opus-4-sonnet-alias`.
_OTHER_FAMILY_RE = re.compile(r"\b(?:opus|fable)\b")


def _normalize_model_id(model: str) -> str:
    """Strip an optional vendor prefix and an optional trailing context suffix."""
    normalized = model.strip().lower()
    normalized = _VENDOR_PREFIX_RE.sub("", normalized)
    normalized = _VENDOR_SLASH_RE.sub("", normalized)
    normalized = _CONTEXT_SUFFIX_RE.sub("", normalized)
    return normalized


def is_above_sonnet(model) -> bool:
    """True unless `model` matches a recognised Sonnet or Haiku id.

    An empty or absent value is not above Sonnet: nothing was asked for above the
    default. The harness then applies the Sonnet default from
    `env.CLAUDE_CODE_SUBAGENT_MODEL`.

    This is an allowlist, not the substring test the earlier version of this hook
    used. That test treated any id containing "sonnet" or "haiku" anywhere as below
    the bar, so `claude-opus-4-sonnet-alias` passed with no justification even
    though "opus" is the family that matters. Fixing the cause means testing
    shape, not substring: see `_BELOW_BAR_RE` and `_OTHER_FAMILY_RE`, and
    decisions/subagent-model-justification.md for the gap this closes.
    """
    if not isinstance(model, str) or not model.strip():
        return False
    normalized = _normalize_model_id(model)
    if _OTHER_FAMILY_RE.search(normalized):
        return True
    return not _BELOW_BAR_RE.match(normalized)


def find_marker(text) -> str:
    """Return the justification text when a valid marker is present, else ''.

    Valid means at least MIN_JUSTIFICATION_CHARS characters of trimmed text after
    the colon. The search is case sensitive, matching the marker's own spelling.
    """
    if not isinstance(text, str) or not text:
        return ""
    match = MARKER_RE.search(text)
    if not match:
        return ""
    justification = match.group(1).strip()
    if len(justification) < MIN_JUSTIFICATION_CHARS:
        return ""
    return justification


def emit_ask(model: str, justification: str) -> None:
    reason = "Requested model: %s. Stated justification: \"%s\"" % (
        model or "(unnamed)", justification,
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }))


def emit_deny() -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": DENY_REASON,
        }
    }))


def judge_against_text(model: str, text: str) -> None:
    """Apply rule 1's shape: deny with no name, or ask with the stated case."""
    justification = find_marker(text)
    if justification:
        emit_ask(model, justification)
    else:
        emit_deny()


# A `model` option inside a script: `model: "opus-..."`, `model: M`, `model:
# `${tier}``, whatever the script's own language does with it. This is a
# deliberately crude text test, not a JavaScript parser: a PreToolUse hook cannot
# run the script, so a value that is not a plain quoted literal (a variable, a
# concatenation, a ternary, a member expression, a template literal, a read from
# `args`) is a value this gate cannot resolve. It cannot prove that value is below
# the bar, so it cannot allow it either -- an unprovable `model` option needs the
# marker, the same as a proven-above-bar one. A false ask is the accepted cost of
# an unprovable value; the marker is how the owner clears it. Two things are
# skipped on purpose so this stays a test of agent options, not of any "model"
# text at all: a line the script itself comments out (`//` starts the line), and
# the script's own `export const meta = {...}` header, whose `phases[].model`
# names a phase's model override, not an agent call.
SCRIPT_MODEL_RE = re.compile(r"""\bmodel\b\s*:\s*([^,;}\n]+)""")

_META_BLOCK_RE = re.compile(r"\bmeta\s*=\s*\{")

_QUOTED_LITERAL_RE = re.compile(r"""^(['"])((?:(?!\1).)*)\1$""")


def _strip_meta_block(text: str) -> str:
    """Drop the script's `meta = {...}` header, crudely brace-matched.

    If the braces do not balance (a truncated script, an edge this text test does
    not parse), everything from the header onward is dropped. The safer miss for
    a text test is under-reading a decoy script, not over-reading one.
    """
    match = _META_BLOCK_RE.search(text)
    if not match:
        return text
    depth = 0
    for index in range(match.end() - 1, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[: match.start()] + text[index + 1 :]
    return text[: match.start()]


def script_models(text: str):
    """Yield (raw_value, literal) for each `model:` option found in `text`.

    `literal` is the quoted string's content when the value is a plain quoted
    literal, else None: a variable, a template literal, a concatenation, a
    ternary, a member expression, or anything else this text test does not
    resolve to a value on its own.
    """
    if not isinstance(text, str):
        return
    for line in _strip_meta_block(text).splitlines():
        if line.strip().startswith("//"):
            continue
        for match in SCRIPT_MODEL_RE.finditer(line):
            value = re.sub(r"//.*$", "", match.group(1)).strip()
            literal_match = _QUOTED_LITERAL_RE.match(value)
            yield value, (literal_match.group(2) if literal_match else None)


def read_script_path(path) -> str:
    if not isinstance(path, str) or not path:
        return ""
    try:
        if not os.path.isfile(path) or not os.access(path, os.R_OK):
            return ""
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except Exception:
        return ""


def handle_agent(tool_input: dict) -> None:
    model = tool_input.get("model")
    prompt = tool_input.get("prompt")
    if isinstance(model, str) and is_above_sonnet(model):
        judge_against_text(model, prompt)
        return
    if tool_input.get("subagent_type") == "fork":
        judge_against_text("fork (inherits the session model)", prompt)
        return


def handle_workflow(tool_input: dict) -> None:
    """Rule 3, a shape test on the script's `model:` options.

    A quoted literal is judged by value, like the Agent case: below the bar
    allows, above the bar needs the marker. A `model:` option set any other way
    -- a variable, a template literal, a concatenation, a ternary, a member
    expression, an `args` read -- cannot be proven below the bar from static
    text, so it needs the marker too. See `script_models` and
    decisions/subagent-model-justification.md for the gap this closes: a script
    that names its model indirectly used to evade the gate outright.
    """
    script = tool_input.get("script")
    script_text = script if isinstance(script, str) else ""
    script_text += "\n" + read_script_path(tool_input.get("scriptPath"))

    found_model = ""
    unprovable = False
    for _raw_value, literal in script_models(script_text):
        if literal is not None:
            if is_above_sonnet(literal):
                found_model = literal
                break
            continue
        unprovable = True
        break

    if not found_model and not unprovable:
        return
    label = found_model or "an indirectly set model option (the gate cannot read its value)"
    judge_against_text(label, script_text)


def main() -> None:
    _force_utf8_streams()
    try:
        raw = sys.stdin.read()
    except Exception:
        return
    try:
        payload = json.loads(raw)
    except Exception:
        return
    if not isinstance(payload, dict):
        return

    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return

    try:
        if tool_name == "Agent":
            handle_agent(tool_input)
        elif tool_name == "Workflow":
            handle_workflow(tool_input)
    except Exception:
        return  # fail open: a gate bug must never brick a session


if __name__ == "__main__":
    main()
