// CLI: `node receiver-state.mjs <name>` prints the board state of the session with that name:
// busy, idle, waiting or unseen. For hooks/sendmessage_state.py, so the board read has one home
// (lib.mjs). Never fails: any trouble prints unseen.
import { execSync } from 'node:child_process'
import { parseAgentsJson, receiverState } from './lib.mjs'

let out = 'unseen'
try {
  const json = execSync('claude agents --json', { encoding: 'utf8', timeout: 8000, stdio: ['ignore', 'pipe', 'ignore'] })
  out = receiverState(parseAgentsJson(json), process.argv[2])
} catch { /* unseen */ }
console.log(out)
