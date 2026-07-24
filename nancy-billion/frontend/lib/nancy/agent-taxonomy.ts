/**
 * Shared agent taxonomy — single source of truth for how the fleet's 29 real
 * domains (from /agents/list) are grouped, iconified, and colored. Used by
 * both Mission Control (agent roster) and Kanban (a card's "department" is
 * derived from its assigned agent's category, never invented).
 *
 * Categories are a display-only grouping decision — the backend has no
 * category field of its own.
 */
import type { ElementType } from 'react'
import {
  Activity, Cpu, Database, Shield, Bot, Terminal, Folder, Globe2, RefreshCw,
  Zap, BarChart3, Search, Rss, Radio, Sparkles, Signal, ShieldCheck, Eye,
  Thermometer, Brain, FlaskConical, Scale, Server, Palette, ClipboardList,
  GitBranch, Code2,
} from 'lucide-react'

export const STATUS_DOT: Record<string, string> = {
  online: 'bg-primary',
  executing: 'bg-gold',
  idle: 'bg-muted-foreground',
  training: 'bg-accent',
  offline: 'bg-destructive/60',
  error: 'bg-destructive',
}

export const STATUS_COLOR: Record<string, string> = {
  online: 'text-primary',
  executing: 'text-gold',
  idle: 'text-muted-foreground',
  offline: 'text-destructive',
  training: 'text-accent',
  error: 'text-destructive',
}

export const DOMAIN_ICON: Record<string, ElementType> = {
  'artificial-consciousness': Brain,
  'quantum-reasoning': Zap,
  'quantum-computing': Cpu,
  'embodied-cognition': Bot,
  'neural-interface': Activity,
  'self-improvement': RefreshCw,
  'temporal-prediction': BarChart3,
  'data-science': Database,
  'research': Search,
  'market-research': BarChart3,
  'business-intelligence': BarChart3,
  'bioinformatics': FlaskConical,
  'astrophysics': Globe2,
  'healthcare-analytics': FlaskConical,
  'operations-research': Server,
  'security': Shield,
  'ethics': Scale,
  'legal-compliance': Scale,
  'qa-testing': ShieldCheck,
  'devops': Terminal,
  'system-monitoring': Signal,
  'file-management': Folder,
  'swarm-coordinator': Rss,
  'communication': Radio,
  'environmental-control': Thermometer,
  'holographic-display': Eye,
  'nanotechnology': Sparkles,
  'crypto-trading': BarChart3,
  'creative-design': Palette,
  'planning': ClipboardList,
  'dispatcher': GitBranch,
  'explore': Search,
  'general-purpose': Bot,
  'claude': Sparkles,
  'claude-code-guide': Code2,
  'statusline-setup': Terminal,
}

export interface AgentCategory {
  label: string
  icon: ElementType
  domains: string[]
  color: string
}

export const AGENT_CATEGORIES: AgentCategory[] = [
  { label: 'Cognition & Reasoning', icon: Brain, color: 'oklch(0.72 0.15 42)', domains: ['artificial-consciousness', 'quantum-reasoning', 'quantum-computing', 'embodied-cognition', 'neural-interface', 'self-improvement', 'temporal-prediction'] },
  { label: 'Data & Research', icon: FlaskConical, color: 'oklch(0.68 0.13 290)', domains: ['data-science', 'research', 'market-research', 'business-intelligence', 'bioinformatics', 'astrophysics', 'healthcare-analytics', 'operations-research'] },
  { label: 'Security & Governance', icon: Scale, color: 'oklch(0.78 0.13 88)', domains: ['security', 'ethics', 'legal-compliance', 'qa-testing'] },
  { label: 'Infrastructure & Ops', icon: Server, color: 'oklch(0.72 0.14 200)', domains: ['devops', 'system-monitoring', 'file-management', 'swarm-coordinator', 'communication'] },
  { label: 'Physical & Interface', icon: Cpu, color: 'oklch(0.7 0.14 150)', domains: ['environmental-control', 'holographic-display', 'nanotechnology'] },
  { label: 'Business & Creative', icon: Palette, color: 'oklch(0.68 0.15 20)', domains: ['crypto-trading', 'creative-design'] },
  { label: 'Meta & Orchestration', icon: Sparkles, color: 'oklch(0.7 0.14 250)', domains: ['planning', 'dispatcher', 'explore', 'general-purpose', 'claude', 'claude-code-guide', 'statusline-setup'] },
]

export function categoryFor(domain: string): string {
  return AGENT_CATEGORIES.find((c) => c.domains.includes(domain))?.label ?? 'Other'
}

export function colorFor(domain: string): string {
  return AGENT_CATEGORIES.find((c) => c.domains.includes(domain))?.color ?? 'var(--hud)'
}

export function iconFor(domain: string): ElementType {
  return DOMAIN_ICON[domain] ?? Bot
}

export function categoryIconFor(domain: string): ElementType {
  return AGENT_CATEGORIES.find((c) => c.domains.includes(domain))?.icon ?? Bot
}
