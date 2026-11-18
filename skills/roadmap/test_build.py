"""Fixture suite for the roadmap build.py. Run: python3 skills/roadmap/test_build.py

Each case builds a throwaway git repo: `main` holds the record homes, `roadmap` holds roadmap/data/.
"""
import ast
import contextlib
import datetime
import email.message
import hashlib
import http.client
import importlib.util
import inspect
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
import urllib.error
import urllib.parse
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
import guard_merge  # noqa: E402  the guard's lane-form rule (_on_lane_form), which the ready-pull case reads (hooks/guard_merge.py)

# Made in setUpModule, not at import, so a helper that imports make_repo leaks no folder.
RUN_FOLDER = None

STEP = {"title": "t", "status": "todo", "phase": "cleanup", "order": 1, "note": "n", "updatedAt": "2026-10-26T00:00:00Z"}
CONFLICT = "<<<<<<< HEAD\na\n=======\nb\n>>>>>>> 1234567 (other)\n"
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
TOKEN_VARS = ("GH_TOKEN", "GITHUB_TOKEN")  # the GitHub read's token variables: no fixture's build child gets them
_NO_LANE = object()  # item(): the default, which leaves the row's lane key out
_ABSENT = object()  # commit_step(): a field set to this is left out of the step file
_OWN_REPO = object()  # rest_draft(): the head repo is the base repo of the case
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
# sha256 of skills/roadmap/page/index.html outside the build blocks.
TODAY_TEMPLATE_SHA256 = "0531ecd924b2783d47ca1da9565b247dae9facd171a09b810eedf187e0cce894"
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


def fixture_env():
    """The environment a fixture's build child runs with: the caller's, minus the GitHub token variables."""
    return {k: v for k, v in os.environ.items() if k not in TOKEN_VARS}


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


def headers_of(pairs=None):
    """A response's headers as urlopen gives them: an email Message, so a name reads in any case."""
    message = email.message.Message()
    for key, value in (pairs or {}).items():
        message[key] = value
    return message


def http_error(code, pairs=None):
    """The HTTPError that the rest_get seam raises on a non-2xx reply: headers as a Message, an empty body."""
    return urllib.error.HTTPError("https://api.github.com/repos/owner/fixture/pulls", code, "error %d" % code,
                                  headers_of(pairs), io.BytesIO(b""))


def request_url(call):
    """The URL that a mocked rest_get call received, positional or by keyword."""
    return call.args[0] if call.args else call.kwargs["url"]


def request_token(call):
    """The token that a mocked rest_get call received, positional or by keyword."""
    return call.args[1] if len(call.args) > 1 else call.kwargs.get("token")


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
        # The one home of the GitHub read's environment and seam: no case reads a caller's token or the network.
        # A case that needs a read sets a token and serves pages through serve_pulls (UpkeepFixture).
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        for key in TOKEN_VARS:
            os.environ.pop(key, None)
        seam = mock.patch.object(build, "rest_get", create=True, return_value=([], headers_of()))
        self.rest_get = seam.start()
        self.addCleanup(seam.stop)

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


class NotesHome(Fixture):
    def test_notes_folder_is_a_home_beside_the_old_notes_file(self):
        """The page reads the notes folder as a home, as it reads the old notes file. Control: the old file's panel
        still homes on the old file."""
        (self.repo / "docs" / "notes").mkdir(parents=True)
        (self.repo / "docs" / "notes" / "wheel-speed-cap.md").write_text(
            "- wheel-speed-cap: the spin rate is capped (hooks/guard.py)\n", encoding="utf-8")
        (self.repo / "docs" / "debts").mkdir(parents=True)
        (self.repo / "docs" / "debts" / "notes.md").write_text(
            "# Notes\n\n- old-note: kept in the old file (hooks/guard.py)\n", encoding="utf-8")
        page, _ = self.build_from_main()
        panels = build_info(page)["panels"]
        notes = [p for p in panels if p.get("home") == "docs/notes"]
        self.assertEqual(len(notes), 1, "no panel reads the notes folder: %s" % [p.get("home") for p in panels])
        self.assertFalse(notes[0]["read"].startswith("unknown"), notes[0])
        self.assertEqual(self.panel(page, "Debt notes")["home"], "docs/debts/notes.md")

    def test_checkout_with_no_notes_folder_reads_notes_as_empty(self):
        """kind notes is optional: a checkout with no docs/notes reads the Notes home as empty, not unknown."""
        page, _ = self.build_from_main()
        self.assertFalse((self.repo / "docs" / "notes").exists())  # scope: the folder is absent in this checkout
        notes = self.panel(page, "Notes")
        self.assertFalse(notes["read"].startswith("unknown"), notes)
        self.assertIn("empty", notes["read"], notes)

    def test_missing_core_homes_still_read_unknown_without_a_notes_folder(self):
        """Control: with no docs/notes, the core homes that are missing read unknown, as before."""
        page, _ = self.build_from_main()
        self.assertFalse((self.repo / "docs" / "notes").exists())  # scope: the folder is absent in this checkout
        self.assertEqual(self.panel(page, "Debts")["read"], "unknown (no debts or docs/debts in this checkout)")
        self.assertEqual(self.panel(page, "Debt notes")["read"],
                         "unknown (no debts/notes.md or docs/debts/notes.md in this checkout)")


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

    def test_missing_pulls_list_reads_unknown_whatever_threads_is(self):
        # Only the pulls list makes the whole read unknown. A threads list that is missing does not (LiveThreadsOptional).
        self.write_live({"readAt": "2026-10-26T21:00:00Z", "threads": []})
        page, _ = self.build_from_main("--live", str(self.live))
        self.assertEqual(self.panel(page)["read"], "unknown (the live file has no pulls list)")
        self.assertNotIn("threads", build_info(page)["live"])
        self.write_live({"readAt": "2026-10-26T21:00:00Z", "threads": None, "pulls": {}})
        page, _ = self.build_from_main("--live", str(self.live))
        self.assertEqual(self.panel(page)["read"], "unknown (the live file has no pulls list)")
        self.write_live({"readAt": "2026-10-26T21:00:00Z"})
        page, _ = self.build_from_main("--live", str(self.live))
        self.assertEqual(self.panel(page)["read"], "unknown (the live file has no pulls list)")

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
    # git's empty tree: every repo holds it, so a commit or ref on it needs no file of its own.
    EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

    def setUp(self):
        super().setUp()
        self.use_origin(self.SLUG)
        self.origin_set = set()  # branches whose refs/remotes/origin/ ref a case set, dropped or broke

    def commit_step(self, sid, **fields):
        """Write a step on the record branch and commit it, where a build from main reads it. A field set to _ABSENT is left out."""
        self.write_step(sid, {k: v for k, v in dict(STEP, **fields).items() if v is not _ABSENT})
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "step " + sid)

    def publish(self, sessions=None, pulls=(), threads=(), read_at=None, items=None, landed=None):
        """Write the --live file. threads=_ABSENT leaves the threads key out. The sessions, items and landedPulls keys
        appear only when given, and landed is written
        as given (a case may send a value that is not a list). readAt is five minutes old by default."""
        value = {"readAt": read_at or iso_ago(5)}
        if threads is not _ABSENT:
            value["threads"] = list(threads)
        value["pulls"] = list(pulls)
        if sessions is not None:
            value["sessions"] = list(sessions)
        if items is not None:
            value["items"] = items
        if landed is not None:
            value["landedPulls"] = landed
        self.write_live(value)
        return value

    def out_with_live(self, expect=(0, None)):
        _, out = self.build_from_main("--live", str(self.live), expect=expect)
        return out

    # argparse's refusal of a flag the build does not know: exit 2, with this text in the output.
    NO_SOURCE_FLAG = "unrecognized arguments"

    def source_out(self, source, live=True):
        """(code, output) of a build from main that names the sessions source `source`. None names no flag, so the
        default run. A build that raises fails the case with a named cause. A build that predates the flag refuses it
        (exit 2, NO_SOURCE_FLAG), so the run repeats without the flag: the case's asserts then fail on the old
        behaviour, not on the refusal. Only test_the_build_accepts_the_sessions_source_flag carries the refusal, the
        way SINCE_FALLBACK's case carries the missing constant."""
        self.on_main()
        argv = ["--repo", str(self.repo), "--out", str(self.out)]
        if live:
            argv += ["--live", str(self.live)]
        flag = [] if source is None else ["--sessions-source", source]
        try:
            code, out = run_build(*argv, *flag)
            if code == 2 and flag and self.NO_SOURCE_FLAG in out:
                code, out = run_build(*argv)
        except Exception as err:
            self.fail("the build raised %s instead of reading the row as one unknown entry" % type(err).__name__)
        return code, out

    def register_source(self, name, reader):
        """A context that registers `reader` as the sessions source `name` in build.SESSION_SOURCES. A build without
        the registry gets the name as a module attribute instead, so the case runs and fails on its own assert, not on
        an AttributeError (SINCE_FALLBACK's reason)."""
        if hasattr(build, "SESSION_SOURCES"):
            return mock.patch.dict(build.SESSION_SOURCES, {name: reader})
        return mock.patch.object(build, "SESSION_SOURCES", {name: reader}, create=True)

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

    def rest_draft(self, number, branch, updated_min=780, title=None, created_min=None, draft=True, head_repo=_OWN_REPO):
        """A pulls row as GitHub's list call returns it, the shape the REST read takes. updated_min and created_min
        are minutes before now. The default 780 (13 h) is stale; created_min is left out when None. head.repo is the
        head repo as GitHub gives it: the base repo's full name by default, another full name for a fork's pull, and
        null (head_repo=None) for a head repo GitHub no longer has, such as a deleted fork."""
        full_name = self.SLUG if head_repo is _OWN_REPO else head_repo
        row = {"number": number, "title": title or "lane " + branch, "draft": draft,
               "head": {"ref": branch, "repo": None if full_name is None else {"full_name": full_name}},
               "updated_at": iso_ago(updated_min)}
        if created_min is not None:
            row["created_at"] = iso_ago(created_min)
        return row

    def fresh_rows(self, first, count):
        """`count` open drafts updated an hour ago, numbered from `first`. None of them is stale."""
        return [self.rest_draft(n, "fresh-%d" % n, 60) for n in range(first, first + count)]

    def mark(self, number, **flags):
        """A live pulls row that carries only the marks (held, reviewLog) for the pull `number`."""
        return dict({"number": number, "title": "lane %d" % number}, **flags)

    def live_pull(self, number, branch, title=None):
        """The live pulls row the publisher writes for an open pull, with no marks: held and reviewLog read as unset."""
        return {"number": number, "title": title or "lane " + branch, "branch": branch}

    def origin_commit(self, branch, when):
        """Point refs/remotes/origin/<branch> at a new commit dated `when` (ISO, with its zone): the branch's newest commit."""
        sha = git(self.repo, "commit-tree", self.EMPTY_TREE, "-m", "lane " + branch,
                  env={"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}).strip()
        self.set_origin(branch, sha)

    def set_origin(self, branch, target):
        """Point refs/remotes/origin/<branch> at the object `target`."""
        git(self.repo, "update-ref", "refs/remotes/origin/" + branch, target)
        self.origin_set.add(branch)

    def drop_origin(self, branch):
        """Leave refs/remotes/origin/<branch> out, so the branch has no ref."""
        git(self.repo, "update-ref", "-d", "refs/remotes/origin/" + branch)
        self.origin_set.add(branch)

    def break_origin(self, branch):
        """Write refs/remotes/origin/<branch> to name an object git does not hold, so reading it fails."""
        ref = self.repo / ".git" / "refs" / "remotes" / "origin" / branch
        ref.parent.mkdir(parents=True, exist_ok=True)
        ref.write_text("1" * 40 + "\n", encoding="utf-8")
        self.origin_set.add(branch)

    def stale_draft_branches(self, item):
        """The head branches of the rows in one served page that the build reads as stale drafts: a draft whose
        updated_at is over 12 h before now. A page that is not a list of rows gives none."""
        body = item[0] if isinstance(item, tuple) else item
        if not isinstance(body, list):
            return []
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=12)
        out = []
        for row in body:
            if not (isinstance(row, dict) and row.get("draft") is True and isinstance(row.get("head"), dict)):
                continue
            ref, at = row["head"].get("ref"), row.get("updated_at")
            if not isinstance(ref, str) or not isinstance(at, str):
                continue
            try:
                when = datetime.datetime.fromisoformat(at.replace("Z", "+00:00"))
            except ValueError:
                continue
            if when.tzinfo is not None and when < cutoff:
                out.append(ref)
        return out

    def serve_pulls(self, *pages, token="test-token"):
        """Serve the rest_get seam: page N is pages[N-1], and a page past the list is empty. A page is a list of
        pulls rows, a (body, headers) pair, or an exception to raise. The seam, as the build reads it, returns
        (body, headers) on a 200, raises urllib.error.HTTPError on a non-2xx and raises ValueError on a body that is
        not JSON. token sets GH_TOKEN for the read; None leaves the environment as the case set it. Each stale draft
        branch served here gets a commit 13 h old, so the build's commit read finds one, unless the case has already
        set that branch's origin ref (origin_commit, set_origin, drop_origin, break_origin)."""
        if token is not None:
            os.environ["GH_TOKEN"] = token
        for item in pages:
            for branch in self.stale_draft_branches(item):
                if branch not in self.origin_set:
                    self.origin_commit(branch, iso_ago(780))

        def reply(url, token):
            number = int(urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("page", ["1"])[0])
            item = pages[number - 1] if number <= len(pages) else []
            if isinstance(item, BaseException):
                raise item
            return item if isinstance(item, tuple) else (item, headers_of())

        self.rest_get.side_effect = reply

    def requested_pages(self):
        """The page numbers that the REST read asked for, in the order it asked."""
        return [int(urllib.parse.parse_qs(urllib.parse.urlparse(request_url(c)).query)["page"][0])
                for c in self.rest_get.call_args_list]

    def pull_row(self, number, branch, head=None, merged=None, **fields):
        """One landedPulls row. head and merged are left out when None, so a case can send a row with neither. `fields`
        add keys, such as replacedBy."""
        row = {"number": number, "branch": branch}
        if head is not None:
            row["head"] = head
        if merged is not None:
            row["merged"] = merged
        row.update(fields)
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

    def is_ancestor(self, sha, ref):
        done = subprocess.run(["git", "-C", str(self.repo), "merge-base", "--is-ancestor", sha, ref], capture_output=True)
        return done.returncode == 0

    def behind_main(self):
        """A full sha that main has moved past: the tip before an empty commit lands on main. Leaves HEAD on main."""
        self.on_main()
        behind = git(self.repo, "rev-parse", "HEAD").strip()
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "later work on main")
        return behind

    def off_main(self):
        """The record branch's tip. Its history shares nothing with main, so main never reaches it."""
        return git(self.repo, "rev-parse", "roadmap").strip()

    def no_trailer_on_main(self):
        """Scope check: main holds no Step trailer, so a landed mark in the case must come from a landedPulls row."""
        trailers = git(self.repo, "log", "main", "--format=%(trailers:key=Step,valueonly)").strip()
        self.assertEqual(trailers, "", "main holds a Step trailer, so the case would not show the landedPulls read")


class LandedPulls(UpkeepFixture):
    """Landed marks from the live file's landedPulls rows (closed or merged lane pulls). A row marks its step when its
    branch is the step or lane/<step>, the step is open, and the row is merged or its head is an ancestor of main.
    The cases run through build.main, which ignores the key today, so each red is a missing landed entry or a
    missing printed line. A negative case shares its live file with a row that marks, so an empty result cannot pass."""

    def landed_build(self):
        """(page, out) of a build from main that reads the live file. A doing step with no lane exits 1."""
        return self.build_from_main("--live", str(self.live), expect=(0, 1))

    def build_with_head(self, head_of):
        """A doing c2 whose lane/c2 row names head_of(an ancestor of main) as its head, built from main."""
        self.commit_step("c2", status="doing", order=2)
        behind = self.behind_main()
        self.assertTrue(self.is_ancestor(behind, "main"), "scope: the head must be an ancestor of main")
        self.no_trailer_on_main()
        self.publish(sessions=[], items=[], landed=[self.pull_row(12, "lane/c2", head=head_of(behind))])
        return self.landed_build()

    def test_bare_step_branch_row_marks_its_doing_step_landed(self):
        self.commit_step("c2", status="doing", order=2)
        self.commit_step("c1", status="doing")  # control: its live session keeps it off the stalled lines
        self.no_trailer_on_main()
        self.publish(sessions=[self.session_in_repo("session_test01", "SESSION_STATUS_RUNNING", "cs-step:c1")],
                     items=[], landed=[self.pull_row(12, "c2", merged=True)])
        page, out = self.landed_build()
        self.assertEqual(build_info(page)["landed"], {"c2": ["#12"]}, "a merged row on branch c2 marks c2 landed")
        self.assertIn("stalled step: c2 (done: landed in #12)", out.splitlines())
        self.assertEqual(self.row(out, "landed, waiting for triage to close"), (1, "c2 (#12)"))
        self.assertEqual(self.code, 1, "a stalled step must exit 1")

    def test_lane_branch_row_merged_marks_it_whatever_its_head(self):
        self.commit_step("c2", status="doing", order=2)
        off = self.off_main()
        self.assertFalse(self.is_ancestor(off, "main"), "scope: the head must be off main")
        self.no_trailer_on_main()
        self.publish(sessions=[], items=[], landed=[self.pull_row(12, "lane/c2", head=off, merged=True)])
        page, out = self.landed_build()
        self.assertEqual(build_info(page)["landed"], {"c2": ["#12"]}, "merged true marks the step, its head off main or not")
        self.assertIn("stalled step: c2 (done: landed in #12)", out.splitlines())

    def test_full_sha_head_on_main_marks_its_step_landed(self):
        page, out = self.build_with_head(lambda sha: sha)
        self.assertEqual(build_info(page)["landed"], {"c2": ["#12"]}, "an ancestor head marks the step with no merged key")
        self.assertIn("stalled step: c2 (done: landed in #12)", out.splitlines())

    def test_abbreviated_sha_head_on_main_marks_its_step_landed(self):
        page, out = self.build_with_head(lambda sha: sha[:7])
        self.assertEqual(build_info(page)["landed"], {"c2": ["#12"]}, "a 7-character head on main marks the step")
        self.assertIn("stalled step: c2 (done: landed in #12)", out.splitlines())

    def test_head_not_on_main_marks_nothing(self):
        self.commit_step("c2", status="doing", order=2)
        self.commit_step("c3", status="doing", order=3)
        off = self.off_main()
        self.assertFalse(self.is_ancestor(off, "main"), "scope: the head must be off main")
        self.no_trailer_on_main()
        self.publish(sessions=[], items=[], landed=[self.pull_row(12, "lane/c2", head=off, merged=False),
                                                    self.pull_row(13, "lane/c3", merged=True)])
        page, _ = self.landed_build()
        landed = build_info(page)["landed"]
        self.assertEqual(landed.get("c3"), ["#13"], "control: the merged row on lane/c3 marks c3")
        self.assertNotIn("c2", landed, "an unmerged row whose head is off main marks nothing")

    def test_row_with_no_usable_head_and_not_merged_marks_nothing(self):
        self.commit_step("c2", status="doing", order=2)
        self.commit_step("c3", status="doing", order=3)
        self.no_trailer_on_main()
        self.publish(sessions=[], items=[], landed=[
            self.pull_row(14, "lane/c2"),  # no head, not merged
            self.pull_row(15, "lane/c2", head="nothex"),  # a head that is no sha
            self.pull_row(16, "lane/c2", merged=False),
            self.pull_row(17, "lane/c2", merged="true"),  # merged must be the JSON true, not text
            self.pull_row(18, "lane/c3", merged=True)])  # control
        page, _ = self.landed_build()
        landed = build_info(page)["landed"]
        self.assertEqual(landed.get("c3"), ["#18"], "control: the merged row on lane/c3 marks c3")
        self.assertNotIn("c2", landed, "a row with no usable head that is not merged marks nothing")

    def test_head_git_cannot_read_marks_nothing(self):
        self.commit_step("c2", status="doing", order=2)
        self.commit_step("c3", status="doing", order=3)
        self.no_trailer_on_main()
        for head in ("f" * 40, "fffffff"):
            with self.subTest(head=head):
                self.publish(sessions=[], items=[], landed=[self.pull_row(19, "lane/c2", head=head),
                                                            self.pull_row(20, "lane/c3", merged=True)])
                page, _ = self.landed_build()
                landed = build_info(page)["landed"]
                self.assertEqual(landed.get("c3"), ["#20"], "control: the merged row on lane/c3 marks c3")
                self.assertNotIn("c2", landed, "a head git cannot read marks nothing")

    def test_branch_must_be_the_step_or_its_lane_branch_exactly(self):
        self.commit_step("c1", status="done")
        self.commit_step("c2", status="doing", order=2)
        self.commit_step("c3", status="doing", order=3)
        self.no_trailer_on_main()
        self.publish(sessions=[], items=[], landed=[
            self.pull_row(21, "c1", merged=True),  # a done step never reads landed
            self.pull_row(22, "lane/c2x", merged=True),  # a longer name is not c2's lane
            self.pull_row(23, "c9", merged=True),  # no such step
            self.pull_row(24, "feature/c2", merged=True),  # another prefix
            self.pull_row(25, "lane/c3", merged=True)])  # control
        page, _ = self.landed_build()
        landed = build_info(page)["landed"]
        self.assertEqual(landed.get("c3"), ["#25"], "control: the merged row on lane/c3 marks c3")
        self.assertEqual(sorted(landed), ["c3"], "only the control step reads landed")

    def test_trailer_and_row_for_one_step_list_each_pr_once(self):
        self.land("c1", 7)  # a Step trailer on main, from PR #7
        self.publish(sessions=[], items=[], landed=[self.pull_row(9, "lane/c1", merged=True),
                                                    self.pull_row(7, "lane/c1", merged=True)])
        page, _ = self.build_from_main("--live", str(self.live), expect=(0, 1))
        self.assertEqual(sorted(build_info(page)["landed"]["c1"]), ["#7", "#9"],
                         "the trailer's PR and the row's PR both name c1, each once")

    def test_no_landed_pulls_key_or_empty_list_keeps_the_trailer_marks(self):
        # Green on the old code: the trailer marks are unchanged, so this is the control beside the red cases.
        self.land("c1", 9)
        self.publish(sessions=[], items=[])
        page, _ = self.build_from_main("--live", str(self.live), expect=(0, 1))
        self.assertEqual(build_info(page)["landed"], {"c1": ["#9"]}, "a file with no landedPulls key keeps the trailer mark")
        self.publish(sessions=[], items=[], landed=[])
        page, _ = self.build_from_main("--live", str(self.live), expect=(0, 1))
        self.assertEqual(build_info(page)["landed"], {"c1": ["#9"]}, "an empty landedPulls list keeps the trailer mark")

    def test_bad_rows_are_counted_in_skipped_and_mark_nothing(self):
        self.commit_step("c2", status="doing", order=2)
        self.commit_step("c3", status="doing", order=3)
        self.no_trailer_on_main()
        bad = ["lane/c2",  # a row that is not an object
               {"number": "12", "branch": "lane/c2", "merged": True},  # number is text
               {"number": True, "branch": "lane/c2", "merged": True},  # number is a bool
               {"branch": "lane/c2", "merged": True}]  # no number
        self.publish(sessions=[], items=[], landed=bad + [self.pull_row(13, "lane/c3", merged=True)])
        page, _ = self.landed_build()
        landed, live = build_info(page)["landed"], build_info(page)["live"]
        self.assertEqual(landed.get("c3"), ["#13"], "control: the good row beside the bad ones still marks c3")
        self.assertNotIn("c2", landed, "a bad row marks nothing")
        self.assertEqual(len(live["skipped"]), 4, "each of the four bad rows is counted in skipped: %r" % (live["skipped"],))

    def test_landed_pulls_that_is_not_a_list_is_skipped_and_marks_nothing(self):
        self.commit_step("c2", status="doing", order=2)
        self.no_trailer_on_main()
        for value in ({"number": 12, "branch": "lane/c2", "merged": True}, "lane/c2"):
            with self.subTest(value=value):
                self.publish(sessions=[], items=[], landed=value)
                page, _ = self.landed_build()
                self.assertEqual(build_info(page)["landed"], {}, "a landedPulls that is not a list marks nothing")
                self.assertEqual(len(build_info(page)["live"]["skipped"]), 1,
                                 "the value is counted in skipped, as the other not-a-list keys are")

    def test_thirty_two_landed_rows_mark_thirty_two_steps(self):
        for n in range(1, 33):
            self.write_step("L%02d" % n, dict(STEP, status="doing", order=n))
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "32 steps")
        self.no_trailer_on_main()
        self.publish(sessions=[], items=[], landed=[self.pull_row(100 + n, "lane/L%02d" % n, merged=True)
                                                    for n in range(1, 33)])
        page, _ = self.landed_build()
        self.assertEqual(build_info(page)["landed"], {"L%02d" % n: ["#%d" % (100 + n)] for n in range(1, 33)},
                         "every one of the 32 landed rows marks its step")

    def test_landed_todo_step_is_not_ready(self):
        ready = dict(status="todo", phase="now", note="Brief is written. Ready.")
        self.commit_step("c2", order=2, **ready)
        self.commit_step("c3", order=3, **ready)  # control: unlanded, so it is listed
        self.no_trailer_on_main()
        self.publish(sessions=[], items=[], landed=[self.pull_row(31, "lane/c2", merged=True)])
        page, _ = self.landed_build()
        listed = [s["id"] for s in self.ready_block(page)["steps"]]
        self.assertIn("c3", listed, "control: an unlanded ready step is listed")
        self.assertNotIn("c2", listed, "a todo step that landed is not ready")

    def test_merged_that_is_not_a_json_bool_skips_the_row_and_marks_nothing(self):
        self.commit_step("c2", status="doing", order=2)
        self.commit_step("c3", status="doing", order=3)
        self.no_trailer_on_main()
        for merged in ("true", 1):
            with self.subTest(merged=merged):
                self.publish(sessions=[], items=[], landed=[self.pull_row(17, "lane/c2", merged=merged),
                                                            self.pull_row(18, "lane/c3", merged=True)])  # control
                page, _ = self.landed_build()
                landed, live = build_info(page)["landed"], build_info(page)["live"]
                self.assertEqual(landed.get("c3"), ["#18"], "control: the merged row on lane/c3 marks c3")
                self.assertNotIn("c2", landed, "a merged value that is not a JSON bool marks nothing")
                self.assertEqual(len(live["skipped"]), 1,
                                 "the row with a non-bool merged is counted in skipped: %r" % (live["skipped"],))

    def test_a_skipped_landed_pull_row_reads_the_stale_and_pull_reasons_unknown(self):
        self.commit_step("c2", status="doing", order=2)
        self.no_trailer_on_main()
        self.publish(sessions=[], items=[], landed=[self.pull_row(13, "lane/c2", merged=True)])  # control: nothing skipped
        page, _ = self.landed_build()
        live = build_info(page)["live"]
        self.assertIsNone(live["staleWhy"], "control: a file with no skipped row reads no stale reason")
        self.assertIsNone(live["pullWhy"], "control: a file with no skipped row reads no pull reason")
        self.publish(sessions=[], items=[], landed=[{"number": "12", "branch": "lane/c2", "merged": True}])
        page, _ = self.landed_build()
        live = build_info(page)["live"]
        self.assertEqual(live["staleWhy"], "unknown (1 landedPulls rows skipped)",
                         "a skipped landedPulls row makes the live read unknown, as a skipped pull row does")
        self.assertEqual(live["pullWhy"], "unknown (1 landedPulls rows skipped)",
                         "the pull line reads the same unknown reason as the stale read")

    def test_merged_row_with_no_main_ref_marks_nothing(self):
        self.commit_step("c2", status="doing", order=2)
        self.no_trailer_on_main()
        self.publish(sessions=[], items=[], landed=[self.pull_row(12, "lane/c2", merged=True)])
        page, _ = self.landed_build()
        self.assertEqual(build_info(page)["landed"], {"c2": ["#12"]}, "control: with main read, the merged row marks c2")
        page, out = self.build_from_main("--live", str(self.live), "--main-branch", "nomain", expect=(0, 1))
        self.assertEqual(build_info(page)["landed"], {},
                         "with no main ref a merged row marks nothing, as the trailer path reads unknown")
        self.assertIn("stalled step: c2 (resume, pause or done)", out.splitlines())

    def test_head_with_surrounding_spaces_marks_nothing(self):
        self.commit_step("c2", status="doing", order=2)
        self.commit_step("c3", status="doing", order=3)
        behind = self.behind_main()
        self.assertTrue(self.is_ancestor(behind, "main"), "scope: the head must be an ancestor of main")
        self.no_trailer_on_main()
        self.publish(sessions=[], items=[], landed=[self.pull_row(19, "lane/c2", head=" %s " % behind),
                                                    self.pull_row(20, "lane/c3", head=behind)])  # control
        page, _ = self.landed_build()
        landed = build_info(page)["landed"]
        self.assertEqual(landed.get("c3"), ["#20"], "control: a clean ancestor head marks c3")
        self.assertNotIn("c2", landed, "a head with surrounding spaces is no sha and marks nothing")

    def test_branch_names_are_case_sensitive(self):
        self.commit_step("c2", status="doing", order=2)
        self.commit_step("c3", status="doing", order=3)
        self.no_trailer_on_main()
        self.publish(sessions=[], items=[], landed=[self.pull_row(21, "LANE/c2", merged=True),
                                                    self.pull_row(22, "C2", merged=True),
                                                    self.pull_row(23, "lane/c3", merged=True)])  # control
        page, _ = self.landed_build()
        landed = build_info(page)["landed"]
        self.assertEqual(landed.get("c3"), ["#23"], "control: the merged row on lane/c3 marks c3")
        self.assertNotIn("c2", landed, "LANE/c2 and C2 are not lane/c2 or c2 and mark nothing")


class LiveThreadsOptional(UpkeepFixture):
    """A live file with no threads list reads the rest valid: pulls, sessions and items work as they do with threads.
    Only the thread count reads unknown (threads is None, threadsWhy says why). The pulls list alone makes the whole
    read unknown (LiveWork)."""

    NO_THREADS = "unknown (the live file has no threads list)"

    def test_no_threads_list_keeps_the_read_valid(self):
        value = self.publish(threads=_ABSENT, pulls=[self.draft(7, "c1")])
        page, _ = self.build_from_main("--live", str(self.live), expect=(0, 1))
        self.assertEqual(self.panel(page)["read"], value["readAt"])

    def test_pulls_sessions_and_items_work_without_threads(self):
        session = self.session_in_repo("session_test01", "SESSION_STATUS_RUNNING", "cs-step:c1")
        for pulls in ([], [self.draft(7, "c1")]):  # an empty and a full pulls list
            with self.subTest(pulls=len(pulls)):
                value = self.publish(threads=_ABSENT, pulls=pulls, sessions=[session], items=[self.item(12, lane=None)])
                page, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
                self.assertEqual(self.panel(page)["read"], value["readAt"])
                live = build_info(page)["live"]
                self.assertEqual([p["number"] for p in live["pulls"]], [p["number"] for p in pulls])
                self.assertIsNone(live["pullWhy"])
                self.assertIsNone(live["staleWhy"])
                self.assertIsNone(live["itemsWhy"])
                self.assertEqual(live["pageItems"], [self.item(12, lane=None)])
                self.assertEqual([s["id"] for s in live["laneSessions"]], ["session_test01"])
                self.assertEqual(live["sessionSteps"], ["c1"])
                self.assertEqual(live["liveSteps"], ["c1"])
                pair = [line for line in out.splitlines() if line.startswith(build.PAIR_LINE)]
                self.assertEqual(pair, [build.PAIR_LINE + ": c1 (#7)"] if pulls else [])

    def test_threads_that_is_not_a_list_reads_only_the_thread_count_unknown(self):
        value = self.publish(threads=_ABSENT, pulls=[self.draft(7, "c1")])
        for name, threads in (("missing", _ABSENT), ("null", None), ("an object", {})):
            with self.subTest(threads=name):
                self.write_live(dict(value, threads=threads) if threads is not _ABSENT else value)
                page, _ = self.build_from_main("--live", str(self.live), expect=(0, 1))
                self.assertEqual(self.panel(page)["read"], value["readAt"])
                live = build_info(page)["live"]
                self.assertIsNone(live["threads"])
                self.assertEqual(live["threadsWhy"], self.NO_THREADS)
                self.assertEqual([p["number"] for p in live["pulls"]], [7])

    def test_missing_threads_list_is_no_skipped_entry_and_no_zero_count(self):
        value = self.publish(threads=_ABSENT, pulls=[self.draft(7, "c1")])
        page, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        self.assertEqual(self.panel(page)["read"], value["readAt"])
        live = build_info(page)["live"]
        self.assertEqual(live["skipped"], [])
        self.assertEqual(live["threadsWhy"], self.NO_THREADS)
        self.assertNotIn("live threads naming no open step: 0", out)
        row = re.search(r"^  live threads naming no open step: (.*)$", out, re.M)
        self.assertIsNotNone(row, "the upkeep output has no live threads row with its reason:\n%s" % out)
        self.assertEqual(row.group(1), self.NO_THREADS)

    def test_threads_list_present_leaves_threads_why_none(self):
        # A control: a missing key reads as None, so this case holds on the old code too, and guards the new one.
        value = self.publish(threads=[{"title": "Build a", "state": "working"}], pulls=[self.draft(7, "c1")])
        page, _ = self.build_from_main("--live", str(self.live), expect=(0, 1))  # the open pull on todo c1 is a red line
        self.assertEqual(self.panel(page)["read"], value["readAt"])
        live = build_info(page)["live"]
        self.assertEqual([t["title"] for t in live["threads"]], ["Build a"])
        self.assertIsNone(live.get("threadsWhy"))


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

    def test_doing_step_whose_only_lane_is_completed_or_failed_reads_stalled(self):
        self.commit_step("c1", status="doing")  # control: an idle lane holds it live
        self.commit_step("c2", status="doing", order=2)
        self.commit_step("c3", status="doing", order=3)  # control: a review ready lane holds it live
        for bucket in (BUCKET_COMPLETED, BUCKET_FAILED):  # coordinator 14:40 CST Nov 7: an ended lane is not live
            with self.subTest(bucket=bucket):
                self.publish(sessions=[
                    self.session_in_repo("session_test01", "SESSION_STATUS_IDLE", "cs-step:c1"),
                    session_row("session_test02", "SESSION_STATUS_IDLE", self.REPO, "cs-step:c2", status_bucket=bucket),
                    session_row("session_test03", "SESSION_STATUS_IDLE", self.REPO, "cs-step:c3",
                                status_bucket=BUCKET_REVIEW_READY),
                ], items=[])
                page, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
                self.stalled_block(page)
                self.assertEqual(self.stalled_lines(out), [self.RESUME],
                                 "only c2 is stalled; the idle and review ready lanes hold c1 and c3")
                self.assertEqual(self.code, 1, "a stalled step must exit 1")

    def test_doing_step_with_a_trailing_space_on_its_cs_step_tag_is_not_stalled(self):
        self.commit_step("c1", status="doing")  # control: no session, so it is stalled
        self.commit_step("c2", status="doing", order=2)
        self.publish(sessions=[self.session_in_repo("session_test01", "SESSION_STATUS_RUNNING", "cs-step:c2 ")], items=[])
        page, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        self.stalled_block(page)
        self.assertEqual(self.stalled_lines(out), ["stalled step: c1 (resume, pause or done)"],
                         "the stray space still names c2's lane, so c2 is not stalled")

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


class ReadyFixture(UpkeepFixture):
    """The helpers of the ready view, one home for every ready class: a live read at a fixed time, todo steps committed
    at chosen ages, and the readers of the ready block and its lines. It holds no tests."""

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

class ReadyNotStarted(ReadyFixture):
    """The ready-not-started view (plan: stalled steps, Part 2). A todo or ready step in phase now is listed in the
    page's ready block when no live lane holds it (no live cs-step session, no open pull on its id or lane/<id>), it has
    no valid `paused` field, and no open waiting-page item homed to it has a lane. Its age is whole hours from its
    updatedAt to the live read, or None. The build prints `ready not started: <id> (<age>h)` per step, or one
    `ready not started: <why>` when the read is unknown. A listed step inside the age limit never changes the exit
    code; one over it does (ReadyNextAct). The limit and its exit 1 follow coordinator 12:56 and 13:40 CST Nov 7, part 3a.
    A todo or ready step with a missing or wrongly cased phase prints an unknown line that names it, and the count reads
    unknown. A completed or failed lane is not live, so it holds no step (coordinator 14:40 CST Nov 7)."""

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
        self.ready_step("c3", order=3, updatedAt=self.before(26 * 60 + 10))  # age 26: over the 24 h limit, so exit 1
        self.known_read()
        # Coordinator 12:56 and 13:40 CST Nov 7, part 3a: a ready step over the limit exits 1, so only 1 is accepted.
        page, _ = self.build_from_main("--live", str(self.live), expect=(1,))
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

    def test_ready_lines_inside_the_limit_never_change_the_exit_code(self):
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

    def test_cs_step_tag_with_a_trailing_space_holds_the_step_back(self):
        self.ready_step("c2", order=2)
        self.ready_step("c3", order=3)  # control: no session names it
        # idle_lanes strips the step id from the tag, so the live read must too: the stray space still names c2.
        self.known_read(sessions=[self.session_in_repo("session_test01", "SESSION_STATUS_RUNNING", "cs-step:c2 ")])
        page, _ = self.build_from_main("--live", str(self.live))
        self.assertEqual(self.ready_ids(self.ready_block(page)), ["c3"], "a cs-step:c2 tag with a trailing space holds c2")

    def test_todo_step_whose_only_lane_is_completed_or_failed_is_ready_and_starts_a_lane(self):
        self.ready_step("c2", order=2)  # coordinator 14:40 CST Nov 7: an ended lane holds no step
        for bucket in (BUCKET_COMPLETED, BUCKET_FAILED):
            with self.subTest(bucket=bucket):
                ended = session_row("session_test01", "SESSION_STATUS_IDLE", self.REPO, "cs-step:c2", status_bucket=bucket)
                self.known_read(sessions=[ended])
                page, out = self.build_from_main("--live", str(self.live))
                ready = self.ready_block(page)
                self.assertEqual(self.ready_ids(ready), ["c2"], "the ended lane holds no step, so c2 is ready")
                self.assertEqual([s["act"] for s in ready["steps"]], ["start lane"], "the ready step's next act is start lane")
                self.assertEqual(self.ready_lines(out), ["ready not started: c2 (3h)"], "the step prints its ready line")
                self.assertEqual(count_lines(out), [ready_line("count", n=1)], "the ready count counts the step")

    def test_idle_and_review_ready_lanes_still_hold_the_step_back(self):
        self.ready_step("c2", order=2)  # held by an idle lane with no bucket, as the IDLE pin reads it
        self.ready_step("c3", order=3)  # held by a review ready lane
        self.ready_step("c4", order=4)  # control: no lane
        self.known_read(sessions=[
            self.session_in_repo("session_test01", "SESSION_STATUS_IDLE", "cs-step:c2"),
            session_row("session_test02", "SESSION_STATUS_IDLE", self.REPO, "cs-step:c3", status_bucket=BUCKET_REVIEW_READY),
        ])  # coordinator 14:40 CST Nov 7: only a completed or failed lane ends its hold
        page, _ = self.build_from_main("--live", str(self.live))
        self.assertEqual(self.ready_ids(self.ready_block(page)), ["c4"], "an idle lane and a review ready lane hold their steps")

    def test_todo_step_with_a_landed_mark_does_not_read_start_lane(self):
        # Coordinator 13:20 CST Nov 7: a step that landed on main has no lane to start.
        self.land("c2", 12, status="todo", phase="now", order=2, updatedAt=self.before(190))
        self.ready_step("c3", order=3)  # control: no landing, so it reads start lane
        self.known_read()
        page, _ = self.build_from_main("--live", str(self.live))
        ready = self.ready_block(page)
        self.assertIn("c3", self.ready_ids(ready), "the control step is listed")
        acts = {s["id"]: s["act"] for s in ready["steps"]}
        self.assertEqual(acts["c3"], "start lane", "control: a step with no landing reads start lane")
        self.assertNotEqual(acts.get("c2"), "start lane", "a todo step that landed on main does not read start lane")

    def test_wrongly_cased_phase_prints_an_unknown_line_that_names_the_step(self):
        self.ready_step("c2", order=2, phase="Now")  # not `now`, so the step must not drop out silently
        self.known_read()
        _, out = self.build_from_main("--live", str(self.live))
        self.assert_unknown_phase(out, "c2")

    def test_missing_phase_prints_an_unknown_line_that_names_the_step(self):
        self.ready_step("c2", order=2, phase=_ABSENT)
        self.known_read()
        _, out = self.build_from_main("--live", str(self.live))
        self.assert_unknown_phase(out, "c2")

    def test_phase_with_a_trailing_space_prints_an_unknown_line_that_names_the_step(self):
        # A stray space is not a phase name, so the step must not drop out of the ready list with no line.
        self.ready_step("c2", order=2, phase="now ")
        self.known_read()
        _, out = self.build_from_main("--live", str(self.live))
        self.assert_unknown_phase(out, "c2")

    def assert_unknown_phase(self, out, sid):
        """A todo step with no usable phase prints one unknown ready line that names it, and the count reads unknown."""
        named = [line for line in out.splitlines()
                 if line.startswith("ready not started: unknown (") and re.search(r"\b%s\b" % sid, line)]
        self.assertEqual(len(named), 1, "%s prints one unknown ready line that names it" % sid)
        counts = count_lines(out)
        self.assertEqual(len(counts), 1, "the count line prints once")
        self.assertTrue(counts[0].startswith("ready not started count: unknown ("), "the count reads unknown, never 0: %r" % counts[0])

    def test_steps_unknown_prints_one_unknown_ready_line(self):
        self.on_main()
        code, out = run_build("--repo", str(self.repo), "--record-branch", "no-such-branch", "--out", str(self.out))
        self.assertIn(code, (0, None), out)
        self.assertEqual(self.ready_lines(out), ["ready not started: unknown (steps unknown)"],
                         "with no steps, the build prints one unknown ready line")


# The age limit of a ready step (READY_AGE_LIMIT_HOURS in build.py). Read with getattr, so a missing name fails the one
# constant case by name and every other case still goes red on its behaviour, not as an import error.
LIMIT_HOURS = getattr(build, "READY_AGE_LIMIT_HOURS", 24)
# The one home of the exact text of the next-act lines. The count line does not start `ready not started: <id>`, so it
# never reads as a per-step line. `count unknown` takes the ready block's why, which already reads `unknown (<why>)`, as
# the ready-not-started line does.
READY_LINE_FORMATS = {
    "over": "ready over limit: {id} (start lane; owner {owner}; age {age}h)",
    "count": "ready not started count: {n}",
    "count unknown": "ready not started count: {why}",
}
NEXT_ACT_KEYS = ("id", "act", "owner", "age")  # the keys a doing entry and a ready entry share


def ready_line(kind, **fields):
    """The exact text of one next-act line of `kind`, from READY_LINE_FORMATS."""
    return READY_LINE_FORMATS[kind].format(**fields)


def over_lines(out):
    return re.findall(r"^ready over limit: .*$", out, re.M)


def count_lines(out):
    return re.findall(r"^ready not started count: .*$", out, re.M)


class ReadyNextAct(ReadyFixture):
    """The next act, owner and age limit of the ready steps (the PR-ledger design, part 3a). A ready step's next act is
    `start lane`. A doing or active step with no lane takes its act from the same next-act function, so the stalled
    entries and the ready entries carry the same keys. A ready step more than LIMIT_HOURS whole hours past its
    updatedAt prints one `ready over limit` line and the build exits 1. The build always prints `ready not started count: <N>`,
    zero included, or `ready not started count: <why>` when the read is unknown. Each exclusion case also holds an over-limit
    control step, so the case goes red on the old code where the control's line is missing."""

    def aged(self, hours):
        """An updatedAt `hours` whole hours before the live read: ten minutes past the hour, so the floor reads hours."""
        return self.before(hours * 60 + 10)

    def test_the_age_limit_is_one_constant_of_24_hours(self):
        self.assertTrue(hasattr(build, "READY_AGE_LIMIT_HOURS"), "build.py has no READY_AGE_LIMIT_HOURS constant")
        self.assertEqual(build.READY_AGE_LIMIT_HOURS, 24, "the ready age limit is 24 whole hours")

    def test_a_ready_step_over_the_limit_prints_one_red_line_and_exits_1(self):
        self.ready_step("c2", order=2, updatedAt=self.aged(LIMIT_HOURS + 1))  # over the limit
        self.ready_step("c3", order=3, updatedAt=self.aged(LIMIT_HOURS - 1))  # inside it: listed, no red line
        self.known_read()
        page, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        self.assertEqual(self.ready_ids(self.ready_block(page)), ["c2", "c3"], "both ready steps are listed")
        self.assertEqual(over_lines(out), [ready_line("over", id="c2", owner="coordinator", age=LIMIT_HOURS + 1)],
                         "one red line for the step over the limit, none for the one inside it")
        self.assertEqual(self.code, 1, "a ready step over the limit exits 1")

    def test_a_ready_step_at_24_h_10_min_is_inside_the_limit(self):
        self.ready_step("c2", order=2, updatedAt=self.aged(LIMIT_HOURS))  # age 24: 24 whole hours is not over a 24 h limit
        self.ready_step("c3", order=3, updatedAt=self.aged(LIMIT_HOURS + 1))  # control: age 25, over
        self.known_read()
        page, out = self.build_from_main("--live", str(self.live), expect=(1,))
        self.assertIn("ready not started: c2 (24h)", out.splitlines(), "c2 is listed at age 24")
        self.assertEqual(over_lines(out), [ready_line("over", id="c3", owner="coordinator", age=LIMIT_HOURS + 1)],
                         "only the control is over; a limit read as 24 or more would also mark c2")

    def test_a_ready_step_over_the_limit_names_its_owner_and_an_absent_owner_reads_coordinator(self):
        self.ready_step("c2", order=2, updatedAt=self.aged(LIMIT_HOURS + 1), owner="triage")
        self.ready_step("c3", order=3, updatedAt=self.aged(LIMIT_HOURS + 1))  # no owner field
        self.known_read()
        page, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        self.assertEqual(over_lines(out), [ready_line("over", id="c2", owner="triage", age=LIMIT_HOURS + 1),
                                           ready_line("over", id="c3", owner="coordinator", age=LIMIT_HOURS + 1)],
                         "the owner field names the owner; an absent one reads coordinator")
        self.assertEqual([s.get("owner") for s in self.ready_block(page)["steps"]], ["triage", "coordinator"],
                         "the ready entries carry the same owners")

    def test_a_ready_entry_carries_the_next_act_start_lane(self):
        self.ready_step("c2", order=2)  # 3 h, inside the limit
        self.known_read()
        page, _ = self.build_from_main("--live", str(self.live))
        self.assertEqual([s.get("act") for s in self.ready_block(page)["steps"]], ["start lane"],
                         "a ready step's one next act is start lane")

    def test_a_doing_entry_and_a_ready_entry_share_one_shape(self):
        git(self.repo, "checkout", "-q", "roadmap")
        self.commit_step("c2", status="doing", order=2, updatedAt=self.aged(3))  # no lane: stalled
        self.ready_step("c3", order=3, updatedAt=self.aged(3))  # ready, inside the limit
        self.known_read()
        page, _ = self.build_from_main("--live", str(self.live), expect=(0, 1))
        stalled = self.stalled_block(page)["steps"]
        ready = self.ready_block(page)["steps"]
        self.assertEqual([s["id"] for s in stalled], ["c2"], "the doing step is the stalled entry")
        self.assertEqual([s["id"] for s in ready], ["c3"], "the todo step is the ready entry")
        for name, entries in (("stalled", stalled), ("ready", ready)):
            for entry in entries:
                self.assertEqual([k for k in NEXT_ACT_KEYS if k not in entry], [],
                                 "the %s entry %s lacks a next-act key" % (name, entry.get("id")))
        self.assertEqual(stalled[0]["act"], "resume, pause or done", "a doing step with no lane is resumed, paused or done")
        self.assertEqual(ready[0]["act"], "start lane", "a ready step's next act is start lane")
        self.assertEqual([stalled[0]["owner"], ready[0]["owner"]], ["coordinator", "coordinator"],
                         "an absent owner reads coordinator on both")
        self.assertEqual([stalled[0]["age"], ready[0]["age"]], [3, 3], "age is whole hours from updatedAt, on both")

    def test_an_excluded_step_prints_no_red_line_even_when_it_is_old(self):
        live_session = [self.session_in_repo("session_test01", "SESSION_STATUS_RUNNING", "cs-step:c2")]
        open_item = [self.item(4, home="step c2", status="open", lane=None)]
        cases = {  # name: (fields for c2, arguments of known_read)
            "live cs-step lane": ({}, {"sessions": live_session}),
            "valid pause": ({"paused": StalledStep.PAUSE}, {}),
            "later phase": ({"phase": "next"}, {}),
            "open unanswered item": ({}, {"items": open_item}),
        }
        for name, (fields, live) in cases.items():
            with self.subTest(name):
                git(self.repo, "checkout", "-q", "roadmap")
                self.ready_step("c2", order=2, updatedAt=self.aged(LIMIT_HOURS + 5), note=name, **fields)
                self.ready_step("c3", order=3, updatedAt=self.aged(LIMIT_HOURS + 1), note="control " + name)  # over, not excluded
                self.known_read(**live)
                page, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
                self.assertEqual(over_lines(out), [ready_line("over", id="c3", owner="coordinator", age=LIMIT_HOURS + 1)],
                                 "%s: the control prints its red line" % name)
                self.assertEqual(self.ready_ids(self.ready_block(page)), ["c3"], "%s: c2 is excluded from the ready list" % name)

    def test_unread_main_reads_the_ready_list_unknown_and_never_start_lane(self):
        # With main unread, no step can be shown landed, so the list reads unknown. The control is the same build with main read.
        self.ready_step("c2", order=2, updatedAt=self.aged(LIMIT_HOURS + 1))  # over the limit, so a listed line would say start lane
        self.known_read()
        _, out = self.build_from_main("--live", str(self.live), expect=(1,))
        self.assertEqual(over_lines(out), [ready_line("over", id="c2", owner="coordinator", age=LIMIT_HOURS + 1)],
                         "control: with main read, c2 prints its red line")
        page, out = self.build_from_main("--live", str(self.live), "--main-branch", "nomain", expect=(0, 1))
        ready = self.ready_block(page)
        self.assertIsNone(ready.get("steps"), "an unread main reads the ready list unknown, never a list of steps")
        self.assertTrue(str(ready.get("why")).startswith("unknown ("), "the why reads %r, not unknown (...)" % ready.get("why"))
        self.assertEqual(self.ready_lines(out), ["ready not started: %s" % ready["why"]], "the list prints one unknown line")
        counts = count_lines(out)
        self.assertTrue(counts and counts[0].startswith("ready not started count: unknown ("),
                        "the count reads unknown, never 0: %r" % counts)
        self.assertEqual([line for line in out.splitlines() if line.startswith("ready ") and "start lane" in line], [],
                         "no ready line says start lane when main is unread")
        self.assertEqual(self.code, 0, "an unknown ready read stalls nothing")

    def test_todo_step_held_by_an_open_pull_named_for_it_prints_no_ready_red_line(self):
        # The pull's branch is not the step id, so no lane holds the step. Its title names the step, and that holds it back.
        pull = {"number": 60, "title": "c2: finish the fix", "branch": "lane-x"}
        self.ready_step("c2", order=2, updatedAt=self.aged(LIMIT_HOURS + 6))  # 30 h old
        self.known_read(pulls=[pull])
        page, out = self.build_from_main("--live", str(self.live), expect=(1,))  # the exit 1 is the pair line's, not a ready line's
        self.assertEqual(self.ready_ids(self.ready_block(page)), [], "a step its pull names is held, not listed as ready")
        self.assertEqual(over_lines(out), [], "the held step prints no ready red line")
        self.assertEqual(count_lines(out), ["ready not started count: 0"], "the count reads zero")
        self.assertEqual(re.findall(r"^%s: (.*)$" % re.escape(TodoWithOpenPull.PAIR), out, re.M), ["c2 (#60)"],
                         "the pair line still names the step and its pull")
        self.known_read()  # control: the same old step with no pull is listed and goes red
        page, out = self.build_from_main("--live", str(self.live), expect=(1,))
        self.assertEqual(over_lines(out), [ready_line("over", id="c2", owner="coordinator", age=LIMIT_HOURS + 6)],
                         "control: with no pull, c2 is listed and prints its red line")
        self.assertEqual(count_lines(out), ["ready not started count: 1"], "control: the count reads one")

    def test_a_ready_step_with_no_age_prints_no_red_line(self):
        self.ready_step("c2", order=2, updatedAt=_ABSENT)  # no age, so nothing shows it over the limit
        self.ready_step("c3", order=3, updatedAt=self.aged(LIMIT_HOURS + 1))  # control: over
        self.known_read()
        page, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        self.assertEqual(over_lines(out), [ready_line("over", id="c3", owner="coordinator", age=LIMIT_HOURS + 1)],
                         "the control prints its red line; c2 with no age prints none")
        self.assertEqual(self.ready_ids(self.ready_block(page)), ["c2", "c3"], "c2 is still listed, with age unknown")

    def test_a_doing_step_over_the_limit_stays_stalled_and_prints_no_ready_red_line(self):
        git(self.repo, "checkout", "-q", "roadmap")
        self.commit_step("c2", status="doing", order=2, updatedAt=self.aged(LIMIT_HOURS + 5))  # no lane: stalled by its status
        self.ready_step("c3", order=3, updatedAt=self.aged(LIMIT_HOURS + 1))  # control: over, a ready red line
        self.known_read()
        _, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        self.assertEqual(over_lines(out), [ready_line("over", id="c3", owner="coordinator", age=LIMIT_HOURS + 1)],
                         "the control is the only ready red line")
        self.assertIn(StalledStep.RESUME, out.splitlines(), "the doing step stays a stalled line")

    def test_the_count_line_is_the_number_of_listed_ready_steps(self):
        self.ready_step("c2", order=2)  # inside the limit
        self.ready_step("c3", order=3, updatedAt=self.aged(LIMIT_HOURS + 1))  # over the limit
        self.known_read()
        _, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        self.assertEqual(count_lines(out), [ready_line("count", n=2)], "two listed ready steps, one of them over, count 2")

    def test_the_count_line_reads_zero_when_no_step_is_ready(self):
        self.known_read()  # the fixture's c1 is in phase cleanup, so nothing is ready
        _, out = self.build_from_main("--live", str(self.live))
        self.assertEqual(count_lines(out), [ready_line("count", n=0)], "zero ready steps prints 0, not no line")

    def test_the_count_line_reads_unknown_never_zero_when_the_read_is_unknown(self):
        self.ready_step("c2", order=2, updatedAt=self.aged(LIMIT_HOURS + 1))  # over, so a known read would print red
        self.publish(sessions=None, items=[], read_at=self.read_at)  # no sessions list
        page, out = self.build_from_main("--live", str(self.live))
        why = self.ready_block(page)["why"]
        self.assertTrue(str(why).startswith("unknown ("), "the ready block says why the read is unknown")
        self.assertEqual(count_lines(out), [ready_line("count unknown", why=why)], "an unknown read prints unknown, never 0")
        self.assertEqual(over_lines(out), [], "an unknown read prints no red line")
        self.assertEqual(self.code, 0, "an unknown read exits 0")

    def test_the_count_line_reads_unknown_when_the_steps_are_unknown(self):
        self.on_main()
        _, out = run_build("--repo", str(self.repo), "--record-branch", "no-such-branch", "--out", str(self.out))
        self.assertEqual(count_lines(out), [ready_line("count unknown", why="unknown (steps unknown)")],
                         "with no steps, the count is unknown, never 0")

    def test_every_over_the_limit_step_prints_its_own_red_line_at_full_size(self):
        git(self.repo, "checkout", "-q", "roadmap")
        for n in range(1, 26):
            self.write_step("r%02d" % n, dict(STEP, status="todo", phase="now", order=n, updatedAt=self.aged(LIMIT_HOURS + 1)))
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "25 over-limit ready steps")
        self.known_read()
        _, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        self.assertEqual(over_lines(out), [ready_line("over", id="r%02d" % n, owner="coordinator", age=LIMIT_HOURS + 1)
                                           for n in range(1, 26)], "one red line per step, in step order")
        self.assertEqual(count_lines(out), [ready_line("count", n=25)], "the count is 25")


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


class LiveStatusPhase(UpkeepFixture):
    """A phase is live when it holds an open step whose status is in build.LIVE_STATUS (doing, and the legacy active).
    The two rows, `untouched 5 days in a live phase` (updatedAt STALE_DAYS old or more) and `no note in a live phase`
    (an empty note), read the open steps of a live phase whose status is todo, ready or live. A step with no
    phase never makes a phase live and is never listed. A phase holding only blocked, folded or ready steps is not live."""

    STALE = "untouched 5 days in a live phase"
    EMPTY = "no note in a live phase"

    def ten_days_ago(self):
        return iso_ago(10 * 24 * 60)

    def stale_and_empty(self):
        """((count, sorted entries) of the stale row, the same of the empty row), from one build of main with no --live file."""
        _, out = self.build_from_main()
        stale_count, stale = self.row(out, self.STALE)
        empty_count, empty = self.row(out, self.EMPTY)
        return (stale_count, self.entries(stale)), (empty_count, self.entries(empty))

    def test_a_phase_holding_a_doing_step_is_live(self):
        self.commit_step("build-doing", status="doing", phase="build", note="Working.", updatedAt=iso_ago(5), order=1)
        self.commit_step("build-ready", status="ready", phase="build", note="Parked for a lane.",
                         updatedAt=self.ten_days_ago(), order=2)
        self.commit_step("build-todo", status="todo", phase="build", note="", updatedAt=iso_ago(5), order=3)
        self.commit_step("later-todo", status="todo", phase="later", note="", updatedAt=self.ten_days_ago(), order=4)
        stale, empty = self.stale_and_empty()
        self.assertEqual(stale, (1, ["build-ready"]),
                         "build holds a doing step, so it is live and its ready step, untouched 10 days, is listed")
        self.assertEqual(empty, (1, ["build-todo"]),
                         "build is live, so its empty todo step is listed; later is not live, so later-todo is in neither row")

    def test_a_phase_holding_only_blocked_or_folded_steps_is_not_live(self):
        self.commit_step("build-doing", status="doing", phase="build", note="Working.", updatedAt=iso_ago(5), order=1)
        self.commit_step("build-ready", status="ready", phase="build", note="Parked for a lane.",
                         updatedAt=self.ten_days_ago(), order=2)
        self.commit_step("stuck-blocked", status="blocked", phase="stuck", note="", updatedAt=self.ten_days_ago(), order=3)
        self.commit_step("waiting-folded", status="folded", phase="waiting", note="", updatedAt=self.ten_days_ago(), order=4)
        (_, stale), (_, empty) = self.stale_and_empty()
        self.assertIn("build-ready", stale, "scope first: build holds a doing step, so its ready step is listed")
        self.assertNotIn("stuck-blocked", stale + empty, "stuck holds only a blocked step, so it is not live")
        self.assertNotIn("waiting-folded", stale + empty, "waiting holds only a folded step, so it is not live")

    def test_a_legacy_active_step_still_makes_its_phase_live(self):
        # A legacy active step still makes its phase live, which the upkeep rows in this file depend on.
        self.commit_step("legacy-active", status="active", phase="build", note="Working.", updatedAt=iso_ago(5), order=1)
        self.commit_step("build-ready", status="ready", phase="build", note="Parked for a lane.",
                         updatedAt=self.ten_days_ago(), order=2)
        self.commit_step("build-todo", status="todo", phase="build", note="", updatedAt=iso_ago(5), order=3)
        stale, empty = self.stale_and_empty()
        self.assertEqual(stale, (1, ["build-ready"]), "an active step makes build live, so its ready step is listed")
        self.assertEqual(empty, (1, ["build-todo"]), "an active step makes build live, so its empty todo step is listed")

    def test_live_status_is_exactly_doing_and_active(self):
        self.assertTrue(hasattr(build, "LIVE_STATUS"),
                        "build has no LIVE_STATUS, so upkeep spells its live statuses out")
        self.assertEqual(tuple(build.LIVE_STATUS), ("doing", "active"),
                         "LIVE_STATUS holds doing and the legacy active; done, ready and todo are not live")
        unknown = [s for s in build.LIVE_STATUS if s not in build.KNOWN_STATUS]
        self.assertEqual(unknown, [], "each LIVE_STATUS entry is in KNOWN_STATUS")

    def test_upkeep_spells_no_status_literal_of_its_own(self):
        # Any status word in upkeep's code is a second spelling, so the check reads each string constant against
        # build.KNOWN_STATUS, the one home of the status words.
        tree = ast.parse(inspect.getsource(build.upkeep))
        literal = sorted(n.lineno for n in ast.walk(tree) if isinstance(n, ast.Constant) and n.value in build.KNOWN_STATUS)
        self.assertEqual(literal, [], "upkeep spells a status word itself, at these lines of its source; "
                                      "it must read the status constants in build")

    def test_thirty_stale_steps_in_a_live_phase_are_all_listed(self):
        self.commit_step("build-doing", status="doing", phase="build", note="Working.", updatedAt=iso_ago(5), order=1)
        ids = sorted("ready-%02d" % i for i in range(30))
        for n, sid in enumerate(ids, start=2):
            self.commit_step(sid, status="ready", phase="build", note="Parked for a lane.",
                             updatedAt=self.ten_days_ago(), order=n)
        (count, stale), _ = self.stale_and_empty()
        self.assertEqual(count, 30, "all 30 stale ready steps in build are counted")
        self.assertEqual(stale, ids, "the row lists all 30, with no cut-off for a long list")

    def test_folded_blocked_and_queued_steps_are_read_by_neither_row(self):
        self.commit_step("build-doing", status="doing", phase="build", note="Working.", updatedAt=iso_ago(5), order=1)
        self.commit_step("build-folded", status="folded", phase="build", note="", updatedAt=self.ten_days_ago(), order=2)
        self.commit_step("build-blocked", status="blocked", phase="build", note="", updatedAt=self.ten_days_ago(), order=3)
        self.commit_step("build-queued", status="queued", phase="build", note="", updatedAt=self.ten_days_ago(), order=4)
        self.commit_step("build-todo", status="todo", phase="build", note="", updatedAt=self.ten_days_ago(), order=5)
        (stale_count, stale), (empty_count, empty) = self.stale_and_empty()
        self.assertIn("build-todo", stale, "scope first: build is live, so its todo step, untouched 10 days, is listed")
        self.assertEqual((stale_count, stale), (1, ["build-todo"]),
                         "the stale row reads todo, ready and live steps, so folded, blocked and queued are not listed")
        self.assertEqual((empty_count, empty), (1, ["build-todo"]),
                         "the empty row reads todo, ready and live steps, so folded, blocked and queued are not listed")

    def test_a_step_with_no_phase_makes_no_phase_live_and_is_never_listed(self):
        self.commit_step("build-doing", status="doing", phase="build", note="Working.", updatedAt=iso_ago(5), order=1)
        self.commit_step("build-ready", status="ready", phase="build", note="Parked for a lane.",
                         updatedAt=self.ten_days_ago(), order=2)
        for name, phase in (("absent", _ABSENT), ("null", None)):
            with self.subTest(name):
                git(self.repo, "checkout", "-q", "roadmap")
                self.commit_step("nophase-doing", status="doing", phase=phase, note="Working.", updatedAt=iso_ago(5), order=3)
                self.commit_step("nophase-todo", status="todo", phase=phase, note="", updatedAt=self.ten_days_ago(), order=4)
                (_, stale), (_, empty) = self.stale_and_empty()
                self.assertIn("build-ready", stale, "scope first: build is live, so its ready step, untouched 10 days, is listed")
                self.assertNotIn("nophase-todo", stale, "a step with no phase is never listed in the stale row")
                self.assertNotIn("nophase-todo", empty, "a step with no phase is never listed in the empty row")

    def test_a_doing_step_and_an_active_step_are_listed_in_both_rows(self):
        self.commit_step("build-doing", status="doing", phase="build", note="", updatedAt=self.ten_days_ago(), order=1)
        self.commit_step("legacy-active", status="active", phase="legacy", note="", updatedAt=self.ten_days_ago(), order=2)
        (stale_count, stale), (empty_count, empty) = self.stale_and_empty()
        self.assertEqual((stale_count, stale), (2, ["build-doing", "legacy-active"]),
                         "doing and active are live statuses, so both steps are listed in the stale row")
        self.assertEqual((empty_count, empty), (2, ["build-doing", "legacy-active"]),
                         "doing and active are live statuses, so both steps are listed in the empty row")

    def test_a_phase_holding_only_a_ready_step_is_not_live(self):
        self.commit_step("build-doing", status="doing", phase="build", note="Working.", updatedAt=iso_ago(5), order=1)
        self.commit_step("build-todo", status="todo", phase="build", note="", updatedAt=self.ten_days_ago(), order=2)
        self.commit_step("ready-only", status="ready", phase="ready-only", note="", updatedAt=self.ten_days_ago(), order=3)
        (_, stale), (_, empty) = self.stale_and_empty()
        self.assertIn("build-todo", empty, "scope first: build is live, so its empty todo step is listed")
        self.assertEqual(stale, ["build-todo"], "ready-only holds no live step, so it is not live and is not listed")
        self.assertEqual(empty, ["build-todo"], "ready-only holds no live step, so it is not live and is not listed")

    def test_blocked_and_folded_are_known_statuses_and_not_listed(self):
        self.assertIn("todo", build.LISTED_STATUS, "scope first: LISTED_STATUS holds the statuses the stale and empty rows read")
        missing = [s for s in ("blocked", "folded") if s not in build.KNOWN_STATUS]
        self.assertEqual(missing, [], "KNOWN_STATUS lacks these statuses, so upkeep reports a step in one as unknown")
        listed = [s for s in ("blocked", "folded") if s in build.LISTED_STATUS]
        self.assertEqual(listed, [], "LISTED_STATUS holds these statuses, so the stale and empty rows read a step in one")

    def test_queued_is_not_a_known_status(self):
        self.assertIn("blocked", build.KNOWN_STATUS, "scope first: KNOWN_STATUS holds the statuses that stay")
        self.assertNotIn("queued", build.KNOWN_STATUS, "queued is retired, so KNOWN_STATUS does not accept it")

    def test_queued_is_not_a_listed_status(self):
        self.assertIn("todo", build.LISTED_STATUS, "scope first: LISTED_STATUS holds the statuses the stale and empty rows read")
        self.assertNotIn("queued", build.LISTED_STATUS, "queued is retired, so the stale and empty rows do not read it")

    def test_queued_is_an_unknown_status_entry_and_blocked_and_folded_are_not(self):
        self.commit_step("c-waiting", status="waiting", order=1)  # an unknown status is still listed
        for order, status in enumerate(("blocked", "folded", "queued"), start=2):
            self.commit_step("c-" + status, status=status, order=order)
        self.publish(sessions=[])
        _, detail = self.row(self.out_with_live(), StaleInProgress.ROW)
        self.assertIn('c-waiting (unknown status "waiting")', self.entries(detail),
                      "scope first: the row lists a step with an unknown status")
        self.assertEqual(self.entries(detail), ['c-queued (unknown status "queued")', 'c-waiting (unknown status "waiting")'],
                         "queued is retired, so the row lists it as an unknown status; blocked and folded are known, so they are not listed")

    def test_build_spells_the_live_statuses_only_in_live_status(self):
        path = HERE / "build.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        home = set()  # the nodes of the LIVE_STATUS assignment, the one place the two words are listed together
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "LIVE_STATUS" for t in node.targets):
                home.update(id(n) for n in ast.walk(node.value))
        words = ("doing", "active")
        lists = sorted(n.lineno for n in ast.walk(tree)
                       if isinstance(n, (ast.Tuple, ast.List, ast.Set)) and id(n) not in home
                       and all(w in {e.value for e in n.elts if isinstance(e, ast.Constant)} for w in words))
        compares = sorted(n.lineno for n in ast.walk(tree)
                          if isinstance(n, ast.Compare) and any(isinstance(op, ast.Eq) for op in n.ops)
                          and any(isinstance(x, ast.Constant) and x.value in words for x in [n.left, *n.comparators]))
        self.assertEqual(lists, [], "a tuple or list holds both doing and active at these lines of build.py, outside LIVE_STATUS")
        self.assertEqual(compares, [], "an == comparison with doing or active is at these lines of build.py")


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


class WaitOnClosedPull(UpkeepFixture):
    """The upkeep row for an open step whose title, why or note waits on a pull request that GitHub shows closed and
    unmerged (roadmap step dead-pr-waits, a wait on a dead PR). The build reads GitHub's answer from the --live file and never calls GitHub: a
    closed pull is a landedPulls row with merged false, and an open pull is a pulls row. Each negative case shares its
    live file with a control that the row must name, so an empty row cannot pass."""

    LABEL = "open step waits on a closed unmerged PR"
    CONTROL = "c-closed"

    def closed(self, number):
        return self.pull_row(number, "lane-%d" % number, merged=False)

    def merged(self, number):
        return self.pull_row(number, "lane-%d" % number, merged=True)

    def listed(self, out):
        return self.entries(self.row(out, self.LABEL)[1])

    def assert_control_listed(self, out):
        self.assertIn("%s (#41)" % self.CONTROL, self.listed(out),
                      "the control step, which waits on the closed unmerged #41, is not in the %r row:\n%s" % (self.LABEL, out))

    def test_open_step_waiting_on_a_closed_unmerged_pull_is_listed(self):
        self.commit_step(self.CONTROL, note="Waits on #41 to land.")
        self.publish(landed=[self.closed(41)])
        out = self.out_with_live()
        self.assertEqual(self.listed(out), ["c-closed (#41)"], "the closed unmerged #41 is not listed as its waiting step")

    def test_wait_in_title_or_why_is_listed_like_one_in_the_note(self):
        self.commit_step("c-title", title="Waits on #51 to land", note="n")
        self.commit_step("c-why", why="Blocked on #52 for its fix.", note="n")
        self.commit_step(self.CONTROL, note="Waits on #41 to land.")
        self.publish(landed=[self.closed(41), self.closed(51), self.closed(52)])
        out = self.out_with_live()
        self.assert_control_listed(out)
        for sid, pr in (("c-title", 51), ("c-why", 52)):
            with self.subTest(field=sid):
                self.assertIn("%s (#%d)" % (sid, pr), self.listed(out),
                              "a wait on closed unmerged #%d in the step %s is not listed" % (pr, sid))

    def test_open_pull_is_not_listed(self):
        self.commit_step(self.CONTROL, note="Waits on #41 to land.")
        self.commit_step("c-open", note="Waits on #42 to land.")
        self.publish(landed=[self.closed(41)], pulls=[{"number": 42, "title": "lane 42", "branch": "lane-42"}])
        out = self.out_with_live()
        self.assert_control_listed(out)
        self.assertNotIn("c-open (#42)", self.listed(out), "a step that waits on the open #42 is listed as waiting on a closed PR")

    def test_merged_pull_is_not_listed(self):
        self.commit_step(self.CONTROL, note="Waits on #41 to land.")
        self.commit_step("c-merged", note="Waits on #43 to land.")
        self.publish(landed=[self.closed(41), self.merged(43)])
        out = self.out_with_live()
        self.assert_control_listed(out)
        self.assertNotIn("c-merged (#43)", self.listed(out), "a step that waits on the merged #43 is listed as waiting on a closed PR")

    def test_done_step_is_not_listed(self):
        self.commit_step(self.CONTROL, note="Waits on #41 to land.")
        self.commit_step("c-done", status="done", note="Waits on #44 to land.")
        self.publish(landed=[self.closed(41), self.closed(44)])
        out = self.out_with_live()
        self.assert_control_listed(out)
        self.assertNotIn("c-done (#44)", self.listed(out), "a done step that waits on #44 is listed; a done step is not open")

    def test_each_wait_phrase_the_roadmap_writes_is_listed(self):
        # One step per phrase, each waiting on its own closed unmerged pull (#61 on). Each subtest names one phrase.
        waits = (("stacked on", "Stacked on #61 for its base."), ("stacks on", "This stacks on #62."),
                 ("stack on", "Stack on #63 for its base."), ("built on", "Built on #64 and its fix."),
                 ("waits for", "Waits for #65 to land."), ("wait for", "Wait for #66 to land."),
                 ("waiting on", "Waiting on #67 to land."), ("lands with", "Lands with #68 in one batch."),
                 ("after PR", "Ships after PR #69 lands."), ("once PR", "Runs once PR #70 lands."))
        self.commit_step(self.CONTROL, note="Waits on #41 to land.")
        steps = {}
        for n, (phrase, note) in enumerate(waits, start=61):
            sid = "w-" + phrase.replace(" ", "-")
            self.commit_step(sid, note=note)
            steps[phrase] = (sid, n)
        self.publish(landed=[self.closed(41)] + [self.closed(n) for _, n in steps.values()])
        out = self.out_with_live()
        self.assert_control_listed(out)
        for phrase, (sid, n) in steps.items():
            with self.subTest(phrase=phrase):
                self.assertIn("%s (#%d)" % (sid, n), self.listed(out),
                              "the wait phrase %r on the closed unmerged #%d is not listed" % (phrase, n))

    def test_live_file_with_no_landed_pulls_key_reads_the_row_unknown(self):
        self.commit_step(self.CONTROL, note="Waits on #41 to land.")
        self.publish(pulls=[])  # no landedPulls key: the closed #41 is unknown, not known to be absent
        out = self.out_with_live()
        count, detail = self.row(out, self.LABEL)
        self.assertTrue(detail.startswith("unknown ("),
                        "the row reads %r when the live file has no landedPulls key, not unknown:\n%s" % (detail, out))
        self.assertEqual(count, 1, "the unknown row counts %d entries, not one:\n%s" % (count, out))

    def test_empty_landed_pulls_list_reads_the_row_none(self):
        # The control for the unknown case: a present, empty list is a known none.
        self.commit_step(self.CONTROL, note="Waits on #41 to land.")
        self.publish(pulls=[], landed=[])
        out = self.out_with_live()
        self.assertEqual(self.row(out, self.LABEL), (0, ""), "an empty landedPulls list does not read as none:\n%s" % out)

    def test_open_pull_with_a_closed_row_for_its_number_is_not_listed(self):
        self.commit_step(self.CONTROL, note="Waits on #41 to land.")
        self.commit_step("c-open-dup", note="Waits on #42 to land.")
        self.publish(landed=[self.closed(41), self.closed(42)],
                     pulls=[{"number": 42, "title": "lane 42", "branch": "lane-42"}])
        out = self.out_with_live()
        self.assert_control_listed(out)
        self.assertNotIn("c-open-dup (#42)", self.listed(out),
                         "a step that waits on #42, which is open now, is listed as waiting on a closed pull")

    def test_pull_number_with_no_wait_word_is_not_listed(self):
        self.commit_step(self.CONTROL, note="Waits on #41 to land.")
        self.commit_step("c-no-word", note="Same area as #45.")
        self.publish(landed=[self.closed(41), self.closed(45)])
        out = self.out_with_live()
        self.assert_control_listed(out)
        self.assertNotIn("c-no-word (#45)", self.listed(out),
                         "a note that names #45 with no wait word is listed as waiting on the closed #45")

    def test_history_after_a_closed_pull_is_not_a_wait(self):
        self.commit_step(self.CONTROL, note="Waits on #41 to land.")
        self.commit_step("fix-check-chain", note="The fail-record-ancestor-head lane continues here after #46 closed.")
        self.publish(landed=[self.closed(41), self.closed(46)])
        out = self.out_with_live()
        self.assert_control_listed(out)
        self.assertNotIn("fix-check-chain (#46)", self.listed(out),
                         "a note that says a lane continued after #46 closed is listed as a wait on #46")

    def test_history_after_a_merged_pull_is_not_a_wait(self):
        self.commit_step(self.CONTROL, note="Waits on #41 to land.")
        self.commit_step("fix-check-chain", note="The fail-record-ancestor-head lane continues here after #46 merged.")
        self.publish(landed=[self.closed(41), self.closed(46)])
        out = self.out_with_live()
        self.assert_control_listed(out)
        self.assertNotIn("fix-check-chain (#46)", self.listed(out),
                         "a note that says a lane continued after #46 merged is listed as a wait on #46")

    def test_wait_phrases_until_when_and_wait_on_are_listed_bare_and_with_PR(self):
        # The PR form is the one the regex took later; each bare form is the control at every sha that has the row.
        waits = (("until", "Held until #61 lands."), ("until PR", "Held until PR #62 lands."),
                 ("when", "Ships when #63 lands."), ("when PR", "Ships when PR #64 lands."),
                 ("after", "Ships after #65 lands."), ("once", "Runs once #66 lands."),
                 ("wait on", "Wait on #67 to land."), ("wait on PR", "Wait on PR #68 to land."))
        self.commit_step(self.CONTROL, note="Waits on #41 to land.")
        steps = {}
        for n, (phrase, note) in enumerate(waits, start=61):
            sid = "w-" + phrase.replace(" ", "-")
            self.commit_step(sid, note=note)
            steps[phrase] = (sid, n)
        self.publish(landed=[self.closed(41)] + [self.closed(n) for _, n in steps.values()])
        out = self.out_with_live()
        self.assert_control_listed(out)
        for phrase, (sid, n) in steps.items():
            with self.subTest(phrase=phrase):
                self.assertIn("%s (#%d)" % (sid, n), self.listed(out),
                              "the wait phrase %r on the closed unmerged #%d is not listed" % (phrase, n))

    def test_closed_unmerged_pull_whose_head_is_on_main_is_not_listed(self):
        # The lane's work reached main, though GitHub shows its pull closed and unmerged. The control's head is off main.
        self.commit_step("c-landed", note="Waits on #47 to land.")
        self.commit_step("c-off", note="Waits on #48 to land.")
        self.commit_step(self.CONTROL, note="Waits on #41 to land.")
        off = self.off_main()
        self.assertFalse(self.is_ancestor(off, "main"), "scope: the control's head must be off main")
        behind = self.behind_main()
        self.assertTrue(self.is_ancestor(behind, "main"), "scope: the head of #47 must be an ancestor of main")
        self.no_trailer_on_main()
        self.publish(landed=[self.closed(41), self.pull_row(47, "lane-47", head=behind, merged=False),
                             self.pull_row(48, "lane-48", head=off, merged=False)])
        out = self.out_with_live()
        self.assert_control_listed(out)
        self.assertIn("c-off (#48)", self.listed(out), "a closed unmerged #48 whose head is off main is not listed as a wait")
        self.assertNotIn("c-landed (#47)", self.listed(out),
                         "a closed unmerged #47 whose head is on main is listed as a wait, though its work landed")

    def distinct_head(self, number):
        """A root commit of its own, off main. Its message names the pull, so no two heads share a sha."""
        tree = git(self.repo, "rev-parse", "roadmap^{tree}").strip()
        return git(self.repo, "commit-tree", tree, "-m", "closed lane %d" % number).strip()

    def test_closed_row_no_open_step_waits_on_runs_no_merge_base(self):
        # The roadmap skill's upkeep row states the cost: one git merge-base for the closed row an open step waits on,
        # and none for a closed row no step waits on. Each row has its own head, so the per-sha cache cannot merge calls.
        # lane-N matches no step and the file has no pulls row, so pull_landed_marks and the draft-pull check
        # reach head_on_main with nothing to check here.
        self.commit_step(self.CONTROL, note="Waits on #41 to land.")
        heads = {n: self.distinct_head(n) for n in range(41, 48)}
        self.assertEqual(len(set(heads.values())), 7, "scope: the seven heads must be distinct, or the per-sha cache hides the cost")
        self.publish(landed=[self.pull_row(n, "lane-%d" % n, head=heads[n], merged=False) for n in range(41, 48)])
        with mock.patch.object(build, "git", wraps=build.git) as spy:
            out = self.out_with_live()
        self.assert_control_listed(out)
        merge_bases = [c.args for c in spy.call_args_list if c.args[1:2] == ("merge-base",)]
        checked = [a[3] for a in merge_bases if len(a) > 3]
        unwaited = [n for n in range(42, 48) if heads[n] in checked]
        if unwaited:
            self.fail("the closed-pull wait ran git merge-base on the head of closed #%s, which no open step waits on "
                      "(%d merge-base processes in all)" % (", #".join(str(n) for n in unwaited), len(merge_bases)))
        self.assertEqual(len(merge_bases), 1, "the closed-pull wait ran %d git merge-base processes, not one, though one closed "
                         "row is waited on" % len(merge_bases))


class ReadyAndDraftRows(UpkeepFixture):
    """Two upkeep rows (spec part B). `ready todo steps` lists each todo step whose note has the sentence `Ready.`,
    with no live-phase filter. `draft PRs over 12 h with no live lane` lists each draft pull whose updated_at, read
    from GitHub's REST pulls list (every page), is more than 12 h before the build run. A draft is skipped when a live
    session names its step, or when the live file's pulls row for its number has `held` true or `reviewLog` true.
    Those marks and sessions are read only when the live file is fresh. An entry reads `#<number> (<branch or title>)`.
    A REST row with no usable updated_at, or a read that cannot finish, reads the row as one `unknown (...)` entry.
    A live file that is stale or has no sessions list reads one `unknown (sessions not read: ...; REST read: ...)`
    entry. A `held` or `reviewLog` that is not a JSON bool makes the live pull row skipped, which reads the row unknown.
    The cases for the REST read itself are in StaleDraftRestRead."""

    READY = "ready todo steps"
    DRAFT = "draft PRs over 12 h with no live lane"

    def test_replay_lists_the_ready_step_and_the_stale_draft(self):
        # The Nov 1 replay, read from REST: the draft was last updated 12 h 21 m before the build run.
        self.commit_replay_step()
        self.serve_pulls([self.rest_draft(999, self.REPLAY, 741, self.REPLAY_TITLE)])
        self.publish(sessions=[], pulls=[self.live_pull(999, self.REPLAY, self.REPLAY_TITLE)])
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

    def test_draft_updated_eleven_and_a_half_hours_before_now_is_not_listed(self):
        # updated_at is aged from the build run. 11 h 30 m is under 12 h, so late-eleven is not listed.
        # lone-draft is the control: 13 h before now.
        self.serve_pulls([self.rest_draft(1000, "late-eleven", 690), self.rest_draft(1001, "lone-draft", 780)])
        self.publish(sessions=[], pulls=[self.live_pull(1001, "lone-draft")])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual((count, self.entries(detail)), (1, ["#1001 (lone-draft)"]))

    def test_draft_with_a_live_lane_is_not_listed(self):
        # c1 is doing, so the pair line stays quiet. Its live session carries this repo's tag and the step's tag.
        self.commit_step("c1", status="doing")
        self.serve_pulls([self.rest_draft(1001, "c1", 780), self.rest_draft(1002, "lone-draft", 780)])
        self.publish(sessions=[session_row("session_test01", "SESSION_STATUS_RUNNING", self.REPO, "cs-step:c1")],
                     pulls=[self.live_pull(1001, "c1"), self.live_pull(1002, "lone-draft")])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual((count, self.entries(detail)), (1, ["#1002 (lone-draft)"]))

    def test_draft_whose_only_lane_has_ended_is_listed_as_stale(self):
        # c1's only lane is completed, so c1 holds no live lane and its draft is stale. c2's lane is running:
        # its draft stays unlisted. The live pulls list still names both pulls, as the publisher writes it, so
        # the stalled-step row does not read c1 as stalled; the draft row reads REST and ignores them.
        self.commit_step("c1", status="doing")
        self.commit_step("c2", status="doing", order=2)
        self.serve_pulls([self.rest_draft(1001, "c1", 780), self.rest_draft(1002, "c2", 780)])
        self.publish(sessions=[
            session_row("session_done", "SESSION_STATUS_IDLE", self.REPO, "cs-build:lane", "cs-step:c1",
                        status_bucket=BUCKET_COMPLETED),
            session_row("session_run", "SESSION_STATUS_RUNNING", self.REPO, "cs-build:lane", "cs-step:c2",
                        status_bucket=BUCKET_WORKING)],
            pulls=[dict(self.mark(1001), branch="c1"), dict(self.mark(1002), branch="c2")])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual((count, self.entries(detail)), (1, ["#1001 (c1)"]))

    def test_draft_on_a_lane_branch_with_a_live_step_is_not_listed(self):
        # The head ref lane/c1 is the lane of step c1, as c1 is. lone-draft is the control: no live step.
        self.commit_step("c1", status="doing")
        self.serve_pulls([self.rest_draft(1001, "lane/c1", 780), self.rest_draft(1002, "lone-draft", 780)])
        self.publish(sessions=[session_row("session_test01", "SESSION_STATUS_RUNNING", self.REPO, "cs-step:c1")],
                     pulls=[self.live_pull(1001, "lane/c1"), self.live_pull(1002, "lone-draft")])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual((count, self.entries(detail)), (1, ["#1002 (lone-draft)"]))

    def test_draft_whose_title_holds_a_live_step_id_is_still_listed(self):
        # Only the draft's branch can lane it. The title "Follow-up for c91" holds the live step c91 and stays listed.
        # c91 is the control: its branch is the step, so it is laned.
        self.serve_pulls([self.rest_draft(1001, "c91-cleanup", 780, title="Follow-up for c91"),
                          self.rest_draft(1002, "c91", 780)])
        self.publish(sessions=[session_row("session_test01", "SESSION_STATUS_RUNNING", self.REPO, "cs-step:c91")],
                     pulls=[self.live_pull(1001, "c91-cleanup", "Follow-up for c91"), self.live_pull(1002, "c91")])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual((count, self.entries(detail)), (1, ["#1001 (c91-cleanup)"]))

    def test_empty_step_tag_names_no_draft(self):
        # An empty step id names nothing, so the title "a: b" does not lane this draft.
        self.serve_pulls([self.rest_draft(1001, "lone-draft", 780, title="a: b")])
        self.publish(sessions=[session_row("session_test01", "SESSION_STATUS_RUNNING", self.REPO, "cs-step:")],
                     pulls=[self.live_pull(1001, "lone-draft", "a: b")])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual((count, self.entries(detail)), (1, ["#1001 (lone-draft)"]))

    def test_draft_without_a_usable_updated_at_reads_the_row_unknown(self):
        # A REST row with no usable updated_at is never a partial list: the row reads one unknown entry, and the
        # control lone-draft is not listed beside it.
        bad = {"missing": _ABSENT, "no zone": "2026-11-02T01:14:22", "not a time": "yesterday"}
        for name, updated in bad.items():
            with self.subTest(name):
                row = self.rest_draft(998, "no-date", 780)
                if updated is _ABSENT:
                    del row["updated_at"]
                else:
                    row["updated_at"] = updated
                self.serve_pulls([row, self.rest_draft(1000, "lone-draft", 780)])
                self.publish(sessions=[])
                count, detail = self.row(self.out_with_live(), self.DRAFT)
                self.assertEqual(count, 1, "the row was %r" % (detail,))
                self.assertTrue(detail.startswith("unknown (") and "updated" in detail, detail)
                self.assertNotIn("(lone-draft)", detail)

    def test_draft_with_a_posted_review_log_is_not_listed(self):
        # The #2818 shape: lane lane-ruleset-read, not the step id, and no live session names merge-reads-ruleset.
        # reviewLog true on the live row for number 1001 is the only mark. lone-draft is the control.
        self.commit_step("merge-reads-ruleset", status="doing")
        self.serve_pulls([self.rest_draft(1001, "lane-ruleset-read", 780), self.rest_draft(1002, "lone-draft", 780)])
        self.publish(sessions=[], pulls=[self.mark(1001, reviewLog=True), self.live_pull(1002, "lone-draft")])
        count, detail = self.row(self.out_with_live(expect=(0, 1)), self.DRAFT)
        self.assertEqual((count, self.entries(detail)), (1, ["#1002 (lone-draft)"]),
                         "a draft whose review log is posted is not listed")

    def test_draft_the_runner_holds_is_not_listed_without_a_review_log(self):
        # The same shape as the #2818 case, with held true on the live row for number 1001 and no review log.
        self.commit_step("merge-reads-ruleset", status="doing")
        self.serve_pulls([self.rest_draft(1001, "lane-ruleset-read", 780), self.rest_draft(1002, "lone-draft", 780)])
        self.publish(sessions=[], pulls=[self.mark(1001, held=True), self.live_pull(1002, "lone-draft")])
        count, detail = self.row(self.out_with_live(expect=(0, 1)), self.DRAFT)
        self.assertEqual((count, self.entries(detail)), (1, ["#1002 (lone-draft)"]),
                         "a draft the runner's list names (held true) is not listed")

    def test_orphan_draft_reads_unknown_and_false_flags_are_still_listed(self):
        # #1001 has no live pulls row, so its held and reviewLog marks are unread: the row reads it unknown, not listed.
        # held false and reviewLog false name nothing, so #1002 and #1003 are listed. Three entries: one unknown, two listed.
        self.serve_pulls([self.rest_draft(1001, "orphan-draft", 780), self.rest_draft(1002, "held-false", 780),
                          self.rest_draft(1003, "review-false", 780)])
        self.publish(sessions=[], pulls=[self.mark(1002, held=False), self.mark(1003, reviewLog=False)])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual(count, 3, "the row was %r" % (detail,))
        self.assertRegex(detail, r"unknown \([^)]*#1001", "the draft with no live row is not read unknown")
        self.assertIn("#1002 (held-false)", detail)
        self.assertIn("#1003 (review-false)", detail)

    def test_non_bool_held_or_review_log_skips_the_pull_row(self):
        # A JSON string or number is a wrong shape. The live pulls row is skipped, so the live file reads unknown,
        # and the row reads one unknown entry that names the skipped row and the REST drafts it read.
        for key in ("held", "reviewLog"):
            for value in ("yes", 1):
                with self.subTest(key=key, value=value):
                    self.serve_pulls([self.rest_draft(1001, "lone-draft", 780),
                                      self.rest_draft(1002, "other-draft", 780)])
                    self.publish(sessions=[], pulls=[dict(self.mark(1001), **{key: value})])
                    count, detail = self.row(self.out_with_live(), self.DRAFT)
                    self.assertEqual(count, 1, "a %s that is not a JSON bool reads the row as one entry" % key)
                    self.assertTrue(detail.startswith("unknown (sessions not read: "), detail)
                    self.assertIn("1 pull rows skipped", detail)
                    self.assertRegex(detail, r"REST read: 2 stale-looking drafts?\b")
                    self.assertNotIn("#1001", detail, "an unusable live file named a draft's number")

    def test_held_draft_with_no_updated_at_still_reads_the_row_unknown(self):
        # held does not exempt a REST row from the shape check: the row reads one unknown entry, and the control
        # lone-draft is not listed beside it.
        held = self.rest_draft(998, "held-no-date", 780)
        del held["updated_at"]
        self.serve_pulls([held, self.rest_draft(1000, "lone-draft", 780)])
        self.publish(sessions=[], pulls=[self.mark(998, held=True)])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual(count, 1, "the row was %r" % (detail,))
        self.assertTrue(detail.startswith("unknown ("), detail)
        self.assertNotIn("(lone-draft)", detail)

    def test_no_live_file_reads_the_draft_row_unknown_and_still_reads_rest(self):
        # With no --live file the sessions are unknown, but the REST read still runs and its stale draft is named.
        self.serve_pulls([self.rest_draft(1001, "lone-draft", 780)])
        _, out = self.build_from_main()
        count, detail = self.row(out, self.DRAFT)
        self.assertEqual(count, 1, "the row was %r" % (detail,))
        self.assertTrue(detail.startswith("unknown (sessions not read: ") and "--live" in detail, detail)
        self.assertRegex(detail, r"REST read: 1 stale-looking drafts?\b")
        self.assertNotIn("#1001", detail, "an unusable live file named a draft's number")


class StaleDraftRestRead(UpkeepFixture):
    """The draft row reads GitHub's REST pulls list itself, not the live file's pulls (design `stale-drafts-read-rest`).
    Pages are 100 rows, read in order until a page is short, and the read stops at 20 pages. A stale draft's updated_at
    is over 12 h before the build run. A read that cannot finish reads the row as one `unknown (<why>)` entry, never a
    partial list and never a clear row: no token, an HTTP or rate-limit error, a body that is not a list or not JSON, a
    row of the wrong shape, a read past the 20-page cap, a page that fails midway, or a rate-limit count of 0 before the
    last page. The live file still gives the sessions and the held and reviewLog marks. Those are read only when the
    live file is fresh; otherwise the row is one `unknown (sessions not read: ...; REST read: ...)` entry.

    Each stale draft's newest branch commit is read too, one git log per stale draft. A commit under 12 h old lists
    nothing, so the commit can only suppress a listing. A branch whose commit cannot be read (no ref, a ref on no
    commit, a git failure, a time that does not parse) reads `unknown (#N branch X has no commit time)`, never a listing."""

    DRAFT = ReadyAndDraftRows.DRAFT

    def stale_first_page(self):
        """A full page 1 (100 rows): stale #1001, then 99 fresh drafts."""
        return [self.rest_draft(1001, "old-1001", 780)] + self.fresh_rows(1002, 99)

    def test_each_page_asks_the_open_pulls_list_of_this_repo_at_one_hundred_a_page(self):
        self.serve_pulls(self.stale_first_page(), [self.rest_draft(2001, "old-2001", 780)])
        self.publish(sessions=[])
        self.out_with_live()
        self.assertEqual(len(self.rest_get.call_args_list), 2, "the read did not make one call per page")
        for call in self.rest_get.call_args_list:
            parts = urllib.parse.urlparse(request_url(call))
            query = urllib.parse.parse_qs(parts.query)
            self.assertEqual(parts.netloc, "api.github.com")
            self.assertEqual(parts.path, "/repos/owner/fixture/pulls")
            self.assertEqual((query["state"], query["per_page"]), (["open"], ["100"]))

    def test_pages_of_one_hundred_then_fewer_are_both_read(self):
        self.serve_pulls(self.stale_first_page(), [self.rest_draft(2001, "old-2001", 780)] + self.fresh_rows(2002, 1))
        self.publish(sessions=[], pulls=[self.live_pull(1001, "old-1001"), self.live_pull(2001, "old-2001")])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual(self.requested_pages(), [1, 2], "a full page 1 did not lead to a read of page 2")
        self.assertEqual((count, self.entries(detail)), (2, ["#1001 (old-1001)", "#2001 (old-2001)"]))

    def test_exactly_one_hundred_rows_reads_an_empty_second_page(self):
        self.serve_pulls(self.stale_first_page(), [])
        self.publish(sessions=[], pulls=[self.live_pull(1001, "old-1001")])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual(self.requested_pages(), [1, 2], "a full page 1 did not lead to a read of page 2")
        self.assertEqual((count, self.entries(detail)), (1, ["#1001 (old-1001)"]))

    def test_two_hundred_fifty_rows_are_all_read(self):
        # More than the live file's 200 rows: the stale drafts on page 1 and on page 3 are both listed.
        self.serve_pulls(self.stale_first_page(), self.fresh_rows(1101, 100),
                         [self.rest_draft(3001, "old-3001", 780)] + self.fresh_rows(3002, 49))
        self.publish(sessions=[], pulls=[self.live_pull(1001, "old-1001"), self.live_pull(3001, "old-3001")])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual(self.requested_pages(), [1, 2, 3])
        self.assertEqual((count, self.entries(detail)), (2, ["#1001 (old-1001)", "#3001 (old-3001)"]))

    def test_twenty_full_pages_then_a_short_one_is_the_last_page_read(self):
        # The cap is 20 pages. Page 20 is read, and it is short, so the read ends there and lists its draft.
        pages = [self.fresh_rows(100 * i + 1, 100) for i in range(19)]
        pages.append([self.rest_draft(2000, "old-2000", 780)] + self.fresh_rows(2001, 4))
        self.serve_pulls(*pages)
        self.publish(sessions=[], pulls=[self.live_pull(2000, "old-2000")])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual(self.requested_pages(), list(range(1, 21)))
        self.assertEqual((count, self.entries(detail)), (1, ["#2000 (old-2000)"]))

    def test_past_twenty_pages_reads_one_unknown_entry_and_asks_for_no_page_twenty_one(self):
        pages = [self.stale_first_page()] + [self.fresh_rows(10000 + 100 * i, 100) for i in range(1, 20)]
        self.serve_pulls(*pages)
        self.publish(sessions=[])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertLessEqual(max(self.requested_pages() or [0]), 20, "the read asked for a page past the 20-page cap")
        self.assertEqual(count, 1, "the row was %r" % (detail,))
        self.assertTrue(detail.startswith("unknown ("), detail)
        self.assertNotIn("#1001", detail, "a read past the cap listed part of the drafts")

    def test_a_page_that_fails_midway_reads_one_unknown_entry_not_a_partial_list(self):
        self.serve_pulls(self.stale_first_page(), http_error(500))
        self.publish(sessions=[])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual(count, 1, "the row was %r" % (detail,))
        self.assertTrue(detail.startswith("unknown ("), detail)
        self.assertNotIn("#1001", detail, "page 1's stale draft was listed beside a failed page 2")

    def test_forbidden_and_rate_limited_replies_read_one_unknown_entry_naming_the_rate_limit(self):
        replies = {"403 with the count at zero": http_error(403, {"X-RateLimit-Remaining": "0"}),
                   "429 with a retry delay": http_error(429, {"Retry-After": "60"})}
        for name, reply in replies.items():
            with self.subTest(name):
                self.serve_pulls(self.stale_first_page(), reply)
                self.publish(sessions=[])
                count, detail = self.row(self.out_with_live(), self.DRAFT)
                self.assertEqual(count, 1, "the row was %r" % (detail,))
                self.assertTrue(detail.startswith("unknown ("), detail)
                self.assertIn("rate limit", detail.lower(), "the reason does not name the rate limit")
                self.assertNotIn("#1001", detail)

    def test_rate_limit_at_zero_before_the_last_page_reads_one_unknown_entry(self):
        # Page 1 is full and says the count is at 0, so the read must stop there. Page 2 would list #2001 if read.
        self.serve_pulls((self.stale_first_page(), headers_of({"X-RateLimit-Remaining": "0"})),
                         [self.rest_draft(2001, "old-2001", 780)])
        self.publish(sessions=[])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual(count, 1, "the row was %r" % (detail,))
        self.assertTrue(detail.startswith("unknown ("), detail)
        self.assertNotIn("#1001", detail, "page 1's stale draft was listed with the count at 0")
        self.assertNotIn("#2001", detail, "a page after the count reached 0 was listed")

    def test_rate_limit_at_zero_on_the_last_page_reads_clear(self):
        # The count is 0 on page 2, which is short, so page 2 is the last page and the read is whole.
        self.serve_pulls((self.stale_first_page(), headers_of({"X-RateLimit-Remaining": "5"})),
                         ([self.rest_draft(2001, "old-2001", 780)], headers_of({"X-RateLimit-Remaining": "0"})))
        self.publish(sessions=[], pulls=[self.live_pull(1001, "old-1001"), self.live_pull(2001, "old-2001")])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual(self.requested_pages(), [1, 2])
        self.assertEqual((count, self.entries(detail)), (2, ["#1001 (old-1001)", "#2001 (old-2001)"]))

    def test_a_draft_is_aged_by_updated_at_not_created_at(self):
        self.serve_pulls([self.rest_draft(1001, "created-long-ago", 60, created_min=20 * 60),
                          self.rest_draft(1002, "updated-long-ago", 780, created_min=60)])
        self.publish(sessions=[], pulls=[self.live_pull(1002, "updated-long-ago")])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual((count, self.entries(detail)), (1, ["#1002 (updated-long-ago)"]))

    def test_a_draft_is_aged_from_the_build_run_not_from_the_live_read(self):
        # The live file was read 45 min ago. 12 h 15 m before now is 11 h 30 m before that read, so an age taken from
        # the read would not list it. young-draft, 11 h 30 m before now, is not listed.
        self.serve_pulls([self.rest_draft(1001, "aged-from-now", 735), self.rest_draft(1002, "young-draft", 690)])
        self.publish(read_at=iso_ago(45), sessions=[], pulls=[self.live_pull(1001, "aged-from-now")])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual((count, self.entries(detail)), (1, ["#1001 (aged-from-now)"]))

    def test_a_pull_that_is_not_a_draft_is_not_listed(self):
        self.serve_pulls([self.rest_draft(1001, "open-not-draft", 780, draft=False),
                          self.rest_draft(1002, "draft-stale", 780)])
        self.publish(sessions=[], pulls=[self.live_pull(1002, "draft-stale")])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual((count, self.entries(detail)), (1, ["#1002 (draft-stale)"]))

    def test_the_row_reads_rest_not_the_live_pulls_list(self):
        # The live pulls list holds a stale draft, #1001, that REST does not return: the row does not list it. REST's
        # #1002 has no live pulls row, so its held and reviewLog marks are unread and the row reads it unknown.
        live = dict(self.mark(1001), draft=True, createdAt=iso_ago(780), branch="live-only")
        self.serve_pulls([self.rest_draft(1002, "rest-draft", 780)])
        self.publish(sessions=[], pulls=[live])
        count, detail = self.row_or_named_crash()
        self.assertEqual(count, 1, "the row was %r" % (detail,))
        self.assertTrue(detail.startswith("unknown ("), detail)
        self.assertIn("#1002", detail)
        self.assertNotIn("live-only", detail, "the live pulls list fed the row")

    def test_a_fresh_live_file_and_a_clean_rest_read_reads_no_entry(self):
        # The control: a whole read with no stale draft reads the row clear, with no line at all.
        self.serve_pulls([self.rest_draft(1001, "fresh-draft", 60)])
        self.publish(sessions=[])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual((count, detail), (0, ""))

    def test_a_row_of_the_wrong_shape_reads_one_unknown_entry_not_a_partial_list(self):
        wrong = {
            "number is text": {"number": "1002"},
            "draft is text": {"draft": "true"},
            "draft is null": {"draft": None},
            "head.ref is not text": {"head": {"ref": 5}},
            "head is missing": {"head": _ABSENT},
            "updated_at is not a time": {"updated_at": "yesterday"},
            "updated_at has no zone": {"updated_at": "2026-11-02T01:14:22"},
            "updated_at is null": {"updated_at": None},
        }
        for name, change in wrong.items():
            with self.subTest(name):
                row = self.rest_draft(1002, "bad-row", 780)
                for key, value in change.items():
                    if value is _ABSENT:
                        del row[key]
                    else:
                        row[key] = value
                self.serve_pulls([self.rest_draft(1001, "old-1001", 780), row])
                self.publish(sessions=[])
                count, detail = self.row(self.out_with_live(), self.DRAFT)
                self.assertEqual(count, 1, "the row did not read one entry")
                self.assertTrue(detail.startswith("unknown ("), detail)
                self.assertNotIn("#1001", detail)

    def test_a_body_that_is_not_a_list_or_not_json_reads_one_unknown_entry(self):
        replies = {"an object, not a list": ({"message": "Not Found"}, headers_of()),
                   "not JSON": ValueError("Expecting value: line 1 column 1 (char 0)")}
        for name, reply in replies.items():
            with self.subTest(name):
                self.serve_pulls(reply)
                self.publish(sessions=[])
                count, detail = self.row(self.out_with_live(), self.DRAFT)
                self.assertEqual(count, 1, "the row was %r" % (detail,))
                self.assertTrue(detail.startswith("unknown ("), detail)

    def test_no_token_reads_one_unknown_entry_that_names_the_token(self):
        self.serve_pulls([self.rest_draft(1001, "old-1001", 780)], token=None)
        self.publish(sessions=[])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual(count, 1, "the row was %r" % (detail,))
        self.assertTrue(detail.startswith("unknown (") and "token" in detail.lower(), detail)
        self.assertNotIn("#1001", detail)

    def test_the_token_is_gh_token_else_github_token(self):
        cases = {"GITHUB_TOKEN only": ({"GITHUB_TOKEN": "from-github"}, "from-github"),
                 "both set": ({"GH_TOKEN": "first", "GITHUB_TOKEN": "second"}, "first")}
        for name, (env, want) in cases.items():
            with self.subTest(name):
                for key in ("GH_TOKEN", "GITHUB_TOKEN"):
                    os.environ.pop(key, None)
                os.environ.update(env)
                self.rest_get.reset_mock()
                self.serve_pulls([self.rest_draft(1001, "old-1001", 780)], token=None)
                self.publish(sessions=[])
                self.out_with_live()
                tokens = {request_token(c) for c in self.rest_get.call_args_list}
                self.assertEqual(tokens, {want}, "the read did not send the token that the design names")

    def test_one_build_reads_one_call_per_hundred_open_pulls_plus_one(self):
        # The cost the design states: floor(N / 100) + 1 calls for N open pulls, since a full page is followed by the
        # page that ends the read. N = 0 reads one empty page. N = 100 reads a full page, then an empty one.
        for total in (0, 99, 100, 250):
            with self.subTest(open_pulls=total):
                rows = [self.rest_draft(n, "fresh-%d" % n, 60) for n in range(1, total + 1)]
                self.rest_get.reset_mock()
                self.serve_pulls(*[rows[i:i + 100] for i in range(0, total, 100)])
                self.publish(sessions=[])
                self.out_with_live()
                self.assertEqual(len(self.rest_get.call_args_list), total // 100 + 1)

    def test_a_stale_live_file_reads_one_unknown_entry_that_names_the_rest_read(self):
        self.serve_pulls(self.stale_first_page())
        self.publish(read_at=iso_ago(90), sessions=[])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual(count, 1, "the row was %r" % (detail,))
        self.assertTrue(detail.startswith("unknown (sessions not read: "), detail)
        self.assertIn("the live file was read", detail)
        self.assertRegex(detail, r"REST read: 1 stale-looking drafts?\b")
        self.assertNotIn("#1001", detail, "an unusable live file named a draft's number")

    def test_a_stale_live_file_with_no_stale_drafts_still_reads_one_unknown_entry(self):
        # Never an empty row: a clean REST read under a stale live file is unknown, not clear.
        self.serve_pulls(self.fresh_rows(1001, 2))
        self.publish(read_at=iso_ago(90), sessions=[])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual(count, 1, "a stale live file read the row clear")
        self.assertTrue(detail.startswith("unknown (sessions not read: "), detail)
        self.assertRegex(detail, r"REST read: 0 stale-looking")

    def test_a_live_file_with_no_sessions_list_reads_one_unknown_entry(self):
        self.serve_pulls([self.rest_draft(1001, "old-1001", 780)])
        self.publish()
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual(count, 1, "the row was %r" % (detail,))
        self.assertTrue(detail.startswith("unknown (sessions not read: ") and "no sessions list" in detail, detail)
        self.assertRegex(detail, r"REST read: 1 stale-looking drafts?\b")
        self.assertNotIn("#1001", detail, "an unusable live file named a draft's number")

    def test_a_mark_is_matched_to_its_draft_by_number_not_by_branch(self):
        # The live row for #1005 names the same branch as stale draft #1001, and it is held. #1001 is still listed.
        self.serve_pulls([self.rest_draft(1001, "shared-branch", 780)])
        self.publish(sessions=[], pulls=[dict(self.mark(1005), branch="shared-branch", held=True),
                                         self.live_pull(1001, "shared-branch")])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual((count, self.entries(detail)), (1, ["#1001 (shared-branch)"]))

    def row_or_named_crash(self, live=True):
        """The DRAFT row's (count, detail) from one build. A build that raises fails the case with a named cause."""
        try:
            if live:
                out = self.out_with_live()
            else:
                _, out = self.build_from_main()
        except Exception as err:
            self.fail("the build raised %s instead of reading the row as one unknown entry" % type(err).__name__)
        return self.row(out, self.DRAFT)

    def test_a_transport_error_mid_read_reads_one_unknown_entry_and_does_not_crash(self):
        # http.client raises these from inside the read, past HTTPError and OSError. Each ends as one unknown entry,
        # never a raised exception and never a partial list: page 1's stale #1001 is not listed.
        failures = {"IncompleteRead": http.client.IncompleteRead(b"partial body"),
                    "BadStatusLine": http.client.BadStatusLine("garbage"),
                    "HTTPException": http.client.HTTPException("transport failed")}
        for name, failure in failures.items():
            with self.subTest(name):
                self.serve_pulls(self.stale_first_page(), failure)
                self.publish(sessions=[])
                count, detail = self.row_or_named_crash()
                self.assertEqual(count, 1, "the row was %r" % (detail,))
                self.assertTrue(detail.startswith("unknown ("), detail)
                self.assertNotIn("#1001", detail)

    def test_a_stale_draft_with_no_live_pulls_row_reads_unknown_and_is_not_listed(self):
        # The live file is fresh but has no pulls row for #1001, so its held and reviewLog marks are unread. The draft
        # is not listed: the row reads one unknown entry.
        self.serve_pulls([self.rest_draft(1001, "old-1001", 780)])
        self.publish(sessions=[], pulls=[])
        count, detail = self.row_or_named_crash()
        self.assertEqual(count, 1, "the row was %r" % (detail,))
        self.assertTrue(detail.startswith("unknown ("), detail)
        self.assertIn("#1001", detail)

    def test_an_unusable_live_file_names_a_count_of_stale_drafts_not_their_numbers(self):
        # The sessions are unknown, so the unknown entry counts the stale-looking REST drafts and names none of them:
        # no number and no branch. fresh-1003 is not stale and is not counted.
        self.serve_pulls([self.rest_draft(1001, "old-1001", 780), self.rest_draft(1002, "old-1002", 780),
                          self.rest_draft(1003, "fresh-1003", 60)])
        for name, stale_live in (("live file read 90 minutes ago", True), ("no live file", False)):
            with self.subTest(name):
                if stale_live:
                    self.publish(read_at=iso_ago(90), sessions=[])
                count, detail = self.row_or_named_crash(live=stale_live)
                self.assertEqual(count, 1, "the row was %r" % (detail,))
                self.assertRegex(detail, r"REST read: 2 stale-looking drafts?\b", detail)
                for named in ("#1001", "#1002", "old-1001", "old-1002"):
                    self.assertNotIn(named, detail, "the unusable read named a draft: %s" % named)

    def commit_time(self, branch):
        """The newest commit time of the fixture's refs/remotes/origin/<branch>, as an aware datetime (git's own read)."""
        return datetime.datetime.fromisoformat(git(self.repo, "log", "-1", "--format=%cI", "refs/remotes/origin/" + branch).strip())

    @staticmethod
    def iso_time(text):
        """An ISO time with its zone, as an aware datetime: the form iso_ago and zoned_ago write."""
        return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))

    def zoned_ago(self, minutes):
        """An ISO time `minutes` before now, written in the -06:00 zone rather than UTC."""
        zone = datetime.timezone(datetime.timedelta(hours=-6))
        return (datetime.datetime.now(zone) - datetime.timedelta(minutes=minutes)).isoformat(timespec="seconds")

    def unknown_no_commit(self, number, branch):
        return "unknown (#%d branch %s has no commit time)" % (number, branch)

    def test_a_stale_draft_whose_branch_has_a_commit_under_twelve_hours_old_is_not_listed(self):
        when = iso_ago(60)
        self.origin_commit("pushed-today", when)
        self.serve_pulls([self.rest_draft(1001, "pushed-today", 780)])
        self.publish(sessions=[], pulls=[self.live_pull(1001, "pushed-today")])
        self.assertEqual(self.commit_time("pushed-today"), self.iso_time(when),
                         "the fixture's branch commit is not the 1 h old commit the case set")
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual((count, detail), (0, ""), "a commit 1 h old did not suppress the stale draft: %r" % (detail,))

    def test_the_twelve_hour_line_for_the_branch_commit_holds_in_any_zone(self):
        cases = {"11 h 30 m old, in the -06:00 zone": (self.zoned_ago(690), []),
                 "12 h 30 m old, in UTC": (iso_ago(750), ["#1001 (aged-commit)"])}
        for name, (when, listed) in cases.items():
            with self.subTest(name):
                self.origin_commit("aged-commit", when)
                self.serve_pulls([self.rest_draft(1001, "aged-commit", 780)])
                self.publish(sessions=[], pulls=[self.live_pull(1001, "aged-commit")])
                self.assertEqual(self.commit_time("aged-commit"), self.iso_time(when),
                                 "the fixture's branch commit is not the one the case set")
                count, detail = self.row(self.out_with_live(), self.DRAFT)
                self.assertEqual((count, self.entries(detail)), (len(listed), listed),
                                 "a branch commit %s was not read against 12 h" % name)

    def test_a_recent_commit_suppresses_an_old_one_lists_and_a_fresh_draft_is_never_added(self):
        self.origin_commit("fresh-draft-old-commit", iso_ago(780))
        self.origin_commit("stale-old-commit", iso_ago(780))
        self.origin_commit("stale-recent-commit", iso_ago(60))
        self.serve_pulls([self.rest_draft(1001, "fresh-draft-old-commit", 60),
                          self.rest_draft(1002, "stale-old-commit", 780),
                          self.rest_draft(1003, "stale-recent-commit", 780)])
        self.publish(sessions=[], pulls=[self.live_pull(1002, "stale-old-commit"),
                                         self.live_pull(1003, "stale-recent-commit")])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual((count, self.entries(detail)), (1, ["#1002 (stale-old-commit)"]),
                         "a recent branch commit did not suppress #1003, or a fresh draft was listed")

    def test_a_stale_draft_whose_branch_has_no_ref_reads_one_unknown_entry(self):
        self.drop_origin("no-ref")
        self.serve_pulls([self.rest_draft(1001, "no-ref", 780)])
        self.publish(sessions=[], pulls=[self.live_pull(1001, "no-ref")])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual((count, detail), (1, self.unknown_no_commit(1001, "no-ref")),
                         "a draft whose branch has no ref was not read as one unknown entry")

    def test_a_branch_ref_on_a_tree_holds_no_commit_and_reads_the_same_unknown_entry(self):
        self.set_origin("tree-ref", self.EMPTY_TREE)
        self.serve_pulls([self.rest_draft(1001, "tree-ref", 780)])
        self.publish(sessions=[], pulls=[self.live_pull(1001, "tree-ref")])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual((count, detail), (1, self.unknown_no_commit(1001, "tree-ref")),
                         "a branch ref that holds no commit was not read as one unknown entry")

    def test_a_branch_ref_git_cannot_read_reads_the_same_unknown_entry(self):
        self.break_origin("broken-ref")
        self.serve_pulls([self.rest_draft(1001, "broken-ref", 780)])
        self.publish(sessions=[], pulls=[self.live_pull(1001, "broken-ref")])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual((count, detail), (1, self.unknown_no_commit(1001, "broken-ref")),
                         "a branch ref git cannot read was not read as one unknown entry")

    def test_a_commit_time_that_does_not_parse_reads_the_same_unknown_entry(self):
        # Git's %cI is always ISO, so a real repo cannot show this. The one git read's reply is swapped for text that is
        # not a time. The read goes through build.git, the one home of git reads.
        self.serve_pulls([self.rest_draft(1001, "garbled-time", 780)])
        self.publish(sessions=[], pulls=[self.live_pull(1001, "garbled-time")])
        real_git = build.git

        def garbled(repo, *args, stdin=None):
            if args[:1] == ("log",) and "refs/remotes/origin/garbled-time" in args:
                return "not a time\n"
            return real_git(repo, *args, stdin=stdin)

        with mock.patch.object(build, "git", garbled):
            count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual((count, detail), (1, self.unknown_no_commit(1001, "garbled-time")),
                         "a commit time that does not parse was not read as one unknown entry")

    def test_an_unknown_draft_and_a_listed_one_both_show_in_the_row(self):
        self.drop_origin("no-ref-beside")
        self.serve_pulls([self.rest_draft(1001, "no-ref-beside", 780), self.rest_draft(1002, "old-beside", 780)])
        self.publish(sessions=[], pulls=[self.live_pull(1001, "no-ref-beside"), self.live_pull(1002, "old-beside")])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        expected = sorted(["#1002 (old-beside)", self.unknown_no_commit(1001, "no-ref-beside")])
        self.assertEqual((count, self.entries(detail)), (2, expected),
                         "the unknown entry and the listed draft were not both in the row")

    def test_each_stale_draft_gets_one_branch_commit_read_and_a_fresh_draft_gets_none(self):
        trace = pathlib.Path(self.tmp.name) / "git-trace.txt"
        self.serve_pulls([self.rest_draft(1001, "cost-a", 780), self.rest_draft(1002, "cost-b", 780),
                          self.rest_draft(1003, "cost-fresh", 60)])
        self.publish(sessions=[], pulls=[self.live_pull(1001, "cost-a"), self.live_pull(1002, "cost-b")])
        with mock.patch.dict(os.environ, {"GIT_TRACE": str(trace)}):
            count, detail = self.row(self.out_with_live(), self.DRAFT)
        reads = {}
        for line in (trace.read_text(encoding="utf-8") if trace.exists() else "").splitlines():
            found = re.search(r" log .*refs/remotes/origin/(\S+)", line)
            if found:
                reads[found.group(1)] = reads.get(found.group(1), 0) + 1
        self.assertEqual(reads, {"cost-a": 1, "cost-b": 1},
                         "the build did not read one branch commit per stale draft, or read a fresh draft's commit")
        self.assertEqual((count, self.entries(detail)), (2, ["#1001 (cost-a)", "#1002 (cost-b)"]))
        self.assertEqual(len(self.rest_get.call_args_list), 1, "the branch commit read made a REST call")

    def test_a_stale_draft_whose_branch_commit_is_after_the_build_reads_one_unknown_entry(self):
        # A commit an hour after the build is no proof of recency, so it reads the draft unknown, never fresh and silent.
        self.origin_commit("future-branch", iso_ago(-60))
        self.serve_pulls([self.rest_draft(1001, "future-branch", 780)])
        self.publish(sessions=[], pulls=[self.live_pull(1001, "future-branch")])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual(count, 1, "a commit after the build read the stale draft as no entry at all: %r" % (detail,))
        self.assertTrue(detail.startswith("unknown (#1001"), "the entry is not an unknown for #1001: %r" % (detail,))
        self.assertIn("future-branch", detail, "the unknown entry does not name the branch")
        self.assertNotIn("#1001 (future-branch)", detail, "a commit after the build listed the draft as stale")

    def test_a_fork_pull_whose_head_branch_shares_an_origin_name_reads_unknown_not_the_origin_commit(self):
        # Pull 1001 is a fork's pull whose head ref is `main`, and origin's own main has a commit an hour old. The fork
        # reads unknown, so the origin commit cannot suppress it. #1002 is this repo's own stale branch, still listed.
        self.origin_commit("main", iso_ago(60))
        self.origin_commit("feature", iso_ago(780))
        self.serve_pulls([self.rest_draft(1001, "main", 780, head_repo="someone/fixture"),
                          self.rest_draft(1002, "feature", 780)])
        self.publish(sessions=[], pulls=[self.live_pull(1001, "main"), self.live_pull(1002, "feature")])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        entries = self.entries(detail)
        self.assertEqual(count, 2, "the fork pull was silent: the origin commit suppressed it (%r)" % (detail,))
        self.assertIn("#1002 (feature)", entries, "this repo's own stale draft was not listed")
        unknown = [entry for entry in entries if entry.startswith("unknown (#1001")]
        self.assertEqual(len(unknown), 1, "the fork pull did not read as one unknown entry: %r" % (entries,))
        self.assertNotIn("#1001 (main)", entries, "the fork pull was listed on the origin commit's name")

    def test_a_fork_pull_reads_unknown_even_when_its_branch_commit_is_old(self):
        self.origin_commit("topic", iso_ago(780))
        self.serve_pulls([self.rest_draft(1001, "topic", 780, head_repo="someone/fixture")])
        self.publish(sessions=[], pulls=[self.live_pull(1001, "topic")])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual(count, 1, "the fork pull did not read as one entry: %r" % (detail,))
        self.assertTrue(detail.startswith("unknown (#1001"), "a fork pull with an old commit was not read unknown: %r" % (detail,))
        self.assertNotIn("#1001 (topic)", detail, "a fork pull was listed on its branch commit")

    def test_a_pull_whose_head_repo_is_gone_reads_unknown(self):
        # head.repo is null when the fork was deleted: the head is not this repo, so the commit read does not apply.
        self.origin_commit("gone", iso_ago(780))
        self.serve_pulls([self.rest_draft(1001, "gone", 780, head_repo=None)])
        self.publish(sessions=[], pulls=[self.live_pull(1001, "gone")])
        count, detail = self.row(self.out_with_live(), self.DRAFT)
        self.assertEqual(count, 1, "a pull with a null head repo did not read as one entry: %r" % (detail,))
        self.assertTrue(detail.startswith("unknown (#1001"), "a pull with a null head repo was not read unknown: %r" % (detail,))
        self.assertNotIn("#1001 (gone)", detail, "a pull with a null head repo was listed on its branch commit")


class StaleDraftTable(UpkeepFixture):
    """The two helpers the stale-draft row reads, pinned on their own: build.branch_commit_times (the commit read, one
    `git log -1` per branch) and build.draft_table (one row per draft pull: number, branch, lane, commit, verdict). A case
    passes an explicit `now` and reads no clock, and the origin refs come from the UpkeepFixture helpers."""

    NOW = datetime.datetime(2026, 11, 16, 12, 0, tzinfo=datetime.timezone.utc)

    def ago(self, hours):
        return self.NOW - datetime.timedelta(hours=hours)

    def iso(self, hours):
        """The ago() time as the Z-suffixed ISO text a commit is dated with."""
        return self.ago(hours).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def utc(text):
        return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))

    def pull(self, number, branch, updated_h=13, draft=True):
        """A draft pull row as open_pulls_rest returns it: updated_at is an aware datetime `updated_h` hours before NOW."""
        return {"number": number, "title": "lane " + branch, "branch": branch, "draft": draft, "updated_at": self.ago(updated_h)}

    def test_branch_commit_times_gives_each_branch_its_commit_as_an_aware_time(self):
        self.origin_commit("utc-branch", "2026-11-01T10:00:00Z")
        self.origin_commit("central-branch", "2026-11-02T10:00:00-06:00")
        times, why = build.branch_commit_times(self.repo, ["utc-branch", "central-branch"])
        self.assertIsNone(why, "a read with a checkout named gave a why: %r" % (why,))
        self.assertEqual(set(times), {"utc-branch", "central-branch"}, "the times do not hold both branches")
        self.assertEqual(times["utc-branch"], self.utc("2026-11-01T10:00:00Z"), "the UTC commit time is wrong")
        self.assertEqual(times["central-branch"], self.utc("2026-11-02T16:00:00Z"), "the -06:00 commit time is wrong")
        for name, at in times.items():
            self.assertIsNotNone(at.tzinfo, "the time of %s is naive" % name)

    def test_a_branch_whose_time_cannot_be_read_is_left_out_and_the_others_stay(self):
        self.origin_commit("good", "2026-11-01T10:00:00Z")
        self.drop_origin("no-ref")
        self.set_origin("tree-ref", self.EMPTY_TREE)
        self.break_origin("broken-ref")
        times, why = build.branch_commit_times(self.repo, ["good", "no-ref", "tree-ref", "broken-ref"])
        self.assertIsNone(why, "a read with a checkout named gave a why: %r" % (why,))
        self.assertEqual(times, {"good": self.utc("2026-11-01T10:00:00Z")},
                         "a branch with no readable commit time was kept, or the good branch was dropped")

    def test_a_time_that_is_not_iso_with_a_zone_is_left_out(self):
        self.origin_commit("good", "2026-11-01T10:00:00Z")
        replies = {"refs/remotes/origin/garbled": "not a time\n", "refs/remotes/origin/naive": "2026-11-01T10:00:00\n"}
        real_git = build.git

        def fake(repo, *args, stdin=None):
            if args[:1] == ("log",) and args[-1] in replies:
                return replies[args[-1]]
            return real_git(repo, *args, stdin=stdin)

        with mock.patch.object(build, "git", fake):
            times, why = build.branch_commit_times(self.repo, ["good", "garbled", "naive"])
        self.assertEqual(times, {"good": self.utc("2026-11-01T10:00:00Z")},
                         "a time that is not ISO with a zone was kept, or the good branch was dropped")

    def test_one_git_log_per_distinct_branch_and_no_network(self):
        self.origin_commit("first", "2026-11-01T10:00:00Z")
        self.origin_commit("second", "2026-11-01T11:00:00Z")
        trace = pathlib.Path(self.tmp.name) / "git-trace.txt"
        with mock.patch.dict(os.environ, {"GIT_TRACE": str(trace)}):
            build.branch_commit_times(self.repo, ["first", "second", "first"])
        reads = {}
        for line in (trace.read_text(encoding="utf-8") if trace.exists() else "").splitlines():
            found = re.search(r" log .*refs/remotes/origin/(\S+)", line)
            if found:
                reads[found.group(1)] = reads.get(found.group(1), 0) + 1
        self.assertEqual(reads, {"first": 1, "second": 1}, "the read was not one git log per distinct branch")
        self.assertEqual(len(self.rest_get.call_args_list), 0, "the commit read made a REST call")

    def test_no_checkout_named_reads_no_time_and_says_why(self):
        times, why = build.branch_commit_times(None, ["any-branch"])
        self.assertEqual(times, {}, "a read with no checkout gave times")
        self.assertTrue(why, "a read with no checkout gave no why")

    def test_an_empty_branch_list_reads_nothing_and_gives_no_why(self):
        self.assertEqual(build.branch_commit_times(self.repo, []), ({}, None))

    def test_the_table_has_one_row_per_draft_pull_with_exactly_the_five_fields(self):
        rows = [self.pull(1, "draft-one"), self.pull(2, "not-a-draft", draft=False), self.pull(3, "draft-three", updated_h=1)]
        table = build.draft_table(rows, self.NOW, {"liveRows": {}}, {}, None, {})
        self.assertEqual([row["number"] for row in table], [1, 3], "the table is not one row per draft pull")
        for row in table:
            self.assertEqual(set(row), {"number", "branch", "lane", "commit", "verdict"},
                             "a table row does not have exactly the five fields")
        self.assertEqual([row["branch"] for row in table], ["draft-one", "draft-three"])

    def test_verdict_is_stale_only_when_the_draft_and_its_commit_are_both_over_twelve_hours(self):
        # (draft updated_at h ago, commit h ago or None, verdict, commit the row carries)
        cases = {"stale draft, commit 13 h old": (13, 13, "stale", self.ago(13)),
                 "stale draft, commit 1 h old": (13, 1, "fresh", self.ago(1)),
                 "stale draft, no commit time": (13, None, "unknown", None),
                 "fresh draft, commit 13 h old": (1, 13, "fresh", None)}
        for name, (updated_h, commit_h, verdict, commit) in cases.items():
            with self.subTest(name):
                times = {} if commit_h is None else {"b": self.ago(commit_h)}
                table = build.draft_table([self.pull(1, "b", updated_h=updated_h)], self.NOW, {"liveRows": {}},
                                          {1: {"number": 1}}, None, times)
                self.assertEqual(len(table), 1, "the draft has no table row")
                self.assertEqual(table[0]["verdict"], verdict, "the verdict for %s is wrong" % name)
                self.assertEqual(table[0]["commit"], commit, "the commit for %s is not the one the rule names" % name)

    def test_lane_is_live_then_held_then_none_and_unknown_when_no_mark_is_read(self):
        rows = [self.pull(n, branch) for n, branch in ((1, "live-br"), (2, "held-br"), (3, "review-br"),
                                                       (4, "plain-br"), (5, "no-row-br"))]
        lanes = {"liveRows": {"s-live": ["live-br"]}}
        marks = {1: {"number": 1, "held": True}, 2: {"number": 2, "held": True}, 3: {"number": 3, "reviewLog": True},
                 4: {"number": 4}}
        table = build.draft_table(rows, self.NOW, lanes, marks, None, {})
        self.assertEqual(self.lanes_by_number(table), {1: "live", 2: "held", 3: "held", 4: "none", 5: "unknown"},
                         "a live lane, a held or review-logged pull, a clean pull and an unmarked pull got the wrong lanes")
        table = build.draft_table(rows, self.NOW, lanes, marks, "the live file was read 90 minutes ago", {})
        self.assertEqual(self.lanes_by_number(table), {1: "live", 2: "unknown", 3: "unknown", 4: "unknown", 5: "unknown"},
                         "unread marks did not make every non-live lane unknown")

    @staticmethod
    def lanes_by_number(table):
        return {row["number"]: row["lane"] for row in table}

    def test_a_commit_dated_after_the_build_reads_the_draft_unknown_never_fresh(self):
        # ago(-1) is one hour after NOW: a commit from the future proves nothing about the draft's age.
        table = build.draft_table([self.pull(1, "future-commit")], self.NOW, {"liveRows": {}}, {1: {"number": 1}}, None,
                                  {"future-commit": self.ago(-1)})
        self.assertEqual(len(table), 1, "the draft has no table row")
        self.assertEqual(table[0]["verdict"], "unknown",
                         "a commit an hour after the build read the stale draft fresh, so it was silent")

    def test_the_stale_draft_entries_are_the_table_rows_formatted(self):
        # Four drafts, all stale by updated_at: a stale commit (listed), a recent commit (fresh), no commit (unknown),
        # and a held one (silent). stale_drafts must print exactly the rows the table marks as shown.
        self.origin_commit("old-commit", self.iso(13))
        self.origin_commit("recent-commit", self.iso(1))
        self.drop_origin("no-commit")
        self.origin_commit("held-one", self.iso(13))
        rows = [self.pull(1, "old-commit"), self.pull(2, "recent-commit"), self.pull(3, "no-commit"),
                self.pull(4, "held-one")]
        # The live pulls rows carry the marks: #1 to #3 have a row with no marks, #4 is held.
        work = {"liveRows": {}, "pulls": [{"number": 1}, {"number": 2}, {"number": 3}, {"number": 4, "held": True}],
                "staleWhy": None, "pullWhy": None}
        entries = build.stale_drafts(work, (rows, None), self.NOW, repo=self.repo)
        times, _ = build.branch_commit_times(self.repo, [row["branch"] for row in rows])
        marks = {p["number"]: p for p in work["pulls"]}
        expected = []
        for row in build.draft_table(rows, self.NOW, work, marks, None, times):
            if row["verdict"] == "fresh" or row["lane"] in ("live", "held"):
                continue
            if row["verdict"] == "unknown":
                expected.append("unknown (#%d branch %s has no commit time)" % (row["number"], row["branch"]))
            else:
                expected.append("#%d (%s)" % (row["number"], row["branch"]))
        self.assertEqual(expected, ["#1 (old-commit)", "unknown (#3 branch no-commit has no commit time)"],
                         "the table rows the case expects are not the two it names")
        self.assertEqual(entries, expected, "the stale-draft entries are not the table's rows formatted")


class SessionsSource(UpkeepFixture):
    """The stale-draft row takes its sessions from a named source: `--sessions-source NAME`, default `live-file`. The
    registry build.SESSION_SOURCES maps a name to a reader that returns (liveRows-style rows, None) or (None, why). A name
    the registry does not hold reads the row `unknown (sessions source NAME is not wired)`. A reader that raises or returns
    a bad shape reads the row unknown. A reader's rows replace the live file's sessions for the lane check, and that check
    no longer needs a fresh live file. held and reviewLog still come from the live pulls rows, so a stale draft with no
    live row reads unknown."""

    DRAFT = ReadyAndDraftRows.DRAFT
    UNWIRED = "unknown (sessions source %s is not wired)"

    def test_the_build_accepts_the_sessions_source_flag(self):
        # The one case that carries the flag's red: a build that predates the flag refuses it with exit 2.
        self.on_main()
        code, out = run_build("--repo", str(self.repo), "--out", str(self.out), "--sessions-source", "live-file")
        self.assertNotEqual(code, 2, "the build refused --sessions-source: %s" % out.strip().splitlines()[-1])

    def test_no_flag_and_the_live_file_name_read_the_same_row(self):
        # The control: the default run lists the stale draft, and the explicit live-file name reads the same row.
        self.serve_pulls([self.rest_draft(1001, "c1", 780)])
        self.publish(sessions=[], pulls=[self.live_pull(1001, "c1")])
        _, bare = self.source_out(None)
        self.assertEqual(self.row(bare, self.DRAFT), (1, "#1001 (c1)"), "the default run lost the stale draft")
        _, named = self.source_out("live-file")
        self.assertEqual(self.row(named, self.DRAFT), self.row(bare, self.DRAFT), "live-file reads differently from no flag")

    def test_the_default_run_never_calls_a_registered_reader(self):
        reader = mock.Mock(return_value=({"session-a": ["c1"]}, None))
        self.serve_pulls([self.rest_draft(1001, "c1", 780)])
        with self.register_source("fake", reader):
            _, out = self.source_out(None, live=False)
        self.assertFalse(reader.called, "the default run read a registered sessions source")
        count, detail = self.row(out, self.DRAFT)
        self.assertEqual(count, 1, "the row was %r" % (detail,))
        self.assertTrue(detail.startswith("unknown (sessions not read: ") and "--live" in detail, detail)
        self.assertNotIn("#1001", detail)

    def test_an_unwired_name_reads_one_unknown_entry_that_names_it(self):
        reader = mock.Mock(return_value=({"session-a": ["c1"]}, None))
        self.serve_pulls([self.rest_draft(1001, "c1", 780)])
        self.publish(sessions=[], pulls=[self.live_pull(1001, "c1")])
        with self.register_source("fake", reader):
            _, out = self.source_out("nope")
        self.assertFalse(reader.called, "a name the registry does not hold read a registered source")
        self.assertEqual(self.row(out, self.DRAFT), (1, self.UNWIRED % "nope"))

    def test_an_unwired_name_never_reads_clear_when_no_draft_is_stale(self):
        self.serve_pulls(self.fresh_rows(1001, 2))
        self.publish(sessions=[])
        _, out = self.source_out("nope")
        self.assertEqual(self.row(out, self.DRAFT), (1, self.UNWIRED % "nope"),
                         "a clean read under an unwired name read the row clear")

    def test_a_reader_that_raises_reads_one_unknown_entry_and_does_not_crash(self):
        reader = mock.Mock(side_effect=RuntimeError("the session list is down"))
        self.serve_pulls([self.rest_draft(1001, "c1", 780)])
        self.publish(sessions=[], pulls=[self.live_pull(1001, "c1")])
        with self.register_source("fake", reader):
            _, out = self.source_out("fake")
        self.assertTrue(reader.called, "the named reader was not called")
        count, detail = self.row(out, self.DRAFT)
        self.assertEqual(count, 1, "the row was %r" % (detail,))
        self.assertTrue(detail.startswith("unknown ("), detail)
        self.assertNotIn("#1001", detail, "a raising reader let the stale draft through")

    def test_a_reader_with_a_bad_shape_reads_one_unknown_entry(self):
        bad = {"not a tuple": 7,
               "a tuple of three": ({"session-a": ["c1"]}, None, None),
               "a tuple of one": ({"session-a": ["c1"]},),
               "rows is a list": (["c1"], None),
               "a session's steps are not a list": ({"session-a": "c1"}, None),
               "a step id is not text": ({"session-a": [7]}, None),
               "a session key is not text": ({7: ["c1"]}, None),
               "neither rows nor why": (None, None)}
        self.serve_pulls([self.rest_draft(1001, "c1", 780)])
        self.publish(sessions=[], pulls=[self.live_pull(1001, "c1")])
        for name, value in bad.items():
            with self.subTest(name):
                reader = mock.Mock(return_value=value)
                with self.register_source("fake", reader):
                    _, out = self.source_out("fake")
                self.assertTrue(reader.called, "the named reader was not called")
                count, detail = self.row(out, self.DRAFT)
                self.assertEqual(count, 1, "the row was %r" % (detail,))
                self.assertTrue(detail.startswith("unknown ("), detail)
                self.assertNotIn("#1001", detail, "a bad shape let the stale draft through")

    def test_a_reader_that_gives_a_why_reads_that_why_in_the_unknown_entry(self):
        reader = mock.Mock(return_value=(None, "the session list timed out"))
        self.serve_pulls([self.rest_draft(1001, "c1", 780)])
        self.publish(sessions=[], pulls=[self.live_pull(1001, "c1")])
        with self.register_source("fake", reader):
            _, out = self.source_out("fake")
        self.assertTrue(reader.called, "the named reader was not called")
        count, detail = self.row(out, self.DRAFT)
        self.assertEqual(count, 1, "the row was %r" % (detail,))
        self.assertTrue(detail.startswith("unknown (") and "the session list timed out" in detail, detail)
        self.assertNotIn("#1001", detail)

    def test_reader_rows_hold_a_draft_whatever_the_live_file_is(self):
        # The lane check needs no fresh live file: no file, a file read 90 minutes ago, and an unreadable file all hold c1.
        reader = mock.Mock(return_value=({"session-a": ["c1"]}, None))
        self.serve_pulls([self.rest_draft(1001, "c1", 780)])
        # Each state: how the live file is set up, and whether the build gets a --live argument at all.
        states = {"no --live file": (lambda: None, False),
                  "a live file read 90 minutes ago": (lambda: self.publish(read_at=iso_ago(90), sessions=[]), True),
                  "an unreadable live file": (lambda: self.write_live("{not json"), True)}
        for name, (write, live) in states.items():
            with self.subTest(name):
                reader.reset_mock()
                write()
                with self.register_source("fake", reader):
                    _, out = self.source_out("fake", live=live)
                self.assertTrue(reader.called, "the named reader was not called")
                self.assertEqual(self.row(out, self.DRAFT), (0, ""), "a held draft was listed or read unknown")

    def test_reader_rows_replace_the_live_files_sessions(self):
        # The live file's session holds c1, but the reader's rows hold only c2. #1001 (c1) is listed; #1002 (c2) is held.
        reader = mock.Mock(return_value=({"session-b": ["c2"]}, None))
        self.serve_pulls([self.rest_draft(1001, "c1", 780), self.rest_draft(1002, "c2", 780)])
        self.publish(sessions=[self.session_in_repo("session_test01", "SESSION_STATUS_RUNNING", "cs-step:c1")],
                     pulls=[self.live_pull(1001, "c1"), self.live_pull(1002, "c2")])
        with self.register_source("fake", reader):
            _, out = self.source_out("fake")
        self.assertTrue(reader.called, "the named reader was not called")
        count, detail = self.row(out, self.DRAFT)
        self.assertEqual((count, self.entries(detail)), (1, ["#1001 (c1)"]),
                         "the live file's session still held #1001 beside the reader's rows")

    def test_a_reader_without_a_live_row_leaves_a_stale_draft_unknown_not_listed(self):
        # No --live file: the reader holds c1, so #1001 is skipped. #1002 has no live pulls row, so its marks are unread.
        reader = mock.Mock(return_value=({"session-a": ["c1"]}, None))
        self.serve_pulls([self.rest_draft(1001, "c1", 780), self.rest_draft(1002, "lone", 780)])
        with self.register_source("fake", reader):
            _, out = self.source_out("fake", live=False)
        self.assertTrue(reader.called, "the named reader was not called")
        count, detail = self.row(out, self.DRAFT)
        self.assertEqual(count, 1, "the row was %r" % (detail,))
        self.assertTrue(detail.startswith("unknown (#1002 "), detail)
        self.assertNotIn("#1001", detail, "the draft the reader holds was named")

    def test_a_fresh_live_file_with_no_sessions_list_still_feeds_a_registered_reader(self):
        # The reader holds c1, and #1002's live row is held. The file has no sessions list, and #1003 is listed.
        reader = mock.Mock(return_value=({"session-a": ["c1"]}, None))
        self.serve_pulls([self.rest_draft(1001, "c1", 780), self.rest_draft(1002, "held-draft", 780),
                          self.rest_draft(1003, "lone", 780)])
        self.publish(pulls=[self.live_pull(1001, "c1"), dict(self.mark(1002), branch="held-draft", held=True),
                            self.live_pull(1003, "lone")])
        with self.register_source("fake", reader):
            _, out = self.source_out("fake")
        self.assertTrue(reader.called, "the named reader was not called")
        count, detail = self.row(out, self.DRAFT)
        self.assertEqual((count, self.entries(detail)), (1, ["#1003 (lone)"]))

    def test_an_empty_reader_read_is_known_and_lists_the_drafts_with_live_rows(self):
        reader = mock.Mock(return_value=({}, None))
        self.serve_pulls([self.rest_draft(1001, "c1", 780), self.rest_draft(1002, "lone", 780)])
        self.publish(sessions=[], pulls=[self.live_pull(1001, "c1"), self.live_pull(1002, "lone")])
        with self.register_source("fake", reader):
            _, out = self.source_out("fake")
        self.assertTrue(reader.called, "the named reader was not called")
        count, detail = self.row(out, self.DRAFT)
        self.assertEqual((count, self.entries(detail)), (2, ["#1001 (c1)", "#1002 (lone)"]),
                         "an empty read was read unknown, not known")

    def test_a_full_page_of_drafts_splits_by_a_full_size_reader_read(self):
        # One hundred stale drafts on one full page. The reader holds the even steps' sessions: fifty held, fifty listed.
        drafts = [self.rest_draft(1000 + n, "step-%03d" % n, 780) for n in range(100)]
        rows = {"session-%03d" % n: ["step-%03d" % n] for n in range(0, 100, 2)}
        reader = mock.Mock(return_value=(rows, None))
        self.serve_pulls(drafts)
        self.publish(sessions=[], pulls=[self.live_pull(1000 + n, "step-%03d" % n) for n in range(1, 100, 2)])
        with self.register_source("fake", reader):
            _, out = self.source_out("fake")
        self.assertTrue(reader.called, "the named reader was not called")
        count, detail = self.row(out, self.DRAFT)
        expected = sorted("#%d (step-%03d)" % (1000 + n, n) for n in range(1, 100, 2))
        self.assertEqual((count, self.entries(detail)), (50, expected))


class DoneWithoutCheck(UpkeepFixture):
    """The upkeep row `done without check`, the last row. It reads the done steps whose updatedAt is on or after
    build.DONE_CHECK_SINCE (an ISO UTC time), and lists each whose note, why and ask (joined) fail the close check:
    no Done check named (whole words, any case), `<id>`; a Done check named, but no field holds the phrase
    `Done check green on main:` (any case) followed, after optional spaces, by a ref that lint/report_guard.py
    DONE_REF_RE accepts, `<id> (not shown green on main)`; an updatedAt that is missing or unparsable,
    `<id> (updatedAt unreadable)`. Nothing else shows a Done check green: not `met on main`, not a bare
    `Green on main:`, and no negator or future word. The row reads the step files only, so it needs no --live file."""

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

    def test_a_naive_updated_at_is_listed_as_unreadable(self):
        """A time with no zone is unreadable, as build.zoned_time reads it (None for naive). The step is listed with the
        unreadable mark whatever its note says, and before the constant too. The zoned step is the control."""
        since = self.since_dt()
        after = (since + datetime.timedelta(hours=1)).replace(tzinfo=None).isoformat()
        early = (since - datetime.timedelta(seconds=1)).replace(tzinfo=None).isoformat()
        closed = "Done check: X. Done check green on main: #1312."
        self.commit_steps({
            "aware-control": self.done_step(note="Shipped."),
            "naive-note": self.done_step(updated=after, note="Shipped."),
            "naive-closed": self.done_step(updated=after, note=closed),
            "naive-early": self.done_step(updated=early, note="Shipped."),
        })
        _, entries = self.listed()
        self.assertIn("aware-control", entries)  # scope first: a zoned done step is in scope and listed
        self.assertEqual(entries, sorted(["aware-control", "naive-note" + self.UNREADABLE,
                                          "naive-closed" + self.UNREADABLE, "naive-early" + self.UNREADABLE]),
                         "a done step with a naive updatedAt is not listed as unreadable")

    def test_a_well_formed_close_is_not_listed(self):
        # False-alarm class: a Done check, and the phrase `Done check green on main:` with a ref after it, are not listed.
        closes = {"colon-ref": "Done check: X. Done check green on main: #1312.",
                  "lower-short-hash": "done check green on main: a1b2c3d.",
                  "any-case": "DONE CHECK: X. DONE CHECK GREEN ON MAIN: #1312.",
                  "long-hash": "Done check: X. Done check green on main: %s." % self.HASH_40}
        steps = {"bad-control": self.done_step(note="Shipped.")}
        steps.update({sid: self.done_step(note=note) for sid, note in closes.items()})
        self.commit_steps(steps)
        _, entries = self.listed()
        self.assertIn("bad-control", entries)  # scope first: the in-scope close with no check is listed
        self.assertEqual(entries, ["bad-control"], "a well-formed close is listed")

    def test_a_named_check_with_no_shown_green_line_is_listed_as_not_shown(self):
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
        self.assertEqual(entries, expected, "a named check with no shown green line is not listed as not shown")

    def test_the_ref_must_follow_the_phrase_at_once(self):
        # Miss class: the ref must come right after `Done check green on main:`. A word first, or no ref at all, does
        # not show it green, even with a ref later in the same field.
        self.commit_steps({
            "bad-control": self.done_step(note="Shipped."),
            "exact": self.done_step(note="Done check green on main: #1312."),
            "see-ref": self.done_step(note="Done check green on main: see #1312."),
            "word-then-ref": self.done_step(note="Done check green on main: soon #1312."),
            "no-ref": self.done_step(note="Done check green on main: soon."),
        })
        _, entries = self.listed()
        self.assertIn("bad-control", entries)  # scope first: the in-scope close with no check is listed
        self.assertEqual(entries, sorted(["bad-control", "see-ref" + self.NOT_SHOWN,
                                          "word-then-ref" + self.NOT_SHOWN, "no-ref" + self.NOT_SHOWN]),
                         "a word, or no ref, after the colon shows the Done check green")

    def test_the_colon_is_required(self):
        # Miss class: `green on main` with no colon after `main` does not show it green, even with a ref after it or
        # in another sentence.
        self.commit_steps({
            "bad-control": self.done_step(note="Shipped."),
            "exact": self.done_step(note="Done check green on main: #1312."),
            "no-colon": self.done_step(note="Done check green on main #5"),
            "ref-after": self.done_step(note="Done check green on main. Fixed in #1312."),
            "ref-before": self.done_step(note="Fixed in #1312. Done check green on main."),
        })
        _, entries = self.listed()
        self.assertIn("bad-control", entries)  # scope first: the in-scope close with no check is listed
        self.assertEqual(entries, sorted(["bad-control", "no-colon" + self.NOT_SHOWN, "ref-after" + self.NOT_SHOWN,
                                          "ref-before" + self.NOT_SHOWN]),
                         "a phrase with no colon after main shows the Done check green")

    def test_the_phrase_must_be_whole_words(self):
        # Miss class: `green on main` must be whole words in the phrase. A word that only contains a phrase word does not count.
        self.commit_steps({
            "bad-control": self.done_step(note="Shipped."),
            "exact": self.done_step(note="Done check green on main: #1312."),
            "red-green": self.done_step(note="Done check: red on main and green on the fix #1312."),
            "mainline": self.done_step(note="Done check green on mainline: #1312."),
            "greens": self.done_step(note="Done check greens on main: #1312."),
        })
        _, entries = self.listed()
        self.assertIn("bad-control", entries)  # scope first: the in-scope close with no check is listed
        self.assertEqual(entries, sorted(["bad-control", "red-green" + self.NOT_SHOWN, "mainline" + self.NOT_SHOWN,
                                          "greens" + self.NOT_SHOWN]),
                         "a phrase that is not whole words shows the Done check green")

    def test_the_source_must_have_the_shape_of_a_ref(self):
        # Miss class: `#` with no digits and a 41-character hash are not sources. 6 to 40 hex characters with a
        # digit are, as lint/report_guard.py DONE_REF_RE takes them (one home).
        self.commit_steps({
            "ok-seven": self.done_step(note="Done check green on main: a1b2c3d."),
            "ok-six": self.done_step(note="Done check green on main: a1b2c3."),
            "ok-forty": self.done_step(note="Done check green on main: %s." % self.HASH_40),
            "hash-only": self.done_step(note="Done check green on main: #."),
            "forty-one": self.done_step(note="Done check green on main: %s0." % self.HASH_40),
        })
        _, entries = self.listed()
        self.assertIn("hash-only" + self.NOT_SHOWN, entries)
        self.assertEqual(entries, sorted(["hash-only" + self.NOT_SHOWN, "forty-one" + self.NOT_SHOWN]),
                         "a source that is not a PR number or a 6-40 character hash with a digit is not accepted")

    def test_the_phrase_must_be_exact_and_contiguous(self):
        # Miss class, one cause per case: `met on main` is not the phrase; `Green on main:` with no `Done check`
        # right before it is not the phrase; a word or a break between `Done check` and `green on main` breaks it.
        self.commit_steps({
            "bad-control": self.done_step(note="Shipped."),
            "met": self.done_step(note="Done check met on main (a1b2c3d)."),
            "bare": self.done_step(note="Done check: X. Green on main: #1312."),
            "not-yet": self.done_step(note="Done check not yet; green on main #5"),
            "should-be": self.done_step(note="Done check should be green on main after PR #5"),
        })
        _, entries = self.listed()
        self.assertIn("bad-control", entries)  # scope first: the in-scope close with no check is listed
        for sid, cause in (("met", "met on main is not the phrase"),
                           ("bare", "a break between Done check and green on main"),
                           ("not-yet", "words between Done check and green on main"),
                           ("should-be", "words between Done check and green on main")):
            with self.subTest(case=sid):
                self.assertIn(sid + self.NOT_SHOWN, entries, cause)

    def test_words_after_the_ref_do_not_change_a_shown_green_line(self):
        # The rule reads the phrase and the ref after it. A future word later in the same sentence does not unshow it.
        self.commit_steps({
            "bad-control": self.done_step(note="Shipped."),
            "after-ref": self.done_step(note="Done check green on main: #1312, fixed after the merge."),
        })
        _, entries = self.listed()
        self.assertIn("bad-control", entries)  # scope first: the in-scope close with no check is listed
        self.assertEqual(entries, ["bad-control"], "a future word after the ref unshows a Done check green line")

    def test_the_ref_forms_after_the_colon_show_green_on_main(self):
        # The ref forms lint/report_guard.py DONE_REF_RE accepts after the colon: `PR <n>`, a /pull/<n> URL (the ref is
        # inside the word, and DONE_REF_RE finds it there), and no space at all. The phrase counts in why and ask too.
        self.commit_steps({
            "bad-control": self.done_step(note="Shipped."),
            "pr-word": self.done_step(note="Done check green on main: PR 1312."),
            "pull-url": self.done_step(note="Done check green on main: https://github.com/o/r/pull/1312."),
            "no-space": self.done_step(note="Done check green on main:#1312."),
            "in-why": self.done_step(note="Shipped.", why="Done check green on main: #1312."),
            "in-ask": self.done_step(note="Shipped.", ask="Done check green on main: #1312."),
        })
        _, entries = self.listed()
        self.assertIn("bad-control", entries)  # scope first: the in-scope close with no check is listed
        self.assertEqual(entries, ["bad-control"], "a ref form after the colon is listed as not shown")

    def test_a_hex_letter_word_is_no_commit_ref(self):
        # Miss class: `effaced` is hex letters with no digit. DONE_REF_RE needs a digit in a hex run, so it is no ref.
        self.commit_steps({
            "bad-control": self.done_step(note="Shipped."),
            "effaced": self.done_step(note="Done check green on main: effaced."),
        })
        _, entries = self.listed()
        self.assertIn("bad-control", entries)  # scope first: the in-scope close with no check is listed
        self.assertEqual(entries, sorted(["bad-control", "effaced" + self.NOT_SHOWN]),
                         "a hex-letter word with no digit is read as a commit ref")

    def test_done_checks_and_undone_check_are_not_named(self):
        # Named is whole words `done check`: `Done checks` and `Undone check` do not name a check.
        self.commit_steps({
            "plural": self.done_step(note="Done checks: green on main #1312."),
            "undone": self.done_step(note="Undone check green on main: #1312."),
            "no-name": self.done_step(note="Green on main: #1312."),
        })
        _, entries = self.listed()
        self.assertEqual(entries, ["no-name", "plural", "undone"],
                         "a `Done checks` or `Undone check` phrase is read as a named check")

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
            steps["good-%03d" % n] = self.done_step(note="Done check green on main: #1312.")
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

    def check_starts(self, expect=(1,)):
        """One build, with its mockup check wrapped to count the git processes the check starts. Each process is counted
        at subprocess.Popen, the one start every helper of the build reaches, so a git call made any way is counted.
        The rest of the build is outside the count. `expect` is the build's exit codes: (1,) when a miss exits it, (0,)
        when every file is on origin. Returns (build output, the check's (misses, unread), the git argv
        the check started). The check's result is None when the check did not run."""
        real = build.mockup_misses
        seen = {}

        def check(repo, steps):
            with mock.patch.object(subprocess, "Popen", wraps=subprocess.Popen) as popen:
                seen["result"] = real(repo, steps)
            seen["argv"] = [c.args[0] for c in popen.call_args_list if c.args and c.args[0][:1] == ["git"]]
            return seen["result"]

        with mock.patch.object(build, "mockup_misses", check):
            _, out = self.build_from_main(expect=expect)
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

    def test_five_files_on_origin_over_fifty_origin_refs_start_at_most_four_git_processes(self):
        # The on-origin path, not the all-miss path: each of the five files is on origin/main, so the check reads them.
        for k in range(1, 6):
            item = "item%d-a" % (40 + k)
            self.commit_step("c%d" % k, order=k, title="Picker %d" % k, note="Shape the %s picker." % item,
                             mockups={item: "docs/design/item%d/a.html" % (40 + k)})
        for k in range(1, 6):
            self.commit_design("docs/design/item%d/a.html" % (40 + k))
        self.fetch_origin("main")
        for n in range(1, 50):
            self.fetch_origin("main", name="lane-%02d" % n)  # 50 origin refs in all, as open PR branches leave them
        out, result, argv = self.check_starts(expect=(0,))
        self.steps_line(out, 5)
        self.assertIsNotNone(result, "the mockup check did not run")
        misses, unread = result
        self.assertEqual(misses, [], "a file on origin read as a miss")
        self.assertEqual(unread, [], "a file on origin read as unknown")
        self.assertTrue(any("cat-file" in call for call in argv), "the check never read origin's files: %r" % argv)
        self.assertLessEqual(len(argv), 4, "the mockup check started %d git processes for 5 files on origin over 50 origin refs, "
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
    open pull request or open page item still holds it. A lane that only stale drafts hold gets one `joint (...)` line
    instead of silence, and the row counts it. A read the build cannot make is one `unknown (...)` entry,
    never an empty list. Each negative case shares its live file with a listed control, so an empty row cannot pass."""

    ROW = "lanes to archive"
    # The hold line for a lane a doing step still holds: the step id(s), then the way out, then the lane. Pinned here and
    # in merge/test_idle_lanes.py, the CLI's copy of the same line.
    DOING_HOLD = "hold (step %s still doing under this lane; set the step's status to todo or done; lane %s)"

    # The joint line for one lane: its stale draft PRs to close, the branches to archive, then the lane's session id.
    JOINT = "joint (close #%d; archive archive/%s; archive lane %s)"

    def lane(self, sid, step, bucket=BUCKET_COMPLETED, status="SESSION_STATUS_IDLE", idle_since=_ABSENT,
             unarchived=_ABSENT, tags=()):
        """A sessions row for a lane of this repo that names `step`, with its get_session bucket and any extra tags.
        idle_since and unarchived (the row's unarchived_epoch) are left out unless given."""
        row = session_row(sid, status, "cs-build:lane", "cs-step:" + step, self.REPO, *tags, status_bucket=bucket)
        if idle_since is not _ABSENT:
            row["idle_since"] = idle_since
        if unarchived is not _ABSENT:
            row["unarchived_epoch"] = unarchived
        return row

    def idle_lane(self, sid, step, idle_since=None, unarchived=0, tags=()):
        """A completed lane on `step` idle 13 h at the live read, with no unarchived commit, unless the case gives
        idle_since (_ABSENT leaves it out), unarchived or extra tags."""
        since = self.created_before(13 * 60) if idle_since is None else idle_since
        return self.lane(sid, step, idle_since=since, unarchived=unarchived, tags=tags)

    def stale_pull(self, number, branch, title=None, hours=13, **fields):
        """An open draft pull on `branch`, created `hours` before the live read, with its head off main (the record
        branch's tip, which main never reaches). A field in `fields` sets that key; _ABSENT leaves it out."""
        row = self.draft(number, branch, self.created_before(hours * 60), title)
        row["head"] = self.off_main()
        for key, value in fields.items():
            if value is _ABSENT:
                row.pop(key, None)
            else:
                row[key] = value
        return row

    def main_tip(self):
        return git(self.repo, "rev-parse", "main").strip()

    def joint_for(self, entries, sid):
        """The joint lines that name lane `sid`."""
        return [e for e in entries if e.startswith("joint (") and e.endswith("; archive lane %s)" % sid)]

    def tree(self):
        """Every file under the case's temp folder, with its size and mtime, so a write anywhere shows as a change."""
        root = pathlib.Path(self.tmp.name)
        return sorted((str(p.relative_to(root)), p.stat().st_size, p.stat().st_mtime_ns)
                      for p in root.rglob("*") if p.is_file())

    def publish(self, sessions=None, pulls=(), threads=(), read_at=None, items=(), landed=None):
        """UpkeepFixture.publish with the items key present: [] unless a case names rows. items=None leaves the key out,
        the file a publisher writes before the waiting page had items."""
        return super().publish(sessions=sessions, pulls=pulls, threads=threads, read_at=read_at,
                               items=None if items is None else list(items), landed=landed)

    def land(self, steps):
        """Write {step id: fields} on the record branch in one commit. Each step is written whole, from STEP."""
        for sid, fields in steps.items():
            self.write_step(sid, dict(STEP, **fields))
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "steps " + ", ".join(sorted(steps)))

    def commit_handoff(self, slug):
        """The lane's handoff file on the record branch, at the path the archive-ready check reads. Leaves HEAD on roadmap."""
        git(self.repo, "checkout", "-q", "roadmap")
        path = self.repo / (build.IDLE_HANDOFF % slug)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# %s\n" % slug, encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "handoff " + slug)

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

    def steps_and_marks(self):
        """The record's steps and the landed marks main gives them, read as the build reads them for idle_lanes."""
        source, why = build.record_source(self.repo, "roadmap")
        self.assertIsNotNone(source, why)
        steps = build.load(source)["steps"]
        marks, _strays, _why = build.landed_marks(self.repo, build.main_ref(self.repo, "main"), "main", steps)
        return steps, marks

    def idle_direct(self):
        """build.idle_lanes on the fixture's live file, with the steps, marks and repo name the build reads."""
        fn = getattr(build, "idle_lanes", None)
        if fn is None:
            self.fail("build.idle_lanes is absent: no function names the lanes to archive")
        steps, marks = self.steps_and_marks()
        work = build.live_work(str(self.live), steps, self.SLUG)
        return fn(work, steps, marks, self.SLUG, self.repo)

    @staticmethod
    def ids(entries):
        """The first word of each entry: a session id, or `unknown` for an unknown entry."""
        return sorted(entry.split(" ", 1)[0] for entry in entries)

    @staticmethod
    def named(entries, sid):
        return any(sid in entry for entry in entries)

    def reported(self):
        """build.idle_lanes_report on the fixture's live file: the entries `merge --idle-lanes` prints, unjoined."""
        return build.idle_lanes_report(self.repo, str(self.live))

    def line_for(self, entries, sid):
        """The one entry of lane `sid`: its archive line `<sid> (...)`, or its hold line, which ends `; lane <sid>)`."""
        found = [e for e in entries if e.startswith(sid + " (") or e.endswith("; lane %s)" % sid)]
        self.assertEqual(len(found), 1, "lane %s has %d lines, not one: %r" % (sid, len(found), entries))
        return found[0]

    def assert_held(self, line, sid):
        """A per-lane verdict that cannot archive reads `hold (<why>; lane <sid>)`."""
        self.assertTrue(line.startswith("hold (") and line.endswith("; lane %s)" % sid), "not a hold line: %r" % (line,))

    def assert_no_unknown_line(self, entries):
        """`unknown (` is the form for a read the whole list cannot make. A per-lane reason never reads that way."""
        self.assertFalse([e for e in entries if e.startswith("unknown (")], "a per-lane reason reads unknown: %r" % (entries,))

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

    def test_lane_with_no_cs_step_is_held_with_its_reason_and_never_listed(self):
        # A completed lane with no cs-step tag is held, and the hold names the missing tag. A working lane with no step is
        # not idle, so it reads no line. session_a is the listed control.
        self.land({"c1": {"status": "done", "order": 1}})
        no_step = session_row("session_nostep", "SESSION_STATUS_IDLE", "cs-build:lane", self.REPO,
                              status_bucket=BUCKET_COMPLETED)
        busy = session_row("session_busy", "SESSION_STATUS_RUNNING", "cs-build:lane", self.REPO,
                           status_bucket=BUCKET_WORKING)
        self.publish(sessions=[no_step, busy, self.lane("session_a", "c1")])
        entries = self.reported()
        self.assertEqual(self.line_for(entries, "session_a"), "session_a (c1; topic -)", entries)
        line = self.line_for(entries, "session_nostep")
        self.assert_held(line, "session_nostep")
        self.assertIn("no cs-step tag", line)
        self.assertEqual([e for e in entries if "session_busy" in e], [], "a working lane with no step got a line: %r" % (entries,))
        self.assert_no_unknown_line(entries)

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

    def test_step_id_not_on_the_record_branch_with_no_trailer_holds_the_lane_and_is_never_unknown(self):
        # No Step trailer on main and no other repo tag, so the step cannot be shown landed. The hold names the step and
        # the missing trailer. session_a is the listed control.
        self.land({"c1": {"status": "done", "order": 1}})
        self.publish(sessions=[self.lane("session_orphan", "ghost"), self.lane("session_a", "c1")])
        entries = self.reported()
        self.assertEqual(self.line_for(entries, "session_a"), "session_a (c1; topic -)", entries)
        line = self.line_for(entries, "session_orphan")
        self.assert_held(line, "session_orphan")
        self.assertIn("ghost", line)
        self.assertIn("no Step trailer on main", line)
        self.assert_no_unknown_line(entries)

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

    def test_absent_step_with_a_step_trailer_on_main_is_landed_and_its_lane_is_listed(self):
        # The step is not on the record branch, and a Step trailer on main names it, so the step reads as landed.
        # session_a is the listed control.
        self.land({"c1": {"status": "done", "order": 1}})
        self.trailer_on_main("ghost")
        self.publish(sessions=[self.lane("session_orphan", "ghost"), self.lane("session_a", "c1")])
        entries = self.reported()
        self.assertEqual(self.line_for(entries, "session_a"), "session_a (c1; topic -)", entries)
        self.assertEqual(self.line_for(entries, "session_orphan"), "session_orphan (ghost; topic -)", entries)
        self.assert_no_unknown_line(entries)

    def test_absent_step_with_a_trailer_held_by_an_open_pull_has_no_line(self):
        # A lane that waits on an open pull reads no line, whether or not its step has a trailer. session_a is the control.
        self.land({"c1": {"status": "done", "order": 1}})
        self.trailer_on_main("ghost")
        self.publish(sessions=[self.lane("session_orphan", "ghost"), self.lane("session_a", "c1")],
                     pulls=[{"number": 61, "title": "lane ghost", "branch": "lane/ghost"}])
        entries = self.reported()
        self.assertEqual(self.line_for(entries, "session_a"), "session_a (c1; topic -)", entries)
        self.assertEqual([e for e in entries if "session_orphan" in e], [],
                         "a lane held by an open pull got a line: %r" % (entries,))
        self.assert_no_unknown_line(entries)

    def test_absent_step_with_another_repo_tag_holds_the_lane_and_names_that_tag(self):
        # No Step trailer on main, and the lane also carries another repo's cs-repo tag. The hold names that tag.
        # session_a is the listed control.
        self.land({"c1": {"status": "done", "order": 1}})
        other = session_row("session_orphan", "SESSION_STATUS_IDLE", "cs-build:lane", "cs-step:ghost", self.REPO,
                            "cs-repo:owner/other", status_bucket=BUCKET_COMPLETED)
        self.publish(sessions=[other, self.lane("session_a", "c1")])
        entries = self.reported()
        self.assertEqual(self.line_for(entries, "session_a"), "session_a (c1; topic -)", entries)
        line = self.line_for(entries, "session_orphan")
        self.assert_held(line, "session_orphan")
        self.assertIn("cs-repo:owner/other", line)
        self.assert_no_unknown_line(entries)

    def test_absent_step_with_a_trailer_and_another_repo_tag_is_still_listed(self):
        # The other repo's tag holds a lane only when no Step trailer on main names its step. The trailer is the positive
        # proof here, so the lane is listed. session_a is the listed control.
        self.land({"c1": {"status": "done", "order": 1}})
        self.trailer_on_main("ghost")
        other = session_row("session_orphan", "SESSION_STATUS_IDLE", "cs-build:lane", "cs-step:ghost", self.REPO,
                            "cs-repo:owner/other", status_bucket=BUCKET_COMPLETED)
        self.publish(sessions=[other, self.lane("session_a", "c1")])
        entries = self.reported()
        self.assertEqual(self.line_for(entries, "session_a"), "session_a (c1; topic -)", entries)
        self.assertEqual(self.line_for(entries, "session_orphan"), "session_orphan (ghost; topic -)", entries)
        self.assert_no_unknown_line(entries)

    def test_lanes_to_archive_row_lists_a_trailer_landed_lane_and_holds_an_absent_step_lane(self):
        # The row prints the list merge --idle-lanes prints, so its raw detail carries the archive line and the hold
        # line. The detail is read raw: a hold reason is not split on the row's ", " joiner. session_a is the control.
        self.land({"c1": {"status": "done", "order": 1}})
        self.trailer_on_main("gone")
        self.publish(sessions=[self.lane("session_landed", "gone"), self.lane("session_orphan", "ghost"),
                               self.lane("session_a", "c1")])
        _, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        _, detail = self.row(out, self.ROW)
        self.assertIn("session_a (c1; topic -)", detail, out)
        self.assertIn("session_landed (gone; topic -)", detail, out)
        self.assertIn("hold (", detail, out)
        self.assertIn("; lane session_orphan)", detail, out)
        self.assertNotIn("unknown (", detail, out)

    def test_empty_record_reads_one_whole_read_unknown_and_holds_no_lane(self):
        # A record branch with no step files cannot judge any lane, so the whole list reads one unknown entry. The lane
        # names cs-step:x, which the per-lane reading holds. The scope check runs first: the record has no step file.
        git(self.repo, "rm", "-rq", "roadmap/data/steps")
        git(self.repo, "commit", "-q", "-m", "drop every step")
        self.assertEqual(list((self.data / "steps").glob("*.json")), [], "the record still has step files")
        self.publish(sessions=[self.lane("session_x", "x")])
        entries = self.reported()
        self.assertEqual(entries, ["unknown (the record branch has no steps)"], entries)

    def test_failed_second_trailer_read_reads_one_whole_read_unknown_and_no_hold(self):
        # landed_marks reads the Step trailers once, and that read succeeds. The lane's absent step makes idle_lanes read
        # them again, and that read fails. The list cannot be judged, so it is one whole-read unknown, not a hold on the lane.
        self.land({"c1": {"status": "done", "order": 1}})
        self.publish(sessions=[self.lane("session_orphan", "ghost")])
        real = build.step_trailers
        reads = []

        def second_read_fails(repo, ref):
            reads.append(ref)
            return real(repo, ref) if len(reads) == 1 else None

        with mock.patch.object(build, "step_trailers", side_effect=second_read_fails):
            entries = self.reported()
        self.assertGreaterEqual(len(reads), 2, "the Step trailers were read %d time(s), so no second read ran" % len(reads))
        self.assertEqual(len(entries), 1, entries)
        self.assertTrue(entries[0].startswith("unknown (the Step trailers on"), entries)
        self.assertEqual([e for e in entries if e.startswith("hold (")], [], entries)

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

    def test_upkeep_row_lists_a_superseded_lane_as_merge_idle_lanes_does(self):
        # The control is session_a, done and idle, which both list. session_s is on c4, todo with no Step trailer on main,
        # so only its closed pull's replacedBy (#8, merged) lists it. The upkeep row must list it too. Its work is not on
        # main, so the landed rows must not name c4: they read marks from the merged rows only.
        self.land({"c1": {"status": "done", "order": 1}, "c4": {"status": "todo", "order": 4}})
        head = self.off_main()
        self.publish(sessions=[self.idle_lane("session_a", "c1"), self.idle_lane("session_s", "c4")],
                     landed=[self.pull_row(7, "lane/c4", head=head, merged=False, replacedBy=8),
                             self.pull_row(8, "batch-7", head=head, merged=True)])
        reported = self.reported()
        self.assertIn("session_s", self.ids(reported),
                      "scope: merge --idle-lanes does not list the superseded lane: %r" % (reported,))
        _, out = self.build_from_main("--live", str(self.live), expect=(0, 1))
        entries = self.entries(self.row(out, self.ROW)[1])
        self.assertIn("session_s", self.ids(entries),
                      "the lanes-to-archive row does not list the superseded lane that merge --idle-lanes lists:\n%s" % out)
        self.assertEqual(self.ids(entries), self.ids(reported),
                         "the lanes-to-archive row and merge --idle-lanes list different lanes: %r" % (entries,))
        closing = self.entries(self.row(out, "landed, waiting for triage to close")[1])
        self.assertFalse([e for e in closing if e.startswith("c4 (")],
                         "the landed row names c4, whose work is not on main: %r" % (closing,))

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

    def test_completed_lane_landed_only_by_a_landed_pull_row_is_listed(self):
        # session_a's step is doing with no Step trailer on main, so only its landedPulls row proves it landed.
        # session_b is the control: its step is done.
        self.land({"c1": {"status": "doing", "order": 1}, "c2": {"status": "done", "order": 2}})
        self.no_trailer_on_main()
        self.publish(sessions=[self.lane("session_a", "c1"), self.lane("session_b", "c2")],
                     landed=[self.pull_row(12, "lane/c1", merged=True)])
        count, entries = self.archive()
        self.assertEqual((count, self.ids(entries)), (2, ["session_a", "session_b"]),
                         "the completed lane on the landed step is listed beside the done one: %r" % (entries,))
        self.assertEqual(self.ids(build.idle_lanes_report(self.repo, str(self.live))), ["session_a", "session_b"],
                         "the merge tool's read lists the same lanes")

    def test_page_row_carries_hold_for_a_tagged_lane_whose_handoff_is_not_on_the_record_branch(self):
        # The untagged lane is the control: its entry reads as it does today. The tagged lane's handoff is not on the
        # record branch, so its entry carries the HOLD flag that merge --idle-lanes prints.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        self.publish(sessions=[self.lane("session_t", "c1", tags=("cs-archive-ready:alpha",)),
                               self.lane("session_u", "c2")])
        _, entries = self.archive()
        self.assertEqual(self.ids(entries), ["session_t", "session_u"], entries)
        self.assertIn("session_u (c2; topic -)", entries)
        held = [entry for entry in entries if entry.startswith("session_t ")]
        self.assertEqual(len(held), 1, entries)
        self.assertIn("HOLD: handoff alpha is not on the record branch", held[0])

    JOINT_PAIR = {"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}}

    def publish_joint_pair(self, tag):
        """session_t on c1 carrying `tag`, and the untagged control session_u on c2, each held only by a stale draft.
        A case lands JOINT_PAIR first."""
        self.publish(sessions=[self.idle_lane("session_t", "c1", tags=(tag,)), self.idle_lane("session_u", "c2")],
                     pulls=[self.stale_pull(101, "lane/c1"), self.stale_pull(102, "lane/c2")])

    def test_joint_lane_tagged_archive_ready_with_no_handoff_on_the_record_branch_is_held(self):
        # The control joint line reads as it does with no tag. The tagged lane's joint line takes the same HOLD flag a
        # plain lane's entry takes when its handoff is not on the record branch.
        self.land(self.JOINT_PAIR)
        self.publish_joint_pair("cs-archive-ready:alpha")
        self.assertEqual(self.reported(), sorted([
            self.JOINT % (101, "lane/c1", "session_t") + " HOLD: handoff alpha is not on the record branch",
            self.JOINT % (102, "lane/c2", "session_u")]),
            "a joint lane tagged cs-archive-ready with no handoff on the record branch lost its HOLD flag")

    def test_joint_lane_tagged_archive_ready_with_its_handoff_on_the_record_branch_keeps_the_plain_joint_line(self):
        # The handoff is on the record branch, so the check passes and the joint line reads as it does with no tag.
        self.land(self.JOINT_PAIR)
        self.commit_handoff("alpha")
        listed = subprocess.run(["git", "-C", str(self.repo), "ls-tree", "-r", "--name-only", "roadmap"],
                                capture_output=True, text=True).stdout.splitlines()
        self.assertIn(build.IDLE_HANDOFF % "alpha", listed, "scope: the handoff is not on the record branch")
        self.publish_joint_pair("cs-archive-ready:alpha")
        self.assertEqual(self.reported(), sorted([
            self.JOINT % (101, "lane/c1", "session_t"),
            self.JOINT % (102, "lane/c2", "session_u")]),
            "a joint lane whose handoff is on the record branch did not keep the plain joint line")

    def test_joint_lane_tagged_archive_ready_with_a_bad_slug_reads_unknown_not_joint(self):
        # Each slug is one a plain lane reads unknown: empty, a `/`, `..`, a line break. Each reads session_t unknown,
        # not its joint line; the untagged control joint line still prints.
        self.land(self.JOINT_PAIR)
        for slug in ("", "a/b", "..", "a\nb"):
            with self.subTest(slug=slug):
                self.publish_joint_pair("cs-archive-ready:" + slug)
                self.assertEqual(self.reported(), sorted([
                    "unknown (archive slug %r is not a plain name; lane session_t)" % slug,
                    self.JOINT % (102, "lane/c2", "session_u")]),
                    "a joint lane tagged cs-archive-ready with slug %r printed its joint line, not unknown" % slug)

    def test_completed_lane_with_a_doing_step_under_it_is_held_not_archived(self):
        # c1 is the lane's own step, landed. c2 is still doing and names this lane, so nothing else owns it: the lane reads
        # a hold line that names c2, and no archive line. session_b is the listed control.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "doing", "order": 2, "lane": "session_a"},
                   "c3": {"status": "done", "order": 3}})
        self.publish(sessions=[self.lane("session_a", "c1"), self.lane("session_b", "c3")])
        steps, marks = self.steps_and_marks()
        self.assertEqual(steps["c2"].get("lane"), "session_a", "scope: c2 does not name session_a")
        self.assertNotIn("c2", marks, "scope: c2 reads as landed, so it is not a step still doing")
        entries = self.idle_direct()
        self.assertTrue(self.line_for(entries, "session_a").startswith("hold (step c2 "),
                        "a completed lane with a doing step still under it was archived, not held: %r" % (entries,))
        self.assertEqual(entries, [self.DOING_HOLD % ("c2", "session_a"), "session_b (c3; topic -)"],
                         "the doing-step hold line is not the pinned text")

    def test_completed_lane_with_an_active_step_under_it_is_held_not_archived(self):
        # The same shape with status active. The hold wording is the spec's one line, so it still reads "still doing".
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "active", "order": 2, "lane": "session_a"},
                   "c3": {"status": "done", "order": 3}})
        self.publish(sessions=[self.lane("session_a", "c1"), self.lane("session_b", "c3")])
        steps, marks = self.steps_and_marks()
        self.assertEqual((steps["c2"].get("status"), steps["c2"].get("lane")), ("active", "session_a"),
                         "scope: c2 is not an active step under session_a")
        self.assertNotIn("c2", marks, "scope: c2 reads as landed, so it is not a step still open")
        entries = self.idle_direct()
        self.assertTrue(self.line_for(entries, "session_a").startswith("hold (step c2 "),
                        "a completed lane with an active step still under it was archived, not held: %r" % (entries,))
        self.assertEqual(entries, [self.DOING_HOLD % ("c2", "session_a"), "session_b (c3; topic -)"],
                         "the doing-step hold line is not the pinned text")

    def test_two_doing_steps_under_a_completed_lane_are_one_hold_line_naming_both_sorted(self):
        # c2 and c3 are doing under session_a, and their order fields run the other way, so the hold line must sort by
        # step id, not by order. session_b is the listed control.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "doing", "order": 3, "lane": "session_a"},
                   "c3": {"status": "doing", "order": 2, "lane": "session_a"}, "c4": {"status": "done", "order": 4}})
        self.publish(sessions=[self.lane("session_a", "c1"), self.lane("session_b", "c4")])
        steps, marks = self.steps_and_marks()
        self.assertEqual([k for k in sorted(steps) if steps[k].get("lane") == "session_a" and k not in marks], ["c2", "c3"],
                         "scope: the two doing steps under session_a are not both open")
        entries = self.idle_direct()
        self.assertTrue(self.line_for(entries, "session_a").startswith("hold (step c2 c3 "),
                        "two doing steps under a completed lane did not read as one sorted hold line: %r" % (entries,))
        self.assertEqual(entries, [self.DOING_HOLD % ("c2 c3", "session_a"), "session_b (c4; topic -)"],
                         "the doing-step hold line is not the pinned text")

    def test_doing_step_under_another_session_does_not_hold_this_lane(self):
        # c2 is doing under session_other, which has no live row here. session_a is archived as it is today.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "doing", "order": 2, "lane": "session_other"}})
        self.publish(sessions=[self.lane("session_a", "c1")])
        steps, marks = self.steps_and_marks()
        self.assertEqual(steps["c2"].get("lane"), "session_other", "scope: c2 does not name session_other")
        self.assertNotIn("c2", marks, "scope: c2 reads as landed, so the lane is not held by a landed step")
        self.assertEqual(self.idle_direct(), ["session_a (c1; topic -)"],
                         "a doing step under another session changed this lane's archive line")

    def test_completed_lane_with_no_doing_step_under_it_is_archived_unchanged(self):
        # c2 names this lane and is done, not doing, so no step is still open under it. session_a is archived as today.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2, "lane": "session_a"}})
        self.publish(sessions=[self.lane("session_a", "c1")])
        steps, _marks = self.steps_and_marks()
        self.assertEqual(steps["c2"].get("status"), "done", "scope: c2 is not done, so it is not the control")
        self.assertEqual(self.idle_direct(), ["session_a (c1; topic -)"],
                         "a done step under a completed lane changed its archive line")

    def test_doing_step_under_a_lane_landed_by_a_step_trailer_on_main_does_not_hold_it(self):
        # c2 still reads doing on the record, but a Step trailer on main lands it, so it is not still open under the lane.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "doing", "order": 2, "lane": "session_a"}})
        self.trailer_on_main("c2")
        self.publish(sessions=[self.lane("session_a", "c1")])
        steps, marks = self.steps_and_marks()
        self.assertIn("c2", marks, "scope: the Step trailer on main did not land c2")
        self.assertEqual(self.idle_direct(), ["session_a (c1; topic -)"],
                         "a doing step that a Step trailer on main landed still held its lane")

    def test_lane_waiting_on_its_own_step_a_pull_or_an_item_gets_no_line_under_a_doing_step(self):
        # Each lane waits on one thing: its own step c1 still doing, an open pull on lane/c2, or an open item on c3. Each
        # has a doing step under it (c1, c4, c5, c6), so a hold check placed before a wait check shows a line here.
        # session_b is the listed control.
        self.land({"c1": {"status": "doing", "order": 1, "lane": "session_own"},
                   "c2": {"status": "done", "order": 2}, "c3": {"status": "done", "order": 3},
                   "c4": {"status": "doing", "order": 4, "lane": "session_own"},
                   "c5": {"status": "doing", "order": 5, "lane": "session_pull"},
                   "c6": {"status": "doing", "order": 6, "lane": "session_item"},
                   "c7": {"status": "done", "order": 7}})
        self.publish(sessions=[self.lane("session_own", "c1"), self.lane("session_pull", "c2"),
                               self.lane("session_item", "c3"), self.lane("session_b", "c7")],
                     pulls=[{"number": 61, "title": "lane c2", "branch": "lane/c2"}],
                     items=[self.item(1, home="step c3", status="open", lane="c3")])
        steps, marks = self.steps_and_marks()
        under = {"session_own": ("c1", "c4"), "session_pull": ("c5",), "session_item": ("c6",)}
        for sid, ks in under.items():
            for k in ks:
                self.assertEqual((steps[k].get("lane"), k in marks), (sid, False),
                                 "scope: %s is not a doing step still open under %s" % (k, sid))
        entries = self.idle_direct()
        self.assertEqual(self.line_for(entries, "session_b"), "session_b (c7; topic -)", entries)
        for sid, wait in (("session_own", "its own step c1 still doing"), ("session_pull", "an open pull on lane/c2"),
                          ("session_item", "an open page item on c3")):
            with self.subTest(lane=sid, wait=wait):
                self.assertEqual([e for e in entries if sid in e], [],
                                 "a lane waiting on %s got a line under its doing steps: %r" % (wait, entries))

    def test_a_done_or_todo_step_under_a_lane_id_does_not_hold_it(self):
        # c8 is done and c9 is todo, and each names session_a. Only a doing step holds a lane, so session_a is archived as
        # today. session_b is the listed control.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2},
                   "c8": {"status": "done", "order": 8, "lane": "session_a"},
                   "c9": {"status": "todo", "order": 9, "lane": "session_a"}})
        self.publish(sessions=[self.lane("session_a", "c1"), self.lane("session_b", "c2")])
        steps, _marks = self.steps_and_marks()
        self.assertEqual([(steps[k].get("status"), steps[k].get("lane")) for k in ("c8", "c9")],
                         [("done", "session_a"), ("todo", "session_a")],
                         "scope: c8 and c9 do not read done and todo under session_a")
        self.assertEqual(self.idle_direct(), ["session_a (c1; topic -)", "session_b (c2; topic -)"],
                         "a done or todo step under session_a changed the lane's archive line")

    def test_doing_step_with_a_padded_lane_id_holds_its_lane(self):
        # c2 is doing, and its lane field is " session_a" with a leading space. The lane is session_a, so c2 holds it.
        # session_b is the listed control.
        self.land({"c1": {"status": "done", "order": 1},
                   "c2": {"status": "doing", "order": 2, "lane": " session_a"},
                   "c3": {"status": "done", "order": 3}})
        self.publish(sessions=[self.lane("session_a", "c1"), self.lane("session_b", "c3")])
        steps, marks = self.steps_and_marks()
        self.assertEqual(steps["c2"].get("lane"), " session_a", "scope: c2 does not carry the padded lane id")
        self.assertNotIn("c2", marks, "scope: c2 reads as landed, so it is not a step still doing")
        entries = self.idle_direct()
        self.assertEqual(self.line_for(entries, "session_b"), "session_b (c3; topic -)", entries)
        line = self.line_for(entries, "session_a")
        self.assertTrue(line.startswith("hold (step c2 ") and line.endswith("; lane session_a)"),
                        "a doing step with a padded lane id did not hold its lane: %r" % line)

    def test_doing_step_with_a_capitalised_status_holds_its_lane(self):
        # c2 reads "Doing", capitalised. The status is the word doing in any casing, so c2 holds session_a.
        # session_b is the listed control.
        self.land({"c1": {"status": "done", "order": 1},
                   "c2": {"status": "Doing", "order": 2, "lane": "session_a"},
                   "c3": {"status": "done", "order": 3}})
        self.publish(sessions=[self.lane("session_a", "c1"), self.lane("session_b", "c3")])
        steps, marks = self.steps_and_marks()
        self.assertEqual(steps["c2"].get("status"), "Doing", "scope: c2 does not read Doing")
        self.assertNotIn("c2", marks, "scope: c2 reads as landed, so it is not a step still doing")
        entries = self.idle_direct()
        self.assertEqual(self.line_for(entries, "session_b"), "session_b (c3; topic -)", entries)
        line = self.line_for(entries, "session_a")
        self.assertTrue(line.startswith("hold (step c2 ") and line.endswith("; lane session_a)"),
                        "a doing step with a capitalised status did not hold its lane: %r" % line)

    def test_doing_step_with_a_padded_status_holds_its_lane(self):
        # c2 reads " doing " with a space on each side. The status is the word doing with the spaces trimmed, so c2 holds
        # session_a. session_b is the listed control.
        self.land({"c1": {"status": "done", "order": 1},
                   "c2": {"status": " doing ", "order": 2, "lane": "session_a"},
                   "c3": {"status": "done", "order": 3}})
        self.publish(sessions=[self.lane("session_a", "c1"), self.lane("session_b", "c3")])
        steps, marks = self.steps_and_marks()
        self.assertEqual(steps["c2"].get("status"), " doing ", "scope: c2 does not read \" doing \"")
        self.assertNotIn("c2", marks, "scope: c2 reads as landed, so it is not a step still doing")
        entries = self.idle_direct()
        self.assertEqual(self.line_for(entries, "session_b"), "session_b (c3; topic -)", entries)
        line = self.line_for(entries, "session_a")
        self.assertTrue(line.startswith("hold (step c2 ") and line.endswith("; lane session_a)"),
                        "a doing step with a padded status did not hold its lane: %r" % line)

    def test_done_or_todo_in_any_casing_under_a_lane_does_not_hold_it(self):
        # The control for the casing cases. "Done", "DONE", "TODO" and "Todo" are not the word doing, so each names
        # session_a and holds nothing. session_a is archived as today. session_b is the listed control.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2},
                   "c8": {"status": "Done", "order": 8, "lane": "session_a"},
                   "c9": {"status": "DONE", "order": 9, "lane": "session_a"},
                   "c10": {"status": "TODO", "order": 10, "lane": "session_a"},
                   "c11": {"status": "Todo", "order": 11, "lane": "session_a"}})
        self.publish(sessions=[self.lane("session_a", "c1"), self.lane("session_b", "c2")])
        steps, _marks = self.steps_and_marks()
        self.assertEqual([(steps[k].get("status"), steps[k].get("lane")) for k in ("c8", "c9", "c10", "c11")],
                         [("Done", "session_a"), ("DONE", "session_a"), ("TODO", "session_a"), ("Todo", "session_a")],
                         "scope: the cased done and todo steps do not read under session_a")
        self.assertEqual(self.idle_direct(), ["session_a (c1; topic -)", "session_b (c2; topic -)"],
                         "a done or todo step in another casing changed session_a's archive line")

    def test_the_doing_hold_line_names_the_way_out_as_todo_or_done(self):
        # A hold a doing step causes must say how the lane is released: set the step's status to todo or done.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "doing", "order": 2, "lane": "session_a"}})
        self.publish(sessions=[self.lane("session_a", "c1")])
        steps, marks = self.steps_and_marks()
        self.assertEqual((steps["c2"].get("status"), steps["c2"].get("lane")), ("doing", "session_a"),
                         "scope: c2 is not a doing step under session_a")
        self.assertNotIn("c2", marks, "scope: c2 reads as landed, so it is not a step still doing")
        line = self.line_for(self.idle_direct(), "session_a")
        self.assert_held(line, "session_a")
        self.assertIn("set the step's status to todo or done", line,
                      "the doing-step hold line does not say how to clear it: %r" % line)

    def test_a_lane_only_a_stale_draft_holds_prints_one_joint_line(self):
        # The lane is idle 13 h, has no unarchived commit, and its only holder is one draft 13 h old with its head off main.
        # Today such a lane waits and prints nothing. The joint line names the draft, its branch and the lane.
        self.land({"c1": {"status": "done", "order": 1}})
        self.publish(sessions=[self.idle_lane("session_a", "c1")], pulls=[self.stale_pull(101, "lane/c1")])
        self.assertEqual(self.reported(), [self.JOINT % (101, "lane/c1", "session_a")],
                         "a lane whose only holder is a stale draft printed no joint line")

    def test_every_stale_draft_of_one_lane_is_named_on_its_one_joint_line(self):
        self.land({"c1": {"status": "done", "order": 1}})
        self.publish(sessions=[self.idle_lane("session_a", "c1")],
                     pulls=[self.stale_pull(101, "lane/c1"), self.stale_pull(102, "c1")])
        entries = self.reported()
        self.assertEqual(len(entries), 1, "a lane with two stale drafts printed %d lines, not one: %r" % (len(entries), entries))
        line = entries[0]
        self.assertTrue(line.startswith("joint (close ") and line.endswith("; archive lane session_a)"), line)
        self.assertEqual(sorted(re.findall(r"#(\d+)", line)), ["101", "102"], line)
        self.assertEqual(sorted(re.findall(r"archive/(\S+?)[ ;]", line)), ["c1", "lane/c1"], line)

    def test_each_joint_lane_has_its_own_line_sorted_with_the_plain_lanes(self):
        # session_c is idle with its idle fields set but no pull: the empty case, which must read as a plain line.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2},
                   "c3": {"status": "done", "order": 3}})
        self.publish(sessions=[self.idle_lane("session_a", "c1"), self.idle_lane("session_b", "c2"),
                               self.idle_lane("session_c", "c3")],
                     pulls=[self.stale_pull(101, "lane/c1"), self.stale_pull(102, "lane/c2")])
        self.assertEqual(self.reported(), sorted([self.JOINT % (101, "lane/c1", "session_a"),
                                                  self.JOINT % (102, "lane/c2", "session_b"),
                                                  "session_c (c3; topic -)"]),
                         "two joint lanes and one plain lane did not print one line each, sorted")

    def test_thirty_two_stale_draft_lanes_each_get_one_joint_line_in_sorted_order(self):
        # The full-size case: the row a long idle backlog reads, one joint line per lane.
        self.land({"L%02d" % n: {"status": "done", "order": n} for n in range(1, 33)})
        self.publish(sessions=[self.idle_lane("session_%02d" % n, "L%02d" % n) for n in range(1, 33)],
                     pulls=[self.stale_pull(200 + n, "lane/L%02d" % n) for n in range(1, 33)])
        self.assertEqual(self.reported(), sorted(self.JOINT % (200 + n, "lane/L%02d" % n, "session_%02d" % n)
                                                 for n in range(1, 33)))

    def test_a_stale_draft_the_batch_runner_holds_gets_no_joint_line(self):
        # session_b is the control: the same stale draft, unheld, prints the line. session_c's draft carries held false
        # and reviewLog false, which hold nothing, so it prints too. session_a's held draft waits silently.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2},
                   "c3": {"status": "done", "order": 3}})
        self.publish(sessions=[self.idle_lane("session_a", "c1"), self.idle_lane("session_b", "c2"),
                               self.idle_lane("session_c", "c3")],
                     pulls=[self.stale_pull(101, "lane/c1", held=True), self.stale_pull(102, "lane/c2"),
                            self.stale_pull(103, "c3", held=False, reviewLog=False)])
        entries = self.reported()
        self.assertEqual(len(self.joint_for(entries, "session_b")), 1, "control: the unheld stale draft printed no joint line")
        self.assertEqual(len(self.joint_for(entries, "session_c")), 1, "a draft with held false printed no joint line")
        self.assertEqual(self.joint_for(entries, "session_a"), [], "a draft the batch runner holds printed a joint line")

    def test_a_stale_draft_with_a_posted_review_log_gets_no_joint_line(self):
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        self.publish(sessions=[self.idle_lane("session_a", "c1"), self.idle_lane("session_b", "c2")],
                     pulls=[self.stale_pull(101, "lane/c1", reviewLog=True), self.stale_pull(102, "lane/c2")])
        entries = self.reported()
        self.assertEqual(len(self.joint_for(entries, "session_b")), 1, "control: the stale draft without a review log printed no joint line")
        self.assertEqual(self.joint_for(entries, "session_a"), [], "a draft with a posted review log printed a joint line")

    def test_a_stale_draft_with_no_head_sha_gets_no_joint_line(self):
        # The ruling: a stale draft with no head sha gets no joint line, and its lane keeps waiting, as it does today.
        # The head is missing, null or empty in turn. session_b is the control: its draft has a head and prints the line.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        for head in (_ABSENT, None, ""):
            with self.subTest(head=head):
                self.publish(sessions=[self.idle_lane("session_a", "c1"), self.idle_lane("session_b", "c2")],
                             pulls=[self.stale_pull(101, "lane/c1", head=head), self.stale_pull(102, "lane/c2")])
                entries = self.reported()
                self.assertEqual(len(self.joint_for(entries, "session_b")), 1,
                                 "control: the stale draft with a head printed no joint line")
                self.assertEqual(self.joint_for(entries, "session_a"), [],
                                 "a stale draft with no head sha printed a joint line")
                self.assertNotIn("session_a (c1; topic -)", entries,
                                 "a stale draft with no head sha released its lane as a plain line")

    def test_a_stale_draft_on_a_step_a_live_row_of_another_session_holds_gets_no_joint_line(self):
        # session_c works on s1 under its own row, so s1 is live on another session and the stale draft on s1 is not the
        # lane's alone. session_b is the control.
        self.land({"s1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        working = session_row("session_c", "SESSION_STATUS_RUNNING", "cs-build:lane", "cs-step:s1", self.REPO,
                              status_bucket=BUCKET_WORKING)
        self.publish(sessions=[self.idle_lane("session_a", "s1", idle_since=self.created_before(26 * 60)), working,
                               self.idle_lane("session_b", "c2")],
                     pulls=[self.stale_pull(101, "s1", hours=25), self.stale_pull(102, "lane/c2")])
        steps, _marks = self.steps_and_marks()
        self.assertEqual(steps["s1"].get("status"), "done", "scope: s1 is not done")
        self.assertIn("s1", build.live_work(str(self.live), steps, self.SLUG)["liveSteps"],
                      "scope: no live row holds s1, so the other session does not hold it")
        entries = self.reported()
        self.assertEqual(len(self.joint_for(entries, "session_b")), 1, "control: the lane with no live row on its step printed no joint line")
        self.assertEqual(self.joint_for(entries, "session_a"), [],
                         "a stale draft on a step another session's live row holds printed a joint line")

    def test_a_stale_draft_beside_a_doing_step_already_in_marks_gets_no_joint_line(self):
        # The doing step `it` is under the lane, and a merged pull (landedPulls) puts it in marks, so it reads landed but
        # not done. Any doing step holds the lane, and the draft titled for it names that step. session_b is the control.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2},
                   "it": {"status": "doing", "order": 3, "lane": "session_a"}})
        self.publish(sessions=[self.idle_lane("session_a", "c1"), self.idle_lane("session_b", "c2")],
                     pulls=[self.stale_pull(101, "lane/c1", title="it follow-up"), self.stale_pull(102, "lane/c2")],
                     landed=[self.pull_row(2800, "it", merged=True)])
        steps, _marks = self.steps_and_marks()
        self.assertEqual((steps["it"].get("status"), steps["it"].get("lane")), ("doing", "session_a"),
                         "scope: it is not a doing step under session_a")
        work = build.live_work(str(self.live), steps, self.SLUG)
        self.assertEqual(build.pull_landed_marks(self.repo, build.main_ref(self.repo, "main"), steps, work), {"it": ["#2800"]},
                         "scope: the merged pull does not put it in marks")
        entries = self.reported()
        self.assertEqual(len(self.joint_for(entries, "session_b")), 1, "control: the lane with no doing step printed no joint line")
        self.assertEqual(self.joint_for(entries, "session_a"), [],
                         "a doing step under the lane, already in marks, did not hold the lane off its joint line")

    def test_a_stale_draft_beside_a_ready_pull_on_a_lane_suffix_gets_no_joint_line(self):
        # lane/c1-r2 is a lane pull by the guard's rule (_on_lane_form counts lane/<slug>-*), and it is ready, not a draft.
        # session_b is the control.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        self.publish(sessions=[self.idle_lane("session_a", "c1"), self.idle_lane("session_b", "c2")],
                     pulls=[self.stale_pull(101, "lane/c1"), self.stale_pull(103, "lane/c1-r2", draft=False),
                            self.stale_pull(102, "lane/c2")])
        self.assertTrue(guard_merge._on_lane_form("lane/c1-r2", ["c1"]), "scope: the guard does not count lane/c1-r2 as c1's pull")
        entries = self.reported()
        self.assertEqual(len(self.joint_for(entries, "session_b")), 1, "control: the stale draft with no suffix pull printed no joint line")
        self.assertEqual(self.joint_for(entries, "session_a"), [],
                         "a stale draft beside a ready lane/<slug>-r2 pull printed a joint line")

    def test_a_stale_draft_whose_head_is_not_a_full_sha_gets_no_joint_line(self):
        # A head is the full 40 hex digits. session_b has one, the control, and prints the line. A 40-hex head on the
        # draft prints it too, which the last step checks.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        for head in ("xyz", "e" * 39):
            with self.subTest(head=head):
                self.publish(sessions=[self.idle_lane("session_a", "c1"), self.idle_lane("session_b", "c2")],
                             pulls=[self.stale_pull(101, "lane/c1", head=head), self.stale_pull(102, "lane/c2")])
                entries = self.reported()
                self.assertEqual(len(self.joint_for(entries, "session_b")), 1, "control: a full-sha head printed no joint line")
                self.assertEqual(self.joint_for(entries, "session_a"), [], "a head of %r printed a joint line" % head)
        self.publish(sessions=[self.idle_lane("session_a", "c1")], pulls=[self.stale_pull(101, "lane/c1", head="e" * 40)])
        self.assertEqual(len(self.joint_for(self.reported(), "session_a")), 1,
                         "a 40-hex head on a stale draft printed no joint line")

    def test_a_stale_draft_naming_a_doing_step_already_in_marks_gets_no_joint_line(self):
        # `it` is doing and a merged pull puts it in marks (landedPulls), so it reads landed but not done. A draft that
        # names it is its live pull, not a stale one, and holds the lane. Two inputs: the step is doing under another
        # session, and the draft's title names it; or the step is this lane's own tag, with no lane field, and the draft
        # sits on its bare head ref. session_b is the control in both: a completed lane with its own stale draft.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        inputs = (
            # (label, the fields of `it`, the session_a row, its draft, the lane field `it` must read)
            ("a doing step under another session, titled for it",
             {"status": "doing", "order": 3, "lane": "session_other"},
             self.idle_lane("session_a", "c1"), self.stale_pull(101, "lane/c1", title="it follow-up"), "session_other"),
            ("a doing step with no lane field, on its bare head",
             {"status": "doing", "order": 3},
             self.idle_lane("session_a", "it"), self.stale_pull(101, "it"), None),
        )
        for label, it_fields, lane_a, draft_a, lane_field in inputs:
            with self.subTest(input=label):
                self.land({"it": it_fields})
                self.publish(sessions=[lane_a, self.idle_lane("session_b", "c2")],
                             pulls=[draft_a, self.stale_pull(102, "lane/c2")],
                             landed=[self.pull_row(2800, "it", merged=True)])
                steps, _marks = self.steps_and_marks()
                self.assertEqual((steps["it"].get("status"), steps["it"].get("lane")), ("doing", lane_field),
                                 "scope: it does not read doing with the lane field under test")
                work = build.live_work(str(self.live), steps, self.SLUG)
                self.assertEqual(build.pull_landed_marks(self.repo, build.main_ref(self.repo, "main"), steps, work),
                                 {"it": ["#2800"]}, "scope: the merged pull does not put it in marks")
                entries = self.reported()
                self.assertEqual(len(self.joint_for(entries, "session_b")), 1,
                                 "control: the lane with no doing step printed no joint line")
                self.assertEqual(self.joint_for(entries, "session_a"), [],
                                 "a draft naming a doing step already in marks printed a joint line")

    def test_a_review_ready_lane_is_not_held_by_its_own_stale_draft(self):
        # A review-ready lane is idle and not ended, so its own row is live. The draft check must leave that row out
        # (skip=sid), or the lane holds its own draft and never prints. session_b is the control: a completed lane.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        ready = self.lane("session_a", "c1", bucket=BUCKET_REVIEW_READY, idle_since=self.created_before(26 * 60), unarchived=0)
        self.publish(sessions=[ready, self.idle_lane("session_b", "c2")],
                     pulls=[self.stale_pull(101, "lane/c1", hours=25), self.stale_pull(102, "lane/c2")])
        steps, _marks = self.steps_and_marks()
        work = build.live_work(str(self.live), steps, self.SLUG)
        self.assertEqual(work["liveRows"].get("session_a"), ["c1"], "scope: the review-ready row does not hold c1")
        entries = self.reported()
        self.assertEqual(self.joint_for(entries, "session_b"), [self.JOINT % (102, "lane/c2", "session_b")],
                         "control: the completed lane with a stale draft printed no joint line")
        self.assertEqual(self.joint_for(entries, "session_a"), [self.JOINT % (101, "lane/c1", "session_a")],
                         "a review-ready lane's own live row held its own stale draft")

    def test_a_stale_draft_whose_title_names_a_doing_step_gets_no_joint_line(self):
        # c5 is doing and the draft's title names it, so the draft is the step's live PR, not a stale one. session_b is
        # the control: its draft names no doing step.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2},
                   "c5": {"status": "doing", "order": 5}})
        named = self.stale_pull(101, "lane/c1", title="Ruling 557 a home (c5)")
        steps, _marks = self.steps_and_marks()
        self.assertEqual(steps["c5"].get("status"), "doing", "scope: c5 is not a doing step")
        self.assertTrue(build.names_step(named, "c5"), "scope: the draft's title does not name c5")
        self.publish(sessions=[self.idle_lane("session_a", "c1"), self.idle_lane("session_b", "c2")],
                     pulls=[named, self.stale_pull(102, "lane/c2")])
        entries = self.reported()
        self.assertEqual(len(self.joint_for(entries, "session_b")), 1, "control: the unnamed stale draft printed no joint line")
        self.assertEqual(self.joint_for(entries, "session_a"), [], "a draft whose title names a doing step printed a joint line")

    def test_an_open_records_pull_gives_no_lane_a_joint_line(self):
        # The control is the lane alone. Then one open pull holding the word records, in its title or its branch, stops the
        # line for every lane, draft or not, as the pinned rule reads "any pull".
        self.land({"c1": {"status": "done", "order": 1}})
        self.publish(sessions=[self.idle_lane("session_a", "c1")], pulls=[self.stale_pull(101, "lane/c1")])
        self.assertEqual(self.reported(), [self.JOINT % (101, "lane/c1", "session_a")],
                         "control: the lane alone printed no joint line")
        cases = (("title", "Roadmap records for batch 110", "lane-batch-110", {}),
                 ("branch", "batch 110 rebuild", "records-batch-110", {}),
                 ("not a draft", "Batch 110 records", "lane-batch-111", {"draft": False}))
        for label, title, branch, fields in cases:
            with self.subTest(records=label):
                self.publish(sessions=[self.idle_lane("session_a", "c1")],
                             pulls=[self.stale_pull(101, "lane/c1"), self.stale_pull(120, branch, title=title, **fields)])
                self.assertEqual(self.reported(), [], "an open records pull (%s) did not stop the joint line" % label)

    def test_a_lane_with_an_unarchived_commit_gets_no_joint_line(self):
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        self.publish(sessions=[self.idle_lane("session_a", "c1"), self.idle_lane("session_b", "c2", unarchived=2)],
                     pulls=[self.stale_pull(101, "lane/c1"), self.stale_pull(102, "lane/c2")])
        entries = self.reported()
        self.assertEqual(len(self.joint_for(entries, "session_a")), 1, "control: the lane with no unarchived commit printed no joint line")
        self.assertEqual(self.joint_for(entries, "session_b"), [], "a lane with an unarchived commit printed a joint line")

    def test_unarchived_epoch_missing_or_not_an_int_gets_no_joint_line(self):
        # JSON false is a bool that Python reads as an int equal to 0, so a check that only tests isinstance(v, int) and
        # v == 0 lets it through. JSON true and a float 0.0 are the other shapes a check must refuse.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        for label, value in (("missing", _ABSENT), ("text", "0"), ("false", False), ("true", True), ("float", 0.0)):
            with self.subTest(unarchived=label):
                self.publish(sessions=[self.idle_lane("session_a", "c1"), self.idle_lane("session_b", "c2", unarchived=value)],
                             pulls=[self.stale_pull(101, "lane/c1"), self.stale_pull(102, "lane/c2")])
                entries = self.reported()
                self.assertEqual(len(self.joint_for(entries, "session_a")), 1,
                                 "control: the lane with unarchived_epoch 0 printed no joint line")
                self.assertEqual(self.joint_for(entries, "session_b"), [],
                                 "a lane whose unarchived_epoch is %s printed a joint line" % label)

    def test_a_lane_with_a_doing_step_among_its_tags_gets_no_joint_line(self):
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2},
                   "c3": {"status": "doing", "order": 3}})
        busy = self.idle_lane("session_a", "c1")
        busy["tags"].append("cs-step:c3")  # c3 is on the lane's tags and still doing, so the lane is not done
        self.publish(sessions=[busy, self.idle_lane("session_b", "c2")],
                     pulls=[self.stale_pull(101, "lane/c1"), self.stale_pull(102, "lane/c2")])
        steps, marks = self.steps_and_marks()
        self.assertEqual((steps["c3"].get("status"), "c3" in marks), ("doing", False), "scope: c3 is not an open step")
        entries = self.reported()
        self.assertEqual(len(self.joint_for(entries, "session_b")), 1, "control: the lane with no doing step printed no joint line")
        self.assertEqual(self.joint_for(entries, "session_a"), [], "a lane with a doing step on its tags printed a joint line")

    def test_a_doing_step_under_the_lane_holds_it_and_prints_no_joint_line(self):
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2},
                   "c3": {"status": "doing", "order": 3, "lane": "session_a"}})
        self.publish(sessions=[self.idle_lane("session_a", "c1"), self.idle_lane("session_b", "c2")],
                     pulls=[self.stale_pull(101, "lane/c1"), self.stale_pull(102, "lane/c2")])
        steps, marks = self.steps_and_marks()
        self.assertEqual((steps["c3"].get("lane"), "c3" in marks), ("session_a", False), "scope: c3 is not open under session_a")
        entries = self.reported()
        self.assertEqual(len(self.joint_for(entries, "session_b")), 1, "control: the lane with no doing step printed no joint line")
        self.assertEqual(self.joint_for(entries, "session_a"), [], "a lane with a doing step under it printed a joint line")
        self.assertIn(self.DOING_HOLD % ("c3", "session_a"), entries, "the doing-step hold line is missing: %r" % entries)

    def test_a_draft_under_twelve_hours_or_with_no_createdAt_gets_no_joint_line(self):
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        cases = (("under 12 h", self.stale_pull(101, "lane/c1", hours=5)),
                 ("no createdAt", self.stale_pull(101, "lane/c1", createdAt=_ABSENT)))
        for label, pull in cases:
            with self.subTest(draft=label):
                self.publish(sessions=[self.idle_lane("session_a", "c1"), self.idle_lane("session_b", "c2")],
                             pulls=[pull, self.stale_pull(102, "lane/c2")])
                entries = self.reported()
                self.assertEqual(len(self.joint_for(entries, "session_b")), 1, "control: the 13 h draft printed no joint line")
                self.assertEqual(self.joint_for(entries, "session_a"), [], "a draft (%s) printed a joint line" % label)

    def test_a_ready_pull_on_the_lane_gets_no_joint_line(self):
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        self.publish(sessions=[self.idle_lane("session_a", "c1"), self.idle_lane("session_b", "c2")],
                     pulls=[self.stale_pull(101, "lane/c1", draft=False), self.stale_pull(102, "lane/c2")])
        entries = self.reported()
        self.assertEqual(len(self.joint_for(entries, "session_b")), 1, "control: the stale draft printed no joint line")
        self.assertEqual(self.joint_for(entries, "session_a"), [], "a ready pull printed a joint line")

    def test_idle_since_under_twelve_hours_missing_or_without_a_zone_gets_no_joint_line(self):
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        no_zone = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=13)).strftime("%Y-%m-%dT%H:%M:%S")
        for label, since in (("5 h before the read", self.created_before(5 * 60)), ("missing", _ABSENT),
                             ("without a zone", no_zone)):
            with self.subTest(idle_since=label):
                self.publish(sessions=[self.idle_lane("session_a", "c1", idle_since=since), self.idle_lane("session_b", "c2")],
                             pulls=[self.stale_pull(101, "lane/c1"), self.stale_pull(102, "lane/c2")])
                entries = self.reported()
                self.assertEqual(len(self.joint_for(entries, "session_b")), 1, "control: the lane idle 13 h printed no joint line")
                self.assertEqual(self.joint_for(entries, "session_a"), [], "a lane with idle_since %s printed a joint line" % label)

    def test_a_draft_already_landed_on_main_lists_its_lane_plain_not_joint(self):
        # Such a draft releases its lane today, so the lane is listed as it always was. session_b is the control.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        self.publish(sessions=[self.idle_lane("session_a", "c1"), self.idle_lane("session_b", "c2")],
                     pulls=[self.stale_pull(101, "lane/c1", head=self.main_tip()), self.stale_pull(102, "lane/c2")])
        entries = self.reported()
        self.assertEqual(len(self.joint_for(entries, "session_b")), 1, "control: the stale draft printed no joint line")
        self.assertEqual(self.joint_for(entries, "session_a"), [], "a draft already landed on main printed a joint line")
        self.assertIn("session_a (c1; topic -)", entries, "the landed draft's lane is no longer listed as it was: %r" % entries)

    def test_an_open_page_item_on_the_lane_gives_no_joint_line(self):
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2}})
        self.publish(sessions=[self.idle_lane("session_a", "c1"), self.idle_lane("session_b", "c2")],
                     pulls=[self.stale_pull(101, "lane/c1"), self.stale_pull(102, "lane/c2")],
                     items=[self.item(1, home="step c1", status="open", lane="c1")])
        entries = self.reported()
        self.assertEqual(len(self.joint_for(entries, "session_b")), 1, "control: the lane with no open item printed no joint line")
        self.assertEqual(self.joint_for(entries, "session_a"), [], "a lane an open page item holds printed a joint line")

    def test_one_pull_that_is_not_a_stale_draft_stops_the_lanes_joint_line(self):
        # Lane A has its stale draft on lane/c1 and a second pull on c1 that is not a stale draft: held, a review log, under
        # 12 h, ready, or titled with a doing step. A joint line needs every pull on the lane to be stale, so lane A waits.
        # session_b is the control: its one stale draft prints the line.
        self.land({"c1": {"status": "done", "order": 1}, "c2": {"status": "done", "order": 2},
                   "c5": {"status": "doing", "order": 5}})
        second = (("held", self.stale_pull(102, "c1", held=True)),
                  ("a review log", self.stale_pull(102, "c1", reviewLog=True)),
                  ("under 12 h", self.stale_pull(102, "c1", hours=5)),
                  ("ready", self.stale_pull(102, "c1", draft=False)),
                  ("titled with a doing step", self.stale_pull(102, "c1", title="Ruling 557 a home (c5)")))
        for label, extra in second:
            with self.subTest(second_pull=label):
                self.publish(sessions=[self.idle_lane("session_a", "c1"), self.idle_lane("session_b", "c2")],
                             pulls=[self.stale_pull(101, "lane/c1"), extra, self.stale_pull(103, "lane/c2")])
                entries = self.reported()
                self.assertEqual(len(self.joint_for(entries, "session_b")), 1,
                                 "control: the lane with one stale draft printed no joint line")
                self.assertEqual(self.joint_for(entries, "session_a"), [],
                                 "a lane with a %s pull on it printed a joint line" % label)

    def test_a_lane_whose_absent_step_has_a_trailer_on_main_gets_a_joint_line(self):
        # ghost is on no record branch, so it counts as landed only by its Step trailer on main. Its lane is judged as a
        # lane of landed steps is, and the stale draft on lane/ghost gives the joint line. session_a is the control.
        self.land({"c1": {"status": "done", "order": 1}})
        self.trailer_on_main("ghost")
        self.publish(sessions=[self.idle_lane("session_g", "ghost"), self.idle_lane("session_a", "c1")],
                     pulls=[self.stale_pull(101, "lane/ghost"), self.stale_pull(102, "lane/c1")])
        steps, _marks = self.steps_and_marks()
        self.assertNotIn("ghost", steps, "scope: ghost is on the record branch")
        self.assertIn("ghost", [t[0] for t in build.step_trailers(self.repo, "main")], "scope: no Step trailer names ghost on main")
        entries = self.reported()
        self.assertEqual(len(self.joint_for(entries, "session_a")), 1, "control: the lane of a done step printed no joint line")
        self.assertEqual(self.joint_for(entries, "session_g"), [self.JOINT % (101, "lane/ghost", "session_g")],
                         "a lane whose absent step has a Step trailer on main printed no joint line")

    def test_the_joint_pass_starts_no_process_and_opens_no_file(self):
        # Two parts. Process starts: every git read goes through build._nowindow.run, so a count of its calls is the count
        # of process starts. The joint lane is read once as it is, and once with its idle_since left out, which stops the
        # joint decision and leaves the rest of the read; equal counts show the decision starts none of its own. Files:
        # live_work reads the live file once, before the decision, so the decision on that built work opens no path.
        self.land({"c1": {"status": "done", "order": 1}})
        self.publish(sessions=[self.idle_lane("session_a", "c1")], pulls=[self.stale_pull(101, "lane/c1")])
        before = self.tree()
        starts = []
        real_run = build._nowindow.run

        def counted(*args, **kwargs):
            starts.append(args)
            return real_run(*args, **kwargs)

        with mock.patch.object(build._nowindow, "run", side_effect=counted):
            joint = self.reported()
        self.assertEqual(joint, [self.JOINT % (101, "lane/c1", "session_a")], "control: the joint lane printed no joint line")
        self.assertEqual(self.tree(), before, "the joint read wrote or changed a file")
        joint_starts = len(starts)
        self.publish(sessions=[self.idle_lane("session_a", "c1", idle_since=_ABSENT)],
                     pulls=[self.stale_pull(101, "lane/c1")])
        starts.clear()
        with mock.patch.object(build._nowindow, "run", side_effect=counted):
            plain = self.reported()
        self.assertEqual(plain, [], "scope: the lane with no idle_since is not joint and prints nothing")
        self.assertEqual(joint_starts, len(starts), "the joint decision starts %d process(es) of its own" % (joint_starts - len(starts)))
        self.publish(sessions=[self.idle_lane("session_a", "c1")], pulls=[self.stale_pull(101, "lane/c1")])
        steps, marks = self.steps_and_marks()
        work = build.live_work(str(self.live), steps, self.SLUG)
        opened = []
        real_open = io.open

        def recorded(file, *args, **kwargs):
            if isinstance(file, (str, os.PathLike)):  # subprocess opens its pipes by descriptor, an int, and is no path
                opened.append(os.fspath(file))
            return real_open(file, *args, **kwargs)

        with mock.patch("io.open", side_effect=recorded), mock.patch("builtins.open", side_effect=recorded):
            decided = build.idle_lanes(work, steps, marks, self.SLUG, self.repo)
        self.assertEqual(decided, [self.JOINT % (101, "lane/c1", "session_a")],
                         "control: the decision on the built work printed no joint line")
        self.assertEqual(opened, [], "the joint decision opened %r" % (opened,))


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


def load_built_index():
    """tests/built_index.py as a module: the page fixture's script, loaded by path because tests/ is not a package."""
    spec = importlib.util.spec_from_file_location("built_index", HERE / "tests" / "built_index.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BuiltIndexEnv(unittest.TestCase):
    """The page fixture's build child (tests/built_index.py) gets no GitHub token, as Fixture.setUp gives its cases none."""

    def build_children(self, caller):
        """[(argv, env, url)], one per build child that built_index.main() starts under the caller's variables. env is
        the environment the child runs with; url is the origin of the fixture repo it reads."""
        built = load_built_index()
        seen = []

        def fake_run(argv, **kw):
            # A child given no env inherits this process's environment, so the copy is taken at the call. The origin is
            # read with test_build.git, not the hooks' git helper: that one shares the module this case patches.
            env = dict(kw["env"]) if kw.get("env") is not None else dict(os.environ)
            repo = argv[argv.index("--repo") + 1]
            seen.append((list(argv), env, git(repo, "remote", "get-url", "origin").strip()))
            pathlib.Path(argv[argv.index("--out") + 1]).write_text("<html></html>", encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0, "", "")

        with mock.patch.dict(os.environ), mock.patch.object(built._nowindow, "run", side_effect=fake_run), \
                mock.patch.object(sys, "argv", ["built_index.py"]), \
                mock.patch.object(sys, "stdout", io.TextIOWrapper(io.BytesIO(), encoding="utf-8")):
            for key in TOKEN_VARS:
                os.environ.pop(key, None)
            os.environ.update(caller)
            built.main()
        return seen

    def test_one_build_child_runs_build_py_on_a_repo_with_a_github_name(self):
        # The control: the fixture repo names the GitHub repo that a token would reach, so the leak below is real.
        seen = self.build_children({"GH_TOKEN": "dummy"})
        self.assertEqual(len(seen), 1, "built_index.py starts %d build children, not one" % len(seen))
        argv, _, url = seen[0]
        self.assertEqual(os.path.basename(argv[1]), "build.py", "the build child is not build.py: %r" % (argv,))
        self.assertIn(load_built_index().GITHUB, url, "the fixture repo's origin names no GitHub repo, so no read would reach GitHub")

    def test_the_build_child_gets_no_github_token(self):
        for caller in ({}, {"GH_TOKEN": "dummy"}, {"GITHUB_TOKEN": "dummy"}, {"GH_TOKEN": "dummy", "GITHUB_TOKEN": "dummy"}):
            with self.subTest(caller=sorted(caller)):
                seen = self.build_children(caller)
                self.assertEqual(len(seen), 1, "built_index.py starts %d build children, not one" % len(seen))
                env = seen[0][1]
                self.assertEqual([k for k in TOKEN_VARS if k in env], [],
                                 "the build child runs with a GitHub token, so the page build reads GitHub's open pulls")

    def test_the_build_child_keeps_the_other_caller_variables(self):
        # The control for the strip: a fix that hands the child an empty environment fails here, not in the token cases.
        with mock.patch.dict(os.environ, {"ROADMAP_FIXTURE_KEEP": "kept"}):
            seen = self.build_children({"GH_TOKEN": "dummy"})
        self.assertEqual(len(seen), 1, "built_index.py starts %d build children, not one" % len(seen))
        self.assertEqual(seen[0][1].get("ROADMAP_FIXTURE_KEEP"), "kept", "the build child lost the caller's other variables")


if __name__ == "__main__":
    unittest.main()
