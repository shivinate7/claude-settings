Done
- OTHER: audited /home/user/shivinate7/mailaudit/CLAUDE.md at main 17d26a6 (merge of PR #188, audit owner answers). It is 245 lines, so the size check warns (limit 200). AGENTS.md is a symlink to CLAUDE.md (mode 120000). There is no .claude/CLAUDE.md. Target after the cuts: about 60 lines.
- Class counts (headings, intros and blanks count with their section's main class): KEEP 56, PATH 136, DUP 30, MOVE 20, STALE 3.
- Main constraint: claim 5 of the record check (no orphan, /home/user/shivinate7/mailaudit/check-records.mjs:318-357) fails any record that has no `- `slug`` bullet in CLAUDE.md or a .claude/rules file. So every PATH or DUP bullet must move to a rules file, unless the owner deletes the record. Only the command fence and the prose cuts can go outright.
- 5 biggest cuts:
  1. "Sync, the remote and the token", L76-108 (34, PATH). Move to a new rule with paths `src/entry.jsx`, `src/sync-rules.mjs`, `src/remote-rules.mjs`, `src/merge-rules.mjs`, `worker/**`. Its 10 "Retired:" bullets are true. Three of them still guard code in src/entry.jsx until slice S3: `pushforce-sha-only-after-write`, `peek-is-three-valued`, `photo-writes-wait-one-second`.
  2. "Storage", "Envelope photos" and "Saved versions", L62-75 and L110-141 (44 PATH; keep 3 architecture lines: `single-file-architecture`, `storage-split-three-adapters` and the intro). Move to rules on `src/photo-rules.mjs`, `src/version-rules.mjs`, `src/entry.jsx`, `src/b64.mjs`.
  3. "Open threads" and "Measurements", L184-226 (35). The threads go to the sync rule; claim 7 accepts the `## Open threads` heading in a rules file. The measurements split across screens.md, native.md and testing.md. All 3 STALE lines are here:
     - L197 `the-token-used-to-span-two-repos` is listed as open, but its Status reads "closed".
     - L198 `watchdog-lives-in-private-repo` is listed as open, but the record is retired.
     - L225 `switch-thirds-and-seal` measures the view switch that commit 250823d removed (L11a).
  4. The "Build and deploy" fence, L228-245, plus L31-35 (20 MOVE, 3 DUP). The fence copies the package.json scripts and the `build-and-deploy` record. check-docs blanks fences, so nothing checks it, and it already leaves out `check:rules`, `check:screens` and `check:golden`. L31-35 copies the header of check-records.mjs:7-18.
  5. Restated parent rules, L19-22, L30, L40-48 and L203-211 (23 DUP): `outcomes-decision-is-argument`, `outcomes-stale-decision-protocol`, `verification-report-unknown-reads`, `git-one-record-per-question`, `speak-rewrite-superseded-in-place`, `tokens-never-load-whole-doc`, `git-cite-by-id`, `tokens-folder-rules-load-by-path`. The "More index" section also repeats .claude/rules/README.md.
- "Build, CI and assets", L152-173: 11 bullets are PATH (`.github/workflows/**`, `icon/**`, `build.mjs`, `docs/decisions/**`). 4 are partial DUPs: `main-moves-only-by-pr`, `records-hold-current-text-only`, `invariants-cited-by-slug`, `debts-hold-known-gaps`. Each of those records adds a local fact (for example the all-jobs-passed check, admins included), so their bullets must move, not vanish.
- KEEP rules that are wrong or unclear:
  - L37-38 says a Status line is "the only thing" that separates open from settled. That is false. Settled records also carry one: `the-public-seed` ("retired"), `sync-revamp-cloudflare` ("ruled"). A record is open because it is listed under Open threads.
  - The counts at L24, L26, L31 and L51 ("8 records", "11 records", "eight things", "Eight rules") are true now, but I found no reader for them in check-docs.mjs or check-records.mjs (`verification-checked-reader-for-numbers`).
- Rules files:
  - debts.md (`docs/debts/**`) and testing.md (`test/**`) are well scoped.
  - native.md's glob `src/*-rules.mjs` also catches `merge-rules` and `remote-rules`, which build.mjs:16 does not bundle into the native app.
  - `build.mjs` is in both native.md and screens.md, so one read loads about 240 lines. Why screens.md names `src/merge-rules.mjs` and `LedgerStore.swift`: unknown.
  - No rule covers `src/entry.jsx`, `src/b64.mjs`, `worker/**` or `icon/**`.
- Mechanical check: check_claude_md_size.py would have warned, but it only warns and mailaudit CI does not run it. Extending claim 7 to refuse a closed or retired Status under Open threads would have caught the 2 stale threads.

Input Needed
- Owner call: delete the retired records (git keeps them, citations need fixing) or move their bullets to a rules file scoped to `docs/decisions/**`.