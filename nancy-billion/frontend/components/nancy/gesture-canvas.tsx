'use client'

import { useEffect, useRef, useState } from 'react'

interface GestureCanvasProps {
  /** Callback when a gesture is recognized */
  onGestureRecognized?: (gesture: string, confidence: number) => void
  /** Whether gesture recognition is active */
  active?: boolean
  /** Visual feedback intensity */
  feedbackIntensity?: number
  /** Canvas dimensions */
  width?: number
  height?: number
}

export function GestureCanvas({
  onGestureRecognized,
  active = true,
  feedbackIntensity = 0.7,
  width = 300,
  height = 300
}: GestureCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [isDrawing, setIsDrawing] = useState(false)
  const [lastPoint, setLastPoint] = useState<{ x: number; y: number } | null>(null)
  const [points, setPoints] = useState<Array<{ x: number; y: number; time: number }>>([])
  const [recognizedGesture, setRecognizedGesture] = useState<string | null>(null)
  
  useEffect(() => {
    if (!active || typeof window === 'undefined') return
    
    const canvas = canvasRef.current
    if (!canvas) return
    
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    
    // Set canvas dimensions
    canvas.width = width
    canvas.height = height
    
    // Mouse/touch event handlers
    const handleStart = (e: MouseEvent | TouchEvent) => {
      e.preventDefault()
      const point = getPointFromEvent(e)
      if (!point) return
      
      setIsDrawing(true)
      setLastPoint(point)
      setPoints([{ ...point, time: Date.now() }])
    }
    
    const handleMove = (e: MouseEvent | TouchEvent) => {
      if (!isDrawing) return
      e.preventDefault()
      const point = getPointFromEvent(e)
      if (!point) return
      
      setLastPoint(point)
      setPoints(prev => [...prev, { ...point, time: Date.now() }])
      
      // Keep only recent points for performance
      if (points.length > 50) {
        setPoints(prev => prev.slice(-50))
      }
      
      // Draw line segment
      if (ctx && lastPoint) {
        ctx.beginPath()
        ctx.moveTo(lastPoint.x, lastPoint.y)
        ctx.lineTo(point.x, point.y)
        ctx.strokeStyle = `rgba(56, 211, 235, ${feedbackIntensity})`
        ctx.lineWidth = 2
        ctx.stroke()
      }
    }
    
    const handleEnd = () => {
      if (!isDrawing) return
      setIsDrawing(false)
      
      // Analyze the gesture
      const gesture = analyzeGesture(points)
      if (gesture && onGestureRecognized) {
        onGestureRecognized(gesture, calculateGestureConfidence(points, gesture))
        setRecognizedGesture(gesture)
        
        // Clear after recognition
        setTimeout(() => {
          setRecognizedGesture(null)
          setPoints([])
          if (ctx) {
            ctx.clearRect(0, 0, canvas.width, canvas.height)
          }
        }, 1500)
      }
    }
    
    // Get point from mouse or touch event
    const getPointFromEvent = (e: MouseEvent | TouchEvent): { x: number; y: number } | null => {
      if (!canvas) return null
      const rect = canvas.getBoundingClientRect()
      
      let clientX: number, clientY: number
      if ('touches' in e && e.touches.length > 0) {
        clientX = e.touches[0].clientX
        clientY = e.touches[0].clientY
      } else {
        clientX = e.clientX
        clientY = e.clientY
      }
      
      return {
        x: clientX - rect.left,
        y: clientY - rect.top
      }
    }
    
    // Attach event listeners
    canvas.addEventListener('mousedown', handleStart as EventListener)
    canvas.addEventListener('mousemove', handleMove as EventListener)
    canvas.addEventListener('mouseup', handleEnd as EventListener)
    canvas.addEventListener('mouseleave', handleEnd as EventListener)
    
    canvas.addEventListener('touchstart', handleStart as EventListener)
    canvas.addEventListener('touchmove', handleMove as EventListener)
    canvas.addEventListener('touchend', handleEnd as EventListener)
    canvas.addEventListener('touchcancel', handleEnd as EventListener)
    
    // Cleanup
    return () => {
      canvas.removeEventListener('mousedown', handleStart as EventListener)
      canvas.removeEventListener('mousemove', handleMove as EventListener)
      canvas.removeEventListener('mouseup', handleEnd as EventListener)
      canvas.removeEventListener('mouseleave', handleEnd as EventListener)
      canvas.removeEventListener('touchstart', handleStart as EventListener)
      canvas.removeEventListener('touchmove', handleMove as EventListener)
      canvas.removeEventListener('touchend', handleEnd as EventListener)
      canvas.removeEventListener('touchcancel', handleEnd as EventListener)
    }
  }, [active, feedbackIntensity, height, onGestureRecognized, width])
  
  // Simple gesture recognition (in production, use a proper ML model)
  const analyzeGesture = (points: Array<{ x: number; y: number; time: number }>): string | null => {
    if (points.length < 5) return null
    
    // Calculate basic properties
    const firstPoint = points[0]
    const lastPoint = points[points.length - 1]
    const dx = lastPoint.x - firstPoint.x
    const dy = lastPoint.y - firstPoint.y
    const distance = Math.sqrt(dx * dx + dy * dy)
    
    // Simple gesture classifications
    if (distance < 20) {
      // Tap or click
      return 'tap'
    }
    
    if (Math.abs(dx) > Math.abs(dy) * 2) {
      // Horizontal swipe
      return dx > 0 ? 'swipe-right' : 'swipe-left'
    }
    
    if (Math.abs(dy) > Math.abs(dx) * 2) {
      // Vertical swipe
      return dy > 0 ? 'swipe-down' : 'swipe-up'
    }
    
    // Check for circular motion
    const totalAngleChange = calculateTotalAngleChange(points)
    if (Math.abs(totalAngleChange) > Math.PI * 1.5) {
      return totalAngleChange > 0 ? 'circle-clockwise' : 'circle-counterclockwise'
    }
    
    // Check for zigzag
    if (isZigzagPattern(points)) {
      return 'zigzag'
    }
    
    return null
  }
  
  // Helper functions for gesture analysis
  const calculateTotalAngleChange = (points: Array<{ x: number; y: number; time: number }>): number => {
    if (points.length < 3) return 0
    
    let totalAngle = 0
    for (let i = 1; i < points.length - 1; i++) {
      const p0 = points[i - 1]
      const p1 = points[i]
      const p2 = points[i + 1]
      
      const v1x = p1.x - p0.x
      const v1y = p1.y - p0.y
      const v2x = p2.x - p1.x
      const v2y = p2.y - p1.y
      
      const dot = v1x * v2x + v1y * v2y
      const cross = v1x * v2y - v1y * v2x
      const angle = Math.atan2(Math.abs(cross), dot)
      
      totalAngle += cross > 0 ? angle : -angle
    }
    
    return totalAngle
  }
  
  const isZigzagPattern = (points: Array<{ x: number; y: number; time: number }>): boolean => {
    if (points.length < 6) return false
    
    const dxs = points.slice(1).map((p, i) => p.x - points[i].x)
    const signChanges = dxs.reduce((count, dx, i) => {
      if (i > 0 && ((dx > 0 && dxs[i - 1] < 0) || (dx < 0 && dxs[i - 1] > 0))) {
        return count + 1
      }
      return count
    }, 0)
    
    return signChanges >= 3
  }
  
  // Calculate confidence based on gesture clarity
  const calculateGestureConfidence = (points: Array<{ x: number; y: number; time: number }>, gesture: string): number => {
    if (points.length < 5) return 0.5
    
    // Base confidence on gesture clarity and consistency
    let confidence = 0.7
    
    // Increase confidence for longer, more deliberate gestures
    const duration = points[points.length - 1].time - points[0].time
    if (duration > 500) confidence += 0.1
    if (duration > 1000) confidence += 0.1
    
    // Increase confidence for larger gestures
    const firstPoint = points[0]
    const lastPoint = points[points.length - 1]
    const distance = Math.sqrt(
      Math.pow(lastPoint.x - firstPoint.x, 2) + 
      Math.pow(lastPoint.y - firstPoint.y, 2)
    )
    if (distance > 100) confidence += 0.1
    if (distance > 200) confidence += 0.1
    
    return Math.min(0.95, confidence)
  }
  
  return (
    <canvas
      ref={canvasRef}
      className={`absolute inset-0 pointer-events-none ${!active ? 'opacity-25' : ''}`}
      width={width}
      height={height}
      style={{
        background: 'radial-gradient(circle at center, transparent 0%, rgba(0,0,0,0.3) 100%)',
        pointerEvents: 'none'
      }}
    />
  )
}