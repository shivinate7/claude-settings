export const meta = {
  name: 'deep-audit-run2',
  description: 'Deep audit Run 2: an Opus judge and an Opus refuter per topic over quote-checked findings, then one Opus write-up',
  phases: [{ title: 'Judge', model: 'opus' }, { title: 'Refute', model: 'opus' }, { title: 'Write-up', model: 'opus' }],
}
// args: {dir, shas, paths, topics: {topic: [finding, ...]}} where topics is checked.json.
const A = args
const shaLine = Object.entries(A.shas).map(([r, s]) => `${r}: ${A.paths[r]} @ ${s}`).join('; ')
const F = {type:'object', properties:{findings:{type:'array', items:{type:'object', properties:{
  kind:{type:'string'}, topic:{type:'string'}, a_repo:{type:'string'}, a_file:{type:'string'}, a_line:{type:'integer'}, a_quote:{type:'string'},
  b_repo:{type:'string'}, b_file:{type:'string'}, b_line:{type:'integer'}, b_quote:{type:'string'},
  why:{type:'string'}, harm:{type:'string', enum:['high','medium','low']}, verdict:{type:'string'}}, required:['kind','topic','a_repo','a_file','a_line','why','harm']}}}, required:['findings']}
const R = {type:'object', properties:{report_md:{type:'string'}, lanes:{type:'array', items:{type:'object', properties:{
  slug:{type:'string'}, repo:{type:'string'}, home:{type:'string', enum:['lane','debt','note','owner-question']}, one_home:{type:'boolean'},
  findings:{type:'array', items:{type:'string'}}, brief:{type:'string'}}, required:['slug','repo','home','brief']}}}, required:['report_md','lanes']}
const READ = `Read only with \`git -C <path> show <sha>:<file>\` piped to sed -n on line ranges, and \`git -C <path> grep -n -E '<term>' <sha>\`. Repos and pinned shas: ${shaLine}.`
const topics = Object.keys(A.topics).filter(t => A.topics[t].length)
const judged = await pipeline(topics,
  t => agent(`Audit: deep audit judge.
Topic "${t}".
These findings passed an exact-quote check. Read each one's cited lines and the code or text around them. Confirm a finding only when the defect is real. For a duplicate, confirm only when one copy can change without the other. Kill the rest. You may add a contradiction between two claims in this topic that the sweep missed, with exact quotes. Rate the harm: what Claude could do wrong in normal work because of it. Put "confirmed" or "added" in verdict.
${READ}
Findings: ${JSON.stringify(A.topics[t])}`, {label:`judge:${t}`, phase:'Judge', agentType:'Explore', model:'opus', schema:F}),
  (j, t) => agent(`Audit: deep audit refuter.
Topic "${t}".
Try to disprove each finding below. Re-read the source at the cited lines. A contradiction is refuted if a later ruling or a scope line resolves it. An empty promise is refuted if the check exists and runs. An overpromise is refuted if the code covers the claim. A duplicate is refuted if both copies read one home, through an import, a generated block, or a check that fails when they differ. Return only the findings that survive, unchanged except for verdict ("survives: <why>").
${READ}
Findings: ${JSON.stringify((j && j.findings) || [])}`, {label:`refute:${t}`, phase:'Refute', agentType:'Explore', model:'opus', schema:F}))
const survived = judged.filter(Boolean).flatMap(r => r.findings || [])
log(`${survived.length} findings survived`)
phase('Write-up')
const out = await agent(`Audit: deep audit write-up.
Merge duplicate findings. Rank them by harm in Claude's normal work. Give each one home: a lane, a debt (only when Claude is likely to hit it), a note, or an owner question under the stale-decision protocol. Each confirmed duplicate becomes a one-home lane (one_home true); those lanes feed the one-home check build in claude-settings PR #1106. Group lanes by repo. A lane's brief names its files, the rulings that govern it, and the check that proves it done.
report_md is the report in plain short sentences, in sections for contradictions, empty promises, overpromises and duplicates. Every finding cites its repo, file and line. Never quote text from a private repo (q_max, degen, joyous) in report_md; cite their file and line only.
Findings: ${JSON.stringify(survived)}`, {label:'write-up', phase:'Write-up', agentType:'Explore', model:'opus', schema:R})
return { survived, ...out }
