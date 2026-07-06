'use client'

import { useEffect, useState } from 'react'

export function HudOverlay() {
  const [time, setTime] = useState(0)

  useEffect(() => {
    const interval = setInterval(() => {
      setTime(prev => prev + 16) // ~60fps
    }, 16)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="fixed inset-0 pointer-events-none z-50">
      {/* HUD Corner Markers */}
      <div className="hud-corner top-left">
        <div className="hud-line hud-horizontal" style={{ width: '80px' }}></div>
        <div className="hud-line hud-vertical" style={{ height: '80px' }}></div>
      </div>
      <div className="hud-corner top-right">
        <div className="hud-line hud-horizontal" style={{ width: '80px' }}></div>
        <div className="hud-line hud-vertical" style={{ height: '80px' }}></div>
      </div>
      <div className="hud-corner bottom-left>
        <div className="hud-line hud-horizontal" style={{ width: '80px' }}></div>
        <div className="hud-line hud-vertical" style={{ height: '80px' }}></div>
      </div>
      <div className="hud-corner bottom-right>
        <div className="hud-line hud-horizontal" style={{ width: '80px' }}></div>
        <div className="hud-line hud-vertical" style={{ height: '80px' }}></div>
      </div>

      {/* Central HUD Elements */}
      <div className="hud-center">
        <div className="hud-ring animate-hud-spin">
          <div className="absolute inset-0 rounded-full border-2 border-hud/30 animate-hud-pulse"></div>
        </div>
        
        {/* Frequency spectrum analyzer */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute bottom-0 left-1/2 transform -translate-x-1/2 h-[60px] w-[160px]">
            {/* Simulated frequency bars */}
            {[...Array(16)].map((_, i) => (
              <div key={i} 
                   className="absolute bottom-0 left-[calc(100%*_(1/16))] w-[4px] bg-hud/40"
                   style={{ 
                     height: `${Math.sin(time * 0.005 + i) * 20 + 30}px`,
                     transformOrigin: 'bottom',
                     animation: `pulse-${i} 1.5s ease-in-out infinite`,
                     animationDelay: `${i * 0.1}s`
                   }}
              />
            ))}
          </div>
        </div>
        
        {/* Data streams */}
        <div className="hud-data-top">
          <div className="hud-data-item">SYSTEM STATUS: <span className="text-hud/100">NOMINAL</span></div>
          <div className="hud-data-item">AI CORE: <span className="text-hud/100">ONLINE</span></div>
          <div className="hud-data-item">NETWORK: <span className="text-hud/100">SECURE</span></div>
          <div className="hud-data-item">POWER: <span className="text-hud/100">OPTIMAL</span></div>
        </div>
        
        <div className="hud-data-bottom>
          <div className="hud-data-item">UTC: <span className="text-hud/100">{new Date().toUTCString().substring(12, 20)}</span></div>
          <div className="hud-data-item">SESSION: <span className="text-hud/100">ACTIVE</span></div>
          <div className="hud-data-item">USER: <span className="text-hud/100">LEO</span></div>
          <div className="hud-data-item">LOCATION: <span className="text-hud/100">KAMPALA</span></div>
          <div className="hud-data-item">ENV: <span className="text-hud/100">{getEnvironmentalStatus()}</span></div>
        </div>
      </div>

      {/* Floating HUD elements */}
      <div className="absolute inset-0 pointer-events-none">
        {/* Left floating data */}
        <div className="absolute left-4 top-1/4 space-y-2 text-xs text-hud/60">
          <div>MEMORY: <span className="text-hud/100">47%</span></div>
          <div>PROCESS: <span className="text-hud/100">12/64</span></div>
          <div>THREAT: <span className="text-hud/100">NONE</span></div>
          <div>TEMP: <span className="text-hud/100">37°C</span></div>
        </div>
        
        {/* Right floating data */}
        <div className="absolute right-4 top-1/4 space-y-2 text-xs text-hud/60">
          <div>BANDWIDTH: <span className="text-hud/100">1.2GB/s</span></div>
          <div>LATENCY: <span className="text-hud/100">12ms</span></div>
          <div>SECURITY: <span className="text-hud/100">MAX</span></div>
          <div>INTEGRITY: <span className="text-hud/100">99.8%</span></div>
        </div>
      </div>
    </div>
  )
  
  const getEnvironmentalStatus = (): string => {
    // In a real implementation, this would get data from the environmental service
    // For now, we'll return a simulated status based on time
    const hour = new Date().getHours()
    if (hour >= 6 && hour < 18) {
      return 'DAYLIGHT'
    } else if (hour >= 18 && hour < 20) {
      return 'DUSK'
    } else {
      return 'NIGHT'
    }
  }
}

// CSS keyframes for environmental scanning effects
if (typeof window !== 'undefined' && !document.getElementById('jarvis-environmental-styles')) {
  const style = document.createElement('style')
  style.id = 'jarvis-environmental-styles'
  style.textContent = `
    @keyframes environmental-scan-pulse {
      0%, 100% { opacity: 0.2; }
      50% { opacity: 0.5; }
    }
  `
  document.head.appendChild(style)
}