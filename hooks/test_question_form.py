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
  A stood pick (`stands: true`) may write `Problem: ...` with no stake kind.
- Each option states gain and loss: page `gain` and `lose` fields; chat `Gain:` and `Lose:` in the description.
- A widening option: page `widens: true`, never in `pick`; chat `Goes against your uniform ruling (t18)`
  in its label or description, and never `(Recommended)` in its label (rule uniform-pick).
- A press in a web app: page `links`; chat an https:// url in that option's description (rule press-link).
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
import copy
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


def parts(**over):
    """The form lines as a dict. A part set to None is dropped; `based` is a list of lines."""
    found = {"goal": GOAL, "problem": PROBLEM, "based": list(BASED)}
    found.update(over)
    return found


def form_text(goal=GOAL, problem=PROBLEM, based=BASED):
    return "\n".join(line for line in (goal, problem, *based) if line)


def page_item(tail="", options=None, **over):
    """Item 92 in the form: the form lines in `context`, option b marked widens, the pick on a."""
    item = copy.deepcopy(ITEM92)
    item["context"] = form_text(**{k: v for k, v in over.items() if k in ("goal", "problem", "based")}) + tail
    item["options"][1]["widens"] = True
    if options is not None:
        item["options"] = options
    item.update({k: v for k, v in over.items() if k not in ("goal", "problem", "based")})
    return item


def chat_box(options=None, **over):
    """A chat box with the same form lines. Options default to test_call_judge.good_options()."""
    return tcj.good_box(options=options, **{k: v for k, v in over.items() if k in ("goal", "problem", "based")})


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
                 case_closed_stood_and_updates, case_str_replace, case_batch, case_chat_boxes, case_call_judge):
        try:
            case()
        except Exception as exc:
            check(case.__name__, False, "raised %s: %s" % (type(exc).__name__, exc))
    print("FAIL: %d failed" % len(FAILED) if FAILED else "all checks passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
