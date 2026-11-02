#!/usr/bin/env python3
"""Cases for the JavaScript and TypeScript mutant maker: hooks/mutate_js.mjs, and its Python side in
hooks/mutate_shared.py (`js_mutants`, `changed_lines`, `classify_node_tap`, and the `lines` filter of
`ast_mutants`). Standard library only, unittest style, like hooks/test_mutate_report.py.

    python3 hooks/test_mutate_js.py

The engine parses with the typescript package in the repository's node_modules. A missing package
is a FAIL, never a skip: `npm ci --ignore-scripts --no-audit --no-fund` at the repository root
installs it. No case skips, because a skipped case reads as a pass.

Temp files live in the run folder of lint/_test_temp.py. Each fixture gets its own folder under it.
"""
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import time
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ENGINE = os.path.join(HERE, "mutate_js.mjs")
LOADER = os.path.join("skills", "plain-english-map", "scripts", "lib", "lazy-typescript.mjs")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
import mutate_shared  # noqa: E402

NODE = shutil.which("node") or "node"
RUN = ""  # this run's folder, made in setUpModule and removed in tearDownModule


def setUpModule():
    global RUN
    RUN = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN, ignore_errors=True)


def write(name, text):
    """A fixture file in a folder of its own under the run folder. Returns its absolute path."""
    folder = os.path.join(RUN, uuid.uuid4().hex)
    os.makedirs(folder)
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def engine(path, lines=None):
    """Run the engine on one file. Returns the process; the caller reads the verdict."""
    command = [NODE, ENGINE, path]
    if lines is not None:
        command += ["--lines", lines]
    return subprocess.run(command, capture_output=True, text=True, timeout=120)


def engine_mutants(path, lines=None):
    done = engine(path, lines)
    if done.returncode != 0:
        raise AssertionError("engine exit %d: %s" % (done.returncode, done.stderr.strip()))
    return json.loads(done.stdout)


def edit_of(source, text):
    """(line, new text) of the one source line that a mutant changes. The new text is None when the
    line is removed. A mutant that changes two source lines, or reprints the file, raises."""
    old_lines, new_lines = source.split("\n"), text.split("\n")
    shortest = min(len(old_lines), len(new_lines))
    head = 0
    while head < shortest and old_lines[head] == new_lines[head]:
        head += 1
    tail = 0
    while tail < shortest - head and old_lines[-1 - tail] == new_lines[-1 - tail]:
        tail += 1
    old = old_lines[head:len(old_lines) - tail]
    new = new_lines[head:len(new_lines) - tail]
    if len(old) != 1 or len(new) > 1:
        raise AssertionError("a mutant changes %d source lines and writes %d" % (len(old), len(new)))
    return head + 1, (new[0] if new else None)


def unique_line(source, text):
    """The 1-based number of the one source line equal to `text`."""
    hits = [number for number, line in enumerate(source.split("\n"), 1) if line == text]
    if len(hits) != 1:
        raise AssertionError("expected one source line %r, found %d" % (text, len(hits)))
    return hits[0]


def git(cwd, *args):
    done = subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid", *args],
                          cwd=cwd, capture_output=True, text=True)
    if done.returncode != 0:
        raise AssertionError("git %s failed: %s" % (" ".join(args), done.stderr.strip()))
    return done.stdout.strip()


# One body, shared by the TypeScript and the .mjs fixture. Every kind of site appears in it once.
BODY = """\
  const   odd=1;
  if (p.a === p.b && ok) {
    return true;
  }
  if (p.a !== p.b || !ok) {
    return false;
  }
  const same = p.a == p.b;
  const differs = p.a != p.b;
  while (p.a < p.b) {
    p.a = p.a + 1;
  }
  if (p.a > p.b) {
    p.a = 0;
  }
  return p.a <= p.b;
}
"""
TS_SOURCE = ("// keep   this  spacing\n"
             "type Pair = { a: number; b: number };\n"
             "export function gate(p: Pair, ok: boolean): boolean {\n" + BODY)
MJS_SOURCE = "// keep   this  spacing\nexport function gate(p, ok) {\n" + BODY
TSX_SOURCE = """\
type Props = { ok: boolean };
export const Card = (props: Props) => {
  if (props.ok === true) {
    return <p>Don't</p>;
  }
  return <p>no</p>;
};
"""
JSX_SOURCE = """\
export const Card = (props) => {
  if (props.ok === true) {
    return <p>Don't</p>;
  }
  return <p>no</p>;
};
"""

# (kind, source line, the exact line the mutant writes in its place). Each row runs on the TypeScript
# and the .mjs fixture. The return-dropped kind is checked apart, because the engine may write the
# dropped line as nothing or remove it.
KINDS = [
    ("comparison === to !==", "  if (p.a === p.b && ok) {", "  if (p.a !== p.b && ok) {"),
    ("comparison !== to ===", "  if (p.a !== p.b || !ok) {", "  if (p.a === p.b || !ok) {"),
    ("comparison == to !=", "  const same = p.a == p.b;", "  const same = p.a != p.b;"),
    ("comparison != to ==", "  const differs = p.a != p.b;", "  const differs = p.a == p.b;"),
    ("comparison < to >=", "  while (p.a < p.b) {", "  while (p.a >= p.b) {"),
    ("comparison > to <=", "  if (p.a > p.b) {", "  if (p.a <= p.b) {"),
    ("logical && to ||", "  if (p.a === p.b && ok) {", "  if (p.a === p.b || ok) {"),
    ("logical || to &&", "  if (p.a !== p.b || !ok) {", "  if (p.a !== p.b && !ok) {"),
    ("prefix ! dropped", "  if (p.a !== p.b || !ok) {", "  if (p.a !== p.b || ok) {"),
    ("true to false", "    return true;", "    return false;"),
    ("false to true", "    return false;", "    return true;"),
    ("if test negated", "  if (p.a === p.b && ok) {", "  if (!(p.a === p.b && ok)) {"),
    ("while test negated", "  while (p.a < p.b) {", "  while (!(p.a < p.b)) {"),
    ("return value to undefined", "  return p.a <= p.b;", "  return undefined;"),
]

# Comment openers and a lone quote inside strings, and a multi-line template literal that holds
# `a === b` text. Each trap alone gives no mutant. Each trap with a real defect after it gives the
# defect's mutants only.
TRAPS = [
    ("comment opener /* inside a string", 'const s = "/* x */";\n'),
    ("comment opener // inside a string", "const t = '// y';\n"),
    ("comment opener # inside a string", 'const u = "# z";\n'),
    ("multi-line template literal holding a === b", "const v = `first\nif (p.a === p.b) {\nlast`;\n"),
    ("lone quote in a string", 'const w = "Don\'t";\n'),
]
JSX_TRAP = ("lone quote in JSX text", "const el = <p>Don't</p>;\n")
DEFECT = "if (p.a === p.b) {}\n"

# A small file for the Python side: the default output of ast_mutants on it is pinned by digest, so
# a change to the default is visible.
AST_SOURCE = """\
def is_big(n, limit):
    if n > limit and n != 0:
        return True
    while n < 3:
        n = n + 1
    return False
"""
AST_DEFAULT_DIGEST = "c66ccfd6e7ae370015036baf0098884c3a904f2f05bd365629b0a1c716443531"

# Node test files: one per class the classifier must tell apart, plus a crash that names an assertion.
PASS_TEST = """\
import test from 'node:test';
import assert from 'node:assert/strict';
test('adds', () => { assert.equal(1 + 1, 2); });
"""
ASSERT_TEST = """\
import test from 'node:test';
import assert from 'node:assert/strict';
test('adds wrong', () => { assert.equal(1 + 1, 3); });
"""
IMPORT_TEST = """\
import test from 'node:test';
import './missing-module.mjs';
test('never runs', () => {});
"""
THROW_TEST = """\
import test from 'node:test';
test('throws', () => { throw new Error('boom'); });
"""
# AssertionError is not imported, so the test throws a ReferenceError that names it.
UNIMPORTED_ERROR_TEST = """\
import test from 'node:test';
test('throws an assertion it never imported', () => { throw new AssertionError({ message: 'boom' }); });
"""


class EngineTests(unittest.TestCase):

    def test_typescript_is_installed_in_the_repository(self):
        path = os.path.join(REPO, "node_modules", "typescript", "package.json")
        self.assertTrue(os.path.isfile(path),
                        "typescript is not installed: run npm ci --ignore-scripts --no-audit --no-fund at the repository root")

    def test_the_engine_loads_typescript_only_through_the_one_loader(self):
        # A copy of the engine and of the one loader, outside the clone: no node_modules is above it, so
        # the loader's own message must appear. An engine that imports typescript some other way parses.
        root = os.path.join(RUN, uuid.uuid4().hex)
        os.makedirs(os.path.join(root, "hooks"))
        os.makedirs(os.path.dirname(os.path.join(root, LOADER)))
        shutil.copy(ENGINE, os.path.join(root, "hooks", "mutate_js.mjs"))
        shutil.copy(os.path.join(REPO, LOADER), os.path.join(root, LOADER))
        # NODE_PATH removed: a machine that sets it to a global typescript would load the package by that
        # route, and the case would then prove nothing about the one loader.
        env = dict(os.environ)
        env.pop("NODE_PATH", None)
        done = subprocess.run([NODE, os.path.join(root, "hooks", "mutate_js.mjs"), write("gate.ts", TS_SOURCE)],
                              capture_output=True, text=True, timeout=120, env=env)
        self.assertNotEqual(done.returncode, 0, "the engine parsed without the loader's package")
        self.assertIn("cannot load the typescript package", done.stderr)

    def test_each_kind_on_the_typescript_fixture(self):
        self.check_kinds("gate.ts", TS_SOURCE)

    def test_each_kind_on_the_mjs_fixture(self):
        self.check_kinds("gate.mjs", MJS_SOURCE)

    def check_kinds(self, name, source):
        found = engine_mutants(write(name, source))
        for label, old_line, new_line in KINDS:
            with self.subTest(kind=label):
                line = unique_line(source, old_line)
                edits = [edit_of(source, m["text"]) for m in found if m["line"] == line]
                self.assertIn((line, new_line), edits, "no mutant writes %r on line %d" % (new_line, line))
        with self.subTest(kind="return dropped"):
            line = unique_line(source, "    return false;")
            edits = [edit_of(source, m["text"]) for m in found if m["line"] == line]
            self.assertTrue(any(new is None or "return" not in new for _, new in edits),
                            "no mutant drops the return on line %d" % line)

    def test_every_mutant_edits_only_the_line_its_label_names(self):
        for name, source in (("gate.ts", TS_SOURCE), ("gate.mjs", MJS_SOURCE)):
            with self.subTest(fixture=name):
                for mutant in engine_mutants(write(name, source)):
                    self.assertEqual(edit_of(source, mutant["text"])[0], mutant["line"], mutant["label"])
                    self.assertTrue(mutant["label"].startswith("L%d " % mutant["line"]), mutant["label"])

    def test_every_mutant_keeps_the_text_outside_its_edit(self):
        # The comment and the odd spacing sit far from the sites. A reprint would move them.
        for name, source in (("gate.ts", TS_SOURCE), ("gate.mjs", MJS_SOURCE)):
            with self.subTest(fixture=name):
                for mutant in engine_mutants(write(name, source)):
                    self.assertIn("// keep   this  spacing", mutant["text"])
                    self.assertIn("  const   odd=1;", mutant["text"])

    def test_a_mutant_equal_to_the_source_is_left_out(self):
        # `return undefined` on a line that already says it: the return-value mutant equals the source.
        source = "function f(a) {\n  return undefined;\n}\n"
        found = engine_mutants(write("same.mjs", source))
        self.assertTrue(all(m["text"] != source for m in found))
        self.assertEqual(len(found), 1, "only the dropped return should remain")
        self.assertEqual(edit_of(source, found[0]["text"])[0], 2)

    def test_the_same_file_gives_the_same_output_twice(self):
        path = write("gate.ts", TS_SOURCE)
        first = engine(path).stdout
        self.assertTrue(first)
        self.assertEqual(first, engine(path).stdout)

    def test_a_parse_error_exits_nonzero_with_a_message(self):
        for name, text in (("broken.ts", "const x = ;\n"), ("broken.mjs", "function (\n")):
            with self.subTest(fixture=name):
                done = engine(write(name, text))
                self.assertNotEqual(done.returncode, 0)
                self.assertTrue(done.stderr.strip(), "a parse error printed no message")

    def test_lines_keeps_only_the_listed_lines(self):
        path = write("gate.ts", TS_SOURCE)
        target = unique_line(TS_SOURCE, "  if (p.a > p.b) {")
        only = engine_mutants(path, lines=str(target))
        self.assertTrue(only)
        self.assertTrue(all(m["line"] == target for m in only))
        self.assertEqual(only, [m for m in engine_mutants(path) if m["line"] == target])

    def test_lines_takes_a_comma_list(self):
        path = write("gate.ts", TS_SOURCE)
        first = unique_line(TS_SOURCE, "  if (p.a === p.b && ok) {")
        second = unique_line(TS_SOURCE, "  while (p.a < p.b) {")
        found = engine_mutants(path, lines="%d,%d" % (first, second))
        self.assertEqual({m["line"] for m in found}, {first, second})

    def test_lines_on_a_line_with_no_site_gives_nothing(self):
        self.assertEqual(engine_mutants(write("gate.ts", TS_SOURCE), lines="1"), [])

    def test_a_line_separator_inside_a_string_is_not_a_line_break(self):
        # U+2028 and U+2029 end a line for TypeScript's line map. Inside a string literal a reader sees no
        # line break, so the comparison on line 3 must keep its number.
        for separator in ("\u2028", "\u2029"):
            with self.subTest(separator=hex(ord(separator))):
                source = 'const sep = "a%sb";\nconst other = 1;\nif (p.a === p.b) {}\n' % separator
                path = write("separator.ts", source)
                self.assertEqual({m["line"] for m in engine_mutants(path)}, {3})
                line = unique_line(source, "if (p.a === p.b) {}")
                only = engine_mutants(path, lines=str(line))
                self.assertIn("L3 compare === -> !==", [m["label"] for m in only])
                self.assertTrue(all(m["line"] == line for m in only))

    def test_a_tsx_file_parses_its_jsx_and_mutates_its_sites(self):
        line = unique_line(TSX_SOURCE, "  if (props.ok === true) {")
        found = engine_mutants(write("card.tsx", TSX_SOURCE))
        edits = [edit_of(TSX_SOURCE, m["text"]) for m in found if m["line"] == line]
        self.assertIn((line, "  if (props.ok !== true) {"), edits)

    def test_a_boolean_in_a_type_position_gets_no_mutant(self):
        # `true` and `false` in a type are literal types, not values. A mutant there is one no test can kill.
        # The value on the next line still gets its mutant.
        source = "type R = { ok: true } | { ok: false };\nconst ok = true;\n"
        edits = [edit_of(source, m["text"]) for m in engine_mutants(write("types.ts", source))]
        self.assertEqual([edit for edit in edits if edit[0] == 1], [], "a mutant was made in a type position")
        self.assertIn((2, "const ok = false;"), edits)

    def test_each_extension_parses_with_its_own_grammar(self):
        cases = [(".js", MJS_SOURCE), (".cjs", MJS_SOURCE), (".mjs", MJS_SOURCE), (".ts", TS_SOURCE),
                 (".mts", TS_SOURCE), (".jsx", JSX_SOURCE), (".tsx", TSX_SOURCE)]
        for ext, source in cases:
            with self.subTest(ext=ext):
                found = engine_mutants(write("sample" + ext, source))
                self.assertTrue(found, "no mutant from a file that has sites")
                for mutant in found:
                    self.assertEqual(edit_of(source, mutant["text"])[0], mutant["line"])

    def test_scanner_traps_alone_make_no_mutant_and_do_not_hide_a_defect(self):
        # building-scanner-respects-strings: each trap, then a real defect on the next line.
        for ext, traps in ((".ts", TRAPS), (".mjs", TRAPS), (".tsx", TRAPS + [JSX_TRAP])):
            for label, trap in traps:
                with self.subTest(ext=ext, trap=label):
                    self.assertEqual(engine_mutants(write("trap" + ext, trap)), [],
                                     "a mutant was made inside a string, a template or JSX text")
                    defect_line = trap.count("\n") + 1
                    armed = trap + DEFECT
                    found = engine_mutants(write("armed" + ext, armed))
                    self.assertTrue(found, "the defect after the trap was missed")
                    for mutant in found:
                        self.assertEqual(edit_of(armed, mutant["text"])[0], defect_line)



class JsMutantsTests(unittest.TestCase):

    def test_returns_label_and_text_pairs_that_differ_from_the_source(self):
        found = mutate_shared.js_mutants(write("gate.ts", TS_SOURCE))
        self.assertTrue(found)
        for item in found:
            self.assertIsInstance(item, tuple)
            self.assertEqual(len(item), 2)
            label, text = item
            self.assertTrue(label.startswith("L"), label)
            self.assertNotEqual(text, TS_SOURCE)

    def test_a_sample_is_drawn_the_way_ast_mutants_draws_one(self):
        path = write("gate.ts", TS_SOURCE)
        full = mutate_shared.js_mutants(path)
        keep = sorted(random.Random(7).sample(range(len(full)), 3))
        self.assertEqual(mutate_shared.js_mutants(path, limit=3, seed=7), [full[i] for i in keep])

    def test_a_limit_above_the_count_keeps_every_mutant_in_order(self):
        path = write("gate.ts", TS_SOURCE)
        full = mutate_shared.js_mutants(path)
        self.assertEqual(mutate_shared.js_mutants(path, limit=len(full) + 5), full)

    def test_lines_keeps_only_the_listed_lines(self):
        line = unique_line(TS_SOURCE, "  while (p.a < p.b) {")
        found = mutate_shared.js_mutants(write("gate.ts", TS_SOURCE), lines=[line])
        self.assertTrue(found)
        for label, _text in found:
            self.assertTrue(label.startswith("L%d " % line), label)

    def test_the_same_file_gives_the_same_pairs_twice(self):
        path = write("gate.mjs", MJS_SOURCE)
        self.assertEqual(mutate_shared.js_mutants(path), mutate_shared.js_mutants(path))

    def test_a_parse_error_raises_value_error(self):
        with self.assertRaises(ValueError):
            mutate_shared.js_mutants(write("broken.mjs", "function (\n"))

    def test_an_empty_lines_set_gives_no_mutant(self):
        path = write("gate.ts", TS_SOURCE)
        self.assertTrue(mutate_shared.js_mutants(path), "the fixture has no site to filter")
        self.assertEqual(mutate_shared.ast_mutants(AST_SOURCE, lines=set()), [])
        self.assertEqual(mutate_shared.js_mutants(path, lines=set()), [])


class AstSideTests(unittest.TestCase):

    def test_the_default_output_is_unchanged(self):
        pairs = mutate_shared.ast_mutants(AST_SOURCE)
        digest = hashlib.sha256(json.dumps(pairs).encode("utf-8")).hexdigest()
        self.assertEqual(digest, AST_DEFAULT_DIGEST)
        self.assertEqual(mutate_shared.ast_mutants(AST_SOURCE, lines=None), pairs)

    def test_lines_keeps_only_the_sites_on_those_lines(self):
        only = mutate_shared.ast_mutants(AST_SOURCE, lines=[2])
        self.assertTrue(only)
        for label, _text in only:
            self.assertTrue(label.startswith("L2 "), label)
        self.assertEqual(only, [item for item in mutate_shared.ast_mutants(AST_SOURCE) if item[0].startswith("L2 ")])

    def test_a_sample_is_the_seeded_sample_of_the_full_list(self):
        full = mutate_shared.ast_mutants(AST_SOURCE)
        keep = sorted(random.Random(4).sample(range(len(full)), 3))
        self.assertEqual(mutate_shared.ast_mutants(AST_SOURCE, limit=3, seed=4), [full[i] for i in keep])


def write_files(folder, files):
    for name, text in files.items():
        with open(os.path.join(folder, name), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)


class ChangedLinesTests(unittest.TestCase):

    def commits(self, before, after):
        """A repository with two commits, each a map of file name to text. Returns (repo, base, head)."""
        repo = os.path.join(RUN, uuid.uuid4().hex)
        os.makedirs(repo)
        git(repo, "init", "-q")
        shas = []
        for files in (before, after):
            write_files(repo, files)
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", "commit")
            shas.append(git(repo, "rev-parse", "HEAD"))
        return repo, shas[0], shas[1]

    def test_a_changed_and_an_appended_line_are_both_listed(self):
        repo, base, head = self.commits({"subject.js": "one\ntwo\nthree\nfour\nfive\n"},
                                        {"subject.js": "one\nTWO\nthree\nfour\nfive\nsix\n"})
        result = mutate_shared.changed_lines(repo, base, head, "subject.js")
        self.assertIsInstance(result, set)
        self.assertEqual(result, {2, 6})

    def test_a_deletion_adds_no_line(self):
        repo, base, head = self.commits({"subject.js": "one\ntwo\nthree\n"}, {"subject.js": "one\nthree\n"})
        self.assertEqual(mutate_shared.changed_lines(repo, base, head, "subject.js"), set())

    def test_a_file_that_did_not_change_lists_nothing(self):
        repo, base, head = self.commits({"subject.js": "one\n", "other.txt": "x\n"},
                                        {"subject.js": "one\n", "other.txt": "x\nmore\n"})
        self.assertEqual(mutate_shared.changed_lines(repo, base, head, "subject.js"), set())

    def test_only_the_lines_of_the_named_path_are_listed(self):
        repo, base, head = self.commits({"subject.js": "one\ntwo\n", "other.txt": "x\n"},
                                        {"subject.js": "one\ntwo\nthree\n", "other.txt": "x\ny\nz\n"})
        self.assertEqual(mutate_shared.changed_lines(repo, base, head, "subject.js"), {3})


class NodeTapTests(unittest.TestCase):

    def node_test(self, name, text):
        """Run `node --test` on one fixture file. Returns (exit code, output)."""
        done = subprocess.run([NODE, "--test", "--test-reporter=tap", write(name, text)],
                              capture_output=True, text=True, timeout=120)
        return done.returncode, done.stdout + done.stderr

    def test_a_passing_file_is_a_pass(self):
        code, output = self.node_test("pass.test.mjs", PASS_TEST)
        self.assertIn("ok 1", output)
        self.assertEqual(mutate_shared.classify_node_tap(code, output, False), "pass")

    def test_a_failing_assertion_is_an_assert(self):
        code, output = self.node_test("assert.test.mjs", ASSERT_TEST)
        self.assertIn("ERR_ASSERTION", output, "the fixture did not fail on an assertion")
        self.assertEqual(mutate_shared.classify_node_tap(code, output, False), "assert")

    def test_an_import_throw_is_a_crash_not_a_kill(self):
        code, output = self.node_test("import.test.mjs", IMPORT_TEST)
        self.assertIn("not ok", output, "the fixture did not fail as a test")
        self.assertNotIn("ERR_ASSERTION", output)
        self.assertEqual(mutate_shared.classify_node_tap(code, output, False), "crash")

    def test_a_throw_inside_a_test_is_a_crash_not_a_kill(self):
        code, output = self.node_test("throw.test.mjs", THROW_TEST)
        self.assertIn("boom", output)
        self.assertEqual(mutate_shared.classify_node_tap(code, output, False), "crash")

    def test_an_unimported_assertion_error_is_a_crash_not_a_kill(self):
        code, output = self.node_test("unimported.test.mjs", UNIMPORTED_ERROR_TEST)
        self.assertIn("AssertionError is not defined", output, "the fixture did not fail on the missing name")
        self.assertIn("name: 'ReferenceError'", output)
        self.assertNotIn("ERR_ASSERTION", output)
        self.assertEqual(mutate_shared.classify_node_tap(code, output, False), "crash")

    def test_a_timeout_is_a_timeout_whatever_the_output(self):
        self.assertEqual(mutate_shared.classify_node_tap(0, "ok 1 - x\n", True), "timeout")
        self.assertEqual(mutate_shared.classify_node_tap(1, "not ok 1 - x\n", True), "timeout")

    def test_only_a_not_ok_block_with_an_assertion_is_an_assert(self):
        cases = [
            ("ERR_ASSERTION in a not ok block",
             "not ok 1 - t\n  ---\n  error: 'x'\n  code: 'ERR_ASSERTION'\n  ...\n", "assert"),
            ("AssertionError in a not ok block",
             "not ok 1 - t\n  ---\n  name: 'AssertionError'\n  ...\n", "assert"),
            ("ERR_ASSERTION only in an ok block",
             "ok 1 - t\n  ---\n  code: 'ERR_ASSERTION'\n  ...\nnot ok 2 - u\n  ---\n  error: 'boom'\n  ...\n", "crash"),
            ("red with no TAP block", "Error: boom\n", "crash"),
            ("exit 0 is a pass", "not ok 1 - t\n", "pass"),
        ]
        for case, output, want in cases:
            with self.subTest(case=case):
                code = 0 if want == "pass" else 1
                self.assertEqual(mutate_shared.classify_node_tap(code, output, False), want)


class TempRunFolderTests(unittest.TestCase):

    def test_the_first_run_sweeps_an_old_sibling_and_keeps_a_new_one(self):
        root = os.path.join(RUN, uuid.uuid4().hex)
        os.makedirs(root)
        old = os.path.join(root, "4242-%s" % uuid.uuid4().hex)
        fresh = os.path.join(root, "4343-%s" % uuid.uuid4().hex)
        os.makedirs(old)
        os.makedirs(fresh)
        two_days_ago = time.time() - 2 * 24 * 60 * 60
        os.utime(old, (two_days_ago, two_days_ago))
        own = _test_temp.run_folder(temp_root=root)
        self.assertFalse(os.path.exists(old), "an old sibling run folder was kept")
        self.assertTrue(os.path.isdir(fresh), "a new sibling run folder was removed")
        self.assertTrue(os.path.isdir(own), "the run's own folder was not made")


if __name__ == "__main__":
    unittest.main()
