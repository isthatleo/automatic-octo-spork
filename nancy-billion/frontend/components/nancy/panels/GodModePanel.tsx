'use client'

import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'

interface GodModePanelProps {
  onLog: (message: string) => void
}

export function GodModePanel({ onLog }: GodModePanelProps) {
  return (
    <div className=\
p-6\>
      <h1 className=\
text-2xl
font-bold
text-hud/100
mb-4\>GOD MODE DASHBOARD</h1>
      <p className=\
text-hud/60
mb-6\>Civilization Status Overview</p>

      <div className=\
grid
grid-cols-1
md:grid-cols-2
lg:grid-cols-3
gap-4\>
        <div className=\
bg-gray-900/50
rounded-xl
p-4
border
border-hud/20\>
          <h2 className=\
text-lg
font-semibold
text-hud
mb-3\>Civilization Health</h2>
          <div className=\
text-2xl
font-bold
text-green-400\>87%</div>
          <p className=\
text-hud/50\>Stable & Secure</p>
        </div>

        <div className=\
bg-gray-900/50
rounded-xl
p-4
border
border-hud/20\>
          <h2 className=\
text-lg
font-semibold
text-hud
mb-3\>Agent Activity</h2>
          <div className=\
text-2xl
font-bold
text-cyan-400\>142/200</div>
          <p className=\
text-hud/50\>Active Agents</p>
        </div>

        <div className=\
bg-gray-900/50
rounded-xl
p-4
border
border-hud/20\>
          <h2 className=\
text-lg
font-semibold
text-hud
mb-3\>Knowledge Growth</h2>
          <div className=\
text-2xl
font-bold
text-purple-400\>+12.3%/day</div>
          <p className=\
text-hud/50\>Expanding Rapidly</p>
        </div>
      </div>

      <div className=\
mt-6
p-4
bg-gray-900/50
rounded-xl
border
border-hud/20\>
        <h2 className=\
text-lg
font-semibold
text-hud
mb-3\>System Status</h2>
        <div className=\
space-y-2\>
          <div className=\
flex
justify-between\>
            <span>Overall Performance:</span>
            <span className=\
font-mono
text-green-400\>Optimal</span>
          </div>
          <div className=\
flex
justify-between\>
            <span>Threat Level:</span>
            <span className=\
font-mono
text-green-400\>Minimal</span>
          </div>
          <div className=\
flex
justify-between\>
            <span>Learning Rate:</span>
            <span className=\
font-mono
text-blue-400\>Accelerating</span>
          </div>
        </div>
      </div>
    </div>
  )
}