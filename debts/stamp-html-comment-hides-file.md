# A fence in an HTML comment hides the rest of the file

- **What.** A fence inside an HTML comment hides the rest of the file. Main has the same hole.
- **Where.** The fence scan in `actions/stamp/stamp.mjs`.
- **Decision.** `stamp-cite-near-miss` (the stamp cite near-miss check).
- **Retire.** Mask HTML comments before the fence scan. A test with a fence inside a comment still reads the rest of the file.
