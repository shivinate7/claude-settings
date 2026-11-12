Owner ruling R37 (2026-11-11, restart plan): a fixed number that refuses without an owner ruling is retired, and a check keeps a ruled limit or measures instead. Time limits belong to plan R3's lane; the sim-lease numbers wait on the owner.

# Fixed-number census (Explore sonnet, 2026-11-12 11:20 CST). 63 limits that refuse, fail or block.
Ruling column: A = owner's own words name the value (7, stay, cite beside). B = a decision names it, no owner words (37, retire or measure). C = no ruling (19, retire or measure).
Full row table lived in the agent's report; ids below match it (line refs as of main 2deb827ad).

## A (stay, cite)
L2 check_record_slugs MAX 32 (rule git-slug-then-claim-number); H13 guard.py:3566 round 2/3 model rules; M1 merge NET_RETRIES 3; M3 LOCK_MAX_HOLD 6 h; M8 REVIEW_LAST_ROUND 3; B1/B2 bin/sim-lease 100/60/60 (conflicts with machine-load-brake: owner call needed).

## B/C by area (retire or measure)
- lint: L1 STE001 30 words (R37, PR 1). L3 WINDOW_DAYS 14. L4 TIMEOUT 900. L5 TIMEOUT 1800. L6 RULE_FLOOR 98. L7 UNMECHANIZED_EXPECTED 58 / JUDGMENT_EXPECTED 25 (equality). L8 REASON_MIN_WORDS 8. L9 compliance_probes SHARED_RUN 5 / SHARED_MIN 12 / RESTATES_SHARE 0.5.
- hooks counts: H3 SIM_BOOT_CAP 2 (record only). H4 SLEEP_LIMIT 25 s. H5 STAMP 1/60 min. H6 MERGE_NEST_DEPTH 4. H7 ENV_MAX_DEPTH 64. H8 rm_var 64 combos. H9 BASED_MAX 3 (record says one to three). H10 ONCE_WINDOW 10 min. H11 DEFAULT_ASK_LENGTH 2 h (R12 owner: arbitrary). H12 EXPIRY_MAX_AHEAD 24 h. H17 BASE_COPY caps 200/20. H18 REFUSE_COUNT.
- hooks load: H1/H2 load brake memory 85/95 %, disk (record machine-load-brake, "placeholder for the owner to tune").
- time limits (plan R3: stop on silence, no stored total-time number): H14 40 s. H15 25 s. H16 5 s. H19 3600. M2 RATE_LADDER. M4 lock expiry. M5 5 min. M6 3600. M7 500 pages. M9 50 commits. M10 deadlineMinutes 80/45. B3-B9 sim-lease wait 300, sim-test LOCK_WAIT 300, crash WINDOW 3 in 30 s, --for 1-900, shoot 15000 ms, ios-ship step timeouts, wait-pid 540. O1 mutate_sweep 3600. C1-C15 CI job/step caps (75/60/30/15/10/5/3 min), playwright apt 300 s, readme_links 2 tries 20 s.
- contradictions: merge.py:1369 warns at 0.7 vs ci-job-caps 80 % (warn-only); bin/sim-lease load average vs machine-load-brake "Never the load average".
- W1 check_claude_md_size MAX 200 warns only (plan R35 owns it).
- Not covered: mods/, githooks/pre-commit, tools/, testing/, skills/ scripts.
