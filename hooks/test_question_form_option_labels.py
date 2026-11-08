#!/usr/bin/env python3
"""Cases for the option-label check and the `recommended` rename of hooks/question_form.py.

Three parts, one file:

  1. Rule option-labels-match-chat. A waiting-page decision and the chat question that asked it are two static
     copies of one option list. Letter a on the page must mean the same as letter a in the chat. A chat question
     cites its item with a line "Page item: <id>" and writes one line per option, "a) <text>". The check refuses a
     page write whose option label for a letter differs from the chat text for that letter.
     Function cases (fn:) call question_form.chat_page_label_hit(item_id, options, chat_text) directly.
     Wiring cases (wire:) run hooks/guard.py as a hook process with a transcript_path holding the chat question,
     the way the page-item write path reads a chat text.
  2. The `recommended` field. The page stars `recommended`, falling back to `pick`. The widening guard
     (widens_pick_hit, rule uniform-pick) also refuses a `recommended` that names a widening option. The page draws
     `recommended` (its itemFields block lists it).
  3. The page's own copy of the star and the answer label is tested in skills/waiting-page/tests/page.test.mjs.
     page_grant.py's ignoring of the answer `label` is tested in skills/waiting-page/test_page_grant_label.py.

Red on the old code (422cbbdfe): every wire: case that expects a refusal, and the recommended and field cases,
fail on an assert about the verdict (the check is not wired, the field is not drawn). The fn: cases cannot run
there, because chat_page_label_hit is not built yet: they report "not built", which is not a red (P3). Run with the
argument `behaviour` to skip them, which is the red-run form. Without it, every case runs.

Standard library only, no test runner. Run it from the repository root:

    python3 hooks/test_question_form_option_labels.py              (all cases)
    python3 hooks/test_question_form_option_labels.py behaviour     (the cases that need no new function)

Each wire: case writes its transcript and its guard config under this run's folder (test_call_judge.ROOT, from
lint/_test_temp.py), so no temp file lives anywhere else.
"""
import copy
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_call_judge as tcj  # noqa: E402  the fixture home: PAGE_URL, PAGE_REPO, ROOT, check, FAILED
import test_question_form as tqf  # noqa: E402  the verdict step and the item_hit and guard verdict pair

check, FAILED = tcj.check, tcj.FAILED
question_form = tqf.question_form
GUARD = os.environ.get("GUARD_UNDER_TEST") or os.path.join(HERE, "guard.py")
RULE = "option-labels-match-chat"
NOT_BUILT = object()  # chat_page_label_hit is not in hooks/question_form.py yet

# The two options of the owner's question, as the page holds them. Letter = position: a is Keep it as is.
OPTIONS = [
    {"key": "a", "label": "Keep it as is", "gain": "No new form on the shared allow list.",
     "lose": "Each batch waits until the coordinator wakes."},
    {"key": "b", "label": "Allow merge --role", "gain": "The runner merges each batch alone.",
     "lose": "A second merge form on the shared allow list."},
]
# The chat lines for OPTIONS. CHAT_B_MISMATCH names a different option for letter b: it is no prefix of the label.
CHAT_A = "a) Keep it as is"
CHAT_B = "b) Allow merge --role"
CHAT_B_MISMATCH = "b) Hold the batch for the coordinator"
CHAT_B_SHORT = "b) Allow merge"  # the short form: a prefix of the label
ITEM = "merge-role-allow"  # the page item id the chat cites
OTHER_ITEM = "other-item"


def chat_question(lines, cite=ITEM):
    """A chat question: the form lines, a "Page item: <id>" line when `cite` is set, then the option lines."""
    head = [tcj.GOAL_LINE, tcj.PROBLEM_LINE, *tcj.BASED_LINES, tcj.DEPARTS_LINE]
    if cite is not None:
        head.append("Page item: " + cite)
    return "\n".join(head + list(lines))


def label_item(doc, options=None, **over):
    """A waiting-page decision that passes the form and the other rules, with `options` as its options."""
    item = tcj.good_page_item(id=doc)
    item["options"] = copy.deepcopy(OPTIONS if options is None else options)
    item.update(over)
    return item


def label_options(label_b):
    """OPTIONS with letter b's label set to `label_b`, for a case that changes one label."""
    options = copy.deepcopy(OPTIONS)
    options[1]["label"] = label_b
    return options


def fn_label(item_id, options, chat):
    """chat_page_label_hit(item_id, options, chat), or NOT_BUILT when the function is not there yet."""
    fn = getattr(question_form, "chat_page_label_hit", None)
    if fn is None:
        return NOT_BUILT
    try:
        return fn(item_id, options, chat)
    except Exception as exc:  # a crash is a wrong verdict, shown by name
        return "RAISED %s: %s" % (type(exc).__name__, exc)


def fn_pass(name, got):
    if got is NOT_BUILT:
        check(name, False, "chat_page_label_hit is not in hooks/question_form.py yet (not built)")
        return
    check(name, got == "", "want a pass, got %r" % (got,))


def fn_refuse(name, got, letter):
    """A refusal is a non-empty message that names the letter whose label differs."""
    if got is NOT_BUILT:
        check(name, False, "chat_page_label_hit is not in hooks/question_form.py yet (not built)")
        return
    named = isinstance(got, str) and bool(re.search(r"\b%s\b" % letter, got, re.I))
    check(name, bool(got) and named, "want a refusal naming letter %r, got %r" % (letter, got))


# ------------------------------------------------------------------ 1. the function (fn:)

def case_fn_equal_labels_pass():
    fn_pass("fn: a chat line equal to each label passes",
            fn_label(ITEM, OPTIONS, "\n".join((CHAT_A, CHAT_B))))


def case_fn_case_and_spaces_fold():
    fn_pass("fn: a chat line that differs only in case and spacing passes",
            fn_label(ITEM, OPTIONS, "\n".join(("a)   KEEP it   AS is", "b) allow   MERGE --role"))))


def case_fn_prefix_either_way_passes():
    fn_pass("fn: a chat short form that the label starts with passes",
            fn_label(ITEM, OPTIONS, "\n".join((CHAT_A, CHAT_B_SHORT))))
    fn_pass("fn: a label that is a prefix of a longer chat line passes",
            fn_label(ITEM, label_options("Allow"), "\n".join((CHAT_A, "b) Allow merge --role, then wait"))))


def case_fn_differing_label_refuses_naming_the_letter():
    fn_refuse("fn: a chat line for b that differs from its label is refused, naming b",
              fn_label(ITEM, OPTIONS, "\n".join((CHAT_A, CHAT_B_MISMATCH))), "b")


def case_fn_no_cited_id_passes():
    fn_pass("fn: a chat question that cites no page item passes, even with a differing letter",
            fn_label(ITEM, OPTIONS, "\n".join((CHAT_A, CHAT_B_MISMATCH))))


def case_fn_other_item_passes():
    chat = chat_question((CHAT_A, CHAT_B_MISMATCH), cite=OTHER_ITEM)
    fn_pass("fn: a chat question that cites another page item passes",
            fn_label(ITEM, OPTIONS, chat))


def case_fn_letter_missing_from_chat_passes():
    fn_pass("fn: an option whose letter the chat does not write passes",
            fn_label(ITEM, OPTIONS, CHAT_A))


def case_fn_letter_is_position():
    options = copy.deepcopy(OPTIONS) + [{"key": "c", "label": "Wait a day", "gain": "g", "lose": "l"}]
    fn_refuse("fn: letter c is the third option's position, so a differing c is refused",
              fn_label(ITEM, options, "\n".join((CHAT_A, CHAT_B, "c) Hold for a day"))), "c")


# ------------------------------------------------------------------ 1. the page-item write path (wire:)

def write_transcript(name, text):
    """A transcript of one human message and one assistant message holding `text`, under this run's folder."""
    folder = os.path.join(tcj.ROOT, "label-transcripts")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name + ".jsonl")
    human = {"type": "user", "message": {"role": "user", "content": "Ask the owner."}}
    assistant = {"type": "assistant", "message": {"role": "assistant",
                                                    "content": [{"type": "text", "text": text}]}}
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(human) + "\n" + json.dumps(assistant) + "\n")
    return path


def decision_of(stdout):
    """(decision, reason) a guard run printed. Empty output is an allow."""
    out = stdout.strip()
    if not out:
        return "allow", ""
    try:
        block = json.loads(out)["hookSpecificOutput"]
        return block["permissionDecision"], block["permissionDecisionReason"]
    except Exception:
        return "unparsable", out[:200]


def guard_hook(name, call, transcript):
    """Run hooks/guard.py as the hook process does, for one ArtifactData call, with the transcript the session
    wrote. Returns (decision, reason)."""
    folder = os.path.join(tcj.ROOT, "label-cfg", name)
    os.makedirs(folder, exist_ok=True)
    env = dict(os.environ, CLAUDE_CONFIG_DIR=folder, CLAUDE_GUARD_ROOT_PID=str(os.getpid()))
    for key in ("CLAUDE_CODE_REMOTE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE_SESSION_ID"):
        env.pop(key, None)
    payload = {"session_id": "label-session", "tool_name": "ArtifactData", "cwd": tcj.PAGE_REPO,
               "tool_input": dict(call, url=tcj.PAGE_URL), "transcript_path": transcript}
    got = subprocess.run([sys.executable, GUARD], input=json.dumps(payload), capture_output=True, text=True,
                         env=env, timeout=120)
    if got.returncode != 0:
        return "error", "exit %d: %s" % (got.returncode, got.stderr.strip()[:200])
    return decision_of(got.stdout)


def set_write(doc, options=None):
    return {"action": "set", "collection": tcj.PAGE_ITEMS, "doc_id": doc, "data": label_item(doc, options)}


def wire_refuses(name, call, transcript):
    """A deny that names the rule. The message wording is the builder's, so the letter is not read here."""
    decision, reason = guard_hook(name, call, transcript)
    check(name, decision == "deny" and RULE in reason,
          "want a deny naming %s, got %s: %r" % (RULE, decision, reason[:200]))


def wire_allows(name, call, transcript):
    decision, reason = guard_hook(name, call, transcript)
    check(name, decision == "allow", "want an allow, got %s: %r" % (decision, reason[:200]))


def case_wire_differing_set_is_refused():
    """A set whose option b reads "Allow merge --role" beside a chat question that wrote b as something else is refused
    as option-labels-match-chat. On the old code the check is not wired, so the set is allowed."""
    transcript = write_transcript("differs", chat_question((CHAT_A, CHAT_B_MISMATCH)))
    wire_refuses("wire: a set whose label for b differs from the chat's b is refused", set_write(ITEM), transcript)


def case_wire_differing_update_is_refused():
    """An update that carries options is judged on the same rule: a differing letter is refused."""
    transcript = write_transcript("differs-update", chat_question((CHAT_A, CHAT_B_MISMATCH)))
    call = {"action": "update", "collection": tcj.PAGE_ITEMS, "doc_id": ITEM,
            "data": {"kind": "decision", "options": copy.deepcopy(OPTIONS)}}
    wire_refuses("wire: an update carrying options whose b differs from the chat's b is refused", call, transcript)


def case_wire_matching_set_is_allowed():
    """Control, green on the old code: the same labels, written as the chat wrote them, pass."""
    transcript = write_transcript("matches", chat_question((CHAT_A, CHAT_B)))
    wire_allows("control: a set whose labels equal the chat's lines is allowed", set_write(ITEM), transcript)


def case_wire_short_form_is_allowed():
    """Control, green on the old code: a chat short form that the label starts with is allowed."""
    transcript = write_transcript("short", chat_question((CHAT_A, CHAT_B_SHORT)))
    wire_allows("control: a set whose chat b is the short form of its label is allowed", set_write(ITEM), transcript)


def case_wire_no_cited_id_is_allowed():
    """Control, green on the old code: a chat question with no Page item line is not compared, even when it differs."""
    transcript = write_transcript("no-cite", chat_question((CHAT_A, CHAT_B_MISMATCH), cite=None))
    wire_allows("control: a chat question that cites no page item is not compared", set_write(ITEM), transcript)


def case_wire_other_item_is_allowed():
    """Control, green on the old code: a chat question that cites another item is not compared to this one."""
    transcript = write_transcript("other-cite", chat_question((CHAT_A, CHAT_B_MISMATCH), cite=OTHER_ITEM))
    wire_allows("control: a chat question that cites another page item is not compared", set_write(ITEM), transcript)


def case_wire_missing_letter_is_allowed():
    """Control, green on the old code: an option whose letter the chat does not write is not compared."""
    transcript = write_transcript("no-b", chat_question((CHAT_A,)))
    wire_allows("control: a chat that writes no line for b is not compared for b", set_write(ITEM), transcript)


# ------------------------------------------------------------------ 2. the recommended field (uniform-pick)

def decision_with(**over):
    """The data of a decision whose option b widens a shared tool. Keys in `over` set or replace fields."""
    options = [{"key": "a", "label": "Keep it as is", "gain": "g", "lose": "l"},
               {"key": "b", "label": "Allow merge --role", "gain": "g", "lose": "l", "widens": True}]
    data = {"kind": "decision", "options": options}
    data.update(over)
    return data


def widens_refuses(name, data):
    fn = getattr(question_form, "widens_pick_hit", None)
    got = fn(data) if fn is not None else NOT_BUILT
    check(name, bool(got) and got is not NOT_BUILT, "want a widening refusal, got %r" % (got,))


def widens_passes(name, data):
    got = question_form.widens_pick_hit(data)
    check(name, got == "", "want a pass, got %r" % (got,))


def case_recommended_naming_widening_is_refused():
    """uniform-pick reads `recommended` as it reads `pick`: a recommended option that widens a shared tool is refused.
    On the old code the field is ignored, so the write passes."""
    widens_refuses("recommended: a recommended key that widens a shared tool is refused",
                   decision_with(pick="a", recommended="b"))
    widens_refuses("recommended: a recommended key that widens is refused when pick is absent",
                   decision_with(recommended="b"))
    widens_refuses("recommended: a list recommended that holds a widening key is refused",
                   decision_with(pick=["a"], recommended=["a", "b"]))


def case_pick_naming_widening_still_refused():
    """Control, green on the old code: a pick that names a widening option is still refused."""
    widens_refuses("control: a pick that widens is still refused", decision_with(pick="b"))


def case_recommended_plain_passes():
    """Controls, green on the old code: a recommended option that does not widen passes, with pick or without."""
    widens_passes("control: a recommended key that does not widen passes", decision_with(pick="a", recommended="a"))
    widens_passes("control: a recommended key that does not widen passes with no pick", decision_with(recommended="a"))


def case_recommended_is_a_drawn_field():
    """The page draws `recommended` (its itemFields block lists it), so a write that names it is not refused as an
    item-field-rendered field. On the old code the page does not list it and the write is refused."""
    tqf.page("recommended: an item that names a plain recommended option is a drawn field and passes", "set",
             tqf.entry_of(tcj.good_page_item(recommended="a")), None)


def case_pick_is_a_drawn_field():
    """Control, green on the old code: `pick` is drawn, so a write that names it passes."""
    tqf.page("control: an item that names pick is a drawn field and passes", "set",
             tqf.entry_of(tcj.good_page_item(pick="a")), None)


# ------------------------------------------------------------------ the run

CASES = (case_fn_equal_labels_pass, case_fn_case_and_spaces_fold, case_fn_prefix_either_way_passes,
         case_fn_differing_label_refuses_naming_the_letter, case_fn_no_cited_id_passes,
         case_fn_other_item_passes, case_fn_letter_missing_from_chat_passes, case_fn_letter_is_position,
         case_wire_differing_set_is_refused, case_wire_differing_update_is_refused,
         case_wire_matching_set_is_allowed, case_wire_short_form_is_allowed, case_wire_no_cited_id_is_allowed,
         case_wire_other_item_is_allowed, case_wire_missing_letter_is_allowed,
         case_recommended_naming_widening_is_refused, case_pick_naming_widening_still_refused,
         case_recommended_plain_passes, case_recommended_is_a_drawn_field, case_pick_is_a_drawn_field)
FN_CASES = tuple(c for c in CASES if c.__name__.startswith("case_fn_"))


def main():
    behaviour = "behaviour" in sys.argv[1:]
    for case in CASES:
        if behaviour and case in FN_CASES:
            continue
        try:
            case()
        except Exception as exc:
            check(case.__name__, False, "raised %s: %s" % (type(exc).__name__, exc))
    print("FAIL: %d failed" % len(FAILED) if FAILED else "all checks passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
