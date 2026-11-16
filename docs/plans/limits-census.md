Owner ruling R37 (2026-11-11, restart plan), narrowed by owner page item 595 (owner save 2026-11-12 12:54 CST, record 618b84ece, relayed by triage). R37 targets limits that cut fine work off. Those retire. The 14-day hook-stub window stays. A number that an owner ruling names stays, with the ruling cited by decision id beside it. Do not raise every number to the owner. Time limits belong to plan R3's lane. The sim-lease load numbers wait on an owner page item. Hook-count rows H10 and H11 belong to lane owner-override-one-route.

Refuter: refuter opus, 2026-11-15, AGREE WITH CHANGES

The true verdict is agree with changes. The checker reads the role word only, so the verdict words are free. The refuter's changes, and what the census now does for each:
1. "Is a stated bound" is no test, and item 595 does not say it. The first paragraph read it that way. It now holds item 595's own terms. H4, H6, H7 and H8 are re-judged on the cuts-fine-work-off test in the section "Outcome per row group".
2. L4 and L5 cite "owner 12:11 CST Nov 10". The cite is true: decision ci-job-caps holds the owner's words of 2026-11-10 12:11 CST (stopgap: raise time limits generously, retire time-pinned tests). Both are time limits and belong to plan R3's lane.
3. H9 was kept on "the owner's own output style says one to three". That reading is wrong. The style line (output-styles/shiv-stylisms.md:22) is "1 to 3 sentences" for a simple answer, a different count. The section "Outcome per row group" states what is read and what is unmeasured.
4. Rows with no outcome now have one: L9, H3, H1/H2 and the two contradictions.
5. The kept numbers with owner words now have a decision id beside them: L2, M1, M3, M8, H13.
6. The "Not covered" areas and the STE rename are listed as open follow-ups with their status.

# Fixed-number census (Explore sonnet, 2026-11-12 11:20 CST). 63 limits that refuse, fail or block.
Ruling column: A = owner's own words name the value (7, stay, cite beside). B = a decision names it, no owner words (37, retire or measure). C = no ruling (19, retire or measure).
Full row table lived in the agent's report; ids below match it (line refs as of main 2deb827ad).

## A (stay, cite)
Each number below stays. The decision that holds the owner's words is beside it.
- L2 check_record_slugs MAX 32: rule git-slug-then-claim-number (root CLAUDE.md, owner's rule: "a slug of 32 characters or fewer"). No decision record holds the 32 itself (decision waiting-data-in-repo repeats it for registry ids). The UI-crop reason is in the check's docstring.
- H13 guard.py round 2 and round 3 model rules: decision agent-model-cap (the round rows: sonnet from round 2, opus for the builder's third try, "the owner's standing grant") and rule roles-third-round-steps-up. The decision gives no date for the third-try grant: unmeasured.
- M1 merge NET_RETRIES 3: decision standing-merge-grant (owner ruling 2026-10-13, kept by owner ruling 2026-10-16).
- M3 LOCK_MAX_HOLD 6 h: decision standing-merge-grant (owner ruling 2026-10-17) and decision merge-lock.
- M8 REVIEW_LAST_ROUND 3: rule roles-review-cap-three; decision hold-unsafe-after-round-3 holds the round rules and decision pr-review-record holds the record form.
- B1/B2 bin/sim-lease 100/60/60: owner rulings of 2026-11-02 (degen shared-sim-lease), cited by decision sim-lease-tool. They conflict with decision machine-load-brake. See contradiction 2 below.

## B/C by area (retire or measure)
- lint: L1 STE001 30 words (R37, PR 1). L3 WINDOW_DAYS 14 (kept: owner item 595 (2026-11-12 12:54 CST), the 14-day window stays). L4 TIMEOUT 900. L5 TIMEOUT 1800. L6 RULE_FLOOR 98 (retired: R37, item 595 narrowing). L7 UNMECHANIZED_EXPECTED 61 / JUDGMENT_EXPECTED 27 equality (retired: R37, item 595 narrowing; the pins stood at 58 and 25 until PR 2814 moved them to 62 and 26, then marking counts-from-rest as judgment moved them to 61 and 27; the move-off-mechanism check replaces them). L8 REASON_MIN_WORDS 8 (retired: R37, item 595 narrowing). L9 compliance_probes SHARED_RUN 5 / SHARED_MIN 12 / RESTATES_SHARE 0.5.
- hooks counts: H3 SIM_BOOT_CAP 2 (record only). H4 SLEEP_LIMIT 25 s. H5 STAMP 1/60 min. H6 MERGE_NEST_DEPTH 4. H7 ENV_MAX_DEPTH 64. H8 rm_var 64 combos. H9 BASED_MAX 3 (record says one to three). H10 ONCE_WINDOW 10 min. H11 DEFAULT_ASK_LENGTH 2 h (R12 owner: arbitrary). H12 EXPIRY_MAX_AHEAD 24 h. H17 BASE_COPY caps 200/20. H18 REFUSE_COUNT.
- hooks load: H1/H2 load brake memory 85/95 %, disk (record machine-load-brake, "placeholder for the owner to tune").
- time limits (plan R3: stop on silence, no stored total-time number): H14 40 s. H15 25 s. H16 5 s. H19 3600. M2 RATE_LADDER. M4 lock expiry. M5 5 min. M6 3600. M7 500 pages. M9 50 commits. M10 deadlineMinutes 80/45. B3-B9 sim-lease wait 300, sim-test LOCK_WAIT 300, crash WINDOW 3 in 30 s, --for 1-900, shoot 15000 ms, ios-ship step timeouts, wait-pid 540. O1 mutate_sweep 3600. C1-C15 CI job/step caps (75/60/30/15/10/5/3 min), playwright apt 300 s, readme_links 2 tries 20 s.
- contradictions: merge/merge.py:1637 warns at 0.7 compared with ci-job-caps 80 % (warn-only); bin/sim-lease load average compared with machine-load-brake "Never the load average".
- W1 check_claude_md_size MAX 200 warns only (plan R35 owns it).
- Not covered: mods/, githooks/pre-commit, tools/, testing/, skills/ scripts.

## Outcome of PR 3 plan
- To retire: H17 path cap, in branch h17-path-cap-census, not yet merged.
- Retired: L6 RULE_FLOOR 98, L7 the 61/27 equality pins (58 and 25 before PR 2814, 62 and 26 after it), L8 REASON_MIN_WORDS 8 (PR lint-counts-census). The rule audit now prints the counts and names each anchor removed since origin/main. The move check covers three acts against the merge base with origin/main: a row off guard, check or ci, a row relabelled between unmechanized and judgment, and an anchor renamed in place off its mechanism. Each fails when its reason is unchanged (spacing aside), and a rename off a mechanism always fails. It does not see a pure delete of an anchor with its row; the removed-anchor line prints that.
- To join the ask: H12 deadline (item 602 pick a), in branch h12-deadline-ask-census, not yet merged.
- To state the reason beside the number: H4, H6, H7, H8, in branch hook-bounds-reasons-census, not yet merged. The reason beside the number stays useful. The keep or retire call now rests on the cuts-fine-work-off test (see "Outcome per row group"), not on "is a stated bound".
- Kept unchanged: H5 (refuter: a stricter replacement is not a measurement); H9 (reason withdrawn: the output style says "1 to 3 sentences", a different count; see "Outcome per row group"); H18 (a presence rule).

## Outcome per row group
Test: does the number cut fine work off? Read from the code on 2026-11-15. The refusal counts are unmeasured: guard.log on this machine holds about one hour (66 lines), so it cannot show how often a rule refused.

Re-judged hook bounds (refuter change 1):
- H4 SLEEP_LIMIT 25 s (hooks/guard_stream.py). Kept. It cuts no work off: waiter_verdict lets a background sleep of any length run when a command follows it, and Monitor is allowed (decision agents-wait-with-monitor). A foreground sleep over 25 s costs one turn. The number is a time number, so plan R3's lane may still change it.
- H6 MERGE_NEST_DEPTH 4 (hooks/guard_merge.py). Kept. It cuts no work off: four nested `bash -c` layers is no honest command. It refuses past depth 4 only with a merge flag inside (_unproved_confirm). _self_role_hit refuses past depth 4 with no content check.
- H7 ENV_MAX_DEPTH 64 (hooks/guard_env.py). Kept. It cuts no work off: no honest command nests 64 substitutions. The `$(` scan is one pass with an own stack, so the cap adds no cost bound there. It bounds the recursive backtick read and makes an unreadable nest fail closed.
- H8 rm_var 64 combos (hooks/guard_rm_var.py, _rm_word_safe). Follow-up lane rm-var-combo-cap. The size is the product of the value counts, so one for loop over 65 written-out words is refused, and that cuts fine work off. The cost bound is needed for a product of several names only. A scratch-name read at hooks/guard.py:1814 also cuts picks at 64. It refuses nothing, so it cuts no work off. Decision rm-on-a-variable-needs-a-guard does not name the 64. Not built here.

Rows with no outcome before (refuter changes 3 and 4):
- H9 BASED_MAX 3 (hooks/question_form.py:83). Kept for now, source unproven. Read: decision question-form says "one to three Based on lines" under an owner steer of 2026-10-30 12:50 CDT, and that steer concerns one form and one guard, not the count. The phrase first appears in commit 43c221d76b (2026-10-22), in the rubric list under the heading "Owner rulings, 2026-10-22 10:18 CDT". The commit holds no owner words for the count. Unmeasured: whether the owner named three, and how often a fourth premise was refused. A merged premise fixes the refusal, so it cuts little work off. One note line records it.
- L4 TIMEOUT 900 and L5 TIMEOUT 1800 (lint/check_python_floor.py:70, lint/check_debt_retire.py:38). Kept as an interim stopgap with the owner's words (decision ci-job-caps, 2026-11-10 12:11 CST). They end with step time-pinned-tests-go. Time limits: plan R3's lane owns them.
- L9 compliance_probes SHARED_RUN 5, SHARED_MIN 12, RESTATES_SHARE 0.5 (lint/compliance_probes.py:658-660). Kept. They set how much copying counts as a copy of a record (decision child-cites-not-copies). They bound no work. A false alarm is fixed by citing the record. The false-alarm rate and the owner's words for the three numbers are unmeasured. One note line records it.
- H3 SIM_BOOT_CAP 2 (hooks/guard.py:5454). Kept. It matches the owner's two-Duos ruling (decision sim-lease-tool, rulings of 2026-11-02) and guards memory on the Mac. The refusal names the booted devices, so the work goes on with one of them. Decision sweep-shuts-down-idle-simulators, ruling 3, holds the number.
- H1/H2 load brake 85 % / 95 % memory, disk (decision machine-load-brake). Kept. It guards a real harm: a full disk crashed agents (owner incident, 2026-10-26). A busy machine only delays new lanes, and a full one stops running agents by design. The record calls the memory level "a placeholder for the owner to tune". Unmeasured: the right level on the Mac. One note line records it.
- Contradiction 1: merge/merge.py warns at 0.7 of a job cap (line ~1637), decision ci-job-caps targets 80 %. Kept. It only warns and cuts no work off. The two numbers should share one home. Follow-up lane merge-warn-cap-share, with plan R3's lane. One note line records it.
- Contradiction 2: bin/sim-lease reads the load average (100/60/60, owner rulings of 2026-11-02), decision machine-load-brake says "Never the load average". Two owner rulings conflict, so no builder picks. It waits on the owner page item named in the first paragraph. The grant waits at most 300 s, then exits 1. One note line records it.

## Open follow-ups
- Not covered by the census, status open (nothing read yet): mods/, githooks/pre-commit, tools/, testing/, and the skill scripts under skills/. Next step: a read-only census of each, with the same test.
- STE rename (R37 item 2: lint/ste_lint.py, actions/ste-lint, the STE0nn codes, rule anchor output-write-in-ste): open. Step ste-lint-rename runs last, in its own PR. It is not built here.
- Follow-up lanes named above, none started: rm-var-combo-cap (H8), merge-warn-cap-share (contradiction 1).
- Time limits go to plan R3's lane: L4, L5, H14 to H16, H19, M2, M4 to M7, M9, M10, B3 to B9, O1, C1 to C15.
