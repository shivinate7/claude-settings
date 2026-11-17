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
  1e. Label edges: the page label must
     equal the chat label after folding, and only the chat label may be the shorter one, at a word boundary. A chat
     line the check cannot read (A, em dash, text; **A** text; a cite with no colon) is checked or noted. A page
     letter the chat question never writes is refused. A curly apostrophe or an em dash folds equal to its plain
     form. A payload with no transcript_path logs one noted line.
  1f. Unread chat forms: a cite with no colon whose id has no digit and no hyphen, and the chat option forms
     "Option A: x", "A x", "a)x" and "**a**) x", are not read. A write the chat refutes must be checked or noted, never
     a silent allow. Each red case fails on the carry head with an allow and zero noted lines; each control is green.
  1g. A bold letter with a dash ("**A** — Blue") reads the dash as the separator, so the chat text is "Blue". The page
     label "Blue" is allowed with no noted line; another label is still refused.
  2. The `recommended` field. The page stars `recommended`, falling back to `pick`. The widening guard
     (widens_pick_hit, rule uniform-pick) also refuses a `recommended` that names a widening option. The page draws
     `recommended` (its itemFields block lists it).
  3. The page's own copy of the star and the answer label is tested in skills/waiting-page/tests/page.test.mjs.
     page_grant.py reads the answer `label` only when the answer has no `optionId`; skills/waiting-page/test_page_grant_label.py tests it.

Red on the round-2 base: the cases of part 1e and the re-pointed fn: case fail on an assert about the verdict.
Part 1f's cases fail while the check allows, with no note, a write the chat refutes. The fn: cases need
chat_page_label_hit. Run with the argument
`behaviour` to skip them, for a base without that function. Without it, every case runs.

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
    {"key": "a", "id": "keep-as-is", "label": "Keep it as is", "gain": "No new form on the shared allow list.",
     "lose": "Each batch waits until the coordinator wakes."},
    {"key": "b", "id": "allow-merge-role", "label": "Allow merge --role",
     "gain": "The runner merges each batch alone.", "lose": "A second merge form on the shared allow list."},
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


def label_item(doc, options=None, ids=True, **over):
    """A waiting-page decision that passes the form and the other rules, with `options` as its options. Its `shown` is
    the options as given; `ids` False leaves an option with no id as it is (the option-letters-frozen cases need that)."""
    item = tcj.good_page_item(id=doc)
    item["options"] = copy.deepcopy(OPTIONS if options is None else options)
    item = tcj.with_frozen_fields(item, ids=ids)
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


def case_fn_chat_short_form_passes_page_short_refused():
    """Owner, 12:35 CST Nov 8: "A and B mean the same". Coordinator ruling, 07:57 CST Nov 12: the page label must equal
    the chat label after folding case, spaces and punctuation, and only the chat label may be the shorter one. So a
    chat short form that the label starts with passes, and a page label shorter than the chat's line is refused,
    naming b. The lines are cited to the item, so the check reads them."""
    fn_pass("fn: a chat short form that the label starts with passes",
            fn_label(ITEM, OPTIONS, chat_question((CHAT_A, CHAT_B_SHORT))))
    fn_refuse("fn: a page label shorter than the chat's line is refused, naming b",
              fn_label(ITEM, label_options("Allow"), chat_question((CHAT_A, "b) Allow merge --role, then wait"))), "b")


def case_fn_differing_label_refuses_naming_the_letter():
    fn_refuse("fn: a chat line for b that differs from its label is refused, naming b",
              fn_label(ITEM, OPTIONS, chat_question((CHAT_A, CHAT_B_MISMATCH))), "b")


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
    options = copy.deepcopy(OPTIONS) + [{"key": "c", "id": "wait-a-day", "label": "Wait a day", "gain": "g", "lose": "l"}]
    fn_refuse("fn: letter c is the third option's position, so a differing c is refused",
              fn_label(ITEM, options, chat_question((CHAT_A, CHAT_B, "c) Hold for a day"))), "c")


# ------------------------------------------------------------------ 1. the page-item write path (wire:)

def write_transcript(name, text):
    """A transcript of one human message, then one assistant message per text (a str, or a list of str), under this
    run's folder."""
    texts = [text] if isinstance(text, str) else list(text)
    folder = os.path.join(tcj.ROOT, "label-transcripts")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name + ".jsonl")
    lines = [{"type": "user", "message": {"role": "user", "content": "Ask the owner."}}]
    lines += [{"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": t}]}}
              for t in texts]
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(line) + "\n" for line in lines))
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
               "tool_input": dict(call, url=tcj.PAGE_URL)}
    if transcript is not None:  # None: the payload carries no transcript_path key at all
        payload["transcript_path"] = transcript
    got = subprocess.run([sys.executable, GUARD], input=json.dumps(payload), capture_output=True, text=True,
                         env=env, timeout=120)
    if got.returncode != 0:
        return "error", "exit %d: %s" % (got.returncode, got.stderr.strip()[:200])
    return decision_of(got.stdout)


def noted_rule_rows(name):
    """The guard.log rows of this run's guard folder `name` that note RULE. Empty when there is no log."""
    path = os.path.join(tcj.ROOT, "label-cfg", name, "guard.log")
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            rows = [line.split("\t") for line in f if line.strip()]
    return [row for row in rows if len(row) > 3 and row[2] == "noted" and row[3] == RULE]


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
            "data": tcj.with_frozen_fields({"kind": "decision", "options": copy.deepcopy(OPTIONS)})}
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


# ------------------------------------------------------------------ 1b. the cited question the chat asked

GROUP_X, GROUP_Y = "x1-keep", "y2-wait"  # two items asked in one reply
WAIT_A = "a) Wait a day"


def options_with_a(label_a):
    """OPTIONS with letter a's label set to `label_a`, for a case that changes the first label."""
    options = copy.deepcopy(OPTIONS)
    options[0]["label"] = label_a
    return options


def grouped_chat():
    """One reply that asks two items. x1 writes a) Keep it as is, and y2, cited mid-reply, writes a) Wait a day. Each
    question's lines run to the next Page item line."""
    return chat_question((CHAT_A, CHAT_B, "Page item: %s" % GROUP_Y, WAIT_A, CHAT_B), cite=GROUP_X)


def case_wire_later_note_does_not_hide_the_question():
    """A later assistant text that cites the item with no option lines is no question. The earlier question's b still
    holds, so a write whose b differs from it is refused."""
    transcript = write_transcript("shadow", [chat_question((CHAT_A, CHAT_B_MISMATCH)),
                                             "Page item: %s is being written now." % ITEM])
    wire_refuses("wire: a later note citing the item with no option lines does not hide the earlier question's b",
                 set_write(ITEM), transcript)


def case_fn_cite_mid_line_counts():
    """A cite at the end of a sentence counts as a cite: the chat asked the item, so its differing b is refused."""
    text = "Question for the page. Page item: %s\n%s\n%s" % (ITEM, CHAT_A, CHAT_B_MISMATCH)
    fn_refuse("fn: a cite at the end of a sentence counts, and a differing b is refused",
              fn_label(ITEM, OPTIONS, text), "b")


def case_wire_grouped_first_question_is_allowed():
    """Control: x1's own a) line is read for x1, so its write with a) Keep it as is is allowed."""
    transcript = write_transcript("grouped-x1", grouped_chat())
    wire_allows("control: x1 with a) Keep it as is, in a reply that also asks y2, is allowed",
                set_write(GROUP_X, options_with_a("Keep it as is")), transcript)


def case_wire_grouped_question_reads_its_own_lines():
    """y2's write with a) Wait a day is allowed: its lines run from its own Page item line, not from x1's."""
    transcript = write_transcript("grouped-y2", grouped_chat())
    wire_allows("wire: y2 with a) Wait a day, in a reply that also asks x1, is allowed",
                set_write(GROUP_Y, options_with_a("Wait a day")), transcript)


def case_wire_grouped_question_refuses_the_other_label():
    """y2's write with a) Keep it as is is refused: that is x1's a) line, not y2's."""
    transcript = write_transcript("grouped-y2-keep", grouped_chat())
    wire_refuses("wire: y2 with a) Keep it as is, in a reply that also asks x1, is refused",
                 set_write(GROUP_Y, options_with_a("Keep it as is")), transcript)


def case_wire_unreadable_transcript_is_allowed_and_noted():
    """Control: a transcript that cannot be read allows the write, and the guard logs one noted line for the rule."""
    missing = os.path.join(tcj.ROOT, "label-transcripts", "no-such-transcript.jsonl")
    decision, reason = guard_hook("unreadable", set_write(ITEM), missing)
    check("control: a missing transcript allows the write", decision == "allow",
          "want an allow, got %s: %r" % (decision, reason[:200]))
    noted = noted_rule_rows("unreadable")
    check("control: a missing transcript logs one noted line for %s" % RULE, len(noted) == 1,
          "want one noted line, got %r" % (noted,))


def case_recommended_a_with_widening_pick_b_stays_refused():
    """Control, green on the current code. The old name pick is read the same way as recommended (SKILL.md, uniform-pick),
    so a write whose pick is the widening b is refused even with recommended a: the page stars recommended, and the
    write is still refused."""
    widens_refuses("control: recommended a with a widening pick b is refused: the old name pick is read the same way",
                   decision_with(pick="b", recommended="a"))


# ------------------------------------------------------------------ 1c. a reply that asks two questions, cite and options

def case_wire_grouped_with_question_lines_reads_below():
    """Control, green on the old code: a reply that asks two items, each cite above its question line and then its
    options, reads each item's own options below its cite. y2 with a) Wait a day is allowed, and so is x1 with a)
    Keep it as is: the text between them looks like a footer reply's middle, but the reply opens with a cite."""
    chat = "\n".join(("Page item: %s" % GROUP_X, "Which path?", CHAT_A, CHAT_B,
                      "Page item: %s" % GROUP_Y, "Which day?", WAIT_A, CHAT_B))
    transcript = write_transcript("grouped-qline", chat)
    wire_allows("control: y2 with a) Wait a day, its cite above its question line, is allowed",
                set_write(GROUP_Y, options_with_a("Wait a day")), transcript)
    wire_allows("control: x1 with a) Keep it as is, its cite above its question line, is allowed",
                set_write(GROUP_X, options_with_a("Keep it as is")), transcript)


# ------------------------------------------------------------------ 1d. a cite written below its options (footer)

FOOT_ONE, FOOT_TWO = "f1-keep", "f2-wait"  # two items asked in one reply, each cite under its options


def footer_chat():
    """One reply that asks two items, each cite under its own options: f1 writes a) Keep it as is, f2 writes a) Wait a
    day. f2's question line and options sit under f1's cite."""
    return "\n".join(("Which path?", CHAT_A, CHAT_B, "Page item: %s" % FOOT_ONE,
                      "Which day?", WAIT_A, CHAT_B, "Page item: %s" % FOOT_TWO))


def case_fn_footer_cite_reads_the_options_above():
    """A cite under its options reads those options: a differing b is refused. On the old code the lines under the cite
    are read, there are none, and the write passes."""
    text = "\n".join(("Which path?", CHAT_A, CHAT_B_MISMATCH, "Page item: %s" % ITEM))
    fn_refuse("fn: a cite under its options reads them, and a differing b is refused",
              fn_label(ITEM, OPTIONS, text), "b")


def case_fn_footer_cite_reads_past_gain_and_lose_lines():
    """A footer cite reads every option line of its question, with Gain and Lose lines between them (rule
    style-question-form): a differing a, three lines above the cite's nearest option line, is refused."""
    text = "\n".join(("Which path?", "a) Hold the batch", "   Gain: g", "   Lose: l",
                      CHAT_B, "   Gain: g", "   Lose: l", "Page item: %s" % ITEM))
    fn_refuse("fn: a footer cite reads its a) line past Gain and Lose lines, and a differing a is refused",
              fn_label(ITEM, OPTIONS, text), "a")


def case_wire_footer_first_item_reads_its_own_lines():
    """f1 with a) Keep it as is is allowed: its options sit above its cite. On the old code f1 reads f2's a) Wait a
    day, under its cite, and the write is refused."""
    transcript = write_transcript("footer-f1", footer_chat())
    wire_allows("wire: f1 with a) Keep it as is, its cite under its options, is allowed",
                set_write(FOOT_ONE, options_with_a("Keep it as is")), transcript)


def case_wire_footer_first_item_refuses_the_next_label():
    """f1 with a) Wait a day is refused against f1's own a) line, above its cite. On the old code the lines under f1's
    cite are read as f1's, f2's a) Wait a day matches, and the write is allowed."""
    transcript = write_transcript("footer-f1-wait", footer_chat())
    wire_refuses("wire: f1 with a) Wait a day, f2's line under f1's cite, is refused",
                 set_write(FOOT_ONE, options_with_a("Wait a day")), transcript)


def case_wire_footer_second_item_reads_its_own_lines():
    """f2 with a) Keep it as is is refused: its own a) is Wait a day, above its cite. On the old code nothing sits
    under f2's cite, and the write is allowed."""
    transcript = write_transcript("footer-f2-keep", footer_chat())
    wire_refuses("wire: f2 with a) Keep it as is, f1's line, is refused",
                 set_write(FOOT_TWO, options_with_a("Keep it as is")), transcript)


def case_wire_footer_second_item_is_allowed():
    """Control, green on the old code: f2 with a) Wait a day, its own line, is allowed."""
    transcript = write_transcript("footer-f2", footer_chat())
    wire_allows("control: f2 with a) Wait a day, its cite under its options, is allowed",
                set_write(FOOT_TWO, options_with_a("Wait a day")), transcript)


# ------------------------------------------------------------------ 1e. The label rule's edges

def options_with_c():
    """OPTIONS plus a third option, c, that no chat question in these cases writes."""
    return copy.deepcopy(OPTIONS) + [{"key": "c", "id": "wait-a-day", "label": "Wait a day", "gain": "g", "lose": "l"}]


def wire_checked_or_noted(name, call, transcript):
    """A chat form the check cannot read is either checked (a deny naming the rule) or skipped with one noted line for
    the rule. The builder picks which. A silent allow with no note is the fault."""
    decision, reason = guard_hook(name, call, transcript)
    noted = noted_rule_rows(name)
    checked = decision == "deny" and RULE in reason
    check(name, checked or (decision == "allow" and len(noted) == 1),
          "want a deny naming %s, or an allow with one noted line, got %s with %d noted line(s): %r"
          % (RULE, decision, len(noted), reason[:200]))


def case_fn_chat_short_form_mid_word_refused():
    """A chat short form must stop at a word boundary. "No" stops mid-word in "Node.js rewrite", and "Keep" stops
    mid-word in "Keeping it as is", so each pair is a mismatch, and the letter is named."""
    fn_refuse("fn: a chat form that stops mid-word (No, for Node.js rewrite) is refused, naming a",
              fn_label(ITEM, options_with_a("Node.js rewrite"), chat_question(("a) No", CHAT_B))), "a")
    fn_refuse("fn: a chat form that stops mid-word (Keep, for Keeping it as is) is refused, naming a",
              fn_label(ITEM, options_with_a("Keeping it as is"), chat_question(("a) Keep", CHAT_B))), "a")


def case_wire_unparsed_dash_form_is_checked_or_noted():
    """The chat line "A <em dash> Red" is an option line the check does not read. Its "Red" differs from the page's a,
    so a form that is read refuses the write. A form that is skipped logs one noted line."""
    transcript = write_transcript("unparsed-dash", chat_question(("A — Red", CHAT_B)))
    wire_checked_or_noted("wire: a chat line 'A <em dash> Red' is checked or noted, not silently skipped",
                          set_write(ITEM), transcript)


def case_wire_unparsed_bold_form_is_checked_or_noted():
    """The chat line "**A** Red" is an option line the check does not read. The same test as the dash form."""
    transcript = write_transcript("unparsed-bold", chat_question(("**A** Red", CHAT_B)))
    wire_checked_or_noted("wire: a chat line '**A** Red' is checked or noted, not silently skipped",
                          set_write(ITEM), transcript)


def case_wire_unparsed_cite_is_checked_or_noted():
    """The cite "Page item <id>" has no colon, so the check does not read it as a cite, and the chat's a) Red is not
    compared. Read, the cite refuses the write. Skipped, it must log one noted line."""
    transcript = write_transcript("unparsed-cite", chat_question(("Page item " + ITEM, "a) Red", CHAT_B), cite=None))
    wire_checked_or_noted("wire: a cite 'Page item <id>' with no colon is checked or noted, not silently skipped",
                          set_write(ITEM), transcript)


def case_fn_extra_page_letter_is_refused():
    """The page adds option c, which the chat question never writes. The chat shows no c, so the write is a mismatch
    and c is named."""
    fn_refuse("fn: a page option c that the chat question never writes is refused, naming c",
              fn_label(ITEM, options_with_c(), chat_question((CHAT_A, CHAT_B))), "c")


def case_wire_extra_page_letter_is_refused():
    """The same extra option, judged at the write: a set that adds c, which the chat question never wrote, is refused."""
    transcript = write_transcript("extra-letter", chat_question((CHAT_A, CHAT_B)))
    wire_refuses("wire: a set that adds option c, which the chat question never wrote, is refused",
                 set_write(ITEM, options_with_c()), transcript)


def case_fn_curly_apostrophe_folds_equal():
    """A curly apostrophe is the same mark as a straight one. A label and a chat line that differ only in it are equal,
    so the write passes. Refusing them is a false alarm."""
    fn_pass("fn: a chat line with a curly apostrophe, equal to the label's straight one, passes",
            fn_label(ITEM, options_with_a("Don't merge the batch"),
                     chat_question(("a) Don’t merge the batch", CHAT_B))))


def case_fn_em_dash_folds_equal():
    """An em dash folds to a hyphen, in either direction: a chat line and a label that differ only in that mark are
    equal, so the write passes."""
    fn_pass("fn: a chat em dash equal to the label's hyphen passes",
            fn_label(ITEM, options_with_a("Hold - the batch"), chat_question(("a) Hold — the batch", CHAT_B))))
    fn_pass("fn: a label em dash equal to the chat's hyphen passes",
            fn_label(ITEM, options_with_a("Hold — the batch"), chat_question(("a) Hold - the batch", CHAT_B))))


def no_transcript_noted(name, transcript, state):
    """A write whose payload carries `transcript` (None: no transcript_path key) is allowed, and logs one noted line for
    the rule, as an unreadable transcript does. `state` names the payload's state in the check names."""
    decision, reason = guard_hook(name, set_write(ITEM), transcript)
    check("control: a payload with %s is allowed" % state, decision == "allow",
          "want an allow, got %s: %r" % (decision, reason[:200]))
    noted = noted_rule_rows(name)
    check("wire: a payload with %s logs one noted line for %s" % (state, RULE), len(noted) == 1,
          "want one noted line, got %r" % (noted,))


def case_wire_no_transcript_key_is_noted():
    """A payload with no transcript_path key passes the label check and logs nothing. It must log one noted line."""
    no_transcript_noted("no-key", None, "no transcript_path key")


def case_wire_empty_transcript_path_is_noted():
    """A payload with an empty transcript_path passes the label check and logs nothing. It must log one noted line."""
    no_transcript_noted("empty-path", "", "an empty transcript_path")


# ------------------------------------------------------------------ 1f. Cites and forms the label check does not read

# Two gaps in the round-2 check. A chat text it does not read is allowed with no note, so a write the chat refutes passes:
#  - a cite with no colon counts only when its id holds a digit or a hyphen (PAGE_ITEM_CITE), so "Page item merge",
#    with the one-word id "merge", is not a cite;
#  - a chat option line counts only in the forms CHAT_OPTION_LINE reads, so "Option A: Blue", "A Blue", "a)Blue" and
#    "**a**) Blue" are not option lines.
# A red case is a write the chat refutes. It must be checked (a deny naming the rule) or noted (one line). A silent
# allow is the fault. A control is green on the carry head and stays green: it shows the fixture reaches the check, or
# that the page's own text in an unread form is allowed.
ONE_WORD_ITEM = "merge"  # an id with no digit and no hyphen
FORM_OPTION_WORD = "Option A: {}"
FORM_BARE_LETTER = "A {}"
FORM_NO_SPACE = "a){}"
FORM_BOLD_PAREN = "**a**) {}"


def case_wire_one_word_colonless_cite_is_checked_or_noted():
    """Finding 1. The cite "Page item merge" has no colon and a one-word id, so PAGE_ITEM_CITE does not read it. The
    chat's a) Blue is then not compared with the page's "Keep it as is", and the write is allowed with no note. Red on
    the carry head: an allow with zero noted lines."""
    transcript = write_transcript("one-word-colonless",
                                  chat_question(("Page item " + ONE_WORD_ITEM, "a) Blue", CHAT_B), cite=None))
    wire_checked_or_noted("wire: a cite 'Page item merge' (one-word id, no colon) is checked or noted, not silently skipped",
                          set_write(ONE_WORD_ITEM), transcript)


def case_wire_one_word_colon_cite_is_refused():
    """Control, green on the carry head. The same one-word id cited with its colon, "Page item: merge", is read, and the
    chat's a) Blue is refused. So the fixture reaches the check, and the red case above fails on the colon-less cite."""
    transcript = write_transcript("one-word-colon", chat_question(("a) Blue", CHAT_B), cite=ONE_WORD_ITEM))
    wire_refuses("control: a cite 'Page item: merge' (one-word id, colon) with a) Blue is refused",
                 set_write(ONE_WORD_ITEM), transcript)


def unread_form_checked_or_noted(slug, line):
    """The chat question writes option a in an unread form, then the page's b, which the chat matches. The page's a is
    "Keep it as is", so a read of the form refuses the write."""
    transcript = write_transcript("form-" + slug, chat_question((line, CHAT_B)))
    wire_checked_or_noted("wire: a chat line '%s' is checked or noted, not silently skipped" % line,
                          set_write(ITEM), transcript)


def case_wire_option_word_form_is_checked_or_noted():
    """Finding 2. "Option A: Blue" is the tag LABEL_TAG reads on a page label, so Claude can write it in the chat. The
    chat check does not read it, so letter a is skipped and the write is allowed with no note. Red on the carry head."""
    unread_form_checked_or_noted("option-word", FORM_OPTION_WORD.format("Blue"))


def case_wire_bare_letter_form_is_checked_or_noted():
    """Finding 2. "A Blue" is a letter and a space with no mark after it. The chat check does not read it, so the write
    is allowed with no note. Red on the carry head."""
    unread_form_checked_or_noted("bare-letter", FORM_BARE_LETTER.format("Blue"))


def case_wire_no_space_form_is_checked_or_noted():
    """Finding 2. "a)Blue" has no space after its mark. The chat check does not read it, so the write is allowed with no
    note. Red on the carry head."""
    unread_form_checked_or_noted("no-space", FORM_NO_SPACE.format("Blue"))


def case_wire_bold_paren_form_is_checked_or_noted():
    """Finding 2. "**a**) Blue" closes its bold before the paren. The chat check does not read it, so the write is allowed
    with no note. Red on the carry head."""
    unread_form_checked_or_noted("bold-paren", FORM_BOLD_PAREN.format("Blue"))


def case_wire_unread_forms_with_the_page_text_are_allowed():
    """Control, green on the carry head. Each form the check does not read, written with the page's own text for a, is
    allowed. A check that refused a right answer in one of these forms would be a false alarm."""
    for slug, template in (("option-word", FORM_OPTION_WORD), ("bare-letter", FORM_BARE_LETTER),
                           ("no-space", FORM_NO_SPACE), ("bold-paren", FORM_BOLD_PAREN)):
        line = template.format("Keep it as is")
        transcript = write_transcript("control-" + slug, chat_question((line, CHAT_B)))
        wire_allows("control: a chat line '%s' with the page's text is allowed" % line, set_write(ITEM), transcript)


def wire_zero_noted(name, call, transcript):
    """A clean write is allowed and logs no noted line for the rule. The five red cases above accept one noted line, so
    a fix that notes every write would pass them. This control refuses it."""
    decision, reason = guard_hook(name, call, transcript)
    noted = noted_rule_rows(name)
    check(name, decision == "allow" and not noted,
          "want an allow with no noted line for %s, got %s with %d noted line(s): %r"
          % (RULE, decision, len(noted), reason[:200]))


def case_wire_clean_writes_log_no_noted_line():
    """Keep-green control, green on every old commit. Three clean paths: a set whose labels match the chat, a set whose
    chat question cites another item, and a set whose chat question cites no item. Each is allowed and logs no noted
    line for the rule."""
    wire_zero_noted("wire: a clean set whose labels match the chat logs no noted line for the rule",
                    set_write(ITEM), write_transcript("clean-matching", chat_question((CHAT_A, CHAT_B))))
    wire_zero_noted("wire: a clean set whose chat cites another item logs no noted line for the rule",
                    set_write(ITEM),
                    write_transcript("clean-other-item", chat_question((CHAT_A, CHAT_B_MISMATCH), cite=OTHER_ITEM)))
    wire_zero_noted("wire: a clean set whose chat cites no item logs no noted line for the rule",
                    set_write(ITEM), write_transcript("clean-no-cite", chat_question((CHAT_A, CHAT_B_MISMATCH), cite=None)))


# ------------------------------------------------------------------ 1g. a bold letter with a dash

# A dash after a bold letter ("**A** — Blue", "**A** - Blue", "**Option A** — Blue") separates the letter from its text.
# The chat text for letter a is "Blue", so the page label "Blue" is a right answer and must be allowed with no noted line.
BOLD_DASH_LINES = (
    ("bold-em-dash", "**A** — Blue"),
    ("bold-hyphen", "**A** - Blue"),
    ("bold-option-em-dash", "**Option A** — Blue"),
)


def case_wire_bold_dash_chat_forms_allow_the_page_label():
    """Each bold letter with a dash, beside the page label "Blue" for letter a, is allowed and logs no noted line for the
    rule. Read with the dash as the separator, the chat's text for a is "Blue" and equals the label."""
    for slug, line in BOLD_DASH_LINES:
        transcript = write_transcript(slug, chat_question((line, CHAT_B)))
        wire_zero_noted("wire: the chat line %s with the page label Blue is allowed, with no noted line" % slug,
                        set_write(ITEM, options_with_a("Blue")), transcript)


def case_wire_bold_dash_chat_form_refuses_another_label():
    """The same bold letter with an em dash, beside the page label Green, is still refused as option-labels-match-chat.
    The allowance covers the label that equals the chat's text, not every label."""
    transcript = write_transcript("bold-em-dash-green", chat_question(("**A** — Blue", CHAT_B)))
    wire_refuses("wire: a bold letter with an em dash refuses the page label Green",
                 set_write(ITEM, options_with_a("Green")), transcript)


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


def case_fn_page_label_hit_never_raises_on_an_unreadable_transcript():
    """page_label_hit gives an unknown verdict, never an exception, for a missing transcript file, a path that names
    no file, a non-string path and no path. A write that carries no options reads nothing and passes."""
    writes = [("set", {"doc_id": "never-raise-case", "data": label_item("never-raise-case")})]
    for path in ("${", "/nonexistent/chat.jsonl", None, "", 7):
        try:
            got = question_form.page_label_hit(writes, path)
        except Exception as exc:  # a crash is a wrong verdict, shown by name
            got = ("RAISED", "%s: %s" % (type(exc).__name__, exc))
        check("fn: page_label_hit with transcript %r is unknown, not a raise" % (path,),
              got[0] == question_form.LABELS_UNKNOWN and got[1], "got %r" % (got,))
    bare = [("set", {"doc_id": "never-raise-case", "data": {"kind": "decision", "status": "open"}})]
    check("fn: page_label_hit reads no transcript for a write with no options",
          question_form.page_label_hit(bare, "${") == ("", ""), "a write with no options was judged")


# ------------------------------------------------------------------ the run

CASES = (case_fn_page_label_hit_never_raises_on_an_unreadable_transcript, case_fn_equal_labels_pass, case_fn_case_and_spaces_fold, case_fn_chat_short_form_passes_page_short_refused,
         case_fn_differing_label_refuses_naming_the_letter, case_fn_no_cited_id_passes,
         case_fn_other_item_passes, case_fn_letter_missing_from_chat_passes, case_fn_letter_is_position,
         case_wire_differing_set_is_refused, case_wire_differing_update_is_refused,
         case_wire_matching_set_is_allowed, case_wire_short_form_is_allowed, case_wire_no_cited_id_is_allowed,
         case_wire_other_item_is_allowed, case_wire_missing_letter_is_allowed,
         case_recommended_naming_widening_is_refused, case_pick_naming_widening_still_refused,
         case_recommended_plain_passes, case_recommended_is_a_drawn_field, case_pick_is_a_drawn_field,
         case_wire_later_note_does_not_hide_the_question, case_fn_cite_mid_line_counts,
         case_wire_grouped_first_question_is_allowed, case_wire_grouped_question_reads_its_own_lines,
         case_wire_grouped_question_refuses_the_other_label, case_wire_unreadable_transcript_is_allowed_and_noted,
         case_recommended_a_with_widening_pick_b_stays_refused,
         case_wire_grouped_with_question_lines_reads_below, case_fn_footer_cite_reads_the_options_above,
         case_fn_footer_cite_reads_past_gain_and_lose_lines, case_wire_footer_first_item_reads_its_own_lines,
         case_wire_footer_first_item_refuses_the_next_label, case_wire_footer_second_item_reads_its_own_lines,
         case_wire_footer_second_item_is_allowed,
         case_fn_chat_short_form_mid_word_refused, case_wire_unparsed_dash_form_is_checked_or_noted,
         case_wire_unparsed_bold_form_is_checked_or_noted, case_wire_unparsed_cite_is_checked_or_noted,
         case_fn_extra_page_letter_is_refused, case_wire_extra_page_letter_is_refused,
         case_fn_curly_apostrophe_folds_equal, case_fn_em_dash_folds_equal,
         case_wire_no_transcript_key_is_noted, case_wire_empty_transcript_path_is_noted,
         case_wire_one_word_colonless_cite_is_checked_or_noted, case_wire_one_word_colon_cite_is_refused,
         case_wire_option_word_form_is_checked_or_noted, case_wire_bare_letter_form_is_checked_or_noted,
         case_wire_no_space_form_is_checked_or_noted, case_wire_bold_paren_form_is_checked_or_noted,
         case_wire_unread_forms_with_the_page_text_are_allowed, case_wire_clean_writes_log_no_noted_line,
         case_wire_bold_dash_chat_forms_allow_the_page_label, case_wire_bold_dash_chat_form_refuses_another_label)
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
