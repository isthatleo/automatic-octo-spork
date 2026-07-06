import { generateText } from 'ai'
import { z } from 'zod'
import { localBrain } from '@/lib/nancy/local-brain'

export const maxDuration = 30

const MODEL = 'openai/gpt-5.4-mini' as any

const ActionSchema = z.object({
  reply: z.string(),
  action: z.enum([
    'none',
    'knowledge',
    'news',
    'market',
    'locate',
    'navigate',
    'launch',
    'close',
  ]),
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
    .nullable(),
  topic: z.string().nullable(),
  symbol: z.string().nullable(),
  panel: z.enum(['overview', 'map', 'core', 'agents', 'system']).nullable(),
  target: z.string().nullable(),
  media: z.enum(['articles', 'videos']).nullable(),
  autoOpenTop: z.boolean(),
})

const SYSTEM = `You are NANCY — a Stark-class artificial intelligence modeled on JARVIS from Iron Man, but reimagined as a woman.
You serve a single operator: a professional trader.
You must reply with ONLY valid JSON, no markdown, no URLs.`

export async function POST(req: Request) {
  let text = ''
  try {
    const body = (await req.json()) as {
      text: string
      history?: { role: 'user' | 'assistant'; content: string }[]
    }
    text = body.text
    const recent = (body.history ?? []).slice(-6)

    const prompt = `Return ONLY JSON matching this schema: ${JSON.stringify(
      ActionSchema.shape,
    )}. Use the fields to describe the single action and what to say out loud.`

    const result = await generateText({
      model: MODEL,
      system: SYSTEM,
      messages: [
        ...recent.map((m) => ({ role: m.role, content: m.content })),
        { role: 'user' as const, content: `${text}\n\n${prompt}` },
      ],
    })

    return Response.json({ raw: result.text ?? result })
  } catch (err) {
    console.log('[v0] nancy brain falling back to local core:', (err as Error).message)
    return Response.json(localBrain(text), { status: 200 })
  }
}

