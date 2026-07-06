'use client'



import { useEffect, useState } from 'react'

import { cn } from '@/lib/utils'



interface MemoryCrystalPanelProps {

  onLog: (message: string) => void

}



export function MemoryCrystalPanel({ onLog }: MemoryCrystalPanelProps) {

  return (

    <div className=\

p-6\>

      <h1 className=\

text-2xl

font-bold

text-hud/100

mb-4\>MEMORY CRYSTAL</h1>

      <p className=\

text-hud/60

mb-6\>Experiential Knowledge Archive</p>



      <div className=\

bg-gray-900/50

rounded-xl

p-6\>

        <div className=\

space-y-6\>

          <div className=\

text-center\>

            <div className=\

w-32

h-32

rounded-full

border-2

border-hud/50

flex

items-center

justify-center

mb-4\>

              <div className=\

w-28

h-28

rounded-full

bg-hud/20\></div>

            </div>

            <h2 className=\

text-xl

font-bold

text-hud\>456</h2>

            <p className=\

text-hud/60\>Wisdom Crystals Formed</p>

            <p className=\

text-hud/50\>2.4 TB Experiential Data • 98.7% Integrity</p>

          </div>



          <div className=\

grid

grid-cols-1

md:grid-cols-2

gap-4\>

            <div className=\

bg-gray-800/50

p-4

rounded\>

              <h3 className=\

text-lg

font-semibold

text-hud

mb-3\>Recent Insights</h3>

                <div className=\

flex

justify-between

text-hud/50\>

                  <span>Quantum Pattern Recognition</span>

                  <span className=\

font-mono\>Just now</span>

                </div>

                <div className=\

flex

justify-between

text-hud/50\>

                  <span>Market Prediction Algorithm</span>

                  <span className=\

font-mono\>3 min ago</span>

                </div>

                <div className=\

flex

justify-between

text-hud/50\>

                  <span>Neural Network Optimization</span>

                  <span className=\

font-mono\>7 min ago</span>

                </div>

              </div>

            </div>

            <div className=\

bg-gray-800/50

p-4

rounded\>

              <h3 className=\

text-lg

font-semibold

text-hud

mb-3\>Memory Formation Rate</h3>

              <div className=\

flex

items-center

justify-between\>

                <span>Crystals/Hour:</span>

                <span className=\

font-mono

text-green-400\>12.4</span>

              </div>

              <div className=\

flex

items-center

justify-between\>

                <span className=\

font-mono

text-green-400\>94.2%</span>

              </div>

            </div>

          </div>



          <div className=\

mt-6\>

            <h3 className=\

text-lg

font-semibold

text-hud

mb-3\>Memory Layers</h3>

            <div className=\

space-y-2\>

              <div className=\

flex

justify-between\>

                <span>Experience Data:</span>

              </div>

              <div className=\

flex

justify-between\>