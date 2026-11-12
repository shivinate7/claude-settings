# A message to another session names only refs that exist

## The ruling

A `send_message` call to another session is refused when its text names a commit, a pull request or a PR comment of this repo that does not exist. The refusal names each missing ref. The guard stops a mistake Claude makes, not an attacker (`guard-guards-mistakes-only`).

Kind: build
Plan: docs/decisions/send-message-refs-resolve.md#the-ruling (all)
Home: hooks/guard.py

**Incident.** 2026-11-08, lane `notes-fix-large-1` sent batch runner 8 a record link it typed before the post returned. **Harm stopped:** a session acts on a ref that does not exist.

**Ruling.** Coordinator, 2026-11-08 02:30 CST: reuse the sha function of decision `agent-report-shas-resolve` on `send_message`. Name the repo each ref resolves against, and state the cost of each GitHub read.

## What is judged

Rule `message-ref-missing` judges `mcp__claude-code-remote__send_message` only when the call has no `agent_id`, a session's own call. Rule `agent-no-remote-tools` refuses an agent's call first, and an override that lifts it ends the judge before this check. The text is `tool_input.message`. An owner override lifts this rule's refusal. Two other rules also judge this tool: `lane-one-topic`, before this check, on a lane brief; `message-time-matches-clock`, after it, on a header stamp.

- **Commit sha.** The token rule of `agent-report-shas-resolve`, resolved in the repo of the payload's `cwd`. A `github.com/<owner>/<repo>/commit/<sha>` URL of this repo is judged too.
- **Pull request.** `PR #N`, `PR N`, `PR: #N`, `PR (#N)`, `**PR** #N`, `` PR `#N` ``, `PR number N`, `pull request #N` and `#N (PR)`, in any case. `PR: #N` and `PR (#N)` need the `#`, so `PR: 2500 lines` is no PR. Every number of a list counts, such as `PRs 7 and 8` or `PRs #7, #8 and #9`. So do `PRs #7 #8`, `PRs #7 or #8` and `PRs #7 + #8`. After a singular `PR`, a further number needs its own `#`, so `PR #7, 12 files` names one PR. Also a `github.com/<owner>/<repo>/pull/N` URL of this repo, with or without a scheme and with any tail such as `/files`. A bare `#N` with no `PR` word is skipped: it may be an issue or an item. A `PR` or `pull` word with other words or marks before its `#N` is judged too (`PR is #N`, `PR opened: #N`, `PR [#N]`, `pull #N`). The words between them hold no digit, `#`, `.`, `;`, `!` or `?`. They hold at most 6 words and at most 200 characters. Words count ASCII letters and apostrophes, so a letter outside ASCII splits a word into pieces. They hold no `issue`, `ticket`, `bug`, `item`, `finding` or `debt` word (plurals too), and no closing verb: `closes`, `closed`, `closing`, `fixes`, `fixed`, `fixing`, `resolves`, `resolved` or `resolving`. A second PR word ends the gap, and its own pass judges the numbers after it. The `PR` word must stand alone, so `pr` in `msg-ref-pr-forms` is no PR word. `pull` counts only right before `#N` or in `pull request`. Each `#N` after the word is judged the same way, from the number before it, so `PR #7 is #8` names both. This repo's own `owner/repo#N` counts as a PR too, unless an issue word or a closing verb comes just before it (`Issue o/r#5`, `Fixes o/r#5`). A merged or closed PR keeps its `refs/pull/N/head` (measured: #1 and #1764 of this repo), so it passes.
- **PR comment.** A `github.com/<owner>/<repo>/(pull|issues)/N#issuecomment-<id>` URL of this repo.

## Which repo

"This repo" is the `owner/repo` of the `cwd` checkout's `origin`. Text that names another repo is skipped:

- A URL to another repo, and a PR number or a sha in that URL's link text (`[PR #5](https://github.com/acme/widgets/pull/5)`, `[0123abc](https://github.com/acme/widgets/commit/0123abc)`).
- A sha, PR number or comment link on a `> ` quoted line or inside a double-quoted span. Quoted text may come from another repo (the quote rule of `agent-report-shas-resolve`).
- A sha or PR number on a line that names another repo. A line names another repo when it holds an `owner/repo` that is not this repo, with a mark:
  - `#` or `@` right after it, whatever its case (`acme/widgets#5`).
  - `:`, or the word `PR` or `PRs`, right after it (`acme/widgets: PR #5`, `acme/widgets PR #5`). This mark counts only when owner and name are lowercase letters, digits, `-`, `_` or `.`, and neither is all digits. So `CI/CD:`, `Done/Next:` and `2/3:` are no marks.
- An `owner/repo` with no mark is a branch or a path (`lane/env-file-scope`, `origin/main`, `hooks/guard_merge`). `origin/` and `upstream/` never count. Nor do this repo's branch prefixes (`lane/`, `archive/`, `claude/`, `handoff/`), so `lane/x PR #5` is judged against this repo. An `owner/repo` whose name ends in a file extension (`hooks/guard.py`) is a path.

With no origin, only shas are judged, and each PR or comment link is named as unchecked. In a cwd that is no git repo, a PR or comment link is not judged and not named.

## Fail open

- In a cwd that is no git repo, each sha is named as unchecked, and a PR or comment link is allowed with nothing printed.
- A git call that fails or times out: each sha it could not check is named as unchecked, and the message is allowed.
- A shallow clone with a missing sha: allowed, and the sha is named as unchecked.
- With no origin, or when `git config` fails, each PR and comment link is named as unchecked, since none can be matched to this repo.
- `ls-remote` or `gh` fails, times out (5 s each), or is missing: allowed. The guard's answer carries `additionalContext` that names each ref it could not check, so the sender reads it in the tool result.
- The `additionalContext` holds no `permissionDecision`. An explicit allow would skip the permission prompt that the session shows.
- The `additionalContext` prints only when the call is allowed. A refusal prints its own reason instead.
- Only a clear answer refuses: no `refs/pull/N/head` in a good `ls-remote`, or `gh api` exiting non-zero with `HTTP 404` on stderr. Any other gh failure leaves the link unchecked.
- At most 5 comment links are read per send, and at most 20 PRs and 20 shas. The rest are named as unchecked.
- An allowed answer writes no log, except `report-sha-shallow` from the shared sha function.

## Cost

Per send, at most:

- One `git config --local --get remote.origin.url` runs, at most once, when unquoted text holds one of these:
  - a PR number, such as `PR #N` or `#N (PR)`;
  - an `owner/repo#N` of any repo, with or without a PR word;
  - a `github.com` pull, issues or commit URL, of any repo. An issue link starts it too, though nothing in it is judged;
  - a markdown link to a `github.com/<owner>/<repo>/` path, of any repo;
  - a sha on a line that holds `owner/repo` followed by `#`, `@`, `:` or `PR`. The mark test runs before the other-repo test, so a sha beside a path such as `hooks/guard.py:3099` also starts it.
- One `git cat-file --batch-check` runs for all shas, and one `git rev-parse --is-shallow-repository` on a miss.
- One `git ls-remote origin` runs for all PR numbers. Measured once: about 0.6 s, from a cloud container.
- One `gh api repos/<owner>/<repo>/issues/comments/<id>` runs per comment link, up to 5. It is a network read.
- Each git and gh read has a 5 s limit.

The limits add to 45 s: `git config`, `git cat-file`, `git rev-parse`, `git ls-remote` and five `gh` reads, at 5 s each. The URL-word pattern runs at most twice on a line. Its time is linear in the line's length: 64,000 letters took 0.002 to 0.12 s across runs, and 256,000 took 0.008 s in one run, on one machine. The guard's PreToolUse hook timeout is 60 s (`settings.json`). The pattern has no cap in the code, so a line long enough to pass that timeout is possible; that line's time is unmeasured. Whether a timeout allows the call is the harness's rule, not this code's. On a timeout, the code writes nothing.

The PR gap scan reads at most 200 characters after each PR word, so its time is linear in the line's length. Measured once, by a test-author and a reviewer: 4,000 distinct `PR #N` and 40,000 `PR ` words on one line each took about 0.2 s. Before the cap they took 12 s and 30 s. The suite bounds each case at 5 s, except on Windows.

A message with no sha, no PR number, no `owner/repo#N` and no `github.com` link of the kinds above starts no process. A message whose only ref is a sha on a line with no mark starts only the `git cat-file`, and on a miss the `git rev-parse`. A guard.log line is written only for a refusal, or for `report-sha-shallow` on a shallow clone. The check writes no file of its own, and starts no timer or long-lived process.

## Known gaps

- An issue number, a branch name and a record path are not judged.
- A fork's `origin` lacks the upstream's `refs/pull`, so a PR of the upstream reads as missing. Fix: none — the owner's repos are not worked from forks. Until: 2026-11-21.
- A ref that exists but is the wrong one passes.
- A sha resolves only in the cwd's local clone. A commit pushed from another clone and not yet fetched reads as missing, and the message is refused. The refusal says to check each ref with git or gh. A `git fetch` in that clone makes such a commit resolve.
- A repo whose name ends like a file extension (`vercel/next.js: PR #5`) reads as a path, so its PR is judged against this repo and can refuse.
- A lowercase path, label or branch with another prefix, followed by `:` or `PR`, reads as another repo, so its line is skipped (`hooks/guard_merge: PR #5`, `ci/cd: PR #5`).
- With no origin, a commit URL of this repo and an `owner/repo#N` are not judged. A payload with no `cwd` is judged in the hook's own directory, with no notice.
- A repo with a capital letter, marked only by `:` or `PR` (`Acme/Widgets: PR #5`), is judged against this repo and can refuse.
- A PR list split across a line break is judged on its first line only.
- A `#N` that follows a PR or pull word but means something else is judged as a PR (`PR merged, see #3`). Only a PR that does not exist refuses.
- A PR number whose gap breaks those limits passes: `PR for step 2 is #N`, `PR for this bug is #N`, a gap of 7 or more words, or a gap over 200 characters. The limits keep issue numbers from refusing.
- A `PR` word joined to the word before it by `-`, `/` or `.` is no PR word, so `mini-PR #8` passes.
- A `#` with exactly 6 or 8 digits, after a PR word and other words, is a colour, not a PR (`the PR sets the border to #000000`). A PR number that long is not judged in that form.
- The sha forms that `agent-report-shas-resolve` skips are skipped here too: `key=<sha>`, a URL from its scheme on (this repo's compare URLs included) and a line starting `index <hex>..<hex>`.
- A made-up sha glued straight onto a scheme passes, such as `8c1f0e2a7https://…`. The URL word starts only at a letter that begins a word, and a hex run followed by a letter is no token.
- Another repo's PR or sha named with no `owner/repo` on its line is judged against this repo and can refuse. In a full clone, a foreign sha is missing and is refused. In a shallow clone it is allowed and named unchecked.
- A scheduled send, `send_later`, is not judged, and is not built. `MESSAGE_REF_TOOL` names only `send_message`, and the field that holds its text is unverified here. An agent's `send_later` is still refused first, by rule `agent-no-remote-tools`, which bars an agent's remote tools.
