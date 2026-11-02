"""Fixture suite for the roadmap builder. Run: python3 skills/roadmap/test_build.py

Each case builds a throwaway git repo: `main` holds the record homes, `roadmap` holds roadmap/data/.
"""
import contextlib
import datetime
import hashlib
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import shutil
import tempfile
import unittest

sys.dont_write_bytecode = True
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parent.parent / "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)
import build  # noqa: E402

# Made in setUpModule, not at import, so a helper that imports make_repo leaks no folder.
RUN_FOLDER = None

STEP = {"title": "t", "status": "todo", "phase": "cleanup", "order": 1, "note": "n", "updatedAt": "2026-10-26T00:00:00Z"}
CONFLICT = "<<<<<<< HEAD\na\n=======\nb\n>>>>>>> 1234567 (other)\n"
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}

# The page script the roadmap branch's build.py put in front of the viewer. The
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
# sha256 of the roadmap branch's roadmap/page/index.html, the page the old builder used.
TODAY_TEMPLATE_SHA256 = "b6451344f00bcc1ce27fe378de2cf5b3aaa610954d6ecb1dd8050677627160c6"
BLOCK = re.compile(r"<!-- build:([a-z-]+) -->.*?<!-- /build:\1 -->\n?", re.S)


def today_page(template, data):
    """What the roadmap branch's build.py wrote for this template and data."""
    head, sep, rest = template.partition("<body>")
    return head + sep + "\n" + TODAY_STUB % json.dumps(data, ensure_ascii=False).replace("</", "<\\/") + rest


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True,
                          env={**os.environ, **GIT_ENV}).stdout


def run_build_streams(*argv):
    """(code, stdout, stderr) of build.main(argv): 0 for a normal return, else the SystemExit code."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            build.main(list(argv))
            code = 0
        except SystemExit as e:
            code = e.code
    return code, out.getvalue(), err.getvalue()


def run_build(*argv):
    code, out, err = run_build_streams(*argv)
    return code, out + err


def build_info(page):
    found = re.search(r"window\.ROADMAP_BUILD = (.*?);\n</script>", page, re.S)
    return json.loads(found.group(1).replace("<\\/", "</"))


def iso_ago(minutes):
    """An ISO UTC time this many minutes before now (after it when negative), shaped as readAt."""
    when = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutes)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def session_row(sid, status, *tags):
    """One sessions row, as triage copies it from list_sessions."""
    return {"id": sid, "session_status": status, "tags": list(tags)}


def make_repo(root, steps=None, meta=None):
    """The one roadmap fixture repo, under `root`: `main` holds the record homes, `roadmap` holds
    roadmap/data/. Leaves HEAD on `roadmap`. `steps` and `meta` add files ({stem: JSON}) to its data."""
    repo = pathlib.Path(root) / "repo"
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
    data = repo / "roadmap" / "data"
    for folder in ("steps", "topics", "meta"):
        (data / folder).mkdir(parents=True)
    for stem, step in {"c1": STEP, **(steps or {})}.items():
        (data / "steps" / (stem + ".json")).write_text(json.dumps(step), encoding="utf-8")
    (data / "topics" / "t01.json").write_text(json.dumps({"title": "x", "order": 1}), encoding="utf-8")
    for stem, doc in {"cull": {"stopRule": "s"}, **(meta or {})}.items():
        (data / "meta" / (stem + ".json")).write_text(json.dumps(doc), encoding="utf-8")
    (repo / "briefs").mkdir()
    (repo / "briefs" / "c1.md").write_text("# c1\n\nA brief.\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "roadmap")
    return repo


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


class Fixture(unittest.TestCase):
    STEPS = None  # extra or replacement step files for make_repo, {stem: step}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=RUN_FOLDER)
        self.repo = make_repo(self.tmp.name, steps=self.STEPS)
        self.data = self.repo / "roadmap" / "data"
        self.out = pathlib.Path(self.tmp.name) / "page.html"
        self.live = pathlib.Path(self.tmp.name) / "live.json"

    def tearDown(self):
        self.tmp.cleanup()

    def write_step(self, sid, step):
        (self.data / "steps" / (sid + ".json")).write_text(json.dumps(step), encoding="utf-8")

    def on_main(self):
        git(self.repo, "checkout", "-q", "main")

    def build_from_main(self, *extra, expect=(0, None)):
        """(page, output) of a build from main. expect lists the exit codes the case accepts."""
        self.on_main()
        code, out = run_build("--repo", str(self.repo), "--out", str(self.out), *extra)
        self.assertIn(code, expect, out)
        return self.out.read_text(encoding="utf-8"), out

    def write_live(self, value):
        self.live.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")

    def panel(self, page, name="Live work"):
        return {p["name"]: p for p in build_info(page)["panels"]}[name]

    def use_origin(self, slug):
        """Point the fixture repo's origin at GitHub, so github_slug reads `slug`."""
        git(self.repo, "remote", "add", "origin", "git@github.com:%s.git" % slug)


class TodaysPage(Fixture):
    def test_page_equals_today_apart_from_the_build_blocks(self):
        page, _ = self.build_from_main()
        template = (HERE / "page" / "index.html").read_text(encoding="utf-8")
        data = {"steps": {"c1": STEP}, "topics": {"t01": {"title": "x", "order": 1}}, "meta": {"cull": {"stopRule": "s"}}}
        self.assertEqual(BLOCK.sub("", page), today_page(BLOCK.sub("", template), data))

    def test_template_outside_the_blocks_is_todays(self):
        template = (HERE / "page" / "index.html").read_text(encoding="utf-8")
        self.assertEqual(hashlib.sha256(BLOCK.sub("", template).encode("utf-8")).hexdigest(), TODAY_TEMPLATE_SHA256)

    def test_comment_opener_in_data_cannot_reach_the_page_script(self):
        self.write_step("c1", dict(STEP, note="<!-- <script> x"))
        git(self.repo, "commit", "-qam", "note")
        page, _ = self.build_from_main()
        self.assertNotIn("<!-- <script>", page)

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

    def test_todo_home_has_its_own_panel(self):
        page, _ = self.build_from_main()
        self.assertTrue(self.panels(page)["To-do"]["read"].startswith("unknown"))  # no docs/todo.md yet
        (self.repo / "docs").mkdir()
        (self.repo / "docs" / "todo.md").write_text("# To-do\n", encoding="utf-8")
        page, _ = self.build_from_main()
        self.assertEqual(self.panels(page)["To-do"]["home"], "docs/todo.md")

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


class StepTrailers(Fixture):
    """A merged lane commit with a `Step:` trailer marks its step "landed in #N" (lane 2)."""

    def setUp(self):
        super().setUp()
        self.write_step("c2", dict(STEP, order=2))
        self.write_step("c3", dict(STEP, order=3, status="done"))
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "more steps")
        self.on_main()
        git(self.repo, "checkout", "-q", "-b", "lane")
        for n, trailer in enumerate(("Step: c1", "Step: zz9", "Step: c3", "No-step: here")):
            (self.repo / ("f%d.txt" % n)).write_text("x", encoding="utf-8")
            git(self.repo, "add", "-A")
            git(self.repo, "commit", "-q", "-m", "lane %d\n\nBody.\n\n%s" % (n, trailer))
        git(self.repo, "checkout", "-q", "main")
        (self.repo / "other.txt").write_text("x", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "main moves on")
        git(self.repo, "merge", "-q", "--no-ff", "lane", "-m", "Merge pull request #7 from o/lane")

    def test_trailer_marks_only_its_open_step(self):
        page, _ = self.build_from_main()
        self.assertEqual(build_info(page)["landed"], {"c1": ["#7"]})

    def test_trailer_naming_no_step_is_listed(self):
        _, out = self.build_from_main()
        self.assertRegex(out, r"Step trailers naming no step: zz9 in [0-9a-f]{7} \(#7\)")
        self.assertRegex(out, r"landed, waiting for triage to close: c1 \(#7\)")

    def test_trailer_on_main_itself_names_its_commit(self):
        (self.repo / "direct.txt").write_text("x", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "direct (#9)\n\nStep: c2")
        page, _ = self.build_from_main()
        self.assertEqual(build_info(page)["landed"], {"c1": ["#7"], "c2": ["#9"]})

    def test_unmerged_lane_marks_nothing(self):
        git(self.repo, "reset", "-q", "--hard", "HEAD^1")
        page, _ = self.build_from_main()
        self.assertEqual(build_info(page)["landed"], {})


class RecordsAndHealth(Fixture):
    """Counts, newest five and the repo map (lane 3)."""

    def setUp(self):
        super().setUp()
        self.on_main()
        for n in range(7):
            (self.repo / "decisions" / ("d%d.md" % n)).write_text("# Decision %d\n" % n, encoding="utf-8")
            git(self.repo, "add", "-A")
            git(self.repo, "commit", "-q", "-m", "d%d" % n)
        (self.repo / "decisions" / ".hidden").write_text("x", encoding="utf-8")
        self.use_origin("owner/fixture")

    def records(self, page):
        return {r["kind"]: r for r in build_info(page)["records"]}

    def test_count_equals_ls(self):
        page, _ = self.build_from_main()
        ls = subprocess.run("ls | wc -l", shell=True, cwd=self.repo / "decisions", capture_output=True, text=True)
        self.assertEqual(self.records(page)["decisions"]["count"], int(ls.stdout))

    def test_newest_five_newest_first_with_links(self):
        page, _ = self.build_from_main()
        newest = self.records(page)["decisions"]["newest"]
        self.assertEqual([n["title"] for n in newest], ["Decision %d" % n for n in (6, 5, 4, 3, 2)])
        self.assertEqual(newest[0]["url"], "https://github.com/owner/fixture/blob/main/decisions/d6.md")

    def test_missing_home_count_is_unknown(self):
        page, _ = self.build_from_main()
        debts = self.records(page)["debts"]
        self.assertIsNone(debts["count"])
        self.assertTrue(debts["why"].startswith("unknown"))

    def test_uncommitted_entries_are_said_not_skipped(self):
        (self.repo / "decisions" / "loose.md").write_text("# Loose\n", encoding="utf-8")
        page, _ = self.build_from_main()
        row = self.records(page)["decisions"]
        self.assertEqual(row["count"], 9)
        self.assertIn("1 of 9 entries have no add commit", row["newestWhy"])
        panel = {p["name"]: p for p in build_info(page)["panels"]}["Decisions"]
        self.assertIn("not yet committed", panel["read"])

    def test_clean_home_stamp_has_no_edit_note(self):
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "hidden file")
        page, _ = self.build_from_main()
        panel = {p["name"]: p for p in build_info(page)["panels"]}["Decisions"]
        self.assertNotIn("not yet committed", panel["read"])

    def test_non_ascii_and_renamed_entries_are_dated(self):
        (self.repo / "decisions" / "é x.md").write_text("# Accent\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "accent")
        git(self.repo, "mv", "decisions/d0.md", "decisions/renamed.md")
        git(self.repo, "commit", "-q", "-m", "rename")
        page, _ = self.build_from_main()
        row = self.records(page)["decisions"]
        self.assertEqual([n["name"] for n in row["newest"][:2]], ["renamed.md", "é x.md"])
        self.assertIsNone(row["newestWhy"])
        self.assertIn("%C3%A9%20x.md", row["newest"][1]["url"])

    def test_a_home_that_is_a_file_has_no_count(self):
        (self.repo / "plans").write_text("x", encoding="utf-8")
        page, _ = self.build_from_main()
        row = self.records(page)["plans"]
        self.assertIsNone(row["count"])
        self.assertIn("not a folder", row["why"])

    def test_shallow_clone_newest_reads_unknown(self):
        clone = pathlib.Path(self.tmp.name) / "shallow"
        subprocess.run(["git", "clone", "-q", "--depth", "1", "--branch", "main", self.repo.as_uri(), str(clone)], check=True)
        code, out = run_build("--repo", str(clone), "--out", str(self.out))
        self.assertIn(code, (0, None), out)
        row = self.records(self.out.read_text(encoding="utf-8"))["decisions"]
        self.assertEqual(row["count"], 8)
        self.assertEqual(row["newest"], [])
        self.assertTrue(row["newestWhy"].startswith("unknown"))

    def health(self, page):
        return {h["name"]: h for h in build_info(page)["health"]}

    def test_map_unknown_without_an_extras_file(self):
        page, _ = self.build_from_main()
        self.assertTrue(self.health(page)["Repo map"]["read"].startswith("unknown"))

    def test_map_from_the_record_branch_extras(self):
        (self.repo / "MAP.md").write_text("# map\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "map")
        git(self.repo, "checkout", "-q", "roadmap")
        (self.repo / "roadmap" / "extras.json").write_text(json.dumps({"map": "MAP.md"}), encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "extras")
        page, _ = self.build_from_main()
        repo_map = self.health(page)["Repo map"]
        self.assertEqual(repo_map["home"], "MAP.md")
        self.assertEqual(repo_map["read"], git(self.repo, "log", "-1", "--format=%h", "--", "MAP.md").strip())

    def test_map_from_the_layout_extras_without_the_rolled_out_mark(self):
        (self.repo / "MAP.md").write_text("# map\n", encoding="utf-8")
        (self.repo / ".claude").mkdir(exist_ok=True)
        (self.repo / ".claude" / "layout-extras.json").write_text(
            json.dumps({"kinds": {}, "roadmap": {"map": "MAP.md"}}), encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "map and extras")
        page, _ = self.build_from_main()
        self.assertEqual(self.health(page)["Repo map"]["home"], "MAP.md")

    def test_compliance_and_session_board_say_why_unknown(self):
        page, _ = self.build_from_main()
        health = self.health(page)
        self.assertIn("unknown", health["Compliance scores"]["read"])
        self.assertIn("one machine", health["Session board"]["read"])


class LiveWork(Fixture):
    """Live work from the publisher's file: project threads and GitHub (lane 5, option a)."""

    def setUp(self):
        super().setUp()
        self.write_step("c2", dict(STEP, order=2, status="done"))
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "done step")

    def test_no_live_file_reads_unknown(self):
        page, _ = self.build_from_main()
        self.assertTrue(self.panel(page)["read"].startswith("unknown (no --live file"))
        self.assertNotIn("threads", build_info(page)["live"])

    def test_threads_and_pulls_are_baked_in_waiting_first(self):
        self.write_live({"readAt": "2026-10-26T21:00:00Z",
                         "threads": [{"title": "Build a", "state": "working", "step": "c1"},
                                     {"title": "Ask b", "state": "blocked"},
                                     {"title": "Old c", "state": "done"}],
                         "pulls": [{"number": 9, "title": "nine"}, {"number": 3, "title": "three", "draft": True}],
                         "branches": [{"name": "lane-x"}]})
        page, out = self.build_from_main("--live", str(self.live))
        live = build_info(page)["live"]
        self.assertEqual(self.panel(page)["read"], "2026-10-26T21:00:00Z")
        self.assertEqual([t["title"] for t in live["threads"]], ["Ask b", "Build a", "Old c"])
        self.assertEqual([p["number"] for p in live["pulls"]], [3, 9])
        self.assertEqual(live["branches"], [{"name": "lane-x"}])
        self.assertEqual((live["skipped"], live["strays"]), ([], []))
        self.assertIn("live threads naming no open step: 0", out)

    def test_wrong_shape_entries_are_counted_not_dropped(self):
        self.write_live({"readAt": "2026-10-26T21:00:00Z",
                         "threads": [{"title": "ok", "state": "working"}, {"title": "bad", "state": "asleep"},
                                     {"title": "bad step", "state": "working", "step": ["c1"]}, "x"],
                         "pulls": [{"number": "7", "title": "s"}], "branches": "lane"})
        page, out = self.build_from_main("--live", str(self.live))
        live = build_info(page)["live"]
        self.assertEqual([t["title"] for t in live["threads"]], ["ok"])
        self.assertEqual(live["skipped"], ["thread 2", "thread 3", "thread 4", "pull 1", "branch (not a list)"])
        self.assertIn("live file entries skipped: thread 2, thread 3, thread 4, pull 1, branch (not a list)", out)

    def test_thread_naming_a_missing_or_done_step_is_listed(self):
        self.write_live({"readAt": "2026-10-26T21:00:00Z",
                         "threads": [{"title": "A", "state": "working", "step": "zz9"},
                                     {"title": "B", "state": "working", "step": "c2"},
                                     {"title": "C", "state": "working", "step": "c1"}], "pulls": []})
        _, out = self.build_from_main("--live", str(self.live))
        self.assertIn("live threads naming no open step: zz9 (A), c2 (B)", out)

    def test_unreadable_live_file_reads_unknown(self):
        self.write_live("{not json")
        page, _ = self.build_from_main("--live", str(self.live))
        self.assertTrue(self.panel(page)["read"].startswith("unknown (the live file could not be read"))

    def test_missing_read_at_reads_unknown(self):
        self.write_live({"threads": [], "pulls": []})
        page, _ = self.build_from_main("--live", str(self.live))
        self.assertEqual(self.panel(page)["read"], "unknown (the live file's readAt is not an ISO time: None)")

    def test_missing_threads_or_pulls_list_reads_unknown(self):
        self.write_live({"readAt": "2026-10-26T21:00:00Z", "threads": []})
        page, _ = self.build_from_main("--live", str(self.live))
        self.assertEqual(self.panel(page)["read"], "unknown (the live file has no pulls list)")
        self.assertNotIn("threads", build_info(page)["live"])
        self.write_live({"readAt": "2026-10-26T21:00:00Z", "threads": None, "pulls": {}})
        page, _ = self.build_from_main("--live", str(self.live))
        self.assertEqual(self.panel(page)["read"], "unknown (the live file has no threads or pulls list)")

    def test_read_at_that_is_not_a_time_reads_unknown(self):
        self.write_live({"readAt": "yesterday", "threads": [], "pulls": []})
        page, _ = self.build_from_main("--live", str(self.live))
        self.assertTrue(self.panel(page)["read"].startswith("unknown (the live file's readAt is not an ISO time"))

    def test_a_true_pull_number_is_skipped(self):
        self.write_live({"readAt": "2026-10-26T21:00:00Z", "threads": [], "pulls": [{"number": True, "title": "t"}]})
        page, _ = self.build_from_main("--live", str(self.live))
        self.assertEqual(build_info(page)["live"]["skipped"], ["pull 1"])

    def test_unread_steps_make_strays_unknown_not_listed(self):
        self.assertEqual(build.live_work(None, None)["read"][:7], "unknown")
        self.write_live({"readAt": "2026-10-26T21:00:00Z", "threads": [{"title": "A", "state": "working", "step": "c1"}],
                         "pulls": []})
        self.assertEqual(build.live_work(str(self.live), None)["strays"], ["unknown (the steps could not be read)"])

    def test_markup_in_a_thread_title_cannot_reach_the_page_script(self):
        self.write_live({"readAt": "x", "threads": [{"title": "</script><!-- y", "state": "working"}], "pulls": []})
        page, _ = self.build_from_main("--live", str(self.live))
        self.assertNotIn("</script><!--", page)


class UpkeepFixture(Fixture):
    """The one home of the upkeep helpers: a fixture repo whose GitHub name is set, steps committed on the
    record branch, a --live file, and a reader of the upkeep rows. Each upkeep class extends it."""

    SLUG = "owner/fixture"
    REPO = "cs-repo:" + SLUG

    def setUp(self):
        super().setUp()
        self.use_origin(self.SLUG)

    def commit_step(self, sid, **fields):
        """Write a step on the record branch and commit it, where a build from main reads it."""
        self.write_step(sid, dict(STEP, **fields))
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "step " + sid)

    def publish(self, sessions=None, pulls=(), threads=(), read_at=None):
        """Write the --live file. The sessions key appears only when given. readAt is five minutes old by default."""
        value = {"readAt": read_at or iso_ago(5), "threads": list(threads), "pulls": list(pulls)}
        if sessions is not None:
            value["sessions"] = list(sessions)
        self.write_live(value)
        return value

    def out_with_live(self):
        _, out = self.build_from_main("--live", str(self.live))
        return out

    def summary_counts(self, out):
        """{row label: count} in the order the upkeep line prints them. Fails when the output has no upkeep line."""
        line = re.search(r"^upkeep: (.*)$", out, re.M)
        if line is None:
            self.fail("the output has no upkeep line:\n%s" % out)
        return {seg.rsplit(": ", 1)[0]: int(seg.rsplit(": ", 1)[1]) for seg in line.group(1).split("; ")}

    def row(self, out, label):
        """(count, detail) of one upkeep row. The detail is "" when the row prints no line. Fails when the row is absent."""
        counts = self.summary_counts(out)
        if label not in counts:
            self.fail("the upkeep output has no %r row:\n%s" % (label, out))
        detail = re.search(r"^  %s: (.*)$" % re.escape(label), out, re.M)
        return counts[label], (detail.group(1) if detail else "")

    def entries(self, detail):
        """The entries of a row's detail, sorted. The builder orders them by step id, which no case relies on."""
        return sorted(detail.split(", ")) if detail else []

    # The Nov 1 replay (spec "Red first"): a todo step, `Ready.` in its note, with a draft PR on its branch,
    # created 12 h 16 m before the live read, and no live session for the step.
    REPLAY = "feedback-repeat-detect"
    REPLAY_TITLE = "Feedback guard flags a new item that repeats older feedback"

    def commit_replay_step(self):
        self.commit_step(self.REPLAY, title="Feedback repeat detect", note="Brief is written. Ready.")

    def replay_pull(self):
        return self.draft(999, self.REPLAY, self.created_before(736), self.REPLAY_TITLE)

    def draft(self, number, branch, created=None, title=None):
        """An open draft pull row. The createdAt key is left out when created is None."""
        row = {"number": number, "title": title or "lane " + branch, "branch": branch, "draft": True}
        if created is not None:
            row["createdAt"] = created
        return row

    def created_before(self, minutes, read_ago=5):
        """An ISO createdAt `minutes` before the live read, when that read was read_ago minutes before now."""
        return iso_ago(read_ago + minutes)


class StaleInProgress(UpkeepFixture):
    """The upkeep row for each doing or active step with no live lane and no open PR. Its entries read
    `<id> (set to todo)`, `<id> (set to done: landed in #N)`, or one `unknown (<why>)` when unreadable."""

    ROW = "in progress with no live lane or open PR"

    def session_in_repo(self, sid, status, *tags):
        """A sessions row for this fixture repo, carrying the cs-repo tag the builder checks."""
        return session_row(sid, status, self.REPO, *tags)

    def stale(self, out):
        """(count, entries) of the stale row. Fails when the output holds no such row."""
        return self.row(out, self.ROW)

    def listed_ids(self, entries):
        return re.findall(r"([^,()\s]+) \(set to ", entries)

    def test_doing_step_with_a_live_session_is_not_listed(self):
        self.commit_step("c1", status="doing")
        self.commit_step("c2", status="doing", order=2)  # no session, so it is listed and an empty row cannot pass
        for status in ("SESSION_STATUS_RUNNING", "SESSION_STATUS_IDLE",
                       "SESSION_STATUS_REQUIRES_ACTION", "SESSION_STATUS_PENDING"):
            with self.subTest(status=status):
                self.publish(sessions=[self.session_in_repo("session_test01", status, "cs-step:c1")])
                count, entries = self.stale(self.out_with_live())
                self.assertEqual((count, self.listed_ids(entries)), (1, ["c2"]))

    def test_doing_step_whose_id_is_an_open_pull_branch_is_not_listed(self):
        self.commit_step("c1", status="doing")
        self.commit_step("c2", status="doing", order=2)  # control: listed
        self.publish(sessions=[], pulls=[{"number": 874, "title": "Lane c1", "branch": "c1"}])
        count, entries = self.stale(self.out_with_live())
        self.assertEqual((count, self.listed_ids(entries)), (1, ["c2"]))

    def test_doing_and_active_steps_with_neither_are_set_to_todo(self):
        self.commit_step("c1", status="doing")
        self.commit_step("c2", status="active", order=2)
        self.publish(sessions=[])
        count, entries = self.stale(self.out_with_live())
        self.assertEqual(count, 2)
        self.assertIn("c1 (set to todo)", entries)
        self.assertIn("c2 (set to todo)", entries)

    def test_archived_session_does_not_keep_its_step_live(self):
        self.commit_step("c1", status="doing")
        self.publish(sessions=[self.session_in_repo("session_test01", "SESSION_STATUS_ARCHIVED", "cs-step:c1")])
        self.assertEqual(self.stale(self.out_with_live()), (1, "c1 (set to todo)"))

    def test_step_page_does_not_match_tag_or_branch_page_name_queue(self):
        self.commit_step("page", status="doing", note="Lane page-name-queue: draft PR #874")
        self.publish(sessions=[self.session_in_repo("session_test01", "SESSION_STATUS_RUNNING", "cs-step:page-name-queue")],
                     pulls=[{"number": 874, "title": "Page name queue", "branch": "page-name-queue"}])
        self.assertEqual(self.stale(self.out_with_live()), (1, "page (set to todo)"))

    def test_step_trailer_on_main_sets_the_step_to_done(self):
        self.commit_step("c1", status="doing")
        self.on_main()
        (self.repo / "landed.txt").write_text("x", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "landed (#12)\n\nStep: c1")
        self.publish(sessions=[])
        self.assertEqual(self.stale(self.out_with_live()), (1, "c1 (set to done: landed in #12)"))

    def test_live_file_with_no_sessions_list_reads_the_row_unknown(self):
        self.commit_step("c1", status="doing")
        value = self.publish(threads=[{"title": "Build a", "state": "working", "step": "c1"}],
                             pulls=[{"number": 9, "title": "nine"}])
        page, out = self.build_from_main("--live", str(self.live))
        self.assertEqual(self.stale(out), (1, "unknown (the live file has no sessions list)"))
        self.assertEqual(self.panel(page)["read"], value["readAt"])
        live = build_info(page)["live"]
        self.assertEqual([t["title"] for t in live["threads"]], ["Build a"])
        self.assertEqual([p["number"] for p in live["pulls"]], [9])

    def test_read_at_two_hours_old_reads_the_row_unknown(self):
        self.commit_step("c1", status="doing")
        value = self.publish(sessions=[], read_at=iso_ago(120))
        page, out = self.build_from_main("--live", str(self.live))
        count, entries = self.stale(out)
        found = re.fullmatch(r"unknown \(the live file was read (\d+) minutes ago; read it again\)", entries)
        self.assertEqual(count, 1)
        self.assertIsNotNone(found, entries)
        self.assertIn(int(found.group(1)), range(119, 122))
        self.assertEqual(self.panel(page)["read"], value["readAt"])

    def test_read_at_five_minutes_old_lists_normally(self):
        self.commit_step("c1", status="doing")
        self.publish(sessions=[])
        self.assertEqual(self.stale(self.out_with_live()), (1, "c1 (set to todo)"))

    def test_read_at_that_is_not_a_time_reads_the_row_unknown(self):
        self.commit_step("c1", status="doing")
        self.publish(sessions=[], read_at="yesterday")
        count, entries = self.stale(self.out_with_live())
        self.assertEqual(count, 1)
        self.assertTrue(entries.startswith("unknown ("), entries)

    def test_malformed_session_rows_are_skipped_named_and_read_the_row_unknown(self):
        self.commit_step("c1", status="doing")
        self.publish(sessions=[self.session_in_repo("session_test01", "SESSION_STATUS_RUNNING", "cs-step:c1"),
                               {"id": "session_test02", "session_status": "SESSION_STATUS_RUNNING", "tags": "cs-step:c2"},
                               "session_test03"])
        page, out = self.build_from_main("--live", str(self.live))
        skipped = build_info(page)["live"]["skipped"]
        self.assertNotIn("session 1", skipped)
        self.assertIn("session 2", skipped)
        self.assertIn("session 3", skipped)
        self.assertRegex(out, r"live file entries skipped: .*session 2")
        self.assertEqual(self.stale(out), (1, "unknown (2 session rows skipped)"))

    def test_todo_and_done_steps_are_never_listed(self):
        self.commit_step("c2", status="done", order=2)
        self.commit_step("c3", status="todo", order=3)
        self.commit_step("c4", status="doing", order=4)  # control: listed, so an empty row cannot pass
        self.publish(sessions=[])
        self.assertEqual(self.stale(self.out_with_live()), (1, "c4 (set to todo)"))

    def test_no_live_file_reads_the_row_unknown(self):
        self.commit_step("c1", status="doing")
        _, out = self.build_from_main()
        count, entries = self.stale(out)
        self.assertEqual(count, 1)
        self.assertTrue(entries.startswith("unknown (") and "--live" in entries, entries)

    def test_unreadable_live_file_reads_the_row_unknown(self):
        self.commit_step("c1", status="doing")
        self.write_live("{not json")
        count, entries = self.stale(self.out_with_live())
        self.assertEqual(count, 1)
        self.assertTrue(entries.startswith("unknown ("), entries)

    def test_read_at_more_than_five_minutes_ahead_reads_the_row_unknown(self):
        self.commit_step("c1", status="doing")
        self.publish(sessions=[], read_at=iso_ago(-10))
        self.assertEqual(self.stale(self.out_with_live()), (1, "unknown (the live file's readAt is in the future)"))
        with self.subTest("two minutes ahead is within the tolerance"):
            self.publish(sessions=[], read_at=iso_ago(-2))
            self.assertEqual(self.stale(self.out_with_live()), (1, "c1 (set to todo)"))

    # Only archived ends a lane (session-tiers, Live-coordinator check), so an unseen status keeps its step live.
    def test_session_in_an_unseen_status_keeps_its_step_live(self):
        self.commit_step("c1", status="doing")
        self.commit_step("c2", status="doing", order=2)  # control: listed
        self.publish(sessions=[self.session_in_repo("session_test01", "SESSION_STATUS_SOMETHING_NEW", "cs-step:c1")])
        count, entries = self.stale(self.out_with_live())
        self.assertEqual((count, self.listed_ids(entries)), (1, ["c2"]))

    def test_session_counts_only_with_this_repos_cs_repo_tag(self):
        self.commit_step("c1", status="doing")
        self.commit_step("c2", status="doing", order=2)  # control: listed
        rows = {
            "this repo's tag keeps c1 live": (session_row("session_test01", "SESSION_STATUS_RUNNING",
                                                          self.REPO, "cs-step:c1"), ["c2"]),
            "no cs-repo tag leaves c1 listed": (session_row("session_test01", "SESSION_STATUS_RUNNING",
                                                            "cs-step:c1"), ["c1", "c2"]),
            "another repo's tag leaves c1 listed": (session_row("session_test01", "SESSION_STATUS_RUNNING",
                                                                "cs-repo:other/repo", "cs-step:c1"), ["c1", "c2"]),
        }
        for name, (row, listed) in rows.items():
            with self.subTest(name):
                self.publish(sessions=[row])
                count, entries = self.stale(self.out_with_live())
                self.assertEqual((count, sorted(self.listed_ids(entries))), (len(listed), listed))
        git(self.repo, "remote", "remove", "origin")
        self.publish(sessions=[self.session_in_repo("session_test01", "SESSION_STATUS_RUNNING", "cs-step:c1")])
        self.assertEqual(self.stale(self.out_with_live()),
                         (1, "unknown (the repo's GitHub name could not be read)"))

    def test_skipped_pull_rows_make_the_row_unknown(self):
        self.commit_step("c1", status="doing")
        self.publish(sessions=[], pulls=[{"number": 9, "title": "ok"}, {"number": "10", "title": "bad number"},
                                         {"number": 11}])
        self.assertEqual(self.stale(self.out_with_live()), (1, "unknown (2 pull rows skipped)"))

    def test_open_step_with_an_unknown_status_is_listed_with_that_status(self):
        self.commit_step("c1", status="waiting")
        self.commit_step("c2", status="doing", order=2)  # control: listed as todo
        self.publish(sessions=[])
        count, entries = self.stale(self.out_with_live())
        self.assertEqual(count, 2)
        self.assertIn('c1 (unknown status "waiting")', entries)
        self.assertIn("c2 (set to todo)", entries)


    def test_session_without_tags_or_with_null_tags_is_tagless_not_skipped(self):
        self.commit_step("c1", status="doing")
        self.commit_step("c2", status="doing", order=2)  # control: listed
        tagless = [{"id": "session_test02", "session_status": "SESSION_STATUS_IDLE"},
                   {"id": "session_test03", "session_status": "SESSION_STATUS_RUNNING", "tags": None}]
        self.publish(sessions=[self.session_in_repo("session_test01", "SESSION_STATUS_RUNNING", "cs-step:c1")] + tagless)
        page, out = self.build_from_main("--live", str(self.live))
        self.assertEqual(build_info(page)["live"]["skipped"], [])
        self.assertEqual(self.stale(out), (1, "c2 (set to todo)"))
        with self.subTest("a tags string is still skipped"):
            self.publish(sessions=[self.session_in_repo("session_test01", "SESSION_STATUS_RUNNING", "cs-step:c1"),
                                   {"id": "session_test04", "session_status": "SESSION_STATUS_RUNNING", "tags": "cs-step:c1"}])
            page, out = self.build_from_main("--live", str(self.live))
            self.assertEqual(build_info(page)["live"]["skipped"], ["session 2"])
            self.assertEqual(self.stale(out), (1, "unknown (1 session rows skipped)"))

    def test_repo_tag_compares_without_case(self):
        self.commit_step("c1", status="doing")
        self.commit_step("c2", status="doing", order=2)  # control: listed
        self.publish(sessions=[session_row("session_test01", "SESSION_STATUS_RUNNING", "cs-repo:Owner/Fixture", "cs-step:c1")])
        self.assertEqual(self.stale(self.out_with_live()), (1, "c2 (set to todo)"))


OPEN, CLOSE = "<!-- roadmap:data -->", "<!-- /roadmap:data -->"


class FeelRows(UpkeepFixture):
    """The feel-fix rows of the upkeep list (spec feel-fix-needs-device-check, part A). A feel-fix is a step whose
    `feel` is anything but absent, false or null. A landed feel-fix with no valid `deviceCheck` is listed in the
    device row. With a valid check it reads the try-it suffix in the triage row. The triage row drops the device
    row's steps, and the in-progress row skips a feel-fix that has no valid check."""

    DEVICE = "landed, waiting for a device trial"
    TRIAGE = "landed, waiting for triage to close"
    UNLANED = StaleInProgress.ROW
    CHECK = {"how": "simulator", "at": "2026-11-01T11:44:00-06:00"}
    NOT_FEEL = {"absent": {}, "json-false": {"feel": False}, "json-null": {"feel": None}}
    OTHER_FEEL = {"true": {"feel": True}, "yes": {"feel": "yes"}, "zero": {"feel": 0}, "empty-text": {"feel": ""},
                  "empty-list": {"feel": []}, "empty-object": {"feel": {}}, "text-false": {"feel": "false"}}
    INVALID_CHECKS = {
        "bad-how": {"how": "phone", "at": "2026-11-01T11:44:00-06:00"},
        "no-zone": {"how": "device", "at": "2026-11-01T11:44:00"},
        "not-a-time": {"how": "device", "at": "yesterday"},
        "no-at": {"how": "device"},
        "no-how": {"at": "2026-11-01T11:44:00-06:00"},
        "text": "simulator",
        "list": ["simulator", "2026-11-01T11:44:00-06:00"],
    }

    def land(self, sid, pr, **fields):
        """Write the step on the record branch, then land it on main as a merged PR's commit with a Step: trailer.
        The step is doing unless the case says otherwise."""
        fields.setdefault("status", "doing")
        git(self.repo, "checkout", "-q", "roadmap")
        self.commit_step(sid, **fields)
        self.on_main()
        (self.repo / ("landed-%s-%d.txt" % (sid, pr))).write_text("x", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "landed (#%d)\n\nStep: %s" % (pr, sid))

    def land_all(self, specs, first_pr):
        """Land each step in specs ({step id: fields}), one PR each from first_pr. Returns {step id: PR number}."""
        prs = {}
        for pr, (sid, fields) in enumerate(specs.items(), start=first_pr):
            self.land(sid, pr, **fields)
            prs[sid] = pr
        return prs

    def build_live(self):
        """(page, out) of a build from main, with a live file that lists no sessions."""
        self.publish(sessions=[])
        return self.build_from_main("--live", str(self.live))

    def test_landed_feel_fix_without_a_check_is_listed_in_the_device_row(self):
        self.land("c1", 12, feel=True)
        _, out = self.build_live()
        self.assertEqual(self.row(out, self.DEVICE), (1, "c1 (#12)"))
        self.assertEqual(self.row(out, self.TRIAGE), (0, ""))

    def test_device_row_sits_just_before_the_triage_row(self):
        self.land("c1", 12, feel=True)
        _, out = self.build_live()
        labels = list(self.summary_counts(out))
        self.assertIn(self.DEVICE, labels)
        self.assertEqual(labels[labels.index(self.DEVICE) + 1], self.TRIAGE)

    def test_device_row_joins_every_mark_with_a_comma(self):
        self.land("c1", 12, feel=True)
        self.land("c1", 13, feel=True, note="second landing")
        _, out = self.build_live()
        self.assertEqual(self.row(out, self.DEVICE), (1, "c1 (#12, #13)"))

    def test_landed_feel_fix_with_a_valid_check_reads_the_try_it_suffix(self):
        self.land_all({"sim": {"feel": True, "deviceCheck": self.CHECK},
                       "dev": {"feel": True, "deviceCheck": dict(self.CHECK, how="device")}}, 12)
        _, out = self.build_live()
        count, detail = self.row(out, self.TRIAGE)
        self.assertEqual((count, self.entries(detail)),
                         (2, ["dev (#13; open a try-it item)", "sim (#12; open a try-it item)"]))
        self.assertEqual(self.row(out, self.DEVICE), (0, ""))

    def test_present_but_invalid_device_check_reads_unreadable(self):
        prs = self.land_all({sid: {"feel": True, "deviceCheck": check} for sid, check in self.INVALID_CHECKS.items()}, 20)
        _, out = self.build_live()
        want = sorted("%s (#%d; device trial unreadable)" % (sid, pr) for sid, pr in prs.items())
        count, detail = self.row(out, self.DEVICE)
        self.assertEqual((count, self.entries(detail)), (len(want), want))
        self.assertEqual(self.row(out, self.TRIAGE), (0, ""))
        self.assertEqual(self.row(out, self.UNLANED)[0], 0)

    def test_absent_false_or_null_is_not_a_feel_fix(self):
        prs = self.land_all(self.NOT_FEEL, 30)
        _, out = self.build_live()
        self.assertEqual(self.row(out, self.DEVICE), (0, ""))
        want = sorted("%s (#%d)" % (sid, pr) for sid, pr in prs.items())
        count, detail = self.row(out, self.TRIAGE)
        self.assertEqual((count, self.entries(detail)), (len(want), want))
        # control: a step that is not a feel-fix is still listed as set to done
        want_done = sorted("%s (set to done: landed in #%d)" % (sid, pr) for sid, pr in prs.items())
        count, detail = self.row(out, self.UNLANED)
        self.assertEqual((count, self.entries(detail)), (len(want_done), want_done))

    def test_other_feel_values_are_feel_fixes(self):
        prs = self.land_all(self.OTHER_FEEL, 40)
        _, out = self.build_live()
        want = sorted("%s (#%d)" % (sid, pr) for sid, pr in prs.items())
        count, detail = self.row(out, self.DEVICE)
        self.assertEqual((count, self.entries(detail)), (len(want), want))
        self.assertEqual(self.row(out, self.TRIAGE), (0, ""))
        self.assertEqual(self.row(out, self.UNLANED)[0], 0)

    def test_landed_feel_fix_without_a_check_is_not_listed_as_set_to_done(self):
        self.land("c1", 12, feel=True)  # doing, no check: the device row lists it instead
        self.land("c2", 13, order=2)  # control: a plain landed step is still listed
        self.land("c3", 14, order=3, status="active", feel=True)  # active counts the same as doing
        _, out = self.build_live()
        self.assertEqual(self.row(out, self.UNLANED), (1, "c2 (set to done: landed in #13)"))

    def test_landed_feel_fix_with_a_valid_check_is_still_listed_as_set_to_done(self):
        self.land("c1", 12, feel=True, deviceCheck=self.CHECK)
        _, out = self.build_live()
        self.assertEqual(self.row(out, self.UNLANED), (1, "c1 (set to done: landed in #12)"))

    def test_feel_fix_not_yet_landed_still_reads_set_to_todo(self):
        git(self.repo, "checkout", "-q", "roadmap")
        self.commit_step("c1", status="doing", feel=True)
        _, out = self.build_live()
        self.assertEqual(self.row(out, self.UNLANED), (1, "c1 (set to todo)"))


class TodoWithOpenPull(UpkeepFixture):
    """The pair line of the build (spec part A). A pull names a step when its branch is the step id, or its title
    holds the id as a whole token. Each named todo step prints one line, and the build exits 1 after it writes the
    page. With no live read, the build prints one unknown line and exits 0."""

    PAIR = "todo step with an open PR"

    def pair_lines(self, out):
        return re.findall(r"^%s: (.*)$" % re.escape(self.PAIR), out, re.M)

    def test_replay_build_goes_red_naming_the_step_and_its_pull(self):
        self.commit_replay_step()
        self.publish(sessions=[], pulls=[self.replay_pull()])
        _, out = self.build_from_main("--live", str(self.live), expect=(1,))
        self.assertEqual(self.pair_lines(out), ["feedback-repeat-detect (#999)"])

    def test_red_build_writes_the_page_before_it_exits_1(self):
        self.commit_replay_step()
        self.publish(sessions=[], pulls=[self.replay_pull()])
        page, _ = self.build_from_main("--live", str(self.live), expect=(1,))
        self.assertIn("Feedback repeat detect", page)

    def test_live_file_with_no_sessions_list_still_goes_red_on_the_pair(self):
        # The pair gate reads readAt and pulls only. publish() leaves the sessions key out, so the gate must not need it.
        self.commit_step("r7")
        self.publish(pulls=[{"number": 70, "title": "r7 lane", "branch": "r7"}])
        _, out = self.build_from_main("--live", str(self.live), expect=(1,))
        self.assertEqual(self.pair_lines(out), ["r7 (#70)"])

    def test_title_token_names_the_step(self):
        self.commit_step("r5")
        self.publish(sessions=[], pulls=[{"number": 50, "title": "r5: fix x", "branch": "lane-q"}])
        _, out = self.build_from_main("--live", str(self.live), expect=(1,))
        self.assertEqual(self.pair_lines(out), ["r5 (#50)"])

    def test_short_slug_inside_a_longer_word_does_not_name_the_step(self):
        # r6 is the control: it is named, so an empty list of lines cannot pass.
        self.commit_step("r5")
        self.commit_step("r6", order=2)
        self.publish(sessions=[], pulls=[{"number": 40, "title": "pr5 cleanup", "branch": "c91-r5x"},
                                         {"number": 41, "title": "r6 lane", "branch": "r6"}])
        _, out = self.build_from_main("--live", str(self.live), expect=(1,))
        self.assertEqual(self.pair_lines(out), ["r6 (#41)"])

    def test_no_live_file_reads_the_pair_line_unknown_and_exits_0(self):
        _, out = self.build_from_main()
        lines = self.pair_lines(out)
        self.assertEqual(len(lines), 1, out)
        self.assertTrue(lines[0].startswith("unknown (") and "--live" in lines[0], lines)

    def test_stale_live_read_reads_the_pair_line_unknown_and_exits_0(self):
        self.publish(sessions=[], read_at=iso_ago(120))
        _, out = self.build_from_main("--live", str(self.live))
        lines = self.pair_lines(out)
        self.assertEqual(len(lines), 1, out)
        self.assertRegex(lines[0], r"^unknown \(the live file was read \d+ minutes ago")


class ReadyAndDraftRows(UpkeepFixture):
    """Two upkeep rows (spec part B). `ready todo steps` lists each todo step whose note has the sentence `Ready.`,
    with no gate on live phases. `draft PRs over 12 h with no live lane` lists each draft pull created more than
    12 h before the live read, when no live session names its step. An entry reads `#<number> (<branch or title>)`,
    or `unknown (#<number> has no createdAt)` when its createdAt is missing or not an ISO time with a zone."""

    READY = "ready todo steps"
    DRAFT = "draft PRs over 12 h with no live lane"

    def test_replay_lists_the_ready_step_and_the_stale_draft(self):
        self.commit_replay_step()
        self.publish(sessions=[], pulls=[self.replay_pull()])
        _, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        self.assertEqual(self.row(out, self.READY), (1, self.REPLAY))
        self.assertEqual(self.row(out, self.DRAFT), (1, "#999 (%s)" % self.REPLAY))

    def test_ready_sentence_must_stand_alone(self):
        # r-start and r-mid hold the sentence. r-already has no break before Ready., and r-glued has none after it.
        notes = {"r-start": "Ready.", "r-mid": "Brief is written. Ready. Go on.",
                 "r-already": "Already Ready.", "r-glued": "Ready.x"}
        for order, (sid, note) in enumerate(notes.items(), start=2):
            self.commit_step(sid, note=note, order=order)
        _, out = self.build_from_main()
        count, detail = self.row(out, self.READY)
        self.assertEqual((count, self.entries(detail)), (2, ["r-mid", "r-start"]))

    def test_only_todo_steps_are_listed_as_ready(self):
        self.commit_step("t-todo", note="Ready.", order=2)  # control: listed
        self.commit_step("d-doing", status="doing", note="Ready.", order=3)
        self.commit_step("d-done", status="done", note="Ready.", order=4)
        _, out = self.build_from_main()
        count, detail = self.row(out, self.READY)
        self.assertEqual((count, self.entries(detail)), (1, ["t-todo"]))

    def test_draft_under_twelve_hours_before_the_read_is_not_listed(self):
        # The read is 45 min old. A draft 11 h 30 m before it is 12 h 15 m before now, so a check against the
        # wall clock would list it. lone-draft is the control: 13 h before the read.
        self.publish(sessions=[], read_at=iso_ago(45), pulls=[
            self.draft(1000, "late-eleven", self.created_before(690, read_ago=45)),
            self.draft(1001, "lone-draft", self.created_before(780, read_ago=45))])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual((count, self.entries(detail)), (1, ["#1001 (lone-draft)"]))

    def test_draft_with_a_live_lane_is_not_listed(self):
        # c1 is doing, so the pair line stays quiet. Its live session carries this repo's tag and the step's tag.
        self.commit_step("c1", status="doing")
        self.publish(sessions=[session_row("session_test01", "SESSION_STATUS_RUNNING", self.REPO, "cs-step:c1")],
                     pulls=[self.draft(1001, "c1", self.created_before(780)),
                            self.draft(1002, "lone-draft", self.created_before(780))])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual((count, self.entries(detail)), (1, ["#1002 (lone-draft)"]))

    def test_draft_whose_title_holds_a_live_step_id_is_still_listed(self):
        # Only the draft's branch can lane it. The title "Follow-up for c91" holds the live step c91 and stays listed.
        # c91 is the control: its branch is the step, so it is laned.
        self.publish(sessions=[session_row("session_test01", "SESSION_STATUS_RUNNING", self.REPO, "cs-step:c91")],
                     pulls=[self.draft(1001, "c91-cleanup", self.created_before(780), "Follow-up for c91"),
                            self.draft(1002, "c91", self.created_before(780))])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual((count, self.entries(detail)), (1, ["#1001 (c91-cleanup)"]))

    def test_empty_step_tag_names_no_draft(self):
        # An empty step id names nothing, so the title "a: b" does not lane this draft.
        self.publish(sessions=[session_row("session_test01", "SESSION_STATUS_RUNNING", self.REPO, "cs-step:")],
                     pulls=[self.draft(1001, "lone-draft", self.created_before(780), "a: b")])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual((count, self.entries(detail)), (1, ["#1001 (lone-draft)"]))

    def test_draft_without_a_usable_created_at_reads_its_entry_unknown(self):
        bad = {"missing": None, "no zone": "2026-11-02T01:14:22", "not a time": "yesterday"}
        for name, created in bad.items():
            with self.subTest(name):
                self.publish(sessions=[], pulls=[self.draft(998, "no-date", created),
                                                 self.draft(1000, "lone-draft", self.created_before(780))])
                count, detail = self.row(self.out_with_live(), self.DRAFT)
                self.assertEqual((count, self.entries(detail)),
                                 (2, ["#1000 (lone-draft)", "unknown (#998 has no createdAt)"]))

    def test_no_live_file_reads_the_draft_row_unknown(self):
        _, out = self.build_from_main()
        count, detail = self.row(out, self.DRAFT)
        self.assertEqual(count, 1)
        self.assertTrue(detail.startswith("unknown (") and "--live" in detail, detail)


def baked(text, key):
    """The JSON value right after `key` in a page or a block. The data is plain JSON in a script."""
    at = text.index(key) + len(key)
    return json.JSONDecoder().raw_decode(text, at)[0]


class BlockOnly(Fixture):
    """--block writes only the roadmap data block, for the waiting-page writer to splice in
    (one-page notes, "Build constraints": the build never publishes and never writes ROADMAP_DB)."""

    def block_from_main(self):
        self.on_main()
        code, out = run_build("--repo", str(self.repo), "--block", "--out", str(self.out))
        self.assertIn(code, (0, None), out)
        return self.out.read_text(encoding="utf-8")

    def test_file_is_one_marked_block_holding_the_two_globals(self):
        block = self.block_from_main()
        self.assertTrue(block.strip().startswith(OPEN), block[:80])
        self.assertTrue(block.strip().endswith(CLOSE), block[-80:])
        self.assertEqual((block.count(OPEN), block.count(CLOSE), block.count("<script")), (1, 1, 1))
        self.assertIn("window.ROADMAP_DATA = ", block)
        self.assertIn("window.ROADMAP_BUILD = ", block)
        for word in ("<html", "<head", "<body", "<style"):
            self.assertNotIn(word, block, "the file is more than the data block")

    def test_never_writes_roadmap_db(self):
        block = self.block_from_main()
        self.assertNotIn("ROADMAP_DB", block)
        self.assertNotIn("window.claude", block)

    def test_data_is_what_the_full_build_bakes(self):
        page, _ = self.build_from_main()
        block = self.block_from_main()
        data = baked(block, "window.ROADMAP_DATA = ")
        self.assertEqual(data, baked(page, "const DATA = "))
        self.assertEqual(data["steps"]["c1"], STEP, "two empty values would pass the line above")
        got, want = baked(block, "window.ROADMAP_BUILD = "), build_info(page)
        got.pop("builtAt"), want.pop("builtAt")  # the build time differs between the two builds
        self.assertEqual(got, want)

    def test_no_record_branch_bakes_null_data_and_says_why(self):
        self.on_main()
        code, out = run_build("--repo", str(self.repo), "--record-branch", "no-such-branch", "--block",
                              "--out", str(self.out))
        self.assertIn(code, (0, None), out)
        block = self.out.read_text(encoding="utf-8")
        self.assertIn("window.ROADMAP_DATA = ", block)
        self.assertIsNone(baked(block, "window.ROADMAP_DATA = "))
        self.assertNotIn("ROADMAP_DB", block)
        steps = next(p for p in baked(block, "window.ROADMAP_BUILD = ")["panels"] if p["name"] == "Steps")
        self.assertTrue(steps["read"].startswith("unknown"), steps)
        self.assertIn("no-such-branch", steps["read"])

    def test_on_the_record_branch_it_still_writes_only_the_out_file(self):
        code, out = run_build("--repo", str(self.repo), "--block", "--out", str(self.out))
        self.assertIn(code, (0, None), out)
        self.assertTrue(self.out.exists())
        self.assertFalse((self.repo / "roadmap" / "roadmap.html").exists(), "the page was written too")

    def test_markup_in_the_data_cannot_end_the_block_early(self):
        # A closing script tag, comment openers, a lone quote and a second line, all in one note.
        note = "</script><!-- x --> it's \"q\"\nline two // # /* `tick`"
        self.write_step("c1", dict(STEP, note=note))
        git(self.repo, "commit", "-qam", "note")
        block = self.block_from_main()
        self.assertEqual(block.count("</script>"), 1)
        self.assertEqual(block.count("<!--"), 2, "a comment opener from the data reached the block")
        self.assertEqual(baked(block, "window.ROADMAP_DATA = ")["steps"]["c1"]["note"], note)


class ForkRecord(Fixture):
    """A fork worktree keeps its own waiting page and its own record branch, named in its extras file
    (decision session-tiers). Both record branches sit on one bare origin."""
    STEPS = {"c1": dict(STEP, title="Main record step")}
    MAIN_URL = "https://claude.ai/artifact/MAINPAGE111"
    FORK_URL = "https://claude.ai/artifact/FORKPAGE222"
    MAIN_TITLE = "Main record step"
    FORK_TITLE = "Fork record step"

    def setUp(self):
        super().setUp()
        self.on_main()
        self.write_extras(self.repo, self.MAIN_URL)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "main extras")
        origin = pathlib.Path(self.tmp.name) / "origin.git"
        git(self.tmp.name, "init", "-q", "--bare", str(origin))
        git(self.repo, "remote", "add", "origin", str(origin))
        git(self.repo, "branch", "-q", "roadmap-fork", "roadmap")
        git(self.repo, "checkout", "-q", "roadmap-fork")
        (self.data / "steps" / "c1.json").write_text(json.dumps(dict(STEP, title=self.FORK_TITLE)), encoding="utf-8")
        git(self.repo, "commit", "-qam", "fork record")
        self.on_main()
        git(self.repo, "push", "-q", "origin", "main", "roadmap", "roadmap-fork")
        git(self.repo, "fetch", "-q", "origin")
        self.fork = pathlib.Path(self.tmp.name) / "fork"
        git(self.repo, "worktree", "add", "-q", "-b", "fork-own-page", str(self.fork), "main")
        self.write_extras(self.fork, self.FORK_URL, **{"record-branch": "roadmap-fork"})
        git(self.fork, "commit", "-qam", "fork extras")

    def write_extras(self, root, url, **keys):
        path = pathlib.Path(root) / ".claude" / "layout-extras.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict({"kinds": {}, "waiting-page": url}, **keys)), encoding="utf-8")

    def page_from(self, root, *extra):
        code, out = run_build("--repo", str(root), "--out", str(self.out), *extra)
        self.assertEqual(code, 0, out)
        return self.out.read_text(encoding="utf-8")

    def test_fork_worktree_with_no_flag_reads_its_own_record_branch(self):
        page = self.page_from(self.fork)
        self.assertIn(self.FORK_TITLE, page)
        self.assertNotIn(self.MAIN_TITLE, page)
        panels = {p["name"]: p for p in build_info(page)["panels"]}
        self.assertEqual(panels["Steps"]["read"], git(self.repo, "rev-parse", "--short", "origin/roadmap-fork").strip())

    def test_explicit_record_branch_still_reads_mains(self):
        page = self.page_from(self.fork, "--record-branch", "roadmap")
        self.assertIn(self.MAIN_TITLE, page)
        self.assertNotIn(self.FORK_TITLE, page)

    def broken_extras(self, text):
        """Put `text` in the fork's extras file, uncommitted, where the build reads it."""
        (pathlib.Path(self.fork) / ".claude" / "layout-extras.json").write_text(text, encoding="utf-8")

    def test_unreadable_extras_with_no_flag_warns_on_stderr_and_reads_roadmap(self):
        for text in ("", "{not json", json.dumps({"waiting-page": self.FORK_URL})):
            with self.subTest(text=text):
                self.broken_extras(text)
                if self.out.exists():
                    self.out.unlink()
                code, out, err = run_build_streams("--repo", str(self.fork), "--out", str(self.out))
                self.assertEqual(code, 0, out + err)
                self.assertIn("layout-extras.json", err)
                self.assertNotIn("layout-extras.json", out)
                self.assertNotIn("Traceback", err)
                page = self.out.read_text(encoding="utf-8")
                self.assertIn(self.MAIN_TITLE, page)
                self.assertNotIn(self.FORK_TITLE, page)

    def test_a_readable_extras_file_with_a_bad_record_branch_still_fails(self):
        # Guard: a bad value is refused, never read as roadmap.
        self.write_extras(self.fork, self.FORK_URL, **{"record-branch": "two words"})
        code, out, err = run_build_streams("--repo", str(self.fork), "--out", str(self.out))
        self.assertNotIn(code, (0, None), out + err)
        self.assertFalse(self.out.exists())

    def test_a_flag_still_wins_over_an_unreadable_extras_file(self):
        # Guard: with --record-branch, a broken extras file does not stop the build.
        self.broken_extras("{not json")
        page = self.page_from(self.fork, "--record-branch", "roadmap")
        self.assertIn(self.MAIN_TITLE, page)


if __name__ == "__main__":
    unittest.main()
