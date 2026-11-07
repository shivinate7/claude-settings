"""Known-defect replay: a defect whose catcher loads no package, under a profile whose install failed.

The catcher runs a suite that imports only the product file it plants in, so the failed install is no reason to distrust
its verdict. The file pins that such a defect reads CAUGHT under a profile whose one install failed: the load hook logs no
missing module for a catcher that loads no package, so the failed install is not what the catcher needs.

The profiles are the real `REPLAY_PROFILES` entries, copied, with every install swapped for FAILING_INSTALL. Their
regexes, argv, classifier and lockfile are read from the copy, never restated here.

The run folder, the fixtures and the runner come from hooks/test_mutate_ci.py, the one home of them.
"""
import copy
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_mutate_ci as ci  # noqa: E402  the one home of the fixtures, the runner and the verdict readers
import mutate_guard  # noqa: E402  REPLAY_PROFILES, the one home of the profiles

LOCK_JSON = '{"lockfileVersion": 3, "packages": {}}\n'

MAILAUDIT_FILES = {
    "check-records.mjs": "export function sumRecords(a, b) {\n  return a + b;\n}\n",
    "test/check-records.test.mjs": ("import { sumRecords } from '../check-records.mjs';\n"
                                    "if (sumRecords(1, 2) !== 3) {\n"
                                    "  console.log('FAIL: sumRecords(1, 2) is not 3');\n"
                                    "  process.exit(1);\n"
                                    "}\n"
                                    "console.log('ok');\n"),
}
JOYOUS_FILES = {
    "src/lib/x.ts": "export function add(a: number, b: number): number {\n  return a + b;\n}\n",
    "tests/x/x.test.ts": ("import { test } from 'node:test';\n"
                          "import assert from 'node:assert/strict';\n"
                          "import { add } from '../../src/lib/x.ts';\n\n"
                          "test('add', () => {\n"
                          "  assert.equal(add(1, 2), 3);\n"
                          "});\n"),
}


def setUpModule():
    ci.setUpModule()


def tearDownModule():
    ci.tearDownModule()


def exposed_profile(name):
    """REPLAY_PROFILES[name], copied, with every install that is not None swapped for FAILING_INSTALL."""
    profile = copy.deepcopy(mutate_guard.REPLAY_PROFILES[name])
    for part in (profile["parts"].values() if "parts" in profile else [profile]):
        if part.get("install") is not None:
            part["install"] = ci.FAILING_INSTALL
    return profile


def node_strips_types():
    try:
        done = subprocess.run(["node", "--experimental-strip-types", "-e", "0"], capture_output=True)
    except OSError:
        return False
    return done.returncode == 0


def replay_one(name, files, suite, file, old, new):
    """Replay one planted defect of profile `name`, its catcher `suite`, in a repository of `files` plus the profile's
    lockfile. The catcher's argv is the profile's, with `{suite}` filled. Returns (exit code, stdout, stderr)."""
    profile = exposed_profile(name)
    argv = [item.replace("{suite}", suite) for item in profile["argv"]]
    repo = ci.new_repo()
    files = dict(files)
    files[profile["lockfile"]] = LOCK_JSON
    ci.put(repo, files)
    ci.commit(repo, "Base: the product file, its catcher and the profile's lockfile")
    entry = dict(ci.defect("kb-exposed-%s" % name, old, new, suite, file=file), argv=argv, classify=profile["classify"])
    return ci.known_run([entry], repo, profile=profile)


class ExposedInstallTests(unittest.TestCase):
    """A defect whose catcher loads no package reads CAUGHT and exits 0 under a profile whose install failed."""

    def test_mailaudit_catcher_with_no_package_reads_caught_though_its_install_failed(self):
        code, out, err = replay_one("mailaudit", MAILAUDIT_FILES, "test/check-records.test.mjs", "check-records.mjs",
                                    "return a + b;", "return a - b;")
        self.assertIn("kb-exposed-mailaudit", ci.verdicts_of(out), "no verdict line (exit %d):\n%s%s" % (code, out, err))
        self.assertEqual(ci.verdicts_of(out), {"kb-exposed-mailaudit": "CAUGHT"},
                         "a catcher that loads no package reads CAUGHT, though the profile's install failed\n" + out + err)
        self.assertEqual(code, 0, "all defects caught must exit 0: exit %d\n%s%s" % (code, out, err))

    def test_joyous_catcher_with_no_package_reads_caught_though_its_install_failed(self):
        if not node_strips_types():
            self.skipTest("node lacks --experimental-strip-types, so the joyous case is skipped")
        code, out, err = replay_one("joyous", JOYOUS_FILES, "tests/x/x.test.ts", "src/lib/x.ts",
                                    "return a + b;", "return a - b;")
        self.assertIn("kb-exposed-joyous", ci.verdicts_of(out), "no verdict line (exit %d):\n%s%s" % (code, out, err))
        self.assertEqual(ci.verdicts_of(out), {"kb-exposed-joyous": "CAUGHT"},
                         "a catcher that loads no package reads CAUGHT, though the profile's install failed\n" + out + err)
        self.assertEqual(code, 0, "all defects caught must exit 0: exit %d\n%s%s" % (code, out, err))


if __name__ == "__main__":
    unittest.main()
