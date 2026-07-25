import { NextResponse } from 'next/server'
import { listSlashCommands } from '@/lib/nancy/docs-client'

export const runtime = 'nodejs'

function readMarkdown(path: string) {
  try {
    const fs = require('fs')
    const content = fs.readFileSync(path, 'utf8')
    return { content, error: null as null | string }
  } catch (e: any) {
    return { content: '', error: e?.message || 'read failed' }
  }
}

export async function GET() {
  const commands = listSlashCommands()
  const mdPath = require('path').join(process.cwd(), '..', 'docs', 'commands.md')
  const md = readMarkdown(mdPath)
  return NextResponse.json({
    success: true,
    data: {
      commands,
      markdown: md.content,
      markdown_error: md.error || null,
    },
  })
}
