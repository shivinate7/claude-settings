# c152 stale branches, step c152 (stale-branch cleanup)

Read 2026-10-28. Cutoff: last commit before 2026-10-14. 77 branches on origin; 15 are stale.
Each stale branch holds 1 to 5 commits not on main, counted with full history and git cherry. None was deletable without a copy.
Each one is now pushed to archive/<branch>. A ls-remote check shows each archive equals its branch head (15 of 15).
The cloud proxy refuses branch deletes (403), so the deletes below run on shiv's Mac.

| Branch | Head | Last commit | Commits not on main |
|---|---|---|---|
| `claude-p-fetch-key` | `d46a7a8bfe7e` | 2026-10-12 | 1 |
| `claude/allow-read-projects-dir` | `db6f2a6c619d` | 2026-09-22 | 1 |
| `claude/eloquent-wozniak-fw72yn-lane-a` | `d86c8164ba2f` | 2026-09-21 | 2 |
| `claude/eloquent-wozniak-fw72yn-lane-d` | `c2e350ebfad4` | 2026-09-21 | 5 |
| `claude/held-agent-a4b6f8c47f47503f9` | `17e06c587215` | 2026-10-08 | 1 |
| `claude/held-agent-acce80db5bcaa966b` | `0bc8c8de891c` | 2026-10-13 | 1 |
| `claude/held-ci-spend` | `233de80c94c2` | 2026-10-06 | 2 |
| `claude/held-cs-agent` | `a242e411ad52` | 2026-10-08 | 2 |
| `claude/ste-ui-full-rules` | `03860bee7089` | 2026-09-28 | 2 |
| `claude/youthful-bell-jd1rwk-mutation` | `1d1d4fe057ef` | 2026-09-18 | 1 |
| `freshness/job-timeouts` | `3ce2a2497a23` | 2026-10-05 | 1 |
| `guard-family-scope` | `5fc0f6cf2759` | 2026-10-12 | 1 |
| `merge-ci-savings` | `6425eea58c9d` | 2026-10-13 | 4 |
| `propose/lessons-from-mailaudit` | `27fea033b29c` | 2026-09-19 | 1 |
| `windows-audit-brief` | `ab81cb8f1baf` | 2026-10-11 | 2 |

Out of scope: batch-oct27y and batch-oct27z are newer than 14 days. archive/* branches are kept.

## Command for shiv's Mac

Run it from a claude-settings checkout. Each delete first checks that its archive copy exists, then uses a lease: if the branch moved since the archive push, git refuses the delete and the branch is kept.

```sh
git fetch origin --prune
while read -r b h; do
  a=$(git ls-remote origin "refs/heads/archive/$b" | cut -f1)
  if [ "$a" != "$h" ]; then echo "SKIP $b: archive missing or differs"; continue; fi
  git push --force-with-lease="refs/heads/$b:$h" origin ":refs/heads/$b" 2>&1 | tail -1
done <<EOF
claude-p-fetch-key d46a7a8bfe7e42edd0264590ce73c4e0ec899a9b
claude/allow-read-projects-dir db6f2a6c619da8d3b7ae46084e480ec522784c47
claude/eloquent-wozniak-fw72yn-lane-a d86c8164ba2f0ca8c7c64d24115d05eaef2cdfc0
claude/eloquent-wozniak-fw72yn-lane-d c2e350ebfad4400fab59f416bd35d0cacff48658
claude/held-agent-a4b6f8c47f47503f9 17e06c5872155a48c522e9c05266274aae57f2cd
claude/held-agent-acce80db5bcaa966b 0bc8c8de891c5202682b10650aea38742a023a42
claude/held-ci-spend 233de80c94c2fd3dfd80d9fb215377b03c62fb01
claude/held-cs-agent a242e411ad5208841c6dc939247ae7815cb8e67f
claude/ste-ui-full-rules 03860bee7089e577d2915c1b10d55bf40327cc6c
claude/youthful-bell-jd1rwk-mutation 1d1d4fe057ef6a452c1ee1c56f9d7f79dd003cc7
freshness/job-timeouts 3ce2a2497a2343f312291171a8f493b667a0f7f2
guard-family-scope 5fc0f6cf2759785243ba9279cbffea38ea9ad27a
merge-ci-savings 6425eea58c9dca7531a235340651a9fe6c5d20e4
propose/lessons-from-mailaudit 27fea033b29c083a41adc782c51dad5f20cec68c
windows-audit-brief ab81cb8f1bafa848c0a2edd357f33ab01460772b
EOF
```
