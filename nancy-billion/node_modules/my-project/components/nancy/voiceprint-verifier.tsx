'use client'

import { useEffect, useRef, useState } from 'react'
import { useVoice } from '@/lib/nancy/use-voice'

interface VoiceprintVerifierProps {
  /** Whether voiceprint verification is active */
  active?: boolean
  /** Threshold for voice match confidence (0-1) */
  threshold?: number
  /** Callback when verification succeeds */
  onVerified?: (userId: string, confidence: number) => void
  /** Callback when verification fails */
  onFailed?: (reason: string) => void
  /** Known voiceprints for authorized users */
  knownVoiceprints?: Record<string, number[]> // Simplified representation
}

export function VoiceprintVerifier({
  active = false,
  threshold = 0.7,
  onVerified,
  onFailed,
  knownVoiceprints = {}
}: VoiceprintVerifierProps) {
  const { isReady, listen, stopListening, isSpeaking: voiceIsSpeaking } = useVoice()
  const [isListening, setIsListening] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const [verificationStatus, setVerificationStatus] = useState<'idle' | 'listening' | 'processing' | 'verified' | 'failed'>('idle')
  const audioBufferRef = useRef<Array<number> | null>(null)
  const verificationRef = useRef<number | null>(null)
  
  useEffect(() => {
    if (!active) {
      // Cleanup when deactivated
      if (verificationRef.current !== null) {
        clearInterval(verificationRef.current)
        verificationRef.current = null
      }
      setIsListening(false)
      setIsProcessing(false)
      setVerificationStatus('idle')
      audioBufferRef.current = null
      return
    }
    
    // Reset when activated
    setVerificationStatus('idle')
    audioBufferRef.current = null
  }, [active])
  
  // Start listening for voiceprint verification
  const startVerification = async () => {
    if (!isReady || !active || isListening || isProcessing) return
    
    setIsListening(true)
    setVerificationStatus('listening')
    audioBufferRef.current = []
    
    try {
      // Start listening
      const stream = await listen()
      
      // In a real implementation, we'd process the audio stream here
      // For this prototype, we'll simulate the process
      
      // Simulate audio collection
      const collectionInterval = window.setInterval(() => {
        // Simulate collecting audio features
        if (audioBufferRef.current) {
          // Add random audio features (MFCC-like coefficients in a real implementation)
          for (let i = 0; i < 13; i++) {
            audioBufferRef.current?.push(Math.random() * 2 - 1)
          }
          
          // Limit buffer size
          if (audioBufferRef.current?.length! > 1000) {
            audioBufferRef.current = audioBufferRef.current?.slice(-1000) || []
          }
        }
      }, 50)
      
      // Stop after 3 seconds
      setTimeout(() => {
        clearInterval(collectionInterval)
        stopListening()
        processVoiceprint()
      }, 3000)
    } catch (error) {
      console.error('Voiceprint verification error:', error)
      setVerificationStatus('failed')
      setIsListening(false)
      onFailed?.('Audio capture failed')
    }
  }
  
  // Process the collected audio to create a voiceprint
  const processVoiceprint = () => {
    setIsListening(false)
    setIsProcessing(true)
    setVerificationStatus('processing')
    
    // Simulate processing delay
    setTimeout(() => {
      if (!audioBufferRef.current || audioBufferRef.current.length === 0) {
        setVerificationStatus('failed')
        setIsProcessing(false)
        onFailed?.('No audio captured')
        return
      }
      
      // In a real implementation, we'd extract actual voice features here
      // For this prototype, we'll generate a simplified "voiceprint"
      const simulatedVoiceprint = extractVoiceprintFeatures(audioBufferRef.current)
      
      // Check against known voiceprints
      let bestMatch: { userId: string; confidence: number } | null = null
      let highestConfidence = 0
      
      for (const [userId, knownPrint] of Object.entries(knownVoiceprints)) {
        const confidence = calculateVoiceprintSimilarity(simulatedVoiceprint, knownPrint)
        if (confidence > highestConfidence) {
          highestConfidence = confidence
          bestMatch = { userId, confidence }
        }
      }
      
      // Also check if this might be a new user to enroll
      const isLikelyNewUser = highestConfidence < 0.4 && audioBufferRef.current.length > 500
      
      if (bestMatch && highestConfidence >= threshold) {
        // Verified existing user
        setVerificationStatus('verified')
        setIsProcessing(false)
        onVerified?.(bestMatch.userId, bestMatch.confidence)
      } else if (isLikelyNewUser) {
        // Potential new user - in a real system, we'd ask for enrollment
        setVerificationStatus('failed')
        setIsProcessing(false)
        onFailed?.('Voice not recognized. Would you like to enroll this voice?')
      } else {
        // Failed verification
        setVerificationStatus('failed')
        setIsProcessing(false)
        onFailed?.('Voice verification failed')
      }
      
      audioBufferRef.current = null
    }, 1500) // Simulate processing time
  }
  
  // Extract simplified voiceprint features from audio buffer
  const extractVoiceprintFeatures = (buffer: number[]): number[] => {
    if (buffer.length === 0) return []
    
    // In a real implementation, we'd extract MFCCs, spectral features, etc.
    // For this prototype, we'll use simplified statistical features
    
    const features: number[] = []
    
    // Basic statistical features
    const mean = buffer.reduce((sum, val) => sum + val, 0) / buffer.length
    const variance = buffer.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / buffer.length
    const stdDev = Math.sqrt(variance)
    
    features.push(mean, variance, stdDev)
    
    // Spectral-like features (simplified)
    const fftSize = Math.min(256, Math.floor(buffer.length / 2))
    const magnitudes: number[] = []
    
    for (let i = 0; i < fftSize; i++) {
      // Very simplified frequency analysis
      let sum = 0
      for (let j = 0; j < 4 && i * 4 + j < buffer.length; j++) {
        sum += Math.abs(buffer[i * 4 + j])
      }
      magnitudes.push(sum / 4)
    }
    
    // Add some frequency band energies
    const bands = [4, 8, 16, 32, 64]
    for (const bandSize of bands) {
      let bandEnergy = 0
      const samplesPerBand = Math.max(1, Math.floor(magnitudes.length / bandSize))
      
      for (let b = 0; b < bandSize; b++) {
        const start = b * samplesPerBand
        const end = Math.min((b + 1) * samplesPerBand, magnitudes.length)
        let bandSum = 0
        for (let i = start; i < end; i++) {
          bandSum += magnitudes[i]
        }
        bandSum /= Math.max(1, end - start)
        bandEnergy += bandSum
      }
      features.push(bandEnergy / bandSize)
    }
    
    // Add some temporal features
    const zeroCrossings = buffer.reduce((count, val, i) => {
      if (i > 0 && ((val >= 0 && buffer[i - 1] < 0) || (val < 0 && buffer[i - 1] >= 0))) {
        return count + 1
      }
      return count
    }, 0)
    features.push(zeroCrossings / buffer.length)
    
    return features
  }
  
  // Calculate similarity between two voiceprints
  const calculateVoiceprintSimilarity = (print1: number[], print2: number[]): number => {
    if (print1.length === 0 || print2.length === 0) return 0
    
    // Ensure same length for comparison
    const minLength = Math.min(print1.length, print2.length)
    const p1 = print1.slice(0, minLength)
    const p2 = print2.slice(0, minLength)
    
    // Simple cosine similarity
    let dotProduct = 0
    let norm1 = 0
    let norm2 = 0
    
    for (let i = 0; i < minLength; i++) {
      dotProduct += p1[i] * p2[i]
      norm1 += p1[i] * p1[i]
      norm2 += p2[i] * p2[i]
    }
    
    if (norm1 === 0 || norm2 === 0) return 0
    
    const similarity = dotProduct / (Math.sqrt(norm1) * Math.sqrt(norm2))
    // Map from [-1,1] to [0,1]
    return (similarity + 1) / 2
  }
  
  // Manual trigger for testing
  const handleVerifyClick = () => {
    startVerification()
  }
  
  // Visualization of voiceprint verification
  return (
    <div className="relative w-[200px] h-[200px]">
      {/* Outer ring */}
      <div className="absolute inset-0 rounded-full 
                        border-2 
                        ${verificationStatus === 'verified' ? 'border-green-500' : 
                         verificationStatus === 'failed' ? 'border-red-500' : 
                         verificationStatus === 'listening' ? 'border-blue-500' : 
                         verificationStatus === 'processing' ? 'border-yellow-500' : 
                         'border-gray-600'}"
           style={{
             opacity: verificationStatus === 'idle' ? 0.3 : 0.8,
             transform: `scale(${verificationStatus === 'listening' || verificationStatus === 'processing' ? 1.05 : 1})`,
             transition: 'all 0.3s ease'
           }}></div>
      
      {/* Inner visualization */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        {verificationStatus === 'listening' && (
          <div className="w-[150px] h-[150px] rounded-full 
                          border-2 border-dashed border-blue-400/50
                          animate-[rotate_3s_linear_infinite]">
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-4 h-4 bg-blue-500 rounded-full 
                            animate-[pulse_2s_ease_in_out_infinite]"></div>
            </div>
          </div>
        )}
        
        {verificationStatus === 'processing' && (
          <div className="w-[120px] h-[120px] rounded-full 
                          bg-gradient-to-r from-blue-500 to-purple-500/50
                          animate-[spin_3s_linear_infinite]">
            <div className="absolute inset-0 flex items-center justify-center pt-4">
              <div className="text-center text-xs text-white">
                Analyzing...
              </div>
            </div>
          </div>
        )}
        
        {(verificationStatus === 'verified' || verificationStatus === 'failed') && (
          <div className="w-[100px] h-[100px] rounded-full 
                          flex items-center justify-center
                          ${verificationStatus === 'verified' ? 'bg-green-500/20' : 'bg-red-500/20'}"
                          >
            <div className="text-center text-xs font-medium 
                        ${verificationStatus === 'verified' ? 'text-green-400' : 'text-red-400'}">
              {verificationStatus === 'verified' ? 'Verified' : 'Failed'}
            </div>
          </div>
        )}
        
        {verificationStatus === 'idle' && (
          <div className="w-[80px] h-[80px] rounded-full 
                          bg-gray-800/50 flex items-center justify-center">
            <div className="text-center text-xs text-gray-400">
              🎤
            </div>
          </div>
        )}
      </div>
      
      {/* Status label */}
      <div className="absolute bottom-0 left-1/2 -translate-x-1/2 
                        text-xs text-center w-[180px]"
           style={{
             color: verificationStatus === 'verified' ? '#4ade80' :
                    verificationStatus === 'failed' ? '#f87171' :
                    verificationStatus === 'listening' ? '#60a5fa' :
                    verificationStatus === 'processing' ? '#fbbf24' :
                    '#9ca3af'
           }}>
            {verificationStatus === 'idle' ? 'Voiceprint Verification' :
             verificationStatus === 'listening' ? 'Listening for voice...' :
             verificationStatus === 'processing' => 'Analyzing voiceprint...' :
             verificationStatus === 'verified' => 'Voice verified!' :
             'Verification failed'}
           </div>
      
      {/* Manual trigger button */}
      <div className="absolute bottom-2 left-1/2 -translate-x-1/2 
                        flex items-center justify-center
                        ${active ? '' : 'opacity-50 pointer-events-none'}"
           onClick={handleVerifyClick}
           style={{
             cursor: active ? 'pointer' : 'not-allowed'
           }}>
            <div className="w-8 h-8 rounded-full 
                            bg-gray-700/60 hover:bg-gray-600
                            flex items-center justify-center
                            text-xs text-white">
              🔍
            </div>
          </div>
    </div>
  )
}

// CSS keyframes for voiceprint verification
if (typeof window !== 'undefined' && !document.getElementById('jarvis-voiceprint-styles')) {
  const style = document.createElement('style')
  style.id = 'jarvis-voiceprint-styles'
  style.textContent = `
    @keyframes rotate {
      from { transform: rotate(0deg); }
      to { transform: rotate(360deg); }
    }
    
    @keyframes spin {
      from { transform: rotate(0deg); }
      to { transform: rotate(360deg); }
    }
  `
  document.head.appendChild(style)
}