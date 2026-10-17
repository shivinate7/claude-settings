#!/usr/bin/env python3
"""Tests for the STE auto-fix in lint/ste_gate.py (plan section C).

The gate fixes a Markdown write with ste_lint.apply_fixes, returns the fixed text through the
PreToolUse updatedInput, and denies only the errors that remain. UI files are never fixed.

Owner ruling 2026-10-17 (turn the STE lint into a plain-prose lint): the fixer keeps only the
fixed bloat phrases of STE011, minus the three the debt ste-fix-changes-meaning names (in between,
in terms of, it would appear that). Every Latin (STE007), contraction (STE008) and nominalization
(STE003) fix is gone, and no fix changes the case of the text it swaps. The sentence budget is one
number, 30 words. Contractions, Latin abbreviations, nominalizations, phrasal verbs, condition order
and omitted "that" are advisory warnings: reported, never a deny, never a rewrite.

    python lint/test_ste_autofix.py -v
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ste_lint  # noqa: E402
from test_gates import STE_GATE, run_gate, setUpModule, tearDownModule  # noqa: E402,F401  (the helper and the module isolation hooks; no TestCase is collected)

# 38 words: STE001 against the one budget of 30.
LONG = ("The operators on each shift must record every valve position, every pressure reading, "
        "every alarm, and every handover note in the shared log before they leave the site today "
        "and then sign the page for the next crew.")
# 32 words with one "in order to" (3 words): the fix makes it 30 words, so the write passes.
SHRINKS_TO_LIMIT = ("The operators on each shift must record every valve position, every pressure reading, "
                    "every alarm, and every handover note in the shared log in order to help the next crew today now.")
# 33 words with one "in order to": the fix makes it 31 words, so STE001 stays.
SHRINKS_PAST_LIMIT = SHRINKS_TO_LIMIT[:-1] + " again."


def parse(run):
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout) if run.stdout.strip() else {}


def hso(run):
    return parse(run).get("hookSpecificOutput", {})


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
# pattern the fixer must leave UNCHANGED: either a fix removed by the 2026-10-17 ruling, or an
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


# ------------------------------------------------------------------ 2. fixes removed by the ruling
# Owner ruling 2026-10-17, point 2: remove every autofix the debt ste-fix-changes-meaning lists, and
# any other fix that rewrites more than whitespace or a fixed bloat phrase. The fixer has no
# whitespace fix. A fixed bloat phrase is a row of the STE011 table. So every STE007, STE008 and
# STE003 fix goes, and so do the three STE011 rows the debt names.

# The debt's examples: (id, text). Each was rewritten before the ruling.
DEBT_EXAMPLES = [
    ("its_all_been_fixed", "It's all been fixed\n"),
    ("ad_hoc", "This is an ad hoc fix.\n"),
    ("in_between", "Put the shim in between the plates.\n"),
    ("in_terms_of", "The check is good in terms of safety.\n"),
    ("it_would_appear_that", "It would appear that the pump failed.\n"),
    ("all_caps_its_a_test", "IT'S A TEST\n"),
    ("title_case_dont_trust", "Don't Trust\n"),
]

# One sample per fix row of the STE007, STE008 and STE003 families (the rows FIXABLE held before
# the ruling). Each was rewritten before the ruling; none may be now.
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
        # Before the ruling "PRIOR TO START" became "Before START".
        out = ste_lint.apply_fixes("PRIOR TO START, CHECK THE OIL.\n")[0]
        self.assertIn(out, ("PRIOR TO START, CHECK THE OIL.\n", "BEFORE START, CHECK THE OIL.\n"))

    def test_k02_all_caps_in_order_to_keeps_its_case_or_is_left_alone(self):
        # Before the ruling "IN ORDER TO STOP" became "To STOP".
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


# ------------------------------------------------------------------ gate cases

class _GateCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _path(self, name):
        return os.path.join(self.tmp.name, name)

    def _write(self, name, text):
        with open(self._path(name), "w", encoding="utf-8") as f:
            f.write(text)
        return self._path(name)

    def _pre(self, tool, tool_input, gate=STE_GATE):
        hook = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input}
        return run_gate(gate, hook)


class GateFixTests(_GateCase):
    """ste_gate.py on a PreToolUse Write or Edit of a Markdown file."""

    # (a) fixable errors only -> rewritten input, no deny

    def test_01_fixable_only_write_is_rewritten_not_denied(self):
        target = self._path("notes.md")
        run = self._pre("Write", {"file_path": target,
                                  "content": "We close the valve in order to stop the pump, prior to the shift.\n"})
        out = hso(run)
        self.assertNotEqual(out.get("permissionDecision"), "deny")
        self.assertEqual(out.get("updatedInput"),
                         {"file_path": target, "content": "We close the valve to stop the pump, before the shift.\n"})

    def test_02_rewrite_grants_no_allow(self):
        # Docs: "allow" auto-approves, and "defer" makes the hook ignore updatedInput. The docs do
        # not say "allow" is required with updatedInput, so the rewrite must not add one.
        target = self._path("notes.md")
        out = hso(self._pre("Write", {"file_path": target,
                                      "content": "We close the valve in order to stop the pump.\n"}))
        self.assertIsNotNone(out.get("updatedInput"), "the rewrite is missing")
        self.assertNotIn(out.get("permissionDecision"), ("allow", "defer"))

    def test_03_fixable_plus_unfixable_denies_with_remaining_only(self):
        target = self._path("mixed.md")
        content = "We close the valve in order to stop the pump.\n\n" + LONG + "\n"
        run = self._pre("Write", {"file_path": target, "content": content})
        out = hso(run)
        self.assertEqual(out.get("permissionDecision"), "deny")
        reason = out["permissionDecisionReason"]
        self.assertIn("STE001", reason)
        self.assertIn("operators on each shift", reason, "the sentence is not named")
        self.assertIn("38", reason, "the word count is missing")
        self.assertRegex(reason, r"\b30\b", "the limit is missing")
        self.assertIn("split", reason.lower(), "no split point is suggested")
        self.assertNotIn("STE011", reason, "a fixed bloat phrase is still reported")

    def test_04_denial_shows_at_most_five_findings(self):
        target = self._path("many.md")
        content = "\n\n".join([LONG] * 7) + "\n"
        out = hso(self._pre("Write", {"file_path": target, "content": content}))
        self.assertEqual(out.get("permissionDecision"), "deny")
        findings = [ln for ln in out["permissionDecisionReason"].splitlines()
                    if re.match(r"line \d+: STE001", ln)]
        self.assertTrue(0 < len(findings) <= 5, "showed %d findings" % len(findings))

    def test_05_clean_text_no_output(self):
        run = self._pre("Write", {"file_path": self._path("ok.md"),
                                  "content": "The pump runs at low speed.\n"})
        self.assertEqual(run.stdout.strip(), "")

    def test_06_write_fixes_only_the_changed_block(self):
        disk = "Close it in order to stop.\n\nOld block: prior to this, it is fine.\n"
        target = self._write("blocks.md", disk)
        content = disk + "\nNew block: close it in order to stop, prior to the shift.\n"
        out = hso(self._pre("Write", {"file_path": target, "content": content}))
        self.assertEqual(out.get("updatedInput", {}).get("content"),
                         disk + "\nNew block: close it to stop, before the shift.\n")

    def test_07_edit_fixes_only_new_string(self):
        disk = "Close it in order to stop.\n\nOld block: prior to this, it is fine.\n"
        target = self._write("edit.md", disk)
        out = hso(self._pre("Edit", {"file_path": target,
                                     "old_string": "Old block: prior to this, it is fine.\n",
                                     "new_string": "New block: close it in order to stop, prior to the shift.\n"}))
        self.assertEqual(out.get("updatedInput"), {
            "file_path": target,
            "old_string": "Old block: prior to this, it is fine.\n",
            "new_string": "New block: close it to stop, before the shift.\n",
        })

    def test_08_edit_not_on_disk_lints_whole_text_and_fixes_it(self):
        target = self._write("unreplayable.md", "Clean text.\n")
        out = hso(self._pre("Edit", {"file_path": target,
                                     "old_string": "Nowhere on disk.\n",
                                     "new_string": "We close it in order to stop, prior to the shift.\n"}))
        self.assertEqual(out.get("updatedInput"), {
            "file_path": target,
            "old_string": "Nowhere on disk.\n",
            "new_string": "We close it to stop, before the shift.\n",
        })

    def test_09_edit_not_on_disk_remaining_error_denied(self):
        target = self._write("unreplayable2.md", "Clean text.\n")
        out = hso(self._pre("Edit", {"file_path": target,
                                     "old_string": "Nowhere on disk.\n",
                                     "new_string": LONG + "\n"}))
        self.assertEqual(out.get("permissionDecision"), "deny")
        self.assertIn("STE001", out["permissionDecisionReason"])

    def test_10_output_names_the_fixed_code_without_a_deny(self):
        # One line that names what was fixed, and no deny.
        run = self._pre("Write", {"file_path": self._path("named.md"),
                                  "content": "We close the valve in order to stop the pump.\n"})
        self.assertNotEqual(hso(run).get("permissionDecision"), "deny")
        self.assertIn("STE011", run.stdout)

    def _crash_gate(self):
        # A copy of the gate whose apply_fixes writes a marker and then raises.
        d = os.path.join(self.tmp.name, "gate")
        os.makedirs(d)
        for src in glob.glob(os.path.join(HERE, "*.py")):
            if not os.path.basename(src).startswith("test_"):
                shutil.copy(src, d)
        marker = self._path("fixer-ran.txt")
        with open(os.path.join(d, "ste_lint.py"), "a", encoding="utf-8") as f:
            f.write("\n\ndef apply_fixes(text):\n    open(%r, 'w').close()\n"
                    "    raise RuntimeError('fixer crash')\n" % marker)
        return os.path.join(d, "ste_gate.py"), marker

    def test_11_fixer_crash_falls_back_to_deny_and_exits_zero(self):
        # Ruling (decisions/gate-hooks-fail-closed.md): a crash does not refuse. The gate skips
        # the rewrite, keeps today's behaviour (deny on the lint errors), exits 0, never 2.
        gate, marker = self._crash_gate()
        run = run_gate(gate, {"hook_event_name": "PreToolUse", "tool_name": "Write",
                              "tool_input": {"file_path": self._path("crash.md"),
                                             "content": "We close the valve in order to stop the pump.\n"}})
        self.assertNotEqual(run.returncode, 2)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(os.path.exists(marker), "the fixer never ran")
        out = hso(run)
        self.assertEqual(out.get("permissionDecision"), "deny")
        self.assertIn("STE011", out["permissionDecisionReason"])
        self.assertNotIn("updatedInput", out)

    def test_11b_fixer_crash_on_clean_text_allows(self):
        gate, marker = self._crash_gate()
        run = run_gate(gate, {"hook_event_name": "PreToolUse", "tool_name": "Write",
                              "tool_input": {"file_path": self._path("clean.md"),
                                             "content": "The pump runs at low speed.\n"}})
        self.assertNotEqual(run.returncode, 2)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(os.path.exists(marker), "the fixer never ran")
        self.assertEqual(run.stdout.strip(), "")

    def test_12_fence_only_write_no_output(self):
        run = self._pre("Write", {"file_path": self._path("fence.md"),
                                  "content": "```sh\nrun in order to here\n```\n"})
        self.assertEqual(run.stdout.strip(), "")

    def test_13_fix_then_lint_lets_a_sentence_the_fix_shrinks_under_the_limit_pass(self):
        # 32 words as written, 30 once "in order to" becomes "to". Lint-before-fix would deny it.
        target = self._path("shrink.md")
        out = hso(self._pre("Write", {"file_path": target, "content": SHRINKS_TO_LIMIT + "\n"}))
        self.assertNotEqual(out.get("permissionDecision"), "deny")
        self.assertIn("updatedInput", out)

    def test_13b_fix_then_lint_still_denies_a_sentence_the_fix_leaves_over_the_limit(self):
        # 33 words as written, 31 after the fix: STE001 stays, and the reason reports the fixed count.
        out = hso(self._pre("Write", {"file_path": self._path("shrink2.md"),
                                      "content": SHRINKS_PAST_LIMIT + "\n"}))
        self.assertEqual(out.get("permissionDecision"), "deny")
        reason = out["permissionDecisionReason"]
        self.assertIn("STE001", reason)
        self.assertNotIn("STE011", reason)

    # Advisory text (ruling 2026-10-17): the gate neither denies nor rewrites it. The text stays
    # exactly as the writer wrote it.

    def test_14_latin_vs_cf_via_neither_denied_nor_rewritten(self):
        content = "Compare Option A vs. Option B.\n\nSee cf. section 4.\n\nSend it via email.\n"
        out = hso(self._pre("Write", {"file_path": self._path("latin.md"), "content": content}))
        self.assertNotEqual(out.get("permissionDecision"), "deny")
        self.assertNotIn("updatedInput", out)

    def test_15_would_neither_denied_nor_rewritten(self):
        out = hso(self._pre("Write", {"file_path": self._path("would.md"),
                                      "content": "They'd finished the work.\n"}))
        self.assertNotEqual(out.get("permissionDecision"), "deny")
        self.assertNotIn("updatedInput", out)

    # Unsafe bloat deletions stay unfixed, and STE011 stays an error: the write is denied.

    def test_16_unsafe_deletions_and_majority_denied_not_rewritten(self):
        content = ("In conclusion, the plan works.\n\nThe majority of the valves are open.\n\n"
                   "We will check it.\n")
        out = hso(self._pre("Write", {"file_path": self._path("bloat.md"), "content": content}))
        self.assertEqual(out.get("permissionDecision"), "deny")
        self.assertIn("STE011", out["permissionDecisionReason"])
        self.assertNotIn("updatedInput", out)


class RemovedFixesGateTests(_GateCase):
    """The gate returns no updatedInput for any text whose only fix the ruling removed."""

    def _assert_not_rewritten(self, text):
        out = hso(self._pre("Write", {"file_path": self._path("t.md"), "content": text}))
        self.assertNotIn("updatedInput", out)
        return out

    def test_g01_debt_examples_not_rewritten_by_write(self):
        for rid, text in DEBT_EXAMPLES:
            with self.subTest(example=rid):
                self._assert_not_rewritten(text)

    def test_g02_debt_examples_not_rewritten_by_edit(self):
        target = self._write("e.md", "Intro.\n")
        for rid, text in DEBT_EXAMPLES:
            with self.subTest(example=rid):
                out = hso(self._pre("Edit", {"file_path": target, "old_string": "Intro.\n",
                                             "new_string": text}))
                self.assertNotIn("updatedInput", out)

    def test_g03_latin_contraction_nominalization_text_is_advisory_only(self):
        # Neither a rewrite nor a deny: STE007, STE008 and STE003 are warnings now.
        families = (("latin", LATIN_SAMPLES), ("contraction", CONTRACTION_SAMPLES),
                    ("nominalization", NOMINALIZATION_SAMPLES))
        for name, rows in families:
            with self.subTest(family=name):
                out = self._assert_not_rewritten("\n".join(t for _, t in rows))
                self.assertNotEqual(out.get("permissionDecision"), "deny")


# ------------------------------------------------------------------ UI files: no rewrite

class UiFileTests(_GateCase):
    """UI files keep today's behaviour: the gate denies, and never rewrites the input."""

    def test_u01_tsx_contraction_not_rewritten(self):
        # STE008 does not apply to UI copy, so this is clean today.
        run = self._pre("Write", {"file_path": self._path("Page.tsx"),
                                  "content": "export const P = () => <p>Don't</p>;\n"})
        self.assertNotIn("updatedInput", hso(run))

    def test_u02_tsx_bloat_denied_and_not_rewritten(self):
        # STE007 is a warning now, so the UI sample is a kept error: STE011.
        run = self._pre("Write", {"file_path": self._path("Help.tsx"),
                                  "content": "export const H = () => <p>Prior to use, read it.</p>;\n"})
        out = hso(run)
        self.assertEqual(out.get("permissionDecision"), "deny")
        self.assertIn("STE011", out["permissionDecisionReason"])
        self.assertNotIn("updatedInput", out)


# ------------------------------------------------------------------ review round 1 (PR 367)
# Red pins for the reviewer's findings. Each name starts with its finding number.
# test_r1_guard_* cases pass today: they hold a failure class the fix must not break.
# After the 2026-10-17 ruling each fixture holds a kept bloat phrase, so the check still has a
# fix to refuse.

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


# F4: an ambiguous 's (is or has) or 'd (would or had) stays unchanged. After the 2026-10-17
# ruling every contraction stays unchanged, so these rows are plain "not rewritten" pins.
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


class ReviewRound1GateTests(_GateCase):
    """ste_gate.py, through PreToolUse: the rewrite must match what the file will hold."""

    def _copy_gate(self, appended):
        # A copy of the gate with `appended` added to the copied ste_lint.py, the seam
        # _crash_gate uses. The appended apply_fixes overrides the real one.
        d = os.path.join(self.tmp.name, "gate-%d" % len(appended))
        os.makedirs(d)
        for src in glob.glob(os.path.join(HERE, "*.py")):
            if not os.path.basename(src).startswith("test_"):
                shutil.copy(src, d)
        with open(os.path.join(d, "ste_lint.py"), "a", encoding="utf-8") as f:
            f.write(appended)
        return os.path.join(d, "ste_gate.py")

    # F3 an Edit that lands inside a code span or a fence is not rewritten inside it
    def test_r1_f3b_gate_edit_mid_inline_code_not_rewritten(self):
        target = self._write("span.md", "Run `x` and `close it in order to stop` now.\n")
        new = "in order to start` now.\n"
        out = hso(self._pre("Edit", {"file_path": target,
                                     "old_string": "in order to stop` now.\n", "new_string": new}))
        self.assertIn(out.get("updatedInput", {}).get("new_string"), (None, new))

    def test_r1_f3_gate_edit_fence_not_rewritten(self):
        target = self._write("fence.md", "Intro.\n")
        out = hso(self._pre("Edit", {"file_path": target, "old_string": "Intro.\n",
                                     "new_string": "````\n```\nrun in order to prior to here\n```\n````\n"}))
        self.assertNotIn("updatedInput", out)

    # F4 an ambiguous contraction is neither denied nor rewritten (STE008 is a warning now);
    # front matter is never rewritten.
    def test_r1_f4_gate_its_been_neither_denied_nor_rewritten(self):
        out = hso(self._pre("Write", {"file_path": self._path("its.md"),
                                      "content": "It's been tested.\n"}))
        self.assertNotEqual(out.get("permissionDecision"), "deny")
        self.assertNotIn("updatedInput", out)

    def test_r1_f4_gate_front_matter_write_not_rewritten(self):
        out = hso(self._pre("Write", {"file_path": self._path("fm.md"),
                                      "content": "---\ntags: [a, in order to b]\n---\n\nText.\n"}))
        self.assertNotIn("updatedInput", out)

    def test_r1_f4_gate_front_matter_edit_not_rewritten(self):
        target = self._write("fm2.md", "---\ntags: [a]\n---\n\nText.\n")
        out = hso(self._pre("Edit", {"file_path": target, "old_string": "tags: [a]\n",
                                     "new_string": "tags: [a, in order to b]\n"}))
        self.assertNotIn("updatedInput", out)

    # F5 a fix that removes text a later edit needs: no rewrite for the chain
    def test_r1_f5_multiedit_chain_no_rewrite(self):
        target = self._write("chain.md", "Old A\n")
        out = hso(self._pre("MultiEdit", {"file_path": target, "edits": [
            {"old_string": "Old A\n", "new_string": "We close it in order to stop.\n"},
            {"old_string": "We close it in order to stop.\n", "new_string": "We close it in order to start.\n"},
        ]}))
        self.assertNotIn("updatedInput", out)

    def test_r1_guard_multiedit_independent_edits_rewritten(self):
        target = self._write("indep.md", "Old A\n\nOld B\n")
        out = hso(self._pre("MultiEdit", {"file_path": target, "edits": [
            {"old_string": "Old A\n", "new_string": "We close it in order to stop.\n"},
            {"old_string": "Old B\n", "new_string": "We close it in order to start.\n"},
        ]}))
        self.assertEqual(out.get("updatedInput"), {"file_path": target, "edits": [
            {"old_string": "Old A\n", "new_string": "We close it to stop.\n"},
            {"old_string": "Old B\n", "new_string": "We close it to start.\n"},
        ]})

    # F6 a fixer over its time limit: plain lint, exit 0, no rewrite. Seam: the builder adds
    # the env var STE_FIXER_LIMIT_S (seconds) to ste_gate.py. Today nothing reads it.
    def test_r1_f6_slow_fixer_falls_back_to_plain_lint(self):
        gate = self._copy_gate("\n\ndef apply_fixes(text):\n    import time\n    time.sleep(4)\n"
                               "    return text.replace(\"in order to\", \"to\"), 0\n")
        with mock.patch.dict(os.environ, {"STE_FIXER_LIMIT_S": "1"}):
            run = run_gate(gate, {"hook_event_name": "PreToolUse", "tool_name": "Write",
                                  "tool_input": {"file_path": self._path("slow.md"),
                                                 "content": "We close it in order to stop.\n"}})
        self.assertEqual(run.returncode, 0, run.stderr)
        out = hso(run)
        self.assertNotIn("updatedInput", out)
        self.assertEqual(out.get("permissionDecision"), "deny")
        self.assertIn("STE011", out["permissionDecisionReason"])


# ------------------------------------------------------------------ review round 2 (PR 367)
# Red pins for review round 2. Names start with the finding number. test_r2_guard_* cases
# pass today and hold a failure class the fix must keep.

# F1: an adverb between the form and a perfect verb. No contraction is fixed now, so the text
# is never rewritten.
ADVERBS = ["never", "always", "also", "now", "only", "not"]


class ReviewRound2FixerTests(unittest.TestCase):
    """apply_fixes on Markdown text, round 2."""

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


class ReviewRound2GateTests(_GateCase):
    """ste_gate.py, round 2."""

    def _gate_copy_env(self):
        env = dict(os.environ)
        env.pop("STE_FIXER_MAX_BYTES", None)
        return env

    # F1 the gate neither rewrites nor denies an adverb-perfect form (STE008 is a warning now)
    def test_r2_f1_gate_its_not_been_neither_denied_nor_rewritten(self):
        out = hso(self._pre("Write", {"file_path": self._path("adv1.md"),
                                      "content": "It's not been tested.\n"}))
        self.assertNotEqual(out.get("permissionDecision"), "deny")
        self.assertNotIn("updatedInput", out)

    def test_r2_f1_gate_theres_always_been_neither_denied_nor_rewritten(self):
        out = hso(self._pre("Write", {"file_path": self._path("adv2.md"),
                                      "content": "There's always been a way.\n"}))
        self.assertNotEqual(out.get("permissionDecision"), "deny")
        self.assertNotIn("updatedInput", out)

    # F6 size ceiling: over STE_FIXER_MAX_BYTES the fixer is skipped and plain lint decides
    def test_r2_f6_size_ceiling_skips_fixer(self):
        with mock.patch.dict(os.environ, {"STE_FIXER_MAX_BYTES": "5"}):
            out = hso(self._pre("Write", {"file_path": self._path("ceil.md"),
                                          "content": "We close it in order to stop.\n"}))
        self.assertNotIn("updatedInput", out)
        self.assertEqual(out.get("permissionDecision"), "deny")
        self.assertIn("STE011", out["permissionDecisionReason"])
        # Default ceiling, env unset: a payload just over 262144 bytes skips the fixer.
        big = "a. " * 87380 + "We close it in order to stop.\n"
        self.assertGreater(len(big.encode("utf-8")), 262144)
        run = run_gate(STE_GATE, {"hook_event_name": "PreToolUse", "tool_name": "Write",
                                  "tool_input": {"file_path": self._path("big.md"), "content": big}},
                       env=self._gate_copy_env())
        self.assertEqual(run.returncode, 0, run.stderr)
        out = hso(run)
        self.assertNotIn("updatedInput", out)
        self.assertEqual(out.get("permissionDecision"), "deny")
        self.assertIn("STE011", out["permissionDecisionReason"])

    def test_r2_guard_under_size_ceiling_still_fixed(self):
        with mock.patch.dict(os.environ, {"STE_FIXER_MAX_BYTES": "100"}):
            out = hso(self._pre("Write", {"file_path": self._path("under.md"),
                                          "content": "We close it in order to stop.\n"}))
        self.assertEqual(out.get("updatedInput", {}).get("content"), "We close it to stop.\n")

    # F7 the deny text quotes the writer's own sentence, not the fixed text
    def test_r2_f7_deny_quotes_writers_sentence(self):
        content = "Prior to this, " + " ".join(["word"] * 40) + ".\n"
        out = hso(self._pre("Write", {"file_path": self._path("quote.md"), "content": content}))
        self.assertEqual(out.get("permissionDecision"), "deny")
        reason = out["permissionDecisionReason"]
        self.assertIn("Prior to", reason)
        self.assertNotIn("Before this", reason)


# ------------------------------------------------------------------ review round 3 (PR 367)
# Blocker: ste_gate.py reads the hook JSON with json.load(sys.stdin), which uses the locale
# codec. A Windows pipe is cp1252 without PYTHONUTF8, so raw UTF-8 bytes turn into mojibake.
# run_gate sends ASCII-escaped JSON, so the existing tests never see raw bytes. These send
# raw UTF-8 bytes into a child with the UTF-8 env vars removed and PYTHONUTF8=0.

class ReviewRound3RawStdinTests(_GateCase):

    def _run_raw(self, obj):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        env = dict(os.environ)
        for key in ("PYTHONUTF8", "PYTHONIOENCODING", "PYTHONLEGACYWINDOWSSTDIO"):
            env.pop(key, None)
        env["PYTHONUTF8"] = "0"
        env["LC_ALL"] = "C"
        return subprocess.run([sys.executable, STE_GATE], input=raw, capture_output=True,
                              timeout=15, env=env)

    # Accented, CJK and emoji text, with CRLF, through the gate's raw stdin: exact bytes.
    def test_r3_blocker_raw_utf8_stdin_write_byte_exact(self):
        content = "We use it prior to café 日本語 😀 here.\r\nWe close it in order to stop.\r\n"
        run = self._run_raw({"hook_event_name": "PreToolUse", "tool_name": "Write",
                             "tool_input": {"file_path": self._path("utf.md"), "content": content}})
        self.assertEqual(run.returncode, 0, run.stderr.decode("utf-8", "replace"))
        out = json.loads(run.stdout.decode("utf-8"))  # the printed JSON reads back as UTF-8
        updated = out.get("hookSpecificOutput", {}).get("updatedInput", {})
        self.assertEqual(updated.get("content"),
                         "We use it before café 日本語 😀 here.\r\nWe close it to stop.\r\n")

    def test_r3_blocker_raw_utf8_stdin_edit_byte_exact(self):
        target = self._path("utf-edit.md")
        with open(target, "wb") as f:
            f.write("Intro café.\r\n".encode("utf-8"))
        run = self._run_raw({"hook_event_name": "PreToolUse", "tool_name": "Edit",
                             "tool_input": {"file_path": target, "old_string": "Intro café.\r\n",
                                            "new_string": "We use it prior to café 日本語 😀 here.\r\n"}})
        self.assertEqual(run.returncode, 0, run.stderr.decode("utf-8", "replace"))
        out = json.loads(run.stdout.decode("utf-8"))
        updated = out.get("hookSpecificOutput", {}).get("updatedInput", {})
        self.assertEqual(updated.get("new_string"),
                         "We use it before café 日本語 😀 here.\r\n")

    def test_r3_guard_invalid_utf8_byte_does_not_crash(self):
        # A lone 0xE9 is not UTF-8. The gate must fall back: exit 0, no traceback, never exit 2.
        raw = (b'{"hook_event_name": "PreToolUse", "tool_name": "Write", "tool_input": '
               b'{"file_path": "bad.md", "content": "We close it in order to stop \xe9 here.\\n"}}')
        env = dict(os.environ)
        for key in ("PYTHONUTF8", "PYTHONIOENCODING", "PYTHONLEGACYWINDOWSSTDIO"):
            env.pop(key, None)
        env["PYTHONUTF8"] = "0"
        env["LC_ALL"] = "C"
        run = subprocess.run([sys.executable, STE_GATE], input=raw, capture_output=True,
                             timeout=15, env=env)
        self.assertNotEqual(run.returncode, 2)
        self.assertEqual(run.returncode, 0, run.stderr.decode("utf-8", "replace"))
        self.assertNotIn(b"Traceback", run.stderr)


if __name__ == "__main__":
    unittest.main()
