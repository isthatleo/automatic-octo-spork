'use client'

import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'
import { Globe, Zap, Shield, Heart, Brain, Bot, Folder, TerminalSquare, CandlestickChart, RSS, Music, Users, Heart as HeartIcon, Activity } from 'lucide-react'

export function GodModePanel({ onLog }: { onLog: (entry: Omit<import('@/lib/nancy/types').LogEntry, 'id'>) => void }) {
  const [civilizationHealth, setCivilizationHealth] = useState(98)
  const [agentStats, setAgentStats] = useState({
    total: 200,
    active: 12,
    learning: 8,
    idle: 180
  })
  const [missionStats, setMissionStats] = useState({
    active: 5,
    completed: 142,
    failed: 3
  })
  const [knowledgeMetrics, setKnowledgeMetrics] = useState({
    totalMemories: 12450,
    knowledgeGrowth: 3.2,
    patternsDiscovered: 45,
    wisdomInsights: 8
  })
  const [systemMetrics, setSystemMetrics] = useState({
    cpuUsage: 45,
    memoryUsage: 62,
    gpuUsage: 28,
    networkLatency: 12
  })

  // Simulate real-time data updates
  useEffect(() => {
    const updateMetrics = () => {
      // Simulate fluctuating metrics
      setCivilizationHealth(prev => {
        const change = (Math.random() - 0.5) * 2
        return Math.max(85, Math.min(99, prev + change))
      })
      
      setAgentStats(prev => {
        const activeChange = Math.round((Math.random() - 0.5) * 2)
        const learningChange = Math.round((Math.random() - 0.5) * 1)
        const newActive = Math.max(5, Math.min(50, prev.active + activeChange))
        const newLearning = Math.max(2, Math.min(20, prev.learning + learningChange))
        const newIdle = 200 - newActive - newLearning
        return { 
          total: 200, 
          active: newActive, 
          learning: newLearning, 
          idle: newIdle 
        }
      })
      
      setMissionStats(prev => {
        if (Math.random() > 0.95) { // 5% chance of new mission completion
          return {
            active: Math.max(1, prev.active - 1),
            completed: prev.completed + 1,
            failed: prev.failed
          }
        }
        return prev
      })
      
      setKnowledgeMetrics(prev => ({
        totalMemories: prev.totalMemories + Math.floor(Math.random() * 5),
        knowledgeGrowth: parseFloat((Math.random() * 0.1 + 2.8).toFixed(1)),
        patternsDiscovered: prev.patternsDiscovered + (Math.random() > 0.9 ? 1 : 0),
        wisdomInsights: prev.wisdomInsights + (Math.random() > 0.95 ? 1 : 0)
      }))
      
      setSystemMetrics(prev => ({
        cpuUsage: Math.max(10, Math.min(90, prev.cpuUsage + (Math.random() - 0.5) * 10)),
        memoryUsage: Math.max(20, Math.min(85, prev.memoryUsage + (Math.random() - 0.5) * 8)),
        gpuUsage: Math.max(5, Math.min(60, prev.gpuUsage + (Math.random() - 0.5) * 15)),
        networkLatency: Math.max(5, Math.min(50, prev.networkLatency + (Math.random() - 0.5) * 5))
      }))
    }
    
    const interval = setInterval(updateMetrics, 3000)
    updateMetrics() // Initial call
    
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4 pb-2 border-b border-hud/20">
        <h2 className="text-xl font-bold text-hud/100 font-heading">
          <Zap className="mr-2 h-4 w-4 animate-pulse" /> GOD MODE
        </h2>
        <div className="text-xs text-hud/40">
          Last updated: {new Date().toLocaleTimeString()}
        </div>
      </div>

      {/* Civilization Overview */}
      <div className="bg-gray-900/50 border border-hud/20 rounded-xl p-4">
        <h3 className="font-semibold text-hud/80 mb-3">CIVILIZATION OVERVIEW</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="text-center">
            <div className="text-3xl font-bold" 
                 className={civilizationHealth >= 90 ? 'text-green-400' : 
                           civilizationHealth >= 75 ? 'text-yellow-400' : 'text-red-400'}>
              {civilizationHealth.toFixed(1)}%
            </div>
            <p className="text-xs text-hud/50">Civilization Health</p>
          </div>
          
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-hud/60">Active Agents</span>
              <span className="font-mono">{agentStats.active}/200</span>
            </div>
            <div className="flex justify-between">
              <span className="text-hud/60">Learning Agents</span>
              <span className="font-mono">{agentStats.learning}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-hud/60">Idle Agents</span>
              <span className="font-mono">{agentStats.idle}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Agent Matrix */}
      <div className="bg-gray-900/50 border border-hud/20 rounded-xl p-4">
        <h3 className="font-semibold text-hud/80 mb-3">AGENT MATRIX</h3>
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-hud/60">Agent Distribution by Department</span>
            <span className="text-xs text-hud/40">200 Total Agents</span>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-gray-800/50 px-3 py-2 rounded">
              <div className="flex justify-between">
                <span className="text-hud/50">🔬 Research</span>
                <span className="font-mono text-hud/40">45</span>
              </div>
            </div>
            <div className="bg-gray-800/50 px-3 py-2 rounded">
              <div className="flex justify-between">
                <span className="text-hud/50">⚙️ Engineering</span>
                <span className="font-mono text-hud/40">38</span>
              </div>
            </div>
            <div className="bg-gray-800/50 px-3 py-2 rounded">
              <div className="flex justify-between">
                <span className="text-hud/50">🧠 Memory</span>
                <span className="font-mono text-hud/40">32</span>
              </div>
            </div>
            <div className="bg-gray-800/50 px-3 py-2 rounded">
              <div className="flex justify-between">
                <span className="text-hud/50">🛡️ Security</span>
                <span className="font-mono text-hud/40">25</span>
              </div>
            </div>
            <div className="bg-gray-800/50 px-3 py-2 rounded">
              <div className="flex justify-between">
                <span className="text-hud/50">📊 Analytics</span>
                <span className="font-mono text-hud/40">22</span>
              </div>
            </div>
            <div className="bg-gray-800/50 px-3 py-2 rounded">
              <div className="flex justify-between">
                <span className="text-hud/50">💼 Business</span>
                <span className="font-mono text-hud/40">18</span>
              </div>
            </div>
            <div className="bg-gray-800/50 px-3 py-2 rounded">
              <div className="flex justify-between">
                <span className="text-hud/50">💖 Companion</span>
                <span className="font-mono text-hud/40">15</span>
              </div>
            </div>
            <div className="bg-gray-800/50 px-3 py-2 rounded">
              <div className="flex justify-between">
                <span className="text-hud/50">🔄 Workflow</span>
                <span className: "C:\Users\leona.DESKTOP-10QNDAN\Desktop\automatic-octo-spork\nancy-billion\frontend\components\nancy\god-mode-panel.tsx", line 150, column 1 in root