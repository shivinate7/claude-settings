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
  A stood pick (`stands: true`) may write `Problem: ...` with no stake kind. A line out of this order
  refuses. Only `Based on (<kind>):` is a Based on line: prose that starts with "Based on the log" is not.
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
import shutil
import sys
import time
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import test_call_judge as tcj  # noqa: E402  the call_judge harness; its ROOT is this run's folder

RUN_FOLDER = tcj.ROOT
os.environ["CLAUDE_CONFIG_DIR"] = os.path.join(RUN_FOLDER, "config")
check, FAILED = tcj.check, tcj.FAILED

import guard  # noqa: E402
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
ITEM92 = json.loads(r'''{"kind":"decision","title":"Let the batch runner merge each batch on its own?","context":"Goal: the batch runner merges each batch with no help from the coordinator or you. Today auto mode refuses the runner's `merge --role batch-runner` (03:04 CDT, main d545baf4): the cloud allow rules from #841 cover only `merge N --confirm`. The lane that would widen them was refused as a change to the sessions' own rules, so it needs your word. Asked in chat 03:05 CDT, no answer. Task home: docs/todo.md line fb-0303-1 (#845).","options":[{"gain":"No new form on the shared allow list.","how":"The coordinator merges each batch the runner builds.","key":"a","label":"Keep it as is","lose":"Each batch waits until the coordinator wakes."},{"gain":"The runner merges alone, so batches land sooner.","how":"Lane merge-role-allow adds `merge --role` to the auto-mode allow list, for the coordinator and batch-runner tiers only.","key":"b","label":"Allow merge --role","lose":"A second merge form on the shared allow list, against your one-form ruling (t18)."}],"pick":"a","why":"Your 16:54 CDT ruling (no owner step per merge) holds either way; a keeps the allow list to one form.","status":"open"}''')

# The form lines of the rewrite. Item 92's subject, in the owner's terms; no web marker, no press verb.
GOAL = "Goal: the batch runner merges each batch with no help from the coordinator or you."
PROBLEM = ("Problem (rule): auto mode refuses the runner's merge, and the lane that would allow it changes "
           "the sessions' own rules, so it needs your word.")
BASED = ("Based on (measured): auto mode refused the runner's merge at 03:04 CDT.",
         "Based on (read): the cloud allow rules cover only the plain merge form.")
THIRD = "Based on (ruling): your 16:54 CDT ruling says no owner step per merge."


LINE_KEYS = ("goal", "problem", "based", "departs")


def parts(**over):
    """The form lines as a dict. A part set to None is dropped; `based` is a list of lines."""
    found = {"goal": GOAL, "problem": PROBLEM, "based": list(BASED), "departs": DEPARTS}
    found.update(over)
    return found


def form_text(goal=GOAL, problem=PROBLEM, based=BASED, departs=DEPARTS):
    return "\n".join(line for line in (goal, problem, *based, departs) if line)


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
    return item


TASK_WHY = "Why yours: a session on your computer was asked first and none could reach the remote"


def task_item(steps, **over):
    """A waiting-page task with these steps and the Why yours line in `context`, so only the rule a case
    names judges it (task-names-check reads that line). `over` sets or replaces any field."""
    item = {"kind": "task", "title": "Merge the batch", "status": "open", "steps": list(steps), "context": TASK_WHY}
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


def guard_hit(op, entry, repo=PAGE_REPO):
    try:
        return guard.data_tool_hit(dict(entry, url=PAGE_URL, action=op), repo)
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
    ("a Problem line with no stake kind (no stood pick)", parts(problem="Problem: which job runs it."),
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
           based=["Based on (read): the <Card> prop renders twice."]), None),
    ("placeholder: a JSX lone quote and comment openers beside angle brackets pass",
     parts(goal="Goal: fix the <p>Don't</p> text, and keep // and /* in paths as plain text."), None),
]
for _kind in PREMISE_KINDS:
    FORM_VARIANTS.append(("a Based on kind %s" % _kind, parts(based=["Based on (%s): the premise." % _kind]), None))
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
    page("placeholder: a stood pick with the copied Problem line is refused", "set",
         entry_of(page_item(problem="Problem: <the problem, and why it needs his word>", stands=True)),
         (FORM_RULE, "Problem"))


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


# ------------------------------------------------------------------ closed items, stood picks, updates

def case_closed_stood_and_updates():
    answered = "Answer from chat, 10:42: keep the check in the lint job."
    page("a closed item with no form lines passes", "set",
         entry_of(dict(ITEM92, status="closed", context=answered)), None)
    page("an open item with the chat answer and no form lines is refused", "set",
         entry_of(dict(ITEM92, status="open", context=answered)), (FORM_RULE, None))
    page("a stood pick with `Problem:` and no stake kind passes", "set",
         entry_of(page_item(problem="Problem: which job runs it, and why it needs your word.", stands=True)), None)
    page("a stood pick with a stake kind passes", "set", entry_of(page_item(stands=True)), None)
    page("stands false with no form lines is refused", "set",
         entry_of(dict(ITEM92, stands=False, context="No form here.")), (FORM_RULE, None))
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
         entry_of({"kind": "decision", "options": lacking}), (FORM_RULE, "lose"))
    page("an update that carries options with a gain and a loss each passes, its context not carried", "update",
         entry_of({"kind": "decision", "options": copy.deepcopy(ITEM92["options"])}), None)


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


# ------------------------------------------------------------------ a str_replace that says an item is being reworked

def text_edit(new):
    """A str_replace on a context line of item DOC that adds `new`. It carries no status or kind."""
    return {"collection": "items", "doc_id": DOC, "field": "context", "old_str": "Context.", "new_str": new}


def case_str_replace_rework_is_refused():
    # Rule rework-off-page judges every kind of item, since a str_replace carries no status or kind (decision
    # rework-leaves-page). Main refuses a rework line on any item, and the refusal stays.
    page("a str_replace that adds 'being reworked' is refused as rework-off-page", "str_replace",
         text_edit("The lane is being reworked."), ("rework-off-page", "being reworked"))


# ------------------------------------------------------------------ a task's Why yours line cites what it claims
#
# Rule task-why-cited (decision claims-carry-backing, part (v)). The Why yours line of a waiting-page task
# is judged on its cite: a capability reason needs one, and the cite must hold on this surface. The page accepts a
# route cite and a dated measured cite, and no refusals-file cite. Each case judges one write through
# guard.data_tool_hit alone, with its rows in a file of this run's folder and the surface pinned to local.

WHY_RULE = "task-why-cited"
CAP = "Why yours: the cloud proxy refused the delete (403)"  # a capability reason: "refused" and "403"
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
        page(name, "set", entry_of(page_item(lines=lines)), want)
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
    task = {"kind": "task", "title": "Protect main on claude-settings", "status": "open",
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
    # A backslash glued to a word (origin\) is a path end, not a continuation, and passes as it does today.
    page("a PowerShell push with origin\\ then a line, the backslash glued to a word, passes as today", "set",
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


def case_powershell_hashtable_is_no_bash_form():
    # The NAME=value form in PS_BASH_FORMS ran its value past a `;`, so the second pair of a hashtable read as a
    # `NAME=value tool` line and was refused. A hashtable with `;` between its pairs passes. A leading NAME=value
    # before a command is still refused, and so is one after a `;`.
    for name, ps in (("a hashtable of three pairs", "$h = @{a=1; b=2; c=3}"),
                     ("a hashtable of two named pairs", "$o = @{Name='x'; Value=2}")):
        page("a PowerShell %s passes" % name, "set", entry_of(ps_task(ps)), None)
    for ps in ("FOO=1 tool run", "tool run;FOO=1 tool run"):
        page("a PowerShell command %s is refused as a bash operator" % ps, "set",
             entry_of(ps_task(ps)), ("command-in-item", "bash operator"))


def case_powershell_comment_quote_ends_at_its_line():
    # The quote walk reads `<#` block comments but not `#` line comments, so an unpaired quote in a line comment
    # opened a quote that ran to the end of the text, and a bash form on the next line was blanked out. A quote in a
    # line comment is text, so the next line is read as it stands. A contraction in a comment is text too, and a
    # comment opener inside a string opens no comment.
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


def case_powershell_pipe_then_newline_then_head():
    # A pipe at a line end continues into the next line, so `|`, a newline, then `head` is the bash pipe of `| head`.
    # A pipe to a PowerShell cmdlet on the next line passes, and a pipe inside a string is text.
    refused = ("command-in-item", "bash operator")
    page("a PowerShell command, git log |, then head on the next line, is refused as a bash operator", "set",
         entry_of(ps_task("git log |\nhead -5")), refused)
    page("a PowerShell command, Get-ChildItem |, then Select-Object on the next line, passes", "set",
         entry_of(ps_task("Get-ChildItem |\nSelect-Object -First 5")), None)
    page("a PowerShell string holding a pipe, then head on the next line with no pipe, passes", "set",
         entry_of(ps_task('Write-Host "a |"\nhead x')), None)


def case_powershell_param_attribute_at_line_start():
    # The named arguments of an attribute may wrap, so a line can start with `Mandatory=$true, Position=0`. That is
    # PowerShell, not a NAME=value prefix before a command, so it passes. The one-line attribute passes too.
    page("a PowerShell [Parameter( attribute wrapped so a line starts Mandatory=$true, Position=0, passes", "set",
         entry_of(ps_task("[Parameter(\n    Mandatory=$true, Position=0)]")), None)
    page("a PowerShell one-line [Parameter(Mandatory=$true, Position=0)] passes", "set",
         entry_of(ps_task("[Parameter(Mandatory=$true, Position=0)]")), None)
    # Only an attribute list (`Name=..., Name=...`) may follow a comma. `A=1, node x` is a prefix before `node`.
    page("a PowerShell command, A=1, node x, is refused as a bash operator", "set",
         entry_of(ps_task("A=1, node x")), ("command-in-item", "bash operator"))


def case_powershell_bash_prefix_command_substitution():
    # A NAME=value prefix may hold `$(...)` with a space in it, so `X=$(date +%s) node x` runs `node` after the
    # substitution and is a bash form. A PowerShell assignment with a subexpression passes.
    page("a PowerShell command, X=$(date +%s) node x, is refused as a bash operator", "set",
         entry_of(ps_task("X=$(date +%s) node x")), ("command-in-item", "bash operator"))
    page("a PowerShell assignment with a subexpression, $x = $(Get-Date); git push, passes", "set",
         entry_of(ps_task("$x = $(Get-Date); git push")), None)


def case_powershell_two_deep_expansion():
    # A NAME=value prefix may hold an expansion nested two levels deep, as in `A=${A:-${B:-${C}}}`, which is a bash form
    # and is refused. The same text in single quotes is a string, and its contents are blanked, so it passes.
    page("a PowerShell command, A=${A:-${B:-${C}}} node x, is refused as a bash operator", "set",
         entry_of(ps_task("A=${A:-${B:-${C}}} node x")), ("command-in-item", "bash operator"))
    page("a PowerShell string holding ${A:-${B:-${C}}}, single-quoted, passes", "set",
         entry_of(ps_task("$cfg = '${A:-${B:-${C}}}'")), None)


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


def case_step_path_cmdlet_is_a_shell_line():
    # A command word at a path is read by its basename, as `/usr/bin/chmod +x f` is. A Verb-Noun cmdlet at a Unix or a
    # Windows path is then a shell line on its own. A file name at a path is text, with or without an extension. So is
    # a module-qualified cmdlet, or a URL whose last segment is a cmdlet name: those name docs, not a program.
    refused = ("command-in-item", "shell line")
    page("a step holding `/opt/bin/Get-Thing` is refused as a shell line", "set",
         entry_of(task_item(["Check the output of `/opt/bin/Get-Thing`"])), refused)
    page(r"a step holding `C:\tools\Get-Thing` is refused as a shell line", "set",
         entry_of(task_item([r"Check the output of `C:\tools\Get-Thing`"])), refused)
    page("a step holding `docs/Read-Me.md` alone is text and passes", "set",
         entry_of(task_item(["Check the output of `docs/Read-Me.md`"])), None)
    page("a step holding `docs/Read-Me` alone, with no extension, is text and passes", "set",
         entry_of(task_item(["Check the output of `docs/Read-Me`"])), None)
    page("a step holding `Microsoft.PowerShell.Management/Get-Item` alone is text and passes", "set",
         entry_of(task_item(["Check the output of `Microsoft.PowerShell.Management/Get-Item`"])), None)
    page("a step holding a learn.microsoft.com URL ending in Get-Item alone is text and passes", "set",
         entry_of(task_item(["Check the output of `https://learn.microsoft.com/en-us/powershell/module/"
                             "microsoft.powershell.management/Get-Item`"])), None)


def case_step_span_flag_after_a_determiner_is_text():
    # A determiner (the, a, an, this, its) as a span's first word marks prose, so `the -x flag` is text, and so are the
    # other four. A span whose first word is no determiner keeps the span-flag rule: `ok --force` and `mode -v` stay
    # refused, as does `grep -r x` (case_step_shell_programs_partial).
    for span in ("the -x flag", "a -v option", "an -x flag", "this --force switch", "its -x flag"):
        page("a step holding `%s` is text and passes" % span, "set",
             entry_of(task_item(["Check the output of `%s`" % span])), None)
    for span in ("ok --force", "mode -v"):
        page("a step holding `%s` is refused as a shell line" % span, "set",
             entry_of(task_item(["Check the output of `%s`" % span])), ("command-in-item", "shell line"))


def case_step_folder_with_title_hyphen_is_text():
    # A folder whose last segment is Title-Hyphen (`Claude-Settings`) names a path, not a cmdlet: the word before the hyphen
    # is no approved PowerShell verb, so each passes. Main passes all four; head refuses them as a shell line.
    # `/opt/bin/Get-Thing` stays refused, as its verb Get is approved (case_step_path_cmdlet_is_a_shell_line).
    for folder in ("~/Documents/Claude-Settings", "/Users/shiv/Compass-Datacenters",
                   r"C:\Users\shiv\Compass-Datacenters", "/Users/shiv/Documents/Meeting-Notes"):
        page("a step naming the folder `%s` is text and passes" % folder, "set",
             entry_of(task_item(["Check the output of `%s`" % folder])), None)


def case_step_absolute_path_cmdlet_is_refused_in_every_form():
    # A Verb-Noun cmdlet at an absolute path is a shell line in every form of path, and a step that names it in prose
    # refuses too. Each form is pinned, so none can pass by its own spelling.
    refused = ("command-in-item", "shell line")
    for span in ("C:/tools/Get-Thing", "$HOME/bin/Get-Item", "${HOME}/bin/Get-Item", r"~\Get-Item", "~/bin/Get-Item"):
        page("a step holding `%s` is refused as a shell line" % span, "set",
             entry_of(task_item(["Check the output of `%s`" % span])), refused)


def case_step_verb_noun_folder_with_slash_is_text():
    # A folder path that ends in `/` is text: the slash marks a folder, not a cmdlet, so a Verb-Noun name in it passes.
    # These pass on main already, since a cmdlet name must end the span. They keep passing once the slash rule is built.
    for folder in ("~/Documents/Test-Results/", "C:\\Users\\x\\Documents\\Read-Me\\"):
        page("a step naming the folder `%s` in prose is text and passes" % folder, "set",
             entry_of(task_item(["Save the notes in `%s` before the review" % folder])), None)
    # Controls, passing on main: a path as the argument of a command word that is no shell program, and a PowerShell
    # command, which no shell-line check reads. A rule that refuses a path by its position must keep these passing.
    for span in ("open ~/Documents/Open-Items", "show /Users/x/Projects/Build-Tools"):
        page("a step holding `%s` is text and passes, its path an argument" % span, "set",
             entry_of(task_item(["Check the output of `%s`" % span])), None)
    for ps in ("cd ~/Documents/Open-Items", "ls /Users/x/Projects/Build-Tools",
               r"Copy-Item a.txt C:\Users\x\Documents\Read-Me"):
        page("a PowerShell command, %s, passes" % ps, "set", entry_of(ps_task(ps)), None)


def case_step_folder_without_slash_names_the_slash_remedy():
    # A folder name with no trailing slash, in prose, is still refused, because its Verb-Noun reads as a cmdlet. The
    # refusal names the remedy: end the folder with `/`. Main refuses it and names no remedy, so the remedy is the red.
    page("a step naming the folder `~/Documents/Test-Results` with no slash is refused and names the remedy", "set",
         entry_of(task_item(["Save the notes in `~/Documents/Test-Results` before the review"])),
         ("command-in-item", "end it with /"))


def case_step_backslash_cmdlet_path_after_a_prefix_is_a_shell_line():
    # A Verb-Noun cmdlet at a backslash path is a shell line after `&`, after a VAR=value prefix and after sudo, as it is
    # alone (case_step_path_cmdlet_is_a_shell_line). The forward-slash and the quoted forms are refused on main already:
    # they are the controls, and they stay refused.
    refused = ("command-in-item", "shell line")
    for span in (r"& C:\tools\Get-Thing", r"FOO=1 C:\tools\Get-Thing", r"sudo ~\Get-Item"):
        page("a step holding `%s` is refused as a shell line" % span, "set",
             entry_of(task_item(["Check the output of `%s`" % span])), refused)
    for span in ("& C:/tools/Get-Thing", r"& 'C:\tools\Get-Thing'"):
        page("a step holding `%s` is refused as a shell line, a control" % span, "set",
             entry_of(task_item(["Check the output of `%s`" % span])), refused)


def case_step_span_flag_after_a_prose_determiner_is_text():
    # A prose determiner (your, that, each, these) as a span's first word marks a flag phrase, so `your -x flag` is text,
    # as `the -x flag` is (case_step_span_flag_after_a_determiner_is_text). The span-flag rule keeps its refusal for a
    # command word that is no determiner: `grep -r x`, `chmod +x f` and `ok --force` stay refused.
    for span in ("your -x flag", "that -x flag", "each -x option", "these -v flags"):
        page("a step holding `%s` is text and passes" % span, "set",
             entry_of(task_item(["Check the output of `%s`" % span])), None)
    for span in ("grep -r x", "chmod +x f", "ok --force"):
        page("a step holding `%s` is refused as a shell line, a control" % span, "set",
             entry_of(task_item(["Check the output of `%s`" % span])), ("command-in-item", "shell line"))


def case_step_camel_verb_cmdlet_is_a_shell_line():
    # A Verb-Noun cmdlet whose verb is CamelCase (`ConvertTo-Json`, `ConvertFrom-Json`) is a shell line, as a lowercase
    # verb is (SHELL_CMDLET reads only `[A-Z][a-z]+-`). The control `docs/Read-Me` is a file name and stays text.
    refused = ("command-in-item", "shell line")
    for span in ("ConvertTo-Json x", "ConvertFrom-Json"):
        page("a step holding `%s` is refused as a shell line" % span, "set",
             entry_of(task_item(["Check the output of `%s`" % span])), refused)
    page("a step holding `docs/Read-Me` alone is text and passes, a control", "set",
         entry_of(task_item(["Check the output of `docs/Read-Me`"])), None)


def case_step_bare_cmdlet_outside_the_verb_list_is_a_shell_line():
    # A bare Verb-Noun cmdlet is a shell line when its verb is in PS_VERBS or is any Titlecase word. `Where-Object x`,
    # `Sort-Object` and `Tee-Object f` have verbs PS_VERBS does not list, and are refused as `ConvertTo-Json` is in
    # case_step_camel_verb_cmdlet_is_a_shell_line. A reader that takes the verb from PS_VERBS alone passes all three.
    refused = ("command-in-item", "shell line")
    for span in ("Where-Object x", "Sort-Object", "Tee-Object f"):
        page("a step holding `%s` is refused as a shell line" % span, "set",
             entry_of(task_item(["Check the output of `%s`" % span])), refused)


# A same-process ratio, not a wall clock: a linear form reads about 2 when a run of spaces doubles, the overlapping
# `[ \t]+` form about 4. The limit sits between them.
RATIO_LIMIT = 3.0


def cpu_per_call(fn, floor=0.05, reps=3):
    """The least CPU seconds per call of fn. Each batch runs until this process has used `floor` seconds of CPU, so a clock
    tick is small against it, and the least batch drops a spike. CPU time leaves out the time another process holds the
    CPU, which the load on a shared machine would add to a wall-clock timing. Windows CPU time ticks about 16 ms."""
    best = None
    for _ in range(reps):
        calls = 1
        while True:
            start = time.process_time()
            for _ in range(calls):
                fn()
            took = time.process_time() - start
            if took >= floor:
                break
            calls *= 2
        best = took / calls if best is None else min(best, took / calls)
    return best


def case_powershell_spaced_literals_are_no_bash_test():
    # A PowerShell cast with spaces, `( [ int ] 5 )`, and an array literal after a `;`, `; [ 1, 2 ]`, are PowerShell text, not
    # a bash `[ ... ]` test, so each passes. A real bash test after a `;` stays refused: the fix cannot drop the alternative.
    for name, ps in (("a spaced cast in parentheses", "$n = ( [ int ] 5 )"),
                     ("a spaced array literal after a semicolon", "$a = 1; [ 1, 2 ]")):
        page("a PowerShell command with %s passes" % name, "set", entry_of(ps_task(ps)), None)
    page("a PowerShell command with a bash test after a semicolon is refused as a bash operator", "set",
         entry_of(ps_task("$a = 1; [ -f x ]")), ("command-in-item", "bash operator"))


def case_bracket_test_alternative_is_linear():
    # The `[ ... ]` test alternative of PS_BASH_FORMS, single and double bracket, must take about linear time on a `[` with
    # many spaces after it, or a page write with such a line stalls. The outcome is that stall, so the pin times item_hit on
    # that line with N and with 2N spaces, in this one process, and compares the two. The verdict at the large size must be
    # a pass, so the timed call is the real path and not an early return.
    for opener in ("[", "[["):
        small = entry_of(ps_task(opener + " " * 2000 + "x"))
        large = entry_of(ps_task(opener + " " * 4000 + "x"))
        verdict("a PowerShell line of `%s` and 4000 spaces passes, the timed path" % opener,
                call("item_hit", "set", large), None)
        small_cost = cpu_per_call(lambda: call("item_hit", "set", small))
        large_cost = cpu_per_call(lambda: call("item_hit", "set", large))
        ratio = large_cost / small_cost
        check("a PowerShell line of `%s` with a run of spaces grows linearly when the run doubles" % opener,
              ratio < RATIO_LIMIT,
              "doubling the spaces after `%s` took %.1f times as long: the bracket test is quadratic"
              % (opener, ratio))
    refused = ("command-in-item", "bash operator")
    page("a PowerShell test, [ -f x ] on a line of its own, is refused as a bash operator", "set",
         entry_of(ps_task("[ -f x ]\ngit log")), refused)
    page("a PowerShell test, [[ -f x ]] on a line of its own, is refused as a bash operator", "set",
         entry_of(ps_task("[[ -f x ]]\ngit log")), refused)

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
    task = {"kind": "task", "title": "Merge the batch", "status": "open", "steps": ["Open Terminal"],
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
    crlf = "\r\n".join(line for line in (GOAL, PROBLEM, *BASED, DEPARTS) if line)
    box = chat_box()
    box["questions"][0]["question"] = crlf
    chat("a question with CRLF line endings and a valid Departs from line passes", box, None)
    page("a decision with CRLF line endings and a valid Departs from line passes", "set",
         entry_of(dict(ITEM92, context=crlf)), None)


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
    return {"kind": "task", "port": True, "title": "Merge the batch", "status": "open",
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
          r.code == 0 and r.out == "" and tcj.lifted_log(r, FORM_RULE), tcj.detail(r))
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


def main():
    for case in (case_item_92, case_item_51_stray_field, case_form_lines, case_form_placeholders_on_edits,
                 case_options_state_gain_and_loss, case_older_rules_keep_their_ids,
                 case_closed_stood_and_updates, case_str_replace, case_batch, case_chat_boxes,
                 case_line_order_and_prose, case_chat_press_scan_skips_gain_and_lose, case_session_press_needs_no_link,
                 case_claude_own_merge_needs_no_link,
                 case_chat_reasons_name_a_remedy_and_no_page_field, case_page_reasons_are_one_table,
                 case_gh_login_hit_direct, case_gh_login_switch_on_the_page, case_command_in_item_spans,
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
                 case_press_link_label_is_a_string, case_str_replace_rework_is_refused,
                 case_powershell_bash_forms, case_powershell_hashtable_is_no_bash_form,
                 case_powershell_comment_quote_ends_at_its_line, case_powershell_bash_prefix_braced_expansion,
                 case_powershell_hash_mid_token_is_no_comment, case_step_shell_programs_partial,
                 case_roadmap_broken_pipe_not_a_repo_is_absent, case_roadmap_broken_pipe_other_stderr_stays_unreadable,
                 case_task_why_cited_reds, case_task_why_cited_greens,
                 case_press_link_links_not_a_list_on_a_step, case_press_link_links_not_a_list_on_an_option,
                 case_task_str_replace_removes_only_the_label, case_str_replace_blank_prose_line_passes,
                 case_task_str_replace_rewords_the_reason, case_task_str_replace_renames_the_label,
                 case_task_str_replace_prose_label_passes,
                 case_powershell_pipe_then_newline_then_head, case_powershell_param_attribute_at_line_start,
                 case_powershell_bash_prefix_command_substitution,
                 case_powershell_two_deep_expansion,
                 case_step_path_cmdlet_is_a_shell_line, case_step_span_flag_after_a_determiner_is_text,
                 case_step_folder_with_title_hyphen_is_text, case_step_absolute_path_cmdlet_is_refused_in_every_form,
                 case_step_verb_noun_folder_with_slash_is_text, case_step_folder_without_slash_names_the_slash_remedy,
                 case_step_backslash_cmdlet_path_after_a_prefix_is_a_shell_line,
                 case_step_span_flag_after_a_prose_determiner_is_text, case_step_camel_verb_cmdlet_is_a_shell_line,
                 case_step_bare_cmdlet_outside_the_verb_list_is_a_shell_line,
                 case_powershell_spaced_literals_are_no_bash_test,
                 case_bracket_test_alternative_is_linear):
        try:
            case()
        except Exception as exc:
            check(case.__name__, False, "raised %s: %s" % (type(exc).__name__, exc))
    print("FAIL: %d failed" % len(FAILED) if FAILED else "all checks passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
