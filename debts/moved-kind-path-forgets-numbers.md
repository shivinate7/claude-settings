# A moved kind folder forgets the numbers used under its old path

- **What.** After a kind's folder or file is moved, the claim does not see the numbers that records used under the old path. It can hand out a number that an old record held. The workaround is to keep the old path in the kind's config, or to check those numbers by hand.
- **Where.** The history read in `actions/stamp/stamp.mjs`.
- **Decision.** `deleted-record-keeps-its-number` (a deleted numbered record keeps its number).
- **Retire.** The history read follows a moved kind path. A test that moves a kind folder, then claims, shows no reused number.
