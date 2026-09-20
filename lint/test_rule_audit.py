#!/usr/bin/env python3
"""Fixture tests for rule_audit.py.

Each test builds a small CLAUDE.md fragment, a map, and (when it matters) a guard.py or
gates.yml fragment in memory, then calls `check(...)` directly. No subprocess: the audit
itself does not touch the transcript or the hook protocol the way ste_gate/report_gate do.

Run with:

    python3 lint/test_rule_audit.py -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rule_audit  # noqa: E402

GUARD_SRC = '''
def dispatch():
    refuse(tool, "deny", "shared-tree", REASON, matched)
    refuse(tool, "ask", "subagent-model-cap", REASON, matched)
    record(tool, "noted", "merge-main", matched)
'''

WORKFLOW_SRC = '''
jobs:
  gates:
    steps:
      - name: Guard fixture suite
        run: python3 hooks/test_guard.py
'''

GOOD_MD = (
    "**Shared trees.** Never run `git stash` in a shared checkout."
    "<!-- rule:shared-trees-no-destructive-git -->\n"
)
GOOD_MAP = {
    "rules": {
        "shared-trees-no-destructive-git": {
            "mechanism": {"kind": "guard", "ref": "shared-tree"}
        }
    }
}


def run(md=GOOD_MD, rule_map=None, guard=GUARD_SRC, workflow=WORKFLOW_SRC,
        rule_floor=1, unmechanized_expected=None):
    """Call check() with small pins sized to the fixture, not this repo's real numbers."""
    if rule_map is None:
        rule_map = GOOD_MAP
    if unmechanized_expected is None:
        rules = rule_map.get("rules", {})
        unmechanized_expected = sum(
            1 for r in rules.values()
            if isinstance(r, dict) and (r.get("mechanism") or {}).get("kind") == "unmechanized"
        )
    return rule_audit.check(md, rule_map, guard, workflow, rule_floor, unmechanized_expected)


class RuleAuditTests(unittest.TestCase):

    def test_single_mapped_rule_is_clean(self):
        problems = run()
        self.assertEqual(problems, [])

    def test_new_rule_with_no_row_fails_and_names_it(self):
        md = GOOD_MD + "**New.** Never skip the review.<!-- rule:new-never-skip-review -->\n"
        problems = run(md=md)
        self.assertTrue(any("new-never-skip-review" in p and "no row" in p for p in problems),
                         problems)

    def test_row_naming_a_dead_guard_rule_fails_as_stale(self):
        rule_map = {
            "rules": {
                "shared-trees-no-destructive-git": {
                    "mechanism": {"kind": "guard", "ref": "does-not-exist"}
                }
            }
        }
        problems = run(rule_map=rule_map)
        self.assertTrue(any("does-not-exist" in p and "Stale row" in p for p in problems),
                         problems)

    def test_row_naming_a_real_guard_rule_passes(self):
        rule_map = {
            "rules": {
                "shared-trees-no-destructive-git": {
                    "mechanism": {"kind": "guard", "ref": "subagent-model-cap"}
                }
            }
        }
        problems = run(rule_map=rule_map)
        self.assertEqual(problems, [])

    def test_row_naming_a_missing_gate_file_fails(self):
        rule_map = {
            "rules": {
                "shared-trees-no-destructive-git": {
                    "mechanism": {"kind": "gate", "ref": "lint/does_not_exist.py"}
                }
            }
        }
        problems = run(rule_map=rule_map)
        self.assertTrue(any("does_not_exist.py" in p for p in problems), problems)

    def test_row_naming_a_real_gate_file_with_stale_needle_fails(self):
        rule_map = {
            "rules": {
                "shared-trees-no-destructive-git": {
                    "mechanism": {
                        "kind": "gate",
                        "ref": "lint/rule_audit.py",
                        "needle": "this text will never appear in the file",
                    }
                }
            }
        }
        problems = run(rule_map=rule_map)
        self.assertTrue(any("Stale row" in p for p in problems), problems)

    def test_row_naming_a_dead_ci_step_fails(self):
        rule_map = {
            "rules": {
                "shared-trees-no-destructive-git": {
                    "mechanism": {"kind": "ci", "ref": "Step that does not exist"}
                }
            }
        }
        problems = run(rule_map=rule_map)
        self.assertTrue(any("Step that does not exist" in p for p in problems), problems)

    def test_row_naming_a_real_ci_step_passes(self):
        rule_map = {
            "rules": {
                "shared-trees-no-destructive-git": {
                    "mechanism": {"kind": "ci", "ref": "Guard fixture suite"}
                }
            }
        }
        problems = run(rule_map=rule_map)
        self.assertEqual(problems, [])

    def test_unmechanized_with_a_thin_reason_fails(self):
        rule_map = {
            "rules": {
                "shared-trees-no-destructive-git": {
                    "mechanism": {"kind": "unmechanized", "reason": "no reason"}
                }
            }
        }
        problems = run(rule_map=rule_map)
        self.assertTrue(any("rubber stamp" in p for p in problems), problems)

    def test_orphaned_row_with_no_anchor_left_fails(self):
        rule_map = {
            "rules": {
                "shared-trees-no-destructive-git": {
                    "mechanism": {"kind": "guard", "ref": "shared-tree"}
                },
                "a-deleted-rule": {
                    "mechanism": {
                        "kind": "unmechanized",
                        "reason": "This rule was removed from CLAUDE.md but its row was left behind by mistake.",
                    }
                },
            }
        }
        problems = run(rule_map=rule_map)
        self.assertTrue(any("a-deleted-rule" in p and "no rule anchor" in p for p in problems),
                         problems)

    def test_floor_catches_a_shrunk_reader(self):
        problems = run(rule_floor=5)
        self.assertTrue(any("fewer than the pinned floor" in p for p in problems), problems)

    def test_unmechanized_pin_catches_a_silent_drop(self):
        rule_map = {
            "rules": {
                "shared-trees-no-destructive-git": {
                    "mechanism": {
                        "kind": "unmechanized",
                        "reason": "Nothing enforces this yet, written out at enough length.",
                    }
                }
            }
        }
        problems = run(rule_map=rule_map, unmechanized_expected=0)
        self.assertTrue(any("more than the pinned 0" in p for p in problems), problems)

    def test_the_real_claude_md_and_map_pass_together(self):
        """The check this repo actually ships, over the files it actually ships, at its
        actual pinned floor and unmechanized count -- no override."""
        claude_text = rule_audit.read(rule_audit.CLAUDE_MD)
        rule_map = __import__("json").loads(rule_audit.read(rule_audit.MAP_FILE))
        guard_text = rule_audit.read(rule_audit.GUARD_PY)
        workflow_text = rule_audit.read(rule_audit.WORKFLOW)
        problems = rule_audit.check(claude_text, rule_map, guard_text, workflow_text)
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
