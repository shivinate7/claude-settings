#!/usr/bin/env python3
"""Cases for the cover check of rule task-why-cited (hooks/question_form.py: why_cited_hit, task_check_hit and
task_str_replace_hit, over hooks/route_match.py cite_covers). A waiting-page task's route cite must name a row that
covers the task's act: one whose pattern matches a piece of the act text. With a command, the act text is its lines,
split at &&, || and ;. With no command, it is each backtick span of `context`, and a span that no row matches is not
an act this check can name. A line's cite that covers passes the line; a cite that covers nothing is refused. An
unknown cover (no act text, a row with no pattern, a row that does not compile) is never a refusal.

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

# r-asks covers `gh pr ready`, never a branch delete. r-del-asks covers the delete. r-nopat has no pattern, and
# r-broken has a pattern that does not compile.
NOPATTERN = dict(qf.hook_base.route_row("r-nopat", "unused", "asks", surface="local"))
del NOPATTERN["pattern"]
COVER_ROWS = [qf.hook_base.route_row("r-asks", "^gh pr ready\\b", "asks", surface="local", route="ask-first"),
              qf.hook_base.route_row("r-del-asks", "^git push origin --delete\\b", "asks", surface="local",
                                     route="ask-first"),
              qf.hook_base.route_row("r-broken", "(", "asks", surface="local"),
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

    def test_str_replace_with_a_backtick_span_no_row_matches_passes(self):
        """A span that matches no row is not an act this check can name, so the cite is unknown and passes."""
        hit = self.judge_str_replace(LINE + CITE % "r-asks" + ", so I ran `rm -rf build_x`.")
        self.assertEqual(hit, PASS, "a backtick span that no row matches (rm -rf build_x) is refused on its cite: %r"
                         % (hit,))

    def test_str_replace_with_a_known_backtick_act_the_row_does_not_match_is_refused(self):
        hit = self.judge_str_replace(LINE + CITE % "r-asks" + ", so I ran `git push origin --delete x`.")
        self.assertEqual(hit[0], WHY_RULE,
                         "r-asks covers no backtick span of new_str (git push origin --delete x), yet "
                         "task-why-cited did not refuse: %r" % (hit,))

    def test_a_command_ignores_a_span_another_row_matches(self):
        """With a command, the act is the command. A context span that another row matches is no act of the task."""
        hit = self.judge_task(task(LINE + CITE % "r-asks" + ", then `gh pr ready 12`.", command=DELETE))
        self.assertEqual(hit[0], WHY_RULE,
                         "r-asks covers the context span gh pr ready 12, not the delete command, yet the task "
                         "was not refused: %r" % (hit,))

    def test_a_command_citing_its_own_row_passes_beside_a_span(self):
        hit = self.judge_task(task(LINE + CITE % "r-del-asks" + ", then `gh pr ready 12`.", command=DELETE))
        self.assertEqual(hit, PASS, "r-del-asks covers the delete command, yet the task beside a span was refused: %r"
                         % (hit,))

    def test_a_press_only_span_no_row_matches_passes(self):
        """A press-only task has no command, and its span Merge matches no row: unknown, so it passes."""
        hit = self.judge_task(task(LINE + CITE % "r-asks" + ", then press `Merge`."))
        self.assertEqual(hit, PASS, "a press-only task whose span Merge matches no row is refused on its cite: %r"
                         % (hit,))

    def test_a_span_a_row_matches_is_refused_with_no_command(self):
        hit = self.judge_task(task(LINE + CITE % "r-asks" + ", then ran `git push origin --delete x`."))
        self.assertEqual(hit[0], WHY_RULE,
                         "r-asks covers no span of the task (git push origin --delete x), yet task-why-cited "
                         "did not refuse: %r" % (hit,))

    def test_a_line_whose_first_cite_is_unreadable_and_second_uncovered_is_refused(self):
        hit = self.judge_task(task(LINE + " (route r-broken) (route r-asks).", command=DELETE))
        self.assertEqual(hit[0], WHY_RULE,
                         "r-asks covers none of the delete command, and the line's first cite (r-broken, an uncompilable "
                         "pattern) is unknown, so the line is not refused: %r" % (hit,))

    def test_a_line_whose_first_cite_covers_passes_though_the_second_does_not(self):
        hit = self.judge_task(task(LINE + " (route r-del-asks) (route r-asks).", command=DELETE))
        self.assertEqual(hit, PASS, "the line's first cite r-del-asks covers the delete, yet the line was refused: %r"
                         % (hit,))

    def test_a_dated_measured_cite_backs_a_route_cite_on_a_delete(self):
        hit = self.judge_task(task(LINE + " (route r-asks) (measured 2026-11-07, try X failed).", command=DELETE))
        self.assertEqual(hit, PASS, "a dated measured cite on the line should back it on its own, yet it was refused: %r"
                         % (hit,))


if __name__ == "__main__":
    unittest.main()
