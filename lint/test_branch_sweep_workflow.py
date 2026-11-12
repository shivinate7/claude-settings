#!/usr/bin/env python3
"""Lint cases for .github/workflows/branch-sweep.yml, the workflow that deletes branches with GitHub's own token.

The lint is lint/check_branch_sweep_workflow.py (the builder's). CLI:
    python3 lint/check_branch_sweep_workflow.py --workflow PATH
It prints `clean` when the workflow passes, else one line per finding: `<rule>: line <n>: <text>`. The rules:
  permissions  only the contents scope is named; the top level is contents read; a job may request contents write
  secrets      no evaluated expression reads the secrets context; the token is github.token
  triggers     only push to main and workflow_dispatch
  pin          each uses: is pinned by a full commit SHA, except a ./ local action
  checkout     each actions/checkout step sets persist-credentials: false under its with:
  timeout      each job sets timeout-minutes
  read         the open-PR read step cannot fail silently: no || true in its run, no continue-on-error
  injection    no ${{ }} expression inside a run block
  concurrency  a concurrency block is set at the top level
  condition    a job-level if: limits the job to main
  argv         --open-head takes its value as --open-head=VALUE, so a value that starts with - is not an option
pin, checkout and timeout are ci-hygiene rules (skills/ci-hygiene, steps 7 to 9).

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
concurrency:
  group: branch-sweep
  cancel-in-progress: false
jobs:
  sweep:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    if: github.ref == 'refs/heads/main'
    env:
      GH_TOKEN: ${{ github.token }}
      REPO: ${{ github.repository }}
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@08c6903cd8c0fde910a37f88322edcfb5dd907a8 # v5.0.0
        with:
          fetch-depth: 0
          persist-credentials: false
      - name: Read the heads of open pull requests
        run: gh api --paginate "repos/$REPO/pulls?state=open&per_page=100" --jq '.[].head.ref' > "$RUNNER_TEMP/open-heads.txt"
      - name: Delete the branches the Oct 30 grant allows
        env:
          DEFAULT_BRANCH: ${{ github.event.repository.default_branch }}
        run: |
          args=()
          while IFS= read -r head; do
            if [ -n "$head" ]; then
              args+=(--open-head="$head")
            fi
          done < "$RUNNER_TEMP/open-heads.txt"
          python3 actions/branch-sweep/sweep.py --repo . --default "$DEFAULT_BRANCH" "${args[@]}" > "$RUNNER_TEMP/verdicts.txt"
          while read -r verb name reason; do
            if [ "$verb" = delete ]; then
              gh api -X DELETE "repos/$REPO/git/refs/heads/$name"
            fi
          done < "$RUNNER_TEMP/verdicts.txt"
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

    def test_persist_credentials_under_env_is_flagged(self):
        text = variant("        with:\n          fetch-depth: 0\n          persist-credentials: false\n",
                       "        env:\n          persist-credentials: false\n        with:\n          fetch-depth: 0\n")
        self.assertFinding(text, "checkout", "persist-credentials under env:, so checkout keeps its token")

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

    def test_read_step_with_or_true_is_flagged(self):
        text = variant('> "$RUNNER_TEMP/open-heads.txt"\n', '> "$RUNNER_TEMP/open-heads.txt" || true\n')
        self.assertFinding(text, "read", "the open-PR read ends in || true, so a failed read passes")

    def test_read_step_with_or_echo_is_flagged(self):
        text = variant('> "$RUNNER_TEMP/open-heads.txt"\n', '> "$RUNNER_TEMP/open-heads.txt" || echo "the read failed"\n')
        self.assertFinding(text, "read", "the open-PR read ends in || echo, so a failed read passes")

    def test_read_step_with_continue_on_error_is_flagged(self):
        text = variant("      - name: Read the heads of open pull requests\n",
                       "      - name: Read the heads of open pull requests\n        continue-on-error: true\n")
        self.assertFinding(text, "read", "the open-PR read continues on error")

    def test_expression_in_a_run_block_is_flagged_whatever_the_text_around_it(self):
        lines = {
            "a plain echo": 'echo "${{ github.event.head_commit.message }}"',
            "a # inside quotes": 'echo "# ${{ github.event.head_commit.message }}"',
            "a lone quote": "echo don't ${{ github.event.head_commit.message }}",
            "a shell comment": "# ${{ github.event.head_commit.message }}",
        }
        for label, line in lines.items():
            with self.subTest(label):
                text = variant("          args=()\n", "          " + line + "\n          args=()\n")
                self.assertFinding(text, "injection", "%s: the expression is evaluated in the run block" % label)

    def test_yaml_comment_with_an_expression_is_clean(self):
        text = variant("      - name: Delete", "      # echo ${{ github.event.head_commit.message }}\n      - name: Delete")
        self.assertClean(text, "an expression in a YAML comment is not evaluated, so it is no finding")

    def test_missing_concurrency_is_flagged(self):
        text = variant("concurrency:\n  group: branch-sweep\n  cancel-in-progress: false\n", "")
        self.assertFinding(text, "concurrency", "no concurrency block, so two runs can delete the same branches")

    def test_missing_job_condition_is_flagged(self):
        text = variant("    if: github.ref == 'refs/heads/main'\n", "")
        self.assertFinding(text, "condition", "no job-level if:, so the job can run off main")

    def test_split_open_head_argument_is_flagged(self):
        text = variant('args+=(--open-head="$head")', 'args+=(--open-head "$head")')
        self.assertFinding(text, "argv", "--open-head with a separate value: a head named -x reads as an option")


def tearDownModule():
    if os.path.isdir(RUN_FOLDER):
        tracked_tree.rm_tree(RUN_FOLDER)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main()
