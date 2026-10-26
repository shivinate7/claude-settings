"""Fixture suite for the roadmap builder. Run: python3 skills/roadmap/test_build.py

Each case builds a throwaway git repo: `main` holds the record homes, `roadmap` holds roadmap/data/.
"""
import contextlib
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build  # noqa: E402

STEP = {"title": "t", "status": "todo", "phase": "cleanup", "order": 1, "note": "n", "updatedAt": "2026-10-26T00:00:00Z"}
CONFLICT = "<<<<<<< HEAD\na\n=======\nb\n>>>>>>> 1234567 (other)\n"
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}

# The page script the roadmap branch's build.py put in front of the viewer (roadmap 496ddbc). The
# builder's stub must stay byte for byte this, so the viewer reads the data as it did.
TODAY_STUB = """<script>
(() => {
  const DATA = %s;
  const snap = docs => ({docs: docs.map(([id, d]) => ({id, data: () => d}))});
  const byOrder = (a, b) => (typeof a[1].order === 'number' ? a[1].order : 1e9) - (typeof b[1].order === 'number' ? b[1].order : 1e9);
  const collection = name => ({
    orderBy: () => ({onSnapshot: ok => ok(snap(Object.entries(DATA[name] || {}).sort(byOrder)))}),
  });
  const doc = path => {
    const [col, id] = path.split('/');
    const d = (DATA[col] || {})[id];
    return {
      onSnapshot: ok => ok({exists: !!d, data: () => d}),
      update: () => Promise.reject(new Error('read only')),
    };
  };
  window.ROADMAP_DB = {use: async () => ({collection, doc, readOnly: true})};
})();
</script>
"""
BLOCK = re.compile(r"<!-- build:([a-z-]+) -->.*?<!-- /build:\1 -->\n?", re.S)


def today_page(template, data):
    """What the roadmap branch's build.py wrote for this template and data."""
    head, sep, rest = template.partition("<body>")
    return head + sep + "\n" + TODAY_STUB % json.dumps(data, ensure_ascii=False).replace("</", "<\\/") + rest


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True,
                          env={**os.environ, **GIT_ENV}).stdout


def run_build(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            build.main(list(argv))
            code = 0
        except SystemExit as e:
            code = e.code
    return code, out.getvalue()


def build_info(page):
    found = re.search(r"window\.ROADMAP_BUILD = (.*?);\n</script>", page, re.S)
    return json.loads(found.group(1).replace("<\\/", "</"))


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = repo = pathlib.Path(self.tmp.name) / "repo"
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        (repo / "decisions").mkdir()
        (repo / "decisions" / "one.md").write_text("# one\n", encoding="utf-8")
        (repo / "README.md").write_text("# r\n", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "main")
        git(repo, "checkout", "-q", "--orphan", "roadmap")
        git(repo, "rm", "-rq", "--cached", ".")
        for name in ("decisions", "README.md"):
            p = repo / name
            if p.is_dir():
                for f in p.iterdir():
                    f.unlink()
                p.rmdir()
            else:
                p.unlink()
        self.data = repo / "roadmap" / "data"
        for folder in ("steps", "topics", "meta"):
            (self.data / folder).mkdir(parents=True)
        self.write_step("c1", STEP)
        (self.data / "topics" / "t01.json").write_text(json.dumps({"title": "x", "order": 1}), encoding="utf-8")
        (self.data / "meta" / "cull.json").write_text(json.dumps({"stopRule": "s"}), encoding="utf-8")
        (repo / "briefs").mkdir()
        (repo / "briefs" / "c1.md").write_text("# c1\n\nA brief.\n", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "roadmap")
        self.out = pathlib.Path(self.tmp.name) / "page.html"

    def tearDown(self):
        self.tmp.cleanup()

    def write_step(self, sid, step):
        (self.data / "steps" / (sid + ".json")).write_text(json.dumps(step), encoding="utf-8")

    def on_main(self):
        git(self.repo, "checkout", "-q", "main")

    def build_from_main(self, *extra):
        self.on_main()
        code, out = run_build("--repo", str(self.repo), "--out", str(self.out), *extra)
        self.assertIn(code, (0, None), out)
        return self.out.read_text(encoding="utf-8"), out


class TodaysPage(Fixture):
    def test_page_equals_today_apart_from_the_build_blocks(self):
        page, _ = self.build_from_main()
        template = (HERE / "page" / "index.html").read_text(encoding="utf-8")
        data = {"steps": {"c1": STEP}, "topics": {"t01": {"title": "x", "order": 1}}, "meta": {"cull": {"stopRule": "s"}}}
        self.assertEqual(BLOCK.sub("", page), today_page(BLOCK.sub("", template), data))

    def test_template_holds_build_blocks(self):
        template = (HERE / "page" / "index.html").read_text(encoding="utf-8")
        self.assertTrue(BLOCK.search(template), "the strip above would prove nothing")

    def test_record_branch_tree_writes_its_own_page(self):
        code, out = run_build("--repo", str(self.repo))
        self.assertIn(code, (0, None), out)
        self.assertTrue((self.repo / "roadmap" / "roadmap.html").exists())

    def test_off_the_record_branch_needs_out(self):
        self.on_main()
        code, out = run_build("--repo", str(self.repo))
        self.assertNotIn(code, (0, None), out)


class Stamps(Fixture):
    def panels(self, page):
        return {p["name"]: p for p in build_info(page)["panels"]}

    def test_each_home_carries_a_read_at_stamp(self):
        page, _ = self.build_from_main()
        panels = self.panels(page)
        sha = git(self.repo, "rev-parse", "--short", "roadmap").strip()
        self.assertEqual(panels["Steps"]["read"], sha)
        self.assertEqual(panels["Decisions"]["read"], git(self.repo, "rev-parse", "--short", "main").strip())
        self.assertTrue(build_info(page)["builtAt"])

    def test_missing_home_reads_unknown(self):
        page, _ = self.build_from_main()
        debts = self.panels(page)["Debts"]
        self.assertTrue(debts["read"].startswith("unknown"), debts)
        self.assertNotIn("none", debts["read"])

    def test_missing_record_branch_reads_unknown(self):
        self.on_main()
        git(self.repo, "branch", "-q", "-D", "roadmap")
        code, out = run_build("--repo", str(self.repo), "--out", str(self.out))
        self.assertIn(code, (0, None), out)
        page = self.out.read_text(encoding="utf-8")
        self.assertTrue(self.panels(page)["Steps"]["read"].startswith("unknown"))
        self.assertIn("window.ROADMAP_DB = null", page)


class ConflictMarkers(Fixture):
    def build_tree(self):
        git(self.repo, "add", "-A")
        return run_build("--repo", str(self.repo))

    def assert_refused(self, path):
        code, out = self.build_tree()
        self.assertNotIn(code, (0, None), out)
        self.assertIn(path, out)
        self.assertFalse((self.repo / "roadmap" / "roadmap.html").exists(), "a refused build wrote the page")

    def test_marker_in_step_fails(self):
        (self.data / "steps" / "c1.json").write_text("{\n" + CONFLICT + "}\n", encoding="utf-8")
        self.assert_refused("roadmap/data/steps/c1.json:2")

    def test_marker_in_brief_fails(self):
        (self.repo / "briefs" / "c1.md").write_text("# c1\n\n" + CONFLICT, encoding="utf-8")
        self.assert_refused("briefs/c1.md:3")

    def test_marker_on_the_branch_fails_a_build_from_main(self):
        (self.repo / "briefs" / "c1.md").write_text("# c1\n\n" + CONFLICT, encoding="utf-8")
        git(self.repo, "commit", "-qam", "bad")
        self.on_main()
        code, out = run_build("--repo", str(self.repo), "--out", str(self.out))
        self.assertNotIn(code, (0, None), out)
        self.assertIn("briefs/c1.md:3", out)
        self.assertFalse(self.out.exists())

    def test_setext_heading_passes(self):
        (self.repo / "briefs" / "c1.md").write_text("Title\n=======\n\nText.\n", encoding="utf-8")
        code, out = self.build_tree()
        self.assertIn(code, (0, None), out)
        self.assertTrue((self.repo / "roadmap" / "roadmap.html").exists())

    def test_clean_tree_passes(self):
        code, out = self.build_tree()
        self.assertIn(code, (0, None), out)
        self.assertIn("upkeep:", out)


if __name__ == "__main__":
    unittest.main()
