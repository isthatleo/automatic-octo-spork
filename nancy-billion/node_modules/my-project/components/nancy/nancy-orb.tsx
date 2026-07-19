'use client'

import { motion, AnimatePresence } from 'framer-motion'
import { useEffect, useMemo, useRef, useState } from 'react'
import { cn } from '@/lib/utils'

export type OrbState =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'speaking'
  | 'executing'
  | 'alert'

/*
  Aerospace/FUI HUD, built to an exact spec: independent concentric layers
  (core, breathing inner ring, atmospheric glow, a rotating arc, a counter-
  rotating dotted orbit, drifting ambient particles, a whole-HUD idle
  drift), each animated on its own clock so nothing synchronizes -- calm
  and premium rather than a game HUD.

  Framer Motion orchestrates every layer's continuous idle animation
  (durations/targets keyed off the current OrbState, so Framer smoothly
  retargets on a state change). Real mic/TTS amplitude drives a separate,
  ref-based layer on top -- the listening waveform ring and the speaking
  ripple bursts -- because that has to track actual sound in real time,
  not a fixed animation curve.
*/

const BLUE = '#4B8DFF'
const GOLD = '#DAB249'
const PLUM = '#978CAD'
const ALERT_C = '#E54C4A'

function alphaHex(hex: string, a: number): string {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r}, ${g}, ${b}, ${a})`
}

interface StateProfile {
  color: string
  label: string
  arcDuration: number
  dotDuration: number
  glowRange: [number, number]
  ringPulseMs: number | null
}

const PROFILES: Record<OrbState, StateProfile> = {
  idle:      { color: BLUE,    label: 'Standing by', arcDuration: 11, dotDuration: 48, glowRange: [0.4, 0.75], ringPulseMs: null },
  listening: { color: BLUE,    label: 'Listening',   arcDuration: 9,  dotDuration: 42, glowRange: [0.55, 0.9], ringPulseMs: null },
  thinking:  { color: PLUM,    label: 'Thinking',    arcDuration: 6,  dotDuration: 26, glowRange: [0.5, 0.88], ringPulseMs: 700 },
  speaking:  { color: BLUE,    label: 'Speaking',    arcDuration: 7,  dotDuration: 36, glowRange: [0.55, 0.95], ringPulseMs: null },
  executing: { color: GOLD,    label: 'Working',     arcDuration: 6,  dotDuration: 26, glowRange: [0.5, 0.88], ringPulseMs: 700 },
  alert:     { color: ALERT_C, label: 'Degraded',    arcDuration: 10, dotDuration: 50, glowRange: [0.5, 0.8], ringPulseMs: null },
}

interface AmbientParticle { x: number; y: number; driftX: number; driftY: number; duration: number; delay: number; size: number }

/** Deterministic scatter (no Math.random() per frame/render -- keeps
 * server/client render identical and the field stable across re-mounts). */
function buildAmbientParticles(count: number): AmbientParticle[] {
  return Array.from({ length: count }, (_, i) => {
    const s1 = ((i * 9301 + 49297) % 233280) / 233280
    const s2 = ((i * 4933 + 12345) % 99991) / 99991
    const s3 = ((i * 7919 + 7) % 65535) / 65535
    const angle = s1 * Math.PI * 2
    const radius = 40 + s2 * 22
    return {
      x: 50 + Math.cos(angle) * radius,
      y: 50 + Math.sin(angle) * radius,
      driftX: (s2 - 0.5) * 12,
      driftY: (s3 - 0.5) * 12,
      duration: 3 + s1 * 4,
      delay: s3 * 3,
      size: s2 > 0.72 ? 1.8 : 1,
    }
  })
}

function buildDots(count: number, radius: number) {
  return Array.from({ length: count }, (_, i) => {
    const a = (i / count) * Math.PI * 2
    return { x: 50 + Math.cos(a) * radius, y: 50 + Math.sin(a) * radius }
  })
}

/** Reads live microphone amplitude (0..1). Falls back to 0 silently. */
function useMicLevel(active: boolean) {
  const levelRef = useRef(0)
  useEffect(() => {
    if (!active || typeof navigator === 'undefined' || !navigator.mediaDevices) {
      levelRef.current = 0
      return
    }
    let raf = 0
    let stream: MediaStream | null = null
    let ctx: AudioContext | null = null
    let cancelled = false

    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((s) => {
        if (cancelled) {
          s.getTracks().forEach((t) => t.stop())
          return
        }
        stream = s
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const AC = window.AudioContext || (window as any).webkitAudioContext
        ctx = new AC()
        const src = ctx.createMediaStreamSource(s)
        const analyser = ctx.createAnalyser()
        analyser.fftSize = 256
        src.connect(analyser)
        const data = new Uint8Array(analyser.frequencyBinCount)
        const tick = () => {
          analyser.getByteTimeDomainData(data)
          let sum = 0
          for (let i = 0; i < data.length; i++) {
            const v = (data[i] - 128) / 128
            sum += v * v
          }
          const rms = Math.sqrt(sum / data.length)
          levelRef.current = Math.min(1, rms * 3.5)
          raf = requestAnimationFrame(tick)
        }
        tick()
      })
      .catch(() => {
        levelRef.current = 0
      })

    return () => {
      cancelled = true
      cancelAnimationFrame(raf)
      stream?.getTracks().forEach((t) => t.stop())
      ctx?.close().catch(() => {})
      levelRef.current = 0
    }
  }, [active])
  return levelRef
}

/** Reads live amplitude (0..1) from a playing <audio> element -- the real
 * NeuTTS output (see page.tsx's nancySay), not a fake "speaking" wiggle.
 * Falls back to 0 for the browser Web Speech API path, which exposes no
 * analyzable media element. */
function useElementAudioLevel(el: HTMLAudioElement | null) {
  const levelRef = useRef(0)
  useEffect(() => {
    if (!el) {
      levelRef.current = 0
      return
    }
    let raf = 0
    let ctx: AudioContext | null = null
    let cancelled = false
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const AC = window.AudioContext || (window as any).webkitAudioContext
      ctx = new AC()
      // A freshly-created AudioContext can start "suspended" since this
      // effect runs a tick after the triggering user gesture, not
      // synchronously inside it. If it stays suspended, createMediaElementSource
      // below silently reroutes the audio element's output into a graph that
      // never renders -- .play() succeeds, the transcript updates, but
      // nothing is actually heard. Explicitly resume; harmless no-op if
      // already running.
      ctx.resume().catch(() => {})
      const source = ctx.createMediaElementSource(el)
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 256
      source.connect(analyser)
      analyser.connect(ctx.destination) // keep the audio actually audible
      const data = new Uint8Array(analyser.frequencyBinCount)
      const tick = () => {
        if (cancelled) return
        analyser.getByteTimeDomainData(data)
        let sum = 0
        for (let i = 0; i < data.length; i++) {
          const v = (data[i] - 128) / 128
          sum += v * v
        }
        const rms = Math.sqrt(sum / data.length)
        levelRef.current = Math.min(1, rms * 3.5)
        raf = requestAnimationFrame(tick)
      }
      tick()
    } catch {
      levelRef.current = 0
    }
    return () => {
      cancelled = true
      cancelAnimationFrame(raf)
      ctx?.close().catch(() => {})
      levelRef.current = 0
    }
  }, [el])
  return levelRef
}

export interface OrbQuickNavItem {
  key: string
  label: string
  icon: React.ElementType
  active?: boolean
}

export function NancyOrb({
  state = 'idle',
  name = 'BILLION',
  size = 360,
  audioElement = null,
  quickNav,
  onQuickNav,
}: {
  state?: OrbState
  name?: string
  size?: number
  audioElement?: HTMLAudioElement | null
  /** When provided, clicking the core fans these out as a quick-nav ring
   * around it. Omit to keep an orb purely a status indicator (e.g. the
   * floating workspace-dock orb). */
  quickNav?: OrbQuickNavItem[]
  onQuickNav?: (key: string) => void
}) {
  const particles = useMemo(() => buildAmbientParticles(20), [])
  const dots = useMemo(() => buildDots(80, 49), [])
  const micLevel = useMicLevel(state === 'listening')
  const speakingLevel = useElementAudioLevel(audioElement)
  const [menuOpen, setMenuOpen] = useState(false)
  const [ripples, setRipples] = useState<{ id: number; x: number; y: number }[]>([])
  const rippleSeq = useRef(0)
  const [speakRipples, setSpeakRipples] = useState<{ id: number }[]>([])
  const speakRippleSeq = useRef(0)
  const waveformRef = useRef<SVGCircleElement>(null)
  const ampGlowRef = useRef<HTMLDivElement>(null)
  const coreRef = useRef<HTMLButtonElement>(null)
  const pulseRef = useRef<HTMLDivElement>(null)

  const profile = PROFILES[state]

  // Real haptic feedback (not just visual) on the moment Nancy actually
  // starts listening or speaking -- navigator.vibrate is a real browser
  // API, silently a no-op on desktop/unsupported browsers rather than
  // throwing, so this is safe everywhere.
  useEffect(() => {
    if (typeof navigator === 'undefined' || !navigator.vibrate) return
    if (state === 'listening') navigator.vibrate(30)
    else if (state === 'speaking') navigator.vibrate([20, 40, 20])
  }, [state])

  // Speaking: spawn a thin ripple ring outward every ~450ms while actually
  // speaking, real amplitude gates whether one fires -- a silent gap in
  // the audio doesn't spawn empty ripples.
  useEffect(() => {
    if (state !== 'speaking') return
    const iv = setInterval(() => {
      if (speakingLevel.current < 0.04) return
      const id = speakRippleSeq.current++
      setSpeakRipples((r) => [...r.slice(-3), { id }])
    }, 450)
    return () => clearInterval(iv)
  }, [state, speakingLevel])

  // Real-time amplitude layer -- the listening waveform ring, the
  // amplitude-synced glow boost, and a physical-feeling pulse/scale on the
  // whole HUD, updated every frame directly via refs (Framer Motion's
  // declarative `animate` targets aren't a good fit for continuous
  // real-audio data).
  useEffect(() => {
    let raf = 0
    const draw = () => {
      const live = state === 'listening' ? micLevel.current : state === 'speaking' ? speakingLevel.current : 0
      if (pulseRef.current) {
        pulseRef.current.style.transform = `scale(${1 + live * 0.045})`
      }
      if (waveformRef.current) {
        const r = 32 + live * 7
        waveformRef.current.setAttribute('r', String(r))
        waveformRef.current.setAttribute('opacity', String(live * 0.55))
      }
      if (ampGlowRef.current) {
        ampGlowRef.current.style.opacity = String(live * 0.5)
      }
      raf = requestAnimationFrame(draw)
    }
    draw()
    return () => cancelAnimationFrame(raf)
  }, [state, micLevel, speakingLevel])

  const onCoreClick = (e: React.MouseEvent<HTMLButtonElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const id = rippleSeq.current++
    setRipples((r) => [...r, { id, x: e.clientX - rect.left, y: e.clientY - rect.top }])
    setTimeout(() => setRipples((r) => r.filter((rp) => rp.id !== id)), 650)
    if (quickNav && quickNav.length > 0) setMenuOpen((v) => !v)
  }

  const hasQuickNav = !!quickNav && quickNav.length > 0
  const innerArcC = 2 * Math.PI * 38
  const outerArcC = 2 * Math.PI * 44

  return (
    <div className="flex flex-col items-center gap-4">
      {/* layer 7: idle drift -- the whole HUD wanders within +-2px, barely
          perceptible, so nothing on screen ever sits perfectly still. */}
      <motion.div
        className="relative flex items-center justify-center"
        style={{ width: size, height: size }}
        role="img"
        aria-label={`${name} — ${profile.label}`}
        animate={{ x: [0, 2, -2, 0], y: [0, -1.5, 1.5, 0] }}
        transition={{ duration: 10, repeat: Infinity, ease: 'easeInOut' }}
      >
      {/* real-time physical pulse -- the whole assembly scales fractionally
          with real amplitude while listening/speaking, on top of the
          haptic navigator.vibrate() burst fired on state entry above. */}
      <div ref={pulseRef} className="relative flex h-full w-full items-center justify-center transition-transform duration-100 ease-out">
        {/* layer 3: atmospheric glow -- idle ambient pulse (Framer) plus a
            real-amplitude boost layered on top (ref-driven). */}
        <motion.div
          className="absolute rounded-full"
          style={{ width: '92%', height: '92%', background: `radial-gradient(circle, ${alphaHex(profile.color, 0.9)} 0%, transparent 70%)`, filter: `blur(${size * 0.11}px)` }}
          animate={{ opacity: profile.glowRange, scale: [1, 1.1, 1] }}
          transition={{ duration: 5, repeat: Infinity, ease: 'easeInOut' }}
          aria-hidden
        />
        <div
          ref={ampGlowRef}
          className="pointer-events-none absolute rounded-full transition-colors duration-500"
          style={{ width: '92%', height: '92%', background: `radial-gradient(circle, ${alphaHex(profile.color, 1)} 0%, transparent 65%)`, filter: `blur(${size * 0.11}px)`, opacity: 0 }}
          aria-hidden
        />

        {/* ambient particles -- layer 6 */}
        {particles.map((p, i) => (
          <motion.div
            key={i}
            className="pointer-events-none absolute rounded-full bg-white"
            style={{ left: `${p.x}%`, top: `${p.y}%`, width: p.size, height: p.size }}
            animate={{ x: [0, p.driftX, 0], y: [0, p.driftY, 0], opacity: [0.2, 1, 0.2] }}
            transition={{ duration: p.duration, repeat: Infinity, ease: 'easeInOut', delay: p.delay }}
            aria-hidden
          />
        ))}

        <svg viewBox="0 0 100 100" className="absolute inset-0 overflow-visible">
          {/* layer 5: outer dotted orbit, counter-rotating */}
          <motion.g
            style={{ transformOrigin: '50px 50px' }}
            animate={{ rotate: -360 }}
            transition={{ duration: profile.dotDuration, repeat: Infinity, ease: 'linear' }}
          >
            {dots.map((d, i) => (
              <circle key={i} cx={d.x} cy={d.y} r={0.55} fill="white" fillOpacity={0.35} />
            ))}
          </motion.g>

          {/* longer, near-semi-circle arc -- innermost of the two, white,
              counter-rotating */}
          <motion.g
            style={{ transformOrigin: '50px 50px' }}
            animate={{ rotate: -360 }}
            transition={{ duration: profile.arcDuration * 1.6, repeat: Infinity, ease: 'linear' }}
          >
            <circle
              cx="50" cy="50" r="38"
              fill="none"
              stroke="white"
              strokeWidth="3.2"
              strokeLinecap="round"
              strokeDasharray={`${innerArcC * 0.46} ${innerArcC}`}
            />
          </motion.g>

          {/* layer 4: shorter arc -- outside the semi-circle, white, clockwise */}
          <motion.g
            style={{ transformOrigin: '50px 50px' }}
            animate={{ rotate: 360 }}
            transition={{ duration: profile.arcDuration, repeat: Infinity, ease: 'linear' }}
          >
            <circle
              cx="50" cy="50" r="44"
              fill="none"
              stroke="white"
              strokeWidth="2.6"
              strokeLinecap="round"
              strokeDasharray={`${outerArcC * (55 / 360)} ${outerArcC}`}
            />
          </motion.g>

          {/* layer 2: inner ring, breathing (or a fast 700ms pulse while
              processing) */}
          <motion.circle
            cx="50" cy="50" r="32"
            fill="none"
            stroke="white"
            strokeWidth="0.85"
            style={{ transformOrigin: '50px 50px', filter: `drop-shadow(0 0 ${size * 0.01}px ${alphaHex(profile.color, 0.8)})` }}
            animate={{
              scale: profile.ringPulseMs ? [1, 1.06, 1] : [1, 1.03, 1],
              opacity: profile.ringPulseMs ? [0.85, 1, 0.85] : [0.9, 1, 0.9],
            }}
            transition={{ duration: (profile.ringPulseMs ?? 6000) / 1000, repeat: Infinity, ease: 'easeInOut' }}
          />

          {/* real-time: listening waveform ring, tracks actual mic level */}
          <circle ref={waveformRef} cx="50" cy="50" r="32" fill="none" stroke={profile.color} strokeWidth="0.6" opacity={0} />

          {/* real-time: speaking ripple bursts, one per detected utterance beat */}
          <AnimatePresence>
            {speakRipples.map((r) => (
              <motion.circle
                key={r.id}
                cx="50" cy="50"
                fill="none"
                stroke={profile.color}
                strokeWidth="0.5"
                initial={{ r: 30, opacity: 0.55 }}
                animate={{ r: 50, opacity: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 1.2, ease: 'easeOut' }}
                onAnimationComplete={() => setSpeakRipples((prev) => prev.filter((x) => x.id !== r.id))}
              />
            ))}
          </AnimatePresence>
        </svg>

        {/* layer 1: core -- static dark disk, radial gradient, centred label */}
        <button
          ref={coreRef}
          type="button"
          onClick={onCoreClick}
          className="relative flex cursor-pointer items-center justify-center overflow-hidden rounded-full"
          style={{
            width: '48%',
            height: '48%',
            background: `radial-gradient(circle at 35% 30%, ${alphaHex(profile.color, 0.85)} 0%, ${alphaHex(profile.color, 0.22)} 55%, #05070d 100%)`,
            boxShadow: `0 ${size * 0.05}px ${size * 0.12}px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.08)`,
            transition: 'background 0.6s ease',
          }}
          title={hasQuickNav ? 'Open quick navigation' : name}
        >
          {ripples.map((r) => (
            <span
              key={r.id}
              className="pointer-events-none absolute rounded-full"
              style={{
                left: r.x, top: r.y, width: 4, height: 4,
                background: 'rgba(255,255,255,0.6)',
                transform: 'translate(-50%, -50%)',
                animation: 'hud-ripple 0.65s ease-out forwards',
              }}
            />
          ))}
          <span
            className="relative px-2 text-center"
            style={{ fontWeight: 300, letterSpacing: '0.09em', fontSize: size * 0.06, color: 'white', whiteSpace: 'nowrap' }}
          >
            {name}
          </span>
        </button>

        {/* quick-nav ring */}
        {hasQuickNav && (
          <div
            className={cn('pointer-events-none absolute inset-0 transition-opacity duration-300', menuOpen ? 'opacity-100' : 'opacity-0')}
            aria-hidden={!menuOpen}
          >
            {quickNav!.map((item, i) => {
              const n = quickNav!.length
              const angle = (i / n) * Math.PI * 2 - Math.PI / 2
              const radius = size * 0.44
              const x = Math.cos(angle) * radius
              const y = Math.sin(angle) * radius
              const Icon = item.icon
              return (
                <button
                  key={item.key}
                  type="button"
                  title={item.label}
                  onClick={() => { onQuickNav?.(item.key); setMenuOpen(false) }}
                  className={cn(
                    'absolute flex h-9 w-9 items-center justify-center rounded-full border transition-all duration-300',
                    menuOpen ? 'pointer-events-auto scale-100' : 'scale-0',
                    item.active
                      ? 'border-primary bg-primary/20 text-primary'
                      : 'border-border bg-card text-muted-foreground hover:border-primary/50 hover:text-foreground',
                  )}
                  style={{
                    left: '50%',
                    top: '50%',
                    transform: menuOpen ? `translate(calc(-50% + ${x}px), calc(-50% + ${y}px))` : 'translate(-50%, -50%)',
                    transitionDelay: menuOpen ? `${i * 30}ms` : '0ms',
                  }}
                >
                  <Icon className="h-4 w-4" />
                </button>
              )
            })}
          </div>
        )}
      </div>
      </motion.div>

      {/* caption below the core */}
      <div className="text-center">
        <div
          key={state}
          className="animate-[hud-fade-in_0.4s_ease] text-[0.7rem] transition-colors duration-500"
          style={{ color: state === 'idle' ? 'var(--muted-foreground)' : profile.color }}
        >
          {profile.label}
        </div>
      </div>
    </div>
  )
}
