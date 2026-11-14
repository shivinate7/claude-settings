#!/usr/bin/env python3
"""Cases for rule task-options in hooks/question_form.py. The rule refuses a page task item that carries a
non-empty `options` list. The page draws options only for kind decision: the item render's task branch draws the
steps, the command and the links, and never the options (skills/waiting-page/page.html). So an option's `how` and
`links` on a task never reach the owner. Each red case below passes on main and fails by its own assert.

Red cases (the rule is missing):
  task with options that carry how and links (the shape of items 626 and 661), task with options and no how,
  an update with kind task and options, and a full-size task with four options that carry how and links.
  The refusal text names the fix (PAGE_REASONS["task-options"]: kind decision, or the command field).

Green controls, passing on main and after the build:
  a decision with options, a task with a command and no options, a task with options: [], a task with no options
  key, an update with no kind key and options, a non-list `options` on a task (not this rule's), and a task with
  options on a page that is not this repo's (the scope pin).

Round 2 rulings, red on the round 1 build (e5dd50014) and green once the rule takes them: the rule fires only on an
explicit kind task, so a set with no kind key and options passes (a missing kind reads as a decision, as in
decision_form_hit and _open_decision); and a closed item is not refused, so a closed task with options passes on a
set and on an update.

Standard library only, no test runner. Run it from the repository root:

    python3 -B hooks/test_question_form_task_options.py

Each case judges a write by question_form.item_hit (through tqf.page) and by guard.data_tool_hit (the guard's
surface). The fixtures are test_call_judge's (good_page_item, with_frozen_fields), test_question_form's (task_item,
entry_of, page, verdict) and test_question_form_option_gap's (items_write, judge_both, check_scope, OTHER_URL). Each
is imported, not copied. Temp files: none; the fixtures use the run folder of lint/_test_temp.py.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
LINT = os.path.join(HERE, "..", "lint")
if LINT not in sys.path:
    sys.path.append(LINT)
import test_call_judge as tcj  # noqa: E402  the fixture home: good_page_item, with_frozen_fields, PAGE_URL, PAGE_REPO
import test_question_form as tqf  # noqa: E402  the verdict step: page, entry_of, task_item, call, guard_hit
import test_question_form_option_gap as gap  # noqa: E402  the scope step: items_write, judge_both, check_scope
import layout  # noqa: E402  waiting_page(root) reads the repo's page key

check, FAILED = tcj.check, tcj.FAILED
question_form = tqf.question_form

RULE = "task-options"
REFUSED = (RULE, None)  # the rule a refusal names; no matched fragment, which is the builder's choice
PASS = None  # the verdict a pass is checked against, as tqf.verdict reads it
NO_REASON = "PAGE_REASONS has no reason for rule task-options"  # the failure message when the reason is missing


def shaped_option(key, label, how=None, links=None):
    """A decision-shaped option with a plain gain and lose. `how` and `links` are added only when given."""
    option = {"key": key, "label": label, "gain": "The command runs on your computer.",
              "lose": "Nothing changes until it runs."}
    if how is not None:
        option["how"] = how
    if links is not None:
        option["links"] = links
    return option


PASTE_HOW = "Paste the prompt from the command field into PowerShell."
RUNBOOK = [{"label": "the runbook", "url": "https://claude.ai/artifact/runbook"}]


def incident_options():
    """The shape of items 626 and 661: the paste prompt sat in option a's `how`, with a link, on a task."""
    return [shaped_option("a", "Paste the prompt", how=PASTE_HOW, links=RUNBOOK), shaped_option("b", "Hold it")]


def plain_options():
    """Options with no how and no links."""
    return [shaped_option("a", "Paste the prompt"), shaped_option("b", "Hold it")]


def full_options():
    """Four options, each with how and links: the full-size task."""
    return [shaped_option(k, "Option %s" % k.upper(), how=PASTE_HOW, links=RUNBOOK) for k in "abcd"]


def task_options(options, **over):
    """A page task with these options, frozen as a session writes them (ids and `shown`), so only the rule
    a case names can judge it. The steps and the Why yours line come from test_question_form.task_item."""
    return tcj.with_frozen_fields(tqf.task_item(["Open PowerShell"], options=options, **over))


def scoped_page(name, op, entry, want):
    """Scope before subject: the cwd's page reads as this repo's page, and the write is on it. Both are asserted
    before the verdict is read, so a pass cannot come from a write off this repo's page. Then tqf.page judges the
    write by item_hit and by the guard."""
    call = dict(entry, url=tqf.PAGE_URL, action=op)
    check("scope: %s, the cwd's page reads as this repo's page" % name,
          layout.waiting_page(tqf.PAGE_REPO) == tqf.PAGE_URL,
          "layout.waiting_page reads %r" % (layout.waiting_page(tqf.PAGE_REPO),))
    check("scope: %s, the write is on this repo's page" % name, question_form.is_waiting_page(call, tqf.PAGE_REPO))
    tqf.page(name, op, entry, want)


# ------------------------------------------------------------------ the red cases

def case_task_options_with_how_and_links_refused():
    """Red: a set of a task with options that carry how and links, the 626/661 shape. The page never draws a task's
    options, so the prompt in `how` never reaches the owner. On main the write passes."""
    scoped_page("a task with options that carry how and links is refused as task-options", "set",
                tqf.entry_of(task_options(incident_options())), REFUSED)


def case_task_options_without_how_refused():
    """Red: a set of a task with options and no how and no links. The page draws no option on a task, so the
    options are hidden whatever they carry. On main the write passes."""
    scoped_page("a task with options and no how is refused as task-options", "set",
                tqf.entry_of(task_options(plain_options())), REFUSED)


def case_task_update_with_options_refused():
    """Red: an update that writes kind task and options. The stored item is not read: the write names the kind, so
    the rule judges it. On main the write passes."""
    scoped_page("an update with kind task and options is refused as task-options", "update",
                tqf.entry_of(tcj.with_frozen_fields({"kind": "task", "options": plain_options()})), REFUSED)


def case_full_size_task_options_refused():
    """Red: the full-size task, four options each with how and links. On main the write passes."""
    scoped_page("a task with four options that carry how and links is refused as task-options", "set",
                tqf.entry_of(task_options(full_options())), REFUSED)


def case_refusal_names_the_fix():
    """Red: the refusal text names both fixes, kind decision and the command field. The text sits in the page reason
    table, keyed by rule id. On main the table has no entry for the rule, so each check fails by its own name."""
    reasons = getattr(question_form, "PAGE_REASONS", {}) or {}
    reason = reasons.get(RULE) or ""
    check("refusal text: PAGE_REASONS has a reason for task-options", bool(reason), NO_REASON)
    check("refusal text: task-options names the fix kind decision", "kind `decision`" in reason,
          "reason %r has no fix 'kind `decision`'" % (reason,))
    check("refusal text: task-options names the fix command", "command" in reason.lower(),
          "reason %r has no 'command'" % (reason,))


# ------------------------------------------------------------------ the green controls

def case_decision_with_options_passes():
    """Control: a decision with options passes. The page draws a decision's options, so the rule does not judge it."""
    scoped_page("control: a decision with options passes", "set", tqf.entry_of(tcj.good_page_item()), PASS)


def case_task_with_command_passes():
    """Control: a task with a command and no options passes. The command is the task's place for the paste prompt."""
    cmd = {"powershell": "Get-Date", "mac": "date"}
    scoped_page("control: a task with a command and no options passes", "set",
                tqf.entry_of(tqf.task_item(["Open PowerShell"], command=cmd)), PASS)


def case_task_with_empty_options_passes():
    """Control: a task with options: [] passes. An empty list carries no choice, so the rule has nothing to refuse."""
    scoped_page("control: a task with options: [] passes", "set", tqf.entry_of(task_options([])), PASS)


def case_task_without_options_key_passes():
    """Control: a task with no options key passes."""
    scoped_page("control: a task with no options key passes", "set", tqf.entry_of(tqf.task_item(["Open PowerShell"])),
                PASS)


def case_update_without_kind_with_options_passes():
    """Control: an update with options and no kind key passes. The stored item may be a decision, and the rule
    cannot see its kind, so it does not judge the write."""
    scoped_page("control: an update with no kind key and options passes", "update",
                tqf.entry_of(tcj.with_frozen_fields({"options": plain_options()})), PASS)


def case_non_list_options_on_task_not_this_rule():
    """Control: a task whose `options` is not a list is not this rule's. The rule reads a non-empty list only, so
    the verdict must not name task-options. Another rule may still refuse it, and that is not judged here."""
    for name, value in (("a string", "a"), ("a dict", {"key": "a", "label": "Paste the prompt"})):
        entry = tqf.entry_of(tqf.task_item(["Open PowerShell"], options=value))
        item_hit = tqf.call("item_hit", "set", entry)
        guard_hit = tqf.guard_hit("set", entry)
        check("control: a task with options as %s is not task-options on item_hit" % name,
              item_hit[0] != RULE, "item_hit gave %r" % (item_hit,))
        check("control: a task with options as %s is not task-options on the guard" % name,
              guard_hit[0] != RULE, "guard gave %r" % (guard_hit,))


def case_task_options_on_another_page_passes():
    """Pin of the scope: a task with options on a page that is not this repo's passes. Scope is only this repo's
    waiting page, as the other rules. The check_scope step asserts the scope before the verdict is read."""
    cwd = tcj.make_repo("task-other", page=gap.OTHER_URL)
    call = gap.items_write("set", task_options(incident_options()))
    gap.check_scope("a task with options on another repo's page", call, cwd, gap.OTHER_URL, on_page=False)
    gap.judge_both("pass: a task with options on another repo's page passes", call, cwd, PASS)


# ------------------------------------------------------------------ the round 2 rulings

def case_set_no_kind_with_options_passes():
    """Ruling: a set with no kind key and options passes. A missing kind is a decision, so the rule does not judge
    it as a task. The round 1 build reads a missing kind as task (command_in_item_hit does), so it refuses this
    write: red on e5dd50014."""
    item = tcj.good_page_item()
    item.pop("kind")
    scoped_page("a set with no kind and options passes", "set", tqf.entry_of(item), PASS)


def case_closed_task_with_options_passes_on_set():
    """Ruling: a closed task with options passes on a set. A closed item records what was decided, so the rule does
    not refuse it. The round 1 build refuses it: red on e5dd50014."""
    scoped_page("a closed task with options passes on a set", "set",
                tqf.entry_of(task_options(incident_options(), status="closed")), PASS)


def case_closed_task_update_with_options_passes():
    """Ruling: an update that writes kind task, status closed and options passes. The write names the closed status,
    so the rule judges the closed item, which it does not refuse. The round 1 build refuses it: red on e5dd50014."""
    scoped_page("a closed task with options passes on an update", "update",
                tqf.entry_of(tcj.with_frozen_fields({"kind": "task", "status": "closed", "options": plain_options()})),
                PASS)


def main():
    for case in (case_task_options_with_how_and_links_refused, case_task_options_without_how_refused,
                 case_task_update_with_options_refused, case_full_size_task_options_refused,
                 case_refusal_names_the_fix, case_decision_with_options_passes, case_task_with_command_passes,
                 case_task_with_empty_options_passes, case_task_without_options_key_passes,
                 case_update_without_kind_with_options_passes, case_non_list_options_on_task_not_this_rule,
                 case_task_options_on_another_page_passes, case_set_no_kind_with_options_passes,
                 case_closed_task_with_options_passes_on_set, case_closed_task_update_with_options_passes):
        try:
            case()
        except Exception as exc:
            check(case.__name__, False, "raised %s: %s" % (type(exc).__name__, exc))
    print("FAIL: %d failed" % len(FAILED) if FAILED else "all checks passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
