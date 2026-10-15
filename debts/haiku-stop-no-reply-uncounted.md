# A Stop with no reply text is not counted

- **What.** The counter counts only Stops that carry a reply. Such a Stop neither counts nor judges.
- **Where.** The counter in the Stop reply judge hook.
- **Decision.** `haiku-prompt-hooks` (haiku prompt hooks, Stop reply judge).
- **Retire.** Count and judge a Stop with no reply text, or name it as a limit. A test with no reply text gives the chosen verdict.
