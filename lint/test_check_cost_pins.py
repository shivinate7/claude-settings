#!/usr/bin/env python3
"""Cases for lint/check_cost_pins.py. Standard library only.

    python3 lint/test_check_cost_pins.py

A decision record's Cost sentence may name a file only when a test pins it. The check reads
docs/decisions/*.md under --root and prints one line per unpinned file token:
`<record path>:<line>: <file token> named in a Cost sentence with no pin`.

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
FINDING = re.compile(r"^(?P<path>.+\.md):(?P<line>[0-9]+): (?P<token>.+) named in a Cost sentence with no pin$")
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


def findings(out):
    """(record, line, token) for each finding line in the output, in the order printed."""
    rows = []
    for text in out.splitlines():
        m = FINDING.match(text.strip())
        if m:
            rows.append((record_of(m.group("path")), int(m.group("line")), m.group("token")))
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
        self.assertEqual(findings(out), [], out)

    def assert_found(self, expected):
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertEqual(sorted(findings(out)), sorted(expected), out)

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
