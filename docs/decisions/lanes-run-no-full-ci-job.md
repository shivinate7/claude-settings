# A lane never runs a full CI job

## The ruling

Owner, 2026-10-27 (waiting page item 27, option a): a lane runs only the suites its change touches. It never runs a whole CI job locally, `bin/ci-job` included. The batch's integration CI run is the only full run (`roles-each-layer-proves-once`, each layer proves a change once). `bin/ci-job` stays, as a tool any session may run on demand.

Why: a full local run per lane proves again what the batch run proves, and costs a lane its time. A fixture that copies a changed file is caught by the batch run, and the fixtures now copy what git tracks, so a new shared module no longer breaks them.

Kind: process
Home: rule:roles-each-layer-proves-once
