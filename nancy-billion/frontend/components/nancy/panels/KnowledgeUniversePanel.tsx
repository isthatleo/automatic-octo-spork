'use client'

import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'

interface KnowledgeUniversePanelProps {
  onLog: (message: string) => void
}

export function KnowledgeUniversePanel({ onLog }: KnowledgeUniversePanelProps) {
  return (
    <div className=\
p-6\>
      <h1 className=\
text-2xl
font-bold
text-hud/100
mb-4\>KNOWLEDGE UNIVERSE</h1>
      <p className=\
text-hud/60
mb-6\>3D Knowledge Cosmos Visualization</p>

      <div className=\
bg-gray-900/50
rounded-xl
p-6\>
        <div className=\
text-center
py-8\>
          <div className=\
w-24
h-24
rounded-full
border-2
border-hud/50
flex
items-center
justify-center
mb-4\>
            <div className=\
w-20
h-20
rounded-full
bg-hud/20\></div>
          </div>
          <h2 className=\
text-xl
font-bold
text-hud\>2.4 TB</h2>
          <p className=\
text-hud/60\>Total Knowledge Stored</p>
          <p className=\
text-hud/50
mt-2\>1.8M Neural Connections • 456 Wisdom Units</p>
        </div>
        <div className=\
mt-6\>
          <h3 className=\
text-lg
font-semibold
text-hud
mb-3\>Knowledge Growth</h3>
          <div className=\
h-2
w-full
bg-gray-800/50
rounded-full
mb-2\>
            <div className=\
h-full
bg-gradient-to-r
from-purple-400
to-pink-500
rounded-full\ style={{ width: '75%' }}></div>
          </div>
          <p className=\
text-hud/50
text-right\>+12.3% daily growth</p>
        </div>
        <div className=\
mt-6\>
          <h3 className=\
text-lg
font-semibold
text-hud
mb-3\>Knowledge Domains</h3>
          <div className=\
grid
grid-cols-2
gap-4\>
            <div className=\
bg-gray-800/50
p-3
rounded\>Development: 420GB</div>
            <div className=\
bg-gray-800/50
p-3
rounded\>Research: 380GB</div>
            <div className=\
bg-gray-800/50
p-3
rounded\>Business: 290GB</div>
            <div className=\
bg-gray-800/50
p-3
rounded\>Security: 250GB</div>
            <div className=\
bg-gray-800/50
p-3
rounded\>Media: 180GB</div>
            <div className=\
bg-gray-800/50
p-3
rounded\>Systems: 160GB</div>
            <div className=\
bg-gray-800/50
p-3
rounded\>Other: 520GB</div>
          </div>
        </div>
      </div>
    </div>
  )
}