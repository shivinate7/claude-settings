# schtasks /create /xml requires UTF-16, not UTF-8

## The claim

`schtasks /create /xml` rejects a well-formed task definition when the file is UTF-8.
It accepts the identical document, structure unchanged, when the file is UTF-16 little
endian with a byte order mark, and the declaration names that encoding.

## The measurement

Taken on one real Windows machine, today, against three encodings of the same document.

- UTF-8, no byte order mark: `ERROR: The task XML is malformed. (1,40)`, then
  `ERROR: unable to switch the encoding`. Exit code 1.
- UTF-8, with a byte order mark: `ERROR: The task XML is malformed. (1,2)`, then
  `ERROR: incorrect document syntax`. Exit code 1.
- UTF-16 little endian, with a byte order mark, declaration rewritten to
  `encoding='UTF-16'`: `SUCCESS: The scheduled task ... has successfully been created.`
  Exit code 0. The task then deleted cleanly, exit code 0.

No other change was made between the three runs. The XML structure carries no
`Principal` element and needed none.

## Why the installer shipped unvalidated

`janitor/install_schtasks.py` wrote its XML with
`ET.tostring(task, encoding="utf-8", xml_declaration=True)`. Its test suite,
`janitor/test_install_schtasks.py`, parsed the written file back with
`xml.etree.ElementTree` and checked the element shape. `ElementTree` reads UTF-8 without
complaint, so every case passed while the file itself was one real `schtasks.exe`
refuses. The suite checked shape. It never checked encoding, and never ran the real
tool. CLAUDE.md: "Trust a guard only once it goes red on the defect it guards."

## The fix

`build_task_xml` now calls
`ET.tostring(task, encoding="UTF-16", xml_declaration=True)`. Python's own `UTF-16`
codec writes the leading byte order mark and the matching declaration text. The suite
gained two cases that read the written bytes: one asserts the byte order mark, one
asserts the declaration names UTF-16. Both were proven red first, against a
deliberately reverted UTF-8 build, then proven green again after the fix was restored.

## What this decision is, and is not

This records a measured requirement of the real tool, not a style choice. It does not
touch the XML's structure, which was already correct. It does not authorize calling
`schtasks` from any automated check. The installer still only writes the file and
prints the command. Registering the task remains a separate act, on the owner's own
word.
