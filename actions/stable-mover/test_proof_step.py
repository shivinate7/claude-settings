#!/usr/bin/env python3
"""Cases for the wire of actions/stable-mover/action.yml, read by line. Standard library only.

    python3 actions/stable-mover/test_proof_step.py

The mover step takes HEAD_SHA, RUN_CONCLUSION and RUN_EVENT from the action's inputs, so it judges the run its caller names
(owner, 12:59 CST Nov 16: stable follows each green push run of main, for now). NoRunJobsRead holds that no step of the action
reads a run's jobs, and that the action declares no run-id input. lint/test_stable_workflow.py reads the caller's side.
EnvReaderCases and JobReadScanner feed fixture text to the readers, so a comment, a string, a body or a lone quote never
changes what is found.
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "lint"))
from workflow_steps import block_scalar, drop_comment  # noqa: E402  the one home of the workflow step reader

ACTION = os.path.join(HERE, "action.yml")
MOVER_STEP = "Fast-forward stable to the green head"
JOBS_READ = re.compile(r"actions/runs/|\bgh run\b")  # a read of a run's jobs: the run's REST path, or the gh run command


def action_text():
    with open(ACTION, encoding="utf-8") as f:
        return f.read()


def action_step(text, name):
    """The lines of the composite step named `name` in action.yml, from its `    - name:` line to the next step; None when absent.
    A composite step's `- name:` is at 4 spaces, its keys at 6 and its env keys at 8."""
    lines = text.split("\n")
    start = next((i for i, ln in enumerate(lines) if ln == "    - name: " + name), None)
    if start is None:
        return None
    end = next((j for j in range(start + 1, len(lines)) if lines[j].startswith("    - ")), len(lines))
    return lines[start:end]


def step_env(lines):
    """The step's own `env:` as {name: value}. Only keys at 8 spaces under the 6-space `env:` count: a comment is no key, a body
    under a later `run:` is no key, and an inline comment is dropped (drop_comment), as the runner reads it."""
    found, inside = {}, False
    for i, ln in enumerate(lines):
        if re.match(r"^      env:[ \t]*$", ln):
            inside = True
            continue
        if not inside:
            continue
        m = re.match(r"^        ([\w-]+):[ \t]*(.*?)[ \t]*$", ln)
        if m:
            value = drop_comment(m.group(2))
            body = block_scalar(value, lines[i + 1:], 9)
            found[m.group(1)] = value if body is None else body
        elif ln.strip() and not ln.startswith("        "):
            inside = False
    return found


def action_steps(text):
    """Each composite step of action.yml as raw text. A step starts at its `    - ` line and runs to the next step. A key at 4
    spaces or less ends the steps block. A comment line is text, so it never ends a step."""
    steps, cur = [], None
    for line in text.split("\n"):
        stripped = line.strip()
        if line.startswith("    - "):
            cur = [line]
            steps.append(cur)
        elif not stripped or stripped.startswith("#"):
            if cur is not None:
                cur.append(line)
        elif len(line) - len(line.lstrip(" ")) <= 4:
            cur = None
        elif cur is not None:
            cur.append(line)
    return ["\n".join(s) for s in steps]


def step_name(step):
    """A composite step's name, from its first line `    - name: <name>`, or None."""
    m = re.match(r"^    - name:[ \t]*(.*?)[ \t]*$", step.split("\n", 1)[0])
    return m.group(1) if m else None


def run_text(step):
    """A step's `run:` text: the one line, or a block scalar with its 8-space body. None when the step has no run."""
    lines = step.split("\n")
    for i, line in enumerate(lines):
        m = re.match(r"^      run:[ \t]*(.*?)[ \t]*$", line)
        if m:
            text = block_scalar(drop_comment(m.group(1)), lines[i + 1:], 8)
            return m.group(1) if text is None else text
    return None


def reads_run_jobs(run):
    """True when a line of a run's text reads a run's jobs. A line that starts with `#` is a comment, so it reads nothing."""
    return any(JOBS_READ.search(ln) for ln in run.split("\n") if not ln.lstrip().startswith("#"))


def action_input_names(text):
    """The names of the action's inputs, the keys at 2 spaces under its `inputs:` header."""
    names, inside = [], False
    for line in text.split("\n"):
        if line == "inputs:":
            inside = True
        elif inside and line.strip() and not line.startswith(" ") and not line.startswith("#"):
            inside = False
        elif inside and (m := re.match(r"^  ([\w-]+):[ \t]*$", line)):
            names.append(m.group(1))
    return names


class MoverWire(unittest.TestCase):
    """The run facts reach the mover step of action.yml as the action means them."""

    def step_lines(self, name):
        lines = action_step(action_text(), name)
        self.assertIsNotNone(lines, "scope: action.yml has no step named %r, so no case judges its wire" % name)
        return lines

    def test_the_mover_takes_the_run_facts_from_the_inputs(self):
        # Mistake: a mover that hard-codes the event moves stable on a run of any event, as a schedule run, whatever it was.
        env = step_env(self.step_lines(MOVER_STEP))
        self.assertTrue(env, "scope: the mover step has no env: block, so no case judges its run facts")
        for key, want in (("HEAD_SHA", "${{ inputs.head-sha }}"), ("RUN_CONCLUSION", "${{ inputs.conclusion }}"),
                          ("RUN_EVENT", "${{ inputs.event }}")):
            with self.subTest(key=key):
                self.assertEqual(env.get(key), want, "the mover step must read %s from the action input, and it reads %r" % (key, env.get(key)))


class NoRunJobsRead(unittest.TestCase):
    """The stable action reads no run's jobs. Its steps judge only the run they are given, so none reads more."""

    def test_no_step_reads_a_run_jobs_and_the_action_declares_no_run_id(self):
        text = action_text()
        steps = action_steps(text)
        with self.subTest(claim="steps"):
            self.assertIn(MOVER_STEP, [step_name(s) for s in steps],
                          "scope: action.yml has no step named %r, so no case judges what its steps read" % MOVER_STEP)
            runs = [(step_name(s), run_text(s)) for s in steps]
            for name, run in runs:
                self.assertIsNotNone(run, "scope: step %r has no run: body, so its reads are not judged" % name)
            reading = [name for name, run in runs if reads_run_jobs(run)]
            self.assertEqual(reading, [], "a step of action.yml reads a run's jobs, so the mover judges more than the run it is given: %s"
                             % ", ".join(reading))
        with self.subTest(claim="inputs"):
            names = action_input_names(text)
            self.assertTrue(names, "scope: action.yml has no inputs: block, so no case judges its inputs")
            self.assertNotIn("run-id", names, "action.yml declares a run-id input, which only a read of a run's jobs needs")


class EnvReaderCases(unittest.TestCase):
    """The env reader on fixture text: a comment, a later step's body or a lone quote never changes what is read."""

    def test_a_commented_env_key_is_not_a_key(self):
        lines = ["    - name: m", "      env:", '        # RUN_NOTE: "true"', "        RUN_EVENT: ${{ inputs.event }}", "      run: echo"]
        env = step_env(lines)
        self.assertNotIn("RUN_NOTE", env, "a commented key is text, so RUN_NOTE is not read")
        self.assertEqual(env, {"RUN_EVENT": "${{ inputs.event }}"})

    def test_a_key_in_a_run_body_is_not_an_env_key(self):
        # The body is a multi-line block: its `#` line and its key-shaped line are script text, not env.
        lines = ["    - name: m", "      env:", "        RUN_EVENT: a", "      run: |", "        # a note in the script",
                 '        RUN_NOTE: "true"', "        echo x"]
        env = step_env(lines)
        self.assertNotIn("RUN_NOTE", env, "a key under a later run: body is script text, so RUN_NOTE is not read")
        self.assertEqual(env, {"RUN_EVENT": "a"})

    def test_a_hash_inside_a_quoted_value_is_text(self):
        lines = ["    - name: m", "      env:", '        RUN_ID: "run #${{ inputs.run-id }}"', "      run: echo"]
        self.assertEqual(step_env(lines), {"RUN_ID": '"run #${{ inputs.run-id }}"'},
                         "a # inside a quoted value is text, so the whole quoted value is read")

    def test_a_lone_quote_in_an_inline_comment_is_dropped(self):
        lines = ["    - name: m", "      env:", "        RUN_EVENT: ${{ inputs.event }}  # don't", "      run: echo"]
        self.assertEqual(step_env(lines), {"RUN_EVENT": "${{ inputs.event }}"},
                         "the inline comment holds a lone quote, which is text, and the value ends before the comment")


class JobReadScanner(unittest.TestCase):
    """The run reader on fixture text: a comment line, a comment opener inside a string, a lone quote in a comment, and an empty
    body each give the read the text means."""

    def test_the_read_is_found_or_skipped_as_the_text_says(self):
        cases = (
            ("a comment line that names the read is text", ["        # gh api repos/o/r/actions/runs/1/jobs", "        echo ok"], False),
            ("a comment opener inside a string does not hide a read", ['        echo "# note" && gh api "repos/o/r/actions/runs/1/jobs"'], True),
            ("a lone quote in a comment does not hide the read on the next line",
             ["        # don't", "        gh api repos/o/r/actions/runs/1/jobs"], True),
            ("an empty run body reads nothing", [], False),
        )
        for label, body, want in cases:
            with self.subTest(label):
                step = "\n".join(["    - name: x", "      run: |"] + body) + "\n"
                run = run_text(step)
                self.assertIsNotNone(run, "scope: the fixture step has no run: body, so the case proves nothing")
                self.assertEqual(reads_run_jobs(run), want, label)


if __name__ == "__main__":
    unittest.main()
