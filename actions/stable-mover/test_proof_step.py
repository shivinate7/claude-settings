#!/usr/bin/env python3
"""Cases for the proof step of actions/stable-mover/action.yml, the step that says whether a push run is proven.

    python3 actions/stable-mover/test_proof_step.py [<run folder>]

The step writes proven=true to $GITHUB_OUTPUT only for a push run whose push-skip job succeeded and whose scope job was
skipped (owner page item 880, 11:53 CST Nov 15). A run whose scope ran covers the Linux fast jobs only, so stable must not
move on it. A failed jobs read is UNKNOWN: the step exits 2 and writes no proof.

The step's shell comes from action.yml, read by block_scalar (lint/workflow_steps.py, the one home of the step reader), and
runs as the runner runs a composite step: bash --noprofile --norc -eo pipefail. The seam is `gh`: a stub on PATH prints the
lines the step's --jq filter would print, exits with the code its case sets, and logs its argv. The --jq filter itself is
not run. Needs bash, as actions/stable-mover/test_action.sh does. test_action.sh passes its run folder; run alone, this file
makes its own and removes it.

The wire is read too (owner page item 880, 11:53 CST Nov 15): the mover step takes its proof from the proof step's output, so a
mover that reads a fixed "true" would move stable on a Linux-only push run. MoverWire reads the env of each step in action.yml by
line; the caller's `with:` is read by lint/test_stable_workflow.py.
"""
import os
import re
import shutil
import subprocess
import sys
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "lint"))
from workflow_steps import block_scalar, drop_comment  # noqa: E402  the one home of the workflow step reader
import _test_temp  # noqa: E402  test-temp-standard: every temp path comes from this run's folder

ACTION = os.path.join(HERE, "action.yml")
STEP_NAME = "    - name: Read the push-skip proof of a push run"
RUN_ID = "4242"
REPO = "owner/repo"
PROVEN = ["push-skip=success", "scope=skipped", "checks=skipped", "checks-windows-merge-3=skipped"]
LINUX_ONLY = ["push-skip=success", "scope=success", "checks=success", "checks-windows-merge-3=skipped"]
GH_STUB = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$STUB_LOG"
if [ "$STUB_EXIT" != 0 ]; then echo "gh: stub read failure" >&2; exit "$STUB_EXIT"; fi
cat "$STUB_JOBS"
"""
FOLDER = None  # the run folder, set when the file runs


def proof_run_text():
    """The step's `run:` body as action.yml holds it, or None when the step or its body is absent. The step's keys sit at 6
    spaces and its body at 8; the next step starts at 4, which ends the body."""
    with open(ACTION, encoding="utf-8") as f:
        lines = f.read().split("\n")
    start = next((i for i, ln in enumerate(lines) if ln == STEP_NAME), None)
    if start is None:
        return None
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("    - "):
            return None
        m = re.match(r"^      run:[ \t]*(.*?)[ \t]*$", lines[j])
        if m:
            return block_scalar(m.group(1), lines[j + 1:], 8)
    return None


class ProofStep(unittest.TestCase):
    def run_step(self, event, jobs=None, gh_exit=0):
        """Run the proof step once, as the runner does. -> dict: rc, proven (the proven= values the step wrote), reads (the
        argv of each gh call) and text (stdout and stderr)."""
        body = proof_run_text()
        self.assertIsNotNone(body, "scope: action.yml has no run body in the step named %r, so no case judges the proof" % STEP_NAME)
        self.assertIn("proven=", body, "scope: the step's body writes no proven= line, so no case judges the proof")
        case = os.path.join(FOLDER, uuid.uuid4().hex)
        bin_dir = os.path.join(case, "bin")
        os.makedirs(bin_dir)
        paths = {"gh": os.path.join(bin_dir, "gh"), "step": os.path.join(case, "proof.sh"), "jobs": os.path.join(case, "jobs.txt"),
                 "out": os.path.join(case, "output"), "log": os.path.join(case, "gh.log")}
        with open(paths["gh"], "w", encoding="utf-8") as f:
            f.write(GH_STUB)
        os.chmod(paths["gh"], 0o755)
        with open(paths["step"], "w", encoding="utf-8") as f:
            f.write(body)
        with open(paths["jobs"], "w", encoding="utf-8") as f:
            f.write("".join(line + "\n" for line in jobs or []))
        open(paths["out"], "w", encoding="utf-8").close()
        env = {"PATH": bin_dir + os.pathsep + os.environ.get("PATH", ""), "HOME": case,
               "RUN_EVENT": event, "RUN_ID": RUN_ID, "REPO": REPO, "GH_TOKEN": "fixture-token",
               "GITHUB_OUTPUT": paths["out"], "STUB_LOG": paths["log"], "STUB_JOBS": paths["jobs"], "STUB_EXIT": str(gh_exit)}
        done = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", paths["step"]], env=env,
                              capture_output=True, text=True, timeout=60)
        with open(paths["out"], encoding="utf-8") as f:
            proven = [ln.strip()[len("proven="):] for ln in f if ln.startswith("proven=")]
        reads = []
        if os.path.isfile(paths["log"]):
            with open(paths["log"], encoding="utf-8") as f:
                reads = f.read().splitlines()
        return {"rc": done.returncode, "proven": proven, "reads": reads, "text": done.stdout + done.stderr}

    def assert_jobs_read(self, got):
        """Scope first: the step read the jobs of this run, so the value it wrote is a judgement and not a skipped read."""
        want = "repos/%s/actions/runs/%s/jobs" % (REPO, RUN_ID)
        self.assertTrue(any(want in r for r in got["reads"]),
                        "scope: the step never read the jobs of run %s (gh was called with %r)" % (RUN_ID, got["reads"]))

    def test_a_push_run_with_scope_skipped_and_push_skip_succeeded_is_proven(self):
        got = self.run_step("push", PROVEN)
        self.assert_jobs_read(got)
        self.assertEqual(got["rc"], 0, "the step exits %d on a readable jobs list: %s" % (got["rc"], got["text"][-300:]))
        self.assertEqual(got["proven"], ["true"],
                         "a push run whose push-skip succeeded and whose scope was skipped is proven: the step must write proven=true")

    def test_a_push_run_whose_scope_ran_is_not_proven(self):
        # Mistake: a Linux-only push run counts as proven, so stable moves on a run that never ran the slow legs.
        got = self.run_step("push", LINUX_ONLY)
        self.assert_jobs_read(got)
        self.assertEqual(got["proven"], ["false"],
                         "a push run whose scope ran covers the Linux fast jobs only: the step must write proven=false")

    def test_a_push_run_whose_push_skip_failed_is_not_proven(self):
        # Mistake: the scope skip is taken as proof although the push-skip job itself failed.
        got = self.run_step("push", ["push-skip=failure", "scope=skipped", "checks=skipped"])
        self.assert_jobs_read(got)
        self.assertEqual(got["proven"], ["false"], "a failed push-skip job proves nothing: the step must write proven=false")

    def test_an_empty_jobs_read_is_not_proven(self):
        # Mistake: a jobs read that returns nothing reads as proof, since no line says the scope ran.
        got = self.run_step("push", [])
        self.assert_jobs_read(got)
        self.assertEqual(got["rc"], 0, "an empty jobs read is a read, not an error: the step exits %d: %s" % (got["rc"], got["text"][-300:]))
        self.assertEqual(got["proven"], ["false"], "an empty jobs read proves nothing: the step must write proven=false")

    def test_a_failed_jobs_read_stops_the_step_as_unknown_and_writes_no_proof(self):
        # Mistake: a failed read carries on, and the step writes a proof it never read.
        got = self.run_step("push", PROVEN, gh_exit=1)
        self.assert_jobs_read(got)
        self.assertEqual(got["rc"], 2, "a failed jobs read is UNKNOWN: the step must exit 2, and it exited %d" % got["rc"])
        self.assertEqual(got["proven"], [], "a failed jobs read must write no proof, so the step writes no proven= line")

    def test_a_schedule_run_needs_no_proof_and_reads_no_jobs(self):
        # Mistake: a schedule run waits on a jobs read it has no use for, so a failed read stops the daily's move.
        got = self.run_step("schedule")
        self.assertEqual(len(got["proven"]), 1, "scope: the step did not reach its output line on a schedule run: %s" % got["text"][-300:])
        self.assertEqual(got["rc"], 0, "a schedule run needs no proof, so the step exits 0, and it exited %d" % got["rc"])
        self.assertEqual(got["reads"], [], "a schedule run needs no proof, so the step reads no jobs (gh was called with %r)" % got["reads"])

    def test_a_push_run_with_more_jobs_than_one_page_still_finds_its_proof(self):
        # Full-size state (P8): a page of 100 jobs, with the proof lines after it.
        filler = ["job-%03d=skipped" % n for n in range(100)]
        got = self.run_step("push", filler + PROVEN)
        self.assert_jobs_read(got)
        self.assertEqual(got["proven"], ["true"], "a run with more jobs than one page is proven when its proof lines are in the read")


MOVER_STEP = "Fast-forward stable to the green head"
PROOF_STEP = "Read the push-skip proof of a push run"


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


def step_value(lines, key):
    """The step's own 6-space `key:` value, comment dropped, or None."""
    for ln in lines:
        m = re.match(r"^      %s:[ \t]*(.*?)[ \t]*$" % re.escape(key), ln)
        if m:
            return drop_comment(m.group(1))
    return None


def action_text():
    with open(ACTION, encoding="utf-8") as f:
        return f.read()


class MoverWire(unittest.TestCase):
    """The inputs and the proof reach each step of action.yml as the action means them."""

    def step_lines(self, name):
        lines = action_step(action_text(), name)
        self.assertIsNotNone(lines, "scope: action.yml has no step named %r, so no case judges its wire" % name)
        return lines

    def test_the_mover_takes_its_proof_from_the_proof_step_output(self):
        # Mistake: a mover that reads a fixed "true" moves stable on a Linux-only push run, whose proof is false.
        env = step_env(self.step_lines(MOVER_STEP))
        self.assertTrue(env, "scope: the mover step has no env: block, so no case judges its proof wire")
        self.assertEqual(env.get("RUN_PROVEN"), "${{ steps.proof.outputs.proven }}",
                         "the mover step must read the proof step's output, so a push run the proof rejects cannot move stable: RUN_PROVEN is %r"
                         % env.get("RUN_PROVEN"))

    def test_the_mover_takes_the_run_facts_from_the_inputs(self):
        # Mistake: a mover that hard-codes the event moves stable on a run of any event, as a schedule run, whatever it was.
        env = step_env(self.step_lines(MOVER_STEP))
        self.assertTrue(env, "scope: the mover step has no env: block, so no case judges its run facts")
        for key, want in (("HEAD_SHA", "${{ inputs.head-sha }}"), ("RUN_CONCLUSION", "${{ inputs.conclusion }}"),
                          ("RUN_EVENT", "${{ inputs.event }}")):
            with self.subTest(key=key):
                self.assertEqual(env.get(key), want, "the mover step must read %s from the action input, and it reads %r" % (key, env.get(key)))

    def test_the_proof_step_takes_its_run_and_event_from_the_inputs(self):
        # Mistake: a proof step that hard-codes its event or run reads the wrong run's jobs, or proves a schedule run it never read.
        lines = self.step_lines(PROOF_STEP)
        env = step_env(lines)
        self.assertTrue(env, "scope: the proof step has no env: block, so no case judges its inputs")
        for key, want in (("RUN_EVENT", "${{ inputs.event }}"), ("RUN_ID", "${{ inputs.run-id }}")):
            with self.subTest(key=key):
                self.assertEqual(env.get(key), want, "the proof step must read %s from the action input, and it reads %r" % (key, env.get(key)))

    def test_the_proof_step_has_the_id_the_mover_reads(self):
        # Mistake: the proof step is renamed, and the mover reads an output that no step writes.
        self.assertEqual(step_value(self.step_lines(PROOF_STEP), "id"), "proof",
                         "the proof step must have id `proof`, the id the mover step reads its output from")


class EnvReaderCases(unittest.TestCase):
    """The env reader on fixture text: a comment, a later step's body or a lone quote never changes what is read."""

    def test_a_commented_env_key_is_not_a_key(self):
        lines = ["    - name: m", "      env:", '        # RUN_PROVEN: "true"', "        RUN_EVENT: ${{ inputs.event }}", "      run: echo"]
        env = step_env(lines)
        self.assertNotIn("RUN_PROVEN", env, "a commented key is text, so RUN_PROVEN is not read")
        self.assertEqual(env, {"RUN_EVENT": "${{ inputs.event }}"})

    def test_a_key_in_a_run_body_is_not_an_env_key(self):
        # The body is a multi-line block: its `#` line and its key-shaped line are script text, not env.
        lines = ["    - name: m", "      env:", "        RUN_EVENT: a", "      run: |", "        # a note in the script",
                 '        RUN_PROVEN: "true"', "        echo x"]
        env = step_env(lines)
        self.assertNotIn("RUN_PROVEN", env, "a key under a later run: body is script text, so RUN_PROVEN is not read")
        self.assertEqual(env, {"RUN_EVENT": "a"})

    def test_a_hash_inside_a_quoted_value_is_text(self):
        lines = ["    - name: m", "      env:", '        RUN_ID: "run #${{ inputs.run-id }}"', "      run: echo"]
        self.assertEqual(step_env(lines), {"RUN_ID": '"run #${{ inputs.run-id }}"'},
                         "a # inside a quoted value is text, so the whole quoted value is read")

    def test_a_lone_quote_in_an_inline_comment_is_dropped(self):
        lines = ["    - name: m", "      env:", "        RUN_EVENT: ${{ inputs.event }}  # don't", "      run: echo"]
        self.assertEqual(step_env(lines), {"RUN_EVENT": "${{ inputs.event }}"},
                         "the inline comment holds a lone quote, which is text, and the value ends before the comment")


if __name__ == "__main__":
    given = sys.argv.pop(1) if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else None
    FOLDER = given or _test_temp.run_folder()
    result = unittest.main(exit=False).result
    if given is None:
        shutil.rmtree(FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder this file made
    sys.exit(0 if result.wasSuccessful() else 1)
