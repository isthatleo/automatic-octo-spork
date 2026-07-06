'use client'

import { useEffect, useRef, useState } from 'react'

interface NeuralNetVizProps {
  /** Whether the visualization is active */
  active?: boolean
  /** Style of visualization: 'organic', 'circuit', 'holographic' */
  style?: 'organic' | 'circuit' | 'holographic'
  /** Number of layers in the network */
  layers?: number
  /** Neurons per layer */
  neuronsPerLayer?: number
  /** Activation level (0-1) */
  activationLevel?: number
  /** Whether to show pulse animations */
  showPulses?: boolean
  /** Pulse speed */
  pulseSpeed?: number
  /** Callback when a neuron is "activated" */
  onNeuronActivate?: (layer: number, neuron: number) => void
}

export function NeuralNetViz({
  active = true,
  style = 'holographic',
  layers = 5,
  neuronsPerLayer = 8,
  activationLevel = 0.3,
  showPulses = true,
  pulseSpeed = 1,
  onNeuronActivate
}: NeuralNetVizProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [isInitialized, setIsInitialized] = useState(false)
  const animationRef = useRef<number | null>(null)
  const [neuronStates, setNeuronStates] = useState<Array<Array<{ 
    active: boolean 
    energy: number 
    lastActivation: number 
  }>>>([])
  const [pulses, setPulses] = useState<Array<{ 
    layer: number 
    neuron: number 
    progress: number 
    startTime: number 
  }>>([])
  
  // Initialize neural network state
  useEffect(() => {
    if (!active || typeof window === 'undefined') {
      if (animationRef.current !== null) {
        cancelAnimationFrame(animationRef.current)
        animationRef.current = null
      }
      setIsInitialized(false)
      return
    }
    
    // Initialize neuron states
    const initialStates = Array.from({ length: layers }, (_, layerIdx) =>
      Array.from({ length: neuronsPerLayer }, (_, neuronIdx) => ({
        active: Math.random() < activationLevel,
        energy: Math.random() * 0.5 + 0.5,
        lastActivation: Date.now() - Math.random() * 5000
      }))
    )
    
    setNeuronStates(initialStates)
    setIsInitialized(true)
    
    // Start animation loop
    const animate = () => {
      // Update neuron states with some randomness
      const newStates = neuronStates.map((layer, layerIdx) =>
        layer.map((neuron, neuronIdx) => {
          // Randomly activate neurons based on activation level
          const shouldActivate = Math.random() < (activationLevel * 0.016) // ~60 per second at 30% activation
          
          let newActive = neuron.active
          let newEnergy = neuron.energy
          let newLastActivation = neuron.lastActivation
          
          if (shouldActivate && !neuron.active) {
            newActive = true
            newEnergy = Math.random() * 0.5 + 0.5
            newLastActivation = Date.now()
            
            // Notify of activation
            onNeuronActivate?.(layerIdx, neuronIdx)
          } else if (neuron.active) {
            // Energy decay when active
            newEnergy = Math.max(0, neuron.energy - 0.016)
            if (newEnergy <= 0) {
              newActive = false
            }
          }
          
          return {
            active: newActive,
            energy: newEnergy,
            lastActivation: newLastActivation
          }
        })
      )
      
      setNeuronStates(newStates)
      
      // Generate pulses for active neurons
      if (showPulses) {
        const newPulses: typeof pulses = []
        
        neuronStates.forEach((layer, layerIdx) => {
          layer.forEach((neuron, neuronIdx) => {
            if (neuron.active && neuron.energy > 0.7) {
              // Chance to generate a pulse
              if (Math.random() < 0.1) {
                newPulses.push({
                  layer: layerIdx,
                  neuron: neuronIdx,
                  progress: 0,
                  startTime: Date.now()
                })
              }
            }
          })
        })
        
        // Update existing pulses
        const updatedPulses = pulses
          .map(pulse => ({
            ...pulse,
            progress: Math.min(1, (Date.now() - pulse.startTime) / (1000 / pulseSpeed))
          }))
          .filter(pulse => pulse.progress < 1)
        
        setPulses([...newPulses, ...updatedPulses])
      }
      
      animationRef.current = requestAnimationFrame(animate)
    }
    
    animationRef.current = requestAnimationFrame(animate)
    
    // Cleanup
    return () => {
      if (animationRef.current !== null) {
        cancelAnimationFrame(animationRef.current)
        animationRef.current = null
      }
    }
  }, [active, activationLevel, layers, neuronsPerLayer, onNeuronActivate, showPulses, pulseSpeed])
  
  // Handle click to manually activate a neuron
  const handleContainerClick = (e: MouseEvent) => {
    if (!containerRef.current) return
    
    const rect = containerRef.current.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    
    const colWidth = rect.width / neuronsPerLayer
    const rowHeight = rect.height / layers
    
    const neuronCol = Math.floor(x / colWidth)
    const neuronRow = Math.floor(y / rowHeight)
    
    if (neuronCol >= 0 && neuronCol < neuronsPerLayer && 
        neuronRow >= 0 && neuronRow < layers) {
      
      // Activate the clicked neuron
      setNeuronStates(prev => 
        prev.map((layer, layerIdx) =>
          layer.map((neuron, neuronIdx) => {
            if (layerIdx === neuronRow && neuronIdx === neuronCol) {
              return {
                ...neuron,
                active: true,
                energy: 1.0,
                lastActivation: Date.now()
              }
            }
            return neuron
          })
        )
      )
      
      onNeuronActivate?.(neuronRow, neuronCol)
    }
  }
  
  if (!isInitialized) return null
  
  // Get color based on style
  const getNeuronColor = (energy: number, style: 'organic' | 'circuit' | 'holographic'): string => {
    const baseColors: Record<'organic' | 'circuit' | 'holographic', string> = {
      organic: '#10b981', // Emerald
      circuit: '#f59e0b', // Amber
      holographic: '#38d3eb' // Cyan
    }
    
    const baseColor = baseColors[style]
    // Convert to HSL, adjust lightness based on energy, convert back
    // Simplified: just adjust opacity
    return `${baseColor}${Math.round(energy * 255).toString(16).padStart(2, '0')}`
  }
  
  return (
    <div
      ref={containerRef}
      onClick={handleContainerClick}
      className="relative w-[260px] h-[260px] cursor-pointer"
      style={{
        background: style === 'organic' 
          ? 'radial-gradient(circle at center, #0f172a 0%, #020617 100%)'
          : style === 'circuit'
            ? 'repeating-linear-gradient(45deg, #0f172a 0px, #0f172a 4px, #1e293b 4px, #1e293b 8px)'
            : 'background: #020617; background-image: radial-gradient(circle at center, rgba(56,211,235,0.1) 0%, transparent 50%)' // holographic
      }}
    >
      {/* Connection lines between layers */}
      <div className="absolute inset-0 pointer-events-none"
           style={{
             pointerEvents: 'none'
           }}>
        {Array.from({ length: layers - 1 }, (_, layerIdx) => {
          return (
            <div key={`layer-conn-${layerIdx}`} className="absolute inset-0 pointer-events-none"
                 style={{
                   pointerEvents: 'none',
                   backgroundImage: `
                     repeating-linear-gradient(
                       45deg,
                       rgba(56,211,235,${style === 'holographic' ? 0.3 : 0.1}) 0px,
                       rgba(56,211,235,${style === 'holographic' ? 0.3 : 0.1}) 1px,
                       transparent 1px,
                       transparent 20px
                     )
                   `,
                   opacity: style === 'holographic' ? 0.4 : 0.2
                 }}></div>
          )
        })}
      </div>
      
      {/* Neurons */}
      <div className="absolute inset-0 pointer-events-none">
        {neuronStates.map((layer, layerIdx) =>
          layer.map((neuron, neuronIdx) => {
            const x = (neuronIdx + 0.5) / neuronsPerLayer * 100
            const y = (layerIdx + 0.5) / layers * 100
            
            // Find pulses for this neuron
            const neuronPulses = pulses.filter(
              p => p.layer === layerIdx && p.neuron === neuronIdx
            )
            
            return (
              <div key={`neuron-${layerIdx}-${neuronIdx}`} 
                   className="absolute pointer-events-none"
                   style={{
                     left: `${x}%`,
                     top: `${y}%`,
                     width: '8px',
                     height: '8px',
                     background: `radial-gradient(
                       circle at center,
                       ${getNeuronColor(neuron.energy, style)} 0%,
                       ${getNeuronColor(neuron.energy * 0.5, style)} 70%,
                       transparent 100%
                     )`,
                     border: `1px solid ${getNeuronColor(neuron.energy, style)}80`,
                     boxShadow: neuron.active 
                       ? `0 0 8px ${getNeuronColor(neuron.energy, style)}80,
                          inset 0 0 3px ${getNeuronColor(neuron.energy, style)}40`
                       : '0 0 2px transparent',
                     transform: `scale(${neuron.active && showPulses ? 1 + neuron.energy * 0.5 : 1})`,
                     transition: 'transform 0.1s ease',
                     opacity: neuron.energy
                   }}>{neuronPulses.map((pulse, pulseIdx) => (
                    <div key={`pulse-${layerIdx}-${neuronIdx}-${pulseIdx}`} 
                         className="absolute inset-0 pointer-events-none"
                         style={{
                           border: `2px solid ${getNeuronColor(neuron.energy, style)}${
                             Math.round(pulse.progress * 255)
                           }`,
                           borderRadius: '50%',
                           opacity: 0.3 * (1 - pulse.progress)
                         }}></div>
                  ))}
                </div>
            )
          }))
        )}
      </div>
      
      {/* Activation level indicator */}
      <div className="absolute bottom-2 left-2 right-2 h-0.5"
           style={{
             background: `linear-gradient(
               to right,
               transparent 0%,
               ${getNeuronColor(activationLevel, style)} ${activationLevel * 100}%,
               transparent ${activationLevel * 100}% 100%
             )`,
             height: '2px'
           }}></div>
      
      {/* Style indicator */}
      <div className="absolute top-2 left-2 text-xs font-medium"
           style={{
             color: style === 'organic' ? '#10b981' :
                    style === 'circuit' ? '#f59e0b' :
                    '#38d3eb',
             textShadow: '0 0 3px rgba(0,0,0,0.5)'
           }}>
            {style.charAt(0).toUpperCase() + style.slice(1)}
          </div>
    </div>
  )
}

// CSS keyframes for neural network visualization
if (typeof window !== 'undefined' && !document.getElementById('jarvis-neural-net-styles')) {
  const style = document.createElement('style')
  style.id = 'jarvis-neural-net-styles'
  style.textContent = `
    @keyframes neural-pulse {
      0%, 100% { transform: scale(1); opacity: 0.7; }
      50% { transform: scale(1.3); opacity: 0.4; }
    }
    
    @keyframes energy-wave {
      0% { background-position: 0% 50%; }
      100% { background-position: 100% 50%; }
    }
  `
  document.head.appendChild(style)
}