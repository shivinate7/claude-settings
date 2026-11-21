"""The one reader of the stdout line that a lifted act prints (owner ruling, 22:17 CST Nov 20, option a).

A valid override that lifts a refusal prints one PreToolUse JSON object: hookSpecificOutput.additionalContext
names the lifted rule and says override, and there is no permissionDecision, so the normal permission flow runs.
hooks/guard_core.py refuse() prints it. The guard tests (tests/guard/) and the hook tests (hooks/test_*.py) import
these readers. Nothing copies them.
"""
import json


def context_block(text):
    """The hookSpecificOutput of `text` when `text` is one PreToolUse JSON object with a string additionalContext and
    no permissionDecision, else None."""
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return None
    block = parsed.get("hookSpecificOutput") if isinstance(parsed, dict) else None
    if not isinstance(block, dict) or block.get("hookEventName") != "PreToolUse":
        return None
    if "permissionDecision" in block or not isinstance(block.get("additionalContext"), str):
        return None
    return block


def names_lift(text, rule):
    """True when `text` is the one line a lifted act prints, and its additionalContext names `rule` and says override.
    `rule` is one rule name or a tuple of them."""
    block = context_block(text)
    if block is None:
        return False
    context = block["additionalContext"]
    names = (rule,) if isinstance(rule, str) else tuple(rule or ())
    return "override" in context and any(name and name in context for name in names)


def lift_of(got, reason, rule):
    """True when a guard verdict is a lift of `rule`. decide() in tests/guard reads a line with no permissionDecision
    as "unparsable", so only that verdict with the one line that names `rule` counts as a lift."""
    return got == "unparsable" and names_lift(reason, rule)
