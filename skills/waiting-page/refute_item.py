#!/usr/bin/env python3
"""The blind refuter: write `against`, the best case against the recommended pick, onto one waiting-page decision.

    python3 ~/.claude/skills/waiting-page/refute_item.py <item.json>

<item.json> holds the item's data object. The guard (hooks/question_form.py, rule question-form) refuses an open
decision write that has a `pick` and no `against`, so a session runs this before the write.

In scope: the guard's scope, an item with a pick (a non-blank str, or a list with a non-blank key), a status other
than "closed", and a kind that is absent or "decision". A task or note is out of scope. An in-scope item with
options makes one model call, through decision_watch.invoke_model, the one home of that call. One with no options
makes no call and gets `against: "unknown (no options)"`. Anything else: no call, the file is unchanged, exit 0.

The prompt is blind: the context, each option and the pick key or keys. It never holds `why`, so the refuter does
not read the picker's reasoning. The case is written stripped. A failed call, or a reply with no usable case, is
written as `against: "unknown (<reason>)"`: a visible unknown, never a pass. An exception from the call is an unknown too. The verdict line says `unknown`, and
the exit code is 1 when env CI is set (decision ci-unknown-is-red), else 0.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.realpath(os.path.join(HERE, "..", "..", "hooks"))
if HOOKS not in sys.path:
    sys.path.insert(0, HOOKS)
import decision_watch  # noqa: E402  the one home of invoke_model

REFUTER_MODEL = "sonnet"
REFUTER_EFFORT = "medium"
REFUTER_SHAPE = {"verdict": ("AGAINST",)}

PROMPT = """You are a blind refuter. A decision is waiting for its owner. A session recommends one pick. You have not seen why.
Make the strongest case against that pick: what the owner loses by taking it, which option beats it, and what the
pick's own text leaves out. Argue for the best rival. Do not praise the pick. Do not invent facts the text lacks.

Write plain, short sentences, in one paragraph of at most 120 words.
Reply with only this JSON: {"verdict":"AGAINST","case":"<your case>"}

Title: %(title)s

Context:
%(context)s

Options:
%(options)s

Recommended pick: %(pick)s
"""


def pick_keys(item):
    """The pick as a list of keys, or [] when the item has no pick this script can judge."""
    pick = item.get("pick")
    if isinstance(pick, str):
        return [pick] if pick.strip() else []
    if isinstance(pick, list):
        return [k for k in pick if isinstance(k, str) and k.strip()]
    return []


def in_scope(item):
    """The guard's scope (hooks/question_form.py): a pick, a status other than closed, and kind absent or decision."""
    return (isinstance(item, dict) and item.get("status") != "closed"
            and item.get("kind") in (None, "decision") and bool(pick_keys(item)))


def has_options(item):
    options = item.get("options")
    return isinstance(options, list) and len(options) > 0


def option_text(option):
    if not isinstance(option, dict):
        return "- %s" % option
    lines = ["- %s: %s" % (option.get("key"), option.get("label"))]
    for field in ("how", "gain", "lose"):
        if option.get(field):
            lines.append("    %s: %s" % (field.capitalize(), option[field]))
    return "\n".join(lines)


def build_prompt(item):
    """The refuter's prompt. It reads no `why`."""
    return PROMPT % {"title": item.get("title") or "", "context": item.get("context") or "",
                     "options": "\n".join(option_text(o) for o in item["options"]),
                     "pick": ", ".join(pick_keys(item))}


def case_of(reply):
    """(case, reason): the stripped case text, or None and why there is none."""
    verdict, err = reply if isinstance(reply, tuple) and len(reply) == 2 else (None, "model call returned no reply")
    if verdict is None:
        return None, err or "model call failed"
    case = verdict.get("case") if isinstance(verdict, dict) else None
    if not isinstance(case, str) or not case.strip():
        return None, "model reply carried no case"
    return case.strip(), None


def main(argv, model_call=None):
    path = argv[0] if argv else ""
    if not path:
        print("unknown: usage: refute_item.py <item.json>")
        return 1 if os.environ.get("CI") else 0
    try:
        with open(path, encoding="utf-8") as f:
            item = json.load(f)
    except (OSError, ValueError) as exc:
        print("unknown: item file not read (%s)" % type(exc).__name__)
        return 1 if os.environ.get("CI") else 0
    if not in_scope(item):
        print("skipped: not an open item with a pick")
        return 0
    if not has_options(item):
        case, reason = None, "no options"
    else:
        try:
            call = model_call or decision_watch.invoke_model  # looked up now, so a patch of the attribute takes effect
            case, reason = case_of(call(build_prompt(item), model=REFUTER_MODEL, shape=REFUTER_SHAPE,
                                        effort=REFUTER_EFFORT))
        except Exception as exc:  # the model call's own failures arrive as (None, err); a raise is still an unknown
            case, reason = None, "model call raised %s" % type(exc).__name__
    item["against"] = case if case else "unknown (%s)" % reason
    with open(path, "w", encoding="utf-8") as f:
        json.dump(item, f, ensure_ascii=False, indent=2)
    if case:
        print("ok: against written")
        return 0
    print("unknown: against not written (%s)" % reason)
    return 1 if os.environ.get("CI") else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
