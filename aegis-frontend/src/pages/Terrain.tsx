/**
 * TerrainPage — 3D Risk Terrain visualisation
 *
 * Four dimensions encoded simultaneously:
 *   Height   → inherent severity  (critical = tallest)
 *   Colour   → risk domain        (each domain has its own hue)
 *   Top face → control coverage   (saturated = well-controlled, grey = exposed)
 *   Orange ! → AI overlay         (zero control coverage)
 *
 * Navigation:
 *   Mouse drag  → orbit (Y-axis rotation)
 *   Scroll      → zoom
 *   Click peak  → drill-down detail panel
 *   Domain tabs → isolate a cluster (others fade to near-zero height)
 */

import React, { useEffect, useRef, useState, useCallback } from 'react'
import * as THREE from 'three'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { risksApi } from '@/api/client'
import type { Risk } from '@/types'

// ── Domain normalisation ──────────────────────────────────────────────────────
// The DB stores full descriptive domain names; we bucket them into six display categories.

interface DomainCfg {
  label:    string
  hex:      number          // THREE.Color hex
  hexStr:   string          // CSS colour
  position: [number, number] // world-space centre [x, z]
}

const DOMAINS: Record<string, DomainCfg> = {
  'Financial crime': {
    label: 'Financial crime', hex: 0xe05252, hexStr: '#e05252',
    position: [-4.5, -3.5],
  },
  'Cyber & IT': {
    label: 'Cyber & IT', hex: 0x7c73ff, hexStr: '#7c73ff',
    position: [ 3.5, -3.5],
  },
  'Data & privacy': {
    label: 'Data & privacy', hex: 0x4a9eff, hexStr: '#4a9eff',
    position: [-4.5,  3.5],
  },
  'Operational': {
    label: 'Operational', hex: 0xe8a838, hexStr: '#e8a838',
    position: [ 3.5,  3.5],
  },
  'Financial': {
    label: 'Financial', hex: 0xe8803a, hexStr: '#e8803a',
    position: [ 0,  -8],
  },
  'Compliance': {
    label: 'Compliance', hex: 0x1eb98a, hexStr: '#1eb98a',
    position: [ 0,   8],
  },
}

// DB domain → display category
function normaliseDomain(dbDomain: string | null): string {
  if (!dbDomain) return 'Operational'
  const d = dbDomain.toLowerCase()
  if (d.includes('financial crime') || d.includes('fraud') || d.includes('aml') ||
      d.includes('sanctions') || d.includes('conduct') || d.includes('insider')) return 'Financial crime'
  if (d.includes('cyber') || d.includes('information security') ||
      d.includes('technology') || d.includes('it risk') || d.includes('cloud') ||
      d.includes('privileged')) return 'Cyber & IT'
  if (d.includes('privacy') || d.includes('data protection') ||
      d.includes('gdpr') || d.includes('dsar')) return 'Data & privacy'
  if (d.includes('model') || d.includes('algorithmic') || d.includes('credit')) return 'Financial'
  if (d.includes('esg') || d.includes('environmental') || d.includes('legal') ||
      d.includes('regulatory') || d.includes('compliance') || d.includes('greenwash')) return 'Compliance'
  if (d.includes('third') || d.includes('vendor') || d.includes('resilience') ||
      d.includes('continuity') || d.includes('operational')) return 'Operational'
  return 'Operational'
}

// ── Severity → height ─────────────────────────────────────────────────────────
const SEV_HEIGHT: Record<string, number> = {
  critical: 4.2,
  high:     2.9,
  medium:   1.8,
  low:      0.9,
}

const SEV_LABEL_COLOR: Record<string, string> = {
  critical: '#e05252',
  high:     '#e8a838',
  medium:   '#4a9eff',
  low:      '#1eb98a',
}

// ── Colour helpers ─────────────────────────────────────────────────────────────
function lerpColorHex(from: number, to: number, t: number): number {
  const fr = (from >> 16) & 0xff, fg = (from >> 8) & 0xff, fb = from & 0xff
  const tr = (to >> 16) & 0xff,   tg = (to >> 8) & 0xff,   tb = to & 0xff
  const r = Math.round(fr + (tr - fr) * t)
  const g = Math.round(fg + (tg - fg) * t)
  const b = Math.round(fb + (tb - fb) * t)
  return (r << 16) | (g << 8) | b
}

// ── Label sprite ──────────────────────────────────────────────────────────────
function makeLabelSprite(text: string): THREE.Sprite {
  const canvas = document.createElement('canvas')
  canvas.width = 320
  canvas.height = 56
  const ctx = canvas.getContext('2d')!
  ctx.clearRect(0, 0, 320, 56)
  ctx.fillStyle = 'rgba(10,11,14,0.82)'
  ctx.beginPath()
  ;(ctx as any).roundRect?.(2, 2, 316, 52, 6)
  ctx.fill()
  ctx.fillStyle = '#e8eaf0'
  ctx.font = '500 20px DM Sans, sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  const display = text.length > 26 ? text.slice(0, 24) + '…' : text
  ctx.fillText(display, 160, 28)
  const tex = new THREE.CanvasTexture(canvas)
  tex.needsUpdate = true
  const mat = new THREE.SpriteMaterial({ map: tex, depthTest: false })
  const sprite = new THREE.Sprite(mat)
  sprite.scale.set(3.2, 0.56, 1)
  return sprite
}

// ── Exclamation sprite ─────────────────────────────────────────────────────────
function makeExclSprite(): THREE.Sprite {
  const canvas = document.createElement('canvas')
  canvas.width = 64; canvas.height = 64
  const ctx = canvas.getContext('2d')!
  ctx.clearRect(0, 0, 64, 64)
  ctx.fillStyle = '#e8a838'
  ctx.font = 'bold 52px sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText('!', 32, 34)
  const tex = new THREE.CanvasTexture(canvas)
  tex.needsUpdate = true
  const mat = new THREE.SpriteMaterial({ map: tex, depthTest: false })
  const sprite = new THREE.Sprite(mat)
  sprite.scale.set(0.55, 0.55, 1)
  return sprite
}

// ── Domain ground tile ─────────────────────────────────────────────────────────
function makeDomainTile(hex: number, cx: number, cz: number, w = 5.5, d = 5.5): THREE.Mesh {
  const geo = new THREE.PlaneGeometry(w, d)
  const col = new THREE.Color(hex)
  col.multiplyScalar(0.14)
  const mat = new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.6 })
  const mesh = new THREE.Mesh(geo, mat)
  mesh.rotation.x = -Math.PI / 2
  mesh.position.set(cx, 0.01, cz)
  return mesh
}

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────
export const TerrainPage: React.FC = () => {
  const navigate = useNavigate()
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef    = useRef<HTMLCanvasElement>(null)

  // Three.js refs (don't need to trigger re-renders)
  const rendererRef   = useRef<THREE.WebGLRenderer | null>(null)
  const sceneRef      = useRef<THREE.Scene | null>(null)
  const cameraRef     = useRef<THREE.PerspectiveCamera | null>(null)
  const barMeshesRef  = useRef<THREE.Mesh[]>([])
  const labelGroupRef = useRef<THREE.Group | null>(null)
  const exclGroupRef  = useRef<THREE.Group | null>(null)
  const animFrameRef  = useRef<number>(0)

  // Camera orbit state (refs to avoid stale closures in event listeners)
  const thetaRef    = useRef(Math.PI / 5)
  const phiRef      = useRef(1.05)          // ~60° elevation
  const radiusRef   = useRef(22)
  const isDragRef   = useRef(false)
  const prevMouseRef = useRef({ x: 0, y: 0 })

  // React state
  const [selectedDomain, setSelectedDomain] = useState<string>('All')
  const [selectedRisk,   setSelectedRisk]   = useState<Risk | null>(null)
  const [showLabels,     setShowLabels]      = useState(false)
  const [showAI,         setShowAI]          = useState(true)
  const [rendererReady,  setRendererReady]   = useState(false)

  // Risk data
  const { data: riskList } = useQuery({
    queryKey: ['risks-terrain'],
    queryFn:  () => risksApi.list({ page: 1 }).then(r => r.items),
  })

  // ── Camera update helper ──────────────────────────────────────────────────
  const updateCamera = useCallback(() => {
    const cam = cameraRef.current
    if (!cam) return
    const r = radiusRef.current
    const theta = thetaRef.current
    const phi   = phiRef.current
    cam.position.set(
      r * Math.sin(phi) * Math.sin(theta),
      r * Math.cos(phi),
      r * Math.sin(phi) * Math.cos(theta),
    )
    cam.lookAt(0, 1, 0)
  }, [])

  // ── Scene initialisation ──────────────────────────────────────────────────
  useEffect(() => {
    const container = containerRef.current
    const canvas    = canvasRef.current
    if (!container || !canvas) return

    const w = container.clientWidth
    const h = container.clientHeight

    // Renderer
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false })
    renderer.setSize(w, h)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.shadowMap.enabled = true
    rendererRef.current = renderer

    // Scene
    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0x0a0b0e)
    scene.fog = new THREE.Fog(0x0a0b0e, 30, 60)
    sceneRef.current = scene

    // Camera
    const camera = new THREE.PerspectiveCamera(42, w / h, 0.1, 200)
    cameraRef.current = camera
    updateCamera()
    scene.add(camera)

    // Lighting
    const ambient = new THREE.AmbientLight(0x8888aa, 1.6)
    scene.add(ambient)

    const sun = new THREE.DirectionalLight(0xffffff, 3.5)
    sun.position.set(8, 18, 12)
    sun.castShadow = true
    scene.add(sun)

    const fill = new THREE.DirectionalLight(0x4466aa, 1.2)
    fill.position.set(-10, 8, -8)
    scene.add(fill)

    // Ground plane
    const groundGeo = new THREE.PlaneGeometry(40, 40)
    const groundMat = new THREE.MeshPhongMaterial({ color: 0x0d1018 })
    const ground = new THREE.Mesh(groundGeo, groundMat)
    ground.rotation.x = -Math.PI / 2
    ground.receiveShadow = true
    scene.add(ground)

    // Subtle grid
    const grid = new THREE.GridHelper(40, 32, 0x1a1f28, 0x1a1f28)
    scene.add(grid)

    // Domain tiles
    Object.values(DOMAINS).forEach(d => {
      const [cx, cz] = d.position
      scene.add(makeDomainTile(d.hex, cx, cz))
    })

    // Label + exclamation groups
    const labelGroup = new THREE.Group()
    const exclGroup  = new THREE.Group()
    scene.add(labelGroup)
    scene.add(exclGroup)
    labelGroupRef.current = labelGroup
    exclGroupRef.current  = exclGroup

    setRendererReady(true)

    // Animation loop
    const render = () => {
      animFrameRef.current = requestAnimationFrame(render)
      renderer.render(scene, camera)
    }
    render()

    // Resize observer
    const ro = new ResizeObserver(() => {
      const nw = container.clientWidth
      const nh = container.clientHeight
      renderer.setSize(nw, nh)
      camera.aspect = nw / nh
      camera.updateProjectionMatrix()
    })
    ro.observe(container)

    return () => {
      cancelAnimationFrame(animFrameRef.current)
      ro.disconnect()
      renderer.dispose()
      rendererRef.current  = null
      sceneRef.current     = null
      cameraRef.current    = null
      setRendererReady(false)
    }
  }, [updateCamera])

  // ── Build / rebuild bar meshes when data arrives ──────────────────────────
  useEffect(() => {
    const scene = sceneRef.current
    const labelGroup = labelGroupRef.current
    const exclGroup  = exclGroupRef.current
    if (!scene || !labelGroup || !exclGroup || !riskList) return

    // Clear old bars + sprites
    barMeshesRef.current.forEach(m => scene.remove(m))
    barMeshesRef.current = []
    while (labelGroup.children.length) labelGroup.remove(labelGroup.children[0])
    while (exclGroup.children.length)  exclGroup.remove(exclGroup.children[0])

    // Group risks by display domain
    const byDomain: Record<string, Risk[]> = {}
    riskList.forEach(r => {
      const dn = normaliseDomain(r.domain)
      if (!byDomain[dn]) byDomain[dn] = []
      byDomain[dn].push(r)
    })

    // Build bars
    Object.entries(byDomain).forEach(([domainKey, risks]) => {
      const cfg = DOMAINS[domainKey]
      if (!cfg) return
      const [cx, cz] = cfg.position

      // Sort by severity desc so tallest bars are at domain centre
      const sorted = [...risks].sort((a, b) =>
        (SEV_HEIGHT[b.inherent_severity] ?? 0) - (SEV_HEIGHT[a.inherent_severity] ?? 0)
      )

      const cols = Math.ceil(Math.sqrt(sorted.length))
      const spacing = 1.4

      sorted.forEach((risk, i) => {
        const col = i % cols
        const row = Math.floor(i / cols)
        const bx  = cx + (col - (cols - 1) / 2) * spacing
        const bz  = cz + (row - (cols - 1) / 2) * spacing

        const h = SEV_HEIGHT[risk.inherent_severity] ?? 1.5
        const geo = new THREE.BoxGeometry(1, h, 1)

        // Coverage → top face colour
        const coverage = risk.control_coverage_pct ?? 0
        const satT = Math.max(0.15, coverage / 100)
        const topHex  = lerpColorHex(0x2a2e38, cfg.hex, satT)
        const sideHex = lerpColorHex(0x1a1e26, cfg.hex, 0.65)

        const makeM = (hex: number, emT = 0) => new THREE.MeshPhongMaterial({
          color:    new THREE.Color(hex),
          emissive: new THREE.Color(hex).multiplyScalar(emT),
          shininess: 40,
        })

        const side   = makeM(sideHex)
        const top    = makeM(topHex, 0.08)
        const bottom = makeM(0x080a0d)

        // BoxGeometry face order: +X, -X, +Y, -Y, +Z, -Z
        const bar = new THREE.Mesh(geo, [side, side, top, bottom, side, side])
        bar.position.set(bx, h / 2, bz)
        bar.castShadow    = true
        bar.receiveShadow = true
        bar.userData = { risk, domainKey, origHeight: h, origY: h / 2 }
        scene.add(bar)
        barMeshesRef.current.push(bar)

        // Label sprite (above bar, always created, visibility controlled by state)
        const label = makeLabelSprite(risk.name)
        label.position.set(bx, h + 0.85, bz)
        label.userData = { domainKey }
        labelGroup.add(label)

        // Exclamation sprite (zero coverage only)
        if (coverage === 0) {
          const excl = makeExclSprite()
          excl.position.set(bx, h + 0.45, bz)
          excl.userData = { domainKey }
          exclGroup.add(excl)
        }
      })
    })
  }, [riskList, rendererReady])

  // ── Domain filter — show/hide bars ────────────────────────────────────────
  useEffect(() => {
    barMeshesRef.current.forEach(bar => {
      const visible = selectedDomain === 'All' || bar.userData.domainKey === selectedDomain
      bar.visible = visible
    })
    labelGroupRef.current?.children.forEach(s => {
      const sp = s as THREE.Sprite
      sp.visible = showLabels && (selectedDomain === 'All' || sp.userData.domainKey === selectedDomain)
    })
    exclGroupRef.current?.children.forEach(s => {
      const sp = s as THREE.Sprite
      sp.visible = showAI && (selectedDomain === 'All' || sp.userData.domainKey === selectedDomain)
    })
  }, [selectedDomain, showLabels, showAI])

  // ── Labels toggle ─────────────────────────────────────────────────────────
  useEffect(() => {
    labelGroupRef.current?.children.forEach(s => {
      const sp = s as THREE.Sprite
      sp.visible = showLabels && (selectedDomain === 'All' || sp.userData.domainKey === selectedDomain)
    })
  }, [showLabels, selectedDomain])

  // ── AI overlay toggle ─────────────────────────────────────────────────────
  useEffect(() => {
    exclGroupRef.current?.children.forEach(s => {
      const sp = s as THREE.Sprite
      sp.visible = showAI && (selectedDomain === 'All' || sp.userData.domainKey === selectedDomain)
    })
  }, [showAI, selectedDomain])

  // ── Mouse events ──────────────────────────────────────────────────────────
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const onDown = (e: MouseEvent) => {
      isDragRef.current = true
      prevMouseRef.current = { x: e.clientX, y: e.clientY }
    }
    const onMove = (e: MouseEvent) => {
      if (!isDragRef.current) return
      const dx = e.clientX - prevMouseRef.current.x
      const dy = e.clientY - prevMouseRef.current.y
      thetaRef.current -= dx * 0.008
      phiRef.current    = Math.max(0.35, Math.min(1.45, phiRef.current + dy * 0.005))
      prevMouseRef.current = { x: e.clientX, y: e.clientY }
      updateCamera()
    }
    const onUp   = () => { isDragRef.current = false }
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      radiusRef.current = Math.max(8, Math.min(38, radiusRef.current + e.deltaY * 0.04))
      updateCamera()
    }
    const onClick = (e: MouseEvent) => {
      if (!sceneRef.current || !cameraRef.current) return
      const rect   = canvas.getBoundingClientRect()
      const mouse  = new THREE.Vector2(
        ((e.clientX - rect.left) / rect.width)  *  2 - 1,
        -((e.clientY - rect.top)  / rect.height) *  2 + 1,
      )
      const ray = new THREE.Raycaster()
      ray.setFromCamera(mouse, cameraRef.current)
      const hits = ray.intersectObjects(barMeshesRef.current)
      if (hits.length > 0) {
        const risk = hits[0].object.userData.risk as Risk
        setSelectedRisk(prev => prev?.id === risk.id ? null : risk)
      } else {
        setSelectedRisk(null)
      }
    }

    canvas.addEventListener('mousedown', onDown)
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup',   onUp)
    canvas.addEventListener('wheel',     onWheel, { passive: false })
    canvas.addEventListener('click',     onClick)
    return () => {
      canvas.removeEventListener('mousedown', onDown)
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup',   onUp)
      canvas.removeEventListener('wheel',     onWheel)
      canvas.removeEventListener('click',     onClick)
    }
  }, [updateCamera])

  // ── Reset camera ─────────────────────────────────────────────────────────
  const handleReset = () => {
    thetaRef.current  = Math.PI / 5
    phiRef.current    = 1.05
    radiusRef.current = 22
    updateCamera()
    setSelectedDomain('All')
    setSelectedRisk(null)
  }

  // ── Zoom buttons ──────────────────────────────────────────────────────────
  const zoom = (dir: 1 | -1) => {
    radiusRef.current = Math.max(8, Math.min(38, radiusRef.current + dir * -2.5))
    updateCamera()
  }

  // ── Domain filter tabs ────────────────────────────────────────────────────
  const domainTabs = ['All', ...Object.keys(DOMAINS)]

  // ── Risk detail sidebar ────────────────────────────────────────────────────
  const domainCfg = selectedRisk ? DOMAINS[normaliseDomain(selectedRisk.domain)] : null

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--bg)' }}>

      {/* ── Top toolbar ── */}
      <div style={{
        height: 50, flexShrink: 0, display: 'flex', alignItems: 'center',
        padding: '0 16px', borderBottom: '1px solid var(--border)',
        background: 'var(--bg1)', gap: 12,
      }}>
        <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text)', letterSpacing: '-0.2px', marginRight: 4 }}>
          Risk terrain — Uber Technologies
        </div>

        {/* Overlay toggles */}
        <div style={{ display: 'flex', gap: 5, marginLeft: 'auto' }}>
          {[
            { label: 'AI overlay', active: showAI,     set: setShowAI },
            { label: 'Labels',     active: showLabels,  set: setShowLabels },
          ].map(({ label, active, set }) => (
            <button key={label} onClick={() => set(v => !v)}
              style={{
                height: 28, padding: '0 11px', borderRadius: 6, border: '1px solid',
                borderColor: active ? 'rgba(108,99,255,.45)' : 'var(--border2)',
                background:  active ? 'rgba(108,99,255,.12)' : 'transparent',
                color:       active ? 'var(--accent2)' : 'var(--text2)',
                fontSize: 11, fontWeight: 500, cursor: 'pointer', fontFamily: 'var(--font)',
                transition: 'all .15s',
              }}>
              {active ? '◈ ' : '◇ '}{label}
            </button>
          ))}

          <button onClick={handleReset}
            style={{ height: 28, padding: '0 11px', borderRadius: 6, border: '1px solid var(--border2)', background: 'transparent', color: 'var(--text2)', fontSize: 11, fontWeight: 500, cursor: 'pointer', fontFamily: 'var(--font)' }}>
            ↺ Reset
          </button>

          <button
            style={{ height: 28, padding: '0 11px', borderRadius: 6, border: '1px solid var(--border2)', background: 'transparent', color: 'var(--text2)', fontSize: 11, fontWeight: 500, cursor: 'pointer', fontFamily: 'var(--font)', display: 'flex', alignItems: 'center', gap: 5 }}>
            ↓ Export ↗
          </button>
        </div>
      </div>

      {/* ── Domain filter strip ── */}
      <div style={{
        height: 44, flexShrink: 0, display: 'flex', alignItems: 'center',
        padding: '0 16px', borderBottom: '1px solid var(--border)',
        background: 'var(--bg1)', gap: 8, overflowX: 'auto',
      }}>
        {/* Zoom */}
        <div style={{ display: 'flex', gap: 4, marginRight: 4 }}>
          {(['+', '−'] as const).map((s, i) => (
            <button key={s} onClick={() => zoom(i === 0 ? 1 : -1)}
              style={{ width: 24, height: 24, borderRadius: 5, border: '1px solid var(--border2)', background: 'var(--bg2)', color: 'var(--text2)', fontSize: 14, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font)', lineHeight: 1 }}>
              {s}
            </button>
          ))}
        </div>

        <span style={{ fontSize: 10, color: 'var(--text3)', marginRight: 2, whiteSpace: 'nowrap' }}>Filter domain:</span>

        {domainTabs.map(d => {
          const cfg = DOMAINS[d]
          const active = selectedDomain === d
          return (
            <button key={d} onClick={() => setSelectedDomain(d)}
              style={{
                height: 26, padding: '0 12px', borderRadius: 99, border: '1px solid',
                borderColor: active ? (cfg?.hexStr ?? 'rgba(108,99,255,.4)') : 'var(--border2)',
                background:  active ? (cfg ? cfg.hexStr + '20' : 'rgba(108,99,255,.1)') : 'transparent',
                color:       active ? (cfg?.hexStr ?? 'var(--accent2)') : 'var(--text2)',
                fontSize: 12, fontWeight: active ? 600 : 400, cursor: 'pointer',
                fontFamily: 'var(--font)', whiteSpace: 'nowrap', transition: 'all .15s',
              }}>
              {d}
            </button>
          )
        })}
      </div>

      {/* ── Main area: canvas + detail panel ── */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* Three.js canvas */}
        <div ref={containerRef} style={{ flex: 1, position: 'relative', cursor: 'grab', overflow: 'hidden' }}>
          <canvas ref={canvasRef} style={{ display: 'block', width: '100%', height: '100%' }} />

          {/* Legend */}
          <div style={{
            position: 'absolute', bottom: 16, left: 16,
            display: 'flex', gap: 12, padding: '7px 12px',
            background: 'rgba(10,11,14,0.82)', borderRadius: 8,
            border: '1px solid var(--border2)', backdropFilter: 'blur(4px)',
          }}>
            {(['critical', 'high', 'medium', 'low'] as const).map(s => (
              <div key={s} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <div style={{ width: 8, height: 8, borderRadius: 2, background: SEV_LABEL_COLOR[s] }} />
                <span style={{ fontSize: 11, color: 'var(--text2)', textTransform: 'capitalize' }}>{s}</span>
              </div>
            ))}
          </div>

          {/* Hint */}
          <div style={{
            position: 'absolute', bottom: 16, right: selectedRisk ? 'calc(280px + 16px)' : 16,
            fontSize: 10, color: 'var(--text3)', background: 'rgba(10,11,14,0.7)',
            borderRadius: 6, padding: '5px 10px', border: '1px solid var(--border)',
            transition: 'right .25s',
          }}>
            Drag to orbit · Scroll to zoom · Click a peak
          </div>
        </div>

        {/* ── Risk detail panel ── */}
        <div style={{
          width: selectedRisk ? 288 : 0,
          flexShrink: 0,
          overflow: 'hidden',
          transition: 'width .22s ease',
          borderLeft: selectedRisk ? '1px solid var(--border)' : 'none',
          background: 'var(--bg1)',
        }}>
          {selectedRisk && domainCfg && (
            <div style={{ width: 288, padding: '20px 18px', overflowY: 'auto', height: '100%', boxSizing: 'border-box' }}>

              {/* Close */}
              <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
                <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--text3)' }}>
                  Risk Detail
                </div>
                <button onClick={() => setSelectedRisk(null)}
                  style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text3)', fontSize: 16, lineHeight: 1 }}>
                  ×
                </button>
              </div>

              {/* Domain chip */}
              <div style={{ fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 4, display: 'inline-block',
                background: domainCfg.hexStr + '20', color: domainCfg.hexStr, marginBottom: 10 }}>
                {normaliseDomain(selectedRisk.domain)}
              </div>

              {/* Name */}
              <h3 style={{ fontSize: 15, fontWeight: 400, color: 'var(--text)', lineHeight: 1.4, marginBottom: 14 }}>
                {selectedRisk.name}
              </h3>

              {/* Severity */}
              <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
                <div style={{ flex: 1, padding: '10px 12px', background: 'var(--bg2)', borderRadius: 8, border: '1px solid var(--border)' }}>
                  <div style={{ fontSize: 10, color: 'var(--text3)', marginBottom: 3 }}>Inherent</div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: SEV_LABEL_COLOR[selectedRisk.inherent_severity] }}>
                    {selectedRisk.inherent_severity.charAt(0).toUpperCase() + selectedRisk.inherent_severity.slice(1)}
                  </div>
                </div>
                <div style={{ flex: 1, padding: '10px 12px', background: 'var(--bg2)', borderRadius: 8, border: '1px solid var(--border)' }}>
                  <div style={{ fontSize: 10, color: 'var(--text3)', marginBottom: 3 }}>Residual</div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: SEV_LABEL_COLOR[selectedRisk.residual_severity] }}>
                    {selectedRisk.residual_severity.charAt(0).toUpperCase() + selectedRisk.residual_severity.slice(1)}
                  </div>
                </div>
              </div>

              {/* Likelihood / Impact bars */}
              {(['likelihood', 'impact'] as const).map(field => {
                const val = selectedRisk[field] as number
                return (
                  <div key={field} style={{ marginBottom: 12 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <span style={{ fontSize: 11, color: 'var(--text3)', textTransform: 'capitalize' }}>{field}</span>
                      <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text)' }}>{val}/5</span>
                    </div>
                    <div style={{ height: 4, background: 'var(--bg3)', borderRadius: 2 }}>
                      <div style={{ width: `${(val / 5) * 100}%`, height: '100%', borderRadius: 2, background: domainCfg.hexStr, transition: 'width .3s' }} />
                    </div>
                  </div>
                )
              })}

              {/* Control coverage */}
              <div style={{ marginBottom: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ fontSize: 11, color: 'var(--text3)' }}>Control coverage</span>
                  <span style={{ fontSize: 11, fontWeight: 600, color: (selectedRisk.control_coverage_pct ?? 0) === 0 ? 'var(--red)' : 'var(--teal)' }}>
                    {Math.round(selectedRisk.control_coverage_pct ?? 0)}%
                  </span>
                </div>
                <div style={{ height: 4, background: 'var(--bg3)', borderRadius: 2 }}>
                  <div style={{ width: `${selectedRisk.control_coverage_pct ?? 0}%`, height: '100%', borderRadius: 2, background: (selectedRisk.control_coverage_pct ?? 0) === 0 ? 'var(--red)' : 'var(--teal)', transition: 'width .3s' }} />
                </div>
                {(selectedRisk.control_coverage_pct ?? 0) === 0 && (
                  <div style={{ marginTop: 5, fontSize: 10, color: 'var(--amber)', display: 'flex', alignItems: 'center', gap: 4 }}>
                    <span>!</span> No controls linked — AI-flagged exposure
                  </div>
                )}
              </div>

              {/* Owner */}
              {selectedRisk.owner && (
                <div style={{ marginBottom: 14, padding: '9px 12px', background: 'var(--bg2)', borderRadius: 8, border: '1px solid var(--border)' }}>
                  <div style={{ fontSize: 10, color: 'var(--text3)', marginBottom: 2 }}>Owner</div>
                  <div style={{ fontSize: 12, color: 'var(--text)' }}>{selectedRisk.owner.full_name}</div>
                  <div style={{ fontSize: 10, color: 'var(--text3)' }}>{selectedRisk.owner.role?.replace('_', ' ')}</div>
                </div>
              )}

              {/* Description */}
              {selectedRisk.description && (
                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text3)', marginBottom: 5 }}>Description</div>
                  <p style={{ fontSize: 11, color: 'var(--text2)', lineHeight: 1.65 }}>{selectedRisk.description}</p>
                </div>
              )}

              {/* Framework tags */}
              {selectedRisk.framework_tags?.length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text3)', marginBottom: 6 }}>Frameworks</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                    {selectedRisk.framework_tags.map(tag => (
                      <span key={tag} style={{ fontSize: 10, padding: '2px 7px', borderRadius: 4, background: 'var(--bg3)', color: 'var(--text2)', border: '1px solid var(--border)' }}>{tag}</span>
                    ))}
                  </div>
                </div>
              )}

              {/* Actions */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
                <button
                  onClick={() => navigate('/controls')}
                  style={{ height: 32, borderRadius: 7, border: '1px solid rgba(108,99,255,.35)', background: 'rgba(108,99,255,.1)', color: 'var(--accent2)', fontSize: 12, fontWeight: 500, cursor: 'pointer', fontFamily: 'var(--font)' }}>
                  + Add control
                </button>
                <button
                  onClick={() => navigate('/canvas')}
                  style={{ height: 32, borderRadius: 7, border: '1px solid var(--border2)', background: 'transparent', color: 'var(--text2)', fontSize: 12, cursor: 'pointer', fontFamily: 'var(--font)' }}>
                  View on canvas →
                </button>
              </div>

            </div>
          )}

          {/* Empty state (panel closed placeholder — never actually shown since width=0) */}
          {!selectedRisk && (
            <div style={{ width: 288, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 10, color: 'var(--text3)' }}>
              <span style={{ fontSize: 28 }}>△</span>
              <div style={{ fontSize: 12, textAlign: 'center', padding: '0 20px' }}>Click a peak to drill into that risk</div>
            </div>
          )}
        </div>

      </div>
    </div>
  )
}
