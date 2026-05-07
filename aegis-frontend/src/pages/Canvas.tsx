import React, { useEffect, useRef, useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { canvasApi } from '@/api/client'
import { Spinner, EmptyState, Button } from '@/components/ui'
import type { CanvasNode, CanvasEdge, NodeType } from '@/types'

const NODE_COLORS: Record<NodeType, { bg: string; border: string; text: string }> = {
  risk:    { bg: 'rgba(224,82,82,.12)',    border: 'rgba(224,82,82,.4)',    text: '#f08080' },
  control: { bg: 'rgba(30,185,138,.12)',   border: 'rgba(30,185,138,.4)',   text: '#25d9a3' },
  process: { bg: 'rgba(108,99,255,.12)',   border: 'rgba(108,99,255,.4)',   text: '#8b85ff' },
  evidence:{ bg: 'rgba(232,168,56,.12)',   border: 'rgba(232,168,56,.4)',   text: '#f5c06a' },
}

export const CanvasPage: React.FC = () => {
  const qc = useQueryClient()
  const svgRef = useRef<SVGSVGElement>(null)
  const [selected, setSelected] = useState<CanvasNode | null>(null)
  const [aiOverlay, setAiOverlay] = useState(true)
  const [zoom, setZoom] = useState(100)
  const [dragging, setDragging] = useState<{ id: string; ox: number; oy: number } | null>(null)
  const [nodes, setNodes] = useState<CanvasNode[]>([])
  const [edges, setEdges] = useState<CanvasEdge[]>([])

  const { data, isLoading } = useQuery({
    queryKey: ['canvas'],
    queryFn: canvasApi.get,
  })

  useEffect(() => {
    if (data) {
      setNodes(data.nodes)
      setEdges(data.edges)
    }
  }, [data])

  const updateNode = useMutation({
    mutationFn: ({ id, pos_x, pos_y }: { id: string; pos_x: number; pos_y: number }) =>
      canvasApi.updateNode(id, { pos_x, pos_y }),
  })

  const getNodeLabel = (node: CanvasNode) => {
    if (node.risk) return node.risk.name
    if (node.control) return node.control.name
    return node.label ?? node.node_type
  }

  const getEdgeColor = (type: string) => {
    const colors: Record<string, string> = {
      mitigates: 'rgba(30,185,138,.5)',
      partially_mitigates: 'rgba(232,168,56,.5)',
      evidences: 'rgba(232,168,56,.5)',
      generates: 'rgba(108,99,255,.5)',
    }
    return colors[type] ?? 'rgba(255,255,255,.2)'
  }

  const getNodeById = (id: string) => nodes.find(n => n.id === id)

  const handleMouseDown = useCallback((e: React.MouseEvent, nodeId: string) => {
    e.stopPropagation()
    const node = nodes.find(n => n.id === nodeId)
    if (!node) return
    setDragging({ id: nodeId, ox: e.clientX - node.pos_x, oy: e.clientY - node.pos_y })
    setSelected(node)
  }, [nodes])

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragging) return
    const newX = e.clientX - dragging.ox
    const newY = e.clientY - dragging.oy
    setNodes(prev => prev.map(n => n.id === dragging.id ? { ...n, pos_x: newX, pos_y: newY } : n))
  }, [dragging])

  const handleMouseUp = useCallback(() => {
    if (!dragging) return
    const node = nodes.find(n => n.id === dragging.id)
    if (node) updateNode.mutate({ id: node.id, pos_x: node.pos_x, pos_y: node.pos_y })
    setDragging(null)
  }, [dragging, nodes])

  if (isLoading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
      <Spinner size={24} />
    </div>
  )

  const NODE_W = 140
  const NODE_H = 70

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Toolbar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 16px', borderBottom: '1px solid var(--border)', background: 'var(--bg1)', flexShrink: 0 }}>
        <span style={{ fontSize: 12, color: 'var(--text2)' }}>Control Canvas</span>
        <div style={{ width: 1, height: 18, background: 'var(--border)', margin: '0 4px' }} />
        {(['risk','control','evidence'] as NodeType[]).map(t => (
          <button key={t} style={{ fontSize: 11, fontWeight: 500, padding: '3px 9px', borderRadius: 99, border: `1px solid ${NODE_COLORS[t].border}`, color: NODE_COLORS[t].text, background: NODE_COLORS[t].bg, cursor: 'pointer', fontFamily: 'var(--font)' }}>
            {t[0].toUpperCase()}+
          </button>
        ))}
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            onClick={() => setAiOverlay(v => !v)}
            style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, fontWeight: 500, padding: '4px 10px', borderRadius: 99, border: `1px solid ${aiOverlay ? 'rgba(108,99,255,.4)' : 'var(--border2)'}`, background: aiOverlay ? 'rgba(108,99,255,.2)' : 'none', color: aiOverlay ? 'var(--accent2)' : 'var(--text2)', cursor: 'pointer', fontFamily: 'var(--font)' }}
          >
            <div style={{ width: 5, height: 5, borderRadius: '50%', background: aiOverlay ? 'var(--accent2)' : 'var(--text3)', animation: aiOverlay ? 'pulse 2s infinite' : 'none' }} />
            AI overlay
          </button>
          <div style={{ display: 'flex', alignItems: 'center', background: 'var(--bg1)', border: '1px solid var(--border2)', borderRadius: 6, overflow: 'hidden' }}>
            <button onClick={() => setZoom(z => Math.max(40, z - 10))} style={{ width: 28, height: 26, border: 'none', background: 'none', color: 'var(--text2)', cursor: 'pointer', fontSize: 14, fontFamily: 'var(--font)' }}>−</button>
            <span style={{ fontSize: 11, fontWeight: 500, padding: '0 6px', color: 'var(--text)', borderLeft: '1px solid var(--border)', borderRight: '1px solid var(--border)' }}>{zoom}%</span>
            <button onClick={() => setZoom(z => Math.min(150, z + 10))} style={{ width: 28, height: 26, border: 'none', background: 'none', color: 'var(--text2)', cursor: 'pointer', fontSize: 14, fontFamily: 'var(--font)' }}>+</button>
          </div>
        </div>
      </div>

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Canvas */}
        <div
          style={{ flex: 1, position: 'relative', overflow: 'hidden', background: 'var(--bg)', cursor: dragging ? 'grabbing' : 'grab' }}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
        >
          {/* Dot grid */}
          <svg style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}>
            <defs>
              <pattern id="dot-grid" width="24" height="24" patternUnits="userSpaceOnUse">
                <circle cx="1" cy="1" r="0.8" fill="rgba(255,255,255,.06)" />
              </pattern>
            </defs>
            <rect width="100%" height="100%" fill="url(#dot-grid)" />
          </svg>

          <div style={{ position: 'absolute', inset: 0, transformOrigin: '0 0', transform: `scale(${zoom/100})` }}>
            {/* SVG edges */}
            <svg style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none', overflow: 'visible' }} ref={svgRef}>
              <defs>
                {['green','amber','purple'].map(c => (
                  <marker key={c} id={`arr-${c}`} markerWidth="7" markerHeight="7" refX="5" refY="3" orient="auto">
                    <path d="M0,0 L0,6 L7,3 z" fill={c === 'green' ? 'rgba(30,185,138,.6)' : c === 'amber' ? 'rgba(232,168,56,.6)' : 'rgba(108,99,255,.6)'} />
                  </marker>
                ))}
              </defs>
              {edges.map(edge => {
                const from = getNodeById(edge.from_node_id)
                const to = getNodeById(edge.to_node_id)
                if (!from || !to) return null
                const x1 = from.pos_x + NODE_W
                const y1 = from.pos_y + NODE_H / 2
                const x2 = to.pos_x
                const y2 = to.pos_y + NODE_H / 2
                const mx = (x1 + x2) / 2
                const color = getEdgeColor(edge.edge_type)
                const markerKey = edge.edge_type === 'generates' ? 'purple' : edge.edge_type === 'evidences' ? 'amber' : 'green'
                return (
                  <path key={edge.id}
                    d={`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`}
                    stroke={color} strokeWidth="1.5" fill="none"
                    markerEnd={`url(#arr-${markerKey})`}
                  />
                )
              })}
            </svg>

            {/* Nodes */}
            {nodes.map(node => {
              const c = NODE_COLORS[node.node_type]
              const label = getNodeLabel(node)
              const isSelected = selected?.id === node.id
              const isOrphan = node.is_orphan
              return (
                <div key={node.id}
                  onMouseDown={e => handleMouseDown(e, node.id)}
                  style={{
                    position: 'absolute',
                    left: node.pos_x, top: node.pos_y,
                    width: NODE_W, minHeight: NODE_H,
                    background: c.bg,
                    border: `${isOrphan ? '1.5px dashed' : '1px solid'} ${isSelected ? 'var(--accent2)' : c.border}`,
                    borderRadius: 10,
                    cursor: 'grab',
                    userSelect: 'none',
                    transition: 'box-shadow 0.12s',
                    boxShadow: isSelected ? `0 0 0 2px var(--accent2)` : 'none',
                  }}
                >
                  <div style={{ padding: '7px 10px 4px', display: 'flex', alignItems: 'flex-start', gap: 5 }}>
                    <div style={{ flex: 1, fontSize: 11, fontWeight: 500, color: c.text, lineHeight: 1.3 }}>
                      {label.length > 35 ? label.slice(0, 35) + '…' : label}
                    </div>
                  </div>
                  <div style={{ padding: '0 10px 8px', display: 'flex', gap: 3, flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 9, fontWeight: 500, padding: '1px 5px', borderRadius: 99, background: c.bg, color: c.text, border: `1px solid ${c.border}` }}>
                      {node.node_type}
                    </span>
                    {isOrphan && aiOverlay && <span style={{ fontSize: 9, fontWeight: 500, padding: '1px 5px', borderRadius: 99, background: 'rgba(232,168,56,.15)', color: 'var(--amber)', border: '1px solid rgba(232,168,56,.3)' }}>orphan</span>}
                  </div>
                </div>
              )
            })}

            {/* AI callouts */}
            {aiOverlay && nodes.filter(n => n.ai_gap_flag).map(node => (
              <div key={`ai-${node.id}`} style={{
                position: 'absolute',
                left: node.pos_x,
                top: node.pos_y + NODE_H + 8,
                width: 150,
                background: 'rgba(108,99,255,.12)',
                border: '1px solid rgba(108,99,255,.35)',
                borderRadius: 8,
                padding: '6px 9px',
                pointerEvents: 'none',
                fontSize: 10,
                color: 'var(--accent2)',
                lineHeight: 1.4,
              }}>
                <div style={{ fontSize: 9, fontWeight: 500, marginBottom: 2, display: 'flex', alignItems: 'center', gap: 3 }}>
                  <div style={{ width: 4, height: 4, borderRadius: '50%', background: 'var(--accent2)', animation: 'pulse 2s infinite' }} />
                  AI detected
                </div>
                {node.ai_gap_flag}
              </div>
            ))}
          </div>

          {nodes.length === 0 && (
            <EmptyState title="Canvas is empty" body="Risks and controls appear here after AI fingerprinting" />
          )}
        </div>

        {/* Inspector panel */}
        <div style={{ width: 220, flexShrink: 0, borderLeft: '1px solid var(--border)', background: 'var(--bg1)', overflowY: 'auto', padding: 14 }}>
          {!selected
            ? <div style={{ color: 'var(--text3)', fontSize: 12, textAlign: 'center', paddingTop: 40 }}>Click a node to inspect</div>
            : (
              <div className="animate-fade">
                <div style={{ fontSize: 10, fontWeight: 500, letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--text3)', marginBottom: 4 }}>Node</div>
                <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text)', marginBottom: 10 }}>{getNodeLabel(selected)}</div>
                <div style={{ fontSize: 10, fontWeight: 500, letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--text3)', marginBottom: 5 }}>Type</div>
                <div style={{ marginBottom: 12 }}>
                  <span style={{ fontSize: 11, fontWeight: 500, padding: '2px 7px', borderRadius: 99, background: NODE_COLORS[selected.node_type].bg, color: NODE_COLORS[selected.node_type].text }}>
                    {selected.node_type}
                  </span>
                </div>
                {selected.is_orphan && (
                  <div style={{ background: 'rgba(232,168,56,.1)', border: '1px solid rgba(232,168,56,.25)', borderRadius: 8, padding: '8px 10px', fontSize: 11, color: 'var(--amber)', marginBottom: 10 }}>
                    ⚠ No connections — this node is isolated
                  </div>
                )}
                {selected.ai_gap_flag && (
                  <div style={{ background: 'rgba(108,99,255,.08)', border: '1px solid rgba(108,99,255,.2)', borderRadius: 8, padding: '8px 10px', marginBottom: 10 }}>
                    <div style={{ fontSize: 10, fontWeight: 500, color: 'var(--accent2)', marginBottom: 3 }}>AI flag</div>
                    <div style={{ fontSize: 11, color: 'rgba(232,234,240,.8)', lineHeight: 1.4 }}>{selected.ai_gap_flag}</div>
                  </div>
                )}
                <Button variant="danger" size="sm" style={{ width: '100%' }} onClick={() => {
                  canvasApi.deleteNode(selected.id).then(() => {
                    setNodes(prev => prev.filter(n => n.id !== selected.id))
                    setEdges(prev => prev.filter(e => e.from_node_id !== selected.id && e.to_node_id !== selected.id))
                    setSelected(null)
                  })
                }}>Remove node</Button>
              </div>
            )
          }
        </div>
      </div>
    </div>
  )
}
