# Handoff: next claude-settings coordinator

Written by coordinator session_013NEJL2pASwRjgJDnsvnpNe at 13:30 CST, 2026-11-02. The lane plan is in `handoffs/next-coordinator-lanes.md`. The findings are in `handoffs/load-balance-findings.md`.

Read first: next-coordinator-review-outcomes.md (what is on-outcome and what is straying, the freeze, first lanes) and next-coordinator-review-terms.md (term conflicts).

## Rulings with no home yet

- fb-1310-1 (owner 13:10 CST): every clock time given to the owner names its zone, 24-hour. Follow now. A record-writer agent writes the record on branch time-zone-every-time (decision local-time-central, style time-central-24h). Draft PR #1104 (time zone in every time) is open. Roadmap step time-zone-every-time holds the guard check.
- fb-1231-1, fb-1232-1 (owner 12:31 and 12:32 CST): wind down. Spawn no new sessions. Owner 12:42 (fb-1242-1): archive triage last, with batch runner 7. Send nothing non-urgent to the owner. Triage files it, or the coordinator decides. The wind-down is done. This coordinator is the only live session.
- fb-1312-1, fb-1313-1 (grant 13:12 CST, narrowed 13:13 CST): build one narrow check that a writer's reported filing landed. Keep it in the feedback guard (hooks/feedback_guard.py). Rule: page item n must exist in the repo's waiting store. Build it after waiting-data-in-repo merges (owner hold). Until then, read each page item back with ArtifactData.
- fb-1311-3 (standing): send_message confirms delivery only. Verify every filing on origin: roadmap/data/steps/<slug>.json, handoff paths, page items by ArtifactData query.
- fb-1321-1, fb-1322-1 (owner 13:21 and 13:22 CST, pick b): drop STE as a named standard. Write plainly only. A record-writer writes it on branch drop-ste-name (decision plain-prose-lint rewrite, agents/*.md, skills, debt note). Follow-ups: rename the lint, action and CI step. Child repos' CLAUDE.md files name STE. Ask first before you touch another repo. Files lint/ste_gate.py and lint/md_sweep.py are still on main and unwired, though decision ste-guard-fixes-not-nags says deleted.
- fb-2331-1, fb-2324-1, fb-2326-1, fb-2334-1 (standing): owner questions reach the page in the same turn. Home: rule questions-go-to-owner, built by PR #1070 (report guard, dropped from batch 69). Live sessions report unfiled owner questions to the coordinator.
- Homed earlier, keep the ids: fb-1449-2, fb-1517-1, fb-1531-1, fb-1532-1, fb-0409-1, fb-0429-1, fb-1716-2, fb-1719-2, fb-1726-1, fb-1737-1, fb-1737-2, fb-1737-3, fb-1754-1, fb-1824-1, fb-1843-1, fb-1844-1, fb-1845-1, fb-1846-1, fb-1848-1, fb-1848-2, fb-1850-1, fb-1850-2, fb-1852-1, fb-1927-1, fb-1927-2, fb-1927-3, fb-2049-1, fb-2050-1, fb-2051-1, fb-2051-2, fb-2054-1, fb-2057-1, fb-2102-1, fb-2105-1, fb-2106-1, fb-2107-1, fb-2108-1, fb-2132-1, fb-2134-1, fb-2134-2, fb-2222-1, fb-2222-2, fb-2223-1, fb-2237-1, fb-2237-2, fb-2243-1, fb-2252-1, fb-2254-1, fb-2255-1, fb-2257-1, fb-1041-1 (lane undo check), fb-1041-2 (child repos cite records), fb-1041-3 (branch cleanup), fb-1052-1, fb-1100-1, fb-1112-1, fb-1149-1, fb-1154-1.

## Open owner items

Home: page collection `items`, field n, status open. Page: https://claude.ai/artifact/RddcgXbB6SvTrFZHPmsvFx. Read the live items first. Only triage writes the page, and triage is archived.

- 154 qmax-1011-batch. 155 banchi-codex-rules (no pick yet; blocks banchi #1005). 166 newer-run-clears-red (open). 170 branch-delete-list (paste for the owner's Mac).
- 161 joyous-68-base-red: owner picked b. No override. Wait for the merge-tool fix.
- 153 local-reach-plan: triage records "last answer b". The lane says no answer saved. Unknown until read.
- 150 shivpedia-plan-signoff, 152 grant-plan-signoff, 130 3d-first-target, 131 3d-asset-storage, 91, 163, 167, 168, 169 (drop the self-reported tally).
- Decided: item 109 (pick b, no rotation limit), item 158 (every question to the page the same turn), item 165 (one excuse line, Drops-lines).

## Goal

"Restart the flywheel" from the freeze record, losing no work. Source: owner's opening message, 2026-10-31 14:12 CDT. Phase now: the wind-down left the coordinator alone. The next coordinator restarts the trio (triage, batch runner, lanes).

## Working premises

- P1 [read] claude-settings main is 5a5f081e, batch 69 (PR #1103: #1061, #1097, #1101), merged 13:12 CST. Source: git fetch and gh api. Checked 2026-11-02 13:15 CST.
- P2 [read] PR #1100 (page title Cockpit, head 6e5e38ce) is a draft on origin, not ready. Both older handoffs say ready. Source: gh api pulls/1100, per the overlap analysis. Checked 2026-11-02 13:25 CST.
- P3 [read] Only PR #1061 still needs closing as replaced. #1097 and #1101 are closed and merged. Content of #1061 is on main through #1103. Source: origin compare in the analysis. Checked 2026-11-02 13:25 CST.
- P4 [ruling] The coordinator never merges. Batch runners run every merge (owner 2026-11-01 21:34 CST). Runner 8 (child repos) is archived, so banchi #1003 (119c2e85, green) has no merger. Source: owner, c174 handoff. Checked 2026-11-02 12:53 CST.
- P5 [read] The owner's Mac session is unreachable from the cloud. The owner pastes prompts. Auto mode refuses gh closes, ref deletes (403) and --base-red-ok. Source: get_session, runner handoffs. Checked 2026-11-02 13:13 CST.
- P6 [notes] Triage is the only writer of the page and the roadmap branch (guard roadmap-one-writer). With triage archived, nobody writes either until triage restarts. Source: session-tiers, triage handoff. Checked 2026-11-02 13:25 CST.
- P7 [notes] Feedback guard reads homes from cwd. End each turn in /home/user/claude-settings. Inbox items go under their own `###` heading. Checked 2026-11-02 13:13 CST.
- P8 [read] 37 done, 24 open and 4 unknown older owner sessions (01*, Aug to Oct) are not lanes. Left alone. List: scratchpad classified.tsv. Source: Explore agent. Checked 2026-11-02 12:50 CST.
- P9 [assumed] Shallow clones at /root/claude-settings give false off-main answers. Unshallow before an ancestry check. Source: banchi o3 and q_max handoffs. Checked never.
- P10 [read] 277 remote branches on claude-settings at 13:15 CST. The 136-branch delete list is item 170. Source: git fetch. Checked 2026-11-02 13:15 CST.

## Where things stand

- Branch: main at 5a5f081e. Open PRs: `gh api "repos/shivinate7/claude-settings/pulls?state=open&per_page=100"`. Same query for banchi, q_max, joyous, degen, mailaudit.
- Lane handoffs: `handoffs/*.md` across origin branches (git grep on origin). The triage handoff (roadmap branch, handoffs/triage-claude-settings.md) lists the archive order. Runner handoffs: branches handoff/batch-runner-claude-settings and handoff/batch-runner-child-repos.
- All flywheel sessions (013NEJ*) are archived. Open lane work is branches and draft PRs only.
- Roadmap steps not started (Ready, need a new session): option-key-guard-gap, ask-reaches-writer, time-zone-every-time. The report-guard LANDING_TOOLS gap (trial lg, pick a, owner 2026-11-01 16:23) needs a step. Ruling 12:50 CST: mockup-homes reads open steps only.
- Drafts that carry a lane handoff to drop before merge: #1051 (local-session-reach), #1034 (craft-book), and the other-clone-cd-refuse branch.

## Work in flight

- Record-writer agent on branch drop-ste-name: draft PR pending.
- PR #1104 (time zone in every time, head 3a3375fb): draft, lint passes.
- Workflow run wf_7d7b23ee-49f: writes these three files on branch handoff/next-coordinator. No PR.
- No servers. No timed check-ins.

## Next steps

1. Verify branch handoff/next-coordinator on origin. Read the three files. Tell the owner where they are. The owner rules on the findings that need a ruling.
2. Verify the branch and draft PR from the drop-ste-name record-writer.
3. Restart the trio in this order: triage, then a batch runner for claude-settings, then lanes from the lane plan. Triage goes first, because the page and the roadmap have no writer. Say the session shape in one line first.
4. Read page item 153 and the live items. Route each answer to the session that owns it. An item whose owner is an archived session moves to the coordinator.
5. Start batch 70 with #1100 alone. Mark it ready first.
6. Ask a session on the owner's computer to close #1061 as replaced and run the item 170 delete paste (standing grant "Acts the cloud refuses").
7. Final wind-down report: Done (archives), open owner items, unstarted steps, older owner sessions left alone.
8. End each turn in /home/user/claude-settings.

## Files and commands

- Inbox: /root/.claude/handoffs/4a3e5715-0a07-53a0-b65e-c228cc13d462.inbox.md.
- Scratchpad: /tmp/claude-0/-home-user/4a3e5715-0a07-53a0-b65e-c228cc13d462/scratchpad/ (classified.tsv, archive-list.txt, archive-result.txt, wind-down-msg.txt, page-items/).
- Verify a handoff: `git fetch -q origin <branch> && git cat-file -e <sha>:<path>`.
- Page item check: ArtifactData query `items` where n in [...].
- Checkouts: /home/user/{claude-settings,q_max,banchi,degen,joyous,mailaudit}.
- Lint: `~/.claude/bin/verdict ~/.claude/bin/ci-job checks --lint`.
