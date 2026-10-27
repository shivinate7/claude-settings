"""build.py refuses a tree with git conflict markers (step c72). Run: python roadmap/test_build.py"""
import contextlib
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build  # noqa: E402

STEP = {"title": "t", "status": "open", "phase": "p", "order": 1, "note": "n", "updatedAt": "2026-10-26T00:00:00Z"}
CONFLICT = "<<<<<<< HEAD\na\n=======\nb\n>>>>>>> 1234567 (other)\n"


class ConflictMarkers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        repo = pathlib.Path(self.tmp.name)
        self.repo, self.root = repo, repo / "roadmap"
        for folder in ("steps", "topics", "meta"):
            (self.root / "data" / folder).mkdir(parents=True)
        (self.root / "data" / "steps" / "c1.json").write_text(json.dumps(STEP), encoding="utf-8")
        (self.root / "page").mkdir()
        (self.root / "page" / "index.html").write_text("<html><body></body></html>", encoding="utf-8")
        (repo / "briefs").mkdir()
        (repo / "briefs" / "c1.md").write_text("# c1\n\nA brief.\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        self.old = build.ROOT, build.DATA
        build.ROOT, build.DATA = self.root, self.root / "data"

    def tearDown(self):
        build.ROOT, build.DATA = self.old
        self.tmp.cleanup()

    def build(self):
        subprocess.run(["git", "-C", str(self.repo), "add", "-A"], check=True)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                build.main()
                code = 0
            except SystemExit as e:
                code = e.code
        return code, out.getvalue()

    def assert_refused(self, path):
        code, out = self.build()
        self.assertNotIn(code, (0, None), out)
        self.assertIn(path, out)
        self.assertFalse((self.root / "roadmap.html").exists(), "a refused build wrote the page")

    def test_marker_in_step_fails(self):
        (self.root / "data" / "steps" / "c1.json").write_text("{\n" + CONFLICT + "}\n", encoding="utf-8")
        self.assert_refused("roadmap/data/steps/c1.json:2")

    def test_marker_in_brief_fails(self):
        (self.repo / "briefs" / "c1.md").write_text("# c1\n\n" + CONFLICT, encoding="utf-8")
        self.assert_refused("briefs/c1.md:3")

    def test_setext_heading_passes(self):
        (self.repo / "briefs" / "c1.md").write_text("Title\n=======\n\nText.\n", encoding="utf-8")
        code, out = self.build()
        self.assertIn(code, (0, None), out)
        self.assertTrue((self.root / "roadmap.html").exists())

    def test_clean_tree_passes(self):
        code, out = self.build()
        self.assertIn(code, (0, None), out)
        self.assertTrue((self.root / "roadmap.html").exists())


class DeferredWithNoQuestion(unittest.TestCase):
    def count(self, note):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            build.upkeep({"c1": dict(STEP, note=note)})
        return out.getvalue().splitlines()[0].rsplit("deferred on shiv with no question: ", 1)[1]

    def test_deferred_with_no_question_counts(self):
        self.assertEqual(self.count("Deferred (shiv, Oct 26): needs your answer."), "1")
        self.assertEqual(self.count("Deferred: shiv's word on the read."), "1")

    def test_asked_line_clears_it(self):
        self.assertEqual(self.count("Deferred (shiv, Oct 26): x. Asked: waiting page item 31."), "0")

    def test_due_after_line_clears_it(self):
        self.assertEqual(self.count("Deferred (shiv, Oct 26): x. Due after: o2's layout move."), "0")

    def test_deferred_by_triage_is_not_on_shiv(self):
        self.assertEqual(self.count("Deferred (triage, Oct 27): not now."), "0")


if __name__ == "__main__":
    unittest.main()
