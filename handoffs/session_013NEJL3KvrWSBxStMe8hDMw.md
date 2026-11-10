# lane: qmax-browser-main-red fix (session_013NEJL3KvrWSBxStMe8hDMw), received 11:04 CST 2026-11-10, kind B

(B) Handoff, resent. The first copy was delivered at 10:01 CST. Lane qmax-browser-main-red (shivinate7/q_max). Nothing is unpushed.
Work: fix main's red browser run 42449067365. ff0fcef2 put two tabs in the Past Rates bar, and that broke two checks.
Done: D-300, "a slice narrows what is below it". It now reaches pills through the Filters layer. PR #1117, head 455c38a6, merged in batch #1120 as a364b23a3.
Open: EPI2B-3, the 1440 bar. Price Date and Clear Filters fold at 1440 with the sidebar shut. That breaks D-649, which says nothing folds at 1440. The design is on branch claude/qmax-pastrates-1440-design, head 88dc480a, with 3 options and item JSON. The pick is option a: More Filters as an icon, plus 8px pill padding. It leaves 14.1px spare in CI.
State: waiting on the owner's page item 428 (qmax-pastrates-bar-1440-pics). Option a departs from D-684 (one select pill).
Left: on the pick, a builder, then a design reviewer at 1440 and 1280. Done when EPI2B-3, BAR-NAMES and verify:specimen are green, and a browser.yml run on main is green.
