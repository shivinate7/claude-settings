# A session never writes the waiting page's answers

## The ruling

Owner, 2026-11-06 11:38 CST: a mistake Claude made means that a guard is missing (decision `mistake-means-missing-guard`). The skill rule "Never write `answers/`" (`skills/waiting-page/SKILL.md`) was the only guard of the owner's grant, so it needs a hook.

- Guard rule `page-answers-write` (`hooks/guard.py`, `page_answers_hit`). A `PreToolUse` `ArtifactData` call is denied when it sets, updates or str_replaces the `answers` collection and its `url` is this repo's registered waiting page (`question_form.waiting_page_root`). It judges a single call, and each entry of a `batch` `writes` list. One bad entry denies the batch.
- The one parser of a call's entries is `hooks/question_form.py` `call_entries`. The item rules (`page_item_hit`) and this rule both read it. The collection name is `WAITING_ANSWERS`, beside `WAITING_ITEMS`.
- The refusal says only the owner's Send writes `answers/`, and that an owner chat answer goes to the item's `lastAnswer` and `reply`. It names no path to work around.
- Allowed:
  - A delete, a get, a list and a query of `answers`. A session routes an answer by deleting its record (skill `waiting-page`, "Route and close").
  - A write to any other collection.
  - An `answers` write to another url. This is the rebuild path (skill `waiting-page`, "Rebuild a page from the repo", steps 4 and 7). The batches that restore `answers` go to the new page before its url is registered in the extras file. The guard knows only the registered page, so the new page is another url until step 7 lands.
- Incident class: named incident (rule `building-guard-needs-incident`), 2026-11-06. The triage session wrote `answers/local-triage-tier-build` at 15:45 CST from words the owner typed in chat, and earlier restored the answers of items 289 and 290. No hook refused either write.
- Harm: a forged owner grant. A record in `answers/` reads as the owner's Send, and the checker `page_grant.py` counts a clear one as a grant for a lane to build. ArtifactData writes as the owner, so the page cannot tell the two writes apart.
- Cost:
  - Pure Python on an `ArtifactData` call. A call with no write to `answers` does no work beyond reading its entries.
  - A call that writes `answers` reads the layout and extras file once, as the item rules already do. No process, no file written, no log line.
  - An unreadable layout allows the call and logs one `noted` line under `page-answers-write`.
- Known limit: a session whose cwd is another repo is not judged. The rule asks the cwd repo's page, so a call from there names a page it does not hold.
- Known limit: a delete of an answer while its item is open with a lane is not judged. The hook sees no live item state. Roadmap step `page-answer-delete-guard` stays open.

Kind: process
Home: rule:questions-go-to-owner
