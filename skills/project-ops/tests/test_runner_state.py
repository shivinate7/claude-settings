#!/usr/bin/env python3
"""Cases for skills/project-ops/scripts/check_runner_state.py. Standard library only.

    python3 skills/project-ops/tests/test_runner_state.py

The batch runner keeps its working state in one file on the record branch. Triage is the one writer of that
branch (rule roadmap-one-writer), so the runner sends the whole file to triage in one message per merge. The
cases prove: the seed file is valid; each field the runner needs is required; a hold with no end event is
refused; a message whose header disagrees with its file is refused; a handoff that copies the list is
refused; and a runner state survives a compaction, read back from the file alone (decision runner-state-on-record).
They also prove: which handoff lines copy the list; the first send from the seed, with no committed file yet; a
fenced message body; the end events that are placeholders; the stale text when no merge is recorded; and the
runner, triage and decision wording.
"""
import inspect
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SKILL, "scripts"))
try:
    import check_runner_state as crs  # noqa: E402
except ModuleNotFoundError as e:  # Only a missing check_runner_state.py: a broken one must fail loud.
    if e.name != "check_runner_state":
        raise
    crs = None

SEED = os.path.join(SKILL, "templates", "runner-state.json")
HOME = "origin/roadmap:plans/runner-state.json"


def need():
    if crs is None:
        raise AssertionError("skills/project-ops/scripts/check_runner_state.py does not exist")
    return crs


def seed_text():
    with open(SEED, encoding="utf-8") as f:
        return f.read()


def seed_state():
    return json.loads(seed_text())


def good_state():
    return {
        "schema": 1, "repo": "owner/repo", "version": 4,
        "writtenAt": "2026-11-13T23:10:00-06:00", "runner": "session_x",
        "afterMerge": {"pr": 3302, "commit": "0123456789ab"},
        "queue": [{"pr": 3323, "head": "82e38f96ece1", "path": "alone"},
                  {"pr": 3314, "head": "f5a4f4e872b8", "path": "fold:g1"}],
        "folds": [{"id": "g1", "pr": 3356, "base": "main", "members": [3314, 3315]}],
        "gos": [{"pr": 3323, "by": "coordinator-relay", "at": "2026-11-13T22:30:00-06:00"}],
        "holds": [{"pr": 2881, "reason": "round 3 owed", "endsOn": "fix verifier posts PASS"}],
        "archivePass": {"lastRunAt": "2026-11-13T23:00:00-06:00", "pending": ["lane-a"]},
    }


def message_for(state, fence=None):
    head = f"RUNNER-STATE {state['repo']} v{state['version']} after merge #{state['afterMerge']['pr']}"
    body = json.dumps(state, indent=1)
    if fence is not None:  # the body in a code fence whose info string is `fence` ("" for none)
        body = f"```{fence}\n{body}\n```"
    return head + "\n" + body


def handoff(version=4, extra=""):
    return ("# Runner handoff\n\n## Goal\nMerge in wave order.\n\n## Where things stand\n"
            f"Runner state: {HOME}, last sent version {version}.\n{extra}\n## Next steps\nRe-read the file.\n")


class SeedAndState(unittest.TestCase):
    def test_seed_is_valid(self):
        with open(SEED, encoding="utf-8") as f:
            seed = json.load(f)
        self.assertEqual(need().state_problems(seed), [])

    def test_good_state_passes(self):
        self.assertEqual(need().state_problems(good_state()), [])

    def test_each_field_is_required(self):
        for key in good_state():
            s = good_state()
            del s[key]
            self.assertTrue(need().state_problems(s), f"missing {key} passed")

    def test_hold_needs_an_end_event(self):
        s = good_state()
        s["holds"][0]["endsOn"] = ""
        self.assertTrue(need().state_problems(s))

    def test_queue_path_must_name_a_fold(self):
        s = good_state()
        s["queue"][1]["path"] = "fold:nope"
        self.assertTrue(need().state_problems(s))

    def test_duplicate_queue_pr_refused(self):
        s = good_state()
        s["queue"].append(dict(s["queue"][0]))
        self.assertTrue(need().state_problems(s))

    def test_time_needs_a_zone(self):
        s = good_state()
        s["writtenAt"] = "2026-11-13T23:10:00"
        self.assertTrue(need().state_problems(s))


class Message(unittest.TestCase):
    def test_good_message_passes(self):
        self.assertEqual(need().message_problems(message_for(good_state())), [])

    def test_header_version_must_match_file(self):
        text = message_for(good_state()).replace(" v4 ", " v5 ", 1)
        self.assertTrue(need().message_problems(text))

    def test_header_pr_must_match_file(self):
        text = message_for(good_state()).replace("after merge #3302", "after merge #9", 1)
        self.assertTrue(need().message_problems(text))

    def test_body_must_be_json(self):
        self.assertTrue(need().message_problems("RUNNER-STATE owner/repo v4 after merge #3302\nnot json"))


class Handoff(unittest.TestCase):
    def test_pointer_handoff_passes(self):
        self.assertEqual(need().handoff_problems(handoff()), [])

    def test_missing_pointer_refused(self):
        self.assertTrue(need().handoff_problems("# Runner handoff\n\n## Goal\nx\n"))

    def test_copied_queue_refused(self):
        self.assertTrue(need().handoff_problems(handoff(extra="Queue: #3323, #3314, #3315\n")))

    def test_copied_holds_refused(self):
        self.assertTrue(need().handoff_problems(handoff(extra="Holds: #2881 until PASS\n")))

    def problems_of(self, line):
        return need().handoff_problems(handoff(extra=line + "\n"))

    def test_pass_holds_reviewed_at_time(self):
        self.assertEqual(self.problems_of("Holds were reviewed at 23:10 for lane 205."), [])

    def test_pass_go_merge_first(self):
        self.assertEqual(self.problems_of("Go merge PR 3359 first."), [])

    def test_pass_queue_the_merge_next(self):
        self.assertEqual(self.problems_of("Queue the merge of lane 3359 next."), [])

    def test_pass_folds_rebuilt_after_merge(self):
        self.assertEqual(self.problems_of("Folds are rebuilt by triage after lane 3359 merges."), [])

    def test_refuse_merge_queue_label_with_refs(self):
        self.assertTrue(self.problems_of("Merge queue: #3323, #3314"), "a queue copy with PR refs passed")

    def test_refuse_queue_label_over_bullets(self):
        self.assertTrue(self.problems_of("Queue:\n- #3323\n- #3314"), "a queue label over a bullet block of refs passed")

    def test_refuse_held_label_with_bare_number(self):
        self.assertTrue(self.problems_of("Held: 3359 until round 3 is posted"), "a held label with a PR number passed")

    def test_refuse_queue_with_short_numbers(self):
        self.assertTrue(self.problems_of("Queue: #12, #15"), "a queue copy with two-digit PR numbers passed")

    def test_refuse_pr_sequence_in_prose(self):
        self.assertTrue(self.problems_of("- PR 3323 is next, then 3314, then 3315"), "a PR sequence in prose passed")


class Compaction(unittest.TestCase):
    """A compaction drops everything but the handoff. The successor must rebuild each field from the file."""

    def committed(self, state):
        # Triage's commit: the message body, written whole, at the home ref.
        body = message_for(state).split("\n", 1)[1]
        return lambda ref: body if ref == HOME else None

    def test_state_survives_compaction(self):
        state = good_state()
        recovered = need().recover(handoff(version=state["version"]), self.committed(state))
        self.assertEqual(recovered, state)

    def test_stale_committed_file_is_named(self):
        state = good_state()
        newer = handoff(version=state["version"] + 1)
        with self.assertRaises(need().Stale):
            need().recover(newer, self.committed(state))

    def test_unreadable_home_is_unknown_not_empty(self):
        with self.assertRaises(need().Unknown):
            need().recover(handoff(), lambda ref: None)

    def test_handoff_holds_no_field_of_the_state(self):
        state = good_state()
        text = handoff(version=state["version"])
        for pr in (3323, 3314, 3315, 2881):
            self.assertNotIn(str(pr), text)

    def test_corrupt_committed_file_is_refused(self):
        state = good_state()
        bad = json.dumps({k: v for k, v in state.items() if k != "queue"})
        with self.assertRaises(need().Unknown):
            need().recover(handoff(version=4), lambda ref: bad)

    def test_stale_with_no_merge_says_first_state(self):
        self.assertEqual(need().state_problems(seed_state()), [], "the seed is not a valid state")
        with self.assertRaises(need().Stale) as cm:
            need().recover(handoff(version=1), lambda ref: seed_text())
        self.assertIn("no merge recorded yet: send the first state", str(cm.exception))

    def test_stale_with_no_merge_never_says_after_commit_none(self):
        self.assertEqual(need().state_problems(seed_state()), [], "the seed is not a valid state")
        with self.assertRaises(need().Stale) as cm:
            need().recover(handoff(version=1), lambda ref: seed_text())
        self.assertNotIn("after commit None", str(cm.exception))


class AgainstCommitted(unittest.TestCase):
    """Triage holds the committed file. A message is judged against it, so a reset cannot overwrite live state."""

    def newer(self, **over):
        s = good_state()
        s["version"] = 5
        s["afterMerge"] = {"pr": 3323, "commit": "aaaaaaaaaaaa"}
        s["queue"] = [s["queue"][1]]
        s.update(over)
        return s

    def judge(self, new, old=None, fence=None):
        return need().message_problems(message_for(new, fence), committed=json.dumps(old or good_state()))

    def test_next_version_passes(self):
        self.assertEqual(self.judge(self.newer()), [])

    def test_reset_from_seed_refused(self):
        seed = good_state()
        seed.update(version=1, queue=[], holds=[], folds=[], gos=[])
        self.assertTrue(self.judge(seed))

    def test_skipped_version_refused(self):
        self.assertTrue(self.judge(self.newer(version=7)))

    def test_same_version_refused(self):
        self.assertTrue(self.judge(self.newer(version=4)))

    def test_merged_pr_must_leave_queue(self):
        s = self.newer()
        s["afterMerge"] = {"pr": 3314, "commit": "aaaaaaaaaaaa"}
        self.assertTrue(self.judge(s))

    def test_unreadable_committed_is_unknown(self):
        with self.assertRaises(need().Unknown):
            need().message_problems(message_for(good_state()), committed="not json")

    def test_fenced_json_body_passes(self):
        self.assertEqual(self.judge(self.newer(), fence="json"), [])

    def test_fenced_bare_body_passes(self):
        self.assertEqual(self.judge(self.newer(), fence=""), [])


class FirstSend(unittest.TestCase):
    """The bootstrap: no state file is committed yet, so the runner sends v1 built from the seed."""

    def judge(self, state, first):
        """Passes `first` only once the keyword exists. Before that the call takes the default, so the red shows
        what the check does without it, not a TypeError."""
        fn = need().message_problems
        if "first" in inspect.signature(fn).parameters:
            return fn(message_for(state), committed=None, first=first)
        return fn(message_for(state), committed=None)

    def first_state(self, version):
        s = seed_state()
        s.update(version=version, afterMerge={"pr": 3302, "commit": "0123456789ab"})
        return s

    def test_absent_committed_is_unknown(self):
        with self.assertRaises(need().Unknown):
            self.judge(good_state(), first=False)

    def test_first_send_accepts_only_version_one(self):
        self.assertEqual(self.judge(self.first_state(1), first=True), [])
        self.assertTrue(self.judge(self.first_state(2), first=True), "a version 2 sent as the first state passed")


class Tightened(unittest.TestCase):
    def test_placeholder_end_event_refused(self):
        for word in ("TBD", "none", "n/a", "unknown", "?"):
            s = good_state()
            s["holds"][0]["endsOn"] = word
            self.assertTrue(need().state_problems(s), word)

    def test_after_merge_types(self):
        s = good_state()
        s["afterMerge"] = {"pr": "x", "commit": 5}
        self.assertTrue(need().state_problems(s))

    def test_archive_pending_items_are_strings(self):
        s = good_state()
        s["archivePass"]["pending"] = [1, None]
        self.assertTrue(need().state_problems(s))

    def test_copy_forms_refused(self):
        for line in ("Queue: 3323, 3314", "**Queue:** #3323", "- Holds: #2881", "Queue (3): #3323",
                     "Folds: g1 = 3314 3315"):
            self.assertTrue(need().handoff_problems(handoff(extra=line + "\n")), line)

    def test_pointer_must_name_the_record_branch(self):
        text = handoff().replace("origin/roadmap:", "origin/main:")
        self.assertTrue(need().handoff_problems(text))

    def test_stale_names_the_way_back(self):
        state = good_state()
        committed = lambda ref: json.dumps(state)  # noqa: E731
        with self.assertRaises(need().Stale) as cm:
            need().recover(handoff(version=5), committed)
        self.assertIn(state["afterMerge"]["commit"], str(cm.exception))

    def test_end_event_with_punctuation_placeholder_refused(self):
        s = good_state()
        s["holds"][0]["endsOn"] = "fix verifier posts PASS."
        self.assertEqual(need().state_problems(s), [], "a real end event with a period was refused")
        for word in ("TBD.", "n/a!", "?!", "todo;", "unknown.", "none!"):
            s["holds"][0]["endsOn"] = word
            self.assertTrue(need().state_problems(s), f"end event {word!r} passed")

    def test_vague_end_event_words_refused(self):
        for word in ("later", "soon", "pending", "x"):
            s = good_state()
            s["holds"][0]["endsOn"] = word
            self.assertTrue(need().state_problems(s), f"end event {word!r} passed")


class DutiesNamed(unittest.TestCase):
    def read(self, *parts):
        with open(os.path.join(SKILL, "..", "..", *parts), encoding="utf-8") as f:
            return f.read()

    def test_triage_bullet_names_the_message(self):
        text = self.read("skills", "project-ops", "templates", "operating-model.md")
        triage = text[text.index("- **Triage.**"):text.index("- **Batch runner.**")]
        self.assertIn("RUNNER-STATE", triage)
        self.assertIn("check_runner_state.py", triage)

    def test_runner_duty_names_channel_fetch_and_answer(self):
        text = self.read("skills", "project-ops", "templates", "operating-model.md")
        runner = text[text.index("- **Batch runner.**"):text.index("- **Lane.**")]
        for word in ("send_message", "git fetch origin roadmap", "answer", "check_runner_state.py handoff"):
            self.assertIn(word, runner)

    def section(self, start, end):
        text = self.read("skills", "project-ops", "templates", "operating-model.md")
        self.assertIn(start, text, f"operating-model.md has no {start} duty")  # scope before subject
        self.assertIn(end, text, f"operating-model.md has no {end} duty")
        return text[text.index(start):text.index(end)]

    def test_runner_start_names_recover(self):
        runner = self.section("- **Batch runner.**", "- **Lane.**")
        self.assertIn("check_runner_state.py recover", runner, "the batch runner's start step names no recover call")

    def test_runner_start_names_the_seed_when_file_absent(self):
        runner = self.section("- **Batch runner.**", "- **Lane.**")
        self.assertIn("absent", runner, "the batch runner's start step says nothing about an absent state file")
        self.assertIn("templates/runner-state.json", runner, "the batch runner's start step names no seed for v1")

    def test_triage_names_first(self):
        triage = self.section("- **Triage.**", "- **Batch runner.**")
        self.assertIn("--first", triage, "the triage duty names no --first send")

    def test_triage_first_only_when_file_absent(self):
        triage = self.section("- **Triage.**", "- **Batch runner.**")
        self.assertIn("absent", triage, "the triage duty does not limit --first to an absent state file")


class WiredIn(unittest.TestCase):
    def read(self, *parts):
        with open(os.path.join(SKILL, "..", "..", *parts), encoding="utf-8") as f:
            return f.read()

    def test_prompt_step_names_the_file(self):
        self.assertIn("plans/runner-state.json", self.read("hooks", "precompact_handoff_prompt.md"))

    def test_runner_duty_names_message_and_reread(self):
        text = self.read("skills", "project-ops", "templates", "operating-model.md")
        self.assertIn("RUNNER-STATE", text)
        self.assertIn("plans/runner-state.json", text)

    def test_ci_runs_this_suite(self):
        self.assertIn("test_runner_state.py", self.read(".github", "workflows", "checks.yml"))

    def ceiling_line(self, *words):
        text = self.read("docs", "decisions", "runner-state-on-record.md")
        self.assertIn("## Cost", text, "the decision has no Cost section")  # scope before subject
        cost = text[text.index("## Cost"):].split("\nKind:", 1)[0]
        lines = [line.lower() for line in cost.splitlines() if "ceiling" in line.lower()]
        self.assertTrue(any(all(w in line for w in words) for line in lines),
                        f"the decision's Cost section has no ceiling line naming {' and '.join(words)}")

    def test_cost_names_the_hold_ceiling(self):
        self.ceiling_line("hold", "compaction")

    def test_cost_names_the_repo_and_queue_ceiling(self):
        self.ceiling_line("repo", "queue")


if __name__ == "__main__":
    unittest.main()
