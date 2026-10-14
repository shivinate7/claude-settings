// Token Weather context band: the fill is measured against the auto-compact window when auto-compact
// is on and that window is smaller than the model window, as desktop-statusline does (register.tsx:129-130).
// Run: node mods/token-weather/token-weather.test.mjs  (stdlib only)
// Seam: hooks/token-weather.mjs exports register(on). The test collects the handlers by event name,
// then drives turn.complete and ui.render with a fake host $.
// Host contract pinned here: session.usage() returns context.breakdown only when called with
// { breakdown: 'summary' }, the call desktop-statusline makes. The fixtures' context.percent is
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

await test('auto-compact off: model window is used', async () => {
  const text = await bandText(context({ isAutoCompactEnabled: false, rawMaxTokens: 500000 }))
  assert.ok(text.includes('25% of context'), text)
  assert.ok(text.includes('250k / 1M'), text)
})

await test('rawMaxTokens above the model window: model window is used', async () => {
  const text = await bandText(context({ isAutoCompactEnabled: true, rawMaxTokens: 2000000 }))
  assert.ok(text.includes('25% of context'), text)
  assert.ok(text.includes('250k / 1M'), text)
})

await test('no breakdown: model window is used', async () => {
  const text = await bandText(context(undefined))
  assert.ok(text.includes('25% of context'), text)
  assert.ok(text.includes('250k / 1M'), text)
})

const failed = r1.filter(r => r.startsWith('FAIL')).length
console.log(r1.join('\n'))
console.log(`token-weather context band: ${r1.length - failed} pass, ${failed} fail of ${r1.length}`)
if (failed) process.exitCode = 1
