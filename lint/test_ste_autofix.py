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
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

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


# ------------------------------------------------------------------ review round 1 (PR 367)
# Red pins for the reviewer's findings. Each name starts with its finding number.
# test_r1_guard_* cases pass today: they hold a failure class the fix must not break.

class ReviewRound1FixerTests(unittest.TestCase):
    """apply_fixes on Markdown text: links, quotes, fences, front matter, English."""

    # F1 links keep their URL
    def test_r1_f1_link_url_kept(self):
        inp = "See [the guide](https://a.example/g) and it's done.\n"
        out = ste_lint.apply_fixes(inp)[0]
        self.assertIn("https://a.example/g", out)
        self.assertIn(out, (inp, "See [the guide](https://a.example/g) and it is done.\n"))

    def test_r1_f1_image_url_kept(self):
        inp = "See ![alt](u) and it's done.\n"
        out = ste_lint.apply_fixes(inp)[0]
        self.assertIn("![alt](u)", out)
        self.assertIn(out, (inp, "See ![alt](u) and it is done.\n"))

    def test_r1_guard_reference_link_kept(self):
        inp = "See [a][b] and it's done.\n\n[b]: https://x.y\n"
        out = ste_lint.apply_fixes(inp)[0]
        self.assertIn("[a][b]", out)
        self.assertIn("[b]: https://x.y", out)

    def test_r1_guard_autolink_kept(self):
        out = ste_lint.apply_fixes("See <https://x.y> and it's done.\n")[0]
        self.assertIn("<https://x.y>", out)

    # F2 quoted code and quoted links survive
    def test_r1_f2_quoted_code_kept(self):
        inp = 'He said "run `x`" and don\'t stop.\n'
        out = ste_lint.apply_fixes(inp)[0]
        self.assertIn("run `x`", out)
        self.assertIn(out, (inp, 'He said "run `x`" and do not stop.\n'))

    def test_r1_f2_quoted_link_url_kept(self):
        inp = '"[guide](https://a.example/g)" and don\'t stop.\n'
        out = ste_lint.apply_fixes(inp)[0]
        self.assertIn("https://a.example/g", out)
        self.assertIn(out, (inp, '"[guide](https://a.example/g)" and do not stop.\n'))

    # F3a fence content is never rewritten
    def test_r1_f3a_four_backtick_fence_unchanged(self):
        inp = "````\n```\nrun don't e.g. here\n```\n````\n"
        self.assertEqual(ste_lint.apply_fixes(inp)[0], inp)

    def test_r1_f3a_tilde_fence_unchanged(self):
        inp = "~~~\n```\nrun don't e.g. here\n```\n~~~\n"
        self.assertEqual(ste_lint.apply_fixes(inp)[0], inp)

    # F4 front matter, and fixes that break English
    def test_r1_f4_front_matter_unchanged(self):
        inp = "---\ntags: [a, e.g. b]\n---\n\nText.\n"
        self.assertEqual(ste_lint.apply_fixes(inp)[0], inp)

    def test_r1_f4_its_been_unchanged(self):
        # "it is been" is wrong English: 's here is has, not is.
        self.assertEqual(ste_lint.apply_fixes("It's been tested.\n")[0], "It's been tested.\n")

    def test_r1_f4_there_is_two_unchanged(self):
        self.assertEqual(ste_lint.apply_fixes("There's two pumps.\n")[0], "There's two pumps.\n")

    def test_r1_f4_per_se_unchanged(self):
        self.assertEqual(ste_lint.apply_fixes("This is a per se violation.\n")[0],
                         "This is a per se violation.\n")

    def test_r1_f4_paren_eg_no_stray_comma(self):
        out = ste_lint.apply_fixes("Check it (e.g.)\n")[0]
        self.assertIn(out, ("Check it (e.g.)\n", "Check it (for example)\n"))

    def test_r1_f4_final_eg_keeps_period(self):
        out = ste_lint.apply_fixes("Use tools, e.g.\n")[0]
        self.assertIn(out, ("Use tools, e.g.\n", "Use tools, for example.\n"))

    # Failure-class guards: CRLF, multi-byte text, lone quote in HTML text
    def test_r1_guard_crlf_kept(self):
        self.assertEqual(ste_lint.apply_fixes("We don't stop.\r\nWe don't stop.\r\n")[0],
                         "We do not stop.\r\nWe do not stop.\r\n")

    def test_r1_guard_multibyte_kept(self):
        self.assertEqual(ste_lint.apply_fixes("Café — don't stop, e.g. naïve.\n")[0],
                         "Café — do not stop, for example, naïve.\n")

    def test_r1_guard_jsx_text_in_md_kept(self):
        self.assertEqual(ste_lint.apply_fixes("<p>Don't</p>\n")[0], "<p>Do not</p>\n")


# F4: an ambiguous 's (is or has) or 'd (would or had) stays unchanged. Each form gets its own
# test, in an ambiguous sentence. Clear forms stay fixable: g16 (it's full), g20 (You'd like).
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
        target = self._write("span.md", "Run `x` and `don't e.g. stop` now.\n")
        new = "e.g. stop` now.\n"
        out = hso(self._pre("Edit", {"file_path": target,
                                     "old_string": "don't e.g. stop` now.\n", "new_string": new}))
        self.assertIn(out.get("updatedInput", {}).get("new_string"), (None, new))

    def test_r1_f3_gate_edit_fence_not_rewritten(self):
        target = self._write("fence.md", "Intro.\n")
        out = hso(self._pre("Edit", {"file_path": target, "old_string": "Intro.\n",
                                     "new_string": "````\n```\nrun don't e.g. here\n```\n````\n"}))
        self.assertNotIn("updatedInput", out)

    # F4 an ambiguous contraction is denied, not rewritten; front matter is never rewritten
    def test_r1_f4_gate_its_been_denied_not_rewritten(self):
        out = hso(self._pre("Write", {"file_path": self._path("its.md"),
                                      "content": "It's been tested.\n"}))
        self.assertEqual(out.get("permissionDecision"), "deny")
        self.assertIn("STE008", out["permissionDecisionReason"])
        self.assertNotIn("updatedInput", out)

    def test_r1_f4_gate_front_matter_write_not_rewritten(self):
        out = hso(self._pre("Write", {"file_path": self._path("fm.md"),
                                      "content": "---\ntags: [a, e.g. b]\n---\n\nText.\n"}))
        self.assertNotIn("updatedInput", out)

    def test_r1_f4_gate_front_matter_edit_not_rewritten(self):
        target = self._write("fm2.md", "---\ntags: [a]\n---\n\nText.\n")
        out = hso(self._pre("Edit", {"file_path": target, "old_string": "tags: [a]\n",
                                     "new_string": "tags: [a, e.g. b]\n"}))
        self.assertNotIn("updatedInput", out)

    # F5 a fix that removes text a later edit needs: no rewrite for the chain
    def test_r1_f5_multiedit_chain_no_rewrite(self):
        target = self._write("chain.md", "Old A\n")
        out = hso(self._pre("MultiEdit", {"file_path": target, "edits": [
            {"old_string": "Old A\n", "new_string": "We don't stop it.\n"},
            {"old_string": "We don't stop it.\n", "new_string": "We won't stop it.\n"},
        ]}))
        self.assertNotIn("updatedInput", out)

    def test_r1_guard_multiedit_independent_edits_rewritten(self):
        target = self._write("indep.md", "Old A\n\nOld B\n")
        out = hso(self._pre("MultiEdit", {"file_path": target, "edits": [
            {"old_string": "Old A\n", "new_string": "We don't stop it.\n"},
            {"old_string": "Old B\n", "new_string": "We won't stop it.\n"},
        ]}))
        self.assertEqual(out.get("updatedInput"), {"file_path": target, "edits": [
            {"old_string": "Old A\n", "new_string": "We do not stop it.\n"},
            {"old_string": "Old B\n", "new_string": "We will not stop it.\n"},
        ]})

    # F6 a fixer over its time limit: plain lint, exit 0, no rewrite. Seam: the builder adds
    # the env var STE_FIXER_LIMIT_S (seconds) to ste_gate.py. Today nothing reads it.
    def test_r1_f6_slow_fixer_falls_back_to_plain_lint(self):
        gate = self._copy_gate("\n\ndef apply_fixes(text):\n    import time\n    time.sleep(4)\n"
                               "    return text.replace(\"don't\", \"do not\"), 0\n")
        with mock.patch.dict(os.environ, {"STE_FIXER_LIMIT_S": "1"}):
            run = run_gate(gate, {"hook_event_name": "PreToolUse", "tool_name": "Write",
                                  "tool_input": {"file_path": self._path("slow.md"),
                                                 "content": "We don't stop the pump.\n"}})
        self.assertEqual(run.returncode, 0, run.stderr)
        out = hso(run)
        self.assertNotIn("updatedInput", out)
        self.assertEqual(out.get("permissionDecision"), "deny")
        self.assertIn("STE008", out["permissionDecisionReason"])

    # Failure-class guard: multi-byte text through the JSON stdin and stdout of the gate
    def test_r1_guard_multibyte_gate_write(self):
        out = hso(self._pre("Write", {"file_path": self._path("mb.md"),
                                      "content": "Café — don't stop, e.g. naïve.\n"}))
        self.assertEqual(out.get("updatedInput", {}).get("content"),
                         "Café — do not stop, for example, naïve.\n")


# ------------------------------------------------------------------ review round 2 (PR 367)
# Red pins for review round 2. Names start with the finding number. test_r2_guard_* cases
# pass today and hold a failure class the fix must keep.

# F1: an adverb between 's or 'd and a perfect verb. "is" never follows "been" or "had".
ADVERBS = ["never", "always", "also", "just", "still", "now", "only", "not"]


class ReviewRound2FixerTests(unittest.TestCase):
    """apply_fixes on Markdown text, round 2."""

    # F2 code in a blockquote fence and in a raw HTML block stays unchanged
    def test_r2_f2_blockquote_fence_unchanged(self):
        inp = "> ```\n> e.g. the code\n> ```\n"
        self.assertEqual(ste_lint.apply_fixes(inp)[0], inp)

    def test_r2_f2_pre_block_unchanged(self):
        inp = "<pre>\ne.g. x\n</pre>\n"
        self.assertEqual(ste_lint.apply_fixes(inp)[0], inp)

    def test_r2_guard_list_item_fence_two_spaces_unchanged(self):
        inp = "- item\n\n  ```\n  e.g. the code\n  ```\n"
        self.assertEqual(ste_lint.apply_fixes(inp)[0], inp)

    def test_r2_guard_list_item_fence_four_spaces_unchanged(self):
        inp = "1. Step one:\n\n    ```sh\n    e.g. run this\n    ```\n"
        self.assertEqual(ste_lint.apply_fixes(inp)[0], inp)

    # F3 et al. keeps its period; N.B. never gives "Note:,"
    def test_r2_f3_et_al_keeps_period(self):
        inp = "The paper is by Smith et al. The next section is done.\n"
        out = ste_lint.apply_fixes(inp)[0]
        self.assertIn(out, (inp, "The paper is by Smith and others. The next section is done.\n"))

    def test_r2_f3_nb_no_note_colon(self):
        inp = "N.B., the file is locked.\n"
        out = ste_lint.apply_fixes(inp)[0]
        self.assertNotIn("Note:,", out)
        self.assertIn(out, (inp, "Note, the file is locked.\n"))

    # F4 a shortcut reference label and its definition stay in sync
    def test_r2_f4_shortcut_label_in_sync(self):
        inp = "See [it's here] now.\n\n[it's here]: notes.md\n"
        out = ste_lint.apply_fixes(inp)[0]
        self.assertIn(out, (inp, "See [it is here] now.\n\n[it is here]: notes.md\n"))

    # F5 CRLF: every line keeps \r\n, no mixed endings
    def test_r2_f5_crlf_no_mixed_endings(self):
        inp = "Use tools, e.g.\r\nWe don't stop.\r\n"
        out = ste_lint.apply_fixes(inp)[0]
        self.assertIn(out, (inp, "Use tools, for example.\r\nWe do not stop.\r\n"))

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

    # F1 the gate does not rewrite an adverb-perfect form; it still denies
    def test_r2_f1_gate_its_not_been_denied_not_rewritten(self):
        out = hso(self._pre("Write", {"file_path": self._path("adv1.md"),
                                      "content": "It's not been tested.\n"}))
        self.assertEqual(out.get("permissionDecision"), "deny")
        self.assertNotIn("updatedInput", out)

    def test_r2_f1_gate_theres_always_been_denied_not_rewritten(self):
        out = hso(self._pre("Write", {"file_path": self._path("adv2.md"),
                                      "content": "There's always been a way.\n"}))
        self.assertEqual(out.get("permissionDecision"), "deny")
        self.assertNotIn("updatedInput", out)

    # F5 the gate's Write path keeps CRLF endings on every line
    def test_r2_f5_gate_crlf_write_no_mixed_endings(self):
        inp = "Use tools, e.g.\r\nWe don't stop.\r\n"
        out = hso(self._pre("Write", {"file_path": self._path("crlf.md"), "content": inp}))
        content = out.get("updatedInput", {}).get("content", inp)
        self.assertIn(content, (inp, "Use tools, for example.\r\nWe do not stop.\r\n"))

    # F6 size ceiling: over STE_FIXER_MAX_BYTES the fixer is skipped and plain lint decides
    def test_r2_f6_size_ceiling_skips_fixer(self):
        with mock.patch.dict(os.environ, {"STE_FIXER_MAX_BYTES": "5"}):
            out = hso(self._pre("Write", {"file_path": self._path("ceil.md"),
                                          "content": "We don't stop.\n"}))
        self.assertNotIn("updatedInput", out)
        self.assertEqual(out.get("permissionDecision"), "deny")
        self.assertIn("STE008", out["permissionDecisionReason"])

    def test_r2_guard_under_size_ceiling_still_fixed(self):
        with mock.patch.dict(os.environ, {"STE_FIXER_MAX_BYTES": "100"}):
            out = hso(self._pre("Write", {"file_path": self._path("under.md"),
                                          "content": "We don't stop.\n"}))
        self.assertEqual(out.get("updatedInput", {}).get("content"), "We do not stop.\n")

    def test_r2_f6_gate_1p5mb_within_budget(self):
        # 1.5 MB of "a. " with one fixable contraction at the end: over the 256 KB default, so
        # the fixer is skipped and plain lint decides: deny on STE008, no rewrite, under 9 s.
        content = "a. " * 500000 + "We don't stop.\n"
        target = self._path("big.md")
        start = time.perf_counter()
        run = run_gate(STE_GATE, {"hook_event_name": "PreToolUse", "tool_name": "Write",
                                  "tool_input": {"file_path": target, "content": content}},
                       env=self._gate_copy_env())
        elapsed = time.perf_counter() - start
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertLess(elapsed, 9.0)
        out = hso(run)
        self.assertNotIn("updatedInput", out)
        self.assertEqual(out.get("permissionDecision"), "deny")
        self.assertIn("STE008", out["permissionDecisionReason"])

    # F7 the deny text quotes the writer's own sentence, not the fixed text
    def test_r2_f7_deny_quotes_writers_sentence(self):
        content = "Use tools, e.g. " + " ".join(["word"] * 40) + ".\n"
        out = hso(self._pre("Write", {"file_path": self._path("quote.md"), "content": content}))
        self.assertEqual(out.get("permissionDecision"), "deny")
        reason = out["permissionDecisionReason"]
        self.assertIn("e.g.", reason)
        self.assertNotIn("for example", reason)


if __name__ == "__main__":
    unittest.main()
