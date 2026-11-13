# An agent pushes only to the branch its brief names

## The ruling

Rule `push-target-named` in `hooks/guard.py` refuses an agent's `git push` unless the agent's own brief names the branch it sends to. Its home is `judge_shell` step 4, in the `_push_calls` loop, after the force verdict (`push_target_kind` in `hooks/guard_push_delete.py`). Lane: `brief-names-push-target`, 2026-11-12 CST.

- The mistake: in lane `writer-lists-awaiting-threads` a builder pushed to the lane branch before the review records were posted.
- The harm: the early push breaks the pull request review record (`pr-review-record`) and lands unreviewed work on origin.
- What is read: the payload's valid `agent_id` (`scratchpad_agent`, the one `AGENT_ID` pattern), then the first user record of that agent's own transcript (`own_session.agent_brief_text`, through `agent_transcript_path`). A record held as a list of blocks reads as its text blocks, one per line.
  - A line counts when it starts, after markdown lead characters `#*_>` and spaces, with `Push to:`. A line inside a fence, or in backticks (a backtick cannot lead the line), does not count.
  - The value is the first word after `Push to:`, with backticks, asterisks, underscores, full stops, commas, semicolons and parentheses stripped from both ends (`brief_push_target`). A word that strips to empty is read past, so `**Push to:** lane-x` names `lane-x`. The words after the value are a note: `Push to: none (report only)` is none. `refs/heads/` and `origin/` are dropped from the value.
  - A line with no value, or whose value starts with `<` (a placeholder such as `<branch>`), is skipped, indented or not. The first line with a real value decides.
- Verdicts, each a refusal:
  - `none`: every push.
  - a named branch: a push whose destinations (`push_destinations`) are not all that branch, a glob, or a destination that cannot be resolved (a detached HEAD).
  - a push that sends tags (`--tags`, with or without a refspec) under a named branch: refused with the same reason. Every tag reaches the remote, which no branch covers.
  - a push to main under a brief that names another branch: refused, not asked. An agent has no one to answer an ask. Owner, 2026-11-13 00:50 CST, Cockpit item 672 pick a, relayed by triage at 00:51 CST: refuse it. The same pick, item 673 a, adds the `Push to:` line to rule `roles-brief-contents`; triage sends that edit to the owner's Windows session.
  - no usable line, or a brief that cannot be read (no transcript path, a missing file, a folder, an empty file): refused, with the remedy "stop and report that the brief names no push target". An ask inside an agent has no one to answer it, so no line is a deny, not an ask.
- The remedy never names the destination branch (`git-remedy-never-names-target`).
- Passes: a dry run (`read_verb`), a call with no valid `agent_id` (the top-level session), and a forced push, which keeps its own refusal (`force-push`). The override lifts it (`owner-override`).
- Accepted limits (Claude is unlikely to write these forms by mistake, `guard-guards-mistakes-only`):
  - a dash lead (`- Push to:`) is not a line, so the push is refused with the remedy;
  - a malformed `agent_id` is a top-level call and is not judged;
  - an `agent_type` with no `agent_id` is not judged;
  - an async or Workflow agent whose transcript sits elsewhere reads as no line: the push is refused, and the remedy says to report;
  - a forced push to main still asks first: the force-push rule runs before this step, and an ask inside an agent has no one to answer it.
- Cost: one file read per agent push, stopped at the first user record, never raising, no file written, no process start. A call with no agent push reads nothing.

The `push-target-named:` cases in `hooks/test_guard.py` (family `push-target-named`) protect it. They were red before the rule landed. `hooks/test_agent_brief.py` pins the standing push line each agent gets, and `lint/test_agent_push_form.py` pins `Push to:` in each writer role file.

Kind: process
Home: hooks/guard.py
