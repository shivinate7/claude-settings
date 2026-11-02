export const meta = {
  name: 'deep-audit-run1',
  description: 'Deep audit Run 1: Sonnet sweep of claims, second copies and open PRs for contradictions, empty promises, overpromises and duplicated sources of truth',
  phases: [{ title: 'Claims' }, { title: 'Copies' }, { title: 'Open PRs' }],
}
const A = args
const shaLine = Object.entries(A.shas).map(([r, s]) => `${r}: ${A.paths[r]} @ ${s}`).join('; ')
const FIND = {type:'object', properties:{findings:{type:'array', items:{type:'object', properties:{
  kind:{type:'string', enum:['contradiction','empty_promise','overpromise','duplicate']},
  topic:{type:'string', enum:['merge','tiers','models','questions-page','guards','records','artifacts-design','ci-batches','other']},
  a_repo:{type:'string'}, a_file:{type:'string'}, a_line:{type:'integer'}, a_quote:{type:'string'},
  b_repo:{type:'string'}, b_file:{type:'string'}, b_line:{type:'integer'}, b_quote:{type:'string'},
  why:{type:'string'}}, required:['kind','topic','a_repo','a_file','a_line','a_quote','why']}},
  unread:{type:'array', items:{type:'string'}}}, required:['findings']}
const RULES = `Read only with \`git -C <path> show <sha>:<file>\` piped to sed -n on line ranges, and \`git -C <path> grep -n -E '<term>' <sha>\`. Never load a whole long file. Repos and pinned shas: ${shaLine}.
Finding kinds:
- contradiction: two texts, or a text and the code, cannot both be true.
- empty_promise: the text names a check, hook or test that does not exist, never runs (not in settings.json hooks or .github/workflows), or does not test the claim.
- overpromise: the text claims more than the code does ("never", "all", "every") and the code covers only part.
- duplicate: two places hold the same list, constant or rule, and neither reads the other, so one can change alone.
Each quote is copied character for character from the cited line. A finding with no exact quote is dropped later, so never paraphrase a quote. Report only real defects you checked; a line that is merely absolute with nothing contradicting it is no finding. Cap: 25 findings, the most harmful first. List files you could not read in unread.`

phase('Claims')
const claimJobs = A.claim_shards.map(f => () => agent(`Audit: deep audit claim sweep.
Read the claim rows in ${A.dir}/shards/${f} (tab-separated: repo, file, line, kinds, text). For each claim, check it three ways: does a named check exist and test it (empty_promise), does the code cover all of it (overpromise), and does any other text or code say otherwise (contradiction, search with git grep across the repos). Also flag a claim that restates another file's rule as a second copy (duplicate).
${RULES}`, {label:`claims:${f}`, phase:'Claims', agentType:'Explore', model:'sonnet', schema:FIND}))
const copyJobs = A.dup_shards.map(f => () => agent(`Audit: deep audit second-copy sweep.
Read ${A.dir}/shards/${f}: a JSON list of candidate second copies (a string list or a 12+ word sentence found in 2+ files). For each, read both places. Report a duplicate only when both hold the same thing for the same purpose and neither imports, generates or checks the other. Name each copy's file and symbol in the quote fields. Drop boilerplate (license text, test fixtures, a quoted example).
${RULES}`, {label:`copies:${f}`, phase:'Copies', agentType:'Explore', model:'sonnet', schema:FIND}))
const prGroups = []
for (let i = 0; i < A.prs.length; i += 3) prGroups.push(A.prs.slice(i, i + 3))
const prJobs = prGroups.map((g, i) => () => agent(`Audit: deep audit open-PR sweep.
Repo shivinate7/claude-settings at ${A.paths['claude-settings']}. Run \`git -C ${A.paths['claude-settings']} fetch origin <ref>\` for each, then read \`git diff origin/main...origin/<ref>\`, in parts. PRs: ${g.map(p => `#${p.n} ${p.ref} (${p.t})`).join('; ')}.
Report what each PR's added text or code would make contradict main, promise without a check, overpromise, or duplicate. Use b_* fields for the main side. Repo for these findings: claude-settings; put "PR #n" at the start of why.
${RULES}`, {label:`prs:${i}`, phase:'Open PRs', agentType:'Explore', model:'sonnet', schema:FIND}))
const all = await parallel([...claimJobs, ...copyJobs, ...prJobs])
const ok = all.filter(Boolean)
log(`${ok.length}/${all.length} sweep agents returned`)
// The caller writes the result to <dir>/run1-findings.json and pushes it.
return { findings: ok.flatMap(r => r.findings || []), unread: ok.flatMap(r => r.unread || []), returned: ok.length, total: all.length }