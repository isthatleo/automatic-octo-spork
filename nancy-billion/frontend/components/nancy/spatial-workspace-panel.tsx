'use client'

import { useEffect, useState, useRef } from 'react'
import { cn } from '@/lib/utils'
import { Users, Globe, Activity, Zap, Folder, TerminalSquare, Code, Monitor, LayoutDashboard, Settings, Monitor as MonitorIcon, Smartphone, Gamepad, Headphones, Mic, Camera } from 'lucide-react'

export function SpatialWorkspacePanel({ onLog }: { onLog: (entry: Omit<import('@/lib/nancy/types').LogEntry, 'id'>) => void }) {
  const [workspaces, setWorkspaces] = useState([
    { id: 'dev-main', name: 'Primary Development', type: 'code', active: true, progress: 78 },
    { id: 'research-ai', name: 'AI Research Lab', type: 'research', active: true, progress: 45 },
    { id: 'comm-secure', name: 'Secure Communications', type: 'communication', active: false, progress: 0 },
    { id: 'design-ui', name: 'UI/UX Design Studio', type: 'design', active: true, progress: 62 },
    { id: 'analysis-data', name: 'Data Analysis Hub', type: 'analysis', active: true, progress: 31 },
    { id: 'sys-admin', name: 'System Administration', type: 'system', active: false, progress: 0 },
    { id: 'media-prod', name: 'Media Production', type: 'media', active: true, progress: 55 },
    { id: 'network-ops', name: 'Network Operations', type: 'network', active: false, progress: 0 }
  ])
  const [activeWorkspace, setActiveWorkspace] = useState<string | null>('dev-main')
  const [isManipulating, setIsManipulating] = useState(false)
  const [workspacePositions, setWorkspacePositions] = useState<Record<string, { x: number; y: number; z: number; scale: number }>>({})

  // Initialize 3D positions for workspaces
  useEffect(() => {
    const initialPositions: Record<string, { x: number; y: number; z: number; scale: number }> = {}
    workspaces.forEach(workspace => {
      const angle = (Math.random() * Math.PI * 2)
      const radius = 2 + Math.random() * 3
      initialPositions[workspace.id] = {
        x: Math.cos(angle) * radius,
        y: (Math.random() - 0.5) * 2,
        z: Math.sin(angle) * radius,
        scale: 0.8 + Math.random() * 0.4
      }
    })
    setWorkspacePositions(initialPositions)
  }, [workspaces])

  // Simulate workspace activity updates
  useEffect(() => {
    const updateWorkspaces = () => {
      setWorkspaces(prev => 
        prev.map(workspace => ({
          ...workspace,
          progress: workspace.active 
            ? Math.min(100, workspace.progress + Math.random() * 2) 
            : Math.max(0, workspace.progress - Math.random() * 1),
          active: Math.random() > 0.7 || workspace.active // 30% chance to toggle
        }))
      )
      
      // Update active workspace occasionally
      if (Math.random() > 0.95) {
        const randomWorkspace = workspaces[Math.floor(Math.random() * workspaces.length)]
        setActiveWorkspace(randomWorkspace.id)
        onLog({ level: 'info', message: `Switched to workspace: ${randomWorkspace.name}` })
      }
    }
    
    const interval = setInterval(updateWorkspaces, 4000)
    updateWorkspaces() // Initial call
    
    return () => clearInterval(interval)
  }, [workspaces.length])

  const handleWorkspaceClick = (workspaceId: string) => {
    setActiveWorkspace(workspaceId)
    setIsManipulating(true)
    onLog({ level: 'info', message: `Activated workspace: ${workspaces.find(w => w.id === workspaceId)?.name}` })
    
    // Reset manipulation state after delay
    setTimeout(() => setIsManipulating(false), 2000)
  }

  const handleWorkspaceDrag = (workspaceId: string, x: number, y: number, z: number) => {
    setIsManipulating(true)
    setWorkspacePositions(prev => ({
      ...prev,
      [workspaceId]: {
        ...prev[workspaceId],
        x,
        y,
        z
      }
    }))
    
    onLog({ level: 'info', message: `Repositioned workspace: ${workspaces.find(w => w.id === workspaceId)?.name}` })
    
    // Reset manipulation state after delay
    setTimeout(() => setIsManipulating(false), 1500)
  }

  const handleWorkspaceScale = (workspaceId: string, scale: number) => {
    setWorkspacePositions(prev => ({
      ...prev,
      [workspaceId]: {
        ...prev[workspaceId],
        scale
      }
    }))
    
    onLog({ level: 'info', message: `Scaled workspace: ${workspaces.find(w => w.id === workspaceId)?.name} to ${(scale * 100).toFixed(0)}%` })
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4 pb-2 border-b border-hud/20">
        <h2 className="text-xl font-bold text-hud/100 font-heading">
          <Users className="mr-2 h-4 w-4 animate-pulse" /> SPATIAL WORKSPACE
        </h2>
        <div className="flex items-center space-x-2 text-xs text-hud/40">
          <button 
            onClick={() => setIsManipulating(!isManipulating)}
            className={`px-3 py-1 rounded text-hud/60 hover:bg-hud/10 hover:text-hud/100 ${isManipulating ? 'bg-hud/20' : ''}`}
          >
            {isManipulating ? '✋ Manipulate' : '👆 Interact'}
          </button>
          <span className="text-hud/40">{isManipulating ? '3D Manipulation Active' : 'Ready for Interaction'}</span>
        </div>
      </div>

      {/* Workspace Statistics */}
      <div className="bg-gray-900/50 border border-hud/20 rounded-xl p-4">
        <h3 className="font-semibold text-hud/80 mb-3">WORKSPACE STATISTICS</h3>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-hud/60">Total Workspaces</span>
              <span className="font-mono text-hud/40">{workspaces.length}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-hud/60">Active Workspaces</span>
              <span className="font-mono text-hud/40">{workspaces.filter(w => w.active).length}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-hud/60">Average Progress</span>
              <span className="font-mono text-hud/40">{Math.round(workspaces.reduce((sum, w) => sum + w.progress, 0) / workspaces.length)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-hud/60">Compute Utilization</span>
              <span className="font-mono text-hud/40">{Math.floor(Math.random() * 40 + 60)}%</span>
            </div>
          </div>
          
          {/* Workspace Type Distribution */}
          <div className="mt-4">
            <div className="flex justify-between mb-1">
              <span className="text-hud/60">Workspace Types</span>
              <span className="text-xs text-hud/40">8 Categories</span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs text-hud/50">
              {[...new Set(workspaces.map(w => w.type))].map(type => (
                <div key={type} className="flex items-center">
                  <div className="w-2 h-2 bg-hud/20 rounded mr-1"></div>
                  <span>{type.toUpperCase()}</span>
                  <span className="ml-2">({workspaces.filter(w => w.type === type).length})</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* 3D Workspace Visualization */}
      <div className="bg-gray-900/50 border border-hud/20 rounded-xl p-4">
        <h3 className="font-semibold text-hud/80 mb-3">3D WORKSPACE ENVIRONMENT</h3>
        <div className="relative h-96 bg-black/50 overflow-hidden">
          {/* Grid floor */}
          <div className="absolute inset-0" 
               style={{
                 backgroundImage: 
                   'linear-gradient(90deg, hsla(210, 80%, 20%, 0.1) 1px, transparent 1px),' +
                   'linear-gradient(0deg, hsla(210, 80%, 20%, 0.1) 1px, transparent 1px)',
                 backgroundSize: '20px 20px',
                 opacity: '0.3'
               }}></div>
          
          {/* Workspace nodes in 3D space */}
          <div className="absolute inset-0 flex items-center justify-center" 
               style={{ 
                 transformStyle: 'preserve-3d',
                 perspective: '800px',
                 transform: `rotateX(20deg) rotateY(${isManipulating ? Date.now() * 0.01 : 0}deg)`
               }}>
            {workspaces.map(workspace => {
              const pos = workspacePositions[workspace.id] || { x: 0, y: 0, z: 0, scale: 1 }
              const isActive = workspace.id === activeWorkspace
              const isManipulatingNow = isManipulating && workspace.id === activeWorkspace
              
              return (
                <div key={workspace.id} 
                     className="absolute"
                     style={{
                       left: `calc(50% + ${pos.x * 20}px)`,
                       top: `calc(50% + ${pos.y * 20}px)`,
                       transform: `translateZ(${pos.z * 20}px) scale(${pos.scale * (isActive ? 1.2 : 1)})`,
                       zIndex: Math.round(100 + pos.z * 10) // Higher Z = higher z-index
                     }}
                     onClick={() => handleWorkspaceClick(workspace.id)}
                     onMouseDown={(e: React.MouseEvent) => {
                       if (isManipulating) {
                         e.preventDefault()
                         // In a real implementation, this would start drag operation
                         onLog({ level: 'info', message: `Started manipulating ${workspace.name}` })
                       }
                     }}
                     className={`
                       transition-transform ${isManipulating ? '0s' : '0.3s ease-in-out'}
                     `}
                  >
                    {/* Workspace Container */}
                    <div className="relative w-16 h-16 bg-gray-800/50 border border-hud/20 rounded-lg overflow-hidden flex items-center justify-center"
                         style={{
                           boxShadow: isActive 
                             ? '0 0 20px hsla(210, 80%, 60%, 0.5)' 
                             : '0 0 10px hsla(0, 0%, 0%, 0.3)',
                           borderColor: isActive 
                             ? 'hsla(210, 80%, 60%, 0.8)' 
                             : 'hsla(210, 80%, 20%, 0.5)',
                           background: isActive 
                             ? 'hsla(210, 80%, 20%, 0.3)' 
                             : 'hsla(210, 80%, 10%, 0.2)'
                         }}>
                       {/* Workspace Icon */}
                       <div className="text-hud/60">
                         {workspace.type === 'code' && <Code className="h-5 w-5" />}
                         {workspace.type === 'research' && <Activity className="h-5 w-5" />}
                         {workspace.type === 'communication' && <Mic className="h-5 w-5" />}
                         {workspace.type === 'design' && <Camera className="h-5 w-5" />}
                         {workspace.type === 'analysis' && <MonitorIcon className="h-5 w-5" />}
                         {workspace.type === 'system' && <Settings className="h-5 w-5" />}
                         {workspace.type === 'media' && <Headphones className="h-5 w-5" />}
                         {workspace.type === 'network' && <Globe className="h-5 w-5" />}
                         {!['code','research','communication','design','analysis','system','media','network'].includes(workspace.type) && <Folder className="h-5 w-5" />}
                       </div>
                       {/* Workspace Label */}
                       <div className="absolute bottom-0 left-0 right-0 bg-black/50 text-xs text-center text-hud/50 p-1">
                         {workspace.name.length > 8 
                           ? workspace.name.substring(0, 8) + '...' 
                           : workspace.name}
                       </div>
                       {/* Progress Indicator */}
                       <div className="absolute bottom-0 left-0 h-0.5 w-full bg-gradient-to-r from-hud to-hud/20"
                            style={{ width: `${workspace.progress}%` }}></div>
                       {/* Active Indicator */}
                       {isActive && (
                         <div className="absolute -top-1 -left-1 w-4 h-4 bg-hud/100 rounded-full 
                             animate-pulse border border-hud/20"></div>
                       )}
                       {/* Manipulation Indicator */}
                       {isManipulatingNow && (
                         <div className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 rounded-full 
                             animate-pulse border border-hud/20"></div>
                       )}
                    </div>
                  )
            })}
            
            {/* Connection lines between active workspaces */}
            <div className="absolute inset-0 pointer-events-none" 
                 style={{
                   pointerEvents: 'none'
                 }}>
              {workspaces
                .filter(w => w.active)
                .map((ws1, i1) => 
                  workspaces
                    .filter(w => w.active && w.id !== ws1.id)
                    .map((ws2, i2) => {
                      const pos1 = workspacePositions[ws1.id] || { x: 0, y: 0, z: 0 }
                      const pos2 = workspacePositions[ws2.id] || { x: 0, y: 0, z: 0 }
                      
                      // Only draw connection if both workspaces are in view
                      if (Math.abs(pos1.x) < 3 && Math.abs(pos1.y) < 3 && Math.abs(pos2.x) < 3 && Math.abs(pos2.y) < 3) {
                        return (
                          <div key={`conn-${ws1.id}-${ws2.id}`} 
                               className="absolute"
                               style={{
                                 left: `calc(50% + ${((pos1.x + pos2.x) / 2) * 20}px)`,
                                 top: `calc(50% + ${((pos1.y + pos2.y) / 2) * 20}px)`,
                                 width: `${Math.sqrt(Math.pow((pos2.x - pos1.x) * 20, 2) + Math.pow((pos2.y - pos1.y) * 20, 2))}px`,
                                 height: '2px',
                                 background: 'linear-gradient(to right, transparent, hsla(210, 80%, 60%, 0.3), transparent)',
                                 transformOrigin: 'left',
                                 transform: `rotate(${Math.atan2(pos2.y - pos1.y, pos2.x - pos1.x) * (180 / Math.PI)}deg)`,
                                 opacity: '0.6'
                               }}
                          />
                        )
                      }
                      return null
                    })
                )
                .flat()
                .filter(Boolean): any[]}
            </div>
          </div>
        </div>
      </div>

      {/* Active Workspace Details */}
      {activeWorkspace && (
        <div className="bg-gray-900/50 border border-hud/20 rounded-xl p-4">
          <h3 className="font-semibold text-hud/80 mb-3">ACTIVE WORKSPACE DETAILS</h3>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-hud/60">Workspace</span>
              <span className="font-mono text-hud/40">{workspaces.find(w => w.id === activeWorkspace)?.name || 'Unknown'}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-hud/60">Type</span>
              <span className="font-mono text-hud/40">{workspaces.find(w => w.id === activeWorkspace)?.type?.toUpperCase() || 'UNKNOWN'}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-hud/60">Status</span>
              <span className="font-mono text-hud/40">{workspaces.find(w => w.id === activeWorkspace)?.active ? 'ACTIVE' : 'INACTIVE'}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-hud/60">Progress</span>
              <span className="font-mono text-hud/40">{workspaces.find(w => w.id === activeWorkspace)?.progress || 0}%</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-hud/60">Last Updated</span>
              <span className="font-mono text-hud/40">{new Date().toLocaleTimeString()}</span>
            </div>
          </div>
          
          {/* Workspace Controls */}
          <div className="mt-4 pt-3 border-t border-hud/20">
            <div className="grid grid-cols-2 gap-3">
              <button 
                onClick={() => {
                  const ws = workspaces.find(w => w.id === activeWorkspace)
                  if (ws) {
                    setWorkspaces(prev => 
                      prev.map(w => 
                        w.id === activeWorkspace 
                          ? {...w, active: !w.active, progress: w.active ? 0 : Math.min(100, w.progress + 10)} 
                          : w
                      )
                    )
                    onLog({ level: 'info', message: `${ws.active ? 'Deactivated' : 'Activated'} workspace: ${ws.name}` })
                  }
                }}
                className="w-full px-3 py-2 rounded text-hud/60 hover:bg-hud/10 hover:text-hud/100"
              >
                {workspaces.find(w => w.id === activeWorkspace)?.active ? '⏸ Deactivate' : '▶ Activate'}
              </button>
              
              <button 
                onClick={() => {
                  const ws = workspaces.find(w => w.id === activeWorkspace)
                  if (ws) {
                    setWorkspaces(prev => 
                      prev.map(w => 
                        w.id === activeWorkspace 
                          ? {...w, progress: Math.min(100, w.progress + 15)} 
                          : w
                      )
                    )
                    onLog({ level: 'info', message: `Advanced progress in workspace: ${ws.name}` })
                  }
                }}
                className="w-full px-3 py-2 rounded text-hud/60 hover:bg-hud/10 hover:text-hud/100"
              >
                ⏩ Advance Progress
              </button>
              
              <button 
                onClick={() => {
                  // Reset workspace
                  setWorkspaces(prev => 
                    prev.map(w => 
                      w.id === activeWorkspace 
                        ? {...w, progress: 0, active: false} 
                        : w
                    )
                  )
                  onLog({ level: 'info', message: `Reset workspace: ${workspaces.find(w => w.id === activeWorkspace)?.name}` })
                }}
                className="w-full px-3 py-2 rounded text-hud/60 hover:bg-hud/10 hover:text-hud/100"
              >
                🔄 Reset
              </button>
              
              <button 
                onClick={() => {
                  // Duplicate workspace
                  const ws = workspaces.find(w => w.id === activeWorkspace)
                  if (ws) {
                    const newId = `${ws.id}-copy-${Date.now()}`
                    setWorkspaces(prev => [
                      ...prev,
                      {
                        id: newId,
                        name: `${ws.name} Copy`,
                        type: ws.type,
                        active: false,
                        progress: 0
                      }
                    ])
                    setActiveWorkspace(newId)
                    onLog({ level: 'info', message: `Duplicated workspace: ${ws.name}` })
                  }
                }}
                className="w-full px-3 py-2 rounded text-hud/60 hover:bg-hud/10 hover:text-hud/100"
              >
                📋 Duplicate
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}