---
id: pending
slug: child-list
---

# The child list is one file, read only through its reader, and holds names only

## The ruling

Owner ruling, 14:27 CST, Nov 25, 2026, typed "yes" in the consultant's chat to this statement, relayed by the coordinator: `private repo names and ids may appear in this public repo; on yes PR 3947 merges as it is`.

An earlier relay from Sim Manager's chat, 14:12 CST, Nov 25, 2026, not typed in the consultant's chat, said the same. The owner ruled that private repo names and ids may appear in this repo. The list keeps names only, which works either way.

## The decision

- The child list is `docs/children.txt`. It holds one `owner/name since` line for each repo that registered with this repo.
- The list is read only through `lint/children.py`, the one reader.
- The file holds names only. It holds no repo id. The reader matches each child by name.
- Three other lists of repos exist in the repo. This decision does not move them.
- The branch that carries the list merges as it is. Its early commits hold repo ids and entry names, which the ruling above allows.

## Known limits

- A renamed child is unknown to the reader until its line is fixed by pull request.

Kind: process
Home: lint/children.py
