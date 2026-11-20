# A brief that edits the mutation test is not routed to a test-author

**What.** A brief that edits `hooks/mutate_guard.py` is not routed to a test-author. It should be. Nothing routes such a brief at spawn. The guard refuses the builder's first write to that file, after the spawn. Queued step `brief-routes-mutate-file`, queued in chat on Nov 18-19 (owner goal item 10).

**Where.** `hooks/agent_brief.py`, the `SCOPE` map. Its builder line says only "A mutant goes to a test-author." `hooks/guard.py`, `AUTHOR_MUTATION_TESTS`, lists the mutation tests that only a test-author owns. The routing reads that constant, never a copy of it.

**Decision.** `builders-cannot-edit-tests` (a builder never edits a test, and a mutation test is test code, so a test-author owns it).

**Retire.** `hooks/test_agent_brief.py` holds a case, red first on the current code, where a builder brief that names `hooks/mutate_guard.py` gets the test-author routing.
