#!/usr/bin/env python3
"""Stop report guard: a `step:<slug>` a report names, or a "queued"/"filed" claim about a step, is read from
git (rule building-mistake-names-its-guard, rule verification-report-unknown-reads, decision
`mistake-means-missing-guard`). The step must be a blob on origin/roadmap; a step only on a lane branch is not
queued. The false-alarm controls pin "queued" in other senses (a CI run, a merge queue, a lane waiting).

    python3 lint/test_report_guard_steps.py -v
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
import test_report_guard as trg  # noqa: E402  the transcript helpers and the run isolation (one home)

RUN_FOLDER = trg.RUN_FOLDER
SLUG = "pick-reaches-page"
STEP_FILE = "roadmap/data/steps/%s.json" % SLUG


def setUpModule():
    trg.setUpModule()


def tearDownModule():
    trg.tearDownModule()


def git(cwd, *args):
    run = subprocess.run(["git", "-C", cwd, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                         capture_output=True, text=True)
    assert run.returncode == 0, (args, run.stderr)
    return run.stdout


def report(deviations="none", done="> **Done** OTHER read the audit", nxt="> **Next** none"):
    return "%s\n> **Deviations** %s\n%s" % (done, deviations, nxt)


class StepClaimTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.folder, True)

    def repo(self, on_roadmap=(), on_lane=(), remote=True, single_branch=False):
        """A clone whose origin holds branch roadmap with the `on_roadmap` steps and branch lane-x with `on_lane`."""
        origin = os.path.join(self.folder, "origin.git")
        seed = os.path.join(self.folder, "seed")
        clone = os.path.join(self.folder, "clone")
        git(self.folder, "init", "-q", "--bare", origin)
        git(self.folder, "init", "-q", "-b", "main", seed)
        with open(os.path.join(seed, "f"), "w") as handle:
            handle.write("x")
        git(seed, "add", "-A")
        git(seed, "commit", "-qm", "init")
        for branch, slugs in (("roadmap", on_roadmap), ("lane-x", on_lane)):
            git(seed, "checkout", "-q", "-b", branch, "main")
            for slug in slugs:
                path = os.path.join(seed, "roadmap/data/steps/%s.json" % slug)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w") as handle:
                    handle.write("{}")
            git(seed, "add", "-A")
            git(seed, "commit", "-qm", branch, "--allow-empty")
        git(seed, "push", "-q", origin, "main", "roadmap", "lane-x")
        git(self.folder, "clone", "-q", *(["--single-branch", "--branch", "main"] if single_branch else []),
            origin, clone)
        if not remote:
            git(clone, "remote", "set-url", "origin", os.path.join(self.folder, "no-such.git"))
        return clone

    def run_report(self, clone, reply):
        records = [trg.human("do the task"), trg.tool_use_msg("Bash", {"command": "git commit -m x"}),
                   trg.tool_result_msg(), trg.assistant_text(reply)]
        path = trg.write_transcript(records, self.folder)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": False, "cwd": clone}
        run = trg.run_guard(trg.REPORT_GUARD, hook)
        self.assertEqual(run.returncode, 0, run.stderr[-300:])
        return (json.loads(run.stdout) if run.stdout.strip() else None), run.stderr

    def blocked(self, clone, reply):
        out, _ = self.run_report(clone, reply)
        self.assertIsNotNone(out, "passed, but must block: " + reply)
        self.assertEqual(out.get("decision"), "block", out)
        self.assertIn("step", out.get("reason", ""), out)

    def passes(self, clone, reply):
        out, err = self.run_report(clone, reply)
        self.assertIsNone(out, "blocked, but must pass: %s" % out)
        return err

    # Red: the 12:10 CST mistake, a guard reported as queued with no step file on origin/roadmap.
    def test_red_named_step_missing_on_roadmap_blocks(self):
        clone = self.repo()
        self.blocked(clone, report("I misread the inbox; the guard is queued as `step:%s`." % SLUG))

    def test_red_named_step_only_on_lane_branch_blocks(self):
        clone = self.repo(on_lane=[SLUG])
        self.blocked(clone, report("I misread the inbox; the guard is queued as `step:%s`." % SLUG))

    def test_red_queued_claim_in_next_names_missing_step_blocks(self):
        clone = self.repo()
        self.blocked(clone, report(nxt="> **Next** The guard is queued as step:%s." % SLUG))

    def test_red_bare_queued_claim_names_no_step_blocks(self):
        clone = self.repo()
        self.blocked(clone, report(nxt="> **Next** The guard is queued as a roadmap step."))

    def test_red_bare_filed_and_has_a_step_block(self):
        clone = self.repo()
        for text in ("The follow-up is filed as a step.", "The follow-up has a step."):
            with self.subTest(text=text):
                self.blocked(clone, report(nxt="> **Next** " + text))

    # Green: the step is a blob on origin/roadmap.
    def test_green_named_step_on_roadmap_passes(self):
        clone = self.repo(on_roadmap=[SLUG])
        self.passes(clone, report("I misread the inbox; the guard is queued as `step:%s`." % SLUG))
        self.passes(clone, report(nxt="> **Next** The guard is queued as step:%s." % SLUG))

    def test_green_roadmap_step_newer_than_local_view_passes(self):
        # the step lands on origin/roadmap after the clone: only the fetch can see it
        clone = self.repo()
        pusher = os.path.join(self.folder, "pusher")
        git(self.folder, "clone", "-q", "-b", "roadmap", os.path.join(self.folder, "origin.git"), pusher)
        os.makedirs(os.path.join(pusher, "roadmap/data/steps"))
        with open(os.path.join(pusher, STEP_FILE), "w") as handle:
            handle.write("{}")
        git(pusher, "add", "-A")
        git(pusher, "commit", "-qm", "step")
        git(pusher, "push", "-q", "origin", "roadmap")
        self.passes(clone, report(nxt="> **Next** The guard is queued as step:%s." % SLUG))

    # Green: "queued" and "filed" in other senses are no claim about a step (rule verification-cry-wolf-guard-is-spent).
    def test_green_other_senses_of_queued_pass(self):
        clone = self.repo()
        for text in ("The CI run is queued behind two others.",
                     "The PR sits in the merge queue.",
                     "Lane msg-claims-vs-git is queued, waiting for the load brake.",
                     "The CI job step is queued.",
                     "The job was queued and the step that waits for it is slow.",
                     "I filed the report with the batch runner.",
                     "Unstarted: batch 104, queued until the merge lands.",
                     "Unstarted: lane x, queued until step merge-reads-ruleset merges.",
                     "Filed the debt, and the next step is the owner's ruling.",
                     "The batch is queued, and the next step is the merge.",
                     "The hook has a step-by-step recovery in its docstring.",
                     "The lane is queued at step 3 of the batch procedure.",
                     "Proposed as `step:%s`, not filed yet." % SLUG,
                     "Triage will file step:%s." % SLUG):
            with self.subTest(text=text):
                self.passes(clone, report(nxt="> **Next** " + text))

    # Red: a slug cited with an escape word, or with no claim word, is still read from git.
    def test_red_slug_cited_beside_other_sense_word_or_no_claim_word_blocks(self):
        clone = self.repo()
        for text in ("The check is queued as step:%s." % SLUG,
                     "The guard is queued as step:%s, and CI runs on the PR." % SLUG,
                     "`step:%s` awaits the owner's ruling." % SLUG,
                     "The guard was added to the roadmap as step:%s." % SLUG):
            with self.subTest(text=text):
                self.blocked(clone, report(nxt="> **Next** " + text))

    def test_red_claim_words_tied_to_the_step_noun_block(self):
        clone = self.repo()
        for text in ("The guard has a roadmap step.", "The guard is added to the roadmap as a step.",
                     "The step is queued.", "It is queued in the roadmap queue as a step."):
            with self.subTest(text=text):
                self.blocked(clone, report(nxt="> **Next** " + text))

    # A single-branch clone's narrow refspec must not hide a step that is on origin/roadmap.
    def test_green_single_branch_clone_sees_roadmap_step(self):
        clone = self.repo(on_roadmap=[SLUG], single_branch=True)
        self.passes(clone, report(nxt="> **Next** The guard is queued as step:%s." % SLUG))

    def test_red_single_branch_clone_missing_step_blocks(self):
        clone = self.repo(single_branch=True)
        self.blocked(clone, report(nxt="> **Next** The guard is queued as step:%s." % SLUG))

    def test_green_code_span_and_quote_are_no_claim(self):
        clone = self.repo()
        self.passes(clone, report(nxt="> **Next** The word `queued as a step` is in the guard's regex."))
        self.passes(clone, report(nxt='> **Next** The owner wrote "queued as a step" in the inbox.'))

    # Unknown: a fetch that fails is reported as unknown and refuses nothing (rule verification-report-unknown-reads).
    def test_fetch_failure_prints_unknown_and_passes(self):
        clone = self.repo(remote=False)
        err = self.passes(clone, report(nxt="> **Next** The guard is queued as step:%s." % SLUG))
        self.assertIn("unknown", err)

    # Cost: a report that names no step starts no fetch, so a dead origin prints nothing.
    def test_no_step_named_starts_no_fetch(self):
        clone = self.repo(remote=False)
        err = self.passes(clone, report())
        self.assertNotIn("unknown", err)

    # Red: a sentence that names a proposal but claims the step is queued or filed is still read from git.
    def test_red_proposal_word_beside_a_claim_blocks(self):
        clone = self.repo()
        for text in ("The proposed guard is queued as step:fake-one.",
                     "Queued the proposal as step:fake-one.",
                     "I filed step:fake-one, the guard we proposed."):
            with self.subTest(text=text):
                self.blocked(clone, report(nxt="> **Next** " + text))

    # Green: a slug in a negated or future claim is no claim that it is filed.
    def test_green_negated_or_future_slug_passes(self):
        clone = self.repo()
        for text in ("step:fake-one is not yet filed.",
                     "Triage is to file step:fake-one.",
                     "Triage should file step:fake-one.",
                     "Triage can file step:fake-one.",
                     "Triage would file step:fake-one.",
                     "I did not file step:fake-one.",
                     "File step:fake-one for the guard.",
                     "Should I file step:fake-one?",
                     "step:fake-one is missing from the roadmap."):
            with self.subTest(text=text):
                self.passes(clone, report(nxt="> **Next** " + text))

    # Red: a claim with an object between the claim word and the step noun, or beside a CI word, names no slug.
    def test_red_no_slug_claim_with_object_or_other_sense_word_blocks(self):
        clone = self.repo()
        for text in ("I queued the guard as a roadmap step.",
                     "I filed the follow-up as a step.",
                     "Added the guard to the roadmap as a step.",
                     "The step for the guard is queued.",
                     "The check is queued as a roadmap step.",
                     "The follow-up action is queued as a step.",
                     "The guard is queued as a roadmap step and the CI run is green."):
            with self.subTest(text=text):
                self.blocked(clone, report(nxt="> **Next** " + text))

    # Green: a step in normal coding text is no claim about the roadmap (rule verification-cry-wolf-guard-is-spent).
    def test_green_step_in_coding_text_passes(self):
        clone = self.repo()
        for text in ("Added a step to the install script.",
                     "Added a new step to the skill.",
                     "The setup script has a step that installs jq.",
                     "The migration has a step that drops the column.",
                     "The page now has the step list.",
                     "Triage has the step.",
                     "The deploy step is filed under ops.",
                     "The rollout is queued in a new step of the plan.",
                     "Added a CI step and rebuilt the roadmap page.",
                     "The guard reads git, and the setup script has a step for jq."):
            with self.subTest(text=text):
                self.passes(clone, report(nxt="> **Next** " + text))

    # Order: an unbacked sentence does not hide the read of a slug another sentence names.
    def test_red_unbacked_sentence_does_not_hide_missing_slug(self):
        clone = self.repo()
        out, _ = self.run_report(clone, report(nxt="> **Next** Queued as a roadmap step. It is step:%s." % SLUG))
        self.assertIsNotNone(out)
        reason = out.get("reason", "")
        self.assertIn("Queued as a roadmap step", reason)
        self.assertIn("step:%s" % SLUG, reason)
        self.assertEqual(reason.count("Step-cite guard"), 1, reason)

    def test_unbacked_sentence_with_filed_slug_refuses_once_and_named_passes(self):
        clone = self.repo(on_roadmap=[SLUG])
        out, _ = self.run_report(clone, report(nxt="> **Next** Queued as a roadmap step. It is step:%s." % SLUG))
        self.assertIsNotNone(out)
        reason = out.get("reason", "")
        self.assertIn("Queued as a roadmap step", reason)
        self.assertNotIn("holds no step file", reason)
        self.assertEqual(reason.count("Step-cite guard"), 1, reason)
        self.passes(clone, report(nxt="> **Next** Queued as roadmap step:%s. It is step:%s." % (SLUG, SLUG)))

    # The refusal says how it clears, in facts: a filed step named as a slug, or the phrase in backticks.
    def test_reason_says_how_to_clear(self):
        clone = self.repo()
        out, _ = self.run_report(clone, report(nxt="> **Next** The guard is queued as a roadmap step."))
        reason = out.get("reason", "")
        self.assertIn("`step:<slug>`", reason)
        self.assertIn("triage files", reason)
        self.assertIn("backticks", reason)


if __name__ == "__main__":
    unittest.main()
