# The compliance-check skill has two findings that wait

**What.** Two fixes for `skills/compliance-check` wait for the owner. Probes use `python3`, and macOS has no `python`. The cite probe leaves the bare-slug form open.

**Where.** `skills/compliance-check/probes.md`: lines 10 to 13 use `python3`; line 45 matches D plus digits, keyword cites and bare slugs. A reviewer says the bare-slug grep leaves the form open, so the owner decides.

**Decision.** none. See the Ruling below.

**Retire.** When the skill next changes, land both findings in its file: settle `python` against `python3`, and cover the slug form (D plus a backtick slug) in the cite probe. Closed when the probes file shows both.

## Ruling

Owner, 2026-10-12/13: these findings wait. The other findings of the three skills have landed.
