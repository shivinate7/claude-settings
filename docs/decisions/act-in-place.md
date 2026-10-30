# The owner acts where he reads; he never hunts for what he must act on

## The ruling

Owner, 2026-10-28 13:01 CDT (waiting-page gripe on item 47): when an item asks the owner to act, everything he needs sits on the item. He never searches for the page to press on or the file that holds a command.

- An option or step that asks him to press in a web app (GitHub, a pull request, a `home#374` ref, Settings) carries a link to that exact page. The link sits on the option that presses; a task carries `links` on the item. A `#374` ref needs a url with `/pull/374` or `/issues/374`. Rule `style-press-has-link` holds the text.
- A step never sends him to a file for a command, and never holds one. Owner, 2026-10-30 14:47 CDT (item 78 note): the command comes as PowerShell and Mac. The task's `command` field is `{powershell, mac}`: a PowerShell 5.1-safe block and a bash or zsh block. The page shows one closed disclosure per shell, each with a Copy button, PowerShell first on Windows. The step says "paste the command below". Rule `style-command-in-item` holds the text.
  - A stored `command` that is one string, from before this ruling, shows as one block with no shell label, so a bash line never shows under a PowerShell label. The guard refuses a new write of one.
- Guard rule `press-link` (`hooks/question_form.py`, run by `hooks/guard.py`) refuses an `ArtifactData` set or update to `items` whose option (label and how, read together) or task steps (joined; the title names the page when the steps name none) have a press verb and a web marker. A press verb is press, click or tap (but not "press on", and not the page's own Send, Mark done or Take my pick), an imperative approve, merge, hit or turn on (`you` may come first), or "mark" a PR or `#N` "ready", or "mark ... ready on" a ref. A web marker is GitHub, a PR, a pull request, a `#N` ref (not "item #N" or "step #N"), or Settings as a page name. It refuses when no link goes to the page.
  - A `#N` ref needs a url with `/pull/N` or `/issues/N`. An unnumbered press passes with any link.
  - It skips an update with `steps` and no `links`: the stored links are not visible.
- Guard rule `command-in-item` refuses a task set or update whose steps, joined, say "the command in/from <file>", or say "its command" with a file named. It also refuses "run/copy/paste the command" with a file named; "the command below" never matches. A `command` on the item does not excuse a step that points at a file. It also refuses a `command` that is not both `powershell` and `mac` as non-empty strings. It refuses a `powershell` block with `&&`, `||`, `<<`, `<<<`, `/dev/null` or `export`, since PowerShell 5.1 has none of them. It refuses a step whose backtick span or fence holds a shell line. It does not judge a decision.
- Both rules judge only a call whose `url` is this repo's waiting page (`layout.waiting_page`). Both are built against the named incidents below. They landed 2026-10-29; the shell checks of `command-in-item` landed 2026-10-30.
  - Cost: no new process. They run inside the guard process that every `ArtifactData` call already starts. They write no file unless they deny.
  - Known limit: the guard reads words, not meaning. A press verb outside the list (such as enable auto-merge, select or close) passes. An unnumbered press passes with any link.

Incidents:

- 2026-10-28 13:01 CDT, waiting-page item 47: option a asked him to mark home#374 ready and press Merge, with no link to it.
- Waiting-page item 39: the steps sent him to `plans/c152-stale-branch-deletes.md` for the command.
- 2026-10-30 14:40 CDT, waiting-page item 78: a bash-only command under "any terminal works" failed in his Windows PowerShell 5.1 on `&&` and `<<<`.

Kind: process
Home: rule:style-press-has-link
