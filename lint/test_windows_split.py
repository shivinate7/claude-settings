#!/usr/bin/env python3
"""Guard for the Windows split of .github/workflows/gates.yml.

Proves: (1) each suite command in REQUIRED runs in exactly one `windows-latest` job (none
dropped, none run twice); (2) at least MIN_JOBS `windows-latest` jobs carry those suites.
Cut F adds: the guard suite has its own Windows job (GUARD_JOB) and runs off it nowhere else; its
slice (GUARD_TESTS=windows-slice) runs only on pull_request; the guard mutation harness has its own
Linux job (MUTATE_JOB) and runs nowhere else; both jobs skip on the `guard` scope flag.

Why not rule_audit.py: it reads step names only. This needs job boundaries and `run:` lines.
Line-based parse, stdlib only, like rule_audit. Only single-line `run: <cmd>` steps count.
GATES_YML overrides the path (used for red proofs on a scratch copy).

CiCoverage (last class) also proves every test_*.py, test_*.sh and *.test.ps1 file has a run step.

Run with:  python3 lint/test_windows_split.py -v
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
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
    "python hooks/test_prose_judge.py",
    "python hooks/test_question_outcome.py",
    "python hooks/test_rm_prompt_answer.py",
    "python hooks/test_agent_brief.py",
    "python hooks/test_wrappers.py",
    "python lint/test_gates.py",
    "python hooks/test_ruling_home.py",
    "python lint/test_ruling_census.py",
    "python lint/test_verdict.py",
    "python lint/test_hook_platform_exit.py",
    "python lint/check_unknown_reads_contract.py",
    "python janitor/test_session_end_sweep.py",
    "python janitor/test_install_launchd.py",
    "python janitor/test_install_schtasks.py",
    "sh hooks/test_install_windows.sh",
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
# The same pattern for the guard suite (GUARD_TESTS=windows-slice, cut F). Its own Windows job,
# gates-windows-guard, runs the full suite off pull_request and the slice on it.
GUARD_CMD = "python hooks/test_guard.py"
GUARD_SLICE = "python hooks/test_guard.py [windows-slice]"
GUARD_SLICE_ENV = {"GUARD_TESTS": "windows-slice"}
GUARD_JOB = "gates-windows-guard"
# The guard mutation harness moves off `gates` (Linux) to its own Linux job (cut F).
MUTATE_CMD = "python3 hooks/mutate_guard.py"
MUTATE_JOB = "gates-mutate-guard"
# The scope flag each of the two cut-F jobs skips on (scope has no flag of its own for them).
FLAG_OF = {GUARD_JOB: "guard", MUTATE_JOB: "guard"}


def key(st):
    """A step's run command; a test_merge or test_guard step with its slice env reads as its SLICE."""
    run = st.get("run")
    env = st.get("env") if isinstance(st.get("env"), dict) else {}
    if run == "python merge/test_merge.py" and "MERGE_TESTS" in env:
        return SLICE
    if run == GUARD_CMD and "GUARD_TESTS" in env:
        return GUARD_SLICE
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
SHELL = {"sh hooks/test_install_windows.sh": "bash", "bash actions/stamp/test_action.sh": "bash"}
# Steps whose whole `if:` is pinned (the harness must stay off pull_request and on its scope flag).
IF_PIN = {"python janitor/mutate_sweep.py":
          "${{ !cancelled() && github.event_name != 'pull_request' && needs.scope.outputs.sweep == 'true' }}",
          # The full merge suite runs on every event but pull_request; the slice only on it.
          "python merge/test_merge.py":
          "${{ !cancelled() && github.event_name != 'pull_request' && needs.scope.outputs.code == 'true' }}",
          SLICE: "${{ !cancelled() && github.event_name == 'pull_request' && needs.scope.outputs.code == 'true' }}",
          # The full guard suite runs off pull_request; the guard slice only on it (cut F).
          GUARD_CMD: "${{ !cancelled() && github.event_name != 'pull_request' && needs.scope.outputs.code == 'true' }}",
          GUARD_SLICE: "${{ !cancelled() && github.event_name == 'pull_request' && needs.scope.outputs.code == 'true' }}"}


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


def job_gate_problems(name, job, flag=None):
    """`needs: scope`, and a job-level if that (a) reads needs.scope.outputs.<own flag>, (b) is true on push,
    schedule and workflow_dispatch even when every flag is 'false', (c) is true on pull_request with every flag
    'true' and false with every flag 'false'. The lint job `gates` needs scope and has no if. `flag` names the
    scope output for a job whose flag is not its own name (FLAG_OF)."""
    problems = []
    if not re.fullmatch(r"\[?\s*scope\s*\]?", job["needs"] or ""):
        problems.append(f"{name}: needs is {job['needs']}, want scope")
    expr = job["if"]
    if expr is None and name != "gates":
        return problems + [f"{name}: no job-level if"]
    own = flag or name.replace("-", "_")
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
            problems += job_gate_problems(name, job, FLAG_OF.get(name))
    return problems


def hardening_problems(text):
    """A carrying job has `needs: scope`, a job-level if of the allowed form, and setup-python; a REQUIRED step keeps
    `!cancelled()`, its pinned shell and its pinned if."""
    problems = []
    n = text.count("MERGE_TESTS")  # one mention only: the slice step's env. Job, workflow or $GITHUB_ENV copies would slice every run.
    if n != 1:
        problems.append(f"MERGE_TESTS appears {n} times in gates.yml, want exactly 1 (the slice step's env)")
    slice_envs = {SLICE: SLICE_ENV, GUARD_SLICE: GUARD_SLICE_ENV}
    for name, job in windows_jobs(text).items():
        steps = job["steps"]
        if not any(key(st) in REQUIRED for st in steps):
            continue
        problems += job_gate_problems(name, job, FLAG_OF.get(name))
        if not any(st.get("uses", "").startswith("actions/setup-python@") for st in steps):
            problems.append(f"{name}: no setup-python")
        for st in steps:
            cmd = key(st)
            if cmd not in REQUIRED and cmd not in slice_envs:
                continue
            if cmd in slice_envs and st["env"] != slice_envs[cmd]:
                problems.append(f"{name}: slice env is {st['env']}, want {slice_envs[cmd]}")
            if "!cancelled()" not in st.get("if", ""):
                problems.append(f"{name}: {cmd!r} if lacks !cancelled(): {st.get('if')}")
            if cmd in IF_PIN and st.get("if") != IF_PIN[cmd]:
                problems.append(f"{name}: {cmd!r} if is not the pinned text: {st.get('if')}")
            if st.get("shell") != SHELL.get(cmd):
                problems.append(f"{name}: {cmd!r} shell is {st.get('shell')}, want {SHELL.get(cmd)}")
    return problems


def guard_problems(text):
    """Cut F. The guard suite has its own windows-latest job, GUARD_JOB. It runs the full suite off pull_request
    and the slice on it, both gated on the guard flag. No other Windows job runs the guard suite."""
    jobs = windows_jobs(text)
    if GUARD_JOB not in jobs:
        return [f"no windows-latest job named {GUARD_JOB}"]
    problems = []
    for name, job in jobs.items():
        if name != GUARD_JOB and any(key(st) in (GUARD_CMD, GUARD_SLICE) for st in job["steps"]):
            problems.append(f"{name} runs the guard suite; it belongs to {GUARD_JOB} alone")
    job = jobs[GUARD_JOB]
    problems += job_gate_problems(GUARD_JOB, job, FLAG_OF[GUARD_JOB])
    steps = {}
    for st in job["steps"]:
        steps.setdefault(key(st), st)
    for cmd in (GUARD_CMD, GUARD_SLICE):
        if cmd not in steps:
            problems.append(f"{GUARD_JOB} has no step {cmd!r}")
    if GUARD_CMD in steps and steps[GUARD_CMD].get("if") != IF_PIN[GUARD_CMD]:
        problems.append(f"{GUARD_JOB}: full guard if is not the pinned text: {steps[GUARD_CMD].get('if')}")
    if GUARD_SLICE in steps:
        st = steps[GUARD_SLICE]
        if st.get("env") != GUARD_SLICE_ENV:
            problems.append(f"{GUARD_JOB}: slice env is {st.get('env')}, want {GUARD_SLICE_ENV}")
        if st.get("if") != IF_PIN[GUARD_SLICE]:
            problems.append(f"{GUARD_JOB}: slice if is not the pinned text: {st.get('if')}")
    g = text.count("GUARD_TESTS")  # one mention only: the slice step's env
    if g != 1:
        problems.append(f"GUARD_TESTS appears {g} times in gates.yml, want exactly 1 (the guard slice step's env)")
    # CI runs the whole guard suite. A GUARD_FAMILY here would make CI run one family and call it green.
    f = text.count("GUARD_FAMILY")
    if f:
        problems.append(f"GUARD_FAMILY appears {f} times in gates.yml, want 0 (CI runs every case)")
    return problems


def mutate_problems(text):
    """Cut F. The guard mutation harness runs in MUTATE_JOB on Linux, and in no other job."""
    jobs = all_jobs(text)
    homes = [n for n, j in jobs.items() for st in j["steps"] if st.get("run") == MUTATE_CMD]
    problems = []
    if homes != [MUTATE_JOB]:
        problems.append(f"{MUTATE_CMD!r} runs in {homes}, want exactly [{MUTATE_JOB!r}]")
    if MUTATE_JOB in jobs and not (jobs[MUTATE_JOB]["os"] or "").startswith("ubuntu"):
        problems.append(f"{MUTATE_JOB} runs on {jobs[MUTATE_JOB]['os']}, want ubuntu-latest")
    return problems


class WindowsSplit(unittest.TestCase):
    def setUp(self):
        with open(GATES, encoding="utf-8") as f:
            self.text = f.read()
        self.assertTrue(windows_jobs(self.text), "parsed no windows-latest job: wrong path or parse")

    def test_each_suite_runs_exactly_once(self):
        bad = [p for p in placement_problems(self.text) if "times" in p]
        self.assertEqual(bad, [])
        # The mutation harness is placed
        # once in its own job. Named failure: a harness dropped or doubled, so mutants go unrun.
        self.assertEqual(mutate_problems(self.text), [])

    def test_scope_job_gates_every_other_job(self):
        self.assertEqual(scope_problems(self.text), [])
        # The guard and mutate jobs skip on the
        # guard flag. Named failure: a cut job runs or never runs on push, schedule and dispatch.
        jobs = all_jobs(self.text)
        for name in (GUARD_JOB, MUTATE_JOB):
            self.assertIn(name, jobs, f"no job named {name}")
            self.assertEqual(job_gate_problems(name, jobs[name], FLAG_OF[name]), [])

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

    def test_the_guard_suite_has_its_own_windows_job(self):
        self.assertEqual(guard_problems(self.text), [])

    def test_gates_sets_no_guard_family(self):
        self.assertEqual([p for p in guard_problems(self.text) if "GUARD_FAMILY" in p], [])
        # The red proof: the checker flags a
        # guard family set in gates. Named failure: a guard family runs in gates and CI goes green.
        bad = [p for p in guard_problems(self.text + "\n# GUARD_FAMILY=shared-tree\n") if "GUARD_FAMILY" in p]
        self.assertTrue(bad)

    def test_checker_sees_the_guard_slice_and_mutate_defects(self):
        full_if, slice_if = IF_PIN[GUARD_CMD], IF_PIN[GUARD_SLICE]
        good_job_if = "${{ needs.scope.outputs.guard == 'true' || github.event_name != 'pull_request' }}"

        def doc(full_if=full_if, slice_if=slice_if, env="windows-slice", job_if=good_job_if, extra="", more=""):
            return ("jobs:\n  gates-windows-guard:\n    runs-on: windows-latest\n    needs: scope\n"
                    f"    if: {job_if}\n{extra}    steps:\n"
                    "      - uses: actions/setup-python@abc # v6\n"
                    f"      - name: Full\n        if: {full_if}\n        run: python hooks/test_guard.py\n"
                    f"      - name: Slice\n        if: {slice_if}\n        env:\n          GUARD_TESTS: {env}\n"
                    "        run: python hooks/test_guard.py\n" + more)
        self.assertEqual(guard_problems(doc()), [])
        self.assertTrue(guard_problems(doc(slice_if=full_if)))  # slice runs on push
        self.assertTrue(guard_problems(doc(full_if=slice_if)))  # full suite runs on pull_request
        self.assertTrue(guard_problems(doc(env="full")))  # slice env not pinned
        self.assertTrue(guard_problems(doc(extra="    env:\n      GUARD_TESTS: windows-slice\n")))  # job-level env
        self.assertTrue(guard_problems(doc(job_if=good_job_if.replace("guard", "gates_windows"))))  # wrong flag
        self.assertTrue(guard_problems(doc(job_if="${{ needs.scope.outputs.guard == 'true' }}")))  # skips on push
        self.assertTrue(guard_problems(doc(more="  gates-windows:\n    runs-on: windows-latest\n    needs: scope\n"
                                               "    if: ${{ needs.scope.outputs.gates_windows == 'true' }}\n"
                                               "    steps:\n      - run: python hooks/test_guard.py\n")))
        gates = "jobs:\n  gates-mutate-guard:\n    runs-on: ubuntu-latest\n    steps:\n      - run: python3 hooks/mutate_guard.py\n"
        self.assertEqual(mutate_problems(gates), [])
        self.assertTrue(mutate_problems(gates.replace("gates-mutate-guard", "gates")))  # in the lint job
        self.assertTrue(mutate_problems(gates.replace("ubuntu-latest", "windows-latest")))  # on Windows
        self.assertTrue(mutate_problems("jobs:\n  gates:\n    runs-on: ubuntu-latest\n    steps:\n"
                                        "      - run: python3 hooks/mutate_guard.py\n"
                                        "  gates-mutate-guard:\n    runs-on: ubuntu-latest\n    steps:\n"
                                        "      - run: python3 hooks/mutate_guard.py\n"))  # runs twice


# Mod tests: one step of the `gates` job (Linux), on the `mods` scope flag. The step finds every
# *.test.mjs and *.test.js file under mods/ except node_modules, so a new mods/<name>/ joins with no
# edit here. It carries the exit code of every file: a failing first or last file fails the step. The
# checker's own self-tests (ModTestStepChecker) run on synthetic text and pass now: they show each
# defect is seen. MOD_GLOB is the name pattern that marks the step, in a glob or in a find -name.
MOD_GLOB = "*.test.mjs"
MOD_FLAG = "mods"
GATES_JOB = "gates"
STAMP = os.path.join(HERE, "..", ".github", "stamp.json")
CHECKOUT = re.compile(r"^(?:      - |        )uses:[ \t]*actions/checkout@", re.M)


def job_block(text, name):
    """Raw text of one job: from its `  name:` line to the next job line. None when the job is absent."""
    m = re.search(rf"^  {re.escape(name)}:\s*$(.*?)(?=^  [\w-]+:\s*$|\Z)", text, re.M | re.S)
    return m.group(1) if m else None


def step_blocks(block):
    """Each `      - ` step of a job block, as raw text. Block scalars stay whole."""
    return [p for p in re.split(r"^(?=      - )", block or "", flags=re.M) if p.startswith("      - ")]


def step_key(step, key):
    """A step's own `key:` value (`        key:` or inline `      - key:`), or None. Body lines sit deeper."""
    m = re.search(rf"^(?:      - |        ){re.escape(key)}:[ \t]*(.*?)[ \t]*$", step, re.M)
    return m.group(1) if m else None


def run_body(step):
    """A step's `run:` text: the one line, or a `run: |` block with its 10-space indent removed. None if absent."""
    lines = step.split("\n")
    for i, line in enumerate(lines):
        m = re.match(r"^(?:      - |        )run:[ \t]*(.*?)[ \t]*$", line)
        if not m:
            continue
        if m.group(1) != "|":
            return m.group(1)
        body = []
        for ln in lines[i + 1:]:
            if ln.strip() and not ln.startswith("          "):
                break
            body.append(ln[10:] if ln.strip() else "")
        return "\n".join(body).strip("\n") + "\n"
    return None


def mod_steps(text):
    """The steps of the gates job whose run names the mod glob."""
    return [st for st in step_blocks(job_block(text, GATES_JOB)) if MOD_GLOB in (run_body(st) or "")]


def mods_scope_problems(text):
    """The scope job must export the mods output. Without it needs.scope.outputs.mods is empty and the step never runs."""
    scope = job_block(text, "scope") or ""
    if not re.search(r"^      mods:[ \t]*\$\{\{[ \t]*steps\.scope\.outputs\.mods[ \t]*\}\}[ \t]*$", scope, re.M):
        return ["scope job does not export the mods output"]
    return []


def mods_step_problems(text):
    """Pins on the one mod-test step of the gates job. [] when the step is right."""
    homes = mod_steps(text)
    if len(homes) != 1:
        return [f"{len(homes)} steps in {GATES_JOB} run {MOD_GLOB}, want 1"]
    st = homes[0]
    steps = step_blocks(job_block(text, GATES_JOB))
    i = steps.index(st)
    problems = []
    cond = step_key(st, "if") or ""
    if "!cancelled()" not in cond:
        problems.append(f"mod step if lacks !cancelled(): {cond}")
    if f"needs.scope.outputs.{MOD_FLAG} == 'true'" not in cond:
        problems.append(f"mod step if does not read needs.scope.outputs.{MOD_FLAG}: {cond}")
    if "github.event_name" in cond:
        problems.append(f"mod step if reads the event; the {MOD_FLAG} flag alone decides: {cond}")
    if step_key(st, "shell") != "bash":
        problems.append(f"mod step shell is {step_key(st, 'shell')}, want bash")
    if step_key(st, "continue-on-error") is not None:
        problems.append("mod step sets continue-on-error, which swallows the exit code")
    body = run_body(st)
    if re.search(r"(?<!\|)\|(?!\|)", body):
        problems.append("mod step pipes a command: the pipe takes the last command's exit code")
    if re.search(r"\|\|\s*(true|:)\b", body):
        problems.append("mod step ends a command with || true or || :")
    checkout = [j for j, s in enumerate(steps) if CHECKOUT.search(s)]
    if not checkout or checkout[0] > i:
        problems.append("no actions/checkout before the mod step")
    return problems


def mods_problems(text):
    return mods_scope_problems(text) + mods_step_problems(text)


def run_mod_body(body, files, dirs=(), find_exit=None):
    """Run a step body as `shell: bash` does, in a scratch repo. files maps a path to True (passes) or False (fails).
    dirs are empty folders to make. find_exit, when set, puts a `find` first on PATH that runs the real find and
    then exits with that code, as a find does that meets an error after it listed files. Returns the exit code."""
    with tempfile.TemporaryDirectory() as root:
        work = os.path.join(root, "repo")
        os.makedirs(work, exist_ok=True)
        for d in dirs:
            os.makedirs(os.path.join(work, d), exist_ok=True)
        env = None
        if find_exit is not None:
            shim = os.path.join(root, "shim")
            os.makedirs(shim)
            with open(os.path.join(shim, "find"), "w", encoding="utf-8", newline="\n") as f:
                f.write(f'#!/bin/sh\n"{shutil.which("find")}" "$@"\nexit {find_exit}\n')
            os.chmod(os.path.join(shim, "find"), 0o755)
            env = dict(os.environ, PATH=shim + os.pathsep + os.environ["PATH"])
        for rel, ok in files.items():
            full = os.path.join(work, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write("// fixture\n" if ok else 'throw new Error("planted failure");\n')
        script = os.path.join(root, "step.sh")
        with open(script, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)
        r = subprocess.run([shutil.which("bash"), "--noprofile", "--norc", "-eo", "pipefail", script.replace("\\", "/")],
                           cwd=work, capture_output=True, text=True, timeout=300, env=env)
        return r.returncode


class ModTestStep(unittest.TestCase):
    def setUp(self):
        with open(GATES, encoding="utf-8") as f:
            self.text = f.read()

    def test_the_scope_job_exports_the_mods_flag(self):
        self.assertEqual(mods_scope_problems(self.text), [])

    def test_gates_runs_the_mod_glob_in_one_pinned_step(self):
        self.assertEqual(mods_step_problems(self.text), [])

    @unittest.skipUnless(shutil.which("bash") and shutil.which("node"), "needs bash and node on PATH")
    def test_the_step_fails_when_any_mod_test_fails(self):
        steps = mod_steps(self.text)
        self.assertEqual(len(steps), 1, "no step runs the mod glob, so no mod test runs in CI")
        body = run_body(steps[0])
        cases = [
            ("all pass", {"mods/a/a.test.mjs": True, "mods/b/b.test.mjs": True}, True),
            ("first file fails", {"mods/a/first.test.mjs": False, "mods/b/b.test.mjs": True}, False),
            ("last file fails, in a new mod", {"mods/a/a.test.mjs": True, "mods/zz-new/last.test.mjs": False}, False),
            # These two shapes never ran.
            ("nested tests/ file fails", {"mods/a/a.test.mjs": True, "mods/a/tests/b.test.mjs": False}, False),
            ("*.test.js file fails", {"mods/a/a.test.mjs": True, "mods/a/c.test.js": False}, False),
            # Control, green now: a dependency's own test under node_modules is not ours to run.
            ("node_modules test fails", {"mods/a/a.test.mjs": True, "mods/a/node_modules/dep/d.test.js": False}, True),
        ]
        for label, files, ok in cases:
            with self.subTest(case=label):
                rc = run_mod_body(body, files)
                self.assertEqual(rc == 0, ok, f"{label}: exit {rc}")

    @unittest.skipUnless(shutil.which("bash") and shutil.which("node") and shutil.which("find"), "needs bash, node and find on PATH")
    def test_the_step_fails_when_it_finds_no_test_or_find_errors(self):
        """`done < <(find ...)` drops find's exit code, and an empty loop exits 0 with nothing run."""
        steps = mod_steps(self.text)
        self.assertEqual(len(steps), 1, "no step runs the mod glob, so no mod test runs in CI")
        body = run_body(steps[0])
        ok = {"mods/a/a.test.mjs": True}
        cases = [
            ("mods/ is missing", {}, (), None),
            ("mods/ is empty", {}, ("mods",), None),
            ("mods/ holds no test file", {"mods/a/readme.md": True}, (), None),
            ("only a node_modules test file", {"mods/a/node_modules/dep/d.test.js": True}, (), None),
            ("find exits 2 after it listed a passing file", ok, (), 2),
        ]
        for label, files, dirs, find_exit in cases:
            with self.subTest(case=label):
                rc = run_mod_body(body, files, dirs, find_exit)
                self.assertNotEqual(rc, 0, f"{label}: the step exited 0")
        # Control, green now: one passing file and a clean find still pass.
        self.assertEqual(run_mod_body(body, ok), 0)

    def test_gates_stays_a_required_check_and_mods_adds_no_name(self):
        """Control, green now: the mod step rides the required `gates` job, so the list gains no name."""
        with open(STAMP, encoding="utf-8") as f:
            required = json.load(f)["merge"]["requiredChecks"]
        self.assertIn(GATES_JOB, required)
        self.assertEqual([n for n in required if "mod" in n.lower()], [])


MOD_CHECKOUT = ("      - uses: actions/checkout@08c6903cd8c0fde910a37f88322edcfb5dd907a8 # v5.0.0\n"
                "        with:\n          fetch-depth: 0\n\n")
MOD_STEP = ("      - name: Mod tests\n"
            "        if: ${{ !cancelled() && needs.scope.outputs.mods == 'true' }}\n"
            "        shell: bash\n"
            "        run: |\n"
            "          fail=0\n"
            "          for f in mods/*/*.test.mjs; do\n"
            "            node --test \"$f\" || fail=1\n"
            "          done\n"
            "          exit $fail\n")


def mod_doc(body=MOD_STEP, extra="", checkout=True, scope_out=True):
    """A synthetic gates fragment: checkout, the mod step, then any extra step. Each argument changes one pin."""
    gates = (MOD_CHECKOUT if checkout else "") + body + extra
    scope = "      mods: ${{ steps.scope.outputs.mods }}\n" if scope_out else "      code: ${{ steps.scope.outputs.code }}\n"
    return ("jobs:\n  scope:\n    outputs:\n" + scope +
            "  gates:\n    runs-on: ubuntu-latest\n    needs: scope\n    steps:\n" + gates +
            "  pointer-windows:\n    runs-on: windows-latest\n    steps:\n      - run: echo\n")


class ModTestStepChecker(unittest.TestCase):
    def test_the_checker_passes_the_right_step(self):
        self.assertEqual(mods_problems(mod_doc()), [])

    def test_the_checker_sees_each_defect(self):
        defects = {
            "pipe": mod_doc(body=MOD_STEP.replace("|| fail=1", "| tail -1")),
            "or true": mod_doc(body=MOD_STEP.replace("|| fail=1", "|| true")),
            "continue-on-error": mod_doc(body=MOD_STEP.replace("        shell: bash\n", "        shell: bash\n        continue-on-error: true\n")),
            "one hardcoded file": mod_doc(body=MOD_STEP.replace("mods/*/*.test.mjs", "mods/plain-diff/plain-diff.test.mjs")),
            "no step": mod_doc(body=""),
            "wrong flag": mod_doc(body=MOD_STEP.replace("needs.scope.outputs.mods", "needs.scope.outputs.code")),
            "no !cancelled()": mod_doc(body=MOD_STEP.replace("!cancelled() && ", "")),
            "reads the event": mod_doc(body=MOD_STEP.replace("== 'true' }}", "== 'true' && github.event_name != 'pull_request' }}")),
            "no shell": mod_doc(body=MOD_STEP.replace("        shell: bash\n", "")),
            "shell sh": mod_doc(body=MOD_STEP.replace("shell: bash", "shell: sh")),
            "no checkout": mod_doc(checkout=False),
            "scope lacks the mods output": mod_doc(scope_out=False),
        }
        for label, doc in defects.items():
            with self.subTest(defect=label):
                self.assertTrue(mods_problems(doc), label)

# ---- every test file runs in a CI step. A test file that no run step names never fails a pull
# request, so its red stays invisible: lint/test_check_agent_models.py ran in no step. Failure
# classes: (a) product, a test file has no run line in gates.yml; (b) test, this parser misreads a
# run line (a comment, a quote, a block scalar); (c) stale, a test file was renamed or removed and
# its run line was not. Scope: test_*.py, test_*.sh and *.test.ps1 outside hidden folders.
# mutate_*.py is not a suite (mutate_shared.py is plumbing), and mods/*/*.test.mjs runs in the
# gates "Mod tests" glob step, so neither is listed here.
REPO = os.path.normpath(os.path.join(HERE, ".."))
TEST_FILE = re.compile(r"^(?:test_.*\.(?:py|sh)|.*\.test\.ps1)$")


def strip_comment(text):
    """`text` up to a `#` that opens a shell comment: at the start, or after a space, outside quotes."""
    quote = ""
    for i, ch in enumerate(text):
        if quote:
            quote = "" if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or text[i - 1] in " \t"):
            return text[:i]
    return text


# A block scalar head: `|` or `>`, then an optional indent digit and chomping sign, then an optional comment.
BLOCK_HEAD = re.compile(r"^[|>][0-9+-]*(?:[ \t]+#.*)?$")
RUN_KEY = re.compile(r"^(\s*)(- )?run:[ \t]*(.*)$")


def run_commands(text):
    """Each shell command a workflow runs: a one-line `run:` value, and each line of a block scalar
    under `run:`. A block holds the lines indented deeper than its key, so a sibling key (`env:`) ends
    it. A comment line, or a trailing comment, is not a command."""
    commands, block = [], None  # block: the column of the open run key
    for line in text.splitlines():
        body = line.strip()
        column = len(line) - len(line.lstrip(" "))
        if block is not None and body and column <= block:
            block = None
        if block is not None:
            commands.append(strip_comment(body))
            continue
        found = RUN_KEY.match(line)
        if not found:
            continue
        key_column = len(found.group(1)) + (2 if found.group(2) else 0)  # `- run:` keys sit after the dash
        value = found.group(3).strip()
        if BLOCK_HEAD.match(value):
            block = key_column
        else:
            commands.append(strip_comment(value))
    return commands


# A run step may name a path with a `./` or `$VAR/` (or `${VAR}/`) prefix. The prefix is dropped first.
# A folder in front of the path (`hooks/lint/test_x.py`) still names another file.
PATH_PREFIX = re.compile(r"(?<![\w.$/-])(?:\./|\$\{?\w+\}?/)")


def names_path(commands, path):
    """True when a command names `path` as a whole word, after a path prefix is dropped.
    `test_x_stop.py` does not name `test_x.py`, and `hooks/lint/test_x.py` does not name `lint/test_x.py`."""
    pattern = re.compile(r"(?<![\w./-])" + re.escape(path) + r"(?![\w./-])")
    return any(pattern.search(PATH_PREFIX.sub("", command)) for command in commands)


def find_test_files(root):
    """Repo-relative posix paths of the test files, skipping hidden folders such as .git and .claude.
    A folder the scan cannot read raises. It must fail the test, never read as holding no tests."""
    def unreadable(error):
        raise error
    found = []
    for folder, dirs, names in os.walk(root, onerror=unreadable):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        found += [os.path.relpath(os.path.join(folder, n), root).replace(os.sep, "/")
                  for n in names if TEST_FILE.match(n)]
    return sorted(found)


class CiCoverage(unittest.TestCase):
    def test_every_test_file_runs_in_a_ci_step(self):
        with open(GATES, encoding="utf-8") as handle:
            commands = run_commands(handle.read())
        missing = [p for p in find_test_files(REPO) if not names_path(commands, p)]
        self.assertEqual(missing, [], "no run step in gates.yml names: " + ", ".join(missing))

    def test_a_comment_line_is_not_a_run(self):
        # Rows: a comment line, a trailing comment, and a comment line inside a block. Named failure: a
        # commented-out suite counted as run, so CI looks covered when it is not.
        cases = [
            ("comment line", "      - run: echo\n      # run: python3 lint/test_x.py\n"),
            ("trailing comment", "      - run: echo  # python3 lint/test_x.py\n"),
            ("comment line in a block", "      - run: |\n          echo start\n          # python3 lint/test_x.py\n"),
        ]
        for case, text in cases:
            with self.subTest(case):
                self.assertFalse(names_path(run_commands(text), "lint/test_x.py"))

    def test_a_hash_inside_quotes_is_not_a_comment(self):
        text = '      - run: echo "a # b" && python3 lint/test_x.py\n'
        self.assertTrue(names_path(run_commands(text), "lint/test_x.py"))

    def test_a_lone_quote_does_not_hide_a_run(self):
        # Rows: a lone quote in a run keeps the run, and a lone quote in a step name is not a run.
        # Named failure: a quote hides a suite or fakes one.
        cases = [
            ("quote in a run", "      - run: echo don't && python3 lint/test_x.py\n", True),
            ("quote in a name", "      - name: Don't skip lint/test_x.py\n", False),
        ]
        for case, text, runs in cases:
            with self.subTest(case):
                self.assertEqual(bool(names_path(run_commands(text), "lint/test_x.py")), runs)

    def test_a_block_scalar_line_is_a_run(self):
        text = "      - run: |\n          echo start\n          python3 lint/test_x.py\n"
        self.assertTrue(names_path(run_commands(text), "lint/test_x.py"))

    def test_a_block_ends_at_the_next_step(self):
        text = ("      - run: |\n          echo\n"
                "      - name: lint/test_x.py\n"
                "      - run: python3 lint/test_y.py\n")
        commands = run_commands(text)
        self.assertFalse(names_path(commands, "lint/test_x.py"))
        self.assertTrue(names_path(commands, "lint/test_y.py"))

    def test_a_longer_or_deeper_name_does_not_cover_a_shorter_one(self):
        text = "      - run: python3 lint/test_x_stop.py\n      - run: python3 mylint/test_x.py\n"
        self.assertFalse(names_path(run_commands(text), "lint/test_x.py"))

    def test_a_chomping_block_indicator_is_a_block(self):
        # Heads "| # c" and ">- # c": a trailing comment after the indicator still opens a block.
        # Named failure: a block run is missed.
        for head in ("|-", ">-", "|+", "| # c", ">- # c"):
            with self.subTest(head=head):
                text = "      - run: %s\n          echo start\n          python3 lint/test_x.py\n" % head
                self.assertTrue(names_path(run_commands(text), "lint/test_x.py"))

    def test_a_dot_slash_path_is_a_run(self):
        text = "      - run: python3 ./lint/test_x.py\n"
        self.assertTrue(names_path(run_commands(text), "lint/test_x.py"))

    def test_a_workspace_variable_path_is_a_run(self):
        for path in ("$GITHUB_WORKSPACE/lint/test_x.py", "${GITHUB_WORKSPACE}/lint/test_x.py"):
            with self.subTest(path=path):
                text = "      - run: python3 %s\n" % path
                self.assertTrue(names_path(run_commands(text), "lint/test_x.py"))

    def test_a_sibling_key_ends_a_run_block(self):
        text = ("      - run: |\n          echo start\n"
                "        env:\n          MERGE_TESTS: lint/test_x.py\n")
        self.assertFalse(names_path(run_commands(text), "lint/test_x.py"))

    def test_a_path_under_another_folder_is_not_a_run(self):
        for path in ("hooks/lint/test_x.py", "$GITHUB_WORKSPACE/hooks/lint/test_x.py"):
            with self.subTest(path=path):
                text = "      - run: python3 %s\n" % path
                self.assertFalse(names_path(run_commands(text), "lint/test_x.py"))

    def test_an_unreadable_folder_fails_the_scan(self):
        with self.assertRaises(OSError):
            find_test_files(os.path.join(HERE, "no-such-folder-for-the-scan"))


if __name__ == "__main__":
    unittest.main()
