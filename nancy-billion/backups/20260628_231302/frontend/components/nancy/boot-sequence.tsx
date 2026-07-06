'use client'

import { useEffect, useRef, useState } from 'react'
import { ArcReactor } from './hud-bits'

const LINES = [
  'INITIALIZING NÅNCY KERNEL v9.4.1',
  'MOUNTING NEURAL SUBSTRATE ............ OK',
  'CALIBRATING ARC REACTOR ............. 100%',
  'LINKING STARK INDUSTRIES UPLINK ..... OK',
  'SPOOLING AUTONOMOUS AGENT SWARM ..... 6 ONLINE',
  'ACQUIRING ORBITAL SATELLITE FEED .... OK',
  'LOADING VOICE RECOGNITION MATRIX .... OK',
  'ENCRYPTION HANDSHAKE [AES-512] ...... SECURE',
  'ALL SYSTEMS NOMINAL',
]

export function BootSequence({ onDone }: { onDone: () => void }) {
  const [visible, setVisible] = useState<string[]>([])
  const [closing, setClosing] = useState(false)
  const idx = useRef(0)

  useEffect(() => {
    const interval = setInterval(() => {
      if (idx.current >= LINES.length) {
        clearInterval(interval)
        setTimeout(() => setClosing(true), 500)
        setTimeout(onDone, 1100)
        return
      }
      setVisible((v) => [...v, LINES[idx.current]])
      idx.current += 1
    }, 230)
    return () => clearInterval(interval)
  }, [onDone])

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-6 bg-background transition-opacity duration-500"
      style={{ opacity: closing ? 0 : 1 }}
    >
      <ArcReactor size={180} />
      <div className="font-heading text-2xl tracking-[0.4em] text-primary hud-glow">
        NÅNCY
      </div>
      <div className="h-44 w-[min(90vw,460px)] overflow-hidden rounded-md border border-border bg-card/40 p-3 text-[0.62rem] leading-relaxed">
        {visible.map((line, i) => {
          const text = line ?? ''
          return (
            <div key={i} className="flex gap-2 text-muted-foreground">
              <span className="text-primary/60">{'>'}</span>
              <span
                className={
                  text.includes('OK') ||
                  text.includes('SECURE') ||
                  text.includes('NOMINAL')
                    ? 'text-primary'
                    : 'text-foreground'
                }
              >
                {text}
              </span>
            </div>
          )
        })}
        <span className="ml-3 inline-block h-3 w-2 animate-pulse bg-primary align-middle" />
      </div>
    </div>
  )
}
