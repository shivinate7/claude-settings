# Handoff: batch runner for the child repos

This handoff is for the next batch runner of q_max, banchi, degen, joyous and mailaudit. Batch runner 8 (session_013NEJL15CmUPTsMgxECh1fX) wrote it when the owner asked it to wind down (2026-11-02 12:31 CST). The coordinator is session_013NEJL2pASwRjgJDnsvnpNe. Read each PR's state on GitHub before you act, because heads move.

## Held PRs

| Repo | PR | Branch | Head | Waits on |
|---|---|---|---|---|
| banchi | #1003 lane c174, the shell-guard skip | c174-guard-skip-tree | 119c2e857 | Tonight's scheduled check run on main going green, or queue item 166. The PR is ready and green and holds main. Then merge it plainly. |
| banchi | #1005 folder-only CLAUDE.md sections | o3-claude-md-rules | f25397f49 | Queue item 155. It is a draft. |
| q_max | #1011 batch: ci-hygiene, holds lane #1008 | claude/int-batch-qmax-r5 | b602fd459 | Queue item 154. The tool reads main as UNKNOWN, because browser run 41377928751 on main was cancelled. The owner's "merge" names a plain merge, so a completed browser.yml run on main, or the owner's --base-red-ok word, is needed. After the merge, the coordinator closes #1008 as replaced. |
| joyous | #68 pins the tour test clock | test/tour-chip-day | ba8fc5f85 | Queue item 161, pick b: no override, wait for the merge-tool fix. #68 is the fix for main's build red (run 41389182137), so a plain merge refuses until the tool accepts it. |

Queued behind q_max #1011, all drafts: pin #1012 (c2633701d), #1006 (7bf8a510e), #1010 (df93ef675), #1007 (97b3d4693). #1007 conflicts with #1010 in harness/check-invariants.mjs `laneContext`, so the q_max lane merges main into #1007 after #1010 lands. Behind joyous #68: #67, the pin move (d70be0275, draft). The joyous lane brings it up to main after #68.

Notes-only branches with no PR yet. Each joins its repo's next batch:
- q_max `claude/notes-close-refusal` (8c968b7e3)
- joyous `claude/notes-base-red-refusal` (65c4933ff)

## Merge-tool notes

- The tool runs the commit at origin/main in /root/claude-settings. To update it, run `git fetch origin "+refs/heads/main:refs/remotes/origin/main"` there.
- #1067 (stale red-main fix) clears an older red of another event type when a newer passing run exists. It does NOT clear a scheduled red that a newer green dispatch run on the SAME sha replaced (banchi run 41436198024 against 41483723188). Lane red-main-same-sha-green (session_013NEJKzjNAqNMb6b9s2s1Vg) fixes that.
- Auto mode refuses `--base-red-ok` from a batch runner ("CI Bypass"). It also refuses `gh api` PR comments and closes ("External System Writes"). Hand each PR named as replaced to the coordinator, which closes it.
- Run `~/.claude/bin/merge <n> --confirm` as its own command, in the background, from the repo checkout. A `Drops-lines:` trailer counts only in the last paragraph of the commit message, with Co-Authored-By.
- After each resume: get_session in its own turn, then `~/.claude/bin/merge --role batch-runner`.
- Each merge sends the coordinator one line: repo, PR, merge sha and the four pace numbers. The fourth is `n/a (cloud)`.

## Branches left to delete

- degen `pins-d8037a4` (c61c9ca3d): closed #321, never merged, replaced by #322. Archive it first, then delete it.
- banchi `pin-cs-main-49a4165` and degen `pins-49a4165` are already gone.

## Lanes

- banchi: session_013NEJL3SffaYSu5tzgYVhAv
- degen: session_013NEJL23zsFvkMq9tWHapJu
- joyous: session_013NEJKyiQqKEzbn8MHNnmpS
- q_max: session_013NEJL2hUNJQEdygCh3zSxo
- mailaudit: session_013NEJKzn1fifK4dRyquE9WH
