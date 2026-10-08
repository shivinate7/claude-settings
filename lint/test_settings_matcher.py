#!/usr/bin/env python3
"""The PreToolUse matcher that routes to hooks/guard.py must cover every tool the guard judges.
Run: python3 lint/test_settings_matcher.py. Without Workflow and start_session in the matcher,
the guard's subagent-model-floor never sees those calls.
"""
import json, os, re, unittest

SETTINGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "settings.json")


def guard_matchers():
    entries = json.load(open(SETTINGS))["hooks"]["PreToolUse"]
    return [e["matcher"] for e in entries
            if any("guard.py" in h.get("command", "") for h in e["hooks"])]


class Matcher(unittest.TestCase):
    def test_guard_matcher_covers_model_floor_tools(self):
        matchers = guard_matchers()
        self.assertTrue(matchers)
        for tool in ("Agent", "Task", "Workflow", "mcp__ccd_session__start_session"):
            with self.subTest(tool=tool):
                self.assertTrue(any(re.fullmatch(m, tool) for m in matchers))


if __name__ == "__main__":
    unittest.main()
