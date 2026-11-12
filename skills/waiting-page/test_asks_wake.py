#!/usr/bin/env python3
"""Prose contract for the writer's end check, `stale_pages.py --page <file> --asks <asks>` (skill waiting-page).

    python3 skills/waiting-page/test_asks_wake.py

Reads prose only and runs none of the skill's code. Each claim has one case:
  1. reference/republish.md, "Keep the page on main's code", step 2 names the end check as its own run: a code span
     with stale_pages.py, --page and --asks, and no --write, in a sentence that says end or last.
  2. The same step has a sentence that says exit 1 means an ask is open.
  3. SKILL.md's wake text (a block that names a wake or a turn start) names the same run, in a sentence that says
     end or last.
The controls pass on the text as it stands. They show that each read finds its section, and that the span reader
takes a lone apostrophe and comment-like characters as plain text.
"""
import re
import unittest

from test_export_page import skill_step  # the one home of "step n of a section" (the export suite)
from test_skill_park_relay import SKILL, blocks, read, sentences  # the one home of the prose reader (the park relay suite)

STEP_HEADING = "## Keep the page on main's code"
CODE = re.compile(r"`([^`]*)`")
END = re.compile(r"\b(?:end|last)\b", re.I)
EXIT_ONE = re.compile(r"\bexit\s+(?:code\s+)?1\b", re.I)
ASK = re.compile(r"\bask", re.I)
OPEN = re.compile(r"\bopen\b", re.I)
WAKE = re.compile(r"\bwake\b|\bturn start\b|\bstart of each turn\b", re.I)


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


def step_two():
    """Step 2 of "Keep the page on main's code", on one line, read from the skill file that holds it."""
    return " ".join(skill_step(STEP_HEADING, 2).split())


def wake_blocks():
    """The SKILL.md blocks that name a wake or a turn start."""
    return [b for b in blocks(read(SKILL)) if WAKE.search(b)]


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

    def test_2_step_2_says_exit_1_means_an_ask_is_open(self):
        step = step_two()
        says = [s for s in sentences(step) if EXIT_ONE.search(s) and ASK.search(prose(s)) and OPEN.search(prose(s))]
        self.assertTrue(says, "republish.md step 2 has no sentence that says exit 1 means an ask is open. Step 2:\n" + step)


class WakeTextNamesTheCheck(unittest.TestCase):
    def test_3_wake_text_names_the_asks_run_as_the_end_check(self):
        wake = wake_blocks()
        self.assertTrue(wake, "SKILL.md has no wake block (a block that names a wake or a turn start), so there is no wake text")
        named = [s for b in wake for s in sentences(b) if any(own_run(c) for c in spans(s))]
        self.assertTrue(named, "SKILL.md's wake text names no `stale_pages.py --page <file> --asks <asks>` run")
        ended = [s for s in named if END.search(prose(s))]
        self.assertTrue(ended, "SKILL.md's wake text names the `--asks` run but does not say it is the wake's end check")


class Controls(unittest.TestCase):
    def test_c1_step_2_still_names_the_plain_run(self):
        step = step_two()
        plain = [c for c in spans(step) if "stale_pages.py" in c and "--page" in c and "--write" in c]
        self.assertTrue(plain, "republish.md step 2 no longer names the plain run (`stale_pages.py --page <file> --write`). "
                        "Step 2:\n" + step)

    def test_c2_skill_has_a_wake_block(self):
        self.assertTrue(wake_blocks(), "SKILL.md has no wake block, so test 3 reads nothing")

    def test_c3_a_lone_apostrophe_in_prose_does_not_hide_a_span(self):
        text = "Don't rerun it. Run `stale_pages.py --page <file> --asks <asks>` last."
        self.assertEqual(spans(text), ["stale_pages.py --page <file> --asks <asks>"],
                         "the span reader lost a code span after a lone apostrophe")

    def test_c4_a_span_with_comment_openers_is_read_whole(self):
        text = "Run `stale_pages.py --page <file> --asks <asks> # end // last` now."
        self.assertEqual(spans(text), ["stale_pages.py --page <file> --asks <asks> # end // last"],
                         "the span reader cut a code span at a comment opener")


if __name__ == "__main__":
    unittest.main()
