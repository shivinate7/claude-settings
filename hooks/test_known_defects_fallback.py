"""Known-defect replay: a catcher with an import fallback, in a profile of parts.

Part `oracle` installs and claims the planted defect by its `code` regex. Part `extra` fails to install and claims nothing
the defect touches. The catcher imports a module only `extra`'s install would provide, under `try/except ImportError`, and
falls back to an assertion on the plant. The fallback catches the plant, so the replay must not read CAUGHT: the defect
needs part `extra`, which failed, and the UNKNOWN reason names both the module and part `extra`.

The run folder, the fixtures and the runner come from hooks/test_mutate_ci.py, the one home of them. Its cases cover the
single-profile fallback. These cover the cross-part fallback, a green control, and where a catcher run's log lives.
"""
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_mutate_ci as ci  # noqa: E402  the one home of the fixtures, the runner and the verdict readers

CATCHER = "test_cross.py"
NODE_CATCHER = "test_cross.mjs"
NODE_CALC = "export function add(a, b) {\n  return a + b;\n}\n"
MISSING_PY = "kb_extra_only"  # a module only part extra's install would provide
MISSING_NODE = "kb-missing-pkg"  # a package only part extra's install would provide

# The fallback expects 3 when kb_extra_only is missing. The plant makes add(1, 2) return -1, so the fallback catches it.
FALLBACK_CATCHER = ("import sys\n"
                    "from calc import add\n\n"
                    "try:\n"
                    "    import kb_extra_only\n"
                    "    expected = kb_extra_only.add(1, 2)\n"
                    "except ImportError:\n"
                    "    expected = 3\n"
                    "if add(1, 2) != expected:\n"
                    "    print('FAIL: add(1, 2) is not %d' % expected)\n"
                    "    sys.exit(1)\n"
                    "print('ok')\n")
NODE_FALLBACK_CATCHER = ("import { add } from './calc.mjs';\n"
                         "try {\n"
                         "  await import('kb-missing-pkg');\n"
                         "} catch {\n"
                         "  // the package is absent, so only the plant is checked below\n"
                         "}\n"
                         "if (add(1, 2) !== 3) {\n"
                         "  console.log('FAIL: add(1, 2) is not 3');\n"
                         "  process.exit(1);\n"
                         "}\n"
                         "console.log('ok');\n")


def probe_catcher(sidecar):
    """A catcher that appends the log path the replay gave this run to `sidecar`, then asserts on the plant."""
    return ("import os\n"
            "import sys\n"
            "from calc import add\n\n"
            "with open(%r, 'a', encoding='utf-8') as handle:\n"
            "    handle.write(os.environ.get('MUTATE_MISSING_LOG', '') + '\\n')\n"
            "if add(1, 2) != 3:\n"
            "    print('FAIL: add(1, 2) is not 3')\n"
            "    sys.exit(1)\n"
            "print('ok')\n") % (sidecar,)


def cross_part_profile(extra_install):
    """Part oracle installs ORACLE_INSTALL and claims calc by its code regex. Part extra installs `extra_install` and claims
    nothing: its code regex matches no calc file and its tests regex matches no catcher."""
    return {"parts": {
        "oracle": {"install": ci.ORACLE_INSTALL, "lockfile": ci.ROOT_LOCK, "code": r"^calc\.(?:py|mjs)$"},
        "extra": {"install": extra_install, "lockfile": ci.APP_LOCK, "code": r"^app/", "tests": r"^app/test_"},
    }}


def python_repo(catcher):
    """defect_repo, with `catcher` as CATCHER and both parts' lockfiles committed."""
    return ci.defect_repo(extra_files={CATCHER: catcher, ci.ROOT_LOCK: ci.LOCK_TEXT, ci.APP_LOCK: ci.LOCK_TEXT})


def node_repo():
    """calc.mjs, the Node fallback catcher and both parts' lockfiles, committed on main."""
    repo = ci.new_repo()
    ci.put(repo, {"calc.mjs": NODE_CALC, NODE_CATCHER: NODE_FALLBACK_CATCHER,
                  ci.ROOT_LOCK: ci.LOCK_TEXT, ci.APP_LOCK: ci.LOCK_TEXT})
    ci.commit(repo, "Base: the module, its catcher and both lockfiles")
    return repo


def lines_of(path):
    if not os.path.isfile(path):
        raise AssertionError("no catcher run wrote %s" % path)
    with open(path, encoding="utf-8") as handle:
        return handle.read().splitlines()


def setUpModule():
    ci.setUpModule()


def tearDownModule():
    ci.tearDownModule()


class CrossPartFallbackTests(unittest.TestCase):
    """A catcher whose fallback reads a module of a failed part, and the log its runs leave in the replay's temp folder."""

    def assert_unknown_naming_module_and_part(self, code, out, err, defect_id, module):
        self.assertIn(defect_id, ci.verdicts_of(out), "no verdict line for %s (exit %d):\n%s%s" % (defect_id, code, out, err))
        self.assertEqual(ci.verdicts_of(out)[defect_id], "UNKNOWN",
                         "a catcher that imports a module of a failed install reads UNKNOWN, never CAUGHT\n" + out + err)
        line = [text for text in out.splitlines() if text.startswith("UNKNOWN %s:" % defect_id)]
        self.assertEqual(len(line), 1, "one UNKNOWN line for %s:\n%s%s" % (defect_id, out, err))
        self.assertIn(module, line[0], "the UNKNOWN reason must name the module the catcher imported: " + line[0])
        self.assertIn("part extra", line[0], "the UNKNOWN reason must name the failed install of part extra: " + line[0])
        self.assertEqual(code, 1, "UNKNOWN exits 1: exit %d\n%s%s" % (code, out, err))

    def test_a_python_fallback_reads_unknown_when_its_module_belongs_to_the_failed_part(self):
        repo = python_repo(FALLBACK_CATCHER)
        defects = [ci.defect("kb-fb-py", "return a + b", "return a - b", CATCHER, file="calc.py")]
        code, out, err = ci.known_run(defects, repo, profile=cross_part_profile(ci.FAILING_INSTALL))
        self.assert_unknown_naming_module_and_part(code, out, err, "kb-fb-py", MISSING_PY)

    def test_the_same_fallback_reads_caught_when_every_install_passed(self):
        # The green control: with no install failed, the module is still missing, and the log changes no verdict.
        repo = python_repo(FALLBACK_CATCHER)
        defects = [ci.defect("kb-fb-ok", "return a + b", "return a - b", CATCHER, file="calc.py")]
        code, out, err = ci.known_run(defects, repo, profile=cross_part_profile(ci.PASSING_INSTALL))
        self.assertEqual(ci.verdicts_of(out), {"kb-fb-ok": "CAUGHT"},
                         "with every install passing, the fallback catches the plant and reads CAUGHT\n" + out + err)
        self.assertEqual(code, 0, "all defects caught must exit 0: exit %d\n%s%s" % (code, out, err))

    def test_a_node_fallback_reads_unknown_when_its_package_belongs_to_the_failed_part(self):
        repo = node_repo()
        defects = [dict(ci.defect("kb-fb-node", "return a + b", "return a - b", NODE_CATCHER, file="calc.mjs"),
                        argv=["node", NODE_CATCHER])]
        code, out, err = ci.known_run(defects, repo, profile=cross_part_profile(ci.FAILING_INSTALL))
        self.assert_unknown_naming_module_and_part(code, out, err, "kb-fb-node", MISSING_NODE)

    def test_the_import_log_lives_only_under_the_replay_temp_folder_and_is_removed(self):
        sidecar = os.path.join(ci.fresh(), "log_paths.txt")
        temp = ci.fresh()
        repo = python_repo(probe_catcher(sidecar))
        defects = [ci.defect("kb-fb-cost", "return a + b", "return a - b", CATCHER, file="calc.py")]
        before = (ci.state_of(repo), ci.tree_of(repo))
        with mock.patch.dict(os.environ, {"TMPDIR": temp}):
            code, out, err = ci.known_run(defects, repo, profile=cross_part_profile(ci.FAILING_INSTALL))
        self.assertEqual(ci.verdicts_of(out), {"kb-fb-cost": "CAUGHT"},
                         "the probe catcher runs and catches the plant\n" + out + err)
        self.assertEqual(code, 0, "all defects caught must exit 0: exit %d\n%s%s" % (code, out, err))
        paths = lines_of(sidecar)
        self.assertEqual(len(paths), 2, "the clean and the planted catcher run each log one path: %s" % paths)
        for path in paths:
            self.assertTrue(path, "the catcher was given no MUTATE_MISSING_LOG path, so its run logs no missing module")
            self.assertTrue(os.path.isabs(path), "the log path is not absolute: %s" % path)
            self.assertEqual(os.path.commonpath([path, temp]), temp,
                             "the log %s is outside the replay temp folder %s" % (path, temp))
            folders = os.path.relpath(path, temp).split(os.sep)[:-1]
            self.assertTrue(any(name.startswith("mutate_defects_") for name in folders),
                            "the log %s is not inside the replay's own folder" % path)
            self.assertFalse(os.path.exists(path), "the log %s survives its run" % path)
        self.assertEqual(os.listdir(temp), [], "the temp folder holds files after the run: %s" % os.listdir(temp))
        self.assertEqual((ci.state_of(repo), ci.tree_of(repo)), before,
                         "the run wrote into the repository, its worktrees, branches, status or HEAD")


if __name__ == "__main__":
    unittest.main()
