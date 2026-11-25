#!/usr/bin/env python3
"""Cases for the list-lines check, lint/check_list_lines.py (decision lists-one-line-per-item). Run:
`python3 lint/test_check_list_lines.py`.

The check is not built yet. Each case asserts first that the file exists, with its claim in the message, so every
case fails on that one named cause until the builder lands it. Each case drives the check's CLI as a child process,
never an import. Fixtures are git repos in this run's folder: a base commit, then a head commit that adds the item.

Pinned for the builder (the cases build to these):
- CLI: `python3 lint/check_list_lines.py --root DIR --base REF` judges the lists the head of DIR adds an item to,
  against REF. Exit 0 passes. Exit 1 refuses and prints one failure line per refusal.
- Crowded: more than 8 items in the head. A crowded list that the change adds an item to holds one item per line.
  Where order cannot matter (Python import names, set literals, shell case alternatives) it is also sorted. An
  ordered list (a list, a tuple, dict keys) is never sorted by the check or by --fix.
- Failure line for a crowded line: `<path>:<line>: list-lines: <n> items on one line, and this change adds one.
  Rule: claude-settings decision lists-one-line-per-item. Fix: python3 ~/.claude/lint/check_list_lines.py --fix <path>`.
  <line> is the 1-based line in the head; <n> is the items on that line in the head.
- Shell arm: alternatives one per line, each but the last ending in `|\`. The last alternative ends in `)`, and the
  action starts on the next line. The spec's form with `)` alone on a line is a syntax error in bash and in sh, so
  the cases pin `zulu)`. Sort-cause failure text is not in the spec: the cases pin that it names "not sorted".
- Keep marker: a comment `list-lines-ok: <reason>` on the line above the list (above the `case` line for a shell arm).
  The reason must be non-empty; the bare-marker failure text is not in the spec: the cases pin that it names
  "list-lines-ok" and "reason". A marker on a list that is not crowded is refused: the cases pin that it names
  "list-lines-ok".
- --fix reflows a crowded list one item per line; a Python AST is unchanged by a reflow; a shell arm comes out one
  alternative per line, sorted, and `sh -n` and `bash -n` accept it.
- Base not in the clone: prints `unknown: base <REF> not in this clone` and `git fetch origin <REF>`. Exit 0 locally,
  exit 1 when env CI is set.
- A language with no reader prints one `not read: <language>` line and exits 0. Language names are the row names of
  lint/code_check_standard.json (JSON has no row; Swift has one).
- Dark switch: `--list-lines` on actions/code-check/code_check.py main(), off by default. Its two cases live in
  actions/code-check/test_action.py, class CodeCheck: test_list_lines_switch_off_runs_no_judgment (a control) and
  test_list_lines_switch_on_refuses_crowded_shell_arm.
"""
import ast
import contextlib
import os
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  the one home of the run folder and its sweep (lint/_test_temp.py)

CHECK = os.path.join(REPO, "lint", "check_list_lines.py")
CHECK_REL = "lint/check_list_lines.py"
RULE = "lists-one-line-per-item"
TIMEOUT = 120  # hang guard: each case runs in well under a second
MISSING_BASE = "no-such-base"  # a ref that no clone holds
RUN = ""  # this run's folder, made in setUpModule and removed in tearDownModule
ISOLATED = None  # CLAUDE_CONFIG_DIR points under RUN for the whole run, so no case reads the real ~/.claude

ITEMS_19 = ["item%02d" % n for n in range(1, 20)]
ITEMS_20 = ["item%02d" % n for n in range(1, 21)]
NAMES_9 = ", ".join('"n%d"' % n for n in range(1, 10))
NAMES_10 = ", ".join('"n%d"' % n for n in range(1, 11))
ORDER_9 = ["zeta", "alpha", "mu", "beta", "omega", "delta", "pi", "gamma", "rho"]  # unsorted: order matters
ARM_SH = '#!/bin/sh\ncase "$1" in\n  %s) echo hit ;;\n  *) echo miss ;;\nesac\n'


def setUpModule():
    global RUN, ISOLATED
    RUN = _test_temp.run_folder()
    ISOLATED = contextlib.ExitStack()
    ISOLATED.enter_context(_test_temp.isolated_config(RUN))


def tearDownModule():
    ISOLATED.close()
    shutil.rmtree(RUN, ignore_errors=True)


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                   capture_output=True, text=True, timeout=TIMEOUT)


def head_sha(cwd):
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, check=True,
                          timeout=TIMEOUT).stdout.strip()


def put(root, files):
    for name, text in files.items():
        path = os.path.join(root, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)


def make_repo(name, base, head):
    """A git repo in this run's folder: `base` committed, then `head` written in full on top. Returns (root, base sha)."""
    root = os.path.join(RUN, name)
    os.makedirs(root)
    git(root, "init", "-q", "-b", "main")
    put(root, base)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    base_sha = head_sha(root)
    put(root, head)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "head")
    return root, base_sha


def run_check(root, base, *extra, ci=False):
    """Run the check on `root` against `base`. CI and GITHUB_ACTIONS are stripped from the child env, so only ci=True sets CI."""
    env = dict(os.environ)
    for name in ("CI", "GITHUB_ACTIONS"):
        env.pop(name, None)
    if ci:
        env["CI"] = "true"
    done = subprocess.run([sys.executable, CHECK, "--root", root, "--base", base, *extra], cwd=root,
                          capture_output=True, text=True, env=env, timeout=TIMEOUT)
    return done.returncode, done.stdout + done.stderr


def failure_line(path, line, count):
    return ("%s:%d: list-lines: %d items on one line, and this change adds one. Rule: claude-settings decision %s. "
            "Fix: python3 ~/.claude/lint/check_list_lines.py --fix %s" % (path, line, count, RULE, path))


def arm_per_line(items):
    """A shell case arm with one alternative per line, joined with `|\\`, the `)` on the last alternative."""
    body = "".join("  %s|\\\n" % item for item in items[:-1])
    return '#!/bin/sh\ncase "$1" in\n%s  %s)\n    echo hit ;;\n  *) echo miss ;;\nesac\n' % (body, items[-1])


def arm(items):
    return ARM_SH % "|".join(items)


def arm_items(lines, start):
    """(alternatives, the arm's last line index) read from the one-per-line form that starts after the `case` line."""
    items, i = [], start + 1
    while not lines[i].strip().endswith(")"):
        items.append(lines[i].strip()[:-2])
        i += 1
    items.append(lines[i].strip()[:-1])
    return items, i


class ListLinesCase(unittest.TestCase):
    def repo(self, claim, base, head):
        """(root, base sha) for a fixture. Asserts the check is built first: until it is, every case fails here, on its claim."""
        if not os.path.isfile(CHECK):
            self.fail("%s is not built: %s" % (CHECK_REL, claim))
        return make_repo(self._testMethodName, base, head)

    def judge(self, claim, base, head, *extra, ci=False, ref=None):
        """Run the check on a fixture. `ref` names the base outright (a ref no clone holds, for the unknown cases)."""
        root, sha = self.repo(claim, base, head)
        return run_check(root, ref or sha, *extra, ci=ci)

    # Refused

    def test_crowded_shell_arm_with_added_alternative_is_refused(self):
        rc, out = self.judge("a crowded shell case arm that gains an alternative is refused",
                             {"scripts/arm.sh": arm(ITEMS_19)}, {"scripts/arm.sh": arm(ITEMS_20)})
        self.assertNotEqual(rc, 0, "the crowded shell arm passed: exit 0, output %r" % out)
        self.assertIn(failure_line("scripts/arm.sh", 3, 20), out,
                      "no failure line in the spec's form for the crowded shell arm: %r" % out)

    def test_crowded_python_import_tuple_with_added_name_is_refused(self):
        base = {"scripts/imports.py": "from names_mod import (\n    ALPHA, BRAVO, CHARLIE, DELTA,\n    ECHO, FOXTROT, GOLF, HOTEL,\n"
                                      "    INDIA, JULIET,\n)\n"}
        head = {"scripts/imports.py": "from names_mod import (\n    ALPHA, BRAVO, CHARLIE, DELTA,\n    ECHO, FOXTROT, GOLF, HOTEL,\n"
                                      "    INDIA, JULIET, KILO,\n)\n"}
        rc, out = self.judge("a crowded Python import tuple that gains a name is refused", base, head)
        self.assertNotEqual(rc, 0, "the crowded import tuple passed: exit 0, output %r" % out)
        self.assertIn("scripts/imports.py:", out, "no failure line names the import tuple's file: %r" % out)
        self.assertIn(RULE, out, "the failure does not name decision %s: %r" % (RULE, out))

    def test_unsorted_one_per_line_shell_arm_with_added_item_is_refused(self):
        base_items = ["item05", "item02", "item09", "item01", "item07", "item03", "item10", "item08", "item04", "item06"]
        head_items = base_items[:3] + ["item11"] + base_items[3:]
        rc, out = self.judge("an unsorted shell arm, already one per line, that gains an item is refused",
                             {"scripts/arm.sh": arm_per_line(base_items)}, {"scripts/arm.sh": arm_per_line(head_items)})
        self.assertNotEqual(rc, 0, "the unsorted arm passed: exit 0, output %r" % out)
        self.assertIn("not sorted", out, "the unsorted arm is not refused for its order: %r" % out)
        self.assertNotIn("items on one line", out, "the arm is one per line, so the one-line cause must not fire: %r" % out)

    def test_keep_marker_without_reason_is_refused(self):
        rc, out = self.judge("a keep marker with no reason is refused, even on a crowded list",
                             {"scripts/names.py": "# list-lines-ok:\nNAMES = (%s)\n" % NAMES_9},
                             {"scripts/names.py": "# list-lines-ok:\nNAMES = (%s)\n" % NAMES_10})
        self.assertNotEqual(rc, 0, "a bare keep marker passed: exit 0, output %r" % out)
        self.assertIn("list-lines-ok", out, "the bare keep marker is not named in the failure: %r" % out)
        self.assertIn("reason", out, "the failure does not say the marker has no reason: %r" % out)

    def test_keep_marker_on_uncrowded_list_is_refused(self):
        rc, out = self.judge("a keep marker on a list that is not crowded is refused",
                             {"scripts/pair.py": 'PAIR = ("x", "y")\n'},
                             {"scripts/pair.py": '# list-lines-ok: kept as a pair\nPAIR = ("x", "y", "z")\n'})
        self.assertNotEqual(rc, 0, "a keep marker on an uncrowded list passed: exit 0, output %r" % out)
        self.assertIn("list-lines-ok", out, "the uncrowded keep marker is not named in the failure: %r" % out)

    def test_comment_opener_inside_string_is_not_a_keep_marker(self):
        marker = '"# list-lines-ok: not a marker"'
        base = {"scripts/names.py": "NAMES = (%s)\n" % ", ".join([marker] + ['"n%d"' % n for n in range(1, 8)])}
        head = {"scripts/names.py": "NAMES = (%s)\n" % ", ".join([marker] + ['"n%d"' % n for n in range(1, 9)])}
        rc, out = self.judge("a comment opener inside a string is not a keep marker", base, head)
        self.assertNotEqual(rc, 0, "the string holding marker text passed as a keep marker: exit 0, output %r" % out)
        self.assertIn(RULE, out, "the failure does not name decision %s: %r" % (RULE, out))

    def test_quoted_hash_in_crowded_shell_arm_is_not_a_comment(self):
        base = {"scripts/arm.sh": '#!/bin/sh\ncase "$1" in\n  "#a"|b|c|d|e|f|g|h|i) echo hit ;;\n  *) echo miss ;;\nesac\n'}
        head = {"scripts/arm.sh": '#!/bin/sh\ncase "$1" in\n  "#a"|b|c|d|e|f|g|h|i|j) echo hit ;;\n  *) echo miss ;;\nesac\n'}
        rc, out = self.judge("a # inside quotes in a crowded shell arm does not hide the arm", base, head)
        self.assertNotEqual(rc, 0, "the crowded arm with a quoted # passed: exit 0, output %r" % out)
        self.assertIn(RULE, out, "the failure does not name decision %s: %r" % (RULE, out))

    def test_lone_apostrophe_in_shell_comment_does_not_hide_later_arm(self):
        base = {"scripts/arm.sh": "#!/bin/sh\n# don't edit this list by hand\ncase \"$1\" in\n  %s) echo hit ;;\n"
                                  "  *) echo miss ;;\nesac\n" % "|".join(ITEMS_19)}
        head = {"scripts/arm.sh": "#!/bin/sh\n# don't edit this list by hand\ncase \"$1\" in\n  %s) echo hit ;;\n"
                                  "  *) echo miss ;;\nesac\n" % "|".join(ITEMS_20)}
        rc, out = self.judge("a lone apostrophe in a shell comment does not hide a crowded arm below it", base, head)
        self.assertNotEqual(rc, 0, "the arm below a lone apostrophe passed: exit 0, output %r" % out)
        self.assertIn(failure_line("scripts/arm.sh", 4, 20), out, "no failure line for the arm below the comment: %r" % out)

    # Passes

    def test_three_item_tuple_with_added_item_passes(self):
        rc, out = self.judge("a 3-item tuple that gains an item passes (4 items, not crowded)",
                             {"scripts/items.py": 'ITEMS = ("alpha", "bravo", "charlie")\n'},
                             {"scripts/items.py": 'ITEMS = ("alpha", "bravo", "charlie", "delta")\n'})
        self.assertEqual(rc, 0, "a 4-item tuple was refused: exit %d, output %r" % (rc, out))

    def test_crowded_list_the_change_does_not_touch_passes(self):
        rc, out = self.judge("a crowded list the change does not touch passes",
                             {"scripts/table.py": "TABLE = (%s)\nVERSION = 1\n" % NAMES_10},
                             {"scripts/table.py": "TABLE = (%s)\nVERSION = 2\n" % NAMES_10})
        self.assertEqual(rc, 0, "an untouched crowded list was judged: exit %d, output %r" % (rc, out))

    def test_added_item_to_ordered_one_per_line_list_passes(self):
        base = 'ORDER = [\n' + "".join('    "%s",\n' % v for v in ORDER_9) + ']\n'
        head = 'ORDER = [\n' + "".join('    "%s",\n' % v for v in ORDER_9 + ["chi"]) + ']\n'
        rc, out = self.judge("an added item to an ordered list, one per line and unsorted, passes", {"scripts/order.py": base},
                             {"scripts/order.py": head})
        self.assertEqual(rc, 0, "an ordered list was refused or sorted: exit %d, output %r" % (rc, out))

    def test_crowded_list_with_reasoned_keep_marker_passes(self):
        rc, out = self.judge("a crowded list with a keep marker that has a reason passes",
                             {"scripts/names.py": "# list-lines-ok: generated names, order fixed by the loader\nNAMES = (%s)\n" % NAMES_9},
                             {"scripts/names.py": "# list-lines-ok: generated names, order fixed by the loader\nNAMES = (%s)\n" % NAMES_10})
        self.assertEqual(rc, 0, "a reasoned keep marker was refused: exit %d, output %r" % (rc, out))

    def test_removal_only_passes(self):
        rc, out = self.judge("a diff that only removes an item passes",
                             {"scripts/table.py": "TABLE = (%s)\n" % NAMES_10},
                             {"scripts/table.py": "TABLE = (%s)\n" % NAMES_9})
        self.assertEqual(rc, 0, "a removal was refused: exit %d, output %r" % (rc, out))

    # Scanner traps: each must read the text as the language does (building-scanner-respects-strings)

    def test_pipe_and_hash_inside_quotes_in_shell_arm_are_not_separators(self):
        base = {"scripts/arm.sh": '#!/bin/sh\ncase "$1" in\n  "x|y"|"#z"|a|b|c|d|e) echo hit ;;\n  *) echo miss ;;\nesac\n'}
        head = {"scripts/arm.sh": '#!/bin/sh\ncase "$1" in\n  "x|y"|"#z"|a|b|c|d|e|f) echo hit ;;\n  *) echo miss ;;\nesac\n'}
        rc, out = self.judge("| and # inside quotes in a shell arm are not separators: 8 alternatives pass", base, head)
        self.assertEqual(rc, 0, "a quoted | was counted as a separator: exit %d, output %r" % (rc, out))

    def test_here_doc_holding_a_fake_case_is_not_judged(self):
        template = '#!/bin/sh\ncat > "$OUT" <<\'EOF\'\ncase "$1" in\n  %s) echo fake ;;\nEOF\n'
        rc, out = self.judge("a here-doc holding a fake case arm is not judged", {"scripts/gen.sh": template % "|".join(ITEMS_19)},
                             {"scripts/gen.sh": template % "|".join(ITEMS_20)})
        self.assertEqual(rc, 0, "text inside a here-doc was judged as a case arm: exit %d, output %r" % (rc, out))

    def test_python_string_holding_list_text_is_not_a_list(self):
        rc, out = self.judge("a Python string holding list text is not a list",
                             {"scripts/hint.py": 'HINT = "[a, b, c, d, e, f, g, h, i, j]"\n'},
                             {"scripts/hint.py": 'HINT = "[a, b, c, d, e, f, g, h, i, j, k]"\n'})
        self.assertEqual(rc, 0, "a string holding list text was judged as a list: exit %d, output %r" % (rc, out))

    def test_multi_line_quoted_text_holding_case_is_not_judged(self):
        template = "#!/bin/sh\nMSG='first line\ncase \"$1\" in\n  %s) echo fake ;;\n'\necho \"$MSG\"\n"
        rc, out = self.judge("a multi-line quoted string holding a case arm is not judged",
                             {"scripts/msg.sh": template % "|".join(ITEMS_19)}, {"scripts/msg.sh": template % "|".join(ITEMS_20)})
        self.assertEqual(rc, 0, "a multi-line quoted string was judged as a case arm: exit %d, output %r" % (rc, out))

    # Empty state

    def test_diff_touching_no_python_or_shell_file_prints_nothing(self):
        rc, out = self.judge("a diff that touches no Python or shell file prints nothing and passes",
                             {"README.md": "# t\n", "scripts/arm.sh": arm(ITEMS_19)},
                             {"README.md": "# t\n\nmore words\n"})
        self.assertEqual(rc, 0, "a prose-only diff failed: exit %d, output %r" % (rc, out))
        self.assertEqual(out.strip(), "", "a prose-only diff printed output: %r" % out)

    # Languages with no reader

    def test_language_with_no_reader_prints_one_skip_line_and_passes(self):
        rc, out = self.judge("a language with no reader prints one `not read: swift` line and does not fail",
                             {"Sources/names.swift": "let names = [%s]\n" % NAMES_9},
                             {"Sources/names.swift": "let names = [%s]\n" % NAMES_10})
        self.assertEqual(rc, 0, "an unread language failed the run: exit %d, output %r" % (rc, out))
        skips = [line for line in out.splitlines() if "not read: swift" in line]
        self.assertEqual(len(skips), 1, "want one `not read: swift` line, got %d in %r" % (len(skips), out))

    # Base that cannot be read

    def test_unreadable_base_is_unknown_locally_and_names_the_fetch(self):
        rc, out = self.judge("a base not in this clone is unknown and exits 0 with no CI env",
                             {"scripts/arm.sh": arm(ITEMS_19)}, {"scripts/arm.sh": arm(ITEMS_20)}, ref=MISSING_BASE)
        self.assertEqual(rc, 0, "an unknown base failed a local run: exit %d, output %r" % (rc, out))
        self.assertIn("unknown: base %s not in this clone" % MISSING_BASE, out, "no unknown line for the missing base: %r" % out)
        self.assertIn("git fetch origin %s" % MISSING_BASE, out, "the unknown line names no fetch fix: %r" % out)

    def test_unreadable_base_is_red_under_ci(self):
        rc, out = self.judge("a base not in this clone exits non-zero when env CI is set",
                             {"scripts/arm.sh": arm(ITEMS_19)}, {"scripts/arm.sh": arm(ITEMS_20)}, ci=True, ref=MISSING_BASE)
        self.assertNotEqual(rc, 0, "an unknown base passed under CI: exit 0, output %r" % out)
        self.assertIn("unknown: base %s not in this clone" % MISSING_BASE, out, "no unknown line under CI: %r" % out)

    # --fix

    def test_fix_reflow_keeps_python_ast_and_the_check_then_passes(self):
        claim = "--fix reflows a crowded Python list and leaves its AST equal"
        root, sha = self.repo(claim, {"scripts/order.py": "ORDER = (%s)\n" % NAMES_9},
                               {"scripts/order.py": "ORDER = (%s)\n" % NAMES_10})
        path = os.path.join(root, "scripts", "order.py")
        before = open(path, encoding="utf-8").read()
        subprocess.run([sys.executable, CHECK, "--fix", path], cwd=root, capture_output=True, text=True, timeout=TIMEOUT)
        after = open(path, encoding="utf-8").read()
        self.assertEqual(ast.dump(ast.parse(before)), ast.dump(ast.parse(after)), "a reflow changed the Python AST:\n%s" % after)
        per_line = [line.count('"n') for line in after.splitlines()]
        self.assertEqual(sum(per_line), 10, "the reflow lost or kept an item: %r" % after)
        self.assertTrue(all(count <= 1 for count in per_line), "the reflow left two items on one line: %r" % after)
        git(root, "add", "-A")
        git(root, "commit", "-qm", "reflowed")
        rc, out = run_check(root, sha)
        self.assertEqual(rc, 0, "the reflowed file still fails the check: exit %d, output %r" % (rc, out))

    def test_fix_shell_arm_is_one_per_line_sorted_and_still_parses(self):
        claim = "--fix sorts a crowded shell arm one alternative per line, and sh and bash still parse it"
        root, _ = self.repo(claim, {"scripts/arm.sh": arm(ITEMS_19)},
                            {"scripts/arm.sh": arm(list(reversed(ITEMS_20)))})
        path = os.path.join(root, "scripts", "arm.sh")
        subprocess.run([sys.executable, CHECK, "--fix", path], cwd=root, capture_output=True, text=True, timeout=TIMEOUT)
        lines = open(path, encoding="utf-8").read().splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith("case "))
        items, last = arm_items(lines, start)
        self.assertEqual(items, ITEMS_20, "the fixed arm is not the 20 alternatives, sorted: %r" % items)
        self.assertTrue(all(line.strip().endswith("|\\") for line in lines[start + 1:last]),
                        "an alternative line before the last does not end in |\\: %r" % lines[start:last + 2])
        self.assertTrue(lines[last + 1].strip().startswith("echo hit"), "the action is not on its own line: %r" % lines[last:last + 2])
        for shell in ("sh", "bash"):
            syntax = subprocess.run([shell, "-n", path], capture_output=True, text=True, timeout=TIMEOUT)
            self.assertEqual(syntax.returncode, 0, "%s -n rejects the fixed arm: %s" % (shell, syntax.stderr))
            hit = subprocess.run([shell, path, "item07"], capture_output=True, text=True, timeout=TIMEOUT).stdout.strip()
            self.assertEqual(hit, "hit", "%s no longer matches item07 to the arm: %r" % (shell, hit))
            miss = subprocess.run([shell, path, "zz"], capture_output=True, text=True, timeout=TIMEOUT).stdout.strip()
            self.assertEqual(miss, "miss", "%s matches a value outside the arm: %r" % (shell, miss))

    def test_fix_does_not_sort_ordered_list_or_dict_keys(self):
        claim = "--fix keeps the order of an ordered list and of dict keys"
        order_10 = ORDER_9 + ["chi"]
        base = {"scripts/ordered.py": 'ORDER = [%s]\nTABLE = {%s}\n' % (
            ", ".join('"%s"' % v for v in ORDER_9), ", ".join('"%s": %d' % (k, i) for i, k in enumerate(ORDER_9)))}
        head = {"scripts/ordered.py": 'ORDER = [%s]\nTABLE = {%s}\n' % (
            ", ".join('"%s"' % v for v in order_10), ", ".join('"%s": %d' % (k, i) for i, k in enumerate(order_10)))}
        root, _ = self.repo(claim, base, head)
        path = os.path.join(root, "scripts", "ordered.py")
        before = open(path, encoding="utf-8").read()
        subprocess.run([sys.executable, CHECK, "--fix", path], cwd=root, capture_output=True, text=True, timeout=TIMEOUT)
        after = open(path, encoding="utf-8").read()
        self.assertEqual(ast.dump(ast.parse(before)), ast.dump(ast.parse(after)),
                         "--fix changed the order of an ordered list or dict keys:\n%s" % after)


if __name__ == "__main__":
    unittest.main()
