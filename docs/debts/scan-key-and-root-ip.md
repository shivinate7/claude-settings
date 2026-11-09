# The export scan refuses a variable named KEY and an ssh root@ address

- **What.** In the 2026-11-08 export of the personal accounts' pages, the scan refused two pages for shapes that held no secret. banchi-answer-desk held a storage slot name in a variable called `KEY`; the `credential-name` shape read it as a key. degen-cockpit held an ssh command `root@<box IP>`; the `email` shape read it as an address. The owner reworded both live pages to pass. A third refusal, a vendor's support email and phone, was correct.
- **Where.** `skills/waiting-page/export_page.py`, `SECRET_SHAPES` entries `credential-name` and `email`.
- **Decision.** `waiting-data-in-repo` (a copy of the page lives in the repo; the scan runs before any write).
- **Retire.** The scan passes a short name-like value after `KEY` (no digit run, under the random-looking bar) and a `user@` before an IPv4 host, while it still refuses a random-looking key and a real address. A case for each form goes red first. Until then, the page writer rewords the page.
