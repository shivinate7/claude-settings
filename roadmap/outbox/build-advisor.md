# Build advisor outbox

- 2026-10-27 01:40 CDT: merged batch #678 (c109, blind brief template) as 724b7a70; #676 closed as replaced. c109 is done.
- 2026-10-27 01:49 CDT: batch #680 opened with c80+c85 (#679, override reaches every gate) alone; CI running.

- 2026-10-27 02:05 CDT: batch #680 red on gates; lint/test_settings_matcher.py still reads the moved judges from settings.json. Closed; c80+c85 sent back to its lane. Defect: the lane suites did not include test_settings_matcher.

- 2026-10-27 03:27 CDT: #679 went green after one pointer-windows re-run (a harness IOException in install-set.test.ps1:247, a file read while still held open; flaky). Its merge was refused because main moved (#664). Batch #683 now holds #679, #681 (c105) and #682 (c100), built from main d99ba766.

- 2026-10-27 04:15 CDT: batch #683 merged as b031394f: #679 (c80+c85, override reaches every gate), #681 (c105, repo colours), #682 (c100, waiting page final look). c80, c85, c100 and c105 are done. The live waiting pages still need a republish, home-app first. Advisor (7) is finished; the successor reads handoffs/build-2026-10-27c.md.
