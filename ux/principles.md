# UX house rules

Read this file before you write UI in a repo with screens. Each rule states only what Vercel
web-interface-guidelines, impeccable and frontend-design do not state. Ruling: record
ux-house-rules (house UX rules). A repo's own design records can add to a rule, never cancel it.

## ux-press-moves-nothing

A press, a load or a change of state moves no other content.
Check: press each control and load each state. Pass when no other element moves or changes size.
A loading area holds its loaded size, and a control keeps the box of its widest label or icon.
Source: banchi D118 (a press never moves other content) and D313 (nothing moves unless moved);
home-app `SPEC.md` "Look and feel" (owner, 2026-10-11); q_max D-684 (a pick moves nothing beside
it); ios-adblock `ios/App/AdBlockApp.swift` (the state icon has a fixed frame).

## ux-order-holds-still

A list keeps a plain, predictable order, and an act on a row does not re-rank the list.
Check: act on a row. Pass when the other rows keep their order until the person sorts again.
Source: banchi D181 (order is taken once, a sale keeps it) and D263 (a sort press re-sorts, nothing else jumps);
degen D11 (no AI picks what to read).

## ux-unknown-is-not-empty

A screen shows loading, failed, unknown and loaded as different states.
Check: force a failed read and an unknown state. Pass when neither shows as empty, zero or done.
Source: q_max D-255 (never assert an unreached state) and D-233 (a failed history read says so);
ios-adblock `ios/App/AdBlockApp.swift` (`BlockerRow` has its own error and unknown states).

## ux-claims-are-true

Screen copy claims only what the product does and what the owner confirmed.
Check: pass when each promise (a search scope, a feature, a figure, a trust line) is true now.
Source: joyous `docs/design-brief.md` move 6 (no unsourced claim); sillage
`docs/product/screens.md` (search copy promises notes that search does not read); q_max check W1
(the weights screen's claim matches the blend).

## ux-machine-text-hidden

A code, a path, a record id or raw server text shows only in a closed disclosure.
Check: pass when each visible string is in the person's words, and machine text is behind a
"What the server said" disclosure under a plain sentence.
Source: banchi D196 (no screen string names a mechanism) and D269 (machine words hide behind a
disclosure); q_max D-640 (an error never shows the server's raw reason).

## ux-no-dead-end

Each refusal, error and end page offers a next step that the person can reach from that screen.
Check: pass when each one has a control that leads on: a fix, Try Again, or another way, such as a
phone number. Prose that names a place is not a control.
Source: q_max D-261 (a refusal names a reachable fix) and D-226 (offer the destination, not
prose); joyous `docs/design-brief.md` move 4 (no dead end, offer a call) and record
custom-tour-booking (an unknown link shows Book a tour and the phone).

## ux-empty-one-action

An empty state is one sentence that says what fills it, and the one control that does.
Check: pass when an empty list shows one sentence and one control, and its filters stay hidden.
Source: banchi `CLAUDE.md` "Register" and `docs/DESIGN.md` `EmptyState`; q_max
`specs/ux-plan-b.md` B2 (owner confirmed, 2026-09-29).

## ux-ask-or-undo

A press that cannot be undone asks first, and a press that can be undone acts and offers Undo.
Check: pass when no destructive press does both or neither, and each ask names the act and the
count, with first focus on Cancel.
Source: banchi `docs/DESIGN.md` UX-099 (ask first, or undo after) and D57 (mark sold is one
press, undoable); q_max D-497 (un-retire is an undo) and D-653 (a restore keeps the retirement in
the log); ios-adblock `DESIGN.md` (a removed site keeps its report).

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
Source: q_max D-582 (one plain name for each screen) and check NAME1 (one act gets one name).
banchi `docs/DESIGN.md` UX-118 (one icon, one meaning) and `CLAUDE.md` "Register".

## ux-a11y-floor

Each screen meets the accessibility floor in `a11y.md`.
Check: run the CI check in `a11y.md` on the changed screens, at each size and theme they ship in.
Pass when it is green and the hand checks there pass.
Source: q_max D-648 (contrast floor); banchi `app/tests/gallery.spec.ts` (axe on the kit);
sillage `CLAUDE.md` (four test layers); ios-adblock `ios/App/AdBlockApp.swift` (Dynamic Type).
