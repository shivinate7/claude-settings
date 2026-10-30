# The phase rail splits a phase name at 372 to 380 px

- **What.** At a page width of 372 to 380 px, which covers the 375 phone, the status box is 340 px or wider, so the phase rail keeps 5 columns. The current phase's name then breaks inside the word, such as "Organiz / e •". Design review round 3 of step c136 measured it.
- **Where.** `skills/waiting-page/page.html`, `.prail .nm > span:first-child` (`overflow-wrap: anywhere`) and the `@container (max-width: 339px)` rule.
- **Decision.** None. Mockup: `docs/design/one-page-notes.md`, item 16.
- **Retire.** The 3-column rule starts at a box of about 355 px, or the dot moves to the next line. No phase name breaks inside a word at any width from 320 to 414.
