#!/usr/bin/env python3
"""Tests for ste_lint.apply_fixes, the STE auto-fix (decision ste-guard-fixes-not-nags).

The fixer keeps only the fixed bloat phrases of STE011, minus eight rows. The three rows the
decision plain-prose-lint names (in between, in terms of, it would appear that) are not in the
table, and five borderline rows (in a timely manner, along the lines of, close down, of major
importance, except when) stay errors with no fix. No Latin (STE007), contraction (STE008) or
nominalization (STE003) fix exists, and no fix changes the case of the text it swaps. The sentence
budget is one number, 30 words. Contractions, Latin abbreviations, nominalizations, phrasal verbs,
condition order and omitted "that" are advisory warnings: reported, never a rewrite.

    python lint/test_ste_autofix.py -v
"""
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ste_lint  # noqa: E402

# 38 words: STE001 against the one budget of 30.
LONG = ("The operators on each shift must record every valve position, every pressure reading, "
        "every alarm, and every handover note in the shared log before they leave the site today "
        "and then sign the page for the next crew.")
# 32 words with one "in order to" (3 words): the fix makes it 30 words, so the write passes.
SHRINKS_TO_LIMIT = ("The operators on each shift must record every valve position, every pressure reading, "
                    "every alarm, and every handover note in the shared log in order to help the next crew today now.")
# 33 words with one "in order to": the fix makes it 31 words, so STE001 stays.
SHRINKS_PAST_LIMIT = SHRINKS_TO_LIMIT[:-1] + " again."


class FixtureCountTests(unittest.TestCase):
    """The sentences above are the ones the cases below say they are."""

    def test_long_is_over_the_one_budget(self):
        self.assertEqual(ste_lint.count_words(LONG), 38)

    def test_shrinking_sentences_cross_the_budget_only_through_the_fix(self):
        self.assertEqual(ste_lint.count_words(SHRINKS_TO_LIMIT), 32)
        self.assertEqual(ste_lint.count_words(SHRINKS_PAST_LIMIT), 33)
        fixed_to, _ = ste_lint.apply_fixes(SHRINKS_TO_LIMIT)
        fixed_past, _ = ste_lint.apply_fixes(SHRINKS_PAST_LIMIT)
        self.assertEqual(ste_lint.count_words(fixed_to), 30)
        self.assertEqual(ste_lint.count_words(fixed_past), 31)


# ------------------------------------------------------------------ 1. golden grammar set
# (id, before, after). `after` is correct English. A row whose id ends in `_unchanged` holds a
# pattern the fixer must leave UNCHANGED: either a pattern whose fix plain-prose-lint removed, or an
# unsafe pattern that never had one. Other rows hold the correct fixed text of a kept bloat phrase.

GOLDEN = [
    ("g01_latin_start_cap_unchanged", "E.g. the pump stops.", "E.g. the pump stops."),
    ("g02_latin_mid_unchanged", "Use a tool, e.g. a hammer, for this.", "Use a tool, e.g. a hammer, for this."),
    ("g03_latin_end_comma_unchanged", "Stop the pump, e.g., during a test.", "Stop the pump, e.g., during a test."),
    ("g04_latin_in_parens_unchanged", "Check the valves (e.g. the inlet valve).", "Check the valves (e.g. the inlet valve)."),
    ("g05_ie_mid_unchanged", "Check the valves, i.e. the inlets.", "Check the valves, i.e. the inlets."),
    ("g06_etc_sentence_end_unchanged", "Test the unit at the end, etc.", "Test the unit at the end, etc."),
    ("g07_etc_mid_unchanged", "Pumps, valves, etc. must be checked.", "Pumps, valves, etc. must be checked."),
    ("g08_vs_unchanged", "The rule applies to pumps vs. valves.", "The rule applies to pumps vs. valves."),
    ("g09_vs_unchanged", "Compare Option A vs. Option B.", "Compare Option A vs. Option B."),
    ("g10_cf_unchanged", "See cf. section 4 for details.", "See cf. section 4 for details."),
    ("g11_via_unchanged", "Send the report via email.", "Send the report via email."),
    ("g12_et_al_commas_unchanged", "The team, et al., reviewed the design.", "The team, et al., reviewed the design."),
    ("g13_ad_hoc_unchanged", "This is an ad hoc fix.", "This is an ad hoc fix."),
    ("g14_contraction_mid_unchanged", "We don't stop the pump.", "We don't stop the pump."),
    ("g15_contraction_start_unchanged", "Don't stop the pump.", "Don't stop the pump."),
    ("g16_its_mid_unchanged", "The pump stops when it's full.", "The pump stops when it's full."),
    ("g17_lets_unchanged", "Let's test the valve.", "Let's test the valve."),
    ("g18_well_end_clause_unchanged", "Stop the pump, and we'll check it.", "Stop the pump, and we'll check it."),
    ("g19_wont_unchanged", "The pump won't start.", "The pump won't start."),
    ("g20_youd_unchanged", "You'd like the valve closed.", "You'd like the valve closed."),
    ("g21_theyve_unchanged", "The crews say they've finished.", "The crews say they've finished."),
    ("g23_in_order_to", "Close the valve in order to stop the flow.", "Close the valve to stop the flow."),
    ("g24_due_to_start", "Due to the fact that the seal wore, the pump failed.",
     "Because the seal wore, the pump failed."),
    ("g25_in_the_event", "In the event that the alarm sounds, leave the room.", "If the alarm sounds, leave the room."),
    ("g26_noted_delete_unchanged", "It should be noted that the pump runs hot.",
     "It should be noted that the pump runs hot."),
    ("g27_note_delete_unchanged", "Check it. Please note that the door is locked.",
     "Check it. Please note that the door is locked."),
    ("g28_conclusion_delete_unchanged", "In conclusion, the plan works.", "In conclusion, the plan works."),
    ("g29_majority_unchanged", "The majority of the valves are open.", "The majority of the valves are open."),
    ("g30_large_number", "We saw a large number of faults.", "We saw many faults."),
    ("g31_able_to", "We are able to finish today.", "We can finish today."),
    ("g32_first_of_all", "First of all, lock the door.", "First, lock the door."),
    ("g33_make_use_of_unchanged", "We made use of the new tool.", "We made use of the new tool."),
    ("g34_decision_about_unchanged", "Make a decision about the pump.", "Make a decision about the pump."),
    ("g35_take_into_consideration_unchanged", "The team will take into consideration the cost.",
     "The team will take into consideration the cost."),
    ("g36_gives_consideration_unchanged", "The team gives consideration to the cost.",
     "The team gives consideration to the cost."),
    ("g37_makes_use_unchanged", "It makes use of the pump.", "It makes use of the pump."),
    ("g38_provides_support_unchanged", "This provides support for the goal.", "This provides support for the goal."),
    ("g39_provide_support_plural_unchanged", "We provide support for the goal.", "We provide support for the goal."),
    ("g40_comparison_of_unchanged", "Do a comparison of the two bids.", "Do a comparison of the two bids."),
    ("g41_in_terms_of_unchanged", "The check is good in terms of safety.", "The check is good in terms of safety."),
    ("g42_list_item", "- Close the valve in order to stop the flow.", "- Close the valve to stop the flow."),
    ("g43_table_cell", "| 1 | Close it in order to isolate. |", "| 1 | Close it to isolate. |"),
    ("g44_comma_unchanged", "Stop, in order to test.", "Stop, in order to test."),
    ("g45_prior_to_start", "Prior to startup, check the oil.", "Before startup, check the oil."),
]


class GoldenGrammarTests(unittest.TestCase):
    """One method per golden row, so the report names the failing row."""


def _golden_case(before, after):
    def test(self):
        self.assertEqual(ste_lint.apply_fixes(before)[0], after)
    return test


for _gid, _before, _after in GOLDEN:
    setattr(GoldenGrammarTests, "test_" + _gid, _golden_case(_before, _after))


# ------------------------------------------------------------------ 2. removed fixes
# The decision plain-prose-lint removes every autofix it lists, and any other fix that rewrites
# more than whitespace or a fixed bloat phrase. The fixer has no whitespace fix. A fixed bloat
# phrase is a row of the STE011 table. So no STE007, STE008 or STE003 fix exists, and neither do
# the three STE011 rows the debt names.

# The debt's examples: (id, text). None may be rewritten.
DEBT_EXAMPLES = [
    ("its_all_been_fixed", "It's all been fixed\n"),
    ("ad_hoc", "This is an ad hoc fix.\n"),
    ("in_between", "Put the shim in between the plates.\n"),
    ("in_terms_of", "The check is good in terms of safety.\n"),
    ("it_would_appear_that", "It would appear that the pump failed.\n"),
    ("all_caps_its_a_test", "IT'S A TEST\n"),
    ("title_case_dont_trust", "Don't Trust\n"),
]

# One sample per removed fix row of the STE007, STE008 and STE003 families. None may be rewritten.
LATIN_SAMPLES = [
    ("eg_before_paren", "Check it (e.g.)\n"),
    ("eg_line_end", "Use tools, e.g.\n"),
    ("eg_mid", "Use a tool, e.g. a hammer, for this.\n"),
    ("ie_before_paren", "Check it (i.e.)\n"),
    ("ie_line_end", "Check the valves, i.e.\n"),
    ("ie_mid", "Check the valves, i.e. the inlets.\n"),
    ("etc_sentence_end", "Test the unit at the end, etc.\n"),
    ("etc_mid", "Pumps, valves, etc. must be checked.\n"),
    ("et_al_sentence_end", "The paper is by Smith et al. The next section is done.\n"),
    ("et_al_mid", "The team, et al., reviewed the design.\n"),
    ("ad_hoc", "This is an ad hoc fix.\n"),
    ("viz", "Name the tool, viz. the hammer.\n"),
]
CONTRACTION_SAMPLES = [
    ("cant", "We can't stop the pump.\n"),
    ("wont", "The pump won't start.\n"),
    ("dont", "We don't stop the pump.\n"),
    ("doesnt", "The valve doesn't leak.\n"),
    ("didnt", "The seal didn't hold.\n"),
    ("isnt", "The valve isn't open.\n"),
    ("arent", "The valves aren't open.\n"),
    ("wasnt", "The gauge wasn't read.\n"),
    ("werent", "The gauges weren't read.\n"),
    ("hasnt", "The pump hasn't started.\n"),
    ("havent", "The crews haven't left.\n"),
    ("hadnt", "The crew hadn't left.\n"),
    ("shouldnt", "You shouldn't stop it.\n"),
    ("wouldnt", "It wouldn't start.\n"),
    ("couldnt", "It couldn't start.\n"),
    ("mustnt", "You mustn't stop it.\n"),
    ("its_full", "The pump stops when it's full.\n"),
    ("thats_a", "That's a good sign.\n"),
    ("theres_a", "There's a leak.\n"),
    ("heres", "Here's the plan.\n"),
    ("whats_the", "What's the plan?\n"),
    ("lets", "Let's test the valve.\n"),
    ("youre", "You're ready.\n"),
    ("were", "We're ready.\n"),
    ("theyre", "They're ready.\n"),
    ("youll", "You'll see it.\n"),
    ("well", "We'll check it.\n"),
    ("itll", "It'll start.\n"),
    ("youve", "You've seen it.\n"),
    ("weve", "We've seen it.\n"),
    ("theyve", "They've seen it.\n"),
    ("youd_like", "You'd like the valve closed.\n"),
]
NOMINALIZATION_SAMPLES = [
    ("makes_use_of", "It makes use of the pump.\n"),
    ("make_use_of", "We make use of the pump.\n"),
    ("made_use_of", "We made use of the new tool.\n"),
    ("take_into_consideration", "The team will take into consideration the cost.\n"),
    ("gives_consideration_to", "The team gives consideration to the cost.\n"),
    ("give_consideration_to", "We give consideration to the cost.\n"),
    ("do_a_comparison_of", "Do a comparison of the two bids.\n"),
    ("make_a_decision_about", "Make a decision about the pump.\n"),
    ("provide_a_description_of", "Provide a description of the seal.\n"),
    ("effect_a_change_to", "Effect a change to the plan.\n"),
    ("provides_support_for", "This provides support for the goal.\n"),
    ("provide_support_for", "We provide support for the goal.\n"),
    ("is_in_violation_of", "The plan is in violation of the rule.\n"),
]


class RemovedFixesTests(unittest.TestCase):
    """apply_fixes leaves every removed fix's text exactly as written. One method per sample."""


def _not_rewritten(text):
    def test(self):
        self.assertEqual(ste_lint.apply_fixes(text)[0], text)
    return test


for _prefix, _rows in (("debt", DEBT_EXAMPLES), ("latin", LATIN_SAMPLES),
                       ("contraction", CONTRACTION_SAMPLES), ("nominalization", NOMINALIZATION_SAMPLES)):
    for _rid, _text in _rows:
        setattr(RemovedFixesTests, "test_%s_%s_not_rewritten" % (_prefix, _rid), _not_rewritten(_text))


class KeptFixesTests(unittest.TestCase):
    """The fixes that stay: the fixed bloat phrases of STE011. The case of the text is never
    changed to fit a swap (the class of IT'S A TEST and Don't Trust in the debt)."""

    def test_k01_all_caps_phrase_keeps_its_case_or_is_left_alone(self):
        # The fix must not turn "PRIOR TO START" into "Before START".
        out = ste_lint.apply_fixes("PRIOR TO START, CHECK THE OIL.\n")[0]
        self.assertIn(out, ("PRIOR TO START, CHECK THE OIL.\n", "BEFORE START, CHECK THE OIL.\n"))

    def test_k02_all_caps_in_order_to_keeps_its_case_or_is_left_alone(self):
        # The fix must not turn "IN ORDER TO STOP" into "To STOP".
        out = ste_lint.apply_fixes("CLOSE IT IN ORDER TO STOP THE PUMP.\n")[0]
        self.assertIn(out, ("CLOSE IT IN ORDER TO STOP THE PUMP.\n", "CLOSE IT TO STOP THE PUMP.\n"))

    def test_k03_sentence_start_phrase_still_gets_a_capital(self):
        # Guard: the kept swap still reads right at a sentence start.
        self.assertEqual(ste_lint.apply_fixes("Prior to startup, check the oil.\n")[0],
                         "Before startup, check the oil.\n")


# ------------------------------------------------------------------ 3a. fixer safety

class FixerSafetyTests(unittest.TestCase):
    """apply_fixes must never change code, quoted text, or the layout of a Markdown file. Each
    fixture holds a kept bloat phrase (in order to, prior to), so the mask has a fix to refuse."""

    def test_s01_code_fence_unchanged(self):
        text = ("```python\nx = \"in order to\"  # prior to this\n```\n"
                "```sh\n# prior to this, run in order to win\n```\n")
        self.assertEqual(ste_lint.apply_fixes(text)[0], text)

    def test_s02_inline_code_unchanged(self):
        text = "Run `in order to` and `prior to` here."
        self.assertEqual(ste_lint.apply_fixes(text)[0], text)

    def test_s03_quoted_text_unchanged(self):
        text = 'The sign says "enter prior to the bell" now.'
        self.assertEqual(ste_lint.apply_fixes(text)[0], text)

    def test_s04_lone_quote_in_text_does_not_stop_the_fix(self):
        self.assertEqual(ste_lint.apply_fixes('The 5" pipe, close it in order to stop.')[0],
                         'The 5" pipe, close it to stop.')

    def test_s05_comment_openers_inside_inline_code_unchanged(self):
        text = 'Set `a = "/* x */"` and `b = "# y"`; then close it in order to stop.'
        self.assertEqual(ste_lint.apply_fixes(text)[0],
                         'Set `a = "/* x */"` and `b = "# y"`; then close it to stop.')

    def test_s06_multiline_template_literal_in_fence_unchanged(self):
        text = ("```js\nconst s = `line one in order to\nline two prior to // keep /* keep */`;\n```\n")
        self.assertEqual(ste_lint.apply_fixes(text)[0], text)

    def test_s07_indented_code_block_unchanged(self):
        text = "    cp  a.txt  prior to.txt\n"
        self.assertEqual(ste_lint.apply_fixes(text)[0], text)

    def test_s08_nested_list_indent_kept(self):
        self.assertEqual(ste_lint.apply_fixes("- item\n  - Close the valve in order to stop.\n")[0],
                         "- item\n  - Close the valve to stop.\n")

    def test_s09_trailing_two_space_hard_break_kept(self):
        self.assertEqual(ste_lint.apply_fixes("Close it in order to stop.  \nLine two\n")[0],
                         "Close it to stop.  \nLine two\n")

    def test_s10_space_before_dotted_name_kept(self):
        text = "Copy the file .env now.\n"
        self.assertEqual(ste_lint.apply_fixes(text)[0], text)


# ------------------------------------------------------------------ eight STE011 rows without a fix

# Five borderline rows: the phrase is still an error, and no
# rewrite is applied. The swap changes meaning or tone in some contexts.
BORDERLINE_BLOAT = [
    ("in_a_timely_manner", "Send the report in a timely manner.\n"),
    ("along_the_lines_of", "The design is along the lines of the old one.\n"),
    ("close_down", "Operators close down the plant at night.\n"),
    ("of_major_importance", "This task is of major importance to the crew.\n"),
    ("except_when", "Do not run it except when the gauge reads zero.\n"),
]
# The three debt phrases (orchestrator's call 3): out of the STE011 table, so the linter says
# nothing and the fixer leaves them.
DROPPED_BLOAT = [row for row in DEBT_EXAMPLES
                 if row[0] in ("in_between", "in_terms_of", "it_would_appear_that")]


def _findings(text):
    return ste_lint.Linter(dict(ste_lint.DEFAULT_CONFIG)).check_text("t.md", text)


class BorderlineBloatTests(unittest.TestCase):
    """The five borderline rows stay STE011 errors and are never rewritten."""

    def test_o01_still_an_error_in_the_linter(self):
        # The row is kept, only its fix goes.
        for rid, text in BORDERLINE_BLOAT:
            with self.subTest(phrase=rid):
                hits = [f for f in _findings(text) if f.code == "STE011"]
                self.assertTrue(hits)
                self.assertEqual({f.severity for f in hits}, {"error"})

    def test_o02_apply_fixes_leaves_the_text(self):
        for rid, text in BORDERLINE_BLOAT:
            with self.subTest(phrase=rid):
                self.assertEqual(ste_lint.apply_fixes(text)[0], text)


class DroppedBloatTests(unittest.TestCase):
    """The three debt phrases are not rules any more: no finding, no rewrite."""

    def test_o05_the_linter_reports_no_ste011(self):
        for rid, text in DROPPED_BLOAT:
            with self.subTest(phrase=rid):
                self.assertEqual([f.code for f in _findings(text) if f.code == "STE011"], [])


    def test_o08_the_kept_rows_still_get_their_fix(self):
        # Guard: green before and after. Dropping eight rows must not drop the rest.
        self.assertEqual(ste_lint.apply_fixes("Prior to startup, check the oil.\n")[0],
                         "Before startup, check the oil.\n")
        self.assertEqual(ste_lint.apply_fixes("Close it in order to stop the pump.\n")[0],
                         "Close it to stop the pump.\n")


# ------------------------------------------------------------------ fixer edge cases
# Each name starts with its finding number. test_r1_guard_* cases hold a failure class the fix
# must not break. Each fixture holds a kept bloat phrase, so the check still has a fix to refuse.

class ReviewRound1FixerTests(unittest.TestCase):
    """apply_fixes on Markdown text: links, quotes, fences, front matter, English."""

    # F1 links keep their URL.
    def test_r1_f1_link_url_kept(self):
        inp = "See [the guide](https://a.example/g) and act in order to finish.\n"
        out = ste_lint.apply_fixes(inp)[0]
        self.assertIn("https://a.example/g", out)
        self.assertIn(out, (inp, "See [the guide](https://a.example/g) and act to finish.\n"))

    def test_r1_f1_image_url_kept(self):
        inp = "See ![alt](u) and act in order to finish.\n"
        out = ste_lint.apply_fixes(inp)[0]
        self.assertIn("![alt](u)", out)
        self.assertIn(out, (inp, "See ![alt](u) and act to finish.\n"))

    def test_r1_guard_reference_link_kept(self):
        inp = "See [a][b] and act in order to finish.\n\n[b]: https://x.y\n"
        out = ste_lint.apply_fixes(inp)[0]
        self.assertIn("[a][b]", out)
        self.assertIn("[b]: https://x.y", out)

    def test_r1_guard_autolink_kept(self):
        out = ste_lint.apply_fixes("See <https://x.y> and act in order to finish.\n")[0]
        self.assertIn("<https://x.y>", out)

    # F2 quoted code survives
    def test_r1_f2_quoted_code_kept(self):
        inp = 'He said "run `x`" and act in order to stop.\n'
        out = ste_lint.apply_fixes(inp)[0]
        self.assertIn("run `x`", out)
        self.assertIn(out, (inp, 'He said "run `x`" and act to stop.\n'))

    # F3a fence content is never rewritten
    def test_r1_f3a_four_backtick_fence_unchanged(self):
        inp = "````\n```\nrun in order to prior to here\n```\n````\n"
        self.assertEqual(ste_lint.apply_fixes(inp)[0], inp)

    def test_r1_f3a_tilde_fence_unchanged(self):
        inp = "~~~\n```\nrun in order to prior to here\n```\n~~~\n"
        self.assertEqual(ste_lint.apply_fixes(inp)[0], inp)

    # F4 front matter, and fixes that break English
    def test_r1_f4_front_matter_unchanged(self):
        inp = "---\ntags: [a, in order to b]\n---\n\nText.\n"
        self.assertEqual(ste_lint.apply_fixes(inp)[0], inp)

    def test_r1_f4_there_is_two_unchanged(self):
        self.assertEqual(ste_lint.apply_fixes("There's two pumps.\n")[0], "There's two pumps.\n")

    def test_r1_f4_per_se_unchanged(self):
        self.assertEqual(ste_lint.apply_fixes("This is a per se violation.\n")[0],
                         "This is a per se violation.\n")

    def test_r1_f4_paren_eg_unchanged(self):
        self.assertEqual(ste_lint.apply_fixes("Check it (e.g.)\n")[0], "Check it (e.g.)\n")

    def test_r1_f4_final_eg_unchanged(self):
        self.assertEqual(ste_lint.apply_fixes("Use tools, e.g.\n")[0], "Use tools, e.g.\n")

    # Failure-class guards: CRLF, multi-byte text, lone quote in HTML text
    def test_r1_guard_crlf_kept(self):
        self.assertEqual(ste_lint.apply_fixes("Close it in order to stop.\r\nClose it in order to stop.\r\n")[0],
                         "Close it to stop.\r\nClose it to stop.\r\n")
        # A Latin abbreviation is left as it is, and every line keeps its CRLF, none mixed.
        self.assertEqual(ste_lint.apply_fixes("Prior to start, use tools, e.g.\r\nClose it in order to stop.\r\n")[0],
                         "Before start, use tools, e.g.\r\nClose it to stop.\r\n")

    def test_r1_guard_multibyte_kept(self):
        self.assertEqual(ste_lint.apply_fixes("Café — close it in order to stop, naïve.\n")[0],
                         "Café — close it to stop, naïve.\n")

    def test_r1_guard_jsx_text_in_md_kept(self):
        # building-scanner-respects-strings: a lone quote in HTML text (the apostrophe of Don't)
        # must not stop the fix of the words after it.
        self.assertEqual(ste_lint.apply_fixes("<p>Don't close it in order to stop</p>\n")[0],
                         "<p>Don't close it to stop</p>\n")


# F4: an ambiguous 's (is or has) or 'd (would or had) stays unchanged. Every contraction stays
# unchanged, so these rows are plain "not rewritten" pins.
AMBIGUOUS_FORMS = [
    ("youd", "You'd finished the job.\n"),
    ("wed", "We'd finished the job.\n"),
    ("theyd", "They'd finished the work.\n"),
    ("hed", "He'd finished the job.\n"),
    ("shed", "She'd finished the job.\n"),
    ("itd", "It'd been finished by noon.\n"),
    ("thats", "That's been checked.\n"),
    ("hes", "He's finished the check.\n"),
    ("shes", "She's finished the check.\n"),
    ("whats", "What's been done?\n"),
    ("its", "It's been tested.\n"),
]


def _ambiguous_case(text):
    def test(self):
        self.assertEqual(ste_lint.apply_fixes(text)[0], text)
    return test


for _aid, _text in AMBIGUOUS_FORMS:
    setattr(ReviewRound1FixerTests, "test_r1_f4_ambiguous_" + _aid, _ambiguous_case(_text))


# ------------------------------------------------------------------ more fixer edge cases
# Names start with the finding number. test_r2_guard_* cases hold a failure class the fix must keep.

# F1: an adverb between the form and a perfect verb. No contraction is fixed, so the text
# is never rewritten.
ADVERBS = ["never", "always", "also", "now", "only", "not"]


class ReviewRound2FixerTests(unittest.TestCase):
    """apply_fixes on Markdown text, second set."""

    # F2 code in a blockquote fence and in a raw HTML block stays unchanged
    def test_r2_f2_blockquote_fence_unchanged(self):
        inp = "> ```\n> prior to the code\n> ```\n"
        self.assertEqual(ste_lint.apply_fixes(inp)[0], inp)

    def test_r2_f2_pre_block_unchanged(self):
        inp = "<pre>\nprior to x\n</pre>\n"
        self.assertEqual(ste_lint.apply_fixes(inp)[0], inp)

    def test_r2_guard_list_item_fence_two_spaces_unchanged(self):
        inp = "- item\n\n  ```\n  prior to the code\n  ```\n"
        self.assertEqual(ste_lint.apply_fixes(inp)[0], inp)

    def test_r2_guard_list_item_fence_four_spaces_unchanged(self):
        inp = "1. Step one:\n\n    ```sh\n    run in order to win\n    ```\n"
        self.assertEqual(ste_lint.apply_fixes(inp)[0], inp)

    # F3 et al. and N.B. are left as written
    def test_r2_f3_et_al_unchanged(self):
        inp = "The paper is by Smith et al. The next section is done.\n"
        self.assertEqual(ste_lint.apply_fixes(inp)[0], inp)

    def test_r2_f3_nb_unchanged(self):
        inp = "N.B., the file is locked.\n"
        self.assertEqual(ste_lint.apply_fixes(inp)[0], inp)

    # F4 a shortcut reference label and its definition stay in sync
    def test_r2_f4_shortcut_label_in_sync(self):
        inp = "See [prior to start] now.\n\n[prior to start]: notes.md\n"
        out = ste_lint.apply_fixes(inp)[0]
        self.assertIn(out, (inp, "See [before start] now.\n\n[before start]: notes.md\n"))

    # F6 pure-function speed: "a." * 40000 finishes in under 3 s. Run in a child process
    # with a 20 s cap, so a quadratic fixer fails the test instead of hanging it.
    def test_r2_f6_apply_fixes_40000_pairs_under_3s(self):
        code = ("import sys, time; sys.path.insert(0, %r); import ste_lint; "
                "t = time.perf_counter(); ste_lint.apply_fixes('a.' * 40000); "
                "print(time.perf_counter() - t)" % HERE)
        try:
            run = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                                 timeout=20)
        except subprocess.TimeoutExpired:
            self.fail("apply_fixes on 'a.' * 40000 ran past 20 s")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertLess(float(run.stdout), 3.0)


def _pin_unchanged(text):
    def test(self):
        self.assertEqual(ste_lint.apply_fixes(text)[0], text)
    return test


for _adv in ADVERBS:
    setattr(ReviewRound2FixerTests, "test_r2_f1_its_" + _adv,
            _pin_unchanged("It's %s been tested.\n" % _adv))
    setattr(ReviewRound2FixerTests, "test_r2_f1_theres_" + _adv,
            _pin_unchanged("There's %s been a way.\n" % _adv))
setattr(ReviewRound2FixerTests, "test_r2_guard_had_its", _pin_unchanged("It's had a fault.\n"))
setattr(ReviewRound2FixerTests, "test_r2_guard_had_theres", _pin_unchanged("There's had a fault.\n"))


if __name__ == "__main__":
    unittest.main()
