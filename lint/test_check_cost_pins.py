#!/usr/bin/env python3
"""Cases for lint/check_cost_pins.py. Standard library only.

    python3 lint/test_check_cost_pins.py

A decision record's Cost sentence may name a file only when a test pins it. The check reads
docs/decisions/*.md under --root and prints one line per unpinned file token:
`<record path>:<line>: <file token> named in a Cost sentence with no pin`.
A count claim in a Cost sentence prints `<record path>:<line>: count in a Cost sentence with no reader`.
The file cases compare file rows only; a count case passes counts=True to compare count rows too.

Each case builds a temp tree holding the records and test files it reads, then runs the real script
with --root on that tree. The corpus case runs it on this repo with no --root. COST_PINS_UNDER_TEST
overrides the module path, for a mutant copy.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
MODULE = os.environ.get("COST_PINS_UNDER_TEST") or os.path.join(HERE, "check_cost_pins.py")

DEC = "docs/decisions/"
NAMED = " named in a Cost sentence with no pin"
UNBALANCED = "unbalanced backtick in a Cost paragraph"
# The count rule's row. The file cases leave it out, so a count the rule flags fails only the count cases.
COUNT = "count in a Cost sentence with no reader"
# A plain count beside a cost noun, which the rule flags. Each count case prints it, so a case whose other
# sentences pass still shows that the rule ran on its record.
CONTROL = "- **Cost:** two `simctl list` reads per call.\n"
CONTROL_NEEDLE = "- **Cost:** two `simctl list`"
FINDING = re.compile(r"^(?P<path>.+\.md):(?P<line>[0-9]+): (?P<what>.+)$")
RUN_FOLDER = None  # made in setUpModule, so an import leaks no folder


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def record_of(path):
    """The record's path from its docs folder on, with / separators, so an absolute path and a relative one compare alike."""
    path = path.replace("\\", "/")
    cut = max(path.rfind("docs/decisions/"), path.rfind("docs/debts/"))
    return path[cut:] if cut >= 0 else path


def findings(out, counts=False):
    """(record, line, what) for each finding line in the output, in the order printed. `what` is the file token,
    the count message, or the unbalanced-backtick message, so a case compares one value. Count rows are left out
    unless `counts` is true."""
    rows = []
    for text in out.splitlines():
        m = FINDING.match(text.strip())
        if m:
            what = m.group("what")
            if what.endswith(NAMED):
                what = what[:-len(NAMED)]
            if what == COUNT and not counts:
                continue
            rows.append((record_of(m.group("path")), int(m.group("line")), what))
    return rows


def lineno(text, needle):
    """The 1-based line of `text` that holds `needle`. The needle must hold on one line only."""
    hits = [n for n, line in enumerate(text.splitlines(), 1) if needle in line]
    if len(hits) != 1:
        raise ValueError("needle %r holds on lines %r" % (needle, hits))
    return hits[0]


def row(name, text, needle, token):
    """The finding that record `name`, with `text`, must print for `token`, on the line holding `needle`."""
    return (DEC + name, lineno(text, needle), token)


def count_row(name, text, needle):
    """The count finding that record `name`, with `text`, must print on the line holding `needle`."""
    return row(name, text, needle, COUNT)


class CostPinTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(MODULE), "module absent: lint/check_cost_pins.py")
        self.tree = tempfile.mkdtemp(prefix="ccp_", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.tree, True)

    def put(self, rel, text):
        path = os.path.join(self.tree, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def assert_exists(self, *rels):
        """Each test file the case names is on disk, so a miss below is the pin check, not a missing file."""
        for rel in rels:
            self.assertTrue(os.path.isfile(os.path.join(self.tree, *rel.split("/"))), rel)

    def decide(self, name, body):
        """Write a decision record: a title, a status line, then the body. Returns the whole text."""
        text = "# Record\n\nStatus: accepted.\n\n" + body
        self.put(DEC + name, text)
        return text

    def lint(self):
        r = subprocess.run([sys.executable, MODULE, "--root", self.tree], cwd=self.tree,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        return r.returncode, r.stdout + r.stderr

    def assert_clean(self):
        rc, out = self.lint()
        self.assertEqual(rc, 0, out)
        self.assertEqual(findings(out, counts=True), [], out)

    def assert_found(self, expected, counts=False):
        rc, out = self.lint()
        self.assertEqual(rc, 1, "exit 1 expected with findings %r; got exit %d:\n%s" % (expected, rc, out))
        self.assertEqual(sorted(findings(out, counts)), sorted(expected), out)

    def assert_has(self, expected, counts=False):
        """Each expected finding is printed. Other findings may print too: the case names only its own cause."""
        rc, out = self.lint()
        self.assertEqual(rc, 1, "exit 1 expected with findings %r; got exit %d:\n%s" % (expected, rc, out))
        for wanted in expected:
            self.assertIn(wanted, findings(out, counts), out)

    def test_founding_incident_is_flagged(self):
        # The Proof sentence names a test that holds layout.json. It is another sentence, so it pins nothing here.
        text = self.decide("layout-read.md",
                           "- **Cost:** It also reads `lint/layout.json` once for the named repo. "
                           "Proof: cases in `hooks/test_guard.py`.\n")
        self.put("hooks/test_guard.py", "# guard cases\n\nlayout.json is read by the first case.\n")
        self.assert_found([row("layout-read.md", text, "- **Cost:**", "lint/layout.json")])

    def test_founding_fix_passes(self):
        self.decide("layout-read.md",
                    "- **Cost:** It also opens `lint/layout.json` on every call (no test counts the opens). "
                    "Proof: cases in `hooks/test_guard.py`.\n")
        self.put("hooks/test_guard.py", "# guard cases\n\nlayout.json is read by the first case.\n")
        self.assert_clean()

    def test_same_sentence_test_pins_the_token(self):
        self.decide("state-x.md", "- **Cost:** Reads `state/x.json`; `lint/test_x.py` proves it.\n")
        self.put("lint/test_x.py", "# x cases\n\nreads x.json\n")
        self.assert_clean()

    def test_named_test_without_the_name_does_not_pin(self):
        text = self.decide("state-x.md", "- **Cost:** Reads `state/x.json`; `lint/test_x.py` proves it.\n")
        self.put("lint/test_x.py", "# x cases\n\nreads something else\n")
        self.assert_found([row("state-x.md", text, "- **Cost:**", "state/x.json")])

    def test_named_test_missing_on_disk_does_not_pin(self):
        text = self.decide("state-x.md", "- **Cost:** Reads `state/x.json`; `lint/test_x.py` proves it.\n")
        self.assert_found([row("state-x.md", text, "- **Cost:**", "state/x.json")])

    def test_placeholder_is_pinned_by_its_literal_parent(self):
        self.decide("answers.md", "- **Cost:** Writes `answers/<id>.json`; `hooks/test_writes.py` proves it.\n")
        self.put("hooks/test_writes.py", "# writes\n\nThe answers folder gets one file per id.\n")
        self.assert_clean()

    def test_placeholder_is_unpinned_when_the_test_lacks_the_parent(self):
        text = self.decide("answers.md", "- **Cost:** Writes `answers/<id>.json`; `hooks/test_writes.py` proves it.\n")
        self.put("hooks/test_writes.py", "# writes\n\nOne file per id.\n")
        self.assert_found([row("answers.md", text, "- **Cost:**", "answers/<id>.json")])

    def test_non_files_are_not_named(self):
        # state/real.json is unpinned in the same paragraph, so a clean result shows the paragraph was read.
        text = self.decide("plain.md",
                           "- **Cost:** Each run calls `actions/runs` once. It names `merge-checks` only. "
                           "It reads `hooks/test_guard.py`, `lint/test_x.mjs`, `lint/test_ios_ship.sh` "
                           "and `install.test.ps1`. It also reads `state/real.json` once.\n")
        self.assert_found([row("plain.md", text, "- **Cost:**", "state/real.json")])

    def test_prefixed_and_bare_tokens_are_files(self):
        text = self.decide("forms.md",
                           "- **Cost:** It runs `~/bin/tool` once. It reads `.git/HEAD` once. "
                           "It writes `<config dir>/cc-behavior.json` once. It reads `settings.json` once.\n")
        self.assert_found([row("forms.md", text, "- **Cost:**", token) for token in
                           ("~/bin/tool", ".git/HEAD", "<config dir>/cc-behavior.json", "settings.json")])

    def test_backticks_hold_the_sentence(self):
        # Paragraph one: the test in the next sentence holds the name, and still does not pin it.
        # Paragraph two: ". " inside backticks does not end the sentence that holds the pin.
        text = self.decide("dots.md",
                           "- **Cost:** It reads `state/a.b.json`. Proof: `lint/test_a.py`.\n\n"
                           "- **Cost:** It reads `state/x.json` for each `e.g. sample`; `lint/test_x.py` proves it. "
                           "Don't reread it.\n")
        self.put("lint/test_a.py", "# a cases\n\na.b.json is read\n")
        self.put("lint/test_x.py", "# x cases\n\nx.json is read\n")
        self.assert_found([row("dots.md", text, "state/a.b.json", "state/a.b.json")])

    def test_exemption_words_pin_only_their_own_sentence(self):
        text = self.decide("exempt.md",
                           "- **Cost:** It reads `state/p1.json` once (not pinned).\n"
                           "- **Cost:** It reads `state/p2.json` once (unpinned).\n"
                           "- **Cost:** It reads `state/p3.json` once (Unmeasured).\n"
                           "- **Cost:** It reads `state/p4.json` once (NO TEST counts the reads).\n"
                           "- **Cost:** It reads `state/p5.json` once. Unmeasured for now.\n")
        self.assert_found([row("exempt.md", text, "state/p5.json", "state/p5.json")])

    def test_paragraph_runs_over_wrapped_lines(self):
        text = self.decide("wrap.md",
                           "- **Cost:** It reads `state/w.json` once.\n"
                           "  It also reads `state/v.json` on each run.\n")
        self.assert_found([row("wrap.md", text, "state/w.json", "state/w.json"),
                           row("wrap.md", text, "state/v.json", "state/v.json")])

    def test_paragraph_ends_at_a_blank_line_a_bullet_or_a_heading(self):
        text = self.decide("ends.md",
                           "- **Cost:** It reads `state/w.json` once.\n"
                           "\n"
                           "`state/y.json` is read by the install step.\n"
                           "- **Cost:** It reads `state/u.json` once.\n"
                           "- Writes `state/z.json` on each run.\n"
                           "- **Cost:** It reads `state/t.json` once.\n"
                           "## Next steps\n"
                           "`state/h.json` is read by the next step.\n")
        self.assert_found([row("ends.md", text, "state/w.json", "state/w.json"),
                           row("ends.md", text, "state/u.json", "state/u.json"),
                           row("ends.md", text, "state/t.json", "state/t.json")])

    def test_each_cost_form_starts_a_paragraph(self):
        text = self.decide("forms-cost.md",
                           "- Cost: It reads `state/f1.json` once.\n"
                           "\n"
                           "**Cost:** It reads `state/f2.json` once.\n"
                           "\n"
                           "    - Cost: It reads `state/f3.json` once.\n"
                           "\n"
                           "* **Cost:** It reads `state/f4.json` once.\n"
                           "\n"
                           "- **Cost.** It reads `state/f5.json` once.\n"
                           "\n"
                           "Cost. It reads `state/f6.json` once.\n"
                           "\n"
                           "Costs: It reads `state/c.json` once.\n")
        self.assert_found([row("forms-cost.md", text, "state/f%d.json" % n, "state/f%d.json" % n)
                           for n in (1, 2, 3, 4, 5, 6)])

    def test_cost_lines_under_debts_are_ignored(self):
        line = "- **Cost:** It reads `state/d.json` once.\n"
        text = self.decide("control.md", line)  # control: the same line under decisions is flagged
        self.assert_found([row("control.md", text, "state/d.json", "state/d.json")])
        os.remove(os.path.join(self.tree, *(DEC + "control.md").split("/")))
        self.put("docs/debts/some-debt.md", "# Debt\n\n" + line)
        self.assert_clean()

    def test_cost_word_before_a_non_letter_starts_a_paragraph(self):
        # Costs and Costly are a word that only starts with Cost: they start no paragraph.
        text = self.decide("cost-words.md",
                           "- Cost, per call: reads `state/c1.json` once.\n"
                           "\n"
                           "Cost (per run): reads `state/c2.json` once.\n"
                           "\n"
                           "**Cost**: reads `state/c3.json` once.\n"
                           "\n"
                           "Cost of a run: reads `state/c4.json` once.\n"
                           "\n"
                           "Costs: reads `state/c5.json` once.\n"
                           "\n"
                           "Costly: reads `state/c6.json` once.\n")
        self.assert_found([row("cost-words.md", text, "state/c%d.json" % n, "state/c%d.json" % n)
                           for n in (1, 2, 3, 4)])

    def test_odd_backticks_in_a_cost_paragraph_are_a_finding_on_its_first_line(self):
        text = self.decide("ticks.md",
                           "- **Cost:** It reads `state/x.json once. It also reads `state/y.json` once.\n")
        self.assert_has([row("ticks.md", text, "- **Cost:**", UNBALANCED)])

    def test_nested_bullet_stays_and_a_bullet_at_the_same_or_lesser_indent_ends_the_paragraph(self):
        text = self.decide("nest.md",
                           "- **Cost:** It reads `state/n1.json` once.\n"
                           "  - It also reads `state/n2.json` each run.\n"
                           "- Writes `state/n3.json` on each run.\n"
                           "\n"
                           "- Parent item\n"
                           "  - **Cost:** It reads `state/m1.json` once.\n"
                           "    - Nested under the cost: reads `state/m2.json` each run.\n"
                           "- Lesser bullet: reads `state/m3.json` each run.\n")
        self.assert_found([row("nest.md", text, "state/n1.json", "state/n1.json"),
                           row("nest.md", text, "state/n2.json", "state/n2.json"),
                           row("nest.md", text, "state/m1.json", "state/m1.json"),
                           row("nest.md", text, "state/m2.json", "state/m2.json")])

    def test_sentence_ends_at_dot_paren_dot_star_and_dot_quote(self):
        # Each sentence ends at its closing mark, so the exemption words in the next sentence pin nothing.
        text = self.decide("ends-sentence.md",
                           "- **Cost:** It reads `state/q1.json` (once.) Unmeasured for now.\n"
                           "- **Cost:** **It reads `state/q2.json` once.** Unmeasured for now.\n"
                           "- **Cost:** *It reads `state/q3.json` once.* Unmeasured for now.\n"
                           "- **Cost:** It says \"It reads `state/q4.json` once.\" Unmeasured for now.\n")
        self.assert_found([row("ends-sentence.md", text, "state/q%d.json" % n, "state/q%d.json" % n)
                           for n in (1, 2, 3, 4)])

    def test_pin_name_must_match_whole(self):
        # box.json holds x.json as a substring, and HEADER holds HEAD: neither is a pin for the whole name.
        text = self.decide("whole.md",
                           "- **Cost:** Reads `state/x.json`; `lint/test_box.py` proves it.\n"
                           "- **Cost:** Reads `.git/HEAD`; `lint/test_head.py` proves it.\n"
                           "- **Cost:** Reads `state/z.json`; `lint/test_z.py` proves it.\n")
        self.put("lint/test_box.py", "# box cases\n\nbox.json is read\n")
        self.put("lint/test_head.py", "# head cases\n\nHEADER is read\n")
        self.put("lint/test_z.py", "# z cases\n\nreads z.json once\n")
        self.assert_found([row("whole.md", text, "state/x.json", "state/x.json"),
                           row("whole.md", text, ".git/HEAD", ".git/HEAD")])

    def test_extensions_match_any_case_and_a_line_suffix_is_stripped(self):
        text = self.decide("case.md",
                           "- **Cost:** It reads `state/UP.JSON` once.\n"
                           "- **Cost:** It reads `hooks/guard.py:42` once.\n")
        self.assert_found([row("case.md", text, "state/UP.JSON", "state/UP.JSON"),
                           row("case.md", text, "hooks/guard.py:42", "hooks/guard.py:42")])

    def test_cost_heading_section_body_is_cost_text(self):
        # A heading that starts with the word Cost, at any level, makes its body cost text up to the next heading.
        # A heading whose word is Costs, or any other word, makes none.
        text = self.decide("heading.md",
                           "## Cost\n"
                           "\n"
                           "It reads `state/h1.json` once.\n"
                           "\n"
                           "Reads `state/h2.json`; `lint/test_h.py` proves it.\n"
                           "\n"
                           "### Cost per call\n"
                           "\n"
                           "Each call reads `state/h4.json` once.\n"
                           "\n"
                           "## Costs\n"
                           "\n"
                           "Not a cost section: reads `state/h5.json` once.\n"
                           "\n"
                           "## Next\n"
                           "\n"
                           "`state/h6.json` is read later.\n")
        self.put("lint/test_h.py", "# h cases\n\nh2.json is read\n")
        self.assert_found([row("heading.md", text, "state/h1.json", "state/h1.json"),
                           row("heading.md", text, "state/h4.json", "state/h4.json")])

    def test_numbered_cost_items_start_a_paragraph_like_a_bullet(self):
        # 8. and 3) are list markers, so a deeper-indented line after them and a deeper bullet stay in the paragraph.
        text = self.decide("numbered.md",
                           "- Parent item\n"
                           "8. Cost: It reads `state/o1.json` once.\n"
                           "   It also reads `state/o2.json` each run.\n"
                           "\n"
                           "3) Cost: It reads `state/o3.json` once.\n"
                           "    - Nested under the cost: reads `state/o4.json` each run.\n")
        self.assert_found([row("numbered.md", text, "state/o%d.json" % n, "state/o%d.json" % n)
                           for n in (1, 2, 3, 4)])

    def test_test_names_narrow_swift_and_spec_files_are_pin_candidates(self):
        # ios/FooTests.swift and web/foo.spec.ts pin the tokens in their sentence, and neither is a file token itself.
        text = self.decide("narrow.md",
                           "- **Cost:** Reads `state/s1.json`; `web/foo.spec.ts` proves it.\n"
                           "- **Cost:** Reads `state/s2.json`; `ios/FooTests.swift` proves it.\n"
                           "- **Cost:** Reads `state/s3.json`; `web/foo.test.js` proves it.\n"
                           "- **Cost:** Reads `state/s4.json`; `web/foo.test.mjs` proves it.\n"
                           "- **Cost:** Each run names `ios/FooTests.swift` and `web/foo.spec.ts` once. "
                           "It also reads `state/real.json` once.\n")
        self.put("web/foo.spec.ts", "// spec cases\ns1.json is read\n")
        self.put("ios/FooTests.swift", "// swift cases\ns2.json is read\n")
        self.put("web/foo.test.js", "// js cases\ns3.json is read\n")
        self.put("web/foo.test.mjs", "// mjs cases\ns4.json is read\n")
        self.assert_found([row("narrow.md", text, "state/real.json", "state/real.json")])

    def test_mid_line_cost_sentence_starts_a_paragraph(self):
        # A sentence that begins Cost: after an earlier sentence on its line starts a Cost paragraph.
        # The Cost: field inside a sentence starts none.
        text = self.decide("mid-line.md",
                           "Landed 2026-10-30. Cost: reads `state/mx.json` once.\n"
                           "\n"
                           "Landed earlier. The Cost: field reads `state/fy.json` once.\n")
        self.assert_found([row("mid-line.md", text, "state/mx.json", "state/mx.json")])

    def test_eg_and_ie_do_not_end_a_sentence(self):
        # e.g. and i.e. are abbreviations: each sentence runs on to its real stop.
        self.decide("abbrev.md",
                    "- **Cost:** It reads e.g. `state/e1.json` once; not pinned.\n"
                    "- **Cost:** Not pinned, e.g. `state/e2.json` once.\n"
                    "- **Cost:** Reads i.e. `state/e3.json` once; unmeasured.\n"
                    "- **Cost:** Unmeasured, i.e. `state/e4.json` once.\n")
        self.assert_clean()

    def test_double_backtick_span_is_one_code_span(self):
        text = self.decide("double.md",
                           "- **Cost:** It reads ``state/x.json`` and `state/y.json` once.\n"
                           "- **Cost:** It reads ``state/w.json`` once.\n")
        self.assert_found([row("double.md", text, "state/x.json", "state/x.json"),
                           row("double.md", text, "state/y.json", "state/y.json"),
                           row("double.md", text, "state/w.json", "state/w.json")])

    def test_hash_line_without_a_space_does_not_end_a_cost_paragraph_or_section(self):
        # A heading is one to six hashes and then a space. #1850 and a seven-hash line are text.
        text = self.decide("hash.md",
                           "- **Cost:** It reads `state/h1.json` once.\n"
                           "#1850 is the issue that prompted it, and it reads `state/h2.json` once.\n"
                           "\n"
                           "- **Cost:** It reads `state/h3.json` once.\n"
                           "####### seven hashes is not a heading, and it reads `state/h4.json` once.\n"
                           "\n"
                           "## Cost\n"
                           "\n"
                           "It reads `state/h5.json` once.\n"
                           "#1851 wraps here, and it reads `state/h6.json` once.\n")
        self.assert_found([row("hash.md", text, "state/h%d.json" % n, "state/h%d.json" % n) for n in range(1, 7)])

    def test_cost_inside_a_code_span_mid_line_starts_nothing(self):
        # A Cost: in a code span starts no paragraph. The second line holds a stop inside the span, then Cost:.
        self.decide("code-span.md",
                    "Fields `Cost:` and `Proof:` are read.\n"
                    "Fields `Landed. Cost:` and `Proof:` are read.\n")
        self.assert_clean()

    def test_e_g_before_cost_colon_mid_sentence_starts_nothing(self):
        self.decide("eg-cost.md", "Fields, e.g. Cost: and Proof:, read `x/y.json` once.\n")
        self.assert_clean()

    def test_mid_line_sentence_start_takes_the_line_start_forms(self):
        text = self.decide("mid-forms.md",
                           "Landed. **Cost**: reads `state/a.json` once.\n"
                           "\n"
                           "Landed. Cost. reads `state/b.json` once.\n"
                           "\n"
                           "Landed. Cost of a run: reads `state/c.json` once.\n")
        self.assert_found([row("mid-forms.md", text, "state/%s.json" % n, "state/%s.json" % n) for n in "abc"])

    def test_pin_candidates_include_spec_and_test_variants(self):
        # Each variant pins the tokens in its sentence when it holds the name. None is a file token itself.
        text = self.decide("candidates.md",
                           "- **Cost:** Reads `state/k1.json`; `web/foo.spec.js` proves it.\n"
                           "- **Cost:** Reads `state/k2.json`; `web/foo.spec.tsx` proves it.\n"
                           "- **Cost:** Reads `state/k3.json`; `web/foo.spec.jsx` proves it.\n"
                           "- **Cost:** Reads `state/k4.json`; `web/foo.spec.mjs` proves it.\n"
                           "- **Cost:** Reads `state/k5.json`; `web/foo.test.tsx` proves it.\n"
                           "- **Cost:** Reads `state/k6.json`; `web/foo.spec.cjs` proves it.\n"
                           "- **Cost:** Reads `state/k7.json`; `web/foo.spec.mts` proves it.\n"
                           "- **Cost:** Reads `state/k8.json`; `web/foo.spec.cts` proves it.\n"
                           "- **Cost:** Reads `state/k9.json`; `web/foo.test.cjs` proves it.\n"
                           "- **Cost:** Reads `state/k10.json`; `web/foo.test.mts` proves it.\n"
                           "- **Cost:** Each run names `web/foo.spec.tsx`, `web/foo.spec.mjs`, `web/foo.spec.cjs`, "
                           "`web/foo.spec.mts`, `web/foo.spec.cts`, `web/foo.test.cjs` and `web/foo.test.mts` once. "
                           "It also reads `state/real.json` once.\n")
        for path, name in (("web/foo.spec.js", "k1"), ("web/foo.spec.tsx", "k2"), ("web/foo.spec.jsx", "k3"),
                           ("web/foo.spec.mjs", "k4"), ("web/foo.test.tsx", "k5"),
                           ("web/foo.spec.cjs", "k6"), ("web/foo.spec.mts", "k7"), ("web/foo.spec.cts", "k8"),
                           ("web/foo.test.cjs", "k9"), ("web/foo.test.mts", "k10")):
            self.put(path, "// cases\n%s.json is read\n" % name)
        self.assert_found([row("candidates.md", text, "state/real.json", "state/real.json")])

    def test_padded_double_backtick_span_strips_one_space(self):
        text = self.decide("padded.md", "- **Cost:** It reads `` state/x.json `` once.\n")
        self.assert_found([row("padded.md", text, "state/x.json", "state/x.json")])

    def test_bare_hash_line_does_not_end_a_cost_paragraph(self):
        # A heading needs text after its hashes, so a line of one # is text.
        text = self.decide("bare-hash.md",
                           "- **Cost:** It reads `state/g1.json` once.\n"
                           "#\n"
                           "It also reads `state/g2.json` once.\n")
        self.assert_found([row("bare-hash.md", text, "state/g1.json", "state/g1.json"),
                           row("bare-hash.md", text, "state/g2.json", "state/g2.json")])

    def test_count_beside_a_cost_noun_with_no_reader_is_flagged(self):
        text = self.decide("count.md", "- **Cost:** one `simctl list` read per call.\n")
        self.assert_found([count_row("count.md", text, "- **Cost:**")], counts=True)

    def test_bound_words_pass_a_count_and_the_unbounded_control_is_flagged(self):
        bounded = ["- **Cost:** at most three `simctl list` reads per call.\n",
                   "- **Cost:** up to two `simctl list` reads per call.\n",
                   "- **Cost:** no more than two `simctl list` reads per call.\n",
                   "- **Cost:** fewer than four `simctl list` reads per call.\n",
                   "- **Cost:** at least one `simctl list` read per call.\n"]
        text = self.decide("bound.md", "".join(bounded) + CONTROL)
        self.assert_found([count_row("bound.md", text, CONTROL_NEEDLE)], counts=True)

    def test_count_pinned_only_by_a_test_that_holds_the_span(self):
        self.put("lint/test_x.py", "# x cases\n\nthe `simctl list` read is stubbed\n")
        self.put("lint/test_y.py", "# y cases\n\nthe status file is read\n")
        self.assert_exists("lint/test_x.py", "lint/test_y.py")
        text = self.decide("pin.md",
                           "- **Cost:** one `simctl list` read per call, pinned by `lint/test_x.py`.\n"
                           "- **Cost:** one `simctl list` read per call, pinned by `lint/test_y.py`.\n")
        self.assert_found([count_row("pin.md", text, "pinned by `lint/test_y.py`")], counts=True)

    def test_unmeasured_not_pinned_unpinned_and_no_test_wording_pass_a_count(self):
        exempt = ["- **Cost:** one read per call, unmeasured.\n",
                  "- **Cost:** one read per call, not pinned.\n",
                  "- **Cost:** one read per call, unpinned.\n",
                  "- **Cost:** one read per call, no test counts it.\n"]
        text = self.decide("exempt-count.md", "".join(exempt) + CONTROL)
        self.assert_found([count_row("exempt-count.md", text, CONTROL_NEEDLE)], counts=True)

    def test_trailing_count_after_a_cost_noun_is_flagged_on_its_own_line(self):
        # The count is flagged on the line that holds its count word, not on the paragraph's first line.
        text = self.decide("trailing.md",
                           "- **Cost:** it reads the list\n"
                           "  twice.\n"
                           "\n"
                           "- **Cost:** it writes the file thrice.\n"
                           "\n"
                           "- **Cost:** it reads the list once.\n")
        self.assert_found([count_row("trailing.md", text, "  twice."),
                           count_row("trailing.md", text, "thrice."),
                           count_row("trailing.md", text, "list once.")], counts=True)

    def test_count_inside_a_code_span_is_not_counted(self):
        text = self.decide("span.md",
                           "- **Cost:** `read 2 files`.\n"
                           "- **Cost:** read 2 files.\n")
        self.assert_found([count_row("span.md", text, "- **Cost:** read 2 files.")], counts=True)

    def test_ids_dates_and_times_beside_a_cost_noun_are_not_counted(self):
        # Each id, date and time sits one or two words from a cost noun, so a rule that reads them as counts flags it.
        clean = ["- **Cost:** step 4 reads the list.\n",
                 "- **Cost:** the 08:34 run reads it.\n",
                 "- **Cost:** the 2026-11-08 run reads it.\n",
                 "- **Cost:** ruling 12 calls it.\n",
                 "- **Cost:** see #1992 for the reads.\n"]
        text = self.decide("ids.md", "".join(clean) + CONTROL)
        self.assert_found([count_row("ids.md", text, CONTROL_NEEDLE)], counts=True)

    def test_brief_non_claims_are_not_counted(self):
        text = self.decide("none.md",
                           "- **Cost:** none. Source: owner, 2026-11-08 08:34 CST, ruling 12.\n"
                           "- **Cost:** one home for the rule.\n"
                           "- **Cost:** see item 386 and #1992.\n"
                           + CONTROL)
        self.assert_found([count_row("none.md", text, CONTROL_NEEDLE)], counts=True)

    def test_one_count_claim_is_one_finding_per_sentence(self):
        text = self.decide("one-per.md", "- **Cost:** one `simctl list` read and two writes per call.\n")
        self.assert_found([count_row("one-per.md", text, "- **Cost:**")], counts=True)

    def test_span_wrapped_over_a_line_break_holds_its_count(self):
        # The span runs over the line break, so its 2 is inside code and is not counted.
        text = self.decide("wrapped-span.md", "- **Cost:** it runs `read\n  2 files` per call.\n" + CONTROL)
        self.assert_found([count_row("wrapped-span.md", text, CONTROL_NEEDLE)], counts=True)

    def test_apostrophe_and_comment_openers_in_a_span_do_not_hide_a_count(self):
        # A lone apostrophe and a comment opener inside a span must not end the sentence or hide the count.
        text = self.decide("scan-marks.md",
                           "- **Cost:** it's read twice by the `//` pass.\n"
                           "- **Cost:** it's read by the `#` pass, once a run.\n")
        self.assert_found([count_row("scan-marks.md", text, "it's read twice"),
                           count_row("scan-marks.md", text, "once a run.")], counts=True)

    def test_pin_is_the_nearest_span_not_any_span(self):
        # The nearest span to the count is `near`. A test that holds only the far span pins nothing here.
        self.put("lint/test_x.py", "# x cases\n\nfar is stubbed\n")
        self.put("lint/test_y.py", "# y cases\n\nnear is stubbed\n")
        self.assert_exists("lint/test_x.py", "lint/test_y.py")
        text = self.decide("nearest.md",
                           "- **Cost:** `far` helper runs one `near` read, pinned by `lint/test_x.py`.\n"
                           "- **Cost:** `far` helper runs one `near` read, pinned by `lint/test_y.py`.\n")
        self.assert_found([count_row("nearest.md", text, "pinned by `lint/test_x.py`")], counts=True)

    def test_test_name_span_is_never_the_nearest_span(self):
        # `lint/test_x.py` is nearer the count than `far`, but a test-name span is never the nearest, so the
        # count is pinned only by a test that holds `far`. test_x holds its own name and not `far`, so it pins nothing.
        self.put("lint/test_x.py", "# x cases\n\ntest_x.py is run\n")
        self.put("lint/test_y.py", "# y cases\n\nfar is stubbed\n")
        self.assert_exists("lint/test_x.py", "lint/test_y.py")
        text = self.decide("test-span.md",
                           "- **Cost:** one read per call, in `lint/test_x.py`, for `far`.\n"
                           "- **Cost:** one read per call, in `lint/test_y.py`, for `far`.\n")
        self.assert_found([count_row("test-span.md", text, "in `lint/test_x.py`")], counts=True)

    def test_word_gap_is_three_words_not_four(self):
        # Three words sit between the count and `read`, so the count is read. Four words sit between, so it is not.
        text = self.decide("gap.md",
                           "- **Cost:** one pass over ledger read.\n"
                           "- **Cost:** one pass over the ledger read.\n")
        self.assert_found([count_row("gap.md", text, "one pass over ledger read.")], counts=True)

    def test_bound_inside_a_code_span_does_not_pass_a_count(self):
        # `at most` inside a code span is code, not a bound, so the count has no reader and is flagged.
        text = self.decide("span-bound.md", "- **Cost:** one `at most` read per call.\n")
        self.assert_found([count_row("span-bound.md", text, "- **Cost:**")], counts=True)


class CorpusTests(unittest.TestCase):
    """The corpus case: this repo's own records, with no --root. It may stay red until the records that name
    an unpinned file in a Cost sentence are fixed. It proves the repo is clean; the cases above prove the check flags."""

    def test_this_repo_names_no_unpinned_cost_file(self):
        self.assertTrue(os.path.isfile(MODULE), "module absent: lint/check_cost_pins.py")
        r = subprocess.run([sys.executable, MODULE], cwd=REPO, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertEqual(findings(out), [], out)


if __name__ == "__main__":
    unittest.main()
