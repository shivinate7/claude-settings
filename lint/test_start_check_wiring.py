#!/usr/bin/env python3
"""The wiring of hooks/start_check.py in settings.json: one command runs it, on SessionStart only, with a matcher
that fires on a startup and on no other source, shaped like the SessionStart commands beside it.
Run: python3 lint/test_start_check_wiring.py. Reads settings.json at the repository root.
"""
import json
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS = os.environ.get("SETTINGS_UNDER_TEST") or os.path.join(HERE, "..", "settings.json")
HOOK_NAME = "start_check.py"
SOURCES = ("startup", "resume", "compact", "clear", "fork")


def load_settings():
    with open(SETTINGS, encoding="utf-8") as handle:
        return json.load(handle)


def command_hooks(settings):
    """(event, matcher, hook) for every command hook in settings.json, in every event."""
    found = []
    for event, groups in settings.get("hooks", {}).items():
        for group in groups:
            for hook in group.get("hooks", []):
                found.append((event, group.get("matcher"), hook))
    return found


def start_check_hooks(settings):
    return [(event, matcher, hook) for event, matcher, hook in command_hooks(settings)
            if HOOK_NAME in hook.get("command", "")]


class StartCheckWiring(unittest.TestCase):
    def setUp(self):
        self.settings = load_settings()
        self.found = start_check_hooks(self.settings)

    def test_one_command_runs_the_hook_and_it_sits_on_session_start(self):
        self.assertTrue(self.settings.get("hooks", {}).get("SessionStart"),
                        "scope: settings.json has no SessionStart entries")
        events = [event for event, _, _ in self.found]
        self.assertEqual(events, ["SessionStart"],
                         "want exactly one command that runs %s, on SessionStart; found it on %r" % (HOOK_NAME, events))

    def test_its_matcher_is_startup_and_fires_on_no_other_source(self):
        self.assertEqual(len(self.found), 1, "scope: no single command runs %s" % HOOK_NAME)
        matcher = self.found[0][1]
        self.assertEqual(matcher, "startup", "the %s command's matcher is %r, want startup" % (HOOK_NAME, matcher))
        for source in SOURCES:
            with self.subTest(source=source):
                fires = re.fullmatch(matcher, source) is not None
                self.assertEqual(fires, source == "startup",
                                 "the %s matcher fires on %s: %s" % (HOOK_NAME, source, fires))

    def test_command_is_shaped_like_its_neighbours(self):
        self.assertEqual(len(self.found), 1, "scope: no single command runs %s" % HOOK_NAME)
        command = self.found[0][2].get("command", "")
        self.assertIn("hooks/%s" % HOOK_NAME, command, "the command does not run hooks/%s" % HOOK_NAME)
        self.assertIn('[ -f "$g" ] || exit 0', command, "the command does not exit 0 when the script is missing")
        self.assertIn("for p in python3 python", command, "the command does not look for python3, then python")
        self.assertTrue(command.rstrip().endswith("exit 0"), "the command does not end with exit 0")
        self.assertNotIn("exit 2", command, "the command can exit 2, which blocks the session")

    def test_timeout_is_a_short_positive_number_of_seconds(self):
        self.assertEqual(len(self.found), 1, "scope: no single command runs %s" % HOOK_NAME)
        timeout = self.found[0][2].get("timeout")
        self.assertTrue(isinstance(timeout, int) and not isinstance(timeout, bool) and 0 < timeout <= 10,
                        "the %s command's timeout is %r, want 1 to 10 seconds like its neighbours" % (HOOK_NAME, timeout))


if __name__ == "__main__":
    unittest.main(verbosity=2)
