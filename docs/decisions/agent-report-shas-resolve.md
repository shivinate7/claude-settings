# An agent's report names only commits that exist

## The ruling

An agent's hand-back that names a commit sha its repo does not hold is refused, and the refusal names each missing sha. The guard stops a mistake Claude makes, not an attacker (`guard-guards-mistakes-only`).

Kind: build
Plan: docs/decisions/agent-report-shas-resolve.md#the-ruling (all)
Home: hooks/guard.py

**Incident.** 2026-11-08, lane `comment-check-scans-shell`: Haiku test-authors made no edit and reported the shas 8c1f0e2a7, 5b7d10a42, e7c35b1d0 and 3d2a91f4c. `git cat-file -e` fails on each. No guard refused, and the orchestrator nearly took a false "done". **Harm stopped:** a made-up commit read as finished work.

**Ruling.** Owner, 2026-11-07 13:20 CST: a gap gets a fix (step `agent-report-shas-resolve`).

## Where it runs

One function in `hooks/guard.py` judges a report's text. Two callers use it:

- **PreToolUse, `SubagentHandback`.** Since Claude Code 2.1.271, an agent's report is the `message` of this call (code.claude.com/docs/en/hooks.md, SubagentStop). A missing sha refuses the call with `report-sha-missing` before the report is delivered. The agent fixes its report and hands back again.
- **SubagentStop** (`judge_stop`), the fallback, reads `last_assistant_message`. A missing sha blocks the first stop. A second stop (`stop_hook_active`) is allowed and logs `report-sha-unresolved`, so an agent never loops. A builder stop that breaks `builder-diff` too gets one block with both reasons.

The payload must carry a valid `agent_id`. Every agent type is judged, reviewers and Explore included, since any role can cite a commit. The main session is not judged.

## What counts as a sha

- A token of 7 to 40 lowercase hex characters, with at least one digit and one letter a-f.
- A token that touches `-`, `_`, `/`, `#`, `.` or `@` is not one. That rules out agent ids, UUIDs, colours, URLs, file names and `owner/repo@sha`.
- A sentence mark after the token (`.`, `,`, `;`, `:`, `)`, `]`) followed by a space or the end of the text does not count as touching, so "Fixed in 8c1f0e2a7." is judged.
- A token inside a double-quoted span or on a `> ` quoted line is skipped, since quoted text may come from another repo. A quoted span ends at the line end. A backticked sha is checked.
- A sha resolves when `git cat-file --batch-check` finds it as `<sha>^{commit}` in the repo of the payload's `cwd`. A short sha that matches more than one object is ambiguous, not missing, and passes.

## Fail open

- No git repo at `cwd`, or git fails: allowed.
- A shallow clone (cloud clones fetch 50 commits) with a missing sha: allowed, and logged `report-sha-shallow`, since an old main sha may sit beyond the clone's depth.

## Cost

One `git cat-file --batch-check` process per judged hand-back or stop that holds a sha-like token. When a sha is missing, one more `rev-parse --is-shallow-repository`. None when the report holds no such token. A guard.log line only for a refusal or a note. No file, timer or long-lived process.

## Known gaps

- A sha that exists but that the agent did not make (an old commit) passes. This check proves the commit exists, not that the agent did the work.
- A sha written in uppercase is not read.
