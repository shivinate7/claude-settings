#!/usr/bin/env python3
"""Cases for lint/check_mutant_anchors.py. Standard library only.

    python3 lint/test_check_mutant_anchors.py

`merge --lane-lint` runs the check before review. It refuses a mutant whose anchor text is stale
(in no anchor file) or ambiguous (in more than one place), so the defect shows before any suite
runs. The check reuses the pre-check in hooks/mutate_guard.py, so it judges the MUTATIONS table of
the tree that `--root` names.

Each case runs the real script as a subprocess with `--root <fixture>`. The fixture copies hooks/
and bin/sim-lease, and no suite. A green exit therefore proves that no suite ran. The one case that
plants a suite plants a sentinel that writes a marker when run, and asserts the marker is absent.

Output contract for the check: a FAIL exits 1, and each FAIL line names the kind (`ambiguous` or
`stale`) and the mutant's label. A traceback also exits 1, so each FAIL case also asserts that no
traceback was printed.

CHECK_MUTANT_ANCHORS_UNDER_TEST overrides the script path. The red run points it at an always-0 stub.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  the run-folder standard (decision test-temp-standard)
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  copies what git lists, so no fixture lists files (testing/tracked_tree.py)
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
import mutate_guard  # noqa: E402  the MUTATIONS table and TARGETS the check reads
import mutate_shared  # noqa: E402  anchor_files: the modules a guard mutant may be anchored in

MODULE = os.environ.get("CHECK_MUTANT_ANCHORS_UNDER_TEST") or os.path.join(HERE, "check_mutant_anchors.py")
RUN_FOLDER = None

# A guard mutant whose anchor is two lines long, in one guard module.
SSH_PART = "an ssh value flag takes no value"
# A watch mutant: its anchor is one line in config_watch.py, and no other mutant's anchor holds it.
WATCH_PART = "never restore, only report"

SUITE_SENTINEL = '''\
# A stand-in for hooks/test_guard.py. Running it writes a marker, so a check that ran it leaves a trace.
import os

open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "suite_ran.marker"), "w").close()

ANCHOR_COPY = """@ANCHOR@"""
'''


def pick(part):
    """(label, anchor, target) of the one MUTATIONS entry whose label holds `part`."""
    rows = [mutate_guard.mutation_parts(entry)[:4] for entry in mutate_guard.MUTATIONS]
    hits = [(label, old, target) for label, old, _new, target in rows if part in label]
    if len(hits) != 1:
        raise AssertionError("label fragment %r names %d mutants, not 1" % (part, len(hits)))
    return hits[0]


SSH = pick(SSH_PART)
WATCH = pick(WATCH_PART)


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def make_tree(run):
    """A fixture root with the real hooks/ and bin/sim-lease, and no suite (copy_tracked skips test_*)."""
    root = tempfile.mkdtemp(dir=run, prefix="cma_")
    tracked_tree.copy_tracked(root, "hooks")
    os.makedirs(os.path.join(root, "bin"))
    shutil.copyfile(os.path.join(tracked_tree.REPO, "bin", "sim-lease"),
                    os.path.join(root, "bin", "sim-lease"))
    return root


def target_files(root, target):
    """The files the check reads for a mutant of `target`, under the fixture root."""
    if target == "guard":
        return mutate_shared.anchor_files(os.path.join(root, "hooks"))
    real = mutate_guard.TARGETS[target][0]
    return [os.path.join(root, os.path.relpath(real, tracked_tree.REPO))]


def counts(root):
    """[(label, anchor count)] for every mutant, in table order, over the files the check reads for it."""
    texts = {}
    out = []
    for entry in mutate_guard.MUTATIONS:
        label, old, _new, target = mutate_guard.mutation_parts(entry)[:4]
        total = 0
        for path in target_files(root, target):
            if path not in texts:
                texts[path] = read(path)
            total += texts[path].count(old)
        out.append((label, total))
    return out


def run_check(root):
    env = dict(os.environ)
    env.pop("CI", None)
    result = subprocess.run([sys.executable, MODULE, "--root", root], cwd=root, env=env,
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=600)
    return result.returncode, result.stdout + result.stderr


def names(out, label, kind):
    """True when one output line holds both the kind word and the label."""
    return any(label in line and kind in line for line in out.splitlines())


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    if RUN_FOLDER and os.path.isdir(RUN_FOLDER):
        tracked_tree.rm_tree(RUN_FOLDER)  # test-temp-standard: teardown removes the run folder


class MutantAnchorTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(MODULE), "module absent: lint/check_mutant_anchors.py")
        self.root = make_tree(RUN_FOLDER)
        self.addCleanup(tracked_tree.rm_tree, self.root)

    def plant(self, rel, old, new):
        path = os.path.join(self.root, *rel.split("/"))
        text = read(path)
        self.assertIn(old, text, "the anchor is not in %s before the plant" % rel)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text.replace(old, new, 1))

    def assert_planted(self, before, label, want):
        """The plant left this mutant's count at `want`, and moved no other mutant's count."""
        after = counts(self.root)
        self.assertEqual(dict(before)[label], 1, "the anchor was not unique before the plant: %s" % label)
        self.assertEqual(dict(after)[label], want, "the plant left %s at count %s, not %d"
                         % (label, dict(after)[label], want))
        moved = [name for (name, b), (_n, a) in zip(before, after) if a != b]
        self.assertEqual(moved, [label], "the plant moved other mutants' counts too: %s" % moved)

    def test_ambiguous_guard_anchor_fails(self):
        label, old, target = SSH
        self.assertEqual(target, "guard", "the ssh mutant no longer targets the guard modules")
        before = counts(self.root)
        self.plant("hooks/guard_core.py", old, old + "\n" + old)
        self.assert_planted(before, label, 2)
        rc, out = run_check(self.root)
        self.assertEqual(rc, 1, "check passed an ambiguous anchor: exit %d, expected 1" % rc)
        self.assertNotIn("Traceback", out, "check crashed on an ambiguous anchor instead of naming it")
        self.assertTrue(names(out, label, "ambiguous"),
                        "no FAIL line names both 'ambiguous' and the label: %s" % out)

    def test_stale_guard_anchor_fails(self):
        label, old, target = SSH
        self.assertEqual(target, "guard", "the ssh mutant no longer targets the guard modules")
        before = counts(self.root)
        self.plant("hooks/guard_core.py", old, "")
        self.assert_planted(before, label, 0)
        rc, out = run_check(self.root)
        self.assertEqual(rc, 1, "check passed a stale anchor: exit %d, expected 1" % rc)
        self.assertNotIn("Traceback", out, "check crashed on a stale anchor instead of naming it")
        self.assertTrue(names(out, label, "stale"),
                        "no FAIL line names both 'stale' and the label: %s" % out)

    def test_ambiguous_non_guard_anchor_fails(self):
        label, old, target = WATCH
        self.assertEqual(target, "watch", "the watch mutant no longer targets config_watch.py")
        before = counts(self.root)
        self.plant("hooks/config_watch.py", old, old + "\n" + old)
        self.assert_planted(before, label, 2)
        rc, out = run_check(self.root)
        self.assertEqual(rc, 1, "check passed a doubled anchor in a non-guard target: exit %d, expected 1"
                         % rc)
        self.assertNotIn("Traceback", out, "check crashed on a doubled non-guard anchor instead of naming it")
        self.assertTrue(names(out, label, "ambiguous"),
                        "no FAIL line names both 'ambiguous' and the label: %s" % out)

    def test_unchanged_tree_exits_zero(self):
        before = counts(self.root)
        self.assertEqual([name for name, n in before if n != 1], [],
                         "a mutant's anchor is not in its files exactly once on the unchanged tree")
        rc, out = run_check(self.root)
        self.assertEqual(rc, 0, "check failed the unchanged tree: exit %d: %s" % (rc, out))

    def test_anchor_text_in_test_guard_outside_anchor_files_passes(self):
        _label, old, _target = SSH
        hooks = os.path.join(self.root, "hooks")
        suite = os.path.join(hooks, "test_guard.py")
        marker = os.path.join(hooks, "suite_ran.marker")
        with open(suite, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(SUITE_SENTINEL.replace("@ANCHOR@", old))
        self.assertIn(old, read(suite), "the anchor copy did not land in test_guard.py")
        self.assertFalse(os.path.exists(marker), "a marker exists before the run")
        in_anchor_files = sum(read(path).count(old) for path in mutate_shared.anchor_files(hooks))
        self.assertEqual(in_anchor_files, 1, "the anchor is not once in the anchor files: %d" % in_anchor_files)
        rc, out = run_check(self.root)
        self.assertEqual(rc, 0, "check failed on a copy outside the anchor files: exit %d: %s" % (rc, out))
        self.assertFalse(os.path.exists(marker), "the check ran test_guard.py, so a suite ran")


if __name__ == "__main__":
    unittest.main()
