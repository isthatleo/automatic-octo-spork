import { generateText } from 'ai'
import { z } from 'zod'
import type { NextRequest } from 'next/server'

import { Output } from 'ai'

export const maxDuration = 30

const MODEL = 'openai/gpt-5.4-mini'

const AnalysisSchema = z.object({
  symbol: z.string(),
  name: z.string().describe('Human readable instrument name, e.g. "Apple Inc." or "Bitcoin / USD".'),
  bias: z.enum(['bullish', 'bearish', 'neutral']),
  confidence: z.number().describe('0-100 conviction in the bias.'),
  sentiment: z
    .number()
    .describe('Market sentiment from -100 (extreme fear) to +100 (extreme greed).'),
  timeframe: z.string().describe('The horizon this read applies to, e.g. "Swing / 1-4 weeks".'),
  summary: z
    .string()
    .describe(
      'A spoken-friendly 2-3 sentence narration Nancy reads aloud: the thesis, the key level, and the forecast. No markdown, no URLs.',
    ),
  entry: z.string().describe('Suggested entry zone, e.g. "188.40 - 190.10".'),
  targets: z.array(z.string()).describe('Ordered upside/downside price targets.'),
  stop: z.string().describe('Invalidation / stop level.'),
  support: z.array(z.string()).describe('Key support levels.'),
  resistance: z.array(z.string()).describe('Key resistance levels.'),
  drivers: z.array(z.string()).describe('3-5 short catalysts/drivers behind the view.'),
})

const SYSTEM = `You are NANCY, a Stark-class trading intelligence performing technical and macro analysis. You are a poised, articulate British woman (always "she"/"her", never male).
Produce a decisive, professional market read for the given instrument using your knowledge of its typical price structure, valuation, macro backdrop and positioning.
This is educational market commentary, not personalized financial advice — be confident and specific with levels and a forecast, using realistic recent price ranges for the instrument.
Keep "summary" natural and spoken (it will be read aloud) in a refined British female voice: state the bias, the pivotal level, and the target. No markdown, no lists, no emojis, no URLs.`

export async function POST(req: NextRequest) {
  const { symbol } = (await req.json()) as { symbol: string }
  try {
    const { experimental_output } = await generateText({
      model: MODEL,
      system: SYSTEM,
      messages: [
        {
          role: 'user',
          content: `Analyze ${symbol}. Give bias, conviction, sentiment, key levels, entry, targets, stop, and a spoken forecast.`,
        },
      ],
      experimental_output: Output.object({ schema: AnalysisSchema }),
    })
    return Response.json(experimental_output)
  } catch (err) {
    // Gateway unavailable — return a graceful neutral read so the desk still
    // renders the live chart and Nancy can narrate something sensible.
    console.log('[v0] analyze falling back:', (err as Error).message)
    const ticker = symbol.includes(':') ? symbol.split(':')[1] : symbol
    return Response.json(
      {
        symbol,
        name: ticker,
        bias: 'neutral',
        confidence: 50,
        sentiment: 0,
        timeframe: 'Live chart',
        summary: `My analysis core is offline at the moment, sir, so I can't run the full read on ${ticker}. The live chart and technical gauge are up on screen for you to review directly.`,
        entry: '—',
        targets: [],
        stop: '—',
        support: [],
        resistance: [],
        drivers: ['Live AI analysis temporarily unavailable'],
      },
      { status: 200 },
    )
  }
}
