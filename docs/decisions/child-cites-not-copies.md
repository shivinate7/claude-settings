# A child repo names a claude-settings record and never copies it

## The ruling

Owner, 2026-11-02 10:41 CST, ruling fb-1041-2 ("Stop rule churn and drift in the other repos"):

- A child repo's `CLAUDE.md` never copies the text of a claude-settings rule, grant or record. It names the record, such as "Merge grant: claude-settings `standing-merge-grant`".
- It adds only what applies to that repo alone: its own paths, its own checks and its own exceptions.
- When the record changes, the child line stays true, because it holds no copy.

Incident: on 2026-11-01, from 19:19 to 21:34 CST, the owner rewrote the merge grant three times. The 21:34 ruling says a batch runner merges and the coordinator never merges. The `CLAUDE.md` of home, degen and ios-adblock still said the coordinator merges, in text copied from the grant of 2026-10-29.

## The check

Probe group `restates` in `lint/compliance_probes.py`: `python3 lint/compliance_probes.py restates <child root>`. Child CI runs it through the shared action `actions/claude-md-cites`, pinned like the other shared actions.

- It reads the child's `CLAUDE.md` files and `.claude/**/*.md`, in the same paragraph and list-item units as probe group `supersede`. It never reads a fenced code block.
- It reads the record text from the decisions folder of the claude-settings checkout it runs from, found through `lint/layout.py`. It keeps no copy (`building-allow-list-is-the-constant`).
- Before it compares, it removes headings, `Kind:`, `Plan:` and `Home:` lines, HTML comments, code spans, numbers and time zones, from both sides. So a ruling time counts for nothing in this test.
- A copy in double quotes, straight or curly, is still a copy (orchestrator, 2026-11-02 11:55 CST: the ruling says never copies and names no quote exemption).
- A unit is refused when runs of 5 or more words that it shares with records cover at least 12 of its words and at least half of its words.
- Each refusal names the file, the line and the record, and gives the remedy: name the record, and keep only what applies to this repo.
- It names the file as `CLAUDE.md` when `AGENTS.md` is a link to it.
- Probe group supersede now names `CLAUDE.md` too, when `AGENTS.md` links to it.
- In a claude-settings checkout it prints n/a and exits 0.

Measured on 2026-11-02, on home 428d8fe, degen a2ae7ba and ios-adblock 519ccf8: each of the two copied merge-grant lines had 28 covered words. That is 28 of 43 words in home and 28 of 48 in ios-adblock. The highest line with its own content had 16 covered words (26%) in home and 15 (3%) in degen. degen has nothing refused. The threshold of 12 words and half of the unit sits between them.

Risk kind: named incident, above. Landed 2026-11-02.

Cost: one python start per child CI run, and one per run of skill `compliance-check` (unmeasured). It reads files and writes none. It starts no timer and no long-lived process.

## Not mechanized

- A paraphrase. A line that says a ruling in other words passes. A line with under 12 shared words passes, a citation included.
- Copies of rule text from the root `CLAUDE.md`. The check reads decision records only. For example, a child line that repeats the root rule on how a lane merges passes. That rule changes at the cutover (decision `all-repos-switch-together`), so the copy then goes stale and nothing flags it.
- A shared run under 5 words.
- A copy inside a heading, an HTML comment or a code span.
- A copy shorter than 12 words, such as a one-sentence grant line. See debt `short-copy-passes` (the gap for short copies).
- Owner words that a record keeps in code spans. The check never indexes them, so a copy of 12 or more of them passes. See debt `record-code-spans-unindexed` (the gap for code-span words).

## Why

A copy goes stale the next time the owner rewrites the record. A session in the child repo then reads two answers to one question, and the stale one is nearer.

Kind: process
Home: lint/compliance_probes.py
