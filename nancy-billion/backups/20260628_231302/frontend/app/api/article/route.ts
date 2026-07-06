import type { NextRequest } from 'next/server'

export const revalidate = 600

function meta(html: string, prop: string): string | null {
  const patterns = [
    new RegExp(`<meta[^>]+property=["']${prop}["'][^>]+content=["']([^"']+)["']`, 'i'),
    new RegExp(`<meta[^>]+content=["']([^"']+)["'][^>]+property=["']${prop}["']`, 'i'),
    new RegExp(`<meta[^>]+name=["']${prop}["'][^>]+content=["']([^"']+)["']`, 'i'),
  ]
  for (const re of patterns) {
    const m = html.match(re)
    if (m?.[1]) return m[1]
  }
  return null
}

function decode(s: string): string {
  return s
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#0?39;|&apos;|&#x27;/g, "'")
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/\s+/g, ' ')
    .trim()
}

/**
 * Resolves a (possibly Google-News-redirect) article URL to the publisher page
 * and extracts a hero image, description and title for Nancy's immersive
 * readout. Always returns 200 with best-effort fields.
 */
export async function GET(req: NextRequest) {
  const target = req.nextUrl.searchParams.get('url')
  if (!target) return Response.json({})
  try {
    const res = await fetch(target, {
      headers: {
        'User-Agent':
          'Mozilla/5.0 (compatible; NancyOS/1.0; +https://vercel.com) AppleWebKit/537.36',
      },
      redirect: 'follow',
      next: { revalidate },
    })
    const finalUrl = res.url || target
    const html = (await res.text()).slice(0, 400_000)

    const image = meta(html, 'og:image') || meta(html, 'twitter:image')
    const description =
      meta(html, 'og:description') ||
      meta(html, 'twitter:description') ||
      meta(html, 'description')
    const title = meta(html, 'og:title') || meta(html, 'twitter:title')
    const site = meta(html, 'og:site_name')

    return Response.json({
      url: finalUrl,
      image: image || null,
      title: title ? decode(title) : null,
      description: description ? decode(description) : null,
      site: site ? decode(site) : null,
    })
  } catch (err) {
    console.log('[v0] article enrich error:', (err as Error).message)
    return Response.json({})
  }
}
