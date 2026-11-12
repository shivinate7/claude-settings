# Waiting page, steps tier-items-sorted and answered-sections-by-repo: design notes

Mockup: `docs/design/tier-sort.html`. Screen: `skills/waiting-page/page.html` (main 87daa5b50).
Deep links: `#s=page|single-repo|groups|no-repo|last-sent|empty|key-stops|key-rank|key-oldest|order-pin|order-free|order-az|seen-once|rail-plain`,
`&w=all|390|800|1280`, `&t=light|dark`, `&lab=off`, `&hide=<state>,...`.
Sizes: phone 390, mid 800 and wide 1280, light and dark. `layout.py devices` prints `unknown` for this repo,
so the sizes come from the brief. Mid 800 is drawn because page.html has a breakpoint at 960.
The mockup draws with page.html's own `<style>` (lines 8 to 953). Each new rule reads a page token; it adds no colour.
Every order on the mockup comes from one sort function in its script (the pick below), not from hand placing.
Options are named by name, never by a letter: the waiting page stamps its own letters.

Owner's outcome (2026-11-12 11:19 CST): the tiers are long and unsorted. He must find the item that matters
most first: what stops the most work, then the oldest.

Settled, not options here:
- New before seen inside a tier, and an arrival after load first (stale-asks-sink notes, "settled behaviour",
  owner ask Nov 1 17:16 CST). It holds inside each repo sub-group.
- A group never splits and sits at its best member's key (`sorted()`, `rk`, `age`).
- `repo` exists today. SKILL.md "Item fields" makes it required on every open decision and task, and
  page.html lists it in `itemFields`, but page.html never reads it. The answered-sink notes (point 5) called it
  a new field; it has landed since. This design is the first reader.

## Rulings (coordinator, 11:48 CST Nov 12; undoable picks, no owner question)

- Q1 "Most stopped work first". `holds` is one free sentence, not a list, so a length sort would guess.
  The field `stops` is added. The question-form check refuses a `stops` entry that `holds` does not name,
  and a `stops` on an item with no `holds`, so the two cannot drift.
- Q2 The `meta/page` field `repo` is added, with the `identity.name` fallback.

## 1. The sort key in Blocking. Owner grant: yes

What page.html has today: no count of what an item stops. Measured against the fields:
- `holds` is one free sentence. Reading a count from it is a guess (SKILL.md: "Never guess an urgency").
- Group size counts questions to answer together, not stopped work.
- `rank` is triage's judgment. It can carry the order, but the owner never sees why, and whether writers set it
  on every item today is unmeasured.
- `lane` and `waits` mark an item the owner already answered. They stop nothing of his.
- `by` is a deadline. An item with `by` and no `holds` is in Upcoming.
- Any item with `holds` is in Blocking (`rawTier`), so Upcoming and Whenever hold nothing with stopped work.
  A stopped-work key can act in Blocking only.

Options. Each draws the same five Blocking items of one repo. Picture ids: `#order-stops`, `#order-rank`, `#order-oldest`.

- "Most stopped work first" (`#s=key-stops`). Pick. A new writer field `stops`: a list of what the answer
  stops, each a lane slug, a PR number or a step id (`["lane fix-proxy", "PR #1201"]`). The session that
  asks names them with `holds` (SKILL.md "Add an item": fill `holds` whenever a lane, a merge or a PR waits),
  and the writer writes them. The count is the list's length; a group counts each entry once across members.
  Sort in Blocking: arrival, then new before seen, then most `stops`, then `rank`, then oldest. An item with
  `holds` and no `stops` counts 0 and sits after the counted ones (No. 57).
  Gain: the order follows the owner's own rule, the count shows on the card, and each entry is checkable
  (the writer can see that a lane or PR is live). Loss: one more field on every Blocking item; `holds` and
  `stops` say the same thing twice, so they can drift apart.
- "Triage's order only" (`#s=key-rank`). No new field. Triage sets `rank` from what it reads in `holds`.
  Gain: nothing to add. Loss: the card shows no reason for its place, and triage must re-rank every item
  on each add. The picture's ranks are what a writer might set; the order is only as good as that pass.
- "Oldest first" (`#s=key-oldest`). No field; `rank` dropped from the key. Gain: nothing to set or keep.
  Loss: a small item filed first sits above one that stops four lanes.
- Departs from: SKILL.md "Item fields", `rank` ("orders items inside a tier") and page.html `sorted()`
  `by.holds` (`byRank` first). In Blocking, `stops` goes ahead of `rank`; `rank` breaks ties. Not blocking.
- Upcoming, Whenever and Pick stands keep today's keys (`sorted()`): triage's rank, then deadline (Upcoming)
  or decisions first (Whenever), then oldest. The long Whenever list is fixed by the repo sub-groups (point 2),
  not by a new key.
- Builder note: the order is worked out once at load, with `freezeSeen`, and kept. A writer update while the
  page is open moves no card until reload (ux-order-holds-still). An arrival still goes first.

## 2. One sub-group per repo inside each tier. Owner grant: yes (the `meta/page` field `repo`)

- Pick (`#s=page`): inside each tier, one sub-group per repo. The head is the answered-sink point 5 shape:
  a neutral letter tile (`--chip`, `--ink`), the repo name, a count and a solid rule. It is `role="group"`
  labelled by the head. The head shows the name part of `owner/name`; it shows the whole slug only when two
  repos on the page share a name.
- An item with no `repo` sits under this repo (No. 52, `#s=no-repo`).
- Which repo is "this repo": the page has no `owner/name` of its own (page.html `waitWords` comment).
  Needed outside my scope: a `meta/page` field `repo` (`owner/name`) that the writer sets when it makes the
  page. Until it is set, match the name part of each item's `repo` against `identity.name` (SKILL.md: "name is the
  repo's name"), ignoring case.
- A group whose members are in different repos sits once, under the repo of its member that stops the most,
  this repo on a tie (`#s=groups`: the tokens group sits under sillage). A member from another repo names its
  repo in its top row ("about sample-repo"), with the weight and colour of "goes with No. 4".
- A group shows its count once, in its head ("stops 3"): the members' lists, each entry counted once. Its
  cards show no count, so the number on screen is the one it sorts by.

## 3. Order of the sub-groups

Picture ids: `#repos-pin`, `#repos-free`, `#repos-az`. Each draws one Blocking tier where this repo's first item stops only 1.

- "This repo first, then most stopped" (`#s=order-pin`). Pick. This repo first (the step's title), then each
  other repo at its first item's place by the tier's key, A to Z on a tie. Gain: the owner's own repo is always
  in one place, and the next repo is the one with the most stopped work. Loss: a repo whose item stops four
  lanes can sit below this repo's item that stops one.
- "Most stopped, no repo pinned" (`#s=order-free`). Gain: the purest form of the owner's rule. Loss: this repo
  moves between visits. Departs from: the step answered-sections-by-repo title ("this repo first").
- "This repo first, then A to Z" (`#s=order-az`). Gain: a fixed place for each repo. Loss: the order no longer
  says what matters most.

## 4. Why the order is what it is

- Pick: one line under each tier head names that tier's key (`.tsub`, the words of the rulings' `p.rsub`).
  Wide, it sits beside the head; on a phone it wraps under it. When the tier holds this repo and another, it
  starts "This repo first." A tier that holds only another repo has no such words, since they would be false.
  The keys differ, so no sentence repeats (ux-label-once).
  - Blocking: "Most stopped work first, then triage's order, then oldest."
  - Upcoming: "Triage's order first, then nearest deadline, then oldest."
  - Whenever: "Triage's order first, then decisions, then oldest."
- On each Blocking card the key shows in the top row: "stops 4", ink and weight 600 beside the muted "waited".
  Its names go to a screen reader and `title` (the `holds` line says them in words). No colour carries it.
- Loss: "triage's order" shows in each line. Triage is the page writer (GLOSSARY), so the words are true.
  When `rank` is unset, the line still holds: unranked items follow the ranked ones.

## 5. Seen divider, rail, Answered, one repo, a sent last card, empty

- Seen divider: once inside each sub-group that has seen items (`#s=page`). Its words show on the first divider
  of the page only; later ones show the eye and the dotted rule, words in `.sr` and `title` (stale-asks-sink 1A).
  Gain: one head per repo. Loss: up to one divider per repo per tier (answered-sink point 5 named this).
  - Alternative "Seen divider once per tier" (`#s=seen-once`): new items of every repo, one divider, then the seen
    items of every repo. Gain: one divider per tier. Loss: each repo head shows twice in the tier.
- Rail (`#s=page`): a tier row keeps its chips in the list's order. With two repos or more, each repo's run of
  chips starts with its tile and name, and the run wraps as one so a phone row never ends on a lone tile.
  The name shows at every size: sample-repo and sillage share "S". A chip's screen-reader words add
  "about <repo>" for another repo. Alternative "Rail with no repo marks" (`#s=rail-plain`). Gain: a shorter
  rail. Loss: the rail no longer shows where one repo ends.
- Answered: no sub-groups. It stays newest first (answered-sink point 1): a record of what the owner sent, not
  a list to work through.
- One repo in a tier: when that repo is this repo, no head (Upcoming in `#s=page`, every tier in `#s=single-repo`):
  the page looks as today, plus the line. When the tier's only repo is another repo, its head stays, so the
  owner sees whose it is (Upcoming in `#s=no-repo`).
- A repo's last card sent on this visit (`#s=last-sent`): under `SENT_MOVE` "sink" the card moves to Answered and
  its head goes with it, as a tier with no items goes today. The heads left are fixed at load: this repo's head
  stays though the tier now holds one repo, so nothing else changes shape until reload.
- Empty (`#s=empty`): as today.

## Needed outside the design folder

- SKILL.md item schema: a new field `stops` (list), its rule beside `holds`, and the writer's refusal of `stops`
  without `holds`. `rank` text changes to "breaks ties after `stops` in Blocking".
- SKILL.md `meta/page`: a new field `repo` (`owner/name`).
- page.html: `sorted()` and `renderList()`/`renderRail()` per points 1 to 5.

## Checked

- Playwright, Chromium: all 14 states at 390, 800 and 1280, light and dark (84 runs). No script error, no
  sideways scroll in the frame.
- `check_designs.mjs` on a scratch copy of main's page with this mockup in `designData` and a three-option item
  for point 1 (one `state` and `focus` each, keys `a`, `b`, `c`): exit 0, `problem: null`.
- `label_once.py` on each state's rendered page at 390: hits are today's "Asked before" (the later dividers'
  screen-reader words) and repo names as data (header, rail run and sub-heads; up to 5 times for this repo
  on `#s=page`). No label of this design repeats.
- impeccable critique, single context (no sub-agent tool). Detector: no finding in the mockup's markup; on
  the rendered page it flags the side-tab card edge, a flat type scale and stripes, all from today's page.html
  CSS, outside this step. Fixed: the rail tiles collided on a first letter, so the rail now shows the name.
  Open: `stops` and `holds` can disagree (point 1, a loss of the pick).
