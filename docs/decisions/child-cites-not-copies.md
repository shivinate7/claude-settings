# A child repo names a claude-settings record and never copies it

## The ruling

Owner, 2026-11-02 10:41 CST, ruling fb-1041-2 ("Stop rule churn and drift in the other repos"):

- A child repo's `CLAUDE.md` never copies the text of a claude-settings rule, grant or record. It names the record, such as "Merge grant: claude-settings `standing-merge-grant`".
- It adds only what applies to that repo alone: its own paths, its own checks and its own exceptions.
- When the record changes, the child line stays true, because it holds no copy.

Incident: on 2026-11-01, from 19:19 to 21:34 CST, the owner rewrote the merge grant three times. The 21:34 ruling says a batch runner merges and the coordinator never merges. The `CLAUDE.md` of home, degen and ios-adblock still said the coordinator merges, in text copied from the grant of 2026-10-29.

## The check

Probe group `restates` in `lint/compliance_probes.py`: `python3 lint/compliance_probes.py restates <child root>`. Child CI runs it through the shared action `actions/claude-md-cites`, pinned like the other shared actions.

- It reads every rule file the child keeps: `CLAUDE.md` files, `.claude/**/*.md`, `docs/rules/**/*.md`, each shared rule file (`rule_audit.RULE_FILES`) and the layout's rules folder, in the same paragraph and list-item units as probe group `supersede`. It never reads a fenced code block. A rule file it cannot read, or a layout it cannot read, makes the group unknown (exit 2), never clear.
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

### Rule and record move together

Incident: found on 2026-11-15, line 38 of record `hold-unsafe-after-round-3` changed and the rule sentence in the root `CLAUDE.md` that cites it did not. It stayed stale for over 30 hours, and 7 child repos carried the stale text. Owner, 2026-11-15 00:49 CST: "ensure something is built to always keep the two in alignment" (relayed 01:14 CST).

Probe group `aligned`: `python3 lint/compliance_probes.py aligned <root>`. It is the second step of `actions/claude-md-cites`, on a `pull_request` run, in claude-settings and in each child, on that repo's own decisions folder (found through `lint/layout.py`).

- Env: `BASE_SHA`, the PR's base. The action sets it to `origin/<base branch>`, so the diff runs from the merge base. `HEAD_SHA`, the PR's head, is `HEAD` when unset: the checked-out commit, so the diff's lines match the files on disk, with no second git call. `PR_BODY`, the description, is read from `pull_request.body` of the event file that `GITHUB_EVENT_PATH` names when unset, never from an API call. A null body is empty. The body clears a gap only, so it is read only when a gap is found.
- A gap with no body to read (no `PR_BODY`, no readable event file) is unknown, exit 2, never a refusal and never a clear. A body that is present and empty clears nothing. A local lint run has no event file, so it still needs the PR body, a network read, to decide a gap.
- A missing `BASE_SHA`, or a diff, a folder in the rule walk, the decisions folder or a file it cannot read, is unknown too (exit 2, with a verdict line). The walk skips `.git`, `node_modules`, `.venv`, `venv` and `site-packages` at any depth, and `.claude/worktrees`: a vendored `CLAUDE.md` is no rule file of the repo.
- A unit is one sentence, as a rule paragraph holds them: from the end of the previous `<!-- rule:X -->` anchor, or the paragraph's start, to its own anchor. Text after the last anchor is a unit of its own. A sentence cites a record by its slug alone in a code span, or by the anchor that the record's `Home:` line names. The record is read at head or at base. So a record deleted in the PR, or whose `Home:` line the PR changed, is still cited. A code span is read as code, so a `#`, `//` or `/*` in it opens nothing, and a span that runs over lines keeps its sentence whole. Units come from the rule files above.
- A sentence changed when a diff line touches it and the file's base side holds no sentence with its text, with whitespace runs made one space. The check rebuilds the base side from the head file and the diff's hunks, so it makes no second git call. So an edit to another sentence, on the same line or another, does not change it, and a sentence moved with its text kept is no change.
- When a record file changes, each sentence that cites it needs to change. When a sentence that cites a record changes, the record needs to be in the diff. Else exit 1, naming the record and the first line of each sentence. A refusal demands the record only for the sentences that cite it.
- One PR body line per record clears it: `Rules checked: <record> — no change`, with an em dash. Add the line to the PR body, then push a commit: a body edit alone starts no run, and a re-run reads the old body. It says the author read the citing sentences and they still hold.
- The `-U0` hunk parser is local to `compliance_probes.py`, not the one in `lint/stale_cites.py`. That one (`added_markdown_lines`) keeps added `.md` lines only, reads its own `git diff -M --raw -z` start, and imports the hooks modules. `aligned` also needs removed lines (a deleted record's old `Home:` line, and the base side of a rule file), from its one read. Like the stale_cites parser, it reads each hunk by its counts.

Cost: one git diff read per PR, pinned by `AlignedCost` in `lint/test_compliance_probes.py`, which asserts one git call and no file written. It starts one python process per run (unmeasured). It writes no file, no log, no timer and no long-lived process. The `restates` step costs one python start per child CI run, and one per run of skill `compliance-check` (unmeasured). It reads files and writes none. It starts no timer and no long-lived process.

## Not mechanized

- A paraphrase. A line that says a ruling in other words passes. A line with under 12 shared words passes, a citation included.
- Copies of rule text from the root `CLAUDE.md`. The check reads decision records only. For example, a child line that repeats the root rule on how a lane merges passes. That rule changes at the cutover (decision `all-repos-switch-together`), so the copy then goes stale and nothing flags it.
- A shared run under 5 words.
- A copy inside a heading, an HTML comment or a code span.
- A copy shorter than 12 words, such as a one-sentence grant line. See debt `short-copy-passes` (the gap for short copies).
- A rule unit that restates a record with no citation of it. `aligned` follows citations only; `restates` flags copies of 12 or more words.
- A rule sentence in `agents/`, `skills/` or `output-styles/` Markdown that cites or copies a record. `aligned` reads rule files only. See debt `aligned-skips-agents-skills` (the gap for those files).
- A sentence whose new text matches another sentence of the file's base side. It counts as unchanged.
- A citing sentence that the PR deletes. The check reads head sentences only, so the deletion demands nothing of the record it cited (`lint/compliance_probes.py` `probe_aligned`).
- A `Rules checked:` line that is false. The check reads that the line is there, not that the author read the units (`lint/compliance_probes.py` `RULES_CHECKED`).
- Owner words that a record keeps in code spans. The check never indexes them, so a copy of 12 or more of them passes. See debt `record-code-spans-unindexed` (the gap for code-span words).

## Why

A copy goes stale the next time the owner rewrites the record. A session in the child repo then reads two answers to one question, and the stale one is nearer.

Kind: process
Home: lint/compliance_probes.py
