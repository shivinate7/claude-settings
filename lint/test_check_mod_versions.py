#!/usr/bin/env python3
"""Cases for lint/check_mod_versions.py. Standard library only.

    python3 lint/test_check_mod_versions.py

A plugin folder is one under mods/ that has .claude-plugin/plugin.json, or one that
.claude-plugin/marketplace.json lists as a source. If any file in a plugin folder changed against
origin/main (the merge base) and the version in its plugin.json did not increase, the check fails.
A folder with no plugin.json at origin/main is new and passes. Versions are MAJOR.MINOR.PATCH,
compared as numbers. A FAIL line starts "check_mod_versions: FAIL:" and names the folder and both
versions. An unreadable diff or plugin.json exits non-zero, also outside CI.

Each case builds a temp git repo: a copy of the module, the plugins, the marketplace, and a base
commit that sets refs/remotes/origin/main. It runs the real script from that tree.
MOD_VERSIONS_UNDER_TEST overrides the module path.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.environ.get("MOD_VERSIONS_UNDER_TEST") or os.path.join(HERE, "check_mod_versions.py")
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  copies what git lists, so no fixture lists files (testing/tracked_tree.py)
PLUGIN = ".claude-plugin/plugin.json"
MARKET = ".claude-plugin/marketplace.json"
PREFIX = "check_mod_versions: FAIL:"
FAKE = 'Shows "version": "9.9.9", then // and /* and # and a lone quote: Don\'t'


def plugin_json(name, version, description="A test plugin."):
    return json.dumps({"name": name, "version": version, "description": description}, indent=2) + "\n"


def market_json(sources):
    plugins = [{"name": s.rsplit("/", 1)[-1], "source": s} for s in sources]
    return json.dumps({"name": "test-marketplace", "plugins": plugins}, indent=2) + "\n"


def fail_lines(out):
    return [line for line in out.splitlines() if line.startswith(PREFIX)]


def token(text, s):
    """True when s occurs in text as a whole token. mods/alpha is not mods/alpha-2, and 0.1.0 is not 0.1.0-rc."""
    return re.search(r"(?<![\w-])" + re.escape(s) + r"(?![\w-]|\.\d)", text) is not None


class ModVersionTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(MODULE), "module absent: lint/check_mod_versions.py")
        self.fresh_tree()

    def fresh_tree(self):
        self.tree = tempfile.mkdtemp(prefix="mvg_")
        self.addCleanup(tracked_tree.rm_tree, self.tree)
        tracked_tree.copy_tracked(self.tree, "lint", "hooks")  # the check's imports, whatever they become
        shutil.copyfile(MODULE, os.path.join(self.tree, "lint", "check_mod_versions.py"))

    def put(self, rel, text="# file\n"):
        path = os.path.join(self.tree, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def plugin_tree(self, folder, name, version, description="A test plugin."):
        self.put(folder + "/" + PLUGIN, plugin_json(name, version, description))
        self.put(folder + "/hooks/x.mjs", "export const x = 1;\n")
        self.put(folder + "/x.test.mjs", "// test\n")
        self.put(folder + "/README.md", "# plugin\n")

    def bump(self, folder, name, version, description="A test plugin."):
        self.put(folder + "/" + PLUGIN, plugin_json(name, version, description))

    def base_files(self, alpha="0.1.0", beta="0.1.0", listed=("./mods/alpha", "./mods/beta")):
        # Two plugins under mods/, and the marketplace that lists them. Nothing is committed yet.
        self.plugin_tree("mods/alpha", "alpha", alpha)
        self.plugin_tree("mods/beta", "beta", beta)
        self.put(MARKET, market_json(listed))

    def commit_base(self, origin=True):
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        if origin:
            self.git("update-ref", "refs/remotes/origin/main", "HEAD")

    def commit_change(self):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "change")

    def git(self, *args):
        subprocess.run(["git", "-C", self.tree, "-c", "user.name=test",
                        "-c", "user.email=test@example.com", "-c", "commit.gpgsign=false", *args],
                       check=True, capture_output=True, text=True)

    def rev(self, ref):
        r = subprocess.run(["git", "-C", self.tree, "rev-parse", ref],
                           check=True, capture_output=True, text=True)
        return r.stdout.strip()

    def lint(self, *args):
        env = dict(os.environ)
        env.pop("CI", None)  # CI would make some failures red and others not; these cases also need non-zero locally
        cmd = [sys.executable, os.path.join(self.tree, "lint", "check_mod_versions.py"), *args]
        r = subprocess.run(cmd, cwd=self.tree, env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        return r.returncode, r.stdout + r.stderr

    def assert_passes(self):
        rc, out = self.lint()
        self.assertEqual(rc, 0, out)
        self.assertEqual(fail_lines(out), [], out)

    def assert_fails(self):
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertNotIn("Traceback", out)
        return out

    def assert_flags(self, out, folder, *versions):
        lines = [line for line in fail_lines(out) if token(line, folder)]
        self.assertTrue(lines, "no FAIL line names %s:\n%s" % (folder, out))
        for v in versions:
            self.assertTrue(any(token(line, v) for line in lines),
                            "version %s not on the FAIL line for %s:\n%s" % (v, folder, out))

    def assert_clear(self, out, folder):
        named = [line for line in fail_lines(out) if token(line, folder)]
        self.assertEqual(named, [], out)

    # Positive controls first: a red case means nothing if the clean case fails.

    def test_bumped_plugin_passes(self):
        self.base_files()
        self.commit_base()
        self.put("mods/alpha/hooks/x.mjs", "export const x = 2;\n")
        self.bump("mods/alpha", "alpha", "0.1.1")
        self.commit_change()
        self.assert_passes()

    def test_double_digit_minor_bump_passes_as_a_number(self):
        # As text, "0.10.0" sorts before "0.9.0". The compare must read each part as a number.
        self.base_files(alpha="0.9.0")
        self.commit_base()
        self.put("mods/alpha/hooks/x.mjs", "export const x = 2;\n")
        self.bump("mods/alpha", "alpha", "0.10.0")
        self.commit_change()
        self.assert_passes()

    def test_new_plugin_folder_passes(self):
        self.base_files()
        self.commit_base()
        self.plugin_tree("mods/gamma", "gamma", "0.1.0")
        self.put(MARKET, market_json(["./mods/alpha", "./mods/beta", "./mods/gamma"]))
        self.commit_change()
        self.assert_passes()

    def test_new_plugin_folder_with_a_valid_semver_passes(self):
        for version in ("0.0.1", "12.3.45"):
            with self.subTest(version=version):
                self.fresh_tree()
                self.base_files()
                self.commit_base()
                self.plugin_tree("mods/gamma", "gamma", version)
                self.put(MARKET, market_json(["./mods/alpha", "./mods/beta", "./mods/gamma"]))
                self.commit_change()
                self.assert_passes()

    def test_new_plugin_folder_with_a_non_semver_version_fails(self):
        # A new folder is not exempt from the version format. "banana" is not MAJOR.MINOR.PATCH.
        self.base_files()
        self.commit_base()
        self.plugin_tree("mods/gamma", "gamma", "banana")
        self.put(MARKET, market_json(["./mods/alpha", "./mods/beta", "./mods/gamma"]))
        self.commit_change()
        out = self.assert_fails()
        self.assert_flags(out, "mods/gamma")

    def test_rename_to_a_new_folder_and_name_with_the_same_version_passes(self):
        # The plugin cache keys by name, so a new name installs fresh. The version need not rise.
        self.base_files()
        self.commit_base()
        shutil.rmtree(os.path.join(self.tree, "mods", "alpha"))
        self.plugin_tree("mods/delta", "delta", "0.1.0")
        self.put(MARKET, market_json(["./mods/beta", "./mods/delta"]))
        self.commit_change()
        self.assert_passes()

    def test_folder_move_that_keeps_the_name_and_version_fails(self):
        # The plugin cache keys by name. The same name at the same version keeps the old installed code.
        self.base_files()
        self.commit_base()
        shutil.rmtree(os.path.join(self.tree, "mods", "alpha"))
        self.plugin_tree("mods/delta", "alpha", "0.1.0")
        self.put(MARKET, market_json(["./mods/beta", "./mods/delta"]))
        self.commit_change()
        out = self.assert_fails()
        self.assert_flags(out, "alpha", "0.1.0")

    def test_folder_move_that_keeps_the_name_and_bumps_the_version_passes(self):
        # Plugins are matched by name, not folder: the same name with a higher version passes.
        self.base_files()
        self.commit_base()
        shutil.rmtree(os.path.join(self.tree, "mods", "alpha"))
        self.plugin_tree("mods/delta", "alpha", "0.1.1")
        self.put(MARKET, market_json(["./mods/beta", "./mods/delta"]))
        self.commit_change()
        self.assert_passes()

    def test_change_outside_plugin_folders_passes(self):
        self.base_files()
        self.commit_base()
        self.put("mods/README.md", "# mods\n")  # under mods/, but not in any plugin folder
        self.put("lint/notes.txt", "x\n")
        self.commit_change()
        self.assert_passes()

    def test_unlisted_folder_outside_mods_is_not_guarded(self):
        self.base_files()
        self.plugin_tree("extras/bar", "bar", "0.1.0")  # has plugin.json, not listed by the marketplace
        self.commit_base()
        self.put("extras/bar/hooks/x.mjs", "export const x = 2;\n")
        self.commit_change()
        self.assert_passes()

    def test_main_moving_ahead_does_not_flag_an_untouched_plugin(self):
        # The diff is origin/main...HEAD, the merge base. origin/main has an unbumped change to alpha
        # that this branch never touches. A two-dot diff would flag alpha. This case must pass.
        self.base_files()
        self.commit_base()
        base = self.rev("HEAD")
        self.put("mods/beta/hooks/x.mjs", "export const x = 2;\n")
        self.bump("mods/beta", "beta", "0.1.1")
        self.commit_change()
        branch = self.rev("HEAD")
        self.git("checkout", "-q", "--detach", base)
        self.put("mods/alpha/hooks/x.mjs", "export const x = 9;\n")
        self.commit_change()
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.git("checkout", "-q", "--detach", branch)
        self.assert_passes()

    def test_json_strings_are_read_as_values_when_the_version_is_bumped(self):
        # The description holds a fake version key and comment openers. The real key must be read.
        self.plugin_tree("mods/alpha", "alpha", "0.1.0", description=FAKE)
        self.plugin_tree("mods/beta", "beta", "0.1.0")
        self.put(MARKET, market_json(["./mods/alpha", "./mods/beta"]))
        self.commit_base()
        self.put("mods/alpha/hooks/x.mjs", "export const x = 2;\n")
        self.bump("mods/alpha", "alpha", "0.1.1", description=FAKE)
        self.commit_change()
        self.assert_passes()

    # Failures: a changed folder with no bump, a lower version, or a plugin.json it cannot read.

    def test_json_strings_are_read_as_values_when_the_version_is_not_bumped(self):
        self.plugin_tree("mods/alpha", "alpha", "0.1.0", description=FAKE)
        self.plugin_tree("mods/beta", "beta", "0.1.0")
        self.put(MARKET, market_json(["./mods/alpha", "./mods/beta"]))
        self.commit_base()
        self.put("mods/alpha/hooks/x.mjs", "export const x = 2;\n")
        self.commit_change()
        out = self.assert_fails()
        self.assert_flags(out, "mods/alpha", "0.1.0")
        self.assertFalse(any(token(line, "9.9.9") for line in fail_lines(out)), out)

    def test_code_change_without_bump_fails(self):
        self.base_files()
        self.commit_base()
        self.put("mods/alpha/hooks/x.mjs", "export const x = 2;\n")
        self.commit_change()
        out = self.assert_fails()
        self.assert_flags(out, "mods/alpha", "0.1.0")
        self.assert_clear(out, "mods/beta")

    def test_test_file_change_without_bump_fails(self):
        self.base_files()
        self.commit_base()
        self.put("mods/alpha/x.test.mjs", "// test changed\n")
        self.commit_change()
        out = self.assert_fails()
        self.assert_flags(out, "mods/alpha", "0.1.0")

    def test_readme_change_without_bump_fails(self):
        self.base_files()
        self.commit_base()
        self.put("mods/alpha/README.md", "# plugin, reworded\n")
        self.commit_change()
        out = self.assert_fails()
        self.assert_flags(out, "mods/alpha", "0.1.0")

    def test_plugin_json_change_without_bump_fails(self):
        # plugin.json itself changed, the version did not. The description reaches the installed copy.
        self.base_files()
        self.commit_base()
        self.bump("mods/alpha", "alpha", "0.1.0", description="A reworded description.")
        self.commit_change()
        out = self.assert_fails()
        self.assert_flags(out, "mods/alpha", "0.1.0")

    def test_version_decrease_fails(self):
        self.base_files(alpha="0.2.0")
        self.commit_base()
        self.put("mods/alpha/hooks/x.mjs", "export const x = 2;\n")
        self.bump("mods/alpha", "alpha", "0.1.0")
        self.commit_change()
        out = self.assert_fails()
        self.assert_flags(out, "mods/alpha", "0.2.0", "0.1.0")

    def test_unreadable_version_fails(self):
        cases = {
            "one part": "1.0",
            "v prefix": "v0.2.0",
            "number, not text": 1,
            "no version key": None,
        }
        for label, value in cases.items():
            with self.subTest(case=label):
                self.fresh_tree()
                self.base_files()
                self.commit_base()
                self.put("mods/alpha/hooks/x.mjs", "export const x = 2;\n")
                if value is None:
                    self.put("mods/alpha/" + PLUGIN, json.dumps({"name": "alpha"}) + "\n")
                else:
                    self.bump("mods/alpha", "alpha", value)
                self.commit_change()
                rc, out = self.lint()
                self.assertNotEqual(rc, 0, out)
                self.assertNotIn("Traceback", out)
                self.assertTrue(token(out, "alpha"), out)

    def test_plugin_json_with_a_utf8_bom_is_read_and_judged(self):
        # The BOM is tolerated: the version after it is read and judged like plain text.
        cases = (
            ("bom at HEAD, bumped", False, True, "0.1.1", True),
            ("bom at HEAD, not bumped", False, True, "0.1.0", False),
            ("bom at base, bumped", True, False, "0.1.1", True),
        )
        for label, base_bom, head_bom, head_version, passes in cases:
            with self.subTest(case=label):
                self.fresh_tree()
                self.base_files()
                if base_bom:
                    self.put("mods/alpha/" + PLUGIN, "﻿" + plugin_json("alpha", "0.1.0"))
                self.commit_base()
                self.put("mods/alpha/hooks/x.mjs", "export const x = 2;\n")
                self.put("mods/alpha/" + PLUGIN,
                         ("﻿" if head_bom else "") + plugin_json("alpha", head_version))
                self.commit_change()
                if passes:
                    self.assert_passes()
                else:
                    out = self.assert_fails()
                    self.assert_flags(out, "mods/alpha", "0.1.0")

    def test_prerelease_version_in_a_changed_folder_fails(self):
        for version in ("0.2.0-rc.1", "1.0.0-beta"):
            with self.subTest(version=version):
                self.fresh_tree()
                self.base_files()
                self.commit_base()
                self.put("mods/alpha/hooks/x.mjs", "export const x = 2;\n")
                self.bump("mods/alpha", "alpha", version)
                self.commit_change()
                out = self.assert_fails()
                self.assert_flags(out, "mods/alpha")

    def test_malformed_head_plugin_json_fails(self):
        self.base_files()
        self.commit_base()
        self.put("mods/alpha/hooks/x.mjs", "export const x = 2;\n")
        self.put("mods/alpha/" + PLUGIN, '{ "name": "alpha", "version": ')
        self.commit_change()
        rc, out = self.lint()
        self.assertNotEqual(rc, 0, out)
        self.assertNotIn("Traceback", out)
        self.assertTrue(token(out, "alpha"), out)

    def test_malformed_base_plugin_json_fails(self):
        # A base plugin.json that is present but unreadable is not "new". The folder is an existing plugin.
        self.base_files()
        self.put("mods/alpha/" + PLUGIN, '{ "name": "alpha", "version": ')
        self.commit_base()
        self.put("mods/alpha/hooks/x.mjs", "export const x = 2;\n")
        self.bump("mods/alpha", "alpha", "0.1.1")
        self.commit_change()
        rc, out = self.lint()
        self.assertNotEqual(rc, 0, out)
        self.assertNotIn("Traceback", out)
        self.assertTrue(token(out, "alpha"), out)

    def test_deleted_plugin_json_fails(self):
        # The folder stays and its plugin.json goes. The guard must not read that as a new plugin.
        self.base_files()
        self.commit_base()
        self.put("mods/alpha/hooks/x.mjs", "export const x = 2;\n")
        self.git("rm", "-q", "mods/alpha/" + PLUGIN)
        self.commit_change()
        rc, out = self.lint()
        self.assertNotEqual(rc, 0, out)
        self.assertNotIn("Traceback", out)
        self.assertTrue(token(out, "alpha"), out)

    def test_only_the_unbumped_plugin_is_flagged(self):
        self.base_files()
        self.commit_base()
        self.put("mods/alpha/hooks/x.mjs", "export const x = 2;\n")
        self.bump("mods/alpha", "alpha", "0.1.1")
        self.put("mods/beta/hooks/x.mjs", "export const x = 2;\n")
        self.commit_change()
        out = self.assert_fails()
        self.assert_clear(out, "mods/alpha")
        self.assert_flags(out, "mods/beta", "0.1.0")

    def test_unlisted_mods_folder_is_still_guarded(self):
        self.base_files()  # the marketplace lists alpha and beta only
        self.plugin_tree("mods/gamma", "gamma", "0.1.0")
        self.commit_base()
        self.put("mods/gamma/hooks/x.mjs", "export const x = 2;\n")
        self.commit_change()
        out = self.assert_fails()
        self.assert_flags(out, "mods/gamma", "0.1.0")

    def test_marketplace_source_outside_mods_is_guarded(self):
        self.base_files(listed=("./mods/alpha", "./mods/beta", "./extras/foo"))
        self.plugin_tree("extras/foo", "foo", "0.1.0")
        self.commit_base()
        self.put("extras/foo/hooks/x.mjs", "export const x = 2;\n")
        self.commit_change()
        out = self.assert_fails()
        self.assert_flags(out, "extras/foo", "0.1.0")

    def test_file_moved_out_of_a_plugin_fails(self):
        # Rename detection would show only the new path. With both paths shown, alpha loses a file.
        body = "".join("line %d of a shared body\n" % i for i in range(20))
        self.base_files()
        self.put("mods/alpha/hooks/moved.mjs", body)
        self.commit_base()
        os.remove(os.path.join(self.tree, "mods", "alpha", "hooks", "moved.mjs"))
        self.put("mods/beta/hooks/moved.mjs", body)
        self.bump("mods/beta", "beta", "0.1.1")
        self.commit_change()
        out = self.assert_fails()
        self.assert_flags(out, "mods/alpha", "0.1.0")
        self.assert_clear(out, "mods/beta")

    def test_non_ascii_file_name_counts(self):
        # Git quotes this path in the default output, so the folder prefix would not match.
        self.base_files()
        self.commit_base()
        self.put("mods/alpha/hooks/caf\u00e9.mjs", "export const c = 1;\n")
        self.commit_change()
        out = self.assert_fails()
        self.assert_flags(out, "mods/alpha", "0.1.0")

    def test_no_origin_main_fails(self):
        self.base_files()
        self.commit_base(origin=False)
        self.put("mods/alpha/hooks/x.mjs", "export const x = 2;\n")
        self.commit_change()
        rc, out = self.lint()
        self.assertNotEqual(rc, 0, out)
        self.assertNotIn("Traceback", out)

    def test_not_a_git_repo_fails(self):
        self.base_files()  # no git init: the diff cannot be read
        rc, out = self.lint()
        self.assertNotEqual(rc, 0, out)
        self.assertNotIn("Traceback", out)


if __name__ == "__main__":
    unittest.main()
