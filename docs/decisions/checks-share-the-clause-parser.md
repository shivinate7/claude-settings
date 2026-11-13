# Checks share the clause parser

## The ruling

The checks that read prose by sentence and clause use one module, `lint/_clause.py`. It holds the sentence and clause boundaries and one list for each word class: negators, adverbs, conditionals, reason links, determiners and the cannot-claim phrase forms. It reads text and a mask only. The module runs in linear time. The cannot-claim check does not. Measured 2026-11-08 at commit 9facc42f1: 0.27 s, 0.89 s and 3.44 s for 500, 1,000 and 2,000 phrases in one sentence, about 3.3x to 3.9x per doubling. The cause is `_claim` in `lint/report_guard.py`, which scans the rest of the sentence once for each phrase it finds. Note `cannot-claim-comma-sentence-superlinear` stays open with that measure.

- `lint/report_guard.py` imports it for the cannot-claim check and the pre-existing-failure check.
- The pre-existing-failure check is built: `lint/report_guard.py` `pre_existing_problem`, the pre-existing claim check of decision `pre-existing-needs-main-run`. It reads each reply sentence without a `?`, outside fences, quoted text and code spans. Its run test, `_names_main_run`, passes a line that has a base name (`main`, `master` or `origin/<branch>`) with a hash (7 to 40 hex characters, with a digit) after it, in one of four forms: "on <base> at <sha>", "on <base> at commit <sha>", "on <base> (<sha>)" or "<base>@<sha>". The hash must be on the base and no older than the PR's merge base (step `base-hash-on-base`). It also passes a CI run URL on a line that says "on <base>". The known limits are in that decision's Known limit and in the `pe-` notes in `docs/debts/notes.md`. It uses the clause parser: `_pre_clauses` takes its sentences and clauses from `_clause.sentences` and `_clause.clauses`, and cuts each clause again at the parser's joiners, reason links and subordinators and at "which". Its negators are `ANSWERED_NEGATOR_RE` in `lint/report_guard.py`, because `NEGATORS` lacks none, nothing, nobody, cannot and "yet to". The comment narration check reads the parser by import: `lint/check_comment_narration.py` takes its "in", "from", "if", "unless" and "while" from `lint/_clause.py` lists and keeps "after", "when", "until" and "once" as its own words, which no list holds. Step `pre-existing-uses-clause` (port both checks to the shared parser; filed by triage at roadmap 85bc80e1b) is built for both checks.
- A domain word list stays with its check: the act tables, the blocker states and the check words belong to the cannot-claim check.
- `OUTAGE_NOUNS` and `OUTAGE_VERBS` live in the module, not in the check. They are the words that make a noun or a verb read as an outage, not a red CI check. The cannot-claim check builds its blocker patterns from them. The pre-existing-failure check does not read them: `FAILURE_RE` counts `red` as a failure word.
- `PREPOSITIONS` has one home too: the check's `_PREPOSITION` pattern is built from it.
- Callers read `start`, `join`, `lead`, `lead_at`, `lead_end`, `hard_end`, `end` and `conditional`: `_scan` and `_claim` in lint/report_guard.py, `reasons` and `reasons_before` in lint/_clause.py, and `_pre_clauses` in lint/report_guard.py, which reads `start` and `end` only. Twelve Clause fields have no reader outside the tests: `subject`, `verb`, `aux`, `modal`, `negated`, `tense`, `passive`, `object`, `complement`, `reason_for`, `term` and `sent_end`. `lint/test_clause.py` pins each Clause field, and the mutation report on the module scores each.
- Limit, known: the module is linear except the "as" branch of `lead_opens_clause`, which is quadratic in the count of "as" in one clause (note `pe-as-branch-quadratic`); this does not change the ruling above.
- Limit, intended: a claim whose object is not a PR (docs, config files, CI logs) is no PR claim, so "I can't update the docs for PR 12." and "I can't open the PR's CI logs." pass. Harm: low, a missed flag only. Decision `claims-carry-backing`, part (vi), and note `cannot-claim-pr-possessive-object-no-claim`.
- A PR URL and a --repo flag key a PR by repo and number, so a URL matches a number only when --repo names the URL's repo. The port commit (6f244a56c, the port to the shared parser) did change verdicts: a code span or quote between two separators hid a claim, because the later separator did not open the clause and the negation and conditional reads saw the masked text. This change fixes that hole. The other fixes in this change (the URL key, any -ly adverb before a check word) change verdicts on purpose.

Why: the cannot-claim check carried a regex for each piece of grammar, and each regex cut sentences its own way. A comma-heavy sentence also cost more than its length (note `cannot-claim-comma-sentence-superlinear`).

Protection of the old outcome (one bad edit must break one check, never all of them):

- `lint/test_clause.py` pins each Clause field, and a mutant per field goes red. It runs in all three OS jobs of `.github/workflows/checks.yml`.
- `hooks/mutate_guard.py` scores `lint/_clause.py` in report mode (`REPORT_TARGETS`).
- The import sits at the top of `lint/report_guard.py`, so a broken module fails the guard suites loudly in CI.
- `.github/scripts/ci-scope.sh` selects the hook jobs when `lint/_clause.py` changes.

Accepted risk (owner, named in the plan for step `clause-parser-claims`): one bad edit to `lint/_clause.py` that passes CI breaks every check that imports it, and every repo that pins `lint/`. How often a bad edit passes CI is unmeasured.
Kind: process
Home: lint/_clause.py
