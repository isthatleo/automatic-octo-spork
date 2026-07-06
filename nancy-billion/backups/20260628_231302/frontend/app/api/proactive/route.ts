import { NextResponse } from 'next/server'
import { proactiveAssistant } from '@/lib/nancy/proactive-assistant'

export async function GET() {
  try {
    const suggestions = proactiveAssistant.getActiveSuggestions(10)
    return NextResponse.json({ suggestions })
  } catch (error) {
    console.error('Error fetching proactive suggestions:', error)
    return NextResponse.json({ error: 'Failed to fetch suggestions' }, { status: 500 })
  }
}

export async function POST(request: Request) {
  try {
    const { suggestionId } = await request.json()
    if (!suggestionId) {
      return NextResponse.json({ error: 'Missing suggestionId' }, { status: 400 })
    }
    
    const result = proactiveAssistant.acceptSuggestion(suggestionId)
    if (!result) {
      return NextResponse.json({ error: 'Suggestion not found or already processed' }, { status: 404 })
    }
    
    return NextResponse.json({ success: true, action: result })
  } catch (error) {
    console.error('Error accepting proactive suggestion:', error)
    return NextResponse.json({ error: 'Failed to accept suggestion' }, { status: 500 })
  }
}

export async function DELETE(request: Request) {
  try {
    const { searchParams } = new URL(request.url)
    const suggestionId = searchParams.get('id')
    
    if (!suggestionId) {
      return NextResponse.json({ error: 'Missing suggestion id' }, { status: 400 })
    }
    
    proactiveAssistant.dismissSuggestion(suggestionId)
    return NextResponse.json({ success: true })
  } catch (error) {
    console.error('Error dismissing proactive suggestion:', error)
    return NextResponse.json({ error: 'Failed to dismiss suggestion' }, { status: 500 })
  }
}