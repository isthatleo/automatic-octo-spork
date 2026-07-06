/**
 * Spatial math utilities for JARVIS-enhanced Nancy/Billion system
 * Provides helper functions for 3D positioning, raycasting, and spatial calculations
 */

import type { OrbState } from '@/components/nancy/nancy-orb'

/**
 * 3D vector class for spatial calculations
 */
export class Vector3 {
  constructor(
    public x: number = 0,
    public y: number = 0,
    public z: number = 0
  ) {}

  set(x: number, y: number, z: number): Vector3 {
    this.x = x
    this.y = y
    this.z = z
    return this
  }

  clone(): Vector3 {
    return new Vector3(this.x, this.y, this.z)
  }

  copy(v: Vector3): Vector3 {
    this.x = v.x
    this.y = v.y
    this.z = v.z
    return this
  }

  add(v: Vector3): Vector3 {
    this.x += v.x
    this.y += v.y
    this.z += v.z
    return this
  }

  subtract(v: Vector3): Vector3 {
    this.x -= v.x
    this.y -= v.y
    this.z -= v.z
    return this
  }

  multiply(v: Vector3): Vector3 {
    this.x *= v.x
    this.y *= v.y
    this.z *= v.z
    return this
  }

  multiplyScalar(s: number): Vector3 {
    this.x *= s
    this.y *= s
    this.z *= s
    return this
  }

  divide(v: Vector3): Vector3 {
    this.x /= v.x
    this.y /= v.y
    this.z /= v.z
    return this
  }

  divideScalar(s: number): Vector3 {
    if (s !== 0) {
      this.x /= s
      this.y /= s
      this.z /= s
    }
    return this
  }

  negate(): Vector3 {
    this.x = -this.x
    this.y = -this.y
    this.z = -this.z
    return this
  }

  dot(v: Vector3): number {
    return this.x * v.x + this.y * v.y + this.z * v.z
  }

  cross(v: Vector3): Vector3 {
    return new Vector3(
      this.y * v.z - this.z * v.y,
      this.z * v.x - this.x * v.z,
      this.x * v.y - this.y * v.x
    )
  }

  length(): number {
    return Math.sqrt(this.x * this.x + this.y * this.y + this.z * this.z)
  }

  lengthSq(): number {
    return this.x * this.x + this.y * this.y + this.z * this.z
  }

  normalize(): Vector3 {
    return this.divideScalar(this.length() || 1)
  }

  distanceTo(v: Vector3): number {
    return Math.sqrt(
      (this.x - v.x) * (this.x - v.x) +
      (this.y - v.y) * (this.y - v.y) +
      (this.z - v.z) * (this.z - v.z)
    )
  }

  lerp(v: Vector3, alpha: number): Vector3 {
    this.x += (v.x - this.x) * alpha
    this.y += (v.y - this.y) * alpha
    this.z += (v.z - this.z) * alpha
    return this
  }

  equals(v: Vector3): boolean {
    return v.x === this.x && v.y === this.y && v.z === this.z
  }

  fromArray(array: number[], offset: number = 0): Vector3 {
    this.x = array[offset]
    this.y = array[offset + 1]
    this.z = array[offset + 2]
    return this
  }

  toArray(array: number[] = [], offset: number = 0): number[] {
    array[offset] = this.x
    array[offset + 1] = this.y
    array[offset + 2] = this.z
    return array
  }
}

/**
 * Quaternion for 3D rotations
 */
export class Quaternion {
  constructor(
    public x: number = 0,
    public y: number = 0,
    public z: number = 0,
    public w: number = 1
  ) {}

  set(x: number, y: number, z: number, w: number): Quaternion {
    this.x = x
    this.y = y
    this.z = z
    this.w = w
    return this
  }

  clone(): Quaternion {
    return new Quaternion(this.x, this.y, this.z, this.w)
  }

  copy(q: Quaternion): Quaternion {
    this.x = q.x
    this.y = q.y
    this.z = q.z
    this.w = q.w
    return this
  }

  setFromEuler(euler: Vector3, order: string = 'XYZ'): Quaternion {
    // Simplified Euler to quaternion conversion
    // In production, use a robust library like three.js
    const c1 = Math.cos(euler.x / 2)
    const c2 = Math.cos(euler.y / 2)
    const c3 = Math.cos(euler.z / 2)
    const s1 = Math.sin(euler.x / 2)
    const s2 = Math.sin(euler.y / 2)
    const s3 = Math.sin(euler.z / 2)

    if (order === 'XYZ') {
      this.x = s1 * c2 * c3 + c1 * s2 * s3
      this.y = c1 * s2 * c3 - s1 * c2 * s3
      this.z = c1 * c2 * s3 + s1 * s2 * c3
      this.w = c1 * c2 * c3 - s1 * s2 * s3
    } else {
      // Default to XYZ
      this.x = s1 * c2 * c3 + c1 * s2 * s3
      this.y = c1 * s2 * c3 - s1 * c2 * s3
      this.z = c1 * c2 * s3 + s1 * s2 * c3
      this.w = c1 * c2 * c3 - s1 * s2 * s3
    }

    return this.normalize()
  }

  multiply(q: Quaternion): Quaternion {
    return new Quaternion(
      this.w * q.x + this.x * q.w + this.y * q.z - this.z * q.y,
      this.w * q.y - this.x * q.z + this.y * q.w + this.z * q.x,
      this.w * q.z + this.x * q.y - this.y * q.x + this.z * q.w,
      this.w * q.w - this.x * q.x - this.y * q.y - this.z * q.z
    ).normalize()
  }

  normalize(): Quaternion {
    const length = Math.sqrt(this.x * this.x + this.y * this.y + this.z * this.z + this.w * this.w)
    if (length === 0) {
      this.x = 0
      this.y = 0
      this.z = 0
      this.w = 1
    } else {
      this.x /= length
      this.y /= length
      this.z /= length
      this.w /= length
    }
    return this
  }

  inverse(): Quaternion {
    return this.conjugate()
  }

  conjugate(): Quaternion {
    return new Quaternion(-this.x, -this.y, -this.z, this.w)
  }

  dot(q: Quaternion): number {
    return this.x * q.x + this.y * q.y + this.z * q.z + this.w * q.w
  }

  length(): number {
    return Math.sqrt(this.x * this.x + this.y * this.y + this.z * this.z + this.w * this.w)
  }

  normalize(): Quaternion {
    return this.divideScalar(this.length() || 1)
  }

  setFromAxisAngle(axis: Vector3, angle: number): Quaternion {
    const halfAngle = angle / 2
    const s = Math.sin(halfAngle)
    this.x = axis.x * s
    this.y = axis.y * s
    this.z = axis.z * s
    this.w = Math.cos(halfAngle)
    return this.normalize()
  }

  slerp(qb: Quaternion, t: number): Quaternion {
    // Spherical linear interpolation
    // Simplified version for prototype
    const cosHalfTheta = this.w * qb.w + this.x * qb.x + this.y * qb.y + this.z * qb.z

    if (Math.abs(cosHalfTheta) >= 1.0) {
      this.copy(qb)
      return this
    }

    const halfTheta = Math.acos(cosHalfTheta)
    const sinHalfTheta = Math.sqrt(1.0 - cosHalfTheta * cosHalfTheta)

    if (Math.abs(sinHalfTheta) < 0.001) {
      this.w = 0.5 * (this.w + qb.w)
      this.x = 0.5 * (this.x + qb.x)
      this.y = 0.5 * (this.y + qb.y)
      this.z = 0.5 * (this.z + qb.z)
      return this
    }

    const ratioA = Math.sin((1 - t) * halfTheta) / sinHalfTheta
    const ratioB = Math.sin(t * halfTheta) / sinHalfTheta

    this.w = this.w * ratioA + qb.w * ratioB
    this.x = this.x * ratioA + qb.x * ratioB
    this.y = this.y * ratioA + qb.x * ratioB
    this.z = this.z * ratioA + qb.z * ratioB

    return this.normalize()
  }
}

/**
 * Raycaster for 3D object picking
 */
export class Raycaster {
  constructor(
    public origin: Vector3 = new Vector3(),
    public direction: Vector3 = new Vector3(0, 0, -1)
  ) {}

  set(origin: Vector3, direction: Vector3): void {
    this.origin.copy(origin)
    this.direction.copy(direction).normalize()
  }

  setFromCamera(coords: { x: number; y: number }, camera: { 
    position: Vector3; 
    quaternion: Quaternion; 
    fov: number; 
    aspect: number;
  }): void {
    // Simplified raycasting from camera
    // In production, use proper camera matrix transformations
    this.origin.copy(camera.position)

    // Convert screen coordinates to world direction
    // This is a simplified approximation
    const x = (coords.x * 2 - 1) * Math.tan(camera.fov * Math.PI / 360) * camera.aspect
    const y = -(coords.y * 2 - 1) * Math.tan(camera.fov * Math.PI / 360)
    const z = -1

    this.direction.set(x, y, z).normalize()
    
    // Apply camera rotation
    // Simplified - in reality would use quaternion rotation
    this.direction.x += camera.quaternion.x
    this.direction.y += camera.quaternion.y
    this.direction.z += camera.quaternion.z
    this.direction.normalize()
  }

  intersectObject(object: { 
    position: Vector3; 
    boundingSphere: { radius: number; center: Vector3 } 
  }): { distance: number; point: Vector3 } | null {
    // Simple sphere-ray intersection
    const center = object.boundingSphere.center.clone().add(object.position)
    const oc = this.origin.clone().subtract(center)
    
    const b = this.direction.dot(oc)
    const c = oc.dot(oc) - object.boundingSphere.radius * object.boundingSphere.radius
    
    const discriminant = b * b - c
    
    if (discriminant < 0) {
      return null
    }
    
    const distance = -b - Math.sqrt(discriminant)
    
    if (distance < 0) {
      return null
    }
    
    const point = this.origin.clone().add(this.direction.clone().multiplyScalar(distance))
    
    return { distance, point }
  }

  intersectObjects(objects: Array<{ 
    position: Vector3; 
    boundingSphere: { radius: number; center: Vector3 } 
  }>): Array<{ 
    distance: number; 
    point: Vector3; 
    object: { position: Vector3; boundingSphere: { radius: number; center: Vector3 } }
  }> {
    const intersects: Array<{ 
      distance: number; 
      point: Vector3; 
      object: { position: Vector3; boundingSphere: { radius: number; center: Vector3 } }
    }> = []

    for (const object of objects) {
      const intersect = this.intersectObject(object)
      if (intersect) {
        intersects.push({
          distance: intersect.distance,
          point: intersect.point,
          object: object
        })
      }
    }

    // Sort by distance (closest first)
    intersects.sort((a, b) => a.distance - b.distance)
    return intersects
  }
}

/**
 * Math utilities for common JARVIS calculations
 */
export const JarvisMath = {
  /**
   * Smooth damping function for smooth transitions
   */
  smoothDamp: (current: number, target: number, currentVelocity: number, smoothTime: number, maxSpeed: number = Infinity, deltaTime: number = 0.016): [number, number] => {
    smoothTime = Math.max(0.0001, smoothTime)
    const omega = 2 / smoothTime
    
    const x = omega * deltaTime
    const exp = 1 / (1 + x + 0.48 * x * x + 0.235 * x * x * x)
    
    const change = current - target
    const originalTo = target
    
    let maxChange = maxSpeed * smoothTime
    target = change > maxChange ? target + maxChange : change < -maxChange ? target - maxChange : target
    
    const temp = (currentVelocity + omega * (change - target)) * deltaTime
    currentVelocity = (currentVelocity - omega * temp) * exp
    let result = target + (change - target) * exp + temp * exp
    
    if ((originalTo - current) * (result - originalTo) > 0) {
      result = originalTo
      currentVelocity = (result - originalTo) / deltaTime
    }
    
    return [result, currentVelocity]
  },

  /**
   * Calculate orbital position
   */
  calculateOrbitalPosition: (center: Vector3, radius: number, angle: number, elevation: number = 0): Vector3 => {
    const x = center.x + radius * Math.cos(angle) * Math.cos(elevation)
    const y = center.y + radius * Math.sin(angle) * Math.cos(elevation)
    const z = center.z + radius * Math.sin(elevation)
    return new Vector3(x, y, z)
  },

  /**
   * Convert screen coordinates to normalized device coordinates
   */
  screenToNdc: (screenX: number, screenY: number, viewportWidth: number, viewportHeight: number): { x: number; y: number } => {
    return {
      x: (screenX / viewportWidth) * 2 - 1,
      y: -(screenY / viewportHeight) * 2 + 1
    }
  },

  /**
   * Calculate distance-based attenuation
   */
  distanceAttenuation: (distance: number, referenceDistance: number = 1, maxDistance: number = 100, rolloffFactor: number = 1): number => {
    if (distance < referenceDistance) return 1
    const attenuation = 1 / (1 + rolloffFactor * Math.pow(distance / referenceDistance, 1))
    return Math.min(1, Math.max(0, attenuation))
  },

  /**
   * Generate pseudo-random values based on seed
   */
  seededRandom: (seed: number): number => {
    // Simple LCG (Linear Congruential Generator)
    const x = Math.sin(seed) * 10000
    return x - Math.floor(x)
  },

  /**
   * Map value from one range to another
   */
  mapRange: (value: number, inMin: number, inMax: number, outMin: number, outMax: number): number => {
    return (value - inMin) * (outMax - outMin) / (inMax - inMin) + outMin
  },

  /**
   * Clamp value between min and max
   */
  clamp: (value: number, min: number, max: number): number => {
    return Math.min(Math.max(value, min), max)
  },

  /**
   * Linear interpolation
   */
  lerp: (start: number, end: number, t: number): number => {
    return start + (end - start) * t
  },

  /**
   * Check if point is in front of plane
   */
  pointInFrontOfPlane: (point: Vector3, planePoint: Vector3, planeNormal: Vector3): boolean => {
    return point.subtract(planePoint).dot(planeNormal) > 0
  }
}

/**
 * Constants for JARVIS system
 */
export const JarvisConstants = {
  // Physical constants
  SPEED_OF_SOUND: 343, // m/s
  LIGHT_SPEED: 299792458, // m/s
  
  // UI constants
  HOLOGRAPHIC_INTENSITY_BASE: 0.6,
  ORBITAL_RADIUS_BASE: 1.5,
  PARTICLE_COUNT_BASE: 64,
  
  // Audio constants
  AUDIO_CONTEXT_SAMPLE_RATE: 44100,
  SPATIAL_AUDIO_RANGE_DEFAULT: 10,
  
  // Animation constants
  DEFAULT_ANIMATION_DURATION: 300,
  ORBITAL_SPEED_BASE: 0.2,
  
  // Interaction thresholds
  GESTURE_MIN_POINTS: 5,
  GESTURE_MIN_DURATION_MS: 100,
  VOICE_CONFIDENCE_THRESHOLD: 0.7,
  
  // Prediction constants
  PREDICTION_HORIZON_DEFAULT: 5, // seconds
  PREDICTION_MIN_CONFIDENCE: 0.6,
  
  // Environmental scanning
  ENVIRONMENTAL_SCAN_INTERVAL_DEFAULT: 1000, // ms
  ENVIRONMENTAL_SCAN_RANGE_DEFAULT: 5, // meters
}

/**
 * Extension of Vector3 with JARVIS-specific methods
 */
export interface JarvisVector3 extends Vector3 {
  /**
   * Rotate vector around axis by angle
   */
  rotateAroundAxis: (axis: Vector3, angle: number) => Vector3
  
  /**
   * Project vector onto plane
   */
  projectOntoPlane: (planeNormal: Vector3, planePoint: Vector3) => Vector3
  
  /**
   * Calculate reflection vector
   */
  reflect: (normal: Vector3) => Vector3
}

export type { Vector3, Quaternion, Raycaster }