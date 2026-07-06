'use client'

import { useEffect, useState, useRef } from 'react'
import { cn } from '@/lib/utils'
import { Globe, Brain, Zap, Folder, Activity, Users, Heart, Sparkles, TrendingUp, Search, Link } from 'lucide-react'

export function KnowledgeUniversePanel({ onLog }: { onLog: (entry: Omit<import('@/lib/nancy/types').LogEntry, 'id'>) => void }) {
  const [universeData, setUniverseData] = useState({
    galaxies: 5,
    solarSystems: 23,
    planets: 156,
    moons: 89,
    satellites: 342,
    wormholes: 12
  })
  const [explorationStats, setExplorationStats] = useState({
    distanceTraveled: 1247.5,
    discoveriesToday: 8,
    knowledgeDensity: 4.2,
    explorationRate: 0.7
  })
  const [selectedNode, setSelectedNode] = useState<string | null>(null)
  const [isExploring, setIsExploring] = useState(false)
  const animationRef = useRef<number | null>(null)

  // Simulate universe data updates
  useEffect(() => {
    const updateUniverse = () => {
      setUniverseData(prev => ({
        galaxies: prev.galaxies,
        solarSystems: prev.solarSystems + (Math.random() > 0.95 ? 1 : 0),
        planets: prev.planets + Math.floor(Math.random() * 3),
        moons: prev.moons + Math.floor(Math.random() * 5),
        satellites: prev.satellites + Math.floor(Math.random() * 10),
        wormholes: prev.wormholes + (Math.random() > 0.99 ? 1 : 0)
      }))
      
      setExplorationStats(prev => ({
        distanceTraveled: parseFloat((prev.distanceTraveled + Math.random() * 0.5).toFixed(1)),
        discoveriesToday: prev.discoveriesToday + (Math.random() > 0.9 ? 1 : 0),
        knowledgeDensity: parseFloat((Math.random() * 0.3 + 4.0).toFixed(1)),
        explorationRate: parseFloat((Math.random() * 0.2 + 0.6).toFixed(1))
      }))
    }
    
    const interval = setInterval(updateUniverse, 5000)
    updateUniverse() // Initial call
    
    return () => clearInterval(interval)
  }, [])

  // Animation loop for exploration
  useEffect(() => {
    if (isExploring) {
      const animate = () => {
        // Simulate exploration animation
        setExplorationStats(prev => ({
          distanceTraveled: parseFloat((prev.distanceTraveled + 0.1).toFixed(1)),
          discoveriesToday: Math.floor(Math.random() * 10) === 0 ? prev.discoveriesToday + 1 : prev.discoveriesToday,
          knowledgeDensity: parseFloat((Math.random() * 0.2 + 4.1).toFixed(1)),
          explorationRate: parseFloat((Math.random() * 0.3 + 0.5).toFixed(1))
        }))
        
        animationRef.current = requestAnimationFrame(animate)
      }
      
      animationRef.current = requestAnimationFrame(animate)
      return () => {
        if (animationRef.current) {
          cancelAnimationFrame(animationRef.current)
        }
      }
    }
  }, [isExploring])

  const handleNodeClick = (nodeType: string, nodeName: string) => {
    setSelectedNode(`${nodeType}: ${nodeName}`)
    onLog({ level: 'info', message: `Exploring knowledge node: ${nodeType} - ${nodeName}` })
  }

  const startExploration = () => {
    setIsExploring(true)
    onLog({ level: 'info', message: 'Started knowledge universe exploration' })
  }

  const stopExploration = () => {
    setIsExploring(false)
    onLog({ level: 'info', message: 'Paused knowledge universe exploration' })
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4 pb-2 border-b border-hud/20">
        <h2 className="text-xl font-bold text-hud/100 font-heading">
          <Globe className="mr-2 h-4 w-4 animate-spin" /> KNOWLEDGE UNIVERSE
        </h2>
        <div className="flex items-center space-x-2 text-xs text-hud/40">
          <button 
            onClick={isExploring ? stopExploration : startExploration}
            className={`px-3 py-1 rounded text-hud/60 hover:bg-hud/10 hover:text-hud/100 ${isExploring ? 'bg-hud/20' : ''}`}
          >
            {isExploring ? '⏸ Pause' : '▶ Explore'}
          </button>
          <span className="text-hud/40">{isExploring ? 'Exploring...' : 'Paused'}</span>
        </div>
      </div>

      {/* Universe Statistics */}
      <div className="bg-gray-900/50 border border-hud/20 rounded-xl p-4">
        <h3 className="font-semibold text-hud/80 mb-3">UNIVERSE STATISTICS</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="text-center">
            <div className="text-2xl font-bold text-hud/100">{universeData.galaxies}</div>
            <p className="text-xs text-hud/50">Galaxies</p>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-hud/100">{universeData.solarSystems}</div>
            <p className="text-xs text-hud/50">Solar Systems</p>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-hud/100">{universeData.planets}</div>
            <p className="text-xs text-hud/50">Planets</p>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-hud/100">{universeData.moons}</div>
            <p className="text-xs text-hud/50">Moons</p>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-hud/100">{universeData.satellites}</div>
            <p className="text-xs text-hud/50">Satellites</p>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-hud/100">{universeData.wormholes}</div>
            <p className="text-xs text-hud/50">Wormholes</p>
          </div>
        </div>
      </div>

      {/* Exploration Metrics */}
      <div className="bg-gray-900/50 border border-hud/20 rounded-xl p-4">
        <h3 className="font-semibold text-hud/80 mb-3">EXPLORATION METRICS</h3>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-hud/60">Distance Traveled</span>
              <span className="font-mono text-hud/40">{explorationStats.distanceTraveled.toFixed(1)} ly</span>
            </div>
            <div className="flex justify-between">
              <span className="text-hud/60">Discoveries Today</span>
              <span className="font-mono text-hud/40">{explorationStats.discoveriesToday}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-hud/60">Knowledge Density</span>
              <span className="font-mono text-hud/40">{explorationStats.knowledgeDensity}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-hud/60">Exploration Rate</span>
              <span className="font-mono text-hud/40">{explorationStats.explorationRate}</span>
            </div>
          </div>
          
          {/* Exploration Progress Bar */}
          <div className="mt-4">
            <div className="flex justify-between mb-1">
              <span className="text-hud/60">Exploration Progress</span>
              <span className="text-xs text-hud/40">{(explorationStats.distanceTraveled / 5000 * 100).toFixed(1)}%</span>
            </div>
            <div className="w-full bg-gray-800/50 h-2 rounded overflow-hidden">
              <div className="bg-gradient-to-r from-hud to-hud/20 h-full" 
                   style={{ width: `${Math.min(100, explorationStats.distanceTraveled / 5000 * 100)}%` }}></div>
            </div>
          </div>
        </div>
      </div>

      {/* Galaxy Map Visualization */}
      <div className="bg-gray-900/50 border border-hud/20 rounded-xl p-4">
        <h3 className="font-semibold text-hud/80 mb-3">GALAXY MAP</h3>
        <div className="relative h-96 bg-black/50 overflow-hidden">
          {/* Starfield background */}
          <div className="absolute inset-0" 
               style={{
                 backgroundImage: 
                   'radial-gradient(white at 10% 20%, transparent 1%),' +
                   'radial-gradient(white at 20% 80%, transparent 1%),' +
                   'radial-gradient(white at 50% 50%, transparent 1%),' +
                   'radial-gradient(white at 70% 30%, transparent 1%),' +
                   'radial-gradient(white at 90% 60%, transparent 1%)',
                 backgroundSize: '50px 50px',
                 opacity: '0.1'
               }}></div>
          
          {/* Galaxy representations */}
          <div className="absolute inset-0 flex items-center justify-center">
            {/* Central Galactic Core */}
            <div className="w-20 h-20 bg-gradient-to-r from-hud/20 to-hud/40 rounded-full 
                          animate-pulse relative"
                 onClick={() => handleNodeClick('galactic-core', 'Core')}
                 title="Galactic Core - Central Knowledge Hub">
              <div className="absolute inset-0 rounded-full 
                          border-2 border-hud/100"></div>
            </div>
            
            {/* Spiral Arms */}
            {[...Array(5)].map((_, i) => (
              <div key={i} 
                   className="absolute inset-0"
                   style={{
                     transform: `rotate(${i * 72}deg) translateY(-40%) rotate(${-i * 72}deg)`
                   }}>
                <div className="w-0 h-0 border-l-8 border-hud/50 border-r-8 border-hud/50 
                            border-t-0 border-b-[30px] 
                            animate-pulse"
                     onClick={() => handleNodeClick('spiral-arm', `Arm ${i + 1}`)}
                     title={`Spiral Arm ${i + 1} - Knowledge Flow`}></div>
              </div>
            ))}
            
            {/* Star Systems (planets) */}
            {[...Array(12)].map((_, i) => {
              const angle = i * 30; // 360/12
              const distance = 40 + Math.random() * 20;
              return (
                <div key={i} 
                     className="absolute"
                     style={{
                       left: `calc(50% + ${distance * Math.cos(angle * Math.PI / 180)}px)`,
                       top: `calc(50% + ${distance * Math.sin(angle * Math.PI / 180)}px)`,
                       width: '6px',
                       height: '6px',
                       backgroundColor: 'hsl(210, 80%, 60%)',
                       borderRadius: '50%',
                       animation: `pulse ${3 + Math.random() * 2}s ease-in-out infinite`
                     }}
                     onClick={() => handleNodeClick('star-system', `System ${i + 1}`)}
                     title={`Star System ${i + 1} - Knowledge Cluster`}
                />
              )
            })}
            
            {/* Knowledge particles flowing between nodes */}
            <div className="absolute inset-0" 
                 style={{
                   pointerEvents: 'none',
                   backgroundImage: 
                     'radial-gradient(circle at 25% 25%, hsla(210, 80%, 60%, 0.3) 0%, transparent 50%),' +
                     'radial-gradient(circle at 75% 75%, hsla(210, 80%, 60%, 0.3) 0%, transparent 50%)',
                   backgroundSize: '200% 200%',
                   animation: 'flow 20s linear infinite'
                 }}></div>
          </div>
        </div>
      </div>

      {/* Knowledge Flow */}
      <div className="bg-gray-900/50 border border-hud/20 rounded-xl p-4">
        <h3 className="font-semibold text-hud/80 mb-3">KNOWLEDGE FLOW & CONNECTIONS</h3>
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-hud/60">Active Knowledge Streams</span>
            <span className="font-mono text-hud/40">23</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-hud/60">Cross-Disciplinary Links</span>
            <span className="font-mono text-hud/40">67</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-hud/60">Deep Insights Generated</span>
            <span className="font-mono text-hud/40">{knowledgeMetrics.wisdomInsights}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-hud/60">Pattern Recognition Rate</span>
            <span className="font-mono text-hud/40">89%</span>
          </div>
        </div>
        
        {/* Knowledge Connections Visualization */}
        <div className="mt-3 h-20 bg-gray-800/50 rounded overflow-hidden relative">
          <div className="absolute inset-0" 
               style={{
                 background: 
                   'linear-gradient(45deg, transparent 30%, hsla(210, 80%, 60%, 0.1) 50%, transparent 70%),' +
                   'linear-gradient(-45deg, transparent 30%, hsla(210, 80%, 60%, 0.1) 50%, transparent 70%)',
                 backgroundSize: '20px 20px',
                 animation: 'gridMove 4s linear infinite'
               }}></div>
          
          {/* Connection lines */}
          <div className="absolute inset-0">
            {[...Array(8)].map((_, i) => (
              <div key={i} 
                   className="absolute"
                   style={{
                     left: `${10 + i * 10}%`,
                     top: '50%',
                     width: '80%',
                     height: '2px',
                     background: 'linear-gradient(to right, transparent, hsla(210, 80%, 60%, 0.5), transparent)',
                     transformOrigin: 'left',
                     animation: `pulseLine ${4 + i * 0.5}s ease-in-out infinite alternate`
                   }}
              />
            ))}
          </div>
        </div>
      </div>

      {/* Selected Node Details */}
      {selectedNode && (
        <div className="bg-gray-900/50 border border-hud/20 rounded-xl p-4">
          <h3 className="font-semibold text-hud/80 mb-3">NODE DETAILS</h3>
          <p className="text-hud/60"><strong>Selected:</strong> {selectedNode}</p>
          <p className="text-hud/60"><strong>Type:</strong> Knowledge Nexus</p>
          <p className="text-hud/60"><strong>Connections:</strong> {Math.floor(Math.random() * 8) + 3}</p>
          <p className="text-hud/60"><strong>Knowledge Density:</strong> {((Math.random() * 2) + 3).toFixed(1)} units</p>
          <p className="text-hud/60"><strong>Last Explored:</strong> {new Date(Date.now() - Math.random() * 3600000).toLocaleTimeString()}</p>
          <div className="mt-3 pt-3 border-t border-hud/20">
            <p className="text-hud/50 italic">"This node represents a convergence of knowledge domains where patterns emerge and insights crystallize."</p>
          </div>
        </div>
      )}
    </div>
  )
}