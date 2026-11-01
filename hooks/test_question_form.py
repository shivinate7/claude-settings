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
- A widening option: page `widens: true`, never in `pick`; chat `Goes against your uniform ruling (t18)`
  in its label or description, and never `(Recommended)` in its label (rule uniform-pick).
- A press in a web app: page `links`; chat an https:// url in that option's description (rule press-link).
  The chat scan skips an option's Gain and Lose text, as the page scan reads only label and how.
- A chat refusal reason names its remedy and no field of the waiting page (no `stands`). Each page reason
  is the text of question_form.PAGE_REASONS, the one table guard.py prints from.
- A closed item passes. An update is judged only for the fields it carries. A str_replace on `context`
  that removes a Goal, Problem or Based on line is refused.
- hooks/call_judge.py refuses an AskUserQuestion that fails chat_hit before any model call, with the rule
  chat_hit names; the model sees only a box that passes.

Every case runs on the surfaces the contract names. A page write is judged twice, by question_form.item_hit
and by guard.data_tool_hit, so a guard that does not delegate shows red. The same form lines are judged on
the chat surface from one table (FORM_VARIANTS). The call_judge cases reuse test_call_judge.run_hook (the
one home of the model stub). Temp files: the run folder of lint/_test_temp.py, whose sweep
lint/test_find_copies.py proves once (decision test-temp-standard).
"""
import contextlib
import copy
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import test_call_judge as tcj  # noqa: E402  the call_judge harness; its ROOT is this run's folder

RUN_FOLDER = tcj.ROOT
os.environ["CLAUDE_CONFIG_DIR"] = os.path.join(RUN_FOLDER, "config")
check, FAILED = tcj.check, tcj.FAILED

import guard  # noqa: E402
from precompact_handoff import PREMISE_KINDS  # noqa: E402  the one home of the premise kinds

try:
    import question_form
except ImportError:  # the build has not landed: each case that needs the module fails by name
    question_form = None

# The waiting page of the fixture repo. guard.data_tool_hit judges only a write to this repo's page.
PAGE_URL = "https://claude.ai/artifact/qfpage"
PAGE_REPO = os.path.join(RUN_FOLDER, "page-repo")
os.makedirs(os.path.join(PAGE_REPO, ".git"))
os.makedirs(os.path.join(PAGE_REPO, ".claude"))
with open(os.path.join(PAGE_REPO, ".claude", "layout-extras.json"), "w", encoding="utf-8") as _f:
    json.dump({"kinds": {}, "waiting-page": PAGE_URL}, _f)

FORM_RULE = "question-form"
DEPARTS_RULE = "question-departs"
DEPARTS = tcj.DEPARTS_LINE  # the one valid Departs from line (hooks/test_call_judge.py builds the box from it)
# A Problem line that is bare, or names a stake outside OWNER_STAKES: the contract does not say whether
# question-form or owner-judge names it, so either id passes and the refusal must name the Problem line.
STAKE_RULES = (FORM_RULE, "owner-judge")
OWNER_STAKES = getattr(question_form, "OWNER_STAKES", None) or guard.OWNER_STAKES
DOC = "batch-runner-merge"
MISSING = ("MISSING", "hooks/question_form.py has no such function yet")

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
    return guard.data_tool_hit(dict(entry, url=PAGE_URL, action=op), PAGE_REPO)


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
    task = {"kind": "task", "title": "Merge the batch", "status": "open", "steps": ["Open Terminal"],
            "context": "Why yours: a session on your computer was asked first and none could reach the remote"}
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


def case_batch():
    def batch(writes):
        return guard.data_tool_hit({"url": PAGE_URL, "action": "batch", "writes": writes}, PAGE_REPO)

    good = {"op": "set", "collection": "items", "doc_id": DOC, "data": page_item()}
    bad = {"op": "set", "collection": "items", "doc_id": "second", "data": ITEM92}
    verdict("page guard: a batch of items that meet the form passes", batch([good, dict(good, doc_id="second")]), None)
    verdict("page guard: a batch whose second write has no Problem line is refused", batch([good, bad]),
            (FORM_RULE, "Problem"))


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

    wide = "Goes against your uniform ruling (t18)."
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
                  "description": "Gain: it lands today. Lose: two forms stay. Goes against your uniform ruling (t18)."}
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
    why = "Why yours: a session on your computer was asked first and none could reach the remote"
    task = {"kind": "task", "title": "Merge the batch", "status": "open", "steps": ["Open Terminal"], "context": why}
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
                 description="Gain: it lands today. Lose: two forms stay. Goes against your uniform ruling (t18)."),
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
                  "description": "Gain: it lands today. Lose: two forms stay. Goes against your uniform ruling (t18)."}
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


def main():
    for case in (case_item_92, case_form_lines, case_options_state_gain_and_loss, case_older_rules_keep_their_ids,
                 case_closed_stood_and_updates, case_str_replace, case_batch, case_chat_boxes,
                 case_line_order_and_prose, case_chat_press_scan_skips_gain_and_lose,
                 case_chat_reasons_name_a_remedy_and_no_page_field, case_page_reasons_are_one_table,
                 case_gh_login_hit_direct, case_gh_login_switch_on_the_page,
                 case_departs_missing, case_departs_empty_or_malformed, case_departs_restates_main,
                 case_departs_valid_passes, case_departs_out_of_scope_passes, case_departs_str_replace,
                 case_departs_ids_and_order, case_departs_reasons,
                 case_departs_no_change_word_before_the_semicolon, case_departs_placeholders_are_refused,
                 case_departs_line_forms_pass, case_departs_str_replace_forms,
                 case_call_judge):
        try:
            case()
        except Exception as exc:
            check(case.__name__, False, "raised %s: %s" % (type(exc).__name__, exc))
    print("FAIL: %d failed" % len(FAILED) if FAILED else "all checks passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
