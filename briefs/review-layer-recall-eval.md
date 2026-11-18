Lane brief: measure what each review layer catches (reviewer, refuter, fix verifier, design reviewer).
Governing: decision pr-review-record, roles-review-cap-three. Harm: four layers stack with no measure of what each catches.
1. test-author first (own worktree): write the eval fixture in the repo's test folder: incident list from reverts and red-main reverts (read from git and REST), an answer key per incident, and merged controls (PRs that merged clean). Show it red on main.
2. builder: make the scorer run and report per-layer recall and cost, with n.
3. reviewer (model per agent-model-cap).
Proof command: `~/.claude/bin/verdict <scorer command>`, plus the report file. Report cap: 25 lines. Prior work: none found by grep of roadmap steps.
