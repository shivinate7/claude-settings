# Status tab: stalled band, design notes

Mockup: `stalled-band.html`. Drawn from `skills/waiting-page/page.html` at 7975f6d8b, with its own
CSS copied in whole. Sizes: phone 390 and desktop 1280, the brief's sizes; this repo's device list
reads unknown. Themes: light and dark, by `data-theme` with `prefers-color-scheme` as the default.
Sample data follows the plan's `info["stalled"]` shape: `why`, `steps`, `paused`, `badPause`, `items`.

Deep links: `#s=unknown|stalled|items-unk|paused|zero`, `&o=once|row`, `&w=all|390|1280`,
`&t=light|dark`, `&lab=off`, `&hide=once,row`.

## States

| State | When | What shows |
|---|---|---|
| `unknown` | `steps` is None (`why` "unknown (steps unknown)") | The `livenone` line: "Stalled steps", dashed amber ring, "not read: <plain reason>". The build's words sit behind "What the build said". |
| `stalled` | `steps` or `items` not empty | "Stalled: N" head with a red edge. "Steps" list, then "Waiting items" list, then the "Paused: N" fold, closed. |
| `items-unk` | steps read, `items` None | The step list, then "Waiting items" with one amber "not read" line. Never "none". This is the state until `lane` reaches the parsed rows. |
| `paused` | nothing stalled, `paused` not empty | "No stalled step", then "Paused: N", drawn open. |
| `zero` | nothing stalled or paused | One quiet line: green check, "No stalled step". |

## Tokens

All are page.html's own; no new token.

- Box, head, h4 and row grid: `.live` values (`--line`, `--surface`, radius 12px, 130px id column,
  container query at 559px). On a phone the id column is 40px, as `.rrow` uses.
- Stalled: `--holds`, as a 4px left edge on the band, a 3px edge on the step row (the `.blocked`
  row's edge), the tag, and a new mark (a broken ring with a dot).
- Paused: `--muted`, with a new mark (a ring with two bars).
- Unknown and a bad pause: `--due`, the `.unk` colour, as Live work's "Skipped, wrong shape" line.
- Landed fix line: `--good`, as `.tag.landed`.
- Times: `fmt()` (~:1052), US Central, 24 h, with the zone: "Nov 5, 16:20 CST".

## Items

1. **Placement.** The band sits under the read-at line, above Live work (`build()` ~:3252).
   Gain: the read-at line dates it, so it needs no stamp of its own. Loss: one line sits above it.
   Pick: under the read-at line. The plan says "mounted first"; this departs by one line.
2. **Stalled colour: `--holds`.** Gain: amber keeps one meaning on this tab (unknown). The build
   exits 1 on a stalled step, as on a red line. Loss: red now means blocked and stalled; the mark
   shape tells them apart (filled square, broken ring). Other way: `--due`, which reads as unknown. Pick: `--holds`.
3. **Words once** (option, `o=once`). The band lead says "Triage resumes, pauses or closes each"
   once. A row shows a fix line only when it differs: "done: landed in #N", or "Pause not counted".
   The row tags are marks with `aria-label` and `title`, the `rgl` pattern.
   Gain: passes ux-label-once (the owner's "too much verbiage" ruling). Loss: a row read alone does not say what to do.
   Pick: Words once. **Departs from:** the brief's "Resume, pause or done" on each row and the word tag on `stepRow`.
4. **Words on each row** (option, `o=row`). The brief as written: "Resume, pause or done" per step,
   "Re-route, close or resume" per item, "Stalled" and "Paused" word tags. Gain: each row stands
   alone. Loss: "Stalled" and "Paused" show twice on the tab, and the fix line repeats per row.
5. **What N counts.** "Stalled: N" counts steps plus items (4 = 3 steps + 1 item). Gain: one
   number for "needs a disposition". Loss: N differs from the build's stalled-step lines. Other way: steps only, with "Items: N" apart.
6. **Bad pause.** A `badPause` step stays in the list with an amber line "Pause not counted:
   <why>". Gain: triage sees why its pause did not hold. Loss: one more line. The plan does not ask for it on pages.
7. **Paused rows.** Why, then "<Who> decides; paused <time>" as one sentence, so no field label
   repeats per row. "Who" shows Owner, Coordinator or Triage.
8. **Each step leads on.** A step title is a `button.tx data-go`, as "Doing now" (`renderNow`),
   so a press opens the step row. An item number is plain text: the Waiting tab has no anchor per item.
9. **Doing now marks** (`renderNow` ~:3008). A stalled or paused step shows its mark in place of the
   in-progress mark, so the list no longer says it is in progress. **Owner grant: yes.** It ties to the plan's open question 3.
10. **Step row** (`stepRow` ~:3068). A stalled row gets the red edge and the Stalled tag after
    Landed. A paused row gets the Paused tag and keeps its status edge.

## Checks run

- `label_once.py` on each drawn screen: clean. It counted "Decides", "Why" and "Since" twice in
  paused rows, so item 7 replaced the field labels.
- `impeccable detect`: no finding. The critique ran in one context (no sub-agent tool): it
  dropped the band's own read stamp, a third "read" stamp beside the read-at line and Live work.
