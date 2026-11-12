#!/usr/bin/env python3
"""Cases for the sentence split in hooks/question_form.py (rule question-departs, decision port-keeps-behaviour).

A Departs from line that has both sides but no dash, such as "Departs from: main, where X. The change: Y.",
was refused as "no separator", though its meaning is there. The fix: when no dash separator splits the text,
the line splits at its first sentence end (". ", "! " or "? "). The first sentence is the main side, the rest
the change side. Both sides must be non-empty, the placeholder and no-change checks still apply, and the dash
forms keep winning when a dash is present.

Red on the base head: each sentence-form line below gives departs_hit a refusal, so each case that asserts a pass
fails there. Green controls, beside them: the dash forms, the shapes that stay refused (no dash and no sentence
end, an empty side, a no-change word, a placeholder) and a port item, which still needs `<file>:<symbol>` on main.

Run it from the repository root:

    python3 hooks/test_question_form_departs_sentence.py

Each line is judged by question_form.departs_hit, the one predicate. Lines 1-3 also go through the chat box and a
waiting-page decision (test_question_form.dp_chat and dp_page), and the Input Needed pick of line 1 goes through
lint/report_guard.departs_problem. The fixtures are the shared ones: test_question_form's form lines and helpers,
and test_report_guard's PickGuardTests.PICK_BARE. This file writes no temp files. The run folder that
test_report_guard makes at import is removed at exit, as test_question_form does for its own.
"""
import atexit
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
LINT = os.path.join(REPO, "lint")
sys.path.insert(0, HERE)
import test_question_form as tqf  # noqa: E402  the form lines, the page and chat helpers, verdict (one home)
import question_form  # noqa: E402  the one predicate, loaded by tqf from this checkout's hooks/
check, FAILED = tqf.check, tqf.FAILED

sys.path.insert(0, LINT)
import test_report_guard as trg  # noqa: E402  the Input Needed pick fixture, PickGuardTests.PICK_BARE (one home)
atexit.register(shutil.rmtree, trg.RUN_FOLDER, ignore_errors=True)  # that folder is not this module's, so it goes here
RG = trg.RG  # lint/report_guard.py, the report's Departs-from check

DEPARTS_REFUSAL = tqf.DEPARTS_REFUSAL  # (question-departs, "Departs")

# The owner-side audit's lines: both sides, no dash, the change after the first sentence end.
AUDIT_LINES = [
    ("audit line 1 (owner-feedback-inbox)",
     "Departs from: decision owner-feedback-inbox, where a ruling item needs only a home path that exists. "
     "The change: the item needs proof the ruling landed."),
    ("audit line 2 (the guard is kept and fixed)",
     "Departs from: main, where a guard is deleted only when its wrong refusals outweigh the harm it stops. "
     "With option a, the guard is kept and fixed."),
    ("audit line 3 (decided at each cull)",
     "Departs from: main, where wrong refusals pile up as notes until you call a cull. "
     "With a or b, they are decided at each cull."),
]
# The other two sentence ends of the spec: "! " and "? ".
END_MARKS = [
    ("an exclamation mark ends the main side",
     "Departs from: main, where a guard stops a merge! The change: the guard moves to the lint job."),
    ("a question mark ends the main side",
     "Departs from: main, where a guard stops a merge? The change: the guard moves to the lint job."),
]
# A full-size line: a long change side of many sentences. The fixture reaches the full size, not a short one.
FULL_SIZE = ("Departs from: main, where each check runs in its own job. "
             + " ".join("Step %d moves the check to the lint job." % i for i in range(1, 41)))

# Dash forms keep winning when a dash is present, even with a sentence end on either side of it.
DASH_WITH_SENTENCE_ENDS = [
    ("a dash form with a sentence end in its change side passes",
     "Departs from: main — where a guard stops a merge. The change: the guard moves to the lint job."),
    ("a dash form with a sentence end in its main side passes",
     "Departs from: main, where a guard stops a merge. — the guard moves to the lint job"),
]
# Shapes that stay refused after the split: no dash and no sentence end, an empty side, a no-change word, a
# placeholder change side, and a dash form whose change side says no change.
REFUSED_SHAPES = [
    ("no dash and no sentence end", "Departs from: main stays"),
    ("a sentence end with no space after it", "Departs from: main."),
    ("a sentence end with an empty change side", "Departs from: main. "),
    ("an empty main side before the sentence end", "Departs from: . The change: the stamp moves to the lint job."),
    ("a no-change word after the sentence end", "Departs from: main. No change."),
    ("a placeholder change side after the sentence end", "Departs from: main, where X. <what changes>"),
    ("a dash form whose change side says none, with a sentence end", "Departs from: main — none. The guard is fixed."),
]
# A port item's line: "main, where X. Y." names no <file>:<symbol> on main, so port_item_hit still refuses it.
PORT_SENTENCE = "Departs from: main, where the stamp check runs. The change: it moves to the lint job."


def sentence_lines():
    """Every line that must pass after the split, with its name."""
    return AUDIT_LINES + END_MARKS + [("the full-size line", FULL_SIZE)]


def case_sentence_lines_pass_the_predicate():
    for name, body in sentence_lines():
        found = question_form.DEPARTS_LINE.findall(body)
        check("%s: the text holds one Departs from line" % name, len(found) == 1, "DEPARTS_LINE found %r" % (found[:1],))
        dash = question_form.DEPARTS_SEPARATOR.search(found[0]) if found else None
        check("%s: the line holds no dash separator" % name, dash is None, "a dash at %r" % (dash and dash.group(0),))
        miss = question_form.departs_hit(body)
        check("%s: departs_hit passes the line" % name, miss == "", "departs_hit refused it: %s" % miss)


def case_audit_lines_pass_on_the_chat_box_and_page():
    for name, body in AUDIT_LINES:
        tqf.dp_chat("%s passes on the chat box" % name, body, None)
        tqf.dp_page("%s passes on a waiting-page decision" % name, body, None)


def case_report_pick_with_audit_line_passes():
    line = AUDIT_LINES[0][1]
    text = trg.PickGuardTests.PICK_BARE.replace("> **Next** wait", "> " + line + "\n> **Next** wait")
    check("report scope: lint/report_guard.py is this checkout's",
          os.path.realpath(RG.__file__).startswith(os.path.realpath(LINT) + os.sep), "loaded %r" % (RG.__file__,))
    check("report scope: hooks/question_form.py is this checkout's",
          os.path.realpath(question_form.__file__).startswith(os.path.realpath(HERE) + os.sep),
          "loaded %r" % (question_form.__file__,))
    check("report scope: the Input Needed item offers a pick", RG.offers_a_pick(text), "no pick in the item")
    found = question_form.DEPARTS_LINE.findall(RG.input_needed_section(text))
    check("report scope: the Input Needed item holds one Departs from line", len(found) == 1, "found %r" % (found,))
    miss = RG.departs_problem(text)
    check("report: an Input Needed pick with the audit line 1 passes departs_problem", miss == "",
          "departs_problem refused it: %r" % (miss,))


def refused_directly(name, body):
    found = question_form.DEPARTS_LINE.findall(body)
    check("%s: the text holds one Departs from line" % name, len(found) == 1, "DEPARTS_LINE found %r" % (found[:1],))
    miss = question_form.departs_hit(body)
    check("%s: departs_hit refuses the line" % name, bool(miss), "departs_hit passed it")


def case_dash_forms_with_sentence_ends_pass():
    for name, body in DASH_WITH_SENTENCE_ENDS:
        found = question_form.DEPARTS_LINE.findall(body)
        check("%s: the text holds one Departs from line" % name, len(found) == 1, "DEPARTS_LINE found %r" % (found[:1],))
        miss = question_form.departs_hit(body)
        check("%s: departs_hit passes the line" % name, miss == "", "departs_hit refused it: %s" % miss)
        tqf.dp_chat("%s on the chat box" % name, body, None)
        tqf.dp_page("%s on a waiting-page decision" % name, body, None)


def case_refused_shapes_stay_refused():
    for name, body in REFUSED_SHAPES:
        refused_directly("refused, %s: %r" % (name, body), body)
        tqf.dp_chat("refused, %s: %r on the chat box" % (name, body), body, DEPARTS_REFUSAL)
        tqf.dp_page("refused, %s: %r on a waiting-page decision" % (name, body), body, DEPARTS_REFUSAL)


def case_port_sentence_form_still_refused():
    item = tqf.page_item(port=True, departs=PORT_SENTENCE)
    check("port scope: the item is a port", item.get("port") is True, "port is %r" % (item.get("port"),))
    check("port scope: the item holds one Departs from line",
          len(question_form.DEPARTS_LINE.findall(item["context"])) == 1, "context %r" % (item["context"],))
    miss = question_form.port_item_hit("set", item)
    check("port: a port whose line is `main, where X. Y.` is still refused (no <file>:<symbol> on main)", bool(miss),
          "port_item_hit passed it")


def main():
    for case in (case_sentence_lines_pass_the_predicate, case_audit_lines_pass_on_the_chat_box_and_page,
                 case_report_pick_with_audit_line_passes, case_dash_forms_with_sentence_ends_pass,
                 case_refused_shapes_stay_refused, case_port_sentence_form_still_refused):
        try:
            case()
        except Exception as exc:
            check(case.__name__, False, "raised %s: %s" % (type(exc).__name__, exc))
    print("FAIL: %d failed" % len(FAILED) if FAILED else "all checks passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
