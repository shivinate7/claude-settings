#!/usr/bin/env python3
"""Lane lint runs checks-guard's guard suite after the Playwright install that CI makes.

Run: python3 merge/test_lane_lint_guard_suite.py

The one install is actions/playwright-setup/install.sh, which the composite action and bin/ci-job both call. Lane lint never
downloads a browser. When the pinned browser is absent, the suite runs without the browser marker (GUARD_CHROMIUM), and one
printed line names the skipped page-item-design browser cases and says CI runs them.

The fixture is a throwaway repo. Its job has an earlier playwright-setup step and a suite with NODE_PATH and GUARD_CHROMIUM, as
checks-guard has. The install is a stand-in (Job.install_fixture in lint/test_ci_job.py, the one home of that fixture). The suite is
hooks/test_fixture.py, which writes seen.json: whether the install ran before it, whether NODE_PATH is a folder, and GUARD_CHROMIUM
as it reads it. No case runs npm, a browser download or apt, or reaches the network. The lane lint's read (merge.other_job_runs)
runs the real bin/ci-job (merge.CI_JOB).
"""
import contextlib
import io
import json
import os
import re
import shlex
import shutil
import sys
import tokenize
import unittest
import unittest.mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(os.path.dirname(HERE), "lint"))  # append: no lint module shadows one this suite imports
import test_ci_job as tcj  # noqa: E402  the one home of the ci-job fixture: Job, workflow and step
import merge  # noqa: E402
from workflow_steps import MISSING_INSTALL_LINE  # noqa: E402  the one reader of MISSING_INSTALL's text

REPO = os.path.abspath(os.path.join(HERE, ".."))
ACTION_YML = os.path.join(REPO, "actions", "playwright-setup", "action.yml")
CI_JOB_PY = os.path.join(REPO, "bin", "ci-job")
INSTALL = "Install the pinned Playwright and Chromium"
SUITE = "Guard fixture suite"
SUITE_RUN = "python3 hooks/test_fixture.py"
SUITE_PATH = "hooks/test_fixture.py"
NODE_PATH = "${{ github.workspace }}/.github/shoot/node_modules"
SUITE_TEXT = '''import json, os, sys
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
seen = {"install_ran": os.path.exists(os.path.join(root, "install-calls.txt")),
        "node_path_is_dir": os.path.isdir(os.environ.get("NODE_PATH", "")),
        "chromium": os.environ.get("GUARD_CHROMIUM")}
with open(os.path.join(root, "seen.json"), "w", encoding="utf-8") as f:
    json.dump(seen, f)
sys.exit(1 if os.path.exists(os.path.join(root, "suite-fails")) else 0)
'''


def install_step(uses="./actions/playwright-setup", **with_keys):
    """checks-guard's install step, as a fixture job writes it: the playwright-setup action with its with: keys."""
    return tcj.step(INSTALL, uses=uses, **{"with": {"package-dir": ".github/shoot", **with_keys}})


def suite_step():
    """checks-guard's suite step: NODE_PATH from the workspace, and the browser marker."""
    return tcj.step(SUITE, SUITE_RUN, env={"NODE_PATH": NODE_PATH, "GUARD_CHROMIUM": '"1"'})


def verdict_line(lines, name):
    """The verdict line of the step `name`, or None."""
    return next((ln for ln in lines if ("%s: " % name) in ln), None)


def state_of(line):
    return line.split()[0] if line else None


FIXTURE_NPM = {  # what an npm install makes for the fixture: playwright and playwright-core, whose chromium is browser/chrome in the repo
    "playwright-core/package.json": '{"name": "playwright-core", "version": "1.55.0", "main": "index.js"}\n',
    "playwright-core/index.js": "module.exports = {chromium: {executablePath: () => require('path').join(__dirname, '../../../../browser/chrome')}};\n",
    "playwright-core/cli.js": "// fixture: no case runs the pinned CLI\n",
    "playwright/package.json": '{"name": "playwright", "version": "1.55.0", "main": "index.js"}\n',
    "playwright/index.js": "module.exports = require('playwright-core');\n",
}


class Fixture(tcj.Job):
    """A throwaway repo with the suite file, and the install stand-in that install_fixture writes."""

    def setUp(self):
        super().setUp()
        path = os.path.join(self.root, "hooks", "test_fixture.py")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(SUITE_TEXT)

    def install_fixture(self, ok=True, browser=False):
        """Write the stand-in for actions/playwright-setup/install.sh into the repo. Each call is recorded in install-calls.txt. A
        phase other than `local` also records an apt call (apt-calls.txt), so a case reads an apt run as a failure. The stand-in
        makes the folder an npm install makes (.github/shoot/node_modules, from FIXTURE_NPM), and the pinned browser's file only when
        `browser`. With `ok` False it exits 1 first. It runs no npm, no browser download and no apt."""
        def under(*parts):
            return shlex.quote(self.path(*parts))
        for rel, text in FIXTURE_NPM.items():
            path = self.path("fixture-npm", "node_modules", rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        body = ['echo "$*" >> %s' % under("install-calls.txt"),
                'case "$1" in local) ;; *) echo "apt-get install -y fixture" >> %s ;; esac' % under("apt-calls.txt")]
        if not ok:
            body += ['echo "npm ci: fixture install failed" >&2', "exit 1"]
        body += ["mkdir -p %s" % under(".github", "shoot", "node_modules"),
                 "cp -R %s/. %s" % (under("fixture-npm", "node_modules"), under(".github", "shoot", "node_modules"))]
        if browser:
            body += ["mkdir -p %s" % under("browser"), ": > %s" % under("browser", "chrome")]
        folder = self.path("actions", "playwright-setup")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "install.sh"), "w", encoding="utf-8", newline="\n") as f:
            f.write("#!/bin/sh\n" + "\n".join(body) + "\n")
        os.chmod(os.path.join(folder, "install.sh"), 0o755)

    def path(self, *parts):
        return os.path.join(self.root, *parts)

    def install_ran(self):
        return os.path.exists(self.path("install-calls.txt"))

    def apt_ran(self):
        return os.path.exists(self.path("apt-calls.txt"))

    def seen(self):
        """What the suite recorded when it ran, or None when it did not run."""
        if not os.path.exists(self.path("seen.json")):
            return None
        with open(self.path("seen.json"), encoding="utf-8") as f:
            return json.load(f)


class SuiteAfterInstall(Fixture):
    """ci-job --step on checks-guard's suite step, in a job whose earlier step is the playwright-setup install."""

    def run_suite(self, *steps):
        """ci-job runs the named suite step of the fixture job. -> (rc, lines, out)."""
        return self.run_job(*steps, args=("--step", SUITE))

    def check_pass_after_install(self, uses):
        self.install_fixture()
        rc, lines, out = self.run_suite(install_step(uses=uses), suite_step())
        self.assertTrue(self.install_ran(), "the playwright-setup step did not run before the suite: " + out)
        self.assertEqual(state_of(verdict_line(lines, SUITE)), "PASS", "the suite does not read PASS after the install: " + out)
        self.assertEqual(rc, 0, out)
        seen = self.seen() or {}
        self.assertTrue(seen.get("install_ran") and seen.get("node_path_is_dir"),
                        "the suite did not find the install's NODE_PATH folder: %r" % seen)

    def test_the_install_runs_before_the_suite_and_the_suite_reads_pass(self):
        self.check_pass_after_install("./actions/playwright-setup")

    def test_the_install_named_with_the_workflow_form_of_the_action_also_runs_before_the_suite(self):
        self.check_pass_after_install("$/actions/playwright-setup")

    def test_the_suite_reads_fail_and_not_unknown_when_it_fails_after_the_install(self):
        self.install_fixture()
        with open(self.path("suite-fails"), "w", encoding="utf-8"):
            pass
        rc, lines, out = self.run_suite(install_step(), suite_step())
        self.assertTrue(self.install_ran(), "the playwright-setup step did not run before the suite: " + out)
        self.assertEqual(state_of(verdict_line(lines, SUITE)), "FAIL", "a failing suite does not read FAIL: " + out)
        self.assertEqual(rc, 1, out)

    def test_with_the_pinned_browser_absent_the_suite_runs_without_the_marker_and_one_line_names_the_skipped_cases(self):
        self.install_fixture(browser=False)
        rc, lines, out = self.run_suite(install_step(), suite_step())
        self.assertTrue(self.install_ran(), "the playwright-setup step did not run before the suite: " + out)
        self.assertEqual(state_of(verdict_line(lines, SUITE)), "PASS", "the suite does not read PASS without the browser: " + out)
        self.assertEqual((self.seen() or {}).get("chromium", "not run"), None,
                         "the suite still reads GUARD_CHROMIUM with the browser absent: %r" % (self.seen(),))
        skipped = [ln for ln in out.splitlines() if "page-item-design" in ln]
        self.assertEqual(len(skipped), 1, "want exactly one line that names the skipped page-item-design browser cases, found %d: %s"
                         % (len(skipped), out))
        self.assertRegex(skipped[0], r"\bCI\b", "the skipped-cases line does not say CI runs them: " + skipped[0])

    def test_with_the_pinned_browser_present_the_marker_stays_set(self):
        self.install_fixture(browser=True)
        rc, lines, out = self.run_suite(install_step(), suite_step())
        self.assertTrue(self.install_ran(), "the playwright-setup step did not run before the suite: " + out)
        self.assertEqual(state_of(verdict_line(lines, SUITE)), "PASS", "the suite does not read PASS with the browser: " + out)
        self.assertEqual((self.seen() or {}).get("chromium"), "1", "the suite does not read GUARD_CHROMIUM=1 with the browser present")

    def test_a_failed_install_reads_unknown_naming_the_install_and_the_suite_does_not_run(self):
        self.install_fixture(ok=False)
        rc, lines, out = self.run_suite(install_step(), suite_step())
        self.assertTrue(self.install_ran(), "the install did not run, so its failure is not shown: " + out)
        line = verdict_line(lines, SUITE)
        self.assertEqual(state_of(line), "unknown", "the suite does not read unknown after a failed install: " + out)
        self.assertIsNone(MISSING_INSTALL_LINE.search(line), "the unknown line is the MISSING_INSTALL text, which lane lint reads as not run: " + line)
        self.assertIn("install", line.lower(), "the unknown line does not name the install: " + line)
        self.assertIsNone(self.seen(), "the suite ran after a failed install: " + out)
        self.assertEqual(rc, 2, out)

    def test_a_system_deps_input_reads_unknown_naming_it_and_runs_no_apt(self):
        self.install_fixture()
        rc, lines, out = self.run_suite(install_step(**{"system-deps": "webkit"}), suite_step())
        line = verdict_line(lines, SUITE)
        self.assertEqual(state_of(line), "unknown", "the suite does not read unknown with system-deps set: " + out)
        self.assertIn("system-deps", line, "the unknown line does not name the system-deps input: " + line)
        self.assertFalse(self.apt_ran(), "apt ran in the lane lint: " + out)
        self.assertEqual(rc, 2, out)

    def test_control_a_suite_with_no_install_step_reads_the_missing_install_unknown_and_exits_two(self):
        rc, lines, out = self.run_suite(suite_step())
        self.assertEqual(rc, 2, out)
        unknown = [ln for ln in lines if ln.startswith("unknown")]
        self.assertEqual(len(unknown), 1, out)
        self.assertIsNotNone(MISSING_INSTALL_LINE.search(unknown[0]), "the unknown line is not the missing NODE_PATH install: " + out)
        self.assertIsNone(self.seen(), "the suite ran with no install in its job: " + out)


class LaneLintReadsSuite(Fixture):
    """merge's other_job_runs, the lane lint's read of a picked suite in another job, through the real bin/ci-job."""

    def lane_lint_read(self, *steps):
        """Write the job's workflow where other_job_runs reads it, then run it for the job's picked suite.
        -> (the result list of (job, suites, CiRun), the lines the read printed)."""
        folder = os.path.join(self.root, ".github", "workflows")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "checks.yml"), "w", encoding="utf-8", newline="\n") as f:
            f.write(tcj.workflow(*steps, job="lane"))
        printed = io.StringIO()
        with unittest.mock.patch.dict(os.environ, {"VERDICT_LOG": self.path("verdict.log")}), contextlib.redirect_stdout(printed):
            result = merge.other_job_runs(self.root, [("lane", [SUITE_PATH])], "main")
        return result, printed.getvalue()

    def test_a_failed_install_reads_unknown_through_the_lane_lint_and_never_as_not_run(self):
        self.install_fixture(ok=False)
        result, printed = self.lane_lint_read(install_step(), suite_step())
        self.assertTrue(self.install_ran(), "the install did not run in the lane lint's read: " + printed)
        notes = [ln for ln in printed.splitlines() if ln.startswith("not run")]
        self.assertEqual(notes, [], "a failed install reads as a not-run line: " + printed)
        self.assertEqual([(job, run.state) for job, _, run in result], [("lane", "unknown")], "the lane lint's read: %r" % (result,))

    def test_control_a_suite_with_no_install_step_is_one_not_run_line_through_the_lane_lint(self):
        result, printed = self.lane_lint_read(suite_step())
        notes = [ln for ln in printed.splitlines() if ln.startswith("not run")]
        self.assertEqual(len(notes), 1, "want one not-run line for a suite with no install step, got %d: %s" % (len(notes), printed))
        self.assertIn("lane", notes[0], "the not-run line does not name the job: " + notes[0])
        self.assertEqual(result, [], "the not-run suite left a run in the lane lint's result: %r" % (result,))


def code_of(lines):
    """The shell code of one run:'s lines, with comments removed. A `#` opens a comment only outside quotes, after a space or at
    a line's start. A quote stays open across lines, as a shell string does, so a comment opener inside a multi-line string is code."""
    kept, quote = [], None
    for ln in lines:
        out = []
        for j, ch in enumerate(ln):
            if quote:
                if ch == quote:
                    quote = None
            elif ch in "\"'":
                quote = ch
            elif ch == "#" and (j == 0 or ln[j - 1] in " \t"):
                break
            out.append(ch)
        kept.append("".join(out))
    return "\n".join(kept)


def run_code(text):
    """The code of each `run:` in a YAML file, one string per run. A block run's body is the lines indented past its key."""
    lines, blocks, i = text.split("\n"), [], 0
    while i < len(lines):
        m = re.match(r"^(\s*)run:[ \t]*(.*?)[ \t]*$", lines[i])
        i += 1
        if not m:
            continue
        indent, head = len(m.group(1)), m.group(2)
        body = [] if not head or head.startswith(("|", ">")) else [head]
        while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip(" ")) > indent):
            body.append(lines[i])
            i += 1
        blocks.append(code_of(body))
    return blocks


def code_literals(text):
    """The string literals of a Python file's code, from its tokenizer: a comment is no literal, and a `#` inside a string is text."""
    fstring_middle = getattr(tokenize, "FSTRING_MIDDLE", -1)  # an f-string's text is its own token from Python 3.12
    found = [tok.string for tok in tokenize.tokenize(io.BytesIO(text.encode("utf-8")).readline)
             if tok.type in (tokenize.STRING, fstring_middle)]
    return "\n".join(found)


class Delegation(unittest.TestCase):
    """The composite action and bin/ci-job both call the one install script, and the action runs no install of its own."""

    def read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_the_action_and_ci_job_both_call_install_sh(self):
        action = "\n".join(run_code(self.read(ACTION_YML)))
        self.assertRegex(action, r"install\.sh\"?\s+deps\b", "the action has no deps-phase call of install.sh")
        self.assertRegex(action, r"install\.sh\"?\s+browsers\b", "the action has no browsers-phase call of install.sh")
        literals = code_literals(self.read(CI_JOB_PY))
        self.assertIn("install.sh", literals, "bin/ci-job's code does not name install.sh")
        self.assertIn("playwright-setup", literals, "bin/ci-job's code does not name the playwright-setup folder")

    def test_action_yml_holds_no_npm_ci_or_install_browsers_command_of_its_own(self):
        action = "\n".join(run_code(self.read(ACTION_YML)))
        self.assertNotRegex(action, r"\bnpm\s+ci\b", "action.yml runs npm ci itself")
        self.assertNotRegex(action, r"\binstall\s+\$\{?BROWSERS\b", "action.yml runs `install $BROWSERS` itself")


class Scanners(unittest.TestCase):
    """The two readers above: a run's code and a Python file's literals, on the cases that break a line scanner."""

    def test_a_comment_opener_inside_a_string_hides_no_command_on_its_line(self):
        self.assertIn("npm ci", code_of(['echo "# x" && npm ci']))

    def test_a_lone_quote_in_plain_text_hides_no_command_after_it(self):
        self.assertIn("npm ci", code_of(["echo don't; npm ci"]))

    def test_a_comment_opener_inside_a_multi_line_string_is_text(self):
        self.assertIn("npm ci", code_of(['echo "first', '# still the string" && npm ci']))

    def test_a_comment_line_names_no_command(self):
        self.assertNotIn("npm ci", code_of(["# npm ci is not run here"]))

    def test_a_trailing_comment_names_no_command(self):
        self.assertNotIn("npm ci", code_of(["echo ok  # npm ci later"]))

    def test_run_code_reads_a_block_run_and_a_one_line_run_and_drops_their_comments(self):
        yml = ("    - name: a\n      run: |\n        npm ci --x\n        # npm ci is a comment\n      shell: bash\n"
               "    - name: b\n      run: echo hi # npm ci\n")
        blocks = run_code(yml)
        self.assertEqual(len(blocks), 2, blocks)
        self.assertEqual(blocks[0].count("npm ci"), 1, blocks[0])
        self.assertNotIn("npm ci", blocks[1], blocks[1])

    def test_a_python_comment_is_no_literal(self):
        self.assertNotIn("install.sh", code_literals("x = 1  # install.sh\n"))

    def test_a_hash_inside_a_python_string_is_a_literal(self):
        self.assertIn("install.sh", code_literals('x = "a # install.sh"\n'))

    def test_a_python_multi_line_string_with_a_hash_line_is_a_literal(self):
        self.assertIn("install.sh", code_literals('x = """\n# install.sh\n"""\n'))


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        shutil.rmtree(tcj.RUN_FOLDER, ignore_errors=True)
