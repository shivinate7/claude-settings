# c71: one waiting page for every session, the rule and the skill

Cloud build thread brief. Build advisor (4), Oct 26, against claude-settings main 7ce2d89 (or
newer). Never rebase onto main after review. claude-settings only. Push roadmap edits to the
branch only; only Triage the roadmap (3) republishes.

## Inputs

- Design: /mnt/project-files/plans/c71-waiting-page.md (database schema, session protocol, rulings)
  and the page source c71-waiting-page.html beside it. The pilot page runs by hand from the thread
  "Answer all waiting decisions in one place" (cmsg_01DoF7thf3iq2Srr1UsfXgh2ADTZhQexksM43HTmuCPZMa).
- Measured: a page save wakes no local session; sessions read answers at their own turns.
- Measurement in flight, separate (the local liaison): can a local session write to the page's
  database. It decides one page or two for claude-settings; design so either works.

## Rulings (shiv, Oct 26, saved on the page)

- 1a: one shared page per project or repo, for everything waiting on him, from every session.
- 2a: a save on a page only shiv can write counts as his word. It needs a rule.
- 3a: keep the terminal question box, with a link to the page.

## Task

1. Rule: extend questions-go-to-owner (one home; no second rule) so each question also goes on the
   repo's waiting page, and a save by shiv on that page counts as his word for the item it answers
   (2a), with the terminal box kept and linking the page (3a). Fewest words.
2. Skill skills/waiting-page/: the add, read, route and close protocol from the design, the page
   source as a template, and how a repo makes its page (publish with the db capability).
3. Page URL per repo: one key in the layout file o2 landed (lint/layout.json or the repo's extras
   file), read through layout.py. No URL is a stated "unknown", never a guess.
4. Port: the skill reaches every repo from claude-settings; a repo's page is made at its roll-out.

## Failure classes and proof

- Test-author first, red on main: the URL reader returns the key when set and "unknown" when
  missing (false-alarm case: a repo with no page is not an error); rule_audit's pinned counts
  move only by any new anchor, and say which bucket.
- Run every gates.yml step locally before sending.
- A fresh Sonnet reviewer reads the diff (it changes a rule).

## Report

Cap 20 lines: Done, Deviations, Next, and "Port to other repos: yes or no, and why". Send the green,
reviewed head and branch to "Advise the claude-settings build (4)"
(cmsg_01DoF7thf3iq2Srr1UsfXgh2EyHwiKacoTT56k4JHuc2RT). Keep the PR a draft.
