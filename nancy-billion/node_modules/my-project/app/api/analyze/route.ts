import { generateText } from 'ai'
import { z } from 'zod'
import type { NextRequest } from 'next/server'

export const maxDuration = 30

const MODEL = 'openai/gpt-5.4-mini' as any


// Kept for documentation of the intended output shape.
// Current build setup may not support structured Output exports.
const AnalysisSchema = z.object({
  symbol: z.string(),
  name: z.string(),
  bias: z.enum(['bullish', 'bearish', 'neutral']),
  confidence: z.number(),
  sentiment: z.number(),
  timeframe: z.string(),
  summary: z.string(),
  entry: z.string(),
  targets: z.array(z.string()),
  stop: z.string(),
  support: z.array(z.string()),
  resistance: z.array(z.string()),
  drivers: z.array(z.string()),
})

const SYSTEM = `You are NANCY, a Stark-class trading intelligence performing technical and macro analysis.
You are a poised, articulate British woman (always "she"/"her", never male).
Produce a decisive, professional market read for the given instrument.
This is educational market commentary, not personalized financial advice.
Return ONLY valid JSON, no markdown, no URLs.`

export async function POST(req: NextRequest) {
  const { symbol } = (await req.json()) as { symbol: string }

  try {
    const prompt = `Analyze ${symbol}. Return ONLY JSON matching this schema: ${JSON.stringify(
      AnalysisSchema.shape,
    )}.`

    const result = await generateText({
      model: MODEL,
      system: SYSTEM,
      messages: [{ role: 'user', content: prompt }],
    })

    return Response.json({
      symbol,
      raw: result.text ?? result,
    })
  } catch (err) {
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

