'use client'

import { useEffect, useRef, useState } from 'react'

interface EnvironmentalScannerProps {
  /** Whether environmental scanning is active */
  active?: boolean
  /** Scan frequency in ms */
  scanInterval?: number
  /** Maximum scan range in meters */
  range?: number
  /** Callback when environment data is updated */
  onEnvironmentUpdate?: (data: {
    surfaces: Array<{ type: string; distance: number; normal: { x: number; y: number; z: number } }>
    lighting: { ambient: number; directional: { angle: number; intensity: number } }
    obstacles: Array<{ distance: number; size: { width: number; height: number; depth: number } }>
  }) => void
}

export function EnvironmentalScanner({
  active = false,
  scanInterval = 1000,
  range = 5,
  onEnvironmentUpdate
}: EnvironmentalScannerProps) {
  const scannerRef = useRef<number | null>(null)
  const [isScanning, setIsScanning] = useState(false)
  const [lastScanTime, setLastScanTime] = useState<number | null>(null)
  const [environmentData, setEnvironmentData] = useState<{
    surfaces: Array<{ type: string; distance: number; normal: { x: number; y: number; z: number } }>
    lighting: { ambient: number; directional: { angle: number; intensity: number } }
    obstacles: Array<{ distance: number; size: { width: number; height: number; depth: number } }>
  } | null>(null)
  
  // Simulate environmental scanning (in reality, this would use device sensors or AR APIs)
  const simulateEnvironmentalScan = async () => {
    if (!active) return
    
    setIsScanning(true)
    
    // Simulate scan delay
    try {
      await new Promise(resolve => setTimeout(resolve, Math.random() * 200 + 100)) // Simulate variable scan time
      
      // Generate simulated environmental data
      const simulatedData = {
        surfaces: [
          {
            type: 'wall',
            distance: Math.random() * range,
            normal: { x: Math.random() * 2 - 1, y: 0, z: Math.random() * 2 - 1 }
          },
          {
            type: 'floor',
            distance: Math.random() * 2,
            normal: { x: 0, y: 1, z: 0 }
          },
          {
            type: 'desk',
            distance: Math.random() * 3,
            normal: { x: Math.random() * 2 - 1, y: 0, z: Math.random() * 2 - 1 }
          }
        ].filter(s => s.distance > 0.5 && s.distance <= range),
        
        lighting: {
          ambient: Math.random() * 0.3 + 0.4,
          directional: {
            angle: Math.random() * Math.PI * 2,
            intensity: Math.random() * 0.6 + 0.2
          }
        },
        
        obstacles: Array.from({ length: Math.floor(Math.random() * 3) }, () => ({
          distance: Math.random() * range,
          size: {
            width: Math.random() * 2 + 0.5,
            height: Math.random() * 2 + 0.5,
            depth: Math.random() * 2 + 0.5
          }
        })).filter(o => o.distance > 0.3)
      }
      
      setEnvironmentData(simulatedData)
      setLastScanTime(Date.now())
      setIsScanning(false)
      
      // Call update callback if provided
      onEnvironmentUpdate?.(simulatedData)
      
      // Send data to backend API (in a real implementation)
      try {
        await fetch('/api/environmental', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(simulatedData)
        })
      } catch (error) {
        console.warn('Failed to send environmental data to backend:', error)
        // Continue anyway - local updates are still valuable
      }
    } catch (error) {
      console.error('Error in environmental scan:', error)
      setIsScanning(false)
    }
  }
  
  // Start scanning when active
  useEffect(() => {
    if (!active) {
      if (scannerRef.current !== null) {
        clearInterval(scannerRef.current)
        scannerRef.current = null
      }
      setIsScanning(false)
      return
    }
    
    // Start scanning interval
    scannerRef.current = window.setInterval(() => {
      simulateEnvironmentalScan()
    }, scanInterval)
    
    // Initial scan
    simulateEnvironmentalScan()
    
    // Cleanup
    return () => {
      if (scannerRef.current !== null) {
        clearInterval(scannerRef.current)
        scannerRef.current = null
      }
    }
  }, [active, scanInterval])
  
  // Manual scan trigger
  const triggerScan = () => {
    if (active && !isScanning) {
      simulateEnvironmentalScan()
    }
  }
  
  // Visual indicator for scanning
  if (!isScanning && !environmentData) return null
  
  return (
    <div className={`absolute inset-0 pointer-events-none ${isScanning ? 'animate-pulse' : ''}`}>
      <div className="absolute inset-0" 
           style={{
             background: 'radial-gradient(circle at center, rgba(56,211,235,0.1) 0%, transparent 70%)',
             pointerEvents: 'none',
             animation: isScanning ? 'environmental-scan-pulse 2s ease-in-out infinite' : 'none'
           }}></div>
      
      {/* Scan lines visualization */}
      <div className="absolute inset-0 pointer-events-none" 
           style={{
             backgroundImage: `
               repeating-linear-gradient(
                 45deg,
                 rgba(56,211,235,0.2) 0px,
                 rgba(56,211,235,0.2) 1px,
                 transparent 1px,
                 transparent 20px
               )
             `,
             pointerEvents: 'none',
             opacity: isScanning ? 0.3 : 0.1
           }}></div>
      
      {/* Status indicator */}
      <div className="absolute bottom-2 right-2 w-4 h-4 rounded-full 
                        bg-[rgba(56,211,235,0.6)] 
                        ${isScanning ? 'animate-pulse' : ''}"
           style={{
             boxShadow: `0 0 8px rgba(56,211,235,0.8)`
           }}></div>
    </div>
  )
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