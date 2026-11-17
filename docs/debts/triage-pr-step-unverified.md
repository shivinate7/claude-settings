# A step note can cite a PR whose title names another step

**What.** Triage attached a coordinator note about PR #1634 to step review-record-provenance, the only step that named #1634. PR #1634 is titled "merge: page list reads by number, not by gh's Link header" (branch merge-page-by-number). Triage did not read the PR title first. No check warns when a note's PR cite fits another step's title better.

**Where.** `skills/roadmap/build.py`. Its citation check reads mockup ids in a step's note, why and ask (`mockup_cites`). Nothing reads a PR number in a note against that PR's title.

**Decision.** none

**Retire.** `skills/roadmap/test_build.py` holds a case where a step note cites a PR whose title matches another step's title better, and the build warns on it.
