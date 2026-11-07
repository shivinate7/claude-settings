"""The tracked files a prose-copy check never reads. Standard library only, and no side effects on import.

GLOSSARY.md holds retired words on purpose, in its "Not" cells. docs/records.md is generated from the records, which
quote rule text by design. lint/paraphrase_labelled.json is fixture data for the meaning check and quotes retired text
on purpose. The copy finder (lint/find_copies.py), the reword check (lint/stale_cites.py) and the
retired-names test (lint/test_retired_names.py) all read these names from here.
"""
GLOSSARY = "GLOSSARY.md"
RECORDS_PAGE = "docs/records.md"
PARAPHRASE_LABELLED = "lint/paraphrase_labelled.json"
EXCLUDED_FILES = (GLOSSARY, RECORDS_PAGE, PARAPHRASE_LABELLED)
