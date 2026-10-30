#!/usr/bin/env python3
"""Fixture suite for lint/check_agent_models.py. Run: python3 lint/test_check_agent_models.py

Haiku is allowed only in the agent files for Explore, claude-code-guide, test-author and reviewer.
Every other agent or skill file keeps the Sonnet floor.
Failure classes: false deny (a listed role fails), false allow (another file passes, by name
collision, case or alias), unreadable frontmatter.
One case reads the real agents/plan.md: its "Premises first" paragraph cites the premise record.
The lane session row of docs/decisions/agent-model-cap.md must start its effort cell with medium.
"""
import contextlib, io, os, re, shutil, sys, tempfile, time, unittest, uuid

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


def verdict(relpath, model=None, closed=True, text=None, relative=False):
    """Write one fixture under this run's folder and return the check's (code, stdout).

    An agent file with frontmatter, unless `text` gives the whole file (a record). `relative` runs
    the check from the fixture's folder with the path as given, as a run from a repository root does.
    """
    with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as tmp:
        path = os.path.join(tmp, relpath)
        os.makedirs(os.path.dirname(path))
        with open(path, "w") as handle:
            if text is None:
                handle.write("---\nname: x\nmodel: %s\n%sbody\n" % (model, "---\n" if closed else ""))
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
