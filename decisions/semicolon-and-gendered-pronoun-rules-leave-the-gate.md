# The semicolon and gendered-pronoun rules leave the gate

The owner ruled in chat on 2026-09-23. STE018, the gendered-pronoun rule,
goes away entirely. No gate, warning, or system message reports it. STE006,
the semicolon rule, also leaves the linter. Its guidance stays in CLAUDE.md
as one line of prose, and no machine checks that line. This entry records
the ruling. It does not make it.

## The sentences this amends

every-lint-rule-blocks-or-does-not-exist, a rule blocks or it does not
exist, put STE018 in its table "Promoted to `error`". It also said: "Kept
exactly as they were: STE001 sentence-length, STE006 semicolon, STE007
latin-abbreviation, STE008 contraction." Both rules now leave those lists.
The ruling of that entry still holds. Neither rule blocks now, so neither
rule exists in `lint/ste_lint.py`.

## The measurement

At `66e64ed`, `lint/ste_lint.py` ran at error severity over all 36 tracked
Markdown files. It found 5 errors. STE006 found none. STE018 found 3, all in
repeal-the-no-prefix-report-rule, the report can carry prose above it. Each
of the 3 is a pronoun for the owner, not for an unspecified person. They
are on main today, so the gate did not stop them. The other 2 errors are
STE013 findings in a different record. They are out of scope here.

How often each rule denied a write is unmeasured. Neither `lint/ste_gate.py`
nor `lint/md_sweep.py` keeps a log of a denial.

## The outcome each rule protected, and what protects it now

STE006 protected short sentences. A semicolon joins two sentences into one
long sentence. STE001 still guards that outcome. `lint/ste_lint.py` ends a
sentence only at a period, an exclamation mark, or a question mark. To
STE001, two clauses joined by a semicolon are one sentence, so the word
budget still caps the pair. The line in CLAUDE.md asks for two sentences.
No gate checks that line. A short semicolon pair passes, by the choice of
the owner.

STE018 protected neutral words for an unspecified person. Nothing in this
repository protects that outcome now, and the owner accepts that. The rule
matched a fixed pronoun list with no context. It could not tell an
unspecified person from a named person.

## The mechanism

`lint/ste_lint.py`. The STE006 and STE018 rows go, and their detection code
goes with them. `GENDERED` goes too. `RULES` holds 9 rows. Every row reads
`error`. The other rules keep their codes.

`lint/ste_gate.py` and `lint/md_sweep.py`. Each `NOTE` string names only the
rules that remain.

`lint/test_gates.py`. Each fixture that used a semicolon as its sample
error now uses a different error rule. New cases prove that a semicolon and
a gendered pronoun pass the linter. One more case proves that a long
semicolon pair still trips STE001. The deleted-rules case now lists STE006
and STE018.

`CLAUDE.md`. The Output paragraph gains one line with the anchor
`output-no-semicolon`. Its row in `lint/rule_mechanisms.json` reads
`unmechanized`, with the ruling of the owner as the reason.
`UNMECHANIZED_EXPECTED` in `lint/rule_audit.py` goes up by 1.

## What this does not do

It adds no STE018 guidance to CLAUDE.md. It does not reword the 3 STE018
lines, which are no longer findings. It does not fix the 2 STE013 findings.
It does not touch source-prose-lint-ships-dark, the source lint stays off.
Its STE006 counts were true when that entry was written.
