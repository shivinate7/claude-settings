#!/usr/bin/env python3
"""Cases for the repo typecheck hook: hooks/repo_typecheck.py, called from hooks/config_watch.py.

Run it from the repository root:

    python3 hooks/test_repo_typecheck.py

WHAT IT PROVES. After a Write, Edit or MultiEdit of a file that a repo's `.claude/layout-extras.json`
declares under "typecheck", the watch runs the declared command from the repo root and prints one
PostToolUse block on stdout. Every other case is silent. Each matching entry's command starts once per
matching edit, and the outputs of matching entries share one block.

HOW IT DRIVES THE CODE. Each case runs hooks/config_watch.py the way a hook runs it: a JSON payload on
stdin, the answer on stdout. The module is not called directly. On the old code a direct call to a
missing name fails before any behaviour runs, which is not a red for the named cause (test-practices
P3). The host exists on the old code, so each case fails there on its own assertion.

THE COST CASES run the host under a probe. The probe wraps subprocess.run and subprocess.Popen,
records every process start, and then runs the host as __main__, so the real command still runs.

FIXTURES. The project and its config folder come from hooks/test_config_watch.py (base.Project,
base.write, base.WATCH, base.SONNET, base.LIFT). Temp folders come from this run's folder in
lint/_test_temp.py.
"""

import importlib
import itertools
import json
import os
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lint"))
import _test_temp  # noqa: E402  test-temp-standard: every temp path comes from this run's folder
import test_config_watch as base  # noqa: E402  fixtures: Project, write, WATCH, SONNET, LIFT

RUN_FOLDER = _test_temp.run_folder()
REPO_SETTINGS = os.path.join(HERE, "..", "settings.json")
EXTRAS = os.path.join(".claude", "layout-extras.json")
FAIL_STUB = "tools/typecheck-stub.py"  # prints boom, its cwd and its argv, exits 1
OK_STUB = "tools/typecheck-stub-ok.py"  # prints boom, exits 0: the exit code decides, not the output
SILENT_STUB = "tools/typecheck-stub-silent.py"  # exits 1 with no output
SECOND_STUB = "tools/typecheck-stub-second.py"  # prints bang, exits 1: the second matching entry's output
SLOW_STUB = "tools/typecheck-stub-slow.py"  # sleeps SLOW_SECONDS, prints slow, exits 1
LONG_STUB = "tools/typecheck-stub-long.py"  # sleeps LONG_SECONDS, prints long, exits 1
BIG_STUB = "tools/typecheck-stub-big.py"  # prints BIG_SIZE characters, exits 1
TEST_BUDGET = 4.0  # the total budget the budget cases patch in, in seconds
SLOW_SECONDS = 1.0  # well under half of TEST_BUDGET, so a slow runner cannot flip the budget case
LONG_SECONDS = 3.5  # past what is left of TEST_BUDGET after one SLOW_SECONDS, so the budget runs out
SLACK = 0.25  # timing margin on the second command's timeout
BIG_SIZE = 100000  # characters the big stub prints
TAIL_ALLOWANCE = 200  # the short tail line a capped report may end with
STUBS = {
    FAIL_STUB: "import os, sys\nprint('boom')\nprint('cwd=' + os.getcwd())\n"
               "print('argv=' + repr(sys.argv[1:]))\nsys.exit(1)\n",
    OK_STUB: "print('boom')\n",
    SILENT_STUB: "import sys\nsys.exit(1)\n",
    SECOND_STUB: "import sys\nprint('bang')\nsys.exit(1)\n",
    SLOW_STUB: "import sys, time\ntime.sleep(%r)\nprint('slow')\nsys.exit(1)\n" % SLOW_SECONDS,
    LONG_STUB: "import sys, time\ntime.sleep(%r)\nprint('long')\nsys.exit(1)\n" % LONG_SECONDS,
    BIG_STUB: "import sys\nsys.stdout.write('x' * %d)\nsys.exit(1)\n" % BIG_SIZE,
}
STUB_PREFIX = "typecheck-stub"  # every stub's file name starts with this; the cost cases count starts that name it
POSIX = os.name != "nt"
_counter = itertools.count(1)

# Runs the host under a recorder. `mode` "run" lets each subprocess run; "timeout" makes subprocess.run
# raise TimeoutExpired at once, so a timeout case waits on no clock.
PROBE = r"""
import io, json, os, runpy, subprocess, sys
hook, payload, side, mode = sys.argv[1:5]
calls = []
real_run = subprocess.run
real_popen = subprocess.Popen


def argv_of(args):
    return [str(a) for a in args] if isinstance(args, (list, tuple)) else [str(args)]


class Recording(real_popen):
    def __init__(self, args, *rest, **kwargs):
        calls.append({"api": "Popen", "argv": argv_of(args)})
        super().__init__(args, *rest, **kwargs)


def recording_run(args, *rest, **kwargs):
    calls.append({"api": "run", "argv": argv_of(args), "timeout": kwargs.get("timeout")})
    if mode == "timeout":
        raise subprocess.TimeoutExpired(args, kwargs.get("timeout"))
    return real_run(args, *rest, **kwargs)


subprocess.Popen = Recording
subprocess.run = recording_run
sys.stdin = io.StringIO(payload)
if len(sys.argv) > 5 and sys.argv[5]:
    # Patch the total budget small, so a case can show the shared budget without a long wait.
    sys.path.insert(0, os.path.dirname(hook))
    import repo_typecheck
    if hasattr(repo_typecheck, "TOTAL_BUDGET"):
        repo_typecheck.TOTAL_BUDGET = float(sys.argv[5])
code = 0
try:
    runpy.run_path(hook, run_name="__main__")
except SystemExit as stop:
    code = stop.code if isinstance(stop.code, int) else (0 if stop.code is None else 1)
finally:
    with open(side, "w", encoding="utf-8") as handle:
        json.dump({"calls": calls, "exit": code, "guard_loaded": "guard" in sys.modules}, handle)
"""


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def run_host(repo, payload):
    done = subprocess.run([sys.executable, base.WATCH], input=json.dumps(payload),
                          capture_output=True, text=True, env=repo.project.env())
    return done.returncode, done.stdout, done.stderr


def run_raw(repo, text):
    done = subprocess.run([sys.executable, base.WATCH], input=text,
                          capture_output=True, text=True, env=repo.project.env())
    return done.returncode, done.stdout, done.stderr


def run_probe(repo, payload, mode="run", budget=None):
    side = os.path.join(RUN_FOLDER, "probe-%d.json" % next(_counter))
    argv = [sys.executable, "-c", PROBE, base.WATCH, json.dumps(payload), side, mode]
    if budget is not None:
        argv.append(str(budget))
    done = subprocess.run(argv, capture_output=True, text=True, env=repo.project.env())
    with open(side, encoding="utf-8") as handle:
        report = json.load(handle)
    return done.returncode, done.stdout, report


def one_object(stdout):
    """The one JSON object the host printed, or None when it printed nothing or more than one object."""
    try:
        data = json.loads(stdout)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def block_of(stdout):
    """The PostToolUse block the host printed, or None when there is no block."""
    data = one_object(stdout)
    return data if data is not None and data.get("decision") == "block" else None


def check_starts(report):
    """Each process start that runs a typecheck stub, once per start. Popen is the one place a start happens."""
    return [c for c in report["calls"] if c["api"] == "Popen"
            and any(os.path.basename(a).startswith(STUB_PREFIX) for a in c["argv"])]


def check_timeouts(report):
    """The timeout each typecheck stub was run with, one entry per subprocess.run call."""
    return [c["timeout"] for c in report["calls"] if c["api"] == "run"
            and any(os.path.basename(a).startswith(STUB_PREFIX) for a in c["argv"])]


def guard_log_lines(repo):
    """The lines of the guard.log in the case's own config folder, or [] when none was written."""
    path = os.path.join(repo.project.cfg, "guard.log")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return handle.read().splitlines()


def printed_cwd(reason):
    """The cwd the stub printed into a block reason, or None when the reason holds no cwd line."""
    for line in reason.splitlines():
        if line.startswith("cwd="):
            return line[len("cwd="):]
    return None


def ancestors(path):
    here = os.path.dirname(os.path.abspath(path))
    while True:
        yield here
        parent = os.path.dirname(here)
        if parent == here:
            return
        here = parent


def entry(command, globs=("app/**/*.ts", "app/**/*.tsx"), timeout=90):
    return {"globs": list(globs), "command": list(command), "timeout": timeout}


def fail_command(*extra):
    return [sys.executable, FAIL_STUB] + list(extra)


class Repo(object):
    """One project: the stub commands under tools/, and a layout-extras file that declare() writes."""

    def __init__(self, name):
        self.project = base.Project(os.path.join(RUN_FOLDER, name))
        self.root = self.project.proj
        self.extras = os.path.join(self.root, EXTRAS)
        self.folder = os.path.join(RUN_FOLDER, name)
        for rel, body in STUBS.items():
            base.write(os.path.join(self.root, rel), body)

    def abs(self, rel):
        return os.path.join(self.root, rel)

    def declare(self, *entries):
        self.declare_value(list(entries))

    def declare_value(self, value):
        base.write(self.extras, json.dumps({"kinds": {}, "typecheck": value}))

    def elsewhere(self):
        """A folder outside the repo that holds no extras file: a payload cwd that is not the repo."""
        path = os.path.join(self.folder, "elsewhere")
        os.makedirs(path, exist_ok=True)
        return path

    def payload(self, file_path, tool="Write", cwd=None):
        return {"tool_name": tool, "tool_input": {"file_path": file_path, "content": "x"},
                "cwd": cwd or self.root, "session_id": "case"}


class CaseName(unittest.TestCase):
    def name(self):
        return self.id().rsplit(".", 1)[-1]


class Trigger(CaseName):
    def test_write_to_a_matching_file_blocks_with_the_report(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command()))
        rc, out, err = run_host(repo, repo.payload(repo.abs("app/x.ts")))
        self.assertEqual(rc, 0, "the host exited %s on a block: %s" % (rc, err))
        block = block_of(out)
        self.assertIsNotNone(block, "a Write of app/x.ts with a failing typecheck printed no PostToolUse block")
        self.assertEqual(set(block), {"decision", "reason"}, "the block carries keys beyond decision and reason")
        self.assertIn("x.ts", block["reason"], "the block reason does not name the edited file")
        self.assertIn("boom", block["reason"], "the block reason does not hold the command's output")

    def test_edit_and_multiedit_block_too(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command()))
        for tool, rel in (("Edit", "app/x.tsx"), ("MultiEdit", "app/x.ts")):
            rc, out, err = run_host(repo, repo.payload(repo.abs(rel), tool=tool))
            self.assertIsNotNone(block_of(out), "the %s of %s printed no block" % (tool, rel))

    def test_a_relative_file_path_resolves_against_the_payload_cwd(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command()))
        rc, out, err = run_host(repo, repo.payload("app/x.ts", cwd=repo.root))
        self.assertIsNotNone(block_of(out), "a relative app/x.ts with the repo as cwd printed no block")

    def test_the_root_is_found_from_the_file_not_the_payload_cwd(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command()))
        elsewhere = repo.elsewhere()
        self.assertFalse(os.path.exists(os.path.join(elsewhere, EXTRAS)),
                         "fixture error: the payload cwd holds an extras file")
        rc, out, err = run_host(repo, repo.payload(repo.abs("app/x.ts"), cwd=elsewhere))
        self.assertIsNotNone(block_of(out), "an absolute file inside the repo, with another cwd, printed no block")

    def test_a_backslash_relative_path_matches_the_glob(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command()))
        rc, out, err = run_host(repo, repo.payload("app\\nested\\x.ts", cwd=repo.root))
        self.assertIsNotNone(block_of(out), "a relative app\\nested\\x.ts (backslash separators) printed no block")

    def test_zero_folders_and_deep_folders_both_match_the_double_star_glob(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command(), globs=("app/**/*.ts",)))
        for rel in ("app/x.ts", "app/a/b/c/x.ts"):
            rc, out, err = run_host(repo, repo.payload(repo.abs(rel)))
            self.assertIsNotNone(block_of(out), "%s did not match app/**/*.ts" % rel)

    def test_names_outside_the_globs_stay_silent(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command(), globs=("app/**/*.ts",)))
        rc, out, err = run_host(repo, repo.payload(repo.abs("app/x.ts")))
        self.assertIsNotNone(block_of(out), "app/x.ts did not match app/**/*.ts, so the silence below proves nothing")
        for rel in ("app/x.tsx", "src/x.ts"):
            rc, out, err = run_host(repo, repo.payload(repo.abs(rel)))
            self.assertEqual(out, "", "%s is outside app/**/*.ts but printed output" % rel)

    def test_a_file_outside_every_root_is_silent(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command()))
        rc, out, err = run_host(repo, repo.payload(repo.abs("app/x.ts")))
        self.assertIsNotNone(block_of(out), "a matching repo file printed no block, so the outside case proves nothing")
        target = os.path.join(repo.folder, "outside", "app", "x.ts")
        self.assertFalse(any(os.path.exists(os.path.join(d, EXTRAS)) for d in ancestors(target)),
                         "fixture error: an ancestor of the outside file holds an extras file")
        rc, out, err = run_host(repo, repo.payload(target))
        self.assertEqual(out, "", "a file outside every root printed output")

    def test_a_symlinked_root_is_found_through_its_link(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command()))
        link = os.path.join(repo.folder, "link")
        try:
            os.symlink(repo.root, link)
        except (OSError, NotImplementedError) as err:
            self.skipTest("this platform has no symlinks: %s" % err)
        rc, out, err = run_host(repo, repo.payload(os.path.join(link, "app", "x.ts")))
        self.assertIsNotNone(block_of(out), "a file reached through a symlinked root printed no block")

    def test_a_non_object_tool_input_is_silent(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command()))
        rc, out, err = run_host(repo, repo.payload(repo.abs("app/x.ts")))
        self.assertIsNotNone(block_of(out), "a valid payload printed no block, so the silence below proves nothing")
        payload = repo.payload(repo.abs("app/x.ts"))
        payload["tool_input"] = "app/x.ts"
        rc, out, err = run_host(repo, payload)
        self.assertEqual(out, "", "a tool_input that is not an object printed output")


class Command(CaseName):
    def test_the_command_runs_from_the_root_with_no_shell(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command("$(touch MARK)")))
        rc, out, err = run_host(repo, repo.payload(repo.abs("app/x.ts"), cwd=repo.elsewhere()))
        block = block_of(out)
        self.assertIsNotNone(block, "the command did not run for an absolute app/x.ts with another cwd")
        self.assertIn("argv=['$(touch MARK)']", block["reason"],
                      "the argument did not reach the command as literal text")
        cwd = printed_cwd(block["reason"])
        self.assertIsNotNone(cwd, "the block reason holds no cwd line")
        self.assertTrue(os.path.samefile(cwd, repo.root), "the command did not run from the repo root")
        self.assertFalse(os.path.exists(repo.abs("MARK")), "a shell expanded $(touch MARK): the command ran through a shell")

    @unittest.skipIf(not POSIX, "exec bits are POSIX")
    def test_a_relative_command_runs_from_the_root_not_the_payload_cwd(self):
        repo = Repo(self.name())
        runner = "tools/typecheck-stub-run"
        base.write(repo.abs(runner), "#!%s\n" % sys.executable + STUBS[FAIL_STUB])
        os.chmod(repo.abs(runner), 0o755)
        repo.declare(entry([runner]))
        rc, out, err = run_host(repo, repo.payload(repo.abs("app/x.ts"), cwd=repo.elsewhere()))
        block = block_of(out)
        self.assertIsNotNone(block, "a relative command did not resolve against the repo root")
        cwd = printed_cwd(block["reason"])
        self.assertIsNotNone(cwd, "the block reason holds no cwd line")
        self.assertTrue(os.path.samefile(cwd, repo.root), "the relative command ran from the payload cwd")

    def test_a_command_that_exits_zero_is_silent_even_with_output(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command()))
        rc, out, err = run_host(repo, repo.payload(repo.abs("app/x.ts")))
        self.assertIsNotNone(block_of(out), "a failing command printed no block, so the zero-exit case proves nothing")
        repo.declare(entry([sys.executable, OK_STUB]))
        rc, out, err = run_host(repo, repo.payload(repo.abs("app/x.ts")))
        self.assertEqual(out, "", "a command that exited 0 printed output")

    def test_empty_output_on_a_nonzero_exit_is_silent(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command()))
        rc, out, err = run_host(repo, repo.payload(repo.abs("app/x.ts")))
        self.assertIsNotNone(block_of(out), "a failing command printed no block, so the empty-output case proves nothing")
        repo.declare(entry([sys.executable, SILENT_STUB]))
        rc, out, err = run_host(repo, repo.payload(repo.abs("app/x.ts")))
        self.assertEqual(out, "", "a nonzero exit with no output printed text")

    def test_a_command_that_is_not_installed_is_silent(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command()))
        rc, out, err = run_host(repo, repo.payload(repo.abs("app/x.ts")))
        self.assertIsNotNone(block_of(out), "a failing command printed no block, so the missing-command case proves nothing")
        missing = ["app/node_modules/.bin/tsc", "-p", "app/tsconfig.json", "--noEmit"]
        self.assertFalse(os.path.exists(repo.abs(missing[0])), "fixture error: the compiler exists")
        repo.declare(entry(missing))
        rc, out, err = run_host(repo, repo.payload(repo.abs("app/x.ts")))
        self.assertEqual(out, "", "a command whose program is not installed printed output")

    @unittest.skipIf(not POSIX, "exec bits are POSIX")
    def test_a_command_that_cannot_start_is_silent(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command()))
        rc, out, err = run_host(repo, repo.payload(repo.abs("app/x.ts")))
        self.assertIsNotNone(block_of(out), "a failing command printed no block, so the cannot-start case proves nothing")
        self.assertFalse(os.access(repo.abs(FAIL_STUB), os.X_OK), "fixture error: the stub is executable")
        repo.declare(entry([FAIL_STUB]))
        rc, out, err = run_host(repo, repo.payload(repo.abs("app/x.ts")))
        self.assertEqual(out, "", "a command that cannot start printed output")

    def test_the_block_reason_is_capped(self):
        repo = Repo(self.name())
        repo.declare(entry([sys.executable, BIG_STUB]))
        rc, out, err = run_host(repo, repo.payload(repo.abs("app/x.ts")))
        block = block_of(out)
        self.assertIsNotNone(block, "a command printing 100 KB printed no block")
        self.assertIn("typecheck failed after editing x.ts", block["reason"],
                      "the capped reason lost the header that names the edited file")
        self.assertLess(len(block["reason"]), BIG_SIZE, "the block reason holds the whole 100 KB output")
        cap = getattr(importlib.import_module("repo_typecheck"), "REPORT_CAP", None)
        self.assertIsNotNone(cap, "repo_typecheck has no REPORT_CAP constant")
        self.assertLessEqual(len(block["reason"]), cap + TAIL_ALLOWANCE,
                             "the block reason is longer than REPORT_CAP plus a tail line")

    def test_two_matching_entries_share_one_total_budget(self):
        # Each command sleeps well under half the budget, so a slow runner cannot flip the case. A per-command
        # budget would give the second command the full TEST_BUDGET, not what is left after the first.
        repo = Repo(self.name())
        repo.declare(entry([sys.executable, SLOW_STUB], globs=("app/**/*.ts",)),
                     entry([sys.executable, SLOW_STUB], globs=("app/**/*.ts",)))
        rc, out, report = run_probe(repo, repo.payload(repo.abs("app/x.ts")), budget=TEST_BUDGET)
        self.assertEqual(len(check_starts(report)), 2, "two matching entries did not both start, so the budget proves nothing")
        timeouts = check_timeouts(report)
        self.assertEqual(len(timeouts), 2, "the commands did not run through subprocess.run, so their timeouts are unknown")
        self.assertLessEqual(timeouts[1], TEST_BUDGET - SLOW_SECONDS + SLACK,
                             "the second command got a fresh budget, not what was left of the total after the first")

    def test_a_spent_budget_stops_the_remaining_entries(self):
        repo = Repo(self.name())
        repo.declare(entry([sys.executable, SLOW_STUB], globs=("app/**/*.ts",)),
                     entry([sys.executable, LONG_STUB], globs=("app/**/*.ts",)),
                     entry([sys.executable, SLOW_STUB], globs=("app/**/*.ts",)))
        rc, out, report = run_probe(repo, repo.payload(repo.abs("app/x.ts")), budget=TEST_BUDGET)
        self.assertEqual(len(check_starts(report)), 2,
                         "an entry started after the budget was spent: the third command ran")

    def test_one_bad_entry_costs_only_itself(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command(), globs=("app/**/*.ts",)),
                     dict(entry(fail_command()), command="tsc"))
        rc, out, err = run_host(repo, repo.payload(repo.abs("app/x.ts")))
        block = block_of(out)
        self.assertIsNotNone(block, "a bad entry cost the good entry its report")
        self.assertIn("boom", block["reason"], "the good entry's output is not in the block")
        noted = [line for line in guard_log_lines(repo) if "typecheck" in line]
        self.assertEqual(len(noted), 1, "the bad entry did not write exactly one guard.log line naming typecheck")
        self.assertIn("\tnoted\t", noted[0], "the bad entry's guard.log line is not a noted line")

    def test_a_glob_that_does_not_compile_costs_only_its_entry(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command(), globs=("app/**/*.ts",)),
                     entry(fail_command(), globs=("app/[z-a].ts",)))
        rc, out, err = run_host(repo, repo.payload(repo.abs("app/x.ts")))
        block = block_of(out)
        self.assertIsNotNone(block, "a glob that does not compile cost the good entry its report")
        self.assertIn("boom", block["reason"], "the good entry's output is not in the block")
        noted = [line for line in guard_log_lines(repo) if "typecheck" in line]
        self.assertEqual(len(noted), 1, "the bad glob did not write exactly one guard.log line naming typecheck")
        self.assertIn("\tnoted\t", noted[0], "the bad glob's guard.log line is not a noted line")

    def test_a_timeout_is_silent(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command(), timeout=30))
        rc, out, report = run_probe(repo, repo.payload(repo.abs("app/x.ts")), mode="run")
        self.assertIsNotNone(block_of(out), "a failing command printed no block, so the timeout case proves nothing")
        rc, out, report = run_probe(repo, repo.payload(repo.abs("app/x.ts")), mode="timeout")
        self.assertEqual((rc, out), (0, ""), "a timed-out command printed output or failed the host")


class Silence(CaseName):
    def test_malformed_keys_are_silent_and_start_nothing(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command()))
        rc, out, report = run_probe(repo, repo.payload(repo.abs("app/x.ts")))
        self.assertIsNotNone(block_of(out), "a valid declaration printed no block, so the malformed cases prove nothing")
        cmd = [sys.executable, FAIL_STUB]
        bad = {
            "a string, not a list": "app/**/*.ts",
            "an entry that is not an object": ["not a dict"],
            "empty globs": [entry(cmd, globs=())],
            "an absolute glob": [entry(cmd, globs=("/abs/**/*.ts",))],
            "a glob with ..": [entry(cmd, globs=("../x/**/*.ts",))],
            "a glob that is not a string": [entry(cmd, globs=(1,))],
            "a command that is a string": [dict(entry(cmd), command="tsc")],
            "an empty command": [dict(entry(cmd), command=[])],
            "a command with non-string parts": [dict(entry(cmd), command=[1, 2])],
            "timeout 0": [entry(cmd, timeout=0)],
            "timeout that is a string": [entry(cmd, timeout="90")],
            "timeout below zero": [entry(cmd, timeout=-5)],
        }
        for label, value in bad.items():
            repo.declare_value(value)
            rc, out, report = run_probe(repo, repo.payload(repo.abs("app/x.ts")))
            self.assertEqual(out, "", "%s: the malformed key printed output" % label)
            self.assertEqual(check_starts(report), [], "%s: the malformed key started a process" % label)

    def test_an_empty_typecheck_list_is_silent_and_starts_nothing(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command()))
        rc, out, report = run_probe(repo, repo.payload(repo.abs("app/x.ts")))
        self.assertIsNotNone(block_of(out), "a valid declaration printed no block, so the empty-list case proves nothing")
        self.assertEqual(len(check_starts(report)), 1, "a valid declaration did not start exactly one process")
        repo.declare_value([])
        rc, out, report = run_probe(repo, repo.payload(repo.abs("app/x.ts")))
        self.assertEqual(out, "", "an empty typecheck list printed output")
        self.assertEqual(check_starts(report), [], "an empty typecheck list started a process")


class Cost(CaseName):
    def test_a_matching_edit_starts_exactly_one_process(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command()))
        rc, out, report = run_probe(repo, repo.payload(repo.abs("app/x.ts")))
        self.assertEqual(len(check_starts(report)), 1, "a matching edit did not start exactly one typecheck process")

    def test_only_the_entry_whose_globs_match_runs_once(self):
        repo = Repo(self.name())
        repo.declare(entry([sys.executable, OK_STUB], globs=("lib/**/*.ts",)),
                     entry(fail_command(), globs=("app/**/*.ts",)))
        rc, out, report = run_probe(repo, repo.payload(repo.abs("app/x.ts")))
        self.assertIsNotNone(block_of(out), "the matching entry printed no block")
        starts = check_starts(report)
        self.assertEqual(len(starts), 1, "two entries, one matching, did not start exactly one process")
        self.assertIn("typecheck-stub.py", [os.path.basename(a) for a in starts[0]["argv"]],
                      "the process that started is not the matching entry's command")

    def test_two_matching_entries_each_run_and_report_joined(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command(), globs=("app/**/*.ts",)),
                     entry([sys.executable, SECOND_STUB], globs=("app/**/*.tsx", "app/**/*.ts")))
        rc, out, report = run_probe(repo, repo.payload(repo.abs("app/x.ts")))
        block = block_of(out)
        self.assertIsNotNone(block, "two matching entries printed no single block")
        self.assertEqual(len(check_starts(report)), 2, "two matching entries did not start two processes")
        self.assertIn("boom", block["reason"], "the first matching entry's output is not in the block")
        self.assertIn("bang", block["reason"], "the second matching entry's output is not in the joined block")

    def test_the_declared_timeout_is_capped_at_ninety_seconds(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command(), timeout=500))
        rc, out, report = run_probe(repo, repo.payload(repo.abs("app/x.ts")))
        self.assertEqual(check_timeouts(report), [90], "the command ran with a timeout other than min(declared, 90)")
        repo.declare(entry(fail_command(), timeout=30))
        rc, out, report = run_probe(repo, repo.payload(repo.abs("app/x.ts")))
        self.assertEqual(check_timeouts(report), [30], "a declared timeout under 90 was not used as declared")

    def test_a_non_matching_edit_starts_no_process(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command(), globs=("app/**/*.ts",)))
        rc, out, report = run_probe(repo, repo.payload(repo.abs("app/x.ts")))
        self.assertEqual(len(check_starts(report)), 1, "the matching edit did not start the check, so the silence below proves nothing")
        rc, out, report = run_probe(repo, repo.payload(repo.abs("src/x.ts")))
        self.assertEqual(check_starts(report), [], "a non-matching edit started a typecheck process")
        self.assertEqual(out, "", "a non-matching edit printed output")

    def test_a_repo_without_the_key_starts_no_process(self):
        with_key = Repo(self.name() + "-with")
        with_key.declare(entry(fail_command()))
        rc, out, report = run_probe(with_key, with_key.payload(with_key.abs("app/x.ts")))
        self.assertEqual(len(check_starts(report)), 1, "the repo with the key did not start the check, so this case proves nothing")
        without = Repo(self.name() + "-without")
        self.assertFalse(os.path.exists(without.extras), "fixture error: the repo without the key has an extras file")
        rc, out, report = run_probe(without, without.payload(without.abs("app/x.ts")))
        self.assertEqual(check_starts(report), [], "a repo with no typecheck key started a process")
        self.assertEqual(out, "", "a repo with no typecheck key printed output")

    def test_only_write_edit_and_multiedit_trigger_the_check(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command()))
        rc, out, report = run_probe(repo, repo.payload(repo.abs("app/x.ts"), tool="Write"))
        self.assertIsNotNone(block_of(out), "a Write of app/x.ts printed no block, so the Bash case proves nothing")
        # The Bash payload carries the same file_path, so only the tool name differs.
        bash = {"tool_name": "Bash", "tool_input": {"command": "touch app/x.ts", "file_path": repo.abs("app/x.ts")},
                "cwd": repo.root, "session_id": "case"}
        rc, out, report = run_probe(repo, bash)
        self.assertEqual(out, "", "a Bash call printed a typecheck block")
        self.assertEqual(check_starts(report), [], "a Bash call started the typecheck command")

    def test_a_notebook_edit_does_not_trigger_the_check(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command()))
        rc, out, report = run_probe(repo, repo.payload(repo.abs("app/x.ts"), tool="Write"))
        self.assertIsNotNone(block_of(out), "a Write of app/x.ts printed no block, so the NotebookEdit case proves nothing")
        # The NotebookEdit payload names the same path under both keys, so only the tool name differs.
        notebook = {"tool_name": "NotebookEdit",
                    "tool_input": {"file_path": repo.abs("app/x.ts"), "notebook_path": repo.abs("app/x.ts"), "new_source": "x"},
                    "cwd": repo.root, "session_id": "case"}
        rc, out, report = run_probe(repo, notebook)
        self.assertEqual(out, "", "a NotebookEdit printed a typecheck block")
        self.assertEqual(check_starts(report), [], "a NotebookEdit started the typecheck command")


class Wiring(CaseName):
    def test_the_check_runs_before_the_fast_exit(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command()))
        base.write(repo.project.settings, base.SONNET)  # a recorded settings file, so the second run can take the fast exit
        payload = repo.payload(repo.abs("app/x.ts"))
        rc, out, err = run_host(repo, payload)
        self.assertIsNotNone(block_of(out), "the first edit printed no block")
        rc, out, report = run_probe(repo, payload)
        self.assertFalse(report["guard_loaded"], "the second edit did not take the fast exit, so this case proves nothing")
        self.assertIsNotNone(block_of(out), "the check was skipped on the fast-exit path")

    def test_a_block_and_the_cap_watch_message_share_one_stdout_object(self):
        repo = Repo(self.name())
        repo.declare(entry(fail_command()))
        base.write(repo.project.settings, base.SONNET)
        run_host(repo, repo.payload(repo.abs("notes.txt")))  # records the settings file as the baseline
        base.write(repo.project.settings, base.LIFT)  # an unasked lift, which the cap watch reverts
        rc, out, err = run_host(repo, repo.payload(repo.abs("app/x.ts")))
        data = one_object(out)
        self.assertIsNotNone(data, "the host printed no single JSON object")
        self.assertIn("systemMessage", data, "the cap watch printed no message, so the merge is not tested")
        self.assertIn("agent-model-cap", data["systemMessage"], "the message is not the cap watch's")
        self.assertEqual(data.get("decision"), "block", "the typecheck block is missing when the cap watch also speaks")

    def test_the_post_tool_use_config_watch_timeout_is_at_least_120(self):
        with open(REPO_SETTINGS, encoding="utf-8") as handle:
            settings = json.load(handle)
        entries = [h for group in settings["hooks"]["PostToolUse"] if "Write" in group.get("matcher", "")
                   for h in group.get("hooks", []) if "config_watch.py" in h.get("command", "")]
        self.assertTrue(entries, "settings.json has no config_watch entry on the Write matcher")
        for h in entries:
            self.assertGreaterEqual(h.get("timeout", 0), 120,
                                    "the config_watch PostToolUse entry times out before a typecheck run can finish")

    def test_control_unreadable_stdin_still_exits_zero_with_no_output(self):
        # Green on the old code. It proves the harness runs the host, so the reds above are the host's answers.
        repo = Repo(self.name())
        rc, out, err = run_raw(repo, "not json")
        self.assertEqual((rc, out), (0, ""), "unreadable stdin did not fail open")


if __name__ == "__main__":
    unittest.main(verbosity=2)
