'use client'

import { useEffect, useState } from 'react'
import { ArcReactor, HudPanel, RadialGauge, StatBar } from './hud-bits'
import type { AgentInfo, NewsItem } from '@/lib/nancy/types'
import {
  Activity,
  Cpu,
  Database,
  Shield,
  Bot,
  Terminal,
  Folder,
  Globe2,
  Music,
  Mail,
  Camera,
  Calculator,
  Code2,
  RSS,
  Speaker,
  Play,
  Pause,
  SkipBack,
  SkipForward,
  Volume2,
  Server,
  Menu
} from 'lucide-react'

const AGENTS: AgentInfo[] = [
  { id: 'a1', name: 'ORACLE', role: 'Research & retrieval', load: 62, status: 'online' },
  { id: 'a2', name: 'FORGE', role: 'Code synthesis', load: 78, status: 'online' },
  { id: 'a3', name: 'WARDEN', role: 'Security & defense', load: 34, status: 'online' },
  { id: 'a4', name: 'ATLAS', role: 'Geospatial intel', load: 51, status: 'online' },
  { id: 'a5', name: 'ECHO', role: 'Voice & language', load: 45, status: 'idle' },
  { id: 'a6', name: 'MUSE', role: 'Creative generation', load: 22, status: 'training' },
]

function useJitter(base: number, amp = 6) {
  const [v, setV] = useState(base)
  useEffect(() => {
    const t = setInterval(() => {
      setV(Math.max(2, Math.min(100, base + (Math.random() - 0.5) * amp * 2)))
    }, 1600)
    return () => clearInterval(t)
  }, [base, amp])
  return v
}

export function OverviewPanel() {
  const cpu = useJitter(47)
  const mem = useJitter(63)
  const net = useJitter(38)
  return (
    <div className="flex flex-col gap-3">
      <HudPanel title="Reactor Core" right={<span className="text-primary">100%</span>}>
        <div className="flex items-center justify-center py-2">
          <ArcReactor size={170} />
        </div>
        <p className="text-center text-[0.55rem] uppercase tracking-[0.2em] text-muted-foreground">
          Output 8.6 GW &middot; Stable
        </p>
      </HudPanel>

      <HudPanel title="System Telemetry">
        <div className="flex flex-col gap-3">
          <StatBar label="Neural CPU" value={cpu.toFixed(0)} unit="%" pct={cpu} />
          <StatBar label="Memory" value={mem.toFixed(0)} unit="%" pct={mem} amber />
          <StatBar label="Net Uplink" value={`${(net * 12).toFixed(0)}`} unit="Mb/s" pct={net} />
        </div>
      </HudPanel>

      <HudPanel title="Quick Stats">
        <div className="grid grid-cols-3 gap-1 text-center">
          {[
            { icon: Cpu, label: 'CORES', v: '128' },
            { icon: Database, label: 'STORAGE', v: '4.2 PB' },
            { icon: Shield, label: 'THREATS', v: '0' },
          ].map(({ icon: Icon, label, v }) => (
            <div
              key={label}
              className="flex flex-col items-center gap-1 rounded border border-border bg-secondary/30 py-2"
            >
              <Icon className="h-4 w-4 text-primary" />
              <span className="font-heading text-xs text-foreground">{v}</span>
              <span className="text-[0.5rem] uppercase tracking-widest text-muted-foreground">
                {label}
              </span>
            </div>
          ))}
        </div>
      </HudPanel>
    </div>
  )
}

export function CorePanel() {
  const a = useJitter(72, 8)
  const b = useJitter(55, 8)
  const c = useJitter(88, 5)
  return (
    <div className="flex flex-col gap-3">
      <HudPanel title="Neural Core" right={<span className="text-primary">ACTIVE</span>}>
        <div className="flex flex-wrap items-center justify-around gap-2 py-2">
          <RadialGauge value={a} label="Cognition" color="var(--hud)" />
          <RadialGauge value={b} label="Inference" color="var(--accent)" />
          <RadialGauge value={c} label="Sync" color="var(--hud)" />
        </div>
      </HudPanel>
      <HudPanel title="Model Stack">
        <ul className="flex flex-col gap-2 text-[0.6rem]">
          {[
            ['Reasoning Engine', 'gpt-class · 671B'],
            ['Vision Cortex', 'multimodal · online'],
            ['Voice Synthesis', 'neural TTS · ready'],
            ['Memory Index', '2.4M vectors'],
          ].map(([k, v]) => (
            <li
              key={k}
              className="flex items-center justify-between border-b border-border/50 pb-1.5"
            >
              <span className="flex items-center gap-1.5 text-muted-foreground">
                <Activity className="h-3 w-3 text-primary" />
                {k}
              </span>
              <span className="text-primary">{v}</span>
            </li>
          ))}
        </ul>
      </HudPanel>
    </div>
  )
}

export function AgentsPanel({ onAgentSelect }: { onAgentSelect: (agentId: string) => void }) {
  return (
    <HudPanel
      title="Autonomous Agents"
      right={<span className="text-primary">6 DEPLOYED</span>}
    >
      <ul className="flex flex-col gap-2">
        {AGENTS.map((agent) => {
          const isActive = agent.status === 'online' && agent.load > 50;
          return (
            <li
              key={agent.id}
              onClick={() => onAgentSelect(agent.id)}
              className={`flex flex-col gap-2 rounded border p-2 transition-all duration-300 ${
                isActive
                  ? 'border-[2px] border-gradient-primary hover:shadow-[0_0_20px_10px_rgba(56,211,235,0.4)]'
                  : 'border-border bg-secondary/30 hover:bg-secondary/40'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5 font-heading text-[0.7rem] tracking-widest text-foreground">
                  <Bot className="h-3.5 w-3.5 text-primary" />
                  {agent.name}
                </span>
                <span
                  className={`text-[0.5rem] uppercase tracking-widest ${
                    agent.status === 'online'
                      ? 'text-primary'
                      : agent.status === 'idle'
                        ? 'text-muted-foreground'
                        : 'text-accent'
                  }`}
                >
                  {agent.status}
                </span>
              </div>
              <p className="mb-1.5 text-[0.55rem] text-muted-foreground">
                {agent.role}
              </p>
              <div className="flex items-center gap-3">
                <div className="h-2 w-20 overflow-hidden rounded-full bg-background/60">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${agent.load}%`,
                      background:
                        agent.status === 'training' ? 'var(--accent)' : 'var(--hud)',
                      boxShadow: '0 0 4px var(--hud)',
                    }}
                  />
                </div>
                <span className="text-[0.5rem] text-muted-foreground">{agent.load}%</span>
              </div>
            </li>
          );
        })}
      </ul>
    </HudPanel>
  )
}

const APPS = [
  { icon: Terminal, label: 'Terminal', key: 'terminal' },
  { icon: Globe2, label: 'Browser', key: 'browser' },
  { icon: Folder, label: 'Files', key: 'files' },
  { icon: Code2, label: 'Editor', key: 'editor' },
  { icon: Music, label: 'Music', key: 'music' },
  { icon: Mail, label: 'Mail', key: 'mail' },
  { icon: Camera, label: 'Camera', key: 'camera' },
  { icon: Calculator, label: 'Calc', key: 'calculator' },
]

export function SystemPanel({
  onLaunch,
  launched,
}: {
  onLaunch: (key: string) => void
  launched: string | null
}) {
  return (
    <HudPanel title="Command Layer">
      <p className="mb-2 text-[0.55rem] leading-relaxed text-muted-foreground">
        Simulated OS bridge. Say{' '}
        <span className="text-primary">&ldquo;Nancy, open terminal&rdquo;</span> or
        tap an app.
      </p>
      <div className="grid grid-cols-4 gap-2">
        {APPS.map(({ icon: Icon, label, key }) => (
          <button
            key={key}
            type="button"
            onClick={() => onLaunch(key)}
            className={`flex flex-col items-center gap-1 rounded border p-2 transition-colors ${
              launched === key
                ? 'border-primary bg-primary/15'
                : 'border-border bg-secondary/30 hover:border-primary/60'
            }`}
          >
            <Icon
              className={`h-5 w-5 ${
                launched === key ? 'text-primary hud-glow' : 'text-foreground'
              }`}
            />
            <span className="text-[0.5rem] uppercase tracking-wide text-muted-foreground">
              {label}
            </span>
          </button>
        ))}
      </div>
      {launched && (
        <div className="mt-2 rounded border border-primary/40 bg-background/60 p-2 text-[0.55rem] text-primary">
          {'>'} launching <span className="uppercase">{launched}</span> ...
          process spawned [pid {Math.floor(1000 + Math.random() * 8000)}]
        </div>
      )}
    </HudPanel>
  )
}

export function NewsPanel({ onNewsSelect }: { onNewsSelect: (newsId: string) => void }) {
  // Mock news data - in a real implementation, this would come from an API
  const [newsItems, setNewsItems] = useState<NewsItem[]>([
    {
      id: 'news-1',
      title: 'Breakthrough in Quantum Computing Achieved',
      source: 'MIT Technology Review',
      timestamp: Date.now() - 3600000, // 1 hour ago
      summary: 'Researchers have demonstrated quantum supremacy with a 128-qubit processor, solving a problem that would take classical supercomputers thousands of years.',
      category: 'technology',
      read: false
    },
    {
      id: 'news-2',
      title: 'Global AI Regulation Framework Proposed',
      source: 'Financial Times',
      timestamp: Date.now() - 7200000, // 2 hours ago
      summary: 'International coalition proposes unified framework for AI governance focusing on transparency, accountability, and ethical development.',
      category: 'policy',
      read: false
    },
    {
      id: 'news-3',
      title: 'Renewable Energy Investment Reaches Record High',
      source: 'Bloomberg Green',
      timestamp: Date.now() - 10800000, // 3 hours ago
      summary: 'Global investment in renewable energy infrastructure hits $1.3 trillion in Q2, driven by solar and wind power expansion.',
      category: 'finance',
      read: true
    },
    {
      id: 'news-4',
      title: 'Neural Interface Enables Thought-to-Text Communication',
      source: 'Nature Neuroscience',
      timestamp: Date.now() - 14400000, // 4 hours ago
      summary: 'New brain-computer interface allows users to type text directly from thought with 95% accuracy, no physical movement required.',
      category: 'health',
      read: false
    },
    {
      id: 'news-5',
      title: 'Mars Colony Successfully Harvests First Crops',
      source: 'Space.com',
      timestamp: Date.now() - 18000000, // 5 hours ago
      summary: 'First successful harvest of genetically modified wheat in Martian soil marks major milestone for sustainable off-world colonization.',
      category: 'science',
      read: false
    }
  ]);

  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());

  const refreshNews = useCallback(async () => {
    setRefreshing(true);
    try {
      // Simulate API call
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      // In a real implementation, this would fetch from news APIs
      // For now, we'll just update the timestamp and mark some as unread
      setNewsItems(prev => 
        prev.map(item => ({
          ...item,
          // Randomly mark some items as unread for demo
          read: Math.random() > 0.7 || item.read
        }))
      );
      setLastUpdated(new Date());
    } finally {
      setRefreshing(false);
    }
  }, []);

  // Auto-refresh every 5 minutes
  useEffect(() => {
    const interval = setInterval(refreshNews, 300000); // 5 minutes
    return () => clearInterval(interval);
  }, [refreshNews]);

  return (
    <HudPanel 
      title="Intelligence Feed"
      right={<div className="flex items-center gap-2">
        <button
          onClick={refreshNews}
          disabled={refreshing}
          className={`text-[0.5rem] hover:text-primary transition-colors ${
            refreshing ? 'opacity-50' : ''
          }`}
        >
          <RSS className="h-3 w-3" />
          <span className="text-[0.5rem]">{refreshing ? 'Updating...' : 'Refresh'}</span>
        </button>
        <span className="text-[0.5rem] text-muted-foreground">
          Updated {lastUpdated.toLocaleTimeString()}
        </span>
      </div>}
    >
      <div className="flex flex-col gap-2">
        {newsItems.map((news) => (
          <div
            key={news.id}
            onClick={() => onNewsSelect(news.id)}
            className={`flex flex-col gap-1 rounded border p-2 transition-all duration-200 ${
              !news.read
                ? 'border-[1px] border-primary bg-primary/10 hover:bg-primary/5'
                : 'border-border bg-secondary/20 hover:bg-secondary/30'
            }`}
          >
            <div className="flex items-start gap-2">
              <div className="flex-shrink-0">
                {/* Category badge */}
                <span className={`text-[0.4rem] px-1.5 py-0.5 rounded ${getCategoryColor(news.category)}`}>
                  {news.category.toUpperCase()}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex justify-between items-start mb-1">
                  <h3 className="font-heading text-[0.65rem] text-foreground line-clamp-2">
                    {news.title}
                  </h3>
                  <span className="text-[0.45rem] text-muted-foreground">
                    {news.source} · {formatTimestamp(news.timestamp)}
                  </span>
                </div>
                <p className="text-[0.55rem] text-muted-foreground line-clamp-3">
                  {news.summary}
                </p>
                {!news.read && (
                  <div className="mt-1 flex items-center gap-2">
                    <Speaker className="h-3 w-3 text-primary hover:text-primary/80 cursor-pointer"
                      onClick={(e) => {
                        e.stopPropagation();
                        speakNewsSummary(news);
                      }}
                    />
                    <span className="text-[0.5rem] text-primary cursor-pointer hover:text-primary/80"
                      onClick={(e) => {
                        e.stopPropagation();
                        speakNewsSummary(news);
                      }}
                    >
                      Listen
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
        
        {/* Loading placeholder when refreshing */}
        {refreshing && newsItems.length === 0 && (
          <div className="flex flex-col items-center justify-center py-4">
            <div className="h-4 w-4 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
            <p className="mt-2 text-[0.55rem] text-muted-foreground">Updating intelligence feed...</p>
          </div>
        )}
        
        {/* Empty state */}
        {!refreshing && newsItems.length === 0 && (
          <div className="flex flex-col items-center justify-center py-4 text-center">
            <p className="text-[0.55rem] text-muted-foreground">No news items available</p>
          </div>
        )}
      </div>
    </HudPanel>
  )
}

// Helper function to get color based on category
function getCategoryColor(category: string): string {
  const colors: Record<string, string> = {
    technology: 'bg-primary/20 text-primary',
    finance: 'bg-accent/20 text-accent',
    policy: 'bg-warning/20 text-warning',
    science: 'bg-secondary/20 text-secondary',
    health: 'bg-success/20 text-success',
    default: 'bg-muted/20 text-muted-foreground'
  };
  
  return colors[category] || colors.default;
}

// Helper function to format timestamp
function formatTimestamp(timestamp: number): string {
  const now = Date.now();
  const diff = now - timestamp;
  
  if (diff < 60000) { // Less than 1 minute
    return 'just now';
  } else if (diff < 3600000) { // Less than 1 hour
    const minutes = Math.floor(diff / 60000);
    return `${minutes}m ago`;
  } else if (diff < 86400000) { // Less than 24 hours
    const hours = Math.floor(diff / 3600000);
    return `${hours}h ago`;
  } else {
    return new Date(timestamp).toLocaleDateString();
  }
}

// Function to speak news summary
function speakNewsSummary(news: NewsItem) {
  const text = `
    Breaking news from ${news.source}. ${news.title}. 
    ${news.summary}
  `;
  
  // In a real implementation, we'd use the voice system
  // For now, we'll just log it
  console.log('Speaking news:', text);
  // speak(text); // Uncomment when voice system is integrated
}

/** Media Panel – controls for music and media playback */
export function MediaPanel({
  onPlayPause,
  onNextTrack,
  onPreviousTrack,
  onVolumeChange,
  currentTrack,
  isPlaying,
  volumeLevel
}: {
  onPlayPause: () => void
  onNextTrack: () => void
  onPreviousTrack: () => void
  onVolumeChange: (volume: number) => void
  currentTrack: { title: string; artist: string; albumArt?: string } | null
  isPlaying: boolean
  volumeLevel: number
}) {
  return (
    <HudPanel title="Media Control">
      <div className="flex flex-col gap-3">
        {/* Now Playing */}
        {currentTrack ? (
          <div className="flex items-center gap-3 p-2 rounded border border-hud/30 bg-background/50">
            {currentTrack.albumArt ? (
              <div className="h-12 w-12 rounded overflow-hidden border border-hud/50">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={currentTrack.albumArt}
                  alt={`${currentTrack.title} album art`}
                  className="h-full w-full object-cover"
                />
              </div>
            ) : (
              <div className="h-12 w-12 flex items-center justify-center rounded border border-hud/50 bg-secondary/30">
                <Music className="h-6 w-6 text-primary" />
              </div>
            )}
            <div className="flex-1">
              <h3 className="font-heading text-[0.6rem] text-foreground">
                {currentTrack.title}
              </h3>
              <p className="text-[0.5rem] text-muted-foreground">
                {currentTrack.artist}
              </p>
            </div>
          </div>
        ) : (
          <div className="text-center py-4">
            <p className="text-[0.55rem] text-muted-foreground">
              No track playing
            </p>
            <Music className="h-8 w-8 text-primary/50 mx-auto" />
          </div>
        )}
        
        {/* Controls */}
        <div className="flex items-center justify-center gap-4">
          <button
            type="button"
            onClick={onPreviousTrack}
            className="flex h-8 w-8 items-center justify-center rounded border border-hud/30 bg-secondary/30 text-muted-foreground transition-colors hover:border-primary/60 hover:text-primary"
          >
            <SkipBack className="h-4 w-4" />
          </button>
          
          <button
            type="button"
            onClick={onPlayPause}
            className={`flex h-10 w-10 items-center justify-center rounded border border-hud/30 ${
              isPlaying
                ? 'bg-primary/20 text-primary'
                : 'bg-secondary/30 text-muted-foreground'
            } transition-colors hover-border-primary/60 hover-text-primary`}
          >
            {isPlaying ? (
              <Pause className="h-5 w-5" />
            ) : (
              <Play className="h-5 w-5" />
            )}
          </button>
          
          <button
            type="button"
            onClick={onNextTrack}
            className="flex h-8 w-8 items-center justify-center rounded border border-hud/30 bg-secondary/30 text-muted-foreground transition-colors hover:border-primary/60 hover:text-primary"
          >
            <SkipForward className="h-4 w-4" />
          </button>
        </div>
        
        {/* Progress Bar */}
        <div className="flex items-center gap-2">
          <div className="h-2 w-20 overflow-hidden rounded-full bg-background/60">
            <div
              className="h-full rounded-full"
              style={{
                width: '65%', // In a real implementation, this would be the actual progress
                background: 'var(--hud)',
                boxShadow: '0 0 4px var(--hud)',
                transition: 'width 0.1s linear'
              }}
            />
          </div>
          <div className="flex items-center gap-2 text-[0.5rem]">
            <span>2:30</span>
            <span className="text-muted-foreground">/</span>
            <span>4:15</span>
          </div>
        </div>
        
        {/* Volume Control */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1">
            <Volume2 className="h-4 w-4 text-muted-foreground" />
            <div className="h-0.5 w-10 overflow-hidden rounded-full bg-background/60">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${volumeLevel}%`,
                  background: 'var(--hud)',
                  boxShadow: '0 0 2px var(--hud)',
                  transition: 'width 0.1s linear'
                }}
              />
            </div>
            <Volume2 className="h-4 w-4 text-muted-foreground" />
          </div>
          <span className="text-[0.5rem] text-muted-foreground">
            {volumeLevel}%
          </span>
          <input
            type="range"
            min="0"
            max="100"
            value={volumeLevel}
            onChange={(e) => onVolumeChange(Number(e.target.value))}
            className="h-0 w-0" // Hidden range input for better accessibility
          />
        </div>
        
        {/* Music Source Selector */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1">
            <Server className="h-4 w-4 text-muted-foreground" />
            <span className="text-[0.5rem] text-muted-foreground">Source:</span>
          </div>
          <div className="relative">
            <select
              onChange={(e) => {
                // In a real implementation, this would switch between Spotify/Apple Music/YouTube
                console.log('Switching music source to:', e.target.value);
              }}
              className="px-2 py-1 rounded border border-hud/30 bg-background/60 text-[0.5rem] text-muted-foreground focus:border-primary/60 focus:text-primary"
            >
              <option value="spotify">Spotify</option>
              <option value="apple-music">Apple Music</option>
              <option value="youtube">YouTube</option>
              <option value="local">Local Library</option>
            </select>
          </div>
        </div>
      </div>
    </HudPanel>
  )
}
