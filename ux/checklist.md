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
- [ ] ux-empty-one-action: Is each empty state one sentence and one control? Are filters hidden with no data, and shown with a clear control when a filter emptied the list?
- [ ] ux-ask-or-undo: Does each destructive press either ask first or offer Undo, never both or neither? Does each ask name the act and its count, with first focus on Cancel?
- [ ] ux-keep-what-was-made: Is typed input still there after close, back, a tab change and a return?
- [ ] ux-control-earns-place: Does each control change something, and does each disabled one say why?
- [ ] ux-one-plain-name: Do the nav label and page title match? Does each act keep one name, each icon one meaning, and each enum value a label?
- [ ] ux-a11y-floor: Is the `a11y.md` CI check green, and do its hand checks pass?
