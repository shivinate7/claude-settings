# section 42900
# ---------------------------------------------------------------- commit-trailer-model: an agent's push
#
# An agent's `git push origin HEAD:<branch>` is refused when a commit it sends names, in its Co-Authored-By
# trailer, a model (family word plus version) that differs from the model the agent runs. The agent's model
# is the last assistant record of its own transcript: `<transcript minus .jsonl>/subagents/agent-<id>.jsonl`.
# The trailers are read by git's trailer parsing, from the commits no remote ref holds, never from the shell
# text. A trailer that names no model, a missing or unreadable transcript, a model id that maps to no name, an
# orchestrator's push (no agent_id) and a push with nothing new all pass. The rule id is commit-trailer-model,
# the same as its decision id; the check itself is guard_trailer.py.
FAMILY = "commit-trailer-model"
CTM_RULE = "commit-trailer-model"
CTM_BRANCH = "ctm-topic"
CTM_PUSH = VCS + " push origin HEAD:" + CTM_BRANCH
CTM_ROOT = os.path.join(ROOT, "ctm")
CTM_SESSION = "session_0000"   # a stand-in for a real session id, in the payload and in the trailer
CTM_TRANSCRIPT = os.path.join(CTM_ROOT, "projects", "-ctm-slug", CTM_SESSION + ".jsonl")
CTM_SUBDIR = os.path.join(CTM_ROOT, "projects", "-ctm-slug", CTM_SESSION, "subagents")
# One agent id per transcript shape: 17 lowercase hex characters, as the payload carries them.
CTM_HAIKU, CTM_SONNET, CTM_OPUS_1M = "7c1e9a4b0d2f63e85", "2a6f0c8d1e7b94a30", "e0b4d7a19c3f25b68"
CTM_FABLE, CTM_LAST, CTM_UNMAPPED = "5d93b1e6a0c4f7289", "9f2a6c03e8d15b7a4", "3b8e15c7f902d4a6e"
CTM_NOASSIST, CTM_GARBAGE, CTM_EMPTY = "c4d07a9e62b13f58d", "08f5b2d9e4a71c63b", "f61a3c8e0d9b5427c"
CTM_DIRECTORY, CTM_MISSING = "a7e2d4c1b9f08635d", "b0c9f3a6e2d78514e"
CTM_FALLBACK = "d6a1f3b08c5e72947"   # a turn a fallback served: message.model is Sonnet, requestedModel is Opus
CTM_AGENTS = (CTM_HAIKU, CTM_SONNET, CTM_OPUS_1M, CTM_FABLE, CTM_LAST, CTM_UNMAPPED, CTM_NOASSIST,
              CTM_GARBAGE, CTM_EMPTY, CTM_DIRECTORY, CTM_MISSING, CTM_FALLBACK)
if not all(re.fullmatch(r"[0-9a-f]{17}", agent) for agent in CTM_AGENTS):
    sys.exit("fixture setup failed: an agent id is not 17 lowercase hex characters")


def ctm_record(agent_id, model=None, requested=None):
    """One record of an agent's transcript, in the shape measured on this machine. An assistant record
    carries `message.model`, which the rule reads. Without a model it is a user record. `requested`, when
    given, sets the record's `requestedModel`: the model the agent asked for, which a fallback may not serve."""
    if model is None:
        return json.dumps({"type": "user", "agentId": agent_id, "isSidechain": True,
                           "message": {"role": "user", "content": "push the branch"}})
    record = {"type": "assistant", "agentId": agent_id, "isSidechain": True,
              "message": {"role": "assistant", "model": model,
                          "content": [{"type": "text", "text": "pushed"}]}}
    if requested is not None:
        record["requestedModel"] = requested
    return json.dumps(record)


def ctm_transcript(agent_id, *lines):
    """Write `agent_id`'s transcript, one line each, in the subagents folder beside the session transcript."""
    write(os.path.join(CTM_SUBDIR, "agent-" + agent_id + ".jsonl"), "".join(line + "\n" for line in lines))


write(CTM_TRANSCRIPT, "{}\n")  # an orchestrator's push names this file and reads no agent file
ctm_transcript(CTM_HAIKU, ctm_record(CTM_HAIKU, "claude-haiku-5-5"))
ctm_transcript(CTM_SONNET, ctm_record(CTM_SONNET, "claude-sonnet-5-5"))
ctm_transcript(CTM_OPUS_1M, ctm_record(CTM_OPUS_1M, "claude-opus-5-5[1m]"))
ctm_transcript(CTM_FABLE, ctm_record(CTM_FABLE, "claude-fable-5-1"))
# The last assistant record names the model. The earlier Opus record does not count.
ctm_transcript(CTM_LAST, ctm_record(CTM_LAST, "claude-opus-5-5"), ctm_record(CTM_LAST, "claude-haiku-5-5"))
ctm_transcript(CTM_UNMAPPED, ctm_record(CTM_UNMAPPED, "claude-zzz-9-9"))
ctm_transcript(CTM_FALLBACK, ctm_record(CTM_FALLBACK, "claude-sonnet-5-5", requested="claude-opus-5-5"))
ctm_transcript(CTM_NOASSIST, ctm_record(CTM_NOASSIST))
ctm_transcript(CTM_GARBAGE, "not json", '{"type": ')
ctm_transcript(CTM_EMPTY)
os.makedirs(os.path.join(CTM_SUBDIR, "agent-" + CTM_DIRECTORY + ".jsonl"), exist_ok=True)  # unreadable: a folder


def ctm_value(model):
    """What a Co-Authored-By trailer carries for `model`: the name, then the noreply address."""
    return model + " <noreply@anthropic.com>"


def ctm_trailer(model):
    return "Co-Authored-By: " + ctm_value(model)


def ctm_message(*trailers, body=None):
    """A commit message: a subject, an optional body paragraph, then the trailers as the last paragraph.
    Git reads trailers from that last paragraph only."""
    paragraphs = ["Follow-up fixture"]
    if body:
        paragraphs.append(body)
    paragraphs.append("\n".join(trailers))
    return "\n\n".join(paragraphs) + "\n"


# The trailer block of the incident commit 3b5516cf8, whose trailer named Opus from a Haiku agent. The session id is a stand-in.
CTM_INCIDENT = ctm_message(ctm_trailer("Claude Opus 5.5"),
                           "Claude-Session: https://claude.ai/code/" + CTM_SESSION)


def ctm_commit(where, index, message):
    """Commit one new file. The message is written to a file first, so git reads it exactly as written."""
    write(os.path.join(where, "f%d.txt" % index), "%d\n" % index)
    run_vcs(where, "add", "-A")
    text = os.path.join(os.path.dirname(where), "msg%d.txt" % index)
    write(text, message)
    done = run_vcs(where, *IDENT, "commit", "-q", "-F", text)
    if done.returncode != 0:
        sys.exit("fixture setup failed: commit %d in %r: %s" % (index, where, done.stderr.strip()))


def ctm_repo(name, expect, pushed=(), local=(), branch=None):
    """A checkout on `ctm-topic`, cut from origin/main, beside a bare origin. Each message in `pushed` is
    committed and pushed to origin's `ctm-topic`; each in `local` is committed after them and never pushed.
    `branch`, when given, is a second local branch at the same commit, for a push that names it. Built on first
    use. Before any case runs, the read back holds: the commits no remote ref holds are `local`, and the
    Co-Authored-By values git's trailer parsing reads from them are `expect`."""
    where = os.path.join(CTM_ROOT, name, "repo")
    origin = os.path.join(CTM_ROOT, name, "origin.git")

    def build():
        make_repo(where, {"base.txt": "base\n"})
        run_vcs(where, "init", "--bare", "-q", origin)
        run_vcs(where, "remote", "add", "origin", origin)
        run_vcs(where, "push", "-q", "origin", "main")
        run_vcs(where, "checkout", "-q", "-b", CTM_BRANCH)
        for index, message in enumerate(list(pushed) + list(local)):
            ctm_commit(where, index, message)
            if pushed and index + 1 == len(pushed):
                sent = run_vcs(where, "push", "-q", "origin", "HEAD:" + CTM_BRANCH)
                if sent.returncode != 0:
                    sys.exit("fixture setup failed: push in %r: %s" % (where, sent.stderr.strip()))
        if branch:
            made = run_vcs(where, "branch", branch)
            if made.returncode != 0:
                sys.exit("fixture setup failed: branch %s in %r: %s" % (branch, where, made.stderr.strip()))
        unsent = run_vcs(where, "rev-list", "--count", "HEAD", "--not", "--remotes")
        # HEAD is named: a log with only `--not` and no positive revision walks nothing.
        values = run_vcs(where, "log", "--format=%(trailers:key=Co-Authored-By,valueonly)", "HEAD", "--not",
                         "--remotes")
        found = sorted(line for line in values.stdout.splitlines() if line.strip())
        if unsent.stdout.strip() != str(len(local)) or found != sorted(expect):
            sys.exit("fixture setup failed: %r holds %s unsent commits with trailers %r, want %d with %r"
                     % (where, unsent.stdout.strip(), found, len(local), sorted(expect)))

    lazy_fixture([where], build)
    return where


CTM_REPO_INCIDENT = ctm_repo("incident", [ctm_value("Claude Opus 5.5")], local=[CTM_INCIDENT])
CTM_REPO_HAIKU = ctm_repo("haiku", [ctm_value("Claude Haiku 5.5")],
                          local=[ctm_message(ctm_trailer("Claude Haiku 5.5"))])
CTM_REPO_SONNET = ctm_repo("sonnet", [ctm_value("Claude Sonnet 5.5")],
                           local=[ctm_message(ctm_trailer("Claude Sonnet 5.5"))])
CTM_REPO_FABLE = ctm_repo("fable", [ctm_value("Claude Fable 5.1")],
                          local=[ctm_message(ctm_trailer("Claude Fable 5.1"))])
CTM_REPO_VERSION = ctm_repo("version", [ctm_value("Claude Haiku 4.5")],
                            local=[ctm_message(ctm_trailer("Claude Haiku 4.5"))])
CTM_REPO_NOMODEL = ctm_repo("nomodel", [ctm_value("Claude")], local=[ctm_message(ctm_trailer("Claude"))])
CTM_REPO_FAMILY = ctm_repo("family", [ctm_value("Claude Opus")], local=[ctm_message(ctm_trailer("Claude Opus"))])
CTM_REPO_FAMILYMATCH = ctm_repo("familymatch", [ctm_value("Claude Haiku")],
                                local=[ctm_message(ctm_trailer("Claude Haiku"))])
CTM_REPO_TWO = ctm_repo("two", [ctm_value("Claude Opus 5.5"), ctm_value("Claude Haiku 5.5")],
                        local=[ctm_message(ctm_trailer("Claude Opus 5.5")),
                               ctm_message(ctm_trailer("Claude Haiku 5.5"))])
CTM_REPO_LONG = ctm_repo("long", [ctm_value("Claude Opus 5.5")] + [ctm_value("Claude Haiku 5.5")] * 24,
                         local=[ctm_message(ctm_trailer("Claude Opus 5.5"))]
                         + [ctm_message(ctm_trailer("Claude Haiku 5.5")) for _ in range(24)])
# The Opus line sits in a body paragraph, and the Haiku trailer is the last paragraph: git reads only the last.
CTM_REPO_BODY = ctm_repo("body", [ctm_value("Claude Haiku 5.5")],
                         local=[ctm_message(ctm_trailer("Claude Haiku 5.5"), body=ctm_trailer("Claude Opus 5.5"))])
CTM_REPO_PUSHED = ctm_repo("pushed", [ctm_value("Claude Haiku 5.5")],
                           pushed=[ctm_message(ctm_trailer("Claude Opus 5.5"))],
                           local=[ctm_message(ctm_trailer("Claude Haiku 5.5"))])
CTM_REPO_NOTHING = ctm_repo("nothing", [], pushed=[ctm_message(ctm_trailer("Claude Opus 5.5"))])
# The same model in other spellings: the model id form, hyphens, spaces and lowercase. The trailer value is
# read as written, so each spelling is its own repository.
CTM_REPO_IDOPUS = ctm_repo("idopus", [ctm_value("claude-opus-5-5")],
                           local=[ctm_message(ctm_trailer("claude-opus-5-5"))])
CTM_REPO_HYPHEN = ctm_repo("hyphen", [ctm_value("Claude-Opus-5.5")],
                           local=[ctm_message(ctm_trailer("Claude-Opus-5.5"))])
CTM_REPO_SPACED = ctm_repo("spaced", [ctm_value("claude opus 5.5")],
                           local=[ctm_message(ctm_trailer("claude opus 5.5"))])
CTM_REPO_IDHAIKU = ctm_repo("idhaiku", [ctm_value("claude-haiku-5-5")],
                            local=[ctm_message(ctm_trailer("claude-haiku-5-5"))])
# Push forms: the commit is an Opus trailer, and a local branch `x` names the same commit, so `origin x` has a source.
CTM_REPO_XBRANCH = ctm_repo("xbranch", [ctm_value("Claude Opus 5.5")], local=[CTM_INCIDENT], branch="x")
# Trailers that name no model family the rule knows, or name one with a suffix, a separator or no space.
CTM_REPO_CLAUDE55 = ctm_repo("claude55", [ctm_value("Claude 5.5")], local=[ctm_message(ctm_trailer("Claude 5.5"))])
CTM_REPO_CLAUDECODE = ctm_repo("claudecode", [ctm_value("Claude Code 2.1")],
                               local=[ctm_message(ctm_trailer("Claude Code 2.1"))])
CTM_REPO_GPT4 = ctm_repo("gpt4", [ctm_value("GPT-4")], local=[ctm_message(ctm_trailer("GPT-4"))])
CTM_REPO_OPUS1M = ctm_repo("opus1m", [ctm_value("claude-opus-5-5[1m]")],
                           local=[ctm_message(ctm_trailer("claude-opus-5-5[1m]"))])
CTM_REPO_UNDERSCORE = ctm_repo("underscore", [ctm_value("Claude_Opus_5.5")],
                               local=[ctm_message(ctm_trailer("Claude_Opus_5.5"))])
CTM_REPO_OPUS4 = ctm_repo("opus4", [ctm_value("Claude Opus4.5")], local=[ctm_message(ctm_trailer("Claude Opus4.5"))])
CTM_REPO_HAIKU1M = ctm_repo("haiku1m", [ctm_value("claude-haiku-5-5[1m]")],
                            local=[ctm_message(ctm_trailer("claude-haiku-5-5[1m]"))])
# A family word after a version, or no version at all. The family word may sit anywhere in the value.
CTM_REPO_CLAUDE3OPUS = ctm_repo("claude3opus", [ctm_value("Claude 3 Opus")],
                                local=[ctm_message(ctm_trailer("Claude 3 Opus"))])
CTM_REPO_CLAUDE35SONNET = ctm_repo("claude35sonnet", [ctm_value("Claude 3.5 Sonnet")],
                                   local=[ctm_message(ctm_trailer("Claude 3.5 Sonnet"))])
CTM_REPO_CLAUDESONNET = ctm_repo("claudesonnet", [ctm_value("Claude Sonnet")],
                                 local=[ctm_message(ctm_trailer("Claude Sonnet"))])
CTM_REPO_CLAUDE21 = ctm_repo("claude21", [ctm_value("Claude 2.1")], local=[ctm_message(ctm_trailer("Claude 2.1"))])
# A version that differs from the agent's is a different model in every spelling: the model id form, hyphens, an
# underscore, a space. The name is read as written, so each spelling is its own repository.
CTM_REPO_HAIKU45ID = ctm_repo("haiku45id", [ctm_value("claude-haiku-4-5")],
                              local=[ctm_message(ctm_trailer("claude-haiku-4-5"))])
CTM_REPO_HAIKU45HYPHEN = ctm_repo("haiku45hyphen", [ctm_value("Claude-Haiku-4.5")],
                                  local=[ctm_message(ctm_trailer("Claude-Haiku-4.5"))])
CTM_REPO_HAIKU45UNDER = ctm_repo("haiku45under", [ctm_value("Claude_Haiku_4.5")],
                                 local=[ctm_message(ctm_trailer("Claude_Haiku_4.5"))])
CTM_REPO_HAIKU54 = ctm_repo("haiku54", [ctm_value("Claude Haiku 5.4")],
                            local=[ctm_message(ctm_trailer("Claude Haiku 5.4"))])
# A name with a family word in it, or in an address, is a person's or a product's name and not a model. The trailer
# is written as given: the address is part of the value, so no noreply address is added.
CTM_REPO_JANE = ctm_repo("jane", ["Jane <opus@example.com>"],
                         local=[ctm_message("Co-Authored-By: Jane <opus@example.com>")])
CTM_REPO_OPUSCULUM = ctm_repo("opusculum", ["Opusculum Jones"],
                              local=[ctm_message("Co-Authored-By: Opusculum Jones")])
# A minor version that differs from the agent's is a different model, in the model id form and with the version
# before the family word. Each is read as written.
CTM_REPO_HAIKU54ID = ctm_repo("haiku54id", [ctm_value("claude-haiku-5-4")],
                              local=[ctm_message(ctm_trailer("claude-haiku-5-4"))])
CTM_REPO_CLAUDE54HAIKU = ctm_repo("claude54haiku", [ctm_value("Claude 5-4 Haiku")],
                                  local=[ctm_message(ctm_trailer("Claude 5-4 Haiku"))])


def ctm_case(name, repo, expected, agent, command=CTM_PUSH, transcript=CTM_TRANSCRIPT):
    """One case: `command`, run by `agent` in `repo`. No agent is the orchestrator. A refusal names the rule and
    the Co-Authored-By line it judged. An allow names nothing, so it pins the verdict alone."""
    deny = expected == "deny"
    sh("commit trailer: " + name, command, expected, CTM_RULE if deny else None, cwd=repo,
       agent_id=agent, transcript=transcript, carries=("Co-Authored-By",) if deny else ())


# REFUSED: a pushed commit names a model that differs from the agent's own model.
ctm_case("the 3b5516cf8 trailer from a Haiku agent is refused", CTM_REPO_INCIDENT, "deny", CTM_HAIKU)
ctm_case("a Haiku trailer from a Sonnet agent is refused", CTM_REPO_HAIKU, "deny", CTM_SONNET)
ctm_case("an Opus trailer from a Fable agent is refused", CTM_REPO_INCIDENT, "deny", CTM_FABLE)
ctm_case("a Haiku trailer from an Opus agent on the [1m] model is refused", CTM_REPO_HAIKU, "deny", CTM_OPUS_1M)
ctm_case("a Haiku 4.5 trailer from a Haiku 5.5 agent is refused", CTM_REPO_VERSION, "deny", CTM_HAIKU)
ctm_case("an Opus trailer on the older of two unpushed commits is refused", CTM_REPO_TWO, "deny", CTM_HAIKU)
ctm_case("an Opus trailer is refused when the last assistant record is Haiku", CTM_REPO_INCIDENT, "deny", CTM_LAST)
ctm_case("an Opus trailer on the oldest of 25 unpushed commits is refused", CTM_REPO_LONG, "deny", CTM_HAIKU)
ctm_case("a family word with no version naming another family is refused", CTM_REPO_FAMILY, "deny", CTM_HAIKU)

# PASSES: the model matches, or no model is named, or the agent's model is unknown, or the check is not the agent's.
ctm_case("a Haiku trailer from a Haiku agent passes", CTM_REPO_HAIKU, "allow", CTM_HAIKU)
ctm_case("an Opus trailer from an Opus agent on the [1m] model passes", CTM_REPO_INCIDENT, "allow", CTM_OPUS_1M)
ctm_case("a Fable trailer from a Fable agent passes", CTM_REPO_FABLE, "allow", CTM_FABLE)
ctm_case("a Sonnet trailer from a Sonnet agent passes", CTM_REPO_SONNET, "allow", CTM_SONNET)
ctm_case("a Haiku trailer passes when the last assistant record is Haiku", CTM_REPO_HAIKU, "allow", CTM_LAST)
ctm_case("a trailer that names no model passes", CTM_REPO_NOMODEL, "allow", CTM_HAIKU)
ctm_case("a family word with no version passes when it names the agent's own family", CTM_REPO_FAMILYMATCH, "allow", CTM_HAIKU)
ctm_case("an Opus line in a body paragraph is not a trailer and passes", CTM_REPO_BODY, "allow", CTM_HAIKU)
ctm_case("an Opus commit already on origin is not judged", CTM_REPO_PUSHED, "allow", CTM_HAIKU)
ctm_case("a push with nothing new to send passes", CTM_REPO_NOTHING, "allow", CTM_HAIKU)
ctm_case("an Opus name in the shell text passes when the commit names Haiku", CTM_REPO_HAIKU, "allow", CTM_HAIKU,
         command="echo \"Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\" && " + CTM_PUSH)
ctm_case("an agent's git log, not its push, is not judged", CTM_REPO_INCIDENT, "allow", CTM_HAIKU,
         command=VCS + " log -1")
ctm_case("an orchestrator's push, with no agent_id, passes", CTM_REPO_INCIDENT, "allow", None)
ctm_case("an agent with no transcript_path passes", CTM_REPO_INCIDENT, "allow", CTM_HAIKU, transcript=None)
ctm_case("an agent whose transcript is missing passes", CTM_REPO_INCIDENT, "allow", CTM_MISSING)
ctm_case("an agent whose transcript path is a folder passes", CTM_REPO_INCIDENT, "allow", CTM_DIRECTORY)
ctm_case("an agent whose transcript is not JSON passes", CTM_REPO_INCIDENT, "allow", CTM_GARBAGE)
ctm_case("an agent whose transcript is empty passes", CTM_REPO_INCIDENT, "allow", CTM_EMPTY)
ctm_case("an agent whose transcript holds no assistant record passes", CTM_REPO_INCIDENT, "allow", CTM_NOASSIST)
ctm_case("an agent whose model id maps to no name passes", CTM_REPO_INCIDENT, "allow", CTM_UNMAPPED)

# The model id form, hyphens, spaces and lowercase each name a model, and each is judged as the model it names.
# A fallback serves Sonnet when the agent asked for Opus, so an Opus or a Sonnet trailer passes there and a
# Haiku one does not.
ctm_case("a model id trailer, claude-opus-5-5, from a Haiku agent is refused", CTM_REPO_IDOPUS, "deny", CTM_HAIKU)
ctm_case("a hyphenated Claude-Opus-5.5 trailer from a Haiku agent is refused", CTM_REPO_HYPHEN, "deny", CTM_HAIKU)
ctm_case("a spaced lowercase claude opus 5.5 trailer from a Haiku agent is refused", CTM_REPO_SPACED, "deny",
         CTM_HAIKU)
ctm_case("a model id trailer, claude-haiku-5-5, from a Haiku agent passes", CTM_REPO_IDHAIKU, "allow", CTM_HAIKU)
ctm_case("an Opus trailer passes when a fallback served Sonnet and the agent requested Opus",
         CTM_REPO_INCIDENT, "allow", CTM_FALLBACK)
ctm_case("a Sonnet trailer passes when a fallback served Sonnet and the agent requested Opus",
         CTM_REPO_SONNET, "allow", CTM_FALLBACK)
ctm_case("a Haiku trailer is refused when a fallback served Sonnet and the agent requested Opus",
         CTM_REPO_HAIKU, "deny", CTM_FALLBACK)

# A push inside a shell wrapper is judged as the push it runs, so a wrapper cannot hide a push from the check.
ctm_case("a bash -c wrapped push of an Opus-trailer commit from a Haiku agent is refused", CTM_REPO_INCIDENT,
         "deny", CTM_HAIKU, command="bash -c 'git push origin HEAD:x'")
ctm_case("a sh -lc wrapped push of an Opus-trailer commit from a Haiku agent is refused", CTM_REPO_INCIDENT,
         "deny", CTM_HAIKU, command='sh -lc "git push origin HEAD:x"')

# Each push form that names a branch, or names none, is refused today. Pinned so that a parser change cannot let
# one of them pass by accident.
ctm_case("a push -u origin x of an Opus-trailer commit from a Haiku agent is refused", CTM_REPO_XBRANCH,
         "deny", CTM_HAIKU, command=VCS + " push -u origin x")
ctm_case("a push origin x of an Opus-trailer commit from a Haiku agent is refused", CTM_REPO_XBRANCH,
         "deny", CTM_HAIKU, command=VCS + " push origin x")
ctm_case("a bare git push of an Opus-trailer commit from a Haiku agent is refused", CTM_REPO_XBRANCH,
         "deny", CTM_HAIKU, command=VCS + " push")
ctm_case("a git push origin with no refspec of an Opus-trailer commit from a Haiku agent is refused",
         CTM_REPO_XBRANCH, "deny", CTM_HAIKU, command=VCS + " push origin")

# A name that is no model family the rule knows is not a model, so it passes. Otherwise a product or a tool named
# in a trailer would block every push that carries it.
ctm_case("a Claude 5.5 trailer from a Haiku agent passes", CTM_REPO_CLAUDE55, "allow", CTM_HAIKU)
ctm_case("a Claude Code 2.1 trailer from a Haiku agent passes", CTM_REPO_CLAUDECODE, "allow", CTM_HAIKU)
ctm_case("a GPT-4 trailer from a Haiku agent passes", CTM_REPO_GPT4, "allow", CTM_HAIKU)

# A [1m] suffix, a separator or a missing space does not hide the family or the version. Each name is judged as
# the model it names, so an Opus name in any of these spellings is refused from a Haiku agent.
ctm_case("a claude-opus-5-5[1m] trailer from a Haiku agent is refused", CTM_REPO_OPUS1M, "deny", CTM_HAIKU)
ctm_case("a Claude_Opus_5.5 trailer from a Haiku agent is refused", CTM_REPO_UNDERSCORE, "deny", CTM_HAIKU)
ctm_case("a Claude Opus4.5 trailer from a Haiku agent is refused", CTM_REPO_OPUS4, "deny", CTM_HAIKU)
ctm_case("a claude-haiku-5-5[1m] trailer from a Haiku agent passes", CTM_REPO_HAIKU1M, "allow", CTM_HAIKU)

# A family word after the version still names the model. Read only before the version, "Claude 3.5 Sonnet" would
# pass as no model at all, and an agent could commit under that name.
ctm_case("a Claude 3 Opus trailer from a Haiku agent is refused", CTM_REPO_CLAUDE3OPUS, "deny", CTM_HAIKU)
ctm_case("a Claude 3.5 Sonnet trailer from a Haiku agent is refused", CTM_REPO_CLAUDE35SONNET, "deny", CTM_HAIKU)
ctm_case("a Claude 3.5 Sonnet trailer from a Sonnet 5.5 agent is refused (same family, other version)",
         CTM_REPO_CLAUDE35SONNET, "deny", CTM_SONNET)
ctm_case("a Claude Sonnet trailer from a Sonnet 5.5 agent passes", CTM_REPO_CLAUDESONNET, "allow", CTM_SONNET)
ctm_case("a Claude 2.1 trailer from a Haiku agent passes (no family word)", CTM_REPO_CLAUDE21, "allow", CTM_HAIKU)

# A version that differs from the agent's is refused in every spelling, and a name that only carries a family word
# passes.
ctm_case("a claude-haiku-4-5 trailer from a Haiku 5.5 agent is refused", CTM_REPO_HAIKU45ID, "deny", CTM_HAIKU)
ctm_case("a Claude-Haiku-4.5 trailer from a Haiku 5.5 agent is refused", CTM_REPO_HAIKU45HYPHEN, "deny", CTM_HAIKU)
ctm_case("a Claude_Haiku_4.5 trailer from a Haiku 5.5 agent is refused", CTM_REPO_HAIKU45UNDER, "deny", CTM_HAIKU)
ctm_case("a Claude Haiku 5.4 trailer from a Haiku 5.5 agent is refused", CTM_REPO_HAIKU54, "deny", CTM_HAIKU)
ctm_case("a Jane <opus@example.com> trailer from a Haiku agent passes", CTM_REPO_JANE, "allow", CTM_HAIKU)
ctm_case("an Opusculum Jones trailer from a Haiku agent passes", CTM_REPO_OPUSCULUM, "allow", CTM_HAIKU)
ctm_case("a claude-haiku-5-4 trailer from a Haiku 5.5 agent is refused", CTM_REPO_HAIKU54ID, "deny", CTM_HAIKU)
ctm_case("a Claude 5-4 Haiku trailer from a Haiku 5.5 agent is refused", CTM_REPO_CLAUDE54HAIKU, "deny", CTM_HAIKU)
ctm_case("a Claude Code 2.1 trailer from a Haiku agent passes (no family word)", CTM_REPO_CLAUDECODE, "allow",
         CTM_HAIKU)
ctm_case("a GPT-4 trailer from a Haiku agent passes (no family word)", CTM_REPO_GPT4, "allow", CTM_HAIKU)

# Pin: a push wrapped by flock or in a command substitution is refused as the push it runs.
ctm_case("a flock-wrapped push of an Opus-trailer commit from a Haiku agent is refused", CTM_REPO_INCIDENT, "deny",
         CTM_HAIKU, command="flock /tmp/l git push origin HEAD:x")
ctm_case("a command-substituted push of an Opus-trailer commit from a Haiku agent is refused", CTM_REPO_INCIDENT,
         "deny", CTM_HAIKU, command="echo $(git push origin HEAD:x)")


