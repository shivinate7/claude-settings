# The owner acts where he reads; he never hunts for what he must act on

## The ruling

Owner, 2026-10-28 13:01 CDT (waiting-page gripe on item 47): when an item asks the owner to act, everything he needs sits on the item. He never searches for the page to press on or the file that holds a command.

- An option or step that asks him to press in a web app (GitHub, a pull request, a `home#374` ref, Settings) carries a link to that exact page. The link sits on the option that presses; a task carries `links` on the item. A `#374` ref needs a url with `/pull/374` or `/issues/374`. Rule `style-press-has-link` holds the text.
- A step never sends him to a file for a command. The command sits in the task's `command` field, which the page shows in a closed "Show the command" disclosure with a Copy button. The step says "paste the command below". Rule `style-command-in-item` holds the text.
- Guard rule `press-link` (`hooks/guard.py`) refuses an `ArtifactData` set or update to `items` whose option or step has a press verb and a web marker in one field. It refuses when no link goes to the exact page.
  - It skips an update with `steps` and no `links`: the stored links are not visible.
- Guard rule `command-in-item` refuses a task set or update whose steps, joined, name a file and a command in it. It skips a set whose item carries `command`. It does not judge a decision.
- Both rules judge only a call whose `url` is this repo's waiting page (`layout.waiting_page`). Both are built against the named incidents below. They landed 2026-10-29.
  - Cost: no new process. They run inside the guard process that every `ArtifactData` call already starts. They write no file unless they deny.
  - Known limit: the guard reads words, not meaning. A press worded with no verb and no marker passes.

Incidents:

- 2026-10-28 13:01 CDT, waiting-page item 47: option a asked him to mark home#374 ready and press Merge, with no link to it.
- Waiting-page item 39: the steps sent him to `plans/c152-stale-branch-deletes.md` for the command.

Kind: process
Home: rule:style-press-has-link
