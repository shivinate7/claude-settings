# Every lint rule blocks, or it does not exist

CLAUDE.md says: "Judge every rule, check, and design by the outcome for the
person the software serves." `lint/ste_lint.py` held 19 rules. Four were
`error`. Thirteen were `warning`, two were `info`, and both gates that call
the linter, `lint/ste_gate.py` and `lint/md_sweep.py`, filter their findings
to `error` only. Fifteen rules fired on every run. None of them changed a
single outcome. A rule nobody can see is not a rule. The owner ruled that a
rule either blocks or does not exist.

## The measurement

Every one of the 32 tracked Markdown files in this repository, already
accepted into it, ran through `lint/ste_lint.py` at every severity. The
number beside each rule is the share of those 32 files it hit.

Promoted to `error`. Each one is a binary lookup: a fixed phrase, a fixed
pronoun set, a missing conjunction, a word order. No judgment call sits
between the text and the finding.

| Rule | Firing rate |
| --- | --- |
| STE011 bloat | 0% |
| STE013 double-negative | 3% |
| STE018 gendered-language | 3% |
| STE015 condition-order | 3% |
| STE009 phrasal-verb | 9% |
| STE003 nominalization | 12% |
| STE017 omitted-that | 12% |

Deleted entirely. Each one is a style judgment. Does a verb name the action
clearly? Does a paragraph run too long? Do two words carry the same meaning
in this codebase? No fixed pattern settles any of that. It settles
differently each time a reader looks.

| Rule | Firing rate |
| --- | --- |
| STE019 terminology-drift | 25% |
| STE012 vague-verb | 34% |
| STE004 complex-verb | 40% |
| STE005 noun-cluster | 56% |
| STE014 paragraph-length | 56% |
| STE016 ambiguous-this | 59% |
| STE010 ambiguous-word | 71% |
| STE002 passive-voice | 81% |

A rule that fires on 81% of prose this repository already accepted cannot be
an `error`. Promoting it would block eight of the next ten writes. It would
block them on wording nobody flagged as wrong when they wrote it.

"Trust a guard only once it goes red on the defect it guards." A guard that
goes red on prose the project already lives with finds no defect. It finds
only its own threshold. "A guard that goes red when nothing is wrong is
spent, because the reader learns to scroll past it." STE002 at 81% would
have been the loudest, most-ignored guard in this repository from its first
commit.

Kept exactly as they were: STE001 sentence-length, STE006 semicolon, STE007
latin-abbreviation, STE008 contraction. All four were already `error`. All
four are the same kind of binary lookup as the seven promoted above.

## What this changes

`lint/ste_lint.py`. Seven rules promoted to `error`: STE003, STE009, STE011,
STE013, STE015, STE017, STE018. Eight rules deleted, table row and
detection code together, not the row alone: STE002, STE004, STE005, STE010,
STE012, STE014, STE016, STE019.

Every word table, regex, and config key that served only a deleted rule went
with it. That list is long: `AMBIGUOUS`, `VAGUE_VERBS`, `THIS_VERBS`, `BE`,
`ADVERBS`, `IRREGULAR_PARTICIPLES`, `PARTICIPIAL_ADJECTIVES`,
`FUNCTION_WORDS`, `COMMON_VERBS`, `DRIFT_GROUPS`, and the whole
`check_terminology` method. Three config keys went the same way:
`max_sentences_per_paragraph`, `max_noun_cluster`, and `glossary`. `RULES`
now holds 11 rows. Every row reads `error`.

`lint/ste_gate.py:56` and `lint/md_sweep.py:431` filter findings to
`severity == "error"`. That filter is still correct. It once selected 4
rules out of 19. It now selects all 11 that remain, and the filter itself
never needed to change. Its printed `NOTE` string named the old four rules
by name. It now names the new eleven. That is a one-line fix, inside a file
this repository asks changes to stay tight in.

`lint/test_gates.py`. No case named a deleted rule, so none needed removal.
A new `PromotedRuleTests` class adds one fixture per promoted rule. Each one
proves the rule fires at `error` severity on a small, targeted example. One
more case proves the eight deleted codes hold no row in `RULES`. One more
proves every remaining row reads `error`. The suite held 106 cases before
this change and holds 115 after.

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

## The eight deleted rules are not sanctioned prose

Deleting a rule is not a ruling that the thing it caught stopped mattering.
Passive voice, vague verbs, and noun clusters are still worse writing when
they show up. So are long paragraphs, ambiguous words, ambiguous leading
"this," complex verb forms, and terminology drift. What changed is only
that no machine stops a write over them.

`CLAUDE.md` already says "Write in Simplified Technical English by
default." That line was enough before this change. It stays enough after
it. It names the house style without claiming that a rule enforces every
part of it. A future reader who sees eight rules vanish from `ste_lint.py`
should read this file. That reader should not assume that the deletion was
permission to write passive, vague, over-clustered prose. It is a decision
to stop gating style with a pattern that cannot judge it. It is not a
decision that the style stopped counting.

## What this does not do

It does not touch `lint/ste_gate.py`'s scoping logic, `lint/md_sweep.py`'s
sweep, `lint/report_gate.py`, `lint/_transcript.py`, or `hooks/guard.py`
beyond the one `NOTE` line above. It does not renumber the surviving rule
codes. STE001, STE003, STE006 through STE009, STE011, STE013, and STE015
through STE018 keep the codes they already had. An old citation of STE003 or
STE009 still names the same rule.
