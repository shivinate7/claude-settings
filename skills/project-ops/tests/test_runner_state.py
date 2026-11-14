#!/usr/bin/env python3
"""Cases for skills/project-ops/scripts/check_runner_state.py. Standard library only.

    python3 skills/project-ops/tests/test_runner_state.py

The batch runner keeps its working state in one file on the record branch. Triage is the one writer of that
branch (rule roadmap-one-writer), so the runner sends the whole file to triage in one message per merge. The
cases prove: the seed file is valid; each field the runner needs is required; a hold with no end event is
refused; a message whose header disagrees with its file is refused; a handoff that copies the list is
refused; and a runner state survives a compaction, read back from the file alone (decision runner-state-on-record).
"""
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


def message_for(state):
    head = f"RUNNER-STATE {state['repo']} v{state['version']} after merge #{state['afterMerge']['pr']}"
    return head + "\n" + json.dumps(state, indent=1)


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


if __name__ == "__main__":
    unittest.main()
