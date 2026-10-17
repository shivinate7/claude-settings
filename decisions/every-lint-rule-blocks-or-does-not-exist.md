# A lint rule blocks, or it does not exist, bar six advisory codes

CLAUDE.md says: "Judge every rule, check, and design by the outcome for the
person the software serves." The owner ruled that a rule either blocks or
does not exist. A rule nobody can see is not a rule. `lint/ste_lint.py` held
19 rules: 4 `error`, 13 `warning` and 2 `info`. Both gates that call the
linter, `lint/ste_gate.py` and `lint/md_sweep.py`, filtered their findings to
`error` only. So 15 rules fired on every run and changed no outcome.

## The rule set

`RULES` in `lint/ste_lint.py` holds 11 rows.

Five rules block, at `error`:

- STE001 sentence-length. It reads one key, `max_words`, set to 30. That key
  replaces the two budgets of 20 and 25 words. Mode no longer picks a budget
  (`plain-prose-lint`, the STE lint becomes a plain-prose lint).
- STE011 bloat.
- STE013 double-negative.
- STE020 label-length. A button, a label or an `aria-label` holds 4 words at
  most.
- STE021 bad-escape. A UI escape comment names a rule and a reason.

STE020 and STE021 run on front-end copy only.

Six codes are the owner's exception: STE003, STE007, STE008, STE009, STE015
and STE017 read `warning`. They never block. The gates show them in a
non-blocking note, as a temporary nudge (`plain-prose-lint`).

The rules run on Markdown and on front-end copy. They do not run on source
comments and docstrings unless a caller passes `--source-prose`
(`source-prose-lint-ships-dark`, the source-prose mode ships dark).

## A finding the gate fixes is not a block

The STE gate rewrites a Markdown STE011 finding it can fix, and denies only the
findings it cannot fix. A fixed finding is not a block. A finding the gate
cannot fix still blocks, as this entry says. See ste-gate-fixes-not-nags, the
STE rewrite ruling.

## The measurement

Every one of the 32 tracked Markdown files in this repository, already
accepted into it, ran through `lint/ste_lint.py` at every severity. The
number beside each rule is the share of those 32 files it hit.

A lookup rule is a binary test: a fixed phrase, a fixed pronoun set, a
missing conjunction, a word order. No judgment call sits between the text and
the finding. A judgment rule is a style call. Does a verb name the action
clearly? Does a paragraph run too long? Do two words carry the same meaning
in this codebase? No fixed pattern settles any of that. It settles
differently each time a reader looks.

| Rule | Firing rate | Type | Status |
| --- | --- | --- | --- |
| STE011 bloat | 0% | lookup | error |
| STE013 double-negative | 3% | lookup | error |
| STE018 gendered-language | 3% | lookup | deleted |
| STE015 condition-order | 3% | lookup | warning |
| STE009 phrasal-verb | 9% | lookup | warning |
| STE003 nominalization | 12% | lookup | warning |
| STE017 omitted-that | 12% | lookup | warning |
| STE019 terminology-drift | 25% | judgment | deleted |
| STE012 vague-verb | 34% | judgment | deleted |
| STE004 complex-verb | 40% | judgment | deleted |
| STE005 noun-cluster | 56% | judgment | deleted |
| STE014 paragraph-length | 56% | judgment | deleted |
| STE016 ambiguous-this | 59% | judgment | deleted |
| STE010 ambiguous-word | 71% | judgment | deleted |
| STE002 passive-voice | 81% | judgment | deleted |

STE001 sentence-length, STE007 latin-abbreviation and STE008 contraction are
lookups of the same kind. STE001 reads `error`. STE007 and STE008 read
`warning`. STE006 semicolon is the same kind of lookup, and it is deleted.

A rule that fires on 81% of prose this repository already accepted cannot be
an `error`. Promoting it would block eight of the next ten writes. It would
block them on wording nobody flagged as wrong when they wrote it.

"Trust a guard only once it goes red on the defect it guards." A guard that
goes red on prose the project already lives with finds no defect. It finds
only its own threshold. "A guard that goes red when nothing is wrong is
spent, because the reader learns to scroll past it." STE002 at 81% would
have been the loudest, most-ignored guard in this repository from its first
commit.

## The semicolon and gendered-pronoun rules are deleted

The owner ruled in chat on 2026-09-23. STE018, the gendered-pronoun rule,
goes away entirely. No gate, warning, or system message reports it. STE006,
the semicolon rule, is not in the linter either. CLAUDE.md holds no semicolon
line (`a-rule-with-no-gate-leaves-claude-md`, a rule the owner took off the
gate leaves CLAUDE.md too).

MEASURED at `66e64ed`: `lint/ste_lint.py` ran at error severity over all 36
tracked Markdown files. It found 5 errors. STE006 found none. STE018 found 3,
all in repeal-the-no-prefix-report-rule, the report can carry prose above it.
Each of the 3 is a pronoun for the owner, not for an unspecified person. They
are on main, so the gate did not stop them. Those 3 lines stay as written.
The other 2 errors are STE013 findings in a different record, left as they are.

How often each rule denied a write is unmeasured. Neither `lint/ste_gate.py`
nor `lint/md_sweep.py` keeps a log of a denial.

STE006 protected short sentences. A semicolon joins two sentences into one
long sentence. STE001 guards that outcome. `lint/ste_lint.py` ends a
sentence only at a period, an exclamation mark, or a question mark. To
STE001, two clauses joined by a semicolon are one sentence, so the word
budget caps the pair. A short semicolon pair passes, by the choice of the
owner. No gate checks the guidance to write two sentences.

STE018 protected neutral words for an unspecified person. Nothing in this
repository protects that outcome, and the owner accepts that. The rule
matched a fixed pronoun list with no context. It could not tell an
unspecified person from a named person. No STE018 guidance is in CLAUDE.md.

## Front-end copy

`lint/ste_lint.py` reads the text a user sees in `.tsx`, `.jsx`, `.html` and
`.vue` files. The write hook blocks on it, the same way it blocks on Markdown.
The owner asked for this on 2026-09-28 (`fewest-words-mandate`, fewest words,
most of all in front-end copy).

- STE020 caps a button, label or `aria-label` at 4 words. The owner chose to
  build the cap now, and accepted the risk of a false red on a label that
  needs 5 words.
- Reopen the cap if it goes red on a correct label more than once. Measure
  how often it fires, and bring the count to the owner.
- STE011 holds wordiness pairs copied from the Vale style packs, after a
  license check. The packs are MIT and BSD-3-Clause. Their notices are in
  `lint/LICENSE-ste_lint`.

## What this changes

`lint/ste_lint.py`. STE011 and STE013 are `error`. STE003, STE009, STE015 and
STE017 are `warning`. Ten rules are deleted, table row and detection code
together, not the row alone. Eight are judgment rules: STE002, STE004, STE005,
STE010, STE012, STE014, STE016, STE019. The other two are STE006 and STE018.

Every word table, regex, and config key that served only a deleted rule went
with it. That list is long: `AMBIGUOUS`, `VAGUE_VERBS`, `THIS_VERBS`, `BE`,
`ADVERBS`, `IRREGULAR_PARTICIPLES`, `PARTICIPIAL_ADJECTIVES`,
`FUNCTION_WORDS`, `COMMON_VERBS`, `DRIFT_GROUPS`, `GENDERED`, and the whole
`check_terminology` method. Three config keys went the same way:
`max_sentences_per_paragraph`, `max_noun_cluster`, and `glossary`.

`lint/ste_gate.py` and `lint/md_sweep.py` split the findings by severity.
An `error` blocks. A `warning` goes in a non-blocking note. Each gate prints
a `NOTE` string that names only the rules that block: a sentence over 30
words, bloat, and a double negative.

`lint/test_gates.py`. No case named a code of the eight judgment rules, so
none needed removal. A `PromotedRuleTests` class holds one fixture per promoted rule. Each
one proves the rule fires, at its own severity, on a small, targeted example.
One more case proves the deleted codes hold no row in `RULES`: the eight
judgment rules, STE006 and STE018. One more proves the severity of every
remaining row. Each fixture that used a semicolon as its sample error uses a
different error rule. New cases prove that a semicolon and a gendered pronoun
pass the linter. One more case proves that a long semicolon pair still trips
STE001. The suite held 106 cases before the promotion and held 115 after it.

The 32 tracked Markdown files held 20 errors under the new rule set, before
any wording changed. They hold 0 after. Every fix below changed wording
only. A nominalization turned back into its verb. A phrasal verb became its
plain form. A missing "that" was inserted. A gendered pronoun was replaced.
A condition moved in front of its instruction. No fix changed which claim a
file makes.

One fix needed a suppression instead of a rewrite. `README.md` quotes
CLAUDE.md's own rule text, `"merged only when I name the act"`, inside
quotation marks. That string is itself another record's argument, not this
file's wording. It carries `<!-- ste-disable-line STE015 -->` instead of a
reworded quote that would misreport what CLAUDE.md says.

## The eight deleted judgment rules are not sanctioned prose

Deleting a rule is not a ruling that the thing it caught stopped mattering.
Passive voice, vague verbs, and noun clusters are still worse writing when
they show up. So are long paragraphs, ambiguous words, ambiguous leading
"this," complex verb forms, and terminology drift. What changed is only
that no machine stops a write over them.

`CLAUDE.md` says "Write plainly: short sentences, one term per meaning,
no filler." That line is enough. It names the house style without claiming
that a rule enforces every part of it. A future reader who sees eight rules
vanish from `ste_lint.py` should read this file. That reader should not
assume that the deletion was permission to write passive, vague,
over-clustered prose. It is a decision to stop gating style with a pattern
that cannot judge it. It is not a decision that the style stopped counting.

## What this does not do

It does not touch `lint/ste_gate.py`'s scoping logic, `lint/md_sweep.py`'s
sweep, `lint/report_gate.py` or `hooks/guard.py` beyond the one `NOTE` line
above. It does not renumber the surviving rule codes. STE001, STE003, STE007
through STE009, STE011, STE013, STE015, STE017, STE020 and STE021 keep the
codes they already had. An old citation of STE003 or STE009 still names the
same rule.

Kind: process
Home: lint/ste_lint.py
