'use client'

import { useEffect, useRef, useState } from 'react'

interface SpatialAudioManagerProps {
  /** Whether spatial audio is enabled */
  enabled?: boolean
  /** Default volume for spatial sounds */
  volume?: number
  /** Distance at which sound is at full volume */
  range?: number
  /** Doppler effect intensity */
  dopplerIntensity?: number
}

export function SpatialAudioManager({
  enabled = true,
  volume = 0.7,
  range = 10,
  dopplerIntensity = 0.3
}: SpatialAudioManagerProps) {
  const audioContextRef = useRef<AudioContext | null>(null)
  const listenerRef = useRef<{ x: number; y: number; z: number }>({ x: 0, y: 0, z: 0 })
  const sourceRef = useRef<Map<string, { source: AudioBufferSourceNode; gain: GainNode; panner: PannerNode }>>(new Map())
  const bufferRef = useRef<Map<string, AudioBuffer>>(new Map())
  const [isInitialized, setIsInitialized] = useState(false)
  
  // Initialize audio context
  useEffect(() => {
    if (!enabled || typeof window === 'undefined') return
    
    try {
      // Create audio context
      const AudioContext = window.AudioContext || (window as any).webkitAudioContext
      audioContextRef.current = new AudioContext()
      
      // Set up listener position
      if (audioContextRef.current.listener) {
        audioContextRef.current.listener.positionX.value = listenerRef.current.x
        audioContextRef.current.listener.positionY.value = listenerRef.current.y
        audioContextRef.current.listener.positionZ.value = listenerRef.current.z
      }
      
      setIsInitialized(true)
      
      // Cleanup on unmount
      return () => {
        audioContextRef.current?.close()
        audioContextRef.current = null
      }
    } catch (e) {
      console.warn('Failed to initialize spatial audio:', e)
      setIsInitialized(false)
    }
  }, [enabled])
  
  // Load a sound buffer
  const loadSoundBuffer = async (url: string): Promise<void> => {
    if (!audioContextRef.current) return
    
    try {
      const response = await fetch(url)
      const arrayBuffer = await response.arrayBuffer()
      const audioBuffer = await audioContextRef.current.decodeAudioData(arrayBuffer)
      bufferRef.current.set(url, audioBuffer)
    } catch (e) {
      console.error(`Failed to load sound buffer from ${url}:`, e)
      throw e
    }
  }
  
  // Play a sound at a specific position
  const playSoundAtPosition = async (
    soundUrl: string,
    position: { x: number; y: number; z: number },
    options: {
      loop?: boolean
      playbackRate?: number
      volume?: number
      delay?: number
    } = {}
  ): Promise<void> => {
    if (!audioContextRef.current || !enabled) return
    
    try {
      // Get or load buffer
      let audioBuffer = bufferRef.current.get(soundUrl)
      if (!audioBuffer) {
        await loadSoundBuffer(soundUrl)
        audioBuffer = bufferRef.current.get(soundUrl)
        if (!audioBuffer) throw new Error(`Failed to load buffer for ${soundUrl}`)
      }
      
      // Create audio nodes
      const source = audioContextRef.current.createBufferSource()
      const gainNode = audioContextRef.current.createGain()
      const panner = audioContextRef.current.createPanner()
      
      // Configure nodes
      source.buffer = audioBuffer
      source.loop = options.loop ?? false
      source.playbackRate.value = options.playbackRate ?? 1
      
      gainNode.gain.value = (options.volume ?? volume) * volume
      
      // Set panner properties for 3D audio
      panner.panningModel = 'HRTF'
      panner.distanceModel = 'inverse'
      panner.refDistance = 1
      panner.maxDistance = range
      panner.rolloffFactor = 1
      
      // Connect nodes
      source.connect(gainNode)
      gainNode.connect(panner)
      panner.connect(audioContextRef.current.destination)
      
      // Set position
      panner.positionX.value = position.x
      panner.positionY.value = position.y
      panner.positionZ.value = position.z
      
      // Apply Doppler effect if moving
      if (dopplerIntensity > 0 && options.playbackRate) {
        // In a full implementation, we'd calculate velocity and apply Doppler shift
        // This is a simplified version
        source.playbackRate.value *= 1 + Math.sin(Date.now() * 0.001) * dopplerIntensity * 0.1
      }
      
      // Start playback with optional delay
      const startTime = audioContextRef.current.currentTime + (options.delay ?? 0)
      source.start(startTime)
      
      // Store reference for cleanup if needed
      const soundId = `${soundUrl}-${Date.now()}-${Math.random()}`
      sourceRef.current.set(soundId, { source, gainNode, panner })
      
      // Auto-cleanup when sound ends
      source.onended = () => {
        sourceRef.current.delete(soundId)
        source.disconnect()
        gainNode.disconnect()
        panner.disconnect()
      }
    } catch (e) {
      console.error('Failed to play spatial sound:', e)
    }
  }
  
  // Update listener position (for head tracking or user movement)
  const updateListenerPosition = (position: { x: number; y: number; z: number }) => {
    listenerRef.current = position
    if (audioContextRef.current?.listener) {
      audioContextRef.current.listener.positionX.value = position.x
      audioContextRef.current.listener.positionY.value = position.y
      audioContextRef.current.listener.positionZ.value = position.z
    }
  }
  
  // Set volume
  const setVolume = (newVolume: number) => {
    // In a full implementation, we'd update all active gain nodes
    // For now, we just store the value for new sounds
    // This is a simplification for the prototype
  }
  
  // Preload common JARVIS sounds
  useEffect(() => {
    if (!isInitialized) return
    
    // Preload common interface sounds
    const commonSounds = [
      // These would be actual URLs to sound files in a real implementation
      '/sounds/jarvis-wake.wav',
      '/sounds/jarvis-think.wav',
      '/sounds/jarvis-speak.wav',
      '/sounds/jarvis-alert.wav',
      '/sounds/jarvis-success.wav',
      '/sounds/jarvis-error.wav'
    ]
    
    // For now, we'll just note that these would be preloaded
    // In a real implementation, we'd actually load these buffers
    
    return () => {
      // Cleanup would happen here
    }
  }, [isInitialized])
  
  // Provide methods to child components via context or refs
  // For simplicity in this prototype, we'll just expose basic functionality
  
  return null // This component manages audio invisibly
}

// Hook for components to use spatial audio
export const useSpatialAudio = () => {
  // In a real implementation, this would use React context
  // For now, we'll return a simplified version
  
  const playInterfaceSound = async (soundName: string, options: { volume?: number; loop?: boolean } = {}) => {
    // Map sound names to actual files (would be implemented with real audio assets)
    const soundMap: Record<string, string> = {
      wake: '/sounds/jarvis-wake.wav',
      think: '/sounds/jarvis-think.wav',
      speak: '/sounds/jarvis-speak.wav',
      alert: '/sounds/jarvis-alert.wav',
      success: '/sounds/jarvis-success.wav',
      error: '/sounds/jarvis-error.wav',
      orbit: '/sounds/jarvis-orbit.wav',
      select: '/sounds/jarvis-select.wav',
      back: '/sounds/jarvis-back.wav'
    }
    
    const url = soundMap[soundName] || '/sounds/jarvis-orbit.wav'
    // In a real implementation, we'd call playSoundAtPosition here
    console.log(`Would play sound: ${url}`, options)
  }
  
  return {
    playInterfaceSound
  }
}

export default SpatialAudioManager