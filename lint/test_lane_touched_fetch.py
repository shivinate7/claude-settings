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
from workflow_steps import drop_comment, job_block, run_body, step_blocks, step_env, step_key  # noqa: E402  the one home of the step parser

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
        if_value = squash(step_key(bound[0], "if")).lower()
        self.assertTrue("runner.os=='macos'" in if_value or "matrix.os=='macos-latest'" in if_value,
                        "the macOS run step has no macOS gate, so a Windows leg runs it with the macOS command map")

    def test_the_windows_run_steps_are_gated_to_windows(self):
        windows = [s for s in run_steps() if has_value(s, COMMANDS_WINDOWS)]
        self.assertTrue(windows, "no step of the run job reads commands_windows")
        for step in windows:
            if_value = squash(step_key(step, "if")).lower()
            self.assertTrue("runner.os=='windows'" in if_value or "matrix.os=='windows-latest'" in if_value,
                            "a run step reads commands_windows with no Windows gate, so a macOS leg runs it with the Windows command map")

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


if __name__ == "__main__":
    unittest.main()
