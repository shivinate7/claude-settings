# The export scan still refuses a placeholder password word mid-sentence

- **What.** The waiting-page export allows `password: optional` and `PWD=/Users/x` only when nothing follows the value on its line. Page text such as `Set password: optional for the guest.` or `` `PWD=/Users/x` `` in backticks still refuses, and a refusal stops the whole artifact's export. Two of degen's four false alarms come back in that form.
- **Where.** `skills/waiting-page/export_page.py`, `REST_OF_LINE` and `bare_value`.
- **Decision.** `none`.
- **Retire.** The scan tells `password: optional for the guest` from `password: none hunter2`, for example with a stop-word list after the value, and strips a backtick pair. A case for each form goes red first. Until then, the page writer rewords the item.
