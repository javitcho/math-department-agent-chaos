import { useState, useEffect, useRef, useCallback } from 'react'
import IntakeForm, { AGENTS } from './components/IntakeForm.jsx'
import SessionList from './components/SessionList.jsx'
import ManuscriptPanel from './components/ManuscriptPanel.jsx'
import AgentFeed from './components/AgentFeed.jsx'
import SupervisorPanel from './components/SupervisorPanel.jsx'
import { listSessions, startSession, getSession, resumeSession, exportSession, openEventStream, injectNote } from './api.js'

// ─── Constants ──────────────────────────────────────────────────────────────

const EMPTY_STATE = {
  round: 0,
  mode: 'scout',
  current_chunk_id: '',
  current_chunk_title: '',
  open_flags: [],
  round_goal: '',
  stopping_signal: 'continue',
  stopping_reason: '',
  priority_issues: [],
  scout_verdict: null,
  established: [],
}

// ─── Header ──────────────────────────────────────────────────────────────────

function Header({ topic, running, state }) {
  const signal = state?.stopping_signal?.toLowerCase() || 'continue'
  const COLORS = {
    serendipity: '#C9A84C', counterexample: '#C96B6B', converged: '#5BAA8F',
    elegant: '#9B72C4', scout_pursue: '#5BAA8F', scout_drop: '#9B4040',
    scout_interesting: '#C9A84C',
  }
  const signalColor = COLORS[signal]

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 16, padding: '0 20px',
      height: 46, borderBottom: '1px solid var(--border)', flexShrink: 0,
      background: 'var(--bg3)',
    }}>
      <span style={{ color: 'var(--gold)', fontSize: 11, letterSpacing: '0.16em', textTransform: 'uppercase', fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
        MR-System
      </span>
      <span style={{ color: 'var(--border)', fontSize: 14 }}>│</span>
      <span style={{ color: 'var(--muted)', fontSize: 13, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {topic || 'Mathematical Proof Workbench'}
      </span>
      {running && (
        <span style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#5BAA8F', fontSize: 12, fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
          <RunDots />
          {state?.round > 0 ? `Round ${state.round}` : 'Starting…'}
        </span>
      )}
      {!running && signalColor && signal !== 'continue' && (
        <span style={{
          color: signalColor, fontSize: 11,
          fontFamily: 'var(--font-mono)', letterSpacing: '0.08em',
          border: `1px solid ${signalColor}44`,
          padding: '2px 8px', flexShrink: 0,
        }}>
          {signal.replace(/_/g, ' ').toUpperCase()}
        </span>
      )}
    </div>
  )
}

function RunDots() {
  return (
    <span style={{ display: 'flex', gap: 3, alignItems: 'center' }}>
      {[0, 1, 2].map(i => (
        <span key={i} style={{
          width: 5, height: 5, borderRadius: '50%', background: '#5BAA8F',
          display: 'inline-block',
          animation: `mathPulse 1.4s ease-in-out ${i * 0.22}s infinite`,
        }} />
      ))}
    </span>
  )
}

// ─── Landing ─────────────────────────────────────────────────────────────────

function LandingScreen({ onStart, sessions }) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [showSessions, setShowSessions] = useState(false)

  async function handleStart(topic, mode, scope) {
    setLoading(true)
    setError('')
    try {
      const { session_id } = await startSession(topic, mode, scope)
      onStart(session_id, topic)
    } catch (e) {
      setError(e.message)
      setLoading(false)
    }
  }

  async function handleResume(session) {
    setLoading(true)
    setError('')
    try {
      await resumeSession(session.session_id)
      onStart(session.session_id, session.topic, true)
    } catch (e) {
      setError(e.message)
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh', background: 'var(--bg)',
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      padding: 40,
    }}>
      <div style={{ textAlign: 'center', marginBottom: 48, animation: 'fadeSlideIn 0.6s ease' }}>
        <div style={{ color: 'var(--gold)', fontSize: 11, letterSpacing: '0.22em', textTransform: 'uppercase', marginBottom: 20, fontFamily: 'var(--font-mono)' }}>
          Multi-Agent Mathematical Research System
        </div>
        <h1 style={{ color: 'var(--text)', fontSize: 32, fontWeight: 400, marginBottom: 14, lineHeight: 1.3 }}>
          Mathematical Proof Workbench
        </h1>
        <p style={{ color: 'var(--muted)', fontSize: 16, lineHeight: 1.8, maxWidth: 520 }}>
          Seven specialized agents work in concert — developing, critiquing, and refining mathematical explorations.
        </p>
      </div>

      <div style={{ display: 'flex', gap: 10, marginBottom: 44, flexWrap: 'wrap', justifyContent: 'center', maxWidth: 640, animation: 'fadeSlideIn 0.6s ease 0.1s both' }}>
        {Object.entries(AGENTS).map(([k, ag]) => (
          <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 6, background: '#13120f', border: '1px solid var(--border)', padding: '5px 10px' }}>
            <span style={{ color: ag.color, fontSize: 13 }}>{ag.sym}</span>
            <span style={{ color: 'var(--muted)', fontSize: 11, fontFamily: 'var(--font-mono)' }}>{ag.name}</span>
          </div>
        ))}
      </div>

      <IntakeForm onStart={handleStart} loading={loading} />

      {error && (
        <div style={{ marginTop: 14, color: '#C96B6B', fontSize: 13, maxWidth: 560, textAlign: 'center' }}>
          {error}
        </div>
      )}

      {sessions.length > 0 && (
        <div style={{ marginTop: 40, width: '100%', maxWidth: 560, animation: 'fadeSlideIn 0.6s ease 0.3s both' }}>
          <button
            onClick={() => setShowSessions(s => !s)}
            style={{
              background: 'transparent', border: 'none', color: 'var(--dim)',
              fontSize: 12, fontFamily: 'var(--font-mono)', letterSpacing: '0.1em',
              textTransform: 'uppercase', marginBottom: 12, padding: 0,
            }}>
            {showSessions ? '▲' : '▼'} Previous sessions ({sessions.length})
          </button>
          {showSessions && <SessionList sessions={sessions} onResume={handleResume} />}
        </div>
      )}
    </div>
  )
}

// ─── Workspace ───────────────────────────────────────────────────────────────

function WorkspaceScreen({ sessionId, topic, onNewTopic }) {
  const [manuscript, setManuscript] = useState(null)
  const [state, setState] = useState(EMPTY_STATE)
  const [log, setLog] = useState([])
  const [activeAgent, setActiveAgent] = useState(null)
  const [running, setRunning] = useState(true)
  const [stopInfo, setStopInfo] = useState(null)
  const [userNote, setUserNote] = useState('')
  const [queuedNote, setQueuedNote] = useState('')
  const [scope, setScope] = useState(null)
  const [scopeChange, setScopeChange] = useState('')
  const [exportMsg, setExportMsg] = useState('')
  const closeStreamRef = useRef(null)

  useEffect(() => {
    closeStreamRef.current = openEventStream(sessionId, handleEvent)
    return () => closeStreamRef.current?.()
  }, [sessionId])

  function handleEvent(ev) {
    if (ev.type === 'ping' || ev.type === 'stream_closed') return

    if (ev.type === 'update') {
      if (ev.manuscript) setManuscript(ev.manuscript)
      if (ev.state) setState(ev.state)
      if (ev.agent) {
        setActiveAgent(null)
        setLog(prev => [...prev, {
          agent: ev.agent,
          round: ev.round || 0,
          note: ev.note || '',
          status: 'complete',
        }])
        // Show next agent as thinking (rough heuristic)
        const ORDER = ['decomposer', 'orchestrator', 'rep', 'logic_critic', 'counterex', 'reference', 'elegance', 'orchestrator']
        const idx = ORDER.indexOf(ev.agent)
        if (idx !== -1 && idx + 1 < ORDER.length) {
          setActiveAgent(ORDER[idx + 1])
        }
      }
    }

    if (ev.type === 'scope_changed') {
      if (ev.scope) setScope(ev.scope)
      if (ev.confirmation) {
        setScopeChange(ev.confirmation)
        setTimeout(() => setScopeChange(''), 4000)
      }
      return
    }

    if (ev.type === 'note_queued') {
      setQueuedNote(ev.note || '')
      return
    }

    if (ev.type === 'done') {
      setRunning(false)
      setActiveAgent(null)
      const result = ev.result || {}
      if (result.verdict || result.exit_reason) {
        setStopInfo({
          signal: result.verdict?.toLowerCase() || result.exit_reason || 'complete',
          reason: result.scout_reason || result.exit_reason || 'Session complete.',
        })
      }
      // Refresh final state from server
      getSession(sessionId).then(d => {
        setManuscript(d.manuscript)
        setState(d.state)
      }).catch(() => {})
    }

    if (ev.type === 'error') {
      setRunning(false)
      setActiveAgent(null)
      setStopInfo({ signal: 'error', reason: ev.message })
    }
  }

  function handleNoteSubmit() {
    const trimmed = userNote.trim()
    if (!trimmed) return
    setUserNote('')
    injectNote(sessionId, trimmed).catch(() => {
      // Fallback: queue locally if server unreachable
      setQueuedNote(trimmed)
    })
  }

  function handleContinue() {
    setStopInfo(null)
    setRunning(true)
    const note = queuedNote || undefined
    setQueuedNote('')
    resumeSession(sessionId, note)
      .then(() => {
        closeStreamRef.current?.()
        closeStreamRef.current = openEventStream(sessionId, handleEvent)
      })
      .catch(e => setStopInfo({ signal: 'error', reason: e.message }))
  }

  function handleStop() {
    fetch(`/session/${sessionId}/stop`, { method: 'POST' }).catch(() => {})
    setRunning(false)
    setActiveAgent(null)
  }

  async function handleExport() {
    try {
      const result = await exportSession(sessionId)
      setExportMsg(`Exported: ${result.markdown.split('/').pop()} + ${result.latex.split('/').pop()}`)
      setTimeout(() => setExportMsg(''), 5000)
    } catch (e) {
      setExportMsg(`Export failed: ${e.message}`)
    }
  }

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Header topic={topic} running={running} state={state} />

      {exportMsg && (
        <div style={{ background: '#13120f', borderBottom: '1px solid #201e18', padding: '6px 20px', color: '#5BAA8F', fontSize: 12, fontFamily: 'var(--font-mono)' }}>
          {exportMsg}
        </div>
      )}

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <div style={{ width: '37%', borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
          <div style={{ padding: '9px 18px', borderBottom: '1px solid var(--border)', color: 'var(--muted)', fontSize: 10, letterSpacing: '0.18em', textTransform: 'uppercase', fontFamily: 'var(--font-mono)', background: 'var(--bg3)', flexShrink: 0 }}>
            Manuscript
          </div>
          <ManuscriptPanel manuscript={manuscript} />
        </div>

        <AgentFeed
          log={log}
          activeAgent={activeAgent}
          userNote={userNote}
          onNoteChange={setUserNote}
          onNoteSubmit={handleNoteSubmit}
        />

        <SupervisorPanel
          state={state}
          scope={scope}
          scopeChange={scopeChange}
          running={running}
          stopInfo={stopInfo}
          queuedNote={queuedNote}
          onStop={handleStop}
          onContinue={handleContinue}
          onNewTopic={onNewTopic}
          onExport={handleExport}
        />
      </div>
    </div>
  )
}

// ─── Root ────────────────────────────────────────────────────────────────────

export default function App() {
  const [screen, setScreen] = useState('landing')
  const [sessionId, setSessionId] = useState(null)
  const [topic, setTopic] = useState('')
  const [sessions, setSessions] = useState([])

  useEffect(() => {
    listSessions().then(setSessions).catch(() => {})
  }, [])

  function handleStart(id, t) {
    setSessionId(id)
    setTopic(t)
    setScreen('workspace')
  }

  function handleNewTopic() {
    listSessions().then(setSessions).catch(() => {})
    setScreen('landing')
    setSessionId(null)
    setTopic('')
  }

  if (screen === 'workspace' && sessionId) {
    return (
      <WorkspaceScreen
        sessionId={sessionId}
        topic={topic}
        onNewTopic={handleNewTopic}
      />
    )
  }

  return <LandingScreen onStart={handleStart} sessions={sessions} />
}
