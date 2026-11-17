#!/usr/bin/env python3
"""Cases for the option-letters-frozen rule of hooks/question_form.py (frozen_letters_hit).

Decision docs/decisions/option-keys-are-letters.md, ruling R60 (roadmap r60, 15:07 CST Nov 12): triage keeps each
option's letter as the asking session wrote it. A rule-driven change adds a `note` to an option and reorders nothing.
Each option carries a short unique `id`. An open decision carries `shown`: the options as first shown, in order, each
as {key, id, label}.

Rule option-letters-frozen refuses a set or update of an open decision on this repo's waiting page whose write carries
`options` when:
  - it carries no `shown`;
  - an option has no non-empty string `id`, or two options share one;
  - an option at position i < len(shown) differs from shown[i] in key or id (a reorder, a changed id), or its label is
    not a non-empty string;
  - there are fewer options than shown; or
  - the options and shown differ in length, so an option appended on an update is shown on the same write (ruling R60).
A reworded label passes when the option's key and id still equal shown[i]'s: the letter keeps its meaning (owner,
Nov 15 2026, evening CST: the freeze is for options that flip-flop between the chat and the page, not for their wording).
`shown` keeps the labels as first shown, so a reword is the options' label differing from shown's.
A first set with options must carry shown equal to its own options (key, id and label). An update that appends options
carries shown extended by them.
A note on an option, with key, id and label unchanged, passes. Tasks, notes, closed items and writes with no options pass,
and so does a write to another artifact (item_hit runs the rule on the waiting page only).

Three layers, one file:
  fn:   question_form.frozen_letters_hit(op, data), called directly, as option_letter_hit is.
  wire: hooks/guard.py run as the hook process, through test_question_form_option_labels (one home for guard_hook).
  page: the page's itemFields block lists `shown`, the field a write carries.

The wire cases point GUARD_ITEM_FIELDS_PAGE at a fixture page whose itemFields list is the real one plus `shown`, so
item-field-rendered does not refuse the field before the freeze rule judges it. The page itself is judged by its own case.

When hooks/question_form.py has no frozen_letters_hit, frozen() reads "no refusal", so each refusal case fails on its
own assertion (an allow, or an empty verdict), never on a crash or an import error. Each refusal's fragment names the
option's letter or the field, never the label, so one message shape serves a reword that still fails.

Standard library only, no test runner. Run from the repository root:

    python3 hooks/test_question_form_letters_frozen.py
"""
import copy
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_call_judge as tcj  # noqa: E402  the fixture home: PAGE_URL, PAGE_REPO, PAGE_ITEMS, ROOT, check, FAILED
import test_question_form as tqf  # noqa: E402  the question_form and guard modules, and the verdict step
import test_question_form_option_labels as tql  # noqa: E402  label_item, write_transcript, guard_hook, wire_refuses, wire_allows

check, FAILED = tcj.check, tcj.FAILED
question_form, guard = tqf.question_form, tqf.guard
RULE = "option-letters-frozen"
ITEM = "frozen-letters-case"  # the item these cases write; no reason may name it
OTHER_URL = "https://claude.ai/artifact/frozenotherpage"  # an artifact the fixture repo's registry does not hold
ABSENT = object()  # a field set to ABSENT is left out of the write


def opt(key, label, option_id, **extra):
    """An option as a session writes it: key, id and label, with the gain and lose lines a decision needs."""
    found = {"key": key, "id": option_id, "label": label, "gain": "The change lands today.",
             "lose": "Nobody reads it first."}
    found.update(extra)
    return found


RED, BLUE, GREEN = opt("a", "Red", "red"), opt("b", "Blue", "blue"), opt("c", "Green", "green")
OPTIONS = [RED, BLUE]
# Item 646 as triage left it: the blue option now sits at position a, the red one at position b. Each key is its position's
# letter, so option_letter_hit reads the swap as valid.
SWAPPED = [dict(BLUE, key="a"), dict(RED, key="b")]
NOTED = [dict(RED, note="Now means the red that shipped in 2026."), BLUE]
# Option a reworded, key and id held. `shown` stays as first shown (shown_of(OPTIONS)), so the label differs from it.
REWORDED = [dict(RED, label="Crimson"), BLUE]


def shown_of(options):
    """The `shown` list a write carries: each option's key, id and label, in order."""
    return [{"key": o["key"], "id": o["id"], "label": o["label"]} for o in options]


def full_size():
    """The full size: 26 options keyed a to z, each with its own id."""
    return [opt(chr(97 + i), "Choice %02d" % (i + 1), "choice-%02d" % (i + 1)) for i in range(26)]


def decision(options, shown=ABSENT, **over):
    """An open waiting-page decision with `options`. `shown` is set when given, and left out when it is ABSENT. The
    options keep the ids they were given (ids=False): a bare option in a case must stay bare."""
    data = tql.label_item(ITEM, options=copy.deepcopy(options), ids=False)
    if shown is ABSENT:
        data.pop("shown", None)
    else:
        data["shown"] = copy.deepcopy(shown)
    data.update(over)
    return data


def frozen(op, data):
    """question_form.frozen_letters_hit(op, data): the matched text, "" for a pass. Without the function no rule
    refuses, so the call reads "" and each refusal case fails on its own assertion."""
    fn = getattr(question_form, "frozen_letters_hit", None)
    if fn is None:
        return ""
    try:
        return fn(op, data)
    except Exception as exc:  # a crash is a wrong verdict, shown by name
        return "RAISED %s: %s" % (type(exc).__name__, exc)


def refuses(name, got, fragment):
    """A refusal: a non-empty matched text that names `fragment`, the one cause the case writes."""
    named = bool(got) and re.search(r"\b%s\b" % re.escape(fragment), str(got), re.I) is not None
    check(name, named, "want a refusal naming %r, got %r" % (fragment, got))


def passes(name, got):
    check(name, got == "", "want a pass, got %r" % (got,))


def set_call(data, action="set"):
    """An ArtifactData call that writes `data` as item ITEM."""
    return {"action": action, "collection": tcj.PAGE_ITEMS, "doc_id": ITEM, "data": data}


def plain_chat():
    """A transcript with no chat question, so the option-labels rule has nothing to compare."""
    return tql.write_transcript("frozen-plain", "A reply with no question in it.")


def wire_refuses_frozen(name, call, transcript):
    """A deny that names option-letters-frozen. tql.wire_refuses names the label rule, so this case reads its own."""
    decision_word, reason = tql.guard_hook(name, call, transcript)
    check(name, decision_word == "deny" and RULE in reason,
          "want a deny naming %s, got %s: %r" % (RULE, decision_word, reason[:200]))


# ------------------------------------------------------------------ 1. the function (fn:)

def case_fn_no_shown_is_refused():
    refuses("fn: a set with options and no shown is refused", frozen("set", decision(OPTIONS)), "shown")
    refuses("fn: an update with options and no shown is refused", frozen("update", decision(OPTIONS)), "shown")


def case_fn_item_646_swap_is_refused():
    """The 14:39 CST swap: option_letter_hit passes it (control below), so only the freeze refuses it."""
    refuses("fn: the item-646 swap (options a and b exchanged, keys kept by position) is refused",
            frozen("update", decision(SWAPPED, shown=shown_of(OPTIONS))), "option a")


def case_fn_control_letter_rule_reads_the_swap_as_valid():
    """Control, green on the current head: the existing letter rule does not see the swap, so the freeze must."""
    passes("control: option_letter_hit reads the item-646 swap as valid",
           question_form.option_letter_hit("update", decision(SWAPPED)))


def case_fn_two_labels_swapped_is_refused():
    labels_swapped = [dict(RED, label="Blue"), dict(BLUE, label="Red")]
    refuses("fn: two labels swapped, keys and ids kept, is refused",
            frozen("update", decision(labels_swapped, shown=shown_of(OPTIONS))), "option a")


def case_fn_swap_in_another_case_or_padding_is_refused():
    """The label comparison trims and case-folds, so a swap that only changes case or padding is still a swap."""
    cased = [dict(RED, label="BLUE"), dict(BLUE, label="red")]
    refuses("fn: two labels swapped in another case, keys and ids kept, is refused",
            frozen("update", decision(cased, shown=shown_of(OPTIONS))), "option a")
    padded = [dict(RED, label=" Blue "), dict(BLUE, label="Red")]
    refuses("fn: a label padded with spaces that equals another shown label is refused",
            frozen("update", decision(padded, shown=shown_of(OPTIONS))), "option a")


def case_fn_reword_passes():
    """Case 1: a reworded label passes when the key and id at every position still equal the shown entry's."""
    passes("fn: option a reworded, key and id held at every position, passes",
           frozen("update", decision(REWORDED, shown=shown_of(OPTIONS))))
    both = [dict(RED, label="Crimson"), dict(BLUE, label="Navy")]
    passes("fn: every option reworded, key and id held, passes", frozen("update", decision(both, shown=shown_of(OPTIONS))))
    full = full_size()
    last = full[:-1] + [dict(full[-1], label="Choice 26, reworded")]
    passes("fn: 26 options with option z reworded, key and id held, pass",
           frozen("update", decision(last, shown=shown_of(full))))


def case_fn_reword_with_a_reorder_is_refused():
    """Case 2: a reword beside a reorder is refused. The reorder shows as a changed id (keys follow positions) or as a
    changed key (keys follow the options); the second keeps every id, so a rule that read ids alone would pass it."""
    ids_moved = [dict(BLUE, key="a", label="Navy"), dict(RED, key="b")]
    refuses("fn: option a reworded and options a and b swapped, keys by position, is refused",
            frozen("update", decision(ids_moved, shown=shown_of(OPTIONS))), "option a")
    keys_moved = [dict(RED, key="b", label="Crimson"), dict(BLUE, key="a")]
    refuses("fn: option a reworded and its key moved to b, id held, is refused",
            frozen("update", decision(keys_moved, shown=shown_of(OPTIONS))), "option a")


def case_fn_reword_with_a_changed_id_is_refused():
    """Case 3: the reword alone passes (case_fn_reword_passes), so the changed id is the one cause of the refusal."""
    refuses("fn: option a reworded and its id changed is refused",
            frozen("update", decision([dict(RED, label="Crimson", id="crimson"), BLUE], shown=shown_of(OPTIONS))),
            "option a")


def case_fn_reworded_label_must_be_a_non_empty_string():
    """Case 4: a label stays a non-empty string. The fragment is the option's letter: the one cause is that option."""
    for name, bad in (("empty", ""), ("None", None), ("a number", 7), ("a list", ["Red"])):
        refuses("fn: option a reworded to a label that is %s is refused" % name,
                frozen("update", decision([dict(RED, label=bad), BLUE], shown=shown_of(OPTIONS))), "option a")
    no_label = {k: v for k, v in RED.items() if k != "label"}
    refuses("fn: option a with no label is refused",
            frozen("update", decision([no_label, BLUE], shown=shown_of(OPTIONS))), "option a")
    refuses("fn: option b reworded to an empty label is refused",
            frozen("update", decision([RED, dict(BLUE, label="")], shown=shown_of(OPTIONS))), "option b")


def case_fn_reword_with_an_append():
    """Case 5: a reword of option a beside an appended option c passes when shown is extended by c. Shown keeps the
    first labels. Left short, the write is refused for its shown list, as an append with no reword is."""
    appended = REWORDED + [GREEN]
    passes("fn: option a reworded while option c is appended, shown extended, passes",
           frozen("update", decision(appended, shown=shown_of(OPTIONS + [GREEN]))))
    refuses("fn: the same reword and append with shown left short is refused",
            frozen("update", decision(appended, shown=shown_of(OPTIONS))), "shown")


def case_fn_lone_letter_id_is_refused():
    """An id that is a lone letter would read as a key. The reworded write, whose shown keeps the first id, is refused too."""
    lone = [dict(RED, id="r"), BLUE]
    refuses("fn: an option whose id is a lone letter is refused", frozen("set", decision(lone, shown=shown_of(lone))),
            "lone letter")
    refuses("fn: a reworded option whose id is a lone letter is refused",
            frozen("update", decision([dict(RED, label="Crimson", id="r"), BLUE], shown=shown_of(OPTIONS))), "lone letter")


def case_fn_changed_id_is_refused():
    refuses("fn: a changed id at a shown position is refused (the freeze compares id)",
            frozen("update", decision([dict(RED, id="crimson"), BLUE], shown=shown_of(OPTIONS))), "option a")


def case_fn_fewer_options_is_refused():
    refuses("fn: an update with fewer options than shown is refused",
            frozen("update", decision([RED], shown=shown_of(OPTIONS))), "option b")


def case_fn_append_must_extend_shown():
    """R60: an option appended on an update is shown on the same write, so shown is as long as the options. The append
    that leaves shown short is refused; the one that extends it passes (case_fn_passes)."""
    refuses("fn: an update that appends an option without extending shown is refused",
            frozen("update", decision(OPTIONS + [GREEN], shown=shown_of(OPTIONS))), "shown")


def case_fn_first_set_must_equal_its_shown():
    """A first set's shown equals its own options, so an option the shown list does not hold is refused. This reads the
    brief's strict rule for a first set; an update may append (case_fn_passes). Flagged in the report."""
    refuses("fn: a first set whose shown is shorter than its options is refused",
            frozen("set", decision(OPTIONS + [GREEN], shown=shown_of(OPTIONS))), "shown")


def case_fn_option_id_rules():
    bare = [{k: v for k, v in o.items() if k != "id"} for o in OPTIONS]
    refuses("fn: an option with no id is refused (shown matches, so the id rule alone refuses)",
            frozen("set", decision(bare, shown=copy.deepcopy(bare))), "id")
    empty = [dict(RED, id=""), BLUE]
    refuses("fn: an option whose id is empty is refused", frozen("set", decision(empty, shown=shown_of(empty))), "id")
    same = [dict(RED, id="same"), dict(BLUE, id="same")]
    refuses("fn: two options that share an id are refused", frozen("set", decision(same, shown=shown_of(same))), "id")


def case_fn_empty_and_full_size():
    """The empty state (an update that empties the options) is refused, and the full size (26 options, keys a to z) passes."""
    refuses("fn: an update that empties the options is refused",
            frozen("update", decision([], shown=shown_of(OPTIONS))), "option a")
    full = full_size()
    passes("fn: 26 options keyed a to z, each matching its shown entry, pass",
           frozen("set", decision(full, shown=shown_of(full))))


def case_fn_passes():
    passes("fn: a set whose options match its shown passes",
           frozen("set", decision(OPTIONS, shown=shown_of(OPTIONS))))
    passes("fn: an update that appends an option, shown on the same write, passes",
           frozen("update", decision(OPTIONS + [GREEN], shown=shown_of(OPTIONS + [GREEN]))))
    passes("fn: a note added to an option, key, id and label unchanged, passes",
           frozen("update", decision(NOTED, shown=shown_of(OPTIONS))))
    passes("fn: a task with reordered options and no shown passes", frozen("update", decision(SWAPPED, kind="task")))
    passes("fn: a note with reordered options and no shown passes", frozen("update", decision(SWAPPED, kind="note")))
    passes("fn: a closed item with reordered options and no shown passes",
           frozen("update", decision(SWAPPED, status="closed")))
    passes("fn: a write with no options passes", frozen("update", {"status": "open", "context": "Still open."}))


def case_fn_other_artifact_passes():
    """A reordered write with no shown to another artifact: the freeze is judged on the waiting page only."""
    tool_input = {"action": "set", "collection": tcj.PAGE_ITEMS, "doc_id": ITEM, "url": OTHER_URL,
                  "data": decision(SWAPPED)}
    try:
        got = guard.data_tool_hit(tool_input, tcj.PAGE_REPO)
    except Exception as exc:  # a crash is a wrong verdict, shown by name
        got = ("RAISED", "%s: %s" % (type(exc).__name__, exc))
    tqf.verdict("guard: a reordered write with no shown to another artifact passes", got, None)


# ------------------------------------------------------------------ 2. the wire (wire:, through hooks/guard.py)

def case_wire_swap_is_refused():
    wire_refuses_frozen("wire: a set that swaps options a and b, with shown, is refused by option-letters-frozen",
                        set_call(decision(SWAPPED, shown=shown_of(OPTIONS))), plain_chat())


def case_wire_no_shown_update_is_refused():
    wire_refuses_frozen("wire: an update with options and no shown is refused by option-letters-frozen",
                        set_call(decision(OPTIONS), action="update"), plain_chat())


def case_wire_matching_set_is_allowed():
    tql.wire_allows("wire: a set whose options match its shown is allowed",
                    set_call(decision(OPTIONS, shown=shown_of(OPTIONS))), plain_chat())


def case_wire_note_is_allowed():
    tql.wire_allows("wire: a note added to an option is allowed",
                    set_call(decision(NOTED, shown=shown_of(OPTIONS)), action="update"), plain_chat())


def case_wire_reword_is_allowed():
    tql.wire_allows("wire: a reworded label, key and id held, is allowed",
                    set_call(decision(REWORDED, shown=shown_of(OPTIONS)), action="update"), plain_chat())


def case_wire_reason_names_no_target():
    decision_word, reason = tql.guard_hook("frozen-wire-target", set_call(decision(SWAPPED, shown=shown_of(OPTIONS))),
                                           plain_chat())
    check("wire: the refusal names the rule and no item id, page URL or repo path",
          decision_word == "deny" and RULE in reason and ITEM not in reason and tcj.PAGE_URL not in reason
          and tcj.PAGE_REPO not in reason,
          "want a deny naming %s with no target, got %s: %r" % (RULE, decision_word, reason[:200]))


# ------------------------------------------------------------------ 3. the page (page: its itemFields block)

def case_page_lists_shown():
    """The guard refuses a field the page's itemFields block does not list, before the freeze reads it."""
    fields = question_form._item_fields(question_form.ITEM_FIELDS_PAGE) or []
    check("page: the itemFields block lists shown, so a write that carries shown is not refused as an undrawn field",
          "shown" in fields, "the page's itemFields block does not list shown")


def case_fn_options_that_is_not_a_list_is_refused():
    """An update whose `options` is a mapping (a delete marker) would drop every option unjudged."""
    data = decision(OPTIONS, shown_of(OPTIONS))
    data["options"] = {"__delete__": True}
    refuses("fn: an open decision whose options is not a list is refused", frozen("update", data), "options")


CASES = (case_fn_options_that_is_not_a_list_is_refused, case_fn_no_shown_is_refused, case_fn_item_646_swap_is_refused,
         case_fn_control_letter_rule_reads_the_swap_as_valid, case_fn_two_labels_swapped_is_refused,
         case_fn_swap_in_another_case_or_padding_is_refused, case_fn_reword_passes,
         case_fn_reword_with_a_reorder_is_refused, case_fn_reword_with_a_changed_id_is_refused,
         case_fn_reworded_label_must_be_a_non_empty_string, case_fn_reword_with_an_append,
         case_fn_changed_id_is_refused, case_fn_fewer_options_is_refused, case_fn_append_must_extend_shown,
         case_fn_first_set_must_equal_its_shown, case_fn_option_id_rules, case_fn_lone_letter_id_is_refused,
         case_fn_empty_and_full_size, case_fn_passes, case_fn_other_artifact_passes,
         case_wire_swap_is_refused, case_wire_no_shown_update_is_refused, case_wire_matching_set_is_allowed,
         case_wire_note_is_allowed, case_wire_reword_is_allowed, case_wire_reason_names_no_target, case_page_lists_shown)


def fields_page():
    """A fixture page whose itemFields block is the real list plus `shown`, read by the guard through the seam."""
    folder = os.path.join(tcj.ROOT, "frozen-fields")
    os.makedirs(folder, exist_ok=True)
    fields = list(question_form._item_fields(question_form.ITEM_FIELDS_PAGE) or [])
    if "shown" not in fields:
        fields.append("shown")
    path = os.path.join(folder, "page.html")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write('<!doctype html><script type="application/json" id="itemFields">%s</script>\n' % json.dumps(fields))
    return path


def main():
    seam = question_form.ITEM_FIELDS_SEAM
    before = os.environ.get(seam)
    os.environ[seam] = fields_page()
    try:
        for case in CASES:
            try:
                case()
            except Exception as exc:  # a crash is a wrong verdict, shown by name
                check(case.__name__, False, "raised %s: %s" % (type(exc).__name__, exc))
    finally:
        if before is None:
            os.environ.pop(seam, None)
        else:
            os.environ[seam] = before
    print("FAIL: %d failed" % len(FAILED) if FAILED else "all checks passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
