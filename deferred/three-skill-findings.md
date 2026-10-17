# The compliance-check skill has two findings that wait

**What waits.** Two fixes for `skills/compliance-check`. Each line names what is wrong and where
the skill shows it. "Now" gives the current text.

- Probes use `python`, not `python3`. Now: `probes.md` lines 10 to 13 use `python3`. macOS has
  no `python`, so the owner decides.
- Cite probe: cover the slug form, D plus a backtick slug. Now: `probes.md` line 45 matches D
  plus digits, keyword cites and bare slugs. A reviewer says the bare-slug grep leaves the
  form open, so the owner decides.

**Why it waits.** The owner ruled that these findings wait, on 2026-10-12/13. The other findings
of the three skills have landed.

**What keeps it from being lost.** This file.

**Trigger.** When the skill next changes, land its findings in its file. Then delete them here.
