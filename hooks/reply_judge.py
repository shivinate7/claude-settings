#!/usr/bin/env python3
"""At Stop, a model (Haiku) judges the final reply against six rules. It runs on every fifth Stop and on every Stop whose reply carries an Input Needed label or a Markdown table, and never blocks. A finding comes back as a note on the next turn and writes one guard.log line.

It is a command hook, not a `type: prompt` hook, because a prompt hook cannot exit on a field
in code. This hook does: `stop_hook_active` true means this Stop is already a rewrite, so it
exits 0 at once and never calls the model.

The model call is `decision_watch.invoke_model`, the one home for it: Haiku at effort xhigh,
`--safe-mode`, no tools, and an empty config dir and scratch cwd, so the child cannot fire this
hook again. This file passes its own accepted answer, `{"ok": true|false}`.

Sampling: the judge runs on Stop n of a session (counting only Stops that carry a reply) when (n - 1) % 5 == 0. A skipped Stop returns
at once with no model call and no output. The count is a file per session under the state folder.

Input Needed: a reply with an Input Needed item is judged on every Stop, besides the sample, so
each handed-off step is checked for its reason and the check, and each question for a pick that
can be undone, which the session takes and does not ask (rule questions-go-to-owner). The label is read in code, not by the
model, from lint/report_gate.py LABEL_ORDER (the one home; lint/ lands beside hooks/). If that
import fails, the Stop is judged and one stderr line says so.

Tables: a reply that holds a Markdown table (a separator row such as |---|---|) is judged on every
Stop too, so the model can check that a comparison table carries a gold-standard or target
column. Code finds the table; the model decides whether it compares.

A finding writes one line to guard.log through `guard_core.record` (decision `noted`; rule = the
first judged rule id the reason names, else `reply-judge`; matched = `stop=<n> <reason>`). The
advisor reads these at each cull. guard_core loads only on a finding. A failed write is swallowed.

Fail open. Any model error, timeout or odd answer prints one line on stderr, exits 0, and
blocks nothing. A finding never blocks: the hook runs async, and a finding prints
`{"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": NOTE}}` on stdout, which the
session reads as a note on the next turn.
"""
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

OK_SHAPE = {"ok": (True, False)}
MODEL_TIMEOUT = 20  # the Stop entry allows 25
SAMPLE_EVERY = 5  # the judge runs on Stops 1, 6, 11 of a session
COUNT_SUB = "reply-judge"  # <config dir>/state/reply-judge/<sha256 of session_id>.count
LEAD = re.compile(r"^[\s>]*(?:\*\*)?\s*")
TAIL = re.compile(r"^\s*(?:\*\*)?\s*:?\s*(?:\*\*)?\s*")
EMPTY_ITEM = re.compile(r"^[\W_]*(none|n/a|nothing)?[\W_]*$", re.I)
TABLE_SEPARATOR = re.compile(r"^[\s>]*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$", re.M)
JUDGED_RULES = ("output-start-with-point", "style-cut-narration",
                "output-never-paste-passing-output", "output-never-hand-off-doable-step",
                "style-table-gold-column", "questions-go-to-owner")
JUDGE_RULE = "reply-judge"  # the guard.log rule when the reason names none of JUDGED_RULES
REPLY_MAX = 12000  # the prompt rides stdin, so no argv cap; the clip bounds cost and latency only (unmeasured)

INSTRUCTIONS = (
    "Judge the final reply below against six rules. "
    "output-start-with-point: the first sentence is the point, not a preamble. "
    "style-cut-narration: cut narration and recaps; narration means lines like \"I will now...\" or \"Let me...\"; "
    "a Done/Deviations/Input Needed/Next report is never narration. "
    "output-never-paste-passing-output: a passing run gets a verdict, not its pasted output. "
    "output-never-hand-off-doable-step: a command left to the owner needs its own fenced code block, "
    "ready to run as is, with one shell in the block. "
    "A button path needs no block; a command needs one, even a login command such as gh auth login. "
    "The block sits outside the report blockquote. "
    "A command the reply already ran is not a step left to the owner. "
    "A command named in a report line as done work, a line that says what ran, is not a step left to the owner. "
    "Each item under Input Needed names its reason (decision, login, or an act the safety rules keep for the owner) "
    "and the check that showed the session cannot do it, such as no API key in env or keychain; "
    "flag an item that names neither. "
    "style-table-gold-column: a table that compares options, tools or runs carries a column for the gold standard or target, "
    "what good looks like; flag a comparison table with no such column, and never flag a table that only lists facts. "
    "questions-go-to-owner: flag an Input Needed item whose pick can be undone, such as now or later, "
    "a branch, a draft, a file edit or a folder move; the session takes that pick and names it under Done. "
    "Never flag a pick that cannot be undone, such as a merge, a deploy, a delete with no copy, spend or a message to a person. "
    "Never flag a pick that changes the owner's goal. "
    "Running background work never makes a reply unfinished. "
    "Flag only on a clear breach; when unsure answer {\"ok\": true}. "
    "Reply JSON only: {\"ok\": true} or {\"ok\": false, \"reason\": \"<rule id and the fix, one line>\"}."
)


def build_prompt(reply):
    if len(reply) > REPLY_MAX:
        half = REPLY_MAX // 2
        reply = reply[:half] + "\n[middle of the reply cut for length]\n" + reply[-half:]
    return "%s\n\nReply:\n%s" % (INSTRUCTIONS, reply)


def count_this_stop(session_id):
    """Return this Stop's number n in its session and store it. Never raises. A counter that is
    missing, corrupt, unreadable or unkeyed reads as none, so this Stop is n = 1 and is judged;
    after a good read, a failed write removes the counter file, so the next Stop is judged; if
    the remove also fails, this Stop is judged (n = 1) and the stored count is left as it was."""
    path = None
    n = 1
    try:
        if isinstance(session_id, str) and session_id:
            from shared_names import STATE_DIR_NAME, config_dir  # stdlib only: a sampled-out Stop loads no guard
            key = hashlib.sha256(session_id.encode("utf-8", "replace")).hexdigest()
            path = os.path.join(config_dir(), STATE_DIR_NAME, COUNT_SUB, key + ".count")
            with open(path, "r", encoding="ascii") as f:
                n = int(f.read().strip()) + 1
            if n < 1:
                n = 1
    except Exception:
        n = 1
    try:
        if path:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path + ".tmp", "w", encoding="ascii") as f:
                f.write(str(n))
            os.replace(path + ".tmp", path)
    except Exception:
        # A write that fails would freeze the stored count and skip every later Stop. Drop the
        # file instead, so the next Stop reads a damaged counter and is judged.
        try:
            os.remove(path)
        except Exception:
            n = 1  # ponytail: write and remove both failed; judge this Stop, so no freeze
    return n


def has_input_needed(reply):
    """True when the reply has an Input Needed label line with an item that is not empty or none.
    A reply with no such words returns False before report_gate loads. If LABEL_ORDER cannot be
    read, return True (judge this Stop) and print one stderr line."""
    if "input needed" not in reply.casefold():
        return False
    try:
        lint = os.path.join(HERE, "..", "lint")
        if lint not in sys.path:
            sys.path.append(lint)
        from report_gate import LABEL_ORDER
        want = next(l for l in LABEL_ORDER if "input" in l.casefold()).casefold()
        labels = {l.casefold() for l in LABEL_ORDER}
    except Exception as exc:
        print("reply judge: cannot read LABEL_ORDER (%s: %s); judging this Stop" % (type(exc).__name__, exc),
              file=sys.stderr)
        return True
    item, inside = [], False
    for line in reply.splitlines():
        head = LEAD.sub("", line, count=1)
        hit = next((l for l in labels if head.casefold().startswith(l)), None)
        rest = TAIL.sub("", head[len(hit):], count=1) if hit else ""
        if hit and (head[len(hit):].lstrip().startswith(("**", ":")) or not rest):
            inside = hit == want
            if inside:
                item.append(rest)
        elif inside:
            item.append(line.lstrip("> \t"))
    return not EMPTY_ITEM.match(" ".join(item))


def log_finding(session_id, stop_n, reason):
    """Write one guard.log line for a finding. Never raises."""
    try:
        import guard_core  # lazy: a Stop with no finding loads no guard
        found = [(reason.find(r), r) for r in JUDGED_RULES if r in reason]
        rule = min(found)[1] if found else JUDGE_RULE
        guard_core.set_log_session(session_id)
        guard_core.record("Stop", "noted", rule, "stop=%d %s" % (stop_n, " ".join(reason.split())))
    except Exception:
        pass


def main():
    try:
        hook = json.load(sys.stdin)
        if hook.get("stop_hook_active"):
            return 0
        reply = hook.get("last_assistant_message")
        if not isinstance(reply, str) or not reply.strip():
            return 0
        stop_n = count_this_stop(hook.get("session_id"))
        if (stop_n - 1) % SAMPLE_EVERY and not TABLE_SEPARATOR.search(reply) and not has_input_needed(reply):
            return 0
        import decision_watch
        verdict, error = decision_watch.invoke_model(
            build_prompt(reply), timeout=MODEL_TIMEOUT, shape=OK_SHAPE)
    except Exception as exc:
        error, verdict = "%s: %s" % (type(exc).__name__, exc), None
    if error:
        print("reply judge failed open: %s" % " ".join(error.split()), file=sys.stderr)
        return 0
    if verdict.get("ok") is False:
        reason = verdict.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            reason = "reply judge: the reply breaks a style rule."
        log_finding(hook.get("session_id"), stop_n, reason)
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": reason}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
