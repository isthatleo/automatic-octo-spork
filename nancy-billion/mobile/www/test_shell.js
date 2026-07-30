// Headless check of the mobile shell's host-discovery flow.
//   node mobile/www/test_shell.js
// Serves the shell + a stand-in control room and drives it with Chromium.
const http = require('http')
const fs = require('fs')
const path = require('path')
const { chromium } = require('playwright')

const SHELL_PORT = 4310
const ROOM_PORT = 4311

const shell = http.createServer((req, res) => {
  res.writeHead(200, { 'content-type': 'text/html' })
  res.end(fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8'))
})

const room = http.createServer((req, res) => {
  res.writeHead(200, { 'content-type': 'text/html' })
  res.end('<!doctype html><title>Control Room</title><h1 id="room">CONTROL ROOM</h1>')
})

const fail = (m) => { console.error('FAIL: ' + m); process.exitCode = 1 }
const pass = (m) => console.log('  ok  ' + m)

;(async () => {
  await new Promise((r) => shell.listen(SHELL_PORT, r))
  await new Promise((r) => room.listen(ROOM_PORT, r))

  const browser = await chromium.launch()

  // --- 1. Nothing reachable -> the shell asks for a host -------------------
  {
    const page = await browser.newPage()
    await page.goto(`http://localhost:${SHELL_PORT}/`)
    await page.waitForSelector('#f', { timeout: 8000 })
      .then(() => pass('falls back to the host prompt when nothing answers'))
      .catch(() => fail('never showed the host prompt'))

    // --- 2. Typing a live host connects -----------------------------------
    await page.fill('#h', `localhost:${ROOM_PORT}`)
    await page.click('button[type=submit]')
    await page.waitForSelector('#room', { timeout: 8000 })
      .then(() => pass('connects to a host typed by hand'))
      .catch(() => fail('did not navigate to the typed host'))
    await page.close()
  }

  // --- 3. The host is remembered next launch ------------------------------
  {
    const ctx = await browser.newContext()
    const page = await ctx.newPage()
    await page.goto(`http://localhost:${SHELL_PORT}/`)
    await page.waitForSelector('#f', { timeout: 8000 })
    await page.fill('#h', `localhost:${ROOM_PORT}`)
    await page.click('button[type=submit]')
    await page.waitForSelector('#room', { timeout: 8000 })

    await page.goto(`http://localhost:${SHELL_PORT}/`)   // relaunch, same storage
    await page.waitForSelector('#room', { timeout: 8000 })
      .then(() => pass('remembers the host and skips the prompt on relaunch'))
      .catch(() => fail('did not reuse the saved host'))
    await ctx.close()
  }

  // --- 4. Bare host gets the default port ---------------------------------
  {
    const ctx = await browser.newContext()
    const page = await ctx.newPage()
    await page.goto(`http://localhost:${SHELL_PORT}/`)
    await page.waitForSelector('#f', { timeout: 8000 })
    const normalised = await page.evaluate(() => normalise('192.168.1.42'))
    normalised === 'http://192.168.1.42:3005'
      ? pass('bare host gains the default port')
      : fail(`bad normalise result: ${normalised}`)
    await ctx.close()
  }

  await browser.close()
  shell.close(); room.close()
  console.log(process.exitCode ? '\nshell check FAILED' : '\nshell check passed')
})().catch((e) => { console.error(e); process.exit(1) })
