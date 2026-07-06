'use client'

import { useEffect, useRef, useState } from 'react'
import { useVoice, speak } from '@/lib/nancy/use-voice'

interface EmotiveVoiceSynthProps {
  /** Whether emotive voice synthesis is active */
  active?: boolean
  /** Default emotional state */
  defaultEmotion?: 'neutral' | 'happy' | 'serious' | 'concerned' | 'excited' | 'calm'
  /** Callback when speech starts */
  onSpeechStart?: () => void
  /** Callback when speech ends */
  onSpeechEnd?: () => void
  /** Text to speak with emotion */
  textToSpeak?: string
  /** Trigger speech manually */
  triggerSpeech?: boolean
}

export function EmotiveVoiceSynth({
  active = true,
  defaultEmotion = 'neutral',
  onSpeechStart,
  onSpeechEnd,
  textToSpeak,
  triggerSpeech = false
}: EmotiveVoiceSynthProps) {
  const { isReady, isSpeaking: voiceIsSpeaking } = useVoice()
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [currentEmotion, setCurrentEmotion] = useState<'neutral' | 'happy' | 'serious' | 'concerned' | 'excited' | 'calm'>(defaultEmotion)
  const speechRef = useRef<number | null>(null)
  
  // Update speaking state from voice hook
  useEffect(() => {
    setIsSpeaking(voiceIsSpeaking)
  }, [voiceIsSpeaking])
  
  // Handle text to speak
  useEffect(() => {
    if (!isReady || !active || !textToSpeak || textToSpeak.trim() === '') return
    
    if (triggerSpeech) {
      speakWithEmotion(textToSpeak, currentEmotion)
    }
  }, [isReady, active, textToSpeak, triggerSpeech, currentEmotion])
  
  // Speak text with emotional modulation
  const speakWithEmotion = async (text: string, emotion: 'neutral' | 'happy' | 'serious' | 'concerned' | 'excited' | 'calm') => {
    if (!isReady || !active) return
    
    setCurrentEmotion(emotion)
    setIsSpeaking(true)
    onSpeechStart?.()
    
    try {
      // In a real implementation, we'd modify the voice parameters based on emotion
      // For this prototype, we'll use the existing speak function and add visual feedback
      
      // Speak the text
      speak(text)
      
      // Set up auto-stop detection
      const checkSpeechEnd = () => {
        if (!voiceIsSpeaking && isSpeaking) {
          setIsSpeaking(false)
          onSpeechEnd?.()
          if (speechRef.current !== null) {
            clearTimeout(speechRef.current)
            speechRef.current = null
          }
        } else if (isSpeaking) {
          speechRef.current = setTimeout(checkSpeechEnd, 100)
        }
      }
      
      speechRef.current = setTimeout(checkSpeechEnd, 500) // Start checking after 500ms
    } catch (error) {
      console.error('Emotive voice synthesis error:', error)
      setIsSpeaking(false)
      onSpeechEnd?.()
    }
  }
  
  // Manual speech trigger
  const handleSpeechClick = () => {
    if (textToSpeak && textToSpeak.trim() !== '') {
      speakWithEmotion(textToSpeak, currentEmotion)
    }
  }
  
  // Get emotional voice parameters (for visualization)
  const getEmotionParams = (emotion: 'neutral' | 'happy' | 'serious' | 'concerned' | 'excited' | 'calm') => {
    const emotionMap: Record<'neutral' | 'happy' | 'serious' | 'concerned' | 'excited' | 'calm', {
      color: string
      intensity: number
      wavePattern: 'smooth' | 'ripple' | 'pulse' | 'wave' | 'burst' | 'glow'
      pulseSpeed: number
    }> = {
      neutral: { color: '#38d3eb', intensity: 0.6, wavePattern: 'smooth', pulseSpeed: 1 },
      happy: { color: '#fbbf24', intensity: 0.8, wavePattern: 'burst', pulseSpeed: 1.5 },
      serious: { color: '#64748b', intensity: 0.5, wavePattern: 'pulse', pulseSpeed: 0.7 },
      concerned: { color: '#f87171', intensity: 0.7, wavePattern: 'ripple', pulseSpeed: 1.2 },
      excited: { color: '#f97316', intensity: 0.9, wavePattern: 'wave', pulseSpeed: 2 },
      calm: { color: '#10b981', intensity: 0.4, wavePattern: 'glow', pulseSpeed: 0.5 }
    }
    
    return emotionMap[emotion] || emotionMap.neutral
  }
  
  const emotionParams = getEmotionParams(currentEmotion)
  
  // Visual representation of emotive voice
  return (
    <div className="relative w-[180px] h-[180px]">
      {/* Emotional state indicator */}
      <div className="absolute inset-0 rounded-full 
                        bg-black/40 
                        ${isSpeaking ? `animate-[pulse_2s_ease_in_out_infinite]` : ''}
                        border-2 
                        border-[${emotionParams.color}]/${isSpeaking ? '60' : '30'}"
           style={{
             boxShadow: isSpeaking 
               ? `0 0 20px ${emotionParams.color}80, inset 0 0 10px ${emotionParams.color}40`
               : '0 0 10px transparent'
           }}>
        {/* Emotional waveform visualization */}
        <div className="absolute inset-0 pointer-events-none" 
             style={{
               background: `radial-gradient(
                 circle at center, 
                 transparent 0%, 
                 ${emotionParams.color}20 30%, 
                 transparent 70%
               )`,
               opacity: isSpeaking ? 0.4 : 0.2,
               transform: `scale(${isSpeaking ? 1.1 : 1})`,
               transition: 'transform 0.3s ease',
               animation: 
                 emotionParams.wavePattern === 'smooth' ? 'animate-[breathing_3s_ease_in_out_infinite]' :
                 emotionParams.wavePattern === 'ripple' ? 'animate-[ripple_2s_ease_in_out_infinite]' :
                 emotionParams.wavePattern === 'pulse' ? 'animate-[pulse_1_5s_ease_in_out_infinite]' :
                 emotionParams.wavePattern === 'wave' ? 'animate-[wave_2s_ease_in_out_infinite]' :
                 emotionParams.wavePattern === 'burst' ? 'animate-[burst_1s_ease_in_out_infinite]' :
                 emotionParams.wavePattern === 'glow' ? 'animate-[glow_2_5s_ease_in_out_infinite]' :
                 'none'
             }}></div>
        
        {/* Emotion label */}
        <div className="absolute bottom-2 left-1/2 -translate-x-1/2 
                        text-center text-xs font-medium 
                        ${isSpeaking ? `text-${emotionParams.color}-400` : 'text-gray-400'}"
           style={{
             textShadow: isSpeaking 
               ? `0 0 4px ${emotionParams.color}80`
               : 'none'
           }}>
            {currentEmotion.charAt(0).toUpperCase() + currentEmotion.slice(1)}
          </div>
        
        {/* Microphone icon when listening for emotional cues */}
        {!isSpeaking && (
          <div className="absolute top-2 left-1/2 -translate-x-1/2 
                        w-6 h-6 rounded-full bg-gray-700/60 
                        hover:bg-gray-600
                        flex items-center justify-center
                        text-xs text-gray-400 hover:text-white">
            🎤
          </div>
        )}
        
        {/* Stop button when speaking */}
        {isSpeaking && (
          <div className="absolute top-2 right-2 w-6 h-6 rounded-full 
                        bg-red-500/60 hover:bg-red-500
                        flex items-center justify-center
                        text-xs text-white"
           onClick={() => {
            setIsSpeaking(false)
            onSpeechEnd?.()
            if (speechRef.current !== null) {
              clearTimeout(speechRef.current)
              speechRef.current = null
            }
            // In a real implementation, we'd stop the speech here
           }}>
            ⏹
          </div>
        )}
      </div>
    </div>
  )
}

// CSS keyframes for emotive voice visualization
if (typeof window !== 'undefined' && !document.getElementById('jarvis-emotive-voice-styles')) {
  const style = document.createElement('style')
  style.id = 'jarvis-emotive-voice-styles'
  style.textContent = `
    @keyframes breathing {
      0%, 100% { transform: scale(1); }
      50% { transform: scale(1.05); }
    }
    
    @keyframes ripple {
      0% { transform: scale(0.8); opacity: 0; }
      100% { transform: scale(1.2); opacity: 0.5; }
    }
    
    @keyframes pulse {
      0%, 100% { transform: scale(1); }
      50% { transform: scale(1.1); }
    }
    
    @keyframes wave {
      0% { transform: translateX(-50%); }
      100% { transform: translateX(50%); }
    }
    
    @keyframes burst {
      0%, 100% { transform: scale(1); opacity: 0.3; }
      50% { transform: scale(1.5); opacity: 0.7; }
    }
    
    @keyframes glow {
      0%, 100% { box-shadow: 0 0 5px rgba(0,0,0,0); }
      50% { box-shadow: 0 0 20px rgba(16,185,129,0.5); }
    }
  `
  document.head.appendChild(style)
}