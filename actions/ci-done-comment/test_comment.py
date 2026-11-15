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


def body(needs):
    env = dict(os.environ, NEEDS=json.dumps(needs), CI_DONE_DRY="1", PR="1", REPO="o/r",
               SHA="0123456789abcdef", RUN_URL="https://example/run")
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


def checks_jobs(text):
    """{job name: its block text} for each job under `jobs:` in checks.yml. Stdlib only: CI has no PyYAML."""
    body = text[re.search(r"^jobs:\s*$", text, re.M).end():]
    marks = list(re.finditer(r"^  ([\w-]+):\s*$", body, re.M))
    return {m.group(1): body[m.end():(marks[i + 1].start() if i + 1 < len(marks) else len(body))]
            for i, m in enumerate(marks)}


SCHEDULE_ONLY_IF = re.compile(r"^    if:\s*\$\{\{\s*github\.event_name == 'schedule'\s*\}\}[ \t]*(?:#[^\n]*)?$", re.M)


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
    # R61 part 3: a job whose if is only the schedule is not needed here. ci-done runs on a pull_request alone, so it never
    # reads a scheduled job, and it may name one with no harm.
    scheduled = {k for k, body in jobs.items() if k != "ci-done" and SCHEDULE_ONLY_IF.search(body)}
    if sorted(set(got) - scheduled) != sorted(k for k in jobs if k != "ci-done" and k not in scheduled):
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


class ScheduledSkip(unittest.TestCase):
    """R61 part 3: the nightly gate is a schedule-only job, which ci-done need not name. Controls: the rule holds with the gate
    beside ci-done, with or without its name in ci-done's needs, and a job that a pull_request run needs is still required."""
    SKIP = "  nightly-skip:\n    if: ${{ github.event_name == 'schedule' }}\n    runs-on: x\n"

    def test_a_schedule_only_skip_beside_ci_done_needs_no_entry_there(self):
        self.assertEqual(ci_done_problems(GOOD.replace("  ci-done:", self.SKIP + "  ci-done:", 1)), [])

    def test_a_schedule_only_skip_named_in_ci_done_is_accepted(self):
        text = GOOD.replace("  ci-done:", self.SKIP + "  ci-done:", 1).replace("    needs:\n      - a\n", "    needs:\n      - a\n      - nightly-skip\n")
        self.assertEqual(ci_done_problems(text), [])

    def test_a_trailing_comment_on_the_skips_if_keeps_the_exemption(self):
        # A trailing comment on the if: line is text to YAML, so the gate is still a schedule-only job that ci-done need not name.
        nightly_skip = self.SKIP.replace("'schedule' }}\n", "'schedule' }}  # nightly only\n")
        self.assertEqual(ci_done_problems(GOOD.replace("  ci-done:", nightly_skip + "  ci-done:", 1)), [])

    def test_a_hash_inside_a_quoted_step_of_the_skip_keeps_the_exemption(self):
        # A `#` inside quotes is text, not a comment: the gate's step still reads, and the gate stays exempt.
        nightly_skip = self.SKIP + "    steps:\n      - run: echo \"skip=false # not a comment\" >> \"$GITHUB_OUTPUT\"\n"
        self.assertEqual(ci_done_problems(GOOD.replace("  ci-done:", nightly_skip + "  ci-done:", 1)), [])

    def test_a_pull_request_job_left_out_beside_the_skip_is_still_flagged(self):
        text = GOOD.replace("  ci-done:", "  b:\n    runs-on: x\n" + self.SKIP + "  ci-done:", 1)
        self.assertTrue(ci_done_problems(text), "a job a pull_request run needs is left out of ci-done's needs and is not flagged")


if __name__ == "__main__":
    unittest.main()
