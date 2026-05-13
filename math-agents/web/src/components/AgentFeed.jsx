import { useRef, useEffect } from 'react'
import AgentCard from './AgentCard.jsx'

export default function AgentFeed({ log, activeAgent, userNote, onNoteChange, onNoteSubmit }) {
  const feedRef = useRef(null)

  useEffect(() => {
    if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight
  }, [log])

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', borderRight: '1px solid var(--border)', minWidth: 0 }}>
      <div style={{ padding: '9px 18px', borderBottom: '1px solid var(--border)', color: 'var(--muted)', fontSize: 10, letterSpacing: '0.18em', textTransform: 'uppercase', fontFamily: 'var(--font-mono)', background: 'var(--bg3)', flexShrink: 0 }}>
        Agent Activity
      </div>

      <div ref={feedRef} style={{ flex: 1, overflow: 'auto', padding: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {log.length === 0 && !activeAgent && (
          <div style={{ color: 'var(--dim)', fontSize: 13, padding: 12, fontStyle: 'italic' }}>
            Activity will appear here…
          </div>
        )}
        {log.map((entry, i) => (
          <AgentCard key={i} {...entry} />
        ))}
        {activeAgent && (
          <AgentCard agent={activeAgent} round={0} note="" status="thinking" />
        )}
      </div>

      <div style={{ borderTop: '1px solid var(--border)', padding: '10px 12px', display: 'flex', gap: 8, flexShrink: 0, background: 'var(--bg3)' }}>
        <input
          value={userNote}
          onChange={e => onNoteChange(e.target.value)}
          placeholder="Interject a note for the Rep on the next round…"
          onKeyDown={e => { if (e.key === 'Enter') onNoteSubmit() }}
          style={{
            flex: 1, background: '#13120f', border: '1px solid var(--border)',
            color: 'var(--text)', padding: '7px 11px', fontSize: 13,
          }}
        />
        <button
          onClick={onNoteSubmit}
          style={{
            background: 'transparent', border: '1px solid var(--border)', color: 'var(--muted)',
            padding: '7px 14px', fontSize: 11, fontFamily: 'var(--font-mono)', letterSpacing: '0.06em',
          }}>
          Queue
        </button>
      </div>
    </div>
  )
}
