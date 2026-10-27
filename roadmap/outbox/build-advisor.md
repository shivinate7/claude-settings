# Build advisor outbox

- 2026-10-27 01:40 CDT: merged batch #678 (c109, blind brief template) as 724b7a70; #676 closed as replaced. c109 is done.
- 2026-10-27 01:49 CDT: batch #680 opened with c80+c85 (#679, override reaches every gate) alone; CI running.

- 2026-10-27 02:05 CDT: batch #680 red on gates; lint/test_settings_matcher.py still reads the moved judges from settings.json. Closed; c80+c85 sent back to its lane. Defect: the lane suites did not include test_settings_matcher.
