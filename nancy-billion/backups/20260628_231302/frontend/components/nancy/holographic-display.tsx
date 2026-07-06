'use client'

import { useEffect, useRef, useState } from 'react'
import { useSpring, animated } from '@react-spring/web'
import { JarvisUtils } from '@/lib/nancy/jarvis-utils'

interface HolographicDisplayProps {
  /** Content to display in the hologram */
  children: React.ReactNode
  /** Whether the display is active */
  active?: boolean
  /** Position offset from anchor point */
  offset?: { x: number; y: number; z: number }
  /** Scale of the holographic display */
  scale?: number
  /** Fade-in/fade-out duration in ms */
  transitionDuration?: number
  /** Color tint of the hologram */
  tint?: string
  /** Whether to enable environmental scanning for placement */
  enableEnvironmentalScan?: boolean
  /** Callback when user interacts with the display */
  onInteract?: () => void
}

export function HolographicDisplay({
  children,
  active = false,
  offset = { x: 0, y: 0, z: 0 },
  scale = 1,
  transitionDuration = 300,
  tint = '#38d3eb',
  enableEnvironmentalScan = false,
  onInteract
}: HolographicDisplayProps) {
  const [isVisible, setIsVisible] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  
  // Spring animation for smooth appearance/disappearance
  const { opacity, scale: scaleAnim } = useSpring({
    opacity: active ? 1 : 0,
    scale: scale,
    config: { duration: transitionDuration }
  })
  
  // Environmental scanning for smart placement
  useEffect(() => {
    if (enableEnvironmentalScan && typeof window !== 'undefined') {
      // Simple environmental awareness - in a full implementation this would
      // use actual AR/scene understanding APIs
      const handleVisibilityChange = () => {
        const isElementVisible = containerRef.current?.getBoundingClientRect()
        setIsVisible(active && !!isElementVisible)
      }
      
      window.addEventListener('scroll', handleVisibilityChange)
      window.addEventListener('resize', handleVisibilityChange)
      
      return () => {
        window.removeEventListener('scroll', handleVisibilityChange)
        window.removeEventListener('resize', handleVisibilityChange)
      }
    }
  }, [enableEnvironmentalScan, active])
  
  // Handle user interaction
  const handleClick = () => {
    onInteract?.()
    
    // Add subtle interaction feedback
    if (containerRef.current) {
      containerRef.current.style.transform = 'scale(0.95)'
      setTimeout(() => {
        containerRef.current.style.transform = 'scale(1)'
      }, 100)
    }
  }
  
  if (!isVisible && !active) return null
  
  return (
    <animated.div
      ref={containerRef}
      onClick={handleClick}
      className={`fixed pointer-events-none z-[50] ${active ? '' : 'pointer-events-none'}`}
      style={{
        opacity,
        transform: scaleAnim,
        left: '50%',
        top: '50%',
        transformOrigin: 'center',
        pointerEvents: active ? 'all' : 'none',
        ...offset
      }}
    >
      <div className="relative w-[300px] h-[200px] bg-black/50 backdrop-blur-md border border-[{tint}]/40 rounded-2xl shadow-[0_0_30px_{tint}]/50" 
           style={{ 
             borderColor: tint,
             boxShadow: `0 0 30px ${tint}80`,
             backgroundImage: `
               radial-gradient(circle at center, transparent 0%, ${tint}10 70%, transparent 100%),
               repeating-linear-gradient(45deg, ${tint}20 0px, ${tint}20 1px, transparent 1px, transparent 10px)
             `
           }}>
        {/* Holographic scan lines */}
        <div className="absolute inset-0 pointer-events-none" 
             style={{ 
               backgroundImage: `repeating-linear-gradient(0deg, ${tint}10 0px, ${tint}10 1px, transparent 1px, transparent 20px)`,
               pointerEvents: 'none'
             }}></div>
        
        {/* Content container */}
        <div className="relative p-4 h-full w-full overflow-hidden" 
             style={{ 
               color: tint,
               textShadow: `0 0 5px ${tint}80`,
               fontFeatureSettings: '"liga" 0, "calt" 0' // Disable ligatures for crisp tech font
             }}>
          <div className="h-full w-full overflow-y-auto">
            {children}
          </div>
          
          {/* Subtle animated border */}
          <div className="absolute inset-0 pointer-events-none" 
               style={{ 
                 border: `1px solid ${tint}30`,
                 borderRadius: '2xl',
                 animation: 'holographic-border-pulse 3s ease-in-out infinite'
               }}></div>
        </div>
        
        {/* Status indicator */}
        <div className="absolute bottom-2 right-2 w-4 h-4 rounded-full bg-[{tint}]/60 
                        animate-[pulse_2s_ease-in-out_infinite]" 
             style={{ 
               backgroundColor: tint,
               boxShadow: `0 0 8px ${tint}80`
             }}></div>
      </div>
    </animated.div>
  )
}

// CSS keyframes for holographic effects
if (typeof window !== 'undefined' && !document.getElementById('jarvis-holographic-styles')) {
  const style = document.createElement('style')
  style.id = 'jarvis-holographic-styles'
  style.textContent = `
    @keyframes holographic-border-pulse {
      0%, 100% { border-color: rgba(56, 211, 235, 0.3); }
      50% { border-color: rgba(56, 211, 235, 0.6); }
    }
    
    @keyframes pulse {
      0%, 100% { opacity: 0.6; }
      50% { opacity: 1; }
    }
  `
  document.head.appendChild(style)
}