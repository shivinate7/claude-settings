# <Role> handoff, <date>

From "<old session title>" at <the limit hit, or the slip>. Checked: main <commit>, record branch
<commit>.

## Standing instructions

<The owner's rulings this role follows, each as one dated line, with its home.>

## State

<What merged, what is in flight, and the work order now, in words. For each list (open items,
waits), the home of the list: a page collection, a roadmap ref, a git ref or a GitHub query. Add only
the items that have no home, each with whom it is handed to. Never copy a list that has a home.>

## Deferred for the owner

<The home of the list of deferred steps: a page collection, a roadmap ref, a git ref or a GitHub
query. Add only a deferred step that has no home, and why. Do not ask. Never copy the list.>

## Traps seen

<Each tool or process trap that cost time, and how to avoid it.>

## Pages

Watches stopped at <time>

<The URL of each page this role owns. The old session stopped watching each one at that time,
answered each comment still open at that time, then wrote this file. The successor watches
each one at once, and reads its comments since that time.>

Open items: <n, ...> or none

<The number of each waiting-page item this role owns that is still open, or `none`. The successor
rewrites `owner` on each one to itself.>

Watch: <page URL>

<One `Watch:` line for each page this role owns. The successor runs `ArtifactComments` action `watch`
on each URL first, before any other act. `Watch: none` is allowed only with `Open items: none`.
`scripts/check_handoff.py` checks both lines.>

## Sessions

<Each running session this role talks to, by title.>
