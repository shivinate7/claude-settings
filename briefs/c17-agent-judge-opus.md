Opus on your word, claude-settings. Goal: when the owner wants Opus for a spawn, it runs, with no magic words; Claude never picks Opus on its own; no new model calls.

Today: the type: prompt PreToolUse judge on Agent refuses an audit Explore spawn unless model is sonnet, so it refuses Opus too, against decision subagent-model-cap ("any other spawn runs Opus only when the owner names it"). It sees only the tool call, so the owner's word and the override pass can never reach it.

Lane 1, the ceiling moves to the guard. guard.py already runs on Agent and Task calls. When a spawn sets model opus and no standing word covers it (Plan; builder try 3; reviewer round 3 is not standing), the guard answers "ask" under rule subagent-model-cap, the same way it already asks on a settings write. The owner approves or declines in the prompt. An override pass lifts it like any other ask. Test: a spawn with model opus gets an ask; Plan with opus and a spawn with sonnet or haiku pass; red on main, green on the fix.

Lane 2, the judge keeps only the floor. DONE Oct 21 in PR #544 (the Agent judge accepts Opus); do not redo it, check lanes 1 and 3 against main first. In the Agent prompt judge, the Explore clause blocks only an audit or judging brief that sets model haiku or no model. Opus and Sonnet pass the judge; the guard owns the ceiling.

Lane 3, override takes words. In hooks/override_pass.py, a prompt that starts with the word override grants the pass, and the rest of the prompt is the reason, written to guard.log. So "override: use opus for that one review agent" grants a once pass. "override 15m", "override 2h" and "override off" keep their meaning when they are the whole prompt. A prompt that only mentions override later in a sentence grants nothing. Update the decision owner-override-pass in place.

First check: does a hook "ask" show a prompt to the owner in bypass mode? The guard already relies on it for settings writes, so confirm with that existing case. Report the before and after judge text and the tests.
