'use client'

import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'
import { Heart, Zap, Activity, Brain, Folder, Users, Shield, Monitor, Code, Globe, TrendingUp, Sparkles, ZapOff, Clock, History } from 'lucide-react'

export function MemoryCrystalPanel({ onLog }: { onLog: (entry: Omit<import('@/lib/nancy/types').LogEntry, 'id'>) => void }) {
  const [memoryCrystals, setMemoryCrystals] = useState<Array<{
    id: string
    type: 'experience' | 'lesson' | 'pattern' | 'principle' | 'wisdom'
    clarity: number
    stability: number
    resonance: number
    age: number
    connections: number
    lastAccessed: string
  }>>([
    { id: 'exp-001', type: 'experience', clarity: 85, stability: 70, resonance: 60, age: 2, connections: 12, lastAccessed: '2 hours ago' },
    { id: 'exp-002', type: 'experience', clarity: 92, stability: 85, resonance: 75, age: 1, connections: 8, lastAccessed: '45 minutes ago' },
    { id: 'les-001', type: 'lesson', clarity: 78, stability: 90, resonance: 80, age: 3, connections: 15, lastAccessed: '1 day ago' },
    { id: 'pat-001', type: 'pattern', clarity: 88, stability: 95, resonance: 92, age: 5, connections: 23, lastAccessed: '3 days ago' },
    { id: 'pri-001', type: 'principle', clarity: 95, stability: 98, resonance: 96, age: 8, connections: 31, lastAccessed: '1 week ago' },
    { id: 'wis-001', type: 'wisdom', clarity: 98, stability: 99, resonance: 98, age: 12, connections: 45, lastAccessed: '2 weeks ago' }
  ]))
  const [selectedCrystal, setSelectedCrystal] = useState<string | null>(null)
  const [memoryStats, setMemoryStats] = useState({
    totalMemories: 12450,
    crystalizedMemories: 156,
    clarityAvg: 82.3,
    stabilityAvg: 76.8,
    resonanceAvg: 71.2,
    memoryGrowth: 3.4
  })

  // Simulate memory crystallization process
  useEffect(() => {
    const simulateCrystallization = () => {
      // Occasionally promote experiences to lessons, lessons to patterns, etc.
      if (Math.random() > 0.95) { // 5% chance of progression
        const expIndex = Math.floor(Math.random() * memoryCrystals.length)
        const crystal = memoryCrystals[expIndex]
        
        if (crystal.type === 'experience' && crystal.clarity > 80 && crystal.stability > 75) {
          // Promote experience to lesson
          setMemoryCrystals(prev => 
            prev.map((c, i) => 
              i === expIndex 
                ? {...c, type: 'lesson', clarity: Math.min(95, c.clarity + 5), stability: Math.min(95, c.stability + 10)} 
                : c
            )
          )
          onLog({ level: 'info', message: 'Experience crystallized into Lesson' })
        } else if (crystal.type === 'lesson' && crystal.clarity > 85 && crystal.stability > 85) {
          // Promote lesson to pattern
          setMemoryCrystals(prev => 
            prev.map((c, i) => 
              i === expIndex 
                ? {...c, type: 'pattern', clarity: Math.min(95, c.clarity + 3), stability: Math.min(98, c.stability + 3)} 
                : c
            )
          )
          onLog({ level: 'info', message: 'Lesson crystallized into Pattern' })
        } else if (crystal.type === 'pattern' && crystal.clarity > 90 && crystal.stability > 90) {
          // Promote pattern to principle
          setMemoryCrystals(prev => 
            prev.map((c, i) => 
              i === expIndex 
                ? {...c, type: 'principle', clarity: Math.min(98, c.clarity + 2), stability: 99} 
                : c
            )
          )
          onLog({ level: 'info', message: 'Pattern crystallized into Principle' })
        } else if (crystal.type === 'principle' && crystal.clarity > 95) {
          // Promote principle to wisdom
          setMemoryCrystals(prev => 
            prev.map((c, i) => 
              i === expIndex 
                ? {...c, type: 'wisdom', clarity: 99, stability: 99, resonance: Math.min(99, c.resonance + 2)} 
                : c
            )
          )
          onLog({ level: 'info', message: 'Principle crystallized into Wisdom' })
        }
      }
      
      // Update access times and connection strengths
      setMemoryCrystals(prev => 
        prev.map(crystal => ({
          ...crystal,
          lastAccessed: Math.random() > 0.7 
            ? `${Math.floor(Math.random() * 5)} minutes ago` 
            : crystal.lastAccessed,
          connections: Math.max(0, crystal.connections + (Math.round(Math.random()) * 2 - 1)), // Random walk
          clarity: Math.max(0, Math.min(100, crystal.clarity + (Math.random() - 0.5) * 2)),
          stability: Math.max(0, Math.min(100, crystal.stability + (Math.random() - 0.5) * 1.5)),
          resonance: Math.max(0, Math.min(100, crystal.resonance + (Math.random() - 0.5) * 2))
        }))
      )
      
      // Update stats
      setMemoryStats(prev => ({
        totalMemories: prev.totalMemories + Math.floor(Math.random() * 8),
        crystalizedMemories: Math.min(500, prev.crystalizedMemories + Math.floor(Math.random() * 3)),
        clarityAvg: Math.max(0, Math.min(100, prev.clarityAvg + (Math.random() - 0.5) * 0.5)),
        stabilityAvg: Math.max(0, Math.min(100, prev.stabilityAvg + (Math.random() - 0.5) * 0.3)),
        resonanceAvg: Math.max(0, Math.min(100, prev.resonanceAvg + (Math.random() - 0.5) * 0.4)),
        memoryGrowth: Math.max(0, Math.min(10, prev.memoryGrowth + (Math.random() - 0.5) * 0.5))
      }))
    }
    
    const interval = setInterval(simulateCrystallization, 5000)
    simulateCrystallization() // Initial call
    
    return () => clearInterval(interval)
  }, [memoryCrystals.length])

  const crystalTypeColors: Record<string, string> = {
    experience: 'bg-blue-500/20 border-blue-500/40',
    lesson: 'bg-green-500/20 border-green-500/40',
    pattern: 'bg-purple-500/20 border-purple-500/40',
    principle: 'bg-orange-500/20 border-orange-500/40',
    wisdom: 'bg-red-500/20 border-red-500/40'
  }

  const crystalTypeIcons: Record<string, any> = {
    experience: Experience,
    lesson: Lesson,
    pattern: Pattern,
    principle: Principle,
    wisdom: Wisdom
  }

  const getCrystalIcon = (type: string) => {
    switch (type) {
      case 'experience': return <Activity className="h-4 w-4" />
      case 'lesson': return <Brain className="h-4 w-4" />
      case 'pattern': return <Zap className="h-4 w-4" />
      case 'principle': return <Shield className="h-4 w-4" />
      case 'wisdom': return <Heart className="h-4 w-4" />
      default: return <Activity className="h-4 w-4" />
    }
  }

  const handleCrystalClick = (crystalId: string) => {
    setSelectedCrystal(crystalId)
    const crystal = memoryCrystals.find(c => c.id === crystalId)
    if (crystal) {
      onLog({ level: 'info', message: `Accessed memory crystal: ${crystal.id} (${crystal.type})` })
      
      // Simulate accessing the memory (increases resonance slightly)
      setMemoryCrystals(prev => 
        prev.map(c => 
          c.id === crystalId 
            ? {...c, resonance: Math.min(100, c.resonance + 2), lastAccessed: 'Just now'} 
            : c
        )
      )
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4 pb-2 border-b border-hud/20">
        <h2 className="text-xl font-bold text-hud/100 font-heading">
          <Heart className="mr-2 h-4 w-4 animate-pulse" /> MEMORY CRYSTAL
        </h2>
        <div className="flex items-center space-x-2 text-xs text-hud/40">
          <span className="text-hud/40">Memory Crystallization System</span>
        </div>
      </div>

      {/* Memory Statistics */}
      <div className="bg-gray-900/50 border border-hud/20 rounded-xl p-4">
        <h3 className="font-semibold text-hud/80 mb-3">MEMORY STATISTICS</h3>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-hud/60">Total Memories</span>
              <span className="font-mono text-hud/40">{memoryStats.totalMemories.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-hud/60">Crystalized Memories</span>
              <span className="font-mono text-hud/40">{memoryStats.crystalizedMemories.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-hud/60">Average Clarity</span>
              <span className="font-mono text-hud/40">{memoryStats.clarityAvg.toFixed(1)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-hud/60">Average Stability</span>
              <span className="font-mono text-hud/40">{memoryStats.stabilityAvg.toFixed(1)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-hud/60">Average Resonance</span>
              <span className="font-mono text-hud/40">{memoryStats.resonanceAvg.toFixed(1)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-hud/60">Memory Growth Rate</span>
              <span className="font-mono text-hud/40">+{memoryStats.memoryGrowth.toFixed(1)}%/day</span>
            </div>
          </div>
          
          {/* Memory Type Distribution */}
          <div className="mt-4">
            <div className="flex justify-between mb-1">
              <span className="text-hud/60">Memory Type Distribution</span>
              <span className="text-xs text-hud/40">5 Stages of Crystallization</span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs text-hud/50">
              {['experience', 'lesson', 'pattern', 'principle', 'wisdom'].map(type => {
                const count = memoryCrystals.filter(c => c.type === type).length
                return (
                  <div key={type} className="flex items-center">
                    <div className="w-2 h-2 rounded mr-1" 
                         className={crystalTypeColors[type]}></div>
                    <span>{type.charAt(0).toUpperCase() + type.slice(1)}</span>
                    <span className="ml-2">({count})</span>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Memory Crystal Visualization */}
      <div className="bg-gray-900/50 border border-hud/20 rounded-xl p-4">
        <h3 className="font-semibold text-hud/80 mb-3">MEMORY CRYSTAL LATTICE</h3>
        <div className="relative h-96 bg-black/50 overflow-hidden">
          {/* Crystal lattice background */}
          <div className="absolute inset-0" 
               style={{
                 backgroundImage: 
                   'repeating-linear-gradient(0deg, hsla(210, 80%, 20%, 0.05) 0%, hsla(210, 80%, 20%, 0.05) 1px, transparent 1px, transparent 20%),' +
                   'repeating-linear-gradient(90deg, hsla(210, 80%, 20%, 0.05) 0%, hsla(210, 80%, 20%, 0.05) 1px, transparent 1px, transparent 20%)',
                 backgroundSize: '20px 20px',
                 opacity: '0.2'
               }}></div>
          
          {/* Crystal formations */}
          <div className="absolute inset-0 flex items-center justify-center">
            {memoryCrystals.map((crystal, index) => {
              const angle = (index / memoryCrystals.length) * Math.PI * 2
              const baseRadius = 80
              const radiusVariance = Math.sin(Date.now() * 0.001 + index) * 10
              const radius = baseRadius + radiusVariance + (crystal.clarity / 100) * 20
              const x = Math.cos(angle) * radius
              const y = Math.sin(angle) * radius
              const scale = 0.6 + (crystal.clarity / 100) * 0.4
              const opacity = 0.3 + (crystal.resonance / 100) * 0.4
              
              return (
                <div key={crystal.id} 
                     className="absolute"
                     style={{
                       left: `calc(50% + ${x}px)`,
                       top: `calc(50% + ${y}px)`,
                       width: `${40 * scale}px`,
                       height: `${40 * scale}px`,
                       background: `radial-gradient(circle at center, ${crystalTypeColors[crystal.type].replace('/20', '/40')} 0%, transparent 70%)`,
                       border: `2px solid ${crystalTypeColors[crystal.type].replace('/20', '/60')}`,
                       borderRadius: '50%',
                       transform: `scale(${scale})`,
                       opacity: `${opacity.toFixed(2)}`,
                       transition: 'transform 0.3s ease, opacity 0.3s ease'
                     }}
                     onClick={() => handleCrystalClick(crystal.id)}
                     onMouseEnter={() => {
                       // Slight pulse on hover
                       const crystalEl = document.querySelector(`[data-crystal-id="${crystal.id}"]`) as HTMLElement
                       if (crystalEl) {
                         crystalEl.style.transform = `scale(${scale * 1.2})`
                         crystalEl.style.opacity = `${Math.min(0.9, opacity + 0.2)}`
                       }
                     }}
                     onMouseLeave={() => {
                       // Return to normal state
                       const crystalEl = document.querySelector(`[data-crystal-id="${crystal.id}"]`) as HTMLElement
                       if (crystalEl) {
                         crystalEl.style.transform = `scale(${scale})`
                         crystalEl.style.opacity = `${opacity.toFixed(2)}`
                       }
                     }}
                >
                  {/* Crystal Core */}
                  <div className="absolute inset-0 flex items-center justify-center"
                       style={{
                         pointerEvents: 'none'
                       }}>
                    <div className="w-6 h-6 bg-white/10 rounded-full 
                             border border-white/20 
                             flex items-center justify-center">
                      {getCrystalIcon(crystal.type)}
                    </div>
                    {/* Crystal Label */}
                    <div className="absolute bottom-0 left-0 right-0 bg-black/80 text-xs text-center text-hud/60 p-1"
                         style={{
                           pointerEvents: 'none',
                           whiteSpace: 'nowrap',
                           overflow: 'hidden',
                           textOverflow: 'ellipsis'
                         }}>
                      {crystal.id}
                    </div>
                    {/* Resonance Indicator */}
                    <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-hud to-hud/20"
                         style={{
                           pointerEvents: 'none',
                           width: `${crystal.resonance}%`
                         }}></div>
                  </div>
                </div>
              )}
              
              {/* Connection lines between related crystals */}
              <div className="absolute inset-0 pointer-events-none" 
                   style={{
                     pointerEvents: 'none'
                   }}>
                {memoryCrystals.map((crystal1, i1) => 
                  memoryCrystals.map((crystal2, i2) => {
                    if (i1 >= i2) return null // Avoid duplicates and self-connections
                    
                    // Only show connections for highly related crystals (simplified logic)
                    const shouldConnect = 
                      Math.random() > 0.7 && // 30% chance of connection
                      crystal1.clarity > 70 && 
                      crystal2.clarity > 70
                    
                    if (!shouldConnect) return null
                    
                    const pos1 = {
                      x: Math.cos((i1 / memoryCrystals.length) * Math.PI * 2) * 
                           (80 + Math.sin(Date.now() * 0.001 + i1) * 10 + (crystal1.clarity / 100) * 20),
                      y: Math.sin((i1 / memoryCrystals.length) * Math.PI * 2) * 
                           (80 + Math.sin(Date.now() * 0.001 + i1) * 10 + (crystal1.clarity / 100) * 20)
                    }
                    
                    const pos2 = {
                      x: Math.cos((i2 / memoryCrystals.length) * Math.PI * 2) * 
                           (80 + Math.sin(Date.now() * 0.001 + i2) * 10 + (crystal2.clarity / 100) * 20),
                      y: Math.sin((i2 / memoryCrystals.length) * Math.PI * 2) * 
                           (80 + Math.sin(Date.now() * 0.001 + i2) * 10 + (crystal2.clarity / 100) * 20)
                    }
                    
                    return (
                      <div key={`conn-${crystal1.id}-${crystal2.id}`} 
                           className="absolute"
                           style={{
                             left: `calc(50% + ${((pos1.x + pos2.x) / 2)}px)`,
                             top: `calc(50% + ${((pos1.y + pos2.y) / 2)}px)`,
                             width: `${Math.sqrt(Math.pow((pos2.x - pos1.x), 2) + Math.pow((pos2.y - pos1.y), 2))}px`,
                             height: '1px',
                             background: `linear-gradient(to right, transparent, ${crystalTypeColors[crystal1.type].replace('/20', '/40')}, transparent)`,
                             transformOrigin: 'left',
                             transform: `rotate(${Math.atan2(pos2.y - pos1.y, pos2.x - pos1.x) * (180 / Math.PI)}deg)`,
                             opacity: '0.3'
                           }}
                      />
                    )
                  })
                )
                .flat()
                .filter(Boolean): any[]}
              </div>
            </div>
          </div>
        </div>

      {/* Selected Crystal Details */}
      {selectedCrystal && (
        <div className="bg-gray-900/50 border border-hud/20 rounded-xl p-4">
          <h3 className="font-semibold text-hud/80 mb-3">CRYSTAL DETAILS</h3>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-hud/60">Crystal ID</span>
              <span className="font-mono text-hud/40">{selectedCrystal}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-hud/60">Type</span>
              <span className="font-mono text-hud/40">
                {memoryCrystals.find(c => c.id === selectedCrystal)?.type 
                  ?.charAt(0).toUpperCase() + 
                  memoryCrystals.find(c => c.id === selectedCrystal)?.type.slice(1) || 'UNKNOWN'}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-hud/60">Clarity</span>
              <span className="font-mono text-hud/40">{memoryCrystals.find(c => c.id === selectedCrystal)?.clarity || 0}%</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-hud/60">Stability</span>
              <span className="font-mono text-hud/40">{memoryCrystals.find(c => c.id === selectedCrystal)?.stability || 0}%</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-hud/60">Resonance</span>
              <span className="font-mono text-hud/40">{memoryCrystals.find(c => c.id === selectedCrystal)?.resonance || 0}%</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-hud/60">Age</span>
              <span className="font-mono text-hud/40">{memoryCrystals.find(c => c.id === selectedCrystal)?.age || 0} cycles</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-hud/60">Connections</span>
              <span className="font-mono text-hud/40">{memoryCrystals.find(c => c.id === selectedCrystal)?.connections || 0}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-hud/60">Last Accessed</span>
              <span className="font-mono text-hud/40">{memoryCrystals.find(c => c.id === selectedCrystal)?.lastAccessed || 'Unknown'}</span>
            </div>
          </div>
          
          {/* Crystal Insights */}
          <div className="mt-4 pt-3 border-t border-hud/20">
            <h4 className="font-semibold text-hud/80 mb-2">CRYSTAL INSIGHTS</h4>
            <p className="text-hud/60">
              This memory crystal represents a {memoryCrystals.find(c => c.id === selectedCrystal)?.type === 'wisdom' 
                ? 'profound insight that has stood the test of time and experience' 
                : memoryCrystals.find(c => c.id === selectedCrystal)?.type === 'principle'
                ? 'fundamental truth that guides decision-making and action'
                : memoryCrystals.find(c => c.id === selectedCrystal)?.type === 'pattern'
                ? 'recurring observation that reveals underlying structure'
                : memoryCrystals.find(c => c.id === selectedCrystal)?.type === 'lesson'
                ? 'hard-won understanding gained through experience'
                : 'raw experience awaiting processing and integration'}
            </p>
            <div className="mt-3">
              <p className="text-hud/50 italic">
                "The clarity of this crystal reflects the precision of understanding, 
                its stability the reliability of application, 
                and its resonance the depth of connection to other knowledge."
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}