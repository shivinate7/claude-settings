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
    """{job: {"if": job-level if or None, "steps": [{key: value}]}} for windows-latest jobs.

    Step keys sit at 8 spaces, or inline after `- ` at 6. Block scalars (`run: |`) read as "|".
    """
    jobs, job, in_jobs = {}, None, False
    for line in text.splitlines():
        if re.match(r"^jobs:\s*$", line):
            in_jobs = True
        elif in_jobs and (m := re.match(r"^  ([\w-]+):\s*$", line)):
            job = jobs[m.group(1)] = {"os": None, "if": None, "steps": []}
        elif not job:
            continue
        elif m := re.match(r"^    (runs-on|if):\s*(\S.*?)\s*$", line):
            job["os" if m.group(1) == "runs-on" else "if"] = m.group(2)
        elif m := re.match(r"^      - (\w+):\s*(.*?)\s*$", line):
            job["steps"].append({m.group(1): m.group(2)})
        elif (m := re.match(r"^        (\w+):\s*(.*?)\s*$", line)) and job["steps"]:
            job["steps"][-1][m.group(1)] = m.group(2)
        elif (m := re.match(r"^          (\w+):\s*(.*?)\s*$", line)) and job["steps"]:  # an `env:` block key
            if not isinstance(job["steps"][-1].get("env"), dict):
                job["steps"][-1]["env"] = {}
            job["steps"][-1]["env"][m.group(1)] = m.group(2)
    return {n: j for n, j in jobs.items() if j["os"] == "windows-latest"}


# On pull_request the Windows merge job runs only the marked tests (MERGE_TESTS=windows-slice).
# The slice step has the same `run:` as the full step, so it is told apart by its env.
SLICE = "python merge/test_merge.py [windows-slice]"
SLICE_ENV = {"MERGE_TESTS": "windows-slice"}


def key(st):
    """A step's run command; a test_merge step with a MERGE_TESTS env reads as SLICE."""
    run = st.get("run")
    if run == "python merge/test_merge.py" and isinstance(st.get("env"), dict) and "MERGE_TESTS" in st["env"]:
        return SLICE
    return run


def placement_problems(text):
    """Strings naming each suite not run exactly once, or too few carrying jobs."""
    jobs = {n: [key(st) for st in j["steps"]] for n, j in windows_jobs(text).items()}
    problems = []
    homes = [n for n, runs in jobs.items() for r in runs if r == SLICE]
    if len(homes) != 1:
        problems.append(f"{SLICE!r} runs {len(homes)} times on windows-latest: {homes}")
    for cmd in REQUIRED:
        homes = [n for n, runs in jobs.items() for r in runs if r == cmd]
        if len(homes) != 1:
            problems.append(f"{cmd!r} runs {len(homes)} times on windows-latest: {homes}")
    carrying = [n for n, runs in jobs.items() if any(r in REQUIRED for r in runs)]
    if len(carrying) < MIN_JOBS:
        problems.append(f"{len(carrying)} windows-latest jobs carry the suites, need {MIN_JOBS}: {carrying}")
    return problems


# Steps whose `shell:` is pinned. Any other REQUIRED step must set none.
SHELL = {"sh hooks/test_install_src.sh": "bash", "bash actions/stamp/test_action.sh": "bash"}
# Steps whose whole `if:` is pinned (the harness must stay off pull_request and on its scope flag).
IF_PIN = {"python janitor/mutate_sweep.py":
          "${{ !cancelled() && github.event_name != 'pull_request' && steps.scope.outputs.sweep == 'true' }}",
          # The full merge suite runs on every event but pull_request; the slice only on it.
          "python merge/test_merge.py":
          "${{ !cancelled() && github.event_name != 'pull_request' && steps.scope.outputs.code == 'true' }}",
          SLICE: "${{ !cancelled() && github.event_name == 'pull_request' && steps.scope.outputs.code == 'true' }}"}


def hardening_problems(text):
    """A carrying job has no job-level if, a scope step and setup-python; a REQUIRED step keeps
    `!cancelled()`, its pinned shell and its pinned if."""
    problems = []
    n = text.count("MERGE_TESTS")  # one mention only: the slice step's env. Job, workflow or $GITHUB_ENV copies would slice every run.
    if n != 1:
        problems.append(f"MERGE_TESTS appears {n} times in gates.yml, want exactly 1 (the slice step's env)")
    for name, job in windows_jobs(text).items():
        steps = job["steps"]
        if not any(key(st) in REQUIRED for st in steps):
            continue
        if job["if"] is not None:
            problems.append(f"{name}: job-level if: {job['if']}")
        if not any(st.get("id") == "scope" and "harness-scope.sh" in st.get("run", "") for st in steps):
            problems.append(f"{name}: no scope step")
        if not any(st.get("uses", "").startswith("actions/setup-python@") for st in steps):
            problems.append(f"{name}: no setup-python")
        for st in steps:
            cmd = key(st)
            if cmd not in REQUIRED and cmd != SLICE:
                continue
            if cmd == SLICE and st["env"] != SLICE_ENV:
                problems.append(f"{name}: slice env is {st['env']}, want {SLICE_ENV}")
            if "!cancelled()" not in st.get("if", ""):
                problems.append(f"{name}: {cmd!r} if lacks !cancelled(): {st.get('if')}")
            if cmd in IF_PIN and st.get("if") != IF_PIN[cmd]:
                problems.append(f"{name}: {cmd!r} if is not the pinned text: {st.get('if')}")
            if st.get("shell") != SHELL.get(cmd):
                problems.append(f"{name}: {cmd!r} shell is {st.get('shell')}, want {SHELL.get(cmd)}")
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

    def test_suites_keep_their_conditions(self):
        self.assertEqual(hardening_problems(self.text), [])

    def test_checker_sees_drop_and_duplicate(self):
        def doc(*jobs, slice_=True):
            return "jobs:\n" + "".join(
                f"  j{i}:\n    runs-on: windows-latest\n    steps:\n"
                + "".join(f"      - run: {c}\n" for c in cmds)
                + ("      - run: python merge/test_merge.py\n        env:\n          MERGE_TESTS: windows-slice\n"
                   if slice_ and i == 0 else "")
                for i, cmds in enumerate(jobs)
            )
        self.assertTrue(placement_problems(doc(REQUIRED[:7], REQUIRED[7:14], REQUIRED[14:], slice_=False)))
        self.assertEqual(placement_problems(doc(REQUIRED[:7], REQUIRED[7:14], REQUIRED[14:])), [])
        self.assertTrue(placement_problems(doc(REQUIRED[1:7], REQUIRED[7:14], REQUIRED[14:])))
        self.assertTrue(placement_problems(doc(REQUIRED[:8], REQUIRED[7:14], REQUIRED[14:])))

    def test_checker_sees_the_merge_slice_defects(self):
        full_if = "${{ !cancelled() && github.event_name != 'pull_request' && steps.scope.outputs.code == 'true' }}"
        slice_if = full_if.replace("!=", "==")

        def doc(full_if=full_if, slice_if=slice_if, env="windows-slice", with_full=True):
            full = (f"      - name: Full\n        if: {full_if}\n        run: python merge/test_merge.py\n"
                    if with_full else "")
            return ("jobs:\n  j:\n    runs-on: windows-latest\n    steps:\n"
                    "      - id: scope\n        run: bash .github/scripts/harness-scope.sh\n"
                    "      - uses: actions/setup-python@abc # v6\n" + full +
                    f"      - name: Slice\n        if: {slice_if}\n        env:\n          MERGE_TESTS: {env}\n"
                    "        run: python merge/test_merge.py\n")
        self.assertEqual(hardening_problems(doc()), [])
        self.assertIn("'python merge/test_merge.py' runs 0 times on windows-latest: []",
                      placement_problems(doc(with_full=False)))  # full run removed
        self.assertNotIn("'python merge/test_merge.py' runs 0 times on windows-latest: []", placement_problems(doc()))
        self.assertTrue(hardening_problems(doc(slice_if=full_if)))  # slice runs on push
        self.assertTrue(hardening_problems(doc(full_if=slice_if)))  # full run on pull_request
        self.assertTrue(hardening_problems(doc(slice_if=slice_if.replace("!cancelled() && ", ""))))
        self.assertTrue(hardening_problems(doc(env="full")))  # slice env not pinned
        good = doc()
        for bad in (good.replace("    runs-on: windows-latest\n", "    runs-on: windows-latest\n    env:\n      MERGE_TESTS: windows-slice\n"),
                    "env:\n  MERGE_TESTS: windows-slice\n" + good,
                    good.replace("      - id: scope\n", "      - run: echo MERGE_TESTS=windows-slice >> $GITHUB_ENV\n      - id: scope\n")):
            self.assertTrue(any("MERGE_TESTS appears 2 times" in p for p in hardening_problems(bad)), bad)
        self.assertFalse(any("MERGE_TESTS appears" in p for p in hardening_problems(good)))
        self.assertTrue(hardening_problems(doc(full_if=full_if.replace(" && steps.scope.outputs.code == 'true'", ""))))


if __name__ == "__main__":
    unittest.main()
