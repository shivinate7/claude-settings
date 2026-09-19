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
design and the three gaps this closes.

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


def is_above_sonnet(model) -> bool:
    """True when `model` names neither sonnet nor haiku.

    An empty or absent value is not above Sonnet: nothing was asked for above the
    default. Matches the substring test the earlier hook used, so a model id such
    as `claude-opus-4-1-20250805` still trips the gate and `claude-sonnet-5` does
    not.
    """
    if not isinstance(model, str) or not model.strip():
        return False
    lowered = model.lower()
    return "sonnet" not in lowered and "haiku" not in lowered


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


# A model name inside a script: `"model": "opus-..."`, `model: 'opus-...'`, or
# `model="opus-..."`, whichever quoting the script's own language uses. The value
# is read by KEY, same as the Agent case, never by scanning the whole script for
# any quoted word.
SCRIPT_MODEL_RE = re.compile(
    r"""model["']?\s*[:=]\s*["']([^"']+)["']"""
)


def script_models(text: str):
    """Yield every model value a script assigns to a `model` key."""
    if not isinstance(text, str):
        return
    for match in SCRIPT_MODEL_RE.finditer(text):
        yield match.group(1)


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
    script = tool_input.get("script")
    script_text = script if isinstance(script, str) else ""
    script_text += "\n" + read_script_path(tool_input.get("scriptPath"))

    found_model = ""
    for value in script_models(script_text):
        if is_above_sonnet(value):
            found_model = value
            break
    if not found_model:
        return
    judge_against_text(found_model, script_text)


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
