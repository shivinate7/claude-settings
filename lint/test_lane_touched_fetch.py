#!/usr/bin/env python3
"""Pins for the lane-touched-tests workflow: its fetch (R62, step ci-linux-windows-once) and its macOS leg.

touched-tests.py reads one diff: BASE_SHA...HEAD. A lane checkout therefore fetches a small depth, not the full history.
Every checkout in the lane workflow must fetch a depth from 1 to MAX_DEPTH. A depth of 0 is the full history, and it is
refused here so the lane checkout stays shallow.

The reach-the-merge-base step builds the credential as a base64 header. GitHub masks the token itself, not its base64
form, so the step must mask that form with ::add-mask:: before the fetch argv uses it. LANE_YML names another copy of the
workflow for a green control; it defaults to the workflow in this repo.

The macOS leg runs only the macOS test files a draft PR touches. The cases read the workflow's steps with
lint/workflow_steps.py and run the script text of the `legs` step and of the run steps, with the selector's own output
writer (.github/scripts/touched-tests.py, write_outputs) as the fixture. No case matches the workflow's words.

The run job's whole `if:`, each job's and step's `continue-on-error`, and the Windows `*.test.ps1)` arm are pinned too. Each of
those cases also runs its check on an in-memory mutant of the workflow text, so the check is shown to catch its defect.

    python3 lint/test_lane_touched_fetch.py
"""
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LANE = os.environ.get("LANE_YML") or os.path.join(ROOT, ".github", "workflows", "lane-touched-tests.yml")
SELECTOR = os.path.join(ROOT, ".github", "scripts", "touched-tests.py")
MAX_DEPTH = 50  # the largest fetch-depth that still counts as shallow; a checkout fetching more than this fails the depth case
MASK = "::add-mask::"
MASKED_VARIABLE = re.compile(r"::add-mask::\$\{?\w")
USE_IN_ARGV = re.compile(r"extraheader=\$\{?auth")  # the fetch argv carries the credential as the git header
HANG_GUARD = 120  # seconds; a run here ends in a few seconds, so the guard is never the verdict

sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "testing"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
import tracked_tree  # noqa: E402  test-temp-standard: teardown removes the run folder (testing/tracked_tree.py)
from workflow_steps import disables, drop_comment, job_block, run_body, step_blocks, step_env, step_key  # noqa: E402  the one home of the step parser

RUN_FOLDER = None  # set by setUpModule

# Fixtures: the selector's lists. The full-size lists reach the largest matrix a PR could give (P8); the empty lists the smallest.
WIN_ONE = ["lint/test_win_00.py"]
WIN_FULL = ["lint/test_win_%02d.py" % i for i in range(40)]
MAC_ONE = ["lint/test_mac_00.py"]
MAC_FULL = ["lint/test_mac_%02d.py" % i for i in range(40)]
WIN_CMD = "python"  # the interpreter a Windows test runs under, in the selector's map
MAC_CMD = "python3"  # the interpreter a macOS test runs under, in the selector's map

COMMANDS_MACOS = "${{needs.touched.outputs.commands_macos}}"  # squashed: a step env value reads the macOS command map
COMMANDS_WINDOWS = "${{needs.touched.outputs.commands_windows}}"
MATRIX_FILES = "${{matrix.files}}"
MACOS_STEP = "Run the touched macOS tests"
WINDOWS_STEP = "Run the touched tests"
# Each gated run step's whole `if:` value, squashed. Whole, so `!(runner.os == 'macOS')` or a leading `!` is a different value.
IF_VALUES = {
    WINDOWS_STEP: "runner.os=='Windows'",
    MACOS_STEP: "runner.os=='macOS'",
    "Run the touched PowerShell tests": "!cancelled()&&runner.os=='Windows'",
}
# The lines of the two run steps that are meant to differ, stripped. The Windows step keeps the PowerShell arm and its comment;
# the macOS step must not have them, and RunBodies pins that.
PS1_ARM = '*.test.ps1) if [ "$RUNNER_OS" = Windows ]; then return 77; fi; echo "no PowerShell step on $RUNNER_OS"; return 1 ;;'
MEANT_TO_DIFFER = ("# 77 is a skip: on Windows the PowerShell step below runs it.", PS1_ARM)
# The run job's whole `if:`, squashed. A literal false or a negation of it skips every leg, and no test goes red.
RUN_JOB_IF = "github.event.pull_request.draft&&needs.touched.outputs.any=='true'"


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    if RUN_FOLDER and os.path.isdir(RUN_FOLDER):
        tracked_tree.rm_tree(RUN_FOLDER)  # test-temp-standard: teardown removes the run folder


def fresh_dir():
    return tempfile.mkdtemp(dir=RUN_FOLDER)


def live_lines(text):
    """The workflow's lines without comment-only lines, so a comment that names the mask does not count as the mask."""
    return [line for line in text.splitlines() if not line.lstrip().startswith("#")]


def mask_problem(text):
    """None when the credential is masked before the fetch argv uses it, else the one cause."""
    lines = live_lines(text)
    use = next((i for i, line in enumerate(lines) if USE_IN_ARGV.search(line)), None)
    if use is None:
        return "the lane workflow has no fetch argv that carries the credential header"
    mask = next((i for i, line in enumerate(lines) if MASK in line), None)
    if mask is None:
        return "the base64 credential is not masked: no ::add-mask:: line, so a log can print it"
    if mask > use:
        return "the base64 credential is masked after the fetch argv already uses it"
    if not MASKED_VARIABLE.search(lines[mask]):
        return "the ::add-mask:: line does not mask a shell variable that holds the credential"
    return None


GOOD = ('      - name: Reach the merge base\n'
        '        run: |\n'
        '          auth="AUTHORIZATION: basic $(printf \'x-access-token:%s\' "$GH_TOKEN" | base64 -w0)"\n'
        '          echo "::add-mask::$auth"\n'
        '          fetch() { git -c "http.https://github.com/.extraheader=$auth" fetch "$@"; }\n')


def read_lane():
    with open(LANE, encoding="utf-8") as f:
        return f.read()


def squash(value):
    """A value with its white space removed, so `${{ x }}` and `${{x}}` read alike."""
    return re.sub(r"\s+", "", value or "")


def job_outputs(block):
    """{name: raw value} of a job's `outputs:` map: the 6-space keys under its 4-space `outputs:` line. A comment is no key."""
    found, inside = {}, False
    for line in (block or "").split("\n"):
        if re.match(r"^    outputs:[ \t]*$", line):
            inside = True
        elif inside and (m := re.match(r"^      ([\w-]+):[ \t]*(.*?)[ \t]*$", line)):
            found[m.group(1)] = drop_comment(m.group(2))
        elif inside and line.strip() and not line.startswith("      "):
            inside = False
    return found


def read_outputs(path):
    """{name: value} from a GITHUB_OUTPUT file: `name=value` lines and `name<<DELIM` blocks, as Actions reads them."""
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    found, i = {}, 0
    while i < len(lines):
        block = re.match(r"^([\w-]+)<<(.+)$", lines[i])
        if block:
            body = []
            i += 1
            while i < len(lines) and lines[i] != block.group(2):
                body.append(lines[i])
                i += 1
            found[block.group(1)] = "\n".join(body)
        elif "=" in lines[i]:
            key, value = lines[i].split("=", 1)
            found[key] = value
        i += 1
    return found


def selector_outputs(windows, macos):
    """The selector's GITHUB_OUTPUT values for these lists, written by the selector's own write_outputs."""
    spec = importlib.util.spec_from_file_location("touched_tests", SELECTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cmds = {"windows": {f: WIN_CMD for f in windows}, "macos": {f: MAC_CMD for f in macos}}
    out = os.path.join(fresh_dir(), "select-output.txt")
    with mock.patch.dict(os.environ, {"GITHUB_OUTPUT": out}):
        module.write_outputs(list(windows), list(macos), cmds)
    return read_outputs(out)


def entries_of(matrix_text):
    """The `include` list of a matrix output, or None when the output is absent."""
    if matrix_text is None:
        return None
    return json.loads(matrix_text)["include"]


def with_this_python(script):
    """The script with its `python -c` run by this interpreter, so the case needs no `python` on PATH."""
    return re.sub(r"(?<![\w./-])python3?(?=\s+-c\b)", lambda _: shlex.quote(sys.executable), script)


def legs_run(matrix_text):
    """(exit code, stderr, outputs) of the `legs` step, run from the parsed workflow with MATRIX set to `matrix_text`."""
    step = next((s for s in step_blocks(job_block(read_lane(), "touched")) if step_key(s, "id") == "legs"), None)
    out = os.path.join(fresh_dir(), "legs-output.txt")
    open(out, "w", encoding="utf-8").close()
    env = dict(os.environ)
    env.update(MATRIX=matrix_text, GITHUB_OUTPUT=out)
    if step is None:
        return None, "the touched job has no step with id legs", {}
    proc = subprocess.run(["bash", "-c", with_this_python(run_body(step))], env=env, capture_output=True, text=True,
                          timeout=HANG_GUARD)
    return proc.returncode, proc.stderr.strip(), read_outputs(out)


def resolve(value, sel, entry, outputs):
    """A step env value as the run would give it: `needs.touched.outputs`, `steps.select.outputs` and `matrix` expressions
    read from the fixtures. Any other text is its own value, so it cannot match a pin by accident."""
    m = re.fullmatch(r"\$\{\{\s*([\w.-]+)\s*\}\}", (value or "").strip())
    if not m:
        return value
    path = m.group(1)
    if path.startswith("needs.touched.outputs."):
        return resolve(outputs.get(path[len("needs.touched.outputs."):], ""), sel, entry, outputs)
    if path.startswith("steps.select.outputs."):
        return sel.get(path[len("steps.select.outputs."):], "")
    if path.startswith("matrix."):
        return entry.get(path[len("matrix."):], "")
    return value


def has_value(step, want):
    """True when one of the step's own env values squashes to `want`."""
    return any(squash(v) == want for v in step_env(step).values())


def run_steps():
    return step_blocks(job_block(read_lane(), "run"))


def run_step(step, env_values, runner_os):
    """(process, recorded lines) of one run step's script, with `python` and `python3` as recording stubs. Each recorded
    line is `<interpreter> <file>`, so a run shows which interpreter ran which file."""
    folder = fresh_dir()
    bindir = os.path.join(folder, "stubs")
    os.makedirs(bindir)
    for name in ("python", "python3"):
        path = os.path.join(bindir, name)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write('#!/bin/sh\nprintf \'%s %s\\n\' "$(basename "$0")" "$*" >> "$RECORD_FILE"\n')
        os.chmod(path, 0o755)
    record = os.path.join(folder, "record.txt")
    env = dict(os.environ)
    env.update(env_values)
    env.update(RUNNER_OS=runner_os, RECORD_FILE=record, PATH=bindir + os.pathsep + os.environ.get("PATH", ""))
    proc = subprocess.run(["bash", "-c", with_this_python(run_body(step))], env=env, cwd=folder, capture_output=True,
                          text=True, timeout=HANG_GUARD)
    recorded = []
    if os.path.isfile(record):
        with open(record, encoding="utf-8") as f:
            recorded = f.read().splitlines()
    return proc, recorded


def named_run_step(text, name):
    """The run job's step with this `name:` in the workflow text, or None."""
    return next((s for s in step_blocks(job_block(text, "run")) if step_key(s, "name") == name), None)


def gate_problem(what, raw, want):
    """None when the `if:` value `raw` is `${{ want }}` whole, else the one cause for `what`. `want` is squashed."""
    expr = re.fullmatch(r"\$\{\{(.*)\}\}", drop_comment(raw or "").strip())
    if expr is None:
        return "%s has no ${{ }} if: value" % what
    if squash(expr.group(1)) != want:
        return "%s gates on %r, want %r" % (what, squash(expr.group(1)), want)
    return None


def if_problem(step, want):
    """None when the step's whole `if:` is `${{ want }}`, else the one cause. `want` is squashed."""
    return gate_problem("the step %r" % step_key(step, "name"), step_key(step, "if"), want)


def run_job_if_problem(text):
    """None when the run job's whole `if:` is RUN_JOB_IF, else the one cause."""
    m = re.search(r"^    if:(.*)$", job_block(text, "run") or "", re.M)
    return gate_problem("the run job", m.group(1) if m else None, RUN_JOB_IF)


def body_lines(body):
    """The stripped lines of a run body, without blank lines and without the lines meant to differ."""
    return [ln for ln in (raw.strip() for raw in (body or "").split("\n")) if ln and ln not in MEANT_TO_DIFFER]


def code_lines(body):
    """Each line of a shell body with its quoted text masked and its comment cut. A `#` opens a comment only outside quotes and
    at a word's start. A quote opened on one line runs on into the next, as the shell's does, so a multi-line string is masked."""
    out, quote = [], ""
    for line in body.split("\n"):
        code, i = [], 0
        while i < len(line):
            ch = line[i]
            if quote == "'":
                quote = "" if ch == "'" else quote
                code.append("_")
            elif quote == '"':
                if ch == "\\":
                    code.append("__")
                    i += 2
                    continue
                quote = "" if ch == '"' else quote
                code.append("_")
            elif ch == "\\":
                code.append("__")
                i += 2
                continue
            elif ch in "'\"":
                quote = ch
                code.append("_")
            elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
                break
            else:
                code.append(ch)
            i += 1
        out.append("".join(code))
    return out


def ps1_arms(body):
    """The code lines of a run body that hold a `*.test.ps1)` case arm. Unanchored, as an arm may follow a `;;` on its line;
    quoted and commented text is masked first, so a string or a comment that names one is no arm."""
    return [ln for ln in code_lines(body) if re.search(r"\*\.test\.ps1\s*\)", ln)]


def mutate_block(text, block, old, new):
    """`text` with `old` replaced once inside `block`, the raw text of one step or job that `text` holds once. In memory:
    the workflow file is read, never written. A stale `old` raises, so no case passes on a mutant that did not apply."""
    if text.count(block) != 1 or block.count(old) != 1:
        raise AssertionError("the mutant's text is not in the workflow once: %r" % old)
    return text.replace(block, block.replace(old, new, 1), 1)


def windows_arm_problem(text):
    """None when the Windows run step keeps its `*.test.ps1)` arm, else the one cause."""
    step = named_run_step(text, WINDOWS_STEP)
    if step is None:
        return "no run step is named %r" % WINDOWS_STEP
    if not ps1_arms(run_body(step) or ""):
        return "the Windows run step has no `*.test.ps1)` arm, so a PowerShell file fails there instead of skipping"
    return None


def continue_on_error_problem(text):
    """None when no run step and not the run job can let its failure pass, else the one cause."""
    job = job_block(text, "run") or ""
    own = re.search(r"^    continue-on-error:(.*)$", job, re.M)
    if own and disables("continue-on-error", own.group(1)):
        return "the run job has continue-on-error: true, so its failure cannot fail the pull request"
    for step in step_blocks(job):
        if disables("continue-on-error", step_key(step, "continue-on-error") or ""):
            return "the run step %r has continue-on-error: true, so its failure cannot fail the pull request" % step_key(step, "name")
    return None


def run_body_lines(text, name):
    """body_lines of the named run step's run text, or None when the step or its run text is absent."""
    step = named_run_step(text, name)
    body = run_body(step) if step is not None else None
    return None if body is None else body_lines(body)


class LaneCheckoutDepth(unittest.TestCase):
    def test_every_checkout_in_the_lane_workflow_fetches_a_small_depth(self):
        with open(LANE, encoding="utf-8") as f:
            text = f.read()
        depths = re.findall(r"^\s*fetch-depth:\s*(\S+)\s*$", text, re.M)
        self.assertTrue(depths, "the lane workflow has no fetch-depth, so each checkout fetches the full history")
        for depth in depths:
            self.assertTrue(depth.isdigit() and 1 <= int(depth) <= MAX_DEPTH,
                            f"a lane checkout fetches depth {depth}, want 1 to {MAX_DEPTH}")


class LaneTokenMask(unittest.TestCase):
    def test_the_base64_credential_is_masked_before_the_fetch_argv_uses_it(self):
        self.assertTrue(os.path.isfile(LANE), f"the lane workflow is missing at {LANE}")
        with open(LANE, encoding="utf-8") as f:
            problem = mask_problem(f.read())
        self.assertIsNone(problem, problem)

    def test_a_mask_that_only_a_comment_names_does_not_count(self):
        text = GOOD.replace('          echo "::add-mask::$auth"\n', '          # ::add-mask::$auth is the plan\n')
        self.assertEqual(mask_problem(text), "the base64 credential is not masked: no ::add-mask:: line, so a log can print it")

    def test_a_mask_after_the_argv_use_is_a_problem(self):
        lines = GOOD.splitlines(keepends=True)
        mask = '          echo "::add-mask::$auth"\n'
        late = [line for line in lines if line != mask] + [mask]
        self.assertEqual(mask_problem("".join(late)),
                         "the base64 credential is masked after the fetch argv already uses it")

    def test_a_mask_before_the_argv_use_passes(self):
        self.assertIsNone(mask_problem(GOOD))


class LegsMatrix(unittest.TestCase):
    """The `legs` step, run on the selector's matrix: it keeps the Windows entry and now the macOS entry too."""

    def test_a_macos_list_keeps_a_macos_leg(self):
        sel = selector_outputs(WIN_FULL, MAC_FULL)
        code, err, out = legs_run(sel["matrix"])
        self.assertEqual(code, 0, f"the legs step exits {code} on this matrix: {err}")
        entries = entries_of(out.get("matrix"))
        self.assertIsNotNone(entries, "the legs step writes no matrix output")
        macos = [e for e in entries if e.get("os") == "macos-latest"]
        self.assertTrue(macos, "the legs step drops the macos-latest entry, so a draft PR that touches a macOS-tested file starts no macOS leg")
        self.assertEqual(json.loads(macos[0]["files"]), sorted(MAC_FULL))

    def test_the_windows_entry_is_unchanged(self):
        sel = selector_outputs(WIN_FULL, MAC_ONE)
        code, err, out = legs_run(sel["matrix"])
        self.assertEqual(code, 0, f"the legs step exits {code} on this matrix: {err}")
        want = [e for e in entries_of(sel["matrix"]) if e.get("os") == "windows-latest"]
        got = [e for e in entries_of(out.get("matrix")) if e.get("os") == "windows-latest"]
        self.assertEqual(got, want, "the legs step changes the windows-latest entry")
        self.assertEqual(out.get("any"), "true")

    def test_no_macos_files_means_no_macos_leg(self):
        sel = selector_outputs(WIN_ONE, [])
        code, err, out = legs_run(sel["matrix"])
        self.assertEqual(code, 0, f"the legs step exits {code} on this matrix: {err}")
        self.assertEqual([e for e in entries_of(out.get("matrix")) if e.get("os") == "macos-latest"], [],
                         "the legs step writes a macos-latest entry with no macOS files")
        self.assertEqual(out.get("any"), "true")

    def test_no_files_starts_no_leg(self):
        sel = selector_outputs([], [])
        code, err, out = legs_run(sel["matrix"])
        self.assertEqual(code, 0, f"the legs step exits {code} on an empty matrix: {err}")
        self.assertEqual(entries_of(out.get("matrix")), [])
        self.assertEqual(out.get("any"), "false")

    def test_a_macos_only_matrix_sets_any_true(self):
        sel = selector_outputs([], MAC_ONE)
        code, err, out = legs_run(sel["matrix"])
        self.assertEqual(code, 0, f"the legs step exits {code} on this matrix: {err}")
        self.assertEqual(out.get("any"), "true",
                         "the legs step sets any for a macOS-only matrix to the wrong value, so the run job does not start for a PR that touches only macOS-tested files")


class RunStepBinding(unittest.TestCase):
    """The run job's steps: the macOS step reads its own command map and the matrix's files, and runs only those."""

    def test_the_touched_job_exposes_commands_macos(self):
        outputs = job_outputs(job_block(read_lane(), "touched"))
        self.assertEqual(squash(outputs.get("commands_macos")), "${{steps.select.outputs.commands_macos}}",
                         "the touched job does not expose commands_macos, so a macOS run step has no command map")

    def test_a_macos_run_step_reads_commands_macos_and_matrix_files(self):
        bound = [s for s in run_steps() if has_value(s, COMMANDS_MACOS)]
        self.assertTrue(bound, "no step of the run job reads commands_macos, so the macOS leg has no command map")
        self.assertTrue(has_value(bound[0], MATRIX_FILES), "the macOS run step does not read matrix.files")

    def test_the_macos_run_step_runs_only_the_listed_macos_files(self):
        bound = [s for s in run_steps() if has_value(s, COMMANDS_MACOS)]
        self.assertTrue(bound, "no step of the run job reads commands_macos, so the macOS leg has no command map")
        sel = selector_outputs(WIN_ONE, MAC_FULL)
        entry = next((e for e in entries_of(sel["matrix"]) if e.get("os") == "macos-latest"), None)
        self.assertIsNotNone(entry, "the selector wrote no macos-latest entry for a macOS list")
        outputs = job_outputs(job_block(read_lane(), "touched"))
        env_values = {k: resolve(v, sel, entry, outputs) for k, v in step_env(bound[0]).items()}
        proc, recorded = run_step(bound[0], env_values, "macOS")
        self.assertEqual(proc.returncode, 0, f"the macOS run step exits {proc.returncode}: {proc.stderr.strip()}")
        self.assertEqual(recorded, [f"{MAC_CMD} {f}" for f in MAC_FULL],
                         "the macOS run step runs other files or another interpreter than the listed macOS files")

    def test_the_macos_run_step_is_gated_to_macos(self):
        bound = [s for s in run_steps() if has_value(s, COMMANDS_MACOS)]
        self.assertTrue(bound, "no step of the run job reads commands_macos, so the macOS leg has no command map")
        for step in bound:
            problem = if_problem(step, IF_VALUES[MACOS_STEP])
            self.assertIsNone(problem, problem)

    def test_the_windows_run_steps_are_gated_to_windows(self):
        windows = [s for s in run_steps() if has_value(s, COMMANDS_WINDOWS)]
        self.assertTrue(windows, "no step of the run job reads commands_windows")
        for step in windows:
            name = step_key(step, "name")
            self.assertIn(name, IF_VALUES, f"the run step {name!r} reads commands_windows and has no pinned gate")
            problem = if_problem(step, IF_VALUES[name])
            self.assertIsNone(problem, problem)

    def test_a_negated_if_fails_the_whole_compare(self):
        """The old substring pin passes each negation below; the whole compare refuses it. The mutant is an in-memory copy of the
        macOS step's text, with its own `if:` line replaced, so the case reads the same text whether the file is right or not."""
        step = named_run_step(read_lane(), MACOS_STEP)
        self.assertIsNotNone(step, f"no run step is named {MACOS_STEP!r}")
        expr = re.fullmatch(r"\$\{\{(.*)\}\}", drop_comment(step_key(step, "if") or "").strip())
        self.assertIsNotNone(expr, "the macOS run step has no ${{ }} if: value to negate")
        inner = expr.group(1).strip()
        for mutant in ("${{ !(%s) }}" % inner, "${{ !%s }}" % inner):
            with self.subTest(mutant=mutant):
                mutated = re.sub(r"^        if: [^\n]*", lambda _: "        if: " + mutant, step, count=1, flags=re.M)
                self.assertIn("runner.os=='macos'", squash(mutant).lower(),
                              "the old substring pin would not pass this mutant, so it proves nothing about the old test")
                self.assertIsNotNone(if_problem(mutated, IF_VALUES[MACOS_STEP]),
                                     f"the whole compare passed the negated if value {mutant!r}")

    def test_the_windows_run_step_still_runs_the_listed_windows_files(self):
        bash = [s for s in run_steps() if has_value(s, COMMANDS_WINDOWS) and (step_key(s, "shell") or "").strip() == "bash"]
        self.assertTrue(bash, "no bash run step reads commands_windows")
        sel = selector_outputs(WIN_FULL, MAC_ONE)
        entry = next((e for e in entries_of(sel["matrix"]) if e.get("os") == "windows-latest"), None)
        self.assertIsNotNone(entry, "the selector wrote no windows-latest entry for a Windows list")
        outputs = job_outputs(job_block(read_lane(), "touched"))
        env_values = {k: resolve(v, sel, entry, outputs) for k, v in step_env(bash[0]).items()}
        proc, recorded = run_step(bash[0], env_values, "Windows")
        self.assertEqual(proc.returncode, 0, f"the Windows run step exits {proc.returncode}: {proc.stderr.strip()}")
        self.assertEqual(recorded, [f"{WIN_CMD} {f}" for f in WIN_FULL],
                         "the Windows run step runs other files or another interpreter than the listed Windows files")


class ReaderIgnoresComments(unittest.TestCase):
    """Each reader gives the same answer with a comment or a quoted word added to the workflow: a comment is no key, no env
    value and no run line, so a comment cannot turn a pin green (building-scanner-respects-strings)."""

    def test_a_comment_in_the_outputs_is_not_an_output(self):
        text = read_lane()
        commented = text.replace("    outputs:\n", "    outputs:\n      # commands_macos: ${{ steps.select.outputs.commands_macos }}\n", 1)
        self.assertNotEqual(commented, text, "the touched job has no outputs: line to put a comment under")
        self.assertEqual(job_outputs(job_block(commented, "touched")), job_outputs(job_block(text, "touched")))

    def test_a_comment_in_a_step_env_is_not_an_env_value(self):
        text = read_lane()
        commented = text.replace("          FILES: ${{ matrix.files }}\n",
                                      "          # COMMANDS: ${{ needs.touched.outputs.commands_macos }}\n"
                                      "          FILES: ${{ matrix.files }}\n", 1)
        self.assertNotEqual(commented, text, "the run job has no FILES line to put a comment above")
        self.assertEqual([step_env(s) for s in step_blocks(job_block(commented, "run"))],
                         [step_env(s) for s in step_blocks(job_block(text, "run"))])

    def test_a_quoted_word_in_a_run_body_is_not_an_env_value(self):
        text = read_lane()
        quoted = text.replace("          failed=0\n",
                              '          echo "COMMANDS: ${{ needs.touched.outputs.commands_macos }}"\n'
                              "          failed=0\n", 1)
        self.assertNotEqual(quoted, text, "the run job has no `failed=0` line to put a quoted word above")
        self.assertEqual([step_env(s) for s in step_blocks(job_block(quoted, "run"))],
                         [step_env(s) for s in step_blocks(job_block(text, "run"))])


class RunBodies(unittest.TestCase):
    """The macOS run step repeats the Windows one. Its body must match the Windows body, or both must call one shared script:
    a call is one line, so equal bodies cover both forms. The lines meant to differ are left out (MEANT_TO_DIFFER)."""

    def macos_body(self):
        step = named_run_step(read_lane(), MACOS_STEP)
        self.assertIsNotNone(step, f"no run step is named {MACOS_STEP!r}")
        body = run_body(step)
        self.assertIsNotNone(body, "the macOS run step has no run: text")
        return body

    def test_the_macos_run_step_body_matches_the_windows_one(self):
        win = named_run_step(read_lane(), WINDOWS_STEP)
        self.assertIsNotNone(win, f"no run step is named {WINDOWS_STEP!r}")
        win_body = run_body(win)
        self.assertIsNotNone(win_body, "the Windows run step has no run: text")
        self.assertEqual(body_lines(self.macos_body()), body_lines(win_body),
                         "the macOS run step's body differs from the Windows one beyond the lines meant to differ")

    def test_the_macos_run_step_has_no_ps1_arm(self):
        self.assertEqual(ps1_arms(self.macos_body()), [],
                         "the macOS run step has a `*.test.ps1)` arm, which never returns 77 on macOS, so it only fails the file")

    def test_the_macos_run_step_has_no_comment_naming_the_windows_step(self):
        named = [raw.strip() for raw in self.macos_body().split("\n") if raw.strip().startswith("#") and "PowerShell step" in raw]
        self.assertEqual(named, [], "the macOS run step has a comment that names the Windows-only PowerShell step")


class ArmScanner(unittest.TestCase):
    """The arm finder reads shell text, so each case pins one way a quote or a comment could fool it (building-scanner-respects-strings)."""

    def test_a_comment_opener_inside_a_string_does_not_hide_an_arm(self):
        self.assertEqual(len(ps1_arms('case "$1" in a) echo "#";; *.test.ps1) return 1 ;; esac\n')), 1,
                         "a `#` inside quotes cut the line, so the arm after it reads as absent")

    def test_a_lone_quote_in_a_comment_opens_no_string(self):
        self.assertEqual(len(ps1_arms("# don't add an arm here\n*.test.ps1) return 1 ;;\n")), 1,
                         "a lone quote in a comment opened a string, which hid the arm on the next line")

    def test_arm_text_inside_a_multi_line_string_is_not_an_arm(self):
        self.assertEqual(ps1_arms('echo "first\n*.test.ps1) return 1 ;;\nlast"\n'), [],
                         "arm text inside a multi-line quoted string reads as an arm")


class WindowsPs1Arm(unittest.TestCase):
    """The Windows run step keeps its `*.test.ps1)` arm: the arm returns 77, the skip that the PowerShell step then runs."""

    def test_the_windows_run_step_keeps_its_ps1_arm(self):
        text = read_lane()
        problem = windows_arm_problem(text)
        self.assertIsNone(problem, problem)
        mutated = mutate_block(text, named_run_step(text, WINDOWS_STEP), PS1_ARM, "")
        self.assertIsNotNone(windows_arm_problem(mutated), "the check passed a Windows run step with its arm deleted")


class ContinueOnErrorAbsent(unittest.TestCase):
    """No run step and not the run job lets its failure pass: `continue-on-error: true` would turn a red test green."""

    def test_no_run_step_and_not_the_run_job_carries_continue_on_error(self):
        text = read_lane()
        problem = continue_on_error_problem(text)
        self.assertIsNone(problem, problem)
        step = named_run_step(text, WINDOWS_STEP)
        job = job_block(text, "run")
        on_step = mutate_block(text, step, "        shell: bash\n", "        shell: bash\n        continue-on-error: true\n")
        on_job = mutate_block(text, job, "    runs-on: ${{ matrix.os }}\n", "    runs-on: ${{ matrix.os }}\n    continue-on-error: true\n")
        for where, mutated in (("on a run step", on_step), ("on the run job", on_job)):
            with self.subTest(where=where):
                self.assertIsNotNone(continue_on_error_problem(mutated), f"the check passed continue-on-error: true {where}")
        off = mutate_block(text, step, "        shell: bash\n", "        shell: bash\n        continue-on-error: false\n")
        self.assertIsNone(continue_on_error_problem(off), "the check refused continue-on-error: false, which fails nothing")


class RunJobIfPinned(unittest.TestCase):
    """The run job's whole `if:` is pinned. A literal false or a negation skips every leg, and no test goes red."""

    def test_the_run_job_if_is_the_pinned_value_and_a_false_or_a_negation_fails(self):
        text = read_lane()
        problem = run_job_if_problem(text)
        self.assertIsNone(problem, problem)
        job = job_block(text, "run")
        line = re.search(r"^    if: .*$", job, re.M).group(0)
        for value in ("${{ false }}",
                      "${{ !(github.event.pull_request.draft && needs.touched.outputs.any == 'true') }}",
                      "${{ !github.event.pull_request.draft && needs.touched.outputs.any == 'true' }}"):
            with self.subTest(value=value):
                mutated = mutate_block(text, job, line, "    if: " + value)
                self.assertIsNotNone(run_job_if_problem(mutated), f"the check passed the run job if: {value}")


class BodyCompareIgnoresComments(unittest.TestCase):
    """The body compare skips comment-only and blank lines. A `#` inside quotes is text (code_lines), so a line it opens counts."""

    def test_comment_and_blank_lines_are_no_difference_and_commands_are(self):
        text = read_lane()
        mac = run_body_lines(text, MACOS_STEP)
        self.assertEqual(run_body_lines(text, WINDOWS_STEP), mac, "the Windows and macOS run bodies differ on the real file")
        win = named_run_step(text, WINDOWS_STEP)
        with self.subTest("a comment-only line and a blank line"):
            edited = mutate_block(text, win, "          set -u\n", "          set -u\n          # don't add a rule here\n\n")
            self.assertEqual(run_body_lines(edited, WINDOWS_STEP), mac,
                             "a comment-only or blank line in the Windows run body fails the body compare")
        with self.subTest("a command edit"):
            edited = mutate_block(text, win, "          set -u\n", "          set -e\n")
            self.assertNotEqual(run_body_lines(edited, WINDOWS_STEP), mac,
                                "a command edit in the Windows run body passes the body compare")
        with self.subTest("a # line inside a multi-line string"):
            self.assertEqual(body_lines('echo "first\n# second\nlast"\n'), ['echo "first', "# second", 'last"'],
                             "a # line inside a multi-line string is dropped as a comment")


class IfCompareCaseInsensitive(unittest.TestCase):
    """GitHub compares a string in `if:` case-insensitively, so 'macos' gates the same step as 'macOS'. The compare stays
    whole, so a negation of either spelling still fails."""

    def test_the_macos_if_compare_ignores_case_and_rejects_a_negation(self):
        text = read_lane()
        step = named_run_step(text, MACOS_STEP)
        self.assertIsNotNone(step, f"no run step is named {MACOS_STEP!r}")
        problem = if_problem(step, IF_VALUES[MACOS_STEP])
        self.assertIsNone(problem, problem)
        line = "        if: ${{ runner.os == 'macOS' }}"
        for value in ("runner.os == 'macos'", "runner.os == 'MACOS'"):
            with self.subTest(value=value):
                edited = mutate_block(text, step, line, "        if: ${{ %s }}" % value)
                self.assertIsNone(if_problem(named_run_step(edited, MACOS_STEP), IF_VALUES[MACOS_STEP]),
                                  f"the check refused {value!r}, which GitHub compares as the macOS value")
        for value in ("!(runner.os == 'macos')", "!(runner.os == 'macOS')"):
            with self.subTest(value=value):
                edited = mutate_block(text, step, line, "        if: ${{ %s }}" % value)
                self.assertIsNotNone(if_problem(named_run_step(edited, MACOS_STEP), IF_VALUES[MACOS_STEP]),
                                     f"the check passed the negation {value!r}")


if __name__ == "__main__":
    unittest.main()
