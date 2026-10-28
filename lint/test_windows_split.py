#!/usr/bin/env python3
"""Guard for the Windows split of .github/workflows/checks.yml.

Proves: (1) each suite command in REQUIRED runs in exactly one `windows-latest` job (none
dropped, none run twice); (2) at least MIN_JOBS `windows-latest` jobs carry those suites.
Cut F adds: the guard suite has its own Windows job (GUARD_JOB) and runs off it nowhere else; its
slice (GUARD_TESTS=windows-slice) runs only on pull_request; the guard mutation test has its own
Linux job (MUTATE_JOB) and runs nowhere else; both jobs skip on the `guard` scope flag.

Why not rule_audit.py: it reads step names only. This needs job boundaries and `run:` lines.
Line-based parse, stdlib only, like rule_audit. Only single-line `run: <cmd>` steps count.
CHECKS_YML overrides the path (used for red runs on a scratch copy).

CiCoverage (last class) also proves every test_*.py, test_*.sh and *.test.ps1 file has a run step.

Run with:  python3 lint/test_windows_split.py -v
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from workflow_steps import job_block, run_body, step_blocks, step_key  # noqa: E402  the one home of the step parser
CHECKS = os.environ.get("CHECKS_YML") or os.path.join(HERE, "..", ".github", "workflows", "checks.yml")
MIN_JOBS = 3

# The run commands of the old single `checks-windows` job. Edit here only on purpose.
REQUIRED = [
    "python hooks/test_guard.py",
    "python janitor/test_sweep.py",
    "python janitor/mutate_sweep.py",
    "python hooks/test_config_watch.py",
    "python hooks/test_precompact_handoff.py",
    "python hooks/test_decision_watch.py",
    "python hooks/test_prose_judge.py",
    "python hooks/test_rm_prompt_answer.py",
    "python hooks/test_agent_brief.py",
    "python hooks/test_wrappers.py",
    "python lint/test_report_guard.py",
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
# checks-windows-guard, runs the full suite off pull_request and the slice on it.
GUARD_CMD = "python hooks/test_guard.py"
GUARD_SLICE = "python hooks/test_guard.py [windows-slice]"
GUARD_SLICE_ENV = {"GUARD_TESTS": "windows-slice"}
GUARD_JOB = "checks-windows-guard"
# A long suite splits across shard jobs: the base job, then `<base>-2` to `<base>-<n>`. The full step of each
# carries SHARD_VAR[base]=<i>/<n> in its step env, and the n values cover 1 to n once each, so every case runs
# once. A shard job past the first never runs on pull_request: the required check is the base job alone, so
# the PR verdict stays in it (the slice there runs whole, with no shard value).
SHARD_VAR = {"checks-windows-guard": "GUARD_SHARD", "checks-windows-merge": "MERGE_SHARD"}
SHARD_CMD = {"checks-windows-guard": "python hooks/test_guard.py", "checks-windows-merge": "python merge/test_merge.py"}
SHARD_JOB_IF = "${{ github.event_name != 'pull_request' }}"


def shard_base(name):
    """The base job a shard job belongs to (`checks-windows-guard-2` -> `checks-windows-guard`), or None."""
    m = re.fullmatch(r"(.+)-([2-9]|[1-9][0-9]+)", name)
    return m.group(1) if m and m.group(1) in SHARD_VAR else None


# The guard mutation test moves off `checks` (Linux) to its own Linux job (cut F).
MUTATE_CMD = "python3 hooks/mutate_guard.py"
MUTATE_JOB = "checks-mutate-guard"
# The bin/shoot suite and its browser install have their own Linux job, off the `checks` lint job.
SHOOT_CMD = 'NODE_PATH="$PWD/.github/shoot/node_modules" node --test lint/test_shoot.mjs'
SHOOT_JOB = "checks-shoot"
# The scope flag each job skips on when the flag is not its own name.
FLAG_OF = {GUARD_JOB: "guard", MUTATE_JOB: "guard", SHOOT_JOB: "shoot"}


def key(st):
    """A step's run command; a test_merge or test_guard step with its slice env reads as its SLICE."""
    run = st.get("run")
    env = st.get("env") if isinstance(st.get("env"), dict) else {}
    if run == "python merge/test_merge.py" and "MERGE_TESTS" in env:
        return SLICE
    if run == GUARD_CMD and "GUARD_TESTS" in env:
        return GUARD_SLICE
    return run


def shard_problems(cmd, homes):
    """A suite in several jobs is one shard family: its base job and `<base>-2`..`<base>-<n>`, each full step with
    SHARD_VAR=<i>/<n>, the values 1/n to n/n once each. [] when the homes are such a family."""
    names = [n for n, _ in homes]
    bases = {shard_base(n) or n for n in names}
    base = next(iter(bases))
    if len(bases) != 1 or base not in SHARD_VAR or SHARD_CMD[base] != cmd:
        return [f"{cmd!r} runs {len(homes)} times on windows-latest: {names}"]
    n = len(homes)
    want_names = {base} | {f"{base}-{i}" for i in range(2, n + 1)}
    got = sorted((st.get("env") or {}).get(SHARD_VAR[base], "") if isinstance(st.get("env"), dict) else ""
                 for _, st in homes)
    want = sorted(f"{i}/{n}" for i in range(1, n + 1))
    problems = []
    if set(names) != want_names or len(names) != n:
        problems.append(f"{cmd!r} shard jobs are {names}, want {sorted(want_names)}")
    if got != want:
        problems.append(f"{cmd!r} {SHARD_VAR[base]} values are {got}, want {want}: a case would run twice or never")
    return problems


def placement_problems(text):
    """Strings naming each suite not run exactly once, or too few carrying jobs."""
    wj = windows_jobs(text)
    jobs = {n: [key(st) for st in j["steps"]] for n, j in wj.items()}
    problems = []
    homes = [n for n, runs in jobs.items() for r in runs if r == SLICE]
    if len(homes) != 1:
        problems.append(f"{SLICE!r} runs {len(homes)} times on windows-latest: {homes}")
    for cmd in REQUIRED:
        homes = [(n, st) for n, j in wj.items() for st in j["steps"] if key(st) == cmd]
        if len(homes) > 1:
            problems += shard_problems(cmd, homes)
        elif len(homes) != 1 or any(isinstance(st.get("env"), dict) and SHARD_VAR.get(n) in st["env"]
                                    for n, st in homes):
            problems.append(f"{cmd!r} runs {len(homes)} times on windows-latest: {[n for n, _ in homes]}"
                            + (" (a lone shard value)" if homes else ""))
    carrying = [n for n, runs in jobs.items() if any(r in REQUIRED for r in runs)]
    if len(carrying) < MIN_JOBS:
        problems.append(f"{len(carrying)} windows-latest jobs carry the suites, need {MIN_JOBS}: {carrying}")
    return problems


# Steps whose `shell:` is pinned. Any other REQUIRED step must set none.
SHELL = {"sh hooks/test_install_windows.sh": "bash", "bash actions/stamp/test_action.sh": "bash"}
# Steps whose whole `if:` is pinned (the mutation test must stay off pull_request and on its scope flag).
IF_PIN = {"python janitor/mutate_sweep.py":
          "${{ !cancelled() && github.event_name != 'pull_request' && needs.scope.outputs.sweep == 'true' }}",
          # The full merge suite runs on every event but pull_request; the slice only on it.
          "python merge/test_merge.py":
          "${{ !cancelled() && github.event_name != 'pull_request' && needs.scope.outputs.code == 'true' }}",
          SLICE: "${{ !cancelled() && github.event_name == 'pull_request' && needs.scope.outputs.code == 'true' }}",
          # The full guard suite runs off pull_request; the guard slice only on it (cut F).
          GUARD_CMD: "${{ !cancelled() && github.event_name != 'pull_request' && needs.scope.outputs.code == 'true' }}",
          GUARD_SLICE: "${{ !cancelled() && github.event_name == 'pull_request' && needs.scope.outputs.code == 'true' }}"}


FLAGS = ["checks_windows", "checks_windows_merge", "checks_windows_rest", "checks_macos", "shell_macos", "pointer_windows",
         "code", "guard", "sweep", "shoot"]


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


def job_check_problems(name, job, flag=None):
    """`needs: scope`, and a job-level if that (a) reads needs.scope.outputs.<own flag>, (b) is true on push,
    schedule and workflow_dispatch even when every flag is 'false', (c) is true on pull_request with every flag
    'true' and false with every flag 'false'. The lint job `checks` needs scope and has no if. `flag` names the
    scope output for a job whose flag is not its own name (FLAG_OF)."""
    problems = []
    if not re.fullmatch(r"\[?\s*scope\s*\]?", job["needs"] or ""):
        problems.append(f"{name}: needs is {job['needs']}, want scope")
    expr = job["if"]
    if shard_base(name):  # a shard past the first: every event but pull_request, whatever the flags
        return problems + ([] if expr == SHARD_JOB_IF else [f"{name}: shard job if is {expr}, want {SHARD_JOB_IF}"])
    if expr is None and name != "checks":
        return problems + [f"{name}: no job-level if"]
    own = flag or name.replace("-", "_")
    if name == "checks":  # the lint job runs on every PR: no job-level if
        return problems + ([f"checks: job-level if: {expr}"] if expr is not None else [])
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
    """A `scope` job on ubuntu with every flag as a job output; every other job passes job_check_problems
    (the lint job `checks` needs scope but runs always)."""
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
        # ci-done is the fan-in that comments when a run ends red: it needs every job, not scope
        # alone (actions/ci-done-comment/test_comment.py checks its needs and if).
        if name not in ("scope", "ci-done"):
            problems += job_check_problems(name, job, FLAG_OF.get(name))
    return problems


def hardening_problems(text):
    """A carrying job has `needs: scope`, a job-level if of the allowed form, and setup-python; a REQUIRED step keeps
    `!cancelled()`, its pinned shell and its pinned if."""
    problems = []
    n = text.count("MERGE_TESTS")  # one mention only: the slice step's env. Job, workflow or $GITHUB_ENV copies would slice every run.
    if n != 1:
        problems.append(f"MERGE_TESTS appears {n} times in checks.yml, want exactly 1 (the slice step's env)")
    slice_envs = {SLICE: SLICE_ENV, GUARD_SLICE: GUARD_SLICE_ENV}
    # A shard value outside a full step's own env (job, workflow or $GITHUB_ENV) would reach the slice on pull_request.
    for var in SHARD_VAR.values():
        homes = sum(1 for j in all_jobs(text).values() for st in j["steps"]
                    if isinstance(st.get("env"), dict) and var in st["env"] and key(st) in REQUIRED)
        if text.count(var) != homes:
            problems.append(f"{var} appears {text.count(var)} times in checks.yml, want {homes} (once per shard step's env)")
    for name, job in windows_jobs(text).items():
        steps = job["steps"]
        if not any(key(st) in REQUIRED for st in steps):
            continue
        problems += job_check_problems(name, job, FLAG_OF.get(name))
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
    and the slice on it, both run only on the guard flag. No other Windows job runs the guard suite."""
    jobs = windows_jobs(text)
    if GUARD_JOB not in jobs:
        return [f"no windows-latest job named {GUARD_JOB}"]
    problems = []
    for name, job in jobs.items():
        if name not in (GUARD_JOB, ) and shard_base(name) != GUARD_JOB and any(
                key(st) in (GUARD_CMD, GUARD_SLICE) for st in job["steps"]):
            problems.append(f"{name} runs the guard suite; it belongs to {GUARD_JOB} and its shard jobs alone")
        if shard_base(name) and any(key(st) in (SLICE, GUARD_SLICE) for st in job["steps"]):
            problems.append(f"{name} runs a slice; the slice belongs to the base job, the required check")
    job = jobs[GUARD_JOB]
    problems += job_check_problems(GUARD_JOB, job, FLAG_OF[GUARD_JOB])
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
        problems.append(f"GUARD_TESTS appears {g} times in checks.yml, want exactly 1 (the guard slice step's env)")
    # CI runs the whole guard suite. A GUARD_FAMILY here would make CI run one family and call it green.
    f = text.count("GUARD_FAMILY")
    if f:
        problems.append(f"GUARD_FAMILY appears {f} times in checks.yml, want 0 (CI runs every case)")
    return problems


def mutate_problems(text):
    """Cut F. The guard mutation test runs in MUTATE_JOB on Linux, and in no other job."""
    jobs = all_jobs(text)
    homes = [n for n, j in jobs.items() for st in j["steps"] if st.get("run") == MUTATE_CMD]
    problems = []
    if homes != [MUTATE_JOB]:
        problems.append(f"{MUTATE_CMD!r} runs in {homes}, want exactly [{MUTATE_JOB!r}]")
    if MUTATE_JOB in jobs and not (jobs[MUTATE_JOB]["os"] or "").startswith("ubuntu"):
        problems.append(f"{MUTATE_JOB} runs on {jobs[MUTATE_JOB]['os']}, want ubuntu-latest")
    return problems


def shoot_problems(text, required):
    """The shoot suite runs in SHOOT_JOB on Linux and in no other job, with no step-level if, so a job
    that runs cannot skip the suite and read green. No other job installs a browser. SHOOT_JOB is a
    required check (`required`: stamp.json merge.requiredChecks)."""
    jobs = all_jobs(text)
    homes = [n for n, j in jobs.items() for st in j["steps"] if st.get("run") == SHOOT_CMD]
    problems = []
    if homes != [SHOOT_JOB]:
        problems.append(f"{SHOOT_CMD!r} runs in {homes}, want exactly [{SHOOT_JOB!r}]")
    job = jobs.get(SHOOT_JOB)
    if job:
        if not (job["os"] or "").startswith("ubuntu"):
            problems.append(f"{SHOOT_JOB} runs on {job['os']}, want ubuntu-latest")
        problems += [f"{SHOOT_JOB}: step {st} has a step-level if" for st in job["steps"] if "if" in st]
    # The raw job text, so an install inside a `run: |` block counts too.
    installs = [n for n in jobs if n != SHOOT_JOB and "playwright install" in (job_block(text, n) or "")]
    if installs:
        problems.append(f"a browser install runs outside {SHOOT_JOB}: {installs}")
    if required is not None and SHOOT_JOB not in required:  # None: stamp.json reads "protection", which no offline test can read
        problems.append(f"{SHOOT_JOB} is not in merge.requiredChecks, so a red shoot suite blocks no merge")
    return problems


class WindowsSplit(unittest.TestCase):
    def setUp(self):
        with open(CHECKS, encoding="utf-8") as f:
            self.text = f.read()
        self.assertTrue(windows_jobs(self.text), "parsed no windows-latest job: wrong path or parse")

    def test_each_suite_runs_exactly_once(self):
        bad = [p for p in placement_problems(self.text) if "times" in p]
        self.assertEqual(bad, [])
        # The mutation test is placed
        # once in its own job. Named failure: a mutation test dropped or doubled, so mutants go unrun.
        self.assertEqual(mutate_problems(self.text), [])

    def test_the_shoot_suite_has_its_own_required_job(self):
        # Named failure: the browser install shares the `checks` cap again, or a red shoot suite blocks no merge.
        with open(STAMP, encoding="utf-8") as f:
            required = json.load(f)["merge"]["requiredChecks"]
        self.assertEqual(shoot_problems(self.text, required if isinstance(required, list) else None), [])  # "protection": whether the job is required is unknown here

    def test_the_shoot_checker_sees_its_defects(self):
        good = (f"jobs:\n  checks:\n    runs-on: ubuntu-latest\n    steps:\n      - name: lint\n        run: ruff\n"
                f"  {SHOOT_JOB}:\n    runs-on: ubuntu-latest\n    steps:\n"
                f"      - name: Install Chromium\n        run: playwright install chromium\n"
                f"      - name: shoot fixture suite\n        run: {SHOOT_CMD}\n")
        self.assertEqual(shoot_problems(good, [SHOOT_JOB]), [])
        bad = {"back in checks": good.replace("        run: ruff\n", f"        run: ruff\n      - name: s\n        run: {SHOOT_CMD}\n"),
               "install in checks": good.replace("run: ruff", "run: playwright install --with-deps chromium"),
               "install in a checks block": good.replace("run: ruff", "run: |\n          ruff\n          playwright install chromium"),
               "step-level if": good.replace(f"        run: {SHOOT_CMD}", f"        if: false\n        run: {SHOOT_CMD}"),
               "on windows": good.replace(f"  {SHOOT_JOB}:\n    runs-on: ubuntu-latest", f"  {SHOOT_JOB}:\n    runs-on: windows-latest"),
               "suite dropped": good.replace(f"        run: {SHOOT_CMD}\n", "        run: true\n")}
        for label, text in bad.items():
            self.assertTrue(shoot_problems(text, [SHOOT_JOB]), label)
        self.assertTrue(shoot_problems(good, []), "not required")

    def test_scope_job_checks_every_other_job(self):
        self.assertEqual(scope_problems(self.text), [])
        # The guard and mutate jobs skip on the
        # guard flag. Named failure: a cut job runs or never runs on push, schedule and dispatch.
        jobs = all_jobs(self.text)
        for name in (GUARD_JOB, MUTATE_JOB):
            self.assertIn(name, jobs, f"no job named {name}")
            self.assertEqual(job_check_problems(name, jobs[name], FLAG_OF[name]), [])

    def test_the_check_form_sees_its_defects(self):
        ok = "${{ needs.scope.outputs.checks_macos == 'true' || github.event_name != 'pull_request' }}"
        job = {"needs": "scope", "if": ok}
        self.assertEqual(job_check_problems("checks-macos", job), [])
        self.assertEqual(job_check_problems("checks", {"needs": "scope", "if": None}), [])
        self.assertTrue(job_check_problems("checks", {"needs": None, "if": None}))
        bad = {"pr_only": "${{ needs.scope.outputs.checks_macos == 'true' }}",  # skips on push when the flag is false
               "not_pr_always": "${{ github.event_name != 'pull_request' }}",  # never reads the flag
               "other_flag": ok.replace("checks_macos", "checks_windows"),
               "always_on_pr": "${{ !cancelled() || needs.scope.outputs.checks_macos == 'true' }}"}
        for label, expr in bad.items():
            self.assertTrue(job_check_problems("checks-macos", dict(job, **{"if": expr})), label)
        self.assertTrue(job_check_problems("checks-macos", dict(job, needs="checks")))
        self.assertTrue(job_check_problems("checks-macos", dict(job, **{"if": None})))

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
            return ("jobs:\n  checks-windows-merge:\n    runs-on: windows-latest\n    needs: scope\n"
                    "    if: ${{ needs.scope.outputs.checks_windows_merge == 'true' || github.event_name != 'pull_request' }}\n    steps:\n"
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

    def test_checker_sees_the_shard_defects(self):
        full_if = IF_PIN[GUARD_CMD]
        base_if = "${{ needs.scope.outputs.guard == 'true' || github.event_name != 'pull_request' }}"

        def job(name, shard, job_if=SHARD_JOB_IF, slice_=False):
            return (f"  {name}:\n    runs-on: windows-latest\n    needs: scope\n    if: {job_if}\n    steps:\n"
                    "      - uses: actions/setup-python@abc # v6\n"
                    f"      - name: Full\n        if: {full_if}\n"
                    + (f"        env:\n          GUARD_SHARD: {shard}\n" if shard else "")
                    + "        run: python hooks/test_guard.py\n"
                    + (f"      - name: Slice\n        if: {IF_PIN[GUARD_SLICE]}\n        env:\n"
                       "          GUARD_TESTS: windows-slice\n        run: python hooks/test_guard.py\n" if slice_ else ""))

        def doc(*jobs):
            return "jobs:\n" + "".join(jobs)

        def place(text):
            return [p for p in placement_problems(text) if "test_guard" in p]

        base = job("checks-windows-guard", "1/3", base_if, slice_=True)
        good = doc(base, job("checks-windows-guard-2", "2/3"), job("checks-windows-guard-3", "3/3"))
        self.assertEqual(place(good), [])
        self.assertEqual(guard_problems(good), [])
        self.assertEqual(job_check_problems("checks-windows-guard-2", {"needs": "scope", "if": SHARD_JOB_IF}), [])
        bad = {
            "a shard dropped": doc(base, job("checks-windows-guard-2", "2/3")),
            "a shard doubled": doc(base, job("checks-windows-guard-2", "2/3"), job("checks-windows-guard-3", "2/3")),
            "a shard unset": doc(base, job("checks-windows-guard-2", "2/3"), job("checks-windows-guard-3", "")),
            "n disagrees": doc(base, job("checks-windows-guard-2", "2/2"), job("checks-windows-guard-3", "3/3")),
            "a lone shard": doc(job("checks-windows-guard", "1/2", base_if, slice_=True)),
            "a stray job name": doc(base, job("checks-windows-guard-2", "2/3"), job("checks-windows-rest", "3/3")),
        }
        for label, text in bad.items():
            self.assertTrue(place(text) or guard_problems(text), label)
        # A shard job that runs on pull_request, or runs the slice, takes the PR verdict out of the required check.
        self.assertTrue(job_check_problems("checks-windows-guard-2", {"needs": "scope", "if": base_if}))
        self.assertTrue(guard_problems(doc(base, job("checks-windows-guard-2", "2/3", slice_=True),
                                           job("checks-windows-guard-3", "3/3"))))
        # A shard value set for the whole job or workflow would cut the PR slice too.
        self.assertFalse([p for p in hardening_problems(good) if "GUARD_SHARD appears" in p])
        for leak in (good.replace("    steps:\n", "    env:\n      GUARD_SHARD: 1/3\n    steps:\n", 1),
                     "env:\n  GUARD_SHARD: 1/3\n" + good):
            self.assertTrue([p for p in hardening_problems(leak) if "GUARD_SHARD appears" in p], leak)

    def test_the_guard_suite_has_its_own_windows_job(self):
        self.assertEqual(guard_problems(self.text), [])

    def test_checks_sets_no_guard_family(self):
        self.assertEqual([p for p in guard_problems(self.text) if "GUARD_FAMILY" in p], [])
        # The red run: the checker flags a
        # guard family set in checks. Named failure: a guard family runs in checks and CI goes green.
        bad = [p for p in guard_problems(self.text + "\n# GUARD_FAMILY=shared-tree\n") if "GUARD_FAMILY" in p]
        self.assertTrue(bad)

    def test_checker_sees_the_guard_slice_and_mutate_defects(self):
        full_if, slice_if = IF_PIN[GUARD_CMD], IF_PIN[GUARD_SLICE]
        good_job_if = "${{ needs.scope.outputs.guard == 'true' || github.event_name != 'pull_request' }}"

        def doc(full_if=full_if, slice_if=slice_if, env="windows-slice", job_if=good_job_if, extra="", more=""):
            return ("jobs:\n  checks-windows-guard:\n    runs-on: windows-latest\n    needs: scope\n"
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
        self.assertTrue(guard_problems(doc(job_if=good_job_if.replace("guard", "checks_windows"))))  # wrong flag
        self.assertTrue(guard_problems(doc(job_if="${{ needs.scope.outputs.guard == 'true' }}")))  # skips on push
        self.assertTrue(guard_problems(doc(more="  checks-windows:\n    runs-on: windows-latest\n    needs: scope\n"
                                               "    if: ${{ needs.scope.outputs.checks_windows == 'true' }}\n"
                                               "    steps:\n      - run: python hooks/test_guard.py\n")))
        checks = "jobs:\n  checks-mutate-guard:\n    runs-on: ubuntu-latest\n    steps:\n      - run: python3 hooks/mutate_guard.py\n"
        self.assertEqual(mutate_problems(checks), [])
        self.assertTrue(mutate_problems(checks.replace("checks-mutate-guard", "checks")))  # in the lint job
        self.assertTrue(mutate_problems(checks.replace("ubuntu-latest", "windows-latest")))  # on Windows
        self.assertTrue(mutate_problems("jobs:\n  checks:\n    runs-on: ubuntu-latest\n    steps:\n"
                                        "      - run: python3 hooks/mutate_guard.py\n"
                                        "  checks-mutate-guard:\n    runs-on: ubuntu-latest\n    steps:\n"
                                        "      - run: python3 hooks/mutate_guard.py\n"))  # runs twice


# Mod and map-skill tests: one step in each of the jobs checks (Linux), checks-windows and checks-macos, on
# the `mods` scope flag. The step runs .github/scripts/mod-tests.sh with no argument, and that script is the
# one home of both suites. A copy of either suite in a run step would drift, so no step may hold one. The
# script finds every *.test.mjs and *.test.js file under mods/ except node_modules, so a new mods/<name>/
# joins with no edit here. It carries the exit code of every file: a failing first or last file fails it.
# The checker self-tests (ModTestStepChecker) run on synthetic text and pass now: they show each defect is
# seen. MOD_SCRIPT_NAME marks the step that runs the script.
MOD_FLAG = "mods"
MOD_JOBS = ["checks", "checks-windows", "checks-macos"]
MOD_SCRIPT_NAME = "mod-tests.sh"
MOD_CMD = "bash .github/scripts/mod-tests.sh"
MOD_SCRIPT = os.environ.get("MOD_TESTS_SH") or os.path.join(HERE, "..", ".github", "scripts", MOD_SCRIPT_NAME)
STAMP = os.path.join(HERE, "..", ".github", "stamp.json")
CHECKOUT = re.compile(r"^(?:      - |        )uses:[ \t]*actions/checkout@", re.M)
# A copy of either suite in a run command: the mod glob, a bare `node --test`, or the skill folder.
INLINE_COPY = re.compile(r"\*\.test\.m?js|\bnode\s+--test\s*$|plain-english-map")


def mod_steps(text, job):
    """The steps of one job whose run names the mod-test script."""
    return [st for st in step_blocks(job_block(text, job)) if MOD_SCRIPT_NAME in (run_body(st) or "")]


def mods_scope_problems(text):
    """The scope job must export the mods output. Without it needs.scope.outputs.mods is empty and the step never runs."""
    scope = job_block(text, "scope") or ""
    if not re.search(r"^      mods:[ \t]*\$\{\{[ \t]*steps\.scope\.outputs\.mods[ \t]*\}\}[ \t]*$", scope, re.M):
        return ["scope job does not export the mods output"]
    return []


def job_mod_step_problems(text, job):
    """Pins on the one mod-test step of one job. [] when the step is right."""
    homes = mod_steps(text, job)
    if len(homes) != 1:
        return [f"{job}: {len(homes)} steps run {MOD_SCRIPT_NAME}, want 1"]
    st = homes[0]
    steps = step_blocks(job_block(text, job))
    i = steps.index(st)
    problems = []
    cond = step_key(st, "if") or ""
    if "!cancelled()" not in cond:
        problems.append(f"{job}: mod step if lacks !cancelled(): {cond}")
    if f"needs.scope.outputs.{MOD_FLAG} == 'true'" not in cond:
        problems.append(f"{job}: mod step if does not read needs.scope.outputs.{MOD_FLAG}: {cond}")
    if "github.event_name" in cond:
        problems.append(f"{job}: mod step if reads the event; the {MOD_FLAG} flag alone decides: {cond}")
    if step_key(st, "shell") != "bash":
        problems.append(f"{job}: mod step shell is {step_key(st, 'shell')}, want bash")
    if step_key(st, "continue-on-error") is not None:
        problems.append(f"{job}: mod step sets continue-on-error, which swallows the exit code")
    body = (run_body(st) or "").strip()
    if body != MOD_CMD:
        problems.append(f"{job}: mod step runs {body!r}, want {MOD_CMD!r} with no argument")
    checkout = [j for j, s in enumerate(steps) if CHECKOUT.search(s)]
    if not checkout or checkout[0] > i:
        problems.append(f"{job}: no actions/checkout before the mod step")
    if i != len(steps) - 1:
        problems.append(f"{job}: mod step is not the last step")
    return problems


def mods_step_problems(text):
    """Pins on the mod-test step of each job in MOD_JOBS, and no inline copy of either suite anywhere."""
    problems = []
    for job in MOD_JOBS:
        problems += job_mod_step_problems(text, job)
    problems += [f"a run step holds a copy of a mod or map-skill suite: {c!r}"
                 for c in run_commands(text) if INLINE_COPY.search(c)]
    return problems


def mods_problems(text):
    return mods_scope_problems(text) + mods_step_problems(text)


def script_problems(script):
    """Pins on the script's text. A pipe or `|| true` hides a failing file's exit code. Comment lines and
    `case` patterns (`mods|skill)`) are not pipes."""
    code = [re.sub(r"^\s*[\w|\"'*-]+\)", "", ln) for ln in script.splitlines() if not ln.lstrip().startswith("#")]
    body = "\n".join(code)
    problems = []
    if re.search(r"(?<!\|)\|(?!\|)", body):
        problems.append("mod script pipes a command: the pipe takes the last command's exit code")
    if re.search(r"\|\|\s*(?:true|:)(?!\w)", body):
        problems.append("mod script ends a command with || true or || :")
    return problems


class ScriptRun:
    """What one run of the mod script left: exit code, merged output, and the npm calls its shim saw."""
    def __init__(self, rc, out, npm):
        self.rc, self.out, self.npm = rc, out, npm


def run_mod_script(arg, files, dirs=(), find_exit=None, cwd=".", script=None):
    """Run the script file in a scratch repo, with `arg` (None for no argument). files maps a path to True
    (passes) or False (fails). dirs are empty folders to make. find_exit, when set, puts a `find` first on
    PATH that runs the real find and then exits with that code, as a find does that meets an error after it
    listed files. An `npm` shim records its arguments, so no run reaches the network. cwd is a repo-relative
    folder to start in."""
    with tempfile.TemporaryDirectory() as root:
        work = os.path.join(root, "repo")
        shim = os.path.join(root, "shim")
        os.makedirs(shim)
        for d in (*dirs, cwd, ".github/scripts"):
            os.makedirs(os.path.join(work, d), exist_ok=True)
        calls = os.path.join(root, "npm.log")
        shims = {"npm": f'#!/bin/sh\necho "$@" >> "{calls}"\nexit 0\n'}
        if find_exit is not None:
            shims["find"] = f'#!/bin/sh\n"{shutil.which("find")}" "$@"\nexit {find_exit}\n'
        for name, body in shims.items():
            with open(os.path.join(shim, name), "w", encoding="utf-8", newline="\n") as f:
                f.write(body)
            os.chmod(os.path.join(shim, name), 0o755)
        env = dict(os.environ, PATH=shim + os.pathsep + os.environ["PATH"])
        for rel, ok in files.items():
            full = os.path.join(work, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write("// fixture\n" if ok else 'throw new Error("planted failure");\n')
        target = os.path.join(work, ".github", "scripts", MOD_SCRIPT_NAME)
        shutil.copyfile(script or MOD_SCRIPT, target)
        r = subprocess.run([shutil.which("bash"), "--noprofile", "--norc", target.replace("\\", "/")] + ([arg] if arg is not None else []),
                           cwd=os.path.join(work, cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, timeout=300, env=env)
        npm = open(calls, encoding="utf-8").read().splitlines() if os.path.exists(calls) else []
        return ScriptRun(r.returncode, r.stdout, npm)


SKILL_OK = {"skills/plain-english-map/tests/ok.test.mjs": True}
NPM_CI = "ci --ignore-scripts --no-audit --no-fund"


class ModTestStep(unittest.TestCase):
    def setUp(self):
        with open(CHECKS, encoding="utf-8") as f:
            self.text = f.read()

    def test_the_scope_job_exports_the_mods_flag(self):
        self.assertEqual(mods_scope_problems(self.text), [])

    def test_each_of_the_three_jobs_runs_the_script_in_one_pinned_step(self):
        for job in MOD_JOBS:
            with self.subTest(job=job):
                self.assertEqual(job_mod_step_problems(self.text, job), [])

    def test_no_run_step_holds_a_copy_of_either_suite(self):
        copies = [c for c in run_commands(self.text) if INLINE_COPY.search(c)]
        self.assertEqual(copies, [])

    def test_checks_stays_a_required_check_and_mods_adds_no_name(self):
        """Control, green now: the step rides jobs that are already required, so the list gains no name."""
        with open(STAMP, encoding="utf-8") as f:
            required = json.load(f)["merge"]["requiredChecks"]
        if required == "protection":  # the list lives in branch protection, which no offline test reads: check only that the workflow gains no mod job
            self.assertEqual([n for n in all_jobs(self.text) if "mod" in n.lower()], [])
            return
        for job in MOD_JOBS:
            self.assertIn(job, required)
        self.assertEqual([n for n in required if "mod" in n.lower()], [])


@unittest.skipUnless(shutil.which("bash") and shutil.which("node") and shutil.which("find"), "needs bash, node and find on PATH")
class ModTestScript(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.exists(MOD_SCRIPT), f"{MOD_SCRIPT} is missing, so no job runs a mod test")

    def test_the_script_text_has_no_pipe_and_no_or_true(self):
        with open(MOD_SCRIPT, encoding="utf-8") as f:
            self.assertEqual(script_problems(f.read()), [])

    def test_the_script_fails_when_any_mod_test_fails(self):
        cases = [
            ("all pass", {"mods/a/a.test.mjs": True, "mods/b/b.test.mjs": True}, True),
            ("first file fails", {"mods/a/first.test.mjs": False, "mods/b/b.test.mjs": True}, False),
            ("last file fails, in a new mod", {"mods/a/a.test.mjs": True, "mods/zz-new/last.test.mjs": False}, False),
            ("nested tests/ file fails", {"mods/a/a.test.mjs": True, "mods/a/tests/b.test.mjs": False}, False),
            ("*.test.js file fails", {"mods/a/a.test.mjs": True, "mods/a/c.test.js": False}, False),
            # Control: a dependency's own test under node_modules is not ours to run.
            ("node_modules test fails", {"mods/a/a.test.mjs": True, "mods/a/node_modules/dep/d.test.js": False}, True),
        ]
        for label, files, ok in cases:
            with self.subTest(case=label):
                r = run_mod_script("mods", files)
                self.assertEqual(r.rc == 0, ok, f"{label}: exit {r.rc}\n{r.out}")

    def test_the_script_fails_when_it_finds_no_test_or_find_errors(self):
        """`done < <(find ...)` drops find's exit code, and an empty loop exits 0 with nothing run."""
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
                r = run_mod_script("mods", files, dirs, find_exit)
                self.assertNotEqual(r.rc, 0, f"{label}: the script exited 0\n{r.out}")
        self.assertEqual(run_mod_script("mods", ok).rc, 0)  # control: one passing file and a clean find pass

    def test_the_script_prints_the_file_count_before_it_runs_them(self):
        files = {"mods/a/a.test.mjs": True, "mods/a/tests/b.test.mjs": True, "mods/c/c.test.js": False,
                 "mods/a/node_modules/dep/d.test.js": True, "mods/a/readme.md": True}
        r = run_mod_script("mods", files)
        lines = r.out.splitlines()
        self.assertIn("mod tests: 3 files", lines, r.out)
        self.assertLess(r.out.index("mod tests: 3 files"), r.out.index("planted failure"), "the count came after a run")

    def test_the_script_runs_from_the_repo_root_whatever_the_cwd(self):
        r = run_mod_script("mods", {"mods/a/a.test.mjs": True}, cwd="mods/a")
        self.assertEqual(r.rc, 0, r.out)
        self.assertIn("mod tests: 1 files", r.out.splitlines())

    def test_an_unknown_argument_exits_2_and_runs_nothing(self):
        for arg in ("bogus", "all", "--help", "MODS"):
            with self.subTest(arg=arg):
                r = run_mod_script(arg, dict(SKILL_OK, **{"mods/a/a.test.mjs": True}))
                self.assertEqual(r.rc, 2, r.out)
                self.assertEqual(r.npm, [])
                self.assertNotIn("mod tests:", r.out)

    def test_the_mods_argument_runs_phase_one_only(self):
        r = run_mod_script("mods", dict(SKILL_OK, **{"mods/a/a.test.mjs": True}))
        self.assertEqual((r.rc, r.npm), (0, []), r.out)

    def test_the_skill_argument_runs_phase_two_only(self):
        # A failing mod file must not matter: phase one does not run.
        r = run_mod_script("skill", dict(SKILL_OK, **{"mods/a/a.test.mjs": False}))
        self.assertEqual(r.rc, 0, r.out)
        self.assertEqual(r.npm, [NPM_CI])
        self.assertNotIn("mod tests:", r.out)

    def test_the_skill_phase_fails_when_a_skill_test_fails(self):
        r = run_mod_script("skill", {"skills/plain-english-map/tests/bad.test.mjs": False})
        self.assertNotEqual(r.rc, 0, r.out)

    def test_no_argument_runs_both_phases_and_phase_two_runs_after_a_phase_one_failure(self):
        mods_ok, mods_bad = {"mods/a/a.test.mjs": True}, {"mods/a/a.test.mjs": False}
        skill_bad = {"skills/plain-english-map/tests/bad.test.mjs": False}
        cases = [
            ("both pass", dict(SKILL_OK, **mods_ok), True),
            ("phase one fails", dict(SKILL_OK, **mods_bad), False),
            ("phase two fails", dict(skill_bad, **mods_ok), False),
            ("both fail", dict(skill_bad, **mods_bad), False),
        ]
        for label, files, ok in cases:
            with self.subTest(case=label):
                r = run_mod_script(None, files)
                self.assertEqual(r.rc == 0, ok, f"{label}: exit {r.rc}\n{r.out}")
                self.assertEqual(r.npm, [NPM_CI], f"{label}: phase two did not run, or ran twice")
                self.assertIn("mod tests: 1 files", r.out.splitlines())


MOD_CHECKOUT = ("      - uses: actions/checkout@08c6903cd8c0fde910a37f88322edcfb5dd907a8 # v5.0.0\n"
                "        with:\n          fetch-depth: 0\n\n")
MOD_STEP = ("      - name: Mod and map-skill tests\n"
            "        if: ${{ !cancelled() && needs.scope.outputs.mods == 'true' }}\n"
            "        shell: bash\n"
            f"        run: {MOD_CMD}\n")
MOD_SCRIPT_TEXT = ("#!/usr/bin/env bash\n"
                   "# Phase one.\n"
                   "case \"${1:-}\" in\n"
                   "  mods|skill|\"\") ;;\n"
                   "  *) exit 2 ;;\n"
                   "esac\n"
                   "list=$(find mods -name node_modules -prune -o -name '*.test.mjs' -print) || exit 1\n"
                   "fail=0\n"
                   "while IFS= read -r f; do\n"
                   "  node \"$f\" || fail=1\n"
                   "done <<< \"$list\"\n"
                   "exit \"$fail\"\n")


def mod_doc(steps=None, extra=None, checkout=True, scope_out=True):
    """A synthetic checks fragment: the three jobs, each with a checkout, then its steps. `steps` maps a job to
    its step text (default MOD_STEP). `extra` maps a job to a step added after the mod step."""
    steps, extra = steps or {}, extra or {}
    scope = "      mods: ${{ steps.scope.outputs.mods }}\n" if scope_out else "      code: ${{ steps.scope.outputs.code }}\n"
    jobs = "".join(f"  {j}:\n    runs-on: ubuntu-latest\n    needs: scope\n    steps:\n"
                   + (MOD_CHECKOUT if checkout else "") + steps.get(j, MOD_STEP) + extra.get(j, "")
                   for j in MOD_JOBS)
    return "jobs:\n  scope:\n    outputs:\n" + scope + jobs + "  pointer-windows:\n    runs-on: windows-latest\n    steps:\n      - run: echo\n"


def only(job, body):
    """The steps argument of mod_doc that changes one job's mod step."""
    return {job: body}


class ModTestStepChecker(unittest.TestCase):
    def test_the_checker_passes_the_right_step(self):
        self.assertEqual(mods_problems(mod_doc()), [])

    def test_the_checker_sees_each_defect(self):
        inline_glob = ("      - name: Mod tests\n        run: |\n"
                       "          find mods -name '*.test.mjs' -print\n")
        inline_skill = "      - name: Skill\n        run: |\n          cd skills/plain-english-map/tests\n          node --test\n"
        defects = {
            "no step in checks": mod_doc(steps=only("checks", "")),
            "step missing from checks-windows": mod_doc(steps=only("checks-windows", "")),
            "step missing from checks-macos": mod_doc(steps=only("checks-macos", "")),
            "step passes an argument": mod_doc(steps=only("checks-macos", MOD_STEP.replace(".sh\n", ".sh mods\n"))),
            "step passes skill": mod_doc(steps=only("checks", MOD_STEP.replace(".sh\n", ".sh skill\n"))),
            "step calls another script": mod_doc(steps=only("checks", MOD_STEP.replace("mod-tests.sh", "mod-tests.sh; echo"))),
            "two steps in one job": mod_doc(steps=only("checks-windows", MOD_STEP + MOD_STEP)),
            "inline copy of the mod glob in checks": mod_doc(extra={"checks": inline_glob}),
            "inline copy of the mod glob in checks-windows": mod_doc(extra={"checks-windows": inline_glob}),
            "inline copy of the skill run": mod_doc(extra={"checks": inline_skill}),
            "old mod step kept beside the new one": mod_doc(steps=only("checks", inline_glob + MOD_STEP)),
            "wrong flag": mod_doc(steps=only("checks-windows", MOD_STEP.replace("outputs.mods", "outputs.code"))),
            "no !cancelled()": mod_doc(steps=only("checks-macos", MOD_STEP.replace("!cancelled() && ", ""))),
            "reads the event": mod_doc(steps=only("checks", MOD_STEP.replace("== 'true' }}", "== 'true' && github.event_name != 'pull_request' }}"))),
            "no shell": mod_doc(steps=only("checks-windows", MOD_STEP.replace("        shell: bash\n", ""))),
            "shell sh": mod_doc(steps=only("checks-macos", MOD_STEP.replace("shell: bash", "shell: sh"))),
            "shell pwsh": mod_doc(steps=only("checks-windows", MOD_STEP.replace("shell: bash", "shell: pwsh"))),
            "continue-on-error": mod_doc(steps=only("checks", MOD_STEP.replace("        shell: bash\n", "        shell: bash\n        continue-on-error: true\n"))),
            "no checkout": mod_doc(checkout=False),
            "a step after the mod step": mod_doc(extra={"checks-macos": "      - run: echo\n"}),
            "scope lacks the mods output": mod_doc(scope_out=False),
        }
        for label, doc in defects.items():
            with self.subTest(defect=label):
                self.assertTrue(mods_problems(doc), label)

    def test_each_defect_names_its_job(self):
        for job in MOD_JOBS:
            with self.subTest(job=job):
                problems = mods_step_problems(mod_doc(steps=only(job, "")))
                self.assertEqual([p.split(":")[0] for p in problems], [job], problems)

    def test_the_checker_misreads_no_comment_or_block_scalar(self):
        # Rows: a comment that names the script is no step, and a `run: |` block that holds only the script line is
        # the step. Named failure: a commented-out step reads as present, or a block step as absent.
        commented = "      # run: bash .github/scripts/mod-tests.sh\n"
        self.assertTrue(mods_step_problems(mod_doc(steps=only("checks", commented))))
        block = MOD_STEP.replace(f"run: {MOD_CMD}\n", f"run: |\n          {MOD_CMD}\n")
        self.assertEqual(mods_step_problems(mod_doc(steps=only("checks", block))), [])
        trailing = mod_doc(extra={"checks": "      # find mods -name '*.test.mjs'\n"})
        self.assertEqual(mods_step_problems(trailing), [])  # a comment line is not a run

    def test_the_script_checker_sees_each_defect(self):
        self.assertEqual(script_problems(MOD_SCRIPT_TEXT), [])  # control: case patterns and || are no pipe
        defects = {
            "pipe": MOD_SCRIPT_TEXT.replace('node "$f" || fail=1', 'node "$f" | tail -1'),
            "or true": MOD_SCRIPT_TEXT.replace("|| fail=1", "|| true"),
            "or colon": MOD_SCRIPT_TEXT.replace("|| fail=1", "|| :"),
            "pipe after a case pattern line": MOD_SCRIPT_TEXT.replace("exit 2 ;;", "echo x | cat ;;"),
        }
        for label, text in defects.items():
            with self.subTest(defect=label):
                self.assertTrue(script_problems(text), label)
        commented = MOD_SCRIPT_TEXT + "# node a | tail -1 || true\n"
        self.assertEqual(script_problems(commented), [])  # a comment line is not code


# ---- every test file runs in a CI step. A test file that no run step names never fails a pull
# request, so its red stays invisible: lint/test_check_agent_models.py ran in no step. Failure
# classes: (a) product, a test file has no run line in checks.yml; (b) test, this parser misreads a
# run line (a comment, a quote, a block scalar); (c) stale, a test file was renamed or removed and
# its run line was not. Scope: test_*.py, test_*.sh and *.test.ps1 outside hidden folders.
# mutate_*.py is not a suite (mutate_shared.py is plumbing), and mods/*/*.test.mjs runs through
# .github/scripts/mod-tests.sh (the "Mod and map-skill tests" step of three jobs), so neither is listed here.
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
        with open(CHECKS, encoding="utf-8") as handle:
            commands = run_commands(handle.read())
        missing = [p for p in find_test_files(REPO) if not names_path(commands, p)]
        self.assertEqual(missing, [], "no run step in checks.yml names: " + ", ".join(missing))

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
