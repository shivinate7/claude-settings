"""The guard's commit-trailer family: an agent's push whose commits name another model.

guard.py is the only entry point, and it runs this check in its fixed order. Other files reach these names
through `guard`. Decision commit-trailer-model.
"""
import json
import os
import re

import guard_core
from guard_core import split_segments, agent_transcript_path
from guard_merge import _plain_source, _push_calls
from guard_push_delete import push_refspecs

# The families a model id and a trailer both map to a name for. An agent's model id with a word outside it maps to
# nothing, so the check passes (fail open): `claude-zzz-9-9`. A trailer with no family word names no model of
# Claude's and passes, with or without a version: "Claude Code 2.1", `GPT-4` and `Claude 5.5`.
MODEL_FAMILIES = ("opus", "sonnet", "haiku", "fable")
# `claude-<family>-<major>-<minor>` then an optional suffix such as `[1m]`. A minor of three or more digits is a
# date (`claude-sonnet-4-20250514`), not a version, so it maps to nothing.
MODEL_ID = re.compile(r"claude-([a-z]+)-(\d+)-(\d{1,2})(?:\D.*)?\Z", re.S)
# A trailer value is read for a family word anywhere in it, in any casing, as a whole word (`Opus4.5` and
# `Claude_Opus_5.5` read; `Opusculum` does not). The version is the number right after the word, else right before
# it (`Claude 3.5 Sonnet`). A space, a hyphen or an underscore may sit between the word and its version, and a
# hyphen or a dot between major and minor: so `Claude Opus 5.5`, `Claude-Opus-5.5` and `claude-opus-5-5[1m]` read.
FAMILY_WORD = re.compile(r"(?<![a-z])(" + "|".join(MODEL_FAMILIES) + r")(?![a-z])", re.I)
VERSION_AFTER = re.compile(r"[\s_-]*(\d+)(?:[.-](\d{1,2}))?(?!\d)")
VERSION_BEFORE = re.compile(r"(?<!\d)(\d+)(?:[.-](\d{1,2}))?[\s_-]*\Z")
ADDRESS = re.compile(r"<[^>]*>")
TAIL_BYTES = 64 * 1024   # the first read of a transcript's end; it doubles until an assistant record shows
TAIL_MAX = 16 * 1024 * 1024
SYNTHETIC = "<synthetic>"

TRAILER_REASON = (
    "Rule (Git, commit-trailer-model; decision commit-trailer-model): a commit this push sends names another model "
    "in its Co-Authored-By trailer: commit {sha}. Your transcript names {own}. "
    "A trailer misstates who wrote the code. Remedy: amend the commit so Co-Authored-By names the model your own "
    "system prompt names, then push again."
)


def model_name(model_id):
    """(family, major, minor) for a model id such as `claude-opus-5-5[1m]`, else None."""
    found = MODEL_ID.match(model_id) if isinstance(model_id, str) else None
    if not found or found.group(1) not in MODEL_FAMILIES:
        return None
    return found.group(1), int(found.group(2)), int(found.group(3))


def last_models(path):
    """The `message.model` and the top-level `requestedModel` (beside `message`; None when absent) of the last
    assistant record in the transcript at `path`, else None. A turn a fallback served names the served model in
    one and the agent's own choice in the other. It reads the end of the file, doubling the window until a
    record shows. An unreadable file, a line that is not JSON and a synthetic record all read as no record."""
    try:
        size = os.path.getsize(path)
        window = TAIL_BYTES
        with open(path, "rb") as handle:
            while True:
                start = max(0, size - window)
                handle.seek(start)
                lines = handle.read(size - start).decode("utf-8", "replace").split("\n")
                if start:
                    lines = lines[1:]   # the first line of a window that starts mid-file is cut
                for line in reversed(lines):
                    try:
                        record = json.loads(line)
                        model = record["message"]["model"] if record["type"] == "assistant" else None
                    except (ValueError, KeyError, TypeError):
                        continue
                    if isinstance(model, str) and model != SYNTHETIC:
                        return model, record.get("requestedModel")
                if not start or window >= TAIL_MAX:
                    return None
                window *= 2
    except OSError:
        return None


def own_models(path):
    """The (family, major, minor) names the agent's last assistant record gives, served model first, else [].
    A name that maps to nothing is left out."""
    models = last_models(path) or ()
    names = []
    for model_id in models:
        name = model_name(model_id)
        if name and name not in names:
            names.append(name)
    return names


def trailer_differs(value, own):
    """True when the trailer `value` names a model that is not `own` (family, major, minor). A family word with
    no version differs only by family; a version with no minor differs only by major. A value with no family
    word names no model the rule knows, so it passes."""
    value = ADDRESS.sub(" ", value)
    found = FAMILY_WORD.search(value)
    if not found:
        return False   # "Claude Code 2.1", `GPT-4`, a person
    if found.group(1).lower() != own[0]:
        return True
    version = VERSION_AFTER.match(value, found.end()) or VERSION_BEFORE.search(value[:found.start()])
    if not version:
        return False
    if int(version.group(1)) != own[1]:
        return True
    return version.group(2) is not None and int(version.group(2)) != own[2]


def unpushed_trailers(where, sources):
    """(short sha, value) for each Co-Authored-By value git's own trailer parse reads from the commits `sources`
    reach that no remote ref holds, else None when git cannot answer. A commit's values are one line, split by
    the unit separator."""
    done = guard_core._git(where, "log", "--format=%h%x09%(trailers:key=Co-Authored-By,valueonly,separator=%x1f)",
                           *sources, "--not", "--remotes")
    if done is None or done.returncode != 0:
        return None
    found = []
    for line in done.stdout.splitlines():
        sha, _tab, values = line.partition("\t")
        found.extend((sha, value.strip()) for value in values.split("\x1f") if value.strip())
    return found


def commit_trailer_hit(stripped, cwd, transcript, agent_id):
    """(matched text, reason) for the first push of an agent that sends a commit whose Co-Authored-By names a model
    other than the agent's own, read from its transcript. Else None. No agent, no readable transcript, an
    unmapped model id and a git error all give None. Cost: one transcript read and one `git log` per push."""
    if not agent_id or not isinstance(transcript, str) or not transcript.endswith(".jsonl"):
        return None
    owns = None   # the agent's (family, major, minor) names, [] when unreadable; read at most once
    pushes = [push for segment in split_segments(stripped) if segment.strip()
              for push in _push_calls(segment, stripped, cwd)]   # inner_commands reads `bash -c`, `sh -lc`
    for args, where, _overrides in pushes:
        named = push_refspecs(args)
        if named is None or not where or not os.path.isdir(where):
            continue
        sources = []
        for spec in named[1] or [""]:
            source = _plain_source(spec.lstrip("+").partition(":")[0])
            if source not in sources:
                sources.append(source)
        values = unpushed_trailers(where, sources)
        if not values:
            continue
        if owns is None:   # only when a push has a trailer to judge
            path = agent_transcript_path(transcript, agent_id)
            owns = own_models(path) if path else []
        if not owns:
            return None
        for sha, value in values:
            if all(trailer_differs(value, own) for own in owns):   # a trailer naming either model passes
                return "Co-Authored-By: " + value, TRAILER_REASON.format(
                    sha=sha, own=" or ".join("%s %d.%d" % (o[0].capitalize(), o[1], o[2]) for o in owns))
    return None


# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
