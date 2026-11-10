# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJKzQsAzQkvsohtkLuJP

## Reply at 2026-11-10T17:23:39Z UTC

IDLE (B). Handoff for lane judge-timeout-retries-once (step judge-timeout-retries-once, owner asks ask-mw6pwif5wv and page item 379).
Goal: the past-ruling check retries once on a model timeout instead of refusing, logs each timeout, and the rule audit lists the related ids.
State: six stacked draft PRs, all reviewed, all pushed and released to runner 8 (session_013NEJL2vsmyKzJm8jUDt6za). None merged as of 09:48 CST. Merge order:
1. #1418, head 66a6450a7: call_judge question path retries once (35 s + 25 s, 70 s hook).
2. #1422, head bf59f48fb: report_guard relay check uses the same retry (judge_question, one home).
3. #1431, head ab5b48cbe: each past-ruling timeout writes a guard.log line, rule judge-timeout, with the prompt size.
4. #1446, head 2428f36c5: rule_audit lists ids written through module constants (step rule-audit-constant-ids).
5. #1501, head d0804de73: LOGGED_RULES declarations list spawn-judge, question-judge, past-ruling, reply-judge and JUDGED_RULES (step judge-ids-via-constants).
6. #1766, head c35385ac3: report_guard Stop hook 35 → 50 s, past-ruling 25 s + 15 s (owner typed "a", 2026-11-07 21:33 CST; page item 379, asked triage to close it with #1766 as its home).
Left: merge in order once CI is green; each PR holds the commits of the ones before it. Notes only, in docs/debts/notes.md: the budgets and timeout rate are unmeasured, no mutant covers the retry condition, and the rule_audit edge forms.
Files: hooks/call_judge.py, lint/report_guard.py, lint/rule_audit.py, hooks/reply_judge.py, settings.json, docs/decisions/question-reviewer-agent-hook.md, docs/decisions/question-form.md, and their tests.

