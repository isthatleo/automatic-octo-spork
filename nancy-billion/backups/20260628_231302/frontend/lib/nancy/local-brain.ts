import type { NancyDecision } from './nancy-client'

/**
 * A fully local, rule-based fallback for Nancy's brain.
 *
 * This runs whenever the AI Gateway is unreachable (e.g. no credit card on
 * file, network blip, rate limit). It keeps the core experience working —
 * locating places, opening news/markets/knowledge, navigating panels — so the
 * interface never goes dead just because the LLM is unavailable.
 *
 * The output shape is identical to the AI brain's NancyDecision, so the page
 * can consume it without caring where the decision came from.
 */

function clean(s: string): string {
  return s
    .replace(/[.?!,]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

const PANEL_WORDS: Record<string, NonNullable<NancyDecision['panel']>> = {
  dashboard: 'overview',
  overview: 'overview',
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

const KNOWLEDGE_CATEGORIES: Record<string, NonNullable<NancyDecision['category']>> = {
  finance: 'finance',
  markets: 'finance',
  economy: 'finance',
  medicine: 'medicine',
  medical: 'medicine',
  health: 'medicine',
  science: 'science',
  physics: 'physics',
  astrophysics: 'astrophysics',
  astronomy: 'astrophysics',
  space: 'astrophysics',
  cosmology: 'astrophysics',
  history: 'history',
  historical: 'history',
  literature: 'literature',
  books: 'literature',
  novels: 'literature',
}

/** Common spoken instrument names → TradingView EXCHANGE:TICKER symbols. */
const SYMBOL_MAP: Record<string, string> = {
  bitcoin: 'BINANCE:BTCUSDT',
  btc: 'BINANCE:BTCUSDT',
  ethereum: 'BINANCE:ETHUSDT',
  eth: 'BINANCE:ETHUSDT',
  solana: 'BINANCE:SOLUSDT',
  apple: 'NASDAQ:AAPL',
  microsoft: 'NASDAQ:MSFT',
  nvidia: 'NASDAQ:NVDA',
  tesla: 'NASDAQ:TSLA',
  amazon: 'NASDAQ:AMZN',
  google: 'NASDAQ:GOOGL',
  alphabet: 'NASDAQ:GOOGL',
  meta: 'NASDAQ:META',
  facebook: 'NASDAQ:META',
  netflix: 'NASDAQ:NFLX',
  amd: 'NASDAQ:AMD',
  gold: 'TVC:GOLD',
  silver: 'TVC:SILVER',
  oil: 'TVC:USOIL',
  's&p': 'SP:SPX',
  'sp500': 'SP:SPX',
  'sp 500': 'SP:SPX',
  nasdaq: 'NASDAQ:IXIC',
  dow: 'DJ:DJI',
  eurusd: 'FX:EURUSD',
  euro: 'FX:EURUSD',
  gbpusd: 'FX:GBPUSD',
}

/** Project-related keywords -> action */
const PROJECT_KEYS = [
  'project',
  'projects',
  'workspace',
  'repo',
  'repos',
]

function base(reply: string, action: NancyDecision['action']): NancyDecision {
  return {
    reply,
    action,
    category: null,
    topic: null,
    symbol: null,
    panel: null,
    target: null,
    media: 'articles',
    autoOpenTop: false,
  }
}

function guessSymbol(raw: string): string {
  const lower = raw.toLowerCase()
  for (const [name, sym] of Object.entries(SYMBOL_MAP)) {
    if (lower.includes(name)) return sym
  }
  // A bare ticker like "AAPL" → leave it; TradingView resolves bare tickers.
  const ticker = raw.trim().replace(/[^a-z0-9:]/gi, '').toUpperCase()
  return ticker || 'NASDAQ:AAPL'
}

export function localBrain(rawInput: string): NancyDecision {
  const input = clean(rawInput.toLowerCase())
  if (!input) return base('Standing by.', 'none')

  // Close / dismiss
  if (
    /\b(close|dismiss|hide|clear it|clear that|put (it|that) away|that'?s all|that will be all|nothing else|never ?mind|go back|stand down|done)\b/.test(
      input,
    )
  ) {
    return base('Of course. Closing that down and standing by.', 'close')
  }

  // Greetings / smalltalk
  if (/\b(hello|hi|hey|good (morning|evening|afternoon)|how are you|thanks|thank you)\b/.test(input)) {
    return base("I'm right here and listening. How can I help?", 'none')
  }

  // Project intents
  const projectMatch = input.match(
    /\b(start\s+a\s+new\s+project|new\s+project|create\s+a\s+project|make\s+a\s+project)\b(?:\s+(?:called|named|with\s+name\s+)?([^\s,]+))?/
  )
  if (projectMatch) {
    const name = projectMatch[2] ? clean(projectMatch[2]) : 'new-project'
    return {
      ...base(
        `Creating a new project called ${name}.`,
        'launch', // reuse launch action but target will be handled in page
      ),
      target: name, // temporary; page will call /projects/new
    }
  }

  // List projects intent
  const listProjectsMatch = input.match(
    /\b(list\s+projects|show\s+projects|open\s+projects|what\s+projects|projects\s+list)\b/
  )
  if (listProjectsMatch) {
    return {
      ...base(`Listing your projects.`, 'launch'),
      target: '__list_projects__', // sentinel for page
    }
  }

  // Open specific project by name (if user said "open the X project")
  const openProjectMatch = input.match(
    /\b(open|launch|show)\s+(?:the\s+)?([a-zA-Z0-9_\-]+(?:\s+project)?)\b/
  )
  if (openProjectMatch) {
    const cand = clean(openProjectMatch[2].replace(/\s+project\s*/i, ''))
    if (cand && PROJECT_KEYS.some(k => cand.includes(k)) === false) {
      return {
        ...base(`Opening the ${cand} project.`, 'launch'),
        target: cand,
      }
    }
  }

  // Market / trading — a ticker, "analyze", or a known instrument name.
  const marketMatch = input.match(
    /\b(analyze|analyse|chart|price|forecast|sentiment|target|trade|trading|ticker|stock|crypto|forex)\b(?:\s+(?:of|on|for)?\s*(.+))?/, 
  )
  const namedInstrument = Object.keys(SYMBOL_MAP).find((n) => input.includes(n))
  if (marketMatch || namedInstrument) {
    const subject = marketMatch?.[2] ? clean(marketMatch[2]) : namedInstrument || input
    const symbol = guessSymbol(subject)
    return {
      ...base(`Pulling up the desk on ${subject}. Reading the tape now.`, 'market'),
      symbol,
    }
  }

  // News / headlines
  const newsMatch = input.match(
    /\b(?:the\s+)?(?:latest\s+)?(?:news|headlines|current events|world events|what'?s\s+happening|what is happening|briefing)\b(?:\s+(?:on|about|regarding|in|for|from)\s+(.+))?/
  )
  if (newsMatch) {
    const topic = newsMatch[1] ? clean(newsMatch[1].replace(/^(the|a)\s+/, '')) : null
    // If user is a trader and didn't specify a topic, assume finance.
    const autoOpenTop = /\b(open|read|play|show)\b.*\b(top|latest|first)\b/.test(input)
    // None -> let API use Google News search w/ topic, else fallback to trusted outlets
    const category = topic ? null : 'finance'
    return {
      ...base(
        topic
          ? `Pulling the latest verified reporting on ${topic}.`
          : 'Compiling the top financial stories from trusted sources for you.',
        'news',
      ),
      topic,
      category,
      autoOpenTop,
    }
  }

  // Knowledge domain
  for (const [word, category] of Object.entries(KNOWLEDGE_CATEGORIES)) {
    if (new RegExp(`\\b${word}\\b`).test(input)) {
      const topicMatch = input.match(/\b(?:on|about|regarding)\s+(.+)/)
      return {
        ...base(`Opening the ${category} library for you now.`, 'knowledge'),
        category,
        topic: topicMatch ? clean(topicMatch[1]) : null,
      }
    }
  }

  // Locate / show place on map
  const locateMatch = input.match(
    /\b(?:locate|find|show me|show|go to|fly to|navigate to|take me to|where is|map(?:\s+of)?|satellite(?:\s+of)?|zoom (?:in )?(?:on|to))\s+(.+)/, 
  )
  if (locateMatch) {
    const query = clean(locateMatch[1].replace(/^(the|a)\s+/, ''))
    if (query) {
      return { ...base(`Acquiring a satellite lock on ${query}.`, 'locate'), topic: query }
    }
  }

  // Launch / open an application
  const launchMatch = input.match(/\b(open|launch|run|start|execute)\s+(?:the\s+)?(\w+)/)
  if (launchMatch) {
    const word = launchMatch[2]
    if (PANEL_WORDS[word]) {
      return { ...base(`Opening the ${word} interface.`, 'navigate'), panel: PANEL_WORDS[word] }
    }
    const target = LAUNCH_TARGETS.find((t) => word.includes(t)) || word
    return { ...base(`Launching ${target}.`, 'launch'), target }
  }

  // Panel navigation by keyword
  for (const [word, panel] of Object.entries(PANEL_WORDS)) {
    if (new RegExp(`\\b${word}\\b`).test(input)) {
      return { ...base(`Opening the ${word} interface.`, 'navigate'), panel }
    }
  }

  // A short, place-like phrase → treat as a locate request.
  if (input.split(' ').length <= 4 && /^[a-z\s,'-]+$/.test(input)) {
    return { ...base(`Searching for ${input}.`, 'locate'), topic: input }
  }

  return base(
    "I'm running on my local core at the moment, so I'll keep it simple. Try \"locate Tokyo\", \"open the latest news\", \"open projects\", or \"start a new project\".",
    'none',
  )
}