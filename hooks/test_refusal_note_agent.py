#!/usr/bin/env python3
"""Cases for hooks/refusal_note.py: the row it writes for a refused call (roadmap step
report-guard-refusal-right; decision refusals-reach-the-owner).

Each row carries the payload's tool_use_id, and the payload's agent_id when the payload has one. The hook
still writes a subagent's row, so the Stop side can tell it apart: lint/report_guard.py drops such a row
at Stop (lint/test_report_guard_refusal.py). The orchestrator's row carries no agent_id.

Run it from the repository root:

    python3 hooks/test_refusal_note_agent.py

Standard library only. The hook harness (HookCase, fire, refusal_rows) is the one in
hooks/test_refusal_note.py, subclassed here so no case is copied.
"""
import os
import shutil
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_refusal_note as base  # noqa: E402  the hook harness (HookCase), one home

ARCHIVE = base.ARCHIVE
CREATE = "mcp__claude-code-remote__create_session"
INTERRUPT = "mcp__claude-code-remote__interrupt_session"
AGENT_ID = "a1b2c3d4e5f6a7b8c"  # 17 hex characters, the shape hooks/guard.py measured for agent ids


def tearDownModule():
    # Importing the harness made its run folder; this module removes it, since the harness's teardown does not run here.
    shutil.rmtree(base.RUN, ignore_errors=True)


def short(tool):
    return tool.rsplit("__", 1)[-1]


class RefusalRowTests(base.HookCase):
    def refusal_of(self, tool, use_id):
        return self.refusal(tool=tool, use_id=use_id,
                            reason="Permission for %s was denied by the auto-mode classifier." % short(tool))

    def agent_refusal(self, tool, use_id):
        data = self.refusal_of(tool, use_id)
        data["agent_id"] = AGENT_ID
        data["agent_type"] = "builder"
        return data

    def rows(self):
        return self.refusal_rows(skip_bad=True)

    def test_h1_a_subagent_row_carries_its_agent_id_and_tool_use_id(self):
        run = self.fire(self.agent_refusal(CREATE, "toolu_agent_1"))
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.strip(), "", "the hook printed on a subagent's refusal: %r" % run.stdout)
        rows = self.rows()
        self.assertEqual([row["tool_name"] for row in rows], [CREATE],
                         "scope: the subagent's refusal was not written to the scratch refusals file")
        self.assertEqual(rows[0].get("agent_id"), AGENT_ID,
                         "the row for a subagent's refusal carries no agent_id: %r" % rows[0])
        self.assertEqual(rows[0].get("tool_use_id"), "toolu_agent_1",
                         "the row for a subagent's refusal carries no tool_use_id: %r" % rows[0])

    def test_h2_an_orchestrator_row_carries_its_tool_use_id(self):
        run = self.fire(self.refusal_of(ARCHIVE, "toolu_m2"))
        self.assertEqual(run.returncode, 0, run.stderr)
        rows = self.rows()
        self.assertEqual([row["tool_name"] for row in rows], [ARCHIVE],
                         "scope: the orchestrator's refusal was not written to the scratch refusals file")
        self.assertEqual(rows[0].get("tool_use_id"), "toolu_m2",
                         "the orchestrator's row carries no tool_use_id: %r" % rows[0])

    def test_h3_an_orchestrator_row_has_no_agent_id(self):
        run = self.fire(self.refusal_of(ARCHIVE, "toolu_m3"))
        self.assertEqual(run.returncode, 0, run.stderr)
        rows = self.rows()
        self.assertEqual([row["tool_name"] for row in rows], [ARCHIVE],
                         "scope: the orchestrator's refusal was not written to the scratch refusals file")
        self.assertNotIn("agent_id", rows[0], "an orchestrator's row names an agent: %r" % rows[0])

    def test_h4_an_orchestrator_refusal_is_recorded_after_a_subagent_refused_the_same_tool(self):
        self.fire(self.agent_refusal(CREATE, "toolu_agent_4"))
        self.assertEqual([row["tool_name"] for row in self.rows()], [CREATE],
                         "scope: the subagent's refusal was not written to the scratch refusals file")
        run = self.fire(self.refusal_of(CREATE, "toolu_m4"))
        self.assertEqual(run.returncode, 0, run.stderr)
        mine = [row for row in self.rows() if row.get("tool_use_id") == "toolu_m4"]
        self.assertEqual(len(mine), 1,
                         "the orchestrator's refusal of a tool a subagent had refused was not recorded: %r"
                         % self.rows())
        self.assertNotIn("agent_id", mine[0], "the orchestrator's row names an agent: %r" % mine[0])


if __name__ == "__main__":
    unittest.main()
