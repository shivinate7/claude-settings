# A fixture named settings.json asks for the cap

- **What.** A heredoc that writes a fixture named like a settings file (`fixtures/settings.json`) with the cap key asks, though no real settings file changes. `is_settings_file` tests the basename only. Found in review of lane cap-ask-data.
- **Where.** `is_settings_file` in `hooks/guard.py` (near line 665), used by the model-cap rule.
- **Decision.** `subagent-model-cap`.
- **Retire.** The predicate tests the path against the project and user settings locations, and a test shows a fixture write allows.
