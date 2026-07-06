'use client'

import { useEffect, useState } from 'react'
import { HudPanel } from './hud-bits'
import type { ProjectInfo } from '@/lib/nancy/types'

export interface ProjectInfo {
  name: string
  path: string
  type: string
}

export interface KanbanColumn {
  id: string
  title: string
  items: KanbanItem[]
}

export interface KanbanItem {
  id: string
  title: string
  description: string
  status: 'todo' | 'in-progress' | 'review' | 'done'
  priority: 'low' | 'medium' | 'high'
  assignee?: string
  tags: string[]
  createdAt: number
  updatedAt: number
}

/** Projects Panel – lists the workspace and lets you open/create. */
export function ProjectsPanel({
  projects,
  onOpen,
  onCreate,
}: {
  projects: ProjectInfo[]
  onOpen: (path: string) => void
  onCreate: (name: string) => void
}) {
  const [viewMode, setViewMode] = useState<'list' | 'kanban'>('list')
  
  // Mock Kanban data - in a real implementation, this would come from a task manager
  const [kanbanColumns, setKanbanColumns] = useState<KanbanColumn[]>([
    {
      id: 'todo',
      title: 'To Do',
      items: [
        {
          id: 'task-1',
          title: 'Implement voice-first interaction',
          description: 'Create natural language understanding pipeline with wake word detection',
          status: 'todo',
          priority: 'high',
          assignee: 'ORACLE',
          tags: ['voice', 'ai', 'nlp'],
          createdAt: Date.now() - 86400000,
          updatedAt: Date.now() - 86400000
        },
        {
          id: 'task-2',
          title: 'Design orb UI animations',
          description: 'Create fluid simulations and holographic effects for Nancy orb',
          status: 'todo',
          priority: 'medium',
          assignee: 'MUSE',
          tags: ['ui', 'animation', 'design'],
          createdAt: Date.now() - 72000000,
          updatedAt: Date.now() - 72000000
        }
      ]
    },
    {
      id: 'in-progress',
      title: 'In Progress',
      items: [
        {
          id: 'task-3',
          title: 'Build knowledge galaxy model',
          description: 'Create interconnected knowledge base modeled as galaxy/universe',
          status: 'in-progress',
          priority: 'high',
          assignee: 'FORGE',
          tags: ['knowledge', 'graph', 'database'],
          createdAt: Date.now() - 120000000,
          updatedAt: Date.now() - 10000000
        }
      ]
    },
    {
      id: 'review',
      title: 'Review',
      items: [
        {
          id: 'task-4',
          title: 'Integrate news feed with trusted sources',
          description: 'Connect to AI/IT/Finance news sources with audio narration',
          status: 'review',
          priority: 'medium',
          assignee: 'ECHO',
          tags: ['news', 'media', 'integration'],
          createdAt: Date.now() - 90000000,
          updatedAt: Date.now() - 20000000
        }
      ]
    },
    {
      id: 'done',
      title: 'Done',
      items: [
        {
          id: 'task-5',
          title: 'Set up development environment',
          description: 'Configure Nancy billion repository with all dependencies',
          status: 'done',
          priority: 'low',
          assignee: 'WARDEN',
          tags: ['setup', 'devops'],
          createdAt: Date.now() - 200000000,
          updatedAt: Date.now() - 150000000
        }
      ]
    }
  ]);
  const [createName, setCreateName] = useState('')

  const handleOpen = (path: string) => {
    onOpen(path)
  }

  const handleCreate = () => {
    const name = createName.trim()
    if (!name) return
    onCreate(name)
    setCreateName('')
  }

  return (
    <HudPanel title="Projects Workspace" right={<div className="flex items-center gap-2">
      <span className="text-primary">{projects.length} LOADED</span>
      <button
        type="button"
        onClick={() => setViewMode(viewMode === 'list' ? 'kanban' : 'list')}
        className="flex h-8 w-8 items-center justify-center rounded border border-border bg-secondary/30 text-muted-foreground transition-colors hover:border-primary/60 hover:text-primary"
      >
        {viewMode === 'list' ? (
          <span className="text-[0.5rem] uppercase tracking-widest">▰▰▰</span>
        ) : (
          <span className="text-[0.5rem] uppercase tracking-widest">▱▱▱</span>
        )}
      </button>
    </div>}>
      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-2">
          <p className="text-[0.55rem] text-muted-foreground">
            Workspace: <span className="text-primary">automatic-octo-spork</span>
          </p>
          <div className="flex items-center gap-2">
            <input
              value={createName}
              onChange={(e) => setCreateName(e.target.value)}
              placeholder="New project name"
              className="h-8 flex-1 rounded border border-border bg-background/60 px-2.5 text-[0.6rem] text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-primary/60"
            />
            <button
              type="button"
              onClick={handleCreate}
              className="flex h-8 w-8 items-center justify-center rounded border border-border bg-secondary/30 text-muted-foreground transition-colors hover:border-primary/60 hover:text-primary"
            >
              <span className="text-[0.5rem] uppercase tracking-widest">+</span>
            </button>
          </div>
          {createName && (
            <p className="text-[0.5rem] text-muted-foreground italic">
              Press Enter or click + to create "{createName}"
            </p>
          )}
        </div>

        {viewMode === 'list' ? (
          projects.length === 0 ? (
            <p className="text-center text-[0.55rem] text-muted-foreground">
              No projects found in workspace.
            </p>
          ) : (
            <div className="flex flex-col gap-2">
              {projects.map((p) => (
                <div
                  key={p.name}
                  className="flex items-center justify-between p-2 rounded border border-border bg-secondary/20"
                >
                  <div className="flex items-center gap-2">
                    <span className="h-3 w-3">
                      {p.type === 'node' ? (
                        <span className="text-primary">⬢</span>
                      ) : p.type === 'python' ? (
                        <span className="text-primary">🐍</span>
                      ) : p.type === 'rust' ? (
                        <span className="text-primary">🦀</span>
                      ) : p.type === 'go' ? (
                        <span className="text-primary">🔵</span>
                      ) : (
                        <span className="text-muted-foreground">📁</span>
                      )}
                    </span>
                    <div>
                      <span className="font-heading text-[0.6rem] text-foreground">{p.name}</span>
                      <p className="text-[0.5rem] text-muted-foreground">{p.type}</p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleOpen(p.path)}
                    className="flex h-8 w-8 items-center justify-center rounded border border-primary/50 bg-primary/10 px-3 py-1.5 text-[0.55rem] uppercase tracking-widest text-primary transition-colors hover:bg-primary/20"
                  >
                    Open
                  </button>
                </div>
              ))}
            </div>
          )
        ) : (
          // Kanban View
          <div className="grid grid-cols-[200px_1fr] gap-4">
            {/* Column headers */}
            <div className="flex flex-col gap-1">
              {kanbanColumns.map((column) => (
                <div
                  key={column.id}
                  className="flex items-center gap-2 p-2 rounded border border-hud/30 bg-background/50"
                >
                  <span className="h-3 w-3">
                    {column.id === 'todo' ? (
                      <span className="text-primary">📝</span>
                    ) : column.id === 'in-progress' ? (
                        <span className="text-accent">⚡</span>
                      ) : column.id === 'review' ? (
                        <span className="text-warning">👀</span>
                      ) : (
                        <span className="text-success">✅</span>
                      )}
                  </span>
                  <span className="font-heading text-[0.6rem] text-foreground">{column.title}</span>
                  <span className="text-[0.5rem] text-muted-foreground">{column.items.length}</span>
                </div>
              ))}
            </div>
            
            {/* Kanban items */}
            <div className="flex flex-col gap-2 overflow-y-auto h-[calc(100%-80px)]">
              {kanbanColumns.map((column) => (
                <div
                  key={column.id}
                  className="flex-1 min-w-0 space-y-2 rounded border border-hud/20 bg-background/30 p-3"
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-heading text-[0.6rem] text-foreground">{column.title}</span>
                    <span className="text-[0.5rem] text-muted-foreground">{column.items.length} items</span>
                  </div>
                  
                  <div className="space-y-2">
                    {column.items.map((item) => (
                      <div
                        key={item.id}
                        className={`flex flex-col gap-2 rounded border p-3 transition-all duration-200 ${
                          getPriorityBorderColor(item.priority)
                        } hover:bg-background/40 hover:border-primary/30`}
                      >
                        <div className="flex justify-between items-start">
                          <div className="flex items-center gap-2">
                            <span className="text-[0.5rem] text-muted-foreground">
                              {getPriorityDot(item.priority)}
                            </span>
                            <span className="font-heading text-[0.65rem] text-foreground">{item.title}</span>
                          </div>
                          <div className="flex items-center gap-1">
                            {item.assignee && (
                              <div className="flex items-center gap-1 text-[0.5rem]">
                                <Bot className="h-3 w-3" />
                                <span className="text-muted-foreground">{item.assignee}</span>
                              </div>
                            )}
                            <span className="text-[0.5rem] text-muted-foreground">
                              {formatDate(item.updatedAt)}
                            </span>
                          </div>
                        </div>
                        
                        <p className="text-[0.55rem] text-muted-foreground line-clamp-2">
                          {item.description}
                        </p>
                        
                        <div className="flex flex-wrap gap-1 mt-2">
                          {item.tags.map((tag) => (
                            <span
                              key={tag}
                              className="text-[0.45rem] px-1.5 py-0.5 rounded bg-muted/30 text-muted-foreground"
                            >
                              #{tag}
                            </span>
                          ))}
                        </div>
                        
                        <div className="mt-2 flex items-center gap-2 text-[0.5rem]">
                          <span className="text-muted-foreground">Status:</span>
                          <span className={`text-[0.5rem] font-medium ${getStatusColor(item.status)}`}>
                            {item.status.toUpperCase()}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )
        )}
      </div>
    </HudPanel>
  )
}

// Helper functions for Kanban
function getPriorityBorderColor(priority: 'low' | 'medium' | 'high'): string {
  const colors: Record<'low' | 'medium' | 'high', string> = {
    low: 'border-secondary/30',
    medium: 'border-accent/30',
    high: 'border-primary/30'
  };
  return colors[priority];
}

function getPriorityDot(priority: 'low' | 'medium' | 'high'): string {
  const dots: Record<'low' | 'medium' | 'high', string> = {
    low: '●',
    medium: '○',
    high: '◉'
  };
  return dots[priority];
}

function getStatusColor(status: 'todo' | 'in-progress' | 'review' | 'done'): string {
  const colors: Record<'todo' | 'in-progress' | 'review' | 'done', string> = {
    todo: 'text-muted-foreground',
    'in-progress': 'text-accent',
    review: 'text-warning',
    done: 'text-success'
  };
  return colors[status];
}

function formatDate(timestamp: number): string {
  return new Date(timestamp).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric'
  });
}