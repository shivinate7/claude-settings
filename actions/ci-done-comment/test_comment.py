#!/usr/bin/env python3
"""Red run for actions/ci-done-comment, and for its caller in this repo's checks.yml.

A run with a red job must post one comment that names each red job. A green run, or one whose
only non-green jobs were skipped, must post nothing. The checks.yml caller must need every other
job and run when a job failed, or the comment fires before the run ends or never. Stdlib only:
the CI runner has no PyYAML.
Run: python3 actions/ci-done-comment/test_comment.py
"""
import json
import os
import re
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "comment.sh")
CHECKS = os.path.join(HERE, "..", "..", ".github", "workflows", "checks.yml")


def body(needs, job="", announced=""):
    env = dict(os.environ, NEEDS=json.dumps(needs), CI_DONE_DRY="1", PR="1", REPO="o/r",
               SHA="0123456789abcdef", RUN_URL="https://example/run", JOB=job, ANNOUNCED=announced)
    out = subprocess.run(["bash", SCRIPT], env=env, capture_output=True, text=True, check=True)
    return out.stdout


class Body(unittest.TestCase):
    def test_failed_job_is_named(self):
        got = body({"scope": {"result": "success"}, "checks-macos": {"result": "failure"}})
        self.assertIn("<!-- ci-done -->", got)
        self.assertIn("CI finished red on 0123456: checks-macos (failure).", got)
        self.assertIn("Run: https://example/run", got)
        self.assertNotIn("scope", got)

    def test_cancelled_job_is_named(self):
        # A job that hits its timeout-minutes cap ends cancelled. It is red, not quiet.
        got = body({"checks": {"result": "cancelled"}, "checks-windows": {"result": "failure"}})
        self.assertIn("checks (cancelled), checks-windows (failure)", got)

    def test_green_run_posts_nothing(self):
        got = body({"checks": {"result": "success"}, "checks-macos": {"result": "skipped"}})
        self.assertNotIn("ci-done", got)
        self.assertEqual(got.strip(), "No red job: no comment.")


class PerJob(unittest.TestCase):
    """A failing job wakes the runner at once; the run-end comment names only jobs not yet announced."""

    def test_job_mode_names_the_job_with_a_marker(self):
        got = body({}, job="checks")
        self.assertIn("<!-- ci-done -->", got)
        self.assertIn("<!-- ci-job:checks -->", got)
        self.assertIn("CI job checks failed on 0123456", got)
        self.assertIn("Run: https://example/run", got)

    def test_run_end_skips_announced_jobs(self):
        needs = {"checks": {"result": "failure"}, "checks-macos": {"result": "failure"}}
        got = body(needs, announced="checks")
        self.assertIn("checks-macos (failure)", got)
        self.assertNotIn("checks (failure)", got)

    def test_run_end_posts_nothing_when_all_announced(self):
        got = body({"checks": {"result": "failure"}}, announced="checks")
        self.assertEqual(got.strip(), "No red job: no comment.")

    def test_run_end_still_wakes_when_all_red_jobs_announced(self):
        # all-jobs-passed fails with any red job and has no wake step, so the run-end comment names it.
        needs = {"checks": {"result": "failure"}, "all-jobs-passed": {"result": "failure"}}
        got = body(needs, announced="checks")
        self.assertIn("all-jobs-passed (failure)", got)
        self.assertNotIn("checks (failure)", got)

    def test_run_end_still_names_unannounced_cancelled_job(self):
        # A timeout cancels a job before any step can post, so only the run-end comment can name it.
        got = body({"checks": {"result": "cancelled"}}, announced="")
        self.assertIn("checks (cancelled)", got)


NO_STEP_JOBS = {"all-jobs-passed", "ci-done"}


def per_job_problems(text):
    """Each job that fails without a step that wakes the runner as it fails."""
    out = []
    for name, job in checks_jobs(text).items():
        if name in NO_STEP_JOBS:
            continue
        job = re.sub(r"^\s*#.*\n", "", job, flags=re.M)
        if not re.search(r"^    permissions:\s*\n(?:      [\w-]+: \w+\s*\n)*      pull-requests:\s*write\s*$", job, re.M):
            out.append(name + " lacks pull-requests: write")
        step = re.search(r"- name: [^\n]*\n\s+if:\s*(.*)\n\s+uses:\s*\$/actions/ci-done-comment\s*\n\s*with:\s*\n\s*job:\s*(\S+)\s*$", job)
        if not step:
            out.append(name + " has no ci-done-comment job step")
            continue
        for part in ("failure()", "github.event_name == 'pull_request'", "!github.event.pull_request.draft"):
            if part not in step.group(1):
                out.append(name + " step if lacks " + part)
        if step.group(2) != name:
            out.append(name + " step names job " + step.group(2))
    return out


class JobSteps(unittest.TestCase):
    def test_every_job_has_the_step(self):
        with open(CHECKS, encoding="utf-8") as fh:
            self.assertEqual(per_job_problems(fh.read()), [])

    def test_all_jobs_passed_has_no_wake_step(self):
        # all-jobs-passed fails with any red job, so the run-end comment is its wake; a step of its own would double it.
        with open(CHECKS, encoding="utf-8") as fh:
            job = checks_jobs(fh.read())["all-jobs-passed"]
        self.assertNotRegex(job, r"uses:\s*\$/actions/ci-done-comment")

    def test_detector_goes_red(self):
        good = ("jobs:\n  a:\n    permissions:\n      contents: read\n      pull-requests: write\n    steps:\n"
                "      - run: x\n      - name: Wake\n        if: ${{ failure() && github.event_name == 'pull_request' && !github.event.pull_request.draft }}\n"
                "        uses: $/actions/ci-done-comment\n        with:\n          job: a\n")
        self.assertEqual(per_job_problems(good), [])
        for name, bad in {"no step": good.split("      - name: Wake")[0],
                          "wrong name": good.replace("job: a", "job: b"),
                          "no failure": good.replace("failure() && ", ""),
                          "no write": good.replace("pull-requests: write", "pull-requests: read")}.items():
            with self.subTest(name):
                self.assertNotEqual(per_job_problems(bad), [], name)


def checks_jobs(text):
    """{job name: its block text} for each job under `jobs:` in checks.yml. Stdlib only: CI has no PyYAML."""
    body = text[re.search(r"^jobs:\s*$", text, re.M).end():]
    marks = list(re.finditer(r"^  ([\w-]+):\s*$", body, re.M))
    return {m.group(1): body[m.end():(marks[i + 1].start() if i + 1 < len(marks) else len(body))]
            for i, m in enumerate(marks)}


def ci_done_problems(text):
    """Each way the ci-done job in checks.yml fails to comment once, after every job, on a red run."""
    jobs = checks_jobs(text)
    job = jobs.get("ci-done")
    if job is None:
        return ["checks.yml has no ci-done job"]
    job = re.sub(r"^\s*#.*\n", "", job, flags=re.M)  # a commented-out line does nothing
    out = []
    needs = re.search(r"^    needs:\s*\n((?:      - [\w-]+\s*\n)+)", job, re.M)
    got = sorted(re.findall(r"- ([\w-]+)", needs.group(1))) if needs else []
    if got != sorted(k for k in jobs if k != "ci-done"):
        out.append("ci-done must need every other job, as a block list")
    cond = (re.search(r"^    if:\s*(.*)$", job, re.M) or [None, ""])[1]
    for part in ("!cancelled()", "github.event_name == 'pull_request'", "!github.event.pull_request.draft"):
        if part not in cond:
            out.append("ci-done if lacks " + part)
    if not re.search(r"^      pull-requests:\s*write\s*$", job, re.M):
        out.append("ci-done lacks pull-requests: write")
    if not re.search(r"uses:\s*\$/actions/ci-done-comment\s*\n\s*with:\s*\n\s*needs:\s*\$\{\{ toJSON\(needs\) \}\}", job):
        out.append("ci-done does not pass toJSON(needs) to actions/ci-done-comment")
    return out


GOOD = """jobs:
  a:
    runs-on: x
  ci-done:
    needs:
      - a
    if: ${{ !cancelled() && github.event_name == 'pull_request' && !github.event.pull_request.draft }}
    permissions:
      pull-requests: write
    steps:
      - uses: $/actions/ci-done-comment
        with:
          needs: ${{ toJSON(needs) }}
"""


class ChecksCaller(unittest.TestCase):
    def test_checks_yml_ci_done_job(self):
        with open(CHECKS, encoding="utf-8") as fh:
            self.assertEqual(ci_done_problems(fh.read()), [])

    def test_detector_goes_red_on_each_defect(self):
        self.assertEqual(ci_done_problems(GOOD), [])
        broken = {
            "missing job": GOOD.replace("  ci-done:", "  other:"),
            "missed need": GOOD.replace("  a:\n", "  a:\n    runs-on: x\n  b:\n"),
            "no !cancelled": GOOD.replace("!cancelled() && ", ""),
            "runs on drafts": GOOD.replace(" && !github.event.pull_request.draft", ""),
            "read-only token": GOOD.replace("pull-requests: write", "pull-requests: read"),
            "no needs passed": GOOD.replace("needs: ${{ toJSON(needs) }}", "needs: '{}'"),
            "step commented out": GOOD.replace("      - uses:", "      # - uses:"),
        }
        for name, text in broken.items():
            with self.subTest(name):
                self.assertNotEqual(ci_done_problems(text), [], name)


if __name__ == "__main__":
    unittest.main()
