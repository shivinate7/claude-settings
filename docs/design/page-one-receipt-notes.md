# Waiting page rail, one ready count, step page-one-receipt: design notes

Mockup: `docs/design/page-one-receipt.html`. Screen: `skills/waiting-page/page.html` at 174b005c1, Answer tab rail (`renderRail`, the `.ov-prog` block) and
the bar (`renderBar`). Its CSS (lines 8–908) is copied whole. Only `#newcss` is new.
Deep links: `#s=today|after|todayzero|zero|chip`, `&w=all|390|800|1280`, `&t=light|dark`, `&lab=off`, `&hide=chip`.
Sizes: 390, 800 and 1280, which are page.html's bands (`layout.py devices` prints `unknown`). The rail is a side column at 961 and up, and a block above the list below it. Themes: light and dark.
Ruling: coordinator, 2026-11-07 13:56 CST. Drop the rail's "N ready to send" line. Keep the track, its ready segment and "X of Y sent".

## 1. Drop the ready line (ruled), states `after` and `zero`, focus `#railAfter` (zero: `#railZero`)

- The `.ov-prog .sub` line goes: its swatch `i.sw` and the words "N ready to send". The big line "X of Y sent" and the track stay as today.
- The bar keeps "N ready." and the Send button keeps "Send N answers" (`renderBar`). That is the one count on the screen, as `ux-label-once` asks.
- Gain: the word "ready" shows once. Today the `.sub.none` row keeps 22px of blank space, plus the 8px gap, when nothing is ready (`todayzero`).
  After, no row toggles, so the progress block is 34px high in every state, not 64px. Measured in all 30 frames.
- Loss: the ready count is no longer next to the track. On a phone the rail scrolls away and the bar stays fixed at the foot, so the bar was already the one place that is always on screen.
- Departs from: `renderRail` at 174b005c1, which shows the ready count in the rail and in the bar. After, it shows only in the bar. Ruled, not blocking.

## 2. The track's key: no new key (pick)

- Without the line, the swatch that keyed the ready segment's colour goes too. The track still reads, for three reasons:
  - The ready chips in the rail key the colour. `.nchip.ready` is the accent, and `.track .r` is the same accent at 55%.
  - "X of Y sent" sits right above the track, so the green part reads as sent. The rest is the ready part and the empty part.
  - The track is `aria-hidden` today. Each ready chip's label already says ", ready to send", and `#barStatus` says "N ready." in reading order. A screen reader loses nothing.
- No visible legend: a "ready" word by the track brings back the double that the ruling removes (`ux-label-once`).
- No `aria-label` on the track: a screen reader would hear the ready count twice.
- Gain: no new element, no new word. Loss: a reader who has never seen the page infers the light segment from the chips, not from a label.
  In light, the 55% tint reads grey beside the slate chip, so the chip keys it by hue family, not as an exact match.

## 3. Ready segment in the chip's colour (hide: "track in the chip's colour"), state `chip`, focus `#railChip`. Not the pick

- `.track .r` takes the full accent, as a ready chip does, so the chip is an exact key.
- Loss: the full accent sits too close to the green sent segment in lightness. Measured contrast between the two segments: 1.22 light and 1.17 dark.
  The 55% tint gives 2.12 light and 2.52 dark. The tint lets a reader with poor colour vision tell sent from ready. A repo's own accent (`--r-ink-l`) can come closer still.
- Gain: the chip and the segment match exactly. Owner grant: no. It changes no rule.

## 4. Today, states `today` and `todayzero`

- Today's rail, drawn for comparison: the line with its swatch, and its blank row when nothing is ready.

## 5. Text only: the receipt for an option no longer listed (no mockup)

- `receipt()`, the `else` branch for one choice, now ends "You chose an option." when the key is no longer in `options`. New: "You chose an option that is no longer listed."
- That branch adds the full stop itself (the `.line` builds `what + "."`), so the fallback words carry no stop, or the line ends "..".
- `lastAnswerEl` already says "You chose an option that is no longer listed." This makes the two receipts say the same.

## 6. For the builder (outside the design folder)

- Delete the dead CSS with the line: `.ov-prog .sub`, `.ov-prog .sub.none` and `.ov-prog .sw`. Leave the Status tab rail alone (its own `renderRail`).
- Tests: no test reads the rail's ready line. The chip's aria-label also says "ready to send" and stays. A test pins the receipt words for the one-choice fallback.
- Out of scope: in forced-colors mode the track's segments lose their backgrounds, today as after (`ux-forced-colors-hold`). The words carry both counts.

## 7. Measured verdicts

Headless Chrome, every state at 390, 800 and 1280, in light and dark. Checks: no sideways scroll, and no element past the page edge. All pass.
