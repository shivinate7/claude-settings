# Plan: deep audit of contradictions, empty promises and overpromises

Owner ask 2026-11-02 16:02 CST; Sonnet sweep added 16:04 CST; pick a (start after the batch merges) and `opus 24h` at 16:05 CST; duplicated source of truth added 17:02 CST.

## Finding kinds
- Contradiction: two texts, or a text and the code, cannot both be true.
- Empty promise: a rule names a check or hook that does not exist, never runs, or does not test the claim.
- Overpromise: the text claims more than the code does ("never", "all files").
- Duplicated source of truth: two places in code or text hold the same list, constant or rule, so one can change without the other. Example: the file-copy list in janitor/mutate_sweep.py `build_scaffold`, beside `mutate_shared.module_files` (owner, 2026-11-02 17:02 CST).

## Scope
claude-settings main; each open PR and branch as its diff to main; the six child repos; every ruling (decision records, handoffs, inbox, waiting page answered items).

## Run 1: sweep (Sonnet)
1. Script, no agents: reuse the drift-audit pilot extractor. List every rule anchor, every "Check:" or "enforced by" line, every owner cite, every never/always/all claim, with file and line. Mark whether each named hook or check exists and is wired in settings or CI.
   The script also lists second copies by contents: string lists, tuples and sets of names or paths, constants and repeated rule sentences that appear in two or more files. It parses source with the language's own parser where one exists (rule building-scanner-respects-strings, scanners respect strings).
2. Sonnet, read-only, one agent per 40 claims: empty promise, overpromise, contradiction candidates, each quoting both sides with file and line. Other Sonnet agents, one per 40 second-copy rows, judge whether the two copies hold the same thing and name each copy's file and symbol.
3. Script, no agents: each quote must match its file and line exactly. Drop the rest.

## Run 2: judge (Opus, 17 agents, pipelined per topic)
Topics: merge path; tiers and roles; models; questions and the page; guards and refusals; records and numbering; artifacts and design; CI and batches.
4. One Opus judge per topic: confirms or kills candidates, reading cited lines only; adds cross-claim contradictions within the topic. For a duplicate, the judge confirms that one copy can change without the other.
5. One Opus refuter per topic: re-reads each confirmed finding at source and tries to disprove it. For a duplicate, it tries to show that both copies read one home. A home is an import, a generated block, or a check. If the two copies differ, the check fails.
6. One Opus write-up: dedups, ranks by expected harm in normal work, and gives each finding one home. A home is a lane, a debt, a note, or an owner question under outcomes-stale-decision-protocol, which sends a stale decision to the owner. Each confirmed duplicate becomes a one-home lane, and the list feeds the one-home check build planned in PR #1106 (one-home-check-design, the design of the one-home check).

## Output
Report on branch audit/deep-1102; lane list added to the next coordinator's handoff. Cost and the Sonnet agent count: unmeasured until step 1 counts claims.
