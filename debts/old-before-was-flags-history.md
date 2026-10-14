# The records history rule flags a plain description as overruled text

- **What.** The rule flags `was:` when the word `old` comes earlier in the same block. It cannot tell a description from overruled text, so `The old flag was: on.` fails as history.
- **Where.** `OLD_WORD` and the `was:` test in `lint/hook_catalog.py`. Test c14 in `lint/test_hook_catalog.py` pins the current behaviour.
- **Decision.** `records-index-at-merge` (one generated records page, rebuilt at merge time). No decision entry holds it yet.
- **Retire.** The rule tells a description from overruled text, and c14 then passes the line. A rule change: the owner rules first.
