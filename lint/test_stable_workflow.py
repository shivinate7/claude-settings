#!/usr/bin/env python3
"""Cases for the stable workflow's move job, read by line. Standard library only.

    python3 lint/test_stable_workflow.py

The move job's `if:` is the only set of terms that keeps a pull request run from moving stable: it passes only a
successful push run on main of this repository. The job's `concurrency:` must sit on the job, not on the workflow: a
workflow-level group lets a skipped pull request run cancel a pending green move.

FileCases reads .github/workflows/stable.yml of this checkout. ScannerCases feeds fixture text to the same readers, so
a comment that names a key, a block body that holds one, and a lone quote in text do not change what is found.
The job block and the folded `if:` come from lint/workflow_steps.py, the one home of the workflow reader.
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from workflow_steps import block_scalar, drop_comment, job_block  # noqa: E402  the one home of the workflow reader

WORKFLOW = os.path.join(HERE, "..", ".github", "workflows", "stable.yml")
JOB = "move"
TERMS = (
    "github.event.workflow_run.conclusion == 'success'",
    "github.event.workflow_run.event == 'push'",
    "github.event.workflow_run.head_branch == 'main'",
    "github.event.workflow_run.head_repository.full_name == github.repository",
)
IF_BODY = [  # the move job's `if:` as stable.yml writes it: a folded block, one term per line
    "      ${{ github.event.workflow_run.conclusion == 'success'",
    "      && github.event.workflow_run.event == 'push'",
    "      && github.event.workflow_run.head_branch == 'main'",
    "      && github.event.workflow_run.head_repository.full_name == github.repository }}",
]


def workflow_level_concurrency(text):
    """True when a `concurrency:` key sits at column 0, the workflow's own level."""
    return re.search(r"^concurrency:", text, re.M) is not None


def job_concurrency(block):
    """The job's own `concurrency:` value, or None when the job has no such key. A job key sits at 4 spaces."""
    m = re.search(r"^    concurrency:[ \t]*(.*?)[ \t]*$", block, re.M)
    return None if m is None else drop_comment(m.group(1))


def job_if(block):
    """The job's own `if:` expression, a folded or literal body read by block_scalar; None when the job has none.
    A job key sits at 4 spaces, so a step's own `if:` (8 spaces) is never the job's."""
    lines = block.split("\n")
    for i, line in enumerate(lines):
        m = re.match(r"^    if:[ \t]*(.*?)[ \t]*$", line)
        if m:
            value = drop_comment(m.group(1))
            body = block_scalar(value, lines[i + 1:], 6)
            return value if body is None else body
    return None


def if_clauses(expr):
    """The `&&` clauses of an `if:` expression, the `${{ }}` wrapper removed and each clause's spacing squeezed."""
    text = re.sub(r"\$\{\{|\}\}", " ", expr)
    return [" ".join(c.split()) for c in text.split("&&") if c.strip()]


def workflow(*lines):
    return "\n".join(lines) + "\n"


class FileCases(unittest.TestCase):
    """The stable workflow as this checkout holds it."""

    def workflow_text(self):
        # Scope first: every case reads this file, so a missing file is the failure, not a crash.
        self.assertTrue(os.path.isfile(WORKFLOW), "stable.yml is not at %s" % WORKFLOW)
        with open(WORKFLOW, encoding="utf-8") as f:
            return f.read()

    def move_block(self, text):
        block = job_block(text, JOB)
        self.assertIsNotNone(block, "stable.yml has no `%s` job, so there is no move job to check" % JOB)
        return block

    def test_the_move_job_if_has_each_term(self):
        text = self.workflow_text()
        expr = job_if(self.move_block(text))
        self.assertIsNotNone(expr, "the move job has no if: of its own, so no run is gated")
        clauses = if_clauses(expr)
        for term in TERMS:
            with self.subTest(term=term):
                self.assertIn(term, clauses, "the move job's if: has no `%s` clause" % term)

    def test_concurrency_is_not_at_workflow_level(self):
        text = self.workflow_text()
        self.assertFalse(workflow_level_concurrency(text),
                         "concurrency: is at workflow level, so a skipped pull request run can cancel a pending move")

    def test_concurrency_is_on_the_move_job(self):
        text = self.workflow_text()
        self.assertIsNotNone(job_concurrency(self.move_block(text)), "the move job has no concurrency: of its own")


class ScannerCases(unittest.TestCase):
    """The readers on fixture text: a comment, a block body or a lone quote never changes what is found."""

    def test_a_comment_that_names_the_job_key_is_not_the_key(self):
        text = workflow("jobs:", "  move:", "    # concurrency:", "    runs-on: ubuntu-latest")
        self.assertIsNone(job_concurrency(job_block(text, JOB)))

    def test_a_comment_at_column_0_that_names_the_workflow_key_is_not_the_key(self):
        text = workflow("# concurrency:", "name: stable", "jobs:", "  move:", "    runs-on: ubuntu-latest")
        self.assertFalse(workflow_level_concurrency(text))

    def test_a_block_body_that_holds_the_key_text_is_not_the_key(self):
        text = workflow("jobs:", "  move:", "    runs-on: ubuntu-latest", "    steps:", "      - name: x",
                        "        run: |", "          echo \"don't\"", "          concurrency:", "          group: x")
        self.assertIsNone(job_concurrency(job_block(text, JOB)))
        self.assertFalse(workflow_level_concurrency(text))

    def test_a_lone_quote_in_a_comment_does_not_break_the_if_read(self):
        text = workflow("jobs:", "  move:", "    # Don't move a run that failed.", "    if: >-", *IF_BODY,
                        "    runs-on: ubuntu-latest")
        self.assertEqual(if_clauses(job_if(job_block(text, JOB))), list(TERMS))

    def test_a_comment_after_the_folded_header_is_dropped_and_the_quote_in_it_is_text(self):
        text = workflow("jobs:", "  move:", "    if: >- # the run's conclusion and branch", *IF_BODY,
                        "    runs-on: ubuntu-latest")
        self.assertEqual(if_clauses(job_if(job_block(text, JOB))), list(TERMS))

    def test_a_hash_inside_a_quoted_clause_of_a_folded_if_is_kept(self):
        body = ["      ${{ github.event.workflow_run.head_branch == 'main # not a comment'",
                "      && github.event.workflow_run.event == 'push' }}"]
        text = workflow("jobs:", "  move:", "    if: >-", *body, "    runs-on: ubuntu-latest")
        self.assertEqual(if_clauses(job_if(job_block(text, JOB))),
                         ["github.event.workflow_run.head_branch == 'main # not a comment'",
                          "github.event.workflow_run.event == 'push'"])

    def test_a_step_if_is_not_the_job_if(self):
        text = workflow("jobs:", "  move:", "    runs-on: ubuntu-latest", "    steps:", "      - name: a",
                        "        if: ${{ false }}", "        run: echo a")
        self.assertIsNone(job_if(job_block(text, JOB)))

    def test_another_jobs_concurrency_is_not_the_move_job_concurrency(self):
        text = workflow("jobs:", "  move:", "    runs-on: ubuntu-latest", "  other:", "    concurrency:",
                        "      group: y", "    runs-on: ubuntu-latest")
        self.assertIsNone(job_concurrency(job_block(text, JOB)))


if __name__ == "__main__":
    unittest.main()
