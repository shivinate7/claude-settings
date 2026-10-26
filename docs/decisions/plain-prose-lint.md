# The STE lint becomes a plain-prose lint

## The ruling

The STE lint is a plain-prose lint. The writer gets a rewrite only where the rewrite keeps the meaning.
Where the lint cannot judge meaning, it nudges and never blocks.

Owner: a lint rule either blocks or does not exist. A rule nobody can see is not a rule. The six advisory codes below are the one exception. `RULES` in `lint/ste_lint.py` is the home.

STE018 (a gendered pronoun) is deleted outright. STE006 (a semicolon) is prose-only and has no mechanism. Neither raises a finding (owner ruling 2026-09-23).

- A lookup rule (a fixed phrase, a fixed pronoun set, a missing conjunction, a word order) may block. A judgment rule (a style call that settles differently each time a reader looks) must not be an `error`.
- Errors stay for three codes: STE001 (one budget of 30 words, no split by mode), STE011 (bloat) and
  STE013 (double negative). CI's STE lint fails the step on them on changed lines. No hook runs the lint
  on a write (owner, 2026-10-22 10:10 CDT; `ste-gate-fixes-not-nags`).
- STE020 (label length) and STE021 (bad UI escape) are dropped (owner, 2026-10-22 10:10 CDT). The
  icon-and-label rule and design review carry label length. A UI escape is `ste-disable-line CODE: reason`
  or `ste-disable-next-line CODE: reason` in a comment. Any other escape suppresses nothing.
- Six codes are advisory and never block: STE003 (nominalization), STE007 (Latin abbreviation), STE008
  (contraction), STE009 (phrasal verb), STE015 (condition order) and STE017 (omitted "that"). The nudge is
  temporary: STE moves into agent briefs as a writing standard and leaves `CLAUDE.md` (note `ste-into-agent-briefs`).
- Autofix covers STE011 only, and only a fixed bloat phrase. A borderline STE011 row has no fix and still
  errors, as does a bloat phrase in ALL CAPS.
- STE001 reads one key, `max_words`, set to 30. Mode decides only whether STE015 runs.
- `actions/ste-lint` reports an advisory finding as a `::warning` and never fails the step.
- Rule `output-write-in-ste` has a `ci` row in `lint/rule_mechanisms.json`, at the `STE lint` step of `gates.yml`.
- No renames. q_max and banchi pin `actions/ste-lint` by SHA, so every code, file and key keeps its name.
- `agents/*.md` keep their STE wording. Agent briefs are the future home of the writing standard.

Reason: safer outcome first, smaller diff second. A rewrite that changes meaning costs more than a nudge.
A guard that goes red on prose the project already lives with finds no defect and is spent (`verification-cry-wolf-guard-is-spent`).

Kind: process
Home: lint/ste_lint.py
