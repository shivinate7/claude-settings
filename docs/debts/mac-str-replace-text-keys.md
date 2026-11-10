# Mac db_str_replace: the old and new text keys are unknown

- **What.** `normalize_data_call` joins every string value of a `db_str_replace` call (other than path, field, url, collection, doc_id, action and `old_str`) into `new_str`, so new text is judged under any key. If the Mac tool names the old text something other than `old_str`, an edit that removes a banned phrase reads the old text as new and is denied.
- **Where.** `hooks/shared_names.py` (`_MAC_STR_REPLACE_KNOWN`, `_mac_new_str`).
- **Decision.** none.
- **Retire.** The owner's Mac shows one redacted `db_str_replace` input, and the known-key row names its old and new text keys exactly. `hooks/test_shared_names.py` shows old text under the real key stays out of the judged text.
