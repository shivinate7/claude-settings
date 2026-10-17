# The stamp action flags a near-miss cite

## The ruling

The stamp action flags a cite that uses a record's prefix and a known slug in the wrong wrapper, such as
D`slug` with inline-code backticks. Reason: the dangling-cite check saw no cite pattern there, so the
stamp did not rewrite the cite to a numbered id and it stayed broken on main.

- The check lives in the stamp action, so every adopting repo gets it.
- An optional `cite.form` config field holds the form, such as `{prefix}‹{slug}›`. The remedy names it.
- Inline code stays flagged. A doc that must show the wrong form puts it in a fence.
- `hooks/agent_brief.py` adds one cite-form line per record kind to each agent brief. It reads the repo's stamp config.
- claude-sharables drops its own copy of the check later, in that repo.

Fences follow CommonMark. A fence opens at 0 to 3 columns past the content column of its list item or
blockquote. A tab counts to the next multiple of 4. A top-level fence indented 4 or more is an indented
code block, so it gives no protection.

Kind: process
Home: actions/stamp/stamp.mjs

## Holes, named

Debt `stamp-scan-frontmatter-links` is
low harm. None is a regression against main.
