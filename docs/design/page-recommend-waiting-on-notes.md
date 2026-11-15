# Waiting page, lane page-recommend-and-waiting-on: design notes

Mockup: `docs/design/page-recommend-waiting-on.html`. Screen: `skills/waiting-page/page.html` at 066cc6d3 (branch pr3479),
`buildCard` and `optCard`. Its CSS (lines 8–954) is copied whole. Only `#newcss` is new. Designer kind: informed.
Deep links: `#s=both|bothtop|holds|widens|widenscut|multi|ranked|oneline|old|oldsay|today`, `&w=all|360|390|430`,
`&t=light|dark|both`, `&lab=off`, `&hide=bothtop,widenscut,oldsay`.
Sizes: 360, 390 and 430, from the brief (`layout.py devices` prints `unknown`). All three sit in page.html's phone band
(≤520). 800 and 1280 are not drawn: the two new lines use no rule that changes above 520. Themes: light and dark.
Content: items 836, 837, 844, 857 and 878 from the roadmap branch, reopened for drawing (no `status`, `closed`,
`lastAnswer` or CLOSED line) and with session ids taken out of `owner`. Each Waiting on line is written from the item's
own Meanwhile line or `holds`. Multi and ranked are made up from 837. The thread (last answer and reply) is not drawn:
this work does not change it.

## 1. The Recommended line, and where it sits (pick: above the options), states `both`, `holds`, focus `#stBoth`

- A gold panel (`--gold-soft`, `--gold-ink`: the tokens of today's `.pick`), at card level, right after the `ref` line
  and before the multi hint and the options. Sparkle, then "Recommended:", the option's letter chip, its label, then `why`.
- Gain: the owner reads the pick and its reason next to the choice, before any option card. Loss: the panel adds 160–205 px
  on a phone (measured), and on a long context it sits below the first screen at 360.
- The line is a `div` with no handler and no `label for`, so a tap on it picks nothing. A tap on the starred option card
  still picks it, as today (SKILL.md: "a tap on the starred option picks it"). The page still never preselects.
- Only a valid recommendation draws it: the page's own `pickKeys`. A value that does not fit the item draws nothing, as today's star.

## 2. Both lines under the title (hide: "under the title"), state `bothtop`, focus `#stBothTop`

- Waiting on, then Recommended, both before the context. Gain: both answers are on the first phone screen.
- Loss: the options start as far down as in item 1, and the why sits away from the cards it explains. Pick: no (item 1).
- Departs from: page.html `buildCard` — draws a recommendation before the context. Owner grant: no. Not blocking.

## 3. One home for `why`: the option card keeps the star only

- `optCard` draws `.pick` with the sparkle alone; the why moves to the line. A ranked item keeps its place ("1st", "2nd")
  beside the star. A multi item loses "Also recommended." The word "Recommended" shows once as text (ux-label-once);
  the star keeps `aria-label="Recommended"`.
- The `.pick` and `.nopick` rows stay, so the subgrid rows still line up. Gain: the why prints once. Loss: a reader of
  one card alone sees a star and no reason; the reason is one panel up. Pick: yes.
- Departs from: page.html `optCard` `.pick` — drops `it.why` (decided by the lane) and "Also recommended." on a multi
  item (this design's call: the word now shows once in the line). Owner grant: no. Not blocking.

## 4. The Waiting on line, state `both`, `oneline`, focus `#stOneLine`

- The page takes the first context line that starts `Waiting on:` out of `context` and draws it as its own line. Place,
  in `buildCard` order: holds, due, Waiting on, then the thread, then the context. Neutral (`--chip`), bold
  "Waiting on:" lead, no icon.
- Gain: the 220-character clamp can no longer hide it, and it prints once. Loss: a second parse of `context`
  (the Departs from line is checked by the guard only). Pick: yes.
- It is independent of the Recommended line: 844 has a Waiting on line and no valid recommendation (state `oneline`).

## 5. A holds line and a Waiting on line together, state `holds` (878)

- 878's `holds` and its Waiting on line say nearly the same thing. Both are drawn. Pick: keep both; the writer words the
  Waiting on line as who acts next, not a copy of `holds`. Gain: no special case. Loss: two lines on one fact.
- Item 836 has the same overlap with its Meanwhile line, which stays in the context.

## 6. Label length in the line (pick: whole label), states `widens` and `widenscut`

- Pick (`widens`): the whole label, with the lead word and chip, clamped at three lines; `title` holds the full text.
  837 option C's label is 213 characters. Gain: the line reads as a sentence. Loss: a CSS clamp, not `optName`.
- Other (`widenscut`, hide: "label cut at 28"): the page's own `optName`, as the ready line. Gain: one home for a short
  name. Loss: "Keep all four tools, but re…" says little.
- Multi and ranked (`multi`, `ranked`): one row per recommended option, chip and label on one line each, cut with an
  ellipsis; ranked rows carry their place. The cards hold the full labels.

## 7. A widening option that is not recommended, state `widens` (837)

- C is recommended; A widens and keeps today's warning line. Nothing new is drawn for A. A recommendation never names a
  widening option (guard rule `uniform-pick`), so the line never carries the warning. Pick: yes, no new mark.

## 8. Old item with neither line (pick: draw nothing), states `old` and `oldsay`

- Pick (`old`, 857): no `recommended` and no Waiting on line: the card is as today. Its `why` ("A session took this pick
  for you…") is no reason for an option and stays unshown, as today.
- Other (`oldsay`, hide: "says none"): two muted dashed lines, "This item names no recommended option." and
  "This item states no Waiting on line." Gain: the owner knows to ask. Loss: two lines on every old item until they close.
  Departs from: page.html `buildCard` — draws a line for a field the item lacks. Owner grant: no. Not blocking.
- 857 is the item where the owner asked what we wait on. The page shows its Waiting on line only once the writer adds
  one to its `context`.
- 844 stores `recommended: true` on option B, a field the page does not read on an option. No star, today or here.

## 9. Measured verdicts

Headless Chromium, all 11 states at 360, 390 and 430, light and dark (66 frames). No sideways scroll. No card element
past the page edge. No option card or button under 44 px (More context stays 32 px, as today). No console error. All pass.
