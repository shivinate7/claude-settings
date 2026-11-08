# A message to another session names only refs that exist

## The ruling

A `send_message` call to another session is refused when its text names a commit, a pull request or a PR comment of this repo that does not exist. The refusal names each missing ref. The guard stops a mistake Claude makes, not an attacker (`guard-guards-mistakes-only`).

Kind: build
Plan: docs/decisions/send-message-refs-resolve.md#the-ruling (all)
Home: hooks/guard.py

**Incident.** 2026-11-08, lane `notes-fix-large-1` sent batch runner 8 a record link it typed before the post returned. **Harm stopped:** a session acts on a ref that does not exist.

**Ruling.** Coordinator, 2026-11-08 02:30 CST: reuse the sha function of decision `agent-report-shas-resolve` on `send_message`. Name the repo each ref resolves against, and state the cost of each GitHub read.

## What is judged

The PreToolUse guard judges `mcp__claude-code-remote__send_message`, from any session, main or agent. The text is `tool_input.message`. Rule `message-ref-missing` (deny). An owner override lifts it.

- **Commit sha.** The token rule of `agent-report-shas-resolve`, resolved in the repo of the payload's `cwd`. A `github.com/<owner>/<repo>/commit/<sha>` URL of this repo is judged too.
- **Pull request.** `PR #N`, `PR N`, `pull request #N`, `#N (PR)`, in any case, and every number of a list such as `PRs 7 and 8` or `PRs #7, #8 and #9`. After a singular `PR`, a further number needs its own `#`, so `PR #7, 12 files` names one PR. Also a `github.com/<owner>/<repo>/pull/N` URL of this repo, with or without a scheme and with any tail such as `/files`. A bare `#N` with no `PR` word is skipped: it may be an issue or an item. A merged or closed PR keeps its `refs/pull/N/head` (measured: #1 and #1764 of this repo), so it passes.
- **PR comment.** A `github.com/<owner>/<repo>/(pull|issues)/N#issuecomment-<id>` URL of this repo.

## Which repo

"This repo" is the `owner/repo` of the `cwd` checkout's `origin`. Text that names another repo is skipped:

- A URL to another repo.
- A sha or PR number on a line that names another repo. A line names another repo when it holds an `owner/repo` that is not this repo, followed by `#`, `@` or `:` (such as `acme/widgets#5` or `acme/widgets: PR #5`). An `owner/repo` with no such mark is a branch or a path (`lane/env-file-scope`, `origin/main`, `hooks/guard_merge`) and does not count. `origin/` and `upstream/` never count. An `owner/repo` whose name ends in a file extension (`hooks/guard.py`) is a path and never counts.

With no origin, only shas are judged.

## Fail open

- No git repo, no origin, or git fails: allowed.
- `ls-remote` or `gh` fails, times out (5 s each), or is missing: allowed. The guard's answer carries `additionalContext` that names each ref it could not check, so the sender reads it in the tool result. The answer holds no `permissionDecision`, since an explicit allow would skip a permission prompt that main shows. No log is written.
- Only a clear answer refuses: no `refs/pull/N/head` in a good `ls-remote`, or `gh api` exiting non-zero with `HTTP 404` on stderr. Any other gh failure leaves the link unchecked.
- At most 5 comment links are read per send. The rest are named as unchecked.
- A shallow clone with a missing sha: allowed, logged `report-sha-shallow`.

## Cost

Per send, at most:

- one `git config --get remote.origin.url`, when the text names a PR, or holds a pull, issue, comment or commit URL, or a sha on a line with an `owner/repo` mark
- one `git cat-file --batch-check` for all shas (10 s timeout), and one `rev-parse --is-shallow-repository` on a miss
- one `git ls-remote origin` for all PR numbers (5 s), a network read of about 0.6 s, measured once from a cloud container
- one `gh api repos/<owner>/<repo>/issues/comments/<id>` per comment link, up to 5 (5 s each), a network read

The worst case is about 45 s. A message with no ref starts no process. A guard.log line only for a refusal or a note. No file, timer or long-lived process.

## Known gaps

- An issue number, a branch name and a record path are not judged.
- A fork's `origin` lacks the upstream's `refs/pull`, so a PR of the upstream reads as missing. Fix: none — the owner's repos are not worked from forks. Until: 2026-11-21.
- A ref that exists but is the wrong one passes.
- A repo whose name ends like a file extension (`vercel/next.js: PR #5`) reads as a path, so its PR is judged against this repo and can refuse.
- A path or branch followed by `:` reads as another repo, so its line is skipped (`lane/x: head <sha>`, `hooks/guard_merge: PR #5`).
- A PR list split across a line break is judged on its first line only.
- Another repo's PR named with no `owner/repo` on its line is judged against this repo and can refuse.
- The URL-word pattern takes time that grows with the square of a long unbroken token: 1.7 s at 32,000 characters. A timeout fails open (note report-sha-url-word-slow).
