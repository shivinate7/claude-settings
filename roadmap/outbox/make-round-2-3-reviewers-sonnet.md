# Make round 2 and 3 reviewers run Sonnet (c142, a reviewer at round 2 or 3 runs Sonnet)

Paused Oct 27 13:33 CDT on shiv's usage-limit pause. No code written, no branch pushed.

Found so far (claude-settings main 6a3e842): agents/reviewer.md pins `model: haiku`. The guard rule
agent-model-floor (hooks/guard.py, refuse near line 2599) refuses only a haiku model field.
Next: read the model-per-role table (decision agent-model-cap), pick fix (a) guard ask or (b)
Sonnet pin, write the red test in hooks/test_guard.py, then one fresh Sonnet reviewer.
