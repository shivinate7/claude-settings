# An agent pushes only where its brief says

## The ruling

Rule `push-target-named` in `hooks/guard.py` refuses an agent's `git push` unless the agent's own brief names the branch it sends to. Its home is `judge_shell` step 4, in the `_push_calls` loop, after the force verdict (`push_target_reason` in `hooks/guard_push_delete.py`). Lane: `brief-names-push-target`, 2026-11-12 CST.

- The mistake: in lane `writer-lists-awaiting-threads` a builder pushed to the lane branch before the review records were posted.
- The harm: the early push breaks the pull request review record (`pr-review-record`) and lands unreviewed work on origin.
- What is read: the payload's valid `agent_id` (`scratchpad_agent`, the one `AGENT_ID` pattern), then the first user record of that agent's own transcript (`own_session.agent_brief_text`, through `agent_transcript_path`). The first line that starts, after markdown lead characters `#*_>` and spaces, with `Push to:` decides. A line inside a fence, or in backticks (a backtick cannot lead the line), does not count. An empty value or a `<placeholder>` on that line is no target. An `origin/` prefix is cut off.
- Verdicts, each a refusal:
  - `none`: every push.
  - a named branch: a push whose destinations (`push_destinations`) are not all that branch, a glob, or a destination that cannot be resolved (a detached HEAD).
  - a push to main under a brief that names another branch: refused, not asked. An agent has no one to answer an ask. The owner's side of this ruling is pending (coordinator default).
  - no usable line, or a brief that cannot be read (no transcript path, a missing file, a folder, an empty file): refused, with the remedy "stop and report that the brief names no push target". An ask inside an agent has no one to answer it, so no line is a deny, not an ask.
- The remedy never names the destination branch (`git-remedy-never-names-target`).
- Passes: a dry run (`read_verb`), a call with no valid `agent_id` (the top-level session), and a forced push, which keeps its own refusal (`force-push`). The override lifts it (`owner-override`).
- Accepted limits: a bold or dash lead (`**Push to:**`, `- Push to:`) is not a line, so the push is refused with the remedy; a malformed `agent_id` is a top-level call and is not judged. Claude is unlikely to write a forged brief by mistake (`guard-guards-mistakes-only`).
- Cost: one file read per agent push, stopped at the first user record, never raising, no file written, no process start. A call with no agent push reads nothing.

Protected by the `push-target-named:` cases in `hooks/test_guard.py` (family `push-target-named`), red before the rule landed; `hooks/test_agent_brief.py` pins the standing push line each agent gets, and `lint/test_agent_push_form.py` pins `Push to:` in each writer role file.

Kind: process
Home: hooks/guard.py
