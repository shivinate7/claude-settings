# c151-measure-tokens

- c151, compaction timing reads message tokens, not total context: step 1 (measure) done. Draft PR #731, head f45da08, record `hook-inputs-carry-token-counts`. Local gates PASS via bin/verdict; Sonnet reviewer clear in round 2 (round 1: 7 accuracy fixes). Builder sonnet, reviewer sonnet.
- Finding for step 2: PreCompact and Stop inputs hold no token counts; statusLine (interactive only) holds `context_window.current_usage` equal to the transcript's last usage. No source splits fixed overhead from messages; messages-only is a proxy (last usage minus first-turn usage). Overhead in this container: 36.6k to 42.1k.
- Step 2 is unstarted, as briefed. It needs the orchestrator's go.
