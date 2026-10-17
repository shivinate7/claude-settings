# The STE lint becomes a plain-prose lint

## The question

How much of the STE lint should block a write, and what may its fixer change?

## The ruling

Owner ruling, 2026-10-17 01:52 CDT: turn the STE lint into a plain-prose lint.

- Errors stay for five codes: STE001 (one budget of 30 words, no split by mode), STE011 (bloat), STE013 (double negative), STE020 (label length) and STE021 (bad escape).
- Six codes are advisory: STE003 (nominalization), STE007 (Latin abbreviation), STE008 (contraction), STE009 (phrasal verb), STE015 (condition order) and STE017 (omitted "that"). They never block. The owner calls the nudge "only temporary".
- Remove each autofix that changes meaning or rewrites more than a fixed bloat phrase.
- Rule `output-write-in-ste` reads: "Write plainly: short sentences, one term per meaning, no filler."
- No renames. q_max and banchi pin `actions/ste-lint` by SHA, so every code, file and key keeps its name.
- Delete the STE debts that this closes.

Owner on the advisory codes, 2026-10-17 01:57: the nudge is temporary. STE moves into agent briefs, as a writing standard. It leaves `CLAUDE.md`. Deferred item `ste-into-agent-briefs` holds that move.

Orchestrator's calls, 2026-10-17 02:40, under the standing word "safer outcome first, smaller diff second":

- Orchestrator's call: fixes stay for STE011 only.
- Orchestrator's call: five borderline STE011 rows lose their fix and still error: `in a timely manner`, `along the lines of`, `close down`, `of major importance` and `except when`.
- Orchestrator's call: three phrases leave the `BLOAT` table: `in between`, `in terms of` and `it would appear that`.
- Orchestrator's call: the write gate shows advisories as a non-blocking note. A denied write does not show the note.
- Orchestrator's call: a bloat phrase in ALL CAPS still errors and has no fix. The case rewrite went with the fixes that change meaning.

Orchestrator's call, 02:54: `agents/*.md` keep their STE wording. Agent briefs are the future home of the writing standard.

## What landed

MEASURED on branch `prose-lint` (9d577ab) against 68f244f, the base before this lane. Three commits: tests, tests for the orchestrator's calls, and the build. The test suites run in CI, not in this record.

- Fix rows, counted from `FIXABLE` in `lint/ste_lint.py`: 162 fall to 97.
  - STE007: 12 to 0. STE008: 32 to 0. STE003: 13 to 0. Those three families lose 57 rows.
  - STE011: 105 to 97. Five rows lose the fix and three phrases leave the table.
  - The `BLOAT` table falls from 111 to 108 rows.
- A fixed phrase in ALL CAPS is no longer rewritten (`_fix_line`).
- STE001 reads one key, `max_words`, set to 30. It replaces `max_words_procedural` (20) and `max_words_descriptive` (25). Mode no longer picks a budget. It now decides only whether STE015 runs.
- The six advisory rules read `warning`.
  - `lint/ste_gate.py` prints a note for an advisory finding. The write goes ahead. The note holds one line per code: the first finding and the count of more (`advisory_lines` in `lint/_transcript.py`).
  - `lint/md_sweep.py` never blocks on an advisory finding. It prints the note, and appends it to the reason when an error blocks.
  - `actions/ste-lint` reports an advisory finding as a `::warning`. It never fails the step.
- The `NOTE` string of both gates names what blocks: a sentence over 30 words, bloat, double negative.
- `CLAUDE.md` rule `output-write-in-ste` has the owner's wording. Its row in `lint/rule_mechanisms.json` points at `test_ste011_bloat_blocks`.
- Tests: `OneSentenceBudgetTests`, `AdvisoryCodesTests` and `KeptErrorCodesTests` in `lint/test_gates.py`. `RemovedFixesTests`, `KeptFixesTests`, `BorderlineBloatTests` and `DroppedBloatTests` in `lint/test_ste_autofix.py`. By the test commit messages, they ran red on 68f244f: 52 fails in `lint/test_gates.py`, 145 in `lint/test_ste_autofix.py`, and 3 checks in `actions/ste-lint/test_action.py`.
- Debts closed: `ste-fix-changes-meaning` (every example now stays as written) and `ste-eg-line-end-rewrite` (no `e.g.` rewrite remains). Both files are deleted.

## The outcome, and what protects it now

The writer gets a rewrite only where the rewrite keeps the meaning. Where the lint cannot judge meaning, it nudges and never blocks.

- No rewrite of Latin abbreviations, contractions or nominalizations: `RemovedFixesTests` and `RemovedFixesGateTests`.
- The kept bloat rows still fix: `KeptFixesTests`.
- The five blocking codes still block: `KeptErrorCodesTests`.
- An advisory code never blocks: `AdvisoryCodesTests`.

## Holes, named

1. The advisory note is not logged to guard.log. At the 30-day trigger of `ste-into-agent-briefs`, no log can show whether the nudge ran. Debt: `advisory-note-not-logged`, the advisory note leaves no log line.
2. The sweep prints an advisory-only note as a `systemMessage`. Unmeasured: whether the model sees a Stop `systemMessage`. Debt: `sweep-note-delivery-unmeasured`, the sweep note may reach the user only.
3. `load_config` in `lint/ste_lint.py` keeps only the keys of `DEFAULT_CONFIG`. A `.ste.json` that sets `max_words_procedural` or `max_words_descriptive` is ignored with no message. A repo that set them gets 30 words with no notice. Debt: `old-budget-keys-ignored`, removed budget keys are dropped silently.
4. The rule text says "one term per meaning". No check reads it. The gate covers sentence length and filler only. Debt: `one-term-per-meaning-unchecked`, no check reads one term per meaning.
5. The gate and the sweep read file writes only. Replies, briefs and agent messages are unchecked. Debt: `plain-prose-writes-only`, the plain-prose rule is checked on file writes only.
6. Unmeasured: how often a kept STE011 swap changes meaning. Only five rows were read for meaning. Debt: `kept-bloat-rows-unaudited`, 97 kept fix rows are not read against a corpus.
7. `ste-eg-in-fence-reported` stays open. The lint still reports `e.g.` in a pre block and a blockquote fence, now as a warning. Its text is rewritten.
8. Three phrases left `BLOAT` with no note: `in between`, `in terms of` and `it would appear that`. They pass silently. Debt: `dropped-bloat-phrases-silent`, three dropped filler phrases pass with no note.
9. A denied write shows no advisory note. The writer sees the advisories only after the errors clear. Debt: `ste-gate-fixes-not-nags`, the gate fixes and does not nag.
10. `lint/test_ste_autofix.py` comments cite the deleted debt `ste-fix-changes-meaning`. The comment-cites lane re-points them. Debt: `stale-comment-cites`, code comments cite deleted records.

Kind: process
Home: lint/ste_lint.py
