'use client'

import { motion } from 'framer-motion'

/**
 * Shared decorative backdrop for the premium full-screen boards (Mission
 * Control, Kanban). A faint animated dot-grid plus a few very slow drifting
 * glow blobs in the existing ember/gold/tertiary tokens — no new palette,
 * no particle library. Kept deliberately quiet: this is ambience, not a
 * light show, so every layer sits under 10% opacity.
 */
export function AmbientField() {
  return (
    <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden" aria-hidden>
      <div className="hud-dot-grid absolute inset-0 opacity-[0.05]" />
      <motion.div
        className="absolute -left-24 top-[-10%] h-[46vw] w-[46vw] max-h-[560px] max-w-[560px] rounded-full"
        style={{ background: 'radial-gradient(circle, var(--hud) 0%, transparent 70%)', opacity: 0.08 }}
        animate={{ x: [0, 40, -10, 0], y: [0, 30, 10, 0] }}
        transition={{ duration: 26, repeat: Infinity, ease: 'easeInOut' }}
      />
      <motion.div
        className="absolute right-[-8%] top-[20%] h-[38vw] w-[38vw] max-h-[480px] max-w-[480px] rounded-full"
        style={{ background: 'radial-gradient(circle, var(--gold) 0%, transparent 70%)', opacity: 0.06 }}
        animate={{ x: [0, -30, 20, 0], y: [0, -20, 15, 0] }}
        transition={{ duration: 32, repeat: Infinity, ease: 'easeInOut' }}
      />
      <motion.div
        className="absolute bottom-[-12%] left-[30%] h-[34vw] w-[34vw] max-h-[420px] max-w-[420px] rounded-full"
        style={{ background: 'radial-gradient(circle, var(--tertiary) 0%, transparent 70%)', opacity: 0.05 }}
        animate={{ x: [0, 25, -25, 0], y: [0, -15, 10, 0] }}
        transition={{ duration: 38, repeat: Infinity, ease: 'easeInOut' }}
      />
    </div>
  )
}
