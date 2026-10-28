# c154-cloud-handoff-hooks

Step c154: cloud installs keep the hand-off start-up hooks.

- Finding: install.sh cloud branch replaces `.hooks.SessionStart` with the refresh hook alone. No decision record covers it; its comment ("stays hook-free") predates the SessionStart hooks in settings.json. Ruled a defect, not intended.
- Fix plan: append the refresh hook to the repo's SessionStart list; red-then-green case in hooks/test_install_src.sh.
- State: builder (opus) running. Branch c154-cloud-handoff-hooks, no commit yet.
