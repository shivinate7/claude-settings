# <Role> handoff, <date>

From "<old session title>" at <the limit hit, or the slip>. Checked: main <commit>, record branch
<commit>.

## Standing instructions

<The owner's rulings this role follows, each as one dated line, with its home.>

## State

<What merged, what is in flight, and the work order now, in words. For each list (open items,
waits), the home of the list: a page collection, a roadmap ref, a git ref or a GitHub query. Add only
the items that have no home, each with whom it is handed to. Never copy a list that has a home.>

## Priorities

<One row for each owner ruling that ranks work, copied from that ruling, in this form:>

priority: <slug> | pr: <owner>/<repo>#<N>
priority: <slug> | branch: <name>

<The batch runner runs `merge --priority-rows FILE` on these rows in each wake. A row that names no pr and no branch is a flag, because the check cannot read it. Drop a row when its pull request has merged and the owner has seen it.>

## Deferred for the owner

<The home of the list of deferred steps: a page collection, a roadmap ref, a git ref or a GitHub
query. Add only a deferred step that has no home, and why. Do not ask. Never copy the list.>

## Traps seen

<Each tool or process trap that cost time, and how to avoid it.>

## Pages

Watches stopped at <time>

<Read the time from `~/.claude/bin/now-central --full`, never from memory.>

<The URL of each page this role owns. The old session stopped watching each one at that time,
answered each comment still open at that time, then wrote this file. The successor watches
each one at once, and reads its comments since that time.>

Open items: <items collection URL> or none

<The URL of the page's items collection, where each open item this role owns is listed, or `none`.
Never copy item ids here: a copy goes stale. The successor rewrites `owner` on each open item in
that collection to itself.>

Watch: <page URL>

<One `Watch:` line for each page this role owns. The successor runs `ArtifactComments` action `watch`
on each URL first, before any other act. `Watch: none` is allowed only with `Open items: none`.
`scripts/check_handoff.py` checks both lines.>

## Sessions

<Each running session this role talks to, by title.>
