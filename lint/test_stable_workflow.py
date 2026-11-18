#!/usr/bin/env python3
"""Cases for the stable workflow's move job, read by line. Standard library only.

    python3 lint/test_stable_workflow.py

The move job's `if:` is the only set of terms that keeps a pull request run from moving stable: it passes only a
successful push or schedule run on main of this repository (owner page item 880, 11:53 CST Nov 15). The job's `concurrency:`
must sit on the job, not on the workflow: a workflow-level group lets a skipped pull request run cancel a pending green move.

FileCases reads .github/workflows/stable.yml of this checkout. ScannerCases feeds fixture text to the same readers, so
a comment that names a key, a block body that holds one, and a lone quote in text do not change what is found.
The job block and the folded `if:` come from lint/workflow_steps.py, the one home of the workflow reader. CallerWire reads the
mover step's `with:` (head-sha, conclusion, event) from the same reader: the run facts the mover judges (item 880).
CallerNoRunJobs reads that the mover step passes no run-id and that the move job asks for no actions: read.
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from workflow_steps import block_scalar, drop_comment, job_block, step_blocks, step_key, step_with  # noqa: E402  the one home of the workflow reader

WORKFLOW = os.path.join(HERE, "..", ".github", "workflows", "stable.yml")
JOB = "move"
EVENT_TERM_PUSH = "github.event.workflow_run.event == 'push'"
EVENT_TERM_SCHEDULE = "github.event.workflow_run.event == 'schedule'"
TERMS = (
    "github.event.workflow_run.conclusion == 'success'",
    EVENT_TERM_PUSH,
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

    # The if: names the two events as one or-clause: a green push run and a green schedule run of main both move stable (owner,
    # 12:59 CST Nov 16).
    def test_the_move_job_if_has_each_term(self):
        text = self.workflow_text()
        expr = job_if(self.move_block(text))
        self.assertIsNotNone(expr, "the move job has no if: of its own, so no run is gated")
        clauses = if_clauses(expr)
        for term in TERMS:
            if term == EVENT_TERM_PUSH:
                continue
            with self.subTest(term=term):
                self.assertIn(term, clauses, "the move job's if: has no `%s` clause" % term)

    def test_the_move_job_if_accepts_a_push_run_and_a_schedule_run(self):
        expr = " ".join(job_if(self.move_block(self.workflow_text())).split())
        for term in (EVENT_TERM_PUSH, EVENT_TERM_SCHEDULE):
            with self.subTest(term=term):
                self.assertIn(term, expr, "the move job's if: has no `%s` term, so a green run of that event never reaches the mover" % term)
        self.assertIn("||", expr, "the push and schedule terms must be one or-clause, not two that both must hold")

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


MOVER_USES = "$/actions/stable-mover"


def mover_with(text):
    """The `with:` of the move job's step that uses the stable mover, as {name: raw value}. Read by the step reader of
    lint/workflow_steps.py, so a comment, a quoted value or a sibling step's key is never the mover's."""
    block = job_block(text, JOB)
    if block is None:
        return None
    steps = [s for s in step_blocks(block) if step_key(s, "uses") == MOVER_USES]
    return step_with(steps[0]) if len(steps) == 1 else None


class CallerWire(unittest.TestCase):
    """The run facts the caller passes the mover (owner page item 880, 11:53 CST Nov 15). The mover refuses or moves stable on
    these: a hard-coded or missing head, conclusion or event lets a run of the wrong kind move stable."""

    def mover_inputs(self):
        with open(WORKFLOW, encoding="utf-8") as f:
            with_ = mover_with(f.read())
        self.assertIsNotNone(with_, "scope: the move job has no single step that uses %s, so no case judges the mover's inputs" % MOVER_USES)
        self.assertTrue(with_, "scope: the mover step has no with: block, so no case judges the mover's inputs")
        return with_

    def test_the_mover_step_passes_each_run_fact_from_the_workflow_run(self):
        with_ = self.mover_inputs()
        for key, want in (("head-sha", "${{ github.event.workflow_run.head_sha }}"),
                          ("conclusion", "${{ github.event.workflow_run.conclusion }}"),
                          ("event", "${{ github.event.workflow_run.event }}")):
            with self.subTest(key=key):
                self.assertIn(key, with_, "the mover step has no `%s:` input, so the mover cannot judge the run it is given" % key)
                self.assertEqual(with_[key], want,
                                 "the mover's %s input must come from the workflow run, and it is %r" % (key, with_.get(key)))


class WithReaderCases(unittest.TestCase):
    """The mover's `with:` reader on fixture text: a commented key and a lone quote in a comment are text, not inputs."""

    def test_a_commented_with_key_is_not_an_input(self):
        text = workflow("jobs:", "  move:", "    steps:", "      - name: m", "        uses: $/actions/stable-mover", "        with:",
                        "          # event: push", "          head-sha: ${{ github.event.workflow_run.head_sha }}")
        with_ = mover_with(text)
        self.assertIsNotNone(with_, "scope: the fixture has no mover step, so the case proves nothing")
        self.assertNotIn("event", with_, "a commented `event:` line is text, so the mover has no event input in this fixture")

    def test_a_lone_quote_in_an_inline_comment_is_dropped_from_the_input(self):
        text = workflow("jobs:", "  move:", "    steps:", "      - name: m", "        uses: $/actions/stable-mover", "        with:",
                        "          run-id: ${{ github.event.workflow_run.id }}  # don't read another run",
                        "          event: ${{ github.event.workflow_run.event }}")
        with_ = mover_with(text)
        self.assertIsNotNone(with_, "scope: the fixture has no mover step, so the case proves nothing")
        self.assertEqual(with_.get("run-id"), "${{ github.event.workflow_run.id }}",
                         "the inline comment holds a lone quote, which is text, and the input value ends before the comment")


def job_permissions(block):
    """The job's own `permissions:` map as {scope: value}: its 6-space keys under the 4-space header, read to the next 4-space
    key. A comment line is text, and an inline comment comes off a value. A body sits deeper, so it is no key."""
    found, inside = {}, False
    for line in block.split("\n"):
        if line.strip().startswith("#"):
            continue
        if re.match(r"^    permissions:[ \t]*(#.*)?$", line):
            inside = True
        elif inside and (m := re.match(r"^      ([\w-]+):[ \t]*(.*?)[ \t]*$", line)):
            found[m.group(1)] = drop_comment(m.group(2))
        elif inside and line.strip() and not line.startswith("      "):
            inside = False
    return found


class CallerNoRunJobs(unittest.TestCase):
    """The caller passes the mover no run-id, and the move job asks for no actions: read. Only a read of a run's jobs needs
    either, and stable moves on each green run of main (owner, 12:59 CST Nov 16)."""

    def test_the_mover_gets_no_run_id_and_the_move_job_asks_no_actions_read(self):
        with open(WORKFLOW, encoding="utf-8") as f:
            text = f.read()
        block = job_block(text, JOB)
        self.assertIsNotNone(block, "scope: stable.yml has no `%s` job, so no case judges its grants" % JOB)
        with self.subTest(claim="mover inputs"):
            with_ = mover_with(text)
            self.assertIsNotNone(with_, "scope: the move job has no single step that uses %s, so no case judges the mover's inputs"
                                 % MOVER_USES)
            self.assertNotIn("run-id", with_, "the mover step passes a run-id, so the mover reads the jobs of a run it is given")
        with self.subTest(claim="move job permissions"):
            perms = job_permissions(block)
            self.assertIn("contents", perms,
                          "scope: the move job has no permissions: block that grants contents, so no case judges its grants")
            self.assertNotEqual(perms.get("actions"), "read",
                                "the move job asks for actions: read, which only a read of a run's jobs needs")


STEPS_TAIL = ["    steps:", "      - name: x", "        run: |", "          actions: read"]  # a run body that holds the text is no grant


class JobPermissionsReader(unittest.TestCase):
    """The permissions reader on fixture text: a comment line, an inline comment with a quote in it, a comment at column 0, a
    run body that holds the text, and an empty block. Each case ends with STEPS_TAIL."""

    def test_the_grants_are_read_as_the_text_says(self):
        cases = (
            ("a comment line that names a grant is text", ["      contents: write", "      # actions: read"], {"contents": "write"}),
            ("an inline comment comes off the value, and a quote in it is text",
             ["      contents: write", "      actions: read  # don't"], {"contents": "write", "actions": "read"}),
            ("a comment at column 0 does not end the block",
             ["      contents: write", "# asks for no more", "      actions: read"], {"contents": "write", "actions": "read"}),
            ("an empty block grants nothing", [], {}),
        )
        for label, lines, want in cases:
            with self.subTest(label):
                block = "\n".join(["    permissions:"] + lines + STEPS_TAIL) + "\n"
                self.assertEqual(job_permissions(block), want, label)


if __name__ == "__main__":
    unittest.main()
