# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL34RSeYaFjiSJz4Lk5

## Reply at 2026-11-10T17:27:34Z UTC

IDLE (B)
Lane override-strips-status-block. Goal: a typed `override 12h` takes even when the app puts a status block before it. The real case is a `<system-reminder>` "Linked sessions now" block, a blank line, then the words. Ruling: owner waiting-page item 320, Nov 6 17:44 CST.
State: PR #1382 (a typed override takes after the app's status block) is an open draft. Branch override-strips-status-block, head 0cae19f7a, all pushed, base main dbf54806. Handed to runner 8 (session_013NEJL2vsmyKzJm8jUDt6za) on Nov 6, not merged.
Change: in hooks/override.py, grant() → _override_rest. After the start-of-prompt read, the last non-blank line also grants, once pasted and machine blocks are cut by _strip_blocks. That line grants only for `override`, `override off` or `override <n>[m|h]`, plus one punctuation mark. A reason, extra words or `opus` grant nothing, and the line never reaches the Opus forms.
Tests: hooks/test_local_time.py, 12 new cases. The grant cases fail on main (recorded run) and the no-grant cases guard the round-1 bypass.
Records: ruling 320 is filed in docs/decisions/owner-override.md and GLOSSARY.md, in the same PR.
Review: round 1 failed on a bypass, which was fixed with tests added. Round 2 passed. Local `ci-job checks --lint` passed.
Left: CI on the batch, then the merge by a runner. The owner may rule "strict" to stop the one punctuation mark granting on the last line; I left it as the start form allows.
Notes, not debts:
- grant_opus_ask still reads the raw start of the prompt (as on main).
- A closed agent-message block followed by `override 12h` grants; no route found for Claude to write that.
- An unclosed block swallows the form, which is the safe side.

