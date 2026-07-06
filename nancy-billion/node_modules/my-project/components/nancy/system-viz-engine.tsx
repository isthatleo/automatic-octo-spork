'use client'

import { useEffect, useRef, useState } from 'react'

interface SystemVizEngineProps {
  /** Whether the visualization is active */
  active?: boolean
  /** Visualization style: 'orthographic', 'perspective', 'schematic' */
  style?: 'orthographic' | 'perspective' | 'schematic'
  /** Auto-rotate the visualization */
  autoRotate?: boolean
  /** Rotation speed */
  rotationSpeed?: number
  /** Callback when a division is selected */
  onDivisionSelect?: (divisionId: string) => void
  /** Highlight specific divisions */
  highlightedDivisions?: string[]
  /** Show data flows between divisions */
  showDataFlows?: boolean
}

export function SystemVizEngine({
  active = true,
  style = 'orthographic',
  autoRotate = true,
  rotationSpeed = 0.5,
  onDivisionSelect,
  highlightedDivisions = [],
  showDataFlows = true
}: SystemVizEngineProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [isInitialized, setIsInitialized] = useState(false)
  const [rotationAngle, setRotationAngle] = useState(0)
  const animationRef = useRef<number | null>(null)
  
  // Initialize the visualization
  useEffect(() => {
    if (!active || typeof window === 'undefined') {
      if (animationRef.current !== null) {
        cancelAnimationFrame(animationRef.current)
        animationRef.current = null
      }
      setIsInitialized(false)
      return
    }
    
    setIsInitialized(true)
    
    // Start animation loop
    const animate = () => {
      if (autoRotate) {
        setRotationAngle(prev => (prev + rotationSpeed) % 360)
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
  }, [active, autoRotate, rotationSpeed])
  
  // Handle container clicks for division selection
  const handleContainerClick = (e: MouseEvent) => {
    if (!containerRef.current || !onDivisionSelect) return
    
    const rect = containerRef.current.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    
    // In a real implementation, we'd do proper raycasting or hit detection
    // For this prototype, we'll use simplified region detection
    
    const division = getDivisionAtPosition(x, y, rect.width, rect.height)
    if (division) {
      onDivisionSelect(division)
    }
  }
  
  // Get division at screen position (simplified)
  const getDivisionAtPosition = (x: number, y: number, width: number, height: number): string | null => {
    // Define approximate regions for each division (in a real 3D viz, this would be proper hit testing)
    const divisions: Record<string, { x: number; y: number; width: number; height: number }> = {
      chief_autonomy_division: { x: 0.1, y: 0.1, width: 0.15, height: 0.15 },
      learning_division: { x: 0.35, y: 0.1, width: 0.15, height: 0.15 },
      systems_control_division: { x: 0.6, y: 0.1, width: 0.15, height: 0.15 },
      perception_division: { x: 0.85, y: 0.1, width: 0.15, height: 0.15 },
      strategic_planning_division: { x: 0.1, y: 0.4, width: 0.15, height: 0.15 },
      ethics_governance_division: { x: 0.35, y: 0.4, width: 0.15, height: 0.15 },
      interface_division: { x: 0.6, y: 0.4, width: 0.15, height: 0.15 },
      evolution_division: { x: 0.85, y: 0.4, width: 0.15, height: 0.15 }
    }
    
    const normX = x / width
    const normY = y / height
    
    for (const [divisionId, region] of Object.entries(divisions)) {
      if (
        normX >= region.x && 
        normX <= region.x + region.width &&
        normY >= region.y && 
        normY <= region.y + region.height
      ) {
        return divisionId
      }
    }
    
    return null
  }
  
  // Get color for a division based on its state
  const getDivisionColor = (divisionId: string): string => {
    const divisionColors: Record<string, string> = {
      chief_autonomy_division: '#ef4444', // Red - autonomy/security
      learning_division: '#f59e0b', // Amber - learning/knowledge
      systems_control_division: '#6366f1', // Indigo - control/systems
      perception_division: '#10b981', // Emerald - perception/sensing
      strategic_planning_division: '#8b5cf6', // Violet - strategy/planning
      ethics_governance_division: '#ec4899', // Pink - ethics/governance
      interface_division: '#06b6d4', // Cyan - interface/interaction
      evolution_division: '#84cc16' // Lime - evolution/improvement
    }
    
    return divisionColors[divisionId] || '#6b7280' // Default gray
  }
  
  // Get division label
  const getDivisionLabel = (divisionId: string): string => {
    const divisionLabels: Record<string, string> = {
      chief_autonomy_division: 'Autonomy',
      learning_division: 'Learning',
      systems_control_division: 'Systems Control',
      perception_division: 'Perception',
      strategic_planning_division: 'Strategic Planning',
      ethics_governance_division: 'Ethics & Governance',
      interface_division: 'Interface',
      evolution_division: 'Evolution'
    }
    
    return divisionLabels[divisionId] || divisionId
  }
  
  if (!isInitialized) return null
  
  return (
    <div
      ref={containerRef}
      onClick={handleContainerClick}
      className="relative w-[300px] h-[300px] cursor-pointer"
      style={{
        perspective: style === 'perspective' ? '1000px' : 'none'
      }}
    >
      {/* Background grid */}
      <div className="absolute inset-0 pointer-events-none"
           style={{
             backgroundImage: `
               repeating-linear-gradient(
                 0deg,
                 rgba(56,211,235,0.1) 0px,
                 rgba(56,211,235,0.1) 1px,
                 transparent 1px,
                 transparent 20px
               ),
               repeating-linear-gradient(
                 90deg,
                 rgba(56,211,235,0.1) 0px,
                 rgba(56,211,235,0.1) 1px,
                 transparent 1px,
                 transparent 20px
               )
             `,
             opacity: style === 'schematic' ? 0.3 : 0.1
           }}></div>
      
      {/* Division nodes */}
      <div className="absolute inset-0 pointer-events-none"
           style={{
             transform: `rotateY(${rotationSpeed > 0 ? rotationAngle : 0}deg)`
           }}>
        {[ 
          'chief_autonomy_division',
          'learning_division', 
          'systems_control_division',
          'perception_division',
          'strategic_planning_division',
          'ethics_governance_division',
          'interface_division',
          'evolution_division'
        ].map((divisionId, index) => {
          const isHighlighted = highlightedDivisions.includes(divisionId)
          const isSelected = false // Would be tracked in state in a full implementation
          
          const size = isHighlighted || isSelected ? 0.12 : 0.1
          const xPos = 0.15 + (index % 4) * 0.25
          const yPos = 0.1 + Math.floor(index / 4) * 0.3
          
          return (
            <div
              key={divisionId}
              className="absolute pointer-events-none"
              style={{
                left: `${xPos * 100}%`,
                top: `${yPos * 100}%`,
                width: `${size * 100}%`,
                height: `${size * 100}%`,
                transform: `translate(-50%, -50%)`,
                background: `radial-gradient(
                  circle at center,
                  ${getDivisionColor(divisionId)}20 0%,
                  ${getDivisionColor(divisionId)}40 60%,
                  transparent 80%
                )`,
                border: `2px solid ${getDivisionColor(divisionId)}40`,
                boxShadow: isHighlighted || isSelected
                  ? `0 0 15px ${getDivisionColor(divisionId)}80, inset 0 0 5px ${getDivisionColor(divisionId)}40`
                  : '0 0 5px transparent',
                opacity: style === 'schematic' ? 0.8 : 0.6,
                transition: 'all 0.3s ease'
              }}
              title={getDivisionLabel(divisionId)}
            >
              {/* Division label */}
              {style === 'schematic' && (
                <div className="absolute bottom-[-120%] left-1/2 -translate-x-1/2
                              text-xs text-center font-medium
                              text-white
                              ">
                  {getDivisionLabel(divisionId)}
                </div>
              )}
              
              {/* Activity indicator */}
              <div className="absolute inset-0 
                            ${isHighlighted ? 'animate-[pulse_2s_ease_in_out_infinite]' : ''}
                            ${isSelected ? 'animate-[ring_1_5s_ease_in_out_infinite]' : ''}"
                   style={{
                     border: `2px solid ${getDivisionColor(divisionId)}${
                       isHighlighted ? '80' : isSelected ? '60' : '40'
                     }`,
                     borderRadius: '50%',
                     opacity: isHighlighted || isSelected ? 0.7 : 0
                   }}></div>
            </div>
          )
        )}
      </div>
      
      {/* Data flow connections */}
      {showDataFlows && (
        <div className="absolute inset-0 pointer-events-none"
             style={{
               transform: `rotateY(${rotationSpeed > 0 ? rotationAngle : 0}deg)`
             }}>
          {/* Define some example data flows between divisions */}
          {[ 
            { from: 'chief_autonomy_division', to: 'interface_division', type: 'status' },
            { from: 'learning_division', to: 'strategic_planning_division', type: 'insights' },
            { from: 'perception_division', to: 'chief_autonomy_division', type: 'alerts' },
            { from: 'interface_division', to: 'learning_division', type: 'feedback' },
            { from: 'evolution_division', to: 'chief_autonomy_division', type: 'optimizations' },
            { from: 'strategic_planning_division', to: 'systems_control_division', type: 'directives' }
          ].map((flow, index) => (
            <div
              key={`flow-${index}`}
              className="absolute pointer-events-none"
              style={{
                // Calculate positions based on division locations
                left: '50%',
                top: '50%',
                width: '2px',
                height: '80px',
                background: `linear-gradient(
                  to bottom,
                  transparent 0%,
                  ${getDivisionColor(flow.from)}40 40%,
                  ${getDivisionColor(flow.to)}40 60%,
                  transparent 100%
                )`,
                transformOrigin: 'top center',
                // In a real implementation, we'd calculate proper curves
                transform: `rotate(${index * 15}deg) translateY(-40px)`,
                opacity: style === 'schematic' ? 0.4 : 0.2
              }}
            >
              {/* Flow label */}
              {style === 'schematic' && (
                <div className="absolute bottom-[120%] left-1/2 -translate-x-1/2
                              text-xs text-center font-medium
                              text-white
                              ">
                  {flow.type}
                </div>
              )}
            </div>
          ))}
        </div>
      }
      
      {/* Center core */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none"
           style={{
             transform: `rotateY(${rotationSpeed > 0 ? rotationAngle : 0}deg)`
           }}>
        <div className="w-[60px] h-[60px] rounded-full
                        bg-gradient-to-r from-gray-900 via-gray-800 to-gray-950
                        border-2 border-gray-700
                        box-shadow: inset 0 0 10px rgba(255,255,255,0.1),
                                  0 0 15px rgba(56,211,235,0.3)">
          <div className="flex items-center justify-center text-xs font-medium text-white">
            CORE
          </div>
        </div>
      </div>
      
      {/* Rotation indicator */}
      {autoRotate && (
        <div className="absolute bottom-2 left-1/2 -translate-x-1/2
                        w-4 h-4 rounded-full bg-gray-600/60
                        animate-[spin_3s_linear_infinite]"></div>
      )}
    </div>
  )
}

// CSS keyframes for system visualization
if (typeof window !== 'undefined' && !document.getElementById('jarvis-system-viz-styles')) {
  const style = document.createElement('style')
  style.id = 'jarvis-system-viz-styles'
  style.textContent = `
    @keyframes pulse {
      0%, 100% { opacity: 0.6; }
      50% { opacity: 1; }
    }
    
    @keyframes ring {
      0% { transform: scale(0.8); opacity: 0; }
      100% { transform: scale(1.2); opacity: 0; }
    }
    
    @keyframes spin {
      from { transform: rotate(0deg); }
      to { transform: rotate(360deg); }
    }
  `
  document.head.appendChild(style)
}