# The scorecard folder is not a layout kind

- **What.** `scorecard` writes `docs/health/compliance.md`, but `lint/layout.json` has no kind for `docs/health`. So in a rolled-out repo, the layout probe reports `docs/health/` as neither a layout kind nor an extra, and Layout scores out because of the scorecard itself.
- **Where.** `lint/layout.json`, `probe_layout` and `scorecard` in `lint/compliance_probes.py`.
- **Decision.** `one-layout-every-repo` (one layout for every repo).
- **Retire.** The layout names a kind for the scorecard file, and `scorecard` reads its path from that kind. The layout probe passes on a repo that holds the scorecard.
