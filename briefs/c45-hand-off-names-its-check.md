# c45, a step handed to you names the check that proved the session can't do it

Repo: claude-settings. Checked at 149f4bc (main, Oct 25 19:16 CDT).

Incident, Oct 25 (ios-adblock): the session's report listed "delete the two test App IDs on developer.apple.com" under Input Needed. It never checked its tools. The App Store Connect key that created the IDs was on the Mac and could delete them. When asked, it then said the step "needs your login", also unchecked. The owner had to point it out twice. Rule output-never-hand-off-doable-step (do a step yourself before you hand it to me) already says to search first and name the reason, but nothing checks the doability half: the reply judge (hooks/reply_judge.py) only checks the code-block form, and only on 1 Stop in 5.

Task, two parts, one lane:

1. Amend output-never-hand-off-doable-step in output-styles/shiv-stylisms.md, in place, no new rule. Add:
   - Each step handed to the owner names its reason (decision, login, or an act the safety rules keep for the owner) and the check that shows the session cannot do it, in a few words, such as "no API key for Apple in env or keychain". With no check run, the step is not the owner's yet: run the check first.
   - Access that made a thing can remove it. A thing the session made, it cleans up itself.
   - "Can't" and "shouldn't" differ. A step the session can do but that cannot be undone is not handed over as steps: the session asks one yes or no on the exact act, and does it on the yes.
   - A plan that makes throwaway things (test IDs, test branches, test data) names their cleanup in the same ask, so the owner's yes covers both (outcomes-word-covers-named-act, my word covers the act it names).
2. Extend hooks/reply_judge.py, the one home, no new hook:
   - Add to INSTRUCTIONS: each item under Input Needed names its reason and the check that showed the session cannot do it; flag an item that names neither.
   - Judge every Stop whose reply carries an "Input Needed" label, besides the 1-in-5 sample. Detect the label in code (a string match on the label), not by the model. This changes the owner ruling of 2026-10-13 in decision reply-judge-samples-never-blocks; rewrite that entry in place with the new ruling and its cost: one extra model call per report that carries Input Needed, no new file, no new process, no timer.
   - Still never blocks, still fails open.

3. Each finding the judge passes on also writes one line to guard.log, the existing log (rule id, session, Stop number). No new file. Named reader: the advisor at each cull, who counts flags against owner-confirmed misses and false alarms, to rule whether the judge stays, widens or goes. Today it keeps no record, so its value is unmeasured.

Record: the incident above is the named incident (building-guard-needs-incident). Update lint/rule_mechanisms.json reason for output-never-hand-off-doable-step to say the judge now also checks reason and check, on every Input Needed report.

Proof (test-author first, red on main):
- A reply with "Input Needed: delete the two test App IDs on developer.apple.com" and no reason is judged even when it is not a 1-in-5 Stop (counter test, no model needed: stub invoke_model and assert it was called).
- A reply with no Input Needed and a non-sample Stop is not judged.
- The prompt text carries the new clause (string check).
- A model run on the two sample replies (no reason vs. "needs your login: no App Store Connect key in env or keychain") flags the first and passes the second; record the run, it is not a CI test.

Report cap: 15 lines.
