#!/usr/bin/env python3
"""Fixture suite for `merge --priority-rows FILE` (merge/merge.py): the wake's read of each tracked-priority row.

Run: python3 merge/test_priority_rows.py

WHAT IT PROVES. The command prints one line per row, then a summary, and exits 0 only when every row is ok, waiting or done.
A row names its pull request by `pr: owner/repo#N` or by `branch: name`. A row that names neither is flagged with no read.
A closed pull request that did not merge is flagged, never done. A draft, a dirty head and a red newest run are flagged. A
pending run is waiting. A read that fails, a row on another repo and a merge state GitHub has not computed are unknown, never
ok. Cost: a pr: row makes at most two reads (its pull request, and the runs on its head only when the verdict needs them). A
branch: row adds one shared read of the open pull requests per wake, read to its last page. A row with neither makes none.
Malformed and non-priority lines are unknown; comment and blank lines are skipped. The mode writes nothing and takes no lock.

Each case runs merge.py as a subprocess in a checkout whose origin is github.com/shivinate7/claude-settings, with a fake gh on
PATH. The fake answers `gh api` reads and `gh run list` from a state file that the case writes. Its REST answers come from the
library of merge/test_merge.py (GH_REST_LIB), imported and not copied. The control case reads the same fixture through the
tool's own Host in-process, so the fixture is shown to say what the case means.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

HERE = pathlib.Path(__file__).resolve().parent
MERGE = HERE / "merge.py"
sys.path.insert(0, str(HERE.parent / "skills" / "roadmap"))
sys.path.insert(1, str(HERE.parent / "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per test run (lint/_test_temp.py)
import test_build as roadmap  # noqa: E402  the roadmap fixture: make_repo, GIT_ENV, git (one home)
import test_merge as tm  # noqa: E402  GH_REST_LIB, the REST answers of the fake gh, and pull/list_item (one home); its TestCases are not collected here
import merge  # noqa: E402  the tool itself, for the in-process control case

REPO = "shivinate7/claude-settings"
ORIGIN = "git@github.com:shivinate7/claude-settings.git"
SLUG = "ci-speed-stack-4"
ROW_3302 = "priority: %s | pr: %s#3302\n" % (SLUG, REPO)
SHA_A, SHA_B = "a" * 40, "b" * 40  # the head of #3302 before its push, and after it
# The routes the tool reads, as the fake logs them: METHOD repo/route. A runs read is the REST route or `gh run list`.
PULLS = REPO + "/pulls"
PULL_3302 = REPO + "/pulls/3302"
RUN_READS = (REPO + "/actions/runs", REPO + "/run-list")
VERDICT_WORDS = re.compile(r"[a-z]+")

# Made in setUpModule, not at import, so a helper that imports this file leaks no folder.
RUN_FOLDER = None


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


# The fake gh. It answers `gh api` from state.json in FAKE_GH_DIR, and logs one line per call: METHOD repo/route params.
# Its header block for `-i` has gh's shape: the status line, the headers, a blank line, then the body.
DISPATCH = r'''
S = json.load(open(os.path.join(os.environ["FAKE_GH_DIR"], "state.json")))
RUN_FIELDS = ("name", "status", "conclusion", "databaseId", "workflowDatabaseId", "headSha")

def note(line):
    open(os.path.join(os.environ["FAKE_GH_DIR"], "calls.log"), "a").write(line + "\n")

def send(text, link=None, include=False):
    head = ""
    if include:
        head = "HTTP/2.0 200 OK\r\nContent-Type: application/json; charset=utf-8\r\n" + ("Link: %s\r\n" % link if link else "") + "\r\n"
    sys.stdout.buffer.write((head + text + "\n").encode("utf-8"))
    sys.exit(0)

def run_list(a):
    commit = a[a.index("--commit") + 1]
    repo = a[a.index("-R") + 1] if "-R" in a else S["repo"]
    note("GET %s/run-list commit=%s" % (repo, commit))
    if repo != S["repo"]:
        print("fake gh: no repository %s" % repo)
        sys.exit(1)
    if S.get("runs_fail"):
        print(S["runs_fail"])
        sys.exit(1)
    fields = a[a.index("--json") + 1].split(",")
    bad = [f for f in fields if f not in RUN_FIELDS]
    if bad:
        print('Unknown JSON field: "%s"' % bad[0])
        sys.exit(1)
    runs = S["runs"].get(commit, [])
    send(json.dumps([{f: r.get(f) for f in fields} for r in runs]))

def api(a):
    method, path, params, flags, jq = parse(a[1:])
    include = "include" in flags
    m = re.match(r"^repos/(\{owner\}/\{repo\}|[^/{}]+/[^/{}]+)(?:/(.*))?$", path)
    if not m:
        raise Refused(api_error(404, "Not Found"))
    repo = S["repo"] if m.group(1) == "{owner}/{repo}" else m.group(1)
    rel = m.group(2) or ""
    note("%s %s/%s%s" % (method, repo, rel, "".join(" %s=%s" % kv for kv in sorted(params.items()))))
    if repo != S["repo"]:
        raise Refused(api_error(404, "Not Found"))
    pull = re.fullmatch(r"pulls/(\d+)", rel)
    if method == "GET" and pull:
        spec = S["pulls"].get(pull.group(1))
        if spec is None or "gone" in spec:
            raise Refused(api_error(404, "Not Found"))
        send(one(spec["pull"], jq), include=include)
    if method == "GET" and rel == "pulls":
        if S.get("open_fail"):
            raise Refused(api_error(404, "Not Found"))
        items = S["open"]
        size = max(1, min(int(params.get("per_page", 30)), 100))
        last = max(1, -(-len(items) // size))
        n = int(params.get("page", 1))
        link = '<https://api.github.com/repos/%s/pulls?page=%d>; rel="next"' % (repo, n + 1) if include and n < last else None
        send(listing(items, None, params, flags, jq, 100), link=link, include=include)
    if method == "GET" and rel == "actions/runs":
        if S.get("runs_fail"):
            raise Refused(api_error(404, "Not Found"))
        runs = S["runs"].get(params.get("head_sha", ""), [])
        send(listing(runs, "workflow_runs", params, flags, jq, 100, top={"total_count": len(runs)}), include=include)
    raise Refused(api_error(404, "Not Found"))

try:
    if sys.argv[1:2] == ["api"]:
        api(sys.argv[1:])
    elif sys.argv[1:3] == ["run", "list"]:
        run_list(sys.argv[1:])
    else:
        note("UNROUTED " + " ".join(sys.argv[1:]))
        print("fake gh: only `gh api` and `gh run list` are answered")
        sys.exit(1)
except Refused as e:
    print(e.text)
    sys.exit(e.code)
'''

FAKE_GH = "#!/usr/bin/env python3\nimport json, os, re, sys\n" + tm.GH_REST_LIB + DISPATCH
REST = tm.REST  # the REST library's names (pull, list_item), as the fake gh and the other suites read them


def run_for(sha, name, status, conclusion, run_id):
    """One workflow run on `sha`, in the fields both reads answer."""
    return {"name": name, "status": status, "conclusion": conclusion, "databaseId": run_id,
            "workflowDatabaseId": 100 + run_id, "headSha": sha}


def green(sha):
    return [run_for(sha, "checks", "completed", "success", 2)]


def pull_for(n, head, **fields):
    """The pull request `GET pulls/N` returns: its head branch is feat-N, into main."""
    return REST.pull(n, head, "feat-%d" % n, "main", **fields)


def words(line):
    return set(VERDICT_WORDS.findall(line.lower()))


class PriorityRowsCli(unittest.TestCase):
    """merge --priority-rows against one checkout whose origin is shivinate7/claude-settings, with the fake gh on PATH."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=RUN_FOLDER)
        self.repo = roadmap.make_repo(self.tmp.name)
        roadmap.git(self.repo, "remote", "add", "origin", ORIGIN)
        self.bin = pathlib.Path(self.tmp.name) / "bin"
        self.bin.mkdir()
        tm.put_shim(str(self.bin / "gh"), FAKE_GH)
        self.state_dir = pathlib.Path(self.tmp.name) / "ghstate"
        self.state_dir.mkdir()
        self.rows_file = pathlib.Path(self.tmp.name) / "rows.txt"
        self.reset_state()

    def tearDown(self):
        self.tmp.cleanup()

    def reset_state(self):
        """No pull requests, no open ones and no runs: the state a case then fills in."""
        self.state = {"repo": REPO, "pulls": {}, "open": [], "runs": {}}
        self.save()

    def save(self):
        (self.state_dir / "state.json").write_text(json.dumps(self.state), encoding="utf-8")

    def put_pr(self, n, head, runs=(), **fields):
        """Pull request n at head `head`: its GET pulls/N answer, and the runs on that head, newest first."""
        self.state["pulls"][str(n)] = {"pull": pull_for(n, head, **fields)}
        self.state["runs"][head] = list(runs)
        self.save()

    def put_open(self, *rows):
        """The open pull requests the list read answers: (number, head, branch) rows, in the order given."""
        self.state["open"] = [REST.list_item(n, head, branch, "main") for n, head, branch in rows]
        self.save()

    def env(self):
        env = _test_git.apply({**os.environ, **roadmap.GIT_ENV})
        env["PATH"] = str(self.bin) + os.pathsep + os.environ.get("PATH", "")
        env["FAKE_GH_DIR"] = str(self.state_dir)
        return env

    def run_mode(self, source, stdin_text=None):
        """The mode on `source`, a path or `-` with `stdin_text`. -> (exit code, stdout, stderr)."""
        done = subprocess.run([sys.executable, str(MERGE), "--priority-rows", source], cwd=str(self.repo), capture_output=True,
                              text=True, env=self.env(), input=stdin_text, timeout=120)
        return done.returncode, done.stdout, done.stderr

    def wake(self, rows, stdin=False):
        """One wake: the rows as a file, or on stdin when `stdin`. -> (exit code, stdout, stderr)."""
        self.rows_file.write_text(rows, encoding="utf-8")
        return self.run_mode("-" if stdin else str(self.rows_file), rows if stdin else None)

    def calls(self):
        """The fake gh's calls of the last wake, one line each, oldest first."""
        log = self.state_dir / "calls.log"
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []

    def paths(self):
        """The route of each call of the last wake: `<repo>/<route>`, the query and fields left out."""
        return [line.split()[1] for line in self.calls()]

    def reset_calls(self):
        (self.state_dir / "calls.log").unlink(missing_ok=True)

    def row_line(self, out, err, slug):
        """The one line that names row `slug`. Its count is checked first, so a verdict is read from one line only."""
        lines = [line for line in (out + err).splitlines() if slug in line]
        self.assertEqual(len(lines), 1, "want one line for row %s, got %d:\n--- stdout\n%s--- stderr\n%s" % (slug, len(lines), out, err))
        return lines[0]

    def assert_flag(self, line, *reasons):
        w = words(line)
        self.assertIn("flag", w, "want a flag on this line: " + line)
        for reason in reasons:
            self.assertIn(reason, line, "want the reason %r on this line: %s" % (reason, line))

    def assert_ok(self, line):
        w = words(line)
        self.assertIn("ok", w, "want ok on this line: " + line)
        self.assertNotIn("flag", w, "ok names a flag: " + line)
        self.assertNotIn("unknown", w, "ok names unknown: " + line)

    def assert_unknown(self, line):
        w = words(line)
        self.assertIn("unknown", w, "want unknown on this line: " + line)
        self.assertNotIn("ok", w, "unknown must never read as ok: " + line)

    def test_the_3302_wakes_flag_draft_then_draft_and_dirty_then_pass_when_ready_and_green(self):
        self.put_pr(3302, SHA_A, runs=green(SHA_A), draft=True, mergeable=True, mergeable_state="clean")
        code, out, err = self.wake(ROW_3302)
        line = self.row_line(out, err, SLUG)
        self.assert_flag(line, "draft")
        self.assertEqual(code, 1, "a flagged row exits 1: " + err)

        self.put_pr(3302, SHA_A, runs=green(SHA_A), draft=True, mergeable=False, mergeable_state="dirty")
        code, out, err = self.wake(ROW_3302)
        line = self.row_line(out, err, SLUG)
        self.assert_flag(line, "draft", "dirty")
        self.assertEqual(code, 1, "a flagged row exits 1: " + err)

        self.put_pr(3302, SHA_B, runs=green(SHA_B), draft=False, mergeable=True, mergeable_state="clean")
        code, out, err = self.wake(ROW_3302)
        line = self.row_line(out, err, SLUG)
        self.assert_ok(line)
        self.assertEqual(code, 0, "an ok row exits 0: " + err)

    def test_an_outbox_row_with_steps_and_a_pr_list_but_no_pr_or_branch_token_is_flagged(self):
        self.put_pr(3302, SHA_A, runs=green(SHA_A), draft=True, mergeable=True, mergeable_state="clean")
        rows = "priority: %s | steps: priority-vs-merge-order, priority-table-reads-pr | PRs: #3302 draft, #3303 merged\n" % SLUG
        code, out, err = self.wake(rows)
        line = self.row_line(out, err, SLUG)
        self.assert_flag(line, "row names no branch or pr")
        self.assertEqual(code, 1, "a flagged row exits 1: " + err)
        self.assertEqual(self.paths(), [], "a row with no branch and no pr reads nothing")

    def test_a_merged_pr_is_done_even_when_github_reports_no_mergeable_state(self):
        self.put_pr(3302, SHA_A, runs=green(SHA_A), state="closed", merged=True, mergeable=None, mergeable_state="unknown")
        code, out, err = self.wake(ROW_3302)
        line = self.row_line(out, err, SLUG)
        self.assertIn("done", words(line), "want done on this line: " + line)
        self.assertEqual(code, 0, "a done row exits 0: " + err)

    def test_a_closed_pr_that_did_not_merge_is_flagged_and_never_done(self):
        self.put_pr(3302, SHA_A, runs=green(SHA_A), state="closed", merged=False, mergeable=None, mergeable_state="unknown")
        code, out, err = self.wake(ROW_3302)
        line = self.row_line(out, err, SLUG)
        self.assert_flag(line, "closed, not on main")
        self.assertNotIn("done", words(line), "a replaced or closed pull request is not done: " + line)
        self.assertEqual(code, 1, "a flagged row exits 1: " + err)

    def test_a_failed_read_is_unknown_and_never_clear(self):
        def pull_read_fails():
            self.put_pr(3302, SHA_A, runs=green(SHA_A), mergeable=True, mergeable_state="clean")
            self.state["pulls"]["3302"] = {"gone": True}
            self.save()

        def runs_read_fails():
            self.put_pr(3302, SHA_A, runs=green(SHA_A), mergeable=True, mergeable_state="clean")
            self.state["runs_fail"] = "HTTP 404: Not Found"
            self.save()

        for name, setup in {"the pull request read fails": pull_read_fails, "the runs read fails": runs_read_fails}.items():
            with self.subTest(read=name):
                self.reset_state()
                setup()
                code, out, err = self.wake(ROW_3302)
                line = self.row_line(out, err, SLUG)
                self.assert_unknown(line)
                self.assertEqual(code, 1, "an unknown row exits 1: " + err)

    def test_a_failed_open_list_read_is_unknown_for_a_branch_row(self):
        self.put_open((41, SHA_A, "feat-x"))
        self.state["open_fail"] = True
        self.save()
        code, out, err = self.wake("priority: %s | branch: feat-x\n" % SLUG)
        line = self.row_line(out, err, SLUG)
        self.assert_unknown(line)
        self.assertEqual(code, 1, "an unknown row exits 1: " + err)

    def test_a_row_naming_another_repo_is_unknown_and_its_repo_is_never_read(self):
        code, out, err = self.wake("priority: other-repo-step | pr: someone/else#12\n")
        line = self.row_line(out, err, "other-repo-step")
        self.assert_unknown(line)
        self.assertEqual(code, 1, "an unknown row exits 1: " + err)
        self.assertFalse([c for c in self.calls() if "someone/else" in c], "a repo the session cannot read is not read: %s" % self.calls())

    def test_a_merge_state_github_has_not_computed_is_unknown_and_never_clean(self):
        cases = {
            "mergeable and merge state unknown": dict(mergeable=None, mergeable_state="unknown"),
            "merge state unknown beside a mergeable flag": dict(mergeable=True, mergeable_state="unknown"),
        }
        for name, fields in cases.items():
            with self.subTest(state=name):
                self.reset_state()
                self.put_pr(3302, SHA_A, runs=green(SHA_A), **fields)
                code, out, err = self.wake(ROW_3302)
                line = self.row_line(out, err, SLUG)
                self.assert_unknown(line)
                self.assertEqual(code, 1, "an unknown row exits 1: " + err)

    def test_a_draft_is_flagged_whatever_its_merge_state(self):
        cases = {
            "a clean merge state": dict(mergeable=True, mergeable_state="clean"),
            "GitHub's draft merge state": dict(mergeable=True, mergeable_state="draft"),
        }
        for name, fields in cases.items():
            with self.subTest(state=name):
                self.reset_state()
                self.put_pr(3302, SHA_A, runs=green(SHA_A), draft=True, **fields)
                code, out, err = self.wake(ROW_3302)
                line = self.row_line(out, err, SLUG)
                self.assert_flag(line, "draft")
                self.assertNotIn("unknown", words(line), "a draft has a known state: " + line)
                self.assertEqual(code, 1, "a flagged row exits 1: " + err)

    def test_a_dirty_ready_head_is_flagged(self):
        self.put_pr(3302, SHA_A, runs=green(SHA_A), mergeable=False, mergeable_state="dirty")
        code, out, err = self.wake(ROW_3302)
        line = self.row_line(out, err, SLUG)
        self.assert_flag(line, "dirty")
        self.assertEqual(code, 1, "a flagged row exits 1: " + err)

    def test_a_red_newest_run_is_flagged(self):
        runs = [run_for(SHA_A, "checks", "completed", "failure", 3), run_for(SHA_A, "checks", "completed", "success", 2)]
        self.put_pr(3302, SHA_A, runs=runs, mergeable=True, mergeable_state="clean")
        code, out, err = self.wake(ROW_3302)
        line = self.row_line(out, err, SLUG)
        self.assert_flag(line, "checks")
        self.assertEqual(code, 1, "a flagged row exits 1: " + err)

    def test_the_newest_run_of_a_name_decides_not_an_older_one(self):
        runs = [run_for(SHA_A, "checks", "completed", "success", 3), run_for(SHA_A, "checks", "completed", "failure", 2)]
        self.put_pr(3302, SHA_A, runs=runs, mergeable=True, mergeable_state="clean")
        code, out, err = self.wake(ROW_3302)
        line = self.row_line(out, err, SLUG)
        self.assert_ok(line)
        self.assertEqual(code, 0, "an ok row exits 0: " + err)

    def test_a_pending_run_is_waiting_and_exits_zero(self):
        runs = [run_for(SHA_A, "checks", "in_progress", None, 4)]
        self.put_pr(3302, SHA_A, runs=runs, mergeable=True, mergeable_state="clean")
        code, out, err = self.wake(ROW_3302)
        line = self.row_line(out, err, SLUG)
        self.assertIn("waiting", words(line), "want waiting on this line: " + line)
        self.assertEqual(code, 0, "a waiting row exits 0: " + err)

    def test_a_branch_row_resolves_through_the_open_list(self):
        self.put_open((41, SHA_A, "feat-x"))
        self.put_pr(41, SHA_A, runs=green(SHA_A), mergeable=True, mergeable_state="clean")
        code, out, err = self.wake("priority: %s | branch: feat-x\n" % SLUG)
        line = self.row_line(out, err, SLUG)
        self.assert_ok(line)
        self.assertEqual(code, 0, "an ok row exits 0: " + err)

    def test_a_branch_with_no_open_pr_is_flagged(self):
        self.put_open((41, SHA_A, "feat-other"))
        code, out, err = self.wake("priority: %s | branch: feat-gone\n" % SLUG)
        line = self.row_line(out, err, SLUG)
        self.assert_flag(line, "feat-gone")
        self.assertEqual(code, 1, "a flagged row exits 1: " + err)

    def test_the_open_list_is_read_to_its_last_page_for_a_branch_row(self):
        rows = [(n, "%040x" % n, "filler-%d" % n) for n in range(1, 101)] + [(150, SHA_A, "feat-deep")]
        self.put_open(*rows)
        self.put_pr(150, SHA_A, runs=green(SHA_A), mergeable=True, mergeable_state="clean")
        code, out, err = self.wake("priority: %s | branch: feat-deep\n" % SLUG)
        line = self.row_line(out, err, SLUG)
        self.assert_ok(line)
        self.assertEqual(code, 0, "an ok row exits 0: " + err)
        self.assertEqual(self.paths().count(PULLS), 2, "101 open pull requests are two pages, read once each: %s" % self.paths())

    def test_an_open_clean_pr_row_costs_exactly_two_reads(self):
        self.put_pr(3302, SHA_A, runs=green(SHA_A), mergeable=True, mergeable_state="clean")
        code, out, err = self.wake(ROW_3302)
        self.row_line(out, err, SLUG)
        self.assertEqual(code, 0, "an ok row exits 0: " + err)
        paths = self.paths()
        self.assertEqual(paths.count(PULL_3302), 1, "one read of the pull request: %s" % paths)
        self.assertEqual(sum(p in RUN_READS for p in paths), 1, "one read of the runs on its head: %s" % paths)
        self.assertEqual(len(paths), 2, "an open clean pr row costs exactly two reads: %s" % paths)

    def test_two_branch_rows_share_one_open_list_read_and_a_no_branch_row_reads_nothing(self):
        self.put_open((3302, SHA_A, "feat-x"), (3303, SHA_B, "feat-y"))
        self.put_pr(3302, SHA_A, runs=green(SHA_A), mergeable=True, mergeable_state="clean")
        self.put_pr(3303, SHA_B, runs=green(SHA_B), mergeable=True, mergeable_state="clean")
        self.put_pr(9, "9" * 40, runs=green("9" * 40), mergeable=True, mergeable_state="clean")
        rows = ("priority: step-a | branch: feat-x\n"
                "priority: step-b | branch: feat-y\n"
                "priority: step-c | pr: %s#9\n"
                "priority: step-d | steps: none\n") % REPO
        code, out, err = self.wake(rows)
        for slug in ("step-a", "step-b", "step-c"):
            self.assert_ok(self.row_line(out, err, slug))
        self.assert_flag(self.row_line(out, err, "step-d"), "row names no branch or pr")
        self.assertEqual(code, 1, "the flagged row exits 1: " + err)
        paths = self.paths()
        self.assertEqual(paths.count(PULLS), 1, "the open list is read once per wake: %s" % paths)
        self.assertEqual(len(paths), 1 + 2 * 3, "one list read, then two reads for each of the three rows that name a PR: %s" % paths)

    def test_the_wake_writes_nothing_and_leaves_the_checkout_as_it_was(self):
        self.put_open((3302, SHA_A, "feat-x"))
        self.put_pr(3302, SHA_A, runs=green(SHA_A), mergeable=True, mergeable_state="clean")
        rows = "priority: step-a | branch: feat-x\npriority: step-b | pr: %s#3302\n" % REPO
        before = self.snapshot()
        code, out, err = self.wake(rows)
        self.row_line(out, err, "step-a")
        self.row_line(out, err, "step-b")
        self.assertEqual(code, 0, "both rows are ok, so the wake exits 0: " + err)
        self.assertTrue(self.calls(), "the wake read something")
        writes = [c for c in self.calls() if not c.startswith("GET ")]
        self.assertEqual(writes, [], "a wake sends no write, so it takes no lock")
        self.assertEqual(self.snapshot(), before, "the wake leaves no local file in the checkout")

    def snapshot(self):
        found = {}
        for base, dirs, files in os.walk(self.repo):
            dirs[:] = [d for d in dirs if d != ".git"]
            for name in files:
                path = os.path.join(base, name)
                found[os.path.relpath(path, self.repo)] = pathlib.Path(path).read_bytes()
        return found

    def test_another_repo_row_is_unknown_beside_a_local_pr_with_the_same_number(self):
        self.put_pr(12, SHA_A, runs=green(SHA_A), mergeable=True, mergeable_state="clean")
        code, out, err = self.wake("priority: other-repo-step | pr: someone/else#12\n")
        line = self.row_line(out, err, "other-repo-step")
        self.assert_unknown(line)
        self.assertEqual(code, 1, "an unknown row exits 1: " + err)
        reads = self.paths()
        self.assertNotIn(REPO + "/pulls/12", reads, "the row names another repo's #12, so the local #12 is never read")
        self.assertFalse(set(reads) & set(RUN_READS), "the local #12 gets no run read either: %s" % reads)

    def test_a_ready_clean_head_with_no_run_is_unknown_never_ok(self):
        self.put_pr(3302, SHA_A, runs=(), mergeable=True, mergeable_state="clean")
        code, out, err = self.wake(ROW_3302)
        line = self.row_line(out, err, SLUG)
        self.assert_unknown(line)
        self.assertEqual(code, 1, "an unknown row exits 1: " + err)

    def test_a_behind_pr_is_flagged_behind_its_base(self):
        self.put_pr(3302, SHA_A, runs=green(SHA_A), mergeable=True, mergeable_state="behind")
        code, out, err = self.wake(ROW_3302)
        line = self.row_line(out, err, SLUG)
        self.assert_flag(line, "behind base")
        self.assertEqual(code, 1, "a flagged row exits 1: " + err)

    def test_no_rows_exits_one_and_says_no_rows(self):
        cases = {"an empty file": "", "a file of comments and blank lines": "# nothing for this wake\n\n", "a missing file": None}
        for name, text in cases.items():
            with self.subTest(source=name):
                if text is None:
                    code, out, err = self.run_mode(str(pathlib.Path(self.tmp.name) / "missing.txt"))
                else:
                    self.rows_file.write_text(text, encoding="utf-8")
                    code, out, err = self.run_mode(str(self.rows_file))
                self.assertIn("no rows", out + err, "want the words no rows: " + out + err)
                self.assertEqual(code, 1, "no rows exits 1, never clear: " + err)

    def test_two_open_prs_on_one_branch_are_unknown_never_one_of_them(self):
        self.put_open((41, SHA_A, "feat-x"), (42, SHA_B, "feat-x"))
        self.put_pr(41, SHA_A, runs=green(SHA_A), mergeable=True, mergeable_state="clean")
        self.put_pr(42, SHA_B, runs=green(SHA_B), mergeable=True, mergeable_state="clean")
        code, out, err = self.wake("priority: %s | branch: feat-x\n" % SLUG)
        line = self.row_line(out, err, SLUG)
        self.assert_unknown(line)
        self.assertEqual(code, 1, "an unknown row exits 1: " + err)

    def test_a_malformed_pr_value_is_unknown_never_ok(self):
        self.put_pr(3302, SHA_A, runs=green(SHA_A), mergeable=True, mergeable_state="clean")
        for value in ("%s#3302x" % REPO, REPO, "3302", "%s#" % REPO):
            with self.subTest(pr=value):
                code, out, err = self.wake("priority: %s | pr: %s\n" % (SLUG, value))
                line = self.row_line(out, err, SLUG)
                self.assert_unknown(line)
                self.assertEqual(code, 1, "an unknown row exits 1: " + err)

    def test_a_line_without_the_priority_prefix_is_unknown(self):
        self.put_pr(3302, SHA_A, runs=green(SHA_A), mergeable=True, mergeable_state="clean")
        code, out, err = self.wake("%s | pr: %s#3302\n" % (SLUG, REPO))
        line = self.row_line(out, err, SLUG)
        self.assert_unknown(line)
        self.assertEqual(code, 1, "an unknown row exits 1: " + err)

    def test_comment_and_blank_lines_are_skipped_and_name_no_row(self):
        self.put_pr(3302, SHA_A, runs=green(SHA_A), mergeable=True, mergeable_state="clean")
        self.put_pr(9, SHA_B, runs=green(SHA_B), mergeable=True, mergeable_state="clean")
        rows = ("# the owner's priorities for this wake\n"
                "\n"
                "   \n"
                "# priority: old-step | pr: %s#9\n"
                "priority: %s | pr: %s#3302\n") % (REPO, SLUG, REPO)
        code, out, err = self.wake(rows)
        line = self.row_line(out, err, SLUG)
        self.assert_ok(line)
        self.assertEqual(code, 0, "the one row is ok, so the wake exits 0: " + err)
        self.assertIn("of 1 rows", out + err, "only the priority row counts")
        self.assertNotIn("old-step", out + err, "a commented row is no row")
        self.assertNotIn(REPO + "/pulls/9", self.paths(), "a commented row is never read")

    def test_a_blocked_or_unstable_head_with_every_run_green_is_ok(self):
        for state in ("blocked", "unstable"):
            with self.subTest(merge_state=state):
                self.reset_state()
                self.put_pr(3302, SHA_A, runs=green(SHA_A), mergeable=True, mergeable_state=state)
                code, out, err = self.wake(ROW_3302)
                line = self.row_line(out, err, SLUG)
                self.assert_ok(line)
                self.assertEqual(code, 0, "an ok row exits 0: " + err)

    def test_stdin_dash_reads_the_rows_as_the_file_does(self):
        self.put_pr(3302, SHA_A, runs=green(SHA_A), mergeable=True, mergeable_state="clean")
        code, out, err = self.wake(ROW_3302, stdin=True)
        line = self.row_line(out, err, SLUG)
        self.assert_ok(line)
        self.assertEqual(code, 0, "an ok row exits 0: " + err)

    def test_control_the_tools_own_host_reads_this_fixture_as_the_cases_mean_it(self):
        """Green on the old code too. The fixture's draft-and-dirty shape and its green run come back through the tool's own Host."""
        self.put_pr(3302, SHA_A, runs=green(SHA_A), draft=True, mergeable=False, mergeable_state="dirty")
        patch = unittest.mock.patch.dict(os.environ, {"PATH": self.env()["PATH"], "FAKE_GH_DIR": str(self.state_dir)})
        with patch:
            host = merge.Host(cwd=str(self.repo))
            info = host.pr(3302)
            red, pending = merge.Host.judge_runs(host.runs(info["head"]))
        self.assertEqual(info["head"], SHA_A, "the head the fixture names")
        self.assertTrue(info["draft"], "the fixture is a draft")
        self.assertEqual(info["mergeable"], "CONFLICTING", "mergeable false reads as conflicting")
        self.assertEqual(info["merge_state"], "DIRTY", "the dirty merge state comes through")
        self.assertEqual((red, pending), ([], []), "the green run reads as green")


if __name__ == "__main__":
    unittest.main()
