"""The guard's workflow-args family: the rules on the arguments of a Workflow call.

guard.py is the only entry point, and it calls these checks in its fixed order. Other files reach
these names through `guard`.

Rule index (moved from guard.py):

  workflow-args-shape-check
      deny. A Workflow call whose `args` is, or holds as an array item or object value (one
      level down), a placeholder: the whole value is an all-caps word with an underscore
      (`FACT_CLOSE_PLACEHOLDER`, `PR_NUMBER`) or a `__X__` word. A sentence that holds one, a
      short all-caps word, no args and empty args pass. A bare env var name as the whole value
      is refused too; an override lifts it for a real one. (workflow-args-shape-check)
"""
import re


# A Workflow call whose args hold a placeholder (rule workflow-args-shape-check). Mistake: a call that ran with a placeholder
# such as "FACT_CLOSE_PLACEHOLDER" or "__FILL__" as args gave agents nothing to check. The whole value must be the
# placeholder, so a sentence that names one passes. A bare env var name as a whole value ("MAILBOX_REPO") reads as a
# placeholder and is refused: that is a false alarm only when the owner means a real value, and the owner's override
# covers it (decision guard-guards-mistakes-only). The args are structured values, so no quote or comment case applies.
WORKFLOW_ARGS_CAPS = re.compile(r"[A-Z0-9_]*[A-Z][A-Z0-9_]*")
WORKFLOW_ARGS_DUNDER = re.compile(r"__\w+__")
WORKFLOW_ARGS_REASON = ("The Workflow call's args hold the placeholder `%s`, so its agents would check nothing. "
                        "Replace it with the real value, then start the Workflow again. "
                        "(decision workflow-args-shape-check, a Workflow call never runs on placeholder args)")


def workflow_args_placeholder(value) -> bool:
    """True when `value` is a string that is, whole, an all-caps word with an underscore or a __X__ word."""
    if not isinstance(value, str):
        return False
    text = value.strip()
    return bool(text and ((WORKFLOW_ARGS_CAPS.fullmatch(text) and "_" in text) or WORKFLOW_ARGS_DUNDER.fullmatch(text)))


def workflow_args_hit(tool: str, tool_input: dict) -> str:
    """The first placeholder in a Workflow call's args, or "". Reads args, and each array item or object value."""
    if tool != "Workflow":
        return ""
    args = tool_input.get("args")
    if isinstance(args, list):
        values = args
    elif isinstance(args, dict):
        values = list(args.values())
    else:
        values = [args]
    return next((v.strip() for v in values if workflow_args_placeholder(v)), "")


# INSTALL_ID = "uninstalled"
