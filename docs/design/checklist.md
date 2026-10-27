# UX checklist

Copy this list once for each changed screen, at each size and theme it ships in. Mark each line
pass or fail. A fail is a finding. Give the rule id, the screen, the size and the theme. The rules
and their checks are in `principles.md`.

Screen: ____ Size: ____ Theme: ____

- [ ] ux-press-moves-nothing: Do all other elements keep their place and size on each press and load?
- [ ] ux-order-holds-still: Do the rows keep their order after an act on one row?
- [ ] ux-unknown-is-not-empty: Do a failed read and an unknown state each show their own words?
- [ ] ux-claims-are-true: Is each promise in the copy true of the product now?
- [ ] ux-machine-text-hidden: Is each code, path, id and server text behind a closed disclosure?
- [ ] ux-no-dead-end: Does each refusal, error and end page have a control that leads on?
- [ ] ux-empty-one-action: Is each empty state one sentence and one control? With no data, are filters hidden? After a filter empties the list, do filters show with a clear control?
- [ ] ux-ask-or-undo: Does each destructive press either ask first or offer Undo, never both or neither? Does each ask name the act and its count, with first focus on Cancel?
- [ ] ux-keep-what-was-made: Is typed input still there after close, back, a tab change and a return?
- [ ] ux-control-earns-place: Does each control change something, and does each disabled one say why?
- [ ] ux-one-plain-name: Do the nav label and page title match? Does each act keep one name, each icon one meaning, and each enum value a label?
- [ ] ux-a11y-floor: Is the `a11y.md` CI check green, and do its hand checks pass?
- [ ] ux-a11y-floor (touch size): Are touch targets 44 by 44 CSS px on touch screens and 24 by 24 CSS px for a mouse? The axe check covers only 24 px, so 44 px on touch is a hand check.
- [ ] ux-answer-at-press: Does the answer to each press show at the control that was pressed, or beside it?
- [ ] ux-long-run-stops: For each run that takes more than a few seconds, is there a Stop control that ends it?
- [ ] ux-all-is-well: Does a status summary name only what is not normal, or say "All is well." when nothing is?
- [ ] ux-thumb-zone: On each phone layout, can a thumb reach the main input and the main action? (Phone layouts only.)
- [ ] ux-gap-on-parent: Does each flex or grid parent space its children with `gap`, with no child margin between siblings? A `margin-inline: auto` or other one-item offset passes. Prose and flow margins outside flex or grid pass.
- [ ] ux-layout-primitives: Is each page region built from a named layout primitive (stack, cluster, sidebar, grid, center)?
- [ ] ux-component-reads-its-box (box): Does each shared component that this change touches change shape from a container query, not the screen width?
- [ ] ux-variant-extends-home: Does each variant extend its shared component with a modifier, a custom property, a parameter or a style, and not a copy?
- [ ] ux-component-reads-its-box (breakpoints): Does each container breakpoint that this change adds change the component's shape?
- [ ] ux-fluid-tokens: Is each clamp() that this change adds a token read, in the shape `tokens.md` gives? A raw clamp() that the repo's own record rules for passes.
- [ ] ux-swift-same-intent: In Swift, does each stack set its own spacing, with no child padding to space it from a sibling? (Swift screens only.)
