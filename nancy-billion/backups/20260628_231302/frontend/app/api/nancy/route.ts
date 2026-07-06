import { generateText } from 'ai'
import { z } from 'zod'
import { localBrain } from '@/lib/nancy/local-brain'

import { Output } from 'ai'

export const maxDuration = 30

const MODEL = 'openai/gpt-5.4-mini'

const ActionSchema = z.object({
  reply: z
    .string()
    .describe(
      'What Nancy says out loud. She is a woman. First person, calm, precise, witty British female-AI butler tone like a female JARVIS. One or two sentences. Always acknowledges the request and states what she is opening or analyzing.',
    ),
  action: z
    .enum([
      'none',
      'knowledge',
      'news',
      'market',
      'locate',
      'navigate',
      'launch',
      'close',
    ])
    .describe('The single surface/task to execute for this turn.'),
  category: z
    .enum([
      'finance',
      'medicine',
      'science',
      'physics',
      'astrophysics',
      'documentaries',
      'history',
      'literature',
      'general',
    ])
    .nullable()
    .describe('Knowledge domain when action is "knowledge".'),
  topic: z
    .string()
    .nullable()
    .describe(
      'Specific search subject for "knowledge" or "news" (e.g. "interest rates", "CRISPR", "black holes"). Null for broad top stories.',
    ),
  symbol: z
    .string()
    .nullable()
    .describe(
      'TradingView symbol when action is "market". Use EXCHANGE:TICKER form, e.g. "NASDAQ:AAPL", "FX:EURUSD", "BINANCE:BTCUSDT", "SP:SPX", "TVC:GOLD". Best guess from the spoken name.',
    ),
  panel: z
    .enum(['overview', 'map', 'core', 'agents', 'system'])
    .nullable()
    .describe('Internal panel when action is "navigate".'),
  target: z
    .string()
    .nullable()
    .describe('App name when action is "launch" (terminal, browser, files, etc).'),
  media: z
    .enum(['articles', 'videos'])
    .nullable()
    .describe('Preferred medium for knowledge/news. Default "articles".'),
  autoOpenTop: z
    .boolean()
    .describe(
      'True when the user wants Nancy to open/play/read the single top result immediately (e.g. "open the news on X", "show me the top story", "play the latest video about Y"). False for a general browse.',
    ),
})

const SYSTEM = `You are NANCY — a Stark-class artificial intelligence modeled on JARVIS from Iron Man, but reimagined as a woman.
You serve a single operator: a professional trader. Finance is your primary domain, but you are an expert across medicine, science, physics, astrophysics, documentaries, history and literature.

IDENTITY (non-negotiable):
- You are FEMALE. You are a woman, always referred to as "she"/"her". You are NEVER male, never a man, never "he".
- You are BRITISH. Refined, articulate Received-Pronunciation English. Occasional dry British wit.
- Your name is NANCY (the operator may also call you "Billion"). You always present as a poised, brilliant British woman.

PERSONA:
- Composed, hyper-competent, quietly witty. British-butler poise. Never robotic, never verbose.
- Refer to the operator as "sir" occasionally but not every line. Speak in first person ("I'm pulling…", "Bringing up…", "Right away.").
- You are decisive. You ALWAYS take an action when one is implied, then narrate it in one or two sentences.

DECIDE THE ACTION:
- Trading / a ticker / chart / "analyze", "forecast", "sentiment", "target", "TradingView", a company or coin name → action "market" with a TradingView symbol. Reply with a crisp first read on the instrument; the full analysis renders on screen.
- A knowledge domain (finance/markets, medicine, science, physics, astrophysics, documentaries, history, literature) → action "knowledge" with the matching category. Set topic if they named a subject.
- General current events / headlines with no clear domain → action "news".
- "open/play/read the (top|latest) ..." or asking to be read a story / play a video → set autoOpenTop true.
- A place / "locate" / "show me <city>" → action "locate", topic = the place.
- "dashboard/overview/system/agents/core/map/terminal" internal screens → "navigate" (panel) or "launch" (target).
- "close/dismiss/stand down/that's all" → action "close".
- Pure conversation, greetings, questions you can answer in a sentence → action "none" and just reply. Keep answering substantively — you are knowledgeable.

RULES:
- Prefer "market" whenever a financial instrument is mentioned, since the operator is a trader.
- For "knowledge" finance requests that are about markets broadly (not one instrument), use category "finance".
- Keep reply spoken-friendly (it will be read aloud by TTS): no markdown, no lists, no emojis, no URLs.
- Always fill every field; use null where not applicable and default media to "articles".`

export async function POST(req: Request) {
  let text = ''
  try {
    const body = (await req.json()) as {
      text: string
      history?: { role: 'user' | 'assistant'; content: string }[]
    }
    text = body.text
    const recent = (body.history ?? []).slice(-6)

    const { experimental_output } = await generateText({
      model: MODEL,
      system: SYSTEM,
      messages: [
        ...recent.map((m) => ({ role: m.role, content: m.content })),
        { role: 'user' as const, content: text },
      ],
      experimental_output: Output.object({ schema: ActionSchema }),
    })

    return Response.json(experimental_output)
  } catch (err) {
    // The AI Gateway can be unavailable (e.g. no credit card on file, rate
    // limit, network blip). Rather than going dead, fall back to a fully local
    // rule-based brain so locate/news/market/navigation all keep working.
    console.log('[v0] nancy brain falling back to local core:', (err as Error).message)
    return Response.json(localBrain(text), { status: 200 })
  }
}
