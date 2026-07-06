'use client'

import { useEffect, useRef, useState } from 'react'
import { JarvisUtils } from '@/lib/nancy/jarvis-utils'

interface PredictiveUIAnticipatorProps {
  /** Whether prediction is active */
  active?: boolean
  /** How far ahead to predict (in seconds) */
  predictionHorizon?: number
  /** Minimum confidence to show prediction */
  minConfidence?: number
  /** UI element to predict and show */
  predictedElement?: React.ReactNode
  /** Callback when user interacts with predicted element */
  onPredictedInteraction?: () => void
  /** Callback when prediction is made */
  onPredictionMade?: (confidence: number, element: React.ReactNode) => void
}

export function PredictiveUIAnticipator({
  active = true,
  predictionHorizon = 5,
  minConfidence = 0.6,
  predictedElement,
  onPredictedInteraction,
  onPredictionMade
}: PredictiveUIAnticipatorProps) {
  const [isPredicting, setIsPredicting] = useState(false)
  const [predictedConfidence, setPredictedConfidence] = useState(0)
  const [showPrediction, setShowPrediction] = useState(false)
  const predictionRef = useRef<number | null>(null)
  const lastInteractionRef = useRef<number>(Date.now())
  const interactionHistoryRef = useRef<Array<{ type: string; time: number; context?: Record<string, unknown> }>>([])
  
  // Record user interaction
  const recordInteraction = (type: string, context?: Record<string, unknown>) => {
    const now = Date.now()
    interactionHistoryRef.current.push({ type, time: now, context })
    
    // Keep history limited
    if (interactionHistoryRef.current.length > 50) {
      interactionHistoryRef.current = interactionHistoryRef.current.slice(-50)
    }
    
    lastInteractionRef.current = now
    
    // Trigger prediction update
    updatePrediction()
  }
  
  // Update prediction based on interaction history
  const updatePrediction = () => {
    if (!active) return
    
    setIsPredicting(true)
    
    // Use the jarvis utils to predict user intent
    const interactionHistory = interactionHistoryRef.current
    const timeSinceLastInteraction = Date.now() - lastInteractionRef.current
    
    const prediction = JarvisUtils.detectUserIntent(
      interactionHistory.map(i => i.type), 
      timeSinceLastInteraction
    )
    
    setPredictedConfidence(prediction.confidence)
    
    // Show prediction if confidence is high enough
    if (prediction.confidence >= minConfidence) {
      setShowPrediction(true)
      setIsPredicting(false)
      onPredictionMade?.(prediction.confidence, predictedElement)
    } else {
      setShowPrediction(false)
      setIsPredicting(false)
    }
  }
  
  // Start prediction loop
  useEffect(() => {
    if (!active) {
      if (predictionRef.current !== null) {
        clearInterval(predictionRef.current)
        predictionRef.current = null
      }
      setIsPredicting(false)
      setShowPrediction(false)
      return
    }
    
    // Update prediction every second
    predictionRef.current = window.setInterval(() => {
      updatePrediction()
    }, 1000)
    
    // Initial prediction
    updatePrediction()
    
    // Cleanup
    return () => {
      if (predictionRef.current !== null) {
        clearInterval(predictionRef.current)
        predictionRef.current = null
      }
    }
  }, [active, minConfidence, predictionHorizon])
  
  // Handle interaction with predicted element
  const handlePredictedInteraction = () => {
    onPredictedInteraction?.()
    
    // Record this as a successful prediction
    recordInteraction('predicted_element_interaction', { 
      confidence: predictedConfidence,
      elementType: typeof predictedElement === 'string' ? predictedElement : 'component'
    })
    
    // Hide prediction after interaction
    setShowPrediction(false)
  }
  
  if (!showPrediction || !predictedElement) return null
  
  return (
    <div className="fixed z-[40] pointer-events-none"
         style={{
           // Position prediction near where user is likely to look/interact
           top: '20%',
           left: '50%',
           transform: 'translateX(-50%)',
           pointerEvents: showPrediction ? 'all' : 'none',
           opacity: showPrediction ? 1 : 0,
           transition: 'opacity 0.3s ease, transform 0.3s ease'
         }}>
      <div className="relative w-[280px] h-[120px] max-w-[90vw]"
           style={{
             background: 'linear-gradient(135deg, rgba(30,41,59,0.8) 0%, rgba(15,23,42,0.9) 100%)',
             border: `1px solid rgba(56,211,235,${Math.min(0.8, predictedConfidence * 1.2)})`,
             borderRadius: '16px',
             boxShadow: `
               0 0 30px rgba(56,211,235,${Math.min(0.6, predictedConfidence)}),
               0 10px 25px -5px rgba(0,0,0,0.5),
               inset 0 0 5px rgba(56,211,235,0.2)
             `,
             backdropBlur: '10px',
             position: 'relative',
             overflow: 'hidden',
             animation: showPrediction 
               ? 'predictive-slide-up-then-float 0.6s ease-out' 
               : 'predictive-slide-down 0.3s ease-in'
           }}>
           
           {/* Prediction confidence indicator */}
           <div className="absolute top-2 left-2 right-2 h-0.5 bg-[linear-gradient(90deg,transparent_0%,rgba(56,211,235,${Math.min(0.8, predictedConfidence*1.2)})_50%,transparent_100%)"
                style={{
                  height: '2px',
                  backgroundImage: `linear-gradient(90deg, transparent 0%, rgba(56,211,235, ${Math.min(0.8, predictedConfidence * 1.2)}) 50%, transparent 100%)`,
                  height: '2px'
                }}></div>
           
           {/* Predicted content */}
           <div className="relative h-full w-full p-4 overflow-hidden"
                style={{
                  color: '#e2e8f0',
                  textShadow: '0 0 5px rgba(56,211,235,0.3)'
                }}>
              <div className="h-full w-full overflow-y-auto">
                {predictedElement}
              </div>
              
              {/* Interaction hint */}
              <div className="absolute bottom-2 left-2 right-2 text-center text-xs font-medium
                          bg-black/50 backdrop-blur-sm rounded-full px-2 py-1
                          hover:bg-black/60
                          cursor-pointer"
                   onClick={handlePredictedInteraction}
                   style={{
                     pointerEvents: 'all'
                   }}>
                {predictedConfidence >= 0.8 ? 'Click to use' : 'Tap to activate'}
              </div>
            </div>
            
            {/* Subtle animated elements */}
            <div className="absolute inset-0 pointer-events-none"
                 style={{
                   backgroundImage: `
                     repeating-linear-gradient(
                       45deg,
                       rgba(56,211,235,0.1) 0px,
                       rgba(56,211,235,0.1) 1px,
                       transparent 1px,
                       transparent 10px
                     )
                   `,
                   opacity: predictedConfidence * 0.3
                 }}></div>
          </div>
      </div>
    </div>
  )
}

// CSS keyframes for predictive UI
if (typeof window !== 'undefined' && !document.getElementById('jarvis-predictive-ui-styles')) {
  const style = document.createElement('style')
  style.id = 'jarvis-predictive-ui-styles'
  style.textContent = `
    @keyframes predictive-slide-up-then-float {
      0% { transform: translateX(-50%) translateY(20px); opacity: 0; }
      30% { transform: translateX(-50%) translateY(-10px); opacity: 0.9; }
      100% { transform: translateX(-50%) translateY(0); opacity: 1; }
    }
    
    @keyframes predictive-slide-down {
      100% { transform: translateX(-50%) translateY(20px); opacity: 0; }
      0% { transform: translateX(-50%) translateY(0); opacity: 1; }
    }
    
    @keyframes pulse {
      0%, 100% { opacity: 0.6; }
      50% { opacity: 1; }
    }
  `
  document.head.appendChild(style)
}