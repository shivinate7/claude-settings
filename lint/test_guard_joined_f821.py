#!/usr/bin/env python3
"""Joined-order lint for the guard runner's section files: the codes ruff.toml selects, F and E9. Standard library, and ruff.

    python3 lint/test_guard_joined_f821.py              the cases
    python3 lint/test_guard_joined_f821.py --root DIR   the check on the checkout at DIR: one line per finding,
                                                        exit 1 on any, exit 2 when the join cannot be made

The runner (hooks/test_guard.py) execs each section file of tests/guard/ in its own globals, at the line that
calls load_sections. A name a section uses binds in the runner's globals at exec time, so ruff reads each file
alone and reports the name undefined. ruff.toml excludes these files from plain ruff, so this check is the only
lint they get. It joins the files the way the loader runs them: the runner's lines up to its load_sections call,
each section in `# section <n>` order, then the runner's lines after the call. Ruff reads that one file under
the codes ruff.toml selects.

The join splices the sections at the call. A plain append, with the sections after the whole runner, reads
wrong: the runner's lines after the call (LOG_CHECKS, LOG_CHECKS_EXTRA) would run after the sections they use.
The section order and the head check repeat load_sections, because a check cannot import the runner: the import
builds every fixture. The cases below pin the repeat to the loader's behaviour.
"""
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
import unittest
from fnmatch import fnmatch
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
import workflow_steps  # noqa: E402  the one home of the CI step parser

REPO = os.path.dirname(HERE)
RUNNER = os.path.join("hooks", "test_guard.py")
SECTIONS = os.path.join("tests", "guard")
CODE_CHECK = os.path.join("lint", "code_check_standard.json")
CHECKS_YML = os.path.join(".github", "workflows", "checks.yml")
RUNNER_NAME = "test_guard.py"
SECTION_HEAD = re.compile(r"# section (\d+)\n")  # the loader's own pattern (hooks/test_guard.py, load_sections)
# One finding per line: `file:line:col: CODE message`, where a fixable finding puts `[*] ` before its message.
# Ruff 0.17 prints a syntax error with the name `invalid-syntax` and no code.
FINDING_LINE = re.compile(r"^(?P<file>.+?):(?P<line>\d+):\d+: (?P<code>[A-Z]\d+) (?:\[\*\] )?(?P<msg>.+)$")
SYNTAX_LINE = re.compile(r"^(?P<file>.+?):(?P<line>\d+):\d+: invalid-syntax: (?P<msg>.+)$")
UNDEFINED = re.compile(r"^Undefined name `([^`]+)`$")
# Ruff prints a summary after its findings, then hints such as `1 unsafe fix available with ...`. A line after the
# summary that is no finding is a hint; a line before it that is no finding is one this check does not read.
RUFF_SUMMARY = ("Found ", "All checks passed")


def split_lines(text):
    """The lines of `text`, each with its newline. Splits on \\n alone, as the parser's line numbers do."""
    if not text.endswith("\n"):
        text += "\n"
    return [part + "\n" for part in text.split("\n")[:-1]]


def section_files(section_dir):
    """(number, name, text) of each section file of `section_dir`, in n order. Refuses what the loader refuses:
    no section file, a file with no `# section <n>` first line, and two files with one number."""
    found = []
    names = sorted(os.listdir(section_dir)) if os.path.isdir(section_dir) else []
    for name in names:
        if not name.endswith(".py"):
            continue
        with open(os.path.join(section_dir, name), encoding="utf-8") as f:
            text = f.read()
        head = SECTION_HEAD.match(text)
        if not head:
            raise ValueError("%s has no `# section <n>` first line" % name)
        found.append((int(head.group(1)), name, text))
    if not found:
        raise ValueError("no section file in %s, so the join would hold no case" % section_dir)
    numbers = [n for n, _, _ in found]
    for n in sorted(set(numbers)):
        if numbers.count(n) > 1:
            raise ValueError("section number %d is on %d section files" % (n, numbers.count(n)))
    return sorted(found)


def joined(runner_text, sections):
    """(text, origins): the runner with the sections spliced in at its load_sections call, and for each joined
    line the file and line it came from. The call line itself is dropped: its sections now sit in its place."""
    tree = ast.parse(runner_text)
    calls = [node for node in tree.body
             if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
             and isinstance(node.value.func, ast.Name) and node.value.func.id == "load_sections"]
    if len(calls) != 1:
        raise ValueError("the runner has %d module-level load_sections calls, want 1" % len(calls))
    call = calls[0]
    lines = split_lines(runner_text)
    chunks = [(RUNNER_NAME, 1, lines[:call.lineno - 1])]
    chunks += [(name, 1, split_lines(text)) for _, name, text in sections]
    chunks += [(RUNNER_NAME, call.end_lineno + 1, lines[call.end_lineno:])]
    text = "".join(line for _, _, part in chunks for line in part)
    origins = [(name, start + i) for name, start, part in chunks for i in range(len(part))]
    return text, origins


def ruff_command():
    """Ruff at the pin in lint/code_check_standard.json: through pipx when pipx is on PATH. Without pipx, the ruff on
    PATH, which must report the pin: another ruff reads the guard files under other rules, so the check stops."""
    with open(os.path.join(REPO, CODE_CHECK), encoding="utf-8") as f:
        pin = json.load(f)["tools"]["ruff"]
    if shutil.which("pipx"):
        return ["pipx", "run", "ruff==" + pin]
    if shutil.which("ruff"):
        version = subprocess.run(["ruff", "--version"], capture_output=True, text=True, encoding="utf-8")
        words = version.stdout.split()
        got = words[1] if version.returncode == 0 and len(words) > 1 else "unknown"
        if got != pin:
            raise RuntimeError("no pipx, and the ruff on PATH is %s, want the pin %s" % (got, pin))
        return ["ruff"]
    raise RuntimeError("no ruff: neither pipx nor ruff is on PATH")


def selected_codes():
    """The codes ruff.toml selects. The joined step selects the same, since ruff.toml no longer lints the guard files."""
    with open(os.path.join(REPO, "ruff.toml"), "rb") as f:
        return ",".join(tomllib.load(f)["lint"]["select"])


def findings(runner_path, section_dir):
    """[(file, line, code, text)] for each finding ruff reports on the joined file, in joined order. `file` and `line`
    are where the finding sits in its own file. An undefined name is F821, with text `undefined name <name>`."""
    with open(runner_path, encoding="utf-8") as f:
        runner_text = f.read()
    text, origins = joined(runner_text, section_files(section_dir))
    cmd = ruff_command() + ["check", "--isolated", "--no-cache", "--select", selected_codes(),
                            "--output-format", "concise", "--stdin-filename", "joined.py", "-"]
    proc = subprocess.run(cmd, input=text, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode not in (0, 1):
        raise RuntimeError("ruff failed (exit %d): %s" % (proc.returncode, proc.stderr.strip()))
    out = []
    summarized = False
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        m = FINDING_LINE.match(line) or SYNTAX_LINE.match(line)
        if not m:
            if line.startswith(RUFF_SUMMARY):
                summarized = True
            elif not summarized:
                raise RuntimeError("ruff printed a line this check does not read: %s" % line)
            continue
        code = m.groupdict().get("code") or "invalid-syntax"
        msg = m.group("msg")
        if code == "F821":
            undefined = UNDEFINED.match(msg)
            if not undefined:
                raise RuntimeError("ruff printed an F821 this check does not read: %s" % line)
            msg = "undefined name " + undefined.group(1)
        name, start = origins[int(m.group("line")) - 1]
        out.append((name, start, code, msg))
    return out


def undefined_names(runner_path, section_dir):
    """[(name, file, line)] for each name the joined file reads as undefined (F821), in joined order."""
    return [(text[len("undefined name "):], name, start)
            for name, start, code, text in findings(runner_path, section_dir) if code == "F821"]


def check(root):
    return findings(os.path.join(root, RUNNER), os.path.join(root, SECTIONS))


def read(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8") as f:
        return f.read()


class JoinedOrderLint(unittest.TestCase):
    """The join, the check and the wiring. Each planted case builds its tree in this run's folder."""

    def setUp(self):
        self.run = RUN_FOLDER

    def make_tree(self, name, planted=None):
        """A checkout-shaped folder under the run: the runner and every section file, each a link to the real
        file (never a copy), and one more section file holding `planted` when given."""
        root = os.path.join(self.run, name)
        os.makedirs(os.path.join(root, "hooks"))
        os.makedirs(os.path.join(root, "tests", "guard"))
        os.symlink(os.path.join(REPO, RUNNER), os.path.join(root, RUNNER))
        for entry in os.listdir(os.path.join(REPO, SECTIONS)):
            if entry.endswith(".py"):
                os.symlink(os.path.join(REPO, SECTIONS, entry), os.path.join(root, SECTIONS, entry))
        if planted is not None:
            with open(os.path.join(root, SECTIONS, "zz_planted.py"), "w", encoding="utf-8") as f:
                f.write("# section 99999\n" + planted)
        return root

    def test_real_tree_joins_every_section_and_reads_no_undefined_name(self):
        sections = section_files(os.path.join(REPO, SECTIONS))
        _text, origins = joined(read(REPO, RUNNER), sections)
        # Scope first: the join holds every section file, then the subject (the names) is judged.
        joined_names = {name for name, _ in origins}
        self.assertTrue({name for _, name, _ in sections} <= joined_names,
                        "the join leaves out a section file")
        hits = check(REPO)
        self.assertEqual(hits, [], "undefined names on the joined tree: %s" % hits)

    def test_sections_come_before_the_runner_lines_that_use_them(self):
        """The runner's lines after load_sections read LOG_CHECKS, which the sections define. A join that appends
        the sections after the whole runner would put those reads first."""
        text, origins = joined(read(REPO, RUNNER), section_files(os.path.join(REPO, SECTIONS)))
        lines = text.split("\n")
        tail = [i for i, line in enumerate(lines) if line.startswith("UNJOINED = [")]
        self.assertEqual(len(tail), 1, "the runner's tail line is not found once in the join")
        last_section = max(i for i, (name, _) in enumerate(origins) if name != RUNNER_NAME)
        self.assertLess(last_section, tail[0], "the sections sit after the runner lines that use them")
        self.assertFalse(any(line.startswith("load_sections(") for line in lines),
                         "the load_sections call is still in the join")

    def test_planted_misspelled_name_in_a_section_is_reported_with_its_place(self):
        root = self.make_tree("planted", planted="_planted = FAMILES\n")
        hits = undefined_names(os.path.join(root, RUNNER), os.path.join(root, SECTIONS))
        self.assertEqual(hits, [("FAMILES", "zz_planted.py", 2)], "the planted name was not reported where it sits")

    def test_correct_spelling_in_the_same_planted_place_reads_clean(self):
        root = self.make_tree("control", planted="_planted = FAMILIES\n")
        self.assertEqual(undefined_names(os.path.join(root, RUNNER), os.path.join(root, SECTIONS)), [],
                         "the correctly spelled control reads an undefined name")

    def test_empty_section_folder_is_refused_not_passed_clean(self):
        folder = os.path.join(self.run, "empty-sections")
        os.makedirs(folder)
        with self.assertRaisesRegex(ValueError, "no section file"):
            undefined_names(os.path.join(REPO, RUNNER), folder)

    def test_script_mode_exits_one_and_names_the_planted_name(self):
        root = self.make_tree("script", planted="_planted = FAMILES\n")
        proc = subprocess.run([sys.executable, os.path.abspath(__file__), "--root", root],
                              capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("zz_planted.py:2: F821 undefined name FAMILES", proc.stdout)

    def test_planted_unused_import_in_a_section_is_reported(self):
        """ruff.toml excludes the guard files from plain ruff, so this step lints them under F and E9 too: an unused
        import in a section is a finding, not a clean join."""
        root = self.make_tree("unused-import", planted="import colorsys\n")
        proc = subprocess.run([sys.executable, os.path.abspath(__file__), "--root", root],
                              capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(proc.returncode, 1, "the planted unused import reads clean: " + proc.stdout + proc.stderr)
        self.assertIn("zz_planted.py:2: F401", proc.stdout)

    def test_planted_syntax_error_in_a_section_is_a_finding_not_a_failed_join(self):
        """A syntax error in a section is reported with its place, and the join still holds. Ruff prints it with no
        F or E9 code, so a parser that reads only coded lines stops the join with exit 2."""
        root = self.make_tree("syntax", planted="_planted = )\n")
        proc = subprocess.run([sys.executable, os.path.abspath(__file__), "--root", root],
                              capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(proc.returncode, 1, "the planted syntax error did not read as a finding: " + proc.stdout
                         + proc.stderr)
        self.assertIn("zz_planted.py:2: invalid-syntax", proc.stdout)

    def test_planted_unused_local_in_a_section_is_reported_with_its_place(self):
        """An unused local is F841, and ruff offers its fix only unsafe, so ruff prints a hint line after its summary. The
        hint is no finding: the finding and its place are read, and the join is not refused."""
        root = self.make_tree("unused-local", planted="def _planted():\n    unused = 1\n")
        proc = subprocess.run([sys.executable, os.path.abspath(__file__), "--root", root],
                              capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(proc.returncode, 1, "the planted unused local did not read as a finding: "
                         + proc.stdout + proc.stderr)
        self.assertIn("zz_planted.py:3: F841", proc.stdout, "the planted unused local is not reported where it sits")

    def fake_ruff_on_path(self, version):
        """A folder on PATH holding a `ruff` that reports `version`, and nothing else: no pipx."""
        folder = os.path.join(self.run, "ruff-%s" % version)
        os.makedirs(folder)
        fake = os.path.join(folder, "ruff")
        with open(fake, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\necho 'ruff %s'\n" % version)
        os.chmod(fake, 0o755)
        return folder

    def test_ruff_on_path_at_another_version_stops_the_check_without_pipx(self):
        """Without pipx the check runs the ruff on PATH, which must be the pin. Any other ruff reads the guard files
        under other rules, so the check stops."""
        pin = json.loads(read(REPO, CODE_CHECK))["tools"]["ruff"]
        other = "0.0.1" if pin != "0.0.1" else "0.0.2"
        with mock.patch.dict(os.environ, {"PATH": self.fake_ruff_on_path(other)}):
            with self.assertRaisesRegex(RuntimeError, "want the pin %s" % re.escape(pin)):
                ruff_command()

    def test_ruff_on_path_at_the_pin_is_used_without_pipx(self):
        pin = json.loads(read(REPO, CODE_CHECK))["tools"]["ruff"]
        with mock.patch.dict(os.environ, {"PATH": self.fake_ruff_on_path(pin)}):
            self.assertEqual(ruff_command(), ["ruff"], "the ruff at the pin was refused")

    def test_ruff_toml_no_longer_ignores_f821_for_the_guard_files(self):
        with open(os.path.join(REPO, "ruff.toml"), "rb") as f:
            ignores = tomllib.load(f).get("lint", {}).get("per-file-ignores", {})
        samples = ("hooks/test_guard.py", "tests/guard/s00442-misc.py")
        held = [pat for pat, codes in ignores.items()
                if "F821" in codes and any(fnmatch(sample, pat) for sample in samples)]
        self.assertEqual(held, [], "ruff.toml still ignores F821 for the guard files: %s" % held)

    def test_checks_workflow_runs_this_suite(self):
        text = read(REPO, CHECKS_YML)
        runs = []
        for job in workflow_steps.CHECKS_SUITE_JOBS:
            block = workflow_steps.job_block(text, job) or ""
            runs += [workflow_steps.run_body(step) or "" for step in workflow_steps.step_blocks(block)]
        self.assertTrue(any("lint/test_guard_joined_f821.py" in run for run in runs),
                        "checks.yml runs no step of the joined-order lint suite")


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)


def main(argv):
    if len(argv) == 2 and argv[0] == "--root":
        try:
            hits = check(argv[1])
        except (ValueError, RuntimeError) as err:
            print("joined-order lint: the join could not be made: %s" % err)
            return 2
        for file, line, code, text in hits:
            print("%s:%d: %s %s" % (file, line, code, text))
        print("joined-order lint: %d finding(s)" % len(hits))
        return 1 if hits else 0
    unittest.main(argv=[sys.argv[0]])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
