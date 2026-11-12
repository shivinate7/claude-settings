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
  tip          each DELETE call has a gh api read of its branch's tip earlier in the same loop, with no comment
               or quote around the read; a DELETE in a comment is no call
  budget       the delete step reads the request budget with gh api rate_limit before its delete loop, and takes the
               reserve from sweep.py (--budget-reserve), never an inline number; a read in a comment or an echo is no call
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
          reserve=$(python3 actions/branch-sweep/sweep.py --budget-reserve)
          remaining=$(gh api rate_limit --jq .resources.core.remaining)
          args=()
          while IFS= read -r head; do
            if [ -n "$head" ]; then
              args+=(--open-head="$head")
            fi
          done < "$RUNNER_TEMP/open-heads.txt"
          python3 actions/branch-sweep/sweep.py --repo . --default "$DEFAULT_BRANCH" "${args[@]}" > "$RUNNER_TEMP/verdicts.txt"
          while read -r verb name reason; do
            if [ "$verb" = delete ]; then
              if [ "$remaining" -lt "$reserve" ]; then
                echo "budget $remaining below reserve $reserve: stopped"
                break
              fi
              tip=$(gh api "repos/$REPO/git/ref/heads/$name" --jq .object.sha)
              gh api -X DELETE "repos/$REPO/git/refs/heads/$name"
              remaining=$((remaining - 2))
            fi
          done < "$RUNNER_TEMP/verdicts.txt"
"""


TIP_LINE = '              tip=$(gh api "repos/$REPO/git/ref/heads/$name" --jq .object.sha)\n'
DELETE_LINE = '              gh api -X DELETE "repos/$REPO/git/refs/heads/$name"\n'
LOOP_LINE = '          while read -r verb name reason; do\n'
BUDGET_LINE = '          remaining=$(gh api rate_limit --jq .resources.core.remaining)\n'
RESERVE_LINE = '          reserve=$(python3 actions/branch-sweep/sweep.py --budget-reserve)\n'
VERDICT_LOOP_END = '          done < "$RUNNER_TEMP/verdicts.txt"\n'
DELETE_COMPARE = '              if [ "$remaining" -lt "$reserve" ]; then\n'
OLD_READ = '        run: gh api --paginate "repos/$REPO/pulls?state=open&per_page=100" --jq \'.[].head.ref\' > "$RUNNER_TEMP/open-heads.txt"\n'
NEW_READ = ('        run: |\n'
            '          gh api --paginate "repos/$REPO/pulls?state=open&per_page=100" --jq \'.[].head.ref\' > "$RUNNER_TEMP/open-heads.txt"\n'
            '          if [ "$(wc -l < "$RUNNER_TEMP/open-heads.txt")" -gt 0 ]; then echo "open heads listed"; fi\n')


def variant(old, new):
    """GOOD with one edit. The edited text must occur once, so a fixture that drifts fails here, not as a clean read."""
    assert GOOD.count(old) == 1, "fixture edit must match GOOD once: %r" % old
    return GOOD.replace(old, new)


def lint_path(path):
    """The lint's stdout lines for one workflow file. The exit code is not read: a missing lint prints nothing."""
    done = subprocess.run([sys.executable, LINT, "--workflow", path], capture_output=True, text=True, env=ENV)
    return [line for line in done.stdout.splitlines() if line.strip()]


def line_of(text, needle):
    """The 1-based number of the one line of text that holds needle."""
    hits = [n for n, line in enumerate(text.splitlines(), 1) if needle in line]
    assert len(hits) == 1, "needle must name one line: %r" % needle
    return hits[0]


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

    def assertRuleFinding(self, text, rule, msg, line_no=None):
        """A finding of one rule, on line_no when one is given. Scope first: any other rule's finding would make the
        fixture trip more than the rule under test, so that fails before the subject does."""
        lines = self.lint(text)
        findings = [line for line in lines if line != "clean"]
        self.assertEqual([line for line in findings if not line.startswith(rule + ": ")], [],
                         "%s: scope: the fixture trips another rule" % msg)
        where = "" if line_no is None else "line %d: " % line_no
        found = [line for line in findings if line.startswith(rule + ": " + where)]
        place = "" if line_no is None else " on line %d" % line_no
        self.assertTrue(found, "%s: no %s finding%s, got %r" % (msg, rule, place, lines))

    def assertNoRuleFinding(self, text, rule, msg):
        self.assertEqual([line for line in self.lint(text) if line.startswith(rule + ": ")], [], msg)

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

    def test_delete_without_a_tip_read_is_flagged(self):
        self.assertFinding(variant(TIP_LINE, ""), "tip", "a DELETE with no tip read before it in its loop")

    def test_tip_read_after_the_delete_is_flagged(self):
        text = variant(TIP_LINE + DELETE_LINE, DELETE_LINE + TIP_LINE)
        self.assertFinding(text, "tip", "the tip is read after the DELETE, so the DELETE ran unchecked")

    def test_tip_read_outside_the_loop_is_flagged(self):
        text = variant(TIP_LINE, "").replace(LOOP_LINE, TIP_LINE + LOOP_LINE)
        self.assertFinding(text, "tip", "the tip is read before the loop, not in it, so the DELETE in the loop has none")

    def test_commented_out_tip_read_is_flagged(self):
        self.assertFinding(variant(TIP_LINE, "              # " + TIP_LINE.lstrip()), "tip",
                           "a commented-out tip read does not run, so the DELETE has no read before it")

    def test_tip_read_only_in_an_echo_string_is_flagged(self):
        text = variant(TIP_LINE, '              echo "gh api repos/$REPO/git/ref/heads/$name"\n')
        self.assertFinding(text, "tip", "a read named inside an echo string is text, not a call")

    def test_delete_after_a_hash_inside_quotes_is_flagged(self):
        text = variant(TIP_LINE + DELETE_LINE,
                       '              echo "# not a comment"; gh api -X DELETE "repos/$REPO/git/refs/heads/$name"\n')
        self.assertFinding(text, "tip", "a # inside quotes does not hide the DELETE after it in the same line")

    def test_delete_after_a_lone_quote_is_flagged(self):
        text = variant(TIP_LINE + DELETE_LINE,
                       "              echo don't; gh api -X DELETE \"repos/$REPO/git/refs/heads/$name\"\n")
        self.assertFinding(text, "tip", "a lone quote in text does not hide the DELETE after it in the same line")

    def test_delete_on_a_line_after_an_open_quote_is_flagged(self):
        text = variant(TIP_LINE + DELETE_LINE,
                       '              msg="a # opens a quote\n' + DELETE_LINE + '              end"\n')
        self.assertFinding(text, "tip", "a quote left open on one line does not skip the DELETE on the next")

    def test_read_of_one_branch_then_delete_of_another_is_flagged(self):
        # The loop reads the tip of $head, then deletes $name: the read checks a branch the DELETE does not remove.
        text = variant(TIP_LINE, TIP_LINE.replace("$name", "$head"))
        delete_at = text.splitlines().index(DELETE_LINE.rstrip("\n")) + 1
        self.assertRuleFinding(text, "tip", "the loop reads the tip of $head, then deletes $name", delete_at)

    def test_one_line_loop_after_a_block_level_read_is_flagged(self):
        # The block-level read and the DELETE both name $name, so only the one-line loop lacks its own read.
        block_read = '          tip=$(gh api "repos/$REPO/git/ref/heads/$name" --jq .object.sha)\n'
        one_line = '          for name in a b; do gh api -X DELETE "repos/$REPO/git/refs/heads/$name"; done\n'
        text = variant(LOOP_LINE, block_read + one_line + LOOP_LINE)
        at = text.splitlines().index(one_line.rstrip("\n")) + 1
        self.assertRuleFinding(text, "tip", "a one-line loop after a block-level read: its DELETE inherits the read", at)

    def test_one_line_loop_with_its_own_read_is_clean(self):
        one_line = ('          for name in a b; do tip=$(gh api "repos/$REPO/git/ref/heads/$name" --jq .object.sha); '
                    'gh api -X DELETE "repos/$REPO/git/refs/heads/$name"; done\n')
        self.assertClean(variant(LOOP_LINE, one_line + LOOP_LINE),
                         "a one-line loop that reads its own tip before its DELETE is no finding")

    def test_commented_out_delete_is_clean(self):
        text = variant(TIP_LINE + DELETE_LINE,
                       '              # gh api -X DELETE "repos/$REPO/git/refs/heads/$name"\n              echo "$name"\n')
        self.assertClean(text, "a DELETE in a shell comment is no call, so it is no finding")

    def test_missing_budget_read_is_flagged(self):
        self.assertRuleFinding(variant(BUDGET_LINE, ""), "budget", "no gh api rate_limit read before the delete loop")

    def test_budget_read_after_the_loop_is_flagged(self):
        text = variant(BUDGET_LINE, "").replace(VERDICT_LOOP_END, VERDICT_LOOP_END + BUDGET_LINE)
        self.assertRuleFinding(text, "budget", "the budget read comes after the delete loop, so the loop deletes unchecked")

    def test_budget_read_only_in_a_comment_is_flagged(self):
        self.assertRuleFinding(variant(BUDGET_LINE, "          # " + BUDGET_LINE.lstrip()), "budget",
                               "a commented-out budget read does not run")

    def test_budget_read_only_in_an_echo_string_is_flagged(self):
        self.assertRuleFinding(variant(BUDGET_LINE, '          echo "gh api rate_limit"\n'), "budget",
                               "a read named inside an echo string is text, not a call")

    def test_lone_quote_before_the_budget_read_does_not_hide_it(self):
        text = variant(BUDGET_LINE, "          echo don't; " + BUDGET_LINE.lstrip())
        self.assertClean(text, "a lone quote before a real budget read on its line: the read still counts")

    def test_hash_inside_quotes_does_not_hide_the_budget_read(self):
        text = variant(BUDGET_LINE, '          echo "# not a comment"; ' + BUDGET_LINE.lstrip())
        self.assertClean(text, "a # inside quotes is text, so the read after it on the same line still counts")

    def test_budget_read_inside_a_multi_line_string_is_flagged(self):
        text = variant(BUDGET_LINE, "          echo 'start\n" + BUDGET_LINE + "          end'\n")
        self.assertRuleFinding(text, "budget", "a read inside a single-quoted string that spans lines is text, not a call")

    def test_reserve_written_inline_is_flagged(self):
        self.assertRuleFinding(variant(RESERVE_LINE, "          reserve=300\n"), "budget",
                               "the reserve is an inline 300, not read from sweep.py")

    def test_comparison_against_a_literal_is_flagged(self):
        self.assertRuleFinding(variant('"$remaining" -lt "$reserve"', '"$remaining" -lt 300'), "budget",
                               "the delete loop compares against a literal, a copy of the reserve")

    def test_pulls_step_compare_against_a_number_is_clean(self):
        # The open-PR read has no delete, so a number compare there is no copy of the reserve.
        self.assertNoRuleFinding(variant(OLD_READ, NEW_READ), "budget",
                                 "a -gt 0 compare in the pulls step, which has no delete, is a budget finding")

    def test_literal_compare_in_the_delete_block_still_flags_beside_a_pulls_compare(self):
        # Control: the pulls-step compare must not hide the delete loop's literal.
        text = variant(OLD_READ, NEW_READ).replace('"$remaining" -lt "$reserve"', '"$remaining" -lt 300')
        self.assertRuleFinding(text, "budget", "the delete loop compares against 300 beside a pulls-step compare",
                               line_of(text, '"$remaining" -lt 300'))

    def test_arithmetic_compare_against_a_literal_is_flagged(self):
        text = variant(DELETE_COMPARE, '              if (( remaining < 300 )); then\n')
        self.assertRuleFinding(text, "budget", "the delete loop compares with (( )) against 300, a copy of the reserve",
                               line_of(text, "(( remaining < 300 ))"))

    def test_quoted_literal_compare_is_flagged(self):
        text = variant(DELETE_COMPARE, '              if [ "$remaining" -lt "300" ]; then\n')
        self.assertRuleFinding(text, "budget", "the delete loop compares against a quoted 300, a copy of the reserve",
                               line_of(text, '-lt "300"'))

    def test_arithmetic_compare_with_the_number_on_the_left_is_flagged(self):
        text = variant(DELETE_COMPARE, '              if (( 300 > remaining )); then\n')
        self.assertRuleFinding(text, "budget", "the delete loop compares with (( )) and 300 on the left, a copy of the reserve",
                               line_of(text, "(( 300 > remaining ))"))

    def test_arithmetic_compare_against_the_reserve_is_clean(self):
        # Control: the reserve is read from sweep.py, so no literal is compared.
        self.assertNoRuleFinding(variant(DELETE_COMPARE, '              if (( remaining < reserve )); then\n'), "budget",
                                 "an arithmetic compare against the reserve variable is a budget finding")

    def test_literal_in_a_quoted_echo_is_clean(self):
        # Control: a quoted string is text, not a compare.
        text = variant(DELETE_COMPARE, DELETE_COMPARE + '              echo "-lt 300 is a literal compare"\n')
        self.assertNoRuleFinding(text, "budget", "a -lt 300 inside an echo string is a budget finding")

    def test_literal_in_a_shell_comment_is_clean(self):
        # Control: a shell comment is no command.
        text = variant(DELETE_COMPARE, DELETE_COMPARE + '              # if [ "$remaining" -lt 300 ]; then\n')
        self.assertNoRuleFinding(text, "budget", "a -lt 300 in a shell comment is a budget finding")


def tearDownModule():
    if os.path.isdir(RUN_FOLDER):
        tracked_tree.rm_tree(RUN_FOLDER)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main()
