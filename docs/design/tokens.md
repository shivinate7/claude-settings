# UX house tokens

House default design values. A repo may override them. Each part names the repos that show the
value. Ruling: record ux-house-rules (house UX rules). Owner ruling, 2026-10-11.

## Spacing and radius

- Spacing uses a 4 px step. Every fixed gap is a multiple of 4 px. A fluid token's two ends sit on
  the step; its middle can fall between steps (see Fluid tokens).
- Space tokens are `--space-N`, where step N is N x 4 px. `--space-2` is 8 px.
- Corner radius is 8 px.

Seen in: banchi, q_max, degen spec, sillage, feed-build, home.

## Fluid tokens

A size that grows with its box is a clamp() token. Rules: `layout.md` ux-fluid-tokens.

```css
:root {
  --space-2: 8px;
  --space-4: 16px;
  --space-fluid-2-4: clamp(var(--space-2), 1.5cqi + 4px, var(--space-4));
}
```

- The name gives the two ends, as steps: `--space-fluid-<low>-<high>`.
- Both ends are fixed space tokens, so they sit on the 4 px step. Between the ends the value is
  fluid and can fall off the step. A repo whose check needs every gap on the step, such as
  mailaudit's claim 14, keeps fixed tokens.
- The middle term uses `cqi` (the query container's inline size), so the size follows the box.
  With no query container, `cqi` reads the small viewport. Use `vi` only for page-frame tokens.

## Color by role

- Each color has a role name, such as surface, text or accent. Never name a color by its hue.
- Colors come in a light set and a dark set.

Seen in: banchi, feed-build, home, tcg-dealer, sillage.

## Font and navigation

- App chrome uses the system font. Brand fonts appear only in content.
- On a phone, navigation uses a bottom tab bar.

Seen in, system font: feed-build, degen, tcg-dealer, home, joyous.
Seen in, bottom tab bar: sillage, degen spec, feed-build, home iOS.

## Not a default

Motion durations and easing are per repo. They are not house defaults.

Frame, byte and pixel-ratio budgets are per repo, as tokens in that repo.
