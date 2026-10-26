# c54 part 2: each Done item names the model of each subagent that worked on it

Cloud build thread brief. Build advisor (2), Oct 26, against claude-settings main e5525a6.
Base: main e5525a6; never rebase onto main after review. It lands in the batch after c53
(merge tool on REST, PR #591). Push roadmap edits to the branch only; only
"Triage the roadmap (2)" republishes the roadmap page.

## Why

Owner's question, Oct 26: cloud threads run Opus, and he cannot see which models their subagents
got. Part 1 (done by the owner): a cloud environment sets CLAUDE_CODE_SUBAGENT_MODEL and
CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL to sonnet; older threads lack it. Rules in force:
roles-sonnet-is-the-ceiling, subagent-model-cap (the model-per-role table), reports-done-format.

## Task

1. Rule: a Done item that subagents built or reviewed names each one's role and model, e.g.
   "BUILT: ... #123 (builder sonnet, reviewer sonnet)". One short STE sentence added to the
   Reports paragraph of CLAUDE.md, with its anchor and rule_mechanisms.json row.
2. Reviewer: agents/reviewer.md checks the named models against the spawn calls it can see (the
   Agent or workflow call's model, or the agent file's pin) and flags a model above the role's
   row in subagent-model-cap that no owner word covers.
3. Mechanize where cheap: if a hook or lint can read the report's Done lines and the session's
   spawn calls, add it; otherwise mark the rule judgment and say what a machine would need.
4. Record what is unknown: how the env cap interacts with an agent file's own pin (Plan on Opus).
   If you can measure it in this cloud session, do and record it; else leave it as unknown.

## Failure classes and proof

- If you add a check: red first on a Done line that omits a model or names Opus for a builder
  with no owner word; a Done line for work with no subagent must pass (false alarm).
- rule_audit's pinned counts move only by the new anchor; say which bucket.
- A fresh Sonnet reviewer reads the diff. Name its model in your own Done line.

## Report

Cap 15 lines: Done, Deviations, Next. Send the green, reviewed head and branch to
"Advise the claude-settings build (2)". No question for shiv: park any in the PR body.
