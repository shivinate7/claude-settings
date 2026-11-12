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

- **PreToolUse, `SubagentHandback`.** Where the harness delivers an agent's report by this call, the report is its `message` (code.claude.com/docs/en/hooks.md, SubagentStop). Elsewhere the stop fallback below judges it. A missing sha refuses the call with `report-sha-missing` before the report is delivered. The agent fixes its report and hands back again.
- **SubagentStop** (`judge_stop`), the fallback, reads `last_assistant_message`. A missing sha blocks the first stop. A second stop (`stop_hook_active`) is allowed and logs `report-sha-unresolved`, so an agent never loops. A builder stop that breaks `builder-diff` too gets one block with both reasons.

The payload must carry a valid `agent_id`. Every agent type is judged, reviewers and Explore included, since any role can cite a commit. The main session is not judged.

## What counts as a sha

- A token of 7 to 12, or exactly 40, lowercase hex characters, with at least one digit and one letter a-f. That rules out agent ids (17), digests (32, 64) and other long hex.
- A token that touches `-`, `_`, `/`, `#`, `.`, `@` or `=` is not one. That rules out UUIDs, colours, URLs, file names, `key=value` and `owner/repo@sha`.
- Two exceptions are judged. The first is a sha side of a range: `a..b`, `a...b`, or `main..a` and `a..HEAD` with a ref on one side.
- The second is a token followed by a sentence mark: `.`, `,`, `;`, `:`, `)`, `]`, `*`, `"` or a backtick. It is judged up to a space or the end of the text, so "Fixed in 8c1f0e2a7." and "(fixed in 8c1f0e2a7.)" are judged.
- A URL is skipped from its scheme on, so the shas of a compare link's URL are not judged. Text before the URL is judged, unless it is glued to the scheme (see Known gaps). A line that starts `index <hex>..<hex>` (a pasted diff header, which names blob ids) is skipped whole. Any other line that starts with the word index is judged.
- A token inside a double-quoted span or on a `> ` quoted line is skipped, since quoted text may come from another repo (coordinator brief, 2026-11-08: a sha in quoted text of another repo is a false alarm). A quoted span counts only when its closing quote is on the same line, so an unclosed quote hides nothing. A span before a `>` mark does not make a line a `> ` line, so `"x" > landed as <sha>` is judged. A backticked sha is checked.
- A sha resolves when `git cat-file --batch-check` finds it as `<sha>^{commit}` in the repo of the payload's `cwd`. A short sha that git reports as ambiguous passes.

## Fail open

- No git repo at `cwd`, or git fails: allowed.
- A shallow clone allows every missing sha, and logs `report-sha-shallow`, since an old main sha may sit beyond the clone's depth.
- Cloud sessions' clones are shallow. Their depth is set outside this repo and is not verified here.

## Cost

A hand-back is judged before any other guard rule reads git, so a hand-back with no sha-like token starts no git process. One that holds one starts one `git cat-file --batch-check`, and one `rev-parse --is-shallow-repository` when a sha is missing. A stop adds the same to the stop's existing diff reads. A guard.log line only for a refusal or a note. No file, timer or long-lived process.

## Known gaps

- A sha that exists but that the agent did not make (an old commit) passes. This check proves the commit exists, not that the agent did the work.
- A sha written in uppercase is not read.
- A sha in quotes or JSON, `key=<sha>`, and a 13-39 hex token pass (note report-sha-quoted-forms-pass).
- A made-up sha glued straight onto a scheme passes, such as `8c1f0e2a7https://…`. The URL word starts only at a letter that begins a word, and a hex run followed by a letter is no token. A made-up sha on an `index <hex>..<hex>` line passes too (note report-sha-index-line-pass).
- A shallow clone (a clone that holds only recent history) allows every missing sha, so a made-up sha passes there. See Fail open. Note: report-sha-shallow-allowed.
- An agent's report that names another repo's commit by sha in link text (`[0123abc](https://github.com/acme/widgets/commit/0123abc)`) is refused when this repo lacks the sha, outside a shallow clone. Link text is the words inside `[...]`. This path has no other-repo rule, so it judges that text like plain text. The message path skips it (decision `send-message-refs-resolve`).
