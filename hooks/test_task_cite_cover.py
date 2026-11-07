#!/usr/bin/env python3
"""Cases for the cover check of rule task-why-cited (hooks/question_form.py: why_cited_hit, task_check_hit and
task_str_replace_hit, over hooks/route_match.py cite_covers). A waiting-page task's route cite must name a row that
covers the task's act: one whose pattern matches a piece of the act text. The act text is each line of `command`,
split at && and ;, and each backtick span of `context`. A cited row that covers no piece is refused; no act text,
or a row with no pattern, is unknown and never refused.

Run it from the repository root:

    python3 hooks/test_task_cite_cover.py
    /root/.local/share/uv/tools/pytest/bin/python -m pytest hooks/test_task_cite_cover.py -q

The fixtures are the sibling task-why-cited cases' own (hooks/test_question_form.py: rows_at, local_rows, task_item,
TASK_WHY, DOC), so this file holds no copy of them. Each case judges one write on the local surface, and asserts that
surface before it reads a verdict. Temp files live in the run folder test_question_form.py makes.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_question_form as qf  # noqa: E402  the sibling's task-why-cited fixtures (one home)
import question_form  # noqa: E402
import route_match  # noqa: E402  surface(): the scope every case asserts first

WHY_RULE = qf.WHY_RULE
PASS = question_form.PASS
LINE = "Why yours: the cloud refuses branch deletes"
CITE = " (route %s)"
DELETE = {"mac": "cd ~/repo\ngh auth switch -u shivinate7\ngit push origin --delete old-branch"}
ROW_REMEDY = "cite the row of the act"
COMMAND_REMEDY = "name the act's command"

# r-asks covers `gh pr ready`, never a branch delete. r-del-asks covers the delete. r-nopat has no pattern.
NOPATTERN = dict(qf.hook_base.route_row("r-nopat", "unused", "asks", surface="local"))
del NOPATTERN["pattern"]
COVER_ROWS = [qf.hook_base.route_row("r-asks", "^gh pr ready\\b", "asks", surface="local", route="ask-first"),
              qf.hook_base.route_row("r-del-asks", "^git push origin --delete\\b", "asks", surface="local",
                                     route="ask-first"),
              NOPATTERN]


def task(context, **over):
    """A waiting-page task whose Why yours line is `context`; `over` sets its other fields, such as `command`."""
    return qf.task_item(["Open Terminal"], context=context, **over)


class TaskCiteCover(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = qf.rows_at("cite-cover-rows.json", COVER_ROWS)

    def judge_task(self, item):
        """task_check_hit on one task write, on the local surface with the cover rows."""
        with qf.local_rows(self.rows):
            self.assertEqual(route_match.surface(), "local",
                             "the surface is not local, so the cite is judged on the wrong rows")
            return question_form.task_check_hit("set", item)

    def judge_str_replace(self, new_str):
        """task_str_replace_hit on a str_replace of the Why yours line in `context`, on the local surface."""
        entry = {"collection": "items", "doc_id": qf.DOC, "field": "context", "old_str": qf.TASK_WHY,
                 "new_str": new_str}
        with qf.local_rows(self.rows):
            self.assertEqual(route_match.surface(), "local",
                             "the surface is not local, so the cite is judged on the wrong rows")
            return question_form.task_str_replace_hit(entry)

    def test_repro_a_delete_citing_the_row_of_another_act_is_refused(self):
        hit = self.judge_task(task(LINE + CITE % "r-asks" + ".", command=DELETE))
        self.assertEqual(hit[0], WHY_RULE,
                         "a cite of r-asks, a row for another act, covers no piece of the act "
                         "(git push origin --delete old-branch), yet task-why-cited did not refuse: %r" % (hit,))

    def test_a_delete_citing_the_row_of_its_own_act_passes(self):
        hit = self.judge_task(task(LINE + CITE % "r-del-asks" + ".", command=DELETE))
        self.assertEqual(hit, PASS,
                         "r-del-asks covers the act git push origin --delete old-branch, yet the task was refused: %r"
                         % (hit,))

    def test_no_act_text_is_unknown_and_passes(self):
        """No command and no backtick span: the cover is unknown, and unknown is never a refusal."""
        hit = self.judge_task(task(LINE + CITE % "r-asks" + "."))
        self.assertEqual(hit, PASS, "a task with no act text is refused on its cite: %r" % (hit,))

    def test_a_cited_row_with_no_pattern_is_unknown_and_passes(self):
        hit = self.judge_task(task(LINE + CITE % "r-nopat" + ".", command=DELETE))
        self.assertEqual(hit, PASS, "a cite of a row with no pattern is refused, though its cover is unknown: %r"
                         % (hit,))

    def test_refusal_text_names_citing_the_row_of_the_act(self):
        reason = question_form.PAGE_REASONS[WHY_RULE].lower()
        self.assertIn(ROW_REMEDY, reason,
                      "the task-why-cited refusal text does not name the remedy of citing the row of the act")

    def test_refusal_text_names_naming_the_acts_command(self):
        reason = question_form.PAGE_REASONS[WHY_RULE].lower()
        self.assertIn(COMMAND_REMEDY, reason,
                      "the task-why-cited refusal text does not name the remedy of naming the act's command")

    def test_str_replace_citing_a_row_with_no_backtick_act_passes(self):
        """No command is seen on a str_replace, and new_str holds no backtick span: unknown, so it passes."""
        hit = self.judge_str_replace(LINE + CITE % "r-asks" + ".")
        self.assertEqual(hit, PASS, "a str_replace with no act text is refused on its cite: %r" % (hit,))

    def test_str_replace_with_a_backtick_act_the_row_matches_passes(self):
        hit = self.judge_str_replace(LINE + CITE % "r-asks" + ", so I ran `gh pr ready 12`.")
        self.assertEqual(hit, PASS, "r-asks covers the backtick act gh pr ready 12, yet the str_replace was refused: %r"
                         % (hit,))

    def test_str_replace_with_a_backtick_act_the_row_does_not_match_is_refused(self):
        hit = self.judge_str_replace(LINE + CITE % "r-asks" + ", so I ran `git push origin --delete x`.")
        self.assertEqual(hit[0], WHY_RULE,
                         "r-asks covers no backtick span of new_str (git push origin --delete x), yet "
                         "task-why-cited did not refuse: %r" % (hit,))


if __name__ == "__main__":
    unittest.main()
