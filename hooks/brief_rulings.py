#!/usr/bin/env python3
"""The check that a finished lane brief keeps every owner ruling that governs its step. Standard library only.

    python3 hooks/brief_rulings.py BRIEF_FILE [--repo DIR]    prints "<verdict>: <why>"; exit 0 ok or skipped, 1 flag,
                                                              2 unvetted

The rulings are the store lint/ruled_store.py reads (the one reader). The step is the brief's `Lane brief: <slug>` line
(first line, or after a leading `Grant:` line, with guard_merge's markdown lead) or its `cs-step:<slug>` tag. Every entry of that step, open or closed,
goes to one model call with the brief. A flag needs a reason that names a shown ruling by its `ruled:<id>`; any other
reason, an unreadable or absent store, or a model error is "unvetted", never "ok" and never "flag".

Cost: one model call per judged brief, and the two git reads of ruled_store.read_store. A brief with no step, or a step
with no ruling, makes no call. It writes no file and starts no timer.
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for _dir in (HERE, os.path.join(HERE, "..", "lint")):
    if _dir not in sys.path:
        sys.path.append(_dir)

RULED_ID = re.compile(r"(?<![\w/-])ruled:[\w.-]*\w")
CODES = {"ok": 0, "skipped": 0, "flag": 1, "unvetted": 2}


def step_of(brief):
    """The step slug a brief names, or None. The brief header is read as hooks/guard_merge.py reads it (its markdown
    lead too): the Lane brief line counts only as the first line, or the first after a Grant line. A cs-step tag
    anywhere is the fallback. guard_merge is imported here, not at the top: it is the one home of the header form."""
    import guard_merge
    from shared_names import LANE_GRANT_MARKER
    lines = [line.strip() for line in brief.splitlines() if line.strip()]
    if lines and lines[0].startswith(LANE_GRANT_MARKER):
        lines = lines[1:]
    found = guard_merge._BRIEF_LINE.match(lines[0]) if lines else None
    if found:
        return found.group("step")
    tag = re.search(r"(?<![\w-])%s([\w.-]*\w)" % re.escape(guard_merge.ARCHIVE_STEP_PREFIX), brief)
    return tag.group(1) if tag else None


def governing(brief, repo_dir):
    """(lines, unknown). `lines` holds one `ruled:<id>: <quote or (paraphrase) ruling> (owner <at>)` per entry of the
    brief's step, open or closed. `unknown` names the store when it could not be read, as question_form words it."""
    import ruled_store
    step = step_of(brief)
    if step is None:
        return [], []
    entries, state = ruled_store.read_store(repo_dir)
    if state != "ok":
        return [], ["%s (%s)" % (ruled_store.STORE_REF, "absent" if state == "absent" else "unreadable: git")]
    lines = []
    for entry in entries:
        if step not in ruled_store._steps_of(entry) or not isinstance(entry.get("id"), str):
            continue
        quote = " ".join(str(entry.get("quote") or "").split())
        text = quote or "(paraphrase) " + " ".join(str(entry.get("ruling", "")).split())
        lines.append("ruled:%s: %s (owner %s)" % (entry["id"], text, entry.get("at", "?")))
    return lines, []


def prompt(brief, lines, unknown):
    import question_form
    return ("Review this lane brief. A lane builder will act on it exactly as written:\n<<<\n" + brief
            + "\n>>>\nJudge only whether the brief keeps each owner ruling listed after the reply line. A brief drops a "
            "ruling when it says or implies the opposite, leaves out an act the ruling requires, or narrows what the "
            "ruling covers. A brief that is silent on a ruling's subject keeps it. Answer {\"ok\": true} when every "
            "listed ruling is kept.\nReply JSON only: {\"ok\": true} or {\"ok\": false, \"reason\": \"<the listed "
            "`ruled:<id>` and how the brief drops or narrows it, one line>\"}."
            + question_form.candidates_block(lines, unknown))


def _answer(verdict, lines):
    """(verdict, why) for the model's answer dict."""
    import question_form
    ok = verdict.get("ok") if isinstance(verdict, dict) else None
    if ok is True:
        return "ok", "every governing ruling is kept"
    reason = verdict.get("reason") if isinstance(verdict, dict) else None
    if ok is not False or not isinstance(reason, str) or not reason.strip():
        return "unvetted", "the model's answer has no true or false ok, or no reason"
    reason = " ".join(reason.split())
    shown = [line.split(": ", 1)[0] for line in lines]
    # ruling_cite does not catch an unshown id named next to a shown one
    stray = [i for i in RULED_ID.findall(reason) if i not in shown]
    if stray or question_form.ruling_cite(reason, shown, strict=True) != "cited":
        return "unvetted", "the review cited a ruling that was not in the list: " + reason
    return "flag", reason


def judge(brief, repo_dir, invoke=None):
    """(verdict, why): "ok", "skipped" (no step, or no ruling for it), "flag" or "unvetted"."""
    step = step_of(brief)
    if step is None:
        return "skipped", "the brief names no step"
    lines, unknown = governing(brief, repo_dir)
    if unknown:
        return "unvetted", "the ruled store was not read: " + ", ".join(unknown)
    if not lines:
        return "skipped", "no ruling governs step " + step
    import call_judge
    invoke = invoke or call_judge.invoke_model
    try:
        verdict, error = invoke(prompt(brief, lines, unknown), model=call_judge.PAST_RULING_MODEL,
                                timeout=call_judge.PAST_RULING_TIMEOUT, shape=call_judge.OK_SHAPE, effort=None)
        if error:
            return "unvetted", "the model call failed: " + " ".join(str(error).split())
        return _answer(verdict, lines)
    except Exception as exc:
        return "unvetted", "the model call failed: " + " ".join(str(exc).split())


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("brief_file")
    parser.add_argument("--repo", default=os.getcwd())
    args = parser.parse_args(argv)
    try:
        with open(args.brief_file, encoding="utf-8") as handle:
            brief = handle.read()
    except (OSError, ValueError) as exc:  # a missing file, a folder, bytes that are not UTF-8
        verdict, why = "unvetted", "the brief file could not be read: " + " ".join(str(exc).split())
    else:
        verdict, why = judge(brief, args.repo)
    print("%s: %s" % (verdict, why))
    return CODES[verdict]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
