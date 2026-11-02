# Child-repo briefs: name claude-settings records, never copy them

For the owner to send to each repo's coordinator. From lane child-rules-cite-records, branch child-rules-cite-records at 58a51bfa (docs/plans/child-cites-briefs/). Send after decision child-cites-not-copies and actions/claude-md-cites are on claude-settings main; fill <sha> with that main commit.

## Brief for home: name claude-settings records, never copy them

Ruling: claude-settings decision `child-cites-not-copies` (a child repo names a claude-settings record and never copies it), owner, 2026-11-02 10:41 CST.

Read at home 428d8fe. Line numbers are for that commit. Re-read each line before you change it.

### Lines to replace in `CLAUDE.md`

1. Line 28, the item that starts "Merge grant (owner, 2026-10-11". Replace it with:
   `- Merge grant: claude-settings standing-merge-grant. In this repo, a records-only PR (files under records/ only) needs only green checks (owner, 2026-10-12).`
2. Line 29, the item that starts "Standing merge grant (owner, 2026-10-29 16:47 CDT". Delete it. Item 1 names the record.
3. Line 27, the item "Standing roles". Keep it. It names the roles for this repo. Check that it says nothing about who merges beyond "The merge grant below covers the batch runner".

Keep lines 30 to 33 (CI, Merge tool, Cleanup, Batching). They hold this repo's own steps.

### CI step to add

In `.github/workflows/test.yml`, in the job that runs "STE lint", add one step:

    - name: CLAUDE.md cites records
      uses: shivinate7/claude-settings/actions/claude-md-cites@<sha>

`<sha>` is the claude-settings main commit that holds `actions/claude-md-cites`. Put the line fix and the step in one PR.

### Done check

The new step is green on the PR. Before the line fix, `python3 <claude-settings>/lint/compliance_probes.py restates .` refuses line 29.

## Brief for degen: name claude-settings records, never copy them

Ruling: claude-settings decision `child-cites-not-copies` (a child repo names a claude-settings record and never copies it), owner, 2026-11-02 10:41 CST.

Read at degen a2ae7ba. Line numbers are for that commit. Re-read each line before you change it.

### Lines to replace in `CLAUDE.md`

1. Line 7, the item with the anchor `rule:merge-grant`, which starts "The batch runner, and the coordinator under the owner's standing merge grant". Replace the text before the anchor with:
   `Merge grant: claude-settings standing-merge-grant. In this repo, merge with the claude-settings merge tool, because it claims record numbers before the merge.`
   Keep the anchor and the "Check:" text after it.
2. Line 8, the item with the anchor `rule:lanes-hand-off-to-batch-runner`. Keep it. It names this repo's hand-off steps.

### CI step to add

In `.github/workflows/check.yml`, in the job that runs "STE lint", add one step:

    - name: CLAUDE.md cites records
      uses: shivinate7/claude-settings/actions/claude-md-cites@<sha>

`<sha>` is the claude-settings main commit that holds `actions/claude-md-cites`. Move the other claude-settings pins in that file to the same commit (decision `action-pins-follow-sessions`). Put the line fix and the step in one PR.

### Done check

The new step is green on the PR. Line 7 is a paraphrase plus a citation, so the check does not refuse it. This brief is its only fix.

## Brief for ios-adblock: name claude-settings records, never copy them

Ruling: claude-settings decision `child-cites-not-copies` (a child repo names a claude-settings record and never copies it), owner, 2026-11-02 10:41 CST.

Read at ios-adblock 519ccf8. Line numbers are for that commit. Re-read each line before you change it.

### Lines to replace in `CLAUDE.md`

1. Lines 4 and 5, under "Merges": the item that starts "Merge authority comes from the owner's grant in chat" and the item that starts "Standing merge grant (owner, 2026-10-29 16:47 CDT". Replace both with one item:
   `- Merge grant: claude-settings standing-merge-grant.`
2. Keep lines 6 to 8. They hold this repo's own checks and the pin-bump auto-merge.

### CI step to add

This repo runs no STE lint job. In the workflow that runs `all-jobs-passed`, add one job, and list it in `all-jobs-passed`'s needs:

    claude-md-cites:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@<the pin this repo uses>
        - uses: shivinate7/claude-settings/actions/claude-md-cites@<sha>

`<sha>` is the claude-settings main commit that holds `actions/claude-md-cites`. Put the line fix and the job in one PR.

### Done check

The new job is green on the PR. Before the line fix, `python3 <claude-settings>/lint/compliance_probes.py restates .` refuses line 5.
