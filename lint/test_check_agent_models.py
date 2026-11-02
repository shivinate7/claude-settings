#!/usr/bin/env python3
"""Fixture suite for lint/check_agent_models.py. Run: python3 lint/test_check_agent_models.py

Haiku is allowed only in the agent files for Explore, claude-code-guide, test-author and reviewer.
Every other agent or skill file keeps the Sonnet floor.
Failure classes: false deny (a listed role fails), false allow (another file passes, by name
collision, case or alias), unreadable frontmatter.
One case reads the real agents/plan.md: its "Premises first" paragraph cites the premise record.
The lane session row of docs/decisions/agent-model-cap.md must start its effort cell with medium.
A drift between the guard's role lists and the role table fails the check (the guard's role_list_drift).
An agent file's `model:` pin must equal its role's row in the role table. The role is the frontmatter `name:`,
as the guard keys it. A file with no pin, or a name with no row, is not flagged by that rule.
"""
import contextlib, io, os, re, shutil, sys, tempfile, time, unittest, uuid
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import check_agent_models as C  # noqa: E402
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)
RUN_FOLDER = _test_temp.run_folder()

ROLES = ("explore", "claude-code-guide", "test-author", "reviewer")
MODELS = ("haiku", "claude-haiku-5-5", "Haiku")
# The model table of docs/decisions/agent-model-cap.md, reduced to its lane session row. Only the effort cell varies.
RECORD_RELPATH = os.path.join("docs", "decisions", "agent-model-cap.md")
LANE_RECORD = ("| Point | Model | Effort |\n|---|---|---|\n"
               "| lane session (decision `session-tiers`) | opus, the owner's ruling of 2026-10-28 16:15 CDT | %s |\n")


def verdict(relpath, model=None, closed=True, text=None, relative=False, name="x", pinned=True):
    """Write one fixture under this run's folder and return the check's (code, stdout).

    An agent file with frontmatter, unless `text` gives the whole file (a record). `relative` runs
    the check from the fixture's folder with the path as given, as a run from a repository root does.
    `name` is the frontmatter name, the role key. `pinned=False` writes no model line.
    """
    with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as tmp:
        path = os.path.join(tmp, relpath)
        os.makedirs(os.path.dirname(path))
        with open(path, "w") as handle:
            if text is None:
                head = "---\nname: %s\n%s" % (name, "model: %s\n" % model if pinned else "")
                handle.write("%s%sbody\n" % (head, "---\n" if closed else ""))
            else:
                handle.write(text)
        out = io.StringIO()
        before = os.getcwd()
        if relative:
            os.chdir(tmp)
        try:
            with contextlib.redirect_stdout(out):
                code = C.main([relpath if relative else path])
        finally:
            os.chdir(before)
        return code, out.getvalue()


class Haiku(unittest.TestCase):
    def test_listed_roles_may_set_haiku(self):
        for role in ROLES:
            for model in MODELS:
                with self.subTest(role=role, model=model):
                    self.assertEqual(verdict("agents/%s.md" % role, model), (0, ""))

    def test_other_agents_still_fail(self):
        for name in ("builder", "plan", "general-purpose", "claude", "reviewer-lite", "explorer"):
            with self.subTest(name=name):
                self.assertEqual(verdict("agents/%s.md" % name, "haiku")[0], 1)

    def test_skill_files_still_fail(self):
        # A skill named like a role is still a skill.
        for name in ("deploy", "explore", "reviewer", "test-author"):
            with self.subTest(name=name):
                self.assertEqual(verdict("skills/%s/SKILL.md" % name, "haiku")[0], 1)

    def test_listed_roles_may_set_sonnet(self):
        for role in ROLES:
            self.assertEqual(verdict("agents/%s.md" % role, "sonnet"), (0, ""))

    def test_unclosed_frontmatter_still_fails_for_a_listed_role(self):
        self.assertEqual(verdict("agents/reviewer.md", "haiku", closed=False)[0], 1)


def names(out, filename, *words):
    """True when one line of the check's output names the file and each word."""
    return any(filename in line and all(word in line for word in words) for line in out.splitlines())


class PinEqualsRow(unittest.TestCase):
    # The role is the frontmatter `name:`, as the guard keys it (role_agent_keys). Table keys are case-exact (Explore,
    # Plan). The rows come from the real record through the guard's one reader. A case that names a row first asserts
    # that row, so a moved row reads as a stale case, not as a false pass.
    def assertRow(self, role, row):
        table = C._guard.role_model_table(C.ROOT) or {}
        self.assertEqual(table.get(role), row, "the record's row for %r moved; re-point the cases that name it" % role)

    def agent(self, role, model):
        return verdict("agents/%s.md" % role.lower(), model, name=role)

    def test_pin_that_differs_from_its_row_is_flagged(self):
        # Sonnet and opus pins clear the Haiku floor, so these fail only on the pin-equals-row rule.
        cases = (("reviewer", "sonnet", "haiku"), ("reviewer", "claude-sonnet-5-5", "haiku"),
                 ("reviewer", "opus", "haiku"), ("Explore", "sonnet", "haiku"),
                 ("Plan", "sonnet", "opus"), ("designer", "sonnet", "opus"), ("design-reviewer", "sonnet", "opus"))
        for role, pin, row in cases:
            with self.subTest(role=role, pin=pin):
                self.assertRow(role, row)
                code, out = self.agent(role, pin)
                self.assertEqual(code, 1, "pin %s on the %s row passes: %r" % (pin, row, out))
                self.assertTrue(names(out, "%s.md" % role.lower(), pin, row),
                                "no line names the file, the pin and the row: %r" % out)

    def test_pin_equal_to_its_row_passes(self):
        cases = [("Plan", "opus", "opus"), ("Plan", "claude-opus-5-5", "opus"), ("designer", "opus", "opus"),
                 ("design-reviewer", "opus", "opus"), ("builder", "sonnet", "sonnet")]
        cases += [(role, model, "haiku") for role in ("Explore", "claude-code-guide", "test-author", "reviewer",
                                                       "record-writer") for model in MODELS]
        for role, model, row in cases:
            with self.subTest(role=role, model=model):
                self.assertRow(role, row)
                self.assertEqual(self.agent(role, model), (0, ""))

    def test_file_with_no_model_pin_is_not_flagged(self):
        for role in ("builder", "reviewer"):
            with self.subTest(role=role):
                self.assertRow(role, "sonnet" if role == "builder" else "haiku")
                self.assertEqual(verdict("agents/%s.md" % role, name=role, pinned=False), (0, ""))

    def test_role_with_no_table_row_is_not_flagged(self):
        self.assertNotIn("some-role", C._guard.role_model_table(C.ROOT) or {})
        self.assertEqual(verdict("agents/some-role.md", "sonnet", name="some-role"), (0, ""))
        self.assertEqual(verdict("agents/some-role.md", "opus", name="some-role"), (0, ""))

    def test_pin_is_read_past_comments_quotes_and_indented_text(self):
        # Source-text cases (building-scanner-respects-strings): a comment that names the other model, a lone quote in
        # another key's text, and an indented `model:` line inside a block scalar. Only the top-level pin counts.
        self.assertRow("reviewer", "haiku")
        flagged = (("comment names the row word", "model: sonnet  # not haiku\n"),
                   ("lone quote in another key", "description: Don't pin it\nmodel: sonnet\n"),
                   ("indented model line in a block scalar",
                    "description: |\n  model: haiku\n  it's a note\nmodel: sonnet\n"))
        for label, lines in flagged:
            with self.subTest(label):
                code, out = verdict("agents/reviewer.md", text="---\nname: reviewer\n%s---\nbody\n" % lines)
                self.assertEqual(code, 1, "%s: a sonnet pin on the haiku row passes: %r" % (label, out))
                self.assertTrue(names(out, "reviewer.md", "sonnet", "haiku"),
                                "%s: no line names the pin and the row: %r" % (label, out))
        # A comment after a haiku pin that names sonnet leaves the pin haiku, so the file passes.
        self.assertEqual(verdict("agents/reviewer.md",
                                 text="---\nname: reviewer\nmodel: haiku  # sonnet is above the row\n---\nbody\n"),
                         (0, ""))


# The kind is the backticked first cell of a table row, as hooks/test_precompact_handoff.py reads it.
KIND_ROW = re.compile(r"^\|\s*`([a-z]+)`\s*\|", re.M)


class PlanPremises(unittest.TestCase):
    def test_premises_first_cites_the_record_and_copies_no_kind(self):
        with open(os.path.join(ROOT, "agents", "plan.md"), encoding="utf-8") as handle:
            paragraphs = re.split(r"\n\s*\n", handle.read())
        found = [p for p in paragraphs if p.startswith("Premises first")]
        self.assertEqual(len(found), 1, "agents/plan.md needs one 'Premises first' paragraph")
        self.assertIn("`premise-format`", found[0])
        # One home for the kinds: docs/decisions/premise-format.md. The plan agent points at it.
        with open(os.path.join(ROOT, "docs", "decisions", "premise-format.md"), encoding="utf-8") as handle:
            kinds = KIND_ROW.findall(handle.read())
        self.assertTrue(kinds, "no kind rows in docs/decisions/premise-format.md")
        for kind in kinds:
            with self.subTest(kind=kind):
                self.assertIsNone(re.search(r"\b%s\b" % kind, found[0], re.I),
                                  "the paragraph copies the kind %r; cite the record" % kind)


class LaneEffort(unittest.TestCase):
    # The check reads the record it is given as a path. A record at docs/decisions/agent-model-cap.md fails
    # unless the lane session row's effort cell starts with the lane effort, medium.
    def record(self, effort):
        return verdict(RECORD_RELPATH, text=LANE_RECORD % effort)

    def test_lane_row_effort_default_fails(self):
        code, out = self.record("default")
        self.assertEqual(code, 1, "a lane row at effort default passes: %r" % out)

    def test_lane_row_effort_starting_medium_passes(self):
        self.assertEqual(self.record("medium, the owner's ruling of 2026-10-30 15:11 CDT"), (0, ""))

    def test_lane_row_effort_must_start_with_medium(self):
        # A medium later in the cell is not the lane effort: the cell must start with it.
        code, out = self.record("default, medium")
        self.assertEqual(code, 1, "a lane row whose cell only mentions medium passes: %r" % out)

    def test_relative_record_path_with_default_row_fails(self):
        # The check must read the record when the path is relative, as a run from the repository root gives it.
        code, out = verdict(RECORD_RELPATH, text=LANE_RECORD % "default", relative=True)
        self.assertEqual(code, 1, "a relative record path with a default lane row passes: %r" % out)


class RoleListDrift(unittest.TestCase):
    # The check fails when the guard's role_list_drift names drift, and passes when it names none. The check looks
    # the function up at run time, so the patch takes effect (decision agent-model-cap, the three role lists).
    def run_main(self, lines):
        """Run the check on this repository with role_list_drift patched to `lines`: (code, stdout, pointers)."""
        pointers = []

        def fake(pointer_root):
            pointers.append(pointer_root)
            return list(lines)

        out = io.StringIO()
        with mock.patch.object(C._guard, "role_list_drift", fake, create=True), contextlib.redirect_stdout(out):
            code = C.main([])
        return code, out.getvalue(), pointers

    def test_drift_fails_the_check_and_prints_the_line(self):
        line = "test-author is on a sonnet row but in HAIKU_ROLES (hooks/guard.py)"
        code, out, pointers = self.run_main([line])
        self.assertEqual(code, 1, "a drift line from role_list_drift passes the check: %r" % out)
        self.assertIn(line, out)
        self.assertEqual(pointers, [C.ROOT], "the check does not call role_list_drift on this repository")

    def test_no_drift_passes_the_check(self):
        code, out, _ = self.run_main([])
        self.assertEqual((code, out), (0, ""), "no drift from role_list_drift still fails the check: %r" % out)


class RunFolder(unittest.TestCase):
    def test_first_request_sweeps_old_siblings_and_keeps_new_ones(self):
        # test-temp-standard: the first request of a run removes a sibling over a day old and keeps a newer one.
        root = os.path.join(RUN_FOLDER, "sweep")
        old = os.path.join(root, "1-%s" % uuid.uuid4().hex)
        new = os.path.join(root, "2-%s" % uuid.uuid4().hex)
        for path in (old, new):
            os.makedirs(path)
        two_days_ago = time.time() - 2 * 24 * 60 * 60
        os.utime(old, (two_days_ago, two_days_ago))
        own = _test_temp.run_folder(temp_root=root)
        self.assertFalse(os.path.exists(old), "an old sibling run folder survived the sweep")
        self.assertTrue(os.path.isdir(new), "a new sibling run folder was swept")
        self.assertTrue(os.path.isdir(own))


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
