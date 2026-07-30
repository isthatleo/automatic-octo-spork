import type { MetadataRoute } from 'next'

// PWA manifest -- makes the Billion control room INSTALLABLE as an app on
// every platform from the browser itself: Android (Chrome → "Add to Home
// screen" / install prompt), iOS (Safari → Share → "Add to Home Screen"),
// and Windows/macOS/Linux (Chrome/Edge → "Install Billion"). Installed, it
// runs in its own standalone window with the reactor icon -- no browser
// chrome, straight into the voice-first hero.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'Billion — Sovereign AI OS',
    short_name: 'Billion',
    description: 'JARVIS-style personal AI operating system: voice-first control room, real agents, real tools, real memory.',
    start_url: '/',
    display: 'standalone',
    orientation: 'any',
    background_color: '#05080e',
    theme_color: '#05080e',
    icons: [
      { src: '/icons/billion-192.png', sizes: '192x192', type: 'image/png' },
      { src: '/icons/billion-512.png', sizes: '512x512', type: 'image/png' },
      { src: '/icons/billion-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
    ],
  }
}
