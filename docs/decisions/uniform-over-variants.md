# A repo matches a shared format; the shared tool never grows a second form

## The ruling

Owner, 2026-10-27 12:51 CDT, topic t18 (one home, then variants): when a repo differs from a shared format, the repo changes to match it. The shared tool never grows a second accepted form to fit one repo.

- An option that widens what a shared tool accepts is a second accepted form, an allow-list entry or a per-repo exception. It carries "Goes against your uniform ruling (t18)" and is never the recommended option. Rule `style-option-widens-marked` holds the text.
- On the waiting page (skill `waiting-page`), such an option carries `widens: true`. Its card shows the label.
- Guard rule `uniform-pick` (`hooks/guard.py`) refuses an `ArtifactData` set or update to `items` whose `pick` names an option with `widens: true`. It reads each write in a batch and data read from `file_path`.
  - It judges only a call whose `url` is this repo's waiting page (`layout.waiting_page`), and only an item of kind `decision` or with no kind.
  - It is built against a named incident, below. It landed 2026-10-28.
  - Cost: no new process. It runs inside the guard process that every `ArtifactData` call already starts. It writes no file unless it denies.
  - Known limit: an update that sets `pick` without `options` cannot see the stored options and passes. The writer carries `options` again on such an update.
  - Known limit: the guard reads the `widens` mark, not the option's text. An unmarked widening option passes. The reply judge is the backstop.
- Reply judge (`hooks/reply_judge.py`, a model, never blocks): it flags a reply whose recommended option widens a shared tool, and a widening option offered without the label. It runs on the Stops it already judges, so it adds no model call.
- A shared gate that today lets one repo's variant through is a debt to remove (debt `layout-legacy-repos`).

Incident:

- 2026-10-27 12:51 CDT: a waiting-page item recommended loosening a shared tool so it would accept banchi's record titles.

Kind: process
Home: rule:style-option-widens-marked
