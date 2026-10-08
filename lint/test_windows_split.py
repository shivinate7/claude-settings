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
    "python hooks/test_question_outcome.py",
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


def all_jobs(text):
    """{job: {"os", "if": job-level if or None, "needs": raw needs text or None, "steps": [{key: value}]}}.

    Step keys sit at 8 spaces, or inline after `- ` at 6. Block scalars (`run: |`) read as "|".
    """
    jobs, job, in_jobs = {}, None, False
    for line in text.splitlines():
        if re.match(r"^jobs:\s*$", line):
            in_jobs = True
        elif in_jobs and (m := re.match(r"^  ([\w-]+):\s*$", line)):
            job = jobs[m.group(1)] = {"os": None, "if": None, "needs": None, "steps": []}
        elif not job:
            continue
        elif m := re.match(r"^    (runs-on|if|needs):\s*(\S.*?)\s*$", line):
            job[{"runs-on": "os", "if": "if", "needs": "needs"}[m.group(1)]] = m.group(2)
        elif m := re.match(r"^      - (\w+):\s*(.*?)\s*$", line):
            job["steps"].append({m.group(1): m.group(2)})
        elif (m := re.match(r"^        (\w+):\s*(.*?)\s*$", line)) and job["steps"]:
            job["steps"][-1][m.group(1)] = m.group(2)
        elif (m := re.match(r"^          (\w+):\s*(.*?)\s*$", line)) and job["steps"]:  # an `env:` block key
            if not isinstance(job["steps"][-1].get("env"), dict):
                job["steps"][-1]["env"] = {}
            job["steps"][-1]["env"][m.group(1)] = m.group(2)
    return jobs


def windows_jobs(text):
    return {n: j for n, j in all_jobs(text).items() if j["os"] == "windows-latest"}


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
          "${{ !cancelled() && github.event_name != 'pull_request' && needs.scope.outputs.sweep == 'true' }}",
          # The full merge suite runs on every event but pull_request; the slice only on it.
          "python merge/test_merge.py":
          "${{ !cancelled() && github.event_name != 'pull_request' && needs.scope.outputs.code == 'true' }}",
          SLICE: "${{ !cancelled() && github.event_name == 'pull_request' && needs.scope.outputs.code == 'true' }}"}


FLAGS = ["gates_windows", "gates_windows_merge", "gates_windows_rest", "gates_macos", "shell_macos", "pointer_windows",
         "code", "guard", "sweep"]


def eval_if(expr, event, flag_value):
    """Evaluate a job-level `if:` for an event with every scope output set to flag_value.
    Reads only !cancelled(), &&, ||, parentheses, ==, != on github.event_name and needs.scope.outputs.*."""
    e = expr.strip()
    if e.startswith("${{") and e.endswith("}}"):
        e = e[3:-2]
    e = e.replace("!cancelled()", "True").replace("success()", "True").replace("always()", "True")
    e = e.replace("&&", " and ").replace("||", " or ")
    e = e.replace("github.event_name", repr(event))
    e = re.sub(r"needs\.scope\.outputs\.\w+", repr(flag_value), e)
    return bool(eval(e, {"__builtins__": {}}))


def job_gate_problems(name, job):
    """`needs: scope`, and a job-level if that (a) reads needs.scope.outputs.<own flag>, (b) is true on push,
    schedule and workflow_dispatch even when every flag is 'false', (c) is true on pull_request with every flag
    'true' and false with every flag 'false'. The lint job `gates` needs scope and has no if."""
    problems = []
    if not re.fullmatch(r"\[?\s*scope\s*\]?", job["needs"] or ""):
        problems.append(f"{name}: needs is {job['needs']}, want scope")
    expr = job["if"]
    if expr is None and name != "gates":
        return problems + [f"{name}: no job-level if"]
    own = name.replace("-", "_")
    if name == "gates":  # the lint job runs on every PR: no job-level if
        return problems + ([f"gates: job-level if: {expr}"] if expr is not None else [])
    if f"needs.scope.outputs.{own}" not in expr:
        problems.append(f"{name}: job-level if does not read needs.scope.outputs.{own}: {expr}")
    try:
        for ev in ("push", "schedule", "workflow_dispatch"):
            if not eval_if(expr, ev, "false"):
                problems.append(f"{name}: job-level if skips on {ev}: {expr}")
        if not eval_if(expr, "pull_request", "true"):
            problems.append(f"{name}: job-level if skips on pull_request with every flag true: {expr}")
        if eval_if(expr, "pull_request", "false"):
            problems.append(f"{name}: job-level if runs on pull_request with every flag false: {expr}")
    except Exception as ex:
        problems.append(f"{name}: job-level if is not in the allowed form ({ex!r}): {expr}")
    return problems


def scope_problems(text):
    """A `scope` job on ubuntu with every flag as a job output; every other job passes job_gate_problems
    (the lint job `gates` needs scope but runs always)."""
    jobs = all_jobs(text)
    problems = []
    sc = jobs.get("scope")
    if not sc:
        return ["no scope job"]
    if not (sc["os"] or "").startswith("ubuntu"):
        problems.append(f"scope runs on {sc['os']}, want ubuntu")
    if sc["needs"]:
        problems.append(f"scope has needs: {sc['needs']}")
    block = re.search(r"^  scope:\s*$(.*?)(?=^  [\w-]+:\s*$|\Z)", text, re.M | re.S).group(1)
    for f in FLAGS:
        if not re.search(rf"^      {f}:\s*\S", block, re.M):
            problems.append(f"scope job has no output {f}")
    for name, job in jobs.items():
        if name != "scope":
            problems += job_gate_problems(name, job)
    return problems


def hardening_problems(text):
    """A carrying job has `needs: scope`, a job-level if of the allowed form, and setup-python; a REQUIRED step keeps
    `!cancelled()`, its pinned shell and its pinned if."""
    problems = []
    n = text.count("MERGE_TESTS")  # one mention only: the slice step's env. Job, workflow or $GITHUB_ENV copies would slice every run.
    if n != 1:
        problems.append(f"MERGE_TESTS appears {n} times in gates.yml, want exactly 1 (the slice step's env)")
    for name, job in windows_jobs(text).items():
        steps = job["steps"]
        if not any(key(st) in REQUIRED for st in steps):
            continue
        problems += job_gate_problems(name, job)
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

    def test_scope_job_gates_every_other_job(self):
        self.assertEqual(scope_problems(self.text), [])

    def test_the_gate_form_sees_its_defects(self):
        ok = "${{ needs.scope.outputs.gates_macos == 'true' || github.event_name != 'pull_request' }}"
        job = {"needs": "scope", "if": ok}
        self.assertEqual(job_gate_problems("gates-macos", job), [])
        self.assertEqual(job_gate_problems("gates", {"needs": "scope", "if": None}), [])
        self.assertTrue(job_gate_problems("gates", {"needs": None, "if": None}))
        bad = {"pr_only": "${{ needs.scope.outputs.gates_macos == 'true' }}",  # skips on push when the flag is false
               "not_pr_always": "${{ github.event_name != 'pull_request' }}",  # never reads the flag
               "other_flag": ok.replace("gates_macos", "gates_windows"),
               "always_on_pr": "${{ !cancelled() || needs.scope.outputs.gates_macos == 'true' }}"}
        for label, expr in bad.items():
            self.assertTrue(job_gate_problems("gates-macos", dict(job, **{"if": expr})), label)
        self.assertTrue(job_gate_problems("gates-macos", dict(job, needs="gates")))
        self.assertTrue(job_gate_problems("gates-macos", dict(job, **{"if": None})))

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
        full_if = "${{ !cancelled() && github.event_name != 'pull_request' && needs.scope.outputs.code == 'true' }}"
        slice_if = full_if.replace("!=", "==")

        def doc(full_if=full_if, slice_if=slice_if, env="windows-slice", with_full=True):
            full = (f"      - name: Full\n        if: {full_if}\n        run: python merge/test_merge.py\n"
                    if with_full else "")
            return ("jobs:\n  gates-windows-merge:\n    runs-on: windows-latest\n    needs: scope\n"
                    "    if: ${{ needs.scope.outputs.gates_windows_merge == 'true' || github.event_name != 'pull_request' }}\n    steps:\n"
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
                    good.replace("    steps:\n", "    steps:\n      - run: echo MERGE_TESTS=windows-slice >> $GITHUB_ENV\n")):
            self.assertTrue(any("MERGE_TESTS appears 2 times" in p for p in hardening_problems(bad)), bad)
        self.assertFalse(any("MERGE_TESTS appears" in p for p in hardening_problems(good)))
        self.assertTrue(hardening_problems(doc(full_if=full_if.replace(" && needs.scope.outputs.code == 'true'", ""))))


if __name__ == "__main__":
    unittest.main()
