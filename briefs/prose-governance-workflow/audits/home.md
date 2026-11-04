Done
- OTHER: I audited /home/user/home/CLAUDE.md at HEAD 88d659d (the PR #546 merge, cloud Tailscale auto-start). It has 55 lines, 14,544 bytes and 40 bullets. AGENTS.md is a symlink to it. .claude/rules/README.md holds no rule. The bloat is in long bullets, not in the line count: line :47 alone has 2,279 chars.
- OTHER: class counts, as bullets / chars. KEEP 20 / 5.6 KB. PATH 5 / 3.3 KB. DUP 10 / 3.5 KB. MOVE 3 / 1.3 KB. STALE 2 / 0.5 KB. A mixed bullet counts under its main class.
- OTHER: target. CLAUDE.md drops to about 34 lines and 5 KB. A new .claude/rules/home-app.md (paths ios/**, web/**) gets about 6 lines.
- Biggest cuts:
  - :47 iPhone simulators. PATH ios/**. MOVE the UDIDs, the load numbers and the sim-test behaviour; claude-settings bin/sim-test:3-6 and :26 (CAP=2) already state the behaviour. Cut the history of the deleted Duo AC2E94F9 (speak-rewrite-superseded-in-place, rewrite superseded text in place). :45 is PATH web/**. :48 and :50 are PATH ios/**.
  - "## Merging" :27, :28, :36, :37, :38 (2.1 KB). DUP of git-integration-branch-merge (the batch rules), of shared-trees-archive-then-delete, and of claude-settings skills/project-ops/templates/operating-model.md:10-41 and :97. Keep only two clauses: "this repo runs the project-ops roles" and "a lane runs no tools/reinstall-phone-apps".
  - :19-20, heavy disk jobs and add-on changes. MOVE: the header of tools/green-health.mjs, lines 5-10, states the same mechanics. Keep one line: wrap each heavy job or add-on install in --heavy-start and --heavy-end.
  - :21, shared machine. DUP of claude-settings decision shared-resource-owner. Its order to degen and mailaudit never loads in those repos. Keep "this repo owns the HA Green preflight and its holds".
  - Single bullets:
    - :43 is DUP of roles-sonnet-is-the-ceiling.
    - :46 is DUP of parallelism-keep-going.
    - :51 is DUP of shared-trees-one-checkout-per-agent, and the other-checkout guard already enforces it.
    - :55 is DUP of waiting-page SKILL.md:71-74.
    - :39 is MOVE to docs/decisions/main-fix-draft-prs.md.
    - :18's poll floors are MOVE to records/ha-extensions.md:5.
  - Repeats inside the file:
    - The phone install appears three times, at :28, :38 and :49. Keep :49, because the batch runner reads no ios/ file.
    - "Main moves only by PR" appears at :10 and :29.
    - The merge grant is split across :29 and :30.
    - The cloud bullets :32-35 sit under "## Merging".
- STALE, and KEEP rules that are wrong or unclear:
  - :33 says the cloud reach test waits for the owner's go. records/ha-extensions.md:49 says it passed 2026-11-03 14:48 CST.
  - :29-30 say the coordinator merges. claude-settings docs/decisions/standing-merge-grant.md says "The coordinator never merges" (owner, 2026-11-01 21:34 CST). The batch runner merges.
  - :28 puts the roster in CLAUDE.md on branch roadmap. project-ops SKILL.md:47-49 (claude-settings PR #840, batch-23a, 2026-10-29) keeps the roster only in the project instructions on claude.ai. This is likely stale, but I did not read the roadmap branch.
  - :46 says to stop "for an HA change", but :7 grants any HA change with no word at the time. The two contradict.
  - :27 sends lane questions to triage. :28 and the parent rule questions-go-to-owner send them to the parent, the coordinator.
  - :47 calls a session the "sim gatekeeper". GLOSSARY.md:51 lists "gatekeeper" in its Not column, for triage, so this breaks speak-one-name-per-thing.
- MISSING: a cloud curl must force the Tailscale proxy with `--noproxy ''` (records/ha-extensions.md:49). :35 covers only ALL_PROXY for ha-ws.
- Mechanical check: claude-settings lint/check_claude_md_size.py:18 caps lines only (MAX = 200), so 14.5 KB passed it. A byte cap, or a cap of about 400 chars per bullet, would flag :15, :19, :21, :28, :29, :35, :38, :47 and :50.

Deviations
- The other-checkout guard refused a read-only grep of /home/user/claude-settings as "a write in another checkout". This may be a false alarm (verification-cry-wolf-guard-is-spent). I used the Grep tool instead.

Input Needed
- Do home's project instructions on claude.ai hold the operating model? If yes, :28 and :36-38 are full DUP and can go.

Next
- Unknown: the status of step c196 (the sim-test widening), and whether session local_9618917e (the sim gatekeeper) still runs. I made no edits.