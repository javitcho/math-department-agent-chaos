import { useState } from 'react'

const AGENTS = {
  orchestrator: { name: 'Orchestrator',          sym: '◎', color: '#C9A84C' },
  decomposer:   { name: 'Decomposer',            sym: '⬡', color: '#C49060' },
  rep:          { name: 'The Rep',               sym: '✦', color: '#5BAA8F' },
  logic_critic: { name: 'Logic Critic',          sym: '⊗', color: '#C96B6B' },
  counterex:    { name: 'Counterexample Hunter', sym: '⊘', color: '#9B4040' },
  reference:    { name: 'Reference Critic',      sym: '⊞', color: '#5E8FB8' },
  elegance:     { name: 'Elegance Critic',       sym: '◈', color: '#9B72C4' },
}

function ThinkingDots({ color }) {
  return (
    <span style={{ display: 'flex', gap: 3, alignItems: 'center' }}>
      {[0, 1, 2].map(i => (
        <span key={i} style={{
          width: 5, height: 5, borderRadius: '50%', background: color,
          display: 'inline-block',
          animation: `mathPulse 1.4s ease-in-out ${i * 0.22}s infinite`,
        }} />
      ))}
    </span>
  )
}

export default function AgentCard({ agent, round, note, status }) {
  const [expanded, setExpanded] = useState(false)
  const ag = AGENTS[agent] || { name: agent, sym: '·', color: '#7A6E5A' }
  const thinking = status === 'thinking'

  return (
    <div
      onClick={() => !thinking && setExpanded(e => !e)}
      style={{
        borderLeft: `3px solid ${ag.color}`,
        background: '#13120f',
        border: `1px solid #252018`,
        borderLeftColor: ag.color,
        borderLeftWidth: 3,
        cursor: thinking ? 'default' : 'pointer',
        animation: 'fadeSlideIn 0.25s ease',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '9px 13px' }}>
        <span style={{ color: ag.color, fontSize: 15, lineHeight: 1 }}>{ag.sym}</span>
        <span style={{ color: '#D0C4AF', fontSize: 12, fontFamily: 'var(--font-sans)', fontWeight: 600, letterSpacing: '0.04em' }}>
          {ag.name}
        </span>
        {round > 0 && (
          <span style={{ color: '#4a4030', fontSize: 11, fontFamily: 'var(--font-mono)' }}>R{round}</span>
        )}
        <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
          {thinking
            ? <ThinkingDots color={ag.color} />
            : <span style={{ color: '#3a3020', fontSize: 11 }}>{expanded ? '▲' : '▼'}</span>
          }
        </span>
      </div>
      {expanded && !thinking && note && (
        <div style={{
          padding: '10px 14px 14px',
          borderTop: '1px solid #1e1c16',
          color: '#9A8F7A',
          fontSize: 12,
          lineHeight: 1.75,
          fontFamily: 'var(--font-body)',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
        }}>
          {note}
        </div>
      )}
    </div>
  )
}

export { ThinkingDots, AGENTS }
