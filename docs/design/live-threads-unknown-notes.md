# Waiting page Status tab: Live work with no threads list, design notes

Mockup: `live-threads-unknown.html`. Drawn from `skills/waiting-page/page.html` `liveWork()` at
77bcc0d87 (branch lane-live-build-threads-optional). The page CSS in the mockup is the page's own
rules for the Live work panel at that commit. Sizes: Wide 1440, Tablet 820 and Phone 390, the
brief's sizes. This repo's device list reads "unknown". Themes: light and dark. Designer kind:
informed (the brief names no kind).

Cases: the live file has no threads list (unknown), an empty threads list (a real zero, no marker),
and a threads list with one working and one failed thread (the state pills).

Deep links: `#s=all|unknown|zero|failed`, `&o=today|ring|muted|dashed`, `&b=on|off`,
`&p=fold|open`, `&w=all|1440|820|390`, `&t=light|dark`, `&lab=off`, `&hide=ring,muted,dashed,on`.
Focus id: `pick-marker`, in the No threads list case. Each option draws it in its own way.

Problem (design review F1): today the summary marker is `<span class="tag unk">`. `.tag` gives a
pill with a `currentColor` border, and `.unk` gives `--due`. `.tag.st-failed` and `.tag.st-stopped`
are the same pill in the same `--due`. So "threads unknown" reads as a thread state.

## Items

1. **Summary marker, option Ring and words.** Drop `.tag`. Use the panel's own unknown pattern: the
   dashed ring `.rg.unk` and the words in `.unk`, as the not-read line (`livenone`) and the
   stalled band's not-read row already draw it.
   Gain: one look for unknown on this page. A failed pill has a solid box; the marker has no box and
   a dashed ring. Shape tells them apart, not colour, so it holds in forced-colors mode (both edges
   turn CanvasText, one solid, one dashed). An unknown marker and a state pill never share one
   summary, since one needs no threads list and the other needs one.
   Loss: the marker keeps `--due`, the same hue as failed. Hue alone does not separate them. At
   12 px the dashed ring can look like a busy spinner; it does not turn, and the page already uses it
   for each not-read line.
   Pick: yes.

   Builder spec, `skills/waiting-page/page.html`:
   - In `liveWork()`, replace `'<span class="tag unk">threads unknown</span>'` with
     `'<span class="unk thr-unk"><span class="rg unk" aria-hidden="true"></span>threads unknown</span>'`.
   - Add one rule beside `.live summary .asof`:
     `.live summary .thr-unk { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }`.
     The `nowrap` keeps "threads unknown" on one line at 390, which `.tag` gave before.
   - Tokens: text `--due` (from `.unk`, weight 600, the summary's 14.5px). Ring: `.rg.unk`, 12 px,
     2 px dashed `--due`. No new token.
   - `.rg.unk` (two classes) beats the bare `.rg` rule (16 px grid) that comes later in the sheet, so
     the ring stays 12 px. The mockup's excerpt holds both rules in the page's order; seen at 390.
   - Contrast: `--due` on `--surface` is 6.33:1 light (#8a5300 on #ffffff) and 9.19:1 dark
     (#f2b55c on #191e26). The ring is a state cue at the same ratios, over the 3:1 floor.

2. **Summary marker, option Muted words.** Item 1's markup, with the words in `--muted` at regular
   weight (class `mu`). The ring stays `--due`.
   Gain: the words no longer share the failed pill's hue.
   Loss: unknown is `--due` and bold everywhere else on this page (`.unk`). Two looks for one
   meaning, and the summary's one warning reads like plain detail.
   Pick: no.

3. **Summary marker, option Dashed pill.** Keep `.tag.unk`, with `border-style: dashed`.
   Gain: one rule; the marker keeps the pill's size.
   Loss: `.tag.next` already means "Next" with a dashed pill. One shape, two meanings
   (ux-one-plain-name). Still a pill beside state pills.
   Pick: no.

4. **Threads row in the open panel: add the ring.** The body row reads
   "Thread count: unknown (...)" in `.unk` with no ring. Add
   `<span class="rg unk" aria-hidden="true"></span> ` before "Thread count", as the stalled band's
   not-read row does. Toggle: Body row.
   Gain: the folded and open views show unknown the same way.
   Loss: none seen. It is a separate change; the owner can cull it alone.
   Pick: yes.

5. **Empty threads list stays bare.** With `threads: []` the summary shows no thread pill and no
   marker, only the pull request count, as today. Zero is a real read, so it gets no unknown cue
   (ux-unknown-is-not-empty).
   Pick: yes, no change.

6. **Roadmap page tag: keep it.** In `skills/roadmap/page/index.html` the marker is
   `<span class="tag unk">`, but there `.tag` has no border, and `.live .unk` gives bare `--warn`
   text with no fill. `.tag.st-failed` has a `--warn-soft` fill. So fill against no fill already tells
   them apart, and the design review passed it. The brief says the roadmap tag has a `--warn-soft`
   fill; the CSS gives none (`.tag` sets no background, `.live .unk` sets colour only). Contrast: 5.1:1 light (#9a6200 on #ffffff),
   9.2:1 dark (#e9b44c on #191a1d). The roadmap page has no `.rg` ring class, so item 1's look
   there needs a new rule.
   Gain of no change: no work, no risk.
   Loss: the two pages draw "threads unknown" in two looks. A later lane may give the roadmap the
   ring for one look.
   Pick: keep.

Not changed: `.tag.st-failed` and `.tag.st-stopped` use `--due`, which is also this page's
unknown colour. A failed thread in `--holds` would separate them by hue too. That changes the page's
thread-state colours, so it is outside this lane.
