/** Shared "X ago" formatter -- accepts either a unix-ms timestamp (kanban
 *  cards' `at`/`updatedAt` fields) or an ISO date string (news items'
 *  `published` field), so every panel formats elapsed time identically
 *  instead of each hand-rolling its own copy. */
export function timeAgo(input?: string | number): string {
  if (input === undefined || input === null) return ''
  const t = typeof input === 'number' ? input : Date.parse(input)
  if (Number.isNaN(t)) return ''
  const m = Math.round((Date.now() - t) / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.round(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.round(h / 24)}d ago`
}
