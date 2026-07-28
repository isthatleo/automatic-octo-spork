'use client'

import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import type { Scene3DData, Scene3DObject } from '@/lib/nancy/types'

/* ═══════════════════════════════════════════════════════════════════════
   Scene3DViewer — a real, orbit-controllable Three.js renderer for
   illustrative "3d_scene" canvas items (backend: create_3d_scene tool,
   canvas_store.py). Deliberately simple: a handful of labeled primitives
   (box/sphere/cylinder/cone/torus), never a CAD-accurate model — matches
   the honest educational scope documented on the backend tool/schema.
   Raw three (no @react-three/fiber in package.json) driven by refs, mirroring
   how map-panel.tsx drives Leaflet imperatively rather than declaratively.
   ═══════════════════════════════════════════════════════════════════════ */

function buildGeometry(obj: Scene3DObject): THREE.BufferGeometry {
  const s = obj.size ?? []
  switch (obj.type) {
    case 'box':
      return new THREE.BoxGeometry(s[0] ?? 1, s[1] ?? 1, s[2] ?? 1)
    case 'sphere':
      return new THREE.SphereGeometry(s[0] ?? 0.75, 32, 24)
    case 'cylinder':
      return new THREE.CylinderGeometry(s[0] ?? 0.6, s[1] ?? s[0] ?? 0.6, s[2] ?? 1.2, 32)
    case 'cone':
      return new THREE.ConeGeometry(s[0] ?? 0.6, s[1] ?? 1.2, 32)
    case 'torus':
      return new THREE.TorusGeometry(s[0] ?? 0.8, s[1] ?? 0.25, 16, 48)
    default:
      return new THREE.BoxGeometry(1, 1, 1)
  }
}

function makeLabelSprite(text: string): THREE.Sprite {
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')!
  const fontSize = 48
  ctx.font = `${fontSize}px sans-serif`
  const width = Math.max(ctx.measureText(text).width + 32, 64)
  canvas.width = width
  canvas.height = fontSize * 1.6
  ctx.font = `${fontSize}px sans-serif`
  ctx.fillStyle = 'rgba(10, 14, 20, 0.72)'
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  ctx.fillStyle = '#e8f2ff'
  ctx.textBaseline = 'middle'
  ctx.fillText(text, 16, canvas.height / 2)

  const texture = new THREE.CanvasTexture(canvas)
  const material = new THREE.SpriteMaterial({ map: texture, depthTest: false, transparent: true })
  const sprite = new THREE.Sprite(material)
  const scale = 0.014
  sprite.scale.set(canvas.width * scale, canvas.height * scale, 1)
  return sprite
}

export function Scene3DViewer({ scene: sceneData }: { scene: Scene3DData }) {
  const mountRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return

    const width = mount.clientWidth || 480
    const height = 360

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(width, height)
    mount.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    scene.background = null

    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000)

    const objects = sceneData.objects ?? []
    // Frame the camera around the real bounding box of the scene's objects
    // rather than a fixed distance, so both a single small shape and a wide
    // multi-object layout both start fully in view.
    const box = new THREE.Box3()
    if (objects.length === 0) box.expandByPoint(new THREE.Vector3(0, 0, 0))
    for (const obj of objects) {
      const [x, y, z] = obj.position
      box.expandByPoint(new THREE.Vector3(x, y, z))
    }
    const center = box.getCenter(new THREE.Vector3())
    const size = box.getSize(new THREE.Vector3())
    const radius = Math.max(size.length() * 0.6, 3)
    camera.position.set(center.x + radius, center.y + radius * 0.7, center.z + radius)
    camera.lookAt(center)

    scene.add(new THREE.AmbientLight(0xffffff, 0.55))
    const key = new THREE.DirectionalLight(0xffffff, 0.9)
    key.position.set(radius, radius * 1.5, radius)
    scene.add(key)
    const rim = new THREE.DirectionalLight(0x88aaff, 0.4)
    rim.position.set(-radius, -radius * 0.5, -radius)
    scene.add(rim)

    const grid = new THREE.GridHelper(Math.max(size.length() * 1.5, 8), 16, 0x2a3a4a, 0x1a2530)
    grid.position.y = box.min.y - 0.01
    scene.add(grid)

    for (const obj of objects) {
      const geometry = buildGeometry(obj)
      const material = new THREE.MeshStandardMaterial({
        color: obj.color ?? '#3a8bff',
        roughness: 0.45,
        metalness: 0.15,
      })
      const mesh = new THREE.Mesh(geometry, material)
      mesh.position.set(obj.position[0], obj.position[1], obj.position[2])
      scene.add(mesh)

      if (obj.label) {
        const sprite = makeLabelSprite(obj.label)
        const objHeight = (obj.size?.[1] ?? obj.size?.[0] ?? 1) * 0.5 + 0.6
        sprite.position.set(obj.position[0], obj.position[1] + objHeight, obj.position[2])
        scene.add(sprite)
      }
    }

    // Minimal orbit control implemented by hand (no OrbitControls import
    // available without extra deps) -- drag to orbit, wheel to zoom.
    let dragging = false
    let lastX = 0
    let lastY = 0
    let theta = Math.atan2(camera.position.x - center.x, camera.position.z - center.z)
    let phi = Math.acos(THREE.MathUtils.clamp((camera.position.y - center.y) / radius, -1, 1))
    let distance = camera.position.distanceTo(center)

    const updateCamera = () => {
      const clampedPhi = THREE.MathUtils.clamp(phi, 0.15, Math.PI - 0.15)
      camera.position.set(
        center.x + distance * Math.sin(clampedPhi) * Math.sin(theta),
        center.y + distance * Math.cos(clampedPhi),
        center.z + distance * Math.sin(clampedPhi) * Math.cos(theta),
      )
      camera.lookAt(center)
    }

    const onPointerDown = (e: PointerEvent) => {
      dragging = true
      lastX = e.clientX
      lastY = e.clientY
    }
    const onPointerMove = (e: PointerEvent) => {
      if (!dragging) return
      const dx = e.clientX - lastX
      const dy = e.clientY - lastY
      lastX = e.clientX
      lastY = e.clientY
      theta -= dx * 0.008
      phi -= dy * 0.008
      updateCamera()
    }
    const onPointerUp = () => { dragging = false }
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      distance = THREE.MathUtils.clamp(distance * (1 + e.deltaY * 0.001), radius * 0.4, radius * 4)
      updateCamera()
    }

    const el = renderer.domElement
    el.addEventListener('pointerdown', onPointerDown)
    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', onPointerUp)
    el.addEventListener('wheel', onWheel, { passive: false })

    let raf = 0
    const animate = () => {
      raf = requestAnimationFrame(animate)
      renderer.render(scene, camera)
    }
    animate()

    return () => {
      cancelAnimationFrame(raf)
      el.removeEventListener('pointerdown', onPointerDown)
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerup', onPointerUp)
      el.removeEventListener('wheel', onWheel)
      renderer.dispose()
      scene.traverse((obj) => {
        if (obj instanceof THREE.Mesh) {
          obj.geometry.dispose()
          if (Array.isArray(obj.material)) obj.material.forEach((m) => m.dispose())
          else obj.material.dispose()
        }
        if (obj instanceof THREE.Sprite) {
          obj.material.map?.dispose()
          obj.material.dispose()
        }
      })
      if (mount.contains(el)) mount.removeChild(el)
    }
  }, [sceneData])

  return (
    <div className="flex flex-col gap-1.5">
      <div
        ref={mountRef}
        className="h-[280px] w-full cursor-grab touch-none overflow-hidden rounded-lg border border-border bg-background/40 active:cursor-grabbing"
      />
      {sceneData.description && (
        <p className="text-[0.58rem] leading-relaxed text-muted-foreground">{sceneData.description}</p>
      )}
      <span className="text-[0.5rem] text-muted-foreground/70">Drag to orbit · scroll to zoom · illustrative only</span>
    </div>
  )
}
