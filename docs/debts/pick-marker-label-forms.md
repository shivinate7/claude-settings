# Pick marker misses label forms

- **What.** The `pick-reaches-page` guard reads a pick line only when `Coordinator pick` is followed by `:`, `.`, `,`, `;`, a spaced dash or the line end. A label such as `Coordinator pick A: x`, `Coordinator pick 3:`, `Coordinator pick (undoable): x` or `- [x] Coordinator pick:` reads as no marker, so a lane send passes with no page item. Coordinators write the `pick A` form in repo records. The terminator list also lacks an em dash, an en dash, `--`, `->`, `=` and a tab. The key keeps a leading backtick, so `icons-a` in backticks never matches a send without them.
- **Where.** `pick_hit` and its marker regex in `hooks/guard_merge.py`.
- **Decision.** `pick-reaches-page` (a coordinator pick reaches the waiting page); round 2 review note 1.
- **Retire.** The marker reads those four forms and a case per form is in the guard family. Shown by `hooks/test_guard.py`.
