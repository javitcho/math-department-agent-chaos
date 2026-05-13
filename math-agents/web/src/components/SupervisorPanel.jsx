const STOP_META = {
  continue:          { color: '#7A6E5A', label: '· Continue'         },
  scout_interesting: { color: '#C9A84C', label: '⬡  Interesting'     },
  scout_pursue:      { color: '#5BAA8F', label: '✦  Pursue'          },
  scout_drop:        { color: '#9B4040', label: '⊘  Drop'            },
  serendipity:       { color: '#C9A84C', label: '✦  Serendipity'     },
  counterexample:    { color: '#C96B6B', label: '⊗  Counterexample'  },
  converged:         { color: '#5BAA8F', label: '◎  Converged'       },
  elegant:           { color: '#9B72C4', label: '◈  Elegant'         },
  incubate:          { color: '#5E8FB8', label: '⊞  Incubate'        },
  budget:            { color: '#666',    label: '⬡  Budget'          },
}

function SignalDot({ label, active, color }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 7 }}>
      <div style={{
        width: 7, height: 7, borderRadius: '50%',
        background: active ? color : '#252018',
        border: `1px solid ${active ? color : '#2e2820'}`,
        transition: 'all 0.3s',
        boxShadow: active ? `0 0 6px ${color}88` : 'none',
      }} />
      <span style={{ color: active ? color : '#3a3020', fontSize: 11, fontFamily: 'var(--font-mono)', letterSpacing: '0.06em', transition: 'color 0.3s' }}>
        {label}
      </span>
    </div>
  )
}

const STATUS_COLOR = {
  draft:        '#3a3020',
  under_review: '#C9A84C',
  approved:     '#5BAA8F',
  flagged:      '#C96B6B',
  needs_rework: '#C96B6B',
  abandoned:    '#2a2418',
}

const NODE_W = 88
const NODE_H = 18
const LEVEL_GAP = 36   // vertical spacing between rank levels
const COL_GAP = 10     // horizontal gap between nodes in same level

function DependencyGraph({ nodes, traversalOrder, currentId }) {
  if (!nodes || !nodes.length) return null

  const nodeMap = {}
  nodes.forEach(n => { nodeMap[n.id] = n })

  // Compute rank for each node (longest path from roots)
  const rank = {}
  const computeRank = (id) => {
    if (rank[id] !== undefined) return rank[id]
    const n = nodeMap[id]
    if (!n || !n.depends_on || n.depends_on.length === 0) { rank[id] = 0; return 0 }
    const r = Math.max(...n.depends_on.filter(d => nodeMap[d]).map(d => computeRank(d) + 1))
    rank[id] = r
    return r
  }
  ;(traversalOrder || []).forEach(id => computeRank(id))

  // Group by rank
  const levels = {}
  ;(traversalOrder || []).forEach(id => {
    const r = rank[id] ?? 0
    if (!levels[r]) levels[r] = []
    levels[r].push(id)
  })
  const maxRank = Math.max(...Object.keys(levels).map(Number))

  // Assign positions: rank → row (top to bottom), within rank → column (center)
  const pos = {}
  const containerW = 200

  for (let r = 0; r <= maxRank; r++) {
    const group = levels[r] || []
    const totalW = group.length * NODE_W + (group.length - 1) * COL_GAP
    const startX = (containerW - totalW) / 2
    group.forEach((id, i) => {
      pos[id] = {
        x: startX + i * (NODE_W + COL_GAP),
        y: r * (NODE_H + LEVEL_GAP) + 4,
      }
    })
  }

  const svgH = (maxRank + 1) * (NODE_H + LEVEL_GAP) + 12

  // Draw edges
  const edges = []
  ;(traversalOrder || []).forEach(id => {
    const n = nodeMap[id]
    if (!n) return
    ;(n.depends_on || []).forEach(depId => {
      if (!pos[depId] || !pos[id]) return
      const sx = pos[depId].x + NODE_W / 2
      const sy = pos[depId].y + NODE_H
      const tx = pos[id].x + NODE_W / 2
      const ty = pos[id].y
      const cy = (sy + ty) / 2
      edges.push(
        <path
          key={depId + '→' + id}
          d={"M " + sx + " " + sy + " C " + sx + " " + cy + ", " + tx + " " + cy + ", " + tx + " " + ty}
          stroke="#2e2820" strokeWidth={1.5} fill="none" markerEnd="url(#arr)"
        />
      )
    })
  })

  // Draw nodes
  const nodeEls = (traversalOrder || []).map(id => {
    const n = nodeMap[id]
    if (!n || !pos[id]) return null
    const color = STATUS_COLOR[n.status] || '#3a3020'
    const isCurrent = id === currentId
    const { x, y } = pos[id]
    const label = n.title.length > 13 ? n.title.slice(0, 12) + '…' : n.title
    return (
      <g key={id} style={{ cursor: 'default' }}>
        <title>{n.title} ({n.type}) — {n.status}{n.review_requested ? ' [re-review]' : ''}</title>
        <rect
          x={x} y={y} width={NODE_W} height={NODE_H} rx={3}
          fill={isCurrent ? color + '22' : '#13120f'}
          stroke={color}
          strokeWidth={isCurrent ? 1.5 : 1}
        />
        <text
          x={x + NODE_W / 2} y={y + NODE_H / 2 + 4}
          textAnchor="middle" fontSize={9}
          fontFamily="var(--font-mono)"
          fill={color}
        >
          {label}
        </text>
        {n.review_requested && (
          <circle cx={x + NODE_W - 4} cy={y + 4} r={3} fill="#C9A84C" />
        )}
      </g>
    )
  })

  return (
    <svg width={containerW} height={svgH} style={{ display: 'block', overflow: 'visible' }}>
      <defs>
        <marker id="arr" markerWidth={6} markerHeight={6} refX={6} refY={3} orient="auto">
          <path d="M0,0 L0,6 L6,3 Z" fill="#2e2820" />
        </marker>
      </defs>
      {edges}
      {nodeEls}
    </svg>
  )
}

function Section({ label, children }) {
  return (
    <div style={{ marginBottom: 22 }}>
      <div style={{ color: 'var(--muted)', fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', fontFamily: 'var(--font-mono)', marginBottom: 7 }}>
        {label}
      </div>
      {children}
    </div>
  )
}

export default function SupervisorPanel({ state, scope, scopeChange, nodes, traversalOrder, running, stopInfo, queuedNote, onStop, onContinue, onNewTopic, onExport }) {
  const signal = state?.stopping_signal?.toLowerCase() || 'continue'
  const meta = STOP_META[signal] || STOP_META.continue

  return (
    <div style={{ width: '25%', display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
      <div style={{ padding: '9px 18px', borderBottom: '1px solid var(--border)', color: 'var(--muted)', fontSize: 10, letterSpacing: '0.18em', textTransform: 'uppercase', fontFamily: 'var(--font-mono)', background: 'var(--bg3)' }}>
        Supervisor
      </div>

      <div style={{ flex: 1, overflow: 'auto', padding: 16 }}>

        {state?.round > 0 && (
          <Section label="Round">
            <div style={{ color: '#B8AD98', fontSize: 13, fontFamily: 'var(--font-mono)' }}>
              {state.round} — {state.mode}
            </div>
          </Section>
        )}

        {state?.current_chunk_title && (
          <Section label="Focus">
            <div style={{ color: '#B8AD98', fontSize: 13, lineHeight: 1.6 }}>
              {state.current_chunk_title}
            </div>
          </Section>
        )}

        {state?.established?.length > 0 && (
          <Section label="Established">
            {state.established.slice(0, 4).map((e, i) => (
              <div key={i} style={{ color: '#7A6E5A', fontSize: 12, marginBottom: 4, paddingLeft: 10, borderLeft: '2px solid #2a2418', lineHeight: 1.5 }}>
                {e}
              </div>
            ))}
          </Section>
        )}

        {state?.priority_issues?.length > 0 && (
          <Section label="Open Issues">
            {state.priority_issues.map((iss, i) => (
              <div key={i} style={{ color: '#7A6E5A', fontSize: 12, marginBottom: 5, paddingLeft: 10, borderLeft: '2px solid #2a2418', lineHeight: 1.5 }}>
                {iss}
              </div>
            ))}
          </Section>
        )}

        {state?.round_goal && (
          <Section label="Goal">
            <div style={{ color: '#7A6E5A', fontSize: 12, lineHeight: 1.75, fontStyle: 'italic' }}>
              {state.round_goal}
            </div>
          </Section>
        )}

        {stopInfo && (
          <div style={{
            background: '#13120f',
            border: `1px solid ${meta.color}44`,
            padding: 14, marginBottom: 20,
          }}>
            <div style={{ color: meta.color, fontSize: 12, marginBottom: 6, fontFamily: 'var(--font-mono)' }}>
              {meta.label}
            </div>
            <div style={{ color: 'var(--muted)', fontSize: 12, lineHeight: 1.6 }}>
              {stopInfo.reason}
            </div>
            {signal !== 'counterexample' && (
              <button
                onClick={onContinue}
                style={{ marginTop: 12, width: '100%', background: 'transparent', border: '1px solid #2a2418', color: 'var(--muted)', padding: '7px 0', fontSize: 11, fontFamily: 'var(--font-mono)' }}>
                Continue Anyway →
              </button>
            )}
          </div>
        )}

        {queuedNote && (
          <div style={{ marginBottom: 22, padding: '8px 12px', background: '#13120f', border: '1px solid #2a2418', color: 'var(--muted)', fontSize: 12, fontStyle: 'italic', lineHeight: 1.6 }}>
            ↳ Note queued: "{queuedNote}"
          </div>
        )}

        {scope && (
          <Section label="Scope">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
              {[
                ['purpose',  scope.purpose],
                ['audience', scope.audience],
                ['rigor',    scope.rigor],
              ].map(([k, v]) => v && (
                <div key={k} style={{ display: 'flex', gap: 6, fontSize: 11, fontFamily: 'var(--font-mono)' }}>
                  <span style={{ color: '#3a3020', minWidth: 56 }}>{k}</span>
                  <span style={{ color: '#7A6E5A' }}>{v}</span>
                </div>
              ))}
              {scope.tone_notes && (
                <div style={{ color: '#3a3020', fontSize: 11, marginTop: 2, fontStyle: 'italic', lineHeight: 1.5 }}>
                  {scope.tone_notes}
                </div>
              )}
            </div>
          </Section>
        )}

        {nodes && nodes.length > 0 && (
          <Section label="Dependency Graph">
            <div style={{ overflowX: 'auto' }}>
              <DependencyGraph
                nodes={nodes}
                traversalOrder={traversalOrder || nodes.map(n => n.id)}
                currentId={state?.current_chunk_id}
              />
            </div>
          </Section>
        )}

        {scopeChange && (
          <div style={{
            marginBottom: 16,
            padding: '8px 12px',
            background: '#13120f',
            border: '1px solid #C9A84C44',
            color: '#C9A84C',
            fontSize: 12,
            lineHeight: 1.6,
            fontFamily: 'var(--font-mono)',
            animation: 'fadeSlideIn 0.3s ease',
          }}>
            ✦ {scopeChange}
          </div>
        )}

        <Section label="Signals">
          {Object.entries(STOP_META).filter(([k]) => k !== 'continue').map(([k, v]) => (
            <SignalDot key={k} label={v.label} active={signal === k} color={v.color} />
          ))}
        </Section>

      </div>

      <div style={{ padding: '12px 14px', borderTop: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: 7, background: 'var(--bg3)' }}>
        <button
          onClick={onExport}
          style={{ background: 'transparent', border: '1px solid var(--border)', color: 'var(--muted)', padding: '8px 0', fontSize: 11, fontFamily: 'var(--font-mono)', letterSpacing: '0.08em' }}>
          Export md + tex
        </button>
        <button
          onClick={onStop}
          disabled={!running}
          style={{ background: 'transparent', border: '1px solid var(--border)', color: running ? 'var(--muted)' : 'var(--dim)', padding: '8px 0', fontSize: 11, fontFamily: 'var(--font-mono)', letterSpacing: '0.08em' }}>
          Stop Session
        </button>
        <button
          onClick={onNewTopic}
          style={{ background: 'transparent', border: '1px solid var(--border)', color: 'var(--dim)', padding: '8px 0', fontSize: 11, fontFamily: 'var(--font-mono)', letterSpacing: '0.08em' }}>
          New Topic
        </button>
      </div>
    </div>
  )
}
