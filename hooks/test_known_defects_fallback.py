"""Known-defect replay: a catcher with an import fallback, in a profile of parts.

Part `oracle` installs and claims the planted defect by its `code` regex. Part `extra` fails to install and claims nothing
the defect touches. The catcher imports a module only `extra`'s install would provide, under `try/except ImportError`, and
falls back to an assertion on the plant. The fallback catches the plant, so the replay must not read CAUGHT: the defect
needs part `extra`, which failed, and the UNKNOWN reason names both the module and part `extra`.

The run folder, the fixtures and the runner come from hooks/test_mutate_ci.py, the one home of them. Its cases cover the
single-profile fallback. These cover the cross-part fallback, a green control, and where a catcher run's log lives.
LoadHookTests covers the load hook: the runs it must not trust under a failed install, the names it must not log, and
what it costs.
"""
import importlib.util
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


CJS_MODULE = "calc.cjs"
CJS_CALC = "module.exports = { add(a, b) {\n  return a + b;\n} };\n"
CJS_CATCHER = "test_cross.cjs"
CJS_FALLBACK_CATCHER = ("const { add } = require('./calc.cjs');\n"
                        "try {\n"
                        "  require('kb-missing-pkg');\n"
                        "} catch {\n"
                        "  // the package is absent, so only the plant is checked below\n"
                        "}\n"
                        "if (add(1, 2) !== 3) {\n"
                        "  console.log('FAIL: add(1, 2) is not 3');\n"
                        "  process.exit(1);\n"
                        "}\n"
                        "console.log('ok');\n")
PLAIN_CATCHER = ("import sys\n"
                 "from calc import add\n\n"
                 "if add(1, 2) != 3:\n"
                 "    print('FAIL: add(1, 2) is not 3')\n"
                 "    sys.exit(1)\n"
                 "print('ok')\n")
DOTTED_CATCHER = ("import sys\n"
                  "from calc import add\n\n"
                  "try:\n"
                  "    import kb_pkg.sub\n"
                  "    expected = kb_pkg.sub.add(1, 2)\n"
                  "except ImportError:\n"
                  "    expected = 3\n"
                  "if add(1, 2) != expected:\n"
                  "    print('FAIL: add(1, 2) is not %d' % expected)\n"
                  "    sys.exit(1)\n"
                  "print('ok')\n")
STDLIB_FALLBACK_CATCHER = ("import sys\n"
                           "from calc import add\n\n"
                           "try:\n"
                           "    import msvcrt  # Windows only: absent here, and no install provides it\n"
                           "except ImportError:\n"
                           "    pass\n"
                           "if add(1, 2) != 3:\n"
                           "    print('FAIL: add(1, 2) is not 3')\n"
                           "    sys.exit(1)\n"
                           "print('ok')\n")
NODE_RELATIVE_CATCHER = ("import { add } from './calc.mjs';\n"
                         "try {\n"
                         "  await import('./nope.mjs');\n"
                         "} catch {\n"
                         "  // a file of this folder, absent by design: no install provides it\n"
                         "}\n"
                         "if (add(1, 2) !== 3) {\n"
                         "  console.log('FAIL: add(1, 2) is not 3');\n"
                         "  process.exit(1);\n"
                         "}\n"
                         "console.log('ok');\n")
PKG_JSON = '{"name": "kb-present", "version": "1.0.0", "type": "module", "main": "index.mjs"}\n'
PKG_INDEX = "export const value = 1;\n"
# The oracle part's install: a Node package the passing part provides. Its missing subpath is no failed
# install's gap.
PKG_INSTALL = [ci.PY, "-c", ("import pathlib\n"
                             "pkg = pathlib.Path('node_modules', 'kb-present')\n"
                             "pkg.mkdir(parents=True, exist_ok=True)\n"
                             "pkg.joinpath('package.json').write_text(%r, encoding='utf-8')\n"
                             "pkg.joinpath('index.mjs').write_text(%r, encoding='utf-8')\n") % (PKG_JSON, PKG_INDEX)]
NODE_PKG_CATCHER = ("import { add } from './calc.mjs';\n"
                    "try {\n"
                    "  await import('kb-present/missing');\n"
                    "} catch {\n"
                    "  // the package is installed by a part that passed: only its subpath is absent\n"
                    "}\n"
                    "if (add(1, 2) !== 3) {\n"
                    "  console.log('FAIL: add(1, 2) is not 3');\n"
                    "  process.exit(1);\n"
                    "}\n"
                    "console.log('ok');\n")
# Every install passed, so the catcher must run with no load hook: no MUTATE_MISSING_LOG and no hook on PYTHONPATH.
HOOK_PROBE_PY = ("import os\n"
                 "import sys\n"
                 "from calc import add\n\n"
                 "hooked = ['MUTATE_MISSING_LOG'] if 'MUTATE_MISSING_LOG' in os.environ else []\n"
                 "hooked += [entry for entry in os.environ.get('PYTHONPATH', '').split(os.pathsep)\n"
                 "           if entry and os.path.isfile(os.path.join(entry, 'sitecustomize.py'))]\n"
                 "if hooked:\n"
                 "    print('FAIL: the load hook is in the environment: %s' % hooked)\n"
                 "    sys.exit(1)\n"
                 "if add(1, 2) != 3:\n"
                 "    print('FAIL: add(1, 2) is not 3')\n"
                 "    sys.exit(1)\n"
                 "print('ok')\n")
HOOK_PROBE_NODE = ("import { add } from './calc.mjs';\n"
                   "const hooked = [];\n"
                   "if ('MUTATE_MISSING_LOG' in process.env) hooked.push('MUTATE_MISSING_LOG');\n"
                   "if ((process.env.NODE_OPTIONS || '').includes('missing_hook')) hooked.push('NODE_OPTIONS');\n"
                   "if (hooked.length) {\n"
                   "  console.log('FAIL: the load hook is in the environment: ' + hooked.join(', '));\n"
                   "  process.exit(1);\n"
                   "}\n"
                   "if (add(1, 2) !== 3) {\n"
                   "  console.log('FAIL: add(1, 2) is not 3');\n"
                   "  process.exit(1);\n"
                   "}\n"
                   "console.log('ok');\n")
# Counts the catcher's process starts: it appends one line to the counter, then execs the catcher in the same process.
COUNT_WRAPPER = ("import os\n"
                 "import sys\n\n"
                 "with open(sys.argv[1], 'a', encoding='utf-8') as handle:\n"
                 "    handle.write('start\\n')\n"
                 "os.execv(sys.executable, [sys.executable] + sys.argv[2:])\n")


# Appended to the load hook by the first catcher run that finds it unmarked. A rewrite of the hook drops it.
HOOK_MARKER = "# replay marker: the load hook was written once for this replay\n"


def hook_marker_catcher(sidecar):
    """A catcher that appends 'marked' or 'unmarked' to `sidecar` for the load hook it runs under, marks the hook when
    it is unmarked, then asserts on the plant. One replay logs one 'unmarked' and then only 'marked' when the hook is
    written once."""
    return ("import sys\n"
            "import sitecustomize\n"
            "from calc import add\n\n"
            "hook = sitecustomize.__file__\n"
            "with open(hook, encoding='utf-8') as handle:\n"
            "    marked = %r in handle.read()\n"
            "with open(%r, 'a', encoding='utf-8') as handle:\n"
            "    handle.write('marked\\n' if marked else 'unmarked\\n')\n"
            "if not marked:\n"
            "    with open(hook, 'a', encoding='utf-8') as handle:\n"
            "        handle.write(%r)\n"
            "if add(1, 2) != 3:\n"
            "    print('FAIL: add(1, 2) is not 3')\n"
            "    sys.exit(1)\n"
            "print('ok')\n") % (HOOK_MARKER, sidecar, HOOK_MARKER)


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


def cross_part_profile(extra_install, oracle_install=ci.ORACLE_INSTALL):
    """Part oracle installs `oracle_install` (ORACLE_INSTALL by default) and claims calc by its code regex. Part extra
    installs `extra_install` and claims nothing: its code regex matches no calc file and its tests regex matches no
    catcher."""
    return {"parts": {
        "oracle": {"install": oracle_install, "lockfile": ci.ROOT_LOCK, "code": r"^calc\.(?:py|mjs|cjs)$"},
        "extra": {"install": extra_install, "lockfile": ci.APP_LOCK, "code": r"^app/", "tests": r"^app/test_"},
    }}


def python_repo(catcher):
    """defect_repo, with `catcher` as CATCHER and both parts' lockfiles committed."""
    return ci.defect_repo(extra_files={CATCHER: catcher, ci.ROOT_LOCK: ci.LOCK_TEXT, ci.APP_LOCK: ci.LOCK_TEXT})


def repo_with(files):
    """`files` and both parts' lockfiles, committed on main."""
    repo = ci.new_repo()
    ci.put(repo, {**files, ci.ROOT_LOCK: ci.LOCK_TEXT, ci.APP_LOCK: ci.LOCK_TEXT})
    ci.commit(repo, "Base: the module, its catcher and both lockfiles")
    return repo


def node_repo(catcher=NODE_FALLBACK_CATCHER):
    """calc.mjs, `catcher` as NODE_CATCHER, and both parts' lockfiles, committed on main."""
    return repo_with({"calc.mjs": NODE_CALC, NODE_CATCHER: catcher})


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


class LoadHookTests(unittest.TestCase):
    """The load hook of a catcher run under a failed install: the runs it must not trust, the names it keeps out of the
    environment, the cases it must leave CAUGHT, and what it costs."""

    def assert_unknown(self, code, out, err, defect_id, *terms):
        self.assertEqual(ci.verdicts_of(out), {defect_id: "UNKNOWN"},
                         "a run the load hook did not reach reads UNKNOWN under a failed install, never CAUGHT\n"
                         + out + err)
        line = [text for text in out.splitlines() if text.startswith("UNKNOWN %s:" % defect_id)]
        self.assertEqual(len(line), 1, "one UNKNOWN line for %s:\n%s%s" % (defect_id, out, err))
        for term in terms:
            self.assertIn(term, line[0], "the UNKNOWN reason must name %r: %s" % (term, line[0]))
        self.assertEqual(code, 1, "UNKNOWN exits 1: exit %d\n%s%s" % (code, out, err))

    def assert_caught(self, code, out, err, defect_id, why):
        self.assertEqual(ci.verdicts_of(out), {defect_id: "CAUGHT"}, why + "\n" + out + err)
        self.assertEqual(code, 0, "all defects caught must exit 0: exit %d\n%s%s" % (code, out, err))

    def test_a_python_catcher_that_overrides_pythonpath_reads_unknown_when_the_load_hook_did_not_run(self):
        repo = python_repo(FALLBACK_CATCHER)
        defects = [dict(ci.defect("kb-env-py", "return a + b", "return a - b", CATCHER, file="calc.py"),
                        argv=["env", "PYTHONPATH=.", ci.PY, CATCHER])]
        code, out, err = ci.known_run(defects, repo, profile=cross_part_profile(ci.FAILING_INSTALL))
        self.assert_unknown(code, out, err, "kb-env-py", "load hook did not run", "part extra")

    def test_a_node_catcher_that_overrides_node_options_reads_unknown_when_the_load_hook_did_not_run(self):
        repo = node_repo()
        defects = [dict(ci.defect("kb-env-node", "return a + b", "return a - b", NODE_CATCHER, file="calc.mjs"),
                        argv=["env", "NODE_OPTIONS=--max-old-space-size=256", "node", NODE_CATCHER])]
        code, out, err = ci.known_run(defects, repo, profile=cross_part_profile(ci.FAILING_INSTALL))
        self.assert_unknown(code, out, err, "kb-env-node", "load hook did not run", "part extra")

    def test_a_cjs_require_of_a_missing_package_under_a_failed_install_reads_unknown_never_caught(self):
        repo = repo_with({CJS_MODULE: CJS_CALC, CJS_CATCHER: CJS_FALLBACK_CATCHER})
        defects = [dict(ci.defect("kb-cjs", "return a + b", "return a - b", CJS_CATCHER, file=CJS_MODULE),
                        argv=["node", CJS_CATCHER])]
        code, out, err = ci.known_run(defects, repo, profile=cross_part_profile(ci.FAILING_INSTALL))
        self.assert_unknown(code, out, err, "kb-cjs", MISSING_NODE, "part extra")

    def test_a_python_dotted_import_of_a_missing_top_package_reads_unknown_naming_the_package(self):
        # Green on the old code: importing kb_pkg.sub first asks for kb_pkg, which the hook logs by name.
        repo = python_repo(DOTTED_CATCHER)
        defects = [ci.defect("kb-dotted", "return a + b", "return a - b", CATCHER, file="calc.py")]
        code, out, err = ci.known_run(defects, repo, profile=cross_part_profile(ci.FAILING_INSTALL))
        self.assert_unknown(code, out, err, "kb-dotted", "kb_pkg", "part extra")

    def test_the_load_hook_is_absent_from_a_python_catcher_run_when_every_install_passed(self):
        repo = python_repo(HOOK_PROBE_PY)
        defects = [ci.defect("kb-hook-py", "return a + b", "return a - b", CATCHER, file="calc.py")]
        code, out, err = ci.known_run(defects, repo, profile=cross_part_profile(ci.PASSING_INSTALL))
        self.assert_caught(code, out, err, "kb-hook-py",
                           "with every install passing, the catcher's environment carries no load hook")

    def test_the_load_hook_is_absent_from_a_node_catcher_run_when_every_install_passed(self):
        repo = node_repo(HOOK_PROBE_NODE)
        defects = [dict(ci.defect("kb-hook-node", "return a + b", "return a - b", NODE_CATCHER, file="calc.mjs"),
                        argv=["node", NODE_CATCHER])]
        code, out, err = ci.known_run(defects, repo, profile=cross_part_profile(ci.PASSING_INSTALL))
        self.assert_caught(code, out, err, "kb-hook-node",
                           "with every install passing, the catcher's environment carries no load hook")

    def test_a_stdlib_optional_import_under_a_failed_install_reads_caught_because_no_install_owes_it(self):
        # Green pin: the hook skips a standard-library name, so no install is blamed for msvcrt. The scope is checked
        # first: msvcrt is a standard-library name and this platform lacks it, so the catcher takes its fallback. The CI
        # job that runs this file is ubuntu-latest.
        self.assertIn("msvcrt", sys.stdlib_module_names, "msvcrt must be a standard-library name for this pin")
        self.assertIsNone(importlib.util.find_spec("msvcrt"), "msvcrt must be absent here, so the import fails")
        repo = python_repo(STDLIB_FALLBACK_CATCHER)
        defects = [ci.defect("kb-stdlib", "return a + b", "return a - b", CATCHER, file="calc.py")]
        code, out, err = ci.known_run(defects, repo, profile=cross_part_profile(ci.FAILING_INSTALL))
        self.assert_caught(code, out, err, "kb-stdlib", "a standard-library name is no failed install's to provide")

    def test_a_node_relative_import_of_a_missing_file_under_a_failed_install_reads_caught(self):
        # Green pin: a relative specifier is a file of the checkout, not a package, so the hook logs nothing.
        repo = node_repo(NODE_RELATIVE_CATCHER)
        defects = [dict(ci.defect("kb-relative", "return a + b", "return a - b", NODE_CATCHER, file="calc.mjs"),
                        argv=["node", NODE_CATCHER])]
        code, out, err = ci.known_run(defects, repo, profile=cross_part_profile(ci.FAILING_INSTALL))
        self.assert_caught(code, out, err, "kb-relative", "a missing file of the module's own folder is no package")

    def test_a_node_package_present_with_a_missing_subpath_under_a_failed_install_reads_caught(self):
        # Green pin: the package came from a part that passed, so its missing subpath logs nothing.
        repo = node_repo(NODE_PKG_CATCHER)
        defects = [dict(ci.defect("kb-subpath", "return a + b", "return a - b", NODE_CATCHER, file="calc.mjs"),
                        argv=["node", NODE_CATCHER])]
        profile = cross_part_profile(ci.FAILING_INSTALL, oracle_install=PKG_INSTALL)
        code, out, err = ci.known_run(defects, repo, profile=profile)
        self.assert_caught(code, out, err, "kb-subpath",
                           "a present package's missing subpath is no failed install's gap")

    def test_the_load_hook_file_is_written_once_for_two_defects_in_one_replay(self):
        sidecar = os.path.join(ci.fresh(), "hook_marks.txt")
        repo = python_repo(hook_marker_catcher(sidecar))
        defects = [ci.defect("kb-cost-a", "return a + b", "return a - b", CATCHER, file="calc.py"),
                   ci.defect("kb-cost-b", "return a + b", "return a - b", CATCHER, file="calc.py")]
        code, out, err = ci.known_run(defects, repo, profile=cross_part_profile(ci.FAILING_INSTALL))
        self.assertEqual(ci.verdicts_of(out), {"kb-cost-a": "CAUGHT", "kb-cost-b": "CAUGHT"},
                         "the two defects are caught, so the replay ran both:\n" + out + err)
        marks = lines_of(sidecar)
        self.assertEqual(marks, ["unmarked", "marked", "marked", "marked"],
                         "one clean and one planted run per defect, all under one hook: the hook was rewritten between "
                         "runs of one replay, so it was written more than once: %s" % marks)

    def test_a_replay_starts_one_catcher_process_per_clean_and_planted_run(self):
        wrapper = os.path.join(ci.fresh(), "count_starts.py")
        with open(wrapper, "w", encoding="utf-8") as handle:
            handle.write(COUNT_WRAPPER)
        counter = os.path.join(ci.fresh(), "starts.txt")
        repo = python_repo(PLAIN_CATCHER)
        defects = [dict(ci.defect(defect_id, "return a + b", "return a - b", CATCHER, file="calc.py"),
                        argv=[ci.PY, wrapper, counter, CATCHER]) for defect_id in ("kb-count-a", "kb-count-b")]
        code, out, err = ci.known_run(defects, repo, profile=cross_part_profile(ci.FAILING_INSTALL))
        self.assertEqual(ci.verdicts_of(out), {"kb-count-a": "CAUGHT", "kb-count-b": "CAUGHT"},
                         "the two defects are caught, so the replay ran both:\n" + out + err)
        starts = lines_of(counter)
        self.assertEqual(len(starts), 4, "the replay adds no process: one catcher start per clean and planted run, "
                         "two defects, got %d" % len(starts))


if __name__ == "__main__":
    unittest.main()
