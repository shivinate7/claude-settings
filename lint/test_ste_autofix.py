#!/usr/bin/env python3
"""Tests for the STE auto-fix in lint/ste_gate.py (plan section C).

The gate fixes a Markdown write with ste_lint.apply_fixes, returns the fixed text through the
PreToolUse updatedInput, and denies only the errors that remain. UI files are never fixed.

Written test-first. On the current code the gate has no fixer, so the gate cases are red, and
apply_fixes has the unsafe patterns named in the golden set. Safety cases that already pass are
regression guards, not red proof.

    python lint/test_ste_autofix.py -v
"""
import glob
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ste_lint  # noqa: E402
from test_gates import STE_GATE, run_gate  # noqa: E402  (the helper only; no TestCase is collected)

# 29 words: STE001 at the descriptive limit of 25.
LONG = ("The operators on each shift must record every valve position, every pressure reading, "
        "every alarm, and every handover note in the shared log before they leave the site today.")
# 24 words with two contractions: clean now, 26 words once the contractions are fixed.
GROWS_PAST_LIMIT = ("We don't stop the pump until the valve is closed, the gauge reads zero, "
                    "and it's safe for the crew to enter the room.")


def parse(run):
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout) if run.stdout.strip() else {}


def hso(run):
    return parse(run).get("hookSpecificOutput", {})


# ------------------------------------------------------------------ 1. golden grammar set
# (id, before, after). `after` is correct English. Rows whose id ends in `_unsafe_keep` are
# unsafe patterns: the fixer must leave the text UNCHANGED, and the gate still denies on the
# lint error (see GateFixTests test_14 to test_16). Other rows hold the correct fixed text.
# Red today: the rows where apply_fixes output differs from `after`.

GOLDEN = [
    ("g01_latin_start_cap", "E.g. the pump stops.", "For example, the pump stops."),
    ("g02_latin_mid", "Use a tool, e.g. a hammer, for this.", "Use a tool, for example, a hammer, for this."),
    ("g03_latin_end_comma", "Stop the pump, e.g., during a test.", "Stop the pump, for example, during a test."),
    ("g04_latin_in_parens", "Check the valves (e.g. the inlet valve).", "Check the valves (for example, the inlet valve)."),
    ("g05_ie_mid", "Check the valves, i.e. the inlets.", "Check the valves, that is, the inlets."),
    ("g06_etc_sentence_end", "Test the unit at the end, etc.", "Test the unit at the end, and so on."),
    ("g07_etc_mid", "Pumps, valves, etc. must be checked.", "Pumps, valves, and so on must be checked."),
    ("g08_vs_unsafe_keep", "The rule applies to pumps vs. valves.", "The rule applies to pumps vs. valves."),
    ("g09_vs_unsafe_keep", "Compare Option A vs. Option B.", "Compare Option A vs. Option B."),
    ("g10_cf_unsafe_keep", "See cf. section 4 for details.", "See cf. section 4 for details."),
    ("g11_via_unsafe_keep", "Send the report via email.", "Send the report via email."),
    ("g12_et_al_commas", "The team, et al., reviewed the design.", "The team, and others, reviewed the design."),
    ("g13_ad_hoc", "This is an ad hoc fix.", "This is an unplanned fix."),
    ("g14_contraction_mid", "We don't stop the pump.", "We do not stop the pump."),
    ("g15_contraction_start", "Don't stop the pump.", "Do not stop the pump."),
    ("g16_its_mid", "The pump stops when it's full.", "The pump stops when it is full."),
    ("g17_lets", "Let's test the valve.", "Let us test the valve."),
    ("g18_well_end_clause", "Stop the pump, and we'll check it.", "Stop the pump, and we will check it."),
    ("g19_wont", "The pump won't start.", "The pump will not start."),
    ("g20_youd", "You'd like the valve closed.", "You would like the valve closed."),
    ("g21_theyve", "The crews say they've finished.", "The crews say they have finished."),
    ("g22_thed_unsafe_keep", "They'd finished the work.", "They'd finished the work."),
    ("g23_in_order_to", "Close the valve in order to stop the flow.", "Close the valve to stop the flow."),
    ("g24_due_to_start", "Due to the fact that the seal wore, the pump failed.",
     "Because the seal wore, the pump failed."),
    ("g25_in_the_event", "In the event that the alarm sounds, leave the room.", "If the alarm sounds, leave the room."),
    ("g26_noted_delete_unsafe_keep", "It should be noted that the pump runs hot.",
     "It should be noted that the pump runs hot."),
    ("g27_note_delete_unsafe_keep", "Check it. Please note that the door is locked.",
     "Check it. Please note that the door is locked."),
    ("g28_conclusion_delete_unsafe_keep", "In conclusion, the plan works.", "In conclusion, the plan works."),
    ("g29_majority_unsafe_keep", "The majority of the valves are open.", "The majority of the valves are open."),
    ("g30_large_number", "We saw a large number of faults.", "We saw many faults."),
    ("g31_able_to", "We are able to finish today.", "We can finish today."),
    ("g32_first_of_all", "First of all, lock the door.", "First, lock the door."),
    ("g33_make_use_of", "We made use of the new tool.", "We used the new tool."),
    ("g34_decision_about", "Make a decision about the pump.", "Decide about the pump."),
    ("g35_take_into_consideration", "The team will take into consideration the cost.",
     "The team will consider the cost."),
    ("g36_gives_consideration", "The team gives consideration to the cost.", "The team considers the cost."),
    ("g37_makes_use_agreement", "It makes use of the pump.", "It uses the pump."),
    ("g38_provides_support", "This provides support for the goal.", "This supports the goal."),
    ("g39_provide_support_plural", "We provide support for the goal.", "We support the goal."),
    ("g40_comparison_of", "Do a comparison of the two bids.", "Compare the two bids."),
    ("g41_in_terms_of", "The check is good in terms of safety.", "The check is good for safety."),
    ("g42_list_item", "- Test the pump, e.g. the inlet.", "- Test the pump, for example, the inlet."),
    ("g43_table_cell", "| 1 | Close it in order to isolate. |", "| 1 | Close it to isolate. |"),
    ("g44_comma_unsafe_keep", "Stop, in order to test.", "Stop, in order to test."),
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


# ------------------------------------------------------------------ 3a. fixer safety

class FixerSafetyTests(unittest.TestCase):
    """apply_fixes must never change code, quoted text, or the layout of a Markdown file."""

    def test_s01_code_fence_unchanged(self):
        text = ("```python\nx = \"don't e.g. it's\"  # don't\n```\n"
                "```sh\n# don't run e.g. this\n```\n")
        self.assertEqual(ste_lint.apply_fixes(text)[0], text)

    def test_s02_inline_code_unchanged(self):
        text = "Run `don't` and `e.g.` here."
        self.assertEqual(ste_lint.apply_fixes(text)[0], text)

    def test_s03_quoted_text_unchanged(self):
        text = 'The sign says "don\'t enter" now.'
        self.assertEqual(ste_lint.apply_fixes(text)[0], text)

    def test_s04_lone_quote_in_text_does_not_stop_the_fix(self):
        self.assertEqual(ste_lint.apply_fixes('The 5" pipe, don\'t stop.')[0],
                         'The 5" pipe, do not stop.')

    def test_s05_comment_openers_inside_inline_code_unchanged(self):
        text = 'Set `a = "/* x */"` and `b = "# y"`; then don\'t stop.'
        self.assertEqual(ste_lint.apply_fixes(text)[0],
                         'Set `a = "/* x */"` and `b = "# y"`; then do not stop.')

    def test_s06_multiline_template_literal_in_fence_unchanged(self):
        text = ("```js\nconst s = `line one don't\nline two e.g. // keep /* keep */`;\n```\n")
        self.assertEqual(ste_lint.apply_fixes(text)[0], text)

    def test_s07_indented_code_block_unchanged(self):
        text = "    cp  a.txt  don't.txt\n"
        self.assertEqual(ste_lint.apply_fixes(text)[0], text)

    def test_s08_nested_list_indent_kept(self):
        self.assertEqual(ste_lint.apply_fixes("- item\n  - Close the valve in order to stop.\n")[0],
                         "- item\n  - Close the valve to stop.\n")

    def test_s09_trailing_two_space_hard_break_kept(self):
        text = "Line one  \nLine two\n"
        self.assertEqual(ste_lint.apply_fixes(text)[0], text)

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
                                  "content": "We don't stop the pump, e.g. at night.\n"})
        out = hso(run)
        self.assertNotEqual(out.get("permissionDecision"), "deny")
        self.assertEqual(out.get("updatedInput"),
                         {"file_path": target, "content": "We do not stop the pump, for example, at night.\n"})

    def test_02_rewrite_grants_no_allow(self):
        # Docs: "allow" auto-approves, and "defer" makes the hook ignore updatedInput. The docs do
        # not say "allow" is required with updatedInput, so the rewrite must not add one.
        target = self._path("notes.md")
        out = hso(self._pre("Write", {"file_path": target,
                                      "content": "We don't stop the pump, e.g. at night.\n"}))
        self.assertIsNotNone(out.get("updatedInput"), "the rewrite is missing")
        self.assertNotIn(out.get("permissionDecision"), ("allow", "defer"))

    def test_03_fixable_plus_unfixable_denies_with_remaining_only(self):
        target = self._path("mixed.md")
        content = "We don't stop the pump, e.g. at night.\n\n" + LONG + "\n"
        run = self._pre("Write", {"file_path": target, "content": content})
        out = hso(run)
        self.assertEqual(out.get("permissionDecision"), "deny")
        reason = out["permissionDecisionReason"]
        self.assertIn("STE001", reason)
        self.assertIn("operators on each shift", reason, "the sentence is not named")
        self.assertIn("29", reason, "the word count is missing")
        self.assertIn("25", reason, "the limit is missing")
        self.assertIn("split", reason.lower(), "no split point is suggested")
        self.assertNotIn("STE008", reason, "a fixed contraction is still reported")
        self.assertNotIn("STE007", reason, "a fixed abbreviation is still reported")

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
        disk = "We don't stop the pump.\n\nOld block: it's fine.\n"
        target = self._write("blocks.md", disk)
        content = disk + "\nNew block: we'll check it, e.g. daily.\n"
        out = hso(self._pre("Write", {"file_path": target, "content": content}))
        self.assertEqual(out.get("updatedInput", {}).get("content"),
                         disk + "\nNew block: we will check it, for example, daily.\n")

    def test_07_edit_fixes_only_new_string(self):
        disk = "We don't stop the pump.\n\nOld block: it's fine.\n"
        target = self._write("edit.md", disk)
        out = hso(self._pre("Edit", {"file_path": target,
                                     "old_string": "Old block: it's fine.\n",
                                     "new_string": "New block: we'll check it, e.g. daily.\n"}))
        self.assertEqual(out.get("updatedInput"), {
            "file_path": target,
            "old_string": "Old block: it's fine.\n",
            "new_string": "New block: we will check it, for example, daily.\n",
        })

    def test_08_edit_not_on_disk_lints_whole_text_and_fixes_it(self):
        target = self._write("unreplayable.md", "Clean text.\n")
        out = hso(self._pre("Edit", {"file_path": target,
                                     "old_string": "Nowhere on disk.\n",
                                     "new_string": "We don't stop it, e.g. at night.\n"}))
        self.assertEqual(out.get("updatedInput"), {
            "file_path": target,
            "old_string": "Nowhere on disk.\n",
            "new_string": "We do not stop it, for example, at night.\n",
        })

    def test_09_edit_not_on_disk_remaining_error_denied(self):
        target = self._write("unreplayable2.md", "Clean text.\n")
        out = hso(self._pre("Edit", {"file_path": target,
                                     "old_string": "Nowhere on disk.\n",
                                     "new_string": LONG + "\n"}))
        self.assertEqual(out.get("permissionDecision"), "deny")
        self.assertIn("STE001", out["permissionDecisionReason"])

    def test_10_output_names_the_fixed_code_without_a_deny(self):
        # One line that names what was fixed, and no deny. Today the gate denies, which also
        # names STE008, so the deny check is what makes this red.
        run = self._pre("Write", {"file_path": self._path("named.md"),
                                  "content": "We don't stop the pump.\n"})
        self.assertNotEqual(hso(run).get("permissionDecision"), "deny")
        self.assertIn("STE008", run.stdout)

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
                                             "content": "We don't stop the pump.\n"}})
        self.assertNotEqual(run.returncode, 2)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(os.path.exists(marker), "the fixer never ran")
        out = hso(run)
        self.assertEqual(out.get("permissionDecision"), "deny")
        self.assertIn("STE008", out["permissionDecisionReason"])
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
                                  "content": "```sh\nrun don't here\n```\n"})
        self.assertEqual(run.stdout.strip(), "")

    def test_13_fix_then_lint_catches_growth_past_the_limit(self):
        # Clean before the fix (24 words). Lint-before-fix would miss this. Fixed it is 26 words.
        out = hso(self._pre("Write", {"file_path": self._path("grow.md"),
                                      "content": GROWS_PAST_LIMIT + "\n"}))
        self.assertEqual(out.get("permissionDecision"), "deny")
        reason = out["permissionDecisionReason"]
        self.assertIn("STE001", reason)
        self.assertNotIn("STE008", reason)

    # Unsafe patterns (ruling 2): the fixer leaves the text unchanged, so the gate must not
    # rewrite it, and must still deny on the lint error.

    def test_14_unsafe_latin_vs_cf_via_denied_not_rewritten(self):
        content = "Compare Option A vs. Option B.\n\nSee cf. section 4.\n\nSend it via email.\n"
        out = hso(self._pre("Write", {"file_path": self._path("latin.md"), "content": content}))
        self.assertEqual(out.get("permissionDecision"), "deny")
        self.assertIn("STE007", out["permissionDecisionReason"])
        self.assertNotIn("updatedInput", out)

    def test_15_unsafe_would_denied_not_rewritten(self):
        out = hso(self._pre("Write", {"file_path": self._path("would.md"),
                                      "content": "They'd finished the work.\n"}))
        self.assertEqual(out.get("permissionDecision"), "deny")
        self.assertIn("STE008", out["permissionDecisionReason"])
        self.assertNotIn("updatedInput", out)

    def test_16_unsafe_deletions_and_majority_denied_not_rewritten(self):
        content = ("In conclusion, the plan works.\n\nThe majority of the valves are open.\n\n"
                   "We will check it.\n")
        out = hso(self._pre("Write", {"file_path": self._path("bloat.md"), "content": content}))
        self.assertEqual(out.get("permissionDecision"), "deny")
        self.assertIn("STE011", out["permissionDecisionReason"])
        self.assertNotIn("updatedInput", out)


# ------------------------------------------------------------------ UI files: no rewrite

class UiFileTests(_GateCase):
    """UI files keep today's behaviour: the gate denies, and never rewrites the input."""

    def test_u01_tsx_contraction_not_rewritten(self):
        # STE008 does not apply to UI copy, so this is clean today.
        run = self._pre("Write", {"file_path": self._path("Page.tsx"),
                                  "content": "export const P = () => <p>Don't</p>;\n"})
        self.assertNotIn("updatedInput", hso(run))

    def test_u02_tsx_latin_denied_and_not_rewritten(self):
        run = self._pre("Write", {"file_path": self._path("Help.tsx"),
                                  "content": "export const H = () => <p>Use it, e.g. daily.</p>;\n"})
        out = hso(run)
        self.assertEqual(out.get("permissionDecision"), "deny")
        self.assertNotIn("updatedInput", out)


if __name__ == "__main__":
    unittest.main()
