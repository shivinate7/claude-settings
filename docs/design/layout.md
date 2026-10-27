# Layout and spacing

Read this file before you lay out a screen. It says where space lives and how a layout changes
with its size. The house step and the clamp() token shape are in [`tokens.md`](tokens.md).
Ruling: record ux-house-rules (house UX rules). Step d7 (space with containers, not margins).

## ux-gap-on-parent

The parent spaces its children. A flex or grid container sets `gap`. A child sets no margin to
move away from a sibling.
Outcome: the space between two items has one home. A child that moves to another parent brings
no stray margin, so the gaps stay the same from screen to screen.
Check: pass when no child in a flex or grid list has a margin that spaces it from a sibling.
A margin that offsets one item on purpose, such as `margin-inline-start: auto` to push an item
to the end, is not spacing and passes. Margins in prose and normal flow, outside a flex or grid
container, pass.

```css
/* Do */
.toolbar { display: flex; gap: var(--space-2); }

/* Do not */
.toolbar > * + * { margin-inline-start: 8px; }
```

When one item needs a larger space before it, split the list into two stacks inside an outer
stack with the larger gap. Do not give that item a margin.
Source: mailaudit record spacing-on-4px-grid (claim 14 reads margin, padding and gap). q_max
`src/index.css` `.aq-stack` spaces its children with `margin-top` and a larger margin before
`.aq-section-divided`. That is the pattern this rule replaces. Do not migrate it on sight: move it
when a lane changes that screen.

## ux-layout-primitives

A page is built from a few named layout primitives. Each one owns its gap. A screen composes
them and writes no new layout of its own unless no primitive fits.
Outcome: the same structure looks the same on each screen. Content stays centred in the same
column, and a fix to one primitive reaches every screen.
Check: pass when each page region uses one of the primitives below, or the repo's names for
them, and a new layout states why no primitive fits.

| Primitive | Job |
|---|---|
| Stack | Items one above the other, with one gap. |
| Cluster | Items in a row that wrap, such as chips or buttons. |
| Sidebar | A fixed-width side and a main part that takes the rest. It stacks when the main part gets too narrow. |
| Grid | Equal cards in columns. The column count comes from the space. |
| Center | One column with a maximum width, centred on the page. |

```css
.stack   { display: flex; flex-direction: column; gap: var(--space-3); }

.cluster { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); }

.sidebar { display: flex; flex-wrap: wrap; gap: var(--space-4); }
.sidebar > :first-child { flex: 1 1 16rem; }
.sidebar > :last-child  { flex: 999 1 0; min-inline-size: 60%; }

.grid    { display: grid; gap: var(--space-3);
           grid-template-columns: repeat(auto-fill, minmax(min(16rem, 100%), 1fr)); }

.center  { box-sizing: content-box; max-inline-size: 72rem;
           margin-inline: auto; padding-inline: var(--space-4); }
```

The `margin-inline: auto` on Center centres the column. It does not space siblings, so
ux-gap-on-parent allows it.

Screen breakpoints (media queries) change the page frame only: the nav moves, a side column
shows or hides. Use as few as the frame needs, and name each one as a token, such as
`--bp-wide: 64rem`. A media query cannot use a custom property, so write the value in the
query and keep the token as its name in the docs.

## ux-control-beside-area

A control sits next to the area it changes. Anything between them belongs to every state of that
control.
Outcome: the person sees the result of a press where they look, and nothing that does not change
looks like part of the result.
Check: pass when no element sits between a control (tabs, a filter, a toggle) and the area it
changes on screen. An element between them passes when it stays the same in every state of the
control. A summary or a rail that sits between the tabs and the tab panel fails.
Source: claude-settings `roadmap/page` on the roadmap branch, where a summary and a phase rail sat
between the tabs and the tab panel.

## ux-component-reads-its-box

A shared component changes its shape from its own width, with a container query. It never reads
the screen width. Add a container breakpoint only where the component changes shape. Each one
is one more state to screenshot.
Outcome: one component serves a sidebar and a main column with no copy (o11, one home per shared
thing). The screenshot list stays short.
Check: pass when no shared component has a media query on width, and each container breakpoint
changes the component's shape (rows to columns, a label shows or hides). A breakpoint that only
nudges a size fails; use a clamp() token instead.

```css
.card-host { container-type: inline-size; }

.card { display: grid; gap: var(--space-2); }

@container (min-width: 28rem) {
  .card { grid-template-columns: 6rem 1fr; }
}
```

The parent sets `container-type`, so the component itself stays free of it. Two side effects:
a query container is the containing block for its `position: fixed` children, so a sheet or a
toast must render outside it. `container-type: size` also stops the box from taking its height
from its content. Use `inline-size`.
Source: banchi `app/src/Inventory.css` (the `copies` query container); q_max
`src/components/screens/level.css` (`.level-grid`).

## ux-variant-extends-home

A screen that needs a shared component to look or act a little different extends the component.
It never copies it. The component keeps one home. The variant is a modifier class or a custom
property in CSS, and a parameter or a style in Swift.
Outcome: a fix to the shared component reaches every variant, so two screens never drift (o11,
one home per shared thing; rule building-one-home-per-capability).
Check: pass when no component file holds a copy of another component with small edits. A copy
passes only when its commit message states why the home cannot take the variant.

```css
/* The home: one card, with a custom property for the one value a variant changes. */
.card { padding: var(--card-pad, var(--space-3)); border-radius: var(--radius-2); }

/* A variant: a modifier class on the same component. */
.card--dense { --card-pad: var(--space-2); }
```

```swift
// The home: one view, with a parameter for the one thing a variant changes.
struct StatusRow: View {
    var title: String
    var dense = false
    var body: some View {
        HStack(spacing: dense ? Space.s1 : Space.s2) { Text(title) }
    }
}

// A variant: the same view with an argument, or a ButtonStyle for a look that many views share.
StatusRow(title: "Kitchen", dense: true)
```

`lint/find_copies.py` lists the copies a repo holds of claude-settings files and skills.

## ux-fluid-tokens

Space and type that grow with the box use clamp() tokens. A component reads the token. It
writes no raw clamp() of its own.
Outcome: fluid sizes have one home, so two screens never drift to two curves for the same step.
Check: pass when each clamp() in a component file is a token read, and each token follows the
shape in `tokens.md`.
Source: banchi `app/src/Home.css` and q_max `src/index.css` (`--f2-side-w`) show raw clamp()
values that this rule moves into tokens.

## ux-swift-same-intent

A Swift screen follows the same four rules with its own tools.

| Web | SwiftUI |
|---|---|
| `gap` on the parent | `VStack(spacing:)`, `HStack(spacing:)`, `Grid(horizontalSpacing:verticalSpacing:)`. No `.padding()` on a child to space it from a sibling. |
| Layout primitives | `VStack`, `HStack`, `LazyVGrid` with `.adaptive(minimum:)`, `NavigationSplitView` for a sidebar. |
| Container query | `ViewThatFits` picks the first layout that fits the space it gets. |
| Screen breakpoint | `horizontalSizeClass` changes the page frame only. |
| clamp() token | A spacing constant from the token file, scaled with `@ScaledMetric`. |

```swift
ViewThatFits(in: .horizontal) {
    HStack(spacing: Space.s2) { label; value }
    VStack(alignment: .leading, spacing: Space.s1) { label; value }
}
```

Outcome: the same as the web rules. One view serves a phone and an iPad column.
Check: pass when each stack sets its own spacing, and no child pads itself away from a sibling.
Source: home-app `ios/HomeApp/Views.swift` (`ViewThatFits` that stacks at accessibility sizes).
