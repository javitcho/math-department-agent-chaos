const BASE = ''  // Vite proxy forwards /session* → localhost:5000

export async function listSessions() {
  const r = await fetch(`${BASE}/sessions`)
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

export async function startSession(topic, mode, scope = {}) {
  const r = await fetch(`${BASE}/session/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic, mode, ...scope }),
  })
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

export async function getSession(id) {
  const r = await fetch(`${BASE}/session/${id}`)
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

export async function resumeSession(id, note = null) {
  const r = await fetch(`${BASE}/session/${id}/resume`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note }),
  })
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

export async function exportSession(id) {
  const r = await fetch(`${BASE}/session/${id}/export`, { method: 'POST' })
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

export async function injectNote(id, note) {
  const r = await fetch(`${BASE}/session/${id}/note`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note }),
  })
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

export function openEventStream(id, onEvent) {
  const es = new EventSource(`${BASE}/session/${id}/events`)
  es.onmessage = (e) => {
    try {
      onEvent(JSON.parse(e.data))
    } catch {}
  }
  es.onerror = () => {
    es.close()
    onEvent({ type: 'stream_closed' })
  }
  return () => es.close()
}
