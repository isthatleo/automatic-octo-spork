import type { PanelKey } from './types'

export type CommandResult =
  | { type: 'navigate'; panel: PanelKey; reply: string }
  | { type: 'locate'; query: string; reply: string }
  | { type: 'launch'; target: string; reply: string }
  | { type: 'scan'; reply: string }
  | { type: 'time'; reply: string }
  | { type: 'status'; reply: string }
  | { type: 'greet'; reply: string }
  | { type: 'unknown'; reply: string }

const PANEL_WORDS: Record<string, PanelKey> = {
  overview: 'overview',
  home: 'overview',
  dashboard: 'overview',
  map: 'map',
  satellite: 'map',
  earth: 'map',
  globe: 'map',
  core: 'core',
  brain: 'core',
  neural: 'core',
  agent: 'agents',
  agents: 'agents',
  system: 'system',
  terminal: 'system',
  console: 'system',
}

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
  return s
    .replace(/[.?!,]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

export function parseCommand(rawInput: string): CommandResult {
  const input = clean(rawInput.toLowerCase())

  if (!input) return { type: 'unknown', reply: 'Standing by.' }

  if (/\b(hello|hi|hey|good (morning|evening|afternoon))\b/.test(input)) {
    return { type: 'greet', reply: 'Online and listening. How can I help?' }
  }

  if (/\b(status|report|systems?|diagnostic)\b/.test(input)) {
    return {
      type: 'status',
      reply: 'All systems nominal. Reactor at full output, agents synchronized.',
    }
  }

  if (/\b(scan|analyze|sweep|perimeter)\b/.test(input)) {
    return { type: 'scan', reply: 'Initiating deep scan. Compiling telemetry now.' }
  }

  if (/\b(time|clock)\b/.test(input)) {
    return { type: 'time', reply: 'Pulling local chronometer data.' }
  }

  // Launch / open application
  const launchMatch = input.match(
    /\b(open|launch|run|start|execute)\s+(?:the\s+)?(\w+)/,
  )
  if (launchMatch) {
    const target =
      LAUNCH_TARGETS.find((t) => launchMatch[2].includes(t)) || launchMatch[2]
    return {
      type: 'launch',
      target,
      reply: `Launching ${target}.`,
    }
  }

  // Locate / show place on map
  const locateMatch = input.match(
    /\b(?:locate|find|show me|show|go to|fly to|navigate to|take me to|where is|map|zoom (?:in )?(?:on|to))\s+(.+)/,
  )
  if (locateMatch) {
    const query = clean(locateMatch[1].replace(/^(the|a)\s+/, ''))
    if (query) {
      return {
        type: 'locate',
        query,
        reply: `Acquiring satellite lock on ${query}.`,
      }
    }
  }

  // Panel navigation
  for (const [word, panel] of Object.entries(PANEL_WORDS)) {
    const re = new RegExp(`\\b${word}\\b`)
    if (re.test(input)) {
      return {
        type: 'navigate',
        panel,
        reply: `Opening ${panel} interface.`,
      }
    }
  }

  // Treat a lone short phrase as a place query fallback
  if (input.split(' ').length <= 4 && /^[a-z\s,'-]+$/.test(input)) {
    return {
      type: 'locate',
      query: input,
      reply: `Searching for ${input}.`,
    }
  }

  return {
    type: 'unknown',
    reply: "I didn't catch a recognized command. Try 'locate Tokyo' or 'open terminal'.",
  }
}
