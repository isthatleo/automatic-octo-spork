import type { KnowledgeCategory, PanelKey } from './types'
import { guessSymbol } from './local-brain'

export type CommandResult =
  | { type: 'navigate'; panel: PanelKey; reply: string }
  | { type: 'locate'; query: string; reply: string }
  | { type: 'launch'; target: string; reply: string }
  | { type: 'chart'; symbol: string; reply: string }
  | { type: 'time'; reply: string }
  | { type: 'session'; reply: string }
  | {
      type: 'news'
      category: KnowledgeCategory | null
      topic: string | null
      media: 'articles' | 'videos'
      reply: string
    }
  | { type: 'unknown'; reply: string }

const NEWS_CATEGORY_WORDS: [RegExp, KnowledgeCategory | null][] = [
  [/\b(finance|stock|market|crypto|bitcoin|economy|nasdaq|dow)\b/, 'finance'],
  [/\b(medicine|medical|health|disease|clinical)\b/, 'medicine'],
  [/\b(physics|quantum|particle)\b/, 'physics'],
  [/\b(astrophysics|astronomy|nasa|galaxy|planet|star|cosmos)\b/, 'astrophysics'],
  [/\b(documentary|documentaries)\b/, 'documentaries'],
  [/\b(history|historical)\b/, 'history'],
  [/\b(literature|novel|author)\b/, 'literature'],
  [/\b(science|scientific|research|discovery)\b/, 'science'],
]

const PANEL_WORDS: Record<string, PanelKey> = {
  overview: 'overview',
  home: 'overview',
  dashboard: 'overview',
  map: 'map',
  satellite: 'map',
  earth: 'map',
  globe: 'map',
  recon: 'map',
  core: 'core',
  brain: 'core',
  neural: 'core',
  agent: 'agents',
  agents: 'agents',
  system: 'system',
  terminal: 'system',
  console: 'system',
  kanban: 'kanban',
  channels: 'channels',
  instances: 'instances',
  sessions: 'sessions',
  cron: 'cron',
  skills: 'skills',
  models: 'models',
  config: 'config',
  keys: 'keys',
  usage: 'usage',
  profiles: 'profiles',
  pairing: 'pairing',
  plugins: 'plugins',
  mcp: 'plugins',
  webhooks: 'webhooks',
  docs: 'docs',
  theming: 'theming',
  theme: 'theming',
  canvas: 'canvas',
  achievements: 'achievements',
  // Deliberately not "memory" -- /memory is already an explicit slash
  // command below that opens Sessions (real conversation history), and
  // reusing the same word for a different panel here would make "/memory"
  // and "open memory" navigate two different places for no obvious reason.
  journey: 'memory-insights',
  dreams: 'memory-insights',
  wiki: 'memory-insights',
  galaxy: 'memory-insights',
}

// Real, canonical panel keywords for the "open <word>" pattern below --
// exported so docs-client.ts's command reference can be generated from this
// single source instead of hand-maintaining a second, easily-stale list of
// what's actually navigable (PANEL_WORDS has several synonyms per panel --
// e.g. "home"/"dashboard" both mean 'overview' -- so this picks one
// canonical keyword per real target panel).
export const NAVIGABLE_PANELS: { keyword: string; panel: PanelKey }[] = [
  { keyword: 'overview', panel: 'overview' },
  { keyword: 'map', panel: 'map' },
  { keyword: 'core', panel: 'core' },
  { keyword: 'agents', panel: 'agents' },
  { keyword: 'system', panel: 'system' },
  { keyword: 'kanban', panel: 'kanban' },
  { keyword: 'channels', panel: 'channels' },
  { keyword: 'instances', panel: 'instances' },
  { keyword: 'sessions', panel: 'sessions' },
  { keyword: 'cron', panel: 'cron' },
  { keyword: 'skills', panel: 'skills' },
  { keyword: 'models', panel: 'models' },
  { keyword: 'config', panel: 'config' },
  { keyword: 'keys', panel: 'keys' },
  { keyword: 'usage', panel: 'usage' },
  { keyword: 'theming', panel: 'theming' },
  { keyword: 'profiles', panel: 'profiles' },
  { keyword: 'pairing', panel: 'pairing' },
  { keyword: 'plugins', panel: 'plugins' },
  { keyword: 'webhooks', panel: 'webhooks' },
  { keyword: 'canvas', panel: 'canvas' },
  { keyword: 'journey', panel: 'memory-insights' },
  { keyword: 'achievements', panel: 'achievements' },
  { keyword: 'docs', panel: 'docs' },
]

const LAUNCH_TARGETS = [
  'terminal',
  'browser',
  'files',
  'music',
  'editor',
  'mail',
  'camera',
  'calculator',
]

function clean(s: string) {
  return s.replace(/[.?!,]/g, '').replace(/\s+/g, ' ').trim()
}

// Deliberately narrow: only genuine, deterministic LOCAL UI actions belong
// here (open this real panel, fly to this real place on the map, load this
// real news topic, reset the session). Everything else -- greetings, status
// questions, "who are you", small talk, anything starting with a question
// word -- used to be intercepted here with static canned text that never
// reached the backend at all, regardless of how fast or capable it was.
// Confirmed live as the actual cause of "responses feel hardcoded": e.g.
// "what agents do you have" contained the bare word "agent" and silently
// got hijacked into opening the agents panel instead of being answered.
// Anything not matched below falls through to type: 'unknown', which
// app/page.tsx routes to the real, streaming backend.
export function parseCommand(rawInput: string): CommandResult {
  const input = clean(rawInput.toLowerCase())
  if (!input) return { type: 'unknown', reply: 'Standing by.' }

  // Explicit slash-navigation only -- these open a real panel and nothing
  // more, so an instant local response is legitimate.
  if (/^\/(skills|abilities)\b/.test(input)) {
    return { type: 'navigate', panel: 'skills', reply: "Opening your active skills and attached agents, Sir." }
  }
  if (/^\/(memory|remember|recall)\b/.test(input)) {
    return { type: 'navigate', panel: 'sessions', reply: "Opening memory, session history, and recall tools, Sir." }
  }
  if (/^\/(agents|subagents|orb|boot)\b/.test(input)) {
    return { type: 'navigate', panel: 'agents', reply: "Opening agent command and specialist roster, Sir." }
  }
  if (/^\/(terminal|console|command layer)\b/.test(input)) {
    return { type: 'navigate', panel: 'system', reply: "Opening Command Layer terminal and runtime control, Sir." }
  }
  if (/^\/new$/.test(input)) {
    return {
      type: 'session',
      reply: "Starting a fresh session, Sir. Context cleared and workspace reset.",
    }
  }

  // Real current time -- no backend round trip needed for this one, and
  // page.tsx speaks the actual Date() value, not this placeholder reply.
  if (/\b(time|clock)\b/.test(input) && !/\b(weather|forecast)\b/.test(input)) {
    return { type: 'time', reply: 'Pulling local chronometer data, Sir.' }
  }

  // Real news panel with real category/topic parsing -- the reply is just
  // the transitional phrase while real content loads.
  if (/\b(news|headlines|briefing)\b/.test(input)) {
    const media: 'articles' | 'videos' = /\b(video|videos|watch|documentary|documentaries)\b/.test(input)
      ? 'videos'
      : 'articles'
    const category = NEWS_CATEGORY_WORDS.find(([re]) => re.test(input))?.[1] ?? null
    const topicMatch = input.match(/\b(?:about|on|regarding)\s+(.+)/)
    const topic = topicMatch ? clean(topicMatch[1]) : null
    const subject = topic || (category ? `${category}` : 'top stories')
    return {
      type: 'news',
      category,
      topic,
      media,
      reply: `Pulling up the latest ${media === 'videos' ? 'briefings' : 'coverage'} on ${subject}, Sir.`,
    }
  }

  // TradingView chart, only ever on explicit request -- requires BOTH an
  // open-verb AND the literal word "chart"/"trading view", so a casual
  // mention of a price never pops the widget uninvited (the user was
  // explicit: never show it unless asked to open it). Checked before the
  // generic launch/locate matchers below, which would otherwise swallow
  // "open the chart for gold" (launchMatch) or "show me a chart of gold"
  // (locateMatch's "show me" trigger) as the wrong command type.
  const chartMatch = input.match(
    /\b(?:open|show|launch|pull up|bring up)\b.*?\b(?:trading\s*view|tradingview|chart)\b(?:\s+(?:for|of|on)\s+(.+))?$/,
  )
  if (chartMatch) {
    const subject = chartMatch[1] ? clean(chartMatch[1]) : ''
    const symbol = guessSymbol(subject)
    return { type: 'chart', symbol, reply: `Opening the chart for ${symbol}, Sir.` }
  }

  // "open/launch/run X" -- either a real panel (navigate) or a cosmetic
  // desktop-app launch animation (launch); both require an explicit verb,
  // so this can't accidentally hijack a real question.
  const launchMatch = input.match(/\b(open|launch|run|start|execute)\s+(?:the\s+)?(\w+)/)
  if (launchMatch) {
    const word = launchMatch[2]
    if (PANEL_WORDS[word]) {
      return { type: 'navigate', panel: PANEL_WORDS[word], reply: `Opening ${word} interface, Sir.` }
    }
    const target = LAUNCH_TARGETS.find((t) => word.includes(t)) || word
    return { type: 'launch', target, reply: `Launching ${target}, Sir.` }
  }

  // Real geocoding + map fly-to.
  const locateMatch = input.match(
    /\b(?:locate|find|show me|show|go to|fly to|navigate to|take me to|where is|zoom (?:in )?(?:on|to))\s+(.+)/,
  )
  if (locateMatch) {
    const query = clean(locateMatch[1].replace(/^(the|a)\s+/, ''))
    if (query) {
      return { type: 'locate', query, reply: `Acquiring satellite lock on ${query}, Sir.` }
    }
  }

  // Everything else -- greetings, "/status", "who are you", small talk,
  // questions, unrecognized slash commands -- goes to the real backend,
  // which now has live system context, real skills, and real tools.
  return { type: 'unknown', reply: '' }
}
