#!/usr/bin/env python3
"""Prose contract for the writer's end check, `stale_pages.py --page <file> --asks <asks>` (skill waiting-page).

    python3 skills/waiting-page/test_asks_wake.py

Reads prose only and runs none of the skill's code. Each claim has one case:
  1. reference/republish.md, "Keep the page on main's code", step 2 names the end check as its own run: a code span
     with stale_pages.py, --page and --asks, and no --write, in a sentence that says end or last.
  2. The same step has a sentence that says exit 1 means an ask is open on a current page.
  2b. The same step has a sentence that says exit 2 means the asks list could not be read.
  3. SKILL.md's "## Read the answers" section (the wake text) names the same run, in a sentence that says end or last.
  4. The asks save in step 2 comes after a routing act and an answer to the asks the writer holds ("answers the ones it
     holds"), both in sentences that name an ask, and right before the end check: no routing act sits between the save
     and the run. The save is a code span that lists the asks (`ArtifactData list asks`). A "Keep a copy in the repo"
     pointer is never the save.
  5. A FAIL sentence in step 2 says FAIL prints when an ask is listed, and a FAIL sentence says it prints when the
     asks list cannot be read (stale_pages.py prints FAIL on both).
  6. The session that holds an ask answers it, and the writer routes or names it; the writer does not answer each ask.
  7. The comment-wake save list in "## Read the answers" names asks.
  8. The "in full" list in "## Read the answers" names asks, so a cut asks list is not read as clear.
  9. The sentence that saves the asks names, before the save, an after word, a routing act and an answer to the asks it
     holds, for example "After the writer routes each ask and answers the ones it holds, save the asks ...". The wording
     "and the holder replies" does not pass: it does not say the writer answers the asks it holds.
 10. SKILL.md's end-check sentence and republish.md agree on where the check runs: the step the sentence names, and
     whether it says the check ends the wake (republish.md runs it in its step 2 of 5, so the two cannot both say last).
 11. A sentence in "Keep the page on main's code" says `<asks>` is the list saved in the same step.
 12. A sentence in that section that saves the asks says the save touches the `.complete` marker.
 13. The one Cost: paragraph of that section names the second run, the end check's python process.
 14. The one Cost: paragraph names the asks list read.
 15a. The end-check paragraph of SKILL.md's "## Read the answers" orders its asks save after routing and a reply, and
      right before the run (the same order check as case 4).
 15b. The asks save sentence in that paragraph names the `.complete` marker.
 15c. A sentence in that paragraph says the `<asks>` the run reads is the folder saved.
 16. The Cost: sentence that names the `ArtifactData list asks` read names it as the end check's one read.
 17. SKILL.md's end-check sentence says when the check runs: at turn start, or at each wake and before each republish.
     When it names turn start, republish.md's section names turn start too.
 18. republish.md step 2's asks save sentence names the error rule: no `.complete` after a failed list or a pending
     cursor (reference/copies-and-accounts.md, "Keep a copy in the repo" step 2).
 19. SKILL.md's end-check paragraph has the same error rule in its asks save sentence.
 c1-c14. Controls. They pass on the text as it stands, and they show that each read finds its section, that the copy
     step saves the asks, that the Cost: paragraph is found once, that the span reader takes a lone apostrophe,
     comment-like characters and a line break as plain text, and that the order check passes a compliant step and
     names the cause in a save-first step. c12 to c14 show that "and the holder replies" fails the answer check, and
     that the error-rule check passes a save sentence that names the rule and fails one that does not.
"""
import re
import unittest

from test_export_page import skill_file_with, skill_step  # the one home of "step n of a section" (the export suite)
from test_skill_park_relay import SKILL, blocks, read, section, sentences  # the one home of the prose reader (the park relay suite)

STEP_HEADING = "## Keep the page on main's code"
COPY_HEADING = "## Keep a copy in the repo"
READ_HEADING = "## Read the answers"
COPY_NAME = "Keep a copy in the repo"
CODE = re.compile(r"`([^`]*)`")
QUOTED = re.compile(r'"[^"\n]*"')  # a quoted title such as ("Route an ask"): a pointer to a section, never a routing act
END = re.compile(r"\b(?:end|last)\b", re.I)
EXIT_ONE = re.compile(r"\bexit\s+(?:code\s+)?1\b", re.I)
EXIT_TWO = re.compile(r"\bexit\s+(?:code\s+)?2\b", re.I)
ASK = re.compile(r"\bask", re.I)
OPEN = re.compile(r"\bopen\b", re.I)
CURRENT = re.compile(r"\bcurrent page\b", re.I)
UNREADABLE = re.compile(r"\bcould not be read\b", re.I)
WAKE = re.compile(r"\bwake\b|\bturn start\b|\bstart of each turn\b", re.I)
FAIL = re.compile(r"\bFAIL\b")
ONLY = re.compile(r"\bonly\b", re.I)
LISTED = re.compile(r"\blisted\b|\blists?\b", re.I)
ANSWER = re.compile(r"\banswer", re.I)
SESSION = re.compile(r"\bsession\b|\bowner\b|\bholds?\b", re.I)
ROUTE = re.compile(r"\broutes?\b|\bnames?\b", re.I)
WRITER_ANSWERS = re.compile(r"\banswer each\b|\bthe writer answers?\b", re.I)
SAVE = re.compile(r"\b(?:save|saves|saved|fetch|fetches)\b", re.I)
IN_FULL = re.compile(r"\bin full\b", re.I)
# Case 5: the FAIL line also prints when the asks list cannot be read (stale_pages.py open_asks_mode, unknown path).
UNREADABLE_CLAUSE = re.compile(r"\bcannot be read\b|\bcould not be read\b|\bunreadable\b|\bcut[- ]short\b|\bunknown\b", re.I)
# Cases 4, 9, 15a, 15b: the save is ordered after a routing act and an answer to the asks the writer holds, both in ask
# sentences, and right before the run. "answers the ones it holds": a peer-held ask stays open, so "the holder replies" fails.
END_REF = re.compile(r"\bend check\b", re.I)
ROUTE_ACT = re.compile(r"\brout(?:e|es|ed|ing)\b", re.I)
ANSWER_HELD = re.compile(r"\banswers?\b[^,;]*?\bholds?\b", re.I)
AFTER_ACT = re.compile(r"\bafter\b|\bonce\b|\bfollowing\b", re.I)
# Cases 15c, 17: the save word, the timing words, and the republish word.
SAVE_VERB = re.compile(r"\bsav(?:e|es|ed|ing)\b", re.I)
TURN = re.compile(r"\bturn\b", re.I)
WAKE_WORD = re.compile(r"\bwake\b", re.I)
REPUBLISH = re.compile(r"\brepublish", re.I)
# Case 10: a claim that the check comes last, either at the wake's end or as the section's last step.
STEP_NUMBER = re.compile(r"\bstep (\d+)\b", re.I)
LAST_CLAIM = re.compile(r"\bends? (?:each|every|the) wake\b|\bend of (?:each|every|the) wake\b|\blast (?:in|of) (?:each|every|the) wake\b"
                        r"|\blast step\b|\bfinal step\b", re.I)
# Case 11: the list the check reads is the one saved in the same step.
SAME_STEP = re.compile(r"\b(?:same|this) step\b", re.I)
SAVED = re.compile(r"\bsav\w*", re.I)
ASKS_WORD = re.compile(r"\basks?\b", re.I)
COMPLETE = ".complete"  # Cases 12, 15b: the marker's text, in prose or in a code span
# Cases 18, 19, c12 to c14: the save sentence names the error rule, a failed list or a pending cursor leaves `.complete` out.
ERROR_WORD = re.compile(r"\bfail\w*|\berror\w*", re.I)
CURSOR_WORD = re.compile(r"\bcursors?\b", re.I)
NO_WORD = re.compile(r"\b(?:no|not|never|without|only|stops?)\b", re.I)
# Case 13: the Cost: paragraph names the end check's own python process, a second run beside the plain one.
SECOND_RUN = re.compile(r"\bend check\b|\bsecond (?:python|run|process)\b|\btwo (?:python )?(?:processes|runs)\b|\bper run\b"
                        r"|\banother (?:python )?(?:process|run)\b|\bone more (?:python )?(?:process|run)\b", re.I)
SCOPE = "SKILL.md's '## Read the answers' section has no one paragraph with the end check's run (`stale_pages.py --page <file> --asks <asks>`)"


def spans(text):
    """The inner text of each code span in the text, in order."""
    return [m.group(1) for m in CODE.finditer(text)]


def prose(text):
    """The text with its code spans taken out, so a word inside a command does not count as prose."""
    return CODE.sub(" ", text)


def masked(text):
    """The text with its code spans and quoted titles blanked to spaces of the same length, so an offset reads the same in both."""
    text = CODE.sub(lambda m: " " * len(m.group(0)), text)
    return QUOTED.sub(lambda m: " " * len(m.group(0)), text)


def one_line(text):
    return " ".join(text.split())


def sentence_bounds(flat):
    """(start, end) of each sentence of a one-line text, cut where sentences() cuts it."""
    bounds, start = [], 0
    for m in re.finditer(r"(?<=[.!?])\s+", flat):
        bounds.append((start, m.start()))
        start = m.end()
    bounds.append((start, len(flat)))
    return bounds


def asks_run(code):
    """A code span that runs stale_pages.py with --asks."""
    return "stale_pages.py" in code and "--asks" in code


def own_run(code):
    """An asks run that stands alone: it names the fetched page with --page, and it carries no --write, so it is not the plain run."""
    return asks_run(code) and "--page" in code and "--write" not in code


def names_asks(code):
    """A code span that names the asks list: `asks`, or the `ArtifactData list asks` call."""
    code = code.strip()
    return code == "asks" or code.startswith("ArtifactData list asks")


def asks_calls(flat):
    """Offsets of the code spans that list the asks. A pointer such as "Keep a copy in the repo" is no span, so it is no call."""
    return [m.start() for m in CODE.finditer(flat) if names_asks(m.group(1))]


def run_calls(flat):
    """Offsets of the code spans that run the end check."""
    return [m.start() for m in CODE.finditer(flat) if own_run(m.group(1))]


def order_fault(flat):
    """The one cause the asks save is not right before the end check, or "" when it is. The save is the last asks call
    before the run. Before it there must be a routing act and an answer to the asks the writer holds ("answers the ones
    it holds"), each in a sentence that names an ask. No routing act may sit between the save and the run."""
    runs = run_calls(flat)
    if not runs:
        return "no end check run (`stale_pages.py --page <file> --asks <asks>`) in the text"
    run = runs[0]
    saves = [p for p in asks_calls(flat) if p < run]
    if not saves:
        return "no asks save before the end check"
    save = saves[-1]
    body = masked(flat)
    route, answer = [], []
    for a, b in sentence_bounds(flat):
        sentence = body[a:b]
        if not ASK.search(sentence):
            continue
        route += [a + m.start() for m in ROUTE_ACT.finditer(sentence)]
        answer += [a + m.start() for m in ANSWER_HELD.finditer(sentence)]
    if not any(p < save for p in route):
        return "the asks save comes before any routing"
    if not any(p < save for p in answer):
        return "the asks save comes before the writer answers the asks it holds"
    if any(save < p < run for p in route):
        return "routing sits between the asks save and the end check"
    return ""


def ordered_save_sentences(flat):
    """Each sentence with an asks save that, before the save, has an after word, a routing act and an answer to the held asks."""
    body = masked(flat)
    found = []
    for a, b in sentence_bounds(flat):
        calls = asks_calls(flat[a:b])
        if not calls:
            continue
        before = body[a:a + calls[0]]
        if AFTER_ACT.search(before) and ROUTE_ACT.search(before) and ANSWER_HELD.search(before):
            found.append(flat[a:b])
    return found


def names_error_rule(sentence):
    """True when the sentence names the `.complete` marker and says a failed list or a pending cursor leaves it out: an
    error word, a cursor word and a no word, all in its prose (the code spans taken out)."""
    words = prose(sentence)
    return COMPLETE in sentence and bool(ERROR_WORD.search(words) and CURSOR_WORD.search(words) and NO_WORD.search(words))


def step_two():
    """Step 2 of "Keep the page on main's code", on one line, read from the skill file that holds it."""
    return one_line(skill_step(STEP_HEADING, 2))


def copy_step_two():
    """Step 2 of "Keep a copy in the repo", the fetch of the five collections, on one line."""
    return one_line(skill_step(COPY_HEADING, 2))


def read_answers():
    """The SKILL.md "## Read the answers" section: the wake text, read from disk and never copied here."""
    return section(read(SKILL), READ_HEADING)


def end_check_paragraph():
    """The one "## Read the answers" paragraph that holds the end check's run, on one line, or "" when there is not exactly one."""
    found = [one_line(b) for b in blocks(read_answers()) if any(own_run(c) for c in spans(b))]
    return found[0] if len(found) == 1 else ""


def step_section():
    """The whole "Keep the page on main's code" section of republish.md, from its heading to the next section."""
    return skill_file_with(STEP_HEADING).split(STEP_HEADING, 1)[1].split("\n## ", 1)[0]


def republish_flat():
    """The whole "Keep the page on main's code" section on one line."""
    return one_line(step_section())


def section_sentences():
    """Every sentence of the section, each block's sentences in order, one line each."""
    return [s for b in blocks(step_section()) for s in sentences(b)]


def cost_text():
    """The one Cost: paragraph of the section, on one line, or "" when the section has no single one."""
    found = [b for b in blocks(step_section()) if b.lstrip().startswith("Cost:")]
    return " ".join(found[0].split()) if len(found) == 1 else ""


def numbered_steps():
    """(n, text) for each numbered step of "Keep the page on main's code", each text on one line."""
    found = []
    for part in re.split(r"\n(?=\d+\. )", step_section()):
        m = re.match(r"(\d+)\. ", part)
        if m:
            found.append((int(m.group(1)), " ".join(part.split())))
    return found


def run_positions():
    """(step, offset) for each own end-check run in "Keep the page on main's code", in text order."""
    found = []
    for n, text in numbered_steps():
        for m in CODE.finditer(text):
            if own_run(m.group(1)):
                found.append((n, m.start()))
    return found


class EndCheckInRepublishStep(unittest.TestCase):
    def test_1_step_2_names_the_asks_run_as_its_own_end_check(self):
        step = step_two()
        named = [s for s in sentences(step) if any(asks_run(c) for c in spans(s))]
        self.assertTrue(named, "republish.md step 2 names no `stale_pages.py --asks` run, so the writer has no end check. "
                        "Step 2:\n" + step)
        own = [s for s in named if any(own_run(c) for c in spans(s))]
        self.assertTrue(own, "republish.md step 2's `--asks` run is not its own run: it needs --page and must not carry "
                        "--write. Step 2:\n" + step)
        ended = [s for s in own if END.search(prose(s))]
        self.assertTrue(ended, "republish.md step 2 does not say its `--asks` run is the end check. Step 2:\n" + step)

    def test_2_step_2_says_exit_1_means_an_ask_is_open_on_a_current_page(self):
        step = step_two()
        says = [s for s in sentences(step)
                if EXIT_ONE.search(s) and ASK.search(prose(s)) and OPEN.search(prose(s)) and CURRENT.search(prose(s))]
        self.assertTrue(says, "republish.md step 2 has no sentence that says exit 1 means an ask is open on a current page. "
                        "Step 2:\n" + step)

    def test_2b_step_2_says_exit_2_means_the_asks_list_could_not_be_read(self):
        step = step_two()
        says = [s for s in sentences(step) if EXIT_TWO.search(s) and UNREADABLE.search(s) and ASK.search(prose(s))]
        self.assertTrue(says, "republish.md step 2 has no sentence that says exit 2 means the asks list could not be read. "
                        "Step 2:\n" + step)

    def test_4_the_asks_save_follows_routing_and_an_answer_to_the_asks_held_and_comes_right_before_the_end_check(self):
        step = step_two()
        fault = order_fault(step)
        self.assertEqual(fault, "", "republish.md step 2 orders the asks save wrongly (%s), so the end check reads an asks "
                         "list that the routing and the answers have not yet changed. Step 2:\n%s" % (fault, step))

    def test_5_the_fail_line_names_both_the_listed_ask_and_the_unreadable_list(self):
        step = step_two()
        fail = [s for s in sentences(step) if FAIL.search(s)]
        self.assertTrue(fail, "republish.md step 2 names no FAIL line. Step 2:\n" + step)
        listed = [s for s in fail if ASK.search(prose(s)) and LISTED.search(prose(s))]
        self.assertTrue(listed, "republish.md step 2's FAIL sentence does not say FAIL prints when an ask is listed. "
                        "Step 2:\n" + step)
        unreadable = [s for s in fail if UNREADABLE_CLAUSE.search(prose(s))]
        self.assertTrue(unreadable, "republish.md step 2 does not say FAIL also prints when the asks list cannot be read: "
                        "stale_pages.py prints FAIL on an unreadable or cut-short list (exit 2). Step 2:\n" + step)

    def test_6_the_session_that_holds_an_ask_answers_it_and_the_writer_routes_it(self):
        step = step_two()
        holder = [s for s in sentences(step)
                  if ANSWER.search(prose(s)) and ASK.search(prose(s)) and SESSION.search(prose(s)) and ROUTE.search(prose(s))]
        writer = [s for s in sentences(step) if WRITER_ANSWERS.search(prose(s))]
        self.assertTrue(holder and not writer,
                        "republish.md step 2 must say the session that holds an ask answers it, with the writer routing or "
                        "naming it, and must not have the writer answer each ask. Step 2:\n" + step)

    def test_9_the_sentence_that_saves_the_asks_names_routing_and_a_reply_before_the_save(self):
        step = step_two()
        self.assertTrue(asks_calls(step), "republish.md step 2 has no `ArtifactData list asks` save, so there is no save to order. "
                        "Step 2:\n" + step)
        ordered = ordered_save_sentences(step)
        self.assertTrue(ordered, "republish.md step 2's sentence that saves the asks does not name, before the save, an after "
                        "word, a routing act and an answer to the asks it holds (for example: After the writer routes each ask "
                        "and answers the ones it holds, save the asks ...). Step 2:\n" + step)

    def test_10_skill_md_and_republish_agree_on_where_the_end_check_runs(self):
        self.assertTrue(numbered_steps(), "republish.md's \"Keep the page on main's code\" section has no numbered steps")
        ends = [s for b in blocks(read_answers()) for s in sentences(b)
                if any(own_run(c) for c in spans(s)) and END.search(prose(s))]
        self.assertTrue(ends, "SKILL.md's '## Read the answers' section has no sentence that names the end check run")
        skill = ends[0]
        runs = run_positions()
        self.assertTrue(runs, "republish.md's \"Keep the page on main's code\" section has no own `stale_pages.py --page <file> "
                        "--asks <asks>` run")
        run_step = min(runs)[0]
        last_step = max(n for n, _ in numbered_steps())
        named = STEP_NUMBER.search(prose(skill))
        claims_last = LAST_CLAIM.search(prose(skill))
        self.assertTrue(named or claims_last, "SKILL.md's end-check sentence names no position (no step, no end of the "
                        "wake). Sentence:\n" + skill)
        if named:
            self.assertEqual(int(named.group(1)), run_step, "SKILL.md's end-check sentence names step %s, but republish.md "
                             "runs the check in step %d. Sentence:\n%s" % (named.group(1), run_step, skill))
        self.assertEqual(bool(claims_last), run_step == last_step,
                         "SKILL.md and republish.md disagree on where the end check runs: SKILL.md says it ends the wake (%s), "
                         "republish.md runs it in step %d of %d. Sentence:\n%s"
                         % (bool(claims_last), run_step, last_step, skill))


class WakeTextNamesTheCheck(unittest.TestCase):
    def test_3_read_the_answers_section_names_the_asks_run_as_the_end_check(self):
        wake = read_answers()
        self.assertTrue(wake, "SKILL.md has no '## Read the answers' section, so there is no wake text")
        named = [s for b in blocks(wake) for s in sentences(b) if any(own_run(c) for c in spans(s))]
        self.assertTrue(named, "SKILL.md's '## Read the answers' section names no `stale_pages.py --page <file> --asks <asks>` run")
        ended = [s for s in named if END.search(prose(s))]
        self.assertTrue(ended, "SKILL.md's '## Read the answers' section names the `--asks` run but does not say it is the "
                        "wake's end check")

    def test_15a_the_skill_end_check_paragraph_saves_the_asks_after_routing_and_a_reply(self):
        para = end_check_paragraph()
        self.assertTrue(para, SCOPE)
        fault = order_fault(para)
        self.assertEqual(fault, "", "SKILL.md's end-check paragraph orders the asks save wrongly (%s), so the wake's end check "
                         "can read an asks list from before the routing. Paragraph:\n%s" % (fault, para))

    def test_15b_the_skill_asks_save_sentence_names_the_complete_marker(self):
        para = end_check_paragraph()
        self.assertTrue(para, SCOPE)
        marked = [s for s in sentences(para) if asks_calls(s) and COMPLETE in s]
        self.assertTrue(marked, "SKILL.md's end-check paragraph has no asks save sentence that names the `.complete` marker, "
                        "so a partial asks list can read as the whole. Paragraph:\n" + para)

    def test_15c_the_skill_run_reads_the_folder_the_paragraph_saved(self):
        para = end_check_paragraph()
        self.assertTrue(para, SCOPE)
        named = [s for s in sentences(para) if any("<asks>" in c for c in spans(s)) and SAVE_VERB.search(prose(s))]
        self.assertTrue(named, "SKILL.md's end-check paragraph does not say the `<asks>` the run reads is the folder saved "
                        "(no sentence has `<asks>` and a save word). Paragraph:\n" + para)

    def test_17_the_skill_end_check_sentence_says_when_the_check_runs(self):
        para = end_check_paragraph()
        self.assertTrue(para, SCOPE)
        runs = [s for s in sentences(para) if any(own_run(c) for c in spans(s))]
        self.assertTrue(runs, "SKILL.md's end-check paragraph has no sentence with the end check's run")
        sentence = runs[0]
        words = prose(sentence)
        turn = TURN.search(words)
        self.assertTrue(turn or (WAKE_WORD.search(words) and REPUBLISH.search(words)),
                        "SKILL.md's end-check sentence names no timing: say the turn-start case, or each wake and before each "
                        "republish (as republish.md does). Sentence:\n" + sentence)
        if turn:
            self.assertTrue(TURN.search(republish_flat()), "SKILL.md's end-check sentence says the check runs at turn start, but "
                            "republish.md's \"Keep the page on main's code\" section does not say so. Sentence:\n" + sentence)


class WakeSaveListNamesAsks(unittest.TestCase):
    def test_7_the_comment_wake_save_list_names_the_asks(self):
        wake = read_answers()
        save = [s for b in blocks(wake) for s in sentences(b) if any(c.startswith("ArtifactData list receipts") for c in spans(s))]
        self.assertTrue(save, "SKILL.md's '## Read the answers' section has no comment-wake save of `ArtifactData list receipts`")
        named = [s for s in save if any(names_asks(c) for c in spans(s))]
        self.assertTrue(named, "the comment-wake save list names no asks, so the wake's saved copy holds no asks list (the writer "
                        "routes asks from its own read at each wake). Save sentence:\n" + "\n".join(save))

    def test_8_the_in_full_list_names_the_asks_so_a_cut_list_is_not_read_as_clear(self):
        wake = read_answers()
        full = [s for b in blocks(wake) for s in sentences(b) if IN_FULL.search(s)]
        self.assertTrue(full, "SKILL.md's '## Read the answers' section says no list is read in full")
        named = [s for s in full if any(names_asks(c) for c in spans(s))]
        self.assertTrue(named, "the 'in full' list names no asks, so a cut asks list can read as clear. Sentence:\n"
                        + "\n".join(full))


class SaveNamesTheErrorRule(unittest.TestCase):
    def test_18_republish_step_2_asks_save_sentence_names_the_error_rule(self):
        step = step_two()
        saves = [s for s in sentences(step) if asks_calls(s)]
        self.assertTrue(saves, "republish.md step 2 has no sentence with the `ArtifactData list asks` save, so there is no "
                        "save to name the error rule on. Step 2:\n" + step)
        self.assertTrue(any(names_error_rule(s) for s in saves), "republish.md step 2's asks save sentence does not name the "
                        "error rule: no `.complete` after a failed list or a pending cursor (copies-and-accounts.md). Save "
                        "sentences:\n" + "\n".join(saves))

    def test_19_skill_end_check_asks_save_sentence_names_the_error_rule(self):
        para = end_check_paragraph()
        self.assertTrue(para, SCOPE)
        saves = [s for s in sentences(para) if asks_calls(s)]
        self.assertTrue(saves, "SKILL.md's end-check paragraph has no sentence with the `ArtifactData list asks` save. "
                        "Paragraph:\n" + para)
        self.assertTrue(any(names_error_rule(s) for s in saves), "SKILL.md's end-check paragraph's asks save sentence does not "
                        "name the error rule: no `.complete` after a failed list or a pending cursor (copies-and-accounts.md). "
                        "Save sentences:\n" + "\n".join(saves))


class AsksListAndCost(unittest.TestCase):
    def test_11_a_sentence_says_the_asks_span_is_the_list_saved_in_the_same_step(self):
        self.assertTrue(numbered_steps(), "republish.md's \"Keep the page on main's code\" section has no numbered steps")
        span_sentences = [s for s in section_sentences() if "<asks>" in spans(s)]
        self.assertTrue(span_sentences, "republish.md's \"Keep the page on main's code\" section has no sentence with an "
                        "`<asks>` span, so the end check's list is not named")
        says = [s for s in span_sentences if SAVED.search(prose(s)) and SAME_STEP.search(prose(s))]
        self.assertTrue(says, "republish.md's \"Keep the page on main's code\" section does not say `<asks>` is the list "
                        "saved in the same step. Sentences:\n" + "\n".join(span_sentences))

    def test_12_the_asks_save_says_it_touches_the_complete_marker(self):
        self.assertTrue(numbered_steps(), "republish.md's \"Keep the page on main's code\" section has no numbered steps")
        asks_saves = [s for s in section_sentences()
                      if SAVE.search(prose(s)) and (ASKS_WORD.search(prose(s)) or any(names_asks(c) for c in spans(s)))]
        self.assertTrue(asks_saves, "republish.md's \"Keep the page on main's code\" section has no sentence that saves the asks")
        marked = [s for s in asks_saves if COMPLETE in s]
        self.assertTrue(marked, "republish.md's asks save does not touch the `.complete` marker, so a partial asks list can "
                        "read as the whole. Save sentences:\n" + "\n".join(asks_saves))

    def test_13_the_cost_paragraph_names_the_second_run(self):
        cost = cost_text()
        self.assertTrue(cost, "republish.md's \"Keep the page on main's code\" section has no single Cost: paragraph")
        second = [s for s in sentences(cost) if SECOND_RUN.search(prose(s)) or any(own_run(c) for c in spans(s))]
        self.assertTrue(second, "the Cost: paragraph does not name the second run, the end check's python process. Cost:\n" + cost)

    def test_14_the_cost_paragraph_names_the_asks_list_read(self):
        cost = cost_text()
        self.assertTrue(cost, "republish.md's \"Keep the page on main's code\" section has no single Cost: paragraph")
        read_asks = [s for s in sentences(cost)
                     if ASKS_WORD.search(prose(s)) or any(c.startswith("ArtifactData list asks") for c in spans(s))]
        self.assertTrue(read_asks, "the Cost: paragraph does not name the asks list read (`ArtifactData list asks`). Cost:\n"
                        + cost)

    def test_16_the_cost_names_the_asks_read_as_the_end_checks_one_read(self):
        cost = cost_text()
        self.assertTrue(cost, "republish.md's \"Keep the page on main's code\" section has no single Cost: paragraph")
        reads = [s for s in sentences(cost) if any(c.startswith("ArtifactData list asks") for c in spans(s))]
        self.assertTrue(reads, "the Cost: paragraph names no `ArtifactData list asks` read")
        named = [s for s in reads if END_REF.search(prose(s)) or any(own_run(c) for c in spans(s))]
        self.assertTrue(named, "the Cost: sentence for the `ArtifactData list asks` read does not name it as the end check's one "
                        "read, so a second asks read can hide in the cost. Sentence:\n" + "\n".join(reads))


class Controls(unittest.TestCase):
    def test_c1_step_2_still_names_the_plain_run(self):
        step = step_two()
        plain = [c for c in spans(step) if "stale_pages.py" in c and "--page" in c and "--write" in c]
        self.assertTrue(plain, "republish.md step 2 no longer names the plain run (`stale_pages.py --page <file> --write`). "
                        "Step 2:\n" + step)

    def test_c2_read_the_answers_section_has_a_wake(self):
        wake = read_answers()
        self.assertTrue(wake and WAKE.search(wake), "SKILL.md's '## Read the answers' section names no wake, so test 3 reads nothing")

    def test_c3_a_lone_apostrophe_in_prose_does_not_hide_a_span(self):
        text = "Don't rerun it. Run `stale_pages.py --page <file> --asks <asks>` last."
        self.assertEqual(spans(text), ["stale_pages.py --page <file> --asks <asks>"],
                         "the span reader lost a code span after a lone apostrophe")

    def test_c4_a_span_with_comment_openers_is_read_whole(self):
        text = "Run `stale_pages.py --page <file> --asks <asks> # end // last` now."
        self.assertEqual(spans(text), ["stale_pages.py --page <file> --asks <asks> # end // last"],
                         "the span reader cut a code span at a comment opener")

    def test_c5_a_code_span_broken_across_a_line_is_read_whole(self):
        text = "Run `stale_pages.py --page <file>\n  --asks <asks>` last."
        self.assertEqual(spans(text), ["stale_pages.py --page <file>\n  --asks <asks>"],
                         "the span reader cut a code span at a line break")

    def test_c6_the_copy_step_saves_the_asks(self):
        self.assertTrue(any(names_asks(c) for c in spans(copy_step_two())),
                        "\"Keep a copy in the repo\" step 2 no longer fetches `asks`, so test 4 has no save to order against. "
                        "Step 2:\n" + copy_step_two())

    def test_c7_the_cost_paragraph_is_found_once(self):
        self.assertTrue(cost_text(), "republish.md's \"Keep the page on main's code\" section has no single Cost: paragraph, "
                        "so tests 13, 14 and 16 read nothing")

    def test_c8_a_keep_a_copy_pointer_is_not_an_asks_save(self):
        text = 'Keep the copy from the same file ("Keep a copy in the repo" step 2 saves the same list of asks).'
        self.assertEqual(asks_calls(text), [], "a 'Keep a copy in the repo' pointer that names the asks counts as an asks save")
        self.assertEqual(ordered_save_sentences(text), [], "a 'Keep a copy in the repo' pointer passes the save-sentence check")

    def test_c9_a_compliant_step_passes_both_order_checks(self):
        text = one_line('After the writer routes each ask with no `owner` ("Route an ask") and answers the ones it holds, '
                        'save the asks '
                        'into one new folder with `ArtifactData list asks`, then touch `.complete`. Run the end check as its own '
                        'run: `python3 ~/.claude/skills/waiting-page/stale_pages.py --page <file> --asks <asks>` (`<asks>` is the '
                        'folder saved in this step).')
        self.assertEqual(order_fault(text), "", "the order check fails a compliant step")
        self.assertTrue(ordered_save_sentences(text), "the save-sentence check fails a compliant step")

    def test_c10_a_save_first_step_is_named_as_saved_before_routing(self):
        text = one_line('Save the asks first with `ArtifactData list asks`, then touch `.complete` in that folder. After the writer '
                        'takes or routes each ask with no `owner`, run the end check: '
                        '`python3 ~/.claude/skills/waiting-page/stale_pages.py --page <file> --asks <asks>`.')
        self.assertEqual(order_fault(text), "the asks save comes before any routing",
                         "the order check names another cause for a save-first step")

    def test_c11_a_lone_apostrophe_and_comment_openers_in_a_span_read_as_plain_text(self):
        text = ("Don't rerun it. After the writer routes each ask and answers the ones it holds, save the asks with "
                "`ArtifactData list asks # not a comment // or /* one */`,\n  then touch `.complete`. Then run the end check: "
                "`python3 ~/.claude/skills/waiting-page/stale_pages.py --page <file>\n  --asks <asks>` last.")
        flat = one_line(text)
        self.assertEqual(len(asks_calls(flat)), 1, "the span reader cut the asks span at a comment opener or a lone apostrophe")
        self.assertEqual(order_fault(flat), "", "the order check fails a step with a lone apostrophe, comment openers and a "
                         "line-broken run span")

    def test_c12_the_holder_replies_wording_fails_the_answer_check(self):
        text = one_line('After the writer routes each ask and the holder replies, save the asks with `ArtifactData list asks`, '
                        'then touch `.complete`. Run the end check as its own run: `python3 ~/.claude/skills/waiting-page/'
                        'stale_pages.py --page <file> --asks <asks>`.')
        self.assertEqual(order_fault(text), "the asks save comes before the writer answers the asks it holds",
                         "the order check passes 'the holder replies', so the old wording is not red")
        self.assertEqual(ordered_save_sentences(text), [], "the save-sentence check passes 'the holder replies'")

    def test_c13_a_save_sentence_that_names_the_error_rule_passes(self):
        save = one_line('After the writer routes each ask and answers the ones it holds, save the asks into one new folder with '
                        '`ArtifactData list asks` (follow `next_cursor` until it is empty), '
                        'touching `.complete` only when no list call fails and no cursor is still pending.')
        self.assertTrue(names_error_rule(save), "the error-rule check fails a save sentence that names the error rule")

    def test_c14_a_save_sentence_without_the_error_rule_fails(self):
        save = one_line('After the writer routes each ask and answers the ones it holds, save the asks into one new folder with '
                        '`ArtifactData list asks`, touching `.complete`.')
        self.assertFalse(names_error_rule(save), "the error-rule check passes a save sentence with no failed list and no pending "
                         "cursor")


if __name__ == "__main__":
    unittest.main()
