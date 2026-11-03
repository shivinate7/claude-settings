export const meta = {
  name: 'deep-audit-run2',
  description: 'Deep audit Run 2: an Opus judge and an Opus refuter per chunk of up to 40 quote-checked findings, then one Opus write-up per repo',
  phases: [{ title: 'Judge', model: 'opus' }, { title: 'Refute', model: 'opus' }, { title: 'Write-up', model: 'opus' }],
}
// args: {dir, shas, paths, chunks: [{topic, file, n}]} from split.py. Each chunk file is <dir>/run2/<file>, a JSON list of findings.
const A = args
const shaLine = Object.entries(A.shas).map(([r, s]) => `${r}: ${A.paths[r]} @ ${s}`).join('; ')
const F = {type:'object', properties:{findings:{type:'array', items:{type:'object', properties:{
  kind:{type:'string'}, topic:{type:'string'}, a_repo:{type:'string'}, a_file:{type:'string'}, a_line:{type:'integer'}, a_quote:{type:'string'},
  b_repo:{type:'string'}, b_file:{type:'string'}, b_line:{type:'integer'}, b_quote:{type:'string'},
  why:{type:'string'}, harm:{type:'string', enum:['high','medium','low']}, verdict:{type:'string'}}, required:['kind','topic','a_repo','a_file','a_line','why','harm']}}}, required:['findings']}
const R = {type:'object', properties:{report_md:{type:'string'}, lanes:{type:'array', items:{type:'object', properties:{
  slug:{type:'string'}, repo:{type:'string'}, home:{type:'string', enum:['lane','debt','note','owner-question']}, one_home:{type:'boolean'},
  findings:{type:'array', items:{type:'string'}}, brief:{type:'string'}}, required:['slug','repo','home','brief']}}}, required:['report_md','lanes']}
const READ = `Read only with \`git -C <path> show <sha>:<file>\` piped to sed -n on line ranges, and \`git -C <path> grep -n -E '<term>' <sha>\`. A finding whose why starts with "PR #" quotes the PR branch: read its a side at origin/<ref> in the claude-settings checkout. Repos and pinned shas: ${shaLine}.`
const PRIVATE = ['q_max', 'degen', 'joyous']
const judged = await pipeline(A.chunks,
  c => agent(`Audit: deep audit judge.
Topic "${c.topic}". Read the ${c.n} findings in ${A.dir}/run2/${c.file} (a JSON list).
These findings passed an exact-quote check. Read each one's cited lines and the code or text around them. Confirm a finding only when the defect is real. For a duplicate, confirm only when one copy can change without the other. Kill the rest. You may add a contradiction between two claims in this chunk that the sweep missed, with exact quotes. Rate the harm: what Claude could do wrong in normal work because of it. Put "confirmed" or "added" in verdict.
${READ}`, {label:`judge:${c.file}`, phase:'Judge', agentType:'Explore', model:'opus', schema:F}),
  (j, c) => agent(`Audit: deep audit refuter.
Topic "${c.topic}".
Try to disprove each finding below. Re-read the source at the cited lines. A contradiction is refuted if a later ruling or a scope line resolves it. An empty promise is refuted if the check exists and runs. An overpromise is refuted if the code covers the claim. A duplicate is refuted if both copies read one home, through an import, a generated block, or a check that fails when they differ. Return only the findings that survive, unchanged except for verdict ("survives: <why>").
${READ}
Findings: ${JSON.stringify((j && j.findings) || [])}`, {label:`refute:${c.file}`, phase:'Refute', agentType:'Explore', model:'opus', schema:F}))
const survived = judged.filter(Boolean).flatMap(r => r.findings || [])
log(`${survived.length} findings survived; ${judged.filter(x => !x).length} of ${A.chunks.length} chunks returned nothing`)
phase('Write-up')
const repos = Object.keys(A.shas).filter(r => survived.some(f => f.a_repo === r))
const outs = await parallel(repos.map(r => () => agent(`Audit: deep audit write-up for repo ${r}.
Merge duplicate findings. Rank them by harm in Claude's normal work. Give each one home: a lane, a debt (only when Claude is likely to hit it), a note, or an owner question under the stale-decision protocol. Each confirmed duplicate becomes a one-home lane (one_home true); those lanes feed the one-home check build in claude-settings PR #1106. A lane's brief names its files, the rulings that govern it, and the check that proves it done.
report_md is the ${r} section of the report, in plain short sentences, under a "## ${r}" heading with subsections for contradictions, empty promises, overpromises and duplicates. Every finding cites its repo, file and line.${PRIVATE.includes(r) ? ` ${r} is private: this section goes only to a branch of ${r}. Never quote text from any other private repo.` : ` This section is public. Never quote text from a private repo (${PRIVATE.join(', ')}); cite their file and line only.`}
Findings: ${JSON.stringify(survived.filter(f => f.a_repo === r))}`, {label:`write-up:${r}`, phase:'Write-up', agentType:'Explore', model:'opus', schema:R}).then(o => o && { repo: r, ...o })))
const ok = outs.filter(Boolean)
return { survived, sections: ok.map(o => ({ repo: o.repo, report_md: o.report_md })), lanes: ok.flatMap(o => o.lanes || []), missing: repos.filter(r => !ok.some(o => o.repo === r)) }
