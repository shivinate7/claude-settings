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
- Before it compares, it removes headings, `Kind:`, `Plan:` and `Home:` lines, HTML comments, code spans, quoted text, numbers and time zones, from both sides. So a quoted record name, a quote of the owner and a ruling time count for nothing in this test.
- A unit is refused when runs of 5 or more words that it shares with records cover at least 12 of its words and at least half of its words.
- A unit is also refused when it names a record by its slug and carries a ruling time (date, hour and minute) that the same record holds. That line copies the grant's source, not only its name.
- Each refusal names the file, the line and the record, and gives the remedy: name the record, and keep only what applies to this repo.
- In a claude-settings checkout it prints n/a and exits 0.

Measured on 2026-11-02, on home 428d8fe, degen a2ae7ba and ios-adblock 519ccf8: each of the two copied merge-grant lines had 33 covered words (80% and 73% of the line). The highest line with its own content had 16 (25%). The threshold sits between them.

Risk kind: named incident, above. Landed 2026-11-02.

Cost: one python start per child CI run, and one per run of skill `compliance-check`. It reads files and writes none. It starts no timer and no long-lived process.

## Not mechanized

- A paraphrase. A line that says a ruling in other words passes the shared-words test. The second test catches it only when the line names the record and copies its time.
- Copies of rule text from the root `CLAUDE.md`. The check reads decision records only. For example, a child line that repeats "A lone lane is its own integration PR" passes.
- A shared run under 5 words.

## Why

A copy goes stale the next time the owner rewrites the record. A session in the child repo then reads two answers to one question, and the stale one is nearer.

Kind: process
Home: lint/compliance_probes.py
