# Brief for home: name claude-settings records, never copy them

Ruling: claude-settings decision `child-cites-not-copies` (a child repo names a claude-settings record and never copies it), owner, 2026-11-02 10:41 CST.

Read at home 428d8fe. Line numbers are for that commit. Re-read each line before you change it.

## Lines to replace in `CLAUDE.md`

1. Line 28, the item that starts "Merge grant (owner, 2026-10-11". Replace it with:
   `- Merge grant: claude-settings standing-merge-grant. In this repo, a records-only PR (files under records/ only) needs only green checks (owner, 2026-10-12).`
2. Line 29, the item that starts "Standing merge grant (owner, 2026-10-29 16:47 CDT". Delete it. Item 1 names the record.
3. Line 27, the item "Standing roles". Keep it. It names the roles for this repo. Check that it says nothing about who merges beyond "The merge grant below covers the batch runner".

Keep lines 30 to 33 (CI, Merge tool, Cleanup, Batching). They hold this repo's own steps.

## CI step to add

In `.github/workflows/checks.yml`, in the `checks` job that runs "STE lint", add one step:

    - name: CLAUDE.md cites records
      uses: shivinate7/claude-settings/actions/claude-md-cites@<sha>

`<sha>` is the claude-settings main commit that holds `actions/claude-md-cites`. Put the line fix and the step in one PR.

## Done check

The new step is green on the PR. Before the line fix, `python3 <claude-settings>/lint/compliance_probes.py restates .` refuses line 29.
