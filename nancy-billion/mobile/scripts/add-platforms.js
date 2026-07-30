#!/usr/bin/env node
// Adds whichever native platforms this machine can actually build.
//
// `cap add ios` only works on macOS (it needs CocoaPods and Xcode), so on
// Windows and Linux we quietly skip it rather than failing the whole setup.
// Re-running is safe: a platform that already exists is left alone.
const { existsSync } = require('fs')
const { spawnSync } = require('child_process')
const { join } = require('path')

const root = join(__dirname, '..')
const isMac = process.platform === 'darwin'

const run = (args) => spawnSync('npx', ['cap', ...args], {
  cwd: root, stdio: 'inherit', shell: process.platform === 'win32',
})

const add = (platform) => {
  if (existsSync(join(root, platform))) {
    console.log(`  ${platform}: already present, skipping`)
    return true
  }
  console.log(`  ${platform}: adding…`)
  const res = run(['add', platform])
  if (res.status !== 0) {
    console.warn(`  ${platform}: could not be added (exit ${res.status}).`)
    return false
  }
  return true
}

console.log('Billion mobile — native platforms')
add('android')

if (isMac) {
  add('ios')
} else {
  console.log('  ios: skipped — iOS projects can only be generated on macOS.')
}

console.log('\nDone. Next: npm run sync, then npm run open:android (or open:ios).')
