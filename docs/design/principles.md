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
home `SPEC.md` "Look and feel" (owner, 2026-10-11); q_max D-684 (a pick moves nothing beside
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

## ux-statements-are-true

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

## ux-label-once

A label or a status word shows once on a screen. Each other place shows it by shape or colour.
Check: run `python3 ~/.claude/lint/label_once.py` on the `.html` files that `bin/shoot` writes. A
second showing is a hit. Pass
when it prints nothing, or when each hit it names is data, not a label. A word in a sentence passes.
Source: owner, Oct 26 20:40 CDT, on the waiting page ("Blocking", "Upcoming" and "Whenever" three
times or more: too much verbiage).

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
Source: home `SPEC.md`.

## ux-thumb-zone

On a phone layout, the main input and the main action sit in reach of the thumb.
Check: phone layouts only. Pass when a reviewer who holds the phone in one hand reaches the main
input and the main action with the thumb.
Source: sillage `docs/design/system.md`.

## ux-haptics-feel-substantial

An app on a device with haptics considers a haptic on controls that change a value, such as
sliders, steppers and toggles, so the change feels substantial.
Check: devices with haptics only. Pass when each control that changes a value, such as a slider,
stepper or toggle, gives a haptic on a change. Pass also when the screen's design record says why
it does not. The design reviewer checks it.
Source: owner, 2026-11-01 12:18 CST, in chat: "apps should consider integrating haptics on
things like sliders to make it feel substantial".

## Browser and 3D

These rules cover any page that runs in a browser, from a static web app to a full 3D site. Each one
cites a standard or platform source, not an owner repo (record ux-house-rules).

## ux-works-when-script-fails

When JavaScript, WebGL or WebGPU is off or fails, the person still reaches the content and the main
action, or a page that says what is missing and leads on. A blocked script or a failed load never leaves
the person on a blank page.
Check: open each changed route in a Playwright context with `javaScriptEnabled: false`, then in
Chromium launched with `--disable-3d-apis`. Pass when the content and the main action are reachable,
or the page names what is missing and has a control that leads on.
Source: [GOV.UK Service Manual, progressive enhancement](https://www.gov.uk/service-manual/technology/using-progressive-enhancement);
impeccable `harden` and `overdrive` give it as advice with no check.

## ux-lost-scene-recovers

When the GPU drops a 3D scene, the person sees words that say so, and the scene comes back when the GPU
returns.
Check: on the page, call `loseContext()` and then `restoreContext()` on the `WEBGL_lose_context`
extension. For a WebGPU scene, call `device.destroy()` and check for the same words. Pass when the
canvas is never blank without words, and the scene returns after restore.
Source: [MDN, WebGL best practices](https://developer.mozilla.org/en-US/docs/Web/API/WebGL_API/WebGL_best_practices)
("Budget VRAM conservatively": handle `webglcontextlost`).

## ux-still-scene-draws-nothing

A 3D scene that does not move draws no frames, so it does not spend the person's battery.
Check: before load, add an init script that wraps every method whose name starts with `draw` or
`multiDraw` on both `WebGLRenderingContext` and `WebGL2RenderingContext`, and counts each call. Let the
scene draw its first frame, then reset the counter and let the scene rest for five seconds. Pass when
the count stays 0 after the reset, and a camera move or a resize draws again. For a WebGPU scene, count
`GPUQueue.submit` calls the same way. A DevTools trace is the human view.
Source: [three.js manual, rendering on demand](https://threejs.org/manual/en/rendering-on-demand).

## ux-canvas-has-words

A canvas or 3D view that carries information has a name and a text equivalent, and each act in it
works from the keyboard. So a person on a screen reader or a keyboard gets what the view shows. A
canvas that carries no information is hidden from assistive technology.
Check: axe cannot read inside a canvas, so this is a hand check. Tab to the view and through each act
in it, with a screen reader on. Pass when the reader gives the name and the text, and each act works
without a pointer. Read the DOM: each other canvas has aria-hidden="true".
Source: [WCAG 2.2 Understanding 1.1.1, non-text content](https://www.w3.org/WAI/WCAG22/Understanding/non-text-content.html);
WCAG 2.1.1 (keyboard).

## ux-scroll-stays-native

Scroll moves the page at the person's pace, so they can read and find their way. Motion linked to scroll follows the scroll, and never holds,
slows or snaps the page.
Check: scroll each changed route with the wheel, a trackpad, Space, Page Down and the arrow keys. Pass
when each input moves the page by its usual step, and no section holds the scroll. A modal's own
scroll area, kept inside it with `overscroll-behavior`, passes.
Source: [Nielsen Norman Group, Scrolljacking 101](https://www.nngroup.com/articles/scrolljacking-101/)
("scrolljacking leads to more user pain than benefits").

## ux-forced-colors-hold

In forced-colors mode, such as a Windows contrast theme, each control, its edge, its focus ring and its
state stay visible. So a person who uses a contrast theme can see and use each control.
Check: in Playwright, call `page.emulateMedia({ forcedColors: 'active' })` and capture each changed
screen. Pass when each control, edge, focus ring and state shows. A cue made only of `box-shadow` or a
gradient fails, because the browser removes it.
Source: [MDN, forced-colors](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/forced-colors).

## ux-full-height-fits

A full-height region fits the visible phone screen, with the browser bars shown or hidden, so its bottom content and actions are never under the bars.
Check: grep the changed CSS for a `vh` value (`[0-9]vh`). Pass when each hit has an `svh` or `dvh`
declaration on the same property, declared after the `vh` line, which overrides it.
Source: [web.dev, the large, small and dynamic viewport units](https://web.dev/blog/viewport-units).

## ux-vitals-measured

Each changed route's Core Web Vitals meet the "good" lines on web.dev in a mobile lab trace and, where
it exists, at the 75th percentile of field data. The person gets a page that loads, answers a press and
holds still on a real phone.
Check: record a lab trace of the changed route on a mobile profile. Pass when LCP, INP (or Total
Blocking Time in the lab) and CLS meet web.dev's "good" lines. Where field data at the 75th percentile
exists, it must also pass. Field data is in CrUX through PageSpeed Insights, or the repo's own field log.
Source: [web.dev, Web Vitals](https://web.dev/articles/vitals) (the "good" lines, and the 75th
percentile for field data); impeccable `optimize` gives the lines as advice with no check.

## ux-feature-baseline-or-fallback

A web feature outside the repo's browser target runs only behind a feature test, with a fallback the
person can use. So the page works in the browser the person has.
Check: the repo's browser target is in its browserslist or design record, and a repo with no target
uses Baseline Widely available. For each new CSS or JavaScript feature in the diff that the target does
not cover, read its status on webstatus.dev. Pass when the feature sits behind `@supports` or a feature
test, and the fallback was seen working. To see the fallback, invert the `@supports` test or force the
feature test false, then use the page. A browser-name check fails.
Source: [web.dev, Baseline](https://web.dev/baseline); impeccable `overdrive` asks for a working
fallback, with no check.
