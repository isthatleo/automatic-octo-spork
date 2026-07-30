#!/usr/bin/env node
// Post-sync patches for the generated native projects.
//
// The control room is served over plain http from a machine on the user's own
// LAN, which both platforms block by default. Capacitor's `cleartext: true`
// covers Android; iOS needs an explicit App Transport Security exception in
// Info.plist, which Capacitor does not write for us. This adds it idempotently
// so `cap sync` can be re-run as often as you like.
const { existsSync, readFileSync, writeFileSync } = require('fs')
const { join } = require('path')

const root = join(__dirname, '..')
const plist = join(root, 'ios', 'App', 'App', 'Info.plist')

const ATS = `	<key>NSAppTransportSecurity</key>
	<dict>
		<key>NSAllowsArbitraryLoads</key>
		<true/>
	</dict>
`

if (!existsSync(plist)) {
  console.log('patch-native: no iOS project yet — nothing to patch.')
  process.exit(0)
}

const xml = readFileSync(plist, 'utf8')

if (xml.includes('NSAppTransportSecurity')) {
  console.log('patch-native: iOS ATS exception already present.')
  process.exit(0)
}

// Insert just before the final </dict> that closes the root dictionary.
const close = xml.lastIndexOf('</dict>')
if (close === -1) {
  console.warn('patch-native: Info.plist looks unfamiliar — skipping.')
  process.exit(0)
}

writeFileSync(plist, xml.slice(0, close) + ATS + xml.slice(close), 'utf8')
console.log('patch-native: added iOS ATS exception for LAN http.')
