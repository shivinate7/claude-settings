# A scope phrase before a bare cite reads as the cite's name

**What.** A scope phrase in front of a bare item cite reads as the item's name, so the cite passes. `On the waiting page, item 46 is open.`, `Open the waiting page, item 46.` and `In triage, item 46 is open.` each pass, and each should refuse on 46. The same flaw sits in the record-id reader: `On the waiting page, D12 is open.` passes, and should refuse on D12.

**Where.** `lint/report_guard.py`: `GLOSS_LEAD_RE` (about :653), read by `bare_item_cite` through `_item_named` (about :719-731). The lead reader takes the two words before a comma as a name, so `waiting page,` counts. On the default branch the same regex is read by `bare_cite` (about :659).

**Decision.** None; rule `speak-cite-id-plus-gloss` (an id carries a short name).

**Retire.** The lead reader stops reading a scope phrase as a name. `lint/test_report_guard.py` gets the three item probes above and the D12 probe, each expecting a refusal on its id, and it passes.
