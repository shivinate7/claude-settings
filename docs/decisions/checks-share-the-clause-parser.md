# Checks share the clause parser

## The ruling

The checks that read prose by sentence and clause use one module, `lint/_clause.py`. It holds the sentence and clause boundaries and one list for each word class: negators, adverbs, conditionals, reason links, determiners and the cannot-claim phrase forms. It reads text and a mask only. The module runs in linear time. The cannot-claim check does not: its doubling ratio is about 3.9 (measured 2026-11-08, 0.5 s for 500 phrases in one sentence, 2.0 s for 1,000 and 8.2 s for 2,000), because `_claim` in `lint/report_guard.py` scans the rest of the sentence once for each phrase it finds. Note `cannot-claim-comma-sentence-superlinear` stays open with that measure.

- `lint/report_guard.py` imports it for the cannot-claim check. That check is the only caller today.
- The pre-existing-failure check and the comment narration gloss check are planned callers. Neither is built.
- A domain word list stays with its check: the act tables, the blocker states and the check words belong to the cannot-claim check.
- `OUTAGE_NOUNS` and `OUTAGE_VERBS` live in the module, not in the check. They are a shared lexicon: the words that make a noun or a verb read as an outage, not a red CI check. The pre-existing-failure check, a planned caller, tells an outage from a red check the same way. The cannot-claim check builds its blocker patterns from them.
- `PREPOSITIONS` has one home too: the check's `_PREPOSITION` pattern is built from it.
- Two `Clause` fields have no caller yet: `term` and `sent_end`. They serve slices B and C, the pre-existing-failure check and the comment narration gloss check, which read the separator, the nearest stop and the clause's place in its sentence. `lint/test_clause.py` pins each Clause field, and the mutation report on the module scores each.
- Limit, intended: a claim whose object is not a PR (docs, config files, CI logs) is no PR claim, so "I can't update the docs for PR 12." and "I can't open the PR's CI logs." pass. Harm: low, a missed flag only. Decision `claims-carry-backing`, part (vi), and note `cannot-claim-pr-possessive-object-no-claim`.
- A PR URL and a --repo flag key a PR by repo and number, so a URL matches a number only when --repo names the URL's repo. The port commit changed no verdict; the later fixes in this change (the URL key, any -ly adverb before a check word) change verdicts on purpose.

Why: the cannot-claim check carried a regex for each piece of grammar, and each regex cut sentences its own way. A comma-heavy sentence also cost more than its length (note `cannot-claim-comma-sentence-superlinear`).

Protection of the old outcome (one bad edit must break one check, never all of them):

- `lint/test_clause.py` pins each Clause field, and a mutant per field goes red. It runs in all three OS jobs of `.github/workflows/checks.yml`.
- `hooks/mutate_guard.py` scores `lint/_clause.py` in report mode (`REPORT_TARGETS`).
- The import sits at the top of `lint/report_guard.py`, so a broken module fails the guard suites loudly in CI.
- `.github/scripts/ci-scope.sh` selects the hook jobs when `lint/_clause.py` changes.

Accepted risk (owner, named in the plan for step `clause-parser-claims`): one bad edit to `lint/_clause.py` that passes CI breaks every check that imports it, and every repo that pins `lint/`. How often a bad edit passes CI is unmeasured.
Kind: process
Home: lint/_clause.py
