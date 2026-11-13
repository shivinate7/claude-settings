# section 15900
# =========================================================================== 5j. resume a finished reviewer
#
# Rule resume-finished-reviewer. A SendMessage from the main session, or from an agent (a payload with agent_id, whose
# spawn the parent's transcript holds), is refused when
# `to` names a spawn that has finished and either ran in a worktree (the Agent input isolation worktree, or, with no
# isolation input, the role's agent-file pin, any role: the worktree is gone once it finishes) or is a reviewer or
# design-reviewer,
# whose refusal is kept with no worktree. A finished spawn with no worktree that is not a reviewer is allowed.
# A Workflow agent has no spawn in the parent's transcript. Its run's journal, beside the transcript under
# subagents/workflows/<runId>/, holds its started line and, once it finishes, its result line. Its meta file holds the
# agentType, which is the role judged, and spawnedWithWorktree, true when it was spawned with isolation worktree.
# A Workflow agent has no Agent input, so its worktree is that flag or its role file's pin. A finished one with a
# worktree is refused for any role. Otherwise only a reviewer is refused. `to` names it by its agentId or by its
# started line's label. A finished one with no meta file has no role, so the send asks.
# A started-only Workflow agent (no result line) is finished when its run record beside the transcript,
# workflows/<runId>.json, says killed or completed.
# `to` resolves to a spawn by its launch result's toolUseResult.agentId, or by the spawn call's `name` input, and the
# latest spawn with that name wins. A background
# spawn is running while its launch result is async_launched and no later record holds a finish notice for its id.
# Any other result, a foreground spawn's included, is finished. A result of unknown shape asks. An errored spawn never
# ran, so it is skipped: the spawn before it governs, as review_log_hit skips it. The refusal says to
# spawn a fresh reviewer and pass it the prior report (rule roles-resume-by-name). Each transcript also holds the
# round's review log after its reviewer spawn, so review-log-after-round does not refuse first.
FAMILY = "resume-finished-reviewer"
RF_RULE = "resume-finished-reviewer"
RF_CARRIES = ("fresh reviewer", "prior report")
RF_MSG = "Round 2: fix the findings on PR #12."
RF_REVIEW, RF_REVIEW_AGENT = "reviewer-pr12", "a7c1e9d04b2f3a58"
RF_DESIGN, RF_DESIGN_AGENT = "design-reviewer-pr12", "a2d9f4b8e1c6073d"
RF_BUILDER, RF_BUILDER_AGENT = "builder-pr12", "b3e8f1a6c92d7e40"
RF_OTHER, RF_OTHER_AGENT = "builder-pr13", "b5d0a7c3e91f2468"
RF_SHARED = "worker-pr12"
RF_SHARED_REVIEWER_AGENT, RF_SHARED_BUILDER_AGENT = "a9f2c6e1d7b04385", "b1c4e8a2f7d93056"
RF_UNKNOWN = "reviewer-pr14"
RF_WT_UNKNOWN, RF_WT_UNKNOWN_AGENT = "builder-pr35", "b4d7e2a9f1c63058"
RF_WT_LIVE, RF_WT_LIVE_AGENT = "builder-pr36", "b6e1c8f3a9d27540"
RF_CASE_LOWER, RF_CASE_LOWER_AGENT = "reviewer-pr37", "a7f0d5b2e8c39416"
RF_CASE_CAP, RF_CASE_CAP_AGENT = "reviewer-pr38", "a1e6c9f4d2b87053"
RF_NOTICE, RF_NOTICE_AGENT = "reviewer-pr15", "a4e7b0d3c9f15862"
RF_TASKID, RF_TASKID_AGENT = "reviewer-pr16", "a6f3d9c2e8b14750"
RF_STOPPED, RF_STOPPED_AGENT = "reviewer-pr17", "a8e4b1d7f2c90316"
RF_FOREGROUND, RF_FOREGROUND_AGENT = "reviewer-pr18", "a0c7e5f9b3d16428"
RF_ERRORED = "reviewer-pr19"
RF_RUNNING, RF_RUNNING_AGENT = "reviewer-pr20", "a3b8d0e6f4c17295"
RF_ERR_FINISHED, RF_ERR_FINISHED_AGENT = "reviewer-pr21", "a5d8c3f1e7b20964"
RF_ERR_RUNNING, RF_ERR_RUNNING_AGENT = "reviewer-pr22", "a6e9d4a2f8c31075"
RF_MALFORMED = "reviewer-pr23"
# Spawns that ran in a worktree (the Agent input's isolation worktree), each of another role, and a finished Explore
# that ran with no worktree.
RF_WT_BUILDER, RF_WT_BUILDER_AGENT = "builder-pr24", "b9c4e2f7a1d38605"
RF_WT_RUNNING, RF_WT_RUNNING_AGENT = "builder-pr25", "b0e6d3a8f5c17924"
RF_WT_TESTAUTHOR, RF_WT_TESTAUTHOR_AGENT = "test-author-pr26", "c8d1f5a2e9b07364"
RF_WT_DESIGNER, RF_WT_DESIGNER_AGENT = "designer-pr27", "d6b3e9a1f4c28750"
RF_EXPLORE, RF_EXPLORE_AGENT = "explore-pr28", "e4f1c8a3d7b29065"
# Spawns with no isolation input: a record-writer and a test-author, whose agent files pin a worktree, and a Plan, whose
# agent file pins none.
RF_RW, RF_RW_AGENT = "record-writer-pr30", "c2e9a4d7f1b08356"
RF_TA, RF_TA_AGENT = "test-author-pr31", "c6f1b8e3d9a27054"
RF_PLAN, RF_PLAN_AGENT = "plan-pr32", "f7b2d9e4a1c60835"
# A Plan spawned with isolation remote, and a builder spawned with an empty isolation input. Each sets its isolation
# input, so the role's pin is not what decides.
RF_REMOTE_PLAN, RF_REMOTE_PLAN_AGENT = "plan-remote-pr33", "d3a8f6c1e9b47205"
RF_EMPTY_BUILDER, RF_EMPTY_BUILDER_AGENT = "builder-empty-pr34", "e9f2b5d7a4c18036"
# A reviewer named `rev`. A `to` in the `name [ref]` form names it by that name and by the first eight hex of its id.
RF_REV, RF_REV_AGENT = "rev", "a5eb5d25c7e90b41"
# A record the reader cannot parse: a user record whose message is a string, not an object.
RF_UNPARSED = json.dumps({"type": "user", "message": "a message that is a string, not a record"})
RF_DIR = os.path.join(ROOT, "resumefinished")
# A config folder whose global rules name the real checkout (REPO), so the guard reads the owner's agent files there,
# as the role-model rule does. The cases that read a pin run under it. role_config builds the same folder, but the
# role-model section defines it after this one, so this section writes its own.
RF_POINTER = os.path.join(ROOT, "resumefinished-pointer")


def write_rf_pointer():
    write(os.path.join(RF_POINTER, "CLAUDE.md"), "@%s/CLAUDE.md\n" % slash(REPO))


def rf_path(name):
    return os.path.join(RF_DIR, name + ".jsonl")


def rf_launch_result(tool_id, agent_id):
    """A background spawn's launch result: async_launched, its agent id at toolUseResult.agentId on the record."""
    record = json.loads(role_result(tool_id, "Async agent launched successfully."))
    record["toolUseResult"] = {"status": "async_launched", "agentId": agent_id}
    return json.dumps(record)


def rf_launch(tool_id, subagent_type, name, agent_id, isolation=None):
    """A background spawn named `name`, and its launch result. `isolation` is the Agent input's isolation, if any."""
    return rr_spawn(tool_id, subagent_type, name=name, result=rf_launch_result(tool_id, agent_id), isolation=isolation)


def rf_launch_unknown(tool_id, subagent_type, name, isolation=None):
    """A background spawn named `name` whose launch result holds a bare string as toolUseResult, so its state is
    not readable from the record."""
    record = json.loads(role_result(tool_id, "Async agent launched successfully."))
    record["toolUseResult"] = "Async agent launched successfully."
    return rr_spawn(tool_id, subagent_type, name=name, result=json.dumps(record), isolation=isolation)


def rf_finish(tool_id, kind="queue-operation", status="completed", task_id=None):
    """The finish notice of background spawn `tool_id`, in the record type it arrives as: a queue-operation or an
    attachment. Its text names the tool use and a status, as the real notice does. `tool_id` None, with `task_id` (the
    agent id), gives a notice that names the spawn by its agent id alone."""
    lines = []
    if task_id is not None:
        lines.append("<task-id>%s</task-id>" % task_id)
    if tool_id is not None:
        lines.append("<tool-use-id>%s</tool-use-id>" % tool_id)
    lines.append("<status>%s</status>" % status)
    text = "<task-notification>\n" + "\n".join(lines) + "\n</task-notification>"
    if kind == "attachment":
        return [json.dumps({"type": "attachment", "attachment": {"type": "queued_command", "prompt": text}})]
    return [json.dumps({"type": "queue-operation", "operation": "enqueue", "content": text})]


def rf_notice_no_status(tool_id):
    """A task notice that names the tool use and carries no <status>: the spawn's state is not known from it."""
    text = "<task-notification>\n<tool-use-id>%s</tool-use-id>\n</task-notification>" % tool_id
    return [json.dumps({"type": "queue-operation", "operation": "enqueue", "content": text})]


def rf_stop(tool_id, agent_id):
    """A TaskStop call on background spawn `agent_id`, and its result: the JSON text a stop returns, whose message
    starts 'Successfully stopped task:' and names the agent id."""
    body = json.dumps({"message": "Successfully stopped task: %s (reviewer)" % agent_id, "task_id": agent_id})
    return [role_use(tool_id, "TaskStop", {"task_id": agent_id}), role_result(tool_id, body)]


def rf_foreground(tool_id, subagent_type, name, agent_id, status):
    """A foreground spawn named `name`: its result is the plain text, and its toolUseResult is a dict that holds
    `status` and the agent id, as a spawn that ran to its end records it."""
    record = json.loads(role_result(tool_id, "Verdict: PASS."))
    record["toolUseResult"] = {"status": status, "agentId": agent_id}
    return rr_spawn(tool_id, subagent_type, name=name, result=json.dumps(record))


# A Workflow run, whose folder sits beside the workflow-agents transcript. Each agent: its agentId (a 17-hex id, as the
# real journal holds them), its label, its phase, its meta agentType, and whether it finished.
RF_WF_RUN = "wf_5c2e8a1f-7b3"
RF_WF_DONE_AGENT, RF_WF_REVIEW_AGENT, RF_WF_RUNNING_AGENT = "e6a1c9d5b3f72804c", "d4b8f0e2a6c97315e", "b7e2a9c4d1f08836a"
RF_WF_AGENTS = [
    (RF_WF_DONE_AGENT, "scan-finished", "Scan", "workflow-subagent", True),
    (RF_WF_REVIEW_AGENT, "review-finished", "Review", "reviewer", True),
    (RF_WF_RUNNING_AGENT, "review-running", "Review", "reviewer", False),
]
# A second run, whose one finished agent has no meta file, so its agentType is not known.
RF_WF_NOMETA_RUN = "wf_0a7d3e9b-4c1"
RF_WF_NOMETA_AGENT = "f2c8e5a1d7b09346d"
RF_WF_NOMETA_AGENTS = [(RF_WF_NOMETA_AGENT, "meta-missing", "Review", None, True)]
# A run whose agents are workflow-subagent agents spawned with isolation worktree: their meta holds spawnedWithWorktree and a
# worktreePath, as the probe measured it (wf_19ac2aae-ebb). A finished one with those keys is refused, a running one
# with them passes, and a finished one with no worktree keys passes (the control).
RF_WF_WT_RUN = "wf_7d3a1f0c-9e2"
RF_WF_WT_AGENT, RF_WF_WT_RUNNING_AGENT, RF_WF_NOKEYS_AGENT = "a1d4c7e0b9f25683e", "c5e9b2f7a0d13846d", "f0b6d3a9e4c17258b"
RF_WF_WT_PATH = os.path.join(ROOT, "rf-worktrees", "wf_7d3a1f0c-9e2-1")
RF_WF_WT_KEYS = {"spawnedWithWorktree": True, "worktreePath": RF_WF_WT_PATH}
RF_WF_WT_AGENTS = [
    (RF_WF_WT_AGENT, "scan-worktree", "Scan", "workflow-subagent", True),
    (RF_WF_WT_RUNNING_AGENT, "scan-worktree-running", "Scan", "workflow-subagent", False),
    (RF_WF_NOKEYS_AGENT, "scan-no-worktree", "Scan", "workflow-subagent", True),
]
RF_WF_WT_EXTRA = {RF_WF_WT_AGENT: RF_WF_WT_KEYS, RF_WF_WT_RUNNING_AGENT: RF_WF_WT_KEYS}
# A reviewer stopped with TaskStop leaves a started line and no result line. Its run record beside the transcript
# (workflows/<runId>.json) names the run's status: killed when stopped, completed when finished. A run with no record
# is still running. The notype run's agent is finished, with a worktree flag and no agentType in its meta.
RF_WF_KILLED_RUN, RF_WF_KILLED_AGENT = "wf_6e1b9d3a-0c8", "c7a3e9f1d5b20846e"
RF_WF_COMPLETED_RUN, RF_WF_COMPLETED_AGENT = "wf_8f2d4b6a-e91", "a2e8c5f0b7d31964c"
RF_WF_NORECORD_RUN, RF_WF_NORECORD_AGENT = "wf_1c7e5a9d-f34", "e5b0d8a3c6f97412a"
RF_WF_NOTYPE_RUN, RF_WF_NOTYPE_AGENT = "wf_3d6a0e8c-b27", "f9c4a1e7d2b68053b"
RF_WF_KILLED_AGENTS = [(RF_WF_KILLED_AGENT, "review-killed", "Review", "reviewer", False)]
RF_WF_COMPLETED_AGENTS = [(RF_WF_COMPLETED_AGENT, "review-completed", "Review", "reviewer", False)]
RF_WF_NORECORD_AGENTS = [(RF_WF_NORECORD_AGENT, "review-no-record", "Review", "reviewer", False)]
RF_WF_NOTYPE_AGENTS = [(RF_WF_NOTYPE_AGENT, "scan-no-type", "Scan", None, True)]
RF_WF_NOTYPE_EXTRA = {RF_WF_NOTYPE_AGENT: RF_WF_WT_KEYS}
# A run whose journal cannot be read: its journal.jsonl is a folder, so the guard's open() fails on it. The journal
# holds no agent, so the target is named by no readable journal.
RF_WF_UNREADABLE_RUN = "wf_9b2c6e4a-1f7"
RF_WF_UNREADABLE_AGENT = "d8f0a3c6e2b91574f"


def rf_workflow_launch(transcript_name, run):
    """A Workflow launch and its result, as a list of lines. The launched text names the run's folder beside the
    transcript `transcript_name`, as the real one does."""
    return [role_use("w1", "Workflow", {"script": "phase('Scan')\nconst s = await agent('Scan the pull request.', "
                                                  "{ label: 'scan-finished' })\nreturn s"}),
            role_result("w1", "Workflow launched in background. Task ID: wo5r8k1x3\nTranscript dir: %s"
                        % os.path.join(RF_DIR, transcript_name, "subagents", "workflows", run))]


RF_TRANSCRIPTS = {
    # A worktree builder whose launch result holds a bare string, so its agent id is not in the record, and whose
    # finish notice names that id. A running worktree builder beside it, its agent id in its launch result.
    "worktree-builder-unknown-result-finished": rr_session(
        rf_launch_unknown("b1", "builder", RF_WT_UNKNOWN, isolation="worktree"),
        rf_finish("b1", task_id=RF_WT_UNKNOWN_AGENT),
        rf_launch("b2", "builder", RF_WT_LIVE, RF_WT_LIVE_AGENT, isolation="worktree")),
    # Two background reviewers that finished: the first spawned as `reviewer`, the second as `Reviewer`. Each is
    # followed by its round's review log.
    "bg-reviewer-case-pair-finished": rr_session(
        rf_launch("r1", "reviewer", RF_CASE_LOWER, RF_CASE_LOWER_AGENT), rf_finish("r1"),
        rr_comment("c1", rr_record(1)),
        rf_launch("r2", "Reviewer", RF_CASE_CAP, RF_CASE_CAP_AGENT), rf_finish("r2"),
        rr_comment("c2", rr_record(2))),
    # A background reviewer that finished: its launch result, its finish notice, then the round's record.
    "bg-reviewer-finished": rr_session(rf_launch("r1", "reviewer", RF_REVIEW, RF_REVIEW_AGENT),
                                       rf_finish("r1"), rr_comment("c1", rr_record())),
    # A foreground reviewer: its result is the plain tool_result, with no launch record.
    "fg-reviewer-finished": rr_session(rr_spawn("r1", "reviewer", name=RF_REVIEW),
                                       rr_comment("c1", rr_record())),
    # A background design-reviewer whose finish notice is an attachment record.
    "bg-design-reviewer-finished": rr_session(rf_launch("d1", "design-reviewer", RF_DESIGN, RF_DESIGN_AGENT),
                                              rf_finish("d1", "attachment"), rr_comment("c1", rr_record())),
    # The reviewer still runs. A builder spawned after it finished, so a notice for another id is in the transcript.
    "bg-reviewer-running": rr_session(rf_launch("r1", "reviewer", RF_REVIEW, RF_REVIEW_AGENT),
                                      rr_comment("c1", rr_record()),
                                      rf_launch("b1", "builder", RF_OTHER, RF_OTHER_AGENT), rf_finish("b1")),
    # A reviewer and a builder, both finished, under different names.
    "builder-finished": rr_session(rf_launch("r1", "reviewer", RF_REVIEW, RF_REVIEW_AGENT),
                                   rf_finish("r1"), rr_comment("c1", rr_record()),
                                   rf_launch("b1", "builder", RF_BUILDER, RF_BUILDER_AGENT), rf_finish("b1")),
    # Two spawns share one name: the older a finished reviewer, the newer a running builder.
    "shared-name-finished-reviewer-then-running-builder": rr_session(
        rf_launch("r1", "reviewer", RF_SHARED, RF_SHARED_REVIEWER_AGENT), rf_finish("r1"),
        rr_comment("c1", rr_record()),
        rf_launch("b1", "builder", RF_SHARED, RF_SHARED_BUILDER_AGENT)),
    # The same two spawns in the reverse order: the older a running builder, the newer a finished reviewer.
    "shared-name-running-builder-then-finished-reviewer": rr_session(
        rf_launch("b1", "builder", RF_SHARED, RF_SHARED_BUILDER_AGENT),
        rf_launch("r1", "reviewer", RF_SHARED, RF_SHARED_REVIEWER_AGENT), rf_finish("r1"),
        rr_comment("c1", rr_record())),
    # A finished reviewer far up a transcript of about a megabyte: the reader must still reach its spawn.
    "long-reviewer-finished": rr_session(rf_launch("r1", "reviewer", RF_REVIEW, RF_REVIEW_AGENT), RR_FILLER,
                                         rf_finish("r1"), rr_comment("c1", rr_record())),
    # A reviewer whose launch result holds a bare string, so its state cannot be read.
    "reviewer-unknown-result": rr_session(rf_launch_unknown("r1", "reviewer", RF_UNKNOWN),
                                          rr_comment("c1", rr_record())),
    # A reviewer whose notice names its id with no status.
    "reviewer-notice-no-status": rr_session(rf_launch("r1", "reviewer", RF_NOTICE, RF_NOTICE_AGENT),
                                            rf_notice_no_status("r1"), rr_comment("c1", rr_record())),
    # A background reviewer whose finish notice names only its agent id: no tool-use id in the notice.
    "bg-reviewer-agent-id-notice": rr_session(rf_launch("r1", "reviewer", RF_TASKID, RF_TASKID_AGENT),
                                              rf_finish(None, task_id=RF_TASKID_AGENT),
                                              rr_comment("c1", rr_record())),
    # A background reviewer that a TaskStop closed: the stop's result names its agent id.
    "bg-reviewer-stopped": rr_session(rf_launch("r1", "reviewer", RF_STOPPED, RF_STOPPED_AGENT),
                                      rf_stop("s1", RF_STOPPED_AGENT), rr_comment("c1", rr_record())),
    # A foreground reviewer whose toolUseResult carries a terminal status.
    "fg-reviewer-status-completed": rr_session(
        rf_foreground("r1", "reviewer", RF_FOREGROUND, RF_FOREGROUND_AGENT, "completed"),
        rr_comment("c1", rr_record())),
    # A reviewer whose spawn result is an error: the spawn did not run, and the result has no toolUseResult.
    "reviewer-spawn-errored": rr_session(rr_spawn_error("r1", "reviewer", name=RF_ERRORED),
                                         rr_comment("c1", rr_record())),
    # A background reviewer whose finish notice says it is still running.
    "reviewer-notice-running": rr_session(rf_launch("r1", "reviewer", RF_RUNNING, RF_RUNNING_AGENT),
                                          rf_finish("r1", status="running"), rr_comment("c1", rr_record())),
    # A reviewer that finished, then a spawn of the same name whose result is an error: that spawn never ran.
    "finished-then-errored-spawn": rr_session(
        rf_launch("r1", "reviewer", RF_ERR_FINISHED, RF_ERR_FINISHED_AGENT), rf_finish("r1"),
        rr_comment("c1", rr_record()), rr_spawn_error("r2", "reviewer", name=RF_ERR_FINISHED)),
    # A reviewer still running, then a spawn of the same name whose result is an error.
    "running-then-errored-spawn": rr_session(
        rf_launch("r1", "reviewer", RF_ERR_RUNNING, RF_ERR_RUNNING_AGENT), rr_comment("c1", rr_record()),
        rr_spawn_error("r2", "reviewer", name=RF_ERR_RUNNING)),
    # A reviewer named `rev` that finished, and one that runs, each with the round's review log after its spawn.
    "bg-rev-finished": rr_session(rf_launch("r1", "reviewer", RF_REV, RF_REV_AGENT), rf_finish("r1"),
                                  rr_comment("c1", rr_record())),
    "bg-rev-running": rr_session(rf_launch("r1", "reviewer", RF_REV, RF_REV_AGENT),
                                 rr_comment("c1", rr_record())),
    # A builder that ran in a worktree and finished, with no reviewer in the session.
    "worktree-builder-finished": rr_session(
        rf_launch("b1", "builder", RF_WT_BUILDER, RF_WT_BUILDER_AGENT, isolation="worktree"), rf_finish("b1")),
    # A builder that ran in a worktree and still runs: its launch result, and no finish notice.
    "worktree-builder-running": rr_session(
        rf_launch("b1", "builder", RF_WT_RUNNING, RF_WT_RUNNING_AGENT, isolation="worktree")),
    "worktree-test-author-finished": rr_session(
        rf_launch("t1", "test-author", RF_WT_TESTAUTHOR, RF_WT_TESTAUTHOR_AGENT, isolation="worktree"),
        rf_finish("t1")),
    "worktree-designer-finished": rr_session(
        rf_launch("d1", "designer", RF_WT_DESIGNER, RF_WT_DESIGNER_AGENT, isolation="worktree"), rf_finish("d1")),
    # An Explore that finished and ran with no worktree.
    "explore-finished": rr_session(rf_launch("e1", "Explore", RF_EXPLORE, RF_EXPLORE_AGENT), rf_finish("e1")),
    # A record-writer, a test-author and a Plan that finished, each with no isolation input.
    "record-writer-finished": rr_session(rf_launch("w1", "record-writer", RF_RW, RF_RW_AGENT), rf_finish("w1")),
    "test-author-finished": rr_session(rf_launch("t1", "test-author", RF_TA, RF_TA_AGENT), rf_finish("t1")),
    "plan-finished": rr_session(rf_launch("p1", "Plan", RF_PLAN, RF_PLAN_AGENT), rf_finish("p1")),
    # A Plan that ran with isolation remote, and a builder whose isolation input is empty: both finished.
    "remote-plan-finished": rr_session(
        rf_launch("p1", "Plan", RF_REMOTE_PLAN, RF_REMOTE_PLAN_AGENT, isolation="remote"), rf_finish("p1")),
    "builder-empty-isolation-finished": rr_session(
        rf_launch("b1", "builder", RF_EMPTY_BUILDER, RF_EMPTY_BUILDER_AGENT, isolation=""), rf_finish("b1")),
    # An agent's own send. Each sender is the running builder spawned in the transcript, so the payload's agent_id is
    # that spawn's agentId, as the probe measured it.
    "agent-sender-finished-reviewer": rr_session(
        rf_launch("r1", "reviewer", RF_REVIEW, RF_REVIEW_AGENT), rf_finish("r1"), rr_comment("c1", rr_record()),
        rf_launch("b1", "builder", RF_OTHER, RF_OTHER_AGENT)),
    "agent-sender-running-reviewer": rr_session(
        rf_launch("r1", "reviewer", RF_REVIEW, RF_REVIEW_AGENT), rr_comment("c1", rr_record()),
        rf_launch("b1", "builder", RF_OTHER, RF_OTHER_AGENT)),
    "agent-sender-finished-worktree": rr_session(
        rf_launch("b1", "builder", RF_WT_BUILDER, RF_WT_BUILDER_AGENT, isolation="worktree"), rf_finish("b1"),
        rf_launch("b2", "builder", RF_OTHER, RF_OTHER_AGENT, isolation="worktree")),
    # A Workflow run, whose folder sits beside this transcript (write_rf_workflow). Its launch result names the run's
    # folder, as the real one does. The run leaves no spawn in this transcript.
    "workflow-agents": rr_session(rf_workflow_launch("workflow-agents", RF_WF_RUN)),
    # A builder spawned in the transcript, still running, then a Workflow run. An agent's send to a Workflow agent
    # carries the builder's agentId, which this transcript holds as the spawn's id.
    "workflow-agent-sender": rr_session(rf_launch("b1", "builder", RF_OTHER, RF_OTHER_AGENT),
                                        rf_workflow_launch("workflow-agent-sender", RF_WF_RUN)),
    # A Workflow run whose one agent has a result line and no meta file.
    "workflow-no-meta": rr_session(rf_workflow_launch("workflow-no-meta", RF_WF_NOMETA_RUN)),
    # A builder spawned in the transcript, still running, then a Workflow run whose agents were spawned with isolation
    # worktree (RF_WF_WT_RUN). The builder is the sender of the agent cases.
    "workflow-worktree": rr_session(rf_launch("b1", "builder", RF_OTHER, RF_OTHER_AGENT),
                                    rf_workflow_launch("workflow-worktree", RF_WF_WT_RUN)),
    # A reviewer stopped with TaskStop, and one whose run finished: each run record says so. A run with no record,
    # and a run whose agent is finished with a worktree flag and no agentType.
    "workflow-killed": rr_session(rf_workflow_launch("workflow-killed", RF_WF_KILLED_RUN)),
    "workflow-completed": rr_session(rf_workflow_launch("workflow-completed", RF_WF_COMPLETED_RUN)),
    "workflow-norecord": rr_session(rf_workflow_launch("workflow-norecord", RF_WF_NORECORD_RUN)),
    "workflow-notype": rr_session(rf_workflow_launch("workflow-notype", RF_WF_NOTYPE_RUN)),
    # A Workflow run whose journal cannot be read (write_rf_transcripts makes its journal a folder).
    "workflow-unreadable": rr_session(rf_workflow_launch("workflow-unreadable", RF_WF_UNREADABLE_RUN)),
    # No spawn at all: the empty state.
    "no-spawn": rr_session(),
}


def write_rf_workflow(transcript_name, run, agents, meta_extra=None):
    """A Workflow run's folder beside the transcript `transcript_name`: the journal, a launched line, then a started line
    for each agent and a result line for each one that finished, and one meta file per agent, holding its agentType.
    An agent whose agentType is None has no meta file, unless `meta_extra` gives it keys: then its meta holds those
    keys alone. `meta_extra` maps an agent id to more meta keys, such as the
    worktree keys of an agent spawned with isolation worktree."""
    folder = os.path.join(RF_DIR, transcript_name, "subagents", "workflows", run)
    lines = [json.dumps({"type": "launched"})]
    for agent_id, label, phase, agent_type, finished in agents:
        key = "v2:" + hashlib.sha256(agent_id.encode("utf-8")).hexdigest()
        lines.append(json.dumps({"type": "started", "key": key, "agentId": agent_id, "label": label, "phase": phase}))
        if finished:
            lines.append(json.dumps({"type": "result", "key": key, "agentId": agent_id, "result": "done",
                                     "toolsUsed": ["Bash"]}))
        extra = (meta_extra or {}).get(agent_id, {})
        if agent_type is not None or extra:
            meta = {"agentType": agent_type, "model": "sonnet"} if agent_type is not None else {"model": "sonnet"}
            meta.update(extra)
            write(os.path.join(folder, "agent-%s.meta.json" % agent_id), json.dumps(meta))
    write(os.path.join(folder, "journal.jsonl"), "\n".join(lines) + "\n")


def write_rf_run_record(transcript_name, run, status):
    """A Workflow run's record beside the transcript `transcript_name`, at <transcript minus .jsonl>/workflows/<runId>.json,
    a sibling of subagents/. It holds the keys the probe's record holds, with fixture values: the run's id, name, status,
    result and counts. A stopped run (status killed) holds an error and a null result; a finished one holds its result."""
    record = {"runId": run, "workflowName": "review-run", "status": status, "agentCount": 1, "logs": [],
              "phases": [{"title": "Review"}], "durationMs": 5542, "startTime": 1794157505311,
              "timestamp": "2026-11-08T17:05:10.864Z", "result": None if status == "killed" else "done"}
    if status == "killed":
        record["error"] = "Error: Workflow aborted"
    write(os.path.join(RF_DIR, transcript_name, "workflows", run + ".json"), json.dumps(record))


def write_rf_transcripts():
    write_transcripts(RF_TRANSCRIPTS, RF_DIR)
    write_rf_workflow("workflow-agents", RF_WF_RUN, RF_WF_AGENTS)
    write_rf_workflow("workflow-agent-sender", RF_WF_RUN, RF_WF_AGENTS)
    write_rf_workflow("workflow-no-meta", RF_WF_NOMETA_RUN, RF_WF_NOMETA_AGENTS)
    write_rf_workflow("workflow-worktree", RF_WF_WT_RUN, RF_WF_WT_AGENTS, RF_WF_WT_EXTRA)
    write_rf_workflow("workflow-killed", RF_WF_KILLED_RUN, RF_WF_KILLED_AGENTS)
    write_rf_run_record("workflow-killed", RF_WF_KILLED_RUN, "killed")
    write_rf_workflow("workflow-completed", RF_WF_COMPLETED_RUN, RF_WF_COMPLETED_AGENTS)
    write_rf_run_record("workflow-completed", RF_WF_COMPLETED_RUN, "completed")
    write_rf_workflow("workflow-norecord", RF_WF_NORECORD_RUN, RF_WF_NORECORD_AGENTS)
    write_rf_workflow("workflow-notype", RF_WF_NOTYPE_RUN, RF_WF_NOTYPE_AGENTS, RF_WF_NOTYPE_EXTRA)
    # The journal is a folder, so the guard's open() fails on it, as the role transcript's `unreadable` folder does.
    os.makedirs(os.path.join(RF_DIR, "workflow-unreadable", "subagents", "workflows", RF_WF_UNREADABLE_RUN,
                             "journal.jsonl"), exist_ok=True)


# `missing` is never written: the guard's read of it fails, and the rule allows.
lazy_fixture([rf_path(name) for name in RF_TRANSCRIPTS], write_rf_transcripts)
lazy_fixture([RF_POINTER], write_rf_pointer)


def rf_refuse(name, tool_input, transcript, agent_id=None, carries=RF_CARRIES, config=None, agent_type=None):
    """A SendMessage the guard refuses for the rule: the reason names the rule and each fragment in `carries`
    (by default a fresh reviewer and the prior report, the reviewer wording). `agent_id` and `agent_type` make it an
    agent's send."""
    add("resume-finished-reviewer: " + name, "deny", rule=RF_RULE, tool=RR_BUILTIN_SEND, cwd=NOGIT,
        transcript=transcript, carries=carries, agent_id=agent_id, agent_type=agent_type, env=ROLE_ENV, config=config,
        **tool_input)


def rf_allow(name, tool_input, transcript, agent_id=None, config=None, agent_type=None):
    """A SendMessage the guard lets through silently. `agent_id` and `agent_type` make it an agent's send."""
    add("resume-finished-reviewer: " + name, "allow", tool=RR_BUILTIN_SEND, cwd=NOGIT, transcript=transcript,
        silent=True, agent_id=agent_id, agent_type=agent_type, env=ROLE_ENV, config=config, **tool_input)


def rf_ask(name, tool_input, transcript):
    """A SendMessage the guard holds for the owner: the reason names the rule."""
    add("resume-finished-reviewer: " + name, "ask", rule=RF_RULE, tool=RR_BUILTIN_SEND, cwd=NOGIT,
        transcript=transcript, env=ROLE_ENV, **tool_input)


# Refused: the target is a reviewer or design-reviewer spawn that has finished.
rf_refuse("a finished background reviewer, named by its agent id, is refused",
          {"to": RF_REVIEW_AGENT, "message": RF_MSG}, rf_path("bg-reviewer-finished"))
rf_refuse("a finished background reviewer, named by its spawn name, is refused",
          {"to": RF_REVIEW, "message": RF_MSG}, rf_path("bg-reviewer-finished"))
rf_refuse("a finished foreground reviewer, named by its spawn name, is refused",
          {"to": RF_REVIEW, "message": RF_MSG}, rf_path("fg-reviewer-finished"))
# A finished agent is resumed by a fresh agent of the same role, so a finished design-reviewer's refusal names a
# fresh design-reviewer, not a fresh reviewer.
rf_refuse("a finished design-reviewer, named by its spawn name, is refused, and the reason says fresh design-reviewer",
          {"to": RF_DESIGN, "message": RF_MSG}, rf_path("bg-design-reviewer-finished"),
          carries=("fresh design-reviewer", "prior report"))
rf_refuse("a finished reviewer far up a long transcript is refused",
          {"to": RF_REVIEW, "message": RF_MSG}, rf_path("long-reviewer-finished"))
rf_refuse("the latest spawn with the name wins: an older running builder, then a newer finished reviewer, is refused",
          {"to": RF_SHARED, "message": RF_MSG}, rf_path("shared-name-running-builder-then-finished-reviewer"))
rf_refuse("a finish notice that names only the agent id, with no tool-use id, is refused",
          {"to": RF_TASKID_AGENT, "message": RF_MSG}, rf_path("bg-reviewer-agent-id-notice"))
rf_refuse("a reviewer that a TaskStop closed is refused",
          {"to": RF_STOPPED_AGENT, "message": RF_MSG}, rf_path("bg-reviewer-stopped"))
rf_refuse("a foreground reviewer whose toolUseResult carries a terminal status is refused",
          {"to": RF_FOREGROUND, "message": RF_MSG}, rf_path("fg-reviewer-status-completed"))
# A finished agent that ran in a worktree is refused a resume, for any
# role, since its worktree is gone. An isolation input that is set decides. When it is absent, the role's agent file
# decides: agents/builder.md, test-author.md and record-writer.md pin a worktree, so their spawns ran in one. Reviewers
# are refused whatever their isolation.
rf_refuse("a finished builder spawned with isolation worktree is refused, and the reason says fresh builder",
          {"to": RF_WT_BUILDER, "message": RF_MSG}, rf_path("worktree-builder-finished"), carries=("fresh builder",))
rf_refuse("a finished test-author spawned with isolation worktree is refused, and the reason says fresh test-author",
          {"to": RF_WT_TESTAUTHOR, "message": RF_MSG}, rf_path("worktree-test-author-finished"),
          carries=("fresh test-author",))
rf_refuse("a finished designer spawned with isolation worktree is refused, and the reason says fresh designer",
          {"to": RF_WT_DESIGNER, "message": RF_MSG}, rf_path("worktree-designer-finished"), carries=("fresh designer",))
rf_refuse("a finished reviewer spawned with no isolation is refused: the reviewer refusal is kept with no worktree",
          {"to": RF_REVIEW, "message": RF_MSG}, rf_path("bg-reviewer-finished"))
# The pin is read from the real checkout (RF_POINTER), so each of these runs under it. Each has no isolation input.
rf_refuse("a finished builder with no isolation input is refused: agents/builder.md pins a worktree",
          {"to": RF_BUILDER, "message": RF_MSG}, rf_path("builder-finished"), carries=("fresh builder",),
          config=RF_POINTER)
rf_refuse("a finished record-writer with no isolation input is refused: agents/record-writer.md pins a worktree",
          {"to": RF_RW, "message": RF_MSG}, rf_path("record-writer-finished"), carries=("fresh record-writer",),
          config=RF_POINTER)
rf_refuse("a finished test-author with no isolation input is refused: agents/test-author.md pins a worktree",
          {"to": RF_TA, "message": RF_MSG}, rf_path("test-author-finished"), carries=("fresh test-author",),
          config=RF_POINTER)
# The input is set to remote, which leaves no local tree after the run, so it is refused as a worktree is. Plan's
# pin is none: the input alone decides.
rf_refuse("a finished Plan spawned with isolation remote is refused: remote leaves no tree, and the Plan pins none",
          {"to": RF_REMOTE_PLAN, "message": RF_MSG}, rf_path("remote-plan-finished"), carries=("fresh Plan",),
          config=RF_POINTER)
# Allowed: the target runs, is a finished spawn with no worktree that is not a reviewer, is not in the transcript,
# or the send is not the main session's.
rf_allow("a running reviewer is allowed, though another spawn's finish notice is in the transcript",
         {"to": RF_REVIEW, "message": RF_MSG}, rf_path("bg-reviewer-running"))
rf_allow("a finished Plan with no isolation input passes: agents/plan.md pins no isolation",
         {"to": RF_PLAN, "message": RF_MSG}, rf_path("plan-finished"), config=RF_POINTER)
# The input is set, even empty, so the builder's worktree pin is not read: a set input that is not worktree passes.
rf_allow("a finished builder spawned with an empty isolation input passes: the set input beats the worktree pin",
         {"to": RF_EMPTY_BUILDER, "message": RF_MSG}, rf_path("builder-empty-isolation-finished"), config=RF_POINTER)
rf_allow("a running builder spawned with isolation worktree passes",
         {"to": RF_WT_RUNNING, "message": RF_MSG}, rf_path("worktree-builder-running"))
rf_allow("a finished Explore spawned with no isolation passes",
         {"to": RF_EXPLORE, "message": RF_MSG}, rf_path("explore-finished"))
rf_allow("the latest spawn with the name wins: an older finished reviewer, then a newer running builder, is allowed",
         {"to": RF_SHARED, "message": RF_MSG}, rf_path("shared-name-finished-reviewer-then-running-builder"))
rf_allow("a send to main is allowed", {"to": "main", "message": RF_MSG}, rf_path("bg-reviewer-finished"))
rf_allow("a name that matches no spawn (a peer session) is allowed",
         {"to": "session-peer-pr9", "message": RF_MSG}, rf_path("bg-reviewer-finished"))
# Controls for the agent cases below: a main-session send to the same finished spawns on the same transcripts. The old
# code already refuses these, so each shows the transcript reads as finished, and a red agent case is the guard's.
rf_refuse("control: a main-session send to a finished reviewer on the sender transcript is refused",
          {"to": RF_REVIEW, "message": RF_MSG}, rf_path("agent-sender-finished-reviewer"))
rf_refuse("control: a main-session send to a finished worktree builder on the sender transcript is refused",
          {"to": RF_WT_BUILDER, "message": RF_MSG}, rf_path("agent-sender-finished-worktree"),
          carries=("fresh builder",))
# An agent's own send. Its payload carries agent_id and agent_type, and agent_id is the spawn's agentId, which the
# parent's transcript holds (the running builder in each of these). Its send is judged as the main session's is.
rf_refuse("an agent's send to a finished reviewer the parent spawned is refused",
          {"to": RF_REVIEW, "message": RF_MSG}, rf_path("agent-sender-finished-reviewer"),
          agent_id=RF_OTHER_AGENT, agent_type="builder")
rf_refuse("an agent's send to a finished worktree builder the parent spawned is refused, and the reason says fresh builder",
          {"to": RF_WT_BUILDER, "message": RF_MSG}, rf_path("agent-sender-finished-worktree"),
          agent_id=RF_OTHER_AGENT, agent_type="builder", carries=("fresh builder",))
rf_allow("an agent's send to a running reviewer the parent spawned passes",
         {"to": RF_REVIEW, "message": RF_MSG}, rf_path("agent-sender-running-reviewer"),
         agent_id=RF_OTHER_AGENT, agent_type="builder")
rf_allow("an agent's send to main passes",
         {"to": "main", "message": RF_MSG}, rf_path("agent-sender-finished-reviewer"),
         agent_id=RF_OTHER_AGENT, agent_type="builder")
# A main-session send to a Workflow agent, named by its agentId. Its spawn is in its run's journal, not the transcript:
# it has finished when its result line exists, has no worktree, and is a reviewer by its meta agentType.
rf_allow("a main-session send to a finished Workflow agent passes: it has no worktree, and its agentType is not a reviewer",
         {"to": RF_WF_DONE_AGENT, "message": RF_MSG}, rf_path("workflow-agents"))
rf_refuse("a main-session send to a finished Workflow reviewer is refused",
          {"to": RF_WF_REVIEW_AGENT, "message": RF_MSG}, rf_path("workflow-agents"))
rf_allow("a main-session send to a running Workflow reviewer (a started line, no result) passes",
         {"to": RF_WF_RUNNING_AGENT, "message": RF_MSG}, rf_path("workflow-agents"))
# A Workflow agent named by its started line's label, not its agentId: `review-finished` labels the finished reviewer.
# The control names the finished non-reviewer by its label, so the label path alone is not what refuses.
rf_refuse("a main-session send to a finished Workflow reviewer, named by its journal label, is refused",
          {"to": "review-finished", "message": RF_MSG}, rf_path("workflow-agents"))
rf_allow("control: a main-session send to a finished non-reviewer Workflow agent, named by its label, passes",
         {"to": "scan-finished", "message": RF_MSG}, rf_path("workflow-agents"))
# An agent's send (a payload with agent_id) to a finished Workflow reviewer is refused. Its sender is the running
# builder spawned in that transcript. The control is an agent's send to a finished non-reviewer Workflow agent.
rf_refuse("an agent's send to a finished Workflow reviewer is refused",
          {"to": RF_WF_REVIEW_AGENT, "message": RF_MSG}, rf_path("workflow-agent-sender"),
          agent_id=RF_OTHER_AGENT, agent_type="builder")
rf_allow("control: an agent's send to a finished non-reviewer Workflow agent passes",
         {"to": RF_WF_DONE_AGENT, "message": RF_MSG}, rf_path("workflow-agent-sender"),
         agent_id=RF_OTHER_AGENT, agent_type="builder")
# A finished Workflow agent of agentType workflow-subagent that was spawned with isolation worktree: its meta holds
# spawnedWithWorktree and a worktreePath, and its worktree is gone once it finishes. Refused for a main-session send and
# for an agent's send. The role pins no isolation, so the meta keys are what decide.
rf_refuse("a main-session send to a finished Workflow agent spawned with a worktree is refused",
          {"to": RF_WF_WT_AGENT, "message": RF_MSG}, rf_path("workflow-worktree"),
          carries=("fresh workflow-subagent", "prior report"))
rf_refuse("an agent's send to a finished Workflow agent spawned with a worktree is refused",
          {"to": RF_WF_WT_AGENT, "message": RF_MSG}, rf_path("workflow-worktree"),
          agent_id=RF_OTHER_AGENT, agent_type="builder", carries=("fresh workflow-subagent", "prior report"))
# The same agent type with the same keys, while it runs (a started line, no result), passes. A finished one with no
# worktree keys passes too: it is the control that shows the keys alone make the refusal above.
rf_allow("a main-session send to a running Workflow agent spawned with a worktree passes: a started line, no result",
         {"to": RF_WF_WT_RUNNING_AGENT, "message": RF_MSG}, rf_path("workflow-worktree"))
rf_allow("control: a main-session send to a finished Workflow agent of workflow-subagent with no worktree keys passes",
         {"to": RF_WF_NOKEYS_AGENT, "message": RF_MSG}, rf_path("workflow-worktree"))
# A reviewer stopped with TaskStop leaves a started line and no result line. Its run record says killed, so the run is
# finished, and the reviewer is refused. A finished run's record says completed, and the same. A run with no record is
# still running, so its started-only reviewer passes.
rf_refuse("a started-only Workflow reviewer whose run record says killed is refused: the run was stopped",
          {"to": RF_WF_KILLED_AGENT, "message": RF_MSG}, rf_path("workflow-killed"))
rf_refuse("a started-only Workflow reviewer whose run record says completed is refused: the run finished",
          {"to": RF_WF_COMPLETED_AGENT, "message": RF_MSG}, rf_path("workflow-completed"))
rf_allow("a started-only Workflow reviewer with no run record passes: the run is still running",
         {"to": RF_WF_NORECORD_AGENT, "message": RF_MSG}, rf_path("workflow-norecord"))
# A finished Workflow agent with no agentType has the role agent, and its worktree flag alone refuses it.
rf_refuse("a finished Workflow agent with a worktree flag and no agentType is refused as an agent",
          {"to": RF_WF_NOTYPE_AGENT, "message": RF_MSG}, rf_path("workflow-notype"),
          carries=("this agent has finished", "fresh agent", "prior report"))
# Asked: no readable journal names the target, and a journal beside the transcript cannot be read. The control is the
# same target on a transcript whose journals all read: nothing names it, so it passes.
rf_ask("a Workflow agent whose journal cannot be read asks: no readable journal names it",
       {"to": RF_WF_UNREADABLE_AGENT, "message": RF_MSG}, rf_path("workflow-unreadable"))
rf_allow("control: a Workflow agent that no journal names passes when every journal can be read",
         {"to": RF_WF_UNREADABLE_AGENT, "message": RF_MSG}, rf_path("workflow-agents"))
rf_allow("a send in a transcript with no spawn at all is allowed",
         {"to": RF_REVIEW, "message": RF_MSG}, rf_path("no-spawn"))
rf_allow("a missing transcript is allowed, never refused",
         {"to": RF_REVIEW, "message": RF_MSG}, rf_path("missing"))
# Asked: a finished Workflow agent with a result line and no meta file. Its role is unknown, and an unknown state asks
# (coordinator ruling).
rf_ask("a finished Workflow agent with no meta file asks: its role is unknown",
       {"to": RF_WF_NOMETA_AGENT, "message": RF_MSG}, rf_path("workflow-no-meta"))
# Asked: the target is a reviewer whose result shape is unknown, so the guard cannot tell whether it finished.
rf_ask("a reviewer whose launch result holds a bare string asks",
       {"to": RF_UNKNOWN, "message": RF_MSG}, rf_path("reviewer-unknown-result"))
rf_ask("a reviewer whose notice names its id with no status asks",
       {"to": RF_NOTICE_AGENT, "message": RF_MSG}, rf_path("reviewer-notice-no-status"))
# An errored spawn never ran, so it is skipped, as review_log_hit skips it. Its name resolves to nothing, or to the
# spawn before it: the older finished spawn is refused, and the older running spawn is allowed.
rf_allow("a reviewer whose spawn result is an error is allowed: that spawn never ran",
         {"to": RF_ERRORED, "message": RF_MSG}, rf_path("reviewer-spawn-errored"))
rf_refuse("a reviewer that finished, then a same-name spawn whose result is an error, is refused: the finished one governs",
          {"to": RF_ERR_FINISHED, "message": RF_MSG}, rf_path("finished-then-errored-spawn"))
rf_allow("a reviewer that runs, then a same-name spawn whose result is an error, is allowed: the running one governs",
         {"to": RF_ERR_RUNNING, "message": RF_MSG}, rf_path("running-then-errored-spawn"))
rf_ask("a reviewer whose finish notice says it is still running asks",
       {"to": RF_RUNNING_AGENT, "message": RF_MSG}, rf_path("reviewer-notice-running"))
# Asked: the send names the builder by its agent id, which its finish notice carries. Its launch result holds a bare
# string, so the guard cannot read its state. The name-addressed send to it asks too (the control). The id-addressed
# send to the running worktree builder passes: its id resolves, and its state is running.
rf_ask("an id-addressed send to a finished worktree builder whose launch result holds a bare string asks",
       {"to": RF_WT_UNKNOWN_AGENT, "message": RF_MSG}, rf_path("worktree-builder-unknown-result-finished"))
rf_ask("control: a name-addressed send to that builder asks: its launch result holds a bare string",
       {"to": RF_WT_UNKNOWN, "message": RF_MSG}, rf_path("worktree-builder-unknown-result-finished"))
rf_allow("control: an id-addressed send to a still-running worktree builder passes",
         {"to": RF_WT_LIVE_AGENT, "message": RF_MSG}, rf_path("worktree-builder-unknown-result-finished"))
# Refused: a reviewer spelled `Reviewer` is refused as the lower-case one is. The lower-case send is the control, on
# the same transcript, so the spelling is what decides.
rf_refuse("control: a finished reviewer named in lower case is refused, beside a `Reviewer` spawn in the transcript",
          {"to": RF_CASE_LOWER, "message": RF_MSG}, rf_path("bg-reviewer-case-pair-finished"))
rf_refuse("a finished Reviewer spelled with a capital R, with no worktree, is refused as the lower-case one is",
          {"to": RF_CASE_CAP, "message": RF_MSG}, rf_path("bg-reviewer-case-pair-finished"),
          carries=("prior report",))


# A `to` in the `name [ref]` form, which SendMessage writes when a name is ambiguous. The ref is the first eight hex of
# the agent id, so `rev [<ref>]` names the spawn `rev` that holds that id. The bare-name cases are controls: they
# show the fixture reads as finished and as running, so each ref case turns on its ref alone.
rf_refuse("name [ref] form: a finished reviewer named rev is refused by its bare name (control)",
          {"to": RF_REV, "message": RF_MSG}, rf_path("bg-rev-finished"))
rf_refuse("name [ref] form: a finished reviewer named rev, with its ref, is refused",
          {"to": "rev [a5eb5d25]", "message": RF_MSG}, rf_path("bg-rev-finished"))
rf_allow("name [ref] form: a running reviewer named rev is allowed by its bare name (control)",
         {"to": RF_REV, "message": RF_MSG}, rf_path("bg-rev-running"))
rf_allow("name [ref] form: a running reviewer named rev, with its ref, is allowed",
         {"to": "rev [a5eb5d25]", "message": RF_MSG}, rf_path("bg-rev-running"))
# The name picks the spawn: a name no spawn holds is allowed, though the finished rev holds the ref.
rf_allow("name [ref] form: a name with no spawn is allowed, though a finished reviewer holds its ref",
         {"to": "nobody [a5eb5d25]", "message": RF_MSG}, rf_path("bg-rev-finished"))


# The two checks below run one SendMessage each, in a config folder of their own, so each reads the guard.log rows
# its own call wrote. They build their own folders and read no lazy fixture: see FIXTURELESS_CHECKS.
RF_COST_LABEL = ("resume-finished-reviewer: one SendMessage to a finished reviewer reads the transcript once, "
                 "across both readers")
RF_UNPARSED_LABEL = ("resume-finished-reviewer: a transcript record the read cannot parse asks, and logs a noted "
                     "line")


def rf_guard_run(name, lines, to):
    """(decision, reason, guard.log rows) for one SendMessage from the main session to `to`, judged over the transcript
    `lines`. The folder named `name` is the config folder the call writes its guard.log into."""
    folder = os.path.join(ROOT, "resumefinished-log", name)
    write_transcripts({"transcript": lines}, folder)   # the one writer: it puts the merge tool's record marker in
    path = os.path.join(folder, "transcript.jsonl")
    log = os.path.join(folder, "guard.log")
    if os.path.exists(log):
        os.remove(log)
    env = dict(os.environ)
    for key in ("CLAUDE_CODE_REMOTE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_PROJECT_DIR"):
        env.pop(key, None)
    env.update(ROLE_ENV)
    env["CLAUDE_CONFIG_DIR"] = folder
    env["CLAUDE_GUARD_ROOT_PID"] = str(os.getpid())   # the suite stands in for `claude`
    body = {"tool_name": RR_BUILTIN_SEND, "tool_input": {"to": to, "message": RF_MSG}, "cwd": NOGIT,
            "transcript_path": path}
    got = subprocess.run([sys.executable, GUARD], input=json.dumps(body), capture_output=True, text=True,
                         env=env, timeout=120)
    if got.returncode != 0:
        return "error", got.stderr.strip()[:200], []
    decision, reason = read_decision(got.stdout)
    return decision, reason, [line.split("\t") for line in _guard_log_lines(folder)]


def rf_unparsed_case():
    """A transcript with a record the reader cannot parse, after a finished reviewer: a SendMessage to that reviewer is
    asked, not allowed, and one noted line names the rule. The control is the same transcript without that record: the
    finished reviewer is refused there, so the record is the cause."""
    base = rr_session(rr_spawn("r1", "reviewer", name=RF_MALFORMED), rr_comment("c1", rr_record()))
    # The scope first: the unparsed line is a JSON object whose message is a string, the shape the reader fails on.
    bad = json.loads(RF_UNPARSED)
    if not isinstance(bad, dict) or not isinstance(bad.get("message"), str):
        return False, "the unparsed fixture is not a record with a string message: %r" % (RF_UNPARSED[:80],)
    decision, reason, _rows = rf_guard_run("unparsed-control", base, RF_MALFORMED)
    if decision != "deny" or RF_RULE not in reason:
        return False, "control: without the unparsed record, want a deny that names %s, got %r: %s" % (
            RF_RULE, decision, reason[:80])
    decision, reason, rows = rf_guard_run("unparsed", base + [RF_UNPARSED], RF_MALFORMED)
    problems = []   # one cause per message: the verdict, then the noted line
    if decision != "ask" or RF_RULE not in reason:
        problems.append("with the unparsed record, want an ask that names %s, got %r: %s" % (
            RF_RULE, decision, reason[:80]))
    noted = [r for r in rows if len(r) == 6 and r[2] == "noted" and r[3].startswith(RF_RULE)]
    if not noted:
        problems.append("no noted %s line in guard.log: %r" % (RF_RULE, [r[2:4] for r in rows if len(r) > 3]))
    if problems:
        return False, "; ".join(problems)
    return True, "the unparsed record asks, and one noted line names the rule"


def rf_cost_case():
    """One SendMessage from the main session to a finished reviewer opens the transcript once: review_log_hit and
    resume_finished_hit share one read. The control is a send to main, which only the review reader judges: it opens the
    transcript once too. The control and the deny are asserted before the count, so a count is read only where the
    rule reached its read."""
    folder = os.path.join(ROOT, "resumefinished-cost")
    write_transcripts({"transcript": RF_TRANSCRIPTS["bg-reviewer-finished"]}, folder)
    with open(os.path.join(folder, "transcript.jsonl"), encoding="utf-8") as handle:
        lines = handle.read().splitlines()   # the lines with the record marker in, as lb_run writes them
    control_got, control_reason, control = lb_run(
        RR_BUILTIN_SEND, {"mode": "judge", "reading": LB_NORMAL}, {"to": "main", "message": RF_MSG},
        own_env=ROLE_ENV, transcript=lines, spy=True)
    if control_got == "error":
        return False, control_reason
    if control_got != "allow":
        return False, "control: a send to main is %s, want allow: %s" % (control_got, control_reason[:80])
    if control.get("opened", 0) != 1:
        return False, "control: a send to main opened the transcript %d time(s), want 1" % control.get("opened", 0)
    got, reason, side = lb_run(RR_BUILTIN_SEND, {"mode": "judge", "reading": LB_NORMAL},
                               {"to": RF_REVIEW, "message": RF_MSG}, own_env=ROLE_ENV, transcript=lines, spy=True)
    if got == "error":
        return False, reason
    if got != "deny" or RF_RULE not in reason:
        return False, "%s, want a deny that names %s: %s" % (got, RF_RULE, reason[:80])
    opened = side.get("opened", 0)
    if opened != 1:
        return False, "the transcript was opened %d time(s) by one SendMessage to a finished reviewer, want 1" % opened
    return True, "one SendMessage to a finished reviewer opens the transcript once, as a send to main does"


