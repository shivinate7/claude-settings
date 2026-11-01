# UX checklist

Copy this list once for each changed screen, at each size and theme it ships in. Mark each line
pass or fail. A fail is a finding. Give the rule id, the screen, the size and the theme. The rules
and their checks are in `principles.md`.

Screen: ____ Size: ____ Theme: ____

- [ ] ux-press-moves-nothing: Do all other elements keep their place and size on each press and load?
- [ ] ux-order-holds-still: Do the rows keep their order after an act on one row?
- [ ] ux-unknown-is-not-empty: Do a failed read and an unknown state each show their own words?
- [ ] ux-statements-are-true: Is each promise in the copy true of the product now?
- [ ] ux-machine-text-hidden: Is each code, path, id and server text behind a closed disclosure?
- [ ] ux-no-dead-end: Does each refusal, error and end page have a control that leads on?
- [ ] ux-empty-one-action: Is each empty state one sentence and one control? With no data, are filters hidden? After a filter empties the list, do filters show with a clear control?
- [ ] ux-ask-or-undo: Does each destructive press either ask first or offer Undo, never both or neither? Does each ask name the act and its count, with first focus on Cancel?
- [ ] ux-keep-what-was-made: Is typed input still there after close, back, a tab change and a return?
- [ ] ux-control-earns-place: Does each control change something, and does each disabled one say why?
- [ ] ux-one-plain-name: Do the nav label and page title match? Does each act keep one name, each icon one meaning, and each enum value a label?
- [ ] ux-label-once: Does each label and status word show once, with shape or colour in each other place? Does `label_once.py` print nothing, or only hits that are data?
- [ ] ux-a11y-floor: Is the `a11y.md` CI check green, and do its hand checks pass?
- [ ] ux-a11y-floor (touch size): Are touch targets 44 by 44 CSS px on touch screens and 24 by 24 CSS px for a mouse? The axe check covers only 24 px, so 44 px on touch is a hand check.
- [ ] ux-answer-at-press: Does the answer to each press show at the control that was pressed, or beside it?
- [ ] ux-long-run-stops: For each run that takes more than a few seconds, is there a Stop control that ends it?
- [ ] ux-all-is-well: Does a status summary name only what is not normal, or say "All is well." when nothing is?
- [ ] ux-thumb-zone: On each phone layout, can a thumb reach the main input and the main action? (Phone layouts only.)
- [ ] ux-works-when-script-fails: With JavaScript off, and with WebGL off, are the content and the main action reachable, or does the page say what is missing and lead on?
- [ ] ux-lost-scene-recovers: After a forced context loss, does the canvas show words, and does the scene return on restore? (3D pages only.)
- [ ] ux-still-scene-draws-nothing: While the scene rests, does the draw-call count stay 0? (3D pages only.)
- [ ] ux-canvas-has-words: Does each canvas that carries information have a name, a text equivalent and keyboard acts? Is each other canvas hidden from assistive technology, with aria-hidden="true" in the DOM?
- [ ] ux-scroll-stays-native: Do the wheel, trackpad, Space, Page Down and arrow keys each move the page by their usual step, with no section that holds the scroll?
- [ ] ux-forced-colors-hold: In forced-colors mode, do each control, edge, focus ring and state show?
- [ ] ux-full-height-fits: Does each `vh` value in the changed CSS have an `svh`, `dvh` or `lvh` declaration on the same selector?
- [ ] ux-vitals-measured: Are LCP, INP and CLS good at the 75th percentile of field data? Is "unmeasured" named only where the route has too little traffic for field data?
- [ ] ux-feature-baseline-or-fallback: Is each new feature Baseline Widely available, or behind a feature test with a fallback seen working?
- [ ] ux-gap-on-parent: Does each flex or grid parent space its children with `gap`, with no child margin between siblings? A `margin-inline: auto` or other one-item offset passes. Prose and flow margins outside flex or grid pass.
- [ ] ux-control-beside-area: Does each control sit next to the area it changes? Is each element between them the same in every state of the control?
- [ ] ux-layout-primitives: Is each page region built from a named layout primitive (stack, cluster, sidebar, grid, center)?
- [ ] ux-component-reads-its-box (box): Does each shared component that this change touches change shape from a container query, not the screen width?
- [ ] ux-variant-extends-home: Does each variant extend its shared component with a modifier, a custom property, a parameter or a style, and not a copy?
- [ ] ux-component-reads-its-box (breakpoints): Does each container breakpoint that this change adds change the component's shape?
- [ ] ux-fluid-tokens: Is each clamp() that this change adds a token read, in the shape `tokens.md` gives? A raw clamp() that the repo's own record rules for passes.
- [ ] ux-swift-same-intent: In Swift, does each stack set its own spacing, with no child padding to space it from a sibling? (Swift screens only.)
