Assumed Duo size: 360x780 folded, 760x780 unfolded (no size written anywhere; to confirm)

# Banchi phone, blind lane 1: notes

Lane kind: blind. Lane: banchi-phone-blind-1. Mockup: `banchi-phone-blind-1.html` (opens from disk).
PNGs: `png/`. All cards, orders and buyers are made up.

Deep links: `#d=<1..3>&s=<empty|loading|list|error>&size=<folded|unfolded>&t=<light|dark>` shows one frame.
More screens: `#d=<n>&v=<view>&t=light` (D1: pack, shoot, check, send. D2: pull, pack, shoot, check, send.
D3: box, shoot, check, pack, seal, send). Pick pictures: `#pick=<2a..4b>&t=light`. Overview: `#d=<n>&ov=1&t=light`.

Data in every list state: 18 orders today (5 packed, 2 ready to seal, 11 with 16 cards to pull in
10 boxes), 30 boxes on 3 shelves, a Bloomburrow sitting into Box 15 of about 300 cards (212 shot so
far, so Box 15 holds 212; 17 of them wait for the seller, everywhere the count shows), a send of 236 cards at $517.84, with 47 under the $0.49 floor held back.

Colour: Banchi blue #3d5af1 is the only hue. Everything else is neutral grey. Status shows by shape
(filled, outlined, dashed), not by a second hue. In dark theme, blue text uses a light tint of the
same blue (#a3afff) for 4.5:1; blue fills keep #3d5af1 with white text (4.9:1).

## D1 · Four tabs

- Idea: a plain bottom tab bar with one tab per act: Pull, Shoot, Check, Send.
- Structure: four flat lists. Navigation: tab bar (house default). First screen: Pull, a list of
  sold cards grouped by box in shelf order, so one walk along the shelf pulls all of them.
- Seller: Shoot (camera, card number next, last five reads, End sitting), then Check (one unsure
  card at a time, the candidates as rows, Hold back or Skip), then Send (one summary, one button).
- Helper: opens on Pull. Each row says box, card number, the count after a divider, and the buyer.
  Tap the circle when the card is in hand. Unfolded: the right page draws the box with the cards to pull.
  Packing: an "Envelopes" section at the end of the Pull list (view `pack`) lists each order whose cards
  are all pulled, with its cards by name. The helper writes the name on an envelope, puts the cards in,
  seals it and taps its circle; the row stays in place, marked packed.
- Gain: familiar; every act one tap away; easy to build. Loss: the helper sees seller tabs and
  badges they never use; the list asks the helper to read many rows; Pack is only a section of Pull.

## D2 · Today

- Idea: no tabs. One home that lists today's jobs as plain sentences, each with one button. A job
  opens a guided walk, one thing per screen.
- Structure: hub and walk. Navigation: Back to Today from each walk; no tab bar. First screen:
  Today, with "Pull sold cards" first, then "Cards that wait for you", "Send to TCGplayer",
  "Photograph a box".
- Seller: "Photograph a box" opens a full-screen camera; "Look at them" walks the unsure cards;
  "Review the send" is one page and one button.
- Helper: "Start pulling" shows one card per screen: the box number very large, where the box sits,
  how to find the card, its photograph, and one button "I have it". Then "Put the card in the
  envelope for Carla V." with slots for the order's cards.
- Gain: the screens explain themselves; the helper never meets a list or a seller word; the next
  job is always on top. Loss: no overview of all pulls at once; more taps for a seller who knows
  the app; breaks the house rule "phone navigation uses a bottom tab bar" (see choice 2).

## D3 · Shelf (bold)

- Idea: the app is a drawing of the real shelf. No tabs and no order list. Thirty tiles sit where
  the boxes sit; a box with sold cards is blue with a count. You zoom shelf, box, card.
- Structure: spatial. Navigation: tap to zoom in, Back to zoom out. First screen: the shelf, with
  a Packing table tile and three seller buttons (Photograph, Check 17, Send 236).
- Seller: a sitting is "Filling Box 15": the camera plus a bar of how full the box is. Unsure
  cards show as dashed marks at their place in the box. Send is a sheet over the shelf.
- Helper: "Blue boxes hold sold cards. Tap one." The box view draws the box from above, front at
  the top, dividers as bands, each sold card as a blue line at its place. The Packing table shows one
  envelope per order with a dot per card, split into "Ready to seal" and "Still filling". Tapping a
  ready envelope opens a sheet (view `seal`): write the name, put the cards in, seal, then "Mark packed".
  When sales cannot be read, all box tiles and the Packing table tile turn striped ("sales not known"; the Packing table reads "As of 8:05: 2 ready · 11 filling"); dashed keeps one meaning,
  "cards wait for you". The first screen fits 780 tall with the Packing table visible.
- Gain: matches what the helper sees at the shelf; place in the box is a picture, not a number;
  the seller sees the whole store at a glance. Loss: 30 tiles (44 px tall) is the limit before the
  first screen needs to scroll; tiles need a number label on each real box; no common app works like this, so
  a first-time user needs the one-line hint.

## Design choices

1. **Pull list order is shelf order, not order date.** Gain: one walk along the shelf; the list holds
   still when a card is pulled (ux-order-holds-still). Loss: an urgent order is not on top. Pick: shelf order.
2. **D2 and D3 drop the bottom tab bar.** Gain: the helper sees one job, not four sections. Loss:
   breaks the house default "on a phone, navigation uses a bottom tab bar". Pick: keep the option open
   until the direction is chosen. Owner grant: yes.
3. **A card's place shows two ways: "Card 187" and "29th after Normal A–F".** Gain: the divider count
   stays right when cards before the divider leave; the front count is the true place. Loss: two
   numbers to read. Pick: see question 2.
4. **The pulled mark is a large circle with no word; one hint line explains it.** Gain: the status word
   shows once (ux-label-once); a 44 px target. Loss: a new helper must read the hint once. Pick: circle.
5. **Unsure cards keep their place and wait in a pile (Check).** Gain: the sitting runs without a stop;
   nothing is guessed. Loss: the seller comes back to them later. Pick: see question 3.
6. **"Auto" shoots when a still card fills the guide.** Gain: zero attention per card. Loss: needs the
   camera code to detect a still card; if it cannot, the claim is false (ux-claims-are-true).
   Pick: show it, confirm it can be built. Owner grant: yes.
7. **A failed sales read keeps the last list, and the time of that list shows once per screen** (in the
   error sentence, or on the D3 Packing table page that the error opens next to).
   Gain: the helper can still work; unknown is not shown as empty. Loss: a card that sold after 8:05
   is missing until Try again works. Pick: keep the labelled list.
8. **Server text hides behind "What the server said".** Gain: plain words first (ux-machine-text-hidden).
   Loss: one more tap for the seller who wants the code. Pick: disclosure.
9. **Order numbers do not show; the buyer name is the envelope label.** Gain: the helper writes a
   name, not a 21-character code. Loss: two buyers with one name need the order number. Pick: name,
   with the number in the order detail. Owner grant: yes.
10. **Each physical box carries a large number label (Box 1 to 30).** Gain: the helper matches a
    number, not a set name. Loss: the seller must label boxes and keep numbers stable. Pick: numbers.
    Owner grant: yes (asks a physical step of the seller).
11. **Price floor ($0.49) is shown on Send with "Change the floor".** Gain: the seller knows why 47
    cards stay back. Loss: one more line on Send. Pick: show it.
12. **Unfolded uses the right page for the next level (box or walk step), not a wider list.** Gain:
    the two pages read as list and detail; nothing sits under the hinge. Loss: a laptop pose puts the
    detail on the upright half only. Pick: list left, detail right.
13. **Only one hue.** Status by shape (filled, outlined, dashed, striped), one meaning per shape. Gain: follows the palette rule;
    works for colour-blind users. Loss: the error box has no red. Pick: one hue.

## Picks for shiv

### Q1. Which direction or directions to keep?

- A. D1 Four tabs. Picture: `png/d1-overview.png`. Gain: familiar, fast for the seller, house tab
  bar. Loss: the helper meets seller tabs and a long list.
- B. D2 Today. Picture: `png/d2-overview.png`. Gain: the helper gets one card per screen with
  plain sentences; the next job is on top. Loss: no tab bar; no all-at-once overview.
- C. D3 Shelf (bold). Picture: `png/d3-overview.png`. Gain: the screen matches the physical shelf;
  place in a box is a picture. Loss: new to everyone; grid limit near 30 boxes.
- My pick: B, and borrow D3's box drawing for the helper's "I cannot find it" screen.

### Q2. How does the helper find the card inside the box?

- A. Count from the front: "Count 108 cards from the front." Picture: `png/pick-2-a.png`.
  Gain: one number, always true. Loss: counting 108 cards by hand is slow and easy to miscount.
- B. Count from a divider: "Find the divider Normal A–F. Take the 34th card after it." Picture:
  `png/pick-2-b.png`. Gain: short counts; the divider is a landmark. Loss: needs dividers every
  ~100 cards; the seller must keep divider names on the phone and in the box the same.
- C. Show the two neighbours: photographs of the card before and after. Picture:
  `png/pick-2-c.png`. Gain: no counting; looks like the box. Loss: the helper still needs a start
  point; a neighbour that sold and left breaks the hint.
- My pick: B, with C shown under "I cannot find it".

### Q3. When does the seller resolve the cards Banchi is not sure of?

- A. During the sitting: the camera stops and asks at once. Picture: `png/pick-3-a.png`. Gain: the
  card is still in hand. Loss: breaks "zero attention per card"; the stack waits.
- B. After the sitting, in a pile: one card at a time with its photograph. Picture:
  `png/pick-3-b.png`. Gain: the sitting never stops; the seller answers in one go. Loss: the seller
  may need to find the card again for a close look (its place is shown).
- C. Never by hand: all unsure cards stay back from the send. Picture: `png/pick-3-c.png`. Gain:
  zero attention. Loss: unsure cards are often the valuable printings; they never get listed.
- My pick: B.

### Q4. Does the helper get their own home?

- A. One home for both people (D2 Today with all jobs). Picture: `png/pick-4-a.png`. Gain: one app,
  one set of screens to learn and build. Loss: the helper sees seller jobs and money.
- B. A helper home with only "Start pulling" and "Envelopes to seal"; the seller is behind
  "I am the seller". Picture: `png/pick-4-b.png`. Gain: nothing on screen the helper does not use.
  Loss: one more mode; the switch must not confuse the helper. Owner grant: yes.
- My pick: B.
