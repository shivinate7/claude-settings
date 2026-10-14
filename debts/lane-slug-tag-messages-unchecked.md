# The lane-slug rule does not read tag messages

- **What.** Tag messages are out of scope. A tag is another act, so the lane-slug rule does not read it.
- **Where.** The lane-slug rule's message readers.
- **Decision.** `lane-by-slug` (lanes are named by slug, and records are cited by id).
- **Retire.** Decide whether the rule reads tag messages. Then a test pins the call, or the owner records the scope.
