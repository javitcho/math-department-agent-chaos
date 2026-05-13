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

function Select({ label, value, onChange, options }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      <div style={{ color: 'var(--muted)', fontSize: 11, fontFamily: 'var(--font-mono)', letterSpacing: '0.08em' }}>
        {label}
      </div>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        style={{
          background: '#13120f', border: '1px solid #2a2418', color: 'var(--text)',
          padding: '6px 10px', fontSize: 13, fontFamily: 'var(--font-body)',
          appearance: 'none', cursor: 'pointer',
        }}
      >
        {options.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  )
}

export default function IntakeForm({ onStart, loading }) {
  const [topic, setTopic] = useState('')
  const [mode, setMode] = useState('scout')
  const [showScope, setShowScope] = useState(false)
  const [purpose, setPurpose] = useState('exploration')
  const [audience, setAudience] = useState('self')
  const [rigor, setRigor] = useState('sketch')

  const handleStart = () => {
    if (!topic.trim()) return
    onStart(topic.trim(), mode, { purpose, audience, rigor })
  }

  return (
    <div style={{ width: '100%', maxWidth: 560, animation: 'fadeSlideIn 0.6s ease 0.2s both' }}>
      <div style={{ color: 'var(--muted)', fontSize: 12, marginBottom: 8, fontFamily: 'var(--font-mono)', letterSpacing: '0.08em' }}>
        TOPIC OR THEOREM
      </div>
      <textarea
        value={topic}
        onChange={e => setTopic(e.target.value)}
        rows={3}
        placeholder="e.g. prove that √2 is irrational"
        style={{
          width: '100%', background: '#13120f',
          border: '1px solid #2a2418', color: 'var(--text)',
          padding: '14px 16px', fontSize: 15,
          lineHeight: 1.7, resize: 'vertical',
        }}
      />

      <div style={{ display: 'flex', gap: 10, marginTop: 12, alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: 0, flex: 1 }}>
          {['scout', 'deep'].map(m => (
            <button
              key={m}
              onClick={() => setMode(m)}
              style={{
                flex: 1,
                background: mode === m ? '#1a1810' : 'transparent',
                border: `1px solid ${mode === m ? '#3a3020' : '#201e18'}`,
                color: mode === m ? 'var(--gold)' : 'var(--dim)',
                padding: '8px 0', fontSize: 12,
                fontFamily: 'var(--font-mono)', letterSpacing: '0.06em',
              }}>
              {m}
            </button>
          ))}
        </div>
        <button
          onClick={() => setShowScope(s => !s)}
          style={{
            background: 'transparent', border: '1px solid #201e18', color: 'var(--dim)',
            padding: '8px 14px', fontSize: 11, fontFamily: 'var(--font-mono)', letterSpacing: '0.06em',
          }}>
          scope {showScope ? '▲' : '▼'}
        </button>
      </div>

      {showScope && (
        <div style={{ marginTop: 12, display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, padding: '14px 16px', background: '#13120f', border: '1px solid #201e18', animation: 'fadeSlideIn 0.2s ease' }}>
          <Select
            label="PURPOSE"
            value={purpose}
            onChange={setPurpose}
            options={[
              { value: 'exploration', label: 'Exploration' },
              { value: 'paper',       label: 'Paper'       },
              { value: 'thesis',      label: 'Thesis'      },
              { value: 'lecture_notes', label: 'Lecture'   },
              { value: 'fun',         label: 'Fun'         },
            ]}
          />
          <Select
            label="AUDIENCE"
            value={audience}
            onChange={setAudience}
            options={[
              { value: 'self',          label: 'Self'          },
              { value: 'undergraduate', label: 'Undergrad'     },
              { value: 'graduate',      label: 'Graduate'      },
              { value: 'research',      label: 'Research'      },
            ]}
          />
          <Select
            label="RIGOR"
            value={rigor}
            onChange={setRigor}
            options={[
              { value: 'sketch',           label: 'Sketch'        },
              { value: 'intuition_first',  label: 'Intuition'     },
              { value: 'full',             label: 'Full'          },
            ]}
          />
        </div>
      )}

      <button
        onClick={handleStart}
        disabled={loading || !topic.trim()}
        style={{
          marginTop: 14, width: '100%', background: 'var(--gold)', color: '#0e0d0b',
          border: 'none', padding: '13px 0',
          fontSize: 15, letterSpacing: '0.04em',
          opacity: loading ? 0.6 : 1,
        }}
      >
        {loading ? 'Starting…' : 'Begin Exploration'}
      </button>
    </div>
  )
}

export { AGENTS }
