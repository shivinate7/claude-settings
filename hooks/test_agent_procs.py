#!/usr/bin/env python3
"""Cases for hooks/agent_procs.py, the one home of the per-agent process record (step agent-owned-processes),
and for the cost of the agent marker on the tool-call path. Standard library only, `unittest`.

Run it from the repository root:

    python3 hooks/test_agent_procs.py

Where the cases live. The record's behaviour is judged where it acts: the SubagentStop cases and the stop-list cases
are in janitor/test_sweep.py (class AgentOwnedProcessTests, extending the agent-end fixture), the kill-only-yours
cases are in tests/guard/s71834-agent-owned-kill.py, and the simulator lease cases are in lint/test_sim_lease.py
(class LeaseRecord). This file holds the cases that need the new module's own functions: the Office adapter and the
visible-window rule, which take injected process lists so they run on Linux. Those cases have no entry point on the
base, so they FAIL there on `hooks/agent_procs.py does not exist yet`. That failure is not a red (test-practices P3);
the post-build mutant is what proves them.

The cost case is a control: it passes on the base, because the recording adds nothing to the tool-call path today.
It pins the stated number, zero process starts, so a recording that starts a process there fails it.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import stall_watch  # noqa: E402  the tool-call path the cost pin counts (hooks/stall_watch.py)

try:
    import agent_procs  # noqa: E402  the one home of the per-agent record (hooks/agent_procs.py); absent on the base
except ImportError:
    agent_procs = None

AGENT = "5c0a1e7d93b2f4860"  # 17 hex characters, the id the marker carries
OFFICE_IMAGES = ("EXCEL.EXE", "POWERPNT.EXE", "WINWORD.EXE")


def need_module(case):
    """Fail the case with the one named cause when the module is not there yet."""
    case.assertIsNotNone(agent_procs, "hooks/agent_procs.py does not exist yet: no Office adapter, no visible-window rule")


class OfficeAdapter(unittest.TestCase):
    """Item 8 and 6 (visible window): the Office adapter diffs the three Office images before and after the agent's
    run (COM-started Office has DcomLaunch as its parent, so a parent check cannot find it). Off Windows, or when no
    Office process runs, it exits early and starts nothing. These cases inject the process lists."""

    def test_the_office_diff_names_the_office_pid_the_agent_started(self):
        need_module(self)
        before = {100: "bash.exe"}
        after = {100: "bash.exe", 4242: "EXCEL.EXE", 4243: "notepad.exe"}
        self.assertEqual(agent_procs.office_started(before, after), [4242],
                         "the diff does not name the one new Office pid, 4242")

    def test_off_windows_the_office_adapter_reads_no_process_list(self):
        need_module(self)
        reads = []

        def lister():
            reads.append(1)
            return {4242: "EXCEL.EXE"}

        self.assertIsNone(agent_procs.office_snapshot("linux", lister), "the adapter took a snapshot off Windows")
        self.assertEqual(reads, [], "the adapter read the process list off Windows")

    def test_on_windows_with_no_office_process_the_adapter_exits_early(self):
        need_module(self)
        self.assertIsNone(agent_procs.office_snapshot("win32", lambda: {100: "bash.exe"}),
                          "the adapter took a snapshot with no Office process running")

    def test_a_visible_window_or_a_start_that_differs_is_reported_and_never_ended(self):
        need_module(self)
        candidates = [
            {"pid": 4242, "owner": AGENT, "visible": True, "start_ok": True},
            {"pid": 4300, "owner": None, "visible": False, "start_ok": True},
            {"pid": 4400, "owner": AGENT, "visible": False, "start_ok": False},
        ]
        self.assertEqual(agent_procs.plan_ends(candidates, AGENT), [],
                         "a visible, unclear or reused pid is in the stop plan")


class ToolCallPathCost(unittest.TestCase):
    """Item 10 (control): the stall_watch call that carries the agent marker starts no process. The count runs on the
    tool-call path, the hook itself, so a recording added there that starts one fails this pin."""

    def test_a_background_call_with_an_agent_id_starts_no_process(self):
        if os.name != "posix":
            self.skipTest("the stall_watch hook is posix only: it returns before any rewrite elsewhere")
        call = {"tool_name": "Bash", "agent_id": AGENT,
                "tool_input": {"command": "sleep 1", "run_in_background": True, "description": "pin"}}
        starts = []
        real_popen = subprocess.Popen

        class CountingPopen(real_popen):
            def __init__(self, *args, **kwargs):
                starts.append(args[0] if args else kwargs.get("args"))
                super().__init__(*args, **kwargs)

        out = io.StringIO()
        with mock.patch.object(subprocess, "Popen", CountingPopen), \
                mock.patch.object(sys, "stdin", io.StringIO(json.dumps(call))), \
                contextlib.redirect_stdout(out):
            stall_watch.hook()
        command = json.loads(out.getvalue())["hookSpecificOutput"]["updatedInput"]["command"]
        self.assertIn("export CLAUDE_AGENT_ID=" + AGENT, command, "scope: the call was not marked with the agent id")
        self.assertEqual(starts, [], "the tool-call path started %d process(es): %r" % (len(starts), starts))


if __name__ == "__main__":
    unittest.main(verbosity=2)  # one line per case, which the mutation runner reads to know a case ran
