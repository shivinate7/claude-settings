# <Role> handoff, <date>

From "<old session title>" at <the limit hit, or the slip>. Checked: main <commit>, record branch
<commit>.

## Standing instructions

<The owner's rulings this role follows, each as one dated line, with its home.>

## State

<What merged, what is in flight, each wait handed over and to whom, and the work order now, in words.>

## Deferred for the owner

<Each deferred step, and why. Do not ask.>

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
