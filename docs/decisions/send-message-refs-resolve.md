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
- **Pull request.** `PR #N`, `PR N`, `PR: #N` and `PR (#N)` (with the `#`, so `PR: 2500 lines` is no PR), `**PR** #N`, `` PR `#N` ``, `PR number N`, `pull request #N` and `#N (PR)`, in any case. Every number of a list counts, such as `PRs 7 and 8`, `PRs #7, #8 and #9`, `PRs #7 #8`, `PRs #7 or #8` and `PRs #7 + #8`. After a singular `PR`, a further number needs its own `#`, so `PR #7, 12 files` names one PR. Also a `github.com/<owner>/<repo>/pull/N` URL of this repo, with or without a scheme and with any tail such as `/files`. A bare `#N` with no `PR` word is skipped: it may be an issue or an item. A line whose `PR` or `pull` word comes before a `#N` with other words or marks between them is judged (`PR is #N`, `PR opened: #N`, `PR [#N]`, `pull #N`). So is this repo's own `owner/repo#N`. The words between hold no digit, `#`, `.`, `;`, `!` or `?`, number at most 6, and hold no `issue`, `ticket`, `bug`, `item`, `finding`, `debt`, `closes`, `fixes` or `resolves`. The `PR` word stands alone: `pr` inside a name such as `msg-ref-pr-forms` is no PR word. The word `pull` counts only right before its number (`pull #N`) or in `pull request`. A PR word judges each `#N` after it on the line, by the same rule, so `PR #7 is #8` names both. `owner/repo#N` after an issue word (`Issue o/r#5`) is no PR. A merged or closed PR keeps its `refs/pull/N/head` (measured: #1 and #1764 of this repo), so it passes.
- **PR comment.** A `github.com/<owner>/<repo>/(pull|issues)/N#issuecomment-<id>` URL of this repo.

## Which repo

"This repo" is the `owner/repo` of the `cwd` checkout's `origin`. Text that names another repo is skipped:

- A URL to another repo, and a PR number in that URL's link text (`[PR #5](https://github.com/acme/widgets/pull/5)`).
- A sha, PR number or comment link on a `> ` quoted line or inside a double-quoted span. Quoted text may come from another repo (the quote rule of `agent-report-shas-resolve`).
- A sha or PR number on a line that names another repo. A line names another repo when it holds an `owner/repo` that is not this repo, with a mark:
  - `#` or `@` right after it, in any case (`acme/widgets#5`).
  - `:` or the word `PR` right after it (`acme/widgets: PR #5`, `acme/widgets PR #5`). This mark counts only when owner and name are lowercase letters, digits, `-`, `_` or `.`, and neither is all digits. So `CI/CD:`, `Done/Next:` and `2/3:` are no marks.
- An `owner/repo` with no mark is a branch or a path (`lane/env-file-scope`, `origin/main`, `hooks/guard_merge`). `origin/` and `upstream/` never count, and nor do this repo's branch prefixes (`lane/`, `archive/`, `claude/`, `handoff/`), so `lane/x PR #5` is judged against this repo. An `owner/repo` whose name ends in a file extension (`hooks/guard.py`) is a path.

With no origin, only shas are judged.

## Fail open

- No git repo, or git fails: allowed.
- Every fail-open below names each ref it could not check, as the next line says: a sha in a shallow clone or when git fails, and a PR or comment when there is no origin. With no origin, every pull and comment URL is named, since none can be matched to this repo.
- `ls-remote` or `gh` fails, times out (5 s each), or is missing: allowed. The guard's answer carries `additionalContext` that names each ref it could not check, so the sender reads it in the tool result. The answer holds no `permissionDecision`, since an explicit allow would skip a permission prompt that main shows. No log is written, except `report-sha-shallow` from the shared sha function.
- Only a clear answer refuses: no `refs/pull/N/head` in a good `ls-remote`, or `gh api` exiting non-zero with `HTTP 404` on stderr. Any other gh failure leaves the link unchecked.
- At most 5 comment links are read per send, and at most 20 PRs and 20 shas. The rest are named as unchecked.
- A shallow clone with a missing sha: allowed, and the sha is named as unchecked.

## Cost

Per send, at most:

- one `git config --get remote.origin.url`, when the text names a PR, or holds a pull, issue, comment or commit URL, or a sha on a line with an `owner/repo` mark
- one `git cat-file --batch-check` for all shas (5 s timeout, the same for `git config` and `rev-parse`), and one `rev-parse --is-shallow-repository` on a miss
- one `git ls-remote origin` for all PR numbers (5 s), a network read of about 0.6 s, measured once from a cloud container
- one `gh api repos/<owner>/<repo>/issues/comments/<id>` per comment link, up to 5 (5 s each), a network read

The worst case is 45 s: three git calls at 5 s, `ls-remote` at 5 s, and five `gh` reads at 5 s. The URL-word pattern runs twice on each line, 10.3 s on one 64 KiB unbroken line (measured once), so the total stays under the guard's 60 s hook timeout. A hook timeout allows the call. A message with no ref starts no process. A guard.log line only for a refusal or a note. No file, timer or long-lived process.

## Known gaps

- An issue number, a branch name and a record path are not judged.
- A fork's `origin` lacks the upstream's `refs/pull`, so a PR of the upstream reads as missing. Fix: none — the owner's repos are not worked from forks. Until: 2026-11-21.
- A ref that exists but is the wrong one passes.
- A sha resolves only in the cwd's local clone. A commit pushed from another clone and not yet fetched reads as missing, and the message is refused. The remedy is `git fetch`.
- A repo whose name ends like a file extension (`vercel/next.js: PR #5`) reads as a path, so its PR is judged against this repo and can refuse.
- A lowercase path, label or branch with another prefix, followed by `:` or `PR`, reads as another repo, so its line is skipped (`hooks/guard_merge: PR #5`, `ci/cd: PR #5`).
- With no origin, a commit URL of this repo is not judged. A payload with no `cwd` is not judged, with no notice.
- A repo with a capital letter, marked only by `:` or `PR` (`Acme/Widgets: PR #5`), is judged against this repo and can refuse.
- A PR list split across a line break is judged on its first line only.
- A `#N` that follows a PR or pull word but means something else is judged as a PR (`PR merged, see #3`). Only a PR number that does not exist refuses.
- A made-up PR whose gap breaks those limits passes (`PR for step 2 is #N`, `PR for this bug is #N`, a gap of 7 words). The limits keep issue and step numbers from refusing.
- A PR word joined to the word before it by `-`, `/` or `.` is no PR word, so `mini-PR #8` passes.
- After a gap of other words, a `#` with exactly 6 or 8 digits is read as a colour, not a PR (`the PR sets the border to #000000`). A PR number that long is not judged in that form.
- A line with thousands of PR words is slow to read: 15 s for 10,000 on one 30 KB line (measured once). A hook timeout fails open.
- The sha forms that `agent-report-shas-resolve` skips are skipped here too: `key=<sha>`, a URL word (this repo's compare URLs included) and a line starting `index `.
- Another repo's PR named with no `owner/repo` on its line is judged against this repo and can refuse.
- The URL-word pattern takes time that grows with the square of a long unbroken token: 1.7 s at 32,000 characters. A timeout fails open (note report-sha-url-word-slow).
