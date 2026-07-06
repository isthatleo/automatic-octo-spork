import { Analytics } from '@vercel/analytics/next'
import type { Metadata, Viewport } from 'next'
import { Orbitron, Geist_Mono } from 'next/font/google'
import './globals.css'

const orbitron = Orbitron({
  variable: '--font-orbitron',
  subsets: ['latin'],
})
const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
})

export const metadata: Metadata = {
  title: 'NÅNCY // Stark-class Interface',
  description:
    'NÅNCY — a Jarvis-class holographic command interface with voice control, satellite intelligence, and an autonomous agent core.',
  generator: 'v0.app',
}

export const viewport: Viewport = {
  colorScheme: 'dark',
  themeColor: '#05080d',
  userScalable: false,
  width: 'device-width',
  initialScale: 1,
}

import { HudOverlay } from '@/components/hud/hud-overlay'
import { ProactiveSuggestions } from '@/components/hud/proactive-suggestions'

export const metadata: Metadata = {
  title: 'JÄRVIS — Advanced AI Assistant',
  description:
    'JÄRVIS — an advanced AI assistant with proactive intelligence, holographic interface, and autonomous capabilities.',
  generator: 'v0.app',
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
      className={`dark ${orbitron.variable} ${geistMono.variable}`}
    >
      <body className="bg-background font-mono antialiased">
        {children}
        <HudOverlay className="fixed inset-0 pointer-events-none z-40" />
        <ProactiveSuggestions className="fixed inset-0 pointer-auto z-50" />
        {process.env.NODE_ENV === 'production' && <Analytics />}
      </body>
    </html>
  )
}
