#!/usr/bin/env python3
"""Prose contract for the writer's end check, `stale_pages.py --page <file> --asks <asks>` (skill waiting-page).

    python3 skills/waiting-page/test_asks_wake.py

Reads prose only and runs none of the skill's code. Each claim has one case:
  1. reference/republish.md, "Keep the page on main's code", step 2 names the end check as its own run: a code span
     with stale_pages.py, --page and --asks, and no --write, in a sentence that says end or last.
  2. The same step has a sentence that says exit 1 means an ask is open on a current page.
  2b. The same step has a sentence that says exit 2 means the asks list could not be read.
  3. SKILL.md's "## Read the answers" section (the wake text) names the same run, in a sentence that says end or last.
  4. The end check runs after the step that saves the asks, or step 2 saves them first.
  5. The FAIL line appears only when an ask is listed.
  6. The session that holds an ask answers it, and the writer routes or names it; the writer does not answer each ask.
  7. The comment-wake save list in "## Read the answers" names asks.
  8. The "in full" list in "## Read the answers" names asks, so a cut asks list is not read as clear.
The controls pass on the text as it stands. They show that each read finds its section, that the copy step saves
the asks, and that the span reader takes a lone apostrophe, comment-like characters and a line break as plain text.
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


def spans(text):
    """The inner text of each code span in the text, in order."""
    return [m.group(1) for m in CODE.finditer(text)]


def prose(text):
    """The text with its code spans taken out, so a word inside a command does not count as prose."""
    return CODE.sub(" ", text)


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


def step_two():
    """Step 2 of "Keep the page on main's code", on one line, read from the skill file that holds it."""
    return " ".join(skill_step(STEP_HEADING, 2).split())


def copy_step_two():
    """Step 2 of "Keep a copy in the repo", the fetch of the five collections, on one line."""
    return " ".join(skill_step(COPY_HEADING, 2).split())


def read_answers():
    """The SKILL.md "## Read the answers" section: the wake text, read from disk and never copied here."""
    return section(read(SKILL), READ_HEADING)


def numbered_steps():
    """(n, text) for each numbered step of "Keep the page on main's code", each text on one line."""
    body = skill_file_with(STEP_HEADING).split(STEP_HEADING, 1)[1].split("\n## ", 1)[0]
    found = []
    for part in re.split(r"\n(?=\d+\. )", body):
        m = re.match(r"(\d+)\. ", part)
        if m:
            found.append((int(m.group(1)), " ".join(part.split())))
    return found


def save_and_run_positions():
    """Where the section saves the asks, and where its own end-check run sits: (step, offset) pairs, in text order.
    A save is a copy step ("Keep a copy in the repo") or a sentence with a save verb and an asks span. The run's own
    sentence is never a save, so a line that says what the run reads does not count."""
    saves, runs = [], []
    for n, text in numbered_steps():
        for m in CODE.finditer(text):
            if own_run(m.group(1)):
                runs.append((n, m.start()))
        if COPY_NAME in text:
            saves.append((n, text.index(COPY_NAME)))
        for s in sentences(text):
            codes = spans(s)
            if not any(own_run(c) for c in codes) and SAVE.search(prose(s)) and any(names_asks(c) for c in codes):
                saves.append((n, text.index(s)))
    return saves, runs


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

    def test_4_the_end_check_runs_after_the_step_that_saves_the_asks(self):
        saves, runs = save_and_run_positions()
        self.assertTrue(runs, "republish.md's \"Keep the page on main's code\" section has no own `stale_pages.py --page <file> "
                        "--asks <asks>` run")
        self.assertTrue(saves, "no step of \"Keep the page on main's code\" saves the asks, so the end check reads no saved list")
        first_save, first_run = min(saves), min(runs)
        self.assertLess(first_save, first_run,
                        "republish.md's end check (step %d) runs before the step that saves the asks (step %d, "
                        "\"Keep a copy in the repo\"), so the check reads an asks list not yet saved"
                        % (first_run[0], first_save[0]))

    def test_5_the_fail_line_appears_only_when_an_ask_is_listed(self):
        step = step_two()
        fail = [s for s in sentences(step) if FAIL.search(s)]
        self.assertTrue(fail, "republish.md step 2 names no FAIL line. Step 2:\n" + step)
        only = [s for s in fail if ONLY.search(prose(s)) and ASK.search(prose(s)) and LISTED.search(prose(s))]
        self.assertTrue(only, "republish.md step 2 has no sentence that says the FAIL line appears only when an ask is listed; "
                        "as written it reads as printed on every run. Step 2:\n" + step)

    def test_6_the_session_that_holds_an_ask_answers_it_and_the_writer_routes_it(self):
        step = step_two()
        holder = [s for s in sentences(step)
                  if ANSWER.search(prose(s)) and ASK.search(prose(s)) and SESSION.search(prose(s)) and ROUTE.search(prose(s))]
        writer = [s for s in sentences(step) if WRITER_ANSWERS.search(prose(s))]
        self.assertTrue(holder and not writer,
                        "republish.md step 2 must say the session that holds an ask answers it, with the writer routing or "
                        "naming it, and must not have the writer answer each ask. Step 2:\n" + step)


class WakeTextNamesTheCheck(unittest.TestCase):
    def test_3_read_the_answers_section_names_the_asks_run_as_the_end_check(self):
        wake = read_answers()
        self.assertTrue(wake, "SKILL.md has no '## Read the answers' section, so there is no wake text")
        named = [s for b in blocks(wake) for s in sentences(b) if any(own_run(c) for c in spans(s))]
        self.assertTrue(named, "SKILL.md's '## Read the answers' section names no `stale_pages.py --page <file> --asks <asks>` run")
        ended = [s for s in named if END.search(prose(s))]
        self.assertTrue(ended, "SKILL.md's '## Read the answers' section names the `--asks` run but does not say it is the "
                        "wake's end check")


class WakeSaveListNamesAsks(unittest.TestCase):
    def test_7_the_comment_wake_save_list_names_the_asks(self):
        wake = read_answers()
        save = [s for b in blocks(wake) for s in sentences(b) if any(c.startswith("ArtifactData list receipts") for c in spans(s))]
        self.assertTrue(save, "SKILL.md's '## Read the answers' section has no comment-wake save of `ArtifactData list receipts`")
        named = [s for s in save if any(names_asks(c) for c in spans(s))]
        self.assertTrue(named, "the comment-wake save list names no asks, so a wake saves no asks list for the end check. "
                        "Save sentence:\n" + "\n".join(save))

    def test_8_the_in_full_list_names_the_asks_so_a_cut_list_is_not_read_as_clear(self):
        wake = read_answers()
        full = [s for b in blocks(wake) for s in sentences(b) if IN_FULL.search(s)]
        self.assertTrue(full, "SKILL.md's '## Read the answers' section says no list is read in full")
        named = [s for s in full if any(names_asks(c) for c in spans(s))]
        self.assertTrue(named, "the 'in full' list names no asks, so a cut asks list can read as clear. Sentence:\n"
                        + "\n".join(full))


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


if __name__ == "__main__":
    unittest.main()
