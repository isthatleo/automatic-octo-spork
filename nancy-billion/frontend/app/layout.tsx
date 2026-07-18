import { Analytics } from '@vercel/analytics/next'
import type { Metadata, Viewport } from 'next'
import { Chakra_Petch, Space_Grotesk, JetBrains_Mono, Orbitron } from 'next/font/google'
import './globals.css'

// Chakra Petch → JARVIS-style sharp technical display face for headings & HUD.
const chakraPetch = Chakra_Petch({
  variable: '--font-heading',
  subsets: ['latin'],
  weight: ['300', '400', '500', '600', '700'],
  display: 'swap',
})
// Space Grotesk → refined, modern, distinctive body face.
const spaceGrotesk = Space_Grotesk({
  variable: '--font-sans',
  subsets: ['latin'],
  weight: ['300', '400', '500', '600', '700'],
  display: 'swap',
})
const jetbrainsMono = JetBrains_Mono({
  variable: '--font-mono',
  subsets: ['latin'],
  display: 'swap',
})
// Orbitron → reserved for hero moments only (reactor readout, the orb's own
// name plate, the biggest number on a panel) so it reads as a deliberate
// accent rather than the everyday typeface.
const orbitron = Orbitron({
  variable: '--font-display',
  subsets: ['latin'],
  weight: ['500', '700', '900'],
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'NÅNCY // Stark-class Interface',
  description:
    'NÅNCY — a Jarvis-class voice-first assistant with holographic recon, satellite intelligence, and an autonomous agent core.',
}

export const viewport: Viewport = {
  colorScheme: 'dark',
  themeColor: '#05080d',
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
      className={`dark ${chakraPetch.variable} ${spaceGrotesk.variable} ${jetbrainsMono.variable} ${orbitron.variable}`}
    >
      <body className="bg-background font-sans antialiased">
        {children}
        {process.env.NODE_ENV === 'production' && <Analytics />}
      </body>
    </html>
  )
}
