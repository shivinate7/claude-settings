# Lane standing rules (orchestrator session_013NEJL1XXYYo8v15nsrgKv7)

- Message the orchestrator (send_message to session_013NEJL1XXYYo8v15nsrgKv7) only with a green, reviewed head, or when blocked on something only it or shiv can settle. Everything else goes in roadmap/outbox/<your-slug>.md (roadmap branch; pull first, push direct).
- Every message is 5 lines or fewer: what changed, head commit, test results, open issues.
- Before you stop or pause, push your work and update your outbox note so a fresh session can resume from it.
- Never push to any repo other than claude-settings. Use gh api (REST), never gh pr. GraphQL is 403.
- Never rebase onto main, never merge to main, never touch files outside your step. Merge origin/main INTO your branch (merge commit) only when told.
- Inside the lane: a builder agent writes the failing test first and shows it red, then the fix, then runs the local gates through `bin/verdict` (`PATH=$PWD/bin:$PATH bin/verdict ci-job gates --lint` plus the suites you touch). A fresh reviewer agent that never saw the build reviews, up to 3 rounds; the builder fixes between rounds. Guard, gate or check changes get the net-value test after round 3.
- Models: Opus for guard, hook, merge-gate and CI code, design, and reviews of those; Sonnet for other building and reviewing; Haiku only for trivial mechanical edits.
- Lane PRs stay drafts; CI skips drafts. "Green" means the local gates pass. Open a draft PR to main via gh api REST.
- Before handing over, also run `python3 lint/check_silent_undo.py --upstream origin/main --head HEAD --strict`; an intended drop needs a `Drops-lines: <path> -- <reason>` trailer on a real commit.
- Use GLOSSARY.md names (e.g. "agent", not the retired "subagent").
- The guard refuses `git pull -q`, `git push -q` and `>/dev/null` on git writes: end those lines with `2>&1 | tail -1`. pytest is absent: `python3 -m unittest`.
- A question for shiv: a "Deferred: why" line in your outbox note, push, tell the orchestrator, pause.
