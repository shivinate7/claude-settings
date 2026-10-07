#!/usr/bin/env python3
"""Guard for the Windows split of .github/workflows/gates.yml.

Proves: (1) each suite command in REQUIRED runs in exactly one `windows-latest` job (none
dropped, none run twice); (2) at least MIN_JOBS `windows-latest` jobs carry those suites.

Why not rule_audit.py: it reads step names only. This needs job boundaries and `run:` lines.
Line-based parse, stdlib only, like rule_audit. Only single-line `run: <cmd>` steps count.
GATES_YML overrides the path (used for red proofs on a scratch copy).

Run with:  python3 lint/test_windows_split.py -v
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
GATES = os.environ.get("GATES_YML") or os.path.join(HERE, "..", ".github", "workflows", "gates.yml")
MIN_JOBS = 3

# The run commands of the old single `gates-windows` job. Edit here only on purpose.
REQUIRED = [
    "python hooks/test_guard.py",
    "python janitor/test_sweep.py",
    "python janitor/mutate_sweep.py",
    "python hooks/test_config_watch.py",
    "python hooks/test_precompact_handoff.py",
    "python hooks/test_decision_watch.py",
    "python lint/test_gates.py",
    "python hooks/test_ruling_home.py",
    "python lint/test_ruling_census.py",
    "python lint/test_verdict.py",
    "python lint/check_unknown_reads_contract.py",
    "python janitor/test_session_end_sweep.py",
    "python janitor/test_install_launchd.py",
    "python janitor/test_install_schtasks.py",
    "sh hooks/test_install_src.sh",
    "node actions/stamp/test_stamp.mjs",
    "bash actions/stamp/test_action.sh",
    "python merge/test_launch.py",
    "python merge/test_merge.py",
    "python merge/test_cmd.py",
]


def windows_jobs(text):
    """{job name: [single-line run commands]} for each job whose runs-on is windows-latest."""
    jobs, name, in_jobs = {}, None, False
    for line in text.splitlines():
        if re.match(r"^jobs:\s*$", line):
            in_jobs = True
        elif in_jobs and (m := re.match(r"^  ([\w-]+):\s*$", line)):
            name = m.group(1)
            jobs[name] = {"os": None, "runs": []}
        elif name and (m := re.match(r"^    runs-on:\s*(\S+)", line)):
            jobs[name]["os"] = m.group(1)
        elif name and (m := re.match(r"^\s+(?:- )?run:\s+(\S.*?)\s*$", line)) and m.group(1)[0] not in "|>":
            jobs[name]["runs"].append(m.group(1))
    return {n: j["runs"] for n, j in jobs.items() if j["os"] == "windows-latest"}


def placement_problems(text):
    """Strings naming each suite not run exactly once, or too few carrying jobs."""
    jobs = windows_jobs(text)
    problems = []
    for cmd in REQUIRED:
        homes = [n for n, runs in jobs.items() for r in runs if r == cmd]
        if len(homes) != 1:
            problems.append(f"{cmd!r} runs {len(homes)} times on windows-latest: {homes}")
    carrying = [n for n, runs in jobs.items() if any(r in REQUIRED for r in runs)]
    if len(carrying) < MIN_JOBS:
        problems.append(f"{len(carrying)} windows-latest jobs carry the suites, need {MIN_JOBS}: {carrying}")
    return problems


class WindowsSplit(unittest.TestCase):
    def setUp(self):
        with open(GATES, encoding="utf-8") as f:
            self.text = f.read()
        self.assertTrue(windows_jobs(self.text), "parsed no windows-latest job: wrong path or parse")

    def test_each_suite_runs_exactly_once(self):
        bad = [p for p in placement_problems(self.text) if "times" in p]
        self.assertEqual(bad, [])

    def test_suites_spread_over_enough_jobs(self):
        bad = [p for p in placement_problems(self.text) if "carry" in p]
        self.assertEqual(bad, [])

    def test_checker_sees_drop_and_duplicate(self):
        def doc(*jobs):
            return "jobs:\n" + "".join(
                f"  j{i}:\n    runs-on: windows-latest\n    steps:\n"
                + "".join(f"      - run: {c}\n" for c in cmds)
                for i, cmds in enumerate(jobs)
            )
        self.assertEqual(placement_problems(doc(REQUIRED[:7], REQUIRED[7:14], REQUIRED[14:])), [])
        self.assertTrue(placement_problems(doc(REQUIRED[1:7], REQUIRED[7:14], REQUIRED[14:])))
        self.assertTrue(placement_problems(doc(REQUIRED[:8], REQUIRED[7:14], REQUIRED[14:])))


if __name__ == "__main__":
    unittest.main()
