# Brief for degen: name claude-settings records, never copy them

Ruling: claude-settings decision `child-cites-not-copies` (a child repo names a claude-settings record and never copies it), owner, 2026-11-02 10:41 CST.

Read at degen a2ae7ba. Line numbers are for that commit. Re-read each line before you change it.

## Lines to replace in `CLAUDE.md`

1. Line 7, the item with the anchor `rule:merge-grant`, which starts "The batch runner, and the coordinator under the owner's standing merge grant". Replace the text before the anchor with:
   `Merge grant: claude-settings standing-merge-grant. In this repo, merge with the claude-settings merge tool, because it claims record numbers before the merge.`
   Keep the anchor and the "Check:" text after it.
2. Line 8, the item with the anchor `rule:lanes-hand-off-to-batch-runner`. Keep it. It names this repo's hand-off steps.

## CI step to add

In degen's `check.yml` workflow, in the job that runs "STE lint", add one step:

    - name: CLAUDE.md cites records
      uses: shivinate7/claude-settings/actions/claude-md-cites@<sha>

`<sha>` is the claude-settings main commit that holds `actions/claude-md-cites`. Move the other claude-settings pins in that file to the same commit (decision `action-pins-follow-sessions`). Put the line fix and the step in one PR.

## Done check

The new step is green on the PR. Line 7 is a paraphrase plus a citation, so the check does not refuse it. This brief is its only fix.
