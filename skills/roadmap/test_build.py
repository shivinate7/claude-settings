"""Fixture suite for the roadmap build.py. Run: python3 skills/roadmap/test_build.py

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
from unittest import mock

sys.dont_write_bytecode = True
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parent.parent / "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)
import build  # noqa: E402
import layout  # noqa: E402  the waiting page and record branch readers (lint/layout.py)
import shared_names  # noqa: E402  the one home of the tag names (hooks/shared_names.py), on the path build set

# Made in setUpModule, not at import, so a helper that imports make_repo leaks no folder.
RUN_FOLDER = None

STEP = {"title": "t", "status": "todo", "phase": "cleanup", "order": 1, "note": "n", "updatedAt": "2026-10-26T00:00:00Z"}
CONFLICT = "<<<<<<< HEAD\na\n=======\nb\n>>>>>>> 1234567 (other)\n"
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
_NO_LANE = object()  # item(): the default, which leaves the row's lane key out
_ABSENT = object()  # commit_step(): a field set to this is left out of the step file
# get_session's status_bucket as list_sessions returns it: the SESSION_STATUS_BUCKET_* enum names, measured on real rows.
BUCKET_COMPLETED = "SESSION_STATUS_BUCKET_COMPLETED"
BUCKET_REVIEW_READY = "SESSION_STATUS_BUCKET_REVIEW_READY"
BUCKET_WORKING = "SESSION_STATUS_BUCKET_WORKING"
BUCKET_BLOCKED = "SESSION_STATUS_BUCKET_BLOCKED"
BUCKET_FAILED = "SESSION_STATUS_BUCKET_FAILED"

# The page script the roadmap branch's build.py put in front of the viewer. The
# script's stub must stay byte for byte this, so the viewer reads the data as it did.
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
# sha256 of the roadmap branch's roadmap/page/index.html, the page the old script used.
TODAY_TEMPLATE_SHA256 = "23bc9c5770e92a063db47619ce0dec0bf50a0d8972cfa973b7cf3b7ca07c32d2"
BLOCK = re.compile(r"<!-- build:([a-z-]+) -->.*?<!-- /build:\1 -->\n?", re.S)


def today_page(template, data):
    """What the roadmap branch's build.py wrote for this template and data."""
    head, sep, rest = template.partition("<body>")
    return head + sep + "\n" + TODAY_STUB % json.dumps(data, ensure_ascii=False).replace("</", "<\\/") + rest


def git(repo, *args, env=None):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True,
                          env={**os.environ, **GIT_ENV, **(env or {})}).stdout


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


def session_row(sid, status, *tags, status_bucket=None):
    """One sessions row, as triage copies it from list_sessions. The status_bucket key (get_session's bucket) is
    added only when given, so a row without it reads as the live file's rows did before the key existed."""
    row = {"id": sid, "session_status": status, "tags": list(tags)}
    if status_bucket is not None:
        row["status_bucket"] = status_bucket
    return row


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
        """(page, output) of a build from main. expect lists the exit codes the case accepts; self.code is the exit code."""
        self.on_main()
        code, out = run_build("--repo", str(self.repo), "--out", str(self.out), *extra)
        self.code = code
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
        """Write a step on the record branch and commit it, where a build from main reads it. A field set to _ABSENT is left out."""
        self.write_step(sid, {k: v for k, v in dict(STEP, **fields).items() if v is not _ABSENT})
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "step " + sid)

    def publish(self, sessions=None, pulls=(), threads=(), read_at=None, items=None):
        """Write the --live file. The sessions and items keys appear only when given. readAt is five minutes old by default."""
        value = {"readAt": read_at or iso_ago(5), "threads": list(threads), "pulls": list(pulls)}
        if sessions is not None:
            value["sessions"] = list(sessions)
        if items is not None:
            value["items"] = items
        self.write_live(value)
        return value

    def out_with_live(self, expect=(0, None)):
        _, out = self.build_from_main("--live", str(self.live), expect=expect)
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
        """The entries of a row's detail, sorted. The script orders them by step id, which no case relies on."""
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

    def session_in_repo(self, sid, status, *tags):
        """A sessions row for this fixture repo, carrying the cs-repo tag the script checks."""
        return session_row(sid, status, self.REPO, *tags)

    def listed_ids(self, entries):
        return re.findall(r"([^,()\s]+) \(set to ", entries)

    def item(self, n, home="c153", status="closed", lane=_NO_LANE):
        """One row of the --live file's items list, as the publisher copies it from the waiting page. lane=None writes
        "lane": null (an answer with no lane); the default leaves the lane key out, so the row reads the items unknown."""
        row = {"n": n, "status": status, "home": home}
        if lane is not _NO_LANE:
            row["lane"] = lane
        return row

    def stalled_block(self, page):
        """The page's stalled block. Fails with a named cause when the page has none."""
        info = build_info(page)
        self.assertIn("stalled", info, "the page has no stalled block")
        return info["stalled"]

    def ready_block(self, page):
        """The page's ready block. Fails with a named cause when the page has none."""
        info = build_info(page)
        self.assertIn("ready", info, "the page has no ready block")
        return info["ready"]

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


class StaleInProgress(UpkeepFixture):
    """The upkeep row for each doing or active step with no live lane and no open PR. Its entries read
    `<id> (set to todo)`, `<id> (set to done: landed in #N)`, or one `unknown (<why>)` when unreadable."""

    ROW = "in progress with no live lane or open PR"

    def stale(self, out):
        """(count, entries) of the stale row. Fails when the output holds no such row."""
        return self.row(out, self.ROW)

    def test_doing_step_with_a_live_session_is_not_listed(self):
        self.commit_step("c1", status="doing")
        self.commit_step("c2", status="doing", order=2)  # no session, so it is listed and an empty row cannot pass
        for status in ("SESSION_STATUS_RUNNING", "SESSION_STATUS_IDLE",
                       "SESSION_STATUS_REQUIRES_ACTION", "SESSION_STATUS_PENDING"):
            with self.subTest(status=status):
                self.publish(sessions=[self.session_in_repo("session_test01", status, "cs-step:c1")])
                count, entries = self.stale(self.out_with_live(expect=(1,)))
                self.assertEqual((count, self.listed_ids(entries)), (1, ["c2"]))

    def test_doing_step_whose_id_is_an_open_pull_branch_is_not_listed(self):
        self.commit_step("c1", status="doing")
        self.commit_step("c2", status="doing", order=2)  # control: listed
        self.publish(sessions=[], pulls=[{"number": 874, "title": "Lane c1", "branch": "c1"}])
        count, entries = self.stale(self.out_with_live(expect=(1,)))
        self.assertEqual((count, self.listed_ids(entries)), (1, ["c2"]))

    def test_doing_and_active_steps_with_neither_are_set_to_todo(self):
        self.commit_step("c1", status="doing")
        self.commit_step("c2", status="active", order=2)
        self.publish(sessions=[])
        count, entries = self.stale(self.out_with_live(expect=(1,)))
        self.assertEqual(count, 2)
        self.assertIn("c1 (set to todo)", entries)
        self.assertIn("c2 (set to todo)", entries)

    def test_archived_session_does_not_keep_its_step_live(self):
        self.commit_step("c1", status="doing")
        self.publish(sessions=[self.session_in_repo("session_test01", "SESSION_STATUS_ARCHIVED", "cs-step:c1")])
        self.assertEqual(self.stale(self.out_with_live(expect=(1,))), (1, "c1 (set to todo)"))

    def test_step_page_does_not_match_tag_or_branch_page_name_queue(self):
        self.commit_step("page", status="doing", note="Lane page-name-queue: draft PR #874")
        self.publish(sessions=[self.session_in_repo("session_test01", "SESSION_STATUS_RUNNING", "cs-step:page-name-queue")],
                     pulls=[{"number": 874, "title": "Page name queue", "branch": "page-name-queue"}])
        self.assertEqual(self.stale(self.out_with_live(expect=(1,))), (1, "page (set to todo)"))

    def test_step_trailer_on_main_sets_the_step_to_done(self):
        self.commit_step("c1", status="doing")
        self.on_main()
        (self.repo / "landed.txt").write_text("x", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "landed (#12)\n\nStep: c1")
        self.publish(sessions=[])
        self.assertEqual(self.stale(self.out_with_live(expect=(1,))), (1, "c1 (set to done: landed in #12)"))

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
        self.assertEqual(self.stale(self.out_with_live(expect=(1,))), (1, "c1 (set to todo)"))

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
        self.assertEqual(self.stale(self.out_with_live(expect=(1,))), (1, "c4 (set to todo)"))

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
            self.assertEqual(self.stale(self.out_with_live(expect=(1,))), (1, "c1 (set to todo)"))

    # Only archived ends a lane (session-tiers, Live-coordinator check), so an unseen status keeps its step live.
    def test_session_in_an_unseen_status_keeps_its_step_live(self):
        self.commit_step("c1", status="doing")
        self.commit_step("c2", status="doing", order=2)  # control: listed
        self.publish(sessions=[self.session_in_repo("session_test01", "SESSION_STATUS_SOMETHING_NEW", "cs-step:c1")])
        count, entries = self.stale(self.out_with_live(expect=(1,)))
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
                count, entries = self.stale(self.out_with_live(expect=(1,)))
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
        count, entries = self.stale(self.out_with_live(expect=(1,)))
        self.assertEqual(count, 2)
        self.assertIn('c1 (unknown status "waiting")', entries)
        self.assertIn("c2 (set to todo)", entries)


    def test_session_without_tags_or_with_null_tags_is_tagless_not_skipped(self):
        self.commit_step("c1", status="doing")
        self.commit_step("c2", status="doing", order=2)  # control: listed
        tagless = [{"id": "session_test02", "session_status": "SESSION_STATUS_IDLE"},
                   {"id": "session_test03", "session_status": "SESSION_STATUS_RUNNING", "tags": None}]
        self.publish(sessions=[self.session_in_repo("session_test01", "SESSION_STATUS_RUNNING", "cs-step:c1")] + tagless)
        page, out = self.build_from_main("--live", str(self.live), expect=(1,))
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
        self.assertEqual(self.stale(self.out_with_live(expect=(1,))), (1, "c2 (set to todo)"))


class StalledStep(UpkeepFixture):
    """The stalled-step view (plan: stalled steps). A doing or active step with no live lane and no open PR is
    stalled until it has a disposition: a valid `paused` field, which triage writes, or status done. A stalled
    step prints `stalled step: <id> (resume, pause or done)`, or `stalled step: <id> (done: landed in #N)` when it
    landed, and the build exits 1 after it writes the page. An unknown live read prints
    `stalled step: unknown (<why>)`, lists no steps as [], and exits 0."""

    PAUSE = {"why": "waits on the owner's call on the batch", "decides": "owner",
             "at": "2026-11-06T11:00:00-06:00", "by": "triage"}
    RESUME = "stalled step: c2 (resume, pause or done)"

    def stalled_lines(self, out):
        """The printed step lines, in print order. The unknown and item lines are not step lines."""
        return re.findall(r"^stalled step: (?!unknown \(|items unknown \(|item \d).*$", out, re.M)

    def stalled_ids(self, out):
        return [re.match(r"stalled step: (\S+) \(", line).group(1) for line in self.stalled_lines(out)]

    def test_doing_step_with_no_lane_exits_1_and_prints_one_stalled_line(self):
        self.commit_step("c2", status="doing", order=2)
        self.publish(sessions=[], items=[])
        page, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        self.stalled_block(page)
        self.assertEqual(self.stalled_lines(out), [self.RESUME], "c2 has no lane, so it is the one stalled line")
        self.assertEqual(self.code, 1, "a stalled step must exit 1")

    def test_a_live_step_is_not_printed_beside_a_stalled_one(self):
        self.commit_step("c1", status="doing")  # control: its live session keeps it off the lines
        self.commit_step("c2", status="doing", order=2)
        self.publish(sessions=[self.session_in_repo("session_test01", "SESSION_STATUS_RUNNING", "cs-step:c1")], items=[])
        page, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        self.stalled_block(page)
        self.assertEqual(self.stalled_lines(out), [self.RESUME], "only c2 is stalled")
        self.assertEqual(self.code, 1, "a stalled step must exit 1")

    def test_page_is_written_before_exit_1_and_lists_the_stalled_ids(self):
        self.commit_step("c1", status="doing")  # control: live, so not in the stalled ids
        self.commit_step("c2", status="doing", order=2)
        self.publish(sessions=[self.session_in_repo("session_test01", "SESSION_STATUS_RUNNING", "cs-step:c1")], items=[])
        page, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        stalled = self.stalled_block(page)
        self.assertEqual([s["id"] for s in stalled["steps"]], ["c2"], "the page's stalled steps are c2 only")
        self.assertEqual(self.code, 1, "a stalled step must exit 1")

    def test_landed_doing_step_reads_done_with_its_pr(self):
        self.commit_step("c1", status="doing")  # control: live, so not printed
        self.land("c2", 12, order=2)  # landed on main with a Step: trailer, still doing, no lane
        self.publish(sessions=[self.session_in_repo("session_test01", "SESSION_STATUS_RUNNING", "cs-step:c1")], items=[])
        page, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        self.stalled_block(page)
        self.assertEqual(self.stalled_lines(out), ["stalled step: c2 (done: landed in #12)"])
        self.assertEqual(self.code, 1, "a stalled step must exit 1")

    def test_valid_paused_field_exits_0_and_lists_the_step_as_paused(self):
        self.commit_step("c2", status="doing", order=2, paused=self.PAUSE)
        self.publish(sessions=[], items=[])
        page, out = self.build_from_main("--live", str(self.live))
        stalled = self.stalled_block(page)
        self.assertIn("c2", stalled["paused"], "a valid paused step is listed in paused")
        self.assertEqual(stalled["steps"], [], "a paused step is not stalled, and a known read lists [] for none")
        self.assertEqual(self.stalled_lines(out), [])

    def test_bad_paused_field_keeps_the_step_stalled_and_lists_it_in_badPause(self):
        bad = {
            "no why": {k: v for k, v in self.PAUSE.items() if k != "why"},
            "empty why": dict(self.PAUSE, why=""),
            "decides not in the set": dict(self.PAUSE, decides="boss"),
            "at with no zone": dict(self.PAUSE, at="2026-11-06T11:00:00"),
        }
        for name, paused in bad.items():
            with self.subTest(name):
                git(self.repo, "checkout", "-q", "roadmap")
                self.commit_step("c2", status="doing", order=2, paused=paused)
                self.publish(sessions=[], items=[])
                page, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
                stalled = self.stalled_block(page)
                self.assertEqual([b["id"] for b in stalled["badPause"]], ["c2"], "a wrong-shaped pause is listed")
                self.assertEqual(self.stalled_lines(out), [self.RESUME], "and the step stays stalled")
                self.assertEqual(self.code, 1, "a stalled step must exit 1")

    def test_unknown_live_read_prints_unknown_with_steps_none_and_exits_0(self):
        self.commit_step("c2", status="doing", order=2)
        cases = {
            "no --live file": None,
            "readAt two hours old": dict(sessions=[], read_at=iso_ago(120), items=[]),
            "no sessions list": dict(items=[]),
        }
        for name, live in cases.items():
            with self.subTest(name):
                args = ()
                if live is not None:
                    self.publish(**live)
                    args = ("--live", str(self.live))
                page, out = self.build_from_main(*args)
                stalled = self.stalled_block(page)
                self.assertIsNone(stalled["steps"], "an unknown read lists no steps, never []")
                self.assertRegex(out, r"(?m)^stalled step: unknown \(", "the unknown line is missing")
                self.assertEqual(self.code, 0, "an unknown read exits 0")

    def test_landed_feel_fix_without_a_device_trial_is_not_stalled(self):
        self.commit_step("c2", status="doing", order=2)  # control: a plain lane-less step is still stalled
        self.land("c1", 12, feel=True)  # waits for a device trial: the device row lists it, not the stalled lines
        self.publish(sessions=[], items=[])
        page, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        stalled = self.stalled_block(page)
        self.assertEqual([s["id"] for s in stalled["steps"]], ["c2"], "the feel-fix is not stalled")
        self.assertEqual(self.stalled_lines(out), [self.RESUME])
        self.assertEqual(self.code, 1, "a stalled step must exit 1")

    def test_todo_done_ready_and_unknown_status_steps_are_never_stalled(self):
        self.commit_step("c2", status="doing", order=2)  # control: stalled
        self.commit_step("c3", status="todo", order=3)
        self.commit_step("c4", status="done", order=4)
        self.commit_step("c5", status="todo", note="Brief is written. Ready.", order=5)  # a ready todo step
        self.commit_step("c6", status="waiting", order=6)  # unknown status: the upkeep row lists it, the stall never does
        self.publish(sessions=[], items=[])
        page, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        stalled = self.stalled_block(page)
        self.assertEqual([s["id"] for s in stalled["steps"]], ["c2"])
        self.assertEqual(self.stalled_lines(out), [self.RESUME])
        self.assertEqual(self.code, 1, "a stalled step must exit 1")

    def test_stalled_ids_are_the_in_progress_row_ids(self):
        self.commit_step("c1", status="doing")  # control: live, in neither the row nor the stalled ids
        self.commit_step("c2", status="doing", order=2)
        self.commit_step("c3", status="active", order=3)
        self.land("c4", 14, order=4)  # landed, so the row reads set to done
        self.publish(sessions=[self.session_in_repo("session_test01", "SESSION_STATUS_RUNNING", "cs-step:c1")], items=[])
        page, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        stalled = self.stalled_block(page)
        _, detail = self.row(out, StaleInProgress.ROW)
        row_ids = sorted(self.listed_ids(detail))
        self.assertEqual(row_ids, ["c2", "c3", "c4"], "the row lists the three lane-less steps")
        self.assertEqual(sorted(s["id"] for s in stalled["steps"]), row_ids, "the page's ids are the row's ids")
        self.assertEqual(sorted(self.stalled_ids(out)), row_ids, "the printed ids are the row's ids")
        self.assertEqual(self.code, 1, "a stalled step must exit 1")

    def test_no_stalled_step_reads_an_empty_list_not_unknown(self):
        self.commit_step("c1", status="doing")  # live, so nothing is stalled
        self.publish(sessions=[self.session_in_repo("session_test01", "SESSION_STATUS_RUNNING", "cs-step:c1")], items=[])
        page, out = self.build_from_main("--live", str(self.live))
        stalled = self.stalled_block(page)
        self.assertEqual(stalled["steps"], [], "zero stalled steps is an empty list, not unknown")
        self.assertEqual(stalled["items"], [], "an empty items list reads zero, not unknown")
        self.assertEqual(self.stalled_lines(out), [])

    def test_topic_session_does_not_keep_a_doing_step_live(self):
        self.commit_step("c1", status="doing")  # control: its cs-step session keeps c1 live, so c1 is not stalled
        self.commit_step("c2", status="doing", order=2)
        topic = self.session_in_repo("session_test01", "SESSION_STATUS_RUNNING", "cs-step:c1", "cs-topic:c2")
        self.publish(sessions=[topic], items=[])
        page, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        stalled = self.stalled_block(page)
        self.assertIsNotNone(stalled["steps"], "the live read is known, so the steps list is a list")
        self.assertNotIn("c1", [s["id"] for s in stalled["steps"]], "the cs-step:c1 session keeps c1 live")
        self.assertEqual([s["id"] for s in stalled["steps"]], ["c2"], "a cs-topic tag never keeps a step live")
        self.assertEqual(self.stalled_lines(out), [self.RESUME])
        self.assertEqual(self.code, 1, "a stalled step must exit 1")

    def test_open_pull_on_the_lane_slash_branch_clears_a_doing_step(self):
        self.commit_step("c2", status="doing", order=2)
        self.publish(sessions=[], pulls=[{"number": 7, "title": "Lane c2", "branch": "lane/c2"}], items=[])
        page, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        stalled = self.stalled_block(page)
        self.assertIsNotNone(stalled["steps"], "the live read is known, so the steps list is a list")
        self.assertEqual(stalled["steps"], [], "an open pull on lane/c2 keeps c2 live")
        self.assertEqual(self.stalled_lines(out), [])
        self.assertEqual(self.code, 0, "no stalled step exits 0")

    def test_open_pull_on_a_longer_lane_branch_does_not_clear_a_doing_step(self):
        self.commit_step("c2", status="doing", order=2)  # control: lane/c2x is another lane
        self.publish(sessions=[], pulls=[{"number": 8, "title": "Lane c2x", "branch": "lane/c2x"}], items=[])
        page, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        stalled = self.stalled_block(page)
        self.assertIsNotNone(stalled["steps"], "the live read is known, so the steps list is a list")
        self.assertEqual([s["id"] for s in stalled["steps"]], ["c2"], "a pull on lane/c2x does not clear c2")
        self.assertEqual(self.stalled_lines(out), [self.RESUME])
        self.assertEqual(self.code, 1, "a stalled step must exit 1")


class StalledItem(UpkeepFixture):
    """A waiting-page item whose answer went to a lane that is gone. An open item (status not closed) whose `lane`
    is set and not live prints `stalled step: item <n> (lane <slug>: re-route, close or resume)` and the build exits
    1. A slug lane is live when an open pull's branch is the lane or lane/<slug>, or a live session in this repo
    carries cs-step:<slug> or cs-topic:<slug>. A tier lane such as batch-runner is live when a live session in this repo carries
    cs-build:<tier>. A row with no lane key reads the items unknown and exits 0."""

    def item_lines(self, out):
        return re.findall(r"^stalled step: item \d+ \(.*$", out, re.M)

    def test_open_item_on_a_lane_that_is_gone_is_stalled(self):
        self.publish(sessions=[], items=[self.item(12, status="open", lane="x")])
        page, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        stalled = self.stalled_block(page)
        self.assertEqual(stalled["items"], [{"n": 12, "lane": "x"}], "item 12 answers lane x, which has no live work")
        self.assertEqual(self.item_lines(out), ["stalled step: item 12 (lane x: re-route, close or resume)"])
        self.assertEqual(self.code, 1, "a stalled item must exit 1")

    def test_open_pull_on_the_lane_branch_clears_the_item(self):
        self.publish(sessions=[], pulls=[{"number": 7, "title": "Lane x", "branch": "x"}],
                     items=[self.item(12, status="open", lane="x"),
                            self.item(13, status="open", lane="y")])  # control: lane y has no work
        page, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        stalled = self.stalled_block(page)
        self.assertEqual(stalled["items"], [{"n": 13, "lane": "y"}], "only item 13 is stalled: lane x has a PR")
        self.assertEqual(self.item_lines(out), ["stalled step: item 13 (lane y: re-route, close or resume)"])
        self.assertEqual(self.code, 1, "a stalled item must exit 1")

    def test_live_session_with_the_tier_tag_clears_the_tier_lane(self):
        self.publish(sessions=[self.session_in_repo("session_test01", "SESSION_STATUS_RUNNING", "cs-build:batch-runner")],
                     items=[self.item(12, status="open", lane="batch-runner"),
                            self.item(13, status="open", lane="y")])  # control: lane y has no work
        page, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        stalled = self.stalled_block(page)
        self.assertEqual(stalled["items"], [{"n": 13, "lane": "y"}], "only item 13 is stalled: batch-runner is live")
        self.assertEqual(self.item_lines(out), ["stalled step: item 13 (lane y: re-route, close or resume)"])
        self.assertEqual(self.code, 1, "a stalled item must exit 1")

    def test_closed_item_is_never_listed(self):
        self.publish(sessions=[], items=[self.item(12, status="closed", lane="x"),
                                         self.item(13, status="open", lane="y")])  # control: open, so listed
        page, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        stalled = self.stalled_block(page)
        self.assertEqual(stalled["items"], [{"n": 13, "lane": "y"}], "a closed item is never stalled")
        self.assertEqual(self.item_lines(out), ["stalled step: item 13 (lane y: re-route, close or resume)"])
        self.assertEqual(self.code, 1, "a stalled item must exit 1")

    def test_item_rows_with_no_lane_key_read_the_items_unknown_and_exit_0(self):
        self.publish(sessions=[], items=[self.item(12, status="open")])
        page, out = self.build_from_main("--live", str(self.live))
        stalled = self.stalled_block(page)
        self.assertIsNone(stalled["items"], "a row with no lane reads the items unknown, never []")
        self.assertRegex(out, r"(?m)^stalled step: items unknown \(", "the items unknown line is missing")
        self.assertEqual(self.code, 0, "an unknown items read exits 0")

    def test_live_topic_session_clears_the_item_lane(self):
        topic = self.session_in_repo("session_test01", "SESSION_STATUS_RUNNING", "cs-topic:x")
        self.publish(sessions=[topic], items=[self.item(12, status="open", lane="x"),
                                             self.item(13, status="open", lane="y")])  # control: lane y has no work
        page, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        stalled = self.stalled_block(page)
        self.assertIsNotNone(stalled["items"], "the live read is known, so the items list is a list")
        self.assertEqual(stalled["items"], [{"n": 13, "lane": "y"}], "a live cs-topic:x session clears item 12")
        self.assertEqual(self.item_lines(out), ["stalled step: item 13 (lane y: re-route, close or resume)"])
        self.assertEqual(self.code, 1, "a stalled item must exit 1")

    def test_archived_tier_session_does_not_keep_the_tier_lane_live(self):
        archived = self.session_in_repo("session_test01", "SESSION_STATUS_ARCHIVED", "cs-build:batch-runner")
        self.publish(sessions=[archived], items=[self.item(12, status="open", lane="batch-runner")])
        page, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        stalled = self.stalled_block(page)
        self.assertIsNotNone(stalled["items"], "the live read is known, so the items list is a list")
        self.assertEqual(stalled["items"], [{"n": 12, "lane": "batch-runner"}], "an archived session keeps no lane live")
        self.assertEqual(self.item_lines(out), ["stalled step: item 12 (lane batch-runner: re-route, close or resume)"])
        self.assertEqual(self.code, 1, "a stalled item must exit 1")

    def test_tier_session_of_another_repo_does_not_keep_the_tier_lane_live(self):
        other = session_row("session_test02", "SESSION_STATUS_RUNNING", "cs-repo:owner/other-repo", "cs-build:batch-runner")
        self.publish(sessions=[other], items=[self.item(12, status="open", lane="batch-runner")])
        page, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        stalled = self.stalled_block(page)
        self.assertIsNotNone(stalled["items"], "the live read is known, so the items list is a list")
        self.assertEqual(stalled["items"], [{"n": 12, "lane": "batch-runner"}], "a session of another repo keeps no lane live")
        self.assertEqual(self.item_lines(out), ["stalled step: item 12 (lane batch-runner: re-route, close or resume)"])
        self.assertEqual(self.code, 1, "a stalled item must exit 1")

    def test_open_pull_on_the_lane_slash_branch_clears_the_item(self):
        self.publish(sessions=[], pulls=[{"number": 7, "title": "Lane x", "branch": "lane/x"}],
                     items=[self.item(12, status="open", lane="x"),
                            self.item(13, status="open", lane="y")])  # control: lane y has no work
        page, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        stalled = self.stalled_block(page)
        self.assertIsNotNone(stalled["items"], "the live read is known, so the items list is a list")
        self.assertEqual(stalled["items"], [{"n": 13, "lane": "y"}], "an open pull on lane/x clears item 12")
        self.assertEqual(self.item_lines(out), ["stalled step: item 13 (lane y: re-route, close or resume)"])
        self.assertEqual(self.code, 1, "a stalled item must exit 1")

    def test_null_lane_reads_the_items_known_and_is_never_stalled(self):
        self.publish(sessions=[], items=[self.item(12, status="open", lane=None)])
        page, out = self.build_from_main("--live", str(self.live), expect=(0,))
        stalled = self.stalled_block(page)
        self.assertIsNotNone(stalled["items"], "a null lane is a known answer, so the items list is a list")
        self.assertEqual(stalled["items"], [], "a null lane names no lane, so item 12 is not stalled")
        self.assertNotRegex(out, r"(?m)^stalled step: items unknown \(", "a null lane must not read the items unknown")
        self.assertEqual(self.code, 0, "a known read with no stalled item exits 0")


class ReadyNotStarted(UpkeepFixture):
    """The ready-not-started view (plan: stalled steps, Part 2). A todo or ready step in phase now is listed in the
    page's ready block when no live lane holds it (no cs-step session, no open pull on its id or lane/<id>), it has
    no valid `paused` field, and no open waiting-page item homed to it has a lane. Its age is whole hours from its
    updatedAt to the live read, or None. The build prints `ready not started: <id> (<age>h)` per step, or one
    `ready not started: <why>` when the read is unknown. Ready lines never change the exit code."""

    def setUp(self):
        super().setUp()
        self.read_at = iso_ago(5)  # the live read; the fixture's ages are counted back from it

    def before(self, minutes):
        """An ISO UTC time `minutes` before the live read."""
        at = datetime.datetime.fromisoformat(self.read_at.replace("Z", "+00:00"))
        return (at - datetime.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def ready_step(self, sid, order, **fields):
        """Commit a todo step in phase now, last updated 3 h 10 min before the live read, so its age is 3 whichever
        way the hours round. Fields override those defaults."""
        git(self.repo, "checkout", "-q", "roadmap")
        step = dict(status="todo", phase="now", order=order, updatedAt=self.before(190))
        step.update(fields)
        self.commit_step(sid, **step)

    def known_read(self, sessions=(), pulls=(), items=()):
        """A live file read at self.read_at, with its sessions and items lists, so the read is known."""
        self.publish(sessions=list(sessions), pulls=list(pulls), items=list(items), read_at=self.read_at)

    def ready_ids(self, ready):
        """The listed ids, in order. The steps must be a list before any id is read, so an unknown None fails by name."""
        self.assertIsNotNone(ready.get("steps"), "the read is unknown (%s), so no steps are listed" % ready.get("why"))
        return [s["id"] for s in ready["steps"]]

    def ready_lines(self, out):
        return re.findall(r"^ready not started: .*$", out, re.M)

    def assert_unknown(self, live_args, prefix):
        """A build from main with `live_args`: the ready block is unknown, lists no steps, and prints its why as one line."""
        page, out = self.build_from_main(*live_args, expect=(0,))
        ready = self.ready_block(page)
        why = str(ready.get("why"))
        self.assertTrue(why.startswith(prefix), "the why reads %r, not %r" % (why, prefix))
        self.assertIsNone(ready.get("steps"), "an unknown read lists no steps, never []")
        self.assertEqual(self.ready_lines(out), ["ready not started: %s" % why], "the unknown read prints one line")

    def test_todo_step_in_phase_now_with_no_lane_is_listed(self):
        self.ready_step("c2", order=2)
        self.known_read()
        page, _ = self.build_from_main("--live", str(self.live))
        ready = self.ready_block(page)
        self.assertIsNone(ready.get("why"), "a known read has no why")
        self.assertEqual(self.ready_ids(ready), ["c2"], "the todo step in phase now is listed")
        self.assertEqual(self.code, 0, "a ready step alone does not stall the build")

    def test_ready_status_step_is_listed(self):
        self.ready_step("c2", order=2, status="ready")
        self.known_read()
        page, _ = self.build_from_main("--live", str(self.live))
        self.assertEqual(self.ready_ids(self.ready_block(page)), ["c2"], "a step with status ready is listed")

    def test_listed_steps_are_in_step_order_not_commit_order(self):
        self.ready_step("c3", order=3)  # committed first, but later in step order
        self.ready_step("c2", order=2)
        self.known_read()
        page, _ = self.build_from_main("--live", str(self.live))
        self.assertEqual(self.ready_ids(self.ready_block(page)), ["c2", "c3"], "listed by step order")

    def test_every_ready_step_is_listed_in_order_at_full_size(self):
        git(self.repo, "checkout", "-q", "roadmap")
        for n in range(1, 26):
            self.write_step("r%02d" % n, dict(STEP, status="todo", phase="now", order=n, updatedAt=self.before(190)))
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "25 ready steps")
        self.known_read()
        page, _ = self.build_from_main("--live", str(self.live))
        self.assertEqual(self.ready_ids(self.ready_block(page)), ["r%02d" % n for n in range(1, 26)],
                         "all 25 ready steps are listed, in step order")

    def test_no_ready_step_reads_an_empty_list_not_unknown(self):
        self.known_read()  # the fixture's c1 is in phase cleanup, so nothing is ready
        page, _ = self.build_from_main("--live", str(self.live))
        ready = self.ready_block(page)
        self.assertIsNone(ready.get("why"), "a known read has no why")
        self.assertEqual(self.ready_ids(ready), [], "zero ready steps is an empty list")

    def test_open_pull_on_the_step_id_or_its_lane_branch_excludes_it(self):
        self.ready_step("c2", order=2)
        self.ready_step("c3", order=3)  # control: no pull names it
        for branch in ("c2", "lane/c2"):
            with self.subTest(branch=branch):
                self.known_read(pulls=[{"number": 7, "title": "Lane c2", "branch": branch}])
                page, _ = self.build_from_main("--live", str(self.live), expect=(0, 1))  # the todo-with-open-PR line exits 1
                self.assertEqual(self.ready_ids(self.ready_block(page)), ["c3"], "an open pull on %s holds c2 back" % branch)

    def test_cs_step_session_excludes_the_step(self):
        self.ready_step("c2", order=2)
        self.ready_step("c3", order=3)  # control
        self.known_read(sessions=[self.session_in_repo("session_test01", "SESSION_STATUS_RUNNING", "cs-step:c2")])
        page, _ = self.build_from_main("--live", str(self.live))
        self.assertEqual(self.ready_ids(self.ready_block(page)), ["c3"], "a live cs-step:c2 session holds c2 back")

    def test_cs_topic_session_does_not_exclude_the_step(self):
        self.ready_step("c2", order=2)
        self.ready_step("c3", order=3)
        self.known_read(sessions=[self.session_in_repo("session_test01", "SESSION_STATUS_RUNNING", "cs-topic:c2")])
        page, _ = self.build_from_main("--live", str(self.live))
        self.assertEqual(self.ready_ids(self.ready_block(page)), ["c2", "c3"], "a cs-topic tag never holds a step back")

    def test_valid_paused_excludes_the_step_and_a_wrong_shaped_one_keeps_it(self):
        self.ready_step("c3", order=3)  # control
        self.ready_step("c2", order=2, paused=StalledStep.PAUSE)
        self.known_read()
        page, _ = self.build_from_main("--live", str(self.live))
        self.assertEqual(self.ready_ids(self.ready_block(page)), ["c3"], "a valid pause excludes c2")
        bad = {
            "empty why": dict(StalledStep.PAUSE, why=""),
            "decides not in the set": dict(StalledStep.PAUSE, decides="boss"),
            "at with no zone": dict(StalledStep.PAUSE, at="2026-11-06T11:00:00"),
        }
        for name, paused in bad.items():
            with self.subTest(name):
                self.ready_step("c2", order=2, paused=paused)
                self.known_read()
                page, _ = self.build_from_main("--live", str(self.live))
                self.assertEqual(self.ready_ids(self.ready_block(page)), ["c2", "c3"], "a wrong-shaped pause keeps c2 listed")

    def test_open_unanswered_item_homed_to_the_step_excludes_it(self):
        self.ready_step("c2", order=2)
        self.ready_step("c3", order=3)  # control
        for home in ("step c2", "STEP c2", "c2"):
            with self.subTest(home=home):
                self.known_read(items=[self.item(4, home=home, status="open", lane=None)])
                page, _ = self.build_from_main("--live", str(self.live))
                self.assertEqual(self.ready_ids(self.ready_block(page)), ["c3"], "an open item with no lane holds c2 back")

    def test_an_item_with_a_lane_or_a_closed_item_does_not_exclude_the_step(self):
        self.ready_step("c2", order=2)
        self.ready_step("c3", order=3)
        cases = {
            # an open item on a lane with no live work is a stalled item, so the build exits 1
            "open with a lane": (self.item(4, home="step c2", status="open", lane="batch-runner"), (0, 1)),
            "closed with no lane": (self.item(4, home="step c2", status="closed", lane=None), (0,)),
        }
        for name, (row, expect) in cases.items():
            with self.subTest(name):
                self.known_read(items=[row])
                page, _ = self.build_from_main("--live", str(self.live), expect=expect)
                self.assertEqual(self.ready_ids(self.ready_block(page)), ["c2", "c3"], "%s does not hold c2 back" % name)

    def test_doing_or_active_step_is_not_listed(self):
        self.ready_step("c3", order=3)  # control
        for status in ("doing", "active"):
            with self.subTest(status=status):
                self.ready_step("c2", order=2, status=status)
                self.known_read()
                # a lane-less doing or active step is stalled, so the build exits 1
                page, _ = self.build_from_main("--live", str(self.live), expect=(0, 1))
                self.assertEqual(self.ready_ids(self.ready_block(page)), ["c3"], "stalled covers %s steps" % status)

    def test_phase_other_than_now_and_done_steps_are_not_listed(self):
        self.ready_step("c3", order=3)  # control
        for label, fields in (("phase next", {"phase": "next"}), ("done", {"status": "done"})):
            with self.subTest(label):
                self.ready_step("c2", order=2, **fields)
                self.known_read()
                page, _ = self.build_from_main("--live", str(self.live))
                self.assertEqual(self.ready_ids(self.ready_block(page)), ["c3"], "a %s step is not listed" % label)

    def test_unknown_read_lists_no_steps_and_prints_one_unknown_line(self):
        self.ready_step("c2", order=2)  # ready on its own, so a None can only come from the read
        with self.subTest("no --live file"):
            self.assert_unknown((), "unknown (no --live file")
        cases = {
            "readAt two hours old": (dict(sessions=[], items=[], read_at=iso_ago(120)), "unknown (the live file was read "),
            "no sessions list": (dict(sessions=None, items=[]), "unknown (the live file has no sessions list"),
            "no items list": (dict(sessions=[], items=None), "unknown (the live file has no items list"),
            "open row with no lane key": (dict(sessions=[], items=[self.item(4, home="step c9", status="open")]),
                                          "unknown (an open items row has no lane key"),
        }
        for name, (live, prefix) in cases.items():
            with self.subTest(name):
                self.publish(**dict({"read_at": self.read_at}, **live))
                self.assert_unknown(("--live", str(self.live)), prefix)

    def test_closed_row_with_no_lane_key_does_not_make_the_read_unknown(self):
        self.ready_step("c2", order=2)
        self.known_read(items=[self.item(4, home="step c2", status="closed")])
        page, _ = self.build_from_main("--live", str(self.live))
        ready = self.ready_block(page)
        self.assertIsNone(ready.get("why"), "only an open row with no lane key reads the items unknown")
        self.assertEqual(self.ready_ids(ready), ["c2"])

    def test_age_is_whole_hours_from_updated_at_to_the_live_read(self):
        self.ready_step("c2", order=2)  # 3 h 10 min before the read: age 3
        self.ready_step("c3", order=3, updatedAt=self.before(26 * 60 + 10))  # age 26
        self.known_read()
        page, _ = self.build_from_main("--live", str(self.live))
        ready = self.ready_block(page)
        self.assertEqual(self.ready_ids(ready), ["c2", "c3"])
        self.assertEqual([s["age"] for s in ready["steps"]], [3, 26], "age is whole hours from updatedAt to the read")
        self.assertTrue(all(type(s["age"]) is int for s in ready["steps"]), "an age is an int")

    def test_age_is_none_when_updated_at_is_missing_or_has_no_zone(self):
        self.ready_step("c2", order=2, updatedAt=_ABSENT)
        self.ready_step("c3", order=3, updatedAt=self.before(190).replace("Z", ""))
        self.known_read()
        page, _ = self.build_from_main("--live", str(self.live))
        ready = self.ready_block(page)
        self.assertEqual(self.ready_ids(ready), ["c2", "c3"])
        self.assertEqual([s["age"] for s in ready["steps"]], [None, None], "a missing or zoneless updatedAt has no age")

    def test_each_listed_step_prints_its_age_or_age_unknown(self):
        self.ready_step("c2", order=2)
        self.ready_step("c3", order=3, updatedAt=_ABSENT)
        self.known_read()
        _, out = self.build_from_main("--live", str(self.live))
        self.assertEqual(self.ready_lines(out), ["ready not started: c2 (3h)", "ready not started: c3 (age unknown)"],
                         "one line per listed step, with its age")

    def test_ready_lines_never_change_the_exit_code(self):
        self.ready_step("c2", order=2)
        with self.subTest("ready only"):
            self.known_read()
            _, out = self.build_from_main("--live", str(self.live))
            self.assertEqual(self.ready_lines(out), ["ready not started: c2 (3h)"], "the ready line is printed")
            self.assertEqual(self.code, 0, "a ready line alone exits 0")
        self.ready_step("c3", order=3, status="doing")  # a lane-less doing step is stalled and exits 1
        with self.subTest("ready beside a stalled step"):
            self.known_read()
            _, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
            self.assertEqual(self.ready_lines(out), ["ready not started: c2 (3h)"], "the ready line is printed beside a stall")
            self.assertEqual(self.code, 1, "the stalled step still exits 1")

    def test_ready_status_step_is_not_an_unknown_status_entry_in_the_upkeep(self):
        self.ready_step("c2", order=2, status="ready")
        self.commit_step("c3", status="waiting", order=3)  # control: an unknown status is listed
        self.known_read()
        _, out = self.build_from_main("--live", str(self.live))
        _, detail = self.row(out, StaleInProgress.ROW)
        self.assertIn('c3 (unknown status "waiting")', detail, "control: the row lists the unknown status")
        self.assertNotIn('c2 (unknown status "ready")', detail, "ready is a known status, so the row never lists c2")

    def test_listed_steps_follow_step_order_not_the_step_id(self):
        self.ready_step("c3", order=1)
        self.ready_step("c1", order=2)  # c1 sorts first by id, so only the order puts c3 first
        self.known_read()
        page, _ = self.build_from_main("--live", str(self.live))
        self.assertEqual(self.ready_ids(self.ready_block(page)), ["c3", "c1"], "listed by step order")

    def test_age_floors_to_whole_hours(self):
        self.ready_step("c2", order=2, updatedAt=self.before(220))  # 3 h 40 min floors to 3; rounding would give 4
        self.known_read()
        page, _ = self.build_from_main("--live", str(self.live))
        ready = self.ready_block(page)
        self.assertEqual(self.ready_ids(ready), ["c2"])
        self.assertEqual([s["age"] for s in ready["steps"]], [3], "the age is whole hours, rounded down")

    def test_item_with_an_empty_lane_holds_the_step_back(self):
        self.ready_step("c2", order=2)
        self.ready_step("c3", order=3)  # control
        self.known_read(items=[self.item(4, home="step c2", status="open", lane="")])
        page, _ = self.build_from_main("--live", str(self.live))
        self.assertEqual(self.ready_ids(self.ready_block(page)), ["c3"], "an empty lane is unanswered, so it holds c2 back")

    def test_steps_unknown_prints_one_unknown_ready_line(self):
        self.on_main()
        code, out = run_build("--repo", str(self.repo), "--record-branch", "no-such-branch", "--out", str(self.out))
        self.assertIn(code, (0, None), out)
        self.assertEqual(self.ready_lines(out), ["ready not started: unknown (steps unknown)"],
                         "with no steps, the build prints one unknown ready line")


class UntouchedInLivePhase(UpkeepFixture):
    """The upkeep row `untouched 5 days in a live phase`: each open step in a phase that holds an active step, whose
    updatedAt is STALE_DAYS old or more, or cannot be read. A zoneless, null or int updatedAt lists the step; it never
    crashes the build."""

    ROW = "untouched 5 days in a live phase"

    def test_unreadable_updated_at_lists_the_step_and_does_not_crash(self):
        self.commit_step("live-a", status="active", phase="build", updatedAt=iso_ago(5), order=1)  # control: fresh
        for name, value in (("zoneless", "2026-11-01T10:00:00"), ("null", None), ("int", 1234)):
            with self.subTest(name):
                git(self.repo, "checkout", "-q", "roadmap")
                self.commit_step("bad-b", status="todo", phase="build", updatedAt=value, order=2)
                try:
                    _, out = self.build_from_main()
                except Exception as err:  # the crash is the defect, so it fails by name, not as an error
                    self.fail("upkeep crashed on an updatedAt that is %s: %s: %s" % (name, type(err).__name__, err))
                count, detail = self.row(out, self.ROW)
                self.assertEqual((count, self.entries(detail)), (1, ["bad-b"]),
                                 "the unreadable step is listed, and the fresh active step is not")


class PageRulings(UpkeepFixture):
    """The upkeep row for each closed waiting-page item whose home step is open and cites the item nowhere.
    The step's note, why or ask cites an item with `item <n>` (any case, an optional #). The row reads
    `<step id> (page item <n>)` per item, or one `unknown (<why>)` when the --live file cannot say."""

    ROW = "page rulings not on their step"
    CITE = "Ruling (page item 9): keep"
    UNKNOWN = r"unknown \((?:[^()]|\([^()]*\))*\)"  # one entry, with at most one level of parentheses inside

    def rulings(self, out):
        return self.row(out, self.ROW)

    def listed(self, entries):
        return sorted(entries.split(", ")) if entries else []

    def assert_unknown(self, out):
        """The row reads exactly one unknown entry: never a list, never an empty row. Returns the entry."""
        count, entries = self.rulings(out)
        self.assertEqual(count, 1, out)
        self.assertIsNotNone(re.fullmatch(self.UNKNOWN, entries), entries)
        return entries

    def test_closed_item_whose_step_does_not_cite_it_is_listed(self):
        """The incident: item 9 closed, step c153 open, its note never cites item 9. The file has no
        sessions key and the fixture has no GitHub origin, and the row still reads."""
        self.commit_step("c153", note="Waiting on the cull.")
        self.publish(items=[self.item(9)])
        self.assertEqual(self.rulings(self.out_with_live()), (1, "c153 (page item 9)"))

    def test_the_same_item_cited_in_the_step_note_is_not_listed(self):
        self.commit_step("c153", note=self.CITE)
        self.publish(items=[self.item(9)])
        self.assertEqual(self.rulings(self.out_with_live()), (0, ""))

    def test_a_cite_in_why_or_ask_counts_too(self):
        self.commit_step("c310", note="Waiting.", why=self.CITE)
        self.commit_step("c311", note="Waiting.", ask=self.CITE)
        self.commit_step("c312", note="Waiting.")  # control: listed, so an empty row cannot pass
        self.publish(items=[self.item(9, home=sid) for sid in ("c310", "c311", "c312")])
        self.assertEqual(self.rulings(self.out_with_live()), (1, "c312 (page item 9)"))

    def test_cite_forms_match_the_item_number_only(self):
        forms = {"page item 9": True, "waiting page item 9 a": True, "Item #9": True, "ITEM  9": True,
                 "item 90": False, "item 19": False, "Ruling: keep": False}
        steps = ["c%d" % (320 + i) for i in range(len(forms))]
        for sid, note in zip(steps, forms):
            self.commit_step(sid, note=note)
        self.publish(items=[self.item(9, home=sid) for sid in steps])
        expect = sorted("%s (page item 9)" % sid for sid, cited in zip(steps, forms.values()) if not cited)
        count, entries = self.rulings(self.out_with_live())
        self.assertEqual((count, self.listed(entries)), (len(expect), expect))

    def test_a_cite_clears_only_its_own_item_number(self):
        self.commit_step("c153", note=self.CITE)  # cites item 9 only
        self.publish(items=[self.item(9), self.item(10)])
        count, entries = self.rulings(self.out_with_live())
        self.assertEqual((count, self.listed(entries)), (1, ["c153 (page item 10)"]))

    def test_a_list_of_items_cites_only_the_number_right_after_item(self):
        """Pins current behaviour: "page items 9 and 10" cites neither item, because the cite needs `item`
        directly before the number. "item 9 and 10" cites 9 only, so 10 still lists."""
        self.commit_step("c1", note="page items 9 and 10")
        self.commit_step("c2", note="item 9 and 10", order=2)  # both steps written before the build, which checks out main
        self.publish(items=[self.item(9, home="c1"), self.item(10, home="c1"),
                            self.item(9, home="c2"), self.item(10, home="c2")])
        count, entries = self.rulings(self.out_with_live())
        self.assertEqual((count, self.listed(entries)),
                         (3, sorted(["c1 (page item 9)", "c1 (page item 10)", "c2 (page item 10)"])))

    def test_open_item_is_never_listed(self):
        self.commit_step("c153", note="Waiting.")
        self.commit_step("c154", note="Waiting.", order=2)  # control: closed, so an empty row cannot pass
        self.publish(items=[self.item(9, status="open"), self.item(10, home="c154")])
        self.assertEqual(self.rulings(self.out_with_live()), (1, "c154 (page item 10)"))

    def test_home_that_names_no_step_is_never_listed(self):
        self.commit_step("c154", note="Waiting.")
        self.commit_step("c204", note="Waiting.", order=2)  # open, so "c204 (zoomed in)" fails on the exact compare
        self.publish(items=[self.item(9, home="decision x"), self.item(10, home="c204 (zoomed in)"),
                            self.item(11, home=""), self.item(12, home="c999"), self.item(13, home="c154")])
        count, entries = self.rulings(self.out_with_live())
        self.assertEqual((count, self.listed(entries)), (1, ["c154 (page item 13)"]))

    def test_home_matches_a_step_id_exactly_after_trimming_and_the_step_prefix(self):
        self.commit_step("c153", note="Waiting.")
        self.publish(items=[self.item(9, home="  c153 "), self.item(10, home="step c153"),
                            self.item(11, home="STEP c153"), self.item(12, home="C153")])
        count, entries = self.rulings(self.out_with_live())
        self.assertEqual((count, self.listed(entries)),
                         (3, sorted(["c153 (page item 9)", "c153 (page item 10)", "c153 (page item 11)"])))

    def test_item_whose_step_is_done_is_never_listed(self):
        self.commit_step("c2", status="done", note="Waiting.", order=2)
        self.commit_step("c154", note="Waiting.", order=3)  # control: listed
        self.publish(items=[self.item(9, home="c2"), self.item(10, home="c154")])
        self.assertEqual(self.rulings(self.out_with_live()), (1, "c154 (page item 10)"))

    def test_a_step_that_is_not_done_is_listed_in_any_status(self):
        statuses = ("todo", "doing", "active")
        steps = ["c%d" % (330 + i) for i in range(len(statuses))]
        for i, (sid, status) in enumerate(zip(steps, statuses)):
            self.commit_step(sid, status=status, note="Waiting.", order=2 + i)
        self.publish(items=[self.item(20 + i, home=sid) for i, sid in enumerate(steps)])
        expect = sorted("%s (page item %d)" % (sid, 20 + i) for i, sid in enumerate(steps))
        count, entries = self.rulings(self.out_with_live())
        self.assertEqual((count, self.listed(entries)), (len(expect), expect))

    def test_no_live_file_reads_the_row_unknown_once(self):
        self.commit_step("c153", note="Waiting.")
        _, out = self.build_from_main()
        self.assertIn("--live", self.assert_unknown(out))

    def test_live_file_with_no_items_list_reads_the_row_unknown_once(self):
        self.commit_step("c153", note="Waiting.")
        for label, items in (("missing", None), ("an object", {}), ("a string", "c153")):
            with self.subTest(items=label):
                self.publish(items=items)
                self.assertIn("items", self.assert_unknown(self.out_with_live()))

    def test_an_empty_items_list_reads_zero_not_unknown(self):
        self.publish(items=[])
        self.assertEqual(self.rulings(self.out_with_live()), (0, ""))

    def test_an_item_row_of_the_wrong_shape_reads_the_row_unknown_once(self):
        self.commit_step("c154", note="Waiting.")
        good = self.item(10, home="c154")  # a script that skips the bad row and lists this one fails here
        bad_rows = [
            "c153 (page item 9)",
            {"n": "9", "status": "closed", "home": "c153"},
            {"n": True, "status": "closed", "home": "c153"},
            {"n": 9.0, "status": "closed", "home": "c153"},
            {"n": 9, "status": None, "home": "c153"},
            {"n": 9, "status": "closed", "home": 153},
            {"n": 9, "status": "closed"},
            {"n": 9, "home": "c153"},
        ]
        for bad in bad_rows:
            with self.subTest(row=bad):
                self.publish(items=[good, bad])
                self.assert_unknown(self.out_with_live())

    def test_a_live_file_without_items_still_bakes_live_work(self):
        """Only the page-ruling row reads items: a file without the key keeps its threads and read time."""
        value = self.publish(threads=[{"title": "Build a", "state": "working"}])
        page, _ = self.build_from_main("--live", str(self.live))
        self.assertEqual(self.panel(page)["read"], value["readAt"])
        self.assertEqual([t["title"] for t in build_info(page)["live"]["threads"]], ["Build a"])

    def test_a_read_at_over_an_hour_old_reads_the_row_unknown_once(self):
        self.commit_step("c153", note="Waiting.")
        self.publish(items=[self.item(9)], read_at=iso_ago(5))  # control: a fresh read lists the item
        self.assertEqual(self.rulings(self.out_with_live()), (1, "c153 (page item 9)"))
        for minutes in (61, 120):
            with self.subTest(minutes=minutes):
                self.publish(items=[self.item(9)], read_at=iso_ago(minutes))
                self.assert_unknown(self.out_with_live())

    def test_a_read_at_that_is_not_an_iso_time_reads_the_row_unknown_once(self):
        self.commit_step("c153", note="Waiting.")
        self.publish(items=[self.item(9)])  # control: a fresh read lists the item
        self.assertEqual(self.rulings(self.out_with_live()), (1, "c153 (page item 9)"))
        for read_at in ("yesterday", "2026-13-45T99:00:00Z"):
            with self.subTest(read_at=read_at):
                self.publish(items=[self.item(9)], read_at=read_at)
                self.assert_unknown(self.out_with_live())

    def test_a_read_at_more_than_five_minutes_ahead_reads_the_row_unknown_once(self):
        self.commit_step("c153", note="Waiting.")
        self.publish(items=[self.item(9)], read_at=iso_ago(-2))  # control: within five minutes ahead, the item lists
        self.assertEqual(self.rulings(self.out_with_live()), (1, "c153 (page item 9)"))
        for minutes in (6, 90):
            with self.subTest(minutes=minutes):
                self.publish(items=[self.item(9)], read_at=iso_ago(-minutes))
                self.assert_unknown(self.out_with_live())

    def test_a_skipped_session_row_does_not_make_the_row_unknown(self):
        """The sessions list feeds the stale-step row only. A wrong-shape session row is skipped there,
        and this row still lists its uncited item."""
        self.commit_step("c153", note="Waiting.")
        self.publish(sessions=[session_row("session_test01", "SESSION_STATUS_RUNNING"), "session_test03"],
                     items=[self.item(9)])
        page, out = self.build_from_main("--live", str(self.live))
        self.assertIn("session 2", build_info(page)["live"]["skipped"])
        self.assertEqual(self.rulings(out), (1, "c153 (page item 9)"))


class DatedClaims(UpkeepFixture):
    """The upkeep row for each doing or active step whose note's newest dated claim is STALE_DAYS or more
    whole days old. A claim is `Finding` or `Checked` (any case), then a date with no "." or newline between
    and within 40 characters. The date is `Mon D` or `Month D`, optionally with `, YYYY` or ` YYYY`, or ISO
    `YYYY-MM-DD`. A date with no year takes this year, or the year before if it is in the future. The row
    reads `<step id> (<date as written>)` per step."""

    ROW = "dated claims to re-check before a lane starts"
    MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
              "September", "October", "November", "December")

    def today(self):
        return datetime.datetime.now(datetime.timezone.utc).date()  # the clock the build reads

    def ago(self, days):
        return self.today() - datetime.timedelta(days=days)

    def md(self, d):
        """`Mon D` in English. A fixed table, not strftime: `%-d` is glibc-only and `%b` follows the locale."""
        return "%s %d" % (self.MONTHS[d.month - 1][:3], d.day)

    def full(self, d):
        return "%s %d" % (self.MONTHS[d.month - 1], d.day)

    def claims(self, out):
        return self.row(out, self.ROW)

    def listed(self, entries):
        """Sorted `<id> (<date>)` entries. A date can hold a comma, so match whole entries, not split on commas."""
        return sorted(m.group(0) for m in re.finditer(r"\S+ \([^()]*\)", entries))

    def build(self):
        """The build with no --live file: the row reads notes only, so it must not need the live file."""
        return self.build_from_main()[1]

    def control(self):
        """A doing step whose claim is STALE_DAYS old, so each negative case also has a listed row. Returns its entry."""
        self.commit_step("ctl", status="doing", note="Finding, %s: control." % self.md(self.ago(10)))
        return "ctl (%s)" % self.md(self.ago(10))

    def test_the_incident_shape_is_listed(self):
        """Incident: step r5 is doing, and its only claim is ten days old."""
        self.commit_step("r5", status="doing", note="Finding, %s: ios-adblock, joyous and degen: each a drifted "
                         "impeccable skill." % self.md(self.ago(10)))
        ctl = self.control()
        count, entries = self.claims(self.build())
        self.assertEqual((count, self.listed(entries)), (2, sorted([ctl, "r5 (%s)" % self.md(self.ago(10))])))

    def test_a_newer_claim_wins_whichever_comes_first(self):
        """The newest claim decides, so a fresh Checked clears an old Finding in either order."""
        old = "Finding, %s: drifted skills." % self.md(self.ago(10))
        new = "Checked, %s: gone." % self.md(self.ago(1))
        self.commit_step("newer-first", status="doing", note="%s %s" % (new, old))
        self.commit_step("newer-last", status="doing", note="%s %s" % (old, new))
        ctl = self.control()
        count, entries = self.claims(self.build())
        self.assertEqual((count, self.listed(entries)), (1, [ctl]))

    def test_an_active_step_is_listed(self):
        self.commit_step("a1", status="active", note="Finding, %s: x." % self.md(self.ago(10)))
        ctl = self.control()
        count, entries = self.claims(self.build())
        self.assertEqual((count, self.listed(entries)), (2, sorted([ctl, "a1 (%s)" % self.md(self.ago(10))])))

    def test_todo_done_and_other_statuses_are_never_listed(self):
        stale = "Finding, %s: x." % self.md(self.ago(10))
        for sid, status in (("t1", "todo"), ("d1", "done"), ("b1", "blocked")):
            self.commit_step(sid, status=status, note=stale)
        ctl = self.control()
        count, entries = self.claims(self.build())
        self.assertEqual((count, self.listed(entries)), (1, [ctl]))

    def test_a_gap_over_40_characters_a_period_or_a_newline_does_not_count(self):
        stale = self.md(self.ago(10))
        self.commit_step("far", status="doing", note="Finding, %s%s: x." % ("word " * 12, stale))  # 62 characters between
        self.commit_step("dot", status="doing", note="Finding. %s: x." % stale)
        self.commit_step("newline", status="doing", note="Finding,\n%s: x." % stale)
        self.commit_step("near", status="doing", note="Finding, after the cull, %s: x." % stale)  # 18 between: counts
        ctl = self.control()
        count, entries = self.claims(self.build())
        self.assertEqual((count, self.listed(entries)), (2, sorted([ctl, "near (%s)" % stale])))

    def test_an_iso_date_is_read_as_written(self):
        iso = self.ago(10).isoformat()
        self.commit_step("iso", status="doing", note="Checked %s: x." % iso)
        ctl = self.control()
        count, entries = self.claims(self.build())
        self.assertEqual((count, self.listed(entries)), (2, sorted([ctl, "iso (%s)" % iso])))

    def test_a_yearless_date_in_the_future_takes_the_year_before(self):
        # Feb 29 has no year before a common year, so the case steps past it.
        future = next(d for d in (self.today() + datetime.timedelta(days=n) for n in range(3, 9))
                      if (d.month, d.day) != (2, 29))
        self.commit_step("fut", status="doing", note="Finding, %s: x." % self.md(future))
        ctl = self.control()
        count, entries = self.claims(self.build())
        self.assertEqual((count, self.listed(entries)), (2, sorted([ctl, "fut (%s)" % self.md(future)])))

    def test_an_explicit_year_is_kept_as_written(self):
        day = self.ago(10)
        self.commit_step("comma", status="doing", note="Finding, %s, %d: x." % (self.md(day), day.year))
        self.commit_step("space", status="doing", note="Checked %s %d: x." % (self.md(day), day.year))
        ctl = self.control()
        count, entries = self.claims(self.build())
        self.assertEqual((count, self.listed(entries)), (3, sorted([
            ctl, "comma (%s, %d)" % (self.md(day), day.year), "space (%s %d)" % (self.md(day), day.year)])))

    def test_each_written_form_is_read_as_the_spec_says(self):
        """One step per form, one build. A form that lists gives its date as written; the rest give None."""
        day = self.ago(10)
        forms = [  # (step id, note and why, date as written or None when the step must not list)
            ("full", {"note": "Finding, %s: x." % self.full(day)}, self.full(day)),
            ("upper", {"note": "checked %s: x." % self.md(day).upper()}, self.md(day).upper()),
            ("five", {"note": "Finding, %s: x." % self.md(self.ago(5))}, self.md(self.ago(5))),
            ("four", {"note": "Finding, %s: x." % self.md(self.ago(4))}, None),
            ("fresh", {"note": "Checked %s: x." % self.md(self.ago(1))}, None),
            ("no-claim", {"note": "Waiting on the cull. The lane ran 10 days ago."}, None),
            ("word-only", {"note": "Finding, nothing dated here."}, None),
            ("why-only", {"note": "Waiting on the cull.", "why": "Finding, %s: x." % self.md(day)}, None),
        ]
        for sid, fields, _ in forms:
            self.commit_step(sid, status="doing", **fields)
        ctl = self.control()
        expect = sorted([ctl] + ["%s (%s)" % (sid, date) for sid, _, date in forms if date])
        count, entries = self.claims(self.build())
        self.assertEqual((count, self.listed(entries)), (len(expect), expect))

    def test_a_hyphenated_word_is_not_a_claim(self):
        """`checked` or `finding` inside a hyphenated word is not a claim. Each note holds a stale date after it."""
        stale = self.md(self.ago(10))
        self.commit_step("h1", status="doing", note="lane c146-checked-map (coordinator, %s 16:13 CDT)" % stale)
        self.commit_step("h2", status="doing", note="Re-checked %s: x." % stale)
        self.commit_step("h3", status="doing", note="finding-x %s: x." % stale)
        ctl = self.control()
        count, entries = self.claims(self.build())
        self.assertEqual((count, self.listed(entries)), (1, [ctl]))

    def test_a_lowercase_may_is_not_a_month(self):
        """Lowercase `may` is an ordinary word, so `may 2` is no date. Capitalized `May 2` still is. The day is
        20 on the days when May 2 is too recent to be stale, so the lowercase text would be stale if read."""
        today = self.today()
        day = 20 if datetime.date(today.year, 5, 2) <= today <= datetime.date(today.year, 5, 6) else 2
        self.commit_step("lc", status="doing", note="Finding: this may %d lanes re-run." % day)
        self.commit_step("cap", status="doing", note="Finding, May %d: x." % day)
        ctl = self.control()
        count, entries = self.claims(self.build())
        self.assertEqual((count, self.listed(entries)), (2, sorted([ctl, "cap (May %d)" % day])))


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

    def build_live(self, expect=(0, None)):
        """(page, out) of a build from main, with a live file that lists no sessions."""
        self.publish(sessions=[])
        return self.build_from_main("--live", str(self.live), expect=expect)

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
        _, out = self.build_live(expect=(1,))
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
        _, out = self.build_live(expect=(1,))
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
        _, out = self.build_live(expect=(1,))
        self.assertEqual(self.row(out, self.UNLANED), (1, "c2 (set to done: landed in #13)"))

    def test_landed_feel_fix_with_a_valid_check_is_still_listed_as_set_to_done(self):
        self.land("c1", 12, feel=True, deviceCheck=self.CHECK)
        _, out = self.build_live(expect=(1,))
        self.assertEqual(self.row(out, self.UNLANED), (1, "c1 (set to done: landed in #12)"))

    def test_feel_fix_not_yet_landed_still_reads_set_to_todo(self):
        git(self.repo, "checkout", "-q", "roadmap")
        self.commit_step("c1", status="doing", feel=True)
        _, out = self.build_live(expect=(1,))
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
        # The pair check reads readAt and pulls only. publish() leaves the sessions key out, so the check must not need it.
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

    def test_ready_step_with_an_open_pull_gets_the_pair_line_like_todo(self):
        self.commit_step("r8")  # control: a todo step with an open pull
        self.commit_step("r9", status="ready", order=2)
        self.publish(sessions=[], pulls=[{"number": 80, "title": "r8 lane", "branch": "r8"},
                                         {"number": 90, "title": "r9 lane", "branch": "r9"}])
        _, out = self.build_from_main("--live", str(self.live), expect=(1,))
        self.assertEqual(self.pair_lines(out), ["r8 (#80)", "r9 (#90)"], "a ready step is a todo step for the pair line")


class ReadyAndDraftRows(UpkeepFixture):
    """Two upkeep rows (spec part B). `ready todo steps` lists each todo step whose note has the sentence `Ready.`,
    with no live-phase filter. `draft PRs over 12 h with no live lane` lists each draft pull created more than
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

    def test_ready_status_step_with_a_ready_sentence_is_listed_too(self):
        self.commit_step("t-todo", note="Ready.", order=2)  # control: listed
        self.commit_step("r-ready", status="ready", note="Ready.", order=3)
        _, out = self.build_from_main()
        count, detail = self.row(out, self.READY)
        self.assertEqual((count, self.entries(detail)), (2, ["r-ready", "t-todo"]), "ready reads as todo in this row")

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


class DoneWithoutCheck(UpkeepFixture):
    """The upkeep row `done without check`, the last row. It reads the done steps whose updatedAt is on or after
    build.DONE_CHECK_SINCE (an ISO UTC time), and lists each whose note, why and ask (joined) fail the close check:
    no Done check named, `<id>`; a Done check named, but no sentence holds `green on main` or `met on main` (whole
    words, any case) with a source (`#<digits>`, `PR <n>`, a /pull/<n> URL, or a 6-40 character hex commit hash with a digit), `<id> (not shown green on main)`;
    an updatedAt that is missing or unparsable, `<id> (updatedAt unreadable)`. A sentence ends at ". " or at the end
    of the text. The row reads the step files only, so it needs no --live file."""

    ROW = "done without check"
    NOT_SHOWN = " (not shown green on main)"
    UNREADABLE = " (updatedAt unreadable)"
    HASH_40 = "0123456789abcdef0123456789abcdef01234567"
    # The fifteen rows before this one, in print order. The control case reads them.
    OLD_ROWS = ["notes over %d words" % build.NOTE_WORDS, "untouched %d days in a live phase" % build.STALE_DAYS,
                "no note in a live phase", "new in top %d with no placement line" % build.TOP,
                "in progress with no live lane or open PR", "ready todo steps",
                "draft PRs over %d h with no live lane" % build.STALE_DRAFT_HOURS,
                "dated claims to re-check before a lane starts", "page rulings not on their step",
                build.IDLE_LANES_LINE, "landed, waiting for a device trial", "landed, waiting for triage to close",
                "Step trailers naming no step", "live threads naming no open step", "live file entries skipped"]
    # A build without the constant gets this value, so a case fails on its own assert, not on an AttributeError.
    # test_the_constant_is_an_iso_utc_time names the missing constant.
    SINCE_FALLBACK = "2000-01-01T00:00:00Z"

    def since(self):
        """build.DONE_CHECK_SINCE, read through getattr for the reason above."""
        return getattr(build, "DONE_CHECK_SINCE", self.SINCE_FALLBACK)

    def since_dt(self):
        raw = self.since()
        try:
            return datetime.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            self.fail("build.DONE_CHECK_SINCE is not an ISO time: %r" % (raw,))

    def just_before(self):
        """The whole second before the constant, as an ISO UTC time."""
        at = self.since_dt()
        at = at if at.tzinfo else at.replace(tzinfo=datetime.timezone.utc)
        return (at.astimezone(datetime.timezone.utc) - datetime.timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def done_step(self, updated=None, **fields):
        """A done step, in scope by default: updatedAt is the constant. Each field given replaces the default."""
        step = {"title": "t", "status": "done", "phase": "cleanup", "order": 1,
                "updatedAt": self.since() if updated is None else updated}
        step.update(fields)
        return step

    def commit_steps(self, steps):
        """Write each {id: step} on the record branch, then commit once. Commit before the build: build_from_main
        leaves HEAD on main, where the step folder is not."""
        for sid, step in steps.items():
            self.write_step(sid, step)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "steps")

    def listed(self):
        """(count, sorted entries) of the row, from a build of main with no --live file."""
        _, out = self.build_from_main()
        count, detail = self.row(out, self.ROW)
        return count, self.entries(detail)

    def test_the_row_is_the_last_row(self):
        self.commit_steps({"bad": self.done_step(note="Shipped.")})
        _, out = self.build_from_main()
        self.assertEqual(list(self.summary_counts(out))[-1], self.ROW)

    def test_the_fifteen_rows_before_it_keep_their_order(self):
        # Control, green on main: the rows before this one print as they did, with or without this row.
        self.commit_steps({"bad": self.done_step(note="Shipped.")})
        _, out = self.build_from_main()
        self.assertEqual(list(self.summary_counts(out))[:len(self.OLD_ROWS)], self.OLD_ROWS)

    def test_the_constant_is_an_iso_utc_time(self):
        self.assertTrue(hasattr(build, "DONE_CHECK_SINCE"), "build has no DONE_CHECK_SINCE")
        self.assertEqual(self.since_dt().utcoffset(), datetime.timedelta(0),
                         "build.DONE_CHECK_SINCE is not UTC: %r" % (self.since(),))

    def test_a_done_step_with_no_done_check_is_listed_plain(self):
        self.commit_steps({
            "no-check": self.done_step(note="Shipped the feed."),
            "blank": self.done_step(note="", why="", ask=""),
            "no-keys": self.done_step(),  # no note, why or ask key at all
        })
        _, entries = self.listed()
        self.assertEqual(entries, ["blank", "no-check", "no-keys"], "a done step with no Done check is not listed plain")

    def test_a_done_step_updated_before_the_constant_is_never_listed(self):
        self.commit_steps({
            "on-the-line": self.done_step(updated=self.since(), note="Shipped."),
            "one-second-early": self.done_step(updated=self.just_before(), note="Shipped."),
            "early-named": self.done_step(updated=self.just_before(), note="Done check: X."),
        })
        _, entries = self.listed()
        self.assertIn("on-the-line", entries)  # scope first: the step on the constant is in scope and listed
        self.assertEqual(entries, ["on-the-line"], "a done step updated before the constant is listed")

    def test_only_done_steps_are_listed(self):
        self.commit_steps({
            "done": self.done_step(note="Shipped."),
            "todo": self.done_step(status="todo", note="Shipped."),
            "doing": self.done_step(status="doing", note="Shipped."),
            "active": self.done_step(status="active", note="Shipped."),
            "todo-unreadable": self.done_step(status="todo", updated="yesterday", note="Shipped."),
        })
        _, entries = self.listed()
        self.assertIn("done", entries)
        self.assertEqual(entries, ["done"], "a step that is not done is listed")

    def test_an_unreadable_updated_at_is_listed_as_unreadable(self):
        missing = self.done_step(note="Shipped.")
        del missing["updatedAt"]
        self.commit_steps({
            "readable": self.done_step(note="Shipped."),
            "missing-at": missing,
            "word-at": self.done_step(updated="yesterday", note="Shipped."),
            "bad-month": self.done_step(updated="2026-13-45T00:00:00Z", note="Shipped."),
        })
        _, entries = self.listed()
        self.assertIn("readable", entries)
        self.assertEqual(entries, sorted(["readable", "missing-at" + self.UNREADABLE, "word-at" + self.UNREADABLE,
                                          "bad-month" + self.UNREADABLE]),
                         "a done step with an unreadable updatedAt is not listed as unreadable")

    def test_a_well_formed_close_is_not_listed(self):
        # False-alarm class: a Done check, and a green-on-main sentence that holds a source, are not listed.
        closes = {"colon-ref": "Done check: X. Green on main: #1312.",
                  "met-short-hash": "Done check met on main (a1b2c3d).",
                  "any-case": "DONE CHECK: X. GREEN ON MAIN: #1312.",
                  "met-long-hash": "Done check: X. Met on main (%s)." % self.HASH_40}
        steps = {"bad-control": self.done_step(note="Shipped.")}
        steps.update({sid: self.done_step(note=note) for sid, note in closes.items()})
        self.commit_steps(steps)
        _, entries = self.listed()
        self.assertIn("bad-control", entries)  # scope first: the in-scope close with no check is listed
        self.assertEqual(entries, ["bad-control"], "a well-formed close is listed")

    def test_a_named_check_with_no_green_on_main_sentence_is_listed_as_not_shown(self):
        steps = {"named-only": self.done_step(note="Done check: the feed loads."),
                 "named-upper": self.done_step(note="DONE CHECK: the feed loads."),
                 "named-in-why": self.done_step(note="Shipped.", why="done check: the feed loads."),
                 "named-in-ask": self.done_step(note="Shipped.", ask="Done check: the feed loads."),
                 "plain-control": self.done_step(note="Shipped.")}
        self.commit_steps(steps)
        _, entries = self.listed()
        self.assertIn("plain-control", entries)
        expected = sorted(["plain-control"] + [sid + self.NOT_SHOWN for sid in
                                               ("named-only", "named-upper", "named-in-why", "named-in-ask")])
        self.assertEqual(entries, expected, "a named check with no green-on-main sentence is not listed as not shown")

    def test_the_source_must_share_the_green_sentence(self):
        # Miss class: a source in another sentence does not back a green-on-main sentence.
        self.commit_steps({
            "ok-same-sentence": self.done_step(note="Done check: X. Green on main: #1312."),
            "no-source": self.done_step(note="Done check: X. Green on main."),
            "source-after": self.done_step(note="Done check: X. Green on main. Fixed in #1312."),
            "source-before": self.done_step(note="Done check: X. Fixed in #1312. Green on main."),
        })
        _, entries = self.listed()
        self.assertIn("no-source" + self.NOT_SHOWN, entries)
        self.assertEqual(entries, sorted(["no-source" + self.NOT_SHOWN, "source-after" + self.NOT_SHOWN,
                                          "source-before" + self.NOT_SHOWN]),
                         "a green-on-main sentence with its source in another sentence is not listed")

    def test_the_phrase_must_be_whole_words(self):
        # Miss class: `green on main` must be whole words. `met on main` with a source still counts.
        self.commit_steps({
            "ok-met": self.done_step(note="Done check: X. Met on main: #1312."),
            "red-green": self.done_step(note="Done check: red on main and green on the fix #1312."),
            "mainline": self.done_step(note="Done check: X. Green on mainline #1312."),
            "greens": self.done_step(note="Done check: X. Greens on main #1312."),
        })
        _, entries = self.listed()
        self.assertIn("mainline" + self.NOT_SHOWN, entries)
        self.assertEqual(entries, sorted(["red-green" + self.NOT_SHOWN, "mainline" + self.NOT_SHOWN,
                                          "greens" + self.NOT_SHOWN]),
                         "a green-on-main phrase that is not whole words is not listed as not shown")

    def test_the_source_must_have_the_shape_of_a_ref(self):
        # Miss class: `#` with no digits and a 41-character hash are not sources. 6 to 40 hex characters with a
        # digit are, as lint/report_guard.py DONE_REF_RE takes them (one home).
        self.commit_steps({
            "ok-seven": self.done_step(note="Done check: X. Green on main: a1b2c3d."),
            "ok-six": self.done_step(note="Done check: X. Green on main: a1b2c3."),
            "ok-forty": self.done_step(note="Done check: X. Green on main: %s." % self.HASH_40),
            "hash-only": self.done_step(note="Done check: X. Green on main: #."),
            "forty-one": self.done_step(note="Done check: X. Green on main: %s0." % self.HASH_40),
        })
        _, entries = self.listed()
        self.assertIn("hash-only" + self.NOT_SHOWN, entries)
        self.assertEqual(entries, sorted(["hash-only" + self.NOT_SHOWN, "forty-one" + self.NOT_SHOWN]),
                         "a source that is not a PR number or a 6-40 character hash with a digit is not accepted")

    def test_a_negated_green_on_main_sentence_is_listed_as_not_shown(self):
        # Miss class: a negator (not, never, no, isn't, yet) in the same clause, before `green on main` or
        # `met on main`, says the check is not shown green, even with a source after it. A clause breaks at `,` `;` `:`.
        self.commit_steps({
            "bad-control": self.done_step(note="Shipped."),
            "not-met": self.done_step(note="Done check not met on main, see #1312."),
            "not-green-yet": self.done_step(note="Done check: X. Not green on main yet, see #1312."),
            "never-met": self.done_step(note="Done check: X. Never met on main: #1312."),
            "no-green": self.done_step(note="Done check: X. No green on main: #1312."),
            "isnt-green": self.done_step(note="Done check: X. Isn't green on main: #1312."),
            "after-break-not": self.done_step(note="Done check: X, not green on main #6."),
        })
        _, entries = self.listed()
        self.assertIn("bad-control", entries)  # scope first: the in-scope close with no check is listed
        self.assertEqual(entries, sorted(["bad-control"] + [sid + self.NOT_SHOWN for sid in
                                                            ("not-met", "not-green-yet", "never-met", "no-green",
                                                             "isnt-green", "after-break-not")]),
                         "a green-on-main sentence with a negator before the phrase is listed as shown green")

    def test_a_negator_in_an_earlier_clause_does_not_negate_green_on_main(self):
        # Miss class: a negator counts only in the clause of `green on main` or `met on main`. A clause breaks at
        # `,` `;` `:` (lint/report_guard.py ANSWERED_CLAUSE_BREAK_RE), so `no`, `never` or `can't` before a break
        # says nothing about the phrase after it.
        self.commit_steps({
            "bad-control": self.done_step(note="Shipped."),
            "comma-no": self.done_step(note="Done check no longer red, green on main: #1"),
            "comma-never": self.done_step(note="Done check was never red, met on main #5"),
            "semicolon-no": self.done_step(note="No failures; Done check green on main: #12"),
            "semicolon-cant": self.done_step(note="Done check can't fail; green on main #3"),
            "colon-never": self.done_step(note="Done check never failed: green on main #2"),
        })
        _, entries = self.listed()
        self.assertIn("bad-control", entries)  # scope first: the in-scope close with no check is listed
        self.assertEqual(entries, ["bad-control"],
                         "a negator in an earlier clause is read as negating green on main")

    def test_a_green_on_main_claim_with_a_future_marker_is_listed_as_not_shown(self):
        # Miss class: a sentence whose green-on-main claim has a future marker in the same sentence (will, expected,
        # once, pending, or after ... merge, merges or lands) claims a check that is not green yet, even with a source.
        self.commit_steps({
            "bad-control": self.done_step(note="Shipped."),
            "will-after-merge": self.done_step(note="Done check not yet met — will be green on main after the merge #5"),
            "expected": self.done_step(note="Done check: not yet; green on main expected #5"),
            "once-lands": self.done_step(note="Done check: X. Green on main once #12 lands."),
            "pending": self.done_step(note="Done check pending: green on main #5."),
            "after-merges": self.done_step(note="Done check: X. Green on main after the fix merges #12."),
        })
        _, entries = self.listed()
        self.assertIn("bad-control", entries)  # scope first: the in-scope close with no check is listed
        self.assertEqual(entries, sorted(["bad-control"] + [sid + self.NOT_SHOWN for sid in
                                                            ("will-after-merge", "expected", "once-lands", "pending",
                                                             "after-merges")]),
                         "a green-on-main claim with a future marker in its sentence is shown green")

    def test_a_green_on_main_claim_with_no_future_marker_is_not_listed(self):
        # Control, green now: a present or past claim with a source is shown green. A future word in another
        # sentence does not reach the green-on-main sentence.
        self.commit_steps({
            "bad-control": self.done_step(note="Shipped."),
            "no-longer": self.done_step(note="Done check no longer red, green on main: #1"),
            "colon-ref": self.done_step(note="Done check: X. Green on main: #1312."),
            "merged-after": self.done_step(note="Done check green on main after fix #12 merged."),
            "future-elsewhere": self.done_step(note="Done check: will fix later. Green on main: #5."),
        })
        _, entries = self.listed()
        self.assertIn("bad-control", entries)  # scope first: the in-scope close with no check is listed
        self.assertEqual(entries, ["bad-control"],
                         "a green-on-main claim with no future marker in its sentence is listed as not shown")

    def test_a_negator_after_a_dash_still_negates_green_on_main(self):
        # Miss class: a dash breaks a clause, so the negator after it sits in the clause of `met on main`.
        self.commit_steps({
            "bad-control": self.done_step(note="Shipped."),
            "dash-not": self.done_step(note="Done check — not met on main, see #7"),
        })
        _, entries = self.listed()
        self.assertIn("bad-control", entries)  # scope first: the in-scope close with no check is listed
        self.assertEqual(entries, sorted(["bad-control", "dash-not" + self.NOT_SHOWN]),
                         "a negator after a dash is not read as negating met on main")

    def test_a_pr_word_or_pull_url_ref_shows_green_on_main(self):
        # The ref forms lint/report_guard.py DONE_REF_RE accepts: `PR <n>` and a /pull/<n> URL.
        self.commit_steps({
            "bad-control": self.done_step(note="Shipped."),
            "pr-word": self.done_step(note="Done check: X. Green on main: PR 1312."),
            "pull-url": self.done_step(note="Done check: X. Green on main: https://github.com/o/r/pull/1312."),
        })
        _, entries = self.listed()
        self.assertIn("bad-control", entries)  # scope first: the in-scope close with no check is listed
        self.assertEqual(entries, ["bad-control"], "a green-on-main sentence with a PR ref is listed as not shown")

    def test_a_hex_letter_word_is_no_commit_ref(self):
        # Miss class: `effaced` is hex letters with no digit. DONE_REF_RE needs a digit in a hex run, so it is no ref.
        self.commit_steps({
            "bad-control": self.done_step(note="Shipped."),
            "effaced": self.done_step(note="Done check met on main, effaced."),
        })
        _, entries = self.listed()
        self.assertIn("bad-control", entries)  # scope first: the in-scope close with no check is listed
        self.assertEqual(entries, sorted(["bad-control", "effaced" + self.NOT_SHOWN]),
                         "a hex-letter word with no digit is read as a commit ref")

    def test_done_checks_without_the_colon_form_counts_as_unnamed(self):
        self.commit_steps({
            "plural": self.done_step(note="Done checks: green on main #1312."),
            "no-name": self.done_step(note="Green on main: #1312."),
        })
        _, entries = self.listed()
        self.assertEqual(entries, ["no-name", "plural"], "a `Done checks` phrase is read as a named check")

    def test_no_done_step_in_scope_reads_zero_with_no_detail(self):
        self.commit_steps({
            "open": self.done_step(status="todo", note="Shipped."),
            "old": self.done_step(updated=self.just_before(), note="Shipped."),
        })
        _, out = self.build_from_main()
        self.assertEqual(self.row(out, self.ROW), (0, ""))

    def test_full_size_fixture_lists_every_bad_close_and_no_good_one(self):
        steps, bad = {}, []
        for n in range(120):
            steps["bad-%03d" % n] = self.done_step(note="Shipped.")
            steps["good-%03d" % n] = self.done_step(note="Done check: X. Green on main: #1312.")
            bad.append("bad-%03d" % n)
        self.commit_steps(steps)
        count, entries = self.listed()
        self.assertEqual((count, entries), (120, bad), "the full-size fixture lists the wrong entries")


def baked(text, key):
    """The JSON value right after `key` in a page or a block. The data is plain JSON in a script."""
    at = text.index(key) + len(key)
    return json.JSONDecoder().raw_decode(text, at)[0]


class BlockOnly(Fixture):
    """--block writes only the roadmap data block, for the page writer to splice in
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

    def test_block_bakes_the_ready_view_unknown_without_a_live_file(self):
        build_block = baked(self.block_from_main(), "window.ROADMAP_BUILD = ")
        self.assertIn("ready", build_block, "the block has no ready view")
        ready = build_block["ready"]
        self.assertTrue(str(ready.get("why")).startswith("unknown (no --live file"), ready)
        self.assertIsNone(ready.get("steps"), "an unknown read lists no steps, never []")

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

    def test_waiting_page_is_the_forks_in_its_worktree_and_mains_on_the_checkout(self):
        self.assertEqual(layout.waiting_page(str(self.fork)), self.FORK_URL)
        self.assertEqual(layout.waiting_page(str(self.repo)), self.MAIN_URL)

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


class MockupFiles(UpkeepFixture):
    """The mockup check of the build. Only open steps are judged. A step's note, why or ask that cites an item by its
    mockup id (item<N>-<letter>, a whole token) needs a `mockups` entry, {"<id>": "<path>"}. The one mockup home is the
    repo's design folder, and the file must be on origin: any remote-tracking ref under refs/remotes/origin/, as a
    fetch leaves it. An absent path is a miss, and so is a folder or a link at it on origin. A miss prints
    `mockup with no file: <step> <id>` for each id, writes the page, and the build exits 1. The miss line names
    `git fetch`, since a stale or unfetched origin ref reads as a miss. A path that origin cannot
    show reads unknown: `mockup file unread: <step> <id> (<why>)`, exit 0. Unknown covers no origin ref, a shallow
    checkout, an unreadable layout and a failed git read; empty git output means absent, a failed read means unknown.
    The check starts at most four git processes, however many entries and origin refs there are.
    The machine-home form is refused. A step with no mockup passes. HOME is this case's own folder, so no case reads
    or writes the real home. The repo is "fixture" (UpkeepFixture's origin)."""

    MISS = "mockup with no file"
    UNREAD = "mockup file unread"
    MACHINE = "fixture-imports"
    MACHINE_ITEM = "~/Developer/fixture-imports/item48/a.html"
    WIN_MACHINE_ITEM = "C:\\Users\\x\\Developer\\fixture-imports\\item48\\a.html"
    APP_SUPPORT = "~/Library/Application Support/Claude-Work/side-session-notes/abc123/a.html"
    SHOT_URL = "https://claude.ai/artifact/0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d/asset/shot.png"
    DESIGN_ITEM = "docs/design/item48/a.html"

    def setUp(self):
        super().setUp()
        self.home = pathlib.Path(self.tmp.name) / "home"
        self.home.mkdir()
        patch = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        patch.start()
        self.addCleanup(patch.stop)

    def machine_item(self):
        """Make the machine home's item file: the folder and the file, on this run's home."""
        path = self.home / "Developer" / self.MACHINE / "item48" / "a.html"
        path.parent.mkdir(parents=True)
        path.write_text("<p>mockup</p>\n", encoding="utf-8")

    def commit_design(self, rel, branch="main", new=False):
        """Commit one file under the checkout's design folder on `branch`, made from main when `new`. The file is in git
        only once it is committed."""
        git(self.repo, "checkout", "-q", *(["-b", branch, "main"] if new else [branch]))
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<p>mockup</p>\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "design " + rel)

    def fetch_origin(self, branch, name=None):
        """Make origin readable: the remote-tracking ref `name` (default `branch`) at `branch`'s tip, as a fetch leaves it.
        With no such ref the origin cannot be read, and a design entry reads unknown."""
        git(self.repo, "update-ref", "refs/remotes/origin/" + (name or branch), branch)

    def make_shallow(self):
        """Mark the checkout shallow at origin/main's tip, the way a shallow clone is marked: its history stops there."""
        tip = git(self.repo, "rev-parse", "origin/main").strip()
        (self.repo / ".git" / "shallow").write_text(tip + "\n", encoding="utf-8")

    def origin_link(self, rel, target):
        """Make origin/main hold a link at `rel` that names `target`. The commit is built on a temporary index, so the
        checkout's index and files stay as they were, and no link is made on this machine (a Windows run needs none)."""
        folder = pathlib.Path(self.tmp.name)
        env = {"GIT_INDEX_FILE": str(folder / "link.index")}
        (folder / "target.txt").write_text(target, encoding="utf-8")
        blob = git(self.repo, "hash-object", "-w", str(folder / "target.txt")).strip()
        git(self.repo, "read-tree", "main", env=env)
        git(self.repo, "update-index", "--add", "--cacheinfo", "120000,%s,%s" % (blob, rel), env=env)
        tree = git(self.repo, "write-tree", env=env).strip()
        commit = git(self.repo, "commit-tree", tree, "-p", "main", "-m", "link " + rel).strip()
        git(self.repo, "update-ref", "refs/remotes/origin/main", commit)

    def failing_origin_git(self, verbs=("cat-file", "ls-tree")):
        """A patch of the build's git read. A read of an origin ref by one of `verbs` (None: any verb) returns None, as a
        failed read does; every other read goes to git. An origin ref counts in the argv or on stdin, since the batched
        type read passes its refs on stdin. Empty output means the path is absent, and None means the read failed."""
        real = build.git

        def read(repo, *args, stdin=None):
            named = any("refs/remotes/origin/" in arg for arg in args) or "refs/remotes/origin/" in (stdin or "")
            if args and named and (verbs is None or args[0] in verbs):
                return None
            return real(repo, *args, stdin=stdin)
        return mock.patch.object(build, "git", read)

    def check_starts(self):
        """One build, with its mockup check wrapped to count the git processes the check starts. Each process is counted
        at subprocess.Popen, the one start every helper of the build reaches, so a git call made any way is counted.
        The rest of the build is outside the count. Returns (build output, the check's (misses, unread), the git argv
        the check started). The check's result is None when the check did not run."""
        real = build.mockup_misses
        seen = {}

        def check(repo, steps):
            with mock.patch.object(subprocess, "Popen", wraps=subprocess.Popen) as popen:
                seen["result"] = real(repo, steps)
            seen["argv"] = [c.args[0] for c in popen.call_args_list if c.args and c.args[0][:1] == ["git"]]
            return seen["result"]

        with mock.patch.object(build, "mockup_misses", check):
            _, out = self.build_from_main(expect=(1,))
        return out, seen.get("result"), seen.get("argv", [])

    def write_extras(self, text):
        """The checkout's extras file, as given. Write it after the commits: their `git add -A` would stage it."""
        path = self.repo / ".claude" / "layout-extras.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def miss_lines(self, out):
        """The text after the prefix of each miss line, in printed order: the step and id, then any remedy."""
        return re.findall(r"^%s: (.*)$" % re.escape(self.MISS), out, re.M)

    def misses(self, out):
        """The "<step> <mockup id>" of each miss line, in printed order. Words after the id, a remedy, do not change it."""
        return [" ".join(line.split()[:2]) for line in self.miss_lines(out)]

    def unread_ids(self, out):
        """The "<step> <mockup id>" of each line the build could not read, in printed order."""
        return re.findall(r"^%s: (\S+ \S+) \(" % re.escape(self.UNREAD), out, re.M)

    def steps_line(self, out, count):
        """Scope first: the build read `count` steps, so an empty miss list is not a build that read nothing."""
        self.assertIn("%s: %d steps" % (self.out.name, count), out, "the build did not read the steps")

    def test_an_item_cited_in_the_note_with_no_mockup_is_a_miss_and_the_page_is_written(self):
        self.commit_step("c1", title="Item forty eight picker", note="Shape the item48-a picker.")
        page, out = self.build_from_main(expect=(1,))
        self.steps_line(out, 1)
        self.assertIn("Item forty eight picker", page, "the red build did not write the page")
        self.assertEqual(self.misses(out), ["c1 item48-a"])

    def test_an_item_cited_in_why_with_no_mockup_is_a_miss(self):
        self.commit_step("c1", why="The item49-b option has no picture.")
        _, out = self.build_from_main(expect=(1,))
        self.steps_line(out, 1)
        self.assertEqual(self.misses(out), ["c1 item49-b"])

    def test_an_item_cited_in_ask_with_no_mockup_is_a_miss(self):
        self.commit_step("c1", ask="Which of item48-a or item48-b?")
        _, out = self.build_from_main(expect=(1,))
        self.steps_line(out, 1)
        self.assertEqual(self.misses(out), ["c1 item48-a", "c1 item48-b"])

    def test_a_cite_inside_a_longer_token_is_not_a_mockup_id(self):
        self.commit_step("c1", title="Lookalike ids", note="Compare 1item48-a, xitem48-a and item48-ab.")
        page, out = self.build_from_main(expect=(0,))
        self.steps_line(out, 1)
        self.assertIn("Lookalike ids", page, "the build did not read the step")
        self.assertEqual(self.misses(out), [])

    def test_a_step_with_no_mockup_passes(self):
        self.commit_step("c1", title="Plain step", note="No picture is cited here.")
        page, out = self.build_from_main(expect=(0,))
        self.steps_line(out, 1)
        self.assertIn("Plain step", page, "the build did not read the step")
        self.assertEqual(self.misses(out), [])

    def test_an_entry_outside_the_mockup_homes_is_a_miss(self):
        self.commit_step("c1", note="Shape the item48-a picker.", mockups={"item48-a": self.APP_SUPPORT})
        _, out = self.build_from_main(expect=(1,))
        self.steps_line(out, 1)
        self.assertEqual(self.misses(out), ["c1 item48-a"])

    def test_an_image_hosted_as_an_artifact_asset_is_a_miss(self):
        self.commit_step("c1", note="Shape the item48-a picker.", mockups={"item48-a": self.SHOT_URL})
        _, out = self.build_from_main(expect=(1,))
        self.steps_line(out, 1)
        self.assertEqual(self.misses(out), ["c1 item48-a"])

    def test_a_design_entry_whose_file_is_not_on_origin_is_a_miss(self):
        self.commit_step("c1", note="Shape the item48-a picker.", mockups={"item48-a": self.DESIGN_ITEM})
        self.fetch_origin("main")  # origin is readable, and it lacks the file
        _, out = self.build_from_main(expect=(1,))
        self.steps_line(out, 1)
        self.assertEqual(self.misses(out), ["c1 item48-a"])

    def test_a_miss_line_names_git_fetch_as_the_remedy(self):
        self.commit_step("c1", note="Shape the item48-a picker.", mockups={"item48-a": self.DESIGN_ITEM})
        self.fetch_origin("main")  # origin is readable and lacks the file: a stale or unfetched origin ref reads as a miss
        _, out = self.build_from_main(expect=(1,))
        self.steps_line(out, 1)
        self.assertEqual(self.misses(out), ["c1 item48-a"], "the miss is not reported")
        for line in self.miss_lines(out):
            self.assertIn("git fetch", line, "the miss line names no `git fetch`, so a stale origin ref reads as a broken file")

    def test_a_design_entry_whose_file_is_on_origin_passes(self):
        self.commit_step("c1", title="Design held", note="Shape the item48-a picker.", mockups={"item48-a": self.DESIGN_ITEM})
        self.commit_design(self.DESIGN_ITEM)
        self.fetch_origin("main")
        page, out = self.build_from_main(expect=(0,))
        self.steps_line(out, 1)
        self.assertIn("Design held", page, "the build did not read the step")
        self.assertEqual(self.misses(out), [])
        self.assertEqual(self.unread_ids(out), [])

    def test_a_machine_home_entry_is_a_miss_even_when_its_file_is_there(self):
        self.machine_item()
        self.commit_step("c1", note="Shape the item48-a picker.", mockups={"item48-a": self.MACHINE_ITEM})
        self.fetch_origin("main")  # origin is readable, so the refusal is not an unknown
        _, out = self.build_from_main(expect=(1,))
        self.steps_line(out, 1)
        self.assertEqual(self.misses(out), ["c1 item48-a"])

    def test_a_windows_machine_home_entry_is_a_miss(self):
        self.commit_step("c1", note="Shape the item48-a picker.", mockups={"item48-a": self.WIN_MACHINE_ITEM})
        self.fetch_origin("main")
        _, out = self.build_from_main(expect=(1,))
        self.steps_line(out, 1)
        self.assertEqual(self.misses(out), ["c1 item48-a"])

    def test_a_design_file_in_the_checkout_but_not_on_origin_is_a_miss(self):
        self.commit_step("c1", note="Shape the item48-a picker.", mockups={"item48-a": self.DESIGN_ITEM})
        self.fetch_origin("main")  # origin is readable, and it lacks the file
        self.commit_design(self.DESIGN_ITEM)  # the checkout gets it after the origin ref was taken
        _, out = self.build_from_main(expect=(1,))
        self.steps_line(out, 1)
        self.assertEqual(self.misses(out), ["c1 item48-a"])

    def test_a_design_file_on_origin_but_not_in_the_checkout_passes(self):
        self.commit_step("c1", title="Design held", note="Shape the item48-a picker.", mockups={"item48-a": self.DESIGN_ITEM})
        self.commit_design(self.DESIGN_ITEM)
        self.fetch_origin("main")  # origin/main holds the file
        git(self.repo, "rm", "-q", self.DESIGN_ITEM)  # main, where commit_design left the checkout, drops it
        git(self.repo, "commit", "-q", "-m", "drop the design locally")
        page, out = self.build_from_main(expect=(0,))
        self.steps_line(out, 1)
        self.assertIn("Design held", page, "the build did not read the step")
        self.assertEqual(self.misses(out), [])
        self.assertEqual(self.unread_ids(out), [])

    def test_a_design_file_on_the_record_branch_on_origin_passes(self):
        self.commit_step("c1", title="Design held", note="Shape the item48-a picker.", mockups={"item48-a": self.DESIGN_ITEM})
        self.fetch_origin("main")  # origin is readable, and its default branch lacks the file
        self.commit_design(self.DESIGN_ITEM, branch="roadmap")
        self.fetch_origin("roadmap")
        page, out = self.build_from_main(expect=(0,))
        self.steps_line(out, 1)
        self.assertIn("Design held", page, "the build did not read the step")
        self.assertEqual(self.misses(out), [])
        self.assertEqual(self.unread_ids(out), [])

    def test_with_no_origin_ref_a_design_entry_reads_unknown_even_when_its_file_is_in_the_checkout(self):
        self.commit_step("c1", title="Design held", note="Shape the item48-a picker.", mockups={"item48-a": self.DESIGN_ITEM})
        self.commit_design(self.DESIGN_ITEM)  # no fetch_origin: the fixture has no origin ref
        page, out = self.build_from_main(expect=(0,))
        self.steps_line(out, 1)
        self.assertIn("Design held", page, "the build did not read the step")
        self.assertEqual(self.misses(out), [])
        self.assertEqual(self.unread_ids(out), ["c1 item48-a"])

    def test_with_no_origin_ref_a_missing_design_file_reads_unknown_and_is_no_miss(self):
        self.commit_step("c1", note="Shape the item48-a picker.", mockups={"item48-a": self.DESIGN_ITEM})
        _, out = self.build_from_main(expect=(0,))
        self.steps_line(out, 1)
        self.assertEqual(self.misses(out), [])
        self.assertEqual(self.unread_ids(out), ["c1 item48-a"])

    def test_a_shallow_checkout_reads_a_design_entry_unknown_even_when_origin_holds_it(self):
        self.commit_step("c1", title="Design held", note="Shape the item48-a picker.", mockups={"item48-a": self.DESIGN_ITEM})
        self.commit_design(self.DESIGN_ITEM)
        self.fetch_origin("main")  # origin/main holds the file
        self.make_shallow()
        page, out = self.build_from_main(expect=(0,))
        self.steps_line(out, 1)
        self.assertIn("Design held", page, "the build did not read the step")
        self.assertEqual(self.misses(out), [])
        self.assertEqual(self.unread_ids(out), ["c1 item48-a"])

    def test_only_the_item_with_no_file_is_named_when_a_step_cites_two(self):
        self.commit_step("c1", note="Shape item48-a and item48-b.", mockups={"item48-a": self.DESIGN_ITEM})
        self.commit_step("c2", order=2, title="Plain", note="No picture is cited here.")
        self.commit_design(self.DESIGN_ITEM)
        self.fetch_origin("main")
        _, out = self.build_from_main(expect=(1,))
        self.steps_line(out, 2)
        self.assertEqual(self.misses(out), ["c1 item48-b"])

    def test_a_folder_at_the_mockup_path_on_origin_is_a_miss(self):
        self.commit_step("c1", note="Shape the item48-a picker.", mockups={"item48-a": "docs/design/item48"})
        self.commit_design("docs/design/item48/a.html")  # the mockup path names a folder, not a file
        self.fetch_origin("main")
        _, out = self.build_from_main(expect=(0, 1))
        self.steps_line(out, 1)
        self.assertEqual(self.misses(out), ["c1 item48-a"], "a folder on origin at the mockup path reads ok, not a miss")
        self.assertEqual(self.code, 1, "a miss exits 1")

    def test_a_link_on_origin_at_the_mockup_path_is_a_miss(self):
        self.commit_step("c1", note="Shape the item48-a picker.", mockups={"item48-a": "docs/design/item48.html"})
        self.origin_link("docs/design/item48.html", "docs/design/a.html")  # a link is no mockup file
        _, out = self.build_from_main(expect=(0, 1))
        self.steps_line(out, 1)
        self.assertEqual(self.misses(out), ["c1 item48-a"], "a link on origin at the mockup path reads ok, not a miss")
        self.assertEqual(self.code, 1, "a miss exits 1")

    def test_a_done_step_that_cites_a_mockup_with_no_entry_does_not_fail_the_build(self):
        self.commit_step("c1", status="done", title="Shipped picker", note="Shape the item48-a picker.")
        _, out = self.build_from_main(expect=(0, 1))
        self.steps_line(out, 1)
        self.assertEqual(self.misses(out), [], "a done step's cited mockup fails the build")
        self.assertEqual(self.unread_ids(out), [], "a done step's cited mockup reads unknown")
        self.assertEqual(self.code, 0, "a build with no open miss exits 0")

    def test_a_file_on_another_origin_branch_counts_as_on_origin(self):
        self.commit_step("c1", title="Design held", note="Shape the item48-a picker.", mockups={"item48-a": self.DESIGN_ITEM})
        self.commit_design(self.DESIGN_ITEM, branch="pr-lane", new=True)  # an open PR's branch
        self.fetch_origin("main")  # origin is readable, and its default branch lacks the file
        self.fetch_origin("pr-lane")  # origin holds the PR's branch, which has it
        page, out = self.build_from_main(expect=(0, 1))
        self.steps_line(out, 1)
        self.assertEqual(self.misses(out), [], "a file on an open PR's origin branch reads as a miss")
        self.assertEqual(self.unread_ids(out), [], "a file on an open PR's origin branch reads as unknown")
        self.assertEqual(self.code, 0, "a step whose mockup is on origin exits 0")
        self.assertIn("Design held", page, "the build did not read the step")

    def test_a_file_only_on_a_local_branch_is_a_miss(self):
        self.commit_step("c1", note="Shape the item48-a picker.", mockups={"item48-a": self.DESIGN_ITEM})
        self.commit_design(self.DESIGN_ITEM, branch="pr-lane", new=True)  # a local branch has no origin ref
        self.fetch_origin("main")  # origin is readable, and its default branch lacks the file
        _, out = self.build_from_main(expect=(0, 1))
        self.steps_line(out, 1)
        self.assertEqual(self.misses(out), ["c1 item48-a"], "a local branch's file reads as on origin")
        self.assertEqual(self.code, 1, "a miss exits 1")

    def test_a_failed_origin_read_reads_the_design_entry_unknown_and_is_no_miss(self):
        self.commit_step("c1", title="Design held", note="Shape the item48-a picker.", mockups={"item48-a": self.DESIGN_ITEM})
        self.commit_design(self.DESIGN_ITEM)
        self.fetch_origin("main")  # origin holds the file, so only a read that found nothing could say miss
        with self.failing_origin_git():
            page, out = self.build_from_main(expect=(0, 1))
        self.steps_line(out, 1)
        self.assertEqual(self.misses(out), [], "a failed origin read reads as a miss")
        self.assertEqual(self.unread_ids(out), ["c1 item48-a"], "a failed origin read does not read unknown")
        self.assertEqual(self.code, 0, "an unknown entry exits 0")
        self.assertIn("Design held", page, "the build did not read the step")

    def test_a_failed_origin_ref_listing_reads_every_design_entry_unknown_and_is_no_miss(self):
        self.commit_step("c1", title="Design held", note="Shape the item48-a picker.", mockups={"item48-a": self.DESIGN_ITEM})
        self.commit_step("c2", order=2, title="Design held too", note="Shape the item49-b picker.",
                         mockups={"item49-b": "docs/design/item49/b.html"})
        self.commit_design(self.DESIGN_ITEM)  # origin/main holds item48-a and lacks item49-b
        self.fetch_origin("main")
        with self.failing_origin_git(verbs=None):  # every read of an origin ref fails, the listing among them
            _, out = self.build_from_main(expect=(0,))
        self.steps_line(out, 2)
        self.assertEqual(self.misses(out), [], "a failed origin ref listing reads an entry as a miss")
        self.assertEqual(self.unread_ids(out), ["c1 item48-a", "c2 item49-b"],
                         "a failed origin ref listing does not read every entry unknown")

    def test_five_entries_over_fifty_origin_refs_start_at_most_four_git_processes(self):
        for k in range(1, 6):
            item = "item%d-a" % (40 + k)
            self.commit_step("c%d" % k, order=k, title="Picker %d" % k, note="Shape the %s picker." % item,
                             mockups={item: "docs/design/item%d/a.html" % (40 + k)})
        self.fetch_origin("main")
        for n in range(1, 50):
            self.fetch_origin("main", name="lane-%02d" % n)  # 50 origin refs in all, as open PR branches leave them
        out, result, argv = self.check_starts()
        self.steps_line(out, 5)
        self.assertIsNotNone(result, "the mockup check did not run")
        misses, unread = result
        self.assertEqual(misses, [("c%d" % k, "item%d-a" % (40 + k)) for k in range(1, 6)],
                         "the check did not judge all five entries as misses")
        self.assertEqual(unread, [], "the check read an entry as unknown")
        self.assertLessEqual(len(argv), 4, "the mockup check started %d git processes for 5 entries over 50 origin refs, "
                                           "want at most 4" % len(argv))

    def test_a_malformed_extras_file_reads_the_design_entry_unknown_and_the_build_writes_the_page(self):
        self.commit_step("c1", title="Design held", note="Shape the item48-a picker.", mockups={"item48-a": self.DESIGN_ITEM})
        self.commit_design(self.DESIGN_ITEM)
        self.fetch_origin("main")
        self.write_extras("{ not json")
        self.on_main()
        raised = None
        try:
            code, out = run_build("--repo", str(self.repo), "--out", str(self.out))
        except Exception as err:  # the defect: the layout's error leaves the build as a raise, not an unknown line
            raised = err
        if raised is not None:
            self.fail("the build raised %s on a malformed extras file, want an unknown line and exit 0" % type(raised).__name__)
        self.steps_line(out, 1)
        self.assertEqual(self.unread_ids(out), ["c1 item48-a"], "a malformed extras file does not read the entry unknown")
        self.assertEqual(code, 0, "an unknown entry exits 0")
        self.assertTrue(self.out.exists(), "the build wrote no page")
        self.assertIn("Design held", self.out.read_text(encoding="utf-8"), "the build did not write the step")

    def test_a_malformed_extras_file_still_builds_a_step_that_cites_no_mockup(self):
        self.commit_step("c1", title="Plain step", note="No picture is cited here.")
        self.write_extras("{ not json")
        page, out = self.build_from_main(expect=(0,))
        self.steps_line(out, 1)
        self.assertIn("Plain step", page, "the build did not write the page")


class IdleLanes(UpkeepFixture):
    """The lanes-to-archive upkeep row and build.idle_lanes (spec section 3). A lane is listed only when its session
    is completed or review ready, every cs-step it names is landed (a Step trailer on main, or status done), and no
    open pull request or open page item still holds it. A read the build cannot make is one `unknown (...)` entry,
    never an empty list. Each negative case shares its live file with a listed control, so an empty row cannot pass."""

    ROW = "lanes to archive"

    def lane(self, sid, step, bucket=BUCKET_COMPLETED, status="SESSION_STATUS_IDLE"):
        """A sessions row for a lane of this repo that names `step`, with its get_session bucket."""
        return session_row(sid, status, "cs-build:lane", "cs-step:" + step, self.REPO, status_bucket=bucket)

    def publish(self, sessions=None, pulls=(), threads=(), read_at=None, items=()):
        """UpkeepFixture.publish with the items key present: [] unless a case names rows. items=None leaves the key out,
        the file a publisher writes before the waiting page had items."""
        return super().publish(sessions=sessions, pulls=pulls, threads=threads, read_at=read_at,
                               items=None if items is None else list(items))

    def land(self, steps):
        """Write {step id: fields} on the record branch in one commit. Each step is written whole, from STEP."""
        for sid, fields in steps.items():
            self.write_step(sid, dict(STEP, **fields))
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "steps " + ", ".join(sorted(steps)))

    def trailer_on_main(self, sid):
        """A commit on main whose last paragraph is `Step: <sid>`, so the step reads as merged there. Leaves HEAD on
        the record branch."""
        git(self.repo, "checkout", "-q", "main")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "%s merged\n\nStep: %s" % (sid, sid))
        git(self.repo, "checkout", "-q", "roadmap")

    def archive(self, *extra):
        """(count, entries) of the lanes-to-archive row, from a build from main that reads the fixture's live file.
        `extra` adds build flags, such as --main-branch."""
        _, out = self.build_from_main("--live", str(self.live), *extra, expect=(0, 1))
        count, detail = self.row(out, self.ROW)
        return count, self.entries(detail)

    def idle_direct(self):
        """build.idle_lanes on the fixture's live file, with the steps, marks and repo name the build reads."""
        fn = getattr(build, "idle_lanes", None)
        if fn is None:
            self.fail("build.idle_lanes is absent: no function names the lanes to archive")
        source, why = build.record_source(self.repo, "roadmap")
        self.assertIsNotNone(source, why)
        steps = build.load(source)["steps"]
        marks, _strays, _why = build.landed_marks(self.repo, build.main_ref(self.repo, "main"), "main", steps)
        work = build.live_work(str(self.live), steps, self.SLUG)
        return fn(work, steps, marks, self.SLUG, self.repo)

    @staticmethod
    def ids(entries):
        """The first word of each entry: a session id, or `unknown` for an unknown entry."""
        return sorted(entry.split(" ", 1)[0] for entry in entries)

    @staticmethod
    def named(entries, sid):
        return any(sid in entry for entry in entries)

    def test_control_the_live_file_builds_and_an_existing_upkeep_row_reads(self):
        # Green on the old code too: the fixture builds with a live file, and a row that exists now reads. So the red
        # cases in this class fail on the new row, not on the fixture.
        self.land({"c1": {"status": "done", "order": 1}})
        self.publish(sessions=[self.lane("session_a", "c1")])
        _, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        self.assertEqual(self.row(out, "notes over %d words" % build.NOTE_WORDS), (0, ""))

    def test_core_four_lanes_only_the_one_whose_step_merged_is_listed(self):
        self.land({"c1": {"status": "doing", "order": 1}, "c2": {"status": "done", "order": 2},
                   "c3": {"status": "done", "order": 3}, "c4": {"status": "done", "order": 4}})
        self.trailer_on_main("c1")
        self.publish(sessions=[self.lane("session_a", "c1"),
                               self.lane("session_b", "c2"),
                               self.lane("session_c", "c3", bucket=BUCKET_WORKING, status="SESSION_STATUS_RUNNING"),
                               self.lane("session_d", "c4")],
                     pulls=[{"number": 21, "title": "c2 lane", "branch": "c2"}],
                     items=[{"n": 4, "status": "open", "home": "step c4", "lane": "c4"}])
        self.assertEqual(self.ids(self.idle_direct()), ["session_a"])

    def test_open_pull_on_the_lane_head_form_blocks_its_lane(self):
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        self.publish(sessions=[self.lane("session_a", "c1"), self.lane("session_b", "c2")],
                     pulls=[{"number": 31, "title": "lane c1", "branch": "lane/c1"}])
        count, entries = self.archive()
        self.assertEqual((count, self.ids(entries)), (1, ["session_b"]))

    def test_open_pull_on_the_bare_step_head_blocks_its_lane(self):
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        self.publish(sessions=[self.lane("session_a", "c1"), self.lane("session_b", "c2")],
                     pulls=[{"number": 32, "title": "lane c2", "branch": "c2"}])
        count, entries = self.archive()
        self.assertEqual((count, self.ids(entries)), (1, ["session_a"]))

    def test_open_draft_whose_head_is_an_ancestor_of_main_does_not_block(self):
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2},
                   "c3": {"status": "done", "order": 3}})
        git(self.repo, "checkout", "-q", "main")
        ancestor = git(self.repo, "rev-parse", "HEAD").strip()
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "later work on main")  # `ancestor` is now strictly behind
        git(self.repo, "checkout", "-q", "roadmap")
        off_main = git(self.repo, "rev-parse", "roadmap").strip()  # a commit main never reaches
        self.publish(sessions=[self.lane("session_a", "c1"), self.lane("session_b", "c2"), self.lane("session_c", "c3")],
                     pulls=[dict(self.draft(41, "c1"), head=ancestor), dict(self.draft(42, "c2"), head=off_main)])
        count, entries = self.archive()
        # session_a: the draft's head is in main, so it does not block. session_b: not in main, so it blocks.
        # session_c is the control: no pull, so it is listed.
        self.assertEqual((count, self.ids(entries)), (2, ["session_a", "session_c"]))

    def test_open_draft_with_no_head_sha_holds_its_lane(self):
        # Green on the old code: a draft with no head sha cannot be shown landed, so it holds. session_b is the control.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        self.publish(sessions=[self.lane("session_a", "c1"), self.lane("session_b", "c2")],
                     pulls=[self.draft(71, "lane/c1")])
        count, entries = self.archive()
        self.assertEqual((count, self.ids(entries)), (1, ["session_b"]))

    def test_open_draft_whose_head_git_cannot_read_holds_its_lane(self):
        # Green on the old code: a head sha git does not hold makes the ancestor read fail, and a failed read holds.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        self.publish(sessions=[self.lane("session_a", "c1"), self.lane("session_b", "c2")],
                     pulls=[dict(self.draft(72, "lane/c1"), head="f" * 40)])
        count, entries = self.archive()
        self.assertEqual((count, self.ids(entries)), (1, ["session_b"]))

    def test_blocked_failed_working_and_unbucketed_lanes_are_never_listed(self):
        self.land({"c%d" % n: {"status": "done", "order": n} for n in range(1, 6)})
        self.publish(sessions=[self.lane("session_blocked", "c1", bucket=BUCKET_BLOCKED),
                               self.lane("session_failed", "c2", bucket=BUCKET_FAILED),
                               self.lane("session_working", "c3", bucket=BUCKET_WORKING, status="SESSION_STATUS_RUNNING"),
                               session_row("session_unbucketed", "SESSION_STATUS_IDLE", "cs-build:lane",
                                           "cs-step:c4", self.REPO),
                               self.lane("session_ok", "c5")])
        count, entries = self.archive()
        self.assertEqual((count, self.ids(entries)), (1, ["session_ok"]))

    def test_completed_and_review_ready_lanes_are_listed(self):
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        self.publish(sessions=[self.lane("session_a", "c1", bucket=BUCKET_COMPLETED),
                               self.lane("session_b", "c2", bucket=BUCKET_REVIEW_READY)])
        count, entries = self.archive()
        self.assertEqual((count, self.ids(entries)), (2, ["session_a", "session_b"]))

    def test_lowercase_completed_bucket_is_not_listed(self):
        # list_sessions rows carry the enum name. A lowercase `completed` is no name a real row carries, so its lane is
        # never listed. The enum-named lane beside it is the control.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        lowercase = session_row("session_lower", "SESSION_STATUS_IDLE", "cs-build:lane", "cs-step:c1", self.REPO,
                                status_bucket="completed")
        self.publish(sessions=[lowercase, self.lane("session_a", "c2")])
        count, entries = self.archive()
        self.assertEqual((count, self.ids(entries)), (1, ["session_a"]))

    def test_step_merged_by_a_step_trailer_on_main_is_landed_and_one_still_open_is_not(self):
        self.land({"c1": {"status": "doing", "order": 1}, "c2": {"status": "doing", "order": 2}})
        self.trailer_on_main("c1")
        self.publish(sessions=[self.lane("session_a", "c1"), self.lane("session_b", "c2")])
        count, entries = self.archive()
        self.assertEqual((count, self.ids(entries)), (1, ["session_a"]))

    def test_other_repos_lane_is_ignored_not_listed_and_not_unknown(self):
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        other = session_row("session_other", "SESSION_STATUS_IDLE", "cs-build:lane", "cs-step:c1",
                            "cs-repo:other/repo", status_bucket=BUCKET_COMPLETED)
        self.publish(sessions=[other, self.lane("session_a", "c2")])
        count, entries = self.archive()
        self.assertEqual((count, self.ids(entries)), (1, ["session_a"]))

    def test_lane_with_no_cs_step_is_never_listed(self):
        self.land({"c1": {"status": "done", "order": 1}})
        no_step = session_row("session_nostep", "SESSION_STATUS_IDLE", "cs-build:lane", self.REPO,
                              status_bucket=BUCKET_COMPLETED)
        self.publish(sessions=[no_step, self.lane("session_a", "c1")])
        count, entries = self.archive()
        self.assertFalse(self.named(entries, "session_nostep"), entries)
        self.assertTrue(self.named(entries, "session_a"), "the control lane is not listed: %r" % (entries,))

    def test_session_without_the_lane_tag_is_ignored(self):
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        triage = session_row("session_triage", "SESSION_STATUS_IDLE", "cs-build:triage", "cs-step:c1",
                             self.REPO, status_bucket=BUCKET_COMPLETED)
        self.publish(sessions=[triage, self.lane("session_a", "c2")])
        count, entries = self.archive()
        self.assertEqual((count, self.ids(entries)), (1, ["session_a"]))

    def test_archived_session_is_ignored(self):
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        self.publish(sessions=[self.lane("session_archived", "c1", status="SESSION_STATUS_ARCHIVED"),
                               self.lane("session_a", "c2")])
        count, entries = self.archive()
        self.assertEqual((count, self.ids(entries)), (1, ["session_a"]))

    def test_step_id_not_on_the_record_branch_reads_the_lane_unknown(self):
        self.land({"c1": {"status": "done", "order": 1}})
        self.publish(sessions=[self.lane("session_ghost", "ghost"), self.lane("session_a", "c1")])
        count, entries = self.archive()
        unknown = [entry for entry in entries if "unknown (" in entry]
        self.assertEqual(count, 2, entries)
        self.assertEqual(len(unknown), 1, entries)
        self.assertIn("step ghost not on the record branch", unknown[0])
        self.assertTrue(self.named(entries, "session_a"), "the control lane is not listed: %r" % (entries,))

    def test_stale_live_read_is_one_unknown_entry_and_no_lane_is_listed(self):
        self.land({"c1": {"status": "done", "order": 1}})
        self.publish(sessions=[self.lane("session_a", "c1")], read_at=iso_ago(build.STALE_LIVE_MINUTES + 30))
        count, entries = self.archive()
        self.assertEqual(count, 1, entries)
        self.assertEqual(len(entries), 1, entries)
        self.assertTrue(entries[0].startswith("unknown ("), entries)

    def test_bad_read_at_is_one_unknown_entry(self):
        self.land({"c1": {"status": "done", "order": 1}})
        self.publish(sessions=[self.lane("session_a", "c1")], read_at="not a time")
        count, entries = self.archive()
        self.assertEqual(count, 1, entries)
        self.assertTrue(entries and entries[0].startswith("unknown ("), entries)

    def test_skipped_session_or_pull_row_reads_the_whole_list_unknown(self):
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        broken_session = {"id": 7, "session_status": "SESSION_STATUS_IDLE", "tags": []}
        broken_pull = {"number": "twelve", "title": "lane c2", "branch": "c2"}
        cases = (("session", [broken_session, self.lane("session_a", "c1")], ()),
                 ("pull", [self.lane("session_a", "c1")], [broken_pull]))
        for label, sessions, pulls in cases:
            with self.subTest(row=label):
                self.publish(sessions=sessions, pulls=pulls)
                count, entries = self.archive()
                self.assertEqual(count, 1, entries)
                self.assertTrue(entries and entries[0].startswith("unknown ("), entries)

    def test_missing_sessions_list_is_one_unknown_entry(self):
        self.land({"c1": {"status": "done", "order": 1}})
        self.publish(sessions=None)
        count, entries = self.archive()
        self.assertEqual(count, 1, entries)
        self.assertTrue(entries and entries[0].startswith("unknown ("), entries)

    def test_no_live_file_is_one_unknown_entry(self):
        self.land({"c1": {"status": "done", "order": 1}})
        _, out = self.build_from_main(expect=(0, 1))
        count, detail = self.row(out, self.ROW)
        self.assertEqual(count, 1, out)
        self.assertTrue(detail.startswith("unknown ("), out)

    def test_empty_sessions_list_is_an_empty_row_not_an_unknown_one(self):
        self.land({"c1": {"status": "done", "order": 1}})
        self.publish(sessions=[])
        self.assertEqual(self.archive(), (0, []))

    def test_thirty_two_idle_lanes_are_all_listed_in_sorted_order(self):
        self.land({"L%02d" % n: {"status": "done", "order": n} for n in range(1, 33)})
        self.publish(sessions=[self.lane("session_%02d" % n, "L%02d" % n) for n in range(1, 33)])
        count, entries = self.archive()
        self.assertEqual(count, 32)
        self.assertEqual(self.ids(entries), sorted("session_%02d" % n for n in range(1, 33)))

    def test_only_a_closed_page_item_releases_its_lane(self):
        # The waiting page's statuses are open and closed (skill waiting-page, the item fields). An answered item is
        # not closed, so it still holds its lane. The closed item beside it releases its lane.
        self.land({"c%d" % n: {"status": "done", "order": n} for n in range(1, 5)})
        self.publish(sessions=[self.lane("session_a", "c1"), self.lane("session_b", "c2"),
                               self.lane("session_c", "c3"), self.lane("session_d", "c4")],
                     items=[{"n": 1, "status": "answered", "home": "step c2", "lane": "c2"},
                            {"n": 2, "status": "closed", "home": "step c3", "lane": "c3"},
                            {"n": 3, "status": "open", "home": "step c4", "lane": "c4"}])
        count, entries = self.archive()
        self.assertEqual((count, self.ids(entries)), (2, ["session_a", "session_c"]))

    def test_a_page_item_status_other_than_closed_holds_its_lane(self):
        # Green on the old code: a status the reader does not list as done holds. The closed item on c3 is the control.
        self.land({"c%d" % n: {"status": "done", "order": n} for n in range(1, 4)})
        for status in ("Closed", "parked"):
            with self.subTest(status=status):
                self.publish(sessions=[self.lane("session_a", "c1"), self.lane("session_b", "c2"),
                                       self.lane("session_c", "c3")],
                             items=[{"n": 1, "status": status, "home": "step c2", "lane": "c2"},
                                    {"n": 2, "status": "closed", "home": "step c3", "lane": "c3"}])
                count, entries = self.archive()
                self.assertEqual((count, self.ids(entries)), (2, ["session_a", "session_c"]))

    def test_a_live_file_with_no_items_key_reads_unknown_and_lists_no_lane(self):
        # The control is the same file with an items list, which lists the lane. With no items key the page items are
        # unknown, so the row reads unknown and names no lane.
        self.land({"c1": {"status": "done", "order": 1}})
        self.publish(sessions=[self.lane("session_a", "c1")], items=[])
        count, entries = self.archive()
        self.assertEqual((count, self.ids(entries)), (1, ["session_a"]))
        self.publish(sessions=[self.lane("session_a", "c1")], items=None)
        count, entries = self.archive()
        self.assertEqual((count, entries), (1, [build.ITEMS_MISSING_WHY]),
                         "a live file with no items key lists a lane, so an open page item cannot hold it")

    def test_live_items_keep_the_owner_field_of_a_page_item(self):
        # A waiting-page item names `owner`, the session that reads the answer. The live file's copy must keep it, or
        # idle_lanes cannot see that the lane asked its own question. The copy is the items row in live_work.
        self.land({"c1": {"status": "done", "order": 1}})
        self.publish(sessions=[self.lane("session_a", "c1")],
                     items=[{"n": 1, "status": "open", "home": "step c1", "owner": "session_a"}])
        source, why = build.record_source(self.repo, "roadmap")
        self.assertIsNotNone(source, why)
        steps = build.load(source)["steps"]
        rows = build.live_work(str(self.live), steps, self.SLUG)["pageItems"]
        self.assertEqual([row.get("owner") for row in rows], ["session_a"],
                         "live_work dropped the owner of an items row, so the lane that asked cannot be seen")

    def test_an_open_page_item_owned_by_a_lane_session_holds_that_lane(self):
        # The item names no lane, so the lane is still waiting on its own question. session_b is the control.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        self.publish(sessions=[self.lane("session_a", "c1"), self.lane("session_b", "c2")],
                     items=[{"n": 1, "status": "open", "home": "step c1", "owner": "session_a"}])
        count, entries = self.archive()
        self.assertEqual((count, self.ids(entries)), (1, ["session_b"]))

    def test_lane_rows_with_no_status_bucket_read_the_list_unknown_not_empty(self):
        # The control is one row that carries a bucket: its lane is listed and no unknown entry is made. With no row
        # carrying status_bucket, the list cannot say which lane is idle, so it reads unknown.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        self.publish(sessions=[self.lane("session_a", "c1"),
                               session_row("session_b", "SESSION_STATUS_IDLE", "cs-build:lane", "cs-step:c2", self.REPO)])
        count, entries = self.archive()
        self.assertEqual((count, self.ids(entries)), (1, ["session_a"]))
        self.publish(sessions=[session_row("session_a", "SESSION_STATUS_IDLE", "cs-build:lane", "cs-step:c1", self.REPO),
                               session_row("session_b", "SESSION_STATUS_IDLE", "cs-build:lane", "cs-step:c2", self.REPO)])
        count, entries = self.archive()
        self.assertEqual(count, 1, "lane rows with no status_bucket read as an empty list: %r" % (entries,))
        self.assertTrue(entries and entries[0].startswith("unknown ("), entries)

    def test_a_pull_row_whose_branch_is_a_list_is_skipped_and_idle_lanes_reads_unknown(self):
        # The pull row is counted as skipped, and the lanes read unknown. A crash on the list is the defect, so it is
        # turned into a named failure here, not an error.
        self.land({"c1": {"status": "done", "order": 1}})
        self.publish(sessions=[self.lane("session_a", "c1")],
                     pulls=[{"number": 51, "title": "lane c1", "branch": ["lane/c1"]}])
        source, why = build.record_source(self.repo, "roadmap")
        self.assertIsNotNone(source, why)
        steps = build.load(source)["steps"]
        work = build.live_work(str(self.live), steps, self.SLUG)
        self.assertIn("pull 1", work["skipped"], "a pull row whose branch is a list was kept, not counted as skipped")
        try:
            entries = self.idle_direct()
        except Exception as err:
            self.fail("idle_lanes crashed on a pull row whose branch is a list: %r" % (err,))
        self.assertEqual(len(entries), 1, entries)
        self.assertTrue(entries[0].startswith("unknown ("), "the skipped pull row did not read the lanes unknown: %r" % (entries,))

    def test_a_repo_tag_with_a_space_inside_is_not_this_repo(self):
        # Green on the old code: the space after the colon stays after strip, so the tag is not owner/name.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        spaced = session_row("session_spaced", "SESSION_STATUS_IDLE", "cs-build:lane", "cs-step:c1",
                             "cs-repo: " + self.SLUG, status_bucket=BUCKET_COMPLETED)
        self.publish(sessions=[spaced, self.lane("session_a", "c2")])
        count, entries = self.archive()
        self.assertEqual((count, self.ids(entries)), (1, ["session_a"]))

    def test_a_repo_tag_with_outer_whitespace_is_not_this_repo(self):
        # The one reading of a repo tag takes no strip (hooks/shared_names.py, repo_tag_names). idle_lanes strips each
        # tag before it reads it, so these two lanes are listed unless the strip goes.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2},
                   "c3": {"status": "done", "order": 3}})
        trailing = session_row("session_trailing", "SESSION_STATUS_IDLE", "cs-build:lane", "cs-step:c1",
                               "cs-repo:" + self.SLUG + " ", status_bucket=BUCKET_COMPLETED)
        leading = session_row("session_leading", "SESSION_STATUS_IDLE", "cs-build:lane", "cs-step:c2",
                              " cs-repo:" + self.SLUG, status_bucket=BUCKET_COMPLETED)
        self.publish(sessions=[trailing, leading, self.lane("session_a", "c3")])
        count, entries = self.archive()
        self.assertEqual((count, self.ids(entries)), (1, ["session_a"]),
                         "a repo tag with outer whitespace is read as this repo, so its lane is listed")

    def unread_main_lane(self):
        """One lane on c1. c1 is doing, with a Step trailer on main, so the lane reads as landed while main reads."""
        self.land({"c1": {"status": "doing", "order": 1}})
        self.trailer_on_main("c1")
        self.publish(sessions=[self.lane("session_a", "c1")])

    def test_unreadable_main_reads_the_lanes_unknown_not_empty(self):
        # The control is the same call with main read: the lane is listed. With main unreadable, no step can be shown
        # landed, so the list reads one unknown entry. The old code returns [], which is the defect.
        self.unread_main_lane()
        self.assertEqual(self.ids(build.idle_lanes_report(self.repo, str(self.live))), ["session_a"])
        self.assertIsNone(build.main_ref(self.repo, "nomain"), "the fixture must make main unreadable")
        entries = build.idle_lanes_report(self.repo, str(self.live), main_branch="nomain")
        self.assertEqual(len(entries), 1, "an unreadable main reads as %r, not one unknown entry" % (entries,))
        self.assertTrue(entries[0].startswith("unknown ("), entries)

    def test_unreadable_main_upkeep_row_reads_unknown_not_empty(self):
        # The control is the same build from main with main read: the lane is listed. With --main-branch naming no
        # branch, the upkeep row must read one unknown entry, never an empty row.
        self.unread_main_lane()
        count, entries = self.archive()
        self.assertEqual((count, self.ids(entries)), (1, ["session_a"]))
        count, entries = self.archive("--main-branch", "nomain")
        self.assertEqual(count, 1, "an unreadable main reads the lanes row as %r" % (entries,))
        self.assertTrue(entries and entries[0].startswith("unknown ("), entries)

    def test_archived_rows_with_no_bucket_do_not_read_a_live_lane_unknown(self):
        # Green on the old code: a live row with an enum bucket makes the no-bucket check false, so the archived row
        # with no bucket changes nothing. The live lane is judged normally. session_a is the control.
        self.land({"c1": {"status": "done", "order": 1}})
        archived = session_row("session_old", "SESSION_STATUS_ARCHIVED", "cs-build:lane", "cs-step:c1", self.REPO)
        self.publish(sessions=[archived, self.lane("session_a", "c1")])
        count, entries = self.archive()
        self.assertEqual((count, self.ids(entries)), (1, ["session_a"]))

    def test_live_lane_rows_with_no_bucket_read_unknown_when_an_archived_row_holds_a_bucket(self):
        # The no-bucket check counts archived rows too. Here one archived row's bucket hides two live rows that carry
        # none, so the old code lists nothing and reads no unknown, which is [] (the defect). The live rows must read
        # unknown: the archived row is not counted.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        archived = self.lane("session_old", "c1", status="SESSION_STATUS_ARCHIVED")
        self.publish(sessions=[archived,
                               session_row("session_b", "SESSION_STATUS_IDLE", "cs-build:lane", "cs-step:c2", self.REPO)])
        count, entries = self.archive()
        self.assertEqual(count, 1, "live rows with no bucket read as %r, not one unknown entry" % (entries,))
        self.assertTrue(entries and entries[0].startswith("unknown ("), entries)

    def test_live_lane_rows_with_only_wrong_form_buckets_read_unknown_not_empty(self):
        # The control is one row in the enum form: its lane is listed and no unknown entry is made. Then every live row
        # carries a wrong form (`completed`, `COMPLETED`), so no lane reads idle and the list reads one unknown entry,
        # never [].
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2},
                   "c3": {"status": "done", "order": 3}})
        self.publish(sessions=[self.lane("session_a", "c1")])
        count, entries = self.archive()
        self.assertEqual((count, self.ids(entries)), (1, ["session_a"]))
        wrong = [session_row("session_lower", "SESSION_STATUS_IDLE", "cs-build:lane", "cs-step:c2", self.REPO,
                             status_bucket="completed"),
                 session_row("session_upper", "SESSION_STATUS_IDLE", "cs-build:lane", "cs-step:c3", self.REPO,
                             status_bucket="COMPLETED")]
        self.publish(sessions=wrong)
        count, entries = self.archive()
        self.assertEqual(count, 1, "wrong-form buckets read as %r, not one unknown entry" % (entries,))
        self.assertTrue(entries and entries[0].startswith("unknown ("), entries)


class SharedTagNames(unittest.TestCase):
    """The roadmap's tag names have one home, hooks/shared_names.py. build reads the very objects, so a
    copied literal cannot drift from the guard's check. Identity, not equality: an equal copy fails."""

    def test_lane_head_refs_is_the_shared_function(self):
        self.assertTrue(hasattr(shared_names, "lane_head_refs"), "hooks/shared_names.py has no lane_head_refs")
        self.assertTrue(hasattr(build, "lane_head_refs"), "build has no lane_head_refs")
        self.assertIs(build.lane_head_refs, shared_names.lane_head_refs)

    def test_repo_and_step_tags_are_the_shared_objects(self):
        for name in ("REPO_TAG", "STEP_TAG"):
            with self.subTest(name=name):
                self.assertTrue(hasattr(shared_names, name), "hooks/shared_names.py has no %s" % name)
                self.assertIs(getattr(build, name), getattr(shared_names, name))

    def test_repo_tag_names_is_the_shared_function(self):
        self.assertTrue(hasattr(shared_names, "repo_tag_names"), "hooks/shared_names.py has no repo_tag_names")
        self.assertIs(build.repo_tag_names, shared_names.repo_tag_names)

    def test_repo_tag_names_reads_the_tag_strictly(self):
        # The one reading of a repo tag: the exact `cs-repo:` prefix, no strip, owner/name without case.
        slug = "shivinate7/claude-settings"
        self.assertTrue(hasattr(build, "repo_tag_names"), "build has no repo_tag_names")
        self.assertTrue(build.repo_tag_names("cs-repo:shivinate7/claude-settings", slug))
        for tag in ("cs-repo:shivinate7/claude-settings ", " cs-repo:shivinate7/claude-settings",
                    "CS-REPO:shivinate7/claude-settings", "cs-repo:claude-settings", None, 7):
            with self.subTest(tag=tag):
                self.assertFalse(build.repo_tag_names(tag, slug))


if __name__ == "__main__":
    unittest.main()
