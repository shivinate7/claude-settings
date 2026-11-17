# The STE lint is a plain-prose lint

## The ruling

The STE lint is a plain-prose lint. The writer gets a rewrite only where the rewrite keeps the meaning.
Where the lint cannot judge meaning, it nudges and never refuses.

Owner, 2026-11-02 13:22 CST: drop Simplified Technical English (STE) as a named writing standard, everywhere. Write plainly only. The one standard is rule `output-write-in-ste` in `CLAUDE.md`: "Write plainly: short sentences, one term per meaning, no filler." The lint keeps its current checks and names for now. Renaming the lint, its CI step and its shared action is a separate follow-up.

Owner: a lint rule either refuses or does not exist. A rule nobody can see is not a rule. The six advisory codes below are the one exception. `RULES` in `lint/ste_lint.py` is the home.

STE018 (a gendered pronoun) is deleted outright. STE006 (a semicolon) is prose-only and has no mechanism. Neither raises a finding (owner ruling 2026-09-23).

- A lookup rule (a fixed phrase, a fixed pronoun set, a missing conjunction, a word order) may refuse. A judgment rule (a style call that settles differently each time a reader looks) must not be an `error`.
- Errors stay for two codes: STE011 (bloat) and STE013 (double negative). CI's STE lint fails the
  CI step on these two codes on changed lines. The lint never refuses on
  word count: STE001 and the 30-word budget are dropped (owner, 2026-11-11 12:54 and 12:56 CST;
  restart plan R37). `count_words` stays: `--stats` measures and never caps. No hook runs the lint
  on a write (owner, 2026-10-22 10:10 CDT; `ste-guard-fixes-not-nags`).
- STE020 (label length) and STE021 (bad UI escape) are dropped (owner, 2026-10-22 10:10 CDT). The
  icon-and-label rule and design review carry label length. A UI escape is `ste-disable-line CODE: reason`
  or `ste-disable-next-line CODE: reason` in a comment. Any other escape suppresses nothing.
- Six codes are advisory and never refuse: STE003 (nominalization), STE007 (Latin abbreviation), STE008
  (contraction), STE009 (phrasal verb), STE015 (condition order) and STE017 (omitted "that").
- Autofix covers STE011 only, and only a fixed bloat phrase. A borderline STE011 row has no fix and still
  errors, as does a bloat phrase in ALL CAPS.
- Config key `max_words` is a removed key. The lint ignores it and says so on stderr. Mode decides only whether STE015 runs.
- `actions/ste-lint` reports an advisory finding as a `::warning` and never fails the step.
- Rule `output-write-in-ste` has a `ci` row in `lint/rule_mechanisms.json`, at the `STE lint` CI step of `checks.yml`.
- No renames yet. q_max and banchi pin `actions/ste-lint` by SHA, so every code, file and key keeps its name.

Reason: safer outcome first, smaller diff second. A rewrite that changes meaning costs more than a nudge.
A guard that goes red on prose the project already lives with finds no defect and is spent (`verification-cry-wolf-guard-is-spent`).

Kind: process
Home: lint/ste_lint.py
