# Stalled steps count as in progress

- **What.** The phase's "N in progress" count and the Latest changes feed count a stalled step as in progress. A stalled step keeps status `active`, and the count and the feed's kind read `active` as "In progress". This breaks the coordinator ruling in decision `stalled-steps` (a live doing step reads "In progress"; a stalled one does not).
- **Where.** `skills/roadmap/page/index.html` lines 553 and 561 (the count), 727 (`KIND`), 732 and 752 (feed rows). `skills/waiting-page/page.html` line 3089 (the count).
- **Decision.** `stalled-steps` (stalled steps: a stalled step is not "In progress").
- **Retire.** The count and the feed read a stalled id as stalled, as the Doing now list already draws it (`skills/waiting-page/page.html` line 3092). A page test shows a stalled `active` step is not counted in progress, and its feed row reads Stalled, on both pages.
