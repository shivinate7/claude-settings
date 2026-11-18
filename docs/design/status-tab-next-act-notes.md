# Status tab next act: design notes

Mockup: `status-tab-next-act.html`. Screen: the waiting page's Status tab, the Live work box, its
"Open pull requests" list. Step status-tab-lists-coord-prs (each open pull request shows its next
act). The act, owner, age and red come from one ledger row per pull request, built by
`pr_next_act` (merge/merge.py) and joined by number.

This is a port. Today's list (skills/waiting-page/page.html `liveWork`, the "Open pull requests"
`<ul>`) and today's CSS (`.live h4`, `.live li`, `.live li .nm`, `.tag`, `.unk`, `.rg.unk`) are the
default, copied verbatim at e88dac4d5. Sizes 1440, 820 and 390 are the brief's; this repo's device
list reads unknown. All figures are samples, on a fixed clock (07:30 CST), so screenshots stay the
same.

Deep links: `#s=live|lanes|stale`, `&red=mark|word`, `&why=row|head`, `&w=1440|820|390`,
`&t=light|dark`, `&lab=off`, `&hide=<option>`.

## Items

1. **Act line.** A third line under today's title and branch line: the act in ink, then
   "owner <owner>", then "waited <age>". The age uses the page's own `span()` (page.html), so
   it reads "waited 5 hours" or "waited 2 days", as the asks read.
   Gain: today's two lines and the 130 px number column stay as they are. The act is the one
   word in ink, so the eye finds it.
   Loss: each row grows by one line (about 20 px).
   Pick: as drawn.

2. **List head.** The h4 becomes a flex row: "Open pull requests", then the counts, then
   "acts read <time>", pushed to the end as the summary's `read <time>` is.
   Counts: "<n> red" in `--holds` first, then each owner with its count, most first, and
   "unknown <n>" last for pulls with no ledger row.
   Gain: the time of the act read sits beside the list it dates (ux-control-beside-area).
   Loss: at 390 the time wraps to its own line, right-aligned.
   Pick: as drawn.

3. **Red row.** Red rows sort first. The other rows keep REST order. Two options, each with a hide
   control. Focus id: `pick-red`, the first red row.
   - *Edge and mark.* The red edge that the stalled band uses (`inset 3px 0 0 var(--holds)`), and
     a red mark in a `.tag.ic`, the shape the stalled mark uses. Its aria-label and title give the
     reason, such as "Red: waited past its 24-hour limit".
     Gain: the word "red" shows once, in the head count, and each row shows red by shape and
     colour (ux-label-once).
     Loss: one new glyph to learn.
   - *Word tag.* A "red" word tag in `--holds`, with no edge.
     Gain: plain to read.
     Loss: "red" shows on every red row (ux-label-once). A row without an edge is easier to miss
     at a glance.
   Pick: Edge and mark.

4. **A pull with no ledger row.** The act line reads "act unknown: no ledger row for this pull
   request", with the page's dashed unknown ring in `--due`. It shows no owner and no age. It is
   never blank or "none". The head counts it as "unknown 1".
   Pick: as drawn.

5. **Draft with no live lane** (plan item e). The act line reads "no live lane, owner
   coordinator, waited 20 hours" (the build replaces the ledger's "lane round 1"). The row is not red. It counts under coordinator.
   Pick: as drawn.

6. **Lanes not read** (`#s=lanes`). No lane hold can be told when the sessions list is missing, the
   repo's GitHub name is unread, a session row was skipped, or the draft has no branch, so no draft
   can read "no live lane". The act line reads "(ring) lane unknown, owner unknown, waited 20 hours".
   The reason shows in the span's title and once in a line under the head ("Lane holds unknown: ..."). A cause that
   lies in the whole list makes every round-1 draft read "lane unknown"; a draft with no branch
   reads it alone.
   Owner: the owner reads "unknown", because the coordinator owns the row only once the build knows
   that no lane holds it, and the ledger's "lane" is the owner of an act the build has replaced.
   Pick: owner unknown, as the tests pin it.

7. **Acts too old** (`#s=stale`). The ledger's readAt is older than STALE_LIVE_MINUTES (60), or
   missing. Every act reads "act unknown", with no owner, no age and no red. The rows keep REST
   order. The head counts read "owners unknown", never zero. The acts-read time shows the old time
   with the unknown ring. Two options, each with a hide control. Focus id: `pick-why`.
   - *Reason on each row* (the brief's words): "act unknown: read 2 hours ago, past the
     60-minute limit" on every row.
   - *Reason once at the head:* one line under the head says "Every act is unknown: the acts were
     read 2 hours ago, past the 60-minute limit.". Each row reads "act unknown" alone.
   Gain of once: the same reason does not show nine times (ux-label-once). Loss: a row read alone
   does not say why.
   Pick: Reason once at the head. Departs from: the brief's and the plan's test case "every act
   reads unknown with that reason". Owner grant: yes (it changes the spec). Not blocking. The
   mockup's default view draws "Reason on each row", per the spec, until the owner rules.

8. **Owner word "owner".** The pull request that waits on a page item reads "owner owner", because
   `pr_next_act` names the owner "owner". The mockup draws the real string. A label such as "owner
   Shivam" would be a departure from the one home of the act's wording.
   Pick: as drawn.

9. **Both renderers.** The roadmap page (skills/roadmap/page/index.html, `.live li`) shows the
   same row text in its own CSS (120 px column, 13 px). Not drawn here (plan item f).

## Departures from today's look

- The "Open pull requests" h4 changes from a block to a flex row, so that the counts and the
  acts-read time can sit on it. Each other line of today's row is the same.
- The only new marks are the red edge, which the stalled band already uses, and the red mark
  glyph (item 3).

## Critique (impeccable, on this mockup)

- The stale state with the reason on every row repeats one sentence nine times. Answered by item 7.
- `.asof.unk` lines read in muted grey, not in `--due`, because `.asof` comes after `.unk` in the
  page's CSS. Fixed for the new lines only (`.live .prwhy`, the head's old acts-read time). Today's
  "Skipped, wrong shape" line keeps the same fault; it is out of this step.
- The detector (`impeccable detect`) found nothing, on the mockup file or on the rendered live and
  stale screens. The run was single-context: no agent tool was exposed.
- `label_once.py` on the rendered screens: "working" twice (today's thread tags, data) and, in the
  stale state, "act unknown" nine times. Each row must read unknown, never blank (plan test case),
  so the per-row words stay; the reason sentence shows once with item 7's pick.
- The h4 holds the counts, so a screen reader reads a long heading. Kept: the brief puts the counts
  in the h4.
- The red mark's pill border around a filled circle is heavy at 12 px. It matches the stalled mark's
  shape (`.tag.ic`); kept for one family.
