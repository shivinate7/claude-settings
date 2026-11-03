#!/usr/bin/env python3
"""Cases for the option-key gap in hooks/question_form.py. Rule option-letter-keys (decision
option-keys-are-letters) refuses a waiting-page item with an option keyed none. On main such a write got
through three ways, each red below:

  (a)  the write names another repo's waiting page. waiting_page_root judges a write only when its url is the
       cwd repo's own page, so the write is never judged;
  (a') the cwd repo has no page key. layout reads its page as "unknown", so the write is never judged;
  (c)  an update names its data by a relative file_path. _write_data opens the path against the hook
       process's cwd, not the payload's cwd, and an unreadable file reads as None, which passes.

Controls, green on main, beside each red: the same write on the cwd's own page is refused, the same update by
an absolute path is refused (so the relative read is the cause of (c)), letter keys pass in each shape, a
closed item passes, and a write to another collection passes.

Standard library only, no test runner. Run it from the repository root:

    python3 hooks/test_question_form_option_gap.py

Each case judges a write by question_form.page_item_hit (the call judge's surface) and by guard.data_tool_hit
(the guard's surface). Both take the payload cwd. The fixtures are test_call_judge.make_repo, with its `page`
option, and the verdict step is test_question_form.verdict. Temp files: the run folder of lint/_test_temp.py.
"""
import contextlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_call_judge as tcj  # noqa: E402  the fixture home: PAGE_URL, PAGE_ITEMS, make_repo, good_page_item
import test_question_form as tqf  # noqa: E402  the verdict step, and guard and question_form under the run's config

check, FAILED = tcj.check, tcj.FAILED
guard, question_form = tqf.guard, tqf.question_form

OTHER_URL = "https://claude.ai/artifact/otherpage"  # the waiting page of another repo
REFUSED = ("option-letter-keys", "option keyed none")  # the rule a refusal names, and the text of its matched part
PASS = None  # the verdict a pass is checked against, as tqf.verdict reads it


def items_write(action="set", data=None, url=tcj.PAGE_URL, collection=tcj.PAGE_ITEMS, **extra):
    """One ArtifactData call, as guard.data_tool_hit reads its tool_input."""
    call = {"action": action, "url": url, "collection": collection, "doc_id": "gap1"}
    if data is not None:
        call["data"] = data
    call.update(extra)
    return call


def none_item(**over):
    """A waiting-page decision that passes the form, with its first option keyed none: the shape of the Nov 2
    incident items. `over` replaces fields."""
    options = [{"key": "none", "label": "Ship it", "gain": "The change lands today.",
                "lose": "Nobody reads it first."},
               {"key": "b", "label": "Hold it", "gain": "A reviewer reads it first.",
                "lose": "The change lands a day later."}]
    return tcj.good_page_item(options=options, **over)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


@contextlib.contextmanager
def hook_cwd_without(name):
    """Run the body with the process cwd in a folder that holds no `name`, so a relative path resolves only
    if the code joins it to the payload's cwd."""
    folder = os.path.join(tcj.ROOT, "hook-cwd")
    os.makedirs(folder, exist_ok=True)
    saved = os.getcwd()
    os.chdir(folder)
    try:
        check("precondition: no %s at the hook's cwd" % name, not os.path.exists(name))
        yield
    finally:
        os.chdir(saved)


def judge_both(name, call, cwd, want):
    """The verdict on both surfaces: a refusal (want REFUSED) or a pass (want PASS)."""
    by_item = question_form.page_item_hit(call, cwd)[0]
    by_guard = guard.data_tool_hit(call, cwd)
    tqf.verdict(name + ", page_item_hit", by_item, want)
    tqf.verdict(name + ", guard.data_tool_hit", by_guard, want)


# ------------------------------------------------------------------ the red cases

def case_other_repo_page_refuses_none_key():
    """(a) An items write to another repo's waiting page, with an option keyed none, is refused. On main the
    gate reads the url as not this repo's page, so it passes the write."""
    cwd = tcj.make_repo("gap-other", page=OTHER_URL)
    judge_both("(a) a write to another repo's waiting page refuses an option keyed none",
               items_write("set", none_item()), cwd, REFUSED)


def case_no_page_key_refuses_none_key():
    """(a') An items write with an option keyed none, from a cwd repo that has no page key, is refused. On main
    layout reads the cwd's page as unknown, so the write is never judged."""
    cwd = tcj.make_repo("gap-nopage", page=None)
    judge_both("(a') a write from a cwd repo with no page key refuses an option keyed none",
               items_write("set", none_item()), cwd, REFUSED)


def case_relative_file_path_refuses_none_key():
    """(c) An update whose data is a file named by a relative file_path, with an option keyed none, is refused,
    the file read against the payload's cwd. On main _write_data opens the path against the hook's own cwd,
    finds no file, reads None and passes. The process cwd holds no such file, so only the join to cwd can
    make the refusal."""
    cwd = tcj.make_repo("gap-files")
    name = "relative-none.json"
    write_json(os.path.join(cwd, name), none_item())
    with hook_cwd_without(name):
        judge_both("(c) an update with a relative file_path, option keyed none, is refused, read against cwd",
                   items_write("update", file_path=name), cwd, REFUSED)


# ------------------------------------------------------------------ the green controls

def case_own_page_refuses_none_key():
    """Control, green on main: the cwd repo's own page refuses an option keyed none. The rule works wherever
    the gate reads the page as this repo's."""
    judge_both("control: the cwd repo's own page refuses an option keyed none",
               items_write("set", none_item()), tcj.PAGE_REPO, REFUSED)


def case_absolute_path_refuses_none_key():
    """Control, green on main: the same update by an absolute file_path is refused. So the relative read, not the
    rule, is the cause of (c)."""
    cwd = tcj.make_repo("gap-files")
    path = os.path.join(cwd, "absolute-none.json")
    write_json(path, none_item())
    judge_both("control: an update with an absolute file_path, option keyed none, is refused",
               items_write("update", file_path=path), cwd, REFUSED)


def case_letter_keys_pass_in_each_shape():
    """Controls, green on main: a letter-keyed item passes from another repo's page, from a cwd with no page
    key, and from a relative file_path. Each red above is the none key and nothing else."""
    judge_both("control: letter keys pass on another repo's waiting page",
               items_write("set", tcj.good_page_item()), tcj.make_repo("gap-other", page=OTHER_URL), PASS)
    judge_both("control: letter keys pass from a cwd with no page key",
               items_write("set", tcj.good_page_item()), tcj.make_repo("gap-nopage", page=None), PASS)
    cwd = tcj.make_repo("gap-files")
    name = "relative-letters.json"
    write_json(os.path.join(cwd, name), tcj.good_page_item())
    with hook_cwd_without(name):
        judge_both("control: letter keys pass from a relative file_path",
                   items_write("update", file_path=name), cwd, PASS)


def case_closed_none_key_passes():
    """Control, green on main: a closed item keyed none passes, both on the cwd's own page and on another
    repo's page. option_letter_hit returns for a closed item (the closed check), so the rule never judges it."""
    judge_both("control: a closed item keyed none passes on the cwd's own page",
               items_write("set", none_item(status="closed")), tcj.PAGE_REPO, PASS)
    judge_both("control: a closed item keyed none passes on another repo's waiting page",
               items_write("set", none_item(status="closed")), tcj.make_repo("gap-other", page=OTHER_URL), PASS)


def case_non_items_write_with_none_passes():
    """Control, green on main: a write to another collection passes, though its data carries a key none, from
    another repo's page. The rule reads the items collection only."""
    cwd = tcj.make_repo("gap-other", page=OTHER_URL)
    judge_both("control: a meta write with key none in unrelated data passes",
               items_write("set", {"key": "none", "title": "A setting"}, collection="meta"), cwd, PASS)
    judge_both("control: an answers write with an option keyed none passes",
               items_write("set", {"options": [{"key": "none", "label": "x"}]}, collection="answers"), cwd, PASS)


def main():
    for case in (case_other_repo_page_refuses_none_key, case_no_page_key_refuses_none_key,
                 case_relative_file_path_refuses_none_key, case_own_page_refuses_none_key,
                 case_absolute_path_refuses_none_key, case_letter_keys_pass_in_each_shape,
                 case_closed_none_key_passes, case_non_items_write_with_none_passes):
        try:
            case()
        except Exception as exc:
            check(case.__name__, False, "raised %s: %s" % (type(exc).__name__, exc))
    print("FAIL: %d failed" % len(FAILED) if FAILED else "all checks passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
