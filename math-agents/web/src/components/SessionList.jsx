const MODE_COLORS = {
  scout: '#C49060',
  deep: '#5BAA8F',
}

function truncate(str, n) {
  return str && str.length > n ? str.slice(0, n) + '…' : str
}

function reltime(iso) {
  if (!iso || iso === 'unknown') return ''
  try {
    const diff = Date.now() - new Date(iso).getTime()
    const m = Math.floor(diff / 60000)
    if (m < 1) return 'just now'
    if (m < 60) return `${m}m ago`
    const h = Math.floor(m / 60)
    if (h < 24) return `${h}h ago`
    return `${Math.floor(h / 24)}d ago`
  } catch { return '' }
}

export default function SessionList({ sessions, onResume }) {
  if (!sessions.length) {
    return (
      <div style={{ color: '#3a3020', fontSize: 13, fontStyle: 'italic', textAlign: 'center', padding: '20px 0' }}>
        No previous sessions.
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {sessions.map(s => (
        <div
          key={s.session_id}
          onClick={() => onResume(s)}
          style={{
            background: '#13120f',
            border: '1px solid #201e18',
            padding: '10px 14px',
            cursor: 'pointer',
            transition: 'border-color 0.15s',
          }}
          onMouseEnter={e => e.currentTarget.style.borderColor = '#3a3020'}
          onMouseLeave={e => e.currentTarget.style.borderColor = '#201e18'}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
            <span style={{ color: MODE_COLORS[s.mode] || '#7A6E5A', fontSize: 10, fontFamily: 'var(--font-mono)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
              {s.mode}
            </span>
            <span style={{ color: '#2e2820', fontSize: 11 }}>·</span>
            <span style={{ color: '#3a3020', fontSize: 11, fontFamily: 'var(--font-mono)' }}>
              {s.session_id}
            </span>
            <span style={{ marginLeft: 'auto', color: '#3a3020', fontSize: 11, fontFamily: 'var(--font-mono)' }}>
              {reltime(s.saved_at)}
            </span>
          </div>
          <div style={{ color: '#B8AD98', fontSize: 13.5, lineHeight: 1.5 }}>
            {truncate(s.topic, 72)}
          </div>
          <div style={{ color: '#3a3020', fontSize: 11, fontFamily: 'var(--font-mono)', marginTop: 4 }}>
            {s.chunk_count} chunk{s.chunk_count !== 1 ? 's' : ''}
          </div>
        </div>
      ))}
    </div>
  )
}
