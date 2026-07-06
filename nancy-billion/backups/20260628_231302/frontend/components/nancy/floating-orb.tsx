'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { NancyOrb, type OrbState } from './nancy-orb'
import { STATE_HINT } from '@/lib/nancy/labels'

const ORB = 132 // rendered orb size in px

/**
 * A small, draggable Nancy orb that docks bottom-right while a task surface is
 * open. The user can drag it anywhere inside the dashboard. Position persists
 * across re-renders and is clamped to the viewport on resize.
 */
export function FloatingOrb({ state }: { state: OrbState }) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null)
  const drag = useRef<{ dx: number; dy: number } | null>(null)
  const [dragging, setDragging] = useState(false)

  const clamp = useCallback((x: number, y: number) => {
    const pad = 8
    const maxX = window.innerWidth - ORB - pad
    const maxY = window.innerHeight - ORB - pad
    return {
      x: Math.max(pad, Math.min(maxX, x)),
      y: Math.max(pad, Math.min(maxY, y)),
    }
  }, [])

  // Default dock: bottom-right.
  useEffect(() => {
    setPos(clamp(window.innerWidth - ORB - 24, window.innerHeight - ORB - 96))
    const onResize = () =>
      setPos((cur) => (cur ? clamp(cur.x, cur.y) : cur))
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [clamp])

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    const el = ref.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    drag.current = { dx: e.clientX - rect.left, dy: e.clientY - rect.top }
    setDragging(true)
    el.setPointerCapture(e.pointerId)
  }, [])

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!drag.current) return
      setPos(clamp(e.clientX - drag.current.dx, e.clientY - drag.current.dy))
    },
    [clamp],
  )

  const onPointerUp = useCallback((e: React.PointerEvent) => {
    drag.current = null
    setDragging(false)
    ref.current?.releasePointerCapture(e.pointerId)
  }, [])

  if (!pos) return null

  return (
    <div
      ref={ref}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      className="fixed z-[600] flex touch-none select-none flex-col items-center"
      style={{
        left: pos.x,
        top: pos.y,
        width: ORB,
        cursor: dragging ? 'grabbing' : 'grab',
        transition: dragging ? 'none' : 'filter 0.3s ease',
        filter: dragging ? 'drop-shadow(0 0 18px var(--hud))' : undefined,
      }}
      role="button"
      aria-label="Nancy orb — drag to reposition"
    >
      <NancyOrb state={state} size={ORB} compact />
      <span className="-mt-2 rounded bg-background/70 px-1.5 py-0.5 font-heading text-[0.45rem] uppercase tracking-[0.25em] text-primary backdrop-blur-sm">
        {STATE_HINT[state]}
      </span>
    </div>
  )
}
