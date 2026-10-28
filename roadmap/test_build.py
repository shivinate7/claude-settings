"""build.py refuses a tree with git conflict markers (step c72); the pre-commit hook refuses an over-cap
note (step c138). Run: python roadmap/test_build.py"""
import contextlib
import io
import json
import os
import pathlib
import shutil
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
        line = next(l for l in out.getvalue().splitlines() if l.startswith("upkeep: "))
        return line.split("deferred on shiv with no question: ", 1)[1].split(";")[0]

    def test_deferred_with_no_question_counts(self):
        self.assertEqual(self.count("Deferred (shiv, Oct 26): needs your answer."), "1")
        self.assertEqual(self.count("Deferred: shiv's word on the read."), "1")

    def test_asked_line_clears_it(self):
        self.assertEqual(self.count("Deferred (shiv, Oct 26): x. Asked: waiting page item 31."), "0")

    def test_due_after_line_clears_it(self):
        self.assertEqual(self.count("Deferred (shiv, Oct 26): x. Due after: o2's layout move."), "0")

    def test_deferred_by_triage_is_not_on_shiv(self):
        self.assertEqual(self.count("Deferred (triage, Oct 27): not now."), "0")


HERE = pathlib.Path(__file__).resolve().parent


def words(n):
    return " ".join(["w"] * n)


class NoteCapHook(unittest.TestCase):
    """A real git repo with the real hook and build.py, installed by the setup line in CLAUDE.md."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = repo = pathlib.Path(self.tmp.name) / "r"
        (repo / "roadmap" / "data" / "steps").mkdir(parents=True)
        shutil.copy(HERE / "build.py", repo / "roadmap" / "build.py")
        if (HERE / "hooks").is_dir():
            shutil.copytree(HERE / "hooks", repo / "roadmap" / "hooks")
        self.env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                        GIT_COMMITTER_EMAIL="t@t", PYTHONDONTWRITEBYTECODE="1")
        self.git("init", "-q", "-b", "roadmap")
        self.git("config", "core.hooksPath", "roadmap/hooks")  # the setup line in CLAUDE.md
        self.git("add", "roadmap/build.py")
        self.commit("tools")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args, cwd=None, check=True):
        r = subprocess.run(["git", *args], cwd=cwd or self.repo, env=self.env, capture_output=True, text=True)
        if check and r.returncode:
            self.fail(f"git {' '.join(args)}: {r.stdout}{r.stderr}")
        return r

    def step(self, sid, n, status="open", where=None):
        path = (where or self.repo) / "roadmap" / "data" / "steps" / f"{sid}.json"
        path.write_text(json.dumps(dict(STEP, status=status, note=words(n))), encoding="utf-8")

    def commit(self, msg="m", *extra, cwd=None):
        return self.git("commit", "-q", "-m", msg, *extra, cwd=cwd, check=False)

    def assert_refused(self, r, *names):
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        for name in names:
            self.assertIn(name, r.stdout + r.stderr)

    def assert_passed(self, r):
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_grown_note_over_cap_is_refused(self):
        self.step("c122", 240)
        self.git("add", "-A")
        self.assert_passed(self.commit("c122"))
        self.step("c122", 263)
        self.git("add", "-A")
        self.assert_refused(self.commit("grow c122"), "c122 (263 words)")

    def seed(self, *steps):
        """Commit steps (sid, words[, status]) with the hook off, as if an older writer had."""
        for st in steps:
            self.step(*st)
        self.git("add", "-A")
        self.assert_passed(self.commit("seed", "--no-verify"))

    def test_note_at_cap_passes(self):
        self.step("c122", build.NOTE_WORDS)
        self.git("add", "-A")
        self.assert_passed(self.commit())

    def test_new_note_over_cap_is_refused(self):
        self.step("c1", 10)
        self.step("c2", 251)
        self.git("add", "-A")
        r = self.commit()
        self.assert_refused(r, "c2 (251 words)")
        self.assertNotIn("c1 (", r.stderr)

    def test_untouched_over_cap_note_does_not_block(self):
        self.seed(("c9", 300))
        self.step("c1", 10)
        (self.repo / "README.md").write_text("x\n", encoding="utf-8")
        self.git("add", "-A")
        self.assert_passed(self.commit())

    def test_other_field_of_over_cap_step_passes(self):
        self.seed(("c9", 300))
        path = self.repo / "roadmap" / "data" / "steps" / "c9.json"
        path.write_text(json.dumps(dict(json.loads(path.read_text()), title="new")), encoding="utf-8")
        self.git("add", "-A")
        self.assert_passed(self.commit())

    def test_done_step_over_cap_passes(self):
        self.step("c5", 400, status="done")
        self.git("add", "-A")
        self.assert_passed(self.commit())

    def test_deleted_step_passes(self):
        self.seed(("c9", 300))
        self.git("rm", "-q", "roadmap/data/steps/c9.json")
        self.assert_passed(self.commit())

    def test_invalid_json_does_not_block(self):
        (self.repo / "roadmap" / "data" / "steps" / "c7.json").write_text("{not json", encoding="utf-8")
        self.git("add", "-A")
        r = self.commit()
        self.assert_passed(r)
        self.assertIn("c7.json is not valid JSON", r.stderr)

    def test_staged_under_cap_worktree_over_passes(self):
        self.step("c122", 240)
        self.git("add", "-A")
        self.step("c122", 300)
        self.assert_passed(self.commit())

    def test_staged_over_cap_worktree_under_is_refused(self):
        self.step("c122", 263)
        self.git("add", "-A")
        self.step("c122", 240)
        self.assert_refused(self.commit(), "c122 (263 words)")

    def test_commit_all_checks_the_commit_index(self):
        self.seed(("c122", 240))
        self.step("c122", 263)
        self.assert_refused(self.commit("m", "-a"), "c122 (263 words)")

    def test_amend_with_only_page_staged_passes(self):
        self.seed(("c9", 300))
        (self.repo / "roadmap" / "roadmap.html").write_text("<html></html>", encoding="utf-8")
        self.git("add", "-A")
        self.assert_passed(self.commit("m", "--amend", "--no-edit"))
        self.assert_passed(self.commit("empty", "--allow-empty"))

    def test_merge_of_other_writers_over_cap_note_passes(self):
        self.seed(("c1", 10))
        self.git("checkout", "-q", "-b", "other")
        self.seed(("c9", 300), ("c1", 20))
        self.git("checkout", "-q", "roadmap")
        self.step("c1", 30)
        self.git("add", "-A")
        self.assert_passed(self.commit())
        self.git("merge", "-q", "other", check=False)  # conflicts on c1
        self.step("c1", 25)
        self.git("add", "-A")
        self.assert_passed(self.commit("merge"))
        self.assertIn("c9.json", self.git("show", "--stat", "HEAD^2").stdout)

    def test_hook_runs_in_a_worktree(self):
        self.seed(("c1", 10))
        wt = pathlib.Path(self.tmp.name) / "wt"
        self.git("worktree", "add", "-q", "-b", "wt", str(wt))
        self.step("c122", 263, where=wt)
        self.git("add", "-A", cwd=wt)
        self.assert_refused(self.commit("m", cwd=wt), "c122 (263 words)")
        self.step("c122", 240, where=wt)
        self.git("add", "-A", cwd=wt)
        self.assert_passed(self.commit("m", cwd=wt))


if __name__ == "__main__":
    unittest.main()
