# An ANSI-C word in eval or bash -c passes after a refusal

**What.** After a refusal, the guard reads an ANSI-C word inside the script of `bash -c` or `eval` as plain text, so `bash -c $'\x63d /tmp'` and `eval $'\x63d /tmp'` pass. It is the next hop after a refusal: three sightings used three encodings, base64 (PR #2211), encoded quotes (PR #2288) and `\x63d` (PR #2295). Checked on fa589236a: the shape check does not match either form.

**Where.** `hooks/guard_encoded.py`, `_scan_text` (about L211-273). The ANSI-C test `_ansi_c_escape` reads a raw word. `nested_script` (`hooks/guard_core.py` L1776) returns the `bash -c` and `eval` script with its quotes removed (`bash -c $'\x63d /tmp'` gives `$\x63d /tmp`), so no `$'` span is left to match. The decision's Not read list names the gap.

**Decision.** `encoded-retry-after-refusal`, a refused command is not sent again in an encoded form. Its Not read list names this gap.

**Retire.** Closed when a red case with a fresh refusal row in `hooks/test_guard.py` refuses both `bash -c $'\x63d /tmp'` and `eval $'\x63d /tmp'`, and its no-refusal twin passes.

## Ruling

None yet.
