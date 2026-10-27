# c126 and d9: the waiting page gets its items from the orchestrator, with pictures inline

Builder lane, claude-settings, from main 2ca89254. Two steps, one lane, one commit each, because
both edit skills/waiting-page. Report cap: 25 lines.

## c126: lanes never write the waiting page

The defect: skills/waiting-page/SKILL.md ("from every session") and decision questions-go-to-owner
never say who writes when an orchestrator runs lanes. A banchi orchestrator told its lanes to post
their own items. A subagent lane has no wake after it ends, so it cannot read its answer, and two
writers clash on the design republish ("Add a design", step 4).

The fix: a lane (a background agent or a lane session) puts its question in its report. The
orchestrator writes the item, with itself as `owner`, and routes the answer back to the lane or
its next try. Say it in the skill's opening paragraph and in "Add an item", and in decision
questions-go-to-owner, in place (no history). Red first: the brief check (hooks/agent_brief.py, the
Agent prompt hook) flags a lane brief that tells the lane to write a waiting-page item, if that hook
is the home for brief rules; otherwise say which home you used and why.

## d9: a design pick shows a picture of each option, inline and first

shiv's gripe, Oct 27 09:50 CDT: banchi's item 30 (where a card's price history shows) linked its
three mockups as "a folder on GitHub". A link to a folder, repo or file is never enough.

1. Skill: a question about how something looks carries one design per option ("Add a design"),
   drawn on the first device of the repo's app kind (the Duo folded for iOS, a phone width for
   web). The full mockup stays one tap away.
2. skills/waiting-page/page.html: an item's designs show at the front of its card, before the
   option list, not after it. An item whose options name a design that the item does not carry
   shows a plain warning line in place of the picture, so a missing picture is seen, not hidden.
3. hooks/reply_judge.py: its prompt flags a reply that asks the owner to pick between visual
   options and only links to them.

Red first, in skills/waiting-page/tests/page.test.mjs and hooks/test_reply_judge.py: an item shaped
like banchi's item 30 (three visual options, a GitHub folder link, no designs) shows the warning;
an item with designs shows them before the options. The reply judge case is red on main.

## Done when

The new cases are red on main and green on the branch, `node --test skills/waiting-page/tests/page.test.mjs`
and `python3 hooks/test_reply_judge.py` pass, and `bin/ci-job gates --lint` plus `bin/ste-changed`
pass. Check the page at phone and desktop width in both themes, headless. Give a verdict per
screen. A reviewer (sonnet) reads the diff. Commit trailers as the project requires. Push the
lane branch, send the green, reviewed head to the build advisor, and never merge.
