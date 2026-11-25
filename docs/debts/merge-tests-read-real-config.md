# merge/test_merge.py pops the config folder at import and never sets it

- **What.** `merge/test_merge.py` pops `CLAUDE_CONFIG_DIR` at import, in a loop over five names, and never sets it. Its cases read the real `~/.claude`. `python3 lint/check_tests_set_config.py` finds it. It waits on pull requests 3863, 3871 and 3872, which each hold that file.
- **Where.** `merge/test_merge.py:65`. The check is `lint/check_tests_set_config.py`.
- **Decision.** `tests-set-config`: a test file must not pop the config folder at import and leave it unset.
- **Retire.** `merge/test_merge.py` sets `CLAUDE_CONFIG_DIR` at module level after the pop loop, or in `setUpModule()`. Its case `test_repo_names_the_incident_file` in `lint/test_tests_set_config.py` is re-pointed to expect zero findings. Run `lint/test_tests_set_config.py`.
