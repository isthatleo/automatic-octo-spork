/**
 * Checks the passcode session's signing logic.
 *
 * session.ts is TypeScript and there's no build step available here, so this
 * strips the (deliberately simple) type annotations from the real file and
 * runs what's left. It is the same code path, not a restatement of it.
 *
 *   node frontend/lib/nancy/session.test.mjs
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const src = readFileSync(join(here, 'session.ts'), 'utf8')

const js = src
  .replace(/^export const (SESSION_COOKIE|SESSION_TTL_S|PASSCODE)[^\n]*$/gm, '')  // env-derived, set below
  .replace(/^const SECRET[^\n]*$/gm, '')
  .replace(/: Promise<[^>]+>/g, '')
  .replace(/: CryptoKey/g, '')
  .replace(/: ArrayBuffer/g, '')
  .replace(/: string \| undefined/g, '')
  .replace(/: boolean/g, '')
  .replace(/: string/g, '')
  .replace(/\bexport /g, '')

const PASSCODE = 'correct horse battery'
const SECRET = `derived:${PASSCODE}`
const SESSION_TTL_S = 60 * 60 * 24 * 30

const mod = await import(
  'data:text/javascript;base64,' +
  Buffer.from(
    `const PASSCODE=${JSON.stringify(PASSCODE)};` +
    `const SECRET=${JSON.stringify(SECRET)};` +
    `const SESSION_TTL_S=${SESSION_TTL_S};` +
    js +
    '\nexport {mintSession, verifySession, passcodeMatches, passcodeRequired};'
  ).toString('base64')
)

const failures = []
const check = (label, ok, detail = '') => {
  if (ok) console.log(`  ok  ${label}`)
  else { failures.push(label); console.log(`  FAIL ${label}${detail ? ': ' + detail : ''}`) }
}

console.log('passcode session')

check('a passcode being set means the lock is on', mod.passcodeRequired() === true)

const cookie = await mod.mintSession()
check('a freshly minted cookie verifies', (await mod.verifySession(cookie)) === true)
check('the cookie carries no secret', !cookie.includes(PASSCODE) && !cookie.includes(SECRET))

check('a missing cookie is rejected', (await mod.verifySession(undefined)) === false)
check('an empty cookie is rejected', (await mod.verifySession('')) === false)
check('a cookie with no signature is rejected', (await mod.verifySession('9999999999')) === false)

const [exp, sig] = [cookie.slice(0, cookie.lastIndexOf('.')), cookie.slice(cookie.lastIndexOf('.') + 1)]
check('a tampered signature is rejected',
  (await mod.verifySession(`${exp}.${sig.slice(0, -1)}X`)) === false)
check('an extended expiry with the old signature is rejected',
  (await mod.verifySession(`${Number(exp) + 86400}.${sig}`)) === false)

// A correctly signed but expired cookie: sign a past timestamp the same way.
const past = String(Math.floor(Date.now() / 1000) - 10)
const enc = new TextEncoder()
const key = await crypto.subtle.importKey('raw', enc.encode(SECRET),
  { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'])
const raw = await crypto.subtle.sign('HMAC', key, enc.encode(past))
const b64 = Buffer.from(raw).toString('base64')
  .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
check('a validly signed but expired cookie is rejected',
  (await mod.verifySession(`${past}.${b64}`)) === false)

check('the right passcode matches', mod.passcodeMatches(PASSCODE) === true)
check('a wrong passcode does not', mod.passcodeMatches('wrong') === false)
check('a prefix of the passcode does not', mod.passcodeMatches(PASSCODE.slice(0, -1)) === false)
check('the passcode plus extra does not', mod.passcodeMatches(PASSCODE + 'x') === false)
check('an empty passcode does not', mod.passcodeMatches('') === false)

console.log()
if (failures.length) { console.log(`${failures.length} check(s) failed`); process.exit(1) }
console.log('all passcode session checks passed')
