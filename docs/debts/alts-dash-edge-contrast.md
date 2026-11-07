# Dashed card buttons have a control edge under the 3:1 floor

**What.** The `.btn.dash` buttons in a card's `.alts` row (None of these, Mark done, Park) draw an unpressed edge in `--line`. It reads 1.35:1 in light and 1.33:1 in dark. The contrast floor in `docs/design/a11y.md` is 3:1 for a control edge, and no ruling covers it. The visible label still names each control. Step page-park-any-item (Park on every open card) added the third button. Its design review found the gap.

**Where.** `skills/waiting-page/page.html`: the `.btn.dash` rule and its `--line` token.

- **Decision.** `none`.

**Retire.** Give the unpressed `.btn.dash` edge a token at 3:1 or higher in both themes, and keep the pressed state set apart by shape (a solid edge), not by colour alone. The check: a browser test reads the computed edge colour of `#b-none-<id>`, `#b-done-<id>` and `#b-park-<id>` against the card surface in light and dark, and fails under 3:1.
