import { useEffect, useRef, useState, useCallback } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import type { BoundingBox } from '../types'

interface Props {
  sessionId: string | null
  originalKey: number
  currentKey: number
  selectionMode: boolean
  onRegionSelected: (bbox: BoundingBox) => void
  onSelectionCleared: () => void
  currentBBox: BoundingBox | null
}

export default function Viewer3D({
  sessionId, originalKey, currentKey,
  selectionMode, onRegionSelected, onSelectionCleared, currentBBox,
}: Props) {
  const mountRef     = useRef<HTMLDivElement>(null)
  const rendererRef  = useRef<THREE.WebGLRenderer | null>(null)
  const cameraRef    = useRef<THREE.PerspectiveCamera | null>(null)
  const controlsRef  = useRef<OrbitControls | null>(null)
  const origScene    = useRef(new THREE.Scene())
  const currScene    = useRef(new THREE.Scene())
  const origCloudRef = useRef<THREE.Points | null>(null)
  const currCloudRef = useRef<THREE.Points | null>(null)
  const animRef      = useRef<number>(0)
  const boxHelpers   = useRef<THREE.Box3Helper[]>([])
  const firstPt      = useRef<THREE.Vector3 | null>(null)

  // useState so the instruction banner re-renders when click count changes
  const [clickStep, setClickStep]     = useState(0)
  const [origLoading, setOrigLoading] = useState(false)
  const [currLoading, setCurrLoading] = useState(false)

  // ── Initialise Three.js once ─────────────────────────────────────────────
  useEffect(() => {
    const container = mountRef.current!
    const w = container.clientWidth || 800
    const h = container.clientHeight || 600

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(w, h)
    renderer.setScissorTest(true)
    container.appendChild(renderer.domElement)
    rendererRef.current = renderer

    const camera = new THREE.PerspectiveCamera(55, (w / 2) / h, 0.001, 500000)
    camera.position.set(0, 5, 20)
    cameraRef.current = camera

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.07
    controls.screenSpacePanning = true
    controlsRef.current = controls

    for (const scene of [origScene.current, currScene.current]) {
      scene.background = new THREE.Color(0x060d17)
      const grid = new THREE.GridHelper(200, 60, 0x101f30, 0x0d1a28)
      scene.add(grid)
    }

    const animate = () => {
      animRef.current = requestAnimationFrame(animate)
      controls.update()
      const W    = renderer.domElement.clientWidth
      const H    = renderer.domElement.clientHeight
      const half = Math.floor(W / 2)
      camera.aspect = half / Math.max(H, 1)
      camera.updateProjectionMatrix()

      renderer.setViewport(0, 0, half, H)
      renderer.setScissor(0, 0, half, H)
      renderer.render(origScene.current, camera)

      renderer.setViewport(half, 0, half, H)
      renderer.setScissor(half, 0, half, H)
      renderer.render(currScene.current, camera)
    }
    animate()

    const onResize = () => {
      const nw = container.clientWidth
      const nh = container.clientHeight
      renderer.setSize(nw, nh)
    }
    const ro = new ResizeObserver(onResize)
    ro.observe(container)

    return () => {
      cancelAnimationFrame(animRef.current)
      ro.disconnect()
      renderer.dispose()
      if (container.contains(renderer.domElement)) container.removeChild(renderer.domElement)
    }
  }, [])

  // ── Load original cloud ──────────────────────────────────────────────────
  useEffect(() => {
    if (!sessionId || originalKey === 0) return
    setOrigLoading(true)
    fetchCloud(sessionId, 'original').then(({ cloud, center, radius }) => {
      if (origCloudRef.current) {
        origScene.current.remove(origCloudRef.current)
        origCloudRef.current.geometry.dispose()
      }
      origScene.current.add(cloud)
      origCloudRef.current = cloud
      centreCamera(center, radius)
    }).catch(console.error).finally(() => setOrigLoading(false))
  }, [sessionId, originalKey])

  // ── Load current cloud ───────────────────────────────────────────────────
  useEffect(() => {
    if (!sessionId || currentKey === 0) return
    setCurrLoading(true)
    fetchCloud(sessionId, 'current').then(({ cloud }) => {
      if (currCloudRef.current) {
        currScene.current.remove(currCloudRef.current)
        currCloudRef.current.geometry.dispose()
      }
      currScene.current.add(cloud)
      currCloudRef.current = cloud
    }).catch(console.error).finally(() => setCurrLoading(false))
  }, [sessionId, currentKey])

  // ── Selection box helpers ────────────────────────────────────────────────
  useEffect(() => {
    for (const h of boxHelpers.current) {
      origScene.current.remove(h)
      currScene.current.remove(h)
    }
    boxHelpers.current = []

    if (currentBBox) {
      const mn = currentBBox.min as [number, number, number]
      const mx = currentBBox.max as [number, number, number]
      const box = new THREE.Box3(new THREE.Vector3(...mn), new THREE.Vector3(...mx))
      const h1 = new THREE.Box3Helper(box, new THREE.Color(0x00e676))
      const h2 = new THREE.Box3Helper(box, new THREE.Color(0x00e676))
      origScene.current.add(h1)
      currScene.current.add(h2)
      boxHelpers.current = [h1, h2]
    }
  }, [currentBBox])

  // ── Canvas click handler ─────────────────────────────────────────────────
  const handleClick = useCallback((e: MouseEvent) => {
    if (!selectionMode || !origCloudRef.current || !cameraRef.current || !rendererRef.current) return
    const canvas = rendererRef.current.domElement
    const rect   = canvas.getBoundingClientRect()
    const x      = e.clientX - rect.left

    if (x > rect.width / 2) return   // only left (original) half

    const ndcX =  (x / (rect.width / 2)) * 2 - 1
    const ndcY = -((e.clientY - rect.top) / rect.height) * 2 + 1

    const ray = new THREE.Raycaster()
    ray.params.Points = { threshold: 0.5 }
    ray.setFromCamera(new THREE.Vector2(ndcX, ndcY), cameraRef.current)
    const hits = ray.intersectObject(origCloudRef.current)
    if (!hits.length) return

    const pt = hits[0].point.clone()

    if (!firstPt.current) {
      firstPt.current = pt
      setClickStep(1)
    } else {
      const p1 = firstPt.current
      const bbox: BoundingBox = {
        min: [Math.min(p1.x, pt.x), Math.min(p1.y, pt.y), Math.min(p1.z, pt.z)],
        max: [Math.max(p1.x, pt.x), Math.max(p1.y, pt.y), Math.max(p1.z, pt.z)],
      }
      firstPt.current = null
      setClickStep(0)
      onRegionSelected(bbox)
    }
  }, [selectionMode, onRegionSelected])

  useEffect(() => {
    const canvas = rendererRef.current?.domElement
    if (!canvas) return
    canvas.addEventListener('click', handleClick)
    return () => canvas.removeEventListener('click', handleClick)
  }, [handleClick])

  // Reset selection state when mode turns off
  useEffect(() => {
    if (!selectionMode) {
      firstPt.current = null
      setClickStep(0)
    }
  }, [selectionMode])

  function centreCamera(center: THREE.Vector3, radius: number) {
    if (!cameraRef.current || !controlsRef.current) return
    cameraRef.current.position.set(center.x, center.y + radius * 0.4, center.z + radius * 2.2)
    cameraRef.current.lookAt(center)
    controlsRef.current.target.copy(center)
    controlsRef.current.update()
  }

  const loading = origLoading || currLoading

  return (
    <div className="relative w-full h-full">
      {/* Canvas mount */}
      <div ref={mountRef} className="w-full h-full" style={{ cursor: selectionMode ? 'crosshair' : 'grab' }} />

      {/* Panel labels */}
      <PanelLabel side="left" label="ORIGINAL" />
      <PanelLabel side="right" label="CLEANED" colour="success" />

      {/* Vertical divider */}
      <div className="pointer-events-none absolute inset-y-0 left-1/2 w-px bg-border/60" />

      {/* Cloud loading indicator */}
      {loading && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 flex items-center gap-2
          bg-surface2/90 border border-border rounded-full px-4 py-1.5 text-xs text-muted">
          <div className="w-3 h-3 border border-border border-t-accent rounded-full animate-spin" />
          Loading point cloud…
        </div>
      )}

      {/* Selection mode banner */}
      {selectionMode && (
        <div className="pointer-events-none absolute bottom-5 left-1/2 -translate-x-1/2
          flex items-center gap-2 bg-accent/90 backdrop-blur-sm text-white text-xs
          px-4 py-2 rounded-full shadow-lg border border-accent/50 animate-fade-in">
          <span className="w-4 h-4 rounded-full border border-white/60 flex items-center justify-center text-[10px] font-bold">
            {clickStep + 1}
          </span>
          {clickStep === 0
            ? 'Click first corner on the left (ORIGINAL) view'
            : 'Click second corner to complete the selection box'}
        </div>
      )}

      {/* Controls hint */}
      <div className="pointer-events-none absolute bottom-3 right-3 text-[10px] text-dim space-y-0.5 text-right">
        <div>Scroll — zoom</div>
        <div>Drag — rotate</div>
        <div>Right-drag — pan</div>
      </div>
    </div>
  )
}

// ── Panel label chip ──────────────────────────────────────────────────────────
function PanelLabel({ side, label, colour }: { side: 'left' | 'right'; label: string; colour?: string }) {
  const pos = side === 'left' ? 'left-0 w-1/2' : 'right-0 w-1/2'
  const col = colour === 'success' ? 'text-success border-success/30' : 'text-muted border-border'
  return (
    <div className={`pointer-events-none absolute top-3 ${pos} flex justify-center`}>
      <span className={`text-[10px] font-semibold tracking-widest px-3 py-1
        bg-surface/80 border rounded-full backdrop-blur-sm ${col}`}>
        {label}
      </span>
    </div>
  )
}

// ── Cloud fetcher ─────────────────────────────────────────────────────────────
async function fetchCloud(sessionId: string, which: 'original' | 'current') {
  const res = await fetch(`/api/process/preview/${sessionId}/${which}`)
  if (!res.ok) throw new Error(`Preview ${which} failed: ${res.status}`)
  const buffer = await res.arrayBuffer()

  const total     = buffer.byteLength / 4
  const numPoints = Math.floor(total / 6)
  const all       = new Float32Array(buffer)

  const positions = new Float32Array(numPoints * 3)
  const colours   = new Float32Array(numPoints * 3)

  for (let i = 0; i < numPoints; i++) {
    const b = i * 6
    positions[i * 3]     = all[b]
    positions[i * 3 + 1] = all[b + 1]
    positions[i * 3 + 2] = all[b + 2]
    colours[i * 3]       = all[b + 3]
    colours[i * 3 + 1]   = all[b + 4]
    colours[i * 3 + 2]   = all[b + 5]
  }

  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  geo.setAttribute('color',    new THREE.BufferAttribute(colours, 3))
  geo.computeBoundingSphere()

  const sphere = geo.boundingSphere!
  const ptSize = Math.max(sphere.radius * 0.003, 0.005)

  const mat = new THREE.PointsMaterial({ size: ptSize, vertexColors: true, sizeAttenuation: true })
  const cloud = new THREE.Points(geo, mat)

  return { cloud, center: sphere.center.clone(), radius: sphere.radius }
}
