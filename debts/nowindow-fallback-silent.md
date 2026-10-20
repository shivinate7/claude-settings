# The no-window fallback is silent

- **What.** A hook that falls back to plain subprocess says nothing, so the popups return unseen. No test loads the fallback sites with the helper removed.
- **Where.** The ImportError fallback blocks in hooks/, lint/, janitor/ and merge/.
- **Decision.** `spawns-use-no-window` (helper programs start with no window).
- **Retire.** A test removes the helper, imports every fallback site, and checks that a fallback is reported.
