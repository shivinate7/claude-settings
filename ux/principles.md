# UX house rules

Read this file before you write UI in a repo with screens. Each rule states only what Vercel
web-interface-guidelines, impeccable and frontend-design do not state. Ruling: record
ux-house-rules (house UX rules). A repo's own design records can add to a rule, never cancel it. Before you lay out a screen,
also read [`layout.md`](layout.md).

## ux-press-moves-nothing

A press, a load or a change of state moves no other content.
Check: press each control and load each state. Pass when no other element moves or resizes. A
loading area keeps its loaded size, and a control keeps the box of its widest label or icon.
Source: banchi D118 (a press never moves other content) and D313 (nothing moves unless moved);
home-app `SPEC.md` "Look and feel" (owner, 2026-10-11); q_max D-684 (a pick moves nothing beside
it); ios-adblock `ios/App/AdBlockApp.swift` (the state icon has a fixed frame).

## ux-order-holds-still

A list keeps a plain, predictable order, and an act on a row does not re-rank the list.
Check: act on a row. Pass when the other rows keep their order until the person sorts again.
Source: banchi D181 (order is taken once, a sale keeps it) and D263 (a sort press re-sorts,
nothing else jumps).

## ux-unknown-is-not-empty

A screen shows loading, failed, unknown and loaded as different states.
Check: force a failed read and an unknown state. Pass when neither shows as empty, zero or done.
Source: q_max D-255 (never assert an unreached state) and D-233 (a failed history read says so);
ios-adblock `ios/App/AdBlockApp.swift` (`BlockerRow` has its own error and unknown states).

## ux-claims-are-true

Screen copy claims only what the product does and what the owner confirmed.
Check: pass when each promise (a search scope, a feature, a figure, a trust line) is true now.
Source: joyous `docs/design-brief.md` move 6 (no unsourced claim); sillage
`docs/product/screens.md` (search copy promises notes that search does not read); q_max
`docs/rules/ui-primitives.md` W1 (the weights screen's claim matches whether the blend runs).

## ux-machine-text-hidden

A code, a path, a record id or raw server text shows only in a closed disclosure.
Check: pass when each visible string is in the person's words, and machine text is behind a
"What the server said" disclosure under a plain sentence.
Source: banchi D196 (no screen string names a mechanism) and D269 (machine words hide behind a
disclosure); q_max D-640 (an error never shows the server's raw reason).

## ux-no-dead-end

Each refusal, error and end page has a control on that screen that leads on: a fix, or another
way such as a phone number.
Check: pass when each one has that control. Prose that names a place is not a control.
Source: q_max D-261 (a refusal names a reachable fix) and D-226 (offer the destination, not
prose); joyous `docs/design-brief.md` move 4 (no dead end, offer a call) and record
custom-tour-booking (an unknown link shows Book a tour and the phone).

## ux-empty-one-action

An empty state is one sentence that says what fills it, and one control that fills it.
A list that has no data yet hides its filters. A list that a filter emptied keeps its filters,
and its one control clears the filter.
Check: pass when an empty list shows one sentence and one control. With no data, the filters
are hidden. When a filter emptied it, the filters show and the control clears the filter.
Source: banchi `CLAUDE.md` "Register" and `docs/DESIGN.md` `EmptyState`; q_max
`specs/ux-plan-b.md` B2 (owner confirmed, 2026-09-29).

## ux-ask-or-undo

A destructive press asks first when it cannot be undone, and acts and offers Undo when it can.
Check: pass when no destructive press does both or neither, and each ask names the act and the
count, with first focus on Cancel.
Source: banchi `docs/DESIGN.md` ConfirmSheet row (first focus on Cancel) and UX-099 (ask first,
or undo after; the ask names the count); banchi D57 (mark sold is one press, undoable); q_max
D-497 (un-retire is an undo) and D-653 (a restore keeps the retirement in the log).

## ux-keep-what-was-made

Never discard input that a person made and that no server can return.
Check: type, then close, go back, change tabs and leave the app. Pass when the input is still
there on return.
Source: q_max D-399 (a screen with unrecoverable input stays mounted); sillage
`docs/product/screens.md` (Close discards the review, so `ReviewDraft` keeps it) and
`docs/design/system.md` (edit mode keeps the other answers).

## ux-control-earns-place

A control that changes nothing on a view is absent, and an expected control that is off says why.
Check: pass when each control changes something on its view, and each disabled control gives
its reason on hover and on focus.
Source: q_max D-675 (a filter shows only where it changes something). q_max `specs/ux-plan-b.md`
B2 (a disabled button says why; owner confirmed, 2026-09-29). banchi `docs/DESIGN.md` (the spend
button is absent, not disabled, until its preflight answers).

## ux-one-plain-name

Each screen and each act has one plain name, and each icon has one meaning.
Check: the nav label is the page title. An act keeps one name on every screen. An icon keeps one
meaning. Each enum value shows a label. Pass when all four hold.
Source: q_max D-582 (one plain name for each screen) and `docs/rules/ui-primitives.md` NAME1
(one act gets one name).
banchi `docs/DESIGN.md` UX-118 (one icon, one meaning) and `CLAUDE.md` "Register".

## ux-a11y-floor

Each screen meets the accessibility floor in `a11y.md`.
Check: run the CI check in `a11y.md` on the changed screens, at each size and theme they ship in.
Pass when it is green and the hand checks there pass.
Source: q_max D-648 (contrast floor); banchi `app/tests/gallery.spec.ts` (axe on the kit);
sillage `CLAUDE.md` (axe reads contrast as incomplete under jsdom, and a placeholder passes axe);
ios-adblock `ios/App/AdBlockApp.swift` (Dynamic Type).

## ux-answer-at-press

The answer to a press shows where the press was.
Check: press each control that gives an answer, such as a count, a message or a state change.
Pass when each answer appears at the control that was pressed, or beside it.
Source: banchi D118 and UX-058, q_max D-640.

## ux-long-run-stops

A run that takes more than a few seconds shows a Stop control.
Check: for each run that takes more than a few seconds, look for a Stop control that ends it.
Source: q_max D-319.

## ux-all-is-well

A status summary names only what is not normal. When nothing is not normal, it says "All is well."
Check: pass when a status summary lists only the items that are not normal. With no such item, it
shows "All is well." and no other item.
Source: home-app `SPEC.md`.

## ux-thumb-zone

On a phone layout, the main input and the main action sit in reach of the thumb.
Check: phone layouts only. Pass when a reviewer who holds the phone in one hand reaches the main
input and the main action with the thumb.
Source: sillage `docs/design/system.md`.
