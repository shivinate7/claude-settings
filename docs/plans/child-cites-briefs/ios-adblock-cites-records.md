# Brief for ios-adblock: name claude-settings records, never copy them

Ruling: claude-settings decision `child-cites-not-copies` (a child repo names a claude-settings record and never copies it), owner, 2026-11-02 10:41 CST.

Read at ios-adblock 519ccf8. Line numbers are for that commit. Re-read each line before you change it.

## Lines to replace in `CLAUDE.md`

1. Lines 4 and 5, under "Merges": the item that starts "Merge authority comes from the owner's grant in chat" and the item that starts "Standing merge grant (owner, 2026-10-29 16:47 CDT". Replace both with one item:
   `- Merge grant: claude-settings standing-merge-grant.`
2. Keep lines 6 to 8. They hold this repo's own checks and the pin-bump auto-merge.

## CI step to add

This repo runs no STE lint job. In the workflow that runs `all-jobs-passed`, add one job, and list it in `all-jobs-passed`'s needs:

    claude-md-cites:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@<the pin this repo uses>
        - uses: shivinate7/claude-settings/actions/claude-md-cites@<sha>

`<sha>` is the claude-settings main commit that holds `actions/claude-md-cites`. Put the line fix and the job in one PR.

## Done check

The new job is green on the PR. Before the line fix, `python3 <claude-settings>/lint/compliance_probes.py restates .` refuses line 5.
