# UX house rules

The owner's UX rules, taken from the owner's repos. Each repo with screens follows them.
A builder reads `principles.md` before it writes UI. A reviewer marks `checklist.md` for each changed screen. `a11y.md` holds the accessibility floor and its CI check. [`layout.md`](layout.md) holds the spacing and layout rules. [`tokens.md`](tokens.md) holds the house design values: spacing and radius, fluid tokens, color by role, font and phone navigation. A repo may override them. [`repo-colours.json`](repo-colours.json) holds each repo's one colour; read it with `python3 lint/repo_colour.py <repo>`, which draws a colour for a repo that has none.
Vercel web-interface-guidelines keeps web mechanics, impeccable keeps critique and polish, and frontend-design keeps visual direction.
Ruling: record ux-house-rules (house UX rules). Skill design-review, `agents/builder.md` and `agents/reviewer.md` name `principles.md` and `checklist.md` from this folder.
