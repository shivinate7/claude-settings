## Summary

<!-- What changed and why, in two or three lines. Name the step or debt it closes. -->

## Test plan

<!-- The checks you ran, each with its verdict. -->

## Risk

<!-- The kind of change, the review rounds it owes, and what breaks if this change is wrong. Two or three lines. -->

## How to revert

<!-- The revert path: the commit or PR to revert, and any step to undo after it. Write "revert the merge commit" when that is all. -->

<!--
Delete each line you do not use. Each line is for one named case:
- Retire-run: this PR closes a debt whose Retire names no runnable check, or one that cannot run here.
  The slug is the debt file's name without .md. The run URL is a green run on this PR's head or a later commit.
- Drops-lines: this PR removes lines from a path on purpose. The reason says why.
Keep the lines together as the last paragraph. Put nothing after them but the Claude Code attribution line.
A line with a real path and any reason excuses that path, so fill both parts or delete the line.
The untouched placeholders, `<path> -- <reason>` and `<slug> -- <run URL>`, name nothing real.
Comments and code blocks are not read.
The Retire-run line follows decision `debt-close-runs-retire`. The Drops-lines line follows decision `silent-undo-check-design`.
-->

Retire-run: <slug> -- <run URL>
Drops-lines: <path> -- <reason>
