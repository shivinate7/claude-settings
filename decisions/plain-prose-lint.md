# The STE lint becomes a plain-prose lint

## The ruling

The STE lint is a plain-prose lint. The writer gets a rewrite only where the rewrite keeps the meaning.
Where the lint cannot judge meaning, it nudges and never blocks.

- Errors stay for five codes: STE001 (one budget of 30 words, no split by mode), STE011 (bloat), STE013
  (double negative), STE020 (label length) and STE021 (bad escape).
- Six codes are advisory: STE003 (nominalization), STE007 (Latin abbreviation), STE008 (contraction),
  STE009 (phrasal verb), STE015 (condition order) and STE017 (omitted "that"). They never block. The
  nudge is temporary: STE moves into agent briefs as a writing standard and leaves `CLAUDE.md` (deferred
  item `ste-into-agent-briefs`).
- Remove each autofix that changes meaning or rewrites more than a fixed bloat phrase. Fixes stay for
  STE011 only.
- STE001 reads one key, `max_words`, set to 30. Mode decides only whether STE015 runs.
- The six advisory rules read `warning`. `lint/ste_gate.py` prints one note line per code for an
  advisory finding: the first finding and the count of more (`advisory_lines` in `lint/_transcript.py`).
  The write goes ahead. A denied write shows no note. `lint/md_sweep.py` never blocks on an advisory
  finding. `actions/ste-lint` reports one as a `::warning` and never fails the step.
- The `NOTE` string of both gates names what blocks: a sentence over 30 words, bloat, double negative.
- Rule `output-write-in-ste` reads: "Write plainly: short sentences, one term per meaning, no filler."
  Its row in `lint/rule_mechanisms.json` points at `test_ste011_bloat_blocks`.
- No renames. q_max and banchi pin `actions/ste-lint` by SHA, so every code, file and key keeps its name.
- `agents/*.md` keep their STE wording. Agent briefs are the future home of the writing standard.

Orchestrator's calls under the standing word "safer outcome first, smaller diff second":

- Five borderline STE011 rows lose their fix and still error: `in a timely manner`, `along the lines of`,
  `close down`, `of major importance` and `except when`.
- Three phrases leave the `BLOAT` table: `in between`, `in terms of` and `it would appear that`.
- A bloat phrase in ALL CAPS still errors and has no fix (`_fix_line`).

Protection: `RemovedFixesTests` and `RemovedFixesGateTests` (no rewrite of Latin abbreviations,
contractions or nominalizations), `KeptFixesTests`, `KeptErrorCodesTests` (the five blocking codes
block), `AdvisoryCodesTests` (an advisory code never blocks), `OneSentenceBudgetTests`,
`BorderlineBloatTests` and `DroppedBloatTests`, in `lint/test_gates.py` and `lint/test_ste_autofix.py`.

Kind: process
Home: lint/ste_lint.py

## Holes, named

- Debt `ste-gate-fixes-not-nags`: a denied write shows no advisory note. The writer sees advisories only after the errors clear.
- `load_config` in `lint/ste_lint.py` prints a notice on stderr for `max_words_procedural` and `max_words_descriptive` in a config.
