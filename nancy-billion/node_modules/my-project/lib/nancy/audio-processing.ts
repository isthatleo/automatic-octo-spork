'use client'

/**
 * Audio Processing Module for Nancy-billion
 * Integrates clap detection and audio processing capabilities
 */

// Clap Detection Constants
const CLAP_DETECTION_THRESHOLD = 0.7;
const CLAP_SAMPLE_RATE = 16000;
const CLAP_FRAME_SIZE = 512;
const CLAP_CONSECUTIVE_FRAMES_REQUIRED = 3;

// Audio buffer for clap detection
let audioBuffer: Float32Array = new Float32Array();
let consecutiveClaps = 0;
let isListeningForClap = false;

/**
 * Initialize clap detection audio processing
 */
export function initializeClapDetection(): void {
  if (typeof window === 'undefined') return;
  
  // Request audio input
  navigator.mediaDevices.getUserMedia({ audio: true })
    .then(stream => {
      const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 2048;
      
      const microphone = audioContext.createMediaStreamSource(stream);
      microphone.connect(analyser);
      
      const bufferLength = analyser.frequencyBinCount;
      const dataArray = new Uint8Array(bufferLength);
      
      function detectClap() {
        analyser.getByteTimeDomainData(dataArray);
        
        // Simple RMS-based clap detection (in production, would use trained model)
        let sum = 0;
        for (let i = 0; i < bufferLength; i++) {
          // Convert to [-1, 1] range
          const normalized = (dataArray[i] - 128) / 128;
          sum += normalized * normalized;
        }
        const rms = Math.sqrt(sum / bufferLength);
        
        // Detect clap based on sudden energy spike
        if (rms > CLAP_DETECTION_THRESHOLD) {
          consecutiveClaps++;
          if (consecutiveClaps >= CLAP_CONSECUTIVE_FRAMES_REQUIRED && !isListeningForClap) {
            isListeningForClap = true;
            // Trigger wake word detection
            triggerClapWake();
            
            // Reset after a short delay to prevent multiple triggers
            setTimeout(() => {
              consecutiveClaps = 0;
              isListeningForClap = false;
            }, 1000);
          }
        } else {
          consecutiveClaps = Math.max(0, consecutiveClaps - 1);
        }
        
        requestAnimationFrame(detectClap);
      }
      
      detectClap();
    })
    .catch(err => {
      console.error('Error accessing microphone for clap detection:', err);
    });
}

/**
 * Trigger wake word detection when clap is detected
 */
function triggerClapWake(): void {
  console.log('Clap detected! Triggering wake word detection...');
  
  // In a full implementation, this would signal the voice system to listen for commands
  // For now, we'll log it and could integrate with the existing voice system
  const clapEvent = new CustomEvent('clapDetected', {
    detail: {
      timestamp: Date.now(),
      type: 'clap_wake'
    }
  });
  
  window.dispatchEvent(clapEvent);
}

/**
 * Process audio for voice features (pitch, energy, etc.)
 */
export function processAudioFeatures(audioBuffer: Float32Array): {
  energy: number;
  zeroCrossingRate: number;
  spectralCentroid: number;
} {
  // Calculate energy (RMS)
  let energySum = 0;
  for (let i = 0; i < audioBuffer.length; i++) {
    energySum += audioBuffer[i] * audioBuffer[i];
  }
  const energy = Math.sqrt(energySum / audioBuffer.length);
  
  // Calculate zero crossing rate
  let zeroCrossings = 0;
  for (let i = 1; i < audioBuffer.length; i++) {
    if (audioBuffer[i] * audioBuffer[i-1] < 0) {
      zeroCrossings++;
    }
  }
  const zeroCrossingRate = zeroCrossings / audioBuffer.length;
  
  // Simplified spectral centroid (would use FFT in production)
  let spectralSum = 0;
  let weightSum = 0;
  for (let i = 0; i < audioBuffer.length; i++) {
    const magnitude = Math.abs(audioBuffer[i]);
    spectralSum += magnitude * i;
    weightSum += magnitude;
  }
  const spectralCentroid = weightSum > 0 ? spectralSum / weightSum : 0;
  
  return {
    energy,
    zeroCrossingRate,
    spectralCentroid
  };
}

/**
 * Voice activity detection
 */
export function isVoiceActivity(audioBuffer: Float32Array, threshold: number = 0.01): boolean {
  const features = processAudioFeatures(audioBuffer);
  return features.energy > threshold;
}