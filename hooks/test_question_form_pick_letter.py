#!/usr/bin/env python3
"""Cases for the pick-letter-matches-label rule of hooks/question_form.py and its refusal in hooks/guard.py.

Decision option-keys-are-letters names the rule. It refuses a set or update of an open waiting-page decision whose write
carries `options`, when an item text field (title, context, why, an option's text fields, or a step) holds a pick sentence:

    `pick X` or `option X`   (X a letter, any case)

followed, after an optional space, colon, dash, or an opening paren or quote, by words that match the START of the label of
a DIFFERENT option Y and not the label of X. The label is matched the way _chat_short_form reads it: the folded words are
the label's start up to a word boundary, and the fold is chat_page_label_hit's (case, spacing and the marks `*`, `_` and
backtick dropped). Words that match the labels of two other options fit no one label, so the rule does not refuse them: it
asks, and never guesses. The refusal names the label text and its real letter, since the label decides.

Two layers, one file:
  item: question_form.item_hit(op, entry, cwd), the page rules in order. The rule name and its matched text.
  wire: hooks/guard.py run as the hook process (tql.guard_hook). A deny that names the rule and a reason that names the label.
        The letter is checked on the matched text only: the static part of a reason carries standalone letters, so a
        letter in the reason proves nothing.

Section 4 pins the spelling forms (tails, quotes, a bold letter, a line break), a reason that gives no reword remedy, and
a record that names the no-options limit and the shared-tool ruling. Each pass case is a control.

Standard library only, no test runner. Run from the repository root:

    python3 hooks/test_question_form_pick_letter.py
"""
import copy
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_call_judge as tcj  # noqa: E402  the fixture home: PAGE_URL, PAGE_ITEMS, PAGE_REPO, REPO, check, FAILED
import test_question_form as tqf  # noqa: E402  the question_form module and the verdict step for passes
import test_question_form_option_labels as tql  # noqa: E402  label_item, write_transcript, guard_hook

check, FAILED = tcj.check, tcj.FAILED
question_form = tqf.question_form
RULE = "pick-letter-matches-label"
ITEM = "pick-letter-case"  # the item these cases write
DECISION_DOC = os.path.join(tcj.REPO, "docs", "decisions", "option-keys-are-letters.md")

LABEL_A = "100 rows a page"
LABEL_B = "Bookmark plus 100 rows a page"
INCIDENT_PICK = "Pick a: bookmark plus 100 rows a page."  # the incident: letter a, the words of label b


def option(key, label):
    """An option as a session writes it: key and label, with the gain and lose lines a decision needs."""
    return {"key": key, "label": label, "gain": "The page shows the rows at once.", "lose": "The old view stays."}


INCIDENT = [option("a", LABEL_A), option("b", LABEL_B)]


def item(options=None, **over):
    """An open waiting-page decision with `options` (the incident pair by default), its form lines in context, and `over`
    replacing fields. label_item gives each option an id and the `shown` list, so only the pick text varies by case."""
    return tql.label_item(ITEM, options=copy.deepcopy(INCIDENT if options is None else options), **over)


def write(data, action="set"):
    """An ArtifactData call that writes `data` as item ITEM."""
    return {"action": action, "collection": tcj.PAGE_ITEMS, "doc_id": ITEM, "data": data}


def open_decision(data):
    """The scope the rule judges: an open decision that carries options."""
    return isinstance(data, dict) and data.get("kind", "decision") == "decision" and data.get("status") != "closed" \
        and isinstance(data.get("options"), list)


def item_verdict(action, entry):
    """(rule, matched) from question_form.item_hit for one write. A crash is shown by name, never raised."""
    try:
        return question_form.item_hit(action, entry, tcj.PAGE_REPO)
    except Exception as exc:  # a crash is a wrong verdict, shown by name
        return ("RAISED", "%s: %s" % (type(exc).__name__, exc))


def wire(slug, entry):
    """(decision, reason) from hooks/guard.py run as the hook process, with a chat that asks nothing."""
    try:
        return tql.guard_hook(slug, entry, tql.write_transcript("pick-letter-plain", "A reply with no question in it."))
    except Exception as exc:  # a crash is a wrong verdict, shown by name
        return "error", "%s: %s" % (type(exc).__name__, exc)


def refuses_pick(slug, data, label, letter, action="set"):
    """A refusal by the rule at both layers. The scope is checked first, so a pass cannot hide behind a wrong write."""
    entry = write(data, action)
    check(slug + " (scope: an open decision that carries options)", open_decision(data),
          "the write is not an open decision that carries options")
    rule, matched = item_verdict(action, entry)
    check(slug + " (item: the rule is named)", rule == RULE, "want rule %s, got %r" % (RULE, rule))
    check(slug + " (item: the matched text names the label)", label.lower() in str(matched).lower(),
          "want %r in the matched text, got %r" % (label, matched))
    check(slug + " (item: the matched text names the letter)", re.search(r"\b%s\b" % letter, str(matched), re.I) is not None,
          "want the letter %r in the matched text, got %r" % (letter, matched))
    decision_word, reason = wire(slug, entry)
    check(slug + " (wire: denied)", decision_word == "deny", "want deny, got %s: %r" % (decision_word, reason[:200]))
    check(slug + " (wire: the deny names the rule)", RULE in reason, "want %s in the reason, got %r" % (RULE, reason[:200]))
    check(slug + " (wire: the reason names the label)", label.lower() in reason.lower(),
          "want %r in the reason, got %r" % (label, reason[:200]))


def passes_pick(slug, data, scope_ok, scope_what, action="set"):
    """A pass at both layers, after the scope is checked: the write is the kind the case names."""
    entry = write(data, action)
    check(slug + " (scope: %s)" % scope_what, scope_ok, "the write is not %s" % scope_what)
    tqf.verdict(slug + " (item: no refusal)", item_verdict(action, entry), None)
    decision_word, reason = wire(slug, entry)
    check(slug + " (wire: allowed)", decision_word == "allow", "want allow, got %s: %r" % (decision_word, reason[:200]))


# ------------------------------------------------------------------ 1. refusals: the incident and its forms

def case_incident_is_refused():
    """The 14:39 incident: option a is "100 rows a page", option b is "Bookmark plus 100 rows a page", and the why says
    "Pick a" for the bookmark option. The reason names the label of b and the letter b."""
    refuses_pick("pick-incident", item(why=INCIDENT_PICK), LABEL_B, "b")


def case_incident_update_is_refused():
    """The rule judges an update that carries options as it judges a set."""
    refuses_pick("pick-incident-update", item(why=INCIDENT_PICK), LABEL_B, "b", action="update")


def case_step_text_is_refused():
    """A pick sentence in a step is judged as the same text."""
    refuses_pick("pick-step", item(steps=[INCIDENT_PICK]), LABEL_B, "b")


def case_context_text_is_refused():
    """A pick sentence in context, after the form lines, is judged. "Option A" is the pick word of the rule."""
    context = item()["context"] + "\nOption A: bookmark plus 100 rows a page."
    refuses_pick("pick-context", item(context=context), LABEL_B, "b")


def case_option_gain_text_is_refused():
    """A pick sentence in an option's own text (its gain) is judged: the option fields are item text."""
    options = [option("a", LABEL_A), option("b", LABEL_B)]
    options[0]["gain"] = INCIDENT_PICK
    refuses_pick("pick-option-gain", item(options=options), LABEL_B, "b")


def case_upper_case_and_spacing_is_refused():
    """The pick word and the letter in any case, and the words folded for case and spacing."""
    refuses_pick("pick-upper", item(why="PICK A:  Bookmark   plus 100 rows a page."), LABEL_B, "b")


def case_full_size_is_refused():
    """26 options, keyed a to z. Option x carries label b's words, and the pick names z: the refusal names x."""
    labels = ["Choice %02d" % (i + 1) for i in range(26)]
    labels[23] = LABEL_B  # the letter x
    options = [option(chr(97 + i), labels[i]) for i in range(26)]
    refuses_pick("pick-full-size", item(options=options, why="Pick z: bookmark plus 100 rows a page."), LABEL_B, "x")


# ------------------------------------------------------------------ 2. passes: the letter and the label agree, or fit no label

def case_agreeing_pick_passes():
    """Control: the letter names the option whose label the words are."""
    passes_pick("pick-agree", item(why="Pick b: bookmark plus 100 rows a page."),
                open_decision(item()), "an open decision that carries options")


def case_letter_then_parenthesis_passes():
    """Control: the words in parentheses are the letter's own label."""
    passes_pick("pick-paren", item(why="Pick a (100 rows a page)."), open_decision(item()),
                "an open decision that carries options")


def case_closed_item_passes():
    """Control: a closed item is not judged, even with the incident text."""
    data = item(why=INCIDENT_PICK, status="closed")
    passes_pick("pick-closed", data, data.get("status") == "closed", "a closed item that carries options")


def case_task_passes():
    """Control: a task is not judged, even with the incident text in its step and options on the write."""
    data = tcj.with_frozen_fields(dict(tcj.good_task_item(step=INCIDENT_PICK), options=copy.deepcopy(INCIDENT)))
    passes_pick("pick-task", data, data.get("kind") == "task", "a task that carries options")


def case_note_passes():
    """Control: a note is not judged, even with the incident text."""
    data = dict(item(why=INCIDENT_PICK), kind="note")
    passes_pick("pick-note", data, data.get("kind") == "note", "a note that carries options")


def case_bare_letter_passes():
    """Control: a pick word and a letter with no following words name no label."""
    passes_pick("pick-bare", item(why="Pick a."), open_decision(item()), "an open decision that carries options")


def case_words_fitting_two_labels_pass():
    """Control: the words are the start of two other labels, b and c, and of neither label of a. They fit no one label,
    so the rule asks and never guesses: no refusal."""
    options = [option("a", LABEL_A), option("b", "Bookmark only"), option("c", LABEL_B)]
    passes_pick("pick-ambiguous", item(options=options, why="Pick a: bookmark."), open_decision(item(options=options)),
                "an open decision that carries options")


def case_words_of_own_label_pass():
    """Control: the words are the label of the letter itself, though they also start label b. The rule does not refuse a
    match on the label of X."""
    options = [option("a", "Bookmark"), option("b", LABEL_B)]
    passes_pick("pick-own-label", item(options=options, why="Pick a: bookmark."), open_decision(item(options=options)),
                "an open decision that carries options")


def case_words_matching_no_label_pass():
    """Control: a letter followed by text that matches no option label."""
    passes_pick("pick-prose", item(why="Pick a: keep the rows as they are."), open_decision(item()),
                "an open decision that carries options")


def case_option_word_prose_passes():
    """Control: "Option A" followed by prose that matches no label."""
    passes_pick("pick-option-prose", item(why="Option A is a fine choice, but the page needs a decision."),
                open_decision(item()), "an open decision that carries options")


def case_no_options_passes():
    """Control: an update that carries no options is not judged, even with the incident text."""
    data = {"status": "open", "why": INCIDENT_PICK}
    passes_pick("pick-no-options", data, "options" not in data, "an update that carries no options", action="update")


def case_empty_options_passes():
    """Control, the empty state: options is an empty list, so no label is there to match."""
    data = item(options=[], why=INCIDENT_PICK)
    passes_pick("pick-empty-options", data, open_decision(data) and data["options"] == [],
                "an open decision with an empty options list")


def case_full_size_agreeing_pass():
    """Control, the full size: 26 options, and the pick names z, the letter whose label the words are."""
    labels = ["Choice %02d" % (i + 1) for i in range(26)]
    labels[25] = LABEL_B  # the letter z
    options = [option(chr(97 + i), labels[i]) for i in range(26)]
    data = item(options=options, why="Pick z: bookmark plus 100 rows a page.")
    passes_pick("pick-full-size-agree", data, open_decision(data), "an open decision that carries options")


# ------------------------------------------------------------------ 3. the record

def case_docs_name_the_rule():
    """The decision record that holds the rule names it, so a reader finds the rule where the letters are ruled."""
    with open(DECISION_DOC, encoding="utf-8") as handle:
        text = handle.read()
    check("docs: the option-keys record names rule " + RULE, RULE in text,
          "docs/decisions/option-keys-are-letters.md does not name the rule")


# ------------------------------------------------------------------ 4. the spelling forms, the reason, the record

SHARED_TOOL = "a repo changes to fit a shared tool"
QUESTIONS_DOC = os.path.join(tcj.REPO, "docs", "decisions", "questions-go-to-owner.md")
PICK_BLOCK_OPENER = "A pick sentence in an item also names"


def pick_block(text):
    """The pick-letter block of the decision record: its opening paragraph and the bullets under it, up to the next line that
    is neither a bullet nor blank."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if PICK_BLOCK_OPENER in line), None)
    if start is None:
        return ""
    block = []
    for line in lines[start:]:
        if block and line and not line.startswith("  - "):
            break
        block.append(line)
    return "\n".join(block)


def bullet_with(text, marker):
    """The bullet that holds `marker`: the `- ` line it sits on or under, and the lines that wrap below that line."""
    lines = text.splitlines()
    hit = next((i for i, line in enumerate(lines) if marker in line), None)
    if hit is None:
        return ""
    top = hit
    while top > 0 and lines[top] and not lines[top].startswith("- "):
        top -= 1
    end = hit + 1
    while end < len(lines) and lines[end] and not lines[end].startswith("- "):
        end += 1
    return "\n".join(lines[top:end])


def case_recommended_tail_is_refused():
    """A pick whose words end in a parenthesised tail, such as (Recommended), names the option its words name."""
    refuses_pick("pick-recommended-tail", item(why="Pick a: bookmark plus 100 rows a page (Recommended)."), LABEL_B, "b")


def case_comma_tail_is_refused():
    """A pick whose words run on past a comma names the option its words name: a comma does not end the words."""
    refuses_pick("pick-comma-tail", item(why="Pick a: bookmark plus 100 rows a page, which the owner should take."),
                 LABEL_B, "b")


def case_dash_tail_is_refused():
    """A pick whose words end in an em dash and a tail names the option its words name."""
    refuses_pick("pick-dash-tail", item(why="Pick a: bookmark plus 100 rows a page \u2014 recommended."), LABEL_B, "b")


def case_curly_quoted_words_are_refused():
    """The words of a pick in curly quotes name the option the quoted words name."""
    refuses_pick("pick-curly-quotes", item(why="Pick a: \u201cbookmark plus 100 rows a page\u201d."), LABEL_B, "b")


def case_straight_quoted_words_are_refused():
    """The words of a pick in straight quotes name the option the quoted words name."""
    refuses_pick("pick-straight-quotes", item(why='Pick a: "bookmark plus 100 rows a page".'), LABEL_B, "b")


def case_bold_letter_is_refused():
    """A pick whose letter is in markdown emphasis, as in Pick **a**, names the option its words name."""
    refuses_pick("pick-bold-letter", item(why="Pick **a**: bookmark plus 100 rows a page."), LABEL_B, "b")


def case_newline_before_words_is_refused():
    """A pick whose words start on the line after its letter names the option the words name."""
    refuses_pick("pick-newline", item(why="Pick a:\nbookmark plus 100 rows a page"), LABEL_B, "b")


def case_paren_after_letter_is_refused():
    """A pick whose letter is followed by a closing paren, as in Pick a), names the option its words name."""
    refuses_pick("pick-closing-paren", item(why="Pick a) bookmark plus 100 rows a page"), LABEL_B, "b")


def case_agreeing_recommended_pick_passes():
    """Control: the letter names the option whose label the words are, with the (Recommended) tail."""
    passes_pick("pick-agree-recommended", item(why="Pick b: bookmark plus 100 rows a page (Recommended)."),
                open_decision(item()), "an open decision that carries options")


def case_reason_has_no_reword_remedy():
    """The remedy is the letter the label has, and the label decides. A reason that tells the writer to reword the sentence
    offers a second fix that the rule does not ask for."""
    decision_word, reason = wire("pick-reason-remedy", write(item(why=INCIDENT_PICK)))
    check("pick-reason-remedy (scope: the incident is denied)", decision_word == "deny",
          "want deny, got %s" % decision_word)
    if decision_word != "deny":
        return
    check("pick-reason-remedy (reason: no reword remedy)", "reword the sentence" not in reason.lower(),
          "the reason carries the phrase reword the sentence")


def case_reason_keeps_the_letter_remedy():
    """Control: the reason still tells the writer to write the letter the label has, so the no-reword case cannot pass by
    dropping the whole remedy."""
    decision_word, reason = wire("pick-reason-letter", write(item(why=INCIDENT_PICK)))
    check("pick-reason-letter (scope: the incident is denied)", decision_word == "deny",
          "want deny, got %s" % decision_word)
    if decision_word != "deny":
        return
    check("pick-reason-letter (reason: writes the letter the label has)",
          re.search(r"write the letter (?:that )?the label has", reason, re.I) is not None,
          "the reason does not tell the writer to write the letter the label has")


def case_docs_block_names_no_options_limit():
    """The pick-letter block names, as a known limit, that an update with no `options` is not judged. A pass bullet with the
    same words is not a limit, so the case reads only the `Known limit:` bullets of the block."""
    with open(DECISION_DOC, encoding="utf-8") as handle:
        block = pick_block(handle.read())
    limits = [line for line in block.splitlines() if line.startswith("  - Known limit:")]
    check("docs: the pick-letter block names the known limit of an update with no `options`",
          any("no `options`" in line and "update" in line for line in limits),
          "no Known limit bullet of the pick-letter block names an update with no `options`")


def case_option_keys_doc_names_shared_tool_rule():
    """The pick-letter block of the option-keys record names the shared-tool ruling."""
    with open(DECISION_DOC, encoding="utf-8") as handle:
        block = pick_block(handle.read())
    check("docs: the pick-letter block names the shared-tool ruling", SHARED_TOOL in block,
          "the pick-letter block does not contain %r" % SHARED_TOOL)


def case_questions_doc_names_shared_tool_rule():
    """The bullet of the questions record that names rule pick-letter-matches-label names the shared-tool ruling."""
    with open(QUESTIONS_DOC, encoding="utf-8") as handle:
        bullet = bullet_with(handle.read(), "pick-letter-matches-label")
    check("docs: the questions record's pick-letter bullet names the shared-tool ruling", SHARED_TOOL in bullet,
          "the bullet that names pick-letter-matches-label does not contain %r" % SHARED_TOOL)


CASES = (case_incident_is_refused, case_incident_update_is_refused, case_step_text_is_refused,
         case_context_text_is_refused, case_option_gain_text_is_refused, case_upper_case_and_spacing_is_refused,
         case_full_size_is_refused, case_agreeing_pick_passes, case_letter_then_parenthesis_passes,
         case_closed_item_passes, case_task_passes, case_note_passes, case_bare_letter_passes,
         case_words_fitting_two_labels_pass, case_words_of_own_label_pass, case_words_matching_no_label_pass,
         case_option_word_prose_passes, case_no_options_passes, case_empty_options_passes,
         case_full_size_agreeing_pass, case_docs_name_the_rule,
         case_recommended_tail_is_refused, case_comma_tail_is_refused, case_dash_tail_is_refused,
         case_curly_quoted_words_are_refused, case_straight_quoted_words_are_refused, case_bold_letter_is_refused,
         case_newline_before_words_is_refused, case_paren_after_letter_is_refused, case_agreeing_recommended_pick_passes,
         case_reason_has_no_reword_remedy, case_reason_keeps_the_letter_remedy, case_docs_block_names_no_options_limit,
         case_option_keys_doc_names_shared_tool_rule, case_questions_doc_names_shared_tool_rule)


def main():
    for case in CASES:
        try:
            case()
        except Exception as exc:  # a crash is a wrong verdict, shown by name
            check(case.__name__, False, "raised %s: %s" % (type(exc).__name__, exc))
    print("FAIL: %d failed" % len(FAILED) if FAILED else "all checks passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
