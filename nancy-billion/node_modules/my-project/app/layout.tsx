import { Analytics } from '@vercel/analytics/next'
import type { Metadata, Viewport } from 'next'
import { Geist, Geist_Mono, Instrument_Serif } from 'next/font/google'
import './globals.css'

// Geist → the everyday face. Clean, humanist, confident without shouting —
// this is the whole UI's actual voice, not a decorative sci-fi label font.
const geist = Geist({
  variable: '--font-sans',
  subsets: ['latin'],
  display: 'swap',
})
// Geist Mono → data, telemetry, code. Legible at small sizes, no gimmicks.
const geistMono = Geist_Mono({
  variable: '--font-mono',
  subsets: ['latin'],
  display: 'swap',
})
// Instrument Serif Italic → reserved for real hero moments only (the
// wordmark, one big number per screen). A single deliberate, warm,
// editorial accent instead of tracked-out all-caps sci-fi everywhere.
const instrumentSerif = Instrument_Serif({
  variable: '--font-display',
  subsets: ['latin'],
  weight: '400',
  style: 'italic',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'Nancy — Control',
  description: 'A calm, precise control surface for Nancy — voice, agents, and everything she runs.',
}

export const viewport: Viewport = {
  colorScheme: 'dark',
  themeColor: '#131211',
  userScalable: false,
  width: 'device-width',
  initialScale: 1,
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html
      lang="en"
      className={`dark ${geist.variable} ${geistMono.variable} ${instrumentSerif.variable}`}
    >
      <body className="bg-background font-sans antialiased">
        {children}
        {process.env.NODE_ENV === 'production' && <Analytics />}
      </body>
    </html>
  )
}
