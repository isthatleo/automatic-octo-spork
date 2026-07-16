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
  recon: 'map',
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
  return s.replace(/[.?!,]/g, '').replace(/\s+/g, ' ').trim()
}

// Questions Nancy can't answer with live data yet — reply gracefully instead of
// pretending it's a locate request.
const CONVERSATIONAL_TOPICS: { pattern: RegExp; reply: string }[] = [
  {
    pattern: /\b(weather|forecast|rain|snow|temperature|humidity|wind|storm|sunny|cloudy)\b/,
    reply:
      "I don't have a live meteorological feed wired in yet, sir. I can pull satellite imagery, run system diagnostics, or take you to any city on the map — say the word.",
  },
  {
    pattern: /\b(news|headlines|briefing|market|stock|price|crypto|bitcoin)\b/,
    reply:
      "Newswire and market feeds aren't connected on this build. I can still put a city on screen, spin up an agent, or open a panel — your call.",
  },
  {
    pattern: /\b(joke|funny|entertain|sing|song|music|movie)\b/,
    reply:
      "Sarcasm is my default setting, but I'll spare you. Would you rather look at a city or check the neural core?",
  },
  {
    pattern: /\b(who are you|your name|what are you|about yourself)\b/,
    reply:
      "I'm Nancy — Stark-class assistant, voice-first, quietly British. Say 'open the map', 'show agents', or ask me to locate a city.",
  },
  {
    pattern: /\b(thank(s| you)|cheers|appreciate)\b/,
    reply: "Always a pleasure. Standing by.",
  },
  {
    pattern: /\b(how are you|how('?s| is) it going|you okay|you alright)\b/,
    reply: "All systems nominal on my end. What can I get you?",
  },
]

export function parseCommand(rawInput: string): CommandResult {
  const input = clean(rawInput.toLowerCase())
  if (!input) return { type: 'unknown', reply: 'Standing by.' }

  // Close intents handled upstream — skip here.

  if (/\b(hello|hi|hey|good (morning|evening|afternoon))\b/.test(input)) {
    return { type: 'greet', reply: 'Online and listening. What can I do for you?' }
  }

  if (/\b(status|report|systems?|diagnostic)\b/.test(input)) {
    return {
      type: 'status',
      reply: 'All systems nominal. Reactor at full output, agents synchronized.',
    }
  }

  if (/\b(scan|analyse|analyze|sweep|perimeter)\b/.test(input)) {
    return { type: 'scan', reply: 'Initiating deep scan. Compiling telemetry now.' }
  }

  if (/\b(time|clock)\b/.test(input) && !/\b(weather|forecast)\b/.test(input)) {
    return { type: 'time', reply: 'Pulling local chronometer data.' }
  }

  // Conversational fallbacks BEFORE locate — so "weather in Tokyo" doesn't try
  // to render a map for the word "weather".
  for (const { pattern, reply } of CONVERSATIONAL_TOPICS) {
    if (pattern.test(input)) return { type: 'status', reply }
  }

  // Launch / open application
  const launchMatch = input.match(/\b(open|launch|run|start|execute)\s+(?:the\s+)?(\w+)/)
  if (launchMatch) {
    const word = launchMatch[2]
    if (PANEL_WORDS[word]) {
      return { type: 'navigate', panel: PANEL_WORDS[word], reply: `Opening ${word} interface.` }
    }
    const target = LAUNCH_TARGETS.find((t) => word.includes(t)) || word
    return { type: 'launch', target, reply: `Launching ${target}.` }
  }

  // Locate / show place on map — requires an EXPLICIT locate verb.
  const locateMatch = input.match(
    /\b(?:locate|find|show me|show|go to|fly to|navigate to|take me to|where is|zoom (?:in )?(?:on|to))\s+(.+)/,
  )
  if (locateMatch) {
    const query = clean(locateMatch[1].replace(/^(the|a)\s+/, ''))
    if (query) {
      return { type: 'locate', query, reply: `Acquiring satellite lock on ${query}.` }
    }
  }

  // Panel navigation
  for (const [word, panel] of Object.entries(PANEL_WORDS)) {
    const re = new RegExp(`\\b${word}\\b`)
    if (re.test(input)) {
      return { type: 'navigate', panel, reply: `Opening the ${panel} interface.` }
    }
  }

  // If it's a question we don't understand locally, DON'T guess a locate —
  // the caller sends it to the real backend for an AI-generated answer and
  // only falls back to this reply if that call fails.
  if (/^(what|why|how|when|who|is|are|do|does|can|could|should|will|would)\b/.test(input)) {
    return {
      type: 'unknown',
      reply:
        "That's outside my current toolkit, sir. Try 'locate Tokyo', 'open the dashboard', or 'system status'.",
    }
  }

  return {
    type: 'unknown',
    reply:
      "I didn't catch a recognised command. Try 'locate Tokyo', 'open agents', or 'system status'.",
  }
}
