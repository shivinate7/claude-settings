# Waiting page, lane answered-section-folded: design notes

Mockup: `docs/design/answered-folded.html`. Screen: `skills/waiting-page/page.html` (3ff7b367): `answeredEl`, `sectionEl`,
`state.answeredOpen`, the `.rhead` and `.tier.sunk` CSS. Deep links: `#s=closed|closed-sub|open|reply|late-reply`,
`&w=all|390|1280`, `&t=light|dark`, `&lab=off`, `&hide=<state>,...`. Sizes: phone 390 and desktop 1280, light and dark.
`layout.py devices` prints `unknown` for this repo, so the sizes come from the brief. The mockup draws with page.html's own
`<style>` and adds three rules, each reading `--muted` or `--body` only.

Owner gripe (2026-11-08 12:31 CST): the Answered section shows cards with nothing to see or do. Decided in the brief: the
section starts closed; it opens on load only when a card inside carries the New reply mark; the rail's Answered head and its
chips already open it on a press.

1. Closed on load (`#s=closed`). `state.answeredOpen` starts false. Gain: the open work ends the list. Loss: one press to
   see any answer. Pick: yes (decided).
2. The closed line's words: "Answered 5 Show to change one", all inside the `.rhead` button, so the whole line is the 44 px
   target. "Show" is the card fold's verb (ux-one-plain-name). "Tap" is not used: it is false with a mouse
   (ux-statements-are-true). "Show to change an answer" wrapped at 390. Gain: one line at 390 and 1280. Loss: "one" leans
   on the head's word. Pick: yes.
3. The sub line hides while closed and comes back when open, with today's open words. Gain: one line, as asked. Loss: the
   closed head no longer gives the newest time. Pick: hide it. Alternative "Sub line kept" (`#s=closed-sub`): head as today,
   sub line "Show the list to change an answer. Newest <time>." Loss: two lines.
4. The hint shows only while closed (`.rhead[aria-expanded="true"] .rhint`). Open, the chevron and the sub line carry it, as
   on the rulings head. Pick: yes.
5. Opens on load with a New reply inside (`#s=reply`): the section opens, that card's fold opens (`foldOpen` = `newReply`,
   as today), and the other cards stay folded. Builder: decide `answeredOpen` once, beside `freezeSeen`, from the frozen
   Answered set and `newReply`. Never read it live, or a reply that lands mid-visit opens the section.
6. A reply that lands after load (`#s=late-reply`), option "Mark on the closed head": the closed head carries the New reply
   mark (words, as the first mark on the screen), and the hint drops whole to a second row at 390. The section does not
   open by itself. Gain: the reply is not hidden. Loss: one more place for the mark. Pick: yes. Owner grant: yes (it adds
   a mark to a head, which the decided behaviour does not name).
7. Arbiter rulings: drawn as today, open on load, sub line kept. `newReply` never marks a ruling, so "a section opens only
   with a New reply" would close rulings on every load. Pick: rulings unchanged. Owner grant: yes (if "a section" meant
   rulings too).
8. Builder note: `sectionEl` sets `e.sub.hidden = !o.open` for Answered; `answeredEl` passes the hint as a span in the head.
   `.tier.sunk .rhead` wraps, and `.rhint` does not, so the hint never splits.

Departs from: page.html `state.answeredOpen: true` (opened on load). Owner gripe, 2026-11-08 12:31 CST.

## Checked

- Playwright, Chrome: 5 states at 390 and 1280, light and dark (20 runs). No script error, no sideways scroll. A press on
  the head toggles; the rail's Answered head opens the section. The closed head is one 44 px line at 390 and 1280.
- `label_once.py` on the 5 states at 390: no hit.
