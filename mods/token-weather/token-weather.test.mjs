// Token Weather context band: the fill is measured against the auto-compact window when auto-compact
// is on and that window is smaller than the model window. The rule's home is hooks/token-weather.mjs.
// Run: node mods/token-weather/token-weather.test.mjs  (stdlib only)
// Seam: hooks/token-weather.mjs exports register(on). The test collects the handlers by event name,
// then drives turn.complete and ui.render with a fake host $.
// Host contract pinned here: session.usage() returns context.breakdown only when called with
// { breakdown: 'summary' }, per the host type doc for session.usage. The fixtures' context.percent is
// model-relative (25), so the band must measure its own percent against the window it uses.
import assert from 'node:assert/strict'

const HOOK = new URL('./hooks/token-weather.mjs', import.meta.url).href

const r1 = []
async function test(name, fn) {
  try {
    await fn()
    r1.push(`PASS ${name}`)
  } catch (e) {
    r1.push(`FAIL ${name}: ${String(e && e.message ? e.message : e).split('\n')[0]}`)
  }
}

// A fresh module instance per call: the mod keeps its readings at module level.
let instance = 0
async function loadHandlers() {
  const mod = await import(`${HOOK}?instance=${++instance}`)
  const handlers = {}
  mod.register((name, ...rest) => {
    handlers[name] = rest[rest.length - 1]
  })
  return handlers
}

const Box = props => ({ kind: 'Box', ...props })
const Text = props => ({ kind: 'Text', ...props })
const textOf = node =>
  typeof node === 'string' ? node
  : Array.isArray(node) ? node.map(textOf).join('')
  : node && node.children !== undefined ? textOf(node.children)
  : ''

// The breakdown is returned only when the caller asks for it, as the host does.
function fakeHost(context) {
  const usage = async opts => {
    const { breakdown, ...base } = context
    return { context: opts?.breakdown === 'summary' && breakdown ? { ...base, breakdown } : base }
  }
  return {
    session: { usage },
    ui: { invalidate() {}, resolve: () => ({ Box, Text }) },
  }
}

// Fixture: 250k tokens used of a 1M model window. percent is the model-relative figure.
const TOKENS = 250000
const MODEL_WINDOW = 1000000
const context = breakdown => ({
  tokens: TOKENS,
  window: MODEL_WINDOW,
  percent: Math.round((TOKENS / MODEL_WINDOW) * 100),
  ...(breakdown ? { breakdown } : {}),
})

async function bandText(ctx) {
  const h = await loadHandlers()
  const $ = fakeHost(ctx)
  await h['turn.complete']($, {}, async e => e)
  const node = await h['ui.render']($, { bodyColumns: 80, hasSurvey: false }, async e => e)
  return textOf(node)
}

await test('auto-compact on: fill and label measure the 500k auto-compact window, not the 1M model window', async () => {
  const text = await bandText(context({ isAutoCompactEnabled: true, rawMaxTokens: 500000 }))
  assert.ok(text.includes('50% of context'), text)
  assert.ok(text.includes('250k / 500k'), text)
})

// One table, one assertion: each row is a fallback input that must fall back to the 1M model window.
await test('model window is used for every fallback: auto-compact off, rawMaxTokens above the window, no breakdown, rawMaxTokens missing or 0', async () => {
  const rows = [
    ['auto-compact off', { isAutoCompactEnabled: false, rawMaxTokens: 500000 }],
    ['rawMaxTokens above the model window', { isAutoCompactEnabled: true, rawMaxTokens: 2000000 }],
    ['no breakdown', undefined],
    ['rawMaxTokens missing', { isAutoCompactEnabled: true }],
    ['rawMaxTokens 0', { isAutoCompactEnabled: true, rawMaxTokens: 0 }],
  ]
  const bad = []
  for (const [name, breakdown] of rows) {
    const text = await bandText(context(breakdown))
    if (!text.includes('25% of context') || !text.includes('250k / 1M')) bad.push(`${name}: ${text}`)
  }
  assert.deepEqual(bad, [])
})

// Its own row: a missing or zero rawMaxTokens must never print NaN or Infinity.
await test('rawMaxTokens missing or 0: no NaN or Infinity in the band', async () => {
  const bad = []
  for (const breakdown of [{ isAutoCompactEnabled: true }, { isAutoCompactEnabled: true, rawMaxTokens: 0 }]) {
    const text = await bandText(context(breakdown))
    if (/NaN|Infinity/.test(text)) bad.push(text)
  }
  assert.deepEqual(bad, [])
})

const failed = r1.filter(r => r.startsWith('FAIL')).length
console.log(r1.join('\n'))
console.log(`token-weather context band: ${r1.length - failed} pass, ${failed} fail of ${r1.length}`)
if (failed) process.exitCode = 1
