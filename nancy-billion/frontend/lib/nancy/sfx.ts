'use client'

/**
 * JARVIS-style Web Audio sound engine.
 * All SFX are synthesized on the fly — no assets required.
 */

let ctx: AudioContext | null = null
let master: GainNode | null = null
let enabled = true
let hum: { osc: OscillatorNode; gain: GainNode } | null = null

function ac(): AudioContext | null {
  if (typeof window === 'undefined') return null
  if (ctx) return ctx
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const AC = window.AudioContext || (window as any).webkitAudioContext
    ctx = new AC()
    master = ctx.createGain()
    master.gain.value = 0.35
    master.connect(ctx.destination)
    return ctx
  } catch {
    return null
  }
}

export function setSfxEnabled(v: boolean) {
  enabled = v
  if (!v) stopHum()
}

/** Must be called from a user gesture to unlock audio on iOS/Safari. */
export function unlockSfx() {
  const c = ac()
  if (!c) return
  if (c.state === 'suspended') c.resume().catch(() => {})
}

function env(g: GainNode, now: number, peak: number, a: number, d: number) {
  g.gain.setValueAtTime(0, now)
  g.gain.linearRampToValueAtTime(peak, now + a)
  g.gain.exponentialRampToValueAtTime(0.0001, now + a + d)
}

function tone(freq: number, dur: number, type: OscillatorType = 'sine', peak = 0.25, delay = 0) {
  const c = ac()
  if (!c || !master || !enabled) return
  const t = c.currentTime + delay
  const osc = c.createOscillator()
  const g = c.createGain()
  osc.type = type
  osc.frequency.setValueAtTime(freq, t)
  osc.connect(g)
  g.connect(master)
  env(g, t, peak, 0.005, dur)
  osc.start(t)
  osc.stop(t + dur + 0.05)
}

function sweep(f0: number, f1: number, dur: number, type: OscillatorType = 'sawtooth', peak = 0.18) {
  const c = ac()
  if (!c || !master || !enabled) return
  const t = c.currentTime
  const osc = c.createOscillator()
  const g = c.createGain()
  const bp = c.createBiquadFilter()
  bp.type = 'bandpass'
  bp.frequency.value = (f0 + f1) / 2
  bp.Q.value = 6
  osc.type = type
  osc.frequency.setValueAtTime(f0, t)
  osc.frequency.exponentialRampToValueAtTime(Math.max(30, f1), t + dur)
  osc.connect(bp).connect(g).connect(master)
  env(g, t, peak, 0.01, dur - 0.01)
  osc.start(t)
  osc.stop(t + dur + 0.05)
}

function noise(dur: number, peak = 0.12, filterHz = 2000) {
  const c = ac()
  if (!c || !master || !enabled) return
  const t = c.currentTime
  const buf = c.createBuffer(1, Math.floor(c.sampleRate * dur), c.sampleRate)
  const data = buf.getChannelData(0)
  for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1
  const src = c.createBufferSource()
  src.buffer = buf
  const bp = c.createBiquadFilter()
  bp.type = 'bandpass'
  bp.frequency.value = filterHz
  bp.Q.value = 0.8
  const g = c.createGain()
  src.connect(bp).connect(g).connect(master)
  env(g, t, peak, 0.005, dur - 0.005)
  src.start(t)
  src.stop(t + dur + 0.05)
}

/* ─── Public SFX ─────────────────────────────────────────────────── */

export const sfx = {
  /** Short high blip — UI acknowledgement */
  blip() { tone(1180, 0.09, 'sine', 0.22); tone(1760, 0.06, 'sine', 0.12, 0.02) },
  /** Wake-word detected chirp */
  wake() { tone(880, 0.08, 'triangle', 0.22); tone(1320, 0.1, 'sine', 0.2, 0.06) },
  /** Command confirmed */
  confirm() {
    tone(660, 0.09, 'triangle', 0.2)
    tone(990, 0.12, 'sine', 0.2, 0.08)
    tone(1320, 0.14, 'sine', 0.15, 0.16)
  },
  /** Error / unknown */
  error() { tone(220, 0.18, 'sawtooth', 0.18); tone(180, 0.22, 'square', 0.14, 0.05) },
  /** Panel opening whoosh */
  whooshIn() { sweep(180, 1400, 0.55, 'sawtooth', 0.14); noise(0.35, 0.06, 3200) },
  /** Panel closing whoosh */
  whooshOut() { sweep(1400, 180, 0.5, 'sawtooth', 0.14); noise(0.3, 0.05, 2200) },
  /** Descending / scanning zoom */
  scan() {
    sweep(2200, 240, 1.4, 'sine', 0.12)
    tone(440, 0.12, 'sine', 0.14, 0.4)
    tone(660, 0.1, 'sine', 0.12, 0.9)
  },
  /** Boot chime */
  boot() {
    tone(392, 0.18, 'sine', 0.22, 0)
    tone(523, 0.22, 'sine', 0.22, 0.14)
    tone(659, 0.26, 'sine', 0.22, 0.32)
    tone(1046, 0.5, 'triangle', 0.18, 0.55)
    sweep(120, 1200, 0.9, 'sawtooth', 0.08)
  },
  /** Radar ping */
  ping() { tone(1760, 0.05, 'sine', 0.14); tone(880, 0.35, 'sine', 0.1, 0.03) },
  /** Target acquired */
  lock() {
    tone(1200, 0.05, 'square', 0.12)
    tone(1200, 0.05, 'square', 0.12, 0.09)
    tone(1600, 0.14, 'sine', 0.2, 0.2)
  },
  /** Ambient reactor hum (loops until stopped) */
  startHum() {
    const c = ac()
    if (!c || !master || !enabled || hum) return
    const osc = c.createOscillator()
    const g = c.createGain()
    const lp = c.createBiquadFilter()
    lp.type = 'lowpass'
    lp.frequency.value = 260
    osc.type = 'sawtooth'
    osc.frequency.value = 55
    osc.connect(lp).connect(g).connect(master)
    g.gain.value = 0
    g.gain.linearRampToValueAtTime(0.045, c.currentTime + 1.2)
    osc.start()
    hum = { osc, gain: g }
  },
}

export function stopHum() {
  const c = ac()
  if (!c || !hum) return
  hum.gain.gain.cancelScheduledValues(c.currentTime)
  hum.gain.gain.linearRampToValueAtTime(0, c.currentTime + 0.4)
  const h = hum
  hum = null
  setTimeout(() => { try { h.osc.stop() } catch {} }, 500)
}

/**
 * Duck the master briefly to squash any overlapping tails when the user
 * spam-clicks nav / dock. Prevents "audio glitch" pile-ups.
 */
export function duckSfx(durMs = 180) {
  const c = ac()
  if (!c || !master) return
  const t = c.currentTime
  const g = master.gain
  const prev = g.value
  g.cancelScheduledValues(t)
  g.setValueAtTime(prev, t)
  g.linearRampToValueAtTime(0.0001, t + 0.03)
  g.linearRampToValueAtTime(prev, t + durMs / 1000)
}

