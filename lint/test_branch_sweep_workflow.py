#!/usr/bin/env python3
"""Lint cases for .github/workflows/branch-sweep.yml, the workflow that deletes branches with GitHub's own token.

The lint is lint/check_branch_sweep_workflow.py (the builder's). CLI:
    python3 lint/check_branch_sweep_workflow.py --workflow PATH
It prints `clean` when the workflow passes, else one line per finding: `<rule>: line <n>: <text>`. The rules:
  permissions  only the contents scope is named; the top level is contents read; a job may request contents write
  secrets      no evaluated expression reads the secrets context; the token is github.token
  triggers     only push to main and workflow_dispatch
  pin          each uses: is pinned by a full commit SHA, except a $/ local action
  checkout     each actions/checkout step sets persist-credentials: false
  timeout      each job sets timeout-minutes
The last three are ci-hygiene rules (skills/ci-hygiene, steps 7 to 9).

GitHub does not evaluate an expression in a YAML comment. It does evaluate one in a quoted value, a plain value, or a
run: block, even after a `#` or beside a lone quote.

The cases change one line of a good workflow per case, and the real file is read too. On the old commit the lint does
not exist, so every case reads no verdict.
Run: python3 lint/test_branch_sweep_workflow.py
"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "..")
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
sys.path.insert(0, os.path.join(REPO, "testing"))
import tracked_tree  # noqa: E402  fixture teardown removes the tree (testing/tracked_tree.py)

LINT = os.path.join(HERE, "check_branch_sweep_workflow.py")
WORKFLOW = os.path.join(REPO, ".github", "workflows", "branch-sweep.yml")
ENV = _test_git.apply(dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull))
RUN_FOLDER = _test_temp.run_folder()

GOOD = """name: branch-sweep
on:
  push:
    branches: [main]
  workflow_dispatch:
permissions:
  contents: read
jobs:
  sweep:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@08c6903cd8c0fde910a37f88322edcfb5dd907a8 # v5.0.0
        with:
          fetch-depth: 0
          persist-credentials: false
      - name: Delete the branches the Oct 30 grant allows
        env:
          GH_TOKEN: ${{ github.token }}
          REPO: ${{ github.repository }}
        run: |
          python3 actions/branch-sweep/sweep.py --repo . > verdicts.txt
          while read -r verb name reason; do
            if [ "$verb" = delete ]; then
              gh api -X DELETE "repos/$REPO/git/refs/heads/$name"
            fi
          done < verdicts.txt
"""


def variant(old, new):
    """GOOD with one edit. The edited text must occur once, so a fixture that drifts fails here, not as a clean read."""
    assert GOOD.count(old) == 1, "fixture edit must match GOOD once: %r" % old
    return GOOD.replace(old, new)


def lint_path(path):
    """The lint's stdout lines for one workflow file. The exit code is not read: a missing lint prints nothing."""
    done = subprocess.run([sys.executable, LINT, "--workflow", path], capture_output=True, text=True, env=ENV)
    return [line for line in done.stdout.splitlines() if line.strip()]


class Workflow(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="bswf-", dir=RUN_FOLDER)
        self.addCleanup(tracked_tree.rm_tree, self.root)

    def lint(self, text):
        path = os.path.join(self.root, "branch-sweep.yml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return lint_path(path)

    def assertClean(self, text, msg):
        self.assertEqual(self.lint(text), ["clean"], msg)

    def assertFinding(self, text, rule, msg):
        lines = self.lint(text)
        found = [line for line in lines if line.startswith(rule + ": ")]
        self.assertTrue(found, "%s: want a %s finding, got %r" % (msg, rule, lines))

    def test_contents_write_only_is_clean(self):
        self.assertClean(GOOD, "a workflow that requests only contents is not clean")

    def test_repo_workflow_is_clean(self):
        self.assertEqual(lint_path(WORKFLOW), ["clean"], "the repo's branch-sweep.yml is not clean")

    def test_other_scope_is_flagged(self):
        text = variant("      contents: write\n    steps:", "      contents: write\n      issues: write\n    steps:")
        self.assertFinding(text, "permissions", "a job that requests issues: write")

    def test_top_level_write_all_is_flagged(self):
        self.assertFinding(variant("permissions:\n  contents: read", "permissions: write-all"), "permissions",
                           "a top-level write-all")

    def test_pull_request_trigger_is_flagged(self):
        text = variant("  workflow_dispatch:\n", "  workflow_dispatch:\n  pull_request:\n    types: [opened]\n")
        self.assertFinding(text, "triggers", "a pull_request trigger, which would delete on a pull request's events")

    def test_secrets_expression_is_flagged(self):
        text = variant("GH_TOKEN: ${{ github.token }}", "GH_TOKEN: ${{ secrets.SHIV_GITHUB_TOKEN }}")
        self.assertFinding(text, "secrets", "a personal token read from the secrets context")

    def test_unpinned_action_is_flagged(self):
        text = variant("actions/checkout@08c6903cd8c0fde910a37f88322edcfb5dd907a8 # v5.0.0", "actions/checkout@v5")
        self.assertFinding(text, "pin", "actions/checkout pinned to a tag")

    def test_checkout_keeps_credentials_is_flagged(self):
        self.assertFinding(variant("          persist-credentials: false\n", ""), "checkout",
                           "a checkout that keeps its token")

    def test_job_without_timeout_is_flagged(self):
        self.assertFinding(variant("    timeout-minutes: 10\n", ""), "timeout", "a job with no timeout-minutes")

    def test_hash_inside_quotes_does_not_hide_a_secret(self):
        text = variant("REPO: ${{ github.repository }}", 'REPO: "# ${{ secrets.SHIV_GITHUB_TOKEN }}"')
        self.assertFinding(text, "secrets", "a # inside quotes is text, so the expression is evaluated")

    def test_shell_comment_in_a_run_block_is_still_evaluated(self):
        text = variant("        run: |\n", "        run: |\n          # ${{ secrets.SHIV_GITHUB_TOKEN }}\n")
        self.assertFinding(text, "secrets", "GitHub evaluates an expression in a shell comment of a run block")

    def test_lone_quote_does_not_hide_a_secret(self):
        text = variant("REPO: ${{ github.repository }}", "REPO: don't ${{ secrets.SHIV_GITHUB_TOKEN }}")
        self.assertFinding(text, "secrets", "a lone quote in a plain value does not hide the expression")

    def test_yaml_comment_with_a_secret_is_clean(self):
        text = variant("      - name: Delete", "      # don't read ${{ secrets.SHIV_GITHUB_TOKEN }} here\n      - name: Delete")
        self.assertClean(text, "an expression in a YAML comment is not evaluated, so it is no finding")


def tearDownModule():
    if os.path.isdir(RUN_FOLDER):
        tracked_tree.rm_tree(RUN_FOLDER)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main()
