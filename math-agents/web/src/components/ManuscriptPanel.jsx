import { useRef, useEffect } from 'react'
import katex from 'katex'

function renderMath(text) {
  if (!text) return []
  const parts = []
  let remaining = text
  let key = 0

  while (remaining.length > 0) {
    const dispIdx = remaining.indexOf('$$')
    const inlIdx = remaining.indexOf('$')

    if (dispIdx !== -1 && (inlIdx === -1 || dispIdx <= inlIdx)) {
      if (dispIdx > 0) {
        parts.push(<span key={key++}>{remaining.slice(0, dispIdx)}</span>)
      }
      const end = remaining.indexOf('$$', dispIdx + 2)
      if (end === -1) {
        parts.push(<span key={key++}>{remaining.slice(dispIdx)}</span>)
        break
      }
      const math = remaining.slice(dispIdx + 2, end)
      let html = ''
      try { html = katex.renderToString(math, { displayMode: true, throwOnError: false }) } catch {}
      parts.push(<span key={key++} dangerouslySetInnerHTML={{ __html: html }} />)
      remaining = remaining.slice(end + 2)
    } else if (inlIdx !== -1) {
      if (inlIdx > 0) {
        parts.push(<span key={key++}>{remaining.slice(0, inlIdx)}</span>)
      }
      const end = remaining.indexOf('$', inlIdx + 1)
      if (end === -1) {
        parts.push(<span key={key++}>{remaining.slice(inlIdx)}</span>)
        break
      }
      const math = remaining.slice(inlIdx + 1, end)
      let html = ''
      try { html = katex.renderToString(math, { displayMode: false, throwOnError: false }) } catch {}
      parts.push(<span key={key++} dangerouslySetInnerHTML={{ __html: html }} />)
      remaining = remaining.slice(end + 1)
    } else {
      parts.push(<span key={key++}>{remaining}</span>)
      break
    }
  }
  return parts
}

function ChunkView({ chunk, isFocus }) {
  const statusColor = {
    approved: '#5BAA8F',
    under_review: '#C9A84C',
    draft: '#7A6E5A',
    flagged: '#C96B6B',
  }[chunk.status] || '#7A6E5A'

  return (
    <div style={{
      marginBottom: 28,
      paddingBottom: 24,
      borderBottom: '1px solid #1a1810',
      opacity: isFocus ? 1 : 0.72,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <span style={{ color: '#7A6E5A', fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', fontFamily: 'var(--font-mono)' }}>
          {chunk.title}
        </span>
        <span style={{ width: 6, height: 6, borderRadius: '50%', background: statusColor, display: 'inline-block', flexShrink: 0 }} title={chunk.status} />
        {isFocus && (
          <span style={{ color: '#C9A84C', fontSize: 10, fontFamily: 'var(--font-mono)', letterSpacing: '0.1em' }}>FOCUS</span>
        )}
      </div>
      {chunk.content ? (
        <div style={{ color: '#D8CEBC', fontSize: 14.5, lineHeight: 1.9, fontFamily: 'var(--font-body)', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
          {renderMath(chunk.content)}
        </div>
      ) : (
        <div style={{ color: '#3a3020', fontSize: 13, fontStyle: 'italic' }}>No content yet…</div>
      )}
      {chunk.flags?.length > 0 && (
        <div style={{ marginTop: 10 }}>
          {chunk.flags.map((f, i) => (
            <div key={i} style={{ color: '#C96B6B', fontSize: 11, fontFamily: 'var(--font-mono)', marginTop: 4, paddingLeft: 8, borderLeft: '2px solid #C96B6B44' }}>
              ⚑ {f}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function ManuscriptPanel({ manuscript }) {
  const scrollRef = useRef(null)

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = 0
  }, [manuscript?.current_chunk_id])

  if (!manuscript) {
    return (
      <div style={{ flex: 1, overflow: 'auto', padding: '28px 24px' }}>
        <div style={{ color: '#3a3020', fontSize: 14, fontStyle: 'italic', lineHeight: 1.8 }}>
          The Rep will write the manuscript here…
        </div>
      </div>
    )
  }

  const { nodes, current_chunk_id } = manuscript

  return (
    <div ref={scrollRef} style={{ flex: 1, overflow: 'auto', padding: '28px 24px' }}>
      {(nodes || []).map(chunk => (
        <ChunkView
          key={chunk.id}
          chunk={chunk}
          isFocus={chunk.id === current_chunk_id}
        />
      ))}
    </div>
  )
}
