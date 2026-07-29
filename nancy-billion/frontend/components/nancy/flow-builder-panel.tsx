'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Plus, Play, Save, Trash2, Workflow, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

/** Billion's own native visual flow builder -- real execution over the
 * real tool dispatcher/LLM (see backend/flow_engine.py), built without a
 * heavy new frontend graph library (avoids the exact class of dependency
 * risk this project already hit once this session with a much smaller
 * addition). Nodes are auto-laid-out left-to-right by real topological
 * depth; edges are real SVG lines between real port positions. */

type NodeKind = 'input' | 'tool' | 'llm' | 'output'

interface FlowNode {
  id: string
  kind: NodeKind
  label: string
  config: Record<string, unknown>
}
interface FlowEdge {
  source: string
  target: string
}
interface FlowSummary {
  id: string
  name: string
  nodes: FlowNode[]
  edges: FlowEdge[]
  updated_at: number
}
interface TraceStep {
  node_id: string
  kind: string
  label: string
  success: boolean
  duration_s: number
  output_preview?: string
  error?: string
}
interface RunResult {
  success: boolean
  output?: unknown
  error?: string
  trace?: TraceStep[]
}

const KIND_COLORS: Record<NodeKind, string> = {
  input: 'border-primary/50 bg-primary/10 text-primary',
  tool: 'border-gold/50 bg-gold/10 text-gold',
  llm: 'border-accent/50 bg-accent/10 text-accent',
  output: 'border-destructive/50 bg-destructive/10 text-destructive',
}

function newNodeId(existing: FlowNode[]): string {
  let i = existing.length + 1
  while (existing.some((n) => n.id === `node_${i}`)) i++
  return `node_${i}`
}

/** Real topological depth per node -- used purely for left-to-right
 * auto-layout columns, same dependency-order concept the backend's real
 * execution uses (a node can't render left of anything it depends on). */
function computeDepths(nodes: FlowNode[], edges: FlowEdge[]): Record<string, number> {
  const depth: Record<string, number> = {}
  const incoming: Record<string, string[]> = {}
  nodes.forEach((n) => { incoming[n.id] = [] })
  edges.forEach((e) => { incoming[e.target]?.push(e.source) })
  const visiting = new Set<string>()
  function visit(id: string): number {
    if (depth[id] !== undefined) return depth[id]
    if (visiting.has(id)) return 0 // real cycle -- don't infinite-loop the layout
    visiting.add(id)
    const deps = incoming[id] || []
    const d = deps.length === 0 ? 0 : Math.max(...deps.map(visit)) + 1
    depth[id] = d
    visiting.delete(id)
    return d
  }
  nodes.forEach((n) => visit(n.id))
  return depth
}

export function FlowBuilderPanel() {
  const [flows, setFlows] = useState<FlowSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [name, setName] = useState('Untitled Flow')
  const [nodes, setNodes] = useState<FlowNode[]>([])
  const [edges, setEdges] = useState<FlowEdge[]>([])
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [running, setRunning] = useState(false)
  const [runResult, setRunResult] = useState<RunResult | null>(null)
  const [pendingEdgeSource, setPendingEdgeSource] = useState<string | null>(null)

  const loadFlows = useCallback(() => {
    setLoading(true)
    fetch('/api/flows', { cache: 'no-store' })
      .then((r) => r.json())
      .then((j) => setFlows(j.success ? j.flows : []))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { loadFlows() }, [loadFlows])

  const selectFlow = useCallback((flow: FlowSummary) => {
    setActiveId(flow.id)
    setName(flow.name)
    setNodes(flow.nodes)
    setEdges(flow.edges)
    setSelectedNodeId(null)
    setRunResult(null)
  }, [])

  const startNewFlow = useCallback(() => {
    setActiveId(null)
    setName('Untitled Flow')
    setNodes([{ id: 'node_1', kind: 'input', label: 'Input', config: { name: 'goal' } }])
    setEdges([])
    setSelectedNodeId('node_1')
    setRunResult(null)
  }, [])

  const addNode = useCallback((kind: NodeKind) => {
    setNodes((prev) => {
      const id = newNodeId(prev)
      const config: Record<string, unknown> =
        kind === 'input' ? { name: 'value' } :
        kind === 'tool' ? { tool_name: '', args: {} } :
        kind === 'llm' ? { prompt: '' } :
        { from: '' }
      const next = [...prev, { id, kind, label: kind, config }]
      setSelectedNodeId(id)
      return next
    })
  }, [])

  const removeNode = useCallback((id: string) => {
    setNodes((prev) => prev.filter((n) => n.id !== id))
    setEdges((prev) => prev.filter((e) => e.source !== id && e.target !== id))
    setSelectedNodeId((cur) => (cur === id ? null : cur))
  }, [])

  const updateNode = useCallback((id: string, patch: Partial<FlowNode>) => {
    setNodes((prev) => prev.map((n) => (n.id === id ? { ...n, ...patch } : n)))
  }, [])

  const updateNodeConfig = useCallback((id: string, key: string, value: unknown) => {
    setNodes((prev) => prev.map((n) => (n.id === id ? { ...n, config: { ...n.config, [key]: value } } : n)))
  }, [])

  const onNodeClick = useCallback((id: string) => {
    if (pendingEdgeSource && pendingEdgeSource !== id) {
      setEdges((prev) =>
        prev.some((e) => e.source === pendingEdgeSource && e.target === id)
          ? prev
          : [...prev, { source: pendingEdgeSource, target: id }],
      )
      setPendingEdgeSource(null)
      return
    }
    setSelectedNodeId(id)
  }, [pendingEdgeSource])

  const removeEdge = useCallback((source: string, target: string) => {
    setEdges((prev) => prev.filter((e) => !(e.source === source && e.target === target)))
  }, [])

  const saveFlow = useCallback(async () => {
    setSaving(true)
    try {
      const body = { name, nodes, edges }
      const res = activeId
        ? await fetch(`/api/flows/${activeId}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
        : await fetch('/api/flows', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      const json = await res.json()
      if (json.success) {
        setActiveId(json.flow?.id ?? json.flow_id ?? activeId)
        loadFlows()
      }
    } finally {
      setSaving(false)
    }
  }, [activeId, name, nodes, edges, loadFlows])

  const runFlow = useCallback(async () => {
    if (!activeId) return
    setRunning(true)
    setRunResult(null)
    try {
      const res = await fetch(`/api/flows/${activeId}/run`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ inputs: {} }),
      })
      setRunResult(await res.json())
    } catch {
      setRunResult({ success: false, error: 'Request failed' })
    } finally {
      setRunning(false)
    }
  }, [activeId])

  const deleteFlow = useCallback(async (id: string) => {
    await fetch(`/api/flows/${id}`, { method: 'DELETE' })
    if (activeId === id) startNewFlow()
    loadFlows()
  }, [activeId, loadFlows, startNewFlow])

  const depths = useMemo(() => computeDepths(nodes, edges), [nodes, edges])
  const columns = useMemo(() => {
    const cols: Record<number, FlowNode[]> = {}
    nodes.forEach((n) => {
      const d = depths[n.id] ?? 0
      cols[d] = cols[d] || []
      cols[d].push(n)
    })
    return cols
  }, [nodes, depths])
  const selectedNode = nodes.find((n) => n.id === selectedNodeId) || null

  const NODE_W = 168
  const NODE_H = 56
  const COL_GAP = 220
  const ROW_GAP = 76
  const nodePos = useMemo(() => {
    const pos: Record<string, { x: number; y: number }> = {}
    Object.entries(columns).forEach(([colStr, colNodes]) => {
      const col = Number(colStr)
      colNodes.forEach((n, i) => {
        pos[n.id] = { x: col * COL_GAP + 20, y: i * ROW_GAP + 20 }
      })
    })
    return pos
  }, [columns])
  const canvasW = (Math.max(0, ...Object.keys(columns).map(Number)) + 1) * COL_GAP + NODE_W + 40
  const canvasH = Math.max(200, (Math.max(1, ...Object.values(columns).map((c) => c.length))) * ROW_GAP + 40)

  return (
    <div className="flex h-full gap-3">
      {/* Saved flows sidebar */}
      <div className="flex w-52 shrink-0 flex-col gap-2 rounded-xl border border-border bg-card/60 p-3">
        <button
          type="button" onClick={startNewFlow}
          className="flex items-center justify-center gap-1.5 rounded-lg border border-primary/40 bg-primary/10 px-2 py-1.5 text-xs text-primary hover:bg-primary/20"
        >
          <Plus className="h-3.5 w-3.5" /> New Flow
        </button>
        <div className="flex flex-col gap-1 overflow-y-auto">
          {loading && <div className="text-[0.6rem] text-muted-foreground">Loading…</div>}
          {!loading && flows.length === 0 && (
            <div className="text-[0.6rem] text-muted-foreground">No saved flows yet.</div>
          )}
          {flows.map((f) => (
            <div
              key={f.id}
              className={cn(
                'group flex items-center justify-between gap-1 rounded-lg border px-2 py-1.5 text-[0.62rem] cursor-pointer',
                activeId === f.id ? 'border-primary/50 bg-primary/10 text-primary' : 'border-border/60 text-foreground hover:border-primary/30',
              )}
              onClick={() => selectFlow(f)}
            >
              <span className="flex items-center gap-1.5 truncate"><Workflow className="h-3 w-3 shrink-0" /> {f.name}</span>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); deleteFlow(f.id) }}
                className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Canvas + toolbar */}
      <div className="flex flex-1 flex-col gap-2 overflow-hidden">
        <div className="flex items-center gap-2 rounded-xl border border-border bg-card/60 px-3 py-2">
          <input
            value={name} onChange={(e) => setName(e.target.value)}
            className="flex-1 rounded-md border border-border/60 bg-background/40 px-2 py-1 text-xs text-foreground outline-none focus:border-primary/50"
          />
          {(['input', 'tool', 'llm', 'output'] as NodeKind[]).map((k) => (
            <button
              key={k} type="button" onClick={() => addNode(k)}
              className={cn('rounded-md border px-2 py-1 text-[0.6rem]', KIND_COLORS[k])}
            >
              + {k}
            </button>
          ))}
          <button
            type="button" onClick={saveFlow} disabled={saving}
            className="flex items-center gap-1 rounded-md border border-border bg-card px-2 py-1 text-[0.6rem] text-foreground hover:border-primary/50 disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />} Save
          </button>
          <button
            type="button" onClick={runFlow} disabled={!activeId || running}
            className="flex items-center gap-1 rounded-md border border-primary/40 bg-primary/10 px-2 py-1 text-[0.6rem] text-primary hover:bg-primary/20 disabled:opacity-50"
          >
            {running ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />} Run
          </button>
        </div>

        {pendingEdgeSource && (
          <div className="rounded-md border border-gold/40 bg-gold/10 px-2 py-1 text-[0.58rem] text-gold">
            Click a target node to connect from {pendingEdgeSource}, or click empty space to cancel.
          </div>
        )}

        <div className="relative flex-1 overflow-auto rounded-xl border border-border bg-background/40" onClick={() => setPendingEdgeSource(null)}>
          <svg width={canvasW} height={canvasH} className="absolute left-0 top-0">
            {edges.map((e, i) => {
              const s = nodePos[e.source]; const t = nodePos[e.target]
              if (!s || !t) return null
              const x1 = s.x + NODE_W; const y1 = s.y + NODE_H / 2
              const x2 = t.x; const y2 = t.y + NODE_H / 2
              const midX = (x1 + x2) / 2
              return (
                <g key={i}>
                  <path
                    d={`M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`}
                    fill="none" stroke="var(--primary)" strokeWidth={1.5} opacity={0.5}
                  />
                  <circle
                    cx={midX} cy={(y1 + y2) / 2} r={5} fill="var(--card)" stroke="var(--destructive)" strokeWidth={1}
                    className="cursor-pointer"
                    onClick={(ev) => { ev.stopPropagation(); removeEdge(e.source, e.target) }}
                  />
                </g>
              )
            })}
          </svg>
          <div className="relative" style={{ width: canvasW, height: canvasH }}>
            {nodes.map((n) => {
              const p = nodePos[n.id] || { x: 20, y: 20 }
              return (
                <div
                  key={n.id}
                  onClick={(e) => { e.stopPropagation(); onNodeClick(n.id) }}
                  className={cn(
                    'absolute flex cursor-pointer flex-col justify-center rounded-lg border px-2.5 py-1.5 text-[0.62rem] shadow-sm',
                    KIND_COLORS[n.kind],
                    selectedNodeId === n.id && 'ring-2 ring-primary',
                    pendingEdgeSource === n.id && 'ring-2 ring-gold',
                  )}
                  style={{ left: p.x, top: p.y, width: NODE_W, height: NODE_H }}
                >
                  <div className="flex items-center justify-between">
                    <span className="truncate font-medium">{n.label || n.id}</span>
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); setPendingEdgeSource(n.id) }}
                      title="Connect from this node"
                      className="rounded-full border border-current/40 px-1 text-[0.5rem]"
                    >
                      →
                    </button>
                  </div>
                  <span className="truncate text-[0.55rem] opacity-70">{n.kind} · {n.id}</span>
                </div>
              )
            })}
            {nodes.length === 0 && (
              <div className="p-6 text-[0.65rem] text-muted-foreground">
                Add nodes with the buttons above, then click a node's → to connect it to another.
              </div>
            )}
          </div>
        </div>

        {runResult && (
          <div className={cn('max-h-40 overflow-y-auto rounded-xl border px-3 py-2 text-[0.6rem]', runResult.success ? 'border-primary/40 bg-primary/5' : 'border-destructive/40 bg-destructive/5')}>
            <div className="mb-1 font-medium">{runResult.success ? 'Run succeeded' : `Run failed: ${runResult.error}`}</div>
            {runResult.trace?.map((t) => (
              <div key={t.node_id} className={cn('flex items-center gap-2', t.success ? 'text-muted-foreground' : 'text-destructive')}>
                <span className="w-20 truncate">{t.node_id}</span>
                <span className="w-12">{t.kind}</span>
                <span className="w-14">{t.duration_s}s</span>
                <span className="truncate">{t.success ? t.output_preview : t.error}</span>
              </div>
            ))}
            {runResult.success && runResult.output !== undefined && (
              <div className="mt-1 border-t border-border/40 pt-1">Output: {JSON.stringify(runResult.output).slice(0, 400)}</div>
            )}
          </div>
        )}
      </div>

      {/* Node config side panel */}
      <div className="w-64 shrink-0 rounded-xl border border-border bg-card/60 p-3">
        {!selectedNode && <div className="text-[0.6rem] text-muted-foreground">Select a node to configure it.</div>}
        {selectedNode && (
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-[0.65rem] font-medium">{selectedNode.id}</span>
              <button type="button" onClick={() => removeNode(selectedNode.id)} className="text-muted-foreground hover:text-destructive">
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
            <label className="text-[0.55rem] text-muted-foreground">Label</label>
            <input
              value={selectedNode.label}
              onChange={(e) => updateNode(selectedNode.id, { label: e.target.value })}
              className="rounded-md border border-border/60 bg-background/40 px-2 py-1 text-xs outline-none focus:border-primary/50"
            />
            {selectedNode.kind === 'input' && (
              <>
                <label className="text-[0.55rem] text-muted-foreground">Input name (referenced as input.NAME)</label>
                <input
                  value={String(selectedNode.config.name ?? '')}
                  onChange={(e) => updateNodeConfig(selectedNode.id, 'name', e.target.value)}
                  className="rounded-md border border-border/60 bg-background/40 px-2 py-1 text-xs outline-none focus:border-primary/50"
                />
              </>
            )}
            {selectedNode.kind === 'tool' && (
              <>
                <label className="text-[0.55rem] text-muted-foreground">Tool name (e.g. web_search)</label>
                <input
                  value={String(selectedNode.config.tool_name ?? '')}
                  onChange={(e) => updateNodeConfig(selectedNode.id, 'tool_name', e.target.value)}
                  className="rounded-md border border-border/60 bg-background/40 px-2 py-1 text-xs outline-none focus:border-primary/50"
                />
                <label className="text-[0.55rem] text-muted-foreground">Args JSON (values may use {'{{node_id.field}}'})</label>
                <textarea
                  rows={5}
                  value={JSON.stringify(selectedNode.config.args ?? {}, null, 2)}
                  onChange={(e) => { try { updateNodeConfig(selectedNode.id, 'args', JSON.parse(e.target.value)) } catch { /* wait for valid JSON */ } }}
                  className="rounded-md border border-border/60 bg-background/40 px-2 py-1 font-mono text-[0.6rem] outline-none focus:border-primary/50"
                />
              </>
            )}
            {selectedNode.kind === 'llm' && (
              <>
                <label className="text-[0.55rem] text-muted-foreground">Prompt (may use {'{{node_id.field}}'})</label>
                <textarea
                  rows={6}
                  value={String(selectedNode.config.prompt ?? '')}
                  onChange={(e) => updateNodeConfig(selectedNode.id, 'prompt', e.target.value)}
                  className="rounded-md border border-border/60 bg-background/40 px-2 py-1 text-xs outline-none focus:border-primary/50"
                />
              </>
            )}
            {selectedNode.kind === 'output' && (
              <>
                <label className="text-[0.55rem] text-muted-foreground">From ({'{{node_id.field}}'})</label>
                <input
                  value={String(selectedNode.config.from ?? '')}
                  onChange={(e) => updateNodeConfig(selectedNode.id, 'from', e.target.value)}
                  className="rounded-md border border-border/60 bg-background/40 px-2 py-1 text-xs outline-none focus:border-primary/50"
                />
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
