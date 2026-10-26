// Red proof for the macOS mod-test step; this file leaves before merge. On macOS /var is a symlink
// to /private/var, so a mod that compares a path to its real path breaks there only.
import { realpathSync } from 'node:fs'
if (process.platform !== 'win32' && realpathSync('/var') !== '/var') {
  console.error(`red proof: /var resolves to ${realpathSync('/var')}`)
  process.exit(1)
}
console.log('red proof: /var is real here')
