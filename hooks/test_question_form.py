#!/usr/bin/env python3
"""Cases for hooks/question_form.py, the one question form and the one check for both the chat
question box (AskUserQuestion) and a waiting-page item write. Standard library only, no test runner.

Run it from the repository root:

    python3 hooks/test_question_form.py

Interface the module must match (the lane's form contract):
- question_form.chat_hit(tool_input) -> (rule, matched). Judges each question with 2+ options.
- question_form.item_hit(op, entry) -> (rule, matched). One waiting-page write (set, update,
  str_replace), `entry` as guard.data_tool_hit sees it. guard.data_tool_hit calls it for every item write.
- ("", "") passes. A missing Goal, Problem or Based on line, a Based on count outside 1-3, a kind outside
  PREMISE_KINDS and an option with no gain or no loss refuse with rule `question-form`. The older rule ids
  stay: uniform-pick, press-link, port-question, command-in-item, task-names-check.
- The form, as text lines (page: in `context`; chat: in `question`), in this order:
      Goal: <the goal>
      Problem (<stake>): <the problem, and why it needs his word>     <stake> is one of OWNER_STAKES
      Based on (<kind>): <one premise>                                 one to three; <kind> is in PREMISE_KINDS
  A line out of this order refuses. A Problem line with no stake kind refuses too, on every item.
  Only `Based on (<kind>):` is a Based on line: prose that starts with "Based on the log" is not.
- Each option states gain and loss: page `gain` and `lose` fields; chat `Gain:` and `Lose:` in the description.
- A question to the owner holds a line at a line start, `Departs from: <what on main> — <what changes>`
  (rule question-departs), after the form passes. Both sides are non-empty, and the change side says a change,
  not a restatement of main (none, nothing, n/a, no change, unchanged, stays, keeps, as today, as on main,
  same as, already; word match) before the change side's first ";", or anywhere when it has none. The chat
  box judges it in `question`; a page decision in `context`.
- A widening option: page `widens: true`, never in `pick`; chat `Goes against your ruling: a repo changes to
  fit a shared tool, never the tool to fit a repo` in its label or description, and never `(Recommended)` in
  its label (rule uniform-pick).
- A press in a web app: page `links`; chat an https:// url in that option's description (rule press-link).
  The chat scan skips an option's Gain and Lose text, as the page scan reads only label and how.
- A chat refusal reason names its remedy and no field of the waiting page (no `stands`). Each page reason
  is the text of question_form.PAGE_REASONS, the one table guard.py prints from.
- A closed item passes. An update is judged only for the fields it carries. A str_replace on `context`
  that removes a Goal, Problem or Based on line is refused.
- A waiting-page task's Why yours line (rule task-why-cited, decision claims-carry-backing part (v)): a
  capability reason needs a cite that holds on this surface, a `(route <id>)` whose row says refused or asks, or a
  dated `(measured <date>, ...)`. The page reads no refusals file. Cases: case_task_why_cited_reds and _greens.
- question_form.cross_repo_hit(op, data, page_repo, session_id=None) -> reason or None (rule
  question-checked-with-repo). An open decision or task set (a missing kind is a decision, and any status but closed
  is open), or an update carrying `repo`, that names a repo other than the page's needs a session-shaped
  `checked_with`. A `checked_with` equal to the session id in `owner`, or to the writer's `session_id`, is refused.
  A `repo` that is not owner/name is refused with the format reason. `repo` is required on the set: a direct call
  with page_repo None refuses a missing one, but item_hit does not judge it when the page repo is unknown, since no
  compare can run. A str_replace on `repo` or `checked_with` is refused as this rule. An update that
  carries `checked_with` without `repo` is refused, naming `repo`. item_hit and page_item_hit take the writer's
  session_id. guard.py passes the cloud session's record id (env CLAUDE_CODE_REMOTE_SESSION_ID read as session_<x>),
  never the payload's local UUID. The page repo is read from the checkout at cwd,
  and None (no cwd, or no origin) skips only the compare.
- hooks/call_judge.py refuses an AskUserQuestion that fails chat_hit before any model call, with the rule
  chat_hit names; the model sees only a box that passes.

Every case runs on the surfaces the contract names. A page write is judged twice, by question_form.item_hit
and by guard.data_tool_hit, so a guard that does not delegate shows red. The same form lines are judged on
the chat surface from one table (FORM_VARIANTS). The call_judge cases reuse test_call_judge.run_hook (the
one home of the model stub). Temp files: the run folder of lint/_test_temp.py, whose sweep
lint/test_find_copies.py proves once (decision test-temp-standard).
"""
import atexit
import contextlib
import copy
import io
import json
import os
import re
import inspect
import shutil
import sys
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import test_call_judge as tcj  # noqa: E402  the call_judge harness; its ROOT is this run's folder
sys.path.insert(0, os.path.join(REPO, "tests"))
import lift_line  # noqa: E402  the one reader of the lift line (tests/lift_line.py)

RUN_FOLDER = tcj.ROOT
os.environ["CLAUDE_CONFIG_DIR"] = os.path.join(RUN_FOLDER, "config")
check, FAILED = tcj.check, tcj.FAILED

import guard  # noqa: E402
# The pointer is patched by name, not imported: an import line here lists this suite for hooks/guard_pointer.py.
POINTER_CHECKOUT = "guard_pointer.pointer_checkout"  # the ruled-store cases' patch target
sys.path.insert(0, os.path.join(REPO, "lint"))
import test_ruled_store as fixture  # noqa: E402  the one home of a ruled-store fixture (lint/test_ruled_store.py)
import reply_judge  # noqa: E402  the reply judge's instructions, which carry the widening sentence
import route_match  # noqa: E402  the rows-file reader; the task-why cases count its reads
import test_refusal_note as hook_base  # noqa: E402  the route-row fixture (one home), with its own run folder
atexit.register(shutil.rmtree, hook_base.RUN, ignore_errors=True)  # that folder is not this module's, so it goes here
from precompact_handoff import PREMISE_KINDS  # noqa: E402  the one home of the premise kinds

try:
    import question_form
except ImportError:  # the build has not landed: each case that needs the module fails by name
    question_form = None

# The waiting page of the fixture repo, built once by test_call_judge.py (its one home). guard.data_tool_hit
# judges only a write to this repo's page.
PAGE_URL, PAGE_REPO = tcj.PAGE_URL, tcj.PAGE_REPO

FORM_RULE = "question-form"
DEPARTS_RULE = "question-departs"
DEPARTS = tcj.DEPARTS_LINE  # the one valid Departs from line (hooks/test_call_judge.py builds the box from it)
# A Problem line that is bare, or names a stake outside OWNER_STAKES: the contract does not say whether
# question-form or owner-judge names it, so either id passes and the refusal must name the Problem line.
STAKE_RULES = (FORM_RULE, "owner-judge")
OWNER_STAKES = getattr(question_form, "OWNER_STAKES", None) or guard.OWNER_STAKES
DOC = "batch-runner-merge"
MISSING = ("MISSING", "hooks/question_form.py has no such function yet")
# The widening words are one constant, question_form.WIDENS_TEXT. A build that lacks it gets this sentinel,
# so each case that uses it goes red by its own name instead of raising. WIDENS_WORDS pins the owner's exact
# words once; every other case takes WIDE from the module.
WIDENS_WORDS = "Goes against your ruling: a repo changes to fit a shared tool, never the tool to fit a repo"
WIDE = getattr(question_form, "WIDENS_TEXT", None) or "<WIDENS_TEXT missing from hooks/question_form.py>"
# The reply judge's prompt is read from its module constant in case_widens_words_in_the_reply_judge_prompt.
WIDENS_HOMES = ("skills/waiting-page/page.html", "skills/waiting-page/SKILL.md", "output-styles/shiv-stylisms.md",
                "docs/decisions/uniform-over-variants.md", "docs/decisions/question-form.md")
OLD_WIDENS_CARD = "uniform ruling (t18)"

# Waiting item 92 as the writer sent it (Oct 30): a decision with a Goal line and no Problem line, no Based
# on line, and a widening option 'b' not marked widens. It holds no personal data.
ITEM92 = json.loads(r'''{"n":928,"kind":"decision","title":"Let the batch runner merge each batch on its own?","context":"Goal: the batch runner merges each batch with no help from the coordinator or you. Today auto mode refuses the runner's `merge --role batch-runner` (03:04 CDT, main d545baf4): the cloud allow rules from #841 cover only `merge N --confirm`. The lane that would widen them was refused as a change to the sessions' own rules, so it needs your word. Asked in chat 03:05 CDT, no answer. Task home: docs/todo.md line fb-0303-1 (#845).","options":[{"gain":"No new form on the shared allow list.","how":"The coordinator merges each batch the runner builds.","key":"a","label":"Keep it as is","lose":"Each batch waits until the coordinator wakes."},{"gain":"The runner merges alone, so batches land sooner.","how":"Lane merge-role-allow adds `merge --role` to the auto-mode allow list, for the coordinator and batch-runner tiers only.","key":"b","label":"Allow merge --role","lose":"A second merge form on the shared allow list, against your one-form ruling (t18)."}],"pick":"a","why":"Your 16:54 CDT ruling (no owner step per merge) holds either way; a keeps the allow list to one form.","status":"open"}''')

# The form lines of the rewrite. Item 92's subject, in the owner's terms; no web marker, no press verb.
GOAL = "Goal: the batch runner merges each batch with no help from the coordinator or you."
PROBLEM = ("Problem (rule): auto mode refuses the runner's merge, and the lane that would allow it changes "
           "the sessions' own rules, so it needs your word.")
BASED = ("Based on (measured): auto mode refused the runner's merge at 03:04 CDT.",
         "Based on (read): the cloud allow rules cover only the plain merge form (hooks/guard.py:120).")
THIRD = "Based on (ruling): your 16:54 CDT ruling says no owner step per merge."


LINE_KEYS = ("goal", "problem", "based", "departs")


def parts(**over):
    """The form lines as a dict. A part set to None is dropped; `based` is a list of lines."""
    found = {"goal": GOAL, "problem": PROBLEM, "based": list(BASED), "departs": DEPARTS}
    found.update(over)
    return found


# The Waiting on line (tcj.WAITING_LINE, one home). A build without it gets a sentinel line, so each case that
# needs it goes red by its own name instead of raising (the WIDE pattern below).
WAITING = getattr(tcj, "WAITING_LINE", None) or "<WAITING_LINE missing from hooks/test_call_judge.py>"


def form_text(goal=GOAL, problem=PROBLEM, based=BASED, departs=DEPARTS, waiting=WAITING):
    return "\n".join(line for line in (goal, problem, *based, departs, waiting) if line)


def page_item(tail="", options=None, lines=None, **over):
    """Item 92 in the form: the form lines in `context`, option b marked widens, the pick on a. `lines`
    sets the whole context, one line each, for a case that changes the order of the lines."""
    item = copy.deepcopy(ITEM92)
    item["context"] = "\n".join(lines) if lines is not None else form_text(
        **{k: v for k, v in over.items() if k in LINE_KEYS}) + tail
    item["options"][1]["widens"] = True
    if options is not None:
        item["options"] = options
    item.update({k: v for k, v in over.items() if k not in LINE_KEYS})
    return tcj.with_frozen_fields(item)  # ids and `shown` for the options as they stand now


TASK_WHY = "Why yours: a session on your computer was asked first and none could reach the remote"


def task_item(steps, **over):
    """A waiting-page task with these steps and the Why yours line in `context`, so only the rule a case
    names judges it (task-names-check reads that line). `over` sets or replaces any field."""
    item = {"n": 928, "kind": "task", "title": "Merge the batch", "status": "open", "steps": list(steps), "context": TASK_WHY}
    item.update(over)
    return item


def chat_box(options=None, **over):
    """A chat box with the same form lines. Options default to test_call_judge.good_options()."""
    return tcj.good_box(options=options, **{k: v for k, v in over.items() if k in LINE_KEYS})


def entry_of(data, **extra):
    found = {"collection": "items", "doc_id": DOC}
    if data is not None:
        found["data"] = data
    found.update(extra)
    return found


def call(name, *args):
    """question_form.<name>(*args), or MISSING when the module or the function is not there yet."""
    fn = getattr(question_form, name, None)
    if fn is None:
        return MISSING
    try:
        return fn(*args)
    except Exception as exc:  # a crash is a wrong verdict, shown by name
        return ("RAISED", "%s: %s" % (type(exc).__name__, exc))


def guard_hit(op, entry):
    try:
        return guard.data_tool_hit(dict(entry, url=PAGE_URL, action=op), PAGE_REPO)
    except Exception as exc:  # a crash is a wrong verdict, shown by name, as call() shows it
        return ("RAISED", "%s: %s" % (type(exc).__name__, exc))


def verdict(name, got, want):
    """want None: a pass. want (rules, fragment): a refusal by one of the rules, naming the fragment."""
    if want is None:
        check(name, got == ("", ""), "want a pass, got %r" % (got,))
        return
    rules, fragment = want
    rules = (rules,) if isinstance(rules, str) else rules
    ok = got[0] in rules and (not fragment or fragment.lower() in str(got[1]).lower())
    check(name, ok, "want %s naming %r, got %r" % ("/".join(rules), fragment, got))


def page(name, op, entry, want):
    """One page write judged by item_hit and by the guard. Both must give the verdict."""
    verdict("page item_hit: " + name, call("item_hit", op, entry), want)
    verdict("page guard: " + name, guard_hit(op, entry), want)


def chat(name, box, want):
    verdict("chat: " + name, call("chat_hit", box), want)


# ------------------------------------------------------------------ item 92

def case_item_92():
    page("item 92 as written (no Problem line) is refused, naming the Problem line", "set",
         entry_of(ITEM92), (FORM_RULE, "Problem"))
    with_problem = dict(ITEM92, context=ITEM92["context"] + "\n" + PROBLEM)
    page("item 92 with a valid Problem line and no Based on line is still refused, naming Based on", "set",
         entry_of(with_problem), (FORM_RULE, "Based on"))
    page("item 92 rewritten to the form (Goal, Problem, Based on, gain and lose, b widens, pick a) passes", "set",
         entry_of(page_item()), None)
    got_old, got_new = call("item_hit", "set", entry_of(ITEM92)), guard_hit("set", entry_of(ITEM92))
    check("guard.data_tool_hit gives item 92 the verdict question_form.item_hit gives (one home)",
          got_old == got_new and got_old[0] == FORM_RULE, "item_hit %r, guard %r" % (got_old, got_new))


# ------------------------------------------------------------------ the form lines, on both surfaces

# (name, form parts, verdict). The same lines are judged the same on the page and in a chat box.
FORM_VARIANTS = [
    ("the full form", parts(), None),
    ("one Based on line", parts(based=[BASED[0]]), None),
    ("three Based on lines", parts(based=[*BASED, THIRD]), None),
    ("no Goal line", parts(goal=None), (FORM_RULE, "Goal")),
    ("no Problem line", parts(problem=None), (FORM_RULE, "Problem")),
    ("a Problem phrase mid-line does not count", parts(problem="Reason. " + PROBLEM), (FORM_RULE, "Problem")),
    ("a bare Problem line with nothing after the colon", parts(problem="Problem (rule):"),
     (STAKE_RULES, "Problem")),
    ("a Problem stake outside the set (internals)", parts(problem="Problem (internals): which job runs it."),
     (STAKE_RULES, "Problem")),
    ("a Problem line with no stake kind", parts(problem="Problem: which job runs it."),
     (STAKE_RULES, "Problem")),
    ("no Based on line", parts(based=[]), (FORM_RULE, "Based on")),
    ("four Based on lines", parts(based=[*BASED, THIRD, "Based on (notes): a fourth premise."]),
     (FORM_RULE, "Based on")),
    ("a Based on kind outside PREMISE_KINDS", parts(based=["Based on (guess): the runner is slow."]),
     (FORM_RULE, "Based on")),
    ("a Based on line with no kind", parts(based=["Based on: the runner is slow."]), (FORM_RULE, None)),
    ("comment openers and an apostrophe in the lines are plain text",
     parts(goal="Goal: keep the runner's merge, with //path, /* glob and # tags, working.",
           problem="Problem (risk): don't parse # or // here, so it needs your word."), None),
    # The copied template, with a real stake and kind, is refused on the page and in a chat box.
    ("placeholder: the copied Goal line is refused", parts(goal="Goal: <the goal>"), (FORM_RULE, "Goal")),
    ("placeholder: the copied Problem line is refused",
     parts(problem="Problem (goal): <the problem in one plain sentence, and why it needs his word>"),
     (FORM_RULE, "Problem")),
    ("placeholder: the copied Based on line is refused", parts(based=["Based on (read): <one premise>"]),
     (FORM_RULE, "Based on")),
    ("placeholder: the Based on template with <kind> is refused by the kind check",
     parts(based=["Based on (<kind>): <one premise>"]), (FORM_RULE, "Based on")),
    # Real text around angle brackets is text, not a placeholder.
    ("placeholder: real text with angle brackets passes",
     parts(goal="Goal: render <Button> right", problem="Problem (risk): the <Modal> in the lint job needs your word.",
           based=["Based on (read): the <Card> prop renders twice (skills/waiting-page/export_page.py:1046)."]), None),
    ("placeholder: a JSX lone quote and comment openers beside angle brackets pass",
     parts(goal="Goal: fix the <p>Don't</p> text, and keep // and /* in paths as plain text."), None),
    # A read premise names path:line (decision premise-format). Each refusal names the cause, "path:line".
    ("a read premise that names no path:line is refused",
     parts(based=["Based on (read): the cloud allow rules cover only the plain merge form."]), (FORM_RULE, "path:line")),
    ("a read premise that names a path with no line is refused",
     parts(based=["Based on (read): hooks/guard.py holds the merge check."]), (FORM_RULE, "path:line")),
    ("a read premise whose only cite is a URL with a port is refused",
     parts(based=["Based on (read): http://localhost:8080"]), (FORM_RULE, "path:line")),
    ("three Based on lines, one read with no path:line, is refused",
     parts(based=[BASED[0], "Based on (read): the cloud allow rules cover only the plain merge form.", THIRD]),
     (FORM_RULE, "path:line")),
    ("a read premise that names path:line in its text passes",
     parts(based=["Based on (read): the merge check in hooks/guard.py:120 refuses the runner's form."]), None),
    ("a read premise with a relative path with folders and an extension passes",
     parts(based=["Based on (read): skills/waiting-page/export_page.py:1046 writes the page."]), None),
    ("a notes premise with no line passes",
     parts(based=["Based on (notes): an Explore summary says the runner merges alone."]), None),
]
for _kind in PREMISE_KINDS:
    FORM_VARIANTS.append(("a Based on kind %s" % _kind, parts(based=["Based on (%s): the premise (hooks/guard.py:120)." % _kind]), None))
for _stake in OWNER_STAKES:
    FORM_VARIANTS.append(("a Problem stake %s" % _stake,
                          parts(problem="Problem (%s): the pick needs your word." % _stake), None))


def case_form_lines():
    for name, found, want in FORM_VARIANTS:
        page(name, "set", entry_of(page_item(**found)), want)
        chat(name, chat_box(**found), want)


def case_form_placeholders_on_edits():
    # The copied template on the other page paths: an update that carries the context, a str_replace that
    # swaps the Goal line, and a stood pick's Problem line. The set path is FORM_VARIANTS.
    page("placeholder: an update of kind decision with the copied Goal line is refused", "update",
         entry_of({"kind": "decision", "context": form_text(goal="Goal: <the goal, in the owner's terms>")}),
         (FORM_RULE, "Goal"))
    context_replace("placeholder: that swaps the Goal line for the copied template is refused", GOAL,
                    "Goal: <the goal>", (FORM_RULE, "Goal"))
    context_replace("placeholder: that swaps the Goal line for real text with angle brackets passes", GOAL,
                    "Goal: render <Button> right", None)


# ------------------------------------------------------------------ gain and loss in each option

def case_options_state_gain_and_loss():
    def page_options(edit):
        options = copy.deepcopy(ITEM92["options"])
        edit(options)
        return page_item(options=options)

    def chat_options(edit):
        options = tcj.good_options()
        edit(options)
        return chat_box(options=options)

    def no_lose(options):
        options[1].pop("lose", None)

    def no_gain(options):
        options[0].pop("gain", None)

    def empty_lose(options):
        options[1]["lose"] = ""

    def chat_no_lose(options):
        options[1]["description"] = "Gain: a reviewer reads it first."

    def chat_no_gain(options):
        options[0]["description"] = "Lose: nobody reads it first."

    def chat_empty_lose(options):
        options[1]["description"] = "Gain: a reviewer reads it first. Lose:"

    for name, page_edit, chat_edit, fragment in (
            ("an option with no loss", no_lose, chat_no_lose, "lose"),
            ("an option with no gain", no_gain, chat_no_gain, "gain"),
            ("an option with an empty loss", empty_lose, chat_empty_lose, "lose")):
        page(name + " is refused, naming it", "set", entry_of(page_options(page_edit)), (FORM_RULE, fragment))
        chat(name + " is refused, naming it", chat_options(chat_edit), (FORM_RULE, fragment))
    page("every option with a gain and a loss passes", "set", entry_of(page_item()), None)
    chat("every option with a gain and a loss passes", tcj.good_box(), None)


# ------------------------------------------------------------------ older rules, one home

def case_older_rules_keep_their_ids():
    pick_wide = page_item(pick="b")
    page("a pick that names the widening option is refused as uniform-pick", "set", entry_of(pick_wide),
         ("uniform-pick", None))
    press = copy.deepcopy(ITEM92["options"])
    press[1].update(label="Press Merge in GitHub", how="Do it by hand.")
    page("a press in GitHub with no link is refused as press-link", "set",
         entry_of(page_item(options=press)), ("press-link", None))
    press[1]["links"] = [{"label": "the pull request", "url": "https://github.com/shivinate7/home/pull/374"}]
    page("a press in GitHub with a link to the page passes", "set", entry_of(page_item(options=press)), None)
    task = task_item(["Open Terminal"])
    page("a task with a Why yours line and no form lines is not judged by the form", "set", entry_of(task), None)
    page("a task with no Why yours line is refused as task-names-check", "set",
         entry_of(dict(task, context="Nothing here.")), ("task-names-check", None))


# ------------------------------------------------------------------ closed items, stood picks, updates

def case_closed_stood_and_updates():
    answered = "Answer from chat, 10:42: keep the check in the lint job."
    page("a closed item with no form lines passes", "set",
         entry_of(dict(ITEM92, status="closed", context=answered)), None)
    page("an open item with the chat answer and no form lines is refused", "set",
         entry_of(dict(ITEM92, status="open", context=answered)), (FORM_RULE, None))
    page("an item with no form lines is refused", "set",
         entry_of(dict(ITEM92, context="No form here.")), (FORM_RULE, None))
    page("an update of the status only passes", "update", entry_of({"status": "closed"}), None)
    page("an update of the rank only passes", "update", entry_of({"rank": 3}), None)
    page("an update that carries kind decision and a title only passes", "update",
         entry_of({"kind": "decision", "title": "Let the runner merge alone?"}), None)
    page("an update that carries kind decision, status closed and a context with no form passes", "update",
         entry_of({"kind": "decision", "status": "closed", "context": answered}), None)
    page("an update that carries kind decision, status open and a context with no form is refused", "update",
         entry_of({"kind": "decision", "status": "open", "context": answered}), (FORM_RULE, None))
    page("an update that carries kind decision and a context with the form passes", "update",
         entry_of({"kind": "decision", "context": form_text()}), None)
    lacking = copy.deepcopy(ITEM92["options"])
    lacking[1].pop("lose")
    page("an update that carries options with an option that has no loss is refused", "update",
         entry_of(tcj.with_frozen_fields({"kind": "decision", "options": lacking})), (FORM_RULE, "lose"))
    page("an update that carries options with a gain and a loss each passes, its context not carried", "update",
         entry_of(tcj.with_frozen_fields({"kind": "decision", "options": copy.deepcopy(ITEM92["options"])})), None)


def case_str_replace():
    def replace(name, old, new, want, field="context"):
        page("a str_replace " + name, "str_replace",
             {"collection": "items", "doc_id": DOC, "field": field, "old_str": old, "new_str": new}, want)

    full, tail = form_text(), "\nThe lane merge-role-allow would do it."
    replace("that drops the Problem line from context is refused", full, form_text(problem=None),
            (FORM_RULE, "Problem"))
    replace("that drops the Goal line from context is refused", full, form_text(goal=None), (FORM_RULE, "Goal"))
    replace("that drops the only Based on line from context is refused", form_text(based=[BASED[0]]),
            form_text(based=[]), (FORM_RULE, "Based on"))
    replace("that swaps the Problem line for another stake is allowed", PROBLEM,
            "Problem (money): the lane costs runner time, so it needs your word.", None)
    replace("that swaps the Problem line for a stake outside the set is refused", PROBLEM,
            "Problem (internals): which job runs it.", (STAKE_RULES, "Problem"))
    replace("that keeps every form line and changes the prose is allowed", full + tail, full + "\nChanged prose.", None)
    replace("whose old_str holds no form line is allowed", "The lane merge-role-allow would do it.",
            "The lane would do it.", None)
    replace("on the title is allowed", "Let the batch runner merge each batch on its own?",
            "Let the runner merge alone?", None, field="title")
    replace("on why is not judged", PROBLEM, "A keeps the allow list to one form.", None, field="why")


# ------------------------------------------------------------------ a stands:true item is an ordinary item

def case_stands_gets_no_relaxed_stake_rule():
    # A stands item gets no relaxed stake rule. The stake rule is judged on the form (decision_form_hit),
    # not item_hit: item_hit refuses a write that names a field the page does not draw before it reads the form.
    bare = page_item(problem="Problem: which job runs it, and why it needs your word.", stands=True)
    verdict("a stands:true decision with a bare Problem line gets no relaxed stake rule",
            call("decision_form_hit", "set", bare), (STAKE_RULES, "Problem"))
    update = {"kind": "decision", "context": form_text(problem="Problem: which job runs it."), "stands": True}
    verdict("an update with stands:true and a bare Problem line gets no relaxed stake rule",
            call("decision_form_hit", "update", update), (STAKE_RULES, "Problem"))
    verdict("a stands:true decision with a stake Problem line passes the form",
            call("decision_form_hit", "set", page_item(stands=True)), None)


def case_page_reasons_name_no_stands_field():
    # The refusal remedy no longer tells a writer to take a pick and set `stands: true`.
    reasons = getattr(question_form, "PAGE_REASONS", None) or {}
    for rule in (FORM_RULE, STAKE_RULES[1]):
        text = reasons.get(rule)
        check("the page reason for %s is present and names no stands or stood field" % rule,
              text is not None and not re.search(r"stands|stood", text), repr(text)[:160])


def case_str_replace_bare_problem_lines():
    # A bare Problem line is no form line. An edit that removes it, or swaps a stake line for it, is refused.
    context_replace("that removes a bare Problem line from context is refused, as a stake line is",
                    "Problem: which job runs it.", "", (FORM_RULE, "Problem"))
    context_replace("that swaps a stake Problem line for a bare one is refused as no stake",
                    PROBLEM, "Problem: which job runs it.", (STAKE_RULES, "Problem"))


def case_str_replace_bare_to_malformed_stake():
    # A Problem line that is not a labelled stake line is refused as no stake: PROBLEM_LABEL matches the new line and
    # PROBLEM_LINE does not. That covers a stake outside the set, a stake with no text, and a line with no parenthesised
    # stake at all. A page item carries no stood pick, so a bare line swapped for
    # another bare line is refused too. A bare line swapped for a labelled stake line is allowed.
    context_replace("that swaps a bare Problem line for a stake outside the set is refused as no stake",
                    "Problem: which job runs it.", "Problem (internals): which job runs it.", (STAKE_RULES, "Problem"))
    context_replace("that swaps a bare Problem line for a stake with no text is refused as no stake",
                    "Problem: which job runs it.", "Problem (money):", (STAKE_RULES, "Problem"))
    context_replace("that swaps a bare Problem line for another bare line is refused as no stake",
                    "Problem: which job runs it.", "Problem: which job runs it, and why it needs your word.",
                    (STAKE_RULES, "Problem"))
    for shape in ("Problem goal: which job runs it.", "Problem - goal: which job runs it.",
                  "Problem is which job runs it.", "Problem:"):
        context_replace("that swaps a bare Problem line for %r is refused as no stake" % shape,
                        "Problem: which job runs it.", shape, (STAKE_RULES, "Problem"))
    context_replace("that swaps a bare Problem line for a labelled stake line is allowed",
                    "Problem: which job runs it.", "Problem (goal): which job runs it.", None)
    context_replace("that swaps a labelled Problem line for another labelled line is allowed",
                    "Problem (goal): a", "Problem (goal): b", None)


def case_page_form_reason_names_the_pick_on_stake_only():
    # The take-your-own-pick sentence belongs on the stake refusal alone. A missing Goal line is a form refusal, so the
    # reason the writer reads for it names no pick. Both reasons are read off the guard, as the writer sees them.
    missing_goal = {"url": PAGE_URL, "action": "set", "collection": "items", "doc_id": DOC, "data": page_item(goal=None)}
    stake = {"url": PAGE_URL, "action": "set", "collection": "items", "doc_id": DOC,
             "data": page_item(problem="Problem (internals): which job runs it")}
    scope = guard.data_tool_hit(missing_goal, PAGE_REPO)[0]
    check("page form reason: a missing Goal line is refused by the form rule", scope == FORM_RULE, repr(scope))
    goal_reason = printed_reason(missing_goal)
    check("page form reason: a missing Goal line is refused with a reason", goal_reason != "", repr(goal_reason)[:200])
    check("page form reason: a missing Goal refusal does not say take your own pick",
          "take your own pick" not in goal_reason, goal_reason[:200])
    stake_reason = printed_reason(stake)
    check("page form reason: a stake refusal says take your own pick",
          "take your own pick" in stake_reason, stake_reason[:200])


def page_batch(writes):
    """guard.data_tool_hit on one ArtifactData batch of waiting-page writes."""
    return guard.data_tool_hit({"url": PAGE_URL, "action": "batch", "writes": writes}, PAGE_REPO)


def case_batch():
    good = {"op": "set", "collection": "items", "doc_id": DOC, "data": page_item()}
    bad = {"op": "set", "collection": "items", "doc_id": "second", "data": ITEM92}
    verdict("page guard: a batch of items that meet the form passes", page_batch([good, dict(good, doc_id="second")]),
            None)
    verdict("page guard: a batch whose second write has no Problem line is refused", page_batch([good, bad]),
            (FORM_RULE, "Problem"))


# ------------------------------------------------------------------ a task's Why yours line cites what it claims
#
# Rule task-why-cited (decision claims-carry-backing, part (v)). The Why yours line of a waiting-page task
# is judged on its cite: a capability reason needs one, and the cite must hold on this surface. The page accepts a
# route cite and a dated measured cite, and no refusals-file cite. Each case judges one write through
# guard.data_tool_hit alone, with its rows in a file of this run's folder and the surface pinned to local.

WHY_RULE = "task-why-cited"
CAP = "Why yours: the cloud proxy refused the delete (403)"  # a capability reason: "refused" and "403"
# Capability reasons with the widened words, one word each, so a red names its word alone. The rule reads each word as a
# capability word, as it reads "refused" and "403" above.
CAP_COULD_NOT = "Why yours: I could not push the delete from here"
CAP_COULDNT = "Why yours: I couldn't push the delete from here"
CAP_COULDNT_CURLY = "Why yours: I couldn’t push the delete from here"
CAP_REJECTED = "Why yours: the remote rejected the delete"
CAP_401 = "Why yours: the remote returned 401 to the delete"
# The reject forms: "reject", "rejects" and "rejecting" are red on the old commit; "being rejected" holds "rejected", which
# the old commit already reads.
CAP_REJECT = "Why yours: the remote may reject the delete"
CAP_REJECTS = "Why yours: the remote rejects the delete"
CAP_REJECTING = "Why yours: the remote is rejecting the delete"
CAP_REJECTED_BEING = "Why yours: the delete is being rejected"
STEPS = ["Open Terminal"]
BACKTICK_TOOL = "mcp__claude-code-remote__archive_session"
# The rows the cases cite. The first three are on the local surface the cases pin; r-cloud-only is on the cloud one.
WHY_ROWS = [hook_base.route_row("r-refused", "delete_branch", "refused", surface="local"),
            hook_base.route_row("r-asks", "ask_first", "asks", surface="local", route="ask-first"),
            hook_base.route_row("r-works", "gh_api", "works", surface="local", route="gh-api"),
            hook_base.route_row("r-cloud-only", "archive_session", "refused", surface="cloud")]


def rows_at(name, rows):
    """A route rows file named `name` in this run's folder, holding `rows`. Its path."""
    path = os.path.join(RUN_FOLDER, name)
    hook_base.write_route_rows(path, rows)
    return path


@contextlib.contextmanager
def local_rows(path):
    """The rows seam at `path`, on the local surface. The cloud markers are removed for the block, and os.environ is
    restored after it, so no case judges a cite on the cloud surface."""
    with mock.patch.dict(os.environ):
        for name in (hook_base.CLOUD_ENV, hook_base.REMOTE_SESSION_ENV):
            os.environ.pop(name, None)
        os.environ[hook_base.ROUTE_ROWS_ENV] = path
        yield


@contextlib.contextmanager
def counted_rows_reads():
    """The reads of the rows file, counted. Every reader calls route_match.rows_path(), the one home of the path, so
    the count sees each read. The real path is still returned, so a verdict is judged as it is."""
    reads = []
    real = route_match.rows_path

    def counting():
        reads.append(real())
        return reads[-1]

    with mock.patch.object(route_match, "rows_path", counting):
        yield reads


def on_local_surface(name):
    """The scope before the subject (P7): the surface reads local. Off it, the case fails by name and judges nothing."""
    if route_match.surface() == "local":
        return True
    check("task why cited: " + name, False, "the surface is not local, so the cite is judged on the wrong rows")
    return False


def why_guard(name, op, entry, want):
    """One page write judged by guard.data_tool_hit alone, on the local surface."""
    if on_local_surface(name):
        verdict("task why cited: " + name, guard_hit(op, entry), want)


def why_batch(name, writes, want):
    if on_local_surface(name):
        verdict("task why cited: " + name, page_batch(writes), want)


def case_task_why_cited_reds():
    """Each case here must be refused as task-why-cited. The code before the rule passes each one, so each is red on it."""
    rows = rows_at("why-rows.json", WHY_ROWS)
    with local_rows(rows):
        why_guard("a capability line with no cite is refused", "set",
                  entry_of(task_item(STEPS, context=CAP + ".")), (WHY_RULE, None))
        why_guard("a works-row cite is refused, since the row says the act is doable here", "set",
                  entry_of(task_item(STEPS, context=CAP + " (route r-works).")), (WHY_RULE, None))
        why_guard("a cite of an id no row holds is refused", "set",
                  entry_of(task_item(STEPS, context=CAP + " (route r-missing).")), (WHY_RULE, None))
        why_guard("an undated measured cite is refused", "set",
                  entry_of(task_item(STEPS, context=CAP + " (measured, the proxy answered 403 to the delete).")),
                  (WHY_RULE, None))
        why_guard("a backtick tool name in place of a cite is refused, since the page reads no refusals file", "set",
                  entry_of(task_item(STEPS, context="Why yours: I can't delete it, since `%s` was refused this session."
                                     % BACKTICK_TOOL)), (WHY_RULE, None))
        why_guard("an update that carries kind task and an uncited context is refused", "update",
                  entry_of({"kind": "task", "context": CAP + "."}), (WHY_RULE, None))
        why_guard("a str_replace whose new_str holds an uncited capability line is refused", "str_replace",
                  {"collection": "items", "doc_id": DOC, "field": "context", "old_str": TASK_WHY, "new_str": CAP + "."},
                  (WHY_RULE, None))
        why_batch("a batch whose second write is uncited is refused",
                  [{"op": "set", "collection": "items", "doc_id": DOC, "data": task_item(STEPS)},
                   {"op": "set", "collection": "items", "doc_id": "second",
                    "data": task_item(STEPS, context=CAP + ".")}], (WHY_RULE, None))
        # A str_replace whose new_str holds only a cite, with no Why yours line: the cite must back on its own.
        why_guard("a str_replace that swaps a works-row cite in for a refused one is refused", "str_replace",
                  {"collection": "items", "doc_id": DOC, "field": "context", "old_str": "(route r-refused)",
                   "new_str": "(route r-works)"}, (WHY_RULE, None))
        why_guard("a str_replace that swaps an id no row holds in for a refused cite is refused", "str_replace",
                  {"collection": "items", "doc_id": DOC, "field": "context", "old_str": "(route r-refused)",
                   "new_str": "(route r-missing)"}, (WHY_RULE, None))
        why_guard("a str_replace that drops the date from a measured cite is refused", "str_replace",
                  {"collection": "items", "doc_id": DOC, "field": "context",
                   "old_str": "(measured 2026-11-06, the proxy answered 403)",
                   "new_str": "(measured, the proxy answered 403)"}, (WHY_RULE, None))
        why_guard("a plain edit that adds a works-row cite is refused", "str_replace",
                  {"collection": "items", "doc_id": DOC, "field": "context", "old_str": "Run the proxy check.",
                   "new_str": "Run the proxy check (route r-works)."}, (WHY_RULE, None))
        # The widened words: a capability line with no cite is refused, as "refused" and "403" are.
        why_guard("a could-not capability line with no cite is refused", "set",
                  entry_of(task_item(STEPS, context=CAP_COULD_NOT + ".")), (WHY_RULE, None))
        why_guard("a couldn't capability line with no cite is refused", "set",
                  entry_of(task_item(STEPS, context=CAP_COULDNT + ".")), (WHY_RULE, None))
        why_guard("a curly-apostrophe couldn't capability line with no cite is refused", "set",
                  entry_of(task_item(STEPS, context=CAP_COULDNT_CURLY + ".")), (WHY_RULE, None))
        why_guard("a rejected capability line with no cite is refused", "set",
                  entry_of(task_item(STEPS, context=CAP_REJECTED + ".")), (WHY_RULE, None))
        why_guard("a 401 capability line with no cite is refused", "set",
                  entry_of(task_item(STEPS, context=CAP_401 + ".")), (WHY_RULE, None))
        why_guard("a str_replace that adds an uncited 401 capability line is refused", "str_replace",
                  {"collection": "items", "doc_id": DOC, "field": "context", "old_str": TASK_WHY,
                   "new_str": CAP_401 + "."}, (WHY_RULE, None))
        why_guard("a reject capability line with no cite is refused", "set",
                  entry_of(task_item(STEPS, context=CAP_REJECT + ".")), (WHY_RULE, None))
        why_guard("a rejects capability line with no cite is refused", "set",
                  entry_of(task_item(STEPS, context=CAP_REJECTS + ".")), (WHY_RULE, None))
        why_guard("a rejecting capability line with no cite is refused", "set",
                  entry_of(task_item(STEPS, context=CAP_REJECTING + ".")), (WHY_RULE, None))
        why_guard("a being-rejected capability line with no cite is refused", "set",
                  entry_of(task_item(STEPS, context=CAP_REJECTED_BEING + ".")), (WHY_RULE, None))
        why_guard("a str_replace that adds an uncited rejects capability line is refused", "str_replace",
                  {"collection": "items", "doc_id": DOC, "field": "context", "old_str": TASK_WHY,
                   "new_str": CAP_REJECTS + "."}, (WHY_RULE, None))
    with local_rows(rows_at("why-rows-empty.json", [])):
        why_guard("a cite of an id in an empty rows file is refused", "set",
                  entry_of(task_item(STEPS, context=CAP + " (route r-refused).")), (WHY_RULE, None))
    # The scope control: a route-cited line reaches the rows file. Without a read, no cite is judged at all.
    with local_rows(rows), counted_rows_reads() as reads:
        if on_local_surface("a route-cited line reads the rows file"):
            guard_hit("set", entry_of(task_item(STEPS, context=CAP + " (route r-refused).")))
    check("task why cited: a route-cited line reads the rows file", len(reads) >= 1,
          "the rows file was read %d times for a route-cited line" % len(reads))


def case_task_why_cited_greens():
    """Each case here passes on the code before the rule, and must still pass once it lands: a cite the page accepts,
    a line the rule does not judge, and a rows file that does not judge."""
    rows = rows_at("why-rows.json", WHY_ROWS)
    with local_rows(rows):
        why_guard("a refused-row cite passes", "set",
                  entry_of(task_item(STEPS, context=CAP + " (route r-refused).")), None)
        why_guard("an asks-row cite passes", "set",
                  entry_of(task_item(STEPS, context=CAP + " (route r-asks).")), None)
        why_guard("a dated measured cite passes", "set",
                  entry_of(task_item(STEPS, context=CAP + " (measured 2026-11-06, the proxy answered 403 to the delete).")),
                  None)
        why_guard("a refused-row cite in a str_replace passes", "str_replace",
                  {"collection": "items", "doc_id": DOC, "field": "context", "old_str": TASK_WHY,
                   "new_str": CAP + " (route r-refused)."}, None)
        why_guard("a str_replace that swaps an asks-row cite in for a refused one passes", "str_replace",
                  {"collection": "items", "doc_id": DOC, "field": "context", "old_str": "(route r-asks)",
                   "new_str": "(route r-refused)"}, None)
        why_guard("a str_replace that swaps a dated measured cite in for a refused one passes", "str_replace",
                  {"collection": "items", "doc_id": DOC, "field": "context", "old_str": "(route r-refused)",
                   "new_str": "(measured 2026-11-06, the proxy answered 403)"}, None)
        why_guard("a Based on (measured) premise line in a str_replace passes", "str_replace",
                  {"collection": "items", "doc_id": DOC, "field": "context", "old_str": "Run the proxy check.",
                   "new_str": "Based on (measured): the proxy refused the delete (403)."}, None)
        why_guard("a bare premise-kind label in a str_replace passes, since it is no cite", "str_replace",
                  {"collection": "items", "doc_id": DOC, "field": "context", "old_str": "(read)",
                   "new_str": "(measured)"}, None)
        why_guard("a capability word outside the Why yours line passes", "set",
                  entry_of(task_item(STEPS, context="The cloud proxy refused the delete (403).\n" + TASK_WHY)), None)
        why_guard("a decision item with an uncited capability line passes, since the rule judges tasks", "set",
                  entry_of(page_item(tail="\n" + CAP + ".")), None)
        # Controls for the widened words: a dated measured cite or a refused-row cite backs the line, a choice phrase
        # keeps the act, and 401 inside a longer number is no status.
        why_guard("a rejected capability line with a dated measured cite passes", "set",
                  entry_of(task_item(STEPS, context=CAP_REJECTED + " (measured 2026-11-06, check_red_run exited 1).")),
                  None)
        why_guard("a 401 capability line with a refused-row cite passes", "set",
                  entry_of(task_item(STEPS, context=CAP_401 + " (route r-refused).")), None)
        why_guard("a could-not capability line with a refused-row cite passes", "set",
                  entry_of(task_item(STEPS, context=CAP_COULD_NOT + " (route r-refused).")), None)
        why_guard("a choice line with a widened word passes, since the owner keeps the act", "set",
                  entry_of(task_item(STEPS, context="Why yours: it is your call, and I couldn't decide for you.")),
                  None)
        why_guard("a 4012 near miss passes, since 401 inside a longer number is no status", "set",
                  entry_of(task_item(STEPS, context="Why yours: the lane on build 4012 needs the owner.")), None)
    with local_rows(rows_at("why-rows-cloud.json", [WHY_ROWS[3]])):
        why_guard("a row only on another surface passes", "set",
                  entry_of(task_item(STEPS, context=CAP + " (route r-cloud-only).")), None)
    with local_rows(os.path.join(RUN_FOLDER, "missing-route-rows.json")):
        why_guard("a cite against a rows file that does not exist passes", "set",
                  entry_of(task_item(STEPS, context=CAP + " (route r-refused).")), None)
    bad_path = os.path.join(RUN_FOLDER, "garbled-route-rows.json")
    with open(bad_path, "w", encoding="utf-8") as handle:
        handle.write("{not json")
    with local_rows(bad_path):
        why_guard("a cite against a rows file that is not JSON passes", "set",
                  entry_of(task_item(STEPS, context=CAP + " (route r-refused).")), None)
    # The cost control: a Why yours line with no route cite never reads the rows file, whatever its verb.
    with local_rows(rows), counted_rows_reads() as reads:
        why_guard("a Why yours line with no route cite passes", "set", entry_of(task_item(STEPS)), None)
        why_guard("a login line with no route cite passes", "set",
                  entry_of(task_item(STEPS, context="Why yours: this needs your login.")), None)
    check("task why cited: a Why yours line with no route cite never reads the rows file", not reads,
          "the rows file was read %d times" % len(reads))


# ------------------------------------------------------------------ chat only

def case_chat_boxes():
    chat("a good box (form lines, Gain and Lose in each option, one Recommended) passes", tcj.good_box(), None)
    chat("an empty input passes", {}, None)
    one = tcj.good_box()
    one["questions"][0].update(question="Ship it?", options=[{"label": "Yes", "description": "go"}])
    chat("a one-option question with no form lines passes", one, None)
    none = tcj.good_box()
    none["questions"][0].update(question="Ship it?", options=[])
    chat("a question with no options passes", none, None)
    mixed = tcj.good_box()
    mixed["questions"] += tcj.good_box(problem=None)["questions"]
    chat("a second question with 2+ options and no Problem line is refused, naming the line", mixed,
         (FORM_RULE, "Problem"))
    mixed = tcj.good_box()
    mixed["questions"].insert(0, one["questions"][0])
    chat("a one-option question beside a good question passes", mixed, None)

    wide = WIDE + "."
    options = tcj.good_options()
    options[0] = {"label": "Allow the second form (Recommended)",
                  "description": "Gain: it lands today. Lose: two forms stay. " + wide}
    chat("a t18-marked option in the description, labelled Recommended, is refused as uniform-pick",
         tcj.good_box(options=options), ("uniform-pick", None))
    options[0] = {"label": "Allow the second form, " + wide.rstrip(".") + " (Recommended)",
                  "description": "Gain: it lands today. Lose: two forms stay."}
    chat("a t18-marked option in the label, labelled Recommended, is refused as uniform-pick",
         tcj.good_box(options=options), ("uniform-pick", None))
    options = [{"label": "Allow the second form",
                "description": "Gain: it lands today. Lose: two forms stay. " + wide},
               {"label": "Keep one form (Recommended)", "description": "Gain: one form stays. Lose: it waits."}]
    chat("a t18-marked option that is not Recommended passes beside a Recommended one",
         tcj.good_box(options=options), None)

    options = tcj.good_options()
    options[1] = {"label": "Press Merge in GitHub", "description": "Gain: it lands at once. Lose: nobody reads it first."}
    chat("a press in GitHub with no url in the option's description is refused as press-link",
         tcj.good_box(options=options), ("press-link", None))
    options[1]["description"] += " https://github.com/shivinate7/home/pull/374"
    chat("a press in GitHub with an https url in the option's description passes",
         tcj.good_box(options=options), None)
    options = tcj.good_options()
    options[1] = {"label": "Press Merge in GitHub", "description": "Gain: it lands at once. Lose: nobody reads it first."}
    options[0]["description"] += " https://github.com/shivinate7/home/pull/374"
    chat("a url on another option does not stand in for the one that presses", tcj.good_box(options=options),
         ("press-link", None))


# ------------------------------------------------------------------ the order of the lines, prose that starts with Based on

PROSE = "Based on the log, option A is safer."
# (name, the context lines in order, verdict). Only `Based on (<kind>):` is a Based on line, so prose that
# starts with the same two words is not one, and does not move a Based on line before Problem.
LINE_VARIANTS = [
    ("the lines in order", [GOAL, PROBLEM, *BASED, DEPARTS], None),
    ("Problem before Goal", [PROBLEM, GOAL, *BASED, DEPARTS], (FORM_RULE, None)),
    ("a Based on line before Problem", [GOAL, BASED[0], PROBLEM, BASED[1], DEPARTS], (FORM_RULE, None)),
    ("every Based on line before Problem", [GOAL, *BASED, PROBLEM, DEPARTS], (FORM_RULE, None)),
    ("a Based on line before Goal", [BASED[0], GOAL, PROBLEM, BASED[1], DEPARTS], (FORM_RULE, None)),
    ("prose that starts with Based on, after the form lines", [GOAL, PROBLEM, *BASED, DEPARTS, PROSE], None),
    ("prose that starts with Based on, between Goal and Problem", [GOAL, PROSE, PROBLEM, *BASED, DEPARTS], None),
    ("prose that starts with Based on, beside three Based on lines",
     [GOAL, PROBLEM, *BASED, THIRD, PROSE, DEPARTS], None),
    ("prose that starts with Based on is no Based on line", [GOAL, PROBLEM, PROSE, DEPARTS], (FORM_RULE, "Based on")),
    ("a Based on kind outside PREMISE_KINDS still refuses beside the prose",
     [GOAL, PROBLEM, BASED[0], "Based on (guess): the log is old.", PROSE, DEPARTS], (FORM_RULE, "Based on")),
]


def case_line_order_and_prose():
    for name, lines, want in LINE_VARIANTS:
        # The Waiting on line goes last on the page; the chat box carries no such line, so it gets none.
        page(name, "set", entry_of(page_item(lines=lines + [WAITING])), want)
        box = tcj.good_box()
        box["questions"][0]["question"] = "\n".join(lines)
        chat(name, box, want)


# ------------------------------------------------------------------ a press the session makes needs no link

# Decision act-in-place: a session clause that hides an owner press. The press is the owner's, so the option
# needs a link.
HIDDEN_OWNER_PRESS = [
    "The session merges PR #374 after the owner clicks Approve.",
    "The session merges PR #374 but click Merge first.",
    "The session merges PR #374, so click Merge.",
    "The session merges PR #374: press Merge.",
    "The session merges PR #374 - press Merge on GitHub.",
    "The session merges PR #374 (press Merge).",
    "The session merges PR #374 after Shivam approves it on GitHub.",
    "The session merges PR #374 so you hit Merge on GitHub.",
    "The session merges PR #374 but you approve it on GitHub.",
    "The session merges PR #374: you approve it on GitHub.",
]
# A session clause with no press in it, and a press the session makes after the pick: both pass. An owner
# word (the owner, he, Shivam) in a clause with no press verb asks the owner for nothing, so it passes too.
SESSION_ONLY = ["The session merges PR #374.", "After the pick, the session merges PR #374.",
                "The session merges PR #374 as the owner asked.",
                "The session merges PR #374 once the owner's approval is in.",
                "The session merges PR #374 as he asked.",
                "The session merges PR #374 after Shivam's OK.",
                "The session merges PR #374 so CI reruns."]
# The how-text of an option labelled "Go": a split cuts the mark-ready press, so it is refused. The waiting
# page's own button, or a past act, asks the owner for no web press: each passes, with the label "Merge the PR".
GO_SPLIT_PRESS = [
    "The session merges it after your pick. Mark the PR (#12) ready for review.",
    "The session merges it after your pick. Mark PR #12: ready for review.",
    "The session merges it after your pick. Mark PR #12 - ready for review.",
    "The session merges it after your pick. Mark PR #12, ready for review.",
    "The session merges it after your pick. Mark the draft PR and ready on GitHub.",
]
PAGE_BUTTON_OR_PAST_ACT = [
    "The session merges it after Shivam hits Take my pick.",
    "The session merges it after he hits Send.",
    "The session merges it after Shivam approves this item.",
    "The session merges it after he has merged the base PR.",
    "The session merges it after the owner approved the plan.",
]
# A Claude clause that names a press not yet made, as a noun or behind a possessive ("after your click", "after the
# owner's click"), hands the press to the owner, so it is refused: the option needs a link.
CLAUDE_NAMES_OWNER_PRESS = [
    "Claude merges them after your click on Merge.",
    "Claude merges them after the owner's click on Merge.",
]
# A session clause that clicks or presses Merge after the owner's pick is the session's own act, as "merges" is.
# The owner presses nothing, so the option needs no link.
SESSION_PRESSES_AFTER_PICK = [
    "The session clicks Merge after your pick.",
    "The session presses Merge after your pick.",
]
# A Claude clause that waits for, or needs, an owner's press ("the owner's merge", "the owner has to approve it",
# "the owner reviews and approves it") leaves that press to the owner, so it is refused: the option needs a link.
CLAUDE_WAITS_ON_OWNER_PRESS = [
    "Claude waits for the owner's merge.",
    "Claude merges once the owner has to approve it.",
    "Claude merges after the owner reviews and approves it.",
]
# A session or Claude clause that joins a press by "and" with no subject ("and approve it", "and approve on GitHub"),
# or that waits on the owner's approval, leaves that press to the owner: the option needs a link.
SESSION_LEAVES_OWNER_PRESS = [
    "The session merges PR #374 and approve on GitHub.",
    "The session clicks Merge and approve it.",
    "Claude merges PR #374 after the review and approve it.",
    "The session clicks Merge after the owner's approval.",
]
# "the owner's merge commit" names a git object the session keeps, not a press the owner makes: it needs no link.
SESSION_KEEPS_OWNER_MERGE = ["The session merges PR #374 keeping the owner's merge commit."]
# The owner's rights, access, queue or method, and a press he has already made ("has hit Merge"), name no press he
# makes now: the session merges, and he presses nothing. Each passes.
SESSION_NAMES_OWNER_RIGHTS = [
    "The session merges PR #374 because the owner has merge rights.",
    "The session merges PR #374 because Shivam has merge access.",
    "The session merges PR #374 after the owner has hit Merge.",
    "The session merges PR #374 through the owner's merge queue.",
    "The session merges PR #374 with the owner's merge method.",
]
# A label that asks him to click is his press whatever the how says: the session's click in the how leaves it his.
LABEL_ASKS_CLICK_SESSION_HOW = [("Click Merge on GitHub", "The session clicks Merge after your pick.")]


def case_session_press_needs_no_link():
    # Decision act-in-place: the rule covers a press the owner makes. An option whose how says the session makes
    # the press, after the owner's pick, asks him for no press, so it needs no link. An option that asks him to
    # press, with no link, is still refused.
    session = {"key": "a", "label": "Merge PR #374", "how": "The session merges PR #374 after your pick.",
               "gain": "It lands at once.", "lose": "Nobody reads it first."}
    owner = dict(session, how="Press Merge in GitHub.")
    keep = {"key": "b", "label": "Hold it", "how": "Do nothing yet.", "gain": "A reviewer reads it first.",
            "lose": "The change lands a day later."}
    page("a press the session makes after the pick, with no link, passes", "set",
         entry_of(page_item(options=[session, keep])), None)
    page("an owner press of Merge PR #374 in GitHub, with no link, is refused as press-link", "set",
         entry_of(page_item(options=[owner, keep])), ("press-link", None))
    # Decision act-in-place: an option whose label asks him to press is an owner press, whatever its how says.
    for label, how in (("Approve on GitHub", "The session records your pick and reruns CI."),
                       ("Pick this", "The session opens PR #374 after your pick, then press Merge."),
                       ("Click Merge on GitHub", "The session merges after your pick.")):
        page("an owner press labelled %r, with no link, is refused as press-link" % label, "set",
             entry_of(page_item(options=[dict(session, label=label, how=how), keep])), ("press-link", None))
    page("a session press after the pick, with no link, passes when the pick comes first", "set",
         entry_of(page_item(options=[dict(session, how="After the pick, the session merges PR #374."), keep])), None)
    chat("a press the session makes after the pick, with no url, passes",
         chat_box(options=[{"label": "Merge PR #374", "description": "The session merges PR #374 after your pick. "
                                                                    "Gain: it lands at once. Lose: nobody reads it first."},
                           {"label": "Hold it", "description": "Gain: a reviewer reads it first. Lose: the change lands a day later."}]),
         None)
    chat("an owner press of Merge PR #374 in GitHub, with no url, is refused as press-link",
         chat_box(options=[{"label": "Merge PR #374", "description": "Press Merge in GitHub. Gain: it lands at once. "
                                                                    "Lose: nobody reads it first."},
                           {"label": "Hold it", "description": "Gain: a reviewer reads it first. Lose: the change lands a day later."}]),
         ("press-link", None))
    # Decision act-in-place: a session clause that names the owner, or a press set off by a colon, dash,
    # parenthesis, `but` or `so`, is no session act. The press in it is the owner's and needs a link.
    def chat_of(option):
        return {"label": option["label"],
                "description": "%s Gain: %s Lose: %s" % (option["how"], option["gain"], option["lose"])}

    for how in HIDDEN_OWNER_PRESS:
        page("a session clause that hides an owner press, %r, with no link, is refused as press-link" % how, "set",
             entry_of(page_item(options=[dict(session, how=how), keep])), ("press-link", None))
        chat("a session clause that hides an owner press, %r, with no url, is refused as press-link" % how,
             chat_box(options=[chat_of(dict(session, how=how)), chat_of(keep)]), ("press-link", None))
    for how in CLAUDE_NAMES_OWNER_PRESS:
        page("a Claude clause that names an owner press, %r, with no link, is refused as press-link" % how, "set",
             entry_of(page_item(options=[dict(session, how=how), keep])), ("press-link", None))
        chat("a Claude clause that names an owner press, %r, with no url, is refused as press-link" % how,
             chat_box(options=[chat_of(dict(session, how=how)), chat_of(keep)]), ("press-link", None))
    for how in SESSION_PRESSES_AFTER_PICK:
        page("a session clause that clicks or presses after the pick, %r, with no link, passes" % how, "set",
             entry_of(page_item(options=[dict(session, how=how), keep])), None)
        chat("a session clause that clicks or presses after the pick, %r, with no url, passes" % how,
             chat_box(options=[chat_of(dict(session, how=how)), chat_of(keep)]), None)
    for how in CLAUDE_WAITS_ON_OWNER_PRESS:
        page("a Claude clause that waits for an owner press, %r, with no link, is refused as press-link" % how, "set",
             entry_of(page_item(options=[dict(session, how=how), keep])), ("press-link", None))
        chat("a Claude clause that waits for an owner press, %r, with no url, is refused as press-link" % how,
             chat_box(options=[chat_of(dict(session, how=how)), chat_of(keep)]), ("press-link", None))
    for how in SESSION_LEAVES_OWNER_PRESS:
        page("a session clause that leaves an owner press, %r, with no link, is refused as press-link" % how, "set",
             entry_of(page_item(options=[dict(session, how=how), keep])), ("press-link", None))
        chat("a session clause that leaves an owner press, %r, with no url, is refused as press-link" % how,
             chat_box(options=[chat_of(dict(session, how=how)), chat_of(keep)]), ("press-link", None))
    for how in SESSION_KEEPS_OWNER_MERGE:
        page("a session clause that keeps the owner's merge commit, %r, with no link, passes" % how, "set",
             entry_of(page_item(options=[dict(session, how=how), keep])), None)
        chat("a session clause that keeps the owner's merge commit, %r, with no url, passes" % how,
             chat_box(options=[chat_of(dict(session, how=how)), chat_of(keep)]), None)
    for how in SESSION_NAMES_OWNER_RIGHTS:
        page("a session clause that names the owner's rights or a past press, %r, with no link, passes" % how, "set",
             entry_of(page_item(options=[dict(session, how=how), keep])), None)
        chat("a session clause that names the owner's rights or a past press, %r, with no url, passes" % how,
             chat_box(options=[chat_of(dict(session, how=how)), chat_of(keep)]), None)
    for label, how in LABEL_ASKS_CLICK_SESSION_HOW:
        page("a label %r that asks him to click, with how %r, with no link, is refused as press-link" % (label, how),
             "set", entry_of(page_item(options=[dict(session, label=label, how=how), keep])), ("press-link", None))
        chat("a label %r that asks him to click, with how %r, with no url, is refused as press-link" % (label, how),
             chat_box(options=[chat_of(dict(session, label=label, how=how)), chat_of(keep)]), ("press-link", None))
    for how in SESSION_ONLY:
        page("a session clause with no press, %r, with no link, passes" % how, "set",
             entry_of(page_item(options=[dict(session, how=how), keep])), None)
        chat("a session clause with no press, %r, with no url, passes" % how,
             chat_box(options=[chat_of(dict(session, how=how)), chat_of(keep)]), None)
    for how in GO_SPLIT_PRESS:
        page("a split that cuts a mark-ready press, %r, with no link, is refused as press-link" % how, "set",
             entry_of(page_item(options=[dict(session, label="Go", how=how), keep])), ("press-link", None))
        chat("a split that cuts a mark-ready press, %r, with no url, is refused as press-link" % how,
             chat_box(options=[chat_of(dict(session, label="Go", how=how)), chat_of(keep)]), ("press-link", None))
    for how in PAGE_BUTTON_OR_PAST_ACT:
        page("a page-button press or a past act, %r, with no link, passes" % how, "set",
             entry_of(page_item(options=[dict(session, label="Merge the PR", how=how), keep])), None)
        chat("a page-button press or a past act, %r, with no url, passes" % how,
             chat_box(options=[chat_of(dict(session, label="Merge the PR", how=how)), chat_of(keep)]), None)


# ------------------------------------------------------------------ the session's own merge, named as Claude

def case_claude_own_merge_needs_no_link():
    # Decision act-in-place: an option whose how says Claude makes the press after the owner's pick is the
    # session's act, as "The session merges ..." is, so the owner presses nothing and it needs no link. A press in
    # another clause, an owner's own act, and a label that asks him to click still need one.
    claude = {"key": "a", "label": "Merge the lane PRs into one batch.", "how": "Claude merges them after your pick.",
              "gain": "One batch lands at once.", "lose": "A second CI run."}
    keep = {"key": "b", "label": "Hold it", "how": "Do nothing yet.", "gain": "A reviewer reads it first.",
            "lose": "The change lands a day later."}
    hold = {"label": "Hold it", "description": "Gain: a reviewer reads it first. Lose: the change lands a day later."}
    page("Claude's own merge after the pick, with no link, passes", "set",
         entry_of(page_item(options=[claude, keep])), None)
    chat("Claude's own merge after the pick, with no url, passes",
         chat_box(options=[{"label": "Merge the lane PRs into one batch.",
                            "description": "Claude merges them after your pick. Gain: one batch lands at once. "
                                           "Lose: a second CI run."}, hold]),
         None)
    # Claude asking the owner to press is the owner's press, however the clause starts with Claude, and however
    # an adverb, "to", "please" or "for a click" stands between the owner's name and the act.
    for how in ("Claude merges them after your pick, then you click Merge on GitHub.",
                "Shivam merges the lane PRs on GitHub.",
                "Claude asks the owner to press Merge on GitHub.",
                "Claude asks Shivam to click Merge on GitHub.",
                "Claude asks the owner to just click Merge.",
                "Claude asks the owner to please click Merge.",
                "Claude asks him to press Merge.",
                "Claude asks the user to press Merge.",
                "Claude asks the owner for a click on Merge."):
        page("%r, with no link, is refused as press-link" % how, "set",
             entry_of(page_item(options=[dict(claude, how=how), keep])), ("press-link", None))
        chat("%r, with no url, is refused as press-link" % how,
             chat_box(options=[{"label": claude["label"],
                                "description": "%s Gain: one batch lands at once. Lose: a second CI run." % how},
                               hold]),
             ("press-link", None))
    page("a label that clicks Merge on GitHub, with Claude's merge as the how, is refused as press-link", "set",
         entry_of(page_item(options=[dict(claude, label="Click Merge on GitHub."), keep])), ("press-link", None))
    chat("a label that clicks Merge on GitHub, with Claude's merge in the description, is refused as press-link",
         chat_box(options=[{"label": "Click Merge on GitHub.",
                            "description": "Claude merges them after your pick. Gain: one batch lands at once. "
                                           "Lose: a second CI run."}, hold]),
         ("press-link", None))


# ------------------------------------------------------------------ a press in the how-text only

def case_chat_press_scan_skips_gain_and_lose():
    # The page scans an option's label and how; the chat scan reads the label and the description without
    # its Gain and Lose text, which says what the pick does to the owner and is no instruction to press.
    keep = tcj.good_options()[1]
    options = [{"label": "Go ahead (Recommended)", "description": "Gain: merge the pull request today. Lose: nothing."},
               keep]
    chat("a Gain that says merge the pull request is no press", tcj.good_box(options=options), None)
    options[0]["description"] = "Gain: it lands today. Lose: click the button once more on GitHub."
    chat("a Lose that says click on GitHub is no press", tcj.good_box(options=options), None)
    options[0]["description"] = "Press Merge on the pull request in GitHub. Gain: it lands today. Lose: nothing."
    chat("a press in the how-text with no url still refuses as press-link", tcj.good_box(options=options),
         ("press-link", None))
    options[0]["description"] += " https://github.com/shivinate7/home/pull/374"
    chat("a press in the how-text with an https url passes", tcj.good_box(options=options), None)


# ------------------------------------------------------------------ the reasons a refusal prints

# What each chat refusal must tell the agent to write, and the words that belong to the waiting page only:
# a chat box has no `stands`, `context`, `links` or `pick` field to set.
CHAT_REMEDY = {FORM_RULE: ("Goal", "Problem", "Based on", "Gain", "Lose"), "owner-judge": tuple(OWNER_STAKES),
               "uniform-pick": ("(Recommended)",), "press-link": ("https://",), DEPARTS_RULE: ("Departs from",)}
PAGE_ONLY = ("stands", "`context`", "waiting page", "`links`", "`pick`", "`gain`", "`lose`")


def case_chat_reasons_name_a_remedy_and_no_page_field():
    table = getattr(question_form, "CHAT_REASONS", None)
    if table is None:
        check("chat reasons: question_form.CHAT_REASONS is the table of chat reasons", False, MISSING)
        return
    for rule, text in table.items():
        named = [word for word in PAGE_ONLY if word in text]
        check("chat reasons: the %s reason names no field of the waiting page" % rule, not named, named)
        missing = [word for word in CHAT_REMEDY.get(rule, ("<no remedy pinned for this rule>",)) if word not in text]
        check("chat reasons: the %s reason names its remedy" % rule, not missing, missing)
    options = tcj.good_options()
    options[0] = {"label": "Allow the second form (Recommended)",
                  "description": "Gain: it lands today. Lose: two forms stay. " + WIDE + "."}
    press = tcj.good_options()
    press[1] = {"label": "Press Merge in GitHub", "description": "Gain: it lands at once. Lose: nobody reads it first."}
    for name, box in (("a missing Problem line", tcj.good_box(problem=None)),
                      ("a stake outside the set", tcj.good_box(problem="Problem (internals): which job runs it")),
                      ("a Recommended widening option", tcj.good_box(options=options)),
                      ("a press with no url", tcj.good_box(options=press))):
        r = tcj.run_hook(tcj.question_input(box=box), answer=tcj.ALLOW)
        said = r.reason()
        rule = said.split(":", 1)[0]
        named = [word for word in PAGE_ONLY if word in said]
        check("chat reasons: call_judge's refusal for %s names no field of the waiting page" % name,
              bool(said) and not named, named or tcj.detail(r))
        missing = [word for word in CHAT_REMEDY.get(rule, ("<no remedy pinned for rule %s>" % rule,)) if word not in said]
        check("chat reasons: call_judge's refusal for %s names its remedy" % name, bool(said) and not missing,
              missing or tcj.detail(r))


# One table of page reasons: guard.py prints the text of question_form.PAGE_REASONS, so a change to the
# table shows in the refusal. The guard runs in this process with the table's text marked, and the mark
# must reach the printed reason; a guard that prints its own copy of the text does not show it.
def printed_reason(tool_input):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            guard.judge({"tool_name": "ArtifactData", "tool_input": tool_input, "cwd": PAGE_REPO})
        except SystemExit:
            pass
    text = out.getvalue().strip()
    return json.loads(text)["hookSpecificOutput"]["permissionDecisionReason"] if text else ""


def case_page_reasons_are_one_table():
    table = getattr(question_form, "PAGE_REASONS", None)
    if table is None:
        check("page reasons: question_form.PAGE_REASONS is the table of page reasons", False, MISSING)
        return
    task = task_item(["Open Terminal"])
    press = copy.deepcopy(ITEM92["options"])
    press[1].update(label="Press Merge in GitHub", how="Do it by hand.")
    for name, data in (
            ("a decision with no Problem line", ITEM92),
            ("a stake outside the set", page_item(problem="Problem (internals): which job runs it")),
            ("a port with no Departs from line", page_item(port=True, departs=None)),
            ("a decision with no Departs from line", page_item(departs=None)),
            ("a pick that names the widening option", page_item(pick="b")),
            ("a press with no link", page_item(options=press)),
            ("a step that sends the owner to a file for a command",
             dict(task, steps=["Open plans/merge.md", "Run its command"])),
            ("a task with no Why yours line", dict(task, context="Nothing here.")),
            ("a gh command with no switch", gh_task(GH_PATCH, GH_PATCH))):
        tool_input = {"url": PAGE_URL, "action": "set", "collection": "items", "doc_id": DOC, "data": data}
        rule = guard.data_tool_hit(tool_input, PAGE_REPO)[0]
        if rule not in table:
            check("page reasons: %s is refused by a rule in the table" % name, False, "rule %r" % rule)
            continue
        original = table[rule]
        check("page reasons: the refusal for %s prints the table's text of rule %s" % (name, rule),
              original in printed_reason(tool_input), printed_reason(tool_input)[:200])
        table[rule] = "TABLEMARK " + original
        try:
            marked = printed_reason(tool_input)
        finally:
            table[rule] = original
        check("page reasons: the refusal for %s reads its text from the table (%s)" % (name, rule),
              "TABLEMARK" in marked, marked[:200])


# ------------------------------------------------------------------ the gh login switch

# The default gh login is shivinate7; ssemwal-cdc is only for a repo shivinate7 cannot reach
# (decision `act-in-place`). The value pins live in test_shared_names.py; the literals here are the inputs.
GH_PATCH = ("gh api -X PATCH repos/shivinate7/claude-settings/branches/main/protection/"
            "required_status_checks -f strict=true")
GH_WHY = "Why yours: a session on your computer was asked first and none could reach the remote"


def gh_task(mac, ps, **over):
    """A task whose command is {powershell, mac}. `mac` is bash and `ps` its PowerShell 5.1-safe twin."""
    task = {"n": 928, "kind": "task", "title": "Protect main on claude-settings", "status": "open",
            "steps": ["Open Terminal", "Paste the command below and run it"], "context": GH_WHY,
            "command": {"powershell": ps, "mac": mac}}
    task.update(over)
    return task


def gh_hit(name, data, deny):
    """gh_login_hit(data) is a non-empty string for a deny and "" for a pass. A missing function, or a call
    that raises, fails the case by name: neither can pass for a deny."""
    if getattr(question_form, "gh_login_hit", None) is None:
        check(name, False, MISSING[1])
        return
    got = call("gh_login_hit", data)
    if not isinstance(got, str):
        check(name, False, "want a str, got %r" % (got,))
        return
    check(name, bool(got) == deny, "want %s, got %r" % ("deny" if deny else "pass", got))


def case_gh_login_hit_direct():
    gh_hit("gh login switch: the incident PATCH with no switch is denied", gh_task(GH_PATCH, GH_PATCH), True)
    gh_hit("gh login switch: a switch after the gh line is denied",
           gh_task(GH_PATCH + "\ngh auth switch -u shivinate7", GH_PATCH + "\ngh auth switch -u shivinate7"), True)
    gh_hit("gh login switch: ssemwal-cdc before a shivinate7/ repo is denied",
           gh_task("gh auth switch -u ssemwal-cdc && " + GH_PATCH, "gh auth switch -u ssemwal-cdc; " + GH_PATCH), True)
    gh_hit("gh login switch: a cd then gh pr ready, with no switch, is denied",
           gh_task("cd x && gh pr ready 5", "cd x; gh pr ready 5"), True)
    gh_hit("gh login switch: a login outside the pair is denied",
           gh_task("gh auth switch -u someoneelse && gh pr ready 5", "gh auth switch -u someoneelse; gh pr ready 5"), True)
    gh_hit("gh login switch: a gh command after a pipe is denied",
           gh_task("printf '{}' | gh api -X PUT repos/shivinate7/claude-settings/branches/main/protection --input -",
                   "'{}' | gh api -X PUT repos/shivinate7/claude-settings/branches/main/protection --input -"), True)
    gh_hit("gh login switch: a gh command after a semicolon is denied",
           gh_task("cd x; gh pr ready 5", "cd x; gh pr ready 5"), True)
    gh_hit("gh login switch: a continued gh api with no switch is denied",
           gh_task("gh api -X PATCH \\\n  repos/shivinate7/claude-settings/branches/main/protection/required_status_checks \\\n  -f strict=true",
                   "gh api -X PATCH `\n  repos/shivinate7/claude-settings/branches/main/protection/required_status_checks `\n  -f strict=true"),
           True)
    gh_hit("gh login switch: a # inside quotes does not hide a gh command is denied",
           gh_task('echo "# note" && gh api repos/shivinate7/claude-settings/branches/main/protection',
                   'echo "# note"; gh api repos/shivinate7/claude-settings/branches/main/protection'), True)
    gh_hit("gh login switch: a # after a quote does not cut off a gh command is denied",
           gh_task('echo "x #" ; gh pr ready 5', 'echo "x #" ; gh pr ready 5'), True)
    gh_hit("gh login switch: a gh command after a multi-line quoted argument is denied",
           gh_task('gh pr comment 5 --body "first\nsecond"', 'gh pr comment 5 --body "first\nsecond"'), True)
    gh_hit("gh login switch: a switch named inside quotes does not count is denied",
           gh_task('echo "gh auth switch -u shivinate7" && gh pr ready 5', 'echo "gh auth switch -u shivinate7"; gh pr ready 5'),
           True)
    gh_hit("gh login switch: a switch named in a # line does not count is denied",
           gh_task("# gh auth switch -u shivinate7\ngh pr ready 5", "# gh auth switch -u shivinate7\ngh pr ready 5"), True)
    gh_hit("gh login switch: a lone quote in text before a gh command is denied",
           gh_task("echo Don't && gh pr ready 5", 'echo "Don\'t"; gh pr ready 5'), True)

    gh_hit("gh login switch: a switch to shivinate7, then gh api, is allowed",
           gh_task("gh auth switch -u shivinate7 && " + GH_PATCH, "gh auth switch -u shivinate7; " + GH_PATCH), False)
    gh_hit("gh login switch: the long form, --user shivinate7, is allowed",
           gh_task("gh auth switch --user shivinate7 && gh pr ready 5", "gh auth switch --user shivinate7; gh pr ready 5"),
           False)
    gh_hit("gh login switch: a switch and a gh command joined by a semicolon are allowed",
           gh_task("gh auth switch -u shivinate7; gh pr ready 5", "gh auth switch -u shivinate7; gh pr ready 5"), False)
    gh_hit("gh login switch: a cd line, then the switch, then gh, is allowed",
           gh_task("cd x\ngh auth switch -u shivinate7\ngh pr ready 5", "cd x\ngh auth switch -u shivinate7\ngh pr ready 5"),
           False)
    gh_hit("gh login switch: a # open Git Bash line, cd, the switch, then gh, is allowed",
           gh_task("# open Git Bash\ncd x\ngh auth switch -u shivinate7\ngh pr ready 5",
                   "# open Git Bash\ncd x\ngh auth switch -u shivinate7\ngh pr ready 5"), False)
    gh_hit("gh login switch: a switch with no gh command after it is allowed",
           gh_task("gh auth switch -u shivinate7", "gh auth switch -u shivinate7"), False)
    gh_hit("gh login switch: a gh command only in a # comment line is allowed",
           gh_task("# gh pr ready 5", "# gh pr ready 5"), False)
    gh_hit("gh login switch: a gh command echoed as text is allowed",
           gh_task('echo "gh pr list"', 'echo "gh pr list"'), False)
    gh_hit("gh login switch: a command that is only gh auth login is allowed",
           gh_task("gh auth login", "gh auth login"), False)
    gh_hit("gh login switch: a command with no gh is allowed",
           gh_task("python3 hooks/test_guard.py", "python3 hooks/test_guard.py"), False)
    gh_hit("gh login switch: ghq is not gh and is allowed", gh_task("ghq get x", "ghq get x"), False)
    gh_hit("gh login switch: ssemwal-cdc on a repo not under shivinate7 is allowed",
           gh_task("gh auth switch -u ssemwal-cdc && gh api repos/ssemwal-cdc/ops-tools/pulls/5",
                   "gh auth switch -u ssemwal-cdc; gh api repos/ssemwal-cdc/ops-tools/pulls/5"), False)
    gh_hit("gh login switch: a lone quote in a comment line before the switch is allowed",
           gh_task("# Don't forget\ngh auth switch -u shivinate7\ngh pr ready 5",
                   "# Don't forget\ngh auth switch -u shivinate7\ngh pr ready 5"), False)
    gh_hit("gh login switch: a decision holding a gh command is not judged",
           gh_task(GH_PATCH, GH_PATCH, kind="decision"), False)

    # Deny pins: each shell judges its own text. A switch in one shell does not stand for the other.
    gh_hit("gh login switch: a switch to shivinate7 in mac only is denied",
           gh_task("gh auth switch -u shivinate7 && " + GH_PATCH, GH_PATCH), True)
    gh_hit("gh login switch: a switch to shivinate7 in powershell only is denied",
           gh_task(GH_PATCH, "gh auth switch -u shivinate7; " + GH_PATCH), True)
    gh_hit("gh login switch: ssemwal-cdc on a shivinate7/ repo in mac only is denied",
           gh_task("gh auth switch -u ssemwal-cdc && " + GH_PATCH, "gh auth switch -u shivinate7; " + GH_PATCH), True)
    gh_hit("gh login switch: ssemwal-cdc on a shivinate7/ repo in powershell only is denied",
           gh_task("gh auth switch -u shivinate7 && " + GH_PATCH, "gh auth switch -u ssemwal-cdc; " + GH_PATCH), True)

    # Cases for PowerShell paths, gh text in a quoted body, a lone quote, sudo and env.
    # The mac twin of a PowerShell path uses forward slashes: bash reads `"C:\repo\"` as an open quote.
    gh_hit("gh login switch: a PowerShell Set-Location with a trailing backslash, then the switch, then gh, is allowed",
           gh_task('cd "/repo/"\ngh auth switch -u shivinate7\ngh pr view 5',
                   r'Set-Location "C:\repo\"' + "\ngh auth switch -u shivinate7\ngh pr view 5"), False)
    gh_hit("gh login switch: a PowerShell cd to a backslash path, then the switch, then gh, is allowed",
           gh_task("cd /Users/me/repo\ngh auth switch -u shivinate7\ngh pr view 5",
                   r"cd C:\Users\me\repo" + "\ngh auth switch -u shivinate7\ngh pr view 5"), False)
    gh_hit("gh login switch: a PowerShell Set-Location with a trailing backslash, then gh with no switch, is denied",
           gh_task('cd "/repo/"\ngh pr view 5', r'Set-Location "C:\repo\"' + "\ngh pr view 5"), True)
    gh_hit("gh login switch: a multi-line quoted body that holds gh text, after the switch, is allowed",
           gh_task('gh auth switch -u shivinate7\ngh pr comment 5 --body "first\ngh pr merge 5\nsecond"',
                   'gh auth switch -u shivinate7\ngh pr comment 5 --body "first\ngh pr merge 5\nsecond"'), False)
    gh_hit("gh login switch: a lone quote in text after the switch is allowed",
           gh_task("gh auth switch -u shivinate7\necho Don't\ngh pr ready 5",
                   'gh auth switch -u shivinate7\necho "Don\'t"\ngh pr ready 5'), False)
    gh_hit("gh login switch: sudo gh after the switch is allowed",
           gh_task("gh auth switch -u shivinate7 && sudo gh pr ready 5", "gh auth switch -u shivinate7; sudo gh pr ready 5"),
           False)
    gh_hit("gh login switch: sudo gh with no switch is denied",
           gh_task("sudo gh pr ready 5", "sudo gh pr ready 5"), True)
    gh_hit("gh login switch: env GH_HOST=x gh after the switch is allowed",
           gh_task("gh auth switch -u shivinate7 && env GH_HOST=x gh pr ready 5",
                   "gh auth switch -u shivinate7; env GH_HOST=x gh pr ready 5"), False)
    gh_hit("gh login switch: env GH_HOST=x gh with no switch is denied",
           gh_task("env GH_HOST=x gh pr ready 5", "env GH_HOST=x gh pr ready 5"), True)
    gh_hit("gh login switch: a bare switch to ssemwal-cdc, then gh api on a shivinate7 repo, is denied",
           gh_task("gh auth switch -u ssemwal-cdc\ngh api repos/shivinate7/x",
                   "gh auth switch -u ssemwal-cdc\ngh api repos/shivinate7/x"), True)


def case_gh_login_switch_on_the_page():
    page("gh login switch: a gh command with no switch is refused as gh-login-switch", "set",
         entry_of(gh_task(GH_PATCH, GH_PATCH)), ("gh-login-switch", None))
    page("gh login switch: a file step that holds a gh command is refused by command-in-item first", "set",
         entry_of(gh_task(GH_PATCH, GH_PATCH, steps=["Open plans/gh.md", "Run its command"])), ("command-in-item", None))
    page("gh login switch: a switch first is allowed on the page", "set",
         entry_of(gh_task("gh auth switch -u shivinate7 && " + GH_PATCH, "gh auth switch -u shivinate7; " + GH_PATCH)), None)
    # A str_replace on the task's command is judged on the text that replaces old_str.
    page("gh login switch: a str_replace that adds a gh command with no switch to command is refused", "str_replace",
         {"collection": "items", "doc_id": DOC, "field": "command", "old_str": "step one",
          "new_str": "step one\ngh pr merge 5"}, ("gh-login-switch", None))
    page("gh login switch: a str_replace on command that adds a switch, then gh, is allowed", "str_replace",
         {"collection": "items", "doc_id": DOC, "field": "command", "old_str": "step one",
          "new_str": "gh auth switch -u shivinate7\ngh pr merge 5"}, None)
    page("gh login switch: a str_replace on command with no gh text is allowed", "str_replace",
         {"collection": "items", "doc_id": DOC, "field": "command", "old_str": "step one",
          "new_str": "step two"}, None)
    # A str_replace that changes one gh line to another adds no gh line. Rule gh-login-switch asks for the switch
    # when an edit adds a gh line (the waiting-page skill's wording); the stored command keeps its own switch.
    page("gh login switch: a str_replace that changes one gh line to another, on a command that keeps its switch, is allowed",
         "str_replace", {"collection": "items", "doc_id": DOC, "field": "command",
                         "old_str": "gh pr view 3", "new_str": "gh pr view 4"}, None)
    # An edit that removes the switch from a command that still runs gh is refused, and so is one that adds a gh
    # line with no switch beside the line it keeps.
    page("gh login switch: a str_replace that removes the switch and leaves a gh line is refused", "str_replace",
         {"collection": "items", "doc_id": DOC, "field": "command",
          "old_str": "gh auth switch -u shivinate7\ngh pr view 3", "new_str": "gh pr view 3"},
         ("gh-login-switch", None))
    page("gh login switch: a str_replace that adds a gh line beside a gh line, with no switch, is refused",
         "str_replace", {"collection": "items", "doc_id": DOC, "field": "command",
                         "old_str": "gh pr view 3", "new_str": "gh pr view 3\ngh pr merge 3"},
         ("gh-login-switch", None))
    # An edit that names a shivinate7 repo on a gh line keeps no switch, so it is refused as its full text is.
    page("gh login switch: a str_replace that adds a -R shivinate7/ repo to a gh line is refused, as a full write is",
         "str_replace", {"collection": "items", "doc_id": DOC, "field": "command",
                         "old_str": "gh pr view 3", "new_str": "gh pr view 3 -R shivinate7/repo"},
         ("gh-login-switch", None))
    page("gh login switch: a full write of a gh line that names a shivinate7/ repo with no switch is refused",
         "set", entry_of(gh_task("gh pr view 3 -R shivinate7/repo", "gh pr view 3 -R shivinate7/repo")),
         ("gh-login-switch", None))

# ------------------------------------------------------------------ a step's span or fence holds a shell line only as a command

def case_command_in_item_spans():
    # A span or fence is a shell line when it chains with an operator and starts with a program or cmdlet
    # (question_form._shell_line). Text with an operator, a lone quote and a comment opener are no command,
    # and must not hide a real command after them in the same step.
    for name, steps, want in (
            ("a regex in a span is no shell line", ["Search for `foo|bar` in the page"], None),
            ("a span with a semicolon that starts with no program is no shell line",
             ["Read the `title; subtitle` line on the page"], None),
            ("a lone quote in text before a regex span is no shell line", ["Don't search for `foo|bar` in the page"], None),
            ("a comment opener inside a span is text", ["Search for `// a | b` in the page"], None),
            ("a markdown table in a fence over several lines is no shell line",
             ["Check the table:\n```\n| lane | state |\n| N1 | done |\n```"], None),
            ("a git log pipe in a span is a shell line", ["Check the log with `git log | head`"],
             ("command-in-item", "shell line")),
            ("a Get-ChildItem pipe in a span is a shell line", ["Check the list with `Get-ChildItem | Select`"],
             ("command-in-item", "shell line")),
            ("a cd and semicolon line in a span is a shell line", ["Run `cd x; npm test`"],
             ("command-in-item", "shell line")),
            ("a lone quote before a git log pipe is a shell line", ["Don't run `git log | head` yet"],
             ("command-in-item", "shell line")),
            ("a comment opener span does not hide a git log pipe after it",
             ["Run `// note` then `git log | head`"], ("command-in-item", "shell line"))):
        page(name, "set", entry_of(task_item(steps)), want)
    # A span whose first word is no program in the list still holds a second command after an operator: the
    # reader must see past it. Each of these is refused on main.
    for span in ("grep -n x a.py | head", "find . -name x | xargs rm", "yarn install && yarn test",
                 "dir | findstr x", "get-process | sort", "env git log | head", "time git log | head",
                 "$(git log) | head", "cmd /c git log | head"):
        page("a step holding `%s` is refused as a shell line" % span, "set",
             entry_of(task_item(["Check the output of `%s`" % span])), ("command-in-item", "shell line"))
    page("a fence holding grep x a | head is refused as a shell line", "set",
         entry_of(task_item(["Check the output:\n```\ngrep x a | head\n```"])), ("command-in-item", "shell line"))


# ------------------------------------------------------------------ a span an edit verb quotes is text, not a shell line

def span_scope(name, text, body):
    """The scope a quoted-span case judges (P7): `text` holds exactly one unfenced span, `body`. Without it a pass
    could come from a step with no span at all."""
    spans = call("_code_spans", text)
    got = [(b, f) for _, b, f in spans] if isinstance(spans, list) else spans
    check("span scope: " + name, got == [(body, False)], "want one span %r, got %r" % (body, got))


def case_quoted_span_after_edit_verb():
    # An edit verb before a span, with no run verb in its sentence, quotes the span: the step finds or replaces
    # that line of a file, so the span-flag clause reads `scripts/x.py --y` as text (question_form._shell_line,
    # `quoted`). The same span after a run verb is a command. A listed program stays a shell line when quoted, and
    # so does a span whose sentence has both verbs: a run verb in the sentence wins (command_in_item_hit).
    span = "scripts/x.py --y"
    for verb in ("Find", "Locate", "Replace", "Swap", "Search for", "Look for", "Edit"):
        text = "%s the line `%s` in the page" % (verb, span)
        span_scope("%s quotes the span" % verb, text, span)
        page("an edit-verb step (%s) quoting `%s` passes" % (verb, span), "set", entry_of(task_item([text])), None)
    # Delete and remove are no edit verb here: a step that deletes a lane may run the span ("Delete the lane with
    # `merge --drop 5`"), so the span is read as a command. case_delete_remove_span_is_a_shell_line holds the wording.
    for verb in ("Delete", "Remove"):
        text = "%s the line `%s` in the page" % (verb, span)
        span_scope("%s holds the span" % verb, text, span)
        page("a %s step holding `%s` is refused as a shell line" % (verb.lower(), span), "set",
             entry_of(task_item([text])), ("command-in-item", "shell line"))
    text = "Run `%s` in the page" % span
    span_scope("run takes the same span", text, span)
    page("the same span after run is refused as a shell line", "set", entry_of(task_item([text])),
         ("command-in-item", "shell line"))
    text = "Find the line `git push origin x` in the page"
    span_scope("find quotes a listed program", text, "git push origin x")
    page("a quoted git push after find is still refused as a shell line", "set", entry_of(task_item([text])),
         ("command-in-item", "shell line"))
    text = "Find the line and run `%s` in the page" % span
    span_scope("find and run share one sentence", text, span)
    page("a sentence with both find and run refuses the span as a shell line", "set", entry_of(task_item([text])),
         ("command-in-item", "shell line"))


def case_delete_remove_span_is_a_shell_line():
    # "Delete the lane with `merge --drop 5`." runs that command, so the span is a shell line, as after a run verb.
    # "Find the lane with the same span" quotes it and passes: the verb alone decides. Delete and remove are not edit
    # verbs (question_form.SPAN_EDIT_VERB), so the span is never quoted after them.
    span = "merge --drop 5"
    for text in ("Delete the lane with `%s`." % span, "Remove the lane: `%s`" % span):
        span_scope("delete or remove holds the span: %s" % text, text, span)
        page("a step that says `%s` is refused as a shell line" % text, "set", entry_of(task_item([text])),
             ("command-in-item", "shell line"))
    text = "Find the lane with `%s`." % span
    span_scope("find holds the same span", text, span)
    page("a find step quoting `%s` passes" % span, "set", entry_of(task_item([text])), None)


def case_quoted_span_run_after_is_refused():
    # A run verb after an edit-verb span, in the same sentence, makes the span a command: "Find `x` and run it" runs
    # it. The run verb is read after the span up to the sentence break (question_form.SPAN_RUN_AFTER). The control has
    # no run verb after the span, so the span stays quoted text and passes; the two differ only in that run verb.
    span = "scripts/x.py --y"
    text = "Find `%s` in the page" % span
    span_scope("find quotes the span with no run after it", text, span)
    page("an edit-verb step quoting `%s` with no run after passes" % span, "set", entry_of(task_item([text])), None)
    text = "Find `%s` and run it" % span
    span_scope("find, then run after the span", text, span)
    page("a step that finds `scripts/x.py --y` and runs it after the span is refused", "set",
         entry_of(task_item([text])), ("command-in-item", "shell line"))


# ------------------------------------------------------------------ a PowerShell string and a step's shell span

def ps_task(ps, mac="git log -1"):
    """A task whose command is {powershell: ps, mac}, with no gh in either, so only the bash-operator check judges it."""
    return task_item(["Open PowerShell", "Paste the command below and run it"], command={"powershell": ps, "mac": mac})


def case_powershell_bash_forms():
    # A bash form in a PowerShell command is refused: PS_BASH_OPERATOR reads only &&, ||, <<, /dev/null and export,
    # and PS_BASH_FORMS reads the rest with strings and comments blanked. Each bash form is refused, and its
    # PowerShell twin passes. The traps
    # are PowerShell text that looks like a bash form: a cast, a regex escape, a pipe in a string or a comment, and a
    # backslash path that ends a line.
    for name, ps in (("a pipe to head", "git log | head -5"), ("a pipe to grep", "git log --oneline | grep -i fix"),
                     ("a leading NAME=value", "FOO=1 git push"),
                     ("a bracket test", "if [ -f x ]; then git push; fi"),
                     ("a backslash line end", "git push origin \\\nmain"),
                     ("a pipe to jq", "Get-Content x | jq ."), ("a pipe to less", "Get-Content x | less"),
                     ("a double-bracket test", "if [[ -f x ]]; then git push; fi"),
                     ("a pipe to tail", "Get-Content x | tail -5"), ("a pipe to xargs", "Get-ChildItem | xargs rm"),
                     ("a pipe to sed", "git log | sed 1d"), ("a pipe to awk", "git log | awk 1"),
                     ("a pipe to cut", "git log | cut -c1-7"), ("a pipe to wc", "git log | wc -l"),
                     ("a pipe to uniq", "git log --oneline | uniq"), ("a pipe to tr", "git log | tr a b"),
                     ("a pipe to tac", "git log | tac"),
                     ("a while bracket test", "while [ -f x ]; do git push; done"),
                     ("an until bracket test", "until [ -f x ]; do git push; done"),
                     ("an elif bracket test", "if false; then git push; elif [ -f x ]; then git push; fi"),
                     ("a bracket test after an open paren", "git push ( [ -f x ] )"),
                     ("a bracket test after a semicolon", "git status; [ -f x ]; git push"),
                     ("a bracket test at a line start", "[ -f x ]\nRun-It")):
        page("a PowerShell command with %s is refused as a bash operator" % name, "set",
             entry_of(ps_task(ps)), ("command-in-item", "bash operator"))
    # A backslash that ends the string, with no line after it, is a path or an argument: each passes.
    for name, ps in (("cd to a backslash", "cd \\"), ("Set-Location to a backslash", "Set-Location \\"),
                     ("dir of a backslash", "dir \\")):
        page("a PowerShell command, %s, passes" % name, "set", entry_of(ps_task(ps)), None)
    # A backslash with a line after it is a continuation, and refuses.
    page("a PowerShell dir with a continuation backslash and a line after it is refused as a bash operator", "set",
         entry_of(ps_task("dir \\\n-Force")), ("command-in-item", "bash operator"))
    # A lone backslash argument is the drive root, a path, so a line that names a tool after it is no continuation.
    page("a PowerShell cd to a lone backslash, then a line that names a tool, passes", "set",
         entry_of(ps_task("cd \\\ntool x")), None)
    # A backslash glued to a word (origin\) is a path end, not a continuation, so it passes.
    page("a PowerShell push with origin\\ then a line, the backslash glued to a word, passes", "set",
         entry_of(ps_task("git push origin\\\nmain")), None)
    for name, ps in (("a Select-Object pipe", "Get-ChildItem | Select-Object -First 5"),
                     ("a PowerShell variable assignment", '$env:FOO = "1"; git push'),
                     ("a PowerShell if test", "if (Test-Path x) { git push }"),
                     ("a backtick line continuation", "git push origin `\nmain")):
        page("a PowerShell twin with %s passes" % name, "set", entry_of(ps_task(ps)), None)
    # A `[ ... ]` with spaces is a test only at a line start, after `;` or `(`, or after `if`, `elif`, `while` or
    # `until`, so an index with a space after a variable passes. A pipe to a cmdlet whose name starts with a listed
    # name, such as Trace-Command for `tr`, passes: a listed name must end at a word edge.
    for name, ps in (("a backslash path that ends a line", "Set-Location C:\\repo\\\ngit push origin main"),
                     ("a cast and a regex escape", "[int]$n = 5; if ('a[b' -match '\\[') { git push }"),
                     ("a pipe inside a string", 'Write-Host "a | head"'),
                     ("a pipe after a comment opener", "git log # | head"),
                     ("a here-string holding a pipe", "@'\n| head\n'@"),
                     ("a pipe to Trace-Command, named like tr", "Get-Date | Trace-Command"),
                     ("an index with a space in brackets after a variable", "Write-Output $names[ 0 ]")):
        page("a PowerShell trap, %s, passes" % name, "set", entry_of(ps_task(ps)), None)


def case_command_refusal_names_the_bash_forms():
    # A PowerShell command with a bash-only form is refused by command-in-item, and the reason a refused Claude reads
    # (PAGE_REASONS) names that form, so Claude sees its own form in the printed list. Each form is refused first (the
    # scope), then its reason is read for its fragment.
    for form, ps, fragment, named in (
            ("a pipe to head", "git log | head -5", r"\bpipe\b.*\bhead\b|\|\s*head\b",
             "a pipe to a Unix tool, such as head"),
            ("a leading NAME=value", "FOO=1 git push", r"\w+=value\b", "a NAME=value prefix"),
            ("a bracket test", "if [ -f x ]; then git push; fi", r"bracket|\[\s*\]|\[\[", "a bracket test"),
            ("a backslash line end", "git push origin \\\nmain", r"backslash", "a backslash line end")):
        got = call("item_hit", "set", entry_of(ps_task(ps)))
        refused = isinstance(got, tuple) and got[0] == "command-in-item"
        check("%s is refused by command-in-item, the rule whose reason is checked" % form, refused,
              "got %r" % (got,))
        reason = question_form.PAGE_REASONS.get(got[0], "") if refused else ""
        check("the reason a refused Claude reads names %s" % named,
              re.search(fragment, reason, re.I) is not None, "reason %r" % reason)


def case_powershell_hashtable_is_no_bash_form():
    # PS_BASH_FORMS ends a NAME=value value at a `;`, so a hashtable's second pair is no `NAME=value tool` line.
    # A hashtable with `;` between its pairs passes. A leading NAME=value before a command is refused, and so is
    # one after a `;`.
    for name, ps in (("a hashtable of three pairs", "$h = @{a=1; b=2; c=3}"),
                     ("a hashtable of two named pairs", "$o = @{Name='x'; Value=2}")):
        page("a PowerShell %s passes" % name, "set", entry_of(ps_task(ps)), None)
    # A scriptblock value (`E={ ... }`) holds statements, and its `}` closes the value, not the hashtable's. So a `{`
    # and a letter after `NAME=` is a scriptblock, not a `NAME=value tool` line. `E={ $_.Name }` is the control: a `$`
    # after the brace is no command word, and it passes already.
    for name, ps in (("a PowerShell calculated property whose scriptblock calls a cmdlet",
                      "Get-Process | Select-Object @{N='x'; E={ Get-Date }}"),
                     ("a PowerShell calculated property whose scriptblock is an if statement",
                      "@{L='Size'; E={ if ($_.Length -gt 1) { 1 } else { 2 } }}"),
                     ("a PowerShell hashtable whose second value is a scriptblock with a command", "@{a=1; b={ foo }}"),
                     ("a PowerShell calculated property whose scriptblock reads a property (control)",
                      "Get-Process | Select-Object @{N='x'; E={ $_.Name }}")):
        page("%s passes: %s" % (name, ps), "set", entry_of(ps_task(ps)), None)
    for ps in ("FOO=1 tool run", "tool run;FOO=1 tool run"):
        page("a PowerShell command %s is refused as a bash operator" % ps, "set",
             entry_of(ps_task(ps)), ("command-in-item", "bash operator"))


def case_powershell_comment_quote_ends_at_its_line():
    # The quote walk ends a `#` line comment at its newline, so a quote in the comment opens nothing past its line,
    # and the next line is read as it stands. A contraction in a comment is text too, and a comment opener inside a
    # string opens no comment.
    refused = ("command-in-item", "bash operator")
    page("a PowerShell comment with an unpaired single quote, then a pipe to head on the next line, is refused",
         "set", entry_of(ps_task("# the 'main branch\ngit log | head -5")), refused)
    page("a PowerShell comment with an unpaired double quote, then a pipe to head on the next line, is refused",
         "set", entry_of(ps_task('# the "main branch\ngit log | head -5')), refused)
    page("a PowerShell comment with a contraction, then Get-ChildItem, passes", "set",
         entry_of(ps_task("# it's fine\nGet-ChildItem")), None)
    page("a PowerShell block comment with a contraction, then a pipe to head, is refused", "set",
         entry_of(ps_task("<# it's #>\ngit log | head -5")), refused)
    page("a PowerShell string holding a comment opener, then a pipe to head on the next line, is refused", "set",
         entry_of(ps_task('Write-Host "# ok"\ngit log | head -5')), refused)


def case_powershell_bash_prefix_braced_expansion():
    # A NAME=value prefix holding a braced expansion in its value (`${PORT:-8080}`, `${HOME}/bin`) is a bash form,
    # so each is refused. A `$` inside the expansion and one nested expansion are refused too. The hashtable controls
    # pass: their `}` closes the hashtable, not an expansion.
    refused = ("command-in-item", "bash operator")
    page("a PowerShell command, PORT=${PORT:-8080} node server.js, is refused as a bash operator", "set",
         entry_of(ps_task("PORT=${PORT:-8080} node server.js")), refused)
    page("a PowerShell command, X=${HOME}/bin tool run, is refused as a bash operator", "set",
         entry_of(ps_task("X=${HOME}/bin tool run")), refused)
    page("a PowerShell command, PORT=${PORT:-$DEFAULT} node server.js, is refused as a bash operator", "set",
         entry_of(ps_task("PORT=${PORT:-$DEFAULT} node server.js")), refused)
    page("a PowerShell command, PORT=${A:-${B}} node server.js, is refused as a bash operator", "set",
         entry_of(ps_task("PORT=${A:-${B}} node server.js")), refused)
    for name, ps in (("a hashtable of three pairs", "@{a=1; b=2; c=3}"),
                     ("a hashtable with no space after its first semicolon", "@{a=1;b=2 }"),
                     ("a hashtable with a double-quoted underscore name", '@{Name="_"; Value=2}')):
        page("a PowerShell %s passes" % name, "set", entry_of(ps_task(ps)), None)


def case_powershell_hash_mid_token_is_no_comment():
    # A `#` opens a line comment only at a token start (guard_core.token_start), so a `#` inside a word is text, and
    # the bash form after it on the same line is read. The next-line and here-string pins hold the refusal too.
    # Neither depends on that condition: a line comment ends at its newline, and a here-string body is quoted text.
    refused = ("command-in-item", "bash operator")
    page("a PowerShell command, a#b | head, is refused: a # inside a word opens no comment", "set",
         entry_of(ps_task("a#b | head")), refused)
    page("a PowerShell command, https://x/#frag | head, is refused: a # inside a word opens no comment", "set",
         entry_of(ps_task("https://x/#frag | head")), refused)
    page("a PowerShell command, $x#y | head, is refused: a # inside a word opens no comment", "set",
         entry_of(ps_task("$x#y | head")), refused)
    page("a PowerShell command, $x#y then | head on the next line, is refused", "set",
         entry_of(ps_task("$x#y\n| head")), refused)
    page("a PowerShell here-string holding # x 'y, then git log | head on a later line, is refused", "set",
         entry_of(ps_task("$h = @'\n# x 'y\n'@\ngit log | head -5")), refused)


def case_step_shell_programs_partial():
    # A single-span step is a shell line when its first word is in SHELL_PROGRAMS (a cloud CLI included), or a
    # lowercase word whose second word is a flag (chmod +x f, rg --files). Each span below is refused. Controls pass:
    # a bare tool name, a flag alone and a minus between two words. The chained span stays refused, as on main.
    for span in ("gsutil ls", "yarn install", "kubectl get pods", "terraform plan", "chmod +x f", "grep -r x",
                 "pnpm install", "aws s3 ls", "az login", "helm list", "rg --files", "sync --dry-run"):
        page("a step holding `%s` is refused as a shell line" % span, "set",
             entry_of(task_item(["Check the output of `%s`" % span])), ("command-in-item", "shell line"))
    for span in ("kubectl", "--force", "a - b"):
        page("a step holding `%s` alone is text and passes" % span, "set",
             entry_of(task_item(["Check the output of `%s`" % span])), None)
    page("a fence holding a chained terraform plan with a pipe stays a shell line", "set",
         entry_of(task_item(["Check the output:\n```\nterraform plan | tee plan.txt\n```"])),
         ("command-in-item", "shell line"))
    # A program at a path is judged by its bare name, as `chmod` is alone: the word after the directory is the program.
    page("a step holding `/usr/bin/chmod +x f` is refused as a shell line", "set",
         entry_of(task_item(["Check the output of `/usr/bin/chmod +x f`"])), ("command-in-item", "shell line"))


# ------------------------------------------------------------------ a question says how it departs from main
#
# Rule question-departs: a question is asked only when the work departs from main. A line that restates
# main names no departure, so it is refused. Judged after the form passes, on the chat box (each question
# with 2+ options, in `question`) and on a page decision (set, or an update that carries context, in `context`).

# A line that restates main: its change side says there is no change. Each is refused.
RESTATES = [
    "Departs from: agent-model-cap — Opus above the row stays the existing ask",
    "Departs from: lint/stamp.py:run_stamp — none",
    "Departs from: lint/stamp.py:run_stamp — n/a",
    "Departs from: lint/stamp.py:run_stamp — No change.",
    "Departs from: lint/stamp.py:run_stamp - unchanged",
    "Departs from: lint/stamp.py:run_stamp — as today",
    "Departs from: lint/stamp.py:run_stamp — as on main",
    "Departs from: lint/stamp.py:run_stamp — same as main",
    "Departs from: lint/stamp.py:run_stamp — nothing changes",
    "Departs from: lint/stamp.py:run_stamp — keeps the lint job",
    "Departs from: lint/stamp.py:run_stamp — STAYS in the lint job",
    "Departs from: lint/stamp.py:run_stamp — already in the lint job",
]
# A line with an empty side, no separator, or nothing after the colon. Each is refused.
MALFORMED = [
    "Departs from:",
    "Departs from:   ",
    "Departs from: lint/stamp.py:run_stamp —",
    "Departs from: lint/stamp.py:run_stamp - ",
    "Departs from: — the stamp check moves to the lint job",
    "Departs from: lint/stamp.py:run_stamp",
]
# Valid lines: both sides non-empty, the change side a change. The word match is whole words only.
VALID_LINES = [
    DEPARTS,
    # A new thing writes "main — adds <X>" (decision port-keeps-behaviour, question-departs section).
    "Departs from: main — adds a retry button",
    "Departs from: lint/stamp.py:run_stamp - the stamp check moves to the lint job",
    "Departs from: agent-model-cap — Opus above the row needs an owner grant",
    "Departs from: lint/stamp.py:run_stamp — nonetheless the stamp moves to the lint job",
    # Comment openers and a lone quote are plain text in the change side.
    "Departs from: lint/stamp.py:run_stamp — don't parse // or /* or # here, the stamp moves",
]
DEPARTS_REFUSAL = (DEPARTS_RULE, "Departs")


def dp_chat(name, body, want):
    chat(name, chat_box(departs=body), want)


def dp_page(name, body, want):
    page(name, "set", entry_of(page_item(departs=body)), want)


def case_departs_missing():
    dp_chat("no Departs from line in the question is refused as question-departs", None, DEPARTS_REFUSAL)
    dp_page("a decision with no Departs from line is refused as question-departs", None, DEPARTS_REFUSAL)
    page("an update that carries kind decision and a context with no Departs from line is refused", "update",
         entry_of({"kind": "decision", "context": form_text(departs=None)}), DEPARTS_REFUSAL)
    page("an update that carries kind decision and a context with the line passes", "update",
         entry_of({"kind": "decision", "context": form_text()}), None)
    options = tcj.good_options()
    options[0]["description"] += " " + DEPARTS
    chat("a Departs from line in an option's description, not the question, is refused",
         chat_box(options=options, departs=None), DEPARTS_REFUSAL)


def case_departs_empty_or_malformed():
    for body in MALFORMED:
        dp_chat("a line %r is refused as question-departs" % body, body, DEPARTS_REFUSAL)
        dp_page("a page line %r is refused as question-departs" % body, body, DEPARTS_REFUSAL)


def case_departs_restates_main():
    for body in RESTATES:
        dp_chat("a line %r that restates main is refused" % body, body, DEPARTS_REFUSAL)
        dp_page("a page line %r that restates main is refused" % body, body, DEPARTS_REFUSAL)


def case_departs_valid_passes():
    for body in VALID_LINES:
        dp_chat("a valid line %r passes" % body, body, None)
        dp_page("a valid page line %r passes" % body, body, None)
    mid = "Why: " + DEPARTS
    dp_chat("a Departs from phrase after other text on the line does not count", mid, DEPARTS_REFUSAL)
    dp_page("a Departs from phrase after other text on the line does not count", mid, DEPARTS_REFUSAL)


def case_departs_out_of_scope_passes():
    one = tcj.good_box(departs=None)
    one["questions"][0].update(question="Ship it?", options=[{"label": "Yes", "description": "go"}])
    chat("a one-option question with no Departs from line passes", one, None)
    task = {"n": 928, "kind": "task", "title": "Merge the batch", "status": "open", "steps": ["Open Terminal"],
            "context": "Why yours: a session on your computer was asked first and none could reach the remote"}
    page("a task with a Why yours line and no Departs from line passes", "set", entry_of(task), None)
    page("a closed decision with no form lines and no Departs from line passes", "set",
         entry_of(dict(ITEM92, status="closed", context="Answer from chat, 10:42: keep the check in the lint job.")),
         None)
    page("a note with form lines and no Departs from line passes", "set",
         entry_of(page_item(departs=None, kind="note")), None)
    page("an update of the status only passes", "update", entry_of({"status": "closed"}), None)


def context_replace(name, old, new, want):
    """One str_replace on a page item's `context`, judged by item_hit and by the guard."""
    page("a str_replace " + name, "str_replace",
         {"collection": "items", "doc_id": DOC, "field": "context", "old_str": old, "new_str": new}, want)


def case_departs_str_replace():
    context_replace("that drops the Departs from line from context is refused", DEPARTS, "", DEPARTS_REFUSAL)
    context_replace("that drops the line and keeps the form is refused", form_text(), form_text(departs=None),
                    DEPARTS_REFUSAL)
    context_replace("that swaps the line for another valid line is allowed", DEPARTS,
                    "Departs from: lint/stamp.py:run_stamp — the stamp check moves to the test job", None)
    context_replace("whose old_str holds no Departs from line is allowed", "The lane merge-role-allow would do it.",
                    "The lane would do it.", None)
    context_replace("that keeps the line and changes the prose is allowed", form_text(),
                    form_text() + "\nChanged prose.", None)


def case_departs_ids_and_order():
    # The older rules and the form keep their ids: the question-departs check runs after them.
    wide = [dict(tcj.good_options()[0], label="Allow the second form (Recommended)",
                 description="Gain: it lands today. Lose: two forms stay. " + WIDE + "."),
            tcj.good_options()[1]]
    chat("a widening recommended option with no Departs from line is refused as uniform-pick",
         chat_box(options=wide, departs=None), ("uniform-pick", None))
    options = tcj.good_options()
    options[1] = {"label": "Hold it", "description": "Lose: the change lands a day later."}
    chat("a box with no Departs from line and an option with no gain is refused as question-form",
         chat_box(options=options, departs=None), (FORM_RULE, "gain"))
    page("a decision with no Goal and no Departs from line is refused as question-form", "set",
         entry_of(page_item(goal=None, departs=None)), (FORM_RULE, "Goal"))
    page("a port with no Departs from line keeps the port-question id", "set",
         entry_of(page_item(port=True, departs=None)), ("port-question", None))


def case_departs_reasons():
    for surface, table in (("chat", getattr(question_form, "CHAT_REASONS", None)),
                           ("page", getattr(question_form, "PAGE_REASONS", None))):
        text = (table or {}).get(DEPARTS_RULE)
        check("question departs: the %s reasons table holds a question-departs reason" % surface,
              isinstance(text, str) and "Departs from" in text, MISSING if table is None else sorted(table))
        if isinstance(text, str):
            named = [word for word in PAGE_ONLY if word in text] if surface == "chat" else []
            check("question departs: the %s reason names its line and no field the chat box lacks" % surface,
                  not named, named)


# A no-change word in the change side refuses when it comes before the first ";", or anywhere when the side
# has no ";". A word after the ";" names what the change does: "keeps its timeout" and "already loads" are changes.
REFUSED_NO_CHANGE = [
    "Departs from: main — stays the existing ask",
    "Departs from: x.py:f — keeps today's behaviour",
    "Departs from: x — already does this",
    "Departs from: x — none",
    "Departs from: x — same as main",
    "Departs from: x — as before",
    "Departs from: x — no difference",
    "Departs from: x — identical to main",
    "Departs from: x — the phone app stays on the list when offline",
]
PASS_AFTER_SEMICOLON = [
    "Departs from: x.py:f — adds a retry; the old call keeps its timeout",
    "Departs from: x — moves the list; it already loads from cache",
]
PASS_NO_NO_CHANGE_WORD = [
    "Departs from: x — the phone app shows the list when offline",
]
# The template copied verbatim, with an angle-bracket placeholder on either side. Each is refused.
PLACEHOLDERS = [
    "Departs from: <what on main> — <what changes>",
    "Departs from: x — <what changes>",
    "Departs from: <what on main> — adds y",
]
# Line forms that a Departs from line may take: a bullet, a bold label, a star bullet, a double hyphen
# as the separator, and an em dash with no spaces. Each passes.
LINE_FORMS = [
    "- Departs from: x — adds y",
    "**Departs from:** x — adds y",
    "* Departs from: x — adds y",
    "Departs from: x -- adds y",
    "Departs from: x—adds y",
]


def case_departs_no_change_word_before_the_semicolon():
    for body in REFUSED_NO_CHANGE:
        dp_chat("a no-change word before the first ';' is refused: %r" % body, body, DEPARTS_REFUSAL)
        dp_page("a page no-change word before the first ';' is refused: %r" % body, body, DEPARTS_REFUSAL)
    for body in PASS_AFTER_SEMICOLON + PASS_NO_NO_CHANGE_WORD:
        dp_chat("a change side with no no-change word before the first ';' passes: %r" % body, body, None)
        dp_page("a page change side with no no-change word before the first ';' passes: %r" % body, body, None)


def case_departs_placeholders_are_refused():
    for body in PLACEHOLDERS:
        dp_chat("a template placeholder %r is refused as question-departs" % body, body, DEPARTS_REFUSAL)
        dp_page("a page template placeholder %r is refused as question-departs" % body, body, DEPARTS_REFUSAL)


def case_departs_line_forms_pass():
    for body in LINE_FORMS:
        dp_chat("a line form %r passes" % body, body, None)
        dp_page("a page line form %r passes" % body, body, None)
    # CRLF line endings: the same form lines, joined with CR LF. The line's \r is no part of either side.
    crlf = "\r\n".join(line for line in (GOAL, PROBLEM, *BASED, DEPARTS, WAITING) if line)
    box = chat_box()
    box["questions"][0]["question"] = crlf
    chat("a question with CRLF line endings and a valid Departs from line passes", box, None)
    page("a decision with CRLF line endings and a valid Departs from line passes", "set",
         entry_of(tcj.with_frozen_fields(dict(ITEM92, context=crlf))), None)


def case_departs_str_replace_forms():
    context_replace("that swaps a bold Departs from line for one whose change says keeps before any ';' is refused",
                    "**Departs from:** x — adds X", "**Departs from:** x — keeps X", DEPARTS_REFUSAL)
    context_replace("that swaps a plain Departs from line for one whose change says keeps before any ';' is refused",
                    "Departs from: x — adds X", "Departs from: x — keeps X", DEPARTS_REFUSAL)
    context_replace("that swaps a plain Departs from line for a valid one with keeps later in the change is allowed",
                    "Departs from: x — adds X", "Departs from: x — adds X; the old call keeps its timeout", None)


# ------------------------------------------------------------------ a port's main side

def case_port_main_side():
    # A port item whose line says no change is refused by question-departs, which runs on every question.
    # The port rule is not the one that refuses it, so the case takes either id.
    page("a port item whose line says main — nothing is refused", "set",
         entry_of(page_item(port=True, departs="Departs from: main — nothing")),
         (("port-question", DEPARTS_RULE), "Departs"))


# The port shapes of the round-2 review. A backticked or aliased main side names file:symbol and passes. A
# placeholder or no-change change side is refused on a port page, a port task and a question box.
PORT_OK_LINES = [
    "Departs from: `hooks/guard.py:data_tool_hit` — adds a retry",
    "Departs from: app/[id]/page.tsx:Home — adds a retry",
    "Departs from: @/components/x.tsx:Button — adds a retry",
]
PORT_BAD_LINES = [
    "Departs from: main — adds <X>",
    "Departs from: hooks/guard.py:x — <what changes>",
    "Departs from: hooks/guard.py:x — none",
]


def port_task(departs):
    """A port task with a Why yours line, so only the port and departs checks can refuse it."""
    return {"n": 928, "kind": "task", "port": True, "title": "Merge the batch", "status": "open",
            "context": "Why yours: a session on your computer was asked first and none could reach the remote\n"
                       + departs}


def case_port_departs_shapes():
    for body in PORT_OK_LINES:
        page("a port page item whose line is %r passes" % body, "set",
             entry_of(page_item(port=True, departs=body)), None)
        page("a port task whose line is %r passes" % body, "set", entry_of(port_task(body)), None)
    for body in PORT_BAD_LINES:
        page("a port page item whose line is %r is refused" % body, "set",
             entry_of(page_item(port=True, departs=body)), (("port-question", DEPARTS_RULE), "Departs"))
        page("a port task whose line is %r is refused" % body, "set", entry_of(port_task(body)),
             ("port-question", None))
        chat("a question whose line is %r is refused" % body, chat_box(departs=body), (DEPARTS_RULE, "Departs"))


# ------------------------------------------------------------------ call_judge

def case_call_judge():
    bad = tcj.good_box(problem=None)
    r = tcj.run_hook(tcj.question_input(box=bad), answer=tcj.ALLOW)
    d = r.deny() or {}
    check("call_judge: a box with no Problem line is refused, though the model would answer ok",
          r.code == 0 and d.get("permissionDecision") == "deny" and FORM_RULE in r.reason(), tcj.detail(r))
    check("call_judge: the code refusal makes no model call", r.calls == [], tcj.detail(r))
    check("call_judge: the refusal names the Problem line and logs one question-form deny line",
          "problem" in r.reason().lower() and r.log.count("\tdeny\t%s\t" % FORM_RULE) == 1, tcj.detail(r))
    override = tcj.override
    check("call_judge: the code refusal ends with the override line",
          override is not None and hasattr(override, "offer")
          and r.reason().rstrip().endswith(override.offer(FORM_RULE).strip()), r.reason()[-160:])
    r = tcj.run_hook(tcj.question_input(box=bad), answer=tcj.ALLOW, model_fail=True)
    check("call_judge: a model failure does not hide the code refusal",
          r.code == 0 and (r.deny() or {}).get("permissionDecision") == "deny" and r.calls == [], tcj.detail(r))
    r = tcj.run_hook(tcj.question_input(box=bad), answer=tcj.ALLOW, pass_=(tcj.SID_A, tcj.TIMED))
    check("call_judge: a timed override lifts the code refusal",
          r.code == 0 and lift_line.names_lift(r.out.strip(), FORM_RULE) and tcj.lifted_log(r, FORM_RULE),
          tcj.detail(r))
    options = tcj.good_options()
    options[0] = {"label": "Allow the second form (Recommended)",
                  "description": "Gain: it lands today. Lose: two forms stay. " + WIDE + "."}
    r = tcj.run_hook(tcj.question_input(box=tcj.good_box(options=options)), answer=tcj.ALLOW)
    check("call_judge: a Recommended option that goes against the uniform ruling is refused as uniform-pick",
          r.code == 0 and "uniform-pick" in r.reason() and r.log.count("\tdeny\tuniform-pick\t") == 1
          and r.calls == [], tcj.detail(r))
    r = tcj.run_hook(tcj.question_input(), answer=tcj.ALLOW)
    check("call_judge: a good box is not refused by code and reaches the model once",
          r.code == 0 and r.out == "" and len(r.calls) == 1 and "\tdeny\t" not in r.log, tcj.detail(r))
    one = tcj.good_box()
    one["questions"][0].update(question="Ship it?", options=[{"label": "Yes", "description": "go"}])
    r = tcj.run_hook(tcj.question_input(box=one), answer=tcj.ALLOW)
    check("call_judge: a one-option question with no form lines is not refused",
          r.code == 0 and r.out == "" and "\tdeny\t" not in r.log, tcj.detail(r))


def case_widens_text_is_the_set_words():
    got = getattr(question_form, "WIDENS_TEXT", None)
    check("widens: question_form.WIDENS_TEXT is the owner's exact words", got == WIDENS_WORDS, got)


def case_widens_reasons_carry_no_topic_id():
    # A refusal names the rule's words, never the owner's topic id: a bare id reads as a bare id on the card.
    for name in ("WIDENS_REASON", "CHAT_WIDENS_REASON"):
        text = getattr(question_form, name, None)
        if text is None:
            check("widens reasons: question_form.%s is there" % name, False, MISSING)
            continue
        check("widens reasons: question_form.%s carries no t18" % name, "t18" not in text, text)


def case_widens_words_in_every_home():
    # Each file holds the words, collapsed over line wraps, and no longer holds the old card text.
    for rel in WIDENS_HOMES:
        with open(os.path.join(REPO, rel), encoding="utf-8") as f:
            text = re.sub(r"\s+", " ", f.read())
        check("widens homes: %s carries question_form.WIDENS_TEXT" % rel, WIDE in text, WIDE)
        check("widens homes: %s carries no %r" % (rel, OLD_WIDENS_CARD), OLD_WIDENS_CARD not in text,
              OLD_WIDENS_CARD)


def case_widens_words_in_the_reply_judge_prompt():
    # The reply judge's prompt is built from reply_judge.INSTRUCTIONS: it holds the words and no topic id.
    text = re.sub(r"\s+", " ", reply_judge.INSTRUCTIONS)
    check("widens prompt: reply_judge.INSTRUCTIONS carries question_form.WIDENS_TEXT", WIDE in text, WIDE)
    check("widens prompt: reply_judge.INSTRUCTIONS carries no 't18'", "t18" not in text, "t18")


# ------------------------------------------------------------------ past rulings and option keys (units)
#
# question_form.past_rulings(text, root) -> (candidates, unknown), and question_form.key_overlap(reply, earlier) (spec
# past-rulings, and the option-keys section). The spec does not fix the return shapes, so a check reads a marker in
# str(...) and a refusal by truthiness. A missing function fails its check by name.
def _cap_word(i):
    return "word" + chr(97 + i // 26) + chr(97 + i % 26)


CAP_WORDS = [_cap_word(i) for i in range(40)]
CAP_QUESTION = "Goal: " + " ".join(CAP_WORDS)
KEY_SAME = "> **Input Needed** Two questions.\n> a) keep the apps\n> b) remove the apps\n> a) about 2x\n> b) under 80%"
KEY_DISTINCT = ("> **Input Needed** Two questions.\n> 1a) keep the apps\n> 1b) remove the apps\n"
                "> 2a) about 2x\n> 2b) under 80%")
KEY_NOW = "> **Input Needed** Keep the caps?\n> a) about 2x\n> b) under 80%"
KEY_EARLIER = "> **Input Needed** Keep the apps?\n> a) keep\n> b) remove"


def case_past_rulings_caps_and_ranks():
    import question_form  # the one form check (hooks/question_form.py)
    fn = getattr(question_form, "past_rulings", None)
    check("past rulings: question_form.past_rulings exists", callable(fn), "missing function")
    if not callable(fn):
        return
    steps = {"s%02d" % i: "Ruling (owner): STEP%02d %s" % (i, " ".join(CAP_WORDS[:i])) for i in range(40)}
    steps["noise"] = "STEPNOISE %s" % " ".join(CAP_WORDS)  # no Ruling, owner or shiv, so never a candidate
    repo = tcj.make_repo("past-cap", steps=steps)
    candidates, unknown = fn(CAP_QUESTION, repo)
    text = str(candidates)
    kept = [i for i in range(40) if ("STEP%02d" % i) in text]
    check("past rulings: at most 30 step sentences, the 30 with the most overlap (ids 10 to 39)",
          kept == list(range(10, 40)) and "STEPNOISE" not in text, "kept %s" % kept[:5])
    check("past rulings: a repo with no decision folder names closed page items as unknown",
          "closed page items" in str(unknown), str(unknown)[:200])


def case_past_rulings_reads_debts():
    import question_form  # the one form check (hooks/question_form.py)
    fn = getattr(question_form, "past_rulings", None)
    check("past rulings debts: question_form.past_rulings exists", callable(fn), "missing function")
    if not callable(fn):
        return
    repo = tcj.make_repo("past-debts", decisions={tcj.APPS_SLUG: tcj.APPS_RULING},
                         steps={tcj.CI_STEP_ID: tcj.CI_STEP_SENTENCE},
                         debts={tcj.DEBT_SLUG: tcj.DEBT_WHAT})
    candidates, _ = fn(tcj.APPS_GOAL, repo)
    text = str(candidates)
    check("past rulings debts: a docs/debts record's slug and What line reach the candidates",
          tcj.DEBT_SLUG in text and tcj.DEBT_WHAT in text, text[:200])


def case_key_overlap():
    import question_form  # the one form check (hooks/question_form.py)
    fn = getattr(question_form, "key_overlap", None)
    check("key overlap: question_form.key_overlap exists", callable(fn), "missing function")
    if not callable(fn):
        return
    check("key overlap: the keys a and b of two questions in one reply refuse", bool(fn(KEY_SAME, [])),
          "a reply with two questions on a and b passed")
    check("key overlap: distinct keys 1a, 1b, 2a and 2b pass", not fn(KEY_DISTINCT, []),
          "distinct keys refused")
    check("key overlap: keys that overlap a question in an earlier assistant reply since the last human refuse",
          bool(fn(KEY_NOW, [KEY_EARLIER])), "an earlier overlap passed")
    check("key overlap: the same keys with no earlier reply since the last human pass", not fn(KEY_NOW, []),
          "a lone question refused")


RESEND_EARLIER = ("> **Input Needed** Should the GitHub apps keep their access to claude-settings?\n"
                  "> a) keep\n> b) remove")
RESEND_NOW = "> **Input Needed** Do the GitHub apps keep access to claude-settings?\n> a) keep\n> b) remove"
FACTS_NOW = "> **Input Needed** Which fix ships? The run touched the files.\n> - a: 3 files\n> - b: 5 files"


def case_key_overlap_resend_and_fact_lists():
    import question_form  # the one form check (hooks/question_form.py)
    fn = getattr(question_form, "key_overlap", None)
    check("key overlap: question_form.key_overlap exists", callable(fn), "missing function")
    if not callable(fn):
        return
    check("key overlap: a reworded re-send of one question does not clash with its earlier reply",
          not fn(RESEND_NOW, [RESEND_EARLIER]), "a re-send of one question was refused")
    check("key overlap: a - a: 3 files fact list does not clash with a question's keys",
          not fn(FACTS_NOW, [KEY_EARLIER]), "a fact list was refused")


KEY_SIMILAR = ("> **Input Needed** Two questions.\n> Keep access to claude-settings?\n> a) keep it\n> b) remove it\n"
               "> Keep access to other repos?\n> a) keep it on\n> b) turn it off")
KEY_SIMILAR_EARLIER = "> **Input Needed** Keep access to claude-settings?\n> a) keep it\n> b) remove it"
KEY_SIMILAR_NOW = "> **Input Needed** Keep access to other repos?\n> a) keep it on\n> b) turn it off"


def case_key_overlap_similar_questions_clash():
    import question_form  # the one form check (hooks/question_form.py)
    fn = getattr(question_form, "key_overlap", None)
    check("key overlap similar: question_form.key_overlap exists", callable(fn), "missing function")
    if not callable(fn):
        return
    check("key overlap similar: two similar questions, each a and b with different option text, clash in one reply",
          bool(fn(KEY_SIMILAR, [])), "two similar questions with a and b passed")
    check("key overlap similar: a similar question with a and b clashes with an earlier reply's a and b",
          bool(fn(KEY_SIMILAR_NOW, [KEY_SIMILAR_EARLIER])), "a similar question with a and b passed")


def case_past_rulings_skips_the_debt_notes_file():
    import question_form  # the one form check (hooks/question_form.py)
    fn = getattr(question_form, "past_rulings", None)
    check("past rulings notes: question_form.past_rulings exists", callable(fn), "missing function")
    if not callable(fn):
        return
    notes_mark = "notes-4b2c"
    repo = tcj.make_repo("past-notes-file", debts={"notes": "a note line, not a debt. Marker " + notes_mark + ".",
                                                   tcj.DEBT_SLUG: tcj.DEBT_WHAT})
    candidates, _ = fn(tcj.APPS_GOAL, repo)
    text = str(candidates)
    check("past rulings notes: a real debt record still reaches the candidates", tcj.DEBT_WHAT in text, text[:200])
    check("past rulings notes: docs/debts/notes.md is not a record and never reaches the candidates",
          notes_mark not in text, text[:200])


# ------------------------------------------------------------------ past rulings: owner sentences past the index cap
#
# A decision's `## The ruling` section is cut to question_form.INDEX_CAP characters in the judge's index, so an owner
# ruling sentence past the cap never reaches the judge. A record may add owner-ruling sentences past the cap, but never
# more than question_form.RULING_EXTRA_CAP characters of them, so the prompt does not grow for every record. Each case
# makes its own fixture decision in a fixture repo; the pointer is patched to that repo, so no real checkout is read.
# A case's candidate lines are the ones that start with its record id (`decisions/<slug>: `).
PAST_CAP_SLUG = "round-one-reviewers-haiku"
PAST_CAP_QUESTION = "round 1 first review stronger model guard or check change"
RULING_SENTENCE = "Round 1 reviewers run Haiku at xhigh on every change (owner ruling, 2026-11-17 19:45 CST)."
OWNER_SENTENCES = ["Owner ruling %02d: keep item %02d as it is." % (i, i) for i in range(60)]


def _filler(n_chars):
    """Plain sentences with no RULING_WORDS word (ruling, owner, shiv), at least n_chars long."""
    sentences, size = [], 0
    while size < n_chars:
        sentence = "Background sentence %03d: the review stack and its model pins stay as they are." % len(sentences)
        sentences.append(sentence)
        size += len(sentence) + 1
    return " ".join(sentences)


def _record_lines(candidates, record_id):
    """The candidate lines of one record, `<record id>: <text>`, in the order past_rulings gave them."""
    prefix = record_id + ": "
    return [str(c) for c in candidates if str(c).startswith(prefix)]


def _record_text(candidates, record_id):
    """The record's text: its candidate lines after the id, joined. The most a record adds is what this bounds."""
    prefix = record_id + ": "
    return " ".join(line[len(prefix):] for line in _record_lines(candidates, record_id))


def _past_cap_candidates(name, section, fn):
    """(record id, candidates) for one decision whose `## The ruling` section is `section`, from past_rulings."""
    repo = tcj.make_repo(name, decisions={PAST_CAP_SLUG: section})
    with mock.patch(POINTER_CHECKOUT, return_value=repo):
        candidates, _unknown = fn(PAST_CAP_QUESTION, repo)
    return "decisions/" + PAST_CAP_SLUG, candidates


def case_past_ruling_owner_sentence_past_the_cap_reaches_the_line():
    import question_form  # the one form check (hooks/question_form.py)
    fn = getattr(question_form, "past_rulings", None)
    check("past rulings past cap: question_form.past_rulings exists", callable(fn), "missing function")
    if not callable(fn):
        return
    section = _filler(1000) + " " + RULING_SENTENCE + " " + _filler(300)
    offset = section.index(RULING_SENTENCE)
    check("past rulings past cap: the fixture puts the owner sentence past INDEX_CAP and past character 1000",
          offset > question_form.INDEX_CAP and offset >= 1000, "offset %d" % offset)
    record_id, candidates = _past_cap_candidates("past-owner-past-cap", section, fn)
    lines = _record_lines(candidates, record_id)
    check("past rulings past cap: the decision record is a candidate (scope)", bool(lines), str(candidates)[:200])
    if not lines:
        return
    check("past rulings past cap: a candidate line for the record carries Haiku at xhigh and 2026-11-17 19:45",
          any("Haiku at xhigh" in line and "2026-11-17 19:45" in line for line in lines),
          "line ends: ..." + lines[0][-160:])


def case_past_ruling_owner_sentence_inside_the_cap_reaches_the_line():
    import question_form  # the one form check (hooks/question_form.py)
    fn = getattr(question_form, "past_rulings", None)
    check("past rulings inside cap: question_form.past_rulings exists", callable(fn), "missing function")
    if not callable(fn):
        return
    section = RULING_SENTENCE + " " + _filler(1500)
    check("past rulings inside cap: the fixture puts the owner sentence inside INDEX_CAP",
          section.index(RULING_SENTENCE) + len(RULING_SENTENCE) <= question_form.INDEX_CAP,
          "sentence ends at %d" % (section.index(RULING_SENTENCE) + len(RULING_SENTENCE)))
    record_id, candidates = _past_cap_candidates("past-owner-inside-cap", section, fn)
    lines = _record_lines(candidates, record_id)
    check("past rulings inside cap: the decision record is a candidate (scope)", bool(lines), str(candidates)[:200])
    if not lines:
        return
    check("past rulings inside cap: the owner sentence inside INDEX_CAP still reaches the record's line",
          any("Haiku at xhigh" in line and "2026-11-17 19:45" in line for line in lines), lines[0][:200])


def case_past_ruling_section_without_owner_sentence_is_cut_at_the_cap():
    import question_form  # the one form check (hooks/question_form.py)
    fn = getattr(question_form, "past_rulings", None)
    check("past rulings cut: question_form.past_rulings exists", callable(fn), "missing function")
    if not callable(fn):
        return
    head, tail = "HEADMARK-5a1e opens the record.", "TAILMARK-9c2d closes it."
    section = head + " " + _filler(2400) + " " + tail
    record_id, candidates = _past_cap_candidates("past-owner-none", section, fn)
    lines = _record_lines(candidates, record_id)
    check("past rulings cut: the decision record is a candidate (scope)", bool(lines), str(candidates)[:200])
    if not lines:
        return
    text = _record_text(candidates, record_id)
    check("past rulings cut: the text inside INDEX_CAP still reaches the record's line", "HEADMARK-5a1e" in text,
          text[:200])
    check("past rulings cut: a section with no owner sentence is cut, so its tail past the cap is absent",
          "TAILMARK-9c2d" not in text, text[-200:])
    check("past rulings cut: the record adds no more than INDEX_CAP plus RULING_EXTRA_CAP characters",
          len(text) <= question_form.INDEX_CAP + question_form.RULING_EXTRA_CAP, "%d characters" % len(text))


def case_past_ruling_owner_sentences_added_text_is_capped():
    import question_form  # the one form check (hooks/question_form.py)
    fn = getattr(question_form, "past_rulings", None)
    check("past rulings capped: question_form.past_rulings exists", callable(fn), "missing function")
    if not callable(fn):
        return
    section = _filler(900) + " " + " ".join(OWNER_SENTENCES)
    check("past rulings capped: the fixture puts the first owner sentence past INDEX_CAP",
          section.index(OWNER_SENTENCES[0]) > question_form.INDEX_CAP,
          "offset %d" % section.index(OWNER_SENTENCES[0]))
    record_id, candidates = _past_cap_candidates("past-owner-bounded", section, fn)
    lines = _record_lines(candidates, record_id)
    check("past rulings capped: the decision record is a candidate (scope)", bool(lines), str(candidates)[:200])
    if not lines:
        return
    text = _record_text(candidates, record_id)
    check("past rulings capped: the first owner sentence past INDEX_CAP reaches the record's line",
          OWNER_SENTENCES[0] in text, text[-200:])
    check("past rulings capped: 60 owner sentences sit past the cap, and the record adds no more than "
          "INDEX_CAP plus RULING_EXTRA_CAP characters",
          len(text) <= question_form.INDEX_CAP + question_form.RULING_EXTRA_CAP, "%d characters" % len(text))


# A markdown table row is judged alone. Run on together, the rows of a long table form one unit bigger than a record's
# whole ruling budget, and a ruling by the owner in the table's last row would be lost with that unit.
TABLE_FILLER_ROWS = 90  # joined, these rows run well past one record's whole ruling budget


def case_past_ruling_owner_row_after_a_long_table_reaches_the_line():
    import question_form  # the one form check (hooks/question_form.py)
    fn = getattr(question_form, "past_rulings", None)
    check("past rulings table: question_form.past_rulings exists", callable(fn), "missing function")
    if not callable(fn):
        return
    rows = ["| a%d | b | c |" % i for i in range(TABLE_FILLER_ROWS)]
    rows.append("| last | owner ruling 2026-11-17 19:45 CST | keep | ... |")
    section = "B" * 790 + ". \n" + "\n".join(rows)
    record_id, candidates = _past_cap_candidates("past-owner-table-row", section, fn)
    lines = _record_lines(candidates, record_id)
    check("past rulings table: the decision record is a candidate (scope)", bool(lines), str(candidates)[:200])
    if not lines:
        return
    text = _record_text(candidates, record_id)
    check("past rulings table: the owner ruling row past INDEX_CAP, after a long table, reaches the record's line",
          "owner ruling 2026-11-17 19:45" in text, text[-200:])
    check("past rulings table: the record adds no more than INDEX_CAP plus RULING_EXTRA_CAP characters",
          len(text) <= question_form.INDEX_CAP + question_form.RULING_EXTRA_CAP, "%d characters" % len(text))


# Sentences that state a ruling by the owner that do not all fit are taken newest date stamp first (question_form._owner_sentences). So a
# newer ruling beats an older one that sits earlier in the section, and an undated one sorts after the dated ones, so
# it is the one dropped when the newer ruling fills the budget.
NEWEST_LEAD = "Owner ruling, 2026-11-17 19:45 CST: keep the new review budget"
OLDER_LEAD = "Owner ruling, 2026-11-16 09:00 CST: keep the old review budget"
UNDATED_LEAD = "Owner ruling: keep the undated review budget"
PAD_WORDS = "keep the review stack and its model pins as they are".split()


def _sized_sentence(lead, n_chars):
    """One sentence of n_chars characters: `lead`, then plain words with no ruling word, then a period. It holds no
    sentence break before its end."""
    text, index = lead, 0
    while len(text) < n_chars - 1:
        text += " " + PAD_WORDS[index % len(PAD_WORDS)]
        index += 1
    return text[:n_chars - 1] + "."


def case_past_ruling_owner_sentences_newest_date_first():
    import question_form  # the one form check (hooks/question_form.py)
    fn = getattr(question_form, "past_rulings", None)
    check("past rulings newest first: question_form.past_rulings exists", callable(fn), "missing function")
    if not callable(fn):
        return
    cap = question_form.RULING_EXTRA_CAP  # the budget is read from the module, never copied
    newer = _sized_sentence(NEWEST_LEAD, cap // 2)
    older = _sized_sentence(OLDER_LEAD, cap * 55 // 100)
    undated = _sized_sentence(UNDATED_LEAD, cap * 52 // 100)
    section = _filler(900) + " " + older + " " + undated + " " + newer
    check("past rulings newest first: the fixture puts the three owner sentences past INDEX_CAP",
          min(section.index(s) for s in (older, undated, newer)) > question_form.INDEX_CAP,
          "offset %d" % section.index(older))
    check("past rulings newest first: the older and newer dated sentences together are over RULING_EXTRA_CAP",
          len(older) + len(newer) > cap, "%d characters" % (len(older) + len(newer)))
    check("past rulings newest first: the undated sentence does not fit beside the newer dated one",
          1 + len(newer) + 1 + len(undated) > cap, "%d characters" % (len(newer) + len(undated)))
    check("past rulings newest first: the older dated sentence comes first in the section",
          section.index(older) < section.index(newer), "fixture order")
    record_id, candidates = _past_cap_candidates("past-owner-newest-first", section, fn)
    lines = _record_lines(candidates, record_id)
    check("past rulings newest first: the decision record is a candidate (scope)", bool(lines),
          str(candidates)[:200])
    if not lines:
        return
    text = _record_text(candidates, record_id)
    check("past rulings newest first: the newer dated owner sentence reaches the record's line", newer in text,
          text[-200:])
    check("past rulings newest first: the older dated owner sentence is dropped, as it does not fit beside the newer",
          older not in text, text[-200:])
    check("past rulings newest first: the undated owner sentence sorts after the dated ones, so it is dropped when "
          "the newer one fills the budget", undated not in text, text[-200:])


# The owner's rulings not yet on main (the ruled store) sit on origin/roadmap. past_rulings puts each open entry first,
# ahead of the decision records, and names what it supersedes. The pointer is patched to the fixture repo, so the cases
# pass whichever checkout past_rulings reads the store from.
RULED_ID, RULED_CLOSED_ID = "ruled-apps-keep", "ruled-old-shut"
RULED_AT = "2026-11-12T14:15:00-06:00"
RULED_TEXT = "Owner, 2026-11-12, page item 12: keep the apps' access to claude-settings as it is."
RULED_SUPERSEDES = [{"kind": "main-sentence", "ref": "apps-keep-sentence"},
                    {"kind": "test", "ref": "hooks/test_question_form.py::case_ruled_store_first_and_carries_supersedes"}]


def case_ruled_store_first_and_carries_supersedes():
    import question_form  # the one form check (hooks/question_form.py)
    fn = getattr(question_form, "past_rulings", None)
    check("ruled store: question_form.past_rulings exists", callable(fn), "missing function")
    if not callable(fn):
        return
    repo = tcj.make_repo("ruled-first", decisions={tcj.APPS_SLUG: tcj.APPS_RULING})
    fixture.point_ref(repo, fixture.STORE_REF, fixture.ruling_files({
        RULED_ID: fixture.entry(RULED_ID, at=RULED_AT, ruling=RULED_TEXT, supersedes=RULED_SUPERSEDES),
        RULED_CLOSED_ID: fixture.entry(RULED_CLOSED_ID, status="closed"),
    }), tcj.ROOT)
    with mock.patch(POINTER_CHECKOUT, return_value=repo):
        candidates, _unknown = fn(tcj.APPS_GOAL, repo)
    first = candidates[0] if candidates else ""
    check("ruled store: the open entry is the first candidate, ahead of the decision records",
          first.startswith("ruled:%s: " % RULED_ID), str(candidates)[:200])
    check("ruled store: the first candidate carries the entry's ruling text", RULED_TEXT in first, first[:200])
    check("ruled store: the first candidate names the owner time and says open, not on main",
          ("(owner %s; open, not on main; supersedes " % RULED_AT) in first and first.endswith(")"), first[:200])
    check("ruled store: the first candidate carries each supersedes ref",
          all(item["ref"] in first for item in RULED_SUPERSEDES), first[:200])
    check("ruled store: a closed entry is no candidate",
          not any(c.startswith("ruled:%s:" % RULED_CLOSED_ID) for c in candidates), str(candidates)[:200])


RULED_UNREAD_ID = "ruled-unread"


def case_ruled_store_marks_an_unread_entry_unchecked():
    import question_form  # the one form check (hooks/question_form.py)
    fn = getattr(question_form, "past_rulings", None)
    check("ruled store unread: question_form.past_rulings exists", callable(fn), "missing function")
    if not callable(fn):
        return
    repo = tcj.make_repo("ruled-unread", decisions={tcj.APPS_SLUG: tcj.APPS_RULING})
    fixture.point_ref(repo, fixture.STORE_REF, fixture.ruling_files({
        RULED_ID: fixture.entry(RULED_ID, at=RULED_AT, ruling=RULED_TEXT, supersedes=RULED_SUPERSEDES),
        RULED_UNREAD_ID: fixture.entry(RULED_UNREAD_ID, at="2026-11-13T09:00:00-06:00", ruling=RULED_TEXT,
                                       supersedes=None, supersedes_none="unread: triage has not read the supersedes"),
    }), tcj.ROOT)
    with mock.patch(POINTER_CHECKOUT, return_value=repo):
        candidates, _unknown = fn(tcj.APPS_GOAL, repo)
    unread_line = next((c for c in candidates if c.startswith("ruled:%s:" % RULED_UNREAD_ID)), "")
    read_line = next((c for c in candidates if c.startswith("ruled:%s:" % RULED_ID)), "")
    check("ruled store unread: the unread entry is listed", bool(unread_line), str(candidates)[:200])
    check("ruled store unread: its candidate line is marked (unchecked, not law)",
          "(unchecked, not law)" in unread_line, unread_line[:200])
    check("ruled store unread: a read entry's candidate line carries no unchecked mark",
          bool(read_line) and "(unchecked, not law)" not in read_line, read_line[:200])


def case_ruled_store_absent_is_only_unknown():
    import question_form  # the one form check (hooks/question_form.py)
    fn = getattr(question_form, "past_rulings", None)
    check("ruled store absent: question_form.past_rulings exists", callable(fn), "missing function")
    if not callable(fn):
        return
    repo = tcj.make_repo("ruled-absent", decisions={tcj.APPS_SLUG: tcj.APPS_RULING})
    with mock.patch(POINTER_CHECKOUT, return_value=repo):
        candidates, unknown = fn(tcj.APPS_GOAL, repo)
    check("ruled store absent: the unknown list names the store as absent",
          "ruled store (absent)" in unknown, str(unknown)[:300])
    check("ruled store absent: no candidate is a ruled entry",
          not any(c.startswith("ruled:") for c in candidates), str(candidates)[:200])
    check("ruled store absent: the absent store never refuses",
          "ruled store (absent)" not in question_form.unreadable_sources(unknown), str(unknown)[:300])


# Store entries join the candidates only when they share a word with the question (the step rulings' word test), and at
# most RULED_CAP_MAX of them, the newest first. An entry that shares no word stays out.
RULED_UNRELATED = "ruled-lunch-menu"
RULED_UNRELATED_TEXT = "Owner: the cafeteria menu changes on Fridays."
RULED_CAP_MAX = 8


def ruled_ids(candidates):
    """The ids of the ruled candidates, in the order past_rulings gave them (`ruled:<id>: ...` lines)."""
    return [c[len("ruled:"):].split(":", 1)[0] for c in candidates if c.startswith("ruled:")]


def case_ruled_store_words_filter_leaves_out_an_unrelated_entry():
    import question_form  # the one form check (hooks/question_form.py)
    fn = getattr(question_form, "past_rulings", None)
    check("ruled store words: question_form.past_rulings exists", callable(fn), "missing function")
    if not callable(fn):
        return
    repo = tcj.make_repo("ruled-words", decisions={tcj.APPS_SLUG: tcj.APPS_RULING})
    fixture.point_ref(repo, fixture.STORE_REF, fixture.ruling_files({
        RULED_ID: fixture.entry(RULED_ID, at=RULED_AT, ruling=RULED_TEXT),
        # Newer than the matching entry, so newest-first alone would list it first if it were kept.
        RULED_UNRELATED: fixture.entry(RULED_UNRELATED, at="2026-11-13T09:00:00-06:00", ruling=RULED_UNRELATED_TEXT,
                                       quote="lunch options", source="page item 40",
                                       supersedes=[{"kind": "test", "ref": "lunch-menu-check"}]),
    }), tcj.ROOT)
    with mock.patch(POINTER_CHECKOUT, return_value=repo):
        candidates, _unknown = fn(tcj.APPS_GOAL, repo)
    listed = ruled_ids(candidates)
    check("ruled store words: the entry that shares words with the question is listed",
          RULED_ID in listed, str(candidates)[:200])
    check("ruled store words: the entry that shares words with the question is the first candidate",
          bool(candidates) and candidates[0].startswith("ruled:%s: " % RULED_ID), str(candidates)[:200])
    check("ruled store words: the entry that shares no word with the question is left out",
          RULED_UNRELATED not in listed and RULED_UNRELATED_TEXT not in str(candidates), str(candidates)[:200])


def case_ruled_store_caps_matching_entries_at_eight_newest_first():
    import question_form  # the one form check (hooks/question_form.py)
    fn = getattr(question_form, "past_rulings", None)
    check("ruled store cap: question_form.past_rulings exists", callable(fn), "missing function")
    if not callable(fn):
        return
    entries = {}
    for day in range(1, 13):
        rid = "ruled-cap-%02d" % day
        entries[rid] = fixture.entry(rid, at="2026-11-%02dT09:00:00-06:00" % day,
                                     ruling="Owner: keep the apps' access to claude-settings, round %02d." % day)
    repo = tcj.make_repo("ruled-cap", decisions={tcj.APPS_SLUG: tcj.APPS_RULING})
    fixture.point_ref(repo, fixture.STORE_REF, fixture.ruling_files(entries), tcj.ROOT)
    with mock.patch(POINTER_CHECKOUT, return_value=repo):
        candidates, _unknown = fn(tcj.APPS_GOAL, repo)
    listed = ruled_ids(candidates)
    expected = ["ruled-cap-%02d" % day for day in range(12, 12 - RULED_CAP_MAX, -1)]
    check("ruled store cap: at most %d matching entries are listed" % RULED_CAP_MAX,
          len(listed) <= RULED_CAP_MAX, "listed %d: %r" % (len(listed), listed))
    check("ruled store cap: the %d newest matching entries are listed, newest first" % RULED_CAP_MAX,
          listed == expected, "listed %r, want %r" % (listed, expected))


def case_ruled_store_ranks_by_shared_words_before_recency():
    import question_form  # the one form check (hooks/question_form.py)
    fn = getattr(question_form, "past_rulings", None)
    check("ruled store rank: question_form.past_rulings exists", callable(fn), "missing function")
    if not callable(fn):
        return
    many = "ruled-many-words"
    entries = {many: fixture.entry(many, at="2026-10-20T09:00:00-06:00",
                                   ruling="Owner: keep the GitHub apps' access to claude-settings as it is.")}
    # Nine newer entries, each sharing only the word "apps" with the question: recency alone would list them first.
    for day in range(4, 13):
        rid = "ruled-one-word-%02d" % day
        entries[rid] = fixture.entry(rid, at="2026-11-%02dT09:00:00-06:00" % day,
                                     ruling="Owner: the apps menu changes on Fridays, item %02d." % day)
    repo = tcj.make_repo("ruled-rank", decisions={tcj.APPS_SLUG: tcj.APPS_RULING})
    fixture.point_ref(repo, fixture.STORE_REF, fixture.ruling_files(entries), tcj.ROOT)
    with mock.patch(POINTER_CHECKOUT, return_value=repo):
        candidates, _unknown = fn(tcj.APPS_GOAL, repo)
    listed = ruled_ids(candidates)
    check("ruled store rank: the entry that shares the most words with the question is listed",
          many in listed, str(listed))
    check("ruled store rank: the entry that shares the most words is the first candidate, ahead of newer ones",
          bool(listed) and listed[0] == many, str(listed))
    check("ruled store rank: still at most %d ruled entries" % RULED_CAP_MAX,
          len(listed) <= RULED_CAP_MAX, "listed %d: %r" % (len(listed), listed))


# A ruling's optional `scope` (lint/test_ruled_store.py): {"visibility": "private"} governs a private repo only. The
# repo's visibility is its extras key `visibility`, which lint/layout.py reads (make_repo(visibility=...) writes it). Each
# case reads that visibility back through layout.caution, and asserts it, before it judges the candidates.
SCOPE_PRIVATE = {"visibility": "private"}
SCOPE_PUBLIC = {"visibility": "public"}
SCOPE_OPEN_ID, SCOPE_PRIVATE_ID, SCOPE_PUBLIC_ID = "scope-open", "scope-private", "scope-public"
SCOPE_DAY = "2026-11-13T09:00:00-06:00"


def _reads_as(repo, level):
    """True when lint/layout.py reads the repo's visibility as the caution level `level` (public or private-solo)."""
    import layout  # lint/layout.py, the one reader of the visibility key
    return layout.caution(repo)["level"] == level


def _scoped_store(repo, entries):
    fixture.point_ref(repo, fixture.STORE_REF, fixture.ruling_files(entries), tcj.ROOT)


def _listed_ruled_ids(repo):
    """The ruled ids past_rulings lists for the Apps goal, the store read from `repo` itself."""
    import question_form  # the one form check (hooks/question_form.py)
    with mock.patch(POINTER_CHECKOUT, return_value=repo):
        candidates, _unknown = question_form.past_rulings(tcj.APPS_GOAL, repo)
    return ruled_ids(candidates)


def case_ruled_store_scope_omits_a_private_ruling_in_a_public_repo():
    import question_form  # the one form check (hooks/question_form.py)
    fn = getattr(question_form, "past_rulings", None)
    check("ruled scope public: question_form.past_rulings exists", callable(fn), "missing function")
    if not callable(fn):
        return
    repo = tcj.make_repo("ruled-scope-public", decisions={tcj.APPS_SLUG: tcj.APPS_RULING}, visibility="public")
    _scoped_store(repo, {
        SCOPE_OPEN_ID: fixture.entry(SCOPE_OPEN_ID, at=SCOPE_DAY, ruling=RULED_TEXT),
        SCOPE_PRIVATE_ID: fixture.entry(SCOPE_PRIVATE_ID, at=SCOPE_DAY, ruling=RULED_TEXT, scope=SCOPE_PRIVATE),
    })
    reads_public = _reads_as(repo, "public")
    check("ruled scope public: the fixture repo reads as public (scope control)", reads_public,
          "layout.caution did not read the repo's visibility as public")
    if not reads_public:
        return
    listed = _listed_ruled_ids(repo)
    check("ruled scope public: an unscoped ruling is listed in a public repo", SCOPE_OPEN_ID in listed, str(listed))
    check("ruled scope public: a ruling scoped to private is omitted from a public repo",
          SCOPE_PRIVATE_ID not in listed, str(listed))


def case_ruled_store_scope_keeps_a_private_ruling_in_a_private_repo():
    import question_form  # the one form check (hooks/question_form.py)
    fn = getattr(question_form, "past_rulings", None)
    check("ruled scope private: question_form.past_rulings exists", callable(fn), "missing function")
    if not callable(fn):
        return
    repo = tcj.make_repo("ruled-scope-private", decisions={tcj.APPS_SLUG: tcj.APPS_RULING}, visibility="private")
    _scoped_store(repo, {
        SCOPE_OPEN_ID: fixture.entry(SCOPE_OPEN_ID, at=SCOPE_DAY, ruling=RULED_TEXT),
        SCOPE_PRIVATE_ID: fixture.entry(SCOPE_PRIVATE_ID, at=SCOPE_DAY, ruling=RULED_TEXT, scope=SCOPE_PRIVATE),
    })
    reads_private = _reads_as(repo, "private-solo")
    check("ruled scope private: the fixture repo reads as private (scope control)", reads_private,
          "layout.caution did not read the repo's visibility as private")
    if not reads_private:
        return
    listed = _listed_ruled_ids(repo)
    check("ruled scope private: an unscoped ruling is listed in a private repo", SCOPE_OPEN_ID in listed, str(listed))
    check("ruled scope private: a ruling scoped to private is listed in a private repo",
          SCOPE_PRIVATE_ID in listed, str(listed))


def case_ruled_store_scope_private_only_lists_no_ruling_in_a_public_repo():
    # The empty state: the only ruling that shares words with the question is private-scoped.
    import question_form  # the one form check (hooks/question_form.py)
    fn = getattr(question_form, "past_rulings", None)
    check("ruled scope empty: question_form.past_rulings exists", callable(fn), "missing function")
    if not callable(fn):
        return
    repo = tcj.make_repo("ruled-scope-empty", decisions={tcj.APPS_SLUG: tcj.APPS_RULING}, visibility="public")
    _scoped_store(repo, {
        SCOPE_PRIVATE_ID: fixture.entry(SCOPE_PRIVATE_ID, at=SCOPE_DAY, ruling=RULED_TEXT, scope=SCOPE_PRIVATE),
    })
    reads_public = _reads_as(repo, "public")
    check("ruled scope empty: the fixture repo reads as public (scope control)", reads_public,
          "layout.caution did not read the repo's visibility as public")
    if not reads_public:
        return
    listed = _listed_ruled_ids(repo)
    check("ruled scope empty: a public repo whose only matching ruling is private lists no ruled candidate",
          listed == [], str(listed))


def case_ruled_store_scope_private_rulings_do_not_take_the_cap():
    # The full-size state: RULED_CAP_MAX private-scoped rulings are newer than the unscoped one, and all match the words.
    # A cap applied before the scope filter would spend its slots on them and drop the unscoped ruling.
    import question_form  # the one form check (hooks/question_form.py)
    fn = getattr(question_form, "past_rulings", None)
    check("ruled scope cap: question_form.past_rulings exists", callable(fn), "missing function")
    if not callable(fn):
        return
    repo = tcj.make_repo("ruled-scope-cap", decisions={tcj.APPS_SLUG: tcj.APPS_RULING}, visibility="public")
    entries = {SCOPE_OPEN_ID: fixture.entry(SCOPE_OPEN_ID, at="2026-11-01T09:00:00-06:00", ruling=RULED_TEXT)}
    for day in range(1, RULED_CAP_MAX + 1):
        rid = "scope-cap-private-%02d" % day
        entries[rid] = fixture.entry(rid, at="2026-11-%02dT09:00:00-06:00" % (10 + day),
                                     ruling="Owner: keep the apps' access to claude-settings, round %02d." % day,
                                     scope=SCOPE_PRIVATE)
    _scoped_store(repo, entries)
    reads_public = _reads_as(repo, "public")
    check("ruled scope cap: the fixture repo reads as public (scope control)", reads_public,
          "layout.caution did not read the repo's visibility as public")
    if not reads_public:
        return
    listed = _listed_ruled_ids(repo)
    check("ruled scope cap: the unscoped ruling is listed though %d newer private rulings match" % RULED_CAP_MAX,
          SCOPE_OPEN_ID in listed, str(listed))
    check("ruled scope cap: no private-scoped ruling is listed in a public repo",
          not any(rid.startswith("scope-cap-private-") for rid in listed), str(listed))


def case_ruled_store_scope_omits_a_public_ruling_in_a_private_repo():
    import question_form  # the one form check (hooks/question_form.py)
    fn = getattr(question_form, "past_rulings", None)
    check("ruled scope public-in-private: question_form.past_rulings exists", callable(fn), "missing function")
    if not callable(fn):
        return
    repo = tcj.make_repo("ruled-scope-public-in-private", decisions={tcj.APPS_SLUG: tcj.APPS_RULING},
                         visibility="private")
    _scoped_store(repo, {
        SCOPE_OPEN_ID: fixture.entry(SCOPE_OPEN_ID, at=SCOPE_DAY, ruling=RULED_TEXT),
        SCOPE_PUBLIC_ID: fixture.entry(SCOPE_PUBLIC_ID, at=SCOPE_DAY, ruling=RULED_TEXT, scope=SCOPE_PUBLIC),
    })
    reads_private = _reads_as(repo, "private-solo")
    check("ruled scope public-in-private: the fixture repo reads as private (scope control)", reads_private,
          "layout.caution did not read the repo's visibility as private")
    if not reads_private:
        return
    listed = _listed_ruled_ids(repo)
    check("ruled scope public-in-private: an unscoped ruling is listed in a private repo",
          SCOPE_OPEN_ID in listed, str(listed))
    check("ruled scope public-in-private: a ruling scoped to public is omitted from a private repo",
          SCOPE_PUBLIC_ID not in listed, str(listed))


def case_ruled_store_scope_keeps_a_public_ruling_in_a_public_repo():
    import question_form  # the one form check (hooks/question_form.py)
    fn = getattr(question_form, "past_rulings", None)
    check("ruled scope public-in-public: question_form.past_rulings exists", callable(fn), "missing function")
    if not callable(fn):
        return
    repo = tcj.make_repo("ruled-scope-public-in-public", decisions={tcj.APPS_SLUG: tcj.APPS_RULING},
                         visibility="public")
    _scoped_store(repo, {
        SCOPE_OPEN_ID: fixture.entry(SCOPE_OPEN_ID, at=SCOPE_DAY, ruling=RULED_TEXT),
        SCOPE_PUBLIC_ID: fixture.entry(SCOPE_PUBLIC_ID, at=SCOPE_DAY, ruling=RULED_TEXT, scope=SCOPE_PUBLIC),
    })
    reads_public = _reads_as(repo, "public")
    check("ruled scope public-in-public: the fixture repo reads as public (scope control)", reads_public,
          "layout.caution did not read the repo's visibility as public")
    if not reads_public:
        return
    listed = _listed_ruled_ids(repo)
    check("ruled scope public-in-public: an unscoped ruling is listed in a public repo",
          SCOPE_OPEN_ID in listed, str(listed))
    check("ruled scope public-in-public: a ruling scoped to public is listed in a public repo",
          SCOPE_PUBLIC_ID in listed, str(listed))


class _BrokenPipeGit:
    """A git child that dies before its stdin is read: the write raises BrokenPipeError, and stderr holds the text."""

    def __init__(self, stderr):
        self.stdin = self
        self.stdout = io.BytesIO(b"")
        self.stderr = io.BytesIO(stderr)
        self.returncode = 128

    def write(self, data):
        raise BrokenPipeError(32, "Broken pipe")

    def flush(self):
        pass

    def close(self):
        pass

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def communicate(self, data=None, timeout=None):
        return b"", self.stderr.read()


def _unknown_after_broken_pipe(name, stderr):
    """The unknown lines of past_rulings for a folder with a .git entry, where git's stdin write raises a broken pipe."""
    from unittest import mock
    import _nowindow  # the one home of a no-window child start, which _read_steps calls through
    import question_form  # the one form check (hooks/question_form.py)
    folder = os.path.join(RUN_FOLDER, name)
    os.makedirs(folder, exist_ok=True)
    open(os.path.join(folder, ".git"), "w", encoding="utf-8").close()
    with mock.patch.object(_nowindow, "Popen", return_value=_BrokenPipeGit(stderr)):
        _candidates, unknown = question_form.past_rulings(tcj.APPS_GOAL, folder)
    return unknown


def case_roadmap_broken_pipe_not_a_repo_is_absent():
    import question_form  # the one form check (hooks/question_form.py)
    fn = getattr(question_form, "past_rulings", None)
    check("roadmap broken pipe: question_form.past_rulings exists", callable(fn), "missing function")
    if not callable(fn):
        return
    unknown = _unknown_after_broken_pipe(
        "roadmap-not-a-repo", b"fatal: not a git repository (or any of the parent directories): .git\n")
    check("roadmap broken pipe: a .git entry that is no repository reads the roadmap as absent, not unreadable",
          "roadmap step notes (absent)" in unknown
          and not any("roadmap step notes (unreadable" in line for line in unknown), str(unknown)[:300])
    check("roadmap broken pipe: the absent roadmap does not refuse the question",
          not question_form.unreadable_sources(unknown), str(question_form.unreadable_sources(unknown))[:300])


def case_roadmap_broken_pipe_other_stderr_stays_unreadable():
    import question_form  # the one form check (hooks/question_form.py)
    fn = getattr(question_form, "past_rulings", None)
    check("roadmap broken pipe: question_form.past_rulings exists", callable(fn), "missing function")
    if not callable(fn):
        return
    unknown = _unknown_after_broken_pipe("roadmap-other-stderr", b"fatal: unable to read tree deadbeef\n")
    roadmap = [line for line in unknown if "roadmap step notes" in line]
    check("roadmap broken pipe: other stderr text stays unreadable, so the question refuses",
          len(roadmap) == 1 and "unreadable" in roadmap[0] and "absent" not in roadmap[0], str(unknown)[:300])


# ------------------------------------------------------------------ item 51's field: a picture's focus at the top level

def case_item_51_stray_field():
    """A focus written at the top level of a decision, outside its designs, is a field the page does not list. It is
    refused as item-field-rendered and names the field, on both surfaces."""
    page("a top-level focus the page does not list is refused, naming it", "set",
         entry_of(page_item(focus="#fill")), ("item-field-rendered", "focus"))


# ------------------------------------------------------------------ n is a number (step item-n-must-be-number)

# The page's own rule is `typeof it.n === "number" && isFinite(it.n)` (skills/waiting-page/page.html, problem()).
# An item whose n fails it shows "This item has no number, so it cannot be answered". The guard refuses the write
# under the rule item-field-rendered with the reason "item-n-number", and names the item id.
N_RULE = "item-field-rendered"
N_ITEM_ID = "item-n-case"


def with_n(**over):
    """The form item with n set to a value, or with no n when `absent` is passed."""
    item = page_item()
    if over.pop("absent", False):
        item.pop("n", None)
    else:
        item["n"] = over.pop("n", 929)
    item.update(over)
    return item


def case_item_n_text_is_refused():
    for value in ("929", "", " 929", "9.29e2"):
        page("a set whose n is the text %r is refused, naming the item" % value, "set",
             entry_of(with_n(n=value), doc_id=N_ITEM_ID), (N_RULE, N_ITEM_ID))
    page("an update whose n is the text \"929\" is refused, naming the item", "update",
         entry_of({"n": "929"}, doc_id=N_ITEM_ID), (N_RULE, N_ITEM_ID))
    page("a str_replace on the field n is refused, since it can only give text", "str_replace",
         {"collection": "items", "doc_id": N_ITEM_ID, "field": "n", "old_str": "9", "new_str": "8"},
         (N_RULE, N_ITEM_ID))


def case_item_n_other_non_numbers_are_refused():
    # The page's rule: a number that isfinite. A bool, a null, a list, an object, NaN and infinity all fail it.
    for label, value in (("true", True), ("null", None), ("a list", [929]), ("an object", {"n": 929}),
                         ("NaN", float("nan")), ("infinity", float("inf")), ("minus infinity", float("-inf")),
                         ("an int too big for a float", 10 ** 400)):
        page("a set whose n is %s is refused" % label, "set",
             entry_of(with_n(n=value), doc_id=N_ITEM_ID), (N_RULE, N_ITEM_ID))
    page("an update that removes n with the delete marker is refused", "update",
         entry_of({"n": {"__delete__": True}}, doc_id=N_ITEM_ID), (N_RULE, N_ITEM_ID))


def case_item_n_number_passes():
    for label, value in (("929", 929), ("0", 0), ("a negative number", -3), ("a float, which the page accepts", 929.5)):
        page("a set whose n is %s passes" % label, "set", entry_of(with_n(n=value), doc_id=N_ITEM_ID), None)
    page("an update whose n is the number 929 passes", "update", entry_of({"n": 929}, doc_id=N_ITEM_ID), None)


def case_item_n_absent():
    page("a set with no n is refused: a new item needs a number", "set",
         entry_of(with_n(absent=True), doc_id=N_ITEM_ID), (N_RULE, N_ITEM_ID))
    page("an update that does not touch n passes", "update",
         entry_of({"title": "A new title"}, doc_id=N_ITEM_ID), None)
    page("an update of the form fields that does not touch n passes", "update",
         entry_of({"kind": "decision", "context": form_text()}, doc_id=N_ITEM_ID), None)
    page("a str_replace on another field is not judged for n", "str_replace",
         {"collection": "items", "doc_id": N_ITEM_ID, "field": "title", "old_str": "a", "new_str": "b"}, None)


def case_item_n_batch_and_file_path():
    def write(op, data, doc_id):
        return {"op": op, "collection": "items", "doc_id": doc_id, "data": data}

    def batch(*writes):
        return {"action": "batch", "url": PAGE_URL, "writes": list(writes)}

    bad = batch(write("set", with_n(n=928), "good-one"), write("set", with_n(n="929"), "bad-one"),
                write("update", {"title": "x"}, "fine-one"))
    verdict("batch: one item with a text n refuses the call, naming that item",
            guard.data_tool_hit(bad, PAGE_REPO), (N_RULE, "bad-one"))
    verdict("batch: the same call through question_form.page_item_hit refuses the same item",
            question_form.page_item_hit(bad, PAGE_REPO)[0], (N_RULE, "bad-one"))
    ok = batch(write("set", with_n(n=928), "good-one"), write("set", with_n(n=929), "good-two"),
               write("update", {"title": "x"}, "fine-one"))
    verdict("batch: numbers on every set and an update with no n pass", guard.data_tool_hit(ok, PAGE_REPO), None)
    # The file_path form: the data is read from the file, a relative path against the payload cwd.
    folder = judged_folder()
    write_json_file(os.path.join(folder, "n-text.json"), with_n(n="929"))
    write_json_file(os.path.join(folder, "n-number.json"), with_n(n=929))
    refused = {"collection": "items", "doc_id": N_ITEM_ID, "file_path": "n-text.json"}
    passed = {"collection": "items", "doc_id": N_ITEM_ID, "file_path": "n-number.json"}
    verdict("file_path: a file whose n is text is refused, read at the payload cwd",
            call("item_hit", "set", refused, folder), (N_RULE, N_ITEM_ID))
    verdict("file_path: a file whose n is a number passes", call("item_hit", "set", passed, folder), None)


def case_item_n_posted_text_names_the_item():
    # The text Claude sees is the printed reason, not the log line: in a batch it must say which write to fix.
    def write(op, data, doc_id):
        return {"op": op, "collection": "items", "doc_id": doc_id, "data": data}

    bad = {"action": "batch", "url": PAGE_URL,
           "writes": [write("set", with_n(n=928), "good-one"), write("set", with_n(n="929"), "bad-one"),
                      write("update", {"title": "x"}, "fine-one")]}
    said = printed_reason(bad)
    check("batch: the posted n refusal names the bad item", "bad-one" in said, repr(said)[:300])
    check("batch: the posted n refusal names no good item",
          not re.search(r"good-one|fine-one", said), repr(said)[:300])
    check("batch: the posted n refusal still carries the correction",
          "number such as 929" in said, repr(said)[:300])


def case_item_n_text_inside_other_text_is_not_judged():
    # Scanner-safe: the check reads the parsed n, never the text of the write. Text that looks like an n, and
    # comment openers and a lone quote, beside a real number are plain text.
    context = form_text(goal='Goal: keep "n": "929" and n: "929" as plain text, with //path, /* glob and # tags, and don\'t parse it.')
    page("a real number n beside text that reads as a text n passes", "set",
         entry_of(with_n(n=929, context=context), doc_id=N_ITEM_ID), None)
    page("a text n beside text that reads as a number n is still refused", "set",
         entry_of(with_n(n="929", context=form_text(goal='Goal: keep "n": 929 as plain text.')), doc_id=N_ITEM_ID),
         (N_RULE, N_ITEM_ID))


def case_item_n_reason_and_the_pages_own_rule():
    reasons = getattr(question_form, "PAGE_REASONS", None) or {}
    text = reasons.get("item-n-number") or ""
    check("the n reason says n must be a number such as 929, not \"929\"",
          "number such as 929" in text and '"929"' in text, repr(text)[:200])
    check("the n reason cites the decision item-field-rendered", "decision item-field-rendered" in text, repr(text)[:200])
    check("the n reason posts only the correction: it names no other rule's remedy",
          not re.search(r"itemFields|Goal|Problem|__delete__", text), repr(text)[:200])
    # The allow list points at the page's own rule: the page must still carry the predicate the guard follows.
    with open(os.path.join(REPO, "skills", "waiting-page", "page.html"), encoding="utf-8") as f:
        page_text = f.read()
    check("the page's problem() still judges n by typeof number and isFinite",
          'typeof it.n === "number" && isFinite(it.n)' in page_text, "page.html no longer carries the n rule")


# ------------------------------------------------------------------ dismissed: the page's own Mark read

def case_session_update_naming_dismissed_is_refused():
    """`dismissed` is written by the page's Mark read only (step ask-phase-out). The page draws it, so its itemFields
    block lists it, yet a session update that names it is refused on both surfaces. The control is a session update
    that names only a field, which must pass: a refusal of every update would fail it too."""
    for value in ("2026-11-10T18:00:00Z", None):
        data = {"dismissed": value}
        for surface, got in (("page item_hit", call("item_hit", "update", entry_of(data))),
                             ("page guard", guard_hit("update", entry_of(data)))):
            check("%s: a session update naming dismissed=%r is refused" % (surface, value),
                  got[0] != "" and "dismissed" in str(got[1]).lower(),
                  "want a refusal naming dismissed, got %r" % (got,))
    verdict("control: a session update naming only the title passes",
            call("item_hit", "update", entry_of({"title": "Pick a colour"})), None)


# ------------------------------------------------------------------ dismissed: every route refuses it, and the reason names only Mark read
#
# Step ask-phase-out (owner pick 480 a): the page's Mark read writes `dismissed`, and no session write does. Each route is
# refused at the guard, and the reason the guard prints says that only the page's Mark read writes dismissed. The generic
# item-field reason tells a writer to draw the field on the page, which is wrong here: the page draws dismissed already.

DISMISSED_AT = "2026-11-10T18:00:00Z"
ONLY_MARK_READ = re.compile(r"\bonly\b[^.]*\bMark read\b[^.]*\bdismissed\b", re.IGNORECASE)


def dismissed_routes():
    """One write per route that names `dismissed`, each as ArtifactData sends it: a str_replace, a set, an update, an
    update that deletes it, and a batch entry."""
    base = {"url": PAGE_URL, "collection": "items", "doc_id": DOC}
    return (
        ("str_replace on dismissed", dict(base, action="str_replace", field="dismissed", old_str="null", new_str=DISMISSED_AT)),
        ("set with dismissed", dict(base, action="set", data=page_item(dismissed=DISMISSED_AT))),
        ("update with dismissed", dict(base, action="update", data={"dismissed": DISMISSED_AT})),
        ("update deleting dismissed", dict(base, action="update", data={"dismissed": {"__delete__": True}})),
        ("a batch entry with dismissed", {"url": PAGE_URL, "action": "batch", "writes": [
            {"op": "update", "collection": "items", "doc_id": DOC, "data": {"dismissed": DISMISSED_AT}}]}),
    )


def dismissed_refused(name, tool_input):
    """One write that names dismissed, at the guard. It is refused, and the reason it prints says only the page's Mark
    read writes dismissed, with no generic item-field remedy."""
    got = guard.data_tool_hit(tool_input, PAGE_REPO)
    check("%s: refused, naming dismissed" % name, got[0] != "" and "dismissed" in str(got[1]).lower(),
          "got %r" % (got,))
    reason = printed_reason(tool_input)
    check("%s: the reason says only the page's Mark read writes dismissed" % name,
          bool(ONLY_MARK_READ.search(reason)), reason[:200])
    check("%s: the reason gives no generic itemFields remedy" % name,
          "add it to that block" not in reason, reason[:200])


def case_dismissed_refused_on_every_route():
    """A session's write that names `dismissed` is refused on each route, and each refusal's reason names only Mark read."""
    for name, tool_input in dismissed_routes():
        dismissed_refused(name, tool_input)


def case_dismissed_refused_without_a_readable_field_list():
    """The same routes with the page's itemFields block unreadable (fields is None). The refusal and its reason still hold."""
    blank = os.path.join(RUN_FOLDER, "page-without-itemfields.html")
    os.makedirs(RUN_FOLDER, exist_ok=True)
    with open(blank, "w", encoding="utf-8") as f:
        f.write("<!doctype html>\n<html><body><p>A page with no field list.</p></body></html>\n")
    with mock.patch.dict(os.environ, {question_form.ITEM_FIELDS_SEAM: blank}):
        check("control: the blank page reads as no field list (fields is None)",
              question_form._item_fields(blank) is None, "the block read as a list")
        for name, tool_input in dismissed_routes():
            dismissed_refused(name + ", with no readable field list", tool_input)
        verdict("control: an update naming only a title passes with no readable field list",
                call("item_hit", "update", entry_of({"title": "Pick a colour"})), None)


def case_dismissed_reason_keeps_the_generic_remedy_for_other_fields():
    """Control: a stray top-level field that the page does not list still prints the generic item-field reason."""
    stray = {"url": PAGE_URL, "action": "set", "collection": "items", "doc_id": DOC, "data": page_item(focus="#fill")}
    check("control: a stray top-level field keeps the generic itemFields reason",
          question_form.ITEM_FIELD_REASON in printed_reason(stray), printed_reason(stray)[:200])


# ------------------------------------------------------------------ holdsLane: a lane wait's flag, which the page must draw
#
# A lane wait sets `holdsLane` true and `lane` (skills/waiting-page/SKILL.md, "Add an item"). The guard refuses a top-level
# field that the page's itemFields block does not list, so the flag is refused until the page lists it. A merge or PR wait
# sets `holds` alone and carries no flag.

LANE_HOLDS = "Stops the batch run until the answer."
LANE_WAIT = {"holds": LANE_HOLDS, "holdsLane": True, "lane": "batch-runner"}


def case_lane_wait_flag_is_not_refused_as_undrawn():
    """A session's set and update that carry holdsLane with lane and holds pass on both surfaces. The controls: an update
    that names only lane passes, and a merge wait (holds alone, no flag) passes."""
    got = call("item_field_hit", "update", {}, {"holdsLane": True, "lane": "batch-runner"})
    check("item_field_hit: holdsLane with a lane is not an undrawn field", got == "", "want no hit, got %r" % (got,))
    page("a set carrying holdsLane, lane and holds passes", "set", entry_of(page_item(**LANE_WAIT)), None)
    page("an update carrying holdsLane, lane and holds passes", "update", entry_of(dict(LANE_WAIT)), None)
    page("control: an update that names only lane passes", "update", entry_of({"lane": "batch-runner"}), None)
    page("control: a merge wait, holds alone with no holdsLane, passes", "update", entry_of({"holds": LANE_HOLDS}), None)


def case_page_lists_holds_lane():
    """The page draws the lane-wait flag: its itemFields block lists holdsLane, the list the guard reads."""
    fields = question_form._item_fields(question_form.ITEM_FIELDS_PAGE)
    check("page: its itemFields block reads as a list", fields is not None,
          "the itemFields block in skills/waiting-page/page.html did not read as a list of strings")
    check("page: the itemFields block lists holdsLane", "holdsLane" in (fields or []),
          "the page's itemFields block does not list holdsLane")


# ------------------------------------------------------------------ a press link needs a string label

def case_press_link_label_is_a_string():
    # A link counts when it has a url, but the page draws a link only when its label is a string too
    # (skills/waiting-page/page.html isLink). A press whose only link has no
    # string label shows the owner no link, so it is refused. A link to the page with an empty-string label is still
    # a string, so it passes. A labelled link to another PR does not stand for the page, so an unlabelled link to
    # the page beside it does not save the press.
    pr, other = "https://github.com/shivinate7/home/pull/374", "https://github.com/shivinate7/home/pull/999"
    # The option names the pr URL's number, so a link must reach that page: with no number in the text any link passes.
    base = copy.deepcopy(ITEM92["options"])
    base[1].update(label="Merge PR #374", how="Press Merge in GitHub.")

    def with_links(links):
        options = copy.deepcopy(base)
        options[1]["links"] = links
        return entry_of(page_item(options=options))

    page("a press whose link to the page has no label is refused as press-link", "set",
         with_links([{"url": pr}]), ("press-link", None))
    page("a press whose link to the page has a null label is refused as press-link", "set",
         with_links([{"label": None, "url": pr}]), ("press-link", None))
    page("a press whose link to the page has a numeric label is refused as press-link", "set",
         with_links([{"label": 5, "url": pr}]), ("press-link", None))
    page("a press with an unlabelled link to the page beside a labelled link to another PR is refused as press-link",
         "set", with_links([{"label": "the other pull request", "url": other}, {"url": pr}]), ("press-link", None))
    page("a press with only a labelled link to another PR stays refused as press-link", "set",
         with_links([{"label": "the other pull request", "url": other}]), ("press-link", None))
    page("a press whose link to the page has an empty-string label passes", "set",
         with_links([{"label": "", "url": pr}]), None)
    task = task_item(["Open PR #374 on GitHub", "Press Merge."], links=[{"url": pr}])
    page("a task whose step presses in GitHub, with an unlabelled link to the page, is refused as press-link", "set",
         entry_of(task), ("press-link", None))
    page("a task whose step presses in GitHub, with a labelled link to the page, passes", "set",
         entry_of(dict(task, links=[{"label": "PR #374", "url": pr}])), None)


# ------------------------------------------------------------------ a press link that is not a list; a partial edit of the Why yours line
#
# Each case below is also a pytest test (the test_ wrappers after it). A check the case records as failed fails
# its test, by the check's name, so one runner and main() judge the same cases.

def _judged(case):
    """Run one case under pytest: each check it records as failed fails the test, by the check's name."""
    before = len(FAILED)
    case()
    assert len(FAILED) == before, "; ".join(FAILED[before:])


def case_press_link_links_not_a_list_on_a_step():
    """`links` set to true or to a number is no list of links. The step's press has no valid link, so the hit fires as it
    does for a missing link. It must not crash or fail open."""
    for links in (True, 5):
        page("a task step that presses in GitHub, with links %r, is refused as press-link" % (links,), "set",
             entry_of(task_item(["Press Merge in GitHub on the pull request."], links=links)),
             ("press-link", "no link to the page"))


def case_press_link_links_not_a_list_on_an_option():
    """The same for an option's links: true or a number is no valid link, so the press is refused as press-link."""
    for links in (True, 5):
        press = copy.deepcopy(ITEM92["options"])
        press[1].update(label="Press Merge in GitHub", how="Do it by hand.", links=links)
        page("an option that presses in GitHub, with links %r, is refused as press-link" % (links,), "set",
             entry_of(page_item(options=press)), ("press-link", "no link to the page"))


def case_task_str_replace_removes_only_the_label():
    """A str_replace that removes only the Why yours label leaves a line with no label. It is refused as task-names-check."""
    page("a str_replace that removes only the Why yours label is refused as task-names-check", "str_replace",
         {"collection": "items", "doc_id": DOC, "field": "context", "old_str": "Why yours:", "new_str": ""},
         ("task-names-check", None))


def case_str_replace_blank_prose_line_passes():
    """A str_replace that blanks one plain prose line of a decision's context passes. The guard cannot read the stored
    item, so a blank replacement that removes no Why yours line is no task-names-check fault."""
    page("a str_replace that blanks one plain prose line in a decision's context passes", "str_replace",
         {"collection": "items", "doc_id": DOC, "field": "context",
          "old_str": "The lane merge-role-allow would do it.", "new_str": ""}, None)


def case_task_str_replace_rewords_the_reason():
    """A control: an edit that keeps the label and rewords the text after it keeps the line, so it passes."""
    page("a str_replace that rewords the Why yours reason and keeps the label passes", "str_replace",
         {"collection": "items", "doc_id": DOC, "field": "context",
          "old_str": "Why yours: a session on your computer was asked first",
          "new_str": "Why yours: a session on your desk was asked first"}, None)


def case_task_str_replace_renames_the_label():
    """A str_replace that renames the Why yours label to Why mine takes the label away, so it is refused as task-names-check."""
    page("a str_replace that renames the Why yours label to Why mine is refused as task-names-check", "str_replace",
         {"collection": "items", "doc_id": DOC, "field": "context", "old_str": "Why yours:", "new_str": "Why mine:"},
         ("task-names-check", None))


def case_task_str_replace_prose_label_passes():
    """A prose mention of the label, not at a line start, is no Why yours line. Editing that prose passes."""
    page('a str_replace that changes prose the "Why yours:" label to the label passes', "str_replace",
         {"collection": "items", "doc_id": DOC, "field": "context",
          "old_str": 'the "Why yours:" label', "new_str": "the label"}, None)


def test_press_link_links_true_or_a_number_on_a_step_is_no_link():
    _judged(case_press_link_links_not_a_list_on_a_step)


def test_press_link_links_true_or_a_number_on_an_option_is_no_link():
    _judged(case_press_link_links_not_a_list_on_an_option)


def test_task_str_replace_removing_only_the_label_is_refused():
    _judged(case_task_str_replace_removes_only_the_label)


def test_str_replace_blank_prose_line_in_a_decision_passes():
    _judged(case_str_replace_blank_prose_line_passes)


def test_task_str_replace_rewording_the_reason_passes():
    _judged(case_task_str_replace_rewords_the_reason)


def test_task_str_replace_renaming_the_label_is_refused():
    _judged(case_task_str_replace_renames_the_label)


def test_task_str_replace_prose_label_mention_passes():
    _judged(case_task_str_replace_prose_label_passes)


def case_item_stray_field_refused_from_a_record_branch_checkout():
    """The page checks run from a checkout on the record branch. Its extras file is on origin/main
    only, and the page reads it from there (lint/layout.py waiting_page), so an item set with a stray top-level field is
    refused as item-field-rendered, as at the page's own checkout. Scope first: when the page url reads as unknown, no
    page check runs and the case stops at that one cause."""
    repo = tcj.record_branch_checkout()
    check("scope: the record-branch checkout holds no extras file",
          not os.path.isfile(os.path.join(repo, ".claude", "layout-extras.json")), "the checkout holds the extras file")
    tool_input = {"action": "set", "url": PAGE_URL, "collection": tcj.PAGE_ITEMS, "doc_id": DOC, "data": page_item(focus="#fill")}
    named = call("is_waiting_page", tool_input, repo) is True
    check("scope: the page url names the page at the record-branch checkout", named,
          "the page url reads as unknown at a checkout with no extras file, so no page check runs")
    if not named:
        return
    got = call("page_item_hit", tool_input, repo)
    verdict("page_item_hit at the record-branch checkout: a stray top-level field is refused", got[0], ("item-field-rendered", "focus"))
    control = call("page_item_hit", dict(tool_input), tcj.PAGE_REPO)
    verdict("control: the same stray field at the page's own checkout is refused", control[0], ("item-field-rendered", "focus"))


# ------------------------------------------------------------------ a decision on another repo is checked with that repo
#
# Rule question-checked-with-repo (CROSS_REPO_RULE). An open decision or task set that names a `repo` other than the
# page's repo needs a session-shaped `checked_with`, and a `checked_with` equal to the session id in `owner` is refused.
# `repo` is required on an open decision or task set: a set with no repo is refused. The page's repo is the origin of
# the checkout the write is judged at (cwd). With no cwd, or no origin, it is None: there is nothing to compare, so a
# foreign repo passes, but a set with no repo is still refused.
# The fixture is the incident item ma144-tab-bar (mailaudit #144) as it was written, opened, with the repo field.

CROSS_REPO_RULE = "question-checked-with-repo"
PAGE_REPO_NAME = "shivinate7/claude-settings"  # the page's repo: the origin of tcj.origin_page_repo()
OTHER_REPO = "shivinate7/mailaudit"
CHECKED = "session_013ABCdefGHI"
MA144_ID = "ma144-tab-bar"
MA144_OWNER_SESSION = "session_013NEJKymmzw37seAr3Qq5nv"  # the session id in MA144's owner field
VI_FRAGMENTS = (r"\brepo\b", r"shivinate7/claude-settings")

MA144 = json.loads(r'''{"added":"2026-11-08T04:12:00Z","context":"Goal: MANIFEST works well on the open iPhone Duo, in the Card in Hand design you picked on 2026-10-27 12:25 CDT.\nProblem (rule): degen puts its tab bar under the left page. The design lane's pick departs from that ruling, so it needs your word.\nBased on (read): README.md:12, choice 3.\nDeparts from: degen's Duo layout, tab bar under the left page — MANIFEST puts it under the right page.","designs":[{"drawn":951,"file":"docs/design/duo-card-in-hand/png/3-a.png","label":"Under the right page","option":"a","slug":"ma144-3-a"},{"drawn":951,"file":"docs/design/duo-card-in-hand/png/3-b.png","label":"Under the left page, on the keys","option":"b","slug":"ma144-3-b"},{"drawn":951,"file":"docs/design/duo-card-in-hand/png/3-c.png","label":"Under the left page, under the keys","option":"c","slug":"ma144-3-c"}],"home":"mailaudit #144","id":"ma144-tab-bar","kind":"decision","look":true,"n":389,"options":[{"design":"ma144-3-a","gain":"It never moves, and it shows while you type.","how":"The tab bar stays under the right page in every pose.","key":"a","label":"Under the right page, always","lose":"Degen puts it on the left, so the two apps differ."},{"design":"ma144-3-b","gain":"Same side as degen.","how":"The tab bar sits under the left page and rides on top of the keys.","key":"b","label":"Under the left page, on top of the keys","lose":"It jumps 256 pt each time the keys move."},{"design":"ma144-3-c","gain":"Same as degen.","how":"The tab bar sits under the left page, below the keys.","key":"c","label":"Under the left page, under the keys, as degen does","lose":"You must drop the keys to change tabs."}],"owner":"batch runner 9 (session_013NEJKymmzw37seAr3Qq5nv)","pick":"a","ref":"mailaudit #144 (Duo round 2, Card in Hand; branch design/duo-round2, head 441b4e46d); its README, section Choices","short":"Duo tab bar place","status":"open","title":"Duo tab bar: where does it sit?","why":"The design lane picks a: it never moves, and it shows while you type."}''')


def ma144(repo=OTHER_REPO, checked=None, **over):
    """The incident item, judged on `repo` (None leaves the field out). `checked` sets checked_with (None leaves it
    out, "" sets it empty). `over` sets or replaces any other field."""
    item = copy.deepcopy(MA144)
    item["context"] = item["context"] + "\n" + WAITING  # the incident item predates the Waiting on line
    if repo is not None:
        item["repo"] = repo
    if checked is not None:
        item["checked_with"] = checked
    item.update(over)
    return tcj.with_frozen_fields(item)  # MA144 is the record as written; its options get the ids and shown a write carries


def ma144_write(**over):
    """The `set` entry for the incident item, as the page's ArtifactData call carries it."""
    return entry_of(ma144(**over), doc_id=MA144_ID)


def cross(name, op, data, page_repo, fragments=None):
    """cross_repo_hit's result: None for a pass, else a reason that matches every regex in `fragments`. A missing
    function returns the MISSING sentinel, which fails the check by name."""
    got = call("cross_repo_hit", op, data, page_repo)
    if fragments is None:
        check("cross_repo_hit: " + name, got is None, "want a pass (None), got %r" % (got,))
    else:
        ok = isinstance(got, str) and all(re.search(f, got, re.I) for f in fragments)
        check("cross_repo_hit: " + name, ok, "want a reason naming %s, got %r" % (list(fragments), got))


def at_page(name, op, entry, cwd, fragments=None):
    """One page write judged at `cwd` by question_form.item_hit and by guard.data_tool_hit. A pass is ("", ""). A
    refusal is the cross-repo rule, with a reason that matches every regex in `fragments`. The page's repo is the
    origin of `cwd`'s checkout, so only a cwd with an origin reaches the rule."""
    tool_input = dict(entry, url=PAGE_URL, action=op)
    surfaces = (("item_hit", call("item_hit", op, entry, cwd)), ("guard", guard.data_tool_hit(tool_input, cwd)))
    for surface, got in surfaces:
        label = "%s at cwd: %s" % (surface, name)
        if fragments is None:
            check(label, got == ("", ""), "want a pass, got %r" % (got,))
        else:
            ok = got[0] == CROSS_REPO_RULE and all(re.search(f, str(got[1]), re.I) for f in fragments)
            check(label, ok, "want %s naming %s, got %r" % (CROSS_REPO_RULE, list(fragments), got))


def case_cross_repo_missing_checked_with():
    """(i) An open decision on another repo with no checked_with is refused, and the reason names checked_with. On
    main the write is refused as an unknown field, so only the new rule's reason passes this case."""
    cross("(i) no checked_with", "set", ma144(), PAGE_REPO_NAME, ("checked_with",))
    cross("(i) empty checked_with", "set", ma144(checked=""), PAGE_REPO_NAME, ("checked_with",))
    at_page("(i) no checked_with", "set", ma144_write(), tcj.origin_page_repo(), ("checked_with",))


def case_cross_repo_checked_with_passes():
    """(ii) A session-shaped checked_with on another repo's decision passes."""
    cross("(ii) session-shaped checked_with", "set", ma144(checked=CHECKED), PAGE_REPO_NAME)
    at_page("(ii) session-shaped checked_with", "set", ma144_write(checked=CHECKED), tcj.origin_page_repo())


def case_cross_repo_same_repo_passes():
    """(iii) A decision on the page's own repo passes with no checked_with."""
    cross("(iii) repo is the page repo", "set", ma144(repo=PAGE_REPO_NAME), PAGE_REPO_NAME)
    at_page("(iii) repo is the page repo", "set", ma144_write(repo=PAGE_REPO_NAME), tcj.origin_page_repo())


def case_cross_repo_compares_lowercase():
    """(iv) The page's repo in other case passes. Only the case differs, so the compare folds case."""
    cross("(iv) Shivinate7/Claude-Settings is the page repo", "set", ma144(repo="Shivinate7/Claude-Settings"),
          PAGE_REPO_NAME)
    at_page("(iv) Shivinate7/Claude-Settings is the page repo", "set",
            ma144_write(repo="Shivinate7/Claude-Settings"), tcj.origin_page_repo())


def case_cross_repo_no_page_repo_passes():
    """(v) With no page repo the compare is skipped, so a foreign repo with no checked_with passes: a direct call with
    page_repo None, and a write judged at a checkout with no origin (tcj.PAGE_REPO), which reads as no page repo. A set
    with no repo is still refused (case_cross_repo_required_when_page_repo_unknown)."""
    cross("(v) page_repo None", "set", ma144(), None)
    at_page("(v) checkout with no origin", "set", ma144_write(), tcj.PAGE_REPO)


def case_cross_repo_required():
    """(vi) repo is required on an open decision or task set. A set with no repo is refused, and the reason names
    `repo` and the page's own repo, so the writer fixes it in one try."""
    cross("(vi) no repo", "set", ma144(repo=None), PAGE_REPO_NAME, VI_FRAGMENTS)
    at_page("(vi) no repo", "set", ma144_write(repo=None), tcj.origin_page_repo(), VI_FRAGMENTS)


def case_cross_repo_checked_with_not_the_owner():
    """(vii) A checked_with equal to the session id in owner is refused: the owner's own session did not check."""
    cross("(vii) checked_with is the owner's session", "set", ma144(checked=MA144_OWNER_SESSION), PAGE_REPO_NAME,
          ("checked_with",))
    at_page("(vii) checked_with is the owner's session", "set", ma144_write(checked=MA144_OWNER_SESSION),
            tcj.origin_page_repo(), ("checked_with",))


def case_cross_repo_str_replace_not_judged():
    """(viii) A str_replace on context is not judged by this rule, whatever repo it carries. A str_replace on repo or
    checked_with is judged (case_cross_repo_str_replace_on_repo_and_checked_with)."""
    cross("(viii) str_replace with a foreign repo", "str_replace",
          {"repo": OTHER_REPO, "kind": "decision", "status": "open"}, PAGE_REPO_NAME)
    at_page("(viii) str_replace on context", "str_replace",
            entry_of(None, doc_id=MA144_ID, field="context", old_str="README.md:12, choice 3.",
                     new_str="README.md:12, choice 3, and the Duo sizes."), tcj.origin_page_repo())


def case_cross_repo_update_carrying_repo():
    """(ix) An update that carries repo is judged as a set is. It names only its own fields, so the stored kind is
    unseen and the repo alone decides. An update that carries no repo passes."""
    cross("(ix) update with a foreign repo, no checked_with", "update", {"repo": OTHER_REPO}, PAGE_REPO_NAME,
          ("checked_with",))
    cross("(ix) update with no repo", "update", {"title": MA144["title"]}, PAGE_REPO_NAME)
    at_page("(ix) update with a foreign repo, no checked_with", "update", entry_of({"repo": OTHER_REPO},
            doc_id=MA144_ID), tcj.origin_page_repo(), ("checked_with",))


def case_cross_repo_closed_item_passes():
    """(x) A closed item asks the owner nothing, so it passes whatever its repo."""
    cross("(x) closed decision on another repo", "set", ma144(status="closed"), PAGE_REPO_NAME)
    at_page("(x) closed decision on another repo", "set", ma144_write(status="closed"), tcj.origin_page_repo())


def case_cross_repo_task_names_checked_with():
    """(xi) An open task set on another repo is refused without checked_with, as a decision is. The task carries its
    Why yours line, so only this rule judges it."""
    task = task_item(["Open the page and answer item ma144-tab-bar."], repo=OTHER_REPO)
    cross("(xi) open task on another repo, no checked_with", "set", task, PAGE_REPO_NAME, ("checked_with",))
    at_page("(xi) open task on another repo, no checked_with", "set", entry_of(task, doc_id="ma144-task"),
            tcj.origin_page_repo(), ("checked_with",))


def case_cross_repo_malformed_checked_with():
    """(xii) A checked_with that is not session-shaped is refused, and the reason names checked_with."""
    cross("(xii) checked_with is not a session id", "set", ma144(checked="batch runner 9"), PAGE_REPO_NAME,
          ("checked_with",))
    at_page("(xii) checked_with is not a session id", "set", ma144_write(checked="batch runner 9"),
            tcj.origin_page_repo(), ("checked_with",))


# ------------------------------------------------------------------ question-checked-with-repo: the gaps of the rule
#
# One case per gap in the rule above, each with a concrete input. A red case is judged by the verdict it names, never by
# a crash. The writer's session is judged through cross_judged: a build with no session_id parameter is called with the
# signature it has, so its verdict shows instead of a TypeError. The case that needs the parameter asserts it first.

WRITER_SESSION = "session_01WRITERxyz"  # the record id of the session that files the item: the env's cse_<x> read as session_<x>, never the payload's UUID (case_cross_repo_writer_guard_path)
NO_REPO_FRAGMENTS = (r"\brepo\b",)  # the reason names `repo`; with no page repo it cannot name the page's own


def takes_session_id():
    """True when cross_repo_hit takes the writer's session_id."""
    fn = getattr(question_form, "cross_repo_hit", None)
    return fn is not None and "session_id" in inspect.signature(fn).parameters


def cross_judged(op, data, page_repo, session_id=None):
    """cross_repo_hit with the writer's session_id when the build takes one, else with the signature it has."""
    if takes_session_id():
        return call("cross_repo_hit", op, data, page_repo, session_id)
    return call("cross_repo_hit", op, data, page_repo)


def cross_as_writer(name, data, session_id, fragments=None):
    """cross_repo_hit on the page repo with the writer's session_id: a pass is None, a refusal a reason that matches
    every regex in `fragments`."""
    got = cross_judged("set", data, PAGE_REPO_NAME, session_id)
    if fragments is None:
        check("cross_repo_hit: " + name, got is None, "want a pass (None), got %r" % (got,))
    else:
        ok = isinstance(got, str) and all(re.search(f, got, re.I) for f in fragments)
        check("cross_repo_hit: " + name, ok, "want a reason naming %s, got %r" % (list(fragments), got))


def cross_format(name, data, page_repo=PAGE_REPO_NAME):
    """A repo that is not owner/name: the reason is the format reason, which names owner/name and not checked_with."""
    got = call("cross_repo_hit", "set", data, page_repo)
    ok = isinstance(got, str) and re.search(r"owner/name", got) is not None and re.search(r"checked_with", got) is None
    check("cross_repo_hit: " + name, ok, "want a format reason naming owner/name and not checked_with, got %r" % (got,))


def case_cross_repo_open_filter_is_the_one_home():
    """(xiii) The open filter is the one home _open_decision: a set with no kind is a decision, and a status other than
    closed is still open. Each of these sets, on another repo with no checked_with, is refused."""
    no_kind = ma144()
    no_kind.pop("kind")
    cross("(xiii) a set with no kind, on another repo, no checked_with", "set", no_kind, PAGE_REPO_NAME,
          ("checked_with",))
    at_page("(xiii) a set with no kind, at the page's checkout", "set", entry_of(no_kind, doc_id=MA144_ID),
            tcj.origin_page_repo(), ("checked_with",))
    cross("(xiii) status Open", "set", ma144(status="Open"), PAGE_REPO_NAME, ("checked_with",))
    cross("(xiii) status pending", "set", ma144(status="pending"), PAGE_REPO_NAME, ("checked_with",))
    at_page("(xiii) status pending, at the page's checkout", "set", ma144_write(status="pending"),
            tcj.origin_page_repo(), ("checked_with",))


def case_cross_repo_open_filter_controls():
    """(xiii controls) A set with no status is open, so it is judged. A closed set with no kind is not open, so it
    passes. Both hold with or without the fix."""
    no_status = ma144()
    no_status.pop("status")
    cross("(xiii control) a set with no status is open, no checked_with", "set", no_status, PAGE_REPO_NAME,
          ("checked_with",))
    closed_no_kind = ma144(status="closed")
    closed_no_kind.pop("kind")
    cross("(xiii control) a closed set with no kind passes", "set", closed_no_kind, PAGE_REPO_NAME)


def case_cross_repo_str_replace_on_repo_and_checked_with():
    """(xiv) A str_replace on `repo` or `checked_with` changes the cross-repo verdict, which the page cannot see, so it
    is refused as this rule, whatever the page's repo is. The first two writes are judged with no cwd, which pins the
    unknown-page-repo verdict."""
    page("(xiv) a str_replace on repo that swaps in the page's own repo", "str_replace",
         entry_of(None, doc_id=MA144_ID, field="repo", old_str=OTHER_REPO, new_str=PAGE_REPO_NAME),
         (CROSS_REPO_RULE, "repo"))
    page("(xiv) a str_replace on checked_with", "str_replace",
         entry_of(None, doc_id=MA144_ID, field="checked_with", old_str=CHECKED, new_str=WRITER_SESSION),
         (CROSS_REPO_RULE, "checked_with"))
    # The same writes at the page's checkout, where the stored repo is judged by the rule's compare: the bypass is a
    # set that names the page's own repo, then a str_replace that makes it foreign with no checked_with.
    at_page("(xiv) a str_replace on repo, the page's own repo to a foreign one", "str_replace",
            entry_of(None, doc_id=MA144_ID, field="repo", old_str=PAGE_REPO_NAME, new_str=OTHER_REPO),
            tcj.origin_page_repo(), ("repo",))
    at_page("(xiv) a str_replace on repo, a foreign repo to the page's own", "str_replace",
            entry_of(None, doc_id=MA144_ID, field="repo", old_str=OTHER_REPO, new_str=PAGE_REPO_NAME),
            tcj.origin_page_repo(), ("repo",))
    at_page("(xiv) a str_replace on checked_with", "str_replace",
            entry_of(None, doc_id=MA144_ID, field="checked_with", old_str=CHECKED, new_str=WRITER_SESSION),
            tcj.origin_page_repo(), ("checked_with",))


def case_cross_repo_required_when_page_repo_unknown():
    """(xv) `repo` is required on a set: cross_repo_hit called with page_repo None refuses a set with no repo, or an
    empty one, and the reason names `repo`. A write judged at a checkout with no origin is not refused for a missing
    repo (see the ruling below). The origin checkout pins the requirement end to end."""
    cross("(xv) no repo, page repo unknown", "set", ma144(repo=None), None, NO_REPO_FRAGMENTS)
    cross("(xv) empty repo, page repo unknown", "set", ma144(repo=""), None, NO_REPO_FRAGMENTS)
    # With the page repo unknown, item_hit does not judge a missing repo: no compare can run.
    at_page("(xv) no repo, a checkout with no origin passes", "set", ma144_write(repo=None), tcj.PAGE_REPO)
    at_page("(xv) no repo, at the page's checkout with an origin", "set", ma144_write(repo=None),
            tcj.origin_page_repo(), NO_REPO_FRAGMENTS)


def case_cross_repo_malformed_repo_is_a_format_refusal():
    """(xvi) A repo that is not owner/name is refused with the format reason. shivinate7/claude-settings.git passes the
    repo-name pattern, so it is judged as a repo off the page's own and asks for checked_with."""
    cross_format("(xvi) repo shivinate7/claude-settings.git, no checked_with",
                 ma144(repo="shivinate7/claude-settings.git"))
    cross_format("(xvi) repo shivinate7/claude-settings.git, a session-shaped checked_with",
                 ma144(repo="shivinate7/claude-settings.git", checked=CHECKED))
    at_page("(xvi) repo shivinate7/claude-settings.git, at the page's checkout", "set",
            ma144_write(repo="shivinate7/claude-settings.git"), tcj.origin_page_repo(), (r"owner/name",))


def case_cross_repo_malformed_repo_controls():
    """(xvi controls) q_max and a URL fail the repo-name pattern, so they already get the format reason. They hold with
    or without the fix."""
    cross_format("(xvi control) repo q_max", ma144(repo="q_max"))
    cross_format("(xvi control) repo https://github.com/a/b", ma144(repo="https://github.com/a/b"))


def case_cross_repo_writer_session_is_not_the_checker():
    """(xvii) A checked_with equal to the writer's own session is refused: the session that files the item did not
    check with the other repo. The owner here is the coordinator, so only the writer's session can refuse it."""
    check("cross_repo_hit takes session_id (xvii)", takes_session_id(),
          "cross_repo_hit has no session_id parameter, so a checked_with equal to the writer's session is not refused")
    cross_as_writer("(xvii) checked_with is the writer's session, owner coordinator",
                    ma144(checked=WRITER_SESSION, owner="coordinator"), WRITER_SESSION, ("checked_with",))


def case_cross_repo_writer_session_controls():
    """(xvii controls) A checked_with that differs from the writer's session passes. With no session id, a checked_with
    equal to a session id passes, since the writer's refusal does not apply. Both hold with or without the fix."""
    cross_as_writer("(xvii control) checked_with is another session, the writer is WRITER_SESSION",
                    ma144(checked=CHECKED, owner="coordinator"), WRITER_SESSION)
    cross_as_writer("(xvii control) no session id, checked_with equal to WRITER_SESSION passes",
                    ma144(checked=WRITER_SESSION, owner="coordinator"), None)


# ------------------------------------------------------------------ the writer's session, through the guard's dispatch
#
# Rule question-checked-with-repo, the writer's own session. The hook payload's session_id is the local session's UUID.
# A cloud session's record id is the env CLAUDE_CODE_REMOTE_SESSION_ID (cse_<x>, read as session_<x> by
# override.remote_session_id). The writer's refusal compares checked_with with that record id. The cases below run
# guard.judge(payload) in process, as the hook runs it, so the session id has to travel from the payload and the env
# through the guard's dispatch into page_item_hit. The cases above that call cross_repo_hit with a session id directly
# cannot show that.

LANE_ENV = "CLAUDE_CODE_REMOTE_SESSION_ID"
CLOUD_LANE = "cse_013TESTabc"  # this cloud session's env value
CLOUD_RECORD = "session_013TESTabc"  # the same session's record id: the writer's session id in checked_with
OTHER_SESSION = "session_013OTHERxyz"  # another session's record id
LOCAL_UUID = "60f6df14-79ff-4a1e-9c2b-5d7e8f901a2b"  # the hook payload's session_id: a UUID, not a record id


def writer_input(checked=None, **over):
    """The tool_input of one `set` on the incident item, as ArtifactData sends it, with checked_with set to `checked`
    (None leaves it out). `over` sets or replaces any other field of the item."""
    return dict(ma144_write(checked=checked, **over), url=PAGE_URL, action="set")


def guard_refusal(tool_input, lane_env):
    """The reason guard.judge prints for one ArtifactData call at the page's checkout, with the payload's session_id
    LOCAL_UUID and CLAUDE_CODE_REMOTE_SESSION_ID set to lane_env (None unsets it: a local session). None when the
    call passes. guard.judge exits through refuse(), which prints the deny JSON, so the print is what is read."""
    payload = {"tool_name": "ArtifactData", "hook_event_name": "PreToolUse", "cwd": tcj.origin_page_repo(),
               "session_id": LOCAL_UUID, "tool_input": tool_input}
    printed = io.StringIO()
    with mock.patch.dict(os.environ):  # the env is put back as it was on exit
        if lane_env is None:
            os.environ.pop(LANE_ENV, None)
        else:
            os.environ[LANE_ENV] = lane_env
        try:
            with contextlib.redirect_stdout(printed):
                guard.judge(payload)
        except SystemExit:
            pass
        except Exception as exc:  # a crash is a wrong verdict, shown by name
            return "RAISED %s: %s" % (type(exc).__name__, exc)
    text = printed.getvalue().strip()
    return json.loads(text)["hookSpecificOutput"]["permissionDecisionReason"] if text else None


def writer_verdict(name, reason, refused):
    """refused: the reason names the rule and `checked_with`. Else the call passes, with no refusal printed."""
    if refused:
        ok = isinstance(reason, str) and CROSS_REPO_RULE in reason and "checked_with" in reason
        check(name, ok, "want %s naming checked_with, got %r" % (CROSS_REPO_RULE, reason))
    else:
        check(name, reason is None, "want a pass (no refusal), got %r" % (reason,))


def case_cross_repo_writer_guard_path():
    """(xviii) guard.judge refuses a checked_with equal to the writer's own session. The cloud session's record id comes
    from CLAUDE_CODE_REMOTE_SESSION_ID (cse_<x> read as session_<x>), not from the payload's UUID. The red: on the
    build that reads the payload's UUID, the writer's session is never the record id, so the refusal does not fire.
    The controls: another session passes; a local session (env unset) has no writer's session to refuse; a missing
    checked_with is refused end to end (green on the build that has this rule: it shows the guard dispatches it)."""
    writer_verdict("(xviii) guard: checked_with is this cloud session's record id, env cse_013TESTabc",
                   guard_refusal(writer_input(checked=CLOUD_RECORD, owner="coordinator"), CLOUD_LANE), refused=True)
    writer_verdict("(xviii control) guard: checked_with is another session, env cse_013TESTabc",
                   guard_refusal(writer_input(checked=OTHER_SESSION, owner="coordinator"), CLOUD_LANE), refused=False)
    writer_verdict("(xviii control) guard: local session, env unset, checked_with is the record id",
                   guard_refusal(writer_input(checked=CLOUD_RECORD, owner="coordinator"), None), refused=False)
    writer_verdict("(xviii control) guard: no checked_with is refused, env cse_013TESTabc",
                   guard_refusal(writer_input(owner="coordinator"), CLOUD_LANE), refused=True)


def case_cross_repo_writer_page_item_hit():
    """(xix) page_item_hit takes the writer's session id and refuses a checked_with equal to it. It is called direct, so a
    build that drops the id on the way (question_form.py, item_hit's cross-repo call) fails here too, not only in the
    guard case above. Green on the build that threads the id: this case holds the threading in place."""
    got = call("page_item_hit", writer_input(checked=CLOUD_RECORD, owner="coordinator"), tcj.origin_page_repo(),
               CLOUD_RECORD)
    hit = got[0] if isinstance(got, tuple) and got else got
    ok = isinstance(hit, tuple) and len(hit) == 2 and hit[0] == CROSS_REPO_RULE and "checked_with" in str(hit[1])
    check("page_item_hit: checked_with equal to the writer's session is refused, naming checked_with", ok,
          "want %s naming checked_with, got %r" % (CROSS_REPO_RULE, hit))
    got = call("page_item_hit", writer_input(checked=OTHER_SESSION, owner="coordinator"), tcj.origin_page_repo(),
               CLOUD_RECORD)
    hit = got[0] if isinstance(got, tuple) and got else got
    check("control: page_item_hit, checked_with another session passes", hit == ("", ""),
          "want a pass, got %r" % (hit,))


def model_calls_of_call_judge(checked):
    """How many model calls hooks/call_judge.py makes for one ArtifactData write of the page, the payload's session_id
    LOCAL_UUID and CLAUDE_CODE_REMOTE_SESSION_ID set to CLOUD_LANE. A write that a rule refuses makes none."""
    payload = {"tool_name": "ArtifactData", "hook_event_name": "PreToolUse", "cwd": tcj.origin_page_repo(),
               "session_id": LOCAL_UUID, "tool_input": writer_input(checked=checked, owner="coordinator")}
    with mock.patch.dict(os.environ, {LANE_ENV: CLOUD_LANE}):
        run = tcj.run_hook(json.dumps(payload))
    return len(run.calls)


def case_cross_repo_writer_call_judge():
    """(xxi) call_judge.py reads the writer's session the way guard.py does. A checked_with equal to the cloud session's
    record id is a hit, so call_judge asks no model about the write. The red: on a build that passes the payload's UUID,
    the write is no hit there and the model is asked. The control, another session's checked_with, is asked, so the
    model call is seen."""
    refused = model_calls_of_call_judge(CLOUD_RECORD)
    check("(xxi) call_judge: checked_with is this cloud session's record id, no model call", refused == 0,
          "want no model call for a write the rule refuses, got %d call(s)" % refused)
    asked = model_calls_of_call_judge(OTHER_SESSION)
    check("(xxi control) call_judge: checked_with is another session, the model is asked", asked > 0,
          "want a model call for a write no rule refuses, got %d" % asked)


def case_cross_repo_update_checked_with_needs_repo():
    """(xviii) An update that carries checked_with but no repo is refused, and the reason names `repo`. The stored repo
    is unseen, so a checked_with alone cannot be judged against it. The controls carry repo, so they hold with or
    without this refusal."""
    cross("(xx) update with checked_with, no repo", "update", {"checked_with": CHECKED}, PAGE_REPO_NAME, ("`repo`",))
    at_page("(xx) update with checked_with, no repo", "update", entry_of({"checked_with": CHECKED}, doc_id=MA144_ID),
            tcj.origin_page_repo(), ("`repo`",))
    cross("(xx control) update with a foreign repo and checked_with", "update",
          {"repo": OTHER_REPO, "checked_with": CHECKED}, PAGE_REPO_NAME)
    cross("(xx control) update with the page's own repo and checked_with", "update",
          {"repo": PAGE_REPO_NAME, "checked_with": CHECKED}, PAGE_REPO_NAME)


# ------------------------------------------------------- judged_item_writes reads a file_path at the payload cwd
#
# An items write whose data is a file (`file_path`, no `data`) is read by _write_data against the cwd it is given. The
# model review reads its writes through judged_item_writes, which must take the payload cwd as item_hit does. Each file
# name is unique and absent from the process cwd, so a read that finds the file can only come from the cwd join.
def judged_items(writes, cwd):
    """judged_item_writes(writes, cwd). A build whose function takes no cwd is called with the writes alone, so its
    relative write fails an assert, never a TypeError."""
    if "cwd" in inspect.signature(question_form.judged_item_writes).parameters:
        return question_form.judged_item_writes(writes, cwd)
    return question_form.judged_item_writes(writes)


def write_json_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def judged_folder():
    """The payload cwd of these cases: a folder in this run's temp root, swept with the run."""
    folder = os.path.join(tcj.ROOT, "judged-cwd")
    os.makedirs(folder, exist_ok=True)
    return folder


def case_judged_relative_file_path_read_at_cwd():
    """(judged cwd) A set whose data is a file named by a relative file_path is returned when the payload cwd holds the
    file. On main the path is read against the process cwd, finds nothing, and the write is dropped, so no model review
    sees it."""
    folder, item, name = judged_folder(), tcj.good_page_item(), "judged-relative-item.json"
    write_json_file(os.path.join(folder, name), item)
    check("judged cwd: the file is at the payload cwd", os.path.isfile(os.path.join(folder, name)), folder)
    check("judged cwd: no file of that name at the process cwd, so only a join to the payload cwd finds it",
          not os.path.exists(name), os.getcwd())
    got = judged_items([("set", {"collection": tcj.PAGE_ITEMS, "doc_id": "p1", "file_path": name})], folder)
    check("judged cwd: the relative write is returned, its data read from the payload cwd",
          len(got) == 1 and got[0].get("doc_id") == "p1" and got[0].get("data") == item,
          "got %r: the path was read against the process cwd, so the write was dropped" % (got,))


def case_judged_absolute_and_empty_are_unchanged():
    """(judged cwd, control) An absolute file_path is read and returned with no cwd, as on main, and no writes
    judge to an empty list. Green before and after the fix."""
    folder, item = judged_folder(), tcj.good_page_item()
    path = os.path.join(folder, "judged-absolute-item.json")
    write_json_file(path, item)
    check("judged absolute: the file is at its absolute path", os.path.isabs(path) and os.path.isfile(path), path)
    got = question_form.judged_item_writes([("set", {"collection": tcj.PAGE_ITEMS, "doc_id": "p2", "file_path": path})])
    check("judged absolute: the write is returned, its data read from the absolute path",
          len(got) == 1 and got[0].get("doc_id") == "p2" and got[0].get("data") == item, got)
    empty = judged_items([], folder)
    check("judged empty: no writes judge to an empty list", empty == [], empty)


def case_judged_mixed_writes_all_returned():
    """(judged cwd, full list) An inline write, a relative file_path and an absolute file_path come back together, in
    order, from one call. On main the relative write, p4, is the one dropped."""
    folder, item = judged_folder(), tcj.good_page_item()
    name, abs_path = "judged-mixed-relative.json", os.path.join(folder, "judged-mixed-absolute.json")
    write_json_file(os.path.join(folder, name), item)
    write_json_file(abs_path, item)
    check("judged mixed: no file of the relative name at the process cwd", not os.path.exists(name), os.getcwd())
    c = tcj.PAGE_ITEMS
    writes = [("set", {"collection": c, "doc_id": "p3", "data": item}),
              ("set", {"collection": c, "doc_id": "p4", "file_path": name}),
              ("set", {"collection": c, "doc_id": "p5", "file_path": abs_path})]
    ids = [w.get("doc_id") for w in judged_items(writes, folder)]
    check("judged mixed: the inline, relative and absolute writes all come back, in order",
          ids == ["p3", "p4", "p5"],
          "doc ids %r: the relative write p4 is read against the process cwd and dropped" % (ids,))


# ------------------------------------------------------------------ stops: the entries Blocking counts are named in holds
#
# Design notes docs/design/session-role-sort-notes.md, ruling Q1 and point 1: `stops` is a list of what an answer stops, each entry a
# lane slug, a PR number or a step id. holds names them in words, so the two cannot drift. The rule id is not fixed by the
# brief, so each case takes any refusal, other than item-field-rendered, that names the entry it refuses.

STOPS_HOLDS = "Lane fix-proxy and PR #1201 wait on your word."
STOPS_NOT_A_REFUSAL = ("", "MISSING", "RAISED", "item-field-rendered")
_STOPS_PAGE = []


def stops_fields_page():
    """A page whose itemFields block is the real page's list plus `stops`. The list is read from the page, never copied, and
    the seam GUARD_ITEM_FIELDS_PAGE points the check at it, so a stops write is judged by the stops rule, not by
    item-field-rendered. The real page lists `stops` (page.html itemFields), and the seam writes that list as it is."""
    if not _STOPS_PAGE:
        fields = question_form._item_fields(question_form.ITEM_FIELDS_PAGE)
        check("stops: the page's itemFields list reads", fields is not None, "no itemFields list in the page")
        check("stops: the page's itemFields list names stops", "stops" in (fields or []), "the page does not list stops")
        path = os.path.join(RUN_FOLDER, "stops_fields_page.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write('<script type="application/json" id="itemFields">%s</script>' % json.dumps(fields or []))
        _STOPS_PAGE.append(path)
    return _STOPS_PAGE[0]


def stops_item(holds=None, stops=None):
    """A decision in the form. `holds` and `stops` are set when given and left out when None."""
    item = page_item(holds=holds, stops=stops)
    return {k: v for k, v in item.items() if not (k in ("holds", "stops") and v is None)}


def stops_refused(name, got, fragment):
    ok = got[0] not in STOPS_NOT_A_REFUSAL and fragment.lower() in str(got[1]).lower()
    check(name, ok, "want a refusal naming %r, got %r" % (fragment, got))


def stops_page(name, data, fragment=None, op="set"):
    """One page write judged by item_hit and by the guard, with the stops seam. A fragment is a refusal that names it;
    None is a pass. `op` is the write's verb: set by default, or update for a write that carries only the fields it changes."""
    with mock.patch.dict(os.environ, {question_form.ITEM_FIELDS_SEAM: stops_fields_page()}):
        for surface, got in (("page item_hit", call("item_hit", op, entry_of(data))),
                             ("page guard", guard_hit(op, entry_of(data)))):
            if fragment is None:
                check("%s: %s passes" % (surface, name), got == ("", ""), "want a pass, got %r" % (got,))
            else:
                stops_refused("%s: %s" % (surface, name), got, fragment)


def case_stops_names_each_entry_in_holds():
    """A lane is named by its slug in the words, a PR by "#N" or "PR N". A PR number is not named by a longer one that
    starts with it (#12 is not #1201), nor a lane slug by a longer slug (fix is not fix-proxy)."""
    stops_page("a lane entry that holds does not name", stops_item(holds="PR #1201 waits on your word.", stops=["lane fix-proxy"]), "fix-proxy")
    stops_page("a PR entry that holds does not name", stops_item(holds="Lane fix-proxy waits on your word.", stops=["PR #1201"]), "1201")
    stops_page("a second entry that holds does not name", stops_item(holds="Lane fix-proxy waits on your word.", stops=["lane fix-proxy", "PR #1201"]), "1201")
    stops_page("a PR number that is the start of the one holds names", stops_item(holds="Waits on PR #1201.", stops=["PR #12"]), "PR #12")
    stops_page("a lane slug that is the start of the one holds names", stops_item(holds="Lane fix-proxy waits on your word.", stops=["lane fix"]), "fix")


def case_stops_consistent_items_pass():
    """Controls: an item whose holds names every entry passes, with the PR written either way, and so does an item with
    neither field, or an empty list."""
    stops_page("holds names both entries", stops_item(holds=STOPS_HOLDS, stops=["lane fix-proxy", "PR #1201"]), None)
    stops_page("holds writes the PR as PR N", stops_item(holds="Lane fix-proxy and PR 1201 wait on your word.", stops=["lane fix-proxy", "PR #1201"]), None)
    stops_page("holds writes the PR as #N", stops_item(holds="Lane fix-proxy waits on #1201.", stops=["PR #1201"]), None)
    stops_page("an empty stops list with holds", stops_item(holds=STOPS_HOLDS, stops=[]), None)
    stops_page("neither holds nor stops", stops_item(), None)


def case_stops_item_passes_the_real_page_fields():
    """No seam: the check reads the real page's itemFields list, which lists `stops`, so a consistent stops item passes on
    both surfaces. A page that dropped `stops` from that list would refuse it as item-field-rendered, naming the field."""
    page("a consistent stops item passes the page's own field list", "set",
         entry_of(stops_item(holds=STOPS_HOLDS, stops=["lane fix-proxy", "PR #1201"])), None)


def case_stops_needs_holds_and_a_list():
    """stops with no holds, a stops that is not a list, and a repeated entry are each refused, naming the stops or the entry."""
    stops_page("stops with no holds", stops_item(stops=["lane fix-proxy"]), "stops")
    stops_page("stops that is a string, not a list", stops_item(holds=STOPS_HOLDS, stops="lane fix-proxy"), "stops")
    stops_page("a repeated entry", stops_item(holds=STOPS_HOLDS, stops=["lane fix-proxy", "lane fix-proxy"]), "fix-proxy")


def case_stops_refusal_prints_its_table_text():
    """A stops refusal prints its rule's text from question_form.PAGE_REASONS, the one table guard.py prints from (as
    case_page_reasons_are_one_table checks the other page rules)."""
    table = getattr(question_form, "PAGE_REASONS", None)
    if table is None:
        check("stops reason: question_form.PAGE_REASONS is the table of page reasons", False, MISSING)
        return
    tool_input = {"url": PAGE_URL, "action": "set", "collection": "items", "doc_id": DOC,
                  "data": stops_item(holds="PR #1201 waits on your word.", stops=["lane fix-proxy"])}
    with mock.patch.dict(os.environ, {question_form.ITEM_FIELDS_SEAM: stops_fields_page()}):
        rule = guard.data_tool_hit(tool_input, PAGE_REPO)[0]
        check("stops reason: the refused entry has a rule that is in the page reasons table",
              rule in table and rule not in STOPS_NOT_A_REFUSAL, "rule %r" % (rule,))
        if rule in table:
            printed = printed_reason(tool_input)
            check("stops reason: the refusal prints its rule's table text", table[rule] in printed, printed[:200])


def case_stops_update_judged_by_the_fields_it_carries():
    """An update that sets stops with no holds is refused, as a set is. An update that removes stops passes, and so does
    one that carries holds alone: the stored stops is unseen, so the update is judged by what it carries."""
    stops_page("an update that sets stops with no holds", {"stops": ["lane fix-proxy"]}, "stops", op="update")
    stops_page("an update that sets stops and holds that names both", {"stops": ["lane fix-proxy", "PR #1201"], "holds": STOPS_HOLDS},
               None, op="update")
    stops_page("an update that removes stops", {"stops": {"__delete__": True}}, None, op="update")
    stops_page("an update that carries holds only", {"holds": "Lane fix-proxy waits on your word."}, None, op="update")


def case_stops_batch_judged_per_write():
    """A batch that holds a stops write with no holds is refused by the stops rule. A batch of consistent stops writes passes."""
    def batch(writes):
        with mock.patch.dict(os.environ, {question_form.ITEM_FIELDS_SEAM: stops_fields_page()}):
            return page_batch(writes)
    good = {"op": "set", "collection": "items", "doc_id": "stops-batch-ok", "data": stops_item(holds=STOPS_HOLDS, stops=["lane fix-proxy", "PR #1201"])}
    bad = {"op": "set", "collection": "items", "doc_id": "stops-batch-bad", "data": stops_item(stops=["lane fix-proxy"])}
    verdict("page guard: a batch with a stops write and no holds is refused", batch([good, bad]),
            (getattr(question_form, "STOPS_RULE", "<STOPS_RULE missing from hooks/question_form.py>"), "stops"))
    verdict("page guard: a batch of consistent stops writes passes", batch([good]), None)


def case_stops_str_replace_on_holds_is_a_known_gap():
    """KNOWN GAP, pinned so it is on record: a str_replace that drops an entry from holds passes, since stops_hit judges a
    set and an update only, and the stored stops is unseen. This case passes today. A fix that judges the edit turns it red,
    and the case is re-pointed then."""
    page("KNOWN GAP: a str_replace that drops PR #1201 from holds passes while stops still lists it", "str_replace",
         {"collection": "items", "doc_id": DOC, "field": "holds", "old_str": STOPS_HOLDS,
          "new_str": "Lane fix-proxy waits on your word."}, None)
# ------------------------------------------------------------------ a decision states its recommendation, why, and what waits
#
# Rule question-form (decision question-form, the page's card). An open decision set or update shows a
# recommendation that names an option (`recommended`, else the old `pick`), a non-blank `why`, and a `Waiting on:`
# line in `context`. A closed item, another kind, and an update that carries none of these fields pass.
# The page draws the recommendation as visible text above the options, and never preselects one.

WAIT_LINE_TEXT = "Waiting on: nothing stopped; the lane acts next."
PLAIN_OPTIONS = [{k: v for k, v in option.items() if k != "widens"} for option in ITEM92["options"]]


def rec_item(context=None, options=None, **over):
    """A decision that passes the recommendation, why and Waiting on rules: page_item() with `recommended` a and no
    legacy `pick`. `context` replaces the whole context; `options` replaces the options. `over` sets a field, and a
    field set to None is left out, so a case drops one field and keeps the rest."""
    item = page_item(options=options, lines=None if context is None else [context])
    item.pop("pick", None)
    item["recommended"] = "a"
    for key, value in over.items():
        if value is None:
            item.pop(key, None)
        else:
            item[key] = value
    return item


def rec_page(name, op, entry, rule, fragments):
    """A page write judged by item_hit and by the guard. Both give `rule`, and the matched text names one of
    `fragments` (a word the refusal may carry, such as the pick's own name or the recommendation's)."""
    for surface, got in (("item_hit", call("item_hit", op, entry)), ("guard", guard_hit(op, entry))):
        ok = got[0] == rule and any(f in str(got[1]).lower() for f in fragments)
        check("page %s: %s" % (surface, name), ok, "want %s naming one of %r, got %r" % (rule, fragments, got))


def case_recommend_base_passes():
    # Scope before subject: the base decision passes, and each case below removes one part of it.
    page("a decision with a recommended key, a why and a Waiting on line passes", "set", entry_of(rec_item()), None)
    page("a Waiting on line that says nothing is stopped, and who acts next, passes", "set",
         entry_of(rec_item(context=form_text(waiting=WAIT_LINE_TEXT))), None)


def case_recommend_missing_or_unknown_is_refused():
    page("a set with no recommended and no pick is refused, naming the recommendation", "set",
         entry_of(rec_item(recommended=None)), (FORM_RULE, "recommend"))
    page("a set with a blank recommended is refused, naming the recommendation", "set",
         entry_of(rec_item(recommended="")), (FORM_RULE, "recommend"))
    page("a set whose recommended key names no option is refused, naming the recommendation", "set",
         entry_of(rec_item(recommended="z")), (FORM_RULE, "recommend"))


def case_legacy_pick_is_the_recommendation():
    # The red is the refusal: a pick that names no option is read as the recommendation and refused.
    # The control, green on the old code, is a pick that names an option: it is accepted as the recommendation.
    page("a legacy pick that names an option, with no recommended, passes", "set",
         entry_of(rec_item(recommended=None, pick="a")), None)
    rec_page("a legacy pick that names no option is refused, as the recommendation", "set",
             entry_of(rec_item(recommended=None, pick="z")), FORM_RULE, ("recommend", "pick"))


def case_why_is_required():
    page("a blank why is refused, naming why", "set", entry_of(rec_item(why="")), (FORM_RULE, "why"))
    page("a why of spaces only is refused, naming why", "set", entry_of(rec_item(why="   ")), (FORM_RULE, "why"))
    page("a decision with no why is refused, naming why", "set", entry_of(rec_item(why=None)), (FORM_RULE, "why"))


def case_waiting_on_line_is_required():
    page("a decision with no Waiting on line is refused, naming Waiting on", "set",
         entry_of(rec_item(context=form_text(waiting=None))), (FORM_RULE, "Waiting on"))
    page("a Waiting on line with no text after the colon is refused, naming Waiting on", "set",
         entry_of(rec_item(context=form_text(waiting="Waiting on:"))), (FORM_RULE, "Waiting on"))
    page("a Waiting on line of spaces only is refused, naming Waiting on", "set",
         entry_of(rec_item(context=form_text(waiting="Waiting on:    "))), (FORM_RULE, "Waiting on"))
    page("a Meanwhile line is no Waiting on line, and is refused, naming Waiting on", "set",
         entry_of(rec_item(context=form_text(waiting=None) + "\nMeanwhile: the lane keeps its work.")),
         (FORM_RULE, "Waiting on"))
    page("Waiting on words in prose, not at a line start, are no Waiting on line", "set",
         entry_of(rec_item(context=form_text(waiting=None) + "\nWE ARE WAITING ON YOU, nothing else.")),
         (FORM_RULE, "Waiting on"))


def case_update_judges_only_the_fields_it_carries():
    page("an update that carries context with no Waiting on line is refused, naming Waiting on", "update",
         entry_of({"kind": "decision", "context": form_text(waiting=None)}), (FORM_RULE, "Waiting on"))
    page("an update that blanks why is refused, naming why", "update",
         entry_of({"kind": "decision", "why": ""}), (FORM_RULE, "why"))
    page("an update that carries options and a recommended key that names no option is refused", "update",
         entry_of(tcj.with_frozen_fields({"kind": "decision", "options": copy.deepcopy(ITEM92["options"]),
                                          "recommended": "z"})), (FORM_RULE, "recommend"))
    page("an update that carries options and a recommended key that names an option passes", "update",
         entry_of(tcj.with_frozen_fields({"kind": "decision", "options": copy.deepcopy(ITEM92["options"]),
                                          "recommended": "a"})), None)
    page("an update that carries a why with words in it passes", "update",
         entry_of({"kind": "decision", "why": "A keeps the allow list to one form."}), None)


def case_kindless_update_with_a_goal_line_needs_the_waiting_line():
    # The guard cannot see the stored kind, so an update with no kind is a decision when its context carries a Goal
    # line: that line is the decision form. A context with no Goal line is a task's, and passes.
    page("a kindless update whose context has no Goal line (a task) passes", "update",
         entry_of({"context": TASK_WHY}), None)
    page("a kindless update whose context has a Goal line and a Waiting on line passes", "update",
         entry_of({"context": form_text()}), None)
    page("a kindless update whose context has a Goal line and no Waiting on line is refused, naming Waiting on",
         "update", entry_of({"context": form_text(waiting=None)}), (FORM_RULE, "Waiting on"))
    page("a kindless update with a Goal line and a blank Waiting on line is refused, naming Waiting on",
         "update", entry_of({"context": form_text(waiting="Waiting on:")}), (FORM_RULE, "Waiting on"))


def case_kindless_update_with_a_why_yours_line_is_a_task():
    # A kindless update whose context holds a Why yours line is a task, so it passes even when a Goal line opens it.
    # The mirror control: the same text with the Why yours line taken out has no task marker, and is a decision.
    task = "Goal: g\nWhy yours: y (measured 2026-11-10, x)\nSteps: s"
    page("a kindless update whose task context opens with a Goal line and holds a Why yours line passes", "update",
         entry_of({"context": task}), None)
    page("a kindless update whose task context opens with a lower-case goal: line passes", "update",
         entry_of({"context": task.replace("Goal:", "goal:")}), None)
    page("a kindless update whose task context opens with an indented Goal line passes", "update",
         entry_of({"context": task.replace("Goal:", "  Goal:")}), None)
    page("a kindless update with a Goal line and no Why yours line is refused, naming Problem", "update",
         entry_of({"context": "Goal: g\nSteps: s"}), (FORM_RULE, "Problem"))
    page("a kindless update with a Goal line, no Why yours line and no Waiting on line is refused, naming Waiting on",
         "update", entry_of({"context": form_text(waiting=None)}), (FORM_RULE, "Waiting on"))


def case_update_null_recommendation_is_refused():
    # A null key names no option, so it is no recommendation. A null `recommended` beside a valid `pick` passes: the
    # valid key is the recommendation the page draws.
    page("an update with kind decision and a valid recommended key passes", "update",
         entry_of({"kind": "decision", "recommended": "a"}), None)
    page("an update with kind decision, recommended null and a valid pick passes", "update",
         entry_of({"kind": "decision", "recommended": None, "pick": "a"}), None)
    page("an update with kind decision and recommended null is refused, naming the recommendation", "update",
         entry_of({"kind": "decision", "recommended": None}), (FORM_RULE, "recommend"))
    page("an update with kind decision and pick null is refused, naming the recommendation", "update",
         entry_of({"kind": "decision", "pick": None}), (FORM_RULE, "recommend"))
    page("an update with kind decision and both keys null is refused, naming the recommendation", "update",
         entry_of({"kind": "decision", "recommended": None, "pick": None}), (FORM_RULE, "recommend"))


def case_waiting_on_line_is_the_pages_line():
    # The page draws the first context line that starts `Waiting on:` at column 0, with text after the colon
    # (skills/waiting-page/page.html, the waitline split). A bold, bulleted, lower-case or indented label is a line the
    # page does not draw, so a set whose only such line is that form has no Waiting on line.
    page("a plain Waiting on line at column 0, with text after the colon, passes", "set",
         entry_of(rec_item(context=form_text(waiting=WAIT_LINE_TEXT))), None)
    for label, line in (("bold label", "**Waiting on:** nothing stopped; the lane acts next."),
                        ("bullet", "- Waiting on: nothing stopped; the lane acts next."),
                        ("lower-case label", "waiting on: nothing stopped; the lane acts next."),
                        ("indented label", "  Waiting on: nothing stopped; the lane acts next.")):
        page("a Waiting on line in the %s form, which the page does not draw, is refused, naming Waiting on" % label,
             "set", entry_of(rec_item(context=form_text(waiting=line))), (FORM_RULE, "Waiting on"))


def case_str_replace_keeps_the_waiting_line():
    context_replace("that removes the Waiting on line is refused, naming Waiting on",
                    form_text(), form_text(waiting=None), (FORM_RULE, "Waiting on"))
    context_replace("that leaves the Waiting on line with no text is refused, naming Waiting on",
                    WAITING, "Waiting on:", (FORM_RULE, "Waiting on"))
    context_replace("that swaps the Waiting on line for another valid line passes", WAITING, WAIT_LINE_TEXT, None)
    context_replace("whose old_str holds no Waiting on line passes", "The lane merge-role-allow would do it.",
                    "The lane would do it.", None)


def case_recommended_list_is_the_multi_form():
    # The list form holds the multi and ranked decisions: a list of distinct keys, each naming an option. The page
    # marks such an item with its drawn `multi` or `ranked` flag, so these cases carry the flag.
    page("a multi item whose recommended list names every option, in order, passes", "set",
         entry_of(rec_item(options=copy.deepcopy(PLAIN_OPTIONS), multi=True, recommended=["a", "b"])), None)
    page("a multi item whose recommended list is one key passes", "set",
         entry_of(rec_item(options=copy.deepcopy(PLAIN_OPTIONS), multi=True, recommended=["b"])), None)
    page("a ranked item whose recommended list is in rank order passes", "set",
         entry_of(rec_item(options=copy.deepcopy(PLAIN_OPTIONS), ranked=True, recommended=["b", "a"])), None)
    page("an empty recommended list on a multi item is refused, naming the recommendation", "set",
         entry_of(rec_item(options=copy.deepcopy(PLAIN_OPTIONS), multi=True, recommended=[])), (FORM_RULE, "recommend"))
    page("a recommended list that repeats a key is refused, naming the recommendation", "set",
         entry_of(rec_item(options=copy.deepcopy(PLAIN_OPTIONS), multi=True, recommended=["a", "a"])),
         (FORM_RULE, "recommend"))
    page("a recommended list that names an option not there is refused, naming the recommendation", "set",
         entry_of(rec_item(options=copy.deepcopy(PLAIN_OPTIONS), multi=True, recommended=["a", "z"])),
         (FORM_RULE, "recommend"))


def case_recommend_exemptions_pass():
    no_form = form_text(waiting=None)
    page("a closed decision with no recommendation, why or Waiting on line passes", "set",
         entry_of(rec_item(status="closed", recommended=None, why=None, context=no_form)), None)
    page("a note with no recommendation, why or Waiting on line passes", "set",
         entry_of(rec_item(kind="note", recommended=None, why=None, context=no_form)), None)
    page("a ruling with no recommendation, why or Waiting on line passes", "set",
         entry_of(rec_item(kind="ruling", recommended=None, why=None, context=no_form)), None)
    page("a task with no recommendation, why or Waiting on line passes", "set",
         entry_of(task_item(STEPS)), None)
    page("an update that carries only the title passes", "update",
         entry_of({"title": "Let the batch runner merge each batch on its own?"}), None)
    page("an update that carries only the status passes", "update", entry_of({"status": "open"}), None)


def case_recommend_applies_to_a_port_and_a_set_without_kind():
    page("a port decision with a recommendation, why and Waiting on line passes", "set",
         entry_of(rec_item(port=True)), None)
    page("a port decision with no Waiting on line is refused, naming Waiting on", "set",
         entry_of(rec_item(port=True, context=form_text(waiting=None))), (FORM_RULE, "Waiting on"))
    page("a set with no kind is judged as a decision, and is refused for no Waiting on line", "set",
         entry_of(rec_item(kind=None, context=form_text(waiting=None))), (FORM_RULE, "Waiting on"))


# The five real items on the owner's waiting page, each as its form lines: the same labelled lines, field names,
# option count and recommendation shape, with placeholder text. The owner's words and session ids are not copied.
# Each item's shape is one of the forms the rule must judge: a Meanwhile line, a prose paragraph before the Goal
# line, a holds field, an option-level star, and a widening option.
FIVE_FORMS = {
    "one wait per ready PR (836 shape)": {
        "lines": [GOAL, PROBLEM, BASED[1], THIRD, DEPARTS, "Meanwhile: the lane keeps its work and waits for no one."],
        "options": [{"key": "a", "label": "One wait", "gain": "No new rule.", "lose": "An older PR can go unchecked."},
                    {"key": "b", "label": "One wait per PR", "gain": "No PR goes unchecked.",
                     "lose": "A new rule to write and test."}],
        "recommended": "b", "why": "B leaves no ready PR without a check-in."},
    "check-in tools (837 shape)": {
        "lines": [GOAL, PROBLEM, BASED[1], THIRD, DEPARTS, "Meanwhile: the lane keeps option a as a limit."],
        "options": [{"key": "a", "label": "Count four tools", "gain": "No case changes.",
                     "lose": "A recurring cron counts as a one-time check-in.", "widens": True},
                    {"key": "b", "label": "Count send_later", "gain": "The check matches the remedy text.",
                     "lose": "Two tools are blocked at Stop."},
                    {"key": "c", "label": "Read each call", "gain": "The rule text becomes true in code.",
                     "lose": "A new rule and its tests."},
                    {"key": "d", "label": "send_later for session waits", "gain": "A session wait is told apart.",
                     "lose": "How often sessions wait this way is unmeasured."}],
        "recommended": "c", "why": "C matches the rule text and blocks no measured session."},
    "a granted lane flag (844 shape)": {
        "lines": [GOAL, PROBLEM, BASED[1], THIRD, DEPARTS, "Meanwhile: the lane waits; nothing else runs on it."],
        "options": [{"key": "a", "label": "Add a flag", "gain": "A check closes the path.",
                     "lose": "The entry's command text changes.", "widens": True},
                    {"key": "b", "label": "Prose only", "gain": "No entry edit.", "lose": "No check."},
                    {"key": "c", "label": "Flag outside the command", "gain": "No entry edit.",
                     "lose": "The receiver fails closed."}],
        "recommended": "b", "why": "B changes no entry and widens nothing."},
    "the records-only skip (857 shape)": {
        "lines": ["In plain words: the skip is built narrower than the owner chose.", GOAL, PROBLEM, THIRD, DEPARTS,
                  "Meanwhile: the pick stands and the work under it continues.",
                  "WE ARE WAITING ON YOU, nothing else: choose Keep or Overrule."],
        "options": [{"key": "a", "label": "Keep", "gain": "No guard change.", "lose": "A smaller saving."},
                    {"key": "b", "label": "Overrule", "gain": "The full skip.",
                     "lose": "A lane relaxes a pin.", "widens": True}],
        "recommended": "a", "why": "A changes no guard, and the saving is not yet measured."},
    "the push-skip reason line (878 shape)": {
        "lines": ["Plain words: a push run is the CI run that starts when a commit lands on main.", GOAL, PROBLEM,
                  BASED[0], THIRD, DEPARTS],
        "options": [{"key": "a", "label": "Require the tip", "gain": "Most pushes skip.", "lose": "One more run."},
                    {"key": "b", "label": "Print a reason line", "gain": "A reader sees why a run ran.",
                     "lose": "Saves no minutes."},
                    {"key": "c", "label": "Read the merge ref", "gain": "No ruling changes.", "lose": "Unproven."}],
        "recommended": "b", "why": "B costs no ruling and removes the silent skip.",
        "holds": "The lane waits until the owner answers."},
}


def five_form_item(name, waiting=True, status="open", **over):
    """One of FIVE_FORMS as a page write: its lines, its options and its recommendation. `waiting` adds the Waiting
    on line last, as a fixed shape gets it; the item's status is `status`."""
    shape = FIVE_FORMS[name]
    lines = shape["lines"] + ([WAITING] if waiting else [])
    extra = {"holds": shape["holds"]} if "holds" in shape else {}
    return rec_item(context="\n".join(lines), options=copy.deepcopy(shape["options"]), recommended=shape["recommended"],
                    why=shape["why"], status=status, **dict(extra, **over))


def case_five_real_forms():
    for name in FIVE_FORMS:
        page("%s: with its Waiting on line passes (scope)" % name, "set", entry_of(five_form_item(name)), None)
        page("%s: open, with no Waiting on line, is refused naming Waiting on" % name, "set",
             entry_of(five_form_item(name, waiting=False)), (FORM_RULE, "Waiting on"))
        page("%s: closed, with no Waiting on line, passes" % name, "set",
             entry_of(five_form_item(name, waiting=False, status="closed")), None)


def case_five_real_forms_as_written():
    # As written, two real items name no item-level recommendation: one stars an option, the other names none.
    page("the granted-lane-flag shape, starred on option b only, with no item recommendation, is refused naming the "
         "recommendation", "set",
         entry_of(rec_item(context="\n".join(FIVE_FORMS["a granted lane flag (844 shape)"]["lines"] + [WAITING]),
                           options=[dict(o, recommended=True) if o["key"] == "b" else dict(o)
                                    for o in FIVE_FORMS["a granted lane flag (844 shape)"]["options"]],
                           recommended=None)), (FORM_RULE, "recommend"))
    page("the records-only shape with no item recommendation is refused naming the recommendation", "set",
         entry_of(rec_item(context="\n".join(FIVE_FORMS["the records-only skip (857 shape)"]["lines"] + [WAITING]),
                           options=copy.deepcopy(FIVE_FORMS["the records-only skip (857 shape)"]["options"]),
                           recommended=None)), (FORM_RULE, "recommend"))


def case_widens_reason_no_longer_leaves_recommended_out():
    # The remedy for a decision where every option widens: add an option that does not widen, and recommend it.
    text = getattr(question_form, "WIDENS_REASON", None)
    if text is None:
        check("widens reason: question_form.WIDENS_REASON is there", False, MISSING)
        return
    flat = re.sub(r"\s+", " ", text)
    check("widens reason: question_form.WIDENS_REASON no longer says to leave recommended out",
          "leave recommended out" not in flat.lower(), flat)
    check("widens reason: question_form.WIDENS_REASON says to add an option that does not widen",
          "does not widen" in flat.lower(), flat)


def main():
    for case in (case_recommend_base_passes, case_recommend_missing_or_unknown_is_refused,
                 case_legacy_pick_is_the_recommendation, case_why_is_required, case_waiting_on_line_is_required,
                 case_update_judges_only_the_fields_it_carries, case_str_replace_keeps_the_waiting_line,
                 case_kindless_update_with_a_goal_line_needs_the_waiting_line,
                 case_kindless_update_with_a_why_yours_line_is_a_task, case_update_null_recommendation_is_refused,
                 case_waiting_on_line_is_the_pages_line,
                 case_recommended_list_is_the_multi_form, case_recommend_exemptions_pass,
                 case_recommend_applies_to_a_port_and_a_set_without_kind, case_five_real_forms,
                 case_five_real_forms_as_written, case_widens_reason_no_longer_leaves_recommended_out,
                 case_item_92, case_item_51_stray_field, case_item_n_text_is_refused,
                 case_item_n_other_non_numbers_are_refused, case_item_n_number_passes, case_item_n_absent,
                 case_item_n_batch_and_file_path, case_item_n_posted_text_names_the_item,
                 case_item_n_text_inside_other_text_is_not_judged,
                 case_item_n_reason_and_the_pages_own_rule, case_session_update_naming_dismissed_is_refused,
                 case_dismissed_refused_on_every_route, case_dismissed_refused_without_a_readable_field_list,
                 case_dismissed_reason_keeps_the_generic_remedy_for_other_fields,
                 case_lane_wait_flag_is_not_refused_as_undrawn, case_page_lists_holds_lane,
                 case_item_stray_field_refused_from_a_record_branch_checkout,
                 case_form_lines, case_form_placeholders_on_edits,
                 case_options_state_gain_and_loss, case_older_rules_keep_their_ids,
                 case_closed_stood_and_updates, case_str_replace, case_str_replace_bare_problem_lines,
                 case_str_replace_bare_to_malformed_stake,
                 case_stands_gets_no_relaxed_stake_rule, case_page_reasons_name_no_stands_field,
                 case_page_form_reason_names_the_pick_on_stake_only,
                 case_batch, case_chat_boxes,
                 case_line_order_and_prose, case_chat_press_scan_skips_gain_and_lose, case_session_press_needs_no_link,
                 case_claude_own_merge_needs_no_link,
                 case_chat_reasons_name_a_remedy_and_no_page_field, case_page_reasons_are_one_table,
                 case_gh_login_hit_direct, case_gh_login_switch_on_the_page, case_command_in_item_spans,
                 case_powershell_bash_forms, case_command_refusal_names_the_bash_forms,
                 case_powershell_hashtable_is_no_bash_form,
                 case_powershell_comment_quote_ends_at_its_line, case_powershell_bash_prefix_braced_expansion,
                 case_powershell_hash_mid_token_is_no_comment, case_step_shell_programs_partial,
                 case_quoted_span_after_edit_verb, case_delete_remove_span_is_a_shell_line,
                 case_quoted_span_run_after_is_refused, case_press_link_label_is_a_string,
                 case_departs_missing, case_departs_empty_or_malformed, case_departs_restates_main,
                 case_departs_valid_passes, case_departs_out_of_scope_passes, case_departs_str_replace,
                 case_departs_ids_and_order, case_departs_reasons,
                 case_departs_no_change_word_before_the_semicolon, case_departs_placeholders_are_refused,
                 case_departs_line_forms_pass, case_departs_str_replace_forms,
                 case_port_main_side, case_port_departs_shapes, case_call_judge,
                 case_widens_text_is_the_set_words, case_widens_reasons_carry_no_topic_id,
                 case_widens_words_in_every_home, case_widens_words_in_the_reply_judge_prompt,
                 case_past_rulings_caps_and_ranks, case_past_rulings_reads_debts, case_key_overlap,
                 case_key_overlap_resend_and_fact_lists, case_key_overlap_similar_questions_clash,
                 case_past_rulings_skips_the_debt_notes_file,
                 case_past_ruling_owner_sentence_past_the_cap_reaches_the_line,
                 case_past_ruling_owner_sentence_inside_the_cap_reaches_the_line,
                 case_past_ruling_section_without_owner_sentence_is_cut_at_the_cap,
                 case_past_ruling_owner_sentences_added_text_is_capped,
                 case_past_ruling_owner_row_after_a_long_table_reaches_the_line,
                 case_past_ruling_owner_sentences_newest_date_first,
                 case_ruled_store_first_and_carries_supersedes, case_ruled_store_absent_is_only_unknown,
                 case_ruled_store_words_filter_leaves_out_an_unrelated_entry,
                 case_ruled_store_caps_matching_entries_at_eight_newest_first,
                 case_ruled_store_marks_an_unread_entry_unchecked,
                 case_ruled_store_ranks_by_shared_words_before_recency,
                 case_ruled_store_scope_omits_a_private_ruling_in_a_public_repo,
                 case_ruled_store_scope_keeps_a_private_ruling_in_a_private_repo,
                 case_ruled_store_scope_private_only_lists_no_ruling_in_a_public_repo,
                 case_ruled_store_scope_private_rulings_do_not_take_the_cap,
                 case_ruled_store_scope_omits_a_public_ruling_in_a_private_repo,
                 case_ruled_store_scope_keeps_a_public_ruling_in_a_public_repo,
                 case_roadmap_broken_pipe_not_a_repo_is_absent, case_roadmap_broken_pipe_other_stderr_stays_unreadable,
                 case_task_why_cited_reds, case_task_why_cited_greens,
                 case_press_link_links_not_a_list_on_a_step, case_press_link_links_not_a_list_on_an_option,
                 case_task_str_replace_removes_only_the_label, case_str_replace_blank_prose_line_passes,
                 case_task_str_replace_rewords_the_reason, case_task_str_replace_renames_the_label,
                 case_task_str_replace_prose_label_passes,
                 case_cross_repo_missing_checked_with, case_cross_repo_checked_with_passes,
                 case_cross_repo_same_repo_passes, case_cross_repo_compares_lowercase,
                 case_cross_repo_no_page_repo_passes, case_cross_repo_required,
                 case_cross_repo_checked_with_not_the_owner, case_cross_repo_str_replace_not_judged,
                 case_cross_repo_update_carrying_repo, case_cross_repo_closed_item_passes,
                 case_cross_repo_task_names_checked_with, case_cross_repo_malformed_checked_with,
                 case_cross_repo_open_filter_is_the_one_home, case_cross_repo_open_filter_controls,
                 case_cross_repo_str_replace_on_repo_and_checked_with, case_cross_repo_required_when_page_repo_unknown,
                 case_cross_repo_malformed_repo_is_a_format_refusal, case_cross_repo_malformed_repo_controls,
                 case_cross_repo_writer_session_is_not_the_checker, case_cross_repo_writer_session_controls,
                 case_cross_repo_writer_guard_path, case_cross_repo_writer_page_item_hit,
                 case_cross_repo_writer_call_judge, case_cross_repo_update_checked_with_needs_repo,
                 case_judged_relative_file_path_read_at_cwd, case_judged_absolute_and_empty_are_unchanged,
                 case_judged_mixed_writes_all_returned,
                 case_stops_names_each_entry_in_holds, case_stops_consistent_items_pass,
                 case_stops_item_passes_the_real_page_fields,
                 case_stops_needs_holds_and_a_list, case_stops_refusal_prints_its_table_text,
                 case_stops_update_judged_by_the_fields_it_carries, case_stops_batch_judged_per_write,
                 case_stops_str_replace_on_holds_is_a_known_gap):
        try:
            case()
        except Exception as exc:
            check(case.__name__, False, "raised %s: %s" % (type(exc).__name__, exc))
    print("FAIL: %d failed" % len(FAILED) if FAILED else "all checks passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
