# Checks share the clause parser

## The ruling

The checks that read prose by sentence and clause use one module, `lint/_clause.py`. It holds the sentence and clause boundaries and one list for each word class: negators, adverbs, conditionals, reason links, determiners and the cannot-claim phrase forms. It reads text and a mask only. It runs in linear time.

- `lint/report_guard.py` imports it for the cannot-claim check. That check is the only caller today.
- The pre-existing-failure check and the comment narration gloss check are planned callers. Neither is built.
- A domain word list stays with its check: the act tables, the blocker states and the check words belong to the cannot-claim check.

Why: the cannot-claim check carried a regex for each piece of grammar, and each regex cut sentences its own way. A comma-heavy sentence also cost more than its length (note `cannot-claim-comma-sentence-superlinear`).

Protection of the old outcome (one bad edit must break one check, never all of them):

- `lint/test_clause.py` pins each Clause field, and a mutant per field goes red. It runs in all three OS jobs of `.github/workflows/checks.yml`.
- `hooks/mutate_guard.py` scores `lint/_clause.py` in report mode (`REPORT_TARGETS`).
- The import sits at the top of `lint/report_guard.py`, so a broken module fails the guard suites loudly in CI.
- `.github/scripts/ci-scope.sh` selects the hook jobs when `lint/_clause.py` changes.

Accepted risk (owner, named in the plan for step `clause-parser-claims`): one bad edit to `lint/_clause.py` that passes CI breaks every check that imports it, and every repo that pins `lint/`. How often a bad edit passes CI is unmeasured.
Kind: process
Home: lint/_clause.py
