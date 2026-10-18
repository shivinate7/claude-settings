# The STE lint becomes a plain-prose lint

## The ruling

The STE lint is a plain-prose lint. The writer gets a rewrite only where the rewrite keeps the meaning.
Where the lint cannot judge meaning, it nudges and never blocks.

Owner: a lint rule either blocks or does not exist. A rule nobody can see is not a rule. The six advisory codes below are the one exception. `RULES` in `lint/ste_lint.py` is the home.

- A lookup rule (a fixed phrase, a fixed pronoun set, a missing conjunction, a word order) may block. A judgment rule (a style call that settles differently each time a reader looks) must not be an `error`.
- Errors stay for five codes: STE001 (one budget of 30 words, no split by mode), STE011 (bloat),
  STE013 (double negative), STE020 (label length) and STE021 (bad escape).
- Six codes are advisory and never block: STE003 (nominalization), STE007 (Latin abbreviation), STE008
  (contraction), STE009 (phrasal verb), STE015 (condition order) and STE017 (omitted "that"). The nudge is
  temporary: STE moves into agent briefs as a writing standard and leaves `CLAUDE.md` (note `ste-into-agent-briefs`).
- Autofix covers STE011 only, and only a fixed bloat phrase. A borderline STE011 row has no fix and still
  errors, as does a bloat phrase in ALL CAPS.
- STE001 reads one key, `max_words`, set to 30. Mode decides only whether STE015 runs.
- `lint/ste_gate.py` prints one note line per advisory code: the first finding and the count of more. The
  write goes ahead. A denied write shows no note. `lint/md_sweep.py` never blocks on an advisory finding.
  `actions/ste-lint` reports one as a `::warning` and never fails the step.
- The `NOTE` string of both gates names what blocks: a sentence over 30 words, bloat, double negative.
- Rule `output-write-in-ste` has its row in `lint/rule_mechanisms.json` at `test_ste011_bloat_blocks`.
- No renames. q_max and banchi pin `actions/ste-lint` by SHA, so every code, file and key keeps its name.
- `agents/*.md` keep their STE wording. Agent briefs are the future home of the writing standard.

Reason: safer outcome first, smaller diff second. A rewrite that changes meaning costs more than a nudge.
A guard that goes red on prose the project already lives with finds no defect and is spent (`verification-cry-wolf-guard-is-spent`).

Kind: process
Home: lint/ste_lint.py
