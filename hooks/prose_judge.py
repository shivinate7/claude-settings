#!/usr/bin/env python3
"""PreToolUse judge for an Edit or Write of prose, against speak-rewrite-superseded-in-place and
rulings-declare-kind. One command hook replaces the two `type: prompt` hooks on Edit and Write: a
prompt hook cannot look at the path, so it judged every file.

Only a path with a `decisions` folder segment (either slash, any case) is judged. Any other
path exits 0 at once with no output and no model call. The model call is `decision_watch.invoke_model`,
the one home for it.

A model answer {"ok": false, "reason": R} refuses through guard_core.refuse(), so an owner override lifts it
(decision owner-override). The deny holds R. Any model error, timeout or
odd answer fails open: no output, exit 0, so a judge outage never stops an edit of a Markdown file.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def invoke_model(*args, **kwargs):
    """The model call. decision_watch loads on the first call, so a skipped path never pays for it.
    A module-level name, so a test can replace it."""
    from decision_watch import invoke_model as home
    return home(*args, **kwargs)


RULE = "prose-judge"
RULE_CITE = ("(decision rulings-declare-kind, each ruling in a decision record declares its kind) "
             "(rule speak-rewrite-superseded-in-place, superseded text is rewritten in place)")
MODEL_TIMEOUT = 40  # the settings.json row allows 45
OK_SHAPE = {"ok": (True, False)}

COMMON = (
    "Rule: speak-rewrite-superseded-in-place (superseded text is rewritten in place; no story, no old quote, "
    "and no superseded ruling kept beside the new one). A record may state a current fact with its history in "
    "one clause; that is not a breach. "
)
TAIL = (
    "Block only on a clear breach; when unsure answer {\"ok\": true}. Reply JSON only: {\"ok\": true} or "
    "{\"ok\": false, \"reason\": \"<rule id and the fix, one line>\"}."
)
RULES = {
    "Edit": COMMON + (
        "Rule: rulings-declare-kind (refuse only an edit whose new text deletes a `Plan:` or `Home:` line, or "
        "adds a second ruling section to a record; the fix is to move that ruling to its own record. "
        "A record has one `Kind:` line, and the lint counts it, so never refuse an edit for a `Kind:` "
        "line; you see only the changed text). "
    ) + TAIL,
    "Write": COMMON + (
        "Rule: rulings-declare-kind (refuse a decision record that has no `Kind: build` with "
        "`Plan: <path>#<slug> (<platform>)` lines, or `Kind: process` with a `Home:` line). "
    ) + TAIL,
}


def is_prose(path):
    parts = path.replace("\\", "/").lower().split("/")
    return "decisions" in parts[:-1]


def refuse(payload, tool, reason):
    """Refuse through guard_core.refuse(), which lets an owner override lift it. refuse() exits, so its
    exit is returned to main()'s caller as the hook's exit code."""
    text = reason + " " + RULE_CITE  # the one text both the refuse() path and the fallback print carry
    try:
        import guard_core
        guard_core.set_log_session(payload.get("session_id"))
        guard_core.set_override_context(payload.get("session_id"), payload.get("agent_id"))
        guard_core.set_override_veto(lambda: False)  # a prose rule is no act that no override lifts
        guard_core.refuse(tool, "deny", RULE, text, "")
    except SystemExit as done:
        return done.code or 0
    except Exception:  # no guard_core: no override can be read, so the refusal stands
        pass
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "deny",
                                             "permissionDecisionReason": RULE + ": " + text}}))
    return 0


MERGE_TIMEOUT = 60  # one call per merge, so it can wait longer than an edit's hook
PROMPT_CAP = 200000  # characters, the whole merge prompt
NOTE_ROOM = 200  # room kept for one cut note
MERGE_HEAD = (
    "You judge changed prose in a pull request that has just merged. Report only: nothing is refused. "
    "Rule: claims-carry-backing (a sentence that states a capability by route, or a fact about code, must be backed: "
    "it cites a route row id of the route rows below, or a file or test that holds the fact). "
    "Below are the changed sentences as `path:line: text`, the route rows file, and the text of each repo file a sentence names. "
    "Report a sentence only when the rows or the files show it is false, dead (cites a row or file that is not there) "
    "or unbacked. When unsure, report nothing. If input was left out, a line starting `NOTE:` says so. "
    "Reply JSON only: {\"ok\": true, \"findings\": []} when you find none, or "
    "{\"ok\": false, \"findings\": [{\"path\": \"<path>\", \"line\": <line number>, \"why\": \"<one line>\"}]}."
)


def fit(label, text, room):
    """`text` cut to at most `room` characters, with a NOTE line that names what was cut; whole when it fits."""
    if len(text) <= room:
        return text
    keep = max(room - NOTE_ROOM, 0)
    return text[:keep] + "\nNOTE: %d of %d characters of %s were cut to fit the prompt.\n" % (len(text) - keep, len(text), label)


def merge_prompt(sentences, rows_text, files):
    """One prompt for every changed sentence, at most PROMPT_CAP characters. The sentences get at most half the room,
    the route rows at most a third of what is left, and the files share the rest."""
    lines = "\n".join("%s:%s: %s" % (path, line, " ".join(str(text).split())) for path, line, text in sentences)
    room = PROMPT_CAP - len(MERGE_HEAD) - 200  # 200: the section titles
    body = "CHANGED SENTENCES\n" + fit("the changed sentences", lines, room // 2) + "\n"
    room -= len(body)
    rows = "ROUTE ROWS\n" + fit("the route rows", rows_text or "(absent)", max(room // 3, NOTE_ROOM)) + "\n"
    room -= len(rows)
    parts = []
    for path in sorted(files):
        share = max(room // (len(files) - len(parts)), NOTE_ROOM)
        part = "FILE %s\n%s\n" % (path, fit(path, files[path], share))
        room -= len(part)
        parts.append(part)
    return MERGE_HEAD + "\n" + body + rows + "".join(parts)


def read_findings(verdict):
    """(findings, error) from the model's answer: a list of {path, line, why}. An answer that is not that form is an
    error with no finding, never a pass."""
    findings = verdict.get("findings", [])
    if not isinstance(findings, list):
        return [], "the model's findings were not a list"
    out = []
    for item in findings:
        if not (isinstance(item, dict) and isinstance(item.get("path"), str) and item["path"].strip()
                and isinstance(item.get("line"), int) and not isinstance(item.get("line"), bool)
                and isinstance(item.get("why"), str) and item["why"].strip()):
            return [], "a finding of the model had no path, line and why"
        out.append({"path": item["path"], "line": item["line"], "why": " ".join(item["why"].split())})
    if verdict.get("ok") is False and not out:
        return [], "the model said not ok and named no finding"
    return out, None


def merge_findings(sentences, rows_text, files):
    """(findings, error) for the changed sentences of a merged pull request. One model call for all of them, none for an
    empty list. `rows_text`: the route rows file at the merged commit. `files`: {path: text} of each repo file a sentence
    names. A model error or an odd answer is an error return, which the merge prints as unknown."""
    if not sentences:
        return [], None
    verdict, error = invoke_model(merge_prompt(sentences, rows_text, files), timeout=MERGE_TIMEOUT, shape=OK_SHAPE)
    if error:
        return [], " ".join(str(error).split())
    return read_findings(verdict)


def main():
    try:
        hook = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
        tool, args = hook.get("tool_name"), hook.get("tool_input")
        path = args.get("file_path")
        if tool not in RULES or not isinstance(path, str) or not is_prose(path):
            return 0
        if tool == "Edit":
            change = "old_string: %s\nnew_string: %s" % (args.get("old_string"), args.get("new_string"))
        else:
            change = "content: %s" % args.get("content")
        prompt = "Judge this edit to a file: %s\n%s\nfile_path: %s\n%s" % (tool, RULES[tool], path, change)
        verdict, error = invoke_model(prompt, timeout=MODEL_TIMEOUT, shape=OK_SHAPE)
    except Exception as exc:
        print("prose judge failed open: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 0
    if error:
        print("prose judge failed open: %s" % " ".join(str(error).split()), file=sys.stderr)
        return 0
    if verdict.get("ok") is False:
        reason = verdict.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            reason = "prose judge: the edit breaks speak-rewrite-superseded-in-place."
        return refuse(hook, tool, reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
