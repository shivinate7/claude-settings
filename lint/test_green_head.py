#!/usr/bin/env python3
"""CLI tests for the reader of a pull request's newest earlier green head (.github/scripts/green-head.sh).

The reader prints one line: the head sha of the newest earlier `checks` run of the pull request, when that run concluded
success and its `scope` and `all-jobs-passed` jobs did too. Every other case prints one empty line and exits 0.

Each case serves canned REST JSON through a stub `gh` on PATH, so no case reaches GitHub. Inputs (env): REPO, PR, HEAD_SHA,
GH_TOKEN. CI_GREEN_HEAD overrides the script path. The stub answers `gh api` by its arguments: a path with
`/actions/runs/<id>/jobs` gets that run's job list, and any other `gh api` call gets the run list. It honours `--jq FILTER`
through jq, so the reader may parse the JSON either way.

Each negative case first checks that the green fixture prints its sha, so an empty line means the case's own cause.

Run with:  python3 lint/test_green_head.py -v
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  rm_tree removes the run folder

SCRIPT = os.environ.get("CI_GREEN_HEAD") or os.path.join(HERE, "..", ".github", "scripts", "green-head.sh")
BASH = shutil.which("bash")
REPO = "shivinate7/claude-settings"
PR = "7"
HEAD_SHA = "aa" * 20
GREEN_SHA = "bb" * 20
MIDDLE_SHA = "cc" * 20
# This module's run folder (test-temp-standard). read() makes its case folders under it; the module teardown removes it.
RUN_DIR = None

STUB = r"""#!/bin/sh
# Stub gh for lint/test_green_head.py. Answers `gh api` from the canned files in $GH_STUB_DIR. Never reaches GitHub.
d="$GH_STUB_DIR"
if [ -e "$d/fail" ]; then echo "gh: HTTP 500 (stub)" >&2; exit 1; fi
filter=""
prev=""
for a in "$@"; do
  if [ "$prev" = "--jq" ]; then filter="$a"; fi
  prev="$a"
done
id=$(printf '%s\n' "$*" | sed -n 's#.*/actions/runs/\([0-9][0-9]*\)/jobs.*#\1#p')
if [ -n "$id" ]; then src="$d/jobs-$id.json"; else src="$d/runs.json"; fi
if [ -n "$filter" ]; then exec jq -r "$filter" < "$src"; fi
exec cat "$src"
"""


def setUpModule():
    global RUN_DIR
    RUN_DIR = _test_temp.run_folder()


def tearDownModule():
    tracked_tree.rm_tree(RUN_DIR)


def checks_run(run_id, head_sha, conclusion="success", status="completed", created="2026-11-14T15:00:00Z"):
    """One `checks` workflow run, as the runs endpoint lists it."""
    return {"id": run_id, "name": "checks", "event": "pull_request", "head_sha": head_sha,
            "head_branch": "ci-scope-records-only-push", "pull_requests": [{"number": int(PR)}],
            "status": status, "conclusion": conclusion, "created_at": created}


def jobs(scope="success", passed="success"):
    """The job list of one run: its `scope` job and its `all-jobs-passed` job, with their conclusions."""
    return {"jobs": [{"name": "scope", "status": "completed", "conclusion": scope},
                     {"name": "all-jobs-passed", "status": "completed", "conclusion": passed}]}


def green_fixture():
    """The newest run is this head's own and still running. The run before it is green. Only the earlier green run counts."""
    return {"runs": [checks_run(3, HEAD_SHA, None, "in_progress", "2026-11-14T15:10:00Z"),
                     checks_run(2, GREEN_SHA, created="2026-11-14T15:00:00Z")],
            "job_lists": {2: jobs()}}


def read(runs=None, job_lists=None, fail=False, raw=None):
    """Run the reader with the stub gh first on PATH. -> the CompletedProcess."""
    case = tempfile.mkdtemp(dir=RUN_DIR)
    bin_dir = os.path.join(case, "bin")
    os.makedirs(bin_dir)
    stub = os.path.join(bin_dir, "gh")
    with open(stub, "w", encoding="utf-8", newline="\n") as f:
        f.write(STUB)
    os.chmod(stub, 0o755)
    with open(os.path.join(case, "runs.json"), "w", encoding="utf-8") as f:
        f.write(raw if raw is not None else json.dumps({"workflow_runs": runs or []}))
    for run_id, body in (job_lists or {}).items():
        with open(os.path.join(case, f"jobs-{run_id}.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps(body))
    if fail:
        open(os.path.join(case, "fail"), "w").close()
    env = dict(os.environ, PATH=os.pathsep.join([bin_dir, os.environ.get("PATH", "")]), GH_STUB_DIR=case,
               REPO=REPO, PR=PR, HEAD_SHA=HEAD_SHA, GH_TOKEN="stub-token")
    return subprocess.run([BASH, os.path.abspath(SCRIPT)], cwd=case, env=env, capture_output=True, text=True,
                          timeout=120)


@unittest.skipUnless(BASH, "bash not on PATH")
class GreenHead(unittest.TestCase):
    def assert_prints(self, r, want, why):
        self.assertEqual(r.stdout.splitlines(), want, f"{why}: stdout {r.stdout!r}, exit {r.returncode}")
        self.assertEqual(r.returncode, 0, f"{why}: exit {r.returncode}, stderr {r.stderr!r}")

    def assert_green_control(self):
        """The same green fixture, unchanged, must print its sha. Otherwise an empty line in a negative case means nothing."""
        self.assert_prints(read(**green_fixture()), [GREEN_SHA], "control: the green fixture does not print its sha")

    def test_green_run_prints_its_sha(self):
        self.assert_prints(read(**green_fixture()), [GREEN_SHA],
                           "the newest earlier run is green, its scope and all-jobs-passed jobs passed")

    def test_red_run_prints_empty_line(self):
        self.assert_green_control()
        fx = green_fixture()
        fx["runs"][1]["conclusion"] = "failure"
        self.assert_prints(read(**fx), [""], "the newest earlier run concluded failure")

    def test_draft_run_with_scope_skipped_prints_empty_line(self):
        self.assert_green_control()
        fx = green_fixture()
        fx["job_lists"] = {2: jobs(scope="skipped")}
        self.assert_prints(read(**fx), [""], "the earlier run's scope job was skipped, so it ran nothing")

    def test_newest_run_in_progress_decides_over_an_older_green_run(self):
        self.assert_green_control()
        fx = green_fixture()
        fx["runs"].insert(1, checks_run(4, MIDDLE_SHA, None, "in_progress", "2026-11-14T15:05:00Z"))
        fx["job_lists"][4] = jobs()
        self.assert_prints(read(**fx), [""], "the newest earlier run is still in progress, so the older green run is not it")

    def test_gh_failure_prints_empty_line(self):
        self.assert_green_control()
        self.assert_prints(read(**green_fixture(), fail=True), [""], "gh exits nonzero")

    def test_malformed_json_prints_empty_line(self):
        self.assert_green_control()
        self.assert_prints(read(raw="{not json"), [""], "the runs list is not JSON")

    def test_no_earlier_run_prints_empty_line(self):
        self.assert_green_control()
        fx = green_fixture()
        fx["runs"] = fx["runs"][:1]
        fx["job_lists"] = {}
        self.assert_prints(read(**fx), [""], "the only run is this head's own")

    def test_all_jobs_passed_not_success_prints_empty_line(self):
        self.assert_green_control()
        fx = green_fixture()
        fx["job_lists"] = {2: jobs(passed="failure")}
        self.assert_prints(read(**fx), [""], "the earlier run's all-jobs-passed job failed")


if __name__ == "__main__":
    unittest.main()
