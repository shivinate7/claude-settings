# c158-stamp-hang (cloud lane, Oct 28)

- c158: started. Branch `c158-stamp-hang` from batch-oct28a 0ae758e.
- Evidence read: job 122632514525's log blob is gone (404 BlobNotFound). Step list: step 33 "Record stamp engine fixture suite" started 04:38:03Z and stayed in_progress; the server ended the job at its 28 min cap. So neither the 5 min step cap nor the job cap ended the step on the runner.
- Working cause of the cap miss (unmeasured): the Windows runner waits for every process holding the step's output pipe; a hung grandchild of the fully synchronous suite (git, or node -> git) holds it. An in-process setTimeout cannot fire while spawnSync blocks.
- Plan: out-of-process watchdog (suite re-spawns itself with piped stdio, 4 min cap, tree kill, names the hung test and the live process tree, exits red); a timeout on each spawn in the suite; a test that a hung fixture exits red within its cap. Builder Opus, reviewer Opus.
