"""The tier-file fixtures that hooks/test_guard.py (section 5e-3) and hooks/test_session_tier.py share.

Standard library only, and no cases: a test file imports it. Not a test_*.py file, so it has no CI step of its own.

The formats are the spec's (the tier file, one home hooks/session_tier.py). A grant file per folder, named
grant-<first 16 hex digits of sha256(folder key)>.json, holds {"tier", "folder", "at"}. A bound file per session id,
named <session id>.json, holds the same three fields. The folder key is the spec's rule: the real path, case-folded
where the platform folds case, with no trailing separator. It is written here as an oracle, so each suite judges the
module and the guard against the written format and never against the other.
"""
import hashlib
import json
import os
import time

TRIAGE = "triage"
FRESH_AGE = 60         # seconds: a grant this young is valid
STALE_AGE = 2 * 3600   # seconds: past the hour a grant lives


def norm_key(folder):
    """The folder key the spec names: the real path, case-folded where the platform folds case, no trailing separator."""
    norm = os.path.normcase(os.path.realpath(folder))
    return norm.rstrip(os.sep) or os.sep


def tier_dir(config):
    return os.path.join(config, "session-tiers")


def grant_file(config, folder):
    digest = hashlib.sha256(norm_key(folder).encode("utf-8")).hexdigest()[:16]
    return os.path.join(tier_dir(config), "grant-" + digest + ".json")


def bound_file(config, session):
    return os.path.join(tier_dir(config), session + ".json")


def write_file(path, body, crlf_bom=False):
    """One tier file. A dict is written as JSON; bytes are written as they are. CRLF lines and a BOM are the Windows
    spelling a grant or bound file may carry."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if isinstance(body, bytes):
        data = body
    else:
        text = json.dumps(body, indent=2)
        data = ("﻿" + text.replace("\n", "\r\n")).encode("utf-8") if crlf_bom else text.encode("utf-8")
    with open(path, "wb") as handle:
        handle.write(data)


def write_grant(config, folder, age=FRESH_AGE, crlf_bom=False, tier=TRIAGE):
    """The grant for `folder`, written `age` seconds ago."""
    body = {"tier": tier, "folder": norm_key(folder), "at": int(time.time()) - age}
    write_file(grant_file(config, folder), body, crlf_bom)


def write_bound(config, session, folder, tier=TRIAGE, crlf_bom=False):
    """The bound file for `session`, naming `folder`, written now."""
    body = {"tier": tier, "folder": norm_key(folder), "at": int(time.time())}
    write_file(bound_file(config, session), body, crlf_bom)
