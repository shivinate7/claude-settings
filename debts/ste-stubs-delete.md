# Two exit-0 stub scripts stay for old installs

- **What.** `ste_gate.py` and `md_sweep.py` do nothing. They exist only because an installed `settings.json` copy may still call them, and a missing gate script fails closed.
- **Where.** `lint/ste_gate.py` and `lint/md_sweep.py`.
- **Decision.** `ste-gate-fixes-not-nags` (no STE hook runs on a write; the stubs are its transition bandaid).
- **Retire.** Delete both files once every install has refreshed its `settings.json`. `lint/test_settings_matcher.py` stub cases go with them.
